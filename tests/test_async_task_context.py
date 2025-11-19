import asyncio

import pytest

from flowtrace import active_tracing, get_trace_data


async def child():
    return 11


async def parent():
    t = asyncio.create_task(child())
    res = await t
    return res


@pytest.mark.asyncio
async def test_task_context():
    with active_tracing():
        await parent()

    events = get_trace_data()

    # Все async-события должны иметь task_id
    for ev in events:
        if ev.context.task_id is not None:
            # task_id должен быть int
            assert isinstance(ev.context.task_id, int)

    # Родительская таска создаёт дочернюю
    ids = {ev.context.task_id for ev in events if ev.context.task_id is not None}
    assert len(ids) >= 2
