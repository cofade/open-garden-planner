# 8. Crosscutting Concepts

## 8.1 Coordinate System

**Origin**: Bottom-left corner of canvas (CAD convention)
**Y-axis**: Increases upward (mathematical/CAD convention, not screen coordinates)
**Units**: Centimeters internally, displayed as cm or m based on context

```python
@dataclass
class Point:
    x: float  # centimeters, positive = East/Right
    y: float  # centimeters, positive = North/Up (CAD convention)
    z: float = 0.0  # centimeters, elevation (unused in 2D, ready for 3D)
```

Qt's QGraphicsView uses Y-down screen coordinates. The canvas view applies a transform to flip the Y-axis for display while maintaining the CAD convention in the data model.

## 8.2 Command Pattern (Undo/Redo)

All modifications to the document are wrapped in command objects:

```python
class Command(ABC):
    def execute(self) -> None: ...
    def undo(self) -> None: ...

class MoveObjectCommand(Command):
    def __init__(self, obj: GardenObject, old_pos: Point, new_pos: Point): ...
```

- Every user action that modifies state creates a Command
- Commands are pushed onto an UndoStack (QUndoStack)
- Undo history clears on project close (standard behavior)
- Each vertex operation, property change, etc. is a separate undoable command
- The `CommandManager` is owned by `CanvasView` and shared with `CanvasScene` via `scene.get_command_manager()` so that `QGraphicsItem` subclasses can push commands directly when handling resize, rotation, or vertex-editing interactions
- Operations that change both geometry and position (e.g. scaling from a left handle) must be captured in a single command to avoid requiring multiple undos

## 8.3 Internationalization (i18n)

Uses Qt Linguist translation system:

1. All user-facing strings wrapped in `self.tr()` or `QCoreApplication.translate()`
2. Source strings extracted with `pylupdate6` into `.ts` XML files
3. Translators edit `.ts` files (Qt Linguist tool or text editor)
4. `.ts` files compiled to `.qm` binary with `lrelease`
5. `QTranslator` loaded at app startup based on saved language preference

**Shipped languages**: English (default), German
**Extensible**: Community can add languages by creating new `.ts` files

**Translation files location**:
- `src/open_garden_planner/resources/translations/open_garden_planner_de.ts`
- `src/open_garden_planner/resources/translations/open_garden_planner_en.ts`

**Not translated**: Plant scientific names (Latin), file format identifiers

### How to add translations when creating/modifying a widget

1. **In code**: wrap every UI string with `self.tr("English text")`. The class name is the translation context automatically.

2. **Update both `.ts` files** — add a `<context>` block (or extend an existing one) to both files:

   ```xml
   <context>
       <name>MyWidget</name>
       <message>
           <source>English text</source>
           <translation>Translated text</translation>
       </message>
   </context>
   ```

   Note: German file uses `<name>` with no extra indent, English file uses 4-space indent.

3. **Recompile `.qm` files** after every `.ts` change:
   ```bash
   venv/Lib/site-packages/qt6_applications/Qt/bin/lrelease.exe \
     src/open_garden_planner/resources/translations/open_garden_planner_de.ts \
     src/open_garden_planner/resources/translations/open_garden_planner_en.ts
   ```

### Translation rules

- **Always use `self.tr("string")`** for every user-visible string in any `QWidget` subclass.
- Strings passed to `CollapsiblePanel(title, ...)` must use `self.tr("title")` at the **call site** (e.g. in `application.py`), because `CollapsiblePanel` is generic and has no context for the title string.
- `QT_TR_NOOP("string")` marks strings for extraction without translating them at that point (used in module-level dicts). Translate them later with `QCoreApplication.translate("ContextClass", string)`.
- Non-`QObject` contexts (e.g. module-level code) use `QCoreApplication.translate("ContextName", "string")`.

### Context menu strings in QGraphicsItem subclasses

`QGraphicsItem` subclasses (e.g. `CircleItem`, `PolygonItem`, `BackgroundImageItem`) are **not** `QObject` subclasses, so `self.tr()` is unavailable or incorrect. Use the shorthand alias at the top of every `contextMenuEvent()`:

```python
def contextMenuEvent(self, event):
    _ = QCoreApplication.translate
    action = menu.addAction(_("ClassName", "String"))
```

**Dynamic toggle labels** (e.g. "Lock Image" / "Unlock Image") must call `QCoreApplication.translate` on **both branches individually** so `pylupdate6` can extract both source strings:

```python
# CORRECT — both strings are extractable by pylupdate6
lock_text = (
    _("BackgroundImageItem", "Unlock Image")
    if self._locked
    else _("BackgroundImageItem", "Lock Image")
)

# WRONG — only one branch is extracted
lock_text = _("BackgroundImageItem", "Unlock Image" if self._locked else "Lock Image")
```

