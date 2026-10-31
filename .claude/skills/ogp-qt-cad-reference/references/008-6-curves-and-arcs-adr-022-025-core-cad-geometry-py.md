## 6. Curves and arcs (ADR-022/025, `core/cad_geometry.py`)

The Qt-free geometry kernel is `src/open_garden_planner/core/cad_geometry.py`.
Verified contents: `point_to_segment_distance`, `segment_segment_intersection`,
`collect_intersections_on_segment`, `polyline/polygon/rectangle_to_scene_segments`,
`arc_from_three_points`, `arc_to_painter_path`, `sample_arc_points`,
`fillet_corner`, `chamfer_corner`, `reflect_point`, `reflect_angle_deg`,
`snap_point_to_axis_step`.

- **Cubic Bezier is the single curve model** (ADR-022). Each anchor stores
  `handles_in[i]` + `handles_out[i]`; segment i→i+1 renders as
  `path.cubicTo(handles_out[i], handles_in[i+1], anchors[i+1])`. Authoring is
  Illustrator-style click-drag with the mirror-handle smooth default. Item:
  `ui/canvas/items/bezier_item.py`; undoable mutations in `core/commands.py`.
- **3-point arc** (`arc_from_three_points`): circumcenter via the signed-area
  determinant (`d > 0` = the three points wind CCW); collinear (|d| below
  epsilon) → caller falls back to a polyline. Returns
  `(center, radius, start_deg, span_deg)` with angles in **degrees CCW from
  +X, span signed (positive CCW)** — math convention, documented per function.
- **Exact arc rendering** (ADR-025): Qt's `arcTo` drifted rendered endpoints
  up to 0.24 cm on shallow large-radius arcs, so arcs are rendered from exact
  cubic segments instead: `arc_to_painter_path` splits the span into ≤45°
  segments, anchors placed exactly on the analytic circle, control points
  along tangents scaled by `k = 4/3·tan(Δ/4)` (signed for CW spans). Snapping
  never reads the path — only analytic `center`/`radius`.
- **Arc reshape** needs a stable third degree of freedom: `ArcItem` stores its
  through-point, persisted as *additive* `through_x`/`through_y` keys (older
  files derive the angular midpoint on load; `FILE_VERSION` stayed 1.4).
- **Fillet/chamfer** (`fillet_corner` / `chamfer_corner`): polylines and
  polygons mutate in place. The fillet's tangent arc is **sampled into the
  host's own vertex list** (`sample_arc_points`, max chord deviation
  `FILLET_ARC_TOLERANCE_CM = 0.02 cm`), so the rounded corner is one item that
  moves/groups/saves/undoes with the shape — the old free-standing `ArcItem`
  stayed behind when the host moved (ADR-022 addendum 2026-10-31). **Rectangles
  have no per-corner geometry slot**, so editing one is a *destructive, undoable
  conversion*: `RectangleItem` → `PolygonItem`; undo restores the original rect;
  past the undo horizon the polygon stays a polygon. The replacement takes its
  source's polygonal type (raised bed → garden bed, generic rectangle → generic
  polygon, hedge section → hedge polygon); types with no polygonal form
  (furniture, containers, trellis) are refused. Only the edited vertex and its
  two incident edges block a constraint; later anchors renumber in the command.
- Curve editing uses a dedicated `CurveEditMixin` + `CurveControlHandle`
  (selection-driven, keyed on `self.isSelected()`), not the polygon
  `VertexHandle`; undo is a whole-geometry snapshot
  (`SetCurveGeometryCommand`), one command per drag (ADR-025).

---

