from __future__ import annotations

import asyncio
import threading
from contextlib import suppress

# глобальные счётчики для async_id
_async_counter = 1
_lock = threading.Lock()

# таблицы для реестра корутин и их иерархий
TASK_TO_ASYNC_ID: dict[asyncio.Task, int] = {}
ASYNC_PARENT: dict[int, int | None] = {}


def _reserve_async_id(parent: int | None = None) -> int:
    global _async_counter
    with _lock:
        aid = _async_counter
        _async_counter += 1
    ASYNC_PARENT[aid] = parent
    return aid


def _task_factory(loop, coro):
    """
    Перехват создания задач.
    Назначает каждой asyncio.Task свой async_id,
    а также регистрирует родителя, если есть текущая задача.
    """
    parent_task = asyncio.current_task(loop=loop)
    parent_id = TASK_TO_ASYNC_ID.get(parent_task) if parent_task else None

    task = asyncio.Task(coro, loop=loop)

    async_id = _reserve_async_id(parent_id)
    TASK_TO_ASYNC_ID[task] = async_id

    return task


def install_task_factory(loop: asyncio.AbstractEventLoop) -> None:
    """
    Включает наше наблюдение за созданием задач.
    """
    with suppress(Exception):
        loop.set_task_factory(_task_factory)


def uninstall_task_factory(loop: asyncio.AbstractEventLoop) -> None:
    """
    Выключает наблюдение.
    """
    with suppress(Exception):
        loop.set_task_factory(None)


def get_async_id(task: asyncio.Task | None = None) -> int | None:
    """
    Ленивая выдача async_id:
    - если задача известна → отдаём async_id
    - если неизвестна → создаём новый async_id (но без родителя)
      (эта ветка нужна для случаев, когда set_task_factory недоступен)
    """
    if task is None:
        task = asyncio.current_task()

    if task is None:
        return None

    aid = TASK_TO_ASYNC_ID.get(task)
    if aid is not None:
        return aid

    # fallback — lazy assign
    new_id = _reserve_async_id(parent=None)
    TASK_TO_ASYNC_ID[task] = new_id
    return new_id
