## Provenance and maintenance

All claims verified 2026-07-03 against master (v1.23.0). Re-verify with:

- `grep -n 'FILE_VERSION = ' src/open_garden_planner/core/project.py` — schema version (row 9)
- `grep -n 'def execute\|def register_applied\|stack_changed' src/open_garden_planner/core/commands.py` — two-entry-point contract (row 3)
- `grep -n 'scale(self._zoom_factor, -self._zoom_factor)' src/open_garden_planner/ui/canvas/canvas_view.py` — Y-flip at the view (row 1)
- `grep -n 'def is_bed_type\|def is_plant_parent_type\|def is_container_type' src/open_garden_planner/core/object_types.py` — predicate split (row 8)
- `grep -n 'def build_bed_context_menu\|def dispatch_bed_action' src/open_garden_planner/ui/canvas/items/garden_item.py` — bed-feature seam (row 7)
- `grep -n 'def set_task_status\|def set_task_completion' src/open_garden_planner/core/project.py` and `grep -n 'def make_calendar_task_id' src/open_garden_planner/services/task_generator.py` — task write path (row 6)
- `grep -rlE '^(from|import) PyQt6' src/open_garden_planner/agent_api/` — must list only `bridge.py` + `render.py` (row 10). Use the anchored form: a bare `grep -rl PyQt6` false-alarms on the "No PyQt6" docstrings in `queries.py`/`mapping.py`/`diagnostics.py`.
- `grep -rn 'from open_garden_planner.ui' src/open_garden_planner/core/` — every hit must be function-local or TYPE_CHECKING (row 11)
- `grep -n '127.0.0.1\|token' src/open_garden_planner/agent_api/server.py` — loopback-only; reads open, every scene write token-gated (row 12)
- `grep -n '8.9.8' docs/08-crosscutting-concepts/README.md` — pivot invariant text (row 2)
- `grep -n '^| TD-' docs/11-risks-and-technical-debt/README.md` — TD register rows with status and issue (§4)
- `grep -n 'def addItem\|def _refresh_layer_z\|def suspend_z_refresh' src/open_garden_planner/ui/canvas/canvas_scene.py` and `grep -n 'class ArrangeItemsCommand' src/open_garden_planner/core/commands.py` — the four rank writers (row 19)
- `grep -n 'def build_arrange_command' src/open_garden_planner/ui/canvas/arrange.py` — the one arrange seam (row 19)

If any command's output contradicts this file, **the repo wins** — update this
skill in the same PR that changed the fact.

