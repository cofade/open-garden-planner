# Case study: the minimap that deselected the pin it was drawing around (#674, manual test 4)

**Symptom.** A journal pin selected correctly and stayed selected while still.
As soon as it was dragged it became unselected within milliseconds. After the
pin was grouped with a circle, clicking the group selected it and then lost the
selection just as quickly.

**Wrong theories, in the order they were tried.**

1. *Qt's press path was still winning.* It was not: the pin was selected after
   press, and a bare `CanvasView` had no such problem.
2. *The properties/3D selection refresh cleared it.* Instrumenting
   `scene.clearSelection()` showed no calls after the press.
3. *The pin's own `setVisible` was flipping.* It was not the pin's own code.

**Key evidence.** A class-level `QGraphicsItem.setVisible` trace in the full app
showed `MinimapWidget._do_update` hiding the pin and then restoring it. The
minimap masks every `ItemIgnoresTransformations` or high-z item before
`scene.render`; a pin is both. Qt deselects an item when it is hidden. The
minimap is throttled to 100 ms and re-renders on the drag's own scene changes,
so the pin lost the selection one thumbnail after the gesture started. A group
containing a pin inherited the same loss through Qt's selection propagation.

**Root cause.** `MinimapWidget` used `setVisible(False)`/`True` to keep overlays
out of the thumbnail. Visibility is not a paint-only property: it is part of the
selection state.

**Fix.** The minimap now sets `ItemHasNoContents` for the duration of the
render and clears it afterwards. The overlay paints nothing into the thumbnail,
but stays visible, selected and out of the plan revision. `ItemHasNoContents`
was verified against a rendered pixel (red overlay present before/absent during/
present after), not just against the flag.

**Lesson.** A renderer that borrows the live scene must not borrow the user's
state. Mask paint, not presence. Export Service already restored the selection
around its hide/restore; a periodic thumbnail cannot afford to touch it at all.
