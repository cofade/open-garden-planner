# Case study: a nested group survived its parent's ungroup (#674)

**Symptom.** The new integration test `test_nested_groups_ungroup_one_level_at_a_time`
failed after the Group/Ungroup menu work: after ungrouping the outer group, the
inner group's member reported a *different* parent group, and the inner group was
already dissolved too. The issue's rule is explicit — ungroup dissolves **one
level only**.

**Wrong theories, in the order they were tried.**

1. *`UngroupCommand` captured grandchildren.* Its `__init__` stores
   `list(group.childItems())`, which is direct children only; a probe showed the
   captured list was `[inner, shape]`, not the member inside `inner`.
2. *`QGraphicsItemGroup.addToGroup` flattens nested groups.* A minimal Qt
   reproduction kept `inner_member.parentItem() is inner` after
   `outer.addToGroup(inner)`. Rejected.
3. *The menu picked the wrong action.* `QMenu.exec` was monkeypatched and the
   test passed `choose="Ungroup"`; the top-level menu held exactly one match.

**Key evidence.** Two tagged prints decided it:

```
[BEFORE-UNGROUP] selected=[outer, inner]  inner.isSelected()=True
[BEFORE-UNGROUP] inner.parentItem()=outer
```

`GroupCommand.execute` explicitly calls `item.setSelected(False)` before
`addToGroup(item)`, for every item — yet the *inner group* came back selected.
A Qt-only probe showed why the flag can come back: selecting a
`QGraphicsItemGroup` propagates selection into its child items (their
`isSelected()` mirrors the group), and `scene.selectedItems()` in the app's
scene returned the inner group along with the outer one. The command then built
one `UngroupCommand` per "selected" group, so a single gesture dissolved two
levels: outer first, then inner as a now-top-level group.

**Root cause.** `ungroupable_groups()` treated every selected `GroupItem` as an
ungroup target, including one that was a child of another selected group. The
selection set is not the user's intent set when Qt's own selection propagation
adds entries.

**Fix.** `ungroupable_groups()` now keeps only `parentItem() is None` (and still
excludes `SmartSymbolItem`). A round-2 review then found the same trap on the
Group side: `groupable_selection()` filtered only `GroupItem` children, so the
plain members Qt reports as selected right after grouping made the new group's
menu offer Group for a single group. Both filters now apply
`parentItem() is None` to every item. The nested test pins the one-level rule,
the just-grouped test pins the menu matrix in the real post-gesture state, and
the two-group test pins that the whole gesture is one undo step
(`CompoundCommand`).

**Lesson.** When an operation acts on "the selection", filter to the *level* the
operation is defined at (top-level groups) before it decides how many steps to
run. `isSelected()` on a Qt group child is a fact about the group, not evidence
that the user picked the child. Both menu availability and dispatch must use the
same filter, or a menu can offer a number of steps the command will not honour.
