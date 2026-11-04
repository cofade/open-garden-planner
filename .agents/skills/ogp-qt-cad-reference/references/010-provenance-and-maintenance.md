## Provenance and maintenance

Facts verified 2026-07-04 against v1.23.0 source + `docs/08-crosscutting-concepts/README.md` (§8.1/8.9/8.10/8.12/8.16/8.19), `docs/09-architecture-decisions/README.md` (ADR-002/012/020/022/023/025/028), `docs/11-risks-and-technical-debt/README.md` §11.4. Re-verify volatile claims:

- Y-flip transform: `grep -n "scale(self._zoom_factor" src/open_garden_planner/ui/canvas/canvas_view.py`
- Handle allow-list + re-grab: `grep -n "_active_drag_handle" src/open_garden_planner/ui/canvas/canvas_view.py`
- Snap priorities: `grep -rn "priority = " src/open_garden_planner/core/snap/providers/`
- Resize primitive: `grep -n "def resize_rect_item_keeping_anchor" -A 20 src/open_garden_planner/ui/canvas/items/resize_handle.py`
- DXF Y handling: `grep -n "def _y" -A 4 src/open_garden_planner/services/dxf_service.py`
- Render flip recipe: `sed -n '179,189p' src/open_garden_planner/services/scene_rendering.py`
- Serializer centre convention: `grep -n "center_x" src/open_garden_planner/core/project.py | head`
- Constraint-type count (expect 17): `awk '/^class ConstraintType/{f=1;next} /^class /{f=0} f&&/^    [A-Z_]+ *[=(]/{c++} END{print c}' src/open_garden_planner/core/constraints.py`; Newton skip list: `grep -n "ConstraintType.PARALLEL" -A 4 src/open_garden_planner/core/constraint_solver_newton.py`
