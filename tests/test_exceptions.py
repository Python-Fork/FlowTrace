import pytest

import flowtrace
from flowtrace.core import get_trace_data


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
