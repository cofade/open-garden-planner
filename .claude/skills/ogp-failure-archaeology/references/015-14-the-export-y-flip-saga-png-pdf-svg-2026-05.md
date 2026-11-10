## 14. The export Y-flip saga (PNG/PDF/SVG, 2026-05)

Source: debug-verbose case studies (2026-05-01/02) + §11.4 export entries. Four
sequential incidents from the CAD-style `scale(zoom, -zoom)` canvas (ADR-002):

1. **Empty PNG**: `QRectF(0, H, W, -H)` as render target — negative-height rects are
   `isEmpty()` in PyQt6, so `scene.render()` painted zero pixels. Fix: painter pre-flip
   (`translate(0, H_px); scale(1, -1)`), H in **image pixels**, not cm.
2. **PDF narrow strip**: QPdfWriter's painter starts with a **non-identity** transform
   (margin handling), so the mathematically-correct pre-flip overshot. Fix: render to a
   temp `QImage` then `drawImage` — never assume identity on non-QImage devices. Also:
   `QPdfWriter` needs `setResolution(72)` before `setPageLayout()`.
3. **SVG upside-down textures**: `QSvgGenerator` stores pattern tiles un-flipped; under
   the Y-flip they render inverted (brownish mush). Fix: post-process `patternTransform`.
4. **SVG texture bleed**: `QSvgGenerator` never serializes painter clip paths — texture
   rects (the *clip bounding rect*, not the shape) washed across the whole canvas. PNG
   unaffected (native renderer applies the clip). Fix: post-process paired
   shadow-group→clipPath wrapping, lockstep with a `used` set (a forward-window scan
   corrupted the XML). Evidence tool: decode base64 tiles + count `<clipPath>` elements
   (`0` was the smoking gun). **Validate SVG in a real browser** — `QSvgRenderer` is too
   forgiving and hides this class of bug (`scripts/svg_preview.py`).
- Meta-lesson: Qt's SVG/PDF generators are NOT faithful serializers of painter state;
  anything beyond shape+fill+stroke must be recovered in post-processing.
- Status: closed. Related tests: `tests/unit/test_export.py`,
  `tests/unit/test_scene_rendering.py`.
- **Re-opened and settled differently, 2026-11 (#787).** Incidents 3 and 4 were
  "fixed" by rewriting the written file by pattern. The clip pairing matched one
  painter's output; the parametric roof and glasshouse (#768/#769) did not write
  that shape, nothing was paired, and the roof texture flooded the drawing again.
  The pattern flip turned out to be unnecessary when measured against the PNG.
  Both post-processors are gone: the export records the scene below the painter
  (`services/svg_export.py`) and replays it with clips cut into the geometry and
  brush transforms moved into the world transform (PF-CAN-53, debug-verbose case
  study 219). The same slice found that a `paint()` which sets a clip without
  `IntersectClip` paints on a print tile's margin (PF-CAN-54), and that exports
  must retarget only constant-pixel-size text (PF-CAN-08, #789). Pinned by
  `tests/integration/test_svg_export_fidelity.py`,
  `tests/integration/test_pdf_report_pages.py` and
  `tests/integration/test_export_text_notes.py`.

---

