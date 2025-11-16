# **[0.4.0] – 2025-11-01**
### Added
- **Exception-return events** (`↯`) — functions that terminate via exception are now distinctly shown.
- **Compact traceback slices** with `@trace(show_exc=True)` or global `Config(show_exc=True)`.
- `exc_tb_depth` option to control traceback depth per call.
- Extended `CallEvent` with `via_exception` and `exc_tb` fields.
- Updated tree formatter to display traceback context below exception lines.

### Improved
- Exception handling flow now tracks raised, handled, and propagated states precisely.
- Internal filtering and caching (`_is_user_code`, `_is_user_path`) simplified and optimized.
- Cleaner output and consistent arrow semantics across return types.

### Compatibility
No breaking API changes — existing traces remain valid.
Old output formats render identically unless `show_exc=True` is used.

---

# **[0.4.1] – 2025-11-02**

### Added

* Full static analysis integration: pre-commit hooks with Ruff (lint + format) and Mypy.
* GitHub Actions workflows for CI (linting, type checking, testing, and PyPI release).
* Project-level Ruff configuration using the modern `[tool.ruff.lint]` section.
* Inclusion of `flowtrace/py.typed` for PEP 561 type distribution.

### Changed

* Refactored core duration logic to ensure safe arithmetic without `Optional` types.
* Replaced direct `sys.monitoring._flowtrace_session` assignments with `setattr` for type safety.
* Unified test exception handling using `contextlib.suppress`.
* Updated docstrings, examples, and README formatting for clarity and consistency.

### Fixed

* Resolved all Ruff and Mypy warnings, including `SIM108` and `UP047`.
* Corrected minor inconsistencies in stack cleanup and event tracking.
* Verified all tests and CI checks pass across Python 3.12–3.14.

### Quality

* Repository fully passes Ruff, Mypy, and Pytest with 100 % success.
* Clean `pre-commit run --all-files` result on main branch.

---

# **[0.4.2] – 2025-11-09**

### **Added**

* **Task-local tracing isolation**
  Active `TraceSession` is now stored in a `ContextVar`, enabling safe and independent tracing across threads and async tasks.

* **Context manager API**
  Introduced `active_tracing()` for scoped tracing via `with` blocks — ideal for tests and nested runs.

* **Typed configuration system**
  `Config` now includes full type annotations, field validation, and aliases (`show_exc`, `exc_tb_depth`, `inline_return`).

* **Formatter flag `inline_return`**
  Enables switching between compact single-line and detailed multi-line display for simple return cases.

* **Documentation updates**
  README and README.ru expanded with a new section on context managers and refreshed configuration examples.

### **Changed**

* **Unified exception depth control**
  `show_exc` now manages traceback depth uniformly (supports both `bool` and `int` forms).

* **Consistent session management**
  All core APIs (`start_tracing()`, `stop_tracing()`, `is_tracing_active()`) now rely on `ContextVar` instead of global `sys.monitoring` state.

* **Refined configuration updates**
  `config()` now validates and replaces only known fields, preserving strict typing guarantees.

### **Fixed**

* **Always-capture traceback**
  Exception traceback slices (`exc_tb`) are always collected by default, fixing CI failures and improving reliability.

* **CI stability**
  All Pytest, Mypy, and Ruff checks pass consistently across Python 3.12–3.14 in GitHub Actions.

---

# **[0.5.0] – 2025-11-17**

### **Added**

* **Full modular architecture**
  FlowTrace is now split into well-defined subsystems:

  * `flowtrace.events` — unified event model (`CallEvent`, `ExceptionEvent`, `AsyncTransitionEvent`, `ExecutionContext`, `TraceEvent`).
  * `flowtrace.monitoring` — clean integration layer for `sys.monitoring` (registration, dispatching, safe handlers).
  * `flowtrace.session` — central logic for call stacks, timing, exceptions, and async event processing.
  * `flowtrace.asyncio_support` — task-factory integration, lazy async-IDs, Task → parent-task relations.
  * `flowtrace.formatters.async_tree` — async tree visualizer with `↯ await`, `⟳ resume`, and `yield → …` markers.
  * `flowtrace.exporters.chrome_trace` — initial skeleton for Chrome Trace event export.
* **TraceEvent union type** — all event kinds (sync, async, exception) now share a unified internal representation.
* **AsyncTransitionEvent** — dedicated event class for async lifecycle transitions (`resume`, `yield`, synthetic `await`).
* **ExecutionContext** embedded into all events (thread ID, task ID, parent task ID).
* **Public API compatibility** via re-export of `CallEvent` from `flowtrace.core`.

### **Changed**

* `core.py` refactored into a thin façade: only public APIs remain (`start_tracing`, `stop_tracing`, `active_tracing`, `get_trace_data`).
* All call-stack, exception, and timing logic moved to `session.py`.
* `@trace` decorator now integrates cleanly with ContextVar-based sessions and async task contexts.
* All formatters (`print_tree`, `print_summary`, `print_events_debug`) updated for the new `TraceEvent` union model.
* Internal code-filtering logic (`_is_user_code`, `_is_user_path`) moved into `monitoring.py`.
* Removed all direct uses of`` `sys.monitoring._flowtrace_session` outside the public API layer.
* Traceback handling now uses `ExceptionEvent` instead of overloading `CallEvent`.

### **Quality**

* Repository passes **Ruff, Mypy, and Pytest with 100% success**.
* Architecture is now ready for advanced async visualization.
* The internal structure is significantly cleaner, easier to maintain, and still fully backward-compatible with previous public APIs.

---``
