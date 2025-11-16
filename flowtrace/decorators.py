import inspect
import sys
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast, overload

from .config import get_config
from .core import get_trace_data, is_tracing_active, start_tracing, stop_tracing
from .formatters import print_tree

F = TypeVar("F", bound=Callable[..., Any])


@overload
def trace(func: F) -> F: ...
@overload
def trace(
    func: None = None,
    *,
    show_args: bool | None = None,
    show_result: bool | None = None,
    show_timing: bool | None = None,
    show_exc: bool | int | None = None,
    exc_tb_depth: int | None = None,
) -> Callable[[F], F]: ...


def trace(
    func: F | None = None,
    *,
    show_args: bool | None = None,
    show_result: bool | None = None,
    show_timing: bool | None = None,
    show_exc: bool | int | None = None,
    exc_tb_depth: int | None = None,
) -> F | Callable[[F], F]:
    def decorator(real_func: F) -> F:
        sig = inspect.signature(real_func)

        def _format_named_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            try:
                bound = sig.bind_partial(*args, **kwargs)
                bound.apply_defaults()
                parts: list[str] = []
                for name, value in bound.arguments.items():
                    r = repr(value)
                    if len(r) > 200:
                        r = r[:197] + "..."
                    parts.append(f"{name}={r}")
                return ", ".join(parts)
            except Exception:
                return "<unrepr>"

        @wraps(real_func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            fresh = not is_tracing_active()
            if fresh:
                start_tracing()

            cfg = get_config()
            collect_args = show_args if show_args is not None else cfg.show_args
            collect_result = show_result if show_result is not None else cfg.show_result
            collect_timing = show_timing if show_timing is not None else cfg.show_timing

            if isinstance(show_exc, int):
                collect_exc = True
                depth = show_exc
            elif isinstance(show_exc, bool):
                collect_exc = show_exc
                depth = cfg.exc_depth()
            elif exc_tb_depth is not None:
                collect_exc = True
                depth = int(exc_tb_depth)
            else:
                collect_exc = cfg.exc_enabled()
                depth = cfg.exc_depth()

            args_repr = _format_named_args(args, kwargs) if collect_args else None

            sess = getattr(sys.monitoring, "_flowtrace_session", None)
            if sess and getattr(sess, "active", False):
                sess.push_meta_for_func(
                    wrapper.__code__.co_name,  # type: ignore[attr-defined]
                    args_repr=args_repr,
                    collect_args=collect_args,
                    collect_result=collect_result,
                    collect_timing=collect_timing,
                    collect_exc_tb=collect_exc,
                    exc_tb_depth=depth,
                )

            try:
                result = real_func(*args, **kwargs)
                return result
            finally:
                if fresh:
                    stop_tracing()
                    print_tree(get_trace_data())

        wrapper.__flowtrace_real_name__ = real_func.__name__  # type: ignore[attr-defined]

        return cast("F", wrapper)

    # если декоратор вызван без скобок
    return decorator(func) if func is not None else decorator
