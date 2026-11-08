"""#776: an object's art turns with its footprint — one rule for 2D and 3D.

A wheelbarrow's sprite is 60 x 140 cm (portrait). Drawn into a wide rectangle it
used to be squashed; since #776 the picture is rendered at the swapped size and
turned a quarter clockwise, and the 3D builder builds the same turned model.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QTransform

from open_garden_planner.core.furniture_renderer import render_furniture_pixmap
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d.builders import production_registry
from open_garden_planner.core.scene3d.builders.kit import object_box
from open_garden_planner.core.sprite_orientation import NATURAL_SIZE_CM, sprite_turn_deg
from tests.unit.scene3d_builder_cases import polygon_record, rectangle


class TestTheRule:
    def test_every_default_dimension_is_in_the_natural_table(self) -> None:
        """The renderer's defaults ARE the natural sizes (#776 moved them here)."""
        from open_garden_planner.core.furniture_renderer import FURNITURE_DEFAULT_DIMENSIONS

        assert {
            ObjectType[name]: size for name, size in NATURAL_SIZE_CM.items()
        } == FURNITURE_DEFAULT_DIMENSIONS

    @pytest.mark.parametrize(
        ("kind", "width", "height", "turn"),
        [
            # a portrait sprite on a wide rectangle: turn it
            ("WHEELBARROW", 140.0, 60.0, 90.0),
            ("LOUNGER", 190.0, 70.0, 90.0),
            # a landscape sprite on a tall rectangle: turn it
            ("BENCH", 60.0, 180.0, 90.0),
            ("HAMMOCK", 120.0, 300.0, 90.0),
            # the natural orientation, or the same aspect, is stretched as before
            ("WHEELBARROW", 60.0, 140.0, 0.0),
            ("BENCH", 180.0, 60.0, 0.0),
            ("BENCH", 300.0, 100.0, 0.0),
            ("BENCH", 100.0, 300.0, 90.0),
            # a near-square target has no long axis to follow
            ("WHEELBARROW", 100.0, 100.0, 0.0),
            ("WHEELBARROW", 100.0, 103.0, 0.0),
            # near-square natural art never turns
            ("HOT_TUB", 300.0, 100.0, 0.0),
            # a kind with no natural art, or no usable size
            ("UNKNOWN", 300.0, 100.0, 0.0),
            ("WHEELBARROW", 0.0, 100.0, 0.0),
            ("WHEELBARROW", float("nan"), 100.0, 0.0),
        ],
    )
    def test_the_quarter_turn(self, kind: str, width: float, height: float, turn: float) -> None:
        assert sprite_turn_deg(kind, width, height) == turn


class TestThe2DPicture:
    def test_a_turned_render_is_the_natural_pixmap_turned(self, qtbot: object) -> None:
        from PyQt6.QtCore import Qt

        natural = render_furniture_pixmap(ObjectType.WHEELBARROW, 60.0, 140.0)
        turned = render_furniture_pixmap(ObjectType.WHEELBARROW, 140.0, 60.0)
        assert natural is not None and turned is not None
        assert (natural.width(), natural.height()) == (60, 140)
        assert (turned.width(), turned.height()) == (140, 60)
        expected = natural.transformed(
            QTransform().rotate(90.0), Qt.TransformationMode.FastTransformation
        )
        assert turned.toImage() == expected.toImage()

    def test_a_natural_render_is_not_turned(self, qtbot: object) -> None:
        natural = render_furniture_pixmap(ObjectType.WHEELBARROW, 60.0, 140.0)
        assert natural is not None
        assert (natural.width(), natural.height()) == (60, 140)


class TestThe3DModel:
    @staticmethod
    def _built(kind: str, width: float, depth: float, height: float = 80.0) -> np.ndarray:
        record = polygon_record(kind, rectangle(width, depth), height, shape="rectangle")
        parts = production_registry().build(record)
        assert parts
        return np.concatenate([part.mesh.positions for part in parts])

    def test_the_box_builds_in_the_swapped_frame(self) -> None:
        natural = polygon_record("WHEELBARROW", rectangle(60.0, 140.0), 80.0, shape="rectangle")
        turned = polygon_record("WHEELBARROW", rectangle(140.0, 60.0), 80.0, shape="rectangle")
        natural_box = object_box(natural)
        turned_box = object_box(turned)
        assert natural_box is not None and not natural_box.turned
        assert turned_box is not None and turned_box.turned
        assert (turned_box.width, turned_box.depth) == (60.0, 140.0)

    def test_the_turned_model_fills_the_item_not_the_swapped_box(self) -> None:
        positions = self._built("WHEELBARROW", 140.0, 60.0)
        assert positions[:, 0].min() >= -70.01 and positions[:, 0].max() <= 70.01
        assert positions[:, 1].min() >= -30.01 and positions[:, 1].max() <= 30.01
        # the wheel end (the sprite's top, local +y in the build frame) lands at
        # the target's -x end after the clockwise turn
        assert positions[:, 2].max() == pytest.approx(80.0, rel=1e-4)

    def test_a_natural_model_is_unchanged(self) -> None:
        positions = self._built("WHEELBARROW", 60.0, 140.0)
        assert positions[:, 1].max() - positions[:, 1].min() > 100.0
        assert positions[:, 0].max() - positions[:, 0].min() <= 60.01

    def test_placed_turns_the_build_frame_clockwise(self) -> None:
        """The direction the 2D pixmap turns: (x, y) -> (y, -x), so the build
        frame's +x end lands at the target's -y end (and +y at +x)."""
        from open_garden_planner.core.scene3d import Mesh
        from open_garden_planner.core.scene3d.builders.kit import ObjectBox, placed

        mesh = Mesh.from_arrays(
            [[10.0, 0.0, 0.0], [10.0, 1.0, 0.0], [11.0, 0.0, 0.0]],
            [[0.0, 0.0, 1.0]] * 3,
            [[1.0, 1.0, 1.0, 1.0]] * 3,
            [[0.0, 0.0]] * 3,
            [0, 1, 2],
        )
        turned = placed([mesh], ObjectBox(0.0, 0.0, 5.0, 10.0, turned=True))
        assert turned.positions[0][0] == pytest.approx(0.0)
        assert turned.positions[0][1] == pytest.approx(-10.0)
        assert turned.positions[0][2] == pytest.approx(0.0)
