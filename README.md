> 🌐 This document is available in other languages: [Русская версия](README.ru.md)
# 🌀 FlowTrace — Visual Execution Analyzer for Python (3.12+)

> **FlowTrace** is an educational library for visualizing and understanding Python code execution.  
> It shows *how your code actually runs* — which functions call which, with what arguments, what they return, and how long it all takes.

---

## 🎯 Project Goals

- Help Python developers build intuition about *how the interpreter executes code*.
- Provide a lightweight, fast, asyncio-compatible tracing tool.
- Enable learning through introspection — **see**, **understand**, and **explain**.
- Keep the output simple, textual, and readable — no web interfaces or IDE plugins.

---

## 📘 MVP (v0.1)

- [ ] Implement basic execution tracing via `sys.monitoring` (PEP 669).
- [ ] Support both synchronous and asynchronous function calls.
- [ ] Display call trees directly in the CLI.
- [ ] Save structured execution data in JSON.
- [ ] Include minimal documentation and usage examples.

---

## 💡 Concept

FlowTrace turns your program’s execution flow into a human-readable **call tree**.

```python
from flowtrace import trace

@trace
def fib(n):
    return n if n < 2 else fib(n-1) + fib(n-2)

fib(4)
```

Output:
```
fib(4)
 ├─ fib(3)
 │  ├─ fib(2)
 │  │  ├─ fib(1)
 │  │  └─ fib(0)
 │  └─ fib(1)
 └─ fib(2)
fib(4) → 3
```

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
