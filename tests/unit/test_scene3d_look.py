"""The look of a 3D frame as data — rig, presets, auto preset (Phase 17 L1.4, #385).

``core/scene3d/look.py`` holds every look decision that is not a Qt call, so the
GPU-less run covers it. Gates of the story pinned here: G3's default half (the
ramp is continuous; no mood contradicts its time of day) and G6 (the auto
preset on synthetic frame-time series).
"""

from __future__ import annotations

import ast
import dataclasses
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core import shadow_geometry
from open_garden_planner.core.scene3d import SunState, srgb_to_linear, sun_direction_scene
from open_garden_planner.core.scene3d import look as L
from open_garden_planner.core.scene3d.look import (
    AUTO_LEVELS,
    GOLDEN,
    LOW_SUN,
    NEUTRAL_DAY,
    NIGHT,
    NOON,
    PRESET_SPECS,
    PRESETS,
    AutoPolicy,
    AutoPreset,
    LookSpec,
    day_rig,
    fog_color,
    look_for,
    sky_is_stale,
    sky_separation_deg,
)

SOURCE = Path(L.__file__)
#: What the L0 spike measured, frozen when L1.10 deleted it (``tests/data``; its provenance
#: field says how it was made). The drift guards below compare with it.
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))


def sun(elevation: float, azimuth: float = 180.0) -> SunState:
    return SunState(elevation_deg=elevation, azimuth_deg=azimuth)


