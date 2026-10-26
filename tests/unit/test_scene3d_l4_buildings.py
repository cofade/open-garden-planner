"""Roof styles, pitch, overhang and facades (Phase 17 L4.1, #388) — Qt-free.

``core/roof_style`` (the metadata's rules) and the building builder over it: the
roof's TOP is the building's height in every style; a hip roof is the lower
envelope of its eaves' planes (convex outlines; others get the gable); a shed roof
rises toward the item's +y; a flat roof is a slab; the pitch and overhang a user
sets replace the style's; the facade's windows stay under the roof and the door
goes on the wall ``params["door_wall"]`` names.
"""

from __future__ import annotations

import dataclasses
import math

import numpy as np
import pytest

from open_garden_planner.core import roof_style as rs
from open_garden_planner.core.scene3d import DIMENSIONLESS_PARAMS, Params, verify_builder
from open_garden_planner.core.scene3d.builders import buildings, production_registry
from open_garden_planner.core.scene3d.builders.facade import SPECS, door_wall_index, facade
from open_garden_planner.core.scene3d.builders.roofs import (
    MAX_HIP_CORNERS,
    eave_floor,
    flat_roof,
    gable_roof,
    hip_roof,
    is_convex,
    shed_roof,
)
from tests.unit.scene3d_builder_cases import L_RIDGE, L_SHAPE, U_SHAPE, polygon_record, rectangle

REGISTRY = production_registry()
RIDGE = ((-450.0, 0.0), (450.0, 0.0))


def house(params: dict | None = None, ring=None, height: float = 450.0, kind: str = "HOUSE"):
    return polygon_record(kind, ring if ring is not None else rectangle(900.0, 540.0), height,
                          shape="rectangle", params=params)


def names(record) -> list[str]:
    return [part.name for part in REGISTRY.build(record)]


def roof_of(record):
    return next(part for part in REGISTRY.build(record) if part.name == "roof")


# ── the metadata ─────────────────────────────────────────────────────────────


class TestRoofMetadata:
    def test_absent_and_unknown_values_are_automatic(self) -> None:
        for metadata in (None, {}, {"roof_style": "pagoda"}, {"roof_style": 3}):
            assert rs.roof_style(metadata) is None
        assert [rs.roof_style({"roof_style": s}) for s in rs.ROOF_STYLES] == list(rs.ROOF_STYLES)

    @pytest.mark.parametrize(("value", "expected"), [
        (None, None), (0.0, None), (-5.0, None), ("38", None), (True, None), (float("nan"), None),
        (float("inf"), None), (2.0, rs.MIN_PITCH_DEG), (38.0, 38.0), (89.0, rs.MAX_PITCH_DEG),
    ])
    def test_a_pitch_is_clamped_or_absent(self, value, expected) -> None:
        assert rs.roof_pitch_deg({"roof_pitch_deg": value}) == expected

    @pytest.mark.parametrize(("value", "expected"), [
        (None, None), (0.0, 0.0), (-3.0, 0.0), (45.0, 45.0), (1e9, rs.MAX_OVERHANG_CM), ("x", None),
    ])
    def test_an_overhang_is_clamped_or_absent(self, value, expected) -> None:
        assert rs.roof_overhang_cm({"roof_overhang_cm": value}) == expected

    def test_the_pitch_is_the_one_param_that_is_not_a_length(self) -> None:
        assert "roof_pitch_deg" in DIMENSIONLESS_PARAMS
        assert Params({"roof_pitch_deg": 45.0})["roof_pitch_deg"] == 45.0


# ── every style: the top is the height ───────────────────────────────────────


@pytest.mark.parametrize("style", [None, *rs.ROOF_STYLES])
@pytest.mark.parametrize("kind", sorted(rs.BUILDING_KINDS))
@pytest.mark.parametrize("height", [450.0, 250.0, 120.0])
def test_every_style_tops_out_at_the_height(style, kind, height) -> None:
    params = {"roof_style": style} if style else {}
    if kind == "HOUSE":
        params["ridge"] = RIDGE
    record = house(params, height=height, kind=kind)
    parts = verify_builder(REGISTRY.builder_for(kind), record, plan_margin_cm=60.0)
    top = max(float(part.mesh.positions[:, 2].max()) for part in parts)
    assert top == pytest.approx(height, rel=1e-4)
    # a building too low for a door or a window has no facade part (an empty mesh is left out)
    expected = ["walls", "roof", "facade"] if height >= 250.0 else ["walls", "roof"]
    assert [part.name for part in parts] == expected


