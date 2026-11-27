---
id: ADR-034
title: "Curated Agent Schema + UUID Addressing (US-D1.x)"
status: "Accepted (Phase 13 — Package D). Spike implements the read half (`PlanSummary`); the full read surface follows in D1.2."
legacy_anchor: adr-034-curated-agent-schema--uuid-addressing-us-d1x
---

# ADR-034: Curated Agent Schema + UUID Addressing (US-D1.x)

**Status**: Accepted (Phase 13 — Package D). Spike implements the read half (`PlanSummary`); the full read surface follows in D1.2.

## Addendum (US-D3.3 + US-D3.4 — the D3 localisation convention)

Epic #237 required **one** answer across #332 and #333, and #333 escalated it: *"two different answers to the same question across two D3 tools would be worse than either answer."* This is that answer.

**Context.** Several strings an agent receives are built with `QCoreApplication.translate` — task titles at `task_generator.py` (the soil-amendment and soil-mismatch generators), and the mismatch reason sentences in `soil_service.get_mismatch_details`. A German UI therefore returns **German prose** through a surface §8.19 documents as an **English API contract**. Forcing English at the generator is not available: the GUI is the primary consumer of those strings and would break.

**Decision — two field classes, per tool:**

| Field class | Tools | Contract |
|---|---|---|
| `task_id`, `task_type`, `source`; `amendment_id`, `target_kind`, `fixes`, `reason_codes` | D3.3, D3.4 | **Stable English machine keys.** Part of the API contract. Never localised. Agents branch on these. |
| `title`, `notes`; `display_name`, `reasons` | D3.3, D3.4 | **Display strings in the user's current UI language.** Explicitly *not* part of the English contract. Documented in the tool docstring, the schema field description and §8.19. |

- **No second translation path.** The agent layer **passes the generator's string through unchanged**; the localisation stays upstream where it already lives. A test asserts pass-through *and* upstream translation separately, because asserting only "the title changed" would pass even if the wrapper had invented a translation of its own.
- **No new `title_key` field.** `task_type` + `source` + `task_id` already give an agent every branch it needs; a parallel label would be a second thing to keep in sync.
- **Amendment names are data, not translations.** `Amendment.name` / `name_de` are localized *data* fields (an invariant-16 exemption), so `display_name` is *selected*, not translated. The convention is unchanged either way: `amendment_id` never moves with the UI language.
- **Enforcement.** `tests/unit/test_agent_d3_localisation.py` installs a real `QTranslator` and asserts that the machine keys are byte-identical while the display strings change. It also asserts the schema field descriptions carry the rule, because a convention nothing states erodes.

**Addendum (US-D3.3 — task sources).** `Task.source` has **six** values — `calendar`, `propagation`, `succession`, `soil`, `frost`, `manual` — read off the `source=` argument of all seven generators. **Not** seven: both soil generators emit `source="soil"`, and the two are distinguished by `task_type` (`soil_amendment` vs `soil_mismatch`), not by `source`. An agent filtering by `source` alone therefore cannot select one of them, which the `get_tasks` docstring states. A drift guard asserts **equality** in both directions between the tuple and the engine; see §11.4 for why a subset-only guard was not enough.

**Addendum (US-D3.4 — the effective soil record needs provenance).** `SoilStatus` carries **`record_source`** (`'bed'` / `'global'` / `'none'`) alongside the readings. `SoilService.get_effective_record_with_source` resolves the record, provenance and matching history together through one hierarchy (bed's own latest → global default's latest → none); `get_effective_record` delegates to it for existing GUI callers. The overdue check uses that selected history, including global fallbacks. Resolving provenance separately in the provider was rejected after review reproduced an old global reading incorrectly reported as current.

