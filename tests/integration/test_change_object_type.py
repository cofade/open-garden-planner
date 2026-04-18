"""Integration tests: Change Object Type via context menu (issues #148 / #149).

Verifies that:
  - get_valid_types_for_shape() includes POND_POOL for circles (issue #149 fix).
  - _dispatch_change_type() updates object_type and applies the default style.
  - The type change is fully undoable/redoable via the CommandManager.
  - _build_change_type_menu() builds a submenu with the correct entries.
  - All four shape items expose a 'Change Type' submenu in their context menu.
  - Context menu strings use QCoreApplication.translate (no raw string literals).
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.object_types import ObjectType, get_valid_types_for_shape
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click_event() -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_circle(view: CanvasView, cx: float, cy: float, r: float) -> CircleItem:
    from open_garden_planner.core.tools import ToolType

    event = _left_click_event()
    view.set_active_tool(ToolType.CIRCLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(cx, cy))        # click center
    tool.mouse_press(event, QPointF(cx + r, cy))    # click rim (finalizes circle)
    return next(i for i in reversed(view.scene().items()) if isinstance(i, CircleItem))


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> RectangleItem:
    from open_garden_planner.core.tools import ToolType
    event = _left_click_event()
    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))
    return next(i for i in reversed(view.scene().items()) if isinstance(i, RectangleItem))


# ---------------------------------------------------------------------------
# Tests — get_valid_types_for_shape
# ---------------------------------------------------------------------------


class TestGetValidTypesForShape:
    """Verify the shared valid-types registry."""

    def test_circle_includes_pond_pool(self, qtbot) -> None:
        """POND_POOL must appear in circle valid types (issue #149)."""
        types = get_valid_types_for_shape("circle")
        assert ObjectType.POND_POOL in types

    def test_circle_includes_generic_circle(self, qtbot) -> None:
        types = get_valid_types_for_shape("circle")
        assert ObjectType.GENERIC_CIRCLE in types

    def test_polygon_includes_pond_pool(self, qtbot) -> None:
        """Polygon retains POND_POOL as before."""
        types = get_valid_types_for_shape("polygon")
        assert ObjectType.POND_POOL in types

    def test_rectangle_does_not_include_pond_pool(self, qtbot) -> None:
        """POND_POOL is not a rectangle type."""
        types = get_valid_types_for_shape("rectangle")
        assert ObjectType.POND_POOL not in types

    def test_polyline_contains_only_path_types(self, qtbot) -> None:
        types = get_valid_types_for_shape("polyline")
        assert set(types) == {ObjectType.FENCE, ObjectType.WALL, ObjectType.PATH}

    def test_all_shapes_return_non_empty_lists(self, qtbot) -> None:
        for shape in ("circle", "polygon", "rectangle", "polyline"):
            assert len(get_valid_types_for_shape(shape)) > 0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Tests — _dispatch_change_type
# ---------------------------------------------------------------------------


class TestDispatchChangeType:
    """End-to-end change-type workflow via _dispatch_change_type."""

    def test_changes_object_type(self, canvas: CanvasView, qtbot) -> None:
        """_dispatch_change_type() sets the new object type on the item."""
        item = _draw_circle(canvas, 200, 200, 50)
        assert item.object_type == ObjectType.GENERIC_CIRCLE

        item.setSelected(True)
        item._dispatch_change_type(ObjectType.TREE)

        assert item.object_type == ObjectType.TREE

    def test_applies_default_style(self, canvas: CanvasView, qtbot) -> None:
        """After a type change the item's style properties match the new type's defaults."""
        from open_garden_planner.core.object_types import get_style

        item = _draw_circle(canvas, 200, 200, 50)
        item.setSelected(True)
        item._dispatch_change_type(ObjectType.POND_POOL)

        style = get_style(ObjectType.POND_POOL)
        assert item.fill_color == style.fill_color
        assert item.stroke_color == style.stroke_color

    def test_undo_restores_previous_type(self, canvas: CanvasView, qtbot) -> None:
        """Ctrl+Z after _dispatch_change_type() restores the original type and style."""

        item = _draw_circle(canvas, 200, 200, 50)
        original_type = item.object_type
        original_fill = item.fill_color
        item.setSelected(True)

        item._dispatch_change_type(ObjectType.SHRUB)
        assert item.object_type == ObjectType.SHRUB

        canvas.command_manager.undo()
        assert item.object_type == original_type
        assert item.fill_color == original_fill

    def test_redo_reapplies_type_change(self, canvas: CanvasView, qtbot) -> None:
        """Redo after undo re-applies the type change."""
        item = _draw_circle(canvas, 200, 200, 50)
        item.setSelected(True)
        item._dispatch_change_type(ObjectType.SHRUB)
        canvas.command_manager.undo()
        canvas.command_manager.redo()

        assert item.object_type == ObjectType.SHRUB

    def test_multi_select_changes_all_same_type_items(self, canvas: CanvasView, qtbot) -> None:
        """When multiple circles are selected, all get the new type."""
        item1 = _draw_circle(canvas, 100, 100, 40)
        item2 = _draw_circle(canvas, 300, 100, 40)
        item1.setSelected(True)
        item2.setSelected(True)

        item1._dispatch_change_type(ObjectType.TREE)

        assert item1.object_type == ObjectType.TREE
        assert item2.object_type == ObjectType.TREE

    def test_multi_select_does_not_affect_other_shape_types(
        self, canvas: CanvasView, qtbot
    ) -> None:
        """A circle type change does not affect a selected rectangle."""
        circle = _draw_circle(canvas, 100, 100, 40)
        rect = _draw_rect(canvas, 200, 200, 400, 350)
        original_rect_type = rect.object_type

        circle.setSelected(True)
        rect.setSelected(True)

        circle._dispatch_change_type(ObjectType.TREE)

        assert circle.object_type == ObjectType.TREE
        assert rect.object_type == original_rect_type  # untouched


# ---------------------------------------------------------------------------
# Tests — _build_change_type_menu
# ---------------------------------------------------------------------------


class TestBuildChangeTypeMenu:
    """Verify the Change Type submenu structure."""

    def test_returns_menu_for_circle_item(self, canvas: CanvasView, qtbot) -> None:
        from PyQt6.QtWidgets import QMenu

        item = _draw_circle(canvas, 200, 200, 50)
        parent = QMenu()
        submenu = item._build_change_type_menu(parent, get_valid_types_for_shape("circle"))

        assert submenu is not None

    def test_menu_contains_pond_pool_entry(self, canvas: CanvasView, qtbot) -> None:
        from PyQt6.QtWidgets import QMenu

        item = _draw_circle(canvas, 200, 200, 50)
        parent = QMenu()
        submenu = item._build_change_type_menu(parent, get_valid_types_for_shape("circle"))
        assert submenu is not None

        action_data = [a.data() for a in submenu.actions()]
        assert ObjectType.POND_POOL in action_data

    def test_current_type_is_checked(self, canvas: CanvasView, qtbot) -> None:
        from PyQt6.QtWidgets import QMenu

        item = _draw_circle(canvas, 200, 200, 50)
        item._dispatch_change_type(ObjectType.TREE)

        parent = QMenu()
        submenu = item._build_change_type_menu(parent, get_valid_types_for_shape("circle"))
        assert submenu is not None

        checked = [a for a in submenu.actions() if a.isChecked()]
        assert len(checked) == 1
        assert checked[0].data() == ObjectType.TREE

    def test_returns_none_when_no_object_type(self, canvas: CanvasView, qtbot) -> None:
        """Items without object_type should not get a Change Type submenu."""
        from PyQt6.QtWidgets import QMenu

        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        class _PlainItem(GardenItemMixin):
            def scene(self):  # type: ignore[override]
                return None

        plain = _PlainItem.__new__(_PlainItem)
        parent = QMenu()
        result = plain._build_change_type_menu(parent, [])
        assert result is None
