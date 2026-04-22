"""Integration tests for OffsetTool (US-11.15).

Tests exercise the full select → hover → click workflow.
Distance is now determined by cursor position, not a dialog.
All coordinates are scene-space (Y-down, (0,0) = top-left).
"""

# ruff: noqa: ARG002

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from unittest.mock import MagicMock

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


def _offset_click(view: CanvasView, click_pos: QPointF) -> None:
    """Activate offset tool, hover then click at pos — distance from cursor."""
    tool = view.tool_manager.active_tool
    event = _left_click()
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
        # Click ~20 units outside the right edge (boundary at x=800)
        _offset_click(canvas, QPointF(820, 400))

        rects = _items_of(canvas, RectangleItem)
        assert len(rects) == before + 1

    def test_outward_offset_size(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset by ~20 adds ~40 to each dimension."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click 20 units outside the right edge; boundary sampling tolerance ±3
        _offset_click(canvas, QPointF(820, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        nr = new_rects[0]
        assert abs(nr.rect().width() - 640) < 3.0
        assert abs(nr.rect().height() - 440) < 3.0

    def test_outward_offset_larger_than_original(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset always creates a shape wider and taller than original."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(830, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        assert new_rects[0].rect().width() > original.rect().width()
        assert new_rects[0].rect().height() > original.rect().height()

    def test_inward_offset_creates_smaller_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a rectangle creates a smaller RectangleItem."""
        original = _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click well inside the rect, far from boundary → inward offset
        _offset_click(canvas, QPointF(500, 400))

        new_rects = [r for r in _items_of(canvas, RectangleItem) if r is not original]
        assert len(new_rects) == 1
        assert new_rects[0].rect().width() < original.rect().width()
        assert new_rects[0].rect().height() < original.rect().height()

    def test_undo_removes_offset_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after offset removes the created item."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))
        assert len(_items_of(canvas, RectangleItem)) == 2

        canvas.command_manager.undo()
        assert len(_items_of(canvas, RectangleItem)) == 1

    def test_tool_switches_to_select_after_offset(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """After creating an offset, the active tool switches back to SELECT."""
        _add_rect(canvas, 200, 200, 600, 400)
        canvas.set_active_tool(ToolType.OFFSET)

        _offset_click(canvas, QPointF(820, 400))

        assert canvas.tool_manager.active_tool.tool_type == ToolType.SELECT


# ---------------------------------------------------------------------------
# Circle offset
# ---------------------------------------------------------------------------


class TestOffsetCircle:
    def test_outward_offset_creates_larger_circle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking outside a circle creates a larger CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        before_count = len(_items_of(canvas, CircleItem))
        # Click 30 units outside the right boundary (boundary at x=600)
        _offset_click(canvas, QPointF(630, 500))

        circles = _items_of(canvas, CircleItem)
        assert len(circles) == before_count + 1

        new_circles = [c for c in circles if c is not original]
        assert len(new_circles) == 1
        assert new_circles[0].radius > original.radius

    def test_inward_offset_creates_smaller_circle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking inside a circle creates a smaller CircleItem."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click well inside (30 units from right boundary)
        _offset_click(canvas, QPointF(570, 500))

        new_circles = [c for c in _items_of(canvas, CircleItem) if c is not original]
        assert len(new_circles) == 1
        assert new_circles[0].radius < original.radius

    def test_outward_offset_approximate_radius(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Outward offset by ~30 units increases radius by ~30."""
        original = _add_circle(canvas, 500, 500, 100)
        canvas.set_active_tool(ToolType.OFFSET)

        # 30 units outside right boundary
        _offset_click(canvas, QPointF(630, 500))

        new_circles = [c for c in _items_of(canvas, CircleItem) if c is not original]
        assert len(new_circles) == 1
        assert abs(new_circles[0].radius - 130) < 3.0


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

        # Click outside the right boundary (boundary at x=700)
        _offset_click(canvas, QPointF(725, 400))

        new_items = [e for e in _items_of(canvas, EllipseItem) if e is not original]
        assert len(new_items) == 1
        assert new_items[0].rect().width() > original.rect().width()

    def test_inward_offset_creates_smaller_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Inward offset of an ellipse creates a smaller EllipseItem."""
        original = _add_ellipse(canvas, 300, 300, 400, 200)
        canvas.set_active_tool(ToolType.OFFSET)

        # Click inside near the right boundary
        _offset_click(canvas, QPointF(675, 400))

        new_items = [e for e in _items_of(canvas, EllipseItem) if e is not original]
        assert len(new_items) == 1
        assert new_items[0].rect().width() < original.rect().width()


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
        _offset_click(canvas, QPointF(820, 400))
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
        _offset_click(canvas, QPointF(820, 400))
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

        result = tool.mouse_press(event, QPointF(500, 500))
        assert result is False

    def test_hover_empty_scene_no_crash(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.OFFSET)
        tool = canvas.tool_manager.active_tool
        event = _left_click()
        tool.mouse_move(event, QPointF(500, 500))
