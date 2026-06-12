"""Tests for the command pattern (undo/redo) implementation."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import (
    AddLayerCommand,
    AddVertexCommand,
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    DeleteLayerCommand,
    DeleteVertexCommand,
    MoveItemsCommand,
    MoveVertexCommand,
    RenameLayerCommand,
    ReorderLayersCommand,
    SetLayerPropertyCommand,
)
from open_garden_planner.models.layer import Layer


class TestCommandManager:
    """Tests for CommandManager class."""

    @pytest.fixture
    def manager(self, qtbot) -> CommandManager:
        """Create a command manager for testing."""
        return CommandManager()

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def test_initial_state(self, manager) -> None:
        """Test that manager starts with empty stacks."""
        assert not manager.can_undo
        assert not manager.can_redo
        assert manager.undo_description is None
        assert manager.redo_description is None

    def test_execute_enables_undo(self, manager, scene) -> None:
        """Test that executing a command enables undo."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "test")

        manager.execute(command)

        assert manager.can_undo
        assert not manager.can_redo
        assert manager.undo_description == "Create test"

    def test_undo_moves_to_redo_stack(self, manager, scene) -> None:
        """Test that undo moves command to redo stack."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "test")
        manager.execute(command)

        manager.undo()

        assert not manager.can_undo
        assert manager.can_redo
        assert manager.redo_description == "Create test"

    def test_redo_moves_back_to_undo_stack(self, manager, scene) -> None:
        """Test that redo moves command back to undo stack."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "test")
        manager.execute(command)
        manager.undo()

        manager.redo()

        assert manager.can_undo
        assert not manager.can_redo

    def test_new_command_clears_redo_stack(self, manager, scene) -> None:
        """Test that executing new command clears redo stack."""
        item1 = QGraphicsRectItem(0, 0, 100, 100)
        item2 = QGraphicsRectItem(0, 0, 100, 100)
        manager.execute(CreateItemCommand(scene, item1, "first"))
        manager.undo()
        assert manager.can_redo

        manager.execute(CreateItemCommand(scene, item2, "second"))

        assert not manager.can_redo

    def test_clear_empties_both_stacks(self, manager, scene) -> None:
        """Test that clear removes all history."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        manager.execute(CreateItemCommand(scene, item, "test"))
        manager.undo()

        manager.clear()

        assert not manager.can_undo
        assert not manager.can_redo

    def test_signals_emitted(self, manager, scene, qtbot) -> None:
        """Test that signals are emitted correctly."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "test")

        with qtbot.waitSignals([
            manager.can_undo_changed,
            manager.command_executed,
        ]):
            manager.execute(command)