def test_a_house_without_a_ridge_has_a_flat_roof_and_one_with_one_a_gable() -> None:
    flat = roof_of(house())
    gable = roof_of(house({"ridge": RIDGE}))
    flat_top = flat.mesh.positions[flat.mesh.normals[:, 2] > 0.9][:, 2]
    assert float(np.ptp(flat_top)) < 1e-3  # one level: a slab
    assert float(np.ptp(gable.mesh.positions[:, 2])) > 100.0   # two slopes


def test_a_chosen_gable_on_a_house_without_a_ridge_runs_along_its_long_axis() -> None:
    roof = roof_of(house({"roof_style": "gable"}))
    top = roof.mesh.positions[roof.mesh.positions[:, 2] >= 449.0]
    assert float(np.ptp(top[:, 0])) > float(np.ptp(top[:, 1]))  # the ridge runs east-west


class TestHip:
    def test_a_rectangle_gets_four_slopes_meeting_in_a_ridge(self) -> None:
        built = hip_roof(rectangle(900.0, 540.0), 450.0, buildings.HOUSE_ROOF)
        assert built is not None
        top = built.roof.positions[built.roof.positions[:, 2] >= 450.0 - 1e-3]
        # the ridge runs along the long side: 900 - 540 long, at y = 0
        assert float(np.ptp(top[:, 0])) == pytest.approx(900.0 - 540.0, abs=1.0)
        assert float(np.abs(top[:, 1]).max()) < 1e-3
        normals = built.roof.normals[built.roof.normals[:, 2] > 0.1]
        headings = {(round(float(x), 2), round(float(y), 2)) for x, y in normals[:, :2]}
        assert len(headings) == 4  # one slope facing each way

    def test_a_square_is_a_pyramid(self) -> None:
        built = hip_roof(rectangle(600.0, 600.0), 400.0, buildings.HOUSE_ROOF)
        assert built is not None
        top = built.roof.positions[built.roof.positions[:, 2] >= 400.0 - 1e-3]
        assert float(np.linalg.norm(top[:, :2], axis=1).max()) < 1e-3

    def test_an_outline_that_is_not_convex_gets_none_and_the_house_a_gable(self) -> None:
        assert not is_convex(L_SHAPE) and is_convex(rectangle(10.0, 20.0))
        assert hip_roof(L_SHAPE, 450.0, buildings.HOUSE_ROOF) is None
        record = polygon_record("HOUSE", L_SHAPE, 450.0, params={"roof_style": "hip", "ridge": L_RIDGE})
        gable = gable_roof(L_SHAPE, L_RIDGE, 450.0, buildings.HOUSE_ROOF)
        assert gable is not None and roof_of(record).mesh == gable.roof

    def test_an_outline_of_many_corners_gets_a_gable(self) -> None:
        angle = np.linspace(0.0, 2.0 * math.pi, MAX_HIP_CORNERS + 4, endpoint=False)
        ring = [(500.0 * math.cos(a), 300.0 * math.sin(a)) for a in angle]
        assert is_convex(ring) and hip_roof(ring, 450.0, buildings.HOUSE_ROOF) is None

    def test_the_walls_end_under_the_slab(self) -> None:
        built = hip_roof(rectangle(900.0, 540.0), 450.0, buildings.HOUSE_ROOF)
        assert built is not None and built.wall_top is not None
        walls_top = float(built.walls.positions[:, 2].max())
        roof_low = float(built.roof.positions[:, 2].min())
        assert walls_top == pytest.approx(float(built.wall_top(np.zeros((1, 2)))[0]))
        assert roof_low <= walls_top + 1e-3  # the slab's eave hangs at or below the walls' top


