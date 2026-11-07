# Open Garden Planner - Instructions for Coding Agents

PyQt6 desktop app for precision garden planning with CAD-like metric accuracy.

## Quick Reference

```bash
# Run app
venv/Scripts/python.exe -m open_garden_planner

# Run tests. `addopts` runs these in parallel (`-n auto --dist worksteal`) and
# deselects the `perf` marker. 673.6s serial -> 156.2s at `-n 8` (4.31x); `-n auto`
# measured 68-90s on the dev box across this change's own runs. Compare ratios, not
# absolute seconds - this machine drifts 37-63% with no code change (#509, #616, 8.10.4)
venv/Scripts/python.exe -m pytest tests/ -v
# The timing-sensitive tests, which must not share a runner with workers.
# All THREE details are load-bearing: `tests/` (marked cases span directories),
# `-m perf` (or addopts' `-m 'not perf'` wins and nothing runs), and
# `-n 0` (running these across workers is what the split exists to prevent).
venv/Scripts/python.exe -m pytest tests/ -m perf -n 0
# One file or a few tests: `-n 0` avoids paying worker start-up. Measured on the
# file below (24 tests): 12.2s serial against 17.0s under `-n auto`.
venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py -v -n 0

# Lint
venv/Scripts/python.exe -m ruff check src/

# Security scan
venv/Scripts/python.exe -m bandit -r src/ --severity-level high

# Build & verify exe (before every merge) — BOTH checks.
# Sync the lock first: removing a pin does not uninstall a package, and
# PyInstaller can still bundle it (#538).
$env:UV_PROJECT_ENVIRONMENT='venv'  # PowerShell (Git Bash: UV_PROJECT_ENVIRONMENT=venv)
uv sync --locked --python 3.11 --all-extras --group build --no-install-project
# Reinstall the project editable, or `python -m open_garden_planner` dies with
# "No module named open_garden_planner": `--no-install-project` leaves the
# project itself out of the exact sync set, so uv removes it (docs/07 §7.6).
uv pip install --python venv/Scripts/python.exe --no-deps --no-build-isolation --editable .
venv/Scripts/python.exe -m installer.build_environment --strict
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
powershell -Command '$p = Start-Process "dist/OpenGardenPlanner/OpenGardenPlanner.exe" -PassThru; Start-Sleep -Seconds 8; if ($p.HasExited) { exit $p.ExitCode } else { Stop-Process -Id $p.Id; exit 124 }'
# Exit code 124 (killed after 8 s) = success
powershell -Command '$p = Start-Process "dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList "--selftest" -Wait -PassThru; exit $p.ExitCode'
# Exit code 0 = the Agent API server binds, the A1 checks pass, AND the
# Qt Quick 3D engine renders one hidden frame from the bundle's own QML and
# shaders with the right pixels — #277's lesson: a lazily loaded part is
# exercised in the real artifact (no GPU needed; its log lands beside app.log,
# or where OGP_SELFTEST_LOG says). It FAILS under QT_QPA_PLATFORM=offscreen.
# The 8-s smoke only proves the process stays up; --selftest is what sees a
# silently-dead subsystem (#291 hid from the smoke for six releases). Must be
# Start-Process -Wait -PassThru: PowerShell does not wait on a GUI-subsystem
# exe, and a shell-piped run hands it a real stdout so it cannot reproduce the
# no-inherited-handle condition #291 needs.

# Update all catalogs, complete every supported target, compile and validate
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/update_translations.py
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/fill_translations.py
# Complete any remaining translations in all target .ts files, then:
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/compile_translations.py
.venv/Scripts/python.exe scripts/check_translations.py
# Required Test CI checks source + all registered locales + actual compiled lookups.
```

Tech stack: Python 3.11+ | PyQt6 | QGraphicsView/Scene | pytest + pytest-qt | ruff | mypy
Use context7 as required for up-to-date library documentation.

## Debugging

**Use `/debug-verbose` at the first sign of any non-obvious bug — before theorising.**