This pattern was systematically applied across all item classes in issues #148/#149.

## 8.4 Theme System

Branded green color palette with light and dark variants:

| Color Role | Light Theme | Dark Theme |
|------------|-------------|------------|
| Primary | Garden green | Softer green |
| Surface | White/cream | Dark gray/slate |
| Text | Dark gray | Light gray |
| Accent | Complementary | Complementary |

Applied via QSS stylesheets. Theme preference stored in QSettings.

## 8.5 Graphics Asset Pipeline

### Plant SVGs
- AI-generated illustrations in consistent top-down garden style
- ~15-20 category-based shapes (deciduous, conifer, shrub, flower, etc.)
- ~10 unique popular species (rose, lavender, apple, cherry, etc.)
- Stored in `resources/plants/{category}/{name}.svg`
- Color-tinted at render time based on species data

### Textures
- Tileable PNG textures (256x256 or 512x512)
- Materials: grass, gravel, concrete, wood, stone, water, soil, mulch, sand
- Multiple LOD versions for different zoom ranges
- Loaded as QPixmap, applied via QBrush TexturePattern mode

### Object SVGs
- Furniture and infrastructure illustrations (top-down view)
- Stored in `resources/objects/{category}/{name}.svg`
- Rendered via QSvgRenderer into QGraphicsItem paint method

## 8.6 Development Workflow

### Feature Development Process

1. **Create feature branch**: `feature/US-X.X-short-description`
2. **Read user story** from roadmap
3. **Implement** with type hints
4. **Write tests**, run lint (`pytest tests/ -v && ruff check src/`)
5. **Write integration test** — see section 8.10; mandatory, no exceptions
6. **Manual testing** by user
7. **Commit** after approval: `feat(US-X.X): Description`
8. **Push and create PR** via GitHub CLI
9. **Merge with admin flag** (squash merge)
10. **Switch back to master**: `git checkout master && git pull`

### Code Quality Standards

- **Type hints**: All functions must have type annotations
- **Linting**: Code must pass ruff checks
- **Test coverage**: New code must maintain >80% coverage
- **Line length**: 110 characters (Black/ruff config)

### Git Workflow

- **master branch**: Always deployable, protected
- **Feature branches**: `feature/US-X.X-short-description`
- **Commits**: Small, atomic, conventional commit format
- **PRs**: Required for all changes, must pass CI

## 8.7 Error Handling

- Graceful degradation when APIs are unavailable
- Corrupted project files: partial load with warning
- Auto-save recovery on crash
- No silent failures: all errors logged and shown to user where appropriate

## 8.9 QGraphicsView Overlay Widget Patterns

These rules apply whenever you add a **fixed overlay widget** on top of the canvas (minimap, toolbox, legend, etc.).

### 8.9.1 Widget parenting — always parent to the QGraphicsView, never to its viewport

```python
# WRONG — viewport children scroll with scene content
super().__init__(canvas_view.viewport())

# CORRECT — QGraphicsView (QAbstractScrollArea) children stay fixed
super().__init__(canvas_view)
```

`QGraphicsView.scrollContentsBy()` calls `viewport()->scroll()`, which physically moves every child widget of the viewport. Child widgets of the **QGraphicsView itself** are unaffected.

### 8.9.2 Defer initial positioning with QTimer.singleShot(0, ...)

At construction time the widget has not been shown or laid out, so `viewport().geometry()` may return a zero-size rect. Defer the first `_reposition()` call:

```python
QTimer.singleShot(0, self._reposition)   # fires after event loop iteration
```

Continue repositioning on view resize via `installEventFilter(self)` on the **view** (not the viewport).

### 8.9.3 Use viewport().geometry() for positioning, not view.width()/height()

`viewport().geometry()` is in the QGraphicsView's local coordinate space and already excludes scrollbars. Always use it as the bounding rect when computing overlay position.

```python
def _reposition(self) -> None:
    vp = self._canvas_view.viewport().geometry()
    x = vp.right()  - self.width()  - MARGIN
    y = vp.bottom() - self.height() - MARGIN - extra_clearance
    self.move(max(vp.left(), x), max(vp.top(), y))
    self.raise_()
```

### 8.9.4 Account for viewport-drawn overlays (scale bar, rulers)

The canvas draws a **scale bar** in the bottom-right corner and **rulers** along the top and left edges directly in the viewport's `paintEvent` — they are **not** separate widgets. Fixed overlays must clear their reserved space:

| Drawn overlay | Location | Reserved space |
|---------------|----------|----------------|
| Rulers (top & left) | top 20 px, left 20 px | `CanvasView.RULER_SIZE = 20` |
| Scale bar | bottom-right | `CanvasView.SCALE_BAR_RESERVED_PX = 40` |

