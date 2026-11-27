---
id: ADR-046
title: "Derived geometry is recomputed, never projected"
status: "Accepted (2026-09-29). Fixes the HOUSE/ROOF_RIDGE sync; #363 (issue-template links) shipped in the same package and is unrelated to this decision."
refs: ["#364"]
legacy_anchor: adr-046-derived-geometry-is-recomputed-never-projected-issue-364
---

# ADR-046: Derived geometry is recomputed, never projected

**Status**: Accepted (2026-09-29). Fixes the HOUSE/ROOF_RIDGE sync; #363
(issue-template links) shipped in the same package and is unrelated to this
decision.

**Context.** A HOUSE auto-creates a linked `ROOF_RIDGE` polyline along its
longest bounding-box axis, clipped to the polygon boundary. The canonical
computation is `core/roof_ridge.compute_roof_ridge_endpoints()`, extracted in
US-D2.5 so that the drawing tool (`PolygonTool._create_roof_ridge`) and the
Agent API (`application.py`) produce identical ridges — the "one canonical path"
discipline.

`PolygonItem._update_ridge_on_boundary()` did **not** use it. Introduced with
the roof-ridge feature itself (`818e3fb`, #114) and last touched by US-D2.6
(`4e0a312`, #330), it re-projected the ridge's *existing* endpoints onto the
current boundary via `_project_to_polygon_boundary`. Two measured defects:

* **Drift undo cannot repair.** Adding a vertex moved the second endpoint onto
  the newly introduced slanted edge; undo restored the polygon exactly and left
  the ridge behind (36 cm on a 300x200 cm house). The write bypassed the
  command system, so no undo step covered it, and drift accumulated over
  repeated cycles.
* **No rotation or scale awareness — larger than the reported bug.** The
  membrane kept the ridge's prior orientation, so a house rotated 30/90 degrees
  kept a ridge at 0 degrees, deviating 75 cm / 180 cm from geometric truth.
  Since `_paint_with_ridge` mirrors the roof texture along the ridge line,
  every rotated house also rendered a wrongly-oriented roof.

**Decision.** The ridge is **derived** geometry and is recomputed from the
owner's polygon on every sync, through the same canonical function used at
creation:

    compute_roof_ridge_endpoints(polygon, QPointF(0, 0))   # LOCAL frame
      -> house.mapToScene() -> ridge.mapFromScene()         # full transform

Computing in the local frame and mapping through the item's transform — rather
than adding `pos` to local points as creation does — is what makes it correct
for a rotated or scaled house. The creation formula is only valid for an
unrotated item; the issue's own suggested fix (call it with `pos`) would have
reproduced the unrotated case and left rotation broken.

Consequences:

* **Self-healing and undo-safe on every polygon-apply path.** Restoring the
  polygon *is* restoring the ridge, so no extra undo bookkeeping is needed —
  but only because **every** path that writes a polygon's geometry re-derives
  the ridge. There are **six sites**, and the list is deliberately flat rather
  than grouped by method name, because the count is the point: 1)
  `PolygonItem._move_vertex_to`, 2) `_after_vertex_topology_change` (which
  `_insert_vertex`, `_remove_vertex`, `_add_vertex_at_edge` and `_delete_vertex`
  all funnel through — four entry points, **one** apply site), 3)
  `PolygonItem._apply_rotation`, 4) `PolygonItem._apply_resize`, 5) the
  `ResizeItemCommand` apply closure, and 6) the constraint solver's polygon
  restore in `canvas_view`. The fifth was missed by the first implementation of this fix
  and caught only in senior review — it left a HOUSE resize undo restoring the
  polygon while the ridge stayed sized for the *resized* house (**300 cm** of
  drift on a 300->600 cm resize, persisted into the `.ogp`). That closure is now
  `polygon_resize_apply`, module-level rather than a closure inside
  `_on_resize_end` specifically so a test can drive the production function
  instead of re-implementing it. The sixth came out of the same review round:
  `canvas_view`'s solver `finally` restored the polygon with a bare `setPolygon`,
  bypassing `PolygonItem._move_vertex_to` — the one override that re-derives -
  so after the trial move the ridge was left computed for the trial geometry.
  Transient on a successful solve, which re-applies the moves through a command;
  persisted when the solve raises, since nothing re-applies them. **A seventh polygon-write path that skips the
  sync will silently rot this invariant** — the durable lesson is not "recompute
  instead of project" on its own, but "a derived child must be re-derived by
  *every* writer of its owner's state", because a derived child adjusted from
  its own current position becomes state that nothing owns. Re-derive the
  enumeration with `grep -rn "setPolygon\|setPoints\|setRotation\|setScale\|setTransform" src/`
  when adding a path — and remember that a rotation or scale changes the ridge
  without touching the polygon at all, so a polygon-only grep misses the path whose
  absence recreates the orientation defect.

  **The benign hits, recorded so nobody re-litigates them.** That grep returns
  15 sites; only the six above are HOUSE writers. Checked and inert:
  `background_image_item.py` (`setScale`/`setRotation`, never a HOUSE) and
  `dxf_service.py:454` (`EllipseItem`). Two hits *look* alarming and are not
  writers either: `corner_edit_base.py:298,318` (`clone.setRotation`) and
  `polygon_tool.py:196` (a preview `setPolygon`) both build **fresh** items
  that carry no `ridge_item_id`, so `_find_ridge()` returns `None` and there is
  no derived child to re-derive. The test that decides it is not "is this a
  polygon write" but "does the item have a linked ridge".

