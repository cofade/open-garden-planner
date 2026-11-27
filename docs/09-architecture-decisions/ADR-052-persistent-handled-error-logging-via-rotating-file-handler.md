---
id: ADR-052
title: "Persistent Handled-Error Logging via Rotating File Handler"
status: "Accepted (October 2026, #405 / AUD-063 / TD-023)"
refs: ["#405"]
legacy_anchor: adr-052-persistent-handled-error-logging-via-rotating-file-handler-issue-405
---

# ADR-052: Persistent Handled-Error Logging via Rotating File Handler

**Status**: Accepted (October 2026, #405 / AUD-063 / TD-023)

**Context**: §8.7 previously stated "No silent failures: all errors logged and shown to user where appropriate." However, no `logging` configuration existed anywhere in the application. While uncaught exceptions were captured to `crash.log` via `sys.excepthook`, handled errors across 25 loggers (55 warning/error/exception call sites) fell to Python's default `lastResort` handler. In the windowed PyInstaller executable (`console=False`), `sys.stderr is None` (the #291 condition), causing all handled error records to be discarded without trace on disk.

**Decision**:
1. **Bootstrap root logger with a rotating file handler at startup.** New module `core/logging_config.py` provides `setup_logging()`, called early in `main.py::main()` after setting the application identity.
2. **Persistent storage in application data directory.** Handled logs are written to `app.log` located in the platform application data directory (`QStandardPaths.writableLocation(AppDataLocation)`, alongside `crash.log`). The handler rotates at 1 MB with 3 backup files (`app.log.1`, etc.) and UTF-8 encoding.
3. **Safe console attachment.** A `StreamHandler(sys.stderr)` at WARNING level is attached only when `sys.stderr is not None` (developer console runs). When `sys.stderr is None` (windowed frozen exe), no StreamHandler is attached, preventing dropped records or stream errors.
4. **Docs and docstring alignment.** §8.7 and docstrings (`ui/theme.py::apply_theme`) are aligned to describe that handled errors are persisted to `app.log`, while uncaught exceptions trigger `_install_excepthook`, `crash.log`, and the recovery dialog.

**Consequences**:
- Handled errors and warnings in production windowed exe builds are preserved for user troubleshooting.
- No impact on performance: file logging defaults to INFO+, avoiding verbose debug clutter.
- Idempotent and clean test reset via `reset_logging()`.
