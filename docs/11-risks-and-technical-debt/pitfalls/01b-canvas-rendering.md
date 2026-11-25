# Pitfalls: canvas rendering, overlays and exports

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Continues [01-canvas-geometry.md](01-canvas-geometry.md) from PF-CAN-49. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CAN-49

- **Rule:** Qt keeps every item's `DeviceCoordinateCache` picture in the process-wide `QPixmapCache`, whose default limit is 10 MB; a canvas raises it (`ui/canvas/item_cache.ensure_item_cache_budget`, 256 MB) or its item caches thrash and every repaint paints the items again. Setting a cache mode proves nothing: count the paints.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py::TestPanIsCheap`; `tests/integration/test_sun_overlay_cache.py::TestRasterisedOncePerSolve`; `tests/unit/test_minimap_widget.py::TestViewportChangesDoNotRender`; `tests/perf/test_sun_overlay_repaint.py`; `tests/integration/test_canvas_sharpness.py::TestALargeViewportKeepsItsSprites`; `tests/integration/test_sun_overlay_cache.py::TestAboveTheCap`
- **Source:** #784
- **Status:** standing
- **Legacy:** none (new entry)

The family-garden example needs 17 MB of item caches in a 1453 x 898 viewport (one lawn alone is 5.2 MB), so with the default limit Qt evicted and re-painted on every frame: 49 ms for a repaint that is 8 ms of blits, 143 ms for a 40-px pan. A picture larger than the whole limit (a lawn on a 4K display is 33 MB) was never kept at all. The first attempt at #784 set the sun overlay to `DeviceCoordinateCache` and measured no change whatsoever (146 ms against 152) — the overlay's 5 MB picture was evicted by the next item's. NFR-PERF-01's reference plan did not show it because its 990 items are small. The limit is a ceiling, not an allocation. Switching an item's cache mode drops its picture too, and every `scene.render` (export, Agent API render, minimap) switches all of them: the minimap therefore renders on a scene change only, never on a pan or a zoom. A bound stated in megabytes or pixels is a statement about ONE viewport, and it was the 1453 x 898 one the first measurements were taken in (review of the branch). The sprite cache's fixed 64 MB did not hold one frame of a 3840 x 2000 viewport: on a plan of 853 objects at 207 % every zoom step rasterised 134 sprites again and took 1.3 s, so its bound follows the viewport's device pixels now (`sprite_raster.sprite_cache_budget`, 256 MB at most). And the sun overlay kept no picture above 2048 device pixels a side, which a 4K window crosses at fit and a 150 % display from about 1365 logical pixels (`QPainter.deviceTransform()` carries the ratio): every wheel step rasterised it. Above the cap it keeps a reduced picture instead of none. Measure at the largest viewport and at a ratio above 1 (`QT_SCALE_FACTOR` works on the offscreen platform), and count rasterisations at a zoom step INSIDE one raster level: a cache that evicts its own frame shows there and nowhere else. Details and numbers: §8.37.

### PF-CAN-50

- **Rule:** A bitmap drawn through a painter is rasterised for THAT painter: ask `core/raster_resolution` (device scale of the painter, rounded up to a power of two, never below 1) through `paint_plant` / `paint_furniture` / `brush_for_painter`, never hand a renderer the item's size in centimetres as pixels, and never rasterise a sprite whole when it would exceed 1024 px a side.
- **Pinned by:** `tests/integration/test_canvas_sharpness.py`; `tests/unit/test_raster_resolution.py`; `tests/unit/test_sprite_raster.py`; `tests/unit/test_fill_pattern_levels.py`
- **Source:** #785
- **Status:** standing
- **Legacy:** none (new entry)

