"""A ``LookSpec`` as the properties of ``qml/Garden.qml`` (L1.4). Engine-free.

The look itself — the rig by sun elevation, the presets, ``look_for`` — is
``core/scene3d/look.py``: plain data, Qt-free. This module is the thin mapping
onto the engine's scene and decides nothing:

- ``scene_properties(look)`` — the root properties ``Quick3DHost.set_look``
  writes, by their QML names. ``COLOR_PROPERTIES`` and
  ``LINEAR_COLOR_PROPERTIES`` say which of them are colours (the host hands those
  over as ``QColor``) — the latter through ``engine_srgb``, the inverse of the
  engine's OWN linearisation of a colour property, which is not the sRGB curve.
- ``sky_properties(sky)`` — the inputs of ONE ``ProceduralSkyTextureData``, by
  ITS property names (``Quick3DHost.set_sky`` hands them to ``buildSky``).
  ``sky_longitude`` is the measured convention: the generator draws its sun at
  compass bearing ``sunLongitude - 90°``.
- ``atmosphere_properties(sky)`` — the inputs of the atmosphere sky (Phase 17 L7,
  ``qml/AtmosphereSky.qml``, a Qt 6.12 ``SkyMaterial``), by ITS property names
  (``Quick3DHost.set_sky`` hands them to ``buildAtmosphere``). Its sun is a DIRECTION
  in the example's atmosphere coordinates (``atmosphere_sun_direction``): the solar
  position through the one scene → engine map, then ``(x, y, z) → (−x, −z, y)`` —
  derived from the shaders, measured by the board's sky probe; the ``+ 90°`` of the
  painted sky is not assumed for it.

What is truth is not in either mapping: the key light's DIRECTION comes from the
``SunState`` the pipeline sends (``Quick3DSink.set_sun``), and at night from the
look's stated moon (``Quick3DHost._apply_light`` — the one place that aims it).

``NEUTRAL_DAY`` (re-exported) is what a host shows before anyone hands it a
look; the scene file's defaults are its mapping, pinned by a test.
"""

from __future__ import annotations

from typing import Final

import numpy as np

from open_garden_planner.core.scene3d.atmosphere_lut import PaintedSky, atmosphere_gain
from open_garden_planner.core.scene3d.color import srgb_to_linear
from open_garden_planner.core.scene3d.frame import scene_to_engine_vectors, sun_direction_scene
from open_garden_planner.core.scene3d.look import (
    ATMOSPHERE_CLOUD_GAIN,
    ATMOSPHERE_DISC_ENERGY,
    ATMOSPHERE_HAZE_DEG,
    ATMOSPHERE_THIN_CLOUD_LIFT,
    NEUTRAL_DAY,
    LookSpec,
    SkySpec,
    sky_phase,
)

__all__ = ["ATMOSPHERE_VECTOR_PROPERTIES", "COLOR_PROPERTIES", "LINEAR_COLOR_PROPERTIES",
           "NEUTRAL_DAY", "PRECIP_KINDS", "VECTOR_PROPERTIES", "LookSpec", "SkySpec",
           "atmosphere_properties", "atmosphere_sun_direction", "engine_hex", "engine_linear",
           "cloud_light_gain", "painted_sky",
           "engine_srgb", "scene_properties", "sky_longitude", "sky_properties"]

#: The look properties of ``Garden.qml`` that are colours given as ``#rrggbb`` …
COLOR_PROPERTIES: Final = frozenset({"sunColor", "meadowColor"})
#: … and the ones the look derives in LINEAR light: handed over as the sRGB-space
#: triple the engine's own linearisation turns back into that value (``engine_srgb``).
LINEAR_COLOR_PROPERTIES: Final = frozenset({"fogColor", "skyColor", "fillColor", "groundTint"})
#: … and the ones that are ``vector3d`` (handed over as ``QVector3D``): the wind's drift
#: (engine frame) and the light an unlit particle is drawn in (linear rgb) — L5.
VECTOR_PROPERTIES: Final = frozenset({"windDrift", "particleLight"})
#: ``AtmosphereSpec.precipitation`` as the scene's ``precipKind``.
PRECIP_KINDS: Final = {"none": 0, "rain": 1, "snow": 2}

