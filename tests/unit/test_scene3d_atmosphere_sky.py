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
    EARTH_ATMOSPHERE,
    _balance,
    _upper_hemisphere,
    atmosphere_gain,
    drawn_radiance,
    haze_share,
    painted_gradient,
    painted_radiance,
    sky_profile,
    sky_view_lut,
    sky_view_radiance,
    sky_view_rgba16f,
    sky_view_uv,
    transmittance_lut,
)
from open_garden_planner.core.scene3d.color import srgb_to_linear
from open_garden_planner.core.scene3d.frame import scene_to_engine_vectors, sun_direction_scene
from open_garden_planner.core.scene3d.look import (
    ATMOSPHERE,
    ATMOSPHERE_CLOUD_GAIN,
    ATMOSPHERE_DECK_LEVEL,
    ATMOSPHERE_DECK_SUNSET,
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
    deck_anchor,
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
    look — measured on the GPU: the lit grass read the same, L7), both over the sky AS
    DRAWN: through the haze band each counts with the atmosphere's share (#716)."""
    sky = look_for(SunState(elevation, 225.0)).sky
    sun, painted = atmosphere_sun_direction(sky), painted_sky(sky)
    gain = atmosphere_gain(sun, painted)
    directions, weights = _upper_hemisphere()
    share = haze_share(np.arcsin(directions[..., 2])) * weights
    luma = np.array([0.2126, 0.7152, 0.0722])
    painted_light = float((painted_radiance(directions, painted, sun) @ luma * share).sum())
    atmosphere_light = float((sky_view_radiance(directions, sun) @ luma * share).sum())
    assert gain > 0.0
    assert gain * atmosphere_light == pytest.approx(painted_light, rel=1e-9)
    # the haze band is about 1 % of the light: the drawn sky's gain stays within 1.5 % of
    # the bare ratio of L7 (measured: 0.9 % at a 6° sun, the most)
    bare = (float((painted_radiance(directions, painted, sun) @ luma * weights).sum())
            / float((sky_view_radiance(directions, sun) @ luma * weights).sum()))
    assert gain == pytest.approx(bare, rel=0.015)


# ── the profile: the gain per elevation (#716) ───────────────────────────────

#: Sun elevations of the profile's gates: noon, golden hour, sunset, the setting sun and
#: twilight.
PROFILE_SUNS = (60.0, 15.0, 6.0, 2.0, 0.5, -3.0)
_LUMA = np.array([0.2126, 0.7152, 0.0722])


def _ring(elevation_deg: float, azimuth_rad: np.ndarray) -> np.ndarray:
    el = math.radians(elevation_deg)
    return np.stack((np.cos(el) * np.cos(azimuth_rad), np.cos(el) * np.sin(azimuth_rad),
                     np.full_like(azimuth_rad, math.sin(el))), axis=-1)


def _sky(elevation: float, weather: str = "clear") -> tuple:
    look = (look_for(SunState(elevation, 300.0), "medium") if weather == "clear"
            else living_look(SunState(elevation, 300.0), "medium", weather))
    return look, atmosphere_sun_direction(look.sky), painted_sky(look.sky)


@pytest.mark.parametrize("weather", ["clear", "partly_cloudy", "overcast"])
@pytest.mark.parametrize("elevation", PROFILE_SUNS)
def test_every_ring_of_the_drawn_atmosphere_is_as_bright_as_the_painted_gradient(
        elevation: float, weather: str) -> None:
    """#716: one gain for the whole sky left the atmosphere's 6-15° band 1.4-1.8x the
    painted sky and its zenith 0.5-0.8x. Per elevation, the drawn atmosphere's mean over
    the azimuth is the painted sky's GRADIENT (its sun left out: its glow spread round a
    ring drew a bright ring at the sun's elevation) times one glow factor."""
    _look, sun, painted = _sky(elevation, weather)
    _gain, glow = _balance(sun, painted, EARTH_ATMOSPHERE)
    assert 1.0 <= glow < 1.06, glow
    azimuth = np.radians(np.arange(0.0, 360.0, 1.0) + 0.5)
    for ring_elevation in (7.0, 12.0, 25.0, 45.0, 70.0, 88.0):
        directions = _ring(ring_elevation, azimuth)
        drawn = float((drawn_radiance(directions, sun, painted) @ _LUMA).mean())
        target = glow * float(painted_gradient(math.radians(ring_elevation), painted) @ _LUMA)
        assert drawn == pytest.approx(target, rel=0.004), ring_elevation
    profile = sky_profile(sun, painted)
    assert profile.shape == (128,) and not profile.flags.writeable
    assert np.all(np.isfinite(profile)) and profile.min() > 0.0


