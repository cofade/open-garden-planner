## 6. Phase 4 — Shade aggregation: hours-of-sun heatmap — TO BUILD

**Definition:** for a chosen date (or season = set of dates), sample the
daylight period at Δt = 15 min; for each sample with α > 0 compute the
unioned shadow polygon (Phase 3 machinery); accumulate per grid cell:
`sun_minutes[cell] += Δt if cell not in shadow`. Output: heatmap layer
(e.g. <2 h deep shade … >6 h full sun — the horticultural bands; put the
band definitions in `docs/12-glossary/`).

**Performance budget (stated up front):** target garden 30 m × 20 m at 10 cm
cells = 60 000 cells × ~64 daylight samples (Jun 21 Berlin ≈ 16.7 h / 15 min).
Python point-in-polygon per (cell, sample) is ~4 M tests — too slow. Use one
of two vectorized routes (pick in ADR-037):
1. **Rasterize per sample** (recommended): paint the sample's shadow polygons
   into a monochrome `QImage` at grid resolution and accumulate with numpy
   (`QImage` painting is documented thread-safe off the GUI thread, unlike
   QPixmap — but VERIFY with a 2-thread smoke test before relying on it, and
   keep the worker to `QImage` only). 64 fills of a 300×200 image is
   milliseconds.
2. **Pure numpy even-odd rasterization** in the Qt-free core (slower to write,
   fully unit-testable headless; keeps the whole aggregation Qt-free). Numpy
   is already a dependency.

**Threading:** NEVER on the paint path, never blocking the GUI. Run the
aggregation in a `QThread` worker — copy the shape of
`_WeatherFetchWorker` (`ui/widgets/weather_widget.py` line 33) or
`UpdateChecker` (`services/update_checker.py` line 98): worker emits a
`ready(result)` signal; the slot swaps the cached heatmap image and calls
`update()`. Inputs to the worker must be *snapshots* (plain lists of
(polygon, height)) — never live QGraphicsItems across threads (the D1.x
`MainThreadBridge` exists for exactly this reason; for an in-process worker a
plain data snapshot is sufficient).

**Budget gate:** full-day heatmap for the 60 k-cell garden completes < 2 s in
the worker, UI never freezes (scroll the canvas during compute).

### Validation gate P4 — the hand-computable toy case

Single infinite east-west wall, height 200 cm, flat ground, Berlin. Point
50 cm NORTH of the wall. (Northern hemisphere: the sun tracks the *southern*
sky in winter, so the wall's **north** side is the dark side — if your
mental model said "south side", stop and re-derive; the sun never goes north
of the E–W line between the equinoxes' azimuth limits in winter.)

Numbers from the shipped oracle (5-min sampling, geometric elevation —
Appendix):
- **Dec 21: 0 min of direct sun.** Hand argument: winter sun azimuth stays in
  (90°, 270°) (south of the E–W line) all day, so the shadow always has a
  northward component; escaping a 200 cm wall at 50 cm distance would need
  `L·(−cos Az) < 50`, i.e. tan α > 4·|cos'| ⇒ at minimum α ≥ 75.96° for the
  pure-south case — Berlin's winter max is 14.04°. Impossible ⇒ exactly 0.
- **Jun 21: 540 min (9.0 h).** Structure (hourly trace verified): sunrise
  azimuth ≈ 51° (NE) — sun north of the wall line until ~06:00 UTC, and even
  after crossing east the shadow's northward reach stays < 50 cm until
  ~07:30 UTC (high sun, short shadow); blocked through midday
  (reach 73–111 cm); lit again from ~14:40 UTC through NW sunset (az 309°).
  Morning ≈ 4.8 h + evening ≈ 4.2 h ≈ 9 h.

| Command | Expected | If not → |
|---|---|---|
| `python3 .agents/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py \| grep -A3 "toy-case"` | `Dec 21: 0 min`, `Jun 21: 540 min (9.0 h)` | Oracle drift — full re-run. |
| `venv/Scripts/python.exe -m pytest tests/unit/test_shade_aggregation.py -v` | Your production aggregator reproduces 0 min (Dec) and 540 ± 15 min (Jun — one sample of slack for grid discretization) on the same toy scene | Dec ≠ 0 → your shadow polygons leak or azimuth window wrong (Y-flip again — check the direction test first). Jun far off → daylight window or sampling step wrong; print the per-sample lit/shaded trace and compare to the Appendix hourly table. |
| Manual + machine: render the heatmap via `render_canvas_image`, sample the pixel at the toy point | Deep-shade band color (Dec), ~9 h band (Jun) — assert via the RenderMeta pixel formula | Overlay drawn in the wrong frame — same fix path as Phase 3 gate. |

---

