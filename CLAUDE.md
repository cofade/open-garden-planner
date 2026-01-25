# Claude Code Project Instructions

This file provides context for Claude Code sessions working on Open Garden Planner.

## Project Overview

Open Garden Planner is an open-source PyQt6 desktop application for precision garden planning with CAD-like metric accuracy. See `prd.md` for the full Product Requirements Document.

## Tech Stack

- **Python 3.11+** with **PyQt6** for GUI
- **QGraphicsView/Scene** for canvas with pan/zoom
- **pytest + pytest-qt** for testing
- **ruff** for linting, **mypy** for type checking

## Development Workflow

1. Read the relevant user story from `prd.md`
2. Implement the feature with proper type hints
3. Write comprehensive tests (unit, integration, UI as appropriate)
4. Run tests: `venv\Scripts\python.exe -m pytest tests/ -v`
5. Run linter: `venv\Scripts\python.exe -m ruff check src/`
6. Commit with conventional commit format: `feat(US-X.X): Description`
7. Update checkboxes in `prd.md` when milestones are complete

## Running the Application

```bash
venv\Scripts\python.exe -m open_garden_planner
```

## Current Progress (Phase 1: Foundation)

### Completed User Stories
- [x] US-1.1: Create new project with specified dimensions
- [x] US-1.2: Pan and zoom the canvas smoothly
- [x] US-1.7: See cursor coordinates in real-time
- [x] US-1.8: Display OGP logo icon on startup
- [x] US-1.9: Display banner image in GitHub README

### Remaining User Stories (Phase 1)
- [ ] US-1.3: Draw rectangles and polygons on the canvas
- [ ] US-1.4: Select, move, and delete objects
- [ ] US-1.5: Save project to file and reopen it
- [ ] US-1.6: Undo and redo actions

### Recommended Next Steps
1. **US-1.3**: Implement drawing tools (rectangle, polygon)
2. **US-1.4**: Implement selection and object manipulation
3. **US-1.6**: Implement undo/redo with command pattern
4. **US-1.5**: Implement JSON save/load

## Key Files

| File | Purpose |
|------|---------|
| `src/open_garden_planner/main.py` | Application entry point |
| `src/open_garden_planner/app/application.py` | Main window (GardenPlannerApp) |
| `src/open_garden_planner/ui/canvas/canvas_view.py` | Canvas view with pan/zoom |
| `src/open_garden_planner/ui/canvas/canvas_scene.py` | Canvas scene (holds objects) |
| `src/open_garden_planner/ui/dialogs/` | Dialog windows |
| `src/open_garden_planner/core/geometry/` | Geometry primitives (Point, Polygon, etc.) |
| `tests/` | Test suite (unit, integration, UI) |

## Code Conventions

- Use type hints on all functions
- Follow existing code patterns
- Keep commits atomic with clear messages
- All tests must pass before committing
- Update `CLAUDE.md` progress when completing user stories
