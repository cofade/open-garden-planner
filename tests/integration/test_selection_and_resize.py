"""Integration tests: selection and resize-handle behaviour.

Regression coverage for fix #121 / #122:
  - Mid-edge handles (MIDDLE_LEFT, MIDDLE_RIGHT) must constrain to X-axis only.
  - Mid-edge handles (TOP_CENTER, BOTTOM_CENTER) must constrain to Y-axis only.
  - Corner handles may change both axes freely.

Workflow per test:
  1. Draw rectangle via RectangleTool (tool → press → move → release).
  2. Select the resulting item and show its resize handles.
  3. Set up handle drag state (initial rect + drag start).
  4. Call _apply_resize with a diagonal delta.
  5. Assert that only the expected axis changed.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.resize_handle import HandlePosition

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> RectangleItem:
    """Draw a rectangle and return the resulting item."""
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))

    items = [i for i in view.scene().items() if isinstance(i, RectangleItem)]
    assert items, "Rectangle should have been created"
    return items[0]


def _get_handle(item: RectangleItem, position: HandlePosition) -> object:
    """Return the ResizeHandle for the given position."""
    item.show_resize_handles()
    for handle in item._resize_handles:
        if handle._position == position:
            return handle
    raise AssertionError(f"Handle {position} not found on item")


def _setup_handle_drag(handle: object, item: RectangleItem) -> None:
    """Prime a handle for drag testing (sets internal drag state)."""

    handle._is_dragging = True
    handle._drag_start_pos = QPointF(0, 0)
    if hasattr(item, "rect") and callable(item.rect):
        handle._initial_rect = item.rect()
    else:
        handle._initial_rect = item.boundingRect()
    handle._initial_parent_pos = item.pos()


# ---------------------------------------------------------------------------
# Selection basics
# ---------------------------------------------------------------------------


class TestSelection:
    """Basic item selection behaviour."""

    def test_item_selected_programmatically(self, canvas: CanvasView, qtbot: object) -> None:
        """An item can be selected and reports isSelected() == True."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        item.setSelected(True)
        assert item.isSelected()

    def test_deselect(self, canvas: CanvasView, qtbot: object) -> None:
        """Clearing the scene selection deselects all items."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        item.setSelected(True)
        canvas.scene().clearSelection()
        assert not item.isSelected()

    def test_multiple_items_one_selected(self, canvas: CanvasView, qtbot: object) -> None:
        """Selecting one item does not auto-select others."""
        item_a = _draw_rect(canvas, 100, 100, 300, 200)
        item_b = _draw_rect(canvas, 500, 100, 700, 200)
        item_a.setSelected(True)
        assert item_a.isSelected()
        assert not item_b.isSelected()


# ---------------------------------------------------------------------------
# Resize handle axis constraints (Regression #121 / #122)
# ---------------------------------------------------------------------------


class TestResizeHandleConstraints:
    """Regression tests for mid-edge resize axis constraints.

    Fix #121/#122: MIDDLE_LEFT/RIGHT handles must not change item height;
    TOP_CENTER/BOTTOM_CENTER handles must not change item width.
    """

    def test_middle_left_only_changes_x(self, canvas: CanvasView, qtbot: object) -> None:
        """MIDDLE_LEFT handle: diagonal drag changes width but not height."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        initial_height = item.rect().height()

        handle = _get_handle(item, HandlePosition.MIDDLE_LEFT)
        _setup_handle_drag(handle, item)

        # Diagonal delta — both x and y are non-zero
        handle._apply_resize(QPointF(50.0, 50.0))

        assert item.rect().height() == pytest.approx(initial_height, abs=0.01), (
            "MIDDLE_LEFT should not affect height"
        )

    def test_middle_right_only_changes_x(self, canvas: CanvasView, qtbot: object) -> None:
        """MIDDLE_RIGHT handle: diagonal drag changes width but not height."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        initial_height = item.rect().height()

        handle = _get_handle(item, HandlePosition.MIDDLE_RIGHT)
        _setup_handle_drag(handle, item)

        handle._apply_resize(QPointF(50.0, 50.0))

        assert item.rect().height() == pytest.approx(initial_height, abs=0.01), (
            "MIDDLE_RIGHT should not affect height"
        )

    def test_top_center_only_changes_y(self, canvas: CanvasView, qtbot: object) -> None:
        """TOP_CENTER handle: diagonal drag changes height but not width."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        initial_width = item.rect().width()

        handle = _get_handle(item, HandlePosition.TOP_CENTER)
        _setup_handle_drag(handle, item)

        handle._apply_resize(QPointF(50.0, 50.0))

        assert item.rect().width() == pytest.approx(initial_width, abs=0.01), (
            "TOP_CENTER should not affect width"
        )

    def test_bottom_center_only_changes_y(self, canvas: CanvasView, qtbot: object) -> None:
        """BOTTOM_CENTER handle: diagonal drag changes height but not width."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        initial_width = item.rect().width()

        handle = _get_handle(item, HandlePosition.BOTTOM_CENTER)
        _setup_handle_drag(handle, item)

        handle._apply_resize(QPointF(50.0, 50.0))

        assert item.rect().width() == pytest.approx(initial_width, abs=0.01), (
            "BOTTOM_CENTER should not affect width"
        )

    def test_corner_handle_changes_both_axes(self, canvas: CanvasView, qtbot: object) -> None:
        """TOP_LEFT corner handle: diagonal drag changes both width and height."""
        item = _draw_rect(canvas, 100, 100, 400, 300)
        initial_width = item.rect().width()
        initial_height = item.rect().height()

        handle = _get_handle(item, HandlePosition.TOP_LEFT)
        _setup_handle_drag(handle, item)

        handle._apply_resize(QPointF(50.0, 50.0))

        assert item.rect().width() != pytest.approx(initial_width, abs=0.01), (
            "TOP_LEFT should change width"
        )
        assert item.rect().height() != pytest.approx(initial_height, abs=0.01), (
            "TOP_LEFT should change height"
        )

    def test_resize_enforces_minimum_size(self, canvas: CanvasView, qtbot: object) -> None:
        """Resizing below 1 cm is clamped to the minimum size (1 cm)."""
        item = _draw_rect(canvas, 100, 100, 110, 110)  # 10x10 cm

        handle = _get_handle(item, HandlePosition.MIDDLE_RIGHT)
        _setup_handle_drag(handle, item)

        # Delta moves right edge far to the left (would produce negative width)
        handle._apply_resize(QPointF(-500.0, 0.0))

        assert item.rect().width() >= 1.0, "Width must not drop below 1 cm minimum"
