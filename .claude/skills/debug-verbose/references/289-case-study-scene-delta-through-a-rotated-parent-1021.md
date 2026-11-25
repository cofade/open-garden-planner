# Case study: a scene delta applied through a rotated parent moved the wrong child (Plant Grid follow-up review)

## Symptom
Not a user report. The independent review of the Plant Grid follow-up package built four inputs the
package's own tests did not cover, and two of them moved items that had asked
for a zero move:

- `AlignItemsCommand([(group, (100, 0)), (plant, (0, 0))], delta_frame="scene")`
  with `group.setRotation(90)` moved the plant `(100, -100)` instead of `(0, 0)`.
- A bed inside a group, with one plant inside the group and one outside: listing
  `[(group, (100, 0)), (bed, (0, 0))]` moved the outside plant `(100, 0)` away
  from a bed that stayed where it was.

## Wrong theories
- "The child's own delta is applied twice." It is applied once; the problem is
  the *frame* the applied vector is measured in.
- "The residual rule is wrong." It is right for an unrotated group, which is
  why every package test passed: `delta_child - delta_ancestor` is a scene
  vector, and for rotation 0 a scene vector and a parent-local vector are the
  same numbers.
- "A bed's delta is whatever entry listed it." It is not: a bed inside a moved
  group has its own residual delta, and its *net scene* movement is the sum of
  the group's and its own. Copying the first entry the loop met gave the child
  either value, depending on dict order.

The same two mistakes had a third victim: a **bound reference point**, whose
delta came from the first listed ancestor that contained its binding parent, and
the drill-down **nudge**, which listed the bed's external plants as if the bed's
rotated local delta were a scene delta.

## Key evidence
Two probes, written as tests before any production edit, failed with the exact
numbers above (100, -100) and (100, 0). Rotating the group by 90 deg is what
separated the theories: the residual `(-100, 0)` passed to `moveBy` became
`(0, -100)` in scene space, which is a rotation, not a double count. The bed
case separated "which entry" from "which frame": the bed's entry was
`(0, 0)` and the group's `(100, 0)`, and the plant moved by 100 - the group's
value - although the bed did not move at all.

## Root cause
Two rules were missing, and both are about frames, not arithmetic:

1. `QGraphicsItem.moveBy` takes a parent-local vector. A `scene` delta
   (align/distribute) is only the same vector while every parent is unrotated.
   The new residual path subtracted the ancestor's delta in scene space and then
   applied it as if it were local.
2. "The delta to give a bed's children" is the bed's **net scene** movement
   (its listed delta plus every listed ancestor's), mapped into the child's
   parent frame. The expansion used the delta of the item that led the loop to
   the bed, so a listed bed inside a listed group lost to whichever came first.

## Fix and lesson
`core.commands.to_parent_frame()` maps a scene vector through the item's parent
transform; `_MoveItemDeltasCommand` uses it on the residual. `net_scene_deltas()`
computes each listed item's total scene displacement (a `scene` delta already
is one; a `local` delta accumulates through the parent chain), and
`bed_child_move_delta()` picks the nearest listed ancestor's net and maps it
into the child's frame. `bound_owner_net()` applies the same lookup to a
reference point's BINDING parent, and the drill-down nudge now lists only the
focused member so the command's own expansion carries its external plants. The
command and the live drag (propagation and finalizer) share that rule, so the
drag and the undo step agree.

Lesson: **a delta is a vector plus a frame, and the frame must be named at the
call site.** An unrotated test suite cannot tell the two frames apart; every
geometry test that mixes a Qt parent with a per-item delta needs one rotated
case. `tests/integration/test_bed_membership_reconciliation.py` now carries the
rotated residual, the group-plus-bed net-delta, the live-drag, the bound
reference-point and the drilled-bed nudge cases; PF-CAN-70 records the rule.

## What this did not fix
The Plant Grid's snapped resize rounds the per-cell spacing to whole centimetres
*after* snapping the edge, so with columns that do not divide the span the edge
can land less than one cell from the snap line (350 -> 351 for 3 columns). Both
properties are requested by the issue and they conflict; whole-centimetre
spacing wins, and section 8.9.21 says so. The agent's grouped-child frame
mismatch stays filed as #1020.
