"""Command pattern implementation for undo/redo functionality.

All modifications to the canvas are wrapped in commands that can be
executed, undone, and redone.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from PyQt6.QtCore import QObject, QPointF, pyqtSignal
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

if TYPE_CHECKING:
    from open_garden_planner.core.constraints import (
        AnchorRef,
        Constraint,
        ConstraintGraph,
        ConstraintType,
    )


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


class ResizeItemCommand(Command):
    """Command for resizing an item.

    Optionally includes partner_resizes for equal-constraint partners so that
    both the primary item and its EQUAL-constrained partners are undone/redone
    together in a single undo step.
    """

    def __init__(
        self,
        item: QGraphicsItem,
        old_geometry: dict[str, Any],
        new_geometry: dict[str, Any],
        apply_func: Callable[[QGraphicsItem, dict[str, Any]], None],
        partner_resizes: "list[tuple] | None" = None,
    ) -> None:
        """Initialize the resize command.

        Args:
            item: The item being resized
            old_geometry: Dictionary containing old geometry data
            new_geometry: Dictionary containing new geometry data
            apply_func: Function to apply geometry to the item
            partner_resizes: Optional list of (partner_item, old_size, new_size, apply_fn)
                for EQUAL-constrained partners that resize together with this item.
        """
        self._item = item
        self._old_geometry = old_geometry
        self._new_geometry = new_geometry
        self._apply_func = apply_func
        self._partner_resizes: list = partner_resizes or []

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Resize item"

    def execute(self) -> None:
        """Apply the new geometry (and partner new sizes)."""
        self._apply_func(self._item, self._new_geometry)
        for p_item, _old_size, new_size, p_apply_fn in self._partner_resizes:
            p_apply_fn(p_item, new_size)

    def undo(self) -> None:
        """Restore the old geometry (and partner old sizes)."""
        self._apply_func(self._item, self._old_geometry)
        for p_item, old_size, _new_size, p_apply_fn in self._partner_resizes:
            p_apply_fn(p_item, old_size)


class RotateItemCommand(Command):
    """Command for rotating an item."""

    def __init__(
        self,
        item: QGraphicsItem,
        old_angle: float,
        new_angle: float,
        apply_func: Callable[[QGraphicsItem, float], None],
    ) -> None:
        """Initialize the rotate command.

        Args:
            item: The item being rotated
            old_angle: Previous rotation angle in degrees
            new_angle: New rotation angle in degrees
            apply_func: Function to apply rotation to the item
        """
        self._item = item
        self._old_angle = old_angle
        self._new_angle = new_angle
        self._apply_func = apply_func

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Rotate item"

    def execute(self) -> None:
        """Apply the new rotation."""
        self._apply_func(self._item, self._new_angle)

    def undo(self) -> None:
        """Restore the old rotation."""
        self._apply_func(self._item, self._old_angle)


class MoveVertexCommand(Command):
    """Command for moving a single vertex in a polygon."""

    def __init__(
        self,
        item: QGraphicsItem,
        vertex_index: int,
        old_pos: QPointF,
        new_pos: QPointF,
        apply_func: Callable[[QGraphicsItem, int, QPointF], None],
    ) -> None:
        """Initialize the move vertex command.

        Args:
            item: The polygon item being modified
            vertex_index: Index of the vertex being moved
            old_pos: Previous position of the vertex
            new_pos: New position of the vertex
            apply_func: Function to apply vertex position to the item
        """
        self._item = item
        self._vertex_index = vertex_index
        self._old_pos = old_pos
        self._new_pos = new_pos
        self._apply_func = apply_func

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Move vertex"

    def execute(self) -> None:
        """Apply the new vertex position."""
        self._apply_func(self._item, self._vertex_index, self._new_pos)

    def undo(self) -> None:
        """Restore the old vertex position."""
        self._apply_func(self._item, self._vertex_index, self._old_pos)


class AddVertexCommand(Command):
    """Command for adding a vertex to a polygon."""

    def __init__(
        self,
        item: QGraphicsItem,
        vertex_index: int,
        position: QPointF,
        apply_add_func: Callable[[QGraphicsItem, int, QPointF], None],
        apply_remove_func: Callable[[QGraphicsItem, int], None],
    ) -> None:
        """Initialize the add vertex command.

        Args:
            item: The polygon item being modified
            vertex_index: Index where the vertex will be inserted
            position: Position of the new vertex
            apply_add_func: Function to add a vertex to the item
            apply_remove_func: Function to remove a vertex from the item
        """
        self._item = item
        self._vertex_index = vertex_index
        self._position = position
        self._apply_add_func = apply_add_func
        self._apply_remove_func = apply_remove_func

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Add vertex"

    def execute(self) -> None:
        """Add the vertex."""
        self._apply_add_func(self._item, self._vertex_index, self._position)

    def undo(self) -> None:
        """Remove the vertex."""
        self._apply_remove_func(self._item, self._vertex_index)


class AlignItemsCommand(Command):
    """Command for aligning/distributing items with per-item deltas.

    Unlike MoveItemsCommand (uniform delta), each item can move a different amount.
    Used by alignment and distribution operations.
    """

    def __init__(
        self,
        item_deltas: list[tuple[QGraphicsItem, QPointF]],
        description_text: str = "Align items",
    ) -> None:
        """Initialize the alignment command.

        Args:
            item_deltas: List of (item, delta) tuples.
            description_text: Human-readable description for undo menu.
        """
        self._item_deltas = list(item_deltas)
        self._description_text = description_text

    @property
    def description(self) -> str:
        """Human-readable description."""
        return self._description_text

    def execute(self) -> None:
        """Move each item by its individual delta."""
        for item, delta in self._item_deltas:
            item.moveBy(delta.x(), delta.y())

    def undo(self) -> None:
        """Move each item back by its individual delta."""
        for item, delta in self._item_deltas:
            item.moveBy(-delta.x(), -delta.y())


class DeleteVertexCommand(Command):
    """Command for deleting a vertex from a polygon."""

    def __init__(
        self,
        item: QGraphicsItem,
        vertex_index: int,
        position: QPointF,
        apply_add_func: Callable[[QGraphicsItem, int, QPointF], None],
        apply_remove_func: Callable[[QGraphicsItem, int], None],
    ) -> None:
        """Initialize the delete vertex command.

        Args:
            item: The polygon item being modified
            vertex_index: Index of the vertex to delete
            position: Position of the vertex (for undo)
            apply_add_func: Function to add a vertex to the item (for undo)
            apply_remove_func: Function to remove a vertex from the item
        """
        self._item = item
        self._vertex_index = vertex_index
        self._position = position
        self._apply_add_func = apply_add_func
        self._apply_remove_func = apply_remove_func

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Delete vertex"

    def execute(self) -> None:
        """Remove the vertex."""
        self._apply_remove_func(self._item, self._vertex_index)

    def undo(self) -> None:
        """Restore the vertex."""
        self._apply_add_func(self._item, self._vertex_index, self._position)


class AddConstraintCommand(Command):
    """Command for adding a constraint (distance, alignment, or angle).

    Optionally includes item position changes computed by running the solver
    after the constraint is added, so that objects immediately snap to satisfy
    the new constraint and the move is bundled into the same undo step.
    Also optionally includes item rotation changes (for PARALLEL constraints).
    """

    def __init__(
        self,
        graph: "ConstraintGraph",
        anchor_a: "AnchorRef",
        anchor_b: "AnchorRef",
        target_distance: float,
        constraint_type: "ConstraintType | None" = None,
        anchor_c: "AnchorRef | None" = None,
        item_moves: "list[tuple[QGraphicsItem, QPointF, QPointF]] | None" = None,
        item_rotations: "list[tuple[QGraphicsItem, float, float, Callable[[QGraphicsItem, float], None]]] | None" = None,
        target_x: float | None = None,
        target_y: float | None = None,
    ) -> None:
        from open_garden_planner.core.constraints import ConstraintType
        self._graph = graph
        self._anchor_a = anchor_a
        self._anchor_b = anchor_b
        self._target_distance = target_distance
        self._constraint_type = constraint_type or ConstraintType.DISTANCE
        self._anchor_c = anchor_c
        self._constraint_id: UUID | None = None
        self._item_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = item_moves or []
        self._item_rotations: list[tuple[QGraphicsItem, float, float, Callable[[QGraphicsItem, float], None]]] = item_rotations or []
        self._target_x = target_x
        self._target_y = target_y

    @property
    def description(self) -> str:
        return "Add constraint"

    def execute(self) -> None:
        c = self._graph.add_constraint(
            self._anchor_a,
            self._anchor_b,
            self._target_distance,
            constraint_id=self._constraint_id,
            constraint_type=self._constraint_type,
            anchor_c=self._anchor_c,
            target_x=self._target_x,
            target_y=self._target_y,
        )
        self._constraint_id = c.constraint_id
        for item, _old, new in self._item_moves:
            item.setPos(new)
        for item, _old_angle, new_angle, apply_func in self._item_rotations:
            apply_func(item, new_angle)

    def undo(self) -> None:
        if self._constraint_id is not None:
            self._graph.remove_constraint(self._constraint_id)
        for item, old, _new in self._item_moves:
            item.setPos(old)
        for item, old_angle, _new_angle, apply_func in self._item_rotations:
            apply_func(item, old_angle)


class RemoveConstraintCommand(Command):
    """Command for removing a distance constraint."""

    def __init__(
        self,
        graph: "ConstraintGraph",
        constraint: "Constraint",
    ) -> None:
        self._graph = graph
        self._constraint = constraint

    @property
    def description(self) -> str:
        return "Remove constraint"

    def execute(self) -> None:
        self._graph.remove_constraint(self._constraint.constraint_id)

    def undo(self) -> None:
        self._graph.add_constraint(
            self._constraint.anchor_a,
            self._constraint.anchor_b,
            self._constraint.target_distance,
            visible=self._constraint.visible,
            constraint_id=self._constraint.constraint_id,
            constraint_type=self._constraint.constraint_type,
            target_x=self._constraint.target_x,
            target_y=self._constraint.target_y,
        )


class LinearArrayCommand(Command):
    """Command for creating a linear array of copies of one item.

    Bundles item creation and optional distance constraints into a
    single undoable step.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        new_items: "list[QGraphicsItem]",
        constraint_pairs: "list[tuple[AnchorRef, AnchorRef, float]] | None" = None,
        graph: "ConstraintGraph | None" = None,
    ) -> None:
        """Initialize the command.

        Args:
            scene: The scene to add items to.
            new_items: The newly created copies (not including the original).
            constraint_pairs: Optional list of (anchor_a, anchor_b, distance)
                tuples for distance constraints between consecutive items.
            graph: The constraint graph (required if constraint_pairs given).
        """
        self._scene = scene
        self._items = list(new_items)
        self._constraint_pairs = constraint_pairs or []
        self._graph = graph
        self._constraint_ids: list[UUID] = []

    @property
    def description(self) -> str:
        return f"Create linear array ({len(self._items) + 1} items)"

    def execute(self) -> None:
        """Add items and constraints to the scene."""
        for item in self._items:
            if item.scene() is None:
                self._scene.addItem(item)
        if self._graph and self._constraint_pairs:
            self._constraint_ids = []
            for anchor_a, anchor_b, dist in self._constraint_pairs:
                c = self._graph.add_constraint(anchor_a, anchor_b, dist)
                self._constraint_ids.append(c.constraint_id)

    def undo(self) -> None:
        """Remove constraints then items from the scene."""
        if self._graph:
            for cid in reversed(self._constraint_ids):
                self._graph.remove_constraint(cid)
        self._constraint_ids = []
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)