**Addendum (US-D3.3/D3.4 — review and live verification, 2026-10-04).** Soil reads use explicit aggregate models (`SoilStatusListView`, `SoilMismatchBedsView`) for both one-bed and all-bed calls. The soil prompt extracts the requested bed; it does not feed an envelope into a single-bed model. Real-MCP integration coverage uses the application's production provider graph, including authenticated writes/refusals and both new prompts. This caught failures that direct provider tests had missed. Amendment names select `Amendment.display_name(language)` using the app's language. Soil-write numeric annotations are strict: MCP must not coerce booleans/strings into categorical readings before the domain check.

Task generation separates `today` from the calendar `year`. An explicit `actionable_only` option preserves the GUI's current reminder behavior while complete annual calendars and explicit agent windows retain inactive tasks; urgency still uses the actual reference date. Cross-year intervals are clipped to the requested year. `generate_for_date_window` derives frost-anchor years from the actual species and generated propagation offsets, rather than matching the window's year numbers: bundled garlic sowing precedes its anchor year and asparagus harvest extends three years. Both annual calendars and explicit windows use that path, preserving canonical anchor-year task IDs. Propagation reuses the extracted GUI calculator with seed-packet data and stored overrides. A second agent-only calendar or propagation implementation was rejected.

An empty amendment list establishes only that the engine recommends nothing from the readings it can assess. Existing GUI lab-only ppm records remain unconverted and can yield unknown health with an empty plan; tool and prompt prose must not infer that measured values are near target.

Absolute propagation steps use their overridden start-date year as their canonical owner year in the shared generator. Relative steps retain frost-anchor-year IDs. This makes one saved override one task across GUI and agent reads, including multi-year windows; deduplication by anchor-year ID alone cloned an override for every evaluated anchor. An agent-only deduplication rule was rejected because the two surfaces would then disagree on identity.

**Addendum (US-D3.4 — secondary nutrients have no health rating).** `SoilService.health_level` rates `ph`, `n`, `p`, `k` and `overall` — its `ALL_PARAMS` is exactly those five. Passing `'ca'`, `'mg'` or `'s'` **falls through to its `overall` branch** and returns the whole bed's rating. So `SoilReading.health_level` is `str | None`, and `None` for a secondary means *"no rating exists for this nutrient"* — deliberately distinct from `'unknown'`, which means *not tested*. Reporting the overall rating as calcium's would be a confidently wrong answer, which is the D3.1 trap (`check_placement` reporting `unknown_bed` rather than a clean-looking `neutral`). `overall_health_level` likewise covers **pH and N/P/K only**; the secondaries do not drag it down.

**Cross-refs:** §8.19, §8.3, ADR-036 (D3.3/D3.4 addenda), ADR-045, issues #332, #333, #237, §11.4.

**Context**: Agents need a stable contract for reading the plan. The on-disk `.ogp` shape is an implementation detail that shifts with `FILE_VERSION`; exposing it directly would couple agent integrations to the save format.
**Decision**:
- **Curated pydantic schema** (`agent_api/schema.py`) is the default return shape — decoupled from `.ogp`/`FILE_VERSION`. The mapping (`agent_api/mapping.py`) is **Qt-free** and pure: it consumes `ProjectManager.snapshot_dict()` (an in-memory `.ogp`-shaped dict + an `agent_meta` block) and emits the schema. A `raw=True` escape hatch (D1.2) will expose the underlying dict for power use.
- **Object classification stays in sync with the domain** via a unit **drift-guard**: `mapping.py` inlines the bed/plant `ObjectType` name sets (to avoid importing Qt), and `tests/unit/test_agent_api_mapping.py` asserts they equal `SOIL_CONTAINER_TYPES` / `{t for t if is_plant_type(t)}`. Counts are **top-level objects only** (grouped/nested items are not counted individually).
- **Stable UUID addressing.** Objects are addressed by their existing `item_id`; read tools return ids. (Edit tools in D2 target ids.)
**Alternatives considered**: *Return raw `.ogp` JSON* — zero mapping effort but a brittle contract that leaks internals and breaks agents on every format bump; rejected as the default (kept as an opt-in escape hatch).
**Consequences**: A small mapping layer to maintain, guarded against silent drift by the unit test. The schema is the public surface agents code against; it evolves additively and independently of the save format.

