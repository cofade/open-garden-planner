# Case study: a journal pin Qt could not hit (#674, manual test 4 / #728)

**Symptom.** Clicking a journal pin on the canvas did not select it; the click
cleared the selection and a rubber band started. After selecting the pin from the
Journal panel, pressing it to drag lost the pin after a small movement.

**Wrong theories, in the order they were tried.**

1. *The pin's shape was wrong.* `pin.shape().contains(local)` was True and
   `scene.items(scene_pos)` returned the pin.
2. *The Y flip broke the transform.* It was not the flip: a plain
   `QGraphicsRectItem` with `ItemIgnoresTransformations` also returned None from
   `scene.itemAt` with an IDENTITY transform, while the same item without the flag
   was found.
3. *A select-tool change was the regression.* The tool's own walk already found
   the pin; Qt's press path, which ran after it, still could not.

**Key evidence.** For a flagged item: `scene.itemAt(pos, view.transform())` →
None, `scene.itemAt(pos, view.transform())` with identity → None,
`scene.items(pos)` → the item. Clearing the flag made `itemAt` return it again.

**Root cause.** `QGraphicsScene.itemAt` (and therefore `QGraphicsView.itemAt` and
Qt's whole press/drag/double-click path) does not return
`ItemIgnoresTransformations` items. The pin was therefore invisible to Qt's
interaction machinery; only the Journal panel's `setSelected` path worked.

**Fix.** `CanvasView._journal_pin_at` is the pin's hit test: it walks
`scene.items(pos)`, stops at a drag handle or another selectable item above the
pin, and ignores a pin inside a group (the group is the click target). The same
walk then drives a plain click (replace selection), Ctrl/Shift (toggle) and the
drag in `mouseMoveEvent`, with `mouseReleaseEvent` committing one
`MoveItemsCommand`; double-click opens the note. Pinned by
`tests/integration/test_garden_journal.py::TestPinPointerInteraction`.

**Lesson.** `ItemIgnoresTransformations` is a rendering promise, not an
interaction one. Every item that uses it must own a hit test that does not go
through `itemAt`, or it will be visible and unreachable at the same time.
