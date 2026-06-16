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
| **Bed-only features (menu, badge, …) — READ FIRST before adding any bed feature** | `docs/08-crosscutting-concepts/` § 8.14 + ADR-017     |
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

## Workflow

**CRITICAL: Always use feature branches — NEVER commit directly to master.**

> **MUST — every coding job ends with a draft PR.** Any task that changes code (feature, bug fix, refactor, doc-in-code, chore) finishes by pushing the branch and opening a **draft** pull request — never leave the work as just a pushed branch. Open the draft only **after** the `senior-reviewer` pass is fully satisfied (no outstanding P0/P1). The PR stays a **draft** until the user confirms manual testing passed; only then mark it ready and merge. Do NOT open a non-draft PR or merge without explicit user confirmation.

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
| 12 | `/clear` context | Clear Claude context

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

1. Phases 1–12 are complete (see progress table below). Next milestone = **Phase 13 (v2.0)** — 3D Visualization & Sun/Shade.
2. Read the relevant section in `docs/roadmap.md` for the user story or follow-up issue you're tackling.
3. Check `git status` and recent git history (`git log --oneline -20`).
4. Create feature branch and implement.

**Maintaining this file:** Update progress table when US status changes; add new patterns when discovered; keep Quick Reference commands current.

## Phases 1-12 Complete

All user stories from Phase 1 through Phase 12 are delivered (verified per-US against code).
Full history: see `docs/roadmap.md`.

> **Version note**: CI release workflow (`release.yml`) is the sole source of truth for versions. Never create git tags manually.

## Phase 12 ✅ Complete (v1.9.0 – v1.10.x)

| Status | US    | Description                              | Block              |
| ------ | ----- | ---------------------------------------- | ------------------ |
| ✅     | 12.1  | Weather forecast widget in Dashboard     | Weather            |
| ✅     | 12.2  | Frost alert & plant-aware warnings       | Weather            |
| ✅     | 12.3  | DXF export                               | Interoperability   |
| ✅     | 12.4  | DXF import                               | Interoperability   |
| ✅     | 12.5  | Multi-page PDF export                    | Interoperability   |
| ✅     | 12.6  | Shopping list generation                 | Smart Features     |
| ✅     | 12.7  | Pest & disease log                       | Smart Features     |
| ✅     | 12.8  | Succession planting                      | Smart Features     |
| ✅     | 12.9  | Garden journal (map-linked notes)        | Smart Features     |
| ✅     | 12.10 | Soil health tracking & amendment calc    | Smart Features (all 5 sub-stories complete) |
| ✅     | 12.11 | Smart amendment composition + toggleable library + soil texture | Smart Features |

## Phase 13 ✅ Complete (Package A — CAD Precision Boost, v1.11.0)

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | A1    | Relative coordinate input `@dx,dy` (status bar + cursor overlay) |
| ✅     | A2    | Polar coordinate input `@dist<angle`                             |
| ✅     | A3    | Midpoint + intersection snap modes, View-menu toggles            |
| ✅     | A4    | Dynamic Input cursor-anchored overlay                            |

See **ADR-020** (snap engine: provider registry + quadtree spatial index) and **ADR-021** (input pipeline: shared `CoordinateInputBuffer`).

## Phase 13 ✅ Complete (Package B — closing the CAD precision gap, v1.12.0)

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | B1    | Cubic Bezier pen tool (`B`) — click-drag per anchor, smooth tangent default |
| ✅     | B2    | 3-point Arc tool (`A`) — circumcenter math + collinear → polyline fallback |
| ✅     | B3    | Fillet (`Shift+F`) + Chamfer (`Shift+C`) — polyline/polygon mutate in place; rectangle → polygon-with-arc (destructive, undoable) |
| ✅     | B4    | Nearest-point fallback snap (priority 45, default off)           |
| ✅     | B5    | Perpendicular snap from active tool's `last_point` (priority 25) |
| ✅     | B6    | Tangent snap onto circles + arcs from `last_point` (priority 26) |