The skill instruments the relevant code with `print`-based logging (stdout, no config needed), then the bug is reproduced manually and the output is read. Fix from evidence, not assumptions.

Key rules:
- Always include `traceback.format_stack()` at "unexpected call" sites — this is what reveals external callers (e.g. the minimap hiding the label editor).
- Prefix every print with `[TAG]` so output is grep-able.
- Remove all instrumentation before committing; the fix stays, the prints don't.
- After each fix, add a **Case study** entry to the `debug-verbose` skill in both agent skill libraries (symptom, wrong theories, key log line, root cause, lesson). The skill grows with the project.

## Documentation & Knowledge Base

Architecture documentation follows arc42 in `docs/`. This project uses **continuous documentation** — every feature and fix should leave the docs better than found.

### Finding Information

| Need                                 | Location                                              |
| ------------------------------------ | ----------------------------------------------------- |
| User stories, acceptance criteria    | `docs/roadmap.md`                                     |
| Module structure, project tree       | `docs/05-building-block-view/`                        |
| CI/CD, installer, release process    | `docs/07-deployment-view/`                            |
| i18n rules, translation how-to       | `docs/08-crosscutting-concepts/` section 8.3          |
| QGraphicsView widget patterns        | `docs/08-crosscutting-concepts/` section 8.9          |
| Integration test policy (MANDATORY)  | `docs/08-crosscutting-concepts/` section 8.10         |
| Security scanning / SAST (Bandit)    | `docs/08-crosscutting-concepts/` section 8.11         |
| Known pitfalls                       | `docs/11-risks-and-technical-debt/pitfalls/` (index in pitfalls/index/; ADR-061) |
| Debt register, latest repo audit     | `docs/11-risks-and-technical-debt/` §11.3 + `audits/2026-10/audit-2026-10.md` (ADR-047) |
| **Bed-only features (menu, badge, …) — READ FIRST before adding any bed feature** | `docs/08-crosscutting-concepts/` § 8.14 + ADR-017     |
| Functional requirements (FR-*)       | `docs/functional-requirements.md`                     |
| Architecture decisions (ADRs)        | `docs/09-architecture-decisions/`                     |
| Glossary                             | `docs/12-glossary/README.md`                          |
| GitHub wiki sources and publication | `docs/wiki/README.md` (sources in `docs/wiki/`; separate checkout `../open-garden-planner.wiki/`) |

### Skill Library (`.claude/skills/` and `.agents/skills/`)

Claude Code or Codex auto-loads each skill's `name` + `description` and invokes it via the
Skill tool when a task matches. **The authoritative trigger for each skill is its
frontmatter `description`** — this table is a routing map, not a substitute. Reach
for a skill *before* acting, not after. Three pre-existing skills (`debug-verbose`,
`finalize-us`, `analyze-pr`) plus the `senior-reviewer` agent are documented elsewhere
in this file; the `deliver-package` workflow skill and the 19 `ogp-*` skills below cover
the rest. The 3D agents `ogp-3d-creator` (builds) and `ogp-3d-reviewer` (judges) serve step 7.