class TestShed:
    def test_it_rises_toward_the_item_s_plus_y(self) -> None:
        built = shed_roof(rectangle(400.0, 300.0), 250.0, buildings.SHED_ROOF)
        assert built is not None
        roof = built.roof.positions
        north = roof[roof[:, 1] > 100.0][:, 2].max()
        south = roof[roof[:, 1] < -100.0][:, 2].max()
        assert north == pytest.approx(250.0, abs=1e-3) and south < north - 50.0

    def test_its_walls_follow_the_slope(self) -> None:
        built = shed_roof(rectangle(400.0, 300.0), 250.0, buildings.SHED_ROOF)
        assert built is not None and built.wall_top is not None
        tops = built.wall_top(np.array([[0.0, 150.0], [0.0, -150.0]]))
        assert tops[0] > tops[1]

    def test_the_eave_floor_flattens_a_steep_low_roof(self) -> None:
        style = buildings.SHED_ROOF
        built = shed_roof(rectangle(400.0, 600.0), 260.0, style)
        assert built is not None and built.wall_top is not None
        low = float(built.wall_top(np.array([[0.0, -300.0]]))[0])
        assert low >= min(style.eave_floor_cm, style.eave_floor_share * (260.0 - style.slab_cm)) - 1e-3


def test_a_flat_roof_is_one_slab_at_the_height() -> None:
    built = flat_roof(rectangle(400.0, 300.0), 300.0, buildings.FLAT_ROOF)
    assert built is not None
    tops = built.roof.positions[built.roof.normals[:, 2] > 0.9][:, 2]
    assert float(tops.min()) == float(tops.max()) == pytest.approx(300.0)


# ── the user's pitch and overhang ────────────────────────────────────────────


def test_a_steeper_pitch_lowers_the_eaves_and_a_longer_overhang_reaches_further() -> None:
    base = roof_of(house({"ridge": RIDGE})).mesh.positions
    steep = roof_of(house({"ridge": RIDGE, "roof_pitch_deg": 55.0})).mesh.positions
    wide = roof_of(house({"ridge": RIDGE, "roof_overhang_cm": 90.0})).mesh.positions
    assert float(steep[:, 2].min()) < float(base[:, 2].min())
    assert float(np.abs(wide[:, 1]).max()) == pytest.approx(270.0 + 90.0, abs=1.0)
    assert float(np.abs(base[:, 1]).max()) == pytest.approx(270.0 + 30.0, abs=1.0)


@pytest.mark.parametrize("kind,width,depth,height", [
    ("TOOL_SHED", 60.0, 100.0, 200.0), ("TOOL_SHED", 240.0, 180.0, 250.0),
    ("HOUSE", 600.0, 1000.0, 700.0), ("HOUSE", 900.0, 540.0, 450.0), ("GARAGE_SHED", 300.0, 500.0, 250.0)])
@pytest.mark.parametrize("style", ["gable", "hip", "shed"])
def test_no_roof_reaches_the_ground_at_the_panels_extremes(kind, width, depth, height, style) -> None:
    """Senior review of #388, P1: the eave floor held only where the roof met the
    walls; the overhang went on down the slope, and at the panel's own extremes
    (pitch 60°, overhang 150 cm) a 60 x 100 cm tool shed's roof reached 91.5 cm into
    the ground — its hip fell back to a gable that sank the same. Over the panel's
    ranges no roof edge is lower than ``EDGE_FLOOR_SHARE`` of the eave floor, and the
    style the user chose is kept: the OVERHANG is shortened."""
    for pitch in (rs.MIN_PITCH_DEG, 30.0, 45.0, rs.MAX_PITCH_DEG):
        for overhang in (0.0, 50.0, 100.0, rs.MAX_OVERHANG_CM):
            params = {"roof_style": style, "roof_pitch_deg": pitch, "roof_overhang_cm": overhang}
            record = house(params, ring=rectangle(width, depth), height=height, kind=kind)
            roof = roof_of(record)
            base = buildings.HOUSE_ROOF if kind == "HOUSE" else buildings.SHED_ROOF
            style_used = buildings.style_for(record, base)
            floor = buildings.EDGE_FLOOR_SHARE * eave_floor(style_used, height)
            assert float(roof.mesh.positions[:, 2].min()) >= floor - 1e-3, (pitch, overhang)
            if style == "hip":   # a rectangle keeps its hip: a slope facing each way, never the gable's two
                slopes = roof.mesh.normals[roof.mesh.normals[:, 2] > 0.1]
                assert len({(round(float(x), 2), round(float(y), 2)) for x, y in slopes[:, :2]}) == 4


