# Case study: a meadow "shimmer" that was the instrument's own (#798)

## Symptom

The meadow's new grass texture (#798) had to pass "the far meadow does not shimmer in a
camera move". The board's new `--meadow` phase followed 385-394 fixed ground points 30-150 m
away through ten frames of an orbit (0.5° a frame) and of a low flight, and read the far
meadow's frame-to-frame zigzag (`x[i] - (x[i-1] + x[i+1]) / 2`, the day-lapse instrument of
#799). Family garden, High, 1280 x 720: orbit 0.112 → 0.908 luma RMS, flight 0.069 → 0.364
(flat meadow → grass). Nine times the base looked like a texture that crawls.

## Wrong theories

1. **The grass aliases at a distance, so fade its detail toward the flat mean beyond 20 m.**
   That is the usual cure, and it would have brought the felt table back: the far half of the
   default framing is where the flat-green share was won (79 % → 1.6 %).
2. **Qt Quick 3D has anisotropic filtering, so turn it up.** It has none: a `Texture` in Qt
   6.12 has `magFilter`, `minFilter`, `mipFilter` and `generateMipmaps` and nothing else
   (its meta-object, listed). Trilinear blurs a grazing texture; it does not make it crawl.

## Key evidence

The same PNGs re-measured offline (`tools/reanalyze.py`: the frames are kept, so a probe can
change without a render): the probe read the mean of the 3 x 3 pixels around
`floor(projected x, y)`. As a point's projection crosses a pixel boundary the window jumps a
whole pixel, and on a textured ground that jump is a luma step — on a flat meadow it is
nothing, which is why the base read so low. Reading the box-filtered frame BILINEARLY at the
exact projected position: orbit 0.908 → 0.233, flight 0.364 → 0.134 on the same grass
frames; the flat base 0.112 → 0.094 and 0.069 → 0.027. The remaining 0.2 luma RMS is far
under a code.

## Root cause

The instrument, not the render: a window snapped to whole pixels turns a sub-pixel move of a
textured surface into a frame-to-frame step of its own.

## Fix

`board_probes.track_luma` box-filters the luma and reads it bilinearly at the projected
position (unit test: a still and a smooth ramp read zero zigzag, noise reads it). The render
tier's bound (`tests/integration/test_meadow_render.py`, `MAX_ZIGZAG`) is set on the honest
numbers, and a mutation (the grass without mipmaps) shows that the gate still sees a real
shimmer.

## Lesson

Before acting on a temporal statistic of a textured surface, measure the same frames with a
continuous read: a probe that snaps to pixels has a floor that depends on the texture, so a
flat "before" proves nothing about it. Keep the frames of a sequence so a probe can be fixed
offline.
