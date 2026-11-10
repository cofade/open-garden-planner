# Pitfalls: canvas geometry, painting and export

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CAN-01

- **Rule:** A selected item paints without a device cache so its handles do not ghost, and an export clears every item cache so the render is full vector fidelity.
- **Pinned by:** `tests/integration/test_canvas_item_cache.py`; `tests/perf/test_nfr_budgets.py`
- **Source:** #409, #503
- **Status:** standing; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l171-canvas-item-caching-level-of-detail-lod-and-selection-handle-ghosting-issue-409-td-034-aud-056)
- **Legacy:** b1faaa9 README L171

### PF-CAN-02

- **Rule:** A plant's icon and decorative drop-shadow draw at the shared plan date's growth-interpolated spread, while `rect()`, `pos()` and `transformOriginPoint()` keep the footprint that selection, snap and spacing read.
- **Pinned by:** `tests/integration/test_plan_timeline.py`
- **Source:** #218, #219, #299, #315, ADR-062
- **Status:** standing
- **Legacy:** b1faaa9 README L220

**A plant's drawn icon has a fourth independent size, reversing an explicit ADR-037 rejection on the owner's call (issue #299).** A user assigning a Trefle-sourced Apple tree (max spread 590 cm) saw the shadow correctly shrink after setting "Current Spread" to 200 cm (a young tree), but the SVG icon on the canvas stayed at 590 cm. This was, at the time, a *deliberate* decision — ADR-037's growth addendum explicitly rejected rescaling canvas circles ("a display-scale on live items perturbs selection/snap/`mapToScene`, exactly the #218/#219 territory") — but the owner judged the resulting behaviour (a full-size mature icon casting a visibly smaller shadow) to read as a bug, not a feature, and chose to reverse the conclusion while keeping the original hazard analysis intact: never touch `rect()`/`pos()`/`transformOriginPoint()` (the actual thing selection/snap/`mapToScene` depend on). `CircleItem._visual_plant_diameter_cm()` renders the SVG pixmap (and, since a first cut missed this, the decorative drop-shadow — see below) at the shared plan date's growth-interpolated spread when available (ADR-062, #315), falling back to the footprint diameter unchanged otherwise; `rect()`/`radius` (spacing/overlap correctness, still governed by `core/plant_sizing.py`) are provably untouched, since selection/drag/rotation/undo/save all read only those, none of which this change reads or writes.

### PF-CAN-03

- **Rule:** Compute a plant's visual diameter once at the top of `paint()` and reuse it for both the drop-shadow and the icon, and prove such a change on a rendered frame, not on private helpers.
- **Pinned by:** none — The body names no test for this rule; it notes only that the tests of the time asserted on private helpers and could not see the regression.
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l222-a-first-cut-of-this-fix-shipped-a-severe-unrendered-regression-a-senior-review-pass-caught-before-merge)
- **Legacy:** b1faaa9 README L222

### PF-CAN-04

- **Rule:** Anchors of the same `AnchorType` each carry a unique `anchor_index` in `get_anchor_points()`, or `_resolve_anchor_position()` falls back to type-only matching and picks the first one.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L272

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.

### PF-CAN-05

- **Rule:** Positive scene Y is visually upward on the canvas, so an offset computed from a user-facing angle negates `dy` (`dy = -spacing * sin(angle_rad)`) to match screen intuition.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L280

- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

### PF-CAN-06

- **Rule:** A polygon or polyline `EDGE_*` anchor type changes when an edge's dominant axis flips, so `_resolve_anchor_position()` matches such anchors by index alone before any type-only fallback.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L284

- **EDGE_* anchor type instability on polygons/polylines** (TD-007): `_polygon_anchors()` in `measure_snapper.py` classifies each edge as `EDGE_TOP/BOTTOM/LEFT/RIGHT` based on its **current** dominant axis (horizontal vs vertical). This is a dynamic, geometry-dependent label. When a vertex is dragged far enough to flip an edge's dominant axis (e.g. a nearly-horizontal edge becomes nearly-vertical), the freshly-computed anchor type differs from the value stored in the constraint record. `_resolve_anchor_position()` in `dimension_lines.py` then fails on its `(type AND index)` match and falls through to type-only matching, snapping the constraint indicator to the wrong edge. Current workaround: an EDGE_*-aware index-only match block at the top of `_resolve_anchor_position` catches these mismatches before the fallback fires. Long-term fix (TD-007): replace all four `EDGE_*` types with a single `AnchorType.EDGE_MIDPOINT` and use `anchor_index` as the sole edge identity. The edge is always identified by its start-vertex index, not by axis classification, making the anchor stable across all vertex moves.

### PF-CAN-07

- **Rule:** A negative-height target such as `QRectF(0, H, W, -H)` is empty and makes `scene.render()` paint nothing; flip the painter instead, translating by the image height in pixels and scaling Y by -1.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L286

- **`scene.render()` with negative-height target rect is empty (PyQt6)**: `QRectF(0, H, W, -H).isEmpty()` returns `True`. Passing this as the target to `scene.render()` clips to an empty region — nothing is painted. The correct Y-flip technique is `painter.save(); painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source_rect); painter.restore()`. `H_PIXELS` must be the **image height in pixels**, not the canvas height in cm.

### PF-CAN-08

- **Rule:** Outside a view, `scene.render()` draws `ItemIgnoresTransformations` items at device-pixel size, so every export gives those items — and only those — a point size for the output (`scene_rendering.retarget_constant_size_text`); a text note is sized in plan units and is never touched.
- **Pinned by:** `tests/integration/test_export_text_notes.py`
- **Source:** #789
- **Status:** standing
- **Legacy:** b1faaa9 README L288

- **`ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`**: When rendering via `scene.render()` (not through a QGraphicsView), `ItemIgnoresTransformations` items render at their natural pixel size regardless of the source→target scale. For a large scene (e.g. 5300 cm) rendered into a small image (774 px), a 10 pt text item can appear as 80+ cm on canvas. Fix: call `ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering and `_restore_text_after_export()` after. The scale = `output_width_cm / canvas_width_cm`.

- **Only the constant-pixel-size text (#789)**: the first version of this fix gave EVERY text item of the scene the export's point size. A `TextItem` note and a callout's text have no `ItemIgnoresTransformations`: their font is in plan units and the export's scale already scales them. Forcing one point size on them made a note the user sized on purpose four times too large on a balcony plan and unreadable on a large one. `scene_rendering.draws_at_constant_pixel_size(item)` (the flag on the item or on any ancestor) is the one test, shared by PNG, PDF, SVG, print and the Agent API render. Printing had no label sizing at all — a label was 13 device pixels, a quarter of a millimetre at 1200 dpi — and now uses the same helper.

### PF-CAN-09

- **Rule:** A `QPdfWriter` gets `setResolution(72)` before `setPageLayout()`, so device pixels equal PDF points and layout math in points does not land in the top-left corner.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L292

- **QPdfWriter must use `setResolution(72)` before `setPageLayout()`**: Default QPdfWriter resolution is ~1200 DPI. `painter.viewport()` returns device-pixel dimensions, so all layout math in points (1/72 inch) lands in the top-left corner. Adding `writer.setResolution(72)` makes device pixels equal PDF points and layout coordinates match.

### PF-CAN-10

- **Rule:** Never call `scene.render()` directly on a `QPdfWriter` painter, whose margin transform breaks the Y-flip; render into a temporary `QImage` and embed it with `painter.drawImage()`.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L294

- **`scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins)**: QPdfWriter's painter has a non-identity initial transform from margin handling. The painter pre-flip formula `translate(0, cr.top + cr.bottom); scale(1,-1)` is mathematically correct in isolation but produces wrong output because the initial transform shifts the baseline. Fix: render the scene into a temporary `QImage` (where pre-flip is reliable) then embed with `painter.drawImage(content_rect, img)`.

