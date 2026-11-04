# Case study: the pin drag that had no undo, twice (#674, final review of PR #713)

**Symptom.** The journal pin moved correctly, but two drag paths left no Ctrl+Z
entry: a release outside the viewport (the next move silently dropped the open
gesture) and a pin drag performed immediately after a resize or rotation (the
move was swallowed by a stale "already captured" guard).

**Wrong theories.** The first pass assumed the lost-release case was covered by
`_finish_pin_drag` in `mousePressEvent`; it was not, because the no-button move
re-entered the viewport first and cleared the state without finalising. The
second looked like a general undo bug, but the guard was correct for a real
handle gesture - it was simply reading the *last command on the stack* rather
than a command created by *this* gesture.

**Key evidence.** Send `mousePress`, one left-button move, then a `MouseMove`
with `buttons == NoButton`: the pin's position changes, `undo_depth` does not.
Execute a real `ResizeItemCommand`, then drag the pin: the stack still ends with
"Resize item" and the pin move is absent. Both reproduced in the bare canvas,
not only in the full app.

**Fix.** The no-button branch calls `_finish_pin_drag()` before it returns, and
`_finalize_drag_move`'s resize/rotate guard now requires that the undo depth
advanced since the drag began (`_drag_start_undo_depth`), so only the handle
gesture that created the command skips the move. Two integration tests pin both
paths (`test_a_lost_release_is_committed_on_the_next_move`,
`test_a_pin_drag_after_a_resize_is_its_own_undo_step`).

**Lesson.** A bespoke drag state machine needs one end path used by release,
lost release and the next press. And an "already handled" guard must ask
"did THIS gesture create the command?", never "is the last command this type?".
