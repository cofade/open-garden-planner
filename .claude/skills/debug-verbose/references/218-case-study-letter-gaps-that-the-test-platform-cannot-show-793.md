## Case study: letter gaps in a zoomed text note that the test platform cannot show (#793, fixed 2026-11-09)

**Symptom**: a text note on the canvas read "thy me" and "f ictional" at some zooms and was fine at others. The same survey reported the scale bar's label at 1.25:1 on soil although the code drew a white "outline" under it.

**Theories entertained (wrong)**:
- The whole point size is the cause (`round(cm * 28.35)`), so `setPointSizeF` alone fixes it. It does not: the size was 0.8 % off, the gaps were 20 %.
- The fix needs all three of an unhinted font, an exact `setPointSizeF` and `setUseDesignMetrics(True)`. It needs one: the unhinted font alone gives the same letter gaps to 0.01 px at every zoom, and 11.906 pt and 12 pt give the same line width (269.17 px), because the pixel size is whole either way.
- A regression test can compare the gaps on a rendered note. On the suite's platform it shows nothing, before or after.
- The scale bar's halo is too thin or too transparent. There was no halo.

**What instrumentation revealed** (two probes: glyph x positions from the note's own text layout at size s against size 8s / 8, and the gaps between ink runs of a rendered note against the 12x render scaled down):

```
[KERN] windows   old: max |x - x8/8| = 10.25   new: 1.90   old + design metrics: 1.63
[KERN] offscreen old: max |x - x8/8| = 0.00    new: 4.88   <- pixel sizes are whole here
[KERN] windows   zoom 3.3: worst gap error 2.85 px -> 1.15 px     zoom 2.2: 2.18 px -> 0.79 px
[KERN] windows   unhinted, whole pt: 1.15 px / 0.79 px     unhinted, exact pt, design metrics: 1.15 px / 0.79 px
[KERN] offscreen zoom 3.3: worst gap error 1.00 px -> 1.00 px     <- no difference at all
```

On Windows a hinted font rounds every glyph advance to the pixel grid of the one size the note is laid out at; the view then scales those rounded advances while it draws each glyph outline exactly, and the rounding becomes a visible gap. Design metrics remove 84 % of the deviation with the whole point size still in place. The offscreen platform does not hint at all, so the defect does not exist there, and it rounds a fractional point size to whole pixels, so the "linearity" number even gets worse.

For the scale bar the probe was a count of changed pixels: `painter.drawText` with a 3 px pen changed exactly the glyph pixels. A pen does not outline text; only a stroked glyph path does.

**Root cause**: a font set up for the screen (`QFont(family, whole_points)`, default hinting) on an item the view scales; and a halo drawn with an API that cannot draw one.

**Fix**: `TextItem._apply_font` and the callout's text set `PreferNoHinting` (the change itself came with #789, for the SVG export; the two other settings were built here first, measured, and taken out). `ui/canvas/items/halo_text.py` strokes `QPainterPath.addText` outlines for every canvas label. The regression test pins the font setup, because pixels cannot show the defect on the suite's platform; the contrast tests measure pixels, because they can (`tests/integration/test_canvas_legibility.py`). PF-CAN-52.

**Second round (same issue, found by looking at the captures)**: every contrast test passed, and in the picture the last letter of "Perennial border" stood outside its halo. The halo was the stroked outline of `QPainterPath.addText`; the glyphs were drawn by the item's own text layout. Two layouts of one text:

```
[HALO] windows   bold 10 pt 'Perennial border': layout 108.16 px, outline ends at 104.22 px
[HALO] windows   bold  7 pt 'Stepping stones' (an export's size): text ends 6.43 px past its outline
[HALO] offscreen bold 10 pt: painted text ends in column 119, filled outline in column 104
```

The contrast helper averages over the glyphs that do have a halo, so it could not see two that had none. Tried first: unhinted label fonts. The two layouts then agree to 0.02 px, but the small area label lost its dark strokes and the contrast test no longer found it. Kept: `text_outline` lays the text out as `QGraphicsSimpleTextItem` does and takes each glyph's outline where that layout puts it. The pin compares the first and last ink column of the painted text and of the filled outline, and here it fails on the suite's platform too. The same look at the captures showed an object's area label missing whenever its name was on: the two are stacked closer than the declutter's gap, and the layout took them for strangers.

**Lesson**: measure each part of a fix alone before keeping all of them. A metric that averages (contrast over all ink) says nothing about the worst glyph: look at the picture, then write the test for what the picture showed. Before writing a pixel test for a font defect, run the probe on the platform the suite uses. If the number does not move there, pin the cause and write the measured numbers of the real platform next to it. And measure a "halo" before believing the comment that names it.
