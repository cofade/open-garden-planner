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

# Build & verify exe (before every merge)
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe
# Exit code 124 (killed by timeout) = success
```

Tech stack: Python 3.11+ | PyQt6 | QGraphicsView/Scene | pytest + pytest-qt | ruff | mypy
Use context7 as required for up-to-date library documentation.

## Documentation

All architecture documentation follows arc42 in `docs/`. Key references:

| What you need                        | Where to find it                                      |
| ------------------------------------ | ----------------------------------------------------- |
| User stories & acceptance criteria   | `docs/roadmap.md`                                     |
| Module structure & project tree      | `docs/05-building-block-view/`                        |
| CI/CD, installer, release process    | `docs/07-deployment-view/`                            |
| i18n rules & translation how-to      | `docs/08-crosscutting-concepts/` (section 8.3)        |
| QGraphicsView overlay widget patterns | `docs/08-crosscutting-concepts/` (section 8.9)       |
| Integration test policy (MANDATORY)  | `docs/08-crosscutting-concepts/` (section 8.10)      |
| Known pitfalls & technical debt      | `docs/11-risks-and-technical-debt/` (section 11.4)    |
| Functional requirements (FR-*)       | `docs/functional-requirements.md`                     |
| Architecture decisions (ADRs)        | `docs/09-architecture-decisions/`                     |
| GitHub wiki (keep in sync)           | `../open-garden-planner.wiki/Roadmap.md`              |

## Versioning Protocol

**GitHub releases are the ONLY source of truth for versions.** The CI release workflow (`release.yml`) auto-creates tags + releases on every non-chore push to master. **Never create git tags manually.**

```bash
# Find current version (ground truth):
"C:\Program Files\GitHub CLI\gh.exe" release list --limit 1 --json tagName --jq '.[0].tagName'
```

The CI defaults to **patch bump**. For minor/major bumps, add a `minor` or `major` **label** to the PR before merging — the CI reads PR labels to decide the bump level.

After merge, wait for the CI release, then update **both** `pyproject.toml` and `src/open_garden_planner/__init__.py` to match the new release tag. Push as a `chore:` commit (CI skips these).

## Workflow

### CRITICAL: Always Use Feature Branches

**NEVER commit directly to master!** Always work on feature branches.

### Step-by-Step Process

1. **Create feature branch**: `git checkout -b feature/US-X.X-short-description`
2. Read user story from `docs/roadmap.md`
3. Clarify with `AskUserQuestion` if needed
4. Implement with type hints
5. Write tests, run lint
6. **Write integration test** — every US needs at least one end-to-end test in `tests/integration/test_<feature>.py` that simulates the primary UI workflow (tool activate → gesture → verify state). **No merge without this. No exceptions.** See `docs/08-crosscutting-concepts/` section 8.10.
7. Build exe and verify it launches (see Quick Reference)
8. **WAIT for user to manually test and approve** — provide a testing checklist
9. After approval, commit: `feat(US-X.X): Description`
10. Push and create PR via GitHub CLI:
   - `git push -u origin feature/US-X.X-short-description`
   - `"C:\Program Files\GitHub CLI\gh.exe" pr create --title "feat(US-X.X): Title" --body "..."`
   - Merge: `"C:\Program Files\GitHub CLI\gh.exe" pr merge <PR#> --squash --delete-branch --admin`
11. Switch back to master, sync version (see Versioning Protocol)
12. `/clear` context

**Reminders**: Never commit to master. Never commit before user approval. Always create branch BEFORE changes.

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

1. Check the **Phase 11 progress table** below for the next unchecked US
2. Read the user story in `docs/roadmap.md`
3. Check `git status` and recent history
4. Create feature branch and start implementing

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
|        | 11.14 | Ellipse drawing tool                     | Drawing Tools      |
|        | 11.15 | Offset tool                              | Drawing Tools      |
|        | 11.16 | Trim / extend tool                       | Drawing Tools      |
|        | 11.17 | DXF export                               | Interoperability   |
|        | 11.18 | DXF import                               | Interoperability   |
|        | 11.19 | Multi-page PDF export                    | Interoperability   |
|        | 11.20 | Shopping list generation                 | Smart Features     |
|        | 11.21 | Pest & disease log                       | Smart Features     |
|        | 11.22 | Succession planting                      | Smart Features     |
|        | 11.23 | Garden journal (map-linked notes)        | Smart Features     |
|        | 11.24 | Find & replace objects                   | Workflow           |