@pytest.mark.parametrize("elevation", PROFILE_SUNS)
def test_the_sky_as_drawn_sends_the_painted_skys_light_onto_the_ground(elevation: float) -> None:
    """The profile only REDISTRIBUTES the gain: the drawn sky - the painted sky through the
    haze band, the profiled atmosphere above it - sends the painted sky's light onto a
    horizontal surface, and the gain is the profile's mean weighted by the atmosphere's
    own light. (The garden is lit by the painted probe under both models since L7's
    revision, PF-E3D-17; this keeps the sky as bright as the light it stands for.)"""
    _look, sun, painted = _sky(elevation)
    directions, weights = _upper_hemisphere()
    drawn = float((drawn_radiance(directions, sun, painted) @ _LUMA * weights).sum())
    reference = float((painted_radiance(directions, painted, sun) @ _LUMA * weights).sum())
    assert drawn == pytest.approx(reference, rel=0.002)


def _exposed(radiance: np.ndarray, exposure: float) -> np.ndarray:
    """``atmosphere.frag``'s ``skyExposed`` (and the painted skybox's ``qt_exposure``)."""
    return 1.0 - np.exp(-np.asarray(radiance) * exposure)


@pytest.mark.parametrize("elevation", PROFILE_SUNS)
def test_the_clear_sky_never_darkens_on_the_way_down_to_the_horizon(elevation: float) -> None:
    """#716's first gate in the model: away from the sun and across it, the drawn sky's
    luminance never falls from 20° down to 0.5° (before: up to 0.11 of the exposed range
    away from a 6° sun - the bright low band above the painted horizon of the haze band).
    The render tier measures the same on the GPU (``--sky-bands``)."""
    look, sun, painted = _sky(elevation)
    azimuth = math.atan2(sun[1], sun[0])
    elevations = np.arange(20.0, 0.49, -0.25)
    for turn in (90.0, 180.0):
        directions = np.array([_ring(e, np.array([azimuth + math.radians(turn)]))[0]
                               for e in elevations])
        lum = _exposed(drawn_radiance(directions, sun, painted,
                                      weight=1.0 - look.sky.twilight) @ _LUMA,
                       look.mood.probe_exposure)
        assert float(np.max(np.maximum.accumulate(lum) - lum)) < 0.006, turn


@pytest.mark.parametrize("elevation", [15.0, 6.0, 2.0, 0.5])
def test_the_low_band_is_the_painted_skys_brightness(elevation: float) -> None:
    """#716: the 6-15° band every board camera sees read 1.4-1.8x the painted sky. Over the
    azimuth (toward : across : away = 1 : 2 : 1) the exposed band is within 1.15x - the
    issue's bound at sunset - at every low sun."""
    look, sun, painted = _sky(elevation)
    azimuth = math.atan2(sun[1], sun[0])
    drawn = reference = 0.0
    for turn, weight in ((0.0, 1.0), (90.0, 2.0), (180.0, 1.0)):
        for band in np.arange(6.0, 15.01, 0.5):
            direction = _ring(band, np.array([azimuth + math.radians(turn)]))
            drawn += weight * float(_exposed(drawn_radiance(direction, sun, painted) @ _LUMA,
                                             look.mood.probe_exposure)[0])
            reference += weight * float(_exposed(painted_radiance(direction, painted, sun) @ _LUMA,
                                                 look.mood.probe_exposure)[0])
    assert 0.85 < drawn / reference <= 1.15


