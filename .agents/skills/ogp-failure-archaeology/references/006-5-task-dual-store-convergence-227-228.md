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

