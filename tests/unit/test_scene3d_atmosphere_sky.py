"""The atmosphere sky as data (Phase 17 L7, #391): the sky models, the sun direction
in the skymaterial example's atmosphere coordinates, and the inputs of
``qml/AtmosphereSky.qml``. GPU-less: the engine's answer is the render tier's
(``tests/integration/test_view3d_looks_render.py``)."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.app.settings import AppSettings
from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.scene3d.atmosphere_lut import (
    _upper_hemisphere,
    atmosphere_gain,
    painted_radiance,
    sky_view_lut,
    sky_view_radiance,
    sky_view_uv,
    transmittance_lut,
)
from open_garden_planner.core.scene3d.color import srgb_to_linear
from open_garden_planner.core.scene3d.frame import scene_to_engine_vectors, sun_direction_scene
from open_garden_planner.core.scene3d.look import (
    ATMOSPHERE,
    ATMOSPHERE_CLOUD_GAIN,
    ATMOSPHERE_DISC_ENERGY,
    ATMOSPHERE_HAZE_DEG,
    ATMOSPHERE_THIN_CLOUD_LIFT,
    PAINTED,
    SKY_MODELS,
    look_for,
    normalise_sky_model,
    sky_is_stale,
    sky_must_build_now,
)
from open_garden_planner.core.scene3d.weather import living_look
from open_garden_planner.ui.view3d.quick3d.look import (
    ATMOSPHERE_VECTOR_PROPERTIES,
    atmosphere_properties,
    atmosphere_sun_direction,
    cloud_light_gain,
    painted_sky,
)

QML_DIR = (Path(__file__).resolve().parents[2] / "src" / "open_garden_planner" / "ui" / "view3d"
           / "quick3d" / "qml")


def _declared(qml: str) -> dict[str, str]:
    """``property <type> <name>`` of the root SkyMaterial (top level, 4-space indent)."""
    return {name: kind for kind, name in
                re.findall(r"^    property (\w+) (\w+)", qml, flags=re.MULTILINE)}


# ── the models ───────────────────────────────────────────────────────────────


def test_the_models_and_the_default_are_the_decided_ones() -> None:
    assert SKY_MODELS == (PAINTED, ATMOSPHERE) == ("painted", "atmosphere")
    assert AppSettings.VIEW3D_SKY_MODELS == SKY_MODELS, "settings.py writes them out: pinned"
    assert AppSettings.DEFAULT_VIEW3D_SKY_MODEL == PAINTED
    assert AppSettings.KEY_VIEW3D_SKY_MODEL == "view3d/sky_model"
    assert look_for(SunState(40.0, 180.0)).sky.model == PAINTED, "the core never picks one"


@pytest.mark.parametrize(("stored", "expected"), [
    ("painted", PAINTED), ("ATMOSPHERE", ATMOSPHERE), (" atmosphere ", ATMOSPHERE),
    ("volumetric", PAINTED), ("", PAINTED), (3, PAINTED), (None, PAINTED)])
def test_a_stored_model_is_one_of_the_two(stored: object, expected: str) -> None:
    assert normalise_sky_model(stored) == expected


def test_a_change_of_model_is_built_at_once_and_nothing_else_about_it_waits() -> None:
    painted = look_for(SunState(40.0, 180.0)).sky
    atmosphere = replace(painted, model=ATMOSPHERE)
    assert sky_must_build_now(painted, atmosphere) and sky_must_build_now(atmosphere, painted)
    assert sky_is_stale(painted, atmosphere)
    assert not sky_must_build_now(atmosphere, atmosphere)


def test_the_sky_carries_the_moods_twilight() -> None:
    for elevation in (40.0, 2.0, -1.0, -3.0, -5.5, -10.0):
        look = look_for(SunState(elevation, 250.0))
        assert look.sky.twilight == look.mood.twilight
    assert look_for(SunState(40.0, 250.0)).sky.twilight == 0.0
    assert look_for(SunState(-10.0, 250.0)).sky.twilight == 1.0


def test_a_weather_keeps_the_model_and_the_twilight() -> None:
    """``living_look`` replaces the sky's colours and cloud, never what L7 added."""
    for weather in ("clear", "overcast", "rain", "snow"):
        look = living_look(SunState(-3.0, 260.0), "high", weather)
        assert look.sky.twilight == look.mood.twilight and look.sky.model == PAINTED


