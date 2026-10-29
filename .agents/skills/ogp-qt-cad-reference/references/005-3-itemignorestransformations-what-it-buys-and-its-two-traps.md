## 3. `ItemIgnoresTransformations` — what it buys and its two traps

The flag makes an item render in device pixels, ignoring the view's zoom *and*
the Y-flip. That's why it is the standard fix for readable, right-side-up text
and constant-size handles: labels (`garden_item.py`), dimension/constraint
text (`dimension_lines.py`, `constraint_tool.py`), badges
(`soil_badge_item.py`), and **all drag handles** in `resize_handle.py`.

**Trap 1 — fixed device-pixel size under `scene.render()`** (§11.4). Outside
a view there is no zoom, so an IIT text item renders at its natural pixel
size regardless of the source→target scale: a 10 pt label on a 5300 cm canvas
rendered into a 774 px image comes out ~80+ cm wide. Fix: call
`ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering
and `_restore_text_after_export()` after (`export_service.py` ~line 105;
`scale = output_width_cm / canvas_width_cm`). The flag stays ON — only the
point size is retargeted. `render_scene_region`'s `text_point_size` argument
is the same idea for the shared pipeline.

**Trap 2 — PyQt6 silently drops the mouse grab on IIT child handles**
(§11.4, #193 follow-up; ADR-025 consequence 7). A handle grabs the mouse in
`mousePressEvent`, Qt loses the grab before the first `mouseMoveEvent`, and
the drag is inert ("handle shows but won't move"). The workaround lives in
`CanvasView`:

- On press (~line 1961) it records the grabber, but **only if it is in the
  isinstance allow-list**: `(ResizeHandle, RotationHandle, VertexHandle,
  RectCornerHandle, MidpointHandle, CurveControlHandle)`.
- On every `mouseMove` (~2050) and `mouseRelease` (~2674, *before* `super()`)
  it re-grabs: `if self._active_drag_handle is not None and
  scene().mouseGrabberItem() is None: self._active_drag_handle.grabMouse()`.

**Contract: every NEW handle type using IIT MUST be added to that allow-list**
— a faithful copy of an existing handle is still dead until the view knows its
type (this exact miss cost a manual-test round for `CurveControlHandle`).
Grep `_active_drag_handle` to find the sites.

---

