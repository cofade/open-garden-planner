---
name: ogp-qt-cad-reference
description: >
  Domain-theory knowledge pack for Qt Graphics View + CAD geometry as used in
  Open Garden Planner. Load when: touching canvas items or tools, anything
  involving coordinates or the Y-flip, rendering/export (PNG/PDF/SVG/DXF/agent
  render tool), rotation/resize/transformOriginPoint, snapping or the
  constraint solver, drag handles / ItemIgnoresTransformations, curves and
  arcs, scene/signal lifecycle bugs, or writing Qt tests (qtbot, QTest,
  tool.mouse_press). Teaches the mental models a zero-context engineer lacks;
  every claim is grounded in this repo's source and docs.
---

# OGP Qt + CAD Reference

Theory pack for the two technical domains this codebase lives in: the **Qt
Graphics View framework** (PyQt6) and **CAD geometry**. It teaches the mental
models with this repo's real code as the examples. All file paths are relative
to the repo root; all claims verified against source on **2026-07-04 (app
v1.23.0)**. PyQt6 is not always installed in agent containers — verify by
reading source, not by running Qt.

## When NOT to use this skill

- Triaging a live bug → `ogp-debugging-playbook` (and the `/debug-verbose` skill).
- The narrative history of how a fix was found → `ogp-failure-archaeology`.
- Gardening/plant domain rules → `ogp-garden-domain-reference`.
- Which module owns what / layering rules → `ogp-architecture-contract`.
- Build, run, test invocation mechanics → `ogp-build-and-run`, `ogp-validation-and-qa`.
- You are editing pure business logic that never touches `QGraphicsItem`,
  coordinates, rendering, or signals (e.g. `services/task_generator.py`).

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
| z-value | Stacking order within the scene. Layers assign `z_order * 100`; ≥100 is reserved for temporary tool overlays. |

---

## 1. Coordinate systems — the one mental model

There are three frames in any Graphics View app: **local** (item-internal),
**scene** (shared world), and **view/device** (widget pixels). This app adds a
CAD twist, decided in ADR-002 (`docs/09-architecture-decisions/README.md`):
the world is **Y-up, origin bottom-left, units = centimeters**.

The entire Y-up convention is implemented in ONE place — the view transform
(`CanvasView._apply_transform`, `canvas_view.py` ~line 605):

```python
transform = QTransform()
transform.scale(self._zoom_factor, -self._zoom_factor)  # Negative Y for flip
transform.translate(0, -self._canvas_scene.height_cm)
self.setTransform(transform)
```

Composed, this maps scene `(x, y)` → view `(z·x, z·(H − y))` where
`H = height_cm`. Consequences:

- **Scene coordinates ARE the CAD coordinates the user sees.** Scene `(0, 0)`
  renders at the visual bottom-left; larger scene Y is visually higher. The
  status bar shows raw scene coords (`coordinates_changed.emit(scene_pos.x(),
  scene_pos.y())`, `canvas_view.py` ~line 1987). No conversion layer exists in
  the data path — the flip lives only in the display transform.