**Addendum (US-D1.2 — read/query tools):** the read surface grows to `list_objects`, `get_object`, the spatial tools (`objects_in_region`, `objects_in`, `plants_in_bed`, `nearest_objects`, `measure_distance`) and `get_diagnostics`, with these decisions:
- **Curated shapes** `ObjectRef` (lightweight list element), `ObjectDetail` (full single object: rotation, area, colours, parent/children, species, metadata), `Diagnostic`, and `Measurement` join `PlanSummary` in `schema.py`. All structural/spatial logic is the **Qt-free** `agent_api/queries.py`, computed purely from the existing `snapshot_dict` (one main-thread hop per call, no new Qt access).
- **`raw=True`** is realised as a **dict-first union return** (`list[dict[str, Any]] | list[ObjectRef]`, `dict[str, Any] | ObjectDetail | None`). FastMCP emits a clean `anyOf` output schema and — crucially — the dict member must come **first**: with the model first, FastMCP coerces a raw dict back into the model and **silently drops unknown keys** from structured content (verified against mcp 1.28.1). Dict-first preserves the full serialiser dict on `raw=True` while model instances still validate as the model.
- **Coordinate frame:** objects are reported in the plan's **native scene frame** — centimetres, CAD Y-up (ADR-002): origin bottom-left (south-west), +x east/right, +y **north/up** (a larger y is further north — the same frame `move_object` uses). Non-rectangular shapes are summarised by their axis-aligned bounding box (`queries.object_bbox` normalises every serialised geometry: rect, circle/arc, ellipse, polyline/polygon, bezier, and bare-anchor shapes).
- **Spatial index:** a **linear scan** over the snapshot, **not** the live scene quadtree. The quadtree lives in the Qt scene and would force per-query Qt access + a main-thread hop; gardens have tens–low-hundreds of objects, so O(n) is trivially fast and keeps the layer Qt-free and unit-testable.
- **Diagnostics reuse, never recompute:** `get_diagnostics` reports the plan's **already-computed** warnings — the same flags the canvas paints as badges (`garden_item.antagonist_warning` / `spacing_overlap` / `capacity_overrun` / `soil_mismatch_level` / `rotation_status`). `ProjectManager.diagnostics_snapshot` harvests them on the main thread into Qt-free records; the Qt-free `agent_api/diagnostics.py` maps records → `Diagnostic`. Positive indicators (spacing `"ideal"`, rotation `"good"`) are **not** reported. The values reflect the last computed badge state (may lag a debounce tick after a programmatic change — acceptable for read-only inspection).
- **Provider bundle:** `build_server`/`AgentApiServer` now take an `AgentProviders` dataclass (Qt-free) of main-thread-marshaled callables (`snapshot`, `diagnostics`) instead of a bare snapshot callable — the extension seam for render (D1.3), exports/save (D1.4) and writes (D2). **No `FILE_VERSION` change.**

