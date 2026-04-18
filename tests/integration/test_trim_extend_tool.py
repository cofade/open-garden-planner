"""Integration tests for TrimExtendTool (US-11.16).

Tests exercise the full mouse gesture → scene state assertion workflow.
All coordinates are scene-space (Y-down, (0,0) = top-left).
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.core.tools.trim_tool import TrimExtendMode
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _key_event(key: Qt.Key) -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = key
    return event


def _items_of(view: CanvasView, cls: type) -> list:
    return [i for i in view.scene().items() if isinstance(i, cls)]


def _add_polyline(view: CanvasView, points: list[QPointF]) -> PolylineItem:
    item = PolylineItem(points=points, object_type=ObjectType.FENCE)
    view.scene().addItem(item)
    return item


def _add_polygon(view: CanvasView, vertices: list[QPointF]) -> PolygonItem:
    item = PolygonItem(vertices=vertices, object_type=ObjectType.LAWN)
    view.scene().addItem(item)
    return item


def _add_rectangle(view: CanvasView, x: float, y: float, w: float, h: float) -> RectangleItem:
    item = RectangleItem(x=x, y=y, width=w, height=h)
    view.scene().addItem(item)
    return item


# ---------------------------------------------------------------------------
# Trim – polyline targets
# ---------------------------------------------------------------------------


class TestTrimPolyline:
    def test_trim_middle_creates_two_pieces(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Trimming the middle section (between two intersections) of a horizontal
        polyline produces two new polyline pieces and removes the original."""
        h_line = _add_polyline(
            canvas, [QPointF(0, 500), QPointF(1000, 500)]
        )
        # Vertical cutting line
        _add_polyline(canvas, [QPointF(400, 0), QPointF(400, 1000)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click in the middle section (between x=400 and x=700)
        tool.mouse_move(event, QPointF(550, 500))
        tool.mouse_press(event, QPointF(550, 500))

        polylines = _items_of(canvas, PolylineItem)
        assert h_line not in polylines, "Original should be removed"
        # Two cutting lines + two pieces = 4 total
        assert len(polylines) == 4

    def test_trim_head_produces_one_piece(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking before the first intersection removes the leading stub."""
        h_line = _add_polyline(canvas, [QPointF(0, 500), QPointF(1000, 500)])
        _add_polyline(canvas, [QPointF(600, 0), QPointF(600, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click left of the single intersection at x=600
        tool.mouse_move(event, QPointF(300, 500))
        tool.mouse_press(event, QPointF(300, 500))

        polylines = _items_of(canvas, PolylineItem)
        assert h_line not in polylines
        # Cutting line + one remaining piece
        assert len(polylines) == 2

    def test_trim_isolated_removes_entire_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A polyline with no intersections is entirely removed when clicked."""
        line = _add_polyline(canvas, [QPointF(100, 100), QPointF(500, 100)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_move(event, QPointF(300, 100))
        tool.mouse_press(event, QPointF(300, 100))

        polylines = _items_of(canvas, PolylineItem)
        assert line not in polylines
        assert len(polylines) == 0

    def test_trim_undo_restores_original(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after a trim restores the original PolylineItem."""
        h_line = _add_polyline(canvas, [QPointF(0, 500), QPointF(1000, 500)])
        _add_polyline(canvas, [QPointF(500, 0), QPointF(500, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_move(event, QPointF(250, 500))
        tool.mouse_press(event, QPointF(250, 500))

        canvas.command_manager.undo()

        assert h_line in _items_of(canvas, PolylineItem)

    def test_trim_multipoint_polyline_preserves_interior_vertices(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """After trimming one segment, interior vertices of other segments survive."""
        # Polyline with 4 vertices: (0,500)-(300,500)-(600,500)-(900,500)
        h_line = _add_polyline(
            canvas,
            [QPointF(0, 500), QPointF(300, 500), QPointF(600, 500), QPointF(900, 500)],
        )
        # Cutting line intersects first segment at x=150
        _add_polyline(canvas, [QPointF(150, 0), QPointF(150, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click left of x=150 (head)
        tool.mouse_move(event, QPointF(75, 500))
        tool.mouse_press(event, QPointF(75, 500))

        polylines = _items_of(canvas, PolylineItem)
        assert h_line not in polylines
        # The remaining piece should keep vertices at x=150, 300, 600, 900
        remaining = [p for p in polylines if p is not _items_of(canvas, PolylineItem)[0]]
        # At least one piece with >= 3 vertices
        long_pieces = [p for p in polylines if p.object_type == ObjectType.FENCE and len(p.points) >= 3]
        assert len(long_pieces) >= 1


# ---------------------------------------------------------------------------
# Mode toggle
# ---------------------------------------------------------------------------


class TestModeToggle:
    def test_default_mode_is_trim(self, canvas: CanvasView, qtbot: object) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        assert tool._mode == TrimExtendMode.TRIM

    def test_x_key_toggles_to_extend(self, canvas: CanvasView, qtbot: object) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        result = tool.key_press(_key_event(Qt.Key.Key_X))
        assert result is True
        assert tool._mode == TrimExtendMode.EXTEND

    def test_x_key_toggles_back_to_trim(self, canvas: CanvasView, qtbot: object) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool.key_press(_key_event(Qt.Key.Key_X))
        tool.key_press(_key_event(Qt.Key.Key_X))
        assert tool._mode == TrimExtendMode.TRIM

    def test_other_keys_not_consumed(self, canvas: CanvasView, qtbot: object) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        result = tool.key_press(_key_event(Qt.Key.Key_Escape))
        assert result is False


# ---------------------------------------------------------------------------
# Extend – polyline endpoints
# ---------------------------------------------------------------------------


class TestExtendPolyline:
    def test_extend_reaches_cutting_edge(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Extending the right endpoint of a short line to a distant vertical line."""
        # Short line ending at x=300
        short = _add_polyline(canvas, [QPointF(0, 500), QPointF(300, 500)])
        # Vertical barrier at x=700
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool._mode = TrimExtendMode.EXTEND
        event = _left_click_event()

        # Click near the right endpoint of short line
        tool.mouse_move(event, QPointF(302, 500))
        tool.mouse_press(event, QPointF(302, 500))

        # The short line should now end (approx) at x=700
        last_scene = short.mapToScene(short.points[-1])
        assert abs(last_scene.x() - 700.0) < 2.0

    def test_extend_undo_restores_original(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after extend puts the original endpoint back."""
        short = _add_polyline(canvas, [QPointF(0, 500), QPointF(300, 500)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 1000)])

        original_last = short.mapToScene(short.points[-1])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool._mode = TrimExtendMode.EXTEND
        event = _left_click_event()

        tool.mouse_move(event, QPointF(302, 500))
        tool.mouse_press(event, QPointF(302, 500))

        canvas.command_manager.undo()

        restored_last = short.mapToScene(short.points[-1])
        assert abs(restored_last.x() - original_last.x()) < 1.0
        assert abs(restored_last.y() - original_last.y()) < 1.0

    def test_extend_no_target_does_nothing(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Clicking in extend mode with no reachable endpoint is a no-op."""
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        tool._mode = TrimExtendMode.EXTEND
        event = _left_click_event()

        # No items in scene — should not raise
        tool.mouse_move(event, QPointF(500, 500))
        result = tool.mouse_press(event, QPointF(500, 500))
        assert result is False


# ---------------------------------------------------------------------------
# Polygon trim
# ---------------------------------------------------------------------------


class TestTrimPolygon:
    def test_polygon_trim_produces_polyline(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Trimming a polygon edge removes the polygon and adds an open PolylineItem."""
        # Square polygon: top-left(100,100), top-right(900,100),
        #                  bottom-right(900,900), bottom-left(100,900)
        sq = _add_polygon(
            canvas,
            [
                QPointF(100, 100),
                QPointF(900, 100),
                QPointF(900, 900),
                QPointF(100, 900),
            ],
        )
        # Horizontal cutting line crosses the top edge at x=300 and x=700
        _add_polyline(canvas, [QPointF(300, 0), QPointF(300, 200)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 200)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click on the top edge between x=300 and x=700 (y=100)
        tool.mouse_move(event, QPointF(500, 100))
        tool.mouse_press(event, QPointF(500, 100))

        assert sq not in _items_of(canvas, PolygonItem), "Polygon should be removed"
        assert len(_items_of(canvas, PolylineItem)) >= 1, "A polyline should be created"

    def test_polygon_trim_undo_restores_polygon(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after polygon trim restores the PolygonItem."""
        sq = _add_polygon(
            canvas,
            [
                QPointF(100, 100),
                QPointF(900, 100),
                QPointF(900, 900),
                QPointF(100, 900),
            ],
        )
        _add_polyline(canvas, [QPointF(300, 0), QPointF(300, 200)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 200)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_move(event, QPointF(500, 100))
        tool.mouse_press(event, QPointF(500, 100))

        canvas.command_manager.undo()

        assert sq in _items_of(canvas, PolygonItem)


# ---------------------------------------------------------------------------
# Rectangle trim
# ---------------------------------------------------------------------------


class TestTrimRectangle:
    def test_rectangle_trim_produces_polyline(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Trimming a rectangle edge removes it and adds an open PolylineItem."""
        rect = _add_rectangle(canvas, 100, 100, 800, 800)
        # Two vertical cutting lines crossing the top edge (y=100) at x=300 and x=700
        _add_polyline(canvas, [QPointF(300, 0), QPointF(300, 200)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 200)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click on the top edge between the two cuts
        tool.mouse_move(event, QPointF(500, 100))
        tool.mouse_press(event, QPointF(500, 100))

        assert rect not in _items_of(canvas, RectangleItem), "Rectangle should be removed"
        assert len(_items_of(canvas, PolylineItem)) >= 1, "A polyline should be created"

    def test_rectangle_trim_undo_restores_rectangle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after rectangle trim restores the RectangleItem."""
        rect = _add_rectangle(canvas, 100, 100, 800, 800)
        _add_polyline(canvas, [QPointF(300, 0), QPointF(300, 200)])
        _add_polyline(canvas, [QPointF(700, 0), QPointF(700, 200)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        tool.mouse_move(event, QPointF(500, 100))
        tool.mouse_press(event, QPointF(500, 100))

        canvas.command_manager.undo()

        assert rect in _items_of(canvas, RectangleItem)

    def test_rectangle_acts_as_cutting_edge_for_polyline(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A rectangle edge can be used as a cutting boundary for trimming a polyline."""
        # Rectangle with top edge at y=100
        _add_rectangle(canvas, 100, 100, 800, 800)
        # Polyline crossing the top edge of the rectangle
        line = _add_polyline(canvas, [QPointF(500, 0), QPointF(500, 1000)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Click inside the rectangle on the polyline — should trim the inner segment
        tool.mouse_move(event, QPointF(500, 500))
        tool.mouse_press(event, QPointF(500, 500))

        assert line not in _items_of(canvas, PolylineItem), "Original should be removed"


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


class TestRobustness:
    def test_hover_empty_scene_no_crash(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()
        tool.mouse_move(event, QPointF(500, 500))
        # No exception expected

    def test_click_empty_scene_no_crash(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()
        tool.mouse_move(event, QPointF(500, 500))
        tool.mouse_press(event, QPointF(500, 500))
        # No exception expected

    def test_highlight_cleaned_up_on_deactivate(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Deactivating the tool removes the preview highlight from the scene."""
        _add_polyline(canvas, [QPointF(0, 500), QPointF(1000, 500)])

        canvas.set_active_tool(ToolType.TRIM_EXTEND)
        tool = canvas.tool_manager.active_tool
        event = _left_click_event()

        # Trigger a highlight
        tool.mouse_move(event, QPointF(500, 500))
        assert tool._highlight is not None

        # Switch away
        canvas.set_active_tool(ToolType.SELECT)
        assert tool._highlight is None
