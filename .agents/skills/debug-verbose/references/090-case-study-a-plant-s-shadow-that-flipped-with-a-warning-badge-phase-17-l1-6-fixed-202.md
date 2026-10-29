## Case study: a plant's shadow that flipped with a warning badge (Phase 17 L1.6, fixed 2026-10-11)

**Symptom**: a plant linked to a raised bed, its centre 1 cm inside the bed's east edge, stood on the bed's soil (base 38 cm in the 3D record and in the 2D shadow caster). When the companion check put the red antagonist badge on it, both read 0 — the plant dropped to the ground and its shadow lost 38 cm of base. Badge off: 38 again. No test failed.

**Theories entertained (wrong)**:
1. *"Every membership decision must ask the same point, then they cannot disagree."* That was the previous fix, and it was the cause: the lift had been given the link decisions' point.
2. *"The centre of `boundingRect()` is the geometric centre plus symmetric decorations."* True for the shadow margin, the companion highlight and the spacing ring. Not for the badge.

**What the instrumentation revealed** (a ten-line probe printing the point and both bases, run on the tree with the previous fix):

```text
[BASE] badge off: link point (699.0, 400.0)  3D base 38  2D caster base 38
[BASE] badge on : link point (700.8, 401.8)  3D base 0  2D caster base 0
[BASE] badge off: link point (699.0, 400.0)  3D base 38  2D caster base 38
```

The point moved by 1.8 cm in x AND y. Nothing about the plant's geometry had changed.

**Root cause**: `CircleItem.boundingRect()` grows towards +x / +y only while the badge shows (`base.adjusted(0, 0, overflow, overflow)`, `overflow = 0.3 * min(0.45 * radius, 12)`), so its centre moves by half of that. `footprints.bed_membership_point` is `mapToScene(boundingRect().center())` — fine for the shipped link decisions, which have always used it, and wrong as the answer to "where does this plant stand".

**Fix**: the lift asks `footprints.standing_point` — the item's stable geometric centre, the anchor of its outline and the origin of its 3D record. The link decisions keep their point; one predicate (`shape_contains`) serves both. `tests/integration/test_scene3d_base_stacking.py::TestWhereAPlantStandsDoesNotDependOnABadge` toggles the badge and compares the record, the caster and the real overlay's path; `::TestWhichPointEachDecisionAsks` pins the point of each decision on a probe where the two points differ.

**Lesson**: a bounding rect is a PAINT rect. Before using one as geometry, list everything that changes it — here a badge, a highlight, a margin, a ring — and ask whether each is symmetric. And when a refactor claims "identical behaviour" for a value that two candidates could supply, build one probe where the candidates differ: swapping them had passed all 114 related tests.


