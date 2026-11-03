"""The atmosphere sky's look-up tables on the CPU (Phase 17 L7, #391). Qt-free.

A numpy port of the two LUT shaders of Qt's skymaterial example (qtquick3d v6.12.0,
``transmittance.frag`` and ``skytexture.frag``, Copyright (C) 2023 Fernando García
Liñán and (C) 2026 The Qt Company Ltd., MIT; provenance and licence text in
``ui/view3d/quick3d/qml/PROVENANCE.md``): Hillaire's "A Scalable and Production Ready
Sky and Atmosphere Rendering Technique" (2020) with Guimera et al.'s aerosols.

WHY ON THE CPU. The example renders both tables on the GPU, every frame, with
``QuadTextureProvider``. A ``SkyMaterial`` compiles its shader only once every texture
it samples exists (Qt 6.12, ``qssgrenderskymaterial.cpp``: ``skyShaderTexturesReady``),
and a provider's texture exists only after its first render — so the FIRST frame after
the sky appears is white (measured: a shown window shows one white frame; the app's
offscreen frames, which may render only once, are white every time). As texture DATA
from here the table is ready before the first frame, it is computed once per sun
(not every frame), and the sky's colour in any direction is known to Python.

The transmittance table depends on the atmosphere alone (made once); the sky-view
table on the sun too (``sky_view_lut``: about a tenth of a second at 128², float32 as
the shader computes — within 0.75 % of float64 — and remembered for the last suns).

THE GAIN (``atmosphere_gain``). The atmosphere's radiance changes about sevenfold
between a 60° and a 2° sun, the painted sky's — the sky every look of L1–L5 was
accepted on, its light probe balanced against the sun (``ogp-lush-cinematic`` §2) —
hardly. So the atmosphere is scaled, per sky, until the light it sends onto a
horizontal surface (the cosine-weighted luminance of the upper hemisphere: what the
probe's diffuse light gives the ground) equals the painted sky's: the light balance of
the accepted look at every moment, the hue and the structure of the physical sky.
``painted_radiance`` is that sky (Qt's ``ProceduralSkyTextureData`` formula) per
direction.

Coordinates are the example's "atmosphere coordinates": x, y horizontal, z up (the
engine frame's ``(−x, −z, y)``: ``ui/view3d/quick3d/look.atmosphere_sun_direction``).
Spectral: four wavelengths, 630 / 560 / 490 / 430 nm, turned into linear sRGB by the
example's matrix ``M``. Distances in km.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache, lru_cache
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

__all__ = ["LUT_SIZE", "TRANSMITTANCE_SIZE", "Atmosphere", "EARTH_ATMOSPHERE", "PaintedSky",
           "atmosphere_gain", "painted_radiance", "sky_view_lut", "sky_view_radiance",
           "sky_view_rgba16f", "sky_view_uv", "transmittance_lut"]

#: float64 by default; the sky-view loop runs in float32 (as the shader computes)
_F = NDArray[np.floating[Any]]

#: The sky-view and transmittance tables' size (the example's ``lutSize`` /
#: ``lutSizeTransmit``).
LUT_SIZE: Final = 128
TRANSMITTANCE_SIZE: Final = 128
_TRANSMITTANCE_STEPS: Final = 32
_IN_SCATTERING_STEPS: Final = 16

_PI: Final = np.pi
_INV_4PI: Final = 0.25 / np.pi
_RAYLEIGH_PHASE_SCALE: Final = (3.0 / 16.0) / np.pi
_G: Final = 0.8
_EARTH_RADIUS: Final = 6371.0
_ATMOSPHERE_THICKNESS: Final = 100.0
_ATMOSPHERE_RADIUS: Final = _EARTH_RADIUS + _ATMOSPHERE_THICKNESS

# ENABLE_SPECTRAL == 1: the example's constants, per wavelength
_SUN_SPECTRAL_IRRADIANCE: Final = np.array([1.679, 1.828, 1.986, 1.307])
_MOLECULAR_SCATTERING_BASE: Final = np.array([6.605e-3, 1.067e-2, 1.842e-2, 3.156e-2])
_OZONE_ABSORPTION_CROSS_SECTION: Final = np.array([3.472e-21, 3.914e-21, 1.349e-21, 11.03e-23]) * 1e-4
#: The example's spectral → linear sRGB matrix (GLSL ``mat4`` is column-major: these are
#: its COLUMNS; ``rgb = Σ L[i] · column[i]``).
_SPECTRAL_TO_RGB_COLUMNS: Final = np.array([
    [137.672389239975, -8.632904716299537, -1.7181567391931372],
    [32.549094028629234, 91.29801417199785, -12.005406444382531],
    [-38.91428392614275, 34.31665471469816, 29.89044807197628],
    [8.572844237945445, -11.103384660054624, 117.47585277566478],
])


@dataclass(frozen=True, slots=True)
class Atmosphere:
    """The atmosphere's composition (the example's ``AdvancedSky.qml`` defaults)."""

    aerosol_base_density: float = 1.3681e20
    aerosol_background_density: float = 2e6
    aerosol_height_scale: float = 0.73
    ozone_mean_monthly_dobson: float = 347.0
    aerosol_turbidity: float = 1.0
    aerosol_absorption_cross_section: tuple[float, float, float, float] = (
        2.8722e-24, 4.6168e-24, 7.9706e-24, 1.3578e-23)
    aerosol_scattering_cross_section: tuple[float, float, float, float] = (
        1.5908e-22, 1.7711e-22, 2.0942e-22, 2.4033e-22)
    ground_albedo: tuple[float, float, float, float] = (0.3, 0.3, 0.3, 0.3)
    aerosol_type: int = 8
    #: km above the ground the sky is seen from.
    eye_altitude_km: float = 0.05


#: The app's atmosphere: the example's, with half its aerosol haze. At the example's
#: turbidity 1 the noon sky read pale and a low sun's aerosol halo washed a camera facing
#: it to cream; at 0.5 the blue is deeper and the disc stands out of its halo (L7 board
#: moods, 640 x 360; 0.25 differed little more).
EARTH_ATMOSPHERE: Final = Atmosphere(aerosol_turbidity=0.5)


def _ray_sphere(origin: _F, direction: _F, radius: float) -> _F:
    """``raySphereIntersection``: distance to the first hit of a sphere at the origin,
    −1 when none or when the ray points away from it. ``origin`` / ``direction``:
    ``(..., 3)``."""
    b = np.sum(origin * direction, axis=-1)
    c = np.sum(origin * origin, axis=-1) - radius * radius
    d = b * b - c
    root = np.sqrt(np.maximum(d, 0.0))
    t = np.where(d > b * b, -b + root, -b - root)
    return np.where((c > 0.0) & (b > 0.0) | (d < 0.0), -1.0, t)


def _collision(h: _F, atmosphere: Atmosphere) -> tuple[_F, _F, _F]:
    """``getAtmosphereCollisionCoefficients``: per altitude ``h`` (km, any shape) the
    aerosol scattering, the molecular scattering and the total extinction, ``(..., 4)``."""
    h = np.maximum(h, 0.0)[..., None]
    base = atmosphere.aerosol_base_density
    ratio = atmosphere.aerosol_background_density / base
    if atmosphere.aerosol_type == 0:
        density = np.full_like(h, base * (1.0 + ratio))
    else:
        density = base * (np.exp(-h / atmosphere.aerosol_height_scale) + ratio)
    turbidity = atmosphere.aerosol_turbidity
    aerosol_absorption = np.asarray(atmosphere.aerosol_absorption_cross_section) * density * turbidity
    aerosol_scattering = np.asarray(atmosphere.aerosol_scattering_cross_section) * density * turbidity
    hh = h + 1e-4
    t = np.log(hh) - 3.22261
    ozone = 3.78547397e20 * (1.0 / hh) * np.exp(-t * t * 5.55555555)
    molecular_absorption = _OZONE_ABSORPTION_CROSS_SECTION * atmosphere.ozone_mean_monthly_dobson * ozone
    molecular_scattering = _MOLECULAR_SCATTERING_BASE * np.exp(-0.07771971 * np.power(h, 1.16364243))
    extinction = aerosol_absorption + aerosol_scattering + molecular_absorption + molecular_scattering
    return aerosol_scattering, molecular_scattering, extinction


@cache
def transmittance_lut(atmosphere: Atmosphere = EARTH_ATMOSPHERE,
                      size: int = TRANSMITTANCE_SIZE) -> _F:
    """Buffer A (``transmittance.frag``): the transmittance to the top of the atmosphere,
    ``(size, size, 4)`` indexed ``[v, u]``, ``u`` = cos(zenith angle of the sun)·½+½,
    ``v`` = altitude / thickness — texel centres at ``(i + ½) / size``. Read-only."""
    centres = (np.arange(size) + 0.5) / size
    v, u = np.meshgrid(centres, centres, indexing="ij")
    cos_theta = u * 2.0 - 1.0
    sun = np.stack((-np.sqrt(np.maximum(1.0 - cos_theta * cos_theta, 0.0)),
                    np.zeros_like(cos_theta), cos_theta), axis=-1)
    distance = _EARTH_RADIUS + v * (_ATMOSPHERE_RADIUS - _EARTH_RADIUS)
    origin = np.stack((np.zeros_like(v), np.zeros_like(v), distance), axis=-1)
    total = _ray_sphere(origin, sun, _ATMOSPHERE_RADIUS)
    dt = total / _TRANSMITTANCE_STEPS
    optical = np.zeros((size, size, 4))
    for step in range(_TRANSMITTANCE_STEPS):
        t = (step + 0.5) * dt
        point = origin + sun * t[..., None]
        altitude = np.linalg.norm(point, axis=-1) - _EARTH_RADIUS
        optical += _collision(altitude, atmosphere)[2] * dt[..., None]
    table = np.exp(-optical)
    table.setflags(write=False)
    return table


def _lookup(table: _F, cos_theta: _F, normalized_altitude: _F) -> _F:
    """``transmittanceFromLut``: the table bilinearly at (cos θ·½+½, altitude), clamped
    to the edge texels, as a linearly filtered, clamp-to-edge texture samples it."""
    size_v, size_u = table.shape[:2]
    u = np.clip(cos_theta * 0.5 + 0.5, 0.0, 1.0) * size_u - 0.5
    v = np.clip(normalized_altitude, 0.0, 1.0) * size_v - 0.5
    u0 = np.clip(np.floor(u), 0, size_u - 1).astype(np.int64)
    v0 = np.clip(np.floor(v), 0, size_v - 1).astype(np.int64)
    u1, v1 = np.minimum(u0 + 1, size_u - 1), np.minimum(v0 + 1, size_v - 1)
    fu = np.clip(u - u0, 0.0, 1.0)[..., None]
    fv = np.clip(v - v0, 0.0, 1.0)[..., None]
    top = table[v0, u0] * (1.0 - fu) + table[v0, u1] * fu
    bottom = table[v1, u0] * (1.0 - fu) + table[v1, u1] * fu
    result: _F = top * (1.0 - fv) + bottom * fv
    return result


def _interp(column: _F, coordinate: _F) -> _F:
    """One channel-wise 1-D linear look-up along a table's row or column (``(n, 4)``) at
    ``coordinate`` in [0, 1] — what ``_lookup`` does when the other coordinate is fixed
    on a texel centre's row, exactly as the linear filter of a clamp-to-edge texture."""
    size = column.shape[0]
    position = np.clip(np.clip(coordinate, 0.0, 1.0) * size - 0.5, 0.0, size - 1.0)
    low = np.floor(position).astype(np.int64)
    high = np.minimum(low + 1, size - 1)
    fraction = (position - low)[..., None]
    result: _F = column[low] * (1.0 - fraction) + column[high] * fraction
    return result