- The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)`,
  accessed as `scene.canvas_rect` (`canvas_scene.py` ~line 415).
- Qt's *default* convention (any rendering that bypasses `CanvasView` —
  `scene.render()`, minimap, thumbnails, a painter inside `paint()`) is
  **Y-down**: it draws scene y=0 at the *top*. Every Y bug in this repo is
  some surface forgetting which side of the flip it is on.

Beware of two frames of *description* in older docs — **this skill's §1 is the
single owner of the reconciliation; other skills defer here.** §8.10 of
`docs/08-crosscutting-concepts/README.md` calls scene coords "Y-down, (0,0)
top-left" and says to convert with `scene_to_canvas` — that is the abstract Qt
convention, true only for un-flipped renders. The operative rule is §11.4's:
*"The view applies `scale(zoom, -zoom)` so positive scene Y is visually upward
on canvas."* (`docs/11-risks-and-technical-debt/README.md`). The two repo docs
are genuinely split; the data path follows §11.4.

Why the §8.10 framing misleads a test author: `CanvasView.scene_to_canvas()` /
`canvas_to_scene()` (`canvas_view.py` ~line 1433) DO compute `height_cm −
scene_y`, but they have **zero production callers** — grep finds only two callers
in `tests/ui/test_canvas.py`. The status bar, rulers, DXF (`dxf_y = scene_y`),
and serialization all consume **raw** `scene_pos.y()` directly. So an assertion
that pipes an expected value through `scene_to_canvas` produces `H−y`-mirrored
numbers production never emits. **Assert in raw scene coordinates.**

### Surface → what to do about Y (the consequences catalog)

| Surface | What to do about Y | Ground truth |
|---|---|---|
| Item geometry, tool math, serialization, snap, constraints | Nothing. Work in scene cm; the numbers are already CAD Y-up. | whole codebase |
| Screen-intuition directions ("rows go down", "90° = down") | Negate: linear/grid array uses `dy = -spacing * sin(angle_rad)`; grid array steps `-row_spacing` per row. Applies whenever a user-facing angle convention follows *screen* intuition instead of math convention. | §11.4 "Canvas Y-axis flip"; `canvas_view.py` ~4695, ~5015 |
| `painter.drawText()` inside `QGraphicsItem.paint()` | It renders **mirrored** (inherits the flip). Fix: child `QGraphicsSimpleTextItem` with `ItemIgnoresTransformations` (draws in its own non-flipped pixel frame). Anchor at `rect.top()` — smallest scene-Y = *visual bottom* after the flip. | §11.4; `garden_item.py` `_label_item` ~797; `canvas_scene.py` ~857 |
| `scene.render()` to PNG/PDF/image | A negative-height target rect is **EMPTY** in PyQt6 (`QRectF(0, H, W, -H).isEmpty()` is True) — nothing paints. The correct recipe: `painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source)`. `H_PIXELS` = image height in **pixels**, not cm. Canonical implementation: `services/scene_rendering.render_scene_region(..., y_flip=True)` — reuse it, don't re-derive. | §11.4; `scene_rendering.py` lines 180–188 |
| Thumbnails via pixmap | Alternative: render un-flipped, then `pixmap.transformed(QTransform().scale(1, -1))`. Hide `ItemIgnoresTransformations` items and z ≥ 100 overlays first (they'd land at wrong size/position). | §8.9.5 |
| Minimap / any widget mapping its own pixels ↔ scene | Widget pixel Y=0 is visual **top** = scene Y = `height_cm`. Invert: `sy = rect.y() + rect.height() * (1 - my/h)`. | §8.9.6; `minimap_widget.py` |
| PDF (`QPdfWriter`) | Don't pre-flip on the writer's painter (its initial margin transform breaks the formula). Render to a temporary `QImage` (flip is reliable there), then `painter.drawImage(...)`. Also `writer.setResolution(72)` **before** `setPageLayout()`. | §11.4 (two entries) |
| SVG export | Under the `scale(1,-1)` painter flip, `<pattern>` texture tiles render upside-down; post-processed by `ExportService._fix_svg_pattern_yflip()` (adds `patternTransform`). | §11.4; `export_service.py` |
| **DXF export/import** | **NO negation either way.** DXF is Y-up and so is our scene: `dxf_y = scene_y`; import `_y(v) = v * scale`. `dxf_y = canvas_h - scene_y` double-flips (a real past bug). Caution: the `import_file` docstring in `services/dxf_service.py` (~line 324) still says "Y-coordinates are negated" — that comment is **stale and wrong**; the code and the class docstring (~line 94) are correct. | §11.4 "DXF Y-axis"; `dxf_service.py` `_y` helper |
| Agent render tool (`render_canvas_image`) | Output PNG matches the live view (Y-up display), so image *pixel* Y is inverted relative to scene numbers: `px_x = (x_cm - region_x_cm) * px_per_cm`; `px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`. Documented on `RenderMeta.px_per_cm`; pinned by `tests/unit/test_agent_api_render_coordinate_frame.py`. | §8.19; `agent_api/render.py` |
| Item rotation angles | Serialized as a separate angle pivoting on the centre (see §2 below). `core/cad_geometry.py` documents its convention per function — arc math is "degrees CCW from +X" (math convention); one helper explicitly notes Qt's "clockwise-positive in y-down space" screen convention. Read the docstring of the function you call. | `cad_geometry.py` lines 196–198, 272, ~498 |

**Test-writing corollary**: tool integration tests pass *scene* coordinates to
`tool.mouse_press(event, scene_pos)` directly (§8.10) — no flipping. Only
view-pixel-level tests (`QTest` on the viewport) need `view.mapFromScene()`.

---

## 2. The QGraphicsItem geometry contract

Three different "where is it" answers, and this repo's specific convention:

- `pos()` — where the item's local origin sits in its parent's frame.
- `rect()` — the *geometric* shape rect (only on rect-bearing items:
  `CircleItem`, `RectangleItem`, `EllipseItem`).
- `boundingRect()` — the repaint region; geometry **plus decorations** (badge
  overflow, spacing-ring expansion). May be asymmetric.

**Repo convention: items keep `pos() == (0, 0)` and store geometry in local
coords.** `item.pos()` and `item.scenePos()` both return (0,0) for a plant;
the visual centre is `item.mapToScene(item.boundingRect().center())` (§11.4
"Plant items store center in boundingRect(), not in pos()"). Items *can* end
up with nonzero `pos()` after drags/resizes, which is why the serializer
always sums both:

```python
# core/project.py (~line 1428, EllipseItem branch — Circle/Rect analogous)
cx = item.pos().x() + rect.center().x()
cy = item.pos().y() + rect.center().y()
```

### The one invariant: `transformOriginPoint() == rect().center()`

The serializer saves `pos + rect.center()` as the centre and rotation as a
**separate angle pivoting on the centre**. So every geometry mutation —
rotate, programmatic resize, interactive drag-resize, and the undo/redo of any
of them — must end with `transformOriginPoint() == rect().center()`, or a
rotated item's saved centre diverges from its on-screen centre: it **drifts on
reload and jumps on the next rotation**. It looks correct on screen
immediately, so unrotated tests pass green. (§8.9.8; issues #213/#218/#219.)

Do not re-derive this per gesture. Route through the two blessed primitives:

1. **Resize** → `resize_rect_item_keeping_anchor(item, new_rect, scene_anchor,
   local_anchor)` in `src/open_garden_planner/ui/canvas/items/resize_handle.py`
   (~line 46). It calls `prepareGeometryChange()`, applies the rect, re-pins
   the origin to the new centre, and solves the position so a chosen scene
   point stays fixed. The math (Qt maps local `p` → scene as
   `pos + O + R(θ)·(p − O)` with `O = transformOriginPoint`):

   ```
   pos = scene_anchor − O − R(θ)·(local_anchor − O)
   ```

2. **Rotate** → `RotationHandleMixin._apply_rotation` (same file), which
   pivots on `rect().center()` when the item has `rect()`, else
   `boundingRect().center()` (Text/Callout/Polyline — no asymmetric
   decorations).

Lessons baked into those primitives (don't undo them):

- **#219**: the pivot must come from the geometric `rect()`, never the
  decoration-expanded `boundingRect()`. A runtime-only antagonist badge
  expands `boundingRect()` asymmetrically (+x/+y only); pivoting there made
  the save-time pivot (badge on) disagree with the load-time pivot (badge off)
  — a rotated badged plant drifted on save/reload *with no resize involved*.
- **#218**: the interactive `ResizeHandle._apply_resize` takes the fixed
  corner/edge **authoritatively from the handle position** (scene-space
  inference and rotated-local inference disagree under rotation); the item
  normalises the rect itself (`CircleItem._constrain_resize_size`, ~line 589,
  squares it so the dragged handle tracks the cursor — never `min(w, h)`,
  which collapses at 45°); then `_after_resize_geometry()` refreshes
  bookkeeping. Do not post-correct an incoherent geometry step — fix the step.
- **`prepareGeometryChange()` duty**: any code that can *shrink* a custom
  `boundingRect()` must call it first or Qt leaves a stale "ghost" of the old
  extent (the spacing ring made this visible in #218).
- Programmatic centred resize: `CircleItem.set_radius_centered()`
  (`circle_item.py` ~line 464) — resizes footprint, re-pins origin,
  repositions so `pos + center` stays put. Pinned by
  `test_apply_keeps_rotated_plant_centered`.
- **Any resize-under-rotation change needs an explicit rotated-item test** —
  see `tests/integration/test_rotation_aware_resize.py`
  ({Circle,Rect,Ellipse} × {0°, 45°, 215°} × {corner, edge}).

Plant sizing precedence (footprint radius vs `spacing_radius_cm` override vs
DB `max_spread_cm`) has one Qt-free home: `core/plant_sizing.py`. Never inline
it.

---

## 3. `ItemIgnoresTransformations` — what it buys and its two traps

The flag makes an item render in device pixels, ignoring the view's zoom *and*
the Y-flip. That's why it is the standard fix for readable, right-side-up text
and constant-size handles: labels (`garden_item.py`), dimension/constraint
text (`dimension_lines.py`, `constraint_tool.py`), badges
(`soil_badge_item.py`), and **all drag handles** in `resize_handle.py`.

**Trap 1 — fixed device-pixel size under `scene.render()`** (§11.4). Outside
a view there is no zoom, so an IIT text item renders at its natural pixel
size regardless of the source→target scale: a 10 pt label on a 5300 cm canvas
rendered into a 774 px image comes out ~80+ cm wide. Fix: call
`ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering
and `_restore_text_after_export()` after (`export_service.py` ~line 105;
`scale = output_width_cm / canvas_width_cm`). The flag stays ON — only the
point size is retargeted. `render_scene_region`'s `text_point_size` argument
is the same idea for the shared pipeline.