class GridArrayCommand(Command):
    """Command for creating a rectangular grid array of copies of one item.

    Bundles item creation and optional distance constraints into a
    single undoable step.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        new_items: "list[QGraphicsItem]",
        constraint_pairs: "list[tuple[AnchorRef, AnchorRef, float]] | None" = None,
        graph: "ConstraintGraph | None" = None,
    ) -> None:
        """Initialize the command.

        Args:
            scene: The scene to add items to.
            new_items: The newly created copies (not including the original).
            constraint_pairs: Optional list of (anchor_a, anchor_b, distance)
                tuples for distance constraints between adjacent items.
            graph: The constraint graph (required if constraint_pairs given).
        """
        self._scene = scene
        self._items = list(new_items)
        self._constraint_pairs = constraint_pairs or []
        self._graph = graph
        self._constraint_ids: list[UUID] = []

    @property
    def description(self) -> str:
        return f"Create grid array ({len(self._items) + 1} items)"

    def execute(self) -> None:
        """Add items and constraints to the scene."""
        for item in self._items:
            if item.scene() is None:
                self._scene.addItem(item)
        if self._graph and self._constraint_pairs:
            self._constraint_ids = []
            for anchor_a, anchor_b, dist in self._constraint_pairs:
                c = self._graph.add_constraint(anchor_a, anchor_b, dist)
                self._constraint_ids.append(c.constraint_id)

    def undo(self) -> None:
        """Remove constraints then items from the scene."""
        if self._graph:
            for cid in reversed(self._constraint_ids):
                self._graph.remove_constraint(cid)
        self._constraint_ids = []
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)


class CircularArrayCommand(Command):
    """Command for creating a circular array of copies of one item.

    Bundles item creation into a single undoable step.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        new_items: "list[QGraphicsItem]",
    ) -> None:
        """Initialize the command.

        Args:
            scene: The scene to add items to.
            new_items: The newly created copies (not including the original).
        """
        self._scene = scene
        self._items = list(new_items)

    @property
    def description(self) -> str:
        return f"Create circular array ({len(self._items) + 1} items)"

    def execute(self) -> None:
        """Add items to the scene."""
        for item in self._items:
            if item.scene() is None:
                self._scene.addItem(item)

    def undo(self) -> None:
        """Remove items from the scene."""
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)


