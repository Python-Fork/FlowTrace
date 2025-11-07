from __future__ import annotations

import logging
import sys
import traceback
import weakref
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from flowtrace.config import get_config

Cb = Callable[..., None]

# Текущая активная сессия FlowTrace (асинхронно-изолированная)
_CURRENT_SESSION: ContextVar[TraceSession | None] = ContextVar("flowtrace_session", default=None)


@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: int | None = None

    # payload (заполняются строго по флагам)
    args_repr: str | None = None
    result_repr: str | None = None
    duration: float | None = None

    # для exception
    exc_type: str | None = None
    exc_msg: str | None = None
    caught: bool | None = None  # None = "открытое", True = "поймано", False = "ушло наружу"
    via_exception: bool = False
    exc_tb: str | None = None  # компактный срез traceback (если собирали)

    # флаги того, что ДОЛЖНО было собираться для этого вызова
    collect_args: bool = False
    collect_result: bool = False
    collect_timing: bool = False


class TraceSession:
    def __init__(
        self,
        default_collect_args: bool = True,
        default_collect_result: bool = True,
        default_collect_timing: bool = True,
        default_collect_exc_tb: bool = False,
        default_exc_tb_depth: int = 2,
    ):
        self.active: bool = False

        self.default_collect_args = default_collect_args
        self.default_collect_result = default_collect_result
        self.default_collect_timing = default_collect_timing
        self.default_collect_exc_tb = default_collect_exc_tb
        self.default_exc_tb_depth = default_exc_tb_depth

        self.events: list[CallEvent] = []
        self.stack: list[tuple[str, float, int]] = []

        # очередь метаданных от декоратора для КОНКРЕТНОГО следующего вызова функции
        # func_name -> list of (args_repr, collect_args, collect_result, collect_timing, collect_exc_tb, exc_tb_depth)
        self.pending_meta: dict[Any, list[tuple[str | None, bool, bool, bool, bool, int]]] = (
            defaultdict(list)
        )

        self._cb_start: Cb | None = None
        self._cb_return: Cb | None = None

        self._cb_raise: Cb | None = None
        self._cb_reraise: Cb | None = None
        self._cb_unwind: Cb | None = None
        self._cb_exc_handled: Cb | None = None
        self._cb_c_raise: Cb | None = None

        self.open_exc_events: dict[int, list[int]] = defaultdict(
            list
        )  # "открытые" исключения на фрейм
        self.current_exc_by_call: dict[int, int] = {}  # call_event_id -> event_id исключения
        self._exc_prefs_by_call: dict[int, tuple[bool, int]] = {}

    def start(self) -> None:
        if self.active:
            return
        self.active = True

        self._cb_start = _make_handler("PY_START")
        self._cb_return = _make_handler("PY_RETURN")

        self._cb_raise = _make_handler("RAISE")
        self._cb_reraise = _make_handler("RERAISE")
        self._cb_unwind = _make_handler("PY_UNWIND")
        self._cb_exc_handled = _make_handler("EXCEPTION_HANDLED")
        self._cb_c_raise = _make_handler("C_RAISE")

        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_START, self._cb_start)
        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_RETURN, self._cb_return)

        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.RAISE, self._cb_raise)
        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.RERAISE, self._cb_reraise)
        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_UNWIND, self._cb_unwind)
        sys.monitoring.register_callback(
            TOOL_ID, sys.monitoring.events.EXCEPTION_HANDLED, self._cb_exc_handled
        )
        # sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.C_RAISE, self._cb_c_raise)

        sys.monitoring.set_events(
            TOOL_ID,
            sys.monitoring.events.PY_START
            | sys.monitoring.events.PY_RETURN
            | sys.monitoring.events.RAISE
            | sys.monitoring.events.RERAISE
            | sys.monitoring.events.PY_UNWIND
            | sys.monitoring.events.EXCEPTION_HANDLED,
        )

    def stop(self) -> list[CallEvent]:
        if not self.active:
            return self.events

        self.active = False

        current = sys.monitoring.get_events(TOOL_ID)
        if current != sys.monitoring.events.NO_EVENTS:
            sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.NO_EVENTS)

        if getattr(self, "_cb_start", None):
            sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_START, None)
            self._cb_start = None

        if getattr(self, "_cb_return", None):
            sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.PY_RETURN, None)
            self._cb_return = None

        for ev, attr in [
            (sys.monitoring.events.RAISE, "_cb_raise"),
            (sys.monitoring.events.RERAISE, "_cb_reraise"),
            (sys.monitoring.events.PY_UNWIND, "_cb_unwind"),
            (sys.monitoring.events.EXCEPTION_HANDLED, "_cb_exc_handled"),
            (sys.monitoring.events.C_RAISE, "_cb_c_raise"),
        ]:
            if getattr(self, attr, None):
                sys.monitoring.register_callback(TOOL_ID, ev, None)
                setattr(self, attr, None)

        return self.events

    def on_call(self, func_name: str) -> None:
        if not self.active:
            return

        parent_id = self.stack[-1][2] if self.stack else None

        collect_args = self.default_collect_args
        collect_result = self.default_collect_result
        collect_timing = self.default_collect_timing
        collect_exc_tb = self.default_collect_exc_tb

        exc_tb_depth = self.default_exc_tb_depth
        args_repr: str | None = None

        q = self.pending_meta.get(func_name)
        if q:
            (
                args_repr,
                collect_args,
                collect_result,
                collect_timing,
                collect_exc_tb,
                exc_tb_depth,
            ) = q.pop(0)
            if not q:
                self.pending_meta.pop(func_name, None)

        start_time = perf_counter() if collect_timing else 0.0

        event_id = len(self.events)
        self.stack.append((func_name, start_time, event_id))
        self.events.append(
            CallEvent(
                id=event_id,
                kind="call",
                func_name=func_name,
                parent_id=parent_id,
                args_repr=args_repr if collect_args else None,
                collect_args=collect_args,
                collect_result=collect_result,
                collect_timing=collect_timing,
            )
        )
        # Чтобы не раздувать CallEvent, запоминаем настройки по call_id
        self._exc_prefs_by_call[event_id] = (collect_exc_tb, exc_tb_depth)

    def on_return(self, func_name: str, result: Any = None) -> None:
        if not self.active:
            return

        frame_index = None
        for i in range(len(self.stack) - 1, -1, -1):
            name, _, _ = self.stack[i]
            if name == func_name:
                frame_index = i
                break
        if frame_index is None:
            return

        name, start, event_id = self.stack[frame_index]
        call_ev = self.events[event_id]
        collect_timing = call_ev.collect_timing
        collect_result = call_ev.collect_result

        del self.stack[frame_index:]

        end: float = perf_counter() if collect_timing else 0.0
        if collect_timing and start is not None:
            duration = end - start
        else:
            duration = None

        result_repr: str | None = None
        if collect_result:
            with suppress(Exception):
                r = repr(result)
                if len(r) > 60:
                    r = r[:57] + "..."
                result_repr = r
            if "result_repr" not in locals():
                result_repr = "<unrepr>"

        self.events.append(
            CallEvent(
                id=len(self.events),
                kind="return",
                func_name=func_name,
                parent_id=event_id,
                result_repr=result_repr,
                duration=duration,
            )
        )

    def get_current_call_id(self, func_name: str) -> int | None:
        """Публичная обёртка над _current_call_event_id (для внешнего использования внутри ядра)."""
        return self._current_call_event_id(func_name)

    def get_exc_prefs(self, call_event_id: int) -> tuple[bool, int]:
        """
        Возвращает (collect_exc_tb, exc_tb_depth) для данного вызова.
        Безопасная обёртка над внутренним словарём _exc_prefs_by_call.
        """
        return self._exc_prefs_by_call.get(
            call_event_id,
            (self.default_collect_exc_tb, self.default_exc_tb_depth),
        )

    def _find_frame_index(self, func_name: str) -> int | None:
        for i, (name, _, _) in enumerate(reversed(self.stack), start=1):
            if name == func_name:
                return len(self.stack) - i
        return None

    def _current_call_event_id(self, func_name: str) -> int | None:
        idx = self._find_frame_index(func_name)
        if idx is None:
            return None
        return self.stack[idx][2]

    def _append_exception(
        self,
        call_event_id: int | None,
        func_name: str,
        exc_type: str,
        exc_msg: str,
        caught: bool | None,
        exc_tb: str | None = None,
    ) -> int:
        ev = CallEvent(
            id=len(self.events),
            kind="exception",
            func_name=func_name,
            parent_id=call_event_id,
            exc_type=exc_type,
            exc_msg=exc_msg,
            exc_tb=exc_tb,
            caught=caught,
        )
        self.events.append(ev)
        if call_event_id is not None:
            # текущая активная запись исключения этого фрейма
            self.current_exc_by_call[call_event_id] = ev.id
            # «открытым» считаем только когда статус ещё не определён
            if caught is None:
                self.open_exc_events[call_event_id].append(ev.id)
        return ev.id

    def on_exception_raised(self, func_name: str, exc_type: str, exc_msg: str, exc_tb=None) -> None:
        # при raised exception мы еще не знаем судьбу этого exception, поэтому его статус будет None.
        if not self.active:
            return
        call_id = self._current_call_event_id(func_name)
        # нужно ли собирать traceback
        collect_tb, _ = self._exc_prefs_by_call.get(
            call_id if call_id is not None else -1,
            (self.default_collect_exc_tb, self.default_exc_tb_depth),
        )
        tb_text = exc_tb if collect_tb else None
        self._append_exception(call_id, func_name, exc_type, exc_msg, caught=None, exc_tb=tb_text)

    def on_exception_handled(self, func_name: str, exc_type: str, exc_msg: str) -> None:
        # если exception попадает в EXCEPTION_HANDLED, то except уже сработал - убираем из открытых
        if not self.active:
            return

        call_id = self._current_call_event_id(func_name)
        if call_id is None:
            self._append_exception(None, func_name, exc_type, exc_msg, caught=True)
            return

        ev_id = self.current_exc_by_call.get(call_id)
        if ev_id is not None:
            ev = self.events[ev_id]
            ev.caught = True
            self.open_exc_events.get(call_id, []).clear()
        else:
            self._append_exception(call_id, func_name, exc_type, exc_msg, caught=True)

    def on_unwind(self, func_name, exc_type, exc_msg):
        # сигнал о сворачивании кадра из-за exception, но не означает, что exception поймали.
        if not self.active:
            return
        idx = self._find_frame_index(func_name)
        if idx is not None:
            _, start, call_id = self.stack[idx]
            duration = None
            if start:
                duration = perf_counter() - start if start > 0.0 else None

            self.events.append(
                CallEvent(
                    id=len(self.events),
                    kind="return",
                    func_name=func_name,
                    parent_id=call_id,
                    result_repr=None,
                    duration=duration,
                    via_exception=True,
                )
            )

        current_call_id: int | None = self._current_call_event_id(func_name)
        if current_call_id is not None:
            ev_id = self.current_exc_by_call.get(current_call_id)
            if ev_id is not None:
                # уже есть активная — просто idempotent обновление
                if self.events[ev_id].caught is not False:
                    self.events[ev_id].caught = False
            else:
                # вообще не было записи → создадим одну «propagated»
                self._append_exception(current_call_id, func_name, exc_type, exc_msg, caught=False)
            # фрейм завершился исключением — чистим маркеры
            self.current_exc_by_call.pop(current_call_id, None)
            self.open_exc_events.pop(current_call_id, None)

        # снимаем фрейм
        if idx is not None:
            del self.stack[idx:]

    def on_reraise(self, func_name, exc_type, exc_msg):
        # сигнал о том, что исключение не погашено данным кадром и улетает дальше.
        if not self.active:
            return
        call_id = self._current_call_event_id(func_name)
        if call_id is None:
            self._append_exception(None, func_name, exc_type, exc_msg, caught=False)
            return
        ev_id = self.current_exc_by_call.get(call_id)
        if ev_id is not None:
            self.events[ev_id].caught = False
        else:
            self._append_exception(call_id, func_name, exc_type, exc_msg, caught=False)

    def push_meta_for_func(
        self,
        func_name: str,
        *,
        args_repr: str | None,
        collect_args: bool,
        collect_result: bool,
        collect_timing: bool,
        collect_exc_tb: bool,
        exc_tb_depth: int,
    ):
        """Кладём готовые метаданные ДЛЯ СЛЕДУЮЩЕГО вызова данной функции."""
        if not self.active:
            return
        self.pending_meta[func_name].append((
            args_repr,
            collect_args,
            collect_result,
            collect_timing,
            collect_exc_tb,
            exc_tb_depth,
        ))