`render_plant_pixmap(diameter=...)` and `render_furniture_pixmap(width=..., height=...)` take pixels; the item paints passed centimetres, so every sprite was 1 px per cm and anything above 100 % zoom, on a high-density display or in a 300-dpi export was an enlarged bitmap. The resolution cannot be the item's: one item is painted by the canvas, an export, the minimap and the Agent API render at different scales. Three traps on the way: `QPainter.worldTransform()` leaves out the device pixel ratio (`deviceTransform()` has it); a pixmap drawn into an item-space rectangle under the canvas's Y-flip is mirrored (lay a device-space picture down with the device transform made the identity); and a level below 1 is not "sharper", it changes how a texture reads when zoomed out (`MIN_LEVEL`, an owner's decision). A defect of this kind is proportional to zoom and to rotation — test at 400 % and 1000 %, rotated, and against the same interior at 100 % enlarged. §8.9.14.

### PF-CAN-51

- **Rule:** Whatever marks an object (selection handles, the rotation handle, a label anchor) reads `handle_geometry.selection_frame_rect(item)`, never `boundingRect()`; and an `ItemIgnoresTransformations` label is centred or stacked in its own pixel frame, never by an offset written into its position.
- **Pinned by:** `tests/integration/test_selection_frame.py`; `tests/integration/test_canvas_legibility.py::test_a_label_is_centred_on_its_object_at_every_zoom`; `tests/integration/test_pdf_report_pages.py::test_the_position_in_the_plant_list_is_the_plant_not_its_badge`
- **Source:** #790, #793
- **Status:** standing
- **Legacy:** none (new entry)

`boundingRect()` is the repaint region: outline plus shadow, pen, sprite overflow, badge and spacing ring. A magnolia drawn 2.20 m wide showed its handles on an 8.64 m box while its ring was on show. The same confusion of units put labels off-centre: a label that ignores the view's transformations has its position in plan units and its size in pixels, so `setPos(centre - size / 2)` is right at one zoom only, and two such labels anchored at two plan points overlap once the points are closer on screen than the text is wide. A report that states where an object stands reads the same rectangle: the PDF plant list took its Position column from `boundingRect().center()`, and a plant with an antagonist badge in one corner was listed beside itself (found by the review of the 2D branch). See §8.9.17.

The #841 follow-up moves the canonical frame to `core/item_geometry.py`; the
old handle import is an alias. Both object-snap sides, align/distribute and the
capacity badge use it. `tests/integration/test_canvas_editing_precision.py` and
`tests/unit/test_item_geometry.py` pin decoration independence and nested groups.

### PF-CAN-52

- **Rule:** Text that the view scales (a `TextItem` note, a callout) is laid out unhinted (`PreferNoHinting`); text with a halo strokes the glyph outline path, because `drawText` with a wide pen outlines nothing, and takes that outline from the layout that draws the glyphs, never from `QPainterPath.addText`; and a label that shows text from the plan shows a bounded text (`halo_text.label_text`), because stroking outlines costs what the text is long.
- **Pinned by:** `tests/integration/test_canvas_legibility.py::test_a_text_note_is_laid_out_unhinted_whatever_is_set_on_it`; `tests/integration/test_canvas_legibility.py::test_a_callout_is_laid_out_unhinted`; `tests/integration/test_canvas_legibility.py::test_the_scale_bar_label_reads_on_every_background`; `tests/integration/test_canvas_legibility.py::test_the_halo_ends_where_the_text_ends`; `tests/integration/test_plan_label_text_bound.py`
- **Source:** #793, #789
- **Status:** standing
- **Legacy:** none (new entry)

A hinted font rounds every advance to the pixel grid of the one size it is laid out at; the zoom magnifies the rounding into uneven gaps ("thy me"). Measured on Windows over one line: glyph positions up to 10.25 px from linear before and 1.9 px after; worst letter gap at 3.3x zoom 2.85 px off before and 1.15 px after. An exact point size and the document's design metrics add nothing to that (same gaps to 0.01 px). The offscreen platform the suite runs on does not hint (0.0 px either way), so the test pins the font setup, not pixels. A halo built by `addText` is a second layout of the text: a bold 10 pt label ended 3.9 px past it on Windows and 15 px on the offscreen platform, which gives a bold face a regular outline. A label's contrast is measured, not judged: §8.9.15. And the halo made a label's cost its text's length: an object's name went into its label as the plan file had it, so a name of a million characters froze the canvas for 47 s at its first paint and one of a million and a half crashed Qt's stroker (access violation). Only with a real font: the offscreen platform's box font has no outlines to stroke (56 ms), so the test that carried such a name passed alone and hung in a run where another test had registered the suite's font. `PlanLabelItem` and the succession badge show `core.plain_text.clip_line` of what they are given — the rule of every row and card that shows a name (§8.11).

The #872/#874 follow-up resolves note fonts at fixed 96 dpi into pixels, keeping
stored values and the historical 96 dpi appearance. The native Windows pixel
oracle now compares letter gaps with a high-resolution reference and proves
sensitivity by restoring full hinting: 0.5 px versus 2-2.5 px in the measured
sample. Pinned by `tests/integration/test_canvas_native_pixels.py` and
`tests/integration/test_canvas_label_precision.py`.

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

- **Rule:** A soft edge is a field, not strokes: a stroke has one tone, so stacked strokes are flat bands that show as stripes once the zoom makes them wider than a pixel or two. Rasterise the shape on a coarse lattice anchored in the plan, blur it, map the blurred coverage to the falloff (`core/soft_edge`), enlarge that with filtering, clamp it to the shape's own tone THERE (blurred coverage is a distance beside a straight edge only) and cut the shape out again in a device layer — never with a clip.
- **Pinned by:** `tests/integration/test_shadow_feather.py`; `tests/integration/test_shadow_feather_concave.py`; `tests/unit/test_soft_edge.py`; `tests/integration/test_svg_export_fidelity.py::test_a_shadow_feather_is_a_soft_edge_not_an_outline`
- **Source:** #793
- **Status:** standing
- **Legacy:** none (new entry)

The sun shadow's edge was four strokes of 14, 9, 5 and 2.5 cm: bands of 1.25 to 2.5 cm, one soft edge at 100 % zoom and four stripes from 200 % on, the innermost 15 levels darker than the shade it edged (largest step 29 to 39 of 97 levels at every zoom; after, an even ramp's own step: 15 at 100 %, 4 at 400 %, 2 at 1000 %). More strokes are more bands and more antialiased rasterisation, which was 95 % of the overlay's paint. Four traps on the way to the field. (1) Blurred coverage is a distance only through a table, and far from the edge the coverage is tiny: with 1024 entries the falloff ended a tenth of its reach early. (2) A table that stops at the shade's tone starts the falloff below it, by a quarter of a cell's share of the reach, because the enlargement interpolates from cells inside the shade: continue the falloff above 1 inside (`MAX_WEIGHT`) and cut the shade out afterwards. (3) `n` box passes of `r` cells reach `n * r` cells from a cell's CENTRE plus half a cell, not `n * (r + 0.5)`: a lattice sized by the wrong half-width left a constant tint beyond the edge. (4) Floating-point running sums were three quarters of the cost; 32-bit integer sums that wrap are exact for the differences and four times as fast. A lattice anchored at the item's origin, not at the exposed rectangle, is what makes a pan's strip agree with the whole picture — and its pitch must follow from the device's scale alone: a field too large for one pass was computed on a lattice made coarser by what THAT paint exposed, so two tiles of one print met at a seam (6 levels with the bound lowered); it is computed in bands on the one lattice now. (5) The trap the first version walked into (second review of the 2D branch): blurred coverage is a distance beside a STRAIGHT edge only. In the inside corner of an L, in the cusp between two round shades, in a sunlit hole and in a narrow sunlit gap, more than half of what surrounds a sunlit point is shade, the "distance" is negative and the weight above 1: ground beside the shade was painted up to 41 of its 97 levels darker than the shade, along the whole length of a 4 cm gap — and the one test of "no ring darker than the shade" measured one rectangle. The clamp belongs after the enlargement, in device pixels (the mask added to itself with saturation, with the shape's tone at half a byte). Both lattice clamps were tried: clamping the cells the shape does not cover leaves a cell's width of too-dark ground along every concave outline (29 levels in an 8 cm hole), because the enlargement interpolates from the cells beside them; clamping every cell is trap (2) again. Test a falloff on shapes with an inside corner, a cusp, a hole and a gap, and assert on every pixel, not on one profile. §8.9.18.

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