def codes(color: str) -> tuple[int, int, int]:
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def luma(color: str) -> float:
    r, g, b = codes(color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# ── the module ───────────────────────────────────────────────────────────────


def test_the_module_imports_no_qt() -> None:
    """Qt-free: stdlib + numpy and its own package (the scan of ``core/scene3d`` pins
    the package; this names the module, so a failure reads as what it is)."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "math", "collections", "dataclasses", "types", "typing",
                        "numpy"}, imported


# ── the rig: ported, not re-invented ─────────────────────────────────────────


class TestTheRigIsTheSpikes:
    """The values of ``ogp-lush-cinematic`` §3 are measured, and this module must BE them:
    the L0 spike's, frozen in ``tests/data/l0_spike_reference.json`` when the spike was
    deleted (L1.10) — a drift guard against the measurement, no longer against code."""

    def test_the_anchors(self) -> None:
        anchors = SPIKE["rig"]["anchors"]
        for rig, name in ((NOON, "NOON"), (GOLDEN, "GOLDEN"), (LOW_SUN, "LOW")):
            light, look = anchors[name]["sun"], anchors[name]["look"]
            assert [rig.sun_color, rig.sun_brightness] == light
            assert rig.sky_top == look["skyTop"] and rig.sky_horizon == look["skyHorizon"]
            assert rig.sun_disc == look["sunDiscColor"]
            assert rig.exposure == look["exposure"] and rig.probe_exposure == look["probe"]
        night = SPIKE["rig"]["night_look"]
        assert (NIGHT.sky_top, NIGHT.sky_horizon, NIGHT.sun_disc) == (
            night["skyTop"], night["skyHorizon"], night["sunDiscColor"])
        assert (NIGHT.exposure, NIGHT.probe_exposure) == (night["exposure"], night["probe"])
        assert SPIKE["rig"]["ramp_degrees"] == [L.NOON_DEG, L.GOLDEN_DEG, L.NIGHT_BELOW_DEG]
        assert SPIKE["rig"]["meadow_albedo"] == L.MEADOW_ALBEDO
        assert SPIKE["rig"]["fog_of_horizon"] == L.FOG_OF_HORIZON

    def test_the_sun_sets_where_the_2d_overlay_says(self) -> None:
        """ONE sunset threshold: 2D shadows stop below it, and so does the sun's key light
        in 3D — below it the key is the moon of the twilight ramp, faint at first."""
        assert L.NIGHT_BELOW_DEG == shadow_geometry.MIN_SUN_ELEVATION_DEG
        at = look_for(sun(L.NIGHT_BELOW_DEG))
        assert sun(L.NIGHT_BELOW_DEG).is_up and at.moon_travel_scene is None
        assert at.mood.twilight == 0.0 and at.sky.sun_energy == 1.0
        below_sun = sun(L.NIGHT_BELOW_DEG - 1e-9)
        below = look_for(below_sun)
        assert not below_sun.is_up and below.moon_travel_scene is not None
        assert below.mood.sun_brightness < 1e-6, "no key, and no shadow, just below 0.5°"
        assert below.sky.sun_energy == 0.0 and not below.night

    def test_night_begins_at_the_end_of_civil_twilight(self) -> None:
        """Review P1 (truth first): night was a switch at 0.5° — all of civil twilight
        drew as full moonlit night. Now the low-sun rig fades into the night rig down
        to −6°; at and below it, night."""
        assert L.TWILIGHT_DEG == -6.0
        assert not look_for(sun(-5.99)).night and look_for(sun(-6.0)).night
        assert look_for(sun(-6.0)).mood == look_for(sun(-30.0)).mood
        half = look_for(sun((L.NIGHT_BELOW_DEG + L.TWILIGHT_DEG) / 2.0))
        assert half.mood.twilight == pytest.approx(0.5)
        assert half.mood.sun_brightness == pytest.approx(NIGHT.sun_brightness / 2.0)
        assert half.mood.exposure == pytest.approx(math.sqrt(LOW_SUN.exposure * NIGHT.exposure))
        assert half.sky.sky_energy == pytest.approx(0.625) == half.sky.ground_energy
        assert half.mood.saturation == pytest.approx((1.06 + 0.6) / 2.0)
        assert half.shadow.factor == 25.0, "the key is the moon: its soft shadow"

    @pytest.mark.parametrize("elevation", [round(0.5 + 0.25 * k, 2) for k in range(0, 160)])
    def test_the_day_ramp_at_every_quarter_degree(self, elevation: float) -> None:
        """0.5° … 40.25° in quarter degrees: key light, sky, sun disc, both exposures and
        the fog are the spike's ``sun_light`` / ``day_look`` / ``look_for`` to the bit
        (frozen)."""
        rig = day_rig(elevation)
        spike = SPIKE["rig"]["day_ramp"][repr(elevation)]
        assert (rig.sun_color, rig.sun_brightness) == (spike["sun_color"], spike["sun_brightness"])
        look = look_for(sun(elevation))
        assert (rig.sky_top, rig.sky_horizon, rig.sun_disc) == (
            spike["skyTop"], spike["skyHorizon"], spike["sunDiscColor"])
        assert rig.exposure == spike["exposure"] and rig.probe_exposure == spike["probe"]
        assert look.fog_color == spike["fogColor"]
        assert (look.sky.top, look.sky.horizon, look.sky.sun_disc) == (
            rig.sky_top, rig.sky_horizon, rig.sun_disc)

    def test_the_night_rig(self) -> None:
        spike_sun = SPIKE["rig"]["night_sun_berlin_2026_06_21_2130_utc"]
        assert spike_sun["night"]
        look = look_for(sun(spike_sun["elevation"], spike_sun["azimuth"]))
        assert look.night
        assert (look.mood.sun_color, look.mood.sun_brightness) == (spike_sun["color"],
                                                                  spike_sun["brightness"])
        assert look.moon_travel_scene == pytest.approx(spike_sun["travel_scene"], abs=1e-12)
        spike = SPIKE["rig"]["night_look_at_minus_10"]
        assert (look.mood.exposure, look.mood.probe_exposure) == (spike["exposure"], spike["probe"])

    def test_the_deliberate_differences_from_the_spike_are_the_night_fog_and_ground(self) -> None:
        """L1.4, look-dev round 1. The spike's fog was the horizon x probe exposure x 0.8
        in every mood; its night SKY is drawn x 0.25 on top (``skyEnergy``), so the night
        fog was four times brighter than the sky it met: a bright line along the whole
        horizon (a one-row step of 10.5 luma at high and 21.2 at low at eye height; with
        the sky's energy in the fog, and the fog handed to the engine in linear light:
        2.4 / 3.2). By day the energy is 1 and nothing changed."""
        spike = SPIKE["rig"]["night_look_at_minus_10"]
        night = look_for(sun(-10.0))
        assert night.sky.sky_energy == 0.25
        assert night.fog_color == SPIKE["rig"]["night_fog_at_the_sky_energy"]
        assert night.fog_color != spike["fogColor"]
        assert luma(night.fog_color) < luma(spike["fogColor"]) / 1.5
        # Round 5: the night sky's ground hemisphere at the sky's own energy (the day
        # rule), not the spike's 0.15 — that drew a dark line at the night horizon
        # (dip 2.07 / 1.04 luma at low / high -> 0.01 / 0.12). By day both are 1.0.
        assert night.sky.ground_energy == night.sky.sky_energy == 0.25
        day = look_for(sun(30.0))
        assert day.sky.ground_energy == day.sky.sky_energy == 1.0

    def test_the_boards_own_numbers(self) -> None:
        """``ogp-lush-cinematic`` §3, "On the board": what the bench plan's shots get."""
        golden = look_for(sun(15.23))
        assert (golden.mood.sun_color, golden.mood.sun_brightness) == ("#ffd0a8", 1.9)
        assert golden.sky.horizon == "#e7d8c8"
        assert golden.mood.probe_exposure == pytest.approx(0.519, abs=5e-4)
        assert golden.mood.exposure == pytest.approx(1.024, abs=5e-4)
        december = look_for(sun(14.04))
        assert (december.mood.sun_color, december.mood.sun_brightness) == ("#ffcda3", 1.9)
        assert december.mood.exposure == pytest.approx(1.039, abs=5e-4)
        sunset = look_for(sun(5.89))
        assert sunset.mood.sun_color == "#ffb777"
        assert sunset.mood.sun_brightness == pytest.approx(1.896, abs=5e-4)
        assert sunset.mood.exposure == pytest.approx(1.152, abs=5e-4)
        assert sunset.mood.probe_exposure == pytest.approx(0.498, abs=5e-4)
        assert look_for(sun(26.16)).mood.exposure == pytest.approx(0.892, abs=5e-4)
        for elevation in (60.9, 42.2, 30.0, 89.0):
            assert day_rig(elevation) is NOON


class TestAnchorsAndMixing:
    @pytest.mark.parametrize(("elevation", "rig"), [
        (0.5, LOW_SUN), (6.0, GOLDEN), (30.0, NOON), (75.0, NOON), (0.0, LOW_SUN), (-3.0, LOW_SUN)])
    def test_an_anchor_comes_back_exactly(self, elevation: float, rig: L.Rig) -> None:
        assert day_rig(elevation) is rig

    def test_colours_mix_in_linear_light(self) -> None:
        half = L.mix_linear("#000000", "#ffffff", 0.5)
        assert half == "#bcbcbc", "the sRGB encoding of linear 0.5 — not #808080"
        assert L.mix_linear("#123456", "#abcdef", 0.0) == "#123456"
        assert L.mix_linear("#123456", "#abcdef", 1.0) == "#abcdef"

    def test_exposure_mixes_in_stops(self) -> None:
        middle = day_rig((L.GOLDEN_DEG + L.NOON_DEG) / 2.0)
        assert middle.exposure == pytest.approx(math.sqrt(GOLDEN.exposure * NOON.exposure))

    def test_fog_is_the_horizon_as_the_sky_draws_it_times_point_eight_in_linear_light(self) -> None:
        """Horizon x the sky's own energy x probe exposure — what the skybox shows at its
        horizon — x 0.8, in linear light."""
        for elevation in (-20.0, 0.5, 3.0, 6.0, 15.0, 30.0, 61.0):
            look = look_for(sun(elevation))
            expected = srgb_to_linear(look.sky.horizon).astype(np.float64) * (
                look.mood.probe_exposure * look.sky.sky_energy * 0.8)
            assert look.fog_color == L.linear_to_srgb_hex(expected)
            assert look.fog_color == fog_color(look.sky.horizon, look.mood.probe_exposure,
                                               look.sky.sky_energy)
            assert look.plain_sky == look.fog_color, "without a sky texture the fog meets the sky"
        assert look_for(sun(-20.0)).sky.sky_energy == 0.25 and look_for(sun(20.0)).sky.sky_energy == 1.0

    def test_the_flat_fill_is_derived_from_the_sky_not_chosen(self) -> None:
        """Where no sky texture lights the view, a flat fill of the same energy stands in:
        the mean of the sky's top and horizon in linear light x probe exposure (x the
        sky's energy: a quarter at night)."""
        noon = look_for(sun(60.0))
        top, horizon = srgb_to_linear(NOON.sky_top), srgb_to_linear(NOON.sky_horizon)
        assert L.FILL_OF_SKY == 0.5
        assert noon.fill_linear == pytest.approx(
            tuple(float(v) for v in (top + horizon) / 2.0 * NOON.probe_exposure * 0.5), abs=1e-6)
        # half of L1.2's value: at full strength compatibility mode read +22 luma over the
        # GPU's sky-lit frame (review P2, fix round 1)
        assert noon.fill_linear == pytest.approx((0.0927, 0.1304, 0.2024), abs=5e-4)
        night = look_for(sun(-12.0))
        top, horizon = srgb_to_linear(NIGHT.sky_top), srgb_to_linear(NIGHT.sky_horizon)
        assert night.fill_linear == pytest.approx(
            tuple(float(v) for v in (top + horizon) / 2.0 * NIGHT.probe_exposure * 0.25 * 0.5),
            abs=1e-6)
        assert noon.fill_color == L.linear_to_srgb_hex(noon.fill_linear)


# ── gate G3 (default half): continuity, and no mood against its time of day ───

#: Measured over the whole day ramp in 0.5° steps (2026-10-12): the largest step of any
#: colour channel is 5 codes, of the exposure 0.0109 stops, of the probe exposure
#: 0.0073, of the key light's brightness 0.0182. The bounds sit just above.
MAX_COLOUR_STEP = 6        # 8-bit sRGB codes per 0.5°
MAX_EXPOSURE_STEP = 0.015  # stops per 0.5°
MAX_PROBE_STEP = 0.01      # per 0.5°
MAX_BRIGHTNESS_STEP = 0.02  # per 0.5°
#: Through twilight (0.5° → −6°, 13 half degrees; measured 2026-10-19, fix round 1): the
#: largest step of any colour channel is 52 codes (the sky horizon's LAST half degree —
#: mixed in linear light, the dark end moves most in codes; the moon carries the frame's
#: light there, and the render tier's dusk sweep is monotone), of the exposure 0.0724
#: stops (1.25 -> 2.4 over 6.5°), of the moon key 0.0246, of the sky's energy 0.0577. The
#: bounds sit just above.
TWILIGHT_MAX_COLOUR_STEP = 54
TWILIGHT_MAX_EXPOSURE_STEP = 0.075


def _day_elevations(step: float = 0.5) -> list[float]:
    count = int(round((90.0 - L.NIGHT_BELOW_DEG) / step))
    return [L.NIGHT_BELOW_DEG + step * k for k in range(count + 1)]


class TestTheRampIsContinuous:
    def test_no_step_larger_than_the_stated_bound_between_adjacent_half_degrees(self) -> None:
        looks = [look_for(sun(e)) for e in _day_elevations()]
        worst = {"colour": 0, "exposure": 0.0, "probe": 0.0, "brightness": 0.0}
        for before, after in zip(looks, looks[1:], strict=False):
            for first, second in (
                    (before.mood.sun_color, after.mood.sun_color),
                    (before.sky.top, after.sky.top), (before.sky.horizon, after.sky.horizon),
                    (before.sky.sun_disc, after.sky.sun_disc),
                    (before.fog_color, after.fog_color), (before.plain_sky, after.plain_sky),
                    (before.fill_color, after.fill_color)):
                step = max(abs(a - b) for a, b in zip(codes(first), codes(second), strict=True))
                worst["colour"] = max(worst["colour"], step)
            worst["exposure"] = max(worst["exposure"], abs(
                math.log2(after.mood.exposure) - math.log2(before.mood.exposure)))
            worst["probe"] = max(worst["probe"], abs(
                after.mood.probe_exposure - before.mood.probe_exposure))
            worst["brightness"] = max(worst["brightness"], abs(
                after.mood.sun_brightness - before.mood.sun_brightness))
        assert worst["colour"] <= MAX_COLOUR_STEP, worst
        assert worst["exposure"] <= MAX_EXPOSURE_STEP, worst
        assert worst["probe"] <= MAX_PROBE_STEP, worst
        assert worst["brightness"] <= MAX_BRIGHTNESS_STEP, worst
        # the bounds are real: the ramp does move, and by about what was measured
        assert worst["colour"] >= 4 and worst["exposure"] >= 0.008, worst

    def test_a_finer_sweep_finds_no_cliff_between_the_half_degrees(self) -> None:
        """A step hidden BETWEEN two sampled elevations (a rig switch at 8° or 20°, as the
        first boards had) shows up in a sweep ten times finer: no channel moves more
        than two codes in 0.05°."""
        looks = [look_for(sun(e)) for e in _day_elevations(0.05)]
        for before, after in zip(looks, looks[1:], strict=False):
            for first, second in ((before.mood.sun_color, after.mood.sun_color),
                                  (before.sky.horizon, after.sky.horizon),
                                  (before.fog_color, after.fog_color)):
                assert max(abs(a - b) for a, b in
                           zip(codes(first), codes(second), strict=True)) <= 2
            assert abs(math.log2(after.mood.exposure / before.mood.exposure)) <= 0.004

    def test_the_sweep_through_twilight_has_no_cliff(self) -> None:
        """Review P1: the sweep now crosses sunset and civil twilight, −18° … 90° in
        half degrees. The day keeps the day bounds; twilight has its own (measured,
        just above): it spends 0.94 stops of exposure and the whole way from the low
        sun's sky to the night sky over 6.5°. ONE step is not in the ramp, by truth:
        at 0.5° the sun's key light (1.7) goes, as the 2D shadows do — every other
        value crosses it within the twilight bounds."""
        elevations = [-18.0 + 0.5 * k for k in range(217)]
        looks = {e: look_for(sun(e)) for e in elevations}
        worst = {"colour": 0, "exposure": 0.0, "probe": 0.0, "brightness": 0.0, "energy": 0.0}
        for low, high in zip(elevations, elevations[1:], strict=False):
            if low >= L.NIGHT_BELOW_DEG:
                continue                   # the day ramp: test_no_step_larger_than_…
            before, after = looks[low], looks[high]
            for first, second in ((before.sky.top, after.sky.top),
                                  (before.sky.horizon, after.sky.horizon),
                                  (before.fog_color, after.fog_color),
                                  (before.plain_sky, after.plain_sky),
                                  (before.fill_color, after.fill_color)):
                step = max(abs(a - b) for a, b in zip(codes(first), codes(second), strict=True))
                worst["colour"] = max(worst["colour"], step)
            worst["exposure"] = max(worst["exposure"], abs(
                math.log2(after.mood.exposure) - math.log2(before.mood.exposure)))
            worst["probe"] = max(worst["probe"], abs(
                after.mood.probe_exposure - before.mood.probe_exposure))
            worst["energy"] = max(worst["energy"], abs(after.sky.sky_energy - before.sky.sky_energy))
            if high < L.NIGHT_BELOW_DEG:   # the key: the moon fading in (not across sunset)
                worst["brightness"] = max(worst["brightness"], abs(
                    after.mood.sun_brightness - before.mood.sun_brightness))
        assert worst["colour"] <= TWILIGHT_MAX_COLOUR_STEP, worst
        assert worst["exposure"] <= TWILIGHT_MAX_EXPOSURE_STEP, worst
        assert worst["probe"] <= MAX_PROBE_STEP, worst
        assert worst["brightness"] <= MAX_BRIGHTNESS_STEP * 2, worst
        assert worst["energy"] <= 0.06, worst
        # the one step that is not in the ramp: the sun's key light at 0.5°
        day, dusk = look_for(sun(0.5)), look_for(sun(0.4999))
        assert day.mood.sun_brightness == LOW_SUN.sun_brightness and dusk.mood.sun_brightness < 0.001
        assert (day.mood.exposure, day.mood.probe_exposure) == pytest.approx(
            (dusk.mood.exposure, dusk.mood.probe_exposure), abs=1e-3)
        assert max(abs(a - b) for a, b in zip(codes(day.sky.horizon), codes(dusk.sky.horizon),
                                             strict=True)) <= 1

    def test_dusk_never_brightens(self) -> None:
        """From 6° down to night the light only fades: no exposure x energy product
        rises — the sky's light (probe x energy x exposure) never grows as the sun sinks."""
        values = []
        for k in range(0, 121):
            look = look_for(sun(6.0 - 0.1 * k))
            values.append(look.mood.exposure * look.mood.probe_exposure * look.sky.sky_energy)
        assert all(after <= before + 1e-9 for before, after in zip(values, values[1:], strict=False)), \
            values

    def test_no_mood_contradicts_its_time_of_day(self) -> None:
        """Lower sun: never a brighter key, never a cooler one, never a lower exposure —
        so a 14° December noon cannot come out warmer than a 15° June golden hour again."""
        looks = [look_for(sun(e)) for e in _day_elevations(0.25)]
        for lower, higher in zip(looks, looks[1:], strict=False):
            assert lower.mood.sun_brightness <= higher.mood.sun_brightness + 1e-12
            assert lower.mood.exposure >= higher.mood.exposure - 1e-12
            r_low, _g, b_low = codes(lower.mood.sun_color)
            r_high, _g, b_high = codes(higher.mood.sun_color)
            assert r_low - b_low >= r_high - b_high - 1, "a lower sun is at least as warm"
        assert max(look.mood.sun_brightness for look in looks) == NOON.sun_brightness

    def test_night_is_dark_cool_and_desaturated(self) -> None:
        night, noon = look_for(sun(-18.0)), look_for(sun(60.0))
        assert night.mood.sun_brightness < noon.mood.sun_brightness / 4.0
        r, _g, b = codes(night.mood.sun_color)
        assert b > r, "moonlight is cool"
        assert luma(night.sky.top) < luma(noon.sky.top) / 4.0
        assert luma(night.sky.horizon) < luma(noon.sky.horizon) / 4.0
        assert night.mood.saturation == 0.6 < noon.mood.saturation == 1.06
        assert night.sky.sun_energy == 0.0 and noon.sky.sun_energy == 1.0
        assert (night.shadow.factor, night.shadow.pcf_factor) == (25.0, 8.0)
        assert (noon.shadow.factor, noon.shadow.pcf_factor) == (82.0, 2.0)

    def test_the_moon_is_the_night_rigs_stated_direction(self) -> None:
        east, north, up = sun_direction_scene(L.MOON_ELEVATION_DEG, L.MOON_AZIMUTH_DEG)
        assert (L.MOON_ELEVATION_DEG, L.MOON_AZIMUTH_DEG) == (38.0, 165.0)
        assert look_for(sun(-5.0, 300.0)).moon_travel_scene == pytest.approx((-east, -north, -up))
        assert look_for(sun(10.0)).moon_travel_scene is None, "by day the key is the sun"

    def test_the_sun_direction_is_not_part_of_a_day_look(self) -> None:
        """Truth before beauty: a day look made for another azimuth differs only in where
        the SKY draws its disc — nothing in it could aim the light."""
        east, west = look_for(sun(20.0, 90.0)), look_for(sun(20.0, 270.0))
        assert dataclasses.replace(east, sky=west.sky) == west


# ── presets ──────────────────────────────────────────────────────────────────


class TestPresets:
    def test_the_four_presets_are_the_measured_ones(self) -> None:
        """``ogp-3d-renderer`` §4 / the spike's ``GardenSpike.qml``, as data — with three
        values moved in L1.4: the shadow bias of high and ultra, 5 -> 10 (round 2: a
        sun-grazed lit wall was hatched at 5 on Direct3D 11); low's anti-aliasing FXAA
        -> 4x MSAA (fix round 1, #529: the picket moiré); medium's map 1024 -> 2048 (fix
        round 1: no preset has a smaller map than the one below it). The numbers are at
        ``PRESET_SPECS``."""
        rows = {name: (p.shadow_map_quality, p.shadow_cascades, p.soft_shadows, p.shadow_bias,
                       p.antialiasing, p.antialiasing_quality, p.ambient_occlusion,
                       p.ao_sample_rate, p.glow, p.glow_high_quality, p.reflections)
                for name, p in PRESET_SPECS.items()}
        assert rows == {
            "low": ("very_high", 1, "pcf4", 15.0, "msaa", "high", False, 2, False, False, False),
            "medium": ("very_high", 1, "pcf8", 15.0, "msaa", "high", True, 2, True, False, False),
            "high": ("very_high", 2, "pcf16", 10.0, "msaa", "high", True, 3, True, False, False),
            "ultra": ("ultra", 3, "pcf32", 10.0, "msaa", "very_high", True, 4, True, True, True),
        }
        assert tuple(PRESET_SPECS) == PRESETS == ("low", "medium", "high", "ultra")

    def test_no_preset_costs_less_than_the_one_below_it(self) -> None:
        """Review P2: low had a larger shadow map (2048) than medium (1024). Map size,
        cascades, filter and anti-aliasing samples never fall from low to ultra."""
        size = {"high": 1024, "very_high": 2048, "ultra": 4096}
        pcf = {"pcf4": 4, "pcf8": 8, "pcf16": 16, "pcf32": 32}
        samples = {("msaa", "medium"): 2, ("msaa", "high"): 4, ("msaa", "very_high"): 8,
                   ("fxaa", "high"): 1, ("fxaa", "medium"): 1, ("fxaa", "very_high"): 1}
        specs = [PRESET_SPECS[name] for name in PRESETS]
        for lower, higher in zip(specs, specs[1:], strict=False):
            assert size[lower.shadow_map_quality] <= size[higher.shadow_map_quality]
            assert lower.shadow_cascades <= higher.shadow_cascades
            assert pcf[lower.soft_shadows] <= pcf[higher.soft_shadows]
            assert (samples[(lower.antialiasing, lower.antialiasing_quality)]
                    <= samples[(higher.antialiasing, higher.antialiasing_quality)])

    def test_everything_else_of_the_presets_is_still_the_spikes_scene_file(self) -> None:
        """Map, cascades and filter per preset: the bindings of the spike's
        ``GardenSpike.qml``, frozen when L1.10 deleted the spike."""
        spike = "\n".join(SPIKE["qml"]["preset_bindings"])
        for line in (   # (the spike's medium map — 1024 — and low's FXAA: moved, above)
            'shadowMapQuality: root.preset === "low" ? Light.ShadowMapQualityVeryHigh',
            ': root.preset === "medium" ? Light.ShadowMapQualityHigh',
            ': root.preset === "high" ? Light.ShadowMapQualityVeryHigh',
            ': root.preset === "medium" ? 1 : (root.preset === "high" ? 2 : 3))',
            'softShadowQuality: root.preset === "low" ? Light.PCF4',
            ': root.preset === "high" ? Light.PCF16 : Light.PCF32',
            'shadowBias: (root.preset === "low" || root.preset === "medium") ? 15 : 5',
            'aoEnabled: !root.orthoTopDown && root.preset !== "low"',
            'aoSampleRate: root.preset === "ultra" ? 4 : (root.preset === "high" ? 3 : 2)',
            'glowEnabled: !root.orthoTopDown && root.preset !== "low"',
            'fxaaEnabled: root.preset === "low" && !root.orthoTopDown',
            'ssrEnabled: root.preset === "ultra" && root.allowSsr',
        ):
            assert line in spike, line

    @pytest.mark.parametrize("preset", PRESETS)
    def test_every_preset_has_fog_no_sharpening_and_no_ssgi(self, preset: str) -> None:
        spec = PRESET_SPECS[preset]
        assert spec.fog is True, "low without fog drew a one-row cliff at the horizon"
        assert spec.sharpening == 0.0, "0.08 overshot every thin lit edge into dark dots"
        assert spec.global_illumination is False, "SSGI is opt-in: black frames on llvmpipe"
        assert spec.ambient_occlusion == (preset != "low"), "SSAO from medium up"

    @pytest.mark.parametrize("preset", PRESETS)
    @pytest.mark.parametrize("elevation", [-20.0, 0.5, 5.89, 15.23, 60.9])
    def test_a_preset_changes_cost_and_never_the_mood(self, preset: str, elevation: float) -> None:
        look, reference = look_for(sun(elevation), preset), look_for(sun(elevation), "high")
        assert look.mood == reference.mood and look.sky == reference.sky
        assert look.fog_color == reference.fog_color and look.fill_linear == reference.fill_linear
        assert look.moon_travel_scene == reference.moon_travel_scene
        assert look.preset is PRESET_SPECS[preset]
        assert (look.shadow.map_quality, look.shadow.cascades, look.shadow.soft_shadows,
                look.shadow.bias) == (look.preset.shadow_map_quality, look.preset.shadow_cascades,
                                      look.preset.soft_shadows, look.preset.shadow_bias)
        assert (look.shadow.factor, look.shadow.pcf_factor) == (
            reference.shadow.factor, reference.shadow.pcf_factor), "softness follows the mood"

    def test_an_unknown_preset_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown preset"):
            look_for(sun(30.0), "auto")
        with pytest.raises(ValueError):
            dataclasses.replace(PRESET_SPECS["low"], antialiasing="taa")

    @pytest.mark.parametrize(("stored", "expected"), [
        ("auto", "auto"), ("HIGH", "high"), (" low ", "low"), ("ultra", "ultra"),
        ("", "auto"), ("fastest", "auto"), (None, "auto"), (3, "auto")])
    def test_a_stored_quality_is_normalised(self, stored: object, expected: str) -> None:
        assert L.normalise_quality(stored) == expected

    def test_a_look_is_plain_frozen_comparable_data(self) -> None:
        first, second = look_for(sun(22.0, 140.0), "medium"), look_for(sun(22.0, 140.0), "medium")
        assert first == second and first is not second
        assert isinstance(first, LookSpec) and dataclasses.is_dataclass(first)
        with pytest.raises(dataclasses.FrozenInstanceError):
            first.fog_linear = (0.0, 0.0, 0.0)  # type: ignore[misc]
        assert first != look_for(sun(22.5, 140.0), "medium")

    def test_the_neutral_day_is_the_noon_rig_at_high(self) -> None:
        """What a host shows before anyone hands it a look — the one look L1.2 had."""
        assert look_for(sun(60.0, 180.0), "high") == NEUTRAL_DAY
        assert (NEUTRAL_DAY.mood.sun_color, NEUTRAL_DAY.mood.sun_brightness,
                NEUTRAL_DAY.mood.exposure) == ("#fff1dc", 1.9, 0.85)
        assert not NEUTRAL_DAY.night and NEUTRAL_DAY.meadow_albedo == "#487f34"
        assert NEUTRAL_DAY.wind_strength == 2.5


# ── when the sky follows the sun (gate G4, the decision) ─────────────────────


class TestSkyStaleness:
    def test_no_sky_yet_is_stale(self) -> None:
        assert sky_is_stale(None, look_for(sun(30.0)).sky)

    def test_a_move_below_the_threshold_keeps_the_sky(self) -> None:
        shown = look_for(sun(30.0, 180.0)).sky
        assert L.SKY_REBUILD_DEG == 1.0
        for elevation, azimuth in ((30.0, 180.0), (30.5, 180.0), (30.0, 181.1), (29.4, 179.2)):
            wanted = look_for(sun(elevation, azimuth)).sky
            assert sky_separation_deg(shown, wanted) < 1.0
            assert not sky_is_stale(shown, wanted), (elevation, azimuth)

    def test_a_noticeable_move_rebuilds(self) -> None:
        shown = look_for(sun(30.0, 180.0)).sky
        for elevation, azimuth in ((31.01, 180.0), (30.0, 181.2), (29.2, 180.8), (30.0, 0.0)):
            wanted = look_for(sun(elevation, azimuth)).sky
            assert sky_separation_deg(shown, wanted) >= 1.0
            assert sky_is_stale(shown, wanted), (elevation, azimuth)

    def test_the_separation_is_a_great_circle_angle(self) -> None:
        """Near the zenith a large change of azimuth is a small move of the sun."""
        high = look_for(sun(89.5, 0.0)).sky, look_for(sun(89.5, 180.0)).sky
        assert sky_separation_deg(*high) == pytest.approx(1.0, abs=1e-6)
        low = look_for(sun(10.0, 0.0)).sky, look_for(sun(10.0, 2.0)).sky
        assert sky_separation_deg(*low) == pytest.approx(2.0 * math.cos(math.radians(10.0)), abs=1e-3)

    def test_a_change_of_phase_rebuilds_whatever_the_distance(self) -> None:
        """Sunset (0.5°: the disc goes), nightfall (−6°: the night sky), and back."""
        day, dusk = look_for(sun(0.6, 300.0)).sky, look_for(sun(0.4, 300.0)).sky
        assert sky_separation_deg(day, dusk) < 1.0
        assert (L.sky_phase(day), L.sky_phase(dusk)) == ("day", "twilight")
        assert sky_is_stale(day, dusk) and sky_is_stale(dusk, day)
        late, night = look_for(sun(-5.9, 330.0)).sky, look_for(sun(-6.1, 330.5)).sky
        assert (L.sky_phase(late), L.sky_phase(night)) == ("twilight", "night")
        assert sky_is_stale(late, night) and sky_is_stale(night, late)

    def test_twilight_skies_follow_the_sun_by_the_degree(self) -> None:
        shown = look_for(sun(-1.0, 310.0)).sky
        assert not sky_is_stale(shown, look_for(sun(-1.6, 310.0)).sky)
        assert sky_is_stale(shown, look_for(sun(-2.1, 310.0)).sky)

    def test_a_night_sky_is_never_rebuilt_for_the_suns_position(self) -> None:
        """At night the sky draws no sun (its energy is 0): nothing to follow."""
        shown = look_for(sun(-8.0, 310.0)).sky
        for elevation, azimuth in ((-10.0, 330.0), (-40.0, 20.0), (-7.0, 60.0)):
            assert not sky_is_stale(shown, look_for(sun(elevation, azimuth)).sky)

    def test_the_sky_never_asks_for_a_sun_far_below_the_horizon(self) -> None:
        assert look_for(sun(-40.0)).sky.sun_elevation_deg == L.SKY_MIN_ELEVATION_DEG == L.TWILIGHT_DEG == -6.0
        assert look_for(sun(12.0, 725.0)).sky.sun_azimuth_deg == pytest.approx(5.0)


# ── gate G6: the auto preset on synthetic frame-time series ──────────────────


class Feed:
    """A view that draws continuously: ``run(seconds, frame_time)`` advances a clock in
    ``step`` seconds, counts the frames a view with that frame time presents, and
    feeds the machine. ``frame_time`` may be a function of the CURRENT preset."""

    def __init__(self, auto: AutoPreset, step: float = 0.5) -> None:
        self.auto, self.step = auto, step
        self.now, self.frames, self._owed = 0.0, 0, 0.0
        self.changes: list[tuple[float, str]] = []

    def run(self, seconds: float, frame_time: object) -> None:
        end = self.now + seconds
        while self.now < end - 1e-9:
            self.now += self.step
            per_frame = frame_time(self.auto.preset) if callable(frame_time) else frame_time
            if per_frame is not None:
                self._owed += self.step / float(per_frame)
                whole = int(self._owed)
                self.frames += whole
                self._owed -= whole
            changed = self.auto.observe(self.now, self.frames)
            if changed is not None:
                self.changes.append((self.now, changed))


FAST, OK, SLOW = 1 / 60.0, 1 / 35.0, 1 / 15.0


class TestAutoPreset:
    def test_the_policy_has_a_dead_band_and_the_budgets_numbers(self) -> None:
        policy = AutoPolicy()
        assert 1 / policy.slow_frame_s == pytest.approx(27.0)   # the budget is 30, the kill 20
        assert 1 / policy.fast_frame_s == pytest.approx(50.0)
        assert (policy.window_s, policy.hold_s, policy.retry_s, policy.stall_s,
                policy.min_samples) == (3.0, 10.0, 300.0, 10.0, 3)
        assert AUTO_LEVELS == ("low", "medium", "high"), "ultra is a choice, never automatic"
        with pytest.raises(ValueError, match="dead band"):
            AutoPolicy(slow_frame_s=0.02, fast_frame_s=0.03)

    def test_it_starts_where_it_is_told_and_ultra_is_not_a_level(self) -> None:
        assert AutoPreset().preset == "medium"
        assert AutoPreset("high").preset == "high"
        assert AutoPreset("ultra").preset == "medium"
        assert AutoPreset("nonsense").preset == "medium"

    def test_it_steps_down_within_the_stated_time_when_slow(self) -> None:
        """Slow from the first frame: one window of data (3 s) plus one sample (0.5 s)."""
        feed = Feed(AutoPreset("high"))
        feed.run(20.0, SLOW)
        assert feed.changes[0][1] == "medium"
        assert feed.changes[0][0] <= AutoPolicy().window_s + 2 * feed.step
        assert [name for _at, name in feed.changes] == ["medium", "low"], "and on, while slow"
        assert feed.changes[1][0] - feed.changes[0][0] <= AutoPolicy().window_s + feed.step
        assert feed.auto.preset == "low"

    def test_it_never_steps_below_the_lowest_level(self) -> None:
        feed = Feed(AutoPreset("low"))
        feed.run(120.0, SLOW)
        assert feed.changes == [] and feed.auto.preset == "low"

    def test_it_steps_up_only_after_the_hold_time(self) -> None:
        """Every step up waits out the hold — the FIRST one counted from the first poll
        (review P1: a new session stepped up after one window)."""
        feed = Feed(AutoPreset("low"))
        feed.run(60.0, FAST)
        assert [name for _at, name in feed.changes] == ["medium", "high"]
        first, second = (at for at, _name in feed.changes)
        hold = AutoPolicy().hold_s
        assert hold <= first <= hold + 2 * feed.step, "the first step waits the hold, too"
        assert second - first >= hold, "the next one waits out the hold"
        assert second - first <= hold + AutoPolicy().window_s
        assert feed.auto.preset == "high"

    def test_the_bars_are_handed_back_and_seeded_across_sessions(self) -> None:
        """Review P1: the bar on a level that proved too slow lived in memory only. A
        session hands its bars back (``bars_at``: seconds still barred, next bar's
        length) and the next one is seeded with them at its first poll."""
        policy = AutoPolicy()
        feed = Feed(AutoPreset("medium"))
        feed.run(30.0, lambda preset: SLOW if preset == "high" else FAST)
        assert [name for _at, name in feed.changes] == ["high", "medium"]
        down_at = feed.changes[1][0]
        bars = feed.auto.bars_at(feed.now)
        assert bars == {"high": (pytest.approx(policy.retry_s - (feed.now - down_at)),
                                 2 * policy.retry_s)}
        # the next session, started 60 s later: high stays barred for what is left
        left = bars["high"][0] - 60.0
        nxt = Feed(AutoPreset("medium", bars={"high": (left, bars["high"][1])}))
        assert nxt.auto.bars_at(0.0) == {"high": (left, 2 * policy.retry_s)}, "not polled yet"
        nxt.run(left - 1.0, FAST)
        assert nxt.changes == [], "barred: no step up while the bar lasts"
        nxt.run(policy.hold_s + policy.window_s, FAST)
        assert [name for _at, name in nxt.changes] == ["high"], "the bar is over: one retry"
        nxt.run(policy.window_s + 2.0, lambda preset: SLOW if preset == "high" else FAST)
        assert [name for _at, name in nxt.changes] == ["high", "medium"]
        assert nxt.auto.bars_at(nxt.now)["high"][1] == 4 * policy.retry_s, "failed again: doubled"

    def test_a_stored_bar_never_reaches_further_than_the_longest_retry(self) -> None:
        """Re-check of fix round 1: a hand-edited bar of 1e18 s (or a wall clock that
        jumped) was seeded as it stood and barred the level for good — 10 h of 120 fps
        at medium gave 0 steps up. The seed is clamped to ``max_retry_s``."""
        policy = AutoPolicy()
        feed = Feed(AutoPreset("medium", bars={"high": (1e18, 300.0)}))
        feed.auto.observe(0.0, 0)
        assert feed.auto.bars_at(0.0)["high"][0] == policy.max_retry_s
        feed.run(policy.max_retry_s + policy.hold_s + policy.window_s + 2.0, FAST)
        assert [name for _at, name in feed.changes] == ["high"], "the bar ended"

    def test_seeded_bars_are_cleaned(self) -> None:
        """A store that holds nonsense loses the bar, never the session."""
        policy = AutoPolicy()
        auto = AutoPreset("medium", bars={"ultra": (10.0, 10.0), "high": (math.inf, 5.0),
                                          "low": (-30.0, 1e9)})
        auto.observe(0.0, 0)
        assert auto.bars_at(0.0) == {"low": (0.0, policy.max_retry_s)}

    def test_nothing_happens_inside_the_dead_band(self) -> None:
        for start in AUTO_LEVELS:
            feed = Feed(AutoPreset(start))
            feed.run(600.0, OK)
            assert feed.changes == [], start

    @pytest.mark.parametrize("threshold", ["slow", "fast"])
    @pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
    def test_a_series_noisy_around_a_threshold_never_oscillates(self, threshold: str,
                                                               seed: int) -> None:
        """Frame times scattered ± 25 % around a threshold, the same whatever the preset:
        the machine may step, but only ever in ONE direction."""
        policy = AutoPolicy()
        centre = policy.slow_frame_s if threshold == "slow" else policy.fast_frame_s
        noise = random.Random(seed)
        feed = Feed(AutoPreset("medium"))
        feed.run(1800.0, lambda _preset: centre * noise.uniform(0.75, 1.25))
        order = [AUTO_LEVELS.index(name) for _at, name in feed.changes]
        path = [AUTO_LEVELS.index("medium"), *order]
        directions = {b - a for a, b in zip(path, path[1:], strict=False)}
        assert len(directions) <= 1, (threshold, seed, feed.changes)
        assert len(feed.changes) <= len(AUTO_LEVELS) - 1

    def test_a_level_that_is_too_slow_is_not_tried_again_for_a_growing_while(self) -> None:
        """The classic oscillation: high is slow, medium is fast. One step down — and the
        next try of high only after the bar (5 min), then 10, then 20."""
        policy = AutoPolicy()
        feed = Feed(AutoPreset("high"))
        feed.run(3600.0, lambda preset: SLOW if preset == "high" else FAST)
        downs = [at for at, name in feed.changes if name == "medium"]
        ups = [at for at, name in feed.changes if name == "high"]
        assert downs[0] <= policy.window_s + 2 * feed.step
        waits = [up - down for down, up in zip(downs, ups, strict=False)]
        assert waits[0] >= policy.retry_s and waits[1] >= 2 * policy.retry_s
        assert waits[2] >= 4 * policy.retry_s
        assert len(feed.changes) <= 8, "a handful of tries in an hour, not a flicker"
        for up, down in zip(ups, downs[1:], strict=False):
            assert down - up <= policy.window_s + 2 * feed.step, "each failed try ends at once"

    def test_a_stalled_series_holds_the_preset(self) -> None:
        """No frames — the display asleep, the window covered — is NO DATA, never "slow"."""
        for start in AUTO_LEVELS:
            feed = Feed(AutoPreset(start))
            feed.run(600.0, None)
            assert feed.changes == [] and feed.auto.preset == start

    def test_a_stall_in_the_middle_is_a_gap_not_a_slow_frame(self) -> None:
        feed = Feed(AutoPreset("high"))
        feed.run(2.0, OK)
        feed.run(120.0, None)      # asleep: 120 s without a frame
        feed.run(2.0, OK)          # 2 s of frames again: not a full window yet
        assert feed.changes == [], "the gap's 120 s were not divided by its few frames"
        feed.run(60.0, OK)
        assert feed.changes == []

    def test_a_frame_rarer_than_the_stall_time_is_no_data_either(self) -> None:
        """One frame every 12 s cannot be told from a sleeping display by counting
        frames: longer than ``stall_s`` without one is a gap. It holds (stated in the ADR)."""
        feed = Feed(AutoPreset("high"), step=1.0)
        feed.run(600.0, 12.0)
        assert feed.changes == []

    @pytest.mark.parametrize("frame_time", [0.5, 2.0, 4.0, 7.0])
    def test_very_slow_rendering_still_counts(self, frame_time: float) -> None:
        """Two frames a second down to one in seven seconds are SLOW, not stalled: three
        samples of it decide."""
        feed = Feed(AutoPreset("high"), step=1.0)
        feed.run(4 * frame_time + 4.0, frame_time)
        assert feed.changes and feed.changes[0][1] == "medium"

    def test_one_hitch_decides_nothing(self) -> None:
        """The GUI thread held for four seconds (a plan load) while the view is otherwise
        fast: one long sample among fast ones. The median ignores it — and it only
        delays the step up it interrupts."""
        feed = Feed(AutoPreset("medium"))
        feed.run(2.0, FAST)
        feed.run(4.0, None)        # no frame for 4 s: under the stall time, so it is a sample
        feed.run(2.5, FAST)
        assert feed.changes == [], "a 4 s frame time in the window, and no step down"
        feed.run(10.0, FAST)
        assert [name for _at, name in feed.changes] == ["high"]

    def test_pause_drops_what_was_collected(self) -> None:
        feed = Feed(AutoPreset("high"))
        feed.run(2.5, SLOW)
        feed.auto.pause()          # the view was hidden before the window was full
        feed.run(2.5, SLOW)
        assert feed.changes == [], "two halves of a window are not a window"
        feed.run(1.5, SLOW)
        assert [name for _at, name in feed.changes] == ["medium"]

    def test_a_counter_or_clock_that_goes_backwards_starts_over(self) -> None:
        auto = AutoPreset("high")
        assert auto.observe(100.0, 5000) is None
        assert auto.observe(101.0, 10) is None      # a fresh host: its counter began again
        assert auto.observe(50.0, 20) is None       # the clock went back
        feed = Feed(auto)
        feed.now, feed.frames = 50.0, 20
        feed.run(5.0, SLOW)
        assert [name for _at, name in feed.changes] == ["medium"]

    def test_the_steps_are_recorded(self) -> None:
        feed = Feed(AutoPreset("high"))
        feed.run(5.0, SLOW)
        assert [(before, after) for _at, before, after in feed.auto.steps] == [("high", "medium")]