class TestCreateItemCommand:
    """Tests for CreateItemCommand class."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def test_execute_adds_item_to_scene(self, scene) -> None:
        """Test that execute adds the item to the scene."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "rectangle")

        command.execute()

        assert item in scene.items()

    def test_undo_removes_item_from_scene(self, scene) -> None:
        """Test that undo removes the item from the scene."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "rectangle")
        command.execute()

        command.undo()

        assert item not in scene.items()

    def test_redo_adds_item_back(self, scene) -> None:
        """Test that re-executing adds item back."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "rectangle")
        command.execute()
        command.undo()

        command.execute()

        assert item in scene.items()

    def test_description(self, scene) -> None:
        """Test the description property."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = CreateItemCommand(scene, item, "polygon")

        assert command.description == "Create polygon"


class TestDeleteItemsCommand:
    """Tests for DeleteItemsCommand class."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def test_execute_removes_items(self, scene) -> None:
        """Test that execute removes items from scene."""
        item1 = QGraphicsRectItem(0, 0, 100, 100)
        item2 = QGraphicsRectItem(100, 100, 100, 100)
        scene.addItem(item1)
        scene.addItem(item2)
        command = DeleteItemsCommand(scene, [item1, item2])

        command.execute()

        assert item1 not in scene.items()
        assert item2 not in scene.items()

    def test_undo_restores_items(self, scene) -> None:
        """Test that undo restores items to scene."""
        item1 = QGraphicsRectItem(0, 0, 100, 100)
        item2 = QGraphicsRectItem(100, 100, 100, 100)
        scene.addItem(item1)
        scene.addItem(item2)
        command = DeleteItemsCommand(scene, [item1, item2])
        command.execute()

        command.undo()

        assert item1 in scene.items()
        assert item2 in scene.items()

    def test_description_single_item(self, scene) -> None:
        """Test description for single item."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = DeleteItemsCommand(scene, [item])

        assert command.description == "Delete item"

    def test_description_multiple_items(self, scene) -> None:
        """Test description for multiple items."""
        items = [QGraphicsRectItem(0, 0, 100, 100) for _ in range(3)]
        command = DeleteItemsCommand(scene, items)

        assert command.description == "Delete 3 items"


class TestMoveItemsCommand:
    """Tests for MoveItemsCommand class."""

    def test_execute_moves_items(self) -> None:
        """Test that execute moves items by delta."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        item.setPos(50, 50)
        command = MoveItemsCommand([item], QPointF(10, 20))

        command.execute()

        assert item.pos().x() == 60
        assert item.pos().y() == 70

    def test_undo_reverses_move(self) -> None:
        """Test that undo reverses the movement."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        item.setPos(50, 50)
        command = MoveItemsCommand([item], QPointF(10, 20))
        command.execute()

        command.undo()

        assert item.pos().x() == 50
        assert item.pos().y() == 50

    def test_moves_multiple_items(self) -> None:
        """Test moving multiple items together."""
        item1 = QGraphicsRectItem(0, 0, 100, 100)
        item2 = QGraphicsRectItem(0, 0, 100, 100)
        item1.setPos(0, 0)
        item2.setPos(100, 100)
        command = MoveItemsCommand([item1, item2], QPointF(5, 5))

        command.execute()

        assert item1.pos().x() == 5
        assert item2.pos().x() == 105

    def test_description_single_item(self) -> None:
        """Test description for single item."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = MoveItemsCommand([item], QPointF(10, 10))

        assert command.description == "Move item"

    def test_description_multiple_items(self) -> None:
        """Test description for multiple items."""
        items = [QGraphicsRectItem(0, 0, 100, 100) for _ in range(5)]
        command = MoveItemsCommand(items, QPointF(10, 10))

        assert command.description == "Move 5 items"


class TestMoveVertexCommand:
    """Tests for MoveVertexCommand class."""

    def test_execute_moves_vertex(self) -> None:
        """Test that execute calls apply function with new position."""
        applied_values: list[tuple[int, QPointF]] = []

        def apply_func(item, index, pos):
            applied_values.append((index, pos))

        item = QGraphicsRectItem(0, 0, 100, 100)
        old_pos = QPointF(0, 0)
        new_pos = QPointF(50, 50)
        command = MoveVertexCommand(item, 0, old_pos, new_pos, apply_func)

        command.execute()

        assert len(applied_values) == 1
        assert applied_values[0][0] == 0
        assert applied_values[0][1] == new_pos

    def test_undo_restores_vertex(self) -> None:
        """Test that undo calls apply function with old position."""
        applied_values: list[tuple[int, QPointF]] = []

        def apply_func(item, index, pos):
            applied_values.append((index, pos))

        item = QGraphicsRectItem(0, 0, 100, 100)
        old_pos = QPointF(0, 0)
        new_pos = QPointF(50, 50)
        command = MoveVertexCommand(item, 0, old_pos, new_pos, apply_func)
        command.execute()

        command.undo()

        assert len(applied_values) == 2
        assert applied_values[1][1] == old_pos

    def test_description(self) -> None:
        """Test the description property."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = MoveVertexCommand(item, 0, QPointF(0, 0), QPointF(50, 50), lambda *_: None)

        assert command.description == "Move vertex"


class TestAddVertexCommand:
    """Tests for AddVertexCommand class."""

    def test_execute_adds_vertex(self) -> None:
        """Test that execute calls add function."""
        add_calls: list[tuple[int, QPointF]] = []
        remove_calls: list[int] = []

        def add_func(item, index, pos):
            add_calls.append((index, pos))

        def remove_func(item, index):
            remove_calls.append(index)

        item = QGraphicsRectItem(0, 0, 100, 100)
        pos = QPointF(50, 0)
        command = AddVertexCommand(item, 1, pos, add_func, remove_func)

        command.execute()

        assert len(add_calls) == 1
        assert add_calls[0] == (1, pos)
        assert len(remove_calls) == 0

    def test_undo_removes_vertex(self) -> None:
        """Test that undo calls remove function."""
        add_calls: list[tuple[int, QPointF]] = []
        remove_calls: list[int] = []

        def add_func(item, index, pos):
            add_calls.append((index, pos))

        def remove_func(item, index):
            remove_calls.append(index)

        item = QGraphicsRectItem(0, 0, 100, 100)
        pos = QPointF(50, 0)
        command = AddVertexCommand(item, 1, pos, add_func, remove_func)
        command.execute()

        command.undo()

        assert len(remove_calls) == 1
        assert remove_calls[0] == 1

    def test_description(self) -> None:
        """Test the description property."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = AddVertexCommand(item, 1, QPointF(50, 0), lambda *_: None, lambda *_: None)

        assert command.description == "Add vertex"