- **Rule:** What a paint needs of the WHOLE scene (what stands on the plan, which labels have room) is kept in plan coordinates and taken again only when `CanvasScene.paint_revision` has moved, never walked for a paint; and `QGraphicsScene.changed` is not that revision: it cannot tell an edit from a tool's preview, a hover or a shadow that moved, it is silent when an item that ignores transformations is hidden or shown, and it reaches a slot only when the event loop runs — every place that changes what is kept says so itself.
- **Pinned by:** `tests/integration/test_grid_cover_cache.py`; `tests/integration/test_label_layout_cache.py`; `tests/integration/test_tool_preview_repaint.py`; `tests/integration/test_polygon_paint_bound.py::TestTheGridCutOutIsBounded`; `tests/integration/test_label_viewport_entries.py`
- **Source:** #793, #784 (review of the 2D visual-polish branch)
- **Status:** standing
- **Legacy:** none (new entry)

The grid's cut-out and the label pass both read the whole scene inside a paint, so their cost grew with the plan and was paid for a 40-pixel repaint as for a full one: on a plan of 853 named objects the cut-out was 70 ms of a 120 ms repaint. Both answers are properties of the scene, and in plan coordinates they do not change with a pan or a zoom. Measured on Qt 6.12 with a slot on `changed`: moving, hiding, showing, restacking or removing an ordinary item emits it; `setText` and `setPos` on an `ItemIgnoresTransformations` child emit it; `hide()` and `show()` on such a child emit nothing; a zoom, a pan and a repaint emit nothing. Inside the event loop Qt emits `changed` before the paint it causes, and slots run in the order they were connected, so the scene connects its own slot in its constructor, before any view exists. A caller that repaints at once after a change sees the old answer unless a synchronous chokepoint moved the revision too: a garden item's `itemChange` (through `plan_changed`), `addItem`, `removeItem`, `clear`, the selection, and the label items themselves (`halo_text.note_label_changed`), which is also what covers the hidden label. A kept answer that names items is dropped where the scene destroys them (`CanvasScene.clear`). The label pass answered every change of its choice with a full repaint, which painted each zoom step twice; it now asks for the rectangles of the labels that entered or left the choice, and a test of that reads the window's backing store (`screen().grabWindow`): `QWidget.grab()` paints the widget afresh and cannot show a pixel a partial repaint left behind. Three more traps on the way. A clip region of thousands of rectangles makes every line drawn under it slow (20 ms more than the lines themselves), so the grid is cut out in a layer instead. Qt's raster engine draws a cosmetic line into a painter that has no clip ten times slower than into one that has (196 lines: 28 ms against 2.5 ms): give a layer's painter a clip rectangle. And the outlines of two objects must not share one fill: where they overlap with opposite winding they cancel. **What the second review found in the first version of this.** (1) The revision moved on `changed` as well, "to be safe": a rubber band, a shape being drawn and the measure tool's snap mark are scene items, so on 853 objects a rubber band took both kept answers again at every other mouse move (15 + 15 rebuilds in 30 moves, 13 ms a move against 2.8). The signal cannot be filtered — it carries rectangles, not items — so it was let go, after measuring what else it caught: at every `changed` of 4,331 canvas tests a fresh answer was compared with the kept one, and the signal was the only notice for the plan date (`refresh_timeline` hides and shows plants without a plan change) and a bare write to `object_type`; both say so themselves now. Measure a safety net before removing it, and remove it when it costs more than it catches. (2) What is kept must be bounded like what is painted: the cut-out filled every object's exact outline, so the paint bound of #472 did not hold with the grid on (one line of 16,000 zigzag vertices: 2.7 s a repaint; an outline above the bound now covers nothing). (3) Keeping the answer is half of it: the finished layer was still made for every paint (25 ms of 55 in a 4K viewport); the view keeps it and a pan moves it (§8.9.17). (4) A dictionary keyed by `id(viewport)` never drops an entry and hands a dead widget's entry to a new widget at its address: key by the widget, weakly. §8.9.15, §8.9.17, §8.37.

