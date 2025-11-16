from __future__ import annotations

import sys
from collections.abc import Callable
from contextlib import contextmanager

try:
    import asyncio
except Exception:
    asyncio = None  # type: ignore[assignment]

from flowtrace.config import get_config
from flowtrace.events import CallEvent, TraceEvent
from flowtrace.monitoring import reserve_tool_id, start_monitoring, stop_monitoring
from flowtrace.session import CURRENT_SESSION as _CURRENT_SESSION
from flowtrace.session import TraceSession

Cb = Callable[..., None]

_last_data: list[TraceEvent] | None = None
TOOL_ID = reserve_tool_id()


def start_tracing(
    default_show_args: bool | None = None,
    default_show_result: bool | None = None,
    default_show_timing: bool | None = None,
    default_show_exc: bool | None = None,
) -> None:
    cfg = get_config()

    # 1. Создаём новую сессию
    sess = TraceSession(
        default_collect_args=(cfg.show_args if default_show_args is None else default_show_args),
        default_collect_result=(
            cfg.show_result if default_show_result is None else default_show_result
        ),
        default_collect_timing=(
            cfg.show_timing if default_show_timing is None else default_show_timing
        ),
        default_collect_exc_tb=True,
        default_exc_tb_depth=cfg.exc_depth() or 2,
    )

    # 2. Регистрируем её в contextvar
    _CURRENT_SESSION.set(sess)

    # 3. Запускаем сессию: active + async-hooks
    sess.start()

    # 4. Включаем мониторинг (после создания сессии!)
    start_monitoring(TOOL_ID)

    # 5. Запоминаем сессию внутри sys.monitoring (для удобства декораторов)
    sys.monitoring._flowtrace_session = sess  # type: ignore[attr-defined]


def is_tracing_active() -> bool:
    sess = _CURRENT_SESSION.get()
    return bool(sess and sess.active)


def stop_tracing() -> list[TraceEvent]:
    global _last_data
    sess = _CURRENT_SESSION.get()
    if not sess:
        return []

    stop_monitoring(TOOL_ID)

    data = sess.stop()  # деактивирует сессию и вырубит async_hooks
    _last_data = data
    sys.monitoring._flowtrace_session = None  # type: ignore[attr-defined]
    return data


def get_trace_data() -> list[TraceEvent]:
    return list(_last_data) if _last_data else []


@contextmanager
def active_tracing(**kwargs):
    """Контекстный менеджер для безопасной трассировки."""
    start_tracing(**kwargs)
    try:
        yield
    finally:
        stop_tracing()


__all__ = [
    "CallEvent",
    "active_tracing",
    "get_trace_data",
    "start_tracing",
    "stop_tracing",
]