**Addendum (US-D1.3 — vision tool):** `render_canvas_image(x?, y?, width?, height?, layers?, image_width_px?)` returns a PNG of the live canvas plus a `RenderMeta` metadata block, reusing `services/scene_rendering.render_scene_region` (the same pipeline `ExportService.export_to_png`/the PDF report already use — no new rendering logic). Two facts below were **empirically verified**, not assumed, mirroring the D1.2 dict-first-union discovery:
- **`Image` is not pydantic-representable, so the naive design crashes the server at build time.** `async def render_canvas_image(...) -> list[Image | RenderMeta]` registered the normal way makes `@mcp.tool()` raise `PydanticSchemaGenerationError` the moment the server builds (verified against mcp 1.28.1). Annotating `list[Any]` instead defers the same crash to call time — strictly worse. **Fix:** `@mcp.tool(structured_output=False)` skips schema/model creation entirely and routes straight to `_convert_to_content()`'s flattening dispatcher, which correctly turns `Image` → `ImageContent` and a bare `RenderMeta` instance → `TextContent` (pydantic_core JSON dump); confirmed end-to-end via a live `mcp.call_tool()`. **Consequence:** this tool has no `structuredContent`, unlike the other 9 — a client must parse the `TextContent` block's JSON for render metadata. A second, independent pitfall surfaced only by actually running the test suite (not the isolated SDK probe that found the first one): with `from __future__ import annotations` in effect, every `@mcp.tool()` registration calls `inspect.signature(func, eval_str=True)` inside the SDK's `func_metadata` (unconditionally, regardless of `structured_output`) to resolve each stringified annotation via the **function's own `__globals__`**, not the enclosing `build_server()` call's locals — so `Image` must be a genuine module-level import in `server.py`, not merely imported inside `build_server()` (which raises `NameError: name 'Image' is not defined` at server-build time). Costs nothing extra: both names live under the same `mcp.server.fastmcp` package that `FastMCP` itself already pulls in at server-start time, and `agent_api.server` stays behind `agent_api/__init__.py`'s existing lazy `__getattr__` gate either way.
- **The rendered image's pixel Y-axis is inverted relative to the D1.2 scene frame.** `render_scene_region`'s `y_flip=True` (kept here for visual parity with the live CAD view and every existing PNG/PDF export) makes the output PNG Y-up (plan-up at the top; true north on a north-up plan), so a scene point's pixel row is inverted relative to its Y-up scene y (pixel rows count top-down). Empirically pinned by rendering a known-position `CircleItem` and scanning the actual output pixels (`tests/unit/test_agent_api_render_coordinate_frame.py`), including a `y_flip=False` cross-check isolating the flip as the sole cause. **Accepted correction formula**, documented on `RenderMeta.px_per_cm` as the permanent agent-facing contract: `px_x = (x_cm - region_x_cm) * px_per_cm`; `px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`.
- **Region params mirror `objects_in_region`'s existing flat `x, y, width, height` convention** (scene cm) rather than a nested object — all four given together or all omitted (full canvas, resolved from `scene.canvas_rect` on the **same** main-thread hop as the render itself, avoiding a second hop and any TOCTOU race if the canvas is resized in between).
- **`AgentProviders.render`** is the first **parametrized** provider (unlike the no-arg `snapshot`/`diagnostics`): `Callable[[region | None, layers | None, image_width_px], dict]`, implemented as one atomic `run_on_main` hop that resolves the default region, temporarily forces layer-bearing item visibility to match `layers` (new context manager, `_hidden_layers_not_in`), renders, and encodes to PNG bytes.
- **Output size is double-clamped**, not just width-capped: `agent_api/render.py::resolve_image_pixel_size` clamps the requested width **and** the aspect-ratio-derived height independently to `[128, 2048]`, so a pathological region (e.g. 1cm × 10 000cm) can't turn a modest width request into a runaway-large image.
- **`layers` is a full override of what's shown, not a subtractive filter** (unknown names silently match nothing, consistent with D1.2's existing filter semantics). **Post-review fix:** the first cut only ever *hid* items not in the allowlist, leaving an allowed layer's visibility untouched — so a layer the user had toggled off in the live Layers panel stayed invisible even when explicitly requested, since `_update_items_visibility()` (`canvas_scene.py`) is the sole driver of item visibility from layer state and nothing was forcing it back on. `_hidden_layers_not_in` now snapshots **every** layer-bearing item's original visibility, forces each to match `should_show` (in `layers` → visible, otherwise hidden) regardless of its current state, and restores the exact original state afterward — an agent asking for "Layer B" gets Layer B even if a human currently has it hidden, with no lasting effect on the live UI. Pinned by `test_render_canvas_image_layers_filter_shows_layer_hidden_in_ui`. `hide_overlays`/`hide_construction` stay fixed `True` (not exposed as params) — an agent's "look at my garden" screenshot has no reason to show selection handles or construction geometry. Verified the existing `_hidden_overlay_items` already restores the **pre-existing selection**, not just item visibility, so a read-only render call has no lasting side effect on the human's live GUI state.

