import flowtrace
from flowtrace.core import get_trace_data


@flowtrace.trace
def mul(a, b):
    return a * b


@flowtrace.trace
def add_and_mul(x, y):
    return mul(x + y, x)


def test_basic_call_and_return():
    flowtrace.start_tracing()
    add_and_mul(2, 3)
    events = flowtrace.stop_tracing()

    calls = [e for e in events if e.kind == "call"]
    rets = [e for e in events if e.kind == "return"]

    assert any(e.func_name == "add_and_mul" for e in calls)
    assert any(e.func_name == "mul" for e in calls)
    assert len(rets) >= 2
    # дерево завершено корректно
    assert rets[-1].func_name == "add_and_mul"


@flowtrace.trace
def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)


def test_recursive_trace():
    flowtrace.start_tracing()
    fib(3)
    events = flowtrace.stop_tracing()

    fib_calls = [e for e in events if e.kind == "call" and e.func_name == "fib"]
    assert len(fib_calls) >= 3
    assert all(isinstance(e.id, int) for e in fib_calls)


def test_get_trace_data_after_stop():
    flowtrace.start_tracing()
    add_and_mul(1, 1)
    flowtrace.stop_tracing()
    data = get_trace_data()
    assert isinstance(data, list)
    assert all(hasattr(e, "kind") for e in data)