### PF-CAN-11

- **Rule:** A plant item keeps `pos()` at (0, 0) with its geometry in local coordinates, so its scene centre is `item.mapToScene(item.boundingRect().center())`, never `pos()` or `scenePos()`.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L296

- **Plant items store center in `boundingRect()`, not in `pos()`**: OGP `CircleItem` and similar types define their geometry in local coords with `pos()` always at (0, 0). `item.pos()` and `item.scenePos()` both return (0, 0). To get the visual center in scene coordinates: `item.mapToScene(item.boundingRect().center())`.

### PF-CAN-12

- **Rule:** A pattern brush needs no flip of its own in an SVG export: the tile is in the user space of a group that carries the painter's Y-flip, exactly as on a `QImage`. What `QSvgGenerator` does drop is the brush's own transform, which the SVG recorder moves into the world transform (PF-CAN-53).
- **Pinned by:** `tests/integration/test_svg_export_fidelity.py`
- **Source:** #787
- **Status:** standing
- **Legacy:** b1faaa9 README L298

- **SVG pattern tiles appear Y-inverted under painter Y-flip**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. When the scene is rendered with a `scale(1,-1)` painter transform, each pattern tile image is stored un-flipped, but renders upside-down inside the Y-flipped coordinate space. Fix: post-process the SVG after `painter.end()` and add `patternTransform="matrix(1,0,0,-1,0,{tile_height})"` to each `<pattern>` element. See `ExportService._fix_svg_pattern_yflip()`.

- **Superseded reading (#787)**: `ExportService._fix_svg_pattern_yflip()` added `patternTransform="matrix(1,0,0,-1,0,h)"` to every pattern after the fact. Measured against the PNG export in headless Edge and in `QSvgRenderer`, a pattern fill under the flipped painter is oriented like the PNG WITHOUT that attribute; the post-processor was removed together with the clip pairing of PF-CAN-13. The roof's two halves — the only texture with a stated direction — are compared with the PNG by the fidelity test.

### PF-CAN-13

- **Rule:** `QSvgGenerator` writes no painter clip in its default SVG Tiny 1.2 mode, and `QSvgRenderer` ignores `clip-path` in any mode: an SVG export writes a clipped shape as geometry already cut to its clip (PF-CAN-53), and a test that rasterises with `QSvgRenderer` cannot see a `<clipPath>`.
- **Pinned by:** `tests/integration/test_svg_export_fidelity.py`
- **Source:** #787
- **Status:** standing
- **Legacy:** b1faaa9 README L300

- **`QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas**: For texture-filled shapes, Qt emits a "shadow" group containing the polygon `<path>` (`fill="#000000"`) followed by a texture group `<g fill="url(#tex)"><rect x="..." y="..." width="..." height="..."/></g>`. The rect is the *painter's clip bounding rect*, not the polygon shape — and the painter's `setClipPath()` is **never** serialized as `<clipPath>`. In SVG viewers (browsers), the unconstrained rect washes across the whole canvas (often as a brownish overlay if it is a roof-tile texture). PNG export is unaffected because Qt's native renderer applies the clip directly. Fix: post-process the SVG (`ExportService._fix_svg_qt_texture_clipping()`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's `<path>` (preserving its `transform`), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 with a `used_textures` set; forward-window scans match the same texture from multiple shadows and corrupt the XML tree. Validate SVGs in a real browser (`scripts/svg_preview.py` uses Edge headless) — `QSvgRenderer` is too forgiving and hides this bug.

- **Superseded fix (#787)**: `ExportService._fix_svg_qt_texture_clipping()` paired each black "shadow" group with the next texture group in the written file and wrapped it in a `<clipPath>`. It matched one painter's output shape; the parametric roof and the glasshouse of #768/#769 did not have that shape, nothing was paired, and the family-garden example exported with the roof texture over 70 % of the drawing and zero `<clipPath>` elements. It was removed; the clip is now recorded below the painter.

### PF-CAN-14

- **Rule:** OGP scene Y and DXF Y both point up, so DXF export writes `dxf_y = scene_y` and import reads `scene_y = dxf_y * scale`, with no negation in either direction.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L302

- **DXF Y-axis: scene Y is already Y-up, no negation needed**: OGP scene uses Y-up (scene Y=0 = visual bottom). DXF also uses Y-up. The formula `dxf_y = canvas_h - scene_y` double-flips. Correct mapping: `dxf_y = scene_y`. Similarly for import: `scene_y = dxf_y * scale` (no negation).

### PF-CAN-15

- **Rule:** Text drawn with `painter.drawText()` inside `paint()` is mirrored on the Y-flipped canvas; draw it as a child text item with `ItemIgnoresTransformations` instead.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L328

- **`painter.drawText()` inside `QGraphicsItem.paint()` renders upside-down on the Y-flipped canvas**: The view applies `scale(zoom, -zoom)` for the CAD-style bottom-left origin (ADR-002). Text drawn directly inside a `paint()` method inherits this flip and appears mirrored. Symptoms: badge text reads as mirror image; positioning using `rect.bottom()` lands at visual *top* and vice versa. Fix: use a child `QGraphicsSimpleTextItem` (or a custom `QGraphicsItem` subclass) with the `ItemIgnoresTransformations` flag — Qt then draws the item in its own non-flipped pixel-coordinate system. Examples: bed name labels (`_label_item` in `garden_item.py`), succession badge (`SuccessionBadgeItem` in `garden_item.py`), compare-mode overlay labels (`canvas_scene.py`). Anchor at `rect.top()` (smallest scene-Y = visual bottom after flip) and extend the bounding rect upward (negative local Y) so the badge sits inside the bed.

### PF-CAN-16

- **Rule:** Anchor snap always wins over grid snap: `CanvasView.snap_point()` skips grid rounding while `_current_snap` is set, and any new snap layer needs an explicit composition rule.
- **Pinned by:** `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L352

- **Grid snap silently overrides anchor snap unless `CanvasView.snap_point` short-circuits** (Package A, ADR-020/021): Every drawing tool calls `self._view.snap_point(scene_pos)` inside its own `mouse_press`/`mouse_move`/`mouse_release`. The `CanvasView` dispatcher (`_maybe_apply_anchor_snap`) snaps the scene_pos to a midpoint/intersection/endpoint candidate *before* dispatching to the tool — but the tool's own `snap_point` call then rounds that anchor-snapped coordinate back to the nearest grid line (e.g. an edge midpoint at (175, 100) becomes (200, 100) on the default 50 cm grid). With grid snap on (the default), the new Package A snap modes silently lose. Symptom: midpoint/intersection glyph appears on hover but the committed vertex lands on a grid line, not the visible anchor. Root cause: anchor-snap and grid-snap are independently applied by two unrelated layers without composition rules. Fix: `CanvasView.snap_point()` short-circuits the grid rounding step when `self._current_snap is not None`. Anchor snap always wins on the click path; the bounds clamp still runs. Regression test: `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap` (uses a 350×100 rect with a midpoint at (175, 100) — deliberately not on the 50 cm grid). The single short-circuit site keeps this an explicit invariant rather than a side-effect of call ordering — if you find yourself adding a third snap layer, add an explicit composition rule before merging.

### PF-CAN-17

- **Rule:** A raster drawn in item-local space with `painter.drawPixmap()` comes out upside-down under the scene's Y-flip, so the item must flip the painter back about the rect centre first.
- **Pinned by:** `tests/integration/test_object_sprite_rendering.py::TestUprightOnCanvas`
- **Source:** #308
- **Status:** standing
- **Legacy:** b1faaa9 README L404

- **A pixmap blitted in item-local coordinates is upside-down on the canvas — and the plant sprites hid it for eight months** (Package 3a #308, owner manual test 2026-08-17): the view and every export (`export_service`, `pdf_report_service`, `scene_rendering`, `print_dialog`) draw the scene through `scale(1, -1)` (scene Y-up, §8.9), so `painter.drawPixmap(rect, pixmap)` inside `paint()` renders the image mirrored vertically. Every SVG-rendered object had been drawn that way since Phase 6; the plant sprites are radially symmetric *and* randomly rotated, the legacy furniture was near-symmetric, so nobody saw it — until the new fire pit's flames pointed **down** while the gallery thumbnail (rendered without the flip) pointed up. **Fix**: the furniture branches of `RectangleItem.paint` / `CircleItem.paint` flip the painter back about the rect centre (`translate(c); scale(1, -1); translate(-c)`) — the same idea as `background_image_item`'s flip transform and the text items' `setTransform(scale(1, -1))`. Pinned by `tests/integration/test_object_sprite_rendering.py::TestUprightOnCanvas`, which renders the wheelbarrow (heavy wheel end up, thin handles down) through the real flipped `scene.render` and asserts the top band carries more ink than the bottom, as the art does — the test fails with the exactly mirrored numbers without the fix. **Two lessons**: (1) any raster drawn in item space needs the local un-flip; only vector primitives and child items with their own transform are exempt; (2) a metric over `scene.render()` of a `CanvasScene` measures the opaque canvas background, not your item — render the item alone in a bare `QGraphicsScene` (`_render_item_alone` in that test file), which also exposed that an earlier "the tool draws an item that paints" assertion had been vacuous.

### PF-CAN-18

- **Rule:** Over its vertex budget a cached polygon paint draws only a cosmetic-pen outline, keyed on cache mode not `widget`, and every item copy carries both its serialized look and its pen and brush.
- **Pinned by:** `tests/integration/test_polygon_paint_bound.py`
- **Source:** #438, #441, #450, #469, #470, #472, #473
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1119-a-frame-sized-by-a-polygons-most-expensive-vertex-and-one-look-rule-for-item-copies-470472473)
- **Legacy:** b1faaa9 README L1119 (legacy 11.4.9)

### PF-CAN-19

- **Rule:** A textured fill is recoloured as a luminance map so a pale colour reads, the loader restores the stored look attributes, and round-trip tests compare rendered pixels in a non-default colour.
- **Pinned by:** `tests/integration/test_texture_forge_rendering.py::test_user_colour_recolours_without_flattening`; `tests/integration/test_texture_forge_rendering.py::test_texture_paints_with_visible_detail`; `tests/integration/test_item_appearance_roundtrip.py`
- **Source:** #438, #469, #470, #472, #473, #502
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1127-a-fill-colour-nobody-could-see-and-the-round-trip-test-that-asserted-the-wrong-thing-502-from-470472473s-manual-pass)
- **Legacy:** b1faaa9 README L1127 (legacy 11.4.10)

