"""Unit tests for the Agent API create_object parameter layer (Qt-free logic).

Also guards the inlined object-type name sets against drift from the real
``ObjectType`` definitions (``creates`` inlines them to stay Qt-free, mirroring
``mapping.py`` and its drift guard).
"""

from __future__ import annotations

import math

import pytest

from open_garden_planner.agent_api.creates import (
    _CIRCLE_TYPE_NAMES,
    _PLANT_TYPE_NAMES,
    _RECT_TYPE_NAMES,
    _SOIL_CONTAINER_TYPE_NAMES,
    CREATABLE_TYPE_NAMES,
    build_create_dict,
    is_plant_type_name,
)


class TestNameSetDriftGuard:
    """``creates`` inlines the type-name sets; assert they still match source."""

    def test_soil_container_names_match_source(self) -> None:
        from open_garden_planner.core.object_types import SOIL_CONTAINER_TYPES

        assert {t.name for t in SOIL_CONTAINER_TYPES} == _SOIL_CONTAINER_TYPE_NAMES

    def test_plant_names_match_is_plant_type(self) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        assert {t.name for t in ObjectType if is_plant_type(t)} == _PLANT_TYPE_NAMES

    def test_creatable_set_is_exactly_plants_plus_soil_containers(self) -> None:
        """The agreed US-D2.1 scope. Widening it is a deliberate act, not a typo."""
        assert CREATABLE_TYPE_NAMES == _PLANT_TYPE_NAMES | _SOIL_CONTAINER_TYPE_NAMES

    def test_shape_sets_partition_the_creatable_set(self) -> None:
        """Every creatable type is built as exactly one shape — a type in both
        sets (or neither) would be silently unbuildable or ambiguous."""
        assert _CIRCLE_TYPE_NAMES | _RECT_TYPE_NAMES == CREATABLE_TYPE_NAMES
        assert not (_CIRCLE_TYPE_NAMES & _RECT_TYPE_NAMES)

    def test_every_creatable_type_actually_exists_as_an_object_type(self) -> None:
        from open_garden_planner.core.object_types import ObjectType

        for name in CREATABLE_TYPE_NAMES:
            assert ObjectType[name] is not None


class TestPlantCircles:
    @pytest.mark.parametrize(
        ("object_type", "expected_radius"),
        [("TREE", 100.0), ("SHRUB", 50.0), ("PERENNIAL", 30.0)],
    )
    def test_default_radius_mirrors_the_gallery_drop_defaults(
        self, object_type: str, expected_radius: float
    ) -> None:
        """The GUI drop path's size_map is in DIAMETERS (200/100/60)."""
        spec = build_create_dict(object_type=object_type, x=10.0, y=20.0)
        assert spec["type"] == "circle"
        assert spec["radius"] == expected_radius
        assert spec["center_x"] == 10.0
        assert spec["center_y"] == 20.0
        assert spec["object_type"] == object_type

    def test_explicit_radius_wins(self) -> None:
        spec = build_create_dict(object_type="TREE", x=0.0, y=0.0, radius=7.5)
        assert spec["radius"] == 7.5

    def test_name_is_passed_through_only_when_given(self) -> None:
        assert "name" not in build_create_dict(object_type="TREE", x=0.0, y=0.0)
        spec = build_create_dict(object_type="TREE", x=0.0, y=0.0, name="Old Oak")
        assert spec["name"] == "Old Oak"

    def test_rectangular_dimensions_are_refused(self) -> None:
        with pytest.raises(ValueError, match="round"):
            build_create_dict(object_type="TREE", x=0.0, y=0.0, width=10.0)
        with pytest.raises(ValueError, match="round"):
            build_create_dict(object_type="TREE", x=0.0, y=0.0, height=10.0)


