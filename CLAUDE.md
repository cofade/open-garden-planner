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
1. Read user story from `prd.md`
2. Clarify with `AskUserQuestion` tool
3. Implement with type hints
4. Write tests, run lint
5. Launch GitHub sub-agent (Haiku-based, create if not available) for
  - commiting (format: `feat(US-X.X): Description`)
    - commit not to master, only to feature branches
  - making PR
  - additional GitHub sub-agent instance for approving PR
6. Update progress below and in `prd.md`

**Important**: Stay in working mode (no plan mode). Commit after user confirms functionality works. After completing a US, `/clear` context.

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
| 🔄 | 2.1 | Import background image |
| 🔄 | 2.7 | Adjust background image opacity |
| 🔄 | 2.8 | Lock background image |
| ⬜ | 2.2 | Calibrate image (two-point) |
| ⬜ | 2.5 | Measure distances |
| ⬜ | 2.6 | Area/perimeter of selected polygons |

## Future Backlog
1. Vertex coordinate annotations on selection
2. Rotate objects (15° snap)
3. Edit polygon vertices