## Case study: a negative control that only CI could fail — the overlay's own echo (Phase 17 L1.6, fixed 2026-10-11)

**Symptom**: `assert controller.recompute_count == count + 4` failed with `assert 6 == (1 + 4)` in the CI Test job. The Coverage job passed on the same commit; twenty local runs passed.

**Theories entertained (wrong)**:
1. *"CI is slow; the wait of two debounce intervals was too short."* The control waits for NOTHING to happen; a longer wait can only make it fail more often.
2. *"The helper waits on a count, not on a duration, so it cannot race."* It waited for the count and then for the debounce timer to be idle — and the timer IS idle straight after a recompute.

**What the instrumentation revealed** (a probe that runs the recompute synchronously and counts event-loop rounds):

```text
[ECHO] height 75: recompute_count 1 -> 2; debounce active False
[ECHO]   rounds of processEvents until scene.changed: 1; debounce active True
[ECHO] race: recompute_count 5, debounce active False, undo done
[ECHO]   after the echo and its debounce: recompute_count 6 (the control expected 5)
```

**Root cause**: a recompute sets the shadow overlay's path. The scene emits `changed` one event-loop round later, and `changed` is wired to `SunShadowController.schedule_recompute`. That echo's recompute is a no-op while nothing changed (the key holds) — but the test's negative control makes an edit nothing announces, and an echo delivered after it carries the edit into the overlay. Locally the echo always arrived inside the helper's first 10 ms poll; in one CI job it did not.

**Fix**: the helper (`OverlayWatch.settled`) waits for the recompute count, THEN for a `scene.changed` delivered since that recompute, then for the debounce the echo starts. `tests/integration/test_scene3d_base_stacking.py::TestTheOverlaysOwnEcho` holds both halves of the race still by calling `recompute_now()` directly — the echo is then certainly undelivered — once without waiting for it (exactly one extra recompute) and once through the helper (none). With the old helper the second test fails three times out of three.

**Lesson**: "the timer is idle" is not "nothing is pending". When a system answers its own action with a signal, wait for that signal. And a race is turned into a regression by taking the event loop out of the step that hides it: run that step synchronously, and the bad interleaving is the only one there is.

