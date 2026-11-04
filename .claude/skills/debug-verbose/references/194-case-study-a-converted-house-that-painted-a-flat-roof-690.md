# Case study: a converted house that painted a flat roof (#690, manual test 2.1)

**Symptom.** Manual testing converted a 1600 x 750 rectangle to a HOUSE beside a
natively drawn house. In 2D the converted house's roof-tile rows ran straight
across the ridge, while the drawn house's tiles lapped away from it on both
sides. In 3D the converted house's roof also looked much shallower.

**Wrong theories, in the order they were tried.**

1. *The ridge from the type change is wrong.* A probe printed both houses'
   `params["ridge"]`, slope and roof z-range: identical for the same outline
   (`((-800, 0), (800, 0))`, slope 0.568, z 202.96-450). Rejected.
2. *The fill transform (#665) is composed differently.* Both items had an
   identity `fill_transform`; the rectangle's pattern had no transform at all.
   Rejected.
3. *The 3D pitch metadata differs.* Both houses had automatic roof style,
   pitch and overhang. Rejected.
4. *The 2D painter is shared.* It was not: `PolygonItem.paint()` branched to
   `_paint_with_ridge` for a HOUSE, but `RectangleItem.paint()` always called
   `super().paint()`, the plain `QBrush` fill.

**Key evidence.** Installing the same two-colour probe brush on both items and
rendering the same outline showed the sequences: the polygon's walked
`RBBRBB` outward from the ridge (correct down-slope phase), the rectangle's
stayed in one phase because it was a flat fill. After the fix the two rendered
images were byte-identical over all eight house/rotation cases.

The 3D apparent difference was not a defect: the houses in the screenshot had
different footprints/heights, and the wide house's roof is flattened by the
eave floor (450 cm ridge, 375 cm half-depth -> 29.6 degrees, where a narrower
house keeps the 38-degree style pitch). Records for the same outline are
identical, so no 3D change was made.

**Root cause.** One semantic object (a HOUSE) has two item classes, and #690
taught the data path (`ChangeObjectTypeCommand`, `roof_ridge_link`) about both
but not the paint path. The ridge existed and followed the host; only the
renderer that consumes it was missing.

**Fix.** `ui/canvas/items/roof_paint.py` now owns the whole ridge-aware
painting routine (`paint_roof_with_ridge`), moved out of `PolygonItem`.
`PolygonItem._paint_with_ridge` delegates to it, and `RectangleItem.paint()`
calls it for a HOUSE with a live linked ridge. `tests/unit/test_roof_tile_orientation.py`
now runs every orientation for both classes and adds a byte-identical render
comparison.

**Lesson.** Making a type convertible is not only a command/metadata job: check
every consumer of the data path, including each item class's `paint()`. A
derived visual has two seams, geometry and rendering, and both must be shared
across the classes that can represent the object. Measure the 3D record before
"fixing" a perspective illusion; identical records plus different footprints
explain a slope difference.
