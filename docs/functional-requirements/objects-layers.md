---
title: "Objects and layers"
prefixes: ["FR-OBJ", "FR-LAYER", "FR-STACK", "FR-BED", "FR-CONTAINER"]
---

# Objects and layers

## Objects

- **FR-OBJ-01**: Each object type has appropriate default styling. For polylines, changing type through Properties or the context menu applies the new type's defaults and clears the old preset. Undo restores the previous type, preset and exact stroke; lines retain round caps and joins. Preset selection undo restores the previous pen. Styled details remain fully visible through the canvas cache, consistent with uncached output (#524, #525, #526, #471; section 8.30).
- **FR-OBJ-02**: Objects are first-class entities with editable metadata
- **FR-OBJ-03**: Objects can have custom name/label displayed on canvas
- **FR-OBJ-04**: Object metadata shown in properties panel when selected
- **FR-OBJ-05**: Outdoor furniture: table (rectangular, round), chair, bench, parasol/umbrella, lounger, BBQ/grill, fire pit, planter/pot, sandbox, trampoline, hot tub, swing, picnic table and hammock.
- **FR-OBJ-06**: Garden infrastructure: raised bed, compost bin, greenhouse, cold frame, rain barrel, water tap, tool shed, wheelbarrow, pergola, bird bath, garden light and string lights.
- **FR-OBJ-07**: Path styles: gravel, stepping stones, paved, wooden boardwalk and dirt.
- **FR-OBJ-08**: Fence styles: wooden, board, metal/wrought iron, chain link, hedge (living fence) and stone wall.

- **FR-OBJ-09**: Pre-defined object types for common property elements:

  | Object Type | Default Properties | Representation |
  |-------------|-------------------|----------------|
  | **House** | Footprint polygon, name | Filled polygon with roof texture option |
  | **Garage/Shed** | Footprint polygon, name | Filled polygon |
  | **Fence** | Polyline, height, material | Line with fence pattern |
  | **Wall** | Polyline, height, thickness | Thick line with fill |
  | **Path** | Polyline, width, material | Stroked path with texture |
  | **Terrace/Patio** | Polygon, material | Filled polygon with texture |
  | **Driveway** | Polygon, material | Filled polygon with texture |
  | **Pond/Pool** | Polygon, depth | Filled polygon with water texture |
  | **Greenhouse** | Polygon, dimensions | Filled polygon with glass texture |

## Layers

