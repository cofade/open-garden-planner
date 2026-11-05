# Case study: a sky probe that read a false 20-luma dip (#695/#717)

## Symptom

The new set-sun probe, run on the **painted** sky (the reference that never had the L5
black sun), failed on every frame: a dip of 19.7 to 24.2 luma, always in the same image
row, always at the same reported elevation — −1.12° — whatever the sun's own elevation
(+1.0, +0.4, 0.0, −1.0, −3.0). The images looked clean. The probe was the new code.

## Wrong theories

1. *The painted sky has a dark ring under its set sun.* It did not: the L5 fix made a set
   sun match its sky, and the same frames pass the eye. This was the probe's first run.
2. *The sun's glow is darker than the sky around it.* A glow can be, but not at the same
   place for a sun that moved 4° between frames.
3. *The camera sees the ground hemisphere under the horizon and that is the dip.* It
   renders with `ground=None`, so the whole frame is sky; the ground hemisphere is sky
   too, and it is a smooth vertical gradient.

## Key evidence

The reported elevation was **the same for every target sun** while the frame names and
sun elevations differed. That is the tell: the number came from the instrument, not the
scene. The probe compared pixels **in the same image row** near the sun's bearing against
the row's pixels 15–45° away. With a pitched pinhole camera an image row is a plane, not
a cone: off-axis pixels in one row sit at a **higher world elevation** than the centre
pixels, so the comparison was between different parts of the sky.

## Root cause

`sun_dip` binned by image row. At a 70° field and a +3° pitch the away columns in the
horizon rows are several degrees higher in the sky, and the atmosphere/ground-hemisphere
gradient there is ~20 luma — read as a "dip".

## Fix

Bin both the near (±10° of the sun's bearing) and away (15–45°) pixels by **world
elevation** (0.25° bands) and compare each near pixel's darkest value with the median of
the away pixels in the same band. The painted sky then reads 6.1–7.1 luma (its sun's own
soft edge, inside the 10 bound) on both sky models. A second run added the sun's own
elevation: only bands within 1.5° of it count, because an isolated cumulus 6° above a
0.4° sun is legitimately dark and read a 48-luma "dip" — the black sun hides in the
disc's own rows, not anywhere in the sky.

## Lesson

A screen-space row is not a world-space coordinate. Any probe that compares "near" and
"away" pixels across a perspective frame must bin by the world quantity it cares about
(elevation, distance, bearing), or it measures the camera's projection. The first
positive control (a synthetic black disc) passed because the disc and the band were in
the same rows there; the real camera exposed the difference.