| Skill | Reach for it when… |
| ----- | ------------------ |
| `deliver-package` | taking on a whole cluster of issues at once ("take the next package", "pick the next issues and implement them", "deliver package N") — ground truth → choose → implement → gates → senior-review → draft PR |
| `ogp-change-control` | starting any change, branching, opening/merging a PR, versioning, or unsure whether an action is allowed |
| `ogp-architecture-contract` | designing a feature, adding a module, or touching serialization / undo / layers / beds / agent_api — "is this allowed architecturally?" |
| `ogp-failure-archaeology` | about to change a subsystem with history, or tempted to "fix" code that looks wrong (it may be a scar) |
| `ogp-debugging-playbook` | a bug is reported, a test fails unexpectedly, CI is red while local is green, or a canvas/export glitch appears |
| `ogp-qt-cad-reference` | touching canvas items, coordinates/Y-flip, rendering/export, rotation/resize, snapping/constraints, handles, or Qt tests |
| `ogp-garden-domain-reference` | touching species / beds / soil / tasks / calendar / harvest / companion logic, or decoding a diagnostic or domain term |
| `ogp-config-and-flags` | adding/changing a setting or flag, configuring env, or a feature seems mysteriously disabled |
| `ogp-build-and-run` | setting up the env, running the app or tests, building the exe/installer, or an import/build error appears |
| `ogp-diagnostics-and-tooling` | you need to MEASURE instead of eyeball — quality gates, live-plan inspection, mojibake, git archaeology |
| `ogp-validation-and-qa` | writing tests, deciding if work is "done", preparing a PR, or judging whether evidence suffices |
| `ogp-docs-and-writing` | finishing any feature/fix and owing doc updates, writing an ADR/FR/pitfall entry, or unsure where knowledge lives |
| `ogp-external-positioning` | writing README/release notes, adding a dependency/service, licensing questions, or any public capability claim |
| `ogp-3d-sunshade-campaign` | maintaining shipped 3D/sun/shade, shadows, growth, height or solar math |
| `ogp-proof-and-analysis-toolkit` | about to assert a library/geometry/tolerance/coordinate-frame fact — "prove it, don't just install it" |
| `ogp-research-frontier` | picking the next big direction, or scoping D2/D3 / Phase-14+ ambitions |
| `ogp-research-methodology` | starting an investigation, forming a hypothesis, or deciding whether evidence suffices to adopt a change |
| `ogp-asset-forge` | adding/regenerating a texture or 2D art asset — house style, tileability gate, provenance rules (US-E9) |
| `ogp-lush-cinematic` | building or judging anything visible in 3D (Phase 17) — truth gates, style values, light rigs, Beauty Board, rubric, owner taste log |
| `ogp-3d-renderer` | touching Qt Quick 3D code, hosts, picking, screenshots, CI rendering or packaging — measured engine facts and traps |

**Maintaining this table:** add a one-line row when a new skill lands; keep the real
trigger in the skill's `description`. If a row and a `description` disagree, the
`description` wins — fix the row.

References inside skill files are gated (§8.10) — keep them resolvable:

```bash
venv/Scripts/python.exe scripts/check_skill_citations.py
```

### Claude/Codex context parity

`CLAUDE.md` and `AGENTS.md` are a synchronized pair. If either file changes, update
both in the same change. Project-owned skills must exist in both `.claude/skills/` and
`.agents/skills/`; the native senior-reviewer definitions must stay aligned in
`.claude/agents/` and `.codex/agents/`. Run the read-only parity gate before opening or
closing a PR:

```bash
venv/Scripts/python.exe scripts/check_agent_context.py
```

Host-provided skills and local settings remain ignored. The gate intentionally reports
drift instead of overwriting either agent's native file format.

### Contributing to Documentation

**After implementing a feature:**
| Change Type | Update Target |
|-------------|---------------|
| New component/module | `docs/05-building-block-view/` — add black box description |
| New UI pattern | `docs/08-crosscutting-concepts/` section 8.9 |
| Changed runtime behavior | `docs/06-runtime-view/` — update sequence diagrams |
| New user-facing capability | `docs/functional-requirements.md` — add FR-* entry |
| Architecture decision | `docs/09-architecture-decisions/` — create ADR |
| New domain term | `docs/12-glossary/` — add definition |

**After solving issues, all lessons learned MUST be documented:**
| Issue Category | Document In | Capture |
|----------------|-------------|---------|
| PyQt6 quirks | `docs/11-risks-and-technical-debt/pitfalls/` (area file; index row in pitfalls/index/) | Rule → Pinned by → Fix |
| Performance issues | `docs/08-crosscutting-concepts/` | Optimization technique |
| Testing patterns | `docs/08-crosscutting-concepts/` 8.10 | How to test this pattern |
| Security fixes | `docs/08-crosscutting-concepts/` 8.11 | Vulnerability + mitigation |

**ADR triggers:** Create ADR when introducing new dependencies, choosing between approaches, changing patterns, or addressing non-obvious constraints.

