---
id: ADR-049
title: "Frost-Date Semantics - One Parser, 29 February Substituted as 1 March"
status: "Accepted (2026-10, #414 / #416, task-date correctness package)"
legacy_anchor: adr-049-frost-date-semantics---one-parser-29-february-substituted-as-1-march
---

# ADR-049: Frost-Date Semantics - One Parser, 29 February Substituted as 1 March

**Status**: Accepted (2026-10, #414 / #416, task-date correctness package)

## Context

A plan stores its frost dates as `'MM-DD'` strings with no year
(`location["frost_dates"]["last_spring_frost"]`). Every consumer must turn one into
a real date for a *specific* year, because all the calendar windows are anchored
on it. Before this decision there were **four** independent notions of what a
frost date is, and they disagreed in both directions:

- `services/task_generator._parse_frost` (used by every generator and by the agent
  through `generate_for_date_window`);
- a byte-identical duplicate in `ui/views/planting_calendar_view.py`;
- a regex in the location dialog that accepted six dates which can never exist
  (`02-30`, `02-31`, `04-31`, `06-31`, `09-31`, `11-31`). Accepting one produced a
  plan whose frost date then parsed to nothing — i.e. a plan that silently showed
  **no tasks on any surface**;
- `models/succession.py::compute_season_segments`, which sliced the string and
  called `datetime.date` directly. It was found and fixed in review of this
  change, not before it — a reminder that "three readers" is a number someone
  has to go and count. Its `except ValueError` degraded to month-only boundaries,
  so for a `02-29` frost the bed's season segments and the task windows
  disagreed about the same plan on the same day.

Separately, `'02-29'` is a legitimate stored value that exists only in leap years.
Anchored as a literal, a 29-February plan had **no** spring-frost tasks in every
non-leap year: the planting calendar said "No location set.", the Tasks tab listed
none, and `get_tasks` / `get_task_calendar` returned `coverage: "no_frost_dates"` —
which the agent API documents as "the plan has no geo-location", so a client
following the `plan-my-week` prompt asked for a location the plan already had.

## Decision

1. **One parser, one validator.** New Qt-free module
   `core/frost_dates.py` owns `parse_frost(mmdd, year)` and
   `is_valid_frost_date(mmdd)`. The location dialog, the task generator, the
   succession season segments and the Phase 17 spike all go through it; the
   calendar view's duplicate is a thin shim and its dead regex is gone. The invariant "what the dialog accepts is what the
   parser reads" is pinned by
   `test_every_accepted_date_parses_in_a_leap_year`.

2. **`02-29` is accepted at the input boundary** (it is a real date in a leap
   year), and **substituted with 1 March** in a year that has no 29 February
   (`NON_LEAP_SUBSTITUTE_MONTH_DAY`). Consequences accepted deliberately:
   - a 29-February plan now has a full task surface in **every** year, so the
     "no location set" / `no_frost_dates` symptom cannot occur;
   - the substituted date is **invisible by construction**, which is the failure
     mode to avoid, so it is named in one constant, documented here and in §11.4,
     and pinned by tests in both a leap and a non-leap year;
   - in a multi-year listing the non-leap anchor's windows sit **one day later**
     than the leap anchor's. Stated up front so a later reader does not "fix" it.

3. **The producer of a window and the renderer of a window must be the same
   function.** The Phase 17 spike's `in_harvest_window` previously returned `None`
   whenever the anchor year lacked a 29 February ("no window to read"); after the
   substitution that was the last remaining place where a 29-February plan behaved
   as if it had no frost date, so it now consumes `parse_frost` too. Its
   `in_frost_free_season` deliberately still compares `(month, day)` without a
   year — a different question, which never had a year-existence problem — and the
   docstring says so to stop the next reader from "fixing" it.

## Consequences

- Qt-free and unit-testable without a QApplication (invariant 10).
- The substitution is a **product decision with a visible side effect**, not a
  parse detail; anyone changing `parse_frost` must revisit this ADR.
- `tests/unit/test_spike_q3d_board.py` had encoded the old "no window in a
  non-leap year" behaviour as its oracle and was updated to agree with the shared
  rule — the change is stated in that file's docstring rather than made silently.
- `core/frost_dates.py` must stay free of Qt imports; it is imported by the
  generators, a `QDialog`, and the spike.

## Related

The bundled plant data's *harvest offsets* were a separate, related finding
(#416): `harvest_start` was documented as "weeks after planting" while every
reader counts it from the frost. Measured over all 118 bundled species, **both** readings fit a majority of the 64 comparable rows — 37 fit / 27 miss frost-relative (what the code does) and 46 fit / 18 miss planting-relative, with 11 fitting neither — so the data is NOT irreconcilable. The documentation was made true and the row conversion deferred to **#418** on the grounds that it needs a cited horticultural source per row (plus licence clearance), not on irreconcilability. Measured by `scripts/measure_harvest_offsets.py`; an earlier draft quoted figures matching no harness, which the senior review caught. `KNOWN_DIVERGENT_SPECIES` in
`tests/unit/test_harvest_offset_semantics.py` is the pinned baseline, and that
test also asserts that `days_to_maturity` is reference data no computation reads —
which is what keeps the correction out of the generator.
