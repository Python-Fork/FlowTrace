import asyncio

import pytest

from flowtrace import active_tracing, get_trace_data
from flowtrace.events import AsyncTransitionEvent


async def inner():
    await asyncio.sleep(0)
    return 99


async def outer():
    return await inner()


@pytest.mark.asyncio
async def test_await_resume_yield():
    with active_tracing():
        await outer()

    events = get_trace_data()

    transitions = [e for e in events if isinstance(e, AsyncTransitionEvent)]

    kinds = [e.kind for e in transitions]

    # Должны быть await и resume
    assert "await" in kinds
    assert "resume" in kinds

    # yield может появляться, если asyncio.sleep возвращает
    assert all(k in {"await", "resume", "yield"} for k in kinds)
