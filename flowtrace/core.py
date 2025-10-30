from __future__ import annotations

import logging
import sys

from dataclasses import dataclass
from time import perf_counter
from typing import Any, List, Optional
from pathlib import Path
from collections import defaultdict

from flowtrace.config import get_config


@dataclass
class CallEvent:
    id: int
    kind: str
    func_name: str
    parent_id: Optional[int] = None

    # payload (заполняются строго по флагам)
    args_repr: Optional[str] = None
    result_repr: Optional[str] = None
    duration: Optional[float] = None

    # для exception
    exc_type: Optional[str] = None
    exc_msg: Optional[str] = None
    caught: Optional[bool] = None   # None = "открытое", True = "поймано", False = "ушло наружу"

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
    ):
        self.active: bool = False

        self.default_collect_args = default_collect_args
        self.default_collect_result = default_collect_result
        self.default_collect_timing = default_collect_timing

        self.events: list[CallEvent] = []
        self.stack: list[tuple[str, float, int]] = []

        # очередь метаданных от декоратора для КОНКРЕТНОГО следующего вызова функции
        # func_name -> list of (args_repr, collect_args, collect_result, collect_timing)
        self.pending_meta: dict[Any, list[tuple[str | None, bool, bool, bool]]] = defaultdict(list)

        self._cb_start: Optional[callable] = None
        self._cb_return: Optional[callable] = None

        self._cb_raise: Optional[callable] = None
        self._cb_reraise: Optional[callable] = None
        self._cb_unwind: Optional[callable] = None
        self._cb_exc_handled: Optional[callable] = None
        self._cb_c_raise: Optional[callable] = None

        self.open_exc_events: dict[int, list[int]] = defaultdict(list)  # "открытые" исключения на фрейм
        self.current_exc_by_call: dict[int, int] = {}  # call_event_id -> event_id исключения

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
        sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.EXCEPTION_HANDLED, self._cb_exc_handled)
        # sys.monitoring.register_callback(TOOL_ID, sys.monitoring.events.C_RAISE, self._cb_c_raise)

        sys.monitoring.set_events(
            TOOL_ID,
            sys.monitoring.events.PY_START |
            sys.monitoring.events.PY_RETURN |
            sys.monitoring.events.RAISE |
            sys.monitoring.events.RERAISE |
            sys.monitoring.events.PY_UNWIND |
            sys.monitoring.events.EXCEPTION_HANDLED
        )

    def stop(self) -> list[CallEvent]:
        if not self.active:
            return self.events

        self.active = False

        current = sys.monitoring.get_events(TOOL_ID)
        if current != sys.monitoring.events.NO_EVENTS:
            sys.monitoring.set_events(TOOL_ID, sys.monitoring.events.NO_EVENTS)

        if getattr(self, "_cb_start", None):
            sys.monitoring.register_callback(
                TOOL_ID, sys.monitoring.events.PY_START, None
            )
            self._cb_start = None

        if getattr(self, "_cb_return", None):
            sys.monitoring.register_callback(
                TOOL_ID, sys.monitoring.events.PY_RETURN, None
            )
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
        args_repr: str | None = None

        q = self.pending_meta.get(func_name)
        if q:
            # данные только для ЭТОГО вызова; на детей не «протекают»
            args_repr, collect_args, collect_result, collect_timing = q.pop(0)
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

        end = perf_counter() if collect_timing else None
        duration = (end - start) if (start and collect_timing) else None

        result_repr: str | None = None
        if collect_result:
            try:
                r = repr(result)
                if len(r) > 60:
                    r = r[:57] + "..."
                result_repr = r
            except Exception:
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

    def _find_frame_index(self, func_name: str) -> Optional[int]:
        for i in range(len(self.stack) - 1, -1, -1):
            name, _, _ = self.stack[i]
            if name == func_name:
                return i
        return None

    def _current_call_event_id(self, func_name: str) -> Optional[int]:
        idx = self._find_frame_index(func_name)
        if idx is None:
            return None
        return self.stack[idx][2]

    def _append_exception(self, call_event_id: Optional[int], func_name: str,
                          exc_type: str, exc_msg: str, caught: Optional[bool]) -> int:
        ev = CallEvent(
            id=len(self.events),
            kind="exception",
            func_name=func_name,
            parent_id=call_event_id,
            exc_type=exc_type,
            exc_msg=exc_msg,
            caught=caught
        )
        self.events.append(ev)
        if call_event_id is not None:
            # текущая активная запись исключения этого фрейма\
            self.current_exc_by_call[call_event_id] = ev.id
            # «открытым» считаем только когда статус ещё не определён
            if caught is None:
                self.open_exc_events[call_event_id].append(ev.id)
        return ev.id

    def on_exception_raised(self, func_name: str, exc_type: str, exc_msg: str) -> None:
        if not self.active:
            return
        call_id = self._current_call_event_id(func_name)
        # новое «начало жизни» исключения в этом фрейме
        self._append_exception(call_id, func_name, exc_type, exc_msg, caught=None)

    def on_exception_handled(self, func_name: str, exc_type: str, exc_msg: str) -> None:
        if not self.active:
            return

        call_id = self._current_call_event_id(func_name)
        if call_id is None:
            self._append_exception(None, func_name, exc_type, exc_msg, caught=True)
            return
        ev_id = self.current_exc_by_call.get(call_id)
        if ev_id is not None:
            self.events[ev_id].caught = True
            # убираем из «открытых», если там числится
            stk = self.open_exc_events.get(call_id)
            if stk and ev_id in stk:
                try:
                    stk.remove(ev_id)
                except ValueError:
                    pass
        else:
            self._append_exception(call_id, func_name, exc_type, exc_msg, caught=True)

    def on_unwind(self, func_name, exc_type, exc_msg):
        if not self.active:
            return
        idx = self._find_frame_index(func_name)
        call_id = self._current_call_event_id(func_name)
        if call_id is not None:
            ev_id = self.current_exc_by_call.get(call_id)
            if ev_id is not None:
                # уже есть активная — просто idempotent обновление
                if self.events[ev_id].caught is not False:
                    self.events[ev_id].caught = False
            else:
                # вообще не было записи → создадим одну «propagated»
                self._append_exception(call_id, func_name, exc_type, exc_msg, caught=False)
            # фрейм завершился исключением — чистим маркеры
            self.current_exc_by_call.pop(call_id, None)
            self.open_exc_events.pop(call_id, None)

        # снимаем фрейм
        if idx is not None:
            del self.stack[idx:]

    def on_reraise(self, func_name, exc_type, exc_msg):
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
    ):
        """Кладём готовые метаданные ДЛЯ СЛЕДУЮЩЕГО вызова данной функции."""
        if not self.active:
            return
        self.pending_meta[func_name].append((args_repr, collect_args, collect_result, collect_timing))


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


