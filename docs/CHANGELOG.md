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
