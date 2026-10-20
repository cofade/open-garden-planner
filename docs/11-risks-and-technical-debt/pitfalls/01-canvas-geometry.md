# Pitfalls: canvas geometry, painting and export

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CAN-01

- **Rule:** Canvas item caching, Level of Detail (LOD), and selection handle ghosting (issue #409, TD-034, AUD-056)
- **Pinned by:** none — retired with its subject
- **Source:** #409, #503
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l171-canvas-item-caching-level-of-detail-lod-and-selection-handle-ghosting-issue-409-td-034-aud-056)
- **Legacy:** README L171

### PF-CAN-02

- **Rule:** A plant's drawn icon has a fourth independent size, reversing an explicit ADR-037 rejection on the owner's call (issue #299).
- **Pinned by:** none — pending Phase 3 review
- **Source:** #218, #219, #299
- **Status:** standing
- **Legacy:** README L220

**A plant's drawn icon has a fourth independent size, reversing an explicit ADR-037 rejection on the owner's call (issue #299).** A user assigning a Trefle-sourced Apple tree (max spread 590 cm) saw the shadow correctly shrink after setting "Current Spread" to 200 cm (a young tree), but the SVG icon on the canvas stayed at 590 cm. This was, at the time, a *deliberate* decision — ADR-037's growth addendum explicitly rejected rescaling canvas circles ("a display-scale on live items perturbs selection/snap/`mapToScene`, exactly the #218/#219 territory") — but the owner judged the resulting behaviour (a full-size mature icon casting a visibly smaller shadow) to read as a bug, not a feature, and chose to reverse the conclusion while keeping the original hazard analysis intact: never touch `rect()`/`pos()`/`transformOriginPoint()` (the actual thing selection/snap/`mapToScene` depend on). `CircleItem._visual_plant_diameter_cm()` renders the SVG pixmap (and, since a first cut missed this, the decorative drop-shadow — see below) at today's growth-interpolated spread when available, falling back to the footprint diameter unchanged otherwise; `rect()`/`radius` (spacing/overlap correctness, still governed by `core/plant_sizing.py`) are provably untouched, since selection/drag/rotation/undo/save all read only those, none of which this change reads or writes.

### PF-CAN-03

- **Rule:** A first cut of this fix shipped a severe, unrendered regression a senior-review pass caught before merge
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l222-a-first-cut-of-this-fix-shipped-a-severe-unrendered-regression-a-senior-review-pass-caught-before-merge)
- **Legacy:** README L222

### PF-CAN-04

- **Rule:** Anchor index on same-type anchors
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L272

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.

### PF-CAN-05

- **Rule:** Canvas Y-axis flip
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L280

- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

### PF-CAN-06

- **Rule:** EDGE_* anchor type instability on polygons/polylines
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L284

- **EDGE_* anchor type instability on polygons/polylines** (TD-007): `_polygon_anchors()` in `measure_snapper.py` classifies each edge as `EDGE_TOP/BOTTOM/LEFT/RIGHT` based on its **current** dominant axis (horizontal vs vertical). This is a dynamic, geometry-dependent label. When a vertex is dragged far enough to flip an edge's dominant axis (e.g. a nearly-horizontal edge becomes nearly-vertical), the freshly-computed anchor type differs from the value stored in the constraint record. `_resolve_anchor_position()` in `dimension_lines.py` then fails on its `(type AND index)` match and falls through to type-only matching, snapping the constraint indicator to the wrong edge. Current workaround: an EDGE_*-aware index-only match block at the top of `_resolve_anchor_position` catches these mismatches before the fallback fires. Long-term fix (TD-007): replace all four `EDGE_*` types with a single `AnchorType.EDGE_MIDPOINT` and use `anchor_index` as the sole edge identity. The edge is always identified by its start-vertex index, not by axis classification, making the anchor stable across all vertex moves.

### PF-CAN-07

- **Rule:** `scene.render()` with negative-height target rect is empty (PyQt6)
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L286

- **`scene.render()` with negative-height target rect is empty (PyQt6)**: `QRectF(0, H, W, -H).isEmpty()` returns `True`. Passing this as the target to `scene.render()` clips to an empty region — nothing is painted. The correct Y-flip technique is `painter.save(); painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source_rect); painter.restore()`. `H_PIXELS` must be the **image height in pixels**, not the canvas height in cm.

### PF-CAN-08

- **Rule:** `ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L288

- **`ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`**: When rendering via `scene.render()` (not through a QGraphicsView), `ItemIgnoresTransformations` items render at their natural pixel size regardless of the source→target scale. For a large scene (e.g. 5300 cm) rendered into a small image (774 px), a 10 pt text item can appear as 80+ cm on canvas. Fix: call `ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering and `_restore_text_after_export()` after. The scale = `output_width_cm / canvas_width_cm`.

### PF-CAN-09

- **Rule:** QPdfWriter must use `setResolution(72)` before `setPageLayout()`
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L292

- **QPdfWriter must use `setResolution(72)` before `setPageLayout()`**: Default QPdfWriter resolution is ~1200 DPI. `painter.viewport()` returns device-pixel dimensions, so all layout math in points (1/72 inch) lands in the top-left corner. Adding `writer.setResolution(72)` makes device pixels equal PDF points and layout coordinates match.

### PF-CAN-10

- **Rule:** `scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins)
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L294

- **`scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins)**: QPdfWriter's painter has a non-identity initial transform from margin handling. The painter pre-flip formula `translate(0, cr.top + cr.bottom); scale(1,-1)` is mathematically correct in isolation but produces wrong output because the initial transform shifts the baseline. Fix: render the scene into a temporary `QImage` (where pre-flip is reliable) then embed with `painter.drawImage(content_rect, img)`.

