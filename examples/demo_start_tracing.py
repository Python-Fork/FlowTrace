from flowtrace import start_tracing, stop_tracing
from flowtrace.formatters import print_tree

def alpha(x): return beta(x + 1)
def beta(y): return y * 2

start_tracing()
alpha(5)
events = stop_tracing()
print_tree(events)