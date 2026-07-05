#!/usr/bin/env python3
"""Solar-position reference oracle for the Phase 14 sun/shade campaign.

Pure stdlib (math + datetime only) — runs in any Python 3.11+ without PyQt6.
Implements the NOAA "General Solar Position Calculations" algorithm (the
NOAA solar-calculator spreadsheet formulas, themselves condensed from
Meeus, *Astronomical Algorithms*, ch. 25). Stated accuracy of this
formulation: better than ±0.1 deg in declination and ±0.2 min in the
equation of time for years 1900-2100 — far inside the ±0.5 deg tolerance
that garden shade planning needs.

This script has three jobs:
1. SELF-CHECKS  — validate the implementation against independent known
   facts (solstice declination, the solstice-noon elevation identity,
   equation-of-time extremes, equinox sunrise azimuth, equatorial
   near-zenith). Exits non-zero if any check fails.
2. GATE NUMBERS — print the pinned reference numbers that `core/solar.py`
   unit tests and the Phase 3 shadow-length gate must reproduce.
3. WORKED EXAMPLES — azimuth -> canvas-vector conversion and the Phase 4
   wall/shade toy case, so the numbers in SKILL.md are regenerable.

Usage:
    python3 solar_reference.py            # run checks + print all tables
    python3 solar_reference.py --quiet    # checks only (CI-style)

The intended production implementation `src/open_garden_planner/core/solar.py`
should copy `solar_position()` (and its helpers) verbatim — it is already
Qt-free and dependency-free by construction.
"""
from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta

# ---------------------------------------------------------------------------
# NOAA solar position (Meeus-derived). All angles in degrees unless noted.
# ---------------------------------------------------------------------------


def _julian_day(dt_utc: datetime) -> float:
    """Julian Day from a UTC datetime (Meeus ch. 7, valid for Gregorian dates)."""
    year, month = dt_utc.year, dt_utc.month
    day = (
        dt_utc.day
        + dt_utc.hour / 24.0
        + dt_utc.minute / 1440.0
        + dt_utc.second / 86400.0
    )
    if month <= 2:
        year -= 1
        month += 12
    a = year // 100
    b = 2 - a + a // 4
    return int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5


def solar_position(lat_deg: float, lon_deg: float, dt_utc: datetime) -> dict:
    """NOAA solar position for a UTC instant.

    Args:
        lat_deg: geographic latitude, +north.
        lon_deg: geographic longitude, +east (NOAA spreadsheet uses +west;
                 this function uses the modern +east convention throughout).
        dt_utc:  timezone-aware UTC datetime.

    Returns dict with:
        elevation_deg          geometric (airless) solar elevation
        elevation_refracted_deg elevation + NOAA atmospheric-refraction corr.
        azimuth_deg            compass azimuth, degrees clockwise from NORTH
        declination_deg        solar declination
        eot_minutes            equation of time (true - mean solar time), min
        hour_angle_deg         local hour angle (0 = solar noon, + = afternoon)
    """
    if dt_utc.tzinfo is None:
        raise ValueError("dt_utc must be timezone-aware (UTC)")
    dt_utc = dt_utc.astimezone(UTC)

    jd = _julian_day(dt_utc)
    t = (jd - 2451545.0) / 36525.0  # Julian centuries since J2000.0

    # Geometric mean longitude of the sun (deg)
    l0 = (280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360.0
    # Geometric mean anomaly (deg)
    m = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    # Eccentricity of Earth's orbit
    ecc = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    # Equation of center (deg)
    mrad = math.radians(m)
    c = (
        math.sin(mrad) * (1.914602 - t * (0.004817 + 0.000014 * t))
        + math.sin(2 * mrad) * (0.019993 - 0.000101 * t)
        + math.sin(3 * mrad) * 0.000289
    )
    # True and apparent longitude (deg)
    true_long = l0 + c
    omega = 125.04 - 1934.136 * t  # longitude of ascending lunar node
    app_long = true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Mean obliquity of the ecliptic (deg), then corrected for nutation
    eps0 = (
        23.0
        + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    )
    eps = eps0 + 0.00256 * math.cos(math.radians(omega))

    # Solar declination (deg)
    decl = math.degrees(
        math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(app_long)))
    )

    # Equation of time (minutes). y = tan^2(eps/2)
    y = math.tan(math.radians(eps) / 2.0) ** 2
    l0rad = math.radians(l0)
    eot = 4.0 * math.degrees(
        y * math.sin(2 * l0rad)
        - 2.0 * ecc * math.sin(mrad)
        + 4.0 * ecc * y * math.sin(mrad) * math.cos(2 * l0rad)
        - 0.5 * y * y * math.sin(4 * l0rad)
        - 1.25 * ecc * ecc * math.sin(2 * mrad)
    )

    # True solar time (minutes of day). +east longitude ADDS 4 min/deg.
    utc_minutes = dt_utc.hour * 60.0 + dt_utc.minute + dt_utc.second / 60.0
    tst = (utc_minutes + eot + 4.0 * lon_deg) % 1440.0
    hour_angle = tst / 4.0 - 180.0  # deg; 0 at solar noon, + afternoon (west)

    # Elevation
    lat = math.radians(lat_deg)
    dec = math.radians(decl)
    ha = math.radians(hour_angle)
    sin_elev = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(
        ha
    )
    sin_elev = max(-1.0, min(1.0, sin_elev))
    elev = math.degrees(math.asin(sin_elev))

    # Azimuth clockwise from north.
    # atan2 form is singularity-free (avoids the acos formulation's
    # division by cos(elev)): az_from_south = atan2(sin H, cos H sin(lat)
    # - tan(dec) cos(lat)), positive toward west.
    az_south = math.degrees(
        math.atan2(
            math.sin(ha),
            math.cos(ha) * math.sin(lat) - math.tan(dec) * math.cos(lat),
        )
    )
    azimuth = (az_south + 180.0) % 360.0

    # NOAA atmospheric refraction correction (deg), applied to elevation.
    if elev > 85.0:
        refr = 0.0
    else:
        te = math.tan(math.radians(elev))
        if elev > 5.0:
            refr = (58.1 / te - 0.07 / te**3 + 0.000086 / te**5) / 3600.0
        elif elev > -0.575:
            refr = (
                1735.0
                + elev * (-518.2 + elev * (103.4 + elev * (-12.79 + elev * 0.711)))
            ) / 3600.0
        else:
            refr = (-20.774 / te) / 3600.0

    return {
        "elevation_deg": elev,
        "elevation_refracted_deg": elev + refr,
        "azimuth_deg": azimuth,
        "declination_deg": decl,
        "eot_minutes": eot,
        "hour_angle_deg": hour_angle,
    }


