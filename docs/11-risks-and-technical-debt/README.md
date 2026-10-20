# 11. Risks and Technical Debt

Dated audit snapshots: [audit-2026-10.md](audits/2026-10/audit-2026-10.md) (numbers: `audit-2026-10-metrics.json`, re-run with `scripts/audit_metrics.py`; findings tracked in epic #392). §11.3 is the living register (ADR-047).

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
| TD-038 | Constraint presentation | Repeated type presentation dispatch; now one immutable enum-complete panel descriptor with independent rendering and localization guards | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-012; ADR-012 addendum; [A5 evidence](audits/2026-10/audit-2026-10-a5-evidence.md) |
| TD-039 | Solver evidence | Selection-scoped historical mutation gaps; fresh sample and geometric oracles, including corrected all-pinned false convergence | P2 / M | completed; owner acceptance, PR #489; v1.30.4 | #457 | AUD-023; ADR-012 addendum; [A5 evidence](audits/2026-10/audit-2026-10-a5-evidence.md) |

## 11.4 Known Development Pitfalls

Every lesson the project paid for, one entry each. An entry's ID (`PF-<AREA>-<NN>`) is permanent (ADR-061): retired and pointer entries keep theirs. Standing rules live in the numbered files under [pitfalls/](pitfalls/); incident narratives and retired work are verbatim under [archive/](archive/). Each entry names the test that pins it, or says why it has none.

| Area | File | Scope |
|---|---|---|
| CAN | [01-canvas-geometry.md](pitfalls/01-canvas-geometry.md) | canvas geometry, painting and export |
| LIF | [02-lifecycle-threads.md](pitfalls/02-lifecycle-threads.md) | lifecycle, threads, timers and signals |
| PER | [03-persistence-undo-layers.md](pitfalls/03-persistence-undo-layers.md) | persistence, undo and layers |
| UI | [04-ui-panels-dialogs.md](pitfalls/04-ui-panels-dialogs.md) | panels, dialogs and toolbars |
| I18 | [05-i18n.md](pitfalls/05-i18n.md) | translation and display strings |
| CI | [06-ci-release-supply-chain.md](pitfalls/06-ci-release-supply-chain.md) | CI, release and supply chain |
| TST | [07-test-suite-hygiene.md](pitfalls/07-test-suite-hygiene.md) | test-suite hygiene and isolation |
| API | [08-agent-api-security.md](pitfalls/08-agent-api-security.md) | agent API, MCP and security |
| DOM | [09-domain-solver.md](pitfalls/09-domain-solver.md) | domain data, solver and dates |
| E3D | [10-3d-engine-scene.md](pitfalls/10-3d-engine-scene.md) | 3D engine and scene. The host's state contract is written down once, in `src/open_garden_planner/ui/view3d/quick3d/lifecycle.py`. |
| L3D | [11-3d-look-ground-build.md](pitfalls/11-3d-look-ground-build.md) | 3D look, ground and build |
| PRC | [12-process-and-docs.md](pitfalls/12-process-and-docs.md) | process and documentation |

| ID | Rule | Status | Where | Legacy |
|---|---|---|---|---|
| PF-CAN-01 | Canvas item caching, Level of Detail (LOD), and selection handle ghosting (issue #409, TD-034, AUD-056) | retired | [01](pitfalls/01-canvas-geometry.md#pf-can-01) |  |
| PF-CAN-02 | A plant's drawn icon has a fourth independent size, reversing an explicit ADR-037 rejection on the owner's call (issue #299). | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-02) |  |
| PF-CAN-03 | A first cut of this fix shipped a severe, unrendered regression a senior-review pass caught before merge | standing (narrative archived) | [01](pitfalls/01-canvas-geometry.md#pf-can-03) |  |
| PF-CAN-04 | Anchor index on same-type anchors | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-04) |  |
| PF-CAN-05 | Canvas Y-axis flip | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-05) |  |
| PF-CAN-06 | EDGE_* anchor type instability on polygons/polylines | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-06) |  |
| PF-CAN-07 | `scene.render()` with negative-height target rect is empty (PyQt6) | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-07) |  |
| PF-CAN-08 | `ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()` | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-08) |  |
| PF-CAN-09 | QPdfWriter must use `setResolution(72)` before `setPageLayout()` | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-09) |  |
| PF-CAN-10 | `scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins) | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-10) |  |
| PF-CAN-11 | Plant items store center in `boundingRect()`, not in `pos()` | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-11) |  |
| PF-CAN-12 | SVG pattern tiles appear Y-inverted under painter Y-flip | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-12) |  |
| PF-CAN-13 | `QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-13) |  |
| PF-CAN-14 | DXF Y-axis: scene Y is already Y-up, no negation needed | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-14) |  |
| PF-CAN-15 | `painter.drawText()` inside `QGraphicsItem.paint()` renders upside-down on the Y-flipped canvas | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-15) |  |
| PF-CAN-16 | Grid snap silently overrides anchor snap unless `CanvasView.snap_point` short-circuits | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-16) |  |
| PF-CAN-17 | A pixmap blitted in item-local coordinates is upside-down on the canvas — and the plant sprites hid it for eight months | standing | [01](pitfalls/01-canvas-geometry.md#pf-can-17) |  |
| PF-CAN-18 | A frame sized by a polygon's most expensive vertex, and one look rule for item copies (#470/#472/#473) | standing (narrative archived) | [01](pitfalls/01-canvas-geometry.md#pf-can-18) | 11.4.9 |
| PF-CAN-19 | A fill colour nobody could see, and the round-trip test that asserted the wrong thing (#502, from #470/#472/#473's manual pass) | standing (narrative archived) | [01](pitfalls/01-canvas-geometry.md#pf-can-19) | 11.4.10 |
| PF-CAN-20 | A dead optimisation is not a latent feature, and a negative pin can stop noticing (#503) | standing (narrative archived) | [01](pitfalls/01-canvas-geometry.md#pf-can-20) | 11.4.11 |
| PF-CAN-21 | An item states its look once | standing (narrative archived) | [01](pitfalls/01-canvas-geometry.md#pf-can-21) |  |
| PF-LIF-01 | A teardown that gives up quietly turns into a crash somewhere else, and the "somewhere else" is the only symptom you get. | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-01) |  |
| PF-LIF-02 | A Qt dialog must not synchronously join a network worker during `closeEvent()`. | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-02) |  |
| PF-LIF-03 | A private item-tracking list must be dropped at the SAME chokepoint that destroys the items it tracks, not just at the one call site that happened to crash — and an audit that finds one sibling case must check for others in the same class (issue #337, shipped 2026-08-21 in v1.27.2 via PR #339). | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-03) |  |
| PF-LIF-04 | A background `QThread` with a parent `QObject` aborts the app with `0xC0000409` (`QThread: Destroyed while thread is still running`) on window close (issues #480, #483). | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-04) |  |
| PF-LIF-05 | A `scene.changed` slot that touches a `QTimer` must guard against the C++ object being torn down | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-05) |  |
| PF-LIF-06 | A slot connected to an *application*-global signal (`QApplication.focusChanged`) outlives its widget and must be teardown-safe | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-06) |  |
| PF-LIF-07 | Qt silently drops the mouse grab on `ItemIgnoresTransformations` handles between events (PyQt6) | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-07) |  |
| PF-LIF-08 | `QGraphicsScene.changed` only fires on geometry/visibility, not on Python attribute mutations | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-08) |  |
| PF-LIF-09 | `QGraphicsScene.changed` feedback loops: a slot driven by `scene.changed` that itself mutates the scene runs forever while the app is idle | standing (narrative archived) | [02](pitfalls/02-lifecycle-threads.md#pf-lif-09) |  |
| PF-LIF-10 | Subclassing `QWebEnginePage` to siphon `javaScriptConsoleMessage` hard-crashes the process | standing | [02](pitfalls/02-lifecycle-threads.md#pf-lif-10) |  |
| PF-PER-01 | Two divergent item serializers create silent data-loss gaps on clipboard operations; unify under one chokepoint. | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-01) |  |
| PF-PER-02 | Opening a corrupt plan must never contaminate document identity or wipe existing recovery files. | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-02) |  |
| PF-PER-03 | Missing or corrupt external assets must load as placeholders to survive save cycles. | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-03) |  |
| PF-PER-04 | Dimension line updates after undo/redo | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-04) |  |
| PF-PER-05 | Plants stack behind beds when both share a layer's default z | retired | [03](pitfalls/03-persistence-undo-layers.md#pf-per-05) |  |
| PF-PER-06 | Excel reads UTF-8 CSV as Latin-1 unless a BOM is present | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-06) |  |
| PF-PER-07 | A panel that writes item `metadata` directly reaches neither `scene.changed` nor `stack_changed` — every derived overlay goes stale | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-07) |  |
| PF-PER-08 | Layer subsystem: panel is a pure view; ALL mutations go through undoable commands | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-08) |  |
| PF-PER-09 | Undoable layer preconditions must be revalidated on redo | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-09) |  |
| PF-PER-10 | Undo/redo must dirty the document — and so must every "already-applied" edit; route them all through one chokepoint | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-10) |  |
| PF-PER-11 | A bug that is exactly 0 at the default value hides forever — and a `Callable` parameter is where two implementations of one behaviour go to drift | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-11) |  |
| PF-PER-12 | Same-layer stacking inverted on every save/load | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-12) |  |
| PF-PER-13 | Clipboard-pasted items were layer-less | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-13) |  |
| PF-PER-14 | Lesson (design review, #338): a refresh that writes model state breaks snapshot-based undo.: The stacking-order design w | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-14) |  |
| PF-PER-15 | A same-scene project load can leave stale callouts/curves, and UUID lookup then turns a delete into a false success (issue #353, 2026-09-24). | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-15) |  |
| PF-PER-16 | A finite float is not a safe Qt geometry input, and JSON normalization can turn hostile Infinity/NaN into an apparently valid default (issue #355, 2026-09-24). | standing | [03](pitfalls/03-persistence-undo-layers.md#pf-per-16) |  |
| PF-PER-17 | A widget that rewrites a displayed date for "readability" corrupted persisted data. | standing (narrative archived) | [03](pitfalls/03-persistence-undo-layers.md#pf-per-17) |  |
| PF-PER-18 | A1 numeric, download and settings boundaries (#453) | standing (narrative archived) | [03](pitfalls/03-persistence-undo-layers.md#pf-per-18) |  |
| PF-UI-01 | A connectivity "Test" probe must fetch the smallest page the API allows, and a swallowed non-credential failure must not be relabeled "check your credentials" (issue #294). | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-01) |  |
| PF-UI-02 | A variable-width widget in a `QToolBar`'s flow reflows Qt's overflow-extension popup and shuffles neighbouring buttons | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-02) |  |
| PF-UI-03 | Sidebar list panels must store item *ids*, not live `QGraphicsItem` refs, and defer the selection | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-03) |  |
| PF-UI-04 | An enum `QComboBox` that excludes `UNKNOWN` misrepresents missing data as its first option | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-04) |  |
| PF-UI-05 | Context-menu wiring must cover all bed-shape item types | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-05) |  |
| PF-UI-06 | Two-tab dialog: OK must not trigger entry-tab validation when user is on History tab | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-06) |  |
| PF-UI-07 | Two-tab dialog: caller must not create a new record when user clicked OK from History tab | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-07) |  |
| PF-UI-08 | `mousePressEvent` monkey-patch must return None, not the result of `openUrl()` | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-08) |  |
| PF-UI-09 | `ThemeColors.get_colors(ThemeMode.SYSTEM)` ignores the user's theme choice | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-09) |  |
| PF-UI-10 | Bed-only features must NOT be hand-coded into each shape item | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-10) |  |
| PF-UI-11 | `QLineEdit` ignores Return — Enter bubbles to the canvas and finalizes the active tool | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-11) |  |
| PF-UI-12 | Dynamic Input overlay must freeze while the user is typing | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-12) |  |
| PF-UI-13 | Properties panel updates incrementally — rebuild only on a genuine selection/structure change | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-13) |  |
| PF-UI-14 | Free-text property fields commit on a debounce, not per keystroke — and not on focus-out alone | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-14) |  |
| PF-UI-15 | QSvgRenderer paints `currentColor` BLACK — never feed a contract icon SVG to it directly | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-15) |  |
| PF-UI-16 | A `statusBar().showMessage()` set while a modal dialog is open is invisible — and a transient status blip is the wrong channel for a startup reminder | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-16) |  |
| PF-UI-17 | A `QToolBar` added to the main window MUST carry a unique `objectName` — an empty one does not merely warn, it *aliases | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-17) |  |
| PF-UI-18 | A toolbar carrying essential tools must not be user-hideable — `QMainWindow`'s free context menu is a trap with no way back | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-18) |  |
| PF-UI-19 | Google's satellite tile `<img>`s taint any canvas — html2canvas-style capture is structurally impossible, and DOM tile URLs leak the API key | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-19) |  |
| PF-UI-20 | `QDialog.accept()` hides the window — a live harness that watches for the accepted result can see the whole app exit first | standing | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-20) |  |
| PF-UI-21 | A silently-dead code path is a hiding place — fixing it *publishes* its content | standing (narrative archived) | [04](pitfalls/04-ui-panels-dialogs.md#pf-ui-21) | 11.4.6 |
| PF-I18-01 | Translated row templates can still contain English object labels | standing | [05](pitfalls/05-i18n.md#pf-i18-01) |  |
| PF-I18-02 | `test_german_ts_has_no_unfinished` does NOT catch hardcoded English strings in source code | retired | [05](pitfalls/05-i18n.md#pf-i18-02) |  |
| PF-I18-03 | `tr()` + `.format()` is a silent no-op on a Qt positional `%N` literal | standing | [05](pitfalls/05-i18n.md#pf-i18-03) |  |
| PF-I18-04 | A repeated top-level key in the `TRANSLATIONS` literal of `scripts/fill_translations.py` silently shadows the earlier block, and the i18n gate cannot see the strings it drops | standing | [05](pitfalls/05-i18n.md#pf-i18-04) |  |
| PF-I18-05 | A shared, Qt-free service that renders a bilingual data field must resolve the active UI language explicitly; a `lang="en"` default is a silent English leak | standing | [05](pitfalls/05-i18n.md#pf-i18-05) |  |
| PF-I18-06 | Command-description `{property}` fragments must be registered under the "Commands" i18n context | standing | [05](pitfalls/05-i18n.md#pf-i18-06) |  |
| PF-I18-07 | The canonical translation workflow is `fill_translations.py` alone — running `pylupdate6` over the source tree churns the entire `.ts` and marks whole contexts "vanished"/"unfinished" | standing | [05](pitfalls/05-i18n.md#pf-i18-07) |  |
| PF-I18-08 | Registered strings are not the source inventory (#496) | standing | [05](pitfalls/05-i18n.md#pf-i18-08) |  |
| PF-CI-01 | Attribute frozen code from collected files, not only declared dependencies | standing | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-01) |  |
| PF-CI-02 | A stale `*.egg-info` on `sys.path` silently shrinks anything derived from installed metadata (#454, 2026-10-13). | standing | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-02) |  |
| PF-CI-03 | A source checkout's `.env` is not automatically present in a packaged build, and a credential setting must not become a project secret. | standing | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-03) |  |
| PF-CI-04 | A windowed PyInstaller build launched with no console has `sys.stdout is None`, and uvicorn's default log config dereferences it — the Agent API was dead in every released exe (issue #291, closed). | standing | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-04) |  |
| PF-CI-05 | Release workflow race condition with chore commits | standing (narrative archived) | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-05) |  |
| PF-CI-06 | PyInstaller-frozen exe fails to load Qt3D DLLs on a `PyQt6-3D-Qt6` ↔ `PyQt6-Qt6` micro-version mismatch | retired | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-06) |  |
| PF-CI-07 | Never default a file dialog into the install directory; never let the uninstaller wipe it blind | standing (narrative archived) | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-07) |  |
| PF-CI-08 | A non-critical CI job that fails permanently is indistinguishable from one that does nothing — and it trains everyone to scroll past the Actions tab | retired | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-08) |  |
| PF-CI-09 | CI/release hardening: locked metadata also contains the application version | standing | [06](pitfalls/06-ci-release-supply-chain.md#pf-ci-09) |  |
| PF-TST-01 | Hold a worker in flight when proving GUI responsiveness | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-01) |  |
| PF-TST-02 | Within-day simulation tests must fix time as well as date | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-02) |  |
| PF-TST-03 | Every placeable graphics item must be covered by serializer round-trip matrix tests. | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-03) |  |
| PF-TST-04 | A cleanup fixture that runs in the wrong ORDER is not a cleanup — and a plausible mechanism is not a mechanism. | standing (narrative archived) | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-04) |  |
| PF-TST-05 | A test that exercises a real external binary will exercise it on the developer's machine. | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-05) |  |
| PF-TST-06 | `QSettings.setDefaultFormat()` / `setPath()` are process-global statics Qt never reverts — never call them from a test | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-06) |  |
| PF-TST-07 | A full-app integration test that outlives ~500 ms must silence the startup Welcome dialog — its modal `exec()` blocks pytest-qt forever | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-07) |  |
| PF-TST-08 | `UiStateStore` builds its own `QSettings`, so it escapes the conftest isolation — full-app tests read *and overwrite* the developer's real window state | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-08) |  |
| PF-TST-09 | The test suite wrote into the developer's real plant library — isolating one store is not isolating the process | standing (narrative archived) | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-09) |  |
| PF-TST-10 | A "nobody may use X" gate belongs in the AST, not in a regex — and it must be falsified twice | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-10) |  |
| PF-TST-11 | The Welcome-dialog hang above was re-hit on 2026-08-17 (Package 3a) — because its fix was per-file, and only three of 34 app-building test files had it. | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-11) |  |
| PF-TST-12 | A "byte-deterministic" PNG gate is a zlib gate in disguise — compare decoded pixels, never file bytes | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-12) |  |
| PF-TST-13 | A hidden wrap seam is located by measuring `\|row0 − row255\|` per column, not by theorising about the layout | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-13) |  |
| PF-TST-14 | A debounce `QTimer` armed by a test outlives the test — and a timer slot that can open a modal `QMessageBox` becomes a heap-corruption crash in whatever test runs 500 ms later | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-14) |  |
| PF-TST-15 | JavaScript `let` declarations never land on `window` — verification JS that reads `window.map`/`window.bridge` from a page written with top-level `let` returns `undefined` forever, even when the page state is perfectly healthy | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-15) |  |
| PF-TST-16 | A real short-interval `QTimer` racing pytest-qt's `waitUntil` loop segfaults the linux-offscreen suite — drive timer-handler coverage by emitting the signal instead | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-16) |  |
| PF-TST-17 | JS-side guards comparing a NUMBER token with its STRING form silently eat every capture report — the capture "times out" while every test is green | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-17) |  |
| PF-TST-18 | A single wall-clock CI sample cannot distinguish a scheduler spike from a spatial-index regression (issue #354, 2026-09-24). | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-18) |  |
| PF-TST-19 | The four bugs a manual pass found that a green suite could not (#377, #380, #373) | standing (narrative archived) | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-19) | 11.4.2 |
| PF-TST-20 | `qtbot.addWidget` closes a widget, and closing is not deleting | standing (narrative archived) | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-20) |  |
| PF-TST-21 | **Two autouse fixtures, one merely depending on the other, are an atomicity claim with | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-21) |  |
| PF-TST-22 | **A test that writes into the git working tree is unsafe under any scheduler, and | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-22) |  |
| PF-TST-23 | **`pytest-timeout`'s per-test bound is necessary but not sufficient for a Qt suite | standing | [07](pitfalls/07-test-suite-hygiene.md#pf-tst-23) |  |
| PF-API-01 | A CLI's SUCCESS output needs the same treatment as its failure output. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-01) |  |
| PF-API-02 | An INDETERMINATE answer must never select the more DANGEROUS option. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-02) |  |
| PF-API-03 | "Unparseable" and "empty" are different failures, and only one of them is dangerous. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-03) |  |
| PF-API-04 | A refusal nobody asked for is a capability removal wearing a safety hat. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-04) |  |
| PF-API-05 | Verify the installed binary's CAPABILITY, not the product's documented interface — and check that a stub cannot stand in for a real binary. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-05) |  |
| PF-API-06 | A refusal must leave the filesystem exactly as it found it — so take the backup as late as possible. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-06) |  |
| PF-API-07 | "Unparseable" and "parseable but the wrong shape" are different failures and must not share a policy. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-07) |  |
| PF-API-08 | A "best-effort, never raises" reader must own its failure type — and, more importantly, must not enumerate. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-08) |  |
| PF-API-09 | A guard checked on some paths is not a guard. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-09) |  |
| PF-API-10 | A required dataclass field is a contract with an explicit consumer list, not a struct you can extend freely. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-10) |  |
| PF-API-11 | A tool's declared return model is part of its contract, and testing the provider is not the same as testing the tool. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-11) |  |
| PF-API-12 | A third-party config file is a *superset* of the format you assume, and fail-closed turns that into a dead end. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-12) |  |
| PF-API-13 | Never re-serialise a file you do not own. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-13) |  |
| PF-API-14 | A CLI's default scope can write into the user's project directory. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-14) |  |
| PF-API-15 | At a trust boundary that ingests untrusted files, catch `Exception` at the ingestion seam — do NOT enumerate exception families | standing | [08](pitfalls/08-agent-api-security.md#pf-api-15) |  |
| PF-API-16 | Agent API described the compass backwards (issue #267, fixed) | standing (narrative archived) | [08](pitfalls/08-agent-api-security.md#pf-api-16) |  |
| PF-API-17 | **Agent creation must share the loader's construction path and its undo | standing | [08](pitfalls/08-agent-api-security.md#pf-api-17) |  |
| PF-API-18 | A stable geometry API must read live transforms, and a constrained write must refuse rather than half-run the solver | standing | [08](pitfalls/08-agent-api-security.md#pf-api-18) |  |
| PF-API-19 | Three guards in the wrong place (US-D3.2 final pre-merge review, #374) | standing | [08](pitfalls/08-agent-api-security.md#pf-api-19) | 11.4.1 |
| PF-API-20 | Six defects a single package found, and what each one was really about (US-D3.3 #332 + US-D3.4 #333) | standing (narrative archived) | [08](pitfalls/08-agent-api-security.md#pf-api-20) | 11.4.3 |
| PF-API-21 | Review and frozen-client findings in D3.3/D3.4 (#332/#333) | standing | [08](pitfalls/08-agent-api-security.md#pf-api-21) | 11.4.4 |
| PF-API-22 | A product surface can be "protected" by a library default nobody pinned. | standing | [08](pitfalls/08-agent-api-security.md#pf-api-22) |  |
| PF-DOM-01 | No free solver variables does not imply feasibility | standing | [09](pitfalls/09-domain-solver.md#pf-dom-01) |  |
| PF-DOM-02 | A graph row can conceal a no-op geometry path (#406, 2026-10-12). | standing | [09](pitfalls/09-domain-solver.md#pf-dom-02) |  |
| PF-DOM-03 | `search()` and `get_by_id()` returned structurally different field sets for the same provider, and nothing wired the richer one into the selection flow (issue #297). | standing | [09](pitfalls/09-domain-solver.md#pf-dom-03) |  |
| PF-DOM-04 | This shipped over seven senior-review rounds, each finding a real, live-reproducible defect in the previous round's own fix | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-04) |  |
| PF-DOM-05 | Takeaway: this project's `.env` has working credentials for Trefle, Perenual, and Permapeople. A live call costs thirty | standing | [09](pitfalls/09-domain-solver.md#pf-dom-05) |  |
| PF-DOM-06 | Update (manual testing, 2026-08-10): a defect one layer above the seven-round fix, invisible to every review round.: The | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-06) |  |
| PF-DOM-07 | `dict.get(key, default)` is not None-safe, and it silently dropped API search results (issue #296). | standing | [09](pitfalls/09-domain-solver.md#pf-dom-07) |  |
| PF-DOM-08 | Available API fields silently discarded, independent of the crash above (issue #296). | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-08) |  |
| PF-DOM-09 | Closed (#228): task status now has a single write-path | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-09) |  |
| PF-DOM-10 | Writing `metadata["plant_species"]` does not repaint the canvas, and a manual `spacing_radius_cm` override masks the database value | standing | [09](pitfalls/09-domain-solver.md#pf-dom-10) |  |
| PF-DOM-11 | 3-anchor constraints not solved on add | standing | [09](pitfalls/09-domain-solver.md#pf-dom-11) |  |
| PF-DOM-12 | Live-drag projection tolerance must be sub-pixel | standing | [09](pitfalls/09-domain-solver.md#pf-dom-12) |  |
| PF-DOM-13 | `ShoppingListItem.id` must encode the display unit when units auto-promote | standing | [09](pitfalls/09-domain-solver.md#pf-dom-13) |  |
| PF-DOM-14 | Two surfaces that share a status store must derive the key identically — reuse the canonical `species_key()` | standing | [09](pitfalls/09-domain-solver.md#pf-dom-14) |  |
| PF-DOM-15 | A handler fed a canonical `species_key` must match on the canonical key, not a raw name — and a "navigate by species" channel must also handle unkeyed targets | standing | [09](pitfalls/09-domain-solver.md#pf-dom-15) |  |
| PF-DOM-16 | A derived child must be recomputed from its owner, never re-projected from its own current state | standing | [09](pitfalls/09-domain-solver.md#pf-dom-16) |  |
| PF-DOM-17 | A derived texture's orientation is gravity-relative, and naming a half "left" does not make it the downhill side | standing | [09](pitfalls/09-domain-solver.md#pf-dom-17) |  |
| PF-DOM-18 | Corollary - `species_key` is a function, not a field.: The first draft of `suggest_succession` | standing | [09](pitfalls/09-domain-solver.md#pf-dom-18) |  |
| PF-DOM-19 | The GUI anchored task windows on the current year while the agent anchored on every year that could reach the date (TD-037). | standing | [09](pitfalls/09-domain-solver.md#pf-dom-19) |  |
| PF-DOM-20 | The "weeks after planting" comment in the bundled plant data was wrong — and the first measurement of how wrong was itself wrong. | standing | [09](pitfalls/09-domain-solver.md#pf-dom-20) |  |
| PF-DOM-21 | A shared generator's flags are inherited per iteration, so a wrapper can filter before the wrapper's own filter runs. | standing | [09](pitfalls/09-domain-solver.md#pf-dom-21) |  |
| PF-DOM-22 | A day derived from a UTC instant is not the user's day (Phase 17 L1.0, #385) | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-22) | 11.4.7 |
| PF-DOM-23 | Guild boundaries found by independent review (F1/F2) | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-23) | 11.4.8 |
| PF-DOM-24 | Sun self-shadow and late document results (#314, #428) | standing (narrative archived) | [09](pitfalls/09-domain-solver.md#pf-dom-24) | 11.4.6 |
| PF-E3D-01 | A reused (hidden→re-shown) `Qt3DWindow` renders a blank/white surface (PyQt6 + RHI) | retired | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-01) |  |
| PF-E3D-02 | Key events on a `createWindowContainer`-embedded `Qt3DWindow` don't bubble to the ancestor `QMainWindow` (PyQt6) | retired | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-02) |  |
| PF-E3D-03 | `QFirstPersonCameraController` free-flies (moves along the pitched view vector, no pitch limit, arrows only) — wrong for a ground walk | retired | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-03) |  |
| PF-E3D-04 | Time a stall with a trusted clock before blaming the engine | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-04) | 11.4.5 |
| PF-E3D-05 | A hash is not equality; float dust is an edit; a bound checked after the work is a report | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-05) | 11.4.14 |
| PF-E3D-06 | A judge must not ask the suspect; no Qt window predicate is trusted until measured; a Python message handler beside a shown Qt Quick window deadlocks | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-06) | 11.4.15 |
| PF-E3D-07 | No frame inside a measured loop; wait for a condition, not a duration | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-07) | 11.4.16 |
| PF-E3D-08 | What selection, the info card and walk mode taught (Phase 17 L1.8, #385) | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-08) | 11.4.19 |
| PF-E3D-09 | What the default flip and the removal of Qt 3D taught (Phase 17 L1.9 / L1.10, #385) | standing (narrative archived) | [10](pitfalls/10-3d-engine-scene.md#pf-e3d-09) | 11.4.20 |
| PF-L3D-01 | A gate the repair itself satisfies is not evidence; a measure must be able to move | standing (narrative archived) | [11](pitfalls/11-3d-look-ground-build.md#pf-l3d-01) | 11.4.12 |
| PF-L3D-02 | A bounding box is not a footprint; a closed polyline is a ring; pin everything else before changing shipped behaviour | standing (narrative archived) | [11](pitfalls/11-3d-look-ground-build.md#pf-l3d-02) | 11.4.13 |
| PF-L3D-03 | A bound that keeps the topmost N drops what everything stands on; a count is not a time | standing (narrative archived) | [11](pitfalls/11-3d-look-ground-build.md#pf-l3d-03) | 11.4.17 |
| PF-L3D-04 | Never point a Texture at a second texture | standing (narrative archived) | [11](pitfalls/11-3d-look-ground-build.md#pf-l3d-04) |  |
| PF-L3D-05 | What the looks, the sky and the wind taught (Phase 17 L1.4, #385) | standing (narrative archived) | [11](pitfalls/11-3d-look-ground-build.md#pf-l3d-05) | 11.4.18 |
| PF-PRC-01 | "The app changed behaviour" is a claim about a *setting* until the setting has been read. | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-01) |  |
| PF-PRC-02 | A claim written from the producer's side is not a delivered feature — and a test that skips the consumer cannot catch it. | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-02) |  |
| PF-PRC-03 | Lesson: before treating "the UI doesn't update" as a bug, check whether the change contradicts a *formally accepted* dec | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-03) |  |
| PF-PRC-04 | NEVER use PowerShell `Set-Content -Encoding UTF8` for files containing non-ASCII characters | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-04) |  |
| PF-PRC-05 | A `file.py:line` citation drifts silently when unrelated features grow the file — measured, not hypothetical | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-05) |  |
| PF-PRC-06 | The citation gate's own senior review found the gate had almost no teeth on the dimension that motivated it, and the fix needed its own mutation-tested regressions before it actually had any | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-06) |  |
| PF-PRC-07 | A drift-tolerance window that is merely "generous" is a false safety claim, not a weaker one | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-07) |  |
| PF-PRC-08 | Named residual, measured, not swept under the fix | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-08) |  |
| PF-PRC-09 | **An issue's "verified repo facts" are a claim about the code, not the code — and a rule that | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-09) |  |
| PF-PRC-10 | **Lesson | standing | [12](pitfalls/12-process-and-docs.md#pf-prc-10) |  |

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
| 11.4.17 | PF-L3D-03 | A bound that keeps the topmost N drops what everything stands on; a count is not a time |
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
