## Case study: sun badge footprint, malformed species and collected observers (F3, 2026-10-12)

**Symptom.** Review found an L-shaped imported plant's badge outside its footprint and a selected legacy tree raising in the refresh timer. The complete suite also caught an exception during delayed QObject destruction.
**Wrong theories.** None adopted before reproducing the exact shape, accepted metadata, and captured teardown traceback.
**Evidence.** The imported/grouped regression failed `path.contains(QRectF(1189, 1319, 22, 22))`; accepted string/list species metadata failed at `species.get` with AttributeError. The suite traceback identified `disconnect -> Channel.disconnect: ValueError("listener is not connected")`. All regressions pass after correction.
**Root cause.** Bounding rectangles contain empty space in concave footprints. Evaluation and canopy paths normalized species differently. A weak observer can be pruned during cyclic collection before Qt emits destroyed.
**Fix.** Fit the complete badge rectangle inside the undecorated QPainterPath, normalize species once for both consumers, and make destruction cleanup idempotent for an already-removed subscription. Preserve navigation and item geometry across grouped save/load.
**Lesson.** Test actual containment rather than rectangle placement, exercise accepted legacy metadata, and allow both Python collection and Qt destruction to own cleanup without raising.

