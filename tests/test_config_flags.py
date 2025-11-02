import flowtrace


def test_config_affects_tracing_flags():
    flowtrace.config(show_args=False, show_result=True, show_timing=True)

    @flowtrace.trace
    def foo(x):
        return x + 1

    flowtrace.start_tracing()
    foo(42)
    events = flowtrace.stop_tracing()

    call = next(e for e in events if e.kind == "call")
    ret = next(e for e in events if e.kind == "return")

    assert call.args_repr is None  # args скрыты
    assert ret.result_repr is not None  # результат отображён
    assert ret.duration is not None  # время собирается