### PF-CAN-20

- **Rule:** A canvas texture may be softened but never replaced by a flat fill at any zoom, and the negative pin must sample the item's own `shape()` interior, since a mask on background reads as texture.
- **Pinned by:** `tests/integration/test_canvas_item_cache.py::TestTexturesAreNeverDropped`; `tests/integration/test_canvas_item_cache.py::TestTheMaskIsTheItem`
- **Source:** #409, #472, #501, #503
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1139-a-dead-optimisation-is-not-a-latent-feature-and-a-negative-pin-can-stop-noticing-503)
- **Legacy:** b1faaa9 README L1139 (legacy 11.4.11)

### PF-CAN-21

- **Rule:** Every writer that sets an item's style attributes or its live pen and brush sets both through `core/item_look.py`, so `style_gaps(item)` stays empty for every item that does not paint a sprite.
- **Pinned by:** `tests/integration/conftest.py::_every_item_says_what_it_paints`; `tests/integration/test_item_style_in_step.py`; `tests/integration/test_item_roundtrip_matrix.py::test_a_recoloured_rectangle_keeps_its_colour_through_load_save_load`; `tests/integration/test_item_roundtrip_matrix.py::test_a_restroked_item_keeps_its_stroke_through_load_save_load`
- **Source:** #441, #453, #470, #501, #502, #503, #523, #524, #525, #526, #527
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#2d-defects-the-bake-found)
- **Legacy:** b1faaa9 README L2537 (legacy 11.4.17)

### PF-CAN-22

- **Rule:** The sun study's 2D overlays lie on the ground surfaces (`on_ground`, drawn in `GROUND_Z_RANGE` by `_refresh_layer_z`) and under everything else; Arrange stays in a band.
- **Pinned by:** `tests/integration/test_sun_overlays_on_ground.py`; `tests/unit/test_object_height.py::TestLiesOnGround`
- **Source:** PR #584 owner manual pass, ADR-043 addendum "ground surfaces lie under the sun study"
- **Status:** standing
- **Legacy:** none (new entry)

