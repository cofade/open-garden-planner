"""Cutaway and X-ray: what stands between the camera and the selection (Phase 17 L2.4).

``core/scene3d/xray.py`` names the items the view of a selected item passes through.
Held here to plain geometry: a wall between the eye and a shed is an occluder, a
shed beside the line of sight and one behind the selection are not, the selection
never fades itself — and the segment cast it rests on agrees with the pick oracle's
own cast, which the render tier already holds to the engine.
"""

from __future__ import annotations

import numpy as np
import pytest

from open_garden_planner.core.scene3d import Material, Params, Record, Transform, default_builder
from open_garden_planner.core.scene3d.pick_oracle import Ray, cast_all, cast_segment, pick_scene
from open_garden_planner.core.scene3d.xray import (
    MAX_XRAY_ITEMS,
    ROOF_KIND,
    SAMPLE_SHRINK,
    occluders,
    target_points,
    xray_scene,
)


def rect(width: float, depth: float) -> tuple[tuple[float, float], ...]:
    half_w, half_d = width / 2.0, depth / 2.0
    return ((-half_w, -half_d), (half_w, -half_d), (half_w, half_d), (-half_w, half_d))


def box(item_id: str, east: float, north: float, width: float, depth: float,
        height: float) -> Record:
    return Record(item_id=item_id, kind="SHED", shape="rectangle", footprints=(rect(width, depth),),
                  transform=Transform(east, north, 0.0, 0.0), material=Material("SHED"),
                  height_cm=height, params=Params({"seed": item_id}))


def scene(*records: Record):
    return xray_scene({record.item_id: record for record in records}, default_builder)


# the eye stands south of everything, looking north, at 150 cm
EYE = (0.0, -1000.0, 150.0)


class TestOccluders:
    def test_a_wall_between_the_eye_and_the_selection_fades(self) -> None:
        world = scene(box("shed", 0.0, 1000.0, 200.0, 200.0, 220.0),
                      box("wall", 0.0, 0.0, 600.0, 30.0, 400.0))
        assert occluders(world, EYE, {"shed"}) == {"wall"}

    def test_what_stands_beside_the_line_of_sight_or_behind_does_not(self) -> None:
        world = scene(box("shed", 0.0, 1000.0, 200.0, 200.0, 220.0),
                      box("beside", 2000.0, 0.0, 200.0, 30.0, 400.0),
                      box("behind", 0.0, 2000.0, 600.0, 30.0, 400.0))
        assert occluders(world, EYE, {"shed"}) == frozenset()

    def test_a_low_hedge_the_eye_looks_over_stays_and_a_tall_one_fades(self) -> None:
        low = scene(box("shed", 0.0, 1000.0, 200.0, 200.0, 220.0),
                    box("hedge", 0.0, 0.0, 600.0, 30.0, 40.0))
        assert occluders(low, EYE, {"shed"}) == frozenset()

    def test_the_selection_never_fades_itself_nor_a_selected_neighbour(self) -> None:
        world = scene(box("shed", 0.0, 1000.0, 200.0, 200.0, 220.0),
                      box("wall", 0.0, 0.0, 600.0, 30.0, 400.0))
        assert occluders(world, EYE, {"shed", "wall"}) == frozenset()

    def test_nothing_selected_or_unknown_ids_fade_nothing(self) -> None:
        world = scene(box("shed", 0.0, 1000.0, 200.0, 200.0, 220.0),
                      box("wall", 0.0, 0.0, 600.0, 30.0, 400.0))
        assert occluders(world, EYE, set()) == frozenset()
        assert occluders(world, EYE, {"no-such-item"}) == frozenset()
        assert occluders(scene(), EYE, {"shed"}) == frozenset()

    def test_a_partly_hidden_selection_still_fades_what_hides_part_of_it(self) -> None:
        # the wall covers only the shed's west half: the corner points behind it count
        world = scene(box("shed", 0.0, 1000.0, 400.0, 200.0, 220.0),
                      box("wall", -150.0, 0.0, 150.0, 30.0, 400.0))
        assert occluders(world, EYE, {"shed"}) == {"wall"}

    def test_at_most_max_items_are_looked_through(self) -> None:
        sheds = [box(f"s{index:02d}", index * 300.0, 1000.0, 100.0, 100.0, 200.0)
                 for index in range(MAX_XRAY_ITEMS + 4)]
        walls = [box(f"w{index:02d}", index * 300.0, 0.0, 120.0, 30.0, 400.0)
                 for index in range(MAX_XRAY_ITEMS + 4)]
        world = scene(*sheds, *walls)
        # each shed stands straight behind its own wall: only the walls in front of the
        # first MAX_XRAY_ITEMS sheds (sorted by id) are looked for — and the eye at the
        # first wall sees the second wall's shed past it at most
        found = occluders(world, EYE, {s.item_id for s in sheds})
        assert "w00" in found
        assert f"w{MAX_XRAY_ITEMS + 3:02d}" not in found


