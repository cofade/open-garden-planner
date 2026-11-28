---
title: "Drawing and editing"
prefixes: ["FR-DRAW", "FR-EDIT", "FR-SPLIT", "FR-DRILL", "FR-GROUP", "FR-TOOL-ESC"]
---

# Drawing and editing

## Drawing tools and shape properties

- **FR-DRAW-01**: Line tool (click-click or click-drag)
- **FR-DRAW-02**: Rectangle tool (axis-aligned and rotated)
- **FR-DRAW-03**: Polygon tool (click to add vertices, double-click/Enter to close)
- **FR-DRAW-04**: Circle tool (click center, then click rim point to define radius)
- **FR-DRAW-05**: Ellipse tool (shipped in Phase 13 Package B, v1.12.0; PR #191)
- **FR-DRAW-06**: Arc tool
- **FR-DRAW-07**: Polyline tool (connected line segments, open path)
- **FR-DRAW-08** (US-B1): Cubic Bezier pen tool. Click-drag per anchor — drag direction sets the outgoing handle; the incoming handle is mirrored automatically for a smooth tangent default. Double-click or Enter commits the curve. ESC cancels. A placed curve is reshaped in place via control handles (see FR-EDIT-12). Shortcut: `B`.
- **FR-DRAW-09** (US-B2): 3-point arc tool. Click **start → end → bulge** — the 2nd click sets the arc's end and the 3rd sets the curvature (the point the arc bulges through). The unique circular arc through the three points is computed via the circumcenter (`core/cad_geometry.arc_from_three_points`) and rendered as an `ArcItem`. (Click order chosen per manual-test feedback on #195: users fix the span first, then dial in curvature, rather than the classic start→through→end order.) The arc is rendered from exact cubic-Bézier segments (`arc_to_painter_path`), so the drawn curve terminates precisely on the user's clicks at any radius — Qt's `arcTo` could otherwise drift the rendered end by millimetres on a shallow, large-radius arc (FR-EDIT-13, ADR-025). If the three points are collinear (twice the signed triangle area ≤ 1.0), the tool falls back to a 2-vertex polyline (start→end) and a status-bar note. Shortcut: `A`.
- **FR-DRAW-10**: Fill color (solid colors, predefined palette, custom color picker)
- **FR-DRAW-11**: Fill pattern/texture (grass, gravel, concrete, wood, water, soil, mulch)
- **FR-DRAW-12**: Stroke color and width
- **FR-DRAW-13**: Stroke style (solid, dashed, dotted)
- **FR-DRAW-14**: Opacity per shape

## Editing operations

- **FR-EDIT-01**: Select tool (click, box select, Shift+click for multi-select)
- **FR-EDIT-02**: Move objects (drag or arrow keys with Shift for precision)
- **FR-EDIT-03**: Rotate objects (free rotation and snap to 15 degree increments)
- **FR-EDIT-04**: Resize handles sit on the object outline, excluding paint decorations. A single logical edit target shows eight handles when both local axes span at least 32 screen pixels, four corners from 16 pixels, and no resize handles below 16 pixels; zoom restores them. Multi-selection retains outlines without individual resize/rotation handles. A grabbed handle remains usable until release. The rotation handle keeps a 25-pixel gap after zoom, including group drill-down. A circle's position and diameter labels remain stacked beside its right edge (#790, #840).
- **FR-EDIT-05**: Delete objects (Delete key, context menu)
- **FR-EDIT-06**: Duplicate objects (Ctrl+D)
- **FR-EDIT-07**: Undo/Redo (Ctrl+Z, Ctrl+Y) with unlimited history per session
- **FR-EDIT-08**: Copy/Paste (Ctrl+C, Ctrl+V) including across projects
- **FR-EDIT-09**: Edit polygon vertices (add, remove, move individual points)
- **FR-EDIT-10** (US-B3, revised 2026-10-31): Fillet tool — round a polyline / polygon / rectangle corner with a tangent arc. The picked corner vertex is replaced in the SAME item by the two tangent points (at distance `r/tan(α)` along each edge from the corner) plus an arc sampled between them (`cad_geometry.sample_arc_points`; maximum chord deviation `FILLET_ARC_TOLERANCE_CM = 0.02 cm`). The rounded corner therefore moves, groups, saves, deletes and undoes with its host; the old free-standing `ArcItem` stayed behind when the host moved and left the fill as a straight chamfer (owner manual test 2026-10-31). The most-recently-used radius persists in `AppSettings.fillet_last_radius_cm`; press `R` mid-session to change it. If the radius is too large for the corner (offset > either edge length) the click is ignored with a status-bar hint. Shortcut: `Shift+F`. Filleting a rectangle is a **destructive conversion** (rect → polygon); a raised bed becomes a **garden bed** polygon because its wooden frame has no polygonal form (adopting that type's soil fill pattern while keeping the bed's colour), and a type with no polygonal form (furniture, containers, trellis) is refused. A corner whose own vertex or incident edge carries a constraint is refused; constraints on other vertices/edges are renumbered. Undo restores the rectangle (ADR-022).
- **FR-EDIT-11** (US-B3, revised 2026-10-31): Chamfer tool — bevel a corner with a straight cut at distance `d` along each adjacent edge. Same picking + persistence model as Fillet (`AppSettings.chamfer_last_distance_cm`, press `D` to change). No arc is created — only the host item's vertex list changes. Rectangles convert to polygons just like fillet, with the same type mapping (raised bed → garden bed; types with no polygonal form are refused) and the same corner-scoped constraint refusal. Shortcut: `Shift+C`.
- **FR-EDIT-12** (US-B9, issue #193): In-place reshape of placed Bezier and Arc curves. Selecting a curve shows draggable control handles (`CurveEditMixin` + `CurveControlHandle`); deselecting hides them. *Bezier*: an on-curve handle per anchor (drag carries both tangent handles along) plus a tangent handle for each anchor's active control point — dragging a tangent mirrors the opposite one for a smooth (C1) join, **Alt** breaks it into a corner; endpoint anchors expose only their single live handle. *Arc*: start / through / end handles (any drag recomputes the 3-point arc, so the through-point changes curvature with endpoints fixed) plus a read-only centre marker; a drag that would make the points collinear is rejected. Each drag commits exactly one undo step (`SetCurveGeometryCommand`, geometry-snapshot). The arc persists its through-point (additive `through_x`/`through_y`; legacy files derive the angular midpoint) so handles round-trip through save/reload. Reshape only — adding/deleting anchors or arc control points is out of scope. (ADR-025.)
- **FR-EDIT-13** (US-B11, issue #195): 3-point arc endpoint precision — the rendered arc must terminate on the user's clicks within 1e-3 cm at any radius/sweep. Implemented by rendering arcs from exact cubic-Bézier segments rather than Qt's `arcMoveTo`/`arcTo` (see FR-DRAW-09, ADR-025). The fillet computes its tangent points and circle from the same analytic geometry and samples that circle into its host (FR-EDIT-10); it no longer creates an `ArcItem`.
- **FR-EDIT-14** (US-B4, issue #187): Mirror tool — reflect the selected shapes across a user-defined axis. Workflow: select shapes → `Shift+M` → click axis start → click axis end (**Shift** constrains the axis to 0/45/90°) → a small modal asks **Copy** (default) or **Move**. *Copy* adds reflected duplicates (fresh ids, so — like paste — copies start unconstrained) and keeps the originals; *Move* replaces the originals with reflections that keep their `item_id`, so existing constraints stay bound. Selecting a bed auto-includes its plants so they reflect with the bed. The reflected result is clamped back onto the canvas (shifted as a group) if the axis would push it off-bounds. One undo step per mirror (`MirrorItemsCommand`). Supported types: polyline, polygon, rectangle, ellipse, circle, arc, bezier — plus rectangle/circle-based SVG furniture & plants, which reflect *positionally* and render un-flipped (LibreCAD behaviour). Text, callouts, journal pins, construction geometry, background image, and groups are skipped with a status note. Geometry is reflected by rebuilding each item (not a Qt mirror transform), so results round-trip through save/load and DXF. Distinct from the Symmetry *constraint* (`CONSTRAINT_SYMMETRY`), which is a persistent relationship rather than a one-shot copy. (`core/mirror_geometry.py`, ADR-026.)
- **FR-EDIT-15** *(issue #530)*: Every property the **Properties panel** edits is **one undoable step** and marks the plan modified - a bed's grid on/off and grid spacing, a bed's soil depth, and a container's material, drainage, height and soil volume. A direct write into the item is neither undoable nor a mark of a modified plan: Ctrl+Z would undo the item's creation instead of the edit, and closing the app would ask nothing and lose it. An edit that changed nothing commits nothing, and a value that was never set is restored as **absent** again, not as `None`. Committed dropdown and checkbox choices follow undo/redo immediately while retaining focus and selection; refreshing them does not create another command.
- **FR-EDIT-16** *(issue #522)*: A Shift+click on a canvas object picks the first **selectable** item under the cursor. Interactive editing handles retain normal Qt press delivery, including Shift+press to begin a resize or rotation. A locked layer takes the selectable flag away from its items - and its items are still drawn and still hit - so the topmost item under the cursor may be one that cannot be selected. Shift+click toggles what lies behind it (the canvas's own rule: Shift adds or removes), and with nothing selectable beneath the click goes through as before, so a locked item with nothing behind it still clears the selection.
- **FR-EDIT-17** *(issue #552)*: A **FIXED** constraint pins an object for every move path, including the Properties panel X/Y fields - the panel refuses the edit, restores the pinned values and explains why instead of moving the object. The canvas right-click menu offers **Lock position** / **Unlock position** backed by the existing `AddConstraintCommand` / `RemoveConstraintCommand` (no second lock state, no new persisted field), disabled on a locked layer; lock and unlock are separate undo steps. A padlock badge drawn upright in the Y-flipped frame marks pinned objects, including ones without a drawing anchor. Save, reopen, undo and redo preserve the lock. Automatic Parallel/Perpendicular constraint creation also preserves FIXED geometry, including FIXED members of an orientation chain: rotate the other free group, or refuse without changing graph/history when neither group can turn. Already satisfied relations need no geometry change. The orientation indicator must connect to the selected edges: unique rectangle/ellipse/circle edge types must not be confused by their shared index 0 (PR #649 owner pass).
- **FR-EDIT-18** *(issue #560)*: Panel refreshes distinguish an explicit **history transition** (undo/redo) from an ordinary notification. A history transition updates even a focused text/numeric editor and unrelated fields while preserving the selection; ordinary notifications keep protecting uncommitted typing and caret. Pending debounced text commits flush before teardown or selection change as one command per committed gesture, never one per keystroke, and refreshes never register phantom commands.
- **FR-EDIT-19** *(issue #550)*: **Combine shapes > Union** accepts any number of polygons, rectangles, circles and ellipses that are connected by contact or overlap, replaces the whole selection with one result in **one undo step**, and preserves the source's appearance (through `core/item_look.copy_visual_style`) and opaque metadata through save/reopen. **Intersect** and **Subtract** remain exactly-two-shape operations and require a real shared area, not just contact. The existing ellipse context menu entries now produce a result. A selection containing a plant or sprite, a linked or constrained object, an item on a locked layer, subjects on different layers (the result is one item, so there is no correct layer to pick), or two subjects with different non-empty metadata is refused before the preview/confirmation and leaves the scene and undo stack untouched. A union whose result would enclose a hole (a closed ring of touching shapes) is also refused, because the polygon result cannot carry the hole without drawing its connector as a stroke. Closed-shape support is `item_to_painter_path` (a circle's `rect()`, never its shadow-inflated `boundingRect()`); union connectivity is `all_paths_connected` with a 0.001 cm contact tolerance, and a point-contact union is grown by `POINT_CONTACT_MERGE_CM` = 0.01 cm so it is one contour. A result above the plan's `MAX_POLYGON_VERTICES` (16 384) is refused before the preview: the loader would drop such a polygon on reopen, so the user would lose it after saving. A result above 256 vertices keeps #472's paint bound: while it is selected (as it is right after the operation) it fills normally, and once deselected its interactive paint is a cosmetic-pen outline until it is selected again; exports, prints and reports always draw the full fill.

- **FR-EDIT-20** *(issues #592, #594)*: Canvas refresh work is proportional to what changed. After every command, lock badges refresh only for objects pinned now or already showing a badge, and the ground-band classification runs only for commands that can change an object's type, height or group membership. A dense vertex-edit overlay keeps its sampled handles while the viewport stays within the scene region the sample covered, and re-samples on zoom or after a pan beyond it. A one-item-per-command loop therefore stays linear in items, not quadratic, and a 16 384-vertex outline does not re-walk every vertex on each scrollbar step.

  Polylines above 256 points use an exact one-pixel outline while unselected on the canvas or in a minimap thumbnail (#848). Selecting restores the stored width and style. Exports retain full detail, and the saved points and geometric operations are unchanged.

- **FR-EDIT-21** *(issues #627, #635)*: A plant dragged into (or out of) a plant-parent
  or moved via the agent (`move_object` / `set_object_position`) is
  **moved and linked as ONE undoable step**: one Ctrl+Z restores both its position
  and its previous parent, and one Ctrl+Y re-applies both. The link is decided where
  the move left the items, and the move and its links run as one `CompoundCommand`.
  A bed dragged ALONE carries its child plants with no lag, and one undo puts the
  bed and its children back to the centimetre.
  Acceptance: `tests/integration/test_plant_drop_undo.py` (real mouse drags on a
  `CanvasView` and agent `move_object`/`set_object_position`: reparenting moves
  are one undo/redo pair; a bed dragged with its linked plant keeps the link; a bed
  dragged alone carries its child), `tests/unit/test_commands.py::TestCompoundCommand`
  (order, reverse undo, a step that raises rolls the ones that ran back).
- **FR-EDIT-22** *(issue #674)*: **Group** and **Ungroup** are reachable from every groupable
  object's right-click menu, not only from `Ctrl+G` / `Ctrl+Shift+G`. The entries are decided from
  the selection at menu-open time: 2+ objects (no group) offer **Group**; exactly one eligible
  group offers **Ungroup**. A group plus another object or group offers both when at
  least one selected group is eligible. Eligibility is based on representable member poses
  (FR-GROUP-01). Group nests
  the selected items (including a group) into a new outer group; Ungroup dissolves **one nesting
  level** and dissolves every eligible selected top-level group in **one undo step**. Right-clicking an unselected
  object replaces the selection first, on every item type including group, callout,
  text, journal pin and construction geometry. The background image is deliberately **not**
  groupable (it is a plan backdrop; grouping it would re-band it above ground surfaces). The menu
  never offers a row the shortcut would refuse: both read `group_item.groupable_selection` /
  `ungroupable_groups`, and dispatch calls the view's `group_selected` / `ungroup_selected`. No new
  persisted field. Acceptance: `tests/integration/test_group_context_menu.py` (13 item types, real
  `contextMenuEvent`, menu matrix, the just-grouped state, nested one-level rule, one-step
  multi-group undo, selection normalisation and group-delete subtree cleanup).
- **FR-EDIT-23** *(issue #665)*: A filled object's texture can be **turned, scaled and shifted**
  independently of its geometry from the Properties panel: **Pattern Angle** (degrees clockwise,
  0 = as authored), **Pattern Scale** (multiplier, 1.0 = authored tile), and **Pattern Offset X/Y**
  (centimetres, negative allowed), plus one **Reset Pattern** button. The values live in an
  additive per-object `fill_transform` block (`{angle_deg, scale, offset_x_cm, offset_y_cm}`);
  the identity is not written, so old plans load unchanged and `FILE_VERSION` stays. Copy
  appearance, material/pattern changes, undo/redo and save/reload preserve all four values; a
  second save/reload is stable. Geometry, area, selection and snapping are untouched. A HOUSE's
  roof tiles compose the transform with the ridge frame, so both roof planes stay mirrored.
  Acceptance: `tests/unit/test_fill_transform.py` (model round-trip, malformed-file leniency,
  composition order, rendered clockwise sign and tile period) and
  `tests/integration/test_fill_transform.py` (panel spins + Reset, one command per change, geometry
  unchanged, save/reload, copy appearance, roof composition). The 3D ground/faces keep their
  existing untransformed sampling; the control is a 2D display property (ADR-071). A textured
  path/fence (gravel path, dirt path) exposes the same four controls, because its pattern stroke
  carries the same transform.
- **FR-EDIT-24** *(issue #690)*: Converting a rectangle or polygon to **HOUSE** through the
  Properties panel's Type field or the context menu's **Change Type** creates the same linked
  `ROOF_RIDGE` the polygon tool draws, in the **same undo step** as the type change; converting
  away from HOUSE removes it **and its `ridge_item_id` link**, and undo restores the same ridge and
  the original link (stable UUID) — a save or 3D read after two conversions + two undos still
  follows the live ridge. Geometry uses `core.roof_ridge.compute_roof_ridge_endpoints` mapped
  through the item's own transform, and the ridge is built by
  `ui/canvas/roof_ridge_link.build_linked_ridge` - the same seam `PolygonTool` and the agent's
  `create_object` use. It also paints its roof through the same
  `ui/canvas/items/roof_paint.paint_roof_with_ridge` path, so a converted rectangle's tiles lap
  down-slope on both sides of the ridge exactly like a drawn house's (manual test of PR #713, 2.1).
  A converted rectangle's ridge follows the host on move, resize and rotation
  (`update_linked_ridge`, called from `itemChange`, `_apply_rotation`, the resize hook and
  `apply_rect_like_geometry` for undo/redo). Deleting a house or a group containing one removes
  its ridge (menu, Delete key and agent `delete_object` share one tree walk); trimming a house
  into an open fence removes the ridge in the same undo step; fillet/chamfer and a converted
  rectangle's corner drag re-derive it; a mirror copy strips the inherited link and builds a fresh
  ridge on the reflected outline in the same undo step, and a ridge is never a mirror source.
  Grouping a house re-runs the stacking derivation, so the ridge renders above the group rather
  than behind its fill. Acceptance:
  `tests/integration/test_house_roof_ridge.py` (including the two-conversion undo/redo lineage,
  rectangle move/resize/rotate, menu delete and corner drag) and
  `tests/unit/test_roof_tile_orientation.py` (a converted rectangle and a drawn house paint the
  identical roof over eight orientations),
  `tests/integration/test_trim_extend_tool.py`, `tests/integration/test_fillet_chamfer.py`,
  `tests/integration/test_mirror_tool.py` and the grouped-house case in
  `tests/integration/test_agent_api_default_on.py`.
- **FR-EDIT-25** *(issues #741, #740, #727, #726, #703, #712; shipped in v1.37.1 via PR #747)*: 2D drawing & CAD integrity follow-ups:
  - *Derived ridge follow-ups (#712)*: `ROOF_RIDGE` is excluded from `groupable_selection()`, preventing accidental independent grouping. Array commands (`LinearArrayCommand`, `GridArrayCommand`, `CircularArrayCommand`, `ArrayAlongPathCommand`), `OffsetTool`, and mirror copy of a group containing a `HOUSE` build fresh linked ridges in the same undo step. Project load drops invalid/stale `ridge_item_id` and orphan `owner_polygon_id` links. Context menu and Delete key on `ArcItem`, `BezierItem`, `ConstructionLineItem`, `ConstructionCircleItem`, `CalloutItem`, and `TextItem` route through `dispatch_delete_selection`, ensuring full undo/redo.
  - *Multi-layer grouped houses (#741)*: Grouping houses from different layers normalises members and linked ridges to the group layer; undo restores original layers; ungrouping leaves them on the group layer; canvas visibility falls back to the owner's group layer.
  - *Agent API group note pruning (#740)*: `delete_object` on a group deletes nested `JournalPinItem` notes in the same `CompoundCommand` undo step.
  - *Path width consistency (#727)*: Switching path styles preserves user-set widths across path presets; default widths for path styles (`GRAVEL_PATH`, `STEPPING_STONES`, `PAVED_PATH`, `WOODEN_BOARDWALK`, `DIRT_PATH`) are unified to 80 cm.
  - *Paved path geometry (#726)*: Paved paths use `FlatCap` and `BevelJoin` for shadow and border passes, eliminating rounded lobes; 3D selection outline uses `polyline_bevel_footprint` to align with the 3D kerb mesh contour.
  - *Polyline vertex bounds (#703)*: Plan loader and Agent API enforce `MAX_POLYLINE_VERTICES` (16,384), refusing hostile polylines at load and mutation boundaries.

## Split, group drill-down and Esc

- **FR-SPLIT-01**: A closed shape (polygon, rectangle, circle or ellipse) offers
  **Split Along Line…** in its context menu, scoped to that shape. The CAD toolbar's
  Split button and the `Shift+S` shortcut scope the gesture to the selection at activation.
  With an empty selection the cut can reach any eligible closed shape. Click two points
  anywhere to cut the eligible shapes the segment crosses along its supporting axis.
  A scoped cut returns to Select after success. A scene-wide cut stays armed. A shape the
  segment crosses end to end is fully split; a shape it clips is cut along the same
  axis when both pieces are large enough to keep. A segment that only touches an
  outline — a corner, an edge, a tangent — is not a crossing. The tool takes two
  snapped scene points, previews the segment, the supporting axis and the pieces of
  every shape it will split, constrains the line to 45° steps while Shift is held, and
  cancels on Esc without mutating the scene. `S` alone stays Snap to Grid; the split
  shortcut must not reuse it (two window shortcuts on one key fire neither).
- **FR-SPLIT-02**: Applying one gesture replaces every crossed source with its pieces in
  exactly one undo step. Each piece keeps its source's layer, object type when valid for
  a polygon, fill/stroke colours, fill pattern and fill-transform, label/area visibility,
  name, metadata and stacking rank. A rotated source keeps its rotation and material
  direction; curves become polygons; a concave shape may produce more than two pieces;
  a result that would contain a hole is refused. **A straight cut of a raised bed keeps
  that type and its picture** when the piece is an axis-parallel rectangle in the
  source's own frame (#828): two raised beds still show their wooden frame, and a
  diagonal cut - or any type that a polygon can already carry - keeps the polygon path.
  A legacy live `HEDGE_SECTION` behaves the same way; a saved hedge section is migrated
  to `HEDGE_POLYGON` on load and takes the polygon path. A piece whose type does have to change still stands as tall as its
  source: a height that was only the source type's default (a raised bed's 40 cm) is
  written to the piece as its explicit height. When the source was painted as a sprite,
  such a piece takes its new type's fill pattern (soil) instead of the stored fill the
  sprite had hidden; a shape painted by its own brush keeps the pattern the user gave it.
- **FR-SPLIT-03**: The split is refused without mutation for a plant itself, constrained
  shapes, locked layers, grouped members,
  shape types with no polygonal form (for example a container), and any shape whose
  UUID is still referenced by soil, pest, harvest, succession, crop-rotation,
  manual-task or task-state project data (`ProjectManager.has_item_references`). A bed,
  raised bed or other plant parent with a polygonal form IS eligible: its linked plants
  are re-homed to the piece that contains their standing point in the same undo step,
  so no plant is orphaned. A house or a greenhouse is split like a garage: its linked
  roof ridge leaves with it, every piece gets its own ridge, and undo restores the
  original building and ridge. A building without a ridge (a flat roof) gives pieces
  without one. A building whose ridge is constrained or on a locked layer is refused.
  A cut splits the eligible crossed shapes within its scope and
  reports how many crossed objects could not be split; when nothing can be split, the
  reason is shown to the user.
- **FR-DRILL-01**: With a group selected, a plain click on one of its members focuses
  that member for editing without ungrouping. The group remains the canvas selection;
  the focused member is what the Properties, plant-details, companion and crop-rotation
  panels read (`CanvasView.effective_selection`). Clicking outside the member, pressing
  Esc, or selecting another object clears the focus. Nothing else does: the focus
  survives the minimap's refreshes and every other redraw of the running window.
- **FR-DRILL-02**: While focused, a member can be moved by dragging its body or with the
  arrow keys, resized/rotated with its own handles, and its
  geometry/appearance/species/notes can be edited through the Properties panel; each
  edit is one undo step and moves the member in its group's frame, never the group.
  The member's layer cannot change, movement of a constrained member or ancestor is
  refused, and Cut/Delete are refused until the focus is cleared.
- **FR-DRILL-03**: Nested groups drill one level per click; the focused member's inner
  outline is drawn by `GroupItem.paint` and disappears with the selection (exports clear
  it first).
- **FR-GROUP-01** *(issue #1022)*: A selected group draws one standard rotation handle
  above its own selection frame. Dragging it turns the whole group about that frame's
  centre; members keep their relative arrangement, `Shift` snaps to 15°, and one
  `Ctrl+Z` restores the group angle and every member position. A drilled-down member
  shows its own handle and hides the group's. The pivot is fixed at the first turn and
  saved with the angle. Ungrouping converts the composed scene pose of each member into
  its ordinary geometry and preserves it through reload. Undo restores the original local
  poses and group in one step (#1032). Scale and shear outside the supported pose are
  refused before mutation. A grouped bed keeps its plant links and
  carries them on a later move through the net-scene-delta rule; a grouped house's
  ridge follows. The group angle and pivot are additive `.ogp` data (a group `rotation`
  and `transform_origin` key, no `FILE_VERSION` bump). See ADR-075 addendum 6 and §8.9.22.
- **FR-TOOL-ESC-01**: **Esc always returns to the Select tool**, from every drawing,
  object-placing, CAD and constraint tool. A gesture in progress is cancelled with no
  preview left behind and the distance/angle prompt is hidden. An inline text or label
  edit that has the focus is finished by the same Esc. Three narrower meanings take
  an Esc of their own first: cancelling a calibration, leaving vertex editing and
  leaving a group drill-down. All of it works wherever the keyboard focus is in the
  main window - the canvas, a panel, the object search field, the status-bar
  coordinate field - as long as the focused widget does not use Esc itself (an open
  search popup closes first). In fullscreen preview an Esc first ends a tool that was
  picked there - wherever the keyboard focus is - and the next one leaves the preview.
  F1 lists the key under Drawing Tools.

Pins: `tests/unit/test_shape_split.py`, `tests/integration/test_split_shapes.py`,
`tests/integration/test_group_drill_down.py`, `tests/unit/test_project.py::TestItemReferences`,
`tests/integration/test_tool_switching.py::TestEscapeReturnsToSelect`,
`tests/unit/test_object_height.py::TestHeightAcrossATypeChange`.
