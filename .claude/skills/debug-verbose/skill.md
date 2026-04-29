---
name: debug-verbose
description: Evidence-based debugging via targeted verbose instrumentation. Apply at the first sign of any non-obvious bug — before theorising. Grows with each bug fixed in this project.
user_invocable: true
argument: "Optional: short description of the bug or area to instrument"
---

# Verbose Debug Instrumentation

**Core principle**: stop theorising, start observing. The first step for any non-trivial bug is to instrument the code so the actual runtime sequence is printed to stdout, then reproduce with manual testing and read what happened. Fix from evidence, not assumptions.

---

## When to apply (proactively, without being asked)

- Behaviour differs from what the code appears to do
- Event-driven / asynchronous code (timers, signals, focus events, callbacks)
- Something is called unexpectedly, or not called at all
- A guard/condition seems correct but isn't firing
- Third-party framework (Qt, etc.) is involved and may have side effects

---

## How to instrument

### 1. Identify the execution spine

Map the path from trigger to outcome. For every node on that path add a `print`:

```
trigger → A() → B() → [condition] → C()  ← expected
                               ↘ D()      ← what actually happens?
```

### 2. What to print at each node

| Node type | Print |
|-----------|-------|
| Entry to function | function name + key arguments + `type(self).__name__` |
| State that the condition reads | the exact values used in the `if` |
| Timestamps for time-based guards | `time.monotonic()` before AND inside the guard |
| Focus / visibility / flag checks | `hasFocus()`, `isVisible()`, `flags()` |
| Async callbacks (timers, slots) | "fired" + whether preconditions hold |
| Exit paths | which branch was taken, what was returned |
| Unexpected call sites | `traceback.format_stack()[:-1]` — always include this for "who called me?" questions |

### 3. Use `print`, not `logging`

`logging` requires configuration. `print` goes to stdout unconditionally — exactly what you need when the app is run from a terminal.

### 4. Prefix every line

Use a consistent tag like `[MODULE]` so output is grep-able and doesn't get lost in Qt warnings:

```python
print(f"[LABEL] focusOutEvent: elapsed={elapsed:.4f}s  isVisible={self.isVisible()}")
```

### 5. Include call stacks at "unexpected" sites

Any function that should only be called from specific places should print its caller when debugging:

```python
import traceback
for line in traceback.format_stack()[:-1]:
    print(f"[TAG]   {line.strip()}")
```

This is what revealed the minimap as the culprit below.

---

## Template — event-driven method instrumentation

```python
def some_event_handler(self, event):
    import time, traceback
    t = time.monotonic()
    start = getattr(self, '_start_time', 0)
    print(f"\n[TAG] some_event_handler:")
    print(f"[TAG]   key_state  = {self.some_state}")
    print(f"[TAG]   elapsed    = {t - start:.4f}s")
    print(f"[TAG]   condition  = {self.isVisible() and (t - start) < 0.2}")
    print("[TAG]   caller stack:")
    for line in traceback.format_stack()[:-1]:
        print(f"[TAG]     {line.strip()}")
    # ... rest of method
```

---

## Template — async/deferred callback

```python
def _deferred_action():
    import time
    print(f"[TAG] _deferred_action fired — isVisible={item.isVisible()}  hasFocus={item.hasFocus()}")
    if not item.isVisible():
        print("[TAG] ABORT — item hidden before callback ran")
        return
    item.do_thing()
    print(f"[TAG] after do_thing — hasFocus={item.hasFocus()}")

QTimer.singleShot(0, _deferred_action)
```

---

## Case study: label editor auto-closing (fixed 2026-04-22)

**Symptom**: double-clicking any garden item opened the inline label editor for ~110 ms then it closed by itself.

**Theories entertained (wrong)**:
- Qt's double-click Release-2 event steals focus
- `_label_edit_start_time` set after `setFocus()` so guard evaluated stale `0.0`
- `super().focusOutEvent()` clears text cursor

**What instrumentation revealed** (one double-click, reading stdout):

