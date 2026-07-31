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
    _MAX_PLANT_DIAMETER_CM,
    _PLANT_TYPE_NAMES,
    _RECT_TYPE_NAMES,
    _SOIL_CONTAINER_TYPE_NAMES,
    CREATABLE_TYPE_NAMES,
    build_create_dict,
    is_plant_type_name,
)

# A roomy default plan (1000 x 600 cm) for cases where bounds aren't the point.
_CANVAS = {"canvas_width_cm": 1000.0, "canvas_height_cm": 600.0}


def _build(**kwargs: object) -> dict:
    """``build_create_dict`` with a default canvas; bounds tests override it."""
    return build_create_dict(**{**_CANVAS, **kwargs})  # type: ignore[arg-type]


class TestNameSetDriftGuard:
    """``creates`` inlines the type-name sets; assert they still match source."""

    def test_soil_container_names_match_source(self) -> None:
        from open_garden_planner.core.object_types import SOIL_CONTAINER_TYPES

        assert {t.name for t in SOIL_CONTAINER_TYPES} == _SOIL_CONTAINER_TYPE_NAMES
        # Positive control: the comparison is a real equality, so dropping a
        # member from either side must fail it.
        assert {t.name for t in SOIL_CONTAINER_TYPES} != (
            _SOIL_CONTAINER_TYPE_NAMES - {"WALL_PLANTER"}
        )

    def test_plant_names_match_is_plant_type(self) -> None:
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        assert {t.name for t in ObjectType if is_plant_type(t)} == _PLANT_TYPE_NAMES

    def test_creatable_set_is_exactly_plants_plus_soil_containers(self) -> None:
        """The agreed US-D2.1 scope. Widening it is a deliberate act, not a typo."""
        assert CREATABLE_TYPE_NAMES == _PLANT_TYPE_NAMES | _SOIL_CONTAINER_TYPE_NAMES

    def test_shape_sets_are_disjoint(self) -> None:
        """A type in BOTH shape sets would build ambiguously.

        Note the union half of this property is not asserted: `CREATABLE_TYPE_NAMES`
        is *defined* as the union at `creates.py`, so asserting it would be a
        tautology that can never fail. Disjointness is the real content.
        """
        assert not (_CIRCLE_TYPE_NAMES & _RECT_TYPE_NAMES)

    def test_every_creatable_type_actually_exists_as_an_object_type(self) -> None:
        """A typo'd name in either shape set must fail here, not at runtime.

        The `ObjectType[name]` subscript is doing the work — it raises KeyError
        on an unknown name. The positive control below proves that.
        """
        from open_garden_planner.core.object_types import ObjectType

        for name in CREATABLE_TYPE_NAMES:
            ObjectType[name]

        # Positive control: feed the detector the exact drift it exists to catch.
        with pytest.raises(KeyError):
            ObjectType["GARDEN_BEDD"]


class TestPlantCircles:
    @pytest.mark.parametrize(
        ("object_type", "expected_radius"),
        [("TREE", 100.0), ("SHRUB", 50.0), ("PERENNIAL", 30.0)],
    )
    def test_default_radius_mirrors_the_gallery_drop_defaults(
        self, object_type: str, expected_radius: float
    ) -> None:
        """The GUI drop path's size_map is in DIAMETERS (200/100/60)."""
        spec = _build(object_type=object_type, x=10.0, y=20.0)
        assert spec["type"] == "circle"
        assert spec["radius"] == expected_radius
        assert spec["center_x"] == 10.0
        assert spec["center_y"] == 20.0
        assert spec["object_type"] == object_type

    def test_explicit_radius_wins(self) -> None:
        spec = _build(object_type="TREE", x=0.0, y=0.0, radius=7.5)
        assert spec["radius"] == 7.5

    def test_name_is_passed_through_only_when_given(self) -> None:
        assert "name" not in _build(object_type="TREE", x=0.0, y=0.0)
        spec = _build(object_type="TREE", x=0.0, y=0.0, name="Old Oak")
        assert spec["name"] == "Old Oak"

    def test_rectangular_dimensions_are_refused(self) -> None:
        with pytest.raises(ValueError, match="round"):
            _build(object_type="TREE", x=0.0, y=0.0, width=10.0)
        with pytest.raises(ValueError, match="round"):
            _build(object_type="TREE", x=0.0, y=0.0, height=10.0)


