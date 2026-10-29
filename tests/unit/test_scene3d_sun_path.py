"""Sun path arcs and the compass rose (Phase 17 L2.2, #386).

``core/scene3d/sun_path.py`` draws where the sun goes on four days. Held here to
``core.solar`` itself — the L2.2 gate: the noon point of every arc IS the dome
mapping of ``solar_position`` at its instant, and that instant is the day's highest
sun, found here by brute force — to the frame (a sun in the south lies south of the
plan, east lies east), to the horizon (an arc ends on it), to the local day (a
garden far from Greenwich gets one arc, not two halves), and to the polar cases.
"""

from __future__ import annotations

import math
from datetime import date, timedelta, timezone

import numpy as np
import pytest

from open_garden_planner.core.scene3d.color import srgb8_to_linear
from open_garden_planner.core.scene3d.sun_path import (
    ARC_ENGINE_RGBA,
    ARC_KINDS,
    ARC_RGBA,
    CARDINAL_BEARINGS,
    COMPASS_LIFT_CM,
    LETTER_SHARE,
    NORTH_RGBA,
    TODAY_TUBE_FACTOR,
    TUBE_SHARE,
    DayArc,
    SunPoint,
    compass_mesh,
    day_arc,
    dome_point,
    dome_radius,
    hour_marks,
    key_days,
    probe_pin_mesh,
    sun_path_mesh,
)
from open_garden_planner.core.solar import solar_position

BERLIN = (52.52, 13.40, timezone(timedelta(hours=2)))
SYDNEY = (-33.87, 151.21, timezone(timedelta(hours=10)))
QUITO = (-0.18, -78.47, timezone(timedelta(hours=-5)))
TROMSO = (69.65, 18.96, timezone(timedelta(hours=1)))
CENTER = (1200.0, 800.0)
RADIUS = 1600.0


def brute_noon_elevation(lat: float, lon: float, arc: DayArc) -> float:
    """The highest elevation of the day, sampled every 20 s within an hour of the arc's
    noon — the module's search shares no line with this."""
    assert arc.noon is not None
    best = -90.0
    start = arc.noon.utc - timedelta(hours=1)
    for step in range(180 * 2 + 1):
        best = max(best, solar_position(lat, lon, start + timedelta(seconds=20 * step)).elevation_deg)
    return best


@pytest.mark.parametrize("place", [BERLIN, SYDNEY, QUITO], ids=["berlin", "sydney", "quito"])
@pytest.mark.parametrize("day", [date(2026, 6, 21), date(2026, 12, 21), date(2026, 3, 20),
                                 date(2026, 10, 24)])
def test_the_noon_point_is_solar_position_at_solar_noon(place, day: date) -> None:
    """THE gate of L2.2."""
    lat, lon, tz = place
    arc = day_arc(lat, lon, day, tz)
    noon = arc.noon
    assert noon is not None
    exact = solar_position(lat, lon, noon.utc)
    assert (noon.elevation_deg, noon.azimuth_deg) == (exact.elevation_deg, exact.azimuth_deg)
    assert dome_point(CENTER, RADIUS, noon.elevation_deg, noon.azimuth_deg) == dome_point(
        CENTER, RADIUS, exact.elevation_deg, exact.azimuth_deg)
    # … and it IS the day's highest sun (to the brute force's 20 s grid)
    assert noon.elevation_deg >= brute_noon_elevation(lat, lon, arc) - 1e-6
    # it is a point of the arc, in its place in time
    segment = next(s for s in arc.segments if noon in s)
    times = [p.utc for p in segment]
    assert times == sorted(times)


def test_noon_lies_south_in_berlin_and_north_in_sydney() -> None:
    north_noon = day_arc(*BERLIN[:2], date(2026, 6, 21), BERLIN[2]).noon
    south_noon = day_arc(*SYDNEY[:2], date(2026, 6, 21), SYDNEY[2]).noon
    assert north_noon is not None and south_noon is not None
    assert abs(north_noon.azimuth_deg - 180.0) < 2.0
    assert min(south_noon.azimuth_deg, 360.0 - south_noon.azimuth_deg) < 2.0
    assert dome_point(CENTER, RADIUS, north_noon.elevation_deg, north_noon.azimuth_deg)[1] < CENTER[1]
    assert dome_point(CENTER, RADIUS, south_noon.elevation_deg, south_noon.azimuth_deg)[1] > CENTER[1]


class TestTheDome:
    def test_a_bearing_maps_to_its_compass_direction(self) -> None:
        east = dome_point(CENTER, RADIUS, 0.0, 90.0)
        south = dome_point(CENTER, RADIUS, 0.0, 180.0)
        zenith = dome_point(CENTER, RADIUS, 90.0, 0.0)
        assert east == pytest.approx((CENTER[0] + RADIUS, CENTER[1], 0.0))
        assert south == pytest.approx((CENTER[0], CENTER[1] - RADIUS, 0.0))
        assert zenith == pytest.approx((CENTER[0], CENTER[1], RADIUS))

    def test_every_point_lies_on_the_dome(self) -> None:
        arc = day_arc(*BERLIN[:2], date(2026, 6, 21), BERLIN[2])
        for segment in arc.segments:
            for p in segment:
                x, y, z = dome_point(CENTER, RADIUS, p.elevation_deg, p.azimuth_deg)
                assert math.dist((x, y, z), (*CENTER, 0.0)) == pytest.approx(RADIUS)
                assert z >= 0.0

    def test_the_radius_reaches_past_the_plan_corners(self) -> None:
        assert dome_radius(2400.0, 1600.0) > math.hypot(1200.0, 800.0)
        assert dome_radius(10.0, 10.0) == 500.0


