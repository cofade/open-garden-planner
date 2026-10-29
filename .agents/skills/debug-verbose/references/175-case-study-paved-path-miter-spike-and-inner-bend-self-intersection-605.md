## Case study: Paved path outer bend miter spikes and inner bend self-intersections (#605)

**Symptom.** Paved path corners had visual artifacts: outer bends had an excessively sharp
miter fill spike protruding past the border chord, and acute inner bends (< 60°) formed
self-intersecting loops and crossing spikes.
**Wrong assumption.** Standard `MiterJoin` on the path base fill was expected to match
the border chord, and simple parallel offset without bend trimming was sufficient for inner bends.
**Evidence.** Visual inspection and geometry tests in `ui/canvas/items/path_style_paint.py`
showed that outer corner fills used `MiterJoin` while border outlines used bevel/chord joins,
causing the fill to overshoot the border. On inner corners, simple line segment offsetting
without intersection calculation caused overlapping segments to cross each other.
**Fix.** Changed paved path base fill pen join style from `MiterJoin` to `BevelJoin` to match
the border chord. In `_offset_path`, compute exact 2D line intersection for adjacent inner bend
directed lines, trimming only when their intersection lies inside both finite segments.
A review probe found `[PATH605] dot_n=-0.9961946980917455 cross_u=0.0871557427476582
lengths=(100000.0, 100000.0) accepted=False`: the initial angle cutoff rejected a valid
175-degree inner intersection. Cross-product intersection avoids dividing by the nearly
zero `1 + dot` at near-reversals. Degenerate segments are skipped rather than given a
fabricated direction; duplicate corner and end vertices must leave the border unchanged. Pinned by `tests/unit/test_path_style_paint.py`.
**Lesson.** When offsetting polylines for stroke borders or fills, inner corners require
line-line intersection trimming to prevent crossing loops, and fill join styles must match
border join styles.

**Review regression evidence (PR #645).** Six new cases failed before correction: both
turn directions at 175 and 179.9 degrees, and duplicate corner/end vertices. A parity
guard now compares painter borders with the Qt-free relief offset over eight turn angles
and both sides. This preserves the existing separate Qt and numpy representations
without silently giving the bake and relief different corner contracts.
