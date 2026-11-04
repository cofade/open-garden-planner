# Case study: opening a plan crashed because the date had moved (#390)

**Symptom.** The 3D reviewer's probe died opening a plan after a year's time-lapse: 4 of 4, an access
violation or an abort in `scene.render` at `minimap_widget.py`, with nothing on stderr. Without a
time-lapse: 3 of 3 survived. It pointed straight at the new recording code.

**Wrong theories.** (1) The capture view or its render targets corrupt the heap: the first measurement
removed this, the same crash came in plain plan view with no 3D view opened at all. (2) The minimap's
own overlay hiding: the crash moved to `CanvasView.paintEvent` without any change, so the minimap
was only the next one to paint. (3) A Python exception inside `paint`: an `excepthook` printed
nothing, and neither did stderr.

**Key evidence.** A matrix before any fix, on a clean v1.36.0 worktree, with a stated prediction: a
stale BSP index survives `NoIndex` and survives announcing the rects before the date moves.

| Mode, 2 runs each | Result |
|---|---|
| 23 date steps, or just one later date | crash |
| the same with `NoIndex` | survived |
| the same with `prepareGeometryChange` before the clock moves | survived |
| one date before the planting date (all plants hidden) | survived |

**Root cause.** `CircleItem.boundingRect` read `scene.plan_date` live, and `refresh_timeline` announced
the change from the clock's signal, when the rect had already moved. Qt removed the item from the
leaves of the NEW rect. The old leaves kept the pointer, the load path removes document items one by
one (it is deliberately not `clear()`, which would have emptied the index), and the next paint read
a destroyed item.

**Lesson.** A crash that follows the new feature is not yet the new feature's: the time-lapse only moved
the date, as the toolbar's slider does. Ask first whether the smallest non-feature path reproduces it,
on master. When Qt dies in `render` or `paintEvent` with no Python frame below it and nothing on
stderr, try `NoIndex`: a survivor names the index in one run. And an item's `boundingRect` must not read
live state from outside the item unless that state moves after the announcement.
