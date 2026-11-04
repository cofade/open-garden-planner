# Case study: the pane that destroyed the widget that was talking to it (PR for #655–#670)

**Symptom.** Choosing a hidden or locked layer in the Properties panel's Layer
combo moved the item, cleared the panel, and did nothing else. On the source
fork's macOS host the same gesture aborted the process with exit code 139
(SIGSEGV). Nothing in the log; the canvas looked right.

**The probe that found it.** A test connected a spy to the combo's
`currentIndexChanged` and recorded `sip.isdeleted(combo)` inside the handler:
`[]` instead of `[True]` — the signal was never delivered, because the combo no
longer existed by the time Qt tried to deliver it. Tagging the rebuild showed
the order plainly:

```
[LAYER] combo.currentIndexChanged -> on_property_changed
[LAYER]   MoveToLayerCommand.execute -> _update_items_visibility
[PANEL]     scene.selectionChanged -> set_selected_items([])
[PANEL]       _clear_form -> removeRow(0)      <- deletes the combo box
[LAYER] combo.currentIndexChanged <- never resumes
```

**Wrong theories.** (1) "The combo's `currentData()` is stale, so the layer
lookup fails" — the item did move to the target layer, and undo restored it, so
the edit had happened; only the notification was lost. (2) "The selection
signal is queued" — it is direct, and the stack above is synchronous. (3)
"`removeRow` is safe because Qt keeps the sender alive during delivery" — Qt
keeps the C++ object only until the widget is destroyed; `removeRow` calls
`delete` immediately, which takes the connection and the notifier with it. On
macOS the same deletion inside a delivered event is the SIGSEGV.

**Root cause.** `PropertiesPanel._clear_form()` looped
`QFormLayout.removeRow(0)`. A panel rebuild can be re-entrant *through a widget
the panel itself created*: the Layer combo's handler moves the item, the move
deselects it, and the selection change rebuilds the form synchronously. The
rebuild destroyed the combo box while its own signal was still being delivered.

**Fix.** The rebuild takes each row with `takeRow(0)`, hides the widget,
detaches it (`setParent(None)`) and schedules `deleteLater()`. The sender stays
alive for the rest of the delivery; the panel is empty immediately; the memory
is released on the next event-loop turn. `refresh_theme_icons` already deferred
its rebuild with `singleShot(0)` for the same family of reason; this makes the
*synchronous* rebuild safe instead of banning it.

**Lesson.** "Do not destroy widgets from a handler" is not enough advice — say
*which* handler. A panel that reacts to model changes can be called from inside
one of its own fields' signals, and every `removeRow`/`delete` on that path is a
use-after-destruction waiting for a platform where it crashes. Prefer
detach + `deleteLater()` in any teardown that can be re-entered. Pin it by
asserting the sender's liveness *inside* the signal (`sip.isdeleted`), not by
asserting the panel's final state — the final state was correct all along.

---

**Second finding: the plan was silently different after a save.** Reproduced by
grouping a 30-degree rectangle with a circle and reloading: the rectangle's
visible scene centre moved from `(160, 130)` to `(246.44, 67.42)`. The saved
child carried `x=186.44, y=37.42` — `item.pos() + rect.x()`. Printing the child
after `GroupCommand` showed why `pos` is not the shape's frame any more:

```
pre  pos=(0, 0)            mapToParent(0, 0) = (86.44, -62.58)
post pos=(86.44, -62.58)   mapToParent(0, 0) = (86.44, -62.58)   (unchanged scene)
```

`QGraphicsItemGroup.addToGroup()` rewrites a rotated child's `pos` to the parent
position of its local origin and rotates about the item origin; the old pivot
is folded in. `pos + local` therefore double-counts the compensation, and the
loader re-rotates about a different rect centre. The test that catches it must
compare *scene* geometry after a save/reload, in a matrix over shape type and
rotation; a rotation of 0 passes every variant, which is why the bug survived.

**Lesson.** A Qt item's local frame is not a stable serialization frame: the
parent can rewrite it. Serialize through `mapToParent(shape centre)` (invariant
because the pivot is the shape's own centre), and never infer a frame from
`pos()` once a group may have touched the item.
