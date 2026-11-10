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

### PF-CAN-56

- **Rule:** Code that authors an item (a generator, a fixture builder, a tool) turns it with `geometry_apply.apply_rotation`, never with a bare `QGraphicsItem.setRotation`: the bare call turns about the item's origin and is not the `rotation_angle` the serializer saves, so the item is saved unrotated and at another place.
- **Pinned by:** `tests/unit/test_example_content.py::test_the_balcony_chairs_face_the_table_and_stand_where_they_were_drawn`; `tests/integration/test_example_generation.py::test_the_shipped_files_are_what_the_generator_makes`
- **Source:** #795
- **Status:** standing
- **Legacy:** none (new entry)

`scripts/generate_examples.py` turned the two balcony chairs with `chair.setRotation(±90)`. A rectangle item's pivot is the centre of its rectangle only after `_apply_rotation` has set the transform origin; a bare `setRotation` turns about the item's origin (0, 0), and it never writes `rotation_angle`. The plan that shipped therefore had both chairs unrotated at `x = 120` and `x = 292`. Since #661 the serializer writes a shape where its centre lies in the parent frame (`_stored_shape_offset`), which is right for every item turned about its centre; for these two it is the centre turned about the origin, and a regeneration wrote `x = -257, y = 120` and `x = 215, y = -334`: two chairs off the balcony, still without an angle. Nothing ran the generator in a test, so the drift was found only by regenerating an unchanged tree before making any change. The chairs are now turned through the canonical path (they stand where they were drawn and face the table), and a test compares every shipped plan with the generator's output.

### PF-CAN-57

- **Rule:** A soft edge is a field, not strokes: a stroke has one tone, so stacked strokes are flat bands that show as stripes once the zoom makes them wider than a pixel or two. Rasterise the shape on a coarse lattice anchored in the plan, blur it, map the blurred coverage to the falloff (`core/soft_edge`), enlarge that with filtering and cut the shape out again in a device layer — never with a clip.
- **Pinned by:** `tests/integration/test_shadow_feather.py`; `tests/unit/test_soft_edge.py`; `tests/integration/test_svg_export_fidelity.py::test_a_shadow_feather_is_a_soft_edge_not_an_outline`
- **Source:** #793
- **Status:** standing
- **Legacy:** none (new entry)

The sun shadow's edge was four strokes of 14, 9, 5 and 2.5 cm: bands of 1.25 to 2.5 cm, one soft edge at 100 % zoom and four stripes from 200 % on, the innermost 15 levels darker than the shade it edged (largest step 29 to 39 of 97 levels at every zoom; after, an even ramp's own step: 15 at 100 %, 4 at 400 %, 2 at 1000 %). More strokes are more bands and more antialiased rasterisation, which was 95 % of the overlay's paint. Four traps on the way to the field. (1) Blurred coverage is a distance only through a table, and far from the edge the coverage is tiny: with 1024 entries the falloff ended a tenth of its reach early. (2) A table that stops at the shade's tone starts the falloff below it, by a quarter of a cell's share of the reach, because the enlargement interpolates from cells inside the shade: continue the falloff above 1 inside (`MAX_WEIGHT`) and cut the shade out afterwards. (3) `n` box passes of `r` cells reach `n * r` cells from a cell's CENTRE plus half a cell, not `n * (r + 0.5)`: a lattice sized by the wrong half-width left a constant tint beyond the edge. (4) Floating-point running sums were three quarters of the cost; 32-bit integer sums that wrap are exact for the differences and four times as fast. A lattice anchored at the item's origin, not at the exposed rectangle, is what makes a pan's strip agree with the whole picture. §8.9.18.

### PF-CAN-58

