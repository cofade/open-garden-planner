"""The living garden's weather, dew and moods as data (Phase 17 L5, #389, ADR-070).

Truth before beauty: the weather is a LOOK. Nothing here may move the sun or a
shadow, and a clear look outside the morning is ``look_for``'s field for field.
"""

from __future__ import annotations

import math
from dataclasses import fields, replace
from datetime import date

import pytest

from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.scene3d.look import (
    AO_FLAT_BIAS_CM,
    CLEAR_STILL,
    NEUTRAL_DAY,
    PRESETS,
    TWILIGHT_DEG,
    look_for,
    sky_is_stale,
    sky_must_build_now,
    sky_phase,
)
from open_garden_planner.core.scene3d.weather import (
    DEW_GONE_DEG,
    DEW_RISE_DEG,
    MOODS,
    TODAY,
    WEATHER_CHOICES,
    WEATHER_SPECS,
    WEATHERS,
    dew_amount,
    is_evening,
    is_morning,
    living_look,
    mood_of,
    noon_azimuth,
    normalise_weather,
    todays_weather,
    weather_fog,
    weather_from_wmo,
)

#: An afternoon sun (west of the meridian: no dew), a morning one, dusk and night.
AFTERNOON, MORNING = SunState(40.0, 230.0), SunState(4.0, 80.0)
DUSK, NIGHT = SunState(-3.0, 300.0), SunState(-20.0, 0.0)
SUNS = (AFTERNOON, SunState(70.0, 185.0), SunState(10.0, 270.0), MORNING, SunState(0.6, 300.0),
        DUSK, NIGHT)


def sun(elevation: float, azimuth: float = 200.0) -> SunState:
    return SunState(elevation, azimuth)


# ── truth ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.parametrize("at", [s for s in SUNS if not is_morning(s)])
def test_a_clear_look_outside_the_morning_is_look_for_but_its_atmosphere(preset: str,
                                                                         at: SunState) -> None:
    """Every truth gate of L1–L4 reads what it read: only the time of day's life is new."""
    clear = living_look(at, preset, "clear")
    assert replace(clear, atmosphere=CLEAR_STILL) == look_for(at, preset)


@pytest.mark.parametrize("weather", WEATHERS)
@pytest.mark.parametrize("at", SUNS)
def test_no_weather_moves_the_sun_or_the_moon(weather: str, at: SunState) -> None:
    """The key light's direction is not in a look (the pipeline's sun aims it) — and
    the night's moon is the same moon in every weather."""
    look = living_look(at, "high", weather)
    assert look.moon_travel_scene == look_for(at, "high").moon_travel_scene
    assert (look.sky.sun_elevation_deg, look.sky.sun_azimuth_deg) == (
        look_for(at, "high").sky.sun_elevation_deg, look_for(at, "high").sky.sun_azimuth_deg)
    assert look.mood.night == look_for(at, "high").mood.night
    assert look.mood.twilight == look_for(at, "high").mood.twilight


@pytest.mark.parametrize("weather", ["overcast", "rain", "snow"])
@pytest.mark.parametrize("at", SUNS)
def test_a_cloudy_sky_dims_the_key_and_fades_the_shadows_never_the_other_way(
        weather: str, at: SunState) -> None:
    clear, cloudy = living_look(at, "high", "clear"), living_look(at, "high", weather)
    assert cloudy.mood.sun_brightness < clear.mood.sun_brightness or clear.mood.sun_brightness == 0
    assert cloudy.shadow.factor < clear.shadow.factor
    assert cloudy.shadow.pcf_factor >= clear.shadow.pcf_factor
    # the disc fades into the cloud by its COLOUR; its energy stays (energy 0 drew a black
    # sun with a dark halo in Qt's procedural sky: 3D review of L5, round 2)
    assert cloudy.sky.sun_energy == clear.sky.sun_energy
    assert cloudy.sky.cloud == WEATHER_SPECS[weather].cloud > 0.0
    # the preset's cost is never the weather's business
    assert cloudy.preset == clear.preset
    assert (cloudy.shadow.map_quality, cloudy.shadow.cascades, cloudy.shadow.bias) == (
        clear.shadow.map_quality, clear.shadow.cascades, clear.shadow.bias)


