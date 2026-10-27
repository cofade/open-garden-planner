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

- **Rule:** Outside a view, `scene.render()` draws `ItemIgnoresTransformations` items at device-pixel size, so exports wrap it in `ExportService._prepare_text_for_export` and `_restore_text_after_export`.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L288

- **`ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`**: When rendering via `scene.render()` (not through a QGraphicsView), `ItemIgnoresTransformations` items render at their natural pixel size regardless of the source→target scale. For a large scene (e.g. 5300 cm) rendered into a small image (774 px), a 10 pt text item can appear as 80+ cm on canvas. Fix: call `ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering and `_restore_text_after_export()` after. The scale = `output_width_cm / canvas_width_cm`.

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

- **Rule:** An SVG export of the Y-flipped scene renders `<pattern>` tiles upside-down unless each pattern gets a `patternTransform` flip after `painter.end()`, as `ExportService._fix_svg_pattern_yflip()` does.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L298

- **SVG pattern tiles appear Y-inverted under painter Y-flip**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. When the scene is rendered with a `scale(1,-1)` painter transform, each pattern tile image is stored un-flipped, but renders upside-down inside the Y-flipped coordinate space. Fix: post-process the SVG after `painter.end()` and add `patternTransform="matrix(1,0,0,-1,0,{tile_height})"` to each `<pattern>` element. See `ExportService._fix_svg_pattern_yflip()`.

### PF-CAN-13

- **Rule:** `QSvgGenerator` never writes painter clip paths, so SVG export must clip each texture group to its one paired shadow path, and the result is judged in a real browser, not `QSvgRenderer`.
- **Pinned by:** none — The body names only a script for checking this rule, and a script is not a pin.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L300

- **`QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas**: For texture-filled shapes, Qt emits a "shadow" group containing the polygon `<path>` (`fill="#000000"`) followed by a texture group `<g fill="url(#tex)"><rect x="..." y="..." width="..." height="..."/></g>`. The rect is the *painter's clip bounding rect*, not the polygon shape — and the painter's `setClipPath()` is **never** serialized as `<clipPath>`. In SVG viewers (browsers), the unconstrained rect washes across the whole canvas (often as a brownish overlay if it is a roof-tile texture). PNG export is unaffected because Qt's native renderer applies the clip directly. Fix: post-process the SVG (`ExportService._fix_svg_qt_texture_clipping()`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's `<path>` (preserving its `transform`), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 with a `used_textures` set; forward-window scans match the same texture from multiple shadows and corrupt the XML tree. Validate SVGs in a real browser (`scripts/svg_preview.py` uses Edge headless) — `QSvgRenderer` is too forgiving and hides this bug.

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
