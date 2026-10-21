# Pitfalls: domain data, solver and dates

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-DOM-01

- **Rule:** No free solver variables does not imply feasibility, so the Newton solver evaluates the pinned-state residual before returning and a convergence flag agrees with measured geometry.
- **Pinned by:** `tests/unit/test_constraint_solver_invariants.py`; `tests/integration/test_constraint_presentation_workflow.py::test_fixed_items_make_incompatible_trial_infeasible`
- **Source:** #457
- **Status:** pointer → [§8: A5 numerical and presentation evidence (#457)](../../08-crosscutting-concepts/README.md#a5-numerical-and-presentation-evidence-457)
- **Legacy:** b1faaa9 README L128

Held in [§8: A5 numerical and presentation evidence (#457)](../../08-crosscutting-concepts/README.md#a5-numerical-and-presentation-evidence-457). The entry keeps the rule and its pin; the account is in the link.

### PF-DOM-02

- **Rule:** A constraint graph row can hide a no-op geometry path, so Edge Length resizes through canonical `geometry_apply` in one undo step, refuses atomically on conflict or pinned-item movement, and tests assert the real relation.
- **Pinned by:** none — The body names no test and defers its failing regressions to the debug-verbose case study.
- **Source:** #406
- **Status:** standing
- **Legacy:** b1faaa9 README L153

- **A graph row can conceal a no-op geometry path (#406, 2026-10-12).** A real Edge Length
  gesture on a rectangle added the requested 250 cm constraint but left its 200 cm edge intact.
  Verbose caller tracing showed the rigid-item fallback returning no moves for the same pinned
  item. Reuse EQUAL's rectangle size applier through canonical geometry_apply in the existing
  AddConstraintCommand; all four edges at 0/45/215 degrees now resize with one undo step,
  stable scene center/pivot and exact undo/redo. Assert the actual relation after creation,
  not only graph fields. Mixed-graph review then found feasibility was checking the original
  rigid size and the callback displaced FIXED item.pos. Probe proposed canonical geometry
  before feasibility, restore snapshots on refusal/error, and refuse a resize that moves a
  fixed pin. Tests preserve compatible center alignment and atomically refuse conflicting
  edge lengths/fixed-pin movement at all three rotations. Further review pinned EQUAL chains,
  timer-driven serialization inside refusal modals and destructive Override: restore the
  synchronous proposal before every modal, refuse changed shared dimensions and check
  conflicts without offering graph deletion. Unrelated EQUAL dimensions remain supported.
  The debug-verbose mirrors record
  the failing regressions and traces.

### PF-DOM-03

- **Rule:** `search()` and `get_by_id()` return different field sets, so a confirmed search selection fetches the detail record once and merges it field by field, a default or `None` detail field keeping the search value.
- **Pinned by:** `tests/integration/test_plant_search_enrichment.py::TestSearchResultEnrichment`; `tests/unit/test_plant_search_dialog_merge.py::TestGenericFieldMerge`
- **Source:** #297
- **Status:** standing
- **Legacy:** b1faaa9 README L207

**`search()` and `get_by_id()` returned structurally different field sets for the same provider, and nothing wired the richer one into the selection flow (issue #297).** Trefle's `/plants/search` carries only identity/taxonomy fields; `growth`/`specifications`/`foliage` (and therefore sun/water/pH/nutrient/foliage) only exist on `/plants/{id}`'s detail response. `PlantAPIManager.get_by_id()` already existed, fully implemented per provider, but nothing called it — `PlantSearchDialog` assigned the raw sparse `search()` result straight through. **Fix**: `PlantSearchDialog._enrich_selected_plant()` fetches the detail record once, on confirm (not per browsed row, to bound the cost against rate-limited free tiers), and merges it onto the search result via a generic loop over every `PlantSpeciesData` dataclass field (`_merge_detail_into_search_result()`): a field at its dataclass default — or `None`, regardless of the field's own default type — in the detail response defers to the search result's value; everything else takes the detail response's value; `source_id`/`data_source`/`raw_data` always come from the detail response. A provider signaling "no richer detail exists" (`PlantDetailUnavailableError` — Perenual's free-tier paywall, HTTP 429 with a healthy rate-limit budget remaining, not exhaustion; or a Trefle record with a null `main_species`, ~4% of a live sample) falls back quietly; a genuine failure (any exception, or a `source_id` mismatch) shows a translated warning first, so a real error can't silently reproduce #297's own symptom.

### PF-DOM-04

- **Rule:** Validate a plant-API detail record by `source_id` alone, merge it field by field treating a present `None` as empty, and stop any pending debounce timer before a commit path opens a modal.
- **Pinned by:** none — The body names no test for its identity, merge and debounce rules.
- **Source:** #210, #296
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l209-this-shipped-over-seven-senior-review-rounds-each-finding-a-real-live-reproducible-defect-in-the-previous-rounds-own-fix)
- **Legacy:** b1faaa9 README L209

### PF-DOM-05

- **Rule:** Before asserting a plant API's response shape, id space, error-code meaning or sweep completeness, settle it with a live call using the working `.env` credentials.
- **Pinned by:** none — the pins its body names test the merge rule of PF-DOM-03, not this live-call process rule, so none is given.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L216

**Takeaway**: this project's `.env` has working credentials for Trefle, Perenual, and Permapeople. A live call costs thirty seconds and settles what code-reading and argument cannot — use one before asserting a response shape, an id space, an error code's meaning, or a sweep's completeness. Pinned by `tests/integration/test_plant_search_enrichment.py`, `tests/unit/test_trefle_client.py` (`TestGetByIdSourceIdContract`, `TestMainSpeciesNullSafety`), and `tests/unit/test_plant_search_dialog_merge.py`.

### PF-DOM-06

- **Rule:** Every plant search-result row shows its data source through the shared `plant_source_label()`, because a stale custom-library record on a real machine can mimic a live result that mocked tests never see.
- **Pinned by:** none — The body names no test; `tests/integration/test_plant_search_enrichment.py::TestResultListSourceLabel` covers the label but is not named here.
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l218-update-manual-testing-2026-08-10-a-defect-one-layer-above-the-seven-round-fix-invisible-to-every-review-round-the)
- **Legacy:** b1faaa9 README L218

### PF-DOM-07

- **Rule:** Write every external-API JSON lookup as `(data.get(key) or default)`, since `dict.get(key, default)` returns `None` for a present JSON null, whose chained method call raises and silently drops the record.
- **Pinned by:** `tests/unit/test_perenual_client.py::TestParseSpeciesNullSafety`; `tests/unit/test_permapeople_client.py::TestParseSpeciesNullSafety`
- **Source:** #296
- **Status:** standing
- **Legacy:** b1faaa9 README L226

**`dict.get(key, default)` is not None-safe, and it silently dropped API search results (issue #296).** A live audit of all three plant-lookup APIs (Trefle, Perenual, Permapeople) against a 10-plant dataset (trees/shrubs/flowers/vegetables), using real `.env` credentials, found two independent parsers crashing on the same anti-pattern: `data.get("cycle", "").lower()` (Perenual) and `data_dict.get("light requirement", "").lower()` (Permapeople). **`default` in `dict.get(key, default)` only applies when `key` is absent — not when it's present with a JSON `null`**, which is common in both APIs' public datasets for sparse records. A present-but-null value returns `None`, and the chained `.lower()` raises `AttributeError`. The exception is caught by a bare `except Exception` in each client's `search()` loop, so the record is silently dropped — no error reaches the user, only a `logger.warning` nobody reads. Live evidence: 16 silent parse failures logged across 8 of 10 Perenual test plants; reproduced offline (no live calls needed) by feeding `_parse_species({"cycle": None, ...})` directly. **Fix**: rewrite every such lookup as `(data.get(key) or default)` so a present-null value falls through to the default exactly like an absent key. Same audit also found: Perenual's free tier returns the literal string `"Upgrade Plans To Premium/Supreme - ..."` for premium-gated fields (`cycle`/`watering`/`sunlight`) instead of real data or `null` — harmless once the null-guard is in place (the string just fails to match real keywords and stays `UNKNOWN`), but `sunlight` also needed an `isinstance(..., list)` guard, since `" ".join(a_string)` iterates it character-by-character instead of raising. **Lesson**: any parser doing `data.get(key, default).method()` on an external API's JSON is one present-null field away from silently losing the whole record — the fix is a one-line idiom change, but it has to be applied at every call site, not just the one a bug report happened to name. Pinned by `tests/unit/test_perenual_client.py` and the new `TestParseSpeciesNullSafety` classes in `tests/unit/test_permapeople_client.py`; a positive control (`git stash` the fix, re-run) reproduced the exact pre-fix `AttributeError` on 18 of the new/extended tests before the fix was restored.

### PF-DOM-08

- **Rule:** Verify each plant-API field mapping against a live or captured real response rather than a hand-written fixture that encodes the parser's assumption, and map a single-number Soil pH to no range.
- **Pinned by:** none — The body names no test; `tests/unit/test_permapeople_client.py::TestParseSpeciesFieldMapping` covers the pH mapping but is not named here.
- **Source:** #213, #218, #296, #297
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l228-available-api-fields-silently-discarded-independent-of-the-crash-above-issue-296)
- **Legacy:** b1faaa9 README L228

### PF-DOM-09

- **Rule:** Task status has one write path, `set_task_status`, with `task_completions` kept only as a write-only serialized mirror, and every reader derives `task_id` via `make_calendar_task_id()` and `species_key()`.
- **Pinned by:** `tests/integration/test_tasks.py::test_calendar_done_toggle_syncs_task_states`; `tests/integration/test_calendar_task_convergence.py`
- **Source:** #188, #227, #228
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l246-closed-228-task-status-now-has-a-single-write-path)
- **Legacy:** b1faaa9 README L246

### PF-DOM-10

- **Rule:** Assign a species through `PlantDatabasePanel._apply_species_to_item()` and its undoable `ApplySpeciesCommand`, since a raw `metadata["plant_species"]` write never repaints, but keep per-keystroke edits out of that command.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #210, #213
- **Status:** standing
- **Legacy:** b1faaa9 README L252

- **Writing `metadata["plant_species"]` does not repaint the canvas, and a manual `spacing_radius_cm` override masks the database value** (issue #213): the spacing circle's radius comes from `effective_spacing_radius()`, which returns the user override *first* and only falls back to `max_spread_cm/2` from `metadata["plant_species"]`. So a direct `item.metadata["plant_species"] = …` (as several `plant_database_panel` paths did) updates the data model but (a) never triggers `prepareGeometryChange()`/`update()`, so the spacing circle keeps its old size on screen, and (b) is silently overridden on screen by any manual spacing the user set earlier. Contract: route species *assignment* through `PlantDatabasePanel._apply_species_to_item()`, which builds a single undoable `ApplySpeciesCommand` (sets metadata **and**, on *Apply database values*, resizes the drawn footprint to `max_spread_cm` via `CircleItem.set_radius_centered()`, then repaints). The footprint resize is **silent**; the only thing that prompts is a manual `spacing_radius_cm` override that *conflicts* with the database value (Apply → resize + clear override; Keep → leave both). Do **not** wrap live per-keystroke field edits (`_on_field_changed`) in that command — that recreates the per-keystroke undo-churn fixed in #210; there, write metadata directly and just call `prepareGeometryChange()`/`update()` for the repaint.

### PF-DOM-11

- **Rule:** `_compute_constraint_solve_moves()` adds `anchor_c.item_id` to `constrained_ids` for three-anchor constraints such as ANGLE, or the solver cannot move the third item and it stays violated.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L276

- **3-anchor constraints not solved on add**: `_compute_constraint_solve_moves()` in `canvas_view.py` collects `constrained_ids` from `anchor_a` and `anchor_b` only. Any constraint with a third anchor (`anchor_c`, e.g. ANGLE) must also add `anchor_c.item_id` here, otherwise the third item is absent from `item_positions` and the solver cannot move it — showing as red/violated until the user manually drags an object.

### PF-DOM-12

- **Rule:** `ConstraintGraph.project_to_feasible()` keeps a sub-pixel default tolerance of `1e-4`, because a cm-scale tolerance makes `newton_refine()` return the cursor unchanged and the dragged vertex slips.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #169
- **Status:** standing
- **Legacy:** b1faaa9 README L278

- **Live-drag projection tolerance must be sub-pixel** (PR #169 follow-up): `ConstraintGraph.project_to_feasible()` calls `newton_refine()` with a `tol` parameter that gates an early-return *before* projection: `if max_err <= tol: return`. The starting state has `vertex_pos[moving] = desired_scene_pos` (the cursor). At cm-scale `tol` (e.g. 0.5 cm), the cursor near a feasible point falls inside the slack band on most frames of a near-stationary drag, so the function returns the cursor **unchanged** — the moving vertex slips with the cursor up to that band each frame. On a fully-constrained chain (EDGE_LENGTH on every adjacent pair), the slip looks like the entire polyline rigidly translating because the user can only see the moving vertex's position in scene coords. Fix: `project_to_feasible` defaults to `tolerance=1e-4` (sub-render-precision); `solve_anchored` and other full-graph callers retain their cm-scale tolerances. Defensive companion: `newton_refine` now also calls `write_x(x)` on the early-return path so callers always observe a consistent state.

### PF-DOM-13

- **Rule:** `ShoppingListItem.id` encodes the locale-stable display unit, as in `amendment:<aid>:g` or `amendment:<aid>:kg`, so a price keyed by id never re-binds after a g-to-kg promotion.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L324

- **`ShoppingListItem.id` must encode the display unit when units auto-promote**: `ShoppingListService._collect_materials` promotes amendment quantities from g to kg once the cross-bed total crosses 1000 g. Because user-entered prices in `ProjectData.shopping_list_prices` are keyed by `id`, the id must capture the unit (`amendment:<aid>:g` vs `amendment:<aid>:kg`) — otherwise a price entered when the row was 800 g silently re-binds to the same row when it later weighs 1.2 kg, multiplying the apparent total by 1000×. Use the locale-stable suffix (`g`, `kg`) — never the translated `_tr()` string — so the id is identical across English/German runs.

### PF-DOM-14

- **Rule:** Surfaces that share the task status store build the whole task id through the shared `make_calendar_task_id()` and canonical `species_key()`, and sync tests derive ids the way production does.
- **Pinned by:** `tests/integration/test_tasks.py::TestCrossSurfaceSync`
- **Source:** #12, #227
- **Status:** standing
- **Legacy:** b1faaa9 README L371

- **Two surfaces that share a status store must derive the key identically — reuse the canonical `species_key()`** (US-C2, PR #227 #12): the Planting-Calendar dashboard and the Tasks tab both persist per-task done/snooze state in `task_states`, keyed by `task_id = "{species_key}:{task_type}:{year}"` for calendar-derived tasks. They computed `species_key` *differently*: the calendar used the canonical `species_key()` helper ([`models/plant_data.py`](../../../src/open_garden_planner/models/plant_data.py), ADR-016 — `source_id → scientific_name → common_name`, **lowercased**), while `tasks_view.build_plan_state` used a raw `sp.scientific_name or sp.common_name or item.name` (no `source_id`, not lowercased). For any DB-sourced species (carries a `source_id`) or any casing difference the two ids diverged (`12345:harvest:2026` vs `Solanum Lycopersicum:harvest:2026`), so marking a task done on one surface was invisible to the other — sync failed in **both** directions. The round-2 PR test masked it by asserting the data layer with hand-matched ids. Fix: `build_plan_state` now calls the same `species_key()` helper, **and** the id *format* is built through a single shared `make_calendar_task_id()` (in `services/task_generator.py`) used by both the generator and the calendar dashboard — so neither the key nor the format can drift again. Lesson: when two views read/write a shared id-keyed store, the *entire* id derivation (key + format) must be a single shared function, and a sync test must build the id the way *production* does (from a realistic species with a `source_id`), not hand-write a matching string. Regression test: `tests/integration/test_tasks.py::TestCrossSurfaceSync`.

### PF-DOM-15

- **Rule:** A handler fed a canonical `species_key` compares `species_key()` on both sides, selects a `target:<uuid>` key by item id, and never shows that grouping key as a user-facing name.
- **Pinned by:** `tests/integration/test_harvest.py::TestHarvestNavigation`; `tests/integration/test_harvest.py::test_csv_unnamed_target_shows_label_not_blank`
- **Source:** #235
- **Status:** standing
- **Legacy:** b1faaa9 README L373

- **A handler fed a canonical `species_key` must match on the canonical key, not a raw name — and a "navigate by species" channel must also handle unkeyed targets** (US-C1, PR #235 manual test): the Harvest dashboard double-click routes through the shared `GardenPlannerApp._on_highlight_species`, also wired to the planting-calendar `highlight_species` and the Tasks tab `navigate_to_species` — **all three emit a canonical `species_key()`** (ADR-016, lowercased `source_id → scientific → common`). The handler compared that key against each item's **raw-cased** `scientific_name or common_name`, so it never matched for any capitalised name or any DB species carrying a `source_id` → nothing got selected (latent on all three surfaces; surfaced by harvest). Fix: compare `species_key(item.metadata["plant_species"])` on both sides + `centerOn` the first match. Second half of the same bug: a harvest on a **bed or species-less plant** aggregates under a `target:<uuid>` grouping key (it has no species), and the view had deliberately blanked those so they navigated *nowhere*. `_on_highlight_species` now also handles a `target:<uuid>` key by selecting that one item by id (via `_select_items_by_id`), and the view stashes the full grouping key. The same unkeyed target also caused the dashboard/CSV/PDF to show the raw `target:<uuid>` as a *name*: fixed by caching the item's localized object-type name at log time (`_harvest_species_for_target`) and substituting a localized "Unnamed" at every display surface (table + CSV + PDF — all three, or they drift). Lessons: **(1)** a signal documented as carrying a `species_key` must be *consumed* with the same canonical derivation it was produced with — never re-derive from a display name; **(2)** a "select by species" channel needs an explicit branch for targets that have no species (beds), or they become silently unclickable; **(3)** an internal grouping key (`target:<uuid>`) must never leak into a user-facing name column. Regression tests: `tests/integration/test_harvest.py::TestHarvestNavigation` (plant-by-species + bed-by-id + type-name fallback), `::TestAggregationAndExport::test_csv_unnamed_target_shows_label_not_blank`.

### PF-DOM-16

- **Rule:** Every writer of a HOUSE polygon recomputes its roof ridge through `compute_roof_ridge_endpoints` in the polygon's local frame, never re-projecting the ridge from its own current endpoints.
- **Pinned by:** `tests/unit/test_roof_ridge.py`
- **Source:** #114, #364
- **Status:** standing
- **Legacy:** b1faaa9 README L466

**A derived child must be recomputed from its owner, never re-projected from its own current state** (issue #364, 2026-09-29). Symptom: a HOUSE's auto-created roof ridge drifted off its polygon and never recovered — after `add_vertex` the second endpoint stuck to a new slanted edge, and **undo restored the polygon exactly while leaving the ridge 36 cm away** on a 300×200 cm house, accumulating over repeated cycles. The house looked perfect, so the defect was invisible unless you measured the ridge endpoints. The first hypotheses were wrong in the same direction: it was not the vertex command, the constraint solver, or the D2.6 work that introduced it (`git log -S` put `_update_ridge_on_boundary` in `818e3fb`, #114, two years earlier — D2.6 only added a *call site*). The real cause was that the sync was a **membrane, not a recompute**: it re-projected the ridge's *existing* endpoints onto the boundary, so a once-perturbed endpoint had no path back to canonical, and the direct `ridge._points` write bypassed the command system so no undo step could restore it. Measuring the same code against a *rotated* house then exposed a second, larger defect nobody had reported: the membrane kept the ridge's old orientation, so a house rotated 30°/90° kept a ridge at 0° — **75 cm / 180 cm** off, and since `_paint_with_ridge` mirrors the roof texture along that line, **every rotated house rendered a wrongly-oriented roof**. The fix recomputes through the one canonical `compute_roof_ridge_endpoints`, computed in the polygon's **local** frame and mapped through the item's full transform. The local-frame detail is load-bearing and contradicts the obvious reading: the issue's own suggested fix ("call it with `pos`") returns a 0° ridge for a 30° house, because that formula adds `pos` to local points and ignores the transform — it is only correct for an unrotated item, so following the issue verbatim would have fixed the filed symptom and left rotation broken. Pinned by `tests/unit/test_roof_ridge.py`, parametrised over four transforms — unrotated, 30°, 90°, and 45°/scale 1.5. The module collects 26 cases; measured against master's `polygon_item.py` and `canvas_view.py`, **21 fail and 5 pass** — the 5 being the four boundary-invariant cases (the old projection satisfies those by construction) plus the unrotated rotation-tracking case, whose orientation defect is zero at rotation 0. That is 15 of the 20 `TestRidgeDriftOnUndo` cases, plus all of `TestResizeUndo` and `TestHandMovedRidgeEndpoint`. The `TestResizeUndo` cases fail at **300 cm** when the single sync line is removed from the fixed tree — they import the function the fix introduces, so on master they stop at an `ImportError` rather than observing the drift. The two defects differ: the **drift** reproduces at *every* transform including unrotated — which is how #364 was filed — while only the **orientation** defect is zero at rotation 0. A second pass found the first fix was **incomplete**: the `ResizeItemCommand` apply closure (a *fifth* polygon-apply path, not one of the four the sync is called from) never re-derived the ridge, so undoing a HOUSE resize left the ridge sized for the resized house — 300 cm of drift, persisted into the `.ogp` because the ridge is itself a serialized item. No test anywhere resized a HOUSE, so 6509 green tests missed it, and senior review caught it. A third round found a **sixth** writer: the constraint solver's `finally`, which restored a polygon with a bare `setPolygon` while its polyline sibling restored through the override that does re-derive — asymmetric in the same file, 150 lines from the one already fixed. Both were found by review, not by tests (ADR-046). Lesson: when one object is derived from another, ask whether the sync *recomputes* or *adjusts* — an adjustment is a second source of truth that no undo can own — and then confirm that **every** writer of the owner's state re-derives it, because fixing the paths you can see leaves the ones you cannot; and when a geometry helper takes a position argument, check whether it is correct under rotation before reusing it, because "works at the default value" is the signature of the same class of bug.

### PF-DOM-17

- **Rule:** Assign roof-texture halves by the physical down-slope direction, never by `_split_path_by_line`'s left and right naming, which follows the ridge direction rather than gravity.
- **Pinned by:** none — The body names no test; `tests/unit/test_roof_tile_orientation.py` covers the lap direction but is not named here.
- **Source:** #364, #372
- **Status:** standing
- **Legacy:** b1faaa9 README L469

**A derived texture's orientation is gravity-relative, and naming a half "left" does not make it the downhill side** (issue #372, 2026-09-30). Symptom: a HOUSE's roof tiles lapped back **up toward the ridge** on both halves - they read the same outward sequence, being mirror images of each other, so the inversion could not show on one side only - so water would run uphill under the laps, reported by the owner as "regardless of whether I paint a vertical or horizontal house, it is always the wrong direction", a phrasing that is the whole diagnosis. The two first theories were both wrong in an instructive way: the *rotation* was not broken (the transform was computed and applied correctly, provable in isolation), and the *texture* was not upside-down (its `+Y` is genuinely down-slope: a dark lapse line near `y=10` with the light free edge beneath). The halves were assigned by `_split_path_by_line`'s `left`/`right` naming, which follows the left-perpendicular `n = (-uy, ux)` and therefore the ridge's **direction** - for a +X ridge `left_path` is the LOWER half, for a +Y ridge it is the LEFT half. The half that needed the texture's true down-slope was the one being handed the mirror, so the error tracked ridge direction rather than gravity and appeared at every angle. Measured through the production paint path, the two builds differ in **absolute phase** while staying mirror-symmetric: fixed `RBBRBB`, pre-fix `BRRBRR` on both halves. Third lesson, and the one that nearly cost the fix itself: **check that your measuring instrument reaches the code under test.** A test harness called `scene.removeItem(ridge)` to stop the ridge's stroke covering its sample points - which made `_find_ridge()` return `None`, which means `_paint_with_ridge` is never called at all. Every render then measured `super().paint()`, the fallback fill that both builds share, and the fix hashed byte-identical. A "no-op" measured by an instrument that bypasses the code is not evidence of a no-op; when the reviewer reported that the test did not call production code, the correct response was to re-measure the *fix* with a corrected instrument, not to conclude from the broken one. Hide the obstacle with `setVisible(False)` - **not** by clearing its pen, which does nothing here because `_paint_roof_ridge` strokes three *hardcoded* pens and never reads `self.pen()` - and never remove the thing whose presence gates the code path. The same class of bug appeared twice more in the same file: the ridge points were run through `house.mapToScene` although they are already scene space (since #364), so the harness sampled 30 degrees off the real ridge normal at 30 degrees of rotation and invented a "degenerate" band at 90/270 that does not exist. **A fourth trap was a test that looked thorough and pinned nothing:** it swept the house's *rotation* across nine angles and called that angle coverage, but the angle `_paint_with_ridge` feeds to `normal_tx.rotate()` is the ridge direction in the polygon's **local** frame, which `compute_roof_ridge_endpoints` pins to the longest bounding-box axis - 0 for a landscape house at *every* rotation, 90 for a portrait one at every rotation (measured by spying on the value). Since `rotate(-a)` and `rotate(+a)` are the same transform when `a` is 0, a rotation-only sweep is structurally blind to a negated sign, which is the very term the swap argument rests on. Adding a portrait house caught it immediately: negated, the landscape cases still read `RBBRBB` and all four portrait cases read `BRRBRR`. **When a test sweeps a transformation, check which quantity the code under test actually consumes** - an item transform, a local-frame angle and a scene-frame angle are three different things, and only one of them is what a rotation sweep moves. The fix is a swap, not a probe, because of an exact identity: `normal_tx` is `translate . rotate(angle)` and a `QBrush` samples the texture at `T^-1.p`, so texture `+Y` lands at `R(angle).(0,1) = (-sin a, cos a)` - precisely `n`. **Lesson: a geometric naming convention is not a physical one.** Whenever a half, a side, or a region is named by geometry (left/right, near/far, first/second), check that the name survives rotation before branching on it. Second lesson, about the measurement itself: correlating the real 256 px tile texture against the render had **no discriminating power** - peak correlation ~0.03 either way, with the diagonal case a 0.020-vs-0.019 coin flip - because a few hundred sampled pixels span barely one texture period, and a metric that cannot separate right from wrong will happily pass broken code. The fix came from replacing the texture with a **two-colour probe** (red on top, blue on bottom, so blue *is* the down-slope) and sampling a six-point sequence outward from the ridge. When a rendering assertion will not separate, change what it measures rather than loosening the threshold. And note what it took to see this at all: a green 6515-test suite, because nothing in `tests/` had ever looked at a rendered roof pixel.

### PF-DOM-18

- **Rule:** `species_key()` is a module-level function over a species dict, not a record field, so `getattr(record, "species_key", "")` yields an empty key; a bundled plant's key is its scientific name.
- **Pinned by:** none — The body names no test; it mentions nine failing unit tests without naming any.
- **Source:** none recorded
- **Status:** standing
- **Legacy:** b1faaa9 README L509

**Corollary - `species_key` is a function, not a field.** The first draft of `suggest_succession`
read `getattr(record, "species_key", "")` off each candidate and got `""` for all 118 bundled
species, so every call returned an empty list - a result that reads as "no candidates", the exact
silence this project forbids. `species_key(species_dict)` (`models/plant_data.py`, ADR-016) is a
module-level function whose priority is `source_id -> scientific_name -> common_name`, so a
bundled plant's key is its **scientific** name: `"phaseolus vulgaris"`, not `"beans"`. Nine unit
tests failed identically, which is what identified the shared root cause instead of nine separate
bugs. **When many tests fail the same way, find the shared assumption before fixing any of them.**

### PF-DOM-19

- **Rule:** The Tasks tab and dashboard list reminder tasks through `generate_actionable_for_surface` while the Gantt consumes `generate_for_date_window`, so neither the GUI nor the agent hides a task the other shows.
- **Pinned by:** `tests/unit/test_task_windows_multi_anchor.py`
- **Source:** #414
- **Status:** pointer → [ADR: Addendum (#414 — one frost anchor per surface, and one date-window entry point)](../../09-architecture-decisions/README.md#addendum-414--one-frost-anchor-per-surface-and-one-date-window-entry-point)
- **Legacy:** b1faaa9 README L1078

Held in [ADR: Addendum (#414 — one frost anchor per surface, and one date-window entry point)](../../09-architecture-decisions/README.md#addendum-414--one-frost-anchor-per-surface-and-one-date-window-entry-point). The entry keeps the rule and its pin; the account is in the link.

### PF-DOM-20

- **Rule:** Establish which reading the code implements before editing data that contradicts its documentation; harvest offsets count from the last spring frost, and divergent rows stay named in `KNOWN_DIVERGENT_SPECIES`.
- **Pinned by:** `tests/unit/test_harvest_offset_semantics.py::test_divergent_species_set_is_stable`; `tests/unit/test_harvest_offset_semantics.py::test_maturity_fields_are_reference_data_not_used_for_scheduling`
- **Source:** #311, #418
- **Status:** standing
- **Legacy:** b1faaa9 README L1082

- **The "weeks after planting" comment in the bundled plant data was wrong — and the first measurement of how wrong was itself wrong.** Symptom: `models/plant_data.py` documented `harvest_start` as *weeks after planting* while all five readers counted it from the plan's last spring frost, and a garlic plan with a 9 April frost showed a harvest landing in the same April as the frost — roughly 52 weeks after its own October sowing. Wrong theory: that correcting the data rows is a mechanical conversion. Measured over all 118 bundled species (64 with both harvest offsets and a maturity range): "offset × 7 inside `days_to_maturity`" fits **37 of 64**; "(offset − planting_offset) × 7 inside maturity ±15 %" fits **46 of 64**; on the harvest *start*, the planting-relative span lands in 1.0–1.5× the stated maturity for **29 of 64** species against the maturity midpoint (45 %), 33 of 64 against `days_to_maturity_min` (52 %) and 15 of 64 against the maximum (23 %) — so "most species" holds under no denominator except a bare 50/50 split on the minimum. Measured by `scripts/measure_harvest_offsets.py`, which prints all three counts, and garlic's 182-day reading does fit while its *window* still lands in October - about three months after a real garlic harvest. Both readings fit a majority (37/64 frost-relative, 46/64 planting-relative), so the data is **not** irreconcilable and "convert the rows that follow the other reading" has no well-defined target set. What does follow from the measurement is the opposite conclusion to the one this entry originally drew: the rows were probably **authored** as planting-relative, which is the finding #418 has to resolve. Fix: the shipped half makes the documentation true and pins the divergence (`KNOWN_DIVERGENT_SPECIES`); the row conversion is deferred to #418 because it needs a cited horticultural source per row and licence clearance under the #311 provenance rules. The measurement that made the split defensible: `days_to_maturity` is **reference data that no computation reads** (asserted by a test), so correcting rows cannot move a computed date. *When data contradicts its own documentation, establish which reading the code implements before editing the data; and when two fields in the same record cannot be reconciled, say so and name the exceptions instead of picking a winner and moving 60 rows' worth of dates in one release.*

### PF-DOM-21

- **Rule:** A wrapper over `generate_for_date_window` passes `actionable_only=False` inward and filters urgency once at the edge, because the flag is re-applied inside every anchor year.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #326
- **Status:** standing
- **Legacy:** b1faaa9 README L1084

- **A shared generator's flags are inherited per iteration, so a wrapper can filter before the wrapper's own filter runs.** Symptom: routing the Tasks tab through the shared multi-anchor path produced an **empty** task list and the Gantt produced **no bars at all**, while the unit tests of the same helper passed. Root cause: `generate_for_date_window` builds each anchor year with `replace(state, ...)`, so `actionable_only=True` (the GUI default) is re-applied inside every anchor — dropping anchors whose windows are not currently urgent *before* the outer `classify_urgency` filter saw them. Fix: both call sites pass `actionable_only=False` into the inner pass and keep exactly one urgency filter, which is the one they document. This is the same shape as the #326 "`Callable` injection with N call sites" lesson: a flag that is silently defaulted somewhere in the middle of a chain is not a flag, it is an accident waiting for a caller. *A default inside a loop over derived inputs is a filter nobody wrote; when a wrapper delegates, pass the permissive value inward and filter once at the edge.*

### PF-DOM-22

- **Rule:** Store the user's chosen local calendar day and derive the UTC instant from it, never the reverse, so UI writers hand `SimClock` a naive wall reading rather than an instant.
- **Pinned by:** `tests/unit/test_sim_clock.py::TestTimeChangeNeverFiresDateChanged`; `tests/integration/test_sim_clock_wiring.py::TestOnePlanDateEastOfUtc`; `tests/integration/test_sim_clock_wiring.py::TestToolbarPathPreMidnightGap`
- **Source:** #385
- **Status:** standing; narrative in [archive/02-l1-0-clock.md](../archive/02-l1-0-clock.md#1147-a-day-derived-from-a-utc-instant-is-not-the-users-day-phase-17-l10-385)
- **Legacy:** b1faaa9 README L1087 (legacy 11.4.7)

### PF-DOM-23

- **Rule:** Guild placement deep-copies copied metadata, couples UUID resolution to document lifetime, and takes plant geometry from `guild_plant_bounds()`, since a semantic plant may be a rectangle, polygon or path.
- **Pinned by:** none — The body describes its regression tests without naming any test file or test.
- **Source:** #433
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1095-guild-boundaries-found-by-independent-review-f1f2)
- **Legacy:** b1faaa9 README L1095 (legacy 11.4.8)

### PF-DOM-24

- **Rule:** A plant's ground sun estimate excludes only its own caster, and `document_replaced` cancels and clears heatmap work so generation guards reject any late worker result.
- **Pinned by:** none — The body describes its regressions without naming any test file or test.
- **Source:** #314, #428
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l1109-sun-self-shadow-and-late-document-results-314-428)
- **Legacy:** b1faaa9 README L1109 (legacy 11.4.6)


### PF-DOM-25

- **Rule:** Project plant presence and rendered growth from the one plan date, preserving stored lifetime metadata and undo semantics.
- **Pinned by:** `tests/integration/test_plan_timeline.py`; `tests/unit/test_plan_timeline.py`
- **Source:** #315, PR #533, ADR-062
- **Status:** standing; narrative in [archive/14-plan-timeline.md](../archive/14-plan-timeline.md)
- **Legacy:** none (new entry)

A collector-only growth fix left the sprite unchanged. Date visibility, cached paint invalidation, instance metadata and task windows share the documented timeline contract; the workflow tests assert rendered output, persistence and history. See section 8.31 and ADR-062 for the current lifecycle contract.
