## Case study: a committed control kept focus and escaped undo refresh (PR #556 manual pass)

**Symptom.** Undo restored a container's terracotta appearance and watering hint,
but the focused Material combo still displayed Metal. Drainage's checkmark did
the same until deselection/reselection.
**Wrong theory.** The command or 3D material update was at fault. Both had already
restored the correct value; the two panel representations disagreed.
**Evidence.** The isolated tagged refresh probe printed `[MATERIAL-UNDO] refresh
focused=True shown=metal stored=terracotta`, then the same stale value after undo.
The unexpected skipped refresh included traceback.format_stack().
**Root cause/fix.** _refresh_widget skipped every focused widget to protect typing.
Closed dropdowns, checkboxes and color buttons have no uncommitted text to protect.
Only focused text/spin editors and editable combos now retain that protection;
committed controls refresh under blocked signals while keeping focus.
**Lesson.** Keyboard focus is not proof of an edit in progress. The canonical guard
also covers label/grid/frost/style choices, text bold/italic and color buttons.
The owner completed the manual pass before finalization resumed. Regression coverage
for focused Material/Drainage undo and redo belongs in
`tests/integration/test_properties_panel_undo.py`; active text editing retains its
existing protection. Species/instance writes outside the command stack are separate
#559, rather than a refresh-only defect.