* **A hand-dragged ridge endpoint is not sticky.** `PolylineItem._move_vertex_to`
  still constrains a hand-dragged endpoint onto the owner's outline, so the drag
  is honoured; the next polygon edit returns it to canonical. The reason is the
  derived-state invariant above — a second, manually-placed source of truth for
  the same geometry is precisely what this change removes — and not any claim
  about the texture disagreeing, which cannot happen: the texture is re-derived
  from whatever the ridge currently is, so a hand placement never puts the two
  out of sync. The same reasoning drops a user-inserted third ridge vertex on
  the next polygon edit: the derived ridge is exactly the two canonical
  endpoints. That is a deliberate capability loss on a user-editable item, and
  it is accepted here for the same reason.
* **`_project_to_polygon_boundary` is kept**, still used by
  `PolylineItem._move_vertex_to` to constrain that hand drag.
* **A ridge drift already saved into an `.ogp` self-heals on the next polygon
  edit**, not at load time. The cause is *not* serialization order: it is that
  `_deserialize_item_core` calls `_apply_rotation` on the house before the item
  is added to the scene, so `self.scene()` is `None` and `_find_ridge()` bails
  out early — a no-scene guard, independent of which item the file lists first.
  A load-time resync was considered and deliberately left out; it widens the
  blast radius into the deserializer for a cosmetic gain. Recorded here rather
  than discovered later.

**Alternatives rejected.** (a) *Make the projection reversible* — capture ridge
points in every vertex command and restore them in `undo`/`redo`. Rejected:
threading a second geometry through four command classes to preserve state that
should not exist. (b) *Re-project on undo only* — rejected: undo and edit share
one apply path, so "on undo" needs a new signal the architecture does not carry.

**Cross-refs:** section 11.4, issue #364, US-D2.6 (#330), issue #114.

## ADR-046 addendum: roof-tile down-slope is gravity-relative, not name-relative (issue #372)

**Status**: Accepted (2026-09-30). Found during the #364 manual test; shipped in
the same PR. **Pre-existing**, not a #364 regression: master's membrane path
produces the same drift figures, and `git diff eed0895..HEAD` touches
`_paint_with_ridge` only in a docstring.

**Context.** `_paint_with_ridge` splits a HOUSE along its ridge and fills each
half with the tile texture, one mirrored. The roof-tile texture has a fixed
direction: each tile's rounded free edge points `+Y` and laps the tile below
it (measured from the texture - a dark lapse line near `y=10`, the light free
edge beneath), so `+Y` is **down-slope**.

The halves were assigned by `_split_path_by_line`'s naming, which follows the
left-perpendicular `n = (-uy, ux)` and therefore the ridge's *direction*, with
no relation to which side is downhill. Rasterizing both clip regions:

| Ridge | `left_path` (was given the **mirror**) |
|---|---|
| horizontal (+X) | LOWER half |
| vertical (+Y) | LEFT half |

So the half needing the texture's true down-slope was the one being mirrored.
Because the two clip halves are mirror images of each other across the ridge,
they read the *same* outward sequence, so the inversion showed up on **both**
halves at once -- `BRRBRR` either way, mirror-symmetrically -- not on one side.
Water would run uphill under the laps. Wrong at **every** ridge angle, which is
why horizontal and vertical houses were both affected.

**Measured, through the production paint path** (two-colour probe brush on the
item, walking outward from the ridge; `R` = the texture's up-slope phase,
`B` = its down-slope phase):

    fixed    +n RBBRBB   -n RBBRBB      (first transition R->B)
    pre-fix  +n BRRBRR   -n BRRBRR      (first transition B->R)