# ── the sun, in the example's atmosphere coordinates ─────────────────────────


@pytest.mark.parametrize("elevation", [-6.0, 0.0, 12.0, 35.0, 89.0])
@pytest.mark.parametrize("azimuth", [0.0, 90.0, 135.0, 180.0, 270.0, 333.0])
def test_the_shader_turns_the_direction_back_into_the_solar_position(elevation: float,
                                                                      azimuth: float) -> None:
    """``atmosphere.frag``: ``sunDirWorld = (−s.x, s.z, −s.y)`` must be the engine-frame
    direction at the sun — the solar position through the ONE scene → engine map."""
    sky = replace(look_for(SunState(max(elevation, 0.6), azimuth)).sky,
                  sun_elevation_deg=elevation, sun_azimuth_deg=azimuth)
    s = atmosphere_sun_direction(sky)
    world = (-s[0], s[2], -s[1])
    expected = scene_to_engine_vectors(np.asarray(sun_direction_scene(elevation, azimuth)))
    assert world == pytest.approx(tuple(expected), abs=1e-12)
    assert math.hypot(*s) == pytest.approx(1.0)
    # the example's own convention, from a light that TRAVELS away from the sun
    forward = -np.asarray(expected)
    assert s == pytest.approx((forward[0], forward[2], -forward[1]), abs=1e-12)
    # the LUT reads z as up: the sun's elevation is asin(s.z)
    assert math.degrees(math.asin(s[2])) == pytest.approx(elevation, abs=1e-9)


def test_a_southern_sun_lies_where_the_lut_expects_it() -> None:
    """A worked case: noon in the south at 60° — engine (0, sin 60°, +cos 60°)
    (z = −North), so atmosphere (−E, N, up) = (0, −cos 60°, sin 60°)."""
    sky = look_for(SunState(60.0, 180.0)).sky
    assert atmosphere_sun_direction(sky) == pytest.approx((0.0, -0.5, math.sqrt(3) / 2), abs=1e-12)


# ── the inputs of AtmosphereSky.qml ──────────────────────────────────────────


def test_every_input_is_a_declared_property_of_the_qml_with_its_type() -> None:
    declared = _declared((QML_DIR / "AtmosphereSky.qml").read_text(encoding="utf-8"))
    inputs = atmosphere_properties(look_for(SunState(40.0, 180.0)).sky)
    assert set(inputs) <= set(declared), set(inputs) - set(declared)
    vectors = {name for name, kind in declared.items() if kind == "vector3d"}
    assert vectors & set(inputs) == ATMOSPHERE_VECTOR_PROPERTIES
    for name, value in inputs.items():
        kind = declared[name]
        if kind == "vector3d":
            assert isinstance(value, tuple) and len(value) == 3, name
        elif kind == "bool":
            assert isinstance(value, bool), name
        else:
            assert kind == "real" and isinstance(value, float), (name, kind)


def test_the_new_uniforms_are_read_by_the_shader() -> None:
    """The app's uniforms in ``atmosphere.frag`` are exactly the app's properties."""
    shader = (QML_DIR / "atmosphere.frag").read_text(encoding="utf-8")
    app_part = shader.split("// Open Garden Planner (Phase 17 L7, #391). Everything above", 1)[1]
    for name in ("paintedTop", "paintedHorizon", "paintedGround", "paintedSun",
                 "paintedSkyEnergy", "paintedGroundEnergy", "paintedGroundCurve",
                 "atmosphereWeight", "hazeDeg", "atmosphereGain", "sunDiscColor",
                 "cloudLightGain", "cloudHueShare"):
        assert re.search(rf"\b{name}\b", app_part), name