def _multiple_scattering(table: _F, cos_theta: _F, normalized_height: _F, distance: _F,
                         ground_albedo: _F) -> _F:
    """``getMultipleScattering``: the ground's second-order light and Hillaire's fit.

    Two of its three look-ups vary along one axis only: T(cos θ, 0) along the ground row,
    T(1, h) along the column of cos θ = 1 — 1-D interpolations of the same filter
    (``_lookup`` at v = 0, resp. u = 1, clamps to those texel rows/columns' edge)."""
    omega = 2.0 * _PI * (1.0 - np.sqrt(np.maximum(distance * distance
                                                   - _EARTH_RADIUS * _EARTH_RADIUS, 0.0)) / distance)
    ground_row, zenith_column = _ground_row(table), _zenith_column(table)
    to_ground = _interp(ground_row, cos_theta * 0.5 + 0.5)
    ground_to_sample = zenith_column[0] / _interp(zenith_column, normalized_height)
    ground = (_INV_4PI * omega[..., None] * (ground_albedo / _PI) * to_ground * ground_to_sample
              * cos_theta[..., None])
    fit = 0.02 * np.array([0.217, 0.347, 0.594, 1.0]) * (
        1.0 / (1.0 + 5.0 * np.exp(-17.92 * cos_theta)))[..., None]
    result: _F = fit + ground
    return result


