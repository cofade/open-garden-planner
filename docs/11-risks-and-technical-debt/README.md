# 11. Risks and Technical Debt

Dated audit snapshots: [audit-2026-10.md](audits/2026-10/audit-2026-10.md) (numbers: `audit-2026-10-metrics.json`, re-run with `scripts/audit_metrics.py`; findings tracked in epic #392). §11.3 is the living register (ADR-047). §11.4 indexes the pitfall catalogue (ADR-061).

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
remained open for a separately reviewed backend/lock update — #571 is that update (below). The CI `Dependencies` matrix job
(Linux and Windows) now runs `pip-audit` against the committed lock export
(`uv export --locked --all-extras --group build`) on every push, with this single advisory
recorded as `--ignore-vuln PYSEC-2026-3447`; a new advisory fails the job. Both platforms
run it because pip-audit evaluates markers for the running interpreter.

**Update 2026-10-24 (#571, #572).** The job failed `master` (`50324280`) on
[GHSA-xmj3-9gf7-h52w](https://github.com/advisories/GHSA-xmj3-9gf7-h52w) (setuptools
< 84.1.0) and a re-run on six `filelock` 4.2.0 advisories (dev extra only). The build
group pins setuptools **84.1.0** and the lock carries filelock 4.2.4: `pip-audit` finds
no known vulnerability, and the `PYSEC-2026-3447` waiver above ended with it (84.1.0
contains the 83.0.0 fix). CI waives nothing; a new waiver is justified here and named in
`test_dependency_governance.py::WAIVERS`. Details and the frozen re-verification: §8.11.
Lesson: PF-CI-12.

Automated dependency PRs remain unavailable: Dependabot's uv ecosystem image ships uv
**0.12.19** (`uv/Dockerfile` in dependabot-core, read 2026-10-13) while this project pins
`uv ==0.12.23`, and a `required-version` mismatch makes the updater exit before doing any
work. `.github/workflows/dependency-review.yml` is the documented monthly manual fallback:
it reports what `uv lock --upgrade` would change into one issue and never writes to the
repository. See ADR-050's A2 addendum and `docs/07-deployment-view` §7.4.

## 11.3 Technical Debt

The living register (ADR-047). Every row has a status; P0/P1 rows link their issue, P2/P3 rows link their thematic bundle issues; all 73 findings and current evidence are reconciled in [audit-2026-10-reconciliation.md](audits/2026-10/audit-2026-10-reconciliation.md) (epic #392). Rows come from the dated audit snapshots ([audit-2026-10.md](audits/2026-10/audit-2026-10.md), Top-25 = TD-009…TD-033, plus TD-034 re-raised by the Windows check; the long tail stays in the snapshot's appendix), or from an ADR's evidence (TD-035 to TD-037, ADR-048), whose row links the work package that carries it instead of the audit checklist (a P0/P1 row links its own issue). Re-measure with `scripts/audit_metrics.py`. Status is `open` (with a note where useful), `fixed (#PR)`, `accepted (ADR-0xx)`, `closed (reason)` or `superseded (by …)`; historical rows TD-001…TD-008 carry an issue only where one exists. Never delete a row; a resolved row says so.

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
| TD-025 | Security (data) | NaN/Infinity accepted at the .ogp boundary: NaN canvas breaks render_canvas_image, non-finite values are re-saved as invalid JSON | P2 / S | fixed (#487) | #453 | audit-2026-10 AUD-041 |
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
| TD-038 | Constraint presentation | Repeated type presentation dispatch; now one immutable enum-complete panel descriptor with independent rendering and localization guards | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-012; ADR-012 addendum; [A5 evidence](audits/2026-10/audit-2026-10-a5-evidence.md) |
| TD-039 | Solver evidence | Selection-scoped historical mutation gaps; fresh sample and geometric oracles, including corrected all-pinned false convergence | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-023; ADR-012 addendum; [A5 evidence](audits/2026-10/audit-2026-10-a5-evidence.md) |

## 11.4 Known Development Pitfalls

Permanent IDs survive retirement (ADR-061). [Pitfalls](pitfalls/) hold rules and test pins; [archives](archive/) preserve narratives. An unpinned entry explains why.

| Area | Index | Scope | Detailed Entries |
|---|---|---|---|
| CAN | [Canvas Geometry Index](pitfalls/index/01-canvas-geometry.md) | canvas geometry, painting and export | [01-canvas-geometry.md](pitfalls/01-canvas-geometry.md) |
| LIF | [Lifecycle & Threads Index](pitfalls/index/02-lifecycle-threads.md) | lifecycle, threads, timers and signals | [02-lifecycle-threads.md](pitfalls/02-lifecycle-threads.md) |
| PER | [Persistence & Undo Index](pitfalls/index/03-persistence-undo-layers.md) | persistence, undo and layers | [03-persistence-undo-layers.md](pitfalls/03-persistence-undo-layers.md) |
| UI | [UI Panels & Forms Index](pitfalls/index/04-ui-panels-dialogs.md) | panels, dialogs, toolbars and forms | [04-ui-panels-dialogs.md](pitfalls/04-ui-panels-dialogs.md), [04b-ui-forms.md](pitfalls/04b-ui-forms.md) |
| I18 | [i18n Index](pitfalls/index/05-i18n.md) | translation and display strings | [05-i18n.md](pitfalls/05-i18n.md) |
| CI | [CI & Supply Chain Index](pitfalls/index/06-ci-release-supply-chain.md) | CI, release and supply chain | [06-ci-release-supply-chain.md](pitfalls/06-ci-release-supply-chain.md) |
| TST | [Test Suite Hygiene Index](pitfalls/index/07-test-suite-hygiene.md) | test-suite hygiene and isolation | [07-test-suite-hygiene.md](pitfalls/07-test-suite-hygiene.md) |
| API | [Agent API & Security Index](pitfalls/index/08-agent-api-security.md) | agent API, MCP and security | [08-agent-api-security.md](pitfalls/08-agent-api-security.md) |
| DOM | [Domain & Solver Index](pitfalls/index/09-domain-solver.md) | domain data, solver and dates | [09-domain-solver.md](pitfalls/09-domain-solver.md) |
| E3D | [3D Engine & Scene Index](pitfalls/index/10-3d-engine-scene.md) | 3D engine and scene. The host's state contract is written down once, in `src/open_garden_planner/ui/view3d/quick3d/lifecycle.py`. | [10-3d-engine-scene.md](pitfalls/10-3d-engine-scene.md) |
| L3D | [3D Look & Ground Index](pitfalls/index/11-3d-look-ground-build.md) | 3D look, ground and build | [11-3d-look-ground-build.md](pitfalls/11-3d-look-ground-build.md) |
| PRC | [Process & Docs Index](pitfalls/index/12-process-and-docs.md) | process and documentation | [12-process-and-docs.md](pitfalls/12-process-and-docs.md) |

### Redirect of legacy numbered IDs

Citations written before ADR-061 used the numbered form. Each resolves through this table. Legacy number 6 named two different entries, so each is listed with its content.

| Legacy | Now | Note |
|---|---|---|
| 11.4.1 | PF-API-19 | Three guards in the wrong place (US-D3.2 final pre-merge review, #374) |
| 11.4.2 | PF-TST-19 | The four bugs a manual pass found that a green suite could not (#377, #380, #373) |
| 11.4.3 | PF-API-20 | Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333) |
| 11.4.4 | PF-API-21 | Review and frozen-client findings in D3.3/D3.4 (#332/#333) |
| 11.4.5 | PF-E3D-04 | Time a stall with a trusted clock before blaming the engine |
| 11.4.6 | PF-UI-21 | dead code path (### heading, README L575) |
| 11.4.6 | PF-DOM-24 | sun self-shadow (## heading, README L1109) |
| 11.4.7 | PF-DOM-22 | A day derived from a UTC instant is not the user's day (Phase 17 L1.0, #385) |
| 11.4.8 | PF-DOM-23 | Guild boundaries found by independent review (F1/F2) |
| 11.4.9 | PF-CAN-18 | A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473) |
| 11.4.10 | PF-CAN-19 | A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass) |
| 11.4.11 | PF-CAN-20 | A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503) |
| 11.4.12 | PF-L3D-01 | A gate the repair itself satisfies is not evidence; a measure must be able to move |
| 11.4.13 | PF-L3D-02 | A bounding box is not a footprint; a closed polyline is a ring; pin everything else before changing shipped behaviour |
| 11.4.14 | PF-E3D-05 | A hash is not equality; float dust is an edit; a bound checked after the work is a report |
| 11.4.15 | PF-E3D-06 | A judge must not ask the suspect; no Qt window predicate is trusted until measured; a Python message handler beside a shown Qt Quick window deadlocks |
| 11.4.16 | PF-E3D-07 | No frame inside a measured loop; wait for a condition, not a duration |
| 11.4.17 | PF-L3D-03 | The L1.5 ground bake: a bound that keeps the topmost N drops what everything stands on |
| 11.4.17 | PF-L3D-04 | The L1.5 ground bake: never point a Texture at a second texture |
| 11.4.17 | PF-CAN-21 | The L1.5 bake's 2D defects: an item states its look once |
| 11.4.18 | PF-L3D-05 | What the looks, the sky and the wind taught (Phase 17 L1.4, #385) |
| 11.4.19 | PF-E3D-08 | What selection, the info card and walk mode taught (Phase 17 L1.8, #385) |
| 11.4.20 | PF-E3D-09 | What the default flip and the removal of Qt 3D taught (Phase 17 L1.9 / L1.10, #385) |

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
