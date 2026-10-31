# Pitfalls: persistence, undo and layers

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-PER-01

- **Rule:** Clipboard copy and paste go through the one `ProjectManager` serializer that save and load use, because a second serializer for the same vocabulary drifts and silently loses data.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #400
- **Status:** standing
- **Legacy:** b1faaa9 README L178

- **Two divergent item serializers create silent data-loss gaps on clipboard operations; unify under one chokepoint.** (Issue #400, AUD-002, TD-018): `CanvasView` maintained its own separate ~500-line item serializer and deserializer (`_serialize_item`, `_serialize_item_core`, `_deserialize_item`) that diverged from `ProjectManager`. The clipboard serializer dropped `spacing_radius_cm` overrides, `frost_protection_needed`, `label_visible`, and `path_fence_style`, and silently skipped newer geometric types entirely (Arc, Bezier, Groups). The fix eliminated the duplicated serializer completely: `CanvasView` now delegates all item serialization and deserialization directly to `ProjectManager`'s static methods. UUID stripping and geometry offsetting (`_strip_item_ids`, `_offset_item_dict`) are handled uniformly by pure helpers before pasting/patterning. Lesson: having two serialization paths for the same data vocabulary guarantees divergence over time; one authoritative serializer must back both file I/O and clipboard operations.

### PF-PER-02

- **Rule:** A failed plan load must leave no partial scene behind a stale file path: deserialize in memory first, clear `_current_file` on failure, and keep the autosave until the new plan loads.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #403
- **Status:** pointer → [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling)
- **Legacy:** b1faaa9 README L179

Held in [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-03

- **Rule:** A missing or undecodable background image loads as a placeholder that saves its original data back, so a momentarily unreadable asset is never dropped on the next save.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #397
- **Status:** pointer → [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling)
- **Legacy:** b1faaa9 README L180

Held in [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-04

- **Rule:** `CommandManager.command_executed` fires only on `execute()`, so dimension line updates also connect to `can_undo_changed` and `can_redo_changed` to follow undo and redo.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L274

- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.

### PF-PER-05

- **Rule:** Retired: every attach site used to lift a plant above its bed with an explicit `ensure_z_above_parent` z bump, and the code no longer writes z, deriving it from persisted stacking ranks instead.
- **Pinned by:** none — The entry is retired, and its body names no test.
- **Source:** #338
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l306-plants-stack-behind-beds-when-both-share-a-layers-default-z)
- **Legacy:** b1faaa9 README L306

### PF-PER-06

- **Rule:** A CSV meant for Excel is written as `utf-8-sig`, because Excel on Windows reads UTF-8 without a BOM as Latin-1 and garbles umlauts.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L316

- **Excel reads UTF-8 CSV as Latin-1 unless a BOM is present**: A bare `encoding="utf-8"` write produces correct bytes but Excel on Windows still mojibakes German Umlauts (`Tüte` → `TÃ¼te`). Use `encoding="utf-8-sig"` for any CSV the user is expected to open in Excel. Python's own `csv` module strips the BOM transparently on read with either `utf-8` or `utf-8-sig`, so existing tests don't need to change. The BOM byte sequence is `b"\xef\xbb\xbf"` if you need to assert it directly.

### PF-PER-07

- **Rule:** A panel that changes model state a derived overlay reads must also reach `scene.changed` or `stack_changed`, for example via `item.update()`, because `mark_dirty()` alone never repaints.
- **Pinned by:** `tests/integration/test_plant_growth_wiring.py::TestPanelEditReachesTheShadow`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L323

- **A panel that writes item `metadata` directly reaches neither `scene.changed` nor `stack_changed` — every derived overlay goes stale**: `PlantDatabasePanel._update_instance_metadata` writes `plant_instance` keys (`planting_date`, `current_height_cm`, `current_spread_cm`) straight into `item.metadata` and then calls only `mark_dirty()`. A metadata write repaints nothing, so `QGraphicsScene.changed` never fires; and because the edit bypasses the command manager, `stack_changed` never fires either. `SunShadowController` subscribes to exactly those two. Once US-E8 made `current_height_cm` load-bearing for shadow casting, editing the field left the shadow at the **old** size until some unrelated repaint (changing the selection, say) happened to nudge it — intermittent, which reads as a bug rather than a delay. **Fix**: call `item.update()` after the metadata write, so the existing `scene.changed → schedule_recompute` path runs. **Rule**: if a panel mutates model state that a derived overlay reads, it must emit on one of the two channels overlays actually listen to — `mark_dirty()` alone only *saves* the change, it never *shows* it. Pinned by `tests/integration/test_plant_growth_wiring.py`, which takes its `recompute_count` baseline only after the scene has **settled**: creating the overlay is itself a scene change, so an unsettled baseline makes the assertion pass against the unfixed code (the first cut of that test did exactly that). Note these fields still have no undo — they have never gone through a `Command` (pre-existing).

### PF-PER-08

- **Rule:** The layers panel is a pure view that never mutates `Layer` objects or its own list; every layer change goes from a request signal through an undoable command in `core/commands.py`.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #201, #209
- **Status:** standing
- **Legacy:** b1faaa9 README L345

- **Layer subsystem: panel is a pure view; ALL mutations go through undoable commands** (issue #201 + layer-undo fix): historically `LayersPanel` mutated layers directly and `panel._layers` *aliased* `scene._layers` (the scene hands its live list to `panel.set_layers()`), so panel-side inserts mutated the scene before any signal fired — and none of it was undoable (Ctrl+Z silently ignored every layer action). Both are fixed: `LayersPanel.set_layers` now stores a **defensive copy** (`list(layers)`), and every layer operation (add, delete, rename, reorder, visibility, lock, opacity) routes panel request-signal → `GardenPlannerApp` handler → `CommandManager.execute(<LayerCommand>)` → scene mutation → `layers_changed` → `panel.set_layers` rebuild. Rules for any new code touching this subsystem: (1) the panel must NEVER mutate `Layer` objects or its `_layers` list — emit a request signal and let a command in `core/commands.py` (`AddLayerCommand`, `DeleteLayerCommand`, `RenameLayerCommand`, `ReorderLayersCommand`, `SetLayerPropertyCommand`) do the work; the rebuild repaints the widgets. Emit as the **last** statement of a `LayerListItem` handler — the synchronous command → rebuild deletes the emitting widget. (2) `_refresh_list` restores selection by **layer id**, never row index — a top-insert shifts every row down one. (3) Undo of add/delete restores the previously active layer by calling `set_active_layer` **last**, after `layers_changed.emit()` — the panel rebuild's fallback `setCurrentRow(0)` fires first and would otherwise win; the scene's `active_layer_changed → panel.select_layer` connection (signal-blocked) re-syncs the visible selection. (4) Opacity slider drags coalesce into one undo step: `valueChanged` while `isSliderDown()` drives the non-undoable `scene.preview_layer_opacity()` (no `layers_changed`, so no rebuild storm per tick); `sliderReleased` commits one `SetLayerPropertyCommand` carrying the opacity snapshotted at `sliderPressed`. (5) `CanvasScene.add_layer()` *appends* (bottom) and is for bulk/import only (DXF); `CanvasScene.remove_layer()` is likewise a non-undoable primitive — neither is the user-facing path. (6) Command `description` strings are user-visible (status bar "Undo: …") and use `QCoreApplication.translate("Commands", …)` + registration in `scripts/fill_translations.py`. (As of issue #209 **all** command descriptions — not just the layer ones — use this pattern; the former English f-strings have been migrated, including the caller-supplied descriptions of `AlignItemsCommand`/`MultiVertexMoveCommand`, which are wrapped at their call sites in `canvas_view.py`/`properties_panel.py`.)

### PF-PER-09

- **Rule:** An undoable command revalidates its mutable preconditions, such as a replacement layer's lock, immediately before every mutation including redo, not only in its constructor.
- **Pinned by:** `tests/unit/test_commands.py::test_redo_refuses_newly_locked_replacement_and_preserves_redo`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L347

- **Undoable layer preconditions must be revalidated on redo** (US-D2.4): `DeleteLayerCommand` originally checked its replacement layer's lock only in `__init__`. The sequence delete → undo → lock replacement → redo then bypassed the protection because redo re-executed the existing command. The command now checks immediately before mutation, and `CommandManager.redo()` restores a refused command to the redo stack. Regression: `tests/unit/test_commands.py::TestDeleteLayerCommand::test_redo_refuses_newly_locked_replacement_and_preserves_redo`. General rule: mutable protections belong at every mutation boundary, including redo; constructor validation is not enough.

### PF-PER-10

- **Rule:** Only `execute()` and `register_applied()` put a command on the undo stack, both emitting the full signal set, and undo and redo emit `stack_changed` so every change dirties the document.
- **Pinned by:** `tests/integration/test_undo_redo_dirty.py`
- **Source:** #209
- **Status:** standing
- **Legacy:** b1faaa9 README L356

- **Undo/redo must dirty the document — and so must every "already-applied" edit; route them all through one chokepoint** (issue #209): `CommandManager.execute()` emits `command_executed`, but `undo()`/`redo()` historically emitted only `can_undo_changed`/`can_redo_changed`. Because `mark_dirty` was wired to `command_executed` ([application.py](../../../src/open_garden_planner/app/application.py)), undoing or redoing after a save left the title bar's `*` marker (and the close-time "unsaved changes" prompt) believing the document was clean — closing then **silently discarded** the change. Repro: draw → save → Ctrl+Z → title shows no `*`, close prompts nothing. Fix: a dedicated `stack_changed` signal on `CommandManager` (emitted by `execute`/`undo`/`redo`, **not** `clear()` — clearing happens on new/load and must stay clean) wired to `mark_dirty`. A dedicated signal, not "also emit `command_executed` from undo/redo", because the constraints/properties/dimension-line refreshes are *already* separately wired to `can_undo_changed`/`can_redo_changed` (firing `command_executed` too would double-fire them) and the calendar refresh would newly fire.

  **The trap that made this a two-part fix:** `command_executed` was *load-bearing* for dirtiness far beyond `execute()`. ~30 interactive-edit sites across `canvas_view.py`, `properties_panel.py`, `garden_item.py`, and the item modules (`resize_handle.py`, `circle_item.py`, `rectangle_item.py`, `ellipse_item.py`, `polygon_item.py`, `polyline_item.py`) use the "move already applied, just register undo without re-executing" pattern: they reached into `cm._undo_stack.append(cmd)` directly and hand-emitted `command_executed` to mark dirty. Moving `mark_dirty` to `stack_changed` un-dirtied every one of them (drag a resize handle / vertex / edit a radius → no `*`, close discards). Naively the new integration test still passed because it only exercised the `RectangleTool` → `execute()` path. Real fix: a single `CommandManager.register_applied(command)` chokepoint that does the append + redo-clear + **all** signal emits (including `command_executed` *and* `stack_changed`); every former direct-append site now calls it. Lesson: there must be exactly **two** ways onto the undo stack — `execute()` (runs the command) and `register_applied()` (command already applied) — and both emit the full signal set. Never hand-roll `_undo_stack.append` at a call site; the moment you change what `execute()` emits you create silent contract drift with every copy. Regression tests: `tests/integration/test_undo_redo_dirty.py` covers both an `execute()` path *and* a `register_applied` resize path.

### PF-PER-11

- **Rule:** Every `ResizeItemCommand` caller, including each `partner_resizes` applier, uses the one apply function in `ui/canvas/geometry_apply.py`, and its tests run over non-zero rotations where drift shows.
- **Pinned by:** `tests/integration/test_geometry_apply_shared_path.py`
- **Source:** #218, #326
- **Status:** standing
- **Legacy:** b1faaa9 README L412

- **A bug that is exactly 0 at the default value hides forever — and a `Callable` parameter is where two implementations of one behaviour go to drift** (US-D2.2 #326, 2026-08-18): `ResizeItemCommand` and `RotateItemCommand` take a caller-supplied `apply_func`, so every call site wrote its own closure. And `ResizeItemCommand` accepts **two** callables, not one — `apply_func` plus each `partner_resizes` entry's apply function, both run on execute and undo — so the call sites were: three numeric-entry branches in `properties_panel`, a drag-release handler on each item class, `RectVertexEditMixin._move_corner_to`/`_on_corner_move_end` in `resize_handle.py`, and the EQUAL-constraint partner appliers in `core/tools/constraint_tool.py`. When #218 added `setTransformOriginPoint(rect().center())` to keep the rotation pivot on the new centre, it landed in the **item-class drag-release** copies only. The panel's copies kept resizing without re-pinning, so a **rotated** object resized by typing a number pivoted about a point that was no longer its centre. Measured: a `TREE` at (200, 200) rotated 30°, resized 50 → 100 cm through the panel's own code, ended up centred at (263.4, 163.4) — **73.2 cm** away, and it then *saves* that position. Two lessons. (1) **At rotation 0 the drift is exactly 0.0**, and the overwhelming majority of objects are never rotated, so every existing test and every manual pass since #218 was blind to it; when a defect's magnitude is proportional to a parameter that is usually at its neutral value, coverage of the neutral case proves nothing — parametrise the test over the parameter (here `[0, 30, 90, 215]°`). (2) The bug was not found by looking for it: it surfaced because US-D2.2 needed a *third* caller and the extraction forced a byte-level comparison of the existing two. **A `Callable` injection point with N call sites is N implementations of one behaviour**, and nothing in the type system will tell you when one of them stops matching the others — if you are about to become caller N+1, diff callers 1..N first. Fix: `ui/canvas/geometry_apply.py` now holds the one apply function, and **its module docstring is the authoritative list of callers and exceptions** (stated there only — the five paraphrases of it drifted into three inconsistent answers during review, proving the point); `tests/integration/test_geometry_apply_shared_path.py` pins it, and was verified to fail with the re-pin removed (17 tests go red when the re-pin is removed; 10 when the guard was first written). **(3) The first pass converted most call sites and then asserted completeness in six documents — and missed two.** `RectVertexEditMixin._move_corner_to` had the identical omission and was found only by the senior review, because its call site lives in `resize_handle.py` rather than in an item class: measured 640 cm of stale origin and a 331 cm disagreement between the stored and visual centres on a 30° rectangle. The second miss was worse: the EQUAL-constraint partner appliers, reached through `ResizeItemCommand`'s *other* callable parameter (`partner_resizes`), carrying the same rotation bug — 70.7 cm at 90°. An extraction that claims "every caller" is worse than one that names its exceptions, because the next reader stops looking; grep the constructor (`ResizeItemCommand(`) and enumerate **every callable it accepts, including the ones passed in a list**, rather than reasoning from the files you happened to open.

### PF-PER-12

- **Rule:** The serializer writes scene objects bottom to top with `reversed(scene.items())`, because `scene.items()` is top-first and a load re-adds objects bottom-up in file order.
- **Pinned by:** `tests/integration/test_stacking_roundtrip.py::test_stacking_order_survives_save_load_roundtrip`; `tests/integration/test_stacking_roundtrip.py::test_explicit_ranks_round_trip`; `tests/integration/test_stacking_roundtrip.py::test_old_format_file_without_stack_order_loads_in_file_order`
- **Source:** #338
- **Status:** standing
- **Legacy:** b1faaa9 README L414

- **Same-layer stacking inverted on every save/load** (#338): a plan drawn as `lawn → path → bed` (bottom to top) reloaded as `bed → path → lawn` — every same-layer pair silently flipped on every `.ogp` round-trip, and had done so since layers existed. Root cause: `ProjectManager._serialize_scene` walked `scene.items()`, which is Qt's **top-first** order, and wrote objects to the file in that order; load then re-inserted them via `scene.addItem()` in **file order**, which `addItem` stacks bottom-up — so the file's top-first write order became the load's bottom-first read order, exactly reversing every same-z tie. Only the plant-above-bed and ROOF_RIDGE-above-owner cases were ever band-aided (an explicit `zValue() + 1` pass — failure-archaeology incident 22); every other same-layer pair (two beds, a lawn and a path, …) had no such band-aid and simply inverted, unnoticed, because nothing before #338 gave the user a reason to care which of two untied objects was "in front". Fix: `_serialize_scene` now iterates `reversed(scene.items())`, writing objects bottom→top — which also fixes every *older* app version's reads, since they load in file order the same way. Combined with the new persisted `stack_order` rank (ADR-043), a round-trip through the current app is now exact; a round-trip through an app that predates #338 loads in (now-correct) file order and simply has no explicit ranks to preserve. Pinned by `tests/integration/test_stacking_roundtrip.py` (the inversion regression, ranks round-trip, an old file without the `stack_order` key loads in file order). Lesson: a serializer that iterates a Qt container's *default* order without checking what that order means (top-first vs. bottom-first) will silently invert on the next read — never assume `scene.items()`'s order is "the" order without naming which end is first.

### PF-PER-13

- **Rule:** A pasted or duplicated item takes its source's `layer_id` when that layer still resolves in the target scene, else the active layer, so it never lands silently layer-less.
- **Pinned by:** `tests/integration/test_stacking_roundtrip.py::TestPasteDuplicatePreservesStacking`
- **Source:** #338
- **Status:** standing
- **Legacy:** b1faaa9 README L416

- **Clipboard-pasted items were layer-less** (#338, found while implementing stacking order): `CanvasView.copy_selected`/`duplicate_selected` never saved `layer_id`, and `_deserialize_item`'s per-type constructors don't take one — so a pasted or duplicated item always landed with `layer_id = None`, invisible to that layer's visibility/lock toggle and (once #338 shipped) unranked and un-arrangeable. This was a pre-existing gap, not a regression #338 introduced, but per-object stacking is what made it visible (an unranked, layer-less item sorts to the very top of the `None` pseudo-layer's z=0 band, which reads as "why won't Arrange do anything to my pasted copy"). Fix: `_serialize_item_core` now writes `layer_id` when the source item has one; a new `CanvasView._restore_layer_id` applies it to the deserialized item **only if it still resolves in the target scene** (paste after File → New Plan, or into a different scene entirely, means the copied UUID no longer names a real layer) — falling back to the scene's active layer, else leaving the item layer-less exactly as before. Pinned by `tests/integration/test_stacking_roundtrip.py`'s paste/duplicate-ordering cases. Lesson: when a serializer's "core" dict is deliberately relationship-free (so it can be reused by both the full save path and the clipboard's need to drop parent/child links), check that it isn't *also* dropping a field the reused caller actually needs — `layer_id` was cut for the wrong reason and stayed cut for eight months.

### PF-PER-14

- **Rule:** A refresh that runs opportunistically between a command's `execute()` and `undo()` derives its output and never writes the state an undo snapshot depends on.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #338
- **Status:** standing
- **Legacy:** b1faaa9 README L418

- **Lesson (design review, #338): a refresh that writes model state breaks snapshot-based undo.** The stacking-order design went through two drafts that a design review caught before either shipped: (1) a "refresh also renumbers ranks" variant — since the z-refresh runs on many paths that have nothing to do with an explicit arrange (a layer visibility toggle, an opacity-preview commit, any unrelated command's cleanup pass), a command's undo snapshot taken before `execute()` would no longer match the ranks in force by the time `undo()` ran, silently breaking Ctrl+Z for any command that happened to trigger a refresh in between; and (2) a "provisional z assigned at add time, finalized lazily" variant, which breaks the moment an item is deleted from the middle of a layer — the reserved slots stop describing a contiguous order and a later finalize pass can't tell a genuine gap from a reusable one. The shipped design (ADR-043) keeps rank-writing to exactly four call sites and makes every refresh a pure read of whatever ranks already exist. General rule: any code path that both (a) runs unconditionally/opportunistically and (b) can be reached between a command's `execute()` and its `undo()` must never mutate the same state an undo snapshot depends on — if it needs to run there, make it derive its output instead of writing it.

### PF-PER-15

- **Rule:** A same-scene load clears items through one serialized-document-item predicate, and a UUID delete refuses duplicate live IDs and confirms the target is gone before reporting success.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #353
- **Status:** standing
- **Legacy:** b1faaa9 README L458

**A same-scene project load can leave stale callouts/curves, and UUID lookup then turns a delete into a false success (issue #353, 2026-09-24).** Symptom: after saving and loading into the same `CanvasScene`, `list_layers.object_count` exceeded the top-level objects returned by `list_objects`; a concurrent-looking `delete_object` could return success while a same-ID callout remained. The first hypotheses — a command-manager race or a need for a second global lock — were wrong: `MainThreadBridge` already serializes Qt work, and the actual source was `_deserialize_to_scene`'s stale explicit type tuple, which omitted `CalloutItem`, `ArcItem`, and `BezierItem`. The fix centralizes a serialized-document-item predicate (while preserving compare/dimension overlay owners), refuses duplicate live UUIDs before deletion, and verifies target absence before returning success. Lesson: a UUID write API must treat scene identity invariants as part of its postcondition; a command completing on the main thread is not proof that the addressed object is gone.

### PF-PER-16

- **Rule:** A finite float is not a safe Qt geometry input: bound it at the creation boundary, treat an explicit null as a refusal rather than an omission, and test hostile input through the real transport.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #355
- **Status:** standing
- **Legacy:** b1faaa9 README L460

**A finite float is not a safe Qt geometry input, and JSON normalization can turn hostile Infinity/NaN into an apparently valid default (issue #355, 2026-09-24).** Symptom: `1e308` callout offsets were rejected only after probing, while Infinity/NaN sent through the real MCP client arrived as `null` and were treated as omitted, creating a normal callout instead of failing. The root cause was not Qt alone: the API boundary's finite check ran too late, after Pydantic/JSON had already erased the distinction. The fix validates signed offsets against `2 * max(canvas_width_cm, canvas_height_cm)` in the Qt-free creation boundary, uses an omission sentinel in the MCP handler, and rejects explicit null before provider dispatch. Refusals occur before the loader and command, so the scene and undo stack remain untouched. Lesson: hostile-input tests must cross the real transport; a direct validator test cannot see a transport's null normalization.

### PF-PER-17

- **Rule:** A date editor shows stored dates as they are, and an override whose end precedes its start is ignored on read and refused on write, never rewritten in the file.
- **Pinned by:** none — The body says the defects are covered by tests but names no test file or test name.
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1080-a-widget-that-rewrites-a-displayed-date-for-readability-corrupted-persisted-data)
- **Legacy:** b1faaa9 README L1080

### PF-PER-18

- **Rule:** Numeric, download and settings checks sit at the shared ingestion and persistence boundaries, and geometry is validated on Qt's derived bounds and spans, not only on each finite operand.
- **Pinned by:** `tests/unit/test_plan_numeric_safety.py`; `tests/unit/test_verified_update.py`; `tests/unit/test_image_download.py`; `tests/integration/test_a1_plan_safety.py`; `tests/integration/test_a1_download_safety.py`; `tests/integration/test_settings_isolation.py::test_a1_linux_native_settings_are_private_across_sync_and_migration`; `tests/integration/test_settings_isolation.py::test_a1_windows_backend_does_not_attempt_posix_protection`; `tests/integration/test_settings_isolation.py::test_a1_linux_safe_symlink_special_file_and_permission_failure`; `tests/unit/test_settings_security_startup.py`
- **Source:** #453, #480, #483, #485
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l3247-a1-numeric-download-and-settings-boundaries-453)
- **Legacy:** b1faaa9 README L3247


### PF-PER-19

- **Rule:** Authored examples use creation commands and draw plants above raised parents.
- **Pinned by:** `tests/unit/test_templates.py::test_bundled_parent_links_and_forest_layers_follow_render_order`
- **Source:** #316, ADR-066
- **Status:** standing
- **Legacy:** none (new entry)

The initial balcony preview showed empty containers. `[F5-Z]` reported containers
on layer None, plants on the active UUID, and a later container at a higher z than
a preceding plant. The parent clamp is per-layer, so linking IDs alone did not
raise those plants. Assign the active layer to authored rectangles and use
CreateItemsCommand for plants, which also maintains the parent's child list.
Real rendering caught what successful JSON loading did not. Box glyphs in the
first preview separately required the existing `minimal:enable_fonts` recipe.
Ground-level forest beds may span semantic layers. Raised parents need plants on
the same or a higher layer; reciprocal parent/child IDs alone do not ensure this.


### PF-PER-20

- **Rule:** A shape is serialized in its **parent's** frame - the local geometry translated by `mapToParent(shape centre) - shape centre` - not by `item.pos()`, because `QGraphicsItemGroup.addToGroup()` folds the old rotation pivot into `pos()`.
- **Pinned by:** `tests/unit/test_geometry_identity.py::test_rotated_grouped_shape_round_trips`; `tests/unit/test_geometry_identity.py::test_grouped_curves_round_trip_in_their_parent_frame`; `tests/unit/test_geometry_identity.py::test_grouped_construction_geometry_round_trips`; `tests/unit/test_geometry_identity.py::test_nested_groups_round_trip`
- **Source:** #661
- **Status:** standing
- **Legacy:** none (new entry)

A 30-degree rectangle grouped with a circle saved `x=186.44, y=37.42`
(`item.pos() + rect.x()`), but the child's frame had already been normalized by
`addToGroup()`: for a rotated child Qt rewrites `pos` to the parent position of
the item's local `(0, 0)` and rotates about the item origin, so `pos + local`
double-counts the compensation. Reload then rotated the shape about a different
rect centre and its visible scene centre moved from `(160, 130)` to
`(246.44, 67.42)` - a silently different plan, baked into the file at save time
and not fixed by moving the group afterwards. `mapToParent(centre)` is invariant
because `_apply_rotation` always pivots on the shape's own centre, so every
shape branch (rectangle, ellipse, circle, polygon, polyline), the arc/bezier
curves and the construction line/circle translate by that offset. The matrix
covers five shape types x four rotations, a group move before the save, a second
save/reload that must not drift again, the curves, the construction items and a
nested group.

### PF-PER-21

- **Rule:** A command that replaces a shape with a rebuilt one gives the replacement the source's UUID and garden bookkeeping (name, metadata copy, parent/child links, layer, stack rank, label flags, transform including the stored rotation angle). When the edit would also change topology (a corner split renumbers indexed vertex and edge anchors) or the object's kind (a trim turns a closed bed into an open line), it is refused instead of silently retargeting anchors or orphaning records.
- **Pinned by:** `tests/unit/test_geometry_identity.py::test_corner_edit_keeps_the_bed_identity`; `tests/unit/test_geometry_identity.py::test_corner_edit_refuses_a_vertex_constrained_item`; `tests/unit/test_geometry_identity.py::test_corner_edit_refuses_an_edge_constrained_item`; `tests/unit/test_geometry_identity.py::test_rotated_corner_edit_keeps_orientation_and_geometry`; `tests/unit/test_geometry_identity.py::test_trim_refuses_a_referenced_bed`; `tests/unit/test_geometry_identity.py::test_trim_keeps_a_plain_shape_identity`; `tests/unit/test_geometry_identity.py::test_rotated_trim_keeps_orientation`
- **Source:** #668
- **Status:** standing
- **Legacy:** none (new entry)

Chamfer and fillet rebuilt a named bed as a fresh `PolygonItem`, copying only the
visual style: new UUID, empty name and metadata, plants still pointing at the
old id, soil/pest/harvest records keyed to a UUID no live item owned, and every
constraint anchored to the old id dangling. Undo restored the original, so the
loss only surfaced on redo or the next save - and a `.ogp` written afterwards
kept the orphans forever. `inherit_item_identity()` in `core/item_look.py` is
the single rule now used by the corner tools and both trim tools; `object_type`
stays the caller's decision, and the replacement keeps its stack rank so it does
not jump above its plants. Identity is a property of what the user edited, not
of the Python object a rebuild happened to construct.

A vertex insert/delete renumbers indexed anchors, so the graph-level
`shift_vertex_indices()` shifts `EDGE_*` anchors alongside vertex indices, and
`drop_edge_constraints()` removes a reference to an edge that a split or a delete
made disappear instead of guessing one of the halves. Both are pinned directly;
the interactive insert/delete path calls them for polygons and polylines.

Keeping the UUID is only half the answer, and the first review round found the
other half: topology. A chamfer replaces one vertex with two, renumbering every
later `CORNER`/`ENDPOINT` anchor *and* every later `EDGE_*` midpoint index, and a
trim reorders the perimeter completely. Version one of the fix kept the UUID
anyway, so a constrained vertex silently retargeted a different point, and a
trimmed bed became a `FENCE` polyline that still owned the bed's records and
plants. The tools now refuse those two edits (corner edit when the item carries
any indexed anchor; trim when the item is a plant-parent or carries any
constraint) and say why in the status bar. A plain unconstrained polygon still
trims with its identity and rotation intact. The second review round found the
last two gaps: `setRotation()` does not update the stored `rotation_angle` the
serializers read, so a rotated replacement lost its orientation on the next
save; and `inherit_item_identity` must be in the module's own contract
(`__all__`, docstring). Pinned by seven tests covering identity, both refusal
branches, the plain-shape control, rotation, and a save/reload of the result.