**Addendum (US-D1.4 — export/save tools):** `save_plan`/`export_pdf`/`export_dxf`/`export_csv` are the Agent API's first tools with a **filesystem side effect** beyond returning bytes/dicts — each writes a real file to disk by calling the exact same services the GUI's File > Export/Save menu already calls (`PdfReportService`, `DxfExportService`, `ExportService`, `ShoppingListService`, `ProjectManager.save`). No new export/serialization logic; only new callers plus the path plumbing an agent-driven (dialog-less) caller needs that a human clicking through `QFileDialog` doesn't.
- **No token auth needed here — deferred to D2.** ADR-033 flags token auth as "a hard prerequisite before write tools"; D1.4 doesn't trigger that gate because none of these tools mutate the in-memory plan/scene graph. `save_plan` persists what a human already has on screen (mirroring `application._save_to_file` exactly, including the issue-#178 stale shopping-list-price prune before writing) and cannot be used to make an edit the agent isn't otherwise capable of, since D2's scene-mutating write tools don't exist yet — but it is **not** Ctrl+S in every respect: given an explicit `file_path`, it overwrites whatever is already at that path without the confirmation a `QFileDialog` save prompt would give a human, and Ctrl+S can never touch a file other than the one already open. That gap is accepted, not hidden, under the same loopback-trust model as every other file-producing tool here. The three `export_*` tools produce a brand-new deliverable file and never touch the live plan at all. The FastMCP server `instructions` string is updated to say so explicitly rather than leaving the stale "This server is read-only" claim from D1.1–D1.3.
- **File-write threat model stays "loopback trust" (ADR-033), not path sandboxing.** A local MCP client already has the same filesystem access as the OS user account running the app — restricting *which* paths a tool may write to would not add real protection, only guard against typos. `agent_api/exports.py::resolve_export_path` therefore only enforces: (1) with no `file_path` given, use the exact same safe-default chokepoint the GUI dialogs use (`app/paths.py`'s `default_save_path`/`default_dialog_dir`, the #199/#204 data-loss fix — next to the currently open project, or `<Documents>/Open Garden Planner`); (2) with an explicit `file_path`, force the correct suffix (mirroring every `_on_export_*` handler's own `.with_suffix()` call) and require the **parent directory already exist** — a typo'd path fails with a clear error instead of silently creating an arbitrary directory tree, mirroring what a save dialog would allow (you can't save into a folder that doesn't exist there either).
- **`save_plan` requires an explicit `file_path` for a brand-new, never-saved project.** Omitting `file_path` needs `ProjectManager.current_file` already set; if it's `None`, the tool raises rather than inventing an `Untitled.ogp` — mirrors the GUI, where a new project always needs an explicit Save-As dialog interaction before a filename exists. Given a path, that path becomes the project's file going forward (Save As semantics) — `ExportResult.previous_file_path` reports the prior `current_file` so a caller can tell whether this call redirected the project.
- **One shared `ExportResult` schema** (`file_path`, `format`, `row_count | None`, `previous_file_path | None`) covers all four tools, mirroring D1.2's reuse of `Measurement` rather than inventing a schema per tool. None of these tools return `Image` — D1.3's `structured_output=False`/top-level-import workaround doesn't apply; all four register and populate `structuredContent` normally, like the pre-D1.3 tools.
- **`AgentProviders` gains four parametrized fields** (`save_plan`, `export_pdf`, `export_dxf`, `export_csv`), each implemented as one atomic `run_on_main` hop (path resolution + the underlying service call together) — same TOCTOU reasoning as D1.3's `render`: resolving `current_file`/`project_name` and then acting on them must happen in one hop, not two.