### PF-CAN-61

- **Rule:** A method that Qt calls on a view, a scene or an item while another object of the same garbage is destroyed (a virtual such as `scrollContentsBy`, a slot on a signal Qt emits from a destructor) reads only attributes that have a class-level default: the cyclic collector clears an object's `__dict__` before it destroys its C++ part, and an `AttributeError` raised inside a Qt-called virtual ends the process without a traceback.
- **Pinned by:** `tests/integration/test_dropped_canvas.py`; `tests/integration/test_touch_gestures.py::test_late_viewport_event_can_run_without_the_touch_flag`; `tests/integration/test_dropped_canvas.py::test_edit_handles_refresh_ignores_a_destroyed_scene`
- **Source:** #794 (second review of the 2D visual-polish branch)
- **Status:** standing; narrative in [debug-verbose: Case study: a dropped canvas ended the process with 0xC0000409 and not a word — Qt called a virtual on a view whose attributes the collector had already cleared (#794, fixed 2026-11-10)](../../../.claude/skills/debug-verbose/references/231-case-study-a-dropped-canvas-ended-the-process-without-a-word-794.md)
- **Legacy:** none (new entry)

`CanvasView.scrollContentsBy` read `self._sun_legend_rect`, an attribute added with the sun map's key. A view and its scene reference each other, so a pair that is dropped without `close()` and `deleteLater()` is garbage only the cyclic collector finds. It clears the attributes of every object of that garbage first and destroys them afterwards, in an order of its own. When the scene's C++ object goes first, Qt takes the scene from the view (`setScene(nullptr)`), which recomputes the scroll bars and calls `scrollContentsBy` — a virtual, so PyQt enters the Python override on a view whose `__dict__` is empty. The `AttributeError` cannot propagate through C++; PyQt prints it and calls `qFatal`: exit code 0xC0000409 at the first `gc.collect()`, nothing on stdout, and in a test run a worker that is simply gone. The application did not hit it (it closes and deletes its window) and neither did the suite (an autouse fixture closes and deletes every widget, which destroys them in Qt's order), so it was found only by a probe that drops a view. Which methods Qt enters during such a collection was recorded, not guessed: with every method of the view, the scene, the minimap, the shadow controller and every item wrapped, over nine ways of dropping a canvas (bare, shown, with the minimap, a selection and its handles, scroll bars, the scene owned by the view, the key's item, the controller), the only Python code Qt entered was `scrollContentsBy` and `_refresh_dense_vertex_overlays`, which it calls. The fix is the one `CanvasScene._paint_revision` already had for a slot Qt calls from the scene's destructor: a class-level default, so the lookup finds a value when the instance has none. `getattr(self, name, default)` at the read is the same thing, said at every read instead of once. A `paint()`, a `boundingRect()` and an `itemChange()` are not entered during a collection — Qt calls no virtual on an item it is destroying — so they need no such default; a new override of something Qt calls from ANOTHER object's destructor (scroll bars, a scene's signals, an event filter on a parent) does.

PR #985 reproduced the same lifecycle in the viewport event filter during the
Linux coverage run. The touch flag falls back to disabled when instance
attributes have been cleared, so the Qt base filter receives the event.

The Windows closing trace also showed a late edit-handle refresh. At that
point Qt had detached the scene, but the cached Python wrapper was still
reachable. Read the view's current scene for this callback and skip the
refresh when there is no live canvas scene.

### PF-CAN-62

- **Rule:** A print page's order and decoration belong to the page's own transform. Anchor fixed-scale rows at the TOP of the plan so a non-whole tile leaves the short row LAST; draw the optional grid after the scene at the canvas's spacing with a pen stated in millimetres, because a cosmetic pixel at 1200 dpi is invisible.
- **Pinned by:** `tests/integration/test_pdf_report_pages.py::test_the_short_tile_row_is_the_last_page_not_the_first`; `tests/integration/test_pdf_report_pages.py::test_the_print_grid_option_paints_the_canvas_grid`
- **Source:** #868, #871
- **Status:** standing
- **Legacy:** none (new entry)

`_render_scaled` mapped page row 0 to `rows - 1` in scene coordinates. With a plan
height that is not a whole number of tiles, that is the SHORT top row, so sheets 1 and
2 were blank below their strip. Anchoring rows at the top puts the remainder at the
bottom of the last sheet. The Grid checkbox had been stored and never read; the grid
now paints over the plan in the page transform. Both defects are visible only in a
rasterised printout, which is what the tests read.

### PF-CAN-63

- **Rule:** A kept picture is invalidated by the state it reads, and its consumer selects its render scope explicitly; a preview's repaint is no geometry edit, and a thumbnail is no live viewport clip.
- **Pinned by:** `tests/integration/test_canvas_repaint_package.py`; `tests/integration/test_embedded_canvas_paint.py`; `tests/integration/test_canvas_sharpness.py`; `tests/unit/test_minimap_widget.py`
- **Source:** #847, #848, #877, #878
- **Status:** standing
- **Legacy:** none (new entry)

Stamp the snap index with the shared paint revision and compare at query time:
Qt's queued `changed` includes preview movement but cannot announce a real edit
synchronously. The rectangle-drag probe counted ten rebuilds at one unchanged
revision; the retained index counted zero, and a moved object still rebuilt.
Keep item-cache modes during a minimap render; the scoped thumbnail walk cap
selects a whole-item style clip without discarding the viewport's device cache.
The grid builds on its first nonempty paint after invalidation and keeps exact
subpixel phases under one memory bound. Do not require a full repaint to make
a partial repaint cacheable.

Paint tests must capture the owning window before cropping the viewport:
grabbing the viewport alone removes its offset in the backing store. Retain
the host window's Python wrapper; `qtbot.addWidget` keeps only a weak reference.
For a clipped minimap frame, put the view inside the plan before testing a
pan: moving an already-outside viewport may leave the frame clipped to zero.

### PF-CAN-64

- **Rule:** Never set C++ `ItemIgnoresTransformations` on every plan object's label child (`PlanLabelItem` tracks it in Python), drop `DeviceCoordinateCache` globally on crowded plants, drill into a group on `mousePress`, or feed unbounded text to `EditableLabel` / `QGraphicsTextItem`.
- **Pinned by:** `tests/integration/test_plan_label_hits.py::test_scene_query_on_large_plan_uses_bsp_index_not_full_walk`; `tests/integration/test_plan_label_hits.py::test_plan_label_in_plain_scene_ignores_parent_and_view_transforms`; `tests/integration/test_group_drill_down.py::test_dragging_a_newly_grouped_or_selected_group_moves_all_members_together`; `tests/integration/test_canvas_editing_precision.py::test_box_selection_over_position_locked_lawn_selects_plants_not_lawn`; `tests/integration/test_plan_label_text_bound.py::test_inline_label_editor_bounds_huge_name_and_preserves_untouched_name`; `tests/integration/test_plan_label_text_bound.py::test_huge_text_item_bounds_display_and_selection_paint`; `tests/integration/test_plan_label_text_bound.py::test_huge_callout_item_bounds_display_and_selection_paint`
- **Source:** #919, #873, #847
- **Status:** standing; narrative in [debug-verbose: Case study: untransformable label child poisoned Qt's BSP tree (#919)](../../../.claude/skills/debug-verbose/references/264-case-study-untransformable-label-bsp-poisoning-919.md)
- **Legacy:** none (new entry)

Setting C++ `ItemIgnoresTransformations` on `PlanLabelItem` put every top-level garden item on an 853-object plan into Qt's `untransformableItems` fallback list, forcing every `scene.itemAt()`, hover, press, and repaint to walk all owners in Python (with uncached `CircleItem.boundingRect()` recomputing overflow, spacing, and shadow margins on each visit). `PlanLabelItem.setFlag` / `setFlags` now track the flag in Python (`_ignores_transformations`) and `screen_device_transform()` applies screen-space positioning in `LabelPass` and standalone `paint()`; `CircleItem`, `PolylineItem`, and `HaloTextItem` cache `_cached_bounding_rect` until `prepareGeometryChange()`. Crowded plants (`_needs_live_spacing_paint`) keep `DeviceCoordinateCache` while `CanvasScene._invalidate_spacing_ring_caches_for_decorations()` updates only `_clipped_spacing_ring_items` and items overlapping active edit-handle bounds (`edit_decoration_covers` cached at zero translation), and mid-drag timer callbacks defer while `CanvasView.is_interacting` is active. `SelectTool` defers `begin_group_drill_down` to a stationary release so dragging a selected group moves all members together, and starting a drag on a position-locked (`is_position_locked()`) or locked-layer item promotes into rubber-band box selection. Separately (`#873`), `GardenItemMixin.start_label_edit` edits `label_text()` (80 chars) and `TextItem` / `CalloutItem` cap Qt document layout at `MAX_DISPLAY_TEXT_CHARS = 2_000` with a cosmetic selection pen while keeping full underlying strings untouched unless modified.

### PF-CAN-65

- **Rule:** Never cut a semi-transparent overlay out of a separate layer with plain `CompositionMode_DestinationOut` and then composite the interior with `CompositionMode_SourceOver` (`shadow_feather._cut_out_shade` compensates boundary pixels by `(1 - c) / (1 - c * alpha_s)`); and during rapid timeline scrubbing `SunShadowController` caches casters by `(paint_revision, plan_date)` and defers `paint_feather` until the scrub settles while keeping exports feathered.
- **Pinned by:** `tests/integration/test_shadow_feather_concave.py::test_no_lighter_hairline_along_any_outline`; `tests/integration/test_shadow_feather_concave.py::test_diagonal_and_curved_edge_transition_monotonically`; `tests/integration/test_sun_overlay_cache.py::TestTimelineScrub`; `tests/perf/test_sun_overlay_repaint.py::test_timeline_scrub_step_ratio`
- **Source:** #854, #846
- **Status:** standing; narrative in [debug-verbose: Case study: lighter hairline along sun-shadow outlines from DestinationOut + SourceOver (#854)](../../../.claude/skills/debug-verbose/references/265-case-study-shadow-feather-outline-hairline-854.md)
- **Legacy:** none (new entry)

Plain antialiased `DestinationOut` leaves `(1 - c) * alpha_f` on boundary pixels with fractional inside coverage `c`; compositing `c * alpha_s` on top with `SourceOver` produces `alpha - c * (1 - c) * alpha^2`, creating a 9–11 level lighter hairline along every diagonal, curved, or subpixel shade outline. Scaling fractional boundary pixels in `_cut_out_shade` by `(1 - c) / (1 - c * alpha_s)` matches the exact geometric mix while preserving vector `<path>` output in SVG exports. For `#846`, rapid consecutive `_on_clock_changed` steps within `_SCRUB_WINDOW_NS` reuse `(paint_revision, plan_date)` casters and defer `paint_feather` until `_scrub_settle` fires (`_SCRUB_SETTLE_MS`), while exports, minimap, and `settle_overlay()` always render full soft edges.

### PF-CAN-66

- **Rule:** Bound dense polyline stroke paths (`> 256` vertices) with envelope-preserving bucket decimation (`path_style_paint.bounded_stroke_points`) and cosmetic selection pens even when selected or exported while preserving `self._points`; scale cosmetic contour pens in high-DPI exports (`sun_heatmap.SunContourItem`); and use contrast-preserving periodic mip tiles (`fill_patterns.COARSE_LEVELS`) below 50 % zoom so minification does not moire or fail the interior contrast guard.
- **Pinned by:** `tests/integration/test_polyline_style_paint.py::test_selected_dense_polyline_bounds_shadow_stroke_and_selection`; `tests/integration/test_polyline_style_paint.py::test_dense_polyline_exports_preserve_width_and_bound_paths`; `tests/integration/test_sun_heatmap.py`; `tests/unit/test_fill_pattern_levels.py`; `tests/integration/test_canvas_item_cache.py`
- **Source:** #928, #851, #849
- **Status:** standing; narrative in [debug-verbose: Case study: selected dense polyline blocked for 5–10 s in QPainterPathStroker (#928)](../../../.claude/skills/debug-verbose/references/266-case-study-selected-dense-polyline-stroker-928.md)
- **Legacy:** none (new entry)

Passing 16,000 tightly packed vertices inside a 300 cm clip into Qt's non-cosmetic `QPainterPathStroker` blocked selected polyline repaints for 5–10 s across `_paint_shadow`, base/style strokes, and selection highlight even with `WalkBudget` active; decimating stroked paths through `bounded_stroke_points()` and caching selected dense bodies per zoom preserves stored width, style, and `self._points` in bounded time. In high-DPI exports (`#851`), raw 1-px cosmetic contour pens shrank into hairlines in 300-dpi PNGs and skewed in SVG; `SunContourItem` scales contour strokes to the export DPI ratio and `svg_export` keeps cosmetic widths consistent across outputs. Below 50 % zoom (`#849`), `fill_patterns` prefilters tiles periodically at `0.5`, `0.25`, and `0.125` px/cm with mean-preserving AC contrast gain so Qt's bilinear sampler avoids brick/roof-tile moire without flattening interior spread.

### PF-CAN-67

- **Rule:** Compare the settled native viewport with two full repaints. "Settled" means the viewport produced two identical grabs 100 ms apart; the forced full repaint is the negative control for completeness. The edit's paint regions must also cover the union of the item's OLD and NEW bounds: a strip left out is a missing invalidate, not a stale grab.
- **Pinned by:** `tests/integration/test_canvas_native_pixels.py::test_selected_shed_replacement_repaints_in_the_main_window`
- **Source:** #879, #1017
- **Status:** standing
- **Legacy:** none (new entry)

Wait for the minimap's thumbnail timer. Crop the owning window's backing
store without asking the widget to redraw, then capture a second full repaint
as a stability control. The first undo capture differed by 810 pixels, all
inside the minimap. Seven settled main-window edits matched on v1.40.8,
including replacing the selected shed with a glasshouse.

Under a 20-worker full-suite load the fixed 500 ms wait after the edit's first
paint was sometimes shorter than the type-change rebuild's queued paint
(#1017): the partial frame was compared before it was complete. `settled_grab()`
now grabs every 100 ms until two frames
match (bounded at 3 s). That wait only ensures no paint is still queued; a
region the partial frame never painted produces two identical stale grabs, so
the loop cannot detect it. The forced full repaint does: the partial and full
frames stay different, and the assertion fails. The 3 s bound only stops an
endlessly animating viewport.

`#1004` is a separate report: the same test failed alone at `5fbc8620` (today:
`move`, diff 4524, bounds [187, 65, 349, 287], `repeat_noise` 0) and passed 4/4
alone on `0d2d8972` (v1.42.0).

**Re-checked 2026-11-25 (#1004):** it passes 6/6 alone on v1.43.0, and 5/5 even
with `settled_grab()` reverted to the pre-#1017 `grab()`, so the report does not
reproduce on shipped master. The issue's own next step was measured instead of
guessed: every edit's paint regions cover the union of the item's old and new
bounds (`uncovered: []`; the regions are two large rects, the full viewport and
the item band). The "strip outside the update region" hypothesis is refuted on
this machine; what remains is a compare against a frame the window server had not
finished (the #1017 shape) or an environment-specific backing store. The driver
now reports `uncovered` and the test requires it empty, so a real missing
invalidate fails deterministically instead of as a pixel diff.

### PF-CAN-68

- **Rule:** Export a raster picture no finer than the page it lands on: `raster_level` rounds a painter's scale UP to a power of two for the canvas, and a print painter meets that level with up to 1.7x the pixels a 300-dpi page shows. Fit each picture to one pixel per export unit (`svg_export._fit_picture`), measured by the lengths the state transform maps the target's edges onto (never a rotation-inflated bounding box), and never enlarge one.
- **Pinned by:** `tests/unit/test_svg_export_pictures.py::test_a_picture_finer_than_its_place_is_cut_to_the_export`; `tests/unit/test_svg_export_pictures.py::test_the_device_size_is_taken_through_the_state_transform`; `tests/unit/test_svg_export_pictures.py::test_a_turned_picture_is_measured_by_its_edge_not_its_bounding_box`; `tests/unit/test_svg_export_pictures.py::test_a_picture_already_at_the_export_s_size_is_untouched`; `tests/unit/test_svg_export_pictures.py::test_a_non_finite_target_never_aborts_the_export`; `tests/integration/test_svg_export_fidelity.py::test_no_picture_is_embedded_finer_than_the_export_can_show`
- **Source:** #850
- **Status:** standing
- **Legacy:** none (new entry)

Measured on the bundled examples at a 30 cm page (#850): the canvas's raster level sat above the page's own scale, so the family garden's sprites carried 1.33-1.37x the pixels the page shows, the food forest's 1.26-1.69x, and the raised bed's and balcony's 1.00-1.13x — the file fell 18.9 %, 27.4 %, 1.1 % and 6.4 % once each `_PixmapOp` picture was fitted. What stayed is the 300-dpi sprites themselves and the 11 repeating fill-texture brush tiles (3.69 MB base64 / 2.77 MB decoded across 512 x 512 `DETAIL_LEVEL` tiles in the 30 cm family-garden SVG), because `TexturePattern` `QBrush` tiles keep their periodic `fill_patterns.tile_level` tile rather than being non-periodically resampled. Two parts of the report were left alone on purpose — a clipped stroke stays a filled outline because `QSvgRenderer` ignores `clip-path` (the fidelity suite is rasterised with it), and de-duplicating identical payloads saves 0.13 MB of 6.1 MB.

### PF-CAN-69

- **Rule:** Capture both coordinates of a projected datum move; replay them without projection.
- **Pinned by:** `tests/integration/test_reference_points.py::test_projected_move_undo_restores_the_original_coordinate`
- **Source:** #666, PR #985
- **Status:** standing
- **Legacy:** none (new entry)

A requested −20 cm move from x=106 cm stopped at the edge endpoint x=100 cm.
Adding 20 cm during undo restored x=120 cm. Move and Align capture the first
actual result. The reference properties command likewise replays exact coordinates.

### PF-CAN-70

- **Rule:** A command that moves a Qt item group must reconcile bed membership for every plant in the group's child tree, and must not add a bed-child delta to a plant a moved Qt ancestor already carries. Filtering the moved selection for plant types is not the set of plants it carries. Every move also names its delta frame: `scene` deltas are total scene displacements, `local` deltas are parent-relative. A scene residual applied to a Qt child is mapped into its parent's frame, and every non-carried descendant of a bed - a linked plant or a bound reference point - follows the bed's NET scene delta, not the delta of the group that carries the bed and not the bed's own parent-local residual.
- **Pinned by:** `tests/integration/test_bed_membership_reconciliation.py::test_a_mouse_drag_of_a_group_with_its_bed_moves_and_undoes_once`; `tests/integration/test_bed_membership_reconciliation.py::test_live_bed_propagation_skips_a_plant_the_group_carries`; `tests/integration/test_bed_membership_reconciliation.py::test_aligning_a_rotated_group_and_its_child_keeps_the_child_scene_delta`; `tests/integration/test_bed_membership_reconciliation.py::test_a_single_scene_delta_inside_a_rotated_and_scaled_group_lands_in_scene`; `tests/integration/test_bed_membership_reconciliation.py::test_aligning_a_group_and_its_bed_carries_external_plants_by_the_beds_net_delta`; `tests/integration/test_bed_membership_reconciliation.py::test_a_bound_reference_point_follows_its_bed_not_the_group`; `tests/integration/test_group_drill_down.py::test_a_drilled_bed_in_a_rotated_group_carries_its_external_plant_in_scene_space`; `tests/integration/test_agent_api_writes.py::test_move_object_refuses_a_lone_group_member_without_a_side_effect`
- **Source:** #1001, #1021 review, #1020
- **Status:** standing; narrative in [debug-verbose: Case study: a group moved out of a bed kept every plant's bed link (#1001)](../../../.claude/skills/debug-verbose/references/287-case-study-group-move-left-bed-links-1001.md)
- **Legacy:** none (new entry)

`_membership_change_for_move` saw the `GroupItem` only. `is_plant_type()` is
false for a group, so no `BedMembershipChange` was built, while Qt moved every
member as a child. `plants_in_items()` now walks the child tree; the move and
its link changes undo as one step. `expand_with_bed_children` also skips a bed
child whose Qt ancestor is already moved, or a group that contains its bed
would move every linked plant twice.

**#1020:** the same rule holds for a target whose Qt parent is NOT listed. The
agent's `move_object`/`set_object_position` lists only the target; on a rotated
(and scaled) group the scene delta was handed to `moveBy`, which is parent-local,
so the item landed somewhere else on the plan. `MoveItemsCommand(delta_frame="scene")`
now maps every residual into the item's parent frame, with or without a listed
ancestor. Note what the agent still does NOT do: a lone group member is refused by
`_resolve_agent_item` (the curated read tools never expose it), and that refusal is
pinned — the fix is the command's frame rule, not a licence to address members.

### PF-CAN-71

- **Rule:** A per-region raster pass must not let the grouping of geometry into paths decide a cell. Take PRESENCE from the union — the one path a solid sweep paints — and settle a seam cell (its centre on a region boundary) by the even-odd point-in-polygon rule at its centre; the darkest region containing it owns it. A cell that is in no region is sunny. Painting regions separately lets two paths both claim a cell (the darker transmittance wins, one sample darker) or neither (a sunny cell inside a shade).
- **Pinned by:** `tests/unit/test_weighted_seam.py`; `tests/integration/test_open_frame_shade.py::test_every_sample_of_a_two_region_plan_keeps_the_unions_presence`
- **Source:** #1007, found in #830's report
- **Status:** standing
- **Legacy:** none (new entry)

QPainter classifies a pixel whose centre lies exactly on a polygon edge by the path it painted; two disjoint regions painted on their own can both include that cell or both exclude it. The seam cells are found from the region ids (a cell whose id differs from any neighbour's), not from a second full geometric pass, so only a handful of cells per sample are resolved by `points_in_polygons`. A hole or sliver thinner than one cell remains the painter's answer — it is below the raster's resolution, not a seam.

### PF-CAN-72

- **Rule:** A fixed-pixel label's place on the plan is a BOX, not a point. Placement must test the label's whole place-box against an already-placed label's box and against what stands on the plan; a minimum centre distance alone is not enough, because a plan wide enough makes the place-box (chosen for the nominal 1100 px fit) wider than that distance.
- **Pinned by:** `tests/integration/test_sun_map_labels.py::test_on_a_large_plan_no_hour_label_touches_another_or_an_object`
- **Source:** #1008, split out of #830
- **Status:** standing
- **Legacy:** none (new entry)

On a 60 m plan the nominal place-box of an hour label is ~3.9 m wide, while the old rule only asked that label centres be 160 cm apart: neighbouring contour levels stacked at a solid's edge. The label pass could hide some at one zoom, but the placement itself was wrong, and a zoomed-out view painted the pile.

### PF-CAN-73

- **Rule:** A background prefetch must only queue work that is not already cached, and it must never force a repaint from its own drain. An entry that is cached when the queue is merged back would make the timer repaint forever (paint → queue → drain → repaint); a repaint at the end of a batch puts a full scene paint into a hover or a drag, which is the cost the prefetch exists to remove.
- **Pinned by:** `tests/unit/test_sprite_raster.py::TestNextLevelPrefetch`; `tests/integration/test_canvas_repaint_package.py::test_rectangle_tool_hover_and_drag_do_not_walk_whole_plan`
- **Source:** #845, found by the hover/drag repaint gate
- **Status:** standing
- **Legacy:** none (new entry)

The first version queued the next zoom level from every sprite the frame drew and called `viewport.update()` once its queue was empty. At the current level's next level the entries were already cached, so every paint queued them again and the drain repainted: a test that counts `CircleItem.boundingRect` during a hover saw 237 calls a move instead of ~40. The fix is two predicates: `next_key not in cache` before queueing, and no update at all — the next natural paint shows the prefetched pictures.

### PF-CAN-74

- **Rule:** A rewritten SVG `<use>` carries the placement DELTA from the element it references, not the target's absolute x/y. The referenced `<image>` keeps its own x/y and `<use>` translates on top of them; copying the absolute position moves every repeated picture by the first occurrence's offset.
- **Pinned by:** `tests/unit/test_svg_export_pictures.py::test_a_repeated_picture_is_embedded_once_and_placed_twice`; `tests/integration/test_svg_export_fidelity.py`
- **Source:** #850
- **Status:** standing
- **Legacy:** none (new entry)

The first dedupe wrote `<use x="new_x" y="new_y">`; because the defined image already sits at (37, 37), the balcony's sprites landed 37 px down and right and the PNG-vs-SVG mean difference rose to 6.29 (limit 5.0) — the fidelity test, not the payload count, caught it. The fix stores the first x/y and writes `new - first`. A unit test that only counts one base64 payload and one `<use>` would have passed; the fidelity test rasterises both files.
