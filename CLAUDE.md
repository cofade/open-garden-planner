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
```

## Where to Pick Up After Restart

1. **Check current progress** in the Phase 6 table below
2. **Read the roadmap**: `docs/roadmap.md` has full user stories and acceptance criteria
3. **Read architecture docs**: `docs/` contains arc42 documentation (see Documentation section below)
4. **Check git status**: See recent git history, which branch you're on and any uncommitted changes
5. **Pick the next unchecked US** from the Phase 6 progress table below

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

10. After completing a US, `/clear` context

**Important Reminders**:

- Stay in working mode (no plan mode)
- **NEVER commit directly to master branch**
- **NEVER commit before user manually tests and explicitly approves**
- Always create feature branch BEFORE making any changes
- Only commit after user says "commit" or "looks good" or similar approval

## Testing Notes

- PyQt6 tests require `qtbot` fixture parameter in test methods even when unused (needed for Qt initialization); configure ruff per-file ignore for ARG002 in test files

## Project Structure

<!-- Keep this updated when adding/removing files -->

```
src/open_garden_planner/
├── __main__.py, main.py          # Entry points
├── app/application.py            # Main window (GardenPlannerApp)
├── core/
│   ├── commands.py               # Undo/redo command pattern
│   ├── project.py                # Save/load, ProjectManager
│   ├── object_types.py           # ObjectType enum, default styles
│   ├── fill_patterns.py          # Texture/pattern rendering
│   ├── plant_renderer.py         # Plant SVG loading, caching, rendering
│   ├── furniture_renderer.py     # Furniture/hedge SVG rendering & caching
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
│       ├── plant_tool.py         # Plant placement
│       └── measure_tool.py       # Distance measurement
├── ui/
│   ├── canvas/
│   │   ├── canvas_view.py        # Pan/zoom, key/mouse handling
│   │   ├── canvas_scene.py       # Scene (holds objects)
│   │   └── items/                # GardenItem, RectangleItem, PolygonItem, etc.
│   ├── panels/                   # Sidebar panels (drawing tools, properties, layers, plants)
│   ├── dialogs/                  # NewProjectDialog, WelcomeDialog, etc.
│   ├── widgets/toolbar.py        # MainToolbar
│   └── theme.py                  # Light/Dark theme system
├── services/
│   └── plant_api.py              # Trefle.io/Perenual/Permapeople integration
└── resources/
    ├── icons/                    # App icons, banner, tool SVGs
    ├── textures/                 # Tileable PNG textures (Phase 6)
    ├── plants/                   # Plant SVG illustrations (Phase 6)
    ├── translations/             # .ts source & .qm compiled translations
    └── objects/                  # Object SVG illustrations (Phase 6)
        ├── furniture/            # Outdoor furniture SVGs
        └── infrastructure/       # Garden infrastructure SVGs

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

## Phases 1-5 + Backlog Complete!

## Progress (Phase 6: Visual Polish & Public Release v1.0)

| Status | US   | Description                                       |
| ------ | ---- | ------------------------------------------------- |
| ✅     | 6.1  | Rich tileable PNG textures for all materials      |
| ✅     | 6.2  | Illustrated SVG plant rendering (hybrid approach) |
| ✅     | 6.3  | Drop shadows on all objects (toggleable)          |
| ✅     | 6.4  | Visual scale bar on canvas                        |
| ✅     | 6.5  | Visual thumbnail gallery sidebar                  |
| ✅     | 6.6  | Toggleable object labels on canvas                |
| ✅     | 6.7  | Branded green theme (light/dark)                  |
| ✅     | 6.8  | Outdoor furniture objects                         |
| ✅     | 6.9  | Garden infrastructure objects                     |
| ✅     | 6.10 | Object snapping & alignment tools                 |
| ✅     | 6.11 | Fullscreen preview mode (F11)                     |
| ✅     | 6.12 | Internationalization (EN + DE, Qt Linguist)       |
| ✅     | 6.13 | Print support with scaling                        |
|        | 6.14 | Windows installer (NSIS) + .ogp file association  |
|        | 6.15 | Path & fence style presets                        |
