## Case study: Qt Quick 3D crash diagnostics lost on SEH exception (#623)

**Symptom.** When Qt Quick 3D subprocesses or integration tests crashed with Windows
SEH exception `0xC000041D` during teardown, the crash traceback was lost and the
selftest error output was empty or uninformative.
**Wrong assumption.** The `runlog.watchdog()` context manager was assumed to always capture
crashes via `faulthandler`.
**Evidence.** `runlog.watchdog()` unconditionally called `faulthandler.disable()` in its
`finally` block upon normal exit, clobbering process-wide handlers armed by test runners
or parent processes. Furthermore, `tests/integration/test_quick3d_selftest.py` did not arm
`faulthandler` early in `_RUN` mode, and assertion failure messages did not dump the log tail.
**Fix.** In `watchdog()`, record `previously_enabled = faulthandler.is_enabled()`, only enable
if not previously enabled, and in `finally` do not disable if `faulthandler` was already
enabled or targeted to an external file. In `test_quick3d_selftest.py`, enable early `faulthandler`
and print selftest log tails on assertion failures. Pinned by `tests/integration/test_quick3d_selftest.py`.
**Lesson.** Context managers that manage global process-level hooks (like `faulthandler` or
signal handlers) must restore previous state rather than unconditionally disabling them.
