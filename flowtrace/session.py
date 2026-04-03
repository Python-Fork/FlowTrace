from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, field
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
from flowtrace.raw_dispatcher import RawEventDispatcher

CURRENT_SESSION: ContextVar[TraceSession | None] = ContextVar(
    "flowtrace_session",
    default=None,
)


@dataclass(slots=True)
class ActiveCall:
    """Активный вызов в стеке."""

    call_event_id: int
    func_name: str
    start_time: float


@dataclass(slots=True)
class PendingCallMeta:
    """Метаданные для следующего вызова конкретной функции."""

    args_repr: str | None
    show_args: bool
    show_result: bool
    show_timing: bool
    exc_tb_depth: int


@dataclass(slots=True)
class SessionState:
    """Хранение состояния трассировки."""

    active: bool = False
    events: list[TraceEvent] = field(default_factory=list)
    stack: list[ActiveCall] = field(default_factory=list)
    # очередь метаданных от декоратора для КОНКРЕТНОГО следующего вызова функции
    # func_name -> list[PendingCallMeta]
    pending_meta: defaultdict[str, list[PendingCallMeta]] = field(
        default_factory=lambda: defaultdict(list)
    )
    current_exc_by_call: dict[int, int] = field(
        default_factory=dict
    )  # call_event_id -> event_id исключения
    exc_depth_by_call: dict[int, int] = field(default_factory=dict)


class ExecutionContextProvider:
    @staticmethod
    def get_current() -> ExecutionContext:
        """Возвращает свежий ExecutionContext для текущего события."""
        thread_id = threading.get_ident()
        task_id = None
        parent_id = None
        task_name = None

        try:
            task = asyncio.current_task()
        except RuntimeError:
            task = None

        if task is not None:
            task_id = get_async_id(task)
            if task_id is not None:
                parent_id = ASYNC_PARENT.get(task_id)
            with suppress(Exception):
                task_name = task.get_name()

        return ExecutionContext(
            thread_id=thread_id,
            task_id=task_id,
            task_parent_id=parent_id,
            task_name=task_name,
        )


class CallStackInspector:
    """
    Read-only helper для работы со стеком активных вызовов.

    Инспектор не изменяет состояние трассировки и предоставляет
    только безопасные методы чтения текущего стека вызовов.
    Основной идентификатор вызова — ``call_event_id``.
    """

    def __init__(self, state: SessionState) -> None:
        """
        Инициализирует инспектор стека вызовов.
        """
        self.state = state

    def top_call(self) -> ActiveCall | None:
        """
        Возвращает верхний активный вызов из стека.
        """
        if not self.state.stack:
            return None
        return self.state.stack[-1]

    def top_call_event_id(self) -> int | None:
        """
        Возвращает ``call_event_id`` верхнего активного вызова.
        """
        active_call = self.top_call()
        if active_call is None:
            return None
        return active_call.call_event_id

    def find_by_call_event_id(self, call_event_id: int) -> ActiveCall | None:
        """
        Ищет активный вызов в стеке по ``call_event_id``.

        Поиск выполняется с конца стека, так как наиболее
        вероятно нужный вызов находится ближе к вершине.
        """
        for active_call in reversed(self.state.stack):
            if active_call.call_event_id == call_event_id:
                return active_call
        return None

    def current_call_event_id(self) -> int | None:
        """
        Возвращает ``call_event_id`` текущего активного вызова.
        Это алиас для идентификатора верхнего вызова в стеке.
        """
        return self.top_call_event_id()

    def current_active_call(self) -> ActiveCall | None:
        """
        Возвращает текущий активный вызов.
        Это алиас верхнего элемента стека вызовов.
        """
        return self.top_call()


