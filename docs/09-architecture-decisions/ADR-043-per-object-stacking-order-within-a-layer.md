---
id: ADR-043
title: "Per-object stacking order within a layer"
status: "Accepted (2026-08-23)"
refs: ["#338"]
legacy_anchor: adr-043-per-object-stacking-order-within-a-layer-issue-338
---

# ADR-043: Per-object stacking order within a layer

**Status**: Accepted (2026-08-23)

**Context**: Every document item's z-value was `layer.z_order * 100` — nothing per-item — set redundantly in `CanvasScene.addItem` and recomputed in `_update_items_z_order`. Same-layer items therefore tied on z and Qt tie-broke by insertion order, so a user had no way to send one object behind another within a layer. The external request (#338) asked for the CAD-standard *Bring to Front / Bring Forward / Send Backward / Send to Back* gesture set, reachable from the context menu, the Properties panel, and keyboard shortcuts, with multi-selection keeping relative order and beds carrying their contained plants as a block.

**Problem**: Beyond the missing feature, the existing all-items-tie-at-one-z design had a **latent, proven bug**: `.ogp` save walked `scene.items()` (Qt's top-first order) and load re-inserted objects in file order — so **every save/load round-trip inverted same-layer stacking** (`lawn → path → bed` reloaded as `bed → path → lawn`). Only the plant-above-bed and ROOF_RIDGE-above-owner cases were band-aided with an explicit `zValue() + 1` pass (failure-archaeology incident 22); every other same-layer pair silently flipped on every reload. `zValue()` itself was never serialized, so there was nothing to round-trip even if the write order had been correct.

**Decision**:
1. **Sparse rank as the sort key.** `GardenItemMixin.stack_order: int | None` (mirrored on `ArcItem`/`BezierItem`, which are not the mixin) is a sparse integer rank, spaced `STACK_STEP = 1024` apart. It is written in exactly four places: `CanvasScene.addItem` (an item with `stack_order is None` gets `max_rank_in_layer + STACK_STEP`), `MoveToLayerCommand` (only items whose layer actually changes get a fresh top rank; same-layer reselection is a true no-op), `ArrangeItemsCommand` (renumbers every item in each affected layer, snapshotting every prior rank for undo), and the one-time post-load renumber inside `CanvasScene.suspend_z_refresh(renumber=True)` (the load path's exit hook) (gives a file saved without `stack_order` — an older app version — honest ranks in file order on first load by the new app). Every other code path only reads `stack_order`.
2. **z is always derived, never stored as intent.** `CanvasScene._normalized_layer_order(layer_id)` builds each layer's bottom→top order from the ranks (`_layer_top_level_items`), then `_refresh_layer_z` sets `item.setZValue(layer.z_order * 100 + 100 * (i + 1) / (n + 1))` over that order — strictly inside `(base, base + 100)` for any `n`, so it can never collide with a fixed overlay band (§8.25 has the full table).
3. **The plant/ROOF_RIDGE clamp is derive-only.** `core.stacking.normalize_order` reorders a layer's list — moving a plant to immediately above its parent bed, a ROOF_RIDGE to immediately above its owner polygon, only when that parent is itself in the same layer — purely for z derivation. It never writes a rank. This is why "Send to Back" on a lone plant stops just above its bed instead of reaching the true bottom of the layer, and why that stop correctly reports as "already at back" rather than a phantom change (`core/stacking.py::_finish` compares *after* normalization).
4. **The z-refresh never writes ranks.** `_refresh_layer_z`/`_update_items_z_order` are pure derivations from whatever ranks already exist; only the four writers in point 1 mutate `stack_order`. This is what keeps every command's undo/redo snapshot exact (see the rejected "rank-writing refresh" alternative below — this was a real draft, caught in design review, not a hypothetical).
5. **Refresh-on-add, suspended for bulk adds.** A single `CanvasScene.addItem` triggers one `_refresh_layer_z` call unless `_suspend_z_refresh` is set. `suspend_z_refresh()` (a context manager; `renumber=True` on the load path) defers that refresh across a whole batch (`CreateItemsCommand`, `DeleteItemsCommand.undo`, `MirrorItemsCommand`, and `ProjectManager.load`), turning what would be an O(n²) bulk add into O(n) plus one refresh. Measured: a 50-item paste into a 2000-object plan went from 316 ms to 91 ms.
6. **Save order is bottom→top; the key is additive.** `ProjectManager._serialize_scene` now iterates `reversed(scene.items())`, fixing the inversion for *every* reader, including older app versions that never look at `stack_order` at all — they simply render in the (now-correct) file order. `stack_order` is written to `_serialize_item`'s dict only when not `None`; a file without the key loads in file order and is renumbered when the load's `suspend_z_refresh(renumber=True)` scope exits. `FILE_VERSION` stays `"1.4"` — no bump.
7. **One apply seam.** `ui/canvas/arrange.py::build_arrange_command(scene, items, mode)` is the only place that groups a selection by layer, asks the Qt-free `core.stacking.arrange` what changes, and builds the undoable `ArrangeItemsCommand`. Every surface — the Edit ▸ Arrange menu, each item's context-menu submenu (`GardenItemMixin._build_arrange_menu`/`_dispatch_arrange`), the Properties panel's Arrange row, and the agent's `arrange_object` tool — calls this one function, the same discipline `ui/canvas/geometry_apply.py` established for resize/rotate (§8.19).
8. **Agent parity.** `arrange_object(item_id, action)` is a token-gated D2 write tool that calls the identical seam, so it inherits the bed-block and plant-clamp behaviour for free and cannot drift from the GUI. It refuses (raises) a no-op — already at front/back, or nothing to step past — rather than reporting a false success. `ObjectRef`/`ObjectDetail.stack_index` (0-based, bottom→top, computed per layer) is the read-only counterpart.

**Rejected alternatives**:

| Option | Why not |
|--------|---------|
| Qt sibling order / `stackBefore` (`QGraphicsItem` child-stacking API) | `QGraphicsItem.stackBefore` only orders *siblings under one parent*; document items are all top-level with no common parent to exploit, and Qt's sibling order isn't itself persisted — it would need the exact same rank-serialization problem solved anyway, for no benefit over an explicit field. |
| A wider z stride per layer (e.g. `z_order * 10000`) instead of a normalized `[0, 100)` fraction | Collides with the app's fixed overlay z bands, several of which already sit well above 100 for a multi-layer plan — dimension lines 900/901, tool overlays 999–1003, preview items 9999, the soil badge 10002, the minimap cut-off 10000 (§8.25.6). A wider per-layer stride would eventually walk into one of those on a plan with enough layers. (Journal pins are excluded from this list: `JournalPinItem` is itself a rank-carrying document item — its `setZValue(9_500)` at construction is overwritten by the very next refresh, a pre-existing gap documented in §8.25.6, not a fixed band this design had to route around.) |
| A refresh that also writes ranks (e.g. renumbering on every `_update_items_z_order` call) | **Caught in design review, not shipped.** A refresh runs on many paths unrelated to an explicit rank change (layer visibility toggle, opacity preview, any unrelated command's cleanup). If it renumbered ranks as a side effect, a command's undo snapshot (taken before `execute()`) would no longer match the ranks in force when `undo()` runs, silently breaking Ctrl+Z for any command that happens to trigger a refresh in between. Ranks are written **only** by the four call sites in Decision point 1. |
| Provisional z assigned at add time, promoted to a real rank later | **Also caught in design review.** A provisional scheme that reserves a z slot on add and finalizes it lazily breaks the moment items are deleted from the middle of a layer — the reserved slots no longer describe a contiguous order, and a later "finalize" pass has no way to distinguish a genuine gap from one it can reuse. The sparse `STACK_STEP` rank (finalized immediately, spacing absorbs future inserts) has no such failure mode. |
| A lone plant free to move anywhere in its layer, independent of its bed | Rejected by the owner in the design session: a plant that could render behind its own bed would be indistinguishable from a plant that isn't actually planted there. The derive-only clamp (Decision point 3) makes "in front of my bed" a structural guarantee, not a convention the user could accidentally violate via Arrange. |

**Consequences**: New `core/stacking.py` (Qt-free), `ui/canvas/arrange.py` (the seam), `ArrangeItemsCommand` in `core/commands.py`; the old `ensure_z_above_parent` helper and its three dead call sites are deleted, its three live call sites replaced by a refresh. `MoveToLayerCommand`, `SetParentBedCommand`, `GroupCommand`/`UngroupCommand`, and `DeleteItemsCommand.undo` all gained refresh calls where an item becomes top-level or re-links without going through `addItem`. Agent API: `list_objects`/`objects_in_region`/`get_object` now document a bottom→top stacking order (previously accidental top-first); `get_diagnostics` is explicitly **not** in that order. Clipboard copy/duplicate now sort by stacking order and carry `layer_id` (previously pasted items were layer-less — a pre-existing gap fixed as a side effect, §11.4). No `FILE_VERSION` change; old files load and re-save correctly under the new order regardless of whether they carry a `stack_order` key. Tests: `tests/unit/test_stacking.py` (the Qt-free algorithm), `tests/integration/test_stacking_roundtrip.py` (the save/load inversion regression + old-file compatibility), `tests/integration/test_arrange_z_order.py` (every mode, undo/redo, bed block, plant clamp, cross-layer), `tests/integration/test_arrange_context_menu.py`/`test_arrange_menu_actions.py`/`test_arrange_properties_panel.py` (the three GUI surfaces), `tests/integration/test_agent_api_writes.py`/`test_agent_api_default_on.py` (the write tool), `tests/unit/test_agent_api_queries.py` (`stack_index`). Cross-refs: FR-STACK, §8.25, §11.4.

## ADR-043 addendum: ground surfaces lie under the sun study (manual pass of PR #584, 2026-10-24)

**Context.** The owner drew a lawn and switched the 2D shadows and Hours of Sun on: both overlays were hidden under the lawn ("objects of height = 0 like grass"). Since US-E3/E4 the shadow overlay (`-500`) and the heatmap (`-450`) sat below every layer item, so anything drawn over the ground, however flat, covered the analysis that is ABOUT the ground. No single overlay z can fix it: the layer bands interleave a lawn in one layer with a tree in another.

**Decision.**
1. **A ground surface is a garden surface without a height.** `core.object_height.lies_on_ground(type, metadata)`: a `LAWN`, `PATH`, `TERRACE_PATIO`, `DRIVEWAY`, `POND_POOL` or `GARDEN_BED` (`GROUND_SURFACE_TYPE_NAMES`) whose `effective_height_cm` is `None` — only stored metadata can give these types a height, and it makes them solids. `canvas_scene.on_ground(item)` adds groups: a group whose every member is a ground surface is drawn in one slot, so it takes the band too. A mixed group normally stays in its layer band above both overlays. A planted bed with linked plants keeps the ground band if its fill is translucent or if its dense polygon has no coverage path at the canvas detail limit. The original shadow is clipped around the plants in that band. An opaque surface with coverage in a mixed group paints the overlays on itself (`CanvasScene.paint_ground_overlays`): the shape items call it at the end of their own paint, the registered sun-study overlay items paint, clipped to the surface's `grid_cover_path`, and `CanvasScene.refresh_ground_overlays` invalidates those surfaces whenever an overlay's picture changes. The shadow, the hours-of-sun fill and its contour layer all use it (#1031). Pinned by `tests/unit/test_object_height.py::TestLiesOnGround` and `test_sun_overlays_on_ground.py`.
2. **Ground surfaces get their own band below the overlays.** `_refresh_layer_z` stays the one z writer; for a ground surface it writes `ground_z(z)` — a strictly increasing map of the layer-band value into `GROUND_Z_RANGE = (-990, -510)` — so ground surfaces keep their order among themselves (layer, then rank) for any number of layers, above the background image and below both overlays. §8.25.2 and §8.25.6.
3. **One band split for drawing and Arrange.** `CanvasScene._band_entries` splits a layer's items into the two bands, ground surfaces first; `_normalized_layer_order` (the drawing) normalizes each band alone, and `build_arrange_command` arranges each band of the selection on that same split (`core.stacking.arrange` unchanged) and renumbers the layer ground first. So a recorded step is always a visible one and ranks agree with the drawing; at the edge of its band an item reports "already at front/back". The derive-only clamp acts inside a band: a plant on an in-ground bed is above it by the band and sorts by its own rank among the other items; the clamp still orders a plant on an edged or raised bed. Two earlier cuts disagreed: over the whole layer a lawn stepped "forward" past a table with nothing visible; with arrange split by band but the drawing normalized over the whole layer, sending a lawn to the back moved a perennial on an in-ground bed under a tree. The agent's `stack_index` and `list_objects` order are "as displayed" and therefore list ground surfaces first; the tool descriptions say so.
4. **The band follows reclassification.** `CanvasScene._restack_ground_changes` runs after every `stack_changed` (execute, undo, redo — every writer of a type, a group or a height commits through a command) and refreshes only the layers whose items' band disagrees with `on_ground`; about 1 ms on 500 items. A `plan_changed` hook was tried and dropped: `plan_changed(int)` connected to `QTimer.start` made the revision the timer's delay, and it would have scanned the plan on every drag frame for a writer that does not exist.

**Rejected alternatives.**

| Option | Why not |
|--------|---------|
| Move the overlays above every layer item, clipped to the footprints of the objects with a height | Annotations (text, callouts, dimension labels in the layer bands) would sink under a translucent overlay; the clip is a second copy of the caster model |
| One overlay per layer | Two overlay items per layer to keep in sync with the controllers' single results, for the same ordering a z band gives |
| Every object without a height that covers ground (the 3D view's ground rule) | Tried, and reverted after review: a cold frame, rain barrel, planter pot or parasol has no height in the plan but stands up — a cold frame on a raised bed sank under the bed, and none of them offers a Height field to lift it back. Generic shapes, often a zone or a highlight placed above a plant by layer, stay in their layer's band until the owner decides otherwise |

**Consequences.** Saved files list ground surfaces first (the serializer writes display order; ranks are saved per item, so older versions reload the same ranks; the committed bench and edge-case fixtures were regenerated — a pure reorder). A ground surface's own label, badges and selection handles are children and lie under the overlays with it, and under any solid that overlaps them (the overlays take no clicks; a handle under a solid cannot be grabbed). Construction lines (`-10`) now draw over ground surfaces instead of hiding under them. A mixed group (a lawn grouped with a bench) keeps its layer's band and its surfaces paint the overlays on themselves (#1031), but is drawn over any top-level ground surface ranked above it — in 2D and in the 3D ground bake. The 3D ground bake follows the scene order, so a generic shape or a height-less standing object ranked under a surface now paints over it on the 3D ground as well (the two views agree). A plant on an in-ground bed sorts by its own rank among the layer's other items instead of next to its bed: a plan saved by an earlier build without being reloaded since can show such a plant under a tree it was drawn over (plans an earlier build loaded and re-saved carry clamp-ordered ranks and do not change), and giving that bed a height moves the plant back next to it. Pinned by `tests/integration/test_sun_overlays_on_ground.py` (export-pipeline pixels: a shadow and the heatmap change the lawn and leave the shed alone; the band follows a height, a type change, undo, layers and a reload).

## ADR-043 addendum: one z derivation per layer, never one per add (#450, 2026-10-24)

**Context.** A loop of 2 000 single `CanvasScene.addItem` calls took 45 s because each add
re-derived z for its whole layer, and the same O(n) derivation sat behind every command
that added an item. The issue's acceptance is "adding n items costs time in proportion to
n, whoever adds them".

**Decision.** The four rank writers do not change, and the derivation stays the only z
writer; what changes is how often it runs. An appended independent solid is given the
derivation's own next value on a **fixed** `Z_POSITION_SCALE` grid inside its layer band
(the divisor is a constant, not `n + 1`, which is what makes an append's value final). Any
item that can re-order items already in the layer — a pre-ranked re-add, a child, a bed
with children, a linked plant, a roof ridge, or a ground surface, which sorts into its own
band — re-derives synchronously. There is no deferred pass and no command-boundary flush:
what `addItem` writes is final, so a loop of any length, direct or one item per command,
costs **one** derivation per layer. Every derivation reseeds the per-layer provisional
cache with the top of its band-space order — a layer-band value, never the highest
`zValue` — because since the ground band (PR #584) a ground surface's z lives in
`GROUND_Z_RANGE`, and seeding from it would put the next added solids below the background.
A rank writer or a layer reorder invalidates the rank and provisional caches.

**Measurements (dev box, 2026-10-24).** 2 000 direct `addItem` calls: 45 s as reported
in #450, 26.3 s reproduced on `master` at this tree (2 000 derivations), about 0.1 s
after (one `_refresh_layer_z` call), also with 1 000–1 500 items already in the layer. 1 000 one-item `CreateItemCommand` executions: 13.09 s before this addendum's final
shape, 3.18 s after (2 000: 12.1 s), still one derivation for the whole loop; the residual is
*not* z work — it is the per-command UI refresh that already existed (`update_dimension_lines`
refreshing every item's lock badge, about 1.8 s of 3.1 s, and PR #584's O(items)
`_restack_ground_changes`, about 1.0 s), each O(n) per command. A per-command loop is
therefore still quadratic, but no longer because of the stacking derivation; the follow-up
is tracked in #592.

**Pins.** `tests/integration/test_canvas_z_batch.py` holds the call count (one for 2 000
adds, one for 200 commands), ordering, uniqueness, band membership, the layer-reorder case,
the parent-bed synchronous case, and `test_a_ground_surface_takes_its_band_at_once_and_seeds_from_it`
for the merge with the ground band.

## ADR-043 addendum — the per-command refresh is scoped to what a command can change (#592, 2026-10-25)

**Context.** The #450 addendum above measured the residual: 1 000 one-item
`CreateItemCommand` executions took 3.18 s because two `stack_changed` listeners walked
the whole scene after every command — `update_dimension_lines` called
`refresh_lock_badge` on every item (each call scanned the whole constraint dict: 360 600
badge refreshes for 600 commands on a 600-item plan), and `_restack_ground_changes`
classified every item (about 1.0 s). Both are independent of what the command changed.

**Decision.** Two indexed/scoped refreshes, no new write path. `ConstraintGraph` gains
`fixed_item_ids()`; `update_dimension_lines` refreshes only items in that set or already
showing a badge (so an unlock clears it), and skips the rest. `Command` gains
`changes_ground_band`, default **True** for safety; the move/resize/rotate/vertex/curve/
copy/link/constraint commands declare `False`. Create is neutral because `addItem`
derives a ground surface's band synchronously and bulk adds end in
`_update_items_z_order`; Delete/Group/Ungroup/Boolean/ChangeProperty keep the scan
because they can change a type, a height or a group.
`CommandManager.last_command` lets the `stack_changed` slot ask what just happened. A
ground surface added one command at a time still gets its band from `addItem`'s own
synchronous derivation, so the neutral `CreateItemCommand` flag does not trade correctness
for speed.

**Measurements (dev box, 2026-10-25).** 600 single-item adds: 0.31 s with the scan, 0.11 s
with the flag (2.8×); a 100-command pin counts zero badge refreshes and zero ground-band
classifications, and still sees the badge on `AddConstraintCommand` and the band change on
`ChangePropertyCommand` (execute and undo).

**Pins.** `tests/integration/test_canvas_command_refresh.py` (zero classifications and
zero badge refreshes for neutral commands; a FIXED constraint refreshes only its item; a
type change still restacks; a move is neutral). PF-CAN-25 and §8.25.4 record the rule.

## ADR-043 addendum — a plant draws above the bed it stands in, linked or not (#629, 2026-10-27)

**Context.** The clamp in `normalize_order` ("a child renders immediately above its
parent") has always been right, and it followed `parent_bed_id` — the LINK. Drawing a bed
AROUND a standing plant makes no link (#443), so the plant stayed below the new parent:
gone behind it in 2D, still drawn on the soil in 3D, and its sun badge (#481/#627) gone
with it. Measured (plant added first, parent drawn around it): z(plant) 0.00001 against
z(parent) 0.00002 for `RAISED_BED`, `CONTAINER`, `CONTAINER_ROUND`, `WALL_PLANTER` and
`TRELLIS`. The in-ground `GARDEN_BED` looked immune only because it is a *ground surface*
and sorts into `GROUND_Z_RANGE` under everything — a `GARDEN_BED` with a stored height is a
solid and hid the plant the same way. The owner's rule, from the manual pass: "plants are
always on top of beds. Needs to be the same for raised beds and planters."

**Decision.** A plant's stacking parent is its LINK, or — when it has none — the SMALLEST
plant-parent in its layer whose outline contains the plant's **stable centre**
(`footprints.standing_point`, the same point the lift and the sun estimate ask;
`footprints.shape_contains`, the app's one containment predicate). It is the choice #481
already made for the sun estimate: geometry over bookkeeping. The derive-only clamp does
the rest, so the plant renders immediately above that parent — in the drawing order and
therefore in hit-testing (a click at the plant's centre finds the plant, not the bed).

Re-derivation, all through the one `_stack_entries`:
- **add**: `_needs_synchronous_z_refresh` now asks `_parent_captures_a_plant(item)` for an
  arriving plant-parent — a bed drawn round a plant re-derives at once, while a bed added
  where no plant stands only appends (600 childless beds added one at a time: 0.24 s, not
  the 2.12 s a blanket synchronous re-derivation cost).
- **arrange**: unchanged — the clamp is applied inside `core.stacking.normalize_order`, so
  Send to Back on a plant stops just above its bed, and the bed's own block carries it.
- **every other command**: a new `Command.changes_containment` flag (default **True**,
  `False` on the create/delete commands, which `addItem` and a deletion make neutral) gates
  `CanvasScene._restack_plant_containment`, a `stack_changed` slot that re-derives a layer
  whose drawing disagrees with the derivation. That covers a bed RESIZED or MOVED around a
  plant, a vertex edit that swallows one, and a plant dragged into a bed — none of which is
  an add. It is NOT gated by `changes_ground_band` (#592), because the commands that change
  containment (move/resize/rotate/vertex) are exactly the ones that set that flag False.

**One answer, checked rather than re-derived.** Which parent a plant takes is
`CanvasScene._derived_plant_parent` — the link, else the smallest containing parent — and
BOTH the derivation (`_stack_entries`) and the per-command check call it. The check is
therefore not a second rule: it compares the plant's z against the parent that function
names, so the two cannot drift (review round 2 found three near-copies of this question
with three different points and caching, and the check rebuilt each parent's
`QPainterPath` per (plant, parent) pair). Two structural details follow from the
derivation and are load-bearing: only a parent of the plant's own BAND counts (an
in-ground bed lies under the plant by the ground band, §8.25.2, not by the clamp — asking
about it re-derived on every command and never changed anything), and the check runs on
the SMALLEST containing parent rather than "any parent above the plant" (the latter marks
a layer stale forever when an outer bed is arranged above an inner one, because the
derivation can only move the plant above the inner one).

**Cost, measured (dev box, 2026-10-27).** `_restack_plant_containment` on the 990-item
reference plan (200 plants, no links): **0.9 ms**; 300 plants in 30 raised beds: 1.1 ms
linked and 2.8 ms unlinked. It is one O(items) classification pass, then per plant: a
single z comparison against the layer's highest parent (a garden whose plants stand above
its beds ends there), the link lookup when the linked parent is in the plant's own band (no
geometry), or - unlinked, or linked into the ground band - a rect prefilter plus the cached
shape test. Shapes are cached for the pass, as
`ItemLookup.shape_of` caches them for a walk: an adversarial plan (200 plants under 50
concave beds whose bounding boxes all cover them) cost **8 ms at 6 vertices, 30 ms at 200
and 133 ms at 1 200**, against 43 / 330 / 1 661 ms for the draft that rebuilt each shape
per (plant, parent) pair. Only a layer that fails the test is re-derived, once. The pinned
budgets are untouched: the paint gate, the ground-bake G3 gate (it times the bake, not the
command), the caster walk and the snapshot.

**Known limits, stated.** (a) One-way: the check asks whether the plant is BELOW the
parent the derivation names, so a plant that LEAVES a bed keeps the higher z it was given
while inside — harmless (a plant above a bed it is not in hides nothing) and it is what
keeps the scan a one-way test. (b) Containment is asked of the plant's CENTRE, so a plant
straddling a bed's edge with its centre outside is not clamped (it is beside the bed, not
in it). (c) The clamp follows the SMALLEST containing parent, so a larger parent that also
contains the plant — arranged above that one, or simply added after it — still covers it:
the derive-only clamp cannot fix that, because `normalize_order` only ever moves a plant
above its one parent, so a second containing parent above it stays where it is. (d)
Stacking is geometric, and since #443 so is the link: a bed drawn around an unlinked plant
is a stacking parent AND the create command links the plant, so
`footprints.item_base_cm` (ADR-037 decision 5) lifts it by the bed's soil. The lift still
requires the link to name a visible solid whose outline contains the plant, so an explicit
Link action that geometry does not support is the one state where a plant is drawn above a
bed and stands on the floor — a user decision, not a stale link. It is stated in
FR-STACK-10's design and FR-SUN-11.
(e) Only plants: a pot standing on a raised bed is not clamped to it by geometry (the app
parents only plants, ADR-037 decision 5), and a `GARDEN_BED` that becomes a ground surface
again by losing its height simply drops out of the parent set.

**Pins.** `tests/integration/test_plant_above_parent_stacking.py` — every parent type (a
parametrised matrix over `RAISED_BED`/`CONTAINER`/`CONTAINER_ROUND`/`WALL_PLANTER`/
`TRELLIS`/`GARDEN_BED`) keeps an existing plant on top both in z and as the item a click
finds through a real `CanvasView`; an L-shaped bed clamps a plant in its arm but not in its
notch; a distant bed does not clamp; the linked case is unchanged; a plant moved into a bed
by `MoveItemsCommand` comes above it (and undo leaves it outside, with the note above); a
bed grown around a plant is raised by a real `ResizeItemCommand` - through the command's
own slot, not a hand-made call; a healthy layer asks `shape_contains` **and**
`standing_point` zero times (the centre is asked lazily); one pass builds each parent's
path **once** (counted: five concave beds over twenty plants in the notch, five builds —
the per-(plant, parent) rebuild this addendum measures fails at 100); the
`changes_containment` table is re-derived from `core.commands` (every command class but the
three neutral ones must keep the default, and the neutral set is named), and a create is
pinned to skip the scan while a move runs it. The cost itself is a budget in
`tests/perf/test_nfr_budgets.py::TestNfrPerf01ContainmentScanBudget` (linked and
unlinked). The drift guards in
`tests/integration/test_scene3d_base_stacking.py` name the new users of `standing_point`
and `contains_path`. `tests/unit/test_plant_bed_relationship.py`'s rank-symmetry test now
puts its plant OUTSIDE the bed, because a contained plant is clamped by geometry and the
pre-attach assertion would stop being falsifiable.

## ADR-043 addendum - a group is one layered unit (manual test 2.7 of PR #713, 2026-11-04)

**Context.** A group stores its own `layer_id`, but its members kept the layer they
were drawn on. `MoveToLayerCommand` moved only the selected wrapper (and, since #690,
a nested HOUSE's ridge), so `_apply_item_visibility` still hid each member by its own
layer: the owner moved a group from layer 1 to layer 2, hid layer 1, and the group's
house and rectangle disappeared while the group wrapper and its ridge stayed. The
saved plan recorded exactly that split (group and ridge on layer 2, both shapes on
layer 1).

**Decision.** A group is the layered unit for everything it contains.
`MoveToLayerCommand` walks `selection_tree` and writes the target layer to every
member as well (undo restores each member's own layer), so hiding either layer and
ungrouping agree with what was on screen; `UngroupCommand` likewise puts each
member on the group's layer and restores its own on undo. `_apply_item_visibility` resolves a grouped
item's effective layer through its outermost group ancestor, so a plan saved before
this fix - like the owner's - also renders as one unit instead of relying on a
migration. Pinned by `tests/integration/test_house_roof_ridge.py`'s
`test_a_group_controls_its_members_visibility_by_its_own_layer` and the extended
layer-move test.

**Known gap (follow-up #741).** Grouping two objects drawn on different layers
does not consolidate the second member's free-standing `ROOF_RIDGE` onto the
group's layer; only a Move to Layer normalises the whole tree. The visibility
walk above resolves Qt ancestors, not a ridge's owner through a group. Move the
group once to repair a legacy plan.
