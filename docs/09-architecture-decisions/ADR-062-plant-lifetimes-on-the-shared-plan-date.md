---
id: ADR-062
title: "Plant lifetimes on the shared plan date"
status: "Accepted (US-F4); the plan-date task-reminder change shipped in v1.39.1 (PR #903; owner's manual test 2026-11-12)."
refs: ["US-F4", "#315"]
legacy_anchor: adr-062-plant-lifetimes-on-the-shared-plan-date-us-f4-315
---

# ADR-062: Plant lifetimes on the shared plan date

**Status**: Accepted (US-F4); the plan-date task-reminder change shipped in v1.39.1
(PR #903; owner's manual test 2026-11-12).

## Context

Season Manager copies a whole plan into a separate yearly file. Multi-year designs
also need an in-plan view of plants before planting and after removal. ADR-053 already
provides one local plan date through SimClock; another timeline date would split
growth, shadows and visibility. The 2D sprite still read today's wall date, so it
could disagree with the existing date-projected 3D canopy.

## Decision

- Keep SimClock as the only date state. One permanent adaptive Plan & Sun toolbar
  has an exact calendar, Today, a monthly slider preserving the preferred day, editable
  time, the daily animation and an optional live Hours of Sun map. Time is preserved
  by date navigation. The date is session state, never saved.
- A plant is present on the half-open interval `[planting_date, removal_date)`.
  Missing/malformed ISO bounds are open; a stored inverted interval has no present
  day. UI edits reject removal on/before planting before changing data/history.
  `removal_date` is optional additive `plant_instance` metadata; no FILE_VERSION bump.
  Fresh creation stamps the active plan date. Copies and loads preserve saved dates.
- CanvasScene combines presence with layer visibility; construction geometry retains
  its separate tool toggle. Date edits use one ChangePropertyCommand per gesture.
  Command stack changes, document loads and clock date changes reapply visibility.
  Hidden plants cannot be selected, including marquee selection. The hidden-plant
  menu names dates and can navigate to a present day to edit the plant again.
  Revealing a hidden layer uses the normal undoable layer command.
- Companion, spacing, capacity, guild and data diagnostics evaluate the date-present
  set independently of drawing-layer visibility. Solar receivers and casters also
  honor layer visibility. Hidden plants remain saved. API summary counts retain their existing counting
  rule, and object lists retain absent plants with `present=false`; `as_of_date`
  names the shared plan date (or, while a camera tour moves that clock, the owner's held
  date - ADR-072 addendum, #730). Runtime annotations live only in the API snapshot.
- PNG/SVG/PDF/DXF render the current visible state. The PDF plant table excludes
  date-absent plants while retaining hidden-layer data; every report page identifies a non-today plan date. An API layer
  override may reveal a hidden layer but cannot reveal a date-absent plant.
- Both 2D sprites and the existing shadow/heatmap/3D collectors use the shared date
  with the unchanged US-E8 growth model. Sprites invalidate their cached paint after
  a scrub; mature drawing geometry and spacing reservations remain unchanged.
- Task reminders use the plan's day: the Tasks tab's buckets and Done/Snooze writes,
  the calendar dashboard's "Today", and a new manual task's default read the plan clock
  (#859). An agent read may pass an explicit API reference day; `build_plan_state`'s
  wall-clock default applies only to a caller that supplies neither. A **live frost
  forecast** is the exception: its alerts name real calendar days and are classified
  against `PlanState.weather_today` (the wall day), never dropped by the plan-day
  window on a GUI surface, so a 2031 plan still warns about tomorrow's frost. The
  **Agent API's `get_tasks` stays window-bounded**: it returns only tasks inside the
  `from_date`/`to_date` window it reports.
  Historical calendar windows end before removal; actionable plant tasks stop
  once all instances of that species are removed. A surviving undated/later-removal
  instance keeps the species schedule. Future sowing tasks are useful before planting
  and are retained. Manual tasks and succession plans retain their independent dates.
- Season Manager retains hard copies and its existing keep/remove-plants choice;
  scrubbing never deletes objects or changes the season year.

## Alternatives rejected and consequences

A second slider date, deleting/recreating absent plants, and persisting the viewed
date were rejected: they create conflicting simulations, undo mutations while viewing,
or stale startup dates. Editing hidden plants requires navigation or undo, so their
names and date bounds remain discoverable. This feature filters plant instances only;
structure installation/removal dates and a new growth model are outside this story.

Evidence: `tests/integration/test_plan_timeline.py` exercises real controls, history,
save/load, diagnostics, rendered sprites and export artifacts; boundary and task
aggregation tests live in `tests/unit/test_plan_timeline.py`.


## Addendum: combined controls and live exposure (owner planning session, 2026-10-20)

The master merge brings ADR-059/060's Qt Quick 3D workspace. This timeline decision
is ADR-062: the original ADR-059 collided with the workspace, and the initially
chosen ADR-061 was taken by the later pitfall-catalogue merge (#546). Its
requirement bucket remains FR-34.

The owner chose one adaptive strip, monthly steps preserving the calendar day,
current local time at startup, a dated old-map preview during refresh, and exports
that wait for current exposure. The 21 June shortcut is removed. Past/Future
replaces the duplicated date text; on today the Today action already supplies that
context. A current map uses the calendar's date rather than repeating it, and empty
map status takes no space. Complete control groups centre vertically within each
row and wrap at narrow widths;
the calendar's width derives from font metrics. Page steps remain twelve months.
Within a continuous month drag a preferred 31st survives February; direct calendar
edits establish a new preferred day. Today sets the current date and time. Daily animation keeps
running while the user changes the date. No independent date state is introduced.

Decorative shadows and solar simulation are always on, including night/no-location
behavior. The old shadow-disable preference no longer overrides this policy. The
View menu's direct 3D View action uses the existing workspace; no new 3D window,
growth path or ground heatmap is added. The old simulation submenu/toggles are gone.

`LiveSunMap` owns the opt-in intent and latest desired exposure snapshot, separate
from the worker's snapshot and the displayed result. A 200 ms debounce coalesces
input bursts. One worker remains owned through queued finished; superseded work is
canceled and only the latest pending request is launched when ownership is released.
Date/geometry/lifetime/layer/location/bounds changes refresh while enabled; time-only
animation and requirement-only reclassification do not launch daily work. The old
map's actual date remains labelled Updating; stale receiver measurements cannot feed
badges/diagnostics. Document/location/grid replacement drops old imagery. Failure is
labelled Unavailable; unchecking cancels work and clears the preview. A failed open
that never commits leaves the current document/result intact.

`SunExportGate` is the shared visual-export readiness boundary. It pauses animation
under a counted lease and restores it after the last export. GUI waits pump a modal,
cancellable progress dialog; API waits occur in the existing provider worker thread,
outside the five-second GUI bridge call, with a 30-second deadline. Immediately before
writing, it checks document generation, plan revision, wall time and accepted exposure
identity. Cancellation, changed inputs, timeout or calculation failure writes no new
  output. PNG/SVG/PDF, Print and API image/PDF share this rule; DXF/data exports are unchanged.

Tests: `test_plan_sun_controls.py`, `test_timeline_quick3d.py`, the lifetime workflow,
the existing clock/heatmap/document/badge suites and the export transport tests.
No dependency, project-file version or persisted simulation-state change.


## Current constraints

New lifetime calendar choices currently use the SimClock range (1971–2999);
stored legacy dates are preserved and displayed. Entering a new pre-1971 planting
date through this editor is not available. Some legacy intervals have no present
day in the viewing range; the reveal action reports that limitation. Exposure
failure retry, per-tick scene scans, duplicate lifetime refresh and temporary
render-layer changes during concurrent exports remain maintenance follow-ups.
The review record and validation detail belong to PR #533.

## ADR-062 addendum: fixed toolbar topology survives legacy state (PR #556)

The owner manual pass reproduced a legacy saved layout with SunSimToolbar in the
same row as the drawing tools: at 1707 pixels wide it received 259 pixels, while
every neighbor stretched to 137 pixels tall. Making the strip visible did not
restore its dedicated row. A native capture using an isolated copy of the owner's
state reproduced the screenshot.

The main window now calls `UiStateStore.restore_geometry` with
`restore_window_state=False`. Window bounds and splitter proportions still restore;
the non-movable toolbar topology remains the application's initial two-row layout.
The generic store keeps layout replay as its default and preserves existing blobs.
No settings reset, project-format change or new user-visible option is introduced.
Replaying then relocating the adaptive toolbar before first show was rejected after
a reproducible native abort; bypassing obsolete topology avoids that path entirely.

Pinned by `test_restored_shared_row_cannot_squeeze_the_permanent_plan_strip` (strip
first/last in a shared row, two subsequent launches) and
`test_fixed_layout_can_restore_bounds_without_replaying_toolbar_state` (both policies).
Native Windows layout checks and captures use actual platform fonts; an offscreen
run with missing font discovery cannot establish the application's visual acceptance.

## ADR-062 addendum: chronological editor stepping (owner acceptance follow-up, PR #565)

**Context:** The owner found that holding an arrow stopped at the selected field's
boundary: 31 October, December, minute 59 and hour 23. Native stepEnabled disabled
that direction. Instrumented setWrapping(True) was rejected: it produced 31 October
to 1 October and 10:59 to 10:00, without carrying into the larger unit.

**Decision:** Keep native date/time editor subclasses and their appearance, text
editing and popup. Override both step entry and availability; both editors delegate
to one toolbar wall-reading path. Calendar arithmetic handles leap years and short
months, retaining the preferred day for month/year stepping. Civil minute indices
carry hours/minutes across midnight without timezone conversion or DST normalization.
Only the existing 1971-01-01 through 2999-12-31 range saturates a step. Mirror widgets
with their signals blocked, then emit one complete naive reading through the existing
SimClock writer; no intermediate old-date/new-time reading is published.

**Consequences:** Sliders/daily animation retain their existing selected-day policy.
No new clock, persistent setting, undo command, file-format change or dependency.
Pins: tests/integration/test_plan_sun_stepping.py (arrows/repeat, wheel/buttons,
leap/preferred days, range and atomic signals), and
tests/integration/test_timeline_quick3d.py::test_minute_rollover_updates_presence_sun_and_3d_once
(real midnight keypress, presence/builders/light, unchanged plan revision/history).

**Status:** Accepted; owner acceptance confirmed, shipped in [v1.30.19](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.19) via [PR #565](https://github.com/cofade/open-garden-planner/pull/565).

## ADR-062 addendum: actionable location prerequisite (PR #566 manual pass)

The owner confirmed that configuring the missing location restored 2D shadows,
Hours of Sun and animated 3D lighting. The prior status-bar explanation was too
remote from those controls. Plan & Sun now displays a persistent translated link
beside Hours of Sun while either coordinate is missing, replacing the generic
map-unavailable label. The link emits a UI request to the existing location-dialog
handler; it does not guess coordinates or change the clock. Cancel preserves the
hint and plan. Location changes, including New/Open, refresh the hint; saving valid
coordinates lets the existing live-map scheduler recover. Zero coordinates are
valid. Unlike time-varying night text, this prerequisite changes only on location
or document edits, and is covered by the adaptive toolbar's native layout tests.

Pinned by test_sun_location_hint_opens_existing_dialog_and_recovers_map and the
located/unlocated locale/theme/width matrix in test_plan_sun_controls.py.

## ADR-062 addendum: Past/Future in the Today button (PR #584 manual pass)

The owner found the separate Past/Future label more disruptive than useful. It
appeared, disappeared and changed width as the date moved. That pushed the
controls after it, including the month slider under the dragging pointer. The
label is removed. The Today button says Past or Future in its own place while the
plan date is elsewhere. The button always stays enabled. A click sends the
current aware instant to the simulation clock, which updates the plan date and
time together in the plan's zone. This also resets a scrubbed time on today's date.

The button has one width for all three texts. `_TodayButton.sizeHint` keeps the
style's padding and puts it around the widest of the three texts in the active
language. Each text is measured as `QToolButton::sizeHint` measures it
(`fontMetrics().size(Qt::TextShowMnemonic, …)`, a bounding rectangle rounded up).
The first version used `horizontalAdvance`, which rounds to the nearest pixel. With
fractional font metrics the width then still moved by 1 px: in 378 of 480
font/size/language combinations at 125 % scaling (hinted Windows fonts), and in 342
of 432 with unhinted fonts at 100 %.
One letter's width is added as the buffer the owner asked for. The width follows a
font or theme change, because it is a size hint and not a fixed pixel value. A
language change takes effect on restart, as for every string in the app. The
button's accessible name and tooltip describe the action, "Go to the current date
and time".

The cost is a wider Today group on today. With real Verdana 9 pt (Windows font
engine) the button goes from 59 to 123 px in German and from 45 to 78 px in
Spanish. With the theme, German at 10 pt in an 800-px strip then needed a third
row by the strip's own row estimate, with the sliders at their former 90-px floor;
80 px brings it back to two. The floor is now 70 px (`_MIN_SLIDER_WIDTH`): the
measured need plus 10 px for a platform font that runs wider. The reflow only
shrinks the sliders when the strip needs it, so wider windows are unchanged. At such
widths the month slider was never month-precise by mouse (its range spans at least
132 months: about 0.55 px a month at 90 px, 0.4 at 70); its keys and the wheel step
by month. (The first draft of this addendum quoted 48 and 108 px. Those were the
offscreen platform's box font, not Verdana: PF-TST-26.)

Pinned by test_today_button_says_past_or_future_in_place_and_nothing_after_it_moves
(en/de/es × both themes), which scrubs the month slider across today and back and
asserts the button's width and the month slider's position do not change;
test_today_button_width_holds_with_fractional_font_metrics (unhinted fonts at
fractional sizes); and the themed variants of
test_translated_controls_fit_two_rows_at_narrow_width, which also assert the
reflow's own two-row estimate. Run with `QT_QPA_PLATFORM=minimal:enable_fonts`
for real fonts on the dev box.
