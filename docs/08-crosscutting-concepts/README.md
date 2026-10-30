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
- An **Arrange** gesture (Bring to Front/Forward, Send Backward/to Back — issue #338, ADR-043, §8.25) is one `ArrangeItemsCommand`, however many layers or block members it touches; a gesture that changes nothing (already at front/back, no overlapping object to step past) pushes **nothing** onto the undo stack — the seam reports the reason instead (`ui/canvas/arrange.py::build_arrange_command`).

## 8.3 Internationalization (i18n)

Qt Linguist remains the runtime format (ADR-008). English is the source language;
English, German, and Spanish are currently shipped. Registration in `SUPPORTED_LANGUAGES` makes
the full source inventory mandatory for that locale. New UI keys require translations
in every registered target locale in the same PR. The required `Test` CI check enforces
this through `scripts/check_translations.py` and the normal pytest suite (#496).

The canonical inventory comes from fresh PyQt6 extraction plus audited AST/helper/table
sources in `scripts/i18n_bindings.json`. Qt context, source and disambiguation identify a
key. Neither German nor the English template is the inventory authority. Unknown dynamic
lookups fail; finite table additions grow the inventory without a test-list edit.

Run `scripts/update_translations.py`, fill every target catalog (helper scripts
like `fill_translations.py` provide optional assistance), run `scripts/compile_translations.py`,
then `scripts/check_translations.py` in the locked environment. The updater preserves
translations and marks genuinely removed keys vanished. The checker is read-only and
requires exact active keys, completed nonblank targets, preserved placeholders, matching
compiled files and actual Qt lookup results. Retired records cannot satisfy coverage.
English retains source identities. Identical target text is valid for proper names/units.
Current singular-only compilation rejects plural/variant input until tested support is added.

Full commands, source declaration rules and new-language steps: [translation guide](../TRANSLATING.md).
Latin scientific names, provider/user text and machine identifiers are not catalog prose;
finite bundled common names are extracted from the actual bundled species JSON.

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

**Single source of truth: [`ui/theme.py`](../../src/open_garden_planner/ui/theme.py)** (ADR-039). Two complete palettes (`ThemeColors.LIGHT`/`DARK`, key parity pinned by `tests/unit/test_theme.py`) feed one generated application stylesheet (`generate_stylesheet`); the preference (light/dark/system) persists in QSettings and applies live via `apply_theme()` — no restart.

### 8.4.1 Color tokens & the no-hex rule

Base/surface/text/border/accent/status tokens plus the #279 semantic additions: `success_bg`/`warning_bg`/`error_bg`/`info_bg` (tinted banner/card surfaces), `caution` ("this week" urgency yellow), and the `overlay_*` family (dynamic-input overlay — deliberately **constant across modes** because it floats over the always-light canvas). Canvas colors are identical in both modes by design (the garden always renders bright; pinned by `test_default_canvas_color`).

**The no-hex rule**: widget code never hardcodes a chrome color. Styling comes either from the generated stylesheet (via the dynamic properties below) or from the live-palette helpers `theme_color()` / `theme_qcolor()` / `rgba(token, alpha)`. Enforced mechanically by `tests/unit/test_no_hardcoded_qss_colors.py` — the allowlist is EMPTY and stays that way without an ADR-039-documented reason.

### 8.4.2 Typography & widget roles (dynamic properties)

Styled centrally in the generated stylesheet, assigned via `theme.set_text_role(widget, role, color_role)` (which re-polishes, so post-polish changes apply — the §8.17.6 gotcha):

- `QLabel[textRole="h1"/"h2"/"hint"/"small"/"placeholder"]` — size/weight/style
- `QLabel[colorRole="success"/"warning"/"error"/"info"/"caution"/"disabled"/"secondary"]` — semantic text color (orthogonal to textRole; combinable)
- `QPushButton[buttonRole="primary"/"secondary"]` — accent-branded dialog CTAs (welcome dialog)
- `QLineEdit[inputError="true"]`, `QFrame[weatherCard="true"][frostSeverity="orange"/"red"]`
- objectName rules: `#TaskReminderBar` (warning_bg banner), `#UpdateBar` (info_bg), `#constraintsDeleteAllBtn`

> **Do not rename an objectName purely for styling.** For any widget the main window persists — every `QToolBar` — the objectName is also `QMainWindow.saveState()`'s persistence key, so renaming it silently resets that widget's saved layout for every existing user. Add a new selector instead. See §11.4 (#283).

Weight uses `font-weight: 600` (support pinned by `test_theme_tokens.py`; documented fallback is `bold`).

### 8.4.3 Theme propagation contract

`apply_theme()` publishes the resolved palette FIRST (`current_colors()` / `is_dark_theme()` read it live), notifies `register_theme_listener` subscribers (the icon provider clears its cache), restyles via `app.setStyleSheet`, then walks `allWidgets()` duck-typed: widgets exposing `apply_theme_colors(colors)` get palette-driven redraws (CanvasView, dashboards — typically a debounced `schedule_refresh()`); widgets exposing `refresh_theme_icons()` re-request their icons (the three toolbars, the main window's tracked menu actions). New widgets opt in by defining one of the two hooks — no registration list.

### 8.4.4 QSS capability limits

No box-shadow, no transitions, no outline focus rings — focus is a 2 px border swap with 1 px padding compensation (no layout jump). Tabs are underline-style (documentMode: style `QTabBar::tab` directly, `::pane` is partially ignored). Outer popup frames (QMenu/QToolTip) stay square on Windows (rounded corners artifact); only inner menu-item pills get radii.

## 8.5 Graphics Asset Pipeline

### UI icons (chrome — `resources/icons/ui/`, ADR-039)
- Line-icon set on a mechanical contract (24×24, `currentColor` + accent sentinel `#3D8B37`): 150 Tabler-vendored (MIT, pinned release) + 12 bespoke glyphs (#279 + #310)
- Tinted at runtime by the central provider `ui/icons.py` — never fed to QSvgRenderer directly (see §8.21)
- Gates: `scripts/normalize_icons.py` (idempotent canonicalizer) + `scripts/check_icon_conformance.py` + per-icon PROVENANCE — no entry, no merge

### Plant SVGs (`resources/plants/`, ADR-040)
- **Generated, never hand-edited**: all 108 species + 15 category sprites are emitted by `scripts/generate_plant_sprites.py` in the user-approved "Lush Sprite" style; committed files must byte-match regeneration (`--check` + determinism test). See §8.22.
- Top-down, rotation-safe radial shading; QtSvg-subset only; contract in `resources/plants/README.md`, provenance in `resources/plants/PROVENANCE.md`
- Consumed unchanged by `core/plant_renderer.py` (cached pixmaps, stable per-item rotation, optional tint)

### Textures (`resources/textures/`, ADR-042 / #309)
- **Generated, never hand-edited**: all 24 fill-pattern textures (grass, gravel, concrete, wood, water, soil, mulch, roof tiles, sand, stone, glass, hedge, brick, bark, wildflower, terracotta, pebbles, slate, lattice, compost, flagstone, clay, decking, corten) are emitted by `scripts/generate_asset_forge_textures.py` in the "Lush" texture language; committed PNGs must be pixel-identical to regeneration (`--check` + `tests/unit/test_texture_forge_conformance.py`). See §8.24.
- 256×256 px RGB, **1 px = 1 cm** on the canvas (no LOD variants — Qt scales the brush); strictly top-down, no directional light; seamless by construction on a torus, gated by `scripts/check_texture_tileability.py` for every file
- Loaded as `QPixmap` by `core/fill_patterns.py`, recoloured to the user's fill colour by a luminance map (`_tint_texture`: every pixel becomes the chosen colour scaled by the texture's relative luminance, so the colour reads and the detail survives — #502) and applied via `QBrush` texture pattern; the tint-readability band is gated
- Provenance: `resources/textures/PROVENANCE.md` (generator = provenance, one register row per file)

### Object SVGs (`resources/objects/`, ADR-042 / #308)
- **Generated, never hand-edited**: all 24 furniture + infrastructure sprites are emitted by `scripts/generate_object_sprites.py` in the "Lush Object" style (the man-made sibling of the plant art); committed files must byte-match regeneration (`--check` + determinism test). See §8.23.
- Top-down, light from straight above, **no baked shadow** (the item-level painted shadow is the single source — furniture rotation is user-controlled); QtSvg-subset only; viewBox = nominal footprint in cm (gate-read table); contract in `resources/objects/README.md`, provenance in `resources/objects/PROVENANCE.md`
- Consumed unchanged by `core/furniture_renderer.py` (cached pixmaps, stretched to the item rect); gallery thumbnails letterbox by viewBox aspect

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
- **Test coverage**: CI enforces measured per-package line floors; branch coverage is reported separately (ADR-050, ?10.4). Non-UI means every package except `ui`.
- **Line length**: 100 characters in the Ruff configuration; no formatter CI gate is claimed.
- **One dependency source of truth (AUD-052)**: `pyproject.toml` plus the committed `uv.lock` / `pylock.toml`. The old top-level `requirements*.txt` mirrors were removed in #454; toolchain pins, build evidence and the dependency-update runbook live in `docs/07-deployment-view` §7.4.

### Git Workflow

- **master branch**: Always deployable, protected
- **Feature branches**: `feature/US-X.X-short-description`
- **Commits**: Small, atomic, conventional commit format
- **PRs**: Required for all changes, must pass CI

## 8.7 Error Handling

- **Graceful degradation when APIs are unavailable**: external services (Google Maps, Trefle, Perenual, Permapeople) degrade quietly without blocking application workflow.
- **Two-phase atomic project loading (AUD-040, TD-017, #403)**:
  `ProjectManager.load()` deserializes and validates all items, layers, guides, and constraints in memory (Phase 1) before mutating or clearing the active `CanvasScene` (Phase 2). A Phase 1 refusal preserves the scene and document identity, including filename, dirty state, selection and command history. Only an unexpected failure after Phase 2 starts clears `_current_file` (`None`) and marks the document dirty, preventing Save/Ctrl+S from overwriting the previous plan with partial content. `_load_project_file` preserves existing autosave files on every failed load.
- **Missing or corrupt assets load as placeholders (AUD-043, TD-011, #397)**:
  Background images with missing disk paths or invalid embedded image bytes load as non-rendering `BackgroundImageItem` placeholders (`is_placeholder=True`). On subsequent saves, the placeholder re-emits its original raw dictionary so external asset links survive across sessions instead of being silently deleted.
- **Duplicate item UUID detection & re-minting (AUD-043, TD-011, #397)**:
  If a corrupted or hand-edited `.ogp` file contains duplicate `item_id` values, the loader detects the collision, logs a warning, and re-mints a fresh UUID for colliding items, preserving scene graph integrity and unambiguous agent addressing.
- **Undecodable item accounting**:
  Malformed or unknown items in `.ogp` files are skipped with a logged warning, and the skipped count is tracked in `ProjectManager.last_load_skipped_items_count` for diagnostics reporting.
- **Auto-save recovery on crash**:
  Periodic autosaves write to `~autosave_...` next to the project file (or in temp for untitled plans). Autosaves are cleared only after a new file load succeeds.
- **No silent failures — handled logging & crash backstop (AUD-063, TD-023, #405, ADR-052)**:
  Handled errors and warnings across all application components are routed to a persistent rotating file handler (`app.log`, 1 MB, 3 backups) in the user data directory, with console echoing to stderr when available (preventing discarded records in the windowed frozen executable where `sys.stderr is None`). Uncaught exceptions are intercepted by `_install_excepthook` in `main.py`, written to `crash.log`, and surfaced to the user via a recoverable error dialog so unsaved work can be preserved.

### A1 numeric refusal (#453)

The file boundary is `core/plan_io.py`. Invalid numbers anywhere in the raw payload,
including nested group/curve geometry, reject the entire plan before preparation;
they are not silently dropped as malformed items. Phase 1 refusal preserves the
active scene, selection, command history, filename, dirty state and autosave.
Finite inputs can still produce infinite bounds after rotation, image scaling or
group aggregation. The detached-item gate checks Qt's actual bounds and transforms
recursively before applying anything to the active scene; saves check live items too.
Numeric-looking strings in opaque metadata remain text.
All `.ogp` writers validate and encode before replacing files atomically. See the
ADR-003 addendum. The protective identity reset applies only to unexpected failures
after scene mutation.

## 8.8 Settings Storage — One Chokepoint (ADR-041)

User state lives in a platform-native QSettings store (Windows: registry under
`HKEY_CURRENT_USER\Software\cofade\Open Garden Planner`; Linux:
`~/.config/cofade/Open Garden Planner.conf`; macOS: a plist), split across two
wrappers over **one** backend:

| Wrapper | Owns | Keys |
|---------|------|------|
| `app/settings.py` — `AppSettings` | user preferences: recent files, theme, language, auto-save interval, snap toggles, frost thresholds, Agent API port/token/write-toggle, API keys, last-used fillet/chamfer values | flat, grouped by domain (`canvas/`, `appearance/`, `agent_api/`, …) |
| `app/ui_state.py` — `UiStateStore` | UI-only state: window geometry, main splitter sizes; the retained `QMainWindow` layout blob is not replayed by the fixed-layout main window (ADR-062 addendum) | `UiState/` |

Per-panel collapse/expand state is deliberately **not** persisted — the sidebar
accordion starts fully collapsed every session (US-226, ADR-030, §8.17.7).

**The rule: `app/settings.create_qsettings()` is the only place in the repo that
may construct — or even name — `QSettings`.** Everything that persists state
takes its backend from that factory. Enforced by an AST walk over `src/`,
`tests/` and `scripts/` in `tests/unit/test_settings_chokepoint.py` (three test
modules are exempt with stated reasons; `tests/` is in scope because the #283
damage was observed from the test side, and `scripts/` because a dev script runs
outside pytest where nothing isolates it — `installer/` is not scanned only
because it has never touched settings), not by convention: `UiStateStore` built
its own store until #285, which meant it escaped the test isolation layered on
`AppSettings`, and every full-app test read *and overwrote* the developer's real
window geometry and toolbar layout — 120 measured writes from a single test file
(§11.4, ADR-041).

**This section is the single specification of the mechanism.** ADR-041 records the
decision and the alternatives; §11.4 and `CLAUDE.md` record the incident. Neither
restates how it works, because three earlier attempts to keep a second copy in
sync each drifted within one commit. Change the mechanism, change it here.

Three further rules, each gated, each worth understanding before touching this:

- The factory reads `ORGANIZATION_NAME` / `APPLICATION_NAME` from module globals
  **on every call**, never captured at import. That is what lets the test suite
  redirect every consumer at once, which `tests/conftest.py` does at its own
  **import time** (module scope, not in a fixture — pytest imports the root
  conftest before any test module, so even a store built during an import lands
  in the test key; a fixture runs after collection and could not). Do not
  "optimise" the names into a default argument, a module-level tuple or a
  `functools.partial` — `test_rebinding_the_names_redirects_new_stores` will stop
  you, and neither can they retarget an *existing* store (ADR-041).
  **A script outside pytest gets none of this:** it isolates itself through
  `scripts/script_isolation.py` (§8.10), a probe in a scratchpad included. A
  throwaway QApplication name or `QSettings.setDefaultFormat()` redirects nothing:
  the factory passes the module's names, and `QSettings(organization,
  application)` always uses the native format. A review probe that relied on them
  once switched off the owner's Welcome dialog (PF-TST-27).
- **Prefer building a store at runtime over import time.** A module-level
  `_STORE = create_qsettings()` (or one in a class body, decorator or default
  argument) can be redirected by nothing at all once constructed.
  `TestNoStoreIsBuiltAtImportTime` flags it; since the conftest redirection this
  is belt-and-braces rather than load-bearing, and it reads names, so one level
  of indirection defeats it.
- **Never call `QSettings.setDefaultFormat()` or `QSettings.setPath()`** to set
  anything up — not in `src/`, not in a test (both gated). They are process-global
  statics Qt never reverts; a leaked `setPath` to a deleted `tmp_path` once
  poisoned every store built later in the session and broke six unrelated tests
  (§11.4). Redirect the factory instead. The single sanctioned call is
  `isolate_qsettings`'s teardown, which restores the captured `defaultFormat()`
  and then asserts it had not changed — a tripwire, not a silent repair.

**The chokepoint refuses an unsafe production context (#587).** A process that is
not the product or a deliberately isolated script has no business opening the
owner's registry. `create_qsettings()` therefore raises `SettingsIsolationError`
when the module holds the **production** names and any of these is true: the Qt
platform is `offscreen`/`minimal` (the product never runs there), or an exact
agent-session variable is set (`CODEX_SANDBOX`, `CODEX_HOME`, `CLAUDECODE`,
`CLAUDE_CODE*`, `OPENCODE*` — exact names, so `CODEX_API_KEY` does not trigger
it). `OGP_PRODUCT_PROCESS=1`, set by `main()` in `main.py` (not at module import:
a probe that imports `main` for a helper must not inherit the permission), is
the product's way through. A test or script that rebinds the names is allowed;
`script_isolation.isolate_settings()` does that, so no second marker is needed.
`OGP_ALLOW_PRODUCTION_SETTINGS=1` is the explicit override for a one-off tool;
neither the product nor the suite sets it. A plain desktop shell with production
names is allowed — that is how the app runs; the guard refuses headless and
agent/tooling contexts. Pinned by `tests/unit/test_settings_isolation_guard.py`.

**Child processes.** The redirection lives in the test PROCESS. A child that a test
starts does not import `tests/conftest.py`, and on Windows no environment variable
moves the store — it is a registry key. A child that imports the app and builds a
store would read and write the developer's own settings: loading a plan ends with a
write to Recent Files. The rule: **a child has the two names rebound before it can
build a store, and empties its own key when it exits.** For the children of the 3D
engine's tests that is not left to each child. Their environments have one source,
`tests/integration/quick3d_render_support.isolated_env` (gated: §8.10.8), and it puts
a directory holding one `sitecustomize.py` first on the child's `PYTHONPATH`. Python
imports that file at start-up; it imports nothing of the app, waits for the import of
`app/settings.py`, and rebinds the names the moment that module's body has run —
which is before any code can call the factory. At exit it empties the key with
`clear()` AND `sync()`: an exit handler registered before PyQt is imported runs
after PyQt's own, when a store's destructor no longer flushes — on the file
backends a `clear()` alone left the file as it was (measured on Linux). A support script that loads a plan and
is also run by hand (the render driver) rebinds them itself as well, and points the
app's data directory into its own output directory. **Outside pytest nothing does any
of this for you**: a probe script that imports the app must rebind the names first.

What nothing can isolate is the frozen exe: it always uses the production names.
Its `--selftest` therefore builds no settings store and loads no plan — pinned
statically, and from source by counting the stores a real run builds (0). The
8-second smoke test IS the application, started with the user's own settings; it is
given no plan to load.

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

`ItemIgnoresTransformations` is set on: measurement/constraint text labels, dimension display handles, angle display handles. **Stale claim corrected (issue #338):** this section used to say "Z-value ≥ 100 is set on: active measure tool lines, constraint preview geometry", implying z ≥ 100 is itself a reserved overlay band. That was already an oversimplification once multi-layer plans existed — every layer occupies its own `[z_order*100, z_order*100+100)` band, so a perfectly ordinary document item on layer 2+ also carries z ≥ 100 — and it is now additionally imprecise because per-object stacking (§8.25) orders items inside that per-layer band rather than pinning them all to its floor. z is not the right test for "is this a tool overlay"; see §8.25's reserved-z-bands table for the actual fixed overlay ranges (900 and up), and note the illustrative snippet above predates that table — the live overlay-hiding code (`ui/widgets/minimap_widget.py`) uses its own named threshold, not a bare `100`.

**The hide/restore itself emits `scene.changed` — asynchronously — for transformable items.** A `setVisible()` on a transformable item queues `changed([rect])` and then a trailing `changed([])`, delivered on *two separate later event-loop turns* — both *after* the render method has returned; a `setVisible()` on an `ItemIgnoresTransformations` item emits nothing (measured, Qt 6.11 — every handle/label/badge in this app carries the flag, so in production only the curve-edit connector lines are affected). If the thumbnail refresh is (as it should be) driven by `scene.changed`, this is a self-sustaining loop: with a single transformable overlay item on the scene the minimap re-rendered the whole plan ~9×/s forever while idle (issue #305, §11.4). A plain in-call re-entrancy flag does **not** cover it, and a timing window (`singleShot(0)`) is both fragile across Qt versions and drops genuine changes that share the turn. The shipped pattern in `MinimapWidget` is **content-based**: `_do_update()` records `sceneBoundingRect()` of every *transformable* item it hid (the only ones that emit); the `changed` slot (`_on_scene_changed`) ignores an emission iff every rect lies inside one of those (an empty rect list is Qt's trailing no-op — measured, every genuine mutation carries ≥ 1 rect) and schedules a render otherwise. A toggled-off minimap early-returns before rendering at all.

**Rule — every slot connected to `scene.changed` (directly or via a debounce timer it restarts) must be idempotent: compute the final state per item, then apply it once.** Never call `update()`, `setVisible()`, `prepareGeometryChange()`, or add/remove items from such a slot unless the underlying value actually changed, and never do a "clear everything, then set" pass — the item setters' early-return guards (`GardenItemMixin.set_companion_highlight()`/`set_spacing_overlap()`/`set_antagonist_warning()`) cannot help when the handler forces the value through `None` each tick. Both patterns were live in #305: `CanvasView._update_soil_mismatches()` with an unconditional `item.update()` (one bed → loop), and `_update_spacing_overlaps()`/`_update_companion_highlights()` with a clear pass (one gallery-dropped plant → loop). `_update_container_capacity()` is the model to copy. To check a change for a new loop: settle the app for 1.5 s, then assert 0 `scene.changed` emissions and 0 `QGraphicsScene.render` calls over the next 2 s (`tests/integration/test_idle_scene_quiescence.py`).

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

### 8.9.8 Rotatable-item geometry invariant — keep `transformOriginPoint == rect().center()`

Rect-bearing items (`CircleItem`/`RectangleItem`/`EllipseItem`) serialize their position as `pos + rect.center()` with rotation stored as a *separate* angle pivoting on the centre (`core/project.py`). Every geometry mutation on such an item — rotate, programmatic resize, interactive drag-resize, and the undo/redo of any of them — **must end with `transformOriginPoint() == rect().center()`**, or a rotated item's saved centre diverges from its on-screen centre and it drifts on reload / jumps on the next rotation. Do not re-derive this per gesture. **Route every rect-backed resize through `ui/canvas/geometry_apply.py`** (US-D2.2): `apply_rect_like_geometry` is the `apply_func` every `ResizeItemCommand` must be given, and the `build_*_resize` helpers compute the target geometry for either anchor policy. Its module docstring is the authoritative list of callers and exceptions. Below it sit the two lower-level primitives, a coupled pair rather than pick-and-choose: `resize_handle.resize_rect_item_keeping_anchor(item, new_rect, scene_anchor, local_anchor)` (mutating: `prepareGeometryChange()`, apply rect, re-pin origin, reposition so a chosen scene point stays fixed), whose `scene_anchor` must come from the pure forward transform `scene_point_of` — never hand-derived — and `anchored_position`, the inverse form the `geometry_apply` builders solve `pos` through. **Never hand-derive a position beside a re-pin** — `anchored_position` bakes in `O = new_rect.center()`, so a `pos` computed by hand under the *old* origin and then combined with a re-pin is two half-solutions to one transform: that combination slid a rotated rectangle 671 cm out from under the cursor (§11.4). Rotation goes through `geometry_apply.apply_rotation`, the only definition in the codebase (it delegates to `RotationHandleMixin._apply_rotation`, which pivots on `rect().center()`). Note `ResizeItemCommand` accepts **two** callables — `apply_func` and each `partner_resizes` entry's — and both must obey this. For rect-backed items, the interactive `ResizeHandle._apply_resize` takes the fixed corner/edge **authoritatively from the handle position**, never inferred from scene-space, which disagrees with the item frame under rotation. It lets the item normalise the rect (`CircleItem._constrain_resize_size` squares it so the dragged handle tracks the cursor — never `min(w,h)`, which collapses under rotation), then refreshes via `_after_resize_geometry()`. The non-rect fallback (PolygonItem) is exact compensation, not an alignment accident: it rotates the local delta into scene space (`pos_dx * cos_a - pos_dy * sin_a`) before applying it, so the dragged edge tracks the cursor and the opposite edge stays fixed under rotation too. The pivot must come from the *geometric* `rect()`, never the decoration-expanded `boundingRect()` (a runtime-only badge expands the latter asymmetrically); and any shrink of a custom `boundingRect()` must `prepareGeometryChange()` or Qt leaves a stale "ghost". See ADR-028 and §11.4 (#218/#219). Sizing precedence (footprint vs. spacing override vs. DB `max_spread_cm`) likewise has one home: the Qt-free `core/plant_sizing.py` resolver.

### 8.9.9 A native window inside the layout — nothing overlays it (Phase 17 L1.3)

The 3D view is a `QQuickView` in `QWidget.createWindowContainer` (ADR-048): a NATIVE child
window. The patterns above — a child widget parented to the view and raised — do not apply to
it:

- **A sibling or child widget does not paint over a native window.** Raised or not, it is drawn
  underneath. A control or a notice for the 3D view goes ABOVE the view (the pane's strip),
  BESIDE it, or IN ITS PLACE (a message page in a stacked widget) — `ui/view3d/workspace.py`,
  §8.29.3.
- **Its input does not reach the widget that embeds it.** Mouse, wheel and key events go to the
  native window; an event filter installed on that window sees them
  (`Quick3DHost.install_event_filter`). Qt's shortcut map still works across it (measured:
  Ctrl+Z, Alt+1 with the keyboard in the 3D window) as long as the filter passes on the keys it
  does not use.
- **Tests read the 3D view back through the host** (`host.grab()`, in a child process on a real
  platform), never through `QWidget.grab()` of the workspace: a widget grab renders widgets, and
  the 3D view is not one.
- **The top-level window stays a raster window** (`surfaceType() == RasterSurface`, asserted in
  the render tier): embedding the container did not switch the main window to a composited
  path, and a 2D pan step costs the same with the view beside it (×1.04).
- The floating mode switch of the workspace follows §8.9.1 to §8.9.3 — but it is parented to the
  WORKSPACE and floats over the canvas only; in 3D mode it moves into the pane's strip.

### 8.9.10 Selection transparency preserves interactive handles (#522)

`SelectTool` lets Qt deliver presses on `DRAG_HANDLE_TYPES` before applying its
Shift selection toggle. A locked item, badge or label can be transparent to
selection; a resize, rotation, vertex, corner, midpoint or curve-control handle
must receive the press so Qt establishes the mouse grab. The handle tuple lives
in `ui/canvas/items/resize_handle.py` and is shared with `CanvasView`'s dropped-grab
recovery. `test_shift_drag_handle_does_not_select_the_item_behind` drives viewport
press, move and release above a selectable background and checks the grab,
geometry change and single-step undo at 0, 37 and 143 degrees.

### 8.9.11 Dense vertex-edit overlays are a view concern (#551)

A saved polygon may carry up to 16 384 vertices; creating four scene items per
vertex (handle, midpoint handle, coordinate label, edge-length label) puts about
65 000 items into the scene and re-creates them on every zoom. Above
`MAX_ANNOTATED_VERTICES = 24` the model keeps every vertex and the overlay is
sampled: visible handles are spaced by `DENSE_HANDLE_SPACING_PX = 24` viewport
pixels up to `MAX_DENSE_VERTEX_HANDLES = 128`, coordinate and edge-length text
moves into handle tooltips, and only edges long enough on screen get a midpoint.
`CanvasView._apply_transform` and `scrollContentsBy` ask selected items to
re-sample; a handle that is currently being dragged is never removed.
The saved geometry is never changed by this: the tests compare the polygon
before and after entering, zooming and leaving edit mode.

**A pan inside the sampled region does not re-sample (#594).** The sample is
taken over the viewport grown by `DENSE_HANDLE_SPACING_PX` (24 viewport pixels) —
the same region `_dense_overlay_indices` tests candidates in. While the new
viewport stays inside that scene region and the item has not moved, every
now-visible vertex was a candidate and the chosen indices keep their pairwise
screen spacing under translation. A zoom, a pose/geometry change, or a pan that
leaves the region samples again. Measured on a 16 384-vertex polygon (the
loader's cap): ~98 ms per forced re-sample, 0.01 ms when the cached sample is
reused; the pin is a call count on `_dense_overlay_indices`, not a timer.
`_remember_dense_sample` / `_dense_sample_covers_view` in
`ui/canvas/items/resize_handle.py`.

### 8.9.12 Touch gestures — pinch zoom and two-finger pan (#321)

The canvas is a `QGraphicsView`, so gestures belong to its **viewport**: with the
preference on, `CanvasView.set_touch_gestures_enabled` calls
`viewport().grabGesture(Qt.GestureType.PinchGesture)` and installs the view as the
viewport's event filter; off ungrabs it and removes the filter.

**Use Qt's recognizer, not a hand-written touch state machine.** The first cut read
`QTouchEvent`s itself and needed two points in `TouchBegin` — which Qt never sends:
the first finger is one `TouchBegin`, the second arrives in a `TouchUpdate`, so the
gesture could not start. `QPinchGesture`'s recognizer owns exactly that arbitration:
it starts only when a second finger is down, so a single-finger tap or drag is
never claimed and keeps arriving as the synthesised mouse event every tool already
handles. It also reports the fingers' **centre** and a **cumulative**
`totalScaleFactor` for the whole gesture.

`eventFilter` routes `QEvent.Type.Gesture` to `_gesture`, which keeps the last
cumulative scale and centre and, per update, applies the ratio to `_zoom_at` and
the centre's movement to `_pan_by`. **Pan first, then zoom about the new centre** —
the other order leaves a `(1 − ratio) × delta` drift when a pinch also moves. The
gesture's `Finished`/`Canceled` state (and disabling the setting) forgets the pair,
so the next gesture starts from its own values.

**The gesture centre is global; map it once.** Qt's recognizer averages the two
touches' `globalPosition` (`qstandardgestures.cpp`), so `QPinchGesture.centerPoint`
is a *screen* point, not a viewport one. `_viewport_point` is the one conversion
(`viewport().mapFromGlobal(...)`), used by both the started and updated branches.
Tests feed `viewport().mapToGlobal(local)` and one of them moves the window off the
origin: with the window at (0, 0) the two are equal and the bug is invisible.

**A pinch must not drag what the first finger touched.** Qt synthesises a mouse
press for the first touch point before the second finger can start the gesture,
and nothing in the recognizer stops that press's stream. `eventFilter` remembers
that press; on `GestureStarted` `_cancel_touch_press` puts back a move the press
had begun (item, constraint-propagated and child positions) so its release pushes
no undo step, calls the active tool's own `cancel()` (a half-made shape or a
selection box is discarded), sends the press's release **at the point it was made**,
and restores a selection the press had cleared on empty canvas. The item under the
first finger may still be selected, as a tap selects it. One exception is stated
rather than hidden: a **resize/rotate/vertex handle** being dragged is finalized by
that release as a normal one-step edit; a pinch does not un-resize it.

**Never duplicate the transform math.** The wheel and the pinch both call
`_zoom_at(anchor, factor)`, and the middle mouse button and the two-finger pan both
call `_pan_by(delta)`. `_zoom_at` is the old wheel body (clamp, `_apply_transform`,
`zoom_changed`, then compensate the scrollbars so the scene point under the anchor
stays within a pixel) with two stated differences: a zoom a limit did not change
returns before re-applying or re-emitting, and the integer scrollbar step rounds
rather than truncates. `_pan_by` is the old middle-mouse body (`centerOn` from two
`mapToScene` points, so the Y-flip and any zoom are handled and the minimap, which
listens to the scrollbars, follows), its second point rounded rather than truncated.
A second copy of either would drift the moment one of them gains a clamp or a
signal — the #326 rule.

Trackpad pinch is not a touch gesture: it arrives as
`QEvent.Type.NativeGesture` (`Qt.NativeGestureType.ZoomNativeGesture`), also
delivered to the viewport, and `_native_gesture` maps `1 + event.value()` onto
the same `_zoom_at`.

**Testing.** PyQt6 can construct `QPinchGesture` and `QGestureEvent`, and a
`QPinchGesture` subclass can override the read-only `state()`, so
`tests/integration/test_touch_gestures.py` drives the real `eventFilter` with
synthetic started/updated/finished gestures (zoom ×2 anchored within 1 px, both
clamps, pure pan, a combined pan+pinch within 2 px, the press released at its own
point, a dragged item put back with no undo step, a selection restored, a handle
drag keeping its anchored corner and exactly one resize step, finishing and
re-adopting, and the setting off). A real touchscreen's **delivery** is still the
owner's manual test; a headless process cannot produce one.

## 8.10 Integration Test Policy

**Worker responsiveness.** Control an in-flight interval instead of counting timer
ticks over an uncontrolled computation duration. Hold the real worker at an Event,
assert GUI heartbeat delivery and a different execution thread while the request
is still pending, then release and verify the real result. Always release in failure
cleanup. `test_explicit_worker_keeps_gui_responsive` preserves its three-tick assertion,
10 ms timer interval and 30-second result timeout; its synchronous-worker negative
control fails. See §11.4 (PR #490).

**Every user story (US) must ship with at least one end-to-end integration test. No merge without it. No exceptions.**

### Rationale

Unit tests and widget tests protect individual components but cannot catch regressions in the interaction between tools, canvas, and scene — the most failure-prone area of the app. Integration tests lock in observed behavior so that refactoring and feature additions don't silently break existing workflows.

### Test layer contract (AUD-018)

The test battery is partitioned into four distinct layers:

1. **`tests/unit/` (Unit Layer)**: Fast, deterministic unit tests verifying isolated models, geometry calculations, algorithms, and services without UI dependencies or full-application initialization.
2. **`tests/ui/` (UI Component Layer)**: Tests exercising individual UI widgets, dialogs, and collapsible panels in isolation. `tests/ui/test_main_window.py` is the designated smoke test for top-level menu bar actions, status bar feeds, and preview mode switching.
3. **`tests/integration/` (Integration Layer)**: Mandatory multi-component end-to-end workflows exercising tool gestures, canvas interactions, command/undo chains, file persistence, and 3D pipelines.
4. **`tests/perf/` (Performance Tier)**: Timing-sensitive performance benchmarks and memory/nfr budget tests deselected by default and run separately under `pytest tests/ -m perf -n 0`.

All integration tests live in `tests/integration/`. Shared fixtures are in `tests/integration/conftest.py`.

### Per-test timeout (hang guard)

Every test runs under `pytest-timeout` (`timeout = 180` in `pyproject.toml`; dev dependency). A hung full-app test therefore fails loudly instead of silently freezing the battery (§11.4, 2026-08-17). If a legitimate test needs longer, mark it `@pytest.mark.timeout(N)` with a comment saying why — do not raise the global value.

### Test isolation: the user's data directory and the locations Qt hands out

A test process must not read or write anything the user owns — **and neither may it read
another tool's files in the user's home**: an AI client's config holds credentials. Four things
are redirected, all in `tests/conftest.py` at its **import time** — module scope, not a
fixture. pytest imports the root conftest before it collects any test module, so a store that is
built while a module is being *imported* already lands in the test location; a fixture runs
after collection and cannot cover that. (The settings store is the first; §8.8 is its
specification.)

Process isolation does not reset custom-library contents between tests in one
worker. A bundled-catalog search test must supply an empty custom-library stub,
as `test_permaculture_search.py` and `test_plant_search_zero_results.py` do. Keep
the real bundled database, filtering and dialog/provider wiring. The line-package
CI run exposed a two-result assertion failure; priming a custom apple reproduces
it on unchanged master. The original CI writer remains unconfirmed.

| What | Production location | How the suite redirects it |
| ---- | ------------------- | -------------------------- |
| Settings (`QSettings`) | organisation / application of `app.settings` | the two names are rebound to a per-process test key (§8.8, ADR-041) |
| The app-data directory, `services.plant_library.get_app_data_dir()`: custom plants, plant lists, seed inventory, companion rules, smart symbols, weather cache | `%APPDATA%/OpenGardenPlanner` (Windows), `$XDG_DATA_HOME/OpenGardenPlanner` or `~/.local/share/…` (Linux), `~/Library/Application Support/…` (macOS) | `APPDATA` and `XDG_DATA_HOME` are set to a directory of this process, `TEST_DATA_ROOT` (a `tempfile.mkdtemp` named with the pid), removed by `atexit` |
| What the app asks `QStandardPaths.writableLocation` for: `crash.log` and `app.log` (AppDataLocation), the companion, climate and thumbnail caches (AppLocalDataLocation), the default project folder under Documents — which `app.paths.get_projects_dir()` creates | the user's profile, named after the Qt application | the Python-level function is replaced for five locations (`REDIRECTED_QT_LOCATIONS`) and answers with a path under `TEST_DATA_ROOT` — the path only: like Qt it creates nothing, so a writer that forgot its `mkdir` fails here as it would on a first run; every other location is passed through |
| What a LIBRARY keeps for the user. ezdxf 1.4.3 (read in the installed package): it loads `ezdxf.ini` when it is imported, and builds **and writes** a font index, `font_manager_cache.json`, when that is missing | `$XDG_CONFIG_HOME/ezdxf` or `~/.config/ezdxf`; `$XDG_CACHE_HOME/ezdxf` or `~/.cache/ezdxf` — on every platform | `XDG_CONFIG_HOME` and `XDG_CACHE_HOME` are set to folders under `TEST_DATA_ROOT`, on every platform (on Linux that also moves Qt's own settings and cache folders and the AI clients' XDG paths into the test root) |

- **The environment is the whole mechanism for the app-data directory** on Windows and Linux:
  `get_app_data_dir()` reads the variable on every call, so no production override exists or is
  needed, and a **child process** a test starts (a script, the app itself) inherits the
  redirection. That is why it is not a patched function.
- **macOS reads no variable.** There `conftest._rebind_get_app_data_dir` replaces the function
  itself, in the defining module and in every module that bound the name with `from … import`.
  No Mac runs this suite (CI is Linux and Windows): the replacement is exercised by hand in a
  test, the `sys.platform == "darwin"` condition is not. A child process on macOS is not covered.
- **Qt's locations cannot be moved by the environment on Windows** (Qt asks the shell for the
  folders). Hence the Python-level replacement; a test that needs another answer monkeypatches
  `QStandardPaths.writableLocation` as before, and gets the suite's version back afterwards.
  What Qt itself writes from C++ — its shader and QML disk caches — still goes to the folder Qt
  derives from the application name (`pytest-qt-qapp` in a test process): not the user's app
  folder, but not under `TEST_DATA_ROOT` either. A child process is not covered: it does not
  import conftest.
- **Not redirected, by decision:** the temp directory (`tempfile.gettempdir()`), which the
  autosave of an untitled plan and the stylesheet's two arrow images use. Redirecting it would
  move pytest's own `tmp_path` and every library's scratch space. A test that lets an untitled
  plan autosave must sandbox it itself (`tests/integration/test_dynamic_input_overlay.py` shows
  how) — otherwise the real app offers that file for recovery at its next start.
- **Per process, not per test.** Every test of one run shares the redirected directories, as the
  whole suite used to share the real ones. A test that needs an empty library builds its own
  store on `tmp_path` (`PlantListStore(storage_path=…)`) or resets the singleton.
- **`Path.home()` is NOT redirected by the suite, so a test that makes code look there patches
  it.** `services.ai_client_onboarding.detect_clients()` asks every client in its registry, and
  most of their configs hang off the home directory: one test that redirected `APPDATA` for the
  client it was about opened the developer's real `~/.claude.json`, `~/.codex/config.toml`,
  `~/.config/opencode/opencode.jsonc` and `~/.gemini/config/mcp_config.json` (review of L1.1,
  2026-10-11). `tests/unit/test_ai_client_onboarding.py` now gives every test of the module a
  home of its own (an autouse fixture: `Path.home` patched, no client CLI on `PATH`), and the
  test asserts where each config was looked up. The rule for a new test: when the code under
  test resolves `Path.home()`, `~` or a client's config path, the test owns that path.

**A script is not a test: it isolates itself.** A script under `scripts/` that imports the app
runs outside pytest, where none of the above applies. There the settings are the user's own — on
Windows a registry key that no environment variable moves — and `ProjectManager.save()` and
`.load()` end with `add_recent_file`: a generator that writes a fixture through the real
serializer, or a probe that loads one, records it in the user's Recent Files (found 2026-10-11: a
developer's whole list had been replaced by fixture paths). `scripts/script_isolation.py` is the
one place for it, and a script calls it in two steps: `isolate_profile()` under
`if __name__ == "__main__":` **above the first import of the app** (the profile variables —
`USERPROFILE`, `HOME`, `APPDATA`, `LOCALAPPDATA`, the three `XDG_*` — to a temporary directory
of the process), and `isolate()` as **the first statement of `main()`** (that; the two
settings names rebound to a key of the process, cleared at exit; and the stand-in for
`QStandardPaths.writableLocation` — on Windows the variables move `AppDataLocation` and
`DocumentsLocation` but NOT `AppLocalDataLocation` or `CacheLocation`, where the companion,
climate and thumbnail caches live: Qt asks the shell). That stand-in is ONE function,
`script_isolation.redirect_qt_locations`: `tests/conftest.py` loads `script_isolation` and
installs the same one for the suite. Not at import: tests import the fixture generators into
the pytest process, and a second redirection there would take its test key away. **A probe
outside `scripts/`** - in a scratchpad or temp directory, an agent's included - is not read by
the gate below and calls the helper itself, with the repository's `scripts/` on `sys.path`; one
that did not switched off the owner's Welcome dialog (PF-TST-27).

**Every script is read, not a list of them kept.** `tests/integration/test_script_isolation.py`
parses every file under `scripts/`: one that imports the app or builds a Qt application either
calls `script_isolation.isolate()` — with `isolate_profile()` above its first app import and
`isolate()` first in `main()` — or stands on the test's `NOT_ISOLATED` list **with the reason**
(eight today: the isolation itself, a spike benchmark with a helper of its own, three developer
tools that are meant to run in the real profile, three that build no store). A new script that
reaches the app fails the test until it does one or the other. The three that isolate
themselves — `make_bench_plans.py` (until this story it rebound the names to a standing key
nothing cleared, and left the profile alone), `make_scene3d_edge_plan.py`,
`measure_region_work.py` — are each run **as a script, in a child process**: every settings
store the child builds, where its profile variables and Qt's five locations point when it ends,
and that nothing — not a file, not a folder — appeared in the profile it was started with. The
child is handed a decoy pair in place of the production names, so a script that failed to
isolate itself would write there and not into anybody's settings.
`scripts/mutation_check_scene3d.py` imports nothing of the app (its children are pytest). A
probe that is not committed has no such test: write it as a pytest test, or give it the same
two calls.

**No test starts another tool.** `detect_clients()` probes a client CLI it finds on `PATH` by
running it. `tests/unit/test_ai_client_onboarding.py` puts no CLI on `PATH` by default and makes
the module's `subprocess.run` raise; a test that plays a CLI replaces it, and the one that only
needs a CLI to be *found* stubs `cli_supported_flags` (it used to stub `which` to
`/usr/local/bin/claude` for every client and let the probe run whatever was there).

Pinned by `tests/integration/test_app_data_isolation.py`: the four variables are assigned at
conftest module scope before the first import of the app (an AST check, the counterpart of
`TestTheRedirectionMechanismItself` for the settings); the directory resolves under
`TEST_DATA_ROOT` and not where it pointed before; a child process inherits it (not asserted on
macOS, where no variable redirects the folder and the child would create the real one); asking
for a Qt location creates nothing and every writer of the app makes its own folder; ezdxf's own
answer for its two folders lies under the test root; the root is gone
when the interpreter has exited; and — end to end — building the whole `GardenPlannerApp`,
running the plant database panel's save path and the plant-list store opens, creates, renames
and lists **nothing** under the place the directory used to be. That last test never touches
the real directory, not even to read it: it computes where it was from what the environment said
before the redirection (`conftest.PRODUCTION_DATA_ENV`) and watches the process's file access
through a `sys.addaudithook` hook (inert outside the test: an audit hook cannot be removed
again). A positive control points the variable at a stand-in directory and shows that the save
is seen there.

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

**The startup Welcome dialog.** The suite silences it for every test, because its `exec()` is modal (PF-TST-11). The session fixture yields the real method, and `tests/integration/test_startup_welcome.py` puts it back for its own tests. Three things are stood in for there: `WelcomeDialog.exec` records instead of blocking (another modal - a Python-level `exec` or a static `QMessageBox` helper - fails the test), the recovery check, and the window's handlers for a picked plan, New and Open. So the startup timer, the settings read, the recent list and the dialog's wiring to the window run as in the product, not the opening of a plan. A spy marks the end of each window's `_startup_sequence`, so no assertion depends on the timer's length (PF-TST-25).

### Coordinate system reminder

> **Framing note.** The "Y-down / (0,0) top-left" label below is Qt's *abstract*
> convention for the raw scene numbers, kept here for test-authoring mechanics (a
> tool test passes raw `scene_pos` numbers and the compass doesn't matter). OGP's
> view applies `scale(zoom, -zoom)`, so those *same* raw coordinates render
> **Y-up**: a larger scene y is visually higher = **north** (§11.4 "Canvas Y-axis
> flip" is the operative rule). That is why the Agent API — which reports the
> identical raw scene y — describes the frame as "origin bottom-left, +y north."
> Both statements are true of the same numbers; they differ only in whether they
> name Qt's storage convention or the on-screen compass.

- **Scene coordinates** (Y-down abstract convention, what tools receive): `(0, 0)` is top-left
- **Canvas coordinates** (Y-up, what the user sees): `(0, 0)` is bottom-left, +y north
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

**Fonts on the dev box (PF-TST-26, #562/#573).** On Windows the `offscreen` platform has no font database: Qt falls back to a box engine in which every glyph is as wide as the pixel size and every advance is a whole number (Verdana 9 pt "Today": 60 px, really 34–37 px). A width, a row count or a rounding claim measured there says nothing about real fonts. The suite now registers `verdana.ttf`, `arial.ttf` and `segoeui.ttf` from `%WINDIR%/Fonts` once in the session fixture `tests/conftest.py::ui_font_family`, and makes Verdana 10 the application font when the platform's database is empty. `tests/unit/test_test_font_contract.py` fails if either the chosen family or the application font resolves to the box engine. Measured: `tests/integration/test_plan_sun_controls.py` went from 20 failed / 55 passed / 3 skipped to **78 passed in 76.9 s** on the Windows dev box; Linux CI already had real fonts. `test_plan_timeline.py` no longer registers `arial.ttf` inside one test and leaves it in the process-global database; the session fixture owns it. For real font metrics without a window on screen, `minimal:enable_fonts` remains the manual alternative (`tests/conftest.py` only sets `offscreen` as a default):

```bash
QT_QPA_PLATFORM="minimal:enable_fonts" venv/Scripts/python.exe -m pytest tests/integration/test_plan_sun_controls.py -n 0
```

Fractional advances, which 125 % display scaling and unhinted fonts produce, can be forced in a test at scale 1 with a fractional point size and `QFont.HintingPreference.PreferNoHinting`.

### Render tier (opt-in, Phase 17)

The `offscreen` platform plugin selects Qt Quick's *software* scene graph, which renders no 3D at all — an empty frame, not a wrong one. Tests that must see a real Qt Quick 3D frame therefore form an opt-in **render tier**, skipped unless `OGP_RENDER3D=1` and a display are present:

```bash
OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 \
  xvfb-run -a -s "-screen 0 1920x1080x24" \
  venv/bin/python -m pytest tests/integration/test_quick3d_render.py -n 0
```

On Linux the tier forces `xcb` + OpenGL and is skipped without `DISPLAY` (Mesa llvmpipe in a container needs `libegl1` and `libxcb-cursor0`); on Windows it renders with Direct3D 11 — on the GPU, or on WARP with `QSG_RHI_PREFER_SOFTWARE_RENDERER=1`. CI's `render3d` job (§7.4, since L1.2) runs the engine package's render files on both. The render files are `tests/integration/test_quick3d_*.py`, `test_view3d_*_render.py` and `tests/unit/test_render_beauty_board.py`; until L1.10 the L0 spike's `test_spike_q3d_render.py` was the tier's only file. The assertions are about **meaning, never pixel-exact goldens**: shadow-map footprint vs the analytic shadow (IoU ≥ 0.85), north-up ground, the sky's sun at the solar azimuth, picks against a CPU oracle (`core/scene3d/pick_oracle.py`), a clean exit while animating. Headless render tooling writes its own timestamped log and per-phase metrics and arms a watchdog, because a frozen GUI exe has no stdout (PF-E3D-04).

### 8.10.1 Gating our own documentation's shell commands

`tests/unit/test_gate_commands.py` is a static guard over the **commands our
documentation tells people to run** — a category distinct from both unit and
integration tests, and added after a self-inflicted defect worth recording.

The frozen-exe `--selftest` gate was written into several documents at once and
was wrong twice in two commits: first as a naked call PowerShell does not wait
on (returns in ~6 ms with an empty exit code — the gate passes unconditionally),
then with the outer string double-quoted so **bash** expanded `$p` before
PowerShell saw it (`= Start-Process …; exit .ExitCode` — the gate fails
unconditionally, and never launches the exe). Four review rounds used the word
"verified" before anyone executed it.

**What the guard does.** Two rules. **(1)** The command literal may live only in
`SANCTIONED_HOMES` — the canonical definition (`ogp-change-control` §2.8), its
mechanics (`ogp-build-and-run`) and the `CLAUDE.md`/`AGENTS.md` Quick Reference;
every other document must **cite §2.8 by name**. **(2)** Wherever it does appear,
the command must actually work: no `$`/backtick construct bash would expand
first, and a shape (`$p = Start-Process … -Wait -PassThru … exit $p.ExitCode`)
that makes the gate capable of failing.

Rule 1 exists because the first version of this guard did the opposite. Told that
eight documents prescribed a weaker gate, it copied the corrected command into
ten more and policed eighteen copies — in a change whose stated thesis is that a
second copy of a gate list is how a gate goes missing.

**How to test this pattern.** Three rules, each bought with a failure:

1. **Model the shell, not the tokens.** The first implementation used
   `shlex.split(posix=True)` and passed on the known-broken line — `shlex` models
   quoting but not `$`-expansion.
2. **Cover substitution, not just `$NAME`.** The second version was bypassed with
   PowerShell's `$?` idiom, where bash substitutes its own exit status and
   PowerShell then evaluates a constant. `$(…)`, backticks and the special
   parameters all belong in the model.
3. **Pin the teeth against the real defects.** The guard carries the literal
   shipped-broken lines as test cases, so a later simplification cannot quietly
   regress it to a version that passed on them.

Verify a guard of this kind by reintroducing the defect and watching it go red;
a guard that has never been observed failing is an assertion, not a test.

**Documentation identifiers are gated like code.** `tests/unit/test_skill_citations.py`
(`scripts/check_skill_citations.py`, issue #336) resolves every `§N.M`/`section N.M`,
`ADR-0NN`, `FR-*`, and `#NNN` citation in the `SKILL.md` files (both `.claude/skills/`
and `.agents/skills/`) plus `CLAUDE.md`/`AGENTS.md` against the real headings, ADR
index, FR index, and a committed GitHub snapshot (`tests/data/issue_registry.json`,
refreshed via `scripts/refresh_issue_registry.py`) — plus every `` `file.py:line` ``
citation that is actually spelled in the gated form: `` `path.py:N` `` immediately
followed on the same line by a backtick-quoted symbol, e.g. `` `core/object_types.py:671`
`is_bed_type` ``. **A `file.py:line` citation with no trailing symbol is rejected
outright** — an earlier version of this gate made the symbol optional and fell back
to a line-count-only check, which is how that same citation, then wrong by 76 lines
(`core/object_types.py:595/608/622`), sat undetected even after the gate shipped (see
§11.4). A citation spelled out in prose, or as a markdown link (`` [text](path.py#L123) ``),
is invisible to this gate entirely — the same blind spot the i18n gate has for a
string that never reaches `tr()`; normalize a citation into the gated form to bring
it under the gate. It resolves *identifiers*, not *claims* — a citation only has to
point at something that still exists, tolerantly (a `file.py:line` citation passes
if its named symbol, plus any string literal alongside it, is found within 20 lines
of the cited line — small enough to catch every drift incident measured so far,
generous enough that trivial churn doesn't cry wolf). It is **not** a check on how
*selective* the named symbol is: a citation naming a short, common identifier in a
large file (e.g. `execute` in a 2800-line command module) still resolves against a
large fraction of that file's possible line numbers — real but weak protection,
tracked as a named residual rather than a false "resolved" claim (§11.4). §11.4 also
records the rot rate that motivated the gate.

### 8.10.2 Developer quality-gate integration tests

The CI/release CLIs are tested through real subprocesses in temporary repository fixtures
(`tests/integration/test_ci_quality_workflows.py`). The workflows pin check/pass/regression/error
exit codes, read-only checks, version-sync dry runs and repeated application, and unchanged
third-party lock records. Remote GitHub responses are supplied as fixtures; deliberately
failing merge tests belong on a temporary validation base, never master.

### A5 numerical and presentation evidence (#457)

`test_constraint_solver_invariants.py` measures geometry independently of solver
flags: both symmetry axes, signed axis distances, nonzero anchor offsets, coupled
residuals, rigid/deformable pins, incompatible fixed systems, feasible projection,
trial cleanup and exact conflicting IDs. The all-pinned false-convergence regressions
failed before the fix. No iteration count or internal damping constant is pinned.
`test_constraint_descriptors.py` covers every enum with independent English text,
icons and status dots, then installs the compiled German translator and checks the
rendered strings. `test_constraint_presentation_workflow.py` drives a registered
tool and real application panel selection/deletion/undo/redo wiring.
The German workflow also verifies unnamed endpoint text and tooltips, preserving
explicit user names. `test_constraints_panel.py` checks all 52 `ObjectType` labels
against the German catalog; this catches absent entries as well as untranslated
fallbacks. Compare-overlay plant labels share the canonical display-name helper.

`scripts/replay_constraint_mutations.py` uses temporary import overlays and fresh
pytest processes. `--source-ref` replays both solver modules from an explicit revision;
`--selection baseline` excludes the A5 tests. An unmutated control must pass first.
Failures, survivors, invalid runs and timeouts remain distinct; a timeout is not a
killed mutant. The committed A5 evidence records the eight exact substitutions,
source hashes and relevant unit/integration/UI selection. This sampled result is not
a full mutation score. `--inventory-only` records current type-sensitive if conditions.

Do not stage or commit in the checkout while the full suite is running.
`test_gate_commands.py::TestCheckNoSecrets` briefly stages synthetic canary files
in the real Git index, scans them, then removes them. A simultaneous commit can
capture a canary. Wait for suite completion and inspect the staged diff before
committing; review in a separate worktree keeps its index independent.
Repository-wide lint and secret scans must also wait for these tests to finish,
so transient canary files cannot become unrelated lint or scan failures.

### 8.10.3 Constraint tool characterization (#406)

`tests/constraint_tool_helpers.py` drives real CanvasScene/CanvasView tools in raw scene
coordinates with snapping disabled. The per-tool unit files exercise press, move and release;
registered workflows reuse the integration canvas fixture and real ToolManager/command wiring.
Only modal acceptance and input widgets are controlled. Picking, feasibility, solving and graph
commands are never substituted in successful gestures. Capture Qt points by value (QPointF),
not wrappers into a temporary QPolygonF. Initialize rotations through the item's canonical
rotation method; Qt setRotation alone does not update product rotation bookkeeping.

Pin the constraint type, item IDs, anchor types/indexes and target fields; assert the actual
geometry relation, exactly one history entry, graph/geometry undo and the same constraint ID
on redo. Exercise rejected dialogs, empty/repeated picks, conflicts, cancellation, Escape and
tool switching, with overlays cleared. Matrices include 0/45/215-degree rotations, both symmetry
axes, coincidence on points/edges/circles, rectangle/polygon/polyline edges and equal circle sizes.
Mixed-graph rectangle cases retain compatible center alignment, refuse incompatible edge
lengths/fixed-pin movement, and restore exact geometry on probe errors. A registry drift guard
requires a gesture scenario for every registered constraint tool.

The existing coverage parser reports normalized package-relative per-file line/branch counts.
Optional `file_line_floors` extends the package gate; `core/tools/constraint_tool.py` requires
at least 60% full-suite lines. Compare integer covered/total counts; branch counts are reported
separately without a threshold. Missing files and malformed records fail visibly. Linux
rebaselining preserves explicit file floors (ADR-050 addendum).

### A1 trust-boundary testing (#453)

Failing-first tests pin invalid-number rejection, mislabeled HTML caching and
duplicate installer selection. Integration tests drive the real application document
load and update notification/worker paths with network and process launch controlled.
A loopback HTTP fixture proves byte limits apply after gzip decoding. Linux settings
tests run real QSettings in fresh processes with private XDG directories and controlled
umasks; Windows skips only those platform-specific assertions and pins registry parity.
No test executes an installer or calls a paid map provider. Test-layer evidence must
name the platform and locked interpreter, not imply a Windows chmod mock proves Linux.

### Translation gate integration (#496)

`tests/integration/test_translation_gate.py` invokes the real CLI against an isolated
three-locale project, proves a missing target returns nonzero with useful diagnostics,
and checks input files remain unchanged. It also exercises the real language menu,
saved setting and next-window startup translation for every registered locale.
`tests/unit/test_translation_gate.py` mutates both axes: a new locale missing an old key,
and a new source key missing from some or all catalogs. Equal-size wrong-key catalogs,
invalid values/placeholders, stale binaries and stale source declarations fail.

### Constrained gestures and cross-surface invariants (#485, #443)

A gesture that the solver must follow is tested through the real viewport, not by calling
the release handler: `tests/integration/test_constrained_rotation.py` presses the green
rotation handle with `QTest`, moves it and asserts the partner moved **while the button is
still down**, the relation at scene-space anchors (45°, 215°, a wrap-around angle), exactly
one undo entry, and undo/redo restoring angle **and** partner. An angle returned to its start still records partner edits. A no-op with no geometry changes adds no
entry; a FIXED partner stays pinned and the relation reads red; an inter-object
PARALLEL/PERPENDICULAR still refuses the rotation. Partner-plant and partner-bed cases pin
that a correction which moves a partner also re-decides its membership / carries its
plants, and a full-application variant saves and reloads the completed geometry.

A cross-surface invariant is tested on **every edit path that can break it**, through that
path's real entry point: `tests/integration/test_bed_membership_reconciliation.py` covers a
bed's resize/turn/vertex edit (tested service AND the live-applied drag registration), a
plant moved in/out by the move command, a bed moved over / with its plants, array and mirror
copies, the Properties panel's typed width/height, and the agent's `set_vertex`. Each asserts
both sides of the link (`parent_bed_id` and `child_item_ids`), exactly one undo entry, and
undo/redo symmetry. Re-running the command a production caller builds is not a test of that
caller — the panel and the agent failures #443's review found both passed every direct-command
test.

### 8.10.4 The inner loop, and which run is the gate (#509)

**Current scheduling (#601, 26 October 2026).** Coverage measures two disjoint
non-perf test-ID hash partitions on separate Linux runners and the complete perf
set on a third, serial runner. The required `Coverage` check requires every
producer to succeed, combines all three explicit data files, then enforces the
unchanged floors. Branch tracing remains enabled. `Test` remains uninstrumented
and retains its duration artifact and serial budgets. This costs extra setup and
collection work in exchange for a shorter critical path; it does not claim fewer
runner minutes. See the [investigation and full marker audit](../11-risks-and-technical-debt/audits/2026-10/ci-latency-601.md).

The audit moves 27 deterministic cases out of the serial set (116 → 89): mark
individual elapsed-time tests, not their entire mixed class. The AST guard reuses
one parse and lexical index per module. The documented-figure guard runs each CLI
sweep once and applies both invariants and prose checks to that output, avoiding
process-local caches that duplicate work across xdist workers. The fifty receiver
cycles assert immediate acyclic teardown; one separate cyclic case uses full GC.
`test_ci_coverage_shards.py` exercises real xdist selection and branch merging;
workflow pins reject omitted measurements and masked failures.
`test_perf_marker_guard.py::test_mixed_budget_groups_mark_methods_instead_of_the_class`
pins the marker scope. `test_gate_commands.py::test_coverage_shards_and_merge_are_pinned` and
`test_coverage_topology_pin_rejects_incomplete_measurements` pin complete,
mandatory producer inputs and their failure propagation.
The phenology 300-plant gate keeps 16 ms in uninstrumented runs, including CI.
Under coverage it uses the existing snapshot-budget tracer factor (10×) without
the CI factor, so tracing cannot masquerade as a product frame-budget regression.
`test_phenology.py::test_the_product_budget_stays_16ms_and_only_tracing_gets_an_allowance`
pins both refusal thresholds. #601's audit records the reproduced traced failure.

The timings and fourteen-case counts below are the original **#509 baseline**.

`addopts` carries `-n auto --dist worksteal -m 'not perf'` (ADR-058), so the **default**
run is parallel. Three things follow from that, and each is a trap worth naming.

| Command | What it is | Measured |
|---|---|---|
| `pytest tests/` | the correctness battery, parallel, perf deselected | **156 s** (`-n 8`) |
| `pytest tests/ -m perf -n 0` | the timing-sensitive tests, which never share a runner | **26 s** |
| `pytest tests/unit` | the natural inner loop for a logic-only change | **193 s** serial, **61 s** parallel |

**The perf tests need `-m perf`, and the marker is about the measurement, not the
directory.** `addopts` deselects them so that a plain `pytest tests/` **collects no
perf test at all** — the most likely way to mistakenly believe they ran. They are
wall-clock budgets, and **7 of the 14 carry that marker *outside* `tests/perf/`**, so the
split is by auditing for wall-clock assertions rather than by listing a directory. That
number is worth writing down precisely, because it changes the invocation:

```powershell
pytest tests/ -m perf -n 0     # all 14 — what CI runs
pytest tests/perf -m perf      # only 7, and it PASSES. The worst kind of wrong.
```

A directory-scoped command is the natural mistake here and it fails **silently** — the
gate is green while half of it never ran. `-m perf` is required because `addopts`' own
`-m 'not perf'` otherwise wins and collects nothing at all; `-n 0` is required because
running these across workers is the condition the split exists to prevent.

The audit that produced the split was, twice, incomplete: it read `tests/perf/` and
grepped for `time.`, and missed four unmarked bounds including two classes literally
named `TestPerf`. `tests/unit/test_perf_marker_guard.py` now closes that mechanically —
it walks each module's AST, follows the timing sources (`time.perf_counter`,
`time.monotonic`, `time.process_time`) across calls, and fails the build if a test orders
a measured duration against a bound without the marker. **12 of the 14 assert a duration;
the other two are marked for scenario consistency**, which is the one thing the guard is
documented not to check — it proves a marker is *required* where it fires, not that every
marker present is needed.

Issue #528 extends this to durations stored in class attributes, including local
support modules. Both call-graph closures use lexical function identities (class
and enclosing functions within the module), so `GroundBaker.bake` cannot inherit
`TimedBaker.bake`'s stopwatch. Regression tests keep both classes in the same
module in both definition orders, check the real ground-bake AST with its helper
restored inline, and preserve the ordinary session's non-timing ordering assertions.
The scan at PR #556 finds 40 duration candidates with no missing markers. Static
call resolution does not follow dynamic receivers, instance aliases, inherited
methods or imported helper functions; support-module attribute carriers are a
separate supported path.

**A local perf reading on Windows may be a throttled one (#616).** On the Windows 11 dev box,
power throttling (EcoQoS) can raise a `-m perf -n 0` run's timings about 1.8× partway through
the run, and the run does not recover. G3's two-tile bench_large edit read 7.8 ms throttled
and 4.3 ms with the test process opted out. The four-tile edit read 14.8 ms in two passes
throttled and 8.4 ms in one pass opted out. A sudden per-move jump from about 8 to about
15 ms, with passes going from 1 to 2, is the signal. During PR #613 it was misread as
machine load, and a throttled master run as "master also needs two passes". #616 adds the opt-out to the test process via `tests/conftest.py::pytest_configure`, so local timing runs are protected against EcoQoS throttling (pinned by `tests/unit/test_power_throttling.py`; PF-TST-33). `scripts/measure_ground_edit.py` opts its own process out.



**Small targeted runs are slower than they were.** Worker start-up dominates when there
is nothing to distribute: one 11-test file measured 2.85 s serially against 5.48 s under
`-n auto`. Pass **`-n 0`** for a single file or a handful of tests. The asymmetry is
deliberate (517 s saved on a full run against 2.6 s added to a small one) but it is a
real cost, and `-n 0` is the documented escape rather than something to discover.

**Which run is the gate.** A targeted run is good security during a change; the **full**
correctness battery plus the perf step is the gate before a PR. This is safe in one
direction only, and the direction matters: a targeted run can fail while the full run
passes (a false alarm — harmless), but the dangerous direction would be a targeted run
passing beside a red full run, which is exactly why the full run stays the gate. §11.4
records the precedent for the fix when that happens: request the fixture the test
actually needs rather than inheriting it from a neighbour.

One consequence of parallelism is worth expecting: **a hang presents as a crashed
worker**, not as a clean abort. The `pytest-timeout` guard still applies per test (#448
and the 2026-08-17 stall earn it); xdist kills and restarts the one worker and
continues.


Frozen nonlinear numeric answers need a representable-value bound when replayed
across runtimes. In the F4 master merge, Windows matched 154/160 L0 exposure
samples exactly and six at exactly one binary64 ULP, with production lighting
byte-identical to master. test_scene3d_look permits one math.ulp of the expected
exposure with zero relative tolerance; probe exposure, colours and brightness stay
exact. Never replace such evidence with a broad default relative tolerance.

### 8.10.5 Patterns from the 3D scene pipeline (Phase 17 L1.1)

Patterns `tests/integration/test_footprints_golden.py`, `test_scene3d_snapshot.py`,
`test_scene3d_pipeline.py`, `test_scene3d_edge_plan.py`, `tests/unit/test_scene3d_sync.py` and
`tests/perf/test_scene3d_snapshot_budget.py` established; reuse them where they fit. The last
four were paid for by an independent review that found two interface defects behind a green
suite (ADR-059, "What the first version got wrong").

- **A timing budget is asserted on untraced code.** A budget for pure-Python code cannot be
  asserted under a line tracer: under `pytest --cov=open_garden_planner --cov-branch` — how CI's
  coverage job runs the suite — `snapshot_records` took 78 ms where it took 8.6 ms untraced
  (9×), over its 60 ms budget. (A plain `coverage run` of a probe script had measured 39 ms, so
  measure the way CI runs it.) The budget test detects a tracer (`sys.gettrace()`, or coverage's
  `sys.monitoring` tool on 3.12+) and then asserts only a blow-up tripwire at ten times the
  budget; every untraced run asserts the real one. What a test can pin here is the *logic* — that
  a tracer is detected, and that nothing but a tracer or a CI runner widens the budget — not the
  numbers: a test that asserts `BUDGET == 60` restates a constant and guards nothing. The canvas
  repaint budgets
  (`tests/perf/test_nfr_budgets.py`) have no such rule: run locally under the same tracer they
  read 17–41 ms against their local 16.7 ms and fail (three runs, 2026-10-11); in CI their budget
  is 50 ms.

- **A golden fixture before a move.** When code that many callers depend on is moved or
  re-layered, generate a fixture from the UNCHANGED code first, commit it with a test that passes
  on that code, then move — the fixture's bytes must not change. Store floats as their exact
  `repr` and compare as strings on the platform that generated them; elsewhere require the same
  structure and 1e-9 (the last bit of `math.cos` and of Qt's rotation belongs to the platform's C
  library). Regenerating must be deliberate: an environment variable rewrites the fixture and the
  run **fails**, so it cannot be mistaken for a pass. Pin decoration-dependent inputs explicitly
  (stroke widths, rotation pivots) so a style tweak is not reported as a regression.
- **Incremental == full rebuild.** Anything that applies diffs to keep a second representation in
  step is tested against the trivial implementation: after every step of an edit sequence, the
  incrementally updated state equals the state built from scratch. It needs no oracle and finds
  the bugs a hand-written expected value misses.
- **Fixtures parametrised by applicability, not skips.** A matrix whose cells do not all exist
  (a vertex edit on a circle) gets one fixture per applicable subset (`_stage_fixture`), so the
  report lists exactly the cells that ran. `skipped` stays reserved for the environment.
- **A hover that arrives.** `QGraphicsSceneHoverEvent` cannot be constructed in PyQt6. Drive a
  real one through the view: show it, `centerOn` the *item*, then `QTest.mouseMove` to a point
  30 px away and again onto the target — measured to highlight a selection handle on all five
  shape classes. One move straight onto the target after `centerOn(target)` highlighted the
  handle of a circle but not of an ellipse, rectangle, polygon or polyline (cause not
  identified), and a hover test that does not check would have passed vacuously there. Assert an
  effect of the hover (the handle's highlight brush) before asserting that it changed nothing else.
- **Ask the question the defect would answer wrongly.** A closed fence became a slab over the
  whole garden while "every ring matches the 2D ring", "the mesh validates" and "the top is the
  right height" were all true. Each gate compared a property the wrong solid shared with the
  right one. When a gate guards a *solid*, also measure an extensive quantity — the ground it
  covers (`Record.plan_area_cm2` against the cap area, `verify_builder`'s plan view) — and compare
  it with a number derived another way (a fence's length × its width). And put the awkward shapes
  into a committed plan (`scene3d_edge_cases.ogp`): a gate that runs "over the bench plans" tests
  only what the bench plans contain.
- **A recovery test may use only the interface under test.** The first recovery test called a
  method of the recording double (`RecordingSink.reset()`) before `SceneSync.reset()`, and so
  proved nothing about an engine that has no such method — the real `reset()` left the sink's
  transaction open. Write the fake that fails (`FlakySink`), recover through the protocol alone,
  and compare with a from-scratch run (`assert_recovered`). Then write the fake that *ignores* the
  recovery call and show what catches it (`sink.state() != sync.expected_state()`), so the limit
  of the check is on record.
- **A test's name is a claim.** Three tests promised more than they pinned: one "moving or
  turning" test turned the item *before* taking its baseline, one named for `reset()` never called
  it, one asserted a *lower* bound on an error. Read each new test once asking only "which line
  fails if the named behaviour breaks?"
- **Break the rule and watch the test fail.** `scripts/mutation_check_scene3d.py` applies 180
  single-rule mutations to the pipeline, each against the tests that must notice; its first run
  found a comparison (`Record.same_geometry` on `holes`) no test pinned. It is not in the suite
  (it rewrites source files): run it after changing the pipeline or its tests, and add a mutant
  with every rule.
- **A price list is gated — by hand, on a quiet machine.** `scripts/measure_region_work.py`
  exits 1 when a row of its table costs more than 12 times its price (§8.29.1). The ratio is
  two timings, so the script is not in the suite: run it alone after touching a price, a call
  into the clipper or the cut, and add the FAMILY with every such call — twice the hole in the
  list was a way of asking the clipper that no row measured. What the suite pins is everything
  about it that is not a timing (`tests/integration/test_measure_region_work.py`): the
  verdict, the bound, that `main` returns it, and that each family is what its name says.

### 8.10.6 Patterns from the plant builders (Phase 17 L1.7)

Patterns from `tests/unit/test_plant_art.py`, `tests/unit/test_scene3d_plants.py`,
`tests/integration/test_scene3d_plants.py` and `tests/perf/test_scene3d_plants_budget.py`; the
stories behind them are PF-L3D-01. The first three were there from the start; the rest are what an
independent review found missing behind a green suite.

- **A golden of answers before extracting a rule.** The companion of "a golden fixture before a
  move" for a *function*: before `resolve_sprite` was extracted from the 2D renderer, 1,562 of the
  old resolver's answers were recorded (every key of its map, each in two casings, every bundled
  common and scientific name, the names the gallery sets, junk, and the fallback grid of kinds ×
  categories) and committed alone. The extracted function is then held to the file under every
  way it can be asked. Quirks get pinned on purpose — a rule that users see is not improved inside
  a refactoring.
- **An independent reference by subtraction.** To ask "is this colour the sprite's foliage
  colour?" without painting a mask: render the sprite as shipped and once more with its palette
  replaced by black. Source-over compositing is linear in every layer's colour, so the difference
  of the two images is exactly the ink that depends on the palette; everything drawn from other
  colours cancels. The same trick isolates any one input of a layered drawing. Assert the two
  renders share an alpha channel — then they are the same shapes.
- **Every metric gets a case whose answer is known.** A measuring function is code and can be
  wrong in the flattering direction. `side_silhouette` is asserted to give 1.0 for a plant against
  itself, the hue instrument to *fail* a plant built in another palette
  (`test_the_hue_instrument_tells_palettes_apart`), `verify_builder` to reject a builder that
  reads the transform. Where a gate could pass by construction, add the neighbouring measure the
  gate does not ask for (bounding box → distance from the axis).
- **A known gap is a test, not a sentence in a report.** Where the 3D view could still disagree
  with the plan — a species assigned from the plant database — a test asserted both answers as
  they were. The day the gap was closed (the record now carries the item's own species string)
  that test failed and was rewritten into
  `test_a_species_assigned_from_the_database_is_built_as_the_canvas_draws_it`; until then nobody
  could believe it was closed.
- **A gate the code forces cannot fail: measure before the repair.** The height gate compared
  the mesh's top with the plan's height — after a fit whose last step scales the top onto the
  height. It was green for a squash built 1.6 times too tall and squashed back. Three things make
  such a gate real: (1) the repair step RETURNS what it did (`FitReport`: the builder's own top,
  the scale factors, what was clamped and pressed) and a test bounds it; (2) an independent
  measure of where the thing is — here the height below which 95 % and 99 % of the foliage's
  surface lies (`height_quantiles`), per archetype; (3) the size matrix leaves the diagonal:
  every recipe is also built far wider than tall and far taller than wide, and at its bundled
  small size, whose proportion differs from the mature one. Scaled along its own proportion a
  recipe is seen at one proportion only.
- **The report of a repair is itself tested with a case whose answer is known.**
  `TestFitReport` hands the fit a hand-made plant — 1.3 times too tall, one vertex 1.5 radii out,
  one under the ground — and asserts the report number for number. Without it a report that
  always says "nothing repaired" passes every other test (the mutation check: three such
  mutants were killed by this test alone). The same goes for a repair the builders no longer
  need: since no builder hovers or dips any more, setting a plant down and pressing a vertex onto
  the ground are exercised by this test and by nothing else.
- **"For every X" is tested over every X.** "2D and 3D agree for every plant placed from the
  gallery" was checked for 11 of 86 gallery species and was false for a twelfth. The test now
  takes the gallery's own item list (`build_toolbar_categories`), composes the drag data the way
  the gallery widget does, drops all 100 plants through the real `dropEvent` and compares; a
  second test does the same for all 222 keys of the species map and the strings the rule is odd
  about. When a claim quantifies over a list the code owns, iterate that list — a hand-picked
  sample is a different, weaker claim.
- **With every file shipped, nothing asks about a missing file.** A fall-through for a missing
  resource is dead code in every test that runs against the complete set. Pin it where it lives:
  patch `Path.exists` for one resource (`_MissingFiles` empties the renderer's memos on the way
  in and out) and assert both the answer and what is painted. And keep the OLD implementation,
  statement for statement, in the fixture's generator, so that old and new can be compared under
  conditions the golden never recorded (`scripts/make_sprite_resolution_golden.py
  --differential`).
- **"Calls the shared function" is observed, not read off the source.** Asserting that a
  module's source text contains `resolve_sprite(` proves a string. Substitute the function with
  one that answers something no copy of the rule would (always the palm) and assert that the
  caller returns it.
- **A sample of five is a claim about five.** The no-clones gate compared five fixed ids and
  passed with 0.005 to spare; over other ids a hedge reached 0.984. A gate over a random quantity
  states a distribution: enough ids to have one (twelve per recipe, 66 pairs), bounds on its
  maximum, its 95th percentile and its tail share, and the measured table next to the bounds.
- **The derivation of a constant is a test.** `FOLIAGE_TIP_WEIGHT` was "measured from the
  sprites" by a scratch script. The derivation now runs
  (`test_the_tip_weights_are_measured_from_the_sprites`) and holds the constants to its result;
  three of them moved by 0.03–0.05 when it first did.
- **Timing on a shared machine: counts first, then ratios, then units of work.** A cold build
  that takes 330 ms on a quiet box took 1,200 ms with every core busy — CPU time as much as wall
  time, so the process is slower, not waiting. A millisecond bound is then either too tight for
  the busy hour or meaningless in the quiet one. In order of strength: assert the COUNTS that
  cause the time (shapes built per tick — machine-independent; exact for a first build and a
  cold tick, a roomy bound for a warm one), then a RATIO measured in one process (a warm tick
  costs at most half a cold one; measured 1 : 20), then the time in units of a small reference
  workload timed alongside (`reference_ms`), with a bound of about twice the measured units.
- **A sample's maximum is not a bound: a claim is structural or it is a measurement.** "No
  vertex further than 1.092 canopy radii" was the maximum of 117,000 builds on three
  proportions; one id in 300,000 at a fourth proportion read 1.1006, past the gate the
  requirement stated. Either make the code produce the bound as its LAST operation and test the
  mechanism on input it was not tuned for (500 hostile point clouds handed to the fit), or state
  the number as measured, with its sample, and keep the test as a tripwire well clear of it.
  And sweep the variable the code is keyed on (every proportion step), not a list of sizes that
  happens to land on a quarter of its values.
- **A cache makes "build twice and compare" compare one build with itself.** With the shape
  cache warm, the determinism tests passed with unseeded dice. A test that is about BUILDING
  clears the cache first (`build_cold`), and says so.
- **A cache is tested at its cap, with the access pattern of its user.** Least-recently-used is
  the worst policy for a consumer that asks for the same keys in the same order every tick: at
  capacity + 1 the hit rate goes from 100 % to 0. Stand a test AT the cap, one past it and far
  past it, counting builds per tick.
- **Break the rule and watch the test fail.** `scripts/mutation_check_plant_art.py` applies
  94 single-rule breaks to a temporary copy of the tree and runs the tests that must
  notice. Twice it found a rule no test pinned — the placeholder's round rim, and the fit's
  set-down once no builder hovered any more. A kill is pytest's exit code 1 AND a named FAILED
  test — never "any non-zero exit": a renamed test id (exit 4) or a collection error (exit 2) is
  a run that did not test the mutant. `tests/unit/test_plant_art_mutation_script.py` pins that
  rule and, on every suite run, that each mutant's pattern still matches its file exactly once
  and each test it names still exists (as `test_scene3d_mutation_script.py` does for the scene
  contract's script).
- **A script that uses the app outside pytest uses the developer's real stores — isolate it, and
  test that with a child process that cannot do harm.** `tests/conftest.py` redirects the
  settings and the app-data directory for the SUITE; a script run by hand gets neither.
  `scripts/measure_plant_art_3d.py scrub` loads plans, `ProjectManager.load` ends with
  `add_recent_file`, and on Windows the settings are the registry, which no environment variable
  redirects (PF-L3D-01). The script now isolates itself at import, before any app import (settings
  names rebound to a per-process test key, profile variables to a temporary directory, both
  undone at exit; a process that is isolated already is left alone). The test runs it in a child
  process without conftest and asserts where the write LANDED — and its driver refuses to load a
  plan unless the settings names are a test key, so a broken isolation fails the test instead of
  writing the developer's recent files. What decides whether a script needs this is measured,
  not guessed: under isolation, list the settings keys and the files in the profile after each
  step (the six other commands of that script, the golden generator and the sprite generator
  create no settings object and write nothing).

### 8.10.7 Patterns from the built world and base stacking (Phase 17 L1.6)

Established by `tests/integration/test_shadow_caster_golden.py`,
`tests/unit/test_shadow_caster_base.py`, `tests/unit/test_scene3d_builders.py` and
`tests/integration/test_scene3d_built_world.py`.

- **A golden before a behaviour change, plus an independent oracle of who changes.** §8.10.5's
  golden pins a refactor (nothing may change). When behaviour changes for ONE class of input, the
  golden pins everything else: generate it from the unchanged code, and store two things per
  scene — the result as it was, and the result of only the inputs the change will NOT touch. The
  test then proves (a) with the change switched off the old result returns, (b) the untouched
  inputs still give the second result, (c) the touched inputs are exactly the expected ones. Which
  inputs are "untouched" is decided in the test by a re-derivation that does not call the new code
  (`_walk` in the golden test): it found that only 22 of bench_small's 45 parented plants stand
  on raised soil — the first draft of the assertion said 45.
- **A geometric claim gets an oracle that shares no code with it.** The swept shadow of a raised
  caster is checked point by point against a ray test (is `q − t·d` inside the footprint for some
  `t` in the height interval?) that knows nothing of polygons, sweeps or the integer grid — next
  to the algebraic identity (the raised shadow is the ground shadow translated). The identity
  alone would pass a wrong formula that is self-consistent.
- **The same oracle catches a region taken as a list of solids.** A caster's rings are one REGION
  (#444): a closed fence's stroke is an outer ring and a hole, and a self-crossing outline is two
  lobes. The repair that makes them simple rings (a zero-width bridge, `SimplifyPolygons`) is
  judged by the same ray oracle on a grid of cells — the polygon answer and "is some point between
  it and the sun inside the region" must agree cell for cell, and the swept-rings answer must not.
  That is what makes "the slit costs no ground" a measurement. It does not adjudicate the 38 cm²
  between the issue's four-rectangle reference and the offset ring (its cells are 400 cm²);
  the ring's own printed area, 818,062.1 against the rectangles' 818,100, does.
  (`tests/integration/test_shadow_region.py`).
- **A builder matrix turns the local geometry, not only the item.** A builder never sees an
  item's rotation (it is the transform's), so "parametrise over rotation" has to mean the
  footprint and the path *inside the local frame*. Doing that found a shed whose ridge lay askew
  to its walls (the bounding box of a turned polygon) and a ridge tile that overshot the eaves
  where the ridge met them at an angle.
- **Assert containment, not only extremes.** "The top is the height" and "the triangle budget
  holds" passed for both defects above. What failed was "every vertex lies inside the footprint
  grown by the overhang" (`outside_distance`) — a statement about the whole solid.
- **Probe points off the axes of symmetry.** A plan-view "is this point covered" test at the
  centre of a symmetric outline sits exactly on an ear-clipping diagonal and reads "not covered"
  under a lid that covers everything. Use points like (37, 11).
- **Plan-view area as the hole detector.** For anything built along a line, the area of the
  union of its triangles seen from above must be about `length × width`; a slab over the
  enclosed area is two orders of magnitude off. Height, validity and budget all pass on the slab.

Added by the senior review's first round (the same story):

- **A golden that is exact on one platform needs a partner that is exact on all of them.** The
  shadow golden compares bit for bit only where it was generated (win32); the CI test jobs run
  on Linux, where the same file is a "to the grid" gate. The partner is the RELEASED module kept
  as a test oracle (`tests/unit/shadow_geometry_v1_29_10.py`, the same git blob as the tag's
  file — the test checks the blob id): old and new functions run side by side on the machine
  under test and must agree exactly, so "unchanged" is proven wherever the suite runs. Say in
  the test's docstring what each platform enforces; and run the tolerant branch everywhere (it
  is implied by the exact one), or it is dead code on the only machine you can watch.
- **Show that a tolerant comparison can fail.** `test_the_portable_comparison_can_fail` feeds
  the Linux gate a coordinate three grid steps off, a lost vertex, a lost polygon, another path
  element, a changed area and a changed heatmap sample, and one single grid step, which must
  pass. A tolerance nobody has seen refuse anything is a guess.
- **A time budget with a CI factor needs a partner without a clock.** 40 ms ×3 on a runner lets
  a per-vertex Python loop pass. `python_calls` (a `sys.setprofile` hook — it leaves coverage's
  trace hook alone) counts the calls a builder makes: the same number for 5 m and 50 m of fence,
  and a wrapper that touches every vertex is caught by 24,000. Not a dict compared with its own
  literal: that test could not fail.
- **A test named after a behaviour drives the behaviour.** "A bed height change recomputes the
  overlay" used to set `parent_bed_id` and call `recompute_now()`. It now executes a height
  command and a re-parent command, waits out the debounce, reads the overlay's painted tip, and
  ends with a negative control (the wiring disconnected: nothing happens).
- **Pin a known limit with its reason.** Three states in which a plant is in a raised bed and
  not on it are tests that state the expected base AND why — so the fix of the underlying gap
  changes them knowingly instead of "fixing a failing test".
- **Measure a disagreement between two models, commit the measurement.** "The 3D body is wider
  than the 2D footprint" was written from the builders' dimensions. Projecting the meshes onto
  the ground (`scripts/measure_built_world_shadows.py`) showed the opposite for three of five
  fence styles. A table in an ADR needs a script a reader can re-run and a test that fails when
  the table goes stale.
- **A mutation check for each fix — committed, or it is a number nobody can check.** Each rule
  of the review rounds is switched off in the source (the link alone lifts; a 3-tuple is a
  caster; no bevel; an unknown style is a picket fence; a container's soil 2 cm low; a block on
  the first ring only; the link point is the bounding rect's centre again; the parent's shape is its
  bounding box …) and the tests that should notice are run:
  `scripts/mutation_check_built_world.py`, next to the scene contract's
  `mutation_check_scene3d.py`. A mutant counts as KILLED only when pytest exits with code 1 and
  names a failed test — a collection error or a crash is reported as BROKEN, not as a kill. The
  first round quoted its count from a script that lived in a scratch folder. (28 mutants when
  it was committed, 30 since the merge of the contract's second round, 32 since the third
  review round, 33 since the plant builder joined the registry; all killed; `--list` prints the current set.) And a mutation script rots between its runs: a mutant whose text
  has left its file mutates nothing. `tests/unit/test_scene3d_builders_mutation_script.py`
  checks on every suite run that each mutant still matches exactly once and that every test
  file and `-k` word it names exists — it found a stale mutant the day it was written (the
  line under `footprint_of`'s guard had moved).
- **A guard that counts a construct must see every spelling of it.** "The containment test
  exists once" matched `x.contains(y.mapFromScene(p))` written as one expression; the same test
  in two statements passed. The guard now follows a mapped point through local names (and a
  parametrised test feeds it both spellings and three near misses), and states the limit that
  remains: attributes, containers, parameters.
- **Pin which input each decision takes when a refactor claims "identical behaviour".** Five
  inline expressions became two shared functions; swapping the point they used passed all 114
  related tests, because no test had a case where the two candidate points differ. One probe
  where they do (a plant under its warning badge at a bed's edge) and one assertion per
  decision turned the claim from read into tested.
- **No universal sentence next to a gate without a measured number.** The truth-gate row said
  that a 3D shadow ends where the 2D one ends, for every kind; the committed script, asked for
  the reach, printed −270 cm for a house. The reach is now a column of the script, and a test
  scans the docs and skills for the claim.
- **A wait on a count can still race an echo: wait for the echo.** `qtbot.wait(400)` after a
  150 ms debounce is a guess about the machine — but its first replacement,
  `waitUntil(count reached)` then `waitUntil(debounce idle)`, was a race of its own and turned
  CI red (`assert 6 == 1 + 4`, one job of two on the same commit). A recompute sets the
  overlay's path; the scene answers with `changed` one event-loop round LATER; `changed` is wired
  to the debounce. Straight after the recompute the timer is idle and the echo is still on its
  way — "idle" is not "nothing pending" — and an echo delivered late carried an unannounced
  edit into a negative control. What holds: wait for the count, **then for the echo you know is
  coming** (a `scene.changed` delivered since that recompute), then for the debounce the echo
  starts, then assert the exact count (`OverlayWatch.settled` in
  `tests/integration/test_scene3d_base_stacking.py`). And make the race a regression that fails
  EVERYWHERE: run the racing step synchronously, so the event loop cannot hide it —
  `TestTheOverlaysOwnEcho` recomputes by a direct call, then runs the control. With the old
  helper it fails three times out of three on any machine.
- **An assertion on a running timer is a duration in disguise.** The regression above first
  asserted `debounce.isActive()` right after the echo arrived — true only while 150 ms have not
  passed, so a slow machine fails it for no reason. What the test means is what the timer DOES
  (one more recompute, which saw the edit), and the lines after it already said that.
- **"Up to N" needs the worst direction.** "The badge moves the point by up to 1.8 cm" was
  read off one axis; the point moves 1.8 cm in x AND in y, 2.55 cm in all, and against a bed
  edge at 45° the margin is the diagonal. State the per-axis figure and the worst case, and pin
  the worst case (a bed turned by 45°: a plant 2.2 cm inside the edge is outside for the link).
- **A source-reading guard needs a census, not only a pattern.** "An `ItemLookup` is constructed
  only in the two walks" matched `ItemLookup(...)` and so never saw an alias import, `make =
  ItemLookup` or `functools.partial(ItemLookup, items)`; and "the local is not stored" matched
  `x = lookup` / `return lookup` and so missed a list, `.append(lookup)`, `setattr`, a tuple, a
  closure. Turn both around: count EVERY appearance of the identifier and allow the few roles
  that are fine; allow the ONE use of the local that is fine (an argument of a named taker) and
  report every other. Then list what a reading still cannot see (`type(lookup)(…)`).
- **A committed script is outside the suite's isolation: measure what it reaches.** The test
  suite rebinds the settings names; a script run by hand has the owner's. For a script that
  must not need isolation, run it AS DOCUMENTED in a child process with `QSettings` replaced by
  a recorder that refuses (so even a failing run cannot touch the real store), an audit hook on
  `open` / `os.mkdir`, and an empty redirected profile
  (`test_run_as_documented_the_script_reaches_no_settings_no_plan_and_no_app_data`). Watch what
  is constructed and opened, not what is imported: importing the `core` package loads the
  settings module and PyQt6 either way.

### 8.10.8 The 3D render tier (Phase 17 L1.2)

3D cannot be rendered in the default test run: `tests/conftest.py` sets
`QT_QPA_PLATFORM=offscreen`, and under that platform Qt Quick falls back to the software scene
graph, which draws no 3D (`View3D` prints "not based on QRhi … is not going to display anything",
the frame comes back white). So tests that need pixels form an opt-in tier.

**Shape.** Two processes with two jobs:

- a **driver** with a real Qt platform (`tests/integration/quick3d_render_driver.py`) only *does*
  engine things — it drives `SceneSync` → `Quick3DSink` → `Quick3DHost`, saves every frame as a
  PNG and writes raw engine answers (picks, the Models read back from the QML scene, upload
  counters, timings, each offscreen frame's own Qt messages) to `result.json`;
- the **tests** (`test_quick3d_render.py`, `test_quick3d_engine.py`, `test_quick3d_selftest.py`)
  only *judge*, in the ordinary offscreen test process, with a CPU projection of their own
  (`shots.top_down_pixel` + `core.scene3d.pose_ring`) — never with the engine's.

The scene definitions are plain engine-free functions in the driver module that both halves
import, so the test predicts from the same records the driver rendered.

**Which files the CI job runs (#540).** The `render3d` job (`.github/workflows/ci.yml`) runs the
engine-package files above, then — as a **separate pytest invocation**, because `-k` filters the
whole session — **`test_view3d_workspace_render.py`**, filtered to the default workspace's G5
close rows and its G6 crash-marker / compatibility / try-hardware rows
(`-m "not perf and not soak" -k "closes_clean or start_that_died or compatibility_mode or
try_hardware"`; 12 tests). This is the only workflow that starts the workspace every user sees;
before #540 CI exercised the engine package and nothing of the default view. Its **G7 memory
soaks** carry the `soak` marker and stay local (twenty app child processes each), and its
wall-clock rows carry `perf`; G5's *never opened* row is also the real-host proof that no Qt
Quick module is imported before 3D is asked for. A software-only adapter (the CI runners'
WARP/llvmpipe) is detected and the workspace shows its compatibility notice, so those rows
accept the notice where a hardware machine asserts none.

A fourth file has another shape for another failure. `test_quick3d_lifecycle.py` runs ONE call
order of the host per child process (`quick3d_lifecycle_child.py`) and judges what that process
reported — because a Qt Quick window grabbed at the wrong moment returns a good image and the
process dies afterwards, and a Python Qt message handler beside a shown window deadlocks it.
No `pytest.raises` can see either, and in the test process it would take the whole run down.
Its orders are written by hand, and twice the order that failed in review was one nobody had
written (a collapsed pane; `showFullScreen()`). So its last test is not: a seeded random walk
— 250 operations a parent can do to an embedded host (collapse the pane, squeeze it to one
pixel, resize, maximise, full screen, minimise, hide and show the pane, the host, the
window), each followed by a look at once, after `wait_ready()`, or after the event loop ran.
Its judge knows only what QT said about the window at that look — its size, and how much of
it is on a screen: the answer is the scene at that size or a refusal; `wait_ready()` True is
followed by a frame; every `wait_ready(t)` is back within `t` plus what Qt had queued for the
window (the matrix queues nothing of its own and allows 2.0 s) and a False within half a
second of silence; and where ALL of the pane is on a screen, a window Qt shows comes up. The
seed is fixed — a failure must be the same failure twice.

**The judge computes; it does not repeat the host** (review round 5). "A frame of the
window's size" was the same inequality in the host and in the judge — less than one device
pixel off — and at 125 % both took the 553 px frame of a 442 px pane for a 443 px one. The
judge now works out what QT makes for a window (`qt_round`: the logical size times the ratio,
half a pixel up, per side) and asks for exactly that; the host has its own formulation (at
most half a pixel off). Two rules written twice are a check; one rule imported is not. The
ratios that matter are the ones strictly between 1 and 1.5 — 100 %, 150 % and 200 % are exact
whatever the tolerance — so the arithmetic runs in the default tier for every width from 2 to
3000 at twelve ratios against `QSize * ratio` asked of Qt
(`test_the_size_check_is_qts_own_rounding_at_every_ratio`), and one row of the matrix runs a
real window at `QT_SCALE_FACTOR=1.25` with the render target held behind
(`test_at_125_percent_a_pane_one_pixel_wider_does_not_get_its_old_frame`); a raw grab in that
row proves the target IS behind — without it the row would prove nothing.

**The matrix must not depend on the screen it runs on** (review round 4: it did — the walk
asked for 1203 and 1500 px wide windows on whatever it found, and on a 1024 px CI runner the
pane lay beyond the edge, where Windows sends no expose; the local tiers were green "only
because every window fits on this screen"). So: every window of the matrix is PLACED on the
screen on purpose (`_splitter_window`); the walk runs twice — once with every size capped by
`availableGeometry()` (asserted: the pane is on the screen whenever it shows), once with the
window where a 1024 × 768 screen leaves it (asserted: the pane WAS shown beyond the edge);
and the condition that broke CI is not waited for, it is made: `pane_without_paint` puts an
event filter on the view that eats `Expose`, `UpdateRequest` and `Paint` — the view is on
the screen and nothing draws it — because whether a machine withholds those by itself was
measured to change within a day (display asleep, display awake; PF-E3D-06).

**Running it** (it opens windows on the desktop):

```bash
# Windows (Git Bash): Direct3D 11 on the real GPU
OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_quick3d_render.py \
    tests/integration/test_quick3d_engine.py tests/integration/test_quick3d_selftest.py \
    tests/integration/test_quick3d_lifecycle.py tests/integration/test_scene3d_ground_render.py
# … and on the software rasteriser (WARP — what a GPU-less runner has)
OGP_RENDER3D=1 QSG_RHI_PREFER_SOFTWARE_RENDERER=1 venv/Scripts/python.exe -m pytest <the same files>
# Linux: xvfb + xcb + OpenGL (Mesa llvmpipe in a container)
OGP_RENDER3D=1 QSG_RHI_BACKEND=opengl LIBGL_ALWAYS_SOFTWARE=1 \
    xvfb-run -a -s "-screen 0 1920x1080x24" venv/bin/python -m pytest <the same files>
```

Without `OGP_RENDER3D=1` the tier skips with a reason; on Linux it also needs `DISPLAY`. The
helper (`quick3d_render_support.render_env`) gives the DRIVER the real platform and this
checkout's code — the pytest process itself stays offscreen. CI runs the tier in the `render3d`
job (§7.4), which is not a required check. Measured 2026-10-11 on the dev box, after review
round 2: the tier's 96 tests take about four minutes on an RTX 4070 (237 s; 95 passed and one
control reported, not asserted, on Windows) and on WARP (251 s; the two hardware-only budgets
skip there) — with another suite running on the machine; the lifecycle matrix, one process per
call order and several attempts per control, is about two minutes of it. After review round
3 (100 tests: two window-state orders, the random walk and the control of its judge joined):
99 passed and one control reported, not asserted, in 321 s on the RTX 4070, and 97 passed, the
two hardware-only budgets skipped and the one control reported, in 244 s on WARP; the walk
alone took 105 s on the GPU. After review round 4 (104 tests: the second walk and three rows
joined): 103 passed and one control reported, not asserted, in 458 s on the RTX 4070 and 101
passed, the two hardware-only budgets skipped and the control reported, in 355 s on WARP.
After round 5 (105 tests: the 125 % row joined): 104 passed and the control reported in 411 s
on the RTX 4070; 102 passed, the two budgets skipped and the control reported in 287 s on
WARP; the lifecycle file alone on xcb in the container, 41 passed and 4 skipped in 159 s.

**Linux without a Linux machine.** The CI job's stack — Ubuntu 24.04, xvfb, xcb, OpenGL on
Mesa llvmpipe, Python 3.11, the repository's lock — fits in a container, and Docker on the
developer's machine runs the tier there in minutes. That is how the round-2 tree was measured
on xcb before it was pushed, after the round-1 tree had met xcb for the first time in a red
CI job: 88 passed and 8 skipped in under two minutes (round 3: 92 passed and 8 skipped in 184 s;
round 4: 96 passed and 8 skipped in 241 s). A container is
not GitHub's runner; say which one a number came from.

**The tier below it.** Not everything about the engine needs pixels. Under the offscreen
platform `Garden.qml` still loads and Models are still created, posed, tinted, destroyed and
read back, so `tests/ui/test_quick3d_host.py` checks the scene file, every sink call as it
arrives in the QML scene, the sun / ground / camera mapping, the state machine's rules (with
Qt's predicates put where a real window system would put them), the closed-host contract, the
sink's teardown in every order and the recovery after a failed engine call — in the DEFAULT
run, on every machine and in the required CI job. This is also what keeps the `ui` coverage
floor: on Linux, where CI measures, the default tier covers 1,176 of the engine package's 1,325
statements with this file and 789 of the same 1,325 without it (one measurement on one tree,
after review round 2; 94 of the statements it cannot reach are the Windows-only supervising
process of `runlog.py`).

**Its canary contains no product code.** A child process first creates a bare `QQuickView` with
inline `import QtQuick3D` QML. If THAT fails, the platform cannot create Qt Quick 3D objects and
the module skips (on CI it fails: the runners can). The first canary built a `Quick3DHost`, so
a `Garden.qml` that did not load turned the whole file into 32 skips and 0 failures — the guard
skipped exactly the defect it stood in front of. The positive control is a test of its own: the
file is run again in a child pytest with every host pointed at a scene file that does not load,
and must report failures and not one skip (measured: 9 failed, 43 errors, 12 passed, 0 skipped).

**Rules the tier is built on** (each one paid for):

- **Meaning, never golden images.** A box is where the CPU projection puts it (mask IoU), a
  face is lit or not (a luma ratio), a click hits what a CPU ray oracle says. The same
  assertions hold on a GPU, on WARP and on llvmpipe; WARP and the GPU differed by at most 4 of
  255 on a probe frame.
- **Predict in the truth view.** The top-down orthographic shot is not tone-mapped, so a pixel
  is linear radiance and can be *computed*: a lit horizontal face shows
  `tint × (sun brightness × sin(elevation) × sun colour + fill)`; predicted 167.2, measured 171.
- **Every gate has a control that makes it fire.** The mirrored and swapped mappings are
  predicted and must NOT match (IoU 0.000); the wrong rotation sense must not match (0.288 at
  17°); each shader file is broken once and must fail the render; a `QQuickWidget` in the
  embedding test must turn the window into an RHI surface. Angles that cannot tell two senses
  apart (0°, 90° for a rectangle) are not enough — the matrix has two that can.
- **`grab()` on a live host is the only moment of certainty.** The tier never waits for a frame
  to be presented (PF-E3D-06: with the display asleep a visible window presents one frame and
  then none); every step is "change, grab, judge" — after `wait_ready()` said the host is live,
  an answer the driver checks at every place it asks.
- **A crash is not an exception: one call order per process.** The lifecycle matrix starts a
  child per order and takes `END` on the last line as "survived". Controls do what the guard
  forbids, on the raw view, and must fail the way that was measured — die, hang, or answer
  with a frame the judge finds wrong. They only die while the window is still alive in the
  next passes of the event loop: the first version of the control let its host go out of
  scope and "survived" 6 of 6.
- **The judge does not ask the suspect.** The first matrix judged every frame by the state
  the host reported for it — and was blind to a host that reported the wrong state: "live" in
  a collapsed pane (a blank frame, accepted), "new" for a window xcb had already created (the
  order pinned as safe, from a Windows measurement, killed the Linux job). Now a table says,
  per order and per step, what a truthful host MUST answer — a frame of the window's size with
  the probe box at the predicted pixels, a pick that hits it and a projection onto the view's
  centre; or a refusal — and the reported state is checked last, against the answer. Where
  the platform decides (is a window exposed right after `show()`?) the table says "either,
  never a wrong frame", and pins what Windows was measured to do. The window's size, too, is
  asked of Qt (`QWindow.width()`), not of the host.
- **A control is asserted where it was measured, and reported elsewhere.** A crash that was
  measured on Direct3D is not a fact about xcb, and the other way round: `show(); hide();
  grab()` survives on one and kills on the other. Each control names its platforms; on any
  other it is `xfail` without `strict`, so the log of the first run there says `XFAIL` or
  `XPASS` — which is the measurement, to be promoted to an assertion.
- **No Python Qt message handler beside a shown window — not in a test either.** pytest-qt
  installs one for every test (its log capture, measured: `_QtMessageCapture`). What is
  measured about the default `offscreen` platform is an ABSENCE, not a fact: Qt logs "Loading
  backend software" there and names no render loop (on Direct3D 11 and on xcb it says
  "threaded render loop"), and the in-process host tier never hung under that handler. An
  absence is nothing to build on — and a test that shows a host on a REAL platform inside
  the pytest process would deadlock. So real-platform hosts live in child processes, an
  in-process test that shows a host is marked `@pytest.mark.no_qt_log`
  (`tests/ui/test_quick3d_host.py` is, as a module), and no test of that file installs a
  Python handler while a host is shown (the file pins it about itself). The driver
  installs none for its shown-host scenarios (it would deadlock: §8.29.2). Two witnesses
  report instead, and each has a positive control: an OFFSCREEN frame records its own
  messages, on the calling thread (a broken shader fails the render, and the report says no
  message arrived on another thread); for a SHOWN window Qt prints its messages to the
  driver's stderr in a fixed pattern (`QT_MESSAGE_PATTERN`, `QT_FORCE_STDERR_LOGGING` — on
  Windows a process without a console logs to the debugger otherwise), the driver marks each
  scenario, and the test classifies them (a broken shader in a shown window leaves the driver
  at exit code 0 — and is found on stderr, in the scenario it belongs to).
- **A child never sees the developer's data, and leaves nothing in the developer's profile.**
  Every child a test of the engine package starts gets its environment from ONE helper
  (`quick3d_render_support.isolated_env`; `render_env` adds the real Qt platform): the
  variables the app's data directory hangs on (`APPDATA`, `XDG_DATA_HOME`, `XDG_CONFIG_HOME`)
  point into the test's own `tmp_path`, and the user profile itself — which `QStandardPaths`
  and the graphics driver's caches follow, on Windows via `USERPROFILE`, never via `APPDATA`,
  elsewhere via `HOME`, which every XDG location without a variable of its own falls back to
  — is a temp directory of the test process's own, removed at exit. (It is the parent's
  environment with those variables replaced, not an empty one; off Windows two read-only
  lookups survive the move by name: Python's per-user site directory and the X display's
  cookie.) A child that builds the real main window also takes a settings store of its own,
  as `tests/conftest.py` does for the test process. Tests pin the environment handed to the
  child, and that every `env=` a test of the package passes is a call of the helper or a
  variable the same function builds from one and from nothing else (the first guard accepted
  any variable that was called `env`). The SETTINGS store is the one thing no variable
  moves on Windows — a registry key — so the helper also hands every child a start-up hook
  that rebinds the store's names before the child can build one (§8.8, "Child processes"). The lesson behind it: a test once ran the app's log-directory
  helper under a throwaway identity and left a directory in the real roaming profile. The
  test PROCESS itself is isolated by `tests/conftest.py` ("Test isolation", above) — but a
  child does not import conftest, and what conftest replaces in Python (`QStandardPaths`)
  does not reach Qt's own C++: the QML engine writes a compiled copy of every scene file it
  loads into the per-user cache. The in-process host tier loads a fresh copy of `Garden.qml`
  per control (788 such files had piled up in the developer's cache folder), so it switches
  the QML disk cache off for the test process (`QML_DISABLE_DISK_CACHE`, set at import).
- **A recovery is proven against a reference, not against itself.** After a failed engine call,
  `sync.reset()` and `sync.apply(...)`: the sink's state is compared with
  `sync.expected_state()`, the engine's Models with that reference part for part, the frame
  with the CPU prediction — and the half-applied frame in between is looked at, too.
- **At rest means exactly at rest.** Boxes whose every vertex has the full wind weight, in a
  wind 40 times the look's, must lie on the pixels their meshes predict (IoU 1.000, 0.00 px);
  the control removes the shaders' rest factor and the same boxes sit 10.2 and 18.9 px away.
- **The driver records, the test asserts.** A number measured and asserted in the same process
  as the engine can confirm itself. Timings and counters are written down raw; bounds live in
  the tests, with the measured value in the docstring.
- **Budgets only on hardware.** A software rasteriser says nothing about a GPU: timing bounds
  skip themselves when the adapter is WARP / llvmpipe (the adapter's name is read from Qt's
  `qt.rhi.general` output). An adapter the run could not NAME is a failure, not a waiver — the
  first version counted "unknown" as software and would have skipped both budgets green.
  Structural gates (surface types, upload counts) run everywhere.
- **Pick something you can see.** "The frame changed after the edit" is only a test if the
  edited item is visible: the first version moved a chair standing behind a tree and got two
  identical frames. The session edits the two largest solids.
- **A failing run must leave its pictures.** `OGP_RENDER3D_ARTIFACTS` makes every driver run
  copy its frames, `result.json` and log there; CI uploads the directory even when the job fails.

### 8.10.9 Patterns from the 3D workspace (Phase 17 L1.3)

How the workspace (§8.29.3, ADR-060) is tested, and the patterns worth reusing.

**Three tiers, one seam.**

| Tier | Files | What stands in for the engine |
|---|---|---|
| default, no GPU | `tests/unit/test_scene3d_camera.py`, `test_view3d_init_guard.py`, `test_sim_clock_subscription.py`, `test_plain_text.py`; `tests/ui/test_view3d_orbit_input.py`; `tests/integration/test_view3d_sync_controller.py`, `test_plan_revision.py` (the scene's plan revision), `test_view3d_plan_revision.py` (what starts a pass, in the real window), `test_view3d_workspace_widget.py`, `test_view3d_workspace.py` (the §8.10 workflow through a real `GardenPlannerApp`) | `Workspace.engine_factory` returns a stand-in host and a `RecordingSink` — every sink call of an edit session is asserted exactly |
| default, offscreen host | `tests/ui/test_view3d_host_seams.py` (marked `no_qt_log`) | the real `Quick3DHost`, never shown |
| render (`OGP_RENDER3D=1`) | `tests/integration/test_view3d_workspace_render.py` | nothing: the app's own `main()` in a child process on a real device |

- **Replace the engine at the documented seam, not by patching.** `window._workspace.engine_factory
  = factory` before the first switch to 3D. The stand-in host is twenty lines: it records what it
  is told and has a `health()` the test can set.
- **Drive the real signals.** The controller tests execute real commands on a real canvas scene
  and let `QGraphicsScene.changed`, the undo stack's `stack_changed` and the sim clock's channels
  do the rest; "one pass per turn" is only a fact when the turn is Qt's.
- **Assert identity where the rule is "unchanged".** The camera rule compares the pose object
  (`camera.pose is pose`), the goal, the moving flag and the number of camera calls the host got —
  around each of 100 edits. "Approximately the same pose" would pass a camera that drifts.
- **Order on the GUI thread is tested with a paint log, not a sleep.** `PaintLog` (an event filter)
  notes the label's text at every `Paint`; a wrapper around `snapshot_records` notes what had been
  painted when the first snapshot STARTS. The test keeps the GUI thread busy first, so that every
  timer of the start is overdue — the case in which a timer would win.
- **A clock the test holds.** "Quiet for half a second" is read through `workspace._now`; the
  release tests replace it and advance it by hand. No test of a time rule sleeps.
- **Wait for a HELD pass by condition, never by a fixed wait.** The first pass of a document is
  held until its "Building the 3D view…" notice was painted, or for `BUILD_NOTICE_WAIT_MS`
  (250 ms) when the label is not painted, and runs `CATCH_UP_MS` later: about 55 ms with the
  paint, about 300 ms without, measured — and a loaded CI runner can be the second case. The
  story's helpers (`Bench.settle()`, 57 uses, and `_calls()`) waited a fixed 80 ms; with the
  notice's paint withheld from the workspace (a scratch pytest plugin) 21 widget tests and 2
  main-window tests failed, and on the Linux runner one did (`problems_text()` read `''`; the
  pass ran in the test's TEARDOWN). `test_view3d_workspace_widget.pipeline_settled(workspace)`
  is the one condition — no first pass held, none posted, none on the catch-up timer —
  and `wait_for_pipeline()` waits the old minimum and then for it. A test that must read
  BEFORE the fallback (the notice holds the pass back) says so beside its fixed wait. Read a
  result AT the signal that produced it where the claim is "never late": the refused-item
  test records `problems_text()` inside a slot on `controller.applied`.
- **Ask about your own object, not about a count of a shared list.** The theme registry
  (`ui/theme._theme_listeners`) is the process's — under xdist, the worker's: every window an
  earlier test built and left dead has its listener on it, and one theme change takes all of
  them off at once. "The list is one shorter" measured them (CI: `assert 1 == 3 - 1`); "THIS
  coordinator's listener (`SunExposureCoordinator.theme_listener`) is no longer on it" does
  not. A control test reproduces the count's failure on purpose.

**Scripting the REAL app — the workspace gate.** `workspace_gate_hook.py` runs inside the app's
own process (from source: imported by `workspace_gate_child.py` before `main()`; frozen: a
PyInstaller runtime hook of `installer/workspace_gate.spec`) and plays a scenario on the GUI
thread once the main window exists.

> **Rule: no scripted run of the app opens a plan on the production settings names.** A plan
> load writes Recent Files and a clean close writes the window geometry — on Windows into a
> registry key that no environment variable moves. The hook rebinds the two names before
> anything builds a store, records every store by the names Qt reports for it, and ends the
> process with exit code 97 BEFORE a store under any other organisation exists. That is proven
> in the default tier (`test_workspace_gate.py`: `main()` on a plan; a decoy organisation
> refused) before the gate is used once on a real platform, and asserted again inside the
> frozen exe.

- The hook is READ by tests, never imported: importing it rebinds the settings names of the
  importing process. A test pins who may import it.
- A scenario is a generator that yields "wait this long" or "wait until this is true"; every
  step is written to the report at once, so a process that dies leaves the last step it reached.
- The verdict (`GateRun.problems()`): the exit code, a failed step, any Qt warning or error on
  stderr (Qt's own handler, never a Python one), any ERROR line in the child's `app.log`, and a
  run that did not end with a closed window.
- **A gate run talks to nobody.** The hook answers every `urllib.request.urlopen` of the child
  with "offline" at once and counts the calls; every run asserts `network == "offline"`. Before
  that, every frozen run asked GitHub for a newer release two seconds after its window existed,
  and a close while that request was in flight aborted the process (0xC0000409) — the gate
  depended on how fast GitHub answered. The abort itself was a defect of the shipped app,
  fixed on master by `core.worker_lifecycle` (#480); the gates stay offline all the same.

**Measuring rules, each paid for** (PF-E3D-07 has the wrong versions):

- **"A frame" is a finished readback taken the moment the pass committed** — inside a slot on
  `controller.applied` — not `frameSwapped`, and not after `processEvents()` (which adds the
  rest of the 2D side's turn to the 3D number). State the window and pane size with the number:
  a readback grows with the pane's pixels.
- **A memory soak takes no frame inside its measured loop.** A readback renders a frame of its
  own that is never presented, and what it holds stays until a presented frame ends: a soak
  that reads back every cycle measures the readback (twenty rebuilds with the view's frames
  withheld: 1.5 MB per rebuild without a readback, 8.5 with one per rebuild). ONE frame
  before the loop and ONE after it prove the picture; in between the scenario waits on
  `health().frames_presented`, never on a grab. The readback stays the measuring device of
  the LATENCY and PICTURE scenarios, where it is what is being timed or looked at.
- **The soak is judged twice: presenting, and with frames withheld.** Qt frees a destroyed
  Model's buffers at the end of a presented frame, and with the display asleep Windows
  presents none — so `run_gate` sets Qt's `QT_D3D_NO_VBLANK_THREAD=1` by default (update
  requests by timer: no scenario may depend on whether the dev box's display is awake), the
  soak reports how many frames each rebuild presented, and the test asserts at least one.
  The second slope takes the frames away on purpose (`frames="withheld"`: the engine
  story's no-paint filter on the view) and asserts that none was presented.
- **A stand-in host records what must not be called.** The GPU-less tests' host has `grab`,
  `wait_ready`, `pick` and `project` — each only appends its name to a list — so "the
  workspace takes no frame from the live view" is an assertion on that list after every
  steady path ran, beside a scan of the source that would also see a call no test reaches.
- **A slope gate needs its control and its "off" run.** The soak runs with the fix, with 25 MB
  kept per reload (must FAIL) and with the fix out of reach (reported): three numbers from one
  instrument on one machine.
- **A gate measures the product — a known leak gets an allowance derived from the run, not a
  configuration nobody ships** (L1.5 review 3, P1-2). The ground bake made two G7 gates fail on
  a Qt bug (#532: every cache release keeps about half of the same-size tile textures). Turning
  the bake OFF for the gate measured something that does not ship, and a fixed "regression
  ceiling" of 60 MB per rebuild (about three grounds of the bench plan) could not fail. Now the
  soak REPORTS what the ground's textures hold (`ground_texture_mb`: tiles × width × height × 4
  × 4/3 for the mips) and how many releases it made; the bound is `LEAK_BOUND_MB_PER_RELOAD` +
  0.6 × that per release × releases per reload (`known_532_allowance_mb`), and the failure
  message names #532 and the Qt source lines. The control is judged against the same bound,
  and keeps 25 MB per reload BEYOND the allowance (a fixed 25 MB sat 3 MB above the raised
  bound in an instrument that swings ±10 MB a run). A `xfail` tripwire holds the product's
  GPU slope to the PLAIN bound — it passes the day the leak is gone; it is not strict, because
  on the bench plan the leak reads about as much as the bound (+9.3 to +11.4 MB per rebuild
  against 10 in eight runs, seven of them under 10: XPASS, XFAIL, XPASS in review 3's three). Model churn alone (the
  bake off) stays as an additional variant against the plain bound. *The instrument's limit,
  measured in the same runs:* private bytes swing by ±100 to 200 MB from one reload to the
  next on this tree, with the bake on or off, so a ten-point slope reads ±13 on a flat curve
  (Model churn alone: −12.3, +7.5, +8.0, +13.3 in four runs — the last above the plain bound,
  its GPU slope +0.8); the GPU slope is the stable reading. And "the same picture" before
  and after a soak allows 2 of 255 per pixel (`SAME_IMAGE_TOLERANCE`): since the L1.4 sky,
  six sky pixels differ by 1 in about half the runs, at the story's head as well.
- **Compare two modes along the same path, in alternating short blocks.** The 2D pan cost in
  Split against Plan: six rounds of 60 steps each, every block from the same scroll position
  along the same pixels, the canvas at the same size in both, every step checked to have
  scrolled. Report the medians and the fastest tenth.
- **Committed memory, not the working set; and ask DXGI for VRAM** —
  `IDXGIAdapter3::QueryVideoMemoryInfo` through `ctypes` (`workspace_gate_measure.gpu_dedicated_mb`).

**Checking that a test bites.** After the tests were green, each rule was broken once in the
source — one text mutant at a time, the story's tests run, the file restored — and a mutant that
survived got a test (the sets are listed in ADR-060, Validation).

**Wall-clock gates carry `perf`; the default tier keeps their load-proof half** (ADR-058).
`tests/unit/test_perf_marker_guard.py` follows timing sources through the call graph, so a
helper that only WAITS but reads a clock (`Live.quiet()` measured its stable time with
`time.monotonic()`) makes every test that calls it "wall-clock sensitive": it now counts 25 ms
turns and asserts nothing about how long they took. A gate whose statement IS about time keeps
two forms. "A repaint takes no snapshot while it happens" asserts that the canvas was never
still for the quiet time inside the activity — wall clock, so the strict form is `perf`
(`test_a_repaint_in_the_real_window_takes_no_snapshot_while_it_happens`, run with
`pytest tests/ -m perf -n 0`); the default tier asserts what holds under any load — no repaint
starts a pass of its own, every pass in and after the activity is the net's and finds nothing
(`…_never_starts_a_pass_of_its_own`). The same split for the render tier: G2 (edit → frame) and
G11 (pan cost ratio) are `perf` too, so the whole workspace render file on the GPU is
`OGP_RENDER3D=1 pytest tests/integration/test_view3d_workspace_render.py -m "perf or not perf" -n 0`.

**Pin a layout at the size where it broke, with every notice at once, in every language.** "The
strip fits" was believed after the notices moved to rows of their own; the test at the review's
size (main window 1366 px, Split → a 455 px pane) with the longest compatibility sentence, its
button and two refused items found two sentences that were still on BUTTONS, squeezed below
their text (German: 220 px for 488 needed). Assert per visible label `wordWrap()` and
`height() >= heightForWidth(width())`, per visible button `width() >= sizeHint().width()` and its
right edge inside the pane. The app starts maximised: `showNormal()` before `resize()`.

**A test owns no process-wide state, and the suite's order is part of the test** (PF-E3D-07 item
13: two tests of this story were green in every run of its own files and red in the whole
suite). Compare a process-wide table with what was in it BEFORE the test — hold those entries
for the test's length — never with zero. Compare a widget only with one in the same state: a
widget that was never shown is not polished, and under an application style sheet an earlier
test left behind it measures differently from a shown one. Run the whole default tier in its
own order before a story's files are believed.

### 8.10.10 Parity against the 2D canvas, and counting instead of timing (Phase 17 L1.5)

The ground bake (§8.29.5) must paint what the canvas paints. How that is tested, and what each
rule was bought with (`tests/integration/test_scene3d_ground_bake.py`,
`tests/integration/ground_bake_support.py`, `tests/unit/test_path_style_paint.py`; the render
tier: `tests/integration/test_scene3d_ground_render.py`):

- **The reference is the canvas's own render, on the bake's own pixel grid.** A test-owned
  `CanvasScene` holds the items; `services.scene_rendering.render_scene_region` renders it with
  labels and shadows off at the bake's resolution, and the baker is given the canvas's background
  colour as its bare colour (`GroundBaker(bare_rgb=canvas_rgb())`) — the two images are then
  comparable pixel for pixel, with no mask and no tolerance for "the background". Never compare
  against a stored golden image: it pins yesterday's canvas.
- **Bake once as ONE tile, once as tiles.** `tile_px=2048` makes the test plan a single tile:
  that bake must be the canvas's render **bit for bit** (mean 0, max 0), turned or not — it shows
  the painter is right. The 512-px bake of the same scene then shows only what tile borders add,
  and the bound for it is stated with its cause (a hairline clipped per device: mean ≤ 0.016).
  A single tolerance over both hides a wrong brush origin behind "antialiasing".
- **State the largest single difference and how many pixels differ, not only the mean.** A mean
  of 0.001 is one wrong dash in a megapixel. The dashed-outline tests assert where the differing
  pixels lie (one place, at most 40 px across).
- **Straddle on purpose.** Every parity case is placed across a tile border and across a corner
  where four tiles meet, turned by an angle that is no multiple of 45°, with odd sub-pixel
  offsets — the cases a centred, upright fixture cannot fail.
- **When the reference itself is wrong, judge by arithmetic.** Over 9.5 km of line outside the
  image Qt's dasher loses the dash phase (it agreed with the arithmetic at 261 of 393 sampled
  places), so the 19-km dashed line is judged against where the dashes must be, computed in the
  test, not against the canvas.
- **Orientation needs an asymmetric fixture and its mirror images.** `bench_small.ogp` baked
  against its canvas render: normalised cross-correlation 0.99999999 for the identity, −0.28 /
  −0.09 / 0.005 for the three flips. In the render tier the same four numbers are taken between
  the engine's top-down frame and the bake — after bringing the bake into the frame's terms
  (linear light, the mean over the texels a frame pixel covers): compared naively the identity
  scored 0.93, compared like with like 0.98.
- **The live scene is spied on, with a control.** `selectionChanged`, `scene.changed` and every
  item's visibility are recorded while the scene is baked with a selection active; the same spies
  must fire for the old way (hide, render, restore), or they prove nothing.
- **Hostile input is pinned by counts, never by a clock** (§8.11): elements generated, steps of
  the walk, dashes charged, records painted, tiles painted, entries held, comparisons made, the
  size of the image a sprite renderer is asked for, points read by the snapshot — each with a
  control that shows the instrument sees what it bounds (the canvas's own walk over the same
  19-km line: 475,001 elements; the bake's five tiles: under 4,000). A test of a bound runs AT
  the bound and one beyond it (16,384 and 16,385 vertices; a budget spent to the last element by
  the first path).
- **Incremental == full, bit for bit.** After a scripted edit session through the app's own
  commands the tile set equals a fresh baker's on the final records (`SceneSync.expected_state`),
  and an untouched tile is the same OBJECT as before the edit — identity, not equality, is what
  the sink's "upload nothing" rests on.
- **Render tier: a seam is judged where it would be, with two controls.** Regions of one colour
  crossed by a tile border must have a luma spread below 2 (measured 0.0 to 0.7); the same
  measurement must see a 2 cm gap between the quads (48) and a texture set to repeat (7.9). The
  repeat control needs a lawn whose tiles have ANOTHER colour at their opposite edge — on a
  uniform lawn a repeating texture is invisible.
- **Render tier: a leak gate reads objects first, memory second — and measures what a live
  view does.** `ground_tiles.textures_alive()` (the textures whose C++ object exists, asked of sip) holds the keep-alive
  rule on every backend. The memory slope (Theil–Sen over the second half of twenty cycles, with
  a control that keeps every texture) is taken on the machine's own adapter AND on a software
  rasteriser, whose textures are in the process's own memory. The soak takes NO frame in its
  measured loop: the gate's first version called `grab()` after every re-bake, measured the
  grab instead of the re-bake (+16 MB a cycle on a Direct3D 11 window that presents nothing,
  +0.00 without the grab) and excused the result as an expected failure. The gate is
  unconditional now; the grabbing soak is kept as the CONTROL that shows the effect, and is
  reported as not run where the window presents (PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md). Nothing but the re-bake belongs in
  the measured loop — not a query of the QML scene either: per cycle the test reads counters on
  the Python side and reads the scene back once, after the loop. And say which CELL a run was:
  on a hardware window that presents nothing the soak renders nothing, so that cell cannot see
  the graphics side — the test prints it, and a presenting hardware window stays a manual check.
- **Render tier: updates without a frame between them are a case of their own.** Every scenario
  of the first delivery re-baked, took a frame, and re-baked the SAME tiles — which hid a tile
  that turned white when another tile was re-textured after it, or one frame after its replaced
  texture was let go (PF-L3D-04). `ground_retexture` drives five sequences (one tile twice, five
  times, two tiles in turn, a frame between, the other tile after a frame), lets the replaced
  textures go as a presenting window would, and judges each tile's colour against a reference
  frame of that colour — right after the last update and again one frame later.
- **A bound that drops something is tested by WHAT it drops.** "At most 256 records a tile" was
  pinned by counts and still dropped the lawn. `tests/integration/test_scene3d_ground_rules.py`
  paints the same records once more without tiles and without bounds (`unbounded`) and asserts
  where the capped ground differs from that picture and what is there: pavers missing, the lawn
  never. A count says how much was left out; only a picture says whether it mattered.
- **… and on more than one geometry.** The first fix of that rule was pinned with a lawn that
  was the plan rectangle — the one lawn that covers every tile whole — and passed; 10 cm inside
  the plan's edge the same lawn was dropped again. A rule about "what covers the tile" is tested
  with a cover that ends ON the tile's edge, one just inside it, and one that covers a third of
  the tile.
- **A class of defect is guarded by behaviour, not by reading the source.** "Every writer keeps
  an item's style attributes in step with its brush and pen" was first guarded by an AST scan
  for functions that build an item from an item; a review planted six forgetful operations and
  the scan saw one (it knew a keyword spelling and two folders). The guard is now a teardown
  fixture (`tests/integration/conftest.py::_every_item_says_what_it_paints`): every
  `CanvasScene` an integration test builds is tracked, and at the end of the test every item in
  it must satisfy `core.item_look.style_gaps(item) == []` — whatever tool, panel slot, undo,
  loader branch or test helper wrote it. A test that puts an item out of step on purpose says so
  with `@pytest.mark.style_gaps_allowed("why")`. The guard costs 7 ms for the 495-item reference
  plan and 30 ms for 2,000 textured rectangles; it cannot see a writer no integration test
  drives, an item that left its scene, or a scene built by a module-scoped fixture. Its own
  teeth are tested with the six planted operations (`TestTheGuard`). The scan is kept as a map
  of the derivation sites, not as the guard.
- **A time budget is tested with a clock the test owns.** `GroundBaker(budget_s=3.0,
  clock=Ticks())`: a clock that advances one second a reading makes "three tiles a call" an exact
  count. The strongest assertion is the invariant, held after EVERY call of a random edit
  session: a tile that is not pending is the finished picture of the records as they are now, and
  a pending one is the very object it was. One measured row with the real clock belongs in the
  docs, not in an assertion.
- **A reviewed fix is not pinned until a mutant of it dies.** Each rule of the review round was
  broken once in the source (a cover never seen, the budget never spent, a failure cleared by
  another tile, the paint turn not carried, …): 23 mutants, 23 killed — the first run left one
  alive (an edge THROUGH a tile was never the deciding fact in a test), and the test that kills
  it is the one that would have missed the defect.
  Review round 2's rules: 63 mutants, all killed.
- **A leak gate reads the median STEP, not a slope that one step can tilt (Ruling R41).** G6
  first read Theil–Sen over the last ten cycles of twenty (the median of all pairwise slopes).
  On WARP a curve flat at 813–814 MB took ONE step of +20.6 MB at cycle 15 and was flat again —
  and read +2.80 MB a cycle, over the bound of 2.0: a step in the middle of the window tilts
  most PAIRS, so the median of pairs moves (1 of 4 runs that day). A leak adds memory every
  cycle; an allocator takes one more block once. G6 now reads the MEDIAN of the last ten
  cycles' growth (`ground_bake_render_driver.tail_growth`): a leak is most of the steps — the
  median is its size (+32 MB a cycle for the control, which still fails the bound by far) — and
  one step is one of ten: the median is about 0. The bound is unchanged (2.0 MB a cycle); the
  measured curves are pinned in the default tier
  (`tests/unit/test_scene3d_ground.py::TestTheLeakGatesStatistic`, which also shows the old
  statistic reading the step as > 2.0). *Its blind spot, measured the same day:* a leak that
  strikes less often than every other cycle is a minority of the steps — a release every fifth
  cycle stepped a curve up by 10 to 25 MB at each release (+44 MB over twenty cycles) and the
  median of the steps read +0.07. G6 leaks per re-bake, every cycle, so the gate sees what it
  is for; a soak for an occasional leak must look at the total growth as well.
- **A pass the controller owes is counted, never waited for by the clock.** The wiring tests
  (`tests/integration/test_scene3d_ground_wiring.py`) give the workspace's controller a baker
  with a budget of 0 — one tile a pass at least, so every multi-pass path is taken — and wait
  for `Scene3DController.idle` (no pass owed, posted, on a timer, or the ground's — and a
  controller that gave up is idle: nothing runs before a change). Then they count: one snapshot
  per edit and none per ground pass (`snapshot_count`, `ground_count`,
  `TickReport.ground_pass`), `unannounced_changes == 0` after the net's quiet time, the sink's
  state equal to `expected_state()` once nothing is pending, and a tile not yet painted after a
  document change BARE. Ordering claims are made INSIDE a pass's `applied` slot
  (`GroundRig.during`): a 0 ms timer armed in ground pass 5 must fire before ground pass 7
  (it starves no timer). A failure that repeats is a sink that refuses the same tile every
  time (review 3's probe, `TileZeroRefused`): after a second of event loop `recovery_count <= 1`,
  `idle`, ONE ERROR line, a note in the list — and the next edit, and a new document, try
  again. The workspace's own handling of a ground pass is pinned with a test clock that jumps
  10 s after the edit's pass: no ground pass hands the look a sun, and the release is due.
- **The wall-clock gates run on the quiet runner.** G3 — a two-tile edit's bake in at most
  10 ms in the median, a four-tile edit's in 20 ms and two passes (#615, decided) — carries
  `@pytest.mark.perf` (ADR-058, §8.10.4): beside eight workers it read 11.58 ms. So does its
  render-tier twin, whose median is taken in the driver process
  (`test_scene3d_ground_render.py::test_one_small_edit_re_bakes_within_the_time_budget`; the
  rest of that test stays in the render tier — review 3, P2-1). Unlike the pure-Python budgets
  of §8.10.5, G3 asserts its real bound under coverage's tracer too. The bake is mostly Qt
  painting; the tracer slows its Python share, about 1.4× in all on bench_large, not 9×.
  Measured interleaved in PR #613 on the dev box with the test process opted out of power
  throttling: border 3.8–3.9 → 5.2–5.5 ms, corner 6.8–7.2 → 9.9–10.0 ms. Do not add a
  tracer factor back: the one tried in PR #613 weakened master's gate. G3 prints its
  readings in every serial (`-n 0`) run's log. G3's stopwatch is an ATTRIBUTE of
  `tests/integration/ground_bake_support.py::TimedBaker`. Issue #528 makes the perf-marker
  guard (`tests/unit/test_perf_marker_guard.py`) follow that carrier and require the marker.
  The class originally moved to the support module to avoid the guard's bare-name collision;
  lexical function identities now keep timed and ordinary `bake` methods distinct even
  within one module. Everything else is counted.
- **A fix kept over another branch's mechanism is pinned by putting that branch's code back.**
  Where `master` fixed a defect this story had fixed too, `master`'s mechanism won the merge; for
  every fix the story KEPT, a scratch check put the integration branch's code back at that place
  (a whole file, or the one hunk) and ran the pinning tests: each had to fail (10 of 10 did — the
  loader and saver, the corner tools, trim, `clone_with_points`, the fresh line, the panel's undo,
  the two style painters, and `restore_stored_look` on a stroke of no kind).

### 8.10.11 Patterns from the looks, the sky and the wind (Phase 17 L1.4)

How the look (§8.29.4, ADR-059 addendum "looks, sky and the animation policy") is tested, and the
patterns worth reusing.

| Tier | Files | What stands in for the engine |
|---|---|---|
| default, no GPU | `tests/unit/test_scene3d_look.py` (the rig, the ramps, the presets, the auto preset, sky staleness), `test_view3d_look_settings.py`, `test_board_probes.py`, `test_render_beauty_board.py`, `test_quick3d_pure.py` (the mapping); `tests/integration/test_view3d_look_controller.py`, `test_view3d_looks.py` (§8.10: a scripted day in a real `GardenPlannerApp`) | a recording host (`set_look` / `set_sky` / wind calls, a `health()` the test sets) and a `RecordingSink` |
| default, offscreen host | `tests/ui/test_quick3d_host.py` (`TestKeyLight`, `TestSky`, `TestWind`) | the real `Quick3DHost`, never shown: properties read back from the QML scene |
| render (`OGP_RENDER3D=1`) | `tests/integration/test_view3d_looks_render.py` + its window driver `view3d_looks_driver.py` | nothing: the production board as a child process, on the GPU and on WARP |

- **Pin the port against the source, at a resolution finer than any step.** The rig is compared
  with the L0 spike's functions at every quarter degree from 0.5° to 40.25° (and the night rig on
  its own); a deliberate
  difference is a test of its own that names it and its measured reason (two: the night fog's
  energy, the night ground hemisphere's).
- **Continuity is a bound on adjacent samples, then a finer sweep.** No step in sun colour,
  exposure, sky or fog between adjacent half degrees above a stated bound — and a sweep ten
  times finer (0.05°) finds no cliff between them (a ramp can be continuous at the half
  degrees and jump in between).
- **A state machine fed with synthetic series.** `AutoPreset` has no clock of its own; a `Feed`
  helper plays frame counts at chosen times: slow, fast, noisy around each threshold (it must not
  oscillate), stalled (it must hold), a single hitch, a counter that starts over. The controller
  tests replace its clock and drive its timer slot by hand — no test of a time rule sleeps.
- **Assert the look as data, then in pixels.** The default tier asserts `host.looks[-1] ==
  look_for(sun, preset)` — equality of frozen data — and the counts of sky builds and wind
  calls; the render tier asks the engine whether the frames say the same.
- **The light's direction is read back from the scene the engine draws from**, not from what
  Python sent: the quaternion on the QML light rotates (0, 0, −1) onto −`SunState.direction_scene`
  mapped to the engine frame, for a sweep of elevations and azimuths, and onto the moon's stated
  direction at night.
- **An instrument needs a positive control in the same run.** The speckle gate runs the board
  once more with `sharpnessAmount` 0.08 in a copied scene file (the control must fire); the
  memory soak runs once more with a scene file whose `buildSky` never destroys the old Texture
  (the slope must exceed four times the bound); every probe of `board_probes.py` is tested on
  synthetic frames where the answer is known (a shadow painted where the 2D geometry puts it
  scores 1; shifted, it scores low).
- **A soak takes no frame inside its measured loop** (ADR-060 decision 17): one readback before,
  one after (they must be equal), twenty sun changes in between with the frames presented — and
  once with the frames withheld, as on a sleeping display.
- **A sequence A → B → C, then a frame after the old objects are gone.** The sky driver builds
  three skies with a frame after each, destroys nothing by hand, then renders twice more: the
  last sky must still be there, its sun at the solar azimuth (the Qt texture trap, #476, breaks
  exactly this).
- **The render tier's one wall-clock bound is `perf`** (ADR-058): the software adapter's frame
  time. Run the file with `-n 0 -m "perf or not perf"`.
- **No test of the look depends on a sleeping or awake display**: the window driver presents by
  timer (`QT_D3D_NO_VBLANK_THREAD=1`), and the auto preset's "no data" case is a synthetic stall.
- **A wiring call is tested through the window that makes it** (fix round 1). The Preferences
  dialog's `exec` is patched to change its widgets and save, and `window._on_preferences()` runs
  — so deleting the window's one call to the workspace fails the test (2 failures; the earlier
  test called `workspace.apply_look_settings()` itself and stayed green without it).
- **A cross-session rule is tested with two sessions** sharing a store and a wall clock the test
  holds: the first steps medium -> high -> medium and stores the bar; the second, a minute
  later, must not step; the third, after the deadline, retries once and doubles the bar.
- **An aliasing instrument needs a reference, not a threshold.** The fence probe renders the
  fences alone at the frame's size and at twice its size, filters the large one down in linear
  light and measures the luma error over the fences' pixels (`thin_geometry_moire`): FXAA 20.0,
  2x MSAA 12.0, 4x 6.2 at low. A dark-pixel share alone cannot tell aliasing from a picket's own
  shaded side.
- **Measure a step AT the edge, not as two band means.** Two first versions of the plan-edge
  probe got it wrong: looking ACROSS an edge, the farther band read +3 … +8 luma brighter
  whatever it was made of; looking ALONG it, two band means 2 m apart still read the view's
  smooth gradient (1.4 luma per metre) as +4 for identical materials. The probe now fits each
  side on lines across the edge and compares the two fits at the edge line, along the edge
  from both ends, and gates the largest view — a mean of the two views would hide a sheen that
  is darker one way and brighter the other (the old material: −4.1 / +4.3). Positive control:
  the old material reads 4.65, the meadow's 0.21.

### 8.10.12 Patterns from selection, the info card and walk mode (Phase 17 L1.8)

How §8.29.8 is tested, and the patterns worth reusing. The seam is the workspace's
(§8.10.9): `Workspace.engine_factory`.

| Tier | Files | What stands in for the engine |
|---|---|---|
| default, Qt-free | `tests/unit/test_scene3d_walk.py`, `test_scene3d_selection.py`, `test_scene3d_pick_oracle.py`, `test_quick3d_selection_ring.py` (the QML and shader text) | nothing is needed |
| default, widgets | `tests/ui/test_view3d_click.py`, `test_view3d_walk_mode.py`, `test_view3d_info_card.py`, `test_view3d_selection_ring_host.py` | a host that records; the real `Quick3DHost`, never shown |
| default, the workspace | `tests/integration/test_view3d_selection_bridge.py`, `test_view3d_selection_workspace.py`, `test_view3d_selection_controller.py`, `test_view3d_walk_bench.py`, `test_view3d_selection_walk.py` (§8.10: a real `GardenPlannerApp`); `tests/perf/test_view3d_selection_walk_budget.py` | `RecordingSink` and a host whose `pick` answers from a script |
| render (`OGP_RENDER3D=1`) | `tests/integration/test_view3d_selection_render.py` (driver: `view3d_selection_driver.py`, judge: `view3d_selection_support.py`); `test_quick3d_selftest.py` | nothing: the real engine in a child process, GPU and WARP |

- **Measure the other side's rules before mirroring them.** "A locked layer is respected" has
  three possible meanings. `test_view3d_selection_bridge.py` first clicks the REAL canvas with
  `QTest.mouseClick` (through a locked item, with Shift, on a group member) and writes down what
  it does; the 3D rule is then asserted to be that — and the one place where 3D deliberately
  differs is a test of its own that names the canvas's behaviour as the defect.
- **An oracle that shares no code with the thing it judges.** Picks are judged by
  `core/scene3d/pick_oracle.py`: its own camera model, its own projection, its own ray caster
  over the records' meshes. The walker is judged by `Brute` in `test_view3d_walk_bench.py`: the
  distance to EVERY segment (no grid) and a crossing count of its own over the records' rings.
  The engine's `project()` and the walk core's index are never asked whether they are right.
- **Judge a pick only where the answer does not hang on a pixel.** `robust_answer` asks the
  oracle 1.5 px all round a position; where the answer changes, the position is on a silhouette
  edge and either answer is right. Report both counts (off the edges: 360 of 360; on one: 36 of
  40) — "400 of 400" would be a claim about float rounding.
- **Seeded points must be able to fail the gate.** Of the twenty seeded picks at most six may be
  "nothing": twenty lawn clicks prove nothing about picking. The workspace's sixty clicks are
  aimed at the middle of the view for the same reason.
- **Controls for everything a frame is asked.** The look-through test (288 frames, 0 marker
  pixels) has two: the marker IS that colour in a frame, and an eye inside the near distance
  DOES see it. The ring's depth has two: the same frame depth-tested, and the same shader with
  its first formula on OpenGL. The clean-run test has one: a broken `ring.vert` is heard.
- **A timing loop takes no frame.** Selection → the engine has its ring is timed to the end of
  the pass (a slot on `applied`), 120 times, with no readback; one frame is taken after the
  loop, and the ring must be in it. A change that does not arrive is counted as a MISS, never
  dropped — and every pass of a missed change is recorded for the failure message.
- **Drive walk mode's time by hand.** `WalkMode.clock` is an attribute and `WalkMode.step()` is
  the timer's slot: a test sets the clock, calls `step()`, and exactly that much time has
  passed (`hold(key, seconds)` in `test_view3d_selection_walk.py`).
- **Pin a layout rule on geometry.** `test_no_selection_change_and_no_walk_resizes_the_3d_view`
  records the engine widget's rectangle through eight states; the render tier records the real
  view's size at every click. Both were written after the defect, and both fail on it.
- **Real input for one row.** `QTest.mouseClick(host._view, …)` and `QTest.keyPress(host._view,
  …)` on the real `QQuickView` reach the event filters as a user's input does; everything else
  sends events to the filters directly.
- **Mutation as a sanity check of the walk tests**: six text mutants of `walk.py` (no push-out,
  a step per frame, footprints only, no sliding, a thinner walker, the carried time dropped),
  each killed. A scratch tool, point in time, not a gate.
- **Pin "one path" twice: by behaviour and by structure.** The select-by-id path is pinned by a
  parity test (a Diagnostics-panel row and a 3D-list row, four kinds of id, the same selection)
  AND an AST scan (the callers call `select_by_ids`; no `clearSelection` elsewhere in the panels
  or the 3D package). The parity test alone passes on the old, duplicated code — it agreed by
  accident; only the scan fails on it (mutant: master's former `_navigate`).
- **A tripwire for a fix that belongs to another story.** A canvas selection in Split cost
  whole-plan snapshots (the pipeline read the canvas's repaint as a change); the fix was the
  workspace story's plan revision. `test_a_canvas_selection_in_split_takes_no_snapshot`
  asserted the target as `xfail(strict=True)`; when the fix landed it XPASSED, failed the run
  as intended, and its mark was removed (0 snapshots for 4 selection changes; the net it arms
  finds nothing).
- **Wall-clock asserts carry `@pytest.mark.perf`** (ADR-058): the walking-pace test checks a
  distance against the time W was really held, so it runs in the serial `-m perf -n 0` step;
  master's `test_perf_marker_guard` names any that is not marked.
- **Deliver input the way the app gets it** (review 1, P1-3). Calling `eventFilter` by hand
  skips `ShortcutOverride` and the main window's shortcut map — exactly where S was lost. The
  stand-in host (`PickHost`) has a REAL `QWindow` in a window container with the filters on
  it, and a "tail" filter installed first (so Qt runs it last: it sees what no filter took);
  clicks go in with `QTest.mouseClick`, keys with `QTest.keyPress` to
  `QGuiApplication.focusWindow()` — the window that has the keyboard, as the OS would.
- **A control before the claim.** Not walking, S pressed into the 3D view toggles Snap to Grid
  — proof that the shortcut path is live in the test; only then does "walking, S walks and
  nothing fires" mean something.
- **Derive the set, never list it from memory.** The §8.10 test collects every single-key
  shortcut of the live main window (`QAction`s, buttons, `QShortcut`s: 12 today) and checks
  the walker's keys against all of them, and the canvas tool, after each.
- **Offscreen focus is asynchronous.** Under `QT_QPA_PLATFORM=offscreen` the focus window
  changes at once, but the `FocusOut` / `FocusIn` events of an activation arrive later — a key
  pressed before they are processed is let go by the walker's `FocusOut`. Wait for the focus
  window, then let the event loop run (100 ms) before the first key.

### 8.10.13 Patterns from the default flip and the removal of Qt 3D (Phase 17 L1.9 / L1.10)

How §8.29.9 is tested. The seam is still the workspace's (`Workspace.engine_factory`, §8.10.9).

| Tier | Files | What it proves |
|---|---|---|
| default | `tests/integration/test_view3d_workspace.py` | no switch is read and the workspace is always there (the variable set to "", "0", "1" changes nothing; a source scan finds neither its name nor its function); View → "3D View" shows Split and nothing names the retired window's slot (an `ast` scan); the Keyboard Shortcuts dialog lists every mode action's REAL shortcut; G1: a fresh process that builds the app, opens a plan and closes has no engine module loaded |
| default | `tests/integration/test_view3d_sync_controller.py` | date playback (#531): a burst of dates regrows at once and once more on its last day; hidden, it is one catch-up and no timer |
| perf (`-m perf -n 0`) | the same file, `test_a_held_date_key_regrows_at_most_once_per_interval[500\|0]` | a held key for two seconds (a step every 33 ms) against its control without the interval |
| render + perf | `tests/integration/test_view3d_default_render.py` (scenarios: `workspace_default_measure.py`) | the real `main()` in a child: no engine module at start, the first 3D click to a finished frame, a held date key against the behaviour before L1.9 |

- **Make a burst deterministic by putting it in ONE turn of the event loop.** A throttle's
  "first at once, last when the interval is over" cannot be asserted with sleeps on a loaded
  runner. Issuing the 27 later dates inside one turn (no wait between them) makes the deferral
  certain; the wall-clock bound ("at most once per interval") sits in a `perf` test whose
  bound is derived from the time it measured (`regrowths <= held_s / interval + 2`), with a
  control arm on the same machine (interval 0 → one regrowth per step).
- **A helper that says "settled" must know every timer that books a pass.** The date throttle
  added a third timer beside the posted pass and the tick timer. `Scene3DController.idle` and
  the tests' `pipeline_settled` both had to learn it, or a test reads the light-only pass and
  misses the trailing regrowth. A new timer that books a pass goes into both, in the same
  change.
- **A test that writes twice must not depend on the time between its writes.** The workspace
  workflow writes a date, then another one a few hundred ms later — inside the interval on a
  fast machine, outside it on a slow one. It pins `DATE_REGROW_MIN_MS = 0` (the throttle has its
  own tests) instead of hoping for a speed.
- **Run the "before" arm before crediting a fix.** The wind soak's strict xfail (FU-L14-2) was
  red on the UNCHANGED code the day the fix was to be measured: the growth L1.4 had measured
  did not reproduce. Measuring only the "after" arm would have credited the new clock with it.
  A/B a change against a soak alternately, three runs per arm at least, the same machine and
  session, and compare the spread, not one number. And do not read six quiet runs as "gone":
  a seventh run the same day (the final render tier on the L1.9/L1.10 tree) read a second-half slope of 2.637 MB a minute, so the gate is a non-strict xfail again (#534).
- **Measure what a deleted component cost while it still exists.** The old window's numbers
  (`scenario_budget_old_view`, called through its own slot because no menu reaches it after the
  flip) were taken on the L1.9 tree, before L1.10 deleted it; afterwards there is nothing left
  to compare with.

The removal (L1.10) added three tests of what is NOT there and moved the drift guards onto
frozen data:

| Tier | Files | What it proves |
|---|---|---|
| default | `tests/unit/test_no_qt3d_left.py` | no file a clone contains (`git ls-files`) in the code areas — `src/`, `installer/`, `scripts/`, `tests/`, `.github/`, `quality/`, `pyproject.toml`, `uv.lock`, `pylock.toml` — names Qt 3D's modules or wheels (the test's pattern, any case; "Qt 3D" with a space is the prose name and allowed); documentation names them only in the files listed as history (ADRs, roadmap, §11, the failure archaeology, debug case studies, the Phase 14 campaign); every listed history file exists; a positive control of the pattern |
| default | `tests/unit/test_qt_runtime_pins.py` | `PyQt6` and `PyQt6-Qt6` are pinned exactly and equally, the lock holds exactly those versions, `qVersion()` equals the pin, and the Qt Quick 3D binding, DLL and QML module are in the installed wheels |
| default | `tests/unit/test_quick3d_boundary.py::test_the_spike_is_gone_and_nothing_names_it`, `test_quick3d_packaging.py::test_the_spike_left_the_bundle_with_l1_10` | the spike's package, flag and spec entries are gone |
| default | the drift guards in `test_scene3d_look.py`, `test_quick3d_pure.py`, `test_quick3d_qml.py`, `test_scene3d_mesh.py`, `test_scene3d_builders_primitives.py`, `test_board_probes.py`, `test_render_beauty_board.py`, `test_scene3d_ground_bake.py` | production equals the L0 spike's values, read from `tests/data/l0_spike_reference.json` |

- **Freeze a reference before deleting what produced it.** A drift guard that imports the code
  it guards against dies with that code. Run the producer once more, write what the guards
  compare with into a data file with its provenance, point the guards at the file, THEN delete.
  The freezer ran against an archive of the tree before the removal, not the working tree.
- **An absence gate reads what a clone contains, and is mutation-checked per kind of
  presence.** `test_no_qt3d_left` lists files with `git ls-files` — a stray build folder cannot
  fail it and an uncommitted file cannot hide from review. Measured when it was written: an
  import put back in `src/`, a pin in `pyproject.toml`, a hidden import in the spec, a
  self-test import in `main.py`, a lock entry in `pylock.toml`, a comment in `ci.yml`, a line
  in docs/05 and one in a skill each failed it (8 of 8), and each file restored passed.
- **History is a list of files, not a folder.** A directory-wide exemption (all of `docs/`)
  would let new prose describe the removed view as current; the gate names each history file
  with its reason, and only the ADR-048 evidence folder (measured runs, never edited) as a
  folder.

### 8.10.14 Render measurements after Plant Forge (#600, #603, #609, #626, #536)

Use `tests/integration/workspace_render_state.py` as the shared rest predicate:
controller records and ground settled, camera stationary, forge queue/in-flight
admission empty and no forge timer due. Capture the sink's admitted meshes for
the selection oracle, then run independent CPU rays. Rest wind at zero; pausing
a nonzero shader clock preserves displaced vertices. Wait again after a walk
restores its orbit camera because that also restores distance LODs.

A reload clears document-scoped forge admission; its upload budget includes the
v0 stage plus forged replacements for a full rebuild. Retaining SceneSync records
still re-admits forged plants. Assert zero uploads separately for an unchanged
pass inside one document. Always assert wait success before measuring a frame
or memory. G6 samples after two presented frames retire texture uploads; a grab
cannot substitute for presentation. Preserve its upper bound, statistic and
retained-texture control. A non-presenting display reports a bounded refusal.

Qt's application scale multiplies the screen scale. A test that specifically
needs DPR 1.25 pins screen scale 1 as well as application scale 1.25. Full windows
use the available desktop geometry. Test-driver startup can retry STARTING
refusals within one total deadline; do not extend the product host's idle wait.
See [the measurement report](../11-risks-and-technical-debt/audits/2026-10/3d-hardening-611.md).

### 8.10.15 Characterization and instruments after extraction (audit #392)

Before moving an implementation, characterize the actual UI/command workflow.
After moving it, keep the behavioral assertions and retarget AST censuses,
mutation scripts, import hooks and private spies to the defining module. An
export alias preserves object identity, not the global namespace a function uses.
Snapshot every binding an isolation helper changes; a fixed list can leak a new
shared resolver into the next test. A child settings hook intercepts
`config.settings`, before any store is constructed (ADR-041/068).

`test_audit_refactoring.py` drives all five real shape menus at 37/215 degrees,
checks exactly one undo step and exact duplicate restoration, and holds a queued
bridge call while shutdown verifies abort-before-join without pumping Qt.
`test_property_dispatch_workflows.py` drives every generic property branch through
its actual editor. Existing focus/debounce, line-preset, resize and gesture nets
remain part of the full suite. `test_startup_theme_refresh.py` verifies one
stylesheet write plus palette/native-frame refresh; it asserts work rather than
a machine-dependent millisecond number.

Run `benchmark_audit_performance.py` on a quiet runner for the representative
workloads. Timing data and unit gates are separate evidence: coverage tracing,
offscreen rasterization and other workers must be disclosed. The harness reports
all samples and explicit output dimensions; the evidence never substitutes an
old audit observation for a current result. See the quality requirements and
audit evidence for the command, machine and measured limitations.

## 8.11 Security Scanning (SAST)

**Tool:** [Bandit](https://bandit.readthedocs.io/) — a Python SAST tool that detects common security anti-patterns (subprocess injection, unsafe deserialization, weak cryptography, hardcoded secrets, etc.).

**CI enforcement:** The `security` job in `ci.yml` runs `bandit -r src/ --severity-level high` on every push. CI fails only on HIGH-severity findings. MEDIUM and LOW findings are omitted by this invocation. Use the separate all-findings command below for awareness; no broader scan is claimed.

**Dependency vulnerability scan (AUD-054, #454):** the `Dependencies` matrix job (Linux and
Windows) also runs `pip-audit` over the committed lock export
(`uv export --locked --all-extras --group build`, which by default also includes the dev
group), so a finding is a finding in a shipped artifact, a build tool or a development tool
that runs in CI; it runs on both platforms because pip-audit evaluates requirement markers
for the running interpreter (the Windows-only `pywin32` is invisible to a Linux-only scan).
No advisory is waived; any advisory fails the job.

*Fixed 2026-10-24 (#571, #572).* The job turned `master` red with no code change:
[GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w) (setuptools
< 84.1.0, low: a Windows path escape through `namespace_packages.txt` during a legacy wheel
installation; setuptools is in the build group and in the frozen bundle), and a re-run hours
later added six `filelock` 4.2.0 advisories (fixed in 4.2.1; dev extra only, through
`pip-audit` → `cachecontrol[filecache]`). Mitigation: the build group pins setuptools
**84.1.0** and a targeted `uv lock --upgrade-package setuptools --upgrade-package filelock`
moved only those two packages (filelock to 4.2.4); the frozen bundle's inventory, SBOM,
smoke and `--selftest` were re-verified in a local review build on the locked Python 3.11.9
environment (the PR's `frozen-selftest.yml` run repeats it on CI). 84.1.0 also contains
the 83.0.0 fix for GHSA-h35f-9h28-mq5c, so the one former waiver, `PYSEC-2026-3447`, ended
with it (a waiver that matches nothing would hide a widened advisory unreviewed). Lesson:
PF-CI-12.

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

**Work on what a plan file holds — two patterns (Phase 17 L1.1, #385, §8.29.1).** A plan file
is input: it can be edited by hand, and it can be hostile. Bandit sees none of this; it is a
review duty wherever geometry out of a plan is processed on the GUI thread, and the 3D pipeline
is where it was learned. A work bound had been added, a security review read the function it
sat in, and both of the following were wrong with it.

1. **Bound the input before the work.** The check stood *behind* the expensive step: the
   clipper had inflated the path and every ring it returned had been read before anything was
   refused. Ask what a step costs from what is known **before** it runs — a count the item
   already holds (its stored vertices, before one is read), a count that is itself cheap and
   itself paid for (the pairs of a path's segments that cross), the size of an answer before it
   is read (the rings a clipper returned). A library's own work is the hardest to see: pyclipper
   has no bound of its own, and its cost follows not the vertex count but how often the outline
   crosses itself and how many edges a sweep line carries at once — 800 scribbled vertices, well
   under a cap on vertices, took it ten seconds.
2. **Bound the sum, not the largest element.** The check judged the largest outer ring of a
   stroke; a stroke that comes back as many rings was never judged as a whole. Wherever a cost
   is a sum or a product — regions of an item, holes × outer rings, entries × their size in a
   cache — the bound belongs on that sum: one budget that every step pays into, not a limit
   that each element is held against alone. The same holds for memory: a cache bounded by its
   number of entries is not bounded when one entry can be a thousand times another.

How it is pinned matters as much: **no test of these reads a clock.** Each asserts what was —
or never was — called (`tests/integration/test_scene3d_snapshot.py::TestTheInputIsBoundedBeforeTheWork`,
`::TestOutlinesTooLargeToCut`): for every step of a stroke the budget it needs, to the unit, and
that with one unit less the step does not run. A time-out would have passed on a fast machine.
And price every quadratic by what it does, not by its size alone: the last hole found here was a
simplicity test priced at the square of its edges, which is right for an outline and a
hundredth of the truth for a ring whose every pair of edges lies close.

**A third pattern, from the ground bake (Phase 17 L1.5, §8.29.5): a number in the file is a
multiplier.** The two patterns above are about counts — vertices, rings. The bake's holes were
all about MAGNITUDES, which a count does not bound: two points 19 km apart are two vertices and
475,001 gravel dots (gravel's painter until L4's owner pass; a 5 cm chain-link path walks as many); a dashed pen makes as many dashes as its line is long; a furniture sprite is
rendered at its item's size — its area in pixels; a pen width near zero is a spacing near zero.
So: (a) ask of every step what it is PROPORTIONAL to — a length, an area, a ratio of two numbers
of the file — and bound that, by clipping the work to what can be seen before it is generated
(the walk along a styled path keeps its phase and generates inside the tile only) or by a floor
and a ceiling where the ratio enters; (b) what a shared window may cost — a tile — is one budget
for everything in it, charged for the work DONE (the steps walked to find an element, not only
the elements handed out), and a spent budget means "no more", never "no bound" (`if budget:` is
the bug); (c) no bound may sit behind bookkeeping that already paid: the per-tile caps were
applied when a tile was painted, after every record had been entered once per tile it touched —
2,050,003 entries for 50,000 whole-plan rectangles, 55,201 once a record's tiles are four
integers. The criterion these were judged by is stated at the top of the bake's cost table
(§8.29.5): the cost of what the file holds times a stated constant; no amplification; no bound
behind its work. Pinned by counts in `tests/integration/test_scene3d_ground_bake.py::TestHostilePlans`.

**… and a bound on counts is not a bound on time.** What a count costs is the library's to say,
and it varies by three orders of magnitude: Qt fills polygons whose outlines are wavy rings at
0.7 µs a vertex (262,144 vertices in one tile: 172 ms), and ONE polygon of 16,384 vertices in
19 s when it is a COMB whose every tooth crosses every scanline of the tile (1.2 ms a vertex; the
2D canvas needs 186 s for one paint of that item).
Where work runs on the GUI thread and its unit cost is not ours, add the bound only the caller
can keep: stop BETWEEN units for a time budget and leave the rest pending — the bake paints at
least one tile a call and looks at an injectable clock after each (§8.29.5). The budget does not
bound one unit; say what one unit was measured to cost at its worst, and do not round it down.

**Plan text in Qt's rich-text widgets and in the log (Phase 17 L1.3, #385).** A plan file is
input, and so is everything that quotes it — an item's name, and an exception's message that
repeats the name. Two consumers turn such text into something else, and Bandit sees neither:

- **Qt decides "rich text or plain" by looking at the string.** A tooltip, and a `QLabel` left on
  `AutoText`, render markup found in their text (`Qt.mightBeRichText`): a plant called
  `<b>x</b><img src="file:///C:/Windows/win.ini">` put a bold `x` and an image request into the
  tooltip of the "not shown in 3D" list.
- **A log line ends at a line break.** A name with `"\n2026-10-12 ERROR forged"` in it writes a
  line of its own into `app.log` — the file a user sends to support. A traceback's last line is
  the exception's message as it came.

The rule, and the one helper (`core/plain_text.py`, standard library only):

1. **Normalise, then cap, then escape — in that order.** `normalise_text` turns every character
   `str.splitlines()` splits at (LF, CR, VT, FF, FS, GS, RS, NEL, U+2028, U+2029) into ONE line
   break, a tab into a blank, and every other C0 / C1 control and the bidi overrides and
   isolates (U+202A–U+202E, U+2066–U+2069) into U+FFFD. The caps (`clip_text`: lines and
   characters; `clip_line`: one line) are applied to that normalised text — what the CONSUMER
   will see. The first version counted `"\n"` only, and a text broken with U+2028 passed a
   cap of 8 lines with as many lines as it liked. Only then `html.escape`, where the consumer
   renders rich text (`plain_tooltip`, in an explicit `<qt>` element). Each function reads a
   prefix of its input whose length depends on the cap alone.
2. **Labels that can show plan text are `Qt.TextFormat.PlainText`**, said out loud at
   construction; list rows stay plain through the default delegate (pinned with a hostile name).
3. **A log record that can quote the plan is ONE normalised, capped line** (`log_text`) at
   ERROR / WARNING; the traceback goes to DEBUG, which the log file does not record. This holds
   for the workspace's five modules. The scene contract's own records — the builder failure in
   `core/scene3d/sync.py`, the `record_failed` and refusal records in `ui/view3d/snapshot.py`
   — still attach the exception at ERROR or write its message as it came: that story's
   records, pinned by its tests, and an open item.
4. **Do not write invisible characters into source.** An editing tool turned three `\u`
   escapes into the characters themselves, in the very module that defines the separators.
   Named escapes (`\N{LINE SEPARATOR}`), and `tests/unit/test_plain_text.py` scans `src/` and
   `tests/` for characters a reader cannot see.

Pinned by `tests/unit/test_plain_text.py` (each separator in turn yields the same capped result;
the positive control — the old splitter — fails),
`tests/integration/test_view3d_workspace_widget.py::test_a_hostile_name_is_shown_as_its_characters_everywhere`
(checked against Qt's own renderer, with the unescaped string as the control) and
`tests/integration/test_view3d_sync_controller.py::test_an_engine_error_that_quotes_the_plan_is_one_log_line_per_event`.

**Agent API exposure (US-D1.1, §8.19):** the embedded MCP server is a network listener. It is **on by default but read-only** and **bound to `127.0.0.1` only** (never `0.0.0.0`/LAN — so Bandit's B104 does not apply); a Preferences toggle disables it. Default-on is acceptable while read-only (a garden layout isn't sensitive) and removes the discovery friction for AI clients. Reads have no auth (loopback trust). **Writes (US-D2.0 through D2.6, including `undo`/`redo`) are token-gated**: the scene-mutating tools ship only when the user enables editing (off by default) AND require the token — presented in the connect URL as a `?token=` query param (the reliable route; some clients don't transmit auth headers on tool calls) or as an `Authorization: Bearer <token>` header — checked with constant-time comparison. A default-on, unauthenticated *mutate* surface reachable by any local process is exactly what this prevents (ADR-036, §8.19); delivering the token in the URL keeps that protection (a caller still needs the secret) at the cost of a URL-borne secret — mitigated by disabling the uvicorn access log and stripping the `token` param from the request scope right after extraction, so the residual exposure is the client's own config. The gate is per-tool so read-only clients are unaffected. The pre-bind port check uses a plain `socket.bind` and is not a high-severity finding.

**Browser reachability (DNS rebinding) — #396, ADR-033 addendum.** Loopback binding and token gating reason about a *local process* (an MCP client the user launched). They do not cover a **browser**, which is a local process acting for a remote page: a page on `evil.example` can reach `http://127.0.0.1:8765/mcp`, and loopback binding does not stop it because the request originates on this machine. The only barrier is the transport's `Host`/`Origin` validation, so that guard is now **explicitly configured by OGP** rather than inherited from the mcp SDK:

- `agent_api/server.py::build_server(..., host=..., port=...)` constructs `TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...], allowed_origins=[...])` and passes it to `FastMCP(transport_security=...)`. The lists name the **exact** `host:port` pairs (bind address, `127.0.0.1`, `localhost`, the IPv6 loopback literal) with **no `:*` port wildcard** — the port is fixed for the server's life, so a wildcard would only restore the breadth of the SDK default being replaced.
- A hostile `Host` is answered **421**; a hostile `Origin` **403**. Verified against the frozen exe, not only in pytest: loopback `Host` 200, `localhost` 200, `evil.example` 421, loopback `Origin` 200, `http(s)://evil.example` 403.
- **The `mcp>=1.23` dependency floor is a security control, not a version bump.** 1.23.0 is the first release whose FastMCP auto-enables the loopback guard. Measured: under the previous floor (`>=1.12`) a 1.22.0 wheel answered a crafted `Host: evil.example` initialize with **HTTP 200 and a full MCP result**, across all six hostile variants, where 1.30.0 answers 421/403. No shipped exe is known to be exposed — every release happened to bundle a 1.30-era wheel — but the exposure was a property of *whichever wheel resolved at build time* rather than of the product.
- **Test-design consequence.** The black-box 421/403 tests are necessary but not sufficient: with mcp 1.30.0 installed they pass *even with the explicit settings deleted*, and so does a naive "settings object is not None and the flag is True" assertion, because the SDK auto-enable returns exactly such an object. `tests/integration/test_agent_api_dns_rebinding.py` therefore also asserts what the SDK default cannot satisfy — that `allowed_hosts` names the **bound port**, and that nothing is a wildcard. Deleting the `transport_security=` argument fails 3 of its 4 object-level tests.
- **Reads remain unauthenticated** (loopback trust, the audit's challenged decision C2). This closes the *browser* vector; it does not re-open that one. The #355 input boundary additionally rejects non-finite/null/oversized callout offsets before Qt construction, so an authenticated caller cannot turn a write token into unbounded scene geometry. D2.6 reuses the same finite/canvas-relative reachability check for absolute positions and vertices before constructing `QPointF` geometry.


### Temporary files: never a predictable name in the shared temp directory (CWE-377)

Found in review of Phase 17 L1.2 (#385): the 3D self-test wrote its log to
`tempfile.gettempdir() / "OpenGardenPlanner-selftest-3d.log"`. On Windows `%TEMP%` is per user;
on Linux `/tmp` is shared, and a file with a known name there can be created or symlinked by
another local user before the app writes it. Bandit does not flag this form (it reports
`tempfile.mktemp`, not a fixed name joined to `gettempdir()`), so it is a review rule:

- **A log or a diagnostic file goes into the app's ONE per-user log directory** —
  `core.logging_config.resolve_log_dir()`, where `app.log` and `crash.log` live. Reuse the
  helper; do not compute a second path. That directory hangs on Qt's application identity
  (`QStandardPaths.AppDataLocation`), so code that runs before `main()` has named the application
  (the `--selftest` path) must name it first — `main._run_selftest` does, and leaves an existing
  application's identity alone.
- **A real scratch file goes into `tempfile.mkdtemp()` / `TemporaryDirectory()`** (an
  unpredictable name, mode 0700) and is removed afterwards.
- **Tests never write under a real user location**: they pass an explicit path
  (`OGP_SELFTEST_LOG`), or give the child process a user profile of its own
  (`quick3d_render_support.isolated_env`, §8.10.8). A throwaway application NAME is not
  enough — the first version of this rule said it was: the directory is then still created in
  the developer's real profile, under that name (found in review round 2; on Windows
  `QStandardPaths` follows `USERPROFILE`, not `APPDATA`). A test that lets the app resolve a
  per-user path first asks Qt where it would be, which creates nothing, and stops unless the
  answer is inside its own profile.

Pinned by `tests/unit/test_quick3d_selftest.py`
(`test_nothing_in_the_engine_package_writes_into_the_temp_directory`,
`test_the_selftest_writes_its_log_beside_the_apps_logs_not_into_temp`).

## 8.12 Constraint Solver Architecture

The constraint solver lives in [`core/constraints.py`](../../src/open_garden_planner/core/constraints.py) and [`core/constraint_solver_newton.py`](../../src/open_garden_planner/core/constraint_solver_newton.py). It supports 17 constraint types and runs in two phases.

### 8.12.1 Constraint types

Defined in `ConstraintType`. Grouped by the invariant they express:

| Category | Types |
|---|---|
| Dimensional (scale-sensitive) | `EDGE_LENGTH`, `DISTANCE`, `HORIZONTAL_DISTANCE`, `VERTICAL_DISTANCE`, `POINT_ON_CIRCLE`, `ANGLE` |
| Positional | `COINCIDENT`, `POINT_ON_EDGE`, `SYMMETRY_HORIZONTAL`, `SYMMETRY_VERTICAL`, `FIXED` |
| Orientation (scale-invariant) | `HORIZONTAL`, `VERTICAL`, `PARALLEL`, `PERPENDICULAR`, `EQUAL` |
| Contact direction | `TANGENT` (edge perpendicular to radius at contact; paired with `POINT_ON_CIRCLE`) |

### 8.12.2 Two-phase solve

Every `solve_anchored` call runs in two phases:

1. **Gauss-Seidel warm start** — each constraint is resolved by a 1D projection along its own direction. Cheap, robust for decoupled systems, converges in O(N) iterations when the constraints don't share variables in geometrically independent directions.
2. **Newton-Raphson refinement** — runs when the Gauss-Seidel residual exceeds tolerance. Treats the free variables as a single vector `x`, builds a residual vector `F(x)` from all non-orientation constraints, and takes damped Newton steps on `J · Δx = −F`. The Jacobian is computed numerically via central differences (`h = 1e-3 cm`); the step uses `numpy.linalg.lstsq` so rank-deficient systems yield a minimum-norm step. Armijo backtracking (α halves per failed step) accepts only moves that strictly reduce `max|F|`.

Convergence criterion: `max|F| ≤ tolerance`. `solve` defaults to 0.1 cm and 20 warm-start iterations; `solve_anchored` defaults to 1.0 cm and 10. Newton defaults to 25 iterations and 15 backtracks. Caller tolerances govern the final physical error. With no movable variables, evaluate the fixed-state residual before reporting feasibility (#457).

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
    log_harvest: QAction | None = None        # US-C1
    plan_succession: QAction | None = None

def build_bed_context_menu(
    self, menu: QMenu, *, grid_enabled: bool,
    supports_grid: bool = True, supports_soil: bool = True,   # supports_soil: US-C3b
) -> BedMenuActions: ...

def dispatch_bed_action(self, action: QAction | None, actions: BedMenuActions) -> bool: ...
```

`supports_grid=False` drops the grid toggle (round/vertical shapes); `supports_soil=False` drops **only** the soil-test action (the trellis — a plant-parent that holds no soil — keeps pest/harvest/succession). Every **plant-parent** shape's `contextMenuEvent` follows the same skeleton (the guard is `is_plant_parent_type`, not `is_bed_type`, so the trellis is included — US-C3b):

```python
bed_actions = BedMenuActions()
if is_plant_parent_type(self.object_type):
    soil = is_bed_type(self.object_type)   # trellis → False; beds/containers → True
    bed_actions = self.build_bed_context_menu(
        menu, grid_enabled=self._grid_enabled,
        supports_grid=soil,                # round shapes pass False regardless
        supports_soil=soil,
    )
# ...assemble the rest of the menu...
action = menu.exec(event.screenPos())
if self.dispatch_bed_action(action, bed_actions):
    return
# ...handle shape-specific actions...
```

**Why a mixin method, not a base class.** `GardenItemMixin` is already shared by all four shapes; adding methods there avoids a deeper refactor and keeps the change minimal. The mixin handles `request_soil_test`, `request_pest_log`, `request_harvest_log`, `request_succession_plan` view dispatch and the grid-toggle side effect (`scene.selectionChanged.emit()`) so each shape only has to translate its surrounding non-bed menu items.

**Regression test (the part that prevents recurrence).** `tests/integration/test_bed_context_menu.py` parametrises across every plant-parent shape (incl. containers + trellis) and asserts the soil-test is present iff `supports_soil`:

```python
@pytest.mark.parametrize("factory,supports_grid,supports_soil", BED_SHAPES)
def test_bed_context_menu_has_all_features(factory, supports_grid, supports_soil, qtbot):
    item = factory()
    menu = QMenu()
    actions = item.build_bed_context_menu(
        menu, grid_enabled=False, supports_grid=supports_grid, supports_soil=supports_soil)
    assert actions.log_pest_disease is not None
    assert actions.log_harvest is not None
    assert actions.plan_succession is not None
    assert (actions.add_soil_test is not None) == supports_soil   # trellis → None
    assert (actions.toggle_grid is not None) == supports_grid
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

**Update (US-C3 — containers join the soil predicate).** `is_bed_type()` is now the **soil-capable** predicate, not literally "bed": it returns true for `GARDEN_BED`, `RAISED_BED`, **and** the container types `CONTAINER`/`CONTAINER_ROUND`/`WALL_PLANTER`. So containers ride the same `build_bed_context_menu` path and bed-feature playbook above with no extra work. The parent/relationship behaviour (reparenting, drag/copy propagation, "Contained Plants", **and the bed-style context menu**) gates on a second predicate `is_plant_parent_type()` = soil containers **plus** `TRELLIS` (a plant-parent that holds no soil). When adding a feature, pick the predicate by seam: soil → `is_bed_type`; parent/relationship → `is_plant_parent_type`. The four shape items call `build_bed_context_menu(..., supports_grid=…, supports_soil=…)` under an `is_plant_parent_type` guard; for the trellis both flags are `False` (via `is_bed_type(self.object_type)`), so it shows **Pest / Harvest / Succession** but no Grid / Soil-test (US-C3b). The **grid overlay** stays purely on `is_bed_type` — a grid on a vertical surface is meaningless. Container fill is measured by height in litres via the Qt-free `core/container_model.py` (not bed soil-depth). See ADR-031.

## 8.15 Google Maps API Key for the Satellite Background Picker (ADR-019)

**Worker shutdown.** `MapPickerDialog` must never call `QThread.wait()` for the Static Maps worker: a single `requests.get(timeout=10)` cannot observe interruption until the response or timeout. The dialog's `reject()` and `closeEvent()` paths share one asynchronous cancellation request and the dialog rejects only from the worker's terminal signal; `GardenPlannerApp` tracks the modal picker so application shutdown enters the same path. Unexpected exceptions are logged only after formatting and `_scrub_key()` redaction; the user-facing message remains generic. `tests/integration/test_map_picker_dialog.py::TestFetchFlow::test_close_does_not_block_on_in_flight_worker` pins the non-blocking lifecycle and `test_worker_logs_scrubbed_traceback_for_unexpected_failure` pins secret exclusion.

**What needs the key.** The "File → Load Satellite Background…" menu opens `MapPickerDialog`, which uses two Google Maps Platform APIs:

| API | Used for | Free tier |
|-----|----------|-----------|
| Maps JS API | The embedded picker map (display + drawing + Places Autocomplete) | Free for display in apps (no $200 credit deduction) |
| Static Maps API | The final satellite image fetch (1–9 calls per import, depending on bbox size) | $200/month credit → ~100k calls free |

**Key location, in priority order:**

1. A non-empty key in `Preferences`, stored at `api_keys/google_maps_key` in the application's per-user QSettings store.
2. `OGP_GOOGLE_MAPS_KEY` from the process environment. In a source checkout, `main.py` loads this from the project-root `.env`; a packaged build also supports an adjacent `.env` next to the executable.

Preferences takes precedence. Leaving the Preferences field blank keeps the environment/`.env` fallback active; clearing a previously saved value therefore restores that fallback. The key is never copied from the environment into QSettings.

When the key is absent, the menu item is disabled and its tooltip explains where to set it. There is no fallback to a different provider — the dialog is unavailable until the user provides a key.

**One-time setup (developer):**

1. Sign in to <https://console.cloud.google.com/> with the Google account that should pay for any overage.
2. Create a project ("Open Garden Planner Dev").
3. Enable the three APIs the dialog needs: **Maps JavaScript API**, **Places API**, **Maps Static API**.
4. *Billing → Budgets & alerts*: create a budget alert at €1/month so you get pinged if anything ever escapes the $200 free credit.
5. *APIs & Services → Credentials*: create an API key. Restrict it: **API restrictions** = the three APIs above only. **Application restrictions** can stay on "None" for desktop use (HTTP-referrer/IP/Android-package restrictions don't apply to a `.exe`).
6. Put the key in Preferences, or use the environment fallback. For a source checkout, the latter can be the project-root `.env`; for a packaged build, place `.env` next to the executable:

   ```dotenv
   OGP_GOOGLE_MAPS_KEY=AIza...
   ```

**Never bundle the key into the release `.exe`.** Anything pinned into the PyInstaller binary can be extracted with `strings` and abused on your bill. Specifically:

- The CI release workflow must NOT inject the secret into the build artifact.
- A GitHub-Action secret is only safe if it stays in CI (e.g. for an integration test) and never ends up in the shipped `.exe`.
- Distributing the key to other users requires them to obtain their own (cheap, ~5 minutes via the steps above).

**Mosaic vs single call.** The Static Maps API caps a single image at 640×640 base × 2 scale = 1280×1280 effective pixels. For typical garden-sized bboxes (≤ ~200 m on a side at high latitudes) one call is enough; for larger areas `google_maps_service.fetch_bbox` falls back to a 2×2 or 3×3 mosaic at the highest zoom that fits the configured `_MAX_GRID = 3` budget (`pick_zoom_and_grid`). Resulting image is stitched with Pillow before reaching the canvas as a single `BackgroundImageItem`.

**Pixel→meter scale is analytical.** Because Static Maps uses Web-Mercator with a known tile pixel size, the scale of the returned image is `mpp = cos(lat) × 2π × 6378137 / (256 × 2^zoom)`. The new `BackgroundImageItem(geo_metadata=…)` constructor reads `meters_per_pixel` from this dict and sets `_scale_factor = 0.01 / mpp` (px-per-cm) automatically — no calibration click. The existing manual calibration (`Calibrate Scale…` context menu) is still available as an override; on reload, a saved `scale_factor` wins over the geo-derived one.

### 8.15.1 Manual background-image calibration and exact dimensions

Manual calibration is available on the imported image itself, not on the
empty canvas. After importing an image, right-click the image and choose
**Calibrate Scale…**. Click the two endpoints of a feature whose real distance
is known, enter that distance in centimetres, and press **Enter** to apply the
scale. Press **Esc** to cancel the inline calibration instead.

For exact geometry, use the numeric fields in the **Properties** panel:

- rectangles: **Size (W/H)**;
- circles: **Diameter**;
- ellipses: **Semi-axes X** and **Y** (the corresponding width and height are
  twice those values).

Polygons and polylines currently do not have an overall numeric width/height
editor. For those shapes, use typed coordinates or edge-length constraints
when precision matters. These workflows complement manual image calibration:
calibrate the background first, then enter exact geometry values or constrain
the relevant edges.

**QtWebEngine import timing.** `from PyQt6 import QtWebEngineWidgets` must run *before* `QApplication(...)` is created — Qt enforces this so it can configure OpenGL sharing. `main.py` does this at module level. Tests that exercise the dialog must either match the same ordering or use a `QWidget` stand-in for `QWebEngineView` (see `tests/integration/test_map_picker_dialog.py::_DummyWebView`).


## 8.16 Typed Coordinate Input + Unified Snap Engine (Package A — ADRs 020 + 021)

This concept covers four user stories that ship together in Phase 13: relative input `@dx,dy`, polar input `@dist<angle`, midpoint + intersection snap, and the Dynamic Input cursor overlay. The architecture decisions live in **ADR-020** (snap engine) and **ADR-021** (input pipeline); this section captures the cross-cutting *rules* a developer must follow when extending either system.

### 8.16.1 Snap engine layering

* `core/snap/` is the orchestration layer. It does **not** own any geometry — every provider delegates to `measure_snapper.get_anchor_points` or to `core/snap/geometry.item_edges`. Do not duplicate point enumeration; if a new anchor type is needed, add it to `AnchorType` first and a provider second.
* Every provider has a `priority`. Lower wins on ties. Defaults: endpoint 10, intersection 15, center 20, midpoint 30, edge 40. When tuning, remember that two candidates within sub-pixel distance frequently exist (e.g. a corner is also two edge endpoints).
* The `QuadTree` is rebuilt lazily by `CanvasView._ensure_snap_index()` on the first snap query after `QGraphicsScene.changed` fires. Do **not** rebuild eagerly on every signal — for thousand-item gardens the build cost (~3 ms) dominates if you do.
* Items spanning multiple quadrants are inserted into every overlapping child rather than parked at the parent; `_query` collects them via an `id()` set so duplicates never surface. Keep this in mind when changing `_insert_into_children` — switching to a "store at parent" strategy is also valid but must be paired with removing the dedup set.
* `PointSnapper.snap()` widens the query window to `4 × threshold` so that intersection candidates from edges starting outside the cursor area still surface. If you raise the threshold drastically, also revisit `MAX_SEGMENTS_PER_QUERY = 60` in `providers/intersection.py` — the O(n²) intersection step is the soft ceiling.

### 8.16.2 Drawing-tool integration

* `CanvasView._maybe_apply_anchor_snap(tool, scene_pos)` is the single entry point. It runs *before* the tool's `mouse_press/move/release`. Tools that own their anchor logic — `SelectTool`, `MeasureTool`, every `ConstraintTool` family member — set `BaseTool.skip_anchor_snap = True` to opt out (the previous string-prefix match on `tool_type.name` is gone). When adding a new tool that does its own anchor picking, set the flag; otherwise leave it `False` and the dispatcher will apply Package A point snap automatically.
* **Composition rule with grid snap**: `CanvasView.snap_point()` short-circuits the grid-rounding step when `_current_snap is not None`, so an anchor-snap match always wins over grid snap on the click path. Tools may still call `view.snap_point(scene_pos)` defensively — when the dispatcher matched a midpoint/intersection/endpoint, that call is a no-op apart from the canvas-bounds clamp. Do NOT short-circuit the snap inside the tool: the dispatcher is the single owner of this decision.
* The current snap candidate is rendered by `_draw_point_snap_glyph` in `drawForeground`. Glyph mapping is intentionally pictographic and lives in one switch: square = endpoint, circle = center, triangle = midpoint, X = intersection, dot = edge. Add a new kind by extending `SnapCandidateKind` *and* `_draw_point_snap_glyph`; reviewers will reject a half-done mapping.

### 8.16.3 Typed-input invariants

* There is exactly **one** `CoordinateInputBuffer` per `CanvasView`. Both the status-bar field and the Dynamic Input overlay subscribe to its signals; they must never own buffer state of their own. If you add a third surface (e.g. a command palette), wire it the same way.
* The buffer's `anchor` is refreshed by `CanvasView.refresh_input_anchor()`. It is called after every `set_active_tool`, `mouse_press`, `mouse_release`, `mouse_double_click` and `key_press`. Add a new lifecycle hook? Add the refresh call.
* The Y-flip lives **only** in `parser.py`. The user-entered Y is math-positive (up); the parser converts to scene Y (down). Adding a second flip site elsewhere will break relative input in subtle, locale-specific ways.
* The smart decimal/separator rules (A–F) in the parser docstring are not negotiable per call site — they are global. When extending the grammar (e.g. a future `@3,4@2` array-along-path syntax), add a new rule **before** D and write a regression test that covers the same ambiguous input under both old and new rules.

### 8.16.4 Adding typed-coordinate support to a new drawing tool

Three steps, no more:

1. Override `last_point` to return the current anchor (`None` outside an active draw sequence).
2. Override `commit_typed_coordinate(point)` to perform the same action a left click at `point` would, **without** re-applying grid snap (the user has typed exact coords).
3. If the tool finalises on the second click (rectangle/circle/ellipse pattern), call `_reset_state()` and return `True` from `commit_typed_coordinate` after finalisation so `last_point` becomes `None` again.

The integration tests in `tests/unit/test_tool_typed_input.py` cover this contract; a new tool must add a similar parametrised test case.

### 8.16.5 Dynamic Input overlay visibility — three hard rules

The floating overlay is *visible* only when **all** of:

1. `dynamic_input_enabled` is True (View menu / settings).
2. The active tool exists and is not SELECT.
3. The tool's `last_point` is **not** `None` (no anchor → no polar/relative makes sense).

Any other state must hide the overlay. The implementation lives in `CanvasView._update_dynamic_overlay`. If you add a new hide-condition, do it there; do not add visibility logic inside the overlay widget itself — it has no knowledge of the active tool by design.

## 8.17 Sidebar Accordion — Hover-Peek + Click-to-Toggle (ADR-030, issue #226)

The right sidebar is an accordion owned by `SidebarController` (`ui/widgets/panel_stack.py`). It is the single source of truth for every panel's state; `CollapsiblePanel` is a dumb show/hide-and-tween primitive underneath it.

> The first cut used a bottom `QSplitter` that pinned panels *reparented* into (equal-share, draggable). It failed manual testing — opening a panel made it jump to the bottom (reorder), there was no animation, and selection-opened panels were unclosable. This section documents the **revised** model (ADR-030 addendum): one scrollable layout, no reparenting, animated, click-toggles.

### 8.17.1 The state machine

Each panel is `COLLAPSED`, `PEEKING`, or `PINNED`, with a `PinSource` of `USER` or `SELECTION` when open:

- **COLLAPSED** — content hidden; `setMinimumHeight(0)` **then** `setMaximumHeight(header_height())`. Reset the minimum *before* clamping the max.
- **PEEKING** — hover-opened (auto-collapses on leave); content grows to its size.
- **PINNED** — click- or selection-opened; stays open until the title is clicked again. `USER` (click) survives a selection clear; `SELECTION` (auto) is collapsed when the selection no longer matches.

`is_open(key)` ⇔ state ∈ {PEEKING, PINNED}. Clicking the title of **any** open panel collapses it (see §8.17.5).

### 8.17.2 Layout: one scrollable stack, no reparenting

```
SidebarController → QVBoxLayout
  └── QScrollArea (setWidgetResizable, h-scrollbar off)
        └── inner QWidget → QVBoxLayout(spacing 2)
              ├── CollapsiblePanel × 9   # ALWAYS here, fixed canonical order
              └── addStretch()           # last; keeps bars top-aligned when short
```

**Panels are never reparented** — a state change only adjusts the panel's height clamp, so opening/closing one can never reorder the list (the reported bug). There is no splitter and no draggable divider.

**Open panels fill the surplus space.** An open panel's floor is its content height (`setMinimumHeight(sizeHint)`, set on open) and it carries a **content-weighted layout stretch factor** (`setStretchFactor(panel, sizeHint().height())`); collapsed panels have stretch 0 and are clamped to the header. So:
- One panel open → it absorbs all the surplus and fills the sidebar (no empty gap at the bottom — the reported polish item). A panel with an internal scroll area (e.g. Plant Details) thus reveals more of its content.
- Several open → each gets at least its content height, and the leftover surplus is shared **weighted by content size** (the panel with more to show gets proportionally more, instead of an equal half a light panel can't fill).
- Combined content exceeds the viewport → the `QScrollArea` scrolls (the minimum heights force the inner widget past the viewport; the trailing `addStretch()` contributes 0 height, so scroll engages) and each panel sits at its content height.

The stretch is set **after** the content is revealed (`set_expanded(True)` first) so `sizeHint()` reflects the content, not the header-only collapsed height. The minimum is set only **after** the open animation finishes (during the tween it stays 0, else a min above the animating `maximumHeight` would jump the panel).

### 8.17.3 Animation (organic expand/collapse)

Each panel owns a lazy `QPropertyAnimation` on `maximumHeight` (`CollapsiblePanel.animate_expand`/`animate_collapse`, ~160 ms `InOutCubic`):
- **Expand**: `set_expanded(True)` first so the content is visible and `sizeHint()` is valid, then tween the clamp `header → sizeHint`; on finish release the clamp to `QWIDGETSIZE_MAX` so the panel tracks later content-size changes (e.g. a list populating after `update_for_plant`).
- **Collapse**: flip the chevron + logical state immediately (responsive, and keeps `is_expanded()` correct for tests/state), keep the content widget *visible* during the shrink so it is drawn clipped, tween `height → header`, and hide the content on finish.
- `_restart_anim` stops any running tween and reconnects a fresh `finished` handler, so rapid open↔close toggles are safe. `expand_now`/`collapse_now` are the non-animated variants used at startup and `collapse_all()`.

### 8.17.4 Debounce + anti-flicker (hover-peek)

Two controller-level single-shot timers — open (~140 ms) and close (~220 ms, longer so a fast diagonal sweep to the canvas doesn't cascade-peek). The pointer leaves only one bar at a time, so a single `_pending_open_key` / `_pending_close_key` suffices; re-entering a bar cancels its pending close. `PINNED` panels ignore hover. Timer slots re-fetch the entry via `.get(key)` and bail on `None`; `start()`/`stop()` are wrapped in `contextlib.suppress(RuntimeError)` (teardown-safe).

> **Deliberate sharp edge:** the content widget is a *sibling* of `_HeaderFrame`, not a child, so moving the pointer from the header down into a peeked panel's body fires the header's `leaveEvent` and schedules the close — a peek can collapse while the pointer is over its content. This is intentional: peek is transient (the tooltip says "Click to keep open", and a click pins it), and the asymmetric debounce is tuned for the sweep-to-canvas case. Do **not** "fix" it by widening the hover region to include the body — that would break the fast-sweep behaviour.

### 8.17.5 Click-toggle + selection dismissal

`_on_title_click`:
- **PINNED** → collapse. If it was `SELECTION`-opened, set `selection_dismissed = True` so it does **not** re-open on the next selection *re-notify* (a scene move / undo fires `set_selection_pinned(True)` again for the same selection).
- **PEEKING** → promote the hover-peek to a sticky `USER` pin (already open).
- **COLLAPSED** → open as a `USER` pin.

`set_selection_pinned(key, True)` opens as `SELECTION` *unless* `selection_dismissed`. `reset_selection_dismissals()` clears all dismissals and is called from `application._on_selection_changed` (wired to `selectionChanged` **before** the `_update_*_panel` slots), so a genuine selection change re-opens the contextual panels for the newly selected item. When wiring a selection signal to a contextual panel, keep the panel's own content-update call (`set_selected_items` / `update_for_plant` / `update_for_bed`), then call `set_panel_visible(key, relevant)` **and** `set_selection_pinned(key, relevant)`.

### 8.17.6a Contextual-panel visibility

Plant Details / Companion / Crop Rotation have nothing to show unless a matching item is selected, so their **bar is hidden entirely** when irrelevant (they are NOT left as empty collapsed bars the user could open onto a placeholder — this restores the pre-US-226 `setVisible(False)` behaviour). `set_panel_visible(key, visible)` is **orthogonal** to open/collapse: hiding (`visible=False`) cancels any pending hover, collapses the panel instantly (so it reopens clean) and `setVisible(False)`s it (a hidden widget takes no layout space); showing re-adds the bar. The three panels are hidden at startup in `_setup_sidebar` and toggled by the selection updaters via `show_panel`. Non-contextual panels are never hidden. `_fill_target` and the surplus share ignore hidden panels (they occupy no space).

### 8.17.6 The dynamic-property QSS gotcha

`set_visual_state(state)` sets a `panelState` dynamic property (`collapsed`/`peeking`/`pinned`) — but Qt does **not** re-evaluate property selectors until you `style().unpolish(w); style().polish(w)`. The header is styled via `CollapsiblePanel[panelState=…] > QFrame`, so **both** the panel and its header must be re-polished (re-polishing only the parent leaves the child header stale). Peeking = accent border; pinned = 3 px left accent rail; collapsed has a cheap `:hover` highlight for instant affordance before the peek debounce commits.

### 8.17.7 No persistence

Startup is always fully collapsed; pin/peek/dismissal state is never saved. The `UiStateStore` panel-state helpers were removed (window geometry + the horizontal `main` splitter are still persisted).

## 8.18 Smart Symbol Authoring (US-C4)

Smart symbols are **parametric blocks** defined in JSON. Bundled definitions
live in `resources/data/smart_symbols/*.json`; users add their own by dropping a
file in `<app-data>/smart_symbols/` (it appears in the **Smart Symbols** panel on
next launch). See ADR-032 for the architecture.

**File shape** (one symbol per file; `id` should match the filename):

```json
{
  "id": "raised_bed_rows",
  "version": 1,
  "name": "Raised Bed (rows)",
  "name_de": "Hochbeet (Reihen)",
  "category": "beds",
  "parameters": [
    {"name": "L", "type": "length", "label": "Length", "label_de": "Länge",
     "default": 200, "min": 20, "max": 1000, "unit": "cm"},
    {"name": "W", "type": "length", "label": "Width", "default": 100},
    {"name": "rows", "type": "number", "label": "Rows", "default": 4, "min": 1, "max": 20}
  ],
  "elements": [
    {"kind": "rect", "x": 0, "y": 0, "w": "L", "h": "W"},
    {"repeat": {"var": "i", "from": 1, "to": "rows - 1"},
     "element": {"kind": "line", "x1": 0, "y1": "W * i / rows", "x2": "L", "y2": "W * i / rows"}}
  ]
}
```

- **Parameters** — `type` is `number` (integer spin), `length` (float spin, with
  optional `unit`), or `choice` (`choices: [...]`, combo). `name`/`name_de` and
  per-param `label`/`label_de` provide localisation (German falls back to
  English); these are **data strings**, not Qt `tr()`.
- **Elements** — `kind` ∈ `rect{x,y,w,h}`, `line{x1,y1,x2,y2}`,
  `polyline{points:[[x,y],…]}`, `polygon{points}`, `circle{cx,cy,r}`. Every
  coordinate is a number **or** an arithmetic **expression string** over the
  parameters (and the active `repeat` variable `i`). A `repeat{var,from,to}`
  block (inclusive integer range; endpoints may be expressions) emits its inner
  `element` once per value.
- **Expressions** are evaluated by `core/parametric_eval.safe_eval` — `+ - * / %
  ** //`, parentheses, parameter names, and `min/max/abs/round/floor/ceil/sqrt`.
  Anything else (attribute access, arbitrary calls, unknown names) is rejected:
  symbol files are treated as untrusted input, never `eval()`'d. All param values
  are coerced to **float**, so a parameter cannot be used as the `ndigits` arg of
  `round(x, n)` (that needs an int — `round(x, rows)` raises and the symbol falls
  back to cached geometry). Keep expressions small: an over-complex or deeply
  nested formula is rejected (a node-count cap guards against stack-exhausting
  input); coordinate formulas are a few terms, not a program.
- **Versioning** — bump `version` when a definition changes incompatibly. A
  saved plan stores the instance's `version`; on load, a mismatch (or a missing
  definition) falls back to the cached geometry embedded in the file and logs a
  warning, so old plans never break.

`tests/unit/test_smart_symbol_schema.py` validates every bundled file in CI
(loads, validates, every expression parses, generates ≥1 primitive).

## 8.19 Agent API — Embedded MCP Server & Thread Marshaling (US-D1.1–D1.6, D2.0–D2.6, D3.1–D3.4, ADR-033/034/035/036)

The app can host an **MCP server over streamable-HTTP** so AI agents read the
plan currently open in the GUI and, behind the D2 write gate, edit it (epic
#237). Package: `agent_api/`
(`bridge.py`, `server.py`, `schema.py`, `mapping.py`, `queries.py`,
`diagnostics.py`, `prompts.py`, `creates.py`, `edits.py`, `render.py`, `exports.py`,
`providers.py`, `__init__.py`).

**Lifecycle.** `AgentApiServer` builds a `FastMCP`, takes its
`streamable_http_app()` ASGI app, and runs a `uvicorn.Server` we own on a
**daemon `threading.Thread`** with its own asyncio loop. `start()` pre-binds the
port (precise `PortInUseError`) then polls `server.started`; `stop()` sets
`should_exit` and joins. **On by default** (`AppSettings.agent_api_enabled`
default **True**, `agent_api_port` default 8765; a Preferences toggle disables
it), **auto-starts on launch**, bound to **127.0.0.1 only**. Wired in `application.py`:
`_setup_agent_api` (deferred auto-start) / `_on_preferences` (live restart on
toggle/port change) / `closeEvent` (stop).

**Thread-marshaling boundary (`MainThreadBridge`).** Tool handlers run on the
server thread and must never touch Qt directly. `run_on_main(fn)` emits a
`QueuedConnection` signal carrying `(fn, Future)`; the slot runs `fn` on the main
thread and resolves the future; the worker blocks on `future.result(timeout)`.
This is the reusable, write-ready core (D2 edit tools route through it the same
way reads do).

**Pitfall — sync vs async tool dispatch (verified mcp 1.28.1).** The SDK runs a
**sync** tool handler *inline on the event loop*; only `async` handlers yield it.
So a Qt-touching tool MUST be `async def` and offload the blocking main-thread hop
to a worker: `await anyio.to_thread.run_sync(snapshot_provider)`. A sync handler
calling `run_on_main` would block the uvicorn loop on `future.result()`.

**Pitfall — shutdown deadlock.** During `closeEvent` the main thread stops pumping
the Qt loop (it's in `stop()`'s `join`), so an in-flight `run_on_main` could hang.
`MainThreadBridge.abort_pending()` (called *before* `server.stop()`) fails any
in-flight hop immediately so the handler returns and the join completes fast.

**Read model (ADR-034).** Reads go through `ProjectManager.snapshot_dict()` — an
in-memory, read-only `.ogp`-shaped dict (it does NOT run the journal-pin sync that
`save()` does, so reading never mutates state). The Qt-free `mapping.py` maps it to
the curated pydantic `schema.py` (`PlanSummary`); object classification inlines the
bed/plant `ObjectType` name sets, drift-guarded by `tests/unit/test_agent_api_mapping.py`.

**Read/query tools (US-D1.2).** `build_server`/`AgentApiServer` take an
`AgentProviders` bundle (Qt-free) of main-thread-marshaled callables (`snapshot`,
`diagnostics`) — the extension seam for render/export/write later. Tools:
- **Structural/spatial** — `list_objects`, `get_object`, `objects_in_region`,
  `objects_in`, `plants_in_bed`, `nearest_objects`, `measure_distance` are pure
  functions over the snapshot (`agent_api/queries.py`, Qt-free, **linear scan** not
  the live quadtree). Coordinates are the **native scene frame** (cm, CAD Y-up per
  ADR-002: origin bottom-left, +y north/up); shapes are summarised by `object_bbox` (handles every
  serialised geometry). `raw=True` returns the serialiser dict(s) via a **dict-first
  union return** (`list[dict] | list[ObjectRef]`) so FastMCP keeps a clean `anyOf`
  schema **and** preserves unknown keys on raw (model-first would coerce raw dicts
  back into the model and drop keys — verified mcp 1.28.1).
- **`get_diagnostics`** reports the plan's **already-computed** warnings, not a
  recomputation: `ProjectManager.diagnostics_snapshot` harvests each garden item's
  badge flags (`antagonist_warning` / `spacing_overlap` / `capacity_overrun` /
  `soil_mismatch_level` / `rotation_status`) on the main thread into Qt-free records,
  and the Qt-free `diagnostics.py` maps them to `Diagnostic`. Positive indicators
  (spacing `"ideal"`, rotation `"good"`) are not reported; values reflect the last
  computed badge state (may lag a debounce tick — fine for read-only inspection).
  The one exception is `outside_canvas` (#380): it is not a badge flag but is
  computed on every call from each item's live `sceneBoundingRect()`.

**Vision tool (US-D1.3).** `render_canvas_image(x?, y?, width?, height?, layers?,
image_width_px?)` returns a PNG of the live canvas plus a `RenderMeta` block,
reusing `services/scene_rendering.render_scene_region` — the exact pipeline
`ExportService.export_to_png`/the PDF report already use, no new rendering
logic. `agent_api/render.py` is the one Qt-**touching** module in the package
(says so in its own docstring): `resolve_image_pixel_size` (pure, no Qt) clamps
the requested width **and** the aspect-ratio-derived height independently to
`[128, 2048]` so a pathological region can't produce a runaway image; the
provider resolves the default region (full canvas), temporarily forces
layer-bearing item visibility to match `layers` (`_hidden_layers_not_in` —
a full override of what's shown, not a subtractive filter, so an allowed
layer the user has toggled off live is shown anyway; restores every item's
*original* visibility afterward), renders, and PNG-encodes — all in **one**
atomic main-thread hop (`AgentProviders.render`, the first *parametrized*
provider). Two things were **empirically verified**, not assumed:
- `Image` (from `mcp.server.fastmcp.utilities.types`) isn't pydantic-representable,
  so the natural `-> list[Image | RenderMeta]` annotation crashes `build_server()`
  at decoration time; `@mcp.tool(structured_output=False)` is the verified fix,
  at the cost of this one tool having no `structuredContent` (parse the
  `TextContent` block's JSON instead). Relatedly: with `from __future__ import
  annotations` in effect, `Image` must be a genuine module-level import in
  `server.py` — importing it only inside `build_server()` (as `FastMCP` is)
  raises `NameError` at server-build time, since FastMCP resolves stringified
  annotations via the function's own `__globals__`, not the enclosing call's
  locals.
- The rendered image's pixel Y-axis is **inverted** relative to the D1.2 scene
  frame — `render_scene_region`'s `y_flip=True` (kept for parity with the live
  CAD view and every other export) means a small scene-y lands near the
  **bottom** of the image, not the top. Pinned by rendering a known-position
  item and scanning actual pixels (`tests/unit/test_agent_api_render_coordinate_frame.py`).
  The correction formula is documented on `RenderMeta.px_per_cm`:
  `px_x = (x_cm - region_x_cm) * px_per_cm`;
  `px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`.

See ADR-034 addendum (US-D1.3) for the full reasoning.

**Export/save tools (US-D1.4).** `save_plan(file_path?)`, `export_pdf(file_path?,
paper_size?, orientation?)`, `export_dxf(file_path?)`, and `export_csv(kind,
file_path?)` are the first Agent API tools with a **filesystem side effect**
beyond returning bytes/dicts — each writes a real file to disk by calling the
exact same services the GUI's File > Export/Save menu already calls
(`PdfReportService`, `DxfExportService`, `ExportService`, `ShoppingListService`,
`ProjectManager.save`). `agent_api/exports.py::resolve_export_path` is the
shared path-resolution helper: with no `file_path`, it uses the same
`app/paths.py` chokepoint the GUI dialogs use (`default_save_path`/
`default_dialog_dir`, the #199/#204 data-loss fix — next to the currently open
project, or `<Documents>/Open Garden Planner`); with an explicit `file_path`,
it force-applies the correct suffix and requires the parent directory already
exist (a typo'd path fails clearly rather than silently creating a directory
tree). `save_plan` with no `file_path` and no project open raises rather than
inventing an `Untitled.ogp` — mirrors the GUI, where a brand-new project always
needs an explicit Save-As first; given a path, it becomes the project's file
going forward (Save As semantics), and `ExportResult.previous_file_path` reports
the prior file so a caller can tell whether the call redirected the project.
None of these tools return `Image`, so D1.3's `structured_output=False`
workaround doesn't apply — all four register normally and share one
`ExportResult` schema. **No token auth needed:** these tools don't mutate the
in-memory plan (`save_plan` persists what's already on screen, mirroring
`application._save_to_file` including its issue-#178 stale-price prune); the
token-auth gate stays reserved for D2's scene-mutating write tools (ADR-033).
None of the four are overwrite-safe the way a `QFileDialog` prompt is — an
explicit path pointing at an unrelated file is overwritten without
confirmation, accepted under the loopback-trust model. See ADR-034 addendum
(US-D1.4) for the full reasoning.

**Resources & prompts (US-D1.5).** Five read-only resources — `garden://plan`
(curated `PlanSummary`), `garden://plan/raw` (uncurated snapshot dict),
`garden://canvas.png` (full-canvas PNG, no region/layer args), `garden://
diagnostics`, `garden://species` (bundled species DB, 118 records) — and two
read-analysis prompts, `audit-plan` and `describe-garden` (new Qt-free
`agent_api/prompts.py`), round out the epic's "tools + resources + prompts"
MCP surface. Four of the five resources are one-line reuses of existing
D1.2–D1.4 functions; `garden://species` calls `services/bundled_species_db
.get_species_db()` directly with **no `AgentProviders` field and no
main-thread hop** — that module is Qt-free static bundled data, not live-plan
state. Verified directly against the installed `mcp==1.28.1` source (not
assumed, same discipline as D1.3's `Image` discovery): resource functions are
simpler than tools — `@mcp.resource(uri)` only inspects params via plain
`inspect.signature(fn)` (every D1.5 resource is zero-argument, so the
tool-only `eval_str`/module-level-import gotcha doesn't apply), a `bytes`
return with an explicit `mime_type` produces a base64-encoded
`BlobResourceContents` automatically (**no** `Image`/`structured_output=False`
workaround — that was tool-dispatch-only), and any other return (a pydantic
model, a `dict`, a `list`) auto-serializes via `pydantic_core.to_json`. A
plain `str` prompt return is likewise wrapped into a `UserMessage`
automatically. See ADR-034 addendum (US-D1.5) for the full reasoning.

**AI client onboarding (US-D1.6).** A running server is useless until the
user's AI client knows its URL — there's no universal localhost-MCP
auto-discovery. The Help → "Connect AI Assistant…" dialog
(`ConnectAiAssistantDialog`) and a new Qt-free `services/ai_client_onboarding
.py` close that gap: `detect_clients()` checks each client's known config
location (`~/.cursor`, `claude` on `PATH` / `~/.claude.json`, the platform
Claude Desktop app-data dir), and `install_to_client()` registers the URL
where each client's own docs support a safe automatic path — **Cursor** via a
direct JSON merge into `~/.cursor/mcp.json`, **Claude Code** via the `claude
mcp add --transport http --scope user` CLI when it's on `PATH`, else a
**direct atomic merge into the top-level `mcpServers` of `~/.claude.json`**
(the same user-scope `type: "http"` entry the CLI writes, read by both the
CLI and the VS Code extension — so onboarding works without a terminal; the
merge fails *closed* on an unreadable file, since `~/.claude.json` also holds
OAuth/trust). **Claude Desktop is detection-only and cannot reach a localhost
server** (its connectors are reached from Anthropic's cloud and reject
`localhost`), so its row shows an honest "use Claude Code or Cursor instead"
note — no button, no snippet. Every client with an automatic path also gets a
copy-paste JSON snippet with a short "where to put this" note, and an always-
present vendor-agnostic group (canonical `mcpServers` JSON + generic CLI shape +
bare URL) covers any client OGP has never heard of. This is the **first
atomic-write pattern in the codebase**: every prior JSON writer here only
ever wrote its own file with a bare `open(path, "w")`; because this one edits
files *owned by other applications*, the merge preserves every other
key/server and writes via a same-directory temp file + `os.replace()`, copying
the file's current contents to `<name>.bak` **immediately before** that write
and naming the backup in its success message. Two consequences of the ordering:
a **refused** merge leaves the directory byte- and file-for-file identical (a
refusal is the common case for a `foreign` target, so taking the backup earlier
meant the common case littered a second file beside a config OGP had just
declined to touch), and a second call overwrites `.bak` with the state from just
before *that* call, not the pristine original.

**Generalized in issue #366 — clients are data, and the writer is keyed on syntax
rather than on client.** A client is one frozen `ClientTarget` in `TARGETS`;
`container_key` (possibly dotted, e.g. `mcp.servers`), `syntax`
(`json`/`jsonc`/`toml`) and `entry`/`cli_argv` are independent fields, so a new
client is one record rather than two new `if`/`elif` branches, and the dialog
needed no change to gain OpenCode, Codex and Gemini CLI. The three
client-agnostic guarantees (backup, atomic replace, fail-closed) now exist once
in `_merge_into_config`, with only serialisation varying per syntax. Three
lessons worth carrying: **(a)** a client's config may be a *superset* of the
format you assume (OpenCode's is commented JSON that plain `json.load()`
rejects) — and a fail-closed rule is only safe while the *read* can understand
what it refuses to clobber; the tolerant reader is a character scan, not a
regex, and the strict reader still raises so leniency cannot leak into
fail-closed. **(b)** A surgical writer into a file you don't own owes a **parse
check on its own output** — validating the input is not a licence to write an
unverified result (a header spelled `["mcp_servers"."name"]`, or a `[`-leading
line inside another table's multi-line string, both produce a file the user's
own program cannot parse, and one of them destroys the other table's data).
**(c)** Never re-serialise a file you do not own: that is why TOML is appended
surgically and why the foreign JSONC target *refuses* the merge rather than
rewriting the user's comments away. See ADR-035 (with its #253 and #366
addenda) for the per-client reasoning and §11.4 for the pitfall entries.

**Agent write path & token gate (US-D2.0/D2.1, ADR-036).** The scene-mutating
tools — `move_object(item_id, dx, dy)`, `delete_object(item_id)` (D2.0) and
`create_object(object_type, x, y, …)` (D2.1) — sit
behind **two independent guards**: a **writes-enabled** Settings toggle
(`agent_api_writes_enabled`, **default OFF**) and a **bearer token**
(`agent_api_token`, auto-generated with `secrets.token_urlsafe(32)`). The tools
are **registered only when both are present** (`writes_enabled and write_token`)
— when either is missing they don't appear in the tool list at all — and each
call must carry the token, **either in the connect URL as a `?token=` query
param or as an `Authorization: Bearer <token>` header** (the URL token wins when
both are present, so a stale legacy header can't shadow it). The URL route is the reliable one: Claude Code on streamable-HTTP
stores a configured header but omits it on tool-call requests (anthropics/
claude-code#50464 / #28293), while the URL — being the request target — is
always transmitted; delivering the secret there preserves the same threat model
(a caller still needs the token) at the cost of a URL-borne secret (mitigated:
uvicorn access log off + the `token` param is stripped from the request scope
right after extraction, so nothing downstream logs it). Reads stay open (loopback
trust, unchanged), so the gate is **per-tool, not a server-wide middleware**
that would break read-only D1 clients: a pure-ASGI wrapper
(`_bearer_token_middleware`) reads each request's token from the header or the
`?token=` query string into a `contextvars.ContextVar`, and each write handler
calls `_require_write_auth` (constant-time `secrets.compare_digest`) in the same
request task, **before** the `anyio.to_thread.run_sync` main-thread hop. Verified end-to-end against
`mcp==1.28.1` with `stateless_http=True` that the ContextVar set in middleware
is visible in the tool handler for the same request (chosen over a `ctx:
Context` header read so the gate doesn't depend on FastMCP internals). The
write itself hops to the main thread via an `AgentProviders` callable,
resolves the item by UUID (`scene.find_item_by_id`), and runs
`canvas_view.command_manager.execute(cmd)` — matching GUI *behaviour*, not
merely reusing a `Command` class: `delete_object` mirrors
`CanvasView._delete_selected_items`'s full orchestration, not just
`DeleteItemsCommand` — it also removes any constraint referencing the object
(`RemoveConstraintCommand`, else the constraint graph keeps a dangling UUID)
and deletes a `HOUSE`'s linked roof ridge (a `metadata["ridge_item_id"]`
association, else orphaned); contained plants are still detached, not
deleted, matching the GUI's "Keep plants" choice. `move_object` mirrors
`CanvasView`'s whole drag-release sequence — a bed/container/trellis's
contained plants move with it (`AlignItemsCommand` over item+children), and a
moved plant's bed membership is re-evaluated inside the same move command
(`MoveItemsCommand`/`AlignItemsCommand` reconcile it; #443) — so **one agent
write is one undoable step, including a move that reparents a plant**, never
more; every command still marks the plan dirty (invariants #3/#4/#13; no
parallel mutation path).
Both tools **refuse** (in the shared `_resolve_agent_item` chokepoint, so
future write tools inherit it) rather than silently mishandle cases the agent
could otherwise reach by resolving a UUID directly but the GUI forbids: an
object (or, for `move_object`, a bed child) in a geometric constraint —
`CanvasView`'s live solver computes per-item deltas a one-shot agent call
doesn't replicate; a journal pin, whose delete needs a `ProjectData`
note-record prune no bare `DeleteItemsCommand` performs; an item on a **locked
layer** (the GUI enforces the lock by clearing `ItemIsSelectable`/
`ItemIsMovable`, which selection-based GUI edits respect but a UUID lookup
bypasses); and an individual **group member** (a raw snapshot exposes its id,
but `moveBy` on a `QGraphicsItemGroup` child displaces it within the group —
address the group itself). `GroupItem`/`SmartSymbolItem` moves need no special
handling: they are real Qt groups, so `moveBy`/delete cascade to members
natively (the bed↔plant link is *logical*, which is why beds don't).

**Creation is the exception to that chokepoint (US-D2.1).** `create_object`
has no existing item to resolve, so it inherits **none** of
`_resolve_agent_item`'s four refusals — which makes it the one write tool whose
guards have to be stated separately. They live in two places, deliberately, and
must be kept in step:

- **Shape, size and position** — the Qt-free `agent_api/creates.py`. Beyond the
  obvious (unsupported type, a dimension that doesn't fit the shape, a missing
  or non-positive or non-finite extent) it applies two **sanity bounds**, because
  finite-and-positive is not the same as plausible and an agent is exactly where
  a metres-for-centimetres slip appears: every extent is capped at twice the
  plan's larger canvas dimension (the error names the real plan size), and a
  **plant's** diameter is additionally capped at 5000 cm because a plant
  footprint feeds `plant_renderer.render_plant_pixmap`, which allocates an
  `int(diameter)`-square ARGB `QImage` **from scene centimetres, not device
  pixels**, on the Qt main thread — quadratic, and measured at ~2.3 GB / ~3 s
  for a 24000 cm diameter, with allocation failure yielding a *null* (not
  `None`) `QPixmap` the paint path forwards unchecked. Positions further than
  one canvas beyond an edge are refused too: such an object is invisible,
  unselectable and un-deletable in the GUI, so reporting success would be a lie.
  This mirrors `render.py`'s existing precedent of clamping agent-supplied
  sizes harder than the GUI does.
- **Scene state** — `GardenPlannerApp._agent_creation_target_layer()`, which
  needs the live scene and so cannot be Qt-free. It refuses a **locked active
  layer** (the creation-side counterpart of the item-side lock check) and
  returns `None` when the scene has no active layer at all, matching the GUI
  drop path, which likewise leaves `layer_id` unset. It exists as a named seam
  rather than an inline check so the next creation-shaped tool inherits it.

One further asymmetry is worth knowing: creating on a **hidden** active layer
silently un-hides that layer (`QGraphicsScene.addItem` does this for the GUI's
draw tools too) and **undo does not re-hide it** — so the operation is one undo
*stack* entry while leaving a non-undoable visibility change. Pre-existing GUI
behaviour, not a D2.1 regression, but it sits oddly beside the locked-layer
refusal and is recorded in FR-AGENT-14.

Unlike `move_object`, `create_object` needs no bed reconciliation:
`CreateItemCommand.execute` already calls `_auto_parent_plant` and its `undo`
calls `_detach_from_parent`, so a new plant's bed link is established and
reversed **inside the single create step**. (The first cut of D2.1 added an
explicit reconcile on the false premise that the GUI never links a dropped
plant; a probe of the running code disproved it — see ADR-036's D2.1 addendum.)

The token is surfaced (Copy/Regenerate) in Preferences → Agent API and
injected into each client's config by the D1.6 onboarding writers as a
`?token=` query param on the connect URL (`ai_client_onboarding.url_with_token`).
See ADR-036 (and its URL-delivery addendum); §8.11 for the security note.

**Editing existing objects (US-D2.2/D2.3).** Four more tools sit inside the same
`if writes_active:` block and share `_resolve_agent_item`: `resize_object`,
`rotate_object`, `set_species`, `set_parent_bed`. Each applies exactly one
undoable command, and since #443 each reconciles bed membership inside that
same step (a bed resize or rotate can unlink its plants); `move_object`'s
reparent is likewise part of its own step, not a second one. Three points are
load-bearing for anyone extending them:

* **One geometry-apply path per geometry model.** `ResizeItemCommand` /
  `RotateItemCommand` take a caller-supplied `apply_func`, and before D2.2 every
  call site had its own closure — which had drifted, leaving three rotated-geometry
  bugs in shipped GUI paths (§11.4). `ui/canvas/geometry_apply.py` is now the single
  implementation; **its module docstring is the authoritative list of callers and of
  the two deliberate exceptions**, and is deliberately not restated here. Do not add
  another rect closure; add a builder there.
* **Centre-preserving is the agent's anchor rule, for every type.** The read
  tools and `create_object` speak in centres, so `resize_object` holds the
  scene centre invariant; the panel keeps its own per-type anchor behaviour.
  Both are the same builder with `keep_center=True|False`, and both solve `pos`
  through `anchored_position()` so a rotated item lands correctly either way.
* **Rotation sign is measured, not assumed.** A positive angle is
  **counter-clockwise** (east-pointing → north after `+90`). Pinned against a
  measured corner position in both `tests/unit/test_agent_api_edits.py` and
  `tests/integration/test_agent_api_default_on.py` — never against the stored
  angle, which cannot detect an inverted convention. This is the #267 lesson
  applied prospectively.

`set_species` delegates to `ui/plant_species_assignment.apply_species_to_item`
(the #213 helper the plant panel and species search already share) rather than
building `ApplySpeciesCommand` itself; its `apply_database_size` flag answers
the GUI's conflicting-override dialog and is **not** a general "skip the resize"
switch. `set_parent_bed` changes the link only — the plant does not move — and
deliberately does not require geometric containment, reporting
`link_is_geometric` instead so the agent can flag a mismatch. Validation for all
four lives in the Qt-free `agent_api/edits.py`, whose plant-parent name set
carries a drift guard against `PLANT_PARENT_TYPES` (§8.14 / ADR-017 — note
`TRELLIS` is a plant parent but not a soil container). See ADR-036's D2.2/D2.3
addenda, FR-AGENT-15/16.

**Stacking order (issue #338, ADR-043 — outside the D2.x sequence, see
`docs/roadmap.md`'s standalone "Canvas: Per-object stacking order" section).**
A fifth tool in the same `if writes_active:` block, `arrange_object(item_id, action)`, reorders one
object within its own layer (`bring_to_front`/`bring_forward`/`send_backward`/
`send_to_back`). It does not build its own command: it calls
`ui/canvas/arrange.py::build_arrange_command` — the same seam the Edit menu,
every item's context menu, and the Properties panel's Arrange buttons call —
so the bed-carries-its-plants block and the plant-cannot-go-behind-its-bed
clamp (§8.25) apply identically whether a human or an agent triggers the move.
It raises rather than reporting a false success when the gesture is a no-op
(already at the front/back of the layer, or no overlapping object to step
past for the forward/backward step) — the same refusal-over-silent-success
precedent as `set_parent_bed`. `ObjectRef`/`ObjectDetail.stack_index` is the
read-only counterpart: a 0-based position within the object's own layer,
bottom→top, as displayed — comparable only between objects on the same layer.
**Order note:** `list_objects`, `objects_in_region`, and `get_object` are
documented as returning/reading objects **bottom→top in stacking order**
(layer order, then position within the layer) — the same order
`ProjectManager.snapshot_dict`/`_serialize_scene` now writes them in
(`reversed(scene.items())`, ADR-043) and the same order `stack_index` is
computed from. `get_diagnostics` is explicitly **not** in that order — it
walks the live scene's badge state directly and was not changed by #338.

**i18n.** MCP tool/resource/prompt descriptions are an English API contract
(exempt). Only the Settings UI strings go through `tr()`.

**Packaging.** See §7 deployment view — the `mcp`/`uvicorn`/`starlette` stack
needs `collect_submodules` in `ogp.spec`; its distribution metadata comes from
the runtime closure (`installer/runtime_closure.py`, AUD-051/#454). The spec must
NOT walk `mcp.cli`, and must NOT exclude `multiprocessing` (uvicorn imports it).

**US-D2.4/D2.5 — layer addressing and shape/structure creation.** The curated
schema exposes layers as UUID-addressed records (`layer_id`, name, visibility,
lock, opacity, z-order, active flag, and top-level object count);
`layer_names` remains for back-compat. `list_layers` is read-only and open
like the other read tools, while the layer write tools remain behind the D2.0
double gate: `set_object_layer`, `create_layer`, `rename_layer`,
`delete_layer`, `set_active_layer`, and `set_layer_property`. They call
the existing layer commands rather than mutating `scene.layers` directly.
Visibility is undoable; the active layer is session state and therefore the
one layer operation that does not add an undo step. **A locked layer protects
its OBJECTS, and (since issue #365) the lock itself is agent-writable in both
directions.** That is a deliberate reversal of the original D2.4 decision, so
state it plainly: `set_layer_property(layer_id, locked=true|false)` locks and
unlocks through the same `SetLayerPropertyCommand` the Layers panel's own
toggle runs, as one undo step. What is unchanged is the object-level
protection — while a layer is locked, agents may not delete it, move objects
onto it, or edit objects on it — and every one of those guards tests the
layer's **current** lock state rather than a permission bit. So "unlock, then
edit" is simply two ordinary undoable calls the user can see and reverse; no
guard had to become conditional, and the tests that pin them are unchanged.
Every refusal now names `set_layer_property(layer_id, locked=False)` as the
way out, because that is the tool the agent actually has. Deleting another
layer also refuses when its replacement would be locked; the command rechecks
that precondition on redo. `set_layer_property` may change visibility and
opacity on a locked layer, because that does not alter its protected
contents.

**Document lifecycle (issue #365).** Two more token-gated tools,
`new_plan(width_cm?, height_cm?, force?)` and `open_plan(file_path, force?)`.
They are gated like `delete_object` — not merely because they mutate, but
because they **replace the open document and can discard unsaved work**, which
is strictly more destructive. Both reuse the GUI's own paths rather than
reimplementing them: `_on_new_project` was extracted into
`_new_project_document`, and `_open_project_file` was split into a raising
`_load_project_file` plus its modal-reporting GUI wrapper, so an agent never has
a `QMessageBox` appear on its behalf. Each **refuses on a dirty plan unless
`force=true`**: the GUI asks the user at that point and an agent cannot, so the
choice is binary. `new_plan` keeps the current canvas dimension for any
argument omitted and **refuses** an out-of-range or non-finite one rather than
clamping. `open_plan` requires an existing `.ogp` file and is deliberately
**not** sandboxed (a loopback-only server grants no filesystem access a local
MCP client does not already have — see `agent_api/exports.py`). Neither is an
undo step: a new or loaded document resets the stack. Both declare
`PlanLifecycleResult`, not `ExportResult` — neither writes a file, and reusing
`ExportResult` made every successful call raise a `ValidationError` while
body-level tests stayed green.

`create_object` now covers the curated GUI roster by canonical geometry
family: circles, rectangles, ellipses, polygons, polylines, and callouts. The
input contract is explicit: centres and extents are centimetres in the native
CAD Y-up scene frame; polygon/polyline vertices pass through unchanged;
polygons also accept a centre plus width/height convenience form; and callouts
retain their stable item id through save/load. The loader's
`ProjectManager._deserialize_item_core` remains the sole construction path,
so agent-created objects and loaded objects cannot acquire divergent defaults.
`HOUSE` creation builds its linked `ROOF_RIDGE` with the shared
`core.roof_ridge` geometry helper and groups both items into one undo command.
`ROOF_RIDGE`, `GARDEN_JOURNAL_PIN`, `GENERIC_TEXT`, and legacy
`HEDGE_SECTION` are deliberately refused with machine-readable reasons;
`list_creatable_types` exposes both the supported roster and these
exclusions. The union of those two sets is drift-guarded against
`ObjectType`, so a new enum member cannot silently become an undocumented
agent capability. No `FILE_VERSION` change is required: the schema additions
are additive and the new item data uses existing serialisation shapes.

**Low-level geometry escape hatches (US-D2.6, issue #330).** The stable read is
`get_geometry(item_id)`, not `get_object(raw=True)`: the latter intentionally
exposes pre-transform serializer storage. `ui/canvas/geometry_inspect.py` runs on
the Qt main thread and reports the same centre semantics as `get_object`, but maps
current polygon/polyline vertices through `mapToScene()`, plus native extents or
radius, rotation, curve/leader data, vertex capability/minimum count, and every
referencing constraint in deterministic `(type, id)` order. The read is
unauthenticated and never mutates or dirties the plan. Locked-layer and journal
objects remain inspectable; group members remain non-addressable because the
rest of the curated object surface addresses only top-level ids.

Four writes share the ADR-036 gate. `set_object_position(item_id, x, y)`
validates a finite, canvas-reachable absolute centre, converts it to a delta, and
enters the same orchestration as `move_object`: logical bed children move with
the parent, plant bed membership is reconciled inside that same move command
(#443), and a reparent is therefore ONE undo step, not a second one.
`set_vertex`, `add_vertex`, and `delete_vertex`
support only the polygon/polyline protocol. Qt-free `agent_api/edits.py` owns
finite/reachable point validation, zero-based index semantics (an append uses
`index == vertex_count`), and the deletion minimum supplied by the item's
vertex-editing protocol (3 for a polygon, 2 for a polyline). Every accepted topology write is
one `AddVertexCommand`/`DeleteVertexCommand`; set is one `MoveVertexCommand`.
Their callbacks are built only by `geometry_apply.py`, which the interactive
vertex commit paths also call. A HOUSE topology change invokes the item's
existing linked-ridge reprojection hook, keeping the ridge attached through
execute/undo/redo without turning the agent operation into a second command.

The coordinate-frame rule has one precision guard: if a `set_vertex` target is
within `1e-9 cm` of the current live vertex, `local_vertex_for_scene()` reuses
the exact current local `QPointF`; otherwise it uses `mapFromScene`. A raw
scene→local→scene inverse at 215° drifted by about `5.7e-14 cm`, so without the
guard an unchanged request could look like a real mutation. The tool then refuses
that unchanged request as a no-op with no command, history entry, or dirty state;
the epsilon is noise detection, not a user snap mode. A moved-then-restored
vertex leaves the serialized object byte-identical.

**Constrained geometry remains permanently refused.** `_agent_require_unconstrained`
is the one perimeter for absolute positioning, move, resize, rotate, species
assignment when it resizes, and all vertex writes. The error names the first
constraint type/UUID; `get_geometry` exposes the complete blocking set so the
agent can explain why. This is final, not “solver deferred”: silently skipping
`CanvasView`'s live multi-item solver would violate user intent. Solver-backed
agent writes require a separate proof/design. Arrays, booleans,
trim/extend/fillet/chamfer, align, mirror, and group/ungroup remain a named
follow-up backlog. `delete_object` is the one policy exception and removes
referencing constraints as part of its existing GUI-equivalent delete contract.
Every refusal occurs before command execution, leaving scene, constraints,
undo/redo, and dirty state untouched. No `FILE_VERSION` change.

**Follow-up hardening (issues #353 and #355).** The global GUI/agent history is
one `CommandManager` stack, not a second MCP history. Authenticated `undo` and
`redo` preflight the relevant stack, reverse or reapply exactly one command on
the Qt main thread, and return a `HistoryResult` containing the command
description and the post-call `can_undo`/`can_redo` flags. An empty stack is a
refusal; it is never a successful no-op. Project loading uses one centralized
predicate for serialized document items, so same-scene loads remove old
callouts and Arc/Bezier items as well as the original shape roster. Compare and
dimension overlays keep their explicit controller cleanup, and a broad
`CanvasScene.clear()` is not substituted for that ownership boundary. Agent
`delete_object` additionally refuses duplicate live UUIDs and checks that every
requested target is detached before returning success.

Callout input is validated in `agent_api/creates.py` before the loader receives
it. `box_dx` and `box_dy` remain signed so the GUI's normal above/below/left/
right placement works, but each is finite and bounded by
`abs(offset) <= 2 * max(canvas_width_cm, canvas_height_cm)`, including the
resolved defaults. The MCP wrapper uses a private omission sentinel because
some JSON stacks normalize Infinity/NaN to `null`; explicit null is rejected
rather than silently becoming the default offset. Thus oversized, negative-oversized, and non-finite calls
leave both the scene and undo stack untouched, while normal callouts still
save/load, render, and delete through the existing paths. The benchmark
hardening for #354 is documented in FR-SNAP-06 and ADR-020: one warm-up plus
five samples, with median build/query limits calibrated for shared runners.

**Canvas clamping (issue #380).** Agent writes are clamped to the plan canvas,
joining the GUI, and the earlier "stage an object just off-plan" allowance is
retired. The rule lives once for the canvas-view clamp paths and the agent paths (the properties panel's numeric X/Y, the mirror tool and the resize handle still carry their own copies — not yet migrated), Qt-free, in `core/canvas_bounds.py`
(`clamp_shift_within_canvas`, `clamp_delta_within_canvas`,
`rect_intersects_canvas` over `(left, top, right, bottom)` tuples). The GUI's
`CanvasView._clamp_items_to_canvas` / `_clamp_delta_to_canvas` call it, and so do
`GardenPlannerApp._clamp_agent_items_to_canvas` (creation) and
`_agent_apply_object_move` (move / absolute position). It is applied in the
application layer, where live bounding rects exist — `agent_api/creates.py` stays
further Qt-free. `create_object` shifts the whole creation group (a HOUSE and its
linked ridge together); a move clamps the item plus any plants it carries, so an
offset that would strand the group is trimmed to the edge. `BackgroundImageItem`
is exempt, matching the GUI. `require_reachable_position` remains only as the
refuse-absurd gross guard and still leaves the scene and undo stack untouched on
refusal. An object already saved off-plan by an older build — which clamping
cannot recover, because the GUI clamp touches only the items being moved — is
made discoverable instead: `ObjectRef`/`ObjectDetail` carry `outside_canvas`
(bounding-box based; an empty canvas never flags) and `get_diagnostics` gains an
`outside_canvas` kind, harvested by the existing
`ProjectManager.diagnostics_snapshot`. `set_vertex`/`add_vertex`/`delete_vertex`
are **not** clamped (they are outside the GUI's five clamp sites) and are covered
by the flag only — a deliberate scope boundary recorded in the ADR-036
addendum.

**Domain-intelligence tools (US-D3.1 #319, US-D3.2 #331).** D3 wrapped domain engines
that already existed and were already Qt-free, and made them reachable. Both slices
add one Qt-free module, `agent_api/domain.py`, holding the pure functions; the
`AgentProviders` callables in `application.py` marshal them across
`MainThreadBridge.run_on_main`. Three conventions carry across both slices and are
what the next D3 slice should follow:

- **Honest degradation beats a plausible empty answer.** A component that did not
  check something must not report a result that reads as a successful check. D3.1
  returns `spacing_ok`/`soil_ok` as `None` ("not checked", never a fabricated
  `True`) and `overall: "unknown_bed"` for an id that resolves to nothing (never
  `"neutral"`, which reads as "I looked and there was nothing"). D3.2 reports
  `has_plan: false` for "no plan" as distinct from an empty plan, and
  `coverage: "no_frost_dates"` **together with** month-based fallback segments
  rather than an empty segment list.
- **Deterministic ranking with a stable final tiebreak.** D3.1 caps candidates at
  60 and results at 50 and pins identical ordering on repeat calls. D3.2 sorts on
  `(fits_window desc, days_to_maturity asc, species_key asc)`; both are pinned by
  a same-input-twice test *and* a reversed-input-order test, because a suite that
  only re-runs the same order cannot see an unstable tiebreak.
- **`species_key` is derived, never invented (ADR-016).** It is a module-level
  function over a dict (`models/plant_data.py`), not an attribute of a species
  record, and its priority is `source_id -> scientific_name -> common_name` - so a
  bundled plant's key is its **scientific** name. `"beans"` is not a valid key;
  `"phaseolus vulgaris"` is. An implementation that reads a `species_key`
  attribute silently gets `""` for every candidate.

**Machine fields vs display strings.** Across the agent surface, fields an agent
should *branch on* are the English API contract. The tool-side free text (D3.2's
`reasons[]`) is **English and never localised** — ADR-033 makes MCP output an
English contract — so it is documentation, not something to parse. D3.2's
`reasons[]` and D3.3's generated task titles are therefore different problems:
the latter DO cross the boundary translated, and D3.3 owns that decision.
D3.2's `suggest_succession` is the worked example: branch on
`species_key` / `family` / `days_to_maturity` / `fits_window`; `reasons[]` is
prose. Note the asymmetry that makes this necessary - `services/task_generator.py`
and `services/soil_service.py` build their task titles and amendment names with
`QCoreApplication.translate`, because the GUI is their primary consumer, so those
strings cross an API boundary localised. Do not force English at the generator.

**D3.1's companion `name` follows the same rule (issue #410).** `suggest_companions`
returns `species_key` (a stable machine key) beside `name` (a display string in the
user's current UI language, selected from `companion_planting.json`'s `name_de` by
`app/settings.py::active_language()`). Branch on `species_key`, never on `name`. The
D3.1 tool predated the D3.3/D3.4 convention and shipped with the English default; the
fix brought it into line. The generated soil-amendment task titles obey the same rule
(issue #408), with the extra constraint that the task **id** keeps the English data name
so saved task status survives a language switch.

**The D3 localisation convention (US-D3.3 #332 + US-D3.4 #333, decided).** Epic
#237 required one answer across both stories, so this is stated once here and in
the ADR-034 addendum. Every D3 tool carries **two field classes**:

| Class | Fields | Contract |
|---|---|---|
| machine keys | `task_id` / `task_type` / `source`; `amendment_id` / `target_kind` / `fixes` / `reason_codes` | **Stable English.** Part of the API contract. Never localised. |
| display strings | `title` / `notes`; `display_name` / `reasons` | **The user's current UI language.** Explicitly NOT part of the English contract. |

Consequences worth stating because they are all easy to get wrong:

- **The agent layer passes the localised string through; it never translates.**
  The translation stays upstream in `task_generator` / `soil_service`, where the
  GUI already depends on it. `tests/unit/test_agent_d3_localisation.py` pins the
  pass-through *and* the upstream translation separately — asserting only "the
  title changed" would pass even if the wrapper had invented its own translation.
- **Amendment names are data, not translations.** `Amendment.name` / `name_de`
  are bilingual *data* fields, so `display_name` is *selected*. The convention is
  unchanged either way: `amendment_id` never moves with the UI language.
- **`task_type` carries the distinction `source` cannot.** `Task.source` has six
  values — `calendar`, `propagation`, `succession`, `soil`, `frost`, `manual` —
  for seven generators, because both soil generators emit `source="soil"`. The
  amendment and mismatch tasks are told apart by `task_type`
  (`soil_amendment` vs `soil_mismatch`), so **filtering by `source` alone cannot
  select one of them.** A drift guard asserts the tuple equals the engine's set
  in *both* directions (§11.4: a subset-only guard let two values that no
  generator emits through, which made the working value refused and the
  non-working one return an empty list).
- **Hidden statuses match the Tasks tab exactly.** `get_tasks` hides `archived`
  and `dismissed` by default because `ui/views/tasks_view.py` hides those two.
  Hiding only `dismissed` would make the agent a third surface disagreeing with
  the other two about one shared store — invariant 6.
- **Degradation is never silence.** A plan with no geo-location has no frost
  dates, so the calendar and propagation generators produce nothing;
  `coverage: "no_frost_dates"` says so and still returns every other task kind.
  A bed with no soil test gets `coverage: "no_soil_test"`, which means *untested*
  and never *healthy*. An empty list is never the whole answer.

**Soil reads need provenance, not just a reading.** `SoilService.get_effective_record`
applies its documented hierarchy (bed's own latest → plan-wide default's latest →
none) and returns the record alone. For an agent that is unusable: with only a
plan-wide test recorded it hands back the global record *for a bed*, and the
caller cannot tell that from a real bed reading. `SoilStatus.record_source`
(`'bed'` / `'global'` / `'none'`) restores the distinction, and the provider
uses `SoilService.get_effective_record_with_source` to obtain the record, source
and matching history together. The existing `get_effective_record` delegates to
that same resolver. Staleness follows the selected history, including a global
fallback; checking an empty bed history against an old global reading incorrectly
reported it as current.

**D3 transport envelopes and period generation.** `get_soil_status` always
returns `SoilStatusListView.beds`, with one result for a requested bed or all
soil-capable beds when omitted. `get_soil_mismatches` returns
`SoilMismatchBedsView.beds`, keyed by bed UUID, preserving each bed's `coverage`,
`total` and disagreements. Its aggregate coverage distinguishes `no_beds`,
`no_soil_test`, `partial_soil_tests` and `ok`. The soil prompt extracts the
requested bed from both envelopes before rendering; it never treats an envelope
as one bed. Real-client integration tests use `app._build_agent_providers()` and
call all nine new tools and both prompts over HTTP, including authenticated
writes, refusals and undo. Direct provider tests remain useful but cannot detect
an MCP response-schema mismatch.

`build_plan_state(today, year, actionable_only, include_propagation)` separates
the reference date from the calendar year. Annual agent calendars and explicit
task windows retain inactive dated tasks (`actionable_only=False` at the call
site), then classify urgency against the actual reference date. Cross-year
windows are clipped to each requested year before month bucketing.
`generate_for_date_window` uses one snapshot and the shared generators for the
frost-anchor years capable of overlapping the requested dates, deduplicating
absolute tasks. The range is derived from species offsets and generated
propagation steps: autumn garlic sowing precedes its anchor year, while asparagus
harvest extends three years. Annual calendars use this same path; anchor-year
task IDs remain stable.

**GUI reminder surfaces (#414, ADR-029 addendum).** The Tasks tab and the
planting-calendar dashboard no longer call the generators directly. They call
`task_generator.generate_actionable_for_surface(state)`, which wraps
`generate_for_date_window` and then re-applies the GUI's own listing rule
(`classify_urgency(...) is not None`). Two details are load-bearing and neither is
optional:

- **`actionable_only=False` is passed INWARD.** `generate_for_date_window` builds
  each anchor year with `replace(state, ...)`, so the caller's flag is inherited
  *per anchor year*. Passing the GUI's `True` into it filters anchors out before
  the outer filter ever runs — which is exactly what it did, producing an empty
  Tasks tab and a blank Gantt. The helper passes `False` inward and filters once at
  the edge.
- **Undated tasks pass through, and manual tasks are never urgency-filtered.**
  `classify_urgency` dereferences both dates and `generate_manual_tasks` emits
  undated tasks (`date=None`), so calling it unguarded raised `TypeError` and took
  both tabs down for a plan the agent's own `add_manual_task` creates. Manual
  tasks are additionally merged in from their own generator rather than harvested
  from the date-window pass, because they carry absolute dates and so fall outside
  the date span; their generator documents that a manual to-do is never filtered by
  urgency.

The **Gantt** deliberately uses the *unfiltered* `generate_for_date_window` over
Jan 1 – Dec 31, because a calendar chart is not a reminder list: routing it
through the reminder helper dropped most of the chart. Two entry points, two
declared purposes, neither reimplementing the other. The chart draws the windows
the generators produced rather than re-deriving them from `last_frost` plus raw
offsets — which had made it a second independent implementation of "offset to date" (the callers only *call* `generate_calendar_tasks`, so the old count was high) and the reason it could only ever draw one anchor year.
Absolute propagation overrides instead use their start-date year as the task's
owner year in the shared generator. This preserves one identity across GUI and
agent reads and prevents wider anchor ranges from multiplying one saved step.
Propagation plans use the extracted `build_propagation_plans` calculator
shared with the GUI, preserving seed-packet germination values and user overrides.
Missing frost dates still prevent those plans from being computed.

Amendment display names use `Amendment.display_name(language)` with the app's
language, just as the GUI does; stable amendment IDs do not change. Soil-write
arguments use strict numeric MCP annotations so booleans and numeric strings
cannot be coerced into readings before the domain validator sees them.
An empty amendment list means the engine recommends nothing from the readings
it can assess; it does not prove healthy soil. Existing GUI lab-only records
may have no assessed kit values and keep an unknown health result.

**Secondary nutrients have no health rating, and `None` is the honest answer.**
`SoilService.health_level` rates `ph`, `n`, `p`, `k` and `overall` — its
`ALL_PARAMS` is exactly those five. Passing `'ca'` / `'mg'` / `'s'` **falls
through to the `overall` branch** and returns the whole bed's rating. So
`SoilReading.health_level` is `str | None`, and `None` for a secondary means *"no
rating exists"* — deliberately distinct from `'unknown'`, which means *not
tested*. `overall_health_level` likewise covers **pH and N/P/K only**; the
secondaries do not drag it down. Reporting the overall rating as calcium's would
be a confidently wrong answer, which is the same trap D3.1 closed by reporting
`unknown_bed` instead of a clean-looking `neutral`.

**A rotation rule that looks reusable and is not.** D3.2's
`suggest_succession` must exclude a candidate that conflicts with a crop planted
*earlier in the same succession plan*. `CropRotationService.check_plant_placement`
cannot supply that: it compares the candidate only against `records[0]`, the single
most recent planting record, so it cannot see "tomato after the garlic entry three
slots ago" - and succession entries never enter rotation history at all, since only
the Crop Rotation panel writes `PlantingRecord`s. Succession is several crops in
ONE season; that service models one record per season across years. So the
**cross-year** 3-year family cooldown is reused verbatim via
`get_recommendation(bed_id).avoid_families` (already Qt-free, already feeding
`get_diagnostics`), while the **within-plan** rule is new logic confined to
`agent_api/domain.py`. Calling the existing method would have looked correct,
passed a casual test, and excluded almost nothing.

**Season segments are four, and the no-location fallback is shared.**
`models/succession.py::SEASON_SEGMENTS` is `early_spring`, `late_spring`, `summer`,
`fall` - frost-relative boundaries documented in the module docstring. Segments are
contiguous and inclusive at both ends, so a date exactly on the
`early_spring`/`late_spring` boundary resolves to `early_spring`
(`date_to_segment` returns the first match). A plan with no geo-location has no
frost dates; the calendar-month fallback that handles that lived in
`succession_plan_dialog.py` as a private table, and D3.2 **moved** it to
`models/succession.py` as `compute_fallback_segments`, with
`resolve_season_segments(year, location) -> (segments, are_fallback)` as the single
entry point both the dialog and the agent call. Copying it would have let an agent
and the GUI disagree about what "summer" means for the same bed.

## 8.20 Solar Coordinate Discipline (Phase 14 sun/shade)

The one rule: **do all solar/shadow math in scene centimeters, once, and
flip nothing.** Scene coordinates ARE the CAD coordinates the user sees —
+x = East, +y = North (ADR-002; `ogp-qt-cad-reference` §1 owns the
reconciliation with Qt's abstract Y-down description). Only pixel-facing
surfaces (render/export/minimap) apply a Y-flip, and they already do it
themselves (`render_scene_region(y_flip=True)`).

**From compass azimuth to scene vector.** Azimuth `Az` is a compass bearing
clockwise from true north, so the sun's horizontal direction in the scene
frame is `(sin Az, cos Az)` and the shadow extends opposite:
`d_scene = (−sin Az, −cos Az)`. Shadow length is `L = h / tan α`
(`core/shadow_geometry.shadow_length_cm`, geometric elevation, flat ground).

**Worked example (oracle-pinned).** Berlin 52.52N/13.405E,
2026-06-21 12:00 UTC → α = 59.29°, Az = 203.74°. `sin Az = −0.4025`,
`cos Az = −0.9154` → `d_scene = (+0.4025, +0.9154)` — mostly **north**,
slightly east (early-afternoon sun just west of south → shadow falls NNE).
A 100 cm object casts `L = 59.4 cm`; its tip sits at
`base + 59.4·(0.4025, 0.9154)`.

**In a rendered image** (`y_flip=True`, §8.19 formula
`px_y = image_height_px − (y_cm − region_y_cm)·px_per_cm`): the northward
tip has the *larger* scene-y → the *smaller* pixel-y → nearer the image
top — exactly where North renders. Consistent, not a paradox.

**The classic bug** is "correcting" the y-component a second time at some
item-construction or render boundary — that double flip mirrors every
shadow south. The binding pixel test in
`tests/integration/test_shadow_overlay.py` renders the live scene and
asserts the tip lands at the formula-predicted pixel; if a change mirrors
shadows, that test fails before any human has to eyeball a canvas.

**A caster has a base (Phase 17 L1.6, ADR-037 addendum).** A shadow caster
is a solid `footprint × [base, base + h]` —
`core/shadow_geometry.ShadowCaster(footprint, height_cm, base_cm)`. With the
sun at elevation α its ground shadow is the footprint projected from the
base, swept on to its projection from the top:

    S(F, b, h) = { p + t·d : p ∈ F,  t ∈ [b / tan α, (b + h) / tan α] }

that is, the ground shadow `S(F, 0, h)` moved `b / tan α` along `d_scene`.
The tip — and the near edge — lie `b / tan α` further from the sun; the
ground between the footprint and the near edge is shaded by what the caster
stands on, which is a caster of its own. `base_cm` is 0 for everything on
the garden floor and the **soil surface** for a plant that is linked to
(`parent_bed_id`) AND stands inside a soil container with a height —
`core/object_height.standing_base_cm`: 2 cm under the rim of a bed (an
assumption: a bed has no fill in the plan), AT the height of a container
(its height is its fill height). The link alone never lifts: it is
bookkeeping the app does not keep geometric, so a plant whose centre is not
inside its parent's shape stands on the ground (§8.29.6 "Base stacking").
Worked example: a 60 cm perennial on the soil of a 40 cm raised bed (base
38), α = 35° → the tip lies `(38 + 60) / tan 35° = 140.0 cm` beyond the
plant, 54.3 cm further than from the ground (85.7 cm) — and no longer inside
the bed's own 57.1 cm shadow. **One walk makes the casters**
(`collect_identified_casters`, which keeps each caster's owner for the per-plant
sun estimates of §8.27; `collect_shadow_casters` flattens it): the overlay, the
heatmap and those estimates all come from it, and the
3D records take `transform.base_cm` from the same
`ui/canvas/footprints.item_base_cm` (§8.29.6) — a drift guard counts the
callers and the consumers of `compute_scene_shadows`. A caster is a
`ShadowCaster` or an exact `(footprint, height)` pair; any other shape is a
`TypeError` (`caster_fields`), so nothing but a `ShadowCaster` can carry a
base. A caster on the ground takes the unchanged integer path: the released
v1.29.10 functions, kept as a test oracle, give identical results on any
platform (`tests/unit/test_shadow_caster_base.py::TestTheGroundPathIsTheReleasedCode`),
and `tests/integration/test_shadow_caster_golden.py` pins the absolute
numbers — bit for bit on win32, where the fixture was generated; structure,
±2e-3 cm and areas on Linux (ADR-037 addendum, decision 3). The closed-loop
defect this section used to leave open is fixed (#444): `polyline_footprint` of a
CLOSED polyline still returns an outer ring and a hole — that is the offset's
answer, and the 3D records keep reading it — but the 2D caster walk now repairs
the item's ring set into ONE region before the sweep
(`core.shadow_geometry.shadow_region`: the hole is bridged by a zero-width
slit, a self-crossing outline is split into its lobes). The shadow of a fence
drawn as a closed loop is its stroke, not the slab it encloses: measured, the
10 m × 8 m loop of the reproduction went from 888,037 cm² of shade to 174,526.
ADR-037 addendum "one caster's ring set is one REGION", PF-DOM-28. The self-crossing half is bounded at `MAX_REGION_VERTICES = 256` (a crafted 16,384-vertex outline pays no `SimplifyPolygons` on every walk) and the hole half is not.

**Recompute discipline** for canvas-scale overlays (shadow overlay,
heatmap): precompute on change — `scene.changed` debounced (150 ms) +
`stack_changed` for repaint-less metadata edits — cache the result, and
let `paint()` only draw the cached path. Guard every timer start with
`contextlib.suppress(RuntimeError)` (#230).

**Threaded canvas-scale computation** (US-E4 heatmap; the pattern for any
seconds-scale analysis): snapshot plain data on the GUI thread
(`collect_exposure_snapshot` → `collect_identified_casters` — never live QGraphicsItems across threads),
run a `_WeatherFetchWorker`-shaped `QThread` whose results come back via
signals, paint only `QImage` in the worker (`QPixmap` is GUI-thread-only;
the QImage license is pinned by a 2-thread smoke test), recompute **on
demand only** (a button — never `scene.changed`), and **join the worker
before teardown** (`shutdown()` from `closeEvent`): a `QThread` destroyed
while running aborts the interpreter (#230 class).

**The 3D frame.** The 3D view (the workspace's 3D pane, §8.29) adds ONE more mapping,
applied exactly once, at the engine adapter: scene `(E, N, up)` → engine `(x = E, y = up,
z = −N)` (`core/scene3d/frame.py`, numpy; determinant +1, so triangle winding survives). The
adapter applies it when it uploads a mesh or a pose (`core/scene3d/interleave.engine_buffers`,
`ui/view3d/quick3d/adapter.py`, §8.29.2); nothing else converts a coordinate — not the QML, not a
builder. All mesh math stays in the scene frame, and in the item's local frame beneath it
(§8.29.1), in the Qt-free `core/scene3d/` package; only `ui/view3d/quick3d/` may import Qt Quick
3D (an AST scan over the whole tree). The key light travels along −sun vector
(`SunState.direction_scene`, from `core/solar`), so its ground projection is exactly opposite
the 2D shadow direction — pinned by unit tests — and the engine's shadow covers the ground the 2D
shadow covers (IoU ≥ 0.85 at 15° / 35° / 60°, FR-3D-LOOK-06, on the render tier). If the 3D light
and the 2D overlay ever disagree, a test fails first. (The same single mapping drove the US-E6
viewer on Qt 3D, ADR-038; Phase 17 replaced it, ADR-048.)

**One simulation clock (Phase 17 L1.0, ADR-053).** Every sun- or growth-dependent view reads ONE moment, `GardenPlannerApp._sim_clock` (`core/sim_clock.SimClock`, Qt-free). Two time frames, never mixed:

- **`plan_date`** is the user's LOCAL calendar day: the growth date of shadows, heatmap and 3D. It is *stored as the user picked it*, never derived from an instant. A day taken from a UTC instant is not the user's day: the overlay used `utc.date()` and named another day than the heatmap after local midnight east of UTC. Even a *local* day read back from an instant fails inside a spring-forward gap that straddles midnight (America/Nuuk), so UI writers hand the clock a **naive wall reading** — the toolbar's `datetime_changed` carries one (PF-DOM-22).
- **`utc`** is derived from the stored wall-clock reading and is what `core/solar` takes. PEP 495 `fold` keeps the repeated DST hour exact.

Writers call `set_datetime` / `set_date` / `set_time_of_day`. The clock emits `date_changed(plan_date)` only when the date moved (heatmap stale rule, 3D regrow), then `instant_changed(SimChange)` (overlay re-solve, toolbar mirror, 3D light). A time change can never fire `date_changed` on a wall-reading write: the stored date is the one given. Channels are Qt-like in two respects: a bound method is held weakly (no owner ↔ clock cycle), and every listener runs, with the first error re-raised after the last. Writing the clock from a listener raises. They are **not** Qt-like in a third: nothing disconnects a destroyed QObject. A Qt subscriber disconnects in its own teardown and never connects a bound signal's `emit` (ADR-053 decision 4). A two-way view, like the toolbar, writes back only the fields that changed. New consumers (the L1.3 workspace, L2's day sweep, L5's playback) subscribe; they never keep a private copy of the moment. Plan dates are limited to 1971–2999, because Windows' system-zone conversion raises `OSError` near the 1970 epoch and during 3001.

## 8.21 Icon System (#279, ADR-039)

### 8.21.1 The contract

All chrome icons (main/constraint toolbars, gallery category chips, every
menu action and submenu title, status-bar segments, dashboard tabs, panel
and dialog markers — since #310 the whole chrome, see 8.21.5) live in
`resources/icons/ui/` on one binding contract:
`viewBox="0 0 24 24"`, root `fill="none" stroke="currentColor"
stroke-width="2"` with round caps/joins; colors restricted everywhere to
`none`, `currentColor` (the primary line) and the **accent sentinel
`#3D8B37`** (replaced with the theme's `accent` at render time; it equals
the light-theme accent so raw files preview correctly in editors). No
`<text>` (i18n rule — icons are language-neutral), no rasters, no
`<style>`/`<defs>`/`<g>`. Vendored glyphs come from Tabler Icons (MIT,
pinned release — `PROVENANCE.md` + `LICENSE-tabler-icons.txt`); the rest
are bespoke. The binding house-style contract and the add-an-icon
checklist live in `resources/icons/ui/README.md`.

### 8.21.2 The provider (`ui/icons.py`) — the ONLY render path

QSvgRenderer resolves `currentColor` to **black**, never the palette —
the reason the legacy set carried baked hex overrides (§11.4). The
provider substitutes the active theme's colors into the SVG text BEFORE
rasterizing (`get_icon(name, size=24, color=None)` / `get_pixmap`),
renders at devicePixelRatio (crisp at 125/150 % Windows scaling; the dpr
is part of the cache key, so mixed-DPI monitors stay sharp), adds a
fully-grayed Disabled variant (both tokens → `text_disabled`), caches per
`(name, size, dpr, tint, accent)`, and returns `None` for unknown names so
every caller's text fallback keeps working — for `QAction`s and buttons that
still carry text; the pixmap-only labels of #310 (status bar, collapsible
chevron, crop-rotation status, constraint type) show an empty label instead,
which is why the code→file gate exists. Category chips pass their
muted identity tint (`theme.CATEGORY_ICON_TINTS`) as `color`.

### 8.21.3 Refresh protocol (theme switch without restart)

A theme listener registered at import clears the provider cache on every
`apply_theme()`; the propagation walk (§8.4.3) then calls
`refresh_theme_icons()` on the three toolbars — buttons re-request icons,
`gallery_data.refresh_icon_thumbnails` re-renders icon-derived gallery
thumbnails (species/texture art is theme-neutral and untouched), each
`CategoryDropdown.refresh_thumbnails()` re-pulls its labels — and on the
main window (tracked `_icon_actions` menu replay; since #310 also
`_icon_labels` for status-bar pixmap labels, `_tab_icons` for the dashboard
tabs and the frost badge's last state) and on every panel/widget that
exposes its own `refresh_theme_icons` (layers panel rows, weather card,
calendar dashboard + propagation detail, plant-search filters and rows,
collapsible panels, sun-sim toolbar, constraint rows, journal/companion
rows, season manager, succession notes, the 3D window). **Rule (#310 review):
a widget that bakes a provider pixmap or icon at construction MUST expose
`refresh_theme_icons` — the text glyph it replaced followed the palette for
free, a baked pixmap does not.** Widgets constructed after the switch simply
call `get_icon()` fresh. The properties panel
opts in with a DEFERRED full-rebuild hook (singleShot(0) — never rebuild
form widgets inside the walk that invoked the hook; the #200 focus guard
still protects a focused field).

### 8.21.4 Gates & how to add an icon

`scripts/normalize_icons.py` (deterministic canonicalizer — idempotence
is itself a check; `--check` for CI drift) and
`scripts/check_icon_conformance.py` (contract + PROVENANCE cross-check in
both directions), pinned into pytest by `tests/unit/test_icon_conformance.py`;
end-to-end rendering on both themes + app wiring + live-switch re-tint by
`tests/integration/test_icon_system.py` (§8.10). Adding an icon: vendor
from Tabler (note glyph + release) or author bespoke at 24×24 → run the
normalizer → add the PROVENANCE entry → reference it by name in code →
gates green. **No provenance entry, no merge** (asset-forge discipline).
Since #310 a code→file gate (`tests/unit/test_icon_names_referenced_in_src.py`)
also fails when a literal icon name in `src/` (provider calls, the app's
`_set_action_icon` / `_make_icon_label` / `_set_tab_icon` helpers, `.get(…,
"fallback")` literals, the panels' lookup tables, the toolbar rows and the
built gallery) has no file — the drift that had `properties_panel.py`
requesting a non-existent `lawn.svg` for months.

### 8.21.5 Comprehensive coverage (#310, Package 3c)

Everything the user sees as an icon goes through the provider — there is no
second class of "text glyphs that look like icons". Concretely: every menu
action and submenu title in all six menus (per-format Export glyphs, the
Align/Distribute and Auto-Save submenus, Plants/Garden/Help residue), the
status bar (a 14 px pixmap `QLabel` in front of every segment, tooltip'd,
tracked in `_icon_labels`; the sun-hint icon follows the hint's visibility
via an event filter), the dashboard tabs (`setTabIcon`, tracked in
`_tab_icons`), the frost badge (icon tinted with `on_status`, state kept so
the theme walk re-applies it), the View menu's grouped submenus (Snapping /
Overlays) and the direct 3D View action (ADR-062 removes the former
Sun & 3D submenu and its redundant shadow/simulation toggles), the
layers panel (eye/eye_off/lock/lock_open tinted accent / text_secondary /
warning), the constraints panel (a type-icon column reusing the constraint
toolbar's glyphs; row text is now "A – B   detail"), seed viability, task /
calendar urgency (painted themed dot — a `QPixmap` drawn with `QPainter`, not
a font glyph), go-to arrows, plant-search type filters (`QCheckBox.setIcon`),
weather (condition map returns provider icon NAMES; the widget renders them
and re-renders its last forecast on theme switch), journal photo marker,
companion star, collapsible chevron/info, season manager status, the
sun-sim and soil-overlay toolbars, and the theme's spin-box arrows (path
SVGs — a `<text>` glyph depends on the system font). What deliberately stays
text: arrows inside sentences ("File → Set Location", "A → B: reason",
"pH 5.8 → 6.5" — named exceptions in the static guard, which scans every
string constant — f-string parts and escapes included — of every module
under `src/`, with a named list of exception files), canvas TEXT (dimension prefixes "↔ 1.20 m", the constraint tools'
on-canvas preview labels "≡ H (same Y)" / "⊙ On Circle" / "⦿ Coincident",
the succession badge's bullets — drawn in the app font on the canvas, not
chrome; the one emoji among them, "🔒 Fix in place", is gone because emoji
glyphs are font-dependent), the update banner's external-link arrow ("What's
new ↗", typography), and the combo separator rows ("── Paths ──"). Radio
groups (Theme, Language, Auto-Save intervals) carry the icon on the submenu
title only. The 3D window's Refresh/Walk toolbar, the crop-rotation status
prefix and the constraint rows' delete "×" were the last text-only
controls; all are iconized.

## 8.22 Plant Sprite Pipeline (#281, ADR-040)

### 8.22.1 One generator, 123 artifacts

Every SVG under `resources/plants/{species,categories}/` is produced by
`scripts/generate_plant_sprites.py` — a seeded, deterministic generator whose
recipe tables (archetype + palette + signature features per species) are the
actual source of the plant art. Since Phase 17 L1.7 the tables themselves live
in `core/plant_art/recipes.py`, shared with the 3D plant builder (§8.22.4); the
script keeps the drawing code. The committed SVGs are build artifacts:
`--check` and `tests/unit/test_plant_sprite_conformance.py` fail on any byte
drift, which also makes hand edits impossible to land. The binding style
contract lives in `resources/plants/README.md` ("Lush Sprite", user-approved
2026-07-26): shingled leaf rings, per-leaf tip→base gradients, occlusion
under every leaf, glossy fruit / chunky bloom clusters, signature
recognition cue per species. Ball-shaped canopies/mounds use **dome
foreshortening** (manual-test refinement on PR #282): leaves are largest at
the crown and radially compressed + denser toward the rim —
`sqrt(1-(rho/R)^2)` per fixed dome latitude, leaf count from the ring
circumference — so the canopy reads as a sphere seen from above. Flat
growth forms (rosettes, grass tufts, narrow-leaf cushions like lavender)
are exempt from the foreshortening: their outer leaves really are the big
ones. Star-form archetypes were reworked in the same manual-test round:
conifers are interleaved serrated branch-whorl layers (not a flat
thin-leaf star), grass/fern species are fields of clumped tufts over a
dark grounding mass (not a single center starburst), and alliums/corn are
dense double-layer fountains. The on-canvas hedge (HEDGE_POLYGON) fills
with `resources/textures/hedge.png`, regenerated in the same leaf language
via `scripts/generate_asset_forge_textures.py` (tileability-gated) — the
`hedge_section.svg` sprite only serves the plant category + legacy
rectangles. Independent of archetype, SMALL leaves everywhere (length < 12 units)
drop their frilly occlusion underlay and vein lines — a byte-budget
optimization that is visually invisible at canvas scale but does slightly
simplify e.g. rosette outer rings (visible on the sign-off contact sheet).

### 8.22.2 The two invariants

**Rotation safety**: `core/plant_renderer.py` rotates each plant by a stable
per-item random angle, so sprites are top-down with radial shading only
(light from straight above) — never a baked light direction.
**QtSvg subset**: QSvgRenderer ≈ SVG 1.2 Tiny — linear/radial gradients,
opacity, transforms, stroke-linecap; no filters, masks, clipPath, CSS or
text (enforced by an element/attribute/color **allowlist walk** over the
parsed tree in the conformance gate). The one geometry
exception: `hedge_section.svg` keeps its legacy rectangular viewBox
`10 25 80 50`.

### 8.22.3 Changing a sprite — the loop

Edit the recipe → regenerate → **visually review with the real engine**
(QSvgRenderer offscreen grids at 256/64 px — see the `ogp-asset-forge`
skill's "SVG sprite forge" section; never judge by XML or a browser render)
→ run the two gates (`test_plant_sprite_conformance.py`,
`tests/integration/test_plant_sprite_rendering.py` — the §8.10 test renders
every sprite to visible pixels through `render_plant_pixmap`, including
tint, rotation and the 16 px growth-model size) → owner sign-off on a
contact sheet for style-level changes. The recipe is in
`core/plant_art/recipes.py`; a new species additionally needs its names in
`SPECIES_SPRITES` (`core/plant_art/resolve.py`) — and both edits reach the 3D
view as well (§8.22.4).

### 8.22.4 One recipe table for 2D and 3D (Phase 17 L1.7, ADR-059 addendum)

`core/plant_art/` is the Qt-free, standard-library-only home of everything that
says what a plant looks like (an AST scan in `tests/unit/test_plant_art.py`
pins the import rule). Standard-library-only is a rule about the package's own
source files, not about importing them: `import open_garden_planner.core.plant_art`
runs `core/__init__.py`, which loads PyQt6 for other `core` modules. The sprite
generator therefore executes `recipes.py` **by file path** (`_load_recipes`) and
still runs on a Python without Qt, as it did when the tables lived in it — a
test runs it with PyQt6 and numpy blocked. (The first version imported the
package by name; it produced the same bytes and needed Qt for the first time.)

| Module | Holds | Read by |
|---|---|---|
| `recipes.py` | `PALETTES`, `FRUITS`, `FLOWERS`, `SPECIES`, `CATEGORIES` (moved verbatim, order included), `palette_key(recipe)`, `FEATURE_KEYS`, `ARCHETYPES` | the sprite generator (by file path); the 3D plant builder |
| `resolve.py` | `SPECIES_SPRITES`, `CATEGORY_SPRITES`, `DEFAULT_CATEGORY`, `PLANT_KINDS`; `resolve_sprite(kind, species, category, available=…)`, `resolve_recipe`, `recipe_for` | `core/plant_renderer`; the 3D plant builder |

**One rule decides a plant's sprite.** `resolve_sprite` is the 2D resolution,
corrected in #446: the species sprite (the species string normalised - lower
cased, blanks collapsed, `-` and `_` read as blanks - and matched as a WHOLE
name or alias: the name itself, else a key whose every word is a word of the
name, else a key that holds every word of the name), else the sprite of the
plant's category, else the sprite of its object type's default category. `available` says whether a candidate exists — the renderer
passes "the SVG file exists", the 3D builder "the tables hold a recipe"; a
candidate that does not exist is skipped and the next rule applies. Kinds and
categories are plain names (`"TREE"`, `"PALM"`): `core/object_types` imports Qt.

The rule was extracted, not improved - and then it WAS improved (#446): the
substring match is gone, and a name is matched as a whole name or alias. A
whitespace-only species is no species (it takes its category's sprite), "Melon"
is no longer the eggplant's, and "Petroselinum crispum" is the parsley's. What
survives is pinned in `tests/unit/test_plant_art.py`: "Lemon Balm", "Bean
(Bush)" and "Sweet Potato" still take a fruit or vegetable sprite, because their
names contain a whole word that is another plant's name - a curated alias table
would fix them and was declined. The golden
(`tests/fixtures/plant_art/sprite_resolution_golden.json`, 1,562 answers) is
regenerated from the rule, and the rule it replaced is kept as `legacy_resolve`
in the golden's generator. Changing the rule changes what users see on the plan.
What the 3D view builds for a plant is the recipe of the sprite the plan shows;
if the sprite is wrong, fix the rule here, once.

**The same rule on the same inputs.** One rule is half of it; the 2D renderer
and the 3D builder must also hand it the same three things: the item's type, the
item's OWN species string exactly as it is (`item.plant_species` — not stripped,
and not the species data's name) and its plant category. The record carries
that string as `params["sprite_species"]` for this purpose alone. The first
version of the builder resolved from `species_name`, which prefers the species
DATA's common name — and a gallery Pumpkin, whose bundled data is named "Winter
Squash", was drawn as a pumpkin and built as a squash (PF-L3D-01). A species
ASSIGNED from the plant database writes the item's string (#445), so the
assigned species is the one both views draw and build.

**The golden has a generator.** `scripts/make_sprite_resolution_golden.py` keeps
the rule statement for statement, with the question list; `--check` regenerates
the 1,562 rows, and `--differential` holds the production rule AND the renderer
(with `Path.exists` patched) against that copy with sprite files missing — each
of the 123 in turn, random sets, all species, all categories: 481,096
comparisons, none different. The rule #446 REPLACED is kept there as
`legacy_resolve`, and `--legacy-diff` prints what the change did to every case
(74 answers over 37 names). With every file
shipped, nothing else ever asks whether a file exists: dropping the renderer's
`available=` survived 3,048 tests until the missing-file cases were written.

**Byte identity on Windows.** With `core.autocrlf=true` the SVGs in the working
tree end in CRLF, so a raw byte diff of the generator's output against the
files on disk reports all 123 as different. The committed blobs are the
reference (`git cat-file blob HEAD:<path>`); the conformance gate compares
text, which is newline-agnostic.

## 8.23 Object Sprite Pipeline (#308, ADR-042)

### 8.23.1 One generator, 24 artifacts

Every SVG under `resources/objects/{furniture,infrastructure}/` is produced by
`scripts/generate_object_sprites.py` — a seeded, deterministic generator whose
`MATERIALS` anchor table + material primitives + one builder per object are
the actual source of the furniture/infrastructure art. The committed SVGs are
build artifacts: `--check` and `tests/unit/test_object_sprite_conformance.py`
fail on any byte drift, which also makes hand edits impossible to land. The
binding style contract lives in `resources/objects/README.md` ("Lush Object"):
rim-dark → crown-light shading per part (symmetric linear gradients across a
part's short axis, radial for round parts), occlusion halos where parts
stack, material micro-detail (plank gaps + grain + knots, brushed-metal crown
line, weave hatch + puff shading, ripples + caustic sparkles, granular clumps),
gloss on glossy materials. The primitives are reusable building blocks —
`plank`/`wood_surface`, `disc`/`ring`, `fabric`, `metal_bar`, `glass_pane`,
`water_fill`, `granular_fill`, `glow`/`flame`, `frame_box` — so a new object
is typically 20–40 lines composing them; rings are two-subpath paths (nonzero
winding) and circle-clipped planks are computed analytically because QtSvg
has no clipPath.

### 8.23.2 The three invariants

**No baked shadow / light from above**: furniture rotation is USER-controlled
(unlike the plants' stable random rotation), so a baked directional shadow
would rotate with the object and double the item-level painted shadow
(`GardenItem.SHADOW_OFFSET`, View › Shadows). The gate pins the legacy
`#00000020` shadow's absence. **QtSvg subset**: same allowlist discipline as
§8.22.2 (elements/attributes/colors walked over the parsed tree; `fill-opacity`,
`stroke-linejoin` are additionally allowed here). **viewBox = nominal footprint**:
each sprite's `viewBox` is `0 0 W H` with `(W, H)` = `FURNITURE_DEFAULT_DIMENSIONS`
in cm — a gate-read metadata table (no production code sizes objects from it;
users size by dragging), pinned by the gate — the canvas stretches the art to
the user's rect; circle-tool objects (`table_round`, `parasol`, `fire_pit`, `planter_pot`,
`bbq_grill`, `rain_barrel`, `water_tap`, `trampoline`, `bird_bath`) therefore
ship **square** art (a circle item renders into a square footprint — the BBQ's
old 80×60 art was stretched on every canvas until #308).

### 8.23.3 Changing or adding an object — the loop

Edit/add the builder + `OBJECTS` row → regenerate → **visually review with the
real engine** (QSvgRenderer offscreen: canvas scale on lawn + soil, rotated
copy, 64/24 px thumbnails — see the `ogp-asset-forge` skill's "SVG sprite
forge" section; never judge by XML or a browser render) → run the two gates
(`test_object_sprite_conformance.py`; `tests/integration/test_object_sprite_rendering.py`
— the §8.10 test renders every sprite through `render_furniture_pixmap` within
the visual-weight band, at 24 px, checks letterboxed thumbnails, and drives
every new tool end-to-end) → owner sign-off on a contact sheet for style-level
changes. **Adding an object type** touches exactly these surfaces (verified
2026-08-17, ADR-042): `core/object_types.py` (enum member appended, `OBJECT_STYLES`
entry — its `fill_color` is the 3D extrusion colour —, `get_valid_types_for_shape`
branch), `core/tools/base_tool.py` (`ToolType`, same name), `ui/canvas/canvas_view.py`
`_setup_tools` (rect/circle furniture or infrastructure list), `core/furniture_renderer.py`
(`_FURNITURE_FILES` for furniture-dir types; infrastructure-dir types need
`_INFRASTRUCTURE_FILES` **and** `_SVG_DIR_OVERRIDES` **and** `_OBJECT_SVG_FILES` —
the gate checks all three; plus `FURNITURE_DEFAULT_DIMENSIONS`), `core/object_height.py`
(`DEFAULT_HEIGHTS_CM` — gives shadows/3D/height field; every object that stands
up needs a row, open frames included, and
`test_every_standing_object_kind_has_a_default_height` fails without one: ADR-065,
owner's second pass), `ui/widgets/gallery_data.py`
(gallery tuple), and `scripts/fill_translations.py` in the `CanvasView`,
`GalleryData` and `ObjectType` contexts. Roster tests are map-driven; the
additive-enum forward-compat contract (unknown names → generic shape, no
FILE_VERSION bump) is pinned by `tests/unit/test_project_unknown_object_type.py`.

## 8.24 Texture Forge Pipeline (#309, ADR-042)

### 8.24.1 One generator, 24 artifacts

Every PNG under `resources/textures/` is produced by
`scripts/generate_asset_forge_textures.py`: one `generate_<name>(rng)` recipe
per texture over a shared **numpy torus painter** (`Tile`). The painter works
in float64 on a 2×-supersampled canvas whose windows are indexed modulo the
tile size — every primitive (`ellipse`/`blob`/`halo`, `capsule`, `rect`
including full-height planks, `leaf`, `vgrain`) computes analytic
anti-aliased coverage and paints with radial rim → crown shading, so anything
crossing an edge simply continues on the opposite side; noise fields
(`lattice_noise`, `fbm`, `fine_grain`) are periodic lattices, `voronoi` uses
the torus metric (with an optional periodic domain warp for organic slab
edges), and `wrap_blur` is an in-repo separable Gaussian built on `np.roll`.
Structured layouts (brick courses, planks, laths, panes, roof courses) divide
256 exactly, so a joint or bar either **straddles the wrap symmetrically**
(brick/stone/slate courses, the glazing bars — the painter samples at
pixel centres everywhere (windows, analytic fields, noise, Voronoi), so the
wrap sits exactly on the joint's mirror line and the two sides are
identical: glass 0.00/0.00, brick 0.04/0.08)
or lies **clear of it** (wood/decking plank joints at half-pitch offsets);
what must never happen is a joint landing *near* the wrap asymmetrically.
The roof's bottom course repaints its wrapped overhang — with the same RNG
state the row was drawn with, pinned by reading the rng stream
(`TestRoofTileOverhangReplay`) because no seam metric can see a tone
mismatch on a texture full of hard edges — so the overlap layering AND the
per-tile tone are seam-correct. Know what the gates catch: the seam metric
catches broken tiling, the band catches flatness, the pixel gate catches
drift; layering, replay and light-direction defects are found by reading
code and by the owner's eye (both #309 review rounds found one each). All randomness
flows through `random.Random(seed_for(name))` (`"ogp-<name>-lush"`), which is
stream-stable across CPython versions; no numpy RNG, no rasterizer, no
Pillow filter is involved — Pillow only encodes/decodes PNG. The binding
style contract ("Lush": visible detail, radial shading, concentric occlusion,
tint-readable contrast, no directional light) is the `ogp-asset-forge`
skill's §1; provenance is `resources/textures/PROVENANCE.md`.

### 8.24.2 The three invariants

**Pixel determinism, not byte determinism**: `--check` regenerates in memory
and compares the DECODED pixels of each committed PNG (pinned per file by
`tests/unit/test_texture_forge_conformance.py`). PNG is lossless, but the
deflate stream depends on the zlib build Pillow bundles — a Windows wheel and
a Linux CI wheel can encode identical pixels to different bytes — so file
bytes are deliberately not the contract, and regeneration rewrites a file
only when its pixels change (no cross-platform git churn). **Seamless on the
canvas**: `scripts/check_texture_tileability.py` (seam vs the 98th percentile
of the texture's own internal steps, threshold 1.6 unchanged since #264) must
pass for every file (`tests/unit/test_texture_tileability.py` parametrises
all of them — the #264 grandfather list `KNOWN_SEAMED_LEGACY` was emptied
and then deleted, a constant that must stay empty being ceremony), and the
§8.10 test paints the item's real tinted brush two tiles wide and checks the
wrap column AND wrap row against the same metric. **Tint-readable**: the runtime recolour is a luminance map (`_tint_texture`,
#502): each pixel becomes the user's fill colour scaled by the texture's relative
luminance, so the chosen colour reads as itself and the material's detail survives;
the conformance gate pins mean luminance 40–225, luminance
std ≥ 4 and local detail ≥ 2 per texture, and the integration test proves a
**pale** fill colour (the light green that read as the standard brown roof tile
before #502), a red and a blue one each move the rendered hue without flattening the
detail (materials that would collapse under tint fail before an owner sees
them). A fourth rule is not gated but binding: **no directional light** — the
view flips Y and fills never rotate, so every shading cue is radial or
concentric.

### 8.24.3 Changing or adding a texture — the loop

Edit/add the recipe + `TEXTURES` row → run the generator (only changed files
are rewritten) → **look**: a 2×2-tiled half-scale sheet (seams, repetition)
plus 1:1 crops (detail), and the tint check with the object's real default
fill colour → run the three gates (`--check`, tileability, the §8.10 test) →
owner sign-off on a contact sheet for style-level changes → PROVENANCE
register row. Adding a texture additionally touches `core/fill_patterns.py`
(`FillPattern` member + `_TEXTURE_FILES`), the properties panel's
`_pattern_names` (translated), and `scripts/fill_translations.py`; the
conformance gate cross-checks registry ↔ loader table ↔ files on disk. A
seam that the gate reports is located by measurement, not theory: the
per-column `|row0 − row255|` (or the transpose) names the columns, and
painting the suspect primitive alone on a fresh `Tile` confirms it
(2026-08-18: a capsule whose default `taper` pointed every joint line —
§11.4, debugging-playbook row 36).

## 8.25 Stacking order within a layer (#338, ADR-043)

### 8.25.1 Model

Every document item that carries a `layer_id` also carries a sparse integer
**rank**, `stack_order: int | None` (`GardenItemMixin.stack_order`; mirrored
independently on `ArcItem`/`BezierItem`, which are not the mixin). A rank is
a **sort key**, not a display value — nothing renders it, and its absolute
magnitude is meaningless, only its ordering among the other items in the same
layer. Ranks are spaced `STACK_STEP = 1024` apart (`core/stacking.py`) so
inserting between two existing ranks never forces an immediate renumber in
practice.

**Ranks are written in exactly four places** — everywhere else only reads
`stack_order`:

1. `CanvasScene.addItem` — an item whose `stack_order is None` gets
   `max_rank_in_layer + STACK_STEP` (`_next_stack_order`).
2. `MoveToLayerCommand.execute` — only items whose layer actually changes get
   a fresh top rank in the target layer; an item already in the target layer
   is left completely alone (re-selecting an item's current layer, e.g. via
   the Properties panel combo, is a true no-op, not a silent bump to the
   top).
3. `ArrangeItemsCommand.execute` — renumbers every top-level item in each
   affected layer to `STACK_STEP` multiples in the new order; `undo` restores
   every snapshotted rank exactly (see 8.25.4).
4. `CanvasScene.suspend_z_refresh(renumber=True)` — the one-time post-load renumber
   (`ProjectManager.load` wraps its item-creation loop in that context manager).
   This is what gives a file saved without `stack_order` keys — an older app
   version — honest, evenly-spaced ranks the first time the current app opens it.

A `layer_id` of `None` (no active layer at drop time, or a bare item without
one) is ranked in its own pseudo-layer at base z 0 — the band such items
always occupied — so the derive-only clamp (8.25.3) still applies to them.

### 8.25.2 Derived z — the formula

z-values are **never** stored as intent; they are recomputed from the current
ranks on demand. `CanvasScene._layer_top_level_items(layer_id)` collects one
layer's top-level items (`parentItem() is None`, matching `layer_id`), sorted
by `(stack_order is None, stack_order, current scene index)` so an unranked
item sorts to the top of its band. `_stack_entries` turns that list into
`core.stacking.StackEntry` objects (id, plant-parent/owner-polygon id, scene
bounding rect). `_normalized_layer_order(layer_id)` runs those entries through
`core.stacking.normalize_order` (8.25.3) and maps back to live items.
`_refresh_layer_z(layer_id)` then assigns:

```python
item.setZValue(layer.z_order * 100 + 100 * (i + 1) / stacking.Z_POSITION_SCALE)
```

over that normalized bottom→top order (`i` = 0-based position), for
`layer_id = None` the base is `0` instead of `layer.z_order * 100`.
`Z_POSITION_SCALE` is a **fixed** divisor (`1 << 24`), not `n + 1`: the band is
an ordering interval, not a spread that must be filled, so an appended item can
receive its final z without re-deriving every existing item (#450). The fraction
is strictly inside `(base, base + 100)` for up to about 16.7 million ranked
items — it can never touch `base` or `base + 100`, so a layer's items cannot
collide with a neighbouring layer's band or with any fixed overlay band
(8.25.6). **One accepted exception:** the `layer_id = None`
pseudo-layer shares base `0` with a real layer whose `z_order == 0` (the
default single layer every new plan starts with) — an item with no layer and
an item on that first layer can land at the same derived z. This only
matters for items reachable via a pre-#338 `.ogp` that never set `layer_id`;
current code always assigns one on `addItem`. Not fixed, since separating
the bands would need a second special-cased offset for one legacy edge case. `_update_items_z_order()` is unchanged in name and
callers — it just now loops every layer (plus the `None` pseudo-layer) and
calls `_refresh_layer_z` on each, instead of a single flat pass.

**Ground surfaces take the same value moved below the sun study's overlays**
(manual pass of PR #584). A lawn, path, terrace, driveway, pond or in-ground bed
with no height of its own (`core.object_height.lies_on_ground`), or a group made
only of those (`canvas_scene.on_ground`), gets `ground_z(z)` instead of `z`: a strictly increasing map of every real number
into `GROUND_Z_RANGE = (-990, -510)` (`canvas_scene.py`). So a shadow (`-500`)
and the hours-of-sun map (`-450`) lie ON the ground surfaces, under everything
that stands on them, and the ground surfaces keep their order among themselves —
by layer, then by rank — however many layers there are. Arrange works inside a band (8.25.5): a
ground surface brought to the front is the front-most GROUND surface of its
layer, still drawn under the layer's other items (the agent's `stack_index`, "as
displayed", says so). Before, both overlays sat under every layer item and a
lawn hid them.

### 8.25.3 The derive-only clamp

`core.stacking.normalize_order` enforces two structural relationships,
**purely for z derivation** — it reorders a layer's list, it never writes a
rank:

- A plant always renders immediately above the parent it stands in: its **link**
  (`_parent_bed_id`) when that parent is in the same layer's list, else — with no
  link — the **smallest** plant-parent of the layer whose outline contains the
  plant's stable centre (`footprints.standing_point`, the point the lift and the
  sun estimate ask; #629, FR-STACK-10). One answer
  (`CanvasScene._derived_plant_parent`) serves both the derivation and the
  per-command check below, so a bed drawn around a standing plant captures it
  without a link (#443). A parent in a different layer is ignored, and the plant
  sorts as an ordinary top-level entry by its own rank. Since the ground band
  (8.25.2) the list is one BAND of the layer: a plant on an in-ground bed is above
  it by the band, and only a parent of the plant's own band can be its parent.
- A `ROOF_RIDGE` always renders immediately above its owner polygon, under
  the identical same-layer-only condition.

Because this is a reorder-for-display step and not a rank mutation, "Send to
Back" on a lone plant does not reach the true bottom of its layer — it stops
just above its bed, and if it is already there the arrange algorithm reports
"already at back" rather than a phantom change (`core/stacking.py::_finish`
compares the candidate *after* normalization against the *already-normalized*
input, so the clamp collapsing a move to a no-op is visible as exactly that).
Group/Ungroup keep a member's `stack_order` unchanged across the transition —
grouping and ungrouping is a reparent, not an arrange. This is the one
documented exception to the exact round-trip claimed in 8.25.1/FR-STACK-06:
because an ungrouped member keeps its stale pre-group rank instead of being
re-ranked into the current sequence, it can end up tied with an unrelated
item created while the group existed, and that tie is broken by current
scene order rather than by the original session's order.

### 8.25.4 Refresh rules

**A single `CanvasScene.addItem` leaves the correct, final z immediately**
(#450). An appended independent solid gets the next value on the fixed
`Z_POSITION_SCALE` grid inside its layer band — exactly the value the
derivation would assign it — so it is never re-derived; one derivation per
layer serves a whole add loop. Any item that can re-order existing items — a
pre-ranked re-add, a child, a bed with children, a plant (linked, or a parent that
captures it), a roof ridge,
or a ground surface (which sorts into its own band, §8.25.2) — runs
`_refresh_layer_z` synchronously instead. Every derivation reseeds the per-layer
provisional cache; a full `_update_items_z_order` sweep clears both it and the
rank cache. Arrange, move to layer, adding/deleting/reordering layers, and the
flatten direction of group/ungroup run that sweep; the group-forming direction
relies on `addItem`'s append, and relinking refreshes one layer through
`_refresh_layer_z` (the sweep when the item has no layer). Either way the next
add reseeds from the real top rather than resurrecting a stale value. There is
no deferred pass and no command-boundary flush: what `addItem` writes is final,
which is why 2 000 single adds (and 2 000 single-item commands) cost one
derivation, not 2 000 (the pre-#450 loop took 45 s).

The bulk scopes remain the way to suspend even the remaining per-add work. Two
ways to set `scene._suspend_z_refresh`:

- `scene.suspend_z_refresh(renumber=True)` — used by
  `ProjectManager.load` around its whole item-creation loop.
  `renumber=True` additionally does the one-time post-load renumber
  (8.25.1 point 4) before its one full refresh.
- `with scene.suspend_z_refresh(): ...` (a context manager; nests safely) —
  used by every command that re-adds several items on `execute`/`undo`
  (`CreateItemsCommand`, `DeleteItemsCommand.undo`, `MirrorItemsCommand`,
  `LinearArrayCommand`, `GridArrayCommand`, `CircularArrayCommand`,
  `ArrayAlongPathCommand`) via the shared `core.commands._bulk_add_scope`
  helper. `suspend_z_refresh(renumber=True)` is reserved for the file-load
  path only — every bulk re-add path must pass `renumber=False` (the
  default), because renumbering would silently overwrite the exact ranks a
  command's undo/redo snapshot depends on being restored unchanged.

Without this, a bulk add would trigger one O(layer-size) refresh **per item**
— O(n²) for a paste of n items into a large layer. Measured: a 50-item paste
into a 2000-object plan went from 316 ms to 91 ms. The same quadratic shape
applied to a loop of single `addItem` calls (2 000 items: 45 s, issue #450;
measured about 0.1 s with the fixed-grid derivation, without changing any rank).

**The refresh itself never writes a rank — ever.** This was a real draft
design, caught in review before it shipped (see the rejected alternative in
ADR-043): a refresh that also renumbered ranks as a side effect would silently
invalidate any command's undo snapshot taken before a refresh happened to run
in between — since the refresh runs on many paths unrelated to an explicit
arrange (layer visibility toggle, opacity preview, any command's unrelated
cleanup). Only the four writers in 8.25.1 ever touch `stack_order`.

**A command can move an item between the bands** — a type change makes a shed a
lawn, a group of lawns is made or broken. `CanvasScene._restack_ground_changes`
refreshes each layer holding an item whose band no longer matches `on_ground` after
an executed, undone or redone command (`stack_changed`, wired in
`set_command_manager`). It costs about 1 ms on 500 items and restacks nothing when
nothing moved between the bands.

Since #592 that scan runs **only when the command can reclassify something**. The
base `Command.changes_ground_band` is `True`, so an unclassified or future command
keeps the safe scan; the move/resize/rotate/vertex/curve/copy/link/constraint
commands say `False`. Create is neutral because `addItem` takes the synchronous
derivation for a ground surface and bulk adds end in `_update_items_z_order`;
Delete/Group/Ungroup/Boolean/ChangeProperty keep the scan. The
same command-boundary work included the lock badge: `update_dimension_lines` used
to call `refresh_lock_badge` on every item, and each call walked the whole
constraint dict — 600 single-item commands produced 360 600 badge refreshes on a
600-item plan. `ConstraintGraph.fixed_item_ids()` gives the set of items that can
carry a badge; the loop refreshes those plus any item already showing one (so an
unlock clears it) and skips everything else. Measured on the dev box, 600 single
adds: 0.31 s → 0.11 s; the pin counts zero classification calls and zero badge
refreshes for a neutral command, and still pins the badge and the band change.

**A command can also change which parent CONTAINS a plant** (#629): it can resize,
move or vertex-edit a bed around a standing plant, or carry a plant into one.
`CanvasScene._restack_plant_containment` runs on the same `stack_changed` signal and
re-derives only a layer whose drawing disagrees with the derivation — it compares each
plant's z against the parent `_derived_plant_parent` names, so the check cannot drift
from what it checks (a plant above the layer's HIGHEST parent costs one z comparison and
nothing else — the per-plant test is against that top, not against its own parent; a plant
linked to a parent of its own band costs nothing more, because the band-local index
resolves the link before any geometry — a link into the ground band falls through to the
centre, as for an unlinked plant). Only a parent
of the plant's own band counts: an in-ground bed lies under the plant by the band, not
by the clamp, so asking about it would re-derive on every command and never change
anything. `Command.changes_containment` follows #592's shape: the base is `True`, and
the three neutral commands (`CreateItemCommand`, `CreateItemsCommand`,
`DeleteItemsCommand`) say `False` because `addItem` derives an arriving parent
synchronously and a deletion cannot newly hide a plant. Cost, measured on the dev box:
0.9 ms on the 990-item reference plan, 1.1 ms for 300 linked plants in 30 beds, 2.8 ms
for the same garden unlinked, and 30 ms for the adversarial case — 200 plants under 50
concave 200-vertex beds whose bounding boxes all cover the plants. The parents' shapes
are cached for the pass, as `ItemLookup.shape_of` caches them for a walk: without that
cache the adversarial case cost 330 ms, and 1.7 s at 1 200 vertices.

Beyond `addItem`'s automatic refresh, an **explicit** refresh is needed
wherever an item becomes top-level or gets re-linked to a parent without
going through `addItem`: `GroupCommand.undo`/`UngroupCommand.execute` (members
leave the group), `_auto_parent_plant` and `SetParentBedCommand` (attach/
detach a plant), and `DeleteItemsCommand.undo` — unconditionally, whenever it
restored anything, not only when a bed's child list was touched: an undone
PLANT delete restores `parent_bed_id` alone with no bed-side relink, and a
flag gated on the child-relink branch missed that case and left the plant's
z stale below its bed (issue #338 review round 3, P0).
These call `core.commands._refresh_z_after_relink` (single item) or
`scene._update_items_z_order()` (whole scene) — never an explicit z bump. The
old `ensure_z_above_parent(child, parent)` helper — which raised a child's
`zValue()` by one above its parent's whenever they tied — is **deleted**: its
job is now done for free by the derive-only clamp every time the scene
refreshes.

### 8.25.5 The one apply seam

`ui/canvas/arrange.py::build_arrange_command(scene, items, mode) -> tuple[ArrangeItemsCommand | None, ArrangeOutcome]`
is the **only** place that groups a selection by layer, reads each layer's
current order via `scene._band_entries`/`_normalized_layer_order`, asks the
Qt-free `core.stacking.arrange` what changes, and builds the undoable
`ArrangeItemsCommand`. Every surface that can arrange an object calls this one
function — the same discipline `ui/canvas/geometry_apply.py` established for
resize/rotate (§8.19) and for the identical reason: a `Callable`/copy-per-call-site
pattern is how the three rotated-geometry bugs in §11.4/ADR-036's D2.2 story
happened. The four callers:

1. `CanvasView.arrange_selected(mode)` — the Edit ▸ Arrange menu actions and
   the two keyboard-shortcut sets both call this.
2. `GardenItemMixin._build_arrange_menu`/`_dispatch_arrange` — the `Arrange ▸`
   context-menu submenu, shared by every item class that already has the
   `_build_move_to_layer_menu` seam (rectangle, polygon, polyline, circle,
   ellipse, text, callout, group, smart symbol). Delegates to
   `CanvasView.arrange_selected` when a view is available (so status messages
   have exactly one source), falls back to a direct build+execute for
   view-less unit-test construction.
3. `PropertiesPanel._add_arrange_section` — the "Arrange" row (four icon
   buttons), shown for a single selected item and for a multi-selection.
4. `GardenPlannerApp._do_agent_arrange_object` — the Agent API's
   `arrange_object` tool (§8.19).

**Arrange works inside a band** (manual pass of PR #584). Ranks order an item
only among its own band (8.25.2). `CanvasScene._band_entries` is the ONE split of a
layer into its bands, ground surfaces first: `_normalized_layer_order` (the drawing)
normalizes each band alone, and `build_arrange_command` arranges each band of a
layer's selection on the same split — `core.stacking.arrange` over that band's
entries — and hands the command the layer renumbered ground surfaces first. A
recorded step is always visible; at the edge of its band an item reports "already at
front/back". **The rule this rests on:** any reader of a layer's stacking order goes
through `_normalized_layer_order` or `_band_entries`, never `_stack_entries` over a
whole layer — the second review round of the manual pass found exactly that
disagreement (a perennial on an in-ground bed moved under a tree by an unrelated
arrange).

No caller ever builds `ArrangeItemsCommand` directly, or duplicates
`build_arrange_command`'s layer-grouping logic. If you find yourself reaching
for a second implementation, use this seam instead.

### 8.25.6 Reserved z bands

Every fixed-z overlay in the app, low to high, alongside the per-layer band
§8.25.2 derives into:

| Band | z value(s) | What lives there |
|------|-----------|-------------------|
| Background image | `-1000` | `BackgroundImageItem` (satellite/reference photo) |
| **Ground surfaces** | `(-990, -510)` (open interval, `GROUND_Z_RANGE`) | Document items that are `on_ground` (a lawn, path, terrace, driveway, pond or in-ground bed with no height, or a group of only those), their layer z mapped by `ground_z` (8.25.2) — under the two sun overlays |
| Sun & shade shadow overlay | `-500` | `sun_shadow_controller.py`'s shadow-union overlay (US-E3) |
| Hours-of-sun heatmap | `-450` (fill), `-449` (contour lines), `-448` (contour labels) | `sun_heatmap.py` overlay (US-E4) |
| Construction geometry | `-10` | `ConstructionItem` — below every regular item except the ground surfaces, which it draws over (before the ground band it hid under a lawn) |
| **Per-layer document items** | `layer.z_order * 100 + (0, 100)` (open interval) | Every ordinary document item, per-object stacking order within its layer (8.25.2) — this is the band #338 subdivides |
| Dimension/constraint lines | `900` (line/witness), `901` (label/handle, `DIMENSION_LINE_Z + 1`) | `dimension_lines.py` |
| Tool overlay highlights | `999` (corner-edit/trim highlight), `1000` (measure-tool line, on-top ellipse), `1003` (constraint-tool selected marker) | `core/tools/*` in-progress-gesture previews |
| **Shape-tool preview band** | `999` (fill), `1000` (line/path), `1001` (label), `1002` (vertex/handle) — `core/tools/preview_z.py` | The in-progress preview of every shape tool (`circle`, `rectangle`, `ellipse`, `polygon`, `polyline`, `arc`, `bezier`, `mirror`, `callout`, `select`, `construction`). Issue #377: these previously had **no** z-value and drew behind any bed they overlapped. Every value MUST stay below the minimap cutoff below. |
| Transient previews | `9999` | Offset-tool preview path, paste/duplicate drag preview |
| Soil health badge | `10002` | `SoilBadgeItem` (always on top of its bed) |
| Minimap overlay-hide cutoff | `10000` (`minimap_widget._OVERLAY_Z_MIN`) | Threshold above which the minimap thumbnail hides an item as a screen-space overlay (§8.9.5) — a named constant, not a bare `100` (see the corrected note in §8.9.5) |

**`JournalPinItem` is NOT a fixed-z overlay, despite its constructor calling
`self.setZValue(9_500)`.** It is a `GardenItemMixin` with a `layer_id` and a
`stack_order`, so `supports_stacking(pin)` is True and `_refresh_layer_z`
overwrites that 9500 the moment the pin (or any sibling in its layer) is
added — a pin can end up rendering *behind* an ordinary item in the same
layer. Verified: a lone pin lands at `z=50.0`; adding one more layered item
drops it to `33.3` while the new item sits at `66.7`. This is **pre-existing**
(unbumped by #338 — `CanvasScene.addItem` already clobbered the 9500 to
`layer.z_order * 100` before this PR), not a new regression, but it means the
9500 constant is dead for any pin that has a layer. Journal pins are
deliberately excluded from Arrange (`ui/canvas/arrange.py`) and from the
agent's `arrange_object` tool, but nothing today re-asserts their z above the
document band once one is set. Fixing this — either exempting pins from
`supports_stacking` or giving them a real fixed post-refresh bump — is
tracked as follow-up work, not part of #338.

A per-layer band can, in principle, grow past `z_order * 100 + 100` only if
`z_order` itself is large enough to reach the next fixed band above — not a
concern at the layer counts this app supports, and unchanged by #338 (the
formula was already `layer.z_order * 100` before per-object stacking; #338
only subdivides the same band, it does not widen it).

## 8.26 Recorded permaculture traits and guild templates

Species traits are curated facts/design annotations, not a planting-success score. `unknown` and empty functions mean no recorded fact. Botanical niche is independent of the illustration category and drawing layer. `scripts/curate_permaculture_traits.py` is the explicit reviewable assignment table for all 118 bundled species: tall woodland/walnut trees use canopy; fruit/smaller ornamental trees sub-canopy; woody bushes/subshrubs shrub; selected low spreading plants ground-cover; harvested underground crops root; climbing/trailing crops vine; remaining herbaceous crops/bulbs/flowers herbaceous. This is a representative food-forest niche, not a universal cultivar height prediction. A bulb grown for flowers stays herbaceous, while garlic grown underground is root. User snapshots can be edited independently.

### Function evidence and limitations

| Recorded function | Bundled records | Evidence |
|---|---|---|
| Nitrogen fixer | Bush/runner beans, garden pea, broad bean | [UMN legume physiology](https://extension.umn.edu/agriculture/crop-production/forages/legume-life-cycles-and-characteristics), [rhizobia](https://blog-fruit-vegetable-ipm.extension.umn.edu/2022/01/rhizobia-inoculation-for-organic.html), [Cornell Three Sisters](https://warren.cce.cornell.edu/gardening-landscape/warren-county-master-gardener-articles/creating-a-three-sisters-garden). Function depends on compatible symbionts and conditions; it does not mean immediate nitrogen supply to neighbours. |
| Pollinator attractor | Borage, aster, strawberry | [RHS lists](https://www.rhs.org.uk/science/research/plants-for-pollinators), [aster profile](https://www.rhs.org.uk/garden-inspiration/wildlife/top-12-plants-for-autumn-pollinators). |
| Ground cover | Strawberry, winter squash | Strawberry's runner habit and RHS profile, Cornell squash shade/cover guidance. Coverage is design use, not guaranteed weed suppression. Common thyme's low-layer niche does not imply a recorded ground-cover function. |

Other functions remain empty unless recorded by an imported provider or the owner. No role is inferred from companion prose or the crop-rotation demand class. Permapeople complete normalized tokens map Tall trees/Trees/Shrubs/Herbs/Ground cover/Roots/Vines directly; Uses mapping preserves unmapped text, including generic Utility, in the original raw response. The Apple fixture records the issue's 2026-08-17 response (Trees; Utility, Animal feed, Attracts insects, Hedgerow); it is not a claim about today's API response.

### Authoring and operating guilds

Plants → Insert guild opens the bundled/user picker. New, Duplicate and Edit open a form; bundled templates are read-only and Duplicate creates a user-owned ID. User JSON files live in `<app-data>/guilds/`; Reload reads them again and reports invalid filenames without hiding valid templates. Required keys are `id`, positive integer `version`, `name`, `centre`, `roles`, `license`, `attribution`; optional German names/descriptions and source references are supported. A centre is a canonical species key or `function:<token>`. Each role has `function`, positive `count_min`, `ring_radius_cm` (finite positive cm or `canopy_edge`), and ordered `suggested_species` canonical keys. The editor resolves choices from the complete offline catalog and shows eligibility. Replace unresolved user suggestions before insertion. At most 200 plants including centre are allowed.

Pick an instance name, centre species/eligible existing plant, centimetre coordinates and role species. Preview draws transient markers; Cancel/Escape leaves no saved plants/history. Insertion preflights the full layout and commits one command. Centre deletion dissolves links on surviving plants and undo restores them. Right-click plant actions add/remove/transfer membership in one step. A complete copy gets an independent guild; a partial copy loses membership. Editing/reloading templates does not change existing saved snapshots.

The walnut template uses Penn State's [reported tolerance list](https://extension.psu.edu/landscaping-and-gardening-around-walnuts-and-other-juglone-producing-plants), largely observational, including asters under their historical genus. It is not a controlled-trial guarantee for every Symphyotrichum cultivar. The Three Sisters template recognises Indigenous planting traditions and Cornell's cultivar/timing guidance; sturdy corn and staggered planting matter, and the bundled sweet-corn record is an editable planning snapshot rather than a promise of adequate support for every runner bean.

### Runtime and testing discipline

Guild links are orthogonal to §8.14 plant-parent relationships; no new bed predicate or parentage path exists. The canonical build-only plant constructor is shared by gallery, Plant Lists and guild insertion, and creation commands retain `_auto_parent_plant`. A 100 ms parented timer coordinates snapshots/badges/panels. Cosmetic updates are idempotent, and navigation resolves UUIDs after the clicked row callback. API diagnostics may lag one debounce tick; reads do not force recomputation. Tests must compare refusal scene/history state, undo depth, copied metadata independence, editor failure preservation, unchanged-panel signatures and rotated centre geometry in addition to ordinary success.

## 8.27 Cached sun exposure and shared diagnostics

US-F3 (#314) and #428 follow ADR-056. `core/shade_aggregation.compute_sun_exposure` shares the explicit day's sample loop with the existing grid aggregator. `collect_identified_casters` is the single footprint / height / base collector (one `ItemLookup` per walk; `collect_shadow_casters` flattens it for the overlay). Sparse coverage uses unioned owner footprints — each swept from where its owner stands — and excludes the receiver's own UUID, every soil solid whose outline contains the receiver (a bed, raised bed, container or wall planter with a height: `IdentifiedCaster.holds_plants`, so a plant inside a bed it was never linked to reads the bed's real sun, #481) and, for a plant that stands in a soil parent with a height, that parent (`SunReceiver.stands_on`, from `footprints.standing_parent`: without it every plant in a raised bed read 0 hours, ADR-056 addendum). Receiver coordinates use base-shape centres transformed by `mapToScene`; badge/decorative bounds are never sampling geometry. Row zero remains south.

`SunExposureCoordinator` compares immutable runtime snapshots in 60 ms and publishes cached evaluations. Commands are subscribed separately because metadata-only changes need not repaint. Requirement-only edits reclassify without recomputing. No panel, selection, repaint or Agent API read can start work. Ordinary edits retain the grid's visual snapshot with a stale tooltip, but clear receiver minutes, badges and mismatches. Missing location, cancellation, absent results, hidden plants and out-of-grid centres remain unavailable rather than becoming zero hours. Known unavailable requirements produce `sun_evaluation` information diagnostics; Information is a panel severity filter and counts say diagnostics.

`DiagnosticsCoordinator` is the sole general-panel publisher. Producers cache records and emit `CanvasScene.diagnostics_changed`; `ProjectManager.diagnostics_snapshot` harvests all producers for both UI and MCP conversion. Rows store UUIDs and resolve them at click time; document replacement cancels pending navigation. Sun records use enclosing-group navigation UUIDs and retain the physical receiver in details. Theme-aware runtime child badges stay inside plant footprints, with unchanged transform origins, snapping and serialization. Translated labels and one-decimal localized hours are presentation only.

Tests distinguish the displayed ground heatmap from estimated receiver sun. The Berlin constants are measured outside the new sparse implementation, not computed expectations. Deterministic controlled workers emit even after cancellation to prove late-result rejection. Cancellation is checked inside caster loops; an owner keeps its worker until queued `finished` and refuses a second launch while cleanup is pending. The full suite retains the existing heatmap budget and adds a 200-receiver budget plus a live GUI timer assertion.

**Receiver elevation and sliced obstacles (#641).** A plant elevated on raised soil (in a raised bed, container or wall planter with a height, via `ui/canvas/footprints.item_base_cm`) carries `SunReceiver.elevation_cm > 0`. Sparse evaluation groups receivers by elevation. Receivers at ground level ($e \le 0$) continue to sample against ground-level shadows ($z = 0$). For elevated receivers ($e > 0$), obstacles whose top height ($z_{\text{top}} = base + height$) is at or below $e$ cast zero shadow on the receiver plane and are skipped. Taller obstacles are sliced relative to $e$: effective base $b' = \max(0, base - e)$ and effective height $h' = z_{\text{top}} - \max(base, e)$, projecting their shadow onto the receiver's elevated plane with bed sparing preserved. Elevated plants thus clear low fences, walls and edges without receiving false shade warnings.

## A1 security ingestion contracts (#453; sections 8.8, 8.11 and 8.15)

Linux settings protection remains in the one QSettings factory: owner-only 0600,
regular file/current owner, non-truncating migration, unchanged registry behavior,
and fail-closed startup. Atomic Qt synchronization stays enabled. See ADR-041.

The updater validates exact release identity/origins, each redirect, the matching
64 KiB-bounded checksum manifest, actual asset size and SHA-256. It passes a verified
result to launch and rechecks the file. User failures are translated categories;
signed URLs, API credentials and raw network diagnostics are not displayed. See ADR-044.

Thumbnail transfers allow at most 16 MiB and 16777216 decoded pixels; cached thumbnails
are genuine PNGs with at most 2048 pixels per edge. Static Maps transfers allow at most
8 MiB and the existing 1280×1280 tile dimensions. Content-Type is insufficient: header
dimensions, structure and full first-frame decoding are checked before use. Responses
close on all paths, HTTP error excerpts are limited to 200 bytes, and Google keys stay
redacted. Existing invalid caches are rejected; valid legacy images normalize on use.
The map's calibration, crop/mosaic math and existing cancellation outcomes are unchanged.

## 8.28 Bounded 2D canvas paint for crafted plans (#472, ADR-057)

`PolygonItem.paint` sizes its work by a vertex bound, not by whatever a plan file happens to hold. `MAX_FULL_DETAIL_VERTICES = 256` is the full-detail budget: at or below it an unselected polygon paints exactly as it always did. Above it, an **interactive** paint draws the exact outline with a **cosmetic 1-px pen and `Qt.BrushStyle.NoBrush`** — and returns, skipping the shadow, grid and status overlays for that frame. "Interactive" is the item's **cache mode**, not Qt's `widget`: every cached paint receives `widget = 0`, and unselected canvas items are cached, so a `widget`-based guess never fires on the canvas (that was the first version's bug — it never degraded anything; see ADR-057). Every export, report, print and agent render path disables caches first, so those stay exact; a **selected** item is excluded and paints the exact fill, so editing sees the truth. The cosmetic pen is load-bearing: Qt strokes a wide solid pen by building a fill, so reusing the item's own pen would leave the degraded frame quadratic (measured 319 ms at 1,024 vertices against 4 ms cosmetic). A **boolean union** result is subject to the same bound: it is selected when the command creates it (so the owner sees a filled result), and a result above 256 vertices draws the outline once deselected - FR-EDIT-19 says so, and the manual checklist re-checks the fill after clicking away.

The load seam is the second half. `ProjectManager._deserialize_item_core` refuses a polygon above `MAX_POLYGON_VERTICES = 16_384` and skips it with a logged warning (counted for the app's existing skipped-item notice), so a hostile `.ogp` cannot stall the loader or exhaust memory; the rest of the plan loads normally. At this ceiling the degraded outline is ~69 ms, and no legible garden outline comes near it. Both constants live in `ui/canvas/items/polygon_item.py` and are the only place to retune the bound. The measured cost table, the pen-width finding and the rejected alternatives (convex-hull / bounding-box fill, a hairline-but-wide pen, reflex counting, a low load ceiling) are in ADR-057; the regression is pinned by `tests/integration/test_polygon_paint_bound.py`.

An "item made from an item" copies a shape's **look** through one seam that the **offset tool and mirror** share, `core/item_look.py::copy_visual_style`. It copies both the serialized attributes (`fill_pattern`, `fill_color`, `stroke_color`, `stroke_width`, `stroke_style`) and the live `QPen`/`QBrush`, because a copy that writes only one of the two looks right until the next save (#470). Chamfer, fillet and trim are the same shape of bug (#441); the L1 branch routes chamfer and fillet copies and `PolylineItem.clone_with_points` through the same helper, and gives a trim result its pen through `adopt_pen`, the module's pen writer (§8.29.5).

## 8.29 3D scene pipeline (Phase 17 L1, #385, ADR-059)

How the plan reaches a 3D engine. Each L1 story adds its own `### 8.29.N` subsection at the end;
this section is the map. The decisions and their rejected alternatives are ADR-059; the engine
facts are the `ogp-3d-renderer` skill; the look is `ogp-lush-cinematic`.

### 8.29.1 Scene contract v2 — records, diff, builders, sink (L1.1)

**The pipeline.** Five steps, all Qt-free except the first:

```
live canvas items ──snapshot_records()──▶ {item_id: Record}        ui/view3d/snapshot.py (GUI thread)
                                               │ diff() against the last snapshot       core/scene3d/scene_diff.py
                                               ▼
                          SceneSync.apply ──▶ builders, for added + geometry only       build.py, sync.py
                                               │ MeshPart (item-local frame)             mesh.py, polygon.py
                                               ▼
                                           EngineSink                                    sink.py
                               Qt Quick 3D (L1.2) · RecordingSink (tests)
```

Nothing under `core/scene3d/` imports Qt: an AST scan in `tests/unit/test_scene3d_contract.py`
covers every module of the package, sub-packages included, and follows each `core` module the
package reaches (today `shadow_geometry` and `solar`), so a later story cannot add a sibling that
drags Qt in. The engine is imported by one package only, `ui/view3d/quick3d/` (L1.2).

What that scan does **not** say: that importing the package leaves Qt unloaded. It checks the
source (the AST), not the interpreter — `import open_garden_planner.core.scene3d` runs
`core/__init__.py`, which imports PyQt6 for other `core` modules (commands, the project manager).
"Qt-free" here means *no module of the pipeline uses Qt*, which is what keeps it testable without
a GPU and portable to another engine; a process that must not load Qt at all would first have to
untangle `core/__init__.py`.

**Three frames, each conversion defined once** (`core/scene3d/frame.py`):

| Frame | Axes | Who lives there |
|---|---|---|
| Item-local | cm about the item's anchor; +z up from the item's own ground | records, meshes |
| Scene | x = East, y = North, z = up (ADR-002 + height) | the plan, `item_footprints`, solar vectors |
| Engine | x = East, y = up, z = −North | Qt Quick 3D |

- Local → scene is the record's transform: `scene_xy = (east_cm, north_cm) + R(rotation_deg)·local_xy`,
  `scene_z = base_cm + local_z`; `R` turns counter-clockwise seen from above with north up — the
  sense of Qt's `setRotation` on the Y-up canvas (`pose_point`, `pose_ring`, `pose_points`).
- Scene → engine is `SCENE_TO_ENGINE` (`scene_to_engine_points` / `_vectors` and their inverses):
  determinant +1, so winding survives and nothing is mirrored. Apply it **once**, in the engine
  adapter — a second application mirrors the garden (§8.20's rule, in 3D).
- `engine_pose(transform)` says how a transform reads in the engine frame: position
  `(east_cm, base_cm, −north_cm)` and a turn of `+rotation_deg` about the engine's +Y. A test proves
  it equals posing in the scene and mapping the result; the adapter does not re-derive it.

**The record** (`core/scene3d/record.py`) — one plan item as plain immutable data:

| Field | Meaning | Signature |
|---|---|---|
| `kind` | ObjectType name; picks the builder | geometry |
| `shape` | `circle` / `ellipse` / `rectangle` / `polygon` / `polyline` | geometry |
| `footprints` | the OUTER ring(s) of the ground the item covers, item-local cm: simple polygons, counter-clockwise. How many there are says nothing about how the item was drawn (a self-crossing polygon can resolve into one ring) — `params["outline_resolved"]` does | geometry |
| `holes` | `holes[i]` = the clockwise rings cut out of `footprints[i]`; `()` when there are none. A stroke that closes has them, and so can a polygon drawn crossing itself | geometry |
| `path`, `path_width_cm` | a polyline's centre line and stroke width (fences and walls are built from these) | geometry |
| `height_cm` | `effective_height_cm(..., at_date)`; `None` = no 2D caster (a 3D build at a nominal or estimated height still casts, L4) | geometry |
| `params` | sorted immutable mapping — see below | geometry |
| `transform` | `Transform(east_cm, north_cm, rotation_deg, base_cm)` | transform |
| `material` | `Material(key, fill_rgba, stroke_rgba, pattern)` — the item's own sRGB data | material |
| `item_id`, `name`, `parent_id` | identity, display name, the plant's bed | none |

`params` keys written by the snapshot: `seed` (the item id — the one seed source), `radius_cm`
(circles: the footprint radius, a plant's canopy at the sim date), `ridge` (a HOUSE's two ridge
ends in the HOUSE's local frame, from the live ridge item), `species_key` (ADR-016) and
`species_name` (labels), `sprite_species` (a plant item's own species string, raw — what its
2D sprite is resolved from, and so its 3D recipe: §8.22.4), `plant_category`, `path_style` (a
polyline's `PathFenceStyle`, when set),
`container_material`. Selection and hover are not in the record at all. `transform.base_cm` is
where the item stands: the soil of the bed or container it is linked to and stands inside, 0.0 on the ground (§8.29.6).

**Outer rings and holes — read `regions`, not `footprints` alone.** The ground an item covers is
its outer rings *minus* their holes: `record.regions` yields `(outer, holes)` pairs and
`record.plan_area_cm2` the area. A fence that closes on itself is one outer ring with one hole, a
figure of eight or a ladder drawn as one stroke has several — and a polygon drawn crossing itself
can enclose a pocket, so holes are not a stroke's alone. `Record` enforces both orientations, so a
ring cannot be put on the wrong side by
accident. Whoever turns `footprints` into something with area — a builder, the ground bake, a
picker — iterates `regions`; extruding the outer ring alone turns a 3.6 m² fence into a slab over
the 80 m² it encloses (that was the first version's defect, and `verify_builder` now refuses it).

*When a stroke that almost closes does close.* A stroke has butt ends: it reaches half its width
to either side of the centre line and not at all past its end points. Two ends that stop short of
each other **at a corner** close the loop while the gap is at most half the stroke's width (a
10 cm stroke: up to 5 cm; at 6 cm it stays open, one ring, no hole); a gap in the middle of a
straight run never closes. `scene3d_edge_cases.ogp` holds one fence of each kind.

**Every region can be built — the one predicate.** `polygon.is_buildable_region(outer, holes)` is
true exactly when `polygon.cut_region` — the triangulation `prism_mesh` itself uses — cuts the
region and proves the cut (every triangle counter-clockwise, the areas summing to the region's).
The snapshot hands on only regions for which it holds, so for every record
`all(is_buildable_region(o, h) for o, h in record.regions)` is a fact, and
`prism_mesh(record.footprints, h, record.holes)` never raises. What it implies for a builder of
its own: each outer ring is a simple counter-clockwise polygon, each hole a simple clockwise one
inside it, holes do not overlap, and a triangulation exists — `cut_region(outer, holes)` returns
it (`(vertices, triangles)`, remembered). Rings may *touch* in a point; a region whose rings
touch so that it cannot be cut never arrives. Every region of every record is judged — a
circle's, an ellipse's and a rectangle's ring too (on the record grid a circle of radius 2e-7 cm
is no polygon) — but a ring that is convex BY CONSTRUCTION is judged without being cut: a
circle of 1e-3 cm and more by its radius, an ellipse or a rectangle by arithmetic on its corners
(`polygon.is_convex_ring`: every corner turns left, and the ring is no sliver for its reach),
and only a ring that is not convex on the record grid is asked the cut. The arithmetic implies
the predicate (0 exceptions among 78,874 such rings in a sweep of 120,000 shapes; 2,000 in the
suite), so the promise above holds for them unasked. It is there for the date scrub: every dated
plant has a new radius on every tick, and cutting each 24-gon made that snapshot 2.9 times
slower (`bench_large`, 80 plants changing: 11.6 ms at the base, 33 ms cut, 12.7 ms now).
**Regions can nest:** an island standing in a hole is a region of its own, inside another
region's hole; a builder that fills "the hole" fills the island.

**What an outline may cost — one budget, paid before the work.** An item's outline comes out of
a plan file, anybody can write one, and the snapshot runs on the GUI thread on every edit tick.
Two rules hold for everything between the item and its record (§8.11 has them as patterns):

1. *The input is bounded before the work.* An item's STORED vertex count is asked before one
   vertex is read: more than `polygon.MAX_ITEM_VERTICES` = 16,384 is one comparison (a polyline
   of 200,000 points, a polygon of 100,000 vertices). The same cap holds for what the clipper
   returns for an item, all rings together, counted before one ring is read.
2. *The bound is on the sum.* ONE `polygon.WorkBudget` of `MAX_REGION_WORK` = 150,000,000 work
   units pays for everything one item's outline needs, **each step before it runs**. A unit is a
   count, priced at about a nanosecond on the development box, so the verdict is the same on
   every machine. What is paid for, in the order a stroke pays it:

   | Step | What it is priced from |
   | ---- | ---------------------- |
   | counting the pairs of the path's segments (`polygon.touching_pairs`) | the points, squared; then every pair whose boxes meet — all of them before one is tested |
   | the clipper inflating the path | the points; their **stack** (`polygon.stack_height`: a sweep line carries every edge it crosses — 4,000 teeth standing side by side took the clipper 1.6 s without one crossing, lying down 4 ms — except an exactly LEVEL one, which it walks along: a straight fence costs the same east–west as north–south); the pairs that cross (800 points scribbled across a plan: 73,000, half a second, 53,000 rings) or lie within the stroke's reach of each other |
   | reading what came back | every ring and every vertex, counted first |
   | sorting rings into regions (`group_rings`) | holes × outer rings, each question the outer ring's vertices (2,000 × 2,000 small rings took 3.8 s when nothing asked) |
   | each region's cut (`polygon.pay_for_region`) | the simplicity test (the edges squared, and the pairs it has to look at), a bridge per hole, the ears — cut out of what the ITEM has left, not out of a bound per region: a thousand regions that each fit do not fit together |
   | resolving an outline that crosses or touches itself | each union and each band from the vertices, their stack and the **crossings** (the last reading of 800 scribbled vertices took ten seconds; a bound on the vertex count did not see it); each reading's rings before they are read; sorting the strict union's rings (`group_rings`, as above); each comparison with the drawn outline on its lattice. Both unions are asked for flat lists; only a band's difference is read off a tree (below) |

   What the budget does not cover is refused — `polygon.RegionTooLargeError` inside, the
   skip code `outline_too_large` outside — and the refusal is remembered like any other answer
   for as long as the item is there. The counted work of one item is at most the bound, to the
   unit; a refusal costs at most the bound and usually far less.

   *No union is asked for a tree.* Both unions — the plain one and the one with
   `StrictlySimple` — are asked for a flat list (`Execute`; `snapshot._union_rings`), and
   `group_rings` says which hole is whose. As a tree (`Execute2`) a union costs by the rings it
   makes and JOINS, which no price can be read off beforehand, and twice that was seconds
   INSIDE the budget. The strict union of one outline of 340 vertices, every vertex on one of
   two levels: 3.6 s (pyclipper alone 4,382 ms as a tree, 19 ms as a list; refused in 31 ms
   now). And, one call away — for a tree that was flattened on the next line — the plain union
   of ONE ring with 720 holes bridged to its wall, 4,324 vertices: 5.3 s (pyclipper alone, 801
   rings: 7,078 ms as a tree, 23 ms as a list; the whole item is refused in 0.25 to 0.31 s
   now, the same answer for the same units).

   The one tree left is a band reading's DIFFERENCE (`snapshot._band_tree`), which reads its
   hierarchy. Its price does not count its rings and need not: a band cuts every ring a hair
   free of every other, so nothing is left to join, and the same call costs the same as a list
   and as a tree — pyclipper alone: 801 rings in and out 1.8 / 3.0 ms; 1,600 rings out 123 /
   144 ms; 800 diamonds touching tip to tip 28 / 28 ms; 800 bridges walked back 1 to 8 grid
   units beside the way out, 19 to 33 ms either way.

**In time the bound is a measurement.** A unit of the reference — a plain traced outline — took
0.35 to 1.15 ns on the development box when it was quiet and 0.7 to 2.3 ns beside other test
runs: 0.05 to 0.35 s for the bound. `scripts/measure_region_work.py` prints, for every row of
its tables, what a unit CHARGED took in units of the reference — cost to price. Measured on
2026-10-12 beside other test runs, 61 rows: the strokes and outlines built to hurt the
clipper's sweep stayed at 0.7 or below; a ring with hundreds of bridged holes, refused, at 1.4
to 1.5; the outlines that are accepted between 1.0 and 2.0 (the dearest: a ring with bridged
holes, sheared, and an outline that crosses itself); in the table of single cuts, a region
that hides its bridges at 2.1. **One family stood far above that: a ring whose holes TOUCH its
outer ring, 3.6 to 8.1** — the bridge search of the cut (`polygon._bridge_position`) charged a
block of candidates 60 units per edge, while a hole that touches the wall hides its nearest
boundary vertices and takes block after block: 89 such holes were built in 0.65 to 0.8 s, and
110 — 444 vertices — were refused after 0.6 to 1.5 s.

**Re-priced for issue #451 (2026-10-30): a block of bridge candidates costs 600 units per
edge.** The touching-holes family now stands at 0.8 to 1.5 — the dearest row of the whole
table is 1.3 to 1.5 across runs — and 110 such holes are refused in about 0.07 s (200 in
0.01 s, from their size
alone, before one bridge is searched). What it costs in capacity: a slab with 49 such holes
now fits (89 before), a row of 88 square holes (105) and a slab of 117 triangular ones (146).
The higher block price also raises the **pre-cut floor** for an outlined region with many
holes, and that is a stated loss: a crafted 25 × 25 line grid (625 crossings, resolving into
regions with hundreds of holes) is now refused from its size where it used to resolve; a
22 × 22 grid still resolves (286 regions, 25.6 M units). Real plans are far from this — a
closed fence's one hole costs about 1 M units.
So "one item costs at most the bound" holds in units and in seconds: 0.05 to 0.35 s, measured
up to 0.39 beside other test runs, up to 0.7 where a busy machine meets the dearest ordinary
family.

**The table fails above a ratio of 12** (`MAX_COST_TO_PRICE`; exit code 1, the rows named). A
price list fitted to families is only as good as the families: both times a step ran for
seconds inside the budget, it was a way of ASKING the clipper that no row measured — a union
as a tree, at 14 to 76 times its price — and both times the script could only have printed
it. A ratio is two timings, so the gate is run alone on a quiet machine (§8.10).

Measured (`scripts/measure_region_work.py`, development box, 2026-10-11 and, for the rings with
holes, 2026-10-12; the units are exact):

| What fits, at most | | What it costs |
| ---- | ---- | ---- |
| ONE region: a plain traced outline | 3,557 vertices | 147.8 M units |
| … a comb (the ear clipper's worst case) | 1,648 vertices | 149.9 M |
| … a spiral | 4,334 vertices | 149.9 M |
| a whole outline: a closed fence along a traced outline, 10 cm | 1,321 points | 144.5 M |
| … the same fence, every segment nearly level with every other | 933 points | 148.9 M |
| … a straight fence with a post every 2 m, east–west / north–south | 6,666 / 6,645 points | 150.0 M (the pairs of its posts) |
| … the same at 30° (its outline keeps a vertex per post on the grid) | 4,514 points | 150.0 M |
| … a path 100 cm wide with a point every 25 cm | 900 points, 225 m (the review's generator: 1,011) | 149.9 M |
| … a path 60 cm wide with a point every 50 cm | 962 points, 481 m (the review's: 1,201) | 149.8 M |
| … a ladder drawn as one stroke | 168 rungs | 145.1 M |
| … a square mesh drawn as one stroke | 15 × 15 openings | 146.3 M |
| … a wall 30 cm wide traced with a point every 2 cm | 919 points | 149.9 M |
| … a regular polygon (what a DXF import makes of a circle) | 3,456 vertices | 150.0 M |
| … a traced pond | 3,538 vertices (the review's freehand pond: 3,497) | 148.4 M |
| … a drawn outline that crosses itself | 1,513 vertices | 149.5 M |
| … a two-level zigzag (every tooth crosses the others) | 80 vertices | 146.0 M |
| … ONE ring with holes bridged to its wall (a polygon with holes, exported as one ring): a slab with triangular holes, level or sheared | 117 holes, 706 vertices (146 before #451 re-priced the bridge search) | 149.8 M / 149.9 M |
| … a row of square holes, each bridged to the edge | 88 holes, 708 vertices (105 before #451) | 147.6 M |
| … a row of frames — diamonds touching corner to corner, a bridged hole in each | 112 frames, 1,120 vertices (118 before fix round 4) | 149.2 M |
| … a slab whose holes TOUCH its wall (read off a band: the holes open into notches) | 49 holes, 200 vertices (89 before #451) | 144.6 M — about 0.11 s: 0.8 times its price |
| **what a large plan needs:** a closed fence along 400 traced points | | 24.3 M — 16 % of the bound |
| … a line of 2 km (2 points) | | 31,200 units — 0.02 % |
| … a straight line of 2 km with a post every 5 m | 401 points | 1.5 M — 1 % |
| … the same line with every post 2 cm off it | 401 points | 45.6 M — 30 % (its segments stack) |
| … a traced outline of 400 vertices | | 6.2 M — 4 % |
| … a rectangle drawn as a polygon | | 10,200 units |

**What is refused that somebody could want.** These limits are low enough to meet: a garden
path of more than about 900 points, a closed boundary fence traced with more than 1,321, a DXF
circle of more than 3,456 segments, a traced pond of more than about 3,500 vertices (the fence
was built up to about 2,600 points before the bound existed — in 1.9 s per edit). Such an item
is ABSENT from the 3D view — no solid, no decal — while the 2D canvas draws it as always, and
the direction a wobbly line runs in changes how many points fit (933 nearly level, 1,321 round
a loop): the clipper's sweep is not symmetric, and its price follows it. So the user-visible
message for `outline_too_large` is an **acceptance criterion of the workspace story (L1.3)**,
not a hope: an item that silently is not there reads as a bug of the 3D view.

Outlines that built are refused since fix round 4 — few, and stated: it pays for sorting the
strict union's rings out of the item's budget (holes × outer rings), where a tree's hierarchy
had come unpriced. ONE ring with many bridged holes lost one to five per cent of what fits:
a row of square holes 106 → 105, a row of frames 118 → 112, a slab with triangular holes
148 → 146, holes that touch their wall 90 → 89. No other family of the table moved. **The
re-price of #451 moved the bridge families on purpose:** a slab with triangular holes 146 →
117, a row of square holes 105 → 88, holes that touch their wall 89 → 49; the frames and every
family that does not bridge stayed where they were.

| What is refused | What saying no took | What the clipper alone would have taken |
| ---- | ---- | ---- |
| a stroke scribbled over 800 / 1,600 points | 15 ms / 12 ms | 0.34 s / 1.7 s |
| a stroke of 2,000 / 4,000 teeth standing side by side | 14 ms / 51 ms | 0.26 s / 1.1 s |
| a stroke scribbled over 400 points | 65 ms — its inflation is inside the budget (the clipper is asked, once), what comes back is not | 0.07 s |
| an outline scribbled over 400 / 800 / 1,600 vertices | 30 ms / 32 ms / 12 ms | 0.74 s for the last reading of 400 |
| a two-level zigzag of 200 / 340 / 800 vertices | 43 ms / 27 ms / 34 ms | (as a tree: 1.1 s / 3.6 s) |
| ONE ring with 580 / 720 bridged holes (3,484 / 4,324 vertices) | 0.19 s / 0.25 s — the bridges of a region with 720 holes are beyond the budget | its plain union as a tree: 3.2 s / 7.1 s |
| … the 720, sheared | 0.27 s | 6.7 s |
| a slab with 50 / 110 / 200 holes that touch its wall | 0.10 s / 0.07 s / 0.01 s (refused from the size of the 200 before one bridge) — the price stops the search (#451) | — |
| a plain outline of 10,000 vertices | 2 ms (two linear passes; its size is known from its length) | — |
| an item of more than 16,384 vertices | one comparison; not one vertex is read | — |

Not bounded, and stated — four things:

- A **plan** is the sum of its items: there is no budget across a plan (it would make a record
  depend on what else is on the plan). The FIRST snapshot of a plan costs what its items cost,
  and so does every item again when it is edited: two hundred accepted outlines at the bound
  are 30,000 M units — the review measured 33 to 40 s for such a plan — on the first tick, and
  one bound on a tick that edits one of them.
- An **idle tick is linear in the plan's vertices** even when everything is remembered: every
  ring is read off its item, moved into its frame and looked up (0.25 s at 120,000 polygon
  vertices, the same before this pipeline's bounds existed). Asking only the items that changed
  is a later optimisation; nothing here prevents it.
- **What a LIVE plan holds in memory has no cap** — it is linear in the plan (next paragraph):
  at most about 1.8 MB for one item, 156 MB measured for 400 accepted polygons of 3,000
  vertices. `clear_outline_cache()` gives all of it back.
- The 2D shadow overlay inflates a polyline with no bound at all, as it always has (so did
  the retired Qt 3D view's collector until L1.10 removed it).

**What is remembered: everything the plan asks for, and a bounded rest.** `polygon.ring_keyed`
is the one memory for functions of rings (`ring_area`, the verdict-and-cut of a region, a
record's ring facts, the regions of a polygon and of a stroke). A snapshot is one *generation*
(`polygon.snapshot_generation`; `snapshot_records` runs in it): an answer asked for by the
snapshot being taken or the one before is LIVE and is never dropped, so **an unchanged plan is
answered from memory on every tick, whatever its size** — zero cuts, zero inflations. What is
bounded is the STALE answers — the ring an outline had before its last edit, a builder's own
rings, anything asked outside a snapshot: at most `HELD_VERTICES` = 262,144 vertices of them per
memory, keys and answers together, the least recently asked dropped first, settled at the end
of every snapshot. A ring of more than `MAX_ITEM_VERTICES` is never hashed and never a key.

Two forms came before this one, and both were wrong in a way a green suite did not show. An
`lru_cache` bounds the number of answers — 2,048 answers about an outline of 4,000 vertices
that is being dragged were a gigabyte. A cap on the vertices held, dropping the least recently
asked (fix round 3), bounded the memory and **recomputed the plan on every tick** once the plan
was larger than the cap: a snapshot asks in the same order every time, so each answer was the
oldest when its turn came — 160 polygons of 1,000 vertices re-cut all 160 regions per idle tick
(4.6 to 5.3 s where 0.2 s had been), 110 closed fences took 14 s. *A cache must hold its
working set; bound what is beyond it.*

*What a live plan holds.* No cap: linear in the plan. An accepted outline's rings are its
record's own, and its key is the outline as drawn — the same ring when that turns
counter-clockwise, one more copy when it does not; a REFUSED item has no record, and its key
is all that is kept. Measured (review of fix round 4): 130 bytes a vertex for an accepted
polygon once its record is gone — 400 polygons of 3,000 vertices hold 155.9 MB, and
`_polygon_regions` then counts 2,403,200 vertices, 9.2 times `HELD_VERTICES`; 112 bytes a
point for a refused line — 20 lines of 16,384 points hold 36.8 MB. Per item at most about
1.8 MB (the largest key there can be); an accepted outline of 3,500 vertices about 0.45 MB.
The form before this one capped each memory at 27 MB, and recomputed the plan for it.

*One snapshotting scene per process, and one call that forgets.* The generation is the
PROCESS's clock; nothing says whose snapshot it is. **One snapshotting scene per process is
the supported case.** More are correct and recompute: two scenes snapshotted in turn still
find their answers (the one before counts); three in turn find them stale — measured by the
review of fix round 4, every scene's 160 polygons cut again on every tick. A snapshot that
raises half-way leaves the next ones correct. And because what a snapshot asked for is dropped only by LATER snapshots, a plan
that is gone stays held until two more have run — after `scene.clear()` with the 3D view
closed, forever (measured: 321,280 vertices, about 30 MB). So there is one public call in
`snapshot_records`' module: **`ui.view3d.snapshot.clear_outline_cache()`** drops everything the
outline memories hold, live and stale — every `ring_keyed` memory and the circles' — and the
next snapshot is a first one. The workspace calls it when the document changes (a plan is
opened, a new one made) and when the 3D view closes; it is also how a second scene is
snapshotted in one process without the first one's answers in the way. One consequence
worth knowing: the CUT of a region is asked for when it is made and when the solid is built,
not on idle ticks, so in a plan above the cap it goes stale and may be dropped — a full rebuild
(a new sync, `reset()`) then cuts those regions again, once. `cut_region`,
`is_buildable_region` and `is_region_too_large` share one memory (a refusal is remembered with
its words); `is_simple_ring` is not remembered.

**A resolved outline says so.** A polygon that crosses or touches itself does not arrive as it
was drawn: the snapshot resolves it by the non-zero rule — the rule the 2D shadow fills a
caster's own footprint with (a bow-tie's two lobes, 60,000 cm² both ways) — into buildable
regions. Such a record carries `params["outline_resolved"] = True` (`PARAM_OUTLINE_RESOLVED`; the
key is absent otherwise), and **if it is a HOUSE it carries no `ridge`**: the ridge item was
drawn for the outline as drawn. Do not guess from the ring count — one resolved outline is a
single ring of ten vertices, another three rings, another an outer ring with a hole. The
**The regions of a record stand in a stated order**: by the smallest vertex of their outer ring
(x, then y; `snapshot._in_order`) — not in the order the clipper happened to hand its rings
out, which changed with a clipper mode (seven outlines of 13,740 when the plain union went from
a tree to a list). Every answer of the clipper is put in that order BEFORE it is judged,
because regions are paid for and cut one after the other out of one budget. A region's HOLES
stay as the reading gave them: the cut joins holes from the right, and holes that reach equally
far right in the order they come, so that order is part of the cut that was proven. The
recipe for a builder that needs ONE plain outline (a gable roof, a bed's frame): build your shape
only when the record has one footprint, no holes, and no `outline_resolved`; otherwise build
`record.regions` as a block — `prism_mesh(record.footprints, height, record.holes)` — never
`footprints[:1]`. The resolved vertices sit on pyclipper's 1/1000 cm grid, and parts that met in
a single point stand 0.002 cm apart where the region could not be cut otherwise. A vertex placed
twice in a row (a double click, a closing vertex equal to the first) is dropped and resolves
nothing. The canvas *paints* a self-crossing polygon with Qt's odd-even rule, which agrees with
the non-zero rule for a bow-tie and not for a pentagram (its centre: filled by the shadow and so
by the solid, left open by the paint).

**What the snapshot leaves out.** By design, silently: invisible items, items without an object
type, items that cover no ground (text, groups, a one-point polyline), and `ROOF_RIDGE` items —
a ridge is its HOUSE's `ridge` param, and the Qt 3D view's decal for the ridge line is not carried
over. Because something is wrong, and **reported**: an item whose record cannot be built
(malformed metadata, non-finite geometry — any exception is contained to that item), a second
item carrying an id already taken (the lower one wins), an outline that cannot be made into
buildable regions, one that is too large (above), and one with a length beyond `MAX_LENGTH_CM`
or a height below `MIN_HEIGHT_CM`. The return type is the plain
`dict[str, Record]` it always was; the report is an optional keyword-only out-parameter:
`snapshot_records(scene, at_date, skipped=my_list)` appends one
`SkippedItem(item_id, kind, reason, error_type, error_message)` per such item (the list is the
caller's and is not cleared). A `SkippedItem` is plain data and safe to keep: `reason` is a
`SkipReason` code — `record_failed`, `duplicate_id`, `outline_unbuildable`, `outline_too_large`
(nothing is wrong with its shape; the 2D plan shows it as it is), `out_of_range` (a
length beyond 10 km, a height of 1e300 or of 1e-46) — which the UI maps to
a translated text (never show the value); `error_type` and `error_message` are the exception's
class name and message as strings, empty when nothing was raised. It does not hold the exception
(its traceback would keep the scene and the item alive), and two reports of one failure are
equal. Each is also logged once per item and kind of failure (the exception's type), not once
per edit — `record_failed` as an error with the traceback, the other codes as a warning with
the message; after 2,048 different failures one line says that further ones are
not logged, and none are. The wiring (L1.3) must pass a list and show it (for
`outline_too_large` that is an acceptance criterion, see above) — and
`SceneSync.failures` — where a user can find them.

Where the local frame hangs: the circle's centre; `rect().center()` of an ellipse or rectangle;
the centre of the vertex bounding box of a polygon or polyline (`ui/canvas/footprints.item_outline`).
Two consequences worth knowing before reading a diff: a resize that keeps a corner fixed moves the
centre, so it is geometry *and* transform; and a **measured** plant's footprint is its canopy, not
the circle the user drew, so resizing that circle changes nothing.

**The range of a length.** No length of a record exceeds `MAX_LENGTH_CM` = 1e6 cm (10 km): the
height, a stroke width, every coordinate of `footprints` / `holes` / `path`, the transform's
position and base, every float in `params`. `Record`, `Transform` and `Params` refuse anything
beyond it (`RecordRangeError`), an infinite value included, and the snapshot reports such an item
with the code `out_of_range` instead of making a record. A builder may therefore take every
number it reads for a finite float32 with centimetre resolution to spare — a plan edited by hand
can hold a height of 1e300, and no builder has to know. Two things follow for builders:
`Mesh.from_arrays` raises `MeshError` for a value that is not finite once it is float32 (build an
invalid mesh for a test with `dataclasses.replace(mesh, positions=…)`, not through it; `Mesh.merge`
holds a single part to the same rule), and
`prism_mesh` raises for a height or coordinate beyond float32 before computing with it.
The range has a floor as well: a height below `MIN_HEIGHT_CM` = 1e-3 cm is refused like one
beyond the bound (1e-46 is a positive number and exactly zero in float32 — a solid without a
height), and `prism_mesh` gives no geometry for a height that is zero in float32. **Every float
in `params` is taken for a length** and held to the bound; a builder that needs a float that is
none (a ratio, an angle) names its key in `record.DIMENSIONLESS_PARAMS` — empty today — and the
refusal's message says so.

**The record grid.** Lengths are snapped to 1e-7 cm, angles to 1e-9° (`quantize_cm`,
`quantize_deg`), so the same geometry reached along two float paths is one record. This is
load-bearing, not hygiene: without it a HOUSE with a ridge was rebuilt on 689 of 1,000 moves
(ADR-059 decision 5).

**Signatures and the diff.** `geometry_sig`, `transform_sig` and `material_sig` are hashes of the
three field groups; `Record.same_geometry` / `same_transform` / `same_material` compare the
signature first and then the values, because Python hashes collide on real edits
(`hash(-1.0) == hash(-2.0)`). Use those methods — or `diff` — never `a.geometry_sig == b.geometry_sig`
on its own. A signature compares two snapshots of the *same item*; it is not a content address
across items (the seed is the item id).

`diff(old, new)` returns `SceneDiff(added, removed, transform, material, geometry, reordered)`:

| Edit | Diff |
|---|---|
| move, rotate | `transform` |
| recolour (fill; a polyline's stroke) | `material` |
| height, centred resize, vertex edit inside the bounding box, a plant growing with the date, a ridge edit (on its HOUSE) | `geometry` |
| one-sided resize, vertex edit that grows the bounding box | `geometry` + `transform` |
| a bed's height (on each plant in it), re-parenting a plant onto or off raised soil, a bed resized so that a linked plant is no longer inside it (§8.29.6) | `transform` — the base |
| select, deselect, hover, rename, re-parenting between parents without raised soil, a rotation of a circle about its centre | empty |
| create / delete, hide / show | `added` / `removed` |
| arrange (bring to front …) | `reordered` only — never geometry, no engine call |

The three lists are independent: an item appears under each aspect that changed and no other.

**The sink protocol** (`core/scene3d/sink.py`) — eleven methods: `begin`, `commit`, `add(item_id,
parts, transform, material)`, `remove`, `update_transform`, `update_material`,
`replace_geometry(item_id, parts)`, `set_sun(SunState)`, `set_ground(GroundSpec)`,
`set_selection(Selection)` (the selection ring, since L1.8 — §8.29.8) and `clear()`.
Every call but `clear` sits inside `begin`/`commit`; `add` takes an id the sink does not hold,
every other item call one it does; `parts` may be empty (an item without a solid still has a pose
and a material). A part with `tinted=True` is multiplied with `material.tint_linear()` by the
sink. **`clear()`**: after it the engine holds nothing — no items, no sun, no ground — and no
transaction is open. It is legal at any time: inside a transaction (it aborts it), outside one, on
an empty sink. An engine sink must implement it so that it also works after one of its own calls
failed half way.

**`SceneSync`** (`core/scene3d/sync.py`) owns the last applied snapshot and a sink.
`apply(records, sun=None, ground=None)` diffs, runs builders for `added` + `geometry` only — all
of them *before* the sink is touched — and sends one transaction, or nothing. A sun or ground
handed to the same `apply` travels in that transaction, so a clock tick that moves the sun and
grows the plants is one commit; `set_sun` / `set_ground` send one alone, once per change. A
builder that raises is contained (no parts for that item, listed in `failures`, logged). A builder
registered or replaced after an item was built is noticed: the next `apply` rebuilds that item.
The match is by identity, which is a contract on the registry: `builder_for(kind)` returns the
SAME object for the same kind until a `register` changes it, and every `register` moves
`BuilderRegistry.version`. `SceneSync` looks for items to rebuild only when the version moved, so
an idle `apply` asks the registry nothing (a registry without a `version` is compared on every
apply, as before).

*Failure and recovery.* A sink that raises leaves the engine in an unknown state with its
transaction open; the sync is then *poisoned* and every call raises `SyncStateError`.
`reset()` is the way back: it calls `sink.clear()` and forgets the records, the failures, the
poison flag and the sun and ground it remembered, so the next `apply` re-adds every item and
re-sends sun and ground. If `clear()` raises, the sync stays poisoned.

| Situation | What to call |
|---|---|
| a new plan, or another plan opened | nothing special — `apply(snapshot)`: it removes what is gone and adds what is new |
| a sink call raised (`SyncStateError` afterwards) | `reset()`, then `apply(snapshot, sun=…, ground=…)` |
| the engine's scene was destroyed around the same sink (view rebuilt, device lost) | `reset()`, then `apply(…)` |
| a new sink object | a new `SceneSync` |

`sync.expected_state()` returns what a protocol-abiding sink holds right now (one from-scratch
apply into an empty `RecordingSink`). Tests compare it with the sink's own state — it is the only
way to catch a sink that silently *ignores* a call, `clear()` above all. **Precondition:** nothing
was registered in the registry since the last `apply`. The reference is built with the registry
as it is when asked; between a registration and the next `apply` the sink still holds what the
old builders made, and the two differ until that `apply` has run.

**How to write a builder.** A builder is `Callable[[Record], tuple[MeshPart, ...]]` — a pure
function of the record's *geometry part*.

1. Build in the item-local frame: the anchor is the origin, z = 0 is the item's own ground, the
   top is `record.height_cm`. Never add the item's scene position; never read `record.transform`,
   `record.material`, `item_id`, `name` or `parent_id` (the seed is `record.params["seed"]`, via
   `build.item_seed`).
2. Return `Mesh.from_arrays(positions, normals, colors, uvs, indices)` wrapped in
   `MeshPart(mesh, material_kind, casts_shadow, tinted, name)`. Colours are **linear** RGBA
   (`color.srgb_to_linear`). Where a part takes the item's own colour, leave it neutral and set
   `tinted=True` — then a recolour never calls the builder. Glass, water and ground detail set
   `casts_shadow=False`; every other built part casts, whatever height it was built at (ADR-065).
3. Cover the ground the record covers: iterate `record.regions` (or pass
   `record.footprints, height, record.holes` to `prism_mesh`). A hole is not built over.
4. Register it: `registry.register("HOUSE", build_house)` on the `BuilderRegistry` instance the
   wiring hands to your package. Kinds without a builder get `default_builder` (a prism of the
   outer rings minus their holes up to the height; nothing without one; a `ValueError` — which
   `SceneSync` contains — for a ring that crosses itself, which no record from the snapshot has).
   Register the same function object once; do not hand out a new callable per lookup.

**How to test a builder** — no GPU, no Qt:

```python
from open_garden_planner.core.scene3d import (
    BuilderRegistry, RecordingSink, SceneSync, verify_builder,
)

parts = verify_builder(build_house, record)          # the contract, one call
# tuple of MeshPart · deterministic · ignores transform, material, id, name, parent ·
# every mesh validates · mesh top == record.height_cm (±1 %; height_tolerance=0.03 for plants,
# height_tolerance_cm=0.5 for an absolute gate) · seen from above, two bounds on EXCESS:
# no hole of the footprint built over (hole_cover_limit, default 0.5; None = off; a hole
# narrower than 10 cm is a sliver and is not judged) and nothing
# further than plan_margin_cm outside it (default 50; 0.0 = strictly inside; None = off).
# Neither asks for coverage: a flower, a tuft, the pickets of a fence fill a fraction of their
# footprint and pass.

registry = BuilderRegistry()
registry.register("HOUSE", build_house)
sink = RecordingSink()
sync = SceneSync(sink, registry, validate=True)
sync.apply(records)                                   # e.g. snapshot_records(bench plan)
assert sync.failures == {}
assert sink.item(house_id).parts[1].material_kind == "roof"
sink.clear_calls()
sync.apply(moved_records)                             # a move …
assert sink.ops() == [("begin", None), ("update_transform", house_id), ("commit", None)]
assert sync.build_count == len(records)               # … built nothing
```

Run `verify_builder` over every record your builder handles in all THREE committed plans —
`bench_small.ogp`, `bench_large.ogp` and `scene3d_edge_cases.ogp`, which holds the shapes the bench
plans lack: a closed fence, a nearly closed one, an open U, a turned house with its ridge, an
ellipse, a turned raised bed with plants, a pot, a concave polygon, a ladder drawn as one stroke
(four holes), a fence that stays open, and a house whose outline crosses itself (resolved: three
rings, no ridge)
(`tests/integration/test_scene3d_edge_plan.py` is the template). Assert the invariant that makes
diffs safe after each step of an edit sequence: the sink's `state()` equals
`sync.expected_state()` (`tests/integration/test_scene3d_pipeline.py::Pipeline`). And add a mutant
for each rule your builder must keep to `scripts/mutation_check_scene3d.py`.

**Ported from the spike** (`spike_q3d/meshes.py`, deleted in L1.10): `MeshData` → `Mesh`,
`uv` → `uvs`, flat `indices` → `(m, 3)` (`Mesh.from_arrays` takes either), `MeshData.concat` →
`Mesh.merge`, `translated(mesh, …)` → `mesh.translated(…)` *within the local frame*;
`normal_vs_winding`, `srgb_to_linear` and `item_seed` kept their names. The drift guards that
kept the ported helpers equal to the spike's now compare them with the spike's values frozen in
`tests/data/l0_spike_reference.json` (§8.10.13).

### 8.29.2 The engine package — `ui/view3d/quick3d/` (L1.2)

The other side of the `EngineSink` seam: Qt Quick 3D. The decision, what was ported from the
spike and every measurement are the **ADR-048 addendum "L1.2"**; the engine's traps are PF-E3D-06
and the `ogp-3d-renderer` skill. The workspace (§8.29.3, L1.3) embeds this package's host; since
L1.9 that is the product's 3D view.

**The package.** It is the only place in the product that imports `PyQt6.QtQuick3D`, `QtQuick`,
`QtQml` or `QtQuickWidgets` (it does not import the last one at all), and inside it only two
modules do. Everything that is a decision rather than a Qt call lives in an engine-free module,
which is why the GPU-less test run covers it.

| Module | Engine? | What it is |
|---|---|---|
| `core/scene3d/interleave.py` | Qt-free | `engine_buffers(mesh)`: a `Mesh` as the bytes the engine uploads — stride 48, little-endian (position @0, normal @12, linear colour @24, uv @40), uint32 indices, bounds. THE place a mesh crosses into the engine frame |
| `adapter.py` | no | `Quick3DSink` (the `EngineSink`) and `EngineScene`, the narrow boundary it drives |
| `lifecycle.py` | no | **the host's state contract** — its module docstring is the one place it is written down — the six states as a pure function of the facts (`state_of`), and the words of every refusal |
| `materials.py` | no | material kind → QML part component; the tint rule |
| `look.py` | no | `Look` — a mood as plain data — and `NEUTRAL_DAY`, the one look of L1.2 |
| `shots.py` | no | `PerspectiveShot`, `TopDownShot`; `top_down_pixel`, our own projection |
| `qt_messages.py` | no | Qt's messages recorded and classified (by level first) — for rendering on the calling thread only; the graphics adapter read from Qt's log |
| `runlog.py` | no | a line-flushed log; a watchdog that says why before it ends the process; and the second process that ends what the watchdog cannot |
| `selftest.py` | lazy | the 3D part of `--selftest`: the scene, the judge, the run |
| `geometry.py` | **yes** | `BufferGeometry`: `EngineBuffers` → `QQuick3DGeometry`, one upload per object |
| `host.py` | **yes** | `Quick3DHost`: the `QQuickView`, the facts it reads from Qt, the `EngineScene` (it owns every Model), grab, pick, camera, look, `health()` |
| `offscreen.py` | **yes** | `render_records(...)`: records in, one `QImage` out, no window — for processes that own themselves |
| `qml/Garden.qml` + 4 shaders | — | the scene; one part `Component` per material kind |

Importing the package itself is free (`__init__` is a docstring); the engine loads when `host` or
`offscreen` is imported. Measured in the running app on the dev box: the package 1 ms, the sink
with `core/scene3d` 17 ms, the engine bindings 17 ms.

**One Model per mesh part, one geometry per Model lifetime.** `Quick3DSink.add` creates one
engine `Model` per `MeshPart` (a part without triangles gets none), each with its OWN geometry
object and its own material instance. `remove` destroys them; `replace_geometry` destroys and
creates; `clear()` destroys everything. A geometry is never handed to a second Model and never
re-filled — `BufferGeometry` has no method to do it — because the spike measured what reuse
costs: a blank frame and 0 of 20 picks. There is no `Repeater3D` over a list: any change of the
list recreates every delegate. The render tier pins the consequence: an item removed and added
again, and the whole scene cleared and re-sent, come back pixel-identical and pickable.

**A move or a recolour uploads nothing.** `update_transform` sets the Models' `position` and
`eulerRotation.y`; `update_material` sets their tint. The upload counter (`BufferGeometry.uploads`,
read by the render tier around each edit) does not move. One exception since L4, and it
is throttled: a lawn's cut-outs are the other items' outlines in its frame, so a move
over a lawn (or of the lawn) changes the lawn's geometry. The controller applies a change
of the context params alone at most once per `CONTEXT_REBUILD_MIN_MS` (400 ms), the
first at once and the last in a trailing pass; the item's own move is never late
(senior review of #388: 30 lawn rebuilds in 30 drag steps before).

**Frames, once.** A mesh is mapped to the engine frame in `engine_buffers`; a record's transform
becomes a Model pose in `engine_pose` — position `(east, base, −north)`, `eulerRotation.y =
+rotation_deg`, measured on the engine to be the counter-clockwise turn seen from above (the
proof L1.1 left open); the sun and the ground are mapped in the sink; camera placements and pick
results are mapped in the host, with the same `core/scene3d/frame.py` functions. `Garden.qml`
converts nothing.

**The tint rule.** For every material kind: `albedo = vertex colour × tint`, in linear light.
The tint is the item's `Material.tint_rgba` for a part with `tinted=True` and white otherwise;
it is a property of the Model, never baked into the vertex buffer. `vc`, `roof` and `glass` take
it as `PrincipledMaterial.baseColor` (the engine linearises it); `foliage`, `grass` and `water`
take it as a linear `vec3` uniform computed in Python. Measured on one swatch per kind: 171 and
169 of 255 for the two paths.

**Light.** `set_sun` hands over the unit vector the light travels along (the negated sun vector
from `core/solar`); the host turns it into the rotation that puts the light's local −Z onto it.
A sun below `MIN_SUN_ELEVATION_DEG` — the 2D shadow overlay's own threshold — switches the sun
off; a flat fill light remains, so a night is dim rather than black (the night rig is L1.4).
L1.2 has ONE look, `NEUTRAL_DAY`: the spike's noon rig (sun `#fff1dc` × 1.9, exposure 0.85), a
plain sky colour and no image-based light probe; the fill is the mean of the noon sky's top and
horizon in linear light times the spike's probe exposure — derived, not chosen. L1.4 replaced it
with `core/scene3d/look.LookSpec` (§8.29.4); the flat fill remains only where no sky texture lights
the view.

**Two views.** The perspective view is the one people look at: filmic tone mapping, exposed by
the look. The **top-down shot** is the truth view: orthographic, north up, NOT tone-mapped — a
pixel is the surface's linear radiance — and its projection is plain arithmetic
(`shots.top_down_pixel`), which is what lets a test say where a box must be.

**The host is a state machine.** `Quick3DHost` is a `QQuickView`; `container()` wraps it for a
QWidget layout (`QWidget.createWindowContainer` — a native window: sibling widgets do not paint
over it). Never a `QQuickWidget`: with the container beside the 2D canvas the top-level window
stays a raster surface and a 2D pan step costs the same (×0.97 measured); a `QQuickWidget` in
the same place turns the window into a Direct3D surface. Create the host once, keep it, hide and
show it.

A Qt Quick window can be asked for a frame at moments when answering kills the process — not
with an exception: the grab returns a correct image and the process dies in the next passes of
the event loop — and at moments when the answer is a picture that is not the scene (PF-E3D-06).
So the host never guesses. `host.state` is derived on every call from facts the host reads
from Qt (`Quick3DHost._facts()` → `lifecycle.state_of`, a pure function whose whole truth table
runs in the unit tests) plus the two things Qt cannot report: the one offscreen frame was
taken, and `close()` ran. There is no "was shown" flag: an embedded host is shown, hidden,
resized and collapsed by its parent, which asks nobody.

**The contract is written down in ONE place: the module docstring of
`src/open_garden_planner/ui/view3d/quick3d/lifecycle.py`** — the facts, the six states, what
each state promises, which call is legal in which state, what `wait_ready()` means and what
raises what. Nothing else restates it — not this section, not ADR-048, not PF-E3D-06, not the
`ogp-3d-renderer` skill, not `host.py`. It stood in nine places once, and three of them were
wrong (review round 3); `tests/unit/test_quick3d_packaging.py` now fails a second copy of the
state table. Read it there before calling the host. What this section adds is how to live
with it:

- **The workspace needs `wait_ready()` nowhere on the GUI thread.** It is a nested event
  loop, and it takes user input: clicks, keys, timers and other objects' slots run inside
  it. A view shows itself — Qt draws it when the platform asks. A click, a hover, a tick
  that draws just calls: `try: host.pick(x, y)` / `except HostStateError` — the host takes
  the frame it needs itself. Never call `wait_ready()` from a timer slot, a sync tick, a
  paint or a resize handler. `grab()`, `pick()` and `project()` never run the event loop.
- **A tick that draws stops at its first `HostStateError`.** In the steady state `pick()`
  and `project()` take no frame at all (500 + 500 calls: 0 frames); after a resize, one.
  While the render target is behind they refuse on the evidence of ONE frame and take no
  other until a sign of progress is counted, the facts change, or 0.25 s have passed — so
  the next call of the same tick would get the same answer. (Review round 5: they took a
  frame per call — a tick that projected 200 labels spent 0.4 to 0.8 s on 200 refusals.)
- **Where a frame must be HAD and the caller can wait — an export, a tool, a test — call
  `wait_ready()` and act on its answer.** Do not reason about passes of the event loop: Qt
  delivers some resizes inside the call that caused them and others later (PF-E3D-06), and
  the main window the workspace is embedded in is put into full screen by
  `application.py`. It starts no pass of the event loop once its timeout — 1 s by default —
  is up, and it returns within that PLUS whatever was queued on the event loop when its
  last pass began: one pass delivers the whole queue (0.2 s asked, 1.80 s taken behind six
  handlers of 0.3 s); only `wait_ready(0)` is bounded by itself. It answers False after
  half a second of silence — time the event loop was idle, not time it was busy with
  something else; False is not "never", the cause may go. The first show of a process is
  the slow one (its first expose creates the graphics device) and overruns the default as a
  rule: True came after 0.70 to 0.92 s for a top-level host and after 0.96 to 1.73 s for an
  embedded one. Where that takes longer the answer is False while the host is on its way:
  pass a longer timeout (it costs nothing when nothing comes), or ask again.
- **A refusal is an answer.** `HostStateError` says "not now", names the fact that is missing
  and what to do; a caller that draws on a timer skips that tick. `EngineError` says the
  engine failed.
- **`grab()` on a live host is the synchronisation point**: it renders the current state now
  and reads it back. Do not wait for `frameSwapped` to be sure of a frame (PF-E3D-06).
- **`pick(x, y)` answers for the frame rendered last** and returns the item id, the part index
  and the hit point in the SCENE frame. "No hit" never means "could not look": a scene
  function that fails is an `EngineError`, not an empty answer.
- **A host is closed by `close()` — and by Qt**, when the widget that parents its container
  is destroyed (closing the main window does that). The host asks Qt on every call, so it
  reads closed either way and never raises sip's `RuntimeError` from a deleted C++ object.
- **A backend that renders no 3D says so.** Under the software scene graph — what
  `QT_QPA_PLATFORM=offscreen` selects — `renders_3d()` is `False` and `grab` / `pick` /
  `project` raise `EngineError`: a frame without the garden must not pass for one. Nothing
  collapses or minimises there either, which is why the default test tier checks the state
  machine's logic with the facts put where a window system would put them, and the render
  tier checks that Qt really reports them (§8.10.8).
- **Every property write is checked.** A name `Garden.qml` does not declare is an
  `EngineError` that names it — not a dynamic property that swallows the value.

The contract is tested from three sides: the truth table over every combination of the facts
(`tests/unit/test_quick3d_lifecycle_states.py`); the host's plumbing, with the facts put in
place (`tests/ui/test_quick3d_host.py`); and Qt itself —
`tests/integration/test_quick3d_lifecycle.py`, one call order per child process, because the
failure it guards against is a dead process, not an exception, judged against a table of what
a truthful host must answer and never against the state the host reports. Its last test is a
seeded random walk: 250 things a parent can do to an embedded host, in an order nobody chose,
and after each one either the scene at the size Qt gives for the window, or a refusal.

**Teardown and recovery: one owner.** The host owns every Model and its geometry —
`EngineScene.clear()` destroys them all, switches the sun off and drops the plan ground — and
the sink holds handles as names. `Quick3DSink.clear()`, the `EngineSink` verb that
`SceneSync.reset()` calls, asks the host once and empties its own books in a `finally`: legal
inside a transaction an engine error broke half way, twice in a row, and on a host that is
closed or destroyed, where it simply forgets.

A LIVE engine that cannot destroy a Model is the other case, and it is exception-safe too. A
Model leaves the host's books only when the engine confirms it — the Model is deleted or
retired — so after a failed `destroy_part` the handle is still a live part, and after a failed
`clear()` (which tries every Model, then the sun, then the ground, and raises one `EngineError`
at the end) `part_count()` still equals what `engine_parts()` reads from the engine. The sync
stays poisoned, the next `reset()` tries the same Models again, and until one `clear()` went
through the sink refuses `begin()`: its books are empty, the engine is not, and nothing is
built on that. `close()` goes through whatever a Model's teardown said (the Model dies with
the view) and counts the host as closed only at its very end — a `close()` that raised can be
called again.

One sink per scene: `Quick3DSink(host)` and `sink.attach(host)` refuse a host that already
holds Models (`SinkProtocolError`). They refuse rather than clear, because clearing would
destroy what another owner is showing.

Recovery after a failed engine call is `sync.reset()`, then `sync.apply(...)`; when the engine
itself died, `sink.attach(fresh_host)` in between points the emptied sink at a new host. It is
proven for every engine call the sink makes — one call fails in mid-transaction, reset, apply
— against `sync.expected_state()` (§8.29.1), on a list-backed engine, on the real host, and in
pixels; and with an engine that REFUSES to destroy, where no `reset()` may report success
while a Model is left.

**Trouble in a live view: `health()`.** `render_records` raises on a shader or QML error; a
SHOWN view has nobody to raise to, and a frozen exe has no stderr. What Qt reports about a
shown host ON THE GUI THREAD is collected in `host.health()` — a frozen `HostHealth` — and
written to the app's log (`app.log`, ADR-052) as it arrives:

| Field | From | Means |
|---|---|---|
| `qml_warnings`, `qml_warning_count` | the QML engine's `warnings` signal | a binding failed at run time, a scene function threw (file and line included); the first 50 are kept and logged, all are counted, and the log says once that further ones are only counted |
| `scene_graph_error` | the window's `sceneGraphError` signal | Qt could not create the graphics device: the host will never be live, and `wait_ready()` says so at once |
| `frames_presented` | `frameSwapped` | 0 some time after `wait_ready()` said yes: nothing reaches the screen. (With the display asleep it stays at 1 — never wait for a count) |
| `ok` | — | no QML warning and no graphics failure |

It is a poll surface: the workspace (L1.3) asks on a timer and turns the answer into a notice;
it answers in every state, also on a closed host. Three things about it are not negotiable:

- **There is no Qt message recorder for a shown host, and none may be added.** Qt renders a
  shown window on a thread of its own; PyQt's message-handler trampoline needs the GIL; and a
  render-thread message that arrives while the GUI thread sits in a Python-called `hide()`
  deadlocks the process for good — every run, on Direct3D 11 and on xcb (ADR-048, review
  round 2; pinned by a control in the lifecycle matrix). What keeps the product clear of it
  is a STATIC guard, an AST scan over all of `src/` (`tests/unit/test_quick3d_boundary.py`):
  the two Qt calls that install a process-wide Python callback (`qInstallMessageHandler`,
  `QLoggingCategory.installFilter`) may be named only by the recorder module, the recorder's
  `install` may be reached only from `offscreen.py`, and a render-thread signal may be
  touched only through the one queued-connect helper. **It is necessary, not sufficient**:
  it cannot see a handler that a third-party package installs (pytest-qt does, in tests),
  nor a Python override of a virtual that Qt calls on the render thread — and the host does
  not refuse to show itself beside such a handler (ruled out in review round 3: it cannot
  know whose it is). The one exception on record — the L0 spike's process-wide Python
  handler beside shown windows, only under `--spike-q3d` — left with the spike in L1.10.
- **`sceneGraphError` is connected, always.** With no slot on it Qt answers a failed graphics
  initialisation with a modal error box and then aborts the process — the whole 2D app.
- **No Python runs on Qt's render thread.** The two signals Qt may emit from it are connected
  QUEUED; the host counts every slot call that arrives on another thread
  (`slot_calls_off_the_gui_thread`), and the render tier requires 0.

What `health()` cannot see: a shader of a shipped material that does not compile — that is a
Qt message, and the frame still renders, without that material. **Shader errors of the shipped
shaders are caught before release, not at run time**: the render tier and the frozen
self-test compile every one of them on the calling thread, under a recorder, and the tier
shows that a shown window draws what that offscreen frame draws.

**The offscreen path — for processes that own themselves.** `offscreen.render_records(records,
shot=…, sun=…, ground=…, size=…)` runs the real `SceneSync` → `Quick3DSink` → `Quick3DHost` on a
host that is never shown — records, sun and ground in one transaction — reads one frame back and
closes the host: one host per frame, because a never-shown host has exactly one (the
contract). It is for the self-test, a tool, a test. **Not for the running app:** each call blocks the GUI thread for 0.4–1.3 s and
creates and destroys a graphics device, the pattern behind the memory growth ADR-048 criterion
10 still has open; the app shows a host and keeps it. The clock (`open_ms`) stops at the
finished readback. Every Qt message of the render is recorded; a QML error or a shader that
does not compile raises `RenderError` (which carries the recorder's report as `.qt`) — the
frame would have rendered anyway, in the wrong colours — and so does a backend that renders no
3D. This is the one place a Qt message recorder is installed, and it is safe only because a
never-shown window is rendered on the calling thread: the recorder counts every message that
arrives on another thread (`frame.qt["other_threads"]`, required to be 0 by the render tier
and by the self-test itself), and the call refuses to run while a Qt Quick window is shown in
the process. A builder that failed is contained by the
pipeline and leaves its item without a solid: `OffscreenFrame.build_failures` names every such
item, and the self-test and the render tests require it to be empty. The call leaves the
process as it found it: no output unless a `log` is passed, the Qt message handler and Qt's
logging rules put back. A process that owns itself wraps the call in `runlog.watchdog`: when
the time is up the reason, then every thread's stack, are written to the log and the process
exits with code 1. With `supervised=True` a second process ends the first from outside ten
seconds later if it is still there — on Windows the in-process exit was measured not to end a
process deadlocked inside Qt (PF-E3D-06). One watchdog per process at a time: a second one
while the first is armed raises `WatchdogError` (the timer behind it is one per process, and
a supervising process acts for exactly one block).

**The self-test.** `--selftest` (`main._run_selftest_bounded` → `quick3d/selftest.py`) renders
one hidden 160 × 120 frame from the bundle's own QML and shaders — a lit box, its shadow, one
swatch per material kind, so every shipped shader is compiled by the real backend — and judges
the pixels with a pure function: the box where our projection puts it, meadow beside it, shadow
where `core/shadow_geometry` puts the 2D shadow, every swatch drawn, no builder failed. It
needs no GPU (§7.4). ONE watchdog bounds the whole command — the Agent API block and the A1
checks as well as the render — and one log records it: after 300 s the reason is written in
words, then every thread's stack, and the process exits with code 1. The watchdog is
supervised: the exe starts itself a second time with the internal flag
`--selftest-supervisor`, and that process terminates the first — exit code 1, the reason in
the log — when it is still alive at 310 s. It acts for ONE block of ONE process and for
nothing else: the process is named by pid and creation time and must be the supervisor's own
parent (in the frozen build: running the same image); the block by a random nonce in the name
of its release event — a name per process let a finished block's late supervisor terminate
the block after it (PF-E3D-06); and arguments it may not act on end it with exit code 2 and one
line, before anything is opened. The safety net is checked like the subsystems it guards: on
Windows the self-test FAILS when that process did not start, refused, never found this block
(exit code 4 — it used to leave with 0, like one that did its job), failed itself (3 — also
when its own wait fails, which read as 0 until review round 5), or did not leave within
15 s of its release (`[selftest_supervisor]` in the log; its line on stdout is `FAIL
self-test supervisor -> …`, so it cannot be mistaken for a render failure). It also fails
when a Qt message of the render arrived on another thread than the one that rendered.

**What is not here.** No input handling and no orbit camera (L1.3); no look presets, sky, fog,
night rig or wind animation (L1.4, now §8.29.4) — `windTime` exists and stands still, and at 0 the wind
shaders move nothing: every vertex is drawn exactly where its mesh puts it, also one with the
full wind weight in a strong wind (the sway eases in over the clock's first two seconds).
"At rest" means the clock IS 0: a clock PAUSED at another value keeps the sway of that moment
in the frame. A truth probe — and the look story, when it animates the clock — pins
`windTime` to 0 or the wind strength to 0, not "paused"; no
ground texture
(L1.5: `set_ground` sizes the bare plan rectangle and the endless meadow, both in the one meadow
albedo); no builders beyond the default prism (L1.6, L1.7); no selection (L1.8).

### 8.29.3 The workspace — Plan / 3D / Split in the main window (L1.3)

Where the pipeline (§8.29.1) and the engine (§8.29.2) meet the app. The decisions and every
measurement are **ADR-060**; how it is tested is §8.10.9; what went wrong on the way is PF-E3D-07.
Since L1.9 the plan area of every main window — no switch; the default and what it costs are
§8.29.9.

**The parts, and which of them needs the engine.**

| Module | Engine? | What it is |
|---|---|---|
| `core/scene3d/camera.py` | Qt-free | `OrbitCamera`: a goal pose that input moves and a pose that follows it as a critically damped spring, integrated exactly; `frame_pose` (the pose that shows a plan); the clamps |
| `core/plain_text.py` | Qt-free | plan text as text: `normalise_text`, `clip_text` / `clip_line`, `log_text`, `plain_tooltip` (§8.11) |
| `ui/sim_clock_subscription.py` | no | `connect_qobject(channel, slot)`: a QObject on the sim clock, never called after Qt destroyed it (ADR-053 addendum) |
| `ui/view3d/init_guard.py` | stdlib only | `Init3DGuard`: the start marker and the compatibility flag as a state machine |
| `ui/view3d/sync_controller.py` | no | `Scene3DController`: the plan revision, the clock and the net's quiet timer in, at most one pipeline pass per event-loop turn out |
| `ui/canvas/canvas_scene.py` (the 2D scene) | no | the PLAN REVISION: `plan_revision`, `plan_changed(int)`, and THE nudge `note_plan_changed()` (below) |
| `ui/view3d/orbit_input.py` | no | `OrbitInput`: an event filter that turns the 3D window's mouse, wheel and keys into camera calls |
| `ui/view3d/problems_dialog.py` | no | the list of what 3D could not show |
| `ui/view3d/workspace.py` | no | `Workspace`: the modes, the lazily built 3D pane, the notices, the timers |
| `ui/view3d/quick3d/host.py` | **yes** | three things the workspace asked of the host: `prefer_software=`, `install_event_filter()`, `release_cached_resources()` |

`workspace.py` imports no Qt Quick binding: the engine is built by `Workspace.engine_factory`
— by default `quick3d_engine`, which imports `quick3d.host` and `quick3d.adapter` when it is
called. That attribute is THE test seam (§8.10.9).

**Layout.** `Workspace` is a splitter: canvas | 3D pane. *Plan* hides the pane, *3D* hides the
canvas, *Split* shows both, and neither side can be dragged shut. Leaving Split keeps its
position for the next session at once (it used to be kept only by an app closed IN Split). The
pane is a strip above a stacked widget that holds either the engine's window container or a
message page. The strip is two parts: a row of controls (mode switch, "Reset 3D View") and,
below it, the notices, one per line — the status line, "N objects are not shown in 3D" with
"Show List", the compatibility line and, on a row of its own, "Try Hardware Next Time".

> **Rule: a sentence is a label that wraps; a button holds a short command.** A button
> cannot wrap: squeezed, it cuts its text with no ellipsis, and given its way it makes the
> pane as wide as its text. Split in a 1366 px window gives the pane 455 px, and the German
> "Try Hardware Next Time" alone needed 456 px of text. Strip buttons come from
> `workspace._command_button` (never narrower than their text); the outcome of a click is
> said in a label of the strip, never written onto the button (pinned at 1366 px in en / de /
> es).

> **Rule: nothing overlays the 3D view.** It is a native window; a sibling widget does not paint
> over it. A control or a notice for 3D goes into the strip above the view, beside it, or in its
> place — never on top. (The one floating thing in the workspace is the mode switch in Plan and
> Split, and it floats over the canvas.)

**The life of the 3D pane** (`View3DState`): `not_started` → (first switch to 3D or Split: the
start marker is written, the engine factory runs) → `starting` → (the health poll sees the first
presented frame: the marker is removed) → `running`. Two ends beside it: `unavailable` (Qt
reported that it could not create a graphics device — a message, for the session, no retry) and
`failed` (building the engine raised — a message with "Try Again"). The host is never closed
and rebuilt on a mode switch; it is hidden with its pane and its scene stays.

**The pipeline pass.**

```
scene.plan_changed ─┐  (the plan revision moved)
date_changed       ─┴─► dirty ─► ONE posted event per turn ─► snapshot_records(scene, plan_date)
instant_changed ─► sun flag (light only: no snapshot)       ─► ground stage (L1.5's seam)
                                                            ─► SceneSync.apply(records, sun, ground)
scene.changed (a repaint no announcement explains)          ─► applied(TickReport)
    ─► (re)start ONE quiet timer, NET_QUIET_MS = 400 ─► the same pass, ONCE (reconciled=True)
```

**What starts a pass — the plan revision, and the net** (ADR-060 decision 5). A whole-plan
snapshot is O(total vertices) even when every record is cached, and `QGraphicsScene.changed`
fires for every REPAINT — a hover, a selection, a tool's preview under the mouse, the sun's
shadow while "Animate" runs. The first delivery took `changed` as "the plan is dirty": a
snapshot per repaint (a preview mouse-move cost 6.7 ms in Split against 1.0 in Plan on the
small bench plan, 18.3 against 0.7 on the large one). Now:

- **The fast path — what is announced.** `CanvasScene.plan_revision` moves exactly when plan
  CONTENT changed, at the chokepoints the scene and the undo stack already have: an item added
  or removed; a command executed, undone or redone (`set_command_manager` → `stack_changed`);
  a `GardenItem`'s position, transform, visibility, z or parent changing (THE item hook,
  `garden_item.handle_item_change`, which every item's `itemChange` calls first — pinned by a
  census of `ui/canvas/items`); a layer added, removed, reordered, shown, hidden, locked or
  made translucent (`layers_changed`); the canvas resized; the scene cleared; a geometry
  handle's every mouse move; and **THE nudge, `CanvasScene.note_plan_changed()`**, for a writer
  that goes round all of those. A moved revision marks the records dirty AT ONCE.
- **The net — what is not.** A `changed` with no revision move snapshots nothing; it (re)starts
  ONE single-shot timer (`NET_QUIET_MS` = 400 ms — twice the sun animation's tick, pinned),
  only while 3D is visible. Once the scene has been quiet that long, ONE reconciliation pass
  runs. It normally finds nothing; if it finds a difference, an edit path forgot its
  announcement: the pass applies it, `Scene3DController.unannounced_changes` counts it, one
  DEBUG line names the kinds that differed. So no edit stays out of 3D for longer than the
  quiet time, whatever writes it. No `changed`, no timer; a scene that is never quiet is
  reconciled every `NET_MAX_WAIT_S` (5 s) all the same. An announcement explains repaints for
  ONE turn after its pass, no longer: without that expiry an announcement that repaints nothing
  left "explained" standing, and the next unannounced write was never looked at (ADR-060
  decision 5). Blind spot, stated: a write to an item on an opacity-0 layer repaints nothing.
- **Qt's polish is not an edit.** One turn after an item is added Qt tells it
  `ItemVisibleHasChanged(true)` although it was visible all along; announced, every added item
  cost a second whole-plan pass. The hook remembers at `ItemVisibleChange` what the item was.
- **Qt's empty `changed([])` is not a repaint.** Every `item.update()` is reported twice to a
  listener of `changed`: the region at once, then an empty list (the queued half of the same
  update, finding nothing left). The net ignores the empty one; otherwise an announced write
  whose repaint lands after its pass costs a second snapshot a quiet time later.
- Measured after (real window, Split, recording sink): a time sweep with the sun simulation on,
  20 preview moves, three selections and a clear, a hover over handles, "Animate" for 2 s —
  0 snapshots while each happens, 1 after the quiet time, finding nothing; 31 edit paths, each
  announced (`unannounced_changes == 0`). A preview mouse-move turn costs the same in Split as
  in Plan: median ratio 0.94 (small bench plan) and 0.98 (large) on a quiet machine, 1.01 beside
  other suites (gate: ≤ 2.0, a `perf` test).

- **Hidden means paused**: with the pane hidden or the window minimised the controller keeps two
  flags and does nothing else. Showing 3D runs ONE catch-up pass — a plain `apply` of the current
  snapshot.
- **A pass owed to a shown pane waits for its notice.** "Building the 3D view…" is set and the
  pass starts after that label PAINTED (an event filter on the label; 250 ms fallback): a first
  pass costs the sum of its items, with the GUI thread inside it.
- **Nothing takes a frame from the live view.** The workspace tells the engine what the plan
  is; Qt draws it when it draws. No steady path — the pass, the health poll, a timer, a
  resize, the splitter — calls `grab()`, `wait_ready()`, `pick()` or `project()` on the shown
  host: a readback renders a frame that is never presented, and what it holds comes back only
  when a presented frame ends (in a view that presents nothing, never — ADR-060 decision 17).
  A picture of the 3D view for a file goes through `quick3d/offscreen.py`. A view that
  presents nothing is NOT held back: the pass applies, nothing is drawn or uploaded, and the
  first frame after the dark spell shows the plan as it is.
- **A document change is a plain apply**, not a reset; it drops what 3D remembers of the old plan
  (`_drop_plan_memories`: the plant builder's shapes, the record layer's outlines) and frames the
  camera once, when the new document is in the engine (`document_shown`). The workspace hears of
  it from `CanvasScene.document_replaced` — the app's ONE "the document was replaced" signal,
  emitted when the old document is about to go and never for an open that failed its validation
  (`Workspace.connect_plan`); the main window tells the workspace nothing by hand. A failed open
  therefore leaves the view, its camera and its memories as they were.
- **A failure is contained.** A sink call that raised, or a poisoned sync: `reset()`, one more
  `apply`, one log line. A second failure gives the pass up; the next CHANGE — of the plan, the
  date or the light — tries again, a repaint does not (the net stands down while a pass is
  owed). A pass that keeps failing writes ONE ERROR line per distinct failure of the outage;
  the same failure again is a DEBUG line, and the next pass in which nothing failed ends the
  outage. No exception of the pipeline reaches the event loop.
- **What a pass reports** (`TickReport`): the diff, whether a snapshot was taken, the time of the
  snapshot and of the apply, whether it had to recover, and `retired` — how many items lost
  their engine Models.

**What moves the camera.** Four things: user input in the 3D window, "Reset 3D View" (Home), the
first open, and a document change. Nothing else has a call site — an edit, an undo, a date or a
time change, a selection, a resized canvas leave the pose exactly as it was (identity, not
"close": gate G3). Home takes the SHORTEST turn to the default side: yaw is free while
orbiting, and aiming at the default yaw itself unwound every turn (six turns: 2,477.5° back to
317.5°); a snap (first open, new document) lands on the default itself.

**3D mode keeps the canvas selection — and shows it.** 3D mode hides the canvas while the
app's shortcuts stay (Delete, Ctrl+X, Ctrl+D). The workspace first cleared the selection on
entering 3D mode (a stopgap, `clear_selection_hidden_by_3d_mode`); the selection story (L1.8)
removed it, because the selection is SHOWN in 3D: the ring round every selected item, and the
info card below the view (§8.29.8). So the shortcuts act on what the user sees.

**When 3D cannot start.** A marker file is written before the first 3D window of a session is
built and removed after the first presented frame. A marker left by a process that is gone means
the driver took the process down: the next session renders 3D on the software adapter
("compatibility mode"), says so in the strip and offers "Try Hardware Next Time". Only the user
switches back. Three outcomes, not two: a start that dies in SOFTWARE mode too switches 3D OFF
(the flag says `off`; nothing is built; the pane says so and keeps the way back) — it used to
start software again and die at every 3D open. A marker carrying this process's own id with no
start of ours pending is a death (the process that had the id before us). And the poll that
confirms the first frame runs only while 3D is shown, so 3D hidden before its first frame takes
its marker away (`abandon`) and showing it again puts it back (`mark_again`) — a marker left
pending was read as a death by a second instance ten minutes later. The notice and "Try
Hardware Next Time" are shown in EVERY state of the pane while the flag is on (a machine that
could not start in software mode had no way back). `Init3DGuard`'s docstring is the state
machine.

**What 3D could not show.** `Scene3DController.skipped` (the record layer refused the item) and
`.failures` (its builder raised) feed a count in the strip and a non-modal list; activating a row
selects the item on the canvas. Fixing the item clears it with the next pass. The list shows at
most `MAX_PROBLEM_ROWS` (200) rows and then "… and N more" (a row that belongs to no item), and a
fill walks the scene ONCE for all the names: it used to walk it per row — rows × items on the
GUI thread, again on every change while the list was open (3,000 rows over 3,000 items: 3.1 s),
and one plan with duplicated ids is enough to get them. A notice of the engine ("The 3D view
reported a problem") stays until that engine is gone; a pass does not erase it.

**What a destroyed Model leaves behind.** Qt keeps graphics state for every Model it once drew.
`Workspace` adds up `TickReport.retired` and calls `host.release_cached_resources()` when
`RELEASE_AFTER_RETIRED` (64) piled up and the pipeline has been quiet for `RELEASE_IDLE_S`
(0.5 s; the health poll looks), or at once at `RELEASE_NOW_RETIRED` (512). A story that makes
the engine create and destroy objects on its own (a ground texture per bake, a selection
outline) must count them the same way, or measure that they leave nothing.

**How to add to it.**

- *A new consumer of the sim clock*: `connect_qobject(clock.date_changed, self._slot)`; never
  `clock.date_changed.connect(...)` (a scan refuses it).
- *The ground* (L1.5, wired — §8.29.5): the workspace builds the controller with
  `ground_baker=GroundBaker()`, which the controller hands to its `SceneSync`; every pass's
  `apply` bakes in the same transaction. While the baker's time budget leaves tiles pending
  the controller owes a GROUND pass (`SceneSync.continue_ground()`: no snapshot), scheduled
  like any pass — NOT `mark_dirty()`, which would snapshot the whole plan per 10-ms slice.
  What the bake could not do joins the problems list where the other sources meet:
  `problems_dialog.problems_of` and `Scene3DController._set_problems` (`ground_problems`).
  `set_ground_stage(stage)` stays the seam for another ground (`stage(previous_records,
  records, width_cm, depth_cm) -> GroundSpec`, run before `apply`; if it raises, the bare
  rectangle is sent and one line is logged).
- *A look, a sky* (L1.4): through the host; not through the pipeline.
- *A click in 3D* (L1.8): `try: host.pick(x, y) except HostStateError` in the input filter. The
  workspace calls `wait_ready()` nowhere and must not start to.
- *A new notice*: a label in the strip's notices, word-wrapped, `Qt.TextFormat.PlainText`, its
  text through `self.tr()`; anything that came out of a plan through `core/plain_text.py`
  first. A button beside it holds a short command (`_command_button`), never a sentence.
- *A writer that changes plan content without a command and without moving an item* (a
  handler that writes `metadata`, a geometry changed in place): call
  `scene.note_plan_changed()` — or `garden_item.note_plan_changed(item.scene())`, which tells a
  plain `QGraphicsScene` nothing — and `item.update()` if the canvas shows it. Forgetting it
  is not invisible: the net applies it after the quiet time and counts it in
  `unannounced_changes`; the announcement matrix (`test_view3d_plan_revision.py`) pins every
  edit path at 0.

### 8.29.4 Looks, sky and the animation policy (L1.4)

How the 3D view LOOKS — and why none of it can move a shadow. The decisions and every number are
the **ADR-059 addendum "looks, sky and the animation policy (L1.4)"**; how it is tested is
§8.10.11; what went wrong on the way is PF-L3D-05; the art direction behind the values is the
`ogp-lush-cinematic` skill (§3 rigs, §5 the Beauty Board, §7 the fix log).

**Truth and look are separate by construction.** Where the sun stands comes from `core/solar`
through the pipeline (`SceneSync.apply(..., sun=)` → `Quick3DSink.set_sun`): the light travels
along the negated sun vector. A LOOK — `core/scene3d/look.LookSpec`, made by
`look_for(sun, preset)` — holds everything else: the key light's colour and brightness, the
exposure, the sky's inputs, the fog, the shadow softness and the preset's cost. A day look has
no direction in it at all; once the sun is down (twilight and night) the look states its moon
(azimuth 165°, elevation 38°: a look, not an ephemeris — the plan's sun is below the horizon and
the scene still needs a key). The host aims the key light in ONE place,
`Quick3DHost._apply_light`: the look's moon if it has one, else the sun the pipeline sent, else
no key light.

| Part | Engine? | What it does |
|---|---|---|
| `core/scene3d/look.py` | Qt-free | the rig by sun elevation (three day anchors and their ramps; night below 0.5°), the presets, `look_for`, `sky_is_stale`, `AutoPreset` |
| `ui/view3d/look_controller.py` | no | `LookController`: the sun, the settings and the frame count in; `set_look` / `set_sky` / the wind out |
| `ui/view3d/quick3d/look.py` | no | `scene_properties` / `sky_properties` — the mapping onto `Garden.qml`'s properties; `engine_srgb` |
| `ui/view3d/quick3d/host.py` | **yes** | `set_look`, `set_sky`, `set_wind_running`, `rest_wind`, `_apply_light` |
| `quick3d/qml/Garden.qml` | **yes** | the environment, the key light, the flat fill, `buildSky` / `dropSky`, the wind's `FrameAnimation` |

**The mood follows the sun's height without a jump.** Noon at 30° and above, golden at 6°, low
sun at 0.5°, continuous ramps between them (colours mixed in linear light, exposure in stops,
the rest linearly; no step between adjacent half degrees above the bounds pinned in
`test_scene3d_look.py`). At 0.5° — exactly where the 2D shadow overlay stops drawing shadows
(`MIN_SUN_ELEVATION_DEG`), so 2D and 3D never disagree about whether the sun is up — the sun's
key light goes. Civil twilight follows, down to −6° (`TWILIGHT_DEG`): the low-sun rig fades
into the night rig (`twilight_rig`; colours in linear light, exposure in stops — mixed in
stops instead, the sky faded faster than the moon came in and the frame went darker than the
night it ends in, then brighter again), the sky's and the ground hemisphere's energy 1 -> 0.25,
saturation 1.06 -> 0.6, the sky draws no sun, and the key light is the moon fading in (0.32 x
the fraction: no key and no shadow just under 0.5°). Below −6°, night. The key light is never brighter than at noon; a low sun is
warmer and more exposed, not stronger; the light never rises as the sun sinks.

**Presets are cost, never mood.** `low` / `medium` / `high` / `ultra` (`PRESET_SPECS`) differ in
the shadow map, cascades, filtering and bias, anti-aliasing, ambient occlusion, glow and (ultra)
screen-space reflections — and no preset costs less than the one below it in any of them
(pinned). Low and medium both use 4x MSAA: FXAA let picket fences alias into a moiré, and 2x
MSAA still did (PF-L3D-05). Fog is on at every preset (low without it drew a one-row cliff where
the meadow meets the sky). Its distances follow the camera, not the preset (L4 owner pass, ADR-065):
`look.fog_depth_cm(distance)` begins it at 1.5× and fills it at 6× the camera's distance to its
target, floors 26 m / 160 m, full by 760 m, inside the meadow's 10 km edge and the 16 km far plane, set with every
`Quick3DHost.set_camera`. Sharpening is 0 everywhere; screen-space GI is never on. A preset
change applies one `set_look` call without moving the camera or rebuilding sky.
Crossing the Medium/High boundary also updates lawn-blade admission through the
existing scene diff (#607).

**Automatic quality.** With the setting `auto` (the default), `AutoPreset` chooses among low,
medium and high from the frames the view PRESENTS (`health().frames_presented`, Qt's own frame
signal) — polled every 0.5 s and only while the wind animates, because a view that draws on
demand has no frame rate (so reduced motion freezes the choice). Down when the median frame
time stays over 1/27 s for three seconds; up only after ten seconds since the last change — or
since the session's first poll — with every sample under 1/50 s; a level that proved too slow
is not tried again for five minutes, doubling up to an hour. No frame for ten seconds is NO
DATA — the display asleep, a stall — and never "slow": the preset holds. Where `auto` settled
and which levels it had to leave, until when (`view3d/auto_quality_level`,
`view3d/auto_quality_bars`), are stored and seed the next session — without the bars, "high is
too slow, medium is fine" stepped up and down once in every session. The frames are presented
frames under vsync: on a 30 Hz display or a remote-desktop session `auto` sits in the dead band
or steps down for reasons that are not the GPU's (ADR-059 addendum).

> **Rule: nothing that measures the frame rate takes a frame.** No `grab()`, `wait_ready()`,
> `pick()` or `project()` on the live host from the look (ADR-060 decision 17): a readback is a
> frame that is never presented, and what it holds comes back only when a presented one ends.
> A scan over the look controller pins it.

**The sky follows the sun — when the sun moved noticeably.** A procedural sky is a whole texture
generated on the GUI thread (Medium quality: about 0.1 s on the dev box's GPU) plus a light
probe Qt filters once per Texture (on WARP: 9–13 s on the dev box, 40–85 s on a CI runner). So
the sky is rebuilt only when the sun moved at least 1° (great circle) from where the SHOWN sky
draws it (`sky_is_stale`), and while the time slider is dragged only once the sun has rested
150 ms; a change of the sky's PHASE (`sky_phase`: day with a sun disc, twilight, night) is
built at once — sunset at 0.5°, nightfall at −6°, dawn; through twilight the sky follows the sun
by the degree (its colours do); a night sky is never rebuilt for the sun's position (it draws no
disc). A sky the engine cannot build is logged once and the session goes on with the plain sky
and the flat fill — the look itself is sent separately, so a failing sky never keeps it from
the screen. Light, exposure and fog follow every instant — the fog is computed for the sky
ON SCREEN while the sky lags, so it still meets the horizon. Every build is a FRESH `Texture`
with its OWN data object as its child (inputs at the cheapest quality, the quality raised last);
the old pair is destroyed after the scene shows the new one (a Texture loses its data when a
data object it held earlier is destroyed — #476). `sunLongitude = azimuth + 90°` (measured).
No sky is built before the first sun is known, and no sky input is bound live.

**Compatibility mode: no sky, no wind, auto = low.** ONE render-mode parameter
(`LookController(software=True)`, passed by the workspace) decides the three things a software
adapter cannot afford: no sky texture and so no light probe is ever created; no wind — an
animated view renders every frame (1,351 % of one core on WARP, measured by the review); and
`auto` is `low` (with nothing animated there are no presented frames to choose from). A plain
background in the fog's colour and a flat fill light (the mean of the sky's top and horizon in
linear light × probe exposure × the sky's energy × `FILL_OF_SKY` 0.5 — at full strength the
mode read +22 luma over the GPU's sky-lit frame) stand in. The same plain sky and fill are
what the top-down truth view and the `--selftest` frame render; the self-test FAILS when its
frame built a sky.

**Colours derived in linear light are handed over as the engine reads them.** Qt Quick 3D
linearises a colour property with a polynomial, not the sRGB curve; for a dark colour (a night
fog: linear 0.0015) the two differ threefold. The fog, the plain sky and the fill are therefore
given as `QColor.fromRgbF(engine_srgb(linear))`, the inverse of the engine's own conversion.

**The wind (animation policy).** The foliage and grass shaders sway by `windTime` (uv.x = sway
weight, uv.y = phase). A `FrameAnimation` advances it — only while the 3D pane is shown, reduced
motion is off AND the adapter is not a software one. Hidden: the clock stops where it is and nothing ticks (the engine itself
keeps a hidden window's animation running — measured — so the policy stops the clock rather than
trust "hidden"). Reduced motion (Preferences → 3D View; Qt exposes no operating-system preference
for it) RESTS the clock at 0: every vertex is drawn where its mesh puts it. A paused non-zero
clock is not rest — truth probes and the board pin the clock to 0.

**Wiring.** The workspace hands the look controller the sun the pipeline last sent
(`Scene3DController.sync.sun`) after every pass, so the light and the look are computed from one
moment and one solar path; a time-of-day change is a light-only pass — no snapshot of the plan.
The pane's visibility goes to `set_showing`; Preferences' "Save" to `apply_look_settings()`.
A retired sky leaves nothing behind without a cache release (measured: ADR-059 addendum), so it
does not count towards the workspace's release policy for retired Models (ADR-060 decision 15).

**The production Beauty Board.** `scripts/render_beauty_board.py` renders the spike's shots
(golden hour, sunset, noon, morning, December noon, night, walk — same dates, times, cameras)
through the production pipeline, one never-shown host per frame, and writes PNGs and
`metrics.json` with the truth rows (shadow IoU in perspective with cascades, north-up, the sky's
sun azimuth, fog against sky, night against noon, the evening from 6° to −7°, the date each
shot's models were built for, read back from the records rendered) and the look rows (the
fences' aliasing against a supersampled render, the plan's edge, the horizon's hue) and the
frame rate. Procedure:
`ogp-lush-cinematic` §5.

### 8.29.5 The ground bake — flat surfaces as ground tiles (L1.5)

A lawn, a terrace, a driveway, a path or an in-ground bed is not geometry in 3D: it is part of the
ground's picture. `ui/view3d/ground_bake.py` paints that picture from the snapshot's **records**
and never from the live scene (the L0 spike hid items and rendered the scene: it toggled item
visibility, cleared the selection and painted the canvas's beige). Building blocks: §5.13.
Decision record: the ADR-059 addendum "ground bake". Traps: PF-L3D-03, PF-L3D-04 and PF-CAN-21. Test pattern: §8.10.10.

**What is painted.** A record is painted when the snapshot gave it a paint description
(`Material.paint` — every item but a plant) **and** the scene holds no solid for it
(`SceneSync.solid_ids`). A lawn is on the ground; a house is not, and what lies UNDER a house is
whatever flat item was drawn there, or meadow (`MEADOW_RGB`, the one albedo the engine's bare
ground has). Records are painted bottom to top in the snapshot's order — the canvas's stacking
order. An item beside the plan rectangle is not on the ground. Not painted, by decision: the
selection, labels, the canvas's drop shadows, a bed's square-foot grid and the diagnostic borders
and badges — they are the 2D view's overlays, not the garden's surface.

**One implementation with the canvas** wherever the canvas has more than a primitive:

| what | the one implementation | who calls it |
|------|------------------------|--------------|
| fill brush (24 textures, tint) | `core.fill_patterns.create_pattern_brush` | the items; `ground_bake._brush` |
| furniture sprite | `core.furniture_renderer.render_furniture_pixmap` | `RectangleItem` / `CircleItem.paint`; `_paint_sprite` |
| path / fence styles | `ui.canvas.items.path_style_paint.PathStylePaint` (extracted from `PolylineItem.paint`) | `PolylineItem.paint`; `_paint_polyline` |
| rectangle, ellipse, polygon, plain line | one `QPainter` call each (`drawRect` / `drawEllipse` / `drawPolygon` / `drawPath`), mirrored | — |

Both `PathStylePaint` callers bound their walk with the same `clip` + `WalkBudget`
contract: the ground bake per tile, the canvas item per visible viewport (#450).
A 19 km gravel path used to generate its 475 001 elements on every canvas repaint (gravel's
dots until L4's owner pass; a 5 cm chain-link path is the densest walk now);
the live paint now generates only what the viewport exposes, while an export
(cache cleared) still gets every element.

Paved path base fills use `Qt.PenJoinStyle.BevelJoin` to align with the outer border chord, and `_offset_path` detects acute inner bends ($offset \cdot (\vec{u}_1 \times \vec{u}_2) > 0$) and trims overlapping segment ends to their exact intersection point, eliminating self-intersecting V-spikes (#605).


**The paint frame.** The canvas paints an item in the item's OWN coordinates: a fill texture is
anchored at the item's coordinate origin, a sprite is aligned to whole centimetres there. A
record's geometry is centred on its anchor, so the record carries where that anchor is in item
coordinates (`params["paint_origin"]`, part of the geometry signature), and `paint_record` poses
the painter with `QTransform(cos, sin, −sin, cos, T − R·origin)` — the item's scene transform.
The style of the pen and the item's opacity are `Material.paint` (`Paint`: width, style, cap,
join, opacity — a restyle is a material change); a polygon AS DRAWN is `Record.outline` where
`footprints` is not that polygon. A record painted from its regions (one that has no
`outline`) is ONE path in ONE painter call — one fill, one stroke, non-zero winding with the
contract's orientations — so the picture depends neither on the order of its regions nor on the
order of a region's holes, and a translucent fill or pen is blended once.

*A circle's turn is paint.* A circle's record does not turn (scene contract: its footprint and
its solid are the same whatever its rotation), but what the canvas paints in the circle's
coordinates does — a fill texture, a dash pattern, a sprite. That turn travels in
`Paint.rotation_deg` (`LocalFrame.paint_turn_deg`; 0.0 for every other shape, whose transform
carries the turn) and `paint_record` adds it to the painter's pose. In the diff matrix a circle
turned about its centre is therefore ONE material change — no geometry, no transform, no builder
(`tests/integration/test_scene3d_pipeline.py`, `test_scene3d_snapshot.py::TestDiffMatrix`); a
plant, which is never painted, still changes nothing.

*Where the two colours come from.* The stroke is read from the LIVE pen; the fill from the item's
`fill_color` / `fill_pattern` ATTRIBUTES — a textured brush cannot be asked for its pattern or
its tint. So the bake is right exactly where an item's attributes describe its brush, and the
canvas, which paints the brush, never showed where they parted: the offset tool and the corner
tools copied the brush alone (an offset copy of a blue brick terrace was baked, and saved, as
default wood). `core/item_look.py` is the ONE place that carries a look from item to item
(`copy_visual_style` — `master`'s since #470, which the corner tools now use too), that writes a
loaded item's attributes (`restore_stored_look`, `master`'s since #502) and that sets a pen
together with the attributes describing it (`adopt_pen`, L1.5). The guard is behavioural: at the end of every integration test, every item of
every scene the test built must state the look it paints (`tests/integration/conftest.py`,
§8.10.10); `tests/integration/test_item_style_in_step.py` walks the shipped operations that build
an item from an item, and the writers that restyle one in place (PF-CAN-21).

**Flat items the solid path refuses.** A path of 3,000 points or a lawn of 5,000 vertices costs
too much to cut into buildable regions (`outline_too_large`) — but painting needs no regions.
Such an item, when it has no height, keeps its record: `footprints == ()`, the centre line or the
drawn outline, and its paint. The SIZE bound stays in front of everything: above
`MAX_ITEM_VERTICES` (16,384) an item is never read, copied, kept or painted.

**Tiles.** `core/scene3d/ground.py::GroundGrid` lays a pixel grid over the plan rectangle: 512 px
tiles at the finest of 1, ½, ¼ … px/cm at which the ground has at most 4096 × 4096 px and 256
tiles (24 × 16 m: 20 tiles at 1 px/cm; 50 × 30 m: 60 tiles; 100 × 100 m: 25 tiles at ¼). Every
tile is a crop of that ONE grid at whole-pixel offsets, so neighbours meet without a seam by
construction; pixels are RGBA8 with row 0 on the tile's NORTH edge. A tile is a pure function of
the records painted into it, in order.

**Dirty tiles.** `SceneSync` hands the baker the diff the geometry path uses — one edit, one
snapshot, one diff, builders and bake in one transaction. The baker looks at the records the diff
names, marks the tiles under their old and new paint bounds (after a re-order: every tile that
holds records), finds each dirty tile's records in one walk down the stack and re-paints a tile
only if its list changed or holds a changed record. Every other tile is handed out as the SAME
object — which is how the sink knows not to upload it. Measured at L1.5 (idle dev box):
bench_small (98 records, 11 painted, 20 tiles) full bake 13 ms, one move of a 3 m item 3.4 ms
median, at most 2 tiles; bench_large (424 records, 45 painted, 60 tiles) 69 ms and 3.3 ms. These
are L1.5 figures. Since L4 builds furniture as solids, 9 and 25 records are painted, and
bench_large's moved item is a stand-in terrace (ADR-065). A move dirties the
tiles under the item's old AND new paint bounds. Each place is at most four tiles for an item of
up to 3 m; together they are at most four when the move is up to 2 m (old and new place then span
less than one tile's width in each direction — what the gate's 31 moves of 44 cm measure), and
up to eight for a longer one.

**The time budget — a bake does not have to finish.** Painting is the one part of a bake whose
cost Qt decides and a plan can drive up, it runs on the GUI thread, and it is paid again for
every edit that shares a tile; only the baker can stop between two tiles. So one `bake` call
paints for `BAKE_BUDGET_S` (10 ms; `GroundBaker(budget_s=…, clock=…)`, `None`: no budget): at
least one tile, a look at the clock after each, and when the budget is spent the tiles it has not
reached stay **pending** — handed out as the objects they were. The picture is STALE there (bare
ground where there was none yet) and never wrong elsewhere. `GroundBaker.pending` says how many;
every later call — whatever it is told, an empty diff too — goes on with them, **nearest to the
last edit first** (so an edit made while a backlog exists is painted before the backlog), and
re-admits only the tiles the new changes touch. A tile without records is never pending: bare
ground is free. **The promise:** once nothing is pending, the tiles are those of one unbudgeted
bake of the same records — with a diff or without one (pinned over random edit sessions through
three bakers at once, §8.10.10).

Why 10 ms: the workspace's gate is 50 ms from an edit to its frame, and the bake's own gate —
10 ms for one small edit on the bench plans — still holds with the budget ON: an edit that fits
the gate is ONE pass (measured: 31 moves on each bench plan, one pass each). That holds for
an edit of two tiles. An edit where four tiles meet can run over the budget by its last tile:
on CI it read ≤ 10 ms in one uninstrumented run and 12.15 ms in the next (run 40407192860),
and 13.29 ms under coverage (run 40405246734). No gate placed an item on a tile corner before
L4 (#388); the readings and the comparison with master are in ADR-065. G3 holds such an edit
to a median of 20 ms in at most two passes. The owner decided #615 on 2026-10-29: the four-tile
bound is not forced down to 10 ms across CI hardware, it follows the `BAKE_BUDGET_S` contract
("the budget plus ONE tile"), i.e. one 10 ms pass plus its last tile. Measured on CI (PR #613,
median per move): 7.29–12.15 ms uninstrumented in one pass, 10.57–14.57 ms under coverage in one
or two passes; two-tile edits keep 10 ms in one pass. Measured with the real clock
at L1.5: bench_small opens in 2 passes (longest 11.6 ms), bench_large in 8 (longest 13.4 ms).
What the budget does NOT bound is one tile: a pass costs the budget plus the tile it is in — and
one tile more when it brings an edit while older tiles are still pending (below). The
plan built to be slow — two gravel paths of 16,384 points zigzagging over 16 tiles (gravel's dots,
measured before L4's owner pass made gravel a texture), 12.6 s in one
call before — is now 16 passes of 0.73 s in the median (longest 0.92 s), and moving a 1 m square
beside those paths is two passes of 0.45 s; a COMB polygon is worse still (the cost table below).

`SceneSync` reports it: `ground_pending` is true while tiles are pending; `continue_ground()` is
the pass for a caller with nothing new to apply (one bake, no diff, no builder; one transaction
when a tile changed), and any `apply` goes on as well. While work is pending the sink's ground is
behind `expected_state()` in exactly the pending tiles and equal to it in everything else;
`reset()` drops pending work with the tiles; the failure rules do not change (ADR-059 addendum
"ground bake", review round 1).

**The backlog cannot starve.** A call that brings an edit while older tiles are pending paints
the edit's own tiles first (as many as the budget allows, at least one) and then at least ONE
tile of the backlog, whatever the budget says: a pass costs at most the budget plus two tiles.
Without that rule an edit a pass — a drag — kept the budget for itself: with one tile a pass, 14
tiles stayed pending after 1, 5, 10, 20 and 40 edits. Now fifteen edits drain fifteen pending
tiles, and the edit is shown in its own pass also when its middle lies in an older pending tile
(`TestTheTimeBudget::test_an_edit_a_pass_does_not_starve_the_backlog`,
`::test_an_edits_own_tiles_come_before_the_backlog`).

**A tile whose paint fails keeps its picture.** If painting ONE tile raises as a whole (no image
for it: `MemoryError`), that tile keeps the picture it had — the same object — and every other
tile goes on; the bake does not raise and the baker forgets nothing. The tile is listed in
`GroundBaker.tile_failures` (key → the error's type and text), is NOT pending — no pass retries
it on its own — and is tried once more by the next call that brings a change; it is logged once
per tile and kind of error. Before, such a failure cleared the baker: the sink kept its sixteen
painted tiles until the NEXT edit, which took the ground to one painted tile and cost sixteen
tile paints, fifteen passes and a traceback — as did every edit after it
(`TestATileThatCannotBePainted`: two tile paints and one pass an edit, one log line in all).

**A bake that raises anywhere else restarts the baker — it does not clear it.** Such a bake is
the sync's `ground_failure`: the ground the sink shows stays, and the baker's books (which
records, in which order, what was pending) can no longer be trusted. `GroundBaking.restart()`
forgets the books and KEEPS THE PICTURES: the bakes that follow paint every tile anew, within
their budget, and a tile they have not reached is handed out as the object it was. The edit
after such a failure shows the sixteen painted tiles it showed before (cleared, the baker
showed one), a tile whose record went away meanwhile is bare at once, and after fifteen passes
the ground is the finished one — with the same OBJECTS wherever the picture did not change, so
nothing is uploaded twice. `clear()` — a new plan — still forgets the pictures; a restart
followed by another plan rectangle drops them.

**What a bake may cost** — a plan file is untrusted input (§8.11). The criterion: the bake may
cost what the plan file holds, times a stated constant, as the 2D canvas does for the same plan;
it must not AMPLIFY (a small file buying superlinear or unbounded work or memory), and no bound
may sit behind the work it bounds. The baker holds one entry per painted record (its tiles as a
block of four integers, the box of its geometry, whether its fill can cover a tile) plus, per
tile, the ids it was last painted with and — while it is pending — the ids it is to be painted
with. The bounds of one tile, each taken before the work it bounds:

| bound | a tile | what it stops | where it is checked |
|-------|--------|---------------|---------------------|
| `TILE_RECORDS` | 256 | records painted into a tile — beyond it a tile loses its SMALLEST (below) | the walk that hands tiles their records; a record left out is never touched |
| `TILE_VERTICES` | 262,144 | outline vertices × passes (points converted, a path built; a styled path ×8, a dashed stroke ×3) — and once more for a tile's cover tests | the same walk, the same ranking; the highest-ranked record is always painted (≤ 16,384 vertices, styled 131,072) |
| `TILE_ELEMENTS` | 16,384 | stones, planks, posts, dots of path styles — as many as a line is LONG | generated inside the tile only (the walk is clipped, phase kept), each charged in `path_style_paint` before it is handed out |
| `TILE_WALK_STEPS` | 16,384 | steps of the exact walk that finds them | charged before the walk, for the whole segment; beyond: arithmetic |
| `TILE_DASHES` | 32,768 | dashes of dashed pens | a line is cut to the tile; each run's dashes (length / 3 pen widths, a pen at least a pixel) are charged before it is stroked — an unaffordable run is stroked solid |
| `SPRITE_MAX_PIXELS` | 262,144 | the image a furniture sprite is rendered with (its size is the plan's) | before the renderer is asked: a larger one is rendered smaller and stretched |

**What a tile is painted with, and what a capped tile loses** (`GroundBaker._admit`). The rule
is its OUTCOME: **when a bound bites, a tile loses its smallest records, never a large one.**

1. The *members* of a tile are the records whose paint reaches it, from the topmost down to the
   first one whose fill **opaquely covers the whole tile**: nothing under that one can be seen,
   so nothing under it is looked at, charged or painted (50,000 opaque lawns over the whole
   plan: one record a tile, 21 comparisons in all).
2. A tile keeps ALL its members while they are at most 256 and cost at most the vertex bound.
3. Beyond a bound it keeps the members that overlap it MOST. A member's rank is how much of the
   tile its paint box overlaps — box against box, no vertex is read — and ties go to the
   topmost; the lowest-ranked members are left out until both bounds hold, and the tile is
   `capped`.
4. What is kept is painted in z order, bottom to top.

So a tile under 2,000 pavers on a lawn shows the lawn and its 255 largest pavers, wherever the
lawn's edge runs. Pinned by records for four lawns — the plan rectangle, one 10 cm inside the
plan's edge, one half a centimetre inside, one that covers 30 % of the tile — each under 255, 256
and 2,000 pavers: zero lawn pixels bare, and wherever the ground is not the unbounded picture
that picture has a paver. And for a real scene against the canvas's own render (a LAWN rectangle
10 cm inside the plan, pavers of 20 cm): at 256 pavers one paver is missing (484 px, mean 0.032 of
255), at 2,000 the pavers of 145 of 400 places (71,200 px, mean 4.88), no lawn pixel bare
(`TestATileLosesItsSmallestRecords`). Two earlier rules failed exactly here, and both had been
pinned by counts: "the topmost 256" dropped the lawn (138,240 px of a 5.12 m square bare); "the
topmost 256, and under them what covers the WHOLE tile" kept a lawn only when it was the plan
rectangle — 10 cm inside the plan's edge 149,604 px were bare (mean 24.4 against the canvas).

What the rule does not know is a SHAPE. A thin line's paint box is its bounding box, so a long
diagonal line ranks with a lawn (256 of them over a lawn: the lawn is the one left out); a small
item on top of 256 larger ones is left out although it is the topmost; and of members that
overlap the tile equally — 300 translucent lawns over the whole tile — the LOWER ones are left
out.

The work is one pass over a tile's members: per member one overlap (four `min` / `max` and a
product) and at most one push and one pop on a heap of 256. A tile is closed — asked about no
further record — by an opaque cover, by the end of the records, or once it holds 256 members that
each overlap it whole: nothing below can outrank one of them, so the next member only shows that
the tile is capped, and closes it. "Opaquely covers the whole tile" is asked only of a member
whose paint box contains the tile and whose fill is opaque, and it is exact, not a guess: the
tile's four corners inside the rectangle, the true ellipse or the circle; for a polygon no edge
through the tile and its middle filled under the polygon's own fill rule — its rings are read
once per test, within the vertex bound above. "Opaquely" is read off the brush: a fill alpha of
255, an item opacity of 1, and a texture without a translucent pixel (all 24 are opaque).

One `WalkBudget` per tile carries the element, step and dash bounds through all its records; a
spent budget means "no more", never "no bound". A tile painted with a bound in force is in
`GroundBaker.capped` — plain data for whoever tells the user what the 3D view left out (the
workspace's problems list, L1.3). Bounded elsewhere: tiles and pixels of a plan (`GroundGrid`,
refused before any arithmetic for a size that is not a positive finite length up to 10 km), the
brush and sprite caches (200 entries each; a brush texture is 256 × 256 px). A fill, a solid
stroke or a sprite that reaches far beyond a tile costs the tile's pixels: `QPainter` clips to
the image. Memory: the largest ground is 64 MB, held once — the baker's tiles are the very
objects the sync and the sink hold. Measured for 50,000 TRANSLUCENT whole-plan rectangles on 20
tiles, a small square on top: 55,121 entries held (one per record and tile would be 1,000,001);
5,141 comparisons for a full bake — 257 a tile (the 256 it keeps and the one member that shows
it is capped) and one for the square — and 5,120 record paints; 258 comparisons for an edit of
the square. For 50,000 opaque ones: 21 comparisons and 21 record paints.

**The bounds are on COUNTS; what a count costs is the rasteriser's — and that varies by three
orders of magnitude.** One tile at a bound, measured: 256 turned textured rectangles 196 ms;
262,144 polygon vertices of a wavy ring 172 ms (0.7 µs a vertex); five plain lines of 16,384
points folded into the tile 509 ms; two gravel paths of 16,384 points 2.65 s (gravel's dots, before
L4's owner pass made it a texture). And ONE record
whose outline is a COMB — every tooth crossing every scanline of the tile — costs Qt 1.2 ms a
vertex: 1.2 s at 1,024 vertices, 4.8 s at 4,096, 19 s at 16,384, in one tile, and the vertex
bound admits sixteen of the last (not run to the end: about five minutes, extrapolated). The 2D
canvas needs 10.5 s, 38 s and 186 s for ONE paint of the same three items, so the criterion
holds — the bake costs less than the canvas does for the same plan, and nothing amplifies — but
no count here bounds Qt's time for a scanline that crosses 16,000 edges. That is what the time
budget is for, and all it can do: such a tile is one pass. Bounded and linear, not small.

**In the engine** (`quick3d/ground_tiles.py`, `Garden.qml`): one quad per tile in the plan's
plane with its own texture. `flipV: true` (rows are north-up); `ClampToEdge` on both axes (a
repeating texture blends a tile's opposite edge into its border); each quad 0.02 cm wider than
its tile on every side; the bare plan rectangle is not drawn while tiles lie on it; a tile is not
pickable. Only a tile whose picture changed is uploaded — as a **new Model with a new texture**,
and its old Model is destroyed: ONE TEXTURE PER `Texture` ELEMENT, FOR LIFE. (An attached
`QQuick3DTextureData` cannot be updated in place; and a `Texture` pointed at a second data object
forgets it when the first is destroyed — the tile is drawn white: PF-L3D-04.) **Keep-alive rule:**
per tile the texture the scene shows, plus — until the next presented frame, and at the latest
the next update — the one it replaced. `ground_tiles.textures_alive()` counts the objects that
exist on the C++ side.

**How the product wires it** (L1.5 Part B, in the workspace of L1.3 — `ui/view3d/workspace.py`,
`ui/view3d/sync_controller.py`):

- **One baker per engine.** The workspace builds its `Scene3DController` with
  `ground_baker=GroundBaker()` (a budget of 10 ms a pass); the controller hands it to its
  `SceneSync`. Every pass of the plan — an edit, a date, the catch-up, the net — bakes in the
  same transaction as the geometry, with the same diff.
- **A ground pass, not a snapshot.** While tiles are pending (`SceneSync.ground_pending`) the
  controller owes a GROUND pass: `SceneSync.continue_ground()` — one bake, at most one
  transaction with only `set_ground` — scheduled exactly like any pass (the posted event of
  `_schedule`). Measured with a chain of 40 posted events of 10 ms each, offscreen and on the
  Windows platform: a timer due after 5 ms fired after the first slice — the chain starves no
  timer (the 2D side's debouncers, the sun animation) — pinned: a 0 ms timer armed inside
  ground pass 5 fires before pass 7. An edit preempts it (its records pass continues the
  ground itself); a hidden view pauses it (a flag, nothing else); a pass that was given up
  does not schedule it (the next change tries again). `TickReport.ground_pass` marks such a
  pass; `snapshot_count` does not move, and the net never sees one: the bake paints images,
  never the scene. The workspace takes a ground pass for no more than that: it does not hand
  the look a sun (`set_sun` restarts the stale-sky timer) and does not count it as "the
  pipeline worked" (that would push the quiet-time release back while the ground paints).
- **A ground pass that fails is rebuilt ONCE per change** (`GROUND_RECOVERIES`). The sink
  raised: a full pass resets and applies — which paints the first slice again and goes
  through — and the next ground pass fails the same way. Rebuilding again was a busy loop on
  the GUI thread (review 3's probe, an engine that refuses one painted tile: 2,308 ground
  passes and 329 recoveries in 3 s, never idle). So the second failure since the last change
  of the plan (`mark_dirty`, `document_changed`, `reset`) gives up like any pass that cannot
  be rebuilt: records dirty, nothing scheduled, the controller `idle`, ONE ERROR line for the
  whole outage (a records pass whose ground then fails does not end it), and a NOTE in the
  problems list — "3D ground: it could not be finished; it is tried again with the next
  change". A change of the light does not rebuild the ground again (the sun animated over a
  broken ground would rebuild on every step); the next edit, date or document does.
- **What the user is told** (`Scene3DController.ground_problems`, plain `GroundProblems`): items
  whose paint raised (`baker.failures`: a row per item — "it could not be painted completely on
  the 3D ground"); and NOTES of the ground as a whole, rows that belong to no item and come
  first: ground work given up until the next change (`GroundProblems.unfinished`), tiles that
  hold more surfaces than they can show (`baker.capped`), tiles that could not be painted
  (`baker.tile_failures`), a bake that raised (`sync.ground_failure`, not tried again until a
  record, the solids or the plan change). An item whose paint failed IS shown — cut off where
  it failed — so it is not counted with the objects "not shown in 3D" (`problem_count`); like
  every note it makes the ground `incomplete`, and the strip says "… the 3D ground does not
  show all of the plan". The list still names the item.
- **A new document** drops the baker's tiles with the plan's other memories
  (`_drop_plan_memories`): a tile not yet painted is bare, never a picture of the old plan.
- **The release policy does not count tiles.** A re-baked tile is a new Model, but tile Models
  need no cache release (twenty cycles of new tile Models stay flat without one), and every
  release leaves about half of the same-size tile textures behind (#532, known limit 11) — so
  `TickReport.retired` counts items only, and ground work never asks for a release or makes
  one more frequent. It cannot make one rarer either: the releases that item changes cause
  leak whatever the ground did before them.
- **The tile's material is the meadow's** — roughness 1.0, specular amount 0.15
  (`Garden.qml`'s `groundTile`): PrincipledMaterial scales the sky's diffuse light by
  (1 − specular amount), so other values put a luma step where a baked lawn meets the endless
  meadow at the plan's edge (the L1.4 look review measured 2 to 8 luma for 0.92 / 0.2).
- **The frozen `--selftest`** bakes one flat lawn with the product's baker (budget 0, 128-px
  tiles: twelve tiles over as many passes) and judges the lawn's colour where it lies.

Pinned by `tests/integration/test_scene3d_ground_wiring.py` (§8.10.10).

`render_records(..., ground_baker=GroundBaker())` does the same for one offscreen frame — it runs
the passes until nothing is pending — and reports `ground_tiles` / `ground_failure` with it.
A STILL PICTURE of a live view goes that way too, never through repeated `host.grab()`
(limit 6).

**Known limits** (each with what was measured; the manual-test checklist of the story names
1, 7 and 9).

1. **Arcs, Bézier curves and text are not on the ground.** They have no record — the snapshot
   knows rectangles, ellipses, circles, polygons and polylines — so the 3D view shows nothing of
   a construction arc, a curve or a text annotation, flat or not.
2. **A line up to a pixel wide is not the canvas's, pixel for pixel, where it crosses tiles.** Qt
   rasterises such a pen per image and starts anew in every tile. Measured on a 1100 × 700 cm
   plan of six tiles: a SOLID 1 px line differs from the canvas's one image in 420 to 569 px by
   more than 8 of 255 (largest 147; the review's line: 1,123 px, largest 171), mean ≤ 0.07; a
   DASHED one has its dashes somewhere else in a tile — up to 1,903 px by more than 8, largest
   225, mean ≤ 0.22. The same lines at 1.5 px and wider, solid or dashed, are bit-identical. The
   hairlines INSIDE a path style (a border, a bar, a mesh) behave the same: mean ≤ 0.016.
3. Where a dashed outline is cut to a tile, the one corner where its two ends meet is blended
   twice (a pen-width square: at most 120 px by more than 2).
4. **A dashed circle or ellipse that crosses a tile border is stroked along chords** (0.02 px from
   the true curve), Qt's own along four Bézier arcs: the dashes lie up to a pixel apart. Measured
   for a circle of 110 cm with a 7.5 cm dashed pen across two and four tiles, turned or not:
   mean 0.018 to 0.020, about 1,000 px by more than 8 (largest 76). Wholly inside one tile it is
   the canvas's own call, bit for bit.
5. A plan of more than 16.7 million cm² (41 × 41 m) is baked at ½ px/cm, a larger one coarser
   still.
6. **No repeated `grab()` on a live host that is not presenting.** Direct3D 11 frees what was
   released when a frame is PRESENTED, and a frame rendered by `grab()` is never presented: in a
   hardware-adapter window that presents nothing, each grabbed frame leaves what was uploaded for
   it committed until the view closes (PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md: a `grab()` after every re-bake of a 16 MB ground
   +16 to +17 MB a cycle; no `grab()` +0.0; flat on WARP and wherever frames are presented).
   Re-bakes themselves do not grow the process — gate G6 is unconditional in the two cells it
   has (a software rasteriser that presents; the hardware adapter, whose window presented
   nothing and so renders nothing: PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md). A screenshot goes through the offscreen path,
   which gives everything back when its view closes.
7. **While ground work is pending, tiles are stale.** After opening a plan, and after an edit
   that touches a costly tile, the ground catches up over several passes; a tile not yet painted
   shows its older picture (bare ground on first open). Nothing shows the user WHICH tiles are
   behind; `SceneSync.ground_pending` only says that some are.
8. **A record's coordinates are on the contract's grid (1e-7 cm), the item's are not.** An item
   whose points are not round numbers — a chamfered or filleted corner, a turned item — is
   painted from points up to 5e-8 cm away, and single antialiased pixels of a style's elements
   differ (a chamfered gravel path in ONE tile: 118 px, largest 8, mean 0.0003).
9. **A capped tile holds less than the plan**: its smallest records beyond 256 — ranked by how
   much of the tile their paint box overlaps, so a thin diagonal line counts as large and a
   small item on top of 256 larger ones is lost — a style's elements beyond 16,384, dashes
   beyond 32,768 (drawn solid). `GroundBaker.capped` names the tiles; nothing reaches the user
   until the workspace shows it.
10. **Painted as the EXPORT paints, not as the live canvas clips.** The live canvas paints an
    item through its cache, which cuts whatever a style draws beyond the item's bounding
    rectangle — the bars of a 30 cm metal fence reach 37.5 cm from the line, the rectangle 17 cm.
    Exports paint without the cache and show them whole; so does the ground.
11. **OPEN upstream ([QTBUG-151940](https://qt-project.atlassian.net/browse/QTBUG-151940);
    TD-040; #532 closed) — every cache release leaves about half of the ground's same-size tile
    textures behind, re-baked or not.** *Cause:* a Qt Quick 3D 6.11.0 bug, read in its source
    and proven by measurement (#532): `QSSGBufferManager::clear()`
    (`qssgrenderbuffermanager.cpp` ~2049–2052) walks `customTextureMap` with `++it` while
    `releaseTextureData(it.key())` erases through its own lookup (~1516); Qt 6's `QHash` shifts
    the next entry of a collision run back into the freed slot, `++it` skips it, and
    `customTextureMap.clear()` drops the skipped entries unreleased. The key's hash (~2290,
    `qssgrendertexturedata_p.h` 74–77) covers only size, depth, format and transparency, so
    same-size tiles all collide and about half leak per release (WARP, 16 × 512²: +10.8 /
    +11.7 MB a cycle against a prediction of 8 × 1.333 MiB). *The condition* is "two or more
    same-size tile textures cached at a release" — a re-bake is not needed: static tiles, a
    release and a redraw leak too (the "same textures + release −0.28" control of the first
    measurements below was broken: its frame was white, no texture ever loaded).
    *The exposure in the product.* The bake asks for no release and makes none more frequent
    (tile Models are not counted), but EVERY release the workspace makes leaks (ADR-060): at
    64 items that lost their Models and half a second of quiet, or at once at 512 — a delete
    or a regrow of that many, a document change, and a DATE change on a planted plan (every
    dated plant regrows: an animated date releases each time 512 Models have piled up). Qt can
    also release on its own (read in the source, not tested): `~QQuick3DWindowAttachment()`
    queues `QQuickWindow::releaseResources()` when its pending cleanup queue is not empty
    (`qquick3dscenemanager.cpp`, v6.11.0 line 596). Each
    release keeps about half of the ground's same-size tiles. The largest ground is about
    4096² px (limit 5: larger plans are baked coarser) — ~85 MB with its mip chain, so up to
    ~42 MB per release; bench_small's ground (2400 × 1600 px in 20 tiles, 19.5 MiB with mips)
    read, in the workspace's G7 soak on the RTX 4070 (one release per rebuild), dedicated GPU
    memory +9.3 to +11.4 MB per rebuild (eight runs) with the product's release, against 0.0
    to +0.8 with the bake off. *Tried and rejected:* in-place updates (leak, and a stale
    picture), distinct tile sizes (flat at 16 tiles, not at 32 / 64 — chance neighbour
    buckets), tiles as
    `Texture.sourceItem` images (flat in isolation, one generation per rebuild still kept in the
    workspace). *How it is gated* (§8.10.9, review 3): G7 measures the PRODUCT — the bake on —
    against `LEAK_BOUND_MB_PER_RELOAD` (10) + 0.6 × the soak's own tile-texture bytes per
    release × releases per reload (11.7 MB on bench_small, so 21.7); a non-strict `xfail`
    tripwire holds the GPU slope to the plain 10 and passes the day the leak is gone (not
    strict: the leak reads about as much as the bound on this plan); the bake-off run stays
    as Model churn alone, against the plain bound. *A fix:* upstream Qt, or a tile path outside
    the buffer manager's maps that passes G7. *Upstream:* filed on 2026-10-30 as
    [QTBUG-151940](https://qt-project.atlassian.net/browse/QTBUG-151940) (component Quick: 3D,
    affects 6.11.0 and 6.12.0). Its reproducer is committed as
    `docs/09-architecture-decisions/adr-048-evidence/qtbug-151940/texturedata_release_leak.qml`;
    that folder's README says how to run it. Read on 2026-10-30, the loop is unchanged in
    qtquick3d v6.11.3, v6.12.0 and `dev` (eaf90eeb8c32), and the reproducer leaks the same on
    6.12.0 as on 6.11.0 — a bump to 6.11.3 or 6.12.0 does not fix it. How much leaks depends on
    the process's `QHash` seed: 6 to 8 of 16 same-size 512² textures per release
    (`QT_HASH_SEED=0`: 6 in every run), 26 to 32 of 64 same-size 256² textures — below the
    gate's 0.6 share.
    *Re-check* (this entry and TD-040 replace #532 as the tracker). Triggers: every Qt pin bump
    in `pyproject.toml`, and every change of QTBUG-151940 (the owner reported it from their
    account, which watches it; a "Need More Info" there is answered from that account). Steps:
    (1) Read `QSSGBufferManager::clear()` at the new pin's qtquick3d tag. If the
    `customTextureMap` loop still iterates while `releaseTextureData()` erases, only the
    versions named here and in TD-040 move. (2) If it changed, run the reproducer under the new
    runtime (WARP presents with the display asleep): the leak is gone when `registeredTextures`
    stays at 16 in all 10 cycles while `framesRendered` rises. (3) Then run G7 several times on
    a hardware adapter with the display awake
    (`OGP_RENDER3D=1 venv/Scripts/python.exe -m pytest tests/integration/test_view3d_workspace_render.py -m soak -n 0`):
    the bake-on GPU slope must fall into the bake-off range (0.0 to +0.8 MB per rebuild). The
    tripwire alone proves nothing: it passes with the leak in most runs (§8.10.9). (4) Remove
    `KNOWN_532_SHARE`, the allowance and the tripwire, and update §8.10.9, ADR-048 criterion 10,
    TD-040 (`fixed`), reference 13 of the `ogp-3d-renderer` skill and the comment at the Qt pin
    in `pyproject.toml`. If Qt closes the report without a fix, record the reason here and in
    TD-040 and mark the limitation permanent.
    *The first measurements, as taken* (before the cause was known — their "re-baked tiles
    only" reading is superseded above): the workspace calls `QQuickWindow.releaseResources()`
    when items lost their Models (ADR-060). When ground tiles were RE-BAKED before such a
    release — new `QQuick3DTextureData` objects replacing old ones — Qt Quick 3D kept about one
    generation of those textures for good. Measured on WARP, a 16-tile ground, twenty cycles:
    re-bake + release each cycle +10.7 to +13.3 MB a cycle (+7.4 to +8.7 without mipmaps);
    re-bake without release flat; one release, then twenty re-bakes flat; a release every
    fifth cycle a step of 10 to 25 MB at each release. In the workspace's own soak
    (bench_small, every rebuild re-bakes): dedicated GPU memory +7.5 MB per rebuild with the
    release after quiet and +19 with the release in the pass, against 0.0 and −0.1 without the
    baker.

### 8.29.6 Built-world builders and base stacking (L1.6)

The production builders live in `core/scene3d/builders/` (ADR-059 addendum "builders v0"); where an
item stands is one rule shared with the 2D shadows (ADR-037 addendum "base stacking").
`builders.production_registry()` is what the wiring hands to `SceneSync`: the twelve built-world
kinds of this section (`builders.register`) and the three plant kinds (`plants.register`,
§8.29.7) — 15 registered kinds, none in both families, every other kind on the default prism
(`tests/unit/test_scene3d_builders.py::TestRegistration`;
`tests/integration/test_scene3d_built_world.py::test_a_raised_bed_with_two_real_plants_through_the_production_registry`
takes a raised bed and two real plants through both).

**Which kind gets which builder.**

| Kind | Module | Parts (`name`: material kind) | Colour |
|---|---|---|---|
| `HOUSE` | `buildings`, `roofs` | `walls`: vc · `roof`: roof | walls sandstone on every route (`buildings._house_walls`, the `BuiltBuilder` `recolour` step; L4's owner pass), roof = clay tile; no usable ridge → one sandstone `walls` block |
| `GARAGE_SHED`, `TOOL_SHED` | `buildings`, `roofs` | `walls`: vc · `roof`: roof | walls tinted, roof = shingle |
| `FENCE` | `lines` → `fences` / `walls` | `fence`: vc — or `hedge`: foliage (hedge style), `wall`: vc (stone style) | tinted (the item's stroke) |
| `WALL` | `lines` → `walls` / `fences` | `wall`: vc — or the fence of its style | tinted |
| `RAISED_BED` | `beds` | `bed`: vc | baked: oak planks, soil |
| `CONTAINER`, `WALL_PLANTER`, `CONTAINER_ROUND` | `beds` | `walls`: vc · `soil`: vc | walls tinted, soil baked (the palette's soil) |
| a `GARDEN_BED` with a height | `beds` | `walls`: vc · `soil`: vc | walls tinted, soil = the item's own fill (`fill_texture`: its "Boden-Substrat") |
| `HEDGE_SECTION`, `HEDGE_POLYGON` | `hedges` | `hedge`: foliage (the dark core and the leaf shell in one mesh) | baked: the hedge texture's greens |
| `TREE`, `SHRUB`, `PERENNIAL` | `plants` (L1.7, §8.29.7 — registered by `plants.register`, not by this section's `register`) | `wood`: vc · `foliage`: foliage — or `placeholder`: vc for a plant without a height (no shadow) | baked: the recipe's palette, the 2D bark colour |
| everything else | `build.default_builder` | tinted sides (`prism_sides`) + a `fill_texture` cap (`prism`), or nothing without a height | the item's own fill on top, the tint on the edges |

**A solid shows the fill the ground baked (#628 follow-up, ADR-037 addendum).** A lawn, path,
terrace, driveway or generic shape is painted into the ground while it lies flat (§8.29.5); the
moment it is given a height it becomes a solid and that painting stops, so its 3D faces carry the
item's own fill: `MeshPart.fill_texture=True` names such a part, and the sink hands its Model
the canvas's picture (`core.fill_patterns.tinted_pattern_pixels` — the same tinted texture the 2D
brush uses, RGBA8, opaque, its mean the fill colour) through `vcPart`'s `baseColorMap`
(`patternMap`). One picture per (pattern, fill colour), shared and refcounted by the sink
(`release_fill` with the last Model), so a recolour is a material update and a removed object
leaves nothing behind. A SOLID fill has no picture and shows its colour through the same call.
UVs are (position + paint_origin) / 256 on the CAP — the canvas's phase, the record's footprint being centred on its anchor (the forge's 256 px at 1 px = 1 cm, pinned against every texture). The SIDES are the item's tint, not the picture: the canvas paints no texture down an edge, and one fill prism smeared a lawn's grass and a bed's soil down the walls (the owner's second pass). A raised flat item keeps its RELIEF too — a lawn's blades ride the new top, and the height gates (`top_cm`/`fit_scale`, `verify_builder`) ignore `ground_detail` so they are not squashed under the requested height. A raised pool's water takes the same picture WITH plan UVs — without them `texture(uFill, UV0)` read one texel (the committed gate measures luma std 0.000 without the UVs — one value over 194,304 pixels — against 17.25 with them, on a 300 × 220 cm pond at 40 cm): `water.frag` samples it through `uFill` (linearised) and keeps its hue rule and reflection. Measured, Direct3D 11,
1000 × 400 top-down, two 300 cm squares at 40 cm: GRASS reads luma std 26.0, SOLID 0.0, at the
same mean (121.3 / 120.8). The X-ray screen door does not sample the map, so a ghosted solid keeps
its fill colour; PF-L3D-17 holds the two engine traps — a `var` map must bind as
`patternMap ? patternMap : null`, and a `Texture` gets its data at birth because a re-pointed one
goes white (`ogp-3d-renderer` §5).

**What a line becomes is decided in one place**, `builders/lines.py`, from its kind and its style
(`params["path_style"]`, a `PathFenceStyle` name, absent for the plain line); `fences.py` and
`walls.py` are geometry only.

| Kind | Style | Built as |
|---|---|---|
| `FENCE` | none | the default fence: posts, two rails, pickets (`WOODEN_FENCE`) |
| `WALL` | none | the wall (`STONE_WALL`) |
| either | one of the five fence styles | that style, whatever the kind |
| either | anything else — a path style, a name no builder knows | a **plain panel**: the stroke as wide as drawn, up to the height |

The last row is the honest fallback: a style without a solid of its own is never given some other
style's look (it used to become a picket fence). It gets the body the plan itself describes — the
solid the 2D shadow model casts. The five names are a mirror (`fences.FENCE_STYLES`;
`core/object_types.py` imports Qt) pinned against `PATH_FENCE_STYLES`' "fence" category, so a new
fence style fails a test until a builder is chosen for it. At run time the fallback writes ONE
warning per style name to the application's log (`lines._report_plain`), on the first build of a
line in that style — never one per build, and for the first 64 names of a session only: then one
line says that no more follow (starting the memory over would log every name again on every
rebuild pass). A style change sets the stroke's colour
and width too (`apply_style_preset`), so it arrives as `replace_geometry` + `update_material`.

**The rules a builder obeys** (on top of §8.29.1's contract):

1. **The top is the height, by construction.** Build FOR the height: the highest vertex is
   `record.height_cm` to the float32. Give primitives a bottom and a top (`boxes(…, z0, z1)`),
   never a size to add. Wrap the shape function in `common.BuiltBuilder`: it applies the safety
   net (`fit_parts`), and `fit_scale(record)` must be 1.0 — a fit that does something is a bug.
2. **No height: the nominal one.** `BuiltBuilder` builds an item without a height at its kind's
   nominal height — what the 2D resolver answers for the kind alone, `effective_height_cm(kind, None)`;
   the builders hold no table of kinds — and with no nominal height it builds no parts. What is
   built casts in 3D (ADR-065, owner's manual pass). This path is nearly dead in production and is kept as the contract for hand-made records:
   every registered kind but `GARDEN_BED` has a default height, so the snapshot always gives its
   record one. And `GARDEN_BED` is registered for a state the GUI can barely produce — a garden
   bed that carries a height (only through its metadata: the panel offers no Height field for a
   garden bed without one) — so that its plants, which then stand 2 cm under its rim, have soil
   to stand on.
3. **Stand on z = 0.** The lowest vertex is the item's own ground. `transform.base_cm` lifts it;
   a builder never adds it.
4. **Polylines from the centre line.** Use `record.path` and `record.path_width_cm`, per
   segment. Never take `record.footprints` of a polyline for its shape: they are the outline of
   its STROKE — for a closed line one outer ring, with the ground it encloses as a hole in
   `record.holes` — and the outer ring alone lids the garden. Nothing may be built over that
   hole: `verify_builder` refuses a solid that covers more than half of it. That default is for
   loops the size of a garden. A wall or hedge reaches 19–20 cm either side of its line, so a
   small closed loop of one covers over half of what it encloses and is refused although it is
   right: verify such a loop with an explicit `hole_cover_limit` and say why (the test for a
   1 m loop uses 0.65). At the other end the gate has a size floor (`build.HOLE_MIN_WIDTH_CM`,
   10 cm): a hole narrower than that is not judged, so a 12 cm loop of wall — one solid block —
   passes. Measured for square loops at 1 cm steps of the side (6 – 200 cm), the default
   refuses: a WALL 15 – 120 cm, a stone-wall fence 16 – 118 cm, a hedge fence 19 – 111 cm and
   again at 114 cm (the gate samples the hole on a coarse grid; its verdict is not monotonic at
   the edge of a range). The test pins three sides only: 12 cm passes, stroke + 12 cm and 1 m
   are refused.
   **One plain outline, or the plain block**: a builder that needs ONE simple outline — a gable
   roof, a bed's frame, a pot, a hedge — checks that it has one (`common.has_one_plain_ring`;
   `footprint_of` raises otherwise). "One plain outline" is: one outer ring, no hole, and NOT
   `params["outline_resolved"]` — the contract's flag for a polygon drawn crossing or touching
   itself. Any other polygon-footprint record is built as `common.plain_block`: ALL regions,
   holes cut out, up to the height (`BuiltBuilder.uses_the_plain_block` decides before any shape
   function runs). The same function is every builder's fallback block (a house without a
   usable ridge), so no fallback takes `footprints[0]` for the whole. **The ring count is not a
   detector of a self-crossing drawing — the flag is.** A resolved outline can be one plain
   ring (a pentagram, measured), and it is still the block: a resolved ring can come within
   0.002 cm of itself, so nothing is offset from it, and a HOUSE's ridge was drawn for another
   outline — the snapshot hands none on, and the house builder hangs no roof even if one is
   handed in. (Until the flag existed, such a house kept a gable roof.)
5. **Stay on the footprint.** A frame's outer face is the footprint; a round container's rim is
   the footprint's own 24-gon (`lathe` puts its ring vertices on `circle_footprint`'s). Stated
   exceptions: a roof oversails by its overhang; a hedge leaf's tip may pass the outline by a few
   centimetres; a linear item has a nominal thickness (the plan has none). **Corners**: `sweep`
   and `offset_ring` mitre a corner up to `BEVEL_BEYOND` = 2 offsets (a turn of 120°) and bevel a
   sharper one on the side where the edges run apart — no eave spike on an acute-triangle house,
   no spike of coping on a hairpin wall. Where the edges run together (an inset, the inside of
   a bend) the true intersection stays, up to `MITER_LIMIT` = 4 offsets from the joint. **The
   bound and its condition:** nothing lies further than 2 offsets from the line or ring it was
   built on when every leg of a line is at least 4 offsets long (76 cm for a wall). A leg
   shorter than the inside mitre runs back along it puts that corner beyond the leg's other
   end; there the bound is 4 offsets (a wall zigzag with 25 cm legs: 2.6–2.7), and the solid
   overlaps itself.
6. **Flat faces from their winding.** Build flat geometry with `primitives.flat_mesh` (normals
   are computed, never written) and pass `outward=` where you know which way a face looks — the
   winding then follows it.
7. **Colour.** A part that shows the item's own colour is `tinted=True` with `palette.TINT`
   (pure white) vertices. Every other colour is a `palette` entry — mirrored from a 2D table and
   pinned to it. A colour in no 2D table is a finding, not a new entry.
8. **Seed** from `params["seed"]` through `build.item_seed`, nothing else — and name the bit
   generator: `np.random.Generator(np.random.PCG64(seed))`, never `np.random.default_rng(seed)`
   (numpy may change what the default is, and every seeded hedge would reshuffle).
9. **Budget.** State triangles per metre or per corner in the module's `triangle_budget`
   (`builders.triangle_budget(record)` dispatches) and assert it as a ceiling — never pin an
   exact count unless the count is the contract. And make no Python-level call per vertex:
   `tests/perf/test_scene3d_built_world_budget.py` counts calls, so a loop over vertices fails on
   any machine, whatever the clock says.
10. **Name sets.** Import a set of names from its Qt-free home (`container_model.MATERIALS`); ask
    a function rather than copy its table (`nominal_height_cm`); where the home imports Qt, mirror
    it and pin the mirror against the source in a test (`FENCE_STYLES`). An unknown name gets the
    honest fallback, never another name's look.

**Primitives** (`builders/primitives.py`, numpy, no Python loop over vertices): `flat_mesh`,
`boxes`, `bevelled_boxes`, `prism`, `polygon_cap`, `sweep` (a `(lateral, z)` profile along a plan
polyline, mitred or bevelled, open or closed, per-edge colours), `plank`, `lathe`, `tubes`, and
the plan helpers `ccw_ring`, `offset_ring` (may return more points than it was given: a bevelled
corner is two), `polygon_triangles`, `split_triangles_by_line`.

**How to add a builder.**

1. Write `_shape(record, height_cm) -> tuple[MeshPart, ...]` in a module of `builders/` and wrap
   it: `build_x = BuiltBuilder(_shape, "x")`.
2. Register the kind in the module's `register(registry)`, add the module to
   `builders/__init__.register`, and add the kind to `BUILT_WORLD_KINDS`.
3. Add records to `tests/unit/scene3d_builder_cases.py` — sizes, the local geometry turned by
   several angles, with and without a height. `tests/unit/test_scene3d_builders.py` then runs gate
   G1 over them: `verify_builder`, exact top, base 0, fit scale 1, budget, winding, footprint,
   colours.
4. Add what only this archetype has (a ridge, a soil level, a seed) as its own test class.

**Base stacking** (truth gate "Base"). `ui/canvas/footprints.item_base_cm(item, lookup, at_date)`
is the one answer to "how high does this item stand". An item is lifted onto a parent's soil only
when BOTH hold:

1. its `parent_bed_id` names a visible `is_bed_type` parent with a resolved height —
   `object_height.standing_base_cm` → `soil_surface_cm(type, height)`: `SOIL_DROP_CM` (2 cm)
   under the rim of a bed, AT the height of a container (whose height is its soil fill height).
   No base is derived from a height that is not finite or beyond `MAX_PARENT_HEIGHT_CM` (10 km,
   the scene contract's bound on every length): such a base would be out of a record's range
   itself. That is all the height module says;
2. its **stable geometric centre** lies inside that parent's shape —
   `footprints.standing_point(item)` (the outline's anchor in scene coordinates: a plant
   circle's centre, the origin of its record) tested with `footprints.shape_contains`, the
   app's one point-in-bed predicate.

Otherwise 0, as before L1.6. The first condition stays the honest half: an explicit link that
geometry does not support (`set_parent_bed` with `link_is_geometric: false`, or a plan written
before #443) never lifts. Since #443 every edit path keeps the link in step with that same stable
centre — creation, moves (arrow keys, typed coordinates, align/distribute, constraint
propagation), a bed's create/resize/turn/vertex edits, paste/duplicate/array/mirror, the panel
and the agent — inside the SAME undo entry as the edit (ADR-037 addendum "bed membership is
reconciled by geometry"). **Where a linked plant stands follows its centre all the same** — the
second condition is asked on every walk, whatever moved the plant.

**A parent the 3D scene does not hold lifts nothing — settled in the snapshot.** Whether a
parent HAS a record is known in one place, `snapshot_records`, once every record is built: a
parent is left out when one of its lengths is beyond the contract's range (a bed 30 km wide, a
bed 10 km + 1 cm high), when its outline cannot be built, when its record failed. Every record
whose `parent_id` names no record is then put on the ground (`base_cm` 0; `parent_id` stays).
`item_base_cm` itself knows nothing of records, and the 2D casters are not touched: in 2D such a
bed still casts, and its plant casts from its soil — except for the bed TALLER than 10 km, whose
plant casts from the ground there too (the height bound above). Both axes are pinned
(`TestTheOneRule::test_a_parent_the_scene_cannot_hold_is_not_there`,
`::test_a_parent_without_a_record_lifts_nothing`).

**One predicate, one point.** Every link decision and the lift ask `shape_contains` with the SAME
point: `bed_membership_point` returns `standing_point` since issue #443 (iii), so a badge, a
highlight or a selection ring cannot change which bed holds a plant or where it stands. There is
no margin and no disagreement left to pin: `TestLinkAndLiftAskTheSamePoint` asserts the two
functions return the same scene point under a badge, and that the link and the lift agree. A new
caller that asks either question takes `standing_point`; neither writes its own containment test
(a guard counts them).

`item_base_cm` is asked by `snapshot_records` (→ `transform.base_cm`) and by
`collect_identified_casters` (→ `IdentifiedCaster.base_cm` and, flattened, `ShadowCaster.base_cm`,
§8.20); its membership half, `standing_parent`, is asked alone by the sun receivers (§8.27: which
parent's solid a plant stands in). `beds.py` puts the soil at the
same `soil_surface_cm` — one function for the soil mesh, the 3D base and the 2D caster's base. A
bed that changes height reaches each of its plants as one `update_transform`; no plant mesh is
rebuilt. A bed that is resized reaches a plant it no longer contains the same way (38 → 0).
**Cost**: 2.8 µs per lifted plant; the parent's shape is built once per walk
(`ItemLookup.shape_of` — Qt's `contains` rebuilds it per call). bench_large, 240 lifted plants:
the caster walk 3.9 ms before L1.6, 5.0 ms now; `snapshot_records` 8.6 → 10.0 ms.
**An `ItemLookup` lives for ONE walk.** It holds each parent's shape as it was when the walk
asked; kept across an edit it answers from the old shape (measured: a bed shrunk away from its
plant, a kept lookup still says 38). Do not keep "the scene's lookup" on a controller or a view:
a test reads the source and holds three things
(`TestTheParentShapeIsBuiltOncePerWalk::test_a_lookup_lives_for_one_walk_and_is_never_kept`):
the identifier `ItemLookup` appears in `src/` only as an import (under its own name), as the
class, as a parameter's annotation and as a call inside the three walks (the casters, the sun
receivers, the 3D records) — so `make = ItemLookup`,
an alias import and `functools.partial(ItemLookup, …)` fail it; a walk binds its lookup to a
local name and uses that name ONLY as an argument of `item_base_cm` / `standing_parent` /
`_record_of` — so a list,
a dict, `.append(lookup)`, `setattr`, `return lookup, 1` and a closure fail it; and the three
functions that take a lookup use their parameter the same way. What a reading cannot see is
stated in the helpers: a dynamic spelling (`type(lookup)(…)`, `getattr(module, "Item" +
"Lookup")`, `copy.copy(lookup)`), and what a callee that only shares the NAME of a taker does.

**A known smell.** `ui/canvas/footprints.py` is collecting jobs: footprints, the base rule and
the app's point-in-bed test — and `core/commands.py` imports the last one from `ui/` (lazily,
inside the function, as it already imported `GardenItemMixin`). The predicate belongs somewhere
both layers may import without that arrow; it is not restructured in L1.6.

**Remaining limits of base stacking.** The nesting decisions are unchanged: a plant links to the
SMALLEST plant-parent containing it, and parents do not nest. Pinned in
`tests/integration/test_scene3d_base_stacking.py::TestMembershipIsReconciledAndTheLinkAloneNeverLifts`:

| State | What the plan holds | Result |
|---|---|---|
| a climber on a trellis that stands in a raised bed | linked to the trellis (the smallest parent) | the climber at 0, its neighbour in the bed at 38 |
| a pot standing on a raised bed | the pot has no parent (only plants do) | the pot on the ground, its plant at the pot's soil (30), not at 68 |
| a bed whose outline is not one plain outline (several rings, a hole, or a self-crossing drawing: `outline_resolved`) | built as the plain block, top at the rim | its plants stand 2 cm INSIDE the block: "on its soil by construction" holds for the bed builders only |
| an explicit Link action on a plant outside the bed | linked, `link_is_geometric: false` | on the ground until the plant's next move re-decides it |

The states that used to be known limits — a bed drawn around a plant, an array copy carrying its
source's link, a plant mirror-copied without its bed, a bed moved by a typed coordinate or
align/distribute — no longer exist: #443 reconciles all of them in the same undo entry, pinned in
`::TestMembershipIsReconciledAndTheLinkAloneNeverLifts` (a, b) and
`::TestCopiesAndMovesFollowTheLink`.

**3D shadows against the 2D model.** The truth gate "Shadows" (`ogp-lush-cinematic` §1,
IoU ≥ 0.85) is defined on a solid box caster. The built world is not a set of boxes, and the
committed `scripts/measure_built_world_shadows.py` says what that costs — 3D area ÷ 2D area, IoU
of the mesh's ground shadow against the 2D model's, and the REACH (how much further, +, or less
far, −, the 3D shadow extends along the shadow direction: where its tip is), each at a sun of
15° / 35° / 60°:

| Kind | 3D ÷ 2D area | IoU | Reach 3D − 2D (cm) | Why |
|---|---|---|---|---|
| raised bed, box, plain panel | 0.99–1.00 | 0.99–1.00 | −0.6 … 0.0 | none: the same prism (its top edge bevelled) |
| hedge (polygon, section) | 0.94–0.98 | 0.93–0.97 | +2.7 … +4.4 | leaf shell drawn in; leaf tips |
| round tub / terracotta pot | 0.89–0.91 / 0.81–0.83 | the same | −0.6 … −0.3 | taper |
| house, sun square to the ridge | 0.92 / 0.81 / 0.92 | 0.85 / 0.74 / 0.82 | −270.0 / −270.0 / −108.2 | gable: the ridge is mid-house, the 2D prism's top edge at the far wall |
| shed, sun square to the ridge | 0.92 / 0.93 / 1.03 | 0.85 / 0.83 / 0.88 | −150.0 / −81.4 / −21.0 | the same, on a 3 m deep shed |
| house, sun along the ridge | 0.90 / 0.99 / 1.06 | 0.82 / 0.86 / 0.88 | +30.0 / +30.0 / +30.0 | the roof's overhang past the gable wall |
| wall | 1.04 / 1.10 / 1.24 | 0.96 / 0.91 / 0.81 | +15.0 / +15.0 / +15.8 | nominal section: WIDER in 3D |
| stone-wall fence, hedge fence | 1.04–1.06 / 1.13–1.15 / 1.31–1.37 | 0.94–0.96 / 0.87–0.89 / 0.73–0.76 | +14.5 … +15.3, +19.5 … +19.6 | nominal section |
| picket fence | 0.67 / 0.68 / 0.70 | 0.65 / 0.66 / 0.68 | +2.0 / +2.0 / +2.4 | porosity: LESS in 3D |
| metal fence | 0.19 / 0.21 / 0.24 | 0.19 / 0.20 / 0.24 | +0.8 / +0.8 / +0.8 | porosity |
| chain-link fence | 0.13 / 0.14 / 0.19 | 0.12 / 0.13 / 0.19 | +1.5 / +1.5 / +1.5 | porosity |

So: a solid line item casts a wider shadow in 3D than the 2D model, more at a high sun; a porous
fence casts a fraction of it — the hours-of-sun map shows shade behind a chain-link fence where
the 3D fence lets over four fifths of the sun through. **Where the tip is** agrees within 2.5 cm
for the prisms, the pots and the post fences, and does not for a gabled building with the sun
square to its ridge: the 2D model extrudes the footprint to the ridge height, so its tip is cast
from the far wall while the gable's is cast from the middle of the house — half the depth short
at a low sun (2.7 m on the bench house). That is the two models' difference, not a roof to fix.

**What the numbers are for.** They are analytic references for the builders: one item, the sun
square to a straight 10 m line (a building: square to or along its ridge), the mesh projected
onto the ground without a shadow map. A builder's number below the listed one is a finding. An
ENGINE render is judged on solid casters (the box gate); thin members — a 0.8 cm wire, a 1.6 cm
bar, about one shadow-map texel — will read lower there through no fault of the builder and are
exempt from a per-pixel IoU. The analysis stays the 2D model's; a 3D reviewer measuring shadow
IoU on these kinds reads this table, not the box gate. The full table is in ADR-059's builders
addendum; `tests/unit/test_scene3d_shadow_agreement.py` holds the builders to it within 0.05
(a reach within 1 cm) and every copy of the table to the script's.

### 8.29.7 Plant v0 — archetype silhouettes from the shared recipes (L1.7)

`core/scene3d/builders/plants.py` is the builder of the plant kinds (`TREE`, `SHRUB`,
`PERENNIAL`). It decides nothing about a plant by itself: the **recipe** comes from the tables the
2D sprites are drawn from, through the rule the 2D renderer uses and from the renderer's own
inputs (§8.22.4), and the **size** from the record.

```
record ──plant_sprite()──▶ SpriteRef ──recipe_for()──▶ recipe {a, pal, leaf_scale, n_out, …}
   │  kind, sprite_species (raw), plant_category             │
   │  height_cm, params["radius_cm"], params["seed"]         ▼
   │                                    _build_shape(form, seed, proportion step)   remembered
   │                                       ARCHETYPE_BUILDERS[a]   form, built TO the size
   │                                       _fit → FitReport        the last millimetre, reported
   │                                       _foliage_colors         colour
   └──────── exact height, exact radius ──▶ scaled ──▶ MeshPart "wood" (vc) · "foliage" (foliage)
```

**What a record gets.** `plant_archetype(record)` answers the same question without building.

| Record | Built |
|---|---|
| a plant kind, a canopy radius, a height | the silhouette of its recipe's archetype |
| a plant kind, a canopy radius, `height_cm is None`, usable `params["estimated_height_cm"]` | the same recipe silhouette at its illustrative category height (#557) |
| a plant kind, a canopy radius, `height_cm is None`, no usable fallback | the placeholder (below) |
| anything else — not a plant kind, or a plant record without a usable radius | `default_builder` (the prism, or nothing) |

**3D builds what 2D draws.** `plant_sprite` hands the shared rule exactly what the 2D renderer
hands it: the kind, `params["sprite_species"]` — the item's OWN species string, as it is, blanks
and all — and `params["plant_category"]`. Not `species_name`: that is the species data's common
name where the item has data, and the two differ (a gallery "pumpkin" carries the data of "Winter
Squash" while its own string is "pumpkin"). A species ASSIGNED from the plant database replaces
the item's string with the name of the species assigned (#445), so the plant is drawn and built
with that species. The 2D rules are therefore 3D's too: "Lemon Balm" takes the lemon tree's
recipe, a string of blanks takes the category's, and the melon is no longer the eggplant's.

**One thing 2D draws and 3D does not: the item's fill colour.** The canvas paints a plant's
sprite and then lays the item's FILL COLOUR over its ink at 60 / 255 opacity
(`core/plant_renderer.render_plant_pixmap`, `tint_color=self.fill_color`). The 3D foliage is the
recipe's palette alone — the parts are not `tinted` — so recolouring a plant reaches the sink as
`update_material` and changes nothing in 3D, and the reference of the hue gate (below) is the
UNTINTED sprite. A plant the owner has recoloured on the plan therefore differs in hue between
the views. Deliberate for v0 and an owner question for the look pass: should a recoloured plant
be tinted in 3D as on the canvas? (The pipeline's own tint is a multiplication of the vertex
colours; the canvas's is a 23.5 % overlay — following it exactly needs that mix, not the flag.)

**The thirteen archetypes** — every `a=` of the tables; `ARCHETYPE_BUILDERS` is pinned to
`plant_art.ARCHETYPES`, and an unknown archetype raises (`SceneSync` contains it: that one item
has no solid and is listed in `failures`).

| Archetype | Silhouette | Recipe keys read | Triangles, measured max |
|---|---|---|---|
| `canopy` | tapered trunk, crown of seven soft lobes (five round it, each reaching the canopy circle; the top one ends at the height), a leaf shell on the lobes | `leaf_scale`, `n_out`, `frilly` | 1,904 |
| `conifer` | short trunk, 3–6 star-rimmed cone tiers by the tree's proportions (each a little higher, shorter or deeper cut per plant), a leader | — | 664 |
| `mound` | six lobes sitting on the ground, leaning to one side, a leaf shell on the lobes | `leaf_scale`, `n_out`, `narrow`, `frilly` | 1,608 |
| `climber` | six lobes on a one-turn helix (a pillar when tall, a mat when wide), a leaf shell on the lobes, tendrils | `leaf_scale`, `n_out`, `frilly` | 1,352 |
| `ground` | nine bumps of uneven height under a dense leaf shell | `leaf_scale`, `n_out`, `narrow`, `frilly` | 1,092 |
| `hedge` | a hand-clipped drum: batter, a shoulder cut higher or lower and squarer or rounder, an uneven top a little out of level, fine leaf shell | `leaf_scale`, `n_out` | 900 |
| `rosette` | three rings of broad folded leaves round a heart that ends at the height, or a fourth ring when `heart=False` | `n_out`, `leaf_scale`, `heart` | 560 |
| `head` | two rings of large leaves — the upper ring's tallest leaf is the height — and a low bud | `frilly` | 400 |
| `grass` | seven tufts of thin arching blades, the tallest as tall as the plant | `n_out`, `leaf_scale` | 1,120 |
| `allium` | one clump: an outer layer of arching blades, an inner upright one | `n_out`, `leaf_scale` | 470 |
| `feathery` | twelve thin arching stems carrying narrow leaflets | `n_out`, `leaf_scale` | 792 |
| `flower` | a stalk, twelve broad leaves up its length, a leaf bud at the height | — | 316 |
| `palm` | ringed slender trunk, arching notched fronds, a spear of young fronds to the height | `n_out` | 356 |

(The largest plant of the tables' recipes over the full sweep — every recipe × every proportion
step × three ids, below — held as ceilings by the sweep test. Only the soles a lobe loses on the
ground depend on the dice; the mound's number is its limit by construction, 6 × 128 + 420 × 2,
and the most a mound in the sweep had was 1,600.)

Every archetype also reads `pal` (through `palette_key`). Nothing else of a recipe is read in v0 —
and nothing else CAN be: a builder is handed only the five keys the shape cache is keyed on
(`_FORM_KEYS`), and reading another raises. No feature key (`plant_art.FEATURE_KEYS` — fruit,
flowers, pods, umbels, bulbs, bloom puffs), not `head` (the curd is a flower head), not
`rib_color`, not the sprite radius `r`. The season gates (`ogp-lush-cinematic` §1) arrive with
Package L3; until then a plant shows nothing a season decides, and a crown is never bare.

**A sprite's tuning numbers move its 3D plant.** `leaf_scale` and `n_out` were tuned for the 2D
sprites; the builders read them (a coarse-leaved recipe gets fewer, larger leaves; a fine-leaved
one more, smaller ones). Retuning a sprite therefore changes the leaf count and size of that
species in 3D — within clipped ranges, so never past the budget.

**The budget** is 2,000 triangles a plant (`TRIANGLE_BUDGET`), per archetype, and holds by
construction: every count is a clipped function of recipe numbers (`_Plan.number`,
`_Plan.shell_leaves`) and never of the plant's size.

**Built TO the data.** A builder works in centimetres at the plant's real height and radius and
keeps to them — it is not allowed to build something else and have it scaled into place:

- *The top.* Every archetype places its highest point AT the height: lobes are topped out
  (`_top_out`: the tallest lobe ends at the height), the canopy's top lobe, the rosette's heart,
  the tallest blade, the tallest leaf of a crown whorl (`crown=True`) and the conifer's leader
  end there. Measured over the full sweep (63,099 plants, below): the builder's own top is
  1.0000 of the height in every one.
- *Leaves stay inside by turning* (`_leaves`). A shell leaf faces the way the lobe's SURFACE
  faces where it sits (the ellipsoid's own normal — on a flat cushion that is up, though the ray
  from the plant's heart leaves nearly level). It grows from at least 4 % of the height above the
  ground. With no headroom it lies down: its plane is turned about its own level line until the
  leaf fits between 1.5 % of the height and the height — a rotation, so it keeps its size (on a
  squash 60 cm tall and 3.6 m wide, 45 cm leaves lie flat). At the canopy's edge it is turned in
  its plane, by quarter turns, to the first heading that keeps it inside the canopy circle. And
  it is never longer than 0.6 canopy radii (a leaf count is fixed by the budget, so leaves grow
  with the surface they cover: on a plant 40 times taller than wide they came out 2.4 radii long).
- *Folded leaves and blades* (`_fronds`, `_ribbons`). A leaf of a rosette is as long as the
  plant is WIDE, and its bow, the ripple of its edges and the fold of its rib are heights — each
  is held to the room the plant has (the bow never lifts the leaf above the height; an edge or
  the rib moves at most half way down to the ground). A blade's arch nods its tip without
  shortening the blade.
- *Volumes on the ground* (`_lobes`). A lobe that reaches below the ground sits on it, and the
  triangles lying wholly within 1 % of the height above the ground — its hidden sole — are not
  built: pressed flat at z = 0 they were up to 6.7 % of a mound's triangles and coplanar with the
  ground texture.

**The fit** (`_fit`) then normalises the last millimetre and RETURNS what that took, as a
`FitReport` (`fit_report(recipe, seed, height, radius)` for a built plant). In order: foliage
still beyond the canopy circle — the corner of a leaf lying along the plant's edge — is pulled
back onto it; the foliage's bounding box is centred on the local origin while wood stays where
it stands (a trunk's foot is the plan position); what dips below the ground is pressed onto it
and a plant above the ground is set down, never lifted; everything is scaled so that the widest
span is the canopy diameter and the top the height.

Each of those steps undoes a little of the one before — centring moves a vertex that was pulled
onto the circle off it again, and the scale carries it further — so none of them says where a
vertex ENDS. **The last step does**: whatever FOLIAGE is further than `REACH_MAX` (1.09) canopy
radii from the axis is put ONTO that circle (`_rein_in`). Nothing follows it. A vertex is moved
along the axis it is not farthest on — its larger coordinate stays — so an extreme of the
bounding box along the widest axis remains one: the widest span is still exactly the canopy
diameter and still centred. (Along the other axis the box can lose a hair when the vertex reined
in was that axis's extreme; `FitReport.reined_share` says when anything was moved.)

**What the plant's reach rests on: foliage is the outermost part.** The last step moves foliage
only. Wood is flat-shaded, and a moved vertex would leave its face with a stored normal that is
no longer its winding normal — a face lit from the wrong side (the third review reined a
hand-made wood triangle beyond the bound and got one). It does not need moving: a trunk is built
within 1.45 × 0.22 = 0.32 canopy radii of the plan position (`_canopy`; a conifer's 0.28, a
palm's 0.24), and the fit's xy scale — 1.11 at most, measured — would have to exceed 3.4 to carry
it to the bound. So "no part of a plant beyond 1.09 canopy radii" is two statements: for the
foliage it holds by construction, for ANY builder output; for the plant it holds because the
trunk builders keep wood inside the foliage — an invariant of theirs, asserted for every recipe
at every proportion step (`WOOD_REACH_MAX` = 0.5 in the tests; 0.32 measured) and visible in
`FitReport.reach`, which measures the wood too. A new archetype with wood has to keep it.

**Two kinds of statement — never mix them.** A truth claim about a plant is either STRUCTURAL
(the code makes it true for any input; tests check the mechanism, also on hand-made and random
input to `_fit` itself) or MEASURED (a number a sample gave; a test may hold a tripwire well clear
of it, and a requirement may quote it only as "measured over …"). The first fix round stated a
sample's maxima as limits twice: "at most 1.092 canopy radii" was 1.1006 for one id in 300,000,
and "z95 at least 0.62" was 0.603 for a rhubarb half as tall as wide.

| Holds for every plant | how | tested by |
|---|---|---|
| the top is the height, the base is the ground | by construction: the fit's scale and set-down | every build; 500 hostile point clouds handed to `_fit` |
| the widest span is the canopy diameter, centred on the plan position | by construction: the fit's centring and scale; the last step keeps a vertex's larger coordinate | the same |
| **no FOLIAGE vertex further than 1.09 canopy radii from the axis** (the gate: 1.10) | by construction: the fit's LAST step | the same; the review's two plants (1.1006 and 1.098 before), validated as meshes |
| no WOOD vertex beyond it either | the trunk builders' invariant: wood is built within 0.32 canopy radii of the axis and is not moved | every recipe × every proportion step: ≤ 0.5; `test_the_last_step_leaves_wood_alone` |
| at most 2,000 triangles | by construction: counts are clipped functions of recipe numbers | hostile recipe numbers |
| the size is exact at every size the builder accepts | by construction: the remembered shape is scaled by (radius, radius, height) | 600 random sizes; the corners of the range |

**The sizes a plant is built at.** `build_silhouette` builds a height and a canopy radius between
`MIN_SIZE_CM` (a micrometre) and `MAX_LENGTH_CM` (10 km, the longest length a record can hold —
§8.29.1) and refuses anything else with a `ValueError`: a NaN, zero, a negative, an infinity,
1e300. Outside that range the arithmetic leaves float32 — before the check a height of 1e300
returned a mesh of NaNs with nothing but two RuntimeWarnings, a radius of 1e-310 raised an
`OverflowError` out of a logarithm, a height of 5e-324 a `MeshError`. Inside it all thirteen
archetypes build an exact, valid, finite plant, the four corners included
(`test_the_edges_of_the_range_build_an_exact_plant`). That is also what the scaled meshes rely
on: `build_silhouette` constructs them directly instead of through `Mesh.from_arrays` (which
would copy the shared colour, uv and index arrays for every plant on every tick), so sealing
and finiteness are established by the remembered arrays having come out of `from_arrays` and by
the bounded factors — stated in one place, `_Arrays.scaled`.

**The sweep.** A shape depends on nothing but (recipe form, id, proportion step) — the cache's
key — so sweeping the steps covers every kind of shape the builders can produce, where a list
of sizes is a sample of them. `scripts/measure_plant_art_3d.py truth --ids 3` builds every
recipe × every proportion step from 1 : 50 to 80 : 1 (171 steps) × three ids, a different id in
every cell: 63,099 plants, 63,099 distinct shapes (round 1's "4,392 builds" were 1,912 shapes on
43 of the steps). The unit test sweeps the same grid with one id per cell (21,033 plants).

| Measured over the 63,099 plants (2026-10-11) | largest | tripwire |
|---|---|---|
| the builder's own top before the fit / the height | 1.0000 in every plant | within 2 % of 1 |
| pressed onto the ground / set down / ground-flat foliage triangles | 0 / 0 / 0 | 0 / 0 / 0 |
| foliage vertices pulled back onto the canopy circle | 2.18 % of a plant's (a mound 66 times taller than wide) | ≤ 4 % |
| … from at most | 1.085 canopy radii | ≤ 1.15 |
| x and y scaled by | 1.108 (a rosette of six leaves: six tips cannot all point along an axis); 1.063 without the rosettes | ≤ 1.16 |
| the foliage moved to its centre by | 0.047 canopy radii (0.056 in the review's own sample) | ≤ 0.09 |
| plants the last step had to rein in | 3 of 63,099 — and 6 of 210,330 with ten ids a cell (`reach --ids 10`) — all rosettes, at most 0.29 % of a plant's vertices | ≤ 2 % of a plant's vertices |
| where a plant ends: the farthest vertex from the axis, over those 210,330 | median 1.017, 99.9th percentile 1.064 canopy radii; the farthest that needed no reining in, 1.086 (a canopy) | — (by construction: 1.09) |

Where the foliage's mass is — the height below which 95 % and 99 % of its surface area lies —
is a MEASURED property too, per archetype (`MASS_REACHES` in
`tests/unit/test_scene3d_plants.py`, each tripwire 0.05 or more under the smallest measured):

| Archetype | smallest z95 / z99 measured | | Archetype | smallest z95 / z99 measured |
|---|---|---|---|---|
| hedge | 0.877 / 0.938 | | head | 0.720 / 0.820 |
| climber | 0.861 / 0.950 | | mound | 0.719 / 0.884 |
| canopy | 0.818 / 0.914 | | grass | 0.711 / 0.813 |
| flower | 0.806 / 0.818 | | allium | 0.699 / 0.823 |
| palm | 0.805 / 0.821 | | conifer | 0.697 / 0.840 |
| feathery | 0.730 / 0.828 | | rosette | 0.605 / 0.719 (the review's rhubarb: 0.603) |
| | | | ground | 0.580 / 0.826 |

They differ by nature: a hedge is a drum, a conifer a cone (95 % of a cone's surface lies below
0.78 of its height), a rosette flat leaves round a small heart — flattest where it is about half
as tall as it is wide. What the tripwire is for: the squash that was built 1.4 to 1.6 times too
tall measured 0.70 / 0.76 where it now measures 0.88 / 0.97. And at least six vertices touch the
ground.

The bounding box alone would not make the plan view honest either: a sparse plant whose few long
leaves point anywhere fits its box and still leaves its canopy circle (1.39 radii, before). So
the elements that draw an outline — a rosette's outer leaves, a palm's fronds, an allium's outer
blades, a grass's longest blades, the lobes round a crown, a mound, a climber or a ground cover —
reach at least `_RIM_REACH` (0.97) of the radius and sit within `_RIM_JITTER` (0.10) of an even
slot round the axis. That is why the last step is rarely needed; the last step is why the bound
does not depend on it.

**The shape cache — a plant that grows is the same shape, scaled.** A shape is built once per
(recipe form, seed, proportion step) and remembered; `build_silhouette` scales it to the plan's
exact height and radius. The proportion — height over canopy radius — is rounded to a whole
power of `PROPORTION_STEP` (1.05) for the BUILD only: the scale is exact, so the top is the
height and the widest span the canopy diameter at every size (600 random sizes from 1 : 25 to
40 : 1, to float32) and no number the plan states can be misstated by the rounding. What the
rounding costs is form: one axis is stretched against the other by at most √1.05 — 2.5 %.
Colours, wind weights and indices are the remembered arrays themselves (read-only, shared by every
mesh scaled from them); only positions are computed, and normals when the stretch is not 1.

- *Pure.* The same record gives the same mesh, cold or warm, bit for bit
  (`test_remembering_changes_nothing`, `test_a_warm_tick_gives_what_a_cold_build_gives`).
- *Bounded in bytes, and it follows the plan.* `SHAPE_CACHE_BYTES` = 256 MB; the NUMBER of
  shapes is not capped. A shape holds 18 … 139 kB (76 kB on average over the 123 recipes at
  mature size), so the cap is about 3,500 average plants or 1,900 of the largest trees; the
  larger bench plan holds 24 MB.
- *No cliff at the cap.* A plain least-recently-used cache falls off one: a scrub asks for every
  growing plant once per tick, in the same order, so the shape it drops is always the one it
  needs next — with room for 1,024 shapes and 1,025 growing plants every plant was rebuilt on
  every tick (the first version: 1.9 s a tick against 0.1 s; 6 s at 2,000). So a new shape gets
  room only from shapes that nobody asked for since this very shape was last asked for: a shape
  never asked for before (a new plan, a plant that grew a step) takes the place of the least
  recently asked ones; a shape that was dropped comes back only in place of shapes not asked for
  since — and if everything held is in use, it is built, handed out and not held. Measured with
  a cap of exactly 1,024 shapes (`scripts/measure_plant_art_3d.py cache --fit 1024`, shapes
  REBUILT per warm tick): 1,024 plants 0; 1,025 plants 1; 1,126 plants 102; 2,048 plants 1,024;
  4,096 plants 3,072 — the overflow, plant for plant. Shapes of a plan no longer shown are the
  least recently asked and give way on the new plan's first tick. Pinned at the boundary by
  `TestShapeCache::test_at_its_cap_the_cache_has_no_cliff` and, through the pipeline, by
  `test_beyond_the_cap_a_tick_rebuilds_the_overflow_not_everything`.
- *What that rule costs — at the cap only; below it nothing is ever dropped.* A shape that was
  dropped comes back in TWO builds: on the tick it is asked for again everything held is still
  "in use", so it is built and not held, and on the next tick it is built once more and takes
  its place. Measured by the third review and pinned with the same numbers: going back to a plan
  whose shapes were dropped costs two cold ticks (64, 64, 0 builds — a new plan costs one); a
  scrub BACKWARD at the cap costs twice the forward one (one plant crossing a step per tick, 40
  ticks: 40 builds forward, 79 back); two plans shown in turn, each filling the cap, rebuild the
  one that came first every time — half of all builds. `clear_shape_cache()` when a plan is
  closed avoids all three for the next plan: it forgets the shapes AND the request log.
- *The request log is outside the cap.* To tell a shape in use from one nobody asks for, the
  cache remembers when each of the last 65,536 keys was asked for. That log is not counted in
  the 256 MB; full, it weighs 15–21 MB on top (14.6 MB measured with one recipe form shared by
  all keys; the third review read 20.8 MB). It is bounded by its count and emptied by
  `clear_shape_cache()`.
- *Threads.* GUI thread only. The cache keeps its bookkeeping under a lock and builds outside
  it, so two threads asking for one new shape at once would both build it, to the same result —
  by reading; it has NOT been tested under threads.
- *Read-only for good.* The arrays of a mesh are shared with the remembered shape and with every
  later mesh scaled from it, so one consumer writing to them would damage every later build of
  that plant. A read-only flag on a view of a writeable array can be switched back on by whoever
  holds it (it could: `colors.setflags(write=True)` succeeded); the memory under a mesh's arrays
  is therefore an immutable `bytes` object (`Mesh.from_arrays`, and the scaled positions), and
  the flag cannot be set on the array or on what it is a view of.
- *What a builder may read.* The cache's key and the recipe a builder is handed are one object
  (`_form`): a builder cannot read a recipe key the key does not hold.

**A growing plant stays the plant it was.** A plant's dice depend on its id alone, so crossing a
proportion step changes its proportions, not its form. Measured as the IoU of the side
silhouettes in the unit box (each normalised to its own height and canopy, so a pure change of
proportion scores 1.0), the same id one step on, every step × four ids
(`scripts/measure_plant_art_3d.py growth`): median 0.991 … 1.000 per archetype, against 0.71 …
0.92 for another id at the same step. How often it happens: the review counted 151 crossings in
a year of daily ticks of the larger bench plan — about two per growing plant; 0.6 per tick over
the season in the scrub below. The smallest single steps: 0.87 for a conifer at the
three proportions where it gains a whorl (the stack of whorls is re-divided), then 0.94
(feathery, flower, palm — single leaves turning to stay inside the canopy circle). The conifer
was the one archetype whose dice did depend on the proportion: it rolled them per whorl BUILT,
so a new whorl moved every later number up the stream and the tree was re-rolled as well (0.86
on the same ids). All six whorls' dice are rolled now, whether the tree has them or not;
`test_a_conifer_that_gains_a_whorl_keeps_the_ones_it_had`. The new whorl itself remains a
visible step — a look question, not a truth one.

**What a date scrub costs** — the numbers L1.3 schedules against. One tick = the plan date moves
by a day and `SceneSync.apply` gets the new records. Measured on the dev box (Windows 11, Python
3.12.9, 2026-10-11) with every core busy — other agents' test runs shared the machine — over 30
ticks from 1 May (`tests/perf/test_scene3d_plants_budget.py`) and over 180 ticks from 1 April
(`scripts/measure_plant_art_3d.py scrub`); medians:

| Plan | Plants that change per tick | Warm tick (the scrub as it happens) | Cold tick (nothing remembered) | A first build of all plants |
|---|---|---|---|---|
| `bench_small` (61 plants) | 31 in May; 25 over the season | 6.5 ms (p95 15 ms); 4.6 ms over the season | 142 ms; 75 ms over the season | 221–236 ms |
| `bench_large` (320 plants) | 80 in May; 74 over the season | 15.2 ms (p95 25 ms); 10.3 ms over the season (p95 17, max 78) | 342 ms; 235 ms over the season | 1,210–1,222 ms |

Warm, 0.5 and 0.9 of the changing plants are REBUILT per tick (their proportion crossed a step;
at most 4 in one tick over the season) and the others scaled — a tick is twenty times cheaper
than without the cache. `snapshot_records` itself took 6 ms and 16 ms a day on the same machine
(§8.29.1's budget, not this one). On a quiet machine every number is lower, by about 3.5 — an
inference, not a reading: the builder before the cache read 329–333 ms for a first build of
`bench_large` on a quiet machine, and this one costs the same per first build to within 12 %
(compared in one process). That is why the test states its budgets in units of a reference
workload timed alongside (§8.10.6), about twice the measured units, and asserts the counts that
cause the time: exactly where they are exact (a first build builds every plant once; a cold tick
builds every plant that changed), and as a bound where they are not (warm, at most 10 % of the
plants that changed are rebuilt — measured 1.6 % and 1.1 %).

What L1.3 should take from this: a warm scrub tick is cheap enough to run synchronously; a first
build of a large plan is not (a second on a busy machine for 320 plants) and wants to be spread
over ticks or moved off the GUI thread, as does the first tick after a plan was opened.

**Colour.** Foliage: `_foliage_colors` mixes the palette's base anchors (`b0`, `b1`) and tip
anchors (`t0`, `t1`) in sRGB, as the 2D gradients do, converts to linear light and multiplies with
a hue-neutral depth shade. Each vertex has an *exposure* (0 deep inside or at the base, 1 at an
outer tip); the tip weight is `FOLIAGE_TIP_WEIGHT[archetype] + 0.9 × (exposure − its weighted
mean)`, the mean taken over the vertices' surface area times their shade^(1/2.4) — roughly how
bright each shows — so that the plant's mean tip tone, as it is seen, is the archetype's constant
whatever its geometry. Those thirteen constants are measured from the rendered sprites — the tip
weight whose mix has the hue of a sprite's foliage, median per archetype: 0.68 for an allium's
light blades, 0.11 for a conifer's dark whorls — and the measurement runs as a test
(`test_the_tip_weights_are_measured_from_the_sprites`). Wood: one colour, `BARK_SRGB` = the mean
of `resources/textures/bark.png` in linear light.

**Conventions for the engine.** Parts are named `wood` (material kind `vc`) and `foliage`
(`foliage`); both cast shadows. In the foliage part `uv.x` is the wind sway weight —
`z / height`, 0 at the ground, 1 at the top — and `uv.y` the sway phase in [0, 1): one base phase
per plant, ± 0.1 per leaf or blade, so a crown moves as one and its leaves flutter. Wood has
`uv = 0`. Foliage normals are bent toward the direction away from the crown's heart (0.6 for
volumes, 0.7 for leaves), so a crown shades as one soft volume. Randomness is uniform numbers from
`numpy.random.Generator(PCG64(seed))` — the bit generator named, so that no numpy release
reshuffles every plant.

**No two alike — as a distribution.** Side silhouettes of two ids of one recipe and size (IoU on
a 32 × 32 grid): over 30 ids per recipe — 53,505 pairs — the most alike pair is 97.5 % alike (two hedge
sections), 99 % of all pairs are less than 95.2 % alike, and two pairs exceed 97 % (both hedges —
0.46 % of the hedge's pairs; `scripts/measure_plant_art_3d.py clones`). A clipped hedge section and a
flat ground cover are the two shapes that repeat by nature; the hedge is cut by hand in five
ways for that reason. The gate (twelve ids a recipe): no pair above 0.985, 95 % of an
archetype's pairs below 0.97, at most 3 % above 0.97.

**Unknown height and the placeholder (#557).** `core/plant_height_estimate.py` is the
canonical illustrative table: tree categories 400 cm, shrub/climber categories 150 cm,
flowers/perennials/ornamental grasses/ground cover 60 cm, vegetables/herbs 50 cm. A known
category wins over the item kind; otherwise TREE/SHRUB/PERENNIAL use 400/150/60 cm. The snapshot
adds estimates only for those plant kinds. Existing explicit, measured/current, growth-projected and species
heights retain their precedence in `effective_height_cm` and suppress the fallback.

The snapshot retains `height_cm=None` and adds `params["estimated_height_cm"]` transiently.
The existing sprite recipe, palette and builder supply the plant form at that estimate; the
info card marks its height as estimated. This changes decorative 3D geometry and its shadows
only: analytical 2D shadows and Hours of Sun still see an unknown height and exclude that
caster. Merely viewing 3D writes no species/instance height, saved value or undo command.
Category/gallery/tool plants and sparse online species therefore show their plant form;
a known species such as bundled Oak retains its recorded 4,000 cm height.

`placeholder_parts(radius)` remains the defensive fallback for a height-less record without a
usable category estimate: one part named `placeholder`, a smooth spherical cap over the canopy
circle (48 sides), `min(0.12 × diameter, 25 cm)` high, in the neutral 2D white × 0.5 linear
(sRGB 170 / 167 / 158), material `vc`, `casts_shadow=False`. It reads only the radius.
A height outside the record contract remains an `out_of_range` snapshot refusal, not an
estimate or marker. The former universal no-guessed-height marker policy is superseded by
issue #557; estimates remain explicitly non-authoritative.

Regression coverage: `tests/integration/test_plant_package_558_559_560_552_557.py` and
`tests/integration/test_scene3d_plants.py`; the independent 3D evidence uses real assignment,
the production registry and engine, representative categories in two moods, and a matching
base-commit board. Exact mesh dimensions are judged against the resolved known height or
separate estimate and the existing canopy, never against altered garden data.

**Adding an archetype** (a new `a=` in the tables): write `_name(p: _Plan) -> (wood | None,
foliage)` from the primitives (`_lobes`, `_leaves`, `_ribbons`, `_fronds`, `_revolve`); place its
highest point at `p.height` and its outline on the canopy circle (a regular rim); hand leaves
the plant's radius and height so they stay inside; clip every count that a recipe number feeds;
add it to `ARCHETYPE_BUILDERS` and its measured tip weight to `FOLIAGE_TIP_WEIGHT`, and its
measured mass quantiles to the test's `MASS_REACHES`; roll every die whether or not the plant's
proportions use it (a count that depends on the proportion must not move the stream). The gates
then run by themselves — `tests/unit/test_scene3d_plants.py` builds every recipe of both tables
at every proportion step and at six real sizes — and `scripts/mutation_check_plant_art.py` says
whether they would notice a broken rule.

### 8.29.8 Selection, the info card and walk mode (L1.8)

What connects the canvas selection with the 3D view, and how the garden is walked. The decisions
and every measurement are the **ADR-060 addendum "selection, info card and walk (L1.8)"**; how it
is tested is §8.10.12; what went wrong on the way is PF-E3D-08. The modules are §5.15.

**One selection.** There is one: the canvas scene's. The 3D view holds none.

```
a click in the 3D window                         the canvas
  OrbitInput._release ── host.pick(x, y) ──▶  selection_bridge.apply_click ──▶ setSelected / clearSelection
  (press + release within 4 px, 0.4 s)        (the canvas's rules)                    │
                                                                         scene.selectionChanged
  the ring in the engine  ◀── SceneSync ◀── Scene3DController.set_selection ◀─────────┤
  (one Model, one geometry)   (apply / send_selection)                    the info card ◀┘
```

> **Rule: a selection never touches a model.** Selection is in none of a record's signatures. A
> selection change makes zero `add` / `remove` / `replace_geometry` / `update_transform` /
> `update_material` calls, creates no engine object and destroys none. It is ONE sink call —
> `set_selection(Selection)` — and one re-load of the ring's geometry.

**The canvas's rules are the rules** (`ui/view3d/selection_bridge.py`, measured with real clicks —
the table is in the ADR): a plain click selects one item; Ctrl and Shift toggle; a click on the
ground or the sky clears; an item on a locked layer is transparent — the click selects what lies
behind it along the ray (`PickHit.behind`), or clears; a member of a group selects the outermost
group, and the ring runs round every member.

> **Rule: selecting by id is ONE path for the whole app** — `ui/canvas/select_by_id.py`
> (`item_with_id`, `click_target`, `is_selectable`, `replace_selection`, `select_by_ids`). The
> Diagnostics, Canopy and Guilds panels, the plant search, the 3D "Not Shown in 3D" list
> (`Workspace.select_item`) and a click in 3D (`selection_bridge`, which adds the ray's rule) go
> through it. A new list that names objects calls `select_by_ids` and writes no resolver, group
> rule or locked-layer rule of its own; a structure scan in `test_view3d_selection_workspace.py`
> refuses a `clearSelection` in the panels or the 3D package outside it.

> **Rule: a replaced document reads no selection.** `CanvasScene.document_replaced` comes while
> the OLD items are still in the scene and still selected; the workspace's slot empties the
> ring's wish (`set_selection(())`) instead of reading the scene. A selection made in the new
> document arrives as `selectionChanged`, like any other.

> **Rule: a selection change reads nothing of the plan.** The selection path is
> `Scene3DController.set_selection` → `SceneSync.send_selection`: no snapshot, no builder, one
> sink call — and, since the workspace's plan revision, none with the canvas visible either: a
> repaint goes to the quiet-time net, which finds nothing (measured: 0 snapshots for 4
> selection changes in Split, `unannounced_changes` 0).

> **Rule: `host.pick` is called in one place.** `OrbitInput._release`, once per click. It takes a
> frame from the live view (ADR-060 decision 17): never on a mouse move, a timer or a resize. The
> scan test allows exactly this call, by module, function and name. `HostStateError` means "not
> now": the click does nothing and says nothing.

**The ring** is the outline of the item's footprint — every outer ring, every hole — at its
standing base plus 1 cm, so a plant on a raised bed is ringed at the bed's soil. It is a band of
3 px ON SCREEN (a vertex shader moves each outline point outward by band widths), in the canvas's
selection blue, unlit, casting no shadow, not pickable, and drawn in front of everything: the
built world is thicker than the plan's strokes, and a depth-tested ring of a wall lies inside
its masonry. `core/scene3d/selection.py` builds the mesh; the engine holds one static Model and
one geometry that is re-loaded in place.

To change what is ringed, change `selection_of` (the mesh) — not the shader, which knows only
"outward" and "up". To change the look (width, colour, depth), the three numbers are in
`selection.py` and `Garden.qml` and are pinned against each other by
`tests/unit/test_quick3d_selection_ring.py`.

**The info card** (`ui/view3d/info_card.py`) says what the 3D view shows of the one selected
item: its name and kind, a plant's species, its height and canopy diameter at the plan date or
a built item's height and footprint, the bed it stands on — and, when it has no model, why.

> **Rule: the card reads the record.** Every number on it comes from the item's APPLIED record
> (`SceneSync.records`): the numbers the model was built from. No second computation — a card
> that resolved a height by itself could disagree with the solid beside it.

> **Rule: nothing that comes and goes may resize the 3D view.** The card lives in
> `View3DCardSlot`, a strip of one constant height that is there card or no card; walk mode's
> eye height is a menu on the Walk button, which takes no room. A view that changes its size re-scales its picture
> under the pointer (the next click misses), gets a new swapchain, and answers no click while it
> is between two sizes. `test_no_selection_change_and_no_walk_resizes_the_3d_view` pins the
> engine widget's geometry through every state.

Plan text on the card is untrusted (§8.11): every label is `Qt.TextFormat.PlainText`, every
plan-derived string goes through `clip_line`, no tooltip carries plan text, and no label asks
for the width of its text.

**Walk mode.** The rules are Qt-free in `core/scene3d/walk.py`; `ui/view3d/walk_mode.py` is an
event filter that holds one `WalkState` and feeds it keys and time.

| | |
|---|---|
| The walker | a cylinder of radius 22.5 cm; eye at 165 / 150 / 110 cm; 140 cm/s, twice that with Shift |
| What blocks | built-world records and greenhouses whose top is more than 25 cm up: their footprint (outer minus holes) and the plan-view edges of their SHOWN mesh between 25 and 200 cm |
| What does not | plants other than hedges, furniture, flat items, anything above 200 cm (eaves) |
| Motion | ticks of 1/120 s whatever the frame rate; move, then be pushed out along the normal (sliding); 8 pushes at most, else the tick is refused |
| The edge | the plan rectangle |
| The camera | field of view 60°, near plane 5 cm — its farthest corner is 6.9 cm from the eye, under the walker's radius |
| Keys | W A S D / arrows walk, Shift runs, a drag looks, Escape leaves; a click still selects; every other key, and every key with Ctrl or Alt, is the app's |
| The keyboard | "Walk" gives the 3D view the keyboard (`Quick3DHost.focus`) and leaving gives it back (while the view still has it) |

> **Rule: while walking, the walk keys belong to the walker** (`walk_mode.WALKER_KEYS`, stated
> once). They are claimed at `ShortcutOverride` — the event Qt sends to the view's window
> before it looks for a shortcut — unless Ctrl, Alt or Meta is held; every other key is passed
> on. A filter that takes only `KeyPress` loses a key to any shortcut of the main window: the
> 3D view is embedded, so the main window stays the active window and its shortcuts are live
> (S was Snap to Grid). A new key for walk mode goes into `WALKER_KEYS` and nowhere else.

> **Rule: the walker collides with what is drawn.** `build_world(records, width, depth,
> parts_of=…)` is handed the registry's own builder. A new builder that makes a solid wider than
> its footprint blocks the walker with no line of walk code; a new KIND that should block is
> added to `WALK_SOLID_KINDS` (it is `BUILT_WORLD_KINDS` plus the greenhouse).

> **Rule: walk mode borrows the camera and gives it back.** `Workspace._apply_camera` is the one
> place that tells the host where the camera is; while walking it asks `WalkMode.camera()`. Walk
> mode never writes the orbit camera, the plan or the undo stack: leaving shows the pose the
> user had, to the last digit.

The walker starts where the orbit camera looks — on the nearest free ground if that spot is
inside a solid — facing the way it looks. A hidden pane lets go of every key and keeps the
walker; an edit while walking rebuilds its world, and the walker is moved to free ground if
something was put where it stands. A new document, "Reset 3D View" and Escape leave walk mode.

Not in v0: plants as obstacles, stairs and slopes (the ground is flat), doors, pointer capture,
a hover highlight, a box selection in 3D.

### 8.29.9 The default, what the old view promised, and its removal (L1.9 / L1.10)

The workspace is the 3D view of every main window. The decision and every measurement are the
**ADR-060 addendum "the default and the removal"**; how it is tested is §8.10.13; what went
wrong on the way is PF-E3D-09.

**One code path.** There is no switch: `app/application.py::_setup_central_widget` builds the
`Workspace` around the canvas view, always. Starting the app imports `ui/view3d/workspace.py`
and what it needs (no Qt Quick, no QML — the engine is loaded on the first switch to 3D or
Split, `Workspace.engine_factory`), and the app starts in Plan mode in every session (the mode
is not saved). View → "3D View" — the direct workspace action, with its icon —
switches Plan to Split (`_on_show_3d_view`); in 3D or Split it does nothing. The safety net is
the start marker and compatibility mode (`ui/view3d/init_guard.py`, FR-3D-WS-07), not a flag:

| What goes wrong | What the user gets |
|---|---|
| the engine cannot be imported (a missing or mismatched Qt Quick 3D DLL in a frozen build — the #277 class) | the 3D pane says so and offers "Try Again"; the rest of the app runs (`Workspace._start_engine` catches it) |
| the graphics device cannot be created | "3D is unavailable on this graphics device", and compatibility mode for the next start |
| the driver kills the process while 3D starts | the marker stays; the next start of 3D is in compatibility mode and says so |
| it dies in compatibility mode too | 3D is switched off, with the way back on screen |
| it fails AFTER the first frame | the app starts in Plan mode next time; "Use Compatibility Mode Next Time" is in the 3D strip |

> **Rule: Plan mode costs nothing of 3D.** No engine module is loaded before the user asks
> for 3D (the import scan, G1 in a fresh process; the render twin in
> `test_view3d_default_render.py`). A change that imports Qt Quick, QML or `quick3d` at
> start-up — or makes the workspace build its pane before it is asked — fails both.

**Date playback is throttled** (#531). Each date regrows the dated plants, and every Model
Qt Quick 3D destroys leaves 15 to 20 kB behind (ADR-060 decision 16): an arrow key held in the
date field (about 30 steps a second) regrew all of them on every step. `Scene3DController._on_date_changed` regrows at once if
`DATE_REGROW_MIN_MS` (500) has passed since the last regrowth for a date, and otherwise books ONE
trailing regrowth for the end of the interval, which runs only if the clock's date is not the
one the last records pass read. The light follows every step (a light-only pass, no snapshot).
The trailing check stamps the throttle only when it marks records dirty (#542).
A no-op retains the prior timestamp. Controller integration tests use an explicit
module-scoped clock at three origins, consume a manually fired timer before its
slot, and assert admission through the real date signal plus the resulting snapshot
(PF-TST-25); pytest-qt waits and pipeline performance measurements keep real time.
Hidden, a date is a flag (no timer). Measured below: 1.5 to 1.6 regrowth passes a second while
the date steps.

> **Rule: a timer that books a pass is part of "idle".** `Scene3DController.idle` and the
> tests' `pipeline_settled` wait for the posted pass, the tick timer AND the date timer.

**The wind's clock is unchanged.** FU-L14-2 (memory growing while the wind runs) did not
reproduce on 2026-10-19: six alternating soaks of 4–5 minutes, three with the `FrameAnimation`
and three with a C++ `NumberAnimation` (no JavaScript per frame), read 0.46–2.03 MB a minute
from the first sample to the last, second-half slopes 0.0–1.51 — the two clocks inside each
other's spread, dedicated GPU memory flat. The clock change was reverted. But a seventh run the same day (the final render tier on the L1.9/L1.10 tree) read a second-half slope of 2.637
MB a minute against the registered bound of 2.0: the growth is intermittent, not gone. The gate
is a non-strict `xfail` citing #534 until the growth is fixed.

#### FR-SUN-06 / 07 / 08, clause by clause

Each row is a test of the NEW view, or a stated difference the owner sees.

| What the old view promised | The new view | Evidence |
|---|---|---|
| View → "3D View…" opens a separate window | **differs:** the same entry shows Split in the main window; 3D and Split are modes (Alt+2 / Alt+3) — no second window, so no window to lose behind the main one | `test_view3d_workspace.py::test_the_3d_view_action_shows_the_3d_pane_and_reaches_no_window` |
| every visible object with a footprint, extruded at its effective height | the same objects at the same height — the 2D resolver's (FR-SUN-02) | `test_scene3d_snapshot.py::TestRecordContent::test_height_is_the_2d_resolver_s`, `test_scene3d_built_world.py::test_kinds_builders_heights_and_bases` |
| … as prisms in their fill colour | **differs:** buildings, fences, walls, beds, containers and hedges as built shapes (L1.6); plants as their sprite's archetype (L1.7); the other kinds as prisms in their fill colour | `test_scene3d_built_world.py`, `test_scene3d_plants.py::test_every_gallery_plant_is_built_as_the_sprite_the_canvas_draws`, `test_scene3d_snapshot.py::TestRecordContent::test_material` |
| the same footprints as the 2D shadow overlay | the same footprints (`ui/canvas/footprints`, one caster walk); a prism's shadow is the 2D model's; other shapes differ by the measured amounts of FR-SUN-11 | `test_scene3d_shadow_agreement.py::test_a_prism_casts_the_shadow_the_2d_model_casts`, `::test_prisms_pots_and_post_fences_end_where_the_2d_shadow_ends` |
| height-less objects (lawns, paths, in-ground beds) as thin ground decals | **differs:** no decal — they are painted onto the 3D ground as the plan paints them: the same textures and tints, pens, path and fence styles and sprites, north up, in the plan's stacking order; under a solid the ground shows what was drawn there (FR-3D-GROUND-01 / 02, L1.5) | `test_scene3d_ground_bake.py::TestParityPerPattern`, `::TestParityOfPaths`, `::TestParityOfSprites`, `::TestWhatIsPainted::test_a_solid_is_not_painted_and_the_lawn_runs_on_under_it`, `test_scene3d_ground_wiring.py::test_the_workspace_bakes_the_ground_of_what_is_drawn`, render `test_scene3d_ground_render.py::test_a_real_plan_shows_its_baked_ground_in_the_engine` |
| a ground plane the size of the canvas | the plan ground is the canvas rectangle, baked from the plan, in a meadow; it follows a resized canvas | `test_view3d_sync_controller.py::test_a_resized_canvas_moves_the_ground` |
| an orbit camera (drag rotates, wheel zooms), framed on the plan | **differs in the buttons:** right drag orbits, left drag pans, the wheel zooms, both buttons zoom (Qt 3D's own `QOrbitCameraController` mapping); keys too; framed on the first open and on a new plan, never by an edit | `tests/ui/test_view3d_orbit_input.py`, `test_view3d_workspace_widget.py::test_no_edit_moves_the_camera_and_a_document_change_frames_once` |
| a directional sun from the sim date / time and the location | the same, the one sim clock; shadows from a shadow map | `test_view3d_sync_controller.py::test_a_time_change_moves_the_light_and_takes_no_snapshot`, `tests/ui/test_quick3d_host.py::TestKeyLight` |
| no location → a pleasant southern midday (50°, 180°) | the same sun (`NO_LOCATION_SUN`) | `test_view3d_sync_controller.py::test_without_a_location_the_documented_default_sun_is_sent_once` |
| sun below the horizon → a dim bluish overhead light | **differs:** the light fades through civil twilight (to −6°) into a moonlit night (moon from azimuth 165°, elevation 38°) — darker than noon by more than four times | `test_scene3d_look.py::test_night_begins_at_the_end_of_civil_twilight`, render `test_view3d_looks_render.py::test_night_is_under_a_quarter_of_noons_luminance_on_the_same_shot` |
| a snapshot: rebuilt on open, by Refresh, on a date change — NOT live | **differs:** live — every edit within 50 ms (p95) on the small bench plan; no Refresh button | `test_view3d_workspace.py::test_the_workflow_plan_split_edit_pause_clock_new_open_close`, render `test_view3d_workspace_render.py::test_an_edit_is_in_a_finished_frame_within_50_ms_on_the_small_plan` |
| lighting only, no shadow maps | **differs:** shadow maps whose ground coverage matches the 2D shadow (IoU ≥ 0.85 at 15° / 35° / 60°) | render `test_view3d_looks_render.py::test_the_shadow_of_a_box_matches_the_2d_shadow_in_perspective_with_cascades` |
| read-only (no 3D editing) | the same; a click selects (one selection with the plan) and is no undo step | `test_view3d_selection_workspace.py::test_a_plain_click_selects_only_that_item_on_the_canvas` |
| nothing 3D in the `.ogp` | the same: camera, mode, walk and selection leave the saved file as it was | `test_view3d_workspace.py::test_using_3d_writes_nothing_into_the_plan_file` |
| closing the window | **differs:** there is no window; Plan mode hides 3D and pauses it (no work while hidden), and closing the app with 3D visible, hidden or never opened is clean | `test_view3d_workspace_widget.py::test_the_pipeline_is_paused_in_plan_mode_and_catches_up_once`, render `test_view3d_workspace_render.py::test_the_app_closes_clean_with_3d_visible` (and `…hidden_again`, `…never_opened`) |
| Walk at a fixed 165 cm | 165 cm by default; **differs:** 150 and 110 cm on offer | `test_view3d_selection_workspace.py::test_the_eye_height_presets_move_the_eye_and_are_kept`, `test_scene3d_walk.py::test_the_eye_is_at_eye_height_and_looks_where_the_walker_looks` |
| W A S D / arrow keys move | the same; Shift runs | `test_view3d_selection_workspace.py::test_the_walkers_keys_beat_the_windows_shortcuts_and_no_other_key_does`, `tests/ui/test_view3d_walk_mode.py` |
| holding the left button looks around | **differs:** a drag looks around (a click still selects) | `test_view3d_selection_workspace.py::test_a_flick_that_turns_the_walkers_view_is_no_click`, `::test_a_click_still_selects_while_walking` |
| Esc returns to orbit, the orbit camera restored exactly | the same (Escape or the Walk button) | `test_view3d_selection_workspace.py::test_enter_walk_and_leave_restores_the_orbit_pose_exactly` |
| clamped to the plan + 150 cm, cannot leave eye height | **differs:** the plan's edge is the edge (no margin); the eye height is held | `test_scene3d_walk.py::test_the_canvas_bounds_are_the_worlds_edge` |
| no collision (passes through objects) | **differs:** a body 45 cm wide; walls, fences, buildings, hedges, raised beds and containers stop it; plants and furniture do not | `test_scene3d_walk.py`, `test_view3d_walk_bench.py`, `test_view3d_selection_walk.py::test_a_twenty_centimetre_gap_does_not_let_the_walker_through` |
| the sun stays live while walking | the same | `test_view3d_workspace.py::test_using_3d_writes_nothing_into_the_plan_file` (a time change while walking reaches the engine) |
| measured current size drives the 3D extrusion | the same: the record's height and canopy are the 2D resolver's (FR-3D-PLANT-02) | `test_scene3d_plants.py::test_a_planted_garden_is_built_to_the_plan_and_grows_with_the_date` |
| 3D needs Refresh after a measurement edit | **differs:** follows the edit at once | `test_view3d_plan_revision.py` (the Plant Details fields nudge the plan revision) |
| growth from the planting date, one model, one plan date | the same; dated plants regrow on a date change (at most twice a second while the date keeps changing) | `test_view3d_sync_controller.py::test_a_date_change_regrows_the_dated_plants_and_nothing_else`, `::test_a_date_held_down_regrows_at_once_and_once_more_on_its_last_day` |
| an explicit height override wins; an unmeasured plant stays mature at every date | the same (the 2D resolver) | `test_scene3d_snapshot.py::TestRecordContent::test_height_is_the_2d_resolver_s`, `TestDiffMatrix::test_the_date_changes_nothing_but_dated_plants` |

FR-SUN-06 / 07 / 08 are rewritten to say what the product does now and point to FR-33.

#### What the default costs (measured, RTX 4070 / Direct3D 11 and WARP, 2026-10-19)

Through the product's own `main()` in a child process (`workspace_default_measure.py`; the
old window through its own slot on the L1.9 tree, before L1.10 deleted it). Window maximised on
a 5120 × 1440 desktop: the 3D pane in Split is 2334 × 1105 px. The new view at the product's
defaults (quality Automatic, the wind running) except where the row says "still" (the workspace
gate's still look: High, reduced motion). Private bytes swing by 100 MB and more within a run
(L1.8): every memory figure is the median of three readings 200 ms apart, and dedicated GPU
memory (DXGI, this process) is the steadier one. "Cold" = the first run after the code changed;
the later runs had the OS's file cache and the GPU driver's own shader cache (Qt's caches are in
each run's throw-away profile).

| Row | Small bench plan (98 records) | Large bench plan (424) | Old Qt 3D window (small / large) |
|---|---|---|---|
| start-up to the first turn of the event loop, no plan, 3D never opened (median of 5) | 2.20 s (2.12–2.24) — the tree before the flip: 2.19 s (2.04–2.24) | — | (the same start: the old window was never loaded at start-up either) |
| engine modules loaded before 3D is asked for | 0 | 0 | 0 Qt 3D modules |
| first 3D click → first presented frame | 1.10 / 1.12 s (cold 1.88) | 1.81 / 1.86 s (cold 1.77) | 0.57 / 0.58 s; 0.74 s (on screen) |
| first 3D click → first finished readback | 2.29 / 2.33 s (cold 4.49) | 3.25 / 3.31 s (cold 3.30) | — (no readback; opening is synchronous: 0.55 / 0.66 s) |
| edit → finished frame, 120 edits (still) | p50 24.1, **p95 45.9**, max 83.9 ms | p50 62.1, p95 180, max 327 ms | — (no live sync: Refresh rebuilds the scene in 32 / 196 ms) |
| snapshot per pass, 100 edits | p50 3.2, p95 3.6 ms (cold 6.7 / 9.4) | p50 13.1, p95 14.6–15.3 ms | — |
| committed memory before 3D → after the first frame | 880 → 1,428–1,677 MB | 901–909 → 1,849–1,858 MB | 877 → 1,203–1,205 MB; 905 → 1,601 MB |
| dedicated GPU memory after the first frame | 312 MB | 312 MB | 45 / 47 MB |
| after 100 more edits (committed / GPU) | 1,415–1,443 / 312–329 MB | 1,682–1,695 / 329 MB | 1,176–1,179 / 45 MB; 1,644 / 50 MB (no Refresh) |
| on WARP (the whole process on the software adapter): first frame / first readback; edit → frame (still) | 0.96 s / 11.6 s (a sky probe: see below); p50 243, p95 429 ms; snapshot p50 5.2 ms; committed 871–881 → 1,685–1,693 MB | — | not measured: Qt 3D ignores Qt Quick's software switch (it rendered on the GPU) |
| date playback, 60 s, a step every 33 ms, 20 dated trees: regrowth passes / Models replaced | the interval (500 ms): 90 / 1,800 and 97 / 1,940 (349 and 501 steps); none (before L1.9): 312 / 6,240 and 452 / 9,040 — every step | — | — |

**Frame cost per preset** (`scripts/render_beauty_board.py --size 1280x720 --presets
low,medium,high,ultra --shots golden_hour --fps-seconds 5`, the wind running; L1.4's table
re-run on the L1.9 tree). The display was asleep: a vblank-paced run presents no frame there, so
the GPU rows are timer-paced (`QT_D3D_NO_VBLANK_THREAD=1`, capped near 60). "rb" is the median
readback of a new frame — an upper bound of a frame's cost on the GPU.

| Plan, device | low | medium | high | ultra |
|---|---|---|---|---|
| small, RTX 4070 (paced) | 59.2 fps, rb 7.9 ms | 57.4, rb 9.1 | 58.8, rb 8.9 | 59.4, rb 14.2 |
| large, RTX 4070 (paced) | 59.4, rb 13.9 | 58.8, rb 12.6 | 59.2, rb 14.8 | 59.4, rb 20.7 |
| small, WARP (vblank / paced) | 23.2 / 19.7 | 13.8 / 5.7 | 9.8 / 4.1 | 4.8 / 1.9 |
| large, WARP (vblank / paced) | 6.0 / 12.8 | 7.7 / 8.3 | 2.5 / 5.8 | 1.2 / 3.1 |

L1.4 measured the same shot with the display awake: RTX 4070 small 57–60 fps at every preset,
large 60 / 51–53 / 45–54 / 36–41; WARP small 22.6 / 14.2 / 9.6 / 4.7, large 10.5 / 7.8 / 5.6 /
2.9. Today's WARP rows scatter by a factor of two between two runs of the same tree (another
process shared the CPU) — the order of the presets holds, the numbers do not repeat. An
integrated GPU is unmeasured.

What the table says, honestly:

- **The new view costs more than the old one did.** It reaches its first frame about twice as
  late (1.1 against 0.6 s on the small plan), keeps 550–800 MB more committed memory and 312
  against 45 MB on the graphics card. It draws a sky with a light probe, two shadow cascades,
  4× multisampling, ambient occlusion, glow and a wind; the old one drew lit prisms. The first
  frame is still inside the 10 s bound of `test_view3d_default_render.py`; nothing else had a
  bound before this story — these are the numbers the owner accepted at the L1 pull request
  (2026-10-19, no lighter default preset; ADR-060 addendum D5).
- **Edit → frame on the small plan is 45.9 ms at p95 in a 2334 × 1105 pane** — under ADR-060's
  50 ms bound, with less room than L1.3 measured (19.7 ms in a 574 × 734 pane, 29.2 maximised);
  L1.4's look made a frame dearer. The large plan has no bound (180 ms p95).
- **A machine whose ONLY adapter is WARP** (no GPU at all, not the workspace's compatibility
  mode) gets the hardware look on the software rasteriser: a sky light probe (the first readback
  11.6 s) and the wind (L1.4 measured the wind on WARP at 1,351 % of one core) — a follow-up
  issue, not fixed here: the look's software rule follows compatibility mode, not the adapter.
- **Date playback**: the interval holds — 1.5 to 1.6 regrowth passes a second however fast the
  date steps; without it every step regrew all 20 trees. Committed and GPU memory could not
  resolve a slope in a minute (private bytes swung by ±100 MB, GPU memory by ±80 MB around
  releases). By the residual L1.3 measured (15–20 kB per destroyed Model), a held key costs at
  most 2 × 20 × 60 = 2,400 Models a minute — 36 to 48 MB a minute — against the 0.7 GB a minute
  estimated for a key that regrows on every one of its 30 steps a second.

#### With the ground (L1.5 joined; measured on the merged tree, 2026-10-19)

L1.5's ground bake joined after the tables above were measured. The same scenarios on the merged
tree (RTX 4070 unless the row says WARP; the small plan one cold and two warm runs, the large one
cold and one warm; dedicated GPU memory is the steady reading, committed memory the median of
three):

| Row | Small bench plan | Large bench plan | Against the tables above |
|---|---|---|---|
| start-up, 3D never opened (3 runs) | 2.12–2.14 s, 0 engine modules | — | unchanged |
| first 3D click → first presented frame | 1.11–1.22 s | 1.91–2.15 s | small unchanged, large +0.1–0.3 s |
| first 3D click → first finished readback | 2.68–2.96 s | 4.21–4.33 s | +0.4–0.6 s and +1.0 s: the ground's first passes |
| dedicated GPU memory after the first frame | 332.5 MB | 427–429 MB | +20 MB and +115 MB: the ground's tile textures |
| committed memory before 3D → after the first frame | 880 → 1,724–1,743 MB | 903–904 → 2,180 MB | higher by ~50–300 and ~320 MB (private bytes swing) |
| after 100 more edits (committed / GPU) | 1,490–1,495 / 332.6 MB | 1,913–1,914 / 408 MB | — |
| snapshot per pass, p50 / p95 | 3.5 / 4.0–6.3 ms | 14.6 / 21.8–24.8 ms | — |
| edit → finished frame (still), 120 edits | p50 22.2, **p95 41.5**, max 64.9 ms | p50 54.7, p95 103, max 235 ms | within run-to-run spread (45.9 and 180 above) |
| WARP, small: first frame / first readback; edit → frame | 1.05 s / 12.8 s; p50 370, p95 427 ms | — | the readback +1.2 s |
| date playback, 60 s, a step every 33 ms, 20 dated trees: regrowth passes / cache releases / dedicated GPU memory | the interval: 101 and 104 passes, 5 and 6 releases, **+41 and +63 MB a minute**; none: 339 and 219 passes, 13 and 9 releases, +112 and +76 MB a minute | — | without the ground (above) no GPU trend could be resolved (−18.6 to +2.7 MB a minute) |

- **#532, measured on the default's own path.** Each cache release now keeps 8.2 to 10.5 MB of
  dedicated GPU memory (the minute's GPU slope over its releases, four runs) — about half of
  bench_small's ground, what L1.5 measured in G7 (+9.3 to +11.4 MB per rebuild). Date playback
  releases about once per 512 retired Models: the interval cut a held key's releases from 9–13 to
  5–6 a minute, so a minute of held date key keeps 41–63 MB on this plan instead of 76–112; on the
  largest ground (~42 MB per release) that would be about 210–250 MB a minute. The interval
  cannot make one release leak less. The owner shipped the default with #532 open (decided at
  the L1 pull request on 2026-10-19; the ADR-060 addendum, D5).
- **The ground's own cost** is GPU memory for its tiles (+20 MB on the small plan, +115 MB on
  the large) and up to a second before the first frame is complete; it changes nothing at
  start-up and nothing measurable per edit.

#### After the removal (L1.10)

The workspace is the only 3D code. What the old view needed and the host does not is the scar
table of the ADR-060 addendum; what left the bundle is ADR-048's closing addendum. Three rules
remain for whoever touches this area:

- **No Qt 3D anywhere but in history.** `tests/unit/test_no_qt3d_left.py` (§8.10.13) fails on a
  Qt 3D module or wheel name in code, the spec, the workflows, `quality/`, the manifest and the
  locks, and on any document not on its history list.
- **The spike's values are data now.** Each spike module has a production successor (docs/05
  §5.8); what the drift guards compared with is `tests/data/l0_spike_reference.json`. A
  production value that leaves it is a deliberate change: update the file only together with
  the ADR or skill row that records why.
- **`--selftest` is three blocks** — the Agent API server, the A1 checks, and the Qt Quick 3D
  render (with L1.5's baked ground and the selection ring). The render block is what now
  catches #277's class: a missing or mismatched Qt Quick 3D library fails the frame in the real
  artifact, as the Qt 3D import used to.


### 8.29.10 Analyze in 3D — the 2D analysis on the ground, sun path, card v1, growth jump, Cutaway (L2)

Decisions: ADR-063 (and its review addendum). Requirements: FR-3D-ANALYZE-01 … 08.
Lessons: PF-L3D-06, PF-L3D-07, PF-L3D-08.

**The rule: the 2D analysis is the truth, and the 3D view lays it on its ground.** The
engine's shadow maps stay illustrative (ADR-048, criterion 8's scope note). Nothing
of L2 computes a shadow or a sun hour a second time:

```
SunShadowController ──shadows_changed / drape_polygons()──┐
SunHeatmapController ──computed(SunHoursMap) / result() / exposure_changed──┤
LiveSunMap ──enabled_changed / set_enabled / is_current()──┤
SimClock ──instant_changed / date_changed─────────────────┤
                                                          ▼
                      ui/view3d/analysis_controller.py  (engine-free; one per engine)
                        core/scene3d/drape.py      shadow_drape · sun_hours_drape
                        core/scene3d/sun_path.py   day_arc · dome_point · compass_mesh · probe_pin_mesh
                        core/scene3d/xray.py       xray_scene · occluders (pick_oracle.cast_segment)
                                                          │ engine_buffers (the one frame mapping)
                                                          ▼
                      Quick3DHost.set_overlay("shade" | "drape" | "lines") · set_roofs_hidden · set_faded_items
                                                          │
                      Garden.qml: shadeOverlay (multiplies) · drapeOverlay · linesOverlay
                                  (one Model each, for the scene's life)
                                  every part Model: fade → a screen door (screen.frag)
                                  roof parts: cut → a screen door with nothing left; walls: no culling
```

**Modules.**

| Module | Role |
|---|---|
| `core/scene3d/drape.py` | The shadow drape (the overlay's polygons cut at the plan, triangulated; a 5 cm raster for a region the triangulator refuses) and the hours-of-sun drape (one vertex per cell centre plus a clamped edge, the canvas's ramp in linear light, block-averaged beyond 262,144 vertices). Scene frame, 1.5 cm above the ground. |
| `core/scene3d/sun_path.py` | One LOCAL day of the sun per arc (the clock's zone), cut at the horizon, solar noon found and inserted; `dome_point` — the one mapping to the dome; tubes, hour beads, the sun ball; the compass rose (ring, ticks, north arrow, letters from outlines); the probe pin. |
| `core/scene3d/xray.py` | `ROOF_KIND`; the items a segment from the eye to nine points of each selected item's box passes through (box-culled, the pick oracle's triangle test) — a flat item's points lie on its posed footprint (`flat_targets`); roof parts are no occluders (Cutaway cuts them). |
| `core/shade_aggregation.py` | `SunHoursMap` (a shown map as plain data: `minutes_at`, `minutes_through`), and per-sample shade masks kept with every run (packed bits, up to 64 MB). |
| `ui/view3d/analysis_controller.py` | The drape mode, the sun path, the probe, the day sweep, Cutaway — paused while the pane is hidden, failures contained. |
| `ui/view3d/analysis_modes.py` | `DrapeMode`, `JUMP_YEARS` — importable at start-up without an engine module (gate G1). |
| `ui/view3d/growth_jump.py` | +N years on the ONE clock, "Back", and the two pictures of a before/after. |
| `ui/view3d/wipe.py` | The before/after, in the view's place in the pane. |
| `ui/view3d/compass_glyphs.py` | The four translated cardinal letters as outlines from the application font. |

**What each piece holds to.**

- *Overlays* are re-loaded into the ONE geometry of their Model (`ReloadableGeometry`,
  as the selection ring since L1.8): a drape, a sun step or a probe creates and
  destroys no Model and no texture (#531, #532). They are not items: the sink's
  `clear()` leaves them; the controller re-sends them when the pane shows again.
- *The overlays' blends.* The 2D shadows MULTIPLY the frame (the `"shade"` layer,
  `DstColor` / `Zero`, a linear multiplier): a shadow darkens in every mood (PF-L3D-07).
  The hours-of-sun map blends over; a blended custom material keeps the frame's alpha —
  `sourceAlphaBlend: Zero`, `destinationAlphaBlend: One` — or the view's texture lets
  the window's white through (PF-L3D-06). Every overlay but the shade divides its colour
  by the exposure (`overlay.frag`), and the arcs are built in pre-compensated colours
  (`ARC_ENGINE_RGBA`; the legend shows `ARC_RGBA`).
- *A faded or cut part is a screen door* (`screen.frag`; `foliage_door.frag`,
  `water_door.frag` — copies of the look shaders with the discard): an ordered dither
  discards all but its share of the pixels, so it stays opaque, keeps casting its shadow
  and needs no sorting, and it collapses in the depth pass ambient occlusion reads
  (`#if QSSG_ENABLE_DEPTH_PASS`), which does not run the discard (PF-L3D-08). No part
  blends or hides for X-ray or Cutaway; the look materials stay master's while nothing
  fades.
- *The drape is lifted 1.5 cm* (the tiles and the meadow's frame lie at 0): clear of the
  ground's depth from every distance the orbit camera frames a garden at, and below
  everything that stands on the ground.
- *The sweep's map* is the shown map's own samples taken by their local time of day
  (`SunHoursMap.sample_minutes_of_day`), summed incrementally as the sweep passes them
  — the map samples a UTC civil day; at sunset it is the whole map in every zone.
- *The probe* meets the drape's plane where the view ray through the click does
  (`pick_oracle.perspective_ray`, the camera the view is shown from — the walker's in
  walk mode); it reads `SunHoursMap.minutes_at` and `band_of` — only while the shared
  Hours of Sun says the map is current (`is_current()`; a dated preview of a changed
  plan reads `"updating"`, ADR-056). It needs no frame of
  its own: it rides the click's one pick (`OrbitInput.ground_clicked`).
- *X-ray* runs `XRAY_DELAY_MS` (150) after the camera, the selection or the records
  last changed, over the meshes the sink holds (`Workspace._held_parts`, shared with
  walk mode's world). A faded part is not pickable.
- *The hours-of-sun state has one owner*, `LiveSunMap`: the 3D drape follows its
  `enabled_changed` (off → "Nothing on the Ground", the menu follows) and choosing the
  drape switches it on.
- *The sweep gives the time back on every exit* — the end of the day, a stop, the
  engine going, a date change (a turn later: the clock refuses a write from its own
  notification) — except when the user set a time during it: theirs stays.
- *Growth jump*: the before-picture in `jump`, the after-picture in the first
  `applied` pass whose `Scene3DController.pass_date` is the new date — two frames per
  jump, the only frames besides the click's pick (the frame-taker scan in
  `test_view3d_workspace_widget.py` names both).
- *The strip's control row wraps* (`workspace._WrapRow`): it asks for its widest
  control, not the sum, so the Analyze button fits beside "Reset 3D View" and "Walk"
  in a 455 px Split pane in every language.

**Testing (§8.10).** The default tier holds the cores (`test_scene3d_drape.py`,
`test_scene3d_sun_path.py`, `test_scene3d_xray.py`, `test_plant_card_facts.py`), the QML
scene without a GPU (`tests/ui/test_view3d_analysis_host.py`) and the workflow with the
REAL 2D analysis beside the workspace and a stand-in engine
(`tests/integration/test_view3d_analysis.py`: each drape is compared with the 2D side's
own polygons and map, byte for byte for the hours of sun). The render tier
(`test_view3d_analysis_render.py`, opt-in) holds what only pixels show: the drape
darkens, row 0 is south, north is up, fades let the ground through, the roof goes.
The frozen `--selftest` draws a drape patch and a lines patch: both overlay shaders are
compiled from the bundle and judged by colour. The Beauty Board renders each shot with
the drapes, the sun path and Cutaway (`scripts/render_beauty_board.py --analysis`).

### 8.29.11 Plant Forge — procedural 3D species models, LODs and phenology (L3, #387, ADR-064)

All 123 sprite recipes (108 species, 15 categories) feed the same resolver and
`Traits3D` table in 2D and 3D. The forge covers 13 archetypes: canopy, conifer,
palm, mound, hedge, rosette, grass, feathery, allium, head, ground, flower and
climber. It uses no external model assets. Object sprite colours likewise live
in one stdlib-only material table; the SVG byte-conformance gate preserves them.

`lod.py` caps total triangles at 25,000 / 6,000 / 800. Camera distances up to
18 m use LOD0, up to 45 m use LOD1, beyond that LOD2. `ForgeCache` holds fully
sized/seeded meshes at most 256 entries and 64 MiB of array data. No disk cache:
a local Python 3.11 run over all 123 recipes at height 420 cm, radius 180 cm,
seed 303 (median of three builds per recipe) measured cold median 3.69 ms,
p90 13.07 ms, maximum 23.01 ms and warm median 0.0012 ms. These describe synthesis,
not first-frame or presentation latency. The acceptance budget is median 150 ms.

Foliage area follows crown surface area (target 1.6); lower counts receive larger
leaves within the same triangle cap. Structural wood independently keeps its
base at zero and top at the resolved height when seasonal leaves disappear.
Normal fitting uses the same axis scale as positions. Climber support prefers
an explicit trellis parent, then a nearby fence/wall/pergola/trellis within
50 cm of the canopy edge, then a bamboo tripod.

Flower, fruit/pod and tuber parts have independent seasonal controls. Recorded
harvest windows use `core/calendar_windows.py` and the plan's local frost dates,
including cross-year and leap-day anchors. Illustrative bloom/leaf seasons shift
six months in the southern hemisphere; the recorded frost calendar does not.
Seasonal state changes update shader/Model values without copying mesh buffers.
Plant existence remains the shared lifetime clock's responsibility (#315).

Tests exercise actual workspace scheduling and render flags, asynchronous stale
results, camera-only LOD, recovery invalidation, shader-only seasonal updates,
exact calendar dates, winter wood bounds and sparse tall crowns. They live in
`tests/integration/test_plant_forge.py`, `test_plant_forge_workspace.py`,
`test_plant_forge_calendar.py`, and the `test_plant_forge_l31.py` through
`test_plant_forge_l34.py`, `test_phenology.py`, `test_plant_forge_review.py`,
`test_plant_art.py` and `test_object_sprite_conformance.py` unit files.
The production Beauty Board and frozen self-test also exercise forged models.

The 300-plant / 100-support callback budget is **typical per-date wall time**,
not an absolute operating-system scheduling deadline. The render driver places
all plants in view on a grid, warms the three dates and settles frames outside
timing. It takes exactly 15 interleaved observations per date (April, June,
October), once, and gates the worst date median at **16.0 ms**. Every raw sample,
per-date median, combined p95 and maximum, and the actual graphics adapter are
published in the render artifacts. No adaptive retries select a passing round.
A negative control adds 20 ms inside the production uniform hop and must fail
the same budget. Geometry-job and Model/buffer-churn checks are independent.
The mixed-species phenology unit budget remains an additional gate.


### 8.29.12 The built world complete — objects, roofs, facades, surfaces, ground detail (L4, #388, ADR-065)

**Objects.** The 24 `OBJECT_KINDS` (furniture, play, utility, structures) are built
from the bevelled pieces of `builders/kit.py` in `builders/palette.py`'s colours, which
mirror the 2D object `MATERIALS` (drift guard in `test_scene3d_builders_palette.py`).
Every object goes through `BuiltBuilder` (top = resolved height by construction) and
stays under `OBJECT_TRIANGLE_BUDGET` (4,000) by construction: repeated members (slats,
staves, bays, lattice cells) are capped, and a hostile 9 km object stays bounded. Every
object kind has a default height in `core/object_height.DEFAULT_HEIGHTS_CM` (since the
owner's second pass, ADR-065, the parasol, fire pit, planter pot, cold frame, rain
barrel, water tap, swing, hammock and pergola too), so every object casts in 2D and 3D
and shows its height in the properties panel. How to add an object: a builder function
in the family module, an entry in its `KINDS`, a `DEFAULT_HEIGHTS_CM` row, a row in
`test_scene3d_l4_objects.py`'s parametrised cases (height, footprint margin,
orientation against the sprite's top edge = local +y).

**Roofs and facades.** `core/roof_style.py` owns the three optional metadata keys
(`roof_style`, `roof_pitch_deg`, `roof_overhang_cm`) and their clamping readers; the
snapshot copies them into the record's params for HOUSE, GARAGE_SHED and TOOL_SHED.
`builders/roofs.py` builds gable, hip (lower envelope of the eave planes, convex
footprints only), shed and flat roofs, each returning the walls' top as a function
so the walls meet the roof. `builders/facade.py` puts windows on every wall that can
hold one and the door on the wall `params["door_wall"]` names, batched into one mesh.
The 2D plan, its ridge line and its sun study read none of this.

**Context params.** `core/scene3d/context.py::with_context` runs once at the end of
`snapshot_records`: it writes a building's door wall (the wall facing the nearest
PATH; a garage's nearest DRIVEWAY first), a lawn's cut-outs (flat items painted above
it and enclosed buildings on it, in the lawn's frame, at most 96, largest first) and
a lawn's blade share (220 / m², ≤ 36,000 per lawn, ≤ 60,000 per plan, water-filled by
area; the roots' jittered grid lies over the lawn's bounding box and is bounded by
construction, `surfaces.MAX_SWARD_GRID` points and `MAX_SWARD_WORK` point-in-ring tests,
so a thin lawn in a huge box gets a sparser sward). All are geometry for `SceneSync`,
and all are `record.BUILD_ONLY_PARAMS`: the
ground bake compares records with `Record.same_ground_geometry`, which ignores them,
so a cut-out that moves rebuilds the lawn's blades without re-baking its tiles. The
lawn's blades are remembered whole (`surfaces.SWARD_CACHE_BYTES`, 64 MB, least recently
used first), so that rebuild only re-masks them: a move of a flat item over the lawn
costs 4.6 / 12.8 / 8.0 ms on bench_small / bench_large / bench_built (median of 15,
2026-10-26; 11.7 / 28.2 / 18.1 ms when every blade was regrown). The sync controller
forgets them with the plan (`clear_lawn_cache`).

**Ground detail.** A part that is relief on painted ground sets
`MeshPart.ground_detail` (and must not cast a shadow: `MeshPart.__post_init__`). It is
drawn, but it never makes its item a solid (`SceneSync.solid_ids`), the pick oracle
and QML (`pickable && !groundDetail`) never pick it, and the info card still says the
item lies on the ground. Paths get stones / planks / kerbs / a gravel edging per
style (gravel and dirt are their textures, painted by the bake — L4 manual pass), terraces and driveways kerbs or deck boards (`surface_pattern` DECKING / WOOD),
ponds water and coping, lawns blades. A surface with a height is a solid as before.
Stepping stones follow the 2D painter's walk (`surfaces.walk_path` =
`PathStylePaint._walk_path`); a stone that would hang past the path's end is slid half
a stone along it, one that cannot be slid onto the footprint is left out.

Gravel edging follows the round painted stroke, including outer bends and
caps, through the canonical `shadow_geometry.polyline_round_outline` helper.
Its bevelled profile is swept inward around every boundary; nominal analytical
caster footprints remain square/butt. Visible curves use 0.01 cm arc tolerance
and preflight/output guards cap the outline at 4096 vertices. Beyond that budget
the accurate ground bake remains without relief. The independent Qt oracle in
`tests/integration/test_gravel_rim_relief.py` checks outer arc/cap coverage and
rejects relief over inner texture or outside the painted stroke; the 0.05 cm
painted-outline bound replaces the old nominal-footprint gravel comparison
(#605, PR #645 owner finding).

**Presets.** Lawn blades are synthesized and uploaded only for High/Ultra.
`LookController.preset_changed` updates `Scene3DController.set_lawn_blades`; its
next snapshot adds/removes the geometry through SceneSync. Offscreen rendering
uses the same admission rule. QML `lawnBlades` also gates visibility. The lawn-only
`lawn.frag` folds normals upward; plant grass keeps its original shader. From Medium up the ground tiles use `ground.frag` (`detailNormals`), which
tilts the normal by the tile texture's own luminance gradient (clamped ±0.35). It
flips `v` itself: a `CustomMaterial`'s `TextureInput` ignores `Texture.flipV`
(measured: the tiles drew mirrored north–south). Scene-wide OIT is not used: it broke
L2's multiply drapes (ADR-065 decision 9).

**Paths.** A line's stroke is its width on the ground in cm: presets 70–100 cm, PATH
default 80 cm, the properties panel up to `MAX_LINE_WIDTH_CM` (500 cm, suffix "cm");
shapes keep `MAX_STROKE_WIDTH` (20 px). Bench plans older than L4 keep their widths
(`make_bench_plans.LEGACY_PATH_WIDTH_CM`); `bench_built.ogp` holds every L4 kind,
path style and roof style for the board.

**Truth details from the 3D review.** The endless meadow is a frame IN the plan's plane
(`core/scene3d/meadow.py`): a 20 km square around the plan in cells of at most 100 m, the
plan cut out less a 1 mm strip under its edge. Nothing lies under the plan. One quad of two
triangles 1 cm, then 5 cm, under the plan lost the depth test to it: its depth, interpolated
across 2 km, was more than 5 cm off at 55–90 m. The 5 cm step also drew an ambient-occlusion
line along every plan edge. The host loads the frame into one geometry when the plan
rectangle changes, like the selection ring. A keyed meadow is gated in 156 views: an orbit
sweep, and the workspace's own camera on the three bench plans. Path relief treats every
path as open, because its outline is: a
rail runs on its own offset line, chorded outside a bend where the outline squares off,
and a boardwalk's end planks stand half a plank in. A deck's boards are 2.5 cm high
(`DECK_TOP_CM`) and lie on the ground, so furniture standing at z 0 does not sink into
them. `kit.beam` and `kit.rod` lift an end that stands on the ground by what its tilted
end cap dips.
A lawn's cut-outs are one keyhole ring per region, so a loop of path keeps the lawn inside
it. A pond's cut-out is grown by its coping (`POND_CLEARANCE_CM`). An open gravel or dirt
path's cut-out is the rounded stroke the canvas paints (`ROUND_PATH_STYLES`). An object
without a height cuts the lawn only when it covers its footprint at the ground
(`GROUND_COVERING_KINDS`, whatever its height: a cold frame's soil and a fire pit's ash
lie under a blade's 7 cm); a pergola or a parasol stands in the grass.
"Painted above the lawn" is the 2D paint order, read from the record order. That order is
right only after the scene restacks its ground band (`CanvasScene._restack_ground_changes`,
PF-CAN-22). The restack runs on every `stack_changed` and scans the items. It skips the
scan when the command manager's `last_command` says it cannot change a band
(`changes_ground_band = False`, #592). That scan is what keeps the cut-outs right.
Two writes defeat it, and both leave 2D and 3D agreeing on a stale order:
- a height written outside a command: it emits no `stack_changed`, so it stays stale until
  the next command that is not marked `changes_ground_band = False`;
- a command wrongly marked `changes_ground_band = False`.
Either way, a terrace on a lowered lawn stays under the lawn and is not cut out.
Tests that change the height of a ground surface use the Properties panel's own command
(`_set_height` in `tests/integration/test_view3d_sync_controller.py`).

**Bounds from the senior review.** A deck's boards are found before a mesh is built,
with numpy row crossings; beyond `MAX_DECK_BOARDS` (2,000) boards, or `MAX_DECK_ROWS`
(1,000) rows scanned over all its regions, a deck gets a kerb, or its plain solid when
raised (a 402-vertex comb had built 446,364 triangles in 14 s; a sawtooth of 601 regions
narrower than 1 cm, which are now skipped, scanned rows for 2.8 s). A
kerb, skirt or coping is swept along at most `MAX_RELIEF_VERTICES` (4,096) outline
vertices; beyond, the surface keeps its painted ground. An overhang never takes a pitched
roof's lowest edge below `EDGE_FLOOR_SHARE` (half) of the eave floor: the overhang is
shortened and the chosen style and pitch kept (a 60 × 100 cm shed at 60° and 150 cm
reached 91.5 cm into the ground). How the overhang is found:
- Two estimates of how much more overhang holds. One is the chord to a roof that sank.
  The other is a line from the last roof that held: through the two last that held, or
  at first at that roof's own `slope`.
- That slope is the edge's fall per cm of overhang only for a hip, and for a gable square
  to its ridge. A gable with an oblique ridge falls faster at its far corner; the HOUSE
  tool's ridge follows the bounding box, so a house drawn turned has one. A shed's edge
  falls twice as fast until its slope clamp and slower after it. So neither estimate is
  sure to be short.
- A guess is the nearer estimate, 1 % short. After a guess sinks, the next goes at most
  halfway. Only a roof that holds is kept.
- The search stops when even the larger estimate (within the bracket) is under a
  centimetre or 2.5 % of the overhang found, or after `OVERHANG_TRIES` (5) guesses.
- On a straight edge the chord finds the root in one guess: three roofs in all.
- A builder returns no roof on an exact coincidence: a U outline's offset edge on the
  ridge line at 100 cm, or the ridge on the inner edge of an L drawn on a grid at no
  overhang. A guess is 1 % short of its estimate, so it never lands on the long end, and
  the short end is tried at half a centimetre too.
- A gable holds its eaves to 0.75 × (top − ridge cap − slab), lower than the eave floor.
  So a gabled building 18–22 cm tall is too low for the floor even without an overhang,
  and keeps that roof (its edge 0.8–3.7 cm above the ground).
- A style that builds no roof at either end is left to the caller: a hip falls back to
  the gable, otherwise the building is its plain block.

`scripts/measure_roof_overhang.py` measures the search over 20,592 cases (the grid in
its docstring, houses turned with the tool's ridge among them). It reports:
- 0 floor violations, and 0 roofs lost, where "lost" means no roof although some overhang
  in range holds;
- 624 gables at 20 cm that keep the walls' own roof;
- for the 1,581 cases it shortens: median 99.0 % of the longest overhang that holds,
  worst 96.5 %. The 3 under 97 % are the single-slope roof of a 100 × 50 cm shed at 4 m,
  60° and 100 cm, whose slope clamp kinks the edge's fall;
- 1.40 roofs built per case, 7 at most;
- 3 roofs for a 64-corner hip at 700 cm, 60° and 150 cm.

Context params change at most once per `CONTEXT_REBUILD_MIN_MS` during a drag (§8.29,
"A move or a recolour uploads nothing"). A held pass keeps the plan's 60,000 blades:
- The old shares are kept while the lawns' total fits, so a resized lawn leaves the
  others alone. Otherwise no held share is above its new one.
- A record that becomes or stops being a lawn (its blade share appears or goes) is not
  held: a lawn turned into a terrace, given a height, or lowered from one. Any other
  context param is held at its old state, an absent one included: a lawn's cut-outs
  come and go as an item crosses the lawn's box.
- A lawn with a height grows no blades and takes no share.

A document change and a pause end the hold, and a recovery from scratch applies the plan
unheld.

**Tests.** `test_scene3d_l4_objects.py`, `test_scene3d_l4_buildings.py`,
`test_scene3d_l4_surfaces.py` (unit, every builder through `verify_builder` on
hostile input), `tests/integration/test_l4_built_world.py` (panel → undo → snapshot →
context → production registry), the ground-bake and render tiers (the "ground alone"
gates take the relief off: `ground_bake_render_driver._without_relief`) and the
frozen self-test, whose High-preset frame compiles `ground.frag` from the bundle.

## 8.30 Line appearance snapshots and paint containment (#524, #525, #526, #471)

`core/item_look.py` owns `LineLook`, `capture_line_look`, `apply_line_look`,
`line_look_for_type` and `line_look_for_preset`. Commands capture copied Qt pen,
brush and color values. Restoring a snapshot never reapplies preset defaults;
`adopt_pen` updates the live pen and serialized stroke attributes together.
The callback does not retain a Properties panel. The panel's deferred type refresh
uses a parented timer, so destroying the panel also cancels the refresh.

Both type-change surfaces use the new type's defaults and clear the previous
path/fence preset. Undo restores the prior type, preset and exact stroke. Picking
NONE removes decoration while keeping the current stroke. Selecting the existing
type/preset adds no history entry. Context-menu multi-selection retains one command
per affected line. Existing non-line type changes are unchanged.

`ui/canvas/items/path_style_paint.py::style_paint_reach` owns the conservative
styled reach: `max(1.5, default_miter_limit) * width_cm + 4.0`. The canvas unions
that expansion of the path's control bounds with its existing bounds, then retains
its shadow allowance. The ground baker uses the same reach and its existing pixel
spill. No decorative elements are generated to calculate bounds. Pen and preset
changes notify Qt before mutating the values that determine the bounds. Unselected
items retain DeviceCoordinateCache; selection, hit testing and exports keep their
existing policies.

The integration pins are `test_line_appearance_history.py` (real controls, context
actions, command counts, exact history, full-window dirty state, persistence and
ground output) and `test_styled_line_bounds.py` (all ten painters, preset/narrow/wide
strokes, bends and hairpins, transformed cached views and notification order).
The uncached oracle paints into an independent fixed image, never into the bounds
being tested. Rotated Qt device caches may regenerate; the zero-rotation control
proves actual reuse by counting paint calls.
The dynamic cases populate the cache before width/preset edits, undo/redo and a
move, comparing every frame with a separate uncached view and checking that the
old location clears. Contrast is measured against an empty-scene image: absolute
darkness also counts the dark outside-page background, while a white-background
threshold misses the cream page. One device pixel permits antialiasing alignment;
the fixed-image geometric-containment oracle retains its separate exact bound.

The reproducible mutation replay is `scripts/replay_line_appearance_mutations.py`:
five isolated runtime plugins restore the name-only undo, preset overwrite,
square/bevel pen, old bounds and late geometry notification defects. Each must
cause assertion failures without setup errors; an unmodified full integration
control must pass. Plugins do not rewrite production source. Reports go to
`artifacts/line-mutations/`.

## 8.31 Plan date, visibility and lifetime (US-F4, ADR-062)

The shared SimClock local date is the plan date. One permanent Plan & Sun strip
holds the exact calendar and monthly slider, which preserves the preferred day
(clamping short months). Today preserves wall time.
Neither date navigation nor visibility filtering adds history or persists a date.

CanvasScene is the layer/date visibility seam: a plant is visible only when its
layer permits it and planting <= plan date < removal (an absent bound is open).
Construction geometry continues to use its tool toggle. Never force-show an absent
plant when updating layers or rendering an explicitly requested API layer. Hidden
plants remain serialized and listed in the API. Marquee selection checks isVisible.
The popover lists hidden plants by name and date bounds and navigates to a present day.

Lifetime fields use the existing Plant Details controls and one undoable command;
the removal minimum is an explicit nonempty unset label with a Clear button. Signals
are blocked during panel refresh. Hiding an edited plant can synchronously clear its
selection, so the command callback keeps its target independently of the panel.

The date-present set drives companion/spacing/capacity, guild and data diagnostics,
independently of drawing-layer visibility. PDF data pages retain hidden beds and
date-present plants. Solar receivers/casters and rendered overlays additionally
honor layer visibility. Use CanvasScene.is_present for data and isVisible for drawing.
Sprite growth, shadow casters, heatmaps and 3D all use the plan date, while task
reminders retain their real-world reference day. Plant task windows stop at removal;
species aggregation keeps the schedule while any instance remains. Manual/succession
dates and Season Manager file copies retain their existing behavior.

Post-clear timeline notification refreshes New Plan only after the old items are gone.
Hidden-layer discovery executes the existing layer visibility command and marks dirty;
the date navigation itself remains runtime-only. Lifetime refresh derives the age
label from stored metadata, including undo and rejected edits. Calendar selectors
ignore wheel edits; new lifetime dates stay within the SimClock range while existing
legacy dates remain unchanged and readable. Only date changes invalidate all plant
paint caches; a lifetime command updates its own item. Automatic API companion
checks use date-present bed members; task soil warnings use presence on their explicit
reference day, independently of the displayed simulation date.


Plant Details treats the form and profile identity as one presentation. Removing
species metadata through undo or selection refresh clears the header labels,
thumbnail, external links, source tooltip and licence line. Redo repopulates them;
the species-free selected item remains the Create Custom target. Pinned through
the real command-stack refresh by
`tests/integration/test_apply_database_species.py::test_undo_species_assignment_clears_the_whole_profile_and_redo_restores_it`.

### 8.31.1 Permanent controls and live-map/export lifecycle

The date/time editors use native QDateEdit/QTimeEdit subclasses so their styling,
typing and calendar popup remain native. Both delegate stepBy/stepEnabled to one
SunSimToolbar wall-reading path (FR-TIMELINE-06, PR #565): day/month/year arithmetic
carries across calendar boundaries; minute/hour arithmetic uses bounded civil
minutes, never timezone-aware elapsed seconds. The whole target date/time is
mirrored with widget signals blocked before emitting one datetime_changed value.
There is no transient midnight on the old date. Month/year steps preserve the
preferred day; direct calendar choices/typing and day steps establish a new one.
Daily animation and the time-of-day slider retain their selected-day behavior.
See PF-UI-26 and ADR-062's chronological-stepping addendum.

SunSimToolbar is the sole toolbar instance for date/time. Atomic groups wrap rather
than disappear into overflow; date width is derived from font metrics. Slider
lengths compact only when the flow's measured groups need it to fit two rows;
group geometry is refreshed before measuring, including on wider platform fonts.
Each row is measured before placement so all group layouts share the row's height
and centre their controls vertically. Date/time fields use the same themed sizing.
The Today button says Past or Future in its own place while the plan date is
elsewhere, at one width for all three texts (`_TodayButton.sizeHint`, each text
measured as `QToolButton` measures it), so no control after it moves while the date
does; a click goes back to today (ADR-062 addendum "Past/Future in the Today
button": a separate label pushed the month slider under the dragging pointer). To keep
the strip within two rows the sliders shrink, but no narrower than 70 px (`_MIN_SLIDER_WIDTH`). Map status consumes space only
while needed: a completed current map shares the calendar's date, an updating map
for that date says Updating, and an older preview retains its actual date. The
hidden-plants menu follows the visible map controls without an empty reserved slot.
Themed renders in both themes and all three locales test alignment as well as fit.
The former PlanTimelineToolbar is
removed. The main window restores bounds and splitter preferences, retaining its
application-defined toolbar rows instead of replaying saved toolbar topology.
A legacy state can otherwise put Plan & Sun beside the drawing tools: measured
at a 1707-pixel window, the strip shrank to 259 pixels and stretched its neighbors
to 137 pixels tall. Startup now retains the dedicated full-width row. The legacy
blob stays untouched; generic UiStateStore callers can still restore layout state.
The restart regression saves a shared row with the strip first or last, then checks
full width, separation and containment across two subsequent launches.
Solar and decorative shadows
are automatic; Hours of Sun and daily animation remain opt-in session state.

Never confuse an enabled map with a finished map: LiveSunMap tracks the requested
snapshot; SunHeatmapController keeps its in-flight snapshot and displayed_snapshot
separate. A retained preview names the displayed date, never the requested date.
Only current measurements may reach diagnostics. A failure remains visible as an
unavailable state; changing document/location/grid discards the preview. Repainting
an overlay does not request more daily work: scheduling compares semantic snapshots.

SunExportGate returns readiness through a Future, so API threads wait outside Qt.
Its GUI modal progress loop continues delivering worker results and cancellation.
The 30-second timeout does not widen the generic main-thread bridge timeout.
Generation/revision/wall-time checks protect exports even when no map is enabled.
No output is written until readiness and identity checks succeed. Animation uses
counted pause leases so concurrent exports cannot resume it prematurely. Print
uses the same readiness boundary and holds its lease until preview closes, validating
the snapshot before each paint. Its legend names the plan date. Cancellation closes
quietly; a changed document/date or failed calculation prevents rendering.


Collection itself is debounced: notifications only mark inputs dirty, withdraw
measurements and compare constant-time document/location/grid identity. The timer
collects one latest snapshot; a matching displayed receiver cache restores results
without a worker for requirement-only edits. is_current and UI reflection never
scan the scene. Export readiness and final validation remain explicit trust boundaries.

API export operations own their pause lease across queued calls. A lock coordinates
abandonment with begin and render admission; late calls refuse and queued cleanup
releases an acquired lease exactly once. Already-started rendering returns its actual
outcome. GUI cancellation wins even if readiness completed in the same event turn.

## 8.32 Panel edit boundaries and position locks (#552, #558–#560)

Plant Details species and instance edits use independent deep snapshots in
`PlantSpeciesEditCommand` / `PlantInstanceEditCommand`. Numeric valueChanged ticks
retain live feedback and merge through the command's merge_from method; the same
widget's editingFinished ends that gesture. Re-entering it starts a new undo step.
Shared custom-library writes are intentionally separate from document undo.
An editable-form signature rejects unchanged input before any online-to-custom
conversion or library write, so focus-only flushes cannot create phantom edits.

CommandManager emits before_history_navigation before selecting an undo/redo entry,
including an initially empty stack. Panels flush staged text there. The completed
history_navigated signal forces an in-place model refresh; that refresh never writes
a command. ProjectManager.before_save and application document dirty guards flush
the same editors, so a Save or Close within the notes debounce captures the input.
Ordinary same-selection updates protect the active editor's text/caret while other
fields refresh. Structural changes retain the existing focus/teardown safeguards.
Focus can be reported as the spinbox or its inner editor; both are interpreted
before save and protected during ordinary refresh. Notes retain numeric cursor
and selection offsets across document replacement.

PositionLockMixin is shared by GardenItemMixin and CurveEditMixin. Object menus use
the same Add/RemoveConstraintCommand actions and existing FIXED state. Scene
dimension refresh derives all badges; loading derives them after restoring the graph.
No panel selection is required. LockBadgeItem is hidden by visual exports.
DimensionLineManager suppresses its older center marker for PositionLockMixin
objects, so paths have exactly one upright badge; construction-only markers remain.

The real-widget regressions in test_plant_package_558_559_560_552_557.py exercise
save-before-debounce, pending Name undo/redo, separate spin gestures, focused
unrelated-field refresh, all menu families, and unselected/tool-created locks.
test_plant_dimensions_records.py covers assignment, exact/estimated records,
rotated width edits, overrides, growth and repeated save/load.

The Plan & Sun bar shows an actionable location prerequisite beside Hours of Sun
when either coordinate is missing, including before solar controls are used.
It opens the existing File → Set Garden Location dialog. Project location changes
and document replacement refresh it immediately; valid zero coordinates count as
configured. The hint replaces the generic map-unavailable label while coordinates
are absent. Saving a location lets an already enabled live map recover through its
existing scheduler. Date navigation remains available without a location.



## 8.33 Offline examples and template authoring (US-F5, ADR-066)

Welcome's Examples & templates tab and File > New from example share
`TemplateGallery`; File > New from template accepts any `.ogp`. Both call the one
normal document-load path with template-copy semantics. Save opens Save As for the
untitled copy. File > Save as template explains the exact data categories removed
and writes by default under `<app-data>/templates/`; that folder is also listed in
the gallery. Export does not rename or clean the live project.

To author a bundled example, edit `scripts/generate_examples.py`, run it in the
locked environment, inspect all three rendered previews and add its provenance.
Use the ordinary constructors and CreateItemsCommand so bed links and child lists
agree. Parents and children must share a layer for the z-order clamp. IDs are
normalized before the saved plan is reloaded and rendered. Every registered locale
needs sidecar name/description text. These content strings follow the existing
localized-data convention; widget text goes through Qt translation as usual.

Keep the field-classification test aligned with ProjectData. New project fields
must be explicitly kept or stripped; unknown serialized top-level keys are dropped.
The filter is not a free-text anonymizer. Succession dates are retained calendar
dates, so authors state their example year rather than claiming climate adaptation.
See `resources/examples/PROVENANCE.md` and `tests/integration/test_templates_gallery.py`.

The gallery tab hides Welcome's large banner. A bounded, scrollable details area
keeps a complete card visible at 600 x 500 with 9/12 pt fonts in every locale;
`tests/ui/test_template_gallery.py` pins the actual item/viewport rectangles.

### Orientation-creation lock regression (PR #649 owner pass)

`tests/integration/test_orientation_constraint_locks.py` drives registered
Parallel/Perpendicular tool gestures with a FIXED endpoint or chain member.
It measures the picked edges' scene-space endpoint vectors rather than their
items' stored angles. The full-window test clicks the toolbar button and
viewport midpoints, then checks one-step undo/redo and saved geometry on reload.
Refusals must retain a pre-existing redo entry as well as graph and geometry.

The same suite also reads the actual dashed connector item. Its endpoints
must match the selected scene-space edge midpoints. Index-only matching is
valid for polygon/polyline edges whose classification changes on vertex edits;
rectangle/ellipse/circle edge types are unique but share index 0.