def test_the_table_carries_the_profile_in_its_alpha() -> None:
    """The profile rides in the sky-view table's alpha (one value per row); without a
    painted sky the alpha is 1, as the example's provider wrote it."""
    _look, sun, painted = _sky(6.0)
    plain = np.frombuffer(sky_view_rgba16f(sun), dtype="<f2").reshape(128, 128, 4)
    shaped = np.frombuffer(sky_view_rgba16f(sun, painted), dtype="<f2").reshape(128, 128, 4)
    assert np.array_equal(plain[..., :3], shaped[..., :3])
    assert np.all(plain[..., 3] == 1.0)
    assert np.allclose(shaped[..., 3], sky_profile(sun, painted)[:, None].astype(np.float16))
    # a weather changes the profile at the same sun: the table must be refilled for it
    _overcast_look, same_sun, grey = _sky(6.0, "overcast")
    assert same_sun == sun and not np.allclose(sky_profile(sun, grey), sky_profile(sun, painted))


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
            ATMOSPHERE_CLOUD_GAIN * inputs["atmosphereGain"] * lift * deck_anchor(sky))
        assert inputs["cloudLightGain"] == pytest.approx(cloud_light_gain(sky, painted))


def test_a_deck_takes_its_anchor_and_scattered_clouds_do_not() -> None:
    """#719: nothing tied the deck's level to the painted horizon it meets at the haze band
    (11-14 luma under it by day, 37-45 at sunset). Measured in the frame: by day one LEVEL,
    taken as far as the deck is closed (Snow's 0.85 is 0.7 closed); toward sunset a SHAPE
    per sun elevation, interpolated in log space and held beyond its rows, that every deck
    (cloud >= 0.5, the overcast mood's boundary) takes in full. Partly cloudy's 0.4 takes
    neither: its clouds keep the light the owner accepted."""
    shape = dict(ATMOSPHERE_DECK_SUNSET)
    elevations = [elevation for elevation, _factor in ATMOSPHERE_DECK_SUNSET]
    assert elevations == sorted(elevations) and all(factor > 0.0 for factor in shape.values())
    assert shape[max(elevations)] == 1.0, "by day the shape is 1: the level alone"
    at = SunState(40.0, 200.0)
    assert deck_anchor(living_look(at, "high", "partly_cloudy").sky) == 1.0
    assert deck_anchor(look_for(at).sky) == 1.0
    overcast = living_look(at, "high", "overcast").sky
    assert deck_anchor(overcast) == pytest.approx(ATMOSPHERE_DECK_LEVEL), "a full deck by day"
    snow = living_look(at, "high", "snow").sky
    closed = (snow.cloud - 0.5) / 0.5
    assert closed == pytest.approx(0.7)
    assert deck_anchor(snow) == pytest.approx(ATMOSPHERE_DECK_LEVEL ** closed)
    for row in (0.0, 2.0, -3.0):           # on a row: its factor, in full for both decks
        assert deck_anchor(replace(overcast, sun_elevation_deg=row)) == pytest.approx(
            ATMOSPHERE_DECK_LEVEL * shape[row])
        assert deck_anchor(replace(snow, sun_elevation_deg=row)) == pytest.approx(
            ATMOSPHERE_DECK_LEVEL ** closed * shape[row])
    between = deck_anchor(replace(overcast, sun_elevation_deg=0.25))
    assert between == pytest.approx(ATMOSPHERE_DECK_LEVEL * math.sqrt(shape[0.0] * shape[0.5]))
    assert deck_anchor(replace(overcast, sun_elevation_deg=-12.0)) == pytest.approx(
        ATMOSPHERE_DECK_LEVEL * shape[min(elevations)]), "held below the first row"


def test_a_full_cover_diffuses_the_sun_side_of_the_decks_ambient() -> None:
    """#719: the example lights its clouds' ambient from the clear sky beside the sun, by
    how much each sample faces the sun; at a 0.5° sun that sample is the aerosol glow, and
    a closed deck read 138 / 120 / 102 luma toward / across / away. A thick deck diffuses
    it as it does the forward lobe (``CLOUD_DIFFUSION``): 126 / 120 / 119."""
    code = (QML_DIR / "atmosphere.frag").read_text(encoding="utf-8")
    assert "sunFacing = mix(sunFacing, 0.5, CLOUD_DIFFUSION * cloudCoverage);" in code


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
    assert overcast["cloudLightGain"] == pytest.approx(
        ATMOSPHERE_CLOUD_GAIN * overcast["atmosphereGain"] * ATMOSPHERE_DECK_LEVEL)


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
