## Case study: a real Preferences-to-picker integration test appeared to hang after the first successful workflow (Issue #342, fixed 2026-08-30)

**Symptom.** The new satellite workflow test printed `imported key='preference-key'`, then reported `FAILED` at the second Preferences save and stopped producing pytest output while Qt teardown was pending.

**Wrong theories.** The first suspects were a leaked WebEngine thread, the existing Agent API server, and the known modal-dialog teardown hazard. None explained why the failure occurred exactly after the import path had completed.

**Key evidence.** Flushed milestone prints narrowed the boundary to `[SAT-DBG] clearing Preferences`; a traceback wrapper then showed `AttributeError: '_PasswordLineEdit' object has no attribute 'clear'` at the test's `self._google_maps_key.clear()` call.

**Root cause.** The test treated the application's password-field wrapper as if it were the wrapped `QLineEdit`; the assertion failure happened before the test could print its post-save state, making the surrounding Qt teardown look like the cause.

**Fix.** Replace the wrapper call with its supported `setText("")` API, remove all temporary instrumentation, and keep the real Preferences dialog in the integration path while stubbing only the network-bound picker boundary.

**Lesson.** In a Qt integration test, print flushed milestones around each boundary before theorising about teardown; when a custom widget wrapper is involved, inspect its public API instead of assuming it forwards the underlying control's methods. A test that reaches the real UI save path is only useful if its own harness failure is distinguishable from application lifecycle noise.

