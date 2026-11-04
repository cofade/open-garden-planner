## 1. Coordinate systems — the one mental model

There are three frames in any Graphics View app: **local** (item-internal),
**scene** (shared world), and **view/device** (widget pixels). This app adds a
CAD twist, decided in ADR-002 (`docs/09-architecture-decisions/README.md`):
the world is **Y-up, origin bottom-left, units = centimeters**.

The entire Y-up convention is implemented in ONE place — the view transform
(`CanvasView._apply_transform`, `canvas_view.py` ~line 605):

```python
transform = QTransform()
transform.scale(self._zoom_factor, -self._zoom_factor)  # Negative Y for flip
transform.translate(0, -self._canvas_scene.height_cm)
self.setTransform(transform)
```

Composed, this maps scene `(x, y)` → view `(z·x, z·(H − y))` where
`H = height_cm`. Consequences:

- **Scene coordinates ARE the CAD coordinates the user sees.** Scene `(0, 0)`
  renders at the visual bottom-left; larger scene Y is visually higher. The
  status bar shows raw scene coords (`coordinates_changed.emit(scene_pos.x(),
  scene_pos.y())`, `canvas_view.py` ~line 1987). No conversion layer exists in
  the data path — the flip lives only in the display transform.
- The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)`,
  accessed as `scene.canvas_rect` (`canvas_scene.py` ~line 415).
- Qt's *default* convention (any rendering that bypasses `CanvasView` —
  `scene.render()`, minimap, thumbnails, a painter inside `paint()`) is
  **Y-down**: it draws scene y=0 at the *top*. Every Y bug in this repo is
  some surface forgetting which side of the flip it is on.

Beware of two frames of *description* in older docs — **this skill's §1 is the
single owner of the reconciliation; other skills defer here.** §8.10 of
`docs/08-crosscutting-concepts/README.md` calls scene coords "Y-down, (0,0)
top-left" and says to convert with `scene_to_canvas` — that is the abstract Qt
convention, true only for un-flipped renders. The operative rule is §11.4's:
*"The view applies `scale(zoom, -zoom)` so positive scene Y is visually upward
on canvas."* (`docs/11-risks-and-technical-debt/README.md`). The two repo docs
are genuinely split; the data path follows §11.4.

Why the §8.10 framing misleads a test author: `CanvasView.scene_to_canvas()` /
`canvas_to_scene()` (`canvas_view.py` ~line 1433) DO compute `height_cm −
scene_y`, but they have **zero production callers** — grep finds only two callers
in `tests/ui/test_canvas.py`. The status bar, rulers, DXF (`dxf_y = scene_y`),
and serialization all consume **raw** `scene_pos.y()` directly. So an assertion
that pipes an expected value through `scene_to_canvas` produces `H−y`-mirrored
numbers production never emits. **Assert in raw scene coordinates.**

### Surface → what to do about Y (the consequences catalog)

| Surface | What to do about Y | Ground truth |
|---|---|---|
| Item geometry, serialization, snap, constraints, most tool math | Nothing. Work in scene cm; the numbers are already CAD Y-up. **One exception: typed coordinate input — see the next row.** | whole codebase |
| **Typed coordinate input** (`@dx,dy` cartesian, `@dist<angle` polar — ADR-021) | The parser **DOES flip Y at the user-input boundary**: it reads entered coordinates in math-convention Y-up and negates into scene space — `QPointF(a, -b)` (absolute), `last_point.y() - b` (relative), `dy = -distance * sin(rad)` (polar). Its own in-code comment says *"Scene Y axis points down"* — i.e. the parser sits on the §8.10 side of the same repo split, so this is a genuine converting seam, **not** a "numbers are already Y-up" case. The `-b` flip and its test are load-bearing: do NOT "simplify" them away. | `core/coordinate_input/parser.py` ~118 (polar), ~138 (relative), ~146 (absolute); `tests/unit/test_coordinate_parser.py`; also flagged as a converting seam in `ogp-architecture-contract` invariant 1 |
| Screen-intuition directions ("rows go down", "90° = down") | Negate: linear/grid array uses `dy = -spacing * sin(angle_rad)`; grid array steps `-row_spacing` per row. Applies whenever a user-facing angle convention follows *screen* intuition instead of math convention. | §11.4 "Canvas Y-axis flip"; `canvas_view.py` ~4695, ~5015 |
| `painter.drawText()` inside `QGraphicsItem.paint()` | It renders **mirrored** (inherits the flip). Fix: child `QGraphicsSimpleTextItem` with `ItemIgnoresTransformations` (draws in its own non-flipped pixel frame). Anchor at `rect.top()` — smallest scene-Y = *visual bottom* after the flip. | §11.4; `garden_item.py` `_label_item` ~797; `canvas_scene.py` ~857 |
| `scene.render()` to PNG/PDF/image | A negative-height target rect is **EMPTY** in PyQt6 (`QRectF(0, H, W, -H).isEmpty()` is True) — nothing paints. The correct recipe: `painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source)`. `H_PIXELS` = image height in **pixels**, not cm. Canonical implementation: `services/scene_rendering.render_scene_region(..., y_flip=True)` — reuse it, don't re-derive. | §11.4; `scene_rendering.py` lines 180–188 |
| Thumbnails via pixmap | Alternative: render un-flipped, then `pixmap.transformed(QTransform().scale(1, -1))`. Hide `ItemIgnoresTransformations` items and z ≥ 100 overlays first (they'd land at wrong size/position). | §8.9.5 |
| Minimap / any widget mapping its own pixels ↔ scene | Widget pixel Y=0 is visual **top** = scene Y = `height_cm`. Invert: `sy = rect.y() + rect.height() * (1 - my/h)`. | §8.9.6; `minimap_widget.py` |
| PDF (`QPdfWriter`) | Don't pre-flip on the writer's painter (its initial margin transform breaks the formula). Render to a temporary `QImage` (flip is reliable there), then `painter.drawImage(...)`. Also `writer.setResolution(72)` **before** `setPageLayout()`. | §11.4 (two entries) |
| SVG export | Under the `scale(1,-1)` painter flip, `<pattern>` texture tiles render upside-down; post-processed by `ExportService._fix_svg_pattern_yflip()` (adds `patternTransform`). | §11.4; `export_service.py` |
| **DXF export/import** | **NO negation either way.** DXF is Y-up and so is our scene: `dxf_y = scene_y`; import `_y(v) = v * scale`. `dxf_y = canvas_h - scene_y` double-flips (a real past bug). Caution: the `import_file` docstring in `services/dxf_service.py` (~line 324) still says "Y-coordinates are negated" — that comment is **stale and wrong**; the code and the class docstring (~line 94) are correct. | §11.4 "DXF Y-axis"; `dxf_service.py` `_y` helper |
| Agent render tool (`render_canvas_image`) | Output PNG matches the live view (Y-up display), so image *pixel* Y is inverted relative to scene numbers: `px_x = (x_cm - region_x_cm) * px_per_cm`; `px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`. Documented on `RenderMeta.px_per_cm`; pinned by `tests/unit/test_agent_api_render_coordinate_frame.py`. | §8.19; `agent_api/render.py` |
| Item rotation angles | Serialized as a separate angle pivoting on the centre (see §2 below). `core/cad_geometry.py` documents its convention per function — arc math is "degrees CCW from +X" (math convention); one helper explicitly notes Qt's "clockwise-positive in y-down space" screen convention. Read the docstring of the function you call. | `cad_geometry.py` lines 196–198, 272, ~498 |

**Test-writing corollary**: tool integration tests pass *scene* coordinates to
`tool.mouse_press(event, scene_pos)` directly (§8.10) — no flipping. Only
view-pixel-level tests (`QTest` on the viewport) need `view.mapFromScene()`.

---

