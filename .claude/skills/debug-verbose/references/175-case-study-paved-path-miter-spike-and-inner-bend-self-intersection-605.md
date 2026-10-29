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
normals `v = offset * (n1 + n2) / (1 + n1 . n2)` with a collinearity guard (`dot_n > -0.99`),
trimming overlapping segments. Pinned by `tests/unit/test_path_style_paint.py`.
**Lesson.** When offsetting polylines for stroke borders or fills, inner corners require
line-line intersection trimming to prevent crossing loops, and fill join styles must match
border join styles.
