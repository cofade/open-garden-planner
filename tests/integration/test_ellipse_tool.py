"""Integration tests for EllipseTool (US-11.14).

Tests exercise the full mouse gesture → scene state assertion workflow.
All coordinates are scene-space (Y-down, (0,0) = top-left).
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mouse_event(
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = modifiers
    return event


def _key_event(key: Qt.Key) -> MagicMock:
    event = MagicMock(spec=QKeyEvent)
    event.key.return_value = key
    return event


def _ellipses(view: CanvasView) -> list[EllipseItem]:
    return [i for i in view.scene().items() if isinstance(i, EllipseItem)]


def _draw_ellipse(
    view: CanvasView,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    modifiers: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier,
) -> None:
    """Simulate a full press → move → release gesture."""
    tool = view.tool_manager.active_tool
    event = _mouse_event(modifiers)
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))


# ---------------------------------------------------------------------------
# Basic drawing
# ---------------------------------------------------------------------------


class TestBasicDraw:
    def test_drag_creates_ellipse_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A click-drag produces exactly one EllipseItem in the scene."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        assert len(_ellipses(canvas)) == 0
        _draw_ellipse(canvas, 100, 100, 300, 400)
        assert len(_ellipses(canvas)) == 1

    def test_drag_geometry_matches_bounding_rect(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Width and height match the drag extent."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 100, 100, 300, 400)
        item = _ellipses(canvas)[0]
        assert abs(item.rect().width() - 200) < 1.0
        assert abs(item.rect().height() - 300) < 1.0

    def test_tiny_drag_creates_no_item(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """A drag of less than 1px creates no item (noise guard)."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 100, 100, 100.5, 100.5)
        assert len(_ellipses(canvas)) == 0

    def test_drag_top_left_direction(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Dragging toward top-left still produces a valid rect (positive size)."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 300, 400, 100, 100)
        items = _ellipses(canvas)
        assert len(items) == 1
        assert items[0].rect().width() > 0
        assert items[0].rect().height() > 0


# ---------------------------------------------------------------------------
# Modifier keys
# ---------------------------------------------------------------------------


class TestModifiers:
    def test_shift_constrains_to_circle(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Shift while dragging produces equal width and height."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(
            canvas, 100, 100, 300, 400,
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )
        item = _ellipses(canvas)[0]
        assert abs(item.rect().width() - item.rect().height()) < 1.0

    def test_shift_uses_larger_axis(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Shift constrain picks the larger of width/height (300 here)."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(
            canvas, 100, 100, 300, 400,
            modifiers=Qt.KeyboardModifier.ShiftModifier,
        )
        item = _ellipses(canvas)[0]
        assert abs(item.rect().width() - 300) < 1.0

    def test_alt_draws_from_center(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Alt-drag uses start point as center; result centered on start."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        start = QPointF(300, 300)
        end = QPointF(500, 400)
        _draw_ellipse(
            canvas, start.x(), start.y(), end.x(), end.y(),
            modifiers=Qt.KeyboardModifier.AltModifier,
        )
        item = _ellipses(canvas)[0]
        scene_center = item.mapToScene(item.rect().center())
        assert abs(scene_center.x() - start.x()) < 1.0
        assert abs(scene_center.y() - start.y()) < 1.0

    def test_alt_shift_draws_circle_from_center(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Alt+Shift produces a circle centered at start point."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        start = QPointF(300, 300)
        end = QPointF(500, 400)
        _draw_ellipse(
            canvas, start.x(), start.y(), end.x(), end.y(),
            modifiers=Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.ShiftModifier,
        )
        item = _ellipses(canvas)[0]
        assert abs(item.rect().width() - item.rect().height()) < 1.0
        scene_center = item.mapToScene(item.rect().center())
        assert abs(scene_center.x() - start.x()) < 1.0
        assert abs(scene_center.y() - start.y()) < 1.0


# ---------------------------------------------------------------------------
# Cancel / Escape
# ---------------------------------------------------------------------------


class TestCancel:
    def test_escape_during_draw_cancels(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Pressing Escape during a drag cancels and leaves scene empty."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        tool = canvas.tool_manager.active_tool
        event = _mouse_event()

        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_move(event, QPointF(300, 400))

        consumed = tool.key_press(_key_event(Qt.Key.Key_Escape))
        assert consumed is True
        assert len(_ellipses(canvas)) == 0

    def test_escape_after_draw_not_consumed(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Escape when not drawing is not consumed by the tool."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        tool = canvas.tool_manager.active_tool
        consumed = tool.key_press(_key_event(Qt.Key.Key_Escape))
        assert consumed is False


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------


class TestUndo:
    def test_undo_removes_created_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Undo after drawing an ellipse removes it from the scene."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 100, 100, 400, 300)
        assert len(_ellipses(canvas)) == 1

        canvas.command_manager.undo()
        assert len(_ellipses(canvas)) == 0

    def test_redo_restores_ellipse(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Redo after undo restores the EllipseItem."""
        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 100, 100, 400, 300)

        canvas.command_manager.undo()
        assert len(_ellipses(canvas)) == 0

        canvas.command_manager.redo()
        assert len(_ellipses(canvas)) == 1


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_save_load_preserves_geometry(
        self, canvas: CanvasView, qtbot: object, tmp_path: object
    ) -> None:
        """Save + load round-trip preserves center and semi-axes."""
        from open_garden_planner.core.project import ProjectManager

        canvas.set_active_tool(ToolType.ELLIPSE)
        _draw_ellipse(canvas, 100, 200, 300, 500)

        original = _ellipses(canvas)[0]
        orig_rect = original.rect()
        orig_cx = orig_rect.center().x() + original.pos().x()
        orig_cy = orig_rect.center().y() + original.pos().y()
        orig_semi_x = orig_rect.width() / 2
        orig_semi_y = orig_rect.height() / 2

        pm = ProjectManager()
        file_path = tmp_path / "test_ellipse.ogp"  # type: ignore[operator]
        pm.save(canvas.scene(), file_path)

        canvas.scene().clear()
        assert len(_ellipses(canvas)) == 0

        pm.load(canvas.scene(), file_path)

        loaded = _ellipses(canvas)
        assert len(loaded) == 1

        item = loaded[0]
        cx = item.rect().center().x() + item.pos().x()
        cy = item.rect().center().y() + item.pos().y()
        semi_x = item.rect().width() / 2
        semi_y = item.rect().height() / 2

        assert abs(cx - orig_cx) < 1.0
        assert abs(cy - orig_cy) < 1.0
        assert abs(semi_x - orig_semi_x) < 1.0
        assert abs(semi_y - orig_semi_y) < 1.0