def _ground_row(table: _F) -> _F:
    """T(·, altitude 0): the first texel row — what ``_lookup`` reads at v = 0 (clamped
    to the row's centre)."""
    result: _F = table[0]
    return result


def _zenith_column(table: _F) -> _F:
    """T(cos θ = 1, ·): the last texel column — what ``_lookup`` reads at u = 1."""
    return table[:, -1]


def sky_view_uv(direction: _F) -> _F:
    """``sampleSphericalMap``: where a direction (atmosphere coordinates, z up — or the
    engine frame through ``(−x, −z, y)``) reads the sky-view table: ``(..., 2)``."""
    direction = np.asarray(direction, dtype=np.float64)
    engine_x, engine_y, engine_z = -direction[..., 0], direction[..., 2], -direction[..., 1]
    azimuth = np.arctan2(engine_z, engine_x)
    theta = np.arcsin(np.clip(engine_y, -1.0, 1.0))
    warp = np.sqrt(np.abs(theta) / (_PI * 0.5)) * np.sign(theta) * 0.5 + 0.5
    return np.stack((azimuth / (2.0 * _PI) + 0.5, warp), axis=-1)


@lru_cache(maxsize=8)
def sky_view_lut(sun_direction: tuple[float, float, float],
                 atmosphere: Atmosphere = EARTH_ATMOSPHERE, size: int = LUT_SIZE) -> _F:
    """Buffer B (``skytexture.frag``): the sky's in-scattered radiance, linear sRGB,
    ``(size, size, 3)`` indexed ``[v, u]`` (texel centres at ``(i + ½) / size``):
    ``u`` the azimuth, ``v`` the warped elevation (``sky_view_uv``).

    ``sun_direction``: unit vector at the sun, atmosphere coordinates.
    """
    # float32 through the loop (as the shader computes): about half the time of float64,
    # and the result is an RGBA16F texture
    sun = np.asarray(sun_direction, dtype=np.float32)
    table = transmittance_lut(atmosphere).astype(np.float32)
    albedo = np.asarray(atmosphere.ground_albedo, dtype=np.float32)
    centres = ((np.arange(size) + 0.5) / size).astype(np.float32)
    v, u = np.meshgrid(centres, centres, indexing="ij")
    azimuth = 2.0 * _PI * u
    lat = v * 2.0 - 1.0
    elevation = lat * lat * np.sign(lat) * _PI * 0.5
    ray = np.stack((np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth),
                    np.sin(elevation)), axis=-1)
    eye = _EARTH_RADIUS + atmosphere.eye_altitude_km
    origin = np.broadcast_to(np.array([0.0, 0.0, eye], dtype=np.float32), ray.shape)
    to_top = _ray_sphere(origin, ray, _ATMOSPHERE_RADIUS)
    to_ground = _ray_sphere(origin, ray, _EARTH_RADIUS)
    length = np.where(to_ground < 0.0, to_top, to_ground)   # the eye is inside the atmosphere

    cos_view = np.sum(-ray * sun, axis=-1)
    molecular_phase = _RAYLEIGH_PHASE_SCALE * (1.0 + cos_view * cos_view)
    denominator = 1.0 + _G * _G + 2.0 * _G * cos_view
    aerosol_phase = _INV_4PI * (1.0 - _G * _G) / (denominator * np.sqrt(denominator))
    dt = length / _IN_SCATTERING_STEPS
    radiance = np.zeros((size, size, 4), dtype=np.float32)
    transmittance = np.ones((size, size, 4), dtype=np.float32)
    for step in range(_IN_SCATTERING_STEPS):
        t = (step + 0.5) * dt
        point = origin + ray * t[..., None]
        distance = np.linalg.norm(point, axis=-1)
        zenith = point / distance[..., None]
        altitude = distance - _EARTH_RADIUS
        normalized = altitude / _ATMOSPHERE_THICKNESS
        cos_sun = np.sum(zenith * sun, axis=-1)
        aerosol_scattering, molecular_scattering, extinction = _collision(altitude, atmosphere)
        to_sun = _lookup(table, cos_sun, normalized)
        multiple = _multiple_scattering(table, cos_sun, normalized, distance, albedo)
        source = _SUN_SPECTRAL_IRRADIANCE * (
            molecular_scattering * (molecular_phase[..., None] * to_sun + multiple)
            + aerosol_scattering * (aerosol_phase[..., None] * to_sun + multiple))
        step_transmittance = np.exp(-dt[..., None] * extinction)
        integral = (source - source * step_transmittance) / np.maximum(extinction, 1e-7)
        radiance += transmittance * integral
        transmittance *= step_transmittance
    rgb = radiance.astype(np.float64) @ _SPECTRAL_TO_RGB_COLUMNS
    rgb.setflags(write=False)
    result: _F = rgb
    return result


