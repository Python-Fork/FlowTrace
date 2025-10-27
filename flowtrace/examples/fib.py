from flowtrace import trace

@trace
def fib(n: int) -> int:
    return n if n < 2 else fib(n-1) + fib(n-2)

fib(3)