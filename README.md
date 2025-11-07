> 🌐 Also available in: [Русская версия](README.ru.md)
<p align="center">
  <img src="https://raw.githubusercontent.com/Python-Fork/FlowTrace/main/logo.png" width="400" alt="FlowTrace logo">
</p>

# 🌀 FlowTrace — Visual Execution Tracing for Python 3.12+
[![PyPI version](https://img.shields.io/pypi/v/flowtrace.svg)](https://pypi.org/project/flowtrace/)
[![Python](https://img.shields.io/badge/python-3.12|3.13|3.14-blue.svg)](#)

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

@trace(show_timing=True)
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
## 4) Context manager

FlowTrace provides a context manager for scoped tracing inside specific code blocks.  
This approach is especially convenient for short-lived runs, tests, or async tasks.

```python
from flowtrace.core import active_tracing
from flowtrace import print_tree

def run_demo():
    ...

with active_tracing():
    run_demo()

print_tree()
```
Each ```with active_tracing()```: block creates its own isolated tracing session,
so concurrent async tasks or nested runs don’t interfere with each other.
---
## Global configuration
```python
import flowtrace
import flowtrace
flowtrace.config(
    show_args=True,
    show_result=True,
    show_timing=True,
    show_exc=False,
    inline_return=False,
)
```
Controls which information is collected globally.
All flags default to True.

| Flag            | Type       | Description                                             |
| --------------- |------------| ------------------------------------------------------- |
| `show_args`     | bool       | capture and display call arguments                      |
| `show_result`   | bool       | capture and display return values                       |
| `show_timing`   | bool       | measure and display function duration                   |
| `show_exc`      | bool / int | enable exception trace capture; int sets traceback depth|
| `inline_return` | bool       | compact one-line output for leaf calls                  |


## Function-level overrides
```python
@flowtrace.trace(show_args=True)
def foo(x): ...
```

Local flags temporarily override global ones for this function only;
child calls inherit the global configuration.

Example
```python
import flowtrace

flowtrace.config(show_args=False, show_result=True, show_timing=True)

@flowtrace.trace
def a(x): return b(x) + 1

@flowtrace.trace(show_args=True)
def b(y): return y * 2

a(10)
```
Output:
```
→ a() [0.000032s] → 21
  → b(y=10) [0.000010s] → 20
  ← b(y=10)
← a()
```
---
## Why FlowTrace?

- **Not a profiler**: profilers answer “how long”. FlowTrace answers “what, in which order, and why”.

- **Direct line to the VM**: listens to bytecode-level events via sys.monitoring (PEP 669).

- **No code intrusion**: no sys.settrace, no monkey-patching, no stdout noise.

---

## API (current)
```python
from flowtrace import trace, config, start_tracing, stop_tracing, get_trace_data, print_tree
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
- `get_config() -> Config` — access the current typed configuration object.
    
### Event model (```CallEvent```):
``` python
id: int
kind: str
func_name: str
parent_id: int | None
args_repr: str | None
result_repr: str | None
duration: float | None
collect_args: bool
collect_result: bool
collect_timing: bool
```
---
## Design choices (snapshot)

- **Only ```PY_START``` / ```PY_RETURN```**: we do not listen to ```CALL``` to keep the core lean.
Argument strings are provided by the decorator right before the call starts.

- **Exception lifecycle tracing**: FlowTrace now listens to exception-related
  signals (`RAISE`, `RERAISE`, `EXCEPTION_HANDLED`, `PY_UNWIND`).
  Each function frame produces at most one exception event, labeled as
  `[caught]` (handled locally) or `[propagated]` (escaped outward).

- **Timing is opt-in**: ```perf_counter()``` is used only when ```measure_time=True```.
Starting/stopping a session alone does not add timing overhead.

- **Filter user code**: internal modules and site-packages are excluded from the default output.
---
## Design notes

- Zero-overhead when disabled: arguments, results, and timing are gathered only if their flags are True.

- Named argument binding: readable form like a=5, b=2 via inspect.signature, cached at decoration time.

- No cascades: per-function flags affect only that decorated function.
---
## Roadmap

- **Async/coroutine transitions.**

- **JSON export for post-processing.**

- **Include/exclude filters & colorized output.**

- **Minimal CLI helpers.**

---
## Contributing

We welcome small, surgical PRs. The codebase is intentionally compact to be an approachable learning tool for exploring Python 3.12+ internals.

## Development

```bash
python -m pip install -U pip
pip install -e .  # editable install
pip install -U ruff mypy pytest pre-commit
pre-commit install
pytest -q
ruff format .
ruff check .
mypy flowtrace