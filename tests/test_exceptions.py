from contextlib import suppress

import pytest

import flowtrace
from flowtrace import active_tracing, get_trace_data
from flowtrace.events import ExceptionEvent


@flowtrace.trace(show_exc=True)
def fail_once():
    raise ValueError("boom")


def test_trace_exception_and_tb():
    with pytest.raises(ValueError):
        fail_once()

    events = get_trace_data()
    exc = next(e for e in events if e.kind == "exception" and e.func_name == "fail_once")
    ret = next(e for e in events if e.kind == "return" and e.func_name == "fail_once")

    assert exc.exc_type == "ValueError"
    assert exc.exc_tb and "fail_once" in exc.exc_tb
    assert ret.via_exception is True


def fail():
    raise ValueError("boom")


def wrapper():
    with suppress(Exception):
        fail()


def test_exception_event():
    with active_tracing():
        wrapper()

    events = get_trace_data()

    exc_events = [e for e in events if isinstance(e, ExceptionEvent)]
    assert len(exc_events) == 2

    raised = exc_events[0]
    handled = exc_events[1]

    assert raised.func_name == "fail"
    assert handled.func_name == "wrapper"
    assert raised.caught is False
    assert handled.caught is True
