---
name: ogp-architecture-contract
description: >
  The load-bearing architecture contract for Open Garden Planner: the invariant
  table, the module dependency map, the command-pattern write path, and the
  known weak points. Load this BEFORE designing any feature, adding a module or
  package, or touching serialization (.ogp / FILE_VERSION), undo/redo, layers,
  beds/containers/plant-parents, task status, plant sizing, rotation/resize
  geometry, or the agent_api (MCP) surface — and whenever you are asking "is
  this allowed architecturally?", "does an ADR already cover this?", or "which
  predicate / write path / chokepoint do I use?". Also load it before reviewing
  someone else's design.
---

# OGP Architecture Contract

This skill is the binding design contract for `open-garden-planner`
(PyQt6 desktop garden-CAD app). It states **what must stay true**, **why**,
**what breaks if you violate it**, and **what enforces it**. Everything below
was verified against the repo on **2026-07-03** (app v1.23.0, `FILE_VERSION`
`"1.4"`, master after Package D US-D1.3). Re-verify volatile facts with the
commands in "Provenance and maintenance" at the end.

Jargon used once and defined here:

- **`.ogp`** — the JSON project file (ADR-003). **`FILE_VERSION`** — its schema
  version string in `src/open_garden_planner/core/project.py` (currently `"1.4"`).
- **ADR** — Architecture Decision Record; all live in one file:
  `docs/09-architecture-decisions/README.md` (ADR-001…ADR-034).
