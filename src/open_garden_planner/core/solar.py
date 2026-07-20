"""Solar position engine for the Phase 14 sun/shade features (US-E1, #256).

Pure stdlib (math + datetime only) — deliberately Qt-free so it can be
unit-tested in isolation and consumed by both the 2D shadow overlay
(US-E3) and the 3D view's sun light (US-E6) without pulling in any UI.

Implements the NOAA "General Solar Position Calculations" algorithm (the
NOAA solar-calculator spreadsheet formulas, themselves condensed from
Meeus, *Astronomical Algorithms*, ch. 25). Stated accuracy of this
formulation: better than ±0.1 deg in declination and ±0.2 min in the
equation of time for years 1900-2100 — far inside the ±0.5 deg tolerance
that garden shade planning needs (ADR-037).

The math in ``_julian_day`` and ``solar_position`` is copied VERBATIM from
the campaign oracle ``.claude/skills/ogp-3d-sunshade-campaign/scripts/
solar_reference.py`` (self-checked against independent physical facts:
solstice declination, the solstice-noon elevation identity, equation-of-time
extremes, equinox sunrise azimuth). Do not "improve" the constants here —
regenerate the oracle and re-pin ``tests/unit/test_solar.py`` instead.

Conventions (each has a classic sign bug attached — see the test module):
- latitude +north, longitude +EAST (the NOAA spreadsheet itself uses +west);
- ``dt_utc`` must be timezone-aware; it is normalized to UTC internally;
- azimuth is compass bearing, degrees clockwise from true north
  (N=0, E=90, S=180, W=270), computed with the singularity-free atan2 form;
- shadows use the *geometric* elevation; the refracted value is carried for
  completeness (≤0.02° above 30° elevation, ~0.5° at the horizon).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class SolarPosition:
    """Sun position for one instant and site, all angles in degrees."""

    elevation_deg: float
    """Geometric (airless) solar elevation above the horizon."""

    elevation_refracted_deg: float
    """Elevation with the NOAA atmospheric-refraction correction applied."""

    azimuth_deg: float
    """Compass azimuth, degrees clockwise from true NORTH."""

    declination_deg: float
    """Solar declination."""

    eot_minutes: float
    """Equation of time (true minus mean solar time), minutes."""

    hour_angle_deg: float
    """Local hour angle (0 = solar noon, positive = afternoon/west)."""

    @property
    def is_sun_up(self) -> bool:
        """True when the geometric sun center is above the horizon."""
        return self.elevation_deg > 0.0


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


def solar_position(lat_deg: float, lon_deg: float, dt_utc: datetime) -> SolarPosition:
    """NOAA solar position for a UTC instant.

    Args:
        lat_deg: geographic latitude, +north.
        lon_deg: geographic longitude, +east (NOAA spreadsheet uses +west;
                 this function uses the modern +east convention throughout).
        dt_utc:  timezone-aware UTC datetime.

    Raises:
        ValueError: if ``dt_utc`` is naive (no tzinfo).
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

    return SolarPosition(
        elevation_deg=elev,
        elevation_refracted_deg=elev + refr,
        azimuth_deg=azimuth,
        declination_deg=decl,
        eot_minutes=eot,
        hour_angle_deg=hour_angle,
    )
