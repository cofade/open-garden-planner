# Case study: a light rim the owner saw and the metric said was not there (#687)

## Symptom

The 3D survey reported, and a comment on #687 repeated, a light rim about 20 levels bright
round raised beds and other objects on the snow board shot (High), while open flat snow read
160 against 180 on Low. A first session of measurements built an image-space rim probe (the
luma without ambient occlusion minus the luma with it, in a band 2-6 px from every object
against the open snow beyond 16 px) and a world-space profile out from the bed walls. Both
said: no rim (rim 0.0 to -0.8 at every AO setting tried). The session concluded that the
survey's "rim" was open snow darkened by AO next to pixels AO cannot reach, and moved on.

## Wrong theories

1. **The rim is the survey's misreading.** The probe found the band near objects exactly as
   dark as the open snow, at every strength, reach and bias.
2. **The rim exists only where the screen radius falls under a pixel.** Plausible from Qt's
   pass (it returns 1.0 there), and it would explain a rim the probe's band could not hold.

## Key evidence

A crop of the AO frame against the no-AO frame, looked at instead of measured, showed the rim:
a bright band beside the bed walls and round the shrubs, grey snow beyond. A second probe with
a direction (the meadow rows straight above a silhouette) came back empty — no band had more
than 40 pixels — which cannot be true of a frame full of objects. Printing the masks down one
column:

| | value |
|---|---|
| `camera.horizon_row()` on the board's overcast and snow cameras | **-131** (the horizon lies above the frame) |
| rows the probe marked as sky (`mask[:horizon_row + 4] = True`) | **0 .. 592 of 720** |

`a[:-127]` is not "nothing": it is every row but the last 127. Both earlier probes had judged
only the bottom sixth of the picture — the near snow in front of the beds, where the rim is
not.

## Root cause

A slice bound computed from a camera (a horizon row) was negative, and numpy reads a negative
stop from the END of the axis. The mask that should have taken nothing took 82 % of the frame.

## Fix

The probe clamps the bound (`occlusion_rim`: sky rows only when the horizon row is inside the
frame), and `tests/unit/test_board_probes.py::test_a_light_band_above_a_silhouette_is_a_rim_and_even_darkening_is_not`
pins a horizon above and inside the frame. With the mask right, today's AO left a rim of
9.5-10 levels above every silhouette against the meadow behind it (12-13 levels of flat
self-occlusion far from objects) — the survey was right, and the fix of #687 (a weather's bias
at 0.3 of its reach, PF-L3D-26) brought it to 1.2-2.1.

## Lesson

A probe that reports "nothing there" against an owner's eyes is the first suspect, not the
owner. Look at the frame, then print the mask the probe judged: a number computed from a
camera can fall outside the frame, and a negative numpy index silently means the other end.
Clamp every bound that comes from geometry (PF-L3D-27).