# ---------------------------------------------------------------------------
# Shadow geometry (the Phase 3 formulas)
# ---------------------------------------------------------------------------


def shadow_length_cm(height_cm: float, elevation_deg: float) -> float | None:
    """Ground shadow length of a vertical object. None if sun at/below horizon."""
    if elevation_deg <= 0.0:
        return None
    return height_cm / math.tan(math.radians(elevation_deg))


def shadow_direction_canvas(azimuth_deg: float) -> tuple[float, float]:
    """Unit shadow direction in the CANVAS frame (+x = East, +y = North, Y-UP).

    The sun's horizontal direction (unit vector toward the sun's compass
    bearing) is (sin Az, cos Az) in (E, N). The shadow extends OPPOSITE:
        d = (-sin Az, -cos Az)
    In Qt scene coordinates (Y-down) the y component flips sign:
        d_scene = (-sin Az, +cos Az)
    """
    az = math.radians(azimuth_deg)
    return (-math.sin(az), -math.cos(az))


# ---------------------------------------------------------------------------
# Self-checks against independent known facts
# ---------------------------------------------------------------------------

FAILURES: list[str] = []


def check(name: str, value: float, expected: float, tol: float, unit: str) -> None:
    ok = abs(value - expected) <= tol
    status = "PASS" if ok else "FAIL"
    print(
        f"  [{status}] {name}: got {value:+.4f} {unit}, "
        f"expected {expected:+.4f} +/- {tol} {unit} (delta {value - expected:+.4f})"
    )
    if not ok:
        FAILURES.append(name)


def max_elevation_scan(lat: float, lon: float, day_utc: datetime) -> float:
    """Max elevation over the UTC day, minute resolution."""
    best = -90.0
    for minute in range(0, 1440):
        dt = day_utc.replace(hour=0, minute=0, second=0) + timedelta(minutes=minute)
        best = max(best, solar_position(lat, lon, dt)["elevation_deg"])
    return best


def sunrise_azimuth(lat: float, lon: float, day_utc: datetime) -> float:
    """Azimuth at the minute the geometric elevation first crosses 0 upward."""
    prev = None
    for minute in range(0, 1440):
        dt = day_utc.replace(hour=0, minute=0, second=0) + timedelta(minutes=minute)
        pos = solar_position(lat, lon, dt)
        if prev is not None and prev <= 0.0 < pos["elevation_deg"]:
            return pos["azimuth_deg"]
        prev = pos["elevation_deg"]
    raise RuntimeError("no sunrise found")


