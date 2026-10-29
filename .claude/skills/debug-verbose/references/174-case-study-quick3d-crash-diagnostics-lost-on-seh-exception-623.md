## Case study: Qt Quick 3D crash diagnostics lost on SEH exception (#623)

**Symptom.** When Qt Quick 3D subprocesses or integration tests crashed with Windows
SEH exception `0xC000041D` during teardown, the crash traceback was lost and the
selftest error output was empty or uninformative.
**Wrong assumption.** The `runlog.watchdog()` context manager was assumed to always capture
crashes via `faulthandler`.
**Evidence.** `runlog.watchdog()` armed only `dump_traceback_later`: that
timeout dump does not install fatal-exception handlers. The isolated `_RUN`
selftest child likewise had no early handler, and failure messages omitted
the durable log. The original watchdog did not call `faulthandler.disable()`;
the missing handler, rather than an unconditional disable, was the defect.
**Fix.** In `watchdog()`, record `previously_enabled = faulthandler.is_enabled()`, only enable
if not previously enabled, and in `finally` do not disable if `faulthandler` was already
enabled or targeted to an external file. In `test_quick3d_selftest.py`, enable early `faulthandler`
and print selftest log tails on assertion failures. Pinned by `tests/integration/test_quick3d_selftest.py`.
**Lesson.** Context managers that manage global process-level hooks (like `faulthandler` or
signal handlers) must restore previous state rather than unconditionally disabling them.

**Review regression (PR #645).** Injecting a refused crash-log open printed
`[WATCHDOG] observed=UnboundLocalError ...; armed=1`; the original exception
was `RuntimeError("original setup failure")`. Handler state had been assigned
after the operation that failed, so cleanup raised before releasing the
supervisor. Capture cleanup state before entering the try. Regression tests
refuse both crash-log acquisition and the armed announcement, assert the
original exception, an empty armed list, supervisor release and a working next
watchdog.

**Artifact observation.** The PR #645 production board completed every render
and truth gate under Python 3.12, then exited on a native access violation
during teardown. The log retained `Windows fatal exception: access violation`
and the current-thread header, with no Python frame. The same final board
under locked Python 3.11.9 exited 0. This is diagnostic evidence, not a claimed
fix for the intermittent native teardown failure.
