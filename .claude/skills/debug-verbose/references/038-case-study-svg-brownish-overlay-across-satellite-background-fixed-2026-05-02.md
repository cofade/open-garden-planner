## Case study: SVG brownish overlay across satellite background (fixed 2026-05-02)

**Symptom**: After the patternTransform Y-flip fix, SVG export still showed a brownish-orange wash across most of the canvas, hiding the satellite background. PNG export was correct. A "transparent test" (forcing every `opacity="0.x"` to 0) made the satellite reappear — proving garden items were the culprit, not the satellite layer or canvas color.

**Theories entertained (wrong)**:
- Satellite Z-order wrong (it isn't — `BackgroundImageItem.setZValue(-1000)`)
- Canvas background color leaking through (`#f5f5dc` beige is fully opaque, never the brownish observed)
- Pattern tile origin offset
- Opacity stacking on transparent group hierarchy

**What instrumentation revealed**: A small Python script decoded every base64 pattern tile and inspected each `<rect>` in the SVG. Output:

```
<rect x="1035.83" y="393.78" width="4382.73" height="4382.73"/>   ← roof tile
<rect x="3366.42" y="2800.94" width="1408.86" height="1408.86"/>  ← roof tile
clipPath elements: 0     ← Qt did NOT serialize the painter clip region
clip-path attributes: 0
```

The texture rects were the **painter's clip bounding rect**, not the polygon shape. The actual polygon was serialized in the *preceding* "shadow" group: `<g fill="#000000" transform="..."><path d="M2729...Z"/></g>` followed immediately by `<g fill="url(#texpattern_X)" transform="..."><rect x="..." y="..." .../></g>`. Qt clips the rect against the painter clip region during native rendering, but the SVG contains no `<clipPath>` for the viewer to honor. So the rect bleeds across the entire canvas.

**Root cause**: `QSvgGenerator` does not emit `<clipPath>` elements for `QPainter::setClipRegion`/`setClipPath` calls. Texture-filled `QGraphicsItem`s end up as a giant unconstrained rect in the SVG.

**Fix**: Post-process the SVG (`ExportService._fix_svg_qt_texture_clipping`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's path (preserving its transform), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 in document order with a `used_textures` set; a naive "scan 4000 chars ahead" matched the same texture from multiple shadows and produced overlapping replacements that corrupted the XML tree (mismatched `</g>` tags). Visual validation: render SVG via Edge headless (`scripts/svg_preview.py`) — Qt's QSvgRenderer is too forgiving and hides this class of bug.

**Lesson**: Qt's `QSvgGenerator` is *not* a faithful serializer of painter state. Anything beyond shape + fill + stroke (clip regions, composition modes, painter transforms applied to brush textures) must be recovered in post-processing. When pairing emitted constructs (shadow ↔ texture), walk both lists in lockstep with a `used` set — never use a forward window scan, because Qt emits empty bookkeeping groups that throw off positional heuristics. Always validate SVG output in a real browser, not just QSvgRenderer.

---

