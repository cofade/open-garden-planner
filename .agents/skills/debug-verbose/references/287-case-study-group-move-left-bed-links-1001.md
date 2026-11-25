# Case study: a group moved out of a bed kept every plant's bed link (#1001)

## Symptom
A raised bed held three plants. Grouping them with Ctrl+G and moving the group
30 m clear of the bed left all three with `parent_bed_id = bed.item_id`, and
the bed's `child_item_ids` still listed them. A single ungrouped plant moved the
same way unlinked correctly (the #443 path). The bed's capacity, soil and
contained-plant surfaces therefore kept reporting plants that were no longer in
it, and moving the bed later pulled the group back.

## Wrong theories
- "The move command has no membership tracking." False: `_MoveItemDeltasCommand`
  builds a `BedMembershipChange` and reconciles after replaying the deltas; the
  ungrouped control case proves that path works.
- "Qt tells the group's children that they moved, so the tracker sees them."
  False: a member's local position does not change when the group moves; only
  the group gets `ItemPositionHasChanged`, and a `GroupItem` is not a plant.

## Key evidence
`_membership_change_for_move(scene, items)` filtered the moved items themselves:
`is_plant_type(GroupItem)` is false and `iter_plant_parents([group])` finds no
plant-parent, so it returned `None`. The plants moved correctly (Qt children
follow) but no `BedMembershipChange` was ever constructed. The new regression
test failed on the pre-fix code and passed with the child-tree walk.

## Root cause
The membership tracker's input was the selection, not the set of plants the
selection carries. Group membership is a Qt parent-child relationship, and the
move command's `items` list holds only the top-level group.

## Fix and lesson
`core/commands.plants_in_items()` filters the shared
`ui.canvas.items.group_item.selection_tree()` and `_membership_change_for_move`
tracks those plants; the group move reconciles every member through the same
`BedMembershipChange` path a single plant uses, inside the same undo step. The
same lookup exposed the mirror trap in `expand_with_bed_children`: a bed inside
the group lists the plants the group's Qt move already carries, so adding the
bed's delta to those plants moved each twice. `carried_by_moved_item()` checks
the Qt ancestor chain and skips a child that is already carried. The live drag
path (`CanvasView._propagate_bed_children_during_drag`) had the same trap: it
set a carried plant's local position by the group's delta, and the release
finalizer then skipped it, so undo left it displaced. It now asks the same
helper; the mouse-drag/undo and direct live-propagation tests pin it. The move
command now names its delta frame explicitly: align/distribute and uniform
moves are scene deltas (a carried child contributes its residual scene delta),
while the live finalizer's constrained-child corrections are parent-local and
must be applied as listed. Mixing the two frames is the same split one layer
down. Lesson: when a command's effect travels through Qt's parent-child graph,
every tracker it owns must walk that graph too, and a second relationship (bed
link) must not add a delta to an item the first (Qt parent) already moves.
