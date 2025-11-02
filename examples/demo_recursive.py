from flowtrace import print_tree, start_tracing, stop_tracing


def fib(n):
    return n if n < 2 else fib(n - 1) + fib(n - 2)


start_tracing()
fib(3)
events = stop_tracing()
print_tree(events)
