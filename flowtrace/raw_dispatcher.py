from __future__ import annotations

import traceback
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from flowtrace.monitoring import _is_user_code, _is_user_path

if TYPE_CHECKING:
    from types import CodeType

    from flowtrace.session import (
        AsyncTracker,
        CallStackInspector,
        CallTracker,
        ExceptionTracker,
        SessionState,
    )
from flowtrace.utils.code_flags import is_async_gen_code, is_coroutine_code


class CodeNameResolver:
    """
    Разрешает отображаемое имя функции по code object.

    Использует внутренний кэш ``code -> resolved_name``, чтобы
    не выполнять дорогой поиск через ``gc.get_referrers(...)``
    на каждом raw-событии.
    """

    def __init__(self) -> None:
        self._cache: dict[CodeType, str] = {}

    def resolve(self, code: CodeType) -> str:
        """
        Возвращает имя функции для указанного code object.

        Сначала проверяет кэш. Если имя ещё не было вычислено,
        пытается найти функцию или метод, ссылающийся на данный
        ``code`` object, и извлечь ``__flowtrace_real_name__``.
        Если это не удалось, использует ``code.co_name``.

        :param code: Code object исполняемой функции.
        :return: Разрешённое имя функции.
        """
        if code in self._cache:
            return self._cache[code]

        resolved_name = code.co_name

        try:
            import gc
            import inspect

            for obj in gc.get_referrers(code):
                if (inspect.isfunction(obj) or inspect.ismethod(obj)) and getattr(
                    obj, "__code__", None
                ) is code:
                    real = getattr(obj, "__flowtrace_real_name__", None)
                    if real:
                        resolved_name = real
                    break
        except Exception:
            pass

        self._cache[code] = resolved_name
        return resolved_name


class RawEventDispatcher:
    def __init__(
        self,
        state: SessionState,
        call_tracker: CallTracker,
        exception_tracker: ExceptionTracker,
        async_tracker: AsyncTracker,
        stack_inspector: CallStackInspector,
        *,
        default_exc_tb_depth: int,
    ):
        self.state = state
        self.call_tracker = call_tracker
        self.exception_tracker = exception_tracker
        self.async_tracker = async_tracker
        self.stack_inspector = stack_inspector
        self.default_exc_tb_depth = default_exc_tb_depth

        self.code_name_resolver = CodeNameResolver()

    def dispatch(self, label: str, code: CodeType, raw: tuple[Any, ...]) -> None:
        if not _is_user_code(code):
            return

        func_name = self.code_name_resolver.resolve(code)

        if label == "PY_START":
            self.call_tracker.on_call(func_name)
            return

        elif label == "PY_RETURN":
            value = raw[-1] if raw else None
            self.call_tracker.on_return(value)
            return

        elif label == "RAISE":
            exc = raw[-1] if raw else None
            self._dispatch_raise(func_name, exc)
            return

        elif label == "RERAISE":
            exc = raw[-1] if raw else None
            exc_type, exc_msg = self._extract_exc_info(exc)
            self.exception_tracker.on_reraise(func_name, exc_type, exc_msg)
            return

        elif label == "EXCEPTION_HANDLED":
            exc = raw[-1] if raw else None
            exc_type, exc_msg = self._extract_exc_info(exc)
            self.exception_tracker.on_exception_handled(func_name, exc_type, exc_msg)
            return

        elif label == "PY_UNWIND":
            exc = raw[-1] if raw else None
            exc_type, exc_msg = self._extract_exc_info(exc)
            self.exception_tracker.on_unwind(func_name, exc_type, exc_msg)
            return

        elif label == "PY_RESUME":
            self.async_tracker.on_async("resume", func_name)
            return

        elif label == "PY_YIELD":
            value = raw[-1] if raw else None
            detail = self._safe_repr(value)

            if is_async_gen_code(code):
                kind: Literal["await", "resume", "yield"] = "yield"
            elif is_coroutine_code(code):
                kind = "await"
            else:
                kind = "yield"

            self.async_tracker.on_async(kind, func_name, detail)

    def _dispatch_raise(self, func_name: str, exc: BaseException | None) -> None:
        exc_type, exc_msg = self._extract_exc_info(exc)

        call_event_id = self.stack_inspector.current_call_event_id()
        if call_event_id is None and self.state.stack:
            call_event_id = self.state.stack[-1].call_event_id

        depth = self.state.exc_depth_by_call.get(
            call_event_id if call_event_id is not None else -1,
            self.default_exc_tb_depth,
        )

        tb_text = self._format_exc_tb(exc, depth)

        self.exception_tracker.on_exception_raised(
            func_name,
            exc_type,
            exc_msg,
            tb_text,
        )

    @staticmethod
    def _extract_exc_info(exc: BaseException | None) -> tuple[str, str]:
        exc_type = type(exc).__name__ if exc is not None else "<unknown>"
        exc_msg = str(exc) if exc is not None else ""
        return exc_type, exc_msg

    @staticmethod
    def _format_exc_tb(exc: BaseException | None, depth: int) -> str | None:
        if exc is None or depth <= 0:
            return None

        tb = exc.__traceback__
        if not tb:
            return None

        raw_frames = traceback.extract_tb(tb)
        frames = [f for f in raw_frames if _is_user_path(f.filename)]
        if not frames:
            frames = raw_frames

        frames = frames[-depth:]
        return " | ".join(f"{Path(fr.filename).name}:{fr.lineno} in {fr.name}" for fr in frames)

    @staticmethod
    def _safe_repr(value: Any) -> str | None:
        if value is None:
            return None
        try:
            r = repr(value)
            return r if len(r) <= 80 else r[:77] + "..."
        except Exception:
            return "<unrepr>"
