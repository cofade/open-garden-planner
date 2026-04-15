"""Integration tests for GitHub issues #130, #131, #132, #133, #135 and rotation/angle bugs.

Each test exercises the primary UI workflow that exposed the bug.
"""

# ruff: noqa: ARG002

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import PolylineItem
from open_garden_planner.ui.canvas.items import PolygonItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _left_click(pos: QPointF | None = None) -> MagicMock:
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    return event


def _draw_house(view: CanvasView) -> None:
    """Draw a HOUSE polygon (4 vertices) and close it."""
    event = _left_click()
    view.set_active_tool(ToolType.HOUSE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(100, 100))
    tool.mouse_press(event, QPointF(400, 100))
    tool.mouse_press(event, QPointF(400, 400))
    tool.mouse_press(event, QPointF(100, 400))
    tool.mouse_double_click(event, QPointF(100, 400))


def _draw_triangle(view: CanvasView) -> PolygonItem:
    """Draw a generic triangle and return the created item."""
    event = _left_click()
    view.set_active_tool(ToolType.POLYGON)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(100, 100))
    tool.mouse_press(event, QPointF(500, 100))
    tool.mouse_press(event, QPointF(300, 400))
    tool.mouse_double_click(event, QPointF(300, 400))
    polys = [i for i in view.scene().items() if isinstance(i, PolygonItem)]
    return polys[0]


# ---------------------------------------------------------------------------
# Issue #135 — roof ridge deleted together with its house polygon
# ---------------------------------------------------------------------------


class TestIssue135RoofRidgeDeletion:
    """When a HOUSE polygon is deleted, its ROOF_RIDGE must be deleted too."""

    def test_delete_house_also_deletes_ridge(self, canvas: CanvasView, qtbot: object) -> None:
        """Deleting a HOUSE removes its ROOF_RIDGE in the same command."""
        _draw_house(canvas)

        scene = canvas.scene()
        ridges_before = [
            i for i in scene.items()
            if isinstance(i, PolylineItem) and i.object_type == ObjectType.ROOF_RIDGE
        ]
        assert len(ridges_before) == 1, "Expected one ridge after drawing house"

        # Select the house polygon and delete it
        houses = [
            i for i in scene.items()
            if isinstance(i, PolygonItem) and i.object_type == ObjectType.HOUSE
        ]
        assert len(houses) == 1
        houses[0].setSelected(True)

        canvas._delete_selected_items()  # noqa: SLF001

        ridges_after = [
            i for i in scene.items()
            if isinstance(i, PolylineItem) and i.object_type == ObjectType.ROOF_RIDGE
        ]
        houses_after = [
            i for i in scene.items()
            if isinstance(i, PolygonItem) and i.object_type == ObjectType.HOUSE
        ]
        assert len(ridges_after) == 0, "Ridge must be removed when house is deleted"
        assert len(houses_after) == 0, "House must be removed"


# ---------------------------------------------------------------------------
# Issue #133 — drawing on hidden layer auto-unhides it
# ---------------------------------------------------------------------------


class TestIssue133HiddenLayerAutounhide:
    """Drawing an item on a hidden layer must automatically unhide that layer."""

    def test_draw_on_hidden_layer_auto_unhides(self, canvas: CanvasView, qtbot: object) -> None:
        """After hiding the active layer, drawing a circle reveals it again."""
        scene = canvas.scene()
        active_layer = scene.active_layer
        assert active_layer is not None

        # Hide the active layer
        scene.update_layer_visibility(active_layer.id, False)
        assert not active_layer.visible, "Layer must be hidden before drawing"

        # Draw a circle on the (now hidden) active layer
        event = _left_click()
        canvas.set_active_tool(ToolType.CIRCLE)
        tool = canvas.tool_manager.active_tool
        tool.mouse_press(event, QPointF(500, 500))
        tool.mouse_press(event, QPointF(600, 500))

        # The layer must now be visible again
        assert active_layer.visible, "Layer must be auto-unhidden after drawing on it"

        # All items on the layer must be visible
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        layer_items = [
            i for i in scene.items()
            if isinstance(i, GardenItemMixin) and i.layer_id == active_layer.id
        ]
        assert layer_items, "At least one item expected on the layer"
        assert all(i.isVisible() for i in layer_items), "All layer items must be visible"


# ---------------------------------------------------------------------------
# Issue #132 — intra-object constraints allowed
# ---------------------------------------------------------------------------