def _reserve_tool_id(name: str = "flowtrace") -> int:
    for tool_id in range(1, 6):
        current = sys.monitoring.get_tool(tool_id)
        if current is None:
            sys.monitoring.use_tool_id(tool_id, name)
            return tool_id

    raise RuntimeError(
        "[FlowTrace] Failed to register Monitoring API: "
        "all tool IDs are occupied. "
        "Close any active debuggers or profilers and try again"
    )


def _norm(p: Path) -> str:
    # нормализуем и нижний регистр для кросплатформенности
    return str(p).replace("\\", "/").lower()


# --- globals & prefixes ------------------------------------------------------
_last_data: list[CallEvent] | None = None
TOOL_ID = _reserve_tool_id()

# системные и собственные пути (для фильтрации traceback)
_HERE_STR = _norm(Path(__file__).resolve().parent)
_STD_PREFIXES_STR = tuple(_norm(p) for p in {Path(sys.prefix), Path(sys.base_prefix)} if p.exists())

# слабый кэш для фильтрации кода (ускоряет _is_user_code)
_IS_USER_CODE_CACHE: weakref.WeakKeyDictionary[Any, bool] = weakref.WeakKeyDictionary()


def _is_user_code(code) -> bool:
    """Определяет, относится ли код к пользовательскому (а не stdlib/venv/самой FlowTrace)."""
    cached = _IS_USER_CODE_CACHE.get(code)
    if cached is not None:
        return cached
    try:
        p = Path(code.co_filename).resolve()
    except Exception:
        _IS_USER_CODE_CACHE[code] = False
        return False

    sp = _norm(p)

    # Разрешаем примеры внутри FlowTrace/examples
    if sp.startswith(_HERE_STR + "/examples"):
        _IS_USER_CODE_CACHE[code] = True
        return True

    # Скрываем саму либу
    if sp.startswith(_HERE_STR):
        _IS_USER_CODE_CACHE[code] = False
        return False

    # stdlib / venv / site-packages — тоже не показываем
    if any(sp.startswith(pref) for pref in _STD_PREFIXES_STR) or "site-packages/" in sp:
        _IS_USER_CODE_CACHE[code] = False
        return False

    _IS_USER_CODE_CACHE[code] = True
    return True