def _hexagon(radius: float):
    return tuple((radius * math.cos(math.pi * k / 3.0), radius * math.sin(math.pi * k / 3.0)) for k in range(6))


#: An L drawn on a grid: the HOUSE tool's ridge, the bounding box's centre line, lies on
#: its inner edge — the gable builds no roof at exactly no overhang.
L_ON_A_GRID = ((-450.0, -300.0), (450.0, -300.0), (450.0, 0.0), (0.0, 0.0), (0.0, 300.0), (-450.0, 300.0))
L_ON_A_GRID_RIDGE = ((-450.0, 0.0), (450.0, 0.0))


@pytest.mark.parametrize("kind,ring,height,style,pitch,overhang,params", [
    ("HOUSE", _hexagon(300.0), 700.0, "hip", 60.0, 150.0, {}),             # round 3: 37.5 where 73.9 holds
    ("TOOL_SHED", rectangle(240.0, 180.0), 700.0, "shed", 60.0, 100.0, {}),  # 40.3 where 76.9 holds
    ("TOOL_SHED", rectangle(60.0, 100.0), 450.0, "shed", 60.0, 150.0, {}),
    ("TOOL_SHED", rectangle(60.0, 100.0), 200.0, "gable", 60.0, 150.0, {}),
    ("GARAGE_SHED", rectangle(240.0, 180.0), 40.0, "gable", 30.0, 150.0, {}),
    ("HOUSE", U_SHAPE, 150.0, "gable", 60.0, 100.0, {}),   # round 4: no roof at exactly 100 cm
    ("HOUSE", U_SHAPE, 25.0, "gable", 60.0, 100.0, {}),
    ("HOUSE", tuple((250.0 * math.cos(2.0 * math.pi * k / 64), 250.0 * math.sin(2.0 * math.pi * k / 64))
                    for k in range(64)), 700.0, "hip", 60.0, 150.0, {}),   # no roof at the long end
    ("HOUSE", L_ON_A_GRID, 700.0, "gable", 60.0, 150.0,
     {"ridge": L_ON_A_GRID_RIDGE}),                        # round 5: no roof at exactly no overhang
    ("TOOL_SHED", rectangle(100.0, 50.0), 400.0, "shed", 60.0, 100.0, {}),   # round 5: 0 where 94.8 holds
    ("TOOL_SHED", rectangle(150.0, 60.0), 400.0, "shed", 45.0, 150.0, {}),   # the measured grid's worst
])
def test_a_shortened_overhang_is_nearly_the_longest_that_holds(
        monkeypatch: pytest.MonkeyPatch, kind, ring, height, style, pitch, overhang, params) -> None:
    """Senior review of #388: the round-2 search halved after a failed guess — a
    hexagonal hip got 37.5 cm of overhang where 73.9 cm holds; round 4 found a U whose
    gable is NO roof at exactly 100 cm, shortened to 50; round 5 an L on a grid whose
    gable is no roof at exactly no overhang (the roof was lost), and a small shed roof
    whose slope clamp bends the edge's fall (0 where 94.8 holds). Over
    ``scripts/measure_roof_overhang.py``'s grid the worst case is 96.5 % of the longest
    overhang that holds; at most ``OVERHANG_TRIES`` roofs beyond the ends."""
    real = buildings._pitched  # noqa: SLF001
    tried: list[tuple[object, float]] = []

    def counting(record, chosen, height_cm, roof_style):
        built = real(record, chosen, height_cm, roof_style)
        tried.append((None if built is None else built.roof, roof_style.overhang_cm))
        return built

    monkeypatch.setattr(buildings, "_pitched", counting)
    record = polygon_record(kind, ring, height, shape="rectangle" if len(ring) == 4 else "polygon", params={
        "roof_style": style, "roof_pitch_deg": pitch, "roof_overhang_cm": overhang, **params})
    roof = roof_of(record)
    found = next(cm for mesh, cm in tried if mesh is roof.mesh)
    assert len(tried) <= 3 + buildings.OVERHANG_TRIES   # the long end, the short end (and a hair in)

    style_used = buildings.style_for(record, buildings.HOUSE_ROOF if kind == "HOUSE" else buildings.SHED_ROOF)
    floor = buildings.EDGE_FLOOR_SHARE * eave_floor(style_used, height)

    def holds(cm: float) -> bool:
        built = real(record, style, height, dataclasses.replace(style_used, overhang_cm=cm))
        return built is not None and float(built.roof.positions[:, 2].min()) >= floor - 1e-6

    assert not holds(overhang), "the case shortens the overhang"
    low, high = 0.0, overhang
    for _step in range(30):
        middle = (low + high) / 2.0
        low, high = (middle, high) if holds(middle) else (low, middle)
    assert 0.96 * low <= found <= low + 1e-3, (found, low)


