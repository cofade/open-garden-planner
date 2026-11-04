# Case study: a ridge that vanished on copy and hid behind its group (#690, manual test 2.6/2.7)

**Symptom.** Mirror **Copy** of a house produced a copy with a white, flat roof
and no ridge. Grouping a house made its ridge disappear behind the roof; only
the two ends peeked out. Delete + undo made the ridge render correctly again.

**Wrong theories, in the order they were tried.**

1. *Mirror copied the source ridge.* It did not: `MirrorItemsCommand` stripped
   `ridge_item_id` from every copy. The copy had no link and no ridge at all.
2. *Grouping included the ridge in the group.* It did not: `GroupCommand` only
   adds the selected items; the ridge is a top-level sibling.
3. *The group's layer was wrong.* The group's `layer_id` was right, and
   `MoveToLayerCommand([group])` moved the nested ridge correctly.

**Key evidence.** Mirror Copy left exactly one ridge in the scene, owned by the
source; the copy had no `ridge_item_id`. For grouping, `group.zValue()` was
above `ridge.zValue()`, while the stacking normalizer already had the rule
("a ROOF_RIDGE sits immediately above its owner") — and `_stack_entries`
already maps a group child's id to the group. The missing piece was simply that
`GroupCommand.execute` never ran `_update_items_z_order`; undo did, which is why
delete + undo looked right.

**Root cause.** Two lifecycle paths still treated the ridge as a sibling to be
left alone: Mirror Copy deliberately omitted creation, and grouping skipped the
z derivation that resolves a grouped owner to its group.

**Fix.** `MirrorItemsCommand` builds a fresh linked ridge for every copied HOUSE
on first execute (`_add_copy_ridges`) and re-adds the same ridge items on redo;
undo removes them. `GroupCommand.execute` runs the one z derivation after the
members are grouped. The selection bug found in the same round (Ctrl+click
replacing a selected journal pin) was Qt's default press; both Shift and Ctrl
now go through `SelectTool`'s toggle path.

**Lesson.** "The ridge follows its house" has three seams — geometry, rendering
and stacking. Each path that changes the house's *container* (a group) or makes
a *new* house (a copy) must run the matching seam. A sibling that renders above
its owner is not automatically above the owner's group; the z derivation must
be told the group is the owner's render parent.
