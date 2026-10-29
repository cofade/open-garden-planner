## Case study: PNG/SVG export empty after Y-flip fix (fixed 2026-05-01)

**Symptom**: PNG export produced a correctly-sized image filled only with the canvas background color (#f5f5dc). No shapes visible. SVG had file content but rendered empty in browser.

**Theories entertained (wrong)**:
- Scene items not in canvas_rect bounds
- Wrong source rect passed to scene.render()
- DPI calculation error

**What instrumentation revealed**: Added `print(f"[EXPORT] target_rect={target_rect}  isEmpty={target_rect.isEmpty()}")` before `scene.render()`. Output: `isEmpty=True`.

**Root cause**: Previous Y-flip fix used `QRectF(0, H, W, -H)` as the target rect. In PyQt6, `QRectF` with negative height is considered empty — `isEmpty()` returns `True`. Qt's `scene.render()` clips to the target rect, so an empty rect = zero pixels painted.

**Fix**: Replace negative-height rect with painter pre-flip: `painter.translate(0, H_px); painter.scale(1.0, -1.0)` then call `scene.render()` with a normal positive rect. H_px must be the **image height in pixels**.

**Lesson**: Always test `isEmpty()` on any QRectF used as a render target. Negative-dimension rects are valid geometry in some contexts but empty in Qt's rendering pipeline.

---