Both are mirror-symmetric -- the *split* is unchanged by the fix -- so only the
absolute phase separates them, and a half-vs-half comparison cannot tell the
two builds apart. Sweeping every 15 degrees from 0 to 345 gives these two
strings and no others, on both halves: the result is **angle-independent**,
because the defect tracked *which half received the mirror* rather than any
particular orientation. (An earlier draft of the test excluded 90 and 270 on the
claim that the ridge then runs along the sample axis; that claim was an artifact
of a double-applied transform in the harness itself - see §11.4.)

**Decision.** The down-slope half always receives the **normal** brush. The
arithmetic that makes this a swap rather than a probe: `normal_tx` is
`translate(mid) . rotate(angle)` and a `QBrush` transform samples the texture at
`T^-1 . p`, so the texture's `+Y` lands in the world at
`R(angle).(0,1) = (-sin a, cos a)` - exactly `n`. `left_path` is the half the
down-slope points into, so it takes the normal brush. Verified with a
two-colour probe texture at every angle, and by rendering both a horizontal-
and a vertical-ridge house.

**Alternatives rejected.** (a) *Select the mirror by probing which side is
upslope* - equivalent in result, but needs a containment probe and a fallback
for degenerate polygons. The identity above is exact and needs no branch.
(b) *Rotate by `-angle` instead* - measured with the same probe, and this is
  the sharpest illustration of a trap in this whole episode: `angle` here is
  the ridge direction in the polygon's **local** frame, which
  `compute_roof_ridge_endpoints` pins to the longest bounding-box axis. For a
  **landscape** house that is 0 at every rotation, so `rotate(-a)` and
  `rotate(+a)` are the *same transform* and a rotation sweep cannot tell the
  mutant from the correct code at all - measured, the negated sign still reads
  `RBBRBB` at every rotation of a landscape house. For a **portrait** house
  `angle` is 90 and the negated sign reads `BRRBRR`, i.e. it is caught. So the
  alternative is wrong in the case that matters and right-looking in the case
  that hides it, which is why the test cases span both geometries
  (`tests/unit/test_roof_tile_orientation.py`).

**Preserved deliberately.** The two-sided `setClipPath` + oversized `drawRect`
shape was kept; only the brush assignment changed. (At the time the SVG export
depended on that shape through a post-processor; since #787 it does not — the
export records clips and brush transforms below the painter, ADR-076.)

**Testing note.** Correlating the real 256 px tile texture was tried first and
had **no discriminating power** (peak correlation ~0.03 either way, and the
diagonal case tied at 0.020 vs 0.019) - a few hundred sampled pixels span barely
one texture period. The two-colour probe is what settled it, and
`tests/unit/test_roof_tile_orientation.py` uses it, over **eight
house/rotation cases** spanning landscape, portrait and square; 8 of its 11 cases
fail against the unfixed brush assignment. Landscape cases alone would leave the
`rotate()` sign unpinned — see alternative (b).

**Cross-refs:** §11.4, issue #372, issue #114, ADR-046.

## ADR-046 addendum: a type change into HOUSE owns its ridge (issue #690)

The polygon tool and `create_object` already build the canonical ridge, but a
rectangle or polygon converted to HOUSE through the Properties panel or
**Change Type** stayed ridgeless on the canvas (3D still worked from its type).
A type change is now `ChangeObjectTypeCommand`: it applies the type/style state,
creates the linked `ROOF_RIDGE` when the new type is HOUSE, and removes it — and
its `ridge_item_id` link — when the shape leaves HOUSE, all in the type change's
one undo step. The ridge is built once and re-added on redo. **The link itself is
part of the undo state**, not just scene membership: the command remembers the
item's pre-command `ridge_item_id` and restores it on undo, so a HOUSE → bed →
HOUSE sequence followed by two undos leaves the item naming the *original, live*
ridge (a stale key would also make the scene treat the bed as a ridge owner and
refuse it for booleans). Construction goes through
`ui/canvas/roof_ridge_link.build_linked_ridge`; `PolygonTool`, the agent's
`create_object` and the type change all use it, so there is exactly one
construction path and one geometry computation
(`compute_roof_ridge_endpoints`, mapped through the item's own transform). A
converted rectangle's ridge follows the host on move, resize and rotation via
`update_linked_ridge` (the same derivation `PolygonItem` uses; called from the
item hooks, the group-move hook and the canonical `apply_rect_like_geometry`, so
undo/redo follows too). A ridge is created on every path that creates or converts
a HOUSE — drawing, `create_object`, the type change, paste, duplicate and Mirror
Copy. Offset and array copies do not build one yet (follow-up); they can never
adopt the source's, because every lookup (`linked_ridge`, `PolygonItem._find_ridge`, delete,
3D snapshot, sun/shadow) validates the reverse `owner_polygon_id`. This codebase
has no `roof_shape` property (the issue's wording predates the current
`roof_style` metadata, which is 3D-only and does not suppress the 2D ridge).
Pinned by `tests/integration/test_house_roof_ridge.py`.

