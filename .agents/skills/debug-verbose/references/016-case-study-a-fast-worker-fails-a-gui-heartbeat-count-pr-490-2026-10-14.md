## Case study: a fast worker fails a GUI heartbeat count (PR #490, 2026-10-14)

**Symptom.** One CI Test job failed `test_explicit_worker_keeps_gui_responsive`
with two timer ticks instead of three. The same head passed the other full Test
job, both Coverage jobs and the Windows full suite.

**Wrong theories.** No product-threading theory was adopted before tracing. A
fixed tick count over an uncontrolled computation duration was not a responsiveness
contract, and ticks delivered after completion could inflate the count.

**Evidence.** Tagged worker/timer instrumentation recorded `[490-RESP] worker-start`
on thread 12492 at 0.003 s, worker-end at 0.057 s, and GUI ticks on thread 5184
continuing from 0.119 s through 0.181 s. The failed CI assertion recorded `[1, 1]`.

**Root cause.** The test counted timer ticks during however long a small real
computation and its queued result delivery happened to take. Faster completion
could legitimately produce fewer ticks; later ticks did not prove an in-flight worker.

**Fix.** Hold the real computation at a thread Event, require three GUI heartbeat
ticks while the worker is still running/pending, assert a different thread identity,
release it and verify the real result. Always release on failure. Preserve the
existing timer interval and result timeout. All 18 sun-mismatch workflows pass;
a synchronous-worker negative control fails the thread-identity assertion.
Remove all temporary probe prints before committing.

**Lesson.** Control the in-flight interval when proving responsiveness. Do not
infer it from the incidental duration of a small fixture or loosen the tick count.

