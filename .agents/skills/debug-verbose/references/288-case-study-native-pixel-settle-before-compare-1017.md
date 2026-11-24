# Case study: a native-pixel test compared a partial frame before its paint landed (#1017)

## Symptom
`test_selected_shed_replacement_repaints_in_the_main_window` failed once in a
full `pytest tests/` run (`-n auto`, 20 workers). Alone it passed three times in
a row. The assertion said the partial repaint after swapping a shed for a
glasshouse differed from a full repaint in a narrow vertical strip;
`repeat_noise` was 0. Nothing in the branch touched the 2D canvas, which is why
the test was filed separately from #1004. (The 33 x 222 px strip quoted in some
notes belongs to #1004's report; #1017's run kept no assertion text.)

## Wrong theories
- "The type-change repaint misses a region." Not established for #1017. The
  same file passes repeatedly on the shipped base; for #1017, the only
  confirmed defect is that the driver can compare too early. #1004 remains a
  separate open report with no root cause.
- "Pixel stability proves the partial frame is complete." False. A region that
  is never painted produces two *identical* stale grabs, so a stability loop
  returns early and would happily bless the missing region.

## Key evidence
The driver waited a fixed 500 ms after the edit's first paint event, then
grabbed the window's backing store. Under 20 workers that first paint can be an
early frame; the type-change rebuild's later paint is still queued. The test
never sees it because it compares immediately after the fixed wait.

## Root cause
"Settled" was a duration, not a state. A fixed delay cannot distinguish a
finished repaint from a queued one on a loaded machine.

## Fix and lesson
`canvas_native_pixels.embedded_shed_repaints` now takes `settled_grab()`: it
grabs until two frames 100 ms apart are pixel-identical (bounded at 3 s) before
comparing the partial frame with the forced full repaint. The settle loop only
waits out a queued paint; it does not prove completeness. **The forced full
repaint taken immediately after is the negative control:** a region the partial
frame never painted stays different from that full repaint even when two
partial grabs agree. The 3 s bound only stops an endlessly animating viewport;
it is not the detector. Lesson: for a pixel oracle, a stability wait and a
forced full repaint are two different controls — use the first to avoid reading
a queued frame, and the second to catch a frame that is stably wrong.

## What this did not fix
`#1004` is a separate, still-open report: the same test fails alone at
`5fbc8620` (today: `move`, diff 4524, bounds [187, 65, 349, 287],
`repeat_noise` 0) and passes 4/4 alone on `0d2d8972` (v1.42.0, includes
PR #1000). No root cause is claimed here, and this change does not close
`#1004`; the test remains its guard.