**Before merge, verify:** arc42 docs updated, ADRs created if needed, glossary updated, wiki sources validated with `scripts/sync_wiki.py --check`. Publish the wiki manually after owner approval and protected merge (ADR-051). Reconcile direct wiki edits before copying pages. Report publication pending until it is complete.

## Versioning Protocol

**GitHub releases are THE source of truth.** CI auto-creates tags/releases on non-chore push to master.

```bash
# Find current version:
"C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
```

- CI **defaults to patch** bump
- Add `minor` or `major` **label** to PR for bigger bumps
- After merge, update both `pyproject.toml` and `src/open_garden_planner/__init__.py` to match the CI release
- Deliver version sync as a reviewed `chore:` PR (release CI skips its squash commit). `finalize-us` handles this PR automatically under the original finalization authorization; no second manual confirmation is needed. Refresh the lock offline with `scripts/prepare_version_sync.py`.

**Never create git tags manually.**

## Plan Mode

**Avoid the recurring "File has not been read yet" Write failure on the plan file.**
Plan mode pre-creates the plan file, so `Write` (and `Edit`) reject it until it's been read this
session. Build the plan with the **`Edit`** tool (incremental edits — what plan mode tells you to
do). If you must overwrite it wholesale, **`Read` the plan file once first, then `Write`.** Never
`Write`/`Edit` a pre-existing file blind — the same rule applies to any file you didn't create this session.

## Workflow

**CRITICAL: Always use feature branches — NEVER commit directly to master.**

> **MUST — every coding job ends with a draft PR.** Any task that changes code (feature, bug fix, refactor, doc-in-code, chore) finishes by pushing the branch and opening a **draft** pull request — never leave the work as just a pushed branch. Open the draft only **after** the `senior-reviewer` pass is fully satisfied (no outstanding P0/P1) — or, if the pass genuinely cannot be run, with the unmet gate stated in the PR body and no move toward merge (`ogp-change-control` §2.4). The PR stays a **draft** until the user confirms manual testing passed; only then mark it ready and merge. Do NOT open a non-draft PR or merge without explicit user confirmation.

