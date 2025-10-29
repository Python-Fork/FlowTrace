> 🌐 Also available in: [Русская версия](README.ru.md)
# 🌀 FlowTrace — Visual Execution Tracing for Python 3.12+

>FlowTrace is a system-level tracer built on Python’s Monitoring API (PEP 669).
>It doesn’t “profile time by default”. Instead, it reconstructs what happened in your program — calls, returns,
>structure — with minimal overhead and zero monkey-patching.

> **Status**: experimental alpha. Python 3.12+ only.

---
## Installation
```
pip install flowtrace
```
---
## Quick Start
### 1) One-line decorator
```python
from flowtrace import trace

@trace
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

fib(3)
```

Output:

```
→ fib(3)
  → fib(2)
    → fib(1) → 1
    → fib(0) → 0
  ← fib(2) → 1
  → fib(1) → 1
← fib(3) → 2
```
---
## 2) Timing when you need it
```python
from flowtrace import trace

@trace(measure_time=True)
def compute(a, b):
    return a * b

compute(6, 7)
```

Output:

```
→ compute(6, 7) [0.000265s] → 42
```
---
## 3) Manual session
```python
from flowtrace import start_tracing, stop_tracing, print_tree

def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

start_tracing()
fib(3)
events = stop_tracing()
print_tree(events)
```

Output:
```
→ fib()
  → fib()
    → fib()  → 1
    → fib()  → 0
  ← fib()  → 1
  → fib()  → 1
← fib()  → 2
```
---
## Why FlowTrace?

- **Not a profiler**: profilers answer “how long”. FlowTrace answers “what, in which order, and why”.

- **Direct line to the VM**: listens to bytecode-level events via sys.monitoring (PEP 669).

- **No code intrusion**: no sys.settrace, no monkey-patching, no stdout noise.

---

## API (current)
```python
from flowtrace import trace, start_tracing, stop_tracing, get_trace_data, print_tree
```

-  ```@trace(measure_time: bool = True)```
Decorate a function to include its calls in the trace.
When ```measure_time=True```, durations for this function’s calls are recorded.

- ```start_tracing()``` / ```stop_tracing() -> list[CallEvent]```
Start/stop a process-wide tracing session. By default no timing is recorded here — only structure.

- ```get_trace_data() -> list[CallEvent]```
Access the last recorded events.

- ```print_tree(events)```
Pretty-print a hierarchical call tree.
    
### Event model (```CallEvent```):
``` python
id: int
kind: str           
func_name: str
parent_id: int | None
args_repr: str | None
result_repr: str | None
duration: float | None    
```
---
## Design choices (snapshot)

- **Only ```PY_START``` / ```PY_RETURN```**: we do not listen to ```CALL``` to keep the core lean.
Argument strings are provided by the decorator right before the call starts.

- **Timing is opt-in**: ```perf_counter()``` is used only when ```measure_time=True```.
Starting/stopping a session alone does not add timing overhead.

- **Filter user code**: internal modules and site-packages are excluded from the default output.
---
## Roadmap

- **Async/coroutine transitions.**

- **JSON export for post-processing.**

- **Include/exclude filters & colorized output.**

- **Minimal CLI helpers.**

---
## Contributing

We welcome small, surgical PRs. The codebase is intentionally compact to be an approachable learning tool for exploring Python 3.12+ internals.