_last_data: Optional[List[CallEvent]] = None
TOOL_ID = _reserve_tool_id()


def _is_user_code(code) -> bool:
    try:
        path = Path(code.co_filename).resolve()
    except Exception:
        return False

    str_path = str(path)
    here = Path(__file__).resolve().parent

    if str_path.startswith(str(here / "examples")):
        return True

    if str_path.startswith(str(here)):
        return False

    for prefix in (sys.prefix, sys.base_prefix):
        if str_path.startswith(str(Path(prefix).resolve())):
            return False

    if "site-packages" in str_path:
        return False

    return True


def _on_event(label: str, code, raw_args):
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
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
        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        sess.on_exception_raised(func, exc_type, exc_msg)
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
        try:
            if not _is_user_code(code):
                return
        except Exception:
            pass
        try:
            _on_event(event_label, code, args)
        except Exception as e:
            logging.debug("[flowtrace-debug] handler error:", e)

    return handler



def start_tracing(
    default_show_args: bool | None = None,
    default_show_result: bool | None = None,
    default_show_timing: bool | None = None,
) -> None:
    cfg = get_config()

    sess = TraceSession(
        default_collect_args=cfg["show_args"] if default_show_args is None else default_show_args,
        default_collect_result=cfg["show_result"] if default_show_result is None else default_show_result,
        default_collect_timing = cfg["show_timing"] if default_show_timing is None else default_show_timing
    )
    sess.start()
    setattr(sys.monitoring, "_flowtrace_session", sess)


def is_tracing_active() -> bool:
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    return bool(sess and sess.active)


def stop_tracing() -> List[CallEvent]:
    global  _last_data
    sess = getattr(sys.monitoring, "_flowtrace_session", None)
    if not sess:
        return []
    data = sess.stop()
    _last_data = data
    setattr(sys.monitoring, "_flowtrace_session", None)
    return data


def get_trace_data() -> List[CallEvent]:
    return list(_last_data) if _last_data else []