# Qt Quick 3D linearises a colour PROPERTY with a polynomial, not with the sRGB curve
# (measured, L1.4: a flat ambient light of colour c on a white box, read from the
# un-tone-mapped top-down frame — c = 0.04 gives 0 where the sRGB curve gives 0.79 of a
# code, c = 0.08 gives 1 where it gives 1.8; from c = 0.3 on the two agree). Its
# coefficients, as in the engine's own colour utility:
_POLY: Final = (0.305306011, 0.682171111, 0.012522878)


def engine_linear(srgb: float) -> float:
    """What the engine makes of one sRGB-space channel value of a colour property."""
    a, b, c = _POLY
    return srgb * (srgb * (srgb * a + b) + c)


def engine_srgb(linear: tuple[float, float, float]) -> tuple[float, float, float]:
    """The sRGB-space colour (0..1 floats) the engine linearises back into ``linear``.

    For a bright colour this is the sRGB encoding to within a code. For a DARK one it
    is not: at linear 0.0015 — a night fog — the sRGB curve says code 5, and the
    engine reads code 5 as 0.0005, three times darker (the night horizon came out as
    a black line, luma 3 where the sky above it was 13). The triple is handed over
    as floats (``QColor.fromRgbF``): 8 bits are steps of a fifth down there.
    """
    out = []
    for value in linear:
        target = min(max(float(value), 0.0), 1.0)
        low, high = 0.0, 1.0
        for _ in range(48):                      # the polynomial is monotone on 0..1
            middle = (low + high) / 2.0
            if engine_linear(middle) < target:
                low = middle
            else:
                high = middle
        out.append((low + high) / 2.0)
    return (out[0], out[1], out[2])


def engine_hex(linear: tuple[float, float, float]) -> str:
    """``engine_srgb`` to 8 bits, as ``#rrggbb`` — what the scene file's defaults say."""
    return "#" + "".join(f"{round(channel * 255):02x}" for channel in engine_srgb(linear))


def scene_properties(look: LookSpec) -> dict[str, object]:
    """``look`` as ``{QML property: value}`` — every look property of the scene file,
    and nothing else (a test pins both directions against the QML). Values are plain:
    numbers, bools, keys, ``#rrggbb`` for ``COLOR_PROPERTIES`` and an sRGB-space float
    triple for ``LINEAR_COLOR_PROPERTIES``."""
    mood, shadow, preset = look.mood, look.shadow, look.preset
    return {
        # the mood
        "sunColor": mood.sun_color,
        "sunBrightness": float(mood.sun_brightness),
        "exposure": float(mood.exposure),
        "probeExposure": float(mood.probe_exposure),
        "fogColor": engine_srgb(look.fog_linear),
        "saturation": float(mood.saturation),
        "contrast": float(mood.contrast),
        # where no sky texture lights the view
        "skyColor": engine_srgb(look.plain_sky_linear),
        "fillColor": engine_srgb(look.fill_linear),
        "meadowColor": look.meadow_albedo,
        # shadows
        "shadowMapQuality": shadow.map_quality,
        "shadowCascades": int(shadow.cascades),
        "softShadows": shadow.soft_shadows,
        "shadowBias": float(shadow.bias),
        "shadowFactor": float(shadow.factor),
        "pcfFactor": float(shadow.pcf_factor),
        # the preset
        "antialiasing": preset.antialiasing,
        "antialiasingQuality": preset.antialiasing_quality,
        "ambientOcclusion": bool(preset.ambient_occlusion),
        "aoSampleRate": int(preset.ao_sample_rate),
        "glow": bool(preset.glow),
        "glowHighQuality": bool(preset.glow_high_quality),
        "reflections": bool(preset.reflections),
        "fog": bool(preset.fog),
        "lawnBlades": bool(preset.lawn_blades),
        "detailNormals": float(preset.detail_normals),
        # wind
        "windStrength": float(look.wind_strength),
        # the living garden (L5, ADR-070)
        **_atmosphere_properties(look),
    }


