## 3. Phase 1 — Solar position engine (`core/solar.py`) — TO BUILD

**Contract:** Qt-free module, stdlib `math`/`datetime` only, implementing the
NOAA "General Solar Position Calculations" (Meeus-derived). The shipped
reference implementation is in
`.claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py` —
**copy `solar_position()` and `_julian_day()` from it verbatim**; it passed
all 10 self-checks on 2026-07-04 (Appendix). API:

```python
def solar_position(lat_deg: float, lon_deg: float, dt_utc: datetime) -> SolarPosition:
    """lat +north, lon +EAST (modern convention — NOAA's sheet uses +west!),
    dt_utc timezone-aware. Returns elevation/azimuth/declination/EoT/hour angle."""
```

(Wrap the dict in a frozen dataclass for the production module.)

### The formulas (theory obligation — these ARE the algorithm)

All angles degrees; `T` = Julian centuries since J2000.0 = (JD − 2451545)/36525.

1. **Julian Day** (Meeus ch. 7, Gregorian): with month ≤ 2 → year−1, month+12;
   `A = ⌊y/100⌋`, `B = 2 − A + ⌊A/4⌋`;
   `JD = ⌊365.25(y+4716)⌋ + ⌊30.6001(m+1)⌋ + D + B − 1524.5` (D includes the
   time-of-day fraction).
2. **Geometric mean longitude** `L₀ = 280.46646 + 36000.76983·T + 0.0003032·T²` (mod 360).
3. **Mean anomaly** `M = 357.52911 + 35999.05029·T − 0.0001537·T²`.
4. **Eccentricity** `e = 0.016708634 − 0.000042037·T − 0.0000001267·T²`.
5. **Equation of center**
   `C = sin M·(1.914602 − 0.004817·T − 0.000014·T²) + sin 2M·(0.019993 − 0.000101·T) + 0.000289·sin 3M`.
6. **Apparent longitude** `λ = L₀ + C − 0.00569 − 0.00478·sin Ω`, with
   `Ω = 125.04 − 1934.136·T` (nutation/aberration correction).
7. **Obliquity** `ε₀ = 23°26′21.448″ − 46.815″·T − 0.00059″·T² + 0.001813″·T³`;
   corrected `ε = ε₀ + 0.00256·cos Ω`.
8. **Declination** `δ = asin(sin ε · sin λ)`.
9. **Equation of time (minutes)**, `y = tan²(ε/2)`:
   `EoT = 4·deg[ y·sin 2L₀ − 2e·sin M + 4e·y·sin M·cos 2L₀ − ½y²·sin 4L₀ − 1.25e²·sin 2M ]`.
10. **True solar time (min)** `TST = (UTC_min + EoT + 4·lon_east) mod 1440`
    — **+east longitude ADDS 4 min/deg**; sign errors here are the classic bug.
11. **Hour angle** `H = TST/4 − 180` (0 at solar noon, + afternoon/west).
12. **Elevation** `sin α = sin φ·sin δ + cos φ·cos δ·cos H` (φ = latitude).
13. **Azimuth** (clockwise from north, singularity-free atan2 form):
    `A_south = atan2( sin H, cos H·sin φ − tan δ·cos φ )` (from south, +west);
    `Az = (A_south + 180°) mod 360`. Do NOT use the acos formulation — it
    divides by cos α and blows up near the zenith (equator test case!).
14. **Refraction (optional output)**: NOAA piecewise correction; ≤0.02° above
    30° elevation, ~0.5° at the horizon. Shadows use *geometric* elevation by
    default; expose both. Rationale below.

**Accuracy & tolerance:** this formulation is good to ~±0.1° over 1900–2100
(full NOAA SPA reaches ±0.0003° — irrelevant here). Campaign tolerance is
**±0.5°** for elevation/azimuth: at the worst realistic case (winter Berlin,
α ≈ 13°, 2 m object) a 0.5° elevation error moves a shadow tip ~35 cm on an
~8.6 m shadow (~4%) — well inside gardening decision noise, while ±0.5° is
tight enough to catch every classic implementation bug (EoT sign → minutes ≈
degrees·¼ error; longitude sign → 2×4·13.4 ≈ 107 min of solar time; degrees/
radians mixups → tens of degrees).

### Build steps

1. Branch per `ogp-change-control` (e.g. `feature/US-E1-solar-engine`).
2. Create `src/open_garden_planner/core/solar.py` — copy from the reference
   script; add the dataclass; NO PyQt6 imports.
3. Create `tests/unit/test_solar.py` pinning the Appendix numbers (below) and
   the self-check identities (solstice-noon `α = 90 − |φ − δ|`, EoT extremes,
   equinox sunrise azimuth ≈ 90°).
4. Run the quality battery (pytest/ruff/bandit — commands in Phase 6).

### Gate P1

| Command | Expected | If not → |
|---|---|---|
| `venv/Scripts/python.exe -m pytest tests/unit/test_solar.py -v` (Linux: `venv/bin/python …`) | All pass; pinned values (tolerance ±0.05° vs the oracle, since it's the same algorithm): Berlin 52.52N/13.405E 2026-06-21 12:00 UTC → **elev 59.29°, az 203.74°, δ +23.44°, EoT −1.82 min**; 2026-12-21 12:00 UTC → **elev 13.08°, az 193.06°**; Equator 0/0 2026-03-20 12:00 UTC → **elev 88.14°, az 91.34°** | See branch table below. |
| `grep -rn "PyQt6" src/open_garden_planner/core/solar.py` | no output | Remove the import; solar math never touches Qt (fenced wrong path). |

> **Independent-oracle note (aligns with `ogp-research-frontier` step 1):** the
> pinned rows above share the production algorithm, so ±0.05° "vs the oracle"
> is a self-consistency check, not third-party validation. The oracle earns
> trust through **independent physical-identity cross-checks** it already runs
> (axial tilt, solstice-noon `α = 90 − |φ−δ|`, almanac EoT extremes, equinox
> azimuth). To fully meet the frontier's "precomputed third-party numbers"
> bar, paste **≥1 externally-sourced NOAA/Meeus row per test location** (with a
> provenance comment) alongside the oracle rows.

**Branch: numbers off by >1°** (the classic-bugs checklist, in order of
likelihood):
1. **Equation of time dropped or mis-signed** → symptom: elevation right at
   solar noon but wrong at fixed clock times; azimuth shifted ~¼°·EoT_min.
   Check step 10: `+ EoT`.
2. **Timezone / longitude sign** → symptom: hours-scale error or E/W mirror.
   `dt_utc` must be real UTC (`tzinfo=UTC`, `.astimezone(UTC)` first);
   longitude is +EAST (Berlin +13.405, not −13.405). NOAA's own spreadsheet
   uses +west — if you "corrected" against it, you double-flipped.
3. **Degrees/radians** → symptom: garbage (tens of degrees off). Every `sin`/
   `cos` input must pass through `radians()`; every `asin`/`atan2` output
   through `degrees()`.
4. **Azimuth quadrant** → symptom: elevation perfect, azimuth mirrored around
   180°. Use the atan2 form (step 13), verify the +180 shift with:
   northern-hemisphere solar noon MUST give Az ≈ 180.
5. Only then suspect coefficients — diff your constants against the reference
   script character by character.

---

