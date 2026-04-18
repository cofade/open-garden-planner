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
