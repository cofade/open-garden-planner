## Case study: a year's time-lapse that jumped at the clock change (#732, fixed 2026-11-05)

**Symptom**: A camera tour across the year changes brightness abruptly between two
neighbouring frames at the end of October - the owner read 24 luma levels in the
promotional video. Nothing else in the video jumps; the camera path and the grade are
continuous.

**Theories entertained (wrong)**:

- The sky's own update (a new sun, a cloud pass, the atmosphere) settling differently on
  one frame.
- The colour grade or the tone mapper reacting to the low sun.
- The video writer (encoding, colour conversion) repeating or dropping a frame.

**What instrumentation revealed** (`tests/integration/view3d_capture_driver.py`,
scenario `timelapse`, a two-week tour across the change, per-frame mean luma of the saved
PNGs and the clock's UTC time read after each capture):

```text
utc_times: 13:00 ... 13:00 | 14:00 ... 14:00     <- two values, one per side of the DST change
luma_steps: 0.004 1.281 0.005 ... 18.067 0.004   <- every other step < 2
```

The UTC time-of-day changed exactly where the wall time stayed 15:00. The sun is computed
from `SimClock.utc`; holding the wall time across a DST change therefore moved the sun by
an hour - the "jump" was a real solar hour, not a rendering fault.

**Root cause**: `WorkspaceCaptureCoordinator._tour_clock` moved a year tour with
`clock.set_date(day)`, which keeps the wall time by design (ADR-053). That is right for a
day tour, whose time range is the variable, but wrong for a year tour, whose date is: the
zone offset changes under the fixed wall reading.

**Fix** (`ui/view3d/workspace_capture.py`, `_tour_clock`; `SimClock.set_utc_time_on`;
ADR-053 addendum L6): the first frame records its UTC time-of-day; every later frame asks the
clock for the **instant** whose local date is the frame's and whose UTC time-of-day matches, so
the wall reading is derived through the zone with the repeated autumn hour's `fold` included. A
local date with no exact instant (a 23-hour spring day) gets the nearest reading on that date,
within the missing hour. The local clock shifts by the DST offset, the sun moves evenly away
from midnight, and the dates
the dialog names are kept.

**Lesson**: "same wall time" is not "same sun". Any clock writer that sweeps dates must
hold the UTC instant and derive the wall reading - and the proof is a per-frame measurement
of the thing the user sees (luma), not an assertion that the clock API was called. The
render tier now pins the two-week gate: largest neighbouring-frame step 1.53 levels after
the fix, 18.07 before it.
