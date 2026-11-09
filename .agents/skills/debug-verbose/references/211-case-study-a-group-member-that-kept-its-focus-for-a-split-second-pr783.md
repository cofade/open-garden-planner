## Case study: a group member that kept its focus for a split second (PR #783, fixed 2026-11-09)

**Symptom**: owner manual test 8 of PR #783. With a group selected, a click on a
member focused it (handles, Properties panel) "only for a split second, then
focus shifts back to the group again". Twenty-one green drill-down tests said it
worked.

**Theories entertained (wrong)**:
- The deferred `_finish_group_drill_down` (a `QTimer.singleShot(0)` after
  `selectionChanged`) judged a half-updated selection and cleared the focus —
  it only runs when the selection changes, and nothing in the click changes it.
- The mouse release of the second click was read as a click outside the member.
- A panel refresh triggered by `drill_down_changed` re-selected the group.

**What the log revealed**: a probe drove the real `GardenPlannerApp` window with
two real viewport clicks and printed `traceback.format_stack()` from a
`scene.selectionChanged` listener. (The first probe run proved nothing: its click
landed at x=19, inside the left ruler, and started a guide drag. Print the hit
test before believing a "nothing happened".)

```
[PROBE] click2
[PROBE] immediately <RectangleItem ...>
[PROBE] selectionChanged []
  File "src/open_garden_planner/ui/widgets/minimap_widget.py", line 230, in _do_update
    hidden = self._hide_overlay_items()
  File "src/open_garden_planner/ui/widgets/minimap_widget.py", line 284, in _hide_overlay_items
    item.setFlag(no_contents, True)
[PROBE] after wait None []
```

The selection was cleared from inside the minimap's thumbnail render, 100 ms
after the click, by a `setFlag` on one of the focused member's handles.

**Root cause**: `QGraphicsItem.setFlags` deselects an item that reports
`isSelected()` without being selectable. A descendant that already existed when
its parent joined a `QGraphicsItemGroup` reports its GROUP's selection and routes
`setSelected(False)` to the group, so setting any flag on such a handle inside
the selected group unselected the group, and the view then retired the
drill-down. Measured in isolation (Qt 6.12): the flag unselects the group,
`setOpacity` does not, a selectable child is immune, and so is a child created
AFTER the grouping (it reports False). Handles are created when a member is
first selected, and a user selects the members to group them, so the real
workflow always meets the precondition; a test that groups unselected members
does not, and would have passed on the broken code. The
minimap had already been taught not to `setVisible(False)` (PR #713); the flag it
switched to has the same side effect for this one kind of item.

**Lesson learned**: a feature that depends on a Qt selection staying put must be
tested in the running window, past every periodic repaint, with real clicks — a
bare canvas has no minimap, and a test that calls the feature's entry point
directly skips the event path the user takes. And "stack at the unexpected
call" is the whole method: the caller was a widget nobody suspected, as the
project rule already said it would be. Rule and pins: PF-CAN-48.
