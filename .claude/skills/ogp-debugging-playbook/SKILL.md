---
name: ogp-debugging-playbook
description: >
  Fast symptom→cause→experiment triage for Open Garden Planner's recurring failure modes.
  Load this when: a bug is reported (by a user, manual tester, or reviewer); a test fails
  unexpectedly; CI is red while local is green (or vice versa); a test passes alone but fails
  in the full run; behaviour differs from what the code appears to do; a visual glitch appears
  on the canvas (mirrored text, ghost shapes, items drifting/jumping, handles that won't drag);
  an export (PNG/SVG/PDF/DXF) looks wrong or empty; the German UI shows English or mojibake;
  panels go stale or steal focus; the packaged exe crashes or a bundled service silently fails.
  This skill classifies the symptom against the project's hard-won pitfall chronicle so you
  fix from precedent instead of re-fighting a solved bug.
---

# OGP Debugging Playbook

Fast triage for this repo's *recurring* failure modes. Every row below is grounded in a
documented incident — the project has already paid for these lessons once. Your job:
match the symptom, run the cheapest discriminating experiment, follow the fix pointer.

Ground-truth sources (read the matching entry BEFORE changing code):

| Source | What it holds |
|---|---|
| `docs/11-risks-and-technical-debt/README.md` §11.4 | The pitfall chronicle — one entry per hard-won lesson, with contracts and regression tests |
| `.claude/skills/debug-verbose/skill.md` | Instrumentation method + full case studies (symptom → wrong theories → key log line → root cause) |
| `docs/08-crosscutting-concepts/README.md` §8.9 | QGraphicsView overlay/geometry patterns (incl. §8.9.8 rotation invariant) |
| `docs/08-crosscutting-concepts/README.md` §8.19 + `docs/07-deployment-view/README.md` §7.6 | MCP server threading pitfalls + PyInstaller bundling fixes |

Jargon used once, defined once:
- **Y-flip**: the canvas view applies `scale(zoom, -zoom)` so positive scene Y is visually *up* (CAD-style, origin bottom-left). Anything drawn or exported without accounting for this appears mirrored or misplaced. (§11.4 "Canvas Y-axis flip")
- **`ItemIgnoresTransformations`**: Qt flag making an item render at fixed pixel size regardless of zoom. Used by all drag handles, labels, badges. It has three separate failure modes (rows 2, and export rows below).
- **The chronicle**: §11.4. When this playbook says "chronicle: `<keyword>`", grep that keyword in §11.4 for the full entry.

## When NOT to use this skill

- You want the full narrative of an incident (wrong theories, evidence, timeline) → `ogp-failure-archaeology` owns the chronicle-as-history; this skill is fast lookup only.
- You need the *instrumentation how-to* (what to print, where, templates) → invoke `/debug-verbose`; do not reinvent it from here.
- You need measurement/profiling tooling details → `ogp-diagnostics-and-tooling`.
- You need Qt or CAD-geometry *theory* (why QGraphicsScene works the way it does) → `ogp-qt-cad-reference`.
- You are writing new tests or the QA gate, not chasing a bug → `ogp-validation-and-qa`.
- The "bug" is a missing feature or a design disagreement → `docs/roadmap.md` + `ogp-change-control`.

---

## Triage protocol

1. **Reproduce first.** Get exact steps, exact object types (rectangle bed vs polygon bed vs circle plant — they are four independent classes, see row 18), rotation state, and whether a save/reload or undo/redo is involved. Half the rows below only fire under rotation or across a save/load boundary.
2. **Classify against the tables below.** Match on the symptom column (phrased the way a tester says it). If a row matches, read the cited §11.4 chronicle entry / case study before touching code — it names the contract you must preserve and the regression test that pins it.
3. **If no row matches, or two rows compete: stop theorising and invoke `/debug-verbose`.** That skill's method — `print`-based instrumentation with `[TAG]` prefixes, `traceback.format_stack()` at every "who called me?" site, reproduce manually, read stdout — is the project standard. Do not duplicate its templates here; load the skill.
4. **Fix from evidence.** Prefer the fix pattern the chronicle already established (e.g. route through the existing command/helper) over a new local patch — most §11.4 entries end with a contract ("any new X must also do Y"); violating it is how these bugs recur.
5. **Document.** After the fix: remove all instrumentation prints; add a **Case study** entry to `.claude/skills/debug-verbose/skill.md` (symptom, wrong theories, key log line, root cause, lesson) and a §11.4 entry if a new contract emerged. This duty is mandatory per `CLAUDE.md`; format guidance in `ogp-docs-and-writing`.

Run commands note (2026-07-03): `CLAUDE.md` commands use `venv/Scripts/python.exe` — the dev machine is Windows. On Linux/CI the interpreter is `venv/bin/python` and headless Qt needs `QT_QPA_PLATFORM=offscreen` (already set in `tests/conftest.py` and `.github/workflows/ci.yml`).

---

## Triage table A — canvas geometry & interaction

| # | Symptom (as reported) | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 1 | "Rotated item drifts on save/reload" / "jumps on the next rotation" / "resize under rotation collapses, drifts, or leaves a ghost disc" | Broken invariant `transformOriginPoint() == rect().center()`. Known breakers: pivoting on `boundingRect().center()` while a runtime badge asymmetrically expands the bounding rect; a resize that recentres visually but forgets the origin; post-correcting an incoherent resize step | Print `item.transformOriginPoint()` vs `item.rect().center()` after the gesture — any divergence confirms it. Reproduce **with rotation ≠ 0** (0° always looks fine) and across save/reload | §8.9.8 in `docs/08` (the canonical statement). Route resizes through `resize_rect_item_keeping_anchor` in `src/open_garden_planner/ui/canvas/items/resize_handle.py`; rotation via `RotationHandleMixin._apply_rotation` (pivots on `rect().center()`). Tests: `tests/integration/test_rotation_aware_resize.py` | #213/#218/#219, ADR-028; chronicle: `transformOriginPoint` |
| 2 | "Handle shows but won't drag" / new handle is inert while identical existing handles work | Qt silently drops the mouse grab on `ItemIgnoresTransformations` child items between events. `CanvasView` re-grabs — but only for handle types in its `isinstance` allow-list (`src/open_garden_planner/ui/canvas/canvas_view.py`, grep `_active_drag_handle`, ~line 1961). A new handle class not in the tuple gets the press, then nothing | After the press, check `view._active_drag_handle` — `None` means the allow-list missed. Also: `scene.mouseGrabberItem()` goes `None` before the first move | Add the handle class to the allow-list tuple in `CanvasView.mousePressEvent`. Testing: use `QTest.mousePress/Move/Release` on `view.viewport()` after `view.centerOn(target)` — a hand-built `QMouseEvent` is **never delivered** to `ItemIgnoresTransformations` children (see Qt facts below) | #193, ADR-025; debug-verbose case study "inert curve handles"; chronicle: `mouse grab` |
| 3 | "Badge/label text is mirrored" / text positioned at visual top when code says bottom | Y-flip: `painter.drawText()` (or any direct draw) inside `QGraphicsItem.paint()` inherits `scale(zoom, -zoom)` | Zoom in/out: direct-drawn text stays mirrored at all zooms. Compare with an existing correct badge (`SuccessionBadgeItem` in `src/open_garden_planner/ui/canvas/items/garden_item.py`) | Use a child item with `ItemIgnoresTransformations` (e.g. `QGraphicsSimpleTextItem`), never `drawText` in `paint()`. Anchor at `rect.top()` (= visual bottom after flip) | Chronicle: `renders upside-down` |
| 4 | Directional feature (array, offset) goes the wrong way vertically; imported/exported DXF vertically flipped | Y-flip sign error. For user-facing angles: `dy = -spacing * sin(angle)`. For DXF: scene is already Y-up, so `dxf_y = scene_y` — the "obvious" `canvas_h - scene_y` **double-flips** | One test shape near the canvas bottom edge; round-trip it | Chronicle: `Canvas Y-axis flip` and `DXF Y-axis`; `src/open_garden_planner/services/dxf_service.py` | Chronicle entries (Package DXF work) |
| 5 | "Snap glyph shows on the midpoint but the committed vertex lands on a grid line" | Grid snap re-rounds the anchor-snapped point inside the tool's own `snap_point` call — two snap layers composed without rules | Toggle grid snap off: if the vertex now lands on the anchor, confirmed | `CanvasView.snap_point()` short-circuits grid rounding when `self._current_snap is not None` — keep that single composition site; test `tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap` | Package A, ADR-020/021; chronicle: `Grid snap silently overrides` |
| 6 | "Typing Enter in the coordinate overlay places the vertex then instantly closes the polyline" (or any QLineEdit inside the viewport triggers a tool action) | `QLineEdit.keyPressEvent` calls `event.ignore()` for Return/Enter, so the key bubbles to `CanvasView.keyPressEvent` → active tool | Instrument the tool's `key_press` — does it receive Return right after the overlay commit? | Intercept Return/Enter in the line-edit subclass and `event.accept()` (see `_DynamicLineEdit`) | Package A US-A4; chronicle: `QLineEdit ignores Return` |
| 7 | "Plant disappears behind its bed" — often only after save/reload | Equal z-values: same layer ⇒ same `z_order * 100`; Qt tie-breaks by **insertion order**, which reverses across JSON load | Check both items' `zValue()` — equal confirms. Live session OK + broken after reload is the signature | Call `ensure_z_above_parent(plant, bed)` (`src/open_garden_planner/core/commands.py`) at **every** attach site — grep existing call sites and mirror them | Chronicle: `stack behind beds`; debug-verbose case study "same-zValue reversal" |

## Triage table B — export (PNG / SVG / PDF)

| # | Symptom | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 8 | Export image completely empty (right size, background colour only) | Negative-height target rect: `QRectF(0, H, W, -H).isEmpty()` is `True` in PyQt6 → `scene.render()` clips to nothing | `print(target_rect.isEmpty())` before `scene.render()` | Painter pre-flip instead: `translate(0, H_px); scale(1, -1)` with a positive rect; `H_px` = image height in **pixels** | Chronicle: `negative-height target rect`; debug-verbose case study |
| 9 | SVG export: brownish wash over the whole canvas / texture fills bleed everywhere (PNG fine) | `QSvgGenerator` never serialises painter clip paths — texture rect is the unconstrained clip bounding rect | Open the SVG in a **real browser** (not `QSvgRenderer` — it is too forgiving and hides this). `grep -c clipPath file.svg` → 0 confirms | Post-processing already exists: `ExportService._fix_svg_qt_texture_clipping()` (`src/open_garden_planner/services/export_service.py`) — check it ran and still pairs shadow/texture groups 1:1. Preview via `scripts/svg_preview.py` | Chronicle: `does not serialize painter clip regions` |
| 10 | SVG texture tiles look upside-down / abstract mush | Pattern tiles stored un-flipped, rendered inside the Y-flipped space | Decode a pattern tile base64 — the tile itself is correct; the composition is flipped | `ExportService._fix_svg_pattern_yflip()` adds `patternTransform="matrix(1,0,0,-1,0,{h})"` | Chronicle: `SVG pattern tiles` |
| 11 | PDF: everything crammed in the top-left corner | `QPdfWriter` defaults to ~1200 DPI; layout math assumes points | Print `painter.viewport()` — device-pixel dimensions ≫ page points | `writer.setResolution(72)` **before** `setPageLayout()` (already done twice in `src/open_garden_planner/services/pdf_report_service.py`) | Chronicle: `setResolution(72)` |
| 12 | PDF: scene appears as a thin strip / offset despite correct-looking flip math | `QPdfWriter`'s painter starts with a **non-identity** transform (margins) | `print(painter.worldTransform())` before your first draw | Render scene to a temp `QImage` first, then `painter.drawImage(content_rect, img)` — never `scene.render()` directly onto the PDF painter | Chronicle: `directly on QPdfWriter painter`; debug-verbose case study |
| 13 | Exported image: text/labels gigantic or minimap thumbnail shows misplaced handles | `ItemIgnoresTransformations` items render at natural pixel size under `scene.render()` (no view involved) | Compare a 10 pt label's size in-app vs in export | `ExportService._prepare_text_for_export()` before render + `_restore_text_after_export()` after; thumbnails hide such items first (§8.9.5) | Chronicle: `render at fixed device-pixel size` |

## Triage table C — tests, CI, teardown

| # | Symptom | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 14 | "Passes alone, fails in the full run" + CI shows `Fatal Python error: Aborted` mid-suite (often the test *after* the guilty one errors) | A `scene.changed` slot starts a `QTimer` whose C++ object is already torn down — `scene.changed` still fires while the scene is cleared during teardown → `RuntimeError` inside a Qt slot → interpreter abort | Run the failing test *after* the full-app test that precedes it in collection order; read which slot raised | Wrap every `.start()` in a `scene.changed`-driven slot with `contextlib.suppress(RuntimeError)`; **never** `scene.changed.connect(lambda: self._timer.start())` — a lambda can't be made teardown-safe. Existing examples: `canvas_view._on_scene_changed_for_soil`, `application._on_scene_changed_for_*` | #230; chronicle: `torn down` |
| 15 | "Passes alone, fails together": an unrelated later test fails with an exception raised in a slot of a widget from an *earlier* test | A slot connected to an **app-global** signal (`QApplication.focusChanged`, `aboutToQuit`, …) outlives its widget; pytest-qt attributes any slot exception to whatever test is running when it fires | The traceback names a widget the failing test never created | Guard the slot body with `try/except RuntimeError: return`; wrap the explicit disconnect in `contextlib.suppress(TypeError, RuntimeError)` (Qt auto-disconnects destroyed receivers, so the manual disconnect races) | PR #235; chronicle: `application*-global signal` |
| 16 | "Passes alone, fails together" where every failing assertion sees exactly the **default** setting value; CI may stay green | Process-global `QSettings.setDefaultFormat()` / `setPath()` leaked from an earlier test — later `QSettings` writes go to a deleted temp path | The tell: actual value == coded default in every failure. `pytest` the failing test alone → green | Never call the QSettings global statics in a test; `monkeypatch.setattr` a QSettings factory instead. `tests/conftest.py` has an `isolate_qsettings` tripwire for `setDefaultFormat` (not `setPath`) | Chronicle: `process-global statics` |
| 17 | Geometry/undo logic provably correct in unit tests, but the real UI gesture is dead | Unit tests call item hooks directly and skip the view routing layer (press→grab→move delivery) — see row 2 | Write one `QTest`-driven viewport test; if it fails while hook tests pass, the bug is in routing, not logic | See row 2; pattern in `#193` regression test `TestHandleDragViaView` | #193 |

## Triage table D — panels, signals, staleness

| # | Symptom | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 18 | "Field loses focus after every keystroke" in a sidebar panel | The panel rebuilds its whole form on every command signal, destroying the focused editor. Root cause fixed for the properties panel by identity-gated incremental refresh (#206) — a *new* field regresses it if it doesn't register a refresher, or a new panel copies the old rebuild-everything pattern | Instrument `set_selected_items` entry with `/debug-verbose` — does it run per keystroke? | New editable fields must `_register_refresh(...)`; relationship-dependent fields must join `_compute_identity`. Free-text fields commit on **debounce + focus-out** (never per keystroke, never focus-out-only) and must flush via `_pending_text_commits` before any rebuild | #200 → #206 → #210; chronicle: `rebuild only on a genuine` and `debounce, not per keystroke` |
| 19 | Panel shows stale data after undo/redo (correct after re-selecting) | Panel wired only to `selectionChanged` (or the legacy `command_executed`, which does **not** fire on undo/redo) | Undo → check panel; re-select same item → panel corrects itself. That asymmetry is the signature | Wire the panel refresh to `cmd_mgr.stack_changed` (fires once per execute/register_applied/undo/redo, never on `clear()`). Test pattern: `tests/integration/test_panel_refresh_wiring.py` | #222/#223/#225; chronicle: `stack_changed` |
| 20 | After a save, undo then close — no "unsaved changes" prompt, edit silently lost | Dirtiness not wired to the undo stack. Contract: exactly **two** ways onto the undo stack — `CommandManager.execute()` and `register_applied()` — both emit the full signal set incl. `stack_changed → mark_dirty`. Hand-rolled `_undo_stack.append(...)` breaks it | Save → Ctrl+Z → is the title-bar `*` present? | Route through `register_applied`; never append to `_undo_stack` directly. Test: `tests/integration/test_undo_redo_dirty.py` | #209; chronicle: `two* ways onto the undo stack` |
| 21 | Sidebar list selection "works only sometimes" / list scroll jumps to top after clicking | (a) Rows cache live `QGraphicsItem` refs that go stale after undo/delete → `setSelected` no-ops; (b) `scene.changed` fires on every repaint and drives a destructive list rebuild racing the click | Click, then check whether a rebuild ran between press and the deferred selection (instrument with `/debug-verbose` + stack traces) | Store `item_id` only, resolve at click time via `scene.find_item_by_id`; defer scene mutation with `QTimer.singleShot(0, ...)`; debounce **and** signature-guard the rebuild (diff before rebuild — a debounce limits *how often*, not *whether*) | #212; chronicle: `store item *ids` |
| 22 | Warning borders (soil mismatch etc.) go stale after dragging a plant in/out of a bed — but update after any *other* edit | `QGraphicsScene.changed` fires only on **visual** changes; Python attribute writes (`parent_bed_id`, `_child_item_ids`) emit nothing, so the debounced refresh never triggers | The stale-until-unrelated-edit pattern is itself the discriminator | Funnel reparenting through `SetParentBedCommand` (it calls `trigger_soil_mismatch_refresh` itself); any new reparent path must call it explicitly (`src/open_garden_planner/core/commands.py`) | #173; chronicle: `only fires on geometry/visibility`; debug-verbose case study |
| 23 | Marking a task done on one surface (calendar vs Tasks tab) invisible on the other | Two surfaces deriving a shared store key differently | Print both surfaces' computed `task_id` for the same task | Both key **and** format must come from one shared function: canonical `species_key()` (`src/open_garden_planner/models/plant_data.py`) + `make_calendar_task_id()` (`services/task_generator.py`). A sync test must build ids the way production does (realistic species with `source_id`), not hand-written strings | #227; chronicle: `derive the key identically` |
| 24 | A startup notification "never appears" | `statusBar().showMessage()` written while a modal dialog (Welcome) covers the window — painted behind it, then expires | Reproduce via the Welcome→recent-project path specifically | Persistent dismissible bar (`TaskReminderBar` pattern) + defer the check with `QTimer.singleShot(0, ...)` past the modal `exec()` | #227 fix #16; chronicle: `modal dialog is invisible` |
| 25 | New bed feature (menu entry, badge) works on rectangle beds but missing on polygon/ellipse/circle beds | Four independently-implemented bed shape classes; hand-wiring one misses the others | Right-click each of the four shapes | Never hand-code per shape: `GardenItemMixin.build_bed_context_menu` + `dispatch_bed_action` central dispatch; extend the parametrised `tests/integration/test_bed_context_menu.py`. Read §8.14 + ADR-017 **first** (CLAUDE.md marks this READ FIRST) | US-12.7/12.8 recurrences; chronicle: `all bed-shape item types` |

## Triage table E — i18n, encoding, data display

| # | Symptom | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 26 | German UI shows an English string even though a translation was registered | The call site bypasses `tr()` — plain f-string or module-level dict looked up directly. `test_german_ts_has_no_unfinished` **cannot** catch this (it only checks strings already extracted into the `.ts`) | Grep the English text in `src/` — is it inside `tr()` / `QT_TR_NOOP` / `QCoreApplication.translate()`? | Wrap at the call site (`self.tr("...").format(...)`; `QT_TR_NOOP` dicts translated at lookup). Add the phrase to `tests/unit/test_i18n.py::TestNoHardcodedEnglish`'s grep list so it can't recur | Chronicle: `does NOT catch hardcoded English` |
| 27 | Entire German UI suddenly mojibake (`ö` → `Ã¶`) after a "harmless" text edit | PowerShell `Set-Content -Encoding UTF8` double-encoded UTF-8 | `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — non-zero = double-encoded | `git checkout HEAD -- <files>`, redo with the Edit tool or Python `open(..., encoding="utf-8")`. Never PowerShell for non-ASCII files | Chronicle: `NEVER use PowerShell` |
| 28 | Undo menu / status bar shows half-English ("text content ändern") | `ChangePropertyCommand` `{property}` fragment not registered under the `"Commands"` i18n context — degrades silently to English, and the unfinished-strings test can't see it | Check `scripts/fill_translations.py` `"Commands"` dict for the fragment | Register the German fragment manually when adding any new `ChangePropertyCommand` property name | #210; chronicle: `Commands* i18n context` |
| 29 | Spin box shows "0 cm" / "0.0" for a value that is actually *missing* | `setSpecialValueText("")` — Qt treats an **empty** special-value string as disabling the feature entirely | Is the special value text empty? | Non-empty placeholder: `setSpecialValueText(self.tr("—"))` paired with `minimum` as the unset sentinel (pattern in `src/open_garden_planner/ui/panels/plant_database_panel.py`) | #231; chronicle: `setSpecialValueText` |
| 30 | Combo shows a confident concrete value ("Annual") for a species whose trait is unknown — and saving corrupts the model | Enum combo excludes the `UNKNOWN` member + `setCurrentIndex(0)` fallback; save path reads `currentData()` back | Load a sparse online-search species; inspect the combo | Prepend a neutral `("—", Enum.UNKNOWN.value)` entry at index 0 for every combo bound to an enum with an unset member | #231; chronicle: `excludes *UNKNOWN` |
| 31 | Feature "silently broken" though its service logic + tests are perfect: values arrive as `None`, or new dataclass fields vanish in the live app | Field added to a dataclass but not to its `to_dict`/`from_dict` (the live path round-trips through metadata dicts; direct-construction tests never do) — or the field has no UI to set it ("ghost field") | Diff `dataclasses.fields(...)` vs `to_dict()` keys; then check the panel actually has a row for the field | Update both serialisation sites + write a `dataclasses.fields()`-driven round-trip test (`tests/unit/test_plant_data_serialization.py` is the model); audit the owning panel | US-12.10d; debug-verbose case studies "mismatch border never appears" + "ghost field" |

## Triage table F — packaging / frozen exe

| # | Symptom | Likely cause | Discriminating experiment | Fix pointer | Incident |
|---|---|---|---|---|---|
| 32 | Exe builds but the embedded MCP server silently fails (GUI fine); or `ModuleNotFoundError: multiprocessing` at server start | `multiprocessing` in the spec `excludes` (uvicorn imports it eagerly even single-process), or missing `collect_submodules`/`copy_metadata` for the mcp/uvicorn/starlette stack | Run the **frozen** exe and hit `http://127.0.0.1:8765/mcp` with an MCP client — dev pytest cannot surface these | `installer/ogp.spec`; full rules in `docs/07-deployment-view/README.md` §7.6. Never `collect_submodules("mcp")` top-level — `mcp.cli` calls `sys.exit(1)` without the `typer` extra and **aborts the build**; collect `mcp.server`/`mcp.shared`/`mcp.types` | US-D1.1; docs/07 §7.6 |
| 33 | Exe won't start / crashes on launch after adding any new dependency | PyInstaller missed dynamically-imported submodules or package metadata | The mandatory pre-merge smoke: `venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm` then `timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe` — exit code 124 (killed by timeout) = success | Add `collect_submodules` + `copy_metadata` in `installer/ogp.spec`, mirroring the §7.6 pattern; `pydantic_core*.pyd` stays `upx_exclude`d | CLAUDE.md Quick Reference; docs/07 |
| 34 | "All my gardens vanished after updating" (Windows) | User data saved under `$INSTDIR` (dialogs defaulting to CWD) + uninstaller `RMDir /r` on upgrade | Where did the user's `.ogp` live? | Every file dialog must route through `app/paths.py` (`get_projects_dir()`), never `""`/CWD; NSIS uninstaller rescues `$INSTDIR\*.ogp` first. Tests: `tests/unit/test_paths.py`, `tests/integration/test_save_location.py` | #199, ADR-027; chronicle: `install directory` |

---

## Qt debugging facts you probably don't know

These are load-bearing for interpreting evidence in this repo (all verified against the chronicle / test suite as of 2026-07-03):

1. **pytest-qt turns any exception raised inside a Qt slot into a failure of the currently running test** — even when the slot belongs to a widget created by an *earlier* test. This is the engine behind every "passes alone, fails together" row (14–16). When a test failure's traceback names code the test never touched, suspect a leaked slot, not the test.
2. **A hand-built `QMouseEvent` passed to `view.mousePressEvent` is not delivered to `ItemIgnoresTransformations` child items** (even when `itemAt` finds them). Use `QTest.mousePress/Move/Release` on `view.viewport()` — real event dispatch — after `view.centerOn(target)` so the target is inside the viewport. This is the only faithful way to test handle drags. (#193 case study.)
3. **`QT_QPA_PLATFORM=offscreen`** makes Qt run headless (no display server). Already set in `tests/conftest.py` and CI; export it yourself for ad-hoc scripts on Linux.
4. **PyQt6 tests require the `qtbot` fixture even when unused** (Qt initialisation); ruff has a per-file ARG002 ignore for test files (CLAUDE.md).
5. **`QGraphicsScene.changed` is both too chatty and too quiet**: it fires on *every repaint* (a firehose — never wire it to a destructive rebuild without debounce + a diff guard, row 21) yet *never* fires on Python attribute writes (row 22). Both directions have bitten this project.
6. **`QGraphicsItem.shape()` is hit-testing geometry, not drawing geometry** — for `QGraphicsPolygonItem` it returns the pen-width stroke *envelope*. Outline items with their primitive (`drawPolygon(self.polygon())`), never `drawPath(self.shape())`. (Case study "stroke envelope".)
7. **Python's `max(iterable, key=...)` is left-biased on ties** — with date-resolution keys, the *first* record with the max date wins, not the newest. Design tie-breaks explicitly. (Case study "max() ties".)
8. **An overridden/monkey-patched Qt event handler must return `None`** — forwarding a `bool` (e.g. `lambda e: QDesktopServices.openUrl(...)`) raises `TypeError: invalid argument to sipBadCatcherResult()`. (Chronicle: `sipBadCatcherResult`.)
9. **`item.pos()` is (0,0) for OGP shape items** — geometry lives in the local rect; the visual centre is `item.mapToScene(item.boundingRect().center())` (or `rect().center()` for the geometric centre, row 1). Coordinates asserted in tests are in cm, scene frame.

---

## Provenance and maintenance

Written 2026-07-03 against master at v1.23.0. Every row cites its §11.4 chronicle entry, debug-verbose case study, or docs/07–08 section; nothing here is folklore. Re-verify before trusting a row after major refactors:

```bash
# Chronicle keywords (one per table row family) — each must still hit docs/11 §11.4:
G=docs/11-risks-and-technical-debt/README.md
grep -c "transformOriginPoint" $G          # row 1
grep -c "_active_drag_handle" $G           # row 2
grep -c "renders upside-down" $G           # row 3
grep -c "setResolution(72)" $G             # row 11
grep -c "torn down" $G                     # row 14
grep -c "store only the stable" $G         # row 21
grep -c "trigger_soil_mismatch_refresh" $G # row 22
grep -c "setSpecialValueText" $G           # row 29
grep -c "NEVER use PowerShell" $G          # row 27
grep -c "register_applied" $G              # row 20

# Source anchors still exist:
grep -n "_fix_svg_pattern_yflip\|_fix_svg_qt_texture_clipping" src/open_garden_planner/services/export_service.py
grep -n "isinstance(grabber" src/open_garden_planner/ui/canvas/canvas_view.py
grep -n "def trigger_soil_mismatch_refresh\|def ensure_z_above_parent" src/open_garden_planner/core/commands.py
grep -n "class TestNoHardcodedEnglish" tests/unit/test_i18n.py
grep -n "multiprocessing" docs/07-deployment-view/README.md

# Sibling docs this skill defers to:
ls .claude/skills/debug-verbose/skill.md
grep -n "8.9.8\|8.19" docs/08-crosscutting-concepts/README.md | head -4
```

Maintenance duty: when a new §11.4 entry or debug-verbose case study lands, add (or update) the matching triage row here — symptom phrased as a tester would say it, plus the discriminating experiment. Keep this file *triage-only*; full narratives belong to the chronicle and `ogp-failure-archaeology`.