```python
from open_garden_planner.ui.canvas.canvas_view import CanvasView

sb = CanvasView.SCALE_BAR_RESERVED_PX if self._canvas_view.scale_bar_visible else 0
y = vp.bottom() - self.height() - MARGIN - sb
```

### 8.9.5 Scene thumbnail rendering — Y-flip and item filtering

`QGraphicsScene.render()` renders in raw scene coordinates (Y increases downward). The canvas view applies a Y-flip transform. Flip the resulting pixmap:

```python
pixmap = scene.render(painter, target, source_rect)
thumbnail = pixmap.transformed(QTransform().scale(1, -1))
```

Before rendering, **hide screen-space overlay items** that would appear at wrong positions or wrong sizes in the thumbnail:

```python
hidden = []
for item in scene.items():
    if (item.isVisible() and (
        bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        or item.zValue() >= 100          # temporary tool overlays
    )):
        item.setVisible(False)
        hidden.append(item)

# ... render ...

for item in hidden:
    item.setVisible(True)
```

`ItemIgnoresTransformations` is set on: measurement/constraint text labels, dimension display handles, angle display handles. Z-value ≥ 100 is set on: active measure tool lines, constraint preview geometry.

### 8.9.6 Coordinate mapping with Y-flip

Minimap Y=0 is the **visual top** of the canvas, which corresponds to **scene Y = canvas_height** (max scene Y). All coordinate conversions must invert Y:

```python
# minimap pixel → scene
sx = canvas_rect.x() + (mx / w) * canvas_rect.width()
sy = canvas_rect.y() + canvas_rect.height() * (1.0 - my / h)   # inverted

# scene → minimap pixel (for viewport rect overlay)
ry = (canvas_rect.height() - (scene_max_y - canvas_rect.y())) * scale_y
```

### 8.9.7 Thumbnail aspect ratio — size the widget, don't letterbox

Never stretch a canvas thumbnail into a fixed aspect-ratio widget — this produces gray bars when the canvas has a different proportion. Instead, **resize the overlay widget** to match the canvas aspect ratio within maximum dimensions:

```python
if canvas_w / canvas_h > MAX_W / MAX_H:
    w, h = MAX_W, int(MAX_W * canvas_h / canvas_w)
else:
    h, w = MAX_H, int(MAX_H * canvas_w / canvas_h)
self.setFixedSize(w, h)
self._reposition()
```

## 8.8 Settings Storage

User preferences stored via QSettings (platform-native):
- Window size, position, panel collapse states
- Recent files list
- Theme preference (light/dark)
- Language preference
- Auto-save interval
- Grid and snap settings
- Last used export options

## 8.10 Integration Test Policy

**Every user story (US) must ship with at least one end-to-end integration test. No merge without it. No exceptions.**

### Rationale

Unit tests and widget tests protect individual components but cannot catch regressions in the interaction between tools, canvas, and scene — the most failure-prone area of the app. Integration tests lock in observed behavior so that refactoring and feature additions don't silently break existing workflows.

### Test location

All integration tests live in `tests/integration/`. Shared fixtures are in `tests/integration/conftest.py`.

### Minimum requirement per US

Each US must have at least one test that exercises its **primary workflow** end to end:

1. Activate the relevant tool (if applicable)
2. Simulate the user gesture (mouse press → move → release)
3. Assert the resulting scene state (item created, property changed, item removed, etc.)

### How tool interaction is tested

Tools expose a direct API that bypasses the Qt event pipeline while still testing real business logic:

```python
tool.mouse_press(event, scene_pos: QPointF)
tool.mouse_move(event, scene_pos: QPointF)
tool.mouse_release(event, scene_pos: QPointF)
```

- `event`: `MagicMock(spec=QMouseEvent)` with `event.button.return_value = Qt.MouseButton.LeftButton`
- `scene_pos`: Qt Y-down scene coordinates (not canvas Y-up coordinates)
- Always disable snapping in tests: `view.set_snap_enabled(False)`

### Standard fixture pattern

```python
@pytest.fixture
def canvas(qtbot):
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view
```

### Coordinate system reminder

- **Scene coordinates** (Y-down, what tools receive): `(0, 0)` is top-left
- **Canvas coordinates** (Y-up, what the user sees): `(0, 0)` is bottom-left
- Pass scene coordinates to tool methods; use `view.scene_to_canvas()` / `view.canvas_to_scene()` when conversion is needed

### What integration tests cover

| Category | File | Tests |
|----------|------|-------|
| Drawing workflows | `test_drawing_workflows.py` | Rectangle, Circle, Polygon, Text, cancel |
| Tool switching | `test_tool_switching.py` | Default tool, switch, cancel-on-switch, Escape |
| Selection & resize | `test_selection_and_resize.py` | Select, deselect, move, mid-edge constraint, corner |
| Undo/Redo | `test_undo_redo.py` | Draw→undo, draw→undo→redo, move→undo, multi-action stack |