class CallTracker:
    def __init__(
        self,
        state: SessionState,
        stack_inspector: CallStackInspector,
        execution_context_provider: ExecutionContextProvider,
        *,
        default_show_args: bool,
        default_show_result: bool,
        default_show_timing: bool,
        default_exc_tb_depth: int,
    ):
        self.state = state
        self.stack_inspector = stack_inspector
        self.execution_context_provider = execution_context_provider

        self.default_show_args = default_show_args
        self.default_show_result = default_show_result
        self.default_show_timing = default_show_timing
        self.default_exc_tb_depth = default_exc_tb_depth

    def on_call(self, func_name: str) -> None:
        if not self.state.active:
            return

        parent_id = self.state.stack[-1].call_event_id if self.state.stack else None
        meta = self._resolve_meta(func_name)

        args_repr = meta.args_repr
        show_args = meta.show_args
        show_result = meta.show_result
        show_timing = meta.show_timing
        exc_tb_depth = meta.exc_tb_depth

        start_time = perf_counter() if show_timing else 0.0
        call_event_id = len(self.state.events)
        context = self.execution_context_provider.get_current()

        self.state.events.append(
            CallEvent(
                id=call_event_id,
                kind="call",
                func_name=func_name,
                parent_id=parent_id,
                args_repr=args_repr if show_args else None,
                show_args=show_args,
                show_result=show_result,
                show_timing=show_timing,
                context=context,
            )
        )
        self.state.stack.append(
            ActiveCall(
                func_name=func_name,
                start_time=start_time,
                call_event_id=call_event_id,
            )
        )
        # Запоминаем глубину traceback именно для этого call_id
        self.state.exc_depth_by_call[call_event_id] = exc_tb_depth

    def _resolve_meta(self, func_name: str) -> PendingCallMeta:
        q = self.state.pending_meta.get(func_name)
        if q:
            meta = q.pop(0)
            if not q:
                self.state.pending_meta.pop(func_name, None)
            return meta

        return PendingCallMeta(
            args_repr=None,
            show_args=self.default_show_args,
            show_result=self.default_show_result,
            show_timing=self.default_show_timing,
            exc_tb_depth=self.default_exc_tb_depth,
        )

    def _close_top_call(
        self,
        *,
        result: Any = None,
        via_exception: bool = False,
    ) -> int | None:
        if not self.state.active:
            return None

        active_call = self.stack_inspector.current_active_call()
        if active_call is None:
            return None

        call_event_id = active_call.call_event_id
        func_name = active_call.func_name
        start_time = active_call.start_time

        call_ev = self.state.events[call_event_id]
        if isinstance(call_ev, CallEvent):
            show_timing = call_ev.show_timing
            show_result = call_ev.show_result
        else:
            show_timing = False
            show_result = False

        duration: float | None = None
        if show_timing and start_time > 0.0:
            duration = perf_counter() - start_time

        result_repr: str | None = None
        if not via_exception and show_result:
            try:
                r = repr(result)
                if len(r) > 60:
                    r = r[:57] + "..."
                result_repr = r
            except Exception:
                result_repr = "<unrepr>"

        context = self.execution_context_provider.get_current()

        self.state.events.append(
            CallEvent(
                id=len(self.state.events),
                kind="return",
                func_name=func_name,
                parent_id=call_event_id,
                result_repr=result_repr,
                duration=duration,
                via_exception=via_exception,
                context=context,
            )
        )

        self.state.stack.pop()
        return call_event_id

    def on_return(self, result: Any = None) -> None:
        self._close_top_call(result=result, via_exception=False)

    def close_via_exception(self) -> int | None:
        return self._close_top_call(via_exception=True)


