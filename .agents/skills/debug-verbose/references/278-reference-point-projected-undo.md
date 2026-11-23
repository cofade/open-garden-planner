# Case study: Undo shifted a reference point (#666)

**Symptom.** A datum nudged toward an outline vertex did not return to its
starting coordinate on Undo. Renaming a datum left off the contour by a parent
rotation also moved it.

**Wrong theory.** A symmetric move delta would restore the same coordinate
even when the item's position callback altered the requested move.

**Key log.** \`[REF-UNDO] current=(106, 100) proposed=(86, 100) projected=(100, 100)\`.
The call stack led from Move and Align to the position change callback. Undo
applied the inverse request and reached x=120 cm, which was on the valid edge.

**Cause and fix.** The delta requested by the caller differed from the result
returned by projection. Capture the actual before and after coordinates; replay
them without projection. Only a new contour binding projects a properties edit.

**Lesson.** Treat any Qt callback that substitutes a requested coordinate like
a geometry solver. Test the before state, the adjusted result and both directions
of history at a contour limit.