def _turned(ring, degrees: float):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return tuple((x * c - y * s, x * s + y * c) for x, y in ring)


@pytest.mark.parametrize("width,depth,degrees,height,overhang", [
    (900.0, 540.0, 45.0, 700.0, 100.0), (600.0, 400.0, 45.0, 450.0, 150.0)])
def test_a_straight_edge_takes_one_guess(monkeypatch: pytest.MonkeyPatch, width, depth, degrees, height,
                                         overhang) -> None:
    """A house drawn turned over a satellite image gets the HOUSE tool's ridge on its
    bounding box's long axis, oblique to its walls (round 6 of the senior review: a case
    neither the test nor the measurement had). Its edge falls in a straight line, and the
    chord to the sunk roof finds the root in one guess: three roofs — the style's
    overhang, none, the guess — at 99 % of the longest that holds. Without the chord it
    took five; a stop on a centimetre alone took four on the larger house."""
    ring = _turned(rectangle(width, depth), degrees)
    crossings = [x0 + (0.0 - y0) / (y1 - y0) * (x1 - x0)
                 for (x0, y0), (x1, y1) in zip(ring, (*ring[1:], ring[0]), strict=True)
                 if y0 != y1 and y0 * y1 <= 0.0]
    ridge = ((min(crossings), 0.0), (max(crossings), 0.0))   # the tool's: along x through the centre
    real = buildings._pitched  # noqa: SLF001
    tried: list[tuple[object, float]] = []

    def counting(record, chosen, height_cm, roof_style):
        built = real(record, chosen, height_cm, roof_style)
        tried.append((None if built is None else built.roof, roof_style.overhang_cm))
        return built

    monkeypatch.setattr(buildings, "_pitched", counting)
    record = polygon_record("HOUSE", ring, height, params={
        "roof_style": "gable", "roof_pitch_deg": 45.0, "roof_overhang_cm": overhang, "ridge": ridge})
    roof = roof_of(record)
    found = next(cm for mesh, cm in tried if mesh is roof.mesh)
    assert len(tried) == 3, [cm for _mesh, cm in tried]
    style = buildings.style_for(record, buildings.HOUSE_ROOF)
    floor = buildings.EDGE_FLOOR_SHARE * eave_floor(style, height)

    def holds(cm: float) -> bool:
        built = real(record, "gable", height, dataclasses.replace(style, overhang_cm=cm))
        return built is not None and float(built.roof.positions[:, 2].min()) >= floor - 1e-6

    low, high = 0.0, overhang
    for _step in range(30):
        middle = (low + high) / 2.0
        low, high = (middle, high) if holds(middle) else (low, middle)
    assert 0.98 * low <= found <= low + 1e-3, (found, low)


def test_a_style_that_builds_no_roof_at_either_end_is_left_to_the_caller() -> None:
    """A hip on an outline that is not convex builds no roof at any overhang:
    ``_kept_up`` returns None, and the caller builds the gable along the ridge."""
    params = {"roof_style": "hip", "roof_pitch_deg": 45.0, "roof_overhang_cm": 150.0, "ridge": L_RIDGE}
    record = polygon_record("HOUSE", L_SHAPE, 450.0, params=params)
    style = buildings.style_for(record, buildings.HOUSE_ROOF)
    assert buildings._kept_up(record, "hip", 450.0, style) is None  # noqa: SLF001
    assert buildings._kept_up(record, "gable", 450.0, style) is not None  # noqa: SLF001
    assert len(roof_of(record).mesh.positions)


