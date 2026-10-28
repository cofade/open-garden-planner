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
| `ogp-3d-sunshade-campaign` | starting or resuming Phase 14 (3D, sun/shade, shadows, height property, solar math) |
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

## Where to Pick Up After Restart

- **Agent move atomicity, plant holder sun exposure, shade mask memory, Windows power throttling opt-out, and Node 24 CI (#635, #621, #579, #616, #637) delivered on 2026-10-28.** #635 wraps agent reparenting moves in `CompoundCommand` for atomic one-step undo (matching GUI #627, FR-EDIT-21, ADR-034); #621 marks cold frames, planter pots, and greenhouses in `holds_plants` to spare contained plants from false 0 h shading and mismatches (FR-SUN-05, ADR-065 addendum); #579 avoids allocating up to 64 MiB shade masks unless 3D progressive drape opts in; #616 opts local Windows test runs out of EcoQoS background power throttling (PF-TST-33, §8.10.4); #637 upgrades GitHub Actions to Node 24 runtimes and pins `ubuntu-24.04`.

- **Download chart accepted by the owner on 28 October 2026 ("perfect").** ADR-067 addendum / FR-STATS / deployment §7.4 own frozen historical estimates, UTC day/week/month/year sums and Pages setup. Tooling-only chore; deployment follows protected merge.

- **Batch #444/#481/#620/#628/#629 shipped on 2026-10-28 as v1.34.3 ([PR #627](https://github.com/cofade/open-garden-planner/pull/627)) after the owner's manual pass ("Manual testing is perfect").** A closed fence's shadow is its stroke, a crossing outline its lobes, the sun estimate spares the bed a plant stands in, a plant draws above its bed, any footprint can take a height and the raised object keeps its fill — on its TOP (tinted sides, no smear) with a raised lawn's blades and a raised pool's water picture intact — and a plant dropped into a bed is ONE undo step, as is a bed dragged with its plant; a bed dragged alone carries its child with no lag. ADR-037/043/056 addenda, FR-SUN-02/09, FR-STACK-10, FR-3D-BUILT-09, FR-EDIT-21, PF-DOM-28, PF-CAN-28/29, PF-UI-29, PF-L3D-17. Follow-up #635 (an agent move that reparents a plant still records two undo steps).

- **Test lifecycle, popup focus, release classification, and 3D workspace modularization (#561, #515, #460, #463, #583, #580, closes #447) shipped on 2026-10-28 as v1.34.2 ([PR #632](https://github.com/cofade/open-garden-planner/pull/632)) after owner acceptance.** #515 / AUD-019 / #447 parent CategoryDropdown to CategoryToolbar to reclaim 870 leaked widgets on close and prevent stylesheet re-polish access violations; #561 suppresses focus-stealing popups during automated test runs via WA_ShowWithoutActivating; AUD-018 documents the test layer contract in §8.10; AUD-038 / AUD-086 / AUD-090 add tag disposition checking, ADR-050 evaluation addendum, and executable-vs-chore release classification; #583 modularizes ui/view3d/workspace.py from 2,381 to 1,861 lines by extracting selection, walk, analysis, wipe, and legend coordinators with typed protocols; #580 expands info card body line budget to 8 lines to keep all fact rows visible at narrowest 455 px split pane width; #577 de-scoped for dedicated geometry research to maintain clean ground drape occlusion.

- **Phase 17 L4 follow-up hardening (#611, #607, #604, #617, #624, #618, #609, #600, #603, #626, #536) shipped on 2026-10-27 as v1.34.1 ([PR #630](https://github.com/cofade/open-garden-planner/pull/630)) after owner executable acceptance.** ADR-065 addendum, 3d-hardening-611.md. Holds context only across common parameters, Low/Medium skip blade synthesis, exact batched lawn masks, lawn normal fold without plant stubble, translucent path rims exclude inner textures via bounded device masks, corner-aware perspective shadow reach, distant horizon rows, fractional-DPR test pinning, independent admitted-mesh selection oracle, reload soak LOD rest waits, and post-presentation upload retirement.

- **Phase 17 L4 "Built world complete" (#388, closes #586 and #614) shipped on 2026-10-27 as v1.34.0 ([PR #613](https://github.com/cofade/open-garden-planner/pull/613)) after the owner's third manual pass ("all perfect").** ADR-065, §8.29.12 and FR-3D-BUILT-01…08 hold the design: builders for all 24 object kinds, roof metadata (`core/roof_style.py`, no FILE_VERSION bump; 2D sun study keeps flat roofs, #440), facades, ground detail (`MeshPart.ground_detail`, `record.BUILD_ONLY_PARAMS`), the endless meadow (`core/scene3d/meadow.py`; PF-L3D-11…14), the drag hold over lawns (`sync_controller.CONTEXT_REBUILD_MIN_MS`). The second pass gave every object without a 2D height a real, settable one (parasol, fire pit, planter pot, cold frame, rain barrel, water tap, swing, hammock, pergola) and set the detail-normal strength to 3.0; re-reviews fixed two P1s before merge (AO fade switched SSAO on at Low, PF-L3D-15; a plain-block house had a sandstone top). Smart-symbol builders deferred (#599); follow-ups #600, #603–#605, #607, #609, #611, #615–#621, #623, #624 (#621 cold-frame/planter 0 h sun; #623 exit crash).
- **Package F is complete: F5 examples/templates (#316) and dogfood fixture retirement (#379) shipped on 2026-10-27 as v1.33.0 ([PR #610](https://github.com/cofade/open-garden-planner/pull/610)) after owner executable acceptance.** Three localized teaching layouts and previews, public sun/fictional-soil demonstrations and portable template export/import share the existing loader. External/exported templates retain the strict site/history filter. ADR-066 and FR-EXAMPLE own the contracts; succession keeps explicit calendar dates. Independent visual/senior reviews, 18,504 local tests, 77 performance cases and all 15 hosted checks passed.

- **#601 CI latency work is owner-approved as a chore (PR #606, 2026-10-26); no release.** Coverage keeps
  full branch data and unchanged floors, using two stable test-ID partitions plus
  a quiet serial perf producer; the existing required Coverage check combines all
  three and fails on missing/failed measurements. Test remains uninstrumented.
  The 116-case perf audit moves 27 deterministic cases to parallel execution;
  duplicate AST/sweep work and fifty full-GC traversals are removed without losing
  their assertions. ADR-058 and `audits/2026-10/ci-latency-601.md` own the evidence.

- **Phase 17 L3 "Plant Forge" (#387) shipped on 2026-10-25 as v1.32.0 ([PR #593](https://github.com/cofade/open-garden-planner/pull/593)) after owner executable acceptance (ADR-064, §8.29.11).** 123 recipes (108 species + 15 categories), 13 archetypes, LOD caps and a 256-entry/64 MiB cache; background admission/recovery, camera-driven LOD, seasonal parts, exact harvest dates and winter bounds. The production render gates exercise the forge. Details in the roadmap and ADR-064.

- **Non-3D follow-up hardening, batch 2 shipped 2026-10-26 as v1.32.1 ([PR #596](https://github.com/cofade/open-garden-planner/pull/596)) after owner acceptance (#562/#573, #574, #581, #587, #590, #592, #594):** real offscreen fonts, command-scoped refresh, cached dense-overlay sample, one height resolver, PEP 639 metadata. Owner manual pass found and fixed: the settings guard, the version artifact (About 1.2.0; PF-CI-15), one 120 px control column + clipped-value tooltips, and species-sized gallery drops (#596; FR-PLANT-15).

- **Non-3D hardening batch #450/#551/#550/#569/#538 shipped on 2026-10-25 as v1.31.1 ([PR #585](https://github.com/cofade/open-garden-planner/pull/585)) after owner acceptance.** See the roadmap and ADR-043/061 addenda for the detail.

- **Phase 17 L2 "Analyze in 3D" (#386) shipped on 2026-10-24 as v1.31.0 ([PR #584](https://github.com/cofade/open-garden-planner/pull/584)) after owner acceptance (two manual passes; every checklist step confirmed).** ADR-063, FR-3D-ANALYZE-01…08, §8.29.10, PF-L3D-06. One "Analyze" menu in the 3D strip: the 2D shadows or the hours-of-sun map draped on the 3D ground (the 2D side's OWN polygons and map — `SunShadowController.drape_polygons()` / `shadows_changed`, `SunHeatmapController.result()` / `computed`; never a second computation), a ground probe (minutes + band, pinned), sun path + compass (`core/scene3d/sun_path.py`; noon point IS `solar_position`), a day sweep on the shared clock (per-sample masks by local time of day), info card v1 (height source, growth share, sun, sowing/harvest windows via the extracted `task_generator.calendar_windows`), +1/+3/+10-year jumps with a before/after wipe (exactly two frames, `growth_jump._grab` — the second sanctioned frame-taker), and Cutaway (roofs off + X-ray fades, `core/scene3d/xray.py`). Overlays are ONE reloadable Model each (no Model/texture churn, #531/#532). Load-bearing engine findings: a blended custom material must keep the frame's alpha (`sourceAlphaBlend: Zero`, `destinationAlphaBlend: One`) or a translucent overlay brightens the view with the window's white (PF-L3D-06); an unlit overlay goes through the mood's exposure, so the 2D shadows lie on a `"shade"` layer that MULTIPLIES the frame and overlay colours divide by the exposure (PF-L3D-07); a hidden or blended Model drops out of the shadow map, so X-ray fades and Cutaway's cut roofs are screen doors (`screen.frag`, a discard) that keep their shadows (PF-L3D-08). `LiveSunMap` owns the hours-of-sun state (`enabled_changed`): the 3D drape follows it, and the probe reads only a current map. Owner manual pass (2026-10-24): the 3D drape follows the shared Hours of Sun both ways — switched on in the toolbar it lays the map (PF-L3D-09) — and off brings back what lay there before; in 2D the ground surfaces (lawn, path, terrace, driveway, pond, in-ground bed without a height, or a group of only those: `canvas_scene.on_ground`) are drawn in `GROUND_Z_RANGE` under the shadow and hours-of-sun overlays, and Arrange works inside each band (PF-CAN-22, ADR-043 addendum, FR-STACK-09). Pass 2: the Plan & Sun strip's Past/Future label is gone; the Today button says Past or Future in its own place at one width for all three texts (`_TodayButton`, each text measured as `QToolButton` measures it; slider floor 70 px; ADR-062 addendum). Offscreen Qt on Windows draws fonts as boxes: measure widths with `QT_QPA_PLATFORM=minimal:enable_fonts` (PF-TST-26, §8.10).

- **Plant Details follow-ups #552/#557/#558/#559/#560 shipped on 2026-10-23 as v1.30.20 ([PR #566](https://github.com/cofade/open-garden-planner/pull/566)) after owner executable acceptance.** Snapshot commands cover species/instance edits; gestures and staged text respect history/save boundaries. Species spread updates centered 2D/3D dimensions while explicit overrides win. Lock menus and one upright export-hidden badge cover ordinary objects. Unknown heights use labelled illustrative 3D estimates without changing analytical heights. Plan & Sun links to Set Garden Location when coordinates are missing. See ADR-004/013/059/062, FR-TIMELINE-07 and PF-UI-27.

- **L1 follow-ups #537/#539/#541/#542 and Plan & Sun editor stepping shipped on 2026-10-23 as v1.30.19 ([PR #565](https://github.com/cofade/open-garden-planner/pull/565)) after owner acceptance:** Global workspace actions select Garden Plan; Walk has a theme-aware icon; Reset key text uses Qt translations; no-op date checks preserve the throttle timestamp. Plan & Sun editor stepping carries and borrows across month/year, hour/day and minute/hour boundaries; native date/time subclasses share one complete naive wall-reading path, preserve preferred days and stop only at SimClock's absolute limits. Arrows/repeat, wheel/buttons, leap years, range and midnight 2D/3D/sun consistency are pinned (FR-TIMELINE-06, ADR-062 addendum, PF-UI-26). Review replaced an uptime-dependent regression with controlled clocks and real date-signal/snapshot assertions (PF-TST-25). ADR-060 addendum and runtime view own the behavior. The exact stale-DPR warning is exempt because Qt corrects its cache before expose; its original cause remains unproven. No render-look change.

- **2D canvas defect batch #522/#530/#445/#446/#528 shipped on 2026-10-22 as v1.30.18 ([PR #556](https://github.com/cofade/open-garden-planner/pull/556)) after owner acceptance.** Five shipped defects on `master`, taken together because they are small, measured and pinned. The sprite resolver now matches a species name as a **whole name or alias**, not as a substring (#446): a melon was drawn as an eggplant, a scientific name as a rose, a plant whose name merely contains another plant's name as that other plant, a blank species as a rose. **Three of the issue's examples survive that fix** - "Lemon Balm", "Bean (Bush)" and "Sweet Potato" still take a fruit or vegetable sprite, because their names contain a whole word that is another plant's name; a curated alias table would fix them and was declined, so the residue is pinned in the unit test. The whole-name-only rule the issue proposed was measured first and **rejected** - it changes 266 of the golden's 1,562 answers over 110 names and most of those are regressions; the rule that shipped changes 74 over 37, and of the bundled species' 118 names exactly one changes (the melon). The assignment of a species writes the item's own species **string** - the name of the species assigned - so the plant is drawn with that species' sprite in 2D and 3D alike (#445); the string is the plant's own name, and the record's data may still name the species differently. Shift+click through an item on a locked layer toggles what lies behind it instead of replacing the selection (#522), which removes the last measured difference between the canvas and the 3D selection bridge. The seven Properties-panel edits are one undoable command each and mark the plan modified (#530). The perf-marker guard follows a measurement that travels in an **attribute**, scoped to the class that owns it, and a value that is only counted is not a duration (#528) - the ground bake's G3 gate is now required to carry its `perf` marker instead of carrying it by hand. The review follow-up also scopes function identities and both call-graph closures, pinned with the real same-module ground-bake AST and both class orders (ADR-058 addendum). Owner manual follow-ups restore the permanent toolbar row without replaying legacy topology and clear the whole Plant Details profile on species undo. Unknown-height category estimates are separate #557; maximum-width geometry sync is separate #558; Plant Details field undo coverage is separate #559, and history-aware text/numeric focus refresh is separate #560. Docs: FR-EDIT-15/16, FR-PLANT-21, FR-PLANT-ART-05, PF-DOM-26/27, PF-UI-18/24/25, PF-TST-24.

- **US-F4 (#315) shipped on 2026-10-21 as v1.30.17 ([PR #533](https://github.com/cofade/open-garden-planner/pull/533)) after owner acceptance.** ADR-062 owns lifetime visibility on the shared SimClock and the permanent adaptive Plan & Sun strip: one calendar/month scrubber, editable time, automatic shadows, live 2D Hours of Sun, guarded visual exports/API presence, and unchanged Season Manager copies. The Qt Quick 3D workspace keeps its existing growth throttle and clock subscriptions. The timeline date is not persisted. F5 (#316) remains separate.

- **Line appearance follow-ups #524/#525/#526/#471 shipped on 2026-10-21 as v1.30.16 ([PR #545](https://github.com/cofade/open-garden-planner/pull/545)) after owner acceptance:** Both type-change surfaces use new type defaults and clear the preset; exact style snapshots drive undo/redo. Styled bounds share the ground painter's reach. Multi-resolution taskbar icons and early Windows AppUserModelID configured. See crosscutting section 8.30 and the ADR-059 addendum.
- **Phase 17 L1 (#385) shipped on 2026-10-19 as v1.30.14 ([PR #484](https://github.com/cofade/open-garden-planner/pull/484)) after owner acceptance** (the 36-step manual checklist, no problems found; a patch release although the PR carried `minor`, because `release.yml` previously read the newest-created merged PR's labels, fixed in #543): the 3D view is the Plan / 3D / Split workspace of the main window on Qt Quick 3D, and the Qt 3D window, its two wheels and the L0 spike are deleted. The owner kept all seven decisions put at the PR as built, including shipping the default with Qt 6.11's ground-texture leak #532 open (ADR-060 addendum D5; the look choices are in `ogp-lush-cinematic`'s taste log). Follow-ups #534–#542 are `priority: high` — wind memory #534, the software-adapter look #535, a render-test flake #536, "3D View" from other tabs #539 and CI coverage of the default workspace #540 matter most. **L2/L3/L4 shipped in v1.31.0/v1.32.0/v1.34.0; L5 (#389) is next.** Load `ogp-lush-cinematic` and `ogp-3d-renderer` before touching 3D.
- **CI gate integrity (#512–#516) shipped on 2026-10-19 as v1.30.13 ([PR #520](https://github.com/cofade/open-garden-planner/pull/520)), after owner acceptance:** the perf-gate pin now evaluates the **command that gates the step** — the marker-selecting command must be the step's **last** command and must itself invoke pytest — closing the echo / here-doc / delegating-script / `|| true` shapes, plus `--co`/`--collect-only` (directly or inside `-o addopts=`) and `PYTEST_ADDOPTS`. The closed shapes are replayed by `scripts/replay_gate_mutations.py` (16 mutations: 14 caught, 2 passing controls; run it after touching the matcher, and run it alone — it rewrites `ci.yml`). **`Coverage` is now a required check**: the floor step is pinned (`if: always()`, reads `coverage.xml`), `check_coverage_floors.main` fails closed (exit 2 when the report is missing, malformed or unresolved), and `quality/master-protection.json` carries `Coverage` — the owner applied the live payload and confirmed `scripts/check_branch_protection.py` before finalization. #516 removed the review archaeology from its four named sites. #515 committed `scripts/probe_widget_leaks.py` and narrowed the widget-leak holder to uncollected cyclic garbage plus one graph outside Python's reachable object graph (the blanket "strong references" reading in #509 is too strong; **#515 remains open** for the residual holder). See the ADR-058 addendum and `docs/11-risks-and-technical-debt/audits/2026-10/test-suite-latency-2026-10.md`.
- **#409's low-zoom LOD flat fill removed; the cache-mode predicate stays - shipped 2026-10-17 as v1.30.10 ([PR #507](https://github.com/cofade/open-garden-planner/pull/507), #503), after owner acceptance on a rebuilt exe (smoke exit 124, `--selftest` exit 0).** `GardenItemMixin.should_use_lod_flat_fill` never ran in the product: Qt passes `widget = 0` for every *cached* paint and every unselected canvas item is `DeviceCoordinateCache`, so its guard was never true and its tests passed only by calling the helper directly. #503 fixed the guard first (one shared `is_interactive_paint` predicate on the item's cache mode, which #472's paint bound also calls), which made the branch live - then measured it and deleted it: on the 990-item reference plan both scenarios below 0.4 zoom have overlapping arms (`fit_in_view` 10.61/11.50 ms median off against 10.87 on; `zoom_step` 7.97/7.98 off against 8.20 on, i.e. the flat fill was ~3 % *cheaper* there), nothing comes near the 16.70 ms budget, all six `tests/perf/test_nfr_budgets.py` cases pass either way, and within-arm variation (8 %) is an order of magnitude above the 0.26 ms between-arm difference - `DeviceCoordinateCache` already amortises the textured `paint()` into a one-off. The owner's manual pass settled what the measurement could not: at 20-25 % zoom every texture, plant sprite and furniture sprite would have become a solid colour and the paint-level diagnostics (bed grid, rotation indicator, soil border, capacity badge, spacing ring, companion highlight, antagonist badge) would have been skipped. **Shipped:** the three helpers and their seven call sites across the rectangle, circle, ellipse and polygon items deleted; no zoom-dependent simplification remains in the canvas. **Kept:** `is_interactive_paint`, the one definition of "which paint is this" - #472's paint bound needs it for real (44.7 ms at 1,024 vertices, 589 ms at 16,384). **Pins:** `tests/integration/test_canvas_item_cache.py` covers seven entries (the four generic shapes plus a plant circle and furniture rectangle/circle, because two deleted call sites sat inside `is_plant` and two inside `is_furniture_type`), each rendered through a real `CanvasView` at five zoom levels plus the export path, with a lower bound only; the sampled interior is the item's own `shape()`. Full dispersion, the mutation that proved the seven entries and the mask invariant: PF-CAN-20, ADR-057 addendum.
- **2D canvas follow-up — a paint bound, one look rule and a line budget (#470, #472, #473, #502) shipped 2026-10-17 as v1.30.8 ([PR #501](https://github.com/cofade/open-garden-planner/pull/501)) after owner acceptance:** Three pre-existing 2D defects found during the Phase 17 L1 work (#385), deliberately kept clear of PR #484's files, plus the manual-pass follow-up. **#502 (textured fills + panel/canvas agreement):** `core/fill_patterns._tint_texture` is now a **luminance map** (the chosen colour scaled by the texture's relative luminance) instead of a 31 % wash, so a light-green fill over the Roof Tiles texture renders green (it rendered the standard brown: `#ca6846` → `#b8925d`), and the §8.10 gate gained the pale-colour case plus a scale-invariant contrast check; `core/item_look.restore_stored_look` makes `ProjectManager._deserialize_item_core` restore the stored appearance attributes (`fill_color`/`stroke_color`/`stroke_width`/`stroke_style`), so the Properties panel stops disagreeing with the canvas after a reload and a second save no longer writes the type defaults over the user's colours (#438/#469). Pinned by `tests/integration/test_item_appearance_roundtrip.py` (rendered pixels, all five shapes, Ctrl+D and a second save), using a fill colour that is no object type's default — with a default-valued colour the assertion held whether or not the loader wrote anything back. Lessons in PF-CAN-18/PF-CAN-19. **#472 (bounded polygon paint, ADR-057/§8.28):** `PolygonItem.paint` sizes itself by `MAX_FULL_DETAIL_VERTICES = 256` — above it an interactive, unselected paint draws the exact outline with a **cosmetic** 1-px pen and no fill (a wide solid pen makes the outline a fill again, which is the trap the first draft fell into), while a selected item and every export/report/print/agent render keep the exact fill — "interactive" is decided by the item's **cache mode**, not Qt's `widget`, which is always `0` for a cached paint (the first shipped guard tested `widget is not None` and therefore never degraded anything; the regression now drives a real `CanvasView`) — and `ProjectManager._deserialize_item_core` refuses a polygon above `MAX_POLYGON_VERTICES = 16_384` non-fatally (skip + log), pinned by `tests/integration/test_polygon_paint_bound.py`. **#470 (one look rule):** `core/item_look.py::copy_visual_style` copies both the serialized appearance (`fill_pattern`/`fill_color`/`stroke_color`/`stroke_width`/`stroke_style`) and the live pen/brush, and the offset tool plus `mirror_geometry` both use it (chamfer/fillet/trim stay with #441 on L1), pinned in `tests/integration/test_offset_tool.py`. **#473 (line budgets):** a second NFR-PERF-01 scenario adds plain fences and a styled path to the reference plan with their item cache **disabled** so `paint()` runs every frame, pinned deterministically by a `cacheMode()` guard plus an upper timing bound in `tests/perf/test_nfr_budgets.py` (a lower bound was machine noise, ±20 ms).

- **Worker lifecycle safety, cache bounds and test hygiene (#480, #483, #482, #474, #449, #448) shipped on 2026-10-16 as v1.30.7 ([PR #498](https://github.com/cofade/open-garden-planner/pull/498)) after owner acceptance:** Deterministic `cancel()` and `shutdown(timeout_ms)` for `UpdateChecker` and `_WeatherFetchWorker` with `core.worker_lifecycle._RETIRING_WORKERS` retention on exit to prevent `0xC0000409` aborts; redundant search field closure removed; furniture renderer clamped to `MAX_FURNITURE_DIMENSION_PX = 2048` and pixmap cache capped at 64 MB with LRU eviction; `FR-AGENT-29` uniqueness gate; test flakiness fixed via Python 3.11 requirement on type gate and multi-round median repaint budget evaluation; `Ctrl+F` shortcut overload resolved by reassigning Find & Replace to `Ctrl+H` and dedicating `Ctrl+F` to global search focus with whole-window duplicate shortcut assertion gate.

- **#496 shipped on 2026-10-16 as v1.30.6 ([PR #497](https://github.com/cofade/open-garden-planner/pull/497)) after owner acceptance:** source-derived translation completeness covers every registered locale in both directions. The required Test check verifies exact keys, completed values and compiled lookups; English/German each cover 2,631 live keys. Use `scripts/check_translations.py` after updating and compiling all catalogs; see ADR-008 and section 8.3. Russian PR #495 remains separate: its contributor must merge latest master and pass the shared gate before finalization.

- **Audit A1/A5/A2 shipped in v1.30.3/v1.30.4/v1.30.5 (PR #487/#489/#490)** after owner acceptance of the frozen executables. Numeric I/O and ingestion, solver characterization, and toolchain/inventory/provenance gates are recorded in `docs/roadmap.md`, ADR-003/012/041/044/050 and the October audit evidence in `docs/11-risks-and-technical-debt/audits/2026-10/`. Epic #392 remains open.

- **Audit #392 backlog reconciled on 2026-10-12:** all 73 P2/P3 findings have one package and evidence-backed disposition; 5 fixed, 19 partial, 49 unresolved. Bundles A1–A13 are issues #453–#465; see `docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10-reconciliation.md`. #406 shipped in v1.30.2 via PR #477, completing all 15 original standalone P0/P1 remediations; constraint refactors remain later work. The epic stays open; historical audit metrics are not current measurements.

- **#406 shipped as v1.30.2 ([PR #477](https://github.com/cofade/open-garden-planner/pull/477)) after owner acceptance on 2026-10-12.** All 13 constraint tools have real gesture/geometry/history coverage, canonical rectangle Edge Length sizing and ADR-050 per-file enforcement. Full-suite target coverage: 2023/2372 lines (85.3%), 486/720 branches (67.5%); line floor 60%. Full CI, independent review and frozen smoke/selftest passed; local timing limitations are recorded in the roadmap. The pre-existing rotation/constraint interaction is follow-up #485; its skipped-undo symptom remains an investigation. #392 stays open for A1–A13.

- **Package F3 (#314) + heatmap lifecycle #428 shipped on 2026-10-12 as v1.30.1 ([PR #436](https://github.com/cofade/open-garden-planner/pull/436); ADR-056).** Owner confirmed all manual checks. The release adds explicit cached ground-level sun estimates excluding self-shadow, sun badges/shared diagnostics, mature-canopy grouping and document-generation rejection of late worker results. F4 supersedes the explicit refresh and 21 June shortcut: use the shared SimClock date and automatically refresh while Hours of Sun is enabled; exposure is not persisted. #328 already shipped in PR #352 and is outside this work. F4 shipped in v1.30.17; F5 later completed Package F in v1.33.0 via PR #610. Wiki sources follow ADR-051 publication.

- **Package F1/F2 (#312/#313) shipped in v1.30.0 (PR #433); F3/F4/F5 subsequently completed Package F in v1.33.0 (PR #610).** Owner acceptance and the full history are in `docs/roadmap.md`, ADR-054/055/056/062/066 and the functional requirements.

- **Canvas performance & NFR-PERF-01 shipped 2026-10-10 as v1.29.9 ([PR #430](https://github.com/cofade/open-garden-planner/pull/430)): #409 (Audit 2026-10 P1, TD-034, AUD-056).** Fit-in-view repaint on the 500-object reference plan (`tests/fixtures/plans/audit-2026-10-plan_500.ogp`, 990 scene items) brought from 54.3 ms (≤ 18 fps) to 12.8 ms (≥ 60 fps; 100% zoom/pan to 4.5 ms) via: (1) `@functools.lru_cache` on `_resolve_svg_path` avoiding thousands of disk stats/frame; (2) `DeviceCoordinateCache` on unselected canvas items (toggled off when selected to eliminate resize/rotation handle ghosting and lag, and temporarily disabled during exports to ensure bit-exact full-detail vector rendering). **These two are the whole of it** — a third measure shipped here, a low-zoom Level-of-Detail flat fill below 0.4 zoom, never ran: its `widget is not None` guard was never true on the canvas, and when #503 fixed the guard and measured it on the 990-item plan, the flat fill bought nothing measurable — the two arms' ranges overlap and the sign flips between scenarios (full dispersion in PF-CAN-20) — because `DeviceCoordinateCache` already amortises the textured paint into a one-off cost. It was removed in #503 rather than made reachable, so this entry no longer lists it as a contributor. Pinned by `tests/perf/test_nfr_budgets.py` and `tests/integration/test_canvas_item_cache.py`.

- **Handled error logging & harvest offset calibration shipped 2026-10-10 as v1.29.8 ([PR #426](https://github.com/cofade/open-garden-planner/pull/426)): #405 + #416 + #418.** Persistent rotating file handler (`app.log`, UTF-8, 1 MB, 3 backups) in user AppData (`%APPDATA%\cofade\Open Garden Planner\app.log`) and safe console handler guarded against `sys.stderr is None` on windowed frozen builds (#291, AUD-063, TD-023, ADR-052); Garlic (*Allium sativum*) harvest window calibrated to +12..+16 weeks post-frost (mid-summer/July) with 240–270d maturity; benchmark plans and sweep counts (1,836 default / 17,884 wide) re-synchronized across docs and tests.

- **Package G (US-G4, #320) shipped 2026-10-09 as v1.29.7 ([PR #421](https://github.com/cofade/open-garden-planner/pull/421)).** Plant favourites & named collections with drag-to-canvas auto-parenting/sizing/planting-date stamping, snapshot updates from plan, portable JSON import/export, and the read-only Agent API `garden://plant-lists` resource. Completes Package G.


- Phases 1–12, Phase 13 (Packages A–D), and Phases 14 and 15 (Visual Refresh, Packages 1–3) are complete. Package D finished in v1.29.1 via PR #382.
- **Phase 17 "Living Garden 3D" — L0 complete with a GO, L1 complete (L1.0 v1.29.10, L1.1–L1.10 v1.30.14), L2 complete (v1.31.0), L3 complete (v1.32.0), L4 complete (v1.34.0)** (owner decision 2026-10-05, ADR-048 *Accepted*): Qt Quick 3D replaces Qt 3D. The L0 spike (`spike_q3d/`, `--spike-q3d`) was deleted in L1.10 — its measured values are frozen in `tests/data/l0_spike_reference.json`; ADR-048's evidence log (entry 19 = the owner-GPU run) records the measurements, and the temporary evidence tooling (`spike-q3d.yml`, `scripts/spike_q3d_ci.py`, its verdict test) is deleted with the decision. **L1** ([#385](https://github.com/cofade/open-garden-planner/issues/385)) was built one story per branch and shipped in two PRs: **L1.0** (one sim clock, `core/sim_clock.py`, ADR-053) **shipped 2026-10-10 (UTC) as v1.29.10 ([PR #429](https://github.com/cofade/open-garden-planner/pull/429))**, and L1.1–L1.10 shipped together on 2026-10-19 as v1.30.14 ([PR #484](https://github.com/cofade/open-garden-planner/pull/484)). Follow-up #428 (late heatmaps painting after document replacement) shipped with F3 in v1.30.1 (PR #436, ADR-056). Read ADR-053 before touching sun or growth time: the plan date is the toolbar's LOCAL day, *stored as given* — UI writers hand the clock a naive wall reading, never an instant (a gap that straddles midnight moves a date read back from one) — and new consumers subscribe to the clock's `date_changed` / `instant_changed` instead of keeping their own moment. Criterion 3 chose the `QQuickView` host; criterion 10's leak half was located and closed by a release in L1.3, then reopened by L1.5's ground textures (#532, shipped open; ADR-048 addendum L1.3, ADR-060 addendum D5). Load `ogp-lush-cinematic` and `ogp-3d-renderer` before touching it. **L1.9 (the default flip):** the Plan / 3D / Split workspace is the 3D view of every main window — no `OGP_QUICK3D` switch, View → "3D View" shows Split (F4 removes the former Sun & 3D submenu) — with a throttled date playback (a held date key, `DATE_REGROW_MIN_MS`); §8.29.9 holds the FR-SUN-06/07/08 parity table and the measured budgets against the old window; the owner shipped the flip with L1.5's open ground-texture leak (Qt 6.11, #532). **L1.10 (the removal):** the Qt 3D window, `core/scene3d/legacy.py`, `core/walk_camera.py`, the spike and the two Qt 3D wheels are gone; `tests/unit/test_no_qt3d_left.py` keeps code free of Qt 3D's names and lets documentation name them only in history files (ADR-060 addendum "the default and the removal", ADR-048's closing addendum). **L5 starts from** the workspace as the only 3D view, with L2-L4 on it (ADR-063/064/065): `core/scene3d/` (records, builders, ground) feeding `ui/view3d/quick3d/` through `Scene3DController`. v1.30.13 was the last release with the Qt 3D window (`ogp-3d-sunshade-campaign` keeps its history).
- Remaining work is tracked in `docs/roadmap.md`. **Package D is complete** (D3.3/D3.4, #332/#333, v1.29.1, PR #382, closing #237). Package F is complete through F5 (#316, v1.33.0, PR #610); Package G is complete via #320; #319 is D3 and #321 is standalone touch input, despite the contiguous numbering. Load-bearing rules from the shipped D2 and Phase 15 work (details in the cited ADRs and §11.4): `ui/canvas/geometry_apply.py` is **the one apply path for every rect-backed resize; do not add another closure** (§8.19); `CanvasScene.clear()` is the one chokepoint that drops every private item-tracking list before the C++ teardown (#337); `ui/canvas/arrange.py::build_arrange_command` is the one apply path for every arrange surface, and the per-layer z-refresh never writes a `stack_order` rank (ADR-043, §8.25); satellite capture is ADR-019 with addenda #346/#347; `release.yml` attests build provenance, which is not Authenticode signing (ADR-044, §11.1/§11.2). Releases remain unsigned; signing options, including no-cost proposals, are under evaluation in #375, with no adopted option or proven effect on AV detections (#376).
- Wiki and community documentation (#417, ADR-051) now use repository sources in `docs/wiki/` and offline `scripts/sync_wiki.py` validation. Publication and issue closure follow owner review and protected merge. Read `docs/wiki/README.md`; never edit the published Roadmap as a second tracker.
- Read the relevant roadmap section before starting work, then check `git status` and `git log --oneline -20`.
- The full shipped-story history belongs in `docs/roadmap.md`, ADRs, functional requirements, and the risk log; do not duplicate it here.
- Phase 14 remains complete; load `ogp-3d-sunshade-campaign` before touching 3D, sun/shade, growth, or solar code.

- **Older pickups (v1.29.6 and earlier, plus the v1.27/v1.28 batches) live in [`docs/agent-pickup-history.md`](docs/agent-pickup-history.md)**, moved out to keep these root instructions inside Codex's `project_doc_max_bytes`; the shipped stories are also in `docs/roadmap.md` and the ADRs.

**Maintaining this file:** Update the progress summary when status changes and keep the Quick Reference current. `CLAUDE.md` and `AGENTS.md` are a synchronized pair: if either changes, update both and run `venv/Scripts/python.exe scripts/check_agent_context.py`.

**Version note:** CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.
