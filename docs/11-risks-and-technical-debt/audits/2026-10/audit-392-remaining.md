# Remaining epic #392 packages — delivery evidence

Prepared on 29 October 2026 from `master` at `003c4bc4`. This is implementation
evidence for a draft PR; it is not a release or owner acceptance. The dated
original audit remains unchanged. GitHub showed exactly A4/A6/A7/A9/A12/A13
open at intake. PR #639 was delivered separately; this branch now incorporates
its shipped v1.34.4 changes and version sync from master (`eb0eda0f`).

## Review slices and acceptance mapping

The dependent A4 → A6/A7 extractions share one reviewable branch against master.
A9, A12 and A13 have separate evidence below. A12's source moves are lossless
mechanical fragments plus explicitly recorded citation/link repairs; they are
reviewed separately from behavioral code. The branch must remain draft until
the owner accepts the executable and documentation.

| Issue / findings | Implementation and proof |
|---|---|
| A4 #456, AUD-003 | Item imports are local to actual constraint-tool consumers. Existing registered gesture workflows remain the behavioral gate. |
| AUD-004 | Shared configuration/path/theme leaves; old settings and path imports are the exact module objects. Existing isolation tests and new cold-process identity/footprint tests cover both import orders and mutable factory bindings. ADR-041/068 own the compatibility decision. |
| AUD-005 | A CI-wired AST gate rejects eager forbidden imports, including relative/class/conditional forms, and permits local/TYPE_CHECKING adapters. Empty exception baseline; no new package-layer cycles are admitted. Dynamic imports and deferred cycles are outside this static claim. |
| AUD-008 | The evaluator and data-directory resolver move below models. Smart-symbol and seed-inventory behavior retain the existing tests and compatibility paths. The synthetic macOS test now restores every resolver binding it changes. |
| AUD-009 | Lazy core/tool exports retain every public name and exact class/function identity. Cold subprocesses reduce the observed project-module footprints from 19/77/21 to 4/4/6 for object types/base tool/smart symbol; all three load zero UI modules and no QtWidgets. Timing samples are retained, with no universal import-time threshold. |
| A6 #458, AUD-007 | Composition extracts clipboard/arrays and drag solves using the existing loader/commands. Before extraction, 134 relevant workflow tests passed. Existing copy/array/drag, guild, layer, geometry and undo nets remain in the full suite. |
| AUD-011 | Five shape menus share repeat-action construction and dispatch. Shape/bed/Boolean capabilities remain local. Actual menus at 37°/215° duplicate once, preserve rotation and reverse/restore in exactly one history step. The bed golden matrix is retained. |
| AUD-013 | Six generic appearance/property edits run through their real editor widgets and command manager. Named handlers replace the large dispatcher chain. Existing name/text debounce, focus-preservation, line-preset, geometry and history tests stay intact. |
| AUD-014 | Shared geometry/live-edit primitives and vertex/midpoint/curve owners are extracted. The old import paths expose the same objects; drag-handle allowlists, live-revision censuses, dense-edit spies and mutation locations follow the defining modules. Existing non-axis-aligned resize/vertex serialization/undo matrices remain gates. |
| A7 #459, AUD-006 | `AgentHost` extracts 130 agent methods (3164 original implementation lines) from the current 9357-line application. It has a concrete typed host and no proxy/mirrored state. Compatibility methods preserve call signatures/injection seams; original Qt contexts remain explicit. Real MCP workflow tests exercise refusal/history/document boundaries. A held queued call proves abort-before-join and that aborted work never executes later. |
| A9 #461, AUD-057/058/059/060 | The committed harness measures all five workloads and records exact inputs/output dimensions, all samples, platform, tracing and source/frozen distinction. Measured redundant theme work is removed without removing new-window palette/title-bar/icon refresh. See the native measurements below. |
| AUD-061 | Direct and suspended multi-add paths are inventoried/measured at 100/500 items. Existing #450 owns the shipped scaling/rank/undo remediation (PR #585); there is no second remediation in this branch. Current direct additions are already cheap; the data is not evidence for another batching optimization. |
| A12 #464, AUD-015/087 | Last 50 baseline commits: median one production file, seven >30, largest 132. This is a fresh scoped inventory, not the historical nine-commit claim. Template guidance triggers early design review for broad changes/new APIs and records semantic slices, round/SHA/findings/dispositions. Line/file counts never approve a change. |
| AUD-077/078 | Unique pickup facts have a complete archived snapshot; root instructions retain binding rules and current pointers. Current entry is about 21 KB, with 28 KiB warning / 32 KiB soft / 64 KiB reader limits. Parity/budget tests enforce the real on-disk bytes. |
| AUD-079/084 | Eight measured large skills are split in both libraries. The debug method and searchable case index remain discoverable. Recursive citation discovery and existing recursive parity run before migration; `quality/context-migration.json` records the exact reconstructed original normalized bodies and retained fragments. Active Markdown pointers follow the new anchors. |
| AUD-080 | The remaining rule inventory is below. A read-only concrete PR-state check closes the draft/base/head/closing-issue gap. No unsupported local permission hook is invented and no user approval is inferred by tooling. |
| AUD-081 | Repeated smart-symbol visibility citations now share one exact-AST fact record. Changing the expression, deleting it or duplicating it fails. Other line citations retain the original 20-line window; paths and specific anchors are repaired after extraction. No widened tolerance or weakened fallback is used. |
| AUD-082 | The Phase-14 routing row now describes maintenance of shipped work. Explicit task discrimination cases distinguish solar maintenance, investigation method, frontier selection and package delivery. Frontmatter stays authoritative and mirrored. |
| AUD-083 | Both native reviewer definitions drop the obsolete Phase-12 claim, use canonical scope pointers and define read-only design/implementation/re-review evidence responsibilities. Claude's native model pin is removed; Codex receives no foreign model syntax. |
| A13 #465, AUD-046/088 | Read-only GitHub verification confirms private reporting enabled. CODEOWNERS names the existing owner only. Commit-linked aliases are mapped; an unlinked professional identity stays separate. The continuity runbook states recovery steps, security ownership and the uncompleted owner-only backup/recovery actions without assigning privileges. AUD-075/091 were already delivered and remain intact. |

