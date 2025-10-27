from flowtrace import start_tracing, stop_tracing
from flowtrace.formatters import print_tree, print_summary, print_events_debug

def add(a, b):
    return a + b

def mul(a, b):
    return a * b

def compute(x):
    y = add(x, 2)
    z = mul(y, 3)
    return z

def nested_example(n):
    if n <= 1:
        return compute(n)
    return compute(nested_example(n - 1))

def main():
    start_tracing()
    result = nested_example(3)
    events = stop_tracing()

    print("[flowtrace] дерево вызовов:")
    print_tree(events)
    print(f"\nРезультат: {result}")

if __name__ == "__main__":
    main()