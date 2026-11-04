# Case study: an idle gate that counted the first picture (#389, fixed 2026-11-02)

**Symptom.** The render tier's reduced-motion gate (issue #389: "the idle frame counter stays
at 0") read **2** frames in its quiet stretch under the tier's environment, while the same
driver run by hand read **0** — and the wind's clock stayed at 0 in both.

**Theories entertained (wrong).** (1) "Something animates under reduced motion" — the clock
read `[0.0, 0.0]` across the stretch. (2) "A stray OS expose or activation event" — an event
filter on the view saw no Expose, Activate or Resize event at all in the stretch. (3) "The sky
is rebuilt a second time" — `sky_builds` stayed at 1.

**What instrumentation revealed** (frame counts polled every 20 ms, `UpdateRequest` events
time-stamped, under `render_env`):

```
UPDATES [1.81, 1.85]          <- the scene asks for its frames at once
FRAMES  [(4.81, 2)]           <- ...and they are PRESENTED three seconds later
```

**Root cause.** The settle step waited for "one second without a frame" — reached at 1.4 s,
before the build's first frame (the bench plan's pipelines and the sky's light probe) had been
presented, so the first picture landed inside the "idle" stretch.

**Fix** (`tests/integration/view3d_living_driver.py`, `_settle`): wait for a frame after the
build was requested, then for a quiet second. The gate reads 0; the animated control ~60/s.

**Lesson.** An idle measurement starts after the first frame was PRESENTED, never after a
quiet spell; and the request time is not the frame time (PF-L3D-18).
