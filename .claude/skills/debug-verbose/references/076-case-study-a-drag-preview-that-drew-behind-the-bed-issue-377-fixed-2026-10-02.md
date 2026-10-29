## Case study: a drag preview that drew behind the bed (issue #377, fixed 2026-10-02)

**Symptom**: While drawing a plant into a raised bed, the dashed preview circle was
invisible for the whole drag - it showed only where it poked outside the bed silhouette - and
the plant "popped" into the front on release. With a plant much smaller than the bed the
entire preview was hidden and placement was blind, guided only by the `Dist / Winkel` HUD.
Reproduced with raised and polygon beds alike.

**Wrong theories**. (1) A paint-order regression from the per-object stacking work (#338) -
plausible, because stacking order was the most recent change to z-values. (2) The preview
item being inserted into the wrong parent. (3) The bed's own paint() drawing over everything.
All wrong. `git log -S "setZValue" -- core/tools/circle_tool.py` returned nothing: the
preview had *never* had a z-value, so it predated #338 entirely.

**Key evidence**: two measurements that made the bug a two-line fact.

```
bed z            = 50.0
preview circle z = 0.0        <- QGraphicsEllipseItem, not a CircleItem
bed beats preview = True
final plant z    = 66.67       <- after release, via the derived-z refresh
plant beats bed  = True
```

`0.0 < 50.0` during the drag, `66.67 > 50.0` after it. Real items get a derived z strictly
inside `(0, 100)` from `CanvasScene._refresh_layer_z`; a bare `QGraphics*Item` keeps Qt's
default `z = 0`, so it loses to everything.

**Root cause**: the preview primitives were never assigned a z-value, and the derived-z
system silently outranked them. A class defect, not one tool: **11** modules built previews
with no z-value.

**A wrong census nearly cost the fix**: the issue's own list of affected modules named 13,
omitting `construction_tool.py` (which does build previews) and including `text_tool`,
`fillet_tool`, `chamfer_tool` (which build no preview item at all - zero grep matches). The
fix therefore re-derived the set from source, and the drift-guard test does the same rather
than trusting a hand-written list.

**Fix**: `core/tools/preview_z.py` defines the reserved band (`999` fill, `1000` line,
`1001` label, `1002` handle), deliberately below `minimap_widget._OVERLAY_Z_MIN` (`10_000`)
so a preview stays visible in the minimap thumbnail. Every preview construction site calls
`setZValue`.

**Lesson**: (1) **No test had ever drawn a preview over an existing item** - every tool test
drew on an empty canvas, where `z = 0` is enough. A green suite is evidence only about the
paths it exercises. (2) When a bug report hands you a list of affected sites, treat it as a
symptom description, not a census - re-derive the set from the source. (3) Measured z-values
turned a "painting problem" into a two-line inequality; instrumenting the numbers beat
reading the paint code.


