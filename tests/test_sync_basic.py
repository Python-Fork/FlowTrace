from flowtrace import active_tracing, get_trace_data


def a():
    return b()


def b():
    return 42


def test_sync_calls():
    with active_tracing():
        result = a()

    assert result == 42

    events = get_trace_data()

    call_names = [e.func_name for e in events if e.kind == "call"]
    assert call_names == ["a", "b"]

    for ev in events:
        assert ev.context is not None
        assert isinstance(ev.context.thread_id, int)
        assert ev.context.task_id is None
