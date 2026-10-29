## 5. Beauty Board procedure

Fixture: `tests/fixtures/plans/bench_small.ogp` (24×16 m showcase garden, every object class;
regenerate with `scripts/make_bench_plans.py`, never hand-edit). Render through the
**production pipeline** (L1.4) — `snapshot_records` → `SceneSync(production_registry())` →
`Quick3DSink` → a never-shown `Quick3DHost` per frame, lit by `core/scene3d/look.look_for`.
Every shot, mood and horizon frame paints the plan's flat surfaces into its ground with the
product's `GroundBaker` (#586); the IoU and orientation probes stay bare, because their oracles
are the records' own footprints. `tests/fixtures/plans/bench_built.ogp` (`--plan`) holds every
L4 object kind, path style and roof style (ADR-065):

```bash
venv/Scripts/python.exe scripts/render_beauty_board.py --out <dir>   --presets low,high --shots all --iou --orient --horizon --moods --watchdog-s 1800
```

(Linux: prefix `QSG_RHI_BACKEND=opengl QT_QPA_PLATFORM=xcb LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a
-s "-screen 0 1920x1080x24"` and use `venv/bin/python`.) `--plan` takes another plan
(`bench_large.ogp`), `--size` the frame (`960x540` is what the L0 and L1.4 boards were judged
at), `--dusk` the evening from 6° to −7° on the golden-hour camera (must fade monotonically;
sunset no larger a step than a half degree of the day ramp), `--fence` the plan's fences alone
against a 2x-supersampled render (aliasing), `--edge` the plan ground against the meadow along
its edges (a step ≤ 1 luma), `--software` renders on the graphics API's software adapter (WARP: the workspace's
compatibility mode — no sky texture, a plain sky and a flat fill), `--fps-seconds N` shows a
window and measures the frames it PRESENTS per preset with the wind running (and, labelled as
such, the cost of a finished readback), `--list` prints the shots and their suns. `<dir>/board.log`
records every phase (line-flushed; `--watchdog-s` dumps every thread's stack into it and exits
1) and `metrics.json` is rewritten after every phase; on a software rasteriser one frame can
take a minute (`ogp-3d-renderer` §8) — a slow board is not a hung board, read the log. The
script is isolated from the user's settings and stores (`scripts/script_isolation.py`). Exit
codes: 0 ok · 1 watchdog · 2 error · 4 a Qt shader or QML error.

Shots: `golden_hour`, `sunset` (the 6° golden anchor, golden_hour's camera), `noon`, `morning`,
`december_noon`, `night`, `walk` — the spike's dates, times and cameras, so a production board
lies beside an L0 board like for like; add `--presets low,medium,high,ultra --shots golden_hour`
for the preset strip. Every shot row of `metrics.json` carries `sun_elev` / `sun_az`,
`sun_date` = `build_date`, `isolated_dark_px` (luma < 40 inside a lit 8-neighbourhood > 110 —
the sharpening's speckles), `clipped_pct` (a channel ≥ 254), `mean_luma` and `mean_luminance`
(linear light), `sky_builds` and the frame's Qt message counts; the run carries
`shadow_iou` (`--iou`: a box caster at 15° / 35° / 60° in a PERSPECTIVE view with the preset's
cascades), `orientation` and `sky` (`--orient`: north-up NCC; the sky's sun disc read 25° off
centre in the east, south and west), `horizon` (`--horizon`: the row-mean step, dip and ridge
where fog meets sky, per mood and preset), `moods` (`--moods`: one camera and date under the
suns of noon, golden hour, sunset and night — `night_over_noon`), `frame_rate`,
`probe_restore_frame_diff` (the first shot rendered again after the probes; must be 0),
`wind_time` (0: every frame at rest), `builds.<date>.digest` (a digest of (item, height) per
snapshot: June and December must differ; `build_date` is read back from the records rendered)
and, with the flags above, `dusk`, `fence_moire` and `plan_edge`. The instruments are `scripts/board_probes.py` (numpy
only, each with a positive control in `tests/unit/test_board_probes.py`).

The L0 spike's board was the reference for "before" until L1.10 deleted the spike; its
numbers stay in ADR-048's evidence log and its values in `tests/data/l0_spike_reference.json`.
"Before" is now the production board run on the base commit (an archive of it, never a
checkout over the working tree). Always show **before vs after** with the same plan, date, camera and size,
and attach `metrics.json` — a board without its numbers is not evidence.

