from flowtrace import trace, start_tracing, stop_tracing
from flowtrace.formatters import print_tree


def fib(n: int) -> int:
    return n if n < 2 else fib(n-1) + fib(n-2)

start_tracing()
fib(3)
events = stop_tracing()
print_tree(events)