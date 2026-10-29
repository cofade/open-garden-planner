## Case study: QGraphicsPolygonItem.shape() is the stroke envelope, not the outline (US-12.10/F2.6a, fixed 2026-05-03)

**Symptom**: After fixing the soil-mismatch border to call `closeSubpath()` on `self.shape()`, all polygon edges were finally painted — but the closing edge was visibly *thinner* than the others.

**Wrong theories**:
- Anti-aliasing artifact at the closing vertex (no — clearly a different stroke width).
- `closeSubpath()` not being applied (verified it ran).
- Pen join style needed `MiterJoin` (didn't fix it).

**Key signal**: visually, the closing segment looked like a *single hairline*, while the other edges were a clean 4 px stroke. That's the signature of stroking a thin-band shape: the outline gets a 4 px stroke but the band itself is < 4 px wide.

**Root cause**: Qt's `QGraphicsPolygonItem.shape()` (bypassed at `ui/canvas/items/garden_item.py:1290` `drawPolygon`) does **not** return the polygon's outline. It returns the *stroke envelope* — a closed band path that's the polygon outline expanded by the pen width, intended for hit-testing (so clicking near the edge counts as a hit). Stroking that band's outline produces the observed double-line effect, with the addPolygon-induced open seam reduced to a thin closing line.

**Fix**: When the item has a `polygon()` method (i.e. it *is* a `QGraphicsPolygonItem`), bypass `shape()` entirely and use `painter.drawPolygon(self.polygon())`. That uses the raw vertex list and produces a uniform stroke on every edge with proper miter joins. Rect / circle / ellipse keep the `drawPath(self.shape())` fallback because their `shape()` *does* return a closed outline.

**Lesson**: `QGraphicsItem.shape()` is hit-testing geometry, not drawing geometry. When you need to outline an item, use the item's *primitive* (polygon, rect, ellipse) not its shape. Reach for `painter.drawPolygon`/`drawRect`/`drawEllipse` over `drawPath(self.shape())` whenever you can.

---

