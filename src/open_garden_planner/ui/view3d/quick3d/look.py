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

What is truth is not in either mapping: the key light's DIRECTION comes from the
``SunState`` the pipeline sends (``Quick3DSink.set_sun``), and at night from the
look's stated moon (``Quick3DHost._apply_light`` — the one place that aims it).

``NEUTRAL_DAY`` (re-exported) is what a host shows before anyone hands it a
look; the scene file's defaults are its mapping, pinned by a test.
"""

from __future__ import annotations

from typing import Final

from open_garden_planner.core.scene3d.look import NEUTRAL_DAY, LookSpec, SkySpec

__all__ = ["COLOR_PROPERTIES", "LINEAR_COLOR_PROPERTIES", "NEUTRAL_DAY", "LookSpec", "SkySpec",
           "engine_hex", "engine_linear", "engine_srgb", "scene_properties", "sky_longitude",
           "sky_properties"]

#: The look properties of ``Garden.qml`` that are colours given as ``#rrggbb`` …
COLOR_PROPERTIES: Final = frozenset({"sunColor", "meadowColor"})
#: … and the ones the look derives in LINEAR light: handed over as the sRGB-space
#: triple the engine's own linearisation turns back into that value (``engine_srgb``).
LINEAR_COLOR_PROPERTIES: Final = frozenset({"fogColor", "skyColor", "fillColor"})

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