**Paint follows the same one-path rule.** A HOUSE is drawn as its roof seen from
above, and both item classes call `ui/canvas/items/roof_paint.py`'s
`paint_roof_with_ridge`: the polygon's outline or the rectangle's four corners,
the same ridge, the same mirrored tile planes. Without it a converted rectangle
fell back to the flat fill and its tiles lapped back up toward the ridge while a
drawn house's lapped away — the 2.1 finding of PR #713's manual test. The
converted and drawn houses are now byte-identical over eight orientations,
pinned by `tests/unit/test_roof_tile_orientation.py`.

**Addendum (ridge lifecycle, #690 review).** Every operation that removes or
replaces a house must treat the ridge as derived geometry, not a sibling the
user selected:

- **Deletion owns the tree.** `group_item.selection_tree()` walks a selected
  item's Qt child tree once; `roof_ridge_link.linked_ridges_under()` uses the
  same walk for ridges, and the GUI delete paths use the tree for constraints
  and journal notes too. Deleting a group therefore removes a nested HOUSE's
  ridge, a child's constraint and a grouped pin's note. The GUI's Delete key, the shared
  shape-menu Delete (routed through `CanvasView._delete_selected_items`, so it is
  undoable) and the Agent API's `delete_object` share it. A grouped pin's
  ProjectData note command is bundled with the item delete in ONE
  `CompoundCommand`, so the first undo restores pin and note together (never a pin
  without its note); the Agent API's delete still leaves a nested pin's note row
  behind (open follow-up, #740).
- **A trim that opens a house removes its roof.** Trimming a HOUSE polygon or
  rectangle produces an open FENCE; the old closed-shape ridge and any
  constraint anchored to it are removed and restored by `TrimPolygonCommand`'s
  `linked_ridge` parameter, and the replacement does not inherit
  `ridge_item_id`.
- **A corner edit re-derives.** Fillet/chamfer replace the host shape, so
  `_CornerReplacementCommand` re-derives the ridge on execute, undo and redo
  (a converted rectangle's corner drag has its own hook in `_move_corner_to`,
  where no `itemChange` fires).
- **A copy never adopts a source ridge.** Mirror Move keeps the house UUID and
  re-derives the ridge; Mirror Copy gets a fresh UUID, strips the inherited
  `ridge_item_id` and builds its OWN ridge on the reflected outline in the same
  undo step (`MirrorItemsCommand._add_copy_ridges`, re-adding the same ridge
  item on redo), and a `ROOF_RIDGE` is never itself a mirror source. Offset and
  array copies still do not build a ridge (documented follow-up).
- **A grouped ridge renders above its group.** A house's ridge is a top-level
  sibling; once the house joins a group the stacking normalizer resolves the
  owner to the GROUP, so grouping must run the one z derivation
  (`_update_items_z_order`). Without it the ridge keeps its pre-group z and the
  group's fill hides all but its ends (manual test 2.7).
- **Same-type changes and layer moves stay symmetric.** A "Change Type" command
  that finds a HOUSE with no ridge creates one, so its undo removes it again
  (the pre-command item had none); a legacy non-HOUSE shape that already names a
  ridge keeps that exact one-sided link on undo. `MoveToLayerCommand` uses the
  same `linked_ridges_under` walk as delete, so a nested HOUSE's ridge follows
  its group to the target layer. One ownership predicate
  (`roof_ridge_link.is_owned_ridge`, reverse `owner_polygon_id`) is shared by
  the 2D lookup, the 3D snapshot and the sun/shadow caster; a missing reverse
  link stays valid for older plans, a mismatched one is never adopted.

Pinned by `tests/integration/test_house_roof_ridge.py`,
`tests/integration/test_trim_extend_tool.py`,
`tests/integration/test_fillet_chamfer.py`,
`tests/integration/test_mirror_tool.py` and
`tests/integration/test_agent_api_default_on.py`.
