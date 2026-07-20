# 12. Glossary

## 12.1 Terms

| Term | Definition |
|------|-----------|
| **arc42** | Template for software architecture documentation (12 sections) |
| **Canvas** | The main drawing area where garden objects are placed and manipulated |
| **Canopy Diameter** | The spread/width of a tree or shrub's foliage when viewed from above |
| **Amendment** | Soil-improving substance (lime, blood meal, compost, etc.) loaded from `resources/data/amendments.json`. Carries application rate (g/m²) and per-fix effect coefficients used by the calculator |
| **Bundled Species DB** | Curated `resources/data/plant_species.json` shipped with the app (~120 records covering every gallery thumbnail, full pH/NPK/sun/water/calendar fields per species). Looked up on canvas drop and tool draw by scientific name → common name → alias to auto-populate `metadata["plant_species"]`; the long tail still falls through to the on-demand API search (issue #170) |
| **AmendmentRecommendation** | Calculator output for one substance applied to one bed: amendment + grams + rationale (e.g. "Raises pH 5.8 → 6.5") |
| **Calibration** | The process of marking a known distance on an image to establish metric scale |
| **Command Pattern** | Design pattern where every modification is wrapped in an object with execute/undo methods |
| **Garden Bed** | A defined planting area (polygon) that can contain plant objects |
| **GardenObject** | Base class for all drawable entities on the canvas |
| **Layer** | A logical grouping of objects for organization and visibility control |
| **LOD** | Level of Detail — rendering different detail levels at different zoom levels |
| **NPK** | Macronutrients tracked in soil tests: Nitrogen (N), Phosphorus (P), Potassium (K) |
| **OGP** | Open Garden Planner (the application) |
| **.ogp** | Project file format (JSON-based) |
| **Object Snap** | Automatic snapping of new/moved objects to edges/vertices of existing objects |
| **Plant Type** | Category of plant: tree, shrub, perennial, annual, ground cover |
| **Polyline** | A connected series of line segments (open path) used for fences, paths, walls |
| **QGraphicsScene** | Qt class that manages all 2D items on the canvas |
| **QGraphicsView** | Qt class that provides the viewport/widget for displaying the scene |
| **Rapitest scale** | Categorical NPK / Ca-Mg-S labels (Depleted/Deficient/Adequate/Sufficient/Surplus and Low/Medium/High) used by consumer soil test kits and stored on `SoilTestRecord` |
| **Scene Coordinates** | Real-world metric coordinates used internally (centimeters) |
| **Seed Gap** | A species placed on the canvas that has no matching packet in `ProjectData.seed_inventory` — surfaces as a row in the Shopping List Seeds category |
| **Shopping List** | Aggregated buying list (Plants / Seeds / Materials) produced from the current plan; only user-entered prices persist with the project, the rows themselves are recomputed on each open |
| **ShoppingListItem** | One purchasable row: stable ID (e.g. `plant:<species_id>`), category, name, quantity, unit, optional price |
| **ShoppingListCategory** | Top-level group in the shopping list: `PLANTS`, `SEEDS`, or `MATERIALS` |
| **SoilTestRecord** | Single soil test entry: date, pH, NPK levels, secondary nutrients, optional ppm values, notes, optional soil texture |
| **SoilTestHistory** | Time-ordered list of `SoilTestRecord`s for one target (a bed UUID or `"global"` default) |
| **Smart composition** | US-12.11 calculator policy: each pick fully closes its primary nutrient deficit and credits all co-fixed nutrients at the same dose factor; greedy by breadth (count of outstanding deficits the substance touches), with organic-preferred and JSON-order tie-breakers |
| **Structural amendment** | Substance added to fix soil texture rather than nutrient levels — sand (drainage), perlite (aeration + drainage), vermiculite (water retention + aeration + CEC), diatomaceous earth (water retention + silica). Driven by `SoilTestRecord.soil_texture` |
| **Soil texture** | Optional `SoilTestRecord` field — `"sandy"`, `"loamy"`, `"clayey"`, or `"compacted"` (or `None`). Drives the structural-pick phase of the calculator |
| **Enabled set / Amendment library** | Per-project allowlist (`ProjectData.enabled_amendments`) of substance IDs the calculator may pick from. `None` (the default) means every bundled amendment is enabled; the user manages the allowlist via the checkbox panel inside the Amendment Plan dialog |
| **Garden Journal** | Free-standing, map-linked notes pinned to canvas locations. Each entry carries a date, plain text, optional photo, and scene coordinates (`JournalNote` in `models/journal_note.py`); the dedicated sidebar panel supports text search and date-range filtering |
| **Journal Pin** | The constant-screen-size `JournalPinItem` marker dropped on the canvas. Carries only the `note_id` reference; the note body lives in `ProjectData.garden_journal_notes` keyed by that id |
| **Screen Coordinates** | Pixel coordinates on the display; converted via QGraphicsView transform |
| **SVG** | Scalable Vector Graphics — vector image format used for icons and plant illustrations |
| **Tileable Texture** | A small image that can be seamlessly repeated to fill any area |
| **tr()** | Qt translation function used to mark strings for internationalization |
| **Relative coordinate input** | Typed point of the form `@dx,dy` interpreted relative to the active tool's `last_point`. Y is math-positive (up); the parser flips to scene-down. Empty anchor → input rejected. See ADR-021 |
| **Polar coordinate input** | Typed point of the form `@dist<angle` with angle in degrees, `0° = east`, CCW positive. `dist` and `angle` accept either decimal mark. Without an `@`, polar input is still interpreted as relative to `last_point`. An anchor is mandatory: without `last_point` the parser raises `ParseError` instead of silently falling back to the origin. See ADR-021 |
| **Dynamic Input** | The frameless distance/angle overlay that floats next to the cursor in the canvas viewport during multi-click drawing. Mirrors the same `CoordinateInputBuffer` as the status-bar field. Hidden when the active tool has no anchor point. See ADR-021 |
| **CoordinateInputBuffer** | `QObject` singleton (per CanvasView) that holds the typed coordinate text and the current anchor. Both the status-bar field and the Dynamic Input overlay subscribe to its signals; this single state prevents the two UI surfaces from drifting out of sync |
| **SnapProvider** | One snap mode (endpoint, center, edge, midpoint, intersection). Subclass of `core/snap/provider.SnapProvider`; yields `SnapCandidate`s for items near a query position. Activation toggled via the View menu and persisted in `AppSettings`. See ADR-020 |
| **SnapCandidate** | One potential snap point produced by a provider. Carries the point, the kind, a priority (lower wins on ties) and the source item |
| **SnapRegistry** | Collection of active `SnapProvider`s with priority-based tie-breaking. Owned by `CanvasView`; its content is driven by the View menu toggles |
| **PointSnapper** | Click-time entry point that combines the `SnapRegistry` with the quadtree spatial index. `CanvasView._maybe_apply_anchor_snap` calls it before every non-select tool mouse event |
| **Midpoint snap** | Snap to the midpoint of any straight edge from a rectangle, polygon, polyline or construction line. Glyph: filled green triangle |
| **Intersection snap** | Snap to the intersection of two straight edges from different items. Glyph: green X. Capped at 60 segments per query for predictable latency |
| **QuadTree (snap)** | Bounded-depth (max 6) spatial index built lazily on `QGraphicsScene.changed`; pre-filters items to a 4×threshold window around the cursor before providers run. Build < 60 ms / 1000 items, query < 1 ms |
| **Arc (3-point)** | Circular arc constructed from start + through-point + end via the circumcenter formula in `core/cad_geometry.arc_from_three_points`. Stored as `ArcItem` with `center`, `radius`, `start_deg`, `span_deg` (math convention — CCW from +X). Collinear inputs fall back to a 2-vertex polyline. See ADR-022 |
| **Cubic Bezier** | Smooth curve item with two handles per anchor (`handles_in[i]`, `handles_out[i]`). Authored via a pen tool (`B`), edited by dragging anchor or handle widgets. Single curve model in the app — quadratic / NURBS variants are out of scope. See ADR-022 |
| **Fillet** | Round a corner with a tangent arc. Tangent points sit at distance `r/tan(α)` along each adjacent edge; the arc center is on the bisector at `r/sin(α)`. Applied to a polyline / polygon vertex in place; rectangle fillet is a destructive rect → polygon conversion (undo restores the rect). See ADR-022 |
| **Chamfer** | Bevel a corner with a straight cut at distance `d` along each adjacent edge. Same picking + persistence model as Fillet, but no arc is created. See ADR-022 |
| **Mirror (tool)** | Modify tool (`Shift+M`) that reflects the selected shapes across a two-click **reflection axis**, in **Copy** (keep originals) or **Move** (replace, preserving `item_id` so constraints stay bound) mode. Reflects by rebuilding each item (`core/mirror_geometry.build_mirrored_item`), so SVG glyphs render un-flipped. Distinct from the **Symmetry constraint** (a persistent relationship). See ADR-026 |
| **Reflection axis** | The user-defined line (two clicks) the Mirror tool reflects across. Hold **Shift** while picking the end to constrain it to 0/45/90°. |
| **Nearest snap** | Fallback snap mode (priority 45, lowest) that yields the closest point on any visible edge or curve to the cursor. Default off. Glyph: hourglass. See ADR-023 |
| **Perpendicular snap** | Foot of perpendicular from the active tool's `last_point` to the nearest straight edge. Requires a reference anchor; pure-cursor perpendicular has no meaning. Priority 25. Glyph: ⊥. See ADR-023 |
| **Tangent snap** | Contact point of a line from `last_point` to a circle/arc's tangent (`α = acos(r/|RC|)`). Two solutions exist for an external point; cursor disambiguates. Priority 26. Glyph: small circle + tangent line. See ADR-023 |
| **Reference point (snap)** | Optional `QPointF` passed to `SnapProvider.candidates()` that names the active tool's anchor (`last_point`). Required by perpendicular and tangent snaps; ignored by the older providers. See ADR-023 |
| **Auto-constraint emit** | Turning a snapped drawing-tool vertex into a durable `ConstraintGraph` entry (`core/auto_constraint.emit_for_polyline`). The snap kind picks the constraint: NEAREST/PERPENDICULAR → POINT_ON_EDGE, MIDPOINT → COINCIDENT, NEAREST-on-circle → POINT_ON_CIRCLE, TANGENT → POINT_ON_CIRCLE + TANGENT. The edge is named via `SnapCandidate.source_edge_index`, resolved to anchors by matching `get_anchor_points`. See ADR-024 |
| **Tangent constraint** | `ConstraintType.TANGENT`: the edge `anchor_a`→`anchor_c` is perpendicular to the radius `anchor_b − anchor_a` (residual = radius projected onto the edge, `(C−v1)·(v0−v1)/\|edge\|`, → 0). Always emitted *with* a `POINT_ON_CIRCLE` companion (which pins the radial distance); the pair is non-degenerate (edge-aligned gradient ⟂ radial gradient) so the contact stays welded to the rim AND tangent under drag. `target_distance` holds the radius for display only. Enforced actively in Gauss-Seidel (translate along the edge) + Newton backup. See ADR-024 |
| **Curve control handle** | A draggable widget (`CurveControlHandle`) shown on a selected `BezierItem`/`ArcItem` for in-place reshaping (`CurveEditMixin`). Bezier: on-curve anchor handles (carry their tangents) + tangent handles (smooth-mirror by default, Alt = corner). Arc: start / through / end handles + a read-only centre marker. Each drag = one `SetCurveGeometryCommand` undo step. Distinct from the polygon/polyline `VertexHandle` (which also inserts/deletes vertices). See ADR-025 |
| **Through-point (arc)** | A point the arc passes through between its endpoints — the 3rd click ("bulge") of the start→end→bulge arc tool. Stored on `ArcItem` (`_through`, persisted as `through_x`/`through_y`; legacy files derive the angular midpoint) as the third degree of freedom held fixed while dragging an endpoint, and itself draggable to change curvature. See ADR-025 |
| **arc_to_painter_path** | Builds an arc's `QPainterPath` from exact cubic-Bézier segments (≤45° each, anchors placed analytically on the circle, control factor `k=4/3·tan(Δ/4)`). Replaces Qt's `arcMoveTo`/`arcTo`, whose rendered endpoints drift on shallow large-radius arcs (issue #195). Used by `ArcItem` and the arc-tool preview. See ADR-025 |
| **render_scene_region** | Shared scene-region renderer in `services/scene_rendering.py`. Hides selection / construction / soil-badge overlays, optionally rescales text, paints `source_rect` of a scene into `target_rect` on any painter, applies the standard Y-flip, and restores everything afterwards. Currently used by PNG export; SVG export + print dialog migration is tracked as follow-up |
| **Manual task** | A user-created reminder (`ManualTask` in `models/task.py`): date, title, notes, optional linked bed. Created/edited via `TaskDialog`, persisted under the additive `.ogp` key `manual_tasks`, and undoable. Shown on the Tasks tab alongside the auto-generated tasks. See ADR-029 |
| **Task state** | The stored raw status of one task keyed by `task_id` (`task_states` in the `.ogp` file): open / snoozed (until a date) / done (on a date) / dismissed. Written at both write chokepoints (`set_task_status`, `set_task_completion`), which also keep the legacy `task_completions` done-set in sync. See ADR-029 |
| **Task generator** | One of six pure, Qt-free `(PlanState) -> list[Task]` functions in `services/task_generator.py` — planting-calendar windows, propagation, succession sow/clear, soil amendments, frost protection, manual tasks. `generate_all` flat-maps and dedups by `task_id`. Pure so they unit-test without a running app. See ADR-029 |
| **Effective status** | The render-time status of a task computed by `services/task_status.effective_status` from its stored `Task state` and "today": open / snoozed / done / dismissed / archived. No background scheduler — an expired snooze reads as open and a task done > 7 days ago reads as archived (done-then-archive window) on the next render. See ADR-029 |
| **Harvest log** | Per-target (plant/bed) yield records (`HarvestRecord`/`HarvestHistory` in `models/harvest_log.py`): date, quantity, unit, quality, notes, optional photo. Persisted under the additive `.ogp` key `harvest_logs` keyed by item UUID; each history caches `species_key` + `species_name` so totals resolve even after the plant is deleted. Add/Edit/Delete are undoable and auto-maintain a pin-less `harvest`-tagged journal note. See FR-23 (US-C1) |
| **Harvest aggregation** | The pure, Qt-free `services/harvest_aggregation.aggregate_by_species_year` that rolls `harvest_logs` into per-species, per-year, per-unit totals for the garden-wide **Harvest** dashboard tab, CSV export, and PDF summary page. Groups by `(species, year, unit)` — quantities in different units are never summed |
| **MCP (Model Context Protocol)** | Open protocol for exposing tools, resources, and prompts to AI agents/LLM clients. Open Garden Planner embeds an **MCP server over streamable-HTTP** (mcp Python SDK) so agents can read the open plan. See ADR-033, §8.19 |
| **Agent API** | The `agent_api/` subsystem: a default-on, loopback-only embedded MCP server (epic #237, US-D1.1) that a Preferences toggle can disable. Reads are open (loopback trust); scene-mutating **write tools** are opt-in + token-gated (US-D2.0). See FR-26 |
| **Agent write token** | The bearer token (`agent_api_token`, auto-generated `secrets.token_urlsafe(32)`) an MCP client must send as `Authorization: Bearer <token>` to call the Agent API's write tools. Required only for writes (reads stay open); paired with the off-by-default "Allow AI assistants to edit the plan" toggle. Surfaced (Copy/Regenerate) in Preferences → Agent API and injected into client configs by the Connect dialog. See ADR-036, §8.19 |
| **Agent write tool** | An MCP tool that mutates the live plan (US-D2.0: `move_object`, `delete_object`). Registered only when editing is enabled AND a token is set; each applies exactly one undoable command via `command_manager.execute` (one agent write = one Ctrl+Z step). See FR-AGENT-13, ADR-036 |
| **MainThreadBridge** | The thread-marshaling boundary (`agent_api/bridge.py`): runs a callable on the Qt main thread from the server's worker thread via a queued signal + `Future`, returning the result/exception. `abort_pending()` releases in-flight calls on shutdown. The reusable write-ready core. See ADR-033 |
| **Curated agent schema** | The stable pydantic contract (`agent_api/schema.py`, e.g. `PlanSummary`) the Agent API returns to clients — decoupled from the `.ogp` save format / `FILE_VERSION` so agent integrations don't break on format changes. Built from `ProjectManager.snapshot_dict` by the Qt-free `agent_api/mapping.py`. See ADR-034 |
| **snapshot_dict** | `ProjectManager.snapshot_dict(scene)` — an in-memory, read-only `.ogp`-shaped dict (plus an `agent_meta` block) used by the Agent API. Unlike `save()`, it does NOT reconcile journal-pin positions, so reading the plan never mutates state |
| **Azimuth** | Compass bearing of the sun, degrees clockwise from true north (N=0, E=90, S=180, W=270). Computed by `core/solar.py` (US-E1) |
| **Elevation angle (solar)** | The sun's angle above the horizon (α). Geometric (airless) by default; shadow features use the geometric value. `elevation_refracted_deg` carries the NOAA refraction correction |
| **Declination (δ)** | Angle of the sun above/below Earth's equatorial plane; ranges ±23.44° over the year (the axial tilt) |
| **Equation of time (EoT)** | True solar time minus mean clock time, in minutes; ranges about −14.2 … +16.4 min over the year |
| **Hour angle (H)** | How far the sun is past local solar noon, 15°/hour, negative in the morning, 0 at solar noon |
| **Solar noon** | The instant the sun crosses the local meridian (hour angle 0) — its highest point of the day; due south in northern mid-latitudes |
| **Effective height** | An object's resolved above-ground height in cm (`core/object_height.py`, US-E2): explicit `object_height_cm` metadata → container fill height → species `max_height_cm` → per-type default → none. Drives shadow casting (US-E3) and 3D extrusion (US-E6). Distinct from a container's *fill* height, which keeps driving soil volume |
| **Shadow length** | `L = h / tan α` — the ground shadow length of an object of effective height *h* under geometric sun elevation α, on the v2.0 flat-ground assumption (`core/shadow_geometry.py`, US-E3). Below α = 0.5° no shadow is drawn (lengths explode near the horizon) |
| **Sun & shade simulation** | The runtime-only canvas overlay (US-E3) painting the union of all object shadows for a simulated date/time at the project's location. Distinct from the cosmetic per-item drop shadows ("Show Shadows", `appearance/show_shadows`) |

## 12.2 Keyboard Shortcuts

| Action | Shortcut |
|--------|----------|
| New Project | Ctrl+N |
| Open Project | Ctrl+O |
| Save | Ctrl+S |
| Save As | Ctrl+Shift+S |
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Select All | Ctrl+A |
| Delete | Delete |
| Duplicate | Ctrl+D |
| Copy | Ctrl+C |
| Paste | Ctrl+V |
| Zoom In | Ctrl++ or Scroll Up |
| Zoom Out | Ctrl+- or Scroll Down |
| Fit to View | Ctrl+0 |
| Toggle Grid | G |
| Toggle Snap | S |
| Select Tool | V |
| Rectangle Tool | R |
| Polygon Tool | P |
| Line Tool | L |
| Measure Tool | M |
| Plant Tool | T |
| Fullscreen Preview | F11 |
| Print | Ctrl+P |
| Garden Plan tab | Ctrl+1 |
| Planting Calendar tab | Ctrl+2 |
| Seed Inventory tab | Ctrl+3 |
| Tasks tab | Ctrl+5 |
| Harvest tab | Ctrl+6 |
| Bezier Tool | B |
| Arc Tool (3-point) | A |
| Fillet Tool | Shift+F |
| Chamfer Tool | Shift+C |
| Fillet — change radius (while active) | R |
| Chamfer — change distance (while active) | D |
| Mirror Tool | Shift+M |

## 12.3 References

- [arc42 Documentation Template](https://arc42.org/)
- [Trefle.io API Documentation](https://trefle.io/)
- [Permapeople API Documentation](https://permapeople.org/knowledgebase/api-docs.html)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [QGraphicsView Framework](https://doc.qt.io/qt-6/qgraphicsview.html)
- [Qt Linguist Manual](https://doc.qt.io/qt-6/qtlinguist-index.html)
- [NSIS Documentation](https://nsis.sourceforge.io/Docs/)
- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