## Current structure and import measurement

The original issue line citations were stale. The current baseline was:

| Host file | Before lines | After lines (initial extraction inventory) |
|---|---:|---:|
| Application | 9357 | 6692 |
| Canvas view | 5882 | 4268 |
| Resize/rotation/vertex handles | 3757 | 1282 |
| Properties panel | 2983 | 2668 |

Final counts can vary slightly with typing/docs. Reproduce with
`scripts/measure_audit_structure.py --baseline 003c4bc4 --output build/structure.json`.
The full sample inventory is retained in `audit-392-structure.json`. Counts are
descriptive; clean boundaries and preserved workflows are the acceptance criteria.
No dependency or `.ogp` schema change was required.

## Native performance evidence

`audit-392-performance.json` retains all samples. Windows build 26200, Python
3.11.9, Qt 6.11.0, native Windows Qt, Intel family 6/model 151, no coverage
tracing. The frozen self-test rendered on an NVIDIA RTX 3090. Caches were not
flushed; these are fresh-process/repeated measurements, not certified cold boots.

- Frozen launch to painted event-loop callback: **2329.0 / 2319.7 / 2230.9 ms**.
- Source application open/save/PNG median: **161.93 / 46.82 / 1540.23 ms**.
  Export is the production PNG path at 300 DPI and 42 cm width: **4960×2976**,
  preserving the plan's aspect ratio. It uses A3 landscape width, not A3 sheet height.
- Idle after settling: **30 seconds**, **0 scene callbacks**, **0 minimap renders**.
  RSS **232,513,536 → 232,505,344 bytes**, about **222 MiB**.
- Direct/batched additions at 100 items: **2.65 / 3.61 ms**; at 500:
  **12.67 / 16.05 ms**. These samples do not justify changing #450's implementation.

A prior source startup sample took 7195 ms and its second theme pass alone took
about 850 ms. That measured repeated work justified replacing the second complete
stylesheet/listener application with the canonical new-window refresh. Source
and frozen totals are different profiles: no speed-up ratio is inferred from them.
The existing NFR-PERF-01 pan/zoom scenarios remain separately gated.

## What the live measurements found

The first native harness bypassed the application's open orchestration and ran
service-level reloads/exports without normal event-loop turns. It aborted inside
the second scene render. Tagged stage output and faulthandler located that exact
sequence. The harness now calls `_load_project_file`, the production GUI/MCP
open path, and services normal queued events between operations; all three
native rounds complete. The precise native object-lifetime mechanism was not
diagnosed, and no product fix is claimed for it. The driver regression test
requires two real opens and actual PNG dimensions so a future shortcut cannot
silently return to that invalid measurement setup.

Child isolation initially intercepted the retired settings alias, not its new
implementation. A tagged loader trace with caller stack showed the loader's
module argument differed from the object in `sys.modules`. Moving the hook to
the defining module fixes the failure before any store is built. The existing
synthetic macOS test also exposed incomplete cleanup after a new shared resolver
was introduced. Both failures were observed before their corrections; the debug
reference records the evidence. Private dense-handle spies were retargeted to
the defining module without changing their behavioral assertions.

## Remaining rule enforcement and owner responsibilities

