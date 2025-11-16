from __future__ import annotations

import asyncio
import threading
import traceback
from collections import defaultdict
from contextlib import suppress
from contextvars import ContextVar
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from flowtrace.asyncio_support import (
    ASYNC_PARENT,
    get_async_id,
    install_task_factory,
    uninstall_task_factory,
)
from flowtrace.events import (
    AsyncTransitionEvent,
    CallEvent,
    ExceptionEvent,
    ExecutionContext,
    TraceEvent,
)
from flowtrace.monitoring import _is_user_code

CURRENT_SESSION: ContextVar[TraceSession | None] = ContextVar(
    "flowtrace_session",
    default=None,
)


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

        self.events: list[TraceEvent] = []
        self.stack: list[tuple[str, float, int]] = []

        # очередь метаданных от декоратора для КОНКРЕТНОГО следующего вызова функции
        # func_name -> list of (args_repr, collect_args, collect_result, collect_timing, collect_exc_tb, exc_tb_depth)
        self.pending_meta: dict[Any, list[tuple[str | None, bool, bool, bool, bool, int]]] = (
            defaultdict(list)
        )

        self.open_exc_events: dict[int, list[int]] = defaultdict(
            list
        )  # "открытые" исключения на фрейм
        self.current_exc_by_call: dict[int, int] = {}  # call_event_id -> event_id исключения
        self._exc_prefs_by_call: dict[int, tuple[bool, int]] = {}

        self.context = ExecutionContext(
            thread_id=threading.get_ident(),
            task_id=None,
            task_parent_id=None,
            task_name=None,
        )

    @staticmethod
    def _async_hooks_on():
        """Включаем слежение за asyncio.Tasks, если есть running loop."""
        if asyncio is None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # нет запущенного event loop → просто не включаем async-хуки
            return

        with suppress(Exception):
            install_task_factory(loop)

    @staticmethod
    def _async_hooks_off():
        """Выключаем слежение за asyncio, если есть running loop."""
        if asyncio is None:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        with suppress(Exception):
            uninstall_task_factory(loop)

    def start(self) -> None:
        if self.active:
            return
        self.active = True
        self._async_hooks_on()

    def stop(self) -> list[TraceEvent]:
        if not self.active:
            return self.events

        self.active = False
        self._async_hooks_off()
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
        if isinstance(call_ev, CallEvent):
            collect_timing = call_ev.collect_timing
            collect_result = call_ev.collect_result
        else:
            collect_timing = False
            collect_result = False

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

    def on_async_transition(
        self,
        kind: Literal["await", "resume", "yield"],
        func_name: str,
        detail: str | None = None,
    ) -> None:
        if not self.active:
            return

        async_id: int | None = None
        parent_async_id: int | None = None

        if asyncio is not None:
            try:
                async_id = get_async_id()
                if async_id is not None:
                    parent_async_id = ASYNC_PARENT.get(async_id)
            except Exception:
                # если что-то странное с asyncio — просто не заполняем async_id
                async_id = None
                parent_async_id = None

        ctx = getattr(self, "context", None)

        ev = AsyncTransitionEvent(
            id=len(self.events),
            kind=kind,
            func_name=func_name,
            async_id=async_id,
            parent_async_id=parent_async_id,
            detail=detail,
            context=ctx,
        )
        self.events.append(ev)

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
            if isinstance(ev, ExceptionEvent):
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
                ev = self.events[ev_id]
                if isinstance(ev, ExceptionEvent) and ev.caught is not False:
                    ev.caught = False
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
            ev = self.events[ev_id]
            if isinstance(ev, ExceptionEvent):
                ev.caught = False
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
        self.pending_meta[func_name].append((
            args_repr,
            collect_args,
            collect_result,
            collect_timing,
            collect_exc_tb,
            exc_tb_depth,
        ))

    def get_execution_context(self) -> ExecutionContext:
        return self.context

    def _handle_raise(self, func_name: str, exc: BaseException | None):
        if not self.active:
            return

        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""

        call_id = self.get_current_call_id(func_name)
        if call_id is None and self.stack:
            _, _, call_id = self.stack[-1]

        collect_tb, depth = self.get_exc_prefs(call_id if call_id is not None else -1)

        tb_text = None
        if exc is not None and collect_tb:
            tb = exc.__traceback__
            if tb:
                raw_frames = traceback.extract_tb(tb)

                # фильтр по user-path
                from flowtrace.monitoring import _is_user_path

                frames = [f for f in raw_frames if _is_user_path(f.filename)]

                if not frames:
                    frames = raw_frames

                frames = frames[-depth:]

                tb_text = " | ".join(
                    f"{Path(fr.filename).name}:{fr.lineno} in {fr.name}" for fr in frames
                )

        self.on_exception_raised(func_name, exc_type, exc_msg, tb_text)

    def _handle_reraise(self, func_name: str, exc: BaseException | None):
        if not self.active:
            return

        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""

        self.on_reraise(func_name, exc_type, exc_msg)

    def _handle_exc_handled(self, func_name: str, exc: BaseException | None):
        if not self.active:
            return

        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""

        self.on_exception_handled(func_name, exc_type, exc_msg)

    def _handle_unwind(self, func_name: str, exc: BaseException | None):
        if not self.active:
            return

        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""

        self.on_unwind(func_name, exc_type, exc_msg)

    @staticmethod
    def _resolve_real_name(code, default: str) -> str:
        REAL = default
        try:
            import gc
            import inspect

            for obj in gc.get_referrers(code):
                if (inspect.isfunction(obj) or inspect.ismethod(obj)) and getattr(
                    obj, "__code__", None
                ) is code:
                    real = getattr(obj, "__flowtrace_real_name__", None)
                    if real:
                        REAL = real
                    break
        except Exception:
            pass
        return REAL

    @staticmethod
    def _safe_repr(value) -> str | None:
        if value is None:
            return None
        try:
            r = repr(value)
            return r if len(r) <= 80 else r[:77] + "..."
        except Exception:
            return "<unrepr>"

    def on_raw_event(self, label: str, code, raw):
        if not _is_user_code(code):
            return
        func_name = self._resolve_real_name(code, code.co_name)

        if label == "PY_START":
            self.on_call(func_name)

        elif label == "PY_RETURN":
            value = raw[-1] if raw else None
            self.on_return(func_name, value)

        elif label == "RAISE":
            exc = raw[-1] if raw else None
            self._handle_raise(func_name, exc)

        elif label == "RERAISE":
            exc = raw[-1] if raw else None
            self._handle_reraise(func_name, exc)

        elif label == "EXCEPTION_HANDLED":
            exc = raw[-1] if raw else None
            self._handle_exc_handled(func_name, exc)

        elif label == "PY_UNWIND":
            exc = raw[-1] if raw else None
            self._handle_unwind(func_name, exc)

        elif label == "PY_RESUME":
            self.on_async_transition("resume", func_name)

        elif label == "PY_YIELD":
            value = raw[-1] if raw else None
            detail = self._safe_repr(value)
            self.on_async_transition("yield", func_name, detail)
