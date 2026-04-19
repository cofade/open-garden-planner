"""Integration tests for OffsetTool (US-11.15).

Tests exercise the full select → hover → click → dialog workflow.
All coordinates are scene-space (Y-down, (0,0) = top-left).
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click(
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = modifiers
    return event


def _items_of(view: CanvasView, cls: type) -> list:
    return [i for i in view.scene().items() if isinstance(i, cls)]


def _add_rect(view: CanvasView, x: float, y: float, w: float, h: float) -> RectangleItem:
    item = RectangleItem(x=x, y=y, width=w, height=h)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_circle(view: CanvasView, cx: float, cy: float, r: float) -> CircleItem:
    item = CircleItem(cx, cy, r, object_type=ObjectType.LAWN)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_ellipse(view: CanvasView, x: float, y: float, w: float, h: float) -> EllipseItem:
    item = EllipseItem(x=x, y=y, width=w, height=h)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _add_polygon(view: CanvasView, vertices: list[QPointF]) -> PolygonItem:
    item = PolygonItem(vertices=vertices, object_type=ObjectType.LAWN)
    view.scene().addItem(item)
    item.setSelected(True)
    return item


def _offset_click(
    view: CanvasView,
    click_pos: QPointF,
    distance: float,
) -> None:
    """Activate offset tool, click at pos with mocked dialog returning distance."""
    tool = view.tool_manager.active_tool
    event = _left_click()

    with patch(
        "open_garden_planner.core.tools.offset_tool.QInputDialog.getDouble",
        return_value=(distance, True),
    ):
        tool.mouse_move(event, click_pos)
        tool.mouse_press(event, click_pos)


# ---------------------------------------------------------------------------
# Rectangle offset
# ---------------------------------------------------------------------------


class TestOffsetRectangle:
    def test_outward_offset_creates_larger_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking outside a rectangle creates a larger RectangleItem."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, RectangleItem))
        # Click outside the rect (to the right)
        _offset_click(canvas, QPointF(820, 400), distance=20.0)

        rects = _items_of(canvas, RectangleItem)
        assert len(rects) == before + 1

    def test_outward_offset_size(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset by 20 adds 40 to each dimension."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click outside (right side)
        _offset_click(canvas, QPointF(820, 400), distance=20.0)

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        nr = new_rects[0]
        assert abs(nr.rect().width() - 640) < 1.0
        assert abs(nr.rect().height() - 440) < 1.0

    def test_inward_offset_creates_smaller_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a rectangle creates a smaller RectangleItem."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click inside the rect (center)
        _offset_click(canvas, QPointF(500, 400), distance=20.0)

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        nr = new_rects[0]
        assert nr.rect().width() < original.rect().width()
        assert nr.rect().height() < original.rect().height()

    def test_inward_too_large_creates_no_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Inward offset larger than half the smallest dimension produces no item."""
        original = _add_rect(canvas, 200, 200, 100, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, RectangleItem))
        _offset_click(canvas, QPointF(250, 250), distance=200.0)
        assert len(_items_of(canvas, RectangleItem)) == before

    def test_undo_removes_offset_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after offset removes the created item."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400), distance=20.0)
        assert len(_items_of(canvas, RectangleItem)) == 2

        canvas.command_manager.undo()
        assert len(_items_of(canvas, RectangleItem)) == 1


# ---------------------------------------------------------------------------
# Circle offset
# ---------------------------------------------------------------------------


class TestOffsetCircle:
    def test_outward_offset_increases_radius(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking outside a circle creates a larger CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        before_count = len(_items_of(canvas, CircleItem))
        # Click outside (to the right of the circle boundary)
        _offset_click(canvas, QPointF(620, 500), distance=30.0)

        circles = _items_of(canvas, CircleItem)
        assert len(circles) == before_count + 1

        new_circles = [c for c in circles if c is not original]
        assert len(new_circles) == 1
        assert abs(new_circles[0].radius - 130) < 1.0

    def test_inward_offset_decreases_radius(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a circle creates a smaller CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(500, 500), distance=30.0)

        new_circles = [c for c in _items_of(canvas, CircleItem) if c is not original]
        assert len(new_circles) == 1
        assert abs(new_circles[0].radius - 70) < 1.0

    def test_inward_offset_larger_than_radius_creates_no_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Inward offset exceeding the radius produces no item."""
        _add_circle(canvas, 500, 500, 50)
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, CircleItem))
        _offset_click(canvas, QPointF(500, 500), distance=200.0)
        assert len(_items_of(canvas, CircleItem)) == before


# ---------------------------------------------------------------------------
# Ellipse offset
# ---------------------------------------------------------------------------


class TestOffsetEllipse:
    def test_outward_offset_creates_larger_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset of an ellipse creates a larger EllipseItem."""
        original = _add_ellipse(canvas, 300, 300, 400, 200)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(720, 400), distance=25.0)

        new_items = [e for e in _items_of(canvas, EllipseItem) if e is not original]
        assert len(new_items) == 1
        assert new_items[0].rect().width() > original.rect().width()


# ---------------------------------------------------------------------------
# Polygon offset
# ---------------------------------------------------------------------------


class TestOffsetPolygon:
    def test_outward_polygon_offset_creates_polygon(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset of a polygon creates a new PolygonItem."""
        _add_polygon(
            canvas,
            [
                QPointF(200, 200),
                QPointF(800, 200),
                QPointF(800, 600),
                QPointF(200, 600),
            ],
        )
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, PolygonItem))
        # Click outside the polygon
        _offset_click(canvas, QPointF(820, 400), distance=20.0)
        assert len(_items_of(canvas, PolygonItem)) == before + 1

    def test_polygon_offset_undo(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo removes the polygon offset result."""
        _add_polygon(
            canvas,
            [
                QPointF(200, 200),
                QPointF(800, 200),
                QPointF(800, 600),
                QPointF(200, 600),
            ],
        )
        canvas.set_active_tool(ToolType.OFFSET)

        before = len(_items_of(canvas, PolygonItem))
        _offset_click(canvas, QPointF(820, 400), distance=20.0)
        assert len(_items_of(canvas, PolygonItem)) == before + 1

        canvas.command_manager.undo()
        assert len(_items_of(canvas, PolygonItem)) == before


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_no_selection_does_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking with no selection is a no-op."""
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()

        # No items in scene, no crash
        result = tool.mouse_press(event, QPointF(500, 500))
        assert result is False

    def test_dialog_cancel_creates_no_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Cancelling the distance dialog creates no item."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()

        with patch(
            "open_garden_planner.core.tools.offset_tool.QInputDialog.getDouble",
            return_value=(0.0, False),
        ):
            tool.mouse_move(event, QPointF(820, 400))
            tool.mouse_press(event, QPointF(820, 400))

        assert len(_items_of(canvas, RectangleItem)) == 1

    def test_hover_empty_scene_no_crash(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()
        tool.mouse_move(event, QPointF(500, 500))
