## Case study: a locked item is not selectable, and `itemAt` answers the locked one (#522)

**Symptom.** Shift+clicking an item on a locked layer REPLACED the selection
instead of toggling it: the item behind was selected and the other one was
deselected.

**Evidence.** The select tool asked `scene.itemAt(pos)`, which answers the
TOPMOST item - and a locked layer takes the selectable flag away from its items
(`CanvasScene` clears `ItemIsSelectable`), so the topmost item was one the tool
could not select. The tool gave up and handed the click to Qt, whose own toggle
key is Ctrl: a Shift+click had become a plain click.

**Wrong theory.** "Qt's Shift handling is wrong" and "the layer lock should
remove the item from the hit test". The second would change what a plain click
does; the first is Qt's documented behaviour. The 3D selection bridge, measured
against the same scenarios, already toggled what the click reached - the two
views disagreed, and the canvas was the one with the defect.

**Cause/fix.** The tool asks for the first SELECTABLE item under the cursor
(`QGraphicsScene.items(pos)` is in descending stacking order), so Shift+click
toggles what lies behind the locked item - the canvas's own rule. With nothing
selectable beneath, the click goes through as before, so a locked item with
nothing behind it still clears the selection and the two views still agree.

**Lesson.** `itemAt` answers the topmost item, not the topmost SELECTABLE one.
When a flag decides what an item can do, the hit test has to ask for the item
the user can act on - and the measurement harness that already compares two
implementations is where the difference shows up.


