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
# console-less condition #291 needs.

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
| Glossary                             | `docs/12-glossary.md`                                 |
| GitHub wiki (sync with roadmap)      | `../open-garden-planner.wiki/Roadmap.md`              |

### Skill Library (`.claude/skills/` and `.agents/skills/`)

Claude Code or Codex auto-loads each skill's `name` + `description` and invokes it via the
Skill tool when a task matches. **The authoritative trigger for each skill is its
frontmatter `description`** — this table is a routing map, not a substitute. Reach
for a skill *before* acting, not after. Three pre-existing skills (`debug-verbose`,
`finalize-us`, `analyze-pr`) plus the `senior-reviewer` agent are documented elsewhere
in this file; the `deliver-package` workflow skill and the 17 `ogp-*` continuity skills
below cover the rest.

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

**Maintaining this table:** add a one-line row when a new skill lands; keep the real
trigger in the skill's `description`. If a row and a `description` disagree, the
`description` wins — fix the row.

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
| New domain term | `docs/12-glossary.md` — add definition |

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
| 7 | **Run senior-reviewer pass** | Launch the `senior-reviewer` agent in a fresh worktree against the branch diff. Address any P0/P1 findings before proceeding. Re-run after fixes for a clean re-review. The `finalize-us` skill repeats this step pre-PR. |
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

- Phases 1–12 are complete; Phase 13 agent integration is shipped through D2.1 (`create_object`), and Phases 14 and 15 (Visual Refresh, Packages 1–3) are complete.
- Remaining work is tracked in `docs/roadmap.md`: the D2/D3 agent write/domain tools, and the permapeople-research Packages F/G (#311–#321). Phase 15 Package 3 shipped 2026-08-18 as v1.26.8 (3a, PR #322) / v1.26.9 (3b, PR #323) / v1.27.0 (3c, PR #325; ADR-042, FR-30, §8.23–§8.24, §8.21.5).
- Read the relevant roadmap section before starting work, then check `git status` and `git log --oneline -20`.
- The full shipped-story history belongs in `docs/roadmap.md`, ADRs, functional requirements, and the risk log; do not duplicate it here.
- Phase 14 remains complete; load `ogp-3d-sunshade-campaign` before touching 3D, sun/shade, growth, or solar code.

**Maintaining this file:** Update the progress summary when status changes and keep the Quick Reference current. `CLAUDE.md` and `AGENTS.md` are a synchronized pair: if either changes, update both and run `venv/Scripts/python.exe scripts/check_agent_context.py`.

**Version note:** CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.
