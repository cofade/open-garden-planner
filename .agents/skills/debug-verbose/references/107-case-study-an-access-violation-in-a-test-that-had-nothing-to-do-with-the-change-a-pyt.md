## Case study: an access violation in a test that had nothing to do with the change — a Python callable on `destroyed`, and the garbage collector (Phase 17 L1.3, fixed 2026-10-12)

**Symptom**: after `connect_qobject` — "take a clock subscriber off its channel when Qt destroys
it" — was built on `receiver.destroyed.connect(<closure>)`, the suite died with
`Windows fatal exception: access violation` in
`tests/integration/test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`, a test that was
not changed.

**Wrong theory**: *"a slot was called after its receiver died"* — the very thing the helper
exists to prevent, so the helper was the last place looked at. The receiver was alive; what was
called dead was the helper's own closure.

**Key evidence**: bare PyQt 6.11, no product code, four ways to let an object with a closure on
its own `destroyed` signal go:

```
toplevel_plain   (refcount frees the wrapper)                       survived; hook ran 1 time(s)
toplevel_cycle   (wrapper in a cycle; gc.collect())                 collected 6;  hook ran 0 time(s)   <- silently never called
child_cycle      (a child of that wrapper)                          collected 7;  hook ran 1 time(s)
deferred_cycle   (Qt owns it, deleteLater() pending; gc.collect();  collected 11; Windows fatal exception: access violation
                  then the deferred delete runs)                                  File "...", line ??? in hook
```

**Root cause**: a Python callable connected to `destroyed` lives and dies with Python's idea of
the wrapper, not with the C++ object. When the wrapper is garbage in a reference cycle while Qt
still owns the object — a `deleteLater()` is pending, a parent holds it — the cyclic collector
clears the callable, and the connection stays behind in C++. Then either the signal is never
delivered (the second line), or Qt delivers it into what is left (the fourth). It surfaced in
an unrelated test because that is where the collector happened to run.

**Fix**: nothing hangs on `destroyed`. The clock's channel calls a guard that asks
`sip.isdeleted(receiver)` at every delivery and takes itself off
(`src/open_garden_planner/ui/sim_clock_subscription.py`); a test pins that the module never
names the signal.

**Lesson**: **a crash in a test you did not touch is a lifetime bug in what you did touch** —
suspect the garbage collector, and reproduce with an explicit `gc.collect()` in bare PyQt before
reading product code. **Do not hang clean-up on a QObject's `destroyed` signal from Python**:
the callable can be collected before the signal fires. Ask at the moment of use
(`sip.isdeleted`) instead of waiting to be told.

