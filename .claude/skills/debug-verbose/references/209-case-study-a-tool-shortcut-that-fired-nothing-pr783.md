## Case study: a tool shortcut that fired nothing because S already belonged to Snap (PR #783, fixed 2026-11-09)

**Symptom**: the new CAD Split tool was advertised with the bare `S` shortcut,
but pressing `S` never selected it in the real window. The toolbar button worked;
the key did not, and there was no error in the log.

**Theories entertained (wrong)**:
- The tool was not registered with the tool manager — it was, and the button
  found it.
- The canvas's own `keyPressEvent` fallback would pick it up — that fallback is
  only reached when the window's shortcut map does not consume the key first.
- `QToolButton.setShortcut("S")` needed the button to have focus — a button
  shortcut is a window shortcut, not a focus-local one.

**What measurement revealed** (a 20-line PyQt script, one window, one
`QToolButton` and one `QAction` both on `S`):

```
hits []
```

Neither the button's `clicked` nor the action's `triggered` fired. Adding a
`QApplication`-level `Ambiguous shortcut overload: S` warning was the only
trace. Removing the action, the button hit; removing the button, the action hit.
The app already had `snap_action.setShortcut(QKeySequence("S"))`, so the new
tool's `S` made every `S` press ambiguous and Qt ran neither handler. The
canvas fallback never saw the key because the window shortcut map had already
consumed it.

**Root cause**: two `WindowShortcut` registrations for the same key in one
top-level window make Qt treat the key as ambiguous and dispatch neither; the
new tool reused the existing Snap to Grid shortcut.

**Lesson learned**: a new tool's `QToolButton` shortcut is a window shortcut and
must be checked against every `QAction` shortcut in the main window, not just
against other tools (`I`, `O`, `Shift+F`, `Shift+C`, `Shift+M` were safe; `S`
was not). Pin the configuration (the two shortcuts differ and `S` still belongs
to Snap to Grid) in a test; offscreen Qt has no focus window, so a synthetic key
press cannot prove it. `Shift+S` is the shipped split shortcut (PF-UI-36).
