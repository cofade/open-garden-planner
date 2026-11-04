## Case study: debounce protected workers but not scene collection (#315)

**Symptom.** One layer visibility command synchronously scanned the whole garden
for every object's notification even though it launched no worker immediately.

**Wrong theories.** Counting worker launches alone cannot prove responsiveness;
no worker-thread or rasterization bottleneck was assumed before measuring capture.

**Evidence.** The fail-first collection-count regression counted 154 synchronous
snapshots for 150 sheds. Afterward the same command captures zero synchronously
and one latest input snapshot when debounce expires. Requirement-only changes reuse
the completed measurements without launching a worker.

**Root cause.** Both schedule and UI reflection collected exposure before debounce.

**Fix.** Notifications mark inputs dirty and withdraw measurements cheaply. Constant
time spatial identity checks immediately clear incompatible imagery; collection and
semantic comparison wait for debounce. Explicit export boundaries still revalidate.
A separately retained receiver cache restores a matching completed map without work.

**Lesson.** Debounce the expensive input capture itself. Assert collection counts
across bulk commands as well as launches and the final result.


