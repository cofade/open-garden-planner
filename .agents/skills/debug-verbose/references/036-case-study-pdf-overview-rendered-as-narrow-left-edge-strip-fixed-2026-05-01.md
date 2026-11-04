## Case study: PDF overview rendered as narrow left-edge strip (fixed 2026-05-01)

**Symptom**: PDF export page 2 showed the scene image as a thin strip at the left edge, not filling the content area. Despite correct code for the painter pre-flip, position was wrong.

**Theories entertained (wrong)**:
- Wrong content_rect coordinates
- Painter viewport not matching page layout
- scale() applied before translate()

**What instrumentation revealed**: Added `print(f"[PDF] initial painter.transform(): {p.worldTransform()}")` before the pre-flip. Output showed a non-identity initial transform (QPdfWriter applies margin offsets before the painter is returned). The formula `translate(0, cr.top + cr.bottom)` assumed an identity baseline — invalid for QPdfWriter.

**Root cause**: QPdfWriter's painter has a non-identity initial transform from margin handling. The pre-flip baseline is shifted, so `translate(0, top+bottom)` overshoots.

**Fix**: Switch to "render scene to temp QImage (which has reliable identity transform), then embed with `painter.drawImage(content_rect, img)`". Immune to QPdfWriter's initial transform. See `_scene_to_image()` in `pdf_report_service.py`.

**Lesson**: Never assume QPainter starts at identity when targeting non-QImage devices (PDF, printer, SVG). Always read `painter.worldTransform()` first.

---