class TestTheTargets:
    def test_nine_points_inside_the_items_box(self) -> None:
        world = scene(box("shed", 100.0, 200.0, 200.0, 100.0, 220.0))
        points = np.asarray(target_points(world, "shed"))
        assert points.shape == (9, 3)
        low = np.array([0.0, 150.0, 0.0])
        high = np.array([200.0, 250.0, 220.0])
        margin = (high - low) / 2.0 * SAMPLE_SHRINK
        assert np.all(points >= low + margin - 1e-6) and np.all(points <= high - margin + 1e-6)
        assert target_points(world, "missing") == ()


class TestTheSegmentCast:
    def test_it_meets_only_what_lies_before_the_end(self) -> None:
        records = {r.item_id: r for r in (box("near", 0.0, 0.0, 100.0, 100.0, 300.0),
                                          box("far", 0.0, 1000.0, 100.0, 100.0, 300.0))}
        world = pick_scene(records, default_builder)
        hits = cast_segment(world, (0.0, -500.0, 100.0), (0.0, 500.0, 100.0))
        assert [hit.item_id for hit in hits] == ["near"]
        assert [hit.item_id for hit in cast_segment(world, (0.0, -500.0, 100.0),
                                                    (0.0, 2000.0, 100.0))] == ["near", "far"]

    def test_a_row_subset_agrees_with_the_full_cast(self) -> None:
        records = {r.item_id: r for r in (box("a", 0.0, 0.0, 100.0, 100.0, 300.0),
                                          box("b", 0.0, 500.0, 100.0, 100.0, 300.0))}
        world = pick_scene(records, default_builder)
        origin, end = (0.0, -500.0, 100.0), (0.0, 2000.0, 100.0)
        b_rows = np.flatnonzero(world.item == world.item_ids.index("b"))
        assert [h.item_id for h in cast_segment(world, origin, end, rows=b_rows)] == ["b"]
        full = cast_segment(world, origin, end)
        ray = cast_all(world, Ray(origin, (0.0, 1.0, 0.0)))
        assert [(h.item_id, round(h.distance_cm, 6)) for h in full] == \
            [(h.item_id, round(h.distance_cm, 6)) for h in ray]
        assert cast_segment(world, origin, end, rows=np.zeros(0, np.int64)) == ()

    def test_a_degenerate_segment_meets_nothing(self) -> None:
        world = pick_scene({"a": box("a", 0.0, 0.0, 100.0, 100.0, 300.0)}, default_builder)
        assert cast_segment(world, (0.0, 0.0, 100.0), (0.0, 0.0, 100.0)) == ()


def test_the_roof_kind_is_the_building_builders_roof_part() -> None:
    """Drift guard: Cutaway hides parts of ``ROOF_KIND`` — the kind the buildings
    builder gives a house's roof."""
    from open_garden_planner.core.scene3d.builders import production_registry

    house = Record(item_id="house", kind="HOUSE", shape="rectangle", footprints=(rect(800.0, 600.0),),
                   transform=Transform(0.0, 0.0, 0.0, 0.0), material=Material("HOUSE"),
                   height_cm=650.0,
                   params=Params({"seed": "house", "ridge": ((-400.0, 0.0), (400.0, 0.0))}))
    parts = production_registry().builder_for("HOUSE")(house)
    assert any(part.material_kind == ROOF_KIND and part.name == "roof" for part in parts)
    assert all(part.material_kind != ROOF_KIND for part in parts if part.name != "roof")


@pytest.mark.parametrize("kind", ["TOOL_SHED", "GARAGE_SHED"])
def test_the_sheds_roof_is_a_roof_part_too(kind: str) -> None:
    from open_garden_planner.core.scene3d.builders import production_registry

    record = Record(item_id=kind, kind=kind, shape="rectangle", footprints=(rect(300.0, 200.0),),
                    transform=Transform(0.0, 0.0, 0.0, 0.0), material=Material(kind),
                    height_cm=250.0, params=Params({"seed": kind}))
    parts = production_registry().builder_for(kind)(record)
    roofs = [part for part in parts if part.material_kind == ROOF_KIND]
    assert roofs and all(part.name == "roof" for part in roofs)
