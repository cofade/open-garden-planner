## Case study: a snapped corner cut the bed it only grazed (PR #783, fixed 2026-11-09)

**Symptom**: after the split tool became scene-wide, a line whose first pick
snapped to a bed's corner and whose second pick went away from the bed removed
the bed and created two pieces. The user had not drawn across it. The bug was
found by the senior review's probe, not by a green test: every existing test
picked points well outside the outline.

**Theories entertained (wrong)**:
- The infinite cutting axis was doing this, and only a finite segment could fix
  it — but the infinite axis is the intended knife line; the selection of which
  shapes to cut was wrong.
- The canvas snap had moved the pick onto an arbitrary nearby point — the snap
  was correct; the pick really was on the corner, and "on the outline" was
  being treated as "inside".
- `segment_crosses_path` needed an epsilon trim at both ends — trimming would
  remove an endpoint touch, but not a segment that runs along an edge.

**What measurement revealed** (a probe of `QPainterPath.intersects` on a
rectangle):

```
cross        True
inside       True
edge         True
outside      False
```

A zero-width line path is reported as intersecting a filled path when it only
touches the outline; `contains` on a boundary point is also True. The first
predicate was `path.intersects(segment)`, so a corner pick selected the bed and
the infinite axis then cut it. The real tool probe reproduced it: source
removed, two pieces, one undo step.

**Root cause**: `QPainterPath.intersects` answers "do these paths share any
point", and a boundary point counts; the split needs "does the segment pass
through the interior", which is a different question.

**Lesson learned**: when code means "crosses", prove interior overlap, not
contact. `segment_crosses_path` now splits the segment at its crossings with the
flattened outline, samples each interval between crossings, and accepts only a
midpoint whose points offset to BOTH sides are inside — a boundary-aligned
segment has one side outside. Pin the outward corner, edge, tangent and true
corner-to-corner cases; a happy-path pick outside the shape proves nothing
(PF-CAN-47).
