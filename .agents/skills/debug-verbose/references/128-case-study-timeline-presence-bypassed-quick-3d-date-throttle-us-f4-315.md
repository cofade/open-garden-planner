## Case study: timeline presence bypassed Quick 3D date throttle (US-F4, #315)

**Symptom.** Scrubbing over a plant's planting/removal date rebuilt Quick 3D on
every calendar step, although its clock listener throttled regrowth to 500 ms.
Ten removal-boundary crossings produced ten snapshots and ten plan revisions in
156 ms; the same number of steps without a presence transition produced none.

**Wrong theories.** An earlier same-presence burst could exceed the throttle
interval on a loaded runner; that explained timing-dependent extra work in that
test but did not explain the boundary case. Same-turn coalescing could not prove
the user's repeated, separate event-loop steps were throttled.

**Evidence.** The independent review probe logged [BOUNDARY-REV] with
traceback.format_stack(): refresh_timeline → setVisible → ItemVisibleHasChanged
→ announce_plan_change → note_plan_changed → the controller's fast mark_dirty
path. Reproduced [BOUNDARY-RESULT] boundary snapshots 10 revision 10 in 156 ms;
after the scoped guard, snapshots 0 revision 0 in 157 ms. Control stayed 0 / 0.

**Root cause.** Canvas presence is derived from the shared clock. Qt's real
visibility notification made that derived state look like an edit of plan
content, which bypassed the separate date-throttling subscription.

**Fix.** CanvasScene.refresh_timeline sets a try/finally-restored scope only while
applying visibility. The common GardenItem announcement hook suppresses only
ItemVisibleHasChanged inside that scope. Manual visibility, layer commands and
metadata/history edits keep announcing; all other item changes remain untouched.
No temporary instrumentation remains in production.

**Lesson.** Trace every path to the expensive work, and exercise state boundaries
on separate event-loop turns. A throttle on the intended callback does not bound
another callback that the same user action triggers. Regression:
tests/integration/test_timeline_quick3d.py covers planting/removal crossings,
settled final geometry, and controls for visibility/layer/history writes.


