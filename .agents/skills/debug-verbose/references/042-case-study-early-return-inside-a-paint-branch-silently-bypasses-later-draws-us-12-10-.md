## Case study: early `return` inside a paint() branch silently bypasses later draws (US-12.10/F2.6b, fixed 2026-05-03)

**Symptom**: GARDEN_BED rectangles correctly showed soil-mismatch borders. RAISED_BED rectangles never did. Both pass `is_bed_type()`, both have a `_soil_mismatch_level`, both call the same paint hook.

**Wrong theories**:
- `is_bed_type(RAISED_BED)` returning False (verified true).
- Pixmap rendering covering the border (no — pen has alpha 220).
- Selection-handle code stealing focus (irrelevant to paint).

**Key signal**: instrumenting paint() showed the `ui/canvas/items/rectangle_item.py:349` `_draw_soil_mismatch_border` call *never ran* for raised beds. That code is unconditional within `is_bed_type` — so something earlier was returning.

**Root cause**: an early `return` at the end of the RAISED_BED furniture-pixmap block bypassed it — RAISED_BED is rendered as a *furniture pixmap* (the wooden-frame look), and that branch returned before reaching the border. Every line below that — grid overlay, rotation indicator, *and the soil mismatch border* — was bypassed for raised beds. The original code reviewer of US-12.10d wired the border thinking it was reachable for all bed types.

**Fix**: Add a second `_draw_soil_mismatch_border` call *inside* the early-return branch, just before the `return` — now `ui/canvas/items/rectangle_item.py:320` `_draw_soil_mismatch_border`. Both the pixmap path and the standard path now paint the border.

**Lesson**: When wiring a new draw call into an existing `paint()` method, search the method for *every* `return` statement and confirm each control-flow path reaches your new code. Better: factor reusable post-paint hooks into a method called at every exit point. An early-return inside an `if` block is a classic stale-call site for new features added later.

---

