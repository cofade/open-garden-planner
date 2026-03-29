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
| Known pitfalls & technical debt      | `docs/11-risks-and-technical-debt/` (section 11.4)    |
| Functional requirements (FR-*)       | `docs/functional-requirements.md`                     |
| Architecture decisions (ADRs)        | `docs/09-architecture-decisions/`                     |
| GitHub wiki (keep in sync)           | `../open-garden-planner.wiki/Roadmap.md`              |

## Versioning Protocol

**Git tags are the ONLY source of truth for versions.** Never infer from files.

```bash
git checkout master && git pull origin master
git fetch --tags
git describe --tags --abbrev=0   # e.g. v1.8.12 ← THIS is your base
```

| Scenario | Bump | Label |
|----------|------|-------|
| US within an ongoing phase | patch | `patch` |
| First US of a brand-new phase | minor | `minor` |
| Major architectural milestone | major | `major` |

After merge, update **both** `pyproject.toml` and `src/open_garden_planner/__init__.py` to match the new tag. Do NOT wait for CI — the version is deterministic from the bump rule.

## Workflow

### CRITICAL: Always Use Feature Branches

**NEVER commit directly to master!** Always work on feature branches.

### Step-by-Step Process

1. **Create feature branch**: `git checkout -b feature/US-X.X-short-description`
2. Read user story from `docs/roadmap.md`
3. Clarify with `AskUserQuestion` if needed
4. Implement with type hints
5. Write tests, run lint
6. Build exe and verify it launches (see Quick Reference)
7. **WAIT for user to manually test and approve** — provide a testing checklist
8. After approval, commit: `feat(US-X.X): Description`
9. Push and create PR via GitHub CLI:
   - `git push -u origin feature/US-X.X-short-description`
   - `"C:\Program Files\GitHub CLI\gh.exe" pr create --title "feat(US-X.X): Title" --body "..."`
   - Merge: `"C:\Program Files\GitHub CLI\gh.exe" pr merge <PR#> --squash --delete-branch --admin`
10. Switch back to master, sync version (see Versioning Protocol)
11. `/clear` context

**Reminders**: Never commit to master. Never commit before user approval. Always create branch BEFORE changes.

## Translation (i18n)

**Always use `self.tr("string")` for every user-visible string in any `QWidget` subclass.**

Full how-to (step-by-step, `.ts` format, recompile command): see `docs/08-crosscutting-concepts/` section 8.3.

Key rules:
- `CollapsiblePanel(title)` → use `self.tr()` at the **call site**, not inside the panel
- `QT_TR_NOOP("string")` for module-level dicts, translate later with `QCoreApplication.translate()`
- Non-QObject contexts → `QCoreApplication.translate("ContextName", "string")`

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

## Progress (Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools v1.9.x)

> **Version note**: First US = v1.9.0 minor bump, subsequent = patch. Never v2.x.

| Status | US    | Description                              | Block              |
| ------ | ----- | ---------------------------------------- | ------------------ |
| ✅     | 11.1  | Plant-bed parent-child relationship      | Bed Interior       |
| ✅     | 11.2  | Plant spacing circles & overlap warnings | Bed Interior       |
| ✅     | 11.3  | Square-foot grid overlay                 | Bed Interior       |
|        | 11.4  | Row planting mode                        | Bed Interior       |
| ✅     | 11.5  | Expanded fill pattern library            | Visual Polish      |
| ✅     | 11.6  | Plant illustration expansion             | Visual Polish      |
| ✅     | 11.7  | Minimap / overview panel                 | Visual Polish      |
|        | 11.8  | Free text annotation tool                | Annotations        |
|        | 11.9  | Auto area labels                         | Annotations        |
|        | 11.10 | Callout / leader line annotations        | Annotations        |
|        | 11.11 | Group / ungroup                          | Shape Operations   |
|        | 11.12 | Boolean shape operations                 | Shape Operations   |
|        | 11.13 | Array along path                         | Shape Operations   |
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
