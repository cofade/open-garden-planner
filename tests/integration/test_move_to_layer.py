"""Integration tests: Move-to-layer via context menu (issue #138).

Verifies that:
  - MoveToLayerCommand correctly reassigns item.layer_id and refreshes the scene.
  - The command integrates with the CommandManager for full undo/redo support.
  - Multi-selection moves all selected items at once (with individual undo per item).
  - The 'Move to Layer' submenu is suppressed when only one layer exists.
"""

# ruff: noqa: ARG002

import uuid
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.core.commands import MoveToLayerCommand
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import RectangleItem


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _add_layer(scene: CanvasScene, name: str) -> Layer:
    """Add a new named layer to the scene and return it."""
    layer = Layer(id=uuid.uuid4(), name=name, z_order=len(scene.layers))
    scene.add_layer(layer)
    return layer


def _draw_rect(view: CanvasView, x1: float, y1: float, x2: float, y2: float) -> RectangleItem:
    """Draw a rectangle via the tool API and return the resulting scene item."""
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier

    view.set_active_tool(ToolType.RECTANGLE)
    tool = view.tool_manager.active_tool
    tool.mouse_press(event, QPointF(x1, y1))
    tool.mouse_move(event, QPointF(x2, y2))
    tool.mouse_release(event, QPointF(x2, y2))

    items = [i for i in view.scene().items() if isinstance(i, RectangleItem)]
    return items[-1]  # the most recently added


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMoveToLayerCommand:
    """Unit-level tests for MoveToLayerCommand through the CommandManager."""

    def test_move_single_item_changes_layer_id(self, canvas: CanvasView, qtbot) -> None:
        """Executing MoveToLayerCommand assigns the item to the target layer."""
        scene = canvas.scene()
        layer2 = _add_layer(scene, "Layer 2")

        item = _draw_rect(canvas, 100, 100, 300, 200)
        original_layer_id = item.layer_id
        assert original_layer_id != layer2.id

        cmd = MoveToLayerCommand([item], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)

        assert item.layer_id == layer2.id

    def test_undo_restores_original_layer(self, canvas: CanvasView, qtbot) -> None:
        """Undoing MoveToLayerCommand returns the item to its previous layer."""
        scene = canvas.scene()
        layer2 = _add_layer(scene, "Layer 2")

        item = _draw_rect(canvas, 100, 100, 300, 200)
        original_layer_id = item.layer_id

        cmd = MoveToLayerCommand([item], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)
        assert item.layer_id == layer2.id

        canvas.command_manager.undo()
        assert item.layer_id == original_layer_id

    def test_redo_reapplies_move(self, canvas: CanvasView, qtbot) -> None:
        """Redo after undo re-assigns the item to the target layer."""
        scene = canvas.scene()
        layer2 = _add_layer(scene, "Layer 2")

        item = _draw_rect(canvas, 100, 100, 300, 200)

        cmd = MoveToLayerCommand([item], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)
        canvas.command_manager.undo()
        canvas.command_manager.redo()

        assert item.layer_id == layer2.id

    def test_move_multi_selection_moves_all_items(self, canvas: CanvasView, qtbot) -> None:
        """Moving multiple items at once works; each item's old layer is captured individually."""
        scene = canvas.scene()
        layer2 = _add_layer(scene, "Layer 2")

        item1 = _draw_rect(canvas, 100, 100, 200, 200)
        item2 = _draw_rect(canvas, 300, 100, 400, 200)
        old_layer1 = item1.layer_id
        old_layer2 = item2.layer_id

        cmd = MoveToLayerCommand([item1, item2], layer2.id, scene, "Layer 2")
        canvas.command_manager.execute(cmd)

        assert item1.layer_id == layer2.id
        assert item2.layer_id == layer2.id

        canvas.command_manager.undo()

        assert item1.layer_id == old_layer1
        assert item2.layer_id == old_layer2

    def test_command_description_reflects_item_count(self, canvas: CanvasView, qtbot) -> None:
        """The command description names the target layer and item count."""
        scene = canvas.scene()
        layer2 = _add_layer(scene, "My Garden Layer")

        item = _draw_rect(canvas, 100, 100, 300, 200)
        cmd = MoveToLayerCommand([item], layer2.id, scene, "My Garden Layer")

        assert "My Garden Layer" in cmd.description
        assert "1" in cmd.description


class TestMoveToLayerMenuVisibility:
    """Tests for the 'Move to Layer' submenu helper on GardenItemMixin."""

    def test_submenu_absent_when_only_one_layer(self, canvas: CanvasView, qtbot) -> None:
        """_build_move_to_layer_menu returns None when the project has a single layer."""
        from PyQt6.QtWidgets import QMenu

        item = _draw_rect(canvas, 100, 100, 300, 200)
        # Default canvas has one layer only
        assert len(canvas.scene().layers) == 1

        parent_menu = QMenu()
        result = item._build_move_to_layer_menu(parent_menu)
        assert result is None

    def test_submenu_present_when_multiple_layers(self, canvas: CanvasView, qtbot) -> None:
        """_build_move_to_layer_menu returns a QMenu when ≥2 layers exist."""
        from PyQt6.QtWidgets import QMenu

        scene = canvas.scene()
        _add_layer(scene, "Layer 2")
        assert len(scene.layers) == 2

        item = _draw_rect(canvas, 100, 100, 300, 200)

        parent_menu = QMenu()
        result = item._build_move_to_layer_menu(parent_menu)
        assert result is not None

    def test_submenu_excludes_current_layer(self, canvas: CanvasView, qtbot) -> None:
        """The 'Move to Layer' submenu does not list the item's current layer."""
        from PyQt6.QtWidgets import QMenu

        scene = canvas.scene()
        layer2 = _add_layer(scene, "Layer 2")

        item = _draw_rect(canvas, 100, 100, 300, 200)
        current_layer_id = item.layer_id

        parent_menu = QMenu()
        submenu = item._build_move_to_layer_menu(parent_menu)
        assert submenu is not None

        action_datas = [a.data() for a in submenu.actions()]
        assert current_layer_id not in action_datas, (
            "Current layer must not appear in 'Move to Layer' submenu"
        )
        assert layer2.id in action_datas