@pytest.mark.parametrize("kind", ["TOOL_SHED", "HOUSE"])
def test_a_ridge_on_an_edge_of_the_outline_keeps_a_roof(kind: str) -> None:
    """Round 5 of the senior review, P1: an L drawn on a grid has the HOUSE tool's ridge on
    its inner edge, and the gable builds no roof at exactly no overhang; the search took
    that for "this style builds no roof here" and the house became a 7 m plain block —
    though every overhang from 0.01 cm to about 100 cm holds. A tool shed whose record
    says rectangle has its ridge there too. The short end is tried a hair inside."""
    ring, ridge = (L_SHAPE, None) if kind == "TOOL_SHED" else (L_ON_A_GRID, L_ON_A_GRID_RIDGE)
    params = {"roof_style": "gable", "roof_pitch_deg": 60.0, "roof_overhang_cm": 150.0}
    if ridge is not None:
        params["ridge"] = ridge
    record = polygon_record(kind, ring, 700.0, shape="rectangle" if kind == "TOOL_SHED" else "polygon",
                            params=params)
    style = buildings.style_for(record, buildings.HOUSE_ROOF if kind == "HOUSE" else buildings.SHED_ROOF)
    assert buildings._pitched(record, "gable", 700.0, dataclasses.replace(style, overhang_cm=0.0)) is None  # noqa: SLF001
    names = {part.name for part in REGISTRY.build(record)}
    assert {"roof", "facade"} <= names, names
    floor = buildings.EDGE_FLOOR_SHARE * eave_floor(style, 700.0)
    assert float(roof_of(record).mesh.positions[:, 2].min()) >= floor - 1e-3


@pytest.mark.parametrize("height", [18.5, 19.0, 20.0, 21.0, 21.5])
def test_a_building_too_low_for_the_floor_keeps_the_walls_own_roof(height: float) -> None:
    """A gable holds its eaves to 0.75 x (top - ridge cap - slab), lower than the
    ``eave_floor`` the floor is half of, so on a house 18-22 cm tall its roof without an
    overhang ends under the floor — 0.8 to 3.7 cm above the ground, with no overhang
    left to shorten. It keeps that roof (round 4: it had become a plain block)."""
    record = house({"roof_style": "gable", "roof_overhang_cm": 150.0}, ring=rectangle(300.0, 200.0),
                   height=height)
    roof = roof_of(record)
    style = buildings.style_for(record, buildings.HOUSE_ROOF)
    without = buildings._pitched(record, "gable", height, dataclasses.replace(style, overhang_cm=0.0))  # noqa: SLF001
    assert without is not None and roof.mesh == without.roof
    assert float(roof.mesh.positions[:, 2].min()) >= 0.0


def test_style_for_clamps_like_the_metadata() -> None:
    record = house({"roof_pitch_deg": 89.0, "roof_overhang_cm": 1e5})
    style = buildings.style_for(record, buildings.HOUSE_ROOF)
    assert (style.pitch_deg, style.overhang_cm) == (rs.MAX_PITCH_DEG, rs.MAX_OVERHANG_CM)
    assert buildings.style_for(house(), buildings.HOUSE_ROOF) is buildings.HOUSE_ROOF


def test_a_tool_shed_rectangle_takes_its_sprite_s_ridge() -> None:
    """The tool-shed sprite's ridge runs along its HEIGHT (the item's local y), also on
    a 200 x 150 shed: the 3D gable follows the sprite, not the long axis."""
    roof = roof_of(polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0, shape="rectangle"))
    top = roof.mesh.positions[roof.mesh.positions[:, 2] >= 249.0]
    assert float(np.ptp(top[:, 1])) > float(np.ptp(top[:, 0]))
    polygon = roof_of(polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0))
    top = polygon.mesh.positions[polygon.mesh.positions[:, 2] >= 249.0]
    assert float(np.ptp(top[:, 0])) > float(np.ptp(top[:, 1]))  # a polygon shows no sprite


# ── the facade ───────────────────────────────────────────────────────────────


def _front(record):
    return next(part for part in REGISTRY.build(record) if part.name == "facade")