class EditConstraintDistanceCommand(Command):
    """Command for editing a constraint's target distance.

    Optionally includes item position changes computed by running the solver
    after the distance change, so that objects immediately snap to satisfy the
    new constraint (bundled into one undo step).
    """

    def __init__(
        self,
        graph: "ConstraintGraph",
        constraint_id: UUID,
        old_distance: float,
        new_distance: float,
        item_moves: "list[tuple[QGraphicsItem, QPointF, QPointF]] | None" = None,
    ) -> None:
        """Initialize the command.

        Args:
            graph: The constraint graph.
            constraint_id: UUID of the constraint to edit.
            old_distance: Previous target distance.
            new_distance: New target distance.
            item_moves: Optional list of (item, old_pos, new_pos) for any
                items that need to move to satisfy the new distance.
        """
        self._graph = graph
        self._constraint_id = constraint_id
        self._old_distance = old_distance
        self._new_distance = new_distance
        self._item_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = item_moves or []

    @property
    def description(self) -> str:
        return "Edit constraint distance"

    def execute(self) -> None:
        c = self._graph.constraints.get(self._constraint_id)
        if c:
            c.target_distance = self._new_distance
        for item, _old, new in self._item_moves:
            item.setPos(new)

    def undo(self) -> None:
        c = self._graph.constraints.get(self._constraint_id)
        if c:
            c.target_distance = self._old_distance
        for item, old, _new in self._item_moves:
            item.setPos(old)
