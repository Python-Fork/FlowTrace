from __future__ import annotations

from functools import wraps
from typing import Callable, Any, TypeVar, cast

from .core import start_tracing, stop_tracing, get_trace_data, is_tracing_active
from .formatters import print_events_debug

F = TypeVar("F", bound=Callable[..., Any])

def trace(func: F) -> F:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        fresh = not is_tracing_active()
        if fresh:
            start_tracing()
        try:
            return func(*args, **kwargs)
        finally:
            if fresh:
                stop_tracing()
                print_events_debug(get_trace_data())

    return cast(F, wrapper)