def _luminance(hex_color: str) -> float:
    from open_garden_planner.core.scene3d.color import srgb_to_linear

    r, g, b = srgb_to_linear(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@pytest.mark.parametrize("at", SUNS)
def test_an_overcast_horizon_is_as_bright_as_the_clear_one(at: SunState) -> None:
    """A cloudy noon is no dusk, and a cloudy night is no brighter than a clear one."""
    clear, cloudy = living_look(at, "high", "clear"), living_look(at, "high", "overcast")
    assert _luminance(cloudy.sky.horizon) == pytest.approx(_luminance(clear.sky.horizon), rel=0.08)
    assert _luminance(cloudy.sky.top) <= _luminance(cloudy.sky.horizon)


@pytest.mark.parametrize("weather", WEATHERS)
@pytest.mark.parametrize("at", SUNS)
def test_the_fog_meets_the_weathered_horizon(weather: str, at: SunState) -> None:
    look = living_look(at, "high", weather)
    spec = WEATHER_SPECS[weather]
    grey = spec.cloud if spec.grey is None else spec.grey   # the sky's own share of the grey
    assert look.fog_linear == weather_fog(look.sky.horizon, look.mood.probe_exposure,
                                          look.sky.sky_energy, grey, look.mood.twilight)
    assert look.plain_sky_linear == look.fog_linear


def test_the_fog_under_a_cloud_is_calibrated_by_day_and_by_night() -> None:
    """The overcast sky draws its horizon otherwise than the clear one: the clear sky's
    fog drew 4 luma above the overcast noon horizon and 3.6 under its night — a seam in
    every cloudy weather (the 3D review's horizon probe per weather). Clear is untouched."""
    from open_garden_planner.core.scene3d.look import fog_linear

    plain = fog_linear("#a0b4c8", 1.2, 1.0)
    assert weather_fog("#a0b4c8", 1.2, 1.0, 0.0, 0.0) == plain
    assert weather_fog("#a0b4c8", 1.2, 1.0, 0.0, 1.0) == plain
    day = weather_fog("#a0b4c8", 1.2, 1.0, 1.0, 0.0)
    night = weather_fog("#a0b4c8", 1.2, 1.0, 1.0, 1.0)
    assert day[1] == pytest.approx(plain[1] * 0.955)
    assert night[1] == pytest.approx(plain[1] * 1.23)
    half = weather_fog("#a0b4c8", 1.2, 1.0, 0.5, 1.0)
    assert plain[1] < half[1] < night[1], "a thinner layer, a smaller correction"


def test_a_weather_spec_refuses_what_it_cannot_be() -> None:
    from open_garden_planner.core.scene3d.weather import WeatherSpec

    with pytest.raises(ValueError):
        WeatherSpec("hail", 0.5, "hail", 1.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        WeatherSpec("x", 1.5, "none", 1.0, 0.0, 1.0)
    with pytest.raises(ValueError):
        WeatherSpec("x", 0.5, "none", 1.0, 0.0, 0.0)


# ── the sky follows a new weather at once ────────────────────────────────────


@pytest.mark.parametrize("weather", ["overcast", "rain", "snow"])
def test_a_new_weather_builds_its_sky_at_once(weather: str) -> None:
    shown = living_look(AFTERNOON, "high", "clear").sky
    wanted = living_look(AFTERNOON, "high", weather).sky
    assert sky_must_build_now(shown, wanted) and sky_is_stale(shown, wanted)
    assert not sky_must_build_now(wanted, wanted)


def test_an_overcast_day_is_still_day() -> None:
    """The phase is the sun's elevation, not the disc: an overcast sky whose disc has
    faded into the cloud is no twilight (else sunset would not be built at once)."""
    noon = living_look(sun(40.0), "high", "overcast").sky
    assert noon.sun_disc == noon.horizon and sky_phase(noon) == "day"
    assert sky_phase(living_look(sun(-2.0), "high", "overcast").sky) == "twilight"
    assert sky_phase(living_look(sun(-12.0), "high", "overcast").sky) == "night"


# ── the dew ──────────────────────────────────────────────────────────────────


def test_morning_and_evening_are_the_sides_of_the_meridian() -> None:
    assert is_morning(sun(10.0, 90.0)) and not is_evening(sun(10.0, 90.0))
    assert is_evening(sun(10.0, 270.0)) and not is_morning(sun(10.0, 270.0))
    # the southern hemisphere: the sun passes through the north at noon
    assert is_morning(sun(30.0, 40.0)) and is_evening(sun(30.0, 320.0))


@pytest.mark.parametrize(("elevation", "expected"), [
    (TWILIGHT_DEG - 0.1, 0.0), (TWILIGHT_DEG, 0.0), (TWILIGHT_DEG + DEW_RISE_DEG / 2, 0.5),
    (TWILIGHT_DEG + DEW_RISE_DEG, 1.0), (0.0, 1.0), (6.0, 1.0), (12.0, 0.5),
    (DEW_GONE_DEG, 0.0), (40.0, 0.0)])
def test_the_dew_lies_from_dawn_until_the_sun_is_up_a_while(elevation: float, expected: float) -> None:
    assert dew_amount(sun(elevation, 90.0)) == pytest.approx(expected)
    assert dew_amount(sun(elevation, 270.0)) == 0.0          # never in the evening


def test_the_dew_comes_and_goes_without_a_step() -> None:
    """A dawn is no switch: from the end of civil twilight to the sun 18° up the dew
    never moves by more than 0.03 per tenth of a degree (the first cut jumped from 0 to
    1 at -6°: 3D review of L5)."""
    elevations = [TWILIGHT_DEG - 1.0 + 0.1 * i for i in range(260)]
    amounts = [dew_amount(sun(e, 90.0)) for e in elevations]
    assert max(abs(b - a) for a, b in zip(amounts, amounts[1:], strict=False)) <= 0.03
    assert max(amounts) == 1.0


@pytest.mark.parametrize("weather", ["overcast", "rain", "snow"])
def test_a_cloudy_low_sun_keeps_noons_exposure(weather: str) -> None:
    """The low sun's exposure lift makes up for a clear key light that cloud takes away:
    inherited, it made an overcast sunset 98 % as bright as noon (3D review of L5, round
    3). Under cloud the day holds NOON's exposure — all of it under a full cover, the
    share of the cloud under snow's 0.85; towards night the mood's own returns — never
    darker as the sun sinks."""
    def exposure(elevation: float, weather: str) -> float:
        return living_look(sun(elevation, 250.0), "high", weather).mood.exposure

    cloud = WEATHER_SPECS[weather].cloud
    noon, clear_noon = exposure(40.0, weather), exposure(40.0, "clear")
    lift = noon / clear_noon                               # the cloud's own +EV
    for elevation in (12.0, 5.9, 2.0, 0.6):
        clear_stops = math.log2(exposure(elevation, "clear") / clear_noon)
        assert clear_stops > 0.0, "a clear low sun keeps its lift"
        # in stops, like ``mix_rig``: what is left of the clear lift is its (1 - cloud)
        assert math.log2(exposure(elevation, weather) / noon) == pytest.approx(
            clear_stops * (1.0 - cloud)), elevation
    assert exposure(-20.0, weather) == pytest.approx(exposure(-20.0, "clear") * lift)
    evening = [exposure(e, weather) for e in (40.0, 5.9, 0.6, -2.0, -4.0, -6.0, -20.0)]
    assert evening == sorted(evening)


@pytest.mark.parametrize("elevation", [4.0, 10.0, 14.0])
@pytest.mark.parametrize("southern", [False, True], ids=["north", "south"])
def test_a_winter_dew_fades_before_noon_not_at_it(elevation: float, southern: bool) -> None:
    """A winter sun that never reaches 18°: the dew fades over the last 25° of azimuth
    before the PLACE's noon — due south, or due north in the southern hemisphere —
    instead of lying until solar noon and going out at once (3D review of L5, round 2)."""
    noon = noon_azimuth(southern)
    towards = 1.0 if southern else -1.0                # the morning side of that noon

    def dew(before_noon_deg: float) -> float:
        return dew_amount(sun(elevation, (noon + towards * before_noon_deg) % 360.0),
                          southern=southern)

    assert dew(0.1) < 0.01, "no step at the meridian"
    assert 0.0 < dew(12.5) < dew(40.0)


def test_a_summer_dawn_near_due_north_keeps_its_dew() -> None:
    """North of ~60° a summer dawn stands near due north — solar MIDNIGHT's meridian
    there, not noon's: its dew RISES from that meridian over 15° (no step: 3D review of
    L5, round 4) and is not faded as if it were noon (senior review: x0.04 at 1°).
    South of the equator the same bearing IS noon."""
    dawn = sun(-1.0, 20.0)                 # 64° N in June, after the white night's low point
    assert dew_amount(dawn) == pytest.approx(dew_amount(sun(-1.0, 60.0))) == 1.0
    assert dew_amount(sun(-1.0, 3.0)) == pytest.approx(0.2), "a fifth of the way up the rise"
    assert dew_amount(sun(-1.0, 20.0), southern=True) < 0.85, "south: noon's fade"
    assert dew_amount(sun(-1.0, 3.0), southern=True) < 0.15


def test_the_dew_rises_from_solar_midnight_without_a_step() -> None:
    """Tromsø, 21 June: the sun never sets, and the morning begins at solar midnight. The
    dew rises over 15° of azimuth from there — without that ramp it switched 0 -> 1.0 in
    one frame (3D review of L5, round 4) — and still reaches its full sheen."""
    from datetime import UTC, datetime, timedelta

    from open_garden_planner.core.solar import solar_position

    start = datetime(2026, 6, 20, 18, 0, tzinfo=UTC)
    dews = [dew_amount(SunState.from_solar_position(
        solar_position(69.65, 18.96, start + timedelta(minutes=2 * k)))) for k in range(540)]
    steps = [abs(b - a) for a, b in zip(dews, dews[1:], strict=False)]
    assert max(steps) < 0.1, max(steps)
    assert max(dews) == pytest.approx(1.0)


@pytest.mark.parametrize("weather", WEATHERS)
@pytest.mark.parametrize("elevation", [0.4, 0.0, -1.0, -3.0, -6.0, -20.0])
def test_a_set_sun_is_hidden_by_matching_the_sky_never_black(weather: str, elevation: float) -> None:
    """Below 0.5° the sky draws no sun: the disc takes the horizon's colour at the sky's
    own energy, in every weather — energy 0 drew a BLACK disc with a dark halo through
    twilight (3D review of L5, round 4: luma 0 against a 173-182 sky at +0.4°)."""
    sky = living_look(sun(elevation, 300.0), "high", weather).sky
    assert sky.sun_disc == sky.horizon
    assert sky.sun_energy == pytest.approx(sky.sky_energy) and sky.sun_energy > 0.0


def test_no_dew_while_a_drape_lies_on_the_ground() -> None:
    """``dew=False`` (an Analyze drape on the ground): a clear morning is the sun's own
    look, field for field but its atmosphere — the drape's colours read as its legend's."""
    paused, plain = living_look(MORNING, "high", "clear", dew=False), look_for(MORNING, "high")
    assert paused.atmosphere.dew == 0.0 and paused.atmosphere.wetness == 0.0
    assert replace(paused, atmosphere=plain.atmosphere) == plain


@pytest.mark.parametrize("weather", ["rain", "snow"])
def test_no_dew_in_rain_or_snow(weather: str) -> None:
    assert dew_amount(MORNING, weather) == 0.0


def test_the_dew_is_a_mist_and_a_sheen_not_a_new_sky() -> None:
    dewy, plain = living_look(MORNING, "high", "clear"), look_for(MORNING, "high")
    assert dewy.atmosphere.dew == 1.0 and dewy.atmosphere.wetness > 0.0
    assert dewy.atmosphere.haze < 1.0
    assert dewy.sky == plain.sky and dewy.mood.sun_brightness == plain.mood.sun_brightness


# ── the atmosphere ───────────────────────────────────────────────────────────


def test_look_for_is_clear_and_still() -> None:
    assert look_for(AFTERNOON, "high").atmosphere == CLEAR_STILL
    assert NEUTRAL_DAY.atmosphere == CLEAR_STILL


@pytest.mark.parametrize("weather", WEATHERS)
def test_the_precipitation_is_the_weathers(weather: str) -> None:
    atmosphere = living_look(AFTERNOON, "high", weather).atmosphere
    assert atmosphere.precipitation == WEATHER_SPECS[weather].precipitation
    assert (atmosphere.precip_density > 0.0) == (atmosphere.precipitation != "none")
    assert atmosphere.weather == weather


def test_the_wind_is_a_shader_value_that_the_weather_sets() -> None:
    strengths = {w: living_look(AFTERNOON, "high", w).wind_strength for w in WEATHERS}
    assert strengths["clear"] == look_for(AFTERNOON, "high").wind_strength
    assert (strengths["rain"] > strengths["overcast"] > strengths["partly_cloudy"]
            > strengths["clear"] > strengths["snow"])
    drift = living_look(AFTERNOON, "high", "rain").atmosphere.wind_drift_scene
    assert math.hypot(*drift) > 0.0


def test_life_keeps_the_time_of_day() -> None:
    noon = living_look(sun(40.0, 180.0), "high", "clear").atmosphere
    assert noon.butterflies == 1.0 and noon.fireflies == 0.0 and noon.lamps == 0.0
    evening = living_look(sun(-4.0, 300.0), "high", "clear").atmosphere
    assert evening.butterflies == 0.0 and evening.fireflies > 0.5 and evening.lamps > 0.5
    before_dawn = living_look(sun(-4.0, 60.0), "high", "clear").atmosphere
    assert before_dawn.fireflies == 0.0, "fireflies on summer EVENINGS"
    assert before_dawn.lamps > 0.5, "the lights burn until sunrise"
    wet = living_look(sun(40.0, 180.0), "high", "rain").atmosphere
    assert wet.butterflies == 0.0 and wet.fireflies == 0.0
    assert living_look(sun(40.0, 180.0), "high", "snow").atmosphere.leaves == 0.0


@pytest.mark.parametrize("southern", [False, True], ids=["north", "south"])
def test_the_fireflies_fade_towards_solar_midnight(southern: bool) -> None:
    """They go out over the last 25° of azimuth before the sun crosses the meridian below
    the horizon — due north in the northern hemisphere, due south in the southern — not
    all at once (3D review of L5)."""
    midnight = (noon_azimuth(southern) + 180.0) % 360.0

    def fireflies(azimuth: float) -> float:
        return living_look(sun(-12.0, azimuth % 360.0), "high", "clear",
                           southern=southern).atmosphere.fireflies

    towards = -1.0 if midnight == 0.0 else 1.0     # the evening side of that midnight
    far, near = fireflies(midnight + towards * 40.0), fireflies(midnight + towards * 12.5)
    assert far > 0.5 and 0.0 < near < far
    assert fireflies(midnight + towards * 0.5) < 0.05


@pytest.mark.parametrize("weather", WEATHERS)
@pytest.mark.parametrize("at", SUNS)
def test_a_particle_is_lit_like_the_frame(weather: str, at: SunState) -> None:
    """Rain at night is dark, at noon bright: the particles' light follows the key and
    the sky — never brighter at night than by day."""
    def luminance(rgb: tuple[float, float, float]) -> float:
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    light = living_look(at, "high", weather).atmosphere.particle_light_linear
    noon = living_look(sun(60.0), "high", weather).atmosphere.particle_light_linear
    assert min(light) >= 0.0 and luminance(light) <= luminance(noon) + 1e-9


def test_the_ground_takes_one_set_of_values() -> None:
    """The meadow, the bare plan and the tiles take the SAME tint, roughness and
    specular — the plan meets the meadow without a step in every weather."""
    rain = living_look(AFTERNOON, "high", "rain")
    assert rain.atmosphere.ground_roughness < 1.0 < rain.atmosphere.ground_specular + 1.0
    assert rain.atmosphere.ground_tint_linear[0] < 1.0
    assert rain.meadow_albedo != look_for(AFTERNOON, "high").meadow_albedo
    clear = living_look(AFTERNOON, "high", "clear").atmosphere
    assert (clear.ground_tint_linear, clear.ground_roughness, clear.ground_specular) == (
        (1.0, 1.0, 1.0), 1.0, 0.15)


@pytest.mark.parametrize("at", SUNS)
def test_under_cloud_the_occlusion_grows_with_the_light_share_and_clear_keeps_the_spikes(
        at: SunState) -> None:
    """#687: under cloud the sky is the light, and the sky an object hides is what grounds
    it — the ambient occlusion grows with the weather's LIGHT share (strength 55 -> 99,
    reach 14 -> 70, bias 0 -> 21 cm at a full overcast). The bias is what keeps open flat
    ground from occluding itself, near and on the far meadow: below 0.3 of the reach a
    light rim stays above every silhouette (the snow survey's rim). Clear, the dew and an
    Analyze drape keep the spike's values exactly (the truth frames and the clear board
    do not move)."""
    from open_garden_planner.core.scene3d.weather import (
        AO_BIAS_UNDER_CLOUD_CM,
        AO_DISTANCE_UNDER_CLOUD,
        AO_STRENGTH_UNDER_CLOUD,
    )

    assert pytest.approx(99.0) == 55.0 * AO_STRENGTH_UNDER_CLOUD   # Qt's strength tops out at 100
    assert pytest.approx(70.0) == 14.0 * AO_DISTANCE_UNDER_CLOUD
    assert pytest.approx(21.0) == AO_BIAS_UNDER_CLOUD_CM
    assert AO_BIAS_UNDER_CLOUD_CM / (14.0 * AO_DISTANCE_UNDER_CLOUD) >= 0.3, "no rim (reference 14)"
    for look in (living_look(at, "high", "clear"), living_look(at, "high", "clear", dew=False)):
        atmosphere = look.atmosphere
        assert (atmosphere.ao_strength_gain, atmosphere.ao_distance_gain, atmosphere.ao_bias_cm) == (
            1.0, 1.0, AO_FLAT_BIAS_CM)
    for weather in WEATHERS:
        spec = WEATHER_SPECS[weather]
        share = spec.cloud if spec.light is None else spec.light
        atmosphere = living_look(at, "high", weather).atmosphere
        assert atmosphere.ao_strength_gain == pytest.approx(1.0 + (AO_STRENGTH_UNDER_CLOUD - 1.0) * share)
        assert atmosphere.ao_distance_gain == pytest.approx(1.0 + (AO_DISTANCE_UNDER_CLOUD - 1.0) * share)
        assert atmosphere.ao_bias_cm == pytest.approx(max(AO_FLAT_BIAS_CM, AO_BIAS_UNDER_CLOUD_CM * share))
    overcast = living_look(at, "high", "overcast").atmosphere
    assert 55.0 * overcast.ao_strength_gain == pytest.approx(99.0)
    assert 14.0 * overcast.ao_distance_gain == pytest.approx(70.0)
    # partly cloudy keeps its sun, and nearly the clear look's occlusion (light share 0.15)
    partly = living_look(at, "high", "partly_cloudy").atmosphere
    assert 1.0 < partly.ao_strength_gain < 1.15 and partly.ao_bias_cm < 3.5
    # the preset still decides WHETHER there is occlusion (PF-L3D-15): the gains are a look
    assert living_look(at, "low", "overcast").preset.ambient_occlusion is False


def test_the_ground_shaders_snow_is_the_weathers() -> None:
    """Drift guard (senior review of L5): ``ground.frag``'s snow colour is
    ``weather.SNOW_LINEAR`` — the meadow's snow (``apply_weather``) and the plan's tiles
    meet without a step only while they are one colour."""
    import re
    from pathlib import Path

    from open_garden_planner.core.scene3d.weather import SNOW_LINEAR

    qml = Path(__file__).resolve().parents[2] / "src/open_garden_planner/ui/view3d/quick3d/qml"
    found = re.search(r"mix\(albedo, vec3\(([^)]*)\), uSnowCover\)",
                      (qml / "ground.frag").read_text(encoding="utf-8"))
    assert found, "ground.frag mixes its snow in as it did"
    assert tuple(float(v) for v in found.group(1).split(",")) == SNOW_LINEAR


# ── the moods ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("at", "weather", "mood"), [
    (sun(40.0, 200.0), "clear", "day"),
    (sun(8.0, 270.0), "clear", "golden_hour"),
    (MORNING, "clear", "morning_dew"),
    (sun(40.0, 200.0), "overcast", "overcast"),
    (sun(40.0, 200.0), "rain", "rain"),
    (sun(40.0, 200.0), "snow", "snow"),
    (DUSK, "clear", "twilight"),
    (DUSK, "rain", "twilight"),
    (NIGHT, "clear", "night"),
    (NIGHT, "overcast", "night"),
])
def test_the_mood_names_what_the_frame_shows(at: SunState, weather: str, mood: str) -> None:
    assert mood_of(living_look(at, "high", weather), at) == mood


