"""Command pattern implementation for undo/redo functionality.

All modifications to the canvas are wrapped in commands that can be
executed, undone, and redone.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QPointF, pyqtSignal
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

if TYPE_CHECKING:
    pass


class Command(ABC):
    """Abstract base class for all undoable commands."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the command."""
        pass

    @abstractmethod
    def execute(self) -> None:
        """Execute (or re-execute) the command."""
        pass

    @abstractmethod
    def undo(self) -> None:
        """Undo the command."""
        pass


class CommandManager(QObject):
    """Manages the undo/redo stack.

    Signals:
        can_undo_changed: Emitted when undo availability changes
        can_redo_changed: Emitted when redo availability changes
        command_executed: Emitted after a command is executed (description)
    """

    can_undo_changed = pyqtSignal(bool)
    can_redo_changed = pyqtSignal(bool)
    command_executed = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the command manager."""
        super().__init__(parent)
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []

    def execute(self, command: Command) -> None:
        """Execute a command and add it to the undo stack.

        Clears the redo stack since we've branched off.
        """
        command.execute()
        self._undo_stack.append(command)

        # Clear redo stack on new command
        had_redo = len(self._redo_stack) > 0
        self._redo_stack.clear()

        self.can_undo_changed.emit(True)
        if had_redo:
            self.can_redo_changed.emit(False)
        self.command_executed.emit(command.description)

    def undo(self) -> None:
        """Undo the last command."""
        if not self._undo_stack:
            return

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

        self.can_undo_changed.emit(len(self._undo_stack) > 0)
        self.can_redo_changed.emit(True)

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self._redo_stack:
            return

        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)

        self.can_undo_changed.emit(True)
        self.can_redo_changed.emit(len(self._redo_stack) > 0)

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.can_undo_changed.emit(False)
        self.can_redo_changed.emit(False)

    @property
    def can_undo(self) -> bool:
        """Whether there are commands to undo."""
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        """Whether there are commands to redo."""
        return len(self._redo_stack) > 0

    @property
    def undo_description(self) -> str | None:
        """Description of the command that would be undone."""
        if self._undo_stack:
            return self._undo_stack[-1].description
        return None

    @property
    def redo_description(self) -> str | None:
        """Description of the command that would be redone."""
        if self._redo_stack:
            return self._redo_stack[-1].description
        return None


class CreateItemCommand(Command):
    """Command for creating a new item on the scene."""

    def __init__(
        self,
        scene: QGraphicsScene,
        item: QGraphicsItem,
        item_type: str = "item",
    ) -> None:
        """Initialize the create command.

        Args:
            scene: The scene to add the item to
            item: The item to add
            item_type: Description of item type (e.g., "rectangle", "polygon")
        """
        self._scene = scene
        self._item = item
        self._item_type = item_type

    @property
    def description(self) -> str:
        """Human-readable description."""
        return f"Create {self._item_type}"

    def execute(self) -> None:
        """Add the item to the scene."""
        if self._item.scene() is None:
            self._scene.addItem(self._item)

    def undo(self) -> None:
        """Remove the item from the scene."""
        if self._item.scene() is not None:
            self._scene.removeItem(self._item)


class CreateItemsCommand(Command):
    """Command for creating multiple items on the scene."""

    def __init__(
        self,
        scene: QGraphicsScene,
        items: list[QGraphicsItem],
        item_type: str = "items",
    ) -> None:
        """Initialize the create items command.

        Args:
            scene: The scene to add the items to
            items: List of items to add
            item_type: Description of item type (e.g., "pasted objects")
        """
        self._scene = scene
        self._items = list(items)  # Copy the list
        self._item_type = item_type

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return f"Create {self._item_type}"
        return f"Create {count} {self._item_type}"

    def execute(self) -> None:
        """Add the items to the scene."""
        for item in self._items:
            if item.scene() is None:
                self._scene.addItem(item)

    def undo(self) -> None:
        """Remove the items from the scene."""
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)


class DeleteItemsCommand(Command):
    """Command for deleting one or more items from the scene."""

    def __init__(
        self,
        scene: QGraphicsScene,
        items: list[QGraphicsItem],
    ) -> None:
        """Initialize the delete command.

        Args:
            scene: The scene containing the items
            items: List of items to delete
        """
        self._scene = scene
        self._items = list(items)  # Copy the list

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return "Delete item"
        return f"Delete {count} items"

    def execute(self) -> None:
        """Remove items from the scene."""
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)

    def undo(self) -> None:
        """Restore items to the scene."""
        for item in self._items:
            if item.scene() is None:
                self._scene.addItem(item)


class MoveItemsCommand(Command):
    """Command for moving one or more items."""

    def __init__(
        self,
        items: list[QGraphicsItem],
        delta: QPointF,
    ) -> None:
        """Initialize the move command.

        Args:
            items: List of items to move
            delta: Movement offset (dx, dy)
        """
        self._items = list(items)
        self._delta = delta

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return "Move item"
        return f"Move {count} items"

    def execute(self) -> None:
        """Move items by delta."""
        for item in self._items:
            item.moveBy(self._delta.x(), self._delta.y())

    def undo(self) -> None:
        """Move items back by negative delta."""
        for item in self._items:
            item.moveBy(-self._delta.x(), -self._delta.y())


class ChangePropertyCommand(Command):
    """Command for changing a property on an item."""

    def __init__(
        self,
        item: QGraphicsItem,
        property_name: str,
        old_value,
        new_value,
        apply_func: Callable[[Any, Any], None] | None = None,
    ) -> None:
        """Initialize the change property command.

        Args:
            item: The item to modify
            property_name: Name of the property being changed
            old_value: The previous value
            new_value: The new value
            apply_func: Optional function to apply the change (takes item and value)
        """
        self._item = item
        self._property_name = property_name
        self._old_value = old_value
        self._new_value = new_value
        self._apply_func = apply_func

    @property
    def description(self) -> str:
        """Human-readable description."""
        return f"Change {self._property_name}"

    def execute(self) -> None:
        """Apply the new value."""
        if self._apply_func:
            self._apply_func(self._item, self._new_value)
        elif hasattr(self._item, self._property_name):
            setattr(self._item, self._property_name, self._new_value)

    def undo(self) -> None:
        """Restore the old value."""
        if self._apply_func:
            self._apply_func(self._item, self._old_value)
        elif hasattr(self._item, self._property_name):
            setattr(self._item, self._property_name, self._old_value)
