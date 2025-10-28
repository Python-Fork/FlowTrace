from __future__ import annotations

from functools import wraps
from typing import Callable, Any, TypeVar, cast

from .core import start_tracing, stop_tracing, get_trace_data, is_tracing_active, _current
from .formatters import print_tree

F = TypeVar("F", bound=Callable[..., Any])

def trace(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        fresh = not is_tracing_active()
        if fresh:
            start_tracing()

        sess = _current
        if sess and sess.active:
            sess.on_call(func.__name__, args, kwargs)

        try:
            result = func(*args, **kwargs)
            if sess and sess.active:
                sess.on_return(func.__name__, result)
            return result
        finally:
            if fresh:
                stop_tracing()
                print_tree(get_trace_data())

    return cast(F, wrapper)