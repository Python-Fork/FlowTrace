import flowtrace

# Глобально: аргументы выключены, результат+время включены
flowtrace.config(show_args=False, show_result=True, show_timing=True)

@flowtrace.trace
def a(x):
    return b(x) + 1

@flowtrace.trace(show_args=True)
def b(y):
    return c(y * 2)

@flowtrace.trace()
def c(z):
    return z + 10

if __name__ == "__main__":
    a(10)