def sky_view_rgba16f(sun_direction: tuple[float, float, float],
                     atmosphere: Atmosphere = EARTH_ATMOSPHERE, size: int = LUT_SIZE) -> bytes:
    """``sky_view_lut`` as the bytes of an RGBA16F texture (alpha 1), row ``v`` = 0
    first — what the example's provider wrote (``FRAGCOLOR = vec4(rgb, 1.0)``)."""
    rgb = sky_view_lut(sun_direction, atmosphere, size)
    rgba = np.concatenate((rgb, np.ones(rgb.shape[:2] + (1,))), axis=-1)
    return rgba.astype("<f2").tobytes()


# ── the painted sky beneath, and the gain that balances the two ─────────────────

#: Qt's ``ProceduralSkyTextureData`` defaults the app does not set (``atmosphere.frag``
#: carries the same constants).
_PAINTED_SKY_CURVE: Final = 0.09
_PAINTED_SUN_MIN_DEG: Final = 1.0
_PAINTED_SUN_MAX_DEG: Final = 100.0
_PAINTED_SUN_CURVE: Final = 0.05
_REC709: Final = np.array([0.2126, 0.7152, 0.0722])


@dataclass(frozen=True, slots=True)
class PaintedSky:
    """The painted sky's inputs, LINEAR rgb (``look.SkySpec`` through the exact sRGB
    curve, as ``ProceduralSkyTextureData`` linearises its colours)."""

    top: tuple[float, float, float]
    horizon: tuple[float, float, float]
    ground: tuple[float, float, float]
    #: the disc colour × its energy
    sun: tuple[float, float, float]
    sky_energy: float
    ground_energy: float
    ground_curve: float