class TestIssue132IntraObjectConstraints:
    """Constraints between two anchors of the same item must be allowed."""

    def test_horizontal_constraint_between_same_item_vertices(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Applying HORIZONTAL constraint between two vertices of one polygon succeeds."""
        _draw_triangle(canvas)

        scene = canvas.scene()
        constraints_before = len(scene.constraint_graph.constraints)

        canvas.set_active_tool(ToolType.CONSTRAINT_HORIZONTAL)
        tool = canvas.tool_manager.active_tool
        event = _left_click()

        # Click near vertex 0 (100, 100) then vertex 1 (500, 100) — both on same polygon
        tool.mouse_press(event, QPointF(100, 100))
        tool.mouse_press(event, QPointF(500, 100))

        constraints_after = len(scene.constraint_graph.constraints)
        assert constraints_after > constraints_before, (
            "Horizontal constraint between two vertices of the same polygon must be accepted"
        )


# ---------------------------------------------------------------------------
# Issue #131 — right-click empty canvas emits import signal
# ---------------------------------------------------------------------------


class TestIssue131RightClickCanvasMenu:
    """Right-clicking on empty canvas must emit import_background_image_requested."""

    def test_signal_exists_on_canvas_view(self, canvas: CanvasView, qtbot: object) -> None:
        """CanvasView declares the import_background_image_requested signal."""
        assert hasattr(canvas, "import_background_image_requested")

    def test_right_click_empty_canvas_emits_signal(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Right-click on empty area emits import_background_image_requested when action chosen."""
        emitted: list[bool] = []
        canvas.import_background_image_requested.connect(lambda: emitted.append(True))

        event = MagicMock(spec=QContextMenuEvent)
        event.pos.return_value = QPoint(1000, 1000)  # Far from any items
        event.globalPos.return_value = QPoint(1000, 1000)

        # Patch QMenu so exec() returns the import action (simulates user selecting it)
        with patch("open_garden_planner.ui.canvas.canvas_view.QMenu") as MockMenu:
            mock_menu = MockMenu.return_value
            mock_action = MagicMock()
            mock_menu.addAction.return_value = mock_action
            mock_menu.exec.return_value = mock_action  # user "clicked" the action

            canvas.contextMenuEvent(event)

        assert emitted, "import_background_image_requested must be emitted when user selects the action"


# ---------------------------------------------------------------------------
# Issue #130 — new project dialog exposes garden year
# ---------------------------------------------------------------------------


class TestIssue130NewProjectDialogYear:
    """NewProjectDialog must provide an optional garden year field."""

    def test_garden_year_none_when_unchecked(self, qtbot: object) -> None:
        """When the year checkbox is unchecked, garden_year returns None."""
        from open_garden_planner.ui.dialogs.new_project_dialog import NewProjectDialog

        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        assert not dialog._year_checkbox.isChecked()
        assert dialog.garden_year is None

    def test_garden_year_returned_when_checked(self, qtbot: object) -> None:
        """When the year checkbox is checked, garden_year returns the spinbox value."""
        from open_garden_planner.ui.dialogs.new_project_dialog import NewProjectDialog

        dialog = NewProjectDialog()
        qtbot.addWidget(dialog)  # type: ignore[attr-defined]

        dialog._year_checkbox.setChecked(True)
        dialog._year_spinbox.setValue(2026)

        assert dialog.garden_year == 2026


# ---------------------------------------------------------------------------
# Rotation undo — Ctrl+Z reverts rotation
# ---------------------------------------------------------------------------


def _draw_rect(view: CanvasView) -> object:
    """Draw a rectangle and return the created item."""
    from open_garden_planner.ui.canvas.items import RectangleItem

    event = _left_click()
    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(100, 100))
    tool.mouse_move(event, QPointF(400, 300))
    tool.mouse_release(event, QPointF(400, 300))
    rects = [i for i in view.scene().items() if isinstance(i, RectangleItem)]
    return rects[0]


class TestRotationUndo:
    """Ctrl+Z after rotating an item must revert the angle."""

    def test_rotation_undo_reverts_angle(self, canvas: CanvasView, qtbot: object) -> None:
        """Simulating _on_rotation_end pushes RotateItemCommand; undo reverts angle."""
        rect = _draw_rect(canvas)

        initial_angle = 0.0
        rect._apply_rotation(45.0)
        assert abs(rect.rotation_angle - 45.0) < 0.01

        # Manually trigger the rotation-end command registration
        rect._on_rotation_end(initial_angle)

        cmd_manager = canvas.scene().get_command_manager()
        assert cmd_manager.can_undo, "RotateItemCommand must be on the undo stack"

        cmd_manager.undo()
        assert abs(rect.rotation_angle - 0.0) < 0.01, "Undo must revert angle to 0°"


# ---------------------------------------------------------------------------
# Angle label — cleanup on deletion
# ---------------------------------------------------------------------------


class TestAngleLabelCleanup:
    """AngleDisplay must not persist after item deletion."""

    def test_angle_display_removed_on_item_deletion(
        self, canvas: CanvasView, qtbot: object
    ) -> None:
        """Deleting a rotated item removes its AngleDisplay from the scene."""
        from open_garden_planner.ui.canvas.items.resize_handle import AngleDisplay

        rect = _draw_rect(canvas)

        # Create the rotation handle so _angle_display is added to scene
        rect.show_rotation_handle()

        scene = canvas.scene()
        displays_before = [i for i in scene.items() if isinstance(i, AngleDisplay)]
        assert len(displays_before) == 1, "AngleDisplay must be in scene after show_rotation_handle"

        # Delete the rectangle
        rect.setSelected(True)
        canvas._delete_selected_items()  # noqa: SLF001

        displays_after = [i for i in scene.items() if isinstance(i, AngleDisplay)]
        assert len(displays_after) == 0, "AngleDisplay must be removed when item is deleted"
