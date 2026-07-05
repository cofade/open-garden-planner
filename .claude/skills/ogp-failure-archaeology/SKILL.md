---
name: ogp-failure-archaeology
description: >
  The chronicle of every major OGP investigation, dead end, rejected fix, and revert — so
  nobody re-fights a settled battle. Load this skill when: (1) you are about to change a
  subsystem that has history (rotation/resize, properties panel, undo stack, task status,
  sidebar lists, exception handling at file-load, release workflow, installer, i18n,
  Agent API render); (2) a bug you're chasing resembles something described here; (3) you
  are tempted to "fix" code that looks wrong (a broad `except Exception`, a debounce plus
  a flush queue, a `rect().center()` pivot, a write-only `task_completions` mirror — it
  may be the scar of a fixed bug); or (4) you're investigating WHY code is written in a
  strange way. Fast triage for a live bug = ogp-debugging-playbook; the invariants as
  forward-looking contracts = ogp-architecture-contract. This skill records how those
  invariants were learned, the hard way.
---

# OGP Failure Archaeology

Repo state when written: v1.23.0, 2026-07-03, default branch `master`, history is
squash-merged PRs. Sources: `docs/11-risks-and-technical-debt/README.md` §11.4 (the
richest), `CLAUDE.md` progress tables, `.claude/skills/debug-verbose/skill.md` case
studies, `docs/roadmap.md`, `docs/09-architecture-decisions/README.md`, `git log`.
Every "pinned by" test file was verified to exist on disk on 2026-07-03.

Entry format: **Symptom → wrong theories/dead ends → root cause → evidence → fix →
status → pinned by**. Not every entry needs every field; short incidents are compressed.

---

## Index — scan this first

