## [0.4.0] – 2025-11-01
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

## [0.4.1] – 2025-11-02

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