def direct_sun_minutes_north_of_wall(
    lat: float,
    lon: float,
    day_utc: datetime,
    wall_height_cm: float,
    dist_north_cm: float,
    step_min: int = 5,
) -> int:
    """Phase 4 toy oracle: minutes of direct sun at a point ``dist_north_cm``
    NORTH of an infinitely long east-west wall of ``wall_height_cm``.

    The point is sunlit at an instant iff the sun is up AND either
    (a) the sun is NORTH of the wall's plane (azimuth in (270,360)|(0,90)),
    so the wall casts its shadow southward, or (b) the sun is south but the
    northward run of the shadow, L*(-cos Az), is shorter than the distance.
    """
    minutes = 0
    for minute in range(0, 1440, step_min):
        dt = day_utc.replace(hour=0, minute=0, second=0) + timedelta(minutes=minute)
        pos = solar_position(lat, lon, dt)
        if pos["elevation_deg"] <= 0.0:
            continue
        length = shadow_length_cm(wall_height_cm, pos["elevation_deg"])
        dx, dy = shadow_direction_canvas(pos["azimuth_deg"])  # canvas: +y north
        northward_reach = (length or 0.0) * dy  # >0 when shadow runs north
        if northward_reach < dist_north_cm:
            minutes += step_min
    return minutes