The sun study's shadow overlay (`-500`) and hours-of-sun map (`-450`) were placed "below every layer item" in US-E3/E4, which reads well until a lawn is drawn: the owner's lawn hid both overlays entirely. A single overlay z cannot fix it — the layer bands interleave a lawn in one layer with a tree in another — so the ground surfaces move instead: an order-keeping map into a band under the overlays. Three things the first two cuts got wrong, each found by review: (1) the rule — "every object without a height" (the 3D view's ground rule) sank a cold frame under the raised bed it stood on, with no Height field to lift it back, so the band holds the garden's surfaces only; (2) Arrange still ranked over the whole layer, so a lawn stepped "forward" past a table and nothing moved; then, split by band while the drawing still normalized the whole layer, sending a lawn to the back moved a perennial on an in-ground bed under a tree — so ONE split (`CanvasScene._band_entries`) now feeds both the drawing and Arrange, and the layer is renumbered ground first; (3) a group is drawn in one slot, so a grouped lawn stayed above the overlays — a group of only surfaces now takes the band. The band follows reclassification after every command (a `plan_changed` hook was dropped: its `int` argument became `QTimer.start`'s delay). Saved files list ground surfaces first (display order). Lesson: two orders (rank and drawing) must come from one function, or a user acts on one and sees the other.

### PF-CAN-23

- **Rule:** A cached paint's `option.exposedRect` is the item's WHOLE rect, not the visible part. A styled line intersects it with the view's visible scene rect, in item coordinates, and passes that clip plus a `WalkBudget` to the one `PathStylePaint` walk; an export or minimap render disables caches first and keeps full detail.
- **Pinned by:** `tests/integration/test_path_style_paint_bound.py`; `tests/unit/test_minimap_widget.py`
- **Source:** #450
- **Status:** standing
- **Legacy:** none (new entry)

### PF-CAN-24

- **Rule:** Stacking z is derived only from ranks. An appended independent solid takes the derivation's own next fixed-grid value at add time (one derivation per layer, never one per add), a re-ordering add (parent bed, children, roof ridge, pre-ranked re-add, ground surface) re-derives synchronously, and the per-layer cache that seeds the next value holds a LAYER-BAND number, never the highest `zValue`, so a ground-only layer (whose z lives in `GROUND_Z_RANGE`) seeds the next solid correctly.
- **Pinned by:** `tests/integration/test_canvas_z_batch.py`; `tests/unit/test_plant_bed_zorder.py`; `tests/integration/test_arrange_z_order.py`
- **Source:** #450
- **Status:** standing
- **Legacy:** none (new entry)

### PF-CAN-25

- **Rule:** A per-command refresh is scoped to what the command can change: the lock badge refreshes only items carrying a FIXED constraint (or already showing a badge that may need clearing), and `CanvasScene._restack_ground_changes` classifies items only when `Command.changes_ground_band` is true. The base default stays true, so a new command is safe until it opts out with proof that it cannot change a type, a height or a group.
- **Pinned by:** `tests/integration/test_canvas_command_refresh.py`
- **Source:** #592
- **Status:** standing
- **Legacy:** none (new entry)

A 600-command loop of one-item `CreateItemCommand`s produced 360 600 `refresh_lock_badge` calls on a 600-item plan, each walking the whole constraint dict (`_is_item_fixed`), and `_restack_ground_changes` walked every item per command after #450 had already made the z derivation one-per-layer. The two loops are independent of what the command actually changed. The fix is the same shape in both places: derive the set of items whose badge can exist (`ConstraintGraph.fixed_item_ids()`), keep the badge-refresh loop to that set plus badges already on screen, and let a command declare itself ground-band neutral. The neutral flag defaults to true because a missing opt-out costs one O(items) scan; a wrong opt-out leaves a lawn in the solid band.

### PF-CAN-26

- **Rule:** A dense vertex-edit overlay stays sampled while the viewport remains inside the scene region the sample was taken over; a pan only translates the points, so the chosen indices keep their pairwise screen spacing. Re-sample on a zoom change, when the item's pose or geometry changes, or when the viewport leaves that region. Re-sampling on every `scrollContentsBy` walks every vertex.
- **Pinned by:** `tests/integration/test_dense_polygon_edit.py::test_a_pan_inside_the_sampled_region_does_not_resample`
- **Source:** #594
- **Status:** standing
- **Legacy:** none (new entry)

`_dense_overlay_indices` maps every vertex through the item's device transform to decide which 128 handles to show. #551 capped the number of scene ITEMS, not the CPU: a selected 16 384-vertex polygon (the loader's cap) re-sampled in ~98 ms per scrollbar step, against 0.01 ms when the sample is reused. The cache records the sampler's actual candidate region — the viewport grown by `DENSE_HANDLE_SPACING_PX` (24 px) — plus the zoom and the item pose; a pan inside that region is free, while a larger pan, a pose/geometry change or a zoom re-samples. The invariant that makes reuse correct is that translation does not change distances; the region must be the one the sampler really tested, not a larger convenience box.

### PF-CAN-27

- **Rule:** Never paint a texture with a pen. A `QPen` whose brush is a texture is right on screen, in PNG and in PDF, but `QSvgGenerator` writes a pen as its colour, and a texture brush's colour is black. Fill the outline instead: `QPainterPathStroker` (width, cap, join) and `drawPath(stroker.createStroke(path))` with `NoPen` and the texture brush. The SVG then carries a pattern fill.
- **Pinned by:** `tests/integration/test_path_style_export.py::test_no_style_exports_as_a_black_bar_to_svg`
- **Source:** #388 (senior review of the owner pass)
- **Status:** standing
- **Legacy:** none (new entry)

The owner pass made gravel and dirt paths their fill textures, drawn as a texture-brush pen along the line. Every raster and PDF check passed, and the ground bake matched the canvas, but every gravel and dirt path came out of an SVG export as an opaque black bar, as wide as the path. `path_style_paint` serves the canvas, the ground bake, the minimap and every export, and its tests covered raster output only. The test now exports every `PathFenceStyle` to SVG, and the textured styles also to PNG and PDF.

### PF-CAN-28

- **Rule:** Exclude underpaint from a translucent textured path; rim masking must follow the device transform, remain bounded and preserve bends and self-crossings.
- **Pinned by:** `tests/integration/test_translucent_path_rims.py`
- **Source:** #617; ADR-065
- **Status:** standing
- **Legacy:** none (new entry)

A pair of odd-even stroke outlines is insufficient: Qt stroke contours overlap at bends. Exact subtraction was measured at 6.6 s for 4,096 points. Use DestinationOut on bounded device tiles for translucent rims and retain the opaque fast path. Textures remain pattern fills for SVG/PDF.

### PF-CAN-29

- **Rule:** A parenting clamp must follow the GEOMETRY, not only the link: a plant renders above the plant-parent whose outline contains its stable centre, linked or not. When a visual guarantee can be satisfied by a category accident (a ground surface sitting under everything), check the guarantee on the categories where the accident does not apply.
- **Pinned by:** `tests/integration/test_plant_above_parent_stacking.py::test_a_parent_drawn_around_a_standing_plant_keeps_it_on_top`; `tests/integration/test_plant_above_parent_stacking.py::test_a_plant_moved_into_a_bed_is_raised_by_the_command`; `tests/integration/test_plant_above_parent_stacking.py::test_a_healthy_layer_asks_no_shape_question`; `tests/integration/test_plant_above_parent_stacking.py::test_the_scan_builds_each_parent_shape_once`; `tests/perf/test_nfr_budgets.py::TestNfrPerf01ContainmentScanBudget`
- **Source:** #629 (owner manual pass of #627)
- **Status:** standing
- **Legacy:** none (new entry)

`core.stacking.normalize_order` has clamped a CHILD immediately above its parent since
#338, and the child relation it read was `parent_bed_id`. Drawing a bed AROUND a standing
plant makes no link (#443), so the plant stayed below the new parent: hidden in 2D, drawn
on the soil in 3D, and its sun badge hidden with it. The in-ground `GARDEN_BED` looked
immune because it has no height and sorts into `GROUND_Z_RANGE` under everything — so the
owner's "plants are always on top of beds" held only for the one type whose guarantee came
from the ground band. The same bed with a stored height would have hidden the plant too.

Measured before the fix: a plant added first and a `RAISED_BED`, `CONTAINER`,
`CONTAINER_ROUND`, `WALL_PLANTER` or `TRELLIS` drawn around it left z(plant) 0.00001
against z(parent) 0.00002. After: the clamp's parent is the link, or the smallest
plant-parent containing the plant's centre; `_stack_entries` is still the one place that
derives it, and a plant-parent's arrival re-derives the layer only when it CAPTURES a
plant (`_parent_captures_a_plant`), which kept 600 childless bed adds at 0.24 s instead of
2.12 s.

Two traps to keep: `Command.changes_containment` is NOT the same gate as
`changes_ground_band` - the commands that change containment (move/resize/rotate/vertex)
are exactly the ones that set the ground-band flag False; and the per-command check must
compare the plant's z against the parent the DERIVATION names (`_derived_plant_parent`) -
not "any parent that contains it", which never settles once an outer bed is arranged above
an inner one, and not a second copy of the rule, which drifted into rebuilding each
parent's shape per (plant, parent) pair (1 661 ms on the adversarial 200-plant plan, 133 ms
with the pass's shape cache, 8 ms at 6 vertices). That rebuild is why the pin is
**counted**, not timed: five concave beds over twenty plants in the notch must build five
paths, and a per-pair rebuild fails at 100 - a wall-clock budget on small beds cannot see
the difference, and a budget that cannot fail is not a pin.

### PF-CAN-30

- **Rule:** Offset path inner bends intersect before the corner and create self-intersecting loops if segment endpoints are connected naively; trim overlapping segments to the intersection at acute inner bends ($offset \cdot (\vec{u}_1 \times \vec{u}_2) > 0$). In paved path rendering, base fill pen join must match border chord (`BevelJoin`) to eliminate miter spikes.
- **Pinned by:** `tests/unit/test_path_style_paint.py`
- **Source:** #605
- **Status:** standing
- **Legacy:** none (new entry)

Polyline offset generation computes parallel segments for each segment of a polyline.
At acute inner bends, parallel segments intersect before the corner vertex; connecting
endpoints directly creates a reverse loop and crossing spikes across the interior of
the path. Trimming inner segments to their geometric intersection produces clean bends.
For paved paths with decorative borders, the fill pen must also use `BevelJoin` to
harmonize with the border chord join.

The trim decision uses finite segment bounds, not an angle cutoff: a 175-degree turn
with sufficiently long legs still has a valid inner intersection. Use a directed-line
cross product rather than `1 + dot` near a reversal, and discard zero-length segments
instead of inventing their normal. The painter/relief parity matrix pins both turn
directions through 179.9 degrees.

### PF-CAN-31

- **Rule:** Rounded gravel relief follows the painted stroke rim, including caps; nominal analytical caster footprints cannot prove decorative rim coverage or exclusion.
- **Pinned by:** `tests/integration/test_gravel_rim_relief.py`; `tests/unit/test_scene3d_l4_surfaces.py`
- **Source:** #605, PR #645 owner pass
- **Status:** standing
- **Legacy:** none (new entry)

Two offset rails joined by chords lay over the gravel texture at an outer bend,
while a nominal square/butt footprint gate passed them. Reuse the round stroke
outline already used for lawn cut-outs; sweep the bevelled profile inward and
retain the analytical caster unchanged. Check both coverage of outer arcs/caps
and exclusion from the texture interior against Qt's independent round stroke.

### PF-CAN-32

- **Rule:** A relationship other surfaces read must be reconciled by EVERY edit path that can invalidate it, through one mutator and one geometric rule. Recompute membership inside the move/resize/rotate/vertex/copy command, so undo restores it in the same step — never at one call site; and scope a bed edit to the plants that bed can affect, or it will overrule a plant's deliberate link to another bed.
- **Pinned by:** `tests/integration/test_bed_membership_reconciliation.py`; `tests/integration/test_scene3d_base_stacking.py`
- **Source:** #443, PR #649
- **Status:** standing
- **Legacy:** none (new entry)

Three evaluators and four call sites looked like "the app reconciles
membership". Every other path — arrow keys, a typed coordinate,
align/distribute, arrays, a mirror copy without its bed, a bed's
resize/turn/vertex edit, a bed moved by a typed coordinate — silently kept a
stale link, and the Properties panel, the soil-mismatch and companion logic
and the diagnostics followed it. The tell was that the lift and the link asked
different points, so an antagonist badge could make them disagree about one
plant. Ask one point (`standing_point`), apply the rule in the commands
themselves, and make a copy drop the link it was serialised with.

The review round added the paths a command-level test cannot see: the
Properties panel's typed resize registered the command without its
`notify_applied` hook (undo/redo asymmetry), and the agent's vertex tools
execute a command with no drag-release handler at all. Test the real entry
point, not the command a caller builds. It also proved the scoping rule: a
scene-wide recompute on a bed edit unlinked a plant from a far-away bed it had
been deliberately linked to.


### PF-CAN-33

- **Rule:** An item's derived centre is `rect().center()`, never `width/2, height/2`: a circle's rect is built at `centre - radius`, so its local origin is not `(0, 0)` and the half-size value names a different point.
- **Pinned by:** `tests/unit/test_geometry_identity.py::test_circle_handle_resize_keeps_centre_and_rect_in_step`; `tests/unit/test_geometry_identity.py::test_circle_handle_resize_survives_save_and_reload`
- **Source:** #657
- **Status:** standing
- **Legacy:** none (new entry)

`CircleItem._after_resize_geometry()` recomputed `_center` as `QPointF(width/2, height/2)`.
The shared resize primitive preserves the rect's local origin (the handle path
rebuilds `QRectF(init_rect.x(), init_rect.y(), w, h)`), and a circle's rect
normally starts at `centre - radius`, so an interactive resize stored a centre
the visible drawing did not share: measured 150/150 stored against 550/550
visible on master `f4e5060`. The canvas still looked right because the primitive
anchors the scene geometry; the serializer writes `pos + centre`, so the object
jumped on reload and every consumer of `item.center` (shadow, 3D footprint) read
the wrong point. The 4-rotation x 8-handle matrix is what exposes it: at
rotation 0 the visual anchor masks the error. `EllipseItem` is the control - it
reads the rect directly and never kept a derived centre.


### PF-CAN-34

- **Rule:** A derived visual belongs to the item that owns it: bake it into that item's geometry (or its own serialized state), never add a second free scene item. A separate decoration does not follow the host when it moves or groups, is not deleted with it, and is not part of its undo/save.
- **Pinned by:** `tests/integration/test_fillet_chamfer.py::test_fillet_polyline_bakes_the_arc_into_the_host`; `tests/unit/test_geometry_identity.py::test_a_raised_bed_converts_to_a_garden_bed_polygon`; `tests/unit/test_fillet_geometry.py::test_sample_arc_points_lie_on_the_arc_between_the_tangent_points`
- **Source:** #668 manual-test follow-up, PR #672
- **Status:** standing
- **Legacy:** none (new entry)

The fillet tool built two objects: a polygon whose corner was cut straight (the
old "5-vertex polygon") and a free-standing `ArcItem` drawn between the tangent
points. The fill therefore never followed the arc, and the moment the owner moved
the bed the arc stayed at its old scene position while the polygon moved: the
"rounded" corner came apart into an unfilleted chamfer, exactly what the manual
test reported. The same rebuild copied the rectangle's `object_type` blindly, so
a raised bed became a `PolygonItem` that still said `RAISED_BED` — the Properties
panel showed "Polygon" (its dropdown does not offer that type for polygons)
while the bed kept its soil depth, plants and records, and the wooden frame was
gone.

Bake the derived geometry into the item: the tangent points and the sampled arc
are vertices of the host (`FILLET_ARC_TOLERANCE_CM = 0.02 cm`), so one move,
group, save, delete or undo carries the whole picture. When a shape changes class
(rectangle → polygon), map its type to a legal member of the new class (raised bed
→ garden bed, generic rectangle → generic polygon) and refuse the edit when no
legal mapping exists; never leave an item in a type/shape combination the panel
cannot represent. A real type change also takes the new type's fill pattern (a
converted raised bed shows the garden bed's soil, not the raised bed's solid
fill) while keeping the user's colour; a same-type edit keeps the user's pattern.