### CI

Integration tests run automatically in CI (`ci.yml`) alongside unit and widget tests. Qt rendering uses `QT_QPA_PLATFORM=offscreen` — no display server required.

## 8.11 Security Scanning (SAST)

**Tool:** [Bandit](https://bandit.readthedocs.io/) — a Python SAST tool that detects common security anti-patterns (subprocess injection, unsafe deserialization, weak cryptography, hardcoded secrets, etc.).

**CI enforcement:** The `security` job in `ci.yml` runs `bandit -r src/ --severity-level high` on every push. CI fails only on HIGH-severity findings. MEDIUM and LOW findings are printed in the log for awareness but do not block merges.

**Local use:**
```bash
venv/Scripts/python.exe -m bandit -r src/ --severity-level high

# See ALL findings (MEDIUM + LOW) for awareness:
venv/Scripts/python.exe -m bandit -r src/
```

**Suppressing a false positive** (use sparingly — always add a justification comment):
```python
result = subprocess.run(cmd)  # nosec B603 — cmd is constructed internally, never from user input
```

**Scope:** `src/` only. Test files are excluded — `assert` statements and test helpers are intentional and not security-relevant.

## 8.12 Constraint Solver Architecture

The constraint solver lives in [`core/constraints.py`](../../src/open_garden_planner/core/constraints.py) and [`core/constraint_solver_newton.py`](../../src/open_garden_planner/core/constraint_solver_newton.py). It supports 16 constraint types and runs in two phases.

### 8.12.1 Constraint types

Defined in `ConstraintType`. Grouped by the invariant they express:

| Category | Types |
|---|---|
| Dimensional (scale-sensitive) | `EDGE_LENGTH`, `DISTANCE`, `HORIZONTAL_DISTANCE`, `VERTICAL_DISTANCE`, `POINT_ON_CIRCLE`, `ANGLE` |
| Positional | `COINCIDENT`, `POINT_ON_EDGE`, `SYMMETRY_HORIZONTAL`, `SYMMETRY_VERTICAL`, `FIXED` |
| Orientation (scale-invariant) | `HORIZONTAL`, `VERTICAL`, `PARALLEL`, `PERPENDICULAR`, `EQUAL` |

### 8.12.2 Two-phase solve

Every `solve_anchored` call runs in two phases:

1. **Gauss-Seidel warm start** — each constraint is resolved by a 1D projection along its own direction. Cheap, robust for decoupled systems, converges in O(N) iterations when the constraints don't share variables in geometrically independent directions.
2. **Newton-Raphson refinement** — runs when the Gauss-Seidel residual exceeds tolerance. Treats the free variables as a single vector `x`, builds a residual vector `F(x)` from all non-orientation constraints, and takes damped Newton steps on `J · Δx = −F`. The Jacobian is computed numerically via central differences (`h = 1e-3 cm`); the step uses `numpy.linalg.lstsq` so rank-deficient systems yield a minimum-norm step. Armijo backtracking (α halves per failed step) accepts only moves that strictly reduce `max|F|`.

Convergence criterion: `max|F| ≤ tolerance` (default 0.1 cm; 1.0 cm for drag-time solves where cm-level drift is invisible). Caps: 20 Gauss-Seidel iterations, 25 Newton iterations, 15 backtrack steps.

### 8.12.3 Why two phases

Gauss-Seidel alone fails on coupled systems — the canonical case is two `EDGE_LENGTH` constraints sharing a vertex. The feasible vertex position is the intersection of two circles, which cannot be reached by alternating 1D projections. Newton handles the 2D move. In the non-coupled majority case, Newton returns immediately because Gauss-Seidel already hit tolerance.

### 8.12.4 Geometric fast path

For the shared-vertex EDGE_LENGTH case, `two_circle_intersection()` in `constraint_solver_newton` provides a closed-form solution. Returns the intersection root nearest the current vertex; returns `None` for non-intersecting circles so the caller can fall back to Newton.

### 8.12.5 Live vertex drag projection

`ConstraintGraph.project_to_feasible()` is called from the vertex-drag `mouseMove` path. It pins every variable except the moving vertex, runs Newton on just the constraints touching that vertex, and returns the closest feasible point to the raw cursor position. Short-circuits when no constraint touches the vertex — zero cost for unconstrained drags.

### 8.12.6 Scale handle blocking

`_has_blocking_constraints()` in `ui/canvas/items/resize_handle.py` guards bounding-box resize handles. Orientation-only constraint types (`HORIZONTAL`, `VERTICAL`, `PARALLEL`, `PERPENDICULAR`, `EQUAL`) are scale-invariant and permit resize; any other constraint — including `FIXED`, `EDGE_LENGTH`, `DISTANCE`, `ANGLE`, `SYMMETRY_*`, `COINCIDENT`, `POINT_ON_*` — blocks the drag and emits a translated status-bar hint.

### 8.12.7 Conflict detection on add

Before executing an `AddConstraintCommand`, the canvas view trial-runs the solver with the proposed constraint via `ConstraintGraph.find_conflicting_constraints()`. Existing constraints whose post-solve residual exceeds 1.0 cm are flagged. The user is shown a `ConstraintConflictDialog` (Override / Cancel) rather than letting the solver silently distort existing geometry.

### 8.12.8 Residual formulas (per type, scaled to cm)

| Type | Residual |
|---|---|
| `EDGE_LENGTH`, `DISTANCE`, `POINT_ON_CIRCLE` | `|P_a − P_b| − L` |
| `HORIZONTAL` | `a_y − b_y` |
| `VERTICAL` | `a_x − b_x` |
| `HORIZONTAL_DISTANCE` | `(b_x − a_x) − sign · L` |
| `VERTICAL_DISTANCE` | `(b_y − a_y) − sign · L` |
| `COINCIDENT` | `(a_x − b_x, a_y − b_y)` — 2 residuals |
| `SYMMETRY_HORIZONTAL` | `(b_x − a_x, a_y + b_y − 2·axis_y)` |
| `SYMMETRY_VERTICAL` | `(b_y − a_y, a_x + b_x − 2·axis_x)` |
| `POINT_ON_EDGE` | perpendicular distance from point to edge |
| `ANGLE` | `(acos(ba·bc / (|ba|·|bc|)) − θ_target) · min(|ba|, |bc|)` |
| `PARALLEL`, `PERPENDICULAR`, `EQUAL`, `FIXED` | handled in warm-start; Newton skips |

**Adding new checks:** If a feature introduces a new code pattern that warrants attention (e.g. cryptography, XML parsing, network server code), review the relevant Bandit rule IDs and verify the CI job covers them.

## 8.13 Soil Health Tracking (US-12.10)

Per-bed soil tests are stored on the project itself, not on individual canvas items, so that historical records survive bed deletion and rotation. The model is intentionally minimal in 12.10a — entry + persistence — and is extended by 12.10b–e (canvas overlay, amendment calculator, plant-soil warnings, history sparklines).

### 8.13.1 Data hierarchy

```
.ogp file
└── "soil_tests" : { target_id → SoilTestHistory }
                    target_id ∈ { <bed-uuid>, "global" }
```

Effective record for a bed = bed's latest record → falls back to global latest → `None`. The fallback chain is implemented in `SoilService.get_effective_record` (`src/open_garden_planner/services/soil_service.py`) and used by every consumer (overlay, amendment calc, mismatch warnings).

### 8.13.2 Rapitest categorical scale

| Field | Range | Labels |
|---|---|---|
| `n_level`, `p_level` | 0–4 | Depleted / Deficient / Adequate / Sufficient / Surplus |
| `k_level` | 1–4 | (no K0 on the kit) — Deficient / Adequate / Sufficient / Surplus |
| `ca_level`, `mg_level`, `s_level` | 0–2 | Low / Medium / High |

Lab-mode ppm values (`*_ppm`) are stored alongside the categorical fields so they survive between sub-stories without a second data migration; conversion ppm → categorical lands in 12.10c.

### 8.13.3 Persistence & file version

The dedicated top-level `"soil_tests"` key was introduced with file version **1.3**. Older v1.2 files load with `soil_tests = {}`; re-saving silently upgrades the file to v1.3. There is no automatic downgrade — opening a v1.3 file in an older binary fails the version gate (existing convention).

### 8.13.4 Undo integration

`AddSoilTestCommand` (in `core/commands.py`) snapshots the prior history dict for the target and restores it on undo. This means undoing the very first record for a bed deletes the `target_id` key entirely, while undoing an N-th record restores history of length N-1.

### 8.13.5 Canvas overlay (US-12.10b)

The toggleable soil-health overlay tints each bed by a chosen parameter (Overall / pH / N / P / K). It is painted in `CanvasView.drawForeground` — **never** in `CanvasScene.drawForeground` — so it is automatically excluded from PNG / SVG / PDF / print exports, all of which call `scene.render()` (which only invokes scene-level draw hooks). This mirrors how the grid and ruler-guide overlays are scoped.

Bed shapes are mapped via `item.mapToScene(item.shape())` so rotated beds stay correctly tinted (a `boundingRect()`-based path would over-paint).

The colour mapping lives in `SoilService.health_level(record, parameter)` and `SoilService.overlay_rgba(level)`:

| Level | RGBA tint | Trigger |
|---|---|---|
| GOOD | (100, 200, 100, 80) | pH 6.0–7.0; NPK ≥ 3 |
| FAIR | (255, 200, 0, 80) | pH 5.5–<6.0 / >7.0–7.5; NPK = 2 |
| POOR | (220, 60, 60, 80) | otherwise |
| UNKNOWN | grey `DiagCrossPattern` (alpha 40) | no record at all |

For `"overall"`, the worst non-unknown level across pH/N/P/K wins (all-unknown stays unknown).

The `SoilService` is a single long-lived instance owned by `GardenPlannerApp` and injected into `CanvasView` via `set_soil_service`. The soil-test-entry dialog reuses the same instance, so dialog edits and overlay tint stay consistent without re-querying `ProjectManager.soil_tests`.

### 8.13.6 Amendment calculation (US-12.10c)

`SoilService.calculate_amendments(record, target_ph, target_n, target_p, target_k, bed_area_m2, loader)` is a **pure static method** — no I/O, no service state. Tests assert quantities trivially; the canvas overlay (8.13.5) and the amendment dialogs share the exact same code path.

**Formula** (from roadmap §1976-2030):

```
pH:  qty_g = |target_ph - current_ph| / |effect_per_100g_m2| * 100 * area_m2
NPK: qty_g = (target_level - current_level) * application_rate_g_m2 * area_m2
```

**Priority walk** (one pass, each substance picked at most once):

1. pH (only if `|delta| ≥ 0.1` — below this is measurement noise).
2. N → P → K (any deficit ≥ 1 Rapitest step).
3. Ca → Mg → S, but only if the pH/NPK picks didn't already supply them — e.g. dolomite lime decrements both Ca and Mg deficits before gypsum is considered.

Returns `[]` for `record is None`, `bed_area_m2 <= 0`, or no deficits.

**Data file**: `src/open_garden_planner/resources/data/amendments.json` (12 substances). Loaded once by `AmendmentLoader`, eagerly validated; corrupt JSON raises at startup rather than mid-dialog.

**Two surfaces** consume the same calculator:

| Surface | File | Behaviour |
|---|---|---|
| Inline per-bed list | `SoilTestDialog._refresh_amendments` | Hidden when `bed_area_m2 == 0` (i.e. global default test). Recomputes live as the form values change. |
| Cross-bed plan | `AmendmentPlanDialog` | Walks every bed, groups by substance, sums grams. "Copy to clipboard" is the fallback for US-12.6 shopping-list integration. |

**Targets** default to the same "ideal" definition the canvas overlay (8.13.5) uses for GOOD: `pH 6.5`, `N=P=K=3`. Per-bed overrides are not persisted — 12.10d will derive plant-aware targets from species in the bed.

**EllipseItem note**: `core.measurements.calculate_area_and_perimeter` does not yet support `EllipseItem`. Beds drawn as ellipses are skipped (the calculator returns `[]` for `area=0`). This is a pre-existing gap, tracked separately.

### 8.13.7 Plant-soil compatibility warnings (US-12.10d)

`SoilService.get_mismatched_plants(record, plant_specs)` is a pure static method that compares the effective bed record against each hosted plant's pH window (with a ±0.05 tolerance — only enough to absorb float-rounding from the dialog's 0.1-step pH spinbox) and "high" NPK demand. It returns `[(spec, [reason, …]), …]`. The view layer (`CanvasView._update_soil_mismatches`, debounced 500 ms on `scene.changed`) walks every bed, calls the calculator, and sets `_soil_mismatch_level` on the bed item: `"warning"` for exactly one reason across all hosted plants, `"critical"` for ≥2. `GardenItemMixin._draw_soil_mismatch_border` paints an amber or red border (4 px) outside the rotation ring; a tooltip joins the per-plant reasons. The Dashboard mirrors the warnings via `PlantingCalendarView._inject_soil_mismatch_tasks` (one amber card per mismatched bed). Plant species expose `n_demand`/`p_demand`/`k_demand`; legacy `nutrient_demand="heavy"` falls back to `high` for all three macros via `_effective_demand`.

