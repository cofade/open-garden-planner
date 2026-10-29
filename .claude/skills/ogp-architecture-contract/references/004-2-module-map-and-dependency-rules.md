## 2. Module map and dependency rules

Verified against `docs/05-building-block-view/README.md` §5.2 and the source tree.

| Package (`src/open_garden_planner/…`) | Role | May depend on |
|---|---|---|
| `main.py`, `__main__.py` | Entry points (incl. the mandatory pre-QApplication `QtWebEngineWidgets` import, ADR-019) | everything |
| `app/` | `application.py` (main window `GardenPlannerApp` — the wiring hub), `settings.py` (`AppSettings`), `paths.py` (the ADR-027 dialog-directory chokepoint), `ui_state.py` | `ui`, `core`, `models`, `services`, `agent_api` |
| `ui/` | Canvas (`ui/canvas/` — view, scene, `items/`), panels, dialogs, views (dashboard tabs), widgets (`panel_stack.SidebarController`, gallery, toolbars) | `core`, `models`, `services` |
| `core/` | Commands + `CommandManager`, `ProjectManager` (save/load/snapshot), `object_types` (predicates), constraints + solvers, `snap/` engine, `cad_geometry`, `mirror_geometry`, `coordinate_input/`, `tools/` (drawing tools), `plant_sizing`, `container_model`, `parametric_eval` | `models`; PyQt6 QtCore/QtGui freely; **`ui` only function-local/TYPE_CHECKING** (invariant 11) |
| `models/` | Pure data: `plant_data` (incl. `species_key`), `task`, `harvest_log`, `smart_symbol` | stdlib (Qt-free where marked) |
| `services/` | Qt-free domain engines (`task_generator`, `task_status`, `harvest_aggregation`, `smart_symbol_library`, shopping list, soil, crop rotation) + Qt-using I/O services (export, `scene_rendering`, pdf report, dxf, weather) | `core`, `models`; never `ui` panels |
| `agent_api/` | Embedded MCP server (see invariant 12). Qt-touching: `bridge.py`, `render.py` only | `core` (snapshot shapes), `services/scene_rendering`; wired by `app/` |
| `resources/` | Data (`plant_species.json` — the single species+calendar source, ADR-014; `smart_symbols/*.json`), icons, textures, translations, web | — |

Rules of thumb: **new domain logic starts Qt-free in `core/` or `services/`** and
gets a thin Qt adapter; **`application.py` is wiring, not logic**; anything both
dashboard tabs or multiple shapes need lives at ONE seam (see invariants 6, 7, 15).

