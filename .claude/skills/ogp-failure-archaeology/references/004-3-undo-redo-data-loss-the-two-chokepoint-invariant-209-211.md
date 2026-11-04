## 3. Undo/redo data loss — the two-chokepoint invariant (#209/#211)

Source: §11.4 ("Undo/redo must dirty the document…").

- Symptom: draw → save → Ctrl+Z → title shows no `*`; closing prompts nothing and
  **silently discards** the undo.
- Root cause: `mark_dirty` was wired to `command_executed`, which only `execute()`
  emitted — `undo()`/`redo()` didn't dirty.
- The trap that made it a two-part fix: `command_executed` was load-bearing for
  dirtiness at ~30 direct `cm._undo_stack.append(cmd)` + hand-emit sites (resize
  handles, vertex drags, live property edits). Moving `mark_dirty` to a new
  `stack_changed` signal *un-dirtied all of them*; the naive integration test stayed
  green because it only exercised the `execute()` path.
- Fix: `CommandManager.stack_changed` (emitted by execute/undo/redo, **not** `clear()` —
  new/load must stay clean) + a single `register_applied(command)` chokepoint that every
  former direct-append site now calls (append + redo-clear + full signal set, without
  re-executing).
- Invariant learned: **exactly two ways onto the undo stack** — `execute()` (runs the
  command) and `register_applied()` (already applied) — both emit the full signal set.
  Never hand-roll `_undo_stack.append` at a call site.
- Status: closed. Pinned by `tests/integration/test_undo_redo_dirty.py` (covers both an
  `execute()` path and a `register_applied` resize path).

---