class TestDeleteVertexCommand:
    """Tests for DeleteVertexCommand class."""

    def test_execute_removes_vertex(self) -> None:
        """Test that execute calls remove function."""
        add_calls: list[tuple[int, QPointF]] = []
        remove_calls: list[int] = []

        def add_func(item, index, pos):
            add_calls.append((index, pos))

        def remove_func(item, index):
            remove_calls.append(index)

        item = QGraphicsRectItem(0, 0, 100, 100)
        pos = QPointF(50, 0)
        command = DeleteVertexCommand(item, 1, pos, add_func, remove_func)

        command.execute()

        assert len(remove_calls) == 1
        assert remove_calls[0] == 1
        assert len(add_calls) == 0

    def test_undo_adds_vertex_back(self) -> None:
        """Test that undo calls add function to restore vertex."""
        add_calls: list[tuple[int, QPointF]] = []
        remove_calls: list[int] = []

        def add_func(item, index, pos):
            add_calls.append((index, pos))

        def remove_func(item, index):
            remove_calls.append(index)

        item = QGraphicsRectItem(0, 0, 100, 100)
        pos = QPointF(50, 0)
        command = DeleteVertexCommand(item, 1, pos, add_func, remove_func)
        command.execute()

        command.undo()

        assert len(add_calls) == 1
        assert add_calls[0] == (1, pos)

    def test_description(self) -> None:
        """Test the description property."""
        item = QGraphicsRectItem(0, 0, 100, 100)
        command = DeleteVertexCommand(item, 1, QPointF(50, 0), lambda *_: None, lambda *_: None)

        assert command.description == "Delete vertex"


# ── Layer commands (issue: layer operations were not undoable) ──────────────


@pytest.fixture
def layer_scene(qtbot):
    """Real CanvasScene with three layers: Top, Middle, Bottom (top first)."""
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene(width_cm=5000, height_cm=3000)
    top = Layer(name="Top", z_order=2)
    middle = Layer(name="Middle", z_order=1)
    bottom = Layer(name="Bottom", z_order=0)
    scene.set_layers([top, middle, bottom])
    scene.set_active_layer(top)
    return scene


def _rect_on_layer(scene, layer) -> QGraphicsRectItem:
    """Add a plain rect item carrying a layer_id to the scene."""
    item = QGraphicsRectItem(0, 0, 100, 100)
    item.layer_id = layer.id
    scene.addItem(item)
    return item


class TestAddLayerCommand:
    """Tests for AddLayerCommand."""

    def test_execute_inserts_at_top_with_highest_z(self, layer_scene) -> None:
        """The new layer lands at index 0 with the highest z_order and is active."""
        new_layer = Layer(name="New")
        command = AddLayerCommand(layer_scene, new_layer)

        command.execute()

        assert layer_scene.layers[0] is new_layer
        assert new_layer.z_order == max(lyr.z_order for lyr in layer_scene.layers)
        assert layer_scene.active_layer is new_layer

    def test_undo_restores_order_z_orders_and_active(self, layer_scene) -> None:
        """Undo removes the layer and restores exact z_orders + active layer."""
        # Seed non-formula z_orders (e.g. from DXF import) to prove the exact
        # snapshot is restored, not a recompute.
        top, middle, bottom = layer_scene.layers
        top.z_order, middle.z_order, bottom.z_order = 30, 20, 10
        prev_active = layer_scene.active_layer
        command = AddLayerCommand(layer_scene, Layer(name="New"))
        command.execute()

        command.undo()

        assert [lyr.name for lyr in layer_scene.layers] == ["Top", "Middle", "Bottom"]
        assert [lyr.z_order for lyr in layer_scene.layers] == [30, 20, 10]
        assert layer_scene.active_layer is prev_active

    def test_redo_reapplies(self, layer_scene) -> None:
        """Redo (execute after undo) re-inserts and re-activates the layer."""
        new_layer = Layer(name="New")
        command = AddLayerCommand(layer_scene, new_layer)
        command.execute()
        command.undo()

        command.execute()

        assert layer_scene.layers[0] is new_layer
        assert layer_scene.active_layer is new_layer

    def test_description(self, layer_scene) -> None:
        """Description includes the layer name."""
        command = AddLayerCommand(layer_scene, Layer(name="Plants"))

        assert command.description == "Add layer 'Plants'"


