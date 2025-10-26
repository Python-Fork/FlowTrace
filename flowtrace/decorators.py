from __future__ import annotations
from functools import wraps
from typing import Callable, Any, TypeVar, cast

from .core import start_tracing, stop_tracing, _current_session
from .formatters import print_events_debug

F = TypeVar("F", bound=Callable[..., Any])

def trace(func: F) -> F:
    """Точка входа. Включает трассировку нг время вызова функции,
    затем отправляет результат в консоль (MVP)."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start_tracing()
        try:
            return func(*args, **kwargs)
        finally:
            data = stop_tracing()
            print_events_debug(data)

    return cast(F, wrapper)