def _is_user_path(path: str) -> bool:
    """То же самое, но для обычного пути (строки)."""
    try:
        sp = _norm(Path(path).resolve())
    except Exception:
        return False

    if any(sp.startswith(pref) for pref in _STD_PREFIXES_STR) or "site-packages/" in sp:
        return False

    # не показываем саму FlowTrace
    return not sp.startswith(_HERE_STR)


def _on_event(label: str, code, raw_args):
    sess = _CURRENT_SESSION.get()
    if not (sess and sess.active):
        return

    func = getattr(code, "co_name", None) or (sess.stack[-1][0] if sess.stack else "<unknown>")

    if label == "PY_START":
        sess.on_call(func)
    elif label == "PY_RETURN":
        result = raw_args[-1]
        sess.on_return(func, result)
    elif label in ("RAISE", "C_RAISE"):
        # print(f"RAISE: {raw_args}")
        exc = raw_args[-1] if raw_args else None
        tb_text = None

        call_id = sess.get_current_call_id(func)
        if call_id is None and sess.stack:
            _, _, call_id = sess.stack[-1]

        collect_tb, depth = sess.get_exc_prefs(call_id if call_id is not None else -1)

        if exc is not None and collect_tb:
            tb = exc.__traceback__
            if tb:
                raw_frames = traceback.extract_tb(tb)
                frames = [f for f in raw_frames if _is_user_path(f.filename)]
                if not frames:
                    frames = raw_frames

                frames = frames[-depth:]
                tb_text = " | ".join(
                    f"{Path(fr.filename).name}:{fr.lineno} in {fr.name}" for fr in frames
                )

        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        sess.on_exception_raised(func, exc_type, exc_msg, tb_text)
    elif label == "RERAISE":
        # print(f"RERAISE: {raw_args}")
        exc = raw_args[-1] if raw_args else None
        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        sess.on_reraise(func, exc_type, exc_msg)
    elif label == "EXCEPTION_HANDLED":
        # print(f"EXCEPTION_HANDLED: {raw_args}")
        exc = raw_args[-1] if raw_args else None
        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        sess.on_exception_handled(func, exc_type, exc_msg)
    elif label == "PY_UNWIND":
        # print(f"PY_UNWIND: {raw_args}")
        exc = raw_args[-1] if raw_args else None
        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        sess.on_unwind(func, exc_type, exc_msg)


