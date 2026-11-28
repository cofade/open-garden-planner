---
title: "Precision"
prefixes: ["FR-SNAP", "FR-INPUT", "FR-REF", "FR-MEAS"]
---

# Precision

## Snapping and alignment

- **FR-SNAP-01**: Snap to object edges and centers, with visual guide lines. Both moving selections and targets use geometric object frames; spacing rings, badges and other paint overflow do not move anchors (#841).
- **FR-SNAP-02**: Align left, right, top, bottom, horizontal center and vertical center using geometric object frames, including rotated items and group members; diagnostic decorations have no effect (#841).
- **FR-SNAP-03**: Distribute horizontally or vertically by geometric frame centers, independently of diagnostic paint (#841).
- **FR-SNAP-04** (US-A3): Midpoint snap — yields the midpoint of every straight edge from rectangles, polygons, polylines and construction lines near the cursor. Toggle in View menu → "Snap to Midpoints"; persisted via `AppSettings.midpoint_snap_enabled` (default on). Visual glyph: filled green triangle.
- **FR-SNAP-05** (US-A3): Intersection snap — computes pairwise segment-segment intersections between edges of items near the cursor, capped at 60 segments per query for predictable latency. Self-intersections within a single item are filtered out to avoid duplicating endpoint mode at polygon vertices. Toggle in View menu → "Snap to Intersections"; persisted via `AppSettings.intersection_snap_enabled` (default on). Visual glyph: green X.
- **FR-SNAP-06**: Snap engine performance — a 1000-item scene snaps under 16 ms per query (60 fps budget); enforced by `tests/unit/test_point_snapper.py::test_perf_end_to_end`. The quadtree pre-filter rebuild is guarded by a warm-up plus five repeated samples in `tests/unit/test_snap_spatial_index.py::test_perf_thousand_items`: the **median** build must be below 200 ms and the median of five 100-query batches below 1 ms. This is a shared-runner regression guard, not a claim that a single wall-clock sample is 200 ms: the historical Python 3.11/Linux single-sample outlier was 284 ms, while repeated local Python 3.12/Windows samples were approximately 15 ms. The median rejects a sustained regression while absorbing an isolated scheduler spike; the platform assumptions and evidence are recorded in ADR-020's #354 addendum.
- **FR-SNAP-07** (US-B4): Nearest snap — yields the closest point on any visible edge or curve to the cursor as a fallback below all other snap modes. Priority 45 (lowest), default off (avoids surprising users who rely on free placement near edges). Toggle in View menu → "Snap to Nearest Point"; persisted via `AppSettings.nearest_snap_enabled`. Visual glyph: hourglass.
- **FR-SNAP-08** (US-B5): Perpendicular snap — drops a foot from the active tool's `last_point` onto the nearest straight edge in range. Requires a `reference_point` (no candidate without an anchor — purely cursor-based perpendicular is meaningless). Priority 25. Default off. Toggle in View menu → "Snap Perpendicular"; persisted via `AppSettings.perpendicular_snap_enabled`. Visual glyph: ⊥.
- **FR-SNAP-09** (US-B6): Tangent snap — from the active tool's `last_point` to a circle or arc, computes the contact point of the tangent line via `α = acos(r/|RC|)`. Returns the tangent point closer to the cursor when both solutions are visible. Reference points inside the circle or at the center yield no candidates. For arcs, candidates are filtered to those lying within the arc's sweep. Priority 26. Default off. Toggle in View menu → "Snap Tangent"; persisted via `AppSettings.tangent_snap_enabled`. Visual glyph: small circle + tangent line.
- **FR-SNAP-10** (issues #196/#192/#197): Snap → durable constraint. When a drawing tool commits a vertex at a snapped point, the snap becomes a geometric constraint stored on the scene's `ConstraintGraph` (via the undoable `AddConstraintCommand`): NEAREST/PERPENDICULAR on a straight edge → `POINT_ON_EDGE` (the vertex rides that named edge); MIDPOINT → `COINCIDENT` (vertex pinned to the edge midpoint); NEAREST on a circle/arc → `POINT_ON_CIRCLE`; TANGENT on a circle/arc → `POINT_ON_CIRCLE` + the new `TANGENT` constraint (TANGENT = edge⟂radius; the pair welds the contact to the rim *and* keeps the edge tangent, robustly under drag — see ADR-024). The source edge is identified by `SnapCandidate.source_edge_index` and resolved to concrete anchors by matching `get_anchor_points(source)`. Emitted constraints are enforced by the existing drag pipeline: dragging the reference item drags the constrained vertex along (`_compute_constraint_propagation`), and dragging the constrained item keeps its vertex on the edge/circle (`_enforce_point_on_edge_positions`). A perpendicular snap intentionally emits `POINT_ON_EDGE` rather than the rotation-only `PERPENDICULAR` type (see ADR-024).
- **FR-SNAP-11**: Snap toggleable independently from grid snap
- **FR-SNAP-12**: Visual snap guide lines during drag operations

## Typed coordinate input

- **FR-INPUT-01** (US-A1): Relative coordinate input `@dx,dy` types a vertex at `(last_point.x + dx, last_point.y − dy)`. The Y-flip implements math convention (`+dy` = up on screen). Available on every multi-click drawing tool (polyline, polygon, rectangle, circle, ellipse, construction line, construction circle) via the status-bar field and the Dynamic Input overlay. Without an anchor point, relative input is rejected with an inline red error tint *and* the parser's diagnostic surfaces in the field's tooltip (e.g. "Relative input requires an existing point to anchor to"); the diagnostic clears on the next keystroke or successful commit.
- **FR-INPUT-02** (US-A2): Polar coordinate input `@dist<angle` (degrees, `0° = east`, CCW positive) types a vertex at `last_point + (dist·cos θ, −dist·sin θ)`. Polar input without a `@` prefix is also accepted and treated as relative to the last point. Polar input requires exactly one `<`. Without an active `last_point` the parser raises `ParseError` (no silent fallback to origin).
- **FR-INPUT-03** (US-A4): Dynamic Input overlay — a frameless distance/angle entry follows the cursor inside the canvas viewport. Visible only when (a) dynamic input is enabled in the View menu, (b) the active tool is not SELECT, and (c) the active tool has a `last_point` to anchor against. Tab cycles fields, Enter commits, Esc returns focus to the canvas. The overlay and the status-bar field mirror a single `CoordinateInputBuffer` per CanvasView; typing in one updates the other live.
- **FR-INPUT-04**: Smart decimal/separator handling (rules A–F in `parser.py`): `;` is always a field separator, mixed `.`/`,` resolves to `.` decimal + `,` separator, comma-only inputs disambiguate by count (1 → separator, 3 → locale decimal pair, 2 → ambiguous with locale-decimal preference and `parse_alternative()` exposing the secondary reading). Whitespace also works as a separator everywhere.

## Reference points

- **FR-REF-01**: The Reference point tool places a named point at a clicked coordinate.
  The point is the ordinary `GENERIC_CIRCLE` record with `metadata.reference_point =
  true`; older versions read it as a small circle and no `FILE_VERSION` bump is needed.
- **FR-REF-02**: The exact centre is `item.pos()` and `rect()` is centred on it. A
  reference point exposes exactly one snap/measure anchor, `CENTER` at that coordinate;
  its halo arms are never snap targets.
- **FR-REF-03**: A point is independent or bound to a parent's outline through
  `reference_point_parent_id` and `reference_point_on_contour`. A bound point is
  projected onto the nearest straight parent edge when placed or moved, and an
  off-contour move is refused; "Independent point" in the dialog is the explicit
  detach. Parent translation moves the point in the same undo step; parent rotation or
  vertex edits do not move an existing point.
- **FR-REF-04**: The symbol is fixed in the plan (default 6 cm, scales with zoom) or
  constant on screen (default 16 px). Colour and cosmetic stroke width are editable.
  The symbol is a target/cross with a solid centre dot.
- **FR-REF-05**: Placement and every edit are exactly one undo step, and moving a
  parent carries its attached points in that same step. Layer, lock, copy/duplicate,
  delete and save/reload follow the ordinary object rules. A reference point has no
  3D form.
- **FR-REF-06**: Every user-visible string is complete in every registered locale
  (en/de/es/ru/fr).

## Measurement and units

- **FR-MEAS-01**: Distance tool: click two points, displays distance in the global unit system (FR-MEAS-07).
- **FR-MEAS-02**: Persistent dimension annotations (add to plan, editable)
- **FR-MEAS-03**: Area display for selected polygon and circle objects
- **FR-MEAS-04**: Perimeter/circumference display for selected objects
- **FR-MEAS-05**: Scale bar overlay (Phase 6)
- **FR-MEAS-06**: Measurements snap to object vertices/edges
- **FR-MEAS-07**: Preferences offers Metric (default) and Imperial (US). Switching updates layout lengths, plant sizes, seed depth, area and real container volume without reopening the plan. Imperial layout uses feet and eighth-inches, plants whole inches, depth fractional inches, area in²/ft², volume US qt/gal. Input accepts explicit units and either decimal mark; bare imperial entries mean inches, or feet in fields whose metric value unit is metres. Switching or viewing rounded text creates no model edit. Scene values, saved geometry, Agent API units and DXF export retain centimetres (issue #673; ADR-078). Temperature, precipitation, harvest mass and the Canadian preset follow FR-MEAS-08 to FR-MEAS-10 (#907).
- **FR-MEAS-08**: The unit profile is per quantity: **length** (and the canvas), **area**, **volume**, **temperature**, **precipitation** and **harvest mass** each follow Metric or Imperial independently. Preferences offers the presets **Metric**, **Imperial (US)**, **Canada (mixed)** and **Custom**; choosing a single quantity row makes the profile Custom. The legacy `units/system` setting still reads as one system for every quantity; the profile is stored additively in `units/profile` and the six `units/<quantity>` keys, and a plan file never stores a display unit.
- **FR-MEAS-09**: Temperature is stored and computed in Celsius and displayed in °C or °F; precipitation is stored in millimetres and displayed in mm or in (at least two decimals, so a drizzle is not `0.0 in`); a new harvest entry offers kg or lb from the mass profile, while each saved harvest record keeps the unit it was entered in and that unit remains its aggregation key (totals never mix units; ADR-081). Weather panels, frost-alert thresholds, germination temperatures, generated frost-task titles and the harvest entry's default unit follow the profile, in the UI language's number format. Temperature fields accept an explicit °C/°F unit in either system (with bare entries using the active system); `core.units` also provides explicit-unit parsers (`parse_precipitation`, `parse_mass`) for precipitation and mass. A live switch refreshes all display surfaces (including canvas/3D area readouts, status bar, weather and calendar dashboard) without reopening the plan.
- **FR-MEAS-10**: **Canada (mixed)** is the recorded provisional preset: length and area imperial (feet/inches, ft²), volume, temperature, precipitation and harvest mass metric. Changing any row makes a Custom profile. Its defaults are revisited when Canadian users' feedback is available (ADR-081).
