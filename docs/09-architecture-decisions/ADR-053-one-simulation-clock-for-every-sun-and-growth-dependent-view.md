---
id: ADR-053
title: "One simulation clock for every sun- and growth-dependent view (Phase 17, L1.0)"
status: "Accepted (2026-10-09, #385 story L1.0, epic #383). This is the first Phase 17 L1 ADR. The epic reserved ADR-049 for the scene pipeline, but that number went to frost dates, so the scene-pipeline ADR follows with L1.1."
legacy_anchor: adr-053-one-simulation-clock-for-every-sun--and-growth-dependent-view-phase-17-l10
---

# ADR-053: One simulation clock for every sun- and growth-dependent view (Phase 17, L1.0)

**Status**: Accepted (2026-10-09, #385 story L1.0, epic #383). This is the first Phase 17 L1 ADR. The
epic reserved ADR-049 for the scene pipeline, but that number went to frost dates, so the
scene-pipeline ADR follows with L1.1.

## Context

Four places each held their own idea of "the simulated moment", and they did not agree:

- `SunSimToolbar` held its widgets (date picker and time slider, in the system zone) and seeded
  `now()` itself.
- `SunShadowController` held a separate UTC instant, seeded `datetime.now(UTC)` independently, and
  grew plants for that instant's **UTC date**.
- The hours-of-sun heatmap took the toolbar's **local** date. A code comment admitted that "near
  midnight the two can name different days".
- The 3D view read the overlay's UTC instant for the light and its UTC date for growth.

So after local midnight east of UTC (or before it west of UTC), the overlay and 3D grew plants for
one day and the heatmap for another. The app decided whether to rebuild 3D by comparing two UTC
dates. And a heatmap still computing when the date changed was never cleared: the stale rule only
looked at a *visible* map, so the late result painted the old day under the new date. Phase 17 adds
more consumers of the same moment — the 3D workspace (L1.3), sky and looks (L1.4), the day sweep
(L2) and playback (L5) — and each would have needed the same reconciliation again.

## Decision

1. **One clock.** `core/sim_clock.py::SimClock` is the session's single simulated moment.
   `GardenPlannerApp` owns it and passes it to the shadow overlay. The toolbar is a *view* of the
   clock: every user edit is written to the clock, and the clock is mirrored back with signals
   blocked. The heatmap request and the 3D view read the clock too. Every session starts at "now";
   the moment is not persisted (FR-SUN-04, unchanged).
2. **The plan date is the user's LOCAL calendar day, stored as given.** `SimInstant` holds
   `plan_date` and a naive wall-clock `time_of_day` in the clock's zone. The UTC instant for
   `core/solar` is *derived* from that wall reading. Shadows, heatmap and 3D all grow plants for
   `plan_date`.
3. **A time change never fires `date_changed`, by construction, on the path the product uses.** The
   toolbar emits its **naive wall reading** (picker date plus slider time, `current_wall_datetime()`),
   and `set_datetime` stores a naive datetime unchanged. `set_time_of_day` and `set_date` never derive
   a date either. So no UTC offset, DST transition, or wrap past midnight can move the date; the
   toolbar's animation stays on its date. An **aware** `set_datetime` is an *instant*, and its date is
   read in the clock's zone. That is right for an instant, but a wall time that is first turned into
   an instant can land on another day: inside a spring-forward gap that starts before midnight
   (America/Nuuk: Saturday 23:00 jumps to Sunday 00:00), the instant of "Saturday 23:30" reads back as
   Sunday 00:30. **User-facing writers therefore hand over wall readings, never instants.**
   `date_changed(plan_date)` fires only when the date moved, then `instant_changed(SimChange)`. A
   no-op write emits nothing.
4. **Qt-free, with two plain channels that are Qt-like in two respects — and not in a third.** The epic names the sim
   clock an engine-independent core: it is the NO-GO insurance, and it can be tested headless without
   a `QApplication`. It therefore notifies through a minimal synchronous `Channel`:
   - `connect` is idempotent; bound methods compare by their target.
   - A **bound method is held weakly**, like a Qt connection: a subscription never keeps its receiver
     alive, so a controller that owns a clock and listens to it forms no reference cycle, and an
     unparented controller dies by refcount. Other callables are held strongly.
   - A listener disconnected during an emission is skipped.
   - **Every listener runs**, and the first exception is re-raised after the last one, with later
     errors attached as notes. `SimClock` delivers `instant_changed` even when a `date_changed`
     listener raised, so one failing consumer (say, a 3D rebuild) cannot starve the overlay and the
     toolbar.
   - Writing the clock from inside its own notification raises `RuntimeError`; the remaining
     listeners would otherwise receive a stale change.
   - **Not Qt-like: nothing disconnects a QObject receiver whose C++ side is destroyed** while its
     Python wrapper lives (measured: after `sip.delete` of a controller's parent, clock writes
     still call the dead controller). The rule for every Qt subscriber, binding from L1.3 on:
     disconnect in your own teardown (or on `destroyed`), and **never connect a bound signal's
     `emit`**. That is a builtin, held strongly, so after its QObject is deleted every clock write
     raises `AttributeError` (after the state is committed), and `disconnect` raises
     `RuntimeError`, so the channel cannot be cleaned. A bound method of an object that cannot be
     weakly referenced (`__slots__` without `__weakref__`) is refused with `TypeError` at `connect`.
5. **DST, exactly.** PEP 495 `fold` is part of the wall reading and of `SimInstant` equality (plain
   `time` equality ignores it). An aware instant is read into the clock's zone through UTC, with an
   exact round trip through the repeated fall-back hour (both folds are tried for the system zone and
   fixed offsets). A wall time inside a skipped hour is converted by PEP 495's rule, the offset in
   force before the gap (CPython, the same on every platform). Two readings inside a gap can name one
   instant and still compare unequal, because they are different things the user picked. The
   toolbar cannot express `fold`, so it always picks the first occurrence. Two visible effects,
   neither touching the plan date: on a spring-forward day, the skipped hour's wall times show the
   sun of the hour after it, so Animate replays that hour's sun once. In a session seeded during
   the second occurrence of a repeated autumn hour (`fold=1`), the next slider or Animate step
   lands on the first occurrence, and the sun steps back about 59 minutes (measured: a +1 minute
   drag moved `utc` by −59 minutes).
6. **A supported date range, 1971-01-01 … 2999-12-31.** The system zone converts through the
   platform's `localtime`/`mktime`, which on Windows raise `OSError` near and before the 1970 epoch
   and during 3001. Measured on Windows 11 with CPython 3.12 in Europe/Berlin: 1960,
   1970-01-01 12:00 and 1970-01-02 00:00 fail, 1970-01-02 01:00 works; 2999-12-31 and 3001-01-02
   work, 3001-06-01 fails. CPython probes about a day either side of the instant.
   The clock refuses dates outside the range with a `ValueError`, and the toolbar's date picker uses
   the same range. Its default was 1752–9999, and picking such a date raised inside a Qt slot.
7. **The heatmap's stale rule follows the plan date.** A new plan date clears a map for another day
   when it is shown, **or while a launched compute's result is still pending**
   (`SunHeatmapController.result_pending`). `QThread.isRunning()` is not enough: it is already False
   once `run()` returned, while the worker's `success` and `finished` signals still wait in the GUI
   queue. `run_for_day` likewise refuses a new launch while a result is pending: accepting one in
   that queued window let the first worker's `finished` `deleteLater` the running second one, a Qt
   fatal abort (measured by the round-2 review; unreachable from the button, which stays
   busy-disabled).

## Alternatives considered (rejected)

- **A `QObject` clock with `pyqtSignal`s in `core/`**, as `CommandManager` and `ProjectManager` are.
  It would carry Qt into the layer the epic names Qt-free (the NO-GO insurance), and its tests would
  need Qt. The `Channel` gives the two connection properties that matter (weak receivers and
  delivery to every listener) without Qt. A later Qt consumer can add a thin adapter.
- **App-only fan-out with no channels**, where setters return a `SimChange` and the app dispatches.
  This works for L1.0, but every later writer (the 3D time control, the day sweep, playback) would
  have to route through one app method, and "fires `date_changed`" would have no subject to test.
- **Keep a UTC instant and derive the date from it.** This is the bug. A UTC date is not the user's
  day, and the senior review showed that even a *local* date derived from an instant fails the gate
  inside a gap that straddles midnight.
- **Use the garden location's zone instead of the system zone.** The `.ogp` location stores no zone
  today, so this is out of scope. The clock takes `tz` as a parameter, and because the toolbar edits
  wall readings in the clock's zone, both would switch together.

## Consequences

- Shadows and 3D now grow plants for the toolbar's date. The visible fix appears only near local
  midnight east or west of UTC.
- `SunSimToolbar.datetime_changed` now carries the naive wall reading instead of an aware local
  datetime; `test_slider_change_emits_aware_datetime` became `test_slider_change_emits_the_wall_reading`.
  `current_datetime_local()` is replaced by `current_wall_datetime()`, and `test_datetime_round_trip`
  compares wall readings. `set_datetime_local()` takes only a naive wall reading and writes only a
  field that differs, because re-setting an unchanged date wiped a date the user was typing on
  every Animate tick.
- There is deliberately no `SimInstant.local` / `SimClock.local`. Its `.date()` would be an
  instant's date, which is not the plan date inside a gap that straddles midnight.
- Four app-glue tests in three files now pass naive wall readings, as the toolbar does; UTC inputs
  named another day in zones far from UTC. Their assertions are unchanged.
- Any writer of the clock regrows 3D on a date change, including `SunShadowController.set_sim_datetime`
  on the shared clock. `test_3d_view` counts one more rebuild because of this.
- Out of scope and unchanged: the 2D plant icon keeps today's real date (FR-SUN-08, #299), tasks and
  calendars keep `date.today()`, and the dormant spike keeps its own shot dates.
- **Trap for any later story that moves the 2D icon onto the plan date.** `CircleItem` sizes its
  icon from `date.today()` (`circle_item.py`), and #430 (NFR-PERF-01) now backs canvas items with
  `DeviceCoordinateCache`. A cached item is not repainted by a pan or by an overlay repainting
  above it, so if the icon is ever driven by `SimClock.plan_date`, `_on_sim_date_changed` must call
  `update()` on the affected plant items — otherwise scrubbing the date leaves stale icons until a
  zoom or re-selection. Nothing in L1.0 meets this: the clock's fan-out never touches what a 2D
  item paints, and the shadow and heatmap overlays are uncached plain items (senior review of the
  #430 merge).
- Later stories subscribe instead of reconciling. L1.3's sync pipeline regrows on `date_changed` and
  relights on `instant_changed`; L1.4 rebuilds the sky only for a noticeable sun move.
- Senior review, round 1, found the two P1s that decisions 3 and 7 now close. The first draft's
  gate held on `set_time_of_day` but not on the toolbar's real path, and its stale rule keyed on
  `isRunning()`. It also found the channel's strong-reference cycle and the doc numbers corrected in
  decision 6. Lesson (PF-DOM-22): test the gate on the path the product actually takes.
- Round 2 found the P1 the round-1 fix introduced: the clock-to-toolbar mirror rewrote the
  unchanged date on every Animate tick and wiped a date being typed. It also found the launch
  guard, the overclaimed "Qt's rules", the instant-derived `local` reads, and app-glue tests that
  still drove the instant path (all closed above).

## Validation

**`tests/unit/test_sim_clock.py`** (Qt-free). IANA-zone cases skip where the platform has no tz data;
a bare Windows venv has none, CI Linux runs them, and they were run locally with `tzdata` on
`PYTHONPATH`. It pins:
- `set_time_of_day` sweeps over every minute, plus the midnight wrap: an ordinary day in the
  machine's zone (CI's is UTC) and in two fixed offsets (+09:00, −07:00), the 2026 DST days in
  Berlin and New York, and the EU DST dates in the machine's zone (ordinary days under CI's
  UTC). These sweeps document the API but **cannot fail by construction**, since that setter
  never derives a date. The proof of the gate is the naive-reading sweep of Nuuk's
  pre-midnight-gap Saturday here, plus the toolbar-path test below;