| Step | Action | Notes |
|------|--------|-------|
| 1 | Create branch: `git checkout -b feature/US-X.X-short-description` | Before any changes |
| 2 | Read user story from `docs/roadmap.md` | Understand acceptance criteria |
| 3 | Implement with type hints & translation | Use `self.tr()` for all UI strings |
| 4 | Run quality checks | `pytest tests/ -v`, `ruff check src/`, `bandit -r src/ --severity-level high` |
| 4a | Update translations | Run `scripts/update_translations.py`, complete every registered target locale, compile, then pass `scripts/check_translations.py`; new source and new locale additions use the same gate (#496) |
| 5 | **Write integration test** in `tests/integration/test_<feature>.py` | **Mandatory** — end-to-end UI workflow. See `docs/08-crosscutting-concepts/` 8.10 |
| 6 | Build & verify exe | See Quick Reference |
| 7 | **Run senior-reviewer pass** | Launch the `senior-reviewer` agent in a fresh worktree against the branch diff. Address any P0/P1 findings before proceeding. Re-run after fixes for a clean re-review. The `finalize-us` skill repeats this step pre-PR. A change visible in 3D first passes `ogp-3d-creator` → `ogp-3d-reviewer` with no P0/P1. |
| 8 | Provide testing checklist | Surface a manual-testing checklist alongside the work |
| 9 | Commit: `feat(US-X.X): Description` | Conventional commit format |
| 10 | Push & **open DRAFT PR** | After a clean senior-reviewer pass, push and open a **draft** PR automatically (`pr create --draft`). **Every coding job ends here — never stop at just a pushed branch.** Keep it a draft and **do NOT merge** until the user confirms manual testing passed — only then mark ready (`pr ready`) and `pr merge --squash --delete-branch --match-head-commit <verified-head-sha>` |
| 11 | Sync version on master | See Versioning Protocol (after merge) |
| 12 | `/clear` context | Clear Agent context

## Translation (i18n)

> **MUST — every feature, no exceptions.** Every user-visible string added in any file MUST be wrapped for translation. Skipping this is a bug.

- `QWidget`/`QDialog` subclasses → `self.tr("string")`
- `QGraphicsItem` context menus (non-QObject) → `QCoreApplication.translate("ClassName", "string")`
- Module-level dicts → `QT_TR_NOOP("string")`, translate later with `QCoreApplication.translate()`
- `CollapsiblePanel(title)` → wrap at the **call site**, not inside the panel
- **Hardcoded English f-strings (`f"{a} overlaps {b}"`) bypass `tr()` and never reach Qt Linguist** — use `self.tr("{a} overlaps {b}").format(a=…, b=…)`. The required `scripts/check_translations.py` gate derives wrapped keys from source and checks every registered locale; truly unwrapped display text still requires review. The legacy German unfinished-string test is retained as an additional regression check. Pattern: if it's user-visible text, it MUST go through `tr()` / `QT_TR_NOOP` / `QCoreApplication.translate()` — registering it in `scripts/fill_translations.py` alone is insufficient.
- **NEVER use PowerShell `Set-Content -Encoding UTF8`** for files with non-ASCII (umlauts etc.) — double-encodes UTF-8 into mojibake. Use the `Edit` tool or Python `open(..., encoding="utf-8")`.

Full how-to (step-by-step, `.ts` format, recompile command): see `docs/08-crosscutting-concepts/` section 8.3.

## Testing Notes

- PyQt6 tests require `qtbot` fixture even when unused (needed for Qt init); ruff per-file ignore ARG002 in test files
- Real windows of tests and probes open behind everything without taking focus (`scripts/quiet_windows.py`; `script_isolation` turns it on). `OGP_WINDOWS_IN_FRONT=1` to watch one.

## Where to Pick Up After Restart

- The issue tracker is the only work list. Read the relevant issue and roadmap
  acceptance criteria, then `git status` and `git log --oneline -20`.
- Current shipped capabilities and release evidence: [roadmap](docs/roadmap.md).
  Runtime/geometry contracts: [ADRs](docs/09-architecture-decisions/README.md)
  and the `ogp-architecture-contract` skill. Consult the relevant subsystem
  reference before changing an implementation that looks unusual.
- Capture quality and L6 hygiene (#733, #735, #738) shipped in **v1.37.6 (PR #759)** after
  owner manual acceptance on 2026-11-06: a 4K picture's horizon band keeps 1080p's look by
  scaling SSAO's radius with the capture height (the review's glow suspicion was measured
  and rejected; PF-E3D-25); a picture uses the view's preset, the MP4 keeps its pinned
  BT.709 HD convention, and the smaller L6 findings are closed (PF-E3D-26). See the
  roadmap.
- UI, plant services, agent prompts, and weather architecture (#772, #765, #763, #724, #693)
  implemented on branch `feature/772-765-763-724-693-ui-services-hygiene`:
  accordion hover transit hysteresis (8px buffer); plant profile header asynchronous thumbnail worker;
  permapeople credentials loaded from AppSettings before env vars; `plan-my-week` prompt
  defaulting to simulated plan date; and application-level `ForecastHolder` decoupling weather
  lifecycle with zero-timer coalescing, stale cancellation, and synchronous re-emission.
- Engine, smart symbols, and CAD hygiene (#688, #720, #723, #692, #689) shipped in
  **v1.37.7 (PR #762)** after owner manual acceptance on 2026-11-07:
  compost_bay_3 repeating bays aspect ratio; dead GLSL removed and TWO_SIDED_KINDS
  moved to core.scene3d.materials; waitUntil test race elimination; offscreen
  deferred deletion flush preventing exit crash; modulo float precision for
  precipitation shader, midnight Today's Weather timer, and unified living_buffers.
- 3D curved geometry and strings (#675, #709, #705, #701) shipped in
  **v1.37.5 (PR #756)** after owner manual acceptance on 2026-11-06: arc-length fence
  spacing, 40 cm string posts with a 2.5 cm chord rule, centroid/nearest-bulb lights,
  and cached shadow-walk roof meshes.
- Sky/render-tier integrity (#695, #696, #704, #714, #717, #718, #722) shipped in
  **v1.37.4 (PR #755)** after owner manual acceptance on 2026-11-06: connected
  white-plateau disc finder, world-elevation set-sun probe (`measured=False` fails
  closed), 3.6 far-row bound at 640 × 360, flood scoped to the rebuild, `scene_reset`
  clears the forge queue, 300 ms settle + 1 s ceiling.
- Distribution trust (#375, ADR-073) decided 2026-11-06: Authenticode for the GitHub installer
  stays deferred (Azure Artifact Signing is unavailable to an individual outside USA/Canada;
  SignPath signs in its own name; Certum Open Source at EUR 49-69/year is trigger 3's concrete
  shape), and the **Microsoft Store is a second channel**: `installer/build_msix.py` packages the
  same bundle as an MSIX, `release.yml` builds it after the attestation (`continue-on-error`,
  workflow artifact `store-package-v<version>`), `msix-store-verify.yml` is the runner-side install +
  self-test measurement (PF-CI-19/20; its result is recorded in ADR-073, not assumed). The listing is **pending** the owner's Partner Center registration
  and the three `OGP_MSIX_*` repository variables (docs/07 §7.2a). Never claim Store availability
  before the first certified version is live.
- Geometry, weather resilience, lighting & test hygiene (#748, #702, #697, #694,
  #685, #706, #707, #708, #710, #700) shipped in **v1.37.3 (PR #752)**: Angled house polygon roof ridge aligns with
  dominant MABB/PCA axis with deduplicated intersection parameters; localized forecast
  card weekdays (`current_locale`); location readers outside L5 route through `plan_place`
  (safe on hostile plan numbers); stale frost alerts cleared on File > New, load, and failed fetch;
  PID collision mock in `Init3DGuard` tests; 2D string lights paint order (glow, wire, posts, bulbs);
  string lights thumbnail moved to `string_lights_paint.py`; 3D string lights wire segments doubled
  and bulbs tessellated (12 segments, 5 rings); and shadow agreement prose pruned to defer to ADR-059.
- 3D hardening, touch/region/CI, and bed/constraint reconciliation (#535/#578/#619, #443/#485, #321/#451) shipped in v1.34.7–v1.34.9 (PRs #647, #649, #650); details in [history](docs/agent-pickup-history.md).
- 3D performance and stability, Slice A (ADR-069): #452 shipped in v1.34.11 (PR #676)
  — a whole-plan read is sliced at 4 ms with heavy builders on one worker lane
  (heartbeat p95 1.7–3.6 ms on the issue's plans, was 4.0–12.6 s in one block). #531
  (in-place Model reuse) and #598 (sparse seasonal index) were built and WITHDRAWN:
  both render tiers draw a replaced geometry as nothing while still picking it. #475
  (raster lane, padded tiles) and #534 (wind memory) are open.
- 2D drawing-tools package (#674, #665, #690) shipped in v1.36.2 (PR #713) after
  owner manual acceptance: Group/Ungroup on every item's context menu with one-step multi-group
  ungroup (FR-EDIT-22), per-object fill angle/scale/offset as additive appearance
  metadata with roof-frame composition (FR-EDIT-23, ADR-071), and a HOUSE ridge created
  by a type change in the same undo step (FR-EDIT-24, ADR-046 addendum). #664 (split
  along line) and #688 (smart-symbol texture stretch) were deliberately left for a
  follow-up slice.
- 2D drawing & CAD integrity follow-ups (#741, #740, #727, #726, #703, #712; FR-EDIT-25)
  shipped in **v1.37.1 (PR #747)** after owner manual acceptance on 2026-11-05:
  `ROOF_RIDGE` excluded from `groupable_selection()`; fresh linked ridges created on
  array (`LinearArrayCommand`, `GridArrayCommand`, `CircularArrayCommand`, `ArrayAlongPathCommand`),
  offset, and mirror copy of groups containing a `HOUSE`; project load sanitises legacy/stale
  `ridge_item_id` and orphan `owner_polygon_id` links; `ArcItem`, `BezierItem`, `ConstructionLineItem`,
  `ConstructionCircleItem`, `CalloutItem`, and `TextItem` route context menu and Delete key through
  `dispatch_delete_selection`; grouping houses across layers normalises member and ridge layers to
  the group layer with undo restoration and canvas visibility fallback; `delete_object` on groups
  prunes nested journal notes in the same compound undo step; path presets default to 80 cm and
  preserve user-set widths on style switch; paved paths use flat caps and bevel joins eliminating
  rounded lobes in 2D and agreeing with 3D kerb mesh; and plan loader enforces `MAX_POLYLINE_VERTICES` (16,384).
- Capture-session integrity package (#730, #731, #732, #745) shipped in v1.37.2 (PR #750):
  a tour holds the clock only when it moves it, and agents use the owner's date during
  a time-lapse (ADR-072 addendum); a kept `.part.mp4` survives, Esc/X ask after 10 s, and
  app close waits for the writer (PF-E3D-22); a year's tour holds UTC across DST (1.53
  vs 18.07 luma; ADR-053 addendum L6, PF-E3D-24); applied blur always has a point,
  using the ground under the view's centre while walking (PF-E3D-23).
- Phase 17 L5 (#389) shipped in v1.35.0 (PR #699); details in
  [history](docs/agent-pickup-history.md). Load `ogp-lush-cinematic`/`ogp-3d-renderer` before a
  visible 3D change; `ogp-3d-sunshade-campaign` for sun, shade, growth or solar maintenance.
- L6 (#390, ADR-072) is the Director's cut: one capture path (`Quick3DHost.capture`),
  photo mode, camera tours, video (`video_writer.py`) and the read-only `render_3d_view`;
  shipped in v1.37.0 (PR #729). A plant's rect follows `CanvasScene.drawn_plan_date`
  (PF-CAN-43); Ultra's reflections + blur + glow crashed Qt (PF-E3D-21, #744); its
  follow-ups are PF-E3D-18/19/20 and #745. Details: [history](docs/agent-pickup-history.md).
- L7 (#391, ADR-048 addendum L7) shipped in v1.36.0 (PR #721): Qt 6.12 pins and an opt-in
  atmosphere sky that only DRAWS (PF-E3D-14/17); details and follow-up numbers in
  [history](docs/agent-pickup-history.md).
- Russian localization (#492, FR-I18N-09) shipped in v1.36.1 (PR #495):
  full Russian UI; details in [history](docs/agent-pickup-history.md).
- The shared SimClock retains the toolbar's local wall date (ADR-053/062).
  Subscribe to its signals. Every rect resize uses `geometry_apply.py`; every
  Arrange surface uses `build_arrange_command`; scene teardown uses
  `CanvasScene.clear()`. Read the architecture contract for the full invariants.
- Wiki sources are in `docs/wiki/`; validate offline. Publication follows
  owner approval and protected merge (ADR-051), and must be reported pending
  until completed. Never use the published Roadmap as a second tracker.
- Full pickup snapshots, including unique compatibility and owner decisions:
  [28 October snapshot](docs/agent-pickup-2026-10-28.md),
  [older history](docs/agent-pickup-history.md). These remain searchable reference
  records; the roadmap, ADRs and requirements are the docs of record.
- Keep root instructions below the soft budget enforced by
  `scripts/check_agent_context.py`; archive narrative before adding new pickups.
  Never remove binding rules to satisfy a byte limit.

**Maintaining this file:** Update the progress summary when status changes and keep the Quick Reference current. `CLAUDE.md` and `AGENTS.md` are a synchronized pair: if either changes, update both and run `venv/Scripts/python.exe scripts/check_agent_context.py`.

**Version note:** CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.