def test_by_day_the_atmosphere_shows_its_sun_over_the_painted_sky() -> None:
    sky = look_for(SunState(35.0, 200.0)).sky
    inputs = atmosphere_properties(sky)
    assert inputs["atmosphereWeight"] == 1.0 and inputs["sunAlpha"] == 1.0
    assert inputs["cloudsEnabled"] is False and inputs["cloudCoverage"] == 0.0
    assert inputs["hazeDeg"] == ATMOSPHERE_HAZE_DEG and inputs["cloudLightGain"] == 0.0, "no cloud"
    assert inputs["atmosphereGain"] == pytest.approx(
        atmosphere_gain(atmosphere_sun_direction(sky), painted_sky(sky)))
    for name, colour in (("paintedTop", sky.top), ("paintedHorizon", sky.horizon),
                         ("paintedGround", sky.ground_bottom)):
        assert inputs[name] == pytest.approx(tuple(srgb_to_linear(colour).tolist())), name
    assert inputs["paintedSun"] == pytest.approx(
        tuple((srgb_to_linear(sky.sun_disc) * sky.sun_energy).tolist()))
    assert inputs["sunDiscColor"] == pytest.approx(
        tuple((srgb_to_linear(sky.sun_disc) * sky.sun_energy * ATMOSPHERE_DISC_ENERGY).tolist()))
    assert inputs["paintedSkyEnergy"] == sky.sky_energy
    assert inputs["paintedGroundCurve"] == sky.ground_curve


def test_through_twilight_it_fades_into_the_painted_night_with_no_sun() -> None:
    weights = []
    for elevation in (0.6, 0.0, -1.5, -3.0, -4.5, -6.0, -12.0):
        inputs = atmosphere_properties(look_for(SunState(elevation, 280.0)).sky)
        weights.append(inputs["atmosphereWeight"])
        if elevation < 0.5:
            assert inputs["sunAlpha"] == 0.0, "a set sun draws no disc and no glow"
    assert weights[0] == 1.0 and weights[-1] == 0.0
    assert weights == sorted(weights, reverse=True), "it fades monotonically"


@pytest.mark.parametrize("weather", ["overcast", "rain", "snow"])
def test_the_weathers_cloud_is_the_volumetric_cloud_and_hides_the_disc(weather: str) -> None:
    sky = living_look(SunState(35.0, 200.0), "high", weather).sky
    inputs = atmosphere_properties(sky)
    assert inputs["cloudsEnabled"] is True and inputs["cloudCoverage"] == sky.cloud > 0.0
    assert inputs["sunAlpha"] == pytest.approx(1.0 - (sky.cloud - 0.5) / 0.5), "gone as the deck closes"
    assert inputs["cloudHueShare"] == sky.cloud, "a full cover takes the weather's own grey"


# ── the CPU look-up tables and the gain (core/scene3d/atmosphere_lut.py) ─────


def test_the_sky_view_tables_texels_read_back_where_they_were_made() -> None:
    """``sky_view_uv`` inverts the table's own parameterisation exactly — what the shader
    computes is where the table holds it."""
    size = 128
    centres = (np.arange(size) + 0.5) / size
    v, u = np.meshgrid(centres, centres, indexing="ij")
    azimuth, lat = 2.0 * np.pi * u, v * 2.0 - 1.0
    elevation = lat * lat * np.sign(lat) * np.pi * 0.5
    rays = np.stack((np.cos(elevation) * np.cos(azimuth), np.cos(elevation) * np.sin(azimuth),
                     np.sin(elevation)), axis=-1)
    uv = sky_view_uv(rays)
    assert np.abs(((uv[..., 0] - u + 0.5) % 1.0) - 0.5).max() < 1e-12
    assert np.abs(uv[..., 1] - v).max() < 1e-12


