# 11. Risks and Technical Debt

Dated audit snapshots: [audit-2026-10.md](audit-2026-10.md) (numbers: `audit-2026-10-metrics.json`, re-run with `scripts/audit_metrics.py`; findings tracked in epic #392). §11.3 is the living register (ADR-047).

## 11.1 Open Questions

| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Trefle.io rate limits and reliability? | Plant search UX | Test API, implement robust caching, Permapeople as fallback, bundled DB as last resort. **Status 2026-10:** open; the SQLite cache (TD-003) and the bundled-DB fallback (`services/plant_api/manager.py` TODO) are not implemented. |
| ~~Texture licensing for fill patterns?~~ **RESOLVED (ADR-042, 2026-08-18)** | Legal | All 24 fill textures are generated in-repo with provenance (§8.24). |
| ~~DXF export complexity for future versions?~~ **RESOLVED (US-12.3/12.4)** | Interoperability | DXF export and import shipped on ezdxf; scope is defined by FR-EXP-07 and FR-IMP-04 (Bezier export via ADR-022, Smart Symbol blocks via ADR-032). |
| ~~Qt6 3D capabilities vs dedicated engine?~~ **RESOLVED (US-E5, ADR-038, 2026-07-20)**: PyQt6-3D chosen — version-matched 6.11.0 wheel, frozen-exe gate passed (+13 MB), built-in orbit + first-person cameras; PyVista rejected on size (+466 MB), pyqtgraph.opengl on feature fit. Pin `PyQt6-3D-Qt6` to `PyQt6-Qt6`'s micro or imports fail | 3D feature (Phase 14) | Done — see ADR-038 evidence log |
| ~~Qt 3D is deprecated since Qt 6.8 — which renderer carries Phase 17's "Living Garden 3D"?~~ **RESOLVED (ADR-048, 2026-10-05)** | 3D look, shadows, upgrade path past the #277 pin pair | **GO** — Qt Quick 3D replaces Qt 3D for Phase 17 (the L0 spike passed the twelve pre-committed criteria, including on the owner's GPU); `QQuickView` host chosen; the D3D11 leak half is accepted open and closes in L1.3. Evidence in ADR-048 (entry 19 = owner run). |
| Bundled plant database source? | Offline functionality | Evaluate USDA Plants Database, consider one-time Trefle.io bulk export. **Partially resolved (ADR-014):** 118 bundled species ship with licence metadata (#311); a bulk-export source remains open. |
| ~~AI-generated SVG quality consistency?~~ **RESOLVED (ADR-040, ADR-042)** | Visual appeal | Procedural generators replaced AI-generated SVGs. |
| NSIS installer signing? | Trust/distribution | Unsigned initially, document for users. **Partially addressed (ADR-044, 2026-09-15):** build provenance attestation (`gh attestation verify`) proves the binary traces back to a public CI run of the public source — free, no cert needed. Releases remain unsigned. Signing options, including no-cost proposals, are under evaluation in [#375](https://github.com/cofade/open-garden-planner/issues/375); no option has been adopted, and effectiveness against these detections is unproven for this project. Reputation detections now observed from a second vendor: Norton 360 `FileRepMalware[Misc]` on the 1.27.9 installer (issue #358, 2026-09-22), same zero-reputation FP class as Defender in #356. Authenticode is tracked in #375. |

## 11.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyQt6 licensing complexity (GPL/Commercial) | Medium | High | Use GPLv3, document clearly, ensure compliance |
| Performance with very large images | Medium | Medium | Implement image tiling/downsampling at zoom levels. **Status 2026-10:** unmeasured; the audit's offscreen harness covers a 500-object plan, not large images (audit-2026-10 §5.7). |
| ~~Scope creep delaying v1.0~~ **Closed** | High | High | v1.0.0 shipped 2026-02-14; 159 releases in total by 2026-10-03. |
| Limited development time | High | Medium | Focus on quality over speed, attract contributors |
| Project not attracting contributors | Medium | High | Excellent documentation, clean code, contributor guide, CI/CD. **Status 2026-10:** no CONTRIBUTING.md exists; the contribution rules live in CLAUDE.md/AGENTS.md and are written for agents (audit-2026-10 §5.10). |
| External API deprecation | Low | Medium | Fallback chain: Trefle -> Permapeople -> Bundled DB. **Status 2026-10:** the bundled-DB step of the chain is not implemented (TD-003). |
| ~~AI-generated SVGs inconsistent quality~~ **Closed (ADR-040, ADR-042)** | Medium | Medium | Sprites and textures are generated, not drawn. |
| Windows installer blocked by SmartScreen | Medium | Low | Document workaround, investigate signing options. Build provenance attestation shipped (ADR-044) as a verifiable trust signal alongside the checksum; does not itself suppress SmartScreen/Defender (issue #356) or Norton `FileRepMalware[Misc]` (issue #358 — second AV vendor, same unsigned zero-reputation profile). Releases remain unsigned; signing options, including no-cost proposals, are under evaluation in [#375](https://github.com/cofade/open-garden-planner/issues/375). No option has been adopted, and no signed release has established effectiveness against these detections. FP path per vendor: Microsoft file-submission forms (#356), Norton portal `submissions.norton.com/reportfalsepositive` (#358; both portals are CAPTCHA-protected, so submissions are manual, not automatable by the maintainer). |
| Large bundle size from PyInstaller | Medium | Low | Optimize includes, strip unused Qt modules |

**Build-backend advisory, 2026-10-09; updated 2026-10-13 (A2 #454).** The first Dependabot
scan of uv.lock reported
[GHSA-h35f-9h28-mq5c](https://github.com/pypa/setuptools/security/advisories/GHSA-h35f-9h28-mq5c)
against setuptools 82.0.0 (also present in the frozen artifact): a moderate Unicode-normalization bypass of MANIFEST.in
exclusions when publishing macOS source distributions. GitHub identifies 83.0.0 as the first
patched version. Applicability assessment: current CI uses Linux/Windows editable installs
and publishes a Windows PyInstaller/NSIS installer; neither that build pipeline nor the app publishes macOS sdists. The waiver concerns the unused affected operation, not absence of setuptools from the executable.
[Dependabot alert 1](https://github.com/cofade/open-garden-planner/security/dependabot/1)
remains open for a separately reviewed backend/lock update. The CI `Dependencies` matrix job
(Linux and Windows) now runs `pip-audit` against the committed lock export
(`uv export --locked --all-extras --group build`) on every push, with this single advisory
recorded as `--ignore-vuln PYSEC-2026-3447`; a new advisory fails the job. Both platforms
run it because pip-audit evaluates markers for the running interpreter.

Automated dependency PRs remain unavailable: Dependabot's uv ecosystem image ships uv
**0.12.19** (`uv/Dockerfile` in dependabot-core, read 2026-10-13) while this project pins
`uv ==0.12.23`, and a `required-version` mismatch makes the updater exit before doing any
work. `.github/workflows/dependency-review.yml` is the documented monthly manual fallback:
it reports what `uv lock --upgrade` would change into one issue and never writes to the
repository. See ADR-050's A2 addendum and `docs/07-deployment-view` §7.4.

## 11.3 Technical Debt

The living register (ADR-047). Every row has a status; P0/P1 rows link their issue, P2/P3 rows link their thematic bundle issues; all 73 findings and current evidence are reconciled in [audit-2026-10-reconciliation.md](audit-2026-10-reconciliation.md) (epic #392). Rows come from the dated audit snapshots ([audit-2026-10.md](audit-2026-10.md), Top-25 = TD-009…TD-033, plus TD-034 re-raised by the Windows check; the long tail stays in the snapshot's appendix), or from an ADR's evidence (TD-035 to TD-037, ADR-048), whose row links the work package that carries it instead of the audit checklist (a P0/P1 row links its own issue). Re-measure with `scripts/audit_metrics.py`. Status is `open` (with a note where useful), `fixed (#PR)`, `accepted (ADR-0xx)`, `closed (reason)` or `superseded (by …)`; historical rows TD-001…TD-008 carry an issue only where one exists. Never delete a row; a resolved row says so.

| ID | Area | Description | Severity / Effort | Status | Issue | Source |
|----|------|-------------|-------------------|--------|-------|--------|
| TD-001 | Plant rendering | Plants currently rendered as flat colored circles | — | closed (Phase 6, ADR-040 sprites) | — | 2026-04 |
| TD-002 | Textures | Procedural patterns are too subtle, barely visible | — | closed (ADR-042 texture forge) | — | 2026-04 |
| TD-003 | Plant cache | SQLite cache for plant API data not yet implemented | P2 / M | open (0 `sqlite` hits in `src/`, 2026-10-03) | — | 2026-04 |
| TD-004 | Object model | Some object types share code that could be better abstracted | P2 / M | superseded by the measured duplication row AUD-011 (five `contextMenuEvent` copies, epic #392) | #458 | 2026-04 |
| TD-005 | Test coverage | Some UI components lack automated tests | P2 / L | superseded by measurement: `ui` 68.5 % lines / 46.9 % branches (audit-2026-10 §5.3); see TD-013, TD-024 | — | 2026-04 |
| TD-006 | Error messages | Some error messages are technical, not user-friendly | P3 / M | open, unmeasured | — | 2026-04 |
| TD-007 | Constraint anchors | Polygon/polyline edge anchors use dynamic `EDGE_TOP/BOTTOM/LEFT/RIGHT` classification (dominant axis). Classification changes when a vertex moves far enough to flip an edge's axis, causing constraint indicators to jump to the wrong edge. Replace with `AnchorType.EDGE_MIDPOINT` + stable numeric `anchor_index` so the edge identity is axis-independent. Workaround in place (index-only match in `_resolve_anchor_position`). | P2 / M | open; workaround in place | — | 2026-04 |
| TD-008 | Constraint solver | Newton-Raphson refinement uses a numerical central-difference Jacobian (`constraint_solver_newton._JACOBIAN_H`). An analytic Jacobian per constraint type would be faster (roughly 2N × eval savings per iteration), but numerical cost is microseconds for typical ≤20-variable systems so no user-facing impact. Revisit only if large-scene solves become a bottleneck. | P3 / L | accepted (ADR-012) | — | 2026-04 |
| TD-009 | Gates/CI (code) | 5 duplicate context keys in fill_translations.py silently drop 62 translations; 5 German PDF strings never reach de.ts | P0 / S | fixed (#411) | #393 | audit-2026-10 AUD-029 |
| TD-010 | Architecture (code) | Free-text annotations (TextItem) are silently dropped from the .ogp on save — data loss | P0 / M | fixed (#394) | #394 | audit-2026-10 AUD-001 |
| TD-011 | Security (data) | Loader silently drops items it cannot decode: a legacy plan whose background image moved loses it on load and permanently on the next save; duplicate item_ids accepted | P1 / S | fixed (#397) | #397 | audit-2026-10 AUD-043 |
| TD-012 | Security (security) | Loopback MCP endpoint's only browser barrier is an mcp SDK default the floor pin does not require (PoC: 1.22.0 serves Host: evil.example) | P1 / S | fixed (#396) | #396 | audit-2026-10 AUD-039 |
| TD-013 | Hotspots (test) | Four user-reachable array features in CanvasView (CC 21-31) are 1.2-1.3% covered and have no tests | P1 / S | fixed (#395) | #395 | audit-2026-10 AUD-010 |
| TD-014 | Docs (documentation) | Six documents declare CI gates and limits that ci.yml never runs (mypy, coverage, formatter, xvfb, 110 cols) — grouped docs drift | P1 / S | completed; v1.29.6; [PR #422](https://github.com/cofade/open-garden-planner/pull/422) (#401 gate/docs corrections) | #401 | audit-2026-10 AUD-062 |
| TD-015 | Docs (documentation) | Agent skills state CI and security facts the code contradicts: 'three CI jobs', 'only lint/test/security', 'no token auth', 'ADR-001…034' | P1 / S | fixed (#398) | #398 | audit-2026-10 AUD-064 |
| TD-016 | Process (process) | 'Never merge on red' is prose-only: required status checks are off on master, merges use --admin, PR #323 merged on a red Test | P1 / S | completed; administrator-enforced protection active and verified; v1.29.6; [PR #422](https://github.com/cofade/open-garden-planner/pull/422) | #399 | audit-2026-10 AUD-085 |
| TD-017 | Security (data) | A .ogp that fails mid-load leaves a partial scene with the PREVIOUS file as current_file; Ctrl+S then overwrites the user's good plan | P1 / M | fixed (#403) | #403 | audit-2026-10 AUD-040 |
| TD-018 | Architecture (code) | Clipboard serializer drops 4 persisted fields and 7 item types the file serializer handles — copy/paste silently loses data | P1 / M | fixed (#400) | #400 | audit-2026-10 AUD-002 |
| TD-019 | Tests (test) | Serializer round-trip tests under-assert: 1 093 serializer mutants survive the 3 project unit files; 8 of 10 sampled also survive 19 persistence test files | P1 / M | fixed (#394) | #394 | audit-2026-10 AUD-017 |
| TD-020 | Gates/CI (process) | mypy strict is declared a CI gate in four documents but never runs; 2 104 errors in 134 files | P1 / M | completed; fresh locked baselines: 1,966 errors on each OS (Linux 137 files, Windows 136); v1.29.6; [PR #422](https://github.com/cofade/open-garden-planner/pull/422) | #401 | audit-2026-10 AUD-030 |
| TD-021 | Gates/CI (test) | Coverage report and >80 % floor are declared (NFR-MAINT-02, §10.6, §8.6) but never measured anywhere | P1 / M | completed; final Linux floors: root 37, agent_api 92, app/core 77, models 95, services 86, spike_q3d 64, ui 71; 75.5% line / 58.7% branch, 7,642 Linux tests passed; v1.29.6; [PR #422](https://github.com/cofade/open-garden-planner/pull/422) | #402 | audit-2026-10 AUD-031 |
| TD-022 | Dependencies (dependency) | Release build has no lockfile: 4 of 42 shipped runtime dists exact-pinned; v1.29.0 shipped 9 runtime dists at versions published after the v1.27.9 build | P1 / M | completed; release-seeded lock and explicit build backends; v1.29.6; [PR #422](https://github.com/cofade/open-garden-planner/pull/422) | #404 | audit-2026-10 AUD-048 |
| TD-023 | Docs (documentation) | §8.7 promises 'all errors logged' but the logging module has no handler anywhere: 55 handled-error log calls are discarded in the windowed exe | P1 / M | fixed (#405, ADR-052) | #405 | audit-2026-10 AUD-063 |
| TD-024 | Tests (test) | Constraint-tool characterization: full-suite coverage raised from 679/2340 lines (29.0%) and 68/706 branches (9.6%) to 2023/2372 lines (85.3%) and 486/720 branches (67.5%); all 13 registered gestures and a 60% per-file floor | P1 / L | completed; owner acceptance, protected PR #477; v1.30.2 | #406 | audit-2026-10 AUD-016; ADR-050 addendum |
| TD-025 | Security (data) | NaN/Infinity accepted at the .ogp boundary: NaN canvas breaks render_canvas_image, non-finite values are re-saved as invalid JSON | P2 / S | open | #453 | audit-2026-10 AUD-041 |
| TD-026 | Architecture (design) | core/tools/constraint_tool.py:34 imports ui.canvas.items at module level — the one violation of invariant 11 | P2 / S | open | #456 | audit-2026-10 AUD-003 |
| TD-027 | Architecture (process) | No layering fitness function in CI; a naive import-linter contract reads 0 kept / 2 broken and cannot see the function-local allowance | P2 / S | open | #456 | audit-2026-10 AUD-005 |
| TD-028 | Architecture (design) | models/ is not the pure-data leaf the module map declares: 2 upward imports; 5 package cycles at module level (9 counting function-local edges) | P2 / S | open | #456 | audit-2026-10 AUD-008 |
| TD-029 | Tests (documentation) | §8.10 lists 4 integration files (skill: ~70) vs 114 actual; the tests/ui layer is not distinct in practice | P2 / S | open | #460 | audit-2026-10 AUD-018 |
| TD-030 | Tests (performance) | Theme-switch tests cost 282.6 s in the battery vs 12.4 s alone: closed widgets are never deleted, so every apply_theme re-polishes a growing population | P2 / S | open | #460 | audit-2026-10 AUD-019 |
| TD-031 | Tests (test) | Solar math is executed but under-asserted: no test timestamp has nonzero seconds and no oracle row nonzero minutes, so a 44.7-degree elevation mutant survives | P2 / S | open | #460 | audit-2026-10 AUD-021 |
| TD-032 | Tests (test) | companion_sets: the P1-4 candidate cap, the P2-12 dedup merge and the antagonist rejection are never executed by any test | P2 / S | open | #460 | audit-2026-10 AUD-022 |
| TD-033 | Tests (test) | Small Qt-free modules score 80-88 %; the surviving gaps are the canvas edge, stacking expand/arrange and shape-type branches | P2 / S | open | #460 | audit-2026-10 AUD-025 |
| TD-034 | Performance (performance) | NFR-PERF-01 missed in a real window: fit-in-view repaint of the 500-object reference plan takes 54 ms (≤ 18 fps), a zoom step 40 ms; 100 % zoom and pan stay inside the budget | P1 / M | fixed (#409) | #409 | audit-2026-10 AUD-056 (Windows check §8.1) |
| TD-035 | Bundle size | Master's release ships ~21 MB of Qt Quick 3D runtime it never loads (Quick3D + ShaderTools DLLs and QML modules, pulled in by the PyInstaller QtQml hook; measured in the ADR-048 evidence run). Phase 17 puts it to use; on a NO-GO, exclude it in `installer/ogp.spec`. | P3 / S | accepted (ADR-048) | #384 | ADR-048 L0 evidence (Windows v6 footprint) |
| TD-036 | 3D geometry source | The Qt Quick 3D spike builds its world from private canvas helpers (`_item_footprints`, `_plant_canopy_radius_cm` in `ui/canvas/sun_shadow_controller.py`). The Qt-free core of Phase 17 L1.1 must promote them to a public, tested module before building on them (senior review, ADR-048). **Fixed in L1.1:** `ui/canvas/footprints.py` is their public home (`item_outline`, `item_footprints`, `plant_canopy_radius_cm`), pinned by a golden fixture generated before the move; the spike, the shadow overlay and the 3D snapshot import the public names. Two underscore aliases stay in `sun_shadow_controller.py` for two frozen test suites until L1.10. | P2 / M | fixed (L1.1, ADR-059) | #385 | ADR-048 L0 senior review |
| TD-037 | Task calendar | Every GUI task surface (the planting calendar's Gantt and dashboard, the Tasks tab) takes its frost-relative windows from the current year's frost only, and the Gantt clips them to that year, while the agent's `get_tasks` / `get_task_calendar` (`generate_for_date_window`) also list windows anchored on other years' frosts. So the GUI does not show a task whose window is anchored on another year's frost: with a 9 April frost, garlic's autumn sowing (9–23 October 2026) appears on no GUI surface. A sweep of the 6 frost dates `scripts/measure_task_window_sweep.py` uses finds each of the bundled (species, task type) windows missed at some frost date; the `--wide` mode covers all 118 species on every day of 2026. Examples, sweeps and the code sites to change are in #414. | P1 / M | fixed (#414) | #414 | ADR-048 L0 senior review (PR #413) |
| TD-038 | Constraint presentation | Repeated type presentation dispatch; now one immutable enum-complete panel descriptor with independent rendering and localization guards | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-012; ADR-012 addendum; [A5 evidence](audit-2026-10-a5-evidence.md) |
| TD-039 | Solver evidence | Selection-scoped historical mutation gaps; fresh sample and geometric oracles, including corrected all-pinned false convergence | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-023; ADR-012 addendum; [A5 evidence](audit-2026-10-a5-evidence.md) |

## 11.4 Known Development Pitfalls

- **Hold a worker in flight when proving GUI responsiveness** (PR #490): the
  sun-mismatch heartbeat test failed on CI with two ticks instead of three while
  three other full CI runs and the local suite passed. Tagged worker/timer traces
  showed that the count depended on compute duration and included post-completion
  ticks. The test now holds the real computation with an Event, requires three
  heartbeat ticks while the worker is running/pending on a different thread, then
  releases it and validates the real result. Failure cleanup always releases the
  worker; the timer interval and result timeout are unchanged. Pinned by
  `tests/integration/test_sun_mismatch.py::test_explicit_worker_keeps_gui_responsive`;
  a synchronous-worker mutation was observed failing its thread assertion.

- **Attribute frozen code from collected files, not only declared dependencies**
  (PR #490 / #454): the 47-component SBOM check passed while the executable's PYZ
  contained unreported setuptools, packaging, pytest/mypy dependencies and nested
  vendored libraries. `Requires-Dist` and a hardcoded hook exception did not describe
  what PyInstaller collected. `installer/frozen_inventory.py` now maps actual Analysis
  source paths through wheel RECORDs, with nested vendored precedence, and bundles
  those owners' metadata/licenses plus a module/file ownership manifest. The checker
  compares it with the executable PYZ and locks containing-wheel versions for vendored
  copies; declared license files must exist and their text must reach the notices.
  Pinned by `tests/unit/test_frozen_inventory.py` and
  `tests/integration/test_distribution_inventory_pipeline.py::test_frozen_hook_dependencies_are_in_the_inventory`
  (observed failing on the original artifact). Synthetic fixtures constructed from the
  expected closure prove orchestration, not complete frozen attribution.

- **A stale `*.egg-info` on `sys.path` silently shrinks anything derived from installed metadata (#454, 2026-10-13).** The runtime-distribution resolver behind the release's third-party notices and SBOM returned **five** distributions (the project + `Pillow` + the three `PyQt6*` wheels) when a test ran it, but the same interpreter returned **48** when the module was run directly. Root cause: a legacy `src/open_garden_planner.egg-info` (version `0.1.0`, written years earlier) was still on disk; the editable install puts `src/` on `sys.path`, and `importlib.metadata.distribution("open-garden-planner")` returns the **first** match — so `Requires-Dist` described a two-year-old project. Two lessons. (1) **Check what `sys.path` order resolves** — when a metadata lookup disagrees with a file a human can read, print the distribution's `_path`; the answer is usually "you got a different distribution than you meant". (2) **Anchor build inputs on the manifest, not on the environment's copy of yourself**: the resolver now reads `[project].dependencies` from `pyproject.toml` and only walks *third parties* through installed metadata, so no stale artefact of the project's own history can change what ships. Related, same task: PyInstaller's `hook-importlib_metadata` bundles setuptools' **vendored** `importlib_metadata` (Apache-2.0) even though nothing declares it — the initial explicit hook exception was superseded in PR #490 by physical RECORD attribution of every collected wheel owner, including vendored copies (see the preceding pitfall).

- **No free solver variables does not imply feasibility** (#457, ADR-012):
  two pinned anchors 100 cm apart with a 200 cm target were reported converged
  with zero error. `[A5-NEWTON] no free slots` and its caller stack showed Newton
  returning before residual evaluation; `solve_anchored` then took the minimum
  with that fabricated zero. Evaluate the fixed-state residual before returning.
  Pinned by `test_constraint_solver_invariants.py` (both direct Newton and graph
  regressions failed first) and the real CanvasView feasibility integration test.
  A convergence flag must agree with independently measured geometry.

- **Translated row templates can still contain English object labels** (#457):
  unnamed endpoints were title-cased from enum identifiers, so German rows read
  `Polygon – Rectangle` despite a correctly translated Properties panel. Trace
  the upstream name builder and use `get_translated_display_name` at display time;
  the previous-season compare overlay had the same fallback. Enumerate every
  `ObjectType` against the compiled catalog (missing Hedge/Roof Ridge entries
  were added), and test real rows/tooltips with unnamed objects. Descriptor tests
  passing literal `A`/`B` cannot cover this boundary. Preserve user names and data.

- **Within-day simulation tests must fix time as well as date** (ADR-053): the
  sun-mismatch workflow set the date, retained 23:49 from the host, then added an
  hour. Correct next-day invalidation contradicted its `ready` assertion. Tagged
  datetime/caller tracing reproduced the same failure alone. Set the fixture to
  noon with `set_time_of_day`; retain worker, cache and date-invalidation checks.
  Do not change production clock semantics or relax timeouts to fix the fixture.

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


- **Canvas item caching, Level of Detail (LOD), and selection handle ghosting (issue #409, TD-034, AUD-056)**: Large plans (e.g. 500 objects / 990 scene items) missed NFR-PERF-01 (fit-in-view was 54 ms / ≤ 18 fps) due to three compounded bottlenecks: (1) un-cached filesystem stat calls in `_resolve_svg_path` for plant and furniture sprites on every frame; (2) rasterising high-detail SVG plant sprites and texture tiles when zoomed far out and covering only 6–10 screen pixels; (3) lack of caching for static canvas items during pan and zoom. Solutions:
  - Cache SVG path resolution with `@functools.lru_cache`.
  - ~~Level-of-Detail (LOD) flat fills below 0.4 zoom~~ — **never ran, and removed in #503.** The branch was written here as an optimisation and shipped as dead code: its guard (`widget is not None`) was never true on the canvas, because Qt passes `widget = 0` for every *cached* paint and every unselected item is `DeviceCoordinateCache`. #409's measured gain came from the `lru_cache` and the device cache, not from this branch. When #503 fixed the guard, the owner's manual pass rejected the feature on sight — at 20–25 % zoom, which is where they work and well under the threshold, every texture on the canvas, every plant sprite and every furniture item would have flat-filled, along with the paint-level overlays drawn after the fill branch (a bed's grid, rotation indicator, soil-mismatch border and capacity badge; a plant's spacing ring, companion highlight and antagonist badge). The branch, its `LOD_FLAT_FILL_THRESHOLD` and its tests were **deleted** rather than made reachable; the measured basis for that is in §11.4.11. `should_use_lod_flat_fill` and `get_lod_fill_color` no longer exist, and no zoom-dependent simplification remains in the canvas.
  - `DeviceCoordinateCache` on canvas items: static items enable caching for fast repaints (~12.8 ms fit-in-view, ~4.5 ms pan/zoom).
  - **Pitfall**: When an item has `DeviceCoordinateCache` while selected, child items with `ItemIgnoresTransformations` (resize/rotation handles) ghost or lag. Contract: items disable caching (`NoCache`) when `isSelected() is True`, and re-enable `DeviceCoordinateCache` on deselection.
  - **Export fidelity**: During exports, `_disable_item_caches` temporarily clears item caches so `scene.render()` outputs full vector fidelity without device-pixel cache scaling artifacts. Pinned by `tests/integration/test_canvas_item_cache.py` and `tests/perf/test_nfr_budgets.py`.

- **Two divergent item serializers create silent data-loss gaps on clipboard operations; unify under one chokepoint.** (Issue #400, AUD-002, TD-018): `CanvasView` maintained its own separate ~500-line item serializer and deserializer (`_serialize_item`, `_serialize_item_core`, `_deserialize_item`) that diverged from `ProjectManager`. The clipboard serializer dropped `spacing_radius_cm` overrides, `frost_protection_needed`, `label_visible`, and `path_fence_style`, and silently skipped newer geometric types entirely (Arc, Bezier, Groups). The fix eliminated the duplicated serializer completely: `CanvasView` now delegates all item serialization and deserialization directly to `ProjectManager`'s static methods. UUID stripping and geometry offsetting (`_strip_item_ids`, `_offset_item_dict`) are handled uniformly by pure helpers before pasting/patterning. Lesson: having two serialization paths for the same data vocabulary guarantees divergence over time; one authoritative serializer must back both file I/O and clipboard operations.
- **Opening a corrupt plan must never contaminate document identity or wipe existing recovery files.** (Issue #403, AUD-040, TD-017): When loading a corrupt `.ogp` file where deserialization raised mid-loop, the previous scene items had already been cleared while `_current_file` still pointed to the previously open plan file. Hitting Ctrl+S immediately overwrote the good plan on disk with the empty or partial scene. Furthermore, `_load_project_file` cleared the existing autosave *before* the load succeeded. Fix: (1) two-phase atomic deserialization validates all items, layers, guides, and constraints in memory before mutating the scene; (2) on any load failure, `ProjectManager.load()` clears `_current_file = None` and marks the document dirty, ensuring Ctrl+S triggers Save As rather than overwriting; (3) `GardenPlannerApp` preserves the existing autosave file on disk until the new plan loads successfully.
- **Missing or corrupt external assets must load as placeholders to survive save cycles.** (Issue #397, AUD-043, TD-011): A legacy plan whose background image file had moved on disk or whose embedded image bytes failed decoding previously caught the exception and returned `None`. As a result, the background image was silently dropped from the scene and permanently lost on the next save. Fix: `BackgroundImageItem` loads a lightweight placeholder item (`is_placeholder=True`) that preserves the original metadata, scale, opacity, and file paths. On save, the placeholder emits its original raw dictionary so assets are preserved even when momentarily unreadable. Additionally, duplicate `item_id`s in a plan file are detected on load and re-minted with fresh UUIDs to prevent corrupted scene graphs.
- **Every placeable graphics item must be covered by serializer round-trip matrix tests.** (Issue #394, AUD-001, AUD-017, TD-010, TD-019): Free-text annotations (`TextItem`) were serializable on the clipboard since v1.1 but completely missing from `ProjectManager._serialize_item_core` and `_deserialize_item_core`. Saving a plan containing text annotations silently dropped them. Unit tests tested persistence for common shapes but lacked an exhaustive matrix across all concrete placeable item types. Fix: `TextItem` is serialized natively under `type: "text"` with font, color, content, and position attributes. A comprehensive round-trip matrix test (`tests/integration/test_item_roundtrip_matrix.py`) verifies exact dictionary equality and round-trip fidelity across every concrete placeable item in the application.
- **"The app changed behaviour" is a claim about a *setting* until the setting has been read.** (Issue #366, owner's manual test): "on startup it no longer asks for my recent projects, it lands on the empty canvas." The obvious suspect was this branch, and the obvious suspect was **wrong twice** — first I blamed the test suite for persisting `show_welcome_on_startup = False`, then I "corrected" myself by pointing at the settings getter, which was also wrong because `QSettings` maps a slash key (`startup/show_welcome`) to a registry **subkey**, so a `Get-ItemProperty` on the parent shows nothing and the key looks absent. The value was there, set to `false`, and the test suite was innocent: `tests/conftest.py` rebinds the org to `cofade_test`, so test writes cannot reach `cofade` — proven by running a test that sets the flag and re-reading the real key. Nothing in the PR touched `welcome_dialog.py` or `settings.py` (empty diff), and the dialog's "Show this screen on startup" checkbox persists that value on click. So it was a user preference, undone with one `reg delete`. Two lessons: **read the persisted value with the same API that wrote it** — `reg query <key> /v` on the *subkey*, or the getter itself, not a parent-key dump; and **check the PR's own diff before blaming it or writing a fix.** A settings-shaped report is the one class of bug report where the correct patch is very often no patch.
- **A CLI's SUCCESS output needs the same treatment as its failure output.** (Issue #366, owner's manual test): the failure path got a condenser (a CLI that rejects its arguments prints its whole help, and the dialog renders that in a one-line label). The success path did not — and `install_to_client` returns the CLI's **stdout** as `detail`, which the dialog appends to the status line. OpenCode 1.18.x frames its confirmation in a coloured box, so the label showed literal `[]90m` fragments and mojibake, because `│`/`◆` are multi-byte and a `QLabel` is not a terminal. Two things had to be stripped, not one: **ANSI is not only SGR** (`ESC [ 2K` erase-line and cursor moves are just as destructive), and the **box glyphs survive escape removal** and have to go separately. Worth noting *which* client: 2.0.16 prints plain text, so probing only the modern binary showed clean output and the bug looked version-specific when it was version-*detection*-specific. The test now uses the real 1.18.32 bytes verbatim.
- **A cleanup fixture that runs in the wrong ORDER is not a cleanup — and a plausible mechanism is not a mechanism.** (Issue #366, the exit-139 segfault; **UNRESOLVED**, and this entry records what is known rather than a story that reads well). What is known: on this branch CI segfaulted on roughly half its runs, and the crash stack's only project frame is `agent_api/server.py` ``_run`` — the crashing thread IS a live uvicorn event loop. What is **not** known: which test leaves it. Two attempts are on the record and neither closed it. (1) `AgentApiServer.stop()` was a bounded best-effort join — set `should_exit`, join 5 s, log a *warning*, return with the thread still running. It now takes a second bounded grace join and escalates to `logger.error`. (2) An autouse `tests/integration/conftest.py` fixture stops any server a top-level app still owns. Attempt (2)'s *first* version also had the wrong **timing**: pytest finalises fixtures in **REVERSE setup order**, so a fixture that does not request `qtbot` may run after `qtbot` has deleted the window — stopping a server whose providers already point at a dead QObject. Requesting `qtbot` makes it tear down last, while the app still exists. **That general lesson stands: an ordering-sensitive teardown must declare its dependencies explicitly, because "after the test body" and "after every other teardown" are not the same moment.** What did *not* stand was the mechanism the guard's docstring asserted — that `QTimer.singleShot(1500, _maybe_start_agent_api)` lets an app auto-start a server during tests. **It cannot**: `tests/conftest.py`'s autouse `_disable_agent_api_server` sets `KEY_AGENT_API_ENABLED = False` for every test. That claim was written with a citation-shaped confidence and checked by nobody, and the final pre-merge review falsified it from the suite's own fixtures. Two rules from that. (a) **A causal story in a pitfall log is a lead, and a lead with a `file:line` reads as a verdict** — so state the evidence and the gap separately, and never let a hypothesis harden into an assertion just because it is repeated. (b) **Check that the mechanism can happen before documenting it**, and check the guard's actual reach: this one reaches the *app's* server only, so tests that construct `AgentApiServer(...)` directly (`test_agent_api_exports.py`, `test_agent_api_frozen_exe.py`) are outside it — though all of those do call `stop()`. A thread-inventory run also over-reported: it flagged threads *appearing* during a test, not ones surviving, so most of its hits were servers starting and stopping normally. Both CI Test runs at the reviewed tip passed, which is **not** evidence the cause is gone. If this recurs it needs its own investigation, starting from the stack rather than from this entry.
- **An INDETERMINATE answer must never select the more DANGEROUS option.** (Issue #366, the final pre-merge review's only P0): the client-CLI capability probe returned an empty flag set when it could not read a binary's help, and the caller read empty as "this CLI is too old" — which selected `legacy_cli_argv`, the argv *without* `--global`. On a MODERN CLI that writes a **project** config into the user's current working directory and returns `success=True`; reproduced end to end, with the user config never touched and the dialog row then contradicting the success message it had just shown. The reasoning was backwards because it asked "which answer is absent" instead of "which failure is dangerous": **the modern argv fails loudly (the CLI prints its help), the legacy one fails silently and writes the wrong file.** So the probe is tri-state — `supported` / `unsupported` / `unknown` — and only a *definitive* absence of the flag may take the legacy path. The same review found the probe's `except` still enumerated `(OSError, subprocess.SubprocessError)` at a trust boundary, which invariant 14 forbids and which this module's own `registered_url` comment explains; it is now broad, and `errors="replace"` keeps a single undecodable byte in someone else's help from becoming an exception on POSIX (where `subprocess` decodes in the calling thread, so it would escape into the dialog's `__init__`) or an empty string on Windows (where it kills the reader thread — the silent path that caused this very bug). **A capability check is a three-valued question, and "I could not tell" is an answer.**
- **"Unparseable" and "empty" are different failures, and only one of them is dangerous.** (Issue #366, the owner's manual test): the onboarding merge's fail-closed rule is "an unreadable file we don't own is left byte-for-byte untouched". The owner's `~/.gemini/config/mcp_config.json` was **0 bytes** — which is what several clients ship before their first MCP server — and the merge reported `Could not read existing … (Expecting value: line 1 column 1 (char 0)); left untouched`. That message is `json.loads("")`. So a fail-closed rule written as "if we cannot use it, do not touch it" quietly answers a question the safety rule never asked: it protects *content*, and a 0-byte file provably has none. The general shape: **a guard phrased around the parser's opinion of the file inherits every quirk of that parser, including its opinion of an empty one.** The fix is a positive notion of emptiness (`_is_effectively_empty`) applied *before* parsing, in both the JSON/JSONC and TOML paths, and it must be applied under the STRICT `replace_on_parse_error=False` policy — otherwise "we protect your file" still quietly excludes "a file you have not written yet". The companion test asserts one byte of junk still fails closed, because the distinction that matters is empty vs corrupt, not lenient vs strict.
- **A refusal nobody asked for is a capability removal wearing a safety hat.** (Issue #366, same manual test, and a decision reversal recorded in ADR-035): a too-old client CLI was made to refuse rather than be handled, on the reasoning that its flags and config shape were unverified. The consequence was not a clear error — it was `install_method="manual"`, so **the Add button silently disappeared from the dialog**, and the owner reported the button missing. The refusal was also unnecessary: running the older binary against a throwaway config showed it writes the *user* config when the newer flag is absent, i.e. the fallback was not merely tolerable but correct. Three lessons. (1) **When a guard changes what the UI offers, check what the UI now offers** — a refusal that demotes a control to a snippet is a feature removal, and it will be reported as "the button is missing" rather than as the error it actually is. (2) **The blast radius of a safety decision is wider than the code it guards**: one `install_method` value moved a button. (3) **A CLI's config shape can differ between generations, not just its flags** — 1.18.x stores servers flat as `mcp.<name>` where 2.x nests them, so supporting both generations means the *reader* must accept both too, or it reports a working registration as absent. The manual snippet must follow the installed generation for the same reason: a snippet in the wrong shape is silently ignored, which reads as "OGP is broken".
- **A teardown that gives up quietly turns into a crash somewhere else, and the "somewhere else" is the only symptom you get.** (Issue #366, found by CI segfaulting — on this branch ~50% of runs, exit 139): the stack named `agent_api/server.py:_run`, i.e. `loop.run_until_complete(server.serve())`, still executing while an **unrelated** Qt test (`test_minimap_widget.py`) was tearing down. Chased to ground with a throwaway pytest plugin that stamped each server thread with the test that created it, which found the mechanism: **`GardenPlannerApp.__init__` schedules `QTimer.singleShot(1500, _maybe_start_agent_api)`**, so *any* test that builds the app can start a REAL uvicorn server 1.5 s later — on whatever event loop runs then, frequently a *different* test. Most such tests called `_stop_agent_api()` in teardown; the ones that did not left a live server thread holding its sockets and its `MainThreadBridge`, alive into interpreter teardown. Four lessons. (1) **A deferred start is a start you cannot see at the call site**: attributing the leak to the test running when the thread appeared points at an innocent bystander, and only stamping the thread with its creating test finds the culprit. (2) **A bounded `join(timeout=...)` that expires and only logs is not a teardown** — `AgentApiServer.stop()` set `should_exit`, joined once for 5 s, warned, and returned with the thread still running. It now takes a second bounded grace join and escalates to `logger.error`, because a leak nobody can see is a leak nobody fixes. (3) **The failing test is rarely the guilty one**; the stack is the evidence, and it pointed three suites away. (4) **Pin the invariant instead of hoping**: `TestServerTeardownLeavesNothingRunning` asserts the thread a server started is dead after `stop()` (three back-to-back cycles), and an autouse `tests/integration/conftest.py` fixture stops any live agent server after every test and *says so* when one is found. Verified by running the whole suite under the leak plugin: **0 threads survive at session end**, down from 1. Honest caveat: this is the only defect the crash stack named, and the flake may have more than one cause — if it recurs, treat it as its own issue rather than assuming this fixed it.
- **Verify the installed binary's CAPABILITY, not the product's documented interface — and check that a stub cannot stand in for a real binary.** (Issue #366, found by the owner's manual test, not by review): the OpenCode row's argv (`mcp add <name> --url <url> --global`) was verified by *running* `opencode mcp add --help` — but only against **one** of the two OpenCode installs on the machine. `~/.opencode/bin/opencode.exe` is **2.0.16** and has `--global`; an npm `opencode-ai` on the same box is **1.18.32** and has **no `--global`** at all (it writes the user config by default, and stores servers FLAT as `mcp.<name>` rather than nested under `mcp.servers`). `shutil.which` returns whichever comes first on `PATH`, and which one that is depends on **how the process was launched** — the owner's shell resolved 2.0.16, the GUI resolved 1.18.32, so the same button succeeded in one and failed in the other. The failure was not clean: a CLI handed an unknown flag answers with **its entire help text** and a non-zero exit, and the dialog renders `detail` in a one-line status label, so the user saw a wall of flag descriptions and no explanation. Two lessons. (1) **When argv is verified against one version, either verify the version or require the flag** — `ClientTarget.cli_required_flags` now does the latter, probing the resolved binary's own `mcp add --help` and refusing before anything is written; a *version string* was measured and deliberately not used, because parsing a help for a flag is evidence the binary accepts it, while `--version` output is a naming convention. (2) **A `shutil.which` stub returns a path that does not exist, which correct code reads as "cannot probe, therefore cannot use"** — so a stub-based test cannot detect this class of bug and in fact *depends* on the stricter behaviour. The only thing that found it was clicking the button on a machine that had two installs. Note also that the 1.18.x help has **no `USAGE:` line at all** (it opens with the command line and goes straight to `Positionals:`), so a "is this a help dump?" heuristic keyed on `USAGE:` alone would have missed the exact case it was written for; a test with the real help text as a fixture is what caught that.
- **A claim written from the producer's side is not a delivered feature — and a test that skips the consumer cannot catch it.** (Issue #366, senior-review round 5, five rounds into one branch): round 4 moved the merge's `.bak` to just before the write, put its location into `InstallResult.detail`, and documented the user-facing consequence in three places — the function's docstring, ADR-035 and this log. All three were true about the **producer** and false about the **product**: the Connect dialog's success branch renders `Added to {client}.` and never read `result.detail`; only the *failure* branch formatted it. The field was populated, the field was documented, and the user's experience was exactly what it was before the fix. The test named `test_a_successful_merge_does_report_its_backup` made this invisible by construction — it asserted `backup is not None and backup.exists()` while its name and docstring promised "the caller is told where it is", and it called the private `_merge_into_config`, which cannot see `_report()` or `install_to_client`. Two rules, both cheap: **a test about a user-visible claim has to go through the path the user goes through** (that one now drives `install_to_client` and asserts the string names both paths, so the name is enforceable); and when a field is added to a result object, **grep for its consumers** — `InstallResult` had two fields the success path never read, and nothing in the type system or the suite noticed. The sibling failure in the same round was a fixture that cleared `CLAUDE_CONFIG_DIR` but not `XDG_CONFIG_HOME`, so a test read the developer's real `opencode.jsonc` and passed vacuously against a file the code could not reach — which is the §11.4 scar from round 1, in a new place. **A fixture that redirects config paths must clear every env var the resolver honours, and the fix is to look at the sibling fixture that already got it right.**
- **A refusal must leave the filesystem exactly as it found it — so take the backup as late as possible.** (Issue #366, senior-review round 4): the onboarding merge copied a `.bak` *before* deciding whether to write. Every refusal therefore littered a second file next to a config OGP had just declined to touch, and the module's whole safety rule is about foreign files (`~/.claude.json` holds OAuth and project trust; `~/.codex/config.toml` holds the user's model choice). The trigger is mundane: it surfaced only because a test asserted the whole directory listing rather than "the file is unchanged" — which is the lesson. **Assert on the directory, not just the target file**, when a failure mode is "we declined to act"; a `.bak` beside an untouched file is invisible to `read_text()` assertions and reads as correct. The corollary is user-facing: when a write *does* happen, the backup path now goes into `InstallResult.detail`, because a backup that is made but never reported is not a safety feature, it is litter the user cannot find.
- **"Unparseable" and "parseable but the wrong shape" are different failures and must not share a policy.** (Issue #366, senior-review round 4): the onboarding merge's fail-closed rule reads "an unreadable `foreign` file is left byte-for-byte untouched". But the code also treated a *readable* file whose `mcpServers` key was the wrong type (`{"mcpServers": "oops"}`) as replaceable — it did `servers = data.get(...); if not isinstance(servers, dict): servers = {}`, which **overwrote the wrong-typed container even when `replace_on_parse_error=False`**, i.e. it clobbered a file it had just promised to protect, and took the user's unrelated top-level keys with it. The distinction: a **parse** error means we understood nothing and a replace is defensible for a file we own; a **shape** error means we read the document perfectly well and only one key is the wrong type, so replacing discards data for no reason. Shape errors now fail closed whatever the ownership says — a deliberate narrowing of the one `own` target's contract. A backstop that is written as "if we cannot use it, start again" quietly answers a question the safety rule never asked.
- **A "best-effort, never raises" reader must own its failure type — and, more importantly, must not enumerate.** (Issue #366, senior-review rounds 2 and 3): the JSONC reader was made to *raise* on an unterminated `/*` rather than silently swallow the rest of the file (swallowing is how a user's server entry gets eaten). Round 2 gave it a module-owned exception; round 3 found the *enumerated* `except` tuple underneath was the actual bug, when `RecursionError` — which both `json.loads` and `tomllib.loads` raise on a deeply nested document — escaped `registered_url` → `detect_clients` → the dialog's `__init__`, and PyQt6 turned the unhandled exception into `qFatal()`/`abort()`. The user-visible symptom: put a deeply nested config where a client keeps its settings, click Help → "Connect AI Assistant…", and the application dies. The general rule is invariant 14's: **one broad `except Exception` at the ingestion chokepoint for untrusted input, and never a list of families** — every family added is a family still missing, and the correct reading is that the broad catch *is* the fix, not a concession. Corollary: a docstring claiming "yields `None` … never an error" is only true if some test drives the function through its *real* caller.
- **A guard checked on some paths is not a guard.** (Issue #366, senior-review rounds 2 and 3): `ClientTarget.merge_supported=False` was meant to guarantee "OGP will not rewrite your OpenCode config". Round 2 found it checked on the no-CLI path but not on the CLI's "already exists" self-heal — the path a user reaches after a **port change or token rotation**, the case the whole issue exists for — and the merge there re-serialised the file and reported success. Round 3 found a third seam that bypassed it entirely (a record with a `cli_name` on `PATH` but no `cli_argv`). The check now lives **inside** the merge. The general shape: a flag that gates a destructive operation wants to be enforced at the seam, not at the call sites its author happened to think of. Ask, for every guard, "name the path that reaches the dangerous operation *without* passing my check" — and note that the code and the ADR can agree with each other and both contradict the flag, which is how this survived a review that had already read both.
- **A required dataclass field is a contract with an explicit consumer list, not a struct you can extend freely.** (Issue #365): adding `new_plan`/`open_plan` to `agent_api.providers.AgentProviders` is two lines that five test harnesses and one production path pick up automatically *only if you go and edit them*. The one that bites is `main.py`'s `--selftest`, which builds its own throwaway `AgentProviders` to prove the Agent API can bind. All 6304 ordinary tests passed while `--selftest` failed with `TypeError: missing 2 required positional arguments` — the product path constructs the real providers from the application, and every harness that touches it had been updated. Same class as #277 and #291: a subsystem dead while the process is alive. When you extend it, run `--selftest` (exit 0) rather than trusting a green `pytest`.
- **A test that exercises a real external binary will exercise it on the developer's machine.** (Issue #366): a unit test that installed a CLI-capable target called the *real* `opencode` binary, which executed `opencode mcp add --global` and modified the developer's own `~/.config/opencode/opencode.jsonc`. `shutil.which` finds those CLIs on a machine that has them, so "no CLI" is not the default a test gets. The fix is an **autouse fixture that stubs `shutil.which` for the whole module**, so the default is "no CLI" rather than "whatever happens to be installed here" — and the scar is worth more than the fix, because the same test produced the single most useful finding in the change: OpenCode's real container key is `mcp.servers`, not the `mcp` its published schema implies (`additionalProperties: {}`, which says nothing). The developer's config was restored.
- **A tool's declared return model is part of its contract, and testing the provider is not the same as testing the tool.** (Issue #365): `new_plan` and `open_plan` first shipped returning `ExportResult(**result)` while their providers returned a dict with no `format` key and a `None` `file_path` against a `str` field. Both therefore raised a pydantic `ValidationError` on **every successful call over the wire** — after the document had already been replaced — while all 22 body-level tests passed, because the main-thread body builds a plain dict and never constructs the model. The two lines between provider and tool were the untested part. A `BaseModel` on a tool's return type is a contract, and it needs coverage at the same level as the handler.
- **A third-party config file is a *superset* of the format you assume, and fail-closed turns that into a dead end.** (Issue #366): the onboarding module's safety rule is "an unreadable `foreign` file is left byte-for-byte untouched rather than replaced" (`~/.claude.json` also holds OAuth and project trust). OpenCode's `~/.config/opencode/opencode.jsonc` is a **JSONC** file — comments and trailing commas are legal — and the merge path read it with `json.load()`, which *raises* on a comment. Combine the two and the feature is not merely degraded but **impossible**: every real user's commented config fails to parse, fail-closed refuses to touch it, and OGP can never register. A fail-closed rule is not automatically the safe choice; it is only safe while the *read* can actually understand what it is refusing to clobber. Two lessons: (a) a tolerant reader must be **scoped to the format that needs it** — the strict `json` reader still raises, pinned by a negative test, because leniency leaking into the fail-closed path would turn genuine corruption into silent replacement; and (b) comment stripping has to be a **character scan, not a regex**, since `//` and `#` inside a string literal are data. Note also that this file is named `.jsonc`, so a detector that globs for `opencode.json` misses every real installation.
- **Never re-serialise a file you do not own.** (Issue #366): writing Codex's `~/.codex/config.toml` with `tomli_w` would be the obvious way to add a `[mcp_servers.<name>]` table, and it would silently **discard every comment and the user's own formatting** in a config file they maintain by hand. The surgical alternative is barely more code: `tomllib` (stdlib, read-only) parses and validates, then only the one table's line span between its header and the next header is rewritten. It also removes the dependency the obvious approach would have added. The general form of the mistake: a "rewrite the document" API is safe for *your own* file and destructive for someone else's, and the difference is invisible in the code.
- **A CLI's default scope can write into the user's project directory.** (Issue #366): `opencode mcp add` writes the **project** config unless `--global` is passed. Omitting the flag does not fail — it silently drops an `opencode.json` into whatever directory the user happened to be in, and the registration appears to work while applying to nothing. Verify a CLI's flags by *running* `--help` (this one was verified by running it), and pin any scope/flag that is load-bearing with a test asserting its presence in the argv.
- **A Qt dialog must not synchronously join a network worker during `closeEvent()`.** (Issue #342 / PR #344): closing the satellite picker while a Static Maps request was slow could freeze the GUI for the request timeout because `MapPickerDialog.closeEvent()` called `QThread.wait()` even after requesting interruption, while `google_maps_service._fetch_tile()` could remain inside `requests.get(timeout=10)`. The fix keeps the dialog alive, routes `reject()` and `closeEvent()` through one cancellation request, and rejects only from the worker's terminal signal; `GardenPlannerApp` tracks the modal picker so application shutdown follows the same path. Unexpected worker tracebacks are formatted and scrubbed before logging, while the dialog receives only a generic message. Pinned by `tests/integration/test_map_picker_dialog.py::TestFetchFlow::test_close_does_not_block_on_in_flight_worker` and `test_worker_logs_scrubbed_traceback_for_unexpected_failure`. Lesson: cancellation can be cooperative without making GUI teardown blocking; every Qt worker that touches network I/O needs an asynchronous owner lifecycle and a secret-safe diagnostic path.

- **A source checkout's `.env` is not automatically present in a packaged build, and a credential setting must not become a project secret.** The satellite picker originally read only `OGP_GOOGLE_MAPS_KEY`, so Python launches that loaded the repository `.env` worked while a frozen executable showed a disabled menu. The supported fallback remains the process environment or `.env` beside the executable. Issue #342 adds a Preferences value at `api_keys/google_maps_key`, with Preferences-first resolution and blank-field fallback to the environment. The key is intentionally absent from `.ogp` serialization, PyInstaller data, logs, and user-facing error details; never "fix" a frozen-build credential problem by bundling or auto-copying the secret. Regression coverage pins both resolution precedence and the immediate menu refresh after saving/clearing Preferences.

**A private item-tracking list must be dropped at the SAME chokepoint that destroys the items it tracks, not just at the one call site that happened to crash — and an audit that finds one sibling case must check for others in the same class (issue #337, shipped 2026-08-21 in v1.27.2 via PR #339).** Symptom: clicking File → New Plan with a plan that had the compare overlay (US-10.7) in use showed an error popup: ``RuntimeError: wrapped C/C++ object of type QGraphicsEllipseItem has been deleted``. Root cause: `_on_new_project()` called `scene.clear()` (which destroys every C++ QGraphicsItem in the scene), then called `clear_compare_overlay()` which iterated `self._compare_items` and called `removeItem()` on each Python wrapper — the C++ object behind each wrapper was already destroyed by `scene.clear()`. **Round 1** guarded only `clear_compare_overlay()` (a `contextlib.suppress(RuntimeError)`) and reordered the two calls in `_on_new_project()` — senior review reproduced the identical `RuntimeError` three lines below, in `set_compare_overlay_visible()`, which reads the same `_compare_items` list and is reachable from the "Show Previous Season Overlay" menu action any time stale wrappers survive a `scene.clear()` the guarded method didn't run for. The same review found a second, independent path to stale state: `_deserialize_to_scene()` (project load) removes items by an isinstance allow-list that never included the overlay's `QGraphicsEllipseItem`/`QGraphicsSimpleTextItem`, so opening a new plan could leave the previous plan's ghosted plants painted on the new canvas. **Round 1 fix**: `CanvasScene.clear()` overridden to drop `_compare_items` before calling `super().clear()` — one chokepoint, so both readers are safe by construction; `_deserialize_to_scene()` calls `clear_compare_overlay()` before its own item removal; the `except Exception` branch of `_load_compare_overlay_from_previous_season()` also clears the overlay. **Round 2**: a second senior-review pass, live-testing the round-1 fix rather than reading it, reproduced the *identical* `RuntimeError` on `_calibration_markers` — the scene's other private `QGraphicsItem`-tracking list (image-calibration crosshairs/lines), 800 lines away in the same class, exposed via `start_image_calibration()` → `add_calibration_point()` → `scene.clear()` → `cancel_calibration()`. It also found `_compare_overlay_visible` was left `True` by the round-1 `clear()` override even though the items were gone, so a freshly loaded overlay could silently start invisible/desynced from the menu action's checked state. **Round 2 fix**: `CanvasScene.clear()` now also drops `_calibration_markers`, `_calibration_points`, `_calibration_image`, `_calibration_mode`, and `_compare_overlay_visible`; `_open_project_file()`'s `except Exception` branch resets the compare-overlay action state and calls `clear_compare_overlay()` so a load failure mid-open cannot leave it stale either. **Known still-open**: three other sites in this codebase guard the *identical* hazard with `contextlib.suppress(RuntimeError)` / `except RuntimeError` instead of a chokepoint fix — `ui/canvas/sun_shadow_controller.py` (`_debounce.start()`, `_overlay` accessor) and `ui/canvas/sun_heatmap.py` (`_overlay` accessor, an items-iteration loop) — left alone here because they track different containers with different teardown lifecycles; audit them individually before assuming this entry closes the bug class. **Lesson**: when a private list tracks references into a container that has its own bulk-teardown method (`QGraphicsScene.clear()`), make that teardown method itself responsible for dropping the list — guarding or reordering the one call site a bug report names fixes the report, not the bug class; and when a review finds one sibling case, grep the same class for every other tracking list before declaring the audit done, because the second sibling (`_calibration_markers`) was sitting in the same file the whole time. Pinned by `tests/unit/test_compare_overlay.py` (`CanvasScene.clear()` drops the compare-overlay list, resets its visibility flag, drops the calibration trackers, and project load via `ProjectManager.load()` cannot leave a ghosted item behind) and `tests/integration/test_compare_overlay.py` (drives the real File → New Plan menu action end-to-end, then exercises the previously-unguarded `set_compare_overlay_visible` reader via the toggle action).

**`search()` and `get_by_id()` returned structurally different field sets for the same provider, and nothing wired the richer one into the selection flow (issue #297).** Trefle's `/plants/search` carries only identity/taxonomy fields; `growth`/`specifications`/`foliage` (and therefore sun/water/pH/nutrient/foliage) only exist on `/plants/{id}`'s detail response. `PlantAPIManager.get_by_id()` already existed, fully implemented per provider, but nothing called it — `PlantSearchDialog` assigned the raw sparse `search()` result straight through. **Fix**: `PlantSearchDialog._enrich_selected_plant()` fetches the detail record once, on confirm (not per browsed row, to bound the cost against rate-limited free tiers), and merges it onto the search result via a generic loop over every `PlantSpeciesData` dataclass field (`_merge_detail_into_search_result()`): a field at its dataclass default — or `None`, regardless of the field's own default type — in the detail response defers to the search result's value; everything else takes the detail response's value; `source_id`/`data_source`/`raw_data` always come from the detail response. A provider signaling "no richer detail exists" (`PlantDetailUnavailableError` — Perenual's free-tier paywall, HTTP 429 with a healthy rate-limit budget remaining, not exhaustion; or a Trefle record with a null `main_species`, ~4% of a live sample) falls back quietly; a genuine failure (any exception, or a `source_id` mismatch) shows a translated warning first, so a real error can't silently reproduce #297's own symptom.

**This shipped over seven senior-review rounds, each finding a real, live-reproducible defect in the previous round's own fix** — not cosmetic disagreements, but `AttributeError`s and silent data loss, several caught only by making the actual API call rather than reasoning from the code. Specifics worth knowing before touching this code again:
- A validation guard that rejects `common_name in ("", "Unknown")` as "bad response" is wrong: Trefle omits `common_name` for many valid, scientific-name-only species. Validate identity via `source_id` alone.
- Merging two records by wholesale replacement (`self._selected_plant = detail`) silently destroys any field the richer record happens to leave sparse. A field-by-field merge that defers to the *other* record only when the "winning" value is empty/default is the only version that can't lose data in either direction — and it must treat a present-but-`None` value as empty even for fields whose own default isn't `None` (`None == ""` is `False`, so a naive equality check misses it).
- A comment asserting a fact about live API behavior ("never observed live", "every lookup below is `.get(key) or default`") is worse than no comment when it's wrong, and it *was* wrong twice in this saga — once about `main_species` being non-null, once about a sweep actually being complete. Trust a fresh live check over a prior comment's claim.
- `dict.get(key, default)` only applies `default` when the key is ABSENT, not when present-with-null — the same trap #296 already documented, re-found three more times in this same file (`main_species`, then `scientific_name`/`family`/`genus`/`image_url`, then `observations`/`growth.description`/`flower.conspicuous`/`default_image`'s two URL fields) because each sweep trusted its own "done" comment instead of re-scanning the whole file.
- Opening a modal (`QMessageBox.warning()`) from inside a commit path (`_on_accept()`, before `self.accept()`) is a re-entrancy hazard the same way a blocking network call is: its nested Qt event loop can deliver a still-pending timer (here, `PlantSearchDialog`'s 500ms search-debounce timer) mid-commit. Same failure class as the #210 debounce/flush incident elsewhere in this file — stop any pending debounced action before anything destructive commits, as the literal first statement if needed.

**Takeaway**: this project's `.env` has working credentials for Trefle, Perenual, and Permapeople. A live call costs thirty seconds and settles what code-reading and argument cannot — use one before asserting a response shape, an id space, an error code's meaning, or a sweep's completeness. Pinned by `tests/integration/test_plant_search_enrichment.py`, `tests/unit/test_trefle_client.py` (`TestGetByIdSourceIdContract`, `TestMainSpeciesNullSafety`), and `tests/unit/test_plant_search_dialog_merge.py`.

**Update (manual testing, 2026-08-10): a defect one layer above the seven-round fix, invisible to every review round.** The user reported "Tomato" showing Full Shade/Low water/no pH after search+confirm — looking exactly like the fix had failed. Live-probing `TrefleClient` and the merge logic directly (bypassing the dialog) proved the enrichment pipeline itself was correct: `Full Sun`/`Medium`/`pH 7.0-7.5`, matching Trefle's real API data. The actual cause was pre-existing and one layer up: `PlantAPIManager.search()` always searches the user's local custom-plant library **first**, concatenated ahead of any API result with **no deduplication** — and the real, unstubbed `%APPDATA%\OpenGardenPlanner\custom_plants.json` on the test machine had accumulated 197 entries (180 of them duplicate "Walnut" test debris), including a stale custom "Tomato" record with wrong sun/water values whose `source_id` happened to collide with Trefle's own numeric id. That record was returned first, displayed with text identical to the real Trefle result (`Tomato (Solanum lycopersicum)`), and — correctly, by design — skipped enrichment entirely because `data_source == "custom"`. **Fix**: every search-result row now shows its data source (`plant_source_label()` in `ui/plant_species_assignment.py`, shared with the properties panel's own "Data Source" tooltip so the two can't drift apart), so a stale custom entry can never again be visually indistinguishable from a live one. **Lesson**: isolated worktrees and mocked HTTP structurally cannot catch a bug that only exists in real, unstubbed machine state — a developer's own accumulated custom-plant-library file is disk state outside git, outside every test fixture, and outside every reviewer's clean worktree. Manual testing against the actually-running app is the only phase in this project's workflow that can see it, which is exactly why CLAUDE.md makes it the final, sovereign gate rather than a formality after review passes.

**A plant's drawn icon has a fourth independent size, reversing an explicit ADR-037 rejection on the owner's call (issue #299).** A user assigning a Trefle-sourced Apple tree (max spread 590 cm) saw the shadow correctly shrink after setting "Current Spread" to 200 cm (a young tree), but the SVG icon on the canvas stayed at 590 cm. This was, at the time, a *deliberate* decision — ADR-037's growth addendum explicitly rejected rescaling canvas circles ("a display-scale on live items perturbs selection/snap/`mapToScene`, exactly the #218/#219 territory") — but the owner judged the resulting behaviour (a full-size mature icon casting a visibly smaller shadow) to read as a bug, not a feature, and chose to reverse the conclusion while keeping the original hazard analysis intact: never touch `rect()`/`pos()`/`transformOriginPoint()` (the actual thing selection/snap/`mapToScene` depend on). `CircleItem._visual_plant_diameter_cm()` renders the SVG pixmap (and, since a first cut missed this, the decorative drop-shadow — see below) at today's growth-interpolated spread when available, falling back to the footprint diameter unchanged otherwise; `rect()`/`radius` (spacing/overlap correctness, still governed by `core/plant_sizing.py`) are provably untouched, since selection/drag/rotation/undo/save all read only those, none of which this change reads or writes.

**A first cut of this fix shipped a severe, unrendered regression a senior-review pass caught before merge**: the decorative drop-shadow (a cosmetic depth effect, unrelated to sun/shade) was left keyed to the full mature `rect()` while the icon shrank, so a young plant rendered as a large grey disc with a tiny sprite inside — measured at 57.6% grey coverage of the frame, up from 1.5% before the icon shrank. No test caught it because every test asserted against the private `_visual_plant_diameter_cm`/`boundingRect()` helpers, never against an actual rendered frame — reverting the one changed line in `paint()` would have left all tests green. Fixed by computing the diameter **once** at the top of `paint()` and reusing it for both the drop-shadow and the icon, so the two can never disagree again. Two further gaps from the same review: `plant_database_panel._update_instance_metadata()` only called `prepareGeometryChange()` for `current_spread_cm`, but `current_height_cm` (via `growth_model._derive_from_other`) and `planting_date` (more elapsed time — more growth, even with no other field touched) can equally change what `boundingRect()` returns — now called unconditionally for every plant-instance write, since it's cheap; and `current_spread_cm`'s spin box (max 10 000) had no path into `render_plant_pixmap`'s `int(diameter)`-square `QImage` allocation before this change, the exact hazard US-D2.1 already capped for a different entry point — `plant_renderer.py` now clamps at the actual allocation site (`_MAX_RENDER_DIAMETER_PX = 5000`, protecting every caller, not just this one). Deliberately not reconciled: dragging a plant's resize handle no longer visibly changes its icon once growth data is set (the icon now tracks the growth timeline, not the footprint) — an accepted consequence of decoupling the two, not something this fix tries to paper over. Also deliberate: the icon uses **today's real date**, not the sun-simulation's scrubbed date — scrubbing the sun timeline changes the shadow/heatmap/3D but not the icon.

**Lesson**: before treating "the UI doesn't update" as a bug, check whether the change contradicts a *formally accepted* decision, not just a module docstring — grep the ADRs, not only the code you're about to touch; reversing one is legitimate with the right authority, but it has to be a conscious act, amended in place, not a silent override. And once a fix like this is written, **render it** before trusting it — a green suite that only asserts against private helpers proved nothing about the one thing a user actually looks at; a single test that paints to a `QImage` and measures pixel coverage would have caught the regression before it ever reached review. See ADR-037's growth addendum, FR-SUN-08, `core/plant_sizing.py`'s docstring (all amended alongside this entry), and the debug-verbose skill's matching case study for the full investigation.

**`dict.get(key, default)` is not None-safe, and it silently dropped API search results (issue #296).** A live audit of all three plant-lookup APIs (Trefle, Perenual, Permapeople) against a 10-plant dataset (trees/shrubs/flowers/vegetables), using real `.env` credentials, found two independent parsers crashing on the same anti-pattern: `data.get("cycle", "").lower()` (Perenual) and `data_dict.get("light requirement", "").lower()` (Permapeople). **`default` in `dict.get(key, default)` only applies when `key` is absent — not when it's present with a JSON `null`**, which is common in both APIs' public datasets for sparse records. A present-but-null value returns `None`, and the chained `.lower()` raises `AttributeError`. The exception is caught by a bare `except Exception` in each client's `search()` loop, so the record is silently dropped — no error reaches the user, only a `logger.warning` nobody reads. Live evidence: 16 silent parse failures logged across 8 of 10 Perenual test plants; reproduced offline (no live calls needed) by feeding `_parse_species({"cycle": None, ...})` directly. **Fix**: rewrite every such lookup as `(data.get(key) or default)` so a present-null value falls through to the default exactly like an absent key. Same audit also found: Perenual's free tier returns the literal string `"Upgrade Plans To Premium/Supreme - ..."` for premium-gated fields (`cycle`/`watering`/`sunlight`) instead of real data or `null` — harmless once the null-guard is in place (the string just fails to match real keywords and stays `UNKNOWN`), but `sunlight` also needed an `isinstance(..., list)` guard, since `" ".join(a_string)` iterates it character-by-character instead of raising. **Lesson**: any parser doing `data.get(key, default).method()` on an external API's JSON is one present-null field away from silently losing the whole record — the fix is a one-line idiom change, but it has to be applied at every call site, not just the one a bug report happened to name. Pinned by `tests/unit/test_perenual_client.py` and the new `TestParseSpeciesNullSafety` classes in `tests/unit/test_permapeople_client.py`; a positive control (`git stash` the fix, re-run) reproduced the exact pre-fix `AttributeError` on 18 of the new/extended tests before the fix was restored.

**Available API fields silently discarded, independent of the crash above (issue #296).** The same audit found each client extracting only a fraction of what its API actually returns, with direct, unambiguous mappings to already-existing `PlantSpeciesData` fields going unused. Confirmed live and fixed: Permapeople provides `images.thumb`/`images.title` but the client hardcoded `image_url`/`thumbnail_url` to `""` with a comment claiming "Permapeople doesn't provide images in API" — false, disproven by every one of the 10 test plants returning a populated URL, though 2 of the 10 (Blueberry, Sunflower) turned out to be the same shared blank-placeholder image, not a real photo — the mapping is still correct (Permapeople itself falls back to that placeholder, our client shouldn't invent a distinction it doesn't make), but neither `image_url` nor `thumbnail_url` is currently rendered anywhere in the app for any source, so this stores data with no consumer yet. It also provides a `"Life cycle"` key (`cycle` stayed `UNKNOWN` for every Permapeople plant — a stale comment had guessed the unrelated `"Layer"` design-category field might indicate cycle), `"Height"`/`"Width"` in metres (never reached `max_height_cm`/`max_spread_cm`, so the auto-resize-footprint-to-species-size feature, #213/#218, could never fire for a Permapeople-sourced plant), `"Genus"` (hardcoded to `""`; live-confirmed present on the Apple record, though a broader re-check found it populated on a minority of records overall — still correct to read when present), and `"Soil pH"` (never reached `ph_min`/`ph_max`, so soil-mismatch diagnostics, US-12.10d, never fired for this source). **A `"Soil pH"` record with only one number (e.g. `"6.5"`, not a range) deliberately maps to `ph_min = ph_max = None`, not to that value twice** — the first cut of this fix set both ends to the single value, which collapsed the acceptable band to zero width; `get_mismatched_plants()`'s tolerance is a deliberately tight ±0.05 (see its own comment there), so every real soil-test reading that wasn't that *exact* value produced a false mismatch warning (live-reproduced against Permapeople's actual "Walking onion" record, caught in a second senior-review round). A single number is an optimum, not a band — only a genuine range gives both ends. Permapeople is also third (last) in the fallback chain (`PlantAPIManager.search()` breaks on the first provider to return any results), and Trefle answered all 10 of this audit's test queries — so with a Trefle token configured, none of these Permapeople mappings are consulted either, for a different reason than Trefle's own reachability gap below. **This has real, previously-invisible downstream effects, not just richer data**: `max_height_cm`/`max_spread_cm` now reaching a Permapeople-sourced plant means `plant_species_assignment.apply_species_to_item()` (#213/#218) silently resizes its drawn footprint on assignment where it never did before, and `core/object_height.effective_height_cm()` falls back to species `max_height_cm` when an object type has no built-in default — `TREE`/`SHRUB`/`PERENNIAL` have none, so a Permapeople tree/shrub that previously resolved to `None` (no shadow, no 3D extrusion) now gets a real height and participates in the Phase 14 sun/shade system. Both are the *intended*, correct consequence of fixing the field mapping, not a side effect to guard against — flagged here so it's a known, deliberate change in scope rather than a surprise the next time someone touches either subsystem. Trefle provides `growth.ph_minimum`/`ph_maximum` (near-identical field names to our own, live-confirmed populated on Carrot: 6.5/7.0 — **the first cut of this fix read them from `specifications` instead of `growth` and shipped a hand-written test whose payload matched that mistake rather than the real API, so it passed on broken code; caught in senior review, re-verified against the actual cached live response before fixing** — see the type-design lesson below) and `growth.soil_nutriments` on the same 0-10 scale Trefle's `light`/`atmospheric_humidity` already successfully map to `sun_requirement`/`water_needs` in the same file — `soil_nutriments` -> `nutrient_demand` just hadn't been wired up yet (live-confirmed Carrot: 6, Tomato: 8; Trefle's own docs confirm this is the plant's *demand* — "required quantity of nutriments... how much fertility the species needs" — not a tolerance, so the mapping direction is correct). **Deliberately not mapped**: a nitrogen fixer (legumes) should report `"fixer"`, which the 0-10 scale alone can't express — `specifications.nitrogen_fixation` looked like the natural override, but it's a documented *string* field with an unspecified value domain, and it came back `null` on every one of 46 live legume records sampled in review (Trifolium, Medicago, Vicia, Glycine, Lupinus, Robinia, and others). Mapping a field with no verified populated example — exactly the mistake this entry's own lesson warns about, one field over — was reverted rather than shipped on faith. Trefle's `growth.minimum_temperature`/`maximum_temperature` (°C, live-confirmed populated) could inform `frost_tolerance`, but that field feeds the frost-alert feature (US-12.2) — a wrong threshold policy could suppress a real frost warning, so it needs its own reviewed story rather than riding along with an unrelated field-mapping cleanup. **Known limitation, not fixed here**: Trefle's `search()` endpoint (what every real user search actually calls) returns a sparse payload with none of `growth`/`specifications`/`foliage` at all — live-confirmed on Carrot's search result (only identity/taxonomy fields). Every mapping in this paragraph, and the pre-existing `light`/`atmospheric_humidity`-derived `sun_requirement`/`water_needs` mapping, only ever executes via `get_by_id()`'s richer detail response — and nothing in the application currently calls `PlantAPIManager.get_by_id()` from the search-selection flow. So today, for a plant found via Trefle search, all of this (including the two fields that shipped before this PR) silently stays `UNKNOWN`/`None` regardless of this fix; it takes effect only if a future story wires a detail fetch into species selection. Filed as issue #297 rather than expanded into this fix. **Update**: #297 is now fixed — see the entry above. **Lesson**: when a client wraps a rich external API into a narrow internal model, re-audit the mapping periodically against live responses — comments asserting "the API doesn't provide X" rot silently and are trivial to disprove with one real request; and a hand-written test fixture that encodes the implementation's own (possibly wrong) assumption about a schema's shape will pass on broken code — verify against a captured real response instead. See issue #296 for the full field-by-field table (including what's captured but never surfaced in the Properties/Plant-Details panel, and what's provided by neither API and only ever comes from the bundled 118-species DB).

**A connectivity "Test" probe must fetch the smallest page the API allows, and a swallowed non-credential failure must not be relabeled "check your credentials" (issue #294).** Symptom: the Preferences "Test" button for Permapeople reported "Could not connect to Permapeople. Please check your credentials." for credentials that were valid. Reproduced live against the real API (local `.env` credentials, same request shape the report describes): `PermapeopleClient.search()` (used by real plant lookups) succeeded with a given key/secret while the Test button's only call, `is_available()`, failed every time with that same pair. **Root cause**: `is_available()` called `GET /api/plants?last_id=0` with `timeout=5` to "just check connectivity", but that endpoint's *default* page returns the full first page — measured ~100 records / ~258KB / **6.1–6.4s** against the live API, reliably exceeding the 5s timeout. The resulting `requests.exceptions.ReadTimeout` was caught by `except requests.RequestException: return False` and silently reinterpreted by the dialog as a credentials failure, even though `search()`'s narrower query (a different endpoint, and one already using `timeout=10` rather than the probe's `5`) returned in time. **Fix, two parts**: (1) pass `per_page=1` on the probe request — a documented Permapeople parameter (default/max 100, permapeople.org/knowledgebase/api-docs.html) — measured ~3.2KB / ~0.5–1.0s, well inside the unchanged 5s timeout (measured, not assumed — widening it would only double the worst-case GUI freeze on an unreachable host for no benefit the tiny payload needs); (2) `is_available()` now returns `False` for missing credentials or a definitive rejection (401/403) and **raises** `PlantAPIError` for everything else non-2xx (5xx, 429, …) or a `RequestException` (timeout/DNS/reset) — the first cut of this fix only split out the exception path and left every other non-200 (a Permapeople outage, say) still collapsing to the same `False` as bad credentials, which a second review round caught as the same defect one HTTP status class over; the existing `_test_api` exception handler already shows a distinct "Test Error: …" message for a raised `PlantAPIError`, reusing the existing translated template (no new registered string, though the wrapped exception text itself is raw English, matching the existing `search()`/`get_by_id()` precedent). **Known related risk, left alone pending evidence**: `PerenualClient.is_available()` (`/species-list?page=1`) and `TrefleClient.is_available()` (`/kingdoms`) both still swallow *every* non-200 to `False` the way Permapeople used to — Perenual's endpoint is a similar unbounded-page shape and worth checking first if a similar report comes in; Trefle's returns a handful of records and is a smaller risk either way. Neither was touched here to avoid changing behaviour with no measured evidence backing it. **Lesson**: a "just ping it" health check that reuses a data endpoint inherits that endpoint's *default* response shape, not the minimal one the check actually needs — bound the page size explicitly rather than trusting a timeout to paper over an oversized default; and a health check that conflates every failure mode into one boolean will keep producing wrong-cause error messages one status code at a time until the *type* is fixed, not just the one path that got reported (the same lesson the #291 entry below draws about `agent_api_running_url()` returning `None` for two different causes). Pinned by `tests/unit/test_permapeople_client.py` (bounded page size; `PlantAPIError` raised on both a network timeout and a 503 -- 429 takes the same branch but isn't separately exercised; 401/403 still correctly `False`) and `tests/integration/test_plant_api_test_button.py`, which clicks the real Test button (not just calls `_test_api` directly): a genuine 401 → "Test Failed", a network timeout or a 503 → "Test Error" (distinct from both, proving the false-credentials-accusation is no longer reachable via a slow connection, an unreachable host, *or* a server error). Valid credentials → "Test Successful" is exercised as a control (unchanged since before the fix, not itself a regression pin).

**A windowed PyInstaller build launched with no console has `sys.stdout is None`, and uvicorn's default log config dereferences it — the Agent API was dead in every released exe (issue #291, closed).** Symptom: the Preferences "Enable Agent API" box is ticked, nothing listens on the port, no error dialog appears, and "Connect AI Assistant…" reports *"the Agent API is currently disabled"* about an already-enabled feature. Works perfectly from source. **Root cause**: `console=False` (what we ship) allocates no console, so when the exe is launched detached — a double-click, or `Start-Process` — `sys.stdout`/`sys.stderr` are `None` (**not** unconditionally; see the correction below); `uvicorn.Config.__init__` calls `configure_logging()`, and uvicorn's default formatter does `self.use_colors = sys.stdout.isatty()` (`uvicorn/logging.py`), so `dictConfig` raises `ValueError: Unable to configure formatter 'default'` and the server never starts. **Fix**: pass `log_config=None` to `uvicorn.Config` — we want none of uvicorn's logging anyway (`log_level` and `access_log=False` are already set, the latter deliberately so the `?token=` query param never reaches a log). **Why it hid for six releases, three compounding reasons**: (1) the failure is caught by `_start_agent_api`'s `except Exception` → `logger.exception`, but **no logging handler is configured anywhere in this app**, and with `sys.stderr is None` even `logging.lastResort` is mute — the traceback is destroyed; (2) the only user-visible trace is an 8-second status-bar message; (3) every diagnostic instinct reaches for a `console=True` build, **which has a real stdout and therefore cannot reproduce it** — the observation changes the result. **Lessons**: a frozen-exe check that only asserts "the app survives 8 seconds" cannot see a silently-dead subsystem, which is why `--selftest` now starts the server and asserts it binds — the same reasoning that produced the Qt3D `--selftest` after #277. **Corrected 2026-08-19 (PR #334):** this entry previously said the windowed exe has `sys.stdout is None` *unconditionally*, so `--selftest` reproduced the shipping condition "for free". Measured: it does not. `console=False` means no console is *allocated*, but a redirected handle is still inherited — launched from a shell pipe the frozen exe wrote **~300 bytes to stdout**, so `sys.stdout` was a live pipe and a regression of the `log_config=None` fix would pass. The shipping condition needs **no inherited stdout handle**: launch it detached (`Start-Process -Wait -PassThru`, which is what `release.yml` does and what the gate lists now prescribe). The observation-changes-the-result trap in this very entry had a second storey; and when a UI message explains an absent thing, check whether the absence has more than one cause — `agent_api_running_url()` returning `None` meant both "switched off" and "failed to start", and the copy named only the first.


Hard-won lessons from implementation. Read these before modifying the related subsystems.

- **A background `QThread` with a parent `QObject` aborts the app with `0xC0000409` (`QThread: Destroyed while thread is still running`) on window close (issues #480, #483).**
  Network workers (`UpdateChecker`, `_WeatherFetchWorker`) created with the main window or widgets as parent outlive normal actions when an HTTP request blocks synchronously in `run()`. Closing the window runs Qt's C++ destructor `~QThread()` on the running thread, triggering `qFatal("QThread: Destroyed while thread is still running")`. Python daemon threads do not bypass Qt C++ parent-child destruction.
  **Fix**: Background worker threads must expose `cancel()` and `shutdown(timeout_ms)`. In `shutdown()`, set the cancellation flag, disconnect all signals with `contextlib.suppress(TypeError, RuntimeError)`, call `setParent(None)` to sever the parent-child ownership link, and call `wait(timeout_ms)`. In `GardenPlannerApp.closeEvent`, invoke `shutdown()` on in-flight services before window destruction. Pinned by `tests/unit/test_update_checker.py` and `tests/integration/test_weather_widget.py`.


- **A variable-width widget in a `QToolBar`'s flow reflows Qt's overflow-extension popup and shuffles neighbouring buttons** (sun-sim UX polish, `feature/sun-display-polish`): the sun-simulation toolbar showed a night / no-location **hint** as a `QLabel` added to the toolbar. When the window is narrow the `QToolBar` overflows into Qt's built-in » extension popup, whose widgets wrap into rows; as the time slider crossed sunset the hint toggled empty↔“Night — the sun is below the horizon”, changing the toolbar's width demand, which **re-flowed the popup and bumped the Animate button to a different row** (reported as “the Animate button jumps down a row”). **Root cause**: a state-dependent, variable-width widget living in a toolbar's flow — toolbars don't reflow gracefully, they overflow. **Fix**: render transient sun-sim hints on the **status bar** (`GardenPlannerApp._set_sun_hint` + a permanent `_sun_hint_label`), never on the toolbar, so the toolbar's width is invariant to sun state (also narrows it, easing the overflow). Pinned by `test_sun_hint_on_status_bar_keeps_toolbar_width_stable` (toolbar `sizeHint` identical day vs night).

- **At a trust boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do NOT enumerate exception families** (US-C4 smart symbols, PR #236, found over three senior-review rounds). The smart-symbol library loads user-dropped JSON (`<app-data>/smart_symbols/*.json`). The contract — "a bad user file must never crash the app" — was first enforced by catching `(OSError, JSONDecodeError, ValueError)`. That broke three times in a row, each a different exception family escaping the too-narrow catch: (1) `from_dict`'s dry-run `generate()` raised `ArithmeticError`/`TypeError` (divide-by-zero, `9**9**9` overflow, `round(x, float)`) — none subclass `ValueError`; (2) a deeply-nested expression (`"+".join(["1"]*5000)`) raised `RecursionError` (a `RuntimeError`) *during `ast.parse`*; (3) a non-dict `parameters` entry (`[42]`) raised `AttributeError` in `from_dict`'s **structural** phase, which runs *before* the dry-run and so bypassed `generate()`'s wrapper entirely. Each "fix" added the family that bit it, then re-declared victory — the losing game. The real fix is structural: the **user-file load loop catches `Exception`** (log-and-skip), so *any* failure of `from_dict` on untrusted input is non-fatal **by construction** (`smart_symbol_library.py`); the **bundled** load loop stays narrow (`ValueError`/`OSError`/`JSONDecodeError` → crash-loud) so our own packaging bugs still surface and stay tested. `BaseException` (Ctrl-C/`SystemExit`) deliberately still propagates. Defense in depth: `generate()` also wraps its body in `except Exception → SmartSymbolError` (for the *runtime* regeneration path — param edits, deserialization — which doesn't go through the loader), the evaluator caps AST node count (`parametric_eval._MAX_NODES`) so its recursion surface is bounded, and `from_dict` guards `isinstance(data, dict)`. Rule: when code ingests untrusted data, put **one broad catch at the ingestion seam**; keep narrow typed catches only for trusted/first-party input (where a surprise exception *should* be loud). Enumerating exception families at a trust boundary is a recurring bug, not a safety measure. Pinned by `tests/unit/test_smart_symbol_library.py` (arithmetic/recursion/structural/non-object poison all skipped; malformed *bundled* still crashes loud).

- **Closed (#228): task status now has a single write-path** (US-C2, #188, ADR-029): "is this task done" was originally persisted in **two** stores kept in sync at every chokepoint — the legacy `task_completions` set (read by the calendar dashboard) and the new `task_states` dict (read by the Tasks tab) — with the standing invariant that any new write path had to touch both or the surfaces silently diverged. The convergence (#228) retired that: `set_task_completion` now delegates to `set_task_status` (the single source of truth), and the calendar dashboard reads `effective_status` instead of `task_completions`, so the latter is a **write-only serialized mirror** kept only for `.ogp` forward/back-compat (older binaries still read it). There is now exactly one write-path; no future edit needs to remember the dual-write. Pinned by `test_tasks.py::TestStatusFlows::test_calendar_done_toggle_syncs_task_states` (mirror still maintained) and `test_calendar_task_convergence.py` (both surfaces agree). **The remaining caution:** any surface that reads the shared status store must still derive the `task_id` through the shared `make_calendar_task_id()` + canonical `species_key()` (the ADR-029 PR #227 addendum invariant) — convergence didn't change that.

- **Sidebar list panels must store item *ids*, not live `QGraphicsItem` refs, and defer the selection** (issue #212): `PlantSearchPanel` ("Find Plants") used to cache the live `QGraphicsItem` in each row's `UserRole` and call `setSelected(True)` on it inline. Two problems compounded into "selection works only sometimes": (1) the cached reference goes stale after undo/redo/delete/reparent — `setSelected` then silently no-ops on a detached item; (2) `QGraphicsScene.changed` (very chatty — fires on every repaint, including the repaint caused by selecting) was wired straight to a full `refresh_plant_list()` that `clear()`s and rebuilds every row, so a refresh could destroy the row the user was mid-clicking. Fix: store only the stable `item_id`, resolve the live item at click time via `scene.find_item_by_id(item_id)` (returns `None` → refresh the list and bail, no crash); defer the scene mutation with `QTimer.singleShot(0, ...)` so it runs after the `QListWidget` finishes its own click processing (same pattern as `_on_companion_highlight_species`); and debounce the `scene.changed` → refresh through a single-shot `QTimer` (~150 ms) so the list isn't torn down on every repaint. Single-click uses `view.ensureVisible()` (scroll only if off-screen); double-click uses `view.centerOn()`. General rule: any sidebar list that drives canvas selection must key on ids + defer, never hold graphics-item references across scene mutations.

  **Follow-up (#212 manual-test round 2): debouncing `scene.changed` is NOT enough — the refresh must also skip the rebuild when nothing changed.** The 150 ms debounce only *coalesces* a burst; it still fires once the burst settles and still did a destructive `results_list.clear()` + recreate-every-row. Because *selecting* a plant triggers its own burst (`selectionChanged` → `_update_spacing_overlaps`/`_update_companion_highlights` mutate item visuals → repaint → more `scene.changed`), every selection ended in a full list rebuild — which (a) reset the list's scroll position (symptom: "list jumps back to the top a moment after I stop scrolling" with >5 plants) and (b) destroyed the row the user just clicked, racing the deferred `_apply_selection` (symptom: "single-click sometimes needs a second/third click"). Fix: `_update_results_display` computes a **signature** of the visible rows (ordered tuple of `(item_id, name, species, plant_type)` after sort+search+type-filter) and **early-returns when it equals the last rendered signature** — so a no-op refresh touches neither scroll nor selection. On a real rebuild it captures+restores the scroll value and re-selects the prior row by `item_id` (scroll preserved on scene-driven refreshes; reset to top on user search/filter via a `from_user_input` flag). `family` is excluded from the signature (search-only, never displayed; any family change that alters results already changes membership). Lesson: a debounce limits *how often* you rebuild, not *whether* you needed to — a list driven by the repaint firehose must also be **idempotent** (diff before rebuild) or it will fight the user's scroll and clicks. (The underlying "rebuild the world on every repaint" smell is the same one tracked for the properties panel in #206; the signature guard is a local band-aid, not a structural fix — the firehose still re-queries the whole scene every tick.) Also hardened: row widgets installed via `setItemWidget` set `WA_TransparentForMouseEvents` so a press always hit-tests to the list row regardless of the row widget's child layout.

- **Writing `metadata["plant_species"]` does not repaint the canvas, and a manual `spacing_radius_cm` override masks the database value** (issue #213): the spacing circle's radius comes from `effective_spacing_radius()`, which returns the user override *first* and only falls back to `max_spread_cm/2` from `metadata["plant_species"]`. So a direct `item.metadata["plant_species"] = …` (as several `plant_database_panel` paths did) updates the data model but (a) never triggers `prepareGeometryChange()`/`update()`, so the spacing circle keeps its old size on screen, and (b) is silently overridden on screen by any manual spacing the user set earlier. Contract: route species *assignment* through `PlantDatabasePanel._apply_species_to_item()`, which builds a single undoable `ApplySpeciesCommand` (sets metadata **and**, on *Apply database values*, resizes the drawn footprint to `max_spread_cm` via `CircleItem.set_radius_centered()`, then repaints). The footprint resize is **silent**; the only thing that prompts is a manual `spacing_radius_cm` override that *conflicts* with the database value (Apply → resize + clear override; Keep → leave both). Do **not** wrap live per-keystroke field edits (`_on_field_changed`) in that command — that recreates the per-keystroke undo-churn fixed in #210; there, write metadata directly and just call `prepareGeometryChange()`/`update()` for the repaint.

- **A `scene.changed` slot that touches a `QTimer` must guard against the C++ object being torn down** (#230 CI crash): handlers wired to `QGraphicsScene.changed` that call `self._some_timer.start()` (the soil-mismatch / companion / spacing debouncers) can fire **during widget/app teardown** — the scene still emits `changed` as it is cleared, after the owning view's child `QTimer` has been deleted. Accessing the deleted timer raises `RuntimeError: wrapped C/C++ object of type QTimer has been deleted` *inside a Qt slot*, which Qt/pytest-qt escalates to `Fatal Python error: Aborted` — aborting the whole interpreter (locally it was timing-dependent and passed; on the CI Linux runner it reliably crashed the Test job). Symptom: a test that builds the full `GardenPlannerApp` and mutates the scene passes, then the *next* test errors and the run aborts mid-suite. Fix/contract: every `scene.changed` slot that starts a timer must wrap the `.start()` in `with contextlib.suppress(RuntimeError):` (see `canvas_view._on_scene_changed_for_soil`, `application._on_scene_changed_for_{companion,spacing,plant_search}`). Timers driven by *command/status* signals (`stack_changed`, `task_states_changed`) don't need it — those signals aren't emitted during teardown. **Never connect `scene.changed` to a bare `lambda: self._timer.start()`** — a lambda can't be made teardown-safe.

- **A slot connected to an *application*-global signal (`QApplication.focusChanged`) outlives its widget and must be teardown-safe** (US-C1 PR #235, surfaced merging master's `global_search` into the new full-app harvest tests): `GlobalSearchField` connects `app.focusChanged → self._on_focus_changed` (the popup is a `Qt.ToolTip` that must close when focus leaves) and tried to clean up with `self.destroyed.connect(lambda _: app.focusChanged.disconnect(self._on_focus_changed))`. Two teardown faults: (1) Qt **already** auto-disconnects a destroyed receiver, so the explicit `disconnect` raced to `TypeError: 'method' object is not connected`; (2) because the connection is to the **process-global** `QApplication` (one instance across the whole test session, unlike a per-window signal), a stray `focusChanged` could still invoke `_on_focus_changed` on a field whose C++ object was gone, raising from inside the slot. pytest-qt captures any exception raised in a Qt slot during a test and **fails that test** — so the leak from one test's torn-down window failed an unrelated later full-app test (`test_harvest.py::TestHarvestNavigation`), "passes alone, fails in the full run". Fix: wrap the disconnect in `contextlib.suppress(TypeError, RuntimeError)` and guard `_on_focus_changed`'s body in `try/except RuntimeError: return`. Rule: any handler bound to an app-global Qt signal (`focusChanged`, `applicationStateChanged`, `aboutToQuit`, …) must assume it can fire after its widget is destroyed — make both the disconnect and the slot body teardown-safe; a bare `destroyed`-lambda disconnect is not enough.

- **An enum `QComboBox` that excludes `UNKNOWN` misrepresents missing data as its first option** (issue #231): the `PlantDatabasePanel` characteristic combos (cycle / flower type / pollination / sun / water) were populated with the `UNKNOWN` member skipped (`if item != Enum.UNKNOWN`), and the populate code fell back to `setCurrentIndex(0)` when `findData(value)` missed. So a species whose trait is `UNKNOWN`/missing — common for sparse **online-search** results, where the API clients leave the enum `UNKNOWN` — was silently shown as the *first concrete option* (a tree's lifecycle read "Annual", flower type "Hermaphrodite", etc.). Worse, the save path reads `combo.currentData()` back into the model, so merely viewing then touching the form **rewrote `UNKNOWN` to that wrong concrete value** (silent data corruption). The bundled DB masked it (its records carry full trait data). Fix: prepend a neutral `(self.tr("—"), Enum.UNKNOWN.value)` entry as index 0 (mirroring the existing nutrient-demand combos), so unknown renders as "—" and round-trips as `UNKNOWN`. Rule: any combo bound to an enum with an `UNKNOWN`/unset member must include a neutral entry for it — never let the index-0 fallback assert a specific value. Pinned by `tests/ui/test_plant_database_panel.py`. **Sibling defect, same issue (now fixed):** the dimension/pH/hardiness spin-boxes called `setSpecialValueText("")` — but Qt treats an **empty** special-value string as *disabling* the feature, so the unset sentinel (`value == minimum == 0`, the model's `0 ↔ None` "unknown") rendered as a concrete "0 cm"/"0"/"0.0". A **non-empty** `setSpecialValueText(self.tr("—"))` engages the placeholder (mirrors `properties_panel.py`, `soil_test_dialog.py`, `location_dialog.py`). Purely a display change — populate still does `setValue(x or 0)` and save still reads `value() if > 0 else None`, so `.value()` returns `0` at the dash and the `None` round-trip is unchanged. Rule: a spin-box placeholder needs a **non-empty** special-value text paired with `minimum` as the sentinel; `setSpecialValueText("")` is a silent no-op.

  **Manual-test follow-up (#213): refreshing only the spacing ring was not enough.** The spacing ring is only painted when the item is selected **and** `spacing_r > footprint_radius` (`circle_item.py`); when a generic plant is placed at a footprint larger than the assigned species' spread (the common case — a 5 m placeholder getting a 1.5 m shrub), the ring falls *inside* the footprint and is never drawn, so "nothing resizes on screen" despite the panel showing the new values. The issue explicitly lists **Diameter** among the properties that must update, so *Apply database values* now resizes the **drawn footprint** itself (diameter == `max_spread_cm`, centre fixed) rather than only the ring. Lesson: the visible artefact a user expects to change is the footprint circle, not the (often hidden) spacing ring — reconcile the thing on screen.

  **Second trap (senior review): programmatic resize must keep the rotation pivot on the centre.** A `CircleItem`'s saved position is `pos + center` (see `core/project.py` serialization), with rotation stored as a *separate* angle pivoting on the centre — i.e. the code relies on the invariant `transformOriginPoint == center == rect.center()`. A resize that only keeps the *visual* centre fixed (via `mapToScene` compensation) but forgets to move `transformOriginPoint` to the new centre will save a **displaced** `center_x/center_y` for any **rotated** plant (and make the next rotation jump). It looks correct on screen immediately, so an unrotated test passes green. `CircleItem.set_radius_centered()` therefore calls `setTransformOriginPoint(new_center)` and repositions so `pos + center` stays put; `test_apply_keeps_rotated_plant_centered` pins it. General rule for this codebase: any geometry mutation on a rotatable item must preserve `transformOriginPoint == rect.center()`, and resize-under-rotation needs an explicit rotated-item test.

  **Closed (#219): rotation now pivots about `rect().center()`, not `boundingRect().center()`.** The latent half of the trap above lived in `RotationHandleMixin._apply_rotation()` (`resize_handle.py`), which set the pivot to `boundingRect().center()`. For a plant showing the **antagonist warning badge** that bounding box is expanded *asymmetrically* (`circle_item.py` `boundingRect()` adds `+x/+y` overflow only), so the pivot was off `rect().center()` — breaking the serializer invariant *before any resize*. Because `_antagonist_warning` is **runtime-only (never serialized)**, the save-time pivot (badge on → off-centre) disagreed with the load-time pivot (badge off → centred): a rotated badged plant drifted on save/reload with no resize involved. Fix: pivot about `rect().center()` when the item exposes `rect()` (`CircleItem`/`RectangleItem`/`EllipseItem`), else fall back to `boundingRect().center()` (`TextItem`/`CalloutItem`/`PolylineItem`, which have no asymmetric decoration). This makes the pivot invariant to badge state, so toggling the badge needs no re-rotation. Pinned by `test_rotation_pivots_about_rect_center_with_badge`. Lesson: a rotation pivot must come from the *geometric* shape (`rect()`), never the decoration-expanded `boundingRect()` — runtime-only decorations otherwise leak into persisted geometry.

  **Closed (#218): the interactive resize of a *rotated* item was geometrically incoherent — fix the geometry step, don't post-correct it.** Symptom (PR #221 manual test): drag-resizing a 45°-rotated plant made the diameter collapse / refuse to grow, the centre drifted, the dragged handle didn't track the cursor, and a stale "ghost" disc lingered. Three compounding causes: (a) `CircleItem._apply_resize` squared via `min(width, height)` — at 45° a diagonal drag projects onto **one** local axis (`local_dy≈0`), so `min` picked the *unchanged* axis and the circle could not grow at all (a headless trace showed radius stuck at 50 through an (80,80) drag); a MIDDLE handle (`new_height == init_height`) was capped likewise. (b) `CircleItem._apply_resize` inferred the fixed edge from **scene-space** `abs(pos_x − init_pos.x()) < 0.01` while the first-cut re-anchor inferred it from the **rotated local** `pos_dx == 0` — the two disagreed under rotation, so the re-anchor pinned the wrong corner and the centre drifted (45–135 cm in the trace). (c) neither `_apply_resize` nor the helper called `prepareGeometryChange()`, so a shrinking `boundingRect()` (which includes the spacing-ring expansion) left stale pixels. Fix: the interactive `ResizeHandle._apply_resize` now takes the fixed corner/edge **authoritatively from `self._position`**, computes the new local rect, lets the item normalise it (`CircleItem._constrain_resize_size` squares it so the dragged handle *tracks the cursor* — corner → `max(w,h)`, edge → that axis, which also lets a side handle grow a circle), applies it through `resize_rect_item_keeping_anchor` (which now `prepareGeometryChange()`s and re-pins the origin), and refreshes via `_after_resize_geometry()`. The earlier rotation-gated `_reanchor_after_rotated_resize` band-aid and the `min(w,h)` + scene-space guess are gone. Scope: rect-bearing items (`Circle`/`Rectangle`/`Ellipse`); polygons keep the axis-aligned path (`hasattr 'rect'` gate). The programmatic `_apply_resize(x,y,w,h,pos,pos)` stays for equal-constraint partner resizes. Pinned by `tests/integration/test_rotation_aware_resize.py` ({shape}×{0,45,215°}×{corner,edge}). Lessons: **(1)** every geometry mutation on a rotatable item must end with `transformOriginPoint == rect().center()`, centralised in one helper; **(2)** don't *post-correct* an incoherent geometry step — fix the step (a band-aid over `min(w,h)` + dual fixed-corner inference can't be made correct); **(3)** any code that shrinks a custom `boundingRect()` must `prepareGeometryChange()` or Qt leaves ghosts.

  **Plant sizing precedence now has one home (#218): `core/plant_sizing.py`.** The three sizing quantities (drawn footprint `_radius`, manual `spacing_radius_cm` override, DB `max_spread_cm`) and their precedence (override > `max_spread`/2 > None; ring shown only when effective > footprint) used to be re-encoded inline in `garden_item.effective_spacing_radius()`, `circle_item.paint()`/`boundingRect()`, and `plant_species_assignment.py`. They now all delegate to the Qt-free `PlantSizing` value object / `sizing_for_item` / `db_spacing_radius_cm` resolver. Behaviour is unchanged (pinned by `tests/unit/test_plant_sizing.py` + the existing `test_spacing_circles.py`); the win is that the next person changing "what size is this plant" edits one file. The underlying "rebuild on every repaint" overlap-refresh smell (#206) is untouched.

- **Release workflow race condition with chore commits**: After merging a feature PR, two chore commits are pushed (sync version + mark progress). These land ~37s after the PR merge but the Release workflow building the new tag takes ~2m50s. The chore-commit Release runs start while the tag doesn't exist yet, compute a stale version (e.g., `v1.8.4` instead of `v1.9.2`), and fail with "release with the same tag name already exists". Fixed by adding `if: "!startsWith(github.event.head_commit.message, 'chore:')"` to the release job, which skips the workflow for chore commits.

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.

- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.

- **3-anchor constraints not solved on add**: `_compute_constraint_solve_moves()` in `canvas_view.py` collects `constrained_ids` from `anchor_a` and `anchor_b` only. Any constraint with a third anchor (`anchor_c`, e.g. ANGLE) must also add `anchor_c.item_id` here, otherwise the third item is absent from `item_positions` and the solver cannot move it — showing as red/violated until the user manually drags an object.

- **Live-drag projection tolerance must be sub-pixel** (PR #169 follow-up): `ConstraintGraph.project_to_feasible()` calls `newton_refine()` with a `tol` parameter that gates an early-return *before* projection: `if max_err <= tol: return`. The starting state has `vertex_pos[moving] = desired_scene_pos` (the cursor). At cm-scale `tol` (e.g. 0.5 cm), the cursor near a feasible point falls inside the slack band on most frames of a near-stationary drag, so the function returns the cursor **unchanged** — the moving vertex slips with the cursor up to that band each frame. On a fully-constrained chain (EDGE_LENGTH on every adjacent pair), the slip looks like the entire polyline rigidly translating because the user can only see the moving vertex's position in scene coords. Fix: `project_to_feasible` defaults to `tolerance=1e-4` (sub-render-precision); `solve_anchored` and other full-graph callers retain their cm-scale tolerances. Defensive companion: `newton_refine` now also calls `write_x(x)` on the early-return path so callers always observe a consistent state.

- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

- **Agent API described the compass backwards (issue #267, fixed)**: every Agent API tool description (move/read/spatial/render) called the scene frame "origin top-left, +y down" — Qt's *default* convention, but wrong for OGP, which is CAD Y-up (ADR-002; see the *Canvas Y-axis flip* entry above). Because the scene renders north-up, an agent told "move the bed 7 m south" computed `dy = +700` and the bed moved **north**. The *math* was correct and internally consistent (read + move + spatial all use raw scene y); only the descriptions lied. Fixed by rewriting every agent-facing description to state **origin bottom-left, +x east, +y north (a larger y is further north); to move south, pass a negative dy**. NOT fixed by negating `dy` in the tool — that would desync `move_object` from the read tools it must stay consistent with. The render pixel formula (`px_y = image_height_px - (y_cm - region_y_cm) * px_per_cm`) was already correct (Y-up image, top-down pixel rows) and test-pinned; only its prose was corrected. Regression-guarded by `tests/unit/test_agent_api_auth.py::test_move_object_description_uses_y_up_compass_frame` (the description must say north/south, never "+y down").

- **EDGE_* anchor type instability on polygons/polylines** (TD-007): `_polygon_anchors()` in `measure_snapper.py` classifies each edge as `EDGE_TOP/BOTTOM/LEFT/RIGHT` based on its **current** dominant axis (horizontal vs vertical). This is a dynamic, geometry-dependent label. When a vertex is dragged far enough to flip an edge's dominant axis (e.g. a nearly-horizontal edge becomes nearly-vertical), the freshly-computed anchor type differs from the value stored in the constraint record. `_resolve_anchor_position()` in `dimension_lines.py` then fails on its `(type AND index)` match and falls through to type-only matching, snapping the constraint indicator to the wrong edge. Current workaround: an EDGE_*-aware index-only match block at the top of `_resolve_anchor_position` catches these mismatches before the fallback fires. Long-term fix (TD-007): replace all four `EDGE_*` types with a single `AnchorType.EDGE_MIDPOINT` and use `anchor_index` as the sole edge identity. The edge is always identified by its start-vertex index, not by axis classification, making the anchor stable across all vertex moves.

- **`scene.render()` with negative-height target rect is empty (PyQt6)**: `QRectF(0, H, W, -H).isEmpty()` returns `True`. Passing this as the target to `scene.render()` clips to an empty region — nothing is painted. The correct Y-flip technique is `painter.save(); painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source_rect); painter.restore()`. `H_PIXELS` must be the **image height in pixels**, not the canvas height in cm.

- **`ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`**: When rendering via `scene.render()` (not through a QGraphicsView), `ItemIgnoresTransformations` items render at their natural pixel size regardless of the source→target scale. For a large scene (e.g. 5300 cm) rendered into a small image (774 px), a 10 pt text item can appear as 80+ cm on canvas. Fix: call `ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering and `_restore_text_after_export()` after. The scale = `output_width_cm / canvas_width_cm`.

- **Qt silently drops the mouse grab on `ItemIgnoresTransformations` handles between events (PyQt6)** (#193 follow-up): A handle item that sets `ItemIgnoresTransformations` (all our drag handles — `VertexHandle`, `ResizeHandle`, `RotationHandle`, `RectCornerHandle`, `MidpointHandle`, `CurveControlHandle`) grabs the mouse in its `mousePressEvent`, but Qt loses that grab before the first `mouseMoveEvent` — so the handle receives the press and then *nothing*, and the drag appears inert (symptom: "handle shows but won't move"). **Root cause**: PyQt6 quirk with `ItemIgnoresTransformations` + child-item mouse grab. **Fix/contract**: `CanvasView` re-establishes the grab each `mouseMove`/`mouseRelease` (`if self._active_drag_handle is not None and scene().mouseGrabberItem() is None: self._active_drag_handle.grabMouse()`), but only for handle types it recognises — **every new such handle MUST be added to the `isinstance(grabber, (...))` allow-list in `CanvasView.mousePressEvent`** (grep `_active_drag_handle`). A faithful copy of an existing handle is still dead until the view knows its type. **Testing note**: a hand-built `QMouseEvent` is *not* delivered to an `ItemIgnoresTransformations` child — use `QTest.mousePress/Move/Release` on `view.viewport()` (after `centerOn` the target) for real handle-drag tests. See ADR-025 and the debug-verbose case study.

- **QPdfWriter must use `setResolution(72)` before `setPageLayout()`**: Default QPdfWriter resolution is ~1200 DPI. `painter.viewport()` returns device-pixel dimensions, so all layout math in points (1/72 inch) lands in the top-left corner. Adding `writer.setResolution(72)` makes device pixels equal PDF points and layout coordinates match.

- **`scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins)**: QPdfWriter's painter has a non-identity initial transform from margin handling. The painter pre-flip formula `translate(0, cr.top + cr.bottom); scale(1,-1)` is mathematically correct in isolation but produces wrong output because the initial transform shifts the baseline. Fix: render the scene into a temporary `QImage` (where pre-flip is reliable) then embed with `painter.drawImage(content_rect, img)`.

- **Plant items store center in `boundingRect()`, not in `pos()`**: OGP `CircleItem` and similar types define their geometry in local coords with `pos()` always at (0, 0). `item.pos()` and `item.scenePos()` both return (0, 0). To get the visual center in scene coordinates: `item.mapToScene(item.boundingRect().center())`.

- **SVG pattern tiles appear Y-inverted under painter Y-flip**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. When the scene is rendered with a `scale(1,-1)` painter transform, each pattern tile image is stored un-flipped, but renders upside-down inside the Y-flipped coordinate space. Fix: post-process the SVG after `painter.end()` and add `patternTransform="matrix(1,0,0,-1,0,{tile_height})"` to each `<pattern>` element. See `ExportService._fix_svg_pattern_yflip()`.

- **`QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas**: For texture-filled shapes, Qt emits a "shadow" group containing the polygon `<path>` (`fill="#000000"`) followed by a texture group `<g fill="url(#tex)"><rect x="..." y="..." width="..." height="..."/></g>`. The rect is the *painter's clip bounding rect*, not the polygon shape — and the painter's `setClipPath()` is **never** serialized as `<clipPath>`. In SVG viewers (browsers), the unconstrained rect washes across the whole canvas (often as a brownish overlay if it is a roof-tile texture). PNG export is unaffected because Qt's native renderer applies the clip directly. Fix: post-process the SVG (`ExportService._fix_svg_qt_texture_clipping()`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's `<path>` (preserving its `transform`), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 with a `used_textures` set; forward-window scans match the same texture from multiple shadows and corrupt the XML tree. Validate SVGs in a real browser (`scripts/svg_preview.py` uses Edge headless) — `QSvgRenderer` is too forgiving and hides this bug.

- **DXF Y-axis: scene Y is already Y-up, no negation needed**: OGP scene uses Y-up (scene Y=0 = visual bottom). DXF also uses Y-up. The formula `dxf_y = canvas_h - scene_y` double-flips. Correct mapping: `dxf_y = scene_y`. Similarly for import: `scene_y = dxf_y * scale` (no negation).

- **`QGraphicsScene.changed` only fires on geometry/visibility, not on Python attribute mutations** (issue #173): The 500 ms debounce timer in `CanvasView` that drives `_update_soil_mismatches` is wired to `scene.changed`. Mutating `parent_bed_id` / `_child_item_ids` on a `GardenItemMixin` instance is a plain Python attribute write — no signal, no scene invalidation, no debounce trigger. Any code path that re-parents a plant (drag-and-drop, properties-panel "Unlink", paste, duplicate, future callers) must explicitly call `trigger_soil_mismatch_refresh(scene)` (in `commands.py`), or the warning borders go stale until the next unrelated scene change. Funnel attach/detach through `SetParentBedCommand` whenever possible — it triggers the refresh itself.

- **Plants stack behind beds when both share a layer's default z** — **superseded by issue #338**: A new `CircleItem` and a new `RectangleItem` placed on the same layer both got `z_order * 100` from the layer (typically `0`); with equal z-values, Qt stacked by add-order, so a plant drawn *before* its bed rendered behind it even when correctly attached as a child. The original fix was a one-off `ensure_z_above_parent(plant, bed)` elevation called from every attach site; #338 replaced that band-aid with per-object stacking order (ADR-043, §8.25): `zValue()` is now always **derived** from a persisted sparse rank via `core.stacking.normalize_order()` (`CanvasScene._normalized_layer_order`), which places a plant immediately above its parent bed (and a ROOF_RIDGE immediately above its owner polygon) as a structural clamp — no explicit z bump needed or possible. `ensure_z_above_parent` itself is deleted. Any path that changes a parent link (attach/detach/paste/duplicate/undo) must end with a z refresh — `_refresh_z_after_relink()` for a single item or `CanvasScene._update_items_z_order()` for the whole scene — never an explicit z write.

- **Context-menu wiring must cover all bed-shape item types**: OGP has four independently-implemented item classes for beds (`RectangleItem`, `PolygonItem`, `EllipseItem`, `CircleItem`). Every new context-menu action added to one must be explicitly added to all others — there is no shared base-class hook for context menus. US-12.7 initially missed `PolygonItem` and `EllipseItem`; both were discovered missing during manual testing.

- **Two-tab dialog: OK must not trigger entry-tab validation when user is on History tab**: Dialogs with an Entry tab (add a new record) and a History tab (view/edit past records) share one OK button. If the user is on the History tab and clicks OK to dismiss the dialog, any validation on the Entry tab (e.g. "empty name" warning) fires incorrectly against an empty form. Guard with `self._tabs.currentIndex() == 0` before running entry-tab validation.

- **Two-tab dialog: caller must not create a new record when user clicked OK from History tab**: When the outer dialog returns `Accepted`, the caller (`_open_pest_log_dialog` in `application.py`) must not unconditionally call `AddPestLogCommand`. If the user was on the History tab, edits were already committed via `EditPestLogCommand` inside the dialog; the outer accept is just a close. Add a `has_new_entry` property to the dialog (set in `_on_accept` based on which tab is active) and gate the add-command on it. Same pattern applies to the soil-test dialog.

- **`mousePressEvent` monkey-patch must return None, not the result of `openUrl()`**: Overriding `mousePressEvent` on a `QLabel` instance via assignment works, but the assigned callable must return `None` (C++ void). `QDesktopServices.openUrl()` returns `bool`. A lambda `lambda _e: QDesktopServices.openUrl(...)` forwards that bool, and PyQt6/SIP raises `TypeError: invalid argument to sipBadCatcherResult()` on return. Fix: use a named inner function (implicit `None` return) or add `, None)[1]` to discard the bool.
- **`ThemeColors.get_colors(ThemeMode.SYSTEM)` ignores the user's theme choice**: `apply_theme()` only writes a stylesheet — it does *not* mutate `QApplication.palette()`. So `detect_system_theme()` (called via `ThemeMode.SYSTEM`) probes the OS palette regardless of what the user picked in Settings → Appearance. A user with `theme_mode=LIGHT` running on a dark-default OS will get the dark-mode palette dict for any code that asks "what colors am I drawing on top of?". Fix: always pass the user's preference — `ThemeColors.get_colors(get_settings().theme_mode)`. Only `theme.py` should call `get_colors()` with `ThemeMode.SYSTEM`; every other consumer must read `get_settings().theme_mode`.
- **Excel reads UTF-8 CSV as Latin-1 unless a BOM is present**: A bare `encoding="utf-8"` write produces correct bytes but Excel on Windows still mojibakes German Umlauts (`Tüte` → `TÃ¼te`). Use `encoding="utf-8-sig"` for any CSV the user is expected to open in Excel. Python's own `csv` module strips the BOM transparently on read with either `utf-8` or `utf-8-sig`, so existing tests don't need to change. The BOM byte sequence is `b"\xef\xbb\xbf"` if you need to assert it directly.
- **PyInstaller-frozen exe fails to load Qt3D DLLs on a `PyQt6-3D-Qt6` ↔ `PyQt6-Qt6` micro-version mismatch**: With `PyQt6-Qt6==6.11.0` installed, a `PyQt6-3D-Qt6` wheel of a *different* micro version (e.g. 6.11.1) imports on Windows with `ImportError: DLL load failed while importing … Die angegebene Prozedur wurde nicht gefunden` ("the specified procedure could not be found"). **Root cause**: PyQt6's `Qt3D*` bindings link against the Qt libraries bundled by `PyQt6-Qt6`; a mismatched-micro `PyQt6-3D-Qt6` ships ABI-incompatible DLLs whose exported symbols the bindings can't resolve. **Fix**: pin `PyQt6-3D-Qt6` to the *exact* micro of `PyQt6-Qt6` (both `6.11.0`) — enforced by the declared `PyQt6==6.11.0` + `PyQt6-Qt6==6.11.0` + `PyQt6-3D==6.11.0` + `PyQt6-3D-Qt6==6.11.0` dependencies in `pyproject.toml` (bump all four together); `installer/ogp.spec` names the Qt3D hidden imports so PyInstaller bundles the DLLs. See ADR-038.

  **Recurred as issue #277 — pinning `PyQt6-3D-Qt6` alone was insufficient.** The original fix pinned only the two Qt3D wheels and left `PyQt6>=6.6.0` (hence `PyQt6-Qt6`) free to float. After `PyQt6-Qt6 6.11.1` was published, a fresh CI resolve (`pip install -e ".[dev]"` on a clean runner — the release build has no lockfile) picked `PyQt6-Qt6 6.11.1` next to the pinned `PyQt6-3D-Qt6 6.11.0`, so the *released* v1.24.9 exe shipped `Qt6Core.dll` 6.11.1 against Qt3D DLLs built for 6.11.0 and crashed the process the instant the 3D view was opened. Startup and the 8-s smoke test both passed because Qt3D is imported lazily (ADR-038) — the same class of miss as the US-D1.4 `unittest` exclusion (a lazily-exercised subsystem broken *only in a frozen build*). Fixes (PR #274): (1) pin the **core** Qt runtime too, so all four Qt wheels move together to equal micros; (2) `tests/unit/test_qt3d_version_guard.py` asserts `qVersion() == importlib.metadata.version("PyQt6-3D-Qt6")` so drift fails the fast CI test job (no Qt3D import → safe on the offscreen runner); (3) a `--selftest` mode in `main.py` imports the Qt3D bindings headless, run against the **actual frozen exe** in `release.yml` (a windowed exe launched with no inherited handle has no stdout, so CI reads the exit code via `Start-Process -Wait -PassThru`); (4) `_on_open_3d_view` catches the `ImportError` and shows a recoverable "3D View Unavailable" dialog, and `main.py` installs a `sys.excepthook` backstop — under PyQt6 an unhandled slot exception otherwise aborts the process, silently discarding unsaved work. See ADR-038 (#277 post-mortem).
- **A reused (hidden→re-shown) `Qt3DWindow` renders a blank/white surface (PyQt6 + RHI)**: A 3D viewer window hidden on close and shown again (to avoid destroying a live `Qt3DWindow`) paints nothing on the *second* open — even though the window is exposed, correctly sized, and its scene graph rebuilt. **Root cause**: hiding the window invalidates its render surface, and Qt3D's RHI backend (DirectX on Windows) does not rebuild its swapchain for the re-exposed surface — the backend initializes exactly once (verified: `isExposed=True`, correct size, scene re-built, yet blank). **Fix**: create a **fresh** `Qt3DWindow` on every open (a new RHI surface) rather than reusing one; retire the previous window with `hide()` + `deleteLater()` **at the next open**, where it has been hidden since its close and its render thread is idle — `deleteLater()` in `closeEvent` instead races the still-live render thread and segfaults (access violation, exit 139). See `application.py::_on_open_3d_view` and ADR-038.
- **Key events on a `createWindowContainer`-embedded `Qt3DWindow` don't bubble to the ancestor `QMainWindow` (PyQt6)**: The 3D viewer embeds a `Qt3DWindow` (a foreign `QWindow`) via `QWidget.createWindowContainer`. While it holds keyboard focus, `QKeyEvent`s go to *that window* and are **not** propagated up the widget hierarchy — so a `keyPressEvent`/`keyReleaseEvent` override on the hosting `QMainWindow` never sees them (symptom: Esc/WASD in the walkthrough do nothing once the user has clicked into the 3D scene). **Fix**: install an event filter on the embedded window itself (`adapter.window_handle()`) and read keys there; keep the `QMainWindow.keyPressEvent` override too, for when the main window still holds focus (before the first click into the scene). Also drop held-key state on the window's `FocusOut` — a `KeyRelease` lost to a focus change otherwise strands the input "stuck down." See `ui/view3d/view3d_window.py`, ADR-038.
- **`QFirstPersonCameraController` free-flies (moves along the pitched view vector, no pitch limit, arrows only) — wrong for a ground walk**: Qt3DExtras' first-person controller translates along the full look direction, so looking up lifts the walker off the ground and slows the forward pace by `cos(pitch)`; it also tilts past the zenith unbounded and binds only the arrow keys. **Fix**: use it for mouse-LOOK only — `setLinearSpeed(0)` disables its translation — and drive movement with a custom horizontal loop (`core/walk_camera.walk_step`, a frame `QTimer`, WASD+arrows via the event filter), moving position and viewCenter by the same ground delta so the look direction is preserved; enforce the ±89° pitch limit in a `viewCenterChanged` slot. Qt3D offers no first-class "look without translate" controller. See `ui/view3d/qt3d_adapter.py`, ADR-038.
- **A panel that writes item `metadata` directly reaches neither `scene.changed` nor `stack_changed` — every derived overlay goes stale**: `PlantDatabasePanel._update_instance_metadata` writes `plant_instance` keys (`planting_date`, `current_height_cm`, `current_spread_cm`) straight into `item.metadata` and then calls only `mark_dirty()`. A metadata write repaints nothing, so `QGraphicsScene.changed` never fires; and because the edit bypasses the command manager, `stack_changed` never fires either. `SunShadowController` subscribes to exactly those two. Once US-E8 made `current_height_cm` load-bearing for shadow casting, editing the field left the shadow at the **old** size until some unrelated repaint (changing the selection, say) happened to nudge it — intermittent, which reads as a bug rather than a delay. **Fix**: call `item.update()` after the metadata write, so the existing `scene.changed → schedule_recompute` path runs. **Rule**: if a panel mutates model state that a derived overlay reads, it must emit on one of the two channels overlays actually listen to — `mark_dirty()` alone only *saves* the change, it never *shows* it. Pinned by `tests/integration/test_plant_growth_wiring.py`, which takes its `recompute_count` baseline only after the scene has **settled**: creating the overlay is itself a scene change, so an unsettled baseline makes the assertion pass against the unfixed code (the first cut of that test did exactly that). Note these fields still have no undo — they have never gone through a `Command` (pre-existing).
- **`ShoppingListItem.id` must encode the display unit when units auto-promote**: `ShoppingListService._collect_materials` promotes amendment quantities from g to kg once the cross-bed total crosses 1000 g. Because user-entered prices in `ProjectData.shopping_list_prices` are keyed by `id`, the id must capture the unit (`amendment:<aid>:g` vs `amendment:<aid>:kg`) — otherwise a price entered when the row was 800 g silently re-binds to the same row when it later weighs 1.2 kg, multiplying the apparent total by 1000×. Use the locale-stable suffix (`g`, `kg`) — never the translated `_tr()` string — so the id is identical across English/German runs.

- **Bed-only features must NOT be hand-coded into each shape item**: Bed-capable shapes are four classes (`RectangleItem`, `PolygonItem`, `EllipseItem`, `CircleItem`). When a new bed-only action (soil test, pest log, succession plan, future ones) is added to only one shape's `contextMenuEvent`, the feature is invisible on the other three. Recurred twice: pest log missing from PolygonItem/EllipseItem until #173; succession plan missing from all three non-rectangle shapes until the US-12.8 post-bug fix. Mitigation: bed actions are now built and dispatched centrally via `GardenItemMixin.build_bed_context_menu` + `dispatch_bed_action`, gated by a parametrised regression test (`tests/integration/test_bed_context_menu.py`) that iterates over all four shape classes. See ADR-017 and § 8.14. **When adding a new bed feature, extend the parametrised test with one new `assert actions.<new_field> is not None` line per shape — that single addition is what blocks future regressions.**

- **`painter.drawText()` inside `QGraphicsItem.paint()` renders upside-down on the Y-flipped canvas**: The view applies `scale(zoom, -zoom)` for the CAD-style bottom-left origin (ADR-002). Text drawn directly inside a `paint()` method inherits this flip and appears mirrored. Symptoms: badge text reads as mirror image; positioning using `rect.bottom()` lands at visual *top* and vice versa. Fix: use a child `QGraphicsSimpleTextItem` (or a custom `QGraphicsItem` subclass) with the `ItemIgnoresTransformations` flag — Qt then draws the item in its own non-flipped pixel-coordinate system. Examples: bed name labels (`_label_item` in `garden_item.py`), succession badge (`SuccessionBadgeItem` in `garden_item.py`), compare-mode overlay labels (`canvas_scene.py`). Anchor at `rect.top()` (smallest scene-Y = visual bottom after flip) and extend the bounding rect upward (negative local Y) so the badge sits inside the bed.

- **NEVER use PowerShell `Set-Content -Encoding UTF8` for files containing non-ASCII characters**: PowerShell 5.1's `Get-Content -Raw` auto-detects encoding but mis-guesses UTF-8-without-BOM as Latin-1; the subsequent `Set-Content -Encoding UTF8` then writes those mis-decoded characters back as UTF-8 with a BOM, **double-encoding every umlaut** (`ö` → `Ã¶`, `ß` → `ÃŸ`, `ä` → `Ã¤`, etc.). Symptom: the entire German UI displays as mojibake after a "harmless" find/replace. Trigger in this codebase: doing in-place text replacement of `Anbauerfolge` → `Anbaufolge` in `scripts/fill_translations.py` and `open_garden_planner_de.ts`. Recovery: `git checkout HEAD -- <files>` and redo the edit with Python (the `Edit` tool, or a small script using `open(..., encoding="utf-8")`). For multi-file bulk replacements use Python, `sed -i.bak`, or `perl -i -pe` — anything but PowerShell. Detect a regressed file fast with `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — any non-zero count means double-encoded.

- **`test_german_ts_has_no_unfinished` does NOT catch hardcoded English strings in source code**: The i18n test only verifies that every string *already extracted into the .ts file* has a German translation; it cannot see strings that bypass `tr()` / `QT_TR_NOOP` / `QCoreApplication.translate(...)` entirely. Symptom: registering a German translation in `scripts/fill_translations.py` doesn't make the string translate in the running app, because the source-code call site still writes a plain Python f-string / dict literal that pylupdate6 never picks up. Concrete failures in this codebase: module-level `_SEGMENT_LABELS = {"early_spring": "Early Spring", ...}` dict was looked up directly with `_SEGMENT_LABELS[key]` in three places — the strings were registered in fill_translations.py but the dialog displayed the raw English. The fix pattern: wrap dict literals with `QT_TR_NOOP` and translate at lookup time, OR add a thin helper like `_segment_label(key)` that calls `QCoreApplication.translate("Context", english)`. Also: `f"{a} overlaps {b}: antagonist"` looks like a translatable sentence but never reaches Qt Linguist because `tr()` is not on the path; use `self.tr("...").format(...)` instead. Mitigation: `tests/unit/test_i18n.py::TestNoHardcodedEnglish` greps a curated list of suspicious phrases (e.g. ` overlaps `, ` antagonist`, `Early Spring`, `Late Spring`) against the source tree — if any match is outside a `tr()`/`QT_TR_NOOP`/`translate()` call, the test fails. The list grows whenever a hardcoded string slips through user-visible testing.

- **`tr()` + `.format()` is a silent no-op on a Qt positional `%N` literal** (US-D3.1, issue #319): three strings in `CompatibleSetDialog` were written `self.tr("Already in bed: %1").format(plants=...)` / `"keeps all %1 already planted".format(count=...)` / `"keeps %1 of %2 already planted".format(count=..., total=...)`. `str.format()` has no `%N` field, so it returned the string **unchanged** — the dialog showed the literal text `Already in bed: %1` and every coverage count was raw, on the most-repeated string in the dialog. Two compounding failures, both invisible to CI:
  1. **The value was never displayed.** No exception, no warning — just a missing value.
  2. **The string was never translated.** The registered keys in `scripts/fill_translations.py` are in `{named}` form (`"Already in bed: {plants}"`), so the `%1` code literal matched no `.ts` entry at all. The German dialog was a mix of translated and untranslated rows. `test_german_ts_has_no_unfinished` was **structurally blind** to this — it only inspects messages *already in the table*, and a `tr()` literal that never gets extracted is by definition not in the table. This is the sibling of the entry above: that one is "the string never reached `tr()`"; this one is "the string reached `tr()` but the literal does not match the registered key".

  **The invariant is about the PAIRING, not the placeholder.** `%N` is correct — and used correctly at `companion_panel.py:96` — when interpolated with `.replace("%1", value)`; `{named}` is correct when interpolated with `.format()`. Crossing the two is broken in both directions, silently. Rule: **pick one idiom per call site and keep the whole project on `{named}` + `.format()`**, since that is what `fill_translations.py` registers and what every other new string uses. Mitigation: `tests/unit/test_dialog_i18n_literals.py` extracts the `tr()` literals and their interpolation method from the source with `ast` (so implicit string concatenation is read the way Python reads it, and the list cannot drift when a string is reworded) and fails on any mismatch, on any dialog literal absent from the German `.ts`, and on any literal registered with its own English text as the translation. A companion test in `tests/unit/test_companion_panel_sets.py` asserts on the **rendered** widget text that no `%N` reaches the user *and* that the interpolated values actually land — the second half matters, because a no-placeholder check alone also passes on a dialog that simply dropped the information. Both were mutation-verified: reverting to `%1`, crossing to the mirror-image `{named}`+`.replace()`, and unregistering a literal are each caught.
  **Also**: German rendering is worth checking directly, because it is the only place both failures are visible at once. `QTranslator` + the compiled `.qm` renders the fixed dialog as `Bereits im Beet: corn, bean` and `behält 1 von 2 bereits gepflanzten` — translated *and* interpolated. A green suite in the source language proves neither.

- **A repeated top-level key in the `TRANSLATIONS` literal of `scripts/fill_translations.py` silently shadows the earlier block, and the i18n gate cannot see the strings it drops** (issue #393 / audit 2026-10 AUD-029): Python keeps only the last of a repeated dict key, so five contexts (`CircleItem`, `EllipseItem`, `PolygonItem`, `RectangleItem`, `PdfReportService`) were each defined twice and the first block's 62 strings never reached the effective registry — 57 survived only because an earlier fill run had already written them into `open_garden_planner_de.ts`, and the remaining 5 (`PdfReportService` "Garden Notes", "No journal notes recorded.", "(no date)", "(empty)", "(photo: {filename})") were live `_tr()` calls in `services/pdf_report_service.py` with no German entry, so the opt-in journal-notes PDF page printed English. `test_german_ts_has_no_unfinished` is structurally blind: it only inspects messages *already in the table*, and a string the registry never emits is by definition not there. The only detector is `ruff` F601, and CI ran `ruff check src/` only — `scripts/` was never linted. Fix: merge each shadowed block into its surviving block, run the fill/compile pipeline, and enforce uniqueness with `tests/unit/test_i18n.py::TestTranslationRegistry::test_translations_literal_has_unique_top_level_keys` (an `ast` parse of the literal, independent of lint scope) plus a CI lint step widened to `ruff check src/ tests/ scripts/`. Rule: a registry that can silently drop its own entries needs a uniqueness test, not only a lint rule.

- **A shared, Qt-free service that renders a bilingual data field must resolve the active UI language explicitly; a `lang="en"` default is a silent English leak** (issues #408, #410): `models/amendment.py::Amendment.display_name` and `services/companion_planting_service.py::get_display_name` both default `lang="en"`, and two call sites omitted it — `services/task_generator.py::_bed_amendment_recs` (generated soil-amendment task titles) and `services/companion_sets.py::suggest_companions` (the agent `suggest_companions` tool's `name`). The GUI showed German (the panels pass `lang`), the task/agent surfaces showed English, and the D3 convention that display strings follow the user's UI language (`docs/08-crosscutting-concepts/` §8.19) was violated. The zero-unfinished gate cannot see either: both are data-selected strings, not `tr()` output. Fix: one shared resolver, `app/settings.py::active_language()`, used by the task generator and the companion-set finder (the two pre-existing private helpers now delegate to it). **The task-id trap is the load-bearing part**: `generate_soil_amendment_tasks` builds `task_id=f"soil_amendment:{bed_id}:{name}"` from the English data name, and `ProjectData.task_states` keys saved done/snooze state by it — localising `name` would have changed every id and orphaned that state. The fix carries both names in `BedInput.amendment_recs` as `(stable_name, display_name, rationale)`: the id uses `stable_name`, the title uses `display_name`. Pinned by `tests/integration/test_agent_task_soil_tools.py::TestSoilReads::test_generated_amendment_task_title_follows_the_ui_but_id_does_not`, `tests/unit/test_task_generator.py::TestSoilAmendmentTasks::test_display_name_in_title_stable_name_in_id`, and `tests/unit/test_agent_d3_localisation.py::test_companion_name_follows_the_ui_while_the_key_stays_english`. Rule: when a display string doubles as a persisted key, localising it is a data migration — separate the machine key from the display text first.

- **Layer subsystem: panel is a pure view; ALL mutations go through undoable commands** (issue #201 + layer-undo fix): historically `LayersPanel` mutated layers directly and `panel._layers` *aliased* `scene._layers` (the scene hands its live list to `panel.set_layers()`), so panel-side inserts mutated the scene before any signal fired — and none of it was undoable (Ctrl+Z silently ignored every layer action). Both are fixed: `LayersPanel.set_layers` now stores a **defensive copy** (`list(layers)`), and every layer operation (add, delete, rename, reorder, visibility, lock, opacity) routes panel request-signal → `GardenPlannerApp` handler → `CommandManager.execute(<LayerCommand>)` → scene mutation → `layers_changed` → `panel.set_layers` rebuild. Rules for any new code touching this subsystem: (1) the panel must NEVER mutate `Layer` objects or its `_layers` list — emit a request signal and let a command in `core/commands.py` (`AddLayerCommand`, `DeleteLayerCommand`, `RenameLayerCommand`, `ReorderLayersCommand`, `SetLayerPropertyCommand`) do the work; the rebuild repaints the widgets. Emit as the **last** statement of a `LayerListItem` handler — the synchronous command → rebuild deletes the emitting widget. (2) `_refresh_list` restores selection by **layer id**, never row index — a top-insert shifts every row down one. (3) Undo of add/delete restores the previously active layer by calling `set_active_layer` **last**, after `layers_changed.emit()` — the panel rebuild's fallback `setCurrentRow(0)` fires first and would otherwise win; the scene's `active_layer_changed → panel.select_layer` connection (signal-blocked) re-syncs the visible selection. (4) Opacity slider drags coalesce into one undo step: `valueChanged` while `isSliderDown()` drives the non-undoable `scene.preview_layer_opacity()` (no `layers_changed`, so no rebuild storm per tick); `sliderReleased` commits one `SetLayerPropertyCommand` carrying the opacity snapshotted at `sliderPressed`. (5) `CanvasScene.add_layer()` *appends* (bottom) and is for bulk/import only (DXF); `CanvasScene.remove_layer()` is likewise a non-undoable primitive — neither is the user-facing path. (6) Command `description` strings are user-visible (status bar "Undo: …") and use `QCoreApplication.translate("Commands", …)` + registration in `scripts/fill_translations.py`. (As of issue #209 **all** command descriptions — not just the layer ones — use this pattern; the former English f-strings have been migrated, including the caller-supplied descriptions of `AlignItemsCommand`/`MultiVertexMoveCommand`, which are wrapped at their call sites in `canvas_view.py`/`properties_panel.py`.)

- **Undoable layer preconditions must be revalidated on redo** (US-D2.4): `DeleteLayerCommand` originally checked its replacement layer's lock only in `__init__`. The sequence delete → undo → lock replacement → redo then bypassed the protection because redo re-executed the existing command. The command now checks immediately before mutation, and `CommandManager.redo()` restores a refused command to the redo stack. Regression: `tests/unit/test_commands.py::TestDeleteLayerCommand::test_redo_refuses_newly_locked_replacement_and_preserves_redo`. General rule: mutable protections belong at every mutation boundary, including redo; constructor validation is not enough.

- **`QLineEdit` ignores Return — Enter bubbles to the canvas and finalizes the active tool** (Package A US-A4): `QLineEdit.keyPressEvent` calls `event.ignore()` for `Key_Return`/`Key_Enter` so a parent (typically a dialog's default button) can pick it up. Inside the Dynamic Input overlay this means the Enter that committed a typed coordinate then propagated to `CanvasView.keyPressEvent`, which delegated to `PolylineTool.key_press` and triggered `_finish_polyline()` whenever the tool already had ≥2 vertices. Symptom: every typed `@500,0` Enter placed the vertex correctly, then immediately closed the polyline — you could only ever draw one segment via the overlay. Fix: `_DynamicLineEdit.keyPressEvent` now intercepts Return/Enter explicitly, drives commit (or empty-Enter finalize) via the overlay, and calls `event.accept()` so the Enter never reaches the canvas. Same trap will bite any future QLineEdit-derived widget hosted inside a `QGraphicsView` viewport — if the parent acts on Return, intercept it at the line edit.
- **Dynamic Input overlay must freeze while the user is typing** (Package A US-A4): The overlay floats next to the cursor with a fixed `(+18, -42)` offset and was originally re-positioned on every `mouseMoveEvent`. The user could never reach it with the mouse — every step toward the fields shifted them further along the cursor vector. Equally bad, naked keystrokes on the canvas didn't reach the overlay because canvas focus owned the keyboard. Fix: `DynamicInputOverlay.is_capturing_input()` reports True iff either field has non-empty text; `CanvasView._update_dynamic_overlay` skips `show_near` while that is True; `CanvasView.keyPressEvent` routes bare coord characters (`0-9 . , ; @ < + - space`) into the overlay's distance edit via `forward_keystroke` before the tool-shortcut dispatch. After commit, fields are cleared (via `_on_buffer_text_changed("")`) so the overlay flips back to tracking. Pitfall variant: do NOT base `is_capturing_input` on focus alone — focus may legitimately sit on the field after commit while the buffer is empty, and the overlay should resume tracking in that state.

- **Grid snap silently overrides anchor snap unless `CanvasView.snap_point` short-circuits** (Package A, ADR-020/021): Every drawing tool calls `self._view.snap_point(scene_pos)` inside its own `mouse_press`/`mouse_move`/`mouse_release`. The `CanvasView` dispatcher (`_maybe_apply_anchor_snap`) snaps the scene_pos to a midpoint/intersection/endpoint candidate *before* dispatching to the tool — but the tool's own `snap_point` call then rounds that anchor-snapped coordinate back to the nearest grid line (e.g. an edge midpoint at (175, 100) becomes (200, 100) on the default 50 cm grid). With grid snap on (the default), the new Package A snap modes silently lose. Symptom: midpoint/intersection glyph appears on hover but the committed vertex lands on a grid line, not the visible anchor. Root cause: anchor-snap and grid-snap are independently applied by two unrelated layers without composition rules. Fix: `CanvasView.snap_point()` short-circuits the grid rounding step when `self._current_snap is not None`. Anchor snap always wins on the click path; the bounds clamp still runs. Regression test: `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap` (uses a 350×100 rect with a midpoint at (175, 100) — deliberately not on the 50 cm grid). The single short-circuit site keeps this an explicit invariant rather than a side-effect of call ordering — if you find yourself adding a third snap layer, add an explicit composition rule before merging.

- **Never default a file dialog into the install directory; never let the uninstaller wipe it blind** (issue #199): Two independent bugs combined to destroy user data on Windows. (1) `QFileDialog.getSaveFileName`/`getOpenFileName` called with `""` as the *directory* argument open in the process **current working directory** — for a packaged build that is `C:\Program Files (x86)\Open Garden Planner`, so users naturally saved `.ogp` plans inside the install folder. (2) The NSIS uninstaller ran `RMDir /r "$INSTDIR"` and the upgrade path (`.onInit`) silently invokes that *old* uninstaller before installing the new build — so every "update" deleted the whole install dir, user plans included. Symptom: "all my gardens vanished after updating." Fixes, both required: app side — `GardenPlannerApp._default_dialog_dir()` resolves every save/open/export dialog to the open project's folder or `<Documents>/Open Garden Planner` (`app/paths.get_projects_dir()`), never CWD; installer side — the uninstall section copies any top-level `$INSTDIR\*.ogp` to `$DOCUMENTS\Open Garden Planner\Recovered Plans` *before* `RMDir /r`, so even pre-existing victims keep their data on the next upgrade. Lesson: user data must never live under `$INSTDIR`, and an installer must treat `$INSTDIR` as possibly containing user files. Regression tests: `tests/unit/test_paths.py`, `tests/integration/test_save_location.py` (the NSIS half is Windows-only, verified manually).

- **Undo/redo must dirty the document — and so must every "already-applied" edit; route them all through one chokepoint** (issue #209): `CommandManager.execute()` emits `command_executed`, but `undo()`/`redo()` historically emitted only `can_undo_changed`/`can_redo_changed`. Because `mark_dirty` was wired to `command_executed` ([application.py](../../src/open_garden_planner/app/application.py)), undoing or redoing after a save left the title bar's `*` marker (and the close-time "unsaved changes" prompt) believing the document was clean — closing then **silently discarded** the change. Repro: draw → save → Ctrl+Z → title shows no `*`, close prompts nothing. Fix: a dedicated `stack_changed` signal on `CommandManager` (emitted by `execute`/`undo`/`redo`, **not** `clear()` — clearing happens on new/load and must stay clean) wired to `mark_dirty`. A dedicated signal, not "also emit `command_executed` from undo/redo", because the constraints/properties/dimension-line refreshes are *already* separately wired to `can_undo_changed`/`can_redo_changed` (firing `command_executed` too would double-fire them) and the calendar refresh would newly fire.

  **The trap that made this a two-part fix:** `command_executed` was *load-bearing* for dirtiness far beyond `execute()`. ~30 interactive-edit sites across `canvas_view.py`, `properties_panel.py`, `garden_item.py`, and the item modules (`resize_handle.py`, `circle_item.py`, `rectangle_item.py`, `ellipse_item.py`, `polygon_item.py`, `polyline_item.py`) use the "move already applied, just register undo without re-executing" pattern: they reached into `cm._undo_stack.append(cmd)` directly and hand-emitted `command_executed` to mark dirty. Moving `mark_dirty` to `stack_changed` un-dirtied every one of them (drag a resize handle / vertex / edit a radius → no `*`, close discards). Naively the new integration test still passed because it only exercised the `RectangleTool` → `execute()` path. Real fix: a single `CommandManager.register_applied(command)` chokepoint that does the append + redo-clear + **all** signal emits (including `command_executed` *and* `stack_changed`); every former direct-append site now calls it. Lesson: there must be exactly **two** ways onto the undo stack — `execute()` (runs the command) and `register_applied()` (command already applied) — and both emit the full signal set. Never hand-roll `_undo_stack.append` at a call site; the moment you change what `execute()` emits you create silent contract drift with every copy. Regression tests: `tests/integration/test_undo_redo_dirty.py` covers both an `execute()` path *and* a `register_applied` resize path.

- **Properties panel updates incrementally — rebuild only on a genuine selection/structure change** (issue #206, supersedes the #200 focus-guard workaround): `PropertiesPanel.set_selected_items` used to rebuild the entire form (`_clear_form()` → `removeRow` everything → recreate) on *every* call, and it is called for *any* command via `command_executed`/`can_undo_changed`/`can_redo_changed` ([application.py](../../src/open_garden_planner/app/application.py) wires all three to a deferred `_update_properties_panel`). Live-editing fields that fire on every keystroke — the **Name** `QLineEdit` and **Text Content** `QTextEdit` — therefore tore down the form *while the user typed in them*, destroying the focused widget and dropping focus + caret after every character ("the plant name field loses focus after each keystroke", #200). The #200 fix was a focus guard (skip the rebuild while a panel editor holds focus), but that guard accreted whitelisted widget types and traded a stale view under focus. **#206 fixes the root cause:** `set_selected_items` now computes a structural **identity** (`_compute_identity`: item id + class + `object_type` + the bed's `child_item_ids` / a plant's `parent_bed_id`, which drive *which* fields and read-only summary rows exist, **plus** `_relationship_summary_key` — the rendered *text* of the Parent Bed / Contained Plants rows. Those rows show a **related** item's name; the id set alone does not catch a rename/undo of that related item while the current item stays selected, which would leave the summary stale on the refresh path since no refresher covers a variable-row summary list. `id(item)` is load-bearing: it is correct only because commands mutate the selected item in place and reuse the same object across undo/redo — a command that swaps the object for the same selection must add a discriminator). When the identity is unchanged — a pure scalar property edit, a canvas drag/resize, or undo/redo on the same item — it keeps the widgets alive and pushes fresh model values into them via the registered field **refreshers** (`_register_refresh` appends a closure next to each widget's creation; `_refresh_field_values` runs them all). Each refresher **skips a focused widget** (`_is_focused`) and writes under `blockSignals` so a value push never registers a command or stomps an active edit. The form is rebuilt only on an identity change (different/multi/empty selection, type change, reparent). The old focus guard at the top of `set_selected_items` is **kept as a defensive backstop** for the rare "selection genuinely changed while a field holds focus" rebuild — it is no longer load-bearing for the common case, so new live-editing fields no longer have to be whitelisted in it. **A naive "skip the rebuild when the selection is unchanged" was rejected** because it would leave Position/Size/colour showing stale values after a canvas drag or undo/redo; the refresh path is what keeps them correct. Lesson: any new editable field added to this panel must register a refresher (`_register_refresh(widget, lambda: widget.set…(read_model()))`) so its value stays in sync without a rebuild; any new field whose presence depends on a model relationship must be folded into `_compute_identity` so that relationship change forces a rebuild. **A combo whose *item list* (not just its selected index) is backed by mutable external state must repopulate that list in its refresher, not merely re-index** (#222 senior-review P1): the **Layer** combo reads `scene.layers`, and a re-index-only refresher left a renamed layer showing its old name / omitted a newly-added layer on the refresh path — its refresher now `clear()`s + re-`_populate_layer_combo()`s under `blockSignals` (`_refresh_layer_combo`). Object-type/style/pattern combos are enum-backed (fixed list) so a re-index is sufficient there. Regression tests: `tests/integration/test_properties_panel_incremental.py` (no-rebuild-on-same-selection, value refresh after move/resize/undo/redo, rebuild on selection change, refresher skips focused widget, **read-only summary rows stay fresh on a related-item rename/undo**, **Layer combo repopulates on a layer rename/add**) and `tests/ui/test_properties_panel.py::TestFocusPreservation`. The unguarded sibling `plant_database_panel.set_selected_items` (which already uses persistent widgets) got a matching defensive `_holds_field_focus()` backstop: it skips the value re-push when called for the already-displayed item while one of its own fields holds focus.

  **Follow-up (#206 wiring): the panel refreshes are driven by a single `stack_changed` connection, not the three-signal fan-out.** #222 fixed the panel *internals* but left the `application.py` wiring as `command_executed` + `can_undo_changed` + `can_redo_changed` → a deferred `_update_*` (three fan-outs per command; `constraints_panel.refresh()` actually ran up to 3× since it isn't `singleShot`-coalesced). They now collapse to one `cmd_mgr.stack_changed.connect(...)` per panel (`stack_changed` fires exactly once per `execute`/`register_applied`/`undo`/`redo`, never on `clear()`); `can_undo/redo_changed` stay wired **only** to the toolbar Undo/Redo action enablement (their real job). **No undo/redo coverage is lost in the swap:** the constraints and properties panels already refreshed on undo/redo via `can_undo/redo_changed` (those `pyqtSignal`s are emitted unconditionally on every `undo()`/`redo()` in `commands.py`, *not* only when the boolean flips), so moving them to `stack_changed` is behaviour-preserving for those two. The genuinely *new* fix is the **plant-database panel**: it was wired only to `selectionChanged` / `object_type_changed` (never to any command signal), so undoing/redoing a species assignment while the plant stayed selected left its species details stale until reselection — it now also hangs off `stack_changed`. Regression test: `tests/integration/test_panel_refresh_wiring.py` (one refresh per panel per execute/undo/redo, incl. the plant-DB undo/redo coverage, plus toolbar enablement intact). **Closed (#225):** the three stragglers — `calendar_view.refresh()` wired to `command_executed` only (so off undo/redo), and the companion / crop-rotation panels wired `selectionChanged`-only — are fixed. Companion + crop-rotation now also hang off `cmd_mgr.stack_changed` (cheap list rebuilds). The calendar gained a debounced `schedule_refresh()` that skips work while its tab is hidden (so the heavyweight `refresh()` that #210 flagged can safely be wired to `stack_changed` + `task_states_changed`); `_on_tab_changed` still refreshes it on show. Regression test: `tests/integration/test_panel_refresh_wiring.py::TestCompanionCropRotationRefreshOnUndoRedo`.

- **Free-text property fields commit on a debounce, not per keystroke — and not on focus-out alone** (issue #210): the Properties-panel **Name** (`QLineEdit`) and **Text Content** (`QTextEdit`) fields originally registered a `ChangePropertyCommand` on every `textChanged`. Typing an N-char value pushed **N** undo entries (Ctrl+Z walked back one character at a time) and — once #209 routed these through `register_applied` → `command_executed` — fired **N** heavyweight `calendar_view.refresh()` calls (propagation plans + Gantt + dashboard + `weather_widget.set_location()`), thrashing the calendar tab once per keystroke when a GPS location was set. Fix: split **live-apply** from **commit**. `textChanged` updates the item live for visual feedback only (no command, guarded by `_updating`) and (re)starts a single-shot **debounce timer** (`_TEXT_COMMIT_DEBOUNCE_MS`, stored on the widget as `_ogp_commit_timer`); the single command is committed when the timer fires (typing pause) **or** on focus-out (`editingFinished` / the `FocusOutTextEdit` subclass's `editing_finished`, which adds the signal QTextEdit lacks), whichever is first. The start value captured at field-build time (`_ogp_name_start` / `_ogp_content_start`) is compared on commit, so an unchanged commit — and the debounce-then-focus-out double fire — push nothing. **Why the debounce and not focus-out alone** (manual-test finding): the Edit→Undo `QAction` (Ctrl+Z, `WindowShortcut`) is `setEnabled(False)` until `can_undo`, and shadows the focused QLineEdit's own undo. With a focus-out-only commit, pressing Ctrl+Z *while still editing* found an empty stack → the action was disabled → Ctrl+Z was a silent no-op and the live-applied value "stayed." The debounce makes a command exist shortly after the user stops typing, so mid-edit Ctrl+Z works. **The debounce introduces a second trap — flush before rebuild**: `set_selected_items` rebuilds the whole form (`_clear_form` → `removeRow`), which deletes the field **and its child debounce timer synchronously**. If a debounce is still armed when the selection changes to another item (focus already off the field, so the #200 guard does not block the rebuild), the timer is destroyed before it fires — the edit was live-applied to the model but never recorded as a command, silently lost from undo. Fix: every field with a debounce registers its commit callback in `self._pending_text_commits` (via `_attach_commit_timer`), and `set_selected_items` calls `_flush_pending_text_commits()` *before* the rebuild, while the widgets are still alive. Each commit is idempotent (no-op when unchanged) so flushing on every rebuild is safe. Lesson: any new free-text field on this panel must follow the live-apply-on-`textChanged` + debounce/focus-out-commit pattern (never one command per keystroke, never focus-out-only), **and** route its commit through the flush queue so a cross-item rebuild cannot eat a pending edit. Regression tests: `tests/integration/test_properties_text_edit_undo.py` (`test_debounce_commits_without_focus_out`, `test_pending_edit_flushed_when_selection_changes`).

- **`QSettings.setDefaultFormat()` / `setPath()` are process-global statics Qt never reverts — never call them from a test** (test-suite isolation): a test fixture in `tests/unit/test_ui_state.py` redirected `UiStateStore`'s settings to a temp INI file by calling `QSettings.setDefaultFormat(IniFormat)` + `QSettings.setPath(IniFormat, UserScope, tmp_path)`. Those are **static, process-wide** and are *not* auto-reverted (the `monkeypatch` arg was declared but unused). After that unit test ran (~⅔ through the suite), the global default format pointed at a `tmp_path` pytest had since deleted, so **every** `QSettings`/`AppSettings` constructed *later in the session* — the `get_settings()` singleton behind the snap-toggle handlers and the welcome dialog — wrote to a dead path and every getter fell back to its coded default. Symptom: 6 settings-persistence tests (`test_anchor_snap`, `test_nearest_snap_workflow`, `test_perpendicular_snap`, `test_tangent_snap`, `test_welcome_dialog`) **fail only in the full run, pass in isolation, and CI stays green** (different collection order/platform dodges the poison). The uniform tell: every failing getter returns exactly the *default* value, i.e. the setter write never persisted. Fix: isolate by `monkeypatch.setattr("open_garden_planner.app.settings.create_qsettings", <factory returning QSettings(ini_path, IniFormat)>)` (auto-reverts, touches no global state) — never the global statics. *(Recipe updated by #285: `ui_state.py` no longer has a `QSettings` name to patch, and `tests/unit/test_settings_chokepoint.py` forbids re-adding one — there is now a single factory to redirect, which is what `tests/unit/test_ui_state.py` does.)* Defensive backstop in [`tests/conftest.py`](../../tests/conftest.py): the session `isolate_qsettings` fixture now captures `QSettings.defaultFormat()` and restores it at teardown (a tripwire for a future `setDefaultFormat` leak — it does **not** cover a `setPath`-only leak), and a function-scoped autouse `_reset_app_settings` clears the `cofade_test` store + nulls the `_settings_instance` singleton around every test so per-test value pollution can't accumulate either. Lesson: a green CI does not prove the local full suite is clean; a "passes alone, fails together" failure whose actual value is always the default is almost always shared global/singleton state, not the code under test. The deeper smell this entry flagged as a follow-up — `UiStateStore` and `AppSettings` each constructing their own store inline, so there was no single chokepoint to isolate — **is fixed (#285 / ADR-041)**: `app/settings.create_qsettings()` is that shared factory, and one fixture now isolates everything. The `defaultFormat()` capture in `isolate_qsettings` was also upgraded from a silent repair to a real tripwire (it restores, then asserts) — a backstop that quietly fixes the damage reports nothing.

- **Command-description `{property}` fragments must be registered under the "Commands" i18n context** (issue #210): `ChangePropertyCommand.description` renders `translate("Commands", "Change {property}").format(property=translate("Commands", self._property_name))`. The German template is `"{property} ändern"`, so the *fragment* must itself be a translated German noun or the undo menu reads half-English ("text content ändern"). Every distinct `property_name` passed to `ChangePropertyCommand` (`"name"`, `"stroke width"`, `"fill color"`, `"text content"`, …) is registered in [`scripts/fill_translations.py`](../../scripts/fill_translations.py) under `"Commands"`. Because all call sites pass an `apply_func`, `property_name` is purely a description fragment (never the attribute being set), so it is safe to use clean human-readable labels — the two ugly raw attribute names (`frost_protection_needed`, `spacing_radius_cm`) and the composed `f"text {prop}"` were normalized to nouns via `_TEXT_PROPERTY_LABELS`. An unregistered fragment degrades to English (Qt `translate` returns the source) rather than crashing — and `test_german_ts_has_no_unfinished` cannot catch the miss, so adding a new `ChangePropertyCommand` fragment requires manually adding its German to the `"Commands"` dict.


- **Two surfaces that share a status store must derive the key identically — reuse the canonical `species_key()`** (US-C2, PR #227 #12): the Planting-Calendar dashboard and the Tasks tab both persist per-task done/snooze state in `task_states`, keyed by `task_id = "{species_key}:{task_type}:{year}"` for calendar-derived tasks. They computed `species_key` *differently*: the calendar used the canonical `species_key()` helper ([`models/plant_data.py`](../../src/open_garden_planner/models/plant_data.py), ADR-016 — `source_id → scientific_name → common_name`, **lowercased**), while `tasks_view.build_plan_state` used a raw `sp.scientific_name or sp.common_name or item.name` (no `source_id`, not lowercased). For any DB-sourced species (carries a `source_id`) or any casing difference the two ids diverged (`12345:harvest:2026` vs `Solanum Lycopersicum:harvest:2026`), so marking a task done on one surface was invisible to the other — sync failed in **both** directions. The round-2 PR test masked it by asserting the data layer with hand-matched ids. Fix: `build_plan_state` now calls the same `species_key()` helper, **and** the id *format* is built through a single shared `make_calendar_task_id()` (in `services/task_generator.py`) used by both the generator and the calendar dashboard — so neither the key nor the format can drift again. Lesson: when two views read/write a shared id-keyed store, the *entire* id derivation (key + format) must be a single shared function, and a sync test must build the id the way *production* does (from a realistic species with a `source_id`), not hand-write a matching string. Regression test: `tests/integration/test_tasks.py::TestCrossSurfaceSync`.

- **A handler fed a canonical `species_key` must match on the canonical key, not a raw name — and a "navigate by species" channel must also handle unkeyed targets** (US-C1, PR #235 manual test): the Harvest dashboard double-click routes through the shared `GardenPlannerApp._on_highlight_species`, also wired to the planting-calendar `highlight_species` and the Tasks tab `navigate_to_species` — **all three emit a canonical `species_key()`** (ADR-016, lowercased `source_id → scientific → common`). The handler compared that key against each item's **raw-cased** `scientific_name or common_name`, so it never matched for any capitalised name or any DB species carrying a `source_id` → nothing got selected (latent on all three surfaces; surfaced by harvest). Fix: compare `species_key(item.metadata["plant_species"])` on both sides + `centerOn` the first match. Second half of the same bug: a harvest on a **bed or species-less plant** aggregates under a `target:<uuid>` grouping key (it has no species), and the view had deliberately blanked those so they navigated *nowhere*. `_on_highlight_species` now also handles a `target:<uuid>` key by selecting that one item by id (via `_select_items_by_id`), and the view stashes the full grouping key. The same unkeyed target also caused the dashboard/CSV/PDF to show the raw `target:<uuid>` as a *name*: fixed by caching the item's localized object-type name at log time (`_harvest_species_for_target`) and substituting a localized "Unnamed" at every display surface (table + CSV + PDF — all three, or they drift). Lessons: **(1)** a signal documented as carrying a `species_key` must be *consumed* with the same canonical derivation it was produced with — never re-derive from a display name; **(2)** a "select by species" channel needs an explicit branch for targets that have no species (beds), or they become silently unclickable; **(3)** an internal grouping key (`target:<uuid>`) must never leak into a user-facing name column. Regression tests: `tests/integration/test_harvest.py::TestHarvestNavigation` (plant-by-species + bed-by-id + type-name fallback), `::TestAggregationAndExport::test_csv_unnamed_target_shows_label_not_blank`.

- **QSvgRenderer paints `currentColor` BLACK — never feed a contract icon SVG to it directly** (#279, ADR-039): Qt's SVG renderer does not resolve `currentColor` against any palette — it falls back to black. This is precisely why the legacy `icons/tools/` set carried baked hex overrides on every element (`constraint.svg` declared `stroke="currentColor"` and then overrode it with `#333` everywhere). Every chrome-icon render must go through the provider `ui/icons.py`, which substitutes the active theme's colors into the SVG text *before* rasterizing; the conformance gate guarantees the files contain only substitutable tokens, so the failure can only re-enter via a NEW direct `QSvgRenderer` call on a contract icon — don't add one. (`gallery_data.render_svg_thumbnail` remains correct for the full-color plant/furniture art, which never uses `currentColor`.)

- **A full-app integration test that outlives ~500 ms must silence the startup Welcome dialog — its modal `exec()` blocks pytest-qt forever** (#279 test-infra finding): `GardenPlannerApp` arms `QTimer.singleShot(500, self._startup_sequence)`, which — with `show_welcome_on_startup` enabled, the default on dev machines — opens the **modal** `WelcomeDialog` via `dialog.exec()`. Headless nobody closes it, so the first event processing after the timer fires (typically pytest-qt's `_process_events` between/after tests) parks the session inside the modal event loop forever — and because pytest's output is block-buffered, the log stays EMPTY, so the hang masquerades as a collection freeze. Existing app-boot tests never hit it because they finish inside the 500 ms window; the #279 theme-switch tests (pixel scans + two full restyles) were the first to outlive it. Fix pattern (`tests/integration/test_icon_system.py::_make_app`): `monkeypatch.setattr(GardenPlannerApp, "_show_welcome_dialog", lambda self: None)` before construction, alongside the established `QMessageBox.question` → Discard patch. Diagnosis tool that found it: `pytest -o faulthandler_timeout=40` dumps every thread's stack at the hang moment — reach for it whenever a Qt test "hangs with no output."

- **A `statusBar().showMessage()` set while a modal dialog is open is invisible — and a transient status blip is the wrong channel for a startup reminder** (US-C2, PR #227 #16): the overdue-task startup reminder used `self.statusBar().showMessage(msg, 10000)`. On the common path (Welcome dialog → recent project) the message was written by `_open_project_file` *while the modal `WelcomeDialog` still covered the main window* (the dialog emits `recent_project_selected` → loads the project → `accept()`s only afterwards), so it was painted behind the dialog and never seen; even the post-dialog re-check was a 10 s bottom-of-window blip competing with `"Opened: …"` / `"Auto-saved"` / `"Ready"`. Net: the user never saw it, toggle on or off. Fix: deliver via a **persistent, dismissible top bar** (`TaskReminderBar`, modelled on `UpdateBar`) with a "Show Tasks" action, and run the check **deferred** (`QTimer.singleShot(0, self._check_overdue_tasks)`) from both the startup sequence and `_open_project_file` so it fires after the modal dialog has closed and the event queue has drained. The check is idempotent (re-evaluates the count, hides on zero) so multiple deferred calls are safe. Lesson: never use the status bar for a notification that must survive a modal dialog or compete with other writes — use a persistent bar; and defer any post-open UI feedback past the modal `exec()` that may have triggered it. Regression test: `tests/integration/test_tasks.py::TestOverdueReminderBar`.

- **A `QToolBar` added to the main window MUST carry a unique `objectName` — an empty one does not merely warn, it *aliases*** (#283): `QMainWindow.saveState()` serialises every toolbar keyed by its `objectName` and logs `QMainWindow::saveState(): 'objectName' not set for QToolBar 0x… 'Tools'` when that key is empty — three such lines at every app exit (`UiStateStore.save_geometry` → `saveState()`, reached from `closeEvent`), because `MainToolbar`, `ConstraintToolbar` and `CategoryToolbar` never set one while `SunSimToolbar` and the soil-overlay toolbar always did. The console noise is the visible half. The damage is that an unnamed toolbar still *reaches* the saved state — under an empty, non-unique key — so `restoreState()` can only match those entries by **layout position**. Measured on Qt 6.11 (probe, not inference): that position equals creation order here only because all five toolbars sit in `TopToolBarArea` via a bare `addToolBar()`; a future left/bottom-area toolbar would not follow that rule. A state that saved "B hidden", restored into a window owning one extra unnamed toolbar created before them, hid **A** instead — and dropping one unnamed toolbar loses the hidden state altogether; with unique names both cases hit B. The arrangement therefore survived only while the number and position of unnamed toolbars never changed — and this app keeps gaining toolbars (soil overlay, then sun-sim in Phase 14). Contract: every toolbar calls `setObjectName("<StableName>")` **before `addToolBar()`** — the five shipped ones do it in three different places (`_setup_toolbar()`, `__init__`, inline at the call site), so the rule is the timing, not the location. The name is a **persistence key**: it must never come from a translated string (`self.tr(…)`), must not change once shipped (see §8.4.2 — do not rename one for a QSS selector), and is why the pre-existing `soil_overlay_toolbar` keeps its odd snake_case. **One-time migration:** an already-saved blob written by an older build restores cleanly against the fixed code — the two named toolbars are restored and the three newly-named ones fall back to their defaults, losing any hidden state. Benign — and moot since the same PR made toolbar visibility non-user-configurable (see the next entry). Pinned by `tests/integration/test_toolbar_state_persistence.py`: a unique-name sweep over every main-window toolbar; a Qt-message-handler assertion that `saveState()` logs nothing, plus a positive control proving the handler actually fires (else that assertion could pass vacuously); the dropped-entry branch against the real app; and the misassignment branch — "hid **A** instead" — on a bare `QMainWindow`, because it does not reproduce against `GardenPlannerApp` at all: measured, the real window keeps hiding the correct toolbar both with an intruder created last and with one front-inserted after construction, so *why* the app's own two-row layout resists the aliasing is unisolated — hence the mechanism is pinned where it can be observed rather than asserted where it cannot. The round-trip guard reads `toolBarBreak()` alongside `toolBarArea()`, because all five toolbars share `TopToolBarArea`: an area-only snapshot is a constant map that stays green even when a restore flattens the sun-sim toolbar off its own row (measured). **Diagnostic note:** do not try to verify this by piping the app's output — measured on Windows, Qt's default handler writes to `OutputDebugString` rather than `stderr` when `stderr` is not a console, so `python -m open_garden_planner 2>&1 | grep objectName` prints nothing whether or not the bug is present (a real PowerShell console does show them, which is how it was reported). The only reliable programmatic instrument is `qInstallMessageHandler`, which is what the test uses.

- **A toolbar carrying essential tools must not be user-hideable — `QMainWindow`'s free context menu is a trap with no way back** (#283 manual test): `QMainWindow` supplies a right-click menu with a checkbox per toolbar, for free, whether or not the app wants it. Since ADR-018 the `CategoryToolbar` *is* the object gallery, so one stray click removed **every** placement tool at once; the layout is saved on exit, so it stayed gone across restarts; and the only route back was that same menu, which a user who has just lost their toolbars has no reason to go looking for. Surfaced in #283's own manual test, reported as "all the drawing tools are gone" — the fix's regression test had happily proved that hiding *persists*, which is the behaviour, not the requirement. Fix: `GardenPlannerApp.createPopupMenu()` returns `None`, and `_enforce_toolbar_visibility()` re-asserts the invariant after every `restoreState()` — three core toolbars on, two feature toolbars off. The two halves are load-bearing together: enforcement without suppression leaves the trap open, and **suppression without enforcement is worse than the bug** — a user whose saved state already hides a core toolbar could never recover it, because those three have no View-menu toggle of their own. (The two feature toolbars are not in that position: each has a checkable View-menu action driving `setVisible`, so a stale-visible one can be dismissed in two clicks — measured, after an earlier draft of this entry claimed otherwise. Their defect is the action/toolbar/overlay desync of #286, not unrecoverability.) **The context menu is not even the likeliest trigger:** preview mode (F11) hides the main toolbar and `closeEvent` persists whatever is on screen, so quitting straight out of preview reopened the app with no drawing tools at all, no right-click involved. Measured as pre-existing — it fires with the `setObjectName` lines reverted too — and healed by the same enforcement, which is why the invariant must be *asserted* rather than merely made unreachable through one menu. Closes #286 as a side effect (soil-overlay toolbar returning visible with its action unchecked). Lesson: before persisting a piece of UI state, ask whether the user can get back out of every state you are about to make durable.

- **`UiStateStore` builds its own `QSettings`, so it escapes the conftest isolation — full-app tests read *and overwrite* the developer's real window state** (#283 test-infra finding — **Closed (#285)**): `tests/conftest.py::isolate_qsettings` redirects `AppSettings` only, but `app/ui_state.py` constructs `QSettings("cofade", "Open Garden Planner")` directly. Every `GardenPlannerApp()` in a test therefore restored whatever geometry and toolbar layout the developer's own app last saved — and wrote it back at teardown, because pytest-qt closes registered widgets and `closeEvent` → `_save_ui_state()` persists. Symptom while writing #283's regression tests: a toolbar-visibility assertion passed under pristine settings and failed locally with the *fix applied*, purely because an earlier experiment had left a different toolbar layout in the real store — an hour lost to "the fix doesn't work" when the test harness was the variable. First patched by an autouse `_isolate_ui_state` fixture pointing `ui_state.QSettings` at the test key; local runs then also matched CI, where the store is always pristine (so `_geometry_restored` is False and the window maximizes). Lesson: a store that bypasses the settings chokepoint also bypasses the test isolation built on it. **Closed by #285 / ADR-041**, which made the tourniquet unnecessary rather than permanent: `app/settings.create_qsettings()` is the only place that constructs — or even names — a settings store, `UiStateStore` takes its backend from there, `_isolate_ui_state` is deleted, and `tests/conftest.py` redirects the whole app by rebinding two module names *at its own import time*. **The mechanism is specified once, in §8.8 — read it there, and change it there.** Do not re-derive it in this entry: three earlier attempts to summarise it here, in ADR-041 and in `CLAUDE.md` each drifted out of sync with the code within one commit, which is how reviews 2, 3 and 4 all found a doc/code mismatch. What belongs here is the evidence: reverting the chokepoint makes `tests/integration/test_settings_isolation.py` fail with exactly 3 reads + 3 writes to the real key, and hashing the real store's 29 values around a 47-test full-app file leaves them byte-identical.

- **The test suite wrote into the developer's real plant library — isolating one store is not isolating the process** (found 2026-10-11 during Phase 17 L1; fixed in `tests/conftest.py`, §8.10 "Test isolation"):
  - **Symptom.** The developer's own `%APPDATA%/OpenGardenPlanner/custom_plants.json` held 209 custom plants, 207 of them the same "Walnut (Juglans regia)"; `plant_lists.json` in the same folder had been rewritten that morning by nobody. Every full run of the suite, by any agent on the machine, added one more Walnut. (Counted by whoever found it; the fix was written and tested without opening that folder.)
  - **Root cause.** `tests/conftest.py` isolated the settings store (#285, the entry above) and nothing else. `services.plant_library.get_app_data_dir()` resolves `%APPDATA%/OpenGardenPlanner` (or `$XDG_DATA_HOME/…`) on every call and was never redirected, so every store built on it — the custom plant library, plant lists, seed inventory, companion rules, smart symbols, the weather cache — was the user's real one in a test process. `tests/ui/test_plant_database_panel.py::…::test_sparse_species_saves_back_as_none` calls `panel._on_field_changed()`, whose last step saves the edited species through `get_plant_library()`: a correct test of the panel, and a write into the real library. Two test files had even noted the gap in a docstring ("isn't isolated by `tests/conftest.py`") and stubbed their own way around it; nobody closed it.
  - **Fix.** The conftest sets `APPDATA` and `XDG_DATA_HOME` to a per-process temporary directory at import time — the same place and for the same reason as the settings redirection. No production code changed. The real directory was not cleaned by this change: what to do with the 207 entries is the owner's decision.
  - **The same search found three more writers outside the test root**, none of them into the user's own app folder, all through `QStandardPaths.writableLocation`: (1) `tests/unit/test_main_hardening.py::TestExceptHook` appended a traceback to `%APPDATA%/pytest-qt-qapp/crash.log` on every run — 331 of them, 82 kB, when counted; (2) the companion, climate and thumbnail caches under `%LOCALAPPDATA%/pytest-qt-qapp/`, which survive from run to run, so a test could pass on a cache an earlier run had filled; (3) `tests/unit/test_paths.py::test_get_projects_dir_falls_back_to_home` created `~/Documents/Open Garden Planner` on every machine it ran on, because `get_projects_dir()` creates what it returns. (1) and (2) are closed by redirecting the Python-level function, (3) by giving that test a home of its own.
  - **Lessons.** *List every place the app writes* (`get_app_data_dir`, `QStandardPaths`, `Path.home()`, the temp directory) and decide each one — redirected, or left with a reason. *A test that is correct about the unit can still be wrong about the world:* the Walnut test asserts what it should and has passed since it was written. *A known gap written into a docstring is a defect with a comment on it.* And the pin must not need the thing it protects: the end-to-end test never reads the real directory — it watches what the process opens (`tests/integration/test_app_data_isolation.py`).

  - **One review later: four more, each outside what "the app-data directory" had made anyone look at** (L1.1 fix round 3, 2026-10-11). (1) **A test read another tool's credentials.** `tests/unit/test_ai_client_onboarding.py` redirected `APPDATA` for the client it was about; `detect_clients()` asks every client in the registry, and the others hang off `Path.home()` — the test opened the developer's real `~/.claude.json`, `~/.codex/config.toml`, `~/.config/opencode/opencode.jsonc` and `~/.gemini/config/mcp_config.json`. Reads, not writes; of files that hold tokens. The module now gives every test a home of its own. (2) **A library has user files too.** ezdxf loads `~/.config/ezdxf/ezdxf.ini` when it is imported and builds *and writes* `~/.cache/ezdxf/font_manager_cache.json` when that is missing (read in the installed 1.4.3, not by touching the home); `XDG_CONFIG_HOME` / `XDG_CACHE_HOME` now point into the test root. (3) **The stand-in was kinder than the thing it stands for.** The replacement for `QStandardPaths.writableLocation` created the folder it named; Qt does not, so a writer without its own `mkdir` would have passed every test and failed on a first run. It names the path only, and a test shows every writer making its folder. (4) **Scripts are outside all of it.** A script that imports the app is not a pytest process: its settings are the user's own — on Windows the registry, which no environment variable moves — and `ProjectManager.save()` / `.load()` end with `add_recent_file`. Probe and generator runs replaced a developer's whole Recent Files list with fixture paths. `scripts/script_isolation.py` (§8.10, "A script is not a test") and a test that runs each script as a script. (5) **And one layer further, a review later** (fix round 4): on Windows the profile variables move only part of what Qt hands out — `AppLocalDataLocation` and `CacheLocation` follow the shell, not the environment — so a script's isolation installs the suite's own stand-in too; the list of scripts that isolate themselves was kept by hand, so every file under `scripts/` is read now; and one onboarding test could still START a client CLI it found. *The question "where does the app write?" has a second half: "and who else runs the app?" — a test, a child process, a script, a probe. Each needs its own answer, and an answer for one is none for the next.*

- **A "nobody may use X" gate belongs in the AST, not in a regex — and it must be falsified twice** (#285, gate-design lesson): `test_settings_chokepoint.py` started as a line-anchored regex for `QSettings\s*\(`. Falsifying it by restoring the pre-#285 code as `from PyQt6.QtCore import QSettings as _Q` … `_Q("cofade", …)` — a two-line edit anyone could make while "just fixing an import cycle" — sailed through, so an **import** pattern was added. A senior review then broke *that* in one experiment: `from PyQt6.QtCore import (\n    QSettings as _Q,\n)` names the class on a line with no `import` keyword, so both regexes passed and only the behavioural test caught the bug. Rewritten as an `ast` walk over `Import`/`ImportFrom`/`Name`/`Attribute`, all spellings collapse into one check — and the same walk cheaply expresses a rule no regex could ("no `create_qsettings()` call that is evaluated at import time", distinguishing a function *body* from a decorator or default argument). Lessons for every textual gate in this repo (QSS colors, icon conformance, texture tileability): match the **name binding**, not just the use, because you cannot use what you have not first named; prefer the AST when the language has one; give every detector a **positive control** fed the exact escape it exists to catch, since a detector that stops matching anything reads as a green gate forever; and treat "my falsification passed" as one data point, not proof — the second reviewer found the second hole in one try.

- **`QGraphicsScene.changed` feedback loops: a slot driven by `scene.changed` that itself mutates the scene runs forever while the app is idle** (issue #305 — a macOS user's OGP process reached **134 GB** after ~1 h in the background; the whole system froze). Measured on Windows (offscreen, real `GardenPlannerApp`, counting `scene.changed` emissions and `QGraphicsScene.render` calls per fixed window after a 1.5 s settle — the probes are now the tests in `tests/integration/test_idle_scene_quiescence.py`), **four independent loops** existed, each of the same shape: (A) `MinimapWidget._do_update()` hides every overlay item (`ItemIgnoresTransformations` or z ≥ `_OVERLAY_Z_MIN`) for the thumbnail render and re-shows them afterwards; for a **transformable** overlay item each `setVisible()` makes the scene emit `changed`, which restarted the 100 ms throttle → `_do_update` again. With one such item the minimap re-rendered the **whole scene ~9×/s forever** (13–14 renders per 1.5 s vs 1 with none). Measured in senior review: `setVisible()` on an `ItemIgnoresTransformations` item emits **no** `changed` at all — and every handle, label and badge in this app carries that flag — so selection handles were *not* a Loop-A trigger; in production only the curve-edit connector lines (transformable, z ≥ 10000) are, and the reporter's idle churn came from B–D below — and a minimap the user had toggled *off* still rasterised the scene on every change into a widget nobody could see. (B) `CanvasView._update_soil_mismatches()` (500 ms debounce on `changed`) called `item.update()` **unconditionally** for every bed — one never-selected `GARDEN_BED` on an otherwise empty plan: 16 `changed` + 8 renders per 4 s, forever. (C) `_update_spacing_overlaps()` (150 ms) and (D) `_update_companion_highlights()` (60 ms) both did a *clear pass* (`set_spacing_overlap(None)` / `set_companion_highlight(None)` + `set_antagonist_warning(False)` on every plant) followed by a *set pass* — so although the item setters have an early-return guard for unchanged values, the handlers forced every value through None each tick: **one gallery-dropped plant with database spacing** (`max_spread_cm`, which FR-PLANT-15 populates on every drop) → 19 `changed` + 20 renders per 3 s forever; tomato + fennel 60 cm apart → 47 `changed` per 3 s. **This one was missed by the first fix and caught in senior review**: the "companion/spacing quiesce" claim had been measured with a `GENERIC_RECTANGLE`, which those handlers skip entirely — a measurement that tests nothing about them. Every loop feeds **every** `changed` subscriber (companion, spacing, plant-search 150 ms, snap dirty flag, sun-shadow debounce, minimap): a full-scene `render()` into fresh `QPixmap`s plus O(n²) scans per cycle with nobody at the keyboard. **Two subtleties that make this class hard to see:** `setVisible()`/`update()` do **not** emit `changed` synchronously — Qt queues the emissions for later event-loop turns (measured: a single hide already yields `[rect]` then `[]` on **two separate turns**, both after the mutating method returned — the empty one is Qt's trailing emission), so a naive in-call re-entrancy flag is **not** enough — and neither is a single `singleShot(0)`, which a first cut used and which was measured to clear the flag between the two emissions; and the emission carries only *rects*, not the item that changed, so a subscriber cannot tell its own churn from a user edit by identity. **Fix**: the minimap's `changed` slot is **content-based** — it records the scene rects of the overlay items it just toggled and ignores an emission iff every rect lies inside one of them (an empty rect list is Qt's trailing no-op; measured, every genuine mutation carries ≥ 1 rect) — no timing window, so a genuine change sharing the same turn is still rendered; a toggled-off minimap no longer renders at all; the soil handlers became **idempotent** (write the tooltip / call `update()` only when the level or text actually changed; `SoilBadgeItem.update_position()` no-ops on unchanged pos — measured: `setPos`/`setToolTip` with an unchanged value do *not* emit `changed`, `update()` does); spacing and companion compute the **final state per item first and call each setter exactly once** — no clear pass — the discipline `_update_container_capacity()` already had. **Rule for every `scene.changed` slot** (and any slot on a timer that `changed` restarts): it must be idempotent — compute the target state, then apply it once; never call `update()`, `setVisible()`, `prepareGeometryChange()` or add/remove items unless the value really changed, and never "clear then set". **How to check for a new loop**: put one bed, one DB-spacing plant and one selected object on the plan, settle 1.5 s, then count `scene.changed` emissions and `QGraphicsScene.render` calls over the next 2 s — both must be 0; the positive control (move a plant → ≥ 1) proves the counters work. Pinned by `tests/integration/test_idle_scene_quiescence.py` and `tests/unit/test_minimap_widget.py::TestMinimapIdleQuiescence` (including the "genuine change in the same turn is not dropped" and "toggled-off minimap does not render" cases). Not measured: the macOS-side accumulation path from "10 Hz pixmap churn" to 134 GB (Windows RSS stayed flat at ~59 MB over 20 s of the loop) — the loop itself is a defect regardless, and the reporter (macOS 26.6.1, self-built PyInstaller `.app`, plan with constraints on screen, minimap state uncertain) has been asked for an Activity Monitor graph should it recur.

- **A non-critical CI job that fails permanently is indistinguishable from one that does nothing — and it trains everyone to scroll past the Actions tab** (issue #293): `.github/workflows/add-to-project.yml` ran `gh project item-add 1 --owner cofade --url <issue>` on every `issues: opened` event and failed **70 out of 70 runs** between 2026-04-18 and 2026-08-15 — there was never a successful one. `gh` resolves whether `--owner` names a user or an organisation via GraphQL *before* adding anything; a token that cannot see that has nothing to classify and the CLI reports exactly `unknown owner type`, exiting 1 in ~5 s. So the credential in the `ADD_TO_PROJECT_PAT` secret never worked: a classic PAT needs the `project` scope, and a fine-grained PAT has historically not covered **user**-owned Projects v2 — `cofade` is a user and the board is `PVT_kwHOAyyXvs4BU2fi`. The tell that this was never a scope *expiry*: the secret was created 2026-04-19, one day **after** the first failing run, i.e. it was added in response to a failure and the failure was never re-checked. The damage was silent and cumulative — the board froze at issue **#161** while ~130 further issues (all of Phase 14, both Visual Refresh packages, the whole Agent API epic) went unrecorded, and `docs/roadmap.md` quietly became the only real tracker. Nobody noticed for four months because the job had no `continue-on-error`: every newly opened issue produced a red ✗ that looked like part of the furniture, which is also what makes such a job dangerous — a permanently red check camouflages a genuine one. **Resolution: the workflow was deleted, not repaired**, together with every public pointer at the board (`README.md`, the wiki, `ogp-external-positioning`) — the board had been unmaintained for ~4 months and had no readers, so fixing the token would have restored an automation feeding an artefact nobody consults. **Lessons:** (1) a new workflow's *first* run must be verified green — adding a secret in response to a failure is not the same as confirming the failure is gone; (2) before repairing a broken automation, check whether its **output** is still wanted; deletion is a legitimate fix and here it was the honest one; (3) never reach for `continue-on-error` to quiet a job that has never worked — that converts a visible defect into an invisible one; (4) a public README pointer at an automated artefact inherits that automation's health — when the automation dies, the pointer becomes an oversell of project activity. Verification: `gh run list --workflow add-to-project.yml --limit 200 --json conclusion` → 70/70 `failure`; `gh project item-list 1 --owner cofade` → 35 items, highest #161.

- **The Welcome-dialog hang above was re-hit on 2026-08-17 (Package 3a) — because its fix was per-file, and only three of 34 app-building test files had it.** A full `pytest tests/` run stalled silently for 18 minutes inside `tests/integration/test_trellis.py` (2nd test), noticed only because the log's **modification time** was old — the tail looked like normal progress. A first write-up of this incident misfiled it as an unsolved "leaked slot" hang and reached for `pytest-timeout` as the fix; the senior review's stack dump (`application.py` → `dialog.exec()` inside pytest-qt's teardown `processEvents()`) pointed straight back at the entry above, which nobody had grepped for "Welcome" first — an institutional-memory failure committed inside a documentation commit. **Fix (structural):** `tests/conftest.py::_silence_welcome_dialog` — a **session**-scoped autouse fixture that replaces `GardenPlannerApp._show_welcome_dialog` with a no-op for the whole run (the class-level patch three files had applied per file), plus `_disable_welcome_dialog`, a per-test store write of `KEY_SHOW_WELCOME=False`. The class patch is the load-bearing one: a store-only guard was tried first and *lost a race once in a full run* — the read returned the default inside a `qtbot.wait` although both a conftest and a module fixture had written `False` before the app was built (`test_idle_scene_quiescence.py`, 2026-08-17). **The mechanism was then pinned down with two 15-line probes, and it is a second, independent pitfall (Windows registry backend):** a `QSettings` that has called `clear()` deletes its registry key **when it is destroyed** (`deleteWriteHandleOnExit`), and **every store built between that `clear()` and that destruction becomes a "black hole" — its writes vanish and its reads return defaults** (probe: `t.clear()`; build `s`; `s.setValue("x", 1)` reads 1; `del t` → `s.value("x")` reads the default and further writes are lost). **And the clearing instance was in ANOTHER PROCESS.** The test key was a fixed name (`cofade_test / Open Garden Planner Test`), so a second pytest run on the same machine — here the senior-reviewer agent running the suite in its worktree while the main battery ran — shared it, and every one of *its* per-test `clear()`s deleted the key under *this* process's live singleton. Decisive experiment: the same three files produce black holes on every run with a deliberately concurrent pytest process, and pass 3/3 under the same concurrency with the fix below. It also explains why the failures moved between tests and runs, and why "passes alone" told nothing. **Fix (three layers, all in `tests/conftest.py`):** (1) **per-process test key** — `TEST_APPLICATION = f"Open Garden Planner Test {os.getpid()}"`, so concurrent suites cannot see each other's key (the session-end `clear()` removes this process's key; a crashed run leaves an orphan `… Test <pid>` under `HKCU\Software\cofade_test`, harmless); (2) `_reset_app_settings` wipes per key (`remove(key)` for `allKeys()`, then `sync()`) instead of `clear()` — defence in depth against the same mechanism inside one process; (3) a **tripwire** at teardown that probes the live singleton and fails the test with "settings singleton is a BLACK HOLE …" if it is dead — the next such incident is a diagnosis, not a mystery. Rules: **never `clear()` a QSettings key that other live instances (in any process) share — `remove()` keys instead; and never assume a settings-based test guard is airtight when a concurrent process can exist (the senior-reviewer worktree runs the suite while you do).** `pytest-timeout` (MIT, dev dependency; `[tool.pytest.ini_options] timeout = 180`) stays — as a guard against *unknown* hangs, not as the fix for this one: on Linux/CI the signal method fails just the hung test; on Windows the thread method dumps every thread's stack and aborts the run, which names the culprit. **Lessons:** (1) before writing a new §11.4 entry, grep §11.4 for the symptom's nouns — this file is only institutional memory if it is read; (2) a hang guard is worth having, but never ship a detector for a landmine you know how to defuse without also defusing it; (3) when waiting on a long run, watch the log's **age**, not its tail (`stat -c %Y` vs `date +%s`); if it stalls, kill it, run the stalled file alone, then after its collection-order predecessors — or use `-o faulthandler_timeout=40` as the "silence the startup Welcome dialog" entry above prescribes.

- **A pixmap blitted in item-local coordinates is upside-down on the canvas — and the plant sprites hid it for eight months** (Package 3a #308, owner manual test 2026-08-17): the view and every export (`export_service`, `pdf_report_service`, `scene_rendering`, `print_dialog`) draw the scene through `scale(1, -1)` (scene Y-up, §8.9), so `painter.drawPixmap(rect, pixmap)` inside `paint()` renders the image mirrored vertically. Every SVG-rendered object had been drawn that way since Phase 6; the plant sprites are radially symmetric *and* randomly rotated, the legacy furniture was near-symmetric, so nobody saw it — until the new fire pit's flames pointed **down** while the gallery thumbnail (rendered without the flip) pointed up. **Fix**: the furniture branches of `RectangleItem.paint` / `CircleItem.paint` flip the painter back about the rect centre (`translate(c); scale(1, -1); translate(-c)`) — the same idea as `background_image_item`'s flip transform and the text items' `setTransform(scale(1, -1))`. Pinned by `tests/integration/test_object_sprite_rendering.py::TestUprightOnCanvas`, which renders the wheelbarrow (heavy wheel end up, thin handles down) through the real flipped `scene.render` and asserts the top band carries more ink than the bottom, as the art does — the test fails with the exactly mirrored numbers without the fix. **Two lessons**: (1) any raster drawn in item space needs the local un-flip; only vector primitives and child items with their own transform are exempt; (2) a metric over `scene.render()` of a `CanvasScene` measures the opaque canvas background, not your item — render the item alone in a bare `QGraphicsScene` (`_render_item_alone` in that test file), which also exposed that an earlier "the tool draws an item that paints" assertion had been vacuous.

- **A "byte-deterministic" PNG gate is a zlib gate in disguise — compare decoded pixels, never file bytes** (Package 3b #309, 2026-08-18): the plan called for a byte-exact `--check` on the regenerated textures. PNG is lossless, but the deflate stream is produced by whatever zlib Pillow's wheel bundles (zlib vs zlib-ng, per platform and release) — the Windows dev machine and the Linux CI runner can encode *identical pixels* to *different bytes*, so a byte gate flaps between environments or forces a Pillow pin. Fix: `--check` decodes the committed PNG and compares arrays; regeneration rewrites a file only when its pixels change (otherwise every cross-platform run would produce a spurious diff). Same reasoning applies to any binary artifact with a compressor in the encode path (PNG, zip, gzip'd fixtures): the art is the pixels; the bytes are the tool's. The SVG generators are unaffected — they emit text.

- **A hidden wrap seam is located by measuring `|row0 − row255|` per column, not by theorising about the layout** (Package 3b #309, 2026-08-18): the regenerated `wood.png` failed the seam gate in *y* (1.85 ×) although its planks run vertically and every grain line is periodic. Two plausible theories (the full-height plank rectangles' bevelled top/bottom edges wrapping into a band; the blur) were wrong; the per-column seam step named exactly the plank-*joint* columns, and painting the joint primitive alone on a fresh `Tile` showed its coverage falling from 110 at row 0 to 142 at row 511 — the `capsule` primitive's `taper` default was 0.0, i.e. "pointed at the far end", so every constant-width line in the set (joints, straw, cracks, cleft streaks) was secretly a blade. One default flipped to 1.0; the lesson is the method: the metric already knows *where* the seam is — ask it (debugging-playbook row 36).

- **A debounce `QTimer` armed by a test outlives the test — and a timer slot that can open a modal `QMessageBox` becomes a heap-corruption crash in whatever test runs 500 ms later** (Package 3c #310, 2026-08-18): `PlantSearchDialog` created its debounce timer as `QTimer()` (no parent). Every test that typed into `search_input` armed it, called `_perform_search()` synchronously, and finished well inside 500 ms — leaving the timer ARMED (a file-logged probe over the full battery counted 17 such calls, all with `timer.isActive() == True`). Two mechanisms are consistent with what was observed, and the run that crashed predates the probe, so the exact liveness state at fire time is not known: (a) the dialog's Python object had been collected → the C++ dialog deleted → the *unparented* timer (Python-owned, still referenced through the signal connection) fired into a dead widget; or (b) the dialog was still alive (its own `timeout → bound method` connection forms a reference cycle that only a later GC breaks) and the slot opened a modal `QMessageBox.warning(self)` in the middle of another test's `processEvents`, whose nested loop then processed the deferred deletion of that very dialog under the modal's feet. Either way the symptom was `Windows fatal exception: code 0xc0000374` in `test_plant_sprite_rendering.py`, a file that has nothing to do with plant search, and it had never fired before because the timing landed in harmless places until two new test files shifted the schedule. Fix, three legs, covering both mechanisms: `QTimer(self)` (lifetime bound to the widget — closes (a)), `done()` stops it (a pending debounced action must be settled before the dialog goes — the #210 flush rule), and **`_perform_search()` itself stops it first** (a search that runs NOW must not run again 500 ms later — this is what closes (b), and it is why the first fix round with parenting alone still aborted). Pinned by `tests/unit/test_plant_search_dialog_timer.py`. Rules: any `QTimer` created in a widget takes that widget as parent; a debounced action settles its own timer when it runs; any timer slot that can open a modal or touch child widgets is stopped in `done()`/`closeEvent`. Diagnostic tell: the crash's stack ends in a widget method under `pytestqt/plugin.py … _process_events` during the SETUP or CALL of an unrelated test — read the crashing FRAME, not the test name; the culprit is whichever earlier test left a timer or thread alive; log the probe to a file, pytest capture dies with the process (playbook row 37).

- **A bug that is exactly 0 at the default value hides forever — and a `Callable` parameter is where two implementations of one behaviour go to drift** (US-D2.2 #326, 2026-08-18): `ResizeItemCommand` and `RotateItemCommand` take a caller-supplied `apply_func`, so every call site wrote its own closure. And `ResizeItemCommand` accepts **two** callables, not one — `apply_func` plus each `partner_resizes` entry's apply function, both run on execute and undo — so the call sites were: three numeric-entry branches in `properties_panel`, a drag-release handler on each item class, `RectVertexEditMixin._move_corner_to`/`_on_corner_move_end` in `resize_handle.py`, and the EQUAL-constraint partner appliers in `core/tools/constraint_tool.py`. When #218 added `setTransformOriginPoint(rect().center())` to keep the rotation pivot on the new centre, it landed in the **item-class drag-release** copies only. The panel's copies kept resizing without re-pinning, so a **rotated** object resized by typing a number pivoted about a point that was no longer its centre. Measured: a `TREE` at (200, 200) rotated 30°, resized 50 → 100 cm through the panel's own code, ended up centred at (263.4, 163.4) — **73.2 cm** away, and it then *saves* that position. Two lessons. (1) **At rotation 0 the drift is exactly 0.0**, and the overwhelming majority of objects are never rotated, so every existing test and every manual pass since #218 was blind to it; when a defect's magnitude is proportional to a parameter that is usually at its neutral value, coverage of the neutral case proves nothing — parametrise the test over the parameter (here `[0, 30, 90, 215]°`). (2) The bug was not found by looking for it: it surfaced because US-D2.2 needed a *third* caller and the extraction forced a byte-level comparison of the existing two. **A `Callable` injection point with N call sites is N implementations of one behaviour**, and nothing in the type system will tell you when one of them stops matching the others — if you are about to become caller N+1, diff callers 1..N first. Fix: `ui/canvas/geometry_apply.py` now holds the one apply function, and **its module docstring is the authoritative list of callers and exceptions** (stated there only — the five paraphrases of it drifted into three inconsistent answers during review, proving the point); `tests/integration/test_geometry_apply_shared_path.py` pins it, and was verified to fail with the re-pin removed (17 tests go red when the re-pin is removed; 10 when the guard was first written). **(3) The first pass converted most call sites and then asserted completeness in six documents — and missed two.** `RectVertexEditMixin._move_corner_to` had the identical omission and was found only by the senior review, because its call site lives in `resize_handle.py` rather than in an item class: measured 640 cm of stale origin and a 331 cm disagreement between the stored and visual centres on a 30° rectangle. The second miss was worse: the EQUAL-constraint partner appliers, reached through `ResizeItemCommand`'s *other* callable parameter (`partner_resizes`), carrying the same rotation bug — 70.7 cm at 90°. An extraction that claims "every caller" is worse than one that names its exceptions, because the next reader stops looking; grep the constructor (`ResizeItemCommand(`) and enumerate **every callable it accepts, including the ones passed in a list**, rather than reasoning from the files you happened to open.

- **Same-layer stacking inverted on every save/load** (#338): a plan drawn as `lawn → path → bed` (bottom to top) reloaded as `bed → path → lawn` — every same-layer pair silently flipped on every `.ogp` round-trip, and had done so since layers existed. Root cause: `ProjectManager._serialize_scene` walked `scene.items()`, which is Qt's **top-first** order, and wrote objects to the file in that order; load then re-inserted them via `scene.addItem()` in **file order**, which `addItem` stacks bottom-up — so the file's top-first write order became the load's bottom-first read order, exactly reversing every same-z tie. Only the plant-above-bed and ROOF_RIDGE-above-owner cases were ever band-aided (an explicit `zValue() + 1` pass — failure-archaeology incident 22); every other same-layer pair (two beds, a lawn and a path, …) had no such band-aid and simply inverted, unnoticed, because nothing before #338 gave the user a reason to care which of two untied objects was "in front". Fix: `_serialize_scene` now iterates `reversed(scene.items())`, writing objects bottom→top — which also fixes every *older* app version's reads, since they load in file order the same way. Combined with the new persisted `stack_order` rank (ADR-043), a round-trip through the current app is now exact; a round-trip through an app that predates #338 loads in (now-correct) file order and simply has no explicit ranks to preserve. Pinned by `tests/integration/test_stacking_roundtrip.py` (the inversion regression, ranks round-trip, an old file without the `stack_order` key loads in file order). Lesson: a serializer that iterates a Qt container's *default* order without checking what that order means (top-first vs. bottom-first) will silently invert on the next read — never assume `scene.items()`'s order is "the" order without naming which end is first.

- **Clipboard-pasted items were layer-less** (#338, found while implementing stacking order): `CanvasView.copy_selected`/`duplicate_selected` never saved `layer_id`, and `_deserialize_item`'s per-type constructors don't take one — so a pasted or duplicated item always landed with `layer_id = None`, invisible to that layer's visibility/lock toggle and (once #338 shipped) unranked and un-arrangeable. This was a pre-existing gap, not a regression #338 introduced, but per-object stacking is what made it visible (an unranked, layer-less item sorts to the very top of the `None` pseudo-layer's z=0 band, which reads as "why won't Arrange do anything to my pasted copy"). Fix: `_serialize_item_core` now writes `layer_id` when the source item has one; a new `CanvasView._restore_layer_id` applies it to the deserialized item **only if it still resolves in the target scene** (paste after File → New Plan, or into a different scene entirely, means the copied UUID no longer names a real layer) — falling back to the scene's active layer, else leaving the item layer-less exactly as before. Pinned by `tests/integration/test_stacking_roundtrip.py`'s paste/duplicate-ordering cases. Lesson: when a serializer's "core" dict is deliberately relationship-free (so it can be reused by both the full save path and the clipboard's need to drop parent/child links), check that it isn't *also* dropping a field the reused caller actually needs — `layer_id` was cut for the wrong reason and stayed cut for eight months.

- **Lesson (design review, #338): a refresh that writes model state breaks snapshot-based undo.** The stacking-order design went through two drafts that a design review caught before either shipped: (1) a "refresh also renumbers ranks" variant — since the z-refresh runs on many paths that have nothing to do with an explicit arrange (a layer visibility toggle, an opacity-preview commit, any unrelated command's cleanup pass), a command's undo snapshot taken before `execute()` would no longer match the ranks in force by the time `undo()` ran, silently breaking Ctrl+Z for any command that happened to trigger a refresh in between; and (2) a "provisional z assigned at add time, finalized lazily" variant, which breaks the moment an item is deleted from the middle of a layer — the reserved slots stop describing a contiguous order and a later finalize pass can't tell a genuine gap from a reusable one. The shipped design (ADR-043) keeps rank-writing to exactly four call sites and makes every refresh a pure read of whatever ranks already exist. General rule: any code path that both (a) runs unconditionally/opportunistically and (b) can be reached between a command's `execute()` and its `undo()` must never mutate the same state an undo snapshot depends on — if it needs to run there, make it derive its output instead of writing it.

- **Google's satellite tile `<img>`s taint any canvas — html2canvas-style capture is structurally impossible, and DOM tile URLs leak the API key** (#346 spike, 2026-09-01): measured inside QtWebEngine 6.10.2 against the live JS-API map with a real key: `fetch(tileUrl, {mode:'cors'})` returns 200 but the response carries **no** `Access-Control-Allow-Origin` header, and drawing a tile `<img>` onto a `<canvas>` makes `getImageData`/`toDataURL` throw `SecurityError` ("canvas has been tainted"). Additionally the tile URLs themselves (e.g. `maps.googleapis.com/maps/vt?pb=...&key=AIza...`) embed the API key as a query parameter — so harvesting them from the DOM and sending them to Python would pipe the credential through every log/error path in both directions. The working engine is the **widget grab** (`QWebEngineView.grab()` / `QWidget.grab()`), which renders at exactly `css_size × devicePixelRatio` (verified at dpr 1.0 and 1.25) and never touches the DOM. Rule: **pixels leave the embedded map only through the widget grab; metadata only through the QWebChannel bridge.** Never add DOM-side image extraction — it is not a "future optimization", it is a dead end by Google's own headers.

- **Subclassing `QWebEnginePage` to siphon `javaScriptConsoleMessage` hard-crashes the process** (#346 spike, 2026-09-01): overriding the console-message hook in a Python `QWebEnginePage` subclass (with or without calling `super()`) crash-exited the app with `STATUS_STACK_BUFFER_OVERRUN (0xC0000409)` and **no Python traceback** — first seen as the whole spike process dying with an empty exit. Symptom shape: a fatally clean exit, nothing on stderr. Rule: never subclass `QWebEnginePage` for telemetry; if a WebEngine page's console output is ever needed, use the remote-debugging/CDP route instead.

- **JavaScript `let` declarations never land on `window` — verification JS that reads `window.map`/`window.bridge` from a page written with top-level `let` returns `undefined` forever, even when the page state is perfectly healthy** (#346 live harness, 2026-09-01): the picker page (and the spike before it) declares `let map`, `let bridge`, `let drawingRectangle`. Polling `runJavaScript("window.map")` is therefore a blind probe — it reports "not ready" while the map is on screen. Use `runJavaScript("typeof map !== 'undefined' && map && ...")` (page-scope evaluation), or expose a dedicated status function on `window` from the page itself.

- **`QDialog.accept()` hides the window — a live harness that watches for the accepted result can see the whole app exit first** (#346 live verification, 2026-09-01): the capture flow ends with `dialog.accept()`, which sets the result AND hides the (only) window; with `quitOnLastWindowClosed` the event loop ends before the harness's next poll tick can read `fetch_result`. The capture had succeeded — the run just ended too fast to print it. Lesson for live-verification harnesses: hook the *accept* itself (or connect to `finished`), never poll the result from a timer that can lose the race.

- **A real short-interval `QTimer` racing pytest-qt's `waitUntil` loop segfaults the linux-offscreen suite — drive timer-handler coverage by emitting the signal instead** (#346 finalization, 2026-09-01): three capture tests set the dialog's 20 s watchdog to a 10 ms interval and `start()`ed it inside a `qtbot.waitUntil(...)` poll of the handler's side effect. Local Windows was green; the windows-differ linux-offscreen CI run aborted with `Fatal Python error: Segmentation fault` — always inside `TestMinimapIdleQuiescence` (an *unrelated* file whose quiescence counting is a natural crash site for corruption planted earlier), at a different member test each run, at the same 66% suite position. Diagnosis recipe that pinned it: (1) trigger master's own CI via a throwaway probe branch (ruled out a runner-flake; master was green); (2) bisect across CI runs — disabling the two new test files → green; re-enabling the unit file → green; skipping all tests but collecting the file (`pytestmark = skip`) → green (collection-time imports innocent); halving the classes (skip ErrorMapping/Eea/RoundTrip/Bridge) → red; only ButtonLifecycle → green; only Success → green; only Cancel without watchdog tests → green. The three watchdog tests were the only red constellation — the combination of a real 10 ms single-shot racing the pytest-qt poll loop was the difference. Fix: emit the timer's signal directly (`dialog._capture_watchdog.timeout.emit()`) — identical handler coverage, zero timing races — and keep the real watchdog timing to the live E2E harness. Rules: never `setInterval(10)+start` a *widget-owned* timer inside a `waitUntil` in a Qt test — if the goal is handler logic, emit the signal; if the goal is real timing, use a live-session harness. Watch out when re-adding: pytest collects `*_test.py` module-level imports in alphabetical file order, so a new test file's *module imports* change nothing here — the poison was execution, not collection.

- **The canonical translation workflow is `fill_translations.py` alone — running `pylupdate6` over the source tree churns the entire `.ts` and marks whole contexts "vanished"/"unfinished"** (#347 finalization, 2026-09-01): adding four strings to `map_picker_dialog.py`, a straightforward `pylupdate6 --ts ... src/open_garden_planner/` re-extraction produced a ~12 000-line diff: every `<location>` line number in the file had shifted, hundreds of untouched messages were re-tagged (the gate than failed with 8 + 539 "unfinished"), and — because the tool has no `-recursive` and rejects directory args containing `..` — replicating the "canonical" full-tree scan was impossible (single-file runs mark everything else vanish/obsolete; running per-directory from `resources/translations` crashed with `FileNotFoundError` on `..\\ui\\icons.py` due to the two-`..` nesting). The actual pipeline the previous PRs used: **new strings are added to the `.ts` by `fill_translations.py` itself** (as location-less, pre-translated messages — the "ADDED [context]: …" output), and `pylupdate6` is effectively never re-run over the tree. Symptom shape: a PR's `.ts` diff exploding into tens of thousands of moved lines while the i18n gate goes red on strings you never touched. Rules: (1) when adding a user-visible string, register it in `scripts/fill_translations.py` and run **only** `fill_translations.py` + `compile_translations.py` — do not re-extract; (2) if you ever do run `pylupdate6`, expect the whole file to be rewritten and the diff to be mostly churn (that alone is a smell; the previous PRs' `.ts` diffs are ~60 added lines) — and be ready to add every newly extracted context to the fill dict, since pylupdate extracts strings under contexts the dict has never heard of (e.g. the tool modules' `QCoreApplication.translate("OffsetTool", …)`, which previously only existed as location-less fill entries under `CanvasView`).

- **JS-side guards comparing a NUMBER token with its STRING form silently eat every capture report — the capture "times out" while every test is green** (#347 live manual test, 2026-09-02): the new capture choreography's page-side guards read `if (!captureState || captureState.token !== String(token)) return;`. Python calls `window.beginCaptureChrome(1)` — a JS **number** literal — so `captureState.token` was a number, `String(token)` a string, and `1 !== '1'` was **always true**. Every profile/frame readiness report died in the guard; Python's 20 s watchdog then popped "The capture timed out — check your network or the API key" while the map was perfectly healthy. All 109 automated tests were green because they drive the QtWebEngine-free bridge directly and never execute the page's JavaScript. The `TestBridgeContract` drift guard only greps function *names*. Fix: stringify at **storage** (`captureState = { token: String(token), … }`) so the echo comparison is string-vs-string; the drift guard now also pins `token: String(token)` in the HTML. Proof: `scripts/live_capture_harness.py` (real dialog + real map + real key) showed `js_result 'ok'` then silence; after the fix it shows the full profile → frame → stitch sequence completing. Rule: **any page-side guard that compares a value echoed from Python must stringify BOTH operands (or store stringified)** — Python hand-builds JS literals, and `1 !== '1'` is a silent always-false guard, exactly the failure shape that automated tests cannot see (same lesson as #346's live harness — the page's JavaScript is only exercised by a live run).

- **A `file.py:line` citation drifts silently when unrelated features grow the file — measured, not hypothetical** (#336, 2026-09-04): nothing verified that the identifiers cited across the `SKILL.md` files in both `.claude/skills/` and `.agents/skills/` plus `CLAUDE.md`/`AGENTS.md` still resolved. The motivating data point: `deliver-package` (PR #334, written one day earlier with unusually careful sourcing and a senior-reviewer pass) still shipped three citation errors, found only by hand — a package range that mixed in an unrelated epic and a standalone issue, two issues wrongly described as having GitHub sub-issues, and a closed issue cited as an example of "an open issue". Building `scripts/check_skill_citations.py` (§8.10) and running it cold against the existing corpus found one more, live: `ogp-architecture-contract`'s note that the Smart Symbols sidebar panel is hidden "via one line" cited `application.py:1574`; the line is now 2893 — 1319 lines of drift from Google Maps/satellite-import features (#342/#346/#347) landing in between, in a 6700-line file. Two other skill files (`ogp-config-and-flags`, `ogp-research-frontier`) carried the same stale line number for the same fact — a single piece of knowledge, copied three times, rotting once and not being noticed twice. Fix: correct all three, then gate it — the checker resolves *identifiers* (does a heading/ADR/FR/symbol/issue-number still exist), not *claims* (is the surrounding prose still accurate), and tolerates trivial refactor churn by accepting a `file.py:line` citation whose named symbol is still found within a small window of the cited line rather than demanding an exact match. Lesson: a fact copied into N documents needs N independent chances to rot and one shared chance to be caught; a citation gate pays for itself the first time two of the three copies are wrong and nobody had reason to open the third.

- **The citation gate's own senior review found the gate had almost no teeth on the dimension that motivated it, and the fix needed its own mutation-tested regressions before it actually had any** (#336, 2026-09-05): round 1 of review found `_extract_symbol` took the *leading* identifier of a cited snippet (`self._sidebar_controller.set_panel_visible(...)` checked for `"self"` — present on nearly every line of any class body), a repeated regex capture group that silently dropped every middle number in an `ADR-a/b/c` list, and a `KNOWN_EXCEPTIONS` declared as a `frozenset` but built by calling `frozenset()` on a **dict literal** — which iterates only the keys, discarding every stated exemption reason without a type error anywhere. Fixing the leading-identifier bug and adding a "regression test" for it both landed **green on the unfixed code**, because the one corpus citation exercising that shape had been rewritten (to drop the `self._x.` prefix) in the same commit as the fix — the test asserted the citation *now* passed, not that the *specific defect* was caught. Only reproducing the bug via mutation (temporarily reverting `_extract_symbol` to `text[:leading identifier]` and re-running the suite) showed the "regression test" was vacuous; the fix that made it non-vacuous was a fixture engineered to contain no string literal at all, so the (separately correct) literal-proximity check couldn't accidentally mask which identifier got extracted. Lesson, general: a regression test for "citation X used to slip past check Y" only has teeth if X *itself*, not a fixed-up copy of X, is what's asserted against — and the fastest way to know is to reintroduce the bug and watch the test go red (the same rule §8.10 states for guards in general, applied to the guard that watches every other guard's citations). Separately, the issue-number check depends on a snapshot (`tests/data/issue_registry.json`) refreshable only by an authenticated `gh` CLI on a dev machine — CI cannot regenerate it, so a PR that adds a genuinely new `#NNN` reference to a skill file must run `scripts/refresh_issue_registry.py` locally before pushing, or `test_real_corpus_citations_all_resolve` goes red for a reason the CI log alone won't explain.

- **A drift-tolerance window that is merely "generous" is a false safety claim, not a weaker one** (#336, 2026-09-05): a follow-up review demonstrated that requiring a symbol span (see above) did not, by itself, close the gap it was built for. The original `_SYMBOL_WINDOW_LINES = 300` was chosen to comfortably survive the ~1319-line drift already found in this file's own motivating example — but measured directly, `core/object_types.py:595` `is_bed_type` (the citation later found to sit 76 lines from the real `is_bed_type`) resolves cleanly at a 300-line window *with the correct symbol attached*, because 76 &lt; 300. Worse, for a common name in a large file (`core/commands.py`'s `execute`, which appears on 76 of 2861 lines) essentially every possible line number in the file passes at that width — the "drift check" had no power at all for that citation. The module docstring asserted the mandatory-symbol rule had already fixed the motivating bug; it had not, and shipping that claim uncorrected would have been the exact "documentation says something the code doesn't do" failure this whole issue exists to catch. Fix: shrink the window to 20 lines — small enough to be below every real drift incident this project has measured (76, ~510, ~1300), large enough to tolerate a docstring or unrelated line inserted just above a citation's target. A symbol moving further than 20 lines now requires a one-line citation fix, which is the gate doing its job, not a false alarm. Lesson: a tolerance window's job is to sit strictly below the smallest real defect you want to catch — picking a width that merely "feels generous enough" and never checking it against a measured incident produces a check that passes by construction rather than by evidence, and the only way to know which one you built is to run the exact rot you're worried about through it before trusting the number.

**Named residual, measured, not swept under the fix**: shrinking the window controls for drift *distance*; it does nothing for symbol *selectivity*. `execute` — the very name used in the motivating `core/commands.py` example above — occurs on 76 of that file's 2861 lines, so even the 20-line window still lets a citation to `execute` resolve against 2351 of 2861 possible line numbers (82.2%); at every candidate line, some `execute` is always within reach. A citation naming a common, generic identifier in a large file is real but weak protection: it catches "the file got so much smaller/bigger that nothing named `execute` remains nearby" and nothing subtler. The corpus's actual citations are unaffected today (every one of them sits at distance 0 from its symbol, verified), but the next contributor who cites a common name in a big file should know the check they're relying on is thinner than "the gate passed" implies. Closing this for good needs a selectivity rule (reject a symbol match against more than a couple of candidate lines in the window, or require a `def`/`class` form when one exists) — filed as follow-up work, not done here.

**Agent creation must share the loader's construction path and its undo
boundary (US-D2.5, #329).** The tempting implementation is to instantiate each
shape class directly from its geometry parameters, but that creates a second
set of defaults and serialization assumptions beside
`ProjectManager._deserialize_item_core`. The safer contract is a Qt-free
validation/dict builder followed by the loader on the Qt main thread;
integration tests then prove the saved snapshot and live geometry agree. The
same boundary matters for composites: a `HOUSE`'s derived `ROOF_RIDGE` is
created in the same `CreateItemsCommand`, so one agent call has one Ctrl+Z
step and cannot leave an orphaned ridge. Callout UUIDs are persisted explicitly
because a visually correct callout whose id changes on save/load breaks every
subsequent agent reference. The durable lesson is to test create -> read ->
save/load -> read, not only the immediate canvas item, and to make every
deliberate unsupported type visible through the discovery tool and a drift
guard.

**A same-scene project load can leave stale callouts/curves, and UUID lookup then turns a delete into a false success (issue #353, 2026-09-24).** Symptom: after saving and loading into the same `CanvasScene`, `list_layers.object_count` exceeded the top-level objects returned by `list_objects`; a concurrent-looking `delete_object` could return success while a same-ID callout remained. The first hypotheses — a command-manager race or a need for a second global lock — were wrong: `MainThreadBridge` already serializes Qt work, and the actual source was `_deserialize_to_scene`'s stale explicit type tuple, which omitted `CalloutItem`, `ArcItem`, and `BezierItem`. The fix centralizes a serialized-document-item predicate (while preserving compare/dimension overlay owners), refuses duplicate live UUIDs before deletion, and verifies target absence before returning success. Lesson: a UUID write API must treat scene identity invariants as part of its postcondition; a command completing on the main thread is not proof that the addressed object is gone.

**A finite float is not a safe Qt geometry input, and JSON normalization can turn hostile Infinity/NaN into an apparently valid default (issue #355, 2026-09-24).** Symptom: `1e308` callout offsets were rejected only after probing, while Infinity/NaN sent through the real MCP client arrived as `null` and were treated as omitted, creating a normal callout instead of failing. The root cause was not Qt alone: the API boundary's finite check ran too late, after Pydantic/JSON had already erased the distinction. The fix validates signed offsets against `2 * max(canvas_width_cm, canvas_height_cm)` in the Qt-free creation boundary, uses an omission sentinel in the MCP handler, and rejects explicit null before provider dispatch. Refusals occur before the loader and command, so the scene and undo stack remain untouched. Lesson: hostile-input tests must cross the real transport; a direct validator test cannot see a transport's null normalization.

**A single wall-clock CI sample cannot distinguish a scheduler spike from a spatial-index regression (issue #354, 2026-09-24).** Symptom: one Python 3.11/Linux run measured 284.1 ms against a 250 ms hard limit while a parallel run and the complete local suite passed; the branch did not touch the spatial-index implementation. Repeating the old test unchanged would preserve the flake. The fix warms the path, records five rebuild and five query samples, and gates medians (200 ms build, 1 ms query) with the sample list in the failure message. Repeated local Python 3.12/Windows samples were about 15 ms median, and the historical 284 ms observation is retained as the calibration outlier. Lesson: performance tests should protect a sustained regression statistically, not assert that one shared runner owns a quiet CPU; report the distribution when the platform is noisy.

**A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver** (US-D2.6, #330, 2026-09-25): the tempting shortcut was to reuse `get_object(raw=True)` and the serializer's polygon points. That is wrong for an edit contract — serializer points are pre-rotation storage, while the agent needs the vertices' current scene positions; at 215° the two frames visibly diverge. The inverse shortcut is equally subtle: `mapToScene` followed by `mapFromScene` moved a rotated polyline by about `5.7e-14 cm`, enough to make an unchanged request look like a real mutation even though the drift was invisible. `ui/canvas/geometry_inspect.py` therefore maps live vertices with `mapToScene`, and `geometry_apply.local_vertex_for_scene` reuses the exact local `QPointF` for an unchanged request within `1e-9 cm`. `set_vertex` then refuses that unchanged request as a no-op before any command is built, so the read/write pair cannot pollute history. The second trap is policy: the live constraint solver can move several connected items, so a one-shot agent tool that moved only the addressed object would silently violate intent. `_agent_require_unconstrained` now refuses every geometry write with the blocking constraint type/UUID, while unauthenticated `get_geometry` lists those constraints. Refusals happen before command execution, so scene, graph, history, and dirty state stay untouched. Pinned by `tests/integration/test_agent_api_geometry.py::test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly`, `tests/integration/test_agent_api_writes.py::test_constrained_geometry_read_succeeds_but_every_d26_write_refuses`, and the default-on orchestration tests. Lesson: for geometry APIs, document and test the coordinate frame at the transform boundary; for multi-item solvers, a refusal with an inspectable reason is safer than a partial mutation.

**A derived child must be recomputed from its owner, never re-projected from its own current state** (issue #364, 2026-09-29). Symptom: a HOUSE's auto-created roof ridge drifted off its polygon and never recovered — after `add_vertex` the second endpoint stuck to a new slanted edge, and **undo restored the polygon exactly while leaving the ridge 36 cm away** on a 300×200 cm house, accumulating over repeated cycles. The house looked perfect, so the defect was invisible unless you measured the ridge endpoints. The first hypotheses were wrong in the same direction: it was not the vertex command, the constraint solver, or the D2.6 work that introduced it (`git log -S` put `_update_ridge_on_boundary` in `818e3fb`, #114, two years earlier — D2.6 only added a *call site*). The real cause was that the sync was a **membrane, not a recompute**: it re-projected the ridge's *existing* endpoints onto the boundary, so a once-perturbed endpoint had no path back to canonical, and the direct `ridge._points` write bypassed the command system so no undo step could restore it. Measuring the same code against a *rotated* house then exposed a second, larger defect nobody had reported: the membrane kept the ridge's old orientation, so a house rotated 30°/90° kept a ridge at 0° — **75 cm / 180 cm** off, and since `_paint_with_ridge` mirrors the roof texture along that line, **every rotated house rendered a wrongly-oriented roof**. The fix recomputes through the one canonical `compute_roof_ridge_endpoints`, computed in the polygon's **local** frame and mapped through the item's full transform. The local-frame detail is load-bearing and contradicts the obvious reading: the issue's own suggested fix ("call it with `pos`") returns a 0° ridge for a 30° house, because that formula adds `pos` to local points and ignores the transform — it is only correct for an unrotated item, so following the issue verbatim would have fixed the filed symptom and left rotation broken. Pinned by `tests/unit/test_roof_ridge.py`, parametrised over four transforms — unrotated, 30°, 90°, and 45°/scale 1.5. The module collects 26 cases; measured against master's `polygon_item.py` and `canvas_view.py`, **21 fail and 5 pass** — the 5 being the four boundary-invariant cases (the old projection satisfies those by construction) plus the unrotated rotation-tracking case, whose orientation defect is zero at rotation 0. That is 15 of the 20 `TestRidgeDriftOnUndo` cases, plus all of `TestResizeUndo` and `TestHandMovedRidgeEndpoint`. The `TestResizeUndo` cases fail at **300 cm** when the single sync line is removed from the fixed tree — they import the function the fix introduces, so on master they stop at an `ImportError` rather than observing the drift. The two defects differ: the **drift** reproduces at *every* transform including unrotated — which is how #364 was filed — while only the **orientation** defect is zero at rotation 0. A second pass found the first fix was **incomplete**: the `ResizeItemCommand` apply closure (a *fifth* polygon-apply path, not one of the four the sync is called from) never re-derived the ridge, so undoing a HOUSE resize left the ridge sized for the resized house — 300 cm of drift, persisted into the `.ogp` because the ridge is itself a serialized item. No test anywhere resized a HOUSE, so 6509 green tests missed it, and senior review caught it. A third round found a **sixth** writer: the constraint solver's `finally`, which restored a polygon with a bare `setPolygon` while its polyline sibling restored through the override that does re-derive — asymmetric in the same file, 150 lines from the one already fixed. Both were found by review, not by tests (ADR-046). Lesson: when one object is derived from another, ask whether the sync *recomputes* or *adjusts* — an adjustment is a second source of truth that no undo can own — and then confirm that **every** writer of the owner's state re-derives it, because fixing the paths you can see leaves the ones you cannot; and when a geometry helper takes a position argument, check whether it is correct under rotation before reusing it, because "works at the default value" is the signature of the same class of bug.


**A derived texture's orientation is gravity-relative, and naming a half "left" does not make it the downhill side** (issue #372, 2026-09-30). Symptom: a HOUSE's roof tiles lapped back **up toward the ridge** on both halves - they read the same outward sequence, being mirror images of each other, so the inversion could not show on one side only - so water would run uphill under the laps, reported by the owner as "regardless of whether I paint a vertical or horizontal house, it is always the wrong direction", a phrasing that is the whole diagnosis. The two first theories were both wrong in an instructive way: the *rotation* was not broken (the transform was computed and applied correctly, provable in isolation), and the *texture* was not upside-down (its `+Y` is genuinely down-slope: a dark lapse line near `y=10` with the light free edge beneath). The halves were assigned by `_split_path_by_line`'s `left`/`right` naming, which follows the left-perpendicular `n = (-uy, ux)` and therefore the ridge's **direction** - for a +X ridge `left_path` is the LOWER half, for a +Y ridge it is the LEFT half. The half that needed the texture's true down-slope was the one being handed the mirror, so the error tracked ridge direction rather than gravity and appeared at every angle. Measured through the production paint path, the two builds differ in **absolute phase** while staying mirror-symmetric: fixed `RBBRBB`, pre-fix `BRRBRR` on both halves. Third lesson, and the one that nearly cost the fix itself: **check that your measuring instrument reaches the code under test.** A test harness called `scene.removeItem(ridge)` to stop the ridge's stroke covering its sample points - which made `_find_ridge()` return `None`, which means `_paint_with_ridge` is never called at all. Every render then measured `super().paint()`, the fallback fill that both builds share, and the fix hashed byte-identical. A "no-op" measured by an instrument that bypasses the code is not evidence of a no-op; when the reviewer reported that the test did not call production code, the correct response was to re-measure the *fix* with a corrected instrument, not to conclude from the broken one. Hide the obstacle with `setVisible(False)` - **not** by clearing its pen, which does nothing here because `_paint_roof_ridge` strokes three *hardcoded* pens and never reads `self.pen()` - and never remove the thing whose presence gates the code path. The same class of bug appeared twice more in the same file: the ridge points were run through `house.mapToScene` although they are already scene space (since #364), so the harness sampled 30 degrees off the real ridge normal at 30 degrees of rotation and invented a "degenerate" band at 90/270 that does not exist. **A fourth trap was a test that looked thorough and pinned nothing:** it swept the house's *rotation* across nine angles and called that angle coverage, but the angle `_paint_with_ridge` feeds to `normal_tx.rotate()` is the ridge direction in the polygon's **local** frame, which `compute_roof_ridge_endpoints` pins to the longest bounding-box axis - 0 for a landscape house at *every* rotation, 90 for a portrait one at every rotation (measured by spying on the value). Since `rotate(-a)` and `rotate(+a)` are the same transform when `a` is 0, a rotation-only sweep is structurally blind to a negated sign, which is the very term the swap argument rests on. Adding a portrait house caught it immediately: negated, the landscape cases still read `RBBRBB` and all four portrait cases read `BRRBRR`. **When a test sweeps a transformation, check which quantity the code under test actually consumes** - an item transform, a local-frame angle and a scene-frame angle are three different things, and only one of them is what a rotation sweep moves. The fix is a swap, not a probe, because of an exact identity: `normal_tx` is `translate . rotate(angle)` and a `QBrush` samples the texture at `T^-1.p`, so texture `+Y` lands at `R(angle).(0,1) = (-sin a, cos a)` - precisely `n`. **Lesson: a geometric naming convention is not a physical one.** Whenever a half, a side, or a region is named by geometry (left/right, near/far, first/second), check that the name survives rotation before branching on it. Second lesson, about the measurement itself: correlating the real 256 px tile texture against the render had **no discriminating power** - peak correlation ~0.03 either way, with the diagonal case a 0.020-vs-0.019 coin flip - because a few hundred sampled pixels span barely one texture period, and a metric that cannot separate right from wrong will happily pass broken code. The fix came from replacing the texture with a **two-colour probe** (red on top, blue on bottom, so blue *is* the down-slope) and sampling a six-point sequence outward from the ridge. When a rendering assertion will not separate, change what it measures rather than loosening the threshold. And note what it took to see this at all: a green 6515-test suite, because nothing in `tests/` had ever looked at a rendered roof pixel.

**An issue's "verified repo facts" are a claim about the code, not the code — and a rule that
sounds reusable can be structurally blind to the case in front of you** (US-D3.2, #331)

Four of #331's own "verified repo facts" were wrong, and three of the four would have produced
a plausible, tested, wrong implementation:

1. It described **three** season segments (`spring`/`summer`/`fall`). `models/succession.py`
   has always had **four** (`early_spring`/`late_spring`/`summer`/`fall`), with boundaries in the
   module docstring. Building to the issue's prose mislabels a third of the growing season. The
   issue's *acceptance criterion* ("labels matching the module's own segment definitions - pinned
   against the documented formulas, not against a re-implementation") was the correct instruction
   and was followed instead. **An acceptance criterion that contradicts the issue's own context
   is usually the accurate one.**
2. It said a plan with no geo-location has "unknown" season segments, implying new code. The
   succession **dialog already had** a calendar-month fallback, as a private table. Copying it
   would have given an agent and the GUI two definitions of "summer" for the same bed. It was
   moved to `models/succession.py` and both callers now use
   `resolve_season_segments(year, location) -> (segments, are_fallback)`.
   **`is the behaviour absent, or just absent from where you looked?`** An issue describing
   something as missing is evidence about the issue, not about the repo.
3. It said to reuse `crop_rotation_service` "rather than re-derive family rules". The cross-year
   cooldown *is* reused verbatim. But the acceptance criterion - never propose a crop that
   conflicts with **an earlier entry in the same bed** - is unmeetable by
   `check_plant_placement`, which compares a candidate only against `records[0]`, the single most
   recent planting record. It cannot see "tomato after the garlic entry three slots ago".
   Succession is several crops in ONE season; that service models one record per season across
   YEARS. And succession entries never enter rotation history at all, because only the Crop
   Rotation panel writes `PlantingRecord`s. **A reusable-looking method can be blind to the shape
   of the question.** Two unrelated mismatches (arity and history-provenance) had to be checked
   separately, and either alone would have produced a call that looked right, passed a casual
   test, and excluded almost nothing.
4. `commands.py:2472` for `SetSuccessionPlanCommand` was ~216 lines stale (it is at 2688).

**Lesson: verify every `file:line` and every "reuse X" instruction against the code before writing
a line, and treat an issue's context section as a hypothesis.** The costs here were cheap only
because the check was done first; the third one in particular would have shipped a tool that
excluded almost nothing while reporting a rotation check it had not performed.

**Corollary - `species_key` is a function, not a field.** The first draft of `suggest_succession`
read `getattr(record, "species_key", "")` off each candidate and got `""` for all 118 bundled
species, so every call returned an empty list - a result that reads as "no candidates", the exact
silence this project forbids. `species_key(species_dict)` (`models/plant_data.py`, ADR-016) is a
module-level function whose priority is `source_id -> scientific_name -> common_name`, so a
bundled plant's key is its **scientific** name: `"phaseolus vulgaris"`, not `"beans"`. Nine unit
tests failed identically, which is what identified the shared root cause instead of nine separate
bugs. **When many tests fail the same way, find the shared assumption before fixing any of them.**


### 11.4.1 Three guards in the wrong place (US-D3.2 final pre-merge review, #374)

The `set_succession_plan` work passed 6635 tests, an out-of-process dogfood
harness, and a real manual test in the built exe. The final review still found
three defects, and all three are the same mistake: **a guard that sits at the
wrong boundary**. Each one was fixed and pinned by
`tests/unit/test_agent_succession_review_fixes.py` (21 tests, each failing
against the pre-fix code).

1. **A guard around the parse does not cover the parse's consequences.**
   `PlantingRecord.from_dict` does `data["year"]` and never type-checks, so a
   `.ogp` carrying `{"year": "2025"}` produced a record whose `year` was the
   *string* `"2025"`. Both readers caught four enumerated exception types around
   the `from_dict` call - and the row sailed through, because nothing had thrown
   *yet*. The `TypeError` arrived later, inside `get_records_for_area`'s sort:
   outside the loop the guard was protecting, and inside a Qt signal handler
   whose own handler catches only `RuntimeError`. That is an uncaught exception
   in the event loop, the `qFatal()`/abort shape #366 recorded. **Enumerating
   exception types at an ingestion seam is a guess about a parser you do not
   control; catch broadly (invariant 14: a `.ogp` is untrusted input) AND
   validate the field you actually depend on** - here
   `_read_crop_rotation_record` in `app/application.py` catches `Exception` and
   requires `isinstance(rec.year, int)`. A list year, a `None` year and a
   missing year are now all dropped instead of detonating later.

2. **Re-resolving a name through the bundled DB silently drops every
   non-bundled species.** The write validator collected species *names* from the
   bundled database plus the plants placed on the canvas, then pushed all of
   them back through `lookup_species` to get keys. A Permapeople or custom
   species has no bundled record, so it resolved to `None` and was skipped: the
   roster missed every custom plant, and `set_succession_plan` refused a species
   the app had just shown the agent - while the sibling tool `set_species`
   accepted it. **Three agent tools disagreeing about one plant is a worse
   failure than any one of them being wrong**, and it was invisible because
   every bundled species worked. The validator now derives keys directly,
   `_agent_known_species_keys()` calling `species_key(dict)` (ADR-016) on the
   plant's own `metadata["plant_species"]`, never a round trip through the
   bundled index. Same class as the `species_key` corollary above: **derive the
   key; do not resolve a name back to the thing you already had.**

3. **A stored object that holds one year must not answer a question about
   another year.** `get_succession_plan(bed_id, year=2027)` on a bed holding a
   2026 plan returned `has_plan: true`, 2026 entry dates, and `season: null` on
   every entry - because the season is derived from the requested year and the
   dates are not. `null` reads as a data fault, not as "that is next year's
   question", so the agent had no way to tell a mismatch from corruption. The
   view now reports `has_plan: false` and carries a `plan_year` field naming the
   year the bed actually has. **When a store is keyed by a dimension the caller
   supplies, an explicit parameter that does not match the store is a miss, not
   a hint to return the wrong row** - and the miss must be legible in the
   response shape.

The common thread: each guard was written where the *code* was, not where the
*trust boundary* or the *key space* is. Review found all three; the suite and the
dogfood harness found none of them.

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

### 11.4.4 Review and frozen-client findings in D3.3/D3.4 (#332/#333)

- **Call the public tool with the production provider graph.** The first
  handover reported 6951 passing tests, but a real MCP client against the frozen
  exe found `get_soil_status` failing with six missing model fields,
  `get_soil_mismatches` failing with missing `total`, and the soil prompt failing
  likewise. Providers returned aggregate `beds` envelopes while the server
  constructed single-bed models. The purported real-client suite only called
  provider methods and prompt renderers directly. Explicit aggregate schemas
  now preserve per-bed coverage; the prompt extracts its requested bed.
  `TestRealMcpTransport` in `tests/integration/test_agent_task_soil_tools.py`
  calls all nine tools and both prompts using `app._build_agent_providers()`.
  Four status/prompt tests and a separate mismatch test were observed failing
  before the fix. Stub registration and direct provider success are evidence
  about different boundaries.
- **Generate a requested period before applying urgency.** A plant with April
  sowing and June/July harvest returned an empty, fully-covered annual calendar
  when queried in October. Future years were also empty because `year` never
  reached generation. `actionable_only=False` retains the schedule for agent
  annual/explicit-window reads while GUI reminders keep their existing default.
  A December-to-January task was dropped from both years; intervals are now
  clipped to year boundaries. Pinned by
  `test_calendar_generates_the_full_requested_year`,
  `test_explicit_task_window_generates_its_calendar_tasks` and
  `test_calendar_clips_cross_year_tasks`, all observed failing first. Propagation
  was absent because no plans were supplied to its generator. The extracted
  `build_propagation_plans` is now shared with the GUI and honors seed data and
  user overrides; `test_propagation_tasks_use_the_gui_calculator` failed for both
  current and future years before the fix.
- **Provenance and staleness must follow the same selected record.** An old
  global test was reported with `record_source=global` and
  `is_test_overdue=false` because staleness checked the bed's empty history.
  The service now resolves record/source/history together, and the existing
  record-only method delegates to it. Pinned by
  `test_global_fallback_uses_global_history_for_staleness` (failed first).
- **Language and input types must be checked at the actual boundary.** A
  German amendment test pinned English names, contrary to the API contract.
  Recommendation names now use the existing `Amendment.display_name(language)`;
  `test_amendment_names_follow_the_ui_language` failed first with English
  `Dolomite lime`/`Compost` versus `Dolomitkalk`/`Kompost`. MCP's permissive
  numeric validation also converted booleans and numeric strings into soil
  readings before the stricter domain validator saw them. Strict numeric
  annotations prevent that; three malformed-input transport cases failed first.
  The translator unit test now requests `qtbot`: it previously depended on an
  unrelated test creating QApplication, so a targeted run failed while the full
  run passed.

- **The requested year is not necessarily a task's frost-anchor year.** Round
  two reproduced bundled garlic sowing on October 15–29, 2026 only when the
  request extended into 2027. Bundled asparagus harvest uses offsets 104–156
  weeks, so a 2026 calendar must also consider prior anchors. Period generation
  now derives an anchor range from the actual calendar and propagation offsets,
  filters overlapping dates and preserves canonical anchor-year IDs. Annual
  calendars and task windows share this path. Both the garlic integration test
  and `test_bundled_multiyear_harvest_includes_prior_frost_anchors` failed first.
- **No recommendation is not a soil-health assessment.** An existing lab-only
  record (`n_ppm=100`, no kit levels) correctly returned unknown health and no
  amendments, yet the prompt claimed every measured value was near target.
  Neutral prompt/tool prose now states the engine's limited conclusion and
  names the unconverted lab readings. The real-client
  `test_lab_only_reading_is_not_presented_as_near_target` failed first.
- **Absolute dates need an absolute identity.** Wider frost-anchor generation
  reapplied a saved March 10 propagation override for every anchor, making three
  tasks in an annual read and five in a three-year read. The dates agreed but
  anchor-year IDs differed, so deduplication failed. The shared propagation
  generator now assigns overridden steps to their start-date year; relative
  steps retain anchor-year IDs. GUI and agent therefore agree.
  `test_absolute_propagation_override_has_one_shared_identity` failed first and
  checks identity, one result, GUI convergence and annual month counts.

### 11.4.5 The Qt Quick 3D spike: engine traps, and a "hang" that was a stopwatch problem (ADR-048, Phase 17 L0)

Each of these cost a round trip during the L0 spike. The engine facts are kept
current in the `ogp-3d-renderer` skill; this entry records why they bite.

**1. A headless 3D test needs a real RHI context.** The `offscreen` QPA plugin
selects the *software* scene graph, which renders no 3D at all — the frame is
empty, not wrong. Linux render tests run under `xvfb-run` with
`QT_QPA_PLATFORM=xcb` and `QSG_RHI_BACKEND=opengl` (Mesa llvmpipe), which needs
`libegl1` and `libxcb-cursor0`. Calling `QQuick3D.idealSurfaceFormat()` before the
`QGuiApplication` exists segfaults.

**2. Conventions that read as art bugs.** A `DirectionalLight` has no `lookAt`
(cameras do) and shines down its local −Z, so an un-oriented sun leaves only sky
light: the first renders were uniformly pale blue. Models use `castsShadows`,
lights `castsShadow`. `ProceduralSkyTextureData` puts its sun at compass bearing
`sunLongitude − 90°`, and the scene environment pre-filters its light probe
**once per Texture object** — updating the texture's properties moved nothing, so
the sky's sun stayed in the north until each sun change built a fresh Texture.
Both are pinned by the spike's sky probe, which reads the disc 25° off-centre (max error 0.85° on OpenGL and 1.4° on D3D11, including up to ~0.6° of the probe's own model error before its bearing maths accounted for the camera pitch).

**3. The `QQuickWidget` host was broken in two ways no screenshot showed.** It has
no `frameSwapped` (frames are counted on its offscreen window's
`afterRendering`), and `QQuickWidget.update()` only re-composites the last texture,
so a "wait for a new frame" loop waited forever. Its window's `isExposed()` is
always False. And the first split-pan measurement said the 3D widget made 2D
panning **70× faster** (0.08 ms vs 5.45 ms): a synchronous `repaint()` never
reaches the flush, which is exactly where a `QQuickWidget` makes the whole window
pay for RHI composition. Measured with event processing, the cost is ×1.42 on
llvmpipe. *A benchmark result that is better than the no-op baseline is a broken
benchmark.*

**4. A QML function's returned object is a `QJSValue`, not a dict** — call
`.toVariant()`. The picking helper had never been exercised and failed on its
first use.

**5. The 56-minute "hang" that was a stopwatch problem.** Windows evidence run
v1 built the frozen exe, passed `--selftest`, then ran the spike for 56 minutes
until the job limit killed it — with no output. Three things made it
uninvestigable: a GUI-subsystem exe has no stdout (`print` is a no-op, the #291
precedent); `Start-Process -Wait` has no timeout; and the artifact host is not
reachable from where the log was read. After the spike learned to write its own
timestamped log, per-phase metrics and a `faulthandler` watchdog, run v2 showed
frames arriving about once a second under Direct3D 11 on WARP — and **one
`grabWindow()` of the sky-lit scene taking ~100 s**. v1 had simply asked for
many of those. *Tooling that must run headless writes its own evidence; without
timestamps, "slow" and "hung" are indistinguishable.*

**6. A geometry does not survive its Model, and an array repeater kills every Model.**
The Windows run's picks came back 0/20 while the container's were 20/20 — not a
platform difference: the Windows command ran the IoU and orientation probes first,
and both swap the scene's models out and back. Once the Model using a
`QQuick3DGeometry` is destroyed, handing the same geometry to a new Model renders
nothing and picks nothing (the frame equals an empty scene's); `update()` does
not restore it, a full re-upload does. And a `Repeater3D` over a JS array
recreates **every** delegate on any change, so a model present before and after
the change came back blank too. The first fix re-uploaded only removed models and
measured 19/20 — the miss was the model that had never left. *A probe that
mutates shared state must restore it through the same path the product uses, and
the measurement that follows it must run in the same order in CI as on the dev
box.*

**7. A gate on `*.yml` sees temporary workflows too.** The evidence workflow
copied the frozen-exe `Start-Process` gate shape and turned CI red through
`tests/unit/test_gate_commands.py` (Rule 1: the command has one home,
`ogp-change-control` §2.8). The fix was not a second copy of the gate: the
evidence run goes through a driver script with a hard timeout and does not
repeat `--selftest`.

**8. A keep-alive list is a leak with a good excuse.** A texture created in
Python is owned by Python, so the spike appended every ground texture to a list
to keep it alive while QML showed it. The first soak with real project reloads
(plan from disk into a new scene, ground re-baked, every model and geometry new)
exited 0 but grew RSS by one baked ground — 2400×1600 RGBA, ~15 MB plus its GPU
copy — per reload, linearly (771 → 1035 MB over 10 reloads). Holding only the
shown texture settled at ~885 MB. Both variants grew ~70 MB on the first reload,
so total growth could not tell a leak from an allocator settling; the slope over
the second half of the reloads can, and the soak now reports and gates it
(< 10 MB/reload). Two Windows runs of that gate then failed without showing a
leak, and without ruling one out: the working set (trimmed and regrown by the
OS) cannot judge a leak at all, and five points of private bytes cannot resolve
10 MB/reload against WARP's ±30–60 MB swings. Re-fitting the gate after each
failure was its own smell (senior review), so the final gate was fixed before
the next run: 20 reloads, private bytes, a Theil–Sen slope, and a positive
control on the same runner that must fire on 25 MB per reload. Windows runs
v9–v19 passed it (1.5–9.0 MB/reload; identical code read 9.0 and 1.8), yet every
one of them, after an early dip, rose 5–10 MB per reload. In longer soaks,
identical code rose +196 and +62 MB by reload 50, and over reloads 51–100 the
five 100-reload runs (the same soak path, not the same code) had slopes of 0.21,
2.03, 3.05, 0.08 and 3.50 MB/reload, the 0.08 an interval that includes zero.
Over reloads 11–20 the same gate read 0.00–0.46 MB/reload on Linux (llvmpipe
RSS); no Linux soak runs past reload 20. The cause is not identified, so the
leak half stays open on D3D11. Three readings of these
curves overreached in turn (a ceiling, a slowdown, a "threefold" pinned on the
wrong pair of runs), so the record now gives numbers, not shapes. The gate
answers "is there a trend over the last ten reloads", not "did memory grow",
so the record carries the whole curve
(ADR-048 entry 10). *Hold the one object in use, not every object
that ever was; judge a leak by its slope, and trust a gate only after you have
seen it fire on the machine it judges.*

**9. An `x or default` threshold turns a perfect zero into a failure.** The
evidence driver judged the projection check as
`(pick.get("max_projection_err_px") or 99) < 1.0`, so a measured 0.0 px read as
99 and failed the run. Thresholds now go through explicit number checks that
fail on a missing or null metric instead of substituting a default, and a probe
that was requested but wrote nothing fails the verdict.

**10. A shader that does not compile is a warning, not an error.** Renaming one
call in the pond's `water.frag` printed `QSpirvCompiler: Failed to parse shader`
as a `QtWarningMsg` to stderr; the run exited 0 with `status: ok` while 449 pond
pixels changed colour (senior review, measured). The frozen exe has no stderr,
so on Windows nothing would have shown at all. The spike now records every Qt
message through `qInstallMessageHandler` into its log and `metrics.json`, and a
shader or QML error ends the run with exit 4 (not 3, which the MSVC CRT's
`abort()` also returns on Windows); a render test breaks the shader on
purpose as the positive control. *Any headless render path must read Qt's
messages, not only its exit code.*

**11. Importing a tool script can take over the suite's settings key.**
`scripts/make_bench_plans.py` pointed the settings names at its own throwaway
key at module scope. `tests/integration/test_bench_plans.py` imports the script
to regenerate the fixtures, so every later test in that pytest process ran on
the script's fixed key instead of conftest's per-process one, the guard against
the "black hole" of two runs sharing a key (ADR-041). The rebinding moved into
`main()`, and an autouse check now fails any test that leaves the names changed
(it caught the old script at once). *A rebinding of process-wide names belongs
in an entry point, never at import time.*

**12. A procedural sky bound live regenerates on every input.**
`ProceduralSkyTextureData` recomputes the whole sky synchronously on the GUI
thread for each input change (~190 ms at high quality on llvmpipe). The spike
bound its inputs to root properties and built a default sky at load, so one
open regenerated it for each look and sun input and threw the first one away:
~4.7 s of CPU, filed under "QML load" or no bucket at all (senior review).
Built once per sun change, inputs set at low quality and raised last, the
frames are bit-identical and that cost drops to ~0.4 s (QML load 1709 → 70 ms,
`set_look` 791 → 0.1 ms, `set_sun` 2192 → 344 ms; llvmpipe, 640×360, commit
a275da2 — ADR-048 entry 6 and the `ogp-3d-renderer` skill cite the same run).
*An input bound live to an expensive generator is a hidden loop; time every
bucket and require the buckets to add up.*

**13. A texture re-attached after a detach renders white, and a guard on
identity did not see it.** The IoU and orientation probes clear the ground
texture for their measurement; `preserved_state()` set the same
`QQuick3DTextureData` back, and Qt Quick 3D drew the plan ground white until the
next project reload (mean difference 13.1 on the frame, all of it in the ground
half). `update()` alone does nothing; `setTextureData(textureData())` plus
`update()`, or a fresh object, restores it: the texture twin of item 6.
`preserved_state`'s guard checked that the shown texture was the one Python
held, which stayed true throughout. A second-window frame comparison caught it
(9.8 mean luma). The first diagnosis, a stale reference frame "fixed" with a
settle wait, was validated by a run without `--iou`, the trigger, so it proved
nothing (senior review, pass 4). Every restore is now checked in pixels
(`probe_restore_frame_diff`: 9.83 before the fix, 0.0 after). *A validation run
that omits the trigger proves nothing; check a contract in the currency it
promises.*

**14. From a git worktree, a test's subprocess ran the main checkout's code.**
`tests/conftest.py` puts the checkout's `src` on the *test* process's path only.
A child started as `python -m open_garden_planner` or `python -c "import
open_garden_planner"` resolves the package through the venv's editable install,
and that points at the main checkout. So a render-tier or isolation test run in a
worktree (where every review and creator agent works) judged other code, and was
green or red for the wrong commit (found by 3D creator round 4). The spike's
render tier and isolation test now put the checkout's own `src` first on the
child's `PYTHONPATH`; `scripts/bench_view3d.py` inserts it itself. *A subprocess
does not inherit the parent's import path; pin it, or the test measures whatever
the environment happens to point at.*

**15. A rule ported by hand drifts from its source.** Symptom: none on the
bench. The spike shows fruit only in a species' harvest window
(`runner.in_harvest_window`), and that port returned False on every asparagus
harvest date at frost dates from 4 January on, and on rhubarb's from 1 January
until just before the frost's anniversary (291 of 1,096 harvest days in
2026–2028 at a 04-09 frost, 783 at 09-20). Neither has a fruit look in the
spike, so no frame changed. Cause: the port took a fixed ±1-year frost anchor
and was checked against the single-year `generate_calendar_tasks`, while the
generator the agent's task tools use (`get_tasks`, `get_task_calendar`),
`generate_for_date_window`, derives the anchor years from the offsets (a
29 February frost: ADR-048 entry 18). Fix: the port derives the range the same
way, pinned by a test that compares the two every day of three years, asparagus
and a southern plan included (ADR-048 entry 18 cites the review passes; PR #413
holds their history). The check also showed that every GUI task surface anchors
on one year (TD-037). *Pin a port to its source day by day, find the source the
product actually calls before naming a deviation, and sweep what the user sees
before saying a fix changed it.*

- **The GUI anchored task windows on the current year while the agent anchored on every year that could reach the date (TD-037).** Symptom: a southern plan (20 September last frost) put a tomato harvest at 29 Nov 2026 – 7 Feb 2027, and on 1 January 2027 the Tasks tab and the dashboard showed nothing — a tomato-only plan read *"No tasks — you're all caught up."* while the task was open; the agent's `get_tasks` listed it. Wrong theories: (a) that the dashboard and the Tasks tab filtered differently — they did not, both called `generate_all(build_plan_state(...))`, and the agent called `generate_for_date_window`; (b) that the offset maths was wrong — it was right, and `generate_for_date_window` already derived the anchor-year range correctly from the offsets. The decisive evidence was a sweep applying the GUI's own listing rule (`classify_urgency(...) is not None`) to **both** sides, over the 64 bundled species that carry calendar offsets x 6 frost dates x every 10th day of 2026 (222 cases): **1,836 missed (task, frost date, day) cases on master and 0 after the fix**, with **0** tasks the GUI listed that the agent did not. The absolute count is harness-dependent — the wider sweep of all 118 species on every day of 2026 (2,190 cases) gives 17,884 before / 0 after — so quote the harness with the number (committed as `scripts/measure_task_window_sweep.py`). The invariant, not the count, is what `tests/unit/test_task_windows_multi_anchor.py` pins: `agent <= gui` **and** `gui <= agent`, so neither side may hide a task the other can see. Root cause: three surfaces each built their own list — the Tasks tab and the dashboard passed the snapshot to `generate_all`, and the Gantt went further and re-derived every window from `self._last_frost` plus the raw species offsets, so the chart was a *second* implementation of "offset to date" — the agent's `generate_for_date_window` and the dashboard's `generate_all` both *call* `generate_calendar_tasks` rather than reimplementing it, so the generator itself is the first implementation and the Gantt's re-derivation the second; the old count included the callers. Fix: one shared entry point, `task_generator.generate_actionable_for_surface`, which wraps `generate_for_date_window` (not a reimplementation) and re-applies the GUI's urgency filter; the Gantt now consumes the generated windows instead of recomputing them, and the dashboard and chart read the same `PlanState`. Two traps inside that fix, both of which produced a green-looking but wrong result: `generate_for_date_window` inherits the caller's `actionable_only` **per anchor year**, so passing the GUI's `True` into it silently dropped anchors before the outer filter ever ran (the Gantt lost most of its chart this way); and comparing raw agent output against the filtered GUI list is apples to oranges — a window 43 days out is *supposed* to be hidden. *Two surfaces that call the same generator can still disagree about which inputs they pass it; find the divergence by comparing the two lists under one rule, not by reading the call sites.*

- **A widget that rewrites a displayed date for "readability" corrupted persisted data.** Symptom: the planting calendar's propagation editor moved each step's displayed date into the current year, start and end independently; a step crossing New Year was saved into the `.ogp` as `start 2026-12-24 / end 2026-01-22` — an inverted step that `compute_propagation_plan` then applied verbatim, so the corruption was permanent for any plan already saved. Wrong theories: (a) that the defect was in the override *writer* alone, so fixing the editor would repair existing files — it would not, because the *reader* applies stored overrides without validation; (b) that swapping the pair on load would be the helpful repair — it would silently rewrite what the user typed. Fix: the editor now shows each step's real dates, and an override whose end precedes its start is **ignored on read and refused on write**, leaving the stored value in the file untouched (no data destroyed, no impossible step displayed). Two further defects surfaced in the same 40-line function and are now covered by the same tests: the editor wrote an override on every `dateChanged` and ran the calendar's full `refresh()` each time — one user gesture produced one *write and one refresh* per keystroke, and the refresh re-fetches the weather. It now commits **once per gesture**, on a 600 ms debounce plus focus-out, mirroring `properties_panel._TEXT_COMMIT_DEBOUNCE_MS`, and a gesture touching several steps emits one batch so the refresh happens once (not once per step). Note what this is and is not: it is *not* an undo step. A propagation override is written straight into `ProjectManager._propagation_overrides` and no `Command` reaches the `CommandManager`, so an override is not undoable at all — a pre-existing gap this change does not close. Invariant 4's one-gesture-one-step rule is what the batching works towards, not what it delivers. The species detail line was five hardcoded English f-strings that the i18n gate is structurally blind to. *A date field that reformats what it holds for display is a data-corruption site; check who reads the persisted value back before deciding the repair, and prefer ignoring an impossible stored value over rewriting it.*

- **The "weeks after planting" comment in the bundled plant data was wrong — and the first measurement of how wrong was itself wrong.** Symptom: `models/plant_data.py` documented `harvest_start` as *weeks after planting* while all five readers counted it from the plan's last spring frost, and a garlic plan with a 9 April frost showed a harvest landing in the same April as the frost — roughly 52 weeks after its own October sowing. Wrong theory: that correcting the data rows is a mechanical conversion. Measured over all 118 bundled species (64 with both harvest offsets and a maturity range): "offset × 7 inside `days_to_maturity`" fits **37 of 64**; "(offset − planting_offset) × 7 inside maturity ±15 %" fits **46 of 64**; on the harvest *start*, the planting-relative span lands in 1.0–1.5× the stated maturity for **29 of 64** species against the maturity midpoint (45 %), 33 of 64 against `days_to_maturity_min` (52 %) and 15 of 64 against the maximum (23 %) — so "most species" holds under no denominator except a bare 50/50 split on the minimum. Measured by `scripts/measure_harvest_offsets.py`, which prints all three counts, and garlic's 182-day reading does fit while its *window* still lands in October - about three months after a real garlic harvest. Both readings fit a majority (37/64 frost-relative, 46/64 planting-relative), so the data is **not** irreconcilable and "convert the rows that follow the other reading" has no well-defined target set. What does follow from the measurement is the opposite conclusion to the one this entry originally drew: the rows were probably **authored** as planting-relative, which is the finding #418 has to resolve. Fix: the shipped half makes the documentation true and pins the divergence (`KNOWN_DIVERGENT_SPECIES`); the row conversion is deferred to #418 because it needs a cited horticultural source per row and licence clearance under the #311 provenance rules. The measurement that made the split defensible: `days_to_maturity` is **reference data that no computation reads** (asserted by a test), so correcting rows cannot move a computed date. *When data contradicts its own documentation, establish which reading the code implements before editing the data; and when two fields in the same record cannot be reconciled, say so and name the exceptions instead of picking a winner and moving 60 rows' worth of dates in one release.*

- **A shared generator's flags are inherited per iteration, so a wrapper can filter before the wrapper's own filter runs.** Symptom: routing the Tasks tab through the shared multi-anchor path produced an **empty** task list and the Gantt produced **no bars at all**, while the unit tests of the same helper passed. Root cause: `generate_for_date_window` builds each anchor year with `replace(state, ...)`, so `actionable_only=True` (the GUI default) is re-applied inside every anchor — dropping anchors whose windows are not currently urgent *before* the outer `classify_urgency` filter saw them. Fix: both call sites pass `actionable_only=False` into the inner pass and keep exactly one urgency filter, which is the one they document. This is the same shape as the #326 "`Callable` injection with N call sites" lesson: a flag that is silently defaulted somewhere in the middle of a chain is not a flag, it is an accident waiting for a caller. *A default inside a loop over derived inputs is a filter nobody wrote; when a wrapper delegates, pass the permissive value inward and filter once at the edge.*

- **A product surface can be "protected" by a library default nobody pinned.** Symptom: the Agent API's only barrier against a web page reaching it through DNS rebinding was the mcp SDK's Host/Origin validation, and the declared floor (`mcp>=1.12`) admitted SDKs that leave it **off** — measured: on 1.22.0 a crafted `Host: evil.example` initialize returned HTTP 200 with a full MCP result, where the 1.30.0 wheel answers 421. No shipped exe was known to be exposed, because every release happened to bundle a 1.30-era wheel. Root cause: the property belonged to *whichever wheel resolved at build time*, not to the product. Fix: `build_server` now takes the host/port it binds and passes explicit `TransportSecuritySettings`, and the floor rises to `mcp>=1.23`. The instructive part is the test design: with mcp 1.30.0 installed, the black-box 421/403 tests **pass even with our settings deleted** (measured). So does a naive object-level assertion that the settings are not None and the flag is True — the SDK auto-enable returns exactly such an object. What actually detects the removal is asserting something the default cannot satisfy: that `allowed_hosts` names the **bound port** and that no entry is a wildcard. Measured: deleting the `transport_security=` argument fails 3 of the 4 object-level tests. *A test that passes because of a library default is not testing your code; assert the configuration object as well as the behaviour it produces.*
### 11.4.7 A day derived from a UTC instant is not the user's day (Phase 17 L1.0, #385)

- **Store the user's calendar day; never derive it from the UTC instant** (ADR-053). Symptom: none was reported. The defect was found by reading the code while one clock was being designed, and a comment in `sun_heatmap.py` already admitted it ("near midnight the two can name different days"). The shadow overlay grew plants for `self._sim_dt_utc.date()`, and the 3D snapshot did the same. The heatmap grew them for the toolbar's local day. At 01:00 local on 22 June at UTC+9, the overlay grew the garden for 21 June and the heatmap for 22 June. Root cause: four owners of "the simulated moment" (toolbar widgets, a controller instant seeded with its own `datetime.now(UTC)`, the heatmap's argument, the 3D view reading the controller), and a date taken from whichever one was nearest. Fix: `core/sim_clock.SimClock` stores the local `plan_date` and a wall-clock time and derives `utc`. "A time change never fires `date_changed`" then holds by construction, not through zone data. Pinned by `tests/unit/test_sim_clock.py::TestTimeChangeNeverFiresDateChanged` (`set_time_of_day` sweeps over an ordinary day in the machine's zone and two fixed offsets, the 2026 DST days in Berlin and New York, and the EU DST dates in the machine's zone; they document the API but cannot fail by construction) and `tests/integration/test_sim_clock_wiring.py::TestOnePlanDateEastOfUtc`. *A date and an instant are different facts; when a feature needs both, store the one the user chose and derive the other.*
  - **The first fix repeated the bug one layer up, and its gate test could not see it** (senior review round 1, P1). The clock stored the date on `set_time_of_day`, which the sweep tested, but the app never called it. The toolbar still emitted `naive.astimezone()`, an instant, and the clock read the date back out of it. In a zone whose spring-forward gap starts before midnight (America/Nuuk: Saturday 23:00 jumps to Sunday 00:00), an Animate tick from 22:50 moved the plan date to Sunday, cleared the heatmap and regrew 3D. Fix: the toolbar emits its naive wall reading, which the clock stores unchanged. Pinned by `test_sim_clock_wiring.py::TestToolbarPathPreMidnightGap` (every slider value and 20 Animate ticks through the real toolbar; fails on the old emission). *A gate test that drives an API the product never calls proves the API, not the gate: test on the path the user's gesture takes.*
  - **Two more defects behind the same seam.** (1) The heatmap's stale rule looked only at a *visible* map, so a date change while the worker computed let the old day's map paint under the new date — although `SunHeatmapController.clear()` had been written for exactly that case. Its only caller never reached it. The first fix keyed on `is_running`, which is `QThread.isRunning()`. That is False as soon as `run()` returns, while `success` and `finished` still wait in the GUI queue, so a date change in that window still let the map paint (senior review P1). The rule now keys on `result_pending`, which is cleared only when the GUI thread has handled the worker's `finished`. Pinned by `test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`: the running case, plus `worker.wait()` followed by a date change, driven through the button. (2) The toolbar's `QDateEdit` allowed its defaults, 1752–9999, while `naive.astimezone()` on Windows raises `OSError` near the 1970 epoch and after 3000. Measured on Windows 11 with CPython 3.12 in Europe/Berlin: 1960, 1970-01-01 12:00 and 1970-01-02 00:00 fail, 1970-01-02 01:00 works; 2999-12-31 and 3001-01-02 work, 3001-06-01 fails (CPython probes about a day either side). Picking such a date raised inside a Qt slot. The clock now refuses dates outside 1971–2999, and the picker uses the same range. *A cleanup method that no caller reaches in the case it documents is a gap, not a guard; and a widget's default range is an input range, so check it against what the code below it can convert.*
  - **A two-way view must write back only what changed** (senior review round 2, P1). Round 1 made the toolbar a view of the clock: the app mirrors every clock change into it with `set_datetime_local`. That called `QDateEdit.setDate()` with the *unchanged* date on every Animate tick (every 200 ms). `setDate` makes the widget redraw its text whenever the text differs from the stored value, and a half-typed date always differs, so typing a date while animating was impossible. Measured with QTest keystrokes: the field read `'2026-06-'`, one tick turned it back into `'2026-06-21'`, and the typed `28` was lost. On master the tick only moved the slider. Fix: the setter writes a field only when it differs. Pinned by `test_sim_clock_wiring.py::TestTypingUnderAnimate`, which fails with the unconditional `setDate`. The same round found `run_for_day` still guarded on `is_running`: a second launch in the queued window let the first worker's `finished` `deleteLater` the running second one, a Qt fatal abort that the busy button keeps unreachable today. It now refuses while `result_pending` (`TestHeatmapLaunchGuard`). *Mirroring a model into an editable widget is a write into the user's hands: compare before you set.*
  - **Two traps in writing the clock itself.** `datetime.time` equality ignores `fold`, so the two occurrences of 02:30 on a fall-back night compare equal. A change-detecting setter would swallow the switch between them, so `SimInstant` equality includes `fold`. And the first range check ran on the instant's UTC date, which refused a valid local 1971-01-01 00:00 at +09:00 (UTC 1970-12-31). The edge test found it before any caller did: the platform guard now allows a day of margin, and the range itself is enforced on the local date.

### 11.4.8 Guild boundaries found by independent review (F1/F2)

Guild happy-path insertion tests did not establish document lifetime, copy isolation or translated refusal behavior. Review reproduced a mirror copy whose species dictionary still aliased the source, a grouped existing centre whose ancestor layer was locked, a stale search-detail response accepted after another selection, and malformed imported trait shapes that could invent functions through substring matching. The fixes deep-copy the complete copied metadata, check every ancestor layer, invalidate enrichment on selection changes, and normalize imported trait containers without inferring values. Unknown data remains preserved.

A second review exercised plan replacement while a placement preview or sidebar click was pending. Four preview wrappers survived scene clearing and `clear_preview()` raised a deleted-C++-object exception; loading a plan with the same UUIDs caused the queued click to select an object in the replacement document. Document replacement now closes the picker before teardown, clears coordinator status synchronously, and cancels pending navigation. UUID resolution must be coupled to document lifetime. Regression tests cover same-ID replacement as well as empty scenes.

Validation errors now have Qt-free codes and structured parameters. API text stays English; UI adapters translate the known code and field labels. Translating only an outer error sentence left its generated reason in English. Actual German editor and deleted-centre refusal tests pin the complete user-visible message, beyond the unfinished-translation gate. No undocumented Qt timer-reentrancy claim is made: the separate timer experiment did not reproduce it.

The full battery found one further representation boundary: existing task/soil tests construct `RectangleItem` plants, so semantic `is_plant_type` does not guarantee `CircleItem.radius`. The badge coordinator now skips geometry for plants with no badge/status and uses the actual rectangle or bounding rectangle when an update is needed. A regression covers an ordinary rectangular plant and an imported rectangular guild centre, retaining serialized geometry. Subsystem-only green tests had omitted this representation. Review also loaded a polygon plant and selected it through the real picker: it was eligible but insertion assumed `rect()`. One `guild_plant_bounds()` helper now uses the base rectangle/polygon/path geometry for centre positioning, boundary preflight, previews and badges. Rotation-parametrized round-trip picker tests cover this path and exact undo restoration.

**F1/F2 owner manual-pass follow-up (PR #433).** The German guild picker displayed English catalog names, and selecting a gallery plant then drawing it ignored food-forest auto-assignment. Instrumentation showed `[F1] auto=True species=shrub chosen=<active-id> active=<active-id>` from `CircleTool._finalize_circle`; the previous integration test exercised only the drag/drop constructor. Circle placement now uses the same `build_plant` constructor as drops, preserving plant metadata, planting-date stamping, parentage and one-step undo. Names in the guild picker, editor and member list use display-time translations, including the previously unregistered bundled catalog names. The saved English names and canonical keys are unchanged, and explicit object names are preserved. Regression tests assert German widget contents and both eligible-layer assignment and fallback behavior; table completeness alone cannot establish either contract.

**Final PR #433 review: deferred P2 maintenance finding.** The synchronous `PlantSearchDialog._enrich_selected_plant()` helper has no callers; selection acceptance uses the asynchronous `_on_accept()` / `_poll_results()` path. Stale comments in the dialog and provider base still reference the synchronous helper. This creates a future validation/fallback maintenance risk, with no observed runtime defect or outstanding P0/P1. A separate cleanup should remove the unused helper and update those references while retaining the asynchronous enrichment integration tests.

## 11.4.6 Sun self-shadow and late document results (#314, #428)

The #314 centre-lookup example assumed the receiving plant was absent from its own ground heatmap. The planning probe measured zero hours for both tomatoes with all solid casters, versus 0 h north and 16.5 h south when only each receiver's own caster was excluded. Zero is a valid measurement only after completed, valid evaluation. The fix preserves the ordinary displayed grid and adds sparse identified receivers in the same explicit run; it does not claim exposure at leaves or model canopy transparency. Whole-day reruns per plant took 17.6 seconds for 20 receivers among 100 casters; batched integer sweeps and vectorized point sampling measured 3.226 seconds for 200 casters/receivers locally.

The document-lifecycle regression was observed failing in all six GUI New/Open/recovery timing cases: a cancelled worker deliberately emitted success and `heatmap_visible()` remained True after replacement. A date-only clear cannot protect document ownership, and `is_running` becomes False before queued success/finished cleanup. The canonical `document_replaced` reset cancels, clears and unchecks before C++ teardown; generation/signature guards reject late results. Ownership stays until finished and the next run is refused while signals remain pending. A malformed prevalidation load deliberately emits no reset and retains the valid current map. Real MCP New/Open and cached diagnostic reads pin the transport seam.

Snapshot comparison must use physical base-shape centres transformed into scene coordinates, not decorated bounding boxes or the assumption that every plant is a circle. Semantic plant types can be imported as rectangles/polygons or grouped. Commands require their own subscription because metadata-only edits may not produce a scene repaint. Cosmetics must be idempotent to avoid an infinite scene-change loop. General diagnostics have one publisher so guild/sun producers cannot erase each other's records.

Review pinned two representation gaps: a badge placed at a concave polygon's bounding-box centre was outside the footprint, and accepted non-dict species metadata raised in the selected-tree timer. Badge rectangles now pass whole-path containment against undecorated base geometry; species snapshots are normalized once. Grouped/imported save-load regressions cover both. The complete suite also caught a delayed destruction callback after a weak clock subscription had been pruned; cleanup now tolerates that already-disconnected state, with a cyclic-collection regression.

### 11.4.9 A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473)

**An unbounded fill is a denial of service a plan file can carry — and the obvious bound does not bound it.** `PolygonItem` painted whatever vertex count a `.ogp` held. A reflex-heavy outline makes one antialiased fill quadratic: measured with the item's own 2.0 pen, ~38 ms at 256 vertices, ~322 ms at 1,024, ~1.4 s at 4,096, ~5.6 s at 16,384 (the bug report measured 10.5 s at 1,024 on its box). The first fix bounded full detail at 1,024 vertices and degraded an over-budget frame to "the outline" — and the independent review, plus a second measurement, showed it bounded nothing: 1,024 was the very count the report called pathological, and Qt strokes a **wide solid pen by building a fill**, so the same 1,024-vertex comb took 319 ms stroked with the item's pen against 4 ms with a cosmetic 1-px pen. The shipped bound is 256 vertices and the degrade uses a **cosmetic** pen and no fill (~4 ms at 1,024, ~69 ms at 16,384); `MAX_POLYGON_VERTICES = 16_384` (a ceiling far above any legible garden outline, at which the degraded 2D outline is ~69 ms) refuses a hostile polygon at the load seam non-fatally. **The degrade also had to be *reachable*.** Qt passes `widget = 0` for every **cached** paint, and every unselected canvas item is `DeviceCoordinateCache`, so the first shipped guard (`widget is not None`, the LOD flat fill's own idiom) selected the empty set: measured through a real view, an over-budget polygon still painted at full detail — 44.7 ms at 1,024 vertices, 589 ms at 16,384 — recurring on every cache regeneration, so the freeze was bounded only by the load ceiling. The discriminator is now the **cache mode**: every export, report, print and agent render path disables caches first (`ExportService._disable_item_caches`), so those stay exact while the cached interactive view degrades, and the regression drives a real `CanvasView` instead of calling `paint()` directly. *An idiom copied from a sibling is not evidence: check that the condition it tests is ever true on the path you are protecting — a cache can make it false, and a test that calls `paint()` itself cannot tell you.* *A cost you can bound is a design choice; a cost you cannot is a bug report waiting for a crafted file — and "draw the outline instead of the fill" is only a bound if the outline is cheap, which for Qt it is not with a wide pen. Measure the degraded path with the pen the item actually uses, or you have bounded the shape, not the paint.*

**A copy must carry both representations of a shape's look, or one of them lies.** The offset tool made a rectangle, circle or ellipse copy in its *type's* default fill, pattern and stroke, while a polygon or line copy "kept all of it" (#470). The asymmetry hid the second defect: the polygon path copied only the live `QPen`/`QBrush`, so the copy looked right until the next save, when `fill_pattern`/`stroke_style` were absent and the loader restored the type defaults. One seam, `core/item_look.py::copy_visual_style`, now copies the serialized attributes (`fill_pattern`, `fill_color`, `stroke_color`, `stroke_width`, `stroke_style`) and the pen/brush together, and both the offset tool and `mirror_geometry` use it. *When an item has a live appearance and a serialized appearance, a copy that writes one and not the other is a round-trip bug wearing a rendering bug's clothes.* Chamfer/fillet/trim have the same shape and are deliberately left to #441 (then on the L1 branch; fixed in v1.30.14) rather than routed here. The loader's own half of the same defect — it rebuilt the brush and pen but never wrote the stored attributes back, so the Properties panel disagreed with the canvas after a reload and the next save overwrote the user's colours (#438/#469) — is fixed in the same branch; see §11.4.10 and the ADR-042 addendum.

**A performance budget cannot see a cost its scenario does not contain — or that its cache hides.** The NFR-PERF-01 reference plan holds no polyline (0 of 990 scene items), so a change making every line's `paint()` 25% slower left all three budget scenarios where they were (#473). The first fix added plain and styled lines to the scenario — but every canvas item enables `DeviceCoordinateCache` and the harness warms the cache before timing, so a cached line is never repainted and a slower `paint()` is still invisible; injecting a 5 ms slowdown into `PolylineItem.paint` moved the measured frame by ~0.3 ms. The shipped scenario disables the cache on its lines and pins that deterministically (a `cacheMode() == NoCache` guard), with 10 short plain fences and 1 short styled gravel path adding a stable ~5 ms. The wall-clock comparison survives only as an *upper* bound: a lower bound made the test a coin flip, because viewport timing on a loaded machine swings by tens of milliseconds in both directions (measured −10 ms to +21 ms on the same view). An absolute per-frame budget for the styled lines is left to #450, which owns the whole-line style walk. *A budget guards what its inputs exercise, on the path they exercise it: "we have a perf test" and "the perf test paints this item every frame" are different claims, and a cache is the quietest way to break the second while keeping the first.*

### 11.4.10 A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass)

**A constant wash cannot recolour a saturated texture.** `_tint_texture` drew a texture and laid the user's colour over it at **alpha 80/255**. Over the brown roof-tile texture (`#ca6846` at the sampled pixel) a light-green fill (`#90ee90`) measured **`#b8925d`** — still brown. The owner set a green fill and the canvas showed "the standard roof tile colour", so the fill colour looked *lost*; a from-scratch control rectangle, styled exactly as they described, rendered the same brown as a file-loaded one, which is what proved nothing was lost on load and the colour was never applied. Raising the wash enough to read (160/255) flattened the low-contrast materials (SAND luminance std 1.62 against the 2.0 floor of `test_texture_paints_with_visible_detail`), so the overlay strength was the wrong knob. The fix is a **luminance map** — every pixel becomes the chosen colour scaled by the texture's relative luminance — which makes the *relative* contrast of the result equal the texture's by construction, i.e. non-flattening is a property, not a tuning. *If a transform must both recolour and preserve detail, preserve it as a ratio the transform cannot change, rather than picking a strength that happens to survive the current assets.*

**The gate proved the wrong claim.** `test_user_colour_recolours_without_flattening` compared **red and blue** — two saturated, far-apart colours. Both passed while the owner's *pale* green rendered brown, and `test_texture_paints_with_visible_detail` measured **absolute** luminance std, which a legitimately dark fill colour lowers for no defect. The gate now also asserts a **pale** colour reads (`g - r > 40`; untinted textures measure about −49) and compares **relative** contrast against the same item's untinted render. Reverting the tint makes 19 of the 48 cases fail. *Coverage by colour extremes is not coverage of the colour space; and a texture-preservation gate must be scale-invariant or it punishes dark colours.*

**A loader that rebuilds the brush but not the attributes rebuilds the wrong truth.** `ProjectManager._deserialize_item_core` restored each item's `QPen`/`QBrush` from the file but never wrote back `fill_color`, `stroke_color`, `stroke_width` or `stroke_style` — and the item constructors pre-seed those attributes with the object type's style (`rectangle_item.py` passes `fill_color=style.fill_color, stroke_color=style.stroke_color, …`). After a reload, the Properties panel read the *type* defaults while the canvas painted the file's colours: on the owner's file `item.stroke_color` was `#228b22` (GENERIC_RECTANGLE's style stroke) while `item.pen()` was `#ff0000`. The next save then wrote those defaults over the user's colours (#438/#469). The loader now restores the stored attributes through `core/item_look.restore_stored_look`, and the serializer no longer falls back to a texture brush's black `color()` for `fill_color`. *Two representations of one fact must be written together; a "restore the brush" path that leaves the attribute behind is how a document quietly rewrites itself.*

**And the test that claimed the look survived a save asserted a value that could not fail.** #470's round-trip check compared the reloaded **pen/brush** while its docstring promised "the look survives" — and its earlier brush-colour assertion (`brush().color()`) was vacuous for a texture brush, which is black on both sides. Round-2 review flagged that assertion; round 3 dropped it instead of replacing it with a real tint check, and the owner's manual pass found the gap the next day. `tests/integration/test_item_appearance_roundtrip.py` now compares **rendered pixels** (and asserts a light-green fill reads `g - r > 40`) across all five shapes plus the Ctrl+D duplicate path. *Deleting a weak assertion is not replacing it; if a test is the only evidence for a claim, the claim loses its evidence the moment the assertion goes.*

**And a test value that equals the default it is meant to prove is restored also cannot fail.** The replacement used the owner's light green `#ff90ee90` — which **is** `GENERIC_RECTANGLE`'s default `fill_color`, so `after.fill_color == item.fill_color` held whether or not the loader wrote anything back. Measured by mutation: deleting only the `fill_color` restore from `restore_stored_look` left that test **passing**; re-pointing it at a non-default colour made it **fail**. The round-trip tests now style items with `USER_FILL` (`#ff1f4fd8`), chosen because it collides with no entry in `OBJECT_STYLES` (asserted by `test_the_test_colours_are_not_type_defaults`, which walks all 52 object types), and the owner's literal green is kept as its own test where it is the subject rather than the evidence. *A regression test proves the defect only when its chosen value is distinguishable from the value the defect leaves behind — otherwise it passes on the broken code, which is the one thing it exists to prevent. When the value must be a realistic one, assert the non-default separately.*

### 11.4.11 A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503)

**A sibling idiom copied twice fails twice, and a test that calls the helper directly cannot see either failure.** #472 shipped its over-budget polygon degrade only after an independent review found the first guard unreachable: `widget is not None` was the LOD flat fill's own idiom (#409), and Qt passes `widget = 0` for every **cached** paint while every unselected canvas item is `DeviceCoordinateCache`. #501's review then reported the identical defect in the LOD guard itself (#503) and left it out of scope. Measured through a real `CanvasScene` + `CanvasView`: `should_use_lod_flat_fill` was invoked once per paint with **no** widget at `fit_in_view` and after four `zoom_out()`s and returned `False` every time, while a `NoCache` control item did see a widget - the one configuration no unselected canvas item is ever in. The tests passed because they called the helper directly with a fabricated widget, structurally unable to notice a condition Qt never supplies.

**Making the guard work would have been the wrong fix, and only a measurement could say so.** The obvious repair - key "interactive" on the item's **cache mode**, exactly as the #472 paint bound already did - was implemented first, and the branch became live for the first time. Measured on the reference plan it was written for (990 scene items, 1600x1000 view, seven rounds of fifteen repaints, both scenarios below the 0.4 threshold): `fit_in_view` at zoom 0.316 read **10.61 and 11.50 ms median with the flat fill disabled, 10.87 ms with it live**, the arms' ranges overlapping entirely; `zoom_step` at zoom 0.348 read **7.97 / 7.98 ms disabled, 8.20 ms live**. All six `tests/perf/test_nfr_budgets.py` cases pass either way, worst reading 12.21 ms against the 16.70 ms budget. The cause is structural and was visible in the code all along: `DeviceCoordinateCache` rasterises a textured item **once** and every later frame is a cheap blit, so the expensive textured `paint()` the LOD existed to avoid was already amortised by the sibling fix shipped in the same PR. The branch could only pay per *cache regeneration**, and the acceptance metric is steady-state repaint. What this establishes is that the effect sits **below this harness's noise** - within-arm variation 8 % against a 0.26 ms between-arm difference, and no reversed-order run was taken, so no claim about which arm is faster survives. (An earlier single-pair reading, 10.58/10.64 and 8.21/7.40, is superseded: it put the `zoom_step` sign the other way. A draft of this very paragraph asserted the ordering it implied and was wrong on its own numbers.)

**The owner's manual pass rejected it, which is why this reads as a deletion rather than a repair.** Making the guard work would have put a design decision on screen that had never been reviewed in the product: below 0.4 an unselected bed, furniture item or plant shows only its flat fill (plant and furniture sprites flat-fill too - they are not pattern-gated), and the early return skips the paint-level diagnostics drawn after it (a bed's grid, crop-rotation indicator, soil-mismatch border and capacity badge; a plant's spacing ring, companion highlight and antagonist badge). The owner works at 20-25 % zoom, well under the threshold, so every texture they work with would have been replaced by a solid colour in exchange for nothing. Issue #503 had offered both repairs - "either the LOD flat fill fires for cached interactive paints ... or it is removed with its rationale recorded" - and the measurement plus the manual pass chose the second. `should_use_lod_flat_fill`, `get_lod_fill_color` and `LOD_FLAT_FILL_THRESHOLD` were deleted. `is_interactive_paint` **was kept**: it is the one definition of "which paint is this", and the #472 paint bound needs it for real (a cached 1,024-vertex comb costs 44.7 ms at full detail and 589 ms at 16,384). Its docstring now says that it classifies paints and does not decide how much detail to draw.

**A negative pin can stop noticing, and a mask in the wrong coordinate frame does not fail - it lies.** Deleting a feature leaves nothing that fails when it returns, so the replacement asserts the *absence* of the regression, and that kind of test has a failure mode a normal suite cannot have: it keeps passing while stopping to look. Three review rounds found it three ways, and none of them was visible from a green run. The sampler took the item's **bounding box**, whose corners are page background for a circle, an ellipse or a polygon, so a *solid* circle measured as high-contrast. The table covered four **classes** while three of the seven deleted call sites sat behind `is_plant` / `is_furniture_type`, which a `GENERIC_*` fixture never enters. And the export mask sat in the wrong frame - `QGraphicsScene.render` composes the painter's scale with a translate by `-source.topLeft()`, and only the scale was applied - which made one case pass at spread 45.97 with a flat fill live. The shared root is one unasserted invariant: **the mask must be the item's interior**, and a mask that is not reads background, which a luminance statistic scores as texture. It is asserted now, as a test rather than a comment.

**The instrument, and how to check it.** `tests/integration/test_canvas_item_cache.py` is the pin: seven entries (the four generic shapes plus a plant circle and furniture rectangle/circle), five zoom levels each plus the export path, the interior taken from `QGraphicsItem.shape()`, a lower-bound-only spread assertion so a future change may soften a texture but not delete it, and `TestTheMaskIsTheItem` for the invariant above. Its calibration table, the seven-entry shape list and the sampler mechanics live **in that file** - not here, because a description restated in nine passages is how this section's own history drifted three times. Run `venv/Scripts/python.exe scripts/verify_lod_removal_mutations.py` to re-apply each of the seven deleted call sites and assert the pin still fails on each; it is a script rather than a test because it rewrites live source files, so it takes a lock, runs alone, and belongs to a review or a pre-merge sweep.

*An idiom is a hypothesis about the framework; a guard needs evidence that its condition is reachable on the path it guards, and a direct-call test is not that evidence. Reachability is necessary, not sufficient - the next question is whether the branch earns the degradation it costs, on the workload it was written for. And a conclusion drawn from one ordering of a noisy measurement is the same class of mistake: both are confident and both are unfounded.*

### 11.4.12 What the plant builders taught (Phase 17 L1.7, #385)

Most gates of the plant story passed the first time they ran. The entries below are about what
that did and did not prove (ADR-059 addendum "plant art v0", §8.29.7). Three of them were found by
looking at a render, not by a number.

- **A gate satisfied by the repair that broke the thing: a cushion floated 9 cm above the
  ground with `min z == 0`.** The base gate says the lowest vertex is at 0, and the first `_fit`
  guaranteed it by subtracting the minimum. Then shell leaves were allowed down to the ground:
  one leaf of a lavender dipped 9 cm below the cushion's base, the fit lifted the whole plant by
  those 9 cm — 13 % of its height — and the gate held: one vertex touched the ground and the
  plant hung in the air (a hydrangea 11 cm, a petunia 15 % of its height). Found on a sanity
  render (the side view); 59 of 123 recipes once counted. Fix: what dips
  below the ground is pressed onto it (as the lobes always were); a plant is only ever set
  *down*, never lifted. Pinned by counting, in
  `tests/unit/test_scene3d_plants.py::test_every_recipe_fits_the_plan_s_numbers`: at least six
  vertices within 0.5 % of the height above the ground (a trunk's foot ring has eight; the
  floating plants had one to three). *"The minimum is zero" is true of a floating object with one
  hanging thread. Ask how much of the thing meets the constraint, not whether its extreme does —
  and never make a constraint hold by translating the result.*
- **What a number cannot say: the crowns were bald on top.** Every gate was green — height,
  spread, triangles, hue, clones — and the first look through an engine (the dormant spike's
  renderer, a scratch script) showed mounds and crowns with a smooth bare top and a skirt of
  leaves. The shell leaves had been placed on an ellipsoid *envelope*; where a lobe reached the
  envelope they were inside it, and between lobes they hovered. Fix: `_on_lobes` casts each leaf
  from the crown's heart onto the outer surface of the lobes
  (`test_shell_leaves_are_set_on_the_lobes`). Moving the leaves onto the lobes then made the
  lobes the plant's outline, and the canopy-circle measure of the next entry went from 1.07 to
  1.20 for a climber and from 1.05 to 1.14 for a mound until their lobes were made regular too —
  the stress test caught that one. *Look-dev is a gate. A story that may not approve its own look
  still has to look.*
- **A fix made by eye stays unpinned until a number can see it: the placeholder's rim.** Through
  the same renderer the placeholder's rim read as a polygon at close range; 24 sides became 48,
  and nothing asserted it. A mutation check — one rule broken at a time on a copy of the tree, 45
  breaks, each run against the story's tests — killed 44. The survivor was a placeholder with
  *eight* sides: the bounding box, the farthest vertex and the smooth normals of an octagon are
  those of a circle. Pinned now by the area of the rim polygon, at least 99.5 % of the canopy
  circle (48 sides cover 99.7 %, 24 cover 98.9 %, 8 cover 90.0 %):
  `tests/unit/test_scene3d_plants.py::TestPlaceholder::test_its_rim_is_the_canopy_circle`. *After
  a fix made by looking, name the number that would have seen the defect. If there is none, the
  fix is a habit, not a gate.*
- **A bounding box that fits is not a footprint that fits: a "fitted" plant stood 39 % outside
  its canopy circle.** The spread gate is the bounding box (widest span = canopy diameter ± 10 %),
  and the first `_fit` made it exact for every archetype. An assertion the gate does not ask for —
  no vertex further than 1.10 canopy radii from the plant's axis — failed on the sixth recipe (a
  fig tree, 1.18). Measured for every archetype it read 1.39 for `feathery`, 1.37 for `allium`,
  1.23 for `flower`, ~1.2 for every leaf shell: a plant whose few long blades point anywhere fits
  its box and pokes out of its circle at the diagonals. Scaling the farthest vertex onto the circle instead only moves the lie — the box then
  spans 72 % of the diameter. Neither fit can repair an irregular outline. Fix: the elements that
  draw an outline are regular by construction (`_RIM_REACH`, `_RIM_JITTER` in
  `core/scene3d/builders/plants.py`), stray shell leaves are pulled back onto the circle before
  the fit, and the box stays exact. That left the reach a measurement — 1.092 radii at most over
  117,000 builds, because the fit's xy scale carries leaf tips that stood on the circle a little
  past it; what became of that number is under "what the second review found", below. *A truth
  gate measures one projection of the truth; measure the neighbouring one before trusting it.*
- **An instrument that under-samples reports a difference that is not there: two identical hedge
  drums "differed" by 26 %.** The no-clones gate compares side silhouettes of two ids on a
  32 × 32 occupancy grid. The first instrument sampled every triangle at 15 points; a hedge's
  side triangles span 27 rows of cells, so each silhouette was a different random sieve and two
  drums — the same shape, by design — scored an IoU of 0.74. The gate was green *because* the
  instrument was broken. Sampled on a lattice finer than half a cell, the same two drums scored
  0.999: clones. Fix, in this order: the instrument (`side_silhouette`), then the hedge (a batter,
  a bulging side, an uneven top; and after the review a shoulder cut higher or lower and
  squarer or rounder — over 30 ids a recipe two sections are 0.975 alike at most now, 0.981 in
  the second review's sample). *Give every metric a case whose answer you
  know: two builds of one id must score 1.0, and something you believe to be a clone should score
  close to it. A gate that has never failed has not yet been shown to work.*
- **"Byte-identical" needs to say against which bytes: on Windows the working tree is not the
  commit.** Regenerating the 123 sprites from the unchanged generator and diffing them against
  `resources/plants/` reported 123 of 123 files different — 10,650 bytes, one per line. With
  `core.autocrlf=true` the files on disk end in CRLF; the generator writes LF, and the committed
  blobs are LF. The reference for a byte comparison is the blob (`git cat-file blob HEAD:<path>`):
  identical, 123 of 123, 5,833,889 bytes, before and after the tables moved. The conformance gate
  never noticed because it compares text.
- **A script that imports the app imports whichever checkout the environment points at.** The dev
  venv's editable install resolves `open_garden_planner` to the main checkout (measured: without
  `PYTHONPATH`, `open_garden_planner.__file__` is the main checkout's, from any directory). A
  sprite generator that had simply gained `from open_garden_planner.core.plant_art.recipes import
  …` would, run from a worktree, have read the *other* checkout's tables as soon as that checkout
  has the package — and a before/after comparison in the worktree would then compare one
  unchanged table with itself and pass. The generator first put its own checkout's `src` first
  on `sys.path` (as `scripts/make_bench_plans.py` does); it now executes its checkout's
  `recipes.py` by file path, which no install can redirect and which needs no app import at all.
  The scratch dump printed the recipes module's path to prove which file was read.
- **A reference built from your own inputs agrees with you.** The first plan for the foliage-hue
  gate compared the mesh's mean hue with the mean hue of the palette's entries — the very colours
  the builder mixes from, so any mixing would have passed within a degree or two of whatever the
  palette's midpoint is. The palettes span up to 41° of hue between their anchors (`dark`: 105° to
  148°); where a sprite's foliage sits in that span is decided by the sprite's drawing code
  (conifers at the base anchors, alliums at the tips). The reference is therefore the rendered
  sprite: the shipped SVG drawn by QSvgRenderer, minus the same sprite drawn with a black palette,
  is exactly the ink that depends on the palette — no hand-made mask for fruit and flowers. A
  single mean tip weight for all plants would have put an onion 9° off; per-archetype weights
  measured from the sprites give 5.0° at worst (rosemary), 0.8° at the median.

**What the independent review then found behind a green suite** (same story, the same day; ADR-059
addendum "plant art v0", "what the first version got wrong"). All eight gates were green.

- **A gate that the code forces cannot fail: a squash was built 1.6 times too tall, and the
  height gate was exact.** The gate compared the mesh's top with the plan's height — after
  `_fit`, whose last step scales the top onto the height. It held for anything. Measured before
  the fit, a Winter Squash 60 × 360 cm was 1.4–1.6 times too tall, so its whole body ended at
  63–76 % of its height under a few leaf tips; at 15 × 800 cm nine archetypes were 3.5 to 11.6
  times too tall. Three causes, none of them visible at the sizes the tests used: shell leaves
  faced the way the RAY from the plant's heart ran, not the way the lobe's surface faces — on a
  flat cushion leaves stood on edge; a leaf's length grew with the plant's width and nothing held
  it to the height; and the size matrix scaled height and spread together, so each recipe was
  only ever built at the proportion it was tuned at. Fix: the builders build to the data (every
  archetype places its highest point at the height; leaves are set by the surface normal and stay
  inside by turning, never by squashing; bow, ripple and fold of a folded leaf are held to the
  height), `_fit` returns a `FitReport` of what it still repaired, and the tests assert the
  report, the area-weighted height quantiles of the foliage, and two off-proportion sizes per
  recipe (every proportion step since the second review). Measured after: the builder's own top
  is 1.0000 of the height in every one of 63,099 plants. Pinned by
  `tests/unit/test_scene3d_plants.py::test_every_recipe_at_every_proportion_step`,
  `::test_every_recipe_fits_the_plan_s_numbers`, `::test_extreme_sizes_and_proportions` and
  `::TestFitReport`. *If the last line of the code
  under test makes the assertion true, the assertion is about that line. Measure before the
  repair, make the repair report itself, and leave the diagonal of the test matrix.*
- **A sole that nobody sees still fights with the ground.** The same measurement found up to
  6.7 % of a mound's foliage triangles (12 % of its area) lying flat at z = 0: lobes that reach
  below the ground were pressed onto it, and their undersides became discs coplanar with the
  ground texture. Hidden from above, but two surfaces in one plane flicker from any angle that
  sees the plant's edge. Fix: `_lobes` leaves out the triangles within 1 % of the height above
  the ground; leaves keep a floor. Pinned by `ground_flat_triangles(...) == 0` for every build.
- **"For every plant from the gallery" was checked for 11 of 86 — and was false for the
  pumpkin.** The builder resolved its recipe from the record's `species_name`, which prefers the
  species DATA's common name; the canvas resolves the sprite from the item's own string. A
  gallery "pumpkin" finds the bundled record of "Winter Squash": the canvas drew `species/pumpkin`
  and 3D built `species/squash` (harmless today — same archetype, same palette — and wrong the
  day fruit arrives). A string of blanks diverged too: 2D answers the rose (its partial match of
  an empty needle), the snapshot stripped the string. The integration test had planted eleven
  species by hand. Fix (ruling R14): the record carries the item's own string, raw
  (`sprite_species`), and the builder hands the rule exactly what the renderer hands it. Pinned
  by `tests/integration/test_scene3d_plants.py::test_every_gallery_plant_is_built_as_the_sprite_the_canvas_draws`
  (all 100 gallery plants through the real drop) and `::test_every_species_string_...` (all 222
  keys and the odd strings). *Sharing a function is half of sharing a rule; the other half is
  its inputs. And a claim over a list is tested over that list.*
- **With every file shipped, nothing asks whether a file is there.** The extracted rule takes an
  `available` predicate; the renderer passes "the SVG exists". Dropping that argument survived
  3,048 tests: the shipped sprite set is complete, so the fall-through to the category sprite
  never ran, and the test of it exercised the pure function with a fake predicate. Without it a
  missing SVG gives a dead path, no renderer, and a plant painted as a bare circle. Fix: tests
  that patch `Path.exists` for one sprite and assert both the answer and what the plant item
  paints, and a differential of old rule against new rule and renderer over every missing-file
  set (`scripts/make_sprite_resolution_golden.py --differential`: 481,096 comparisons). The
  differential earned its keep at once: my own transcription of the old resolver into that script
  had dropped its last `exists()` — 3,582 mismatches, all in the default-category step. *I had
  written down a line I had not read.*
- **"Standard library only" was true of every file and false of the import.** `core/plant_art`
  imports nothing but the standard library, and an AST scan says so. The sprite generator
  imported it by name — which first runs `core/__init__.py`, PyQt6 and twenty app modules. The
  script, pure standard library until then, needed Qt, and two texts said otherwise. Fix: it
  executes `recipes.py` by file path; a test runs it with PyQt6 and numpy blocked. *A property
  of a module's source is not a property of importing it: the package's `__init__` runs first.*
- **Five ids are a claim about five ids.** The no-clones gate took five fixed ids and passed
  with 0.005 to spare; over 24 others a hedge section reached 0.984 and 2.2 % of its pairs
  exceeded the gate's own bound (the reviewer's numbers; over 30 ids I measured 0.983 and 4.1 %), and two texts stated the five-id maxima as properties of the
  builder. Fix: more variation where a shape repeats by nature (a hedge cut by hand in five ways,
  a ground cover with a lumpier skyline), a gate over twelve ids a recipe that bounds a
  distribution, and the measured table beside it (30 ids: maximum 0.975, 99 % of 53,505 pairs
  below 0.952).
- **On a shared machine a millisecond is not a unit.** The first budget was six times a median
  taken in a quiet minute; the review measured a daily scrub tick at 218 ms on the busy box. The
  same first build read 330 ms quiet and 1,200 ms with every core busy — and its CPU time rose
  with its wall time (828 ms against 916 ms), so the process was not waiting, it was slower.
  Neither a bound in milliseconds nor one in CPU time survives that. What does: the counts that
  cause the time (shapes built per tick: exact for a first build and a cold tick, bounded at
  10 % of the plants that changed for a warm one), a ratio measured in one process (warm against
  cold), and the time in units of a small reference workload timed alongside — the warm tick of
  `bench_large` read 0.134–0.138 units at a unit of 114–126 ms and 0.135 at a unit of 76 ms. The
  fix for the cost itself is the shape cache: a plant that only grew is scaled, not rebuilt
  (15 ms against 342 ms per tick on the busy box).

**What the second review found behind the fix round's own claims** (ADR-059 addendum "plant art
v0", "what the second review found").

- **A sample's maximum was written into a requirement as a limit — the first round's lesson,
  repeated one level down.** FR-3D-PLANT-02 said "no part more than 10 % outside the canopy
  circle" because 117,000 builds had read 1.092 at most; a pumpkin at a proportion its growth
  passes through read 1.1006 (one id in the review's 300,000). It said at least 5 % of the
  foliage's surface lies above "62–87 % of the height"; a rhubarb 46 cm tall and 2 m wide read
  60.3 %. Cause of the first: `_fit` pulled strays onto the circle, THEN centred, THEN scaled —
  each step undoing part of the one before, nothing saying where a vertex ends. And the sample
  stood on 43 of 171 proportion steps (since the shape cache, a recipe's seedling, mid and
  mature size are one shape). Fix: the fit's LAST step puts whatever is beyond 1.09 canopy radii
  onto that circle (`REACH_MAX`, `_rein_in`) and reports it — tested on 500 hostile point clouds,
  not on well-behaved builders; the mass is stated as measured; the tests sweep every proportion
  step. *A claim is structural or it is a measurement with its sample. A maximum is neither.*
- **A least-recently-used cache has a cliff exactly where its user stands.** 1,024 shapes, and a
  scrub that asks for every growing plant once per tick in the same order: with 1,024 growing
  plants a warm tick rebuilt none, with 1,025 it rebuilt all 1,025 on every tick (1.9 s against
  0.1 s; 6 s at 2,000) — the shape dropped is always the one needed next. No test stood at the
  cap. Fix: the cap is in bytes and the count follows the plan; a shape that was dropped comes
  back only in place of shapes nobody asked for since, so beyond the cap a tick rebuilds the
  overflow (1,025 plants: 1 per tick). Pinned at the cap, one past it and far past it:
  `tests/unit/test_scene3d_plants.py::TestShapeCache::test_at_its_cap_the_cache_has_no_cliff`.
  *Test a cache at capacity + 1 with its consumer's access pattern.*
- **Behind a cache, "build it twice and compare" compares a build with a look-up.** The
  determinism tests passed with UNSEEDED dice: the second build was a cache hit. Three archetypes
  were never built cold in any test. Fix: `build_cold` clears the cache; the determinism test
  asserts the second build was a build (0 hits, 1 miss; two different colour arrays) and covers
  every archetype. *When a cache is added, re-read every test that calls the cached function
  twice.*
- **A read-only flag is a request.** `Mesh.from_arrays` returned read-only VIEWS of writeable
  arrays; `mesh.colors.setflags(write=True)` succeeded. Before the cache that could damage one
  mesh; with shared arrays, every later build of that plant. Fix: the memory under a mesh's
  arrays is an immutable `bytes` object — the flag cannot be set on the array or on its base.
  Pinned by `TestShapeCache::test_remembered_arrays_cannot_be_written` and
  `::test_a_mesh_from_arrays_cannot_be_made_writeable`.
- **Dice that are rolled per thing built depend on how many things are built.** A conifer has
  three to six whorls by its proportions and rolled each whorl's dice as it built it; gaining a
  whorl moved every later number up the stream — the one plant that was re-rolled when it grew
  (the review suspected all of them; measured, a plant one proportion step on is 0.99–1.00 itself
  for every archetype, against 0.71–0.92 for another id). Fix: all six whorls' dice are rolled
  always. `::test_a_conifer_that_gains_a_whorl_keeps_the_ones_it_had`.
- **A review finding is a claim too: "twelve gallery species have no height" — the twelve are not
  in the gallery.** Checked against the gallery's own item list: all 86 gallery species have a
  bundled record and a height; the twelve named (squash, turnip, arugula, chard, okra, tarragon,
  lemongrass, marjoram, bay laurel, stevia, sorrel, lovage) are twelve SPRITES whose species the
  bundled database does not know, reachable by a species string from a plant list, an older plan,
  an agent or the keyboard. The substance stood — such a plant has its own sprite on the plan and
  a grey disc in 3D, and the docs had not said so — and the documents now say it with the right
  population. *Verify a finding against the code before acting on it, in both directions.*
- **A measuring script loaded two plans — and rewrote the owner's recent-files list.**
  `scripts/measure_plant_art_3d.py scrub` and three scratch probes of this story loaded fixture
  plans with `ProjectManager().load(...)` in a plain Python process. A load ends with
  `add_recent_file`; outside pytest the settings are the developer's real ones, and on Windows
  they are the registry (`HKCU\Software\cofade\Open Garden Planner`) — an `APPDATA` prefix on
  the command, which those runs did have from the second fix round on, does not touch it. The
  owner's ten recent files became fixture paths of agents' worktrees. Nothing in the suite could
  see it: `tests/conftest.py` rebinds the settings names for pytest only. Measured afterwards
  under isolation (a per-process test key): a load of each of the three plans writes exactly ONE
  settings key, `recent_files`, and no file in the profile; creating a canvas reads the settings
  and writes nothing; importing the app writes nothing. Fix: the committed script isolates
  itself at import (as conftest does) and refuses to load a plan unless its store is a test
  key; `tests/integration/test_scene3d_plants.py::test_the_measuring_script_keeps_out_of_the_owner_s_stores`
  runs it in a child process without conftest and checks where the write landed — with a driver
  that loads nothing if the isolation is broken. *Isolation that lives in the test harness
  protects the tests. Anything else that imports the app — a script, a probe, a benchmark —
  needs its own, before its first app import; and "which store does this write to?" is a
  question to ask of every `load`, not only of every `save`.*

### 11.4.13 What the built world and base stacking taught (Phase 17 L1.6, #385)

None of these reached a user. Each was caught by a test written to be able to fail — and each
passed the tests that only looked at one number.

- **A caster from the ground is not conservative — it hides the plant.** A plant in a raised bed
  was extruded from the garden floor *through* its bed. That looked like a harmless
  simplification ("its shadow is a little short"). Measured at a 35° sun: a 60 cm plant's tip
  reached 85.7 cm past its footprint, the 40 cm bed's own shadow 57.1 cm past the bed's edge — so
  a plant more than 28.6 cm from that edge cast nothing the bed did not cast already. Every plant
  in the middle of a raised bed was absent from the shadow overlay and the hours-of-sun map. Fix:
  a caster has a base (`core/shadow_geometry.ShadowCaster`, ADR-037 addendum); the tip moves
  `base / tan α` out (54.3 cm here). Pinned by
  `tests/unit/test_shadow_caster_base.py::TestSweptShadowDefinition::test_the_bed_casts_the_part_below`,
  which asserts the old tip was inside the bed's shadow. *"Slightly wrong" hid "missing": measure
  a simplification against what it is next to, not on its own.*
- **Changing shipped behaviour for one class of input: pin everything else first, and let an
  independent oracle say who is in the class.** The golden
  (`tests/fixtures/shadows/shadow_golden.json`) was generated from the unchanged code one commit
  before the change, and holds per bench plan the union of all shadows *and* the union of the
  casters the change must not touch. The test's own re-derivation of "which casters stand on
  raised soil" (it does not call the new function) found 22 of bench_small's 45 parented plants —
  the other 23 are in in-ground beds or on a trellis. The first assertion said 45. *An oracle
  that shares the implementation's assumption shares its mistakes.*
- **A closed polyline's stroke is a ring with a hole — and height, validity and budget all pass
  on a slab over the hole.** `polyline_footprint` of a fence drawn round a garden returns two
  rings. When this story was written both sat in `record.footprints` and the default builder laid
  a lid over all 48 m² of the test garden; the scene contract has since been corrected (§11.4.14,
  ADR-059): `footprints` holds the stroke's OUTER ring, the garden is a hole in `holes`, and
  `verify_builder` refuses a solid over it
  (`TestPolylinesAreBuiltFromTheCentreLine::test_the_gate_refuses_a_slab_over_the_garden`). The
  lesson for a builder is unchanged: the outer ring is not the fence's shape. Every built-world
  builder for a polyline reads `record.path` and works segment by segment; what catches a
  regression is plan-view AREA (`plan_area`: the union of the mesh's triangles seen from above ≈
  length × width), `covers(x, y)` at points inside the loop, and the hole-cover bound
  (`::test_nothing_is_built_over_the_hole`). The 2D shadow and heatmap still treat both rings as
  footprints; that is deliberately not fixed here (a separate issue; the golden pins it as is).
  - **The first `covers` probe sat on a diagonal.** It tested the centre of a symmetric loop,
    which lies exactly on an ear-clipping diagonal of the lid: "not covered", under a lid. Probe
    points go off every axis of symmetry.
- **A bounding box is aligned with the frame, not with the building.** The spike laid a shed's
  ridge along its scene-frame bounding box. In the item-local frame a *rectangle item* is
  axis-aligned and the rule looks right; a shed drawn as a *polygon* at an angle has its vertices
  turned inside the local frame, and the ridge came out askew to its walls. Found only because the
  builder matrix turns the local geometry by 17° and 213.5°, and only by a containment assertion
  (the ridge tile left the roof). Fix: the box aligned with the footprint's longest edge
  (`roofs.bounding_box_ridge`). Pinned by
  `tests/unit/test_scene3d_builders.py::TestShedRidge::test_it_turns_with_a_footprint_drawn_at_an_angle`.
  *A builder never sees the item's rotation, so "parametrise over rotation" must also mean the
  geometry inside the record.*
- **A ridge tile with square ends overshoots an eave it meets at an angle** — by
  `half width × tan θ` (2.4 cm on a dragged ridge, 3.2 cm on a trapezoid). The top was exact, the
  budget held, every face validated. Fix: each of the tile's two foot lines ends where *it*
  crosses the roof's edge. Caught by `outside_distance(plan points, eaves) ≤ 1e-3`.
- **Clamping a leaf's vertices at the trim height turns leaves inside out.** The first hedge
  brought every vertex above the height down onto it. A leaf standing mostly above the line was
  flattened into the plane and its winding flipped against its stored facing (24 matrix cases).
  Fix: a leaf that reaches too high is moved down *whole* (`hedges.leaf_shell`); the highest leaf
  sits on the height, so the top is still exact by construction.
- **`core/scene3d/` cannot import pyclipper** — the package's import rule (AST scan) allows the
  standard library, numpy and Qt-free `core` modules. A roof's overhang needs an outward offset;
  `primitives.offset_ring` is a mitre offset in numpy in which every edge moves exactly the
  distance (asserted per edge). If a builder ever needs polygon booleans, they go through a
  `core` module, not around the scan.
- **Six tests unpacked the caster as a pair.** `footprint, height = collect_shadow_casters(...)[0]`
  — the cost of a positional type is paid when it grows. `ShadowCaster` is a `NamedTuple`, so the
  third field is named from now on; the shadow functions still accept a bare pair (the spike's
  probes pass one) and treat it as standing on the ground.

Found by the senior review's first round, in code whose tests were all green:

- **A link is not a location.** The first cut lifted a plant onto its bed's soil whenever
  `parent_bed_id` named a raised bed. But the app keeps that link as bookkeeping: it is evaluated
  when a plant is created (also in bulk, also pasted), dropped, or moved by the agent — and by
  nothing that changes a bed — and `set_parent_bed` sets it on purpose
  without containment. Shrink a raised bed away from its plant and the link stays — the plant on
  the lawn then cast from 38 cm, and at a 15° sun its shadow began 141.8 cm away from it, with
  111.8 cm of lit ground in between. New wrong output in the shipped overlay and heatmap, from a
  change whose golden proved "nothing on the ground moved" (true — and beside the point). Fix:
  `item_base_cm` lifts only when the link holds AND the item's centre is inside the parent's
  shape, with the app's own point-in-bed construct, extracted once
  (`footprints.shape_contains`; WHICH point it is asked with was corrected in the second round,
  below). Pinned by
  `tests/integration/test_scene3d_base_stacking.py::TestTheLinkAloneNeverLifts`. *Before keying
  geometry on a relation, find out when the relation is re-evaluated — here: when a plant is
  created (also in bulk, also pasted), when one is dropped, when the agent moves one; never when
  a bed changes.*
- **"Bit-identical" has to say on which machine.** The golden compares exactly only on win32;
  the CI test jobs run on Linux, where the gate is structure plus 2e-3 cm. The ADR said
  "bit-identical, by construction and by proof". The proof that holds everywhere is a different
  test: the released module kept as an oracle next to today's (§8.10.7). *A claim about
  exactness names the platform, or it is the weakest platform's claim.*
- **"The body is wider" was reasoning; the measurement said the opposite for three of five fence
  styles.** The ADR compared a 3 cm stroke with 9 cm posts and concluded that 3D shadows are
  wider. Projecting the meshes onto the ground: a picket fence casts 0.67–0.70 of the 2D strip's
  shadow, a metal fence 0.19–0.24, a chain-link fence 0.13–0.19 — fences are mostly air, and the
  2D model casts a solid strip. Walls, stone-wall and hedge fences ARE wider (1.04–1.37). The
  table is now produced by a committed script and held by a test.
- **A mitre limit is not a bevel.** `MITER_LIMIT = 4` cut a hairpin's mitre at four offsets: a
  116 cm eave spike on an acute-triangle house, 76 cm of coping on a hairpin wall — and the
  footprint test's √2 bound only ever saw right angles. Fix: bevel beyond 2 offsets on the side
  where the edges run apart (`BEVEL_BEYOND`); keep the true intersection where they meet.
  Acute triangles and hairpins are in the matrix now. *A containment bound proven for the
  corners in the test matrix says nothing about the corners that are not in it.*
- **A mirrored name set without a guard chooses for the names it does not know.** The fence
  builder's own list of five fence styles sent every other value to the picket fence — a path
  style, and any fence style added to the 2D table later. Fix: one dispatch (`builders/lines.py`),
  a plain panel for what no builder knows, and the mirror pinned against the 2D table. The
  container material names are imported instead of retyped, and the nominal height asks the 2D
  resolver instead of keeping a third copy of the container set.
- **A lip the plan does not hold lowered the plan's soil by 2 cm.** The 2 cm soil drop under a
  rim suits a raised bed, whose height is a rim. A container's height is its soil FILL height —
  the resolver says so in a comment marked "known simplification". Applying the drop there put
  the plant under the plan's own soil level. Fix: `soil_surface_cm(type, height)` — at the
  height for a container, 2 cm under the rim for a bed — and the drop is documented as the
  assumption it is, with its effect on shadows (7.5 cm at a 15° sun).
- **A tuple's third element is whatever its maker meant.** `compute_scene_shadows` read
  `caster[2]` as a base for any sequence longer than two. Nothing passed one — yet. Fix:
  `caster_fields` unpacks by type and refuses everything but a `ShadowCaster` and an exact pair.
- **A budget raised to make a loaded machine pass stops being a budget.** The build budgets went
  from 40 / 60 to 60 / 90 ms in the last commit of the first cut, although the loaded medians it
  quoted were under the old ones. With the ×3 CI factor a per-vertex Python loop would have
  passed. They are back, and a clock-free call count stands next to them (§8.10.7).

Found by the senior review's second round, again with every test green:

- **The first fix made a shadow depend on a warning badge.** Round 1 asked "is the plant inside
  its bed" with the app's own membership point, the centre of `boundingRect()` — the review had
  prescribed exactly that, for consistency with auto-parenting. But `CircleItem.boundingRect()`
  grows towards +x / +y while the antagonist badge shows, so its centre moves by up to 1.8 cm
  along each axis (2.55 cm in all):
  a linked plant 1 cm inside a raised bed's east edge stood at 38 without the badge and at 0
  with it, in the 3D record and in the 2D caster. Fix: the LIFT asks the item's stable
  geometric centre (`footprints.standing_point`, the outline's anchor — the origin of the 3D
  record); the link decisions keep their shipped point; one predicate (`shape_contains`) serves
  both. *A bounding rect is a paint rect. Before using one as geometry, list everything that
  changes it: here a badge, a companion highlight, the shadow margin, the spacing ring.* And
  the "identical behaviour" of the refactor that extracted that point was true by reading
  only: swapping it for the geometric centre passed all 114 related tests, until one probe
  where the two points differ pinned each decision (`TestWhichPointEachDecisionAsks`).
- **A universal sentence stood next to a truth gate with no number behind it.** The gate row
  said that a 3D shadow ends where the 2D one ends, whatever the kind — reasoned from "the
  height is the same number". The tip is cast by the highest EDGE, and a gable's ridge stands
  mid-house while the 2D prism's top edge is at the far wall: asked for the reach, the story's
  own script printed −270 cm for the bench house with the sun square to its ridge, −150 cm for
  a shed, +30 cm along the ridge (the overhang), +15 cm for a wall (its section). A reviewer
  would have reported a 2.7 m truth-gate miss, or a creator would have "fixed" the roof. Fix:
  the sentence is deleted, the reach is a column of the script and of every copy of the table,
  and a test scans docs and skills for the claim. *Next to a gate, only numbers a script
  prints.*
- **"Every line solid is held to the bound" held for the sizes in the matrix.** `verify_builder`
  refuses a solid over more than half of a hole. The matrix's loops are 8 m × 6 m; a closed
  wall of 1 m side covers 56 % of what it encloses with its 38 cm section — correctly — and is
  refused. The bound is stated with its size now, and a 1 m loop is pinned with an explicit
  limit. The same shape of mistake as the corner bound: "nothing further than 2 offsets" held
  for legs longer than the section; a 25 cm-leg zigzag under a 38 cm wall reaches 2.7 offsets.
  *A bound asserted over a matrix is a bound for the matrix's parameter ranges; say the range.*
- **A lookup that is "one per walk" is the place for what a walk needs once.** The base rule
  called Qt's `contains` per plant, which rebuilds the parent's shape each time; with the
  plant's `boundingRect()` (a Python override) that was 6 µs of the 7.6 µs the rule cost per
  plant. `ItemLookup.shape_of` builds the shape once per parent and walk; the rule costs 2.8 µs.

Found by the senior review's third round — CI was red on a head whose every local run was green:

- **The fix for a fixed wait was a race.** Round 2 replaced `qtbot.wait(400)` by "wait for the
  recompute count, then for the debounce timer to be idle". CI: `assert 6 == 1 + 4` in the Test
  job, green in the Coverage job on the same commit, green in every local run. A recompute sets
  the overlay's path, the scene emits `changed` one event-loop round later, and `changed` is
  wired to the debounce: straight after a recompute the timer is idle and the echo is still on
  its way. Delivered late, it carried an edit nothing had announced into the negative control.
  Fix: `settled` waits for the count, then for the echo (a `scene.changed` delivered since that
  recompute), then for the debounce; and two tests hold both halves of the race still by
  running the recompute synchronously. *A timer being idle says nothing about what is queued.
  If a system answers its own action with a signal, that signal is the thing to wait for.*
- **A field's description is the contract an agent reads.** `link_is_geometric: false` on a
  LIFTED plant was pinned by a test and explained in an ADR addendum, while the tool schema
  still told an agent that false means "the plant sits outside the bed's outline". The
  description, the tool's docstring and FR-AGENT-16 now say what the field tests and where it
  can disagree with the sun study.
- **A cache with a lifetime needs more than a sentence.** `ItemLookup` holds each parent's
  shape for one walk; kept across a bed resize it answers 38 where the truth is 0. The guard is
  a source-reading test: constructed only in the two walks, never stored.
- **A range read at a coarse step is not a range.** "From 16 cm to 120 cm" came from readings
  2 cm and 10 cm apart; at 1 cm the wall starts at 15 and the hedge fence is refused again at
  114 after passing at 112. State the step, or pin the cases a test needs and no more.
- **A bounded memory can still be an unbounded log.** The unknown-style warning cleared its 64
  names when full, so 65 names wrote 65 lines on every rebuild pass. When full: one line, then
  silence — the policy the snapshot's log already had, three files away.

Found while merging the scene contract's second fix round (`9944012`):

- **A bound added in one layer opens a state in the layer above.** The contract began to refuse
  every length beyond 10 km (`MAX_LENGTH_CM`). A raised bed of 10 km + 1 cm then had no record —
  and its plant, whose base is the bed's soil 2 cm lower, had one: floating at 9,999.99 m over
  nothing. A taller bed took its plant out of the 3D scene with it (the plant's base was out of
  range too). Garbage in, but the rule "a parent that has no solid is not there" was mine and
  no longer held. First fix: `soil_surface_cm` gives no base beyond `MAX_PARENT_HEIGHT_CM`, the
  contract's bound mirrored and pinned. **That fixed one axis and named it a rule**: a raised
  bed 30 km WIDE has an ordinary height, got no record all the same, and its plant stood at 38
  over nothing (review round 3). The rule is settled where the fact is known: `snapshot_records`
  puts every record whose parent got none on the ground, for whatever reason the parent was
  left out; the height bound stays as what it is — no base from a height beyond the bound.
  *When an upstream contract starts refusing something, probe what your own rule derives from
  it — and put the consequence where the refusal is visible, not where one symptom of it was
  first seen.*
- **A flag beats an inference, and the builder must not lean on the producer.** Round 1 could
  not tell a self-crossing house that resolves to one ring from an ordinary one, and gave it a
  roof. The contract now says `outline_resolved`, and drops the ridge. The house builder reads
  the FLAG — a test hands it a resolved ring WITH a usable ridge and still gets the block — so
  the rule does not rest on a second module remembering to leave a param out.

Found by the last review pass and at the merge of the plant story (`5c44578`):

- **A requirement stated the mechanism where it meant the invariant.** FR-SUN-11 said that
  moving a plant into or out of a bed changes its shadow "only where the move also re-evaluates
  the link". False in both directions for a LINKED plant: the base is asked on every walk with
  the plant's own centre, so any move takes it 38 → 0 → 38 with the link untouched. What is
  limited is the LINK. *Write what holds for the user (where the plant stands follows its
  centre); put the mechanism's limits (which gestures link) next to it, as limits.*
- **The list of "how a link comes about" was two entries short.** All four array actions copy
  the source's `parent_bed_id` through serialisation (only `item_id` is stripped) and the bed's
  child list is not told; a plant mirror-copied without its bed gets no link at all. And "a bed
  that is moved takes its plants with it" holds for a mouse drag, the arrow keys and an agent
  move, not for a typed coordinate or align / distribute. Each is pinned now
  (`TestCopiesAndMovesThatDoNotEvaluateTheLink`) and is in the follow-up issue. *A list written
  from the call sites of three functions misses every path that calls none of them: also
  enumerate the ways an item is CREATED and the ways it MOVES.*
- **Two stories, one registry.** The plant builder and the built world were developed against
  separate registries; `production_registry()` now holds both. One test says that no kind
  belongs to both families, that each of the 15 kinds resolves to its own builder, and that
  the rest of the `ObjectType` enum falls to the default — over the enum, not over a sample of
  it (the earlier test checked eleven hand-picked kinds).

The rest of that pass is method and lives in §8.10.7: a running timer asserted as a fact, "up
to N" without the worst direction, a source guard without a census, a committed script outside
the suite's isolation.

### 11.4.14 Four things measured while building the 3D scene contract (Phase 17 L1.1, #385)

None of these was reported by a user: each was found by measuring a claim before building on it
(ADR-059). Each would have shipped a diff that silently lies to the engine.

- **A hash is not an equality — `hash(-1.0) == hash(-2.0)` in CPython.** The first design compared
  two snapshots by three hash signatures alone ("cheap: a hash of already-normalised tuples"). A
  probe before writing it: `hash((-1.0, 3.0)) == hash((-2.0, 3.0))` is `True`. So a vertex moved from −1 cm to −2 cm
  (item-local coordinates are centred, hence often negative and often whole numbers) would have
  produced an empty diff, and the 3D view would have kept the old shape with nothing failing.
  Fix: `Record.same_geometry` / `same_transform` / `same_material` compare the signature first and
  the values second; `diff` uses only those. Pinned by
  `tests/unit/test_scene3d_contract.py::TestRecord::test_a_signature_is_only_an_accelerator`,
  which asserts the collision itself and then the detected edit. *A hash can prove two things
  different, never the same; when "same" means "skip the work", confirm it.*
  - **And then the confirmation itself had a hole.** `same_geometry` compares eight fields; the
    collision test pinned one of them. When `holes` became the eighth, the mutation check
    (`scripts/mutation_check_scene3d.py`) deleted its comparison and every test still passed.
    The collision is now asserted in each value-bearing field, and for the transform and the
    material (`test_every_geometry_value_is_compared_not_only_hashed`,
    `test_a_transform_and_a_material_are_compared_too`). Floats collide when they are equal
    modulo 2**61 − 1: besides −1.0 / −2.0, `hash(1.0) == hash(2.0**61)`.
- **Float dust is an edit unless you say otherwise: a HOUSE was rebuilt on 689 of 1,000 moves.**
  "Move → transform only" held for every shape in the first matrix and was false for the one item
  that owns another: a HOUSE's ridge is a separate item whose points the app re-writes by
  `+ delta` on each move (`PolygonItem._move_ridge_by_delta`). Read back into the HOUSE's own
  frame, `(p + d) − (c + d)` is not `p − c` in floats. Measured without snapping: 689 of 1,000
  random moves changed the HOUSE's geometry (the first one already), 271 the ridge item's own.
  Fix: every length of a record is snapped to 1e-7 cm (`core/scene3d/record.quantize_cm`) — 0
  changes in 20,000 moves, by which time the dust had grown to 1.1e-10 cm. Pinned by
  `tests/integration/test_scene3d_snapshot.py::TestHouseRidge::test_a_thousand_moves_never_leak_float_dust_into_the_geometry`.
  - **A second, coarser grid for the ridge was written first and then removed.** It was argued
    from "the error accumulates per move"; the mutation check showed the test passed without it,
    and the measurement above showed why. *An argument that a safeguard is needed is a hypothesis;
    delete the safeguard and see whether anything fails.*
  - **`round(x, 15)` is not "no rounding".** The first mutant meant to switch the grid off set
    the decimals to 15 and survived a test that depended on the grid: 1e-15 still absorbs dust of
    5e-17. A mutant has to remove the behaviour, not weaken it.
- **A polyline's 2D stroke polygon is not the same polygon after a move.** `polyline_footprint`
  inflates the centre line with pyclipper on a 1/1000 cm integer grid, and the 2D code calls it
  with *scene* coordinates. Move the line by a non-multiple of that grid and the polygon is not
  the old one translated — its vertices differ by up to the grid. A record derived from the scene
  polygon would therefore change geometry on every move. Fix: the record inflates the centre line
  in the item-local frame. Consequence, stated rather than hidden: for a polyline,
  `transform ∘ local footprint` matches the 2D stroke polygon only to that grid (measured
  1.6e-3 cm, asserted ≤ 3e-3), while the centre line — what fences and walls are built from —
  matches to 1e-7 like every other shape. Pinned by
  `test_scene3d_snapshot.py::TestTransformReproducesFootprint`.
- **Two things that looked like a diff bug and were the plan being right.** (1) Resizing the drawn
  circle of a *measured* plant produced an empty diff: correct — its footprint is the canopy
  (`plant_canopy_radius_cm`), not the circle, exactly as in the 2D shadow. (2) A resize that keeps
  a corner fixed is reported as geometry **and** transform: correct — the record's frame hangs on
  the item's centre, and that centre moved. Both are pinned as behaviour, not worked around.

**What the independent review then found behind a green suite** (same story, one day later).
Seven gates were green and the contract was wrong in two places other stories were already
building on.

- **A closed fence became a slab, and every gate passed.** `polyline_footprint` returns a closed
  stroke as TWO rings — an outer one and a hole, told apart only by their winding. The record
  carried both as `footprints` and the default builder extruded both. Measured on a 10 m × 8 m
  fence, 10 cm wide: rings of +818,062 and −782,100 cm², a solid over 81.8 m² of ground where the
  fence stands on 3.60 m², and an inner wall facing into the solid. "Every ring matches the 2D
  ring" was true, "the mesh validates" was true, "the top is the fence's height" was true. *No
  gate measured an extensive quantity.* Fix: `Record.holes`, orientation enforced by the record,
  a default builder that cuts holes out and checks its own cap area, a plan-view check in
  `verify_builder`, and a third committed plan made of the shapes the bench plans lack
  (ADR-059 decision 3 and 9; `tests/integration/test_scene3d_snapshot.py::TestClosedStrokes`,
  `test_scene3d_edge_plan.py`). A 2 cm gap **at a corner** does not help: the strokes of the two
  sides overlap there, and the loop closes anyway (35,952 cm², one hole).
  - **"A gap narrower than the stroke closes it" — written here first, and false.** A stroke
    has butt ends: it reaches half its width sideways and nothing past its end points. So a
    10 cm stroke closes a corner gap up to 5.000 cm, a 6 cm corner gap stays open, and a gap in
    the middle of a straight run stays open at 0.01 cm (the re-review measured all three). The
    sentence had been generalised from the one 2 cm fixture; the edge-case plan now holds a fence
    of each kind. *One measured case is one case — say what was measured, not the rule it
    suggests.*
  - **The same defect is live in the 2D shadow, and is NOT fixed here.** `item_footprints` hands
    both rings to `compute_scene_shadows` as solids, so the hole ring casts the shadow of a slab.
    Reproduction with `core/shadow_geometry` alone (no Qt): `polyline_footprint([(0, 0), (1000, 0),
    (1000, 800), (0, 800), (0, 0)], 10.0)` → two rings; `compute_scene_shadows([(ring, 120.0) for
    ring in rings], 60.0, 180.0)` → **88.8 m²** shaded. The stroke region cut into triangles and
    shaded the same way gives **17.5 m²**; the same fence with its west side removed (no hole,
    one ring) gives 16.7 m² both ways. The hours-of-sun heatmap reads the same footprints. It is
    left alone because `item_footprints` is pinned byte for byte by the golden fixture and the 2D
    shadow is shipped behaviour — the fix (shade `outer − holes`, as `group_rings` now makes
    easy) is a change of its own with its own before/after.
  - **Same family, also 2D, also left alone: a polygon that crosses itself.** `_caster_paths_int`
    assumes a simple ring ("normalize CCW for stable winding"). For the bow-tie
    `[(0, 0), (400, 300), (400, 0), (0, 300)]` at 300 cm, sun 60° / azimuth 180°, it shades
    80,000 cm²; its two lobes shaded as the two prisms they are give 129,282 cm² (measured; the
    mechanism was not investigated). The 3D record resolves such a polygon into its lobes; the 2D
    sweep does not.
  - **A plan-view check has its own blind spot.** The first version sampled each *triangle* at
    four points and summed the weights of the ones inside a hole. It read 205 % for a slab over
    the fence's hole (measured — a share above one), and it cannot see a small hole under large
    triangles at all: the two cap triangles of a 10 m slab have eight sample points, and none of
    them lies in an 80 cm hole at (80…160, 210…290) — 0 % covered. The check now samples the
    *hole* (a 24 × 24 lattice of its own interior points) against the triangles
    (`test_a_hole_under_two_huge_triangles_is_seen`, `test_half_a_hole_covered_is_half`).
    *Sample the thing you are asking about.*
- **Recovery was not expressible in the protocol, and the test hid it.** `SceneSync.reset()`
  forgot its records and touched no sink. After a sink call failed in mid-transaction the sink's
  transaction was still open, so the next `begin()` raised and the sync was poisoned again:
  there was no sequence of protocol calls that recovered. The test passed because it first called
  `RecordingSink.reset()` — a convenience of the test double that no engine has. Fix: a tenth
  protocol method, `clear()` (hold nothing; legal at any time, also inside a transaction), which
  `reset()` now calls. (That `reset()` forgets the sun and ground it deduplicates against — or the
  first sun after a recovery would be swallowed as "unchanged" — was already so; it is now pinned.) *A fake that is more
  capable than the real thing certifies behaviour the real thing does not have: test recovery
  with nothing but the interface.*
- **One malformed plant blanked the whole plan.** `plant_species = {"scientific_name": None}` on
  one item raised `AttributeError` out of `snapshot_records`, so no record reached the engine.
  The snapshot now contains any exception to its item, reports the item through `skipped=` and
  logs it once per item and kind of failure (the exception's type, not its message — a message
  can carry a value that changes with every mouse move, and the pipeline snapshots on every edit). *A loop
  over user data needs its `try` inside the loop — and a place where what it swallowed can be
  read.*
- **"Rotate → transform only" was false for the one item a house owns.** A `ROOF_RIDGE` item had
  a record; the app re-derives its points when the house turns (ADR-046), so that record changed
  *geometry* on 400 of 400 rotations. The test that should have seen it took its baseline after
  the rotation. Ridge items now get no record (the ridge is its house's param), and the test
  takes its baseline first.
- **(Re-review.) "Always simple rings a builder can triangulate" was written down and never
  checked.** Four HOUSE outlines, each five to seven vertices, each drawn crossing itself: one
  resolved into a single ring of ten vertices (so "several rings means resolved" was false and
  the house kept a ridge that belonged to another shape), one into an outer ring with a pocket
  the default builder could not cut ("only strokes have holes" was false), one into a ring that
  touched itself, one into nothing at all — its hole began on its outer ring, and ownership was
  decided by a point test at that very vertex. Over random such outlines 2–9 % got no record and
  4–14 % no solid. Fix: one predicate, `polygon.is_buildable_region` — the default builder's own
  triangulation, proven by area and orientation — asked for every region before it is handed on;
  `params["outline_resolved"]`; no ridge for a resolved house. Pinned at 0 of 7,500 random
  outlines and 0 of 4,500 random strokes (`test_random_self_crossing_outlines`,
  `test_random_strokes`). *A sentence that begins "a consumer can rely on …" needs a test that
  ends in a number.*
  - **The library the fix leaned on was wrong too.** The ruling said: take the ring hierarchy
    from pyclipper's `PolyTree`. For an outline that retraces one of its own edges, the strict
    tree handed a solid triangle of 357 cm² out as a hole, and the plain union returned rings
    whose signed areas sum to 33,133 cm² where the outline fills 36,704. Neither is a wrong
    *shape* at a glance. They were found because the check compared against a raster of the
    drawn outline's winding number — a dozen lines of numpy that know nothing of the clipper —
    and not against a second call into the same library. Every reading is now held to that
    raster (`_matches_outline`). *When the tool's answer is the thing in doubt, verify it with
    something that does not share its code.* (And then the mutation check let "the reading is
    taken on trust" SURVIVE: in every sampled outline — 19,500 — the wrong reading was also not
    buildable, so the other check had already turned it down. The safeguard is kept for the
    reading that is wrong and buildable, and pinned with a simulated one. *A safeguard nobody
    can trigger with real input still needs a test, or the next refactoring removes it.*)
  - **Zero-area triangles are not harmless in float32.** Along the edge of a diagonal stroke
    that other strokes cross, vertices of several rings lie on one line; an "ear" of three of
    them has a doubled area of 1e-14 cm² — float noise around zero, positive by luck. Rounded to
    float32 thirteen of them came out wound downwards and `Mesh.validate` refused the fence.
    The ear clipper now emits no triangle for a flat corner, and `prism_mesh` none below
    float32 resolution. Found by this round's own ladder test; the first round had no diagonal
    stroke crossed by another.
  - **The cost cliff was worse than reported, and elsewhere.** The reviewer measured 2.6 s for a
    ladder of 58 holes. One hole is enough: a closed fence along an outline traced with 400
    vertices took 12.6 s to triangulate, with 750 vertices 150 s — on every geometry tick. The
    bridge search tried boundary vertices one by one in Python against every edge. It is one
    array pass per hole now (45 ms and 89 ms for those two), with stated bounds beyond which
    the region is refused instead of built slowly.
- **(Fix round 3.) A bound that is checked after the work is a report, not a bound — and a
  bound on the largest element is not a bound on the sum.** The cost cliff above got "stated
  bounds beyond which the region is refused". They were judged after the quadratic simplicity
  test (2,700 traced points: 2.59 s to refuse where 2,600 took 1.86 s to build); then, as a
  counted work bound, applied to the largest ring of what the clipper had already inflated and
  the snapshot had already read (800 scribbled points: half a second and 53,000 rings before
  anything was asked); and the clipper itself was never priced — its last reading of a
  self-crossing outline of 800 vertices took ten seconds under a limit that counted vertices.
  Now one budget per item, every step paid before it runs, an item's stored vertex count asked
  before one vertex is read, and caches bounded by the vertices they hold (ADR-059 decision 9,
  §8.29.1, §8.11). Three things to keep: *(1) write the test that asserts what RAN before the
  refusal, not that the refusal came* — every earlier form passed "is the large thing
  refused?"; *(2) a library's cost follows its own variables* — pyclipper's are crossings and
  the edges a sweep line carries, not vertices: 4,000 teeth side by side cross nothing and
  took 1.6 s, the same teeth lying down 4 ms; *(3) price a step by what it does* — the
  simplicity test was priced at the square of its edges and cost a hundred times that for a
  ring whose every pair of edges lies close, found by measuring a refusal that took longer
  than its units allowed.
- **(Fix round 4.) A cache smaller than its working set is not a small cache — it is no
  cache, plus its bookkeeping.** Round 3 bounded what the ring memories hold (262,144 vertices,
  least recently asked dropped first) to stop an edit session from holding a gigabyte. A
  snapshot asks the plan in the same order on every tick, so in a plan larger than the cap each
  answer was the oldest when its turn came: nearly every lookup missed, and an UNCHANGED plan
  was recomputed on every tick — 160 polygons of 1,000 vertices 4.6 to 5.3 s per idle tick
  (0.2 s before the cap), 110 closed fences 14 s. Every test of the round ran far below the
  cap. Fix: a snapshot is one generation; what it asks for is live and never dropped; the cap
  bounds the stale rest (ADR-059 decision 9, §8.29.1). *Bound what is beyond the working set,
  never the working set; and test a cache at the size where it is full — shrink the cap in
  the test, count the recomputations on the second tick.*
- **(Fix round 5.) A fix made for the call a review named, not for the rule it found, leaves
  the next call standing.** Round 4 stopped asking the STRICT union for a tree. The PLAIN
  union, eight lines above it in the same function, went on being asked for one — a tree that
  was flattened on the next line — and a test pinned that as expected. One ring with 720 holes
  bridged to its wall held the GUI thread for 5.3 s inside the work budget (pyclipper alone,
  801 rings: 23 ms as a list, 7,078 ms as a tree). Fix: `_clip_tree` is split by what a
  caller may get — `_union_rings` cannot return a tree, `_band_tree` is the one call that
  does, and it is bounded for a stated reason (a band leaves nothing to join; measured the
  same as a list); the op-count test watches `pyclipper.Pyclipper` below every seam; and
  `scripts/measure_region_work.py` FAILS above 12 times the price instead of printing its
  worst row. *After a finding, write down the rule, then grep for every other place the same
  thing is done. And a table that only prints is not a gate: twice the hole was a family
  nobody had put in it.*
- **(Fix round 5.) The order of a clipper's output is not a property of the shape.** A
  record's regions came in the order pyclipper handed its rings out, and that changed when
  one call went from `Execute2` to `Execute`: the same regions, another order, another
  signature. They stand by the smallest vertex of their outer ring now, sorted before they
  are judged (regions are paid one after the other out of one budget, so the order decides
  where a budget runs out). *Whatever a library returns as a list has an order you did not
  choose; if it reaches a signature, choose one.*
- **(Fix round 4.) The same library call can cost a thousand times more for how it is asked.**
  pyclipper's union with `StrictlySimple`: 19 ms as a flat list (`Execute`), 4,382 ms as a tree
  (`Execute2`), same input — a closed zigzag of 340 vertices on two levels. The price was read
  off the rings that came back; the cost followed the splits the tree build tried. *When a
  call into a library is priced, measure that call on input built to hurt it, in each form it
  can be made; a price fitted on kind inputs is a guess.*
- **(Fix round 3.) "Unreachable" was a sample.** A fallback was reported as a path no real
  stroke takes because 0 of 4,500 random strokes took it. A fence whose two butt ends meet
  corner to corner takes it every time, and nothing tested it: replaced by "no regions", 694
  tests and 93 mutants stayed green. *A random sample says how often, never whether; for
  "can this branch run" construct the input from the branch's own condition.*
- **(Re-review.) A finite number is not a usable number.** `"object_height_cm": 1e300` in a
  hand-edited plan is positive and finite; it passed the record's check, and became infinity in
  the mesh's float32 — which a sink that does not validate hands to the engine. Fix: a domain
  bound in the record (`MAX_LENGTH_CM`, 10 km) for every length, and a mesh constructor that
  refuses what is not finite once it is float32. *Validate in the units and the precision of
  the place the number ends up, not of the place it came from.*
- **(Re-review.) A report object that holds an exception holds the world.** `SkippedItem`
  carried the exception it reported, and the caller is told to keep the list: the traceback
  keeps its frames alive, the frames hold the scene and the item. It holds two strings and a
  code now. The test that pins it had to switch pytest's own log capture off first — pytest
  keeps every log record, traceback included, which is the same leak one layer up.
- **A safeguard on the hot path costs what it costs at the size nobody tested.** Refusing a
  ring that crosses itself needs `is_simple_ring`, which compares every pair of edges. The bench
  plans' largest ring has 24 vertices (0.1 ms), so every budget stayed green — and a 500-vertex
  outline cost 72 ms per snapshot while one of its vertices was dragged (1,000 vertices:
  262 ms), because an edited ring misses the cache on every tick. Found by asking for the number
  at n = 500 before anyone drew such a polygon. From 32 vertices on the test now prunes edge
  pairs by bounding box and runs on numpy: 2.9 ms and 10.8 ms, same machine, same load
  (`tests/unit/test_scene3d_polygon.py::TestSimpleRingAtScale` pins that both versions agree).
  *A check that is linear in the plan can still be quadratic in one item: measure it on the
  largest single item a user could make, not on the largest plan.* The ear clipper the two 3D
  views share (`triangulate_polygon`) is quadratic too and was left as it is: it runs only when
  that item's geometry changed, and the Qt 3D view has paid it on every change since US-E6.
  - **One round later that sentence stopped being enough.** "Every region is buildable" is
    checked by cutting the region, so the ear clipper moved from the builder into the snapshot
    (cached; the builder reuses the cut). The total per edit tick was unchanged — and the
    snapshot of a 1,000-vertex outline with one vertex dragged went from 9 ms to 290 ms. Measured
    only because the rule above said to: the suite's budgets run on warm caches and on plans
    whose largest ring has 24 vertices. From 256 vertices on, a ring without holes is now cut by
    the array ear clipper written for regions with holes (1,000 vertices: 30 ms against 272),
    and snapshot plus build is 41 ms where the first version took 250. *Moving work to another
    function moves its cost too; re-measure the hot path at the large size after every such
    move.*
- **A styled polyline did not keep a stroke width across save and load** (observed while
  generating the edge-case plan). `core/project.py` restored `stroke_width` only when the
  polyline had no `path_fence_style` preset, so a fence with a preset came back at the preset's
  width whatever was saved; the edge-case plan therefore uses fences without a preset. *Changed
  by L1.5* (§11.4.17): the loader restores the saved stroke of a preset line too — a file saved
  by a version that did not, with a stroke that differs from the preset's, now shows the saved
  one.

### 11.4.15 What the engine taught while the production package was built (Phase 17 L1.2, #385)

The first six were found by measuring before building on them; the rest by two independent
reviews and by CI's runs of the branch — each of those is a thing a green suite did not see
(ADR-048 addendum L1.2, "Review round 1" and "Review round 2"; the round-2 entries are marked).
Machine: Windows 11, RTX 4070 and WARP, PyQt6 6.11.0, 2026-10-11; xcb + OpenGL on llvmpipe in
a container with the CI job's packages.

- **Grabbing a Qt Quick window that has no scene graph is safe exactly once — and only if the
  window is never shown.** `grabWindow()` on a window without a live scene graph renders one
  frame offscreen and tears everything down again. What that means depends on the window:
  - *Never shown.* The frame is right — pixel-identical to a grab of the same scene in a shown
    window — and it is the only one: the second such grab returned the bare clear colour, every
    Model gone, even the built-in `#Rectangle` ground (mean absolute difference 161 of 255 on a
    320 × 240 frame; Direct3D 11 on the GPU and on WARP alike). `View3D.pick()` finds nothing
    on such a window.
  - *Shown, first expose pending* — `show()`, then `grabWindow()` with no pass of the event loop
    in between. **The grab returns a correct image, and the process dies in the next passes of
    the event loop**: exit code 3 (abort), `0xC0000005` (access violation) or `0xC0000374` (heap
    corruption). 3 of 3 here; 5 of 5 on the GPU, 3 of 3 on WARP and 4 of 4 embedded in a
    splitter in the review that found it.
  - *Shown afterwards* — one hidden grab, then `show()`: the same death (3 of 3). So does an
    embedded, never-shown view that is grabbed and then shown by its parent (2 of 2, 1 of 1 on
    WARP).
  - *Not* when the window is destroyed before the event loop runs again (6 of 6 survived). That
    is why offscreen rendering with one host per frame never met the crash, and why a control
    whose host goes out of scope cannot demonstrate it.

  *Root cause (inferred from the behaviour, not read in Qt's source):* the throwaway render
  device of such a grab and the window's own first expose each set up, and tear down, the same
  scene graph. *What the first version got wrong:* `Quick3DHost.grab()` asked `isVisible()`.
  The engine's condition is `isSceneGraphInitialized()`, and between `show()` and the first
  expose the two disagree: visible, no scene graph. The error message of the hidden case even
  recommended `show()`. And a Python flag "was shown" could not have been right either: the
  parent of an embedded container shows and hides it without telling the host. *Fix:* the host
  is a state machine over what Qt reports — a host that waits for its first expose refuses to
  grab, one that took its offscreen frame refuses `show()` and `container()`, an embedded host
  has no offscreen frame, `wait_ready()` pumps to the first expose and reports. (The contract
  in full is the module docstring of `ui/view3d/quick3d/lifecycle.py`, and only there; the
  entries below say what each of its facts cost.) Pinned by one call order per child process in
  `tests/integration/test_quick3d_lifecycle.py`, with controls that must die; the rule
  itself runs in the default tier too (`tests/ui/test_quick3d_host.py::TestStateMachine`,
  `tests/unit/test_quick3d_lifecycle_states.py`).
- **(Round 2) "Never shown" means "no platform window was ever created" — on xcb anything less
  kills.** The first state machine called a window "new" when it had no scene graph and was
  not visible. `show(); hide()` with no event in between is exactly that — and the window HAS
  a platform window. The one offscreen frame taken then is correct, and on xcb the process
  segfaults in the next event-loop pass (5 of 5; the red CI job); on Direct3D 11 it survives,
  which is why the matrix had pinned that order as safe. So does a window the user closed with
  its X button: its platform window is destroyed, its scene graph kept, and a raw grab of it
  is an access violation on Direct3D 11 and a segfault on xcb. *Fix:* `NEW` is "Qt never sent
  `PlatformSurface/SurfaceCreated` for this window" — latched by an event filter, because
  `QWindow.handle()`, the same fact, is not bound by PyQt6, and `winId()` would create the
  window it asks about. *Lesson:* a crash that was measured not to happen on one backend is
  not a fact about another; the control for it must run where it was measured, and be reported
  — not assumed — elsewhere.
- **Qt's window predicates do not mean what their names suggest, and two backends disagree.**
  Measured as (visible, exposed, scene graph initialised) on Direct3D 11: a new `QQuickView`
  F F F; after `show()` T F F; after ONE `processEvents()` T T T; right after `hide()` F **T** T
  — still "exposed" until the event loop ran — then F F T; shown again T F T; minimised
  **T** F T. So "a frame can be had" needs all three, and "visible" alone is neither necessary
  nor sufficient. Under the software scene graph (`QT_QPA_PLATFORM=offscreen`)
  `isSceneGraphInitialized()` is True from the window's birth and nothing 3D is ever drawn:
  the default test tier can check the state machine's logic, never Qt's behaviour.
  `Quick3DHost.renders_3d()` is False there, and `grab` / `pick` raise instead of returning a
  frame without the garden — so does `render_records`, which makes the self-test's failure
  under that platform name the backend instead of saying "the box is not there".
- **(Round 2) Visible, exposed and scene-graph-initialised is still not "a frame can be had":
  geometry.** A `QSplitter` pane dragged shut leaves the embedded window visible, exposed,
  with a scene graph — and 0 px wide. A raw grab returns an image of the OLD size without one
  pixel of the scene; a raw pick returns a hit; `mapFrom3DScene` returns (0, 0). The first
  state machine said "live". Two more facts of the same family: after an ASYNCHRONOUS change
  of size (a splitter move, `resize()`, `showMaximized()`) the QML root item keeps the old
  size until the event loop delivered the resize event (a pane reopened from 0 is still 0
  wide in the scene, and a frame taken then is blank); and a window ONE pixel wide or high
  draws no 3D at all — the bare clear colour — while 2 px draws the scene. And a pane
  re-shown inside a splitter keeps its stale, empty geometry until the pending layout request
  is delivered. *Fix:* a live host also needs an area of at least 2 × 2 px and a root item
  that has the window's size; `wait_ready()` first delivers what is already pending, then
  waits; and `grab()` rejects an image that does not have the window's size. *Corrected in
  review round 3:* this entry said "after EVERY change of size … until one pass of the event
  loop ran". False twice — the next entry.
- **(Round 3) A resize can arrive INSIDE the call that caused it — and then the scene has
  the new size and the render target the old one.** *Symptom:* `wait_ready()` answered True
  and the very next `grab()` raised `EngineError` ("Qt rendered a 320 × 240 px image for a
  5120 × 1440 window") — after every `showFullScreen()`, 20 of 20, standalone and embedded,
  on the GPU and on WARP. `application.py` calls `showFullScreen()` on the very window the
  workspace embeds the host into. *Wrong theory (round 2's, the entry above):* "after every
  resize the root item lags by one pass, so a root item of the window's size means the host
  has caught up". *Measured, with an event filter on the view:* `showFullScreen()` delivers
  `Resize`, `Move` and `WindowStateChange` inside the call — window and root item agree at
  once — and `Expose` only in the next pass of the event loop; `grabWindow()` on a shown
  window renders into the swap chain as it is, and Qt resizes the swap chain when it handles
  that expose. `showNormal()` delivers its expose inside the call too (the grab is right at
  once); `showMaximized()` and a splitter move deliver nothing inside the call; and a main
  window that was maximised has not touched the embedded view at all until its layout ran —
  the view is, truthfully, live at its old size until then. In every case a grab has the
  wrong size exactly between a `Resize` event and the next `Expose` event of the exposed
  window. *Fix:* that is the tenth fact, latched by the event filter that already latches
  "a platform window was created": a resize event clears it, the next expose event of the
  exposed window sets it, and a live host needs it. `wait_ready()` delivers what is pending
  once for ANY visible host before it answers — also for one that reads live, whose parent's
  resize may still be in the queue. A grab whose image has another size after all is the
  same STATE, not an engine failure: `HostStateError`, counted (`stale_frames`, expected 0
  and 0 in every run so far), and the host reads "starting" until the next expose. Not
  derived from `frameSwapped`: that signal is queued from the render thread, and one emitted
  before a resize can arrive after it. *Lesson:* "one pass of the event loop" is not a unit
  of anything — which events a call delivers before it returns differs per call and per
  platform. Promise an ANSWER (`wait_ready()`), not a number of passes; and test the promise
  against orders nobody wrote down: the hand-written matrix had no full-screen row, the
  seeded random walk that joined it (250 operations) has found nothing since. Pinned by
  `test_after_wait_ready_the_frame_has_the_windows_new_size` and
  `test_a_seeded_random_order_never_yields_a_wrong_frame`. *Corrected in review round 4:
  the fix itself — a fact that an expose switches on — was the next defect, and "has found
  nothing since" lasted until the walk ran on a small screen. The entry below.*
- **(Round 4) A fact that only an OS paint message can set is a fact you may wait for for
  ever — the frame is the witness.** *Symptom:* CI red on `windows-latest` only: the seeded
  walk, 7 problems in 252 looks — three looks where Qt showed the pane and the host never
  came up, and `wait_ready()` taking its whole 5 s three times in a row on a 2 × 60 px
  pane. Green on the dev box, on the GPU and on WARP. *Wrong theory (round 3's fix, the
  entry above):* "a grab has the wrong size exactly between a `Resize` event and the next
  `Expose` — so wait for that expose". *Measured:* Windows sends NO expose to a pane that
  grows where no screen is, and none to one that is shown there. The walk asked for 1203
  and 1500 px wide windows on whatever screen it found; on the runner's 1024 px the pane
  lay beyond the edge. With the window placed like that, the dev box showed the same
  indices — while its display slept. With the display awake, the same pane beyond the same
  edge got an `UpdateRequest` (still no expose), Qt drew, and the frame was right; asleep
  again (the session idle for 25 min), stale again — and on WARP, in those same minutes,
  right. Whether a frame can be had there is not a fact of the platform: it changes with
  the adapter, and within a day on one machine. *Root cause:* the host had made a MESSAGE its evidence for something
  it can simply look at. Each round had added a fact to the state (three, then nine, then
  ten), and each new fact was a new way to be wrong about the one thing that matters: is
  the frame right? *Fix:* the frame answers that. `grab()`, `pick()`, `project()` and
  `wait_ready()` take a frame and compare its size with the window's, to the device pixel
  (*round 5:* "less than one pixel off" — not exact at 125 %; the entry below);
  another size is a refusal, never an answer, and nothing is remembered about it. The
  state is what Qt reports when asked, no more. `wait_ready()` starts no delivery of events
  once its timeout is up (a zero timeout runs none; *round 5:* "bounded by its timeout" was
  more than a nested event loop can promise — below), defaults to 1 s, and says
  False 0.5 s after the last sign of progress whatever the timeout — for every cause at
  once: no screen, no display, no painting. *Two things found on the way:* a pick right
  after a resize, with no frame in between, MISSES (the engine picks with the viewport of
  the frame it rendered last) — so `pick()` and `project()` take a frame of their own
  then; and the size check had a tolerance of two pixels, through which a 447 px frame
  passed for a 448 px window. *Lesson:* do not infer what you can observe; and a test must
  not let the window system decide where its windows are — the matrix places every window
  on the screen on purpose now, runs its walk once as on 1024 × 768, and reproduces "nothing
  draws the view" with an event filter instead of hoping for a machine in that condition.
  Pinned by `test_a_view_that_nothing_draws_is_refused_promptly_and_answers_when_painting_resumes`,
  `test_the_same_walk_where_a_small_screen_leaves_the_pane_beyond_the_edge`,
  `test_a_pane_beyond_the_screens_edge_gets_a_frame_or_a_prompt_refusal_and_answers_when_it_is_back`
  and, without a window, `tests/ui/test_quick3d_host.py::TestWaitReady`.
- **(Round 3) A contract written down in nine places is wrong in three.** The host's state
  table stood in `lifecycle.py`, `host.py`, §8.29.2, ADR-048, this section, the glossary, the
  building-block view and both copies of the `ogp-3d-renderer` skill; after round 2 three of
  them said "after every resize the host is starting for one pass", which the code did not
  do and Qt does not do. *Fix:* the module docstring of `lifecycle.py` IS the contract; every
  other text links to it, and `tests/unit/test_quick3d_packaging.py` fails a second copy of
  the state table. *Lesson:* a table a caller must obey belongs next to the function that
  implements it, once.
- **(Round 3) `QEventLoop.exec()` returns at once when the application is quitting, and a
  bounded wait built on it spins.** *Symptom:* `wait_ready()` on a host that was still
  starting while the app closed: 158,574 looks at Qt in 3.0 s. *Measured:* inside a running
  main loop after `QCoreApplication.quit()`, a local `QEventLoop.exec()` returns −1 in about
  2 µs; without a running main loop `quit()` does nothing, which is why no in-process test
  had met it. *Fix:* the pass reports whether the loop ran; `wait_ready()` answers False at
  once when it did not, and the number of passes is bounded by the timeout whatever a pass
  does. Pinned in a child process with a real main loop
  (`test_a_pass_of_the_event_loop_says_whether_it_ran`).
- **(Round 2) A judge that asks the suspect sees nothing.** The lifecycle matrix compared
  every frame with the state the host had reported for it: a host that says "live" must give
  a frame, one that says "hidden" must refuse. A host that reported the WRONG state passed —
  the blank frame of the collapsed pane was "a frame from a live host". *Fix:* the matrix
  states per order and step what a truthful host must answer, checks the pixels (the probe
  box at the predicted place, in a frame of the window's size), and only then looks at the
  state. The same family as the canary that ran the product (below).
- **With the display asleep, a visible window presents its first frame and then none.**
  *Symptom:* a shown, exposed, active `QQuickView` fired `frameSwapped` once; forty
  `view.update()` calls later the count was still 1 (threaded and basic render loop). A wait for
  two frames timed out after 20 s. *Root cause:* Qt 6.11 delivers update requests on Windows from
  a thread that waits for the display's vertical blank; a monitor in power-save has none. With
  `QT_D3D_NO_VBLANK_THREAD=1` frames flowed again, at about 4 per second (each present waited
  ~250 ms). On WARP frames flow either way. The machine also prints
  `qt.qpa.screen: "Unable to open monitor interface to \\.\DISPLAY1"` on every window.
  `grabWindow()` is unaffected: it renders and reads back synchronously in 1–9 ms. *Fix:* nothing
  in the package or its tests waits for a frame to be *presented*; `grab()` is the
  synchronisation point. (The L0 owner run's protocol note — a `wait_frames` timeout followed by
  an access violation in `grab()` — has two halves. The timeout is this entry. The access
  violation was attributed to it as well in the first version of this text, without evidence;
  a grab of a window whose scene graph was not up — the entry above — fits an access violation
  better. Neither attribution was checked against the L0 run.) The monitor warning is listed, exactly, as
  an `environment` message in `qt_messages._ENVIRONMENT`, so "a clean run records zero Qt
  warnings" stays assertable on that machine; an allow-list wider than what was measured would be
  a hole, and `tests/unit/test_quick3d_pure.py::TestClassify` pins that it is not.
- **A recorder that replaces Qt's message handler deafens the one before it.** *Symptom:* the
  positive control "a broken shader fails the render" raised `RenderError` as it should — and
  the run's own summary still counted 0 Qt errors. `render_records` installs a recorder for one
  frame; the driver had one for the whole run; `qInstallMessageHandler` keeps a single handler.
  *Fix:* `qt_messages.install` forwards every message to the handler it replaced and
  `uninstall(previous)` puts that one back. Inside the running app this is also what keeps the
  app's own logging intact during an offscreen render. Pinned by
  `tests/unit/test_quick3d_pure.py::test_nested_recorders_both_hear_an_error`.
- **(Round 2) A Python Qt message handler beside a shown Qt Quick window deadlocks the
  process.** *Symptom:* the host's "watch" for a live view's errors — a recorder installed
  with `qInstallMessageHandler` for the life of a shown host — and a `hide()` that never
  returned. 5 of 5 in the review, on the GPU and on WARP; later every run here, and on xcb.
  *Wrong theory (round 1's):* "the recorder takes a lock and never raises, so it is safe on
  Qt's render thread". *Root cause:* Qt Quick renders a shown window on a thread of its own
  (`qt.scenegraph.general` says "threaded render loop" on Direct3D 11 and on xcb + OpenGL).
  Qt's message handler is process-wide; PyQt calls a Python handler under the GIL on
  whichever thread emits the message. The GUI thread holds the GIL while it sits inside a
  Python-called Qt function; `hide()` waits there for the render thread; the render thread
  emits a message and waits for the GIL. Any render-thread message at that moment will do —
  the shader errors the watch existed to catch among them. The app installs no Python Qt
  message handler; the watch would have introduced this. *Fix:* no watch. A recorder only
  around rendering on the calling thread — the one-shot offscreen frame — where every message
  was measured to arrive on that thread (the recorder counts the others; the tier requires
  0), and never while a Qt Quick window is shown (`render_records` refuses). A shown host
  reports what Qt delivers on the GUI thread instead (`health()`, §8.29.2). *Lesson:* "thread
  safe" is not "safe to call from that thread" when the caller holds a lock you need — and
  the GIL is a lock. Pinned as a control that must hang
  (`test_a_python_message_handler_beside_a_shown_window_deadlocks`).
- **(Round 2) On Windows, `_exit` does not end a process that is deadlocked inside Qt.**
  `faulthandler.dump_traceback_later(exit=True)` wrote every thread's stack into the log — and
  the process stayed alive, every run (one for three minutes). Its C thread needs no GIL; but
  its `_exit` is `ExitProcess`, which runs every DLL's detach code, and that waited for the
  deadlocked threads. `ExitProcess` from a native timer thread hangs the same way (2 of 2). On
  Linux `_exit` ends the same deadlock at once (5 of 5). *Fix:* a second line of defence for
  the self-test, the render driver and anything else that owns its process:
  `runlog.watchdog(…, supervised=True)` starts a tiny second process that calls
  `TerminateProcess(handle, 1)` ten seconds after the deadline and writes the reason into the
  log first; in the frozen build it is the exe itself (`--selftest-supervisor`).
  *And the trap inside the fix:* the supervisor must know when the block is OVER. The block
  signals a named event and closes it; a block that finishes before the supervisor has even
  started leaves no event behind — and the first version, finding none, waited on the process
  alone and would have terminated it at the deadline: a pytest run, 310 s after the test that
  called the bounded self-test had passed. A missing event now means "released"; the
  supervisor also checks the process's creation time, so a reused pid is never touched.
  Pinned by `test_the_supervisor_leaves_a_process_alone_whose_block_finished_first`.
- **(Round 3) "A missing event means released" was right; "an event that exists is mine" was
  not.** The release event was named after the PROCESS (pid and creation time). *Symptom
  (the review's measurement):* block A — a supervised watchdog of 1 s around an empty body —
  then block B, 60 s, healthy, in the same process. A's supervising process came up after A
  was over, found B's event under the same name, waited on it, and terminated the process
  4.1 s into B, writing "block A was still alive …" into A's log. Latent: the self-test and
  the render driver arm one block per process; but `supervised=True` was advertised for
  reuse, and three texts said a supervisor could only ever act for its own block. *Fix:* a
  random nonce per block in the event's name, handed to the supervisor on its command line;
  one armed watchdog per process (a second raises `WatchdogError` — `faulthandler` has a
  single timer anyway); and a supervisor that checks who it is working for before it opens
  anything: validated arguments (a deadline of `nan` used to be a traceback, `-1` a wait of
  49 days, `0` an immediate terminate), its target must be its own PARENT process and, in the
  frozen build, run the same image, and it appends to the log it was handed and creates no
  file. *And the gate's own #291:* a supervisor that could not be started was logged as
  `supervisor=none` and the self-test passed — the day a build could not start it, nothing
  would have said so until a deadlocked self-test held a release job. On Windows the
  self-test now FAILS without a supervising process that started, was released and left.
  *Lesson:* something that may kill must name its target by what nobody else can have (a
  random name it was handed), never by what the next user will have too (the pid). Pinned by
  `test_a_finished_blocks_supervisor_cannot_end_the_block_after_it`,
  `test_the_supervisor_only_acts_for_the_process_that_started_it` and
  `test_without_its_supervisor_the_selftest_fails_on_windows`.
- **(Round 4) "It left with exit code 0" is not "it did its job".** A supervising process
  that could not find its block — a creation time that was not the process's — left 1.5 s
  into a 20 s block with exit code 0, the same code as one that was released; the block
  called itself supervised and the self-test logged `ok=True detail=started, released,
  left` for a run without a safety net. *Fix:* 0 only for a supervisor that held the
  block's release event; 4 for one that found nothing to wait for. And so that "came up
  late" is not mistaken for "lost": the block signals its event and KEEPS it until the
  supervisor has left (at most 15 s — the only start bound there is), so a late one finds
  it, signalled, and leaves as released. Also: everything that arms a watchdog is inside
  its `try` — a failure while arming had left the process "armed" (every later watchdog
  refused) with a live supervisor that would have ended it at the deadline. Pinned by
  `test_a_supervisor_that_never_supervised_says_so_in_its_exit_code` and
  `test_a_watchdog_that_cannot_be_armed_leaves_nothing_armed_and_no_supervisor`.
  *Round 5, the same lesson twice more:* a supervisor whose own wait FAILED also said 0 —
  the code read "not a timeout" as "released" — and `Armed.supervised` was True beside a
  gap that said the supervisor had not left. Only the two answers that mean "the process
  ended" and "released" are 0 now, and the two properties are one statement. Pinned by
  `test_a_supervisor_whose_wait_fails_says_so_and_terminates_nothing` and
  `test_what_a_block_says_about_its_supervisor`.
- **(Round 5) A judge that repeats the suspect's rule is blind exactly where the suspect is
  wrong — and "exact" needs a definition.** *Symptom:* none in any tier, on three platforms,
  on CI. Found by a reviewer who set `QT_SCALE_FACTOR=1.25`: a pane made one logical pixel
  wider, 442 → 443, with the render target behind, and `grab()` handed out the old frame —
  553 px — for the new pane, whose own frame is 554 px; `pick()` answered with the old
  viewport. *Wrong theory (round 4's own words):* "the size check is exact to the device
  pixel". It was "less than one pixel off `logical × ratio`", which IS exact when the ratio
  is 1, 1.5 or 2 — the three the tests had. *Measured:* Qt sizes a render target as
  `QSize(logical) * ratio`, `qRound` per side, so the right frame is at most HALF a pixel
  off; at 1.25 a 442 px pane has 552.5 → 553 px, and 553 is 0.75 off 553.75. 750 of 11,993
  neighbour frames passed at 1.25; every ratio strictly between 1 and 1.5 had some. *Why no
  test saw it:* the matrix's judge decided "a frame of the window's size" with the same
  inequality as the host. Round 1's judge had asked the host for its STATE and was blind to
  a wrong state; this one asked nothing — and had copied the rule. *Fix:* the host: at most
  half a device pixel off. The judge: what Qt makes for the window, computed by itself
  (`qt_round`), and equal to it. The arithmetic for every width from 2 to 3000 at twelve
  ratios, against `QSize * ratio` asked of Qt, in the default tier; one real-window row at
  125 % whose raw grab first proves that the render target is behind. *Lesson:* an oracle
  must be derived independently of what it judges — from the platform's definition, not from
  the implementation's tolerance; and when a claim says "exact", write down the rounding it
  is exact against, then test where rounding bites (between the round ratios), not where it
  cannot. Pinned by `test_the_size_check_is_qts_own_rounding_at_every_ratio`,
  `test_at_125_percent_a_pane_one_pixel_wider_does_not_get_its_old_frame` and
  `test_the_judge_knows_a_wrong_frame_when_it_sees_one`.
- **(Round 5) Three statements about time, each one measurement short.** (1) *"`wait_ready(t)`
  returns within `t`, plus the one handler that is running."* One pass of Qt's event loop
  delivers the whole queue: 0.2 s asked, 1.80 s taken behind six handlers of 0.3 s. Not
  fixable from the thread those handlers run on — so the contract states that bound, and
  states what the call is: a nested event loop that takes user input, which the workspace
  needs nowhere on the GUI thread. (2) *"False `STALL_S` after the last sign of progress"*
  counted WALL time: a GUI thread busy for 0.7 s in another handler looked like 0.7 s of
  silence, and the repaint queued right behind it was never looked at — False after 0.75 s,
  True when asked again. Silence is counted pass by pass now; a pass that overran its step
  was busy. (3) *"`pick()` and `project()` take a frame once per resize."* Once per CALL
  while the render target was behind: 200 `project()` of one tick, 200 frames, all refused.
  One per refusal now — renewed by a sign of progress, by other facts, or after 0.25 s — and
  the caller's rule is written down: a tick stops at its first `HostStateError`. *Lesson:*
  a bound that names "the one thing" was measured with one thing in the queue; measure the
  claim under load (N queued handlers, N calls in a row, a busy thread) before writing it
  into a contract. Pinned by `test_while_the_render_target_is_behind_a_tick_costs_one_frame`,
  `test_a_busy_pass_of_the_event_loop_is_not_silence`,
  `test_idle_passes_add_up_to_silence_whatever_a_busy_one_took` and
  `test_the_bounds_of_wait_ready_are_stated_once`.
- **(Round 2) Without a slot on `sceneGraphError`, a graphics device that cannot be created
  takes the whole app down.** Forced with `QT_D3D_ADAPTER_INDEX=9`. With a slot connected, Qt
  emits `(ContextNotAvailable, "Failed to initialize graphics backend for D3D11.")` and goes
  on: the window is visible and exposed and never gets a scene graph. With nothing connected,
  Qt opens a native modal dialog with that text, the process sits in it, and after OK it
  aborts (`0xC0000409`). Qt decides by asking whether the signal is connected. *Fix:* the host
  connects it (queued), `health().scene_graph_error` carries the text, and `wait_ready()`
  stops waiting. An 8-second "the process is still running" smoke test passes a process that
  sits in such a dialog — the self-test, not the smoke, is the gate (§7.4).
- **(Round 2) A QML function that throws returns `None` to Python, silently.**
  `QMetaObject.invokeMethod` on a MISSING function raises `RuntimeError`; on one that throws it
  returns `None` and the QML engine emits a warning. The host called `destroyPart` and took
  the return for success: with a failing `destroyPart` every `reset()` forgot one more Model,
  and the fourth "succeeded" with three Models still in the engine and
  `sink.state() == sync.expected_state()` true. *Fix:* a Model leaves the host's books only
  when the engine confirms it (deleted, or `retired`); `pick`, `project` and `engine_parts`
  turn a `None` into an `EngineError`; the QML warning reaches `health()`.
- **(Round 2) On Windows `QStandardPaths` follows `USERPROFILE`, not `APPDATA`.** The shell
  expands its known folders from the process's `USERPROFILE`; the `APPDATA` variable is not
  consulted. A test that set `APPDATA` to a temp directory and then let the app resolve its
  log directory wrote into the developer's real roaming profile — under a throwaway
  organisation name, which is how the empty directory it left behind was found. Qt Quick's
  shader cache and the graphics driver's caches hang on the same profile. *Fix:* the children
  of the engine tests get a profile of the test process's own (§8.10.8), and the one test
  that resolves the log directory first ASKS Qt where it would be — which creates nothing —
  and stops unless the answer is inside that profile.
- **`exposure` is not a property of `SceneEnvironment`.** Only `ExtendedSceneEnvironment`
  (`QtQuick3D.Helpers`) has it; on the plain type it is a QML load error ("Cannot assign to
  non-existent property"), reported with file and line by `Quick3DHost` — the loud path worked
  before the scene did. `Garden.qml` uses the extended environment for that one property, with
  every effect it offers switched off.
- **`TonemapModeNone` leaves LINEAR radiance in the frame — which makes a pixel computable.**
  In the top-down view a lit horizontal face reads
  `255 × tint_linear × (brightness × sin(elevation) × sun_linear + fill_linear)`: predicted 167.2,
  measured 171 (the difference is the material's small specular term). The frame looks dark to a
  human; it is a measurement view, and the render tier's truth checks rest on it
  (`test_a_lit_top_face_has_the_radiance_the_sun_predicts`). Related: a light with
  `brightness: 0` still contributes its `ambientColor`, which is how the fill stays on when the
  sun is switched off; and `PrincipledMaterial.baseColor` is linearised by the engine with an
  approximation of the sRGB curve — a tint through it and the same tint through a custom
  shader's exact uniform read 171 and 169.
- **A log with a fixed name in the temp directory is a hole on Linux (CWE-377).** The self-test
  first wrote `tempfile.gettempdir()/OpenGardenPlanner-selftest-3d.log`. `/tmp` is shared between
  users; a predictable name there can be pre-created or symlinked. Found in review, before any
  release. *Fix:* the log goes into the app's one per-user log directory
  (`core.logging_config.resolve_log_dir`), and `main._run_selftest` names the application first,
  because that directory hangs on Qt's application identity. Rule and tests: §8.11.
- **A guard that runs the thing it guards skips the defect it stands in front of.** The
  default-tier host tests began with a canary in a child process, so that a platform unable to
  create Qt Quick 3D objects would skip the file instead of crashing the run. The canary built
  a `Quick3DHost` — product code. A `Garden.qml` that did not load therefore failed the CANARY:
  32 skipped, 0 failed, a broken engine package, green. *Fix:* the canary is bare Qt with inline
  QML and may only say "this platform cannot"; the positive control runs the file against a
  broken scene and demands failures and no skip (now 9 failed, 43 errors, 0 skipped). The same
  family, found in the same round: a positive control whose host went out of scope before the
  event loop ran could not die; a timing budget that counted an UNKNOWN graphics adapter as a
  software rasteriser would have skipped itself green; Qt debug lines were run through the
  error patterns, so the wording of a debug message could have failed a release.
- **PyQt's enum member names are not a naming scheme.** `QSGRendererInterface.GraphicsApi` in
  PyQt6 6.11 has the members `OpenGL`, `Direct3D11Rhi`, `VulkanRhi`, `MetalRhi`, `NullRhi`,
  `Direct3D12` (plus `Unknown`, `Software`, `OpenVG`). A list of expected strings typed on
  Windows — `Direct3D11Rhi`, `OpenGLRhi`, … — failed the first Linux run, which reported
  `OpenGL`. *Fix:* the name comes from a table keyed by the enum MEMBER
  (`host.GRAPHICS_API_NAMES`: `Direct3D11`, `OpenGL`, …), and a test pins that every member
  has a name.
- **Three one-per-process facts behind a self-test that cannot hang.** `faulthandler` has ONE
  `dump_traceback_later` timer: a watchdog inside a watchdog replaces the outer one and cancels
  it on the way out — so when the whole `--selftest` is bounded, its 3D block arms none.
  `faulthandler` writes to a file DESCRIPTOR: a captured or replaced `sys.stderr` raises
  `io.UnsupportedOperation` (found by the test, under pytest's capture), and a windowed exe has
  no stderr at all — the watchdog then dumps into the null device and still ends the process.
  And under GitHub's `pwsh` (`$ErrorActionPreference = 'stop'`) `Write-Error` ends the step at
  once: a verdict printed with it is the last thing the step prints, so a log printed after it
  never appears — the gate steps print `::error::` with `Write-Host`. *(Round 2)* And a step
  that is cut off by its time limit prints nothing after the cut: the log is printed by a
  step of its own that always runs, not by the step that may hang.
- **A shader may not move a vertex at rest.** The wind shaders ported from the spike displaced
  a vertex by `sin(phase) × strength × weight` at time 0 — up to the full amplitude, with the
  clock standing still. Heights, spreads, picks and shadows are all measured on the mesh. By the
  shaders' arithmetic a leaf tip could sit up to 0.9 cm and a grass tip up to 2.5 cm away with
  the look's wind — invisible to every test — and measured in a wind 40 times stronger, boxes
  with full wind weight sat 20 cm and 38 cm off, with no message of any kind. *Fix:*
  both shaders multiply the sway by `smoothstep(0, 2, time)` — exactly 0 at rest. Pinned in
  pixels with vertices of full wind weight
  (`test_at_rest_a_vertex_with_full_wind_weight_is_where_its_mesh_puts_it`) and by a control
  with the factor removed.

Two measurements that are not traps but will be asked for: `Model.eulerRotation.y =
+rotation_deg` IS the counter-clockwise turn seen from above (mask IoU 0.9994 against the CPU
prediction at 17°, 0.288 against the opposite sense) — the proof L1.1 left open; and the engine's
shadow of a 100 × 100 × 200 cm box overlaps the analytic 2D shadow with IoU 0.976–0.978 at 35°
elevation and 480 × 360 (three azimuths, GPU and WARP within 0.0002), its direction within 0.02°.

### 11.4.16 What the 3D workspace taught (Phase 17 L1.3, #385)

Symptom → root cause → fix, for the things that cost time while the workspace (ADR-060, §8.29.3)
was built. The engine's own traps are §11.4.15; these are about wiring an engine into an app and
about measuring it.

1. **A Python callable on a QObject's `destroyed` signal crashes a test that has nothing to do
   with it.** *Symptom:* after "disconnect a clock subscriber when its QObject is destroyed" was
   built as `receiver.destroyed.connect(<closure>)`, the suite died with an access violation in
   `test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`. *Root cause* (bare PyQt 6.11,
   four ways to let such an object go): freed by refcount — the hook runs once; the wrapper in a
   reference cycle and collected — the hook runs **0 times**, silently; the same with Qt owning
   the object and a `deleteLater()` pending — **access violation** inside the hook when the
   deferred delete runs. The callable lives and dies with Python's idea of the wrapper, not
   with the C++ object; the collector clears it and the connection stays behind. *Fix:* nothing
   hangs on `destroyed`. The clock's channel calls a guard that asks `sip.isdeleted()` at every
   delivery (`ui/sim_clock_subscription.py`, ADR-053 addendum). *(Fix round 1: master's sun
   coordinator, v1.30.1, had the same shape — a closure on its own `destroyed` holding a bound
   method of itself. In bare PyQt that closure runs 0 times in the deferred order, 5 of 5:
   its clean-up silently does not happen. It listens through the helper now, and a scan
   refuses a new `….destroyed.connect(…)` anywhere in the product; the one older site, the
   global search field, is listed there by name.)* **Do not hang clean-up on a
   QObject's `destroyed` signal from Python: the callable can be collected before the signal
   fires. Ask at the moment of use.**
2. **Qt keeps graphics state for every Model it ever drew.** *Symptom:* the memory soak read
   34.6 MB per reload against a bound of 10, with nothing growing in Python (`tracemalloc`: 0.045
   MB per reload) and nothing in VRAM (DXGI: flat). *Root cause:* two retentions inside Qt Quick
   3D — per-draw-call state kept for every destroyed Model until
   `QQuickWindow.releaseResources()` (about 0.2 MB each with shadow passes, independent of the
   mesh: 19 MB per rebuild of the small bench plan, 65 of the large), and what a frame holds
   for destroyed Models, which comes back only at the end of a PRESENTED frame (item 3). *Fix:*
   the workspace counts retired Models and releases (ADR-060 decision 15): 2 MB per rebuild
   instead of 19. *How it was found:* a bare host, 100 Models per round, ONE thing changed per
   run — buffers only, geometries only, Models never drawn, drawn by readback, drawn in
   presented frames, sun on, shadows off, embedded, another material, 300 or 12,000 vertices
   (ADR-048 addendum "L1.3" has the table). The vertex-count runs said "not the mesh"; the sun
   run said "per pass". What the release does NOT give back: 15 to 20 kB per destroyed Model
   (2 MB per rebuild of the small plan, linear over 60 rebuilds) — which is not graphics
   state at all (a view that draws nothing leaves 1.5 MB per rebuild), and bare Qt alone
   keeps 3.4 kB per `Model` with a material that is created with `createObject()` and
   destroyed, never drawn, the engine's collector called. Churn of QML objects is not free;
   a feature that replaces many Models per tick has to avoid the replacing.
3. **A soak that reads back every cycle measures the readback — a lesson that was filed
   wrongly twice before it was filed right.** `grabWindow()` renders a frame of its own and
   reads it back; that frame is never presented (`afterFrameEnd` fired 0 times in 40 grabs),
   and what it holds comes back only when a PRESENTED frame ends. With the display asleep
   Windows presents no frame at all (update requests come from a vblank thread), so on this
   machine at night every frame of every soak was a readback and everything stayed.
   *First filing:* "a property of my instrument" — the soak's child was made to present by
   timer (`QT_D3D_NO_VBLANK_THREAD=1`) and went on reading back once per rebuild. *Second
   filing,* after the ground story read +16 MB per re-bake in a view that did not present:
   "a view that presents nothing keeps every byte uploaded to it" — and a rule was built on
   that sentence (the pipeline paced by presented frames, one generation for a dark view).
   The independent review of the ground story then took the readback out of its loop and
   read +0.0 MB per cycle. The same here, with the pacing gone: twenty rebuilds with the
   view's frames withheld cost 1.5 MB each without a readback and 8.5 with one readback per
   rebuild (26 without the cache release) — and dedicated GPU memory does not move at all
   without the readback, because nothing is drawn. The growth was per frame RENDERED BY A
   READBACK AND NEVER PRESENTED; never per upload, never per edit. The pacing was taken out
   again: it fixed nothing and added a way to get stuck. *Fix:* nothing in the product takes
   a frame from the live view (ADR-060 decision 17), and the soak takes none inside its
   measured loop — one before, one after. **Before a memory curve is read, and before a
   rule is built on it: list every frame the measuring loop itself renders, and run the
   loop once without them.**
4. **`processEvents()` after an edit measures the 2D side.** The first edit-to-frame number
   (p95 56.6 ms) was taken as "edit, `processEvents()`, readback": it contained the rest of the
   event-loop turn — the canvas repainting itself, the minimap, the panels. *Fix:* the readback
   is taken inside a slot on the pipeline's `applied` signal, the moment the pass committed
   (p95 17.6 to 20.6 ms at 1600 × 900; 29.2 ms on the maximised 5120 × 1369 window).
   Also there: a scripted `redo` with nothing to redo "measured" about 200 ms — the time-out of
   waiting for a pass that never came. A measuring script counts the edits that reached the
   engine and reports misses.
5. **A zero timer is not "next turn".** A pass scheduled with `QTimer.singleShot(0)` waited
   behind every timer that was due — on the large bench plan 5 % of the passes started more
   than 228 ms late, behind the 2D side's debounced work. A posted event is delivered first.
   And at HIGH priority it is delivered too early: before the scene's own queued `changed` for
   the same edit, which then starts a second pass (four tests met two snapshots per edit).
   Normal priority, and the two signals share one pass.
6. **The pan comparison was wrong three times.** (a) Two long blocks one after the other —
   Split, then Plan — measured the machine's drift: 1.10 to 1.28 for the same build while other
   suites ran. (b) Short alternating blocks that walked on from where the last one stopped
   compared lawn with dense beds: per-round ratios between 0.16 and 7.2. (c) A walk that reaches
   the end of the scroll range "pans" for 0.001 ms a step. *Now:* six alternating rounds, every
   block from the same position along the same pixels, every step asserted to have scrolled:
   0.83, 1.04 and 1.09 in three runs on the same busy machine (the fastest tenth: 1.05).
7. **An editing tool wrote three `\u` escapes as the characters themselves.** The module that
   DEFINES the line separators (U+2028, U+2029) then contained two of them, invisibly, and so
   did two tests. *Fix:* named escapes (`\N{LINE SEPARATOR}`), and a test that scans `src/` and
   `tests/` for characters a reader cannot see
   (`tests/unit/test_plain_text.py`; its own control caught that the first version missed
   U+FFFD).
8. **Importing the gate's hook into the test process moved the test process off its own
   settings key.** The hook's job is to rebind the settings names of the process that imports
   it — a child. A test that imported it to read a constant rebound pytest's own; conftest's
   per-test check caught it. *Fix:* tests READ the file; a test pins the two modules that may
   import it.
9. **Two delegating import finders asked each other for ever.** The gate's finder and the test
   children's own settings finder both "ask the other finders and wrap the loader they name".
   Each found the other. *Fix:* a re-entrancy guard per module name.
10. **A value read back from a child's store after the child left was empty** — the child's exit
    hook empties its throw-away key. What a run wrote (Recent Files, the saved geometry) is
    recorded INSIDE the child at its last step.
11. **`QSG_RHI_PREFER_SOFTWARE_RENDERER` is read once per process.** Set before the first Qt
    Quick window it selects WARP; set after, it does nothing — and the workspace learns that it
    needs software rendering long after start-up. *Fix:*
    `QQuickGraphicsConfiguration.setPreferSoftwareDevice(True)` on the window, which works at
    any time (the adapter read from Qt's own log: "Microsoft Basic Render Driver").
12. **A test that waits for a memory to shrink must use shapes that differ.** The record
    layer remembers outlines by shape: three identical hedges are one entry, and "fewer entries
    after the plan changed" compared 4 with 4.
13. **Two tests were green in every run of the story's own files and red in the whole suite.**
    *(a)* "The Split position is kept for the next session" restored the saved state into a
    bare `QSplitter` that was never shown and compared its sizes with the workspace's: equal —
    until an earlier test (a theme test) had left an application style sheet behind. A widget
    that was never shown is not polished, so its handle kept the platform's 4 px while the
    shown one's had the theme's 1 px: `[797, 399] != [799, 400]`. *Fix:* the test restores
    into a second real workspace in a second window, the product's own path. *(b)* "The
    subscription books do not grow" asserted that the process-wide table of clock subscribers
    was EMPTY at its end; in the suite two receivers of earlier tests were still alive.
    *Fix:* the test holds what was there before it and compares against that. **A test owns
    no process-wide state: compare with what was there before, never with zero. Compare a
    widget only with one in the same state (shown, polished). And run the whole suite in its
    own order before a story's files are believed — the order is part of the test.**
14. **A "before the document changes" hook ran before the change could fail.** This story fixed
    #428 with a hook of the main window in front of each document path: clear the
    hours-of-sun map, uncheck its button. In `_load_project_file` that is in front of
    `ProjectManager.load()`, whose first phase validates the file and can raise — so opening a
    damaged file, a recent file that had moved, or an agent's `open_plan` on a bad file left
    the plan open and threw its map away (found by the independent review; master, fixing #428
    at the same time through `CanvasScene.document_replaced`, pins the opposite). *Fix:* the
    hooks are gone; the scene's signal — emitted in the COMMITTING phase — is the one
    mechanism, for the map and for the 3D workspace. **Tie clean-up to the event that says
    the thing happened, not to the call that is about to try. And when two changes fix one
    issue, one of them goes.**
15. **An estimate "at ground level under the plant" is inside whatever the plant stands in.**
    Merged from master: the per-plant hours of sun sample the ground cell under the plant's
    centre and leave out the plant's own solid. A raised bed is a solid too. *Measured on
    v1.30.1:* a tomato in a 40 cm raised bed in the open, Berlin, 21 June: 0.0 hours and a
    "too little sun" warning — on every plant of every raised bed. The reference plan of
    that feature has a tree and two tomatoes on open ground; no bed. *Fix:* the receiver
    names the soil parent it stands in (the membership half of the base rule the casters and
    the 3D records already used) and that parent is spared like the plant's own solid: 16.5
    hours. **When a sample point is "under" an object, ask what else is under the object.
    And the first plan a sun feature must be tried on is the one the feature is for: a
    vegetable garden is raised beds.**
16. **A repaint is not an edit.** *Symptom* (the independent review, counting in the real
    window with a recording sink): with the sun simulation on, 10 time changes cost 10
    whole-plan snapshots; 20 mouse moves of the polygon tool's preview, nothing created, 20;
    three selections and a clear, 4; "Animate" is a timer — a snapshot per tick. A preview
    mouse-move turn cost 6.7 ms in Split against 1.0 in Plan (small bench plan), 18.3 against
    0.7 (large). The gates had passed: they changed the time with the sun simulation OFF, and
    the only toolbar that holds the time slider is shown while it is ON. *Root cause:*
    `QGraphicsScene.changed` — a REPAINT — was wired straight to "the plan is dirty". *Fix:*
    the scene's plan revision for what is announced, one quiet-time pass for what is not
    (ADR-060 decision 5); a preview move now costs the same in both modes (median ratio 0.94 and 0.98 on a quiet machine).
    **A signal named "changed" says what it changes: here the pixels, not the plan. And a gate
    that a toolbar's visibility can switch off has to be run with the toolbar shown.**
17. **Qt says "shown" one turn after an item was added — to an item that was visible all
    along.** The scene polishes a new item in the next turn and sends
    `ItemVisibleChange` / `ItemVisibleHasChanged(true)` (`_q_polishItems`); announced as a
    change of the plan, every added item cost a second whole-plan pass. *Fix:* the item hook
    remembers at the PRE-change notice what the item was, and a "change" to what it already
    was is not announced (`garden_item.announce_plan_change`).
18. **A test helper waited a fixed time for a pass the product holds.** *Symptom:* on the Linux
    CI runner `test_a_plan_with_a_refused_item_shows_the_indicator_and_fixing_it_clears_it`
    read `problems_text() == ''` 120 ms after the switch to Split; the log line of the pass
    that refuses the item was in the test's TEARDOWN. Green on the dev box in every run.
    *Root cause:* the first pass of a document is held until its notice was painted — or for
    250 ms when it is not — and runs 25 ms later (decision 7): about 55 ms with the paint,
    300 ms without. The product is not late: the indicator is set by the very pass that
    finds the problem, in the same call. The tests were early — and not one test: the shared
    helpers (`Bench.settle()`, 57 uses, and `_calls()`) waited a fixed 80 ms; with the
    notice's paint withheld on purpose, 23 tests of two files failed. *Fix:* one condition
    (`pipeline_settled`) waited for, not a time (§8.10.9). **A fixed wait in a test is a
    guess about the slowest machine the test will ever run on. Wait for the condition the
    product itself waits for — and to prove the test, run it with the slow path forced.**
19. **A count of a shared list measured every other test.** *Symptom:* under xdist (and in
    CI's coverage job) `test_a_destroyed_coordinator_is_never_called_and_takes_its_theme_listener_along`
    failed with `assert 1 == 3 - 1`. *Root cause:* `ui/theme._theme_listeners` is the
    process's; the dead coordinators of earlier tests in the same worker had their listeners
    on it, and the first theme change takes every dead one off. *Fix:* the coordinator keeps
    its listener by name (`theme_listener`); the test asks whether THAT entry is on the list.
    Item 13's rule, again, in a new place: **assert about your own object.**
20. **A sentence on a button is cut where a label would wrap.** The strip's notices were moved
    to rows of their own with word-wrapping labels, and it was believed fixed; a test at the
    review's size (1366 px window, a 455 px pane) with every notice at once found two that
    were still sentences on buttons — "2 objects are not shown in 3D", and "Try Hardware Next
    Time", whose German text alone is 456 px wide: squeezed to 220 px, cut, no ellipsis. A
    button with a long text and a fixed policy does the opposite: it makes the pane as wide
    as the sentence. *Fix:* sentences are labels; buttons hold a short command, never
    narrower than their text, on a row of their own after a sentence; a click's outcome is
    said in a label, never written onto the button. **Pin a layout at the size where it
    broke, with everything on screen at once, in every shipped language.**
21. **The un-paced close gates prove less than they look.** Every render gate runs with
    `QT_D3D_NO_VBLANK_THREAD=1`, so that no scenario depends on whether the dev box's display
    is awake. The three close gates were added once more as the product starts — paced by the
    display — and pass; but on a SLEEPING display such a view presents its first frame and no
    more, so "close with 3D visible" there closes a view that presented once, not one that
    presents frame after frame. That case stays on the owner's checklist (display on).
22. **`QGraphicsScene.changed` comes twice for one `item.update()` — the second time empty.**
    *Symptom:* a hand mutant of the net ("an explained repaint arms the net too") survived
    every test; the test written to kill it found the PRODUCT doing what the mutant did: a
    write that nudged first and repainted after was in 3D at once — and 400 ms later a second
    whole-plan snapshot ran and found nothing. *Root cause*, from a probe of the signal order:
    the announced pass ran, then `changed([rect])` (explained: the revision had moved), then
    `changed([])` — which compared the revision with the one the first `changed` had just
    recorded, and so looked unexplained. With a listener on `changed` Qt emits an item's
    update at once from `_q_processDirtyItems`; the queued `_q_emitUpdated` that update had
    asked for arrives afterwards and emits what is left: nothing. *Fix:* an empty `changed`
    reports no repaint and is ignored. **A signal can carry "nothing happened" — read its
    argument before treating the emission as an event. And a surviving mutant is a question
    about the product as much as about the tests.**

### 11.4.17 What the ground bake taught (Phase 17 L1.5, #385)

Each of these was measured while the bake (§8.29.5) was built or reviewed. The first section is
about the 2D APP: defects of the shipped canvas and project file that painting the same items a
second way brought to light. Three of them `master` fixed on its own while L1 was in work — the
loader's attributes (#438 / #469) by #502's `restore_stored_look`, the offset copy's look (#470)
by #501's `copy_visual_style` — and since the sync of 2026-10-19 the L1 branch uses master's
mechanism there (its own loader writes and its own copy helper are gone). The others were fixed on
the L1 branch, pinned in the 2D suites — each by a test that fails with master v1.30.13's code at
that place — and reached `master` with L1 in v1.30.14 (PR #484); v1.30.13 still has them.

#### 2D defects the bake found

**An item states its look twice, and nothing kept the two in step.** `fill_color`,
`fill_pattern`, `stroke_color`, `stroke_width`, `stroke_style` (`GardenItemMixin`) are what the
project file, the clipboard, the properties panel, the Agent API and (until #503 removed it) the
paint below 40 % zoom read; the live `brush()` and `pen()` are what the canvas paints. Every writer that set one half
was a defect nobody saw on the canvas:

| writer | what it left behind | what the user lost |
|--------|---------------------|--------------------|
| the project loader, rectangles (`core/project.py`) | the brush set, `fill_color` at the type's default | **a recoloured rectangle was written back in its type's default colour by the next save** — measured on `master`, load → save → load of `#ffc81e1e`: `#ff90ee90` (GENERIC_RECTANGLE), `#ff64b43c` (LAWN), `#ffdeb887` (TERRACE_PATIO), `#ff8b5a2b` (GARDEN_BED); the same wrong colour in the clipboard, in the Agent API's read and on the canvas below 40 % zoom. **Fixed on `master` by #502** (`restore_stored_look`); the L1 branch takes that fix |
| the project loader, rectangle / circle / ellipse / polygon | the pen set (colour, width and dash style all survive load → save → load), `stroke_color` / `stroke_width` at the type's defaults (`stroke_style` was set) — measured for `#dc1e50c8`, 7.5: the attributes read `#ff228b22` 2.5 (GARDEN_BED), `#ffdb7093` 2.0 (GENERIC_CIRCLE), `#ffc88c00` 2.0 (GENERIC_ELLIPSE), `#ff3c821e` 2.0 (LAWN) | the properties panel showed the type's default stroke colour and width of a loaded item; a command that takes its "old value" from the attribute puts the default back. **Fixed on `master` by #502**; the L1 branch takes that fix |
| the project saver, polylines | no `stroke_style` written | **a dashed line came back solid** (`DashDotLine` → `SolidLine`; its colour and width survive) |
| the project loader, polylines with a style preset | the saved stroke read for style NONE only | **a restyled path's own colour and width came back as the preset's** — a gravel path saved with `#dc1e50c8`, 7.5 loads as `#ffb4aa96`, 8.0, and the next save writes that |
| the offset tool (polygons, polylines), the chamfer and fillet tools, `PolylineItem.clone_with_points`, the trim tool's results | brush and pen copied, the attributes at the type's defaults | **the copy changed colour and pattern on save** (an offset copy of a blue brick terrace: default wood); in 3D it was baked as the default at once. The offset tool (and mirror) **fixed on `master` by #501** (#470, `copy_visual_style`, which also gave an offset rectangle, circle or ellipse its source's look); chamfer, fillet, `clone_with_points` and trim fixed on the L1 branch through the same module (#441) |
| `PolylineItem.__init__` / `_setup_styling` (found by review 2) | the pen built, the stroke attributes `None` until the line had been through a project file | **undo raised on a freshly drawn line** — in the shipped app: a stroke-width edit undone `TypeError: setWidthF(NoneType)` (the pen stays at the new width), a dash edit undone `AttributeError` (the pen stays dashed), a type change in the properties panel undone `TypeError` (the type goes back, the pen stays the new type's). The same line behaved after a reopen. Still in master v1.30.13: #523 |
| the properties panel's `_apply_item_state` (the undo and redo of a type change) | the attributes set, overwritten by `apply_style_preset`, then the pen built from the state | a re-stroked preset line after the undo of a type change: pen 12.0, stated 8.0 |
| `GardenItemMixin._dispatch_change_type` on a line (the context menu) | the attributes set from the state, the pen built from the TYPE | **undoing a context-menu type change reset a re-stroked line's pen to its type's** — a fence of 7.5 dashed came back 3.0 solid, stating 7.5 dashed |
| the project loader, all four filled shapes, for a file with a fill colour and NO fill pattern | the brush the constructor made recoloured — which does nothing to a texture — and the attribute set | **the picture changed across a save**: first the type's texture at the type's tint, after save and reopen at the saved colour (the middle of a lawn: (79, 144, 54) → (111, 97, 44)). On `master` for circles, ellipses and polygons; for rectangles since round 1 of this story |

*Fix:* one module, `core/item_look.py` — `master`'s since #501, with this branch's helpers added
in the sync of 2026-10-19 (the branch's own `core/item_style.py` is gone): `copy_visual_style`
(`master`'s) carries a look from item to item, `restore_stored_look` (`master`'s) writes a loaded
item's attributes, `adopt_pen(item, pen)` sets a pen together with the attributes that describe
it, `fill_brush` builds a fill in the item's own pattern, `style_gaps(item)` says where an item's
two statements part; every writer above goes through them — a line states the pen it is built
with, and `_setup_styling` builds a line's pen from the stroke it STATES, as the filled shapes
always did — and the saver writes a polyline's dash style when its pen has one. Merged, two
things met: `master`'s `copy_visual_style` copies the source's ATTRIBUTES as they are where this
branch's had read the stroke off the pen, so a source a test built out of step now hands its gap
on (one older test, `test_fillet_chamfer.py::test_fillet_arc_inherits_host_pen`, gave its host a
bare `setPen` — it uses `adopt_pen` now); and `restore_stored_look` raised on a saved stroke of no
kind (`null`, a list) before the branch's validated preset stroke ran, so a preset line with
`"stroke_width": null` was SKIPPED on the integration branch (and is on master v1.30.13: #527)
— it now leaves such an attribute alone (pinned: `TestAFileTheAppDidNotWrite`, whose `null`
cases fail with master's version).

*Guard for the class, not the instances — and the first guard was not one.* Round 1 guarded the
class by reading the source: an AST scan for functions that build an item from an item (a
"census"). A review planted six forgetful operations and the scan saw ONE: it knew the keyword
spelling `object_type=item.object_type` and two folders, and missed the type through a local, a
constant type, a `type(item)(…)` factory and a brush held in a variable. Its docstring said a new
tool "cannot ship without" the rule. The guard is now BEHAVIOUR: a teardown fixture
(`tests/integration/conftest.py::_every_item_says_what_it_paints`) tracks every `CanvasScene` an
integration test builds and fails the test if an item in one of them has `style_gaps(item) !=
[]`. Run over the folder for the first time — the four product writers of the table's last rows
already fixed — it failed 167 tests, every one for a hand-made `setPen` or `setBrush`: 31 call
sites in six test files and in the generator of the edge-case plan that built items no user can
make (a line that states its stroke is put out of step by a bare `setPen`). They go through the
helper now. Its first PRODUCT finding came with the first test that drove a type change on a
line: the line then states its new type's fill — a transparent grey — beside the transparent
black brush every line paints with. Both paint nothing, and the predicate now says so. With any
one of the four product fixes taken out again, the fixture fails the tests that drive that
writer (the round's mutants). `tests/integration/test_item_style_in_step.py`
keeps the operations by name (clipboard / duplicate / the four arrays, mirror, offset, chamfer /
fillet, trim, `clone_with_points`; the fresh line and its undos; hand-made files) and tests the
guard's teeth with the six planted operations; the scan is kept as a map of the derivation sites.
`tests/integration/test_item_roundtrip_matrix.py` pins load → save → load of a recoloured,
patterned rectangle for eleven object types and of a re-stroked item of every shape.

*One kind of item is exempt:* an item whose picture is a sprite (`GardenItemMixin.paints_sprite`
— a furniture rectangle, a plant or furniture circle). It draws its sprite and asks neither brush
nor pen for the picture; its pen is `NoPen` when it is built and a solid black 1.0 once it was
loaded (the saver writes the pen's colour and width, the loader gives the pen the saved
`stroke_style`). So `style_gaps` does not judge a sprite at all (first only its stroke half; the
fill half too since the sync, when `master`'s own `test_canvas_item_cache.py` gave three sprites a
texture brush they never paint), and `adopt_pen` does not write a sprite's stroke attributes from
a pen. What a LOADED sprite states is `master`'s rule since #502: what the file holds — that black
1.0 (round 1 of this story had read it off the pen; review 2 had asked for the type's stroke,
which `master` then decided otherwise). The owner kept `master`'s rule at the L1 pull request
(2026-10-19).

*Not changed, and inconsistent:* undoing a preset pick in the properties panel returns the style to "none" and leaves the preset's pen (a path of
`#ffa0522d` 5.0 stays `#ffb4aa96` 8.0; #524). The two ways to change a line's type disagree on a
preset line — the context menu keeps the preset's stroke, the panel gives the new type's — and
the context menu's undo gives a re-stroked preset line the preset's stroke back, not its own
(#525). A type change in the panel builds a new pen: a line's round caps and joins are square
and bevelled until the plan is reopened (#526). *Lesson:* an attribute that mirrors a Qt object's state is a
second source of truth; a second consumer finds where they parted — and the fix is one writer,
not one more reader. *And:* a guard that reads the source knows the spellings its author knew;
judge the objects a test leaves behind.

**A loader that starts to read a field must say what it does with a value it cannot use.** Round
1 made the loader restore a preset line's saved stroke; until then that field was not read for
such a line, so ANY value loaded — at the preset's stroke. Read unvalidated, a hand-made
`"stroke_width": null`, `"8"` or `[8.0]` and a `"stroke_color": null` raised, and the item was
skipped — gone after the next save; 0.0, -3.0 and 0.01 loaded as given, `"notacolour"` as black.
For a preset line a width that is no finite number of at least the panel's minimum (0.5) and a
colour Qt cannot read now keep the preset's value, each on its own, and nothing raises
(`TestAFileTheAppDidNotWrite`, 21 cases). A fully transparent colour is a colour — the panel's
own dialog offers the alpha channel — and loads as given. *Not changed:* a PLAIN line and the
four filled shapes apply a saved stroke as found, as `master` does: `null`, `"8"`, `[8.0]` and a
`null` colour skip the item; 0.0 and 0.01 load as given. And since `master`'s strict numeric plan
I/O (#453, `core/plan_io.py`) a width that is infinite, not a number or an integer no float holds
refuses the whole DOCUMENT before any item is built — for every shape
(`test_a_width_no_finite_number_can_hold_refuses_the_whole_plan`).

**Qt fills an open path with the brush that happens to be set.** *Symptom:* a bent boardwalk and
a bent stone wall filled the whole inside of the bend with one colour — over their own planks
and stones, out to the chord between the line's ends (measured for lines with legs of 3 m: up
to 66,449 px beyond anything the style draws).
*Root cause:* the rails and borders were stroked with `drawPath` while the brush of the last
plank or stone was still set; `drawPath` fills. *Fix:* `setBrush(NoBrush)` before the rails
(`path_style_paint.py`). A deliberate change of the 2D picture: of 528 renders through the real
`PolylineItem.paint` (11 styles × 3 shapes × 2 widths × selected or not × 2 scales × turned or
not) 464 are bit-identical to `master`, the 64 that differ are the bent boardwalk and stone wall.
Pinned on the canvas, not only in a 3D test: `tests/integration/test_polyline_style_paint.py`
(nothing beyond a style's reach; away from its bend a bent line is the straight line).

**The style painters cost every plain line a little.** Moving the ten painters out of
`PolylineItem.paint` (so that canvas and ground share them) first made EVERY paint build a
`PathStylePaint`, a copy of the line's points and a ten-entry table — also for style NONE, most
lines of a plan. Measured, interleaved, 100 plain three-point lines: 10.4 µs a paint on `master`,
13.1 with the object, 10.7 once a plain line builds nothing (`STYLES_PAINTED`). The 500-object
reference plan of NFR-PERF-01 holds no line at all, so its repaint numbers could not show it.

**Seen and not changed.** The live canvas paints an item through its device-coordinate cache,
which cuts whatever a path style draws beyond the item's `boundingRect()` (line + half a width
+ 2 cm): the bars of a metal fence reach 1.25 widths from the line and are cut at 30 cm width
(37.5 cm against 17 cm); an export paints without the cache and shows them whole. And a COMB
polygon — every tooth across the item — costs the canvas 10.5 s (1,024 vertices), 38 s (4,096)
and 186 s (16,384) for ONE paint: a plan file can freeze the 2D view.

#### The bake itself

**Adding 2,000 items to the scene one by one takes 45 s.** `CanvasScene.addItem` refreshes the
stacking order per item — quadratic. A plan file is loaded inside
`scene.suspend_z_refresh(renumber=True)`; a test that builds a large scene must do the same
(3.9 s). Not the bake's cost, but it looked like it.

**A line up to a pixel wide is rasterised per device.** Qt draws such a pen with its cosmetic
stroker, which clips the line to the image and then steps along it from the clipped start. A
tile is another image than the whole plan, so single pixels of a hairline differ (mean ≤ 0.016,
one pixel up to 142 of 255) — and nothing wider does. For the same pens a dash pattern AND its
offset are in **pixels**, not pen widths (measured for 0.25 to 1 px pens; offsetting a run in pen
widths puts its dashes elsewhere).

**Qt's dasher, handed a line that leaves the image, puts the dashes somewhere else.** It skips
what lies outside the device — cheaply: 19 km cost what 100 m cost — but the dashes it then draws
inside were measured off: over 9.5 km it agreed with the arithmetic at 261 of 393 places; for a
10 × 6 m dashed rectangle baked as six tiles 640 pixels differed from one whole render, for an
ellipse 7,564. *Fix:* the bake cuts a dashed line to the tile itself (`_runs_inside`) and strokes
each run with `setDashOffset(start / unit)`: 393 of 393, and 0 differing pixels for the
rectangle. An outline that lies wholly in one tile is drawn with the canvas's own call.

**An attached `QQuick3DTextureData` cannot be updated in place.** `setTextureData(new)` +
`update()` on a texture a `Texture` shows changed nothing on screen — also with
`textureDataNodeDirty` emitted by hand, and with the `Texture`'s property set to null and back in
the same turn (three variants, each rendered; the first picture stayed). A fresh object shows.

**… and a `Texture` element must never be pointed at a SECOND texture: the tile goes white.**
*Symptom:* the first run of the time budget on a real engine painted the plan over fourteen
transactions — and most tiles came out WHITE. *Wrong theory:* "a replaced texture was let go
before the scene had shown its successor; keep it one frame longer." Keeping it longer only moved
the white tile one frame later. *Measured* (RTX 4070 and WARP, Qt 6.11; two tiles, each sequence
ending in a frame, and one more frame after the replaced textures were let go):

| what was done to a tile | the frame after | one frame later |
|-------------------------|-----------------|-----------------|
| re-textured twice, no frame between | right | right — or white, when the replaced textures were let go after the frame |
| re-textured, then the OTHER tile re-textured, then a frame | **white** | white |
| re-textured, a frame, the replaced texture let go (what a presenting window does) | right | **white** |
| the same, with a new Model for every re-textured tile | right | right |

*Root cause:* when a `QQuick3DTextureData` that a `Texture` element once held is destroyed, Qt
resets that element's `textureData` to null — whatever it holds by then. The QML binding
`textureData: tileData` does not run again (its source did not change), so the tile is drawn
without a texture until its property is set once more. *Why nobody saw it:* every scenario of
the first delivery re-baked, took a frame and re-baked the SAME tiles, which sets the property
again; and its hardware window presented no frames, so the release after a frame never ran. In a
window that presents, every edited tile was white one frame after its edit, and an edit elsewhere
turned the tiles of the edit before it white. *Fix:* ONE TEXTURE PER `Texture`, FOR LIFE — a
re-baked tile is a new Model with a texture of its own, and its old Model is destroyed
(`quick3d/ground_tiles.py::_replace`). *Pinned:* five sequences on the render tier, each judged
right after its last update and again one frame later
(`test_scene3d_ground_render.py::test_a_re_textured_tile_keeps_its_picture`), and the budgeted
open against the one-pass ground, bit for bit. *Lesson:* "the object is alive" is not "the scene
shows it"; a test that always re-does what it just did cannot see what the second thing broke.

**What grows a Direct3D 11 process is `grab()` in a window that presents nothing — not the
re-bake.** *Symptom:* twenty full re-bakes of a 16 MB ground grew the process's private bytes by
16 MB each, although every replaced texture object was destroyed (two generations alive, never
more). *The first diagnosis was half right and its remedy wrong:* "Direct3D keeps every upload
while no frame is presented — apply edits no faster than frames are presented." The soak that
measured it called `grab()` after every re-bake. *Measured again, the same twenty re-bakes on the
RTX 4070 while its window presented 0 frames:*

| in the measured loop | private bytes per re-bake |
|----------------------|---------------------------|
| no `grab()` — what a live view does | **+0.00 MB** (the review); −0.10 and +0.01 MB (this box, two runs) |
| a `grab()` every fifth cycle | +3.2 MB (the review) |
| a `grab()` every cycle | **+16.1 MB** (the review); +16.1 and +17.4 MB (this box) |
| any of the three on WARP, 33 to 41 frames presented | flat (+0.01 to +0.19 MB) |
| a `grab()` every cycle on the RTX 4070, 38 frames presented | flat (+0.04 MB) |

*Reading:* Direct3D frees what was released when a frame is PRESENTED; a frame rendered by
`grab()` is rendered — its textures are uploaded for it — and never presented. So the growth
belongs to the grabbed frame: one generation of whatever changed since the last grab. Without a
grab nothing is rendered in a window that presents nothing, and nothing is uploaded. Pacing edits
changes nothing, and an agent-driven session that edits without grabbing does not grow. Why that
window presented no frame is NOT established: an OpenGL window on the same GPU presented 45
frames in the same session, so "the display was asleep" does not explain it.
*What follows:* (1) **the rule — no repeated `grab()` on a live host that is not presenting; a
screenshot goes through the offscreen path** (`offscreen.render_records`: a hidden view of its
own that is closed after its one frame, which gives everything back); (2) gate G6 measures what
a live view does — no frame in its loop, and since review 2 no call into the QML scene either —
and is UNCONDITIONAL on the machine's own adapter and on WARP; the grabbing soak is its
documented control
(`test_a_grab_a_cycle_is_what_grows_a_direct3d_window_that_presents_nothing`). *Lesson:* a soak
measures everything in its loop; before a growth is blamed on the thing under test, run the loop
without the instrument.

**… and a gate that cannot fail in one of its cells is half a gate.** "Flat on any adapter,
whether the window presents or not" was written from two measured cells: WARP, whose window
presents its frames (it renders, uploads and frees — flat), and the RTX 4070, whose window
presented NOTHING. Without a grab nothing is rendered in such a window, so nothing is uploaded
and nothing on the graphics side can grow: that cell shows that re-baking does not grow the
PROCESS side, and no more. A hardware window that presents its frames is not automated — it is
the owner's manual checklist item "watch Commit size while dragging a lawn with the display on" —
and the requirement says which cells were measured (FR-3D-GROUND-05).

**`frameSwapped` may never come.** The replaced textures are released when a frame was presented
— and, because that signal may never arrive, at the latest on the next ground update. A release
that only waits for the signal is the L0 spike's growing list again.

**A bound that keeps "the topmost N" drops what everything stands on.** With 256 pavers on a
lawn in one tile, the record `TILE_RECORDS` left out was the lawn: 138,240 px of a 5.12 m square
were bare meadow, one log line said so. The counts were all pinned; nothing asked WHAT was
dropped. The first fix — the walk ends at the first record that opaquely covers the tile, and
below the cut a tile keeps what covers it WHOLE — was pinned with a lawn that was the plan
rectangle, the one lawn that covers every tile whole, and passed. Ten centimetres inside the
plan's edge the same lawn was dropped again: 149,604 px bare, mean 24.4 of 255 against the canvas
(review 2). The rule is now stated by its outcome — a tile loses its SMALLEST records, ranked by
how much of the tile their paint box overlaps — and pinned for four lawns, three counts of pavers
and a real scene against the canvas (§8.29.5). *Lesson:* a rule worded as a mechanism ("keep
what covers the tile") can be followed to the letter and miss what it was for; state the
outcome, and test it on a geometry the mechanism was not written for.

**After a failure, "forget everything and start again" is not the safe choice.** A bake that
raised cleared the baker; the sink kept showing its sixteen painted tiles — until the next edit,
anywhere, re-baked from an empty baker under the time budget: ONE painted tile, fifteen passes to
refill, a traceback, and the same again for every edit while the failure lasted. A tile whose
paint fails now keeps its picture and its place in the books, and nothing else is touched; and
a bake that raises anywhere else RESTARTS the baker — books forgotten, pictures kept until each
tile is painted anew (§8.29.5). The first version of this fix covered only the raise site the
review had used (a tile's paint); the pin for "any other site" raises in the admission walk
instead. *Lesson:* test a failure path by what the user sees on the edit AFTER it, not by the
state right after the exception — and inject the failure in more than one place.

**Every cache release in Qt Quick 3D 6.11 keeps about half of the same-size tile textures —
OPEN (#532)** (L1.5 Part B, review 3). *Symptom:* with the ground bake wired in, the
workspace's G7 soak (twenty rebuilds of bench_small, ADR-060) grew dedicated GPU memory by
7.5 MB per rebuild with its release after quiet and by 19 with the release in the pass — 0.0
and −0.1 without the baker; two G7 gates failed (13.75 and 28.0 MB per rebuild against 10).
*Wrong theory:* "the tiles leak on a reset — `GroundTiles.clear()` lets their textures go
before a frame"; resets without a release are flat. *Isolated on WARP* (a 16-tile ground,
twenty cycles, private bytes per cycle): re-bake + `releaseResources()` each cycle +10.7 to
+13.3 MB; the same without mipmaps +7.4 to +8.7; re-bake alone 0.00; reset + re-bake alone
0.00; one release then twenty re-bakes +0.06; a release every fifth cycle a 10 to 25 MB step
at each release. (A control "new tile Models with the SAME textures + release −0.28" seemed to
show that it takes a re-bake; that control was broken — its frame was white, no texture ever
loaded.) *Root cause:* a Qt Quick 3D 6.11.0 bug, read in its source and proven by measurement
(#532): `QSSGBufferManager::clear()` walks `customTextureMap` with `++it` while
`releaseTextureData(it.key())` erases through its own lookup; Qt 6's `QHash` shifts the next
entry of a collision run back into the freed slot, `++it` skips it, and
`customTextureMap.clear()` drops the skipped entries unreleased. The key's hash covers only
size, depth, format and transparency, so same-size tiles all collide and about half leak per
release (WARP, 16 × 512²: +10.8 / +11.7 MB a cycle against a prediction of 8 × 1.333 MiB) —
static tiles too: every release leaks, re-bake or not. Tried and rejected: in-place updates,
distinct sizes (not flat at ≥ 32 tiles), `Texture.sourceItem` images. *The exposure:* the bake
never asks for a release (tile Models are not counted in `TickReport.retired` — they need
none), but every release the workspace makes for item changes leaks — 64 retired Models and
half a second of quiet, or 512 at once: a delete or regrow of that many, a document change, a
date change on a planted plan (every dated plant regrows). The largest ground (~4096² px,
~85 MB with mips) loses ~42 MB per release; bench_small's (19.5 MiB with mips) read
+9.3 to +11.4 MB of dedicated GPU memory per rebuild in eight runs of review 3. *Wrong first
answer* (a fallback taken before review 3, which replaced it): gate the leak with the bake OFF
and report the product against a "regression ceiling" of 60 MB per rebuild — the gate then
measured a configuration nobody ships, and a ceiling of about three grounds could not fail.
*State:* G7 measures the product (bake on) against the plain bound plus an allowance derived
from the soak's OWN ground (0.6 × tile-texture bytes per release × releases per reload,
§8.10.9); a non-strict `xfail` tripwire holds the GPU slope to the plain bound; the bake-off
run stays as Model churn alone. Whether 3D may become the default view while #532 is open was
the owner's decision (put to them with the measured exposure), not a roadmap blocker; they
shipped it at the L1 pull request (2026-10-19, ADR-060 addendum D5). The fix
is upstream Qt's (a report draft for the owner) or a tile path outside the buffer manager's
maps that also passes G7. The probe is in the story's scratch (`probe_release_driver.diff`).
*Lesson:* a soak that passes alone (G6: re-bakes, no release) and one that passes alone (G7:
releases, no textures replaced) can both be green while their combination leaks — run the
product's own policy against the new kind of resource. And gate what ships: an allowance for a
known leak, derived from the run's own numbers, keeps the gate able to fail; switching the new
resource off, or a ceiling chosen by eye, does not.

**A slope estimator meant to ignore one bad reading does not ignore one STEP** (Ruling R41).
Theil–Sen — the median of all pairwise slopes — shrugs off a single outlier; a single step in
the middle of a window is not an outlier but a level change, and most pairs straddle it. G6's
WARP cell read +2.80 MB a cycle for a curve flat on both sides of one +20.6 MB step (bound 2.0;
re-runs +0.09, −0.01, +0.00). A leak is a property of every cycle, so the gate reads the median
of the per-cycle steps now (§8.10.10). *Lesson:* choose the statistic by the shape of the
failure it must reject AND the shape of the noise it must accept, and pin both with measured
curves.

**A flat item the solid path refuses is not "missing from 3D" any more.** The workspace's
problems list counted an in-ground bed traced with 6,000 points as not shown; with the ground
bake that bed is painted on the ground (FR-3D-GROUND-04), so the count — and a test that
expected it — changed with the merge (both stories' tests now trace a RAISED bed, which is
truly absent). *Lesson:* when one story makes something visible that another reports as
missing, the reporting side's test is the one that notices.

**A budget shared between new and old work starves the old.** One tile a pass, nearest to the
last edit first, and an edit before every pass: the edit's tile was painted, the budget was
spent, and 14 tiles stayed pending after 1, 5, 10, 20 and 40 edits — a drag over a just-opened
plan kept the rest of the ground bare for as long as it lasted. A call that brings an edit now
owes the backlog one tile.

**A painter that raises between `save()` and `restore()` poisons the next record.** A
stepping-stones path that raised at its third stone left the painter two levels deep, moved and
turned to that stone; the caller's one `restore()` popped the wrong level and the rectangle
painted next lost 5,476 of 44,104 px. Pose and opacity are now set absolutely for every record
and restored absolutely by `paint_record`, and a failing record's painter is ended and begun
anew. In the same place: a failure was cleared per TILE, so an item that failed in one tile and
painted cleanly in the next was reported as fine.

**A count is not a time.** The per-tile bounds are on counts, and Qt's cost per count spans three
orders of magnitude (0.7 µs a vertex for a wavy ring, 1.2 ms for a comb: 19 s for one record in
one tile). The first delivery stated "a tile at its bounds: 0.2 to 2.65 s" from the shapes it had
thought of. Only a time budget between tiles holds a pass to something, and it holds it to the
budget plus ONE tile — two when an edit arrives over a backlog (§8.11, §8.29.5).

**Qt paints the last row of a rectangle clipped to a narrow image one step lighter.** A lawn
over a 1100 × 700 cm plan, tile by tile, against the same lawn in one image: 76 values of the
76-px-wide last tile differ by 1 of 255. Tests that compare a tiled ground with an untiled one
allow that one step and say why.

**Four ways a bound can fail to bound** (the security passes; the patterns are §8.11):
a cap on VERTICES does not bound work that follows a LENGTH — two points 19 km apart are 475,001
gravel dots; a budget that charges what is handed out but not what is walked to find it lets 256
paths walk 20 million steps for a few hundred dots (charge the walk); `if budget:` treats a
budget of zero as "no budget" (a spent budget must mean "no more"); and a per-tile cap applied at
paint time sat behind bookkeeping that had already registered every record in every tile it
touched — 2,050,003 entries for 50,000 whole-plan rectangles, 55,201 once the tiles of a record
are four integers.

**PyQt notes.** `QQuick3DObject.update()` exists at runtime but not in PyQt6 6.11's stubs;
`markAllDirty()` is not exposed at all. A `QObject` subclass instance released by Python IS
destroyed on the C++ side (its `destroyed` signal fires) — count that, not Python's references.
`QPainter.end()` followed by `begin()` on the same image is the one way to drop saved levels a
failing painter left behind; there is no way to ask a painter how deep its stack is.

### CI/release hardening: locked metadata also contains the application version

A version-only edit to `pyproject.toml` makes `uv.lock` stale. The measured probe failed
`uv lock --check --offline`, then `uv lock --offline` changed only the editable project's
version. `scripts/prepare_version_sync.py` stages and validates this refresh before applying
any source writes, compares full third-party records, and regenerates the export. The
version-sync chore must therefore include the lock alongside both source declarations.
Pinned by `test_version_sync_cli_is_offline_transactional_and_idempotent`.

Fresh baselines must use declared locked dependencies: the developer venv included undeclared
Qt stubs and older type/coverage tools. Linux and Windows also disagreed about one ignore: 229
were unused on both platforms, while one Windows-unused ignore remained needed on Linux.
Only common unused directives were removed; allowances are measured per platform. Pinned by
`test_baseline_keeps_platforms_independent_and_rejects_tool_drift`.


**Offline refresh is not the same as a universal re-resolve.** A cold locked Linux install
cached its selected wheels but lacked other-platform resolver metadata. Changing only the
project version triggered a re-resolve and failed offline; a freshness check did not fix it.
Version sync now stages the editable lock-record version before native offline validation,
then verifies all third-party records unchanged. The real subprocess test uses an empty cache
on both platforms. Underlying tool stderr must be reported; a process exit alone hid the cause.

**CI hardening review findings (#404/#402/#399).** A fresh Windows checkout changed the export's
1,857 LF endings to CRLF; a working-copy byte check missed it. Generated locks now have explicit
LF attributes. Coverage records must have unique normalized file/line identities and supplied
summary counts must agree with aggregates, or duplicated XML statements can inflate a floor.
An injected second-file write failure verifies full version-sync rollback. Release recovery
resolves a published tag and successful workflow from the feature merge SHA; tag transition
is required only when observing a new merge, so restart after publication can finish normally.
The isolated protection PR #420 rejected its failing head and merged its corrected green head
without a bypass under the proposed admin-enforced policy; temporary branches/policy were
removed. Master enforcement was activated and verified before PR #422 merged normally. Evidence: quality/protection-validation.json.

**Hosted update tooling can lag a reproducible CI pin (2026-10-09).** The first security
update attempt failed with `tool_version_not_supported`: detected uv `==0.12.23`, supported
uv `0.12.18`. Evidence: [Dependabot run 37951191628](https://github.com/cofade/open-garden-planner/actions/runs/37951191628).
The project CI and release used the agreed pinned tool successfully. Preserve the pin and
perform the setuptools advisory update in a separately reviewed manual dependency PR;
automatic security-update support is unresolved, not a successful remediation. An exact
bootstrap pin must be checked against hosted update tooling as well as installation tooling.

**Unicode CLI output needs an explicit stream encoding** (issue #417): UTF-8 wiki files did not prevent redirected Windows stdout from using cp1252. The comparison command emitted byte 0x96 for an en dash and failed to encode a check mark. `scripts/sync_wiki.py` now sets stdout and stderr to UTF-8 before printing. The subprocess comparison regression in `tests/integration/test_wiki_publication.py` captures real Unicode diffs without a UTF-8 environment override.

### 11.4.18 What the looks, the sky and the wind taught (Phase 17 L1.4, #385)

Symptom → root cause → fix, for the things that cost time while the looks (ADR-059 addendum
"looks, sky and the animation policy", §8.29.4) were built. Engine facts are also in the
`ogp-3d-renderer` skill §14; art-direction fixes in `ogp-lush-cinematic` §7.

1. **A colour derived in linear light came out three times too dark at night.** *Symptom:* the
   night fog met the night sky as a black line (luma 3 where the sky above it read 13), although
   the fog's sRGB code was the exact encoding of the linear value the look derived. *Root cause:*
   Qt Quick 3D does not linearise a `color` property with the sRGB curve but with a polynomial
   (`x·(x·(x·0.3053 + 0.6822) + 0.0125)`) — the two agree from about 0.3 up and differ threefold
   for very dark colours: code 5 is 0.0015 by the sRGB curve and 0.0005 to the engine (measured
   with a flat ambient light on a white box in the un-tone-mapped truth view). *Fix:* the three
   colours the look derives in linear light (fog, plain sky, fill) are handed over as
   `QColor.fromRgbF(engine_srgb(linear))` — the inverse of the engine's own conversion, as floats
   (8 bits are steps of a fifth down there). **A colour property is not "sRGB, linearised by the
   engine" for dark values — compute what the engine will make of it.**
2. **The night horizon was a bright line — the spike's own formula.** *Symptom:* at eye height
   the fogged meadow met the night sky with a one-row step of 10.5 luma (high) and 21.2 (low).
   *Root cause:* the spike's fog was horizon × probe exposure × 0.8 in every mood, while the night
   SKY is drawn × 0.25 (`skyEnergy`): the fog was four times brighter than what it met. Nothing
   on the L0 board looked at the horizon at night. *Fix:* the fog carries the sky's energy
   (`fog_linear`): 2.4 / 3.2. And in round 5 the night sky's ground hemisphere (the sliver under
   the far-clipped meadow) at the sky's energy, 0.25, instead of the spike's 0.15 — the same day
   lesson carried to night: dip 2.07 / 1.04 → 0.01 / 0.12. **A rule measured by day (ground
   energy = sky energy; fog = what the sky draws) must be re-measured where the inputs change —
   at night they did.**
3. **The engine animates a hidden window.** *Symptom:* none yet — found by the render tier
   before it could become one: with the window hidden and the wind's `FrameAnimation` still
   running, `windTime` went on advancing (0.59 s of clock in 0.6 s hidden; RTX 4070).
   *Root cause:* a hidden `QQuickView` keeps its animation driver ticking. *Fix:* the animation
   policy STOPS the clock when the pane is hidden (`set_wind_running(False)`) rather than trust
   "hidden"; hidden means zero ticks. And stopped is not rest: a paused non-zero clock keeps the
   sway of that moment in the frame — reduced motion and every truth probe RESET it to 0
   (`rest_wind`).
4. **A sky texture must be a fresh pair, and released with its data.** *Symptom (avoided,
   measured by the sky sequence A → B → C):* the ground bake found that a `Texture` whose
   `textureData` is re-pointed loses its data when a data object it held EARLIER is destroyed
   (#476: a white tile). The spike's sky re-pointed one Texture. *Fix:* every build is a new
   `Texture` with a new `ProceduralSkyTextureData` as its CHILD; only the Texture is ever
   destroyed, after the scene shows the new one, so a pair lives and dies together. A frame
   after the old pairs are gone is the same sky, its sun at the solar azimuth. Measured over
   twenty sun changes, frames presented and withheld: no growth per change in committed memory
   and in dedicated GPU memory — no cache release needed, unlike a retired Model (§11.4.16
   item 2); the positive control (a `buildSky` that never destroys the old Texture) reads 8.2 MB per
   change (presenting: 0.0; frames withheld: 0.125; the bound 1.0).
5. **A sun-grazed lit wall hatched only on Direct3D 11.** *Symptom:* at high and ultra, on the
   dev box's GPU, a wall the sun lit at n·l 0.33 showed a fine diagonal hatch (pixel noise
   1.15 % of its luma, the face 3.7 luma darker). *Root cause:* the spike's shadow bias of 5 was
   measured on llvmpipe with smaller maps and fewer cascades. *Fix:* bias 10 at high and ultra
   (0.18 %, the dither's floor; IoU unchanged). **Shadow acne is a function of the backend, the
   map size and the cascade split — re-measure the bias on the real GPU per preset.**
6. **A view that draws on demand has no frame rate.** *Symptom (by design, before it was
   built):* an automatic preset fed with "frames per second" of a still view would read a
   sleeping display, a hidden pane or an idle scene as "slow" and step down for nothing.
   *Fix:* `AutoPreset` reads presented frames only while the wind animates (the view draws
   continuously), and ten seconds without a presented frame is no data: what was collected is
   dropped and the preset holds. Never a readback to measure (ADR-060 decision 17).
7. **The wind ran in compatibility mode** (fix round 1, review P0). *Symptom:* on a software
   adapter the view with the wind running drew 139 frames in 4 s at 1,351 % of one core (still:
   1 frame, 18 %); the GUI's 10 ms timer ran 19.9 ms late. *Root cause:* the controller decided
   the sky by the render mode (`sky_light=not software`) but the wind and the automatic preset
   by visibility alone — three decisions about one fact, made in two places; and a render-tier
   test asserted the bug for `[software]`. *Fix:* ONE parameter, `LookController(software=...)`,
   decides sky, wind and the automatic preset together. **When one fact gates several
   behaviours, pass the fact, not one of its consequences.**
8. **A failing sky stopped every later look** (review P1). *Symptom:* a host whose sky could
   not be built got 20 suns, 0 looks, 20 sky attempts and 20 ERROR lines. *Root cause:* the sky
   build and `set_look` shared one `try`; the sky was retried in every pass and failed first.
   *Fix:* the sky in its own `try`; on failure one ERROR, the plain sky for the session; the
   look always sent (20 looks, 2 sky calls — the build and the clean-up —, 1 error).
9. **A per-session memory forgot what it learned** (review P1). *Symptom:* "high is too slow,
   medium is fine" stepped medium -> high -> medium in every session. *Root cause:* the bar on a
   level that proved too slow lived in memory; the first step up of a session needed only one
   window. *Fix:* the bars are stored with their deadline and next length, seeded at the first
   poll, and the first step up waits the hold time. *And the store is hostile input* (re-check):
   a 400-digit integer made `math.isfinite` raise and the 3D view refused to start on every
   start; a bar of 1e18 s barred the level for good. Now an unconvertible number drops the bar,
   and a seeded bar is clamped to `max_retry_s` (both pinned).
10. **Judge a fade by the frame, not by one of its inputs** (look review P1, the twilight
    ramp). *Symptom:* the twilight colours mixed in linear light move the sky horizon 8 codes in
    the first half degree and 52 in the last (the drawn horizon 1.1x and 3.4x) — so they were
    mixed in STOPS instead (1.34–1.48x every half degree). The render tier's dusk sweep then
    failed: the frame went from 0.116 (0.6°) down to 0.023 (−3°/−4°) and UP to 0.034 at −6°,
    because the sky faded faster than the moon came in. *Root cause:* the frame's light is the
    sky AND the fading-in moon, at a rising exposure; a smooth sky alone is not a smooth frame.
    *Fix:* back to linear colours (the ruling's recipe): the frame darkens all the way, 0.116 ->
    0.099 (0°) -> 0.052 (−3°) -> 0.034 (−6°); the sky band's late step is carried by the moon.
    *Tolerance, stated* (re-check): at 0.25° sampling `low` rises by 1.2 % over the last half
    degree (−5.5° 0.0338 -> −6.0° 0.0342; `high` stays flat) — invisible, and below what the 1°
    rows and `test_dusk_never_brightens` (sky term only) can see.
    **Measure the composite the viewer sees before "improving" one ingredient.**
11. **FXAA cannot resolve a picket fence** (look review P1, #529). *Symptom:* a moiré band on
    the fence at low. Measured against a 2x-supersampled render: FXAA's luma error 20.0, 2x MSAA
    12.0 (and its dark-pixel share 18.8 %, worse than FXAA's 12.7 %), 4x MSAA 6.2 (medium 7.2).
    *Fix:* low takes 4x MSAA; on the RTX 4070 its cost was inside the run-to-run spread.
12. **Memory grows while the wind runs — intermittent (FU-L14-2, #534; item 1 of §11.4.20).** *Symptom:* the first soak of the
    default steady state (the plan shown, the wind running; fix round 1) reads 2.6 MB per minute
    of committed memory over 2 minutes and 2.09 over 6 (linear: 1034.2 -> 1045.9 MB, 21,594
    frames, about 0.55 kB a frame); dedicated GPU memory flat. With the QML engine's collector
    called every 5 s: 0.81 MB per minute, in steps. *Root cause:* not isolated — per-frame
    garbage of the `FrameAnimation` handler (`windTime += frameTime`) the V4 collector reclaims
    late, and something it does not. *State:* the registered bound (2.0) is kept as a strict
    `xfail` in `test_view3d_looks_render.py`. Untried: the clock as a `NumberAnimation` (no
    JavaScript per frame). The soak runs with timer-paced frames (`QT_D3D_NO_VBLANK_THREAD=1`,
    which the product does not set); the product's vblank-paced path is unmeasured (the
    re-check's display was asleep: 0 frames presented without the flag).
13. **Qt has no "reduce motion" preference to honour.** `QStyleHints` in Qt 6.11 exposes none
   (checked against the binding; a drift guard in `tests/unit/test_view3d_look_settings.py`
   fails the day one appears), so the setting is the application's own
   (`view3d/reduced_motion`).

### 11.4.19 What selection, the info card and walk mode taught (Phase 17 L1.8, #385)

Symptom → root cause → fix, for the things that cost time (ADR-060 addendum, §8.29.8). The
engine's own facts are in the `ogp-3d-renderer` skill, §15.

1. **Selecting an item made the next Ctrl+click clear the selection.** *Symptom* (the render
   tier's first run on the real engine; the default tier was green): plain click on A → {A};
   Ctrl+click on B → {} ; Ctrl+click on B again → {B}. And two `QTest` warnings, "Mouse event at
   … occurs outside target window". *Root cause:* the info card appeared below the view with
   the selection and took 152 px from it. The view's vertical field of view is fixed, so the
   picture was re-scaled; B was no longer under the pointer, the click met the lawn, and a click
   on nothing clears. *Fix:* the card has a place of one height (`View3DCardSlot`), and the
   eye-height box kept its room while hidden (the strip grew 4 px in walk mode; since fix round 1
   the eye height is a menu on the Walk button — a box beside it made the strip's row wider than
   a 455 px pane, and the workspace's notices were cut). *Lesson:* in a
   pane that holds a native 3D view, anything that comes and goes is a resize of the view —
   reserve its room, and pin the view's rectangle in a test. A stand-in host has no picture and
   cannot see this; only a real click on a real frame can.
2. **The ring was invisible from above on OpenGL.** *Symptom:* none on the dev box (Direct3D) —
   found by running the ring scenario once with `QSG_RHI_BACKEND=opengl`: 0 ring pixels in every
   top-down frame, 587 in the perspective frame. *Root cause:* "in front" was written as
   `POSITION.z *= 0.01`. Where clip z runs 0..1 that pulls a fragment to the near plane; where
   it runs −1..1 it pulls it to the MIDDLE of the range — and in an orthographic view from
   4,000 cm the ground lies in the near half. In a perspective view nearly everything lies in
   the far half, which hid it. *Fix:* `mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, 0.01)`.
   *Lesson:* a shader that touches clip space is run on both depth conventions; the Windows dev
   box can do that.
3. **A depth-tested ring of a wall is inside the wall.** A WALL is built 30 cm thick on whatever
   stroke the plan drew; the footprint's outline is 12.5 cm inside the masonry on both sides.
   Measured from above: 3.6 % of the outline visible. The same fact stops a walker that
   collides with footprints 12.5 cm inside the wall. *Lesson:* the footprint is the plan's
   truth, not the picture's; whatever must agree with what the user SEES asks the builder.
4. **Every selection change costs a whole-plan snapshot.** The canvas repaints a selected item,
   the scene emits `changed`, and the pipeline's controller cannot tell a repaint from an edit:
   120 of 120 selection changes rode a pass that took a snapshot (3.6 ms on the small bench
   plan, 14 on the large). The ring itself needs none. Not fixed here — it is the pipeline's
   rule ("every `changed` marks the plan dirty"; the workspace story's plan revision is the
   fix) — and reported. A strict-`xfail` test asserted zero snapshots; it XPASSED when the plan
   revision landed (re-measured 2026-10-19: 6 snapshots for 4 selection changes before, 0 after)
   and its mark is gone.
5. **The canvas does not treat Shift the same everywhere.** A Shift+click on an item toggles it.
   A Shift+click THROUGH a locked item acts as a plain click: the select tool's Shift branch
   looks at the top item only, finds it locked, and falls into the plain path, which replaces
   the selection. 3D toggles in both cases. Reported as a defect of the canvas.
6. **A test of the workspace raced its first pass.** `open3d()` waited 80 ms and then cleared the
   sink's call log; on a busy machine the first pass came later and its calls were counted as
   the selection's. *Fix:* wait on the condition — `controller.apply_count >= 1 and not
   controller.dirty` — never on a duration.
7. **A hidden pane is not a clean controller.** "Select while 3D is hidden, show it, expect ONE
   ring call" failed: the canvas repaint had marked the plan dirty too, so the catch-up was a
   full pass (correct), and the "Building the 3D view…" notice showed for it. Assert what is
   sent, not that nothing else is owed.
8. **`print` with an arrow failed under `-s`.** A measured line containing "→" raised
   `UnicodeEncodeError` on the Windows console's cp1252. Measured lines are ASCII.
9. **A brute-force judge can be the slowest thing in the suite.** Checking 20,000 walker
   positions against 32,548 segments one by one took about 100 s per plan. In runs of 256
   positions against the segments within reach of the run's bounding box — still no grid, still
   every candidate segment — it takes 3 s.
10. **A guessed bound is not a measured one.** Three first-draft assertions were wrong about the
    code they tested: "more than a kilometre walked" (841 m), "no step longer than v·dt" (a push
    out of a corner adds 0.03 %), "more than 120 triangles hit" (112). Each was replaced by the
    measured number with its margin, and the measured number stands in the test.
11. **A selection change did not reach the engine, once.** WARP, the first run of the render
    tier's timing loop: 119 of 120 arrived within two seconds, and the ring was loaded 121
    times instead of 120. Not seen again in 3,240 changes on WARP and 480 on the GPU, with and
    without load on the machine. The cause is not known. The driver now records every pass of a
    change that misses (what was selected on the canvas, what the sync wished and sent, the
    ring loads), so the next occurrence explains itself. Stated as an open doubt, not as fixed.
12. **"The document was replaced" comes BEFORE the old document goes** (found when master's
    #428 mechanism, `CanvasScene.document_replaced`, replaced the main window's hand-called
    hook). The workspace's slot used to read the canvas selection "for the new document" —
    and at that moment the old items are still in the scene and still selected. It did no
    harm only because Qt's `clear()` / `removeItem` then emit `selectionChanged` for every
    removed selected item (measured: a mutant that keeps the read passes the same test). *Fix:*
    the slot reads nothing of the scene and empties the ring's wish. *Lesson:* a slot of a
    "replaced" signal must not read the thing being replaced; a test that passes on both
    versions is a pin of the outcome, not of the fix — say so.
13. **Five lists, five ways to select an object by its id.** The Diagnostics, Canopy and Guilds
    panels walked `parentItem()` to a group, the plant search took the item as found, the 3D
    list used the canvas's click rules — each with its own resolver. They agreed only because
    every group in the app is a `QGraphicsItemGroup` (whose `setSelected` hands the selection
    to the group) and a locked item's `setSelected(True)` does nothing. *Fix:* ONE path,
    `ui/canvas/select_by_id.py`. *Lesson:* a behavioural test cannot tell two copies that
    happen to agree from one path; pin the structure as well (§8.10.12).
14. **Every mutant read BROKEN after the suite went parallel.** The three L1 mutation scripts
    (`scripts/mutation_check_scene3d.py`, `…_built_world.py`, `…_plant_art.py`) run
    `pytest <tests> -q -x`; with master's `-n auto` in `addopts` (ADR-058) a failing test under
    `-x` ends the run as "interrupted" — exit code 2, not 1 — and the scripts count only exit 1
    as KILLED. Measured: a mutant whose tests failed 5 times read "BROKEN … 0/1 mutants
    killed". *Fix:* each script passes `-n 0` (a later `-n` wins). Found while two of the
    scene3d mutants had gone STALE: L1.8's selection lines sat inside their patterns, which
    the default run reports (`test_every_mutant_still_matches_its_file_exactly_once`); both
    re-anchored, and the new lines got mutants of their own. *Lesson:* a tool that reads an
    exit code must be re-checked when the runner's defaults change — run one mutant whose kill
    is certain.
15. **In walk mode S toggled Snap to Grid and never moved the walker** (review 1, P0). *Root
    cause:* Qt sends `ShortcutOverride` to the view's window before it looks for a shortcut;
    the walker took only `KeyPress`, and the 3D view is embedded, so the main window stayed the
    active window and its `S` shortcut fired. W A D and the arrows worked only because no
    shortcut sat on them. Every test passed: they called `eventFilter` by hand, which has no
    shortcut map. *Fix:* claim `WALKER_KEYS` at `ShortcutOverride`; deliver test input through
    Qt (§8.10.12). *Lesson:* a key filter in an embedded window owns a key only if it owns
    its `ShortcutOverride`.
16. **"Walk" left the keyboard on the plan** (review 1, P1-2): W then picked the Wall tool and
    Escape went to the canvas. *Fix:* `Quick3DHost.focus` (`requestActivate`), measured on the
    real window; the focus goes back on leaving while the view still has it.
17. **Ctrl+click on a locked item with nothing behind it cleared in 3D; the canvas keeps the
    selection** (review 1, P1-1). The bridge was told only "toggle"; Qt's own rule is that a
    Ctrl click on an unselectable item changes nothing, while Shift (the select tool's)
    and a plain click clear. Measured rows pin both now.
18. **A look in walk mode could select** (review 1, P2-4): walk mode kept every move to itself,
    so the orbit filter never saw a flick of up to 4 px within 0.4 s and picked on the
    release. Now a left drag turns only past the click's slop, and a drag that turned cancels
    the click.

### 11.4.20 What the default flip and the removal of Qt 3D taught (Phase 17 L1.9 / L1.10, #385)

Symptom → root cause → fix (ADR-060 addendum "the default and the removal", §8.29.9; tests
§8.10.13).

1. **A strict xfail turned red the day its fix was to be measured — without the fix.**
   *Symptom:* the wind soak's strict xfail (FU-L14-2: "committed memory grows 2.1 to 2.6 MB a
   minute while the wind runs", registered bound 2.0) PASSED on 2026-10-19 on the unchanged
   code (`--runxfail`; strict, it would have failed the render tier). *Root cause:* not found —
   the growth L1.4 had measured did not reproduce: six alternating soaks of 4 to 5 minutes,
   three with L1.4's `FrameAnimation` and three with the planned fix (a C++ `NumberAnimation`
   on `windTime`, no JavaScript per frame), read 0.77 / 1.04 / 0.89 and 2.03 / 1.04 / 0.46 MB a
   minute from the first sample to the last (second-half slopes 0.17 / 1.26 / 0.23 and 1.51 /
   0.83 / 0.00): the two clocks inside each other's spread. *Fix:* the clock change was
   reverted (it changed nothing measurable) and the xfail removed — and a seventh run the same day (the final render tier on the L1.9/L1.10 tree) read a second-half slope of 2.637
   MB a minute: intermittent, not gone. The gate is a non-strict xfail again (#534). *Lesson:* run the unchanged code first; a fix measured
   alone would have been credited with a difference that was already there.
2. **"Settled" must know every timer that books a pass.** *Symptom:* after the date-playback
   throttle, the workspace workflow test read `[begin, set_sun, commit]` where it expected the
   tree's regrowth. *Root cause:* the throttle's trailing regrowth waits on a third timer;
   `Scene3DController.idle` and the tests' `pipeline_settled` knew only the posted pass and the
   tick timer, so "nothing is on its way" was true while a regrowth was booked. *Fix:* both
   include `_date_timer` (§8.10.13).
3. **The same test, and the time between two of its writes.** *Symptom:* that test also wrote
   the date twice about 200 ms apart: inside the 500 ms interval on the dev box (the second
   date deferred), outside it on a loaded runner (regrown at once). *Root cause:* its
   expectation depended on the machine's speed. *Fix:* it pins `DATE_REGROW_MIN_MS = 0`; the
   throttle's own tests make bursts deterministic (one turn of the event loop) and keep the
   wall-clock bound in a `perf` test with a control arm.
4. **The menu text promised a window.** "&3D View…" — the ellipsis says "opens a dialog or a
   window", and the action now switches a mode of the main window. The text lost its
   ellipsis (a new source string: German and Spanish had to follow, the gate of #496 says
   so) and its status tip says "beside the plan".
5. **Qt 3D ignored Qt Quick's software switch.** *Symptom:* the old window's "WARP" budget run
   reported the RTX 4070 as its adapter and GPU-speed numbers. *Root cause:*
   `QSG_RHI_PREFER_SOFTWARE_RENDERER` is read by Qt Quick's scene graph; Qt 3D creates its own
   RHI and does not read it. *Fix:* none needed after L1.10 — the row says "not measured"
   rather than reporting a GPU run as WARP. *Lesson:* check the adapter a run REPORTS, not the
   switch it was given.
6. **A sleeping display presents no frames.** *Symptom:* the frame-cost board measured 0 fps on
   the RTX 4070. *Root cause:* the desktop's display was asleep; a vblank-paced swap chain
   presents nothing then. *Fix:* the GPU rows ran timer-paced (`QT_D3D_NO_VBLANK_THREAD=1`,
   capped near 60) and say so. *Lesson:* a frame rate of 0 is a measurement of the display
   first.
7. **A mock that accepts every call proved a call, not a light.** *Symptom:* moved from the
   old window's `MagicMock` onto the workspace's recording engine, "a date edit moves the 3D
   light" failed: no `set_sun` reached the engine. *Root cause:* the test plan had no location,
   so the light is the fixed default sun, which no date moves; the mock had answered the old
   app's unconditional `set_sun` call. *Fix:* the test gives the plan a location. *Lesson:* a
   recording double that keeps the protocol (here: a repeated sun sends nothing) finds what a
   catch-all mock hides.
8. **A lock refresh changes more than the packages it drops.** *Symptom:* `uv lock --offline`
   after removing two pins removed their two entries from `uv.lock` — and reordered three
   resolution-marker lines. *Root cause:* uv writes the marker list in its own order; the
   strings were the same and no version changed (checked line by line). The PEP 751 export
   (`pylock.toml`) changed by exactly the two packages' 26 lines. *Lesson:* read a lock diff
   by what it resolves, and say what else moved.
9. **A branch merged after the removal used the deleted spike.** *Symptom:* after L1.5 joined,
   a ground-bake test imported `spike_q3d.runner.MEADOW_ALBEDO`. *Root cause:* L1.5 was written
   while the spike existed; the removal and the new use met only at the merge. *Fix:* the test
   reads the meadow from the frozen reference. *Lesson:* after merging into a removal, scan the
   merged tree for every removed name, not only the files that conflicted.
10. **A local build bundles what the build environment has installed, not what the lock pins.**
   *Symptom:* the first frozen build after the removal, made with the shared development venv,
   still carried Qt 3D's eleven `Qt63D*.dll` and the `qml/Qt3D` folder — though nothing imports
   them and the spec names none of them. *Root cause:* that venv still had `PyQt6-3D-Qt6`
   installed (removing a pin does not uninstall a wheel); the QML hook collects the QML modules
   it finds in the installed `PyQt6/Qt6/qml` folder, and their plugins pull their DLLs in.
   *Fix:* the before / after bundles were built in ONE clean environment synced from each tree's
   lock (`uv sync --locked`), which is what CI and the release do; after pulling this change,
   re-sync a development venv (`uv sync --locked …`, ogp-build-and-run) before building locally.
   *Lesson:* judge a bundle built from a locked environment; a dev venv's bundle answers what
   the dev venv holds.

## 11.5 Community and Governance

**Feature Requests**: Open to community input, pivots, and voting. The goal is to avoid a dead project — community engagement is welcome.

**Contribution Model**:
- GitHub Issues for bug reports and feature requests
- Pull requests welcome with review process
- [CONTRIBUTING.md](../../CONTRIBUTING.md) owns setup, testing, documentation, and draft-PR review requirements (issue #417, ADR-051). The original audit snapshot retains the finding as it existed at audit time.
- PRs run tests, full-tree ruff, Bandit HIGH, secrets scan, context parity, locked-dependency checks, platform type baselines and package coverage floors. The #399 protection payload makes the existing and dependency/type checks required for administrators too; master enforcement is active and independently verified. Coverage is initially not required by the GitHub setting.

Community policies now live in root CODE_OF_CONDUCT.md, SECURITY.md, and ACCESSIBILITY.md.
Private vulnerability reporting is enabled. Conduct reports go privately to GitHub Support,
not directly to the maintainer. No contact email or private Discussion channel is promised.
Repository wiki sources and manual publication follow `docs/wiki/README.md`; publication
and GitHub community-profile recognition remain pending owner review and merge.

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


### Registered strings are not the source inventory (#496)

**Require every live key in every registered locale, in both directions.** Review of
#495 found a stale source template could pass the German-only unfinished-value test.
Fresh standard extraction found existing German omissions; an AST audit then identified
helper/table sources that standard extraction missed. Bundled plant common names were
also live sources and had to be retained, not marked retired with the rest of the extras.

The old compiler additionally accepted nonempty unfinished translations, turned empty
targets into source fallback and emitted vanished entries. Six targeted regressions
failed first. Shared strict parsing now refuses those targets and excludes retired
records. Context/key, formatting and compiled lookup validation are independent of
catalog counts. A companion explanation also assumed every non-English locale was
German; the explicit German selection now preserves English fallback for other locales.

Pinned by `tests/unit/test_translation_gate.py`, `tests/integration/test_translation_gate.py`
and the source/binary check in `tests/unit/test_i18n.py`. The lesson is that a gate must
derive its required set independently from the artifacts it validates. Unwrapped UI
text and linguistic quality remain separate review obligations; plural input fails
closed until the singular compiler gains tested support.

Independent review reproduced four further blind spots: keyword helper calls, unmarked
members of marked tables, discarded dynamic disambiguation, and a receiver's real Qt
context. The offset tool called `CanvasView.tr()` through its view, but extraction had
assigned `OffsetTool`; a real German status-message regression exposed the mismatch.
The tool now uses explicit `CanvasView` translation calls. Complete display fields and
values are selected from production tables, helper calls bind their source argument,
dynamic consumers retain comments, and unresolved receivers/helper imports fail closed.

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

- **Two autouse fixtures, one merely depending on the other, are an atomicity claim with
  no coverage** (issue #509, 18 October 2026). `tests/conftest.py` wiped every settings
  key in `_reset_app_settings` and wrote `KEY_AGENT_API_ENABLED = False` in a second
  fixture that merely *depended* on the first. Between the two there was a real instant
  in which the key did not exist at all, so a read returned the production default
  (`DEFAULT_AGENT_API_ENABLED = True`) and the port read 8765. A `GardenPlannerApp` from
  an earlier test arms `QTimer.singleShot(1500, self._maybe_start_agent_api)`, and a
  timer landing in that window started a **real** `AgentApiServer`; two workers doing
  that collided with `OSError: [Errno 10048]`. The window was always there — serial runs
  simply made it microseconds wide against a 1500 ms timer — and it is the same shape as
  the Welcome-dialog entry in the same conftest, where a per-test settings write lost a
  race with a 500 ms timer and the fix was to patch the **method** instead. Two further
  facts close it here: `singleShot` is handed the **bound method**
  `self._maybe_start_agent_api`, which PyQt auto-disconnects when the receiver is
  destroyed, so a fixture that destroys each test's widgets cancels the pending timer
  outright; and the write belongs **inside** the wipe, so there is no instant to lose.
  **Lesson: order a fixture's dependencies carefully and you have documented a gap, not
  closed it; a default of `True` behind an absent key is a loaded weapon the moment
  anything is deferred.** Also: `QSettings.value(key, default)` returns the raw QVariant,
  so `setValue(key, False)` reads back as the **string** `'false'` — a tripwire asserting
  `value is not True` passes for that string *and* for the absent key, which is exactly
  the state it exists to catch. Read it the way the product does, `type=bool`.

- **A test that writes into the git working tree is unsafe under any scheduler, and
  serial execution hides it** (issue #509, 18 October 2026). `test_gate_commands.py`'s
  secret-checker canary staged `scripts/_canary_<tag>.py` in the **real** repository,
  scanned, then unstaged and deleted — the only test in the suite that mutated shared
  state. `test_settings_chokepoint.py` globs that same tree (`root.rglob("*.py")`) and
  reads what it found, and those are two moments: under `pytest -n 8` one worker's
  `rglob` could list the canary inside the other worker's write-to-unlink window and die
  with `FileNotFoundError` on the read — three failures in one run — while the same window
  let the canary's own file-wide scan read a *sibling worker's* staged canary and report a
  credential that was never committed anywhere. #507 separately found that an interrupted
  run left the canary staged and the next `git commit -a` published it (a one-line canary
  really was committed on PR #507). The fix is not a scheduler: the canary is now staged
  in a throwaway `git init`-ed repo under `tmp_path`, so nothing outside the temp directory
  is created, staged or deleted even if the process dies mid-test — which makes #507's
  hazard structurally impossible rather than hardened. **Lesson: `@pytest.mark.xdist_group`
  would have hidden this and left the two-concurrent-pytest-process case (the 2026-08-17
  incident that made `TEST_APPLICATION` per-PID) exactly as dangerous; and a hazard that
  exists only under a scheduler is usually a hazard that exists without one too.**

- **`pytest-timeout`'s per-test bound is necessary but not sufficient for a Qt suite,
  and asking the OS for a free port is not a reservation** (issue #509, 18 October 2026).
  Two distinct time hazards, both found the hard way. First, ten test files each carried
  their own copy of `_free_port()` — `bind(("127.0.0.1", 0))`, read the port, **close the
  socket** — and the caller then binds it, so the port is free in name only. Serially the
  window is microscopic; with `-n auto` on 20 workers it is not, and the measured failure
  was `RuntimeError: Agent API server failed to start`, because uvicorn's own
  `create_server` hit `OSError: [Errno 10048]` after the pre-bind socket check had already
  passed. Two `-n 8` runs gave 2 failures and 1 failure, so **capping the worker count would
  not have addressed it, only lowered the odds** — the fix is a retry, in one shared helper,
  because losing that race is inherent to asking the OS for a port and then releasing it.
  That helper retries `PortInUseError` and the exact string
  `"Agent API server failed to start"`, and re-raises every other `RuntimeError`
  immediately: a retry that swallows real product defects is worse than the flake it was
  written to remove.
  Second, and **this correction is itself the lesson**: an earlier draft of this entry
  claimed "`--cov` and the perf tests are mutually exclusive - the repaint budget fails at
  **20.29 ms against a 16.70 ms budget** under tracing ... so the `Coverage` job has been
  measuring something it cannot gate". Both halves were wrong, and the error is the one this
  section exists to prevent. `tests/perf/test_nfr_budgets.py:56-57` reads
  `_IS_CI = os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"` and `FRAME_BUDGET_MS = 50.0 if _IS_CI else 16.7`, so on CI
  the budget is **50 ms**. The 20.29 ms was measured **here**, against the **local** 16.7 ms
  budget, and was generalised to a configuration nobody ran - and `gh run view 39076508170`
  records master's `Coverage` job **succeeded** at `412f01bd`. One variable, both ways, same
  file: `CI=true` -> 6 passed; unset -> 1 failed.
  **Lesson: a measurement taken against one configuration says nothing about another.**
  **Lesson: a number that arrives from a reviewer's report is still a number you did not
  take - the same discipline applies to your own review round.**
  **Lesson: a missing `finally` around a side effect is a correctness bug and an unbounded
  retry loop is a hang; both are worth catching by asking what a helper swallows, not what
  it returns.**

### Timeline growth must change the rendered sprite, not only its collectors (#315)

The existing 3D/shadow collectors read SimClock.plan_date, but CircleItem's sprite
resolver read date.today. Tagged evidence recorded `[F4-GROWTH] sprite_day=2026-10-19
plan_day=2025-06-01` and the same sprite day after scrubbing to 2030, with a stack
through scene rendering. The resolver now reads the scene's shared date and a date
refresh invalidates DeviceCoordinateCache. The mature footprint remains unchanged.
The regression compares rendered canopy pixels at two dates. Its first sampler was
itself wrong: the spacing ring's translucent fill covered the sampled region at both
dates (40000/40000 pixels), so the final sampler explicitly disables that overlay.
PDF text extraction may break lines between glyphs despite correct rendered layout;
whitespace is normalized for content checks and rendered pages are inspected.


### A live sun-map preview is not a current measurement or an export (#315)

The former on-demand map intentionally disappeared on date changes. Retaining its
pixels for the combined timeline requires three separate identities: desired inputs,
in-flight snapshot, and the snapshot whose image is actually displayed. The launched
worker's computed_day changes before its result arrives, so it cannot label the old
image. displayed_snapshot is updated only on accepted success; stale measurements
are cleared immediately and cannot feed badges. The preview remains visibly dated.

Export readiness must also guard the no-map case: a document can be replaced between
two API GUI hops even when its exposure Future is already ready. SunExportGate checks
generation (zero before the first replacement), plan revision and wall time immediately
before writing. Its waits happen outside the API bridge call; cancellation and timeouts
write nothing. The pending-Future test, map date/late-result tests and guarded GUI/API
export tests pin these distinctions. Shutdown is idempotent, including a second call
after QObject teardown; the test fixture releases its controlled workers on cancel.


### Derived lifetime visibility must not announce a plan edit (#315)

The first native Quick3D review found ten regrowth snapshots in 156–172 ms when
ten date steps crossed a planting/removal boundary; the same-presence control
produced none. Tagged stacks traced Qt's ItemVisibleHasChanged through the plan
revision signal to the controller's immediate edit path, bypassing its 500 ms
date throttle. refresh_timeline now scopes only those visibility announcements
as derived runtime state (restored in finally). Manual visibility, layer commands
and lifetime undo/redo still announce edits. Separate-event-loop boundary tests
pin both halves. The identical probe reads zero extra snapshots/revisions after
the fix and the existing clock's trailing update produces the final state.

Translated layout also needs its own evidence: German's first three control
groups missed the available 800-pixel content width by two pixels despite English
passing. The actual group hints, not a guessed Qt cache bug, explained the third
row. Narrow sliders now leave translated text headroom; native-widget captures
and two-locale regressions supplement the English geometry tests.


### Debounce collection and own abandoned export calls (#315)

Worker-count tests missed 154 synchronous whole-scene captures during one 150-item
layer command. Live-map notifications now dirty cheap state; collection occurs once
after debounce, and requirement-only changes restore cached measurements. The bulk
command regression asserts both synchronous and eventual capture counts.

A completed map Future also masked a real-dialog Cancel in the same event turn.
Cancellation now wins independently. Generic bridge timeouts leave queued calls in
Qt, so an abandoned begin could acquire a permanent animation lease and an abandoned
render could write later. Locked operation state refuses late admission and releases
leases through queued Qt cleanup. Fail-first tests withhold actual bridge delivery
until after timeout, then assert resumed animation and absent output files.
