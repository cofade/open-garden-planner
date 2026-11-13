## Case study: the undo entry outlived the annotation it created (#827)

**Symptom.** With the Text tool, one click and then Esc left no text item on the canvas, but
the undo stack had grown by one. Ctrl+Z then did nothing visible, and Ctrl+Shift+Z put an
empty, invisible `TextItem` back — which the next save wrote into the `.ogp`.

**Wrong assumption.** The obvious suspect was the redo path or the serializer. Both were
innocent: `ProjectManager` saves whatever is in the scene, and redo only re-ran a command
that had never been asked to leave. The next wrong instinct was "call `undo()` from
`cancel()`" — that parks the command on the redo stack, which is precisely how the ghost
comes back.

**Evidence.** An integration probe asserted the undo depth around the gesture. On the fixed
build the depth was `1` after the placement click and `1` again after Esc with
`text_items=0`; the same probe on `master` reported `depth=2, text_items=0` — the item
left, the history entry did not. The pre-existing test
(`test_escape_on_an_empty_text_annotation_removes_it`) only checked `scene().items()`; no
assertion ever looked at the stack, which is why the bug survived the test that "covered"
it.

**Fix.** `CanvasView.add_item()` returns the `CreateItemCommand` it executed; `TextTool`
keeps it beside the pending item; `CommandManager.discard(command)` pops only the exact top
command (LIFO identity, refused otherwise), never touches the redo stack, and emits
`can_undo_changed` + `stack_changed` without `command_executed`. The tool discards FIRST
and removes the scene item only on a `True` return, so scene and history can never disagree.
The same pair is resolved by a tool switch (`deactivate()`) and by a click that starts the
next annotation. Pinned by
`tests/integration/test_tool_switching.py::test_escaping_an_empty_text_annotation_leaves_no_ghost_undo_entry`
(observed failing on `master` at `assert manager.undo_depth == depth_before`) and
`tests/unit/test_commands.py::TestCommandManagerDiscard`.

**Lesson.** A test that asserts the scene is not a test of the undo stack. When one gesture
creates state in two places, the test must assert both, and production needs one sanctioned
way back OUT of each: `undo()` is a navigation, not a cancellation.
