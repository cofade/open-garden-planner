"""Tests for the Package A BaseTool typed-input extensions."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.tools.base_tool import ToolType
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

    def test_typed_first_corner_then_click_does_not_leak_preview(
        self, view: CanvasView, qtbot
    ) -> None:
        """Mixing typed + clicked input must not orphan preview rectangles."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtWidgets import QGraphicsRectItem

        view.set_active_tool(ToolType.RECTANGLE)
        tool = view._tool_manager.active_tool
        assert isinstance(tool, RectangleTool)
        # Typed first corner opens a preview rectangle.
        tool.commit_typed_coordinate(QPointF(0, 0))
        # Simulated click at the would-be second corner.
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        tool.mouse_press(event, QPointF(100, 50))
        # Only the finalized item should remain - no leftover preview.
        preview_items = [
            i
            for i in view.scene().items()
            if isinstance(i, QGraphicsRectItem) and i.pen().style() == Qt.PenStyle.DashLine
        ]
        assert preview_items == []
        # Finalize state cleared.
        assert tool.last_point is None

    def test_typed_first_corner_then_shift_click_constrains_to_square(
        self, view: CanvasView, qtbot  # noqa: ARG002
    ) -> None:
        """Shift modifier on the closing click must produce a square."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QMouseEvent
        from open_garden_planner.ui.canvas.items import RectangleItem

        view.set_active_tool(ToolType.RECTANGLE)
        tool = view._tool_manager.active_tool
        assert isinstance(tool, RectangleTool)
        tool.commit_typed_coordinate(QPointF(0, 0))
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
        )
        tool.mouse_press(event, QPointF(300, 80))
        # Shift forces width == height; the longer axis wins.
        rects = [i for i in view.scene().items() if isinstance(i, RectangleItem)]
        assert len(rects) == 1
        r = rects[0].rect()
        assert abs(r.width() - r.height()) < 1e-6


class TestEllipseTypedInput:
    def test_two_corners(self, view: CanvasView) -> None:
        tool = EllipseTool(view)
        tool.commit_typed_coordinate(QPointF(10, 10))
        assert tool.last_point == QPointF(10, 10)
        tool.commit_typed_coordinate(QPointF(60, 30))
        assert tool.last_point is None

    def test_typed_first_corner_then_shift_click_constrains_to_circle(
        self, view: CanvasView, qtbot  # noqa: ARG002
    ) -> None:
        """Shift modifier on the closing click must produce a circle (1:1)."""
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QMouseEvent
        from open_garden_planner.ui.canvas.items import EllipseItem

        view.set_active_tool(ToolType.ELLIPSE)
        tool = view._tool_manager.active_tool
        assert isinstance(tool, EllipseTool)
        tool.commit_typed_coordinate(QPointF(0, 0))
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(0, 0),
            QPointF(0, 0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.ShiftModifier,
        )
        tool.mouse_press(event, QPointF(300, 100))
        ells = [i for i in view.scene().items() if isinstance(i, EllipseItem)]
        assert len(ells) == 1
        r = ells[0].rect()
        assert abs(r.width() - r.height()) < 1e-6


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
