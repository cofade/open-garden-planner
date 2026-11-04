## 16. Inert curve handles — the `ItemIgnoresTransformations` grab drop (#193)

Source: debug-verbose case study (2026-06-08), §11.4 entry, ADR-025.

- Symptom: new `CurveControlHandle`s render but nothing can be dragged; all direct-hook
  tests green.
- Wrong theories: reshape math wrong (hooks pass every test); handle's own
  `mousePressEvent` broken (mirrors `VertexHandle` exactly); draw tool eating clicks.
- Evidence: a hand-built `QMouseEvent` was **not delivered** to the
  `ItemIgnoresTransformations` child even though `itemAt` found it; switching to
  `QTest.mousePress` on `view.viewport()` exposed `view._active_drag_handle is None`
  after the press.
- Root cause: PyQt6 silently drops the mouse grab on `ItemIgnoresTransformations` child
  items between events. `CanvasView` re-establishes the grab — but only for an
  `isinstance` **allow-list** of handle types, and the new handle wasn't in it.
- Fix: one line (add to the tuple). Standing trap: **every new drag handle that sets
  `ItemIgnoresTransformations` MUST be added to the allow-list in
  `CanvasView.mousePressEvent`** (grep `_active_drag_handle`) — a faithful copy of an
  existing handle is still dead until the view knows its type. Testing note: use
  `QTest.mousePress/Move/Release` on `view.viewport()` (after `centerOn`) — synthetic
  events never reach these children.
- Status: closed; the opt-in registration trap remains live for future handles. Pinned
  by `tests/integration/test_curve_vertex_edit.py::TestHandleDragViaView` (fails without
  the fix).

---

