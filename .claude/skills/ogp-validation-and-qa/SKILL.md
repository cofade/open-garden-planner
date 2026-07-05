---
name: ogp-validation-and-qa
description: >
  What counts as EVIDENCE in Open Garden Planner and how to produce it. Load when:
  writing or placing any test (unit/integration/ui); deciding whether a piece of work
  is "done"; preparing a PR or a manual-testing checklist; judging whether test
  results suffice as proof; a reviewer or the user asks "how do you know this works?";
  pinning a bug fix with a regression test; adding a bed/plant-parent feature (golden
  parametrised gate must be extended); or a test passes alone but fails in the full
  run. Covers the evidence hierarchy (CI floor → senior-reviewer → manual-test
  sovereignty), the §8.10 integration-test policy, regression-pinning discipline,
  the full quality-gate battery and the CI-vs-local gate split, and manual-test
  checklist standards.
---

# OGP Validation & QA — what counts as evidence

All facts verified against the repo at v1.23.0, 2026-07-04. Re-verification commands at the bottom.

## When NOT to use this skill

- Sequencing of process gates (branch → review → draft PR → merge → version sync): that is `ogp-change-control`. This skill defines *what evidence each gate demands*, not the order of gates.
- Instrumenting code to find a bug: `debug-verbose` skill and `ogp-diagnostics-and-tooling`.
- Qt event-delivery theory (why hand-built events aren't delivered, transform math): `ogp-qt-cad-reference`. This skill only tells you *which* event style to use in tests.
- Post-mortems of specific shipped bugs: `ogp-failure-archaeology`.
- Build/run mechanics (venv paths, PyInstaller spec details): `ogp-build-and-run`.

---

## 1. The evidence hierarchy

Memorize this ordering. In this project, **"works in tests" ≠ done.**

| Level | Evidence | Status |
|---|---|---|
| 0 | Code compiles, app launches | Not evidence |
| 1 | Green CI (pytest + ruff + bandit, `ci.yml`) | **The floor, never the ceiling.** CI has stayed green while the local full suite was broken (see §4, "passes alone" mode). |
| 2 | Full local gate battery incl. exe smoke (§2 below) | Required before every merge — the exe build is NOT in CI (verified: `ci.yml` has only lint/test/security jobs; PyInstaller runs only in `release.yml` after merge to master). |
| 3 | `senior-reviewer` agent pass (`.claude/agents/senior-reviewer.md`), fresh worktree, branch diff | **Mandatory before opening any PR.** All P0/P1 findings addressed, then re-run for a clean re-review. History shows it catches real P0s (e.g. #213: rotated-plant pivot drift found in review round 2). |
| 4 | **User-confirmed manual testing** | **Sovereign.** The PR stays a *draft* until the user confirms manual testing passed. No agent, test suite, or review substitutes for it. |

Why manual testing outranks everything — three shipped-looking features that green tests did not save:

- **ADR-030 sidebar (#226):** the first cut (QSplitter, reparent-on-pin) passed its tests and **failed manual testing** — opening a panel reordered the list. Redesigned wholesale (single QVBoxLayout, never reparented).
- **US-B7 Paper Space:** dropped entirely at PR #191 manual-test review — it worked, but added nothing over the existing PDF pipeline. Manual review judges *value*, not just correctness.
- **D1.3 `render_canvas_image` layers param:** tests green, but manual testing showed `layers` was subtractive-only (could hide, never show a user-hidden layer). Semantics reworked post-test.

Rule: never claim "done" or mark a PR ready on levels 1–3 alone. Surface a manual checklist (§5) and wait.

---

## 2. The quality-gate battery

Run all of these locally before any PR (commands verified against CLAUDE.md Quick Reference + `pyproject.toml`; paths are Windows-venv style as used in this repo):

| Gate | Command | Pass criterion | In CI? |
|---|---|---|---|
| Full test suite | `venv/Scripts/python.exe -m pytest tests/ -v` | 0 failures **in the full run**, not per-file | Yes (`ci.yml` `test` job, `QT_QPA_PLATFORM=offscreen`) |
| Lint | `venv/Scripts/python.exe -m ruff check src/` | Clean | Yes (`lint` job) |
| Security (SAST) | `venv/Scripts/python.exe -m bandit -r src/ --severity-level high` | No HIGH findings (MEDIUM/LOW are logged, non-blocking — §8.11) | Yes (`security` job) |
| i18n gate | `pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` | Zero unfinished strings. **Limit:** only sees strings *registered* via `tr()`/`QT_TR_NOOP`/`translate()` — a hardcoded English f-string is invisible to it | Yes (part of full suite) |
| Exe build + smoke | `venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm` then `timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe` | **Exit code 124 = pass** (app survived 8 s and was killed by timeout; any other exit = crash on launch) | **No — local-only duty.** `ci.yml` never builds the exe; `release.yml` builds the installer only *after* merge to master (as of 2026-07-04). A frozen-build breakage found post-merge is a broken release. |

Also run per CLAUDE.md when UI strings changed: `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py` then `scripts/compile_translations.py` *before* the i18n gate test.

Full-battery shortcut: the `analyze-pr` skill runs the four fast layers in parallel plus the exe smoke; `finalize-us` repeats the senior-reviewer pass pre-PR.

---

## 3. Integration test policy (§8.10 — mandatory, read the source: `docs/08-crosscutting-concepts/README.md` § 8.10)

**Every user story ships with at least one end-to-end integration test in `tests/integration/test_<feature>.py`. No merge without it. No exceptions.** Minimum shape: activate tool → simulate gesture → assert scene state.

### Standard fixture (already exists — reuse, don't redefine)

`tests/integration/conftest.py` provides `canvas` and `mouse_event`:

```python
@pytest.fixture()
def canvas(qtbot):
    scene = CanvasScene(width_cm=5000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)   # always — predictable coordinates
    return view

@pytest.fixture()
def mouse_event():
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event
```

Plus the `draw_rect(view, event, x1, y1, x2, y2)` helper for rectangle drags.

### Two ways to drive interaction — pick the right one

1. **Tool business logic (the default):** call the tool's direct API — `tool.mouse_press(event, scene_pos)` / `mouse_move` / `mouse_release` — with the `MagicMock` event above and a `QPointF` in **scene coordinates**. This bypasses the Qt event pipeline while testing real logic (§8.10 sanctions this).
2. **Anything involving drag handles / real event delivery:** a hand-built `QMouseEvent` is **not delivered** to an `ItemIgnoresTransformations` child item (§11.4, the #193 mouse-grab pitfall). Use `QTest.mousePress/mouseMove/mouseRelease` on `view.viewport()` after `canvas.centerOn(handle.scenePos())` and `QTest.qWaitForWindowExposed(canvas)`. Working example: `tests/integration/test_curve_vertex_edit.py` (lines ~218–283). Why Qt behaves this way: see `ogp-qt-cad-reference`.

### Coordinate system reminder (source of silent wrong-assert bugs)

- **Assert in raw scene coordinates** — the same `QPointF`s you pass to
  `tool.mouse_press(...)`. Scene coordinates ARE the CAD coordinates the user
  sees; the status bar, rulers, DXF, and serialization all consume raw
  `scene_pos.y()` with no conversion. The §8.10 fixtures and every real
  integration test assert in raw scene numbers.
- **Do NOT pipe expected values through `view.scene_to_canvas()` /
  `canvas_to_scene()`.** Those helpers compute `height_cm − scene_y` but have
  **zero production callers** (tests only) — converting through them yields
  `H−y`-mirrored numbers production never emits, which is exactly the silent
  wrong-assert bug this section warns about.
- §8.10 describes the abstract-Qt "scene = Y-down, top-left; convert with
  `scene_to_canvas`" framing; that is *not* what the data path does. See
  **`ogp-qt-cad-reference` §1** — the single owner of the Y-axis reconciliation
  — for why the two repo docs (§8.10 abstract vs §11.4 operative) diverge.

### qtbot + ruff

Every PyQt6 test needs the `qtbot` fixture **even if unused** (it initializes Qt). Unused-arg lint is already handled globally: `pyproject.toml` has `[tool.ruff.lint.per-file-ignores]` → `"tests/**/*.py" = ["ARG001", "ARG002"]`. Do not add per-line `# noqa: ARG002` unless a file-local convention already does (some files annotate for readability).

CI note: integration tests run headless via `QT_QPA_PLATFORM=offscreen` (set session-wide in `tests/conftest.py`, and in `ci.yml`).

---

## 4. Regression pinning discipline

**Pin every fixed bug.** Convention: the fix's §11.4 entry (`docs/11-risks-and-technical-debt/README.md`) names the test — "Pinned by `<test>`" (e.g. `test_rotation_pivots_about_rect_center_with_badge`, `tests/integration/test_rotation_aware_resize.py`, `tests/unit/test_smart_symbol_library.py`). A fix without a named pinning test is incomplete. Cross-ref: `ogp-failure-archaeology` for the incident narratives; `ogp-docs-and-writing` for how to write the §11.4 entry.

### The parametrised golden gates — MUST extend, not just pass

`tests/integration/test_bed_context_menu.py` is the enforcement arm of §8.14: `BED_SHAPES` parametrises across **all eight** plant-parent factories (RectangleItem raised-bed, PolygonItem, EllipseItem, CircleItem garden-beds, container-rect, wall-planter, round-container, trellis) and asserts each `BedMenuActions` field, plus a source-level `inspect.getsource` check that every shape's `contextMenuEvent` routes through `build_bed_context_menu` + `dispatch_bed_action`. **When adding any bed/plant-parent action, §8.14's playbook step 6 is the linchpin: add one `assert actions.<new_field> is not None` to the parametrised test.** Skip it and the test stays green today but catches nothing tomorrow — that exact omission is why pest-log and succession features each shipped missing from some shapes (twice in three months, per §8.14).

### Rotated-item tests are mandatory for geometry mutations (the #218 lesson)

Unrotated tests pass green while rotated behavior is completely broken: the #218 resize bug (circle diameter refusing to grow, center drift, ghost pixels) was invisible at 0° because the incoherent math degenerates to correct at identity rotation. Pattern to copy: `tests/integration/test_rotation_aware_resize.py` parametrises `_ANGLES = [0.0, 45.0, 215.0]` × shape × handle type. Rule: **any change that mutates item geometry (resize, reanchor, pivot, serialization of pos/center) gets test cases at ≥ two non-zero, non-axis-aligned angles.** Also assert the invariant `transformOriginPoint == rect().center()` after mutation (#219/#218 closure in §11.4).

### "Passes alone, fails in full run" is a first-class failure mode

Two documented instances (§11.4):

- `QSettings.setDefaultFormat/setPath` are process-global statics Qt never reverts — one test poisoned every later `QSettings` in the session; **6 tests failed only in the full run while CI stayed green** (different collection order). Tell: every failing getter returns exactly the coded default.
- A slot on an app-global signal (`QApplication.focusChanged`) outlived its widget; pytest-qt fails whichever *later* test the stray exception lands in.

Rules: never touch Qt global statics in tests (monkeypatch a factory instead — `tests/conftest.py`'s `isolate_qsettings` is only a tripwire, not a license); make app-global-signal slots teardown-safe; and **the pass criterion is the full `pytest tests/ -v` run, never the changed file alone.** When you hit this mode, suspect shared global/singleton state before the code under test.

---

## 5. Manual-test checklist discipline

Every coding job **must surface a manual-testing checklist** (CLAUDE.md Workflow step 8) alongside the draft PR. The user executes it; their confirmation is the release gate (§1 level 4).

A good checklist — model it on `analyze-pr` Phase 4 (`.claude/skills/analyze-pr/SKILL.md`), the house exemplar:

- **Format each item as `shortcut / menu path → expected visual result`.** Falsifiable observations, not "check it works". Prefix with the launch command `venv/Scripts/python.exe -m open_garden_planner` where useful.
- **Golden path + at least one edge case per feature**, derived from acceptance criteria in `docs/roadmap.md` / `docs/functional-requirements.md`. Standard edge cases: empty input, degenerate geometry, undo/redo, save→reload roundtrip.
- **Risk-surface items the diff implies but nobody wrote down.** Read the diff stat and add checks by touched area, e.g.: `.ogp` schema / `FILE_VERSION` → open old file, save, reopen on the previously-released exe; anything geometric → repeat on a **rotated** item (§4); anything with a badge/overlay → toggle it and re-check (the #219 class); translations → switch to German and re-walk the path.
- Subtract what automation already proved — don't ask the user to re-run what pytest covered; list only the manual-only remainder.

---

## 6. Where a new test goes

| Layer | Directory | What belongs here | Fixture needs |
|---|---|---|---|
| Unit | `tests/unit/` | Qt-free logic: `core/`, `models/`, `services/` (sizing math, task generators, parsers, agent-api queries). Fast, no scene. | Usually none; `qtbot` only if a Qt class is touched |
| Integration | `tests/integration/` | Full workflows through `CanvasScene`/`CanvasView`: tool gestures, undo/redo, context menus, panel wiring, save/load roundtrips | `canvas` + `mouse_event` from `tests/integration/conftest.py` |
| UI/widget | `tests/ui/` | Single dialog/panel behavior in isolation (combo contents, field formatting, dialog buttons) | `qtbot` |

Naming: `test_<feature>.py`, classes `Test<Aspect>`, one file per feature/US (see the existing ~70 integration files for granularity).

Decision rule: **a unit test suffices only when the logic is Qt-free and the US's user-visible workflow is already covered by an integration test.** The per-US integration test is non-negotiable (§3) — unit tests are additional precision, not a substitute. Prefer pushing logic into Qt-free modules (the house pattern: `core/plant_sizing.py`, `services/task_generator.py`, `agent_api/queries.py`) precisely so it can be unit-tested, then keep one thinner integration test over the wiring.

Test-suite hygiene inherited automatically from `tests/conftest.py` (don't re-implement): offscreen Qt, isolated `QSettings` store cleared per test, weather network stubbed, agent-API server disabled.

---

## Sibling cross-references

`ogp-change-control` (gate *sequencing*, draft-PR rules, release machinery) · `ogp-debugging-playbook` + `debug-verbose` (evidence-first bug hunting) · `ogp-failure-archaeology` (the incidents behind these rules) · `ogp-qt-cad-reference` (why QTest-on-viewport, coordinate frames, ItemIgnoresTransformations) · `ogp-architecture-contract` (Qt-free layering that makes unit tests possible) · `ogp-build-and-run` (venv/PyInstaller mechanics) · `ogp-diagnostics-and-tooling` (instrumentation) · `analyze-pr` (runs this battery for a PR + drafts the manual list) · `finalize-us` (pre-PR wrapper incl. senior-reviewer) · agent `senior-reviewer` (level-3 evidence).

---

## Provenance and maintenance

Volatile facts date-stamped 2026-07-04 (v1.23.0): CI-vs-local gate split, BED_SHAPES factory count (8), battery commands. Re-verify with:
`grep -n "PyInstaller\|pyinstaller" .github/workflows/ci.yml .github/workflows/release.yml` (exe build must still be release-only) · `sed -n '310,375p;563,650p' docs/08-crosscutting-concepts/README.md` (§8.10 policy + §8.14 playbook) · `grep -c "pytest.param" tests/integration/test_bed_context_menu.py` (golden-gate breadth) · `grep -n "ARG001" pyproject.toml` (per-file ignore) · `grep -n "Pinned by" docs/11-risks-and-technical-debt/README.md` (pinning convention alive) · `grep -n "_ANGLES" tests/integration/test_rotation_aware_resize.py` (rotation parametrisation) · CLAUDE.md Quick Reference (battery commands, timeout-8 = exit 124).
