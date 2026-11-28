---
id: ADR-075
title: "CAD editing keeps the group frame and the command stack"
status: "Shipped in v1.37.10 (PR #783)"
refs: ["#664", "#771"]
legacy_anchor: adr-075-cad-editing-keeps-the-group-frame-and-the-command-stack-issues-664-771
---

# ADR-075: CAD editing keeps the group frame and the command stack

**Status**: Shipped in v1.37.10 (PR #783)

**Context**: Two CAD editing gaps shared the canvas selection and command seams. A
closed shape could not be cut into pieces: the only workaround lost the layer, look,
fill transform, label state and metadata. And a group's members could not be edited
without ungrouping it. Qt constrains the second problem more than the first: a
`QGraphicsItemGroup` routes a child's selection back to the group (`scene.selectedItems()`
returns only the group), and the child's own resize/vertex handles do not receive a
usable drag while the group is the selection. Detaching the child on drill-down and
re-adding it on exit looks simple, but commands captured while detached store local
`pos()`/`rect()` values in the child's temporary top-level frame; re-adding changes
that frame, so a later undo on a moved or rotated group can restore the wrong place.

**Decision**:
1. **Drill-down is a logical focus, not a reparent.** `CanvasView.drill_down_item` names
   one direct member of the selected group. The group stays the Qt selection; the
   member stays its child, so its layer guard, saved group data and transform frame
   are unchanged. `CanvasView.effective_selection()` is the one selection seam every
   panel uses (`_on_selection_changed`, properties, plant details, companion, crop
   rotation), and `drill_down_changed` replaces Qt's `selectionChanged` for that focus
   because Qt does not emit one. `GroupItem.paint` draws the focused member's outline
   only while the group is selected, so exports (which clear selection) never paint it.
2. **Geometry edits of a focused member stay in the group frame.** A body drag is a
   view-owned gesture (`begin_drill_down_drag`/`_finish_drill_down_drag`), not Qt's
   group drag; the arrow keys and the Properties panel convert a scene delta through
   `_delta_in_parent_frame()` before writing `item.pos()`. The member's own resize and
   rotation handles are shown, and the view replays their press/move/release through
   `ResizeHandle.begin_drag/apply_drag/end_drag` and the `RotationHandle` equivalents,
   because Qt routes a group child's handle press to the group. Every grouped
   ancestor's `ItemIsMovable` flag is cleared while the member is focused and restored
   on exit. Changing the member's layer is refused in the context menu, the panel and
   `PropertyEdits`; Cut/Delete and movement of a constrained member or ancestor are
   refused while a member is focused.
3. **Split works in the source's local frame and replaces it in one command.**
   The context menu and the CAD toolbar button next to Trim/Extend reach the
   same tool, but with different scopes: the context menu arms the clicked
   closed shape, while the toolbar and the `Shift+S` shortcut start a scene-wide
   two-point cut with no prior selection. In scene-wide mode the first click is
   the line's first point and every closed shape the drawn segment passes
   through is cut along the segment's supporting axis; shapes on the line's
   infinite extension but not reached by the segment are not cut, and a
   boundary touch (a corner, an edge, a tangent) is not a crossing.
   `core/shape_split.py` clips each item's local `QPainterPath` against the two
   half-planes of the two-point axis; one `SplitShapeCommand` per source removes
   it and adds ordinary `PolygonItem`s, and the whole gesture is one undo step
   (a bare command when no membership reconciliation is needed, otherwise a
   `CompoundCommand`). Pieces copy
   the source's layer, object
   type (when valid for a polygon), name, label/area state, metadata, stack order and
   `fill_transform`; using the local frame keeps a rotated source's rotation and
   pattern direction. Curves flatten to polygons, a concave shape may yield more than
   two pieces, and a result that contains a hole is refused because a `QPolygonF`
   cannot carry it.
4. **A split may not orphan project data.** `CanvasView.split_refusal_reason` refuses
   a plant itself, constraints, locked layers, grouped members (ridge-bearing
   buildings too at first; the second addendum lifts that), shape types without a
   polygonal form, and any source
   whose UUID is still named by soil, pest, harvest, succession, crop-rotation,
   manual-task or task-state data. The last check is
   `ProjectManager.has_item_references`, the single central query. A bed or other
   plant parent with a polygonal form is NOT refused for having plants: a
   `ReconcileBedMembershipCommand` in the same undo step re-homes each linked plant
   to the piece that contains its standing point, using the established
   plant→bed mutator.

**Alternatives considered**:
- *Detach the member and re-add it on exit.* Rejected: command snapshots are in the
  temporary top-level frame; undo after a moved or rotated group would restore a
  different place. It also changes the group's serialized children while focused.
