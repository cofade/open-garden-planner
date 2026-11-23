# Case study: A construction guide blocked reference-point placement (#666)

**Symptom.** Opening the Reference point dialog raised an AttributeError on
plans with a construction line.

**Wrong theory.** Any selectable item that contributed a straight edge
could also serve as a binding parent.

**Key evidence.** The targeted placement test created one ConstructionLineItem.
The failing call was point_dialog → parent_name → item.name.
Construction lines have snap geometry but lack the document-shape attributes
used by the parent picker.

**Cause and fix.** Candidate discovery used geometric capability alone.
Limit new bindings to rectangles and polygons. Keep existing bindings readable
through a defensive label formatter.

**Lesson.** An item can participate in snapping without participating in
document relationships. Test candidate scans with unrelated guide items present.
