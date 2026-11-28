---
id: ADR-029
title: "Unified Task Model — Pure Generators, Render-Time Status, Dual-Store Coexistence"
status: "Accepted (Phase 13 — Package C, US-C2, issue #188)"
legacy_anchor: adr-029-unified-task-model--pure-generators-render-time-status-dual-store-coexistence
---

# ADR-029: Unified Task Model — Pure Generators, Render-Time Status, Dual-Store Coexistence

**Status**: Accepted (Phase 13 — Package C, US-C2, issue #188)

**Context**: The app already surfaced "what to do now" in several disconnected places — the planting-calendar dashboard's "today" view, succession sow/clear dates, soil-amendment recommendations, and frost alerts — but had no single, actionable to-do list, and no way for the user to add their own reminders. US-C2 asks for one unified **Tasks** tab that aggregates every auto-derived action *and* user-created manual tasks, grouped by urgency, with per-task done / snooze / dismiss state that persists. Three forces shaped the design: (1) the auto-derived sources are scattered across services that each compute their own dates; (2) there is no background scheduler in a desktop QGraphicsView app, so "is this overdue / still-snoozed / done-then-archived" has to be answered without a daemon; (3) the existing planting-calendar dashboard is working US-12.x code that already reads a legacy `task_completions` done-set from the project, and refactoring it onto any new model is pure regression risk for no new user value.

**Decision**:
1. **Tasks come from pure, Qt-free generators over a snapshot.** `services/task_generator.py` defines a frozen `Task` value object and a `PlanState` snapshot (location, beds, plant items, succession plans, soil service, manual tasks, frost alerts) assembled Qt-side by `tasks_view.build_plan_state`. Six pure generators, each `(PlanState) -> list[Task]`, cover planting-calendar windows, propagation steps, succession sow/clear, soil amendments, frost protection, and manual tasks; `generate_all` flat-maps them and dedups by `task_id`. Keeping generation Qt-free makes every rule unit-testable without a running app and means the same `PlanState` cannot produce different tasks on two surfaces.
2. **Status is computed at render time, not scheduled.** `services/task_status.py::effective_status` maps a stored raw state + "today" to one of `open / snoozed / done / dismissed / archived`. There is **no** background job: a snooze that has expired reads as `open` on the next render, and a task done more than 7 days ago reads as `archived` (the done-then-archive window). Status is therefore always consistent with the current date with zero scheduler infrastructure.
3. **Status lives in TWO stores kept in sync at both write chokepoints.** The Tasks tab reads the new per-task `task_states` store; the untouched planting-calendar dashboard still reads the legacy `task_completions` done-set. `set_task_status` **and** `set_task_completion` each write **both** stores, so the two surfaces can never disagree about what is done. This deliberate "parallel coexistence" was chosen over refactoring the calendar dashboard onto the new generators now — that refactor carries regression risk against working US-12.x code and delivers no extra user value in this story. A convergence follow-up (retire `task_completions`, point the calendar dashboard at `task_generator`) is planned and tracked separately.
4. **Build a new tab on the generators rather than refactor the calendar dashboard.** The new Tasks tab is greenfield over the pure generators; the calendar dashboard is left exactly as-is. Trade-off: two code paths read overlapping project state (mitigated because they read the *same* state, so they cannot diverge in data — only the legacy path covers less). The alternative — one converged model now — was rejected for this story on regression-risk grounds; see point 3's follow-up.
5. **Persistence is additive and backwards-compatible.** Two new top-level `.ogp` keys — `manual_tasks` and `task_states` — with **no `FILE_VERSION` bump**; older binaries ignore the keys and older files load with empty dicts. On load, legacy `task_completions` ids are folded into `task_states` as archived-done entries, so historical completions still suppress their tasks on the new tab. Manual-task Add/Edit/Delete are undoable commands.
6. **The tab is appended, not inserted, to avoid shortcut/badge regressions** (shortcut renumbered to Ctrl+4 by #310). The Tasks tab is added after Seed Inventory and its shortcut is resolved via `indexOf` (→ Ctrl+5) rather than a hard-coded index, so the existing Garden Plan / Planting Calendar / Seed Inventory shortcuts and the planting-calendar frost badge are untouched.
7. **Frost tasks reuse the calendar's single weather fetch.** Rather than issue a second forecast request, the frost generator consumes the alerts the planting calendar already fetches, delivered via `PlantingCalendarView.frost_alerts_ready` — one network round-trip feeds both surfaces.

**Alternatives considered**:
- *Refactor the planting-calendar dashboard onto the new generators immediately (single converged model).* The clean end-state, but it rewrites working US-12.x code for no new user-visible behaviour in this story. Deferred to a convergence follow-up; dual-store sync keeps the surfaces consistent in the meantime.
- *Single status store (`task_states` only), update the calendar dashboard to read it.* Same regression-risk objection as above, and would require touching the dashboard's done-set reads. The dual-write keeps `task_completions` authoritative for the legacy reader with one extra write line per chokepoint.
- *A background scheduler / timer that flips snoozed→open and done→archived.* Unnecessary complexity for a desktop app; render-time `effective_status(today)` gives the same result deterministically and is trivially testable.
- *Bump `FILE_VERSION` for the new keys.* Rejected — the keys are purely additive and older binaries can ignore them safely; a version bump would needlessly lock older binaries out of new files.
- *Insert the Tasks tab at a fixed index.* Rejected — would shift the established Ctrl+1/2/3 shortcuts and risk the frost-badge wiring; appending + `indexOf` is regression-free.

**Consequences**: Adds `services/task_generator.py`, `services/task_status.py`, `models/task.py` (`ManualTask`), `ui/views/tasks_view.py`, `ui/dialogs/task_dialog.py`, and `Add/Edit/DeleteManualTaskCommand`. Two additive `.ogp` keys, no format bump. The two done-state surfaces stay in lockstep at the cost of a documented dual-write and a planned convergence follow-up. Generators are pure → fast unit tests; status is render-time → no daemon. Tests: pure-generator + `effective_status` unit tests and an end-to-end Tasks-tab integration test (create/snooze/done a manual task, legacy-fold on load, navigate-to-bed). See FR-TASK (FR-TASK-01…09) and §12 glossary entries (Manual task, Task state, Task generator, Effective status).

**Addendum (PR #227)**: dual-store sync (point 3) is necessary but **not sufficient** — the two surfaces must also derive the `task_id` *identically*, or a status written by one is stored under a key the other never looks up. The calendar dashboard and the Tasks-tab generator both key calendar tasks by `"{species_key}:{task_type}:{year}"`, but `tasks_view.build_plan_state` originally computed `species_key` differently from the calendar (raw `scientific_name`, vs the canonical `species_key()` helper from `models/plant_data.py` — `source_id`-first, lowercased, ADR-016), so for any DB-sourced species the ids diverged and sync silently failed in both directions despite the dual-write. Fix (two parts): `build_plan_state` reuses the canonical `species_key()` helper, **and** the calendar `task_id` *format* (`"{species_key}:{task_type}:{year}"`, previously copy-pasted in both the generator and the calendar dashboard) is now built through a single shared `make_calendar_task_id()` in `services/task_generator.py`, used by both surfaces. **Invariant, now code-enforced rather than comment-enforced: the `task_id` derivation — both the key and the format — must go through one shared function across every surface that reads/writes the shared status store.** A new surface or generator must call `make_calendar_task_id()` (calendar/propagation tasks) and the canonical `species_key()`; the still-deferred convergence (retire `task_completions`, point the calendar dashboard fully at `task_generator`) is tracked separately. See §11.4 and `tests/integration/test_tasks.py::TestCrossSurfaceSync`.

**Addendum (PR for #228 — convergence delivered)**: the deferred convergence promised in point 3/4 and both prior addenda is now done — the "parallel coexistence" is retired in favour of a single generation engine and a single status **write-path**, while presentation stays surface-specific:
- **One generator engine feeds both surfaces.** `build_plan_state` + `_bed_amendment_recs` moved from `tasks_view.py` into `services/task_generator.py` (still Qt-free — duck-typed scene access, no widget imports), and the planting-calendar dashboard now builds its "Today's Tasks" rows from `generate_all(build_plan_state(...))` instead of four bespoke `_DashboardTask` paths (`_generate_dashboard_tasks` / `_inject_frost_tasks` / `_inject_soil_mismatch_tasks` / `_collect_succession_tasks`, all deleted). The calendar passes its computed `prop_plans` (a new `build_plan_state` parameter, gated by the propagation toggle); the Tasks tab passes none, so propagation stays Tasks-tab-excluded.
- **Soil-*mismatch* is promoted to a shared generator.** It was calendar-only and is a genuinely different task type from the unified soil-*amendment* task, so converging it meant adding `generate_soil_mismatch_tasks` (fed by a new `BedInput.mismatch_plants`, computed in `build_plan_state` when a soil service is present). Both surfaces now show mismatch warnings. Manual tasks now also appear on the calendar's actionable strip (both decisions were explicit product choices).
- **One status write-path.** `set_task_completion` is now a thin shim that delegates to `set_task_status` (the single source of truth, which still mirrors the legacy `task_completions` set for `.ogp` forward/back-compat). The calendar dashboard reads `effective_status` (showing only `open` tasks) instead of the `task_completions` done-set, so `task_completions` is now a **write-only serialized mirror** with no in-app reader. The dual-*write* invariant from point 3 is gone — there is exactly one write-path.
- **Calendar refresh fixed (#225).** The calendar's `refresh()` is heavyweight (#210), so it was wired only to `command_executed` and went stale on undo/redo. It now has a debounced `schedule_refresh()` that skips work while its tab is hidden (mirroring the Tasks tab), and is wired to `cmd_mgr.stack_changed` + `task_states_changed`. Frost arrives async via `_on_weather_ready`, which now calls `_rebuild_dashboard()` (the dashboard-only path) rather than the full `refresh()` to avoid re-triggering the weather fetch in a loop.

Presentation is allowed to differ (the calendar is an actionable, open-only strip with compact rows; the Tasks tab shows Done/Snoozed sections), but generation and status are unified. Tests: `tests/integration/test_calendar_task_convergence.py` asserts done/snooze/dismiss agree across both surfaces for the same `task_id`; `generate_soil_mismatch_tasks` is unit-tested in `test_task_generator.py`; the obsolete `tests/unit/test_dashboard_tasks.py` was removed (coverage subsumed by the engine tests).

## Addendum (#414 — one frost anchor per surface, and one date-window entry point)

**Context.** The frost-relative windows (sowing, transplant, harvest, propagation
steps) are anchored on the plan's last spring frost. Every GUI surface anchored
on *the current year's* frost, while the agent's `get_tasks` /
`get_task_calendar` anchored on every year whose window could reach the requested
dates — `generate_for_date_window` derives that range from the offsets. The two
therefore disagreed by construction: a southern plan (20 September frost) put a
tomato harvest at 29 Nov 2026 – 7 Feb 2027, invisible on every GUI surface on
1 January 2027. Measured by the committed harness
`scripts/measure_task_window_sweep.py` — over the 64 bundled species with
calendar offsets × 6 frost dates × every 10th day of 2026 (222 cases):
**1,849 missed (task, frost date, day) cases, 0 after the fix**, and 0 tasks the
GUI listed that the agent did not. The count is harness-dependent (all 118 species on every day of 2026 gives 18,007 before / 0 after), so quote the harness with the
number; the *invariant* is pinned by `tests/unit/test_task_windows_multi_anchor.py`,
which asserts both directions.

**Decision 1 — one urgency-filtered entry point, and one unfiltered one for the chart.**
`task_generator.generate_actionable_for_surface(state)` is the single path for the
two surfaces that list *reminders*: the Tasks tab and the planting-calendar
dashboard. It *wraps* `generate_for_date_window` rather than reimplementing it, and
re-applies the GUI's own listing rule (`classify_urgency(...) is not None`)
afterwards. That post-filter is part of the contract: the date-window path
deliberately runs with `actionable_only=False`, so without it a surface would list
the next decade.

The Gantt deliberately uses a **different** entry point,
`generate_for_date_window(state, Jan 1, Dec 31)`, because a calendar chart is not
a reminder list: it draws every window overlapping the displayed year, urgency
irrelevant. Routing it through the reminder helper would drop most of the chart —
which is exactly what happened during implementation. Two entry points, two
declared purposes; neither reimplements the other.

**Decision 2 — the chart consumes generated windows, it does not recompute them.**
`_GanttWidget` previously re-derived every bar from `self._last_frost` plus the
species week-offsets. That made it a second implementation of "offset to date" (the agent's `generate_for_date_window` and the dashboard's `generate_all` both *call* `generate_calendar_tasks` rather than reimplementing it, so the generator itself is the first implementation and the Gantt's re-derivation the second; the old "fourth" counted the callers) and it was
the reason the chart could only ever draw one anchor year. It now draws the
windows the shared generator produced, already clipped to the displayed year.

**Decision 3 — task ids carry the anchor year, and statuses stay separate.**
`make_calendar_task_id` produces `{species_key}:{task_type}:{anchor_year}`, so
listing a second anchor year produces a *second, distinct* id. This is correct and
load-bearing: the 2026-anchored and 2027-anchored harvests are different physical
harvests, and marking one done must not mark the other. Pinned by
`test_different_anchor_years_yield_different_ids`.

**Decision 4 — the propagation editor edits ONE plan; the others render.**
A species has one propagation plan per anchor year (`propagate_plans_by_anchor`).
The detail panel edits the plan anchored on the **current year**; the other
anchors are drawn on the chart and listed by the dashboard and the agent, but are
not editable. The panel's single-plan contract is preserved, which is what let the
#415 year fix stand on its own.

**Consequence for reviewers — two things the reminder helper must NOT do.**
Both were bugs found by the senior review of the first version, in the same eight
lines, with no test covering either:

- **Undated tasks stay.** `classify_urgency` dereferences both dates, and
  `generate_manual_tasks` emits undated tasks (`date=None`). Calling it unguarded
  raises `TypeError` and takes both task tabs down — for a plan the agent's own
  `add_manual_task` creates ("omit `date` for an undated task").
- **Manual tasks are never filtered.** `generate_manual_tasks` documents that "a
  manual task is never filtered out by urgency", and `TasksView._bucket`
  re-derives a bucket for exactly those (including its `no_date` case). They are
  also outside the date span, so they are merged in from their own generator
  rather than harvested from the date-window pass — a long-past or far-future
  to-do would otherwise be dropped before the exemption could apply.

**Consequence for reviewers — `actionable_only` is inherited per anchor year.**
`generate_for_date_window` builds each anchor with `replace(state, ...)`, so a
wrapper that passes the GUI's `True` into it filters anchors out *before* its own
filter runs — this produced an empty Tasks tab and a blank Gantt during this work.
Both call sites pass `False` inward and filter once at the edge. See §11.4.
