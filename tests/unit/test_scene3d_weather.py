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
    normalise_weather,
    todays_weather,
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
    assert cloudy.sky.sun_energy <= clear.sky.sun_energy
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
def test_the_fog_meets_the_weathered_horizon(weather: str) -> None:
    from open_garden_planner.core.scene3d.look import fog_linear

    look = living_look(AFTERNOON, "high", weather)
    assert look.fog_linear == fog_linear(look.sky.horizon, look.mood.probe_exposure,
                                         look.sky.sky_energy)
    assert look.plain_sky_linear == look.fog_linear


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
    """The phase is the sun's elevation, not the disc's energy: an overcast sky with
    no disc is no twilight (else sunset would not be built at once)."""
    noon = living_look(sun(40.0), "high", "overcast").sky
    assert noon.sun_energy == 0.0 and sky_phase(noon) == "day"
    assert sky_phase(living_look(sun(-2.0), "high", "overcast").sky) == "twilight"
    assert sky_phase(living_look(sun(-12.0), "high", "overcast").sky) == "night"


# ── the dew ──────────────────────────────────────────────────────────────────


def test_morning_and_evening_are_the_sides_of_the_meridian() -> None:
    assert is_morning(sun(10.0, 90.0)) and not is_evening(sun(10.0, 90.0))
    assert is_evening(sun(10.0, 270.0)) and not is_morning(sun(10.0, 270.0))
    # the southern hemisphere: the sun passes through the north at noon
    assert is_morning(sun(30.0, 40.0)) and is_evening(sun(30.0, 320.0))


@pytest.mark.parametrize(("elevation", "expected"), [
    (TWILIGHT_DEG - 0.1, 0.0), (TWILIGHT_DEG, 1.0), (0.0, 1.0), (6.0, 1.0), (12.0, 0.5),
    (DEW_GONE_DEG, 0.0), (40.0, 0.0)])
def test_the_dew_lies_from_dawn_until_the_sun_is_up_a_while(elevation: float, expected: float) -> None:
    assert dew_amount(sun(elevation, 90.0)) == pytest.approx(expected)
    assert dew_amount(sun(elevation, 270.0)) == 0.0          # never in the evening


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
    assert strengths["rain"] > strengths["overcast"] > strengths["clear"] > strengths["snow"]
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


# ── today's weather (L5.3) ───────────────────────────────────────────────────


@pytest.mark.parametrize(("code", "weather"), [
    (0, "clear"), (1, "clear"), (2, "clear"), (3, "overcast"), (45, "overcast"), (48, "overcast"),
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
                          "wetness", "snow_cover", "precip_density"):
            assert value == 0.0, field.name