### 8.13.8 History sparklines & seasonal reminder badge (US-12.10e)

The `SoilTestDialog` is split into two tabs (`QTabWidget`):

| Tab     | Content |
|---------|---------|
| Entry   | Existing form (date, mode, pH, Kit/Lab nutrient panel, amendments, notes). |
| History | Past tests listed date-descending + four `SoilSparklineWidget` charts (pH, N, P, K). Ca/Mg/S still appear in the past-tests list but get no sparkline. |

`SoilSparklineWidget` is a single-parameter QPainter line chart with an auto-scaled y-range bounded to parameter semantics (pH 0–14, NPK 0–4). 0 records → "No history yet" placeholder; 1 record → centred dot; ≥2 → polyline + dots with min/max-y labels and first/last-date labels.

**Seasonal reminder.** `SoilService.is_test_overdue(history, today)` is pure: returns `True` only when `today.month ∈ {3, 4, 9, 10}`, the bed has been tested before, and the latest record is older than 180 days (or its date is unparseable). Untested beds (None / empty history) are deliberately *not* flagged — the badge nudges re-testing, not first-testing.

**Badge.** `SoilBadgeItem` is a `QGraphicsObject` (so it can carry a `pyqtSignal`) with `ItemIgnoresTransformations` so it stays 16 × 16 px regardless of zoom. It anchors to the bed's top-right corner (8 px screen-fixed offset, view-scale-aware just like `RotationHandle`). Click → `clicked = pyqtSignal(str)` carrying the bed UUID; `CanvasView` re-emits as `soil_test_badge_clicked`, which the `Application` wires into the same `_open_soil_test_dialog` flow used by the bed context menu.