### PF-CAN-35

- **Rule:** An open path has no inside: offsetting a polyline creates a parallel LINE on the cursor's side, never a filled polygon. Clipper-1 returns the stroked band outline for an open path; take the outline as an area only after proving the source is closed.
- **Pinned by:** `tests/integration/test_offset_tool.py::test_offset_polyline_result_is_a_parallel_line`; `tests/integration/test_offset_tool.py::test_offset_polyline_miters_a_right_angle_corner`
- **Source:** manual-test follow-up 2026-11-01, PR #672
- **Status:** standing
- **Legacy:** none (new entry)

The owner offset a fence, clicked, and asked what the rounded brown band on the
ground was supposed to be. Nothing: pyclipper's open-path offset returns the
outline of the stroked band (both sides joined at the ends), and the tool wrapped
that contour in a `PolygonItem`, filled it with the fence's style and left it in
the scene. A line has no inward/outward side to choose by containment either —
`shape().contains()` is only true inside the stroked band, never on one side of
the line — so the "inward" rule was meaningless.

Offset a polyline segment by segment on one side, with miter joins (bevelled past
a 4× distance limit), and choose the side whose points are nearest the cursor.
The result keeps the source's type and line look (`capture_line_look` /
`apply_line_look`) and is a `PolylineItem`, so it reads as a second fence/path
and exports as a line. Closed shapes continue to use the area offset.

### PF-CAN-36

- **Rule:** A `QGraphicsItemGroup`'s child reports `isSelected() == True` while only the group is selected (Qt propagates selection into group children). An operation that acts on "the selection" must filter to the level it is defined at — group/ungroup count only TOP-LEVEL groups (`parentItem() is None`) — or one gesture dissolves nested levels.
- **Pinned by:** `tests/integration/test_group_context_menu.py::test_nested_groups_ungroup_one_level_at_a_time`; `tests/integration/test_group_context_menu.py::test_two_groups_ungroup_in_one_undo_step`
- **Source:** #674
- **Status:** standing
- **Legacy:** none (new entry)

