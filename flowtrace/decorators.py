from __future__ import annotations
import sys
from functools import wraps
from typing import Callable, Any, TypeVar, cast

from .core import start_tracing, stop_tracing, get_trace_data, is_tracing_active
from .formatters import print_tree

F = TypeVar("F", bound=Callable[..., Any])

def trace(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        fresh = not is_tracing_active()
        if fresh:
            start_tracing()

        sess = getattr(sys.monitoring, "_flowtrace_session", None)  # <—
        if sess and getattr(sess, "active", False):
            sess.push_args_for_code(func.__name__, args, kwargs)

        try:
            result = func(*args, **kwargs)
            return result
        finally:
            if fresh:
                stop_tracing()
                print_tree(get_trace_data())
    return cast(F, wrapper)