Lifecycle: the existing 500 ms debounce timer in `CanvasView.set_soil_service` (introduced for 12.10d mismatch borders) was extended — its `timeout` now calls `_on_soil_debounce_tick` which runs both `_update_soil_mismatches()` and `_update_soil_badges()`. After a soil-test save, `Application._open_soil_test_dialog` calls `refresh_soil_badges()` for an immediate clear (so the badge disappears before the debounce window elapses).

## 8.14 Bed-Specific Features Across All Shape Items (US-12.8 follow-up)

**Why this section exists.** Bed-capable shapes are not one class but four — historical reasons:

| Shape class    | Default bed object_type | Tool that creates it |
|----------------|-------------------------|----------------------|
| `RectangleItem`| `RAISED_BED`            | `Raised Bed` tool    |
| `PolygonItem`  | `GARDEN_BED`            | `Garden Bed` tool    |
| `EllipseItem`  | `GARDEN_BED`            | Generic ellipse → change type |
| `CircleItem`   | `GARDEN_BED`            | Generic circle → change type  |

Twice in three months a new bed-only feature shipped missing from one or more shapes (Pest log on PolygonItem/EllipseItem — fixed in #173; Plan Anbaufolge on all three non-rectangle shapes — fixed post-US-12.8). Root cause: each shape's `contextMenuEvent` hand-rolled its own bed-action block, and there was no test that caught a missed shape.

**Central pattern.** Bed-specific actions are built by **one** method on `GardenItemMixin`:

```python
# garden_item.py
@dataclass(slots=True)
class BedMenuActions:
    toggle_grid: QAction | None = None
    add_soil_test: QAction | None = None
    log_pest_disease: QAction | None = None
    plan_succession: QAction | None = None

def build_bed_context_menu(
    self, menu: QMenu, *, grid_enabled: bool, supports_grid: bool = True
) -> BedMenuActions: ...

def dispatch_bed_action(self, action: QAction | None, actions: BedMenuActions) -> bool: ...
```

Every bed-capable shape's `contextMenuEvent` follows the same skeleton:

```python
bed_actions = BedMenuActions()
if is_bed_type(self.object_type):
    bed_actions = self.build_bed_context_menu(
        menu, grid_enabled=self._grid_enabled, supports_grid=<True for rect/poly, False for round>
    )
# ...assemble the rest of the menu...
action = menu.exec(event.screenPos())
if self.dispatch_bed_action(action, bed_actions):
    return
# ...handle shape-specific actions...
```

**Why a mixin method, not a base class.** `GardenItemMixin` is already shared by all four shapes; adding methods there avoids a deeper refactor and keeps the change minimal. The mixin handles `request_soil_test`, `request_pest_log`, `request_succession_plan` view dispatch and the grid-toggle side effect (`scene.selectionChanged.emit()`) so each shape only has to translate its surrounding non-bed menu items.

**Regression test (the part that prevents recurrence).** `tests/integration/test_bed_context_menu.py` parametrises across all four shape classes and asserts that every bed action exists on every shape:

```python
@pytest.mark.parametrize("factory,supports_grid", BED_SHAPES)
def test_bed_context_menu_has_all_features(factory, supports_grid, qtbot):
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(menu, grid_enabled=False, supports_grid=supports_grid)
    assert actions.add_soil_test is not None
    assert actions.log_pest_disease is not None
    assert actions.plan_succession is not None
```

**Adding a future bed feature** (the playbook):

1. Add a `QAction | None` field to `BedMenuActions`.
2. Add `actions.<new_field> = menu.addAction(...)` in `build_bed_context_menu`.
3. Add a routing branch in `dispatch_bed_action` that calls a `request_*` method on the canvas view.
4. Add the matching `request_*` method + signal on `CanvasView`.
5. Wire the signal in `Application.__init__`.
6. **Extend `test_bed_context_menu.py` with one new `assert actions.<new_field> is not None` line per parametrised shape.**

If you forget step 1–5 the existing test still passes; if you forget step 6 the test will not catch a future regression. The single-line addition in step 6 is the linchpin — treat it as mandatory.

**Upright text badges on the Y-flipped canvas.** Related lesson from the same bug batch: text drawn via `painter.drawText()` inside an item's `paint()` inherits the view's `scale(zoom, -zoom)` and renders **upside-down**. Use `QGraphicsSimpleTextItem` (or a custom `QGraphicsItem` subclass) as a **child** of the item with `ItemIgnoresTransformations`. See `SuccessionBadgeItem` in `garden_item.py` for the multi-line-with-pill-background example; bed name labels (`_label_item`) use `QGraphicsSimpleTextItem` for the simple single-line case.

Cross-references: ADR-017 (decision rationale), `tests/integration/test_bed_context_menu.py` (enforcement), `tests/integration/test_succession.py::TestSuccessionBadgeIndicator` (badge state machine).

## 8.15 Google Maps API Key for the Satellite Background Picker (ADR-019)

**What needs the key.** The "File → Load Satellite Background…" menu opens `MapPickerDialog`, which uses two Google Maps Platform APIs:

| API | Used for | Free tier |
|-----|----------|-----------|
| Maps JS API | The embedded picker map (display + drawing + Places Autocomplete) | Free for display in apps (no $200 credit deduction) |
| Static Maps API | The final satellite image fetch (1–9 calls per import, depending on bbox size) | $200/month credit → ~100k calls free |

**Key location, in priority order:**

1. `OGP_GOOGLE_MAPS_KEY` environment variable (set by your shell or CI).
2. A line in the project-root `.env` file (loaded by `python-dotenv` in `main.py` before anything else).
3. *(future)* Per-user UI in `PreferencesDialog` — stored under `QSettings("cofade", "Open Garden Planner")` at `Network/GoogleMapsApiKey`. Not implemented yet — `services/google_maps_service.has_api_key()` reads only the env var as of ADR-019.

When the key is absent, the menu item is disabled and its tooltip explains where to set it. There is no fallback to a different provider — the dialog is unavailable until the user provides a key.

**One-time setup (developer):**

1. Sign in to <https://console.cloud.google.com/> with the Google account that should pay for any overage.
2. Create a project ("Open Garden Planner Dev").
3. Enable the three APIs the dialog needs: **Maps JavaScript API**, **Places API**, **Maps Static API**.
4. *Billing → Budgets & alerts*: create a budget alert at €1/month so you get pinged if anything ever escapes the $200 free credit.
5. *APIs & Services → Credentials*: create an API key. Restrict it: **API restrictions** = the three APIs above only. **Application restrictions** can stay on "None" for desktop use (HTTP-referrer/IP/Android-package restrictions don't apply to a `.exe`).
6. Paste the key into the project-root `.env`:

   ```dotenv
   OGP_GOOGLE_MAPS_KEY=AIza...
   ```

**Never bundle the key into the release `.exe`.** Anything pinned into the PyInstaller binary can be extracted with `strings` and abused on your bill. Specifically:

- The CI release workflow must NOT inject the secret into the build artifact.
- A GitHub-Action secret is only safe if it stays in CI (e.g. for an integration test) and never ends up in the shipped `.exe`.
- Distributing the key to other users requires them to obtain their own (cheap, ~5 minutes via the steps above).

**Mosaic vs single call.** The Static Maps API caps a single image at 640×640 base × 2 scale = 1280×1280 effective pixels. For typical garden-sized bboxes (≤ ~200 m on a side at high latitudes) one call is enough; for larger areas `google_maps_service.fetch_bbox` falls back to a 2×2 or 3×3 mosaic at the highest zoom that fits the configured `_MAX_GRID = 3` budget (`pick_zoom_and_grid`). Resulting image is stitched with Pillow before reaching the canvas as a single `BackgroundImageItem`.

**Pixel→meter scale is analytical.** Because Static Maps uses Web-Mercator with a known tile pixel size, the scale of the returned image is `mpp = cos(lat) × 2π × 6378137 / (256 × 2^zoom)`. The new `BackgroundImageItem(geo_metadata=…)` constructor reads `meters_per_pixel` from this dict and sets `_scale_factor = 0.01 / mpp` (px-per-cm) automatically — no calibration click. The existing manual calibration (`Calibrate Scale…` context menu) is still available as an override; on reload, a saved `scale_factor` wins over the geo-derived one.

**QtWebEngine import timing.** `from PyQt6 import QtWebEngineWidgets` must run *before* `QApplication(...)` is created — Qt enforces this so it can configure OpenGL sharing. `main.py` does this at module level. Tests that exercise the dialog must either match the same ordering or use a `QWidget` stand-in for `QWebEngineView` (see `tests/integration/test_map_picker_dialog.py::_DummyWebView`).
