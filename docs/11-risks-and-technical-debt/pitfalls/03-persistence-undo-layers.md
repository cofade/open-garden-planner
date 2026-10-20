# Pitfalls: persistence, undo and layers

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-PER-01

- **Rule:** Two divergent item serializers create silent data-loss gaps on clipboard operations; unify under one chokepoint.
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #400
- **Status:** standing
- **Legacy:** README L178

- **Two divergent item serializers create silent data-loss gaps on clipboard operations; unify under one chokepoint.** (Issue #400, AUD-002, TD-018): `CanvasView` maintained its own separate ~500-line item serializer and deserializer (`_serialize_item`, `_serialize_item_core`, `_deserialize_item`) that diverged from `ProjectManager`. The clipboard serializer dropped `spacing_radius_cm` overrides, `frost_protection_needed`, `label_visible`, and `path_fence_style`, and silently skipped newer geometric types entirely (Arc, Bezier, Groups). The fix eliminated the duplicated serializer completely: `CanvasView` now delegates all item serialization and deserialization directly to `ProjectManager`'s static methods. UUID stripping and geometry offsetting (`_strip_item_ids`, `_offset_item_dict`) are handled uniformly by pure helpers before pasting/patterning. Lesson: having two serialization paths for the same data vocabulary guarantees divergence over time; one authoritative serializer must back both file I/O and clipboard operations.

### PF-PER-02


- **Rule:** Opening a corrupt plan must never contaminate document identity or wipe existing recovery files.
- **Pinned by:** none — the home holds this rule (see Status); no test is named here
- **Source:** #403
- **Status:** pointer → [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling)
- **Legacy:** README L179

Held in [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-03


- **Rule:** Missing or corrupt external assets must load as placeholders to survive save cycles.
- **Pinned by:** none — the home holds this rule (see Status); no test is named here
- **Source:** #397
- **Status:** pointer → [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling)
- **Legacy:** README L180

Held in [§8: 8.7 Error Handling](../../08-crosscutting-concepts/README.md#87-error-handling). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-04

- **Rule:** Dimension line updates after undo/redo
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L274

- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.

### PF-PER-05

- **Rule:** Plants stack behind beds when both share a layer's default z
- **Pinned by:** none — retired with its subject
- **Source:** #338
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l306-plants-stack-behind-beds-when-both-share-a-layers-default-z)
- **Legacy:** README L306

### PF-PER-06

- **Rule:** Excel reads UTF-8 CSV as Latin-1 unless a BOM is present
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L316

- **Excel reads UTF-8 CSV as Latin-1 unless a BOM is present**: A bare `encoding="utf-8"` write produces correct bytes but Excel on Windows still mojibakes German Umlauts (`Tüte` → `TÃ¼te`). Use `encoding="utf-8-sig"` for any CSV the user is expected to open in Excel. Python's own `csv` module strips the BOM transparently on read with either `utf-8` or `utf-8-sig`, so existing tests don't need to change. The BOM byte sequence is `b"\xef\xbb\xbf"` if you need to assert it directly.

### PF-PER-07

- **Rule:** A panel that writes item `metadata` directly reaches neither `scene.changed` nor `stack_changed` — every derived overlay goes stale
- **Pinned by:** `tests/integration/test_plant_growth_wiring.py`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L323

- **A panel that writes item `metadata` directly reaches neither `scene.changed` nor `stack_changed` — every derived overlay goes stale**: `PlantDatabasePanel._update_instance_metadata` writes `plant_instance` keys (`planting_date`, `current_height_cm`, `current_spread_cm`) straight into `item.metadata` and then calls only `mark_dirty()`. A metadata write repaints nothing, so `QGraphicsScene.changed` never fires; and because the edit bypasses the command manager, `stack_changed` never fires either. `SunShadowController` subscribes to exactly those two. Once US-E8 made `current_height_cm` load-bearing for shadow casting, editing the field left the shadow at the **old** size until some unrelated repaint (changing the selection, say) happened to nudge it — intermittent, which reads as a bug rather than a delay. **Fix**: call `item.update()` after the metadata write, so the existing `scene.changed → schedule_recompute` path runs. **Rule**: if a panel mutates model state that a derived overlay reads, it must emit on one of the two channels overlays actually listen to — `mark_dirty()` alone only *saves* the change, it never *shows* it. Pinned by `tests/integration/test_plant_growth_wiring.py`, which takes its `recompute_count` baseline only after the scene has **settled**: creating the overlay is itself a scene change, so an unsettled baseline makes the assertion pass against the unfixed code (the first cut of that test did exactly that). Note these fields still have no undo — they have never gone through a `Command` (pre-existing).

### PF-PER-08

- **Rule:** Layer subsystem: panel is a pure view; ALL mutations go through undoable commands
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #201, #209
- **Status:** standing
- **Legacy:** README L345

- **Layer subsystem: panel is a pure view; ALL mutations go through undoable commands** (issue #201 + layer-undo fix): historically `LayersPanel` mutated layers directly and `panel._layers` *aliased* `scene._layers` (the scene hands its live list to `panel.set_layers()`), so panel-side inserts mutated the scene before any signal fired — and none of it was undoable (Ctrl+Z silently ignored every layer action). Both are fixed: `LayersPanel.set_layers` now stores a **defensive copy** (`list(layers)`), and every layer operation (add, delete, rename, reorder, visibility, lock, opacity) routes panel request-signal → `GardenPlannerApp` handler → `CommandManager.execute(<LayerCommand>)` → scene mutation → `layers_changed` → `panel.set_layers` rebuild. Rules for any new code touching this subsystem: (1) the panel must NEVER mutate `Layer` objects or its `_layers` list — emit a request signal and let a command in `core/commands.py` (`AddLayerCommand`, `DeleteLayerCommand`, `RenameLayerCommand`, `ReorderLayersCommand`, `SetLayerPropertyCommand`) do the work; the rebuild repaints the widgets. Emit as the **last** statement of a `LayerListItem` handler — the synchronous command → rebuild deletes the emitting widget. (2) `_refresh_list` restores selection by **layer id**, never row index — a top-insert shifts every row down one. (3) Undo of add/delete restores the previously active layer by calling `set_active_layer` **last**, after `layers_changed.emit()` — the panel rebuild's fallback `setCurrentRow(0)` fires first and would otherwise win; the scene's `active_layer_changed → panel.select_layer` connection (signal-blocked) re-syncs the visible selection. (4) Opacity slider drags coalesce into one undo step: `valueChanged` while `isSliderDown()` drives the non-undoable `scene.preview_layer_opacity()` (no `layers_changed`, so no rebuild storm per tick); `sliderReleased` commits one `SetLayerPropertyCommand` carrying the opacity snapshotted at `sliderPressed`. (5) `CanvasScene.add_layer()` *appends* (bottom) and is for bulk/import only (DXF); `CanvasScene.remove_layer()` is likewise a non-undoable primitive — neither is the user-facing path. (6) Command `description` strings are user-visible (status bar "Undo: …") and use `QCoreApplication.translate("Commands", …)` + registration in `scripts/fill_translations.py`. (As of issue #209 **all** command descriptions — not just the layer ones — use this pattern; the former English f-strings have been migrated, including the caller-supplied descriptions of `AlignItemsCommand`/`MultiVertexMoveCommand`, which are wrapped at their call sites in `canvas_view.py`/`properties_panel.py`.)

### PF-PER-09

- **Rule:** Undoable layer preconditions must be revalidated on redo
- **Pinned by:** `tests/unit/test_commands.py::TestDeleteLayerCommand`
- **Source:** none recorded
- **Status:** standing
- **Legacy:** README L347

- **Undoable layer preconditions must be revalidated on redo** (US-D2.4): `DeleteLayerCommand` originally checked its replacement layer's lock only in `__init__`. The sequence delete → undo → lock replacement → redo then bypassed the protection because redo re-executed the existing command. The command now checks immediately before mutation, and `CommandManager.redo()` restores a refused command to the redo stack. Regression: `tests/unit/test_commands.py::TestDeleteLayerCommand::test_redo_refuses_newly_locked_replacement_and_preserves_redo`. General rule: mutable protections belong at every mutation boundary, including redo; constructor validation is not enough.

### PF-PER-10

- **Rule:** Undo/redo must dirty the document — and so must every "already-applied" edit; route them all through one chokepoint
- **Pinned by:** `tests/integration/test_undo_redo_dirty.py`
- **Source:** #209
- **Status:** standing
- **Legacy:** README L356

- **Undo/redo must dirty the document — and so must every "already-applied" edit; route them all through one chokepoint** (issue #209): `CommandManager.execute()` emits `command_executed`, but `undo()`/`redo()` historically emitted only `can_undo_changed`/`can_redo_changed`. Because `mark_dirty` was wired to `command_executed` ([application.py](../../src/open_garden_planner/app/application.py)), undoing or redoing after a save left the title bar's `*` marker (and the close-time "unsaved changes" prompt) believing the document was clean — closing then **silently discarded** the change. Repro: draw → save → Ctrl+Z → title shows no `*`, close prompts nothing. Fix: a dedicated `stack_changed` signal on `CommandManager` (emitted by `execute`/`undo`/`redo`, **not** `clear()` — clearing happens on new/load and must stay clean) wired to `mark_dirty`. A dedicated signal, not "also emit `command_executed` from undo/redo", because the constraints/properties/dimension-line refreshes are *already* separately wired to `can_undo_changed`/`can_redo_changed` (firing `command_executed` too would double-fire them) and the calendar refresh would newly fire.

  **The trap that made this a two-part fix:** `command_executed` was *load-bearing* for dirtiness far beyond `execute()`. ~30 interactive-edit sites across `canvas_view.py`, `properties_panel.py`, `garden_item.py`, and the item modules (`resize_handle.py`, `circle_item.py`, `rectangle_item.py`, `ellipse_item.py`, `polygon_item.py`, `polyline_item.py`) use the "move already applied, just register undo without re-executing" pattern: they reached into `cm._undo_stack.append(cmd)` directly and hand-emitted `command_executed` to mark dirty. Moving `mark_dirty` to `stack_changed` un-dirtied every one of them (drag a resize handle / vertex / edit a radius → no `*`, close discards). Naively the new integration test still passed because it only exercised the `RectangleTool` → `execute()` path. Real fix: a single `CommandManager.register_applied(command)` chokepoint that does the append + redo-clear + **all** signal emits (including `command_executed` *and* `stack_changed`); every former direct-append site now calls it. Lesson: there must be exactly **two** ways onto the undo stack — `execute()` (runs the command) and `register_applied()` (command already applied) — and both emit the full signal set. Never hand-roll `_undo_stack.append` at a call site; the moment you change what `execute()` emits you create silent contract drift with every copy. Regression tests: `tests/integration/test_undo_redo_dirty.py` covers both an `execute()` path *and* a `register_applied` resize path.

### PF-PER-11


- **Rule:** A bug that is exactly 0 at the default value hides forever — and a `Callable` parameter is where two implementations of one behaviour go to drift
- **Pinned by:** `tests/integration/test_geometry_apply_shared_path.py`
- **Source:** #218, #326
- **Status:** pointer → [ADR: ADR-028: Plant Sizing Resolver + Unified Rotation-Aware Resize](../../09-architecture-decisions/README.md#adr-028-plant-sizing-resolver--unified-rotation-aware-resize)
- **Legacy:** README L412

Held in [ADR: ADR-028: Plant Sizing Resolver + Unified Rotation-Aware Resize](../../09-architecture-decisions/README.md#adr-028-plant-sizing-resolver--unified-rotation-aware-resize). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-12


- **Rule:** Same-layer stacking inverted on every save/load
- **Pinned by:** `tests/integration/test_stacking_roundtrip.py`
- **Source:** #338
- **Status:** pointer → [ADR: ADR-036 addendum: species assignment + explicit bed reparenting (US-D2.3, #327)](../../09-architecture-decisions/README.md#adr-036-addendum-species-assignment--explicit-bed-reparenting-us-d23-327)
- **Legacy:** README L414

Held in [ADR: ADR-036 addendum: species assignment + explicit bed reparenting (US-D2.3, #327)](../../09-architecture-decisions/README.md#adr-036-addendum-species-assignment--explicit-bed-reparenting-us-d23-327). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-13

- **Rule:** Clipboard-pasted items were layer-less
- **Pinned by:** `tests/integration/test_stacking_roundtrip.py`
- **Source:** #338
- **Status:** standing
- **Legacy:** README L416

- **Clipboard-pasted items were layer-less** (#338, found while implementing stacking order): `CanvasView.copy_selected`/`duplicate_selected` never saved `layer_id`, and `_deserialize_item`'s per-type constructors don't take one — so a pasted or duplicated item always landed with `layer_id = None`, invisible to that layer's visibility/lock toggle and (once #338 shipped) unranked and un-arrangeable. This was a pre-existing gap, not a regression #338 introduced, but per-object stacking is what made it visible (an unranked, layer-less item sorts to the very top of the `None` pseudo-layer's z=0 band, which reads as "why won't Arrange do anything to my pasted copy"). Fix: `_serialize_item_core` now writes `layer_id` when the source item has one; a new `CanvasView._restore_layer_id` applies it to the deserialized item **only if it still resolves in the target scene** (paste after File → New Plan, or into a different scene entirely, means the copied UUID no longer names a real layer) — falling back to the scene's active layer, else leaving the item layer-less exactly as before. Pinned by `tests/integration/test_stacking_roundtrip.py`'s paste/duplicate-ordering cases. Lesson: when a serializer's "core" dict is deliberately relationship-free (so it can be reused by both the full save path and the clipboard's need to drop parent/child links), check that it isn't *also* dropping a field the reused caller actually needs — `layer_id` was cut for the wrong reason and stayed cut for eight months.

### PF-PER-14


- **Rule:** Lesson (design review, #338): a refresh that writes model state breaks snapshot-based undo.: The stacking-order design w
- **Pinned by:** none — the home holds this rule (see Status); no test is named here
- **Source:** #338
- **Status:** pointer → [ADR: ADR-036 addendum: species assignment + explicit bed reparenting (US-D2.3, #327)](../../09-architecture-decisions/README.md#adr-036-addendum-species-assignment--explicit-bed-reparenting-us-d23-327)
- **Legacy:** README L418

Held in [ADR: ADR-036 addendum: species assignment + explicit bed reparenting (US-D2.3, #327)](../../09-architecture-decisions/README.md#adr-036-addendum-species-assignment--explicit-bed-reparenting-us-d23-327). The entry keeps the rule and its pin; the account is in the link.

### PF-PER-15

- **Rule:** A same-scene project load can leave stale callouts/curves, and UUID lookup then turns a delete into a false success (issue #353, 2026-09-24).
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #353
- **Status:** standing
- **Legacy:** README L458

**A same-scene project load can leave stale callouts/curves, and UUID lookup then turns a delete into a false success (issue #353, 2026-09-24).** Symptom: after saving and loading into the same `CanvasScene`, `list_layers.object_count` exceeded the top-level objects returned by `list_objects`; a concurrent-looking `delete_object` could return success while a same-ID callout remained. The first hypotheses — a command-manager race or a need for a second global lock — were wrong: `MainThreadBridge` already serializes Qt work, and the actual source was `_deserialize_to_scene`'s stale explicit type tuple, which omitted `CalloutItem`, `ArcItem`, and `BezierItem`. The fix centralizes a serialized-document-item predicate (while preserving compare/dimension overlay owners), refuses duplicate live UUIDs before deletion, and verifies target absence before returning success. Lesson: a UUID write API must treat scene identity invariants as part of its postcondition; a command completing on the main thread is not proof that the addressed object is gone.

### PF-PER-16

- **Rule:** A finite float is not a safe Qt geometry input, and JSON normalization can turn hostile Infinity/NaN into an apparently valid default (issue #355, 2026-09-24).
- **Pinned by:** none — the entry names no test as its pin; pending review
- **Source:** #355
- **Status:** standing
- **Legacy:** README L460

**A finite float is not a safe Qt geometry input, and JSON normalization can turn hostile Infinity/NaN into an apparently valid default (issue #355, 2026-09-24).** Symptom: `1e308` callout offsets were rejected only after probing, while Infinity/NaN sent through the real MCP client arrived as `null` and were treated as omitted, creating a normal callout instead of failing. The root cause was not Qt alone: the API boundary's finite check ran too late, after Pydantic/JSON had already erased the distinction. The fix validates signed offsets against `2 * max(canvas_width_cm, canvas_height_cm)` in the Qt-free creation boundary, uses an omission sentinel in the MCP handler, and rejects explicit null before provider dispatch. Refusals occur before the loader and command, so the scene and undo stack remain untouched. Lesson: hostile-input tests must cross the real transport; a direct validator test cannot see a transport's null normalization.

### PF-PER-17

- **Rule:** A widget that rewrites a displayed date for "readability" corrupted persisted data.
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1080-a-widget-that-rewrites-a-displayed-date-for-readability-corrupted-persisted-data)
- **Legacy:** README L1080

### PF-PER-18

- **Rule:** A1 numeric, download and settings boundaries (#453)
- **Pinned by:** none — the tests this narrative names are cited in the archive (see Status); pending review
- **Source:** #453, #480, #483, #485
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l3247-a1-numeric-download-and-settings-boundaries-453)
- **Legacy:** README L3247