- **FR-LAYER-01**: Support multiple layers (minimum: Background, Property, Hardscape, Plants, Annotations)
- **FR-LAYER-02**: Default layers created with new project, user can add custom layers
- **FR-LAYER-03**: Layer visibility toggle
- **FR-LAYER-04**: Layer lock toggle (prevent editing)
- **FR-LAYER-05**: Layer opacity
- **FR-LAYER-06**: Layer reordering (drag in layer panel)
- **FR-LAYER-07**: Assign objects to layers (default based on object type, manual override). A **group is one layered unit**: moving it to another layer carries its members and their derived roof ridges, and hiding a member's old layer does not hide a group now on another layer - undo restores every member's original layer.
- **FR-LAYER-08**: New layers are created at the top of the layer order and become the active layer, so newly drawn elements stay visible and selectable (issue #201)
- **FR-LAYER-09**: All layer operations are undoable via Ctrl+Z/Ctrl+Y: create, delete (including the item reassignment it causes), rename, reorder, visibility, lock, and opacity — an opacity slider drag coalesces into a single undo step
- **FR-LAYER-10**: One undoable idempotent seven-layer preset retains active/existing layers and uses semantic tags independent of names. The undoable per-project auto-assignment setting defaults off; only future drops/stamps use matching visible/unlocked layers.

## Stacking order

- **FR-STACK-01**: A selected object (or multi-selection) can be **Brought to Front**, **Brought Forward**, **Sent Backward**, or **Sent to Back** — reordering it **within its own layer only**, never across layers. Reachable from: the Edit ▸ Arrange menu (`Ctrl+Shift+]` / `Ctrl+]` / `Ctrl+[` / `Ctrl+Shift+[`, mirrored by `Ctrl+Shift+Up` / `Ctrl+Up` / `Ctrl+Down` / `Ctrl+Shift+Down` on every action); each item's right-click context menu (`Arrange ▸` submenu, on every shape sharing the `GardenItemMixin` context-menu seam — rectangle, polygon, polyline, circle, ellipse, text, callout, group — plus arcs/beziers via the menu/shortcut without a context-menu entry); and the Properties panel's "Arrange" row (four icon buttons), shown for a single selected item and for a multi-selection.
- **FR-STACK-02**: A multi-selection keeps its members' **relative order** when arranged as a block; a selection spanning multiple layers is arranged one layer at a time (each layer's block moves within that layer only) but the whole gesture is **one undo step**.
- **FR-STACK-03**: A bed/container carries its **contained plants along as one block** — their relative order among themselves is preserved. A plant cannot be arranged **below its own bed**: `Send to Back`/`Send Backward` on a lone plant stops just above its bed, and if it is already there the action reports "already at back" rather than silently doing nothing. The same clamp applies to a `ROOF_RIDGE` and its owner polygon.
- **FR-STACK-04**: `Bring Forward`/`Send Backward` step the selection past the single **nearest item in the same layer whose scene bounding rect overlaps any member of the block** — a non-overlapping neighbour is skipped entirely. When there is no such item (or the block is already at the front/back of its layer), the action is a no-op and the status bar reports which: "Already at front", "Already at back", "No overlapping object in front", "No overlapping object behind", or "Select an object to arrange" for an empty/ineligible selection. A no-op pushes **nothing** onto the undo stack.
- **FR-STACK-05**: Every successful arrange is exactly **one undo step** (`ArrangeItemsCommand`), regardless of how many layers or how many items were affected.
- **FR-STACK-06**: Stacking order is persisted: `.ogp` objects are written **bottom→top** (fixing a pre-existing bug where every save/load round-trip inverted same-layer stacking) and each object carries an additive `stack_order` key when ranked. `FILE_VERSION` is unchanged — a file without the key loads in file order and is given honest ranks on that first load; a file with the key round-trips exactly. Copy/duplicate/paste preserve relative stacking order and the source layer (previously a pasted item was layer-less).
- **FR-STACK-07**: Journal pins are **not arrangeable** — no context-menu entry, no menu/shortcut effect, and the Properties panel shows no Arrange row for a pin-only selection. The Agent API's `arrange_object` refuses a pin the same way it refuses a locked-layer or group-member item.
- **FR-STACK-08**: The Agent API exposes a token-gated write tool `arrange_object(item_id, action)` with `action` one of `bring_to_front`/`bring_forward`/`send_backward`/`send_to_back`, applying exactly one undoable command through the same seam the GUI uses (bed block and plant clamp included) and raising on a no-op instead of reporting a false success. `ObjectRef`/`ObjectDetail` carry a read-only `stack_index` (0-based position within the object's layer, bottom→top, as displayed — compare only within one layer); `list_objects`/`objects_in_region`/`get_object` are documented as bottom→top in stacking order (`get_diagnostics` is not).
- **FR-STACK-09** (manual pass of PR #584): A **ground surface** — a lawn, path, terrace, driveway, pond or in-ground bed with no height of its own, or a group made only of those — is drawn under every other object of every layer and under the sun study's shadows and hours-of-sun map, which lie on it as on the ground (FR-SUN-03, FR-SUN-05). A group paints in one z slot, so a surface grouped with a solid cannot stay under an overlay while the solid stays above it; an opaque surface in such a group paints the shadow and the map on itself, clipped to its own cover, and is repainted when they change (#1031). Among themselves the ground surfaces keep their stacking (layer order, then position). Arrange works inside each band: a ground surface steps past, or is brought in front of, the ground surfaces of its layer only — brought to the front, it is the front-most of them, still under the layer's other objects — and any other object never steps past a ground surface; at the edge of its band an object reports "already at front/back" and nothing is recorded. The Agent API's `stack_index` reports the position as drawn. Objects that stand up without a height in the plan (a cold frame, a rain barrel), generic shapes, texts and callouts are not ground surfaces. A height (FR-SUN-02) makes such an object a solid that is stacked like any other; setting or clearing it, or changing the object's type, moves it at once and undoes in the same step.
- **FR-STACK-10** (#629, ADR-043 addendum): A **plant** is drawn above the bed, raised bed, container, round container, wall planter or trellis it stands in — whether or not the link was made (FR-SUN-11's membership). Its stacking parent is its linked parent, or, with no link, the smallest plant-parent in its layer whose outline contains the plant's stable centre (`footprints.standing_point`, the point the lift and the sun estimate ask); the app's derive-only clamp then renders it immediately above that parent, so it is visible and a click at its centre selects it rather than the parent. It is re-derived when a plant-parent arrives around it, after every command that can move, resize, rotate, vertex-edit or re-type an item (`Command.changes_containment`; adds and deletes are neutral because `addItem` derives an arriving parent synchronously and a deletion cannot newly hide a plant), and on arrange. A plant that leaves a bed keeps the higher z it was given (it hides nothing — the clamp never lowers). Only plants: another object standing on a bed follows the ordinary per-object order. This is the visible half of the same geometric choice FR-SUN-09 makes for the estimate. Inspectable through the Agent API as `stack_index` (the serialized order is the drawing order). **Known limits:** (a) the clamp follows the SMALLEST containing parent, so a larger parent that also contains the plant — arranged above that one, or simply added after it — still covers it (the derive-only clamp moves a plant above one parent only); (b) stacking is geometric and, since #443, so is the membership: `item_base_cm` (FR-SUN-02) requires the LINK, and every edit path now re-decides it from the same stable centre — so a bed drawn around a plant, a moved plant and a copy all stand on the soil their geometry names. An explicit Link action that geometry does not support still stands on the floor (FR-SUN-11).

Acceptance: `tests/unit/test_stacking.py` (the Qt-free arrange algorithm — normalization, block expansion, all four modes, every outcome), `tests/integration/test_stacking_roundtrip.py` (the save/load inversion regression, rank round-trip, old-file compatibility, paste/duplicate ordering), `tests/integration/test_arrange_z_order.py` (every mode, undo/redo, multi-selection, bed block, plant clamp, cross-layer, move-to-layer interaction), `tests/integration/test_arrange_context_menu.py`, `tests/integration/test_arrange_menu_actions.py`, `tests/integration/test_arrange_properties_panel.py`, `tests/integration/test_agent_api_writes.py`, `tests/integration/test_agent_api_default_on.py`, `tests/unit/test_agent_api_queries.py`. FR-STACK-10's geometric clamp: `tests/integration/test_plant_above_parent_stacking.py`.

## Garden beds

- **FR-BED-01**: Bed object type (polygon) for vegetable/flower beds
- **FR-BED-02**: Bed metadata: name, soil type, raised (yes/no), height if raised
- **FR-BED-03**: Beds can contain plant objects (visual grouping)
- **FR-BED-04**: Bed area automatically calculated and displayed
- **FR-BED-05**: Grid subdivision display option for planting layout

## Vertical and container gardening

- **FR-CONTAINER-01**: A new toolbar category **"Vertical & Container"** offers **Container** (rectangular pot), **Round Container**, **Wall Planter**, and **Trellis**. They are plain shape items (`RectangleItem`/`CircleItem`) tagged with the new `ObjectType`s `CONTAINER`/`CONTAINER_ROUND`/`WALL_PLANTER`/`TRELLIS` — the same pattern as `RAISED_BED`, so they reuse all existing shape/serialization/resize machinery (ADR-031).
- **FR-CONTAINER-02**: Containers and wall planters are **soil-capable plant-parents**: `is_bed_type()` (the soil predicate) now includes them, so they get soil tests, plant-soil mismatch borders, amendment recommendations, and the bed context menu. Plants dropped inside become children via the existing `find_smallest_bed_containing` reparenting path.
- **FR-CONTAINER-03**: A **trellis** is a plant-parent that holds **no soil**: `is_plant_parent_type()` (= soil containers + trellis) gates reparenting/drag-propagation/contained-plants, while the trellis is excluded from every soil feature.
- **FR-CONTAINER-04**: Containers carry material (terracotta/plastic/wood/metal), drainage (yes/no), fill height (cm), and an optional explicit soil-volume override — all stored as additive `metadata` keys (`container_material`, `container_drainage`, `container_height_cm`, `container_soil_volume_l`). **No `FILE_VERSION` bump**; pre-C3 files load unchanged.
- **FR-CONTAINER-05**: The properties panel shows a **Container** section (material, drainage, height, soil volume) with a live **watering hint** derived from material + drainage, plus the effective soil volume. Soil volume auto-computes from footprint × height (litres) unless overridden. Math lives in the Qt-free `core/container_model.py`; the shopping-list "Soil fill" volume uses container height (litres) for containers instead of bed soil-depth.
- **FR-CONTAINER-06**: When the combined footprint of a container's child plants exceeds the container footprint, a **capacity-overrun badge** (red warning triangle) appears on the container — reusing the badge mechanism (`GardenItemMixin.set_capacity_overrun`, computed by `application._update_container_capacity` on the same triggers as spacing overlaps).
- **FR-CONTAINER-07**: All object names, the category, and container UI strings are localized; the watering-hint matrix is registered under the `ContainerModel` i18n context.
- **FR-CONTAINER-08** (US-C3b): Right-clicking a **trellis** shows a context menu with **Log Pest/Disease**, **Log Harvest**, and **Plan Succession** (climbers get pests, are harvested, and can be succession-planted) but **no** Grid toggle or Soil test. Implemented via a `supports_soil=False` flag on `build_bed_context_menu`, with the shape-item menu guard on `is_plant_parent_type`.
- **FR-CONTAINER-09** (US-C3b): The plant **spacing-overlap** warning for children of a **trellis** is measured in 1-D — only along the trellis's long (rotation-aware) axis; the perpendicular/canvas-Y offset is ignored (real vertical height is metadata, not canvas geometry). Two climbers close along the bar overlap regardless of their canvas-Y offset; climbers far apart along the bar do not. Bed children remain 2-D Euclidean.
