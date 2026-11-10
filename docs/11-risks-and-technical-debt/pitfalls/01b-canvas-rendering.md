# Pitfalls: canvas rendering, overlays and exports

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Continues [01-canvas-geometry.md](01-canvas-geometry.md) from PF-CAN-49. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CAN-49

- **Rule:** Qt keeps every item's `DeviceCoordinateCache` picture in the process-wide `QPixmapCache`, whose default limit is 10 MB; a canvas raises it (`ui/canvas/item_cache.ensure_item_cache_budget`, 256 MB) or its item caches thrash and every repaint paints the items again. Setting a cache mode proves nothing: count the paints.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py::TestPanIsCheap`; `tests/integration/test_sun_overlay_cache.py::TestRasterisedOncePerSolve`; `tests/unit/test_minimap_widget.py::TestViewportChangesDoNotRender`; `tests/perf/test_sun_overlay_repaint.py`
- **Source:** #784
- **Status:** standing
- **Legacy:** none (new entry)

The family-garden example needs 17 MB of item caches in a 1453 x 898 viewport (one lawn alone is 5.2 MB), so with the default limit Qt evicted and re-painted on every frame: 49 ms for a repaint that is 8 ms of blits, 143 ms for a 40-px pan. A picture larger than the whole limit (a lawn on a 4K display is 33 MB) was never kept at all. The first attempt at #784 set the sun overlay to `DeviceCoordinateCache` and measured no change whatsoever (146 ms against 152) — the overlay's 5 MB picture was evicted by the next item's. NFR-PERF-01's reference plan did not show it because its 990 items are small. The limit is a ceiling, not an allocation. Switching an item's cache mode drops its picture too, and every `scene.render` (export, Agent API render, minimap) switches all of them: the minimap therefore renders on a scene change only, never on a pan or a zoom. Details and numbers: §8.37.

### PF-CAN-50

- **Rule:** A bitmap drawn through a painter is rasterised for THAT painter: ask `core/raster_resolution` (device scale of the painter, rounded up to a power of two, never below 1) through `paint_plant` / `paint_furniture` / `brush_for_painter`, never hand a renderer the item's size in centimetres as pixels, and never rasterise a sprite whole when it would exceed 1024 px a side.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py`; `tests/unit/test_raster_resolution.py`; `tests/unit/test_sprite_raster.py`; `tests/unit/test_fill_pattern_levels.py`
- **Source:** #785
- **Status:** standing
- **Legacy:** none (new entry)

`render_plant_pixmap(diameter=...)` and `render_furniture_pixmap(width=..., height=...)` take pixels; the item paints passed centimetres, so every sprite was 1 px per cm and anything above 100 % zoom, on a high-density display or in a 300-dpi export was an enlarged bitmap. The resolution cannot be the item's: one item is painted by the canvas, an export, the minimap and the Agent API render at different scales. Three traps on the way: `QPainter.worldTransform()` leaves out the device pixel ratio (`deviceTransform()` has it); a pixmap drawn into an item-space rectangle under the canvas's Y-flip is mirrored (lay a device-space picture down with the device transform made the identity); and a level below 1 is not "sharper", it changes how a texture reads when zoomed out (`MIN_LEVEL`, an owner's decision). A defect of this kind is proportional to zoom and to rotation — test at 400 % and 1000 %, rotated, and against the same interior at 100 % enlarged. §8.9.14.

### PF-CAN-51

- **Rule:** Whatever marks an object (selection handles, the rotation handle, a label anchor) reads `handle_geometry.selection_frame_rect(item)`, never `boundingRect()`; and an `ItemIgnoresTransformations` label is centred or stacked in its own pixel frame, never by an offset written into its position.
- **Pinned by:** `tests/integration/test_selection_frame.py`; `tests/integration/test_canvas_legibility.py::test_a_label_is_centred_on_its_object_at_every_zoom`
- **Source:** #790, #793
- **Status:** standing
- **Legacy:** none (new entry)

`boundingRect()` is the repaint region: outline plus shadow, pen, sprite overflow, badge and spacing ring. A magnolia drawn 2.20 m wide showed its handles on an 8.64 m box while its ring was on show. The same confusion of units put labels off-centre: a label that ignores the view's transformations has its position in plan units and its size in pixels, so `setPos(centre - size / 2)` is right at one zoom only, and two such labels anchored at two plan points overlap once the points are closer on screen than the text is wide. See §8.9.17.

### PF-CAN-52

- **Rule:** Text that the view scales (a `TextItem` note, a callout) is laid out unhinted (`PreferNoHinting`); text with a halo strokes the glyph outline path, because `drawText` with a wide pen outlines nothing, and takes that outline from the layout that draws the glyphs, never from `QPainterPath.addText`.
- **Pinned by:** `tests/integration/test_canvas_legibility.py::test_a_text_note_is_laid_out_unhinted_whatever_is_set_on_it`; `tests/integration/test_canvas_legibility.py::test_a_callout_is_laid_out_unhinted`; `tests/integration/test_canvas_legibility.py::test_the_scale_bar_label_reads_on_every_background`; `tests/integration/test_canvas_legibility.py::test_the_halo_ends_where_the_text_ends`
- **Source:** #793, #789
- **Status:** standing
- **Legacy:** none (new entry)

A hinted font rounds every advance to the pixel grid of the one size it is laid out at; the zoom magnifies the rounding into uneven gaps ("thy me"). Measured on Windows over one line: glyph positions up to 10.25 px from linear before and 1.9 px after; worst letter gap at 3.3x zoom 2.85 px off before and 1.15 px after. An exact point size and the document's design metrics add nothing to that (same gaps to 0.01 px). The offscreen platform the suite runs on does not hint (0.0 px either way), so the test pins the font setup, not pixels. A halo built by `addText` is a second layout of the text: a bold 10 pt label ended 3.9 px past it on Windows and 15 px on the offscreen platform, which gives a bold face a regular outline. A label's contrast is measured, not judged: §8.9.15.

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

### PF-CAN-55

- **Rule:** A scale bar's length is its label's distance at the scale its picture was painted at: pick a round distance that fits, never clamp the bar, and take the scale from the fitted rectangle, not from the frame's width.
- **Pinned by:** `tests/integration/test_pdf_scale_bar.py`
- **Source:** #782
- **Status:** standing
- **Legacy:** none (new entry)

The PDF report's overview page labelled its bar "10 m" while clamping the bar to a share of the page, and derived the bar's length from the page's width although a tall plan is fitted by its height. The bar was 5 % too long on the default 50 m x 30 m plan and 74 % too long on a 20 m x 40 m plan. The plan also sat in a corner of its frame, so no single number described the page. The fix renders the plan and each bed detail into the centred rectangle of their own aspect ratio, and the report picks its distance from the list the canvas uses (`SCALE_BAR_NICE_DISTANCES_CM`). The tests measure the rendered page, bar against label, over five canvas shapes: a test that only reads the label would have passed on the defect.
