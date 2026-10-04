# Open Garden Planner - Instructions for Coding Agents

PyQt6 desktop app for precision garden planning with CAD-like metric accuracy.

## Quick Reference

```bash
# Run app
venv/Scripts/python.exe -m open_garden_planner

# Run tests
venv/Scripts/python.exe -m pytest tests/ -v

# Lint
venv/Scripts/python.exe -m ruff check src/

# Security scan
venv/Scripts/python.exe -m bandit -r src/ --severity-level high

# Build & verify exe (before every merge) — BOTH checks
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe
# Exit code 124 (killed by timeout) = success
powershell -Command '$p = Start-Process "dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList "--selftest" -Wait -PassThru; exit $p.ExitCode'
# Exit code 0 = Qt3D bindings import, the Qt runtime matches the Qt3D wheel
# version (the check that caught #277), AND the Agent API server binds.
# The 8-s smoke only proves the process stays up; --selftest is what sees a
# silently-dead subsystem (#291 hid from the smoke for six releases). Must be
# Start-Process -Wait -PassThru: PowerShell does not wait on a GUI-subsystem
# exe, and a shell-piped run hands it a real stdout so it cannot reproduce the
# no-inherited-handle condition #291 needs.

# Update & compile translations (after adding/changing any UI strings)
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
# pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished
# verifies zero unfinished strings — fails if any string was missed
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
| Known pitfalls, technical debt       | `docs/11-risks-and-technical-debt/` section 11.4      |
| **Bed-only features (menu, badge, …) — READ FIRST before adding any bed feature** | `docs/08-crosscutting-concepts/` § 8.14 + ADR-017     |
| Functional requirements (FR-*)       | `docs/functional-requirements.md`                     |
| Architecture decisions (ADRs)        | `docs/09-architecture-decisions/`                     |
| Glossary                             | `docs/12-glossary/README.md`                          |
| GitHub wiki (sync with roadmap)      | `../open-garden-planner.wiki/Roadmap.md`              |

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
| `ogp-docs-and-writing` | finishing any feature/fix and owing doc updates, writing an ADR/FR/§11.4 entry, or unsure where knowledge lives |
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
| PyQt6 quirks | `docs/11-risks-and-technical-debt/` 11.4 | Symptoms → Root cause → Fix |
| Performance issues | `docs/08-crosscutting-concepts/` | Optimization technique |
| Testing patterns | `docs/08-crosscutting-concepts/` 8.10 | How to test this pattern |
| Security fixes | `docs/08-crosscutting-concepts/` 8.11 | Vulnerability + mitigation |

**ADR triggers:** Create ADR when introducing new dependencies, choosing between approaches, changing patterns, or addressing non-obvious constraints.

**Before merge, verify:** arc42 docs updated, ADRs created if needed, glossary updated, wiki synced.

## Versioning Protocol

**GitHub releases are THE source of truth.** CI auto-creates tags/releases on non-chore push to master.

```bash
# Find current version:
"C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
```

- CI **defaults to patch** bump
- Add `minor` or `major` **label** to PR for bigger bumps
- After merge, update both `pyproject.toml` and `src/open_garden_planner/__init__.py` to match the CI release
- Push as `chore:` commit (CI skips these)

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
| 4a | Update translations | Add strings to `scripts/fill_translations.py`, run `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py` then `compile_translations.py`; `pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` must pass |
| 5 | **Write integration test** in `tests/integration/test_<feature>.py` | **Mandatory** — end-to-end UI workflow. See `docs/08-crosscutting-concepts/` 8.10 |
| 6 | Build & verify exe | See Quick Reference |
| 7 | **Run senior-reviewer pass** | Launch the `senior-reviewer` agent in a fresh worktree against the branch diff. Address any P0/P1 findings before proceeding. Re-run after fixes for a clean re-review. The `finalize-us` skill repeats this step pre-PR. A change visible in 3D first passes `ogp-3d-creator` → `ogp-3d-reviewer` with no P0/P1. |
| 8 | Provide testing checklist | Surface a manual-testing checklist alongside the work |
| 9 | Commit: `feat(US-X.X): Description` | Conventional commit format |
| 10 | Push & **open DRAFT PR** | After a clean senior-reviewer pass, push and open a **draft** PR automatically (`pr create --draft`). **Every coding job ends here — never stop at just a pushed branch.** Keep it a draft and **do NOT merge** until the user confirms manual testing passed — only then mark ready (`pr ready`) and `pr merge --squash --delete-branch --admin` |
| 11 | Sync version on master | See Versioning Protocol (after merge) |
| 12 | `/clear` context | Clear Agent context

## Translation (i18n)

> **MUST — every feature, no exceptions.** Every user-visible string added in any file MUST be wrapped for translation. Skipping this is a bug.

- `QWidget`/`QDialog` subclasses → `self.tr("string")`
- `QGraphicsItem` context menus (non-QObject) → `QCoreApplication.translate("ClassName", "string")`
- Module-level dicts → `QT_TR_NOOP("string")`, translate later with `QCoreApplication.translate()`
- `CollapsiblePanel(title)` → wrap at the **call site**, not inside the panel
- **Hardcoded English f-strings (`f"{a} overlaps {b}"`) bypass `tr()` and never reach Qt Linguist** — use `self.tr("{a} overlaps {b}").format(a=…, b=…)`. The `test_german_ts_has_no_unfinished` test only catches MISSING translations of REGISTERED strings; it cannot see plain-string call sites. Pattern: if it's user-visible text, it MUST go through `tr()` / `QT_TR_NOOP` / `QCoreApplication.translate()` — registering it in `scripts/fill_translations.py` alone is insufficient.
- **NEVER use PowerShell `Set-Content -Encoding UTF8`** for files with non-ASCII (umlauts etc.) — double-encodes UTF-8 into mojibake. Use the `Edit` tool or Python `open(..., encoding="utf-8")`.

Full how-to (step-by-step, `.ts` format, recompile command): see `docs/08-crosscutting-concepts/` section 8.3.

## Testing Notes

- PyQt6 tests require `qtbot` fixture even when unused (needed for Qt init); ruff per-file ignore ARG002 in test files

## Where to Pick Up After Restart

- Phases 1–12 are complete; Phase 13 agent integration is complete through **D2.6** (the D2 tool layer shipped in v1.27.11 via PR #361), and Phases 14 and 15 (Visual Refresh, Packages 1–3) are complete.
- **Phase 17 "Living Garden 3D" is in Package L0**, the GO/NO-GO spike for replacing Qt 3D with Qt Quick 3D (ADR-047, *Proposed*). The dormant spike lives in `src/open_garden_planner/spike_q3d/` behind `--spike-q3d`; its measurements go into ADR-047's evidence log. Load `ogp-lush-cinematic` and `ogp-3d-renderer` before touching it. Until the ADR decides, the shipped Qt 3D view (`ogp-3d-sunshade-campaign`) is the product.
- Remaining work is tracked in `docs/roadmap.md`; open next are the remaining D3 stories (D3.4 is #333), Package F (#312, #316 and siblings), #320, and the standalone #321. Load-bearing rules from the shipped D2 and Phase 15 work (details in the cited ADRs and §11.4): `ui/canvas/geometry_apply.py` is **the one apply path for every rect-backed resize; do not add another closure** (§8.19); `CanvasScene.clear()` is the one chokepoint that drops every private item-tracking list before the C++ teardown (#337); `ui/canvas/arrange.py::build_arrange_command` is the one apply path for every arrange surface, and the per-layer z-refresh never writes a `stack_order` rank (ADR-043, §8.25); satellite capture is ADR-019 with addenda #346/#347; `release.yml` attests build provenance, which is not Authenticode signing (ADR-044, §11.1/§11.2).
- The post-D2.4/D2.5 hardening package (#353/#354/#355, v1.27.10, PR #360): same-scene document cleanup and fail-closed deletes, authenticated global MCP `undo`/`redo`, bounded callout offsets, and a repeated-median spatial-index guard.
- Read the relevant roadmap section before starting work, then check `git status` and `git log --oneline -20`.
- **#365 and #366 shipped in v1.28.0 via PR #367** (owner manual test passed). #366 rewrites `services/ai_client_onboarding.py` around a frozen `ClientTarget` registry — clients are **data**, so the dialog gained **OpenCode, Codex, and Gemini CLI** with no vendor-specific code beyond one completeness-tested per-client note — and makes the **read-only connect URL the default hand-out**, because the single "Copy URL" button used to copy the *write-enabled* URL, which is how a live write credential ended up pasted into a chat. Three serializers keyed on `syntax`; **TOML is appended surgically** (no `tomli-w`: a full re-serialise would destroy the user's own comments in a file OGP does not own) and **JSONC needs a tolerant reader**, or a commented `opencode.jsonc` fails closed into a dead end. **A client CLI is capability-probed, never assumed**: two OpenCode generations are in the wild (1.18.x has no `--global` and stores servers flat as `mcp.<name>`; 2.x has both) and one machine can hold both, so `cli_required_flags` asks the binary what it advertises and the probe is **tri-state** — an *indeterminate* answer refuses rather than guessing, because the wrong guess writes a project config into the working directory. #365 adds token-gated `new_plan` / `open_plan`, both reusing the GUI's own paths (extracted as `_new_project_document` and a raising `_load_project_file`), and reverses the layer-lock policy. **Read ADR-035's #366 addendum and ADR-034's #365 addendum before touching either area** — both record decisions that are not obvious from the code, including a reversal (an earlier "refuse an old CLI" decision was undone, because it removed a button that worked) and two things deliberately left unchanged (OpenCode's 5 s timeout, and the token still riding the URL rather than a header, because header transmission on tool calls is unmeasured).
- **D3.1 (#319) and D2.7 (#362) shipped 2026-09-29 as v1.28.2 via PR #370** (owner manual test passed). **PR #369 was closed** during this work's credential remediation, and #370 is the PR that shipped — if you find #369 referenced anywhere, it is the dead predecessor, not the shipped PR. That incident also produced `scripts/check_no_secrets.py` (see (e) below), which is now a CI gate. #319 adds the first domain-intelligence tools — `suggest_companions` / `find_compatible_sets` / `find_sets_for_bed` / `check_placement`, the `plan-polyculture-bed` prompt, and a Companion-panel "Suggest a compatible set…" action. `find_sets_for_bed` is the one that answers "what should I plant in this bed?"; `find_compatible_sets` searches a candidate palette you name and is the wrong tool for a bed already planted. #362 adds `get_history`, which makes two of D2's core undo invariants machine-checkable with no human reading the Edit menu. **Three things in this package are load-bearing and are easy to get wrong again:** (a) `parent_bed_id` is a `GardenItem` **property**, not a key in `item.metadata` — reading the dict silently returns nothing and the panel action opens an empty dialog; (b) **never pass a bed's plants as `must_include`** to the clique search, which emits only *maximal* cliques — that call returns 0 sets for 91% of two-plant and 100% of three-plant beds, so the panel and prompt use `find_sets_for_bed()` instead, which ranks by bed coverage and names the conflicting pair; (c) a component that did not check something must not report a result that reads as a successful check (`spacing_ok=None`, `overall="unknown_bed"`, conflicts named rather than swallowed). **Read ADR-045 before touching this area** — it records all three, plus why `CompanionRelationship.source` must stay a declared dataclass field. **Two more traps this package paid for, both invisible to a green suite:** (d) the dialog's three coverage strings paired Qt's positional `%1` with Python's `.format()`, a **silent no-op** — the user saw a literal `Already in bed: %1`, and because the `%1` literal matched no `.ts` key the German dialog was half-translated. `test_german_ts_has_no_unfinished` is **structurally blind** to this: it only inspects messages already in the table, and a `tr()` literal that is never extracted is by definition not in it. The invariant is the **pairing**, not the placeholder — `%1` is *correct* where it is paired with `.replace()`. `tests/unit/test_dialog_i18n_literals.py` now pins both directions by AST-extracting each `tr()` literal and its interpolation method; (e) the new `scripts/check_no_secrets.py` matches the bearer scheme with `re.IGNORECASE` because the server does (`raw[:7].lower() == "bearer "`) — **measured 64/64 casings**, which took two corrections, because a `\b[Bb]earer\b` covered only 2 of 64 while its own docstring claimed case-insensitivity, and then a vestigial `"Bearer eyJ"` allow-marker silently exempted the *canonical* JWT spelling (markers are checked before the rules). An allow-marker that saves no tracked line is a hole, not a safety net. — see §11.4.
- **Package G (#311, #317, #318) shipped in v1.28.1 via PR #368** (owner manual test passed). #311 adds `license` + `attribution` to all bundled data files, a "Data Sources & Licenses" section in the About dialog, and a licence line in Plant Details — closing the CC BY-SA compliance gap. #317 adds a profile header to Plant Database (thumbnail, description, external links to Wikipedia/PFAF/POWO) with off-thread thumbnail fetching and disk caching. #318 adds `PermapeopleClient.get_companions()` with pagination, a local companion cache, and three-tier companion service support (bundled → custom → provider). New settings: `plants/download_images` and `plants/fetch_companion_data`.
- **#364 (HOUSE roof-ridge drift), #363 (dead issue-template links) and #372 (roof tiles lapped toward the ridge) shipped 2026-10-01 as v1.28.3 via PR #371** (owner manual test passed). #364 replaces the ridge sync's boundary *projection* with a **recompute** through the one canonical `core.roof_ridge.compute_roof_ridge_endpoints`, and two things about it are easy to get wrong again: it is computed in the polygon's **local** frame and mapped through the item's full transform (calling it with `item.pos()` as creation does returns a **0-degree** ridge for a 30-degree house, so the issue's own suggested fix was wrong), and the **drift** defect reproduces at every transform (including unrotated — that is how #364 was filed) while only the **orientation** defect is zero at rotation 0, and **21 of the 26** cases in `tests/unit/test_roof_ridge.py` fail against master's `polygon_item.py`/`canvas_view.py` (15 of the 20 `TestRidgeDriftOnUndo` cases, plus all of `TestResizeUndo` and `TestHandMovedRidgeEndpoint`; the 5 that pass are the four boundary-invariant cases plus the unrotated rotation-tracking one, whose orientation defect is zero at rotation 0). The `TestResizeUndo` cases import what the fix introduces, so against master they stop at an `ImportError` rather than observing anything — they are proven by removing the sync line instead: 300 cm. Senior review then found the fix **incomplete twice over**: the `ResizeItemCommand` apply closure is a *fifth* polygon-apply path that never re-derived the ridge, so undoing a HOUSE resize left it sized for the resized house (300 cm, persisted into the `.ogp`) — no test anywhere resized a HOUSE, so 6509 green tests missed it; and a *sixth*, the constraint solver's `finally`, which restored a polygon with a bare `setPolygon` while its polyline sibling restored through the override that does re-derive. ADR-046 enumerates all six — **a derived child must be re-derived by every writer of its owner's state, and a green suite is evidence only about the paths it exercises**. It also silently fixes a larger, unreported defect: the old membrane never rotated the ridge with the house, so every rotated house was 75-180 cm off **and had a wrongly-mirrored roof texture** (`_paint_with_ridge`). A hand-dragged ridge endpoint is deliberately *not* sticky. A drift already saved into an `.ogp` self-heals on the next polygon edit, **not at load** (`_deserialize_item_core` calls `_apply_rotation` before the item is in a scene, so `_find_ridge()` returns `None`). #363 adds the two missing `.github/ISSUE_TEMPLATE` files; `blank_issues_enabled: false` is now deliberate. See ADR-046 and §11.4.
- **#372 (HOUSE roof tiles lap toward the ridge)** shipped in that same PR, found during the #364 manual test. **Pre-existing, not a #364 regression.** `_paint_with_ridge` assigned the two ridge halves to the texture and its mirror by `_split_path_by_line`'s `left`/`right` naming, which follows the ridge's **direction**, not which side is downhill, so the phase inversion appeared on **both** (mirror) halves at every orientation. **The fix is a swap, not a probe**: `left_path` is the down-slope half and takes the **normal** brush. Measured through the production paint path: fixed `RBBRBB`, pre-fix `BRRBRR`, both sides, all orientations. **Four traps, each producing a confident false conclusion:** (1) removing the ridge made `_paint_with_ridge` never run, so the renders measured `super().paint()` and the fix hashed identical to pre-fix; (2) `ridge.setPen(NoPen)` does not suppress the stroke (three hardcoded pens) — use `setVisible(False)`; (3) mapping already-scene ridge points through `mapToScene` invented a degenerate band that does not exist; (4) sweeping the house's *rotation* is structurally blind to a negated sign, because the angle consumed is the ridge direction in the polygon's **local** frame (0 for landscape at every rotation) — a portrait house caught it. **A harness that bypasses or mis-aims at the code under test produces evidence about something else; when a test sweeps a transformation, check which quantity the code actually consumes.** See the ADR-046 addendum and §11.4.
- **US-D3.2 (#331) shipped in v1.28.4, PR #374.** Reads `get_succession_plan` / `find_succession_gaps` / `suggest_succession`, gated write `set_succession_plan`, `plan-succession` prompt. First agent write into `ProjectData`, not the scene: no geometry or badge; the badge refresh rides the existing `succession_plans_changed` signal. Refuses a TRELLIS (`is_bed_type`). Traps: **four** season segments, whose gap windows must stay **disjoint** or filling them is refused; the no-location fallback was *extracted* from the succession dialog; `check_plant_placement` cannot do within-plan rotation; `species_key` is a **function** over a dict, and a bundled plant's key is its lowercased scientific name. See ADR-034/036, §8.19, §11.4.
- **The manual-pass follow-up package (#373, #377, #378, #380) shipped as v1.29.0.** Four defects found by dogfooding, each invisible to a green suite for a *structural* reason (§11.4.2). #377: shape-tool previews kept Qt's default `z=0` while real items get a derived z inside `(0, 100)`, so a preview drew behind any bed it overlapped; fixed by `core/tools/preview_z.py` (band 999–1002, below the minimap's 10000 cutoff); the issue's own module list was wrong (it omitted `construction_tool.py`), so a drift guard re-derives the set from source. #378: the Crop Rotation panel shows a bed's succession plan as a display-only **"Planned This Season"** section; `CropRotationService` is untouched — feeding the plan into `get_recommendation` would change the 3-year cooldown for every caller (the rejected option). #373: shutdown took ~10 s **only with an MCP client holding the SSE stream open** (0.19 s without); uvicorn's graceful shutdown waits for that connection and `force_exit` alone does **not** fix it (measured) — `stop()` now cancels the loop's tasks and stops the loop (10.03 s → 0.58 s). #380: agent writes are now canvas-clamped; the rule lives once in Qt-free `core/canvas_bounds.py`, called by both the GUI drag paths and the agent paths, with `ObjectRef.outside_canvas` + a `get_diagnostics` kind for objects already saved off-plan (a deliberate reversal of the "stage just off-plan" rationale; vertex writes are flag-only). See ADR-036 addenda, FR-AGENT-26, §8.19, §8.25.6, §11.4.2.
- The full shipped-story history belongs in `docs/roadmap.md`, ADRs, functional requirements, and the risk log; do not duplicate it here.
- Phase 14 remains complete; load `ogp-3d-sunshade-campaign` before touching 3D, sun/shade, growth, or solar code.

**Maintaining this file:** Update the progress summary when status changes and keep the Quick Reference current. `CLAUDE.md` and `AGENTS.md` are a synchronized pair: if either changes, update both and run `venv/Scripts/python.exe scripts/check_agent_context.py`.

**Version note:** CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.