- **Rule:** A scene finds the items of a picture by their rectangles taken WITHOUT the painter's transform, and for an item that ignores transformations that rectangle is in pixels around its anchor: one that lies on one side of the anchor is outside a y-flipped `scene.render()` and the item is not painted at all. Give it a `boundingRect()` that reaches across the anchor (the rectangle united with its mirror image).
- **Pinned by:** `tests/integration/test_sun_map_legend.py::test_a_picture_of_the_plan_carries_the_key`; `tests/integration/test_sun_map_legend.py::test_the_svg_and_the_png_export_carry_the_key`
- **Source:** #794
- **Status:** standing; narrative in [debug-verbose: Case study: the key was in the scene, visible, and in no picture (#794)](../../../.claude/skills/debug-verbose/references/224-case-study-the-key-was-in-the-scene-visible-and-in-no-picture-794.md)
- **Legacy:** none (new entry)

The key of the sun map is a scene item at the plan's south-west corner, drawn up and right of it: `QRectF(margin, -margin - height, width, height)` in its own pixels. The canvas is y-up, so every picture is rendered through a painter that flips y, and on the device "up" is inside the plan. But `QGraphicsScene.render` collects its items with `items(sourceRect)`, which for an item that ignores transformations takes its rectangle at its position with NO transform — there, negative y is south of the plan, outside the source rectangle. The item was visible, in the scene, and in no picture (0 dark pixels; 3,236 with the mirrored rectangle). An object label does not show this because it is centred on its anchor. The same blindness in another shape: `shape()` of a path item is its stroke united with the path FILLED, so an open fence round three sides of a balcony "covered" the balcony for anything that asked what it covers (`PolylineItem.grid_cover_path` returns the stroke alone, §8.9.17). And two traps of a key drawn over the viewport instead: Qt scrolls a viewport's pixels on a pan and repaints only the strip that came into view, so anything in viewport coordinates must ask for its own rectangle again in `scrollContentsBy`; and a scroll area's scroll-bar containers are child widgets that stay "visible" with a rectangle while their bar is hidden — they are no overlays. §8.9.18.

### PF-CAN-59

- **Rule:** Text that an item draws by hand (`painter.setFont` + `drawText`) is drawn with a font sized in pixels (`ui/canvas/layout_font.device_independent`), and every measure around it is a share of that font: a font in points is resolved by each painter for its own device, while `QFontMetricsF(font)` answers for the screen.
- **Pinned by:** `tests/integration/test_succession_badge_export.py::test_the_badge_is_legible_and_whole_in_a_printout`; `tests/integration/test_succession_badge_export.py::test_the_badge_is_legible_in_a_png`; `tests/integration/test_text_note_size.py::test_the_size_the_panel_states_is_the_size_of_the_letters_on_the_plan`
- **Source:** #836
- **Status:** standing; narrative in [debug-verbose: Case study: a badge whose text overprinted its own box on paper — a font in points is resolved per paint device (#836, fixed 2026-11-10)](../../../.claude/skills/debug-verbose/references/225-case-study-a-badge-whose-text-overprinted-its-own-box-on-paper-836.md#case-study-a-badge-whose-text-overprinted-its-own-box-on-paper--a-font-in-points-is-resolved-per-paint-device-836-fixed-2026-11-10)
- **Legacy:** none (new entry)

Measured on Windows, Qt 6.12: `QFont("Arial", 28)` is a 37-pixel font on a `QImage` and where no device is given (a scene item's layout, `QFontMetricsF(font)`), and a 467-pixel font on a 1200-dpi `QPrinter`; the two agree only by the accident of a 96-dpi screen. The succession badge sized its box from constants in pixels and `QFontMetricsF`, then drew with `painter.setFont(7 pt)`: right on the canvas, 1 mm lines in a 300-dpi PNG (nothing scaled the box), and in a printout three crop names of 117 px in rows of 13 px, printed over one another. `QGraphicsSimpleTextItem` and `QGraphicsTextItem` do not have the defect: they draw the layout they measured. The same unit confusion had `TextItem.font_size` documented as centimetres: a note's points are laid out at 96 pixels per inch and a pixel of the item is a plan centimetre, so 1.0 (28 pt) is an em of 37 cm. A constant-size item with hand-drawn text therefore keeps one font, derives padding, line pitch and corner radius from its line height, and offers `font()` / `setFont()` so `retarget_constant_size_text` can size it for an export. Test it on a printout (a PDF from a `HighResolution` printer, rasterised), not on a `QImage` alone: a picture has the screen's logical resolution and hides the defect. §8.36.

### PF-CAN-60

- **Rule:** What a paint needs of the WHOLE scene (what stands on the plan, which labels have room) is kept in plan coordinates and taken again only when `CanvasScene.paint_revision` has moved, never walked for a paint; and `QGraphicsScene.changed` alone is not that revision: it is silent when an item that ignores transformations is hidden or shown, and it reaches a slot only when the event loop runs.
- **Pinned by:** `tests/integration/test_grid_cover_cache.py`; `tests/integration/test_label_layout_cache.py`
- **Source:** #793, #784 (review of the 2D visual-polish branch)
- **Status:** standing
- **Legacy:** none (new entry)

The grid's cut-out and the label pass both read the whole scene inside a paint, so their cost grew with the plan and was paid for a 40-pixel repaint as for a full one: on a plan of 853 named objects the cut-out was 70 ms of a 120 ms repaint. Both answers are properties of the scene, and in plan coordinates they do not change with a pan or a zoom. Measured on Qt 6.12 with a slot on `changed`: moving, hiding, showing, restacking or removing an ordinary item emits it; `setText` and `setPos` on an `ItemIgnoresTransformations` child emit it; `hide()` and `show()` on such a child emit nothing; a zoom, a pan and a repaint emit nothing. Inside the event loop Qt emits `changed` before the paint it causes, and slots run in the order they were connected, so the scene connects its own slot in its constructor, before any view exists. A caller that repaints at once after a change sees the old answer unless a synchronous chokepoint moved the revision too: a garden item's `itemChange` (through `plan_changed`), `addItem`, `removeItem`, `clear`, the selection, and the label items themselves (`halo_text.note_label_changed`), which is also what covers the hidden label. A kept answer that names items is dropped where the scene destroys them (`CanvasScene.clear`). The label pass answered every change of its choice with a full repaint, which painted each zoom step twice; it now asks for the rectangles of the labels that entered or left the choice, and a test of that reads the window's backing store (`screen().grabWindow`): `QWidget.grab()` paints the widget afresh and cannot show a pixel a partial repaint left behind. Three more traps on the way. A clip region of thousands of rectangles makes every line drawn under it slow (20 ms more than the lines themselves), so the grid is cut out in a layer instead. Qt's raster engine draws a cosmetic line into a painter that has no clip ten times slower than into one that has (196 lines: 28 ms against 2.5 ms): give a layer's painter a clip rectangle. And the outlines of two objects must not share one fill: where they overlap with opposite winding they cancel. §8.9.15, §8.9.17, §8.37.