```
[LABEL] _give_focus() — after setFocus: hasFocus=True  isVisible=True

[LABEL] focusOutEvent:
[LABEL]   elapsed        = 0.109000s
[LABEL]   isVisible()    = False          ← ALREADY HIDDEN before focusOut fired
[LABEL]   guard (<0.2s)  = False          ← guard missed because isVisible is False
[LABEL]   caller stack:
[LABEL]     minimap_widget.py:205 — item.setVisible(False)   ← THE CULPRIT
```

**Root cause**: `MinimapWidget._hide_overlay_items()` iterates all scene items with `ItemIgnoresTransformations` and calls `setVisible(False)` on them — including the `EditableLabel` — before rendering the minimap thumbnail (~110 ms after focus was given). Hiding the item fired `focusOutEvent` with `isVisible() = False`, so the time-based guard (which checks `isVisible()`) never activated.

**Fix** (one line in `minimap_widget.py`): skip the scene's current focus item in `_hide_overlay_items()`.

**Lesson**: the call stack in `focusOutEvent` pointed directly to the file and line number of the external caller. Without it, debugging would have required days of guessing.

---

## Case study: CalloutItem re-editing immediately commits (fixed 2026-04-29)

**Symptom**: right-clicking an empty `CalloutItem` and choosing "Edit Text" did nothing — the item appeared to enter editing and immediately exit it. Items with non-empty content also failed via the context menu.

**Theories entertained (wrong)**:
- Context menu stealing keyboard focus from the view (real, but not the root cause)
- `QGraphicsTextItem.setFocus()` silently failing for zero-width bounding rects
- `_text_child.clearFocus()` in `_commit_edit` breaking subsequent `setFocus` calls

**What instrumentation revealed** (right-click → "Edit Text" on empty callout):

```
[CALLOUT] start_editing: _editing=False  content=''
[CALLOUT]   scene focus before: CalloutItem          ← parent already has scene focus
[CALLOUT]   scene focus after view.setFocus(): CalloutItem  ← still has it after widget focus restore
[CALLOUT] focusOutEvent on CalloutItem: _editing=True       ← fires DURING _text_child.setFocus()
[CALLOUT]   caller: callout_item.py:234 self._text_child.setFocus(...)
[CALLOUT] _commit_edit: _editing=True  content=''           ← immediately committed
[CALLOUT]   _editing after setFocus: False                  ← editing already dead
```

The sequence was: context menu open → `_text_child` loses focus → Qt gives scene focus to the
parent `CalloutItem` (because `ItemIsFocusable` was set) → `_commit_edit` runs (correct at
this point). Then "Edit Text" → `start_editing()` → `view.setFocus()` restores `CalloutItem`
as scene focus → `_text_child.setFocus()` steals it → `CalloutItem.focusOutEvent` fires with
`_editing=True` → `_commit_edit()` immediately exits editing.

**Root cause**: `CalloutItem` had `ItemIsFocusable` set and a `focusOutEvent` that committed
the edit. Whenever `_text_child.setFocus()` transferred scene focus away from the parent,
`focusOutEvent` fired on the parent and exited editing mode synchronously — before the user
could type anything.

**Fix**: removed `ItemIsFocusable` from `CalloutItem` entirely. Created `_CalloutTextChild`
(`QGraphicsTextItem` subclass) that routes its own `focusOutEvent` → parent's
`_on_text_focus_out()` → `_commit_edit()`, and handles Escape via `clearFocus()`. The parent
now never holds scene focus, so `focusOutEvent` on the parent is never triggered during
`start_editing()`.

**Lesson**: when a `QGraphicsItem` parent holds `ItemIsFocusable` AND has a child
`QGraphicsTextItem`, setting focus on the child fires `focusOutEvent` on the parent
synchronously inside `setFocus()`. This is the correct place to commit on "lost focus", but
it fires at the wrong time when you are *entering* editing. The fix is to never let the parent
hold scene focus — put all focus logic in the child subclass.

---

## After fixing: clean up

Remove all `print` instrumentation before committing. The fix lives in the production code; the diagnosis lives in this skill.

---

## How this skill grows

After every non-trivial bug fixed in this project, add a new **Case study** entry above with:
- Symptom (one line)
- Wrong theories (to avoid repeating them)
- The key log line(s) that revealed the truth
- Root cause (one sentence)
- Lesson learned

Over time this becomes a project-specific debugging playbook.