def test_every_mood_of_the_issue_is_reachable() -> None:
    """Issue #389 L5.1: morning dew, golden hour, overcast, night."""
    reached = {mood_of(living_look(at, "high", w), at) for at in SUNS for w in WEATHERS}
    assert {"morning_dew", "golden_hour", "overcast", "night"} <= reached <= set(MOODS)


def test_a_partly_cloudy_day_keeps_its_sun() -> None:
    """L7 (#391): scattered clouds — the sky's cloud is the atmosphere's cover (0.4: the
    clouds read as scattered) while the light and the sky's grey take smaller shares: the
    sun and its shadows stay, between clear and overcast, and the frame is still a day.
    Every other weather has one share for all three (a change there moves accepted looks)."""
    at = sun(40.0, 200.0)
    clear, partly, overcast = (living_look(at, "high", w) for w in ("clear", "partly_cloudy", "overcast"))
    assert partly.sky.cloud == WEATHER_SPECS["partly_cloudy"].cloud == pytest.approx(0.4)
    assert partly.atmosphere.precipitation == "none" and partly.atmosphere.wetness == 0.0
    assert (clear.mood.sun_brightness > partly.mood.sun_brightness
            > overcast.mood.sun_brightness), "the key light between clear and overcast"
    assert clear.shadow.factor > partly.shadow.factor > overcast.shadow.factor
    assert partly.shadow.factor >= 0.85 * clear.shadow.factor, "its shadows stay crisp"
    assert partly.mood.sun_brightness >= 0.85 * clear.mood.sun_brightness, "the sun stays out"
    assert mood_of(partly, at) == "day" and mood_of(overcast, at) == "overcast"
    spec = WEATHER_SPECS["partly_cloudy"]
    assert spec.light == pytest.approx(0.15) and spec.grey == pytest.approx(0.25)
    for name in ("clear", "overcast", "rain", "snow"):
        assert WEATHER_SPECS[name].light is None and WEATHER_SPECS[name].grey is None, name


