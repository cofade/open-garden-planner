"""What a spacing overlap means (#786): storeys, and where the warning is drawn.

``core.plant_sizing`` owns both rules and is Qt-free:

* two plants conflict only within one storey - a tree and what grows under its
  crown share the ground on purpose;
* the warning is drawn on the arcs of a plant's spacing circle that lie inside
  a conflicting neighbour's circle, not all round the plant.
"""

from __future__ import annotations

import math

import pytest

from open_garden_planner.core.plant_sizing import (
    OVERSTOREY,
    UNDERSTOREY,
    spacing_conflict_arcs,
    spacing_storey,
    spacings_conflict,
)
from open_garden_planner.models.plant_data import PermacultureLayer


class TestSpacingStorey:
    @pytest.mark.parametrize(
        ("layer", "expected"),
        [
            ("canopy", OVERSTOREY),
            ("sub_canopy", OVERSTOREY),
            ("shrub", UNDERSTOREY),
            ("herbaceous", UNDERSTOREY),
            ("ground_cover", UNDERSTOREY),
            ("root", UNDERSTOREY),
            ("vine", UNDERSTOREY),
        ],
    )
    def test_the_recorded_layer_decides_whatever_the_plant_was_drawn_as(
        self, layer: str, expected: str
    ) -> None:
        for drawn_as in ("TREE", "SHRUB", "PERENNIAL"):
            assert spacing_storey({"permaculture_layer": layer}, drawn_as) == expected

    @pytest.mark.parametrize("species", [None, {}, {"permaculture_layer": "unknown"},
                                         {"permaculture_layer": None}, {"permaculture_layer": 7}])
    def test_without_a_layer_the_drawn_type_decides(self, species) -> None:
        assert spacing_storey(species, "TREE") == OVERSTOREY
        assert spacing_storey(species, "SHRUB") == UNDERSTOREY
        assert spacing_storey(species, "PERENNIAL") == UNDERSTOREY
        assert spacing_storey(species, "") == UNDERSTOREY

    def test_every_layer_of_the_model_has_a_storey(self) -> None:
        """A layer added to the model must be sorted into a storey here."""
        from open_garden_planner.core.plant_sizing import OVERSTOREY_LAYERS, UNDERSTOREY_LAYERS

        known = {layer.value for layer in PermacultureLayer} - {"unknown"}
        assert known == OVERSTOREY_LAYERS | UNDERSTOREY_LAYERS
        assert not OVERSTOREY_LAYERS & UNDERSTOREY_LAYERS


class TestSpacingsConflict:
    def test_two_trees_closer_than_their_spreads_conflict(self) -> None:
        assert spacings_conflict(393.0, 350.0, 300.0, OVERSTOREY, OVERSTOREY)

    def test_a_tree_over_its_understorey_is_no_conflict(self) -> None:
        # the food-forest guild: a strawberry 2.3 m from a 3 m apple crown
        assert not spacings_conflict(230.0, 300.0, 30.0, OVERSTOREY, UNDERSTOREY)
        assert not spacings_conflict(230.0, 30.0, 300.0, UNDERSTOREY, OVERSTOREY)

    def test_two_understorey_plants_still_conflict(self) -> None:
        assert spacings_conflict(82.0, 60.0, 50.0, UNDERSTOREY, UNDERSTOREY)

    def test_touching_circles_are_the_intended_distance(self) -> None:
        assert not spacings_conflict(100.0, 60.0, 40.0, UNDERSTOREY, UNDERSTOREY)
        assert spacings_conflict(99.999, 60.0, 40.0, UNDERSTOREY, UNDERSTOREY)


def _covered(arcs: list[tuple[float, float]], angle: float) -> bool:
    return any((angle - start) % 360.0 <= span for start, span in arcs)


class TestSpacingConflictArcs:
    def test_no_neighbour_no_arc(self) -> None:
        assert spacing_conflict_arcs((0.0, 0.0), 100.0, []) == []

    def test_the_arc_faces_the_neighbour_and_ends_where_the_circles_cross(self) -> None:
        # two equal circles a radius apart cross at +-60 degrees
        arcs = spacing_conflict_arcs((0.0, 0.0), 100.0, [(100.0, 0.0, 100.0)])
        assert len(arcs) == 1
        start, span = arcs[0]
        assert start == pytest.approx(300.0)
        assert span == pytest.approx(120.0)

    @pytest.mark.parametrize("bearing", [0.0, 37.0, 90.0, 181.0, 275.0, 359.0])
    def test_every_point_of_an_arc_is_inside_the_neighbour_and_no_other_is(
        self, bearing: float
    ) -> None:
        radius, neighbour_radius, distance = 120.0, 80.0, 150.0
        nx = distance * math.cos(math.radians(bearing))
        ny = distance * math.sin(math.radians(bearing))
        arcs = spacing_conflict_arcs((10.0, -20.0), radius, [(10.0 + nx, -20.0 + ny, neighbour_radius)])
        for step in range(720):
            angle = step / 2.0
            px = 10.0 + radius * math.cos(math.radians(angle))
            py = -20.0 + radius * math.sin(math.radians(angle))
            inside = math.hypot(px - (10.0 + nx), py - (-20.0 + ny)) < neighbour_radius - 1e-6
            outside = math.hypot(px - (10.0 + nx), py - (-20.0 + ny)) > neighbour_radius + 1e-6
            if inside:
                assert _covered(arcs, angle), (bearing, angle)
            if outside:
                assert not _covered(arcs, angle), (bearing, angle)

    def test_a_circle_inside_its_neighbours_is_marked_all_round(self) -> None:
        assert spacing_conflict_arcs((0.0, 0.0), 50.0, [(20.0, 0.0, 300.0)]) == [(0.0, 360.0)]

    def test_a_circle_that_holds_its_neighbour_has_nothing_inside_it(self) -> None:
        assert spacing_conflict_arcs((0.0, 0.0), 300.0, [(20.0, 0.0, 50.0)]) == []

    def test_circles_that_do_not_meet_give_no_arc(self) -> None:
        # a trellis measures along its bar: the pair conflicts, the circles do not cross
        assert spacing_conflict_arcs((0.0, 0.0), 20.0, [(0.0, 195.0, 20.0)]) == []

    def test_arcs_of_two_neighbours_merge_where_they_overlap(self) -> None:
        arcs = spacing_conflict_arcs(
            (0.0, 0.0), 100.0, [(100.0, 0.0, 100.0), (70.7, 70.7, 100.0)]
        )
        assert len(arcs) == 1
        start, span = arcs[0]
        assert start == pytest.approx(300.0)
        assert span == pytest.approx(165.0, abs=0.1)

    def test_an_arc_across_zero_degrees_stays_one_arc(self) -> None:
        arcs = spacing_conflict_arcs(
            (0.0, 0.0), 100.0, [(100.0, 10.0, 100.0), (100.0, -10.0, 100.0)]
        )
        assert len(arcs) == 1
        assert _covered(arcs, 0.0) and _covered(arcs, 359.0) and not _covered(arcs, 180.0)

    def test_neighbours_all_round_mark_the_whole_circle(self) -> None:
        ring = [
            (100.0 * math.cos(math.radians(a)), 100.0 * math.sin(math.radians(a)), 100.0)
            for a in range(0, 360, 60)
        ]
        assert spacing_conflict_arcs((0.0, 0.0), 100.0, ring) == [(0.0, 360.0)]
