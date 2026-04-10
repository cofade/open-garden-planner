"""Integration tests: drawing tool workflows.

Each test exercises the full press → [move] → release sequence and
asserts the resulting scene state.

Tool-specific interaction models (see arc42 §8.10):
  RectangleTool : press(start) → move(end) → release(end)
  CircleTool    : press(center) → press(rim)   [two separate clicks]
  PolygonTool   : press(v1) → press(v2) → press(v3) → mouse_double_click
  TextTool      : press(pos)                   [single click, item appears immediately]
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem
from open_garden_planner.ui.canvas.items.text_item import TextItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _items_of(view: CanvasView, cls: type) -> list:
    return [i for i in view.scene().items() if isinstance(i, cls)]


# ---------------------------------------------------------------------------
# Rectangle
# ---------------------------------------------------------------------------


class TestRectangleTool:
    """Full draw workflow for the rectangle tool."""

    def test_draw_rectangle_creates_item(self, canvas: CanvasView, qtbot: object) -> None:
        """Drawing a rectangle produces exactly one RectangleItem."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(300, 250))
        tool.mouse_release(event, QPointF(300, 250))

        rects = _items_of(canvas, RectangleItem)
        assert len(rects) == 1

    def test_rectangle_has_correct_dimensions(self, canvas: CanvasView, qtbot: object) -> None:
        """The created rectangle matches the drag distance."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(400, 300))
        tool.mouse_release(event, QPointF(400, 300))

        item = _items_of(canvas, RectangleItem)[0]
        assert item.rect().width() == pytest.approx(300.0, abs=0.01)
        assert item.rect().height() == pytest.approx(200.0, abs=0.01)

    def test_draw_rectangle_minimum_size_not_created(self, canvas: CanvasView, qtbot: object) -> None:
        """A drag smaller than the minimum size (1 cm) produces no item."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        # Sub-pixel drag — width and height both < 1
        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(100.5, 100.5))
        tool.mouse_release(event, QPointF(100.5, 100.5))

        assert len(_items_of(canvas, RectangleItem)) == 0

    def test_draw_reversed_drag_produces_positive_rect(self, canvas: CanvasView, qtbot: object) -> None:
        """Dragging right-to-left or bottom-to-top still creates a valid rect."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(400, 300))
        tool.mouse_move(event, QPointF(100, 100))
        tool.mouse_release(event, QPointF(100, 100))

        rects = _items_of(canvas, RectangleItem)
        assert len(rects) == 1
        r = rects[0].rect()
        assert r.width() > 0
        assert r.height() > 0

    def test_cancel_with_escape_during_draw(self, canvas: CanvasView, qtbot: object) -> None:
        """Pressing Escape mid-draw cancels and creates no item."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.cancel()

        assert len(_items_of(canvas, RectangleItem)) == 0
        assert not tool._is_drawing

    def test_two_separate_rectangles(self, canvas: CanvasView, qtbot: object) -> None:
        """Drawing twice produces two independent items."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.RECTANGLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(300, 200))
        tool.mouse_release(event, QPointF(300, 200))

        tool.mouse_press(event, QPointF(400, 100))
        tool.mouse_move(event, QPointF(600, 200))
        tool.mouse_release(event, QPointF(600, 200))

        assert len(_items_of(canvas, RectangleItem)) == 2


# ---------------------------------------------------------------------------
# Circle
# ---------------------------------------------------------------------------


class TestCircleTool:
    """Full draw workflow for the circle tool (two-click: center then rim)."""

    def test_draw_circle_creates_item(self, canvas: CanvasView, qtbot: object) -> None:
        """Two clicks produce exactly one CircleItem."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.CIRCLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(250, 200))   # center
        tool.mouse_press(event, QPointF(350, 200))   # rim (radius = 100)

        circles = _items_of(canvas, CircleItem)
        assert len(circles) == 1

    def test_circle_has_correct_radius(self, canvas: CanvasView, qtbot: object) -> None:
        """The radius equals the distance from center to rim click."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.CIRCLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(200, 200))   # center
        tool.mouse_press(event, QPointF(350, 200))   # rim → radius = 150

        item = _items_of(canvas, CircleItem)[0]
        # CircleItem exposes .radius (not boundingRect, which includes pen width)
        assert item.radius == pytest.approx(150.0, abs=0.01)

    def test_cancel_circle_after_center_click(self, canvas: CanvasView, qtbot: object) -> None:
        """Cancelling after the first click (center set) produces no item."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.CIRCLE)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(250, 200))   # center only
        tool.cancel()

        assert len(_items_of(canvas, CircleItem)) == 0


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------


class TestPolygonTool:
    """Full draw workflow for the polygon tool (multi-click + double-click to close)."""

    def test_draw_triangle_via_double_click(self, canvas: CanvasView, qtbot: object) -> None:
        """Three clicks + double-click close produces one PolygonItem."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.POLYGON)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(200, 100))
        tool.mouse_press(event, QPointF(350, 300))
        tool.mouse_press(event, QPointF(50, 300))
        tool.mouse_double_click(event, QPointF(50, 300))

        polys = _items_of(canvas, PolygonItem)
        assert len(polys) == 1

    def test_polygon_has_correct_vertex_count(self, canvas: CanvasView, qtbot: object) -> None:
        """The created polygon has the same number of vertices as clicks."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.POLYGON)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_press(event, QPointF(300, 100))
        tool.mouse_press(event, QPointF(300, 300))
        tool.mouse_press(event, QPointF(100, 300))
        tool.mouse_double_click(event, QPointF(100, 300))

        poly = _items_of(canvas, PolygonItem)[0]
        # A closed quad has 4 vertices
        assert len(poly.polygon()) == 4

    def test_cancel_polygon_before_close(self, canvas: CanvasView, qtbot: object) -> None:
        """Cancelling mid-draw produces no PolygonItem."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.POLYGON)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_press(event, QPointF(300, 100))
        tool.cancel()

        assert len(_items_of(canvas, PolygonItem)) == 0


# ---------------------------------------------------------------------------
# Text
# ---------------------------------------------------------------------------


class TestTextTool:
    """Full draw workflow for the text annotation tool (single click)."""

    def test_click_creates_text_item(self, canvas: CanvasView, qtbot: object) -> None:
        """A single click places a TextItem in the scene."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.TEXT)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(200, 150))

        texts = _items_of(canvas, TextItem)
        assert len(texts) == 1

    def test_text_item_position(self, canvas: CanvasView, qtbot: object) -> None:
        """The TextItem is placed at the click position (scene coords)."""
        event = _left_click_event()
        canvas.set_active_tool(ToolType.TEXT)
        tool = canvas.tool_manager.active_tool

        tool.mouse_press(event, QPointF(200, 150))

        item = _items_of(canvas, TextItem)[0]
        assert item.x() == pytest.approx(200.0, abs=1.0)
        assert item.y() == pytest.approx(150.0, abs=1.0)
