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

---

🇬🇧 *Suggested phrasing:*
“Let’s add a proper changelog entry for the full 0.5.x minor patch series based on everything we did.”

---
# **[0.5.1] – 2025-11-19**

### **Added**

* **Unified ExecutionContext across all event types**
  Every `CallEvent`, `ExceptionEvent`, and `AsyncTransitionEvent` now carries a fully populated execution context:

  * `thread_id` — execution thread
  * `task_id` — current asyncio.Task identifier
  * `task_parent_id` — parent task (if any)
  * `task_name` — human-readable task label
    This establishes a consistent cross-sync/async foundation for all future visualizers and exporters.

* **ExceptionEvent adopted as the sole exception record type**
  `_append_exception()` now generates `ExceptionEvent` instances directly, removing the legacy `CallEvent(kind="exception")` mechanism.
  Propagation, handling, and unwind phases now update `ExceptionEvent.caught` as intended.

* **Async semantics layer (await / resume / yield)**
  FlowTrace now differentiates async transitions based on CPython’s `co_flags`:

  * `PY_YIELD` inside a coroutine (`CO_COROUTINE`) → synthetic **`await`**
  * `PY_RESUME` → **`resume`**
  * `PY_YIELD` inside an async generator (`CO_ASYNC_GENERATOR`) → **`yield`**
    No custom C hooks, no patching — purely compliant with `sys.monitoring`.

* **Task-aware monitoring**
  `ExecutionContext` is enriched with `task_id` / `parent_task_id` using the lazy async-ID system from `asyncio_support`.
  This preserves full compatibility while preparing for async-tree and Chrome Trace export.

* **Async transition events stabilized**
  `AsyncTransitionEvent` now carries full context, async IDs, parent async IDs, and ready-to-use details for future visualizers.

### **Changed**

* **session.py** re-aligned with new architecture
  Centralized context generation via `get_execution_context()`.
  All event creation flows now attach a fresh execution context.

* **Cleaner raw-event dispatch logic**
  Removed legacy assumptions about phantom `PY_AWAIT`.
  Pure interpretation of CPython events (`PY_START`, `PY_RETURN`, `PY_UNWIND`, `PY_RESUME`, `PY_YIELD`) governs all async semantics.

* **Exception lifecycle corrected**
  Raised, handled, and propagated states are now represented strictly via `ExceptionEvent`, aligning with CPython’s monitoring phases.

* **Removed remnants of early async-tree prototypes**
  No premature visualization logic remains in session or core layers.
  Only clean, inspected semantics prepared for 0.6 async-tree.

* **Improved clarity and internal consistency**
  `on_async_transition()` no longer relies on stale `self.context`; it always receives a fresh `ExecutionContext`.

### **Quality**

* Passes full suite: **Pytest, Mypy, Ruff — all green**
* Codebase ready for the next major feature: **async-tree rendering (0.6)**
* Internal semantics are now strictly aligned with CPython 3.12–3.14 `sys.monitoring`.

---
