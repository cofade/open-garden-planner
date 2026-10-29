## 17. Label editor auto-closing — the minimap culprit (fixed 2026-04-22)

Source: debug-verbose case study (the skill's founding story).

- Symptom: double-click opened the inline label editor for ~110 ms, then it closed
  itself.
- Wrong theories: double-click Release-2 stealing focus; a stale start-time guard;
  `super().focusOutEvent()` clearing the cursor.
- Evidence: `traceback.format_stack()` inside `focusOutEvent` printed
  `minimap_widget.py:205 — item.setVisible(False)` — the minimap's
  `_hide_overlay_items()` hides all `ItemIgnoresTransformations` items (including the
  focused editor) before rendering its thumbnail.
- Fix: skip the scene's current focus item in `_hide_overlay_items()`.
- Lesson (and why `debug-verbose` mandates stack traces at unexpected call sites): the
  external caller is unfindable by reading the widget's own code.
- Status: closed. Sibling case study: `CalloutItem` re-editing immediately committed
  because the parent held `ItemIsFocusable` and `_text_child.setFocus()` synchronously
  fired the parent's `focusOutEvent` → fix was to never let the parent hold scene focus.

---

