# Open Garden Planner - Claude Code Instructions

PyQt6 desktop app for precision garden planning with CAD-like metric accuracy.

## Quick Reference

```bash
# Run app
venv/Scripts/python.exe -m open_garden_planner

# Run tests
venv/Scripts/python.exe -m pytest tests/ -v

# Lint
venv/Scripts/python.exe -m ruff check src/

# Build installer locally (requires PyInstaller + NSIS)
venv/Scripts/python.exe installer/build_installer.py --version 1.2.0
```

## CI/CD & Releases

### Automated Releases (GitHub Actions)

Releases are **fully automated** via `.github/workflows/release.yml`. To trigger a release:

1. Create a feature branch and PR to `master`
2. Add a **version label** to the PR:
   - `major` → bump major (1.0.0 → 2.0.0) — breaking changes
   - `minor` → bump minor (1.0.0 → 1.1.0) — new features
   - `patch` → bump patch (1.0.0 → 1.0.1) — bug fixes (default if no label)
3. Merge the PR → release workflow automatically builds installer + creates GitHub Release

### CI Checks

`.github/workflows/ci.yml` runs on every push and PR:
- **Lint**: `ruff check src/` (ubuntu)
- **Test**: `pytest tests/ -v` under xvfb (ubuntu)

### Version Source of Truth

- **Git tags** (e.g., `v1.6.13`) are the version source of truth
- The release workflow reads the latest tag and bumps based on PR labels
- `installer/build_installer.py` accepts `--version X.Y.Z` to override the hardcoded default
- `pyproject.toml` version should stay in sync
- `src/open_garden_planner/__init__.py` `__version__` should stay in sync

### Version Assignment for US Implementation

When a US implementation is complete and ready to merge:
1. Run `git fetch --tags && git describe --tags --abbrev=0` to get the current latest tag
2. Assign the PR the version label based on the **scope** of change:

   | Scenario | Label | Example |
   |----------|-------|---------|
   | Individual US within an **ongoing phase** | `patch` | v1.9.0 → v1.9.1 |
   | **First US of a brand-new phase** | `minor` | v1.9.x → v1.10.0 |
   | 3D Visualization (Phase 13 only) | `major` | v1.x → v2.0.0 |

   > **Rule of thumb**: almost every US gets `patch`. Only bump `minor` when the PR starts a new phase.

3. After merge, the CI/CD pipeline tags and publishes the new release automatically
4. Update the progress table below with ✅ and the version delivered
5. **Do NOT wait for CI to complete.** The new version is deterministic: apply the bump rule to the
   current tag yourself. Update immediately after merge:
   - `pyproject.toml` → `version = "X.Y.Z"`
   - `src/open_garden_planner/__init__.py` → `__version__ = "X.Y.Z"`

### ⚠ Determining the Correct New Version — ALWAYS Follow This Protocol

**NEVER guess or infer the new version from the CLAUDE.md progress tables or `__init__.py`.**
The source of truth is the **git tags on master after pulling**.

After every PR merge, before writing any version:

```bash
git checkout master && git pull origin master
git fetch --tags
git describe --tags --abbrev=0   # → e.g. v1.8.4  ← THIS is your base
```

Apply the bump rule to **that tag** (not to whatever is written in pyproject.toml or __init__.py):

| Scenario | Bump |
|----------|------|
| US within an ongoing phase | patch |
| First US of a brand-new phase | minor |
| Major architectural milestone | major |