- *Duplicate the member as an edit proxy and apply it back on exit.* Rejected: the
  edit commands would target a deleted proxy after the apply, leaving a broken stack.
- *Copy the split geometry into `shape_boolean` or the tool.* Rejected: the roof
  painter already has a line split, and a second copy would drift; `shape_split`
  reuses `item_to_local_painter_path` and the shared `path_has_hole` / area floor.
- *Produce scene-frame pieces.* Rejected: a rotated source's brush transform would be
  recomputed from the scene origin, so the material would visibly jump at the cut.
- *Allow a split of tracked beds and let the records follow one arbitrary piece.*
  Rejected: the user did not choose which piece inherits the history; refusing is
  reversible, silently reassigning is not.

**Consequences**: New `core/shape_split.py`, `core/tools/split_tool.py` and
`ui/canvas/items/split_menu.py`; `SplitShapeCommand` in `core/commands.py`; group
drill-down state and `drill_down_changed` in `ui/canvas/canvas_view.py`. No
`FILE_VERSION` bump: the pieces are ordinary polygons and drill-down is runtime-only.
User-visible strings are covered in EN/DE/ES/RU. Pins:
`tests/unit/test_shape_split.py`, `tests/integration/test_split_shapes.py`,
`tests/integration/test_group_drill_down.py`, `tests/unit/test_project.py::TestItemReferences`,
`tests/integration/test_tool_switching.py::TestEscapeReturnsToSelect`,
`tests/unit/test_object_height.py::TestHeightAcrossATypeChange`.
Cross-refs: FR-SPLIT, FR-DRILL, FR-GROUP, §8.35, PF-CAN-46, PF-CAN-48.

**Addendum (2026-11-09) — two-point cuts without a selection, and the Shift+S shortcut.**

Addendum 5 defines how a preselection limits this gesture.
Manual testing of PR #783 rejected the first interaction: the toolbar's Split tool
required a selected shape (or a shape-picking first click), so a line could cut only
one object and a scene-wide cut took three clicks. The owner's expectation is the
CAD-knife one: choose the tool, click two points anywhere, and every object the line
crosses is split, fully or partly. The tool now takes the first click as the line's
start with no source selected, freezes the visible closed-shape candidates at that
point, previews every crossed shape's pieces while the second point moves, and applies
all cuts in one undo step. The context-menu action keeps its explicit one-shape scope
and returns to Select; the toolbar stays armed for another cut. The candidate test is
the **drawn segment** (`segment_crosses_item`), not the infinite axis: a shape lying on
the line's extension but not reached by the segment is never touched, while a segment
that starts or ends inside a shape still divides it along the supporting axis.

The shortcut changed from `S` to `Shift+S` because the first version was dead in the
real window: `S` is `snap_action`'s window shortcut, and a second window shortcut on
the same key makes Qt fire neither (measured on Qt 6.12 with a `QToolButton` and a
`QAction` in one window; PF-UI-36). `Shift+S` is free and leaves `S` as Snap to Grid.

Review then found two consequences worth stating. A **touch is not a crossing**:
`segment_crosses_path` splits the segment at its outline crossings and accepts only
an interval whose midpoint is strictly inside (offset points on both sides must be
inside), so a snapped pick on a bed's corner, a segment along an edge, or a tangent
returns False. And **a bed with plants is eligible**: refusing every plant parent
would make the headline feature unable to touch the normal object in a garden. The
`SplitShapeTool` adds a `ReconcileBedMembershipCommand` to the same undo step for
every split source that has children; the existing plant→bed mutator moves each
plant to the new piece containing its standing point, and undo restores the source's
links before the source itself comes back.

**Addendum 2 (2026-11-09) — decisions from the owner's manual test of PR #783.**
Behaviour is specified in FR-SPLIT, FR-DRILL and FR-GROUP and the mechanics in §8.35; this records what was
decided and what was rejected.