| Rule | Machine enforcement / deliberate boundary |
|---|---|
| Feature branches, master base, matching head, draft state and closing keywords | `check_delivery_state.py`; protected master policy. A local shell can still create arbitrary refs; no cross-host permission system is claimed. |
| CI-owned tags/releases | Existing release provenance/classification/gate-command tests and protected finalization. Agents must never issue manual tag commands. |
| Source and catalog translations | Source/catalog/compiled gate for all locales plus review of unwrapped display text. |
| UTF-8, parity, context size, citations | UTF-8 parsers, recursive parity/citation gates, on-disk budgets, exact fact records and migration hashes. |
| Integration, frozen artifact, independent review | Actual recorded runs; template exposes unmet gates. A declaration cannot substitute for evidence. |
| Ready/merge, release rights, private recovery material, backup maintainer | Explicit owner action/authorization remains necessary. Neither metadata nor a hook can infer it. CODEOWNERS grants nothing. |

The account/permission and recovery conditions are intentionally not automated.
Revisit host hooks only when a supported cross-host mechanism can preserve
explicit session authorization. Revisit maintainer continuity when the owner
nominates a backup or exercises recovery. These dispositions are recorded in
ADR-068 rather than silently removing the original policy.

## Review and validation record

Design round 1 identified settings module identity, shutdown order, translation
contexts, moved censuses and recursive host-skill exclusions. Those constraints
are implemented and pinned. Checkpoint review independently reproduced the
dense-handle spy failure; the correction targets the defining module.

Final gate numbers and clean final review are recorded in the PR on its verified
head; this section is updated with the final receipt before handoff. Owner
manual acceptance and wiki publication remain pending until protected merge.

### Final local receipt (29 October 2026)

[Machine-readable receipt](audit-392-validation.json): 20,181 regular tests
passed / 264 skipped / 0 failed; serial performance 81 passed / 12 skipped /
0 failed. The skips include opt-in render/platform cases; the complete opt-in
3D board was not run locally because this package changes no 3D look. The rebuilt
frozen executable separately passed its native engine-frame self-test.
Ruff, all three source/catalog/compiled translation catalogs, zero-exception
import boundaries, context parity/migration/citations and six offline wiki pages
passed. Bandit reports zero HIGH findings; secrets and lock/export checks pass.
Mypy has 1,614 existing findings and zero per-file regressions, with zero new-file
allowances. A Linux static target check on Windows gives the same result; hosted
Linux evidence remains a distinct CI result.

After review corrections, the strict locked environment, frozen rebuild,
70-distribution inventory, survival smoke (124) and detached self-test (0) passed
again. The existing settings-restoring dogfood harness passed all **52** live MCP
checks against that rebuilt executable. An earlier custom live probe was rejected
by automatic action review; the safer existing harness completed the required
transport/provider verification and restored the affected settings and MRU list.

The final fresh-worktree re-review has no outstanding P0/P1. It verified all 174
Claude debug reference files are tracked and independently reconstructed the eight
original skill bodies. Its P2 about routing evidence is also addressed with
negative scope-signature assertions; no semantic model routing is claimed.
The reviewed source tree is recorded in the receipt. This appended receipt is a
documentation delta; hosted CI and owner acceptance are reported separately in
the PR. Wiki publication remains pending after approval and protected merge.

### Hosted coverage registration correction

The first hosted run passed tests, both render tiers and the frozen self-test,
but its aggregate coverage gate correctly refused the new `config` package:
`Missing package or floor entry`. It measured 449/471 statements (95.3%).
Registering a 95% line floor preserves every existing package/file floor; no
baseline is lowered. The source-package inventory regression was observed
failing for the missing `config` entry before the correction. It now detects an
unregistered package without requiring a full traced run. The hosted gate still
checks actual unrounded coverage counts.

The correction's fresh-worktree re-review has no P0/P1/P2 findings; the full
regular suite was rerun (20,181 passed, 264 skipped). The follow-up reviewed tree
is recorded separately from the original implementation review in the receipt.

### Master synchronization after v1.34.4

The branch incorporates master `eb0eda0f08691592469482ed880b4009bb2e573e`
(PR #639 and version-sync PR #642). The atomic move/membership builder from #635
now lives in the extracted `AgentHost`, with explicit application delegates;
the move and link still execute as one compound command. The upstream
move-in/move-out/absolute-position integration tests exercise this merged path.
The holder sun, drape, power-throttling and Node 24 CI changes remain the
upstream implementations. Regenerated catalogs retain every supported locale.

The compact root context and shared smart-symbol fact references remain in
place. Current architecture references now describe atomic agent reparenting;
the migration manifest preserves original hashes and records this later
semantic update separately. The latest validation and rebuilt-artifact results
are reported on the synchronized PR head; earlier receipts above remain dated
evidence for their original heads. Owner acceptance is still pending.
