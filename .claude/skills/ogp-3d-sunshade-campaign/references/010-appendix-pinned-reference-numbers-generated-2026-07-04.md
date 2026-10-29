## Appendix — Pinned reference numbers (generated 2026-07-04)

Produced by running the shipped oracle in this container
(`python3 .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py`,
Python 3.x stdlib, exit code 0). Regenerate after ANY edit to the script and
re-paste; never hand-edit numbers.

Cross-checks passed (10/10), with the arithmetic shown:
- Declination Jun 21 2026 = **+23.4381°**, Dec 21 = **−23.4373°** (known
  axial tilt ±23.44°; deltas −0.002/+0.003).
- Solstice-noon identity `α_max = 90 − |φ − δ|`: Berlin summer
  `90 − |52.52 − 23.44| = 60.92` vs scanned max **60.9181** (Δ 0.0000 vs
  identity); winter `90 − |52.52 + 23.44| = 14.04` vs **14.0427**.
- EoT extremes: 2026-02-11 → **−14.2262 min** (almanac ≈ −14.2);
  2026-11-03 → **+16.4922 min** (almanac ≈ +16.4).
- Equinox: Berlin sunrise azimuth Mar 20 → **90.31°** (due-east fact, Δ 0.31°
  at 1-min sampling); equator max elevation Mar 20 → **89.88°** (near-zenith).

Gate table (pin in `tests/unit/test_solar.py`; oracle tolerance ±0.05°
since production copies the same algorithm; campaign accuracy claim ±0.5°):

```
location                UTC instant             elev elev+refr  azimuth    decl    EoT
Berlin 52.52N 13.405E   2026-06-21 12:00       59.29     59.30   203.74   23.44  -1.82
Berlin 52.52N 13.405E   2026-12-21 12:00       13.08     13.15   193.06  -23.44   1.92
Equator 0N 0E           2026-03-20 12:00       88.14     88.14    91.34   -0.04  -7.43
Equator 0N 0E           2026-06-21 12:00       66.56     66.56     1.05   23.44  -1.82
```

Phase 3 shadow gate (100 cm object, geometric elevation):

```
Berlin Jun 21 12:00Z: elev 59.29°, az 203.74° -> shadow  59.4 cm, canvas dir (dx=+0.403, dy=+0.915)  [dy>0 = NORTH]
Berlin Dec 21 12:00Z: elev 13.08°, az 193.06° -> shadow 430.4 cm, canvas dir (dx=+0.226, dy=+0.974)
```

Worked azimuth→vector example: Az = 203.74°; sin Az = −0.4025,
cos Az = −0.9154; canvas dir (−sin, −cos) = **(+0.4025, +0.9154)**;
Qt-scene dir (−sin, +cos) = (+0.4025, −0.9154).

Phase 4 toy-case gate (200 cm E–W wall, point 50 cm north, Berlin, 5-min
sampling): **Dec 21 = 0 min; Jun 21 = 540 min (9.0 h)**. Hourly structure
(from the verification trace): lit 03:00–07:30 UTC (sun NE→E, shadow reach
< 50 cm until α high enough), shaded 07:30–14:40 (reach 73–111 cm),
lit 14:40–sunset (~19:20, sun W→NW).

---