def _make_handler(event_label: str):
    def handler(*args):
        if not args:
            return
        code = args[0]
        with suppress(Exception):
            if not _is_user_code(code):
                return
        try:
            _on_event(event_label, code, args)
        except Exception as e:
            logging.debug("[flowtrace-debug] handler error: %s", e)

    return handler


def start_tracing(
    default_show_args: bool | None = None,
    default_show_result: bool | None = None,
    default_show_timing: bool | None = None,
    default_show_exc: bool | None = None,
) -> None:
    cfg = get_config()
    sess = TraceSession(
        default_collect_args=cfg.show_args if default_show_args is None else default_show_args,
        default_collect_result=cfg.show_result
        if default_show_result is None
        else default_show_result,
        default_collect_timing=cfg.show_timing
        if default_show_timing is None
        else default_show_timing,
        default_collect_exc_tb=True,
        default_exc_tb_depth=cfg.exc_depth() or 2,
    )
    sess.start()
    _CURRENT_SESSION.set(sess)


def is_tracing_active() -> bool:
    sess = _CURRENT_SESSION.get()
    return bool(sess and sess.active)


def stop_tracing() -> list[CallEvent]:
    global _last_data
    sess = _CURRENT_SESSION.get()
    if not sess:
        return []
    current = sys.monitoring.get_events(TOOL_ID)
    if current != sys.monitoring.events.NO_EVENTS:
        sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.NO_EVENTS)
    data = sess.stop()
    _last_data = data
    sys.monitoring._flowtrace_session = None  # type: ignore[attr-defined]
    return data


def get_trace_data() -> list[CallEvent]:
    return list(_last_data) if _last_data else []


@contextmanager
def active_tracing(**kwargs):
    """Контекстный менеджер для безопасной трассировки."""
    start_tracing(**kwargs)
    try:
        yield
    finally:
        stop_tracing()
