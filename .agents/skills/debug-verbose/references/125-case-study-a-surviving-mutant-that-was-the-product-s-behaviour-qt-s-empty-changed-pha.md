## Case study: a surviving mutant that was the product's behaviour — Qt's empty `changed([])` (Phase 17 L1.3, fixed 2026-10-19)

**Symptom**: the hand mutant "an explained repaint arms the quiet timer too" survived every test
of the 3D sync controller. The test written to kill it failed on the UNMUTATED product: a write
that nudged the plan revision and then repainted was in 3D at once — and 400 ms later a second
whole-plan snapshot ran and found nothing.

**Wrong theory**: *"the 2D side's debounced work repaints later"* — plausible (the matrix test
had seen late repaints) and wrong.

**Key evidence**: a probe that logged every `scene.changed` with its rectangles and every pass,
for five write patterns:

```
update_only:        changed([(397, 297, 306, 206)]), changed([]), applied(net)
write_nudge_update: applied(announced), changed([(397, 297, 306, 206)]), changed([]), applied(net)
```

**Root cause**: with a listener on `QGraphicsScene.changed`, Qt reports an item's `update()` at
once from `_q_processDirtyItems`; the queued `_q_emitUpdated` the same update asked for arrives
afterwards and emits what is left — an empty list. The controller's "explained" test compared
the plan revision with the one the previous `changed` had recorded; the empty echo came right
after the explained one, saw no move, and armed the net.

**Fix**: an empty `changed` reports no repaint and is ignored
(`ui/view3d/sync_controller.py::Scene3DController._on_scene_changed`).

**Lesson**: **log a signal's ARGUMENTS, not just that it fired** — two emissions per update looked
like "something else repainted" until the second one was seen to carry nothing. And a surviving
mutant is a question about the product as much as about the tests.