class TestTheArc:
    def test_an_arc_ends_on_the_horizon(self) -> None:
        arc = day_arc(*BERLIN[:2], date(2026, 6, 21), BERLIN[2])
        assert len(arc.segments) == 1
        segment = arc.segments[0]
        assert segment[0].elevation_deg == 0.0 and segment[-1].elevation_deg == 0.0
        assert all(p.elevation_deg > 0.0 for p in segment[1:-1])
        # sunrise in the north-east, sunset in the north-west at midsummer in Berlin
        assert 30.0 < segment[0].azimuth_deg < 70.0
        assert 290.0 < segment[-1].azimuth_deg < 330.0

    def test_a_garden_far_from_greenwich_gets_one_arc_not_two_halves(self) -> None:
        """The heatmap's UTC civil day would split Sydney's arc at 00:00 UTC (10:00
        local); the local day keeps it whole."""
        arc = day_arc(*SYDNEY[:2], date(2026, 10, 24), SYDNEY[2])
        assert len(arc.segments) == 1
        local = [p.utc.astimezone(SYDNEY[2]).date() for p in arc.segments[0]]
        assert set(local) == {date(2026, 10, 24)}

    def test_polar_night_has_no_arc(self) -> None:
        arc = day_arc(*TROMSO[:2], date(2026, 12, 21), TROMSO[2])
        assert arc.segments == () and arc.noon is None

    def test_the_midnight_sun_is_one_run_above_the_horizon(self) -> None:
        arc = day_arc(*TROMSO[:2], date(2026, 6, 21), TROMSO[2])
        assert len(arc.segments) == 1
        assert all(p.elevation_deg > 0.0 for p in arc.segments[0])

    def test_the_four_days(self) -> None:
        days = key_days(date(2027, 10, 24))
        assert tuple(days) == ARC_KINDS
        assert days == {"today": date(2027, 10, 24), "june_solstice": date(2027, 6, 21),
                        "december_solstice": date(2027, 12, 21),
                        "march_equinox": date(2027, 3, 20)}

    def test_the_hour_marks_are_whole_local_hours_with_the_sun_up(self) -> None:
        arc = day_arc(*BERLIN[:2], date(2026, 6, 21), BERLIN[2])
        marks = hour_marks(arc, BERLIN[2])
        walls = [m.utc.astimezone(BERLIN[2]) for m in marks]
        assert all(w.minute == 0 and w.second == 0 for w in walls)
        assert [w.hour for w in walls] == list(range(walls[0].hour, walls[-1].hour + 1))
        assert 5 <= walls[0].hour <= 6 and 21 <= walls[-1].hour <= 22