# ── today's weather (L5.3) ───────────────────────────────────────────────────


@pytest.mark.parametrize(("code", "weather"), [
    (0, "clear"), (1, "clear"), (2, "partly_cloudy"), (3, "overcast"), (45, "overcast"), (48, "overcast"),
    (51, "rain"), (61, "rain"), (67, "rain"), (80, "rain"), (95, "rain"), (99, "rain"),
    (71, "snow"), (77, "snow"), (85, "snow"), (86, "snow"), (4, "clear"), (1000, "clear")])
def test_a_wmo_code_is_a_preset(code: int, weather: str) -> None:
    assert weather_from_wmo(code) == weather


def test_todays_weather_only_while_the_plan_date_is_today() -> None:
    today = date(2026, 11, 2)
    days = (("2026-11-01", 0), ("2026-11-02", 63), ("2026-11-03", 73))
    assert todays_weather(days, today, today) == "rain"
    assert todays_weather(days, date(2026, 11, 3), today) is None, "a forecast says nothing of another day"
    assert todays_weather((), today, today) is None
    assert todays_weather((("2026-11-01", 0),), today, today) is None


def test_a_stored_choice_is_normalised() -> None:
    assert normalise_weather("Rain") == "rain" and normalise_weather(TODAY) == TODAY
    assert normalise_weather("hail") == "clear" and normalise_weather(None) == "clear"
    assert set(WEATHER_CHOICES) == {*WEATHERS, TODAY}