def _atmosphere_properties(look: LookSpec) -> dict[str, object]:
    """``look.atmosphere`` as the scene's properties. The wind's drift is a direction
    in the GARDEN (east, north): it goes through the frame mapping (``core/scene3d``)
    like every other vector."""
    atmosphere = look.atmosphere
    east, north = atmosphere.wind_drift_scene
    drift = scene_to_engine_vectors(np.array((east, north, 0.0), dtype=np.float64))
    return {
        "wetness": float(atmosphere.wetness),
        "snowCover": float(atmosphere.snow_cover),
        "fogHaze": float(atmosphere.haze),
        "groundTint": engine_srgb(atmosphere.ground_tint_linear),
        "groundRoughness": float(atmosphere.ground_roughness),
        "groundSpecular": float(atmosphere.ground_specular),
        "precipKind": PRECIP_KINDS[atmosphere.precipitation],
        "precipDensity": float(atmosphere.precip_density),
        "windDrift": (float(drift[0]), float(drift[1]), float(drift[2])),
        "particleLight": tuple(float(value) for value in atmosphere.particle_light_linear),
        "leafLife": float(atmosphere.leaves),
        "butterflyLife": float(atmosphere.butterflies),
        "fireflyLife": float(atmosphere.fireflies),
        "lampGlow": float(atmosphere.lamps),
    }


def sky_longitude(azimuth_deg: float) -> float:
    """Compass azimuth (clockwise from north) -> ``ProceduralSkyTextureData.sunLongitude``.

    Measured by the L0 spike's sky probe and again by the L1.4 render tier (the
    disc read 25° off-centre): with longitude L the sky draws its sun at compass
    bearing L - 90°. Re-measure after any Qt upgrade (the render tier does).
    """
    return (azimuth_deg + 90.0) % 360.0


def sky_properties(sky: SkySpec) -> dict[str, object]:
    """``sky`` as the property values of one ``ProceduralSkyTextureData``.

    ``groundHorizonColor`` is the SKY's horizon colour: the ground hemisphere
    shows in a sliver under a far-clipped meadow, and the fog colour there drew a
    dark line (``ogp-3d-renderer`` §4).
    """
    return {
        "sunLatitude": float(sky.sun_elevation_deg),
        "sunLongitude": sky_longitude(sky.sun_azimuth_deg),
        "skyTopColor": sky.top,
        "skyHorizonColor": sky.horizon,
        "groundHorizonColor": sky.horizon,
        "groundBottomColor": sky.ground_bottom,
        "sunColor": sky.sun_disc,
        "skyEnergy": float(sky.sky_energy),
        "groundEnergy": float(sky.ground_energy),
        "groundCurve": float(sky.ground_curve),
        "sunEnergy": float(sky.sun_energy),
    }


#: The atmosphere's inputs that are ``vector3d`` (``QVector3D``): directions and LINEAR
#: colours — a shader uniform, so no colour property's polynomial touches them.
ATMOSPHERE_VECTOR_PROPERTIES: Final = frozenset({
    "sunDirection", "sunDiscColor", "paintedTop", "paintedHorizon", "paintedGround",
    "paintedSun"})


def atmosphere_sun_direction(sky: SkySpec) -> tuple[float, float, float]:
    """Where the atmosphere draws its sun: a unit vector in the skymaterial example's
    atmosphere coordinates.

    The example sets ``sunDirection = (f.x, f.z, −f.y)`` from a light's forward ``f``
    and its shader turns it back into the engine-frame direction AT the sun as
    ``(−s.x, s.z, −s.y)`` (= −f); the sky-view LUT reads the same vector with z up.
    So from the engine-frame vector ``e`` at the sun: ``s = (−e.x, −e.z, e.y)``.
    ``e`` is the solar position (``sky``: elevation floored at the end of civil
    twilight, as the painted sky's) through the one scene → engine map.
    """
    toward = scene_to_engine_vectors(np.asarray(
        sun_direction_scene(sky.sun_elevation_deg, sky.sun_azimuth_deg), dtype=np.float64))
    return (float(-toward[0]), float(-toward[2]), float(toward[1]))


def _linear(hex_colour: str, energy: float = 1.0) -> tuple[float, float, float]:
    red, green, blue = (srgb_to_linear(hex_colour) * float(energy)).tolist()
    return (float(red), float(green), float(blue))


