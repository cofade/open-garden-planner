## Quick glossary (Qt terms, defined once)

| Term | Meaning here |
|---|---|
| `QGraphicsScene` | The model-ish container of all drawable items. Ours: `CanvasScene` (`src/open_garden_planner/ui/canvas/canvas_scene.py`). Infinite coordinate plane; items live in **scene coordinates**. |
| `QGraphicsView` | A widget that displays a scene through a transform (zoom/pan/flip). Ours: `CanvasView` (`src/open_garden_planner/ui/canvas/canvas_view.py`, ~5900 lines — the app's interaction hub). |
| viewport | The inner widget of a view where pixels are actually painted. `view.viewport()` — the target for synthetic mouse events in tests. |
| `QGraphicsItem` | One drawable thing in a scene. Has its own **local coordinates**; `pos()` places local origin in the parent's (usually scene's) frame. |
| `boundingRect()` | Item-local rect Qt uses for repaint/culling. May be larger than the geometry (decorations, badges). |
| `prepareGeometryChange()` | Must be called *before* an item's `boundingRect()` changes, or Qt leaves stale pixels ("ghosts"). |
| `ItemIgnoresTransformations` | Item flag: draw at fixed device-pixel size, ignoring view zoom/flip. Used for labels, badges, drag handles. |
| mouse grab | The item that receives all mouse moves until release (`scene.mouseGrabberItem()`). |
| signal / slot | Qt's observer pattern. A signal `emit()` synchronously calls connected slots (same thread) unless the connection is queued. |
| `QueuedConnection` | Connection type that posts the slot call to the receiver's thread's event loop — the only safe way to cross threads. |
| `QTimer` | Event-loop timer; `singleShot(0, fn)` = "run after current event processing" (deferral idiom). |
| `QPropertyAnimation` | Animates a Qt property over time (used for sidebar expand/collapse). |
| `QSettings` | Platform-native persistent key/value store for preferences. |
| `QTransform` | 3×3 affine matrix. Note: `t.scale(...)` then `t.translate(...)` applies the *translate first* when mapping a point (later calls compose innermost). |
| `qtbot` | pytest-qt fixture; ensures a `QApplication` exists and manages widget lifetime. Required in every Qt test *even if unused* (repo rule, `CLAUDE.md`). |
| `QTest` | Qt's synthetic-input module (`PyQt6.QtTest`): `QTest.mousePress(widget, ...)` goes through the real event pipeline. |
| z-value | Stacking order within the scene — always **derived**, never stored as intent (issue #338, ADR-043). Each layer owns the open band `[z_order*100, z_order*100+100)`; per-object stacking order (a sparse `stack_order` rank, §8.25) spreads a layer's items across its own band. **Not** "≥100 is reserved for overlays" — that was only ever true on a single-layer plan. Fixed overlay z's are all ≥ 900 (dimension lines 900/901, tool previews 999–1003, journal pins 9500, transient previews 9999, soil badge 10002, minimap cutoff 10000) — see §8.25's reserved-band table for the authoritative list. |

---

