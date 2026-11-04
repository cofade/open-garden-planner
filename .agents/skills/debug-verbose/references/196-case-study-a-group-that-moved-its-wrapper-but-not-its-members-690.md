# Case study: a group that moved its wrapper but not its members (#690, manual test 2.7)

**Symptom.** A group with a house and a rectangle was moved from layer 1 to layer 2.
Hiding layer 2 hid the group correctly. Hiding layer 1 then hid the house and
rectangle while the group wrapper and the house's ridge stayed visible.

**Wrong theories, in the order they were tried.**

1. *The group's layer was wrong.* It was not: `group.layer_id` was layer 2.
2. *The ridge was the only thing that followed.* It did follow, but so should the
   members — and they did not.
3. *The members were Qt children, so hiding their layer should not matter.* It
   did: `_apply_item_visibility` ran per item and read each member's own
   `layer_id` (layer 1).

**Key evidence.** The owner's saved plan showed it directly: the group and its
ridge carried layer 2's UUID, while both child shapes still carried layer 1's.
`scene.update_layer_visibility(layer_1, False)` then set those children invisible
individually, even though their parent group was visible.

**Root cause.** Two seams disagreed about who owns a group's layer.
`MoveToLayerCommand` moved only the wrapper (and, since #690, the sibling ridge),
while visibility treated each member's own saved `layer_id` as authoritative.

**Fix.** `MoveToLayerCommand` walks `group_item.selection_tree()` and writes the
target layer to every member too, restoring each on undo. `_apply_item_visibility`
resolves a grouped item's effective layer through its outermost group ancestor,
so plans saved before the fix (like the owner's) render as one unit without a
migration.

**Lesson.** A composite's container attributes are not the sum of its parts'
attributes. When a group is "one object" for selection and stacking, it is one
object for its layer as well; both the command that changes it and the reader
that displays it must agree.