Merging Group/Ungroup into every item's context menu had to combine "dissolve every
selected group" with the issue's "one nesting level per gesture" rule. The first
version filtered `scene.selectedItems()` for `GroupItem` and built one
`UngroupCommand` per hit. A nested test failed: after grouping an inner group and a
shape into an outer group, the inner group still reported selected (Qt mirrors a
group's selection state on its children, even though `GroupCommand` had called
`setSelected(False)` on it), so one click dissolved the outer *and* the inner
group. The first fix filtered only GroupItem children, not every child, so the
menu still counted the plain members Qt reports as selected and offered Group on a
single selected group; a second grouping then emptied the first. Both filters now
keep only `parentItem() is None` for EVERY item (`groupable_selection` and
`ungroupable_groups`), and `ungroupable_groups` still excludes a smart symbol. A
child's `isSelected()` is a fact about its group, not evidence that the user chose
the child.

### PF-CAN-37

- **Rule:** Two item classes that can represent the same semantic object must render it through ONE shared paint path. Making a rectangle convertible into a HOUSE also obliges its `paint()` to take the ridge-aware tile fill; otherwise the converted house is a flat, wrongly-lapping roof beside a correctly-drawn one.
- **Pinned by:** `tests/unit/test_roof_tile_orientation.py::test_a_converted_rectangle_paints_the_identical_roof`; `tests/unit/test_roof_tile_orientation.py::test_tiles_lap_away_from_the_ridge`
- **Source:** #690, PR #713 manual test 2.1 (2026-11-03)
- **Status:** standing
- **Legacy:** none (new entry)

`ChangeObjectTypeCommand` gave a converted rectangle a real `ROOF_RIDGE`, and
`RectangleItem` followed it on move/resize/rotate — but `RectangleItem.paint()`
still called `super().paint()`, the plain `QBrush` fill. The 2D roof therefore
mirrored nothing at the ridge and its tiles lapped toward it, while a
natively-drawn polygon house mirrored the fill across the ridge and lapped
away. The 3D records were already identical for the same outline (measured:
same `ridge` param, slope and z-range), so the only defect was the one missing
paint branch. The fix extracts the polygon's production painter into
`ui/canvas/items/roof_paint.paint_roof_with_ridge` and calls it from both
classes; a converted rectangle and a drawn house now render byte-identically
over eight orientations.

### PF-CAN-38

