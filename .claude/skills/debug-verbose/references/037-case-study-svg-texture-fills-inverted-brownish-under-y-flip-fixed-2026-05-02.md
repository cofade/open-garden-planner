## Case study: SVG texture fills inverted/brownish under Y-flip (fixed 2026-05-02)

**Symptom**: SVG export showed correct shapes and satellite image but a brownish overlay covering the scene. Texture-filled polygons (roof tiles, gravel) appeared wrong. PNG export was correct.

**Theories entertained (wrong)**:
- Satellite image color space issue
- Some polygon covering full canvas with wrong fill
- Pattern tiling origin offset

**What instrumentation revealed**: Extracted pattern tiles from the SVG with a Python script (`scripts/validate_exports.py` + base64 decode). Tile images themselves were correct (e.g. grass texture shows green). Inspected SVG transforms: main group had `matrix(0.213774, 0, 0, -0.213774, 0, 877)` (scale + Y-flip). Pattern elements had no `patternTransform`. Rendered SVG to PNG via `QSvgRenderer` — confirmed brownish overlay visible.

**Root cause**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. The pattern tile images are stored in their natural (non-flipped) orientation. When the scene Y-flip transform is active, each tile renders upside-down within the Y-flipped coordinate space — a texture tile that looks like roof tiles right-side-up looks like abstract brown when flipped.

**Fix**: Post-process the SVG after `painter.end()`: read the file, find all `<pattern>` elements, add `patternTransform="matrix(1,0,0,-1,0,{height})"` to flip the tile back. See `ExportService._fix_svg_pattern_yflip()`.

**Lesson**: Qt's SVG generator does NOT propagate painter transforms into pattern tile images. Any painter-level Y-flip requires explicit `patternTransform` compensation as a post-processing step.

---

