## Case study: new curve edit-handles appear but are completely inert / can't drag (issue #193, fixed 2026-06-08)

**Symptom**: New `CurveControlHandle` widgets render on a selected Bezier/Arc (blue/green squares show), but no handle — and seemingly nothing — can be dragged; the curve feels "stuck in place." All the unit/integration tests that called the item hooks (`_move_control` etc.) directly were green, so the geometry/undo logic was provably fine.

**Wrong theories**:
- *The reshape math or undo snapshot is wrong*. Disproved — the model hooks pass every direct test; the geometry mutates correctly when `_move_control` is invoked.
- *The handle's own `mousePressEvent`/`grabMouse` is broken*. Disproved — the handle mirrors `VertexHandle` exactly (same `grabMouse()` + `ItemIgnoresTransformations` + zValue).
- *The draw tool is still active and eats the clicks*. Disproved — `add_item`/`bezier_tool` don't auto-select, so handles only appear once the user has selected with the SELECT tool, which lets item clicks through (`select_tool.mouse_press` returns `False`).

**Key signal**: tried to write a view-level reproduction. A hand-built `QMouseEvent` passed to `view.mousePressEvent` did **not** deliver to the handle (`scene.mouseGrabberItem()` stayed `None`, event unaccepted) **even though `itemAt` found it** — because Qt won't hit-test/deliver a synthetic press to an `ItemIgnoresTransformations` child (this is *also* why the polyline tests never drive view-level events). Switching to `QTest.mousePress` on `view.viewport()` (real event dispatch) finally grabbed the handle — and exposed that `view._active_drag_handle` was `None` after the press.

**Root cause**: `CanvasView` works around a PyQt6 bug where Qt **silently drops the mouse grab on `ItemIgnoresTransformations` child items between events** by tracking `self._active_drag_handle` on press and re-establishing the grab in `mouseMoveEvent`/`mouseReleaseEvent`. That tracking only fires for an allow-list of handle types (`isinstance(grabber, (ResizeHandle, RotationHandle, VertexHandle, RectCornerHandle, MidpointHandle))`). The new `CurveControlHandle` wasn't in the tuple, so the press grabbed but the grab was dropped before the first move and never re-established → the handle got the press and *no moves* → inert.

**Fix**: add `CurveControlHandle` to the allow-list tuple (and its import) in [ui/canvas/canvas_view.py](src/open_garden_planner/ui/canvas/canvas_view.py). One-line behavioural change. Regression test `TestHandleDragViaView` drives the real path with `QTest` and asserts `view._active_drag_handle is handle` after the press (fails without the fix, passes with it).

**Lesson**: (a) **Any new in-scene handle that uses `ItemIgnoresTransformations` must be registered in `CanvasView`'s `_active_drag_handle` allow-list** — the dropped-grab workaround is opt-in by type, so a faithful copy of `VertexHandle` is still dead until the view knows about it. Grep `_active_drag_handle` when adding a handle class. (b) Tests that call item hooks directly can't see a view-routing bug; the riskiest layer (press→grab→move delivery) needs a **real** event-path test. (c) `QGraphicsView` does **not** deliver a hand-constructed `QMouseEvent` to `ItemIgnoresTransformations` children — use `QTest.mousePress/Move/Release` on `view.viewport()` (and `centerOn` the target first so it's inside the viewport) for faithful handle-drag tests.

---

