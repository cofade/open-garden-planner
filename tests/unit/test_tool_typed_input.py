"""Tests for the Package A BaseTool typed-input extensions."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.tools.circle_tool import CircleTool
from open_garden_planner.core.tools.construction_tool import (
    ConstructionCircleTool,
    ConstructionLineTool,
)
from open_garden_planner.core.tools.ellipse_tool import EllipseTool
from open_garden_planner.core.tools.polygon_tool import PolygonTool
from open_garden_planner.core.tools.polyline_tool import PolylineTool
from open_garden_planner.core.tools.rectangle_tool import RectangleTool
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView


@pytest.fixture
def view(qtbot) -> CanvasView:
    scene = CanvasScene(2000, 2000)
    v = CanvasView(scene)
    qtbot.addWidget(v)
    return v


class TestPolylineTypedInput:
    def test_last_point_initially_none(self, view: CanvasView) -> None:
        tool = PolylineTool(view)
        assert tool.last_point is None

    def test_commit_then_last_point(self, view: CanvasView) -> None:
        tool = PolylineTool(view)
        assert tool.commit_typed_coordinate(QPointF(100, 200)) is True
        assert tool.last_point == QPointF(100, 200)
        tool.commit_typed_coordinate(QPointF(500, 200))
        assert tool.last_point == QPointF(500, 200)


class TestPolygonTypedInput:
    def test_commit_sequence(self, view: CanvasView) -> None:
        tool = PolygonTool(view)
        assert tool.last_point is None
        tool.commit_typed_coordinate(QPointF(0, 0))
        tool.commit_typed_coordinate(QPointF(100, 0))
        tool.commit_typed_coordinate(QPointF(50, 100))
        assert tool.last_point == QPointF(50, 100)


class TestCircleTypedInput:
    def test_first_commit_sets_center(self, view: CanvasView) -> None:
        tool = CircleTool(view)
        tool.commit_typed_coordinate(QPointF(200, 300))
        assert tool.last_point == QPointF(200, 300)

    def test_second_commit_finalizes(self, view: CanvasView) -> None:
        tool = CircleTool(view)
        tool.commit_typed_coordinate(QPointF(200, 300))
        tool.commit_typed_coordinate(QPointF(300, 300))
        # After finalize state is reset
        assert tool.last_point is None


class TestRectangleTypedInput:
    def test_two_corners(self, view: CanvasView) -> None:
        tool = RectangleTool(view)
        tool.commit_typed_coordinate(QPointF(0, 0))
        assert tool.last_point == QPointF(0, 0)
        tool.commit_typed_coordinate(QPointF(100, 50))
        assert tool.last_point is None


class TestEllipseTypedInput:
    def test_two_corners(self, view: CanvasView) -> None:
        tool = EllipseTool(view)
        tool.commit_typed_coordinate(QPointF(10, 10))
        assert tool.last_point == QPointF(10, 10)
        tool.commit_typed_coordinate(QPointF(60, 30))
        assert tool.last_point is None


class TestConstructionTypedInput:
    def test_line(self, view: CanvasView) -> None:
        tool = ConstructionLineTool(view)
        tool.commit_typed_coordinate(QPointF(0, 0))
        assert tool.last_point == QPointF(0, 0)
        tool.commit_typed_coordinate(QPointF(100, 0))
        assert tool.last_point is None

    def test_circle(self, view: CanvasView) -> None:
        tool = ConstructionCircleTool(view)
        tool.commit_typed_coordinate(QPointF(50, 50))
        assert tool.last_point == QPointF(50, 50)
        tool.commit_typed_coordinate(QPointF(100, 50))
        assert tool.last_point is None
