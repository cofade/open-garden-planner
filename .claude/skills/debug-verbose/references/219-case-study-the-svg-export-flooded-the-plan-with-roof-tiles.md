## Case study: the SVG export flooded the plan with roof tiles — the generator drops clips, brush transforms and source rectangles (#787, fixed 2026-11-09)

**Symptom**: the SVG export of the family-garden example, opened in a browser, showed the house's roof-tile texture over about 70 % of the drawing and the glasshouse's glazing bars across the plan. Sun shadows had heavy dark outlines. The PNG export of the same plan was right. The file declared a width of 395.8 mm for a 297 mm export.

**Theories entertained (wrong)**:
- *"The post-processor has to learn the new painters."* `ExportService._fix_svg_qt_texture_clipping` paired a black "shadow" group with the next texture group in the written file. The parametric roof (#768) does not write that pair, so nothing was matched — but teaching a regular expression one more painter leaves the next painter uncovered again.
- *"Switch the generator to SVG 1.1 and it writes the clips itself."* It does (`QSvgGenerator(SvgVersion.Svg11)`), and for one clip the path is exact. But two stacked clips come out as a staircase, and `scene.render()` always stacks its own target rectangle under an item's clip.
- *"The pattern tiles are upside down under the Y-flip"* (the 2026-05 reading behind `_fix_svg_pattern_yflip`). Measured against the PNG, they are not.

**What instrumentation revealed** (a probe that painted one clipped, transformed pattern fill into both generator modes and printed the file):

```
tiny12: clipPath: 0     <pattern id="texpattern_…" … >            ← no patternTransform although brush.setTransform(rotate 30)
svg11 : clipPath: 3     <clipPath id="clipPath3"><path d="M225,200 L250,200 L250,199 L250,197 …   ← a staircase in whole units
QSvgRenderer(svg11) == QSvgRenderer(tiny12), byte for byte           ← the renderer ignores clip-path
Edge(svg11): the circle is clipped                                    ← a browser honours it
[TXT] 'Hello note' Arial 28.0 … → <text … font-family="Segoe UI" font-size="12">   ← the note's font lost on replay
```

and, per bundled example, the difference between the rasterised SVG and the PNG export: mean 25–58 of 255 with 32–71 % of 4 × 4 blocks off by more than 32.

**Root cause**: `QSvgGenerator` is not a faithful serializer of painter state (Qt 6.12). It drops a `TexturePattern` brush's own transform, ignores a pixmap's source rectangle, writes no clip in SVG Tiny 1.2 mode, and in SVG 1.1 mode writes the intersection of two clips as an integer region — `QPainter.clipPath()` falls back to `clipRegion()` as soon as the clip stack holds two entries. The roof painter needs all of it at once: two clipped halves, each with a rotated (and one mirrored) brush, drawn as one oversized rectangle. `QSvgRenderer` ignoring `clip-path` is why the defect could never be seen in a Qt-rendered preview or pinned by a Qt-rendered test.

**Fix** (`services/svg_export.py`): the scene is painted into a recording `QPaintEngine` (declared with the generator's own feature set, so `QPainter` prepares the same calls) that keeps every draw call with its state and the exact clip as a path. The recording is replayed into a `QSvgGenerator(Svg11)`: a clipped fill becomes its outline intersected with the clip, a clipped stroke its stroked outline intersected with the clip, a brush transform moves into the world transform. Only a clipped picture or clipped text keeps a real `<clipPath>`, set as a single exact clip. The two post-processors were removed. The file states its size exactly (`width`/`height` in mm, a view box in 1/300 inch).

**A second bug the replay exposed**: a `QFont` handed out by a text layout carries no record of which properties were set on it, and `QPainter.setFont` resolves such a font entirely from the device default. The replay rebuilds the font with explicit setters (`_explicit_font`).

**After**: mean difference 0.2–2.8 of 255, at most 1.0 % of blocks off (QSvgRenderer); in headless Edge, per pixel, mean 2.7–3.1 with 1.1–1.9 % of pixels off, against 22–50 and 39–67 % before.

**Lesson**: when a serializer is unfaithful, do not repair its output by pattern — put a recorder under the painter and decide yourself what is written. And check what your test renderer ignores before trusting a green picture: `QSvgRenderer` cannot see a `<clipPath>`, so write geometry that needs none, and assert the one remaining clip on the file's structure.
