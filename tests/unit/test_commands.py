"""Tests for the command pattern (undo/redo) implementation."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsScene

from open_garden_planner.core.commands import (
    AddVertexCommand,
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    DeleteVertexCommand,
    MoveItemsCommand,
    MoveVertexCommand,
)


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