- **Seam** — a single chokepoint function/module through which a whole class of
  behavior is routed (this codebase's favorite pattern).
- **Qt-free** — a module with no PyQt6 import, unit-testable without a QApplication.
- **Agent API** — the embedded, loopback-only MCP-over-HTTP server in
  `src/open_garden_planner/agent_api/` (ADR-033/034).

## When NOT to use this skill

- **How an invariant was learned** (the bug sagas, wrong theories, log lines) —
  that is `ogp-failure-archaeology`. This file states the rule, not the story.
- **Qt/CAD mechanics** (why `ItemIgnoresTransformations` drops mouse grabs, how
  Y-flip painting works, quadtree math) — `ogp-qt-cad-reference`.
- **Domain semantics** (what a succession plan or soil amendment *means*) —
  `ogp-garden-domain-reference`.
- **Process gates** (branching, draft PRs, senior-reviewer, versioning, merge
  rules) — `ogp-change-control`.
- **Debugging a live bug** — `ogp-debugging-playbook` / the `debug-verbose` skill.
- Pure doc edits, translations-only changes, or reading code without designing
  anything: you don't need the contract, just don't contradict it.

---

## 1. Invariants (the heart of this skill)

Every row was verified against docs **and** source. Violating any row is a P0/P1
in senior review. Column "Enforced by" is the test or mechanism that catches you.

| # | Invariant | Why | What breaks if violated | Enforced by |
|---|-----------|-----|-------------------------|-------------|
| 1 | **Coordinate frame:** scene stores **cm** in the nominal Qt-native **y-down, origin top-left** labeling, but the data path consumes raw scene y directly as **CAD Y-up** — the *view* flips display via `transform.scale(zoom, -zoom)` (`ui/canvas/canvas_view.py:609`) so larger scene-y renders higher/bottom-left origin (ADR-002, §8.1). The status bar, DXF (`dxf_y = scene_y`), and serialization consume raw scene y with no conversion — the `scene_to_canvas` *helper* has **zero production callers**. Explicit Y-flip seams that DO convert: the coordinate-input parser (ADR-021, flips typed math-up Y to scene at `core/coordinate_input/parser.py` — inline `-b`, not via the helper), thumbnail/minimap mapping (§8.9.5/8.9.6), and the agent render-pixel formula (ADR-034 D1.3). Full reconciliation (why §8.10 abstract vs §11.4 operative disagree) is owned by **`ogp-qt-cad-reference` §1**. | One flip, in one place, keeps every geometry computation in a single frame. | Double-flipped or unflipped geometry: items land mirrored, typed coordinates go the wrong way, angles negate, text renders upside-down. | `test_agent_api_render_coordinate_frame.py` pins the render frame; integration tests use scene coords per §8.10. |
| 2 | **Rotatable rect-bearing items** (`CircleItem`/`RectangleItem`/`EllipseItem`) serialize as `pos + rect().center()` with rotation as a separate angle, so **every geometry mutation must end with `transformOriginPoint() == rect().center()`**. Route resizes through the single primitive `resize_handle.resize_rect_item_keeping_anchor(...)`; rotation pivots on `rect().center()`, **never** `boundingRect().center()` (a runtime-only badge expands boundingRect asymmetrically). (§8.9.8, ADR-028, #218/#219.) | The save format assumes pivot == geometric centre; badges are never serialized, so a badge-dependent pivot disagrees between save and load. | Rotated items drift on save/reload and jump on the next rotation — silent geometry corruption. | `tests/integration/test_rotation_aware_resize.py` (shape×angle×handle matrix), `test_rotation_pivots_about_rect_center_with_badge`, `test_apply_keeps_rotated_plant_centered`. |
| 3 | **Exactly two ways onto the undo stack:** `CommandManager.execute(cmd)` (runs it) and `CommandManager.register_applied(cmd)` (for changes already applied live, e.g. a finished drag). Both emit `stack_changed` → `mark_dirty`. **Never** hand-append `_undo_stack` or hand-emit signals (#209; `core/commands.py:68/86`). `undo()`/`redo()` also emit `stack_changed`; `clear()` does not (so new/load stays clean). | Dirtiness and every panel-refresh path hang off `stack_changed`; a third path silently skips them. | Post-save undo/close silently discards changes (the #209 data-loss bug); panels go stale. | Docstring contract in `commands.py`; `tests/integration/test_panel_refresh_wiring.py`; senior review treats a raw append as P0. |
| 4 | **One user gesture = one undo step.** A multi-part change (geometry+position, metadata+resize+override, mirror of N items, agent write in D2) is one composite command. Live drags mutate directly and `register_applied` one command on release; curve reshapes use whole-geometry snapshot commands (`SetCurveGeometryCommand`, ADR-025). Free-text fields commit on 600 ms debounce/focus-out, not per keystroke (#210, #214). | Undo must match user intent; per-keystroke or per-sub-step commands make Ctrl+Z useless and (post-#209) trigger N heavyweight refreshes. | "Undo does half of it"; undo-stack spam; calendar-refresh churn. | §8.2 rule; `test_properties_panel_incremental.py`; ADR-025 point 5 idiom. |
| 5 | **`LayersPanel` is a pure view.** Every layer mutation (add/delete/rename/reorder/visibility/lock/opacity) goes through the layer commands in `core/commands.py` (`AddLayerCommand`, `DeleteLayerCommand`, `RenameLayerCommand`, `ReorderLayersCommand`, `SetLayerPropertyCommand`, `MoveToLayerCommand` — verified lines 1476–1724). Opacity drags coalesce via `canvas_scene.preview_layer_opacity()` + commit-on-release (#207/#208). Never hand the panel a mutable alias of `scene.layers` (defensive copy). | Layer ops must be undoable and dirty the document like everything else (invariant 3). | Un-undoable layer edits; the §11.4 panel↔scene list-aliasing bug. | FR-LAYER-08/09; layer command tests; comments in `ui/panels/layers_panel.py`. |
| 6 | **Task status has ONE write path:** `ProjectManager.set_task_status` (`core/project.py:687`). `set_task_completion` (:298) is a compat shim delegating to it; the `.ogp` `task_completions` key is a **write-only serialized mirror** (older binaries read it; nothing in-app does). Every surface reading/writing status must derive `task_id` via the shared `make_calendar_task_id()` (`services/task_generator.py:172`) + canonical `species_key()` (`models/plant_data.py:370`, ADR-016: `source_id → scientific_name → common_name`, strip+lower). (ADR-029 + #227/#228 addenda.) | Two surfaces (Tasks tab, calendar dashboard) share one status store; ids derived two ways silently diverge even with correct writes. | "Done on one tab, still open on the other" — the exact PR #227 bug. | `test_calendar_task_convergence.py`, `test_tasks.py::TestCrossSurfaceSync` / `TestStatusFlows`. |
| 7 | **Bed-only features are built centrally**, never per-shape: `GardenItemMixin.build_bed_context_menu(menu, *, grid_enabled, supports_grid, supports_soil)` + `dispatch_bed_action` returning `BedMenuActions` (`ui/canvas/items/garden_item.py:37/490/533`; ADR-017, §8.14). The context-menu guard is `is_plant_parent_type`, with `supports_grid=supports_soil=is_bed_type(...)`. New bed feature = the 6-step playbook in §8.14, ending with a new `assert actions.<field> is not None` in the parametrised test. | Bed-capable shapes are FOUR classes (Rect/Polygon/Ellipse/Circle) + containers + trellis; per-shape copies shipped broken twice in three months. | The new feature is missing from one or more shapes and nobody notices until a user report. | `tests/integration/test_bed_context_menu.py` (parametrised over every plant-parent shape). |
| 8 | **Predicate split (ADR-031):** `is_bed_type` = *soil-capable* (`GARDEN_BED`, `RAISED_BED`, `CONTAINER`, `CONTAINER_ROUND`, `WALL_PLANTER`); `is_plant_parent_type` = soil set + `TRELLIS`; `is_container_type` = litres-by-height subset. All in `core/object_types.py:595/608/622`. **Pick by seam:** soil features (tests, mismatch, amendment volume, grid overlay) → `is_bed_type`; parent/relationship features (reparenting, child propagation, context menu, "Contained Plants") → `is_plant_parent_type`. New "things plants live in/on" are `ObjectType` tags on existing shape items, **not** new `QGraphicsItem` subclasses. | One predicate can't express "parent but no soil" (trellis); new item classes cost ~16 dispatch sites each (rejected repeatedly in ADR-022/031/032). | Trellis gets soil tests, or containers miss reparenting; or you inherit the "new serializer + resize + constraint wiring" tax. | Predicate docstrings; `test_container_gardening.py`, `test_trellis.py`; agent-api drift guard `test_agent_api_mapping.py` (asserts inlined name sets == `SOIL_CONTAINER_TYPES`). |
| 9 | **`.ogp` evolution is additive-first.** New persisted data = a new top-level key or additive `metadata`/item key that old apps ignore and old files load without (defaults). `FILE_VERSION` (currently `"1.4"`, `core/project.py:34`) bumps are **rare and deliberate** — only for changes an old app cannot safely ignore (e.g. new item *types*, 1.4 = arc/bezier). The loader rejects files with `version > FILE_VERSION`. Smart symbols are the model case: serialized as `type:"group"` + `smart_symbol` metadata, old apps degrade to a plain group (ADR-032). | Every bump locks all older installs out of new files; the additive ethos keeps files exchangeable across versions. | Users on older versions can't open shared plans; or (worse) an old app silently drops data it didn't know it had to preserve. | `test_container_roundtrip.py` (round-trip + unbumped FILE_VERSION), `_is_newer_file_version` guard in `project.py`, ADR review of any bump. |
| 10 | **Qt-free/Qt-touching split.** Domain logic that *can* be Qt-free *must* be: `core/plant_sizing.py`, `core/container_model.py`, `core/parametric_eval.py`, `core/coordinate_input/parser.py`, `services/task_generator.py`, `services/task_status.py`, `services/harvest_aggregation.py`, `models/smart_symbol.py`, and in `agent_api/`: `schema.py`, `mapping.py`, `queries.py`, `diagnostics.py`, `providers.py` (the `agent_api/` modules are verified: no PyQt6 import — see the anchored grep in Provenance). Note `services/task_generator.py` is Qt-free logic *except* `from PyQt6.QtCore import QCoreApplication` used solely for `translate()` (it holds no QObject state and is unit-tested without `qtbot`). Qt-touching agent modules are exactly `bridge.py` (QObject signal marshaling) and `render.py` (the one documented exception). | Qt-free code is unit-testable without a QApplication, reusable off the main thread, and immune to teardown crashes. | Logic becomes untestable-without-GUI; agent tools gain hidden main-thread requirements. | Module docstrings state Qt-free-ness; `grep PyQt6` (see Provenance); tests import these modules without `qtbot`. |
| 11 | **Import direction:** `ui` imports `core`/`models`/`services`; `core` never imports `ui` **at module level** — where core code must dispatch on item classes (`mirror_geometry`, `auto_constraint`, `measure_snapper`), the `ui.canvas.items` import is function-local or `TYPE_CHECKING`-only, explicitly "to avoid import cycles (items import core)". `app` wires everything and may import anything. | Prevents import cycles; keeps core loadable headless. | `ImportError` cycles at startup; core silently grows a hard GUI dependency. | Convention + the in-code comments; verify with the Provenance grep. |
| 12 | **Agent API safety model (ADR-033/034, §8.19):** (a) tool handlers run on the uvicorn thread and touch Qt **only** via `MainThreadBridge.run_on_main` (queued signal + Future); (b) Qt-touching handlers are `async def` and offload the blocking hop via `anyio.to_thread.run_sync` (a sync handler blocks the event loop — verified against mcp 1.28.1); (c) reads use `ProjectManager.snapshot_dict()` which never mutates state (`sync_journal=False`); (d) server binds **127.0.0.1 only** (`server.py:304`, "never 0.0.0.0"); (e) surface is **read-only; token auth is a hard prerequisite before any D2 write tool** — there is currently no auth (verified: no token code in `server.py`); (f) shutdown calls `bridge.abort_pending()` *before* `server.stop()`. | Qt is main-thread-only; an unauthenticated localhost server must not be able to mutate the user's plan; close must not deadlock on an in-flight hop. | UI freezes/crashes from off-thread Qt access; any local process could edit the plan; hang on app close. | `test_agent_api_bridge.py` (marshaling/timeout/abort), `test_agent_api_server.py` (end-to-end), the `bridge.py` house-rule docstring. |
| 13 | **Agent writes (D2, not yet built) go through the command system:** the ADR-033 contract is that edit tools route through `MainThreadBridge` identically to reads and "go through the existing undo system" — i.e. one agent operation registers as **one undoable command** on the same `CommandManager` (invariants 3–4 apply unchanged). Do not invent a parallel mutation path for agents. | The user must be able to Ctrl+Z anything an agent did, and dirtiness/panel refresh must fire. | Agent edits that can't be undone or don't dirty the document — data loss with an external actor. | ADR-033 ("write-ready core", "token auth gates D2 writes"); design review of any D2 PR. |
| 14 | **Exception-handling trust rule (PR #236, §11.4):** at a seam that ingests **untrusted input** (user-dropped JSON, network responses, opened files), put **one broad `except Exception`** at the ingestion chokepoint (log-and-skip / degrade); keep **narrow typed catches only for first-party/bundled input** so our own bugs crash loud. Never enumerate exception families at a trust boundary. `BaseException` still propagates. Model: `services/smart_symbol_library.py` (user loop broad, bundled loop narrow). | Enumerating families lost three rounds in a row — each new poison file found an unlisted family. Untrusted input must be non-fatal *by construction*. | A crafted/corrupt user file crashes the app; or, inverted, a packaging bug in bundled data gets silently swallowed. | `tests/unit/test_smart_symbol_library.py` (poison files skipped; malformed bundled crashes loud). |
| 15 | **Plant sizing precedence has one home:** Qt-free `core/plant_sizing.py` (`PlantSizing`, `sizing_for_item`, `db_spacing_radius_cm`). Precedence: manual `spacing_radius_cm` override > DB `max_spread_cm/2` > None; spacing ring shown only when effective > drawn footprint. Species *assignment* routes through the single undoable `ApplySpeciesCommand` path (never bare `item.metadata["plant_species"] = ...`, which doesn't repaint and is masked by overrides). (ADR-028, #213/#218.) | The precedence was re-encoded inline in three files and drifted; bare metadata writes skip `prepareGeometryChange()`. | Ring size wrong on screen vs. data; silent no-op species assignment. | `tests/unit/test_plant_sizing.py`; §11.4 contract entry. |
| 16 | **i18n:** every user-visible string goes through `self.tr()` (QWidget/QDialog), `QCoreApplication.translate("Context", ...)` (non-QObject, e.g. QGraphicsItem menus, command descriptions under context `"Commands"`), or `QT_TR_NOOP` (module-level dicts). Hardcoded English f-strings bypass Qt Linguist **and the i18n gate test cannot see them** — it only checks *registered* strings for unfinished translations (full gate mechanics: `ogp-diagnostics-and-tooling` §1.2/1.3, the canonical home). Exemptions: MCP tool/prompt descriptions (English API contract), Latin plant names, data-baked names like smart-symbol `name`/`name_de`. | German is a shipped language; the gate test has a documented blind spot for unregistered strings. | English leaks into the German UI, undetectably by CI. | `tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` (registered strings only — the review must catch plain strings); §8.3. |
| 17 | **In-scene handle grab allow-list (ADR-025 pt. 7):** any new `ItemIgnoresTransformations` in-scene drag handle must be added to `CanvasView`'s dropped-grab re-grab tuple (`ResizeHandle`, `RotationHandle`, `VertexHandle`, `RectCornerHandle`, `MidpointHandle`, `CurveControlHandle`). | PyQt6 silently drops the mouse grab on such children between events; the view re-grabs only for listed types. | The handle gets the press but no move events — drag dead on arrival (bit US-B9 in manual test round 1). | Manual testing; the tuple's comment in `canvas_view.py`. |
| 18 | **Teardown-safe chatty-signal slots:** any `scene.changed` slot that starts a `QTimer` wraps `.start()` in `contextlib.suppress(RuntimeError)` (never a bare `lambda: timer.start()`); any slot on an app-global signal (`focusChanged`, …) must survive firing after its widget died. Sidebar lists store item **ids**, resolve via `scene.find_item_by_id` at click time, and defer scene mutations with `QTimer.singleShot(0, ...)` (#212, #230, #235). | `scene.changed` fires during teardown after child QTimers are deleted → `Fatal Python error: Aborted` (interpreter abort, CI-killing). | Whole test suite aborts mid-run; "selection works only sometimes". | §11.4 entries; `canvas_view._on_scene_changed_for_soil` et al. as the pattern. |

## 2. Module map and dependency rules

Verified against `docs/05-building-block-view/README.md` §5.2 and the source tree.

| Package (`src/open_garden_planner/…`) | Role | May depend on |
|---|---|---|
| `main.py`, `__main__.py` | Entry points (incl. the mandatory pre-QApplication `QtWebEngineWidgets` import, ADR-019) | everything |
| `app/` | `application.py` (main window `GardenPlannerApp` — the wiring hub), `settings.py` (`AppSettings`), `paths.py` (the ADR-027 dialog-directory chokepoint), `ui_state.py` | `ui`, `core`, `models`, `services`, `agent_api` |
| `ui/` | Canvas (`ui/canvas/` — view, scene, `items/`), panels, dialogs, views (dashboard tabs), widgets (`panel_stack.SidebarController`, gallery, toolbars) | `core`, `models`, `services` |
| `core/` | Commands + `CommandManager`, `ProjectManager` (save/load/snapshot), `object_types` (predicates), constraints + solvers, `snap/` engine, `cad_geometry`, `mirror_geometry`, `coordinate_input/`, `tools/` (drawing tools), `plant_sizing`, `container_model`, `parametric_eval` | `models`; PyQt6 QtCore/QtGui freely; **`ui` only function-local/TYPE_CHECKING** (invariant 11) |
| `models/` | Pure data: `plant_data` (incl. `species_key`), `task`, `harvest_log`, `smart_symbol` | stdlib (Qt-free where marked) |
| `services/` | Qt-free domain engines (`task_generator`, `task_status`, `harvest_aggregation`, `smart_symbol_library`, shopping list, soil, crop rotation) + Qt-using I/O services (export, `scene_rendering`, pdf report, dxf, weather) | `core`, `models`; never `ui` panels |
| `agent_api/` | Embedded MCP server (see invariant 12). Qt-touching: `bridge.py`, `render.py` only | `core` (snapshot shapes), `services/scene_rendering`; wired by `app/` |
| `resources/` | Data (`plant_species.json` — the single species+calendar source, ADR-014; `smart_symbols/*.json`), icons, textures, translations, web | — |

Rules of thumb: **new domain logic starts Qt-free in `core/` or `services/`** and
gets a thin Qt adapter; **`application.py` is wiring, not logic**; anything both
dashboard tabs or multiple shapes need lives at ONE seam (see invariants 6, 7, 15).

## 3. The write path: command pattern (§8.2, ADR-004)

`CommandManager` (`core/commands.py`) is a hand-rolled stack (a `QObject` with
`pyqtSignal`s — **not** `QUndoStack`, despite ADR-004's original wording; verified:
no `QUndoStack` anywhere in `src/`). Owned by `CanvasView`, shared to
`CanvasScene` via `scene.get_command_manager()` so `QGraphicsItem` subclasses can
push commands from interaction handlers.

- `execute(cmd)` — runs `cmd.execute()`, appends, clears redo, emits
  `command_executed` + `can_undo/redo_changed` + `stack_changed`.
- `register_applied(cmd)` — appends **without re-executing** (for live-applied
  drags/edits), same signal set. These two are the only entry points (invariant 3).
- Signal consumers: `stack_changed` → `mark_dirty` + panel refreshes (properties,
  constraints, plant-db, companion, crop-rotation, debounced calendar);
  `can_undo/redo_changed` → toolbar enablement **only**; `calendar_view` is
  deliberately on `command_executed` + debounced `schedule_refresh` (#210/#225).
- Command `description`s are user-visible → translated under the `"Commands"`
  i18n context (invariant 16).
- Composite/edge idioms: whole-geometry snapshot commands for curves (ADR-025),
  destructive-conversion commands that store the original item for undo
  (`FilletCornerCommand`, ADR-022), one-step multi-item commands
  (`MirrorItemsCommand`, ADR-026), param-edit-as-`ChangePropertyCommand` with an
  apply_func (smart symbols, ADR-032).
- **D2 agent writes inherit all of this** (invariant 13): one MCP write call →
  one `run_on_main` hop → one command via `execute()`/`register_applied()`.

## 4. Known weak points — stated plainly

Do not "discover" these; they are known, documented, and mostly deliberate.

| Weak point | Status (2026-07-03) |
|---|---|
| **#206 rebuild-on-repaint firehose.** `scene.changed` fires on every repaint; several panels historically rebuilt themselves off it. Band-aids in place: properties panel does identity-keyed incremental refresh (#222/#223), plant-search list has a debounce + row-signature early-return (#212). The structural smell — chatty signal driving full scene re-queries — **remains**; any new panel wired to `scene.changed` must be debounced AND idempotent (diff before rebuild). | Open smell, band-aided |
| **TD-007 `EDGE_*` anchor instability.** Polygon/polyline edge anchors classify by dominant axis (`EDGE_TOP/BOTTOM/LEFT/RIGHT`); moving a vertex far enough flips the classification and constraint indicators jump edges. Workaround: index-only match in `_resolve_anchor_position`. Real fix (stable `EDGE_MIDPOINT` + numeric index) not done. | Open, medium, workaround in place |
| **TD-008 numerical Jacobian.** Newton refinement uses central differences (`constraint_solver_newton._JACOBIAN_H`), not analytic derivatives. Accepted: microseconds at ≤20 variables. Revisit only if large-scene solves bottleneck. (ADR-012.) | Accepted, low |
| **No token auth on the agent API.** Loopback-only, read-only, on by default. Any local process can read the open plan. **Token auth is the explicit blocker before D2 write tools** (ADR-033) — do not add a write tool without it. | Open by design; hard D2 gate |
| **Heavyweight calendar refresh (#210 trade-off).** `PlantingCalendarView.refresh()` is expensive; it is kept off the per-command hot path via debounced `schedule_refresh()` that skips while the tab is hidden (#225), and weather arrives via `_rebuild_dashboard()` (not full `refresh()`) to avoid a fetch loop. Don't wire it to anything chattier. | Mitigated trade-off |
| **Two divergent item serializers** (found in ADR-026): `CanvasView`'s clipboard pair (has `text`, drops `layer_id`/`item_id`, no arc/bezier) vs `ProjectManager`'s save/load pair (has arc/bezier + ids, no `text` branch). Neither covers everything; Mirror deliberately bypassed both by rebuilding live items. If your feature needs "serialize any item", **do not trust either alone**. | Open, unconsolidated |
| **DXF gaps:** Bezier curves rasterize to line segments (native cubic export deferred, ADR-022); smart-symbol INSERT rotation sign is a known nuance (unrotated exact); DXF blocks key on `(symbol_id, params)` so identical-param instances share the first one's colour (ADR-032). | Known limitations, logged |
| **`is_bed_type` naming debt:** the name now means "soil-capable" (includes containers/wall planters), not literally "bed". A rename to `is_soil_container_type` was rejected as a ~30-site churn; documented trade-off (ADR-031). | Accepted readability debt |
| **i18n gate blind spot:** `test_german_ts_has_no_unfinished` only sees *registered* strings; a plain English f-string in a user-visible path passes CI silently. Review is the only defense. | Structural test gap |
| **Smart-symbol `version` field is a strict geometry contract:** editing a bundled symbol's geometry without bumping its `version` silently re-renders already-saved plans (ADR-032). Sidebar panel currently hidden via one line: `application.py:1574` `set_panel_visible("smart_symbols", False)`. | Sharp edge + deferred UI |
| **Agent diagnostics may lag a debounce tick** — `get_diagnostics` reports the last *computed* badge state, never recomputes (ADR-034). Fine for read-only inspection; don't build write logic on it. | By design |

## 5. Before you design anything — checklist

Work through this in order; it takes five minutes and has repeatedly saved
multi-round review cycles.

1. **Read the ADR index** (`docs/09-architecture-decisions/README.md`). Is your
   problem already decided (possibly with your exact idea listed under
   *Alternatives considered — rejected*)? Respect the rejection or write a new
   ADR superseding it — don't relitigate silently.
2. **Does it touch an invariant above?** Serialization → row 9; anything that
   moves/resizes/rotates → row 2; any mutation → rows 3–5; beds/containers/
   plants-in-things → rows 7–8; tasks → row 6; agent surface → rows 12–13;
   file/network/user-JSON input → row 14. Name the rows in your plan.
3. **Pick the seam, don't add a call site.** New bed action → §8.14 playbook.
   New sizing rule → `plant_sizing.py`. New task surface →
   `make_calendar_task_id` + `species_key`. New dialog → `app/paths.py`
   defaults. New snap kind → a `SnapProvider` (ADR-020/023). New "thing plants
   live in" → an `ObjectType` + predicate membership, not a new item class.
4. **New persisted data?** Default to an additive key with old-app degrade
   semantics written down. A `FILE_VERSION` bump needs an ADR-grade
   justification (it locks out old installs) — see ADR-032 for the graceful
   alternative pattern.
5. **New ADR needed?** CLAUDE.md triggers: new dependency, choosing between
   approaches, changing a pattern, or a non-obvious constraint. If your design
   doc contains the word "instead", it probably needs an ADR.
6. **Can the logic be Qt-free?** If yes, it must be (invariant 10): pure module
   in `core/`/`services/`, thin Qt adapter, unit tests without `qtbot`.
7. **Plan the tests that enforce, not just cover:** parametrised-over-shapes for
   anything multi-shape, drift guards for duplicated constants, a pinning test
   for any invariant you extend (that's how every row above stays true).
8. **Then** switch to `ogp-change-control` for branch/PR/review process, and
   check `ogp-failure-archaeology` if you're touching a subsystem with a saga
   (rotation/resize, tasks, sidebar, snap/constraints, agent API).

## Provenance and maintenance

All claims verified 2026-07-03 against master (v1.23.0). Re-verify with:

- `grep -n 'FILE_VERSION = ' src/open_garden_planner/core/project.py` — schema version (row 9)
- `grep -n 'def execute\|def register_applied\|stack_changed' src/open_garden_planner/core/commands.py` — two-entry-point contract (row 3)
- `grep -n 'scale(self._zoom_factor, -self._zoom_factor)' src/open_garden_planner/ui/canvas/canvas_view.py` — Y-flip at the view (row 1)
- `grep -n 'def is_bed_type\|def is_plant_parent_type\|def is_container_type' src/open_garden_planner/core/object_types.py` — predicate split (row 8)
- `grep -n 'def build_bed_context_menu\|def dispatch_bed_action' src/open_garden_planner/ui/canvas/items/garden_item.py` — bed-feature seam (row 7)
- `grep -n 'def set_task_status\|def set_task_completion' src/open_garden_planner/core/project.py` and `grep -n 'def make_calendar_task_id' src/open_garden_planner/services/task_generator.py` — task write path (row 6)
- `grep -rlE '^(from|import) PyQt6' src/open_garden_planner/agent_api/` — must list only `bridge.py` + `render.py` (row 10). Use the anchored form: a bare `grep -rl PyQt6` false-alarms on the "No PyQt6" docstrings in `queries.py`/`mapping.py`/`diagnostics.py`.
- `grep -rn 'from open_garden_planner.ui' src/open_garden_planner/core/` — every hit must be function-local or TYPE_CHECKING (row 11)
- `grep -n '127.0.0.1\|token' src/open_garden_planner/agent_api/server.py` — loopback-only, still no auth (row 12)
- `grep -n '8.9.8' docs/08-crosscutting-concepts/README.md` — pivot invariant text (row 2)
- `sed -n '29,45p' docs/11-risks-and-technical-debt/README.md` — TD table (§4)

If any command's output contradicts this file, **the repo wins** — update this
skill in the same PR that changed the fact.