class TestDeleteLayerCommand:
    """Tests for DeleteLayerCommand."""

    def test_execute_moves_items_to_replacement(self, layer_scene) -> None:
        """Items on a non-top deleted layer move to the top layer (index > 0)."""
        top, middle, _ = layer_scene.layers
        item = _rect_on_layer(layer_scene, middle)
        command = DeleteLayerCommand(layer_scene, middle.id)

        command.execute()

        assert middle not in layer_scene.layers
        assert item.layer_id == top.id

    def test_execute_top_layer_replacement_is_second(self, layer_scene) -> None:
        """Deleting the top layer (index 0) moves items to the next layer."""
        top, middle, _ = layer_scene.layers
        item = _rect_on_layer(layer_scene, top)
        command = DeleteLayerCommand(layer_scene, top.id)

        command.execute()

        assert top not in layer_scene.layers
        assert item.layer_id == middle.id

    def test_execute_active_layer_handover(self, layer_scene) -> None:
        """Deleting the active layer hands activity to the replacement."""
        top, _, bottom = layer_scene.layers
        layer_scene.set_active_layer(bottom)
        command = DeleteLayerCommand(layer_scene, bottom.id)

        command.execute()

        assert layer_scene.active_layer is top

    def test_undo_restores_index_items_and_active(self, layer_scene) -> None:
        """Undo re-inserts at the original index and restores item layer_ids."""
        top, middle, _ = layer_scene.layers
        layer_scene.set_active_layer(middle)
        item = _rect_on_layer(layer_scene, middle)
        command = DeleteLayerCommand(layer_scene, middle.id)
        command.execute()

        command.undo()

        assert layer_scene.layers[1] is middle
        assert item.layer_id == middle.id
        assert layer_scene.active_layer is middle

    def test_redo_recaptures_items_after_undo(self, layer_scene) -> None:
        """Redo after undo moves the same items again."""
        top, middle, _ = layer_scene.layers
        item = _rect_on_layer(layer_scene, middle)
        command = DeleteLayerCommand(layer_scene, middle.id)
        command.execute()
        command.undo()

        command.execute()

        assert middle not in layer_scene.layers
        assert item.layer_id == top.id

    def test_missing_layer_raises(self, layer_scene) -> None:
        """Constructing against an unknown layer id raises ValueError."""
        from uuid import uuid4

        with pytest.raises(ValueError, match="No layer with id"):
            DeleteLayerCommand(layer_scene, uuid4())

    def test_description(self, layer_scene) -> None:
        """Description includes the layer name."""
        command = DeleteLayerCommand(layer_scene, layer_scene.layers[1].id)

        assert command.description == "Delete layer 'Middle'"


class TestRenameLayerCommand:
    """Tests for RenameLayerCommand."""

    def test_execute_undo_redo(self, layer_scene, qtbot) -> None:
        """Rename round-trips through execute/undo/redo and emits layers_changed."""
        layer = layer_scene.layers[0]
        command = RenameLayerCommand(layer_scene, layer, "Renamed")

        with qtbot.waitSignal(layer_scene.layers_changed, timeout=1000):
            command.execute()
        assert layer.name == "Renamed"

        with qtbot.waitSignal(layer_scene.layers_changed, timeout=1000):
            command.undo()
        assert layer.name == "Top"

        command.execute()
        assert layer.name == "Renamed"

    def test_description(self, layer_scene) -> None:
        """Description shows the new name."""
        command = RenameLayerCommand(layer_scene, layer_scene.layers[0], "Lawn")

        assert command.description == "Rename layer to 'Lawn'"