**Why tags may not match what's in the files**: CI creates the tag asynchronously; chore/sync commits
do NOT trigger a new tag (they're skipped by the Release workflow). If `__init__.py` already reads
`v1.9.1` but `git describe` returns `v1.8.4`, the tag is the truth — the files are stale from a
previous wrong sync.

**Wrong version already written?** Fix it in the chore commit — correct both files and the progress
table entries to match the tag-derived version before pushing.

## Where to Pick Up After Restart

1. **Check current progress** in the Phase 8 table below
2. **Read the roadmap**: `docs/roadmap.md` has full user stories and acceptance criteria
3. **Also update the GitHub wiki** when progress is made — the wiki repo is at `../open-garden-planner.wiki/` (cloned next to this repo). Edit `Roadmap.md` there, commit, and push to keep it in sync.
4. **Read architecture docs**: `docs/` contains arc42 documentation (see Documentation section below)
5. **Check git status**: See recent git history, which branch you're on and any uncommitted changes
6. **Pick the next unchecked US** from the Phase 8 progress table below

## Documentation (arc42)

All project documentation is in the `docs/` directory:

| Section                             | Key Content                                          |
| ----------------------------------- | ---------------------------------------------------- |
| `docs/01-introduction-and-goals/`   | Vision, goals, target users, prd.md index            |
| `docs/02-constraints/`              | Technical/org constraints, licensing (GPLv3)         |
| `docs/03-context-and-scope/`        | Competitive analysis, external APIs, plant API setup |
| `docs/04-solution-strategy/`        | Tech stack, design decisions, visual strategy        |
| `docs/05-building-block-view/`      | Architecture layers, module structure, object model  |
| `docs/06-runtime-view/`             | Drawing, save/load, export, undo/redo flows          |
| `docs/07-deployment-view/`          | Windows installer (NSIS), CI/CD, system requirements |
| `docs/08-crosscutting-concepts/`    | Coordinate system, i18n, themes, dev workflow        |
| `docs/09-architecture-decisions/`   | ADRs for all key technical choices                   |
| `docs/10-quality-requirements/`     | Performance targets, testing strategy                |
| `docs/11-risks-and-technical-debt/` | Open questions, risks, tech debt                     |
| `docs/12-glossary/`                 | Terms, keyboard shortcuts, references                |
| `docs/functional-requirements.md`   | All FR-\* requirements                               |
| `docs/roadmap.md`                   | **Phases, user stories, acceptance criteria**        |

## Translation (i18n) Requirements

**Always use `self.tr("string")` for every user-visible string in any `QWidget` subclass.**

### How to add translations when creating/modifying a widget

1. **In code**: wrap every UI string with `self.tr("English text")`. The class name is the translation context automatically.

2. **Update both `.ts` files** — add a `<context>` block (or extend an existing one) to:
   - `src/open_garden_planner/resources/translations/open_garden_planner_de.ts`
   - `src/open_garden_planner/resources/translations/open_garden_planner_en.ts`

   Format (note: German file uses `<name>` with no extra indent, English file uses 4-space indent):
   ```xml
   <context>
       <name>MyWidget</name>
       <message>
           <source>English text</source>
           <translation>Translated text</translation>
       </message>
   </context>
   ```

3. **Recompile `.qm` files** after every `.ts` change:
   ```bash
   venv/Lib/site-packages/qt6_applications/Qt/bin/lrelease.exe \
     src/open_garden_planner/resources/translations/open_garden_planner_de.ts \
     src/open_garden_planner/resources/translations/open_garden_planner_en.ts
   ```

### Rules
- Strings passed to `CollapsiblePanel(title, ...)` must use `self.tr("title")` at the **call site** (e.g. in `application.py`), because `CollapsiblePanel` is generic and has no context for the title string.
- `QT_TR_NOOP("string")` marks strings for extraction without translating them at that point (used in module-level dicts). Translate them later with `QCoreApplication.translate("ContextClass", string)`.
- Non-`QObject` contexts (e.g. module-level code) use `QCoreApplication.translate("ContextName", "string")`.

## Tech Stack

Note: Use context7 as required for up-to-date documentation in any scenario where you require it.
Python 3.11+ | PyQt6 | QGraphicsView/Scene | pytest + pytest-qt | ruff | mypy

## Workflow

### CRITICAL: Always Use Feature Branches

**NEVER commit directly to master!** Always work on feature branches.

### Step-by-Step Process

1. **Create feature branch** FIRST (before any changes)
   - Branch naming: `feature/US-X.X-short-description` (e.g., `feature/US-6.1-tileable-textures`)
   - Command: `git checkout -b feature/US-X.X-short-description`

2. Read user story from `docs/roadmap.md`

3. Clarify with `AskUserQuestion` tool if needed

4. Implement with type hints

5. Write tests, run lint (`pytest tests/ -v && ruff check src/`)

6. **WAIT for user to manually test and approve the functionality**
   - Do NOT commit yet
   - **Provide a Manual Testing Checklist** covering all acceptance criteria from the user story
   - User will test the implementation
   - Only proceed after explicit approval

7. After user approval, commit changes:
   - Use GitHub sub-agent (Bash subagent_type) for committing
   - Commit message format: `feat(US-X.X): Description`
   - Update progress in `CLAUDE.md` and `docs/roadmap.md` in the same commit

8. Push feature branch and create PR:
   - **Note:** GitHub CLI is installed at `C:\Program Files\GitHub CLI\gh.exe` (not in PATH on Windows)
   - **Use GitHub sub-agent (Bash subagent_type) to push and create PR:**
     - Push: `git push -u origin feature/US-X.X-short-description`
     - Create PR: `"C:\Program Files\GitHub CLI\gh.exe" pr create --title "feat(US-X.X): Title" --body "$(cat <<'EOF' ... EOF)"`
     - Include summary, technical details, test plan in PR body
     - End body with: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

   - **Merge the PR directly with admin flag** (self-approval not allowed):
     - Merge: `"C:\Program Files\GitHub CLI\gh.exe" pr merge <PR-NUMBER> --squash --delete-branch --admin`
     - Note: Use `--admin` flag to bypass branch protection rules

9. After PR is merged, switch back to master:
   - `git checkout master && git pull origin master`

10. **Sync version** — CI/CD creates a new git tag on merge; pull it and update both version files:
    ```bash
    git fetch --tags
    git describe --tags --abbrev=0   # → e.g. v1.7.0
    ```
    Then update **both** of these to the new version (strip the leading `v`):
    - `src/open_garden_planner/__init__.py` → `__version__ = "1.7.0"`
    - `pyproject.toml` → `version = "1.7.0"`

11. After completing a US, `/clear` context

**Important Reminders**:

- Stay in working mode (no plan mode)
- **NEVER commit directly to master branch**
- **NEVER commit before user manually tests and explicitly approves**
- Always create feature branch BEFORE making any changes
- Only commit after user says "commit" or "looks good" or similar approval

## Testing Notes

- PyQt6 tests require `qtbot` fixture parameter in test methods even when unused (needed for Qt initialization); configure ruff per-file ignore for ARG002 in test files

## Known Pitfalls

- **Release workflow race condition with chore commits**: After merging a feature PR, two chore commits are pushed (sync version + mark progress). These land ~37s after the PR merge but the Release workflow building the new tag takes ~2m50s. The chore-commit Release runs start while the tag doesn't exist yet, compute a stale version (e.g., `v1.8.4` instead of `v1.9.2`), and fail with "release with the same tag name already exists". Fixed by adding `if: "!startsWith(github.event.head_commit.message, 'chore:')"` to the release job, which skips the workflow for chore commits.

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.
- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.
- **3-anchor constraints not solved on add**: `_compute_constraint_solve_moves()` in `canvas_view.py` collects `constrained_ids` from `anchor_a` and `anchor_b` only. Any constraint with a third anchor (`anchor_c`, e.g. ANGLE) must also add `anchor_c.item_id` here, otherwise the third item is absent from `item_positions` and the solver cannot move it — showing as red/violated until the user manually drags an object.
- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

## Project Structure

<!-- Keep this updated when adding/removing files -->

```
src/open_garden_planner/
├── __main__.py, main.py          # Entry points
├── app/
│   ├── application.py            # Main window (GardenPlannerApp)
│   └── settings.py               # App-level settings/preferences
├── core/
│   ├── commands.py               # Undo/redo command pattern
│   ├── project.py                # Save/load, ProjectManager
│   ├── object_types.py           # ObjectType enum, default styles
│   ├── fill_patterns.py          # Texture/pattern rendering
│   ├── plant_renderer.py         # Plant SVG loading, caching, rendering
│   ├── furniture_renderer.py     # Furniture/hedge SVG rendering & caching
│   ├── constraints.py            # Distance constraint model & solver
│   ├── measure_snapper.py        # Anchor-point snapper for measure tool
│   ├── measurements.py           # Measurement data model
│   ├── snapping.py               # Object snapping logic
│   ├── alignment.py              # Object alignment helpers
│   ├── i18n.py                   # Internationalization, translator loading
│   ├── geometry/                 # Point, Polygon, Rectangle primitives
│   └── tools/                    # Drawing tools
│       ├── base_tool.py          # ToolType enum, BaseTool ABC
│       ├── tool_manager.py       # ToolManager with signals
│       ├── select_tool.py        # Selection + box select + vertex editing
│       ├── rectangle_tool.py     # Rectangle drawing
│       ├── polygon_tool.py       # Polygon drawing
│       ├── circle_tool.py        # Circle drawing
│       ├── polyline_tool.py      # Polyline/path drawing
│       ├── measure_tool.py       # Distance measurement
│       └── constraint_tool.py    # Distance constraint creation
├── models/
│   ├── plant_data.py             # Plant data model
│   └── layer.py                  # Layer model
├── ui/
│   ├── canvas/
│   │   ├── canvas_view.py        # Pan/zoom, key/mouse handling
│   │   ├── canvas_scene.py       # Scene (holds objects)
│   │   ├── dimension_lines.py    # Dimension line rendering & management
│   │   └── items/                # Canvas item types
│   │       ├── garden_item.py    # GardenItem base class
│   │       ├── rectangle_item.py
│   │       ├── polygon_item.py
│   │       ├── circle_item.py
│   │       ├── polyline_item.py
│   │       ├── background_image_item.py
│   │       └── resize_handle.py
│   ├── panels/
│   │   ├── drawing_tools_panel.py
│   │   ├── properties_panel.py
│   │   ├── layers_panel.py
│   │   ├── gallery_panel.py      # Thumbnail gallery sidebar
│   │   ├── plant_database_panel.py
│   │   └── plant_search_panel.py
│   ├── dialogs/
│   │   ├── new_project_dialog.py
│   │   ├── welcome_dialog.py
│   │   ├── calibration_dialog.py
│   │   ├── custom_plants_dialog.py
│   │   ├── export_dialog.py
│   │   ├── preferences_dialog.py
│   │   ├── print_dialog.py
│   │   ├── shortcuts_dialog.py
│   │   ├── plant_search_dialog.py
│   │   └── properties_dialog.py
│   ├── widgets/
│   │   ├── toolbar.py            # MainToolbar
│   │   └── collapsible_panel.py
│   └── theme.py                  # Light/Dark theme system
├── services/
│   ├── plant_api/                # Trefle.io/Perenual/Permapeople integration
│   │   ├── base.py
│   │   ├── manager.py
│   │   ├── perenual_client.py
│   │   ├── permapeople_client.py
│   │   └── trefle_client.py
│   ├── plant_library.py          # Local plant library management
│   ├── export_service.py         # PDF/image export
│   ├── autosave_service.py       # Autosave logic
│   └── update_checker.py         # GitHub releases update check (frozen exe only)
└── resources/
    ├── icons/                    # App icons, banner, tool SVGs
    ├── textures/                 # Tileable PNG textures
    ├── plants/                   # Plant SVG illustrations
    ├── translations/             # .ts source & .qm compiled translations
    └── objects/                  # Object SVG illustrations
        ├── furniture/            # Outdoor furniture SVGs
        └── infrastructure/       # Garden infrastructure SVGs

installer/                        # Windows installer build files
├── ogp.spec                      # PyInstaller spec (--onedir bundle)
├── ogp_installer.nsi             # NSIS installer script (wizard, registry)
├── build_installer.py            # Build orchestration script
├── ogp_app.ico                   # Application icon (multi-size)
└── ogp_file.ico                  # .ogp file type icon

docs/                             # arc42 architecture documentation
├── 01-introduction-and-goals/    # Vision, goals, users
├── 02-constraints/               # Technical/org constraints
├── 03-context-and-scope/         # Competitors, APIs, plant API setup
├── 04-solution-strategy/         # Tech stack, decisions
├── 05-building-block-view/       # Architecture, modules, object model
├── 06-runtime-view/              # Workflow flows
├── 07-deployment-view/           # Installer, CI/CD
├── 08-crosscutting-concepts/     # i18n, themes, dev workflow
├── 09-architecture-decisions/    # ADRs
├── 10-quality-requirements/      # Performance, testing
├── 11-risks-and-technical-debt/  # Risks, tech debt
├── 12-glossary/                  # Terms, shortcuts, refs
├── functional-requirements.md    # All FR-* requirements
└── roadmap.md                    # Phases & user stories

tests/
├── unit/                         # Unit tests
├── integration/                  # Integration tests
└── ui/                           # UI tests (pytest-qt)
```

## Phases 1-7 + Backlog Complete!

## Progress (Phase 7: CAD Precision & Constraints v1.1 – v1.6) ✅

| Status | US   | Description                                          |
| ------ | ---- | ---------------------------------------------------- |
| ✅     | 7.1  | Measure tool snap to object anchors                  |
| ✅     | 7.2  | Distance constraint data model & solver              |
| ✅     | 7.3  | Distance constraint tool                             |
| ✅     | 7.4  | Dimension line visualization                         |
| ✅     | 7.5  | Constraint solver drag integration                   |
| ✅     | 7.6  | Constraints manager panel                            |
| ✅     | 7.7  | Numeric position input                               |
| ✅     | 7.8  | Numeric dimension input                              |
| ✅     | 7.9  | Horizontal/Vertical alignment constraints            |
| ✅     | 7.10 | Angle constraints                                    |
| ✅     | 7.11 | Symmetry constraints                                 |
| ✅     | 7.12 | Construction geometry                                |
| ✅     | 7.13 | Draggable guide lines                                |
| ✅     | 7.14 | Linear array placement                               |
| ✅     | 7.15 | Grid array placement                                 |
| ✅     | 7.16 | Circular array placement                             |
| ✅     | 7.17 | Coincident constraint (merge two anchor points)      |
| ✅     | 7.18 | Parallel constraint (two edges stay parallel)        |
| ✅     | 7.19 | Perpendicular constraint (two edges at 90°)          |
| ✅     | 7.20 | Equal size constraint (same radius/width/height)     |
| ✅     | 7.21 | Fix in place / Block constraint                      |
| ✅     | 7.22 | Horizontal/Vertical distance constraints (1D)        |
| ✅     | 7.23 | FreeCAD-style constraint toolbar + full SVG icon set |

## Progress (Phase 8: Location, Climate & Planting Calendar v1.7)

> **Version note**: Remaining Phase 8 USes use the `patch` label (v1.8.x series). The first US of Phase 9 uses `minor` (→ v1.9.0).

| Status | US   | Description                                          |
| ------ | ---- | ---------------------------------------------------- |
| ✅     | 8.1  | GPS location & climate zone setup                    |
| ✅     | 8.2  | Frost date & hardiness zone API lookup               |
| ✅     | 8.3  | Auto-update notification & one-click installer download |
| ✅     | 8.4  | Plant calendar data model                            |
| ✅     | 8.5  | Planting calendar view (tab)                         |
| ✅     | 8.6  | Dashboard / today view                               |
| ✅     | 8.7  | Tab-based main window architecture                   |

## Progress (Phase 9: Seed Inventory & Propagation Planning v1.8)

| Status | US   | Description                                          |
| ------ | ---- | ---------------------------------------------------- |
| ✅     | 9.1  | Seed packet data model                               |
| ✅     | 9.2  | Seed viability database                              |
| ✅     | 9.3  | Seed inventory management panel                      |
| ✅     | 9.4  | Seed inventory tab view                              |
| ✅     | 9.5  | Propagation planning (pre-cultivation)               |
| ✅     | 9.6  | Seed-to-plant manual linking                         |

## Progress (Phase 10: Companion Planting & Crop Rotation v1.9)

| Status | US    | Description                                          |
| ------ | ----- | ---------------------------------------------------- |
| ✅     | 10.1  | Companion planting database                          |
| ✅     | 10.2  | Companion planting visual warnings                   |
| ✅     | 10.3  | Companion planting recommendation panel              |
| ✅     | 10.4  | Whole-plan compatibility check                       |
|        | 10.5  | Crop rotation data model                             |
|        | 10.6  | Crop rotation recommendations                        |
|        | 10.7  | Season management & plan duplication                 |

Full user stories, acceptance criteria, and technical notes: see `docs/roadmap.md`
