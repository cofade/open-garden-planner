# Audit 2026-10 — current reconciliation and delivery packages

## Remaining packages shipped (29 October 2026, v1.34.5)

A4 (#456), A6 (#458), A7 (#459), A9 (#461), A12 (#464) and A13 (#465)
are implemented together and shipped in v1.34.5 (PR #640), completing epic #392.
Per-finding evidence, current measurements, review slices and explicit owner-only
continuity actions are in [the delivery record](audit-392-remaining.md) (ADR-068).
The dated intake rows below remain historical acceptance/evidence descriptions;
they are not fresh measurements. Other packages were already delivered.



Reconciled 2026-10-12 against master `9e1629f` (v1.30.1). The [dated snapshot](audit-2026-10.md) retains its historical measurements. [Epic #392](https://github.com/cofade/open-garden-planner/issues/392) is the work ledger; #406 is its last open standalone P0/P1 remediation, not its final remaining finding.

## Reading the dispositions

`unresolved` means remaining work, including measurement/investigation where stated. `partially resolved` separates already-shipped remediation from a named remainder. `fixed (#PR)` cites delivery and leaves no new task. Source inspection is current; historical coverage/mutation/timing/import-cost counts are not asserted as current without a rerun. Accepted policies remain binding; their investigation does not silently reverse them.

## Package map and dependencies

> **Audit 2026-10 package map & order.** Epic #392; #406 completes the last P1 first. A1 #453; A2 #454; A3 #455; A4 #456; A5 #457; A6 #458; A7 #459; A8 #460; A9 #461; A10 #462; A11 #463; A12 #464; A13 #465. After #406 prioritize A1, then small independent remediations. A5 and constraint-related A4/A6 work depend on #406; A6/A7 structural extraction depends on A4; performance-driven changes depend on A9 measurement. A12 preserves facts/citations before moving context. Each bundle may use sequential PRs based on master; close only after all remaining acceptance items pass.

| Package | Issue / responsibility | Findings |
|---|---|---|
| A1 | [#453](https://github.com/cofade/open-garden-planner/issues/453) — Imported data, downloads and credential storage safety | AUD-041, AUD-042, AUD-044, AUD-047 |
| A2 | [#454](https://github.com/cofade/open-garden-planner/issues/454) — Dependency maintenance, build reproducibility and distribution inventory | AUD-049, AUD-050, AUD-051, AUD-052, AUD-053, AUD-054, AUD-055 |
| A3 | [#455](https://github.com/cofade/open-garden-planner/issues/455) — Portable CI, lint hygiene and redundant-check costs | AUD-032, AUD-033, AUD-034, AUD-035, AUD-036, AUD-037, AUD-045 |
| A4 | [#456](https://github.com/cofade/open-garden-planner/issues/456) — Import boundaries, package cycles and architecture enforcement | AUD-003, AUD-004, AUD-005, AUD-008, AUD-009 |
| A5 | [#457](https://github.com/cofade/open-garden-planner/issues/457) — Constraint descriptors and stronger solver assertions | AUD-012, AUD-023 |
| A6 | [#458](https://github.com/cofade/open-garden-planner/issues/458) — Canvas interaction and properties-panel maintainability | AUD-007, AUD-011, AUD-013, AUD-014 |
| A7 | [#459](https://github.com/cofade/open-garden-planner/issues/459) — Application orchestration extraction | AUD-006 |
| A8 | [#460](https://github.com/cofade/open-garden-planner/issues/460) — Test precision, lifecycle hygiene and test-layer documentation | AUD-018, AUD-019, AUD-021, AUD-022, AUD-024, AUD-025, AUD-026, AUD-027, AUD-028 |
| A9 | [#461](https://github.com/cofade/open-garden-planner/issues/461) — Performance contracts, representative benchmarks and bulk insertion | AUD-057, AUD-058, AUD-059, AUD-060, AUD-061 |
| A10 | [#462](https://github.com/cofade/open-garden-planner/issues/462) — Architecture documentation and capability-register consistency | AUD-065, AUD-066, AUD-067, AUD-068, AUD-069, AUD-070, AUD-071, AUD-073, AUD-074, AUD-076 |
| A11 | [#463](https://github.com/cofade/open-garden-planner/issues/463) — Release attribution, version consistency and release recovery | AUD-038, AUD-072, AUD-086, AUD-089, AUD-090 |
| A12 | [#464](https://github.com/cofade/open-garden-planner/issues/464) — Agent context, skill loading and change/review discipline | AUD-015, AUD-077, AUD-078, AUD-079, AUD-080, AUD-081, AUD-082, AUD-083, AUD-084, AUD-087 |
| A13 | [#465](https://github.com/cofade/open-garden-planner/issues/465) — Contributor onboarding and maintainer continuity | AUD-046, AUD-075, AUD-088, AUD-091 |

## Finding dispositions

All 73 P2/P3 checklist entries are assigned exactly once. The acceptance text below records the dated intake specification. Subsequent criteria and delivery state are maintained in the linked GitHub issues, the only implementation work list. AUD-061 remains assigned to A9 for measurement/inventory; existing #450 owns its per-add z-order remediation.

### A1: Imported data, downloads and credential storage safety

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-041 | unresolved | File load/save still use default JSON numeric handling; the new two-phase loader did not add finite-number validation. [src/open_garden_planner/core/project.py:1028](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/core/project.py#L1028). **Remaining acceptance:** Reject non-finite geometry/canvas inputs atomically, validate canvas bounds through the shared validation seam, and refuse non-finite saves; test NaN, Infinity and finite overflow without damaging the open document. |
| AUD-042 | unresolved | The updater downloads then launches an installer without comparing the release checksum; TLS alone is the current check. [src/open_garden_planner/ui/widgets/update_bar.py:257](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/widgets/update_bar.py#L257). **Remaining acceptance:** Verify the matching release checksum and permitted download origin before launch; test corrupt bytes, missing/mismatched checksum, redirects and cancellation with no executable launched. Explain checksum integrity versus authenticity in an ADR-044 addendum. |
| AUD-044 | unresolved | Secrets still use QSettings; the historical Linux file-mode result has not been remeasured on this Windows intake. [src/open_garden_planner/app/settings.py:26](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/app/settings.py#L26). **Remaining acceptance:** Reproduce INI permissions under a controlled Linux umask, then enforce owner-only file access with platform tests; preserve existing Windows registry behavior and migration compatibility. Any keyring dependency requires a separate reviewed ADR. |
| AUD-047 | unresolved | Thumbnail download still buffers the whole response and trusts an image Content-Type before writing bytes to a .png cache. [src/open_garden_planner/services/plant_api/thumbnail_loader.py:78](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/services/plant_api/thumbnail_loader.py#L78). **Remaining acceptance:** Bound both thumbnail and Static Maps response sizes while streaming, verify actual decodable image content before caching, and test oversized, misleading-type and truncated responses with no partial cache artifacts. |

### A2: Dependency maintenance, build reproducibility and distribution inventory

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-049 | partially resolved | PR #422 locks PyInstaller and backend tools; NSIS and Python patch selection still float in release/shared setup. [pyproject.toml:163](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/pyproject.toml#L163). **Remaining acceptance:** Pin or explicitly record the remaining installer/interpreter toolchain selections, emit actual versions in build evidence, and prove a locked frozen build. Do not replace the committed Python lock. |
| AUD-050 | partially resolved | Lockfiles and a documented hosted Dependabot/uv incompatibility now exist; there is still no committed dependency-update configuration. [docs/11-risks-and-technical-debt/README.md:40](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/11-risks-and-technical-debt/README.md#L40). **Remaining acceptance:** Establish working reviewed update automation or a documented scheduled manual fallback, preserve Qt/mcp caps, and smoke-test an update PR without auto-merge. Verify hosted uv support rather than assuming it. |
| AUD-051 | unresolved | The spec bundles selected metadata and the installer GPL text; no consolidated third-party notice artifact exists in the tree. Exact shipped inventory requires a new build. [installer/ogp.spec:21](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/installer/ogp.spec#L21). **Remaining acceptance:** Generate notices from the actual frozen distribution inventory, bundle required license texts and attribution, and verify the installed artifact includes them. Assess current licenses using primary metadata, not the historical 42-distribution count. |
| AUD-052 | unresolved | The stale requirements manifests remain despite the locked installation recipe warning against them. [requirements.txt:2](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/requirements.txt#L2). **Remaining acceptance:** Remove or generate the redundant manifests, update every consumer/link, and prove the documented locked Windows/Linux setup is complete and Qt-version-safe. |
| AUD-053 | unresolved | Actions still use mutable version tags, including release actions with write/OIDC privileges. [.github/workflows/release.yml:25](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/release.yml#L25). **Remaining acceptance:** Pin every external action to a reviewed immutable commit with readable version comments; add a maintenance path and a drift guard that includes the shared composite action. |
| AUD-054 | partially resolved | The old 79.0.1 observation is historical; current build backend is locked at 82.0.0 and an advisory assessment is documented. CI still has no lock-based vulnerability scan. [pyproject.toml:165](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/pyproject.toml#L165). **Remaining acceptance:** Reassess the current locked runtime/build closure with a dependency audit; fix applicable advisories in a separately reviewed dependency PR and add a reproducible scan with documented, justified exceptions. |
| AUD-055 | unresolved | Release provenance attestation exists but no SBOM artifact is generated. [.github/workflows/release.yml:188](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/release.yml#L188). **Remaining acceptance:** Generate a machine-readable SBOM from actual frozen/build inventory, attach it to the matching release and provenance evidence, and verify its package identities match the executable bundle. |

### A3: Portable CI, lint hygiene and redundant-check costs

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-032 | partially resolved | PR #422 adds Windows dependency/type jobs; the main test job remains Linux-only and frozen checks remain post-merge. [.github/workflows/ci.yml:113](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/ci.yml#L113). **Remaining acceptance:** Run the platform-specific test scenarios and frozen smoke/selftest before merge on a Windows CI path; demonstrate a deliberately broken frozen subsystem fails that path and document protection policy. |
| AUD-033 | fixed (#411) | PR #411 widened lint to all three trees and cleared existing findings; this is enforced in current CI. [.github/workflows/ci.yml:41](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/ci.yml#L41). **Remaining acceptance:** Already delivered; retain the all-tree lint gate. |
| AUD-034 | partially resolved | The configured line length is 100 and gate docs were corrected in #422; no formatter gate is present. Historical file counts need remeasurement. [pyproject.toml:89](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/pyproject.toml#L89). **Remaining acceptance:** Measure current formatter drift, land a dedicated behavior-preserving formatting change with blame-ignore metadata, and enforce format --check only after the tree is clean. |
| AUD-035 | unresolved | Both push and pull_request CI triggers remain; no concurrency block exists. The historical duplicate-run count was not repeated. [.github/workflows/ci.yml:8](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/ci.yml#L8). **Remaining acceptance:** Measure duplicate checks for the same head and remove redundant runs with cancellation/concurrency while preserving every protected master check; validate push, draft PR and updated PR events. |
| AUD-036 | unresolved | RUF100 is not selected; the old unused-noqa count requires a fresh scan. [pyproject.toml:92](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/pyproject.toml#L92). **Remaining acceptance:** Re-run the unused-noqa inventory, remove dead directives without suppressing genuine checks, and enforce RUF100 over source/tests/scripts with a clean full lint run. |
| AUD-037 | unresolved | The export harness still has machine-specific setup; it is not a portable quality gate. [scripts/validate_exports.py:15](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/scripts/validate_exports.py#L15). **Remaining acceptance:** Provide explicit CLI inputs/output directories and an import-safe entry point; run on a temporary plan outside the author's workspace and distinguish diagnostic harnesses from merge gates in docs. |
| AUD-045 | partially resolved | PR #422 restricts CI to contents:read; HIGH-only Bandit is the accepted gate, not authorization to silently raise severity. [.github/workflows/ci.yml:3](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/workflows/ci.yml#L3). **Remaining acceptance:** Re-triage present MEDIUM/LOW findings and document dispositions with tests for any real defect. Preserve HIGH-only unless an explicit ADR changes the accepted policy; verify read-only permissions remain sufficient. |

### A4: Import boundaries, package cycles and architecture enforcement

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-003 | unresolved | The module-level core-to-ui import is still present; it is architecture debt rather than a reproduced user defect. [src/open_garden_planner/core/tools/constraint_tool.py:34](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/core/tools/constraint_tool.py#L34). **Remaining acceptance:** After #406, move the item-type import to permitted local/type-checking seams and prove tool gestures/import startup remain valid; include it in the boundary ratchet. |
| AUD-004 | unresolved | Settings still import the theme/UI package at module level; exact import-footprint counts were not rerun. [src/open_garden_planner/app/settings.py:10](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/app/settings.py#L10). **Remaining acceptance:** Put shared settings/path/theme data behind a leaf boundary and compatibility shims, document ADR-041 consequences, and prove lower-layer imports no longer load UI through that seam. |
| AUD-005 | unresolved | The audit script can classify imports, but CI has no enforcing layer fitness test. [scripts/audit_metrics.py:324](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/scripts/audit_metrics.py#L324). **Remaining acceptance:** Enforce module-level boundary rules with explicit shrink-only exceptions while allowing function-local/TYPE_CHECKING seams; test both permitted and forbidden fixtures and wire the gate into CI. |
| AUD-008 | unresolved | The model still imports a core evaluator; the seed-inventory services edge and cycle counts require refreshed graph evidence. [src/open_garden_planner/models/smart_symbol.py:39](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/models/smart_symbol.py#L39). **Remaining acceptance:** Recompute the graph, move/inject the identified upward dependencies behind compatibility paths, and pin model behavior and absence of new package cycles. |
| AUD-009 | unresolved | Core and tool package initializers still eagerly re-export substantial modules. [src/open_garden_planner/core/__init__.py:3](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/core/__init__.py#L3). **Remaining acceptance:** Measure the current import cost and implement lazy compatibility exports if the improvement is measurable; test every public export and subprocess import footprints without breaking import order. |

### A5: Constraint descriptors and stronger solver assertions

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-012 | fixed (#489), v1.30.4; owner accepted | One immutable enum-complete panel descriptor; independent all-type rendering, icons/colors and runtime German checks, including all 52 unnamed object types. Fresh dispatch inventory and deliberate geometry boundaries: [A5 evidence](audit-2026-10-a5-evidence.md). ADR-012 addendum. |
| AUD-023 | fixed (#489), v1.30.4; owner accepted | Eight explicit mutants replayed against existing relevant tests, then strengthened geometric oracles. Both confirmed symmetry survivors are killed; the baseline timeout is reported separately. All-pinned false convergence fixed with failing-first regressions. [A5 evidence](audit-2026-10-a5-evidence.md); historical mutation counts unchanged. |

### A6: Canvas interaction and properties-panel maintainability

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-007 | partially resolved | PR #412 removed the divergent clipboard codec; array orchestration and drag-time constraints still live in CanvasView. [src/open_garden_planner/ui/canvas/canvas_view.py:4819](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/canvas/canvas_view.py#L4819). **Remaining acceptance:** Measure the settled class and extract coherent clipboard/array and drag-solve responsibilities behind existing command/serialization seams; preserve every copy/array/drag workflow and undo count. |
| AUD-011 | unresolved | Shape classes still own repeated common context-menu construction; bed actions already have their own canonical seam. [src/open_garden_planner/ui/canvas/items/rectangle_item.py:562](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/canvas/items/rectangle_item.py#L562). **Remaining acceptance:** Characterize each shape menu, extract shared common actions centrally, and retain shape-specific capability guards and the existing bed-menu golden matrix. |
| AUD-013 | unresolved | The properties panel still routes edits through the large dispatcher; the historical branch coverage needs refresh. [src/open_garden_planner/ui/panels/properties_panel.py:2322](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/panels/properties_panel.py#L2322). **Remaining acceptance:** Characterize every supported property edit through UI/command wiring, including pending-debounce flush and undo; split only after the gesture and focus-preservation net passes. |
| AUD-014 | unresolved | PR #422 removed obsolete type-ignore comments; this did not remediate the large-module finding. Handle classes still share the module. [src/open_garden_planner/ui/canvas/items/resize_handle.py:1303](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/canvas/items/resize_handle.py#L1303). **Remaining acceptance:** Characterize supported shapes at non-axis-aligned rotations, then extract vertex/midpoint responsibilities while preserving mouse-grab allowlists, pivots, serialization and exact undo restoration. |

### A7: Application orchestration extraction

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-006 | unresolved | Agent orchestration still resides in the application class; subsequent features mean the historical LOC/method totals are stale. [src/open_garden_planner/app/application.py:237](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/app/application.py#L237). **Remaining acceptance:** Re-measure the current agent block and extract a coherent host adapter after A4, retaining the real MCP boundary, command path, lifecycle aborts and capability/refusal tests. |

### A8: Test precision, lifecycle hygiene and test-layer documentation

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-018 | fixed (#460) | Defined formal test layer contract in §8.10 partitioning unit, ui, integration, and perf tiers; designated tests/ui/test_main_window.py as the smoke test. [docs/08-crosscutting-concepts/README.md](docs/08-crosscutting-concepts/README.md). |
| AUD-019 | fixed (#515, #460) | Fixed CategoryDropdown parentage in CategoryToolbar eliminating 38,000+ leaked widgets across tests and resolving stylesheet re-polish access violation crashes (#447). Pinned by [tests/unit/test_widget_leak_reclamation.py](tests/unit/test_widget_leak_reclamation.py). |
| AUD-021 | unresolved | The historical seconds/minutes and Jan-Feb mutation gaps require a current source/test sweep. [tests/unit/test_solar.py:35](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/unit/test_solar.py#L35). **Remaining acceptance:** Add independently sourced solar/julian-date oracle rows with nonzero minutes/seconds and Jan-Feb dates, and default circle-footprint spacing assertions; demonstrate confirmed sampled mutants are killed. |
| AUD-022 | unresolved | Candidate-cap, deduplication and antagonist rejection paths remain; the audit already refuted the broader no-tests headline. [src/open_garden_planner/services/companion_sets.py:23](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/services/companion_sets.py#L23). **Remaining acceptance:** Measure those specific paths and add observable result assertions for cap ordering, merged-source deduplication and antagonist refusal, preserving existing bed-set ranking semantics. |
| AUD-024 | unresolved | Commands have story integration coverage; the mutation claim is explicitly scoped to a narrow unit selection. [tests/unit/test_commands.py:30](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/unit/test_commands.py#L30). **Remaining acceptance:** Inventory command contracts using the full relevant suite, add missing execute/undo/redo state-equality tests including deletes and failure paths, and report mutation sampling scope honestly. |
| AUD-025 | unresolved | The small boundary modules and existing tests have evolved; exact historical survivor counts have not been repeated. [src/open_garden_planner/core/canvas_bounds.py:28](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/core/canvas_bounds.py#L28). **Remaining acceptance:** Re-evaluate canvas-edge, stacking block/no-op, shape-type and localized-name gaps; add boundary/refusal assertions for confirmed survivors without duplicating implementation constants. |
| AUD-026 | unresolved | Construction-smoke and weak-assertion claims require a refreshed AST/manual inventory across the current suite. [tests/ui/test_main_window.py:12](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/ui/test_main_window.py#L12). **Remaining acceptance:** Classify current assertionless/existence-only cases, add observable behavior assertions where required, and rename fixture functions that look like tests; document intentional smoke exceptions. |
| AUD-027 | unresolved | Tests still inspect private implementation state; the old ratio is not a current measurement. [tests/integration/test_map_picker_capture.py:54](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/integration/test_map_picker_capture.py#L54). **Remaining acceptance:** Re-measure private assertions, replace fragile high-density cases with stable behavioral probes where worthwhile, and prove those probes detect failure instead of adding a test-only runtime API. |
| AUD-028 | unresolved | More quality tests now depend on root scripts; this does not remediate reduced-tree collection fragility. The old count of three is historical. [tests/unit/test_ci_quality_gates.py:8](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/unit/test_ci_quality_gates.py#L8). **Remaining acceptance:** Make script-test import requirements explicit and classify script-dependent tests for reduced-tree/mutation runs; verify full collection and a controlled source+tests-only copy without false zero-score claims. |

### A9: Performance contracts, representative benchmarks and bulk insertion

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-057 | partially resolved | PR #430 adds the NFR-PERF-01 harness; the audit's blanket no-harness claim is false, while other NFR budgets still lack comparable committed measurement. [tests/perf/test_nfr_budgets.py:73](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/perf/test_nfr_budgets.py#L73). **Remaining acceptance:** Inventory all five NFRs, add reproducible reference-plan harnesses for the missing metrics, and document instrumented/headless versus real-window budgets with actual platform results. |
| AUD-058 | unresolved | Startup and theme application still need a current cold/warm timing breakdown; the old near-budget observation is not a current result. [src/open_garden_planner/main.py:237](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/main.py#L237). **Remaining acceptance:** Measure time to usable window on the frozen artifact with a disclosed machine/profile; remove repeated startup work only from evidence and pin regressions without a flaky universal millisecond assertion. |
| AUD-059 | unresolved | The existing quiescence gate needs a representative 500-object scenario; historical idle RSS and callback counts were not rerun. [tests/integration/test_idle_scene_quiescence.py:60](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/tests/integration/test_idle_scene_quiescence.py#L60). **Remaining acceptance:** Add the committed reference plan to idle/quiescence measurement, record RSS and scene/minimap callbacks over a defined interval, and verify repaint/worker lifecycle remains quiet. |
| AUD-060 | unresolved | Performance rows still need explicit reproducible reference inputs and output dimensions rather than an unspecified typical plan/high resolution. [docs/10-quality-requirements/README.md:33](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/10-quality-requirements/README.md#L33). **Remaining acceptance:** Define the 500-object reference and A3/300-DPI export workload, remeasure load/export via real surfaces, and tie the requirements to the committed harness and machine conditions. |
| AUD-061 | partially resolved | Bulk scopes already exist in loader and command seams; repeated direct adds still refresh layer rank/z. The old timing ratio is historical. [src/open_garden_planner/ui/canvas/canvas_scene.py:787](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/src/open_garden_planner/ui/canvas/canvas_scene.py#L787). **Remaining acceptance:** Inventory and measure multi-add paths; retain per-add z-order/scaling remediation and its order/undo/layer regression criteria under existing issue #450 (which already owns AUD-061). This bundle owns only the distinct benchmark/inventory evidence and links #450 delivery; do not implement or close the same remediation twice. |

### A10: Architecture documentation and capability-register consistency

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-065 | unresolved | ADR-004 still describes QUndoStack although the app uses CommandManager; early asset ADR status lines remain accepted. [docs/09-architecture-decisions/README.md:33](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/09-architecture-decisions/README.md#L33). **Remaining acceptance:** Reconcile the named ADR status/implementation discrepancies and supersession links without rewriting historical decisions; validate every changed cross-reference and current implementation claim. |
| AUD-066 | fixed (#407) | PR #407/ADR-047 already added the live status/issue register and historical-row dispositions. [docs/11-risks-and-technical-debt/README.md:46](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/11-risks-and-technical-debt/README.md#L46). **Remaining acceptance:** Already delivered; maintain the register and preserve resolved rows. |
| AUD-067 | unresolved | The pitfall register remains a long mixed-format history; duplicate/contradictory #366 headlines need precise reconciliation. [docs/11-risks-and-technical-debt/README.md:88](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/11-risks-and-technical-debt/README.md#L88). **Remaining acceptance:** Resolve the named duplicate and contradictory entries, preserve useful lessons, and introduce clear closed/superseded markers tied to implementing evidence. |
| AUD-068 | partially resolved | F/G and shipped D3 entries now exist, but agent restart prose still names already-shipped work as next. [docs/roadmap.md:2588](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/roadmap.md#L2588). **Remaining acceptance:** Reconcile current-state pointers against GitHub/merged history, eliminate contradictory next-work statements, and keep one authoritative roadmap with linked summaries rather than repeated trackers. |
| AUD-069 | unresolved | Citation discovery still assumes chapter READMEs/one ADR index; documentation chapters remain large. [scripts/check_skill_citations.py:84](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/scripts/check_skill_citations.py#L84). **Remaining acceptance:** Extend citation discovery with tests before splitting monoliths; preserve every ADR/section/FR link and migrate chapter content without losing evidence or duplicating canonical facts. |
| AUD-070 | partially resolved | Some gate counts were updated with #422, but stale hardcoded suite/inventory counts remain in skills and docs. [.agents/skills/ogp-validation-and-qa/SKILL.md:211](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.agents/skills/ogp-validation-and-qa/SKILL.md#L211). **Remaining acceptance:** Replace volatile counts with discovery commands or generated inventory, fix corresponding mirrored skills, and add narrowly scoped drift checks for remaining necessary numeric claims. |
| AUD-071 | partially resolved | The FR register still calls the wired ellipse tool future; ACCESSIBILITY.md now documents the current accessibility limitations. [docs/functional-requirements.md:39](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/functional-requirements.md#L39). **Remaining acceptance:** Mark shipped/deferred FRs consistently and link FR-UI-20/21/22 to actionable follow-ups with owner/product decisions where needed; do not claim unsupported accessibility capability. |
| AUD-073 | unresolved | Most roadmap content remains shipped history and earlier unchecked markers still need reconciliation. [docs/roadmap.md:107](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/roadmap.md#L107). **Remaining acceptance:** Separate navigable current work from shipped history without losing acceptance criteria, reconcile stale markers to issue evidence, and keep wiki roadmap generation valid. |
| AUD-074 | unresolved | arrange_object is documented under stacking but still lacks the audit's requested agent-register cross-reference. [docs/functional-requirements.md:563](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/functional-requirements.md#L563). **Remaining acceptance:** Add an explicit agent requirement cross-reference and verify real tool/requirement parity without creating a duplicate behavioral specification. |
| AUD-076 | unresolved | The building-block inventory still lacks black-box entries for arrange, stacking, canvas_bounds and preview_z despite incidental schema wording. [docs/05-building-block-view/README.md:3](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/05-building-block-view/README.md#L3). **Remaining acceptance:** Document the four canonical modules' responsibility/dependencies and verify their actual seams against source; update the tree without duplicating runtime or API contracts. |

### A11: Release attribution, version consistency and release recovery

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-038 | fixed (#463) | Release bump attribution distinguishes new tags, idempotent workflow retries on the same commit SHA, and conflicting tags on different commit SHAs. Failing release on conflicting tag avoids silent skip. `scripts/resolve_release_pr.py`, `.github/workflows/release.yml`, pinned by `tests/unit/test_release_version.py`. ADR-050 addendum. |
| AUD-072 | fixed (#596) | `_version.py` is a gitignored build artifact: a release writes it before PyInstaller and removes it afterwards; a direct build falls back to `__version__`. The installer default is the manifest (A11). `tests/unit/test_packaging_metadata.py` pins the source/frozen/update-checker agreement, the release direction and the spec's conditional hidden import; `--selftest` checks the frozen version. See ADR-050 addendum and PF-CI-15. **Remaining acceptance:** none; keep the generated module out of git. |
| AUD-086 | fixed (#463) | Evaluated dynamic version derivation maintenance cost vs offline single-binary packaging stability in ADR-050 addendum. Retained CI-owned release authority and reviewed version-sync chore workflow. ADR-050 addendum. |
| AUD-089 | fixed (#422) | The fallback now explicitly prohibits manual tags/publication and directs restoration of CI-owned releases. [docs/07-deployment-view/README.md:138](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/docs/07-deployment-view/README.md#L138). **Remaining acceptance:** Already delivered; retain the documented CI-owned recovery constraint. |
| AUD-090 | fixed (#463) | Added release classification gate (`scripts/check_release_classification.py`) verifying executable modifications vs documentation/sync chores, preventing chore commits from concealing unreleased code changes. Pinned by `tests/unit/test_release_classification.py`. ADR-050 addendum. |

### A12: Agent context, skill loading and change/review discipline

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-015 | unresolved | The PR template now exists but has no explicit large-change slicing or asset-separation guidance; the historical nine-commit statistic was not rerun. [.github/pull_request_template.md:1](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/pull_request_template.md#L1). **Remaining acceptance:** Measure current review-unit sizes, add concrete scope/slicing guidance for unusually large changes, and preserve semantic package dependencies without turning raw line counts into an automatic approval shortcut. |
| AUD-077 | unresolved | Root instructions still repeat substantial shipped narrative already maintained in roadmap/ADRs. [AGENTS.md:223](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/AGENTS.md#L223). **Remaining acceptance:** Migrate unique facts first, then replace duplicate progress narrative with concise canonical pointers while retaining all binding rules, handoff information and Claude/Codex parity. |
| AUD-078 | partially resolved | PR #422 raises the configured hard cap to 65,536 and parity checks it; the old 830-byte-headroom claim is obsolete. No smaller growth budget is enforced. [.codex/config.toml:2](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.codex/config.toml#L2). **Remaining acceptance:** Measure actual root-context size and choose documented warning/soft limits below the configured cap; test budget enforcement without silently truncating required context. |
| AUD-079 | unresolved | debug-verbose remains a large method-plus-case monolith; exact current byte/case counts require a fresh inventory. [.agents/skills/debug-verbose/SKILL.md:10](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.agents/skills/debug-verbose/SKILL.md#L10). **Remaining acceptance:** Keep a short method and searchable case index, move cases to mirrored files, and extend citation/parity discovery before migration; prove no lesson or citation is lost. |
| AUD-080 | partially resolved | PR #422 enforces master protection and gates, but local branch/tag/draft/encoding/exe rules still rely partly on prose. [quality/master-protection.json:15](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/quality/master-protection.json#L15). **Remaining acceptance:** Inventory remaining unenforced rules, add cross-platform tests/checks or supported host hooks for actual gaps, and preserve explicit user authorization semantics and existing protected finalization. |
| AUD-081 | unresolved | The citation gate retains a small symbol window; repeated line-number references still create maintenance cost. [scripts/check_skill_citations.py:29](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/scripts/check_skill_citations.py#L29). **Remaining acceptance:** Measure citation duplication, consolidate one gated reference per fact with precise symbols, and keep resolver coverage at least as strong without widening the accepted window. |
| AUD-082 | unresolved | Routing descriptions/table maintenance remain manual; historical mismatches require rechecking current frontmatter. [AGENTS.md:55](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/AGENTS.md#L55). **Remaining acceptance:** Inventory current routing mismatches and ambiguous triggers, revise mirrored descriptions/table consistently, and test concrete discrimination cases rather than matching only identical wording. |
| AUD-083 | unresolved | Both native reviewer definitions still carry the stale Phase-12 claim; the Claude definition pins its native model. [.claude/agents/senior-reviewer.md:26](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.claude/agents/senior-reviewer.md#L26). **Remaining acceptance:** Replace stale phase claims with canonical pointers and define evidence-based finding verification/read-only responsibilities in both native formats; preserve parity without imposing one host's model syntax on the other. |
| AUD-084 | unresolved | Several skills remain large monoliths; current corpus size and loading costs require a fresh inventory. [.agents/skills/ogp-failure-archaeology/SKILL.md:17](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.agents/skills/ogp-failure-archaeology/SKILL.md#L17). **Remaining acceptance:** Introduce progressive disclosure for measured large skills, extend reference-file citation/parity checks first, and verify trigger instructions remain discoverable and all moved content resolves. |
| AUD-087 | partially resolved | The template now records independent-review status; design-stage review and explicit round accounting are still absent. [.github/pull_request_template.md:13](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/pull_request_template.md#L13). **Remaining acceptance:** Define early review criteria for unusually broad/new-API work, record review rounds/findings in delivery evidence, and preserve the existing clean final review and owner manual-testing gates. |

### A13: Contributor onboarding and maintainer continuity

| Finding | Disposition | Current evidence and remaining work |
|---|---|---|
| AUD-046 | partially resolved | PR #424 adds SECURITY.md and private-report routing; the composite original finding also mentions missing update automation and CODEOWNERS. [SECURITY.md:9](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/SECURITY.md#L9). **Remaining acceptance:** Verify current private-report setup and document security-policy ownership; update automation belongs only to A2/AUD-050, maintainer ownership only to AUD-088, avoiding duplicated acceptance items. |
| AUD-075 | fixed (#424) | PR #424 supplies human-oriented locked setup, contribution/review guidance and README links. [CONTRIBUTING.md:18](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/CONTRIBUTING.md#L18). **Remaining acceptance:** Already delivered; retain runnable documented setup and the private security-report path. |
| AUD-088 | partially resolved | PR #424 adds security/onboarding policies; no .mailmap/CODEOWNERS or verified maintainer continuity arrangement exists. [SECURITY.md:3](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/SECURITY.md#L3). **Remaining acceptance:** Reconcile contributor identities, establish ownership/recovery documentation, and identify owner-dependent continuity actions explicitly; do not assign release privileges or invent a second maintainer without owner authorization. |
| AUD-091 | fixed (#424) | PR #424 adds the required problem/issues/validation/docs/manual checklist template. Review-round/slicing improvements are separately assigned to A12. [.github/pull_request_template.md:20](https://github.com/cofade/open-garden-planner/blob/9e1629f9bdd012f8c633e8fd3508ef0cf5623bc0/.github/pull_request_template.md#L20). **Remaining acceptance:** Already delivered; retain draft/manual-review and unmet-gate disclosures. |

## P0/P1 delivery evidence

All 15 remediation issues have been checked against GitHub state and merged history; none remains open. The epic remains open for the unresolved bundles above.
- [#393](https://github.com/cofade/open-garden-planner/issues/393): closed; implemented by [PR #411](https://github.com/cofade/open-garden-planner/pull/411).
- [#394](https://github.com/cofade/open-garden-planner/issues/394): closed; implemented by [PR #412](https://github.com/cofade/open-garden-planner/pull/412).
- [#395](https://github.com/cofade/open-garden-planner/issues/395): closed; implemented by [PR #419](https://github.com/cofade/open-garden-planner/pull/419).
- [#396](https://github.com/cofade/open-garden-planner/issues/396): closed; implemented by [PR #419](https://github.com/cofade/open-garden-planner/pull/419).
- [#397](https://github.com/cofade/open-garden-planner/issues/397): closed; implemented by [PR #412](https://github.com/cofade/open-garden-planner/pull/412).
- [#398](https://github.com/cofade/open-garden-planner/issues/398): closed; implemented by [PR #419](https://github.com/cofade/open-garden-planner/pull/419).
- [#399](https://github.com/cofade/open-garden-planner/issues/399): closed; implemented by [PR #422](https://github.com/cofade/open-garden-planner/pull/422).
- [#400](https://github.com/cofade/open-garden-planner/issues/400): closed; implemented by [PR #412](https://github.com/cofade/open-garden-planner/pull/412).
- [#401](https://github.com/cofade/open-garden-planner/issues/401): closed; implemented by [PR #422](https://github.com/cofade/open-garden-planner/pull/422).
- [#402](https://github.com/cofade/open-garden-planner/issues/402): closed; implemented by [PR #422](https://github.com/cofade/open-garden-planner/pull/422).
- [#403](https://github.com/cofade/open-garden-planner/issues/403): closed; implemented by [PR #412](https://github.com/cofade/open-garden-planner/pull/412).
- [#404](https://github.com/cofade/open-garden-planner/issues/404): closed; implemented by [PR #422](https://github.com/cofade/open-garden-planner/pull/422).
- [#405](https://github.com/cofade/open-garden-planner/issues/405): closed; implemented by [PR #426](https://github.com/cofade/open-garden-planner/pull/426).
- [#409](https://github.com/cofade/open-garden-planner/issues/409): closed; implemented by [PR #430](https://github.com/cofade/open-garden-planner/pull/430).
- [#406](https://github.com/cofade/open-garden-planner/issues/406): closed; implemented by [PR #477](https://github.com/cofade/open-garden-planner/pull/477) (v1.30.2).

## Validation and publication

The intake asserts a one-to-one partition of the 73 epic entries and checks each source locator against the frozen master checkout. Tracker bodies are read back after publication. Repository documentation is delivered in a separate reviewed draft chore PR. The snapshot is unchanged; no bundle implementation or completion is claimed by this intake.

## A1 delivery state — 2026-10-13

Package A1 shipped 2026-10-13 as v1.30.3 via [PR #487](https://github.com/cofade/open-garden-planner/pull/487).
Owner confirmed frozen-build acceptance across all four findings (AUD-041/042/044/047).
The intake rows above remain the dated source evidence/acceptance specification;
the historical audit snapshot has not been rewritten. Epic #392 remains open for
packages A2–A13.

## A2 delivery state — shipped 2026-10-15

AUD-049/050/051/052/053/054/055 shipped in
[v1.30.5](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.5) via
[PR #490](https://github.com/cofade/open-garden-planner/pull/490), merge `6854fe66`,
after owner acceptance. All 18 pre-merge CI checks and the matching Release workflow
passed, including frozen verification and provenance. The intake rows above remain
the dated source evidence/acceptance specification; the historical audit snapshot
has not been rewritten. Per finding:

- **AUD-053** — every external `uses:` in `ci.yml`, `release.yml` and the shared composite
  action is pinned to a commit SHA with a `# vX.Y.Z` comment; `scripts/check_action_pins.py`
  enforces it in the `agent-context` job and covers the composite action.
- **AUD-049** — the interpreter patch (`3.11.9`, the newest 3.11 with a Windows build) and NSIS (`--version=3.13.0`) are pinned;
  `scripts/emit_build_evidence.py --require-complete` records the actual toolchain in
  `dist/build-evidence.json` and fails a release it cannot state; the PyInstaller default
  version now comes from `pyproject.toml` instead of a stale `1.0.0`.
- **AUD-051 / AUD-055** — `installer/runtime_closure.py` is the single resolver used by the
  spec (which now bundles every runtime distribution's `.dist-info`) and by
  `scripts/generate_distribution_inventory.py`, which generates `THIRD_PARTY_NOTICES.md`
  and a CycloneDX 1.5 SBOM from the frozen bundle, fails closed on an unknown license, and
  `--check`s the bundle/SBOM/lock identity. Both artifacts ship with the release, the
  notices are installed next to `LICENSE`, and both are attested.
  PR #490's 14 October review exposed omitted hook/vendored code in the original
  closure-only inventory. `installer/frozen_inventory.py` now attributes actual Analysis
  files to wheel RECORD owners, copies their metadata/license files, preserves distinct
  vendored versions, and writes an ownership manifest checked against the executable PYZ.
  Synthetic pipeline coverage is orchestration evidence; actual code coverage is pinned
  by the frozen-hook regression observed failing before this correction.
- **AUD-052** — `requirements.txt` and `requirements-dev.txt` are deleted; a test keeps
  them gone, unreferenced outside the dated records, and the locked recipe is the single
  installation path.
- **AUD-054** — `pip-audit` scans the committed lock export in the `dependencies` matrix
  job, on Linux **and** Windows (pip-audit evaluates markers for the running platform, so
  the Windows-only `pywin32` is only visible to the Windows leg); the one recorded exception
  is the setuptools advisory `PYSEC-2026-3447` for unused macOS sdist publishing,
  justified in §11.2 and reserved for a
  separately reviewed update. *Update 2026-10-24:* that update is #571 — setuptools 84.1.0
  (for GHSA-xmj3-9gf7-h52w, which had turned the required `Dependencies` checks red) and
  filelock 4.2.4, by a targeted `uv lock --upgrade-package` — and the waiver ended with it
  (#572, PF-CI-12): CI waives no advisory now. AUD-054's remaining acceptance ("fix
  applicable advisories in a separately reviewed dependency PR") is met.
- **AUD-050** — hosted uv is verified at 0.12.19 against this project's `==0.12.23` pin, so
  automation is not available; `dependency-review.yml` is the monthly, report-only manual
  fallback, and the runbook plus the Qt/`mcp` cap drift guard live in §7.4 and
  `tests/unit/test_dependency_governance.py`. The acceptance clause "smoke-test an update PR
  without auto-merge" is disposed of by that decision: no automated update PR exists to smoke
  test, and the manual path was exercised instead — the report-only script's exact shell body
  run under the pinned uv exits 0, leaves `uv.lock` byte-identical and reports the seven
  available updates, which is what the owner acts on in a reviewed PR. Revisit automation
  when hosted uv reaches the pin.

The live monthly report passed in
[run 38646071241](https://github.com/cofade/open-garden-planner/actions/runs/38646071241),
created review issue #493 and confirmed the lock stayed unchanged. The published
release includes the SBOM, notices and complete build evidence; installer and SBOM
provenance verify against the Release workflow. Package A2 is complete; epic #392
remains open for A3–A4 and A6–A13.