def _ease(x: _F, c: float) -> _F:
    """Qt's ``ease`` (the generator's and the shader's): one curve per sign of ``c``."""
    x = np.clip(x, 0.0, 1.0)
    if c > 0.0:
        return 1.0 - np.power(1.0 - x, 1.0 / c) if c < 1.0 else np.power(x, c)
    if c < 0.0:
        low = np.power(x * 2.0, -c) * 0.5
        high = (1.0 - np.power(1.0 - (x - 0.5) * 2.0, -c)) * 0.5 + 0.5
        curve: _F = np.where(x < 0.5, low, high)
        return curve
    return np.zeros_like(x)


def painted_radiance(direction: _F, painted: PaintedSky,
                     sun_direction: tuple[float, float, float]) -> _F:
    """The painted sky's linear radiance per direction (atmosphere coordinates, z up):
    ``ProceduralSkyTextureData.generateSkyTexture`` per direction, ``(..., 3)`` — as
    ``atmosphere.frag``'s ``paintedSky()``."""
    direction = np.asarray(direction, dtype=np.float64)
    up = np.clip(direction[..., 2], -1.0, 1.0)
    angle = np.arccos(up)
    top, horizon = np.asarray(painted.top), np.asarray(painted.horizon)
    ground, sun = np.asarray(painted.ground), np.asarray(painted.sun)
    sky_t = _ease(1.0 - angle / (_PI * 0.5), _PAINTED_SKY_CURVE)[..., None]
    sky = (horizon + (top - horizon) * sky_t) * painted.sky_energy
    sun_angle = np.degrees(np.arccos(np.clip(np.sum(direction * np.asarray(sun_direction), axis=-1),
                                             -1.0, 1.0)))
    glow = _ease((sun_angle - _PAINTED_SUN_MIN_DEG) / (_PAINTED_SUN_MAX_DEG - _PAINTED_SUN_MIN_DEG),
                 _PAINTED_SUN_CURVE)[..., None]
    sky = np.where((sun_angle < _PAINTED_SUN_MIN_DEG)[..., None], sun,
                   np.where((sun_angle < _PAINTED_SUN_MAX_DEG)[..., None], sun + (sky - sun) * glow, sky))
    ground_t = _ease((angle - _PI * 0.5) / (_PI * 0.5), painted.ground_curve)[..., None]
    below = (horizon + (ground - horizon) * ground_t) * painted.ground_energy
    return np.where((up < 0.0)[..., None], below, sky)