class TestRoundContainer:
    def test_radius_is_required_no_invented_default(self) -> None:
        """Unlike plants, a pot has no house-default size to fall back on."""
        with pytest.raises(ValueError, match="requires an explicit 'radius'"):
            _build(object_type="CONTAINER_ROUND", x=0.0, y=0.0)

    def test_builds_a_circle_with_the_given_radius(self) -> None:
        spec = _build(object_type="CONTAINER_ROUND", x=5.0, y=6.0, radius=25.0)
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
        spec = _build(
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
            _build(object_type="GARDEN_BED", x=0.0, y=0.0, width=40.0)
        with pytest.raises(ValueError, match="requires both 'width' and 'height'"):
            _build(object_type="GARDEN_BED", x=0.0, y=0.0, height=40.0)

    def test_radius_is_refused(self) -> None:
        with pytest.raises(ValueError, match="rectangular"):
            _build(
                object_type="GARDEN_BED", x=0.0, y=0.0, width=1.0, height=1.0, radius=5.0
            )


class TestRejections:
    def test_unsupported_type_lists_what_is_supported(self) -> None:
        with pytest.raises(ValueError) as exc:
            _build(object_type="HOUSE", x=0.0, y=0.0, width=1.0, height=1.0)
        message = str(exc.value)
        assert "HOUSE" in message
        # The error must be actionable: it names every type that IS creatable.
        for name in CREATABLE_TYPE_NAMES:
            assert name in message

    def test_unknown_type_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot create"):
            _build(object_type="NOT_A_REAL_TYPE", x=0.0, y=0.0)

    @pytest.mark.parametrize("bad", [0.0, -1.0, -0.001])
    def test_non_positive_extents_are_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="greater than 0"):
            _build(object_type="TREE", x=0.0, y=0.0, radius=bad)
        with pytest.raises(ValueError, match="greater than 0"):
            _build(
                object_type="GARDEN_BED", x=0.0, y=0.0, width=bad, height=10.0
            )

    @pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
    def test_non_finite_numbers_are_refused_before_reaching_qt(self, bad: float) -> None:
        """NaN/inf geometry corrupts a scene silently rather than failing loudly."""
        with pytest.raises(ValueError, match="finite"):
            _build(object_type="TREE", x=bad, y=0.0)
        with pytest.raises(ValueError, match="finite"):
            _build(object_type="TREE", x=0.0, y=bad)
        with pytest.raises(ValueError, match="finite"):
            _build(object_type="TREE", x=0.0, y=0.0, radius=bad)


class TestSanityBounds:
    """Finite and positive is not the same as plausible. An agent is exactly
    where a metres-for-centimetres unit slip shows up."""

    def test_plant_diameter_is_capped_to_bound_the_pixmap_allocation(self) -> None:
        """A plant's footprint feeds render_plant_pixmap, which allocates an
        `int(diameter)` square ARGB QImage from scene CM on the Qt main thread
        -- quadratic. radius=10000 (a 100 m tree) is the shape of the slip.
        """
        with pytest.raises(ValueError, match="CENTIMETRES"):
            _build(object_type="TREE", x=100.0, y=100.0, radius=10000.0)

    def test_the_plant_cap_is_the_documented_constant(self) -> None:
        """Just inside passes, just outside raises -- so the bound is real and
        the constant is the one actually enforced."""
        big_canvas = {"canvas_width_cm": 100000.0, "canvas_height_cm": 100000.0}
        ok = build_create_dict(  # type: ignore[call-overload]
            object_type="TREE", x=0.0, y=0.0,
            radius=_MAX_PLANT_DIAMETER_CM / 2, **big_canvas,
        )
        assert ok["radius"] == _MAX_PLANT_DIAMETER_CM / 2
        with pytest.raises(ValueError, match="may not exceed"):
            build_create_dict(  # type: ignore[call-overload]
                object_type="TREE", x=0.0, y=0.0,
                radius=_MAX_PLANT_DIAMETER_CM / 2 + 1, **big_canvas,
            )

    def test_extent_is_capped_relative_to_the_plan(self) -> None:
        # 2x the larger canvas dimension (1000) = 2000 cm limit.
        assert _build(object_type="GARDEN_BED", x=0.0, y=0.0, width=2000.0, height=10.0)
        with pytest.raises(ValueError, match="implausibly large"):
            _build(object_type="GARDEN_BED", x=0.0, y=0.0, width=2001.0, height=10.0)

    def test_the_size_error_names_the_actual_plan_size(self) -> None:
        """An actionable error: it tells the agent what the plan really is."""
        with pytest.raises(ValueError) as exc:
            _build(object_type="GARDEN_BED", x=0.0, y=0.0, width=99999.0, height=10.0)
        assert "1000" in str(exc.value) and "600" in str(exc.value)

    def test_a_bed_may_span_the_whole_plan(self) -> None:
        """The cap must not refuse a legitimate plot-spanning bed."""
        spec = _build(
            object_type="GARDEN_BED", x=500.0, y=300.0, width=1000.0, height=600.0
        )
        assert spec["width"] == 1000.0

    @pytest.mark.parametrize(
        ("x", "y"),
        [(1e9, 100.0), (100.0, 1e9), (-5000.0, 100.0), (100.0, -2000.0)],
    )
    def test_unreachable_positions_are_refused(self, x: float, y: float) -> None:
        """An object at 1e9 is invisible, unselectable and un-deletable in the
        GUI -- reporting success there would be a lie."""
        with pytest.raises(ValueError, match="too far outside the plan"):
            _build(object_type="TREE", x=x, y=y)

    def test_one_canvas_of_slack_is_allowed_for_staging(self) -> None:
        assert _build(object_type="TREE", x=-999.0, y=-599.0)
        assert _build(object_type="TREE", x=1999.0, y=1199.0)


class TestIsPlantTypeName:
    def test_plants_are_plants_and_containers_are_not(self) -> None:
        assert is_plant_type_name("TREE")
        assert is_plant_type_name("SHRUB")
        assert is_plant_type_name("PERENNIAL")
        assert not is_plant_type_name("GARDEN_BED")
        assert not is_plant_type_name("CONTAINER_ROUND")
        assert not is_plant_type_name("NOT_A_REAL_TYPE")