class TestReorderLayersCommand:
    """Tests for ReorderLayersCommand."""

    def test_execute_applies_new_order(self, layer_scene) -> None:
        """Execute applies the new order with recomputed z_orders."""
        top, middle, bottom = layer_scene.layers
        command = ReorderLayersCommand(layer_scene, [bottom, top, middle])

        command.execute()

        assert layer_scene.layers == [bottom, top, middle]
        assert [lyr.z_order for lyr in layer_scene.layers] == [2, 1, 0]

    def test_undo_restores_exact_order_and_z_orders(self, layer_scene) -> None:
        """Undo restores the original order and the exact original z_orders."""
        top, middle, bottom = layer_scene.layers
        # Non-formula z_orders (e.g. from DXF import) must survive the round trip.
        top.z_order, middle.z_order, bottom.z_order = 30, 20, 10
        command = ReorderLayersCommand(layer_scene, [bottom, top, middle])
        command.execute()

        command.undo()

        assert layer_scene.layers == [top, middle, bottom]
        assert [lyr.z_order for lyr in layer_scene.layers] == [30, 20, 10]

    def test_description(self, layer_scene) -> None:
        """Description is the static reorder text."""
        command = ReorderLayersCommand(layer_scene, list(layer_scene.layers))

        assert command.description == "Reorder layers"


class TestSetLayerPropertyCommand:
    """Tests for SetLayerPropertyCommand."""

    def test_visible_round_trip_affects_items(self, layer_scene) -> None:
        """Visibility toggles the layer flag and the items on it."""
        layer = layer_scene.layers[0]
        item = _rect_on_layer(layer_scene, layer)
        command = SetLayerPropertyCommand(layer_scene, layer, "visible", True, False)

        command.execute()
        assert layer.visible is False
        assert item.isVisible() is False

        command.undo()
        assert layer.visible is True
        assert item.isVisible() is True

    def test_locked_round_trip_affects_items(self, layer_scene) -> None:
        """Locking clears the items' selectable flag; undo restores it."""
        from PyQt6.QtWidgets import QGraphicsItem

        layer = layer_scene.layers[0]
        item = _rect_on_layer(layer_scene, layer)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        command = SetLayerPropertyCommand(layer_scene, layer, "locked", False, True)

        command.execute()
        assert layer.locked is True
        assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

        command.undo()
        assert layer.locked is False
        assert bool(item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

    def test_opacity_round_trip_affects_items(self, layer_scene) -> None:
        """Opacity changes propagate to items and undo restores them."""
        layer = layer_scene.layers[0]
        item = _rect_on_layer(layer_scene, layer)
        command = SetLayerPropertyCommand(layer_scene, layer, "opacity", 1.0, 0.4)

        command.execute()
        assert layer.opacity == 0.4
        assert item.opacity() == pytest.approx(0.4)

        command.undo()
        assert layer.opacity == 1.0
        assert item.opacity() == pytest.approx(1.0)

    def test_invalid_property_raises(self, layer_scene) -> None:
        """An unsupported property name raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported layer property"):
            SetLayerPropertyCommand(layer_scene, layer_scene.layers[0], "name", "a", "b")

    def test_descriptions(self, layer_scene) -> None:
        """Each property/value pair yields its specific description."""
        layer = layer_scene.layers[0]

        show = SetLayerPropertyCommand(layer_scene, layer, "visible", False, True)
        hide = SetLayerPropertyCommand(layer_scene, layer, "visible", True, False)
        lock = SetLayerPropertyCommand(layer_scene, layer, "locked", False, True)
        unlock = SetLayerPropertyCommand(layer_scene, layer, "locked", True, False)
        opacity = SetLayerPropertyCommand(layer_scene, layer, "opacity", 1.0, 0.4)

        assert show.description == "Show layer 'Top'"
        assert hide.description == "Hide layer 'Top'"
        assert lock.description == "Lock layer 'Top'"
        assert unlock.description == "Unlock layer 'Top'"
        assert opacity.description == "Set opacity of layer 'Top' to 40%"
