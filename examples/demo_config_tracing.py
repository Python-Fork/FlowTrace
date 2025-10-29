import flowtrace

flowtrace.config(show_args=False, show_result=True, show_timing=True)

@flowtrace.trace
def a(x): return b(x) + 1

@flowtrace.trace(show_args=True)
def b(y): return y * 2

a(10)