def main() -> int:
    quiet = "--quiet" in sys.argv

    print("=" * 76)
    print("SOLAR REFERENCE ORACLE - NOAA algorithm self-checks")
    print("(script: .claude/skills/ogp-3d-sunshade-campaign/scripts/solar_reference.py)")
    print("=" * 76)

    berlin = (52.52, 13.405)
    jun21 = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    dec21 = datetime(2026, 12, 21, 12, 0, tzinfo=UTC)

    p_jun = solar_position(*berlin, jun21)
    p_dec = solar_position(*berlin, dec21)

    print("\n-- CHECK GROUP 1: solstice declination (known: +/-23.44 deg, the")
    print("   Earth's axial tilt; June solstice 2026 falls on Jun 21) --")
    check("declination 2026-06-21 12:00Z", p_jun["declination_deg"], 23.44, 0.05, "deg")
    check("declination 2026-12-21 12:00Z", p_dec["declination_deg"], -23.44, 0.05, "deg")

    print("\n-- CHECK GROUP 2: solstice NOON elevation identity --")
    print("   At solar noon (hour angle 0) elevation = 90 - |lat - decl| EXACTLY.")
    print("   Berlin summer: 90 - |52.52 - 23.44| = 90 - 29.08 = 60.92 deg")
    print("   Berlin winter: 90 - |52.52 + 23.44| = 90 - 75.96 = 14.04 deg")
    max_jun = max_elevation_scan(*berlin, jun21)
    max_dec = max_elevation_scan(*berlin, dec21)
    ident_jun = 90.0 - abs(berlin[0] - p_jun["declination_deg"])
    ident_dec = 90.0 - abs(berlin[0] - p_dec["declination_deg"])
    check("Berlin max elev Jun 21 vs identity", max_jun, ident_jun, 0.05, "deg")
    check("Berlin max elev Dec 21 vs identity", max_dec, ident_dec, 0.05, "deg")
    check("Berlin max elev Jun 21 vs 60.92", max_jun, 60.92, 0.5, "deg")
    check("Berlin max elev Dec 21 vs 14.04", max_dec, 14.04, 0.5, "deg")

    print("\n-- CHECK GROUP 3: equation-of-time extremes (almanac values:")
    print("   ~ -14.2 min near Feb 11, ~ +16.4 min near Nov 3) --")
    eot_feb = solar_position(0, 0, datetime(2026, 2, 11, 12, 0, tzinfo=UTC))[
        "eot_minutes"
    ]
    eot_nov = solar_position(0, 0, datetime(2026, 11, 3, 12, 0, tzinfo=UTC))[
        "eot_minutes"
    ]
    check("EoT 2026-02-11", eot_feb, -14.2, 0.35, "min")
    check("EoT 2026-11-03", eot_nov, 16.4, 0.35, "min")

    print("\n-- CHECK GROUP 4: equinox facts (2026 March equinox: Mar 20) --")
    print("   Sunrise azimuth ~ due EAST (90 deg) at any latitude; equatorial")
    print("   noon sun within ~2 deg of zenith.")
    mar20 = datetime(2026, 3, 20, 12, 0, tzinfo=UTC)
    sr_az = sunrise_azimuth(*berlin, mar20)
    check("Berlin sunrise azimuth Mar 20", sr_az, 90.0, 1.5, "deg")
    eq_max = max_elevation_scan(0.0, 0.0, mar20)
    check("Equator max elevation Mar 20", eq_max, 90.0, 2.0, "deg")

    print("\n" + "=" * 76)
    print("GATE NUMBERS - pin these in tests/unit/test_solar.py (tolerance")
    print("+/-0.5 deg elevation & azimuth, +/-1 cm shadow length; see SKILL.md)")
    print("=" * 76)

    rows = [
        ("Berlin 52.52N 13.405E", berlin, jun21),
        ("Berlin 52.52N 13.405E", berlin, dec21),
        ("Equator 0N 0E", (0.0, 0.0), mar20),
        ("Equator 0N 0E", (0.0, 0.0), jun21),
    ]
    print(
        f"\n{'location':<24}{'UTC instant':<20}{'elev':>8}{'elev+refr':>10}"
        f"{'azimuth':>9}{'decl':>8}{'EoT':>7}"
    )
    for name, (lat, lon), dt in rows:
        p = solar_position(lat, lon, dt)
        print(
            f"{name:<24}{dt.strftime('%Y-%m-%d %H:%M'):<20}"
            f"{p['elevation_deg']:>8.2f}{p['elevation_refracted_deg']:>10.2f}"
            f"{p['azimuth_deg']:>9.2f}{p['declination_deg']:>8.2f}"
            f"{p['eot_minutes']:>7.2f}"
        )

    print("\n-- Phase 3 shadow-length gate (100 cm object, geometric elevation) --")
    for label, dt in (("Jun 21 12:00Z", jun21), ("Dec 21 12:00Z", dec21)):
        p = solar_position(*berlin, dt)
        length = shadow_length_cm(100.0, p["elevation_deg"])
        dx, dy = shadow_direction_canvas(p["azimuth_deg"])
        print(
            f"  Berlin {label}: elev {p['elevation_deg']:.2f} deg, "
            f"az {p['azimuth_deg']:.2f} deg -> shadow {length:.1f} cm, "
            f"canvas dir (dx={dx:+.3f}, dy={dy:+.3f})  [dy>0 = extends NORTH]"
        )

    print("\n-- Worked azimuth->vector example (SKILL.md Phase 3) --")
    p = solar_position(*berlin, jun21)
    az = p["azimuth_deg"]
    dx, dy = shadow_direction_canvas(az)
    print(f"  Az = {az:.2f} deg (sun just W of due S). sin Az = {math.sin(math.radians(az)):+.4f},")
    print(f"  cos Az = {math.cos(math.radians(az)):+.4f}.")
    print(f"  Canvas (Y-up, +y=North): shadow dir = (-sinAz, -cosAz) = ({dx:+.4f}, {dy:+.4f})")
    print(f"  Qt scene (Y-down):       shadow dir = (-sinAz, +cosAz) = ({dx:+.4f}, {-dy:+.4f})")
    print("  Sanity: northern-hemisphere midday sun is in the SOUTH, so the shadow")
    print("  must extend NORTH: canvas dy > 0. PASS" if dy > 0 else "  FAIL")
    if dy <= 0:
        FAILURES.append("worked example: shadow must extend north at Berlin midday")

    print("\n-- Phase 4 toy-case gate: point 50 cm NORTH of a 200 cm east-west")
    print("   wall, Berlin (5-min sampling, geometric elevation) --")
    for label, dt in (("Dec 21", dec21), ("Jun 21", jun21)):
        mins = direct_sun_minutes_north_of_wall(*berlin, dt, 200.0, 50.0)
        print(f"  {label}: {mins} min of direct sun ({mins / 60.0:.1f} h)")
    print("  Known fact: in winter (N hemisphere) the sun never goes north of the")
    print("  E-W line and never climbs steep enough for a 200 cm wall to cast a")
    print("  <50 cm shadow (needs elev >= 75.96 deg) => Dec 21 MUST be 0 min.")
    dec_mins = direct_sun_minutes_north_of_wall(*berlin, dec21, 200.0, 50.0)
    if dec_mins != 0:
        FAILURES.append("wall toy case: Dec 21 north-of-wall sun minutes != 0")
    print("  Jun 21 sun is north of east/west only shortly after rise / before set")
    print("  (rise az ~51 deg NE, set az ~309 deg NW) => a few hours, not 0, not all day.")

    print("\n" + "=" * 76)
    if FAILURES:
        print(f"RESULT: {len(FAILURES)} CHECK(S) FAILED: {FAILURES}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    if not quiet:
        print("Regenerate SKILL.md appendix by re-running this script and pasting")
        print("the full output (date-stamp it).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