def test_the_transmittance_is_physical() -> None:
    table = transmittance_lut()
    assert table.shape == (128, 128, 4) and not table.flags.writeable
    # 0 where the ray runs through the planet (a sun below a low sample's horizon)
    assert float(table.min()) >= 0.0 and float(table.max()) <= 1.0
    # a sun at the zenith passes more light than one at the horizon; blue less than red
    zenith, horizon = table[0, -1], table[0, 64]
    assert all(zenith > horizon) and zenith[3] < zenith[0]
    # higher up, less air in the way
    assert all(table[-1, 64] > table[0, 64])


def test_the_clear_sky_is_blue_above_and_brightest_toward_the_sun() -> None:
    sun = atmosphere_sun_direction(look_for(SunState(40.0, 180.0)).sky)
    lut = sky_view_lut(sun)
    assert lut.shape == (128, 128, 3) and not lut.flags.writeable
    zenith = sky_view_radiance(np.array([0.0, 0.0, 1.0]), sun)
    assert zenith[2] > zenith[1] > zenith[0] > 0.0, "Rayleigh: a blue zenith"
    near_sun = sky_view_radiance(np.array([sun[0], sun[1], sun[2] + 0.05]), sun)
    away = sky_view_radiance(np.array([-sun[0], -sun[1], sun[2] + 0.05]), sun)
    # the aerosol halo round the sun (1.87x at the app's turbidity 0.5, more at the example's 1)
    assert float(near_sun.sum()) > 1.5 * float(away.sum()), "the aerosol halo round the sun"


@pytest.mark.parametrize("elevation", [60.0, 25.0, 6.0, 1.0, -3.0])
def test_the_gain_gives_the_atmosphere_the_painted_skys_light_on_the_ground(elevation: float) -> None:
    """The gain's DEFINITION: scaled by it, the atmosphere's cosine-weighted luminance
    over the upper hemisphere equals the painted sky's (the light balance of the accepted
    look — measured on the GPU: the lit grass read the same, L7)."""
    sky = look_for(SunState(elevation, 225.0)).sky
    sun, painted = atmosphere_sun_direction(sky), painted_sky(sky)
    gain = atmosphere_gain(sun, painted)
    directions, weights = _upper_hemisphere()
    luma = np.array([0.2126, 0.7152, 0.0722])
    painted_light = float((painted_radiance(directions, painted, sun) @ luma * weights).sum())
    atmosphere_light = float((sky_view_radiance(directions, sun) @ luma * weights).sum())
    assert gain > 0.0
    assert gain * atmosphere_light == pytest.approx(painted_light, rel=1e-9)


def test_the_gain_rises_as_the_sun_sinks() -> None:
    """The physical sky dims about sevenfold from a high sun to a low one, the painted sky
    hardly: the gain is the auto-exposure the accepted look implies."""
    gains = [atmosphere_gain(atmosphere_sun_direction(sky), painted_sky(sky))
             for sky in (look_for(SunState(e, 225.0)).sky for e in (60.0, 30.0, 10.0, 2.0))]
    assert gains == sorted(gains) and gains[-1] > 3.0 * gains[0], gains


def test_the_painted_radiance_is_the_generators_formula() -> None:
    """Spot values of Qt's ``ProceduralSkyTextureData`` arithmetic: the horizon colour at
    the horizon, the top colour high up, the disc's colour in the disc."""
    sky = look_for(SunState(30.0, 180.0)).sky
    painted, sun = painted_sky(sky), atmosphere_sun_direction(sky)
    away = np.array([-sun[0], -sun[1], 0.0])
    away /= np.linalg.norm(away)
    horizon = painted_radiance(away, painted, sun)
    assert horizon == pytest.approx(np.asarray(painted.horizon) * painted.sky_energy, rel=1e-6)
    high = np.array([away[0] * 0.05, away[1] * 0.05, 1.0])
    high /= np.linalg.norm(high)
    assert painted_radiance(high, painted, sun) == pytest.approx(
        np.asarray(painted.top) * painted.sky_energy, rel=0.02)
    assert painted_radiance(np.asarray(sun), painted, sun) == pytest.approx(np.asarray(painted.sun))