class TestTheMeshes:
    def arcs(self) -> list[DayArc]:
        days = key_days(date(2026, 6, 21))
        return [day_arc(*BERLIN[:2], days[kind], BERLIN[2], kind) for kind in ARC_KINDS]

    def test_the_path_is_a_sound_mesh_with_each_arc_in_its_colour(self) -> None:
        mesh = sun_path_mesh(self.arcs(), CENTER, RADIUS)
        mesh.validate()
        colours = {tuple(np.round(c, 5)) for c in mesh.colors}
        for kind in ARC_KINDS:   # built in the engine's pre-compensated colours
            assert tuple(np.round(np.asarray(srgb8_to_linear(ARC_ENGINE_RGBA[kind]), np.float32), 5)) in colours
        assert mesh.positions[:, 2].min() >= -RADIUS * 0.01  # a tube's radius below the rim at most

    def test_the_engine_colours_keep_the_legends_hue_family(self) -> None:
        """The legend shows ``ARC_RGBA``; the tubes are built in ``ARC_ENGINE_RGBA``,
        tuned so the tone curve brings them back to the legend's hue (measured within
        2.7 degrees in five moods). Each stays within 10 degrees of its legend colour."""
        import colorsys

        assert set(ARC_ENGINE_RGBA) == set(ARC_RGBA) == set(ARC_KINDS)
        for kind in ARC_KINDS:
            legend = colorsys.rgb_to_hsv(*(v / 255.0 for v in ARC_RGBA[kind][:3]))[0] * 360.0
            engine = colorsys.rgb_to_hsv(*(v / 255.0 for v in ARC_ENGINE_RGBA[kind][:3]))[0] * 360.0
            assert abs((engine - legend + 180.0) % 360.0 - 180.0) <= 10.0, kind

    def test_the_plan_dates_arc_is_drawn_last_and_thicker(self) -> None:
        """On a key day the plan date's arc lies exactly on its twin (21 June) and was
        hidden under it: it is built last and ``TODAY_TUBE_FACTOR`` thicker."""
        arcs = self.arcs()
        today = srgb8_to_linear(ARC_ENGINE_RGBA["today"])
        mesh = sun_path_mesh(arcs, CENTER, RADIUS)
        mine = np.all(np.isclose(mesh.colors, np.asarray(today, np.float32)), axis=1)
        last = np.flatnonzero(mine)
        others = np.flatnonzero(~mine)
        assert last.min() > others.max()   # every plan-date vertex after every other one
        only = sun_path_mesh([arcs[0]], CENTER, RADIUS)
        # the tube's ring radius: distance of a ring vertex from its arc point
        from open_garden_planner.core.scene3d.sun_path import dome_point
        noon = arcs[0].noon
        axis = np.asarray(dome_point(CENTER, RADIUS, noon.elevation_deg, noon.azimuth_deg))
        reach = np.linalg.norm(only.positions - axis, axis=1).min()
        assert reach == pytest.approx(TUBE_SHARE * RADIUS * TODAY_TUBE_FACTOR, rel=0.05)

    def test_the_sun_ball_is_drawn_only_while_the_sun_is_up(self) -> None:
        arcs = self.arcs()
        bare = sun_path_mesh(arcs, CENTER, RADIUS)
        up = SunPoint(arcs[0].noon.utc, 60.0, 180.0)
        down = SunPoint(arcs[0].noon.utc, -5.0, 0.0)
        assert sun_path_mesh(arcs, CENTER, RADIUS, sun=up).vertex_count > bare.vertex_count
        assert sun_path_mesh(arcs, CENTER, RADIUS, sun=down).vertex_count == bare.vertex_count

    def test_the_compass_lies_flat_and_its_arrow_points_north(self) -> None:
        mesh = compass_mesh(CENTER, RADIUS)
        mesh.validate()  # every flat face wound counter-clockwise from above
        assert np.all(mesh.positions[:, 2] >= COMPASS_LIFT_CM - 1e-6)
        red = np.all(np.isclose(mesh.colors, np.asarray(srgb8_to_linear(NORTH_RGBA), np.float32)),
                     axis=1)
        arrow = mesh.positions[red]
        assert arrow[:, 1].min() > CENTER[1] + RADIUS          # beyond the rim, in the north
        assert abs(arrow[:, 0].mean() - CENTER[0]) < RADIUS * 0.05

    def test_a_letter_lies_at_its_bearing_with_its_top_outwards(self) -> None:
        # an outline with a hole, wound the "wrong" way round: the module orients it
        outer = [(-0.4, -0.5), (-0.4, 0.5), (0.4, 0.5), (0.4, -0.5)]          # clockwise
        hole = [(-0.2, -0.3), (0.2, -0.3), (0.2, 0.3), (-0.2, 0.3)]           # counter-clockwise
        glyphs = {bearing: [outer, hole] for bearing in CARDINAL_BEARINGS}
        bare = compass_mesh(CENTER, RADIUS)
        mesh = compass_mesh(CENTER, RADIUS, glyphs)
        mesh.validate()
        size = LETTER_SHARE * RADIUS
        letters = mesh.positions[bare.vertex_count:]
        p = mesh.positions.astype(np.float64)
        tri = mesh.indices.astype(np.int64)
        tri = tri[tri.min(axis=1) >= bare.vertex_count]
        covered = 0.5 * np.abs(np.cross(p[tri[:, 1]] - p[tri[:, 0]], p[tri[:, 2]] - p[tri[:, 0]])[:, 2]).sum()
        # float32 positions some 30 m from the origin: 1e-4, not 1e-6
        assert covered == pytest.approx(4 * (0.8 * 1.0 - 0.4 * 0.6) * size ** 2, rel=1e-4)
        east = letters[letters[:, 0] > CENTER[0] + RADIUS]
        assert len(east) and np.all(np.abs(east[:, 1] - CENTER[1]) < size)

    def test_an_unfillable_letter_is_left_out_and_the_rest_stands(self) -> None:
        bare = compass_mesh(CENTER, RADIUS)
        broken = {0.0: [[(0.0, 0.0), (1.0, 0.0)]], 90.0: [[(5.0, 5.0), (6.0, 5.0), (5.0, 6.0)],
                                                           [(0.0, 0.0), (0.1, 0.0), (0.0, 0.1)]]}
        mesh = compass_mesh(CENTER, RADIUS, broken)
        assert mesh.vertex_count >= bare.vertex_count

    def test_the_pin_stands_on_the_probed_point(self) -> None:
        mesh = probe_pin_mesh((300.0, 400.0), RADIUS)
        mesh.validate()
        assert mesh.positions[:, 2].min() == pytest.approx(0.0, abs=1e-3)  # on the ground
        assert mesh.positions[:, 2].max() >= 30.0
        assert abs(np.median(mesh.positions[:, 0]) - 300.0) < 20.0
        assert abs(np.median(mesh.positions[:, 1]) - 400.0) < 20.0
        assert np.all(mesh.uvs[:, 0] == 0.0), "probe pin must not be flagged as an arc in uvs"