**Addendum (US-D1.5 — resources + read-analysis prompts):** the read surface grows to 5 MCP resources (`garden://plan`, `garden://plan/raw`, `garden://canvas.png`, `garden://diagnostics`, `garden://species`) and 2 prompts (`audit-plan`, `describe-garden`), with these decisions:
- **`garden://species` needs no new `AgentProviders` field.** `services/bundled_species_db.py` imports only `json`/`pathlib`/`typing` — no Qt dependency — so the resource handler calls `get_species_db()` directly from the server thread, unlike every other resource/tool here which reads live-plan state through a main-thread-marshaled provider. This is static bundled data (118 records), not plan state, so no hop is needed or correct.
- **Resources are simpler than tools — verified by reading `mcp` 1.28.1's source, not assumed** (`fastmcp/server.py`, `fastmcp/resources/types.py`, `lowlevel/server.py`): `@mcp.resource(uri)` only inspects params via plain `inspect.signature(fn)` (no `eval_str`), and every D1.5 resource is zero-argument, so the tool-only `NameError`-on-local-import gotcha (D1.3) doesn't apply here. `FunctionResource.read()` passes `bytes` and `str` through unchanged; anything else (a pydantic model, a `dict`, a `list`) goes through `pydantic_core.to_json(result, fallback=str)` — no manual `json.dumps`/`model_dump_json()` needed. The lowlevel `read_resource` handler then pattern-matches the result type: `bytes` → `BlobResourceContents` (base64-encoded, using the resource's own `mime_type`), `str` → `TextResourceContents`. So `garden://canvas.png` just returns raw PNG `bytes` with `mime_type="image/png"` on the decorator — **no** `Image`/`structured_output=False` workaround; that was a tool-dispatch-only quirk (D1.3).
- **`@mcp.prompt()` accepts a plain `str` return** — it gets wrapped as `[UserMessage(TextContent(text=result))]` automatically, no `list[Message]`/`PromptMessage` construction needed for these read-analysis prompts.
- **New Qt-free `agent_api/prompts.py`** holds the two prompts' text-composition logic (`render_audit_plan_prompt`, `render_describe_garden_prompt`) as pure functions over the existing `PlanSummary`/`Diagnostic`/`ObjectRef` schema types — unit-testable without mcp/Qt, mirroring `mapping.py`/`diagnostics.py`. `server.py`'s registrations stay thin: fetch via the existing providers/queries, hand off to `prompts.py`.
- Four of the five resources are one-line reuses of existing D1.2–D1.4 functions (`mapping.plan_summary_from_snapshot`, a raw `snapshot` passthrough, `providers.render`, `diagnostics_from_records`); no dedicated `resources.py` module was added — it would have been pure ceremony over one-liners.

**Addendum (US-D2.4 — layer tools, #328):** Layer identity is exposed
additively as a curated `Layer` model. Agents address layers by UUID, never
by name; `layer_names` stays in `PlanSummary` for existing clients, while
`PlanSummary.layers`, `list_layers`, and `ObjectRef.layer_id` provide the
addressable state needed by write tools. The mapping computes active state from
the runtime-only `agent_meta.active_layer_id` and counts top-level objects per
layer without changing the `.ogp` format. Existing
`MoveToLayerCommand`, `AddLayerCommand`, `DeleteLayerCommand`,
`RenameLayerCommand`, and `SetLayerPropertyCommand` are the single write
paths. `set_active_layer` is a session-state switch and intentionally has no
undo entry; all document changes use one existing command execution. The
locked-layer decision is deliberately conservative: `locked` is read-only to
agents, `delete_layer` refuses a locked layer, and visibility/opacity remain
changeable because they do not release the user's protection. Layer deletion
preserves its objects on the command's replacement layer and undo restores
both the layer and object assignments. The command revalidates the replacement
lock immediately before every execution, including redo, and a refused redo
remains available on the redo stack.

**Addendum (issue #365 — the layer-lock policy is REVERSED):** the paragraph
above states that `locked` is read-only to agents. **That is no longer true, and
the reversal is a decision, not a bug fix.** The project owner decided agents
SHOULD be able to both lock and unlock layers, so `set_layer_property(layer_id,
locked=...)` now works in both directions, through the **same
`SetLayerPropertyCommand`** the Layers panel's own lock toggle runs — one undo
step, no second write path. The D2.4 reasoning ("an agent that could
unlock-then-edit would reduce every locked-layer refusal from a protection to a
speed bump") is recorded here as the *original* argument, not as a live
constraint; what survives it is described next.

**What deliberately did NOT change** is the important half, and the issue
overstated the blast radius: the four **object-level** lock guards are untouched
and remain absolute in the sense that matters — they test the layer's **current**
lock state. `_resolve_agent_item` still refuses to edit, move, resize, rotate, or
delete an object on a locked layer; `create_object` still refuses a locked
active layer and refuses to place an object on a locked layer;
`delete_layer` still refuses a locked layer. Because each guard reads live
state rather than a permission bit, "unlock, then edit" already works as a
**two-call sequence** with two ordinary undo steps the user can see and reverse.
No guard had to become conditional, and the tests pinning them
(`test_move_and_delete_refuse_locked_layer_item`,
`test_resize_and_rotate_refuse_locked_layer_item`,
`test_arrange_object_refuses_locked_layer_before_any_change`,
`TestLockedLayerDropped`) all still pass unchanged. Only
`test_set_layer_property_refuses_locked_in_both_directions` was **inverted**
(deliberately, not deleted) into `test_set_layer_property_locks_and_unlocks`,
joined by `test_unlock_then_edit_is_a_legitimate_two_call_sequence`.

The one-property-per-call rule is unchanged and now spans three properties:
passing `visible` and `locked` together still refuses *before* any command is
built, so a mixed call can never half-apply. `FR-AGENT-17` is updated to match.

**Addendum (issue #365 — document lifecycle: `new_plan` / `open_plan`):** the
Agent API could save a plan but not create or open one, so an agent could only
ever work on whatever document the user happened to have open. Both new tools
**reuse the GUI's own paths** rather than reimplementing them — `_on_new_project`
was extracted into `_new_project_document`, and `_open_project_file` was split
into `_load_project_file` (raises) plus its GUI wrapper (catches and shows a
modal). That split is load-bearing: an agent must never have a `QMessageBox`
appear on its behalf, so the dialog belongs in the wrapper and the shared path
must raise. This is the same one-seam discipline as
`ui/canvas/geometry_apply.py` and `ui/canvas/arrange.py`.

Three decisions, each of which the issue posed as an open question:

- **These tools are TOKEN-GATED, not ungated beside `save_plan`.** `save_plan`
  only writes a new file, but `new_plan`/`open_plan` **replace the open document
  and can discard unsaved work** — strictly more destructive than
  `delete_object`, so they take the same double gate. They live inside the
  `writes_active` block and are listed in the `WRITE_TOOL_NAMES` drift guard, so
  a future refactor that moves one out of the gate fails
  `test_gate_covers_every_write_tool`.
- **The unsaved-changes guard is `force`, not a prompt.** The GUI asks the user
  (`_confirm_discard_changes`); an agent cannot raise a modal, so the choice is
  binary — refuse, or proceed on an explicit `force=true`. The check lives in
  the main-thread body, because only there can the live `is_dirty` flag be read.
- **Paths are NOT sandboxed.** `agent_api/exports.py` already documents the
  project's position: a loopback-only server grants no filesystem access that a
  local MCP client does not already have as the OS user, so a sandbox would add
  no real protection. What *is* enforced is what prevents a silent surprise — the
  file must exist, be a file, and carry the `.ogp` suffix; and a relative path is
  resolved to absolute, because an agent cannot know which directory the GUI was
  launched in. `new_plan` **refuses** an out-of-range or non-finite canvas rather
  than clamping it: a clamped canvas is a silently different plan than the one
  asked for.

Neither tool is an undo step — a new or loaded document resets the undo stack
(`CommandManager.clear` emits no `stack_changed`, so the new plan starts clean
and not dirty), so there is nothing to Ctrl+Z back to.

## Addendum (US-D2.1 + US-D2.2 — tool return models, #365)

**A tool's declared return model is part of its contract, and testing the
provider is not the same as testing the tool.** `new_plan` and `open_plan`
first shipped returning `ExportResult(**result)` while their providers returned
a dict with no `format` key — and a `None` `file_path` against a `str` field.
Both therefore raised a pydantic `ValidationError` on **every successful call
over the wire**, *after* the document had already been replaced, while all 22
body-level tests passed: the body builds a plain dict and never constructs the
model, so the two lines between provider and tool were untested. The tools now
declare `PlanLifecycleResult` (no `format`, because neither writes a file; and
`was_dirty` read **before** the mutation, because a new or loaded document
clears the flag and reading it afterwards is structurally always `False`).
`tests/integration/test_agent_api_lifecycle.py` calls both through the **real
MCP transport** against a real `GardenPlannerApp`. The general lesson: when a
tool's result crosses a `BaseModel`, that model needs coverage at the same level
as the handler, and the cheapest form is one transport test per new result type
rather than per tool.

## Addendum (US-D2.5 — shape/structure creation, #329)

`create_object`
continues to build through `ProjectManager._deserialize_item_core`, now with
explicit circle, rectangle, ellipse, polygon, polyline, and callout families.
Vertices use the native scene centimetre/Y-up frame with no conversion; the
rectangular polygon convenience form expands to the same four loader points as
an explicit request. `HOUSE` is a composite creation: the ridge endpoints
are computed by the Qt geometry-only `core/roof_ridge.py` helper shared with the
polygon tool, and `CreateItemsCommand` adds the house plus its linked ridge
in one undo step. Callout `item_id` is persisted so UUID addressing survives
a save/load round trip. A Qt-free discovery function and a full-roster drift
guard make support decisions explicit. Direct `ROOF_RIDGE`,
`GARDEN_JOURNAL_PIN`, `GENERIC_TEXT`, and legacy `HEDGE_SECTION` creation
is refused with reasons; these are deliberate gaps, not accidental omissions.
The extension is additive and does not bump `FILE_VERSION`.

## ADR-034 addendum: `render_3d_view` (Phase 17 L6.3, #390, ADR-072)

A second vision tool next to `render_canvas_image`, and like it `structured_output=False`
(`[ImageContent, TextContent]`, no `structuredContent`). Read-only, so it is registered without a
token and needs none. `anyio.to_thread` plus `run_on_main(timeout=30)`: the longest hop of any
read tool, because a picture and its PNG are one hop on the main thread. **It never waits for the
view:** when the view is closed, warming up or recording, the provider raises `CaptureRefused`,
which reaches the client as a clean error sentence in under a millisecond of work, never the
bridge's timeout. A refusal changes nothing, and no call builds an engine or switches a view: the
owner's camera and date never jump. Its camera is validated before the main thread is asked
(all six coordinates or none, finite, within 10 km, eye not on target, field of view 5 to 120°);
its size is clamped like the canvas render's, to 128..2048.

## ADR-034 addendum: Package F1/F2 curated traits and shared diagnostics

`garden://species` includes recorded food-forest layers/functions. `get_object` exposes curated lowercase trait values for plants (unknown/empty defaults) and null for other objects, alongside the saved metadata. These are read-only additions; authentication and write tools are unchanged. Diagnostic records retain existing fields/messages and add structured `details`; guild warnings carry guild/centre IDs, function and required/present counts. The API adapter delegates to `services/diagnostics.py`, also consumed by the sidebar. Guild warnings come from the last coordinator snapshot, subject to the documented debounce delay.