def painted_sky(sky: SkySpec) -> PaintedSky:
    """``sky``'s painted sky in linear light — what ``sky_properties`` hands the
    generator, as the generator linearises it."""
    return PaintedSky(top=_linear(sky.top), horizon=_linear(sky.horizon),
                      ground=_linear(sky.ground_bottom),
                      sun=_linear(sky.sun_disc, sky.sun_energy),
                      sky_energy=float(sky.sky_energy), ground_energy=float(sky.ground_energy),
                      ground_curve=float(sky.ground_curve))


def cloud_light_gain(sky: SkySpec, painted: PaintedSky, sky_gain: float | None = None) -> float:
    """The clouds' light in the painted sky's units: ``ATMOSPHERE_CLOUD_GAIN`` × the clear
    sky's gain at this sun (``sky_gain``: ``atmosphere_gain`` of this sky, when the caller
    has it) — the one gain of the whole atmosphere (3D reviews of L7: a scale of its own,
    at a fixed high sun, dimmed the deck twice and deepened a bright band at the horizon;
    what made the full gain light a cloudy sunset too brightly was the deck's forward
    scattering, which ``atmosphere.frag`` now fades with the cover). The gain was
    calibrated on a full deck: separate clouds take ``ATMOSPHERE_THIN_CLOUD_LIFT`` × (1 −
    cover)² more on top, or Partly cloudy's noon clouds read as dark smoke on a brighter
    sky (3D review of the owner's Partly cloudy: luma 167 on gaps of 207)."""
    gain = atmosphere_gain(atmosphere_sun_direction(sky), painted) if sky_gain is None else sky_gain
    cover = min(max(float(sky.cloud), 0.0), 1.0)
    return (float(ATMOSPHERE_CLOUD_GAIN) * float(gain)
            * (1.0 + float(ATMOSPHERE_THIN_CLOUD_LIFT) * (1.0 - cover) ** 2))


def atmosphere_properties(sky: SkySpec) -> dict[str, object]:
    """``sky`` as the property values of ``AtmosphereSky.qml`` (L7).

    The painted sky beneath is ``sky_properties``' sky, in linear light (its curve
    and sun-glow constants are the generator's defaults, in ``atmosphere.frag``). The
    atmosphere is painted over it by day and fades out through civil twilight
    (``atmosphereWeight`` = 1 − ``sky.twilight``): the night is the painted night. It
    is scaled to the painted sky's light on the ground (``atmosphereGain``:
    ``atmosphere_lut.atmosphere_gain``, from the sky-view table of this sun). Its disc
    shows while the sun is up and as far as the weather's cloud lets it (``sunAlpha``);
    the weather's cloud is the volumetric clouds' coverage.
    """
    day = sky_phase(sky) == "day"
    cloud = min(max(float(sky.cloud), 0.0), 1.0)
    sun = atmosphere_sun_direction(sky)
    painted = painted_sky(sky)
    gain = float(atmosphere_gain(sun, painted))
    return {
        "sunDirection": sun,
        # the clouds themselves hide the disc (atmosphere.frag: cloudT): in the gaps of
        # a partial cover it stays whole, and it goes only as the deck closes
        "sunAlpha": (1.0 - max(cloud - 0.5, 0.0) / 0.5) if day else 0.0,
        "sunDiscColor": _linear(sky.sun_disc, sky.sun_energy * ATMOSPHERE_DISC_ENERGY),
        "paintedTop": painted.top,
        "paintedHorizon": painted.horizon,
        "paintedGround": painted.ground,
        "paintedSun": painted.sun,
        "paintedSkyEnergy": painted.sky_energy,
        "paintedGroundEnergy": painted.ground_energy,
        "paintedGroundCurve": painted.ground_curve,
        "atmosphereWeight": 1.0 - min(max(float(sky.twilight), 0.0), 1.0),
        "hazeDeg": float(ATMOSPHERE_HAZE_DEG),
        "atmosphereGain": gain,
        "cloudLightGain": cloud_light_gain(sky, painted, gain) if cloud > 0.0 else 0.0,
        "cloudHueShare": cloud,
        "cloudsEnabled": cloud > 0.0,
        "cloudCoverage": cloud,
    }
