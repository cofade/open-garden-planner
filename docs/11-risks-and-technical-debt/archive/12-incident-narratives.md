# Archive 12: Incident narratives outside Phase 17

Verbatim copies of chapter-11 §11.4 text as it stood at b1faaa9. Nothing here is edited; each standing rule these narratives support is indexed in [§11.4](../README.md#114-known-development-pitfalls) and lives in its numbered file under [pitfalls/](../pitfalls/).

## Archive L184: A cleanup fixture that runs in the wrong ORDER is not a cleanup — and a plausible mechanism is not a mechanism.

Source: README at b1faaa9, lines 184-184 (PF-TST-04).

- **A cleanup fixture that runs in the wrong ORDER is not a cleanup — and a plausible mechanism is not a mechanism.** (Issue #366, the exit-139 segfault; **UNRESOLVED**, and this entry records what is known rather than a story that reads well). What is known: on this branch CI segfaulted on roughly half its runs, and the crash stack's only project frame is `agent_api/server.py` ``_run`` — the crashing thread IS a live uvicorn event loop. What is **not** known: which test leaves it. Two attempts are on the record and neither closed it. (1) `AgentApiServer.stop()` was a bounded best-effort join — set `should_exit`, join 5 s, log a *warning*, return with the thread still running. It now takes a second bounded grace join and escalates to `logger.error`. (2) An autouse `tests/integration/conftest.py` fixture stops any server a top-level app still owns. Attempt (2)'s *first* version also had the wrong **timing**: pytest finalises fixtures in **REVERSE setup order**, so a fixture that does not request `qtbot` may run after `qtbot` has deleted the window — stopping a server whose providers already point at a dead QObject. Requesting `qtbot` makes it tear down last, while the app still exists. **That general lesson stands: an ordering-sensitive teardown must declare its dependencies explicitly, because "after the test body" and "after every other teardown" are not the same moment.** What did *not* stand was the mechanism the guard's docstring asserted — that `QTimer.singleShot(1500, _maybe_start_agent_api)` lets an app auto-start a server during tests. **It cannot**: `tests/conftest.py`'s autouse `_disable_agent_api_server` sets `KEY_AGENT_API_ENABLED = False` for every test. That claim was written with a citation-shaped confidence and checked by nobody, and the final pre-merge review falsified it from the suite's own fixtures. Two rules from that. (a) **A causal story in a pitfall log is a lead, and a lead with a `file:line` reads as a verdict** — so state the evidence and the gap separately, and never let a hypothesis harden into an assertion just because it is repeated. (b) **Check that the mechanism can happen before documenting it**, and check the guard's actual reach: this one reaches the *app's* server only, so tests that construct `AgentApiServer(...)` directly (`test_agent_api_exports.py`, `test_agent_api_frozen_exe.py`) are outside it — though all of those do call `stop()`. A thread-inventory run also over-reported: it flagged threads *appearing* during a test, not ones surviving, so most of its hits were servers starting and stopping normally. Both CI Test runs at the reviewed tip passed, which is **not** evidence the cause is gone. If this recurs it needs its own investigation, starting from the stack rather than from this entry.

## Archive L209: This shipped over seven senior-review rounds, each finding a real, live-reproducible defect in the previous round's own fix

Source: README at b1faaa9, lines 209-215 (PF-DOM-04).

**This shipped over seven senior-review rounds, each finding a real, live-reproducible defect in the previous round's own fix** — not cosmetic disagreements, but `AttributeError`s and silent data loss, several caught only by making the actual API call rather than reasoning from the code. Specifics worth knowing before touching this code again:
- A validation guard that rejects `common_name in ("", "Unknown")` as "bad response" is wrong: Trefle omits `common_name` for many valid, scientific-name-only species. Validate identity via `source_id` alone.
- Merging two records by wholesale replacement (`self._selected_plant = detail`) silently destroys any field the richer record happens to leave sparse. A field-by-field merge that defers to the *other* record only when the "winning" value is empty/default is the only version that can't lose data in either direction — and it must treat a present-but-`None` value as empty even for fields whose own default isn't `None` (`None == ""` is `False`, so a naive equality check misses it).
- A comment asserting a fact about live API behavior ("never observed live", "every lookup below is `.get(key) or default`") is worse than no comment when it's wrong, and it *was* wrong twice in this saga — once about `main_species` being non-null, once about a sweep actually being complete. Trust a fresh live check over a prior comment's claim.
- `dict.get(key, default)` only applies `default` when the key is ABSENT, not when present-with-null — the same trap #296 already documented, re-found three more times in this same file (`main_species`, then `scientific_name`/`family`/`genus`/`image_url`, then `observations`/`growth.description`/`flower.conspicuous`/`default_image`'s two URL fields) because each sweep trusted its own "done" comment instead of re-scanning the whole file.
- Opening a modal (`QMessageBox.warning()`) from inside a commit path (`_on_accept()`, before `self.accept()`) is a re-entrancy hazard the same way a blocking network call is: its nested Qt event loop can deliver a still-pending timer (here, `PlantSearchDialog`'s 500ms search-debounce timer) mid-commit. Same failure class as the #210 debounce/flush incident elsewhere in this file — stop any pending debounced action before anything destructive commits, as the literal first statement if needed.

## Archive L218: Update (manual testing, 2026-08-10): a defect one layer above the seven-round fix, invisible to every review round.: The

Source: README at b1faaa9, lines 218-219 (PF-DOM-06).

**Update (manual testing, 2026-08-10): a defect one layer above the seven-round fix, invisible to every review round.** The user reported "Tomato" showing Full Shade/Low water/no pH after search+confirm — looking exactly like the fix had failed. Live-probing `TrefleClient` and the merge logic directly (bypassing the dialog) proved the enrichment pipeline itself was correct: `Full Sun`/`Medium`/`pH 7.0-7.5`, matching Trefle's real API data. The actual cause was pre-existing and one layer up: `PlantAPIManager.search()` always searches the user's local custom-plant library **first**, concatenated ahead of any API result with **no deduplication** — and the real, unstubbed `%APPDATA%\OpenGardenPlanner\custom_plants.json` on the test machine had accumulated 197 entries (180 of them duplicate "Walnut" test debris), including a stale custom "Tomato" record with wrong sun/water values whose `source_id` happened to collide with Trefle's own numeric id. That record was returned first, displayed with text identical to the real Trefle result (`Tomato (Solanum lycopersicum)`), and — correctly, by design — skipped enrichment entirely because `data_source == "custom"`. **Fix**: every search-result row now shows its data source (`plant_source_label()` in `ui/plant_species_assignment.py`, shared with the properties panel's own "Data Source" tooltip so the two can't drift apart), so a stale custom entry can never again be visually indistinguishable from a live one. **Lesson**: isolated worktrees and mocked HTTP structurally cannot catch a bug that only exists in real, unstubbed machine state — a developer's own accumulated custom-plant-library file is disk state outside git, outside every test fixture, and outside every reviewer's clean worktree. Manual testing against the actually-running app is the only phase in this project's workflow that can see it, which is exactly why CLAUDE.md makes it the final, sovereign gate rather than a formality after review passes.

## Archive L222: A first cut of this fix shipped a severe, unrendered regression a senior-review pass caught before merge

Source: README at b1faaa9, lines 222-223 (PF-CAN-03).

**A first cut of this fix shipped a severe, unrendered regression a senior-review pass caught before merge**: the decorative drop-shadow (a cosmetic depth effect, unrelated to sun/shade) was left keyed to the full mature `rect()` while the icon shrank, so a young plant rendered as a large grey disc with a tiny sprite inside — measured at 57.6% grey coverage of the frame, up from 1.5% before the icon shrank. No test caught it because every test asserted against the private `_visual_plant_diameter_cm`/`boundingRect()` helpers, never against an actual rendered frame — reverting the one changed line in `paint()` would have left all tests green. Fixed by computing the diameter **once** at the top of `paint()` and reusing it for both the drop-shadow and the icon, so the two can never disagree again. Two further gaps from the same review: `plant_database_panel._update_instance_metadata()` only called `prepareGeometryChange()` for `current_spread_cm`, but `current_height_cm` (via `growth_model._derive_from_other`) and `planting_date` (more elapsed time — more growth, even with no other field touched) can equally change what `boundingRect()` returns — now called unconditionally for every plant-instance write, since it's cheap; and `current_spread_cm`'s spin box (max 10 000) had no path into `render_plant_pixmap`'s `int(diameter)`-square `QImage` allocation before this change, the exact hazard US-D2.1 already capped for a different entry point — `plant_renderer.py` now clamps at the actual allocation site (`_MAX_RENDER_DIAMETER_PX = 5000`, protecting every caller, not just this one). Deliberately not reconciled: dragging a plant's resize handle no longer visibly changes its icon once growth data is set (the icon now tracks the growth timeline, not the footprint) — an accepted consequence of decoupling the two, not something this fix tries to paper over. Also deliberate: the icon uses **today's real date**, not the sun-simulation's scrubbed date — scrubbing the sun timeline changes the shadow/heatmap/3D but not the icon.

## Archive L228: Available API fields silently discarded, independent of the crash above (issue #296).

Source: README at b1faaa9, lines 228-229 (PF-DOM-08).

**Available API fields silently discarded, independent of the crash above (issue #296).** The same audit found each client extracting only a fraction of what its API actually returns, with direct, unambiguous mappings to already-existing `PlantSpeciesData` fields going unused. Confirmed live and fixed: Permapeople provides `images.thumb`/`images.title` but the client hardcoded `image_url`/`thumbnail_url` to `""` with a comment claiming "Permapeople doesn't provide images in API" — false, disproven by every one of the 10 test plants returning a populated URL, though 2 of the 10 (Blueberry, Sunflower) turned out to be the same shared blank-placeholder image, not a real photo — the mapping is still correct (Permapeople itself falls back to that placeholder, our client shouldn't invent a distinction it doesn't make), but neither `image_url` nor `thumbnail_url` is currently rendered anywhere in the app for any source, so this stores data with no consumer yet. It also provides a `"Life cycle"` key (`cycle` stayed `UNKNOWN` for every Permapeople plant — a stale comment had guessed the unrelated `"Layer"` design-category field might indicate cycle), `"Height"`/`"Width"` in metres (never reached `max_height_cm`/`max_spread_cm`, so the auto-resize-footprint-to-species-size feature, #213/#218, could never fire for a Permapeople-sourced plant), `"Genus"` (hardcoded to `""`; live-confirmed present on the Apple record, though a broader re-check found it populated on a minority of records overall — still correct to read when present), and `"Soil pH"` (never reached `ph_min`/`ph_max`, so soil-mismatch diagnostics, US-12.10d, never fired for this source). **A `"Soil pH"` record with only one number (e.g. `"6.5"`, not a range) deliberately maps to `ph_min = ph_max = None`, not to that value twice** — the first cut of this fix set both ends to the single value, which collapsed the acceptable band to zero width; `get_mismatched_plants()`'s tolerance is a deliberately tight ±0.05 (see its own comment there), so every real soil-test reading that wasn't that *exact* value produced a false mismatch warning (live-reproduced against Permapeople's actual "Walking onion" record, caught in a second senior-review round). A single number is an optimum, not a band — only a genuine range gives both ends. Permapeople is also third (last) in the fallback chain (`PlantAPIManager.search()` breaks on the first provider to return any results), and Trefle answered all 10 of this audit's test queries — so with a Trefle token configured, none of these Permapeople mappings are consulted either, for a different reason than Trefle's own reachability gap below. **This has real, previously-invisible downstream effects, not just richer data**: `max_height_cm`/`max_spread_cm` now reaching a Permapeople-sourced plant means `plant_species_assignment.apply_species_to_item()` (#213/#218) silently resizes its drawn footprint on assignment where it never did before, and `core/object_height.effective_height_cm()` falls back to species `max_height_cm` when an object type has no built-in default — `TREE`/`SHRUB`/`PERENNIAL` have none, so a Permapeople tree/shrub that previously resolved to `None` (no shadow, no 3D extrusion) now gets a real height and participates in the Phase 14 sun/shade system. Both are the *intended*, correct consequence of fixing the field mapping, not a side effect to guard against — flagged here so it's a known, deliberate change in scope rather than a surprise the next time someone touches either subsystem. Trefle provides `growth.ph_minimum`/`ph_maximum` (near-identical field names to our own, live-confirmed populated on Carrot: 6.5/7.0 — **the first cut of this fix read them from `specifications` instead of `growth` and shipped a hand-written test whose payload matched that mistake rather than the real API, so it passed on broken code; caught in senior review, re-verified against the actual cached live response before fixing** — see the type-design lesson below) and `growth.soil_nutriments` on the same 0-10 scale Trefle's `light`/`atmospheric_humidity` already successfully map to `sun_requirement`/`water_needs` in the same file — `soil_nutriments` -> `nutrient_demand` just hadn't been wired up yet (live-confirmed Carrot: 6, Tomato: 8; Trefle's own docs confirm this is the plant's *demand* — "required quantity of nutriments... how much fertility the species needs" — not a tolerance, so the mapping direction is correct). **Deliberately not mapped**: a nitrogen fixer (legumes) should report `"fixer"`, which the 0-10 scale alone can't express — `specifications.nitrogen_fixation` looked like the natural override, but it's a documented *string* field with an unspecified value domain, and it came back `null` on every one of 46 live legume records sampled in review (Trifolium, Medicago, Vicia, Glycine, Lupinus, Robinia, and others). Mapping a field with no verified populated example — exactly the mistake this entry's own lesson warns about, one field over — was reverted rather than shipped on faith. Trefle's `growth.minimum_temperature`/`maximum_temperature` (°C, live-confirmed populated) could inform `frost_tolerance`, but that field feeds the frost-alert feature (US-12.2) — a wrong threshold policy could suppress a real frost warning, so it needs its own reviewed story rather than riding along with an unrelated field-mapping cleanup. **Known limitation, not fixed here**: Trefle's `search()` endpoint (what every real user search actually calls) returns a sparse payload with none of `growth`/`specifications`/`foliage` at all — live-confirmed on Carrot's search result (only identity/taxonomy fields). Every mapping in this paragraph, and the pre-existing `light`/`atmospheric_humidity`-derived `sun_requirement`/`water_needs` mapping, only ever executes via `get_by_id()`'s richer detail response — and nothing in the application currently calls `PlantAPIManager.get_by_id()` from the search-selection flow. So today, for a plant found via Trefle search, all of this (including the two fields that shipped before this PR) silently stays `UNKNOWN`/`None` regardless of this fix; it takes effect only if a future story wires a detail fetch into species selection. Filed as issue #297 rather than expanded into this fix. **Update**: #297 is now fixed — see the entry above. **Lesson**: when a client wraps a rich external API into a narrow internal model, re-audit the mapping periodically against live responses — comments asserting "the API doesn't provide X" rot silently and are trivial to disprove with one real request; and a hand-written test fixture that encodes the implementation's own (possibly wrong) assumption about a schema's shape will pass on broken code — verify against a captured real response instead. See issue #296 for the full field-by-field table (including what's captured but never surfaced in the Properties/Plant-Details panel, and what's provided by neither API and only ever comes from the bundled 118-species DB).

## Archive L246: Closed (#228): task status now has a single write-path

Source: README at b1faaa9, lines 246-247 (PF-DOM-09).

- **Closed (#228): task status now has a single write-path** (US-C2, #188, ADR-029): "is this task done" was originally persisted in **two** stores kept in sync at every chokepoint — the legacy `task_completions` set (read by the calendar dashboard) and the new `task_states` dict (read by the Tasks tab) — with the standing invariant that any new write path had to touch both or the surfaces silently diverged. The convergence (#228) retired that: `set_task_completion` now delegates to `set_task_status` (the single source of truth), and the calendar dashboard reads `effective_status` instead of `task_completions`, so the latter is a **write-only serialized mirror** kept only for `.ogp` forward/back-compat (older binaries still read it). There is now exactly one write-path; no future edit needs to remember the dual-write. Pinned by `test_tasks.py::TestStatusFlows::test_calendar_done_toggle_syncs_task_states` (mirror still maintained) and `test_calendar_task_convergence.py` (both surfaces agree). **The remaining caution:** any surface that reads the shared status store must still derive the `task_id` through the shared `make_calendar_task_id()` + canonical `species_key()` (the ADR-029 PR #227 addendum invariant) — convergence didn't change that.

## Archive L270: Release workflow race condition with chore commits

Source: README at b1faaa9, lines 270-271 (PF-CI-05).

- **Release workflow race condition with chore commits**: After merging a feature PR, two chore commits are pushed (sync version + mark progress). These land ~37s after the PR merge but the Release workflow building the new tag takes ~2m50s. The chore-commit Release runs start while the tag doesn't exist yet, compute a stale version (e.g., `v1.8.4` instead of `v1.9.2`), and fail with "release with the same tag name already exists". Fixed by adding `if: "!startsWith(github.event.head_commit.message, 'chore:')"` to the release job, which skips the workflow for chore commits.

## Archive L282: Agent API described the compass backwards (issue #267, fixed)

Source: README at b1faaa9, lines 282-283 (PF-API-16).

- **Agent API described the compass backwards (issue #267, fixed)**: every Agent API tool description (move/read/spatial/render) called the scene frame "origin top-left, +y down" — Qt's *default* convention, but wrong for OGP, which is CAD Y-up (ADR-002; see the *Canvas Y-axis flip* entry above). Because the scene renders north-up, an agent told "move the bed 7 m south" computed `dy = +700` and the bed moved **north**. The *math* was correct and internally consistent (read + move + spatial all use raw scene y); only the descriptions lied. Fixed by rewriting every agent-facing description to state **origin bottom-left, +x east, +y north (a larger y is further north); to move south, pass a negative dy**. NOT fixed by negating `dy` in the tool — that would desync `move_object` from the read tools it must stay consistent with. The render pixel formula (`px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`) was already correct (Y-up image, top-down pixel rows) and test-pinned; only its prose was corrected. Regression-guarded by `tests/unit/test_agent_api_auth.py::test_move_object_description_uses_y_up_compass_frame` (the description must say north/south, never "+y down").

## Archive L354: Never default a file dialog into the install directory; never let the uninstaller wipe it blind

Source: README at b1faaa9, lines 354-355 (PF-CI-07).

- **Never default a file dialog into the install directory; never let the uninstaller wipe it blind** (issue #199): Two independent bugs combined to destroy user data on Windows. (1) `QFileDialog.getSaveFileName`/`getOpenFileName` called with `""` as the *directory* argument open in the process **current working directory** — for a packaged build that is `C:\Program Files (x86)\Open Garden Planner`, so users naturally saved `.ogp` plans inside the install folder. (2) The NSIS uninstaller ran `RMDir /r "$INSTDIR"` and the upgrade path (`.onInit`) silently invokes that *old* uninstaller before installing the new build — so every "update" deleted the whole install dir, user plans included. Symptom: "all my gardens vanished after updating." Fixes, both required: app side — `GardenPlannerApp._default_dialog_dir()` resolves every save/open/export dialog to the open project's folder or `<Documents>/Open Garden Planner` (`app/paths.get_projects_dir()`), never CWD; installer side — the uninstall section copies any top-level `$INSTDIR\*.ogp` to `$DOCUMENTS\Open Garden Planner\Recovered Plans` *before* `RMDir /r`, so even pre-existing victims keep their data on the next upgrade. Lesson: user data must never live under `$INSTDIR`, and an installer must treat `$INSTDIR` as possibly containing user files. Regression tests: `tests/unit/test_paths.py`, `tests/integration/test_save_location.py` (the NSIS half is Windows-only, verified manually).

## Archive L387: The test suite wrote into the developer's real plant library — isolating one store is not isolating the process

Source: README at b1faaa9, lines 387-395 (PF-TST-09).

- **The test suite wrote into the developer's real plant library — isolating one store is not isolating the process** (found 2026-10-11 during Phase 17 L1; fixed in `tests/conftest.py`, §8.10 "Test isolation"):
  - **Symptom.** The developer's own `%APPDATA%/OpenGardenPlanner/custom_plants.json` held 209 custom plants, 207 of them the same "Walnut (Juglans regia)"; `plant_lists.json` in the same folder had been rewritten that morning by nobody. Every full run of the suite, by any agent on the machine, added one more Walnut. (Counted by whoever found it; the fix was written and tested without opening that folder.)
  - **Root cause.** `tests/conftest.py` isolated the settings store (#285, the entry above) and nothing else. `services.plant_library.get_app_data_dir()` resolves `%APPDATA%/OpenGardenPlanner` (or `$XDG_DATA_HOME/…`) on every call and was never redirected, so every store built on it — the custom plant library, plant lists, seed inventory, companion rules, smart symbols, the weather cache — was the user's real one in a test process. `tests/ui/test_plant_database_panel.py::…::test_sparse_species_saves_back_as_none` calls `panel._on_field_changed()`, whose last step saves the edited species through `get_plant_library()`: a correct test of the panel, and a write into the real library. Two test files had even noted the gap in a docstring ("isn't isolated by `tests/conftest.py`") and stubbed their own way around it; nobody closed it.
  - **Fix.** The conftest sets `APPDATA` and `XDG_DATA_HOME` to a per-process temporary directory at import time — the same place and for the same reason as the settings redirection. No production code changed. The real directory was not cleaned by this change: what to do with the 207 entries is the owner's decision.
  - **The same search found three more writers outside the test root**, none of them into the user's own app folder, all through `QStandardPaths.writableLocation`: (1) `tests/unit/test_main_hardening.py::TestExceptHook` appended a traceback to `%APPDATA%/pytest-qt-qapp/crash.log` on every run — 331 of them, 82 kB, when counted; (2) the companion, climate and thumbnail caches under `%LOCALAPPDATA%/pytest-qt-qapp/`, which survive from run to run, so a test could pass on a cache an earlier run had filled; (3) `tests/unit/test_paths.py::test_get_projects_dir_falls_back_to_home` created `~/Documents/Open Garden Planner` on every machine it ran on, because `get_projects_dir()` creates what it returns. (1) and (2) are closed by redirecting the Python-level function, (3) by giving that test a home of its own.
  - **Lessons.** *List every place the app writes* (`get_app_data_dir`, `QStandardPaths`, `Path.home()`, the temp directory) and decide each one — redirected, or left with a reason. *A test that is correct about the unit can still be wrong about the world:* the Walnut test asserts what it should and has passed since it was written. *A known gap written into a docstring is a defect with a comment on it.* And the pin must not need the thing it protects: the end-to-end test never reads the real directory — it watches what the process opens (`tests/integration/test_app_data_isolation.py`).

  - **One review later: four more, each outside what "the app-data directory" had made anyone look at** (L1.1 fix round 3, 2026-10-11). (1) **A test read another tool's credentials.** `tests/unit/test_ai_client_onboarding.py` redirected `APPDATA` for the client it was about; `detect_clients()` asks every client in the registry, and the others hang off `Path.home()` — the test opened the developer's real `~/.claude.json`, `~/.codex/config.toml`, `~/.config/opencode/opencode.jsonc` and `~/.gemini/config/mcp_config.json`. Reads, not writes; of files that hold tokens. The module now gives every test a home of its own. (2) **A library has user files too.** ezdxf loads `~/.config/ezdxf/ezdxf.ini` when it is imported and builds *and writes* `~/.cache/ezdxf/font_manager_cache.json` when that is missing (read in the installed 1.4.3, not by touching the home); `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` now point into the test root. (3) **The stand-in was kinder than the thing it stands for.** The replacement for `QStandardPaths.writableLocation` created the folder it named; Qt does not, so a writer without its own `mkdir` would have passed every test and failed on a first run. It names the path only, and a test shows every writer making its folder. (4) **Scripts are outside all of it.** A script that imports the app is not a pytest process: its settings are the user's own — on Windows the registry, which no environment variable moves — and `ProjectManager.save()` / `.load()` end with `add_recent_file`. Probe and generator runs replaced a developer's whole Recent Files list with fixture paths. `scripts/script_isolation.py` (§8.10, "A script is not a test") and a test that runs each script as a script. (5) **And one layer further, a review later** (fix round 4): on Windows the profile variables move only part of what Qt hands out — `AppLocalDataLocation` and `CacheLocation` follow the shell, not the environment — so a script's isolation installs the suite's own stand-in too; the list of scripts that isolate themselves was kept by hand, so every file under `scripts/` is read now; and one onboarding test could still START a client CLI it found. *The question "where does the app write?" has a second half: "and who else runs the app?" — a test, a child process, a script, a probe. Each needs its own answer, and an answer for one is none for the next.*

## Archive L398: `QGraphicsScene.changed` feedback loops: a slot driven by `scene.changed` that itself mutates the scene runs forever while the app is idle

Source: README at b1faaa9, lines 398-399 (PF-LIF-09).

- **`QGraphicsScene.changed` feedback loops: a slot driven by `scene.changed` that itself mutates the scene runs forever while the app is idle** (issue #305 — a macOS user's OGP process reached **134 GB** after ~1 h in the background; the whole system froze). Measured on Windows (offscreen, real `GardenPlannerApp`, counting `scene.changed` emissions and `QGraphicsScene.render` calls per fixed window after a 1.5 s settle — the probes are now the tests in `tests/integration/test_idle_scene_quiescence.py`), **four independent loops** existed, each of the same shape: (A) `MinimapWidget._do_update()` hides every overlay item (`ItemIgnoresTransformations` or z ≥ `_OVERLAY_Z_MIN`) for the thumbnail render and re-shows them afterwards; for a **transformable** overlay item each `setVisible()` makes the scene emit `changed`, which restarted the 100 ms throttle → `_do_update` again. With one such item the minimap re-rendered the **whole scene ~9×/s forever** (13–14 renders per 1.5 s vs 1 with none). Measured in senior review: `setVisible()` on an `ItemIgnoresTransformations` item emits **no** `changed` at all — and every handle, label and badge in this app carries that flag — so selection handles were *not* a Loop-A trigger; in production only the curve-edit connector lines (transformable, z ≥ 10000) are, and the reporter's idle churn came from B–D below — and a minimap the user had toggled *off* still rasterised the scene on every change into a widget nobody could see. (B) `CanvasView._update_soil_mismatches()` (500 ms debounce on `changed`) called `item.update()` **unconditionally** for every bed — one never-selected `GARDEN_BED` on an otherwise empty plan: 16 `changed` + 8 renders per 4 s, forever. (C) `_update_spacing_overlaps()` (150 ms) and (D) `_update_companion_highlights()` (60 ms) both did a *clear pass* (`set_spacing_overlap(None)` / `set_companion_highlight(None)` + `set_antagonist_warning(False)` on every plant) followed by a *set pass* — so although the item setters have an early-return guard for unchanged values, the handlers forced every value through None each tick: **one gallery-dropped plant with database spacing** (`max_spread_cm`, which FR-PLANT-15 populates on every drop) → 19 `changed` + 20 renders per 3 s forever; tomato + fennel 60 cm apart → 47 `changed` per 3 s. **This one was missed by the first fix and caught in senior review**: the "companion/spacing quiesce" claim had been measured with a `GENERIC_RECTANGLE`, which those handlers skip entirely — a measurement that tests nothing about them. Every loop feeds **every** `changed` subscriber (companion, spacing, plant-search 150 ms, snap dirty flag, sun-shadow debounce, minimap): a full-scene `render()` into fresh `QPixmap`s plus O(n²) scans per cycle with nobody at the keyboard. **Two subtleties that make this class hard to see:** `setVisible()`/`update()` do **not** emit `changed` synchronously — Qt queues the emissions for later event-loop turns (measured: a single hide already yields `[rect]` then `[]` on **two separate turns**, both after the mutating method returned — the empty one is Qt's trailing emission), so a naive in-call re-entrancy flag is **not** enough — and neither is a single `singleShot(0)`, which a first cut used and which was measured to clear the flag between the two emissions; and the emission carries only *rects*, not the item that changed, so a subscriber cannot tell its own churn from a user edit by identity. **Fix**: the minimap's `changed` slot is **content-based** — it records the scene rects of the overlay items it just toggled and ignores an emission iff every rect lies inside one of them (an empty rect list is Qt's trailing no-op; measured, every genuine mutation carries ≥ 1 rect) — no timing window, so a genuine change sharing the same turn is still rendered; a toggled-off minimap no longer renders at all; the soil handlers became **idempotent** (write the tooltip / call `update()` only when the level or text actually changed; `SoilBadgeItem.update_position()` no-ops on unchanged pos — measured: `setPos`/`setToolTip` with an unchanged value do *not* emit `changed`, `update()` does); spacing and companion compute the **final state per item first and call each setter exactly once** — no clear pass — the discipline `_update_container_capacity()` already had. **Rule for every `scene.changed` slot** (and any slot on a timer that `changed` restarts): it must be idempotent — compute the target state, then apply it once; never call `update()`, `setVisible()`, `prepareGeometryChange()` or add/remove items unless the value really changed, and never "clear then set". **How to check for a new loop**: put one bed, one DB-spacing plant and one selected object on the plan, settle 1.5 s, then count `scene.changed` emissions and `QGraphicsScene.render` calls over the next 2 s — both must be 0; the positive control (move a plant → ≥ 1) proves the counters work. Pinned by `tests/integration/test_idle_scene_quiescence.py` and `tests/unit/test_minimap_widget.py::TestMinimapIdleQuiescence` (including the "genuine change in the same turn is not dropped" and "toggled-off minimap does not render" cases). Not measured: the macOS-side accumulation path from "10 Hz pixmap churn" to 134 GB (Windows RSS stayed flat at ~59 MB over 20 s of the loop) — the loop itself is a defect regardless, and the reporter (macOS 26.6.1, self-built PyInstaller `.app`, plan with constraints on screen, minimap state uncertain) has been asked for an Activity Monitor graph should it recur.

## Archive L575: A silently-dead code path is a hiding place — fixing it *publishes* its content

Source: README at b1faaa9, lines 575-629 (PF-UI-21).

### 11.4.6 A silently-dead code path is a hiding place — fixing it *publishes* its content

**Symptom.** `CanvasView.set_status_message` did
`if self.parent() and hasattr(self.parent(), "statusBar")`. In the production
layout the canvas's parent is the `QSplitter` built in `application.py`, which has
no `statusBar`, so the guard swallowed the miss and every caller was a no-op.
Nothing was broken and nothing was visible — the #415 propagation-date refusal
"refused visibly" into a void.

**Why it became a P0.** #415 fixed the route (a signal, wired to
`statusBar().showMessage`). That delivered the refusal *and* published the ~24
strings the dead route had been suppressing, to every user, at once. Two of them
were not translatable:

- `offset_tool.py`: `self._view.tr("Created {dir} offset of {dist:.1f} cm")` —
  wrapped in the *view's* `tr`, which pylupdate6 cannot extract because it only
  walks `self.tr` inside QObject subclasses;
- `canvas_scene.py`: three calibration prompts passed as **bare literals**, wrapped
  in nothing.

Round 6 had AST-scanned every `tr()` literal under `src/` and found the first. It
could not see the second kind, because a bare literal is structurally invisible to a
scan for translations. Round 7 measured the user-visible result with the German
`.qm` loaded through a real window: the status bar read verbatim
`'Calibration: Click first point on the image'`, `'Calibration: Click second point on
the image'`, `'Calibration complete'`.

`test_german_ts_has_no_unfinished` was blind to all three — it inspects messages
already in the catalogue, and a string never registered is by definition not in it.
This is the same blind spot AGENTS.md records for plain-string call sites, reached
through a different door.

**Fix.** Wrap the three in `QCoreApplication.translate("CanvasScene", ...)` and
register them; the `CanvasView`-context offset string was registered in the previous
round. `tests/unit/test_status_literals_are_translated.py` walks every
`set_status_message` call site and fails on a bare literal, resolving
`.format()`/`.replace()` chains and local variables, so it catches the next one
rather than the next two that happen to already be known.

**Lesson.** Repairing a no-op does not surface what it was suppressing; it
*publishes* it, everywhere, at once. Before repairing one, enumerate what it was
suppressing and check that the content is fit to be published. This is the
converse of the usual "dead code is harmless" intuition, and it has now cost two
P0s across three rounds.

**Also corrected here, from the same investigation:** "1.0-1.5× their stated
maturity" was claimed in §11.4 with no denominator and no harness behind it. The
count is 28 of 64 against the maturity midpoint (44 %), 32 of 64 against
`days_to_maturity_min` (50 %) and 15 of 64 against the maximum (23 %) — so "most
species" holds under no denominator except a bare 50/50 split on the minimum.
`scripts/measure_harvest_offsets.py` now prints all three. (Round 7 measured 17 of
64 against the midpoint; that does not reproduce under this harness's span
definition — the *latest* plausible planting offset — so the number that survives is
the one a committed script prints.)

## Archive L630: The four bugs a manual pass found that a green suite could not (#377, #380, #373)

Source: README at b1faaa9, lines 630-736 (PF-TST-19).

### 11.4.2 The four bugs a manual pass found that a green suite could not (#377, #380, #373)

Four defects, each invisible to the suite for a different structural reason.
They are recorded together because the *reason* each was invisible is the
lesson, not the fix.

**1. A preview whose z-value nobody set (#377).** Every drawing tool builds a
bare `QGraphics*Item` preview and adds it to the scene. Qt gives it the default
`z = 0`. Every real document item gets a *derived* z strictly inside `(0, 100)`
from `CanvasScene._refresh_layer_z`. So the preview lost to every bed and shape
it overlapped and was invisible for the whole drag — while the post-release item
`pop`ped in front, which is why it read as a placement problem and not a
rendering one. **The green suite could not see it because no test had ever drawn
a preview over an existing item**: every tool test drew on an empty canvas, where
`z = 0` is enough. Pinned by `tests/integration/test_tool_preview_z_order.py`
(a real bed in the scene, press/move, assert the preview outranks it) and by a
source-scan drift guard in `tests/unit/test_preview_z.py` that re-derives the
affected module set — because **the issue's own list of 13 modules was wrong**:
it omitted `construction_tool.py` (which does build previews) and named three
modules that build none. A bug report is a symptom description, not a census.

**2. A contract the test asserted at the wrong layer (#380).** The agent path
allowed one full canvas of slack; the test
`test_one_canvas_of_staging_slack_is_reachable` asserted the slack point was
*accepted*. That passed on the day it was written and would keep passing after
the object was stranded, because it tested the *guard*, not the *outcome*. The
defect is that the guard returns the position and the caller did nothing with it.
**An assertion on the input-acceptance of a guard says nothing about what the
system did with the accepted input.** The fix moved the rule to one shared
function (`core/canvas_bounds.py`) and the test now asserts the *outcome* — the
object lies inside the canvas — over the real MCP transport.

**3. A shutdown that only fails with a client attached (#373).** `stop()`'s two
5-second joins expired, but only some of the time: **0.19 s with no client,
10.03 s with an MCP client holding the SSE stream open**. uvicorn's graceful
shutdown waits for open connections, which such a client never closes, so
`serve()` never returned. No test held a client across a stop, so the default
(no-client) path was fast and green. **A lifecycle defect whose reproduction
requires a concurrent peer will not be found by a single-threaded test of the
happy path.** Pinned by `tests/integration/test_agent_api_shutdown.py`, which
opens a real SSE stream, holds it, and asserts `stop()` returns in under 4 s with
no "did not stop"/"STILL RUNNING" record (and, for the no-client stop, no record at
ERROR level from *any* logger). Recorded because the fix is counter-intuitive: uvicorn's
`force_exit` alone **does not** work here (measured — the MCP session/SSE tasks
keep the loop alive past it); the reliable fix is to cancel the loop's tasks and
stop the loop directly. **The test itself then taught a second lesson.** Its
first version asserted `elapsed < _STOP_TIMEOUT_S` — a 5 s budget *sitting
exactly on the 5 s join timeout it guards*. It passed standalone and in a
slice, then failed three tests in one full-suite run and passed the next:
**a threshold on the boundary it is meant to detect is a flake, not a check.**
The fix uses a 4 s limit that cleanly separates the ~0.6 s healthy path from the
~10 s regression, and asserts on the server's **own** thread handle rather than
a global `threading.enumerate()` scan (which a leak in any other test could
fail). A flaky test is worse than a missing one: it trains the reader to rerun
instead of investigate.

**3a. A fix that is right for the pathological case can be wrong for the common
one (#373 review).** The first #373 fix cancelled every task on every `stop()`.
That cured the 10 s hang, but it also cancelled uvicorn's *lifespan* task before
its graceful shutdown could run, so **every** close — including the no-client one
that was already fast and clean on master — now logged a `CancelledError`
traceback at ERROR on the very console #373 was filed from. The test asserted two
log substrings, so it stayed green and the doc claimed "no WARNING/ERROR". `stop()`
now **escalates**: `should_exit` first (~0.2 s, quiet), then — only if the thread
outlasts `_GRACEFUL_STOP_S` (1 s) — force-exit, cancel the loop's tasks and stop
the loop. A flag set by `stop()` (not CPython's "Event loop stopped" message text)
tells `_run` that the resulting `RuntimeError` is deliberate. The forced path
with a client streaming still logs two ERROR tracebacks (the cancelled SSE
request and uvicorn's lifespan task). **That is a decision, not an oversight:**
uvicorn logs the lifespan traceback whenever its task is cancelled, and `_run`'s
`finally` cancels every leftover task anyway, so avoiding it would mean letting
lifespan shutdown run, which is exactly what a held SSE stream prevents. Dropping
a live stream is abnormal; the noise is the honest signal. **Lesson: when a
fix changes the common path to cure the rare one, assert the common path stayed
as quiet as before — against every logger, not the two strings you remember.**

**3b. A review fix can itself regress, and only the full suite caught it.** The
senior review found a real P1: a move the clamp erased entirely still pushed a
dead undo step. The first fix refused any call whose *clamped result* was zero —
and `move_object(item_id, 0, 0)` has a clamped result of zero, because it was
**already zero**. That is a legal no-op a caller uses to re-read an object's
current centre, and an existing test
(`test_move_returned_center_matches_read_layer_with_badge`) depends on it. The
review's own slice passed; the 6736-test suite flagged it. **The refusal must
key on the attempt, not the result: "the request was non-zero and the clamp
erased it", never "the result is zero".** Both directions are now pinned. The
sharper lesson is about review scope — *a P1 fix is new code and needs the same
full battery as the original change*, not the reviewer's slice that validated
the defect.

**4. Two surfaces that disagree while both are correct (#378).** The rotation
panel showed "every crop is suitable" for a bed that had a succession plan,
because the plan is *planned* data and the panel reads *grown* data. Neither
surface had a bug; the defect was that one surface could not explain the other's
answer. **This is not a test-coverage failure at all** — no unit test of either
feature can fail, because both behave exactly as specified. It was found by a
human opening both next to each other. The fix is display-only, and the
load-bearing decision is what was **not** done: feeding the plan into
`CropRotationService` would have changed the 3-year cooldown for every caller, so
the plan stays out of the service and a test pins `get_recommendation`'s output
as identical with and without a plan.

The shared lesson: **a green suite is evidence only about the paths it
exercises.** Three of the four were unreachable by any existing test *by
construction* (empty canvas, single-threaded stop, input-only assertion), and the
fourth was not a code defect at all.

## Archive L737: Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333)

Source: README at b1faaa9, lines 737-819 (PF-API-20).

### 11.4.3 Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333)

Every one of these was found **while building the tests for this package**, not by
the tests failing against shipped behaviour — which is the point. In five of six
cases the code I had just written was confidently wrong, and in the sixth a drift
guard was too weak to notice. Four are worth reading twice, because the shape
recurs in this codebase.

**1. `health_level(record, "ca")` silently returns the OVERALL rating.**
`SoilService.health_level` rates `ph`, `n`, `p`, `k` and `overall` — its
`ALL_PARAMS` is exactly those five, and an unrecognised parameter **falls through
to the `overall` branch** rather than raising. My first `SoilStatus` called it for
all six nutrients, so every bed reported its whole health as calcium's. It reads
as a plausible number, so no assertion style catches it by accident. Fixed by
routing only `RATED_PARAMETERS` through the service and making
`SoilReading.health_level` optional, where `None` means *"no rating exists"* —
deliberately distinct from `'unknown'`, which means *not tested*. **A fall-through
default is a silent wrong answer, and a nullable field is the honest way to say
"this was never computed".**

**2. `TASK_SOURCES` listed two values no generator can emit — and my drift guard
was too weak to notice.** I took the source names from the issue text, which said
`soil_amendment` and `soil_mismatch`. Both soil generators actually emit
`source="soil"`; `task_type` is what distinguishes them. So `TASK_SOURCES` had
seven entries for six real values, and the guard I wrote first asserted only
`emitted <= TASK_SOURCES` — a **subset** check, which passes on extra entries. The
field failure would have been nasty and quiet: `get_tasks(source="soil_mismatch")`
returns an empty list forever, and `get_tasks(source="soil")` — the value that
works — is **refused** as unknown. Two lessons: a drift guard must assert
**equality in both directions**, and a guard that can pass vacuously should assert
it saw something (`assert task_calls >= 7`), because a guard reading the wrong
scope reports success forever. The guard is now AST-based over the module, not
fixture-driven, precisely because four of the seven generators need live inputs a
bare `PlanState` cannot supply — a fixture roster silently under-reports.

**3. `get_effective_record` applies the hierarchy invisibly, so its answer cannot
be attributed.** With only a plan-wide soil test recorded, the service returns the
global record *for a bed* — by design, and correctly for the GUI. An agent handed
that has no way left to tell it from a real bed reading. `record_source` now
carries the provenance, and the provider resolves the two histories directly to
recover it. **A function that returns a value but discards how it got there is
half an API for a machine consumer.**

**4. Credentials-shaped input needs the *shape* validated, not just the range.**
`SoilTestRecord` stores the Rapitest kit scale **and** optional lab `*_ppm`
floats. `40` is a plausible ppm nitrogen reading and an invalid kit level. Worse:
**nothing in `services/` reads the `*_ppm` fields at all** — `health_level`,
`calculate_amendments` and the mismatch check all read `*_level`, and no code
converts between the scales (US-12.10c owns that). So the worst case was not a
wrong number but a record that reports UNKNOWN health, recommends nothing, finds
no mismatches — and looks complete to the caller. The tool now refuses ppm by
name and takes kit-only parameters whose *names state the scale*. Related: the
ranges are **per-nutrient** (`k_level` is `1–4`; the kit has no K0; secondaries
are `0–2`), so one shared range check would have accepted a potassium `0` the
engine then reads as Deficient-but-measured.

**5. `credits` is a 3-tuple and I unpacked it as a 2-tuple.** `(kind, current,
target)`, not `(kind, delta)`. A `ValueError` at the first recommendation, caught
by the field-for-field equality test — which is exactly the test that existed to
prove the wrapper computes nothing. **An equality test earns its keep on the first
call, not on the happy path.**

**6. The `app` fixture's modal teardown hung the run.** My tests dirty the plan,
and pytestqt closes the window in its own teardown, where `closeEvent` raises a
modal unsaved-changes dialog. Clearing `_dirty` in a fixture finalizer does not
help: the finalizer can run *after* pytestqt already closed the window. Fixing it
on the instance (`_confirm_discard_changes = lambda *_: False`) works regardless of
ordering. **A test that hangs is a test that has told you something about ordering.**

Two smaller notes for the next person. `WriteResult.action` is a `Literal`, so a
new write action fails at *runtime* with a pydantic error rather than at import —
the tool is registered, the server starts, and the call fails. And
`ProjectManager.manual_tasks` stores `ManualTask.to_dict()` values, **not**
objects, which is easy to assume otherwise and costs an `AttributeError`.

The shared lesson is narrower than §11.4.2's and worth stating separately: **the
defects in this package were all cases of a plausible-looking value that was not
the value the engine means.** A fall-through branch, a name copied from prose, a
hierarchy applied invisibly, a range that looked uniform and is not three times
over. Each was found by a test that compared against the *engine* rather than
against an expected literal — and every one of them would have passed a test
written from the issue text instead.

## Archive L1080: A widget that rewrites a displayed date for "readability" corrupted persisted data.

Source: README at b1faaa9, lines 1080-1081 (PF-PER-17).

- **A widget that rewrites a displayed date for "readability" corrupted persisted data.** Symptom: the planting calendar's propagation editor moved each step's displayed date into the current year, start and end independently; a step crossing New Year was saved into the `.ogp` as `start 2026-12-24 / end 2026-01-22` — an inverted step that `compute_propagation_plan` then applied verbatim, so the corruption was permanent for any plan already saved. Wrong theories: (a) that the defect was in the override *writer* alone, so fixing the editor would repair existing files — it would not, because the *reader* applies stored overrides without validation; (b) that swapping the pair on load would be the helpful repair — it would silently rewrite what the user typed. Fix: the editor now shows each step's real dates, and an override whose end precedes its start is **ignored on read and refused on write**, leaving the stored value in the file untouched (no data destroyed, no impossible step displayed). Two further defects surfaced in the same 40-line function and are now covered by the same tests: the editor wrote an override on every `dateChanged` and ran the calendar's full `refresh()` each time — one user gesture produced one *write and one refresh* per keystroke, and the refresh re-fetches the weather. It now commits **once per gesture**, on a 600 ms debounce plus focus-out, mirroring `properties_panel._TEXT_COMMIT_DEBOUNCE_MS`, and a gesture touching several steps emits one batch so the refresh happens once (not once per step). Note what this is and is not: it is *not* an undo step. A propagation override is written straight into `ProjectManager._propagation_overrides` and no `Command` reaches the `CommandManager`, so an override is not undoable at all — a pre-existing gap this change does not close. Invariant 4's one-gesture-one-step rule is what the batching works towards, not what it delivers. The species detail line was five hardcoded English f-strings that the i18n gate is structurally blind to. *A date field that reformats what it holds for display is a data-corruption site; check who reads the persisted value back before deciding the repair, and prefer ignoring an impossible stored value over rewriting it.*

## Archive L1095: Guild boundaries found by independent review (F1/F2)

Source: README at b1faaa9, lines 1095-1108 (PF-DOM-23).

### 11.4.8 Guild boundaries found by independent review (F1/F2)

Guild happy-path insertion tests did not establish document lifetime, copy isolation or translated refusal behavior. Review reproduced a mirror copy whose species dictionary still aliased the source, a grouped existing centre whose ancestor layer was locked, a stale search-detail response accepted after another selection, and malformed imported trait shapes that could invent functions through substring matching. The fixes deep-copy the complete copied metadata, check every ancestor layer, invalidate enrichment on selection changes, and normalize imported trait containers without inferring values. Unknown data remains preserved.

A second review exercised plan replacement while a placement preview or sidebar click was pending. Four preview wrappers survived scene clearing and `clear_preview()` raised a deleted-C++-object exception; loading a plan with the same UUIDs caused the queued click to select an object in the replacement document. Document replacement now closes the picker before teardown, clears coordinator status synchronously, and cancels pending navigation. UUID resolution must be coupled to document lifetime. Regression tests cover same-ID replacement as well as empty scenes.

Validation errors now have Qt-free codes and structured parameters. API text stays English; UI adapters translate the known code and field labels. Translating only an outer error sentence left its generated reason in English. Actual German editor and deleted-centre refusal tests pin the complete user-visible message, beyond the unfinished-translation gate. No undocumented Qt timer-reentrancy claim is made: the separate timer experiment did not reproduce it.

The full battery found one further representation boundary: existing task/soil tests construct `RectangleItem` plants, so semantic `is_plant_type` does not guarantee `CircleItem.radius`. The badge coordinator now skips geometry for plants with no badge/status and uses the actual rectangle or bounding rectangle when an update is needed. A regression covers an ordinary rectangular plant and an imported rectangular guild centre, retaining serialized geometry. Subsystem-only green tests had omitted this representation. Review also loaded a polygon plant and selected it through the real picker: it was eligible but insertion assumed `rect()`. One `guild_plant_bounds()` helper now uses the base rectangle/polygon/path geometry for centre positioning, boundary preflight, previews and badges. Rotation-parametrized round-trip picker tests cover this path and exact undo restoration.

**F1/F2 owner manual-pass follow-up (PR #433).** The German guild picker displayed English catalog names, and selecting a gallery plant then drawing it ignored food-forest auto-assignment. Instrumentation showed `[F1] auto=True species=shrub chosen=<active-id> active=<active-id>` from `CircleTool._finalize_circle`; the previous integration test exercised only the drag/drop constructor. Circle placement now uses the same `build_plant` constructor as drops, preserving plant metadata, planting-date stamping, parentage and one-step undo. Names in the guild picker, editor and member list use display-time translations, including the previously unregistered bundled catalog names. The saved English names and canonical keys are unchanged, and explicit object names are preserved. Regression tests assert German widget contents and both eligible-layer assignment and fallback behavior; table completeness alone cannot establish either contract.

**Final PR #433 review: deferred P2 maintenance finding.** The synchronous `PlantSearchDialog._enrich_selected_plant()` helper has no callers; selection acceptance uses the asynchronous `_on_accept()` / `_poll_results()` path. Stale comments in the dialog and provider base still reference the synchronous helper. This creates a future validation/fallback maintenance risk, with no observed runtime defect or outstanding P0/P1. A separate cleanup should remove the unused helper and update those references while retaining the asynchronous enrichment integration tests.

## Archive L1109: Sun self-shadow and late document results (#314, #428)

Source: README at b1faaa9, lines 1109-1118 (PF-DOM-24).

## 11.4.6 Sun self-shadow and late document results (#314, #428)

The #314 centre-lookup example assumed the receiving plant was absent from its own ground heatmap. The planning probe measured zero hours for both tomatoes with all solid casters, versus 0 h north and 16.5 h south when only each receiver's own caster was excluded. Zero is a valid measurement only after completed, valid evaluation. The fix preserves the ordinary displayed grid and adds sparse identified receivers in the same explicit run; it does not claim exposure at leaves or model canopy transparency. Whole-day reruns per plant took 17.6 seconds for 20 receivers among 100 casters; batched integer sweeps and vectorized point sampling measured 3.226 seconds for 200 casters/receivers locally.

The document-lifecycle regression was observed failing in all six GUI New/Open/recovery timing cases: a cancelled worker deliberately emitted success and `heatmap_visible()` remained True after replacement. A date-only clear cannot protect document ownership, and `is_running` becomes False before queued success/finished cleanup. The canonical `document_replaced` reset cancels, clears and unchecks before C++ teardown; generation/signature guards reject late results. Ownership stays until finished and the next run is refused while signals remain pending. A malformed prevalidation load deliberately emits no reset and retains the valid current map. Real MCP New/Open and cached diagnostic reads pin the transport seam.

Snapshot comparison must use physical base-shape centres transformed into scene coordinates, not decorated bounding boxes or the assumption that every plant is a circle. Semantic plant types can be imported as rectangles/polygons or grouped. Commands require their own subscription because metadata-only edits may not produce a scene repaint. Cosmetics must be idempotent to avoid an infinite scene-change loop. General diagnostics have one publisher so guild/sun producers cannot erase each other's records.

Review pinned two representation gaps: a badge placed at a concave polygon's bounding-box centre was outside the footprint, and accepted non-dict species metadata raised in the selected-tree timer. Badge rectangles now pass whole-path containment against undecorated base geometry; species snapshots are normalized once. Grouped/imported save-load regressions cover both. The complete suite also caught a delayed destruction callback after a weak clock subscription had been pruned; cleanup now tolerates that already-disconnected state, with a cyclic-collection regression.

## Archive L1119: A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473)

Source: README at b1faaa9, lines 1119-1126 (PF-CAN-18).

### 11.4.9 A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473)

**An unbounded fill is a denial of service a plan file can carry — and the obvious bound does not bound it.** `PolygonItem` painted whatever vertex count a `.ogp` held. A reflex-heavy outline makes one antialiased fill quadratic: measured with the item's own 2.0 pen, ~38 ms at 256 vertices, ~322 ms at 1,024, ~1.4 s at 4,096, ~5.6 s at 16,384 (the bug report measured 10.5 s at 1,024 on its box). The first fix bounded full detail at 1,024 vertices and degraded an over-budget frame to "the outline" — and the independent review, plus a second measurement, showed it bounded nothing: 1,024 was the very count the report called pathological, and Qt strokes a **wide solid pen by building a fill**, so the same 1,024-vertex comb took 319 ms stroked with the item's pen against 4 ms with a cosmetic 1-px pen. The shipped bound is 256 vertices and the degrade uses a **cosmetic** pen and no fill (~4 ms at 1,024, ~69 ms at 16,384); `MAX_POLYGON_VERTICES = 16_384` (a ceiling far above any legible garden outline, at which the degraded 2D outline is ~69 ms) refuses a hostile polygon at the load seam non-fatally. **The degrade also had to be *reachable*.** Qt passes `widget = 0` for every **cached** paint, and every unselected canvas item is `DeviceCoordinateCache`, so the first shipped guard (`widget is not None`, the LOD flat fill's own idiom) selected the empty set: measured through a real view, an over-budget polygon still painted at full detail — 44.7 ms at 1,024 vertices, 589 ms at 16,384 — recurring on every cache regeneration, so the freeze was bounded only by the load ceiling. The discriminator is now the **cache mode**: every export, report, print and agent render path disables caches first (`ExportService._disable_item_caches`), so those stay exact while the cached interactive view degrades, and the regression drives a real `CanvasView` instead of calling `paint()` directly. *An idiom copied from a sibling is not evidence: check that the condition it tests is ever true on the path you are protecting — a cache can make it false, and a test that calls `paint()` itself cannot tell you.* *A cost you can bound is a design choice; a cost you cannot is a bug report waiting for a crafted file — and "draw the outline instead of the fill" is only a bound if the outline is cheap, which for Qt it is not with a wide pen. Measure the degraded path with the pen the item actually uses, or you have bounded the shape, not the paint.*

**A copy must carry both representations of a shape's look, or one of them lies.** The offset tool made a rectangle, circle or ellipse copy in its *type's* default fill, pattern and stroke, while a polygon or line copy "kept all of it" (#470). The asymmetry hid the second defect: the polygon path copied only the live `QPen`/`QBrush`, so the copy looked right until the next save, when `fill_pattern`/`stroke_style` were absent and the loader restored the type defaults. One seam, `core/item_look.py::copy_visual_style`, now copies the serialized attributes (`fill_pattern`, `fill_color`, `stroke_color`, `stroke_width`, `stroke_style`) and the pen/brush together, and both the offset tool and `mirror_geometry` use it. *When an item has a live appearance and a serialized appearance, a copy that writes one and not the other is a round-trip bug wearing a rendering bug's clothes.* Chamfer/fillet/trim have the same shape and are deliberately left to #441 (then on the L1 branch; fixed in v1.30.14) rather than routed here. The loader's own half of the same defect — it rebuilt the brush and pen but never wrote the stored attributes back, so the Properties panel disagreed with the canvas after a reload and the next save overwrote the user's colours (#438/#469) — is fixed in the same branch; see §11.4.10 and the ADR-042 addendum.

**A performance budget cannot see a cost its scenario does not contain — or that its cache hides.** The NFR-PERF-01 reference plan holds no polyline (0 of 990 scene items), so a change making every line's `paint()` 25% slower left all three budget scenarios where they were (#473). The first fix added plain and styled lines to the scenario — but every canvas item enables `DeviceCoordinateCache` and the harness warms the cache before timing, so a cached line is never repainted and a slower `paint()` is still invisible; injecting a 5 ms slowdown into `PolylineItem.paint` moved the measured frame by ~0.3 ms. The shipped scenario disables the cache on its lines and pins that deterministically (a `cacheMode() == NoCache` guard), with 10 short plain fences and 1 short styled gravel path adding a stable ~5 ms. The wall-clock comparison survives only as an *upper* bound: a lower bound made the test a coin flip, because viewport timing on a loaded machine swings by tens of milliseconds in both directions (measured −10 ms to +21 ms on the same view). An absolute per-frame budget for the styled lines is left to #450, which owns the whole-line style walk. *A budget guards what its inputs exercise, on the path they exercise it: "we have a perf test" and "the perf test paints this item every frame" are different claims, and a cache is the quietest way to break the second while keeping the first.*

## Archive L1127: A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass)

Source: README at b1faaa9, lines 1127-1138 (PF-CAN-19).

### 11.4.10 A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass)

**A constant wash cannot recolour a saturated texture.** `_tint_texture` drew a texture and laid the user's colour over it at **alpha 80/255**. Over the brown roof-tile texture (`#ca6846` at the sampled pixel) a light-green fill (`#90ee90`) measured **`#b8925d`** — still brown. The owner set a green fill and the canvas showed "the standard roof tile colour", so the fill colour looked *lost*; a from-scratch control rectangle, styled exactly as they described, rendered the same brown as a file-loaded one, which is what proved nothing was lost on load and the colour was never applied. Raising the wash enough to read (160/255) flattened the low-contrast materials (SAND luminance std 1.62 against the 2.0 floor of `test_texture_paints_with_visible_detail`), so the overlay strength was the wrong knob. The fix is a **luminance map** — every pixel becomes the chosen colour scaled by the texture's relative luminance — which makes the *relative* contrast of the result equal the texture's by construction, i.e. non-flattening is a property, not a tuning. *If a transform must both recolour and preserve detail, preserve it as a ratio the transform cannot change, rather than picking a strength that happens to survive the current assets.*

**The gate proved the wrong claim.** `test_user_colour_recolours_without_flattening` compared **red and blue** — two saturated, far-apart colours. Both passed while the owner's *pale* green rendered brown, and `test_texture_paints_with_visible_detail` measured **absolute** luminance std, which a legitimately dark fill colour lowers for no defect. The gate now also asserts a **pale** colour reads (`g - r > 40`; untinted textures measure about −49) and compares **relative** contrast against the same item's untinted render. Reverting the tint makes 19 of the 48 cases fail. *Coverage by colour extremes is not coverage of the colour space; and a texture-preservation gate must be scale-invariant or it punishes dark colours.*

**A loader that rebuilds the brush but not the attributes rebuilds the wrong truth.** `ProjectManager._deserialize_item_core` restored each item's `QPen`/`QBrush` from the file but never wrote back `fill_color`, `stroke_color`, `stroke_width` or `stroke_style` — and the item constructors pre-seed those attributes with the object type's style (`rectangle_item.py` passes `fill_color=style.fill_color, stroke_color=style.stroke_color, …`). After a reload, the Properties panel read the *type* defaults while the canvas painted the file's colours: on the owner's file `item.stroke_color` was `#228b22` (GENERIC_RECTANGLE's style stroke) while `item.pen()` was `#ff0000`. The next save then wrote those defaults over the user's colours (#438/#469). The loader now restores the stored attributes through `core/item_look.restore_stored_look`, and the serializer no longer falls back to a texture brush's black `color()` for `fill_color`. *Two representations of one fact must be written together; a "restore the brush" path that leaves the attribute behind is how a document quietly rewrites itself.*

**And the test that claimed the look survived a save asserted a value that could not fail.** #470's round-trip check compared the reloaded **pen/brush** while its docstring promised "the look survives" — and its earlier brush-colour assertion (`brush().color()`) was vacuous for a texture brush, which is black on both sides. Round-2 review flagged that assertion; round 3 dropped it instead of replacing it with a real tint check, and the owner's manual pass found the gap the next day. `tests/integration/test_item_appearance_roundtrip.py` now compares **rendered pixels** (and asserts a light-green fill reads `g - r > 40`) across all five shapes plus the Ctrl+D duplicate path. *Deleting a weak assertion is not replacing it; if a test is the only evidence for a claim, the claim loses its evidence the moment the assertion goes.*

**And a test value that equals the default it is meant to prove is restored also cannot fail.** The replacement used the owner's light green `#ff90ee90` — which **is** `GENERIC_RECTANGLE`'s default `fill_color`, so `after.fill_color == item.fill_color` held whether or not the loader wrote anything back. Measured by mutation: deleting only the `fill_color` restore from `restore_stored_look` left that test **passing**; re-pointing it at a non-default colour made it **fail**. The round-trip tests now style items with `USER_FILL` (`#ff1f4fd8`), chosen because it collides with no entry in `OBJECT_STYLES` (asserted by `test_the_test_colours_are_not_type_defaults`, which walks all 52 object types), and the owner's literal green is kept as its own test where it is the subject rather than the evidence. *A regression test proves the defect only when its chosen value is distinguishable from the value the defect leaves behind — otherwise it passes on the broken code, which is the one thing it exists to prevent. When the value must be a realistic one, assert the non-default separately.*

## Archive L1139: A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503)

Source: README at b1faaa9, lines 1139-1152 (PF-CAN-20).

### 11.4.11 A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503)

**A sibling idiom copied twice fails twice, and a test that calls the helper directly cannot see either failure.** #472 shipped its over-budget polygon degrade only after an independent review found the first guard unreachable: `widget is not None` was the LOD flat fill's own idiom (#409), and Qt passes `widget = 0` for every **cached** paint while every unselected canvas item is `DeviceCoordinateCache`. #501's review then reported the identical defect in the LOD guard itself (#503) and left it out of scope. Measured through a real `CanvasScene` + `CanvasView`: `should_use_lod_flat_fill` was invoked once per paint with **no** widget at `fit_in_view` and after four `zoom_out()`s and returned `False` every time, while a `NoCache` control item did see a widget - the one configuration no unselected canvas item is ever in. The tests passed because they called the helper directly with a fabricated widget, structurally unable to notice a condition Qt never supplies.

**Making the guard work would have been the wrong fix, and only a measurement could say so.** The obvious repair - key "interactive" on the item's **cache mode**, exactly as the #472 paint bound already did - was implemented first, and the branch became live for the first time. Measured on the reference plan it was written for (990 scene items, 1600x1000 view, seven rounds of fifteen repaints, both scenarios below the 0.4 threshold): `fit_in_view` at zoom 0.316 read **10.61 and 11.50 ms median with the flat fill disabled, 10.87 ms with it live**, the arms' ranges overlapping entirely; `zoom_step` at zoom 0.348 read **7.97 / 7.98 ms disabled, 8.20 ms live**. All six `tests/perf/test_nfr_budgets.py` cases pass either way, worst reading 12.21 ms against the 16.70 ms budget. The cause is structural and was visible in the code all along: `DeviceCoordinateCache` rasterises a textured item **once** and every later frame is a cheap blit, so the expensive textured `paint()` the LOD existed to avoid was already amortised by the sibling fix shipped in the same PR. The branch could only pay per *cache regeneration**, and the acceptance metric is steady-state repaint. What this establishes is that the effect sits **below this harness's noise** - within-arm variation 8 % against a 0.26 ms between-arm difference, and no reversed-order run was taken, so no claim about which arm is faster survives. (An earlier single-pair reading, 10.58/10.64 and 8.21/7.40, is superseded: it put the `zoom_step` sign the other way. A draft of this very paragraph asserted the ordering it implied and was wrong on its own numbers.)

**The owner's manual pass rejected it, which is why this reads as a deletion rather than a repair.** Making the guard work would have put a design decision on screen that had never been reviewed in the product: below 0.4 an unselected bed, furniture item or plant shows only its flat fill (plant and furniture sprites flat-fill too - they are not pattern-gated), and the early return skips the paint-level diagnostics drawn after it (a bed's grid, crop-rotation indicator, soil-mismatch border and capacity badge; a plant's spacing ring, companion highlight and antagonist badge). The owner works at 20-25 % zoom, well under the threshold, so every texture they work with would have been replaced by a solid colour in exchange for nothing. Issue #503 had offered both repairs - "either the LOD flat fill fires for cached interactive paints ... or it is removed with its rationale recorded" - and the measurement plus the manual pass chose the second. `should_use_lod_flat_fill`, `get_lod_fill_color` and `LOD_FLAT_FILL_THRESHOLD` were deleted. `is_interactive_paint` **was kept**: it is the one definition of "which paint is this", and the #472 paint bound needs it for real (a cached 1,024-vertex comb costs 44.7 ms at full detail and 589 ms at 16,384). Its docstring now says that it classifies paints and does not decide how much detail to draw.

**A negative pin can stop noticing, and a mask in the wrong coordinate frame does not fail - it lies.** Deleting a feature leaves nothing that fails when it returns, so the replacement asserts the *absence* of the regression, and that kind of test has a failure mode a normal suite cannot have: it keeps passing while stopping to look. Three review rounds found it three ways, and none of them was visible from a green run. The sampler took the item's **bounding box**, whose corners are page background for a circle, an ellipse or a polygon, so a *solid* circle measured as high-contrast. The table covered four **classes** while three of the seven deleted call sites sat behind `is_plant` / `is_furniture_type`, which a `GENERIC_*` fixture never enters. And the export mask sat in the wrong frame - `QGraphicsScene.render` composes the painter's scale with a translate by `-source.topLeft()`, and only the scale was applied - which made one case pass at spread 45.97 with a flat fill live. The shared root is one unasserted invariant: **the mask must be the item's interior**, and a mask that is not reads background, which a luminance statistic scores as texture. It is asserted now, as a test rather than a comment.

**The instrument, and how to check it.** `tests/integration/test_canvas_item_cache.py` is the pin: seven entries (the four generic shapes plus a plant circle and furniture rectangle/circle), five zoom levels each plus the export path, the interior taken from `QGraphicsItem.shape()`, a lower-bound-only spread assertion so a future change may soften a texture but not delete it, and `TestTheMaskIsTheItem` for the invariant above. Its calibration table, the seven-entry shape list and the sampler mechanics live **in that file** - not here, because a description restated in nine passages is how this section's own history drifted three times. Run `venv/Scripts/python.exe scripts/verify_lod_removal_mutations.py` to re-apply each of the seven deleted call sites and assert the pin still fails on each; it is a script rather than a test because it rewrites live source files, so it takes a lock, runs alone, and belongs to a review or a pre-merge sweep.

*An idiom is a hypothesis about the framework; a guard needs evidence that its condition is reachable on the path it guards, and a direct-call test is not that evidence. Reachability is necessary, not sufficient - the next question is whether the branch earns the degradation it costs, on the workload it was written for. And a conclusion drawn from one ordering of a noisy measurement is the same class of mistake: both are confident and both are unfounded.*

## Archive L3247: A1 numeric, download and settings boundaries (#453)

Source: README at b1faaa9, lines 3247-3292 (PF-PER-18).

### A1 numeric, download and settings boundaries (#453)

The A1 branch implements AUD-041/042/044/047; owner acceptance and protected merge
remain pending. TD-025 is resolved in the implementation, not yet a shipped claim.

The original failures were reproduced: non-finite JSON reached scene preparation,
a non-finite save overwrote a valid file, HTML labeled as PNG was cached, duplicate
installer assets selected the first entry, and Qt 6.11 Linux settings were mode 0644
under umask 022. Fixes live at shared ingestion/persistence boundaries rather than
only one caller. Geometry validation also checks overflow from finite operands and
live NaN rotation that a conditional serializer would otherwise omit.

Pins: `test_plan_numeric_safety.py`, `test_verified_update.py`, `test_image_download.py`,
`test_a1_plan_safety.py`, `test_a1_download_safety.py`, `test_settings_isolation.py`
and `test_settings_security_startup.py`. Linux evidence uses the locked environment
and real permissions. A successful Windows API mock is never reported as that evidence.
Separate shutdown #480/#483, rotation #485 and unfinished 3D work remain outside A1.

The frozen run exposed host PATH contamination: PyInstaller bundled Poppler's
ICU 78.3 instead of using Windows' native ICU 72.1, breaking WebEngine's required
unsuffixed imports. DLL versions, collection provenance and PE exports identified
the cause; the PE probe needed an export limit above pefile's default 8,192 to
avoid false missing-symbol reports. A controlled-PATH clean build passed both
frozen checks. Match the loader's actual DLL paths before changing Qt pins.

Senior review reproduced four derived-geometry bypasses: translated rectangle
bounds, combined group bounds, a rotated rectangle and decoded image scaling.
Each operand was finite but Qt's resulting bounds were infinite. All four real
load-preservation tests failed before the fix. A fifth regression showed opaque
metadata text `value="NaN"` being incorrectly treated as geometry. The fix checks
Qt's detached item graph before scene mutation, checks live geometry before saves,
checks decoded image extents before scaling and scopes numeric-string validation
to geometry containers. Numeric non-finite JSON remains invalid everywhere.

The earlier review additionally found that a construction line with opposite
finite endpoints can have an infinite span while Qt returns an empty bounding
rectangle. Its real load-preservation test failed first. Raw endpoint differences
and line length are now checked before construction, alongside the detached bounds
gate; an empty Qt rectangle is not sufficient evidence that its primitive is valid.
The same check covers point/anchor/control segments and polygon closing edges.
Arc endpoint and midpoint angle sums are checked before construction. Polyline,
polygon and arc regressions failed first, then passed with the shared arithmetic
guard. Pure huge-finite Qt rendering limits retain their serialized model and remain
outside A1; no coordinate cap or rejection of zero-length primitives was introduced.

## Archive L3322: `qtbot.addWidget` closes a widget, and closing is not deleting

Source: README at b1faaa9, lines 3322-3359 (PF-TST-20).

- **`qtbot.addWidget` closes a widget, and closing is not deleting** (issue #509, 17–18
  October 2026). Symptom: the test suite cost 912.6 s serially, and issue #509's
  premise — that ten files were simply slow — was wrong in an instructive way. The
  leading file, `test_iconography_3c.py`, runs 36 tests in **2.14 s alone** and takes
  **96.7 s** in the suite, and the same file right after `test_main_window.py` takes
  **447 s** with individual theme tests at 60–66 s. Probing `QApplication` directly:
  a clean process holds **0** widgets and one `apply_theme()` round-trip costs
  **1.3 ms**; after `test_main_window.py` it holds **38 271** widgets and **1 580**
  top-level widgets, **0 % of them visible**, and the round-trip costs **22 478 ms**.
  Root cause: `qtbot.addWidget` closes a widget at teardown and nothing ever calls
  `deleteLater()`, so the C++ object and its ~1 270 children survive to process exit
  (only 2 of 30 apps were still reachable by `gc.get_objects()` — the Python wrapper
  is collected, the C++ graph is not). `apply_theme()` walks `app.allWidgets()` on
  every call, so every later theme switch pays for all of them. `gc.collect()` is not
  the fix: it freed 8 337 objects and moved the widget count only 38 271 → 37 638, so the
  survivors are not reachable as collectable cycles. **What holds them is NOT identified** —
  the referrer probe walked into PyQt6/sip bookkeeping and stopped — so "strong references"
  is the reading consistent with that measurement, not a proven mechanism, and the chokepoint
  below does not need it to be true.
  Fixed by one autouse fixture in `tests/conftest.py` that closes and `deleteLater()`s
  every top-level widget per test — 38 271 → 0, and the serial suite 912.6 s → 673.6 s
  with no product change and no test removed. Three details decide whether it works:
  the fixture's **position in the root conftest** is what finalises it last, after
  `tests/integration/conftest.py` has walked the windows it uses to stop servers - which is
  why deleting them earlier would silence the leak warning. The `qtbot` request is a separate
  ordering: it puts the reclaim ahead of qtbot's own teardown. Measured both ways with
  `--setup-show`; an earlier version of this entry credited the request with the first, which
  holds with the request removed; `sendPostedEvents` must name `QEvent.Type.DeferredDelete`
  explicitly, because `sendPostedEvents(None, 0)` — the shape that looks right — flushes
  nothing, and measuring that wrong call is how the first attempt appeared to prove the
  chokepoint ineffective; and a chokepoint beats the 51 per-file edits because it cannot be
  forgotten. **Lesson: the expensive tests in a suite are frequently the victims of other
  tests, not the culprits, and a per-test duration table says which tests are slow, not
  which files are.** Re-running a slow file on its own is the cheapest diagnostic there
  is — it took four wrong hypotheses to find the cause, and the first one cost an hour
  because the instrument (a benchmark of synthetic `QLabel` widgets) never requested an
  icon and so could not see the icon cache it was testing.

## Archive L3432: Line history can restore the preset name while losing the pen (#524–#526, #471)

### Line history can restore the preset name while losing the pen (#524–#526, #471)

**Symptoms:** preset undo retained gravel's 8 cm stroke instead of the previous
5 cm brown stroke. A re-stroked gravel path changed to WALL through Properties
used gray 4 cm with square caps/bevel joins; the context menu used gravel's 8 cm.
Context-menu undo lost the user's 12 cm #102030 stroke. Styled metal tips and
acute paved-path/stone-wall tips also exceeded the canvas bounds.

**Evidence:** an in-memory tagged probe traced preset application during undo
through pply_pfs and _setup_styling. A fixed-image uncached oracle independently
found out-of-bounds pixels. The old issue's bounds numbers were not reused: current
Qt base bounds and the optional shadow already contribute additional margins.

**Cause/fix:** commands stored only a preset name or rebuilt styling from defaults;
the two UI surfaces reconstructed pens differently. Copied LineLook snapshots
now restore through one callback. Type changes intentionally clear the preset, per
owner decision. Canvas and ground admission share the conservative style reach,
and pen/preset setters announce the old geometry before changing it.

**Testing lessons:** expanded bounds made an existing negative numpy slice empty;
the comparison now clamps an independent paint-reach band to the image. Setting
the same Qt cache mode invalidates the cache; the harness must not do that while
measuring reuse. Rotated transforms may regenerate a device cache. A widget
explicitly destroyed by a test must not remain registered for qtbot to close again.
Pixel masks must subtract an empty-scene image: the dark outside-page background
is not line detail, and the cream page is not white. Dynamic cache cases now edit
width/preset after the first paint, undo/redo and move, including vacated pixels.

The standard Beauty Board omits the offscreen renderer's optional ground baker,
so a board without errors can still omit a flat path. This package's validation
supplies production GroundBaker through the supported ground_baker parameter
and records actual tile counts/failures before comparing ground-aware frames.

**Rule:** undo restores captured values, not defaults; validate bounds against an
independent render, and measure the actual cache path. Pinned by
	ests/integration/test_line_appearance_history.py and
	ests/integration/test_styled_line_bounds.py.

### Frozen reference portability observed during line-package validation

Clean master and the branch each failed the same six day-ramp exposure assertions on Windows Python 3.11.9: a one-binary64-ULP difference from the historical JSON. The reference test now permits exactly one ULP for nonlinear exposure only; colors, brightness, fog and linear probe exposure remain exact. All 262 lighting tests then pass. Production lighting and the frozen reference data are unchanged.
