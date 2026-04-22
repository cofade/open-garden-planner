# Open Garden Planner - Claude Code Instructions

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

# Build & verify exe (before every merge)
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe
# Exit code 124 (killed by timeout) = success

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
- After each fix, add a **Case study** entry to `.claude/skills/debug-verbose/skill.md` (symptom, wrong theories, key log line, root cause, lesson). The skill grows with the project.

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
| Functional requirements (FR-*)       | `docs/functional-requirements.md`                     |
| Architecture decisions (ADRs)        | `docs/09-architecture-decisions/`                     |
| Glossary                             | `docs/12-glossary.md`                                 |
| GitHub wiki (sync with roadmap)      | `../open-garden-planner.wiki/Roadmap.md`              |

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

**After solving issues:**
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

## Workflow

**CRITICAL: Always use feature branches — NEVER commit directly to master.**

| Step | Action | Notes |
|------|--------|-------|
| 1 | Create branch: `git checkout -b feature/US-X.X-short-description` | Before any changes |
| 2 | Read user story from `docs/roadmap.md` | Understand acceptance criteria |
| 3 | Implement with type hints & translation | Use `self.tr()` for all UI strings |
| 4 | Run quality checks | `pytest tests/ -v`, `ruff check src/`, `bandit -r src/ --severity-level high` |
| 4a | Update translations | Add strings to `scripts/fill_translations.py`, run `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py` then `compile_translations.py`; `pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` must pass |
| 5 | **Write integration test** in `tests/integration/test_<feature>.py` | **Mandatory** — end-to-end UI workflow. See `docs/08-crosscutting-concepts/` 8.10 |
| 6 | Build & verify exe | See Quick Reference |
| 7 | **WAIT for user approval** Provide testing checklist | Never commit before approval |
| 8 | Commit: `feat(US-X.X): Description` | Conventional commit format |
| 9 | Push & create PR | Use GitHub CLI: `pr create`, `pr merge --squash --delete-branch --admin` |
| 10 | Sync version on master | See Versioning Protocol |
| 11 | `/clear` context | Clear Claude context

## Translation (i18n)

> **MUST — every feature, no exceptions.** Every user-visible string added in any file MUST be wrapped for translation. Skipping this is a bug.

- `QWidget`/`QDialog` subclasses → `self.tr("string")`
- `QGraphicsItem` context menus (non-QObject) → `QCoreApplication.translate("ClassName", "string")`
- Module-level dicts → `QT_TR_NOOP("string")`, translate later with `QCoreApplication.translate()`
- `CollapsiblePanel(title)` → wrap at the **call site**, not inside the panel

Full how-to (step-by-step, `.ts` format, recompile command): see `docs/08-crosscutting-concepts/` section 8.3.

## Testing Notes

- PyQt6 tests require `qtbot` fixture even when unused (needed for Qt init); ruff per-file ignore ARG002 in test files

## Where to Pick Up After Restart

1. Check **Phase 11 or Phase 12 progress table** below for next unchecked US
2. Read user story in `docs/roadmap.md`
3. Check `git status` and recent git history
4. Create feature branch and implement

**Maintaining this file:** Update progress table when US status changes; add new patterns when discovered; keep Quick Reference commands current.

## Phases 1-10 Complete

All user stories from Phase 1 through Phase 10 (US-10.7) are delivered.
Full history: see `docs/roadmap.md`.

## Progress (Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools v1.8.x)

> **Version note**: CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.

| Status | US    | Description                              | Block              |
| ------ | ----- | ---------------------------------------- | ------------------ |
| ✅     | 11.1  | Plant-bed parent-child relationship      | Bed Interior       |
| ✅     | 11.2  | Plant spacing circles & overlap warnings | Bed Interior       |
| ✅     | 11.3  | Square-foot grid overlay                 | Bed Interior       |
| ✅     | 11.5  | Expanded fill pattern library            | Visual Polish      |
| ✅     | 11.6  | Plant illustration expansion             | Visual Polish      |
| ✅     | 11.7  | Minimap / overview panel                 | Visual Polish      |
| ✅     | 11.8  | Free text annotation tool                | Annotations        |
|        | 11.9  | Auto area labels                         | Annotations        |
|        | 11.10 | Callout / leader line annotations        | Annotations        |
| ✅     | 11.11 | Group / ungroup                          | Shape Operations   |
| ✅     | 11.12 | Boolean shape operations                 | Shape Operations   |
| ✅     | 11.13 | Array along path                         | Shape Operations   |
| ✅     | 11.14 | Ellipse drawing tool                     | Drawing Tools      |
|        | 11.15 | Offset tool                              | Drawing Tools      |
| ✅     | 11.16 | Trim / extend tool                       | Drawing Tools      |
|        | 11.24 | Find & replace objects                   | Workflow           |
| ✅     | 11.25 | Missing translations & Change Type menu  | Quality / UX       |

## Progress (Phase 12: Weather & Smart Features v1.9.x)

| Status | US    | Description                              | Block              |
| ------ | ----- | ---------------------------------------- | ------------------ |
|        | 12.1  | Weather forecast widget in Dashboard     | Weather            |
|        | 12.2  | Frost alert & plant-aware warnings       | Weather            |
|        | 12.3  | DXF export                               | Interoperability   |
|        | 12.4  | DXF import                               | Interoperability   |
|        | 12.5  | Multi-page PDF export                    | Interoperability   |
|        | 12.6  | Shopping list generation                 | Smart Features     |
|        | 12.7  | Pest & disease log                       | Smart Features     |
|        | 12.8  | Succession planting                      | Smart Features     |
|        | 12.9  | Garden journal (map-linked notes)        | Smart Features     |