1. **A building with a ridge is split like a garage.** The first version refused every
   ridge-bearing building because its linked `ROOF_RIDGE` would be orphaned. The ridge
   is derived geometry (ADR-046), so nothing has to be preserved: `SplitShapeCommand`
   removes the source's ridge with the source and builds every piece its own through
   `roof_ridge_link.build_copy_ridges`. A source without a ridge (the user's flat roof)
   gives pieces without one. A ridge that is constrained or on a locked layer still
   refuses the split, like the shape itself.
2. **A rebuild's type change keeps the height.** A raised bed's 40 cm is a per-type
   default (ADR-037, rung 4); its garden-bed pieces had none. The height the object
   stood at is written as an explicit `object_height_cm`
   (`object_height.carry_height_across_type_change`), in the one entry point for a
   rebuild's type change, `item_look.adopt_rebuilt_type`, which the split, the corner
   tools and the loader's raised-bed migration share. Accepted trade-off: the piece then
   shows a custom height, so a later manual type change no longer follows the new type's
   default. The Properties panel's own type change is unchanged.
3. **A sprite's stored fill is not its look.** A piece of a sprite-painted source takes
   its new type's fill pattern; a source painted by its own brush keeps the user's
   pattern (`adopt_rebuilt_type(keep_fill=...)`). The wooden frame stays a
   rectangle-only sprite (owner decision 2026-10-31): a piece is a garden bed with soil
   and a height, which the 3D view builds as an edged bed.
4. **Esc ends every tool, and means the same wherever the focus is.** The canvas
   leaves one narrower mode per press (calibration, vertex editing, drill-down), else
   ends the tool (`return_to_select_tool`); the main window calls the same two steps
   (`CanvasView.handle_escape`) for an Esc no focused widget consumed. Rejected: a
   window-level `QShortcut` on Esc, which would pre-empt every line edit, popup and
   inline editor in the window (and a second shortcut on one key fires neither,
   PF-UI-36). The focused inline editor receives the same Esc first.
5. **The minimap hides a selected group's descendants by opacity** instead of a flag
   (PF-CAN-48).

**Addendum 3 (2026-11-20) — the Esc plumbing and overlay typing are finished (#829).**
The P2 findings of the PR #783 reviews are closed without changing any behaviour the
owner tested.

1. **One Esc rule, in preview too.** The main window's preview branch calls
   `CanvasView.handle_escape()` before leaving the preview, so the first Esc ends a tool
   picked inside the preview wherever the focus is (the canvas already handled it when it
   had the key) and the second leaves the preview. `FR-TOOL-ESC-01` says so. The per-tool
   Esc switches in the Split, Callout and Journal Pin tools are gone: the view's central
   rule returns to Select, so a tool only cancels its own gesture.
2. **The inline editor is declared, not guessed.** `TextItem`, `EditableLabel` and the
   callout's text child carry `is_inline_text_editor = True`; the canvas tests that marker
   instead of `hasattr(focus, "toPlainText")`, which agreed only because no fourth class
   happened to hold scene focus.
3. **Every tool switch goes through the view.** The four sites that called
   `_tool_manager.set_active_tool` directly (the offset tool and the vertex-edit action of
   the polygon, polyline and rectangle items) now call `CanvasView.set_active_tool`, so the
   distance/angle prompt is hidden and the typed-input buffer is cleared there too. A drift
   test fails if a new direct call appears outside `canvas_view.py`.
4. **The dynamic overlay is typed.** `_dynamic_overlay` is `DynamicInputOverlay | None`
   under `TYPE_CHECKING`; the former `object` annotation, its `getattr`/`callable` guard and
   the mypy baseline entry are gone.
5. **The split refusal names the ridge.** When the shape itself is editable but its derived
   roof ridge is on a locked layer, the message says "The roof ridge is on a locked layer"
   instead of blaming the shape.
6. **The minimap's hide/restore is one value.** `_hide_overlay_items` returns
   `(item, restore_opacity)` pairs (`None` for the flag path) and `_restore_overlay_items`
   consumes them; the `_faded` side dictionary is gone, so a caller that restores in a
   `finally` carries everything it needs.

**Addendum 4 (2026-11-20) — a straight cut keeps the raised bed's frame (#828).**
Addendum 2, item 3, said a piece is a garden bed because the wooden frame is a
rectangle-only sprite. The owner asked for the frame back. The chosen option is the
smaller of the two the issue offered: a piece that is an **axis-parallel rectangle in
the source's own frame** and comes from a **sprite-painted type that a polygon cannot
carry** is rebuilt as a `RectangleItem` of the source's type, so it paints the same
sprite and keeps its type default. In practice that is a **raised bed** (40 cm); a
legacy live `HEDGE_SECTION` takes the same path, while a saved one is migrated to
`HEDGE_POLYGON` on load and is already polygonal. Every other case is unchanged: a
diagonal cut of a raised bed still gives garden beds; a house or a terrace still gives
polygons that keep their type; a generic rectangle still becomes a generic polygon, as
before. The recognition is
`shape_split.axis_parallel_rect` (tolerance 0.01 cm) and the decision is made once in
`SplitShapeTool._make_piece`, so the previewed **geometry** and the committed pieces
agree; the preview stays a type-neutral dashed outline. No `FILE_VERSION` change: both
rebuilt types already exist and a rectangle was always a valid carrier.

Pinned by `tests/unit/test_axis_parallel_rect.py` and
`tests/integration/test_split_shapes.py::test_a_straight_cut_of_a_raised_bed_gives_two_raised_beds`,
`::test_a_diagonal_cut_of_a_raised_bed_stays_a_pair_of_garden_beds` and
`::test_a_split_raised_bed_keeps_its_frame_and_height`.
**Addendum 5 (PR #981) — the preselection sets the scope of Split.**

**Status:** Shipped in v1.40.11 (PR #981). Owner manual testing passed on 2026-11-20.

The toolbar and Shift+S capture the effective selection at activation. With a
selection, only those targets can be cut, even if all of them are refused or
removed before the second point. With no selection, the tool takes the usual
scene-wide path. A successful scoped cut returns to Select. The raised-bed
example exercises the refusal because its soil test and succession plan refer
to the original bed ID. A freshly drawn raised bed exercises the frame-preserving
cut.

**Addendum 6 (issue #1022, 2026-11-25) - a selected group turns as one unit.**

**Status:** Shipped in v1.43.3 (PR #1030, 2026-11-27); owner manual tests passed on 2026-11-27. A group now mixes in the
same `RotationHandleMixin` as a single item, so it shows one standard handle
above its own selection frame (#840's `selection_frame_rect`, never
`boundingRect()`: a badge or a screen-sized handle would move the pivot). The
gesture is a **group transform**, not a loop over members: children keep their
local positions and Qt's group transform rotates their scene positions about
the frame centre together. `GroupItem._apply_rotation` sets the transform
origin to that centre on the first turn only, and `_on_rotation_end` registers the ordinary
`RotateItemCommand` through `geometry_apply.register_rotation_command`, so the
whole gesture is one undo step and the shared constraint-partner recording
still runs. A drilled-down member keeps its own handle; the group hides its
own for the duration (`CanvasView.begin_group_drill_down` /
`_clear_group_drill_down`), which reuses the existing
`_individual_handles_allowed` rule.

Persistence is additive: a group may carry a `rotation` key (the same key a
pre-#1009 smart-symbol group used) and a `transform_origin`; a later member edit
does not re-pivot, and reloading the saved origin is what keeps every member in
place. The command records both pivot states, so undo restores the previous one
and a drag that changes nothing fixes none. A nested group saves its compensating
base transform, so regrouping a turned group does not apply its translation twice.
That matrix is translation-only; a plan with a rotation or scale there is refused at
the numeric boundary, and edit surfaces refuse such a group. The boundary composes
x/y with that translation, every parent offset and every transformed primitive's box
(including far edges and the group union) through the same Qt-free
`core/object_bounds` code the Agent API uses; a legacy symbol
without an origin rotates about (0, 0) in both. One `core/angles` rule decides an
Agent no-op, saving a group angle, and Ungroup's turned test, canonicalizes a
sub-tolerance target to 0, and commits a gesture that returns inside the tolerance as
exactly 0. A committed
member angle is saved even below 0.01°, so a tiny group turn survives reload.
Grouped child records carry their own `parent_bed_id` / `child_item_ids`, so a link
whose endpoints are both members survives save and reload; copy/duplicate remaps
both fields through one map for the whole tree and drops uncopied endpoints. That
map is the only author of copied links; paste/duplicate never rebuild them from a
top-level-only map, and the forest is normalized so each source item appears once.
The Agent API's group box applies the same base translation; a grouped or turned
callout saves its local bounds and pivot (text edits do not re-pivot it) and reports
the scene-space leader tip; a text note saves its reflected footprint. A turned
standalone callout's region box is its turned footprint.
Ungrouping a turned group (#1032) captures every member's scene transform before
reparenting. The command applies the pose the existing serializers write: normal
member angles, scene-frame geometry for curves and construction lines, and the
one intrinsic Y reflection of text. Nested groups keep their descendants local.
Undo reapplies the captured local state, including the original base matrix and
pivot. Validate the whole group before mutation. A legacy symbol
without an origin rotated about its local (0, 0); the loader reproduces that
exact geometry. A grouped bed's linked top-level plants are captured at gesture start and
carried about the same pivot by `RotateItemCommand`'s follower snapshots. Its membership
tracker re-decides only the group's own plants whose parent bed did not turn with them; a
plant that turns with its own bed keeps the link because the two moved rigidly, and the
carried top-level plants are followers, never re-solved. The move command's
net-scene-delta rule (PF-CAN-70) handles later moves. A constrained member, a member on a
locked layer, or a linked plant owned by another group is refused before any geometry
changes. Roof ridges are re-derived by the existing `update_house_ridges_under` listener.

Pinned by `tests/integration/test_group_rotation.py` (handle visibility,
drill-down, a real viewport drag, rigid member geometry, one-step undo, Shift
snapping, a nested group, a grouped bed, a grouped house ridge, DXF ellipse
orientation, zero-angle pivot, constraint refusal, and save/load after a member
edit and an ungroup refusal).
