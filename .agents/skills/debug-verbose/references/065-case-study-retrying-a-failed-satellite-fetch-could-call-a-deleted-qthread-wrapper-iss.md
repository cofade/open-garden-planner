## Case study: retrying a failed satellite fetch could call a deleted QThread wrapper (Issue #342, fixed 2026-08-30)

**Symptom.** After a satellite fetch failed or was cancelled, a later Cancel click could raise `RuntimeError: wrapped C/C++ object of type _FetchWorker has been deleted`.

**Wrong theories.** The HTTP worker was suspected of still running, and the dialog's `closeEvent()` detachment looked like the likely source of the stale reference.

**Key evidence.** `_on_accept()` connected `finished → worker.deleteLater()` but never cleared `self._worker`; `_on_cancel()` then called `self._worker.isRunning()` after Qt had destroyed the C++ object.

**Root cause.** Python retained a wrapper whose underlying QThread had already been deleted, so the next lifecycle action dereferenced invalid Qt state.

**Fix.** Connect each worker's terminal signal to an identity-checked cleanup slot that clears `_worker`, guard stale wrappers in Cancel/close, and add a real-thread regression test that waits for failure before issuing a second Cancel.

**Lesson.** In Qt worker code, `deleteLater()` is not reference cleanup. Track terminal ownership explicitly, test the action that follows completion, and use the worker identity so a late signal from an older request cannot clear a replacement.

