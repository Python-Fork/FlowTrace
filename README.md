> 🌐 This document is available in other languages: [Русская версия](README.ru.md)
# 🌀 FlowTrace — Visual Execution Analyzer for Python (3.12+)

>FlowTrace is a system-level tracer for Python 3.12+.
>Unlike traditional profilers, FlowTrace doesn’t measure performance — it reconstructs the program’s execution in real time. It tracks function calls, exceptions, asynchronous transitions, and call structures without modifying the code or introducing significant overhead.
>FlowTrace connects directly to the interpreter’s Monitoring API, analyzing execution events at the bytecode level. This allows for system-wide observation of Python applications — from individual functions to the entire process — without interfering with standard I/O streams, using monkey-patching, or producing redundant output.
---

## 🎯 Project Goals

- Help Python developers build intuition about *how the interpreter executes code*.
- Provide a lightweight, fast, asyncio-compatible tracing tool.
- Enable learning through introspection — **see**, **understand**, and **explain**.
- Keep the output simple, textual, and readable — no web interfaces or IDE plugins.

---

## 📘 MVP (v0.1)

- [x] Implement basic tracing via `sys.monitoring` (PEP 669).
- [x] Display hierarchical call trees in the CLI (`print_tree`).
- [x] Show function arguments and return values.
- [ ] Support `async` functions and coroutines.
- [ ] Add JSON export for trace data.
- [x] Provide minimal documentation and examples (`docs/`, `README`).
- [x] Establish project philosophy and guiding principles (`docs/philosophy.md`).

---

## 💡 Example

FlowTrace turns your program’s execution into a clear, readable call tree:

```python
from flowtrace import trace

@trace
def fib(n):
    return n if n <= 1 else fib(n-1) + fib(n-2)

fib(3)
```

Output:
```
fib(3)
 ├─ fib(2)
 │  ├─ fib(1)
 │  └─ fib(0)
 └─ fib(1)
fib(3) → 2
```

This visualization shows exactly how your code executes —
each call, each return, and the structure connecting them.

## ⚙️ Core Principles

- Modern foundation: built on the [PEP 669](https://peps.python.org/pep-0669/) 
  Monitoring API (Python 3.12+),
  replacing the old sys.settrace mechanism for faster, asyncio-safe performance.

- Simplicity first: just one decorator — @trace.

- CLI-based output: all visualization happens in the terminal or via JSON export.
  The focus is on clarity and accessibility.

- Async compatibility: supports coroutines and async tasks transparently.

- Structured API: get structured trace data for further analysis:

```python
data = flowtrace.get_trace_data()
```

## 🧰 Planned Features

- Cross-platform color output.

- output parameter for writing execution data to a file.

- Customizable formatters (minimal / verbose styles).

- Include/exclude filters by module or function.

- Run comparison for analyzing behavioral differences.

## 🤝 Contributing

FlowTrace is open to contributors — its goal is not only to provide a tool,
but to serve as a learning ground for exploring the internals of Python 3.12+.

## 🧠 FlowTrace is not a profiler.
It’s an X-ray of Python code — a way to see your program’s logic in motion.
