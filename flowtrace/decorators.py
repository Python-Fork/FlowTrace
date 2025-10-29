from __future__ import annotations

import inspect
import sys
from functools import wraps
from typing import Callable, Any, TypeVar, cast

from .config import get_config
from .core import start_tracing, stop_tracing, get_trace_data, is_tracing_active
from .formatters import print_tree

F = TypeVar("F", bound=Callable[..., Any])


def trace(func: F | None = None, *, show_args: bool | None = None, show_result: bool | None = None,
          show_timing: bool | None = None) -> F:
    def decorator(real_func: F) -> F:
        sig = inspect.signature(real_func)

        def _format_named_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
            # Считаем аргументы ТОЛЬКО если это действительно нужно
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
            collect_args = show_args if show_args is not None else cfg["show_args"]
            collect_result = show_result if show_result is not None else cfg["show_result"]
            collect_timing = show_timing if show_timing is not None else cfg["show_timing"]

            args_repr = _format_named_args(args, kwargs) if collect_args else None

            sess = getattr(sys.monitoring, "_flowtrace_session", None)
            if sess and getattr(sess, "active", False):
                sess.push_meta_for_func(
                    real_func.__name__,
                    args_repr=args_repr,
                    collect_args=collect_args,
                    collect_result=collect_result,
                    collect_timing=collect_timing,
                )

            try:
                result = real_func(*args, **kwargs)
                return result
            finally:
                if fresh:
                    stop_tracing()
                    print_tree(get_trace_data())
        return cast(F, wrapper)

    return decorator(func) if func is not None else cast(F, decorator)