def test_windows_and_doors_stay_under_the_wall_top_and_on_the_walls() -> None:
    for params in ({"ridge": RIDGE}, {"roof_style": "hip"}, {"roof_style": "shed"}, {}):
        record = house(params)
        built = buildings._roof(record, 450.0, buildings.HOUSE_ROOF)
        assert built is not None and built.wall_top is not None
        points = _front(record).mesh.positions.astype(np.float64)
        assert len(points)
        tops = built.wall_top(points[:, :2])
        assert np.all(points[:, 2] <= tops - 1.0 + 1e-3)
        # proud of the walls by at most MAX_PROUD_CM (9 cm): within the footprint + 10
        assert float(np.abs(points[:, 0]).max()) <= 450.0 + 9.0 + 1e-3
        assert float(np.abs(points[:, 1]).max()) <= 270.0 + 9.0 + 1e-3


def test_a_low_shed_gets_no_window_or_door_its_wall_cannot_hold() -> None:
    low = polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 140.0, shape="rectangle")
    assert [part.name for part in REGISTRY.build(low)] == ["walls", "roof"]
    tall = polygon_record("TOOL_SHED", rectangle(200.0, 150.0), 250.0, shape="rectangle")
    assert [part.name for part in REGISTRY.build(tall)] == ["walls", "roof", "facade"]


@pytest.mark.parametrize("wall", [0, 1, 2, 3])
def test_the_door_goes_on_the_wall_the_param_names(wall: int) -> None:
    """A rectangle's walls in order (counter-clockwise from its south-west corner):
    0 south, 1 east, 2 north, 3 west. The door's brass knob is on that wall."""
    record = house({"ridge": RIDGE, "door_wall": wall})
    points = _front(record).mesh.positions.astype(np.float64)
    colors = _front(record).mesh.colors.astype(np.float64)
    from open_garden_planner.core.scene3d.builders import palette

    brass = np.isclose(colors, np.asarray(palette.BRASS.linear), atol=1e-5).all(axis=1)
    knob = points[brass].mean(axis=0)
    expected = {0: (0.0, -1.0), 1: (1.0, 0.0), 2: (0.0, 1.0), 3: (-1.0, 0.0)}[wall]
    direction = knob[:2] / np.linalg.norm(knob[:2])
    assert float(direction @ np.asarray(expected)) > 0.7


def test_door_wall_index_picks_the_facing_wall_nearest_the_path() -> None:
    ring = rectangle(900.0, 540.0)
    assert door_wall_index(ring, (0.0, -900.0)) == 0      # a path to the south
    assert door_wall_index(ring, (2000.0, 100.0)) == 1    # to the east
    assert door_wall_index(ring, (-100.0, 400.0)) == 2    # to the north
    assert door_wall_index(ring, (-900.0, -50.0)) == 3    # to the west
    assert door_wall_index(ring, (0.0, 0.0)) in range(4)  # inside: still some wall


def test_without_a_path_the_door_is_on_the_longest_front_wall() -> None:
    a = _front(house({"ridge": RIDGE})).mesh
    b = _front(house({"ridge": RIDGE, "door_wall": 0})).mesh
    assert a == b


def test_a_door_wall_out_of_range_falls_back_to_the_front() -> None:
    assert _front(house({"ridge": RIDGE, "door_wall": 99})).mesh == _front(house({"ridge": RIDGE})).mesh


def test_a_garage_gets_a_garage_door() -> None:
    assert SPECS["GARAGE_SHED"].garage and not SPECS["HOUSE"].garage
    mesh = facade("GARAGE_SHED", rectangle(400.0, 600.0), lambda p: np.full(len(p), 230.0), 0)
    points = mesh.positions
    wide = points[points[:, 1] < -299.0]
    assert float(np.ptp(wide[:, 0])) == pytest.approx(SPECS["GARAGE_SHED"].door_w)  # 250 cm wide


def test_the_facade_is_one_flat_mesh_call() -> None:
    """Every box of a facade is batched: the building builder stays inside the
    clock-free call budget of the built world (tests/perf)."""
    import cProfile
    import pstats

    record = house({"ridge": RIDGE})
    profile = cProfile.Profile()
    profile.enable()
    _front(record)
    profile.disable()
    stats = pstats.Stats(profile)
    calls = sum(count for (_file, _line, name), (count, *_rest) in stats.stats.items()  # type: ignore[attr-defined]
                if name == "flat_mesh")
    assert calls <= 8  # the walls, the roof's pieces and ONE for the facade