**Trap 2 — PyQt6 silently drops the mouse grab on IIT child handles**
(§11.4, #193 follow-up; ADR-025 consequence 7). A handle grabs the mouse in
`mousePressEvent`, Qt loses the grab before the first `mouseMoveEvent`, and
the drag is inert ("handle shows but won't move"). The workaround lives in
`CanvasView`:

- On press (~line 1961) it records the grabber, but **only if it is in the
  isinstance allow-list**: `(ResizeHandle, RotationHandle, VertexHandle,
  RectCornerHandle, MidpointHandle, CurveControlHandle)`.
- On every `mouseMove` (~2050) and `mouseRelease` (~2674, *before* `super()`)
  it re-grabs: `if self._active_drag_handle is not None and
  scene().mouseGrabberItem() is None: self._active_drag_handle.grabMouse()`.

**Contract: every NEW handle type using IIT MUST be added to that allow-list**
— a faithful copy of an existing handle is still dead until the view knows its
type (this exact miss cost a manual-test round for `CurveControlHandle`).
Grep `_active_drag_handle` to find the sites.

---

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

## 5. Snap engine + constraint solver theory

### Snap pipeline (ADR-020/023, §8.16)

`core/snap/` is a pure orchestration layer over existing geometry helpers
(`measure_snapper.get_anchor_points`, `core/snap/geometry.item_edges`) — it
owns no point enumeration of its own. Architecture:

- **Provider registry**: each `SnapProvider` owns one mode and a `priority`;
  the registry picks the lowest priority, then distance. Verified priorities:
  endpoint **10** < intersection **15** < center **20** < perpendicular **25**
  < tangent **26** < midpoint **30** < edge **40** < nearest **45** (`core/
  snap/providers/*.py`). Two candidates within sub-pixel distance are common
  (a corner is also two edge endpoints) — priority, not distance, breaks it.
- **QuadTree** (`core/snap/spatial_index.py`): bounded depth 6; items spanning
  multiple quadrants are inserted into *every* overlapping child, deduped at
  query time via an `id()` set. Rebuilt **lazily** by
  `CanvasView._ensure_snap_index()` on the first query after `scene.changed`
  — never eagerly per signal (~3 ms build at 1000 items would dominate).
- `PointSnapper.snap()` widens the query window to 4× the threshold so
  intersections of edges starting outside the cursor area still surface;
  the O(n²) intersection step is capped at `MAX_SEGMENTS_PER_QUERY = 60`.
- **Reference-point providers** (ADR-023): perpendicular and tangent are not
  functions of cursor+scene alone — they need the active tool's `last_point`,
  passed as the optional `reference_point` kwarg through
  `SnapRegistry`/`PointSnapper` (providers stay pure functions; no provider
  reaches into the view).
- Integration rule: `CanvasView._maybe_apply_anchor_snap` is the single
  dispatcher; anchor snap beats grid snap because `snap_point()`
  short-circuits grid rounding when a point-snap matched. Tools opt out via
  `BaseTool.skip_anchor_snap = True`. Each snap kind must also get a glyph in
  `_draw_point_snap_glyph` (square=endpoint, circle=center, triangle=midpoint,
  X=intersection, dot=edge, hourglass=nearest, ⊥=perpendicular).

### Constraint solver (ADR-012, §8.12)

`core/constraints.py` + `core/constraint_solver_newton.py`; **17** constraint
types (`ConstraintType` in `core/constraints.py` — TANGENT was added by ADR-024;
docs/08 §8.12's "16 types" line and its §8.12.8 residual table are stale on this
count); **two-phase solve** in every `solve_anchored`:

1. **Gauss-Seidel warm start** — each constraint resolved by a 1-D projection
   along its own direction. Cheap; converges when constraints don't couple.
   Cap: 20 iterations.
2. **Newton-Raphson refinement** — only when the warm-start residual exceeds
   tolerance. Stacks all non-orientation constraints into a residual vector
   `F(x)`; damped Newton on `J·Δx = −F` with a *numerical* central-difference
   Jacobian (`h = 1e-3 cm`), `numpy.linalg.lstsq` (rank-deficient →
   minimum-norm step), Armijo backtracking (α halves, accept only strict
   `max|F|` decrease). Caps: 25 Newton iterations, 15 backtracks.

Why two phases: Gauss-Seidel alone cannot solve coupled systems — canonical
case: two `EDGE_LENGTH` constraints sharing a vertex; the feasible point is a
two-circle intersection unreachable by alternating 1-D projections. For that
exact case a **geometric fast path** exists: `two_circle_intersection()`
(closed form; returns the root nearest the current vertex, `None` → fall back
to Newton).

Convergence: `max|F| ≤ tolerance`; default **0.1 cm**, relaxed to **1.0 cm**
for drag-time solves. The per-type residual formulas (all scaled to cm) are
tabulated in §8.12.8 of `docs/08-crosscutting-concepts/README.md` — read them
there before adding a type. Which types Newton skips vs which permit resize are
two *different* sets — don't conflate them:
- **Newton skips `PARALLEL`, `PERPENDICULAR`, `EQUAL`, `FIXED`** (warm-start-only,
  `constraint_solver_newton.py` ~lines 128–140). `HORIZONTAL` and `VERTICAL` DO
  get Newton residuals (`ay − by` / `ax − bx`, ~lines 193–196) — a solver
  investigator told "Newton skips HORIZONTAL" would look in the wrong phase.
- **The resize-permitting set is the five *scale-invariant* orientation types
  `HORIZONTAL`, `VERTICAL`, `PARALLEL`, `PERPENDICULAR`, `EQUAL`** (any other,
  including `FIXED`, blocks resize) — `_has_blocking_constraints` in
  `ui/canvas/items/resize_handle.py` ~line 246.

**The sub-pixel tolerance lesson (PR #169, §11.4)**: live-drag projection
(`ConstraintGraph.project_to_feasible`) must use `tolerance=1e-4`, not a
cm-scale tolerance. `newton_refine` early-returns when `max_err <= tol`, and
the iteration *starts* from the raw cursor position — with 0.5 cm slack the
cursor near a feasible point returns **unchanged** frame after frame, letting
a "fully constrained" vertex slip up to the slack band per frame (looks like
the whole rigid polyline translating). Full-graph solves keep cm tolerances;
only the per-frame projection needs sub-render precision.

Conflict detection on add: the view trial-runs the solver
(`find_conflicting_constraints`); existing constraints with post-solve
residual > 1.0 cm trigger the Override/Cancel dialog instead of silently
distorting geometry.

---

## 6. Curves and arcs (ADR-022/025, `core/cad_geometry.py`)

The Qt-free geometry kernel is `src/open_garden_planner/core/cad_geometry.py`.
Verified contents: `point_to_segment_distance`, `segment_segment_intersection`,
`collect_intersections_on_segment`, `polyline/polygon/rectangle_to_scene_segments`,
`arc_from_three_points`, `arc_to_painter_path`, `fillet_corner`,
`chamfer_corner`, `reflect_point`, `reflect_angle_deg`,
`snap_point_to_axis_step`.

- **Cubic Bezier is the single curve model** (ADR-022). Each anchor stores
  `handles_in[i]` + `handles_out[i]`; segment i→i+1 renders as
  `path.cubicTo(handles_out[i], handles_in[i+1], anchors[i+1])`. Authoring is
  Illustrator-style click-drag with the mirror-handle smooth default. Item:
  `ui/canvas/items/bezier_item.py`; undoable mutations in `core/commands.py`.
- **3-point arc** (`arc_from_three_points`): circumcenter via the signed-area
  determinant (`d > 0` = the three points wind CCW); collinear (|d| below
  epsilon) → caller falls back to a polyline. Returns
  `(center, radius, start_deg, span_deg)` with angles in **degrees CCW from
  +X, span signed (positive CCW)** — math convention, documented per function.
- **Exact arc rendering** (ADR-025): Qt's `arcTo` drifted rendered endpoints
  up to 0.24 cm on shallow large-radius arcs, so arcs are rendered from exact
  cubic segments instead: `arc_to_painter_path` splits the span into ≤45°
  segments, anchors placed exactly on the analytic circle, control points
  along tangents scaled by `k = 4/3·tan(Δ/4)` (signed for CW spans). Snapping
  never reads the path — only analytic `center`/`radius`.
- **Arc reshape** needs a stable third degree of freedom: `ArcItem` stores its
  through-point, persisted as *additive* `through_x`/`through_y` keys (older
  files derive the angular midpoint on load; `FILE_VERSION` stayed 1.4).
- **Fillet/chamfer** (`fillet_corner` / `chamfer_corner`): polylines and
  polygons mutate in place (vertex split + `ArcItem`). **Rectangles have no
  per-corner geometry slot**, so filleting one is a *destructive, undoable
  conversion*: `RectangleItem` → 5-vertex `PolygonItem` + free-standing
  `ArcItem`; undo restores the original rect; past the undo horizon the
  polygon stays a polygon (ADR-022 — the rejected alternatives there explain
  why).
- Curve editing uses a dedicated `CurveEditMixin` + `CurveControlHandle`
  (selection-driven, keyed on `self.isSelected()`), not the polygon
  `VertexHandle`; undo is a whole-geometry snapshot
  (`SetCurveGeometryCommand`), one command per drag (ADR-025).

---

## 7. Driving events in tests — two tiers, one hard rule

**Tier 1 — tool logic (default)**: bypass the event pipeline via the tools'
direct API (§8.10):

```python
event = MagicMock(spec=QMouseEvent)
event.button.return_value = Qt.MouseButton.LeftButton
tool.mouse_press(event, QPointF(x, y))   # scene coordinates, cm
```

Always `view.set_snap_enabled(False)` in tests; always take the `qtbot`
fixture even if unused (Qt init).

**Tier 2 — anything involving drag handles**: a hand-built `QMouseEvent` is
**NOT delivered to an `ItemIgnoresTransformations` child item** (§11.4 mouse-
grab entry). You must go through the real event pipeline with `QTest` on the
**viewport**, after bringing the handle on-screen:

```python
# pattern from tests/integration/test_curve_vertex_edit.py (~lines 234–283)
canvas.show(); QTest.qWaitForWindowExposed(canvas)
canvas.centerOn(handle.scenePos())        # handle must be inside the viewport
vp_pos = canvas.mapFromScene(handle.scenePos())
QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=vp_pos)
QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(target_scene))
QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=...)
```

`QT_QPA_PLATFORM=offscreen` makes this work headless in CI. Remember
`mapFromScene` already includes the Y-flip — feed it scene coords and trust it.

---

## Provenance and maintenance

Facts verified 2026-07-04 against v1.23.0 source + `docs/08-crosscutting-concepts/README.md` (§8.1/8.9/8.10/8.12/8.16/8.19), `docs/09-architecture-decisions/README.md` (ADR-002/012/020/022/023/025/028), `docs/11-risks-and-technical-debt/README.md` §11.4. Re-verify volatile claims:

- Y-flip transform: `grep -n "scale(self._zoom_factor" src/open_garden_planner/ui/canvas/canvas_view.py`
- Handle allow-list + re-grab: `grep -n "_active_drag_handle" src/open_garden_planner/ui/canvas/canvas_view.py`
- Snap priorities: `grep -rn "priority = " src/open_garden_planner/core/snap/providers/`
- Resize primitive: `grep -n "def resize_rect_item_keeping_anchor" -A 20 src/open_garden_planner/ui/canvas/items/resize_handle.py`
- DXF Y handling: `grep -n "def _y" -A 4 src/open_garden_planner/services/dxf_service.py`
- Render flip recipe: `sed -n '179,189p' src/open_garden_planner/services/scene_rendering.py`
- Serializer centre convention: `grep -n "center_x" src/open_garden_planner/core/project.py | head`
- Constraint-type count (expect 17): `awk '/^class ConstraintType/{f=1;next} /^class /{f=0} f&&/^    [A-Z_]+ *[=(]/{c++} END{print c}' src/open_garden_planner/core/constraints.py`; Newton skip list: `grep -n "ConstraintType.PARALLEL" -A 4 src/open_garden_planner/core/constraint_solver_newton.py`
