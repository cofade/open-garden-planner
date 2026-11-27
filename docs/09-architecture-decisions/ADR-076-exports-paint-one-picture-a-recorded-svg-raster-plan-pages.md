---
id: ADR-076
title: "Exports paint one picture — a recorded SVG, raster plan pages in the PDF, live SVG text"
status: "Accepted (visual-polish package, 2026-11-09); shipped in v1.38.0 (PR #838)"
refs: ["#787", "#788", "#789"]
legacy_anchor: adr-076-exports-paint-one-picture--a-recorded-svg-raster-plan-pages-in-the-pdf-live-svg-text-787-788-789
---

# ADR-076: Exports paint one picture — a recorded SVG, raster plan pages in the PDF, live SVG text

**Status**: Accepted (visual-polish package, 2026-11-09); shipped in v1.38.0 (PR #838)

**Context**: every export paints the same `QGraphicsScene`, each through a different
paint device, and each device had its own way of being wrong. The SVG of the
family-garden example showed the roof texture over 70 % of the drawing; the PDF
report's plan pages were 72-dpi bitmaps; a 1:50 printout painted shadows over its own
footer; and every export forced one point size on text the user had sized on purpose.
Measured on Qt 6.12: `QSvgGenerator` drops a brush's own transform and a pixmap's source
rectangle, writes no clip in its default mode and a staircase for two stacked clips in
SVG 1.1 mode, and `QSvgRenderer` ignores `clip-path`.

**Decision**:

1. **The SVG export records and replays.** The scene is painted into a recording
   `QPaintEngine` (`services/svg_export.py`) and the recording is replayed into
   `QSvgGenerator(Svg11)`. A clipped fill or stroke is written as geometry already cut
   to its clip, a brush transform is moved into the world transform, a source rectangle
   is cut out of its pixmap. Only a clipped picture or clipped text keeps a real
   `<clipPath>`. Rejected: repairing the written file by pattern (the previous design —
   it knew one painter's output and missed the next one); writing our own SVG
   serializer (every pen, brush, gradient and text item the app paints would have to be
   re-implemented, and a miss drops content silently); SVG 1.1 clips alone (staircases,
   invisible to `QSvgRenderer`, and no answer to brush transforms).
2. **An SVG is laid out at print resolution.** One user unit is 1/300 inch; `width` and
   `height` state the requested size in millimetres. The painter's world transform
   therefore carries the scale of a 300-dpi PNG, so a picture that rasterises itself for
   the painter's scale is print-sharp in the SVG, and a constant-pixel-size label or
   hairline is the size it has in that PNG. The generator's own resolution stays the
   logical screen resolution, because that is what a font's size in user units has to
   agree with.
3. **SVG text stays text.** A designer who imports the plan edits a label, changes its
   typeface, searches it; outlines would take all three away and multiply the file's
   size. The cost is that glyph shapes and advance widths are the viewer's: measured in
   headless Edge a note's run is within 1.6 % of the canvas. Every `font-family` names a
   generic fallback (`'Segoe UI', sans-serif`), so a machine without the family shows a
   similar face instead of the viewer's serif default. Rejected: converting text to
   paths; embedding fonts (licences, size).
4. **The PDF report's plan pages are 300-dpi pictures, not vectors.** The page is laid
   out in points; each plan picture is painted into a `QImage` of 300 dpi and placed on
   the page (`PLAN_RENDER_DPI`). Measured on the four bundled examples, every page type
   on: 150 dpi 1.2–2.7 MB / 0.3–0.8 s, 200 dpi 1.8–4.0 MB / 0.4–1.3 s, 300 dpi
   3.2–7.0 MB / 0.8–2.4 s. Rejected: painting the scene on the PDF painter. It would be
   sharp at any zoom, but the painter's world transform would carry the page's 72 units
   per inch, and everything that rasterises itself for the painter's scale — sprites,
   texture tiles — would be 72 dpi inside a vector page; the earlier finding that a
   pre-flipped painter is unreliable on a `QPdfWriter` (PF-CAN-10) also stands.
5. **Only constant-pixel-size text is given a size for the output** (PF-CAN-08). A text
   note is sized in plan units and scales with the plan. Notes and callouts are laid out
   by their font's design metrics (`PreferNoHinting`), because a hinted layout is rounded
   to the pixels of the note's nominal size and shows it once scaled; the report's own
   text uses the same preference, for the same reason at 72 units per inch.
6. **A `paint()` never replaces the clip it is handed** (PF-CAN-54), and a printout sets
   its tile as an explicit clip.
7. **A report section that needs more pages gets them.** `PdfReportService.plan_pages`
   returns one entry per real page, so the page count, the progress callback and the
   section titles ("Plant List – page 2 of 3") agree. Small beds whose detail frames
   touch share one page; a frame has a minimum extent (150 cm), padding and a minimum
   aspect ratio. The legend lists the object types and plants on the plan, each with a
   sample painted by the item itself.
8. **A plan has a title apart from its file name.** `ProjectManager.display_name` is the
   file's stem, or — for a plan opened from an example or a template and not yet saved —
   that template's title; `project_name` stays what default file names are built from.

**Consequences**: the SVG fidelity test compares the rasterised SVG with the PNG export
of the same scene (four bundled examples, a parametric roof, a glasshouse, a painter
nobody taught about SVG) at a stated tolerance; a new painter needs no SVG knowledge.
An SVG's pictures are embedded once per use, as before, and grow with their resolution.
The report is three to eight times larger than at 72 dpi.

Cross-refs: PF-CAN-08, PF-CAN-12, PF-CAN-13, PF-CAN-53, PF-CAN-54; §8.36; FR-EXP-01,
FR-EXP-02, FR-EXP-03, FR-EXP-08; debug-verbose case study 219.

**Addendum (issue #836, 2026-11-10) — follow-ups, each decided on a measurement**:

9. **Every section of the report is cut into pages by `plan_pages`** (extends
   decision 7). The Harvest Summary stopped at the foot of its first page (21 of 60
   rows on A4 landscape) and the Garden Notes opened pages on the paint device that
   nobody counted (19 pages written, a progress total of 16). Tables share
   `_section_pages` and `_render_table_page`; the notes are laid out by `_notes_pages`
   with the page's own metrics. Rejected: keeping the notes' own `newPage()` and adding
   its pages to the count afterwards — the count would be known only after painting,
   and the plan-date stamp `generate` adds would still reach the last notes page only.
10. **The succession badge is plan content and is drawn to the picture's scale.** It
    names the crops that follow in a bed. Measured before: 47 px tall in a 300-dpi
    PNG (three lines in 4 mm), and on a 1200-dpi printout its text overprinted its own
    box (PF-CAN-59). It takes the object labels' size through the one retarget seam of
    decision 5. Rejected: hiding it through `_hide_overlay_items` like a diagnostic
    badge — a succession plan is what the plan says, and a printed plan is where a
    gardener reads it; a size of its own in exports (7/10 of a label's, as on the
    canvas) — 4.5 pt on paper at 1:100.
11. **On the canvas the badge has room or is left out.** It keeps a constant size, so
    on a plan zoomed out it was larger than its bed. It is drawn where it lies inside
    its bed's outline and covers at most a quarter of it
    (`BADGE_MAX_OWNER_SHARE`), the rule a label follows (§8.9.15). It is painted in the
    label pass, above the plants of its bed. Rejected: shrinking it with the zoom —
    between "readable" and "gone" there is one zoom step, and it would be the only text
    on the canvas that changes size.
12. **A printout's margin is 10 mm, stated in millimetres, in one constant**
    (`PRINT_MARGIN_MM`). The layout was built without a unit, which Qt reads as
    points: 3.5 mm, below what most desktop printers print to, so the sheet could
    differ from its preview; the Print Options dialog counted pages for 10 mm and no
    legend (stated 25 pages for 20 printed, and 2 for 1). `tile_grid` now counts for
    both. A fitted printout stated `1:` width over page width whatever limited the fit:
    1:31 on a plan printed at 1:34, 1:34 on one printed at 1:157. It states the fitted
    scale. Rejected: keeping 3.5 mm and correcting the dialog — the number was never
    chosen, it was a missing unit.
13. **A text note's stored size keeps its meaning; the UI states its height on the
    plan.** `TextItem.font_size` was labelled centimetres and is points / 28.35; a
    stored 1.0 draws an em of 37 cm. Every plan file holds such numbers, so the number
    is frozen and `FILE_VERSION` is unchanged. The Properties panel converts at the
    edge (`em_height_cm`, `font_size_for_em_height`). The unit offered is the font's em,
    not the height of a capital letter: the em is the font size of every other program
    and does not change with the typeface; the tooltip says capitals are about 70 % of
    it. Rejected: storing true centimetres under a new key or a new file version —
    every existing note would need a conversion that depends on the screen resolution
    of the machine that wrote it, which the file does not record; correcting the label
    alone ("points / 28") — true and of no use to a person drawing a plan.
14. **The default plan name is a word of the UI language.**
    `ProjectManager.project_name` returns `tr("Untitled")`. It is on the report's
    cover, the print footer, the window title and in the file name a save dialog
    suggests. **The Agent API's default export file names are not** (review round 1):
    `export_pdf`, `export_dxf` and `export_csv` without a path build the name from
    `ProjectManager.file_stem`, which is the file's stem or the untranslated
    `Untitled`. With one property for both, a German UI named an agent's report
    `Unbenannt.pdf`: a file name a client cannot predict from the tool's contract.

Cross-refs of the addendum: PF-CAN-59; §8.36, §8.9.15, §8.9.16; FR-EXP-01, FR-EXP-03,
FR-EXP-08, FR-VIS-07, FR-VIS-09; debug-verbose case study 225.

**Addendum (plan-truth package, 2026-11-11; shipped in v1.39.1, PR #903) - print and report follow-ups**:

15. **The print "Grid" checkbox paints the canvas grid** (#868). It was stored and
    never read. The grid is drawn after the scene, in the page's own transform, at the
    canvas's grid spacing, with a **stated 0.15 mm pen** converted to device pixels — a
    cosmetic 1-px line at 1200 dpi is invisible. Rejected: rendering a second scene
    with the view's grid pass — that pass is view-level by design and cannot be
    reused through `QGraphicsScene.render`.
16. **A fixed-scale print's pages run top row first; the short row is last** (#871).
    Rows are anchored at the top of the plan, so a height that is not a whole number
    of tiles leaves the plan's **short bottom row on the last page**. That row's strip
    sits at the top of its sheet, with blank paper below it. The old bottom-to-top
    mapping put the remainder first and left sheets 1-2 blank below their strip.
17. **The shopping-list PDF uses the report's one paginator** (#870). `_section_pages`
    and `_render_table_page` now cut and paint it; the footer hook carries the grand
    total on the last page only. The separate `_shopping_list_fits` /
    `_render_shopping_list` loop is gone.
18. **A plant's legend sample includes the sprite's overhang and is 9 mm** (#864).
    `CircleItem` paints the sprite 15 % larger than the footprint; the sample patch
    clipped that foliage, leaving a pale root. The patch is scaled by
    `_LEGEND_SPRITE_OVERHANG` (a drift guard pins it to
    `CircleItem._PLANT_FILL_SCALE`) and the swatch grew from 7 mm to 9 mm with a
    10.5 mm row.
19. **The plant list's Type column is the species' cycle, not the canvas object type**
    (#869). Every gallery plant is `ObjectType.PERENNIAL`, so carrots and lettuce
    read "Perennial". `core.plant_cycle_label` is the one translated cycle vocabulary;
    the plant list, Plant Details, custom-plant table and plant search use it.

Cross-refs: §8.36; FR-EXP-03, FR-EXP-08; PF-CAN-55.
