## 14. Looks, sky and wind on the engine (L1.4)

Concept: docs §8.29.4; decisions and the evidence table: the ADR-059 addendum "looks, sky and
the animation policy (L1.4)"; tests: docs §8.10.11; lessons: PF-L3D-05. The art-direction values
are `ogp-lush-cinematic` §3. What the ENGINE taught (RTX 4070, Direct3D 11; WARP on the same
machine):

- **A colour property is linearised with a polynomial, not the sRGB curve.** Qt Quick 3D turns a
  `color` property into linear light as `x·(x·(x·0.3053 + 0.6822) + 0.0125)`. From about 0.3 up
  the two agree; for dark colours they do not — sRGB code 5 is 0.0015 by the curve and 0.0005 to
  the engine (a flat ambient light on a white box, read in the un-tone-mapped top-down view).
  A colour you computed in linear light goes in as `QColor.fromRgbF(engine_srgb(linear))`
  (`quick3d/look.py`), as floats. Re-measure after a Qt upgrade.
- **A sky build is a fresh `Texture` with its own `ProceduralSkyTextureData` as its child**,
  every input set at `SkyTextureQualityLow` and the quality raised LAST (one generation). Only the
  Texture is ever destroyed — after the scene shows the new one — so a pair lives and dies
  together (a Texture loses its data when a data object it held earlier dies — the Qt texture trap the ground bake found, PF-L3D-05 item 4). A sequence
  A → B → C with a frame after each, then two frames after the old pairs are gone: the same sky,
  its disc at the solar azimuth (`test_a_sky_rebuilt_three_times_…`).
- **Medium sky quality is enough.** 1024 × 512 float texels (8 MB) against High's 2048 × 1024
  (32 MB): the GUI-thread generation 95 → 215 ms in a round-3 A/B on a quiet machine, every shot's
  mean luma within 0.02, the disc's bearing within 0.07°. In the 2026-10-19 boards (a fresh host
  per frame, other test runs sharing the CPU) one Medium build read 123–301 ms, median 171–201.
- **The light probe is the cost on a software adapter.** On WARP the generation itself is the
  same CPU work (145–340 ms at High), but the first frame after each new sky took 11.1 / 13.2 /
  12.3 s (the probe's filtering; 40–85 s on a CI runner, ADR-048), later frames 4 ms. So no sky
  on the software adapter, ever (`LookController(sky_light=False)`).
- **A retired sky needs no `releaseResources()`.** Twenty sun changes, each a new 8 MB sky and
  probe, frames presented and frames withheld: no growth per change in committed memory or in
  dedicated GPU memory (Theil–Sen over the second half: 0.0 presenting, 0.125 withheld, against
  the pre-registered 1.0 MB per change); the positive control — a `buildSky` that never destroys
  the old Texture — reads 8.2 MB per change. Unlike a destroyed Model (§13), it does not count towards the workspace's
  release policy.
- **A hidden window's `FrameAnimation` keeps running.** With the window hidden and the wind's
  clock running, `windTime` went on advancing (0.59 s of clock in 0.6 s hidden). The animation policy stops the clock when the
  pane hides; "hidden" stops nothing by itself. A stopped clock holds its value (the sway of that
  moment) — rest is `windTime = 0` (`Quick3DHost.rest_wind`).
- **Shadow bias is per backend and preset.** At the spike's bias 5, a lit wall grazed at n·l 0.33
  hatched at high and ultra on Direct3D 11 (pixel noise 1.15 % of its luma); bias 10 there
  (0.18 %, the dither's floor), 15 at low and medium; IoU unchanged.
- **Shadow IoU in a PERSPECTIVE view with the preset's cascades** (box 100 × 100 × 200 cm,
  azimuth 225°, the board's `--iou`; the L0 table above was orthographic without cascades):
  bench_small 960 × 540, GPU — low (1 cascade) 0.921 / 0.985 / 0.974, high (2) 0.976 / 0.986 /
  0.978 at 15° / 35° / 60°. At 640 × 360 the render tier holds all four presets ≥ 0.85 on the GPU
  and on WARP (min 0.919 on both; every cell in the ADR-059 addendum). The weakest cell is always low at 15°: one
  cascade over a 7.5 m shadow.
- **The frame rate to the display is capped by vsync** on a 60 Hz screen: count presented frames
  (`health().frames_presented`) and report a readback's time only as the cost of a finished
  frame, labelled as such. A `grab()` per frame measures the readback, not the frame.
- **MSAA quality is a sample count**: `SceneEnvironment.Medium` 2x, `High` 4x, `VeryHigh` 8x.
  2x does not resolve a picket fence (luma error 12.0 against a 2x-supersampled render; 4x 6.2;
  FXAA 20.0). On the RTX 4070 (bench_large, 1280 × 720, a new frame's readback) FXAA, 2x and 4x
  read 23–28, 23–30 and 24–32 ms — inside the run-to-run spread; on WARP under a shared CPU
  67–152, 96–147 and 107–199 ms. A truth view that must not depend on a preset pins its own
  quality (`Garden.qml`: the top-down view at 4x).
- **An animated view on a software adapter renders continuously**: the wind running on WARP
  drew 139 frames in 4 s at 1,351 % of one core (still: 1 frame, 18 %). Nothing animates in
  compatibility mode.
- **Committed memory grew while the wind ran** (FU-L14-2, L1.4): 2.1–2.6 MB per minute,
  linear over 6 minutes (21,594 frames), dedicated GPU memory flat; 0.8 with the QML engine's
  `collectGarbage()` every 5 s. Not isolated. **Re-measured 2026-10-19 (L1.9): not reproduced** — six alternating 4–5 min soaks, three with this `FrameAnimation` and three with a C++ `NumberAnimation` as the clock: 0.46–2.03 MB a minute overall, second-half slopes 0.0–1.51, the two clocks inside each other's spread. The clock change was reverted. But the final render tier the same day read 2.637 (bound 2.0): intermittent, not gone — `test_the_wind_running_for_two_minutes_leaves_nothing_behind` is a non-strict xfail citing #534.
- **A software adapter presents frames while the GPU's display sleeps**: with the display
  asleep the GPU host presented 0 frames (only readbacks measure there), the WARP host 30–60 in
  5 s. Say which a frame-rate number is.
- **Qt 6.11 exposes no "reduce motion" preference** (`QStyleHints`); the drift guard
  `test_qt_still_exposes_no_motion_preference` fails the day one appears.