def test_every_field_of_the_atmosphere_has_a_neutral_default() -> None:
    """A look of L1–L4 maps onto the same scene it always did: the atmosphere's
    defaults are clear, dry and still."""
    for field in fields(CLEAR_STILL):
        value = getattr(CLEAR_STILL, field.name)
        if field.name in ("leaves", "butterflies", "fireflies", "lamps", "cloud", "dew",
                          "wetness", "snow_cover", "precip_density", "built_snow"):
            assert value == 0.0, field.name
        if field.name == "ao_bias_cm":   # #805: the flat-surface floor in every look
            assert value == AO_FLAT_BIAS_CM, field.name
        if field.name in ("ao_strength_gain", "ao_distance_gain"):
            assert value == 1.0, field.name


def test_snow_lies_white_on_built_tops_and_nowhere_else() -> None:
    """#687: under the snow weather a built part's TOPS (roof, bed soil, deck, mat) lie under
    a full cover — smooth, they show no grass through it, and at the meadow's 0.75 a
    terracotta roof read pink; every other weather lays none (a snowless frame keeps the
    principled look: Garden.qml swaps the snow material in only above 0)."""
    from open_garden_planner.core.scene3d.weather import BUILT_SNOW_FULL_AT

    assert WEATHER_SPECS["snow"].snow_cover == BUILT_SNOW_FULL_AT
    for at in SUNS:
        assert living_look(at, "high", "snow").atmosphere.built_snow == 1.0
        for weather in ("clear", "partly_cloudy", "overcast", "rain"):
            assert living_look(at, "high", weather).atmosphere.built_snow == 0.0, weather
        assert living_look(at, "high", "clear", dew=False).atmosphere.built_snow == 0.0
