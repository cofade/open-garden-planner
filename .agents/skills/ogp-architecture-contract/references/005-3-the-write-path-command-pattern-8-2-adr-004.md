## 3. The write path: command pattern (§8.2, ADR-004)

`CommandManager` (`core/commands.py`) is a hand-rolled stack (a `QObject` with
`pyqtSignal`s — **not** `QUndoStack`, despite ADR-004's original wording; verified:
no `QUndoStack` anywhere in `src/`). Owned by `CanvasView`, shared to
`CanvasScene` via `scene.get_command_manager()` so `QGraphicsItem` subclasses can
push commands from interaction handlers.

- `execute(cmd)` — runs `cmd.execute()`, appends, clears redo, emits
  `command_executed` + `can_undo/redo_changed` + `stack_changed`.
- `register_applied(cmd)` — appends **without re-executing** (for live-applied
  drags/edits), same signal set. These two are the only entry points (invariant 3).
- Signal consumers: `stack_changed` → `mark_dirty` + panel refreshes (properties,
  constraints, plant-db, companion, crop-rotation, debounced calendar);
  `can_undo/redo_changed` → toolbar enablement **only**; `calendar_view` is
  deliberately on `command_executed` + debounced `schedule_refresh` (#210/#225).
- Command `description`s are user-visible → translated under the `"Commands"`
  i18n context (invariant 16).
- Composite/edge idioms: whole-geometry snapshot commands for curves (ADR-025),
  destructive-conversion commands that store the original item for undo
  (`FilletCornerCommand`, ADR-022), one-step multi-item commands
  (`MirrorItemsCommand`, ADR-026), param-edit-as-`ChangePropertyCommand` with an
  apply_func (smart symbols, ADR-032).
- **D2 agent writes inherit all of this** (invariant 13): one MCP write call →
  one `run_on_main` hop → one command via `execute()`/`register_applied()`.
  Move/set-position reparenting uses one compound command since #635 (v1.34.4).
  D2.6 vertex writes use the same canonical builders in
  `ui/canvas/geometry_apply.py` as the interactive polygon/polyline paths; never
  add a private callback in `application.py`.

