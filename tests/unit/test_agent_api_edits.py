"""Unit tests for ``agent_api.edits`` — the Agent API's edit-tool validation.

Three jobs, mirroring ``test_agent_api_creates.py``:

  * **drift guards** on the object-type name sets this module inlines to stay
    Qt-free — the inlining is only safe because these fail when the real
    ``ObjectType`` definitions move;
  * **validation** of resize dimensions and rotation angles;
  * **the rotation sign convention**, pinned against a real item's measured
    corner position rather than against the stored angle. Issue #267 is the
    reason: a plausible-sounding docstring that mis-stated the coordinate frame
    sent agents the wrong way for a whole release.
"""

from __future__ import annotations

import math

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api.edits import (
    MAX_ABSOLUTE_ROTATION_DEG,
    PLANT_PARENT_TYPE_NAMES,
    is_plant_parent_type_name,
    normalise_angle_deg,
    require_plant_parent_type,
    validate_resize_request,
    validate_rotation,
)
from open_garden_planner.core.object_types import ObjectType, is_plant_parent_type

_CANVAS = {"canvas_width_cm": 2000.0, "canvas_height_cm": 1500.0}


class TestTypeSetDriftGuards:
    """The inlined name sets must match the real ObjectType definitions."""

    def test_plant_parent_names_match_the_enum(self) -> None:
        assert {
            t.name for t in ObjectType if is_plant_parent_type(t)
        } == PLANT_PARENT_TYPE_NAMES

    def test_trellis_is_a_plant_parent_but_not_a_soil_container(self) -> None:
        """The asymmetry section 8.14 / ADR-017 calls out explicitly: a plant on
        a trellis has a parent but no soil, so set_parent_bed must accept it."""
        from open_garden_planner.core.object_types import SOIL_CONTAINER_TYPES

        assert "TRELLIS" in PLANT_PARENT_TYPE_NAMES
        assert ObjectType.TRELLIS not in SOIL_CONTAINER_TYPES

    def test_predicate_agrees_with_the_set(self) -> None:
        assert is_plant_parent_type_name("GARDEN_BED")
        assert is_plant_parent_type_name("TRELLIS")
        assert not is_plant_parent_type_name("HOUSE")
        assert not is_plant_parent_type_name("NOT_A_REAL_TYPE")

    def test_require_plant_parent_type_names_the_offender_and_the_options(
        self,
    ) -> None:
        require_plant_parent_type("RAISED_BED", "some-id")  # no raise
        with pytest.raises(ValueError, match="HOUSE") as exc:
            require_plant_parent_type("HOUSE", "some-id")
        # The error must list what WOULD work, not just what didn't.
        assert "GARDEN_BED" in str(exc.value)
        assert "TRELLIS" in str(exc.value)


class TestRotationValidation:
    def test_absolute_replaces_and_relative_accumulates(self) -> None:
        assert validate_rotation(90, relative=False, current_angle=90) == 90
        assert validate_rotation(90, relative=True, current_angle=90) == 180

    def test_result_is_normalised_into_0_360(self) -> None:
        assert validate_rotation(90, relative=True, current_angle=300) == 30
        assert validate_rotation(-90, relative=False, current_angle=0) == 270
        assert validate_rotation(360, relative=False, current_angle=0) == 0

    def test_normalise_is_exposed_and_consistent(self) -> None:
        for angle in (-720.0, -1.0, 0.0, 359.9, 360.0, 725.0):
            folded = normalise_angle_deg(angle)
            assert 0.0 <= folded < 360.0
            assert math.isclose((angle - folded) % 360.0, 0.0, abs_tol=1e-9)

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_angle_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_rotation(bad, relative=False, current_angle=0)

    def test_implausibly_large_angle_is_refused_naming_degrees(self) -> None:
        with pytest.raises(ValueError, match="DEGREES"):
            validate_rotation(
                MAX_ABSOLUTE_ROTATION_DEG + 1, relative=False, current_angle=0
            )