- the pinned hazard that an instant of a gap reading lands on Sunday;
- an exact round trip every half hour of 2026 in five zones;
- fold equality, normalisation of an aware input that already carries the clock's zone, and the
  range edges;
- re-entrancy, delivery of `instant_changed` after a `date_changed` listener raised, and the channel
  rules (weak bound methods, strong functions, a refused unweakrefable receiver, every listener
  runs);
- an AST scan that keeps the module on the standard library.

**`tests/integration/test_sim_clock_wiring.py`** (the §8.10 workflow on a real `GardenPlannerApp`).
It pins:
- a slider drag moves only the light and keeps the heatmap;
- a date edit regrows 3D once and clears the heatmap;
- the animation wraps past midnight and stays on the same date;
- an external clock write moves the toolbar;
- with a +09:00 clock, the overlay, the heatmap request and the 3D rebuild all name local
  2026-06-22 while the UTC date is 2026-06-21;
- every slider value and 20 Animate ticks through the real toolbar keep Nuuk's Saturday;
- a date being typed (QTest keystrokes) survives an Animate tick and lands when finished;
- `run_for_day` refuses a second launch while the first result is queued;
- a date change mid-compute — while running, and after `run()` returned with the result still
  queued, driven through the button — never lets the late map paint, and leaves the button idle;
