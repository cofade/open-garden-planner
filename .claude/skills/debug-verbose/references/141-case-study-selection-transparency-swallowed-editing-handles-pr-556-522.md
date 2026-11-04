## Case study: selection transparency swallowed editing handles (PR #556, #522)

**Symptom.** Shift+press on a selected rectangle's resize or rotation handle
selected the object behind it and never began the drag.

**Wrong theory.** Every non-selectable hit was treated as a passive overlay.
No alternate runtime explanation was accepted before the viewport probe.

**Evidence.** The independent reviewer recorded `[REVIEW-HANDLE]` with the
resize handle as the topmost hit, the background as the new target and
`grabber NoneType`. The identical probe with master's select handler grabbed
both resize and rotation handles. Six fail-first viewport cases reproduced
that missing grab at 0, 37 and 143 degrees.

**Root cause/fix.** The select tool consumed Shift before Qt could deliver the
press to the non-selectable handle. Delegate editing-handle presses to Qt first;
share `DRAG_HANDLE_TYPES` with the view's existing dropped-grab recovery. The
regression checks mouse grab, geometry mutation and one-step undo for both
handle types over a selectable background.

**Lesson.** Selection eligibility and input ownership are separate contracts.
A locked object can be transparent to selection while an editing handle must
keep its press. `QTest.mouseMove` was also measured to reset the global keyboard
modifiers after a Shift-modified press; these tests prove starting the drag,
not continuous Shift snapping. Temporary traces are absent from production.
Pinned by `test_shift_drag_handle_does_not_select_the_item_behind`.


