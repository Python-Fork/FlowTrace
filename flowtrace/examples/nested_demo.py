from flowtrace import trace, stop_tracing, start_tracing
from flowtrace.formatters import print_tree

def outer(a, b):
    def inner(x, y):
        return x * y

    z = inner(a + 1, b + 2)
    return z + a + b

start_tracing()
outer(3, 4)
g = stop_tracing()
print_tree(g)