> US-B7 (Paper Space MVP) was dropped during PR #191 manual-test review: the existing `pdf_report_service` already covers print-to-PDF at chosen paper sizes, so a second-space CAD-style print workflow added nothing on top. `FILE_VERSION` stays at 1.4 (bezier + arc item types). The `paper_layouts` key written by short-lived draft builds is silently ignored on load.

See **ADR-022** (Bezier model + filleted-rectangle conversion) and **ADR-023** (snap pipeline v2).

Next: **Phase 14 (v2.0)** — 3D Visualization & Sun/Shade (Future). See `docs/roadmap.md`.

## Phase 12 issue work

| Status | Issue / PR | Description                                                          |
| ------ | ---------- | -------------------------------------------------------------------- |
| ✅     | #170 / #174 | Auto-populate plant species data on drop + bundled species DB (118 records, ADR-014). Auto-fires US-12.10d warnings. |
| ✅     | #173 / #175 | Soil-warning refresh on reparent + plant z-elevation above bed; bonus fix for edit-via-history duplicate guard. |
| ✅     | PR #184    | Sims-style toolbar: Object Gallery moves out of sidebar into 10 category dropdowns + global search (ADR-018). Adds `UiStateStore` for window/splitter/panel persistence. |
| ✅     | satellite picker | Embedded Google Maps satellite background picker (ADR-019). New `MapPickerDialog` (`QWebEngineView` + JS Maps API + Static Maps fetch with mosaic stitching), drag-to-define rectangle, analytical pixel→meter scale from Web-Mercator, canvas auto-resizes to the selection, geo metadata persists in `.ogp`. API key via `OGP_GOOGLE_MAPS_KEY` in `.env`. |
| ✅     | #199 / #204 | Data-loss-on-update fix (ADR-027). New `app/paths.py` chokepoint routes every `QFileDialog` to `<Documents>/Open Garden Planner` (or the open project's folder), never the install dir. NSIS uninstaller rescues top-level `$INSTDIR\*.ogp` to `Documents\Open Garden Planner\Recovered Plans` before `RMDir /r`; `/SD IDOK` keeps silent upgrades from hanging. Fix is forward-protective — the pre-fix→fixed upgrade still runs the old uninstaller. |
| ✅     | #200 / #205 | Properties-panel focus-loss fix: the **Name** (`QLineEdit`) and **Text Content** (`QTextEdit`) fields lost focus on every keystroke because each emits `can_undo/redo_changed`, which deferred-rebuilds the whole form via `set_selected_items`, destroying the focused editor. Widened that method's focus-preservation guard from `QDoubleSpinBox` only to `(QAbstractSpinBox, QLineEdit, QTextEdit)`. See §11.4 pitfall. Follow-up #206 filed for the underlying rebuild-on-every-signal smell (incremental panel updates). |
| ✅     | #201 / #207+#208 | (v1.16.0) New layers default to the top of the layer order + **all layer operations undoable** (FR-LAYER-08/09). #208 (stacked, merged into #207's branch pre-master so one release): `LayersPanel` is now a pure view — every layer op (add/delete/rename/reorder/visibility/lock/opacity) routes through 5 new commands in `core/commands.py`; opacity drags coalesce to one undo step via `preview_layer_opacity()` + commit-on-release; the §11.4 panel↔scene list aliasing is fixed (defensive copy). Command descriptions translated (new "Commands" i18n context). Follow-up #209 filed: undo/redo doesn't `mark_dirty` (pre-existing, all commands). |
| ✅     | #210 / #214 | (v1.16.2) Properties-panel free-text undo granularity + command-description i18n. Name (`QLineEdit`) and Text Content (`QTextEdit`) committed a `ChangePropertyCommand` on **every keystroke** → N undo entries + (post-#209) N heavyweight `calendar_view.refresh()` calls per edit. Now `textChanged` live-updates the item only; a single command commits on a **600 ms debounce or focus-out** (`FocusOutTextEdit` adds the focus-out signal QTextEdit lacks). Debounce (not focus-out-only) is required so mid-edit Ctrl+Z works — the Undo `QAction` is disabled until `can_undo` and shadows the field's own undo. Second-order trap fixed: a pending debounce is **flushed before any form rebuild** (`_pending_text_commits` + `_flush_pending_text_commits()` in `set_selected_items`), else the rebuild destroys the field+timer and the edit is lost from undo. Also localized `ChangePropertyCommand.description`: the `{property}` fragment is now translated under the `Commands` context (18 German fragments; raw attr-name fragments + `f"text {prop}"` normalized via `_TEXT_PROPERTY_LABELS`). Three senior-review rounds (P1 flush bug caught + fixed in round 2). See §11.4 (two new pitfalls). #206 still tracks the underlying rebuild-on-every-signal smell this works around. |
| ✅     | #213 / #217 | (v1.16.4) Assigning a database species to an **existing** generic plant now visibly resizes it. Issue #213 asks that Diameter/visual update; the first cut only refreshed the dashed spacing ring, which paints solely when selected **and** larger than the footprint — so a placeholder placed larger than the species' spread showed no change. Fix: assignment now resizes the **drawn footprint** so its diameter == `max_spread_cm` (centre fixed) via new `CircleItem.set_radius_centered()`, folded into a single undoable `ApplySpeciesCommand` (metadata + spacing override + radius revert together) shared by all paths (panel Load/Create + Plants-menu search in `application.py`). Resize is **silent** unless a manual `spacing_radius_cm` override conflicts (then Apply/Keep prompt). `CustomPlantsDialog` got OK/Cancel + double-click-to-confirm. **P0 caught in senior-review round 2**: the resize kept the *visual* centre fixed but not `transformOriginPoint`, so a **rotated** plant saved a displaced `pos+center` (drift on reload, jump on next rotation) — fixed by syncing the pivot to the new centre, pinned by `test_apply_keeps_rotated_plant_centered`. Three senior-review rounds. Deleted dead `_save_to_custom_library`. See §11.4 (footprint-vs-ring + `transformOriginPoint == rect.center()` invariant) and FR-PLANT-17. |
| ✅     | #219 / #220 | (v1.16.5) Rotation pivot correctness: `RotationHandleMixin._apply_rotation` pivoted on `boundingRect().center()`, but a plant showing the **antagonist badge** has an asymmetric `boundingRect` (+x/+y overflow only), so the pivot drifted off `rect().center()` — breaking the serializer invariant (a circle saves as `pos + rect.center()`, rotation as a separate angle). Since `_antagonist_warning` is **runtime-only (never serialized)**, the save-time pivot (badge on) disagreed with the load-time pivot (badge off): a rotated badged plant drifted on save/reload **with no resize involved**. Fix: pivot about `rect().center()` when the item exposes `rect()` (Circle/Rectangle/Ellipse), else `boundingRect().center()` (Text/Callout/Polyline; Polygon overrides but calls `super()`, no `rect()`). Pivot now invariant to badge state → toggling the badge needs no re-rotation. Pinned by `test_rotation_pivots_about_rect_center_with_badge` (+ Rectangle/Ellipse insurance test). Clean single senior-review pass. See §11.4 (closed: `transformOriginPoint == rect.center()` invariant now enforced at the rotation site). |
| ✅     | #209 / #211 | (v1.16.1) Undo/redo data-loss fix: after a save, `undo()`/`redo()` changed the scene without setting the dirty flag (only `execute()` emitted `command_executed`→`mark_dirty`), so closing skipped the unsaved-changes prompt and silently discarded the change. Added `CommandManager.stack_changed` signal (emitted by execute/undo/redo, **not** `clear()` so new/load stays clean) wired to `mark_dirty`. Senior-review found the deeper rot: `command_executed` was load-bearing for dirtiness on ~30 direct `_undo_stack.append` + hand-emit sites (resize handles, vertex drags, live property edits). Added `register_applied(command)` — appends + clears redo + emits the full signal set **without** re-executing — and migrated every direct-append site to it. Invariant: **exactly two ways onto the undo stack** (`execute()` runs it, `register_applied()` for already-applied), both dirty the document. Also migrated all legacy command `description` f-strings to `QCoreApplication.translate("Commands", …)`. See §11.4 (two-chokepoint invariant). Follow-up #210 filed: per-keystroke calendar churn on free-text fields. Senior-review P2 note: the `{property}` payload in `ChangePropertyCommand.description` is still raw English (pre-existing). |