class TestResizeValidation:
    def test_round_object_takes_radius_and_returns_the_diameter(self) -> None:
        assert validate_resize_request(
            object_type="TREE",
            is_round=True,
            current_width=100,
            current_height=100,
            radius=75,
            **_CANVAS,
        ) == (150.0, 150.0)

    def test_round_object_refuses_width_height(self) -> None:
        with pytest.raises(ValueError, match="round"):
            validate_resize_request(
                object_type="TREE",
                is_round=True,
                current_width=100,
                current_height=100,
                width=50,
                **_CANVAS,
            )

    def test_round_object_needs_a_radius(self) -> None:
        with pytest.raises(ValueError, match="radius"):
            validate_resize_request(
                object_type="TREE",
                is_round=True,
                current_width=100,
                current_height=100,
                **_CANVAS,
            )

    def test_rectangular_object_refuses_radius(self) -> None:
        with pytest.raises(ValueError, match="rectangular"):
            validate_resize_request(
                object_type="GARDEN_BED",
                is_round=False,
                current_width=100,
                current_height=200,
                radius=50,
                **_CANVAS,
            )

    def test_one_axis_alone_leaves_the_other_unchanged(self) -> None:
        assert validate_resize_request(
            object_type="GARDEN_BED",
            is_round=False,
            current_width=100,
            current_height=200,
            width=150,
            **_CANVAS,
        ) == (150.0, 200.0)
        assert validate_resize_request(
            object_type="GARDEN_BED",
            is_round=False,
            current_width=100,
            current_height=200,
            height=250,
            **_CANVAS,
        ) == (100.0, 250.0)

    def test_no_dimension_at_all_is_refused(self) -> None:
        with pytest.raises(ValueError, match="width"):
            validate_resize_request(
                object_type="GARDEN_BED",
                is_round=False,
                current_width=100,
                current_height=200,
                **_CANVAS,
            )

    @pytest.mark.parametrize("bad", [0.0, -1.0])
    def test_non_positive_extent_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="greater than 0"):
            validate_resize_request(
                object_type="GARDEN_BED",
                is_round=False,
                current_width=100,
                current_height=200,
                width=bad,
                **_CANVAS,
            )

    @pytest.mark.parametrize("bad", [float("nan"), float("inf")])
    def test_non_finite_extent_is_refused(self, bad: float) -> None:
        with pytest.raises(ValueError, match="finite"):
            validate_resize_request(
                object_type="GARDEN_BED",
                is_round=False,
                current_width=100,
                current_height=200,
                width=bad,
                **_CANVAS,
            )

    def test_implausible_extent_is_refused_naming_centimetres(self) -> None:
        """The metres-typed-as-centimetres slip, refused with the plan's real
        size in the message — the same bound create_object already applies."""
        with pytest.raises(ValueError, match="CENTIMETRES"):
            validate_resize_request(
                object_type="GARDEN_BED",
                is_round=False,
                current_width=100,
                current_height=200,
                width=100_000,
                **_CANVAS,
            )

    def test_plant_diameter_cap_still_applies_on_resize(self) -> None:
        """A plant's footprint drives a quadratic QImage allocation, so it has a
        tighter absolute cap than the canvas-relative one. Resize must inherit
        it — create_object refusing an absurd plant is no use if resize doesn't."""
        from open_garden_planner.agent_api.creates import _MAX_PLANT_DIAMETER_CM

        big_canvas = {"canvas_width_cm": 100_000.0, "canvas_height_cm": 100_000.0}
        ok = validate_resize_request(
            object_type="TREE",
            is_round=True,
            current_width=100,
            current_height=100,
            radius=_MAX_PLANT_DIAMETER_CM / 2,
            **big_canvas,
        )
        assert ok == (_MAX_PLANT_DIAMETER_CM, _MAX_PLANT_DIAMETER_CM)
        with pytest.raises(ValueError, match="plant"):
            validate_resize_request(
                object_type="TREE",
                is_round=True,
                current_width=100,
                current_height=100,
                radius=(_MAX_PLANT_DIAMETER_CM / 2) + 1,
                **big_canvas,
            )


class TestRotationSignConvention:
    """The measured sign convention, pinned so it cannot silently invert.

    Asserted against a real item's CORNER POSITION before and after, not
    against the stored angle: storing 90 tells you nothing about which way the
    object actually turned, and "which way" is the whole contract the tool's
    docstring makes to an agent.
    """

    def test_positive_angle_turns_east_to_north(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation
        from open_garden_planner.ui.canvas.items import RectangleItem

        # A long, thin bed: its long axis points EAST (+x) at rotation 0.
        item = RectangleItem(0, 0, 100, 20, object_type=ObjectType.RAISED_BED)
        rect = item.rect()
        east_tip_local = QPointF(
            rect.x() + rect.width(), rect.y() + rect.height() / 2
        )

        before = item.mapToScene(east_tip_local)
        centre_before = item.mapToScene(rect.center())
        assert before.x() > centre_before.x(), "precondition: the tip starts east"

        apply_rotation(item, 90.0)

        after = item.mapToScene(east_tip_local)
        centre_after = item.mapToScene(item.rect().center())

        # The scene frame is CAD Y-up (ADR-002): a LARGER y is further north.
        assert after.y() > centre_after.y() + 1.0, (
            "+90 must send an east-pointing tip NORTH (counter-clockwise). If "
            "this fails the sign convention has inverted, and every "
            "rotate_object docstring is now wrong."
        )
        assert abs(after.x() - centre_after.x()) < 1e-6, (
            "+90 must leave the tip due north of the centre, not off to a side"
        )

    def test_rotation_pivots_about_the_centre_which_does_not_move(
        self, qtbot  # noqa: ARG002
    ) -> None:
        from open_garden_planner.ui.canvas.geometry_apply import apply_rotation
        from open_garden_planner.ui.canvas.items import RectangleItem

        item = RectangleItem(300, 400, 100, 20, object_type=ObjectType.RAISED_BED)
        before = item.mapToScene(item.rect().center())
        apply_rotation(item, 37.5)
        after = item.mapToScene(item.rect().center())
        assert abs(after.x() - before.x()) < 1e-6
        assert abs(after.y() - before.y()) < 1e-6
