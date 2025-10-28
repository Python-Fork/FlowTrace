from flowtrace import trace

@trace
def outer(a, b):
    def inner(x, y):
        return x * y

    z = inner(a + 1, b + 2)
    return z + a + b

outer(3, 4)
