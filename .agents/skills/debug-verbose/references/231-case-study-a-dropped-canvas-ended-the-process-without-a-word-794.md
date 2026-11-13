## Case study: a dropped canvas ended the process with 0xC0000409 and not a word — Qt called a virtual on a view whose attributes the collector had already cleared (#794, fixed 2026-11-10)

**Symptom**: a probe of the second review of the 2D visual-polish branch built a `CanvasScene` and a `CanvasView` in a function, returned, and called `gc.collect()`. The process ended there with exit code `0xC0000409`: nothing on stdout, nothing on stderr, no Python traceback, `faulthandler` silent. The commit before the sun map's key (#794) ran the same probe to its end. With `view.close(); view.deleteLater()` before the collection (what pytest-qt and `tests/conftest.py` do after every test) the head survived as well, so the whole suite was green and the application, which closes and deletes its one window, never showed it.

**Theories on the table (wrong)**:
- *"The widget-leak probe (`scripts/probe_widget_leaks.py`), which switches the suite's close-and-delete off, must hit it."* It does not: `apps --count 5` and `per-test tests/ui/test_canvas.py` both exit 0 before and after the fix. A full `GardenPlannerApp` owns its view through a parent chain, and the views of `test_canvas.py` are collected in another order; "by inference" was not a measurement.
- *"Every override Qt can call must survive a cleared `__dict__`: `paint`, `boundingRect`, `shape`, `itemChange`, `drawForeground`, the timers' slots."* That is a list of what Qt CAN call, not of what it calls while a garbage island is taken apart. Giving all of them class-level defaults would have been forty attributes of ceremony and no evidence.
- *"It is the new kept state (the label pass, the standing covers)."* None of it is touched during a collection.

**What instrumentation revealed** (every function of every class of `open_garden_planner` that a canvas is made of — the view, the scene, the minimap, the shadow controller, each item class — wrapped so that a call made while `gc.collect()` runs is counted with whether the instance still has attributes; nine ways of dropping a canvas, three canvases each):

```
[GC] ok zoomed minimap
[GC] ok zoomed minimap selected controller legend
[GC] ok zoomed owned minimap
[GC] ok plain / minimap / selected / minimap selected owned / legend controller minimap selected / owned
[GC] 34 ('CanvasView', 'scrollContentsBy', 'cleared')
[GC] 34 ('CanvasView', '_refresh_dense_vertex_overlays', 'cleared')
```

Two entries, both on the view, both with the instance's `__dict__` already empty; nothing on the scene, the minimap or any item. (The recorder only runs to its end with the fix in place: without it the first of those calls is the abort.)

**Root cause**: a view and its scene reference each other, so a dropped pair is garbage that only the cyclic collector finds. It first CLEARS every object of that garbage (`tp_clear` empties each instance's `__dict__`), then destroys them, in an order of its own. When the scene's C++ object is destroyed first, `QGraphicsScene::~QGraphicsScene` takes the scene from each of its views (`setScene(nullptr)`); the view recomputes its content size, the scroll bars change, and Qt calls the virtual `scrollContentsBy`. PyQt enters the Python override — on a view whose attributes are gone. `scrollContentsBy` had been given one line for the sun map's key, `if not self._sun_legend_rect.isEmpty():`, and that read raised `AttributeError`. An exception cannot propagate through the C++ frame that called the virtual: PyQt prints it and calls `qFatal`, which on Windows is a fast-fail (`0xC0000409`) that neither Python nor `faulthandler` reports. `CanvasScene._paint_revision` already had a class-level default for the same reason (a slot Qt calls from the scene's destructor), with a comment that said so; the new attribute on the view did not get one.

**Fix** (`ui/canvas/canvas_view.py`): `_sun_legend_rect = QRect()` on the class, so the lookup finds a value when the instance has none. `tests/integration/test_dropped_canvas.py` runs a child process (`dropped_canvas_child.py`) that builds canvases with everything on — labels, the grid, the sun overlay, the key, the minimap, a selection, scroll bars, the scene owned by the view — paints them, drops them, collects three times and asserts through a weak reference that the collector really took each view. Before the fix the child died at its first collection.

**Lesson**: when a process dies with `0xC0000409` and no traceback under PyQt, suspect an exception inside a method Qt called — and when it dies inside `gc.collect()`, a method Qt called on an object the collector had already cleared. Do not reason about which overrides Qt "could" call during teardown: wrap them all and count, with a flag for "the instance has no attributes left". The answer here was one method, and it was not one anybody would have listed first. The rule that follows is narrow (PF-CAN-61): a method Qt calls on one object while ANOTHER is destroyed — scroll bars, a scene's signals, an event filter — reads only attributes with a class-level default; a `paint()` or a `boundingRect()` is not entered then. And a suite whose every test closes and deletes its widgets cannot see this class of bug at all: it needs one test that drops a canvas on purpose, in a process of its own, because the failure takes the process with it.
