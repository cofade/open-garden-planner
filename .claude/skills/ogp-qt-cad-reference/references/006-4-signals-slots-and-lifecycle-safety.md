## 4. Signals, slots, and lifecycle safety

### Threading

Cross-thread work uses exactly one pattern: `MainThreadBridge.run_on_main(fn)`
(`agent_api/bridge.py`) emits a `Qt.ConnectionType.QueuedConnection` signal
carrying `(fn, Future)`; the slot runs on the main (Qt-owning) thread and
resolves the future; the worker blocks on `future.result(timeout)`. Never
touch Qt objects from a non-main thread directly. (Related pitfall in §8.19:
an MCP tool handler must be `async def` and offload via
`anyio.to_thread.run_sync`, or it blocks the server's event loop on the
future.)

### Fan-out cost (the #200 → #206 → #222/#223 arc, in brief)

`emit()` is a synchronous call to every connected slot. Wiring heavyweight
slots (full panel rebuild) to chatty signals caused a whole bug family:
rebuilding the properties panel on every `can_undo/redo_changed` destroyed the
focused editor mid-keystroke (#200). The structural fixes, now standing rules:

- Panels listen to `CommandManager.stack_changed` — ONE signal per
  execute/register_applied/undo/redo, never on `clear()` — not the old
  3-signal fan-out. `can_undo/redo_changed` is only for toolbar enablement.
- Rebuild only on genuine structural change; otherwise refresh values in
  place (`properties_panel.py` identity + refreshers, #222).
- Exactly **two** ways onto the undo stack: `CommandManager.execute()` (runs
  the command) and `register_applied()` (already-applied, e.g. live drags).
  Both dirty the document (#209).

### `scene.changed` — know its two-faced nature

- It fires on **every repaint** (extremely chatty — selecting an item triggers
  a burst), so slots must debounce *and* be idempotent (diff before rebuild;
  #212 follow-up).
- It does **NOT** fire on plain Python attribute writes (`parent_bed_id = …`)
  — no Qt geometry/visibility change, no signal (#173). Such paths must
  trigger refreshes explicitly (`trigger_soil_mismatch_refresh`).

### Teardown safety rules (each one has crashed CI or a user session)

1. A `scene.changed` slot that starts a `QTimer` must wrap the `.start()` in
   `with contextlib.suppress(RuntimeError):` — the scene still emits `changed`
   while being cleared at teardown, after the C++ timer is deleted;
   the resulting `RuntimeError` inside a Qt slot escalates to
   `Fatal Python error: Aborted` (whole interpreter). **Never connect
   `scene.changed` to a bare `lambda: self._timer.start()`** — a lambda can't
   be made teardown-safe. (§11.4 #230; see
   `canvas_view._on_scene_changed_for_soil`.)
2. A slot connected to an **application-global** signal
   (`QApplication.focusChanged`, `aboutToQuit`, …) can fire after its widget's
   C++ object is destroyed. Make the disconnect
   `contextlib.suppress(TypeError, RuntimeError)` and guard the slot body with
   `try/except RuntimeError: return`. Qt auto-disconnects destroyed receivers,
   so an explicit disconnect can race to `TypeError`. (§11.4 US-C1.)
3. **pytest-qt escalates any exception raised inside a Qt slot to a test
   failure** — including in a *later, unrelated* test ("passes alone, fails in
   the full run"). Timers on command/status signals (`stack_changed`) don't
   need guard 1 — those aren't emitted during teardown.
4. Overlay widgets: parent to the `QGraphicsView`, never `viewport()` (viewport
   children scroll with content); defer first positioning with
   `QTimer.singleShot(0, ...)` (§8.9.1–8.9.3).

---

