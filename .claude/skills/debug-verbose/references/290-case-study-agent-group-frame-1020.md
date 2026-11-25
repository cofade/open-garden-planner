# Case study: a scene delta had a frame, and the agent never reached the child (#1020)

## Symptom
Not a user report. The round-7 review of the Plant Grid package found a hole in the
delta-frame rule: `MoveItemsCommand` applied a `scene` delta with `item.moveBy()`,
which is parent-local, and the frame correction only ran when the item had a **listed**
Qt ancestor. A grouped child therefore took its scene delta in the group frame. The
issue's stated reproduction was an agent `move_object` on a bed or plant inside a
rotated group.

## Wrong theories
- "The agent lists the group but not the child." It lists neither: it lists the target,
  and `expand_with_bed_children` adds the target's plants. The group is never listed.
- "`delta_frame='scene'` already converts." It only subtracted a listed ancestor's
  delta. With no listed ancestor the branch did nothing, which is why every test on a
  top-level item passed.
- "The agent reproduces it, so the guard must be missing." The guard is
  `_resolve_agent_item`: a lone group member is refused by name ("address the group
  itself"). That has been true since v1.31, and two tests pin it. The reviewer audited
  the delta path and not the resolver.

## Key evidence
A command-level probe with a plant inside a group at 30 degrees and scale 1.5:
`MoveItemsCommand([plant], (40, -25), delta_frame="scene")` moved the plant by
`(40, -25)` rotated and scaled — not the requested scene vector. With the group
unrotated the probe passed, which is the whole trap: at rotation 0 a scene vector and a
parent-local vector are the same numbers.

The agent-level probe returned a tool error, not a move: "… is a member of a group;
address the group itself …". The scene, the item count and the undo depth were all
unchanged.

## Root cause
A `scene` delta is a vector plus a frame. The command mapped it into the parent frame
only for the residual of a listed ancestor; every other scene vector was handed to a
parent-local `moveBy`. The defect is in the command, not in the agent, and it would
have bitten any caller that lists an item with a Qt parent it does not list.

## Fix and lesson
`_MoveItemDeltasCommand` now always maps the scene residual into the item's parent
frame:
`residual = delta - ancestor_delta if ancestor else delta; delta = to_parent_frame(item, residual)`.
`to_parent_frame` is the one helper every frame conversion uses. The agent keeps its
refusal, now pinned against a rotated and scaled group with "no scene change, no undo
step" (`test_move_object_refuses_a_lone_group_member_without_a_side_effect`), and the
command's frame rule is pinned by
`test_a_single_scene_delta_inside_a_rotated_and_scaled_group_lands_in_scene`
(PF-CAN-70).

Lesson: **verify the reported path reaches the code before fixing the path it names.**
The issue's own reproduction was impossible through the public tool, but the invariant
it pointed at was real and wrong for every other caller. Fix the invariant, pin the
refusal that makes the report unreachable, and say both in the PR.