| # | Saga | Issues / PRs | One-line lesson | Status |
|---|------|--------------|-----------------|--------|
| 1 | Rotated-geometry saga | #213/#217, #219/#220, #218/#221 | Every geometry mutation must end with `transformOriginPoint == rect().center()`; don't post-correct an incoherent geometry step — fix the step | Closed |
| 2 | Panel-rebuild saga | #200/#205, #206/#222, #206/#223, #225/#230 | Never rebuild a form on every command signal; identity-gated rebuild + per-widget refreshers | Closed (smell remains, see Open) |
| 3 | Undo/dirty data loss | #209/#211 | Exactly two ways onto the undo stack (`execute`, `register_applied`); both must dirty | Closed |
| 4 | Free-text commit granularity | #210/#214 | Debounce + focus-out commit, and flush pending commits before any form rebuild | Closed |
| 5 | Task dual-store convergence | #227, #228/#230 | Two surfaces sharing an id-keyed store must share the *entire* id derivation; dual-write invariants rot — converge to one write path | Closed |
| 6 | Find Plants selection flakiness | #212/#215 (two rounds) | Store ids not item refs, defer the selection, and a debounce is not idempotence — diff before rebuild | Closed (band-aid, see Open) |
| 7 | Smart-symbol exception enumeration | PR #236 (3 review rounds) | At a trust boundary, one broad `except Exception` at the ingestion seam; enumerating families is a losing game | Closed |
| 8 | Release workflow races | (pre-#209 chore race), #229 | Skip releases for chore commits; wait for releases by *tag transition*, never by date matching | Closed |
| 9 | Data loss on update | #199/#204, ADR-027 | User data must never live under `$INSTDIR`; dialogs must never default to CWD | Closed (forward-protective only) |
| 10 | i18n incidents | (US-12.8 era, ongoing) | `tr()` must be on the call path (registration alone is useless); never PowerShell `Set-Content` on UTF-8 | Closed, recurring class |
| 11 | CI-only teardown crashes | #230, PR #235 | `scene.changed` timer slots and app-global-signal slots must be teardown-safe | Closed |
| 12 | Agent API render (D1.3) | PR #242 | `layers` must force-show, not only hide; two mcp-1.28.1 facts are empirical, don't "clean them up" | Closed |
| 13 | Retired: US-B7 Paper Space | PR #191 review | Feature dropped — pdf_report_service already covered it; `paper_layouts` key silently ignored on load | Retired |
| 14 | Export Y-flip saga | US-12.10-era, 4 case studies | QSvgGenerator/QPdfWriter are not faithful painter serializers; validate SVG in a real browser | Closed |
| 15 | Tangent-constraint degeneracy | "make snap-constraints real" PR #198 | Residual *formulation* decides solver conditioning — parallel gradients = rank-deficient | Closed |
| 16 | Inert `ItemIgnoresTransformations` handles | #193/#202 | New drag handles must join `CanvasView`'s allow-list; synthetic QMouseEvents don't reach these children | Closed (opt-in trap remains) |
| 17 | Label editor auto-close | (2026-04-22) | The minimap hid overlay items incl. the focused editor; stack traces at unexpected call sites find external culprits | Closed |
| 18 | QSettings global-static test poison | (test-suite isolation) | Never call `QSettings.setDefaultFormat/setPath` in a test; "passes alone, fails together, value = default" ⇒ global state | Closed |
| 19 | Stale-trigger family | #173/#175 | `scene.changed` fires only on *visual* change — attribute writes need explicit refresh triggers inside commands | Closed |
| 20 | Ghost-field family (US-12.10d) | #170, dataclass round-trip | New dataclass fields need `to_dict`/`from_dict` AND a UI row; construct-and-test ≠ serialize-and-test | Closed |
| 21 | UNKNOWN-enum display corruption | #231/#232 | Combos need a neutral entry for UNKNOWN; `setSpecialValueText("")` is a silent no-op | Closed |
| 22 | Same-z stacking flip on save/load | US-12.10/F2.7 | Equal zValues tie-break on insertion order, which is not stable across save/load — encode parent+1 explicitly | Closed |
| 23 | Bed-menu wiring recurrence | #173, US-12.8 | Four bed shape classes ⇒ hand-wiring per class regressed twice; now centralised + parametrised test | Closed |
| 24 | `max()` left-biased ties | US-12.10/F2.10a | `max(key=date)` returns the FIRST maximal record — design tie-breaks explicitly | Closed |

Cross-references: forward-looking invariants → `ogp-architecture-contract`; live-bug
triage → `ogp-debugging-playbook`; instrumentation method → project skill
`debug-verbose`; release mechanics → `ogp-change-control` / `finalize-us`.

---

## 1. The rotated-geometry saga (#213 → #219 → #218/#221)

Three issues, four PRs (#217, #220, #221), one underlying theme: OGP serializes a circle
as `pos + rect.center()` with rotation as a separate angle pivoting on the centre, so the
whole codebase silently relies on `transformOriginPoint == rect().center()`. Every
chapter below is a different way that invariant got broken. Source: §11.4 (the #213
follow-up block, "Closed (#219)", "Closed (#218)"), ADR-028, debug-verbose case study
"rotated circle drag-resize" (2026-06-17), CLAUDE.md Phase-12-issue-work table.

**Chapter 1 — #213: assigning a species visibly changes nothing.**
- Symptom: assigning a DB species to an existing generic plant didn't visibly resize it.
- Dead end: first cut refreshed only the dashed *spacing ring* — which paints only when
  the item is selected AND `spacing_r > footprint_radius`. A 5 m placeholder given a
  1.5 m shrub shows no ring at all, so "nothing changed on screen".
- Root cause: the visible artefact the user expects to change is the *footprint circle*,
  not the (often hidden) ring. Also: several panel paths wrote
  `metadata["plant_species"]` directly — no `prepareGeometryChange()`/`update()`, no
  repaint, and a manual `spacing_radius_cm` override silently masks the DB value.
- Fix: `ApplySpeciesCommand` (single undoable step) sets metadata AND resizes the drawn
  footprint to `max_spread_cm` via `CircleItem.set_radius_centered()`. Resize is silent;
  only a *conflicting* manual override prompts (Apply/Keep).
- Second trap (senior-review P0, round 2): the resize kept the *visual* centre fixed but
  not `transformOriginPoint` — a **rotated** plant saved a displaced `pos+center` (drift
  on reload, jump on next rotation). Looks correct on screen; an unrotated test passes
  green. `set_radius_centered()` now re-pins the origin.
- Status: closed. Pinned by
  `tests/integration/test_apply_database_species.py::test_apply_keeps_rotated_plant_centered`.

**Chapter 2 — #219: rotated badged plant drifts on save/reload with NO resize involved.**
- Symptom: rotate a plant that shows the antagonist-warning badge, save, reload → drift.
- Root cause: `RotationHandleMixin._apply_rotation` pivoted on `boundingRect().center()`.
  The badge expands `boundingRect()` *asymmetrically* (+x/+y overflow only), so the pivot
  drifted off `rect().center()`. `_antagonist_warning` is runtime-only (never
  serialized), so the save-time pivot (badge on) disagreed with the load-time pivot
  (badge off).
- Fix: pivot about `rect().center()` when the item exposes `rect()`
  (Circle/Rectangle/Ellipse); `boundingRect().center()` only for items with no
  asymmetric decoration (Text/Callout/Polyline). Pivot is now invariant to badge state.
- Lesson: a rotation pivot must come from the *geometric* shape, never the
  decoration-expanded `boundingRect()` — runtime-only decorations otherwise leak into
  persisted geometry.
- Status: closed. Pinned by
  `tests/integration/test_apply_database_species.py::test_rotation_pivots_about_rect_center_with_badge`.

**Chapter 3 — #218/#221: drag-resizing a 45°-rotated circle collapses / drifts / ghosts.**
- Symptom (PR #221 manual test): diagonal corner drag barely changed the diameter or
  collapsed it; centre drifted across the canvas; the dragged handle didn't track the
  cursor; a translucent "ghost" disc lingered.
- Wrong theories: "the #218 re-anchor band-aid is wrong" (it correctly held the
  serialization invariant — the rot was *underneath* it); "the spacing ring should scale
  with the footprint" (no — decoupling is the intended model); "missing
  `prepareGeometryChange` is the whole bug" (only explained the ghost).
- Evidence (the decisive observation): a scripted headless drive of the real
  `ResizeHandle._apply_resize` with cumulative deltas, printing
  rect/radius/pos/origin/visualCenter per step — a `BOTTOM_RIGHT` drag of (80,80) left
  **radius stuck at 50.00**. At exactly 45° a screen-diagonal drag projects entirely onto
  ONE local axis (`local_dy ≈ 0`), so `min(width, height)` picked the *unchanged* axis.
- Root cause, three compounding faults: (1) `min(w,h)` squaring is incoherent once
  `w ≠ h` under rotation; (2) two *disagreeing* inferences of the fixed edge —
  scene-space `abs(pos_x − init_pos.x()) < 0.01` in the item vs rotated-local
  `pos_dx == 0` in the re-anchor — pinned the wrong corner → drift; (3) no
  `prepareGeometryChange()` on shrink → ghost.
- Fix: replace the step, don't patch it. `ResizeHandle._apply_resize` takes the fixed
  corner/edge **authoritatively from the handle position**; the item normalises the rect
  (`_constrain_resize_size` squares it so the handle tracks the cursor); everything goes
  through one primitive `resize_rect_item_keeping_anchor` (does
  `prepareGeometryChange()` + origin re-pin). The rotation-gated `_reanchor` band-aid was
  deleted.
- LESSON (verbatim from §11.4, the saga's headline): **don't post-correct an incoherent
  geometry step — fix the step.** A re-anchor layered over `min(w,h)` + dual fixed-corner
  inference can never be right; the senior review flagged this fragility before it shipped.
- Status: closed. Pinned by `tests/integration/test_rotation_aware_resize.py`
  ({Circle,Rect,Ellipse} × {0°,45°,215°} × {corner,edge}). Sizing precedence now has one
  home: `core/plant_sizing.py` (pinned by `tests/unit/test_plant_sizing.py`). See ADR-028.

---

## 2. The panel-rebuild saga (#200 → #206/#222 → #223 → #225)

Source: §11.4 ("Properties panel updates incrementally" + its wiring follow-up),
CLAUDE.md issue table.

- Symptom (#200): the properties-panel Name field lost focus after **every keystroke**.
- Root cause: each keystroke's command emitted `can_undo/redo_changed`, which
  deferred-rebuilt the *entire* form (`_clear_form` → recreate), destroying the focused
  editor. First fix (#205) was a focus *guard* — skip the rebuild while a panel editor
  holds focus. Workaround, not a fix: it accreted whitelisted widget types and traded a
  stale view under focus.
- Real fix (#222): `set_selected_items` computes a structural **identity**
  (`_compute_identity`: item id + class + `object_type` + bed `child_item_ids` / plant
  `parent_bed_id` + `_relationship_summary_key`) and rebuilds ONLY on a genuine
  selection/structure change; an unchanged selection pushes fresh values into live
  widgets via registered **refreshers** (skip-if-focused, write under `blockSignals`).
  A naive "skip rebuild on same selection" was **rejected** — it would leave
  Position/Size/colour stale after a canvas drag/undo/redo.
- Senior-review P1s that shaped it: (a) read-only Parent-Bed/Contained-Plants summary
  rows render a *related* item's name → the rendered text is folded into the identity so
  a related-item rename forces a rebuild; (b) the **Layer** combo's item *list* is backed
  by mutable external state (`scene.layers`) — a re-index-only refresher left a renamed
  layer stale; its refresher now repopulates the list. Enum-backed combos keep the cheap
  re-index.
- Wiring follow-up (#223): `application.py` still fanned out three signals
  (`command_executed` + `can_undo_changed` + `can_redo_changed`) per panel — collapsed to
  one `cmd_mgr.stack_changed.connect(...)` each. **A senior-review P1 was REFUTED here**:
  the claim "moving off `can_undo/redo_changed` loses undo/redo refresh coverage" was
  disproved by reading `commands.py` — those signals fire *unconditionally* on every
  undo/redo, not only when the boolean flips, so the swap was behaviour-preserving.
  The genuinely new fix: the plant-database panel had never been wired to any command
  signal, so undo/redo of a species assignment left it stale until reselection.
- #225 closed the stragglers: companion + crop-rotation panels (selectionChanged-only)
  now hang off `stack_changed`; the calendar gained a debounced `schedule_refresh()`
  that skips work while hidden.
- Status: closed for the panels; the underlying "rebuild the world off the repaint/command
  firehose" smell is **still open** (see Open section). Pinned by
  `tests/integration/test_properties_panel_incremental.py`,
  `tests/integration/test_panel_refresh_wiring.py`,
  `tests/ui/test_properties_panel.py::TestFocusPreservation`. The old focus guard is
  kept as a *defensive backstop* — do not delete it, and do not treat it as load-bearing.

---

## 3. Undo/redo data loss — the two-chokepoint invariant (#209/#211)

Source: §11.4 ("Undo/redo must dirty the document…").

- Symptom: draw → save → Ctrl+Z → title shows no `*`; closing prompts nothing and
  **silently discards** the undo.
- Root cause: `mark_dirty` was wired to `command_executed`, which only `execute()`
  emitted — `undo()`/`redo()` didn't dirty.
- The trap that made it a two-part fix: `command_executed` was load-bearing for
  dirtiness at ~30 direct `cm._undo_stack.append(cmd)` + hand-emit sites (resize
  handles, vertex drags, live property edits). Moving `mark_dirty` to a new
  `stack_changed` signal *un-dirtied all of them*; the naive integration test stayed
  green because it only exercised the `execute()` path.
- Fix: `CommandManager.stack_changed` (emitted by execute/undo/redo, **not** `clear()` —
  new/load must stay clean) + a single `register_applied(command)` chokepoint that every
  former direct-append site now calls (append + redo-clear + full signal set, without
  re-executing).
- Invariant learned: **exactly two ways onto the undo stack** — `execute()` (runs the
  command) and `register_applied()` (already applied) — both emit the full signal set.
  Never hand-roll `_undo_stack.append` at a call site.
- Status: closed. Pinned by `tests/integration/test_undo_redo_dirty.py` (covers both an
  `execute()` path and a `register_applied` resize path).

---

## 4. Free-text commit granularity — debounce plus flush (#210/#214)

Source: §11.4 ("Free-text property fields commit on a debounce…").

- Symptom: typing an N-char name pushed N undo entries and (post-#209) N heavyweight
  `calendar_view.refresh()` calls.
- Rejected design: focus-out-only commit. Manual testing found why: the Edit→Undo
  QAction is disabled until `can_undo` and *shadows* the focused QLineEdit's own undo —
  with focus-out-only commit, mid-edit Ctrl+Z found an empty stack and was a silent
  no-op. The debounce (600 ms) exists so a command exists shortly after the user stops
  typing.
- Second-order trap (senior-review P1, round 2): a form rebuild (`set_selected_items`)
  destroys the field **and its child debounce timer** synchronously — an armed debounce
  at selection-change time meant the edit was live-applied to the model but never
  recorded as a command: silently lost from undo. Fix: `_pending_text_commits` +
  `_flush_pending_text_commits()` runs *before* any rebuild, while widgets are alive;
  commits are idempotent so flushing on every rebuild is safe.
- Status: closed. Pinned by `tests/integration/test_properties_text_edit_undo.py`
  (`test_debounce_commits_without_focus_out`,
  `test_pending_edit_flushed_when_selection_changes`). Any new free-text field MUST
  follow live-apply + debounce/focus-out commit + flush-queue registration.

---

## 5. Task dual-store convergence (#227 → #228)

Source: §11.4 ("Closed (#228)…", "Two surfaces that share a status store…"), ADR-029 +
addendum, CLAUDE.md C2/#230 rows.

- Original design (US-C2): "is this task done" lived in **two** stores — legacy
  `task_completions` (calendar dashboard) and new `task_states` (Tasks tab) — with a
  standing dual-write invariant: every new write path must touch both or the surfaces
  silently diverge. That invariant is **retired**: #228 made `set_task_completion`
  delegate to `set_task_status` (single source of truth) and pointed the calendar at
  `effective_status`. `task_completions` is now a **write-only serialized mirror** kept
  only for `.ogp` back-compat. If you see the mirror and think "dead code, delete it" —
  don't: older binaries still read it.
- The sync bug that preceded it (PR #227 post-merge fix): both surfaces keyed tasks by
  `"{species_key}:{task_type}:{year}"` but derived `species_key` *differently* (canonical
  lowercased `species_key()` helper vs raw `scientific_name`). For any DB-sourced species
  the ids diverged → done/snooze sync failed in **both** directions. The round-2 PR test
  masked it by hand-matching ids. Fix: both the key (`species_key()`) and the *format*
  (`make_calendar_task_id()` in `services/task_generator.py`) are one shared function.
- Convergence senior-review P1 (round 1): the rewrite dropped the frost row's
  `frost_items:<ids>` highlight key (the unified engine stores ids in `Task.item_ids`) —
  `_adapt_task` re-encodes it.
- Kin bug (US-C1, PR #235 manual test): the shared `_on_highlight_species` handler
  consumed a canonical `species_key` but compared it against raw-cased names — never
  matched for DB species; and bed/species-less targets (`target:<uuid>` grouping keys)
  navigated nowhere and leaked the raw key into user-facing name columns.
- Status: closed. Pinned by `tests/integration/test_tasks.py::TestCrossSurfaceSync`,
  `tests/integration/test_calendar_task_convergence.py`,
  `tests/integration/test_frost_alerts.py` (TestFrostDashboardNavigation),
  `tests/integration/test_harvest.py::TestHarvestNavigation`.

---

## 6. Find Plants selection flakiness — two rounds (#212/#215)

Source: §11.4 (the #212 entry + its manual-test-round-2 follow-up).

- Round 1 symptom: clicking a plant in the Find Plants list selected it "only sometimes".
  Two compounding causes: (1) rows cached live `QGraphicsItem` refs — stale after
  undo/redo/delete/reparent, `setSelected` silently no-ops on a detached item; (2)
  `scene.changed` (fires on every repaint, including the repaint *caused by selecting*)
  was wired straight to a destructive full list rebuild, which could destroy the row
  mid-click. Fix: store `item_id` only, resolve at click time, defer the scene mutation
  with `QTimer.singleShot(0, …)`, debounce the refresh (~150 ms).
- Round 2 symptom (manual test): "list jumps back to the top a moment after I stop
  scrolling"; "single-click sometimes needs a second/third click". **The debounce was
  not enough** — it coalesces a burst but still fires once the burst settles, and
  selecting a plant triggers its own burst (selection → overlap/companion visuals →
  repaint → more `scene.changed`), so every selection still ended in a destructive
  rebuild.
- Fix: `_update_results_display` computes a **signature** of the visible rows and
  early-returns when unchanged; real rebuilds capture+restore scroll and re-select by
  `item_id`. Row widgets set `WA_TransparentForMouseEvents`.
- Lesson (verbatim spirit of §11.4): a debounce limits *how often* you rebuild, not
  *whether you needed to* — a list driven by the repaint firehose must be idempotent
  (diff before rebuild). The signature guard is explicitly a **band-aid**; the firehose
  smell is the same one as #206 (see Open section).
- Status: closed (workaround-grade). Pinned by
  `tests/integration/test_find_plants_selection.py`
  (`test_row_survives_interleaved_refresh_and_first_click_selects` names the signature
  guard in its docstring).

---

## 7. Smart-symbol exception-family enumeration — the losing game (PR #236)

Source: §11.4 (first entry), CLAUDE.md C4 row. Found over **three** senior-review rounds.

- Contract: a bad user-dropped JSON in `<app-data>/smart_symbols/` must never crash the app.
- The losing game: first enforced with `except (OSError, JSONDecodeError, ValueError)`.
  Broke three times, each a different family escaping the enumeration:
  (1) dry-run `generate()` raised `ArithmeticError`/`TypeError` (divide-by-zero,
  `9**9**9`, `round(x, float)`) — none subclass `ValueError`;
  (2) `"+".join(["1"]*5000)` raised `RecursionError` **during `ast.parse`**;
  (3) a non-dict `parameters` entry raised `AttributeError` in `from_dict`'s
  *structural* phase — before the dry-run, bypassing `generate()`'s wrapper entirely.
  Each "fix" added the family that bit it, then re-declared victory.
- Final rule (structural, not enumerative): the **user-file load loop catches
  `Exception`** (log-and-skip) so any `from_dict` failure on untrusted input is non-fatal
  *by construction*; the **bundled** load loop stays narrow so first-party packaging bugs
  crash loud. `BaseException` still propagates. Defense in depth: `generate()` wraps its
  body → `SmartSymbolError`; the evaluator caps AST node count (`_MAX_NODES`).
- If you see the broad catch in `smart_symbol_library.py` and want to "tighten" it: this
  entry is why you must not.
- Status: closed. Pinned by `tests/unit/test_smart_symbol_library.py`
  (arithmetic/recursion/structural/non-object poison skipped; malformed *bundled* file
  still crashes loud).

---

## 8. Release-workflow races (chore race; #229 date matching)

Source: §11.4 ("Release workflow race condition with chore commits"),
`.claude/skills/finalize-us/skill.md` steps 8–9, commits `dfddf28` and `745c4bb`.

- Race 1: post-merge chore commits (version sync + roadmap) land ~37 s after the PR
  merge, but the release build takes ~2m50s. The chore commits' Release runs started
  before the new tag existed, computed a stale version, and failed with "release with
  the same tag name already exists". Fix: `if: "!startsWith(github.event.head_commit.message, 'chore:')"`
  on the release job. Later hardened (commit `745c4bb`) to also skip **scoped**
  `chore(...)` commits, not just bare `chore:`.
- Race 2 (#229, fixed in the `finalize-us` skill itself, commit `dfddf28`): the
  end-of-story automation waited for the CI release by grepping `createdAt` against
  `$(date ...)`. Two failure modes: local-vs-UTC mismatch, and same-day re-runs — plus a
  date match **cannot detect failure**. Fix: capture the top release tag *before* the
  merge, then poll until the top tag *differs* (tag-transition, timezone-independent,
  ~10 min ceiling), and stop-and-report if no new tag appears. PR checks are gated with
  `gh pr checks --watch --fail-fast`.
- Status: closed. No pinning test (workflow-level); re-verify against
  `.github/workflows/release.yml` and finalize-us step 9 before changing either.

---

## 9. Data loss on update — the installer wiped user plans (#199/#204, ADR-027)

Source: §11.4 ("Never default a file dialog into the install directory…"), ADR-027,
CLAUDE.md issue table.

- Symptom: "all my gardens vanished after updating."
- Two independent bugs that combined: (1) file dialogs called with `""` as directory open
  in the process CWD — for a packaged build that is
  `C:\Program Files (x86)\Open Garden Planner`, so users saved `.ogp` plans into the
  install dir; (2) the NSIS upgrade path silently runs the *old* uninstaller, which did
  `RMDir /r "$INSTDIR"` — every update deleted the install dir, plans included.
- Fix, both halves required: app side — `app/paths.py` chokepoint routes every
  save/open/export dialog to the open project's folder or
  `<Documents>/Open Garden Planner`, never CWD; installer side — the uninstall section
  rescues top-level `$INSTDIR\*.ogp` to `Documents\Open Garden Planner\Recovered Plans`
  before `RMDir /r` (`/SD IDOK` keeps silent upgrades from hanging).
- Known limitation: the fix is **forward-protective only** — the pre-fix→fixed upgrade
  still runs the old (destructive) uninstaller.
- Status: closed. Pinned by `tests/unit/test_paths.py` and
  `tests/integration/test_save_location.py`; the NSIS half is Windows-only, verified
  manually.

---

## 10. i18n incidents — hardcoded strings and mojibake

Source: §11.4 (two entries) + CLAUDE.md Translation section.

- **Hardcoded-English class** (the gate's mechanics/blind-spot are owned by
  `ogp-diagnostics-and-tooling` §1.2/1.3 — in one line: the gate only checks
  strings *already extracted into the .ts file*, so plain-string call sites are
  invisible). Concrete historical failures: module-level
  `_SEGMENT_LABELS = {"early_spring": "Early Spring",…}` looked up raw in three
  places despite being registered in `fill_translations.py`; f-strings like
  `f"{a} overlaps {b}"` look like sentences but never reach Qt Linguist.
  Fix pattern: `QT_TR_NOOP` dicts + translate at lookup, or
  `self.tr("…").format(...)`; grow `TestNoHardcodedEnglish`'s suspicious-phrase
  list whenever a string slips through manual testing. Related:
  `ChangePropertyCommand` `{property}` fragments must be manually registered under the
  `"Commands"` context (an unregistered fragment silently degrades to English).
- **PowerShell mojibake**: PowerShell 5.1 `Get-Content -Raw` mis-guesses UTF-8-no-BOM as
  Latin-1; `Set-Content -Encoding UTF8` then double-encodes every umlaut (`ö` → `Ã¶`).
  Trigger was an in-place `Anbauerfolge` → `Anbaufolge` replace in
  `fill_translations.py` + the `.ts` file. Recovery: `git checkout` the files, redo with
  Python. Fast detection: `grep -c "Ã¶\|Ã¤\|Ã¼\|ÃŸ" <file>` — non-zero = regressed.
- **Excel BOM**: bare `utf-8` CSVs mojibake German umlauts in Excel — use `utf-8-sig`.
- Status: closed individually; the hardcoded-string class recurs — treat every new
  user-visible string as suspect.

---

## 11. CI-only teardown crashes (#230, PR #235)

Source: §11.4 (two adjacent entries).

- **#230**: `scene.changed` slots that `start()` a debounce timer (soil-mismatch /
  companion / spacing) fired **during teardown** — the scene emits `changed` while being
  cleared, after the child `QTimer`'s C++ object is deleted. `RuntimeError` inside a Qt
  slot escalates to `Fatal Python error: Aborted` — the *next* test errors and the run
  aborts mid-suite. Timing-dependent: passed locally, reliably crashed CI Linux. Fix:
  wrap the `.start()` in `contextlib.suppress(RuntimeError)`; **never** connect
  `scene.changed` to a bare `lambda: self._timer.start()` (a lambda can't be made
  teardown-safe). Command/status-signal timers (`stack_changed` etc.) don't need it.
- **PR #235**: `GlobalSearchField` connects to the process-global
  `QApplication.focusChanged`. Two faults: Qt already auto-disconnects destroyed
  receivers, so the explicit `destroyed`-lambda disconnect raced to `TypeError`; and a
  stray `focusChanged` could still invoke the slot on a dead widget. pytest-qt fails the
  *current* test for any exception in a slot — so one test's torn-down window failed an
  unrelated later full-app test ("passes alone, fails in the full run",
  `test_harvest.py::TestHarvestNavigation`). Fix: `suppress(TypeError, RuntimeError)` on
  the disconnect + `try/except RuntimeError: return` in the slot body.
- Rule: any handler bound to `scene.changed` or an app-global signal must assume it can
  fire after its owner is destroyed.
- Status: closed (contract-style; enforced by convention, no dedicated test).

---

## 12. Agent API render tool (D1.3, PR #242) — layers fix + two empirical mcp facts

Source: CLAUDE.md D1.3 row, docs §8.19, ADR-034 addendum.

- **Manual-test fix**: `render_canvas_image`'s `layers` parameter was originally
  *subtractive-only* — it could hide layers but never show one the user had toggled off
  in the live Layers panel, so an agent explicitly requesting a hidden layer got nothing.
  Fix: `_hidden_layers_not_in` snapshots every layer-bearing item's original visibility,
  **forces the full requested set**, and restores the exact original state afterwards —
  no lasting UI side effect.
- **Two facts empirically verified against mcp 1.28.1 — do not "clean these up":**
  (1) `Image` is not pydantic-representable, so the tool needs
  `@mcp.tool(structured_output=False)` — a naive `list[Image | RenderMeta]` annotation
  crashes `build_server()`; and `Image` must be a genuine **top-level import** in
  `server.py`, because `inspect.signature(func, eval_str=True)` resolves stringified
  annotations via the tool's own `__globals__` (a function-local import breaks it).
  (2) `render_scene_region`'s `y_flip=True` inverts the rendered pixel Y-axis relative
  to D1.2's scene frame — the correction formula is documented on
  `RenderMeta.px_per_cm`.
- Status: closed. Pinned by `tests/unit/test_agent_api_render_coordinate_frame.py`
  (coordinate frame) and `tests/integration/test_agent_api_render.py`. Facts dated:
  verified against mcp 1.28.1, 2026-06/07 — re-verify on any mcp version bump.

---

## 13. Retired feature: US-B7 Paper Space (dropped in PR #191 review)

Source: `docs/roadmap.md` (~line 2277, "US-B7 dropped during manual-test review"),
CLAUDE.md Package B note.

- US-B7 added a "Layout" tab (Ctrl+4) with one page / viewport / title block / scale
  bar. Manual testing showed the abstraction added **no user-visible value** over what
  `pdf_report_service` already does (multi-page PDF at A4/A3/Letter/Legal, fit-to-page,
  built-in scale bar). Everything was removed from PR #191 before merge.
- Durable residue you may trip over: `FILE_VERSION` stayed at **1.4** (the bezier + arc
  item types from the same phase are real); the loader **silently ignores** a
  `paper_layouts` key found in `.ogp` files saved by short-lived draft builds. If you
  see that ignore branch, it is intentional — don't "implement" it and don't warn on it.
- Status: retired. Do not re-propose a second-space CAD print workflow without new
  evidence the PDF pipeline is insufficient.

---

## 14. The export Y-flip saga (PNG/PDF/SVG, 2026-05)

Source: debug-verbose case studies (2026-05-01/02) + §11.4 export entries. Four
sequential incidents from the CAD-style `scale(zoom, -zoom)` canvas (ADR-002):

1. **Empty PNG**: `QRectF(0, H, W, -H)` as render target — negative-height rects are
   `isEmpty()` in PyQt6, so `scene.render()` painted zero pixels. Fix: painter pre-flip
   (`translate(0, H_px); scale(1, -1)`), H in **image pixels**, not cm.
2. **PDF narrow strip**: QPdfWriter's painter starts with a **non-identity** transform
   (margin handling), so the mathematically-correct pre-flip overshot. Fix: render to a
   temp `QImage` then `drawImage` — never assume identity on non-QImage devices. Also:
   `QPdfWriter` needs `setResolution(72)` before `setPageLayout()`.
3. **SVG upside-down textures**: `QSvgGenerator` stores pattern tiles un-flipped; under
   the Y-flip they render inverted (brownish mush). Fix: post-process `patternTransform`.
4. **SVG texture bleed**: `QSvgGenerator` never serializes painter clip paths — texture
   rects (the *clip bounding rect*, not the shape) washed across the whole canvas. PNG
   unaffected (native renderer applies the clip). Fix: post-process paired
   shadow-group→clipPath wrapping, lockstep with a `used` set (a forward-window scan
   corrupted the XML). Evidence tool: decode base64 tiles + count `<clipPath>` elements
   (`0` was the smoking gun). **Validate SVG in a real browser** — `QSvgRenderer` is too
   forgiving and hides this class of bug (`scripts/svg_preview.py`).
- Meta-lesson: Qt's SVG/PDF generators are NOT faithful serializers of painter state;
  anything beyond shape+fill+stroke must be recovered in post-processing.
- Status: closed. Related tests: `tests/unit/test_export.py`,
  `tests/unit/test_scene_rendering.py`.

---

## 15. Tangent-constraint degeneracy (PR #198, ADR-024, fixed 2026-06-07)

Source: debug-verbose case study "tangent constraint flips…", ADR-024.

- Symptom evolution across four fix attempts: v1 line stalls radial ("stable but
  wrong") → v2 (signed residual) flips to the opposite side on a large drag → v3
  (continuity warm-start) tangency drifts off → v4 (drop POINT_ON_CIRCLE) tangent holds
  but the contact slides along the line. Each fix traded one face of the same bug.
- Wrong theories, all disproved by instrumentation: inverted sign (the `[TANGENT]` emit
  log showed sign correct at creation); creation-time solve flipping it (no-op at the
  snapped point); coordinate-space mismatch (both scene coords).
- Evidence: per-frame `[TANGENT]` log showed `signed_dist` sliding `+320 → 0 → −320` —
  a clean trajectory *through the centre*, not a one-shot sign error. Reproduced headless
  only after matching the user's exact drag magnitude+direction from the log.
- Root cause: tangency expressed as "perpendicular distance centre→line = ±radius" has a
  gradient (line-normal) **parallel** to POINT_ON_CIRCLE's radial gradient at the tangent
  configuration → rank-deficient Jacobian → drift/stall/flip. v1–v3 were all faces of
  this one ill-conditioning.
- Fix: re-express `TANGENT` as "edge ⟂ radius at the contact" (residual
  `(C−v1)·(v0−v1)/|edge|`), whose gradient is *orthogonal* to the radial one — emit it
  WITH POINT_ON_CIRCLE for a full-rank pair; keep the continuity warm-start (the contact
  still has two antipodal solutions).
- Lessons: residual *formulation* decides conditioning, not the geometry you mean; two
  constraints with parallel gradients at the solution are rank-deficient no matter the
  warm-start; multi-solution constraints need continuous warm-starting; when a GUI bug
  won't reproduce headless, extract the exact user coordinates from instrumentation and
  drive the exact live code path.
- Status: closed. Pinned by `tests/unit/test_constraint_tangent_math.py`. Related §11.4
  entry: live-drag projection tolerance must be sub-pixel (`tolerance=1e-4` in
  `project_to_feasible` — cm-scale tolerance let the vertex slip with the cursor).

---

## 16. Inert curve handles — the `ItemIgnoresTransformations` grab drop (#193)

Source: debug-verbose case study (2026-06-08), §11.4 entry, ADR-025.

- Symptom: new `CurveControlHandle`s render but nothing can be dragged; all direct-hook
  tests green.
- Wrong theories: reshape math wrong (hooks pass every test); handle's own
  `mousePressEvent` broken (mirrors `VertexHandle` exactly); draw tool eating clicks.
- Evidence: a hand-built `QMouseEvent` was **not delivered** to the
  `ItemIgnoresTransformations` child even though `itemAt` found it; switching to
  `QTest.mousePress` on `view.viewport()` exposed `view._active_drag_handle is None`
  after the press.
- Root cause: PyQt6 silently drops the mouse grab on `ItemIgnoresTransformations` child
  items between events. `CanvasView` re-establishes the grab — but only for an
  `isinstance` **allow-list** of handle types, and the new handle wasn't in it.
- Fix: one line (add to the tuple). Standing trap: **every new drag handle that sets
  `ItemIgnoresTransformations` MUST be added to the allow-list in
  `CanvasView.mousePressEvent`** (grep `_active_drag_handle`) — a faithful copy of an
  existing handle is still dead until the view knows its type. Testing note: use
  `QTest.mousePress/Move/Release` on `view.viewport()` (after `centerOn`) — synthetic
  events never reach these children.
- Status: closed; the opt-in registration trap remains live for future handles. Pinned
  by `tests/integration/test_curve_vertex_edit.py::TestHandleDragViaView` (fails without
  the fix).

---

## 17. Label editor auto-closing — the minimap culprit (fixed 2026-04-22)

Source: debug-verbose case study (the skill's founding story).

- Symptom: double-click opened the inline label editor for ~110 ms, then it closed
  itself.
- Wrong theories: double-click Release-2 stealing focus; a stale start-time guard;
  `super().focusOutEvent()` clearing the cursor.
- Evidence: `traceback.format_stack()` inside `focusOutEvent` printed
  `minimap_widget.py:205 — item.setVisible(False)` — the minimap's
  `_hide_overlay_items()` hides all `ItemIgnoresTransformations` items (including the
  focused editor) before rendering its thumbnail.
- Fix: skip the scene's current focus item in `_hide_overlay_items()`.
- Lesson (and why `debug-verbose` mandates stack traces at unexpected call sites): the
  external caller is unfindable by reading the widget's own code.
- Status: closed. Sibling case study: `CalloutItem` re-editing immediately committed
  because the parent held `ItemIsFocusable` and `_text_child.setFocus()` synchronously
  fired the parent's `focusOutEvent` → fix was to never let the parent hold scene focus.

---

## 18. QSettings global-static poison — "passes alone, fails together, CI green"

Source: §11.4 ("`QSettings.setDefaultFormat()` / `setPath()` are process-global…").

- Symptom: 6 settings-persistence tests fail only in the full local run, pass in
  isolation, and CI stays green. Uniform tell: every failing getter returned exactly the
  coded *default* — the setter write never persisted.
- Root cause: a fixture in `tests/unit/test_ui_state.py` called
  `QSettings.setDefaultFormat(IniFormat)` + `setPath(...)` — **static, process-wide,
  never auto-reverted** — pointing at a `tmp_path` pytest later deleted; every
  `QSettings` constructed after it wrote to a dead path.
- Fix: monkeypatch the `QSettings` *symbol* in `ui_state` (auto-reverts) — never the
  globals. Backstops in `tests/conftest.py`: session fixture restores
  `defaultFormat()` at teardown; function-scoped autouse fixture clears the test store +
  nulls the settings singleton.
- Lesson: "passes alone, fails together, actual value = default" is almost always shared
  global/singleton state; green CI does not prove the local full suite is clean
  (different collection order dodges the poison).
- Status: closed (with tripwires; a `setPath`-only leak is NOT covered).

---

## 19. The stale-trigger family (#173/#175)

Source: §11.4 + debug-verbose case study (2026-05-07).

- Symptom: soil-mismatch bed border stayed stale on plant move/reparent but updated on
  any *unrelated* edit — recompute logic proven correct.
- Wrong theories: recompute bug; `_child_item_ids` not updated; debounce timer broken.
- Root cause: `QGraphicsScene.changed` fires only on **visual** change; mutating
  `parent_bed_id`/`_child_item_ids` is a plain Python attribute write — no signal, no
  debounce restart.
- Fix + durable pattern: put the refresh trigger *inside the command*
  (`SetParentBedCommand` calls `trigger_soil_mismatch_refresh` and `ensure_z_above_parent`
  on execute AND undo), never at every caller. Bonus rule from the fix: any "do X also at
  site Y" fix means grep for *every* call site of the same operation — there are almost
  always 3–5 more.
- Status: closed. Related: `tests/unit/test_plant_bed_relationship.py`,
  `tests/unit/test_plant_bed_zorder.py`.

---

## 20. The ghost-field family (US-12.10d, fixed 2026-05-03)

Source: two debug-verbose case studies.

- Incident A: soil-mismatch warnings never fired despite 14 passing integration tests.
  Evidence: a diff of `dataclasses.fields(PlantSpeciesData)` vs `to_dict()` keys — three
  new fields (`n_demand`/`p_demand`/`k_demand`) missing from **both** serialization
  sites, silently dropped on the canvas→metadata→canvas path. The integration tests
  constructed instances directly and never round-tripped. **Construct-and-test is not
  serialize-and-test.**
- Incident B: even after fixing serialization, plants still had `None` everywhere — the
  panel had **no UI rows** for the new fields, so nothing could ever set them. A "ghost
  field" with no UI is worse than no field: the data layer looks complete while the
  feature is unusable.
- Fixes pinned by `tests/unit/test_plant_data_serialization.py` (iterates
  `dataclasses.fields()`, asserts presence + full round-trip equality).
- Status: closed; the *pattern* recurs — when adding a dataclass field, update
  `to_dict`/`from_dict` AND audit the forms that read/write the model.

---

## 21. UNKNOWN-enum display corruption (#231/#232)

Source: §11.4 entry.

- Symptom: a tree's lifecycle read "Annual"; touching the form then **rewrote**
  `UNKNOWN` → that wrong concrete value (silent data corruption). Bundled DB masked it
  (full trait data); sparse online-search results exposed it.
- Root cause: combos skipped the `UNKNOWN` member and fell back to
  `setCurrentIndex(0)`; save reads `currentData()` back.
- Sibling defect, same issue: `setSpecialValueText("")` — Qt treats an **empty** special
  string as *disabling* the feature, so the `0` sentinel rendered as "0 cm" instead of
  blank. A **non-empty** `setSpecialValueText(self.tr("—"))` engages it.
- Fix: neutral `("—", UNKNOWN)` entry at index 0 in every enum combo; non-empty dash on
  all 8 spin-boxes; display-only (populate/save round-trip unchanged).
- Status: closed. Pinned by `tests/ui/test_plant_database_panel.py`
  (`TestMissingDimensionsShowDash`, `test_sparse_species_saves_back_as_none`).

---

## 22–24. Short entries

**22 — Same-z stacking flips after save/load** (US-12.10/F2.7, debug-verbose case
study): plant on a bed rendered correctly live, hidden behind the bed after reload. Both
had `zValue() == 0`; Qt tie-breaks equal z by **insertion order**, which differs between
live mutation order and JSON-load order. Fix: explicit `parent.zValue() + 1` pass in
`_update_items_z_order`. Never rely on insertion order across a persistence boundary.
Pinned by `tests/unit/test_plant_bed_zorder.py`. Closed.

**23 — Bed-menu wiring regressed twice** (#173, US-12.8): four independently-implemented
bed shape classes meant every new bed-only context action had to be hand-added to each;
pest log missed Polygon/Ellipse, succession missed three of four. Fix: central
`build_bed_context_menu` + `dispatch_bed_action` (ADR-017, §8.14) gated by the
parametrised `tests/integration/test_bed_context_menu.py` — adding a bed feature means
adding one assert line per shape there. Closed; read §8.14 + ADR-017 BEFORE adding any
bed feature (CLAUDE.md says the same).

**24 — `max()` is left-biased on ties** (US-12.10/F2.10a, debug-verbose case study):
`SoilTestHistory.latest = max(records, key=r.date)` returned the *first* same-day
record, hiding a newer Lab record behind an older Kit record. When a sort key has limited
resolution (date, not datetime), assume ties and design the tie-break explicitly.
Pinned by `tests/unit/test_soil_test_history_latest.py`. Closed.

Other settled one-liners worth knowing exist (all in §11.4, all closed): QLineEdit
Return bubbling to the canvas finalizing the polyline (US-A4); the Dynamic Input overlay
chasing the cursor away from the mouse (US-A4); grid snap silently overriding anchor
snap (pinned by
`tests/integration/test_anchor_snap.py::test_grid_snap_does_not_override_anchor_snap`);
the status-bar startup reminder invisible behind the modal Welcome dialog → persistent
`TaskReminderBar` + deferred `singleShot(0)` (pinned by
`tests/integration/test_tasks.py::TestOverdueReminderBar`); shopping-list price ids must
encode the display unit (g vs kg) or a price silently multiplies 1000×; trellis gallery
thumbnails fell through to the round fallback because a SOLID fill has no texture
(PR #236 manual-test fix, CLAUDE.md C3 row).

---

## Still open / unsettled (as of 2026-07-03)

- **#206 rebuild-on-repaint firehose smell.** The properties panel is fixed
  (identity + refreshers) and the Find-Plants list has a signature guard, but §11.4
  explicitly calls the guard "a local band-aid, not a structural fix — the firehose
  still re-queries the whole scene every tick". Any list/panel newly wired to
  `scene.changed` will re-fight saga #6 unless it is idempotent from day one.
- **TD-007 — EDGE_* anchor instability** (§11.3 + §11.4): edge anchors on
  polygons/polylines are classified by *current* dominant axis; dragging a vertex far
  enough flips the classification and constraint indicators jump. Workaround in place
  (index-only match block in `_resolve_anchor_position`). Real fix (single
  `EDGE_MIDPOINT` type + stable `anchor_index`) not done. Priority: Medium.
- **TD-008 — numerical Jacobian** (§11.3): Newton refinement uses a central-difference
  Jacobian. **Deliberately not fixed** — microseconds for ≤20-variable systems, no
  user-facing impact. Do not "optimize" this without evidence of a large-scene
  bottleneck.
- **No token auth on the loopback Agent API** (ADR-033, §8.10/§8.19): the embedded MCP
  server is on-by-default, read-only, 127.0.0.1-only, **no auth**. Token auth is stated
  as a *hard prerequisite* before any D2 write tool ships — a default-on unauthenticated
  mutate surface reachable by any local process is explicitly unacceptable. If you are
  implementing D2, auth comes first.
- **Smart Symbols UI deferred** (CLAUDE.md C4 row): the sidebar panel ships hidden
  (`set_panel_visible("smart_symbols", False)` in `application.py`); engine,
  persistence, DXF export, and properties editing are live and tested. The hidden panel
  is intentional, not dead code.
- **§11.1/§11.2 tables** list open questions/risks (Trefle rate limits, texture
  licensing, Qt3D-vs-PyVista for Phase 14 3D, installer signing/SmartScreen, PyInstaller
  bundle size). *Inference, unverified:* several §11.3 rows (TD-001/TD-002 "Phase 6
  addresses") read as stale — phases 1–13 are complete; verify against the code before
  acting on them.
- **#199 residual exposure**: the installer fix is forward-protective only; a user
  upgrading from a pre-fix build still runs the old destructive uninstaller once (the
  rescue only exists in the *new* uninstaller going forward).
- **#193 opt-in trap**: still structurally live — every future
  `ItemIgnoresTransformations` handle must be registered in `CanvasView`'s allow-list.

---

## When NOT to use this skill

- **Triaging a live bug right now** → `ogp-debugging-playbook` (and the project skill
  `debug-verbose` for instrumentation method). Come back here only to check whether the
  bug rhymes with a settled saga.
- **Looking up an invariant as a forward-looking contract** (what you must preserve when
  writing new code) → `ogp-architecture-contract`. This skill records how those
  invariants were *learned*; the contract skill states them normatively.
- **Release/merge mechanics** → `ogp-change-control` / `finalize-us`. Saga #8 here only
  explains *why* those procedures look paranoid.
- **Qt/CAD API reference** (Y-flip math, snap pipeline, item patterns) →
  `ogp-qt-cad-reference` and `docs/08-crosscutting-concepts/` §8.9.
- Adding a brand-new subsystem with no history — nothing here binds you, though sagas
  6, 7, 11, and 16 describe traps that generalise to any new Qt code.

---

## Provenance and maintenance

Primary sources, in order of density: `docs/11-risks-and-technical-debt/README.md`
§11.4 (read PAST line 127 — the file is 167 lines and the truncation point hides
#199/#209/#206/#210/#227/#235 entries), `.claude/skills/debug-verbose/skill.md` case
studies, `CLAUDE.md` progress tables, `docs/roadmap.md` (US-B7 note ~line 2277),
`docs/09-architecture-decisions/README.md`, `git log --oneline`.

Re-verification one-liners (run from repo root):

```bash
# Pinning tests still exist / still pin what this skill claims:
grep -rln "test_apply_keeps_rotated_plant_centered\|test_rotation_pivots_about_rect_center_with_badge" tests/
ls tests/integration/test_rotation_aware_resize.py tests/integration/test_undo_redo_dirty.py \
   tests/integration/test_properties_panel_incremental.py tests/integration/test_properties_text_edit_undo.py \
   tests/integration/test_panel_refresh_wiring.py tests/integration/test_calendar_task_convergence.py \
   tests/integration/test_find_plants_selection.py tests/unit/test_smart_symbol_library.py \
   tests/integration/test_save_location.py tests/unit/test_paths.py tests/integration/test_bed_context_menu.py
grep -rn "TestCrossSurfaceSync\|TestOverdueReminderBar\|TestHandleDragViaView\|TestFrostDashboardNavigation" tests/ -l

# §11.4 keyword sweep (new entries land here first — re-mine after every merged fix):
grep -n "Closed (#\|Lesson\|pinned\|Pinned\|Regression test" docs/11-risks-and-technical-debt/README.md

# New sagas since this skill was written:
git log --oneline -30
grep -n "Case study" .claude/skills/debug-verbose/skill.md

# US-B7 retirement + paper_layouts ignore still documented:
grep -n "paper_layouts" docs/roadmap.md CLAUDE.md

# Release-race procedure unchanged:
grep -n "tag transition\|before_tag\|date matching" .claude/skills/finalize-us/skill.md
```

Maintenance rule (mirrors CLAUDE.md's continuous-documentation policy): after any fix
that survived a wrong theory, a rejected design, a multi-round review, or a manual-test
failure, add an entry here in the standard format AND a case study to `debug-verbose`
if instrumentation cracked it. Date-stamp anything volatile (versions, library
behaviour, "still open" claims).