def sky_view_radiance(direction: _F, sun_direction: tuple[float, float, float],
                      atmosphere: Atmosphere = EARTH_ATMOSPHERE) -> _F:
    """The atmosphere's clear-sky radiance (no gain, no disc, no cloud) per direction,
    read from the sky-view table as the shader reads it (bilinear, clamped)."""
    table = sky_view_lut(sun_direction, atmosphere)
    uv = sky_view_uv(direction)
    size_v, size_u = table.shape[:2]
    u = np.clip(uv[..., 0] * size_u - 0.5, 0.0, size_u - 1.0)
    v = np.clip(uv[..., 1] * size_v - 0.5, 0.0, size_v - 1.0)
    u0, v0 = np.floor(u).astype(np.int64), np.floor(v).astype(np.int64)
    u1, v1 = np.minimum(u0 + 1, size_u - 1), np.minimum(v0 + 1, size_v - 1)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    top = table[v0, u0] * (1.0 - fu) + table[v0, u1] * fu
    bottom = table[v1, u0] * (1.0 - fu) + table[v1, u1] * fu
    result: _F = top * (1.0 - fv) + bottom * fv
    return result


@cache
def _upper_hemisphere(rings: int = 48, sectors: int = 96) -> tuple[_F, _F]:
    """Directions over the upper hemisphere (z up) and their weights cos θ · dω, which
    sum to π: what a horizontal surface receives from a sky of radiance 1."""
    elevation = (np.arange(rings) + 0.5) / rings * (_PI * 0.5)
    azimuth = (np.arange(sectors) + 0.5) / sectors * (2.0 * _PI)
    el, az = np.meshgrid(elevation, azimuth, indexing="ij")
    directions = np.stack((np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)), axis=-1)
    weights = np.sin(el) * np.cos(el) * (_PI * 0.5 / rings) * (2.0 * _PI / sectors)
    directions.setflags(write=False)
    weights.setflags(write=False)
    return directions, weights


def atmosphere_gain(sun_direction: tuple[float, float, float], painted: PaintedSky,
                    atmosphere: Atmosphere = EARTH_ATMOSPHERE) -> float:
    """The scale that gives the atmosphere the painted sky's light on a horizontal
    surface (module docstring): the ratio of their cosine-weighted upper-hemisphere
    luminances. 0 when the atmosphere sends no light at all."""
    directions, weights = _upper_hemisphere()
    painted_light = float((painted_radiance(directions, painted, sun_direction) @ _REC709
                           * weights).sum())
    atmosphere_light = float((sky_view_radiance(directions, sun_direction, atmosphere) @ _REC709
                              * weights).sum())
    return painted_light / atmosphere_light if atmosphere_light > 0.0 else 0.0