### PF-CAN-11

- **Rule:** Plant items store center in `boundingRect()`, not in `pos()`
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L296

- **Plant items store center in `boundingRect()`, not in `pos()`**: OGP `CircleItem` and similar types define their geometry in local coords with `pos()` always at (0, 0). `item.pos()` and `item.scenePos()` both return (0, 0). To get the visual center in scene coordinates: `item.mapToScene(item.boundingRect().center())`.

### PF-CAN-12

- **Rule:** SVG pattern tiles appear Y-inverted under painter Y-flip
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L298

- **SVG pattern tiles appear Y-inverted under painter Y-flip**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. When the scene is rendered with a `scale(1,-1)` painter transform, each pattern tile image is stored un-flipped, but renders upside-down inside the Y-flipped coordinate space. Fix: post-process the SVG after `painter.end()` and add `patternTransform="matrix(1,0,0,-1,0,{tile_height})"` to each `<pattern>` element. See `ExportService._fix_svg_pattern_yflip()`.

### PF-CAN-13

- **Rule:** `QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas
- **Pinned by:** `scripts/svg_preview.py`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L300

- **`QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas**: For texture-filled shapes, Qt emits a "shadow" group containing the polygon `<path>` (`fill="#000000"`) followed by a texture group `<g fill="url(#tex)"><rect x="..." y="..." width="..." height="..."/></g>`. The rect is the *painter's clip bounding rect*, not the polygon shape — and the painter's `setClipPath()` is **never** serialized as `<clipPath>`. In SVG viewers (browsers), the unconstrained rect washes across the whole canvas (often as a brownish overlay if it is a roof-tile texture). PNG export is unaffected because Qt's native renderer applies the clip directly. Fix: post-process the SVG (`ExportService._fix_svg_qt_texture_clipping()`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's `<path>` (preserving its `transform`), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 with a `used_textures` set; forward-window scans match the same texture from multiple shadows and corrupt the XML tree. Validate SVGs in a real browser (`scripts/svg_preview.py` uses Edge headless) — `QSvgRenderer` is too forgiving and hides this bug.

### PF-CAN-14

- **Rule:** DXF Y-axis: scene Y is already Y-up, no negation needed
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L302

- **DXF Y-axis: scene Y is already Y-up, no negation needed**: OGP scene uses Y-up (scene Y=0 = visual bottom). DXF also uses Y-up. The formula `dxf_y = canvas_h - scene_y` double-flips. Correct mapping: `dxf_y = scene_y`. Similarly for import: `scene_y = dxf_y * scale` (no negation).

### PF-CAN-15

- **Rule:** `painter.drawText()` inside `QGraphicsItem.paint()` renders upside-down on the Y-flipped canvas
- **Pinned by:** none — pending Phase 3 review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L328

- **`painter.drawText()` inside `QGraphicsItem.paint()` renders upside-down on the Y-flipped canvas**: The view applies `scale(zoom, -zoom)` for the CAD-style bottom-left origin (ADR-002). Text drawn directly inside a `paint()` method inherits this flip and appears mirrored. Symptoms: badge text reads as mirror image; positioning using `rect.bottom()` lands at visual *top* and vice versa. Fix: use a child `QGraphicsSimpleTextItem` (or a custom `QGraphicsItem` subclass) with the `ItemIgnoresTransformations` flag — Qt then draws the item in its own non-flipped pixel-coordinate system. Examples: bed name labels (`_label_item` in `garden_item.py`), succession badge (`SuccessionBadgeItem` in `garden_item.py`), compare-mode overlay labels (`canvas_scene.py`). Anchor at `rect.top()` (smallest scene-Y = visual bottom after flip) and extend the bounding rect upward (negative local Y) so the badge sits inside the bed.

### PF-CAN-16

