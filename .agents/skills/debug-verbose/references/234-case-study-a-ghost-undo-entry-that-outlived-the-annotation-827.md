## Case study: the undo entry outlived the annotation it created (#827, fixed 2026-11-13)

**Symptom.** With the Text tool, one click and then Esc left no text item on the canvas, but
the undo stack had grown by one. Ctrl+Z then did nothing visible, and Ctrl+Y put an empty,
invisible `TextItem` back — which the next save wrote into the `.ogp`.

**Wrong theories.** The obvious suspect was the redo path or the serializer. Both were
innocent: `ProjectManager` saves whatever is in the scene, and redo only re-ran a command
that had never been asked to leave. The next wrong instinct was "call `undo()` from
`cancel()`" — that parks the command on the redo stack, which is precisely how the ghost
comes back.

**Evidence.** An integration probe read the undo depth around the gesture with one rectangle
already committed: `[PROBE] baseline depth=1`, `[PROBE] after placement depth=2`,
`[PROBE] after Esc depth=1` on the fixed build. The same probe on `master` ended at 2 — the
item left, the history entry did not — and the rectangle's own undo/redo still worked. The
pre-existing test (`test_escape_on_an_empty_text_annotation_removes_it`) only checked
`scene().items()`; no assertion ever looked at the stack, which is why the bug survived the
test that "covered" it.

**Root cause.** `CanvasView.add_item()` executes the create command as a side effect of
placement, while `TextTool.cancel()` removed only the scene item.

**Fix.** `CanvasView.add_item()` returns the `CreateItemCommand` it executed; `TextTool`
keeps it beside the pending item; `CommandManager.discard(command)` pops only the exact top
command (LIFO identity, refused otherwise), never touches the redo stack, and emits
`can_undo_changed` + `stack_changed` without `command_executed`. The tool discards FIRST
and removes the scene item only on a `True` return, so scene and history can never disagree.
The same pair is resolved by a tool switch (`deactivate()`) and by a click that starts the
next annotation; those two paths end the placement without a focus-out, so `cancel()` also
calls `TextItem.finish_editing()` — otherwise the note's text is on screen and empty in the
saved file, because the serializer reads `content`, not the live document. Pinned by
`tests/integration/test_tool_switching.py::test_escaping_an_empty_text_annotation_leaves_no_ghost_undo_entry`
(observed failing on `master` at `assert manager.undo_depth == depth_before`),
`test_clicking_away_with_no_text_leaves_no_empty_annotation`,
`test_clicking_away_with_text_keeps_the_note_and_its_text`, and
`tests/unit/test_commands.py::TestCommandManagerDiscard`.

**Lesson.** A test that asserts the scene is not a test of the undo stack. When one gesture
creates state in two places, the test must assert both, and production needs one sanctioned
way back OUT of each: `undo()` is a navigation, not a cancellation. And a gesture's
"finish" must commit its data itself — focus-out is a side effect, not a contract.