- an unparented controller dies without a GC cycle.

All three P1 tests (round 1's two, round 2's typing test) fail when their fix is reverted.

## Addendum L1.3 — `connect_qobject`: the rule of decision 4 as a mechanism (2026-10-12, #385 story L1.3)

Decision 4 ended with a rule: nothing disconnects a QObject receiver whose C++ side is destroyed
while its Python wrapper lives, so every Qt subscriber disconnects in its own teardown. L1.3 adds
more subscribers (the 3D pipeline's controller listens on both channels) and turns the rule into
one helper, `ui/sim_clock_subscription.py`:

```python
connect_qobject(clock.date_changed, self._on_date_changed)      # a bound method of a QObject
connect_qobject(clock.instant_changed, self._on_instant_changed)
```

- The channel calls a **guard**, not the slot. The guard asks `sip.isdeleted(receiver)` at every
  delivery; a receiver Qt has destroyed is not called, and the guard takes itself off the channel.
- The guard lives exactly as long as the receiver's Python wrapper (a weak-keyed registry), so
  L1.0's two properties survive: a subscription never keeps its receiver alive, and a collected
  receiver leaves the channel at once.
- Only a bound method of a live QObject is taken (`TypeError` otherwise; `RuntimeError` for a
  receiver that is already gone). `disconnect_qobject` takes a slot off by hand.
- **Binding from now on:** no module of the product connects to `date_changed` or
  `instant_changed` directly. An AST scan of `src/` enforces it
  (`tests/unit/test_sim_clock_subscription.py::test_no_module_of_the_product_connects_to_a_clock_channel_directly`);
  the main window's two subscriptions and the shadow overlay's were moved.

**The alternative that was built first and crashed.** "Disconnect on `destroyed`", as decision 4
suggests, was implemented as `receiver.destroyed.connect(<closure that disconnects>)`. The suite
then died with an access violation in a test that has nothing to do with it
(`test_sim_clock_wiring.py::TestHeatmapMidComputeDateChange`). Reproduced in bare PyQt: a Python
callable connected to `destroyed` lives and dies with Python's idea of the wrapper. When the
wrapper is garbage in a reference cycle while Qt still owns the C++ object (a `deleteLater()` is
pending), the cyclic collector clears the callable and the connection stays behind — and then
the signal is either never delivered (the hook ran 0 times) or delivered into what is left (the
access violation). The helper therefore hangs nothing on `destroyed`; a test pins that
(`::test_the_helper_hangs_nothing_on_the_destroyed_signal`). PF-E3D-07, item 1 of archive/05-l1-3-workspace.md, has the reproduction.

## Addendum L6: a year's camera tour is an instant-holding clock writer (#732)

A camera tour is the second kind of writer this ADR did not have in view. A **day** tour holds
the wall time and sweeps the time of day, exactly like the toolbar. A **year** tour used to hold
the *wall* time across dates, which is not the same as holding the sun: `utc` is derived from the
wall reading, so both daylight-saving changes moved the sun by an hour inside the video - the owner
saw a 24-level brightness step between neighbouring frames (#732; a two-week reproduction measured
18.07 levels).

The tour therefore holds the **UTC time of day** for a date range:

- The first frame is written as the dialog promises it - its date at the owner's current wall time
  - and its `utc` time-of-day becomes the held value.
- Every later frame calls `SimClock.set_utc_time_on(frame_date, held_utc_time)`: the clock finds
  the instant whose **local date** is the frame's and whose **UTC time-of-day** matches, and stores
  its wall reading. The derivation goes through the zone, so the repeated autumn hour gets the
  occurrence whose instant actually matches (`fold` included) and the spring gap gets the real
  local hour (03:30, not the nonexistent 02:30). This is a clock-side operation, not a user-facing
  writer handing an instant: decision 3's rule is unchanged for the UI.
- A local date with no such instant - a 23-hour spring day - gets the nearest reading on
  that date (within the missing hour), so the dates the dialog names are kept.
- Only a tour with a `date_range` or a `time_range` holds and restores the owner's moment; a
  flight preview writes the clock not at all, so a date set while one runs survives it (ADR-072
  addendum, #730).

Pinned by `tests/integration/test_directors_cut.py::test_a_years_time_lapse_holds_utc_across_both_clock_changes`,
`::test_a_years_time_lapse_holds_utc_through_the_repeated_autumn_hour` and
`::test_a_year_time_lapse_repeating_a_change_day_keeps_the_instant` (an EU DST zone without
tzdata: constant UTC time-of-day across both changes, the dialog's dates kept, a 03:30 start on
the change day that the wall-offset version turned into a one-hour jump, and a real tour's repeated
date steps) and the render tier's two-week clock-change luma gate
(`tests/integration/test_directors_cut_render.py::test_a_year_time_lapse_does_not_jump_at_the_clock_change`:
largest step 1.53 levels after the fix against 18.07 before it).

## Addendum #945 (2026-11-20): the plan's own time zone

**Status:** Shipped in v1.40.11 (PR #981). Owner manual testing passed on 2026-11-20.

The "garden location's zone" alternative rejected above is now implemented, because the
location does carry a zone: the example generator has written `location["timezone"]` all
along, and the Location dialog now writes it too (an editable IANA-name picker, prefilled
by the Open-Meteo lookup). The clock, the toolbar's wall time, a camera tour's time range
and the "Today" button read it.

- **The stored key is additive.** `location["timezone"]` sits inside the existing location
  dict; a plan without it behaves exactly as before (the computer's zone), and an unknown
  name is treated as absent rather than failing the load. No `FILE_VERSION` change.
- **`core/plan_time.py`** is the one resolver: `plan_timezone_name`, `plan_timezone`
  (an invalid name → `None`), `timezone_names` for the picker and `plan_today`, which
  answers the garden's date for the toolbar's Past/Today/Future state. It is Qt-free.
- **`SimClock.set_timezone(tz)` keeps the WALL reading and moves the instant.** The date
  and time of day are the plan's local reading the user is looking at, so they are kept
  (including `fold`); the sun is re-solved for the same reading at the garden's place.
  A zone change is not a date change: `date_changed` does not fire and growth is untouched.
  `None` returns to the computer's zone.
- **Windows has no IANA database.** `tzdata` is now a runtime dependency, and
  `installer/ogp.spec` collects its files: without them every named zone raises
  `ZoneInfoNotFoundError` in a frozen build. The data package is Apache-2.0.
- **"Today" follows the garden, not the computer.** The toolbar takes a `today_provider`
  (the app passes `plan_today(project.location)`), so a plan in Tokyo on a Berlin computer
  shows the correct Past/Today/Future state and jumps to the garden's current date and time.
- **Not changed:** a plan with no zone still uses the computer's; the 2D plant icon's
  real-date rule (FR-SUN-08) and task/calendar `date.today()` reads are out of scope here.

Pinned by `tests/unit/test_plan_time.py`, `tests/unit/test_sim_clock.py::TestPlanTimezone`,
`tests/unit/test_location_dialog.py` and
`tests/integration/test_sim_clock_wiring.py::TestThePlansTimeZone` (a location change, a
save/reload round trip and clearing the zone).