- **Rule:** Grid snap silently overrides anchor snap unless `CanvasView.snap_point` short-circuits
- **Pinned by:** `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L352

- **Grid snap silently overrides anchor snap unless `CanvasView.snap_point` short-circuits** (Package A, ADR-020/021): Every drawing tool calls `self._view.snap_point(scene_pos)` inside its own `mouse_press`/`mouse_move`/`mouse_release`. The `CanvasView` dispatcher (`_maybe_apply_anchor_snap`) snaps the scene_pos to a midpoint/intersection/endpoint candidate *before* dispatching to the tool — but the tool's own `snap_point` call then rounds that anchor-snapped coordinate back to the nearest grid line (e.g. an edge midpoint at (175, 100) becomes (200, 100) on the default 50 cm grid). With grid snap on (the default), the new Package A snap modes silently lose. Symptom: midpoint/intersection glyph appears on hover but the committed vertex lands on a grid line, not the visible anchor. Root cause: anchor-snap and grid-snap are independently applied by two unrelated layers without composition rules. Fix: `CanvasView.snap_point()` short-circuits the grid rounding step when `self._current_snap is not None`. Anchor snap always wins on the click path; the bounds clamp still runs. Regression test: `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap` (uses a 350×100 rect with a midpoint at (175, 100) — deliberately not on the 50 cm grid). The single short-circuit site keeps this an explicit invariant rather than a side-effect of call ordering — if you find yourself adding a third snap layer, add an explicit composition rule before merging.

### PF-CAN-17

- **Rule:** A pixmap blitted in item-local coordinates is upside-down on the canvas — and the plant sprites hid it for eight months
- **Pinned by:** `tests/integration/test_object_sprite_rendering.py::TestUprightOnCanvas`
- **Source:** #308
- **Status:** standing
- **Legacy:** README L404

- **A pixmap blitted in item-local coordinates is upside-down on the canvas — and the plant sprites hid it for eight months** (Package 3a #308, owner manual test 2026-08-17): the view and every export (`export_service`, `pdf_report_service`, `scene_rendering`, `print_dialog`) draw the scene through `scale(1, -1)` (scene Y-up, §8.9), so `painter.drawPixmap(rect, pixmap)` inside `paint()` renders the image mirrored vertically. Every SVG-rendered object had been drawn that way since Phase 6; the plant sprites are radially symmetric *and* randomly rotated, the legacy furniture was near-symmetric, so nobody saw it — until the new fire pit's flames pointed **down** while the gallery thumbnail (rendered without the flip) pointed up. **Fix**: the furniture branches of `RectangleItem.paint` / `CircleItem.paint` flip the painter back about the rect centre (`translate(c); scale(1, -1); translate(-c)`) — the same idea as `background_image_item`'s flip transform and the text items' `setTransform(scale(1, -1))`. Pinned by `tests/integration/test_object_sprite_rendering.py::TestUprightOnCanvas`, which renders the wheelbarrow (heavy wheel end up, thin handles down) through the real flipped `scene.render` and asserts the top band carries more ink than the bottom, as the art does — the test fails with the exactly mirrored numbers without the fix. **Two lessons**: (1) any raster drawn in item space needs the local un-flip; only vector primitives and child items with their own transform are exempt; (2) a metric over `scene.render()` of a `CanvasScene` measures the opaque canvas background, not your item — render the item alone in a bare `QGraphicsScene` (`_render_item_alone` in that test file), which also exposed that an earlier "the tool draws an item that paints" assertion had been vacuous.

### PF-CAN-18

- **Rule:** A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473)
- **Pinned by:** none — pending Phase 3 review
- **Source:** #438, #441, #450, #469, #470, #472, #473
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1119-a-frame-sized-by-a-polygons-most-expensive-vertex-and-one-look-rule-for-item-copies-470472473)
- **Legacy:** README L1119 (legacy 11.4.9)

### PF-CAN-19

- **Rule:** A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass)
- **Pinned by:** `tests/integration/test_item_appearance_roundtrip.py`
- **Source:** #438, #469, #470, #472, #473, #502
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1127-a-fill-colour-nobody-could-see-and-the-round-trip-test-that-asserted-the-wrong-thing-502-from-470472473s-manual-pass)
- **Legacy:** README L1127 (legacy 11.4.10)

### PF-CAN-20

- **Rule:** A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503)
- **Pinned by:** `scripts/verify_lod_removal_mutations.py`; `tests/integration/test_canvas_item_cache.py`; `tests/perf/test_nfr_budgets.py`
- **Source:** #409, #472, #501, #503
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1139-a-dead-optimisation-is-not-a-latent-feature-and-a-negative-pin-can-stop-noticing-503)
- **Legacy:** README L1139 (legacy 11.4.11)

### PF-CAN-21

- **Rule:** An item states its look once
- **Pinned by:** `tests/integration/conftest.py::_every_item_says_what_it_paints`; `tests/integration/test_item_roundtrip_matrix.py`; `tests/integration/test_item_style_in_step.py`; `tests/integration/test_polyline_style_paint.py`
- **Source:** #441, #453, #470, #501, #502, #503, #523, #524, #525, #526, #527
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#2d-defects-the-bake-found)
- **Legacy:** README L2537
