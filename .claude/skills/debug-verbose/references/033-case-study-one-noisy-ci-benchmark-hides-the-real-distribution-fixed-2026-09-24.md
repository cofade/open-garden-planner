## Case study: one noisy CI benchmark hides the real distribution (fixed 2026-09-24)

**Symptom**: one Python 3.11/Linux run measured 284.1 ms for the 1000-item spatial-index rebuild against a 250 ms limit, while a parallel run and the full local suite passed; the implementation was unchanged by the branch.

**Theories entertained (wrong)**:
- The quadtree had a deterministic performance regression.
- Raising the hard ceiling again would be a sufficient fix.
- The fast local run represented the runner distribution.

**What instrumentation revealed**: repeated local samples were tightly clustered around 15 ms, while the historical CI value was an isolated scheduler outlier. A single wall-clock sample had no way to express that distinction.

**Root cause**: the gate encoded a noisy point measurement as a universal contract.

**Fix**: warm the path, collect five rebuild and five query samples, report the samples on failure, and gate medians at 200 ms / 1 ms. This preserves a sustained-regression failure while tolerating one shared-runner spike.

**Lesson**: performance gates should protect a distribution, not assume a noisy runner is quiet; record the platform and evidence alongside the threshold.

---


Remove all `print` instrumentation before committing. The fix lives in the production code; the diagnosis lives in this skill.

---