class TestRoundContainer:
    def test_radius_is_required_no_invented_default(self) -> None:
        """Unlike plants, a pot has no house-default size to fall back on."""
        with pytest.raises(ValueError, match="requires an explicit 'radius'"):
            build_create_dict(object_type="CONTAINER_ROUND", x=0.0, y=0.0)

    def test_builds_a_circle_with_the_given_radius(self) -> None:
        spec = build_create_dict(object_type="CONTAINER_ROUND", x=5.0, y=6.0, radius=25.0)
        assert spec["type"] == "circle"
        assert spec["radius"] == 25.0


class TestRectangles:
    @pytest.mark.parametrize("object_type", sorted(_RECT_TYPE_NAMES))
    def test_centre_converts_to_the_serialised_top_left_anchor(
        self, object_type: str
    ) -> None:
        """The API speaks centres; the serialiser stores an anchor + extent.

        ``anchor = centre - extent/2`` holds whichever way y is read, so this
        conversion cannot introduce a Y-flip bug (see the module docstring).
        """
        spec = build_create_dict(
            object_type=object_type, x=100.0, y=200.0, width=40.0, height=60.0
        )
        assert spec["type"] == "rectangle"
        assert spec["x"] == 80.0
        assert spec["y"] == 170.0
        assert spec["width"] == 40.0
        assert spec["height"] == 60.0
        # Round-trip: the stored anchor + half-extent returns the requested centre.
        assert spec["x"] + spec["width"] / 2 == 100.0
        assert spec["y"] + spec["height"] / 2 == 200.0

    def test_both_dimensions_are_required(self) -> None:
        with pytest.raises(ValueError, match="requires both 'width' and 'height'"):
            build_create_dict(object_type="GARDEN_BED", x=0.0, y=0.0, width=40.0)
        with pytest.raises(ValueError, match="requires both 'width' and 'height'"):
            build_create_dict(object_type="GARDEN_BED", x=0.0, y=0.0, height=40.0)

    def test_radius_is_refused(self) -> None:
        with pytest.raises(ValueError, match="rectangular"):
            build_create_dict(
                object_type="GARDEN_BED", x=0.0, y=0.0, width=1.0, height=1.0, radius=5.0
            )


class TestRejections:
    def test_unsupported_type_lists_what_is_supported(self) -> None:
        with pytest.raises(ValueError) as exc:
            build_create_dict(object_type="HOUSE", x=0.0, y=0.0, width=1.0, height=1.0)
        message = str(exc.value)
        assert "HOUSE" in message
        # The error must be actionable: it names every type that IS creatable.
        for name in CREATABLE_TYPE_NAMES:
            assert name in message

    def test_unknown_type_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot create"):
            build_create_dict(object_type="NOT_A_REAL_TYPE", x=0.0, y=0.0)

    @pytest.mark.parametrize("bad", [0.0, -1.0, -0.001])
    def test_non_positive_extents_are_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="greater than 0"):
            build_create_dict(object_type="TREE", x=0.0, y=0.0, radius=bad)
        with pytest.raises(ValueError, match="greater than 0"):
            build_create_dict(
                object_type="GARDEN_BED", x=0.0, y=0.0, width=bad, height=10.0
            )

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_numbers_are_refused_before_reaching_qt(self, bad: float) -> None:
        """NaN/inf geometry corrupts a scene silently rather than failing loudly."""
        with pytest.raises(ValueError, match="finite"):
            build_create_dict(object_type="TREE", x=bad, y=0.0)
        with pytest.raises(ValueError, match="finite"):
            build_create_dict(object_type="TREE", x=0.0, y=bad)
        with pytest.raises(ValueError, match="finite"):
            build_create_dict(object_type="TREE", x=0.0, y=0.0, radius=bad)


class TestIsPlantTypeName:
    def test_plants_are_plants_and_containers_are_not(self) -> None:
        assert is_plant_type_name("TREE")
        assert is_plant_type_name("SHRUB")
        assert is_plant_type_name("PERENNIAL")
        assert not is_plant_type_name("GARDEN_BED")
        assert not is_plant_type_name("CONTAINER_ROUND")
        assert not is_plant_type_name("NOT_A_REAL_TYPE")