class ExceptionTracker:
    def __init__(
        self,
        state: SessionState,
        stack_inspector: CallStackInspector,
        execution_context_provider: ExecutionContextProvider,
        call_tracker: CallTracker,
    ):
        self.state = state
        self.stack_inspector = stack_inspector
        self.execution_context_provider = execution_context_provider
        self.call_tracker = call_tracker

    def _append_exception(
        self,
        call_event_id: int | None,
        func_name: str,
        exc_type: str,
        exc_msg: str,
        caught: bool | None,
        exc_tb: str | None = None,
    ) -> int:
        context = self.execution_context_provider.get_current()

        ev = ExceptionEvent(
            id=len(self.state.events),
            func_name=func_name,
            parent_id=call_event_id,
            exc_type=exc_type,
            exc_msg=exc_msg,
            caught=caught,
            via_exception=False,  # это просто “исключение произошло”, а не “return через exc”
            exc_tb=exc_tb,
            context=context,
        )

        self.state.events.append(ev)

        if call_event_id is not None:
            # текущая активная запись исключения этого фрейма
            self.state.current_exc_by_call[call_event_id] = ev.id
        return ev.id

    def on_exception_raised(
        self,
        func_name: str,
        exc_type: str,
        exc_msg: str,
        exc_tb: str | None = None,
    ) -> None:
        # при raised exception мы еще не знаем судьбу этого exception, поэтому его статус будет None.
        if not self.state.active:
            return

        call_event_id = self.stack_inspector.current_call_event_id()

        self._append_exception(
            call_event_id, func_name, exc_type, exc_msg, caught=None, exc_tb=exc_tb
        )

    def on_exception_handled(self, func_name: str, exc_type: str, exc_msg: str) -> None:
        # если exception попадает в EXCEPTION_HANDLED, то except уже сработал - убираем из открытых
        if not self.state.active:
            return

        call_event_id = self.stack_inspector.current_call_event_id()
        if call_event_id is None:
            self._append_exception(None, func_name, exc_type, exc_msg, caught=True)
            return

        ev_id = self.state.current_exc_by_call.pop(call_event_id, None)
        if ev_id is not None:
            ev = self.state.events[ev_id]
            if isinstance(ev, ExceptionEvent):
                ev.caught = True
            else:
                self._append_exception(call_event_id, func_name, exc_type, exc_msg, caught=True)
        else:
            self._append_exception(call_event_id, func_name, exc_type, exc_msg, caught=True)

    def on_unwind(self, func_name, exc_type, exc_msg):
        # сигнал о сворачивании кадра из-за exception, но не означает, что exception поймали.
        if not self.state.active:
            return

        call_event_id = self.stack_inspector.current_call_event_id()

        if call_event_id is not None:
            ev_id = self.state.current_exc_by_call.get(call_event_id)
            if ev_id is not None:
                ev = self.state.events[ev_id]
                if isinstance(ev, ExceptionEvent) and ev.caught is not False:
                    ev.caught = False
            else:
                self._append_exception(call_event_id, func_name, exc_type, exc_msg, caught=False)

        closed_call_event_id = self.call_tracker.close_via_exception()
        if closed_call_event_id is not None:
            self._clear_exception_state(closed_call_event_id)

    def on_reraise(self, func_name, exc_type, exc_msg):
        # сигнал о том, что исключение не погашено данным кадром и улетает дальше.
        if not self.state.active:
            return

        call_event_id = self.stack_inspector.current_call_event_id()
        if call_event_id is None:
            self._append_exception(None, func_name, exc_type, exc_msg, caught=False)
            return

        ev_id = self.state.current_exc_by_call.get(call_event_id)
        if ev_id is not None:
            ev = self.state.events[ev_id]
            if isinstance(ev, ExceptionEvent):
                ev.caught = False
            else:
                self._append_exception(call_event_id, func_name, exc_type, exc_msg, caught=False)
        else:
            self._append_exception(call_event_id, func_name, exc_type, exc_msg, caught=False)

    def _clear_exception_state(self, call_event_id: int) -> None:
        self.state.current_exc_by_call.pop(call_event_id, None)
        self.state.exc_depth_by_call.pop(call_event_id, None)


class AsyncTracker:
    def __init__(
        self,
        state: SessionState,
        execution_context_provider: ExecutionContextProvider,
    ):
        self.state = state
        self.execution_context_provider = execution_context_provider

    def on_async(
        self,
        kind: Literal["await", "resume", "yield"],
        func_name: str,
        detail: str | None = None,
    ) -> None:
        if not self.state.active:
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

        context = self.execution_context_provider.get_current()

        ev = AsyncTransitionEvent(
            id=len(self.state.events),
            kind=kind,
            func_name=func_name,
            async_id=async_id,
            parent_async_id=parent_async_id,
            detail=detail,
            context=context,
        )
        self.state.events.append(ev)


class TraceSession:
    def __init__(
        self,
        default_show_args: bool = True,
        default_show_result: bool = True,
        default_show_timing: bool = True,
        default_exc_tb_depth: int = 2,
    ):
        self.default_show_args = default_show_args
        self.default_show_result = default_show_result
        self.default_show_timing = default_show_timing
        self.default_exc_tb_depth = default_exc_tb_depth

        self.state = SessionState()
        self.stack_inspector = CallStackInspector(self.state)
        self.execution_context_provider = ExecutionContextProvider()
        self.call_tracker = CallTracker(
            state=self.state,
            stack_inspector=self.stack_inspector,
            default_show_timing=self.default_show_timing,
            default_exc_tb_depth=self.default_exc_tb_depth,
            default_show_result=self.default_show_result,
            default_show_args=self.default_show_args,
            execution_context_provider=self.execution_context_provider,
        )
        self.exception_tracker = ExceptionTracker(
            state=self.state,
            stack_inspector=self.stack_inspector,
            execution_context_provider=self.execution_context_provider,
            call_tracker=self.call_tracker,
        )
        self.async_tracker = AsyncTracker(
            state=self.state, execution_context_provider=self.execution_context_provider
        )
        self.raw_dispatcher = RawEventDispatcher(
            state=self.state,
            stack_inspector=self.stack_inspector,
            call_tracker=self.call_tracker,
            exception_tracker=self.exception_tracker,
            async_tracker=self.async_tracker,
            default_exc_tb_depth=self.default_exc_tb_depth,
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
        if self.state.active:
            return
        self.state.active = True
        self._async_hooks_on()

    def stop(self) -> list[TraceEvent]:
        if not self.state.active:
            return self.state.events

        self.state.active = False
        self._async_hooks_off()
        return self.state.events
