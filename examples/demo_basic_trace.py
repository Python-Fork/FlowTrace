from flowtrace import trace


@trace
def multiply(a, b):
    return a * b


@trace(show_timing=False)
def add_and_multiply(a, b):
    s = a + b
    return multiply(s, a)


add_and_multiply(2, 3)
