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

## Tech Stack
Python 3.11+ | PyQt6 | QGraphicsView/Scene | pytest + pytest-qt | ruff | mypy

## Workflow

### CRITICAL: Always Use Feature Branches
**NEVER commit directly to master!** Always work on feature branches.

### Step-by-Step Process
1. **Create feature branch** FIRST (before any changes)
   - Branch naming: `feature/US-X.X-short-description` (e.g., `feature/US-2.5-measure-distances`)
   - Command: `git checkout -b feature/US-X.X-short-description`

2. Read user story from `prd.md`

3. Clarify with `AskUserQuestion` tool if needed

4. Implement with type hints

5. Write tests, run lint (`pytest tests/ -v && ruff check src/`)

6. **WAIT for user to manually test and approve the functionality**
   - Do NOT commit yet
   - User will test the implementation
   - Only proceed after explicit approval

7. After user approval, commit changes:
   - Use GitHub sub-agent (Bash) for committing
   - Commit message format: `feat(US-X.X): Description`
   - Update progress in `CLAUDE.md` and `prd.md` in the same commit

8. Push feature branch and create PR:
   - `git push -u origin feature/US-X.X-short-description`
   - Use GitHub sub-agent to create PR to master
   - Use separate GitHub sub-agent instance to approve PR
   - Merge PR to master

9. After completing a US, `/clear` context

**Important Reminders**:
- Stay in working mode (no plan mode)
- **NEVER commit directly to master branch**
- **NEVER commit before user manually tests and explicitly approves**
- Always create feature branch BEFORE making any changes
- Only commit after user says "commit" or "looks good" or similar approval

## Testing Notes
- PyQt6 tests require `qtbot` fixture parameter in test methods even when unused (needed for Qt initialization); configure ruff per-file ignore for ARG002 in test files

## Progress (Phase 1)

| Status | US | Description |
|--------|-----|-------------|
| ✅ | 1.1 | Create new project with dimensions |
| ✅ | 1.2 | Pan and zoom canvas |
| ✅ | 1.7 | Cursor coordinates display |
| ✅ | 1.8 | App icon |
| ✅ | 1.9 | README banner |
| ✅ | 1.3 | Draw rectangles and polygons |
| ✅ | 1.4 | Select, move, delete objects |
| ✅ | 1.5 | Save/load project files |
| ✅ | 1.6 | Undo/redo |

## Project Structure
<!-- Keep this updated when adding/removing files -->

```
src/open_garden_planner/
├── __main__.py, main.py          # Entry points
├── app/application.py            # Main window (GardenPlannerApp)
├── core/
│   ├── commands.py               # Undo/redo command pattern
│   ├── project.py                # Save/load, ProjectManager
│   ├── geometry/                 # Point, Polygon, Rectangle primitives
│   └── tools/                    # Drawing tools
│       ├── base_tool.py          # ToolType enum, BaseTool ABC
│       ├── tool_manager.py       # ToolManager with signals
│       ├── select_tool.py        # Selection + box select
│       ├── rectangle_tool.py     # Rectangle drawing
│       └── polygon_tool.py       # Polygon drawing
├── ui/
│   ├── canvas/
│   │   ├── canvas_view.py        # Pan/zoom, key/mouse handling
│   │   ├── canvas_scene.py       # Scene (holds objects)
│   │   └── items/                # GardenItem, RectangleItem, PolygonItem, BackgroundImageItem
│   ├── dialogs/                  # NewProjectDialog, etc.
│   └── widgets/toolbar.py        # MainToolbar
└── resources/                    # Icons, images

tests/
├── unit/                         # Unit tests
├── integration/                  # Integration tests
└── ui/                           # UI tests
```

## Phase 1 Complete!

## Progress (Phase 2: Precision & Calibration)

| Status | US | Description |
|--------|-----|-------------|
| ✅ | 2.3 | Toggle grid overlay (was pre-implemented) |
| ✅ | 2.4 | Snap to grid (was pre-implemented) |
| ✅ | 2.1 | Import background image |
| ✅ | 2.7 | Adjust background image opacity |
| ✅ | 2.8 | Lock background image |
| ✅ | 2.2 | Calibrate image (two-point) |
| ✅ | 2.5 | Measure distances |
| ⬜ | 2.6 | Area/perimeter of selected polygons |

## Future Backlog
1. Vertex coordinate annotations on selection
2. Rotate objects (15° snap)
3. Edit polygon vertices