@pytest.mark.parametrize("weather", ["overcast", "rain", "snow"])
def test_the_clouds_are_lit_by_the_one_gain_of_the_atmosphere(weather: str) -> None:
    """3D reviews of L7: the clouds' light is ``ATMOSPHERE_CLOUD_GAIN`` x the clear sky's
    gain at the ACTUAL sun — the one gain of the whole atmosphere. A scale of their own at a
    fixed high sun dimmed the deck twice and deepened a bright band at the horizon; what had
    lit a cloudy sunset too brightly under this gain was the deck's forward scattering."""
    for elevation in (60.0, 50.0, 25.0, 8.0, 2.0, 0.6, -2.0, -4.0):
        sky = living_look(SunState(elevation, 225.0), "medium", weather).sky
        painted = painted_sky(sky)
        inputs = atmosphere_properties(sky)
        lift = 1.0 + ATMOSPHERE_THIN_CLOUD_LIFT * (1.0 - sky.cloud) ** 2
        assert inputs["cloudLightGain"] == pytest.approx(
            ATMOSPHERE_CLOUD_GAIN * inputs["atmosphereGain"] * lift)
        assert inputs["cloudLightGain"] == pytest.approx(cloud_light_gain(sky, painted))


def test_separate_clouds_stay_white_and_leave_the_disc_in_their_gaps() -> None:
    """3D review of the owner's Partly cloudy: the gain calibrated on a full deck read as
    dark smoke at cover 0.4 (x 2.5 now, x 1 on a closed deck), and the clouds themselves
    hide the disc, so ``sunAlpha`` must not dim it in the gaps as well."""
    at = SunState(40.0, 200.0)
    partly = atmosphere_properties(living_look(at, "high", "partly_cloudy").sky)
    overcast = atmosphere_properties(living_look(at, "high", "overcast").sky)
    assert partly["cloudCoverage"] == pytest.approx(0.4) and partly["sunAlpha"] == 1.0
    assert overcast["sunAlpha"] == 0.0
    assert partly["cloudLightGain"] == pytest.approx(
        ATMOSPHERE_CLOUD_GAIN * partly["atmosphereGain"] * (1.0 + ATMOSPHERE_THIN_CLOUD_LIFT * 0.36))
    assert overcast["cloudLightGain"] == pytest.approx(ATMOSPHERE_CLOUD_GAIN * overcast["atmosphereGain"])


def test_a_full_cover_diffuses_the_decks_forward_lobe() -> None:
    """3D review of L7: the example's forward lobe ignores the cover, so a full overcast
    was bright toward a low sun — a cloudy sunset near noon's brightness and a band round
    the horizon. A thick deck diffuses: the lobe fades with the cover, as the silver
    lining does."""
    code = (QML_DIR / "atmosphere.frag").read_text(encoding="utf-8")
    assert "float gFwd = c * cloudPhaseG * (1.0 - CLOUD_DIFFUSION * cloudCoverage);" in code
    assert "msLight += silver * sunRadiance * (1.0 - cloudCoverage);" in code
    assert re.search(r"const float CLOUD_DIFFUSION = 0\.8;", code)


def test_the_clouds_lose_the_sun_through_civil_twilight() -> None:
    """3D review of L7: the example clamps the sun's slant at the horizon, so its deck kept
    the horizon sun's light down to -6 deg and a cloudy dusk brightened. The deck's sunlight
    is faded by the atmosphere's twilight weight (1 by day)."""
    code = (QML_DIR / "atmosphere.frag").read_text(encoding="utf-8")
    assert "sunTint * sunAtten * SUN_RADIANCE_SCALE * atmosphereWeight;" in code