- **Rule:** A derived top-level sibling whose owner can be grouped (a HOUSE's `ROOF_RIDGE`) must re-run the stacking derivation when the owner joins or leaves a group; the normalizer resolves the owner inside the group to the GROUP, and only that refresh puts the sibling above the group's fill.
- **Pinned by:** `tests/integration/test_house_roof_ridge.py::test_grouping_a_house_lifts_its_ridge_above_the_group`; `tests/integration/test_house_roof_ridge.py::test_moving_a_group_to_another_layer_moves_a_nested_houses_ridge`
- **Source:** #690, PR #713 manual test 2.7 (2026-11-03)
- **Status:** standing
- **Legacy:** none (new entry)

`GroupCommand.execute` added the group (top of its layer) and then moved the
house into it. The ridge is not a Qt child, so it kept its pre-group z — above
the house, below the new group — and the group's tile fill covered all but its
ends. Delete + undo looked correct because those paths already call
`_update_items_z_order`. Grouping now does too: `_stack_entries` already maps a
group child's id to the group, so the normalizer puts the ridge immediately
above it. `UngroupCommand` keeps the mirror-image refresh.

### PF-CAN-39

- **Rule:** Selecting with Shift AND Ctrl must go through the app's own toggle path (`SelectTool._selectable_under` + `setSelected`), not Qt's default press; and a selectable item under the cursor must be found with `QGraphicsScene.items(point)`, never `itemAt` alone — `ItemIgnoresTransformations` items (journal pins) are invisible to `itemAt` under the Y-flipped view.
- **Pinned by:** `tests/integration/test_group_context_menu.py::test_a_pin_and_a_shape_multi_select_then_group`
- **Source:** #674, PR #713 manual test 4 (2026-11-03)
- **Status:** standing
- **Legacy:** none (new entry)

Qt's default Ctrl press replaced the selection, so a selected journal pin was
cleared by Ctrl+clicking a rectangle; Shift already worked through
`SelectTool`. Both modifiers now use the same toggle path. The pin itself is
also invisible to `scene.itemAt(scene_pos, view.transform())` because
`ItemIgnoresTransformations` is not handled there while the view's m22 is -1;
the tool's own walk (`scene.items(scene_pos)`) finds it. The canvas-level hit
test that makes the pin itself selectable and draggable is PF-CAN-40.

### PF-CAN-40

- **Rule:** `QGraphicsScene.itemAt` never returns an `ItemIgnoresTransformations` item (measured on Qt 6.12, with or without the canvas Y flip), so a constant-screen-size item such as a journal pin needs its own hit test. The view must also drive the interaction it owns - select/toggle, drag with one undo step, double-click - because Qt's press path cannot start it.
- **Pinned by:** `tests/integration/test_garden_journal.py::TestPinPointerInteraction`
- **Source:** #674, PR #713 manual test 4; #728 (2026-11-04)
- **Status:** standing
- **Legacy:** none (new entry)

The pin was only selectable from the Journal panel. `scene.items(pos)` finds it,
but `scene.itemAt(pos, transform)` and `QGraphicsView.itemAt` return None even
with an identity transform, so Qt's press cleared the selection and started a
rubber band instead of dragging. `CanvasView._journal_pin_at` now performs the
same walk (stopping at a drag handle or another selectable item above the pin),
and `_begin_pin_interaction`/`mouseMoveEvent`/`mouseReleaseEvent` select, toggle,
drag and commit one `MoveItemsCommand`; double-click opens the note. A pin inside
a group is deliberately not intercepted - the group remains the click target.

### PF-CAN-41

- **Rule:** A thumbnail or export pass that masks overlay items must suppress their PAINT, not their visibility. Qt deselects an item when it is hidden, so `setVisible(False)`/`True` around a periodic render clears the user's selection; `ItemHasNoContents` masks paint without changing visibility, selection or the plan revision.
- **Pinned by:** `tests/unit/test_minimap_widget.py`; `tests/integration/test_garden_journal.py`
- **Source:** #674, PR #713 manual test 4 (2026-11-04)
- **Status:** standing
- **Legacy:** none (new entry)

The minimap hid every `ItemIgnoresTransformations` or high-z item to keep
handles, labels and the journal pin out of its thumbnail, then restored them.
A journal pin is exactly such an item, so every thumbnail refresh (100 ms
throttled, and triggered by the drag itself) hid and re-showed it. Qt deselects
a hidden item; a pin drag therefore lost its grip milliseconds after it began,
and a group containing a pin lost the propagated selection. `ItemHasNoContents`
suppresses the paint while the item stays visible and selected. Export Service
already preserved the selection around its own hide/restore; the minimap now
does not need to.

### PF-CAN-42

- **Rule:** A bespoke drag path must end through one finalizer on every exit - release, a release lost outside the viewport, and the next press - and a guard that suppresses a move because a `ResizeItemCommand`/`RotateItemCommand` already exists must be scoped to the gesture that created it (compare the undo depth at drag start), never to the stack top.
- **Pinned by:** `tests/integration/test_garden_journal.py::test_a_lost_release_is_committed_on_the_next_move`; `tests/integration/test_garden_journal.py::test_a_pin_drag_after_a_resize_is_its_own_undo_step`
- **Source:** #674, final review of PR #713 (2026-11-04)
- **Status:** standing
- **Legacy:** none (new entry)

The journal-pin drag had two exits that bypassed `_finalize_drag_move`: a
`MouseMove` with no buttons (the release happened outside the viewport) cleared
the state, and the next left press overwrote the start positions. Separately,
`_finalize_drag_move` skipped any drag when the stack top was a Resize/Rotate
command, even when that command came from an earlier gesture - so a pin dragged
after a resize moved without an undo entry. `_finish_pin_drag()` is now the one
end path, and `_drag_start_undo_depth` tells the guard whether *this* gesture
created the command.

### PF-CAN-43

- **Rule:** A rect that depends on anything outside the item (a plant's on the plan date) reads that input through a value changed only AFTER `prepareGeometryChange`. Qt's BSP index takes an item out of the leaves of the rect it has at that call; told after the rect moved, the old leaves keep the pointer, and it dangles once the item is removed and destroyed.
- **Pinned by:** `tests/integration/test_plan_timeline.py::test_a_new_date_tells_qt_about_a_plants_rect_while_it_is_still_the_old_one`; `tests/integration/test_plan_timeline.py::test_opening_a_plan_after_the_date_moved_does_not_crash`
- **Source:** #390 (Phase 17 L6), found by the 3D review after a time-lapse; present on v1.36.0.
- **Status:** standing
- **Legacy:** none (new entry)

`boundingRect()` of a plant read `scene.plan_date` live, and `refresh_timeline` called
`prepareGeometryChange` from the clock's signal, when the rect had already moved. One date step later
than a plant's planting date, in plain plan view, was enough: the next plan opened died in the
next paint with an access violation, an abort or `0xC0000409`, wherever that paint happened to be
(the minimap's `scene.render`, or `CanvasView.paintEvent`), with nothing on stderr. A date before
the planting date survived, by luck of the hidden plants being re-indexed. `CanvasScene.clear()`
would have hidden it too, because it empties the index first: the load path deliberately removes
document items one by one (`_is_project_document_item`), and each removal leaves its old leaves
behind. `NoIndex` survives, which is the way to tell a stale index from anything else; it is not
the fix. The fix is `CanvasScene.drawn_plan_date`, which moves between the announcement and the
repaint, so the announcement still sees the old rect.

### PF-CAN-44

- **Rule:** A sprite whose natural aspect is opposite its item's is TURNED a quarter, never stretched; the 3D builder must build the same turn from the same rule.
- **Pinned by:** `tests/unit/test_sprite_orientation.py`; `tests/integration/test_object_sprite_rendering.py`
- **Source:** #776
- **Status:** standing
- **Legacy:** none (new entry)

A wheelbarrow's sprite is 60 x 140 cm; drawn into a 140 x 60 rectangle it was rendered into that rect and squashed, and the 3D builder stretched its own model into the same wrong frame. The fix is `core/sprite_orientation.py`: `NATURAL_SIZE_CM` + `sprite_turn_deg` (only opposite aspects turn; near-square art or targets never do). The 2D renderer renders at the swapped size and rotates the pixmap; `kit.object_box` stores the swapped build extents and `kit.placed` turns the mesh by -90 deg about z. The 2D/3D agreement is the point: changing only one of them would have made the picture and the model disagree about which way the wheelbarrow faces.

### PF-CAN-45

- **Rule:** Every ridge path asks one predicate (`is_ridge_bearing_type` / `is_ridge_bearing_kind`), never `object_type == HOUSE`; adding a ridge-bearing kind means adding it to `RIDGE_BEARING_KINDS` and nothing else.
- **Pinned by:** `tests/integration/test_parametric_structures.py::TestGreenhouseRidge`; `tests/integration/test_house_roof_ridge.py`
- **Source:** #768
- **Status:** standing
- **Legacy:** none (new entry)

A HOUSE's linked `ROOF_RIDGE` is derived geometry created, moved, copied, deleted and sanitised by a dozen call sites. Teaching GREENHOUSE to be a building meant touching every one; a single missed `== HOUSE` would have left a greenhouse ridge that did not follow a move, a copy without its own ridge, or a load that dropped the link. The predicate lives in `core.roof_style.py` (Qt-free, kind names) and `core.object_types.is_ridge_bearing_type` (enum); `ChangeObjectTypeCommand` uses it for both the execute and undo halves, and `apply_ridge_look` gives a greenhouse its aluminium finish (and a house its brown) on build, type change and undo.

### PF-CAN-46

- **Rule:** A `QGraphicsItemGroup` child cannot be selected independently: selecting it selects the group, and its resize/vertex handles do not receive a usable drag. Group drill-down is therefore a VIEW-LEVEL logical focus (`drill_down_item` / `effective_selection`), never a reparent or a temporary ungroup.
- **Pinned by:** `tests/integration/test_group_drill_down.py::test_second_click_focuses_the_member_then_outside_restores_the_group`; `tests/integration/test_group_drill_down.py::test_the_properties_panel_shows_the_member_and_disables_its_layer`
- **Source:** #771, ADR-075
- **Status:** standing
- **Legacy:** none (new entry)

Qt 6.12 routes `child.setSelected(True)` through the group: `scene.selectedItems()` returns only the group even though the child's `isSelected()` is true. A `QGraphicsItemGroup` child's `ResizeHandle` press is swallowed by the group, and a double-click does not reach the child's vertex-edit handler. Detaching the child with `removeFromGroup` on drill-down and re-adding it on exit makes handles work but changes its parent frame; commands captured while detached store local `pos()`/`rect()` values, so undo after moving or rotating the group restores the wrong place. The vetted path keeps membership: the group stays selected, `effective_selection()` supplies the member to every panel, body drags and arrow keys convert scene deltas through `_delta_in_parent_frame`, and the view replays the member's handle drag through `begin_drag` / `apply_drag` / `end_drag`. The member's layer/cut/delete operations are refused until the focus clears.

### PF-CAN-47

- **Rule:** `QPainterPath.intersects` is true for a boundary touch, not only for an interior crossing. A geometry operation that means "crosses" must prove interior overlap — for a segment, split it at its outline crossings and require an interval midpoint strictly inside — or a snapped corner pick silently cuts the shape it only grazed.
- **Pinned by:** `tests/unit/test_shape_split.py::test_a_touch_is_not_a_crossing`; `tests/integration/test_split_shapes.py::test_a_line_that_only_touches_a_corner_does_not_split`
- **Source:** #664, PR #783, ADR-075 addendum
- **Status:** standing
- **Legacy:** 11.4.22 (new entry)

The split tool's first crossing predicate was `path.intersects(segment)`. Qt answers
True when a segment ends on the outline, runs along an edge, or is tangent to it, so
a line whose first pick snapped to a bed's corner and whose second pick went away
from it removed the bed and created two pieces. The same answer is right for a
boolean *touch* test and wrong for a knife. `segment_crosses_path` now sorts the
segment's parameters at its crossings with the flattened outline, samples each
interval between them, and accepts the segment only when points offset to BOTH
sides of the line are inside; a boundary-aligned segment has one side outside.
`tests/unit/test_shape_split.py` covers the outward corner/edge/tangent starts and
the true corner-to-corner crossing; the integration test reproduces the
corner-snap cut that used to happen.

### PF-CAN-48

- **Rule:** `QGraphicsItem.setFlags` deselects any item that reports `isSelected()` without being selectable, and a descendant that already existed when its parent joined a `QGraphicsItemGroup` reports its GROUP's selection: one flag set on such a handle inside a selected group unselects the whole group. Code that toggles a flag on arbitrary scene items (the minimap's overlay suppression) must test exactly that condition and hide those items by opacity.
- **Pinned by:** `tests/integration/test_group_drill_down.py::test_the_running_app_keeps_the_member_focused_past_a_minimap_refresh`; `tests/integration/test_group_drill_down.py::test_the_minimap_does_not_paint_a_focused_members_handles`; `tests/integration/test_group_drill_down.py::test_a_focused_member_leaves_the_idle_window_quiet`
- **Source:** #771, PR #783 (manual test 8), ADR-075 addendum 2
- **Status:** standing
- **Legacy:** none (new entry)

Group drill-down (PF-CAN-46) keeps the group as the Qt selection and shows the
focused member's handles. In the real window the focus lasted a split second: the
minimap re-renders 100 ms after any scene change and suppresses every overlay item
for its thumbnail with `setFlag(ItemHasNoContents, True)`. Qt's `setFlags` ends
with "if the item is not selectable but is selected, deselect it"; for a group
descendant `isSelected()` answers for the group and `setSelected(False)` is routed
to the group, so the group lost its selection and the view retired the drill-down.
Measured on Qt 6.12 with three items: a flag set on a non-selectable child of a
selected group unselects the group and emits `selectionChanged`; `setOpacity` does
neither; a selectable child (a grouped journal pin) is not affected, which is why
the earlier group test in `test_garden_journal.py` stayed green. The precondition
is also measured: only a child that existed when its parent was added to the group
reports the group's selection; a child created afterwards reports False and its
flags are harmless. A member's handles are created when it is first selected, and
a user selects the members in order to group them, so the real workflow always
meets the precondition - while a group loaded from a file, whose members were
never selected, does not. The pins therefore build their group through
`_group()`, which selects first; a pin that grouped unselected members would pass
on the broken code. The minimap's test is Qt's own (`not selectable and
isSelected()`), so it is right in both cases. The minimap
keeps `ItemHasNoContents` for everything else (PR #713: hiding deselects) and
makes exactly these descendants fully transparent for the render, restoring the
opacity they had. The idle-quiescence pin shows the opacity round trip does not
restart the #305 render loop. No bare-canvas test could have caught this: the
canvas fixture has no minimap, and the one running-app test called
`begin_group_drill_down` directly instead of clicking.

### PF-CAN-49

- **Rule:** Qt keeps every item's `DeviceCoordinateCache` picture in the process-wide `QPixmapCache`, whose default limit is 10 MB; a canvas raises it (`ui/canvas/item_cache.ensure_item_cache_budget`, 256 MB) or its item caches thrash and every repaint paints the items again. Setting a cache mode proves nothing: count the paints.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py::TestPanIsCheap`; `tests/integration/test_sun_overlay_cache.py::TestRasterisedOncePerSolve`; `tests/perf/test_sun_overlay_repaint.py`
- **Source:** #784
- **Status:** standing
- **Legacy:** none (new entry)

The family-garden example needs 17 MB of item caches in a 1453 x 898 viewport (one lawn alone is 5.2 MB), so with the default limit Qt evicted and re-painted on every frame: 49 ms for a repaint that is 8 ms of blits, 143 ms for a 40-px pan. A picture larger than the whole limit (a lawn on a 4K display is 33 MB) was never kept at all. The first attempt at #784 set the sun overlay to `DeviceCoordinateCache` and measured no change whatsoever (146 ms against 152) — the overlay's 5 MB picture was evicted by the next item's. NFR-PERF-01's reference plan did not show it because its 990 items are small. The limit is a ceiling, not an allocation. Details and numbers: §8.37.

### PF-CAN-50

- **Rule:** A bitmap drawn through a painter is rasterised for THAT painter: ask `core/raster_resolution` (device scale of the painter, rounded up to a power of two, never below 1) through `paint_plant` / `paint_furniture` / `brush_for_painter`, never hand a renderer the item's size in centimetres as pixels, and never rasterise a sprite whole when it would exceed 1024 px a side.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py`; `tests/unit/test_raster_resolution.py`; `tests/unit/test_sprite_raster.py`; `tests/unit/test_fill_pattern_levels.py`
- **Source:** #785
- **Status:** standing
- **Legacy:** none (new entry)

`render_plant_pixmap(diameter=...)` and `render_furniture_pixmap(width=..., height=...)` take pixels; the item paints passed centimetres, so every sprite was 1 px per cm and anything above 100 % zoom, on a high-density display or in a 300-dpi export was an enlarged bitmap. The resolution cannot be the item's: one item is painted by the canvas, an export, the minimap and the Agent API render at different scales. Three traps on the way: `QPainter.worldTransform()` leaves out the device pixel ratio (`deviceTransform()` has it); a pixmap drawn into an item-space rectangle under the canvas's Y-flip is mirrored (lay a device-space picture down with the device transform made the identity); and a level below 1 is not "sharper", it changes how a texture reads when zoomed out (`MIN_LEVEL`, an owner's decision). A defect of this kind is proportional to zoom and to rotation — test at 400 % and 1000 %, rotated, and against the same interior at 100 % enlarged. §8.9.14.

### PF-CAN-53

- **Rule:** The scene is never painted into a `QSvgGenerator` directly: it is painted into the recording engine of `services/svg_export.py` and replayed, because the generator drops a brush's own transform and a pixmap's source rectangle, and writes a clip either not at all or as a staircase.
- **Pinned by:** `tests/integration/test_svg_export_fidelity.py`
- **Source:** #787
- **Status:** standing; narrative in [debug-verbose: Case study: the SVG export flooded the plan with roof tiles — the generator drops clips, brush transforms and source rectangles (#787, fixed 2026-11-09)](../../../.claude/skills/debug-verbose/references/219-case-study-the-svg-export-flooded-the-plan-with-roof-tiles.md#case-study-the-svg-export-flooded-the-plan-with-roof-tiles--the-generator-drops-clips-brush-transforms-and-source-rectangles-787-fixed-2026-11-09)
- **Legacy:** none (new entry)

Measured on Qt 6.12. `QSvgGenerator` (1) writes a `TexturePattern` brush without its `transform()` — the roof's mirrored half and every per-object pattern angle or scale were lost; (2) ignores the source rectangle of `drawPixmap`; (3) writes no clip in SVG Tiny 1.2 mode, and in SVG 1.1 mode writes the intersection of two clips as a one-unit staircase, because `QPainter.clipPath()` falls back to an integer region as soon as two clips are stacked — and `scene.render()` always stacks its own. `QSvgRenderer` ignores `clip-path` altogether. The recorder is a `QPaintEngine` with the generator's feature set; it keeps every draw call with its state and its exact clip, and the replay writes a clipped fill and a clipped stroke as their outlines cut to the clip, and moves a brush transform into the world transform. Only a clipped picture or clipped text keeps a real `<clipPath>` (exact, SVG 1.1). An item's `paint()` needs no SVG knowledge, so a new painter cannot bypass it — the test paints one that nobody taught. A font from a text layout carries no record of what was set on it; `QPainter.setFont` then resolves everything from the device default, so the replay rebuilds the font by hand (a 28 pt Arial note was written as the 9 pt application font).

### PF-CAN-54

- **Rule:** A `paint()` clips with `Qt.ClipOperation.IntersectClip`, never with the default `ReplaceClip`: the painter it is handed already carries the clip of a print tile or a report frame, and replacing it paints on the margin.
- **Pinned by:** `tests/integration/test_pdf_report_pages.py::test_no_scene_painter_replaces_the_clip_it_was_handed`; `tests/integration/test_pdf_report_pages.py::test_a_print_tile_paints_nothing_on_its_margin_or_footer`
- **Source:** #788
- **Status:** standing
- **Legacy:** none (new entry)

`QPainter.setClipPath(path)` and `setClipRect(rect)` REPLACE the painter's clip unless told to intersect it. On the canvas that is invisible: the view clips with a system clip the painter does not own. In `scene.render()` the target rectangle is an ordinary painter clip, and the sun-shadow overlay and the roof replaced it with their own — so a 1:50 printout painted the shadows of the whole garden across each sheet's margin and footer. Both now intersect, an AST test rejects any `setClipPath` / `setClipRect` / `setClipRegion` in `src/` that does not name `IntersectClip` (three non-scene files are listed with their reason), and the printout sets the tile as an explicit clip of its own.
