# Case study: a 4K picture's dark band that was blamed on the glow (#733)

## Symptom

The L6 review of PR #729 read the horizon band of the same shot as about 9 luma darker at
3840 x 2160 than at 1920 x 1080, and named Qt's glow: its blur is sized in pixels, so the
same settings reach half as far across a picture twice as tall. The suggested fix was to
raise `ExtendedSceneEnvironment.glowLevel` for pictures above ~1500 px.

## Wrong theories

1. **The glow.** Plausible (glow *is* pixel-sized) and cheap to "fix": adding a glow level
   per doubling of the height did move the band, but by moving the whole picture - the sky
   read +4.45 and the lower garden +2.2 at level Three - and it took several measured
   attempts to see that no level or strength fixed the reported band without breaking
   another.
2. **Fog or texture minification alone.** The far meadow is the obvious suspect for a
   horizon band. Disabling fog changed nothing.

## Key evidence

The discriminator was a matrix of one look input at a time, measured on the family garden at
the sunset anchor (5.9°), 1080p against 4K, with the band defined as 36-44 % of the
picture's height (the far meadow where the ground meets the sky):

| state | band delta (4K - 1080) |
|---|---|
| as shipped | -1.75 mean / -2.82 worst bucket |
| glow off | -1.75 (glow is not the cause) |
| ambient occlusion off | -0.0 (AO is) |
| AO radius scaled by 0.5 at 4K | -0.41 / -0.53 |

The diff image made it unmistakable: the darkened area was not a sky band but the ground
under it, and it vanished with `ambientOcclusion: false`.

## Root cause

Qt Quick 3D samples screen-space ambient occlusion's scene-unit radius on a **pixel** grid.
At twice the height the same `aoDistance` covers twice the pixels, so it occludes more of
the far ground and darkens the band. The capture view shares the view's environment, so the
resolution of the picture, not of the window, decided the look.

## Fix

`look.ao_distance_scale(height)` (Qt-free): 1.0 at 1080p and below, `1080 / height` above,
floored at 0.25. `Quick3DHost.capture` sets the QML `captureAoDistanceScale` for its frame
and restores 1.0; the view itself never changes. The render tier's `picture` scenario pins
the band at <= 1.0, its worst 40-row bucket at <= 1.6 and the sky control at <= 0.5. The
gate was observed failing before the fix (-1.753) and passing after (-0.41).

## Lesson

A review's named cause is a hypothesis, not evidence - especially when it comes with a
one-line fix. Bisect the *inputs* (one look feature at a time), not the suggested constant.
A resolution-dependent look needs a probe that compares two real sizes of one shot and a
diff image before any parameter is tuned; a "fix" that moves three regions at once is a
second look, not a correction. Also: what remains below the band (~3 levels in the garden
from texture minification) is a different phenomenon - say so rather than tuning it away.
