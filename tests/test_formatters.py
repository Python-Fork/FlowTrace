import io
from contextlib import redirect_stdout

import flowtrace
from flowtrace.formatters import print_events_debug, print_summary, print_tree


@flowtrace.trace
def calc(x, y):
    return x + y


def test_all_formatters_print_something():
    flowtrace.start_tracing()
    calc(1, 2)
    events = flowtrace.stop_tracing()

    buf = io.StringIO()
    with redirect_stdout(buf):
        print_tree(events)
        print_summary(events)
        print_events_debug(events)

    out = buf.getvalue()
    assert "calc" in out
    assert "return" in out or "событий" in out
