## Case study: a plant vanished behind the bed drawn around it (#629)

**Symptom.** The owner's manual pass on #627: a raised bed, container, wall planter or
trellis drawn AROUND a standing plant hid it in 2D. 3D still drew the plant on the soil,
and its sun badge was gone with it. A click at the plant's centre selected the bed.
**Wrong theory.** A paint or z-value problem in the bed's fill — repainting the bed, or
forcing the plant's `zValue()` up at the click site, changed nothing that lasted. So did
"the clamp will lift it when the bed is added": the bed was added after the plant.
**Evidence.** A two-line dump of the two z values was enough:
`plant 0.0000100` / `RAISED_BED 0.0000200` for all five parent types, while `GARDEN_BED`
read `-750.0000000` — the ground band, which is why the in-ground bed looked immune. The
clamp in `core.stacking.normalize_order` was doing exactly what it was told: it follows
`StackEntry.parent_id`, and `_stack_entries` filled that from `parent_bed_id` only. The
owner's gesture makes no link (#443), so the entry had no parent and the plant sorted
below a newer bed.
**Root cause.** The clamp's parent was BOOKKEEPING (the link), while the question the
user asks — "which bed is this plant in?" — is GEOMETRY, which the lift and the sun
estimate already answer geometrically (`footprints.standing_point` +
`shape_contains`). Three subsystems, three answers.
**Fix.** One answer: `CanvasScene._derived_plant_parent` (link, else the smallest
plant-parent whose outline contains the stable centre) is asked by the derivation AND by
the per-command check that compares a plant's z with that parent's — so the check cannot
measure a different rule than the thing it checks. `Command.changes_containment` scopes
the scan (adds/deletes neutral), and the parents' shapes are cached for the pass: without
that cache the adversarial plan cost 1.7 s per command instead of 133 ms.
**Lesson.** When a user says "X is not on top of Y", first ask WHICH SUBSYSTEM answers
"which Y is X in" — and make them all call the same function. A symptom that spares one
object TYPE is a classification difference, not a rendering bug. And a probe that
re-implements the derivation is a second truth waiting to drift; compare against the
derivation's own output instead.


