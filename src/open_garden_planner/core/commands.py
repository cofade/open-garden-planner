"""Command pattern implementation for undo/redo functionality.

All modifications to the canvas are wrapped in commands that can be
executed, undone, and redone.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager, nullcontext, suppress
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, QObject, QPointF, pyqtSignal
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.core.stacking import STACK_STEP

if TYPE_CHECKING:
    from open_garden_planner.core.constraints import (
        AnchorRef,
        Constraint,
        ConstraintGraph,
        ConstraintType,
    )
    from open_garden_planner.models.layer import Layer


class Command(ABC):
    """Abstract base class for all undoable commands."""

    #: Whether executing or undoing this command can change an item's ground band
    #: (``canvas_scene.on_ground``: its object type, height metadata, or group
    #: membership). ``CanvasScene._restack_ground_changes`` skips its O(items)
    #: scan for a command that says ``False``; a command that can reclassify
    #: anything must leave this True (the default), or a lawn can stay in the
    #: solid band (#592).
    changes_ground_band: bool = True

    #: Whether executing or undoing this command can change which plant-parent CONTAINS
    #: a plant, or move a plant inside/outside one — the geometric half of the stacking
    #: clamp (#629). ``CanvasScene._restack_plant_containment`` skips its O(items) scan
    #: for a command that says ``False``. Adds and deletes are neutral: a plant-parent's
    #: arrival is handled synchronously by ``addItem`` (``_needs_synchronous_z_refresh``),
    #: a new plant already lands on top, and a deletion cannot hide anything. A command
    #: that moves, resizes, rotates, vertex-edits, groups or re-types an item must leave
    #: this True (the default), or a bed grown around a plant leaves it behind the bed.
    changes_containment: bool = True

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
        stack_changed: Emitted whenever the stack mutates via execute/undo/redo
            (but NOT clear). Wire mark_dirty to this so undo/redo dirty the
            document too — command_executed only fires on execute. See issue #209.
    """

    can_undo_changed = pyqtSignal(bool)
    can_redo_changed = pyqtSignal(bool)
    command_executed = pyqtSignal(str)
    stack_changed = pyqtSignal()
    before_history_navigation = pyqtSignal()
    history_navigated = pyqtSignal()

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the command manager."""
        super().__init__(parent)
        self._undo_stack: list[Command] = []
        self._redo_stack: list[Command] = []
        self._preparing_history = False
        self._last_command: Command | None = None

    @property
    def last_command(self) -> Command | None:
        """The command whose execute/undo/redo just emitted ``stack_changed``.

        Set immediately before the signal, so a ``stack_changed`` slot can ask
        what changed (``CanvasScene._restack_ground_changes`` does, #592).
        ``None`` before the first command and after ``clear()``.
        """
        return self._last_command

    def _prepare_history(self) -> bool:
        """Commit active editors before selecting a history entry (#560)."""
        if self._preparing_history:
            return False
        self._preparing_history = True
        try:
            self.before_history_navigation.emit()
        finally:
            self._preparing_history = False
        return True

    def execute(self, command: Command) -> None:
        """Execute a command and add it to the undo stack.

        Clears the redo stack since we've branched off.
        """
        command.execute()
        self._undo_stack.append(command)

        # Clear redo stack on new command
        had_redo = len(self._redo_stack) > 0
        self._redo_stack.clear()

        self._last_command = command
        self.can_undo_changed.emit(True)
        if had_redo:
            self.can_redo_changed.emit(False)
        self.command_executed.emit(command.description)
        self.stack_changed.emit()

    def register_applied(self, command: Command) -> None:
        """Register a command whose effect is already applied, without re-running it.

        For interactive gestures (resize/vertex drags, live property edits) the
        change is applied incrementally during the gesture, so calling
        ``command.execute()`` again would double-apply it. This records the
        command on the undo stack and emits the SAME signals as :meth:`execute`
        — crucially including ``command_executed`` and ``stack_changed`` — so the
        document is marked dirty and panels refresh. The single chokepoint keeps
        every "already applied" call site in sync with :meth:`execute`; do NOT
        hand-roll ``_undo_stack.append`` + signal emits at call sites (issue #209).
        """
        self._undo_stack.append(command)
        had_redo = len(self._redo_stack) > 0
        self._redo_stack.clear()

        self._last_command = command
        self.can_undo_changed.emit(True)
        if had_redo:
            self.can_redo_changed.emit(False)
        self.command_executed.emit(command.description)
        self.stack_changed.emit()

    def undo(self) -> None:
        """Undo the last command."""
        if not self._prepare_history():
            return
        if not self._undo_stack:
            return

        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)

        self._last_command = command
        self.can_undo_changed.emit(len(self._undo_stack) > 0)
        self.can_redo_changed.emit(True)
        self.stack_changed.emit()
        self.history_navigated.emit()  # an explicit history transition (#560)

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self._prepare_history():
            return
        if not self._redo_stack:
            return

        command = self._redo_stack.pop()
        try:
            command.execute()
        except Exception:
            # A command may discover that a mutable precondition changed after
            # it was undone. Keep it redoable when execution is refused.
            self._redo_stack.append(command)
            raise
        self._undo_stack.append(command)

        self._last_command = command
        self.can_undo_changed.emit(True)
        self.can_redo_changed.emit(len(self._redo_stack) > 0)
        self.stack_changed.emit()
        self.history_navigated.emit()  # redo is a history transition too (#560)

    def clear(self) -> None:
        """Clear all undo/redo history."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._last_command = None
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
    def undo_depth(self) -> int:
        """Number of commands on the undo stack (US-D2.7)."""
        return len(self._undo_stack)

    @property
    def redo_depth(self) -> int:
        """Number of commands on the redo stack (US-D2.7)."""
        return len(self._redo_stack)

    @property
    def undo_description(self) -> str | None:
        """Description of the command that would be undone."""
        if self._undo_stack:
            return self._undo_stack[-1].description
        return None

    def peek_undo(self) -> Command | None:
        """Return the top of the undo stack without removing it (#559).

        Panels use this to coalesce a numeric/spin gesture: consecutive
        ``valueChanged`` steps of one spin drag merge into the pending command
        instead of one undo entry per tick. Returns None when empty.
        """
        return self._undo_stack[-1] if self._undo_stack else None

    @property
    def redo_description(self) -> str | None:
        """Description of the command that would be redone."""
        if self._redo_stack:
            return self._redo_stack[-1].description
        return None


def _refresh_z_after_relink(scene: QGraphicsScene, item: QGraphicsItem) -> None:
    """Recompute derived z-values after a parent-child relink (issue #338).

    The scene's per-layer z is *derived* from the normalized stacking order
    (see ``CanvasScene._normalized_layer_order``), which already places a
    plant immediately above its parent bed and a ROOF_RIDGE immediately
    above its owner polygon. So establishing/restoring that link only needs
    a refresh, never an explicit z bump — replaces the old
    ``ensure_z_above_parent`` helper.
    """
    layer_id = getattr(item, "layer_id", None)
    refresh_layer = getattr(scene, "_refresh_layer_z", None)
    if layer_id is not None and callable(refresh_layer):
        refresh_layer(layer_id)
        return
    refresh_all = getattr(scene, "_update_items_z_order", None)
    if callable(refresh_all):
        refresh_all()


def _bulk_add_scope(scene: QGraphicsScene) -> AbstractContextManager[None]:
    """Context manager suspending the scene's per-add z-refresh across a
    batch of ``scene.addItem(...)`` calls (issue #338 performance finding).

    Every command that re-adds several items on ``execute``/``undo``
    (``CreateItemsCommand``, ``DeleteItemsCommand.undo``,
    ``MirrorItemsCommand``, ...) must wrap its add loop in this instead of
    letting each ``addItem`` trigger its own full per-layer z recompute —
    that turns an O(n) bulk add into O(n^2) on a large scene. Falls back to
    a no-op for scene doubles (tests) that don't implement
    ``CanvasScene.suspend_z_refresh``.
    """
    suspend = getattr(scene, "suspend_z_refresh", None)
    if callable(suspend):
        return suspend()
    return nullcontext()


def trigger_soil_mismatch_refresh(scene: QGraphicsScene) -> None:
    """Force the canvas view to recompute soil-mismatch borders now.

    QGraphicsScene.changed only fires on geometry/visibility changes, not on
    Python attribute mutations like ``parent_bed_id`` or ``_child_item_ids``.
    Any code path that mutates those attributes must call this helper, or the
    debounced refresh in ``CanvasView`` will never see the change. (Issue #173.)
    """
    for view in scene.views():
        refresh = getattr(view, "refresh_soil_mismatches", None)
        if callable(refresh):
            refresh()


def _auto_parent_plant(scene: QGraphicsScene, item: QGraphicsItem) -> None:
    """If *item* is a plant, point its bed link at the bed its centre is in."""
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    if not isinstance(item, GardenItemMixin):
        return
    if not is_plant_type(item.object_type):
        return
    set_parent_link(scene, item, plant_membership_target(scene, item))


def scene_plants(scene: QGraphicsScene) -> list[QGraphicsItem]:
    """Every plant in *scene* — the only items that carry a bed link.

    A defensive ``TypeError`` catch: command doubles in unit tests answer
    ``items()`` with a non-iterable. A real scene always yields items.
    """
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    try:
        items = list(scene.items())
    except TypeError:  # a command/scene double, not a real QGraphicsScene
        return []
    return [
        item
        for item in items
        if isinstance(item, GardenItemMixin) and is_plant_type(item.object_type)
    ]


def plant_membership_target(
    scene: QGraphicsScene, item: QGraphicsItem
) -> UUID | None:
    """The plant-parent whose shape contains *item*'s link point, else None.

    One predicate, one point: ``find_smallest_bed_containing`` over
    ``footprints.bed_membership_point``. That point is the plant's stable
    geometric centre (issue #443 (iii)), so link decisions and the L1 lift
    (``item_base_cm``) can no longer disagree about which plants a bed holds.
    """
    from open_garden_planner.ui.canvas.footprints import bed_membership_point
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    find = getattr(scene, "find_smallest_bed_containing", None)
    if not callable(find):
        return None
    best_bed = find(bed_membership_point(item))
    if isinstance(best_bed, GardenItemMixin):
        return best_bed.item_id
    return None


def set_parent_link(
    scene: QGraphicsScene,
    item: QGraphicsItem,
    parent_id: UUID | None,
    *,
    refresh_soil: bool = True,
) -> bool:
    """Set *item*'s parent bed, keeping BOTH sides of the link in step.

    The ONE geometry-driven mutator for the plant→bed relationship (issue #443):
    every edit path — creation, a move, a bed edit, a copy, the panel's Link
    action, the agent — calls it, so ``parent_bed_id``
    and the parent's ``child_item_ids`` cannot drift apart. (A few deliberate
    writers remain outside it and set the id directly: the loader's
    ``_relink_parent_child_relationships`` and ``_deserialize_item``, delete
    snapshots/restores, paste/duplicate's remap, and the mirror tool's
    ``_remap_parent_links`` / ``_stamp_identity``.) Returns whether anything
    changed. This docstring is the authoritative direct-writer list; prose
    elsewhere points here.
    """
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    if not isinstance(item, GardenItemMixin):
        return False
    current = item.parent_bed_id
    if current == parent_id:
        # A stale state can carry the right id with a child list that never got
        # it (an array copy restored its source's link; a pre-#443 file). Heal
        # that instead of treating the link as done.
        finder = getattr(scene, "find_item_by_id", None)
        if parent_id is not None and callable(finder):
            parent = finder(parent_id)
            if isinstance(parent, GardenItemMixin) and item.item_id not in parent.child_item_ids:
                parent.add_child_id(item.item_id)
                _refresh_z_after_relink(scene, item)
                if refresh_soil:
                    trigger_soil_mismatch_refresh(scene)
                return True
        return False

    finder = getattr(scene, "find_item_by_id", None)
    if current is not None and callable(finder):
        old_parent = finder(current)
        if isinstance(old_parent, GardenItemMixin):
            old_parent.remove_child_id(item.item_id)
    if parent_id is not None and callable(finder):
        new_parent = finder(parent_id)
        if isinstance(new_parent, GardenItemMixin):
            new_parent.add_child_id(item.item_id)
    item.parent_bed_id = parent_id
    _refresh_z_after_relink(scene, item)
    if refresh_soil:
        trigger_soil_mismatch_refresh(scene)
    return True


def _detach_from_parent(scene: QGraphicsScene, item: QGraphicsItem) -> None:
    """Remove the parent-child link for *item* (if any)."""
    set_parent_link(scene, item, None)


class BedMembershipChange:
    """Re-derive plant→bed links from geometry, with exact undo data.

    Issue #443: the link is bookkeeping that several edit paths never
    reconciled. One rule replaces the per-path guesses — a plant's link is the
    smallest plant-parent that contains its standing point — applied by the
    move/resize/rotate/vertex/copy commands themselves. ``before`` is captured
    when the tracker is built (links are never touched by a geometry change),
    so ``restore`` replays the recorded ids instead of re-solving.

    ``focus_parents`` scopes a BED edit: only plants that link to the edited
    parent, that are linked to it, or that are explicitly moved with it are
    re-decided. A bed edit elsewhere must not overrule a plant's deliberate
    link to a different bed (ADR-037 addendum decision 5).
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        plants: "Sequence[Any] | None" = None,
        *,
        focus_parents: "set[UUID] | None" = None,
    ) -> None:
        self._scene = scene
        self._focus: set[UUID] = set(focus_parents or ())
        self._always: set[QGraphicsItem] = set(plants or ())
        if plants is not None:
            self._plants = list(plants)
        else:
            self._plants = scene_plants(scene)
        if self._focus:
            # A focus edit also has to see plants it does not move yet.
            known = {id(plant) for plant in self._plants}
            self._plants.extend(
                plant for plant in scene_plants(scene) if id(plant) not in known
            )
        self._before: dict[Any, UUID | None] = {
            plant: plant.parent_bed_id
            for plant in self._plants
        }
        self.changed = False

    def _affects(self, plant: QGraphicsItem, target: UUID | None) -> bool:
        """Whether this edit may re-decide *plant*'s link (#443 (a)/(b))."""
        if not self._focus:
            return True
        return (
            plant in self._always
            or target in self._focus
            or self._before.get(plant) in self._focus
        )

    def reconcile(self) -> bool:
        """Point the affected plants at the bed their CURRENT position asks for."""
        targets = {
            plant: plant_membership_target(self._scene, plant)
            for plant in self._plants
        }
        moved = False
        for plant, target in targets.items():
            if not self._affects(plant, target):
                continue
            if plant.scene() is not self._scene:
                continue
            if set_parent_link(self._scene, plant, target, refresh_soil=False):
                moved = True
        if moved:
            trigger_soil_mismatch_refresh(self._scene)
        self.changed = self.changed or moved
        return moved

    def restore(self) -> None:
        """Restore every tracked plant's pre-change link (undo).

        This is safe because undo is strictly LIFO: every command's ``before``
        is its own pre-execute state, so no other command's edit can be older
        than it. Deliberately not limited to the plants ``reconcile`` changed: a
        Mirror-Move replaces the plant OBJECT while reusing its id, so the
        object that carries the new link is not the one restored here — the
        re-added original must get its parent's child id back (and the heal path
        does exactly that).
        """
        moved = False
        for plant, old_parent in self._before.items():
            if plant.scene() is self._scene and set_parent_link(
                self._scene, plant, old_parent, refresh_soil=False
            ):
                moved = True
        if moved:
            trigger_soil_mismatch_refresh(self._scene)


class ReconcileBedMembershipCommand(Command):
    """One undoable step that re-derives plant→bed links from geometry.

    Used where a command was already applied live (a finished drag) and the
    link changes must ride in the SAME undo entry as the geometry
    (``register_applied_with_membership``).
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        plants: "Sequence[Any] | None" = None,
        *,
        focus_parents: "set[UUID] | None" = None,
    ) -> None:
        self._change = BedMembershipChange(
            scene, plants, focus_parents=focus_parents
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Re-link plants to beds")

    @property
    def changed(self) -> bool:
        """Whether the last ``execute`` actually moved a link."""
        return self._change.changed

    def execute(self) -> None:
        self._change.reconcile()

    def undo(self) -> None:
        self._change.restore()


def command_is(
    command: Command,
    types: tuple[type, ...],
) -> bool:
    """Whether *command* — or any step of a ``CompoundCommand`` it wraps — is one of *types*.

    ``_finalize_drag_move`` uses this to keep a live-applied geometry edit from
    also being recorded as a move. A bed edit that re-linked plants is now one
    compound (issue #443), so the plain ``isinstance`` check would miss it and
    add a duplicate position step.
    """
    stack: list[Command] = [command]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, types):
            return True
        stack.extend(getattr(current, "commands", ()))
    return False


def register_applied_with_membership(
    scene: QGraphicsScene,
    command_manager: CommandManager,
    command: Command,
    item: Any,
) -> None:
    """Register a live-applied geometry command WITH its membership corrections.

    The drag-release paths (resize, corner edit, vertex edit) apply geometry
    directly and then register one command. For a bed edit those same gestures
    change which plants the bed holds, and issue #443 requires that to undo in
    the same step: the reconciled links are one ``CompoundCommand`` with the
    geometry. When nothing about membership changed — every non-bed edit — the
    command is registered untouched, so its type stays visible to callers that
    inspect the stack (``_finalize_drag_move``).

    ``item`` is the edited item: only a plant or a plant-parent edit can move a
    link. A fence or building edit therefore leaves explicitly linked plants
    completely alone.
    """
    notify = getattr(command, "notify_applied", None)
    if callable(notify):
        # The command carries its own tracker and undoes the link with the
        # geometry — one stack entry, no wrapper.
        notify()
        command_manager.register_applied(command)
        return

    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    affects_membership = isinstance(item, GardenItemMixin) and (
        is_plant_parent_type(item.object_type) or is_plant_type(item.object_type)
    )
    if not affects_membership:
        command_manager.register_applied(command)
        return

    if is_plant_parent_type(item.object_type):
        reconcile = ReconcileBedMembershipCommand(
            scene, focus_parents={item.item_id}
        )
    else:
        reconcile = ReconcileBedMembershipCommand(scene, [item])
    reconcile.execute()
    if reconcile.changed:
        command_manager.register_applied(CompoundCommand([command, reconcile]))
    else:
        command_manager.register_applied(command)


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
        # Link bookkeeping for #443: a newly drawn BED can change the link of
        # plants that were already standing inside it, and a new PLANT must be
        # linked to the bed it lands in. Captured before the item is added.
        self._membership: BedMembershipChange | None = None

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Create {item_type}").format(
            item_type=self._item_type
        )

    def _membership_change(self) -> BedMembershipChange | None:
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not isinstance(self._item, GardenItemMixin):
            return None
        if is_plant_parent_type(self._item.object_type):
            return BedMembershipChange(
                self._scene,
                focus_parents={self._item.item_id},
            )
        if is_plant_type(self._item.object_type):
            return BedMembershipChange(self._scene, [self._item])
        return None

    def execute(self) -> None:
        """Add the item to the scene and reconcile the links its geometry decides."""
        if self._item.scene() is None:
            if self._membership is None:
                self._membership = self._membership_change()
            self._scene.addItem(self._item)
        if self._membership is not None:
            self._membership.reconcile()
        else:
            _auto_parent_plant(self._scene, self._item)

    def undo(self) -> None:
        """Remove the item from the scene and restore the links it displaced."""
        _detach_from_parent(self._scene, self._item)
        if self._item.scene() is not None:
            self._scene.removeItem(self._item)
        if self._membership is not None:
            self._membership.restore()


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
        # See CreateItemCommand: pasting/duplicating a bed can re-link plants
        # that already stood where the copy lands (#443).
        self._membership: BedMembershipChange | None = None

    def _membership_change(self) -> BedMembershipChange | None:
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        created_plants: list[QGraphicsItem] = [
            item
            for item in self._items
            if isinstance(item, GardenItemMixin) and is_plant_type(item.object_type)
        ]
        creates_parent = any(
            isinstance(item, GardenItemMixin)
            and is_plant_parent_type(item.object_type)
            for item in self._items
        )
        if creates_parent:
            parents = {
                item.item_id
                for item in self._items
                if isinstance(item, GardenItemMixin)
                and is_plant_parent_type(item.object_type)
            }
            return BedMembershipChange(
                self._scene,
                created_plants,
                focus_parents=parents,
            )
        if created_plants:
            return BedMembershipChange(self._scene, created_plants)
        return None

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return QCoreApplication.translate("Commands", "Create {item_type}").format(
                item_type=self._item_type
            )
        return QCoreApplication.translate("Commands", "Create {count} {item_type}").format(
            count=count, item_type=self._item_type
        )

    def execute(self) -> None:
        """Add the items to the scene and reconcile every link the copy affects."""
        if self._membership is None:
            self._membership = self._membership_change()
        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._membership is not None:
            self._membership.reconcile()
        else:
            for item in self._items:
                _auto_parent_plant(self._scene, item)

    def undo(self) -> None:
        """Remove the items and restore the links they displaced."""
        for item in self._items:
            _detach_from_parent(self._scene, item)
        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)
        if self._membership is not None:
            self._membership.restore()


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
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        self._scene = scene
        self._items = list(items)  # Copy the list

        # Snapshot parent-child relationships for undo restoration.
        # bed UUID → list of child UUIDs
        self._bed_children: dict[UUID, list[UUID]] = {}
        # plant UUID → parent bed UUID
        self._plant_parents: dict[UUID, UUID] = {}
        for item in self._items:
            if not isinstance(item, GardenItemMixin):
                continue
            if item.has_children:
                self._bed_children[item.item_id] = list(item._child_item_ids)
            if item.parent_bed_id is not None:
                self._plant_parents[item.item_id] = item.parent_bed_id

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return QCoreApplication.translate("Commands", "Delete item")
        return QCoreApplication.translate("Commands", "Delete {count} items").format(
            count=count
        )

    def execute(self) -> None:
        """Remove items from the scene."""
        from open_garden_planner.core.guild_commands import GuildMembershipCommand, guild_members
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        if not hasattr(self, "_guild_dissolution"):
            changes: dict[Any, dict[str, Any] | None] = {}
            removed = set(self._items)
            pending = list(self._items)
            while pending:
                parent = pending.pop()
                for child in parent.childItems():
                    if hasattr(child, "metadata") and child not in removed:
                        removed.add(child)
                        pending.append(child)
            for deleted in removed:
                guild = getattr(deleted, "metadata", {}).get("guild")
                if isinstance(guild, dict) and guild.get("role") == "centre":
                    for survivor in guild_members(self._scene, guild.get("guild_id", "")):
                        if survivor not in removed:
                            changes[survivor] = None
            self._guild_dissolution = GuildMembershipCommand(list(changes.items()))
        self._guild_dissolution.execute()

        # Detach parent-child links before removing items
        for item in self._items:
            _detach_from_parent(self._scene, item)

        # Detach surviving children of beds being deleted
        deleted_ids = {
            item.item_id for item in self._items if isinstance(item, GardenItemMixin)
        }
        for item in self._items:
            if not isinstance(item, GardenItemMixin):
                continue
            if item.item_id not in self._bed_children:
                continue
            for child_id in self._bed_children[item.item_id]:
                if child_id in deleted_ids:
                    continue  # child is also being deleted
                if hasattr(self._scene, "find_item_by_id"):
                    child = self._scene.find_item_by_id(child_id)
                    if child is not None and isinstance(child, GardenItemMixin):
                        child.parent_bed_id = None
            item._child_item_ids.clear()

        for item in self._items:
            if item.scene() is not None:
                self._scene.removeItem(item)

    def undo(self) -> None:
        """Restore items to the scene."""
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        self._guild_dissolution.undo()

        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        # Restore parent-child relationships from snapshot
        for item in self._items:
            if not isinstance(item, GardenItemMixin):
                continue
            iid = item.item_id
            if iid in self._bed_children:
                item._child_item_ids = list(self._bed_children[iid])
                # Also restore parent_bed_id on surviving children
                for child_id in self._bed_children[iid]:
                    if hasattr(self._scene, "find_item_by_id"):
                        child = self._scene.find_item_by_id(child_id)
                        if child is not None and isinstance(child, GardenItemMixin):
                            child.parent_bed_id = iid
            if iid in self._plant_parents:
                item.parent_bed_id = self._plant_parents[iid]
                # Also re-add to parent's child list (if parent is in scene)
                if hasattr(self._scene, "find_item_by_id"):
                    parent = self._scene.find_item_by_id(self._plant_parents[iid])
                    if parent is not None and isinstance(parent, GardenItemMixin):
                        parent.add_child_id(iid)
        # Ranks were preserved across remove/re-add, but a restored item's
        # derived z (relative to its parent) needs recomputing regardless of
        # which branch above restored the link. Gating this on a "did a bed
        # child get relinked" flag (as an earlier revision did) missed the
        # `_plant_parents` branch entirely: undoing the deletion of a PLANT
        # restores `parent_bed_id` there with no bed-side child link touched,
        # so the flag never fired and the plant's z stayed stale below its
        # bed (issue #338 review round 3, P0). One O(n) refresh on an undo
        # is cheap, so just always run it whenever anything was restored.
        if self._items:
            refresh_all = getattr(self._scene, "_update_items_z_order", None)
            if callable(refresh_all):
                refresh_all()


def _membership_change_for_move(
    scene: QGraphicsScene | None,
    items: list[QGraphicsItem],
) -> BedMembershipChange | None:
    """The plants whose bed link a move can change, or None when none can.

    A moved PLANT may enter or leave a bed. A moved plant-PARENT may change
    the link of plants that did not move (a bed drawn/moved over them), so
    every plant is tracked then. Anything else leaves membership untouched.
    """
    if scene is None:
        return None
    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    parents = [
        item
        for item in items
        if isinstance(item, GardenItemMixin) and is_plant_parent_type(item.object_type)
    ]
    plants: list[QGraphicsItem] = [
        item
        for item in items
        if isinstance(item, GardenItemMixin) and is_plant_type(item.object_type)
    ]
    if parents:
        # The moved plants are ALWAYS re-decided (a moved plant's link follows
        # it); the focus only widens the set to plants the moved beds can affect.
        return BedMembershipChange(
            scene,
            plants,
            focus_parents={item.item_id for item in parents},
        )
    if not plants:
        return None
    return BedMembershipChange(scene, plants)


def _membership_for_added_items(
    scene: QGraphicsScene,
    items: list[QGraphicsItem],
    *,
    clear_inherited: bool,
) -> BedMembershipChange | None:
    """Link tracker for items that are about to be added as copies.

    ``clear_inherited`` drops a link the copy was serialised with: a copy is a
    NEW item, and issue #443 (v) gives it one rule — geometry decides, exactly
    as ``CreateItemsCommand`` already does for a pasted plant. Without this an
    array copy stayed linked to the source's bed wherever it landed, while the
    bed's child list did not hold it.
    """
    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    plants: list[QGraphicsItem] = []
    adds_parent = False
    # Copies are not in the scene yet, so a copied bed cannot be found through
    # the scene when its plant's inherited link is dropped.
    by_id = {
        item.item_id: item
        for item in items
        if isinstance(item, GardenItemMixin)
    }
    for item in items:
        if not isinstance(item, GardenItemMixin):
            continue
        if is_plant_parent_type(item.object_type):
            adds_parent = True
        elif is_plant_type(item.object_type):
            # A copy of a PLANT is a new plant: its source's link must not ride
            # along. Non-plant children keep a deliberate remap (the mirror
            # tool re-parents a copied bed's children onto the copy).
            if clear_inherited and item.parent_bed_id is not None:
                copied_parent = by_id.get(item.parent_bed_id)
                if isinstance(copied_parent, GardenItemMixin):
                    copied_parent.remove_child_id(item.item_id)
                set_parent_link(scene, item, None, refresh_soil=False)
            plants.append(item)
    if adds_parent:
        # A new bed can change the link of plants that did not move — but only
        # the plants that link to it, not a deliberate link to another bed.
        parents = [
            item.item_id
            for item in items
            if isinstance(item, GardenItemMixin)
            and is_plant_parent_type(item.object_type)
        ]
        return BedMembershipChange(
            scene, plants, focus_parents=set(parents)
        )
    if plants:
        return BedMembershipChange(scene, plants)
    return None


def _membership_change_for_geometry(
    scene: QGraphicsScene | None,
    item: QGraphicsItem,
    partner_items: "list[QGraphicsItem] | tuple[QGraphicsItem, ...]" = (),
) -> BedMembershipChange | None:
    """Link tracker for a resize/rotate of *item* (and any partner it corrects).

    A bed's boundary edit re-decides only the plants that link to it (see
    ``BedMembershipChange.focus_parents``); a plant's own geometry change can
    only move its own link (and usually does not even do that — its centre is
    invariant). ``partner_items`` are the constraint-corrected items a rotation
    moved: a partner PLANT may enter or leave a bed, and a partner BED takes its
    own plants with it, so both are tracked. Any other shape leaves membership
    alone, so explicitly linked plants are never overruled by an unrelated edit.
    """
    if scene is None:
        return None
    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.core.plant_renderer import is_plant_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    candidates = [item, *partner_items]
    parents = [
        candidate
        for candidate in candidates
        if isinstance(candidate, GardenItemMixin)
        and is_plant_parent_type(candidate.object_type)
    ]
    plants = [
        candidate
        for candidate in candidates
        if isinstance(candidate, GardenItemMixin)
        and is_plant_type(candidate.object_type)
    ]
    if parents:
        return BedMembershipChange(
            scene,
            plants,
            focus_parents={
                parent.item_id for parent in parents
            },
        )
    if plants:
        return BedMembershipChange(scene, plants)
    return None


def bed_child_has_constraints(scene: QGraphicsScene, child_id: UUID) -> bool:
    """Whether a linked plant has its own placement constraints.

    Automatic bed carrying applies only to unconstrained children. A plant's
    FIXED or other constraint must take priority over this implicit movement;
    solver-controlled children keep their solver result, including zero delta.
    """
    graph = getattr(scene, "constraint_graph", None)
    return graph is not None and bool(graph.get_item_constraints(child_id))


def expand_with_bed_children(
    scene: QGraphicsScene,
    item_deltas: list[tuple[QGraphicsItem, QPointF]],
) -> list[tuple[QGraphicsItem, QPointF]]:
    """Add each moved plant-parent's plants, carrying the parent's delta.

    Issue #443 (vi): a bed moved by a typed coordinate or by align/distribute
    left its plants behind, unlike the drag, arrow-key and agent paths. A plant
    that is itself in ``item_deltas`` keeps its own delta — the user moved it.
    """
    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    result = list(item_deltas)
    moved = {item for item, _delta in result}
    finder = getattr(scene, "find_item_by_id", None)
    if not callable(finder):
        return result
    for item, delta in list(item_deltas):
        if not isinstance(item, GardenItemMixin):
            continue
        if not is_plant_parent_type(item.object_type):
            continue
        for child_id in item.child_item_ids:
            child = finder(child_id)
            if child is None or child in moved or bed_child_has_constraints(scene, child_id):
                continue
            moved.add(child)
            result.append((child, QPointF(delta)))
    return result


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
        scene = self._items[0].scene() if self._items else None
        if scene is not None:
            # One rule: a moved bed takes its plants along (#443 (vi) — the typed
            # coordinate and align/distribute used to leave them behind).
            self._items = [
                moved
                for moved, _carried in expand_with_bed_children(
                    scene, [(item, delta) for item in self._items]
                )
            ]
        self._membership = _membership_change_for_move(scene, self._items)

    @property
    def description(self) -> str:
        """Human-readable description."""
        count = len(self._items)
        if count == 1:
            return QCoreApplication.translate("Commands", "Move item")
        return QCoreApplication.translate("Commands", "Move {count} items").format(
            count=count
        )

    def execute(self) -> None:
        """Move items by delta, then re-derive their bed links from where they are."""
        for item in self._items:
            item.moveBy(self._delta.x(), self._delta.y())
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Restore the bed links, then move items back by negative delta."""
        if self._membership is not None:
            self._membership.restore()
        for item in self._items:
            item.moveBy(-self._delta.x(), -self._delta.y())



class CompoundCommand(Command):
    """Several commands that undo as ONE step.

    The case it exists for: a plant dragged into a bed is moved AND linked, and
    the link is decided after the move (positions, then containment). Two stack
    entries made the first Ctrl+Z undo only the link and the second the move, so
    the drag looked half-undoable (#627's manual pass). The commands run in
    order here and undo in reverse, so one undo puts the plant back where it was
    WITH its old parent.

    ``description``: the step's own name; the first command's when omitted.
    ``execute`` undoes the commands that RETURNED if a later one raises - a step
    with no half-left work and no stack entry. (A command that raises in the middle
    of its own mutations is that command's contract to keep clean, as before.)
    """

    def __init__(self, commands: Sequence[Command], description: str | None = None) -> None:
        # a tuple: the two flags below are computed once, so the set of commands they
        # describe must not be able to change afterwards
        self._commands = tuple(commands)
        if not self._commands:
            raise ValueError("CompoundCommand needs at least one command")
        self._description = description
        # the scene's restack scans ask these of the ONE command it ran: a step that
        # can move, link or re-type anything must keep asking for them
        self.changes_ground_band = any(command.changes_ground_band for command in self._commands)
        self.changes_containment = any(command.changes_containment for command in self._commands)

    @property
    def description(self) -> str:
        return self._description or self._commands[0].description

    @property
    def commands(self) -> tuple[Command, ...]:
        """The steps this compound runs, in order — read-only.

        Exposed for callers that must recognise a step by what it CONTAINS
        (``command_is``): a bed edit that also re-linked plants is one
        ``CompoundCommand`` whose first step is still the resize/rotate.
        """
        return self._commands

    def execute(self) -> None:
        done: list[Command] = []
        try:
            for command in self._commands:
                command.execute()
                done.append(command)
        except Exception:
            for command in reversed(done):
                command.undo()
            raise

    def undo(self) -> None:
        for command in reversed(self._commands):
            command.undo()


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
        """Human-readable description.

        The property fragment is itself translated under the "Commands" context
        (registered in scripts/fill_translations.py) so the whole label localizes
        — e.g. "Textinhalt ändern" rather than the half-English "text content
        ändern". An unregistered fragment falls through to its English source.
        """
        prop = QCoreApplication.translate("Commands", self._property_name)
        return QCoreApplication.translate("Commands", "Change {property}").format(
            property=prop
        )

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


class ApplySpeciesCommand(Command):
    """Command for assigning a database species to an existing plant item.

    Captures the ``metadata['plant_species']`` dict, the user's
    ``spacing_radius_cm`` override, and the drawn footprint radius so assigning a
    species is a single, undoable step. When the user opts to apply database
    values the footprint is resized so its diameter equals the species'
    ``max_spread_cm`` and the spacing override is cleared; execute/undo restore
    all three and force a repaint. See issue #213.
    """

    def __init__(
        self,
        item: QGraphicsItem,
        old_species: dict[str, Any] | None,
        new_species: dict[str, Any] | None,
        old_spacing_override: float | None,
        new_spacing_override: float | None,
        old_radius: float | None = None,
        new_radius: float | None = None,
        *,
        old_species_name: str,
        new_species_name: str,
    ) -> None:
        """Initialize the apply-species command.

        Args:
            item: The plant item to modify (must expose ``metadata`` and
                ``spacing_radius_cm``).
            old_species: Previous ``metadata['plant_species']`` dict (or None).
            new_species: Species dict to assign.
            old_spacing_override: Previous ``spacing_radius_cm`` value.
            new_spacing_override: ``spacing_radius_cm`` value after applying.
            old_radius: Previous footprint radius (cm), or None to leave the
                footprint untouched.
            new_radius: Footprint radius (cm) after applying, or None to leave
                the footprint untouched.
            old_species_name: The item's own species STRING before the
                assignment — what the sprite resolver reads (#445) — and
                new_species_name the string after it. **Required, keyword-only:**
                a command that carries a species but no name would assign the
                data and leave the plant drawn as it was, which is the very
                defect #445 is about.
        """
        self._item = item
        # Defensive copies so later mutations of the source dicts can't alias
        # the undo state.
        self._old_species = deepcopy(old_species)
        self._new_species = deepcopy(new_species)
        self._old_spacing_override = old_spacing_override
        self._new_spacing_override = new_spacing_override
        self._old_radius = old_radius
        self._new_radius = new_radius
        self._old_species_name = old_species_name
        self._new_species_name = new_species_name

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Apply species data")

    def _apply(
        self,
        species: dict[str, Any] | None,
        spacing_override: float | None,
        radius: float | None,
        species_name: str,
    ) -> None:
        # ``metadata`` is a read-only property returning the item's live dict, so
        # mutate it in place (a plant item always has one; a non-plant item would
        # — correctly — raise rather than silently no-op).
        metadata = self._item.metadata  # type: ignore[attr-defined]
        if species is None:
            metadata.pop("plant_species", None)
        else:
            metadata["plant_species"] = dict(species)
        # The item's own species STRING is what the sprite resolver reads, so
        # the assignment has to write it too (#445): without it the plant keeps
        # the sprite it was drawn with, in 2D and in 3D alike. The setter
        # triggers prepareGeometryChange()/update(); set it last so the
        # spacing circle repaints with the new metadata in place.
        if hasattr(self._item, "plant_species"):
            # The assignment, not setattr: mypy narrows the item after the
            # hasattr above, so the setter is reached without an ignore, and the
            # setter is what repaints the item. A non-plant has no such
            # attribute, and must not grow one.
            self._item.plant_species = species_name
        self._item.spacing_radius_cm = spacing_override  # type: ignore[attr-defined]
        # Resize the drawn footprint so it reflects the species' real size
        # (no-op when radius is None or unchanged).
        if radius is not None and hasattr(self._item, "set_radius_centered"):
            self._item.set_radius_centered(radius)

    def execute(self) -> None:
        """Apply the new species + spacing override + footprint radius."""
        self._apply(self._new_species, self._new_spacing_override, self._new_radius,
                    self._new_species_name)

    def undo(self) -> None:
        """Restore the previous species + spacing override + footprint radius."""
        self._apply(self._old_species, self._old_spacing_override, self._old_radius,
                    self._old_species_name)


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
        self._membership = _membership_change_for_geometry(
            item.scene(),
            item,
            [
                partner
                for partner, _old_size, _new_size, _apply_fn in self._partner_resizes
            ],
        )

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Resize item")

    def notify_applied(self) -> None:
        """Reconcile bed membership for a resize that was already applied live."""
        if self._membership is not None:
            self._membership.reconcile()

    def execute(self) -> None:
        """Apply the new geometry (and partner new sizes), then the new links."""
        self._apply_func(self._item, self._new_geometry)
        for p_item, _old_size, new_size, p_apply_fn in self._partner_resizes:
            p_apply_fn(p_item, new_size)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Restore the old links, geometry (and partner old sizes)."""
        if self._membership is not None:
            self._membership.restore()
        self._apply_func(self._item, self._old_geometry)
        for p_item, old_size, _new_size, p_apply_fn in self._partner_resizes:
            p_apply_fn(p_item, old_size)


class RotateItemCommand(Command):
    """Command for rotating an item, with any partner corrections it caused.

    Issue #485: a rotation gesture can change the scene position of an anchor
    (a corner of a rotated rectangle moves). For a DISTANCE constraint the
    partner must follow, and every follow-up correction must be part of the
    SAME undo entry, or undoing the gesture leaves the relation broken and a
    later nudge's undo resurrects the violation. ``partner_moves`` records each
    affected item's pre-gesture and post-gesture position, so execute/redo and
    undo replay the angle and the corrections atomically.
    """

    def __init__(
        self,
        item: QGraphicsItem,
        old_angle: float,
        new_angle: float,
        apply_func: Callable[[QGraphicsItem, float], None],
        partner_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] | None = None,
        partner_vertex_moves: "list[tuple[QGraphicsItem, int, QPointF, QPointF]] | None" = None,
    ) -> None:
        """Initialize the rotate command.

        Args:
            item: The item being rotated
            old_angle: Previous rotation angle in degrees
            new_angle: New rotation angle in degrees
            apply_func: Function to apply rotation to the item
            partner_moves: Items the solver corrected, as
                ``(item, position_before, position_after)`` — recorded, not
                recomputed, so undo restores the exact pre-gesture geometry.
            partner_vertex_moves: Deformable partners' corrected vertices, as
                ``(item, vertex_index, local_before, local_after)`` — the solver's
                vertex-level corrections, recorded the same way.
        """
        self._item = item
        self._old_angle = old_angle
        self._new_angle = new_angle
        self._apply_func = apply_func
        self._partner_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = [
            (moved_item, QPointF(before), QPointF(after))
            for moved_item, before, after in (partner_moves or [])
        ]
        self._partner_vertex_moves: list[
            tuple[QGraphicsItem, int, QPointF, QPointF]
        ] = [
            (moved_item, index, QPointF(before), QPointF(after))
            for moved_item, index, before, after in (partner_vertex_moves or [])
        ]
        self._membership = _membership_change_for_geometry(
            item.scene(),
            item,
            [moved_item for moved_item, _before, _after in self._partner_moves]
            + [
                moved_item
                for moved_item, _index, _before, _after in self._partner_vertex_moves
            ],
        )

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Rotate item")

    def notify_applied(self) -> None:
        """Reconcile bed membership for a rotation that was already applied live."""
        if self._membership is not None:
            self._membership.reconcile()

    def execute(self) -> None:
        """Apply the new rotation, every partner correction and the new links."""
        self._apply_func(self._item, self._new_angle)
        for moved_item, _before, after in self._partner_moves:
            moved_item.setPos(after)
        for moved_item, index, _before, after in self._partner_vertex_moves:
            if hasattr(moved_item, "_move_vertex_to"):
                moved_item._move_vertex_to(index, after)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Restore the old rotation, every partner's pre-gesture position and links."""
        if self._membership is not None:
            self._membership.restore()
        for moved_item, index, before, _after in reversed(self._partner_vertex_moves):
            if hasattr(moved_item, "_move_vertex_to"):
                moved_item._move_vertex_to(index, before)
        for moved_item, before, _after in reversed(self._partner_moves):
            moved_item.setPos(before)
        self._apply_func(self._item, self._old_angle)


class PlantSpeciesEditCommand(Command):
    """One committed Plant Details species edit as a single undo step (#559).

    Captures the ``metadata['plant_species']`` dict, the user's
    ``spacing_radius_cm`` override, and the drawn footprint radius so a
    species-field edit — including a Max Spread change that resizes the
    footprint (#558) — undoes/redoes together. Library writes
    (``update_plant``/``add_plant``) are explicitly NOT part of undo: they
    are shared-library side effects, documented in the panel.
    """

    def __init__(
        self,
        item: QGraphicsItem,
        old_species: dict[str, Any] | None,
        new_species: dict[str, Any] | None,
        old_radius: float | None = None,
        new_radius: float | None = None,
        old_spacing_override: float | None = None,
        new_spacing_override: float | None = None,
    ) -> None:
        self._item = item
        self._old_species = deepcopy(old_species)
        self._new_species = deepcopy(new_species)
        self._old_radius = old_radius
        self._new_radius = new_radius
        self._old_spacing_override = old_spacing_override
        self._new_spacing_override = new_spacing_override

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Edit plant details")

    def _apply(
        self,
        species: dict[str, Any] | None,
        radius: float | None,
        spacing_override: float | None,
    ) -> None:
        if radius is not None:
            self._item.set_radius_centered(radius)  # type: ignore[attr-defined]
        metadata = self._item.metadata  # type: ignore[attr-defined]
        if species is None:
            metadata.pop("plant_species", None)
        else:
            metadata["plant_species"] = deepcopy(species)
        if hasattr(self._item, "spacing_radius_cm"):
            self._item.spacing_radius_cm = spacing_override
        with suppress(Exception):
            if hasattr(self._item, "update"):
                self._item.update()

    def execute(self) -> None:
        """Apply the new species dict + footprint radius."""
        self._apply(self._new_species, self._new_radius, self._new_spacing_override)

    def undo(self) -> None:
        """Restore the old species dict + footprint radius."""
        self._apply(self._old_species, self._old_radius, self._old_spacing_override)

    def merge_from(self, edit: "PlantSpeciesEditCommand") -> None:
        """Apply the next tick while preserving this gesture's original snapshot."""
        if edit._item is not self._item:
            raise ValueError("Cannot merge edits to different plants")
        edit.execute()
        self._new_species = deepcopy(edit._new_species)
        self._new_radius = edit._new_radius
        self._new_spacing_override = edit._new_spacing_override


class PlantInstanceEditCommand(Command):
    """One committed Plant Details instance edit as a single undo step (#559).

    Captures the ``metadata['plant_instance']`` dict. Geometry-affecting keys
    (``current_spread_cm``, ``current_height_cm``, ``planting_date``) trigger
    ``prepareGeometryChange`` before the write so the scene index does not
    keep the old rect.
    """

    _GEOMETRY_KEYS = frozenset(
        {"current_spread_cm", "current_height_cm", "planting_date"}
    )

    def __init__(
        self,
        item: QGraphicsItem,
        old_instance: dict[str, Any],
        new_instance: dict[str, Any],
    ) -> None:
        self._item = item
        self._old_instance = deepcopy(old_instance)
        self._new_instance = deepcopy(new_instance)

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Edit plant details")

    def _apply(self, instance: dict[str, Any]) -> None:
        metadata = self._item.metadata  # type: ignore[attr-defined]
        try:
            if hasattr(self._item, "prepareGeometryChange"):
                self._item.prepareGeometryChange()
        except Exception:
            pass
        metadata["plant_instance"] = deepcopy(instance)
        try:
            if hasattr(self._item, "update"):
                self._item.update()
        except Exception:
            pass

    def execute(self) -> None:
        """Apply the new instance dict."""
        self._apply(self._new_instance)

    def undo(self) -> None:
        """Restore the old instance dict."""
        self._apply(self._old_instance)

    def merge_from(self, edit: "PlantInstanceEditCommand") -> None:
        """Apply a tick without replacing the gesture's original snapshot."""
        if edit._item is not self._item:
            raise ValueError("Cannot merge edits to different plants")
        edit.execute()
        self._new_instance = deepcopy(edit._new_instance)


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
        return QCoreApplication.translate("Commands", "Move vertex")

    def execute(self) -> None:
        """Apply the new vertex position."""
        self._apply_func(self._item, self._vertex_index, self._new_pos)

    def undo(self) -> None:
        """Restore the old vertex position."""
        self._apply_func(self._item, self._vertex_index, self._old_pos)


class SetCurveGeometryCommand(Command):
    """Reshape a Bezier / Arc curve by restoring a geometry snapshot.

    Used by the curve edit handles (issue #193). A handle drag mutates the
    item's geometry live, so by release the *new* state is already applied;
    this command only needs to (re-)apply it on redo and restore the *old*
    state on undo. ``old_state`` / ``new_state`` are the opaque, comparable
    snapshots returned by the item's ``_capture_geometry()``; the item's
    ``_restore_geometry()`` is the inverse.
    """

    def __init__(
        self,
        item: QGraphicsItem,
        old_state: Any,
        new_state: Any,
    ) -> None:
        self._item = item
        self._old = old_state
        self._new = new_state

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Reshape curve")

    def execute(self) -> None:
        self._item._restore_geometry(self._new)  # type: ignore[attr-defined]

    def undo(self) -> None:
        self._item._restore_geometry(self._old)  # type: ignore[attr-defined]


class AddVertexCommand(Command):
    """Command for adding a vertex to a polygon."""

    def __init__(
        self,
        item: QGraphicsItem,
        vertex_index: int,
        position: QPointF,
        apply_add_func: Callable[[QGraphicsItem, int, QPointF], None],
        apply_remove_func: Callable[[QGraphicsItem, int], None],
        topology: tuple[object, bool, int] | None = None,
    ) -> None:
        """Initialize the add vertex command.

        Args:
            item: The polygon item being modified
            vertex_index: Index where the vertex will be inserted
            position: Position of the new vertex
            apply_add_func: Function to add a vertex to the item
            apply_remove_func: Function to remove a vertex from the item
            topology: ``(before_snapshot, closed, vertex_count_before)`` captured
                before the interactive mutation.  The command owns the
                constraint renumbering so GUI undo, redo and the Agent API share
                one invariant (round-4 review P1); when omitted it captures the
                snapshot itself (the Agent API builds before executing).
        """
        self._item = item
        self._vertex_index = vertex_index
        self._position = position
        self._apply_add_func = apply_add_func
        self._apply_remove_func = apply_remove_func
        self._topology = topology
        self._before: object | None = topology[0] if topology else None

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Add vertex")

    def _graph(self) -> object | None:
        scene = self._item.scene()
        return getattr(scene, "constraint_graph", None)

    def _ensure_topology(self) -> tuple[object, bool, int] | None:
        """The ``(before_snapshot, closed, count)`` this command applies."""
        if self._topology is not None:
            return self._topology
        graph = self._graph()
        item_id = getattr(self._item, "item_id", None)
        if graph is None or item_id is None:
            return None
        from open_garden_planner.ui.canvas.items import PolygonItem

        count = int(self._item._get_vertex_count())  # type: ignore[attr-defined]
        self._topology = (
            graph.capture_topology_state(item_id),  # type: ignore[attr-defined]
            isinstance(self._item, PolygonItem),
            count,
        )
        self._before = self._topology[0]
        return self._topology

    def execute(self) -> None:
        """Add the vertex."""
        # Resolve the pre-mutation state BEFORE the geometry changes: the Agent
        # API builds this command before executing, so this is the only place
        # the old vertex count is still observable (#670 review).
        graph = self._graph()
        topology = self._ensure_topology()
        self._apply_add_func(self._item, self._vertex_index, self._position)
        if graph is not None and topology is not None:
            before, closed, count_before = topology
            del before
            graph.apply_vertex_insert(  # type: ignore[attr-defined]
                self._item.item_id,  # type: ignore[attr-defined]
                self._vertex_index,
                closed=closed,
                vertex_count_before=count_before,
            )

    def undo(self) -> None:
        """Remove the vertex and restore the constraint anchors it renumbered."""
        self._apply_remove_func(self._item, self._vertex_index)
        graph = self._graph()
        self._ensure_topology()
        if graph is not None and self._before is not None:
            graph.restore_topology_state(self._before)  # type: ignore[attr-defined]


class AlignItemsCommand(Command):
    """Command for aligning/distributing items with per-item deltas.

    Unlike MoveItemsCommand (uniform delta), each item can move a different amount.
    Used by alignment and distribution operations.
    """

    def __init__(
        self,
        item_deltas: list[tuple[QGraphicsItem, QPointF]],
        description_text: str | None = None,
    ) -> None:
        """Initialize the alignment command.

        Args:
            item_deltas: List of (item, delta) tuples.
            description_text: Already-translated description for the undo menu;
                callers should pass a tr()/translate() result. Falls back to a
                translated generic label when omitted.
        """
        self._item_deltas = list(item_deltas)
        self._description_text = description_text
        scene = self._item_deltas[0][0].scene() if self._item_deltas else None
        if scene is not None:
            # A moved bed takes its plants along, one rule for every path (#443 (vi)).
            self._item_deltas = expand_with_bed_children(scene, self._item_deltas)
        self._membership = _membership_change_for_move(
            scene, [item for item, _delta in self._item_deltas]
        )

    @property
    def description(self) -> str:
        """Human-readable description."""
        if self._description_text is not None:
            return self._description_text
        return QCoreApplication.translate("Commands", "Align items")

    def execute(self) -> None:
        """Move each item by its individual delta, then re-derive bed links."""
        for item, delta in self._item_deltas:
            item.moveBy(delta.x(), delta.y())
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Restore bed links, then move each item back by its individual delta."""
        if self._membership is not None:
            self._membership.restore()
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
        topology: tuple[object, bool, int] | None = None,
    ) -> None:
        """Initialize the delete vertex command.

        Args:
            item: The polygon item being modified
            vertex_index: Index of the vertex to delete
            position: Position of the vertex (for undo)
            apply_add_func: Function to add a vertex to the item (for undo)
            apply_remove_func: Function to remove a vertex from the item
            topology: ``(before_snapshot, closed, vertex_count_before)`` captured
                before the interactive mutation (see ``AddVertexCommand``).
        """
        self._item = item
        self._vertex_index = vertex_index
        self._position = position
        self._apply_add_func = apply_add_func
        self._apply_remove_func = apply_remove_func
        self._topology = topology
        self._before: object | None = topology[0] if topology else None

    @property
    def description(self) -> str:
        """Human-readable description."""
        return QCoreApplication.translate("Commands", "Delete vertex")

    def _graph(self) -> object | None:
        scene = self._item.scene()
        return getattr(scene, "constraint_graph", None)

    def _ensure_topology(self) -> tuple[object, bool, int] | None:
        """The ``(before_snapshot, closed, count)`` this command applies."""
        if self._topology is not None:
            return self._topology
        graph = self._graph()
        item_id = getattr(self._item, "item_id", None)
        if graph is None or item_id is None:
            return None
        from open_garden_planner.ui.canvas.items import PolygonItem

        count = int(self._item._get_vertex_count())  # type: ignore[attr-defined]
        self._topology = (
            graph.capture_topology_state(item_id),  # type: ignore[attr-defined]
            isinstance(self._item, PolygonItem),
            count,
        )
        self._before = self._topology[0]
        return self._topology

    def execute(self) -> None:
        """Remove the vertex."""
        graph = self._graph()
        topology = self._ensure_topology()
        self._apply_remove_func(self._item, self._vertex_index)
        if graph is not None and topology is not None:
            before, closed, count_before = topology
            del before
            graph.apply_vertex_delete(  # type: ignore[attr-defined]
                self._item.item_id,  # type: ignore[attr-defined]
                self._vertex_index,
                closed=closed,
                vertex_count_before=count_before,
            )

    def undo(self) -> None:
        """Restore the vertex and the constraint anchors it renumbered."""
        self._apply_add_func(self._item, self._vertex_index, self._position)
        graph = self._graph()
        self._ensure_topology()
        if graph is not None and self._before is not None:
            graph.restore_topology_state(self._before)  # type: ignore[attr-defined]


class MultiVertexMoveCommand(Command):
    """Undo/redo for one or more vertex moves across one or more items.

    Used to bundle a user-driven vertex drag with automatic constraint
    corrections into a single Ctrl+Z step.
    """

    def __init__(
        self,
        vertex_moves: "list[tuple[QGraphicsItem, int, QPointF, QPointF]]",
        description: str | None = None,
    ) -> None:
        """Initialize with a list of (item, vertex_index, old_local, new_local) tuples."""
        self._vertex_moves = vertex_moves
        self._desc = description

    @property
    def description(self) -> str:
        if self._desc is not None:
            return self._desc
        return QCoreApplication.translate("Commands", "Move vertex")

    def execute(self) -> None:
        for item, idx, _old, new in self._vertex_moves:
            if hasattr(item, "_move_vertex_to"):
                item._move_vertex_to(idx, new)

    def undo(self) -> None:
        for item, idx, old, _new in reversed(self._vertex_moves):
            if hasattr(item, "_move_vertex_to"):
                item._move_vertex_to(idx, old)


def _capture_bed_child_moves(
    item_moves: "list[tuple[QGraphicsItem, QPointF, QPointF]]",
) -> "list[tuple[QGraphicsItem, QPointF, QPointF]]":
    """Children a one-shot solver move must carry, as ``(child, before, after)``.

    ``AddConstraintCommand`` / ``EditConstraintDistanceCommand`` move items to
    satisfy a new relation directly (not through ``MoveItemsCommand``); a bed
    among them must take its plants along, or the next reconcile unlinks them
    while the panel still calls them contained (#443 (vi)).
    """
    from open_garden_planner.core.object_types import is_plant_parent_type
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = []
    moved_ids = {id(item) for item, _old, _new in item_moves}
    for item, old, new in item_moves:
        scene = item.scene()
        if scene is None:
            continue
        finder = getattr(scene, "find_item_by_id", None)
        if not callable(finder):
            continue
        if not isinstance(item, GardenItemMixin):
            continue
        if not is_plant_parent_type(item.object_type):
            continue
        delta = new - old
        for child_id in item.child_item_ids:
            child = finder(child_id)
            if (
                child is None
                or id(child) in moved_ids
                or bed_child_has_constraints(scene, child_id)
            ):
                # The solver already gave this child its own absolute move;
                # adding the bed's delta would move it twice (review round 3).
                continue
            current = child.pos()
            moves.append((child, current, current + delta))
    return moves


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
        self._vertex_moves: list[tuple[QGraphicsItem, int, QPointF, QPointF]] = []
        self._target_x = target_x
        self._target_y = target_y
        self._child_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = []
        self._children_captured = False
        self._membership: BedMembershipChange | None = None

    def _prepare_membership(self) -> None:
        """Build the link tracker from the payload as it is NOW.

        The constraint tools construct the command with an EMPTY payload, run a
        trial ``execute()``/``undo()`` and only then inject ``_item_moves`` (the
        shipped ``CanvasView._execute_constraint_with_solve`` path). Building the
        tracker in ``__init__`` therefore missed the real moves — review round 3.
        """
        moved = (
            [item for item, _old, _new in self._item_moves]
            + [item for item, _old_angle, _new_angle, _fn in self._item_rotations]
            + [item for item, _index, _old_local, _new_local in self._vertex_moves]
        )
        scene = moved[0].scene() if moved else None
        self._membership = _membership_change_for_move(scene, moved)

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add constraint")

    def execute(self) -> None:
        self._prepare_membership()
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
        for item, idx, _old_local, new_local in self._vertex_moves:
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(idx, new_local)
        if not self._children_captured:
            self._children_captured = True
            self._child_moves = _capture_bed_child_moves(self._item_moves)
        for child, _old, new in self._child_moves:
            child.setPos(new)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        if self._constraint_id is not None:
            self._graph.remove_constraint(self._constraint_id)
        if self._membership is not None:
            self._membership.restore()
        # Revert the carried children's positions first.
        for child, old, _new in self._child_moves:
            child.setPos(old)
        # Revert vertex moves first (reverse order)
        for item, idx, old_local, _new_local in reversed(self._vertex_moves):
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(idx, old_local)
        for item, old, _new in self._item_moves:
            item.setPos(old)
        for item, old_angle, _new_angle, apply_func in self._item_rotations:
            apply_func(item, old_angle)
        # A later redo re-prepares from the payload and the restored links; the
        # trial execute/undo of the constraint tool relies on this reset.
        self._membership = None
        self._children_captured = False
        self._child_moves = []


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
        return QCoreApplication.translate("Commands", "Remove constraint")

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
            # #656: the third anchor is part of the removed constraint.  Dropping
            # it left an ANGLE / POINT_ON_EDGE / TANGENT constraint structurally
            # different after undo (a broken relation the panel cannot describe).
            anchor_c=self._constraint.anchor_c,
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
        self._membership: BedMembershipChange | None = None

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Create linear array ({count} items)").format(
            count=len(self._items) + 1
        )

    def execute(self) -> None:
        """Add items and constraints to the scene, then re-derive copy links."""
        if self._membership is None:
            self._membership = _membership_for_added_items(
                self._scene, self._items, clear_inherited=True
            )
        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._graph and self._constraint_pairs:
            self._constraint_ids = []
            for anchor_a, anchor_b, dist in self._constraint_pairs:
                c = self._graph.add_constraint(anchor_a, anchor_b, dist)
                self._constraint_ids.append(c.constraint_id)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Remove constraints then items from the scene; restore displaced links."""
        if self._graph:
            for cid in reversed(self._constraint_ids):
                self._graph.remove_constraint(cid)
        self._constraint_ids = []
        for item in self._items:
            _detach_from_parent(self._scene, item)
            if item.scene() is not None:
                self._scene.removeItem(item)
        if self._membership is not None:
            self._membership.restore()


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
        self._membership: BedMembershipChange | None = None

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Create grid array ({count} items)").format(
            count=len(self._items) + 1
        )

    def execute(self) -> None:
        """Add items and constraints to the scene, then re-derive copy links."""
        if self._membership is None:
            self._membership = _membership_for_added_items(
                self._scene, self._items, clear_inherited=True
            )
        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._graph and self._constraint_pairs:
            self._constraint_ids = []
            for anchor_a, anchor_b, dist in self._constraint_pairs:
                c = self._graph.add_constraint(anchor_a, anchor_b, dist)
                self._constraint_ids.append(c.constraint_id)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Remove constraints then items from the scene; restore displaced links."""
        if self._graph:
            for cid in reversed(self._constraint_ids):
                self._graph.remove_constraint(cid)
        self._constraint_ids = []
        for item in self._items:
            _detach_from_parent(self._scene, item)
            if item.scene() is not None:
                self._scene.removeItem(item)
        if self._membership is not None:
            self._membership.restore()


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
        self._membership: BedMembershipChange | None = None

    @property
    def description(self) -> str:
        return QCoreApplication.translate(
            "Commands", "Create circular array ({count} items)"
        ).format(count=len(self._items) + 1)

    def execute(self) -> None:
        """Add items to the scene, then re-derive every copy's bed link."""
        if self._membership is None:
            self._membership = _membership_for_added_items(
                self._scene, self._items, clear_inherited=True
            )
        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        """Remove items from the scene; restore the links they displaced."""
        for item in self._items:
            _detach_from_parent(self._scene, item)
            if item.scene() is not None:
                self._scene.removeItem(item)
        if self._membership is not None:
            self._membership.restore()


class MirrorItemsCommand(Command):
    """Command for mirroring a selection across an axis (US-B4).

    ``mirrored`` are the freshly-built reflected items. In **copy** mode the
    originals are left untouched and the copies are added. In **move** mode the
    originals are removed and replaced by the reflected items (which carry the
    originals' ``item_id`` so existing constraints stay bound). One drag = one
    undoable step.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        originals: "list[QGraphicsItem]",
        mirrored: "list[QGraphicsItem]",
        copy: bool,
    ) -> None:
        self._scene = scene
        self._originals = list(originals)
        self._mirrored = list(mirrored)
        self._copy = copy
        self._membership: BedMembershipChange | None = None
        if copy:
            from open_garden_planner.ui.guild_copy import remap_mirror_membership

            remap_mirror_membership(scene, self._originals, self._mirrored)

    @property
    def description(self) -> str:
        count = len(self._mirrored)
        if self._copy:
            return QCoreApplication.translate(
                "Commands", "Mirror {count} item(s) (copy)"
            ).format(count=count)
        return QCoreApplication.translate(
            "Commands", "Mirror {count} item(s) (move)"
        ).format(count=count)

    def execute(self) -> None:
        if self._membership is None:
            # In Move mode the originals are removed while their ids live on in
            # the mirrored items; tracking them too lets undo heal the parent's
            # child list for the re-added original object (#443 review).
            tracked = list(self._mirrored)
            if not self._copy:
                tracked.extend(self._originals)
            self._membership = _membership_for_added_items(
                self._scene, tracked, clear_inherited=self._copy
            )
        if not self._copy:
            for item in self._originals:
                if item.scene() is self._scene:
                    # Detach BEFORE removing: the mirrored replacement reuses the
                    # id, so the bed's child list must not keep the id unless the
                    # replacement is linked again (redo/undo stay two-sided).
                    _detach_from_parent(self._scene, item)
                    self._scene.removeItem(item)
        with _bulk_add_scope(self._scene):
            for item in self._mirrored:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        for item in self._mirrored:
            _detach_from_parent(self._scene, item)
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        if not self._copy:
            with _bulk_add_scope(self._scene):
                for item in self._originals:
                    if item.scene() is None:
                        self._scene.addItem(item)
        if self._membership is not None:
            self._membership.restore()


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
        self._vertex_moves: list[tuple[QGraphicsItem, int, QPointF, QPointF]] = []
        self._child_moves: list[tuple[QGraphicsItem, QPointF, QPointF]] = []
        self._children_captured = False
        self._membership: BedMembershipChange | None = None

    def _prepare_membership(self) -> None:
        moved = (
            [item for item, _old, _new in self._item_moves]
            + [item for item, _index, _old_local, _new_local in self._vertex_moves]
        )
        scene = moved[0].scene() if moved else None
        self._membership = _membership_change_for_move(scene, moved)

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit constraint distance")

    def execute(self) -> None:
        self._prepare_membership()
        c = self._graph.constraints.get(self._constraint_id)
        if c:
            c.target_distance = self._new_distance
        for item, _old, new in self._item_moves:
            item.setPos(new)
        for item, idx, _old_local, new_local in self._vertex_moves:
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(idx, new_local)
        if not self._children_captured:
            self._children_captured = True
            self._child_moves = _capture_bed_child_moves(self._item_moves)
        for child, _old, new in self._child_moves:
            child.setPos(new)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        c = self._graph.constraints.get(self._constraint_id)
        if c:
            c.target_distance = self._old_distance
        if self._membership is not None:
            self._membership.restore()
        for child, old, _new in self._child_moves:
            child.setPos(old)
        for item, idx, old_local, _new_local in reversed(self._vertex_moves):
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(idx, old_local)
        for item, old, _new in self._item_moves:
            item.setPos(old)
        self._membership = None
        self._children_captured = False
        self._child_moves = []


class SetParentBedCommand(Command):
    """Command to attach/detach a plant to/from a bed."""

    def __init__(
        self,
        scene: QGraphicsScene,
        plant_item: QGraphicsItem,
        old_parent_id: UUID | None,
        new_parent_id: UUID | None,
    ) -> None:
        self._scene = scene
        self._plant = plant_item
        self._old_parent_id = old_parent_id
        self._new_parent_id = new_parent_id

    @property
    def description(self) -> str:
        if self._new_parent_id is None:
            return QCoreApplication.translate("Commands", "Detach plant from bed")
        return QCoreApplication.translate("Commands", "Attach plant to bed")

    def execute(self) -> None:
        self._set_parent(self._new_parent_id, self._old_parent_id)

    def undo(self) -> None:
        self._set_parent(self._old_parent_id, self._new_parent_id)

    def _set_parent(self, attach_id: UUID | None, detach_id: UUID | None) -> None:
        # One mutator for both sides of the link (issue #443). ``detach_id`` is
        # kept in the signature for the command's own callers; the current
        # parent is read from the plant, which is always the truth here.
        del detach_id
        set_parent_link(self._scene, self._plant, attach_id)


class GroupCommand(Command):
    """Group multiple items into a single movable unit."""

    def __init__(self, scene: QGraphicsScene, items: list[QGraphicsItem]) -> None:
        self._scene = scene
        self._items = list(items)
        self._group: QGraphicsItem | None = None

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Group {count} items").format(
            count=len(self._items)
        )

    def execute(self) -> None:
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        if self._group is None:
            # Infer layer_id from the first item that has one
            layer_id = None
            from open_garden_planner.ui.canvas.items import GardenItemMixin
            for item in self._items:
                if isinstance(item, GardenItemMixin) and item.layer_id:
                    layer_id = item.layer_id
                    break
            self._group = GroupItem(layer_id=layer_id)

        self._scene.addItem(self._group)
        for item in self._items:
            item.setSelected(False)
            self._group.addToGroup(item)  # type: ignore[attr-defined]
        self._group.setSelected(True)

    def undo(self) -> None:
        if self._group is None:
            return
        for item in self._items:
            self._group.removeFromGroup(item)  # type: ignore[attr-defined]
            # Restore standard interaction flags cleared by addToGroup
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setSelected(True)
            # The item is top-level again (issue #338). It keeps the
            # stack_order rank it had before grouping -- clearing it here
            # would make undo(Group) not the inverse of execute() (a member
            # that never had a rank still sorts to the top, which is
            # acceptable). The refresh below only recomputes z-values from
            # existing ranks; it never assigns new ones.
        self._scene.removeItem(self._group)
        refresh_all = getattr(self._scene, "_update_items_z_order", None)
        if callable(refresh_all):
            refresh_all()


class UngroupCommand(Command):
    """Ungroup a GroupItem back into independent items."""

    def __init__(self, scene: QGraphicsScene, group: QGraphicsItem) -> None:
        self._scene = scene
        self._group = group
        self._items: list[QGraphicsItem] = list(group.childItems())

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Ungroup")

    def execute(self) -> None:
        for item in self._items:
            self._group.removeFromGroup(item)  # type: ignore[attr-defined]
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
            item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            item.setSelected(True)
            # Top-level again (issue #338); keeps its pre-group stack_order
            # rank so execute() is the exact inverse of undo() -- see the
            # matching note in GroupCommand.undo above.
        self._scene.removeItem(self._group)
        refresh_all = getattr(self._scene, "_update_items_z_order", None)
        if callable(refresh_all):
            refresh_all()

    def undo(self) -> None:
        if self._group.scene() is None:
            self._scene.addItem(self._group)
        for item in self._items:
            item.setSelected(False)
            self._group.addToGroup(item)  # type: ignore[attr-defined]
        self._group.setSelected(True)


class BooleanShapeCommand(Command):
    """Replace every source shape by one result in a single undo step.

    The original two-shape constructor stays valid; a union over a larger
    selection passes the rest as ``additional_items`` (#550).
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        item_a: QGraphicsItem,
        item_b: QGraphicsItem,
        result_item: QGraphicsItem,
        operation: str,
        *,
        additional_items: list[QGraphicsItem] | None = None,
    ) -> None:
        self._scene = scene
        self._original_items = [item_a, item_b, *(additional_items or [])]
        self._result_item = result_item
        self._operation = operation

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Boolean {operation}").format(
            operation=self._operation
        )

    def execute(self) -> None:
        for item in self._original_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        if self._result_item.scene() is None:
            self._scene.addItem(self._result_item)

    def undo(self) -> None:
        if self._result_item.scene() is not None:
            self._scene.removeItem(self._result_item)
        with _bulk_add_scope(self._scene):
            for item in self._original_items:
                if item.scene() is None:
                    self._scene.addItem(item)


class ArrayAlongPathCommand(Command):
    """Place copies of an item along a path."""

    def __init__(
        self, scene: QGraphicsScene, new_items: list[QGraphicsItem]
    ) -> None:
        self._scene = scene
        self._items = list(new_items)
        self._membership: BedMembershipChange | None = None

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Array along path ({count} copies)").format(
            count=len(self._items)
        )

    def execute(self) -> None:
        if self._membership is None:
            self._membership = _membership_for_added_items(
                self._scene, self._items, clear_inherited=True
            )
        with _bulk_add_scope(self._scene):
            for item in self._items:
                if item.scene() is None:
                    self._scene.addItem(item)
        if self._membership is not None:
            self._membership.reconcile()

    def undo(self) -> None:
        for item in self._items:
            _detach_from_parent(self._scene, item)
            if item.scene() is not None:
                self._scene.removeItem(item)
        if self._membership is not None:
            self._membership.restore()


class MoveToLayerCommand(Command):
    """Move one or more scene items to a different layer (undoable).

    Snapshots each item's current ``layer_id`` AND ``stack_order`` at
    construction time so that undo restores every item to its individual
    original layer and rank, even when items come from different layers
    before the move.

    Items that are already in the target layer are left completely alone on
    execute -- no ``layer_id`` write, no rank reassignment -- so re-selecting
    an item's current layer (e.g. via the Properties panel combo) is a true
    no-op rather than silently bumping it to the top (issue #338).
    """

    def __init__(
        self,
        items: list[QGraphicsItem],
        target_layer_id: UUID,
        scene: QGraphicsScene,
        target_layer_name: str,
    ) -> None:
        """Initialise the command.

        Args:
            items: Items to move (must have a ``layer_id`` attribute).
            target_layer_id: UUID of the destination layer.
            scene: The canvas scene (used to refresh visibility and z-order).
            target_layer_name: Human-readable name of the target layer
                (used in the undo description only; not looked up at undo time).
        """
        # Snapshot (item, original_layer_id, original_stack_order) at
        # construction — before any move.
        self._moves: list[tuple[QGraphicsItem, UUID | None, int | None]] = [
            (item, item.layer_id, getattr(item, "stack_order", None))
            for item in items
        ]
        self._target_layer_id = target_layer_id
        self._scene = scene
        self._target_layer_name = target_layer_name

    @property
    def description(self) -> str:
        n = len(self._moves)
        return QCoreApplication.translate(
            "Commands", "Move {count} item(s) to layer '{name}'"
        ).format(count=n, name=self._target_layer_name)

    def execute(self) -> None:
        """Move items whose layer actually changes to the target layer, on top.

        Items already in the target layer are skipped entirely — they keep
        their existing rank (issue #338). The items that DO change layer are
        ranked above everything already in the target layer, in their
        current bottom-to-top order (so a multi-selection spanning several
        source layers still lands in a sensible relative order).

        Every item in ``changing`` gets its ``layer_id`` written — even one
        that, for whatever reason, isn't currently in ``self._scene``. Scene
        order is used ONLY to decide the rank sequence for the (normal)
        case of items that are in the scene; an item not found there still
        gets moved and ranked, just appended after the ones that are, in
        their original ``self._moves`` order. Without this, such an item
        would be silently skipped here while :meth:`undo` restores it
        unconditionally — execute() must stay the exact inverse of undo()
        (issue #338 review P2).
        """
        changing = [
            item
            for item, old_layer_id, _ in self._moves
            if old_layer_id != self._target_layer_id
        ]
        if changing:
            next_stack_order = getattr(self._scene, "_next_stack_order", None)
            max_rank = (
                next_stack_order(self._target_layer_id) - STACK_STEP
                if callable(next_stack_order)
                else 0
            )
            changing_ids = {id(item) for item in changing}
            in_scene_order = [
                item
                for item in reversed(self._scene.items())
                if id(item) in changing_ids
            ]
            in_scene_ids = {id(item) for item in in_scene_order}
            not_in_scene = [item for item in changing if id(item) not in in_scene_ids]
            bottom_to_top = in_scene_order + not_in_scene
            for k, item in enumerate(bottom_to_top, start=1):
                item.layer_id = self._target_layer_id
                if hasattr(item, "stack_order"):
                    item.stack_order = max_rank + STACK_STEP * k
        self._scene._update_items_visibility()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]

    def undo(self) -> None:
        """Restore each item to its original layer and rank; refresh scene visuals."""
        for item, old_layer_id, old_stack_order in self._moves:
            item.layer_id = old_layer_id
            if hasattr(item, "stack_order"):
                item.stack_order = old_stack_order
        self._scene._update_items_visibility()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]


class AddLayerCommand(Command):
    """Add a new layer at the top of the layer order and activate it (undoable).

    Implements the user-facing "Add Layer" behavior (FR-LAYER-08 / issue #201):
    the layer is inserted at list index 0, which ``reorder_layers`` maps to the
    highest z_order, and becomes the active layer so newly drawn elements land
    on it. Undo restores the previous order, the exact per-layer z_orders
    (imported layers may carry z_orders that do not match the position
    formula), and the previously active layer.
    """

    def __init__(self, scene: QGraphicsScene, layer: "Layer") -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene.
            layer: The (not yet added) layer to insert at the top.
        """
        self._scene = scene
        self._layer = layer
        self._prev_active: Layer | None = scene.active_layer  # type: ignore[attr-defined]
        self._prev_z: list[tuple[Layer, int]] = [
            (lyr, lyr.z_order)
            for lyr in scene.layers  # type: ignore[attr-defined]
        ]

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add layer '{name}'").format(
            name=self._layer.name
        )

    def execute(self) -> None:
        """Insert the layer at the top of the order and make it active."""
        layers = self._scene.layers  # type: ignore[attr-defined]
        if self._layer not in layers:
            layers.insert(0, self._layer)
        # reorder_layers recomputes z_order from list position (index 0 = top),
        # emits layers_changed and refreshes item stacking.
        self._scene.reorder_layers(layers)  # type: ignore[attr-defined]
        self._scene.set_active_layer(self._layer)  # type: ignore[attr-defined]

    def undo(self) -> None:
        """Remove the layer and restore previous z_orders and active layer."""
        layers = self._scene.layers  # type: ignore[attr-defined]
        if self._layer in layers:
            layers.remove(self._layer)
        for lyr, z in self._prev_z:
            lyr.z_order = z
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]
        # Last on purpose: the layers_changed-driven panel rebuild may select a
        # fallback row; restoring the active layer afterwards wins and re-syncs
        # the panel selection via active_layer_changed.
        self._scene.set_active_layer(self._prev_active)  # type: ignore[attr-defined]


class DeleteLayerCommand(Command):
    """Delete a layer, moving its items to a replacement layer (undoable).

    Mirrors ``CanvasScene.remove_layer`` (same replacement-layer rule, no
    recompute of survivor z_orders) but snapshots enough state to restore the
    layer at its original index, give the moved items back their original
    ``layer_id``, and reinstate the previously active layer on undo.

    The caller must guarantee the scene has at least two layers.
    """

    def __init__(self, scene: QGraphicsScene, layer_id: UUID) -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene.
            layer_id: ID of the layer to delete (must exist).
        """
        self._scene = scene
        layer = scene.get_layer_by_id(layer_id)  # type: ignore[attr-defined]
        if layer is None:
            raise ValueError(f"No layer with id {layer_id}")
        self._layer: Layer = layer
        layers = scene.layers  # type: ignore[attr-defined]
        self._index: int = layers.index(layer)
        # Same replacement rule as CanvasScene.remove_layer.
        replacement = scene.get_layer_replacement(layer_id)  # type: ignore[attr-defined]
        if replacement is None:
            raise ValueError(
                f"Cannot delete layer {layer.name!r}: it is the plan's only layer."
            )
        self._replacement: Layer = replacement
        if self._replacement.locked:
            raise ValueError(
                f"Cannot delete layer {layer.name!r}: its replacement layer "
                f"{self._replacement.name!r} is locked. Unlock the replacement "
                "layer first."
            )
        self._prev_active: Layer | None = scene.active_layer  # type: ignore[attr-defined]
        self._moved_items: list[QGraphicsItem] = []

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete layer '{name}'").format(
            name=self._layer.name
        )

    def execute(self) -> None:
        """Move the layer's items to the replacement layer and remove it."""
        # Revalidate on every execution, including redo. Layer locks can change
        # while the command is sitting on the redo stack.
        if self._replacement.locked:
            raise ValueError(
                f"Cannot delete layer {self._layer.name!r}: its replacement layer "
                f"{self._replacement.name!r} is locked. Unlock the replacement "
                "layer first."
            )
        # Re-capture on every execute (incl. redo): the linear stack guarantees
        # the same items are back on this layer by the time a redo runs.
        self._moved_items = [
            item
            for item in self._scene.items()
            if getattr(item, "layer_id", None) == self._layer.id
        ]
        for item in self._moved_items:
            item.layer_id = self._replacement.id
        layers = self._scene.layers  # type: ignore[attr-defined]
        if self._layer in layers:
            layers.remove(self._layer)
        if self._scene.active_layer is self._layer:  # type: ignore[attr-defined]
            self._scene.set_active_layer(self._replacement)  # type: ignore[attr-defined]
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]
        self._scene._update_items_visibility()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]

    def undo(self) -> None:
        """Re-insert the layer, restore item assignments and active layer."""
        layers = self._scene.layers  # type: ignore[attr-defined]
        if self._layer not in layers:
            layers.insert(min(self._index, len(layers)), self._layer)
        for item in self._moved_items:
            item.layer_id = self._layer.id
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]
        self._scene._update_items_visibility()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]
        self._scene.set_active_layer(self._prev_active)  # type: ignore[attr-defined]


class RenameLayerCommand(Command):
    """Rename a layer (undoable)."""

    def __init__(self, scene: QGraphicsScene, layer: "Layer", new_name: str) -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene.
            layer: The layer to rename (its current name is snapshotted).
            new_name: The new layer name.
        """
        self._scene = scene
        self._layer = layer
        self._old_name = layer.name
        self._new_name = new_name

    @property
    def description(self) -> str:
        return QCoreApplication.translate(
            "Commands", "Rename layer to '{name}'"
        ).format(name=self._new_name)

    def execute(self) -> None:
        self._layer.name = self._new_name
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]

    def undo(self) -> None:
        self._layer.name = self._old_name
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]


class ReorderLayersCommand(Command):
    """Reorder the layer stack (undoable).

    Undo restores the exact previous order AND each layer's exact previous
    z_order rather than recomputing from position — imported layers (e.g. DXF)
    may carry z_orders that do not match the ``len - 1 - index`` formula.
    """

    def __init__(self, scene: QGraphicsScene, new_order: list["Layer"]) -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene.
            new_order: The new layer order (first in list = top).
        """
        self._scene = scene
        self._new_order = list(new_order)
        self._old_state: list[tuple[Layer, int]] = [
            (lyr, lyr.z_order)
            for lyr in scene.layers  # type: ignore[attr-defined]
        ]

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Reorder layers")

    def execute(self) -> None:
        self._scene.reorder_layers(list(self._new_order))  # type: ignore[attr-defined]

    def undo(self) -> None:
        self._scene._layers = [lyr for lyr, _ in self._old_state]  # type: ignore[attr-defined]
        for lyr, z in self._old_state:
            lyr.z_order = z
        self._scene.layers_changed.emit()  # type: ignore[attr-defined]
        self._scene._update_items_z_order()  # type: ignore[attr-defined]


class ArrangeItemsCommand(Command):
    """Reorder one or more layers' per-item stacking order (undoable, issue #338).

    Modelled on :class:`ReorderLayersCommand`: takes the already-computed new
    bottom-to-top order for each affected layer, plus a pre-translated
    description (the :class:`AlignItemsCommand` idiom -- the caller picks the
    wording for "bring to front" vs "send backward" etc., this command only
    applies it).

    Snapshots **every** top-level item's current ``stack_order`` in every
    affected layer, not just the ones that visibly move: ``normalize_order``'s
    child-above-parent clamp means an item that wasn't part of the selected
    block can still end up with a different rank once the layer is
    renumbered, so undo must restore the whole layer's ranks, not just the
    block's.

    ``ui/canvas/arrange.py::build_arrange_command`` is the one seam that
    computes *new_orders* and constructs this command -- every UI surface
    (menu, context menu, properties panel, agent tool) shares that seam
    rather than building a competing command here.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        new_orders: dict[UUID, list[QGraphicsItem]],
        description_text: str,
    ) -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene (used to snapshot ranks and refresh
                z-values).
            new_orders: For each affected layer id, that layer's new
                bottom-to-top item order.
            description_text: Already-translated description for the undo
                menu; callers should pass a tr()/translate() result.
        """
        self._scene = scene
        self._new_orders: dict[UUID, list[QGraphicsItem]] = {
            layer_id: list(items) for layer_id, items in new_orders.items()
        }
        self._description_text = description_text
        # Snapshot the CURRENT rank of every top-level item in every
        # affected layer -- before execute() renumbers anything.
        self._old_ranks: dict[QGraphicsItem, int | None] = {}
        normalized_layer_order = scene._normalized_layer_order  # type: ignore[attr-defined]
        for layer_id in self._new_orders:
            for item in normalized_layer_order(layer_id):
                self._old_ranks[item] = getattr(item, "stack_order", None)

    @property
    def description(self) -> str:
        """Human-readable description."""
        return self._description_text

    def execute(self) -> None:
        """Renumber each affected layer's items to STACK_STEP multiples."""
        for items in self._new_orders.values():
            for i, item in enumerate(items):
                if hasattr(item, "stack_order"):
                    item.stack_order = (i + 1) * STACK_STEP
        self._scene._update_items_z_order()  # type: ignore[attr-defined]

    def undo(self) -> None:
        """Restore every snapshotted item's previous ``stack_order``."""
        for item, old_rank in self._old_ranks.items():
            if hasattr(item, "stack_order"):
                item.stack_order = old_rank
        self._scene._update_items_z_order()  # type: ignore[attr-defined]


class SetLayerPropertyCommand(Command):
    """Set a layer's ``visible``, ``locked`` or ``opacity`` property (undoable).

    Delegates to the existing CanvasScene setters, which mutate the layer,
    refresh item visibility/selectability/opacity, and emit ``layers_changed``
    (rebuilding the layers panel so icons and the opacity slider follow).
    """

    _SETTERS = {
        "visible": "update_layer_visibility",
        "locked": "update_layer_lock",
        "opacity": "update_layer_opacity",
    }

    def __init__(
        self,
        scene: QGraphicsScene,
        layer: "Layer",
        prop: str,
        old_value: Any,
        new_value: Any,
    ) -> None:
        """Initialise the command.

        Args:
            scene: The canvas scene.
            layer: The layer to modify.
            prop: One of ``"visible"``, ``"locked"``, ``"opacity"``.
            old_value: The property value before the change.
            new_value: The property value to apply.
        """
        if prop not in self._SETTERS:
            raise ValueError(f"Unsupported layer property: {prop}")
        self._scene = scene
        self._layer = layer
        self._prop = prop
        self._old_value = old_value
        self._new_value = new_value

    @property
    def description(self) -> str:
        name = self._layer.name
        if self._prop == "visible":
            if self._new_value:
                return QCoreApplication.translate(
                    "Commands", "Show layer '{name}'"
                ).format(name=name)
            return QCoreApplication.translate(
                "Commands", "Hide layer '{name}'"
            ).format(name=name)
        if self._prop == "locked":
            if self._new_value:
                return QCoreApplication.translate(
                    "Commands", "Lock layer '{name}'"
                ).format(name=name)
            return QCoreApplication.translate(
                "Commands", "Unlock layer '{name}'"
            ).format(name=name)
        return QCoreApplication.translate(
            "Commands", "Set opacity of layer '{name}' to {pct}%"
        ).format(name=name, pct=round(self._new_value * 100))

    def _apply(self, value: Any) -> None:
        setter = getattr(self._scene, self._SETTERS[self._prop])
        setter(self._layer.id, value)

    def execute(self) -> None:
        self._apply(self._new_value)

    def undo(self) -> None:
        self._apply(self._old_value)


class TrimPolylineCommand(Command):
    """Remove a sub-segment from a PolylineItem, replacing it with 0–2 new pieces."""

    def __init__(
        self,
        scene: QGraphicsScene,
        original_item: QGraphicsItem,
        new_pieces: list[QGraphicsItem],
    ) -> None:
        """Initialize.

        Args:
            scene: The canvas scene.
            original_item: The polyline being trimmed (currently in scene).
            new_pieces: Replacement polyline(s) with trimmed geometry and
                        identical styling. May be empty if the entire item
                        is consumed by the trim.
        """
        self._scene = scene
        self._original = original_item
        self._pieces = list(new_pieces)

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Trim polyline")

    def execute(self) -> None:
        if self._original.scene() is not None:
            self._scene.removeItem(self._original)
        for piece in self._pieces:
            if piece.scene() is None:
                self._scene.addItem(piece)

    def undo(self) -> None:
        for piece in self._pieces:
            if piece.scene() is not None:
                self._scene.removeItem(piece)
        if self._original.scene() is None:
            self._scene.addItem(self._original)


class TrimPolygonCommand(Command):
    """Trim a polygon edge, replacing the PolygonItem with an open PolylineItem."""

    def __init__(
        self,
        scene: QGraphicsScene,
        original_polygon: QGraphicsItem,
        result_polyline: QGraphicsItem,
    ) -> None:
        """Initialize.

        Args:
            scene: The canvas scene.
            original_polygon: The polygon being trimmed (currently in scene).
            result_polyline: Open polyline wrapping the remaining perimeter.
        """
        self._scene = scene
        self._polygon = original_polygon
        self._polyline = result_polyline

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Trim polygon edge")

    def execute(self) -> None:
        if self._polygon.scene() is not None:
            self._scene.removeItem(self._polygon)
        if self._polyline.scene() is None:
            self._scene.addItem(self._polyline)

    def undo(self) -> None:
        if self._polyline.scene() is not None:
            self._scene.removeItem(self._polyline)
        if self._polygon.scene() is None:
            self._scene.addItem(self._polygon)


class TrimRectangleCommand(TrimPolygonCommand):
    """Trim a rectangle edge, replacing the RectangleItem with an open PolylineItem."""

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Trim rectangle edge")


class ExtendPolylineCommand(Command):
    """Extend a PolylineItem endpoint to a new point (item-local coordinates)."""

    def __init__(
        self,
        item: QGraphicsItem,
        endpoint_index: int,
        new_end_local: QPointF,
    ) -> None:
        """Initialize.

        Args:
            item: The PolylineItem to extend.
            endpoint_index: 0 to prepend to start, -1 (or last index) to append to end.
            new_end_local: New endpoint in item-local coordinates.
        """
        self._item = item
        self._endpoint_index = endpoint_index
        self._new_end = new_end_local
        self._old_points: list[QPointF] = item.points  # type: ignore[attr-defined]

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Extend polyline")

    def execute(self) -> None:
        pts = self._item.points  # type: ignore[attr-defined]
        if self._endpoint_index == 0:
            pts.insert(0, self._new_end)
        else:
            pts.append(self._new_end)
        self._item._points = pts  # type: ignore[attr-defined]
        self._item._rebuild_path()  # type: ignore[attr-defined]

    def undo(self) -> None:
        self._item._points = list(self._old_points)  # type: ignore[attr-defined]
        self._item._rebuild_path()  # type: ignore[attr-defined]


# ────────────────────────────────────────────────────────────────────────────
# Fillet / Chamfer corner commands (Phase 13 Package B — US-B3)
# ────────────────────────────────────────────────────────────────────────────


class FilletCornerCommand(Command):
    """Round one corner of a polyline / polygon / rectangle with a tangent arc.

    Execute:
        - Polyline / polygon: replace the corner vertex with the two tangent
          points; spawn a separate ``ArcItem`` for the rounded fillet.
        - Rectangle: convert to a 5-vertex polygon (one corner becomes two
          tangent points); spawn the arc. On undo the rectangle is restored
          unchanged.

    The arc itself is created externally and passed in already-built so the
    command stays pure-Python and doesn't depend on Qt geometry calls during
    undo/redo.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        original_item: QGraphicsItem,
        new_item: QGraphicsItem,
        arc_item: QGraphicsItem,
    ) -> None:
        """Initialize.

        Args:
            scene: Canvas scene.
            original_item: The polyline / polygon / rectangle being modified.
            new_item: Replacement item carrying the corner-split vertex list.
                For polylines / polygons this is a fresh ``PolylineItem`` /
                ``PolygonItem`` with the same styling. For rectangles it is
                a ``PolygonItem`` (the destructive rect→polygon conversion).
            arc_item: Pre-built ``ArcItem`` representing the fillet arc.
        """
        self._scene = scene
        self._original = original_item
        self._new = new_item
        self._arc = arc_item

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Fillet corner")

    def execute(self) -> None:
        if self._original.scene() is not None:
            self._scene.removeItem(self._original)
        if self._new.scene() is None:
            self._scene.addItem(self._new)
        if self._arc.scene() is None:
            self._scene.addItem(self._arc)

    def undo(self) -> None:
        if self._arc.scene() is not None:
            self._scene.removeItem(self._arc)
        if self._new.scene() is not None:
            self._scene.removeItem(self._new)
        if self._original.scene() is None:
            self._scene.addItem(self._original)


class ChamferCornerCommand(Command):
    """Bevel one corner of a polyline / polygon / rectangle with a straight cut.

    Like ``FilletCornerCommand`` but without an arc — the corner vertex is
    simply replaced by two cut-points so the two adjacent edges keep their
    direction and a new straight segment bridges them.
    """

    def __init__(
        self,
        scene: QGraphicsScene,
        original_item: QGraphicsItem,
        new_item: QGraphicsItem,
    ) -> None:
        self._scene = scene
        self._original = original_item
        self._new = new_item

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Chamfer corner")

    def execute(self) -> None:
        if self._original.scene() is not None:
            self._scene.removeItem(self._original)
        if self._new.scene() is None:
            self._scene.addItem(self._new)

    def undo(self) -> None:
        if self._new.scene() is not None:
            self._scene.removeItem(self._new)
        if self._original.scene() is None:
            self._scene.addItem(self._original)


class AddSoilTestCommand(Command):
    """Add a soil test record to a bed (or the global default) — undoable.

    Snapshots the prior history dict on construction so undo restores the
    exact pre-state (including absence of any history when this is the first
    record for the target).
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record: "Any",
    ) -> None:
        """Initialise.

        Args:
            project_manager: The ``ProjectManager`` holding the soil test state.
            target_id: Bed UUID string or the literal ``"global"``.
            record: A ``SoilTestRecord`` instance to append.
        """
        from open_garden_planner.models.soil_test import SoilTestHistory

        self._pm = project_manager
        self._target_id = target_id
        self._record = record
        self._SoilTestHistory = SoilTestHistory
        # Snapshot the prior history dict (or None if no history existed yet)
        existing = self._pm.soil_tests.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add soil test")

    def execute(self) -> None:
        # Build the new history from the prior snapshot (or fresh) + the new record
        if self._prior_history_dict is None:
            history = self._SoilTestHistory(target_id=self._target_id)
        else:
            history = self._SoilTestHistory.from_dict(self._prior_history_dict)
        if not any(r.id == self._record.id for r in history.records):
            history.records.append(self._record)
        self._pm.set_soil_test_history(self._target_id, history)

    def undo(self) -> None:
        # Restore (or delete) the prior snapshot
        self._pm.restore_soil_test_history(self._target_id, self._prior_history_dict)


class EditSoilTestCommand(Command):
    """Edit an existing soil test record — undoable (US-12.10 issue #171).

    Snapshots the prior history dict on construction so undo restores the
    exact pre-state. The record is matched by ``record.id``; if the id is
    not present, execute is a no-op (defensive — should not happen via UI).
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        new_record: "Any",
    ) -> None:
        from open_garden_planner.models.soil_test import SoilTestHistory

        self._pm = project_manager
        self._target_id = target_id
        self._new_record = new_record
        self._SoilTestHistory = SoilTestHistory
        existing = self._pm.soil_tests.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit soil test")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._SoilTestHistory.from_dict(self._prior_history_dict)
        for idx, r in enumerate(history.records):
            if r.id == self._new_record.id:
                history.records[idx] = self._new_record
                break
        else:
            return  # id not found; nothing to edit
        self._pm.set_soil_test_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.restore_soil_test_history(self._target_id, self._prior_history_dict)


class DeleteSoilTestCommand(Command):
    """Delete a soil test record from a bed's history — undoable (US-12.10 issue #171).

    Snapshots the prior history dict on construction so undo restores the
    deleted record at its original list position.
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record_id: str,
    ) -> None:
        from open_garden_planner.models.soil_test import SoilTestHistory

        self._pm = project_manager
        self._target_id = target_id
        self._record_id = record_id
        self._SoilTestHistory = SoilTestHistory
        existing = self._pm.soil_tests.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete soil test")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._SoilTestHistory.from_dict(self._prior_history_dict)
        history.records = [r for r in history.records if r.id != self._record_id]
        self._pm.set_soil_test_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.restore_soil_test_history(self._target_id, self._prior_history_dict)


class AddPestLogCommand(Command):
    """Add a pest/disease log record to a target — undoable (US-12.7).

    Snapshots the prior history dict on construction so undo restores the
    exact pre-state (including absence of any history when this is the first
    record for the target).
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record: "Any",
    ) -> None:
        from open_garden_planner.models.pest_log import PestLogHistory

        self._pm = project_manager
        self._target_id = target_id
        self._record = record
        self._PestLogHistory = PestLogHistory
        existing = self._pm.pest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add pest/disease log")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            history = self._PestLogHistory(target_id=self._target_id)
        else:
            history = self._PestLogHistory.from_dict(self._prior_history_dict)
        if not any(r.id == self._record.id for r in history.records):
            history.records.append(self._record)
        self._pm.set_pest_log_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.restore_pest_log_history(self._target_id, self._prior_history_dict)


class EditPestLogCommand(Command):
    """Edit an existing pest/disease log record — undoable (US-12.7).

    Matches the record by ``record.id``; if absent, execute is a no-op.
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        new_record: "Any",
    ) -> None:
        from open_garden_planner.models.pest_log import PestLogHistory

        self._pm = project_manager
        self._target_id = target_id
        self._new_record = new_record
        self._PestLogHistory = PestLogHistory
        existing = self._pm.pest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit pest/disease log")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._PestLogHistory.from_dict(self._prior_history_dict)
        for idx, r in enumerate(history.records):
            if r.id == self._new_record.id:
                history.records[idx] = self._new_record
                break
        else:
            return
        self._pm.set_pest_log_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.restore_pest_log_history(self._target_id, self._prior_history_dict)


class DeletePestLogCommand(Command):
    """Delete a pest/disease log record from a target's history — undoable (US-12.7)."""

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record_id: str,
    ) -> None:
        from open_garden_planner.models.pest_log import PestLogHistory

        self._pm = project_manager
        self._target_id = target_id
        self._record_id = record_id
        self._PestLogHistory = PestLogHistory
        existing = self._pm.pest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete pest/disease log")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._PestLogHistory.from_dict(self._prior_history_dict)
        history.records = [r for r in history.records if r.id != self._record_id]
        self._pm.set_pest_log_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.restore_pest_log_history(self._target_id, self._prior_history_dict)


def _harvest_note_text(record: "Any", species_name: str) -> str:
    """Build the summary text for a harvest's linked journal note (US-C1)."""
    qty = f"{record.quantity:g}"
    if species_name:
        return QCoreApplication.translate(
            "HarvestJournal", "Harvested {qty} {unit} of {name}"
        ).format(qty=qty, unit=record.unit, name=species_name)
    return QCoreApplication.translate(
        "HarvestJournal", "Harvested {qty} {unit}"
    ).format(qty=qty, unit=record.unit)


class AddHarvestRecordCommand(Command):
    """Add a harvest record to a target — undoable (US-C1, #188).

    Snapshots the prior history dict so undo restores the exact pre-state. Also
    creates a pin-less garden-journal note tagged ``harvest`` summarising the
    entry, so the harvest surfaces in the journal without dropping a canvas pin.
    Undo removes both the record and its linked note.
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record: "Any",
        species_key: str = "",
        species_name: str = "",
    ) -> None:
        from open_garden_planner.models.harvest_log import HarvestHistory
        from open_garden_planner.models.journal_note import JournalNote

        self._pm = project_manager
        self._target_id = target_id
        self._record = record
        self._species_key = species_key
        self._species_name = species_name
        self._HarvestHistory = HarvestHistory
        existing = self._pm.harvest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )
        # Build the linked pin-less journal note once so redo re-applies the
        # same note (and undo can delete it by id).
        note = JournalNote(
            date=record.date,
            text=_harvest_note_text(record, species_name),
            tags=["harvest"],
        )
        self._note = note
        record.journal_note_id = note.id

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add harvest entry")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            history = self._HarvestHistory(target_id=self._target_id)
        else:
            history = self._HarvestHistory.from_dict(self._prior_history_dict)
        if self._species_key:
            history.species_key = self._species_key
        if self._species_name:
            history.species_name = self._species_name
        if not any(r.id == self._record.id for r in history.records):
            history.records.append(self._record)
        self._pm.set_journal_note(self._note)
        self._pm.set_harvest_history(self._target_id, history)

    def undo(self) -> None:
        self._pm.delete_journal_note(self._note.id)
        self._pm.restore_harvest_history(self._target_id, self._prior_history_dict)


class EditHarvestRecordCommand(Command):
    """Edit an existing harvest record — undoable (US-C1).

    Matches the record by ``record.id``; if absent, execute is a no-op. Keeps
    the linked journal note's date + summary text in sync.
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        new_record: "Any",
    ) -> None:
        from open_garden_planner.models.harvest_log import HarvestHistory

        self._pm = project_manager
        self._target_id = target_id
        self._new_record = new_record
        self._HarvestHistory = HarvestHistory
        existing = self._pm.harvest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )
        self._note_id: str | None = new_record.journal_note_id
        prior_note = (
            self._pm.garden_journal_notes.get(self._note_id) if self._note_id else None
        )
        self._prior_note_dict: dict[str, Any] | None = (
            dict(prior_note) if prior_note is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit harvest entry")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._HarvestHistory.from_dict(self._prior_history_dict)
        for idx, r in enumerate(history.records):
            if r.id == self._new_record.id:
                history.records[idx] = self._new_record
                break
        else:
            return
        self._pm.set_harvest_history(self._target_id, history)
        if self._note_id:
            note = self._pm.get_journal_note(self._note_id)
            if note is not None:
                note.date = self._new_record.date
                note.text = _harvest_note_text(
                    self._new_record, history.species_name
                )
                self._pm.set_journal_note(note)

    def undo(self) -> None:
        self._pm.restore_harvest_history(self._target_id, self._prior_history_dict)
        if self._note_id:
            self._pm.restore_journal_note(self._note_id, self._prior_note_dict)


class DeleteHarvestRecordCommand(Command):
    """Delete a harvest record from a target's history — undoable (US-C1).

    Also removes the record's linked journal note. Undo restores both.
    """

    def __init__(
        self,
        project_manager: "Any",
        target_id: str,
        record_id: str,
    ) -> None:
        from open_garden_planner.models.harvest_log import HarvestHistory

        self._pm = project_manager
        self._target_id = target_id
        self._record_id = record_id
        self._HarvestHistory = HarvestHistory
        existing = self._pm.harvest_logs.get(target_id)
        self._prior_history_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )
        # Find the linked journal note id from the prior snapshot.
        self._note_id: str | None = None
        self._prior_note_dict: dict[str, Any] | None = None
        if self._prior_history_dict is not None:
            for raw in self._prior_history_dict.get("records", []):
                if raw.get("id") == record_id:
                    self._note_id = raw.get("journal_note_id")
                    break
            if self._note_id:
                prior_note = self._pm.garden_journal_notes.get(self._note_id)
                self._prior_note_dict = (
                    dict(prior_note) if prior_note is not None else None
                )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete harvest entry")

    def execute(self) -> None:
        if self._prior_history_dict is None:
            return
        history = self._HarvestHistory.from_dict(self._prior_history_dict)
        history.records = [r for r in history.records if r.id != self._record_id]
        if history.records:
            self._pm.set_harvest_history(self._target_id, history)
        else:
            # Drop the whole key rather than leave a phantom empty history.
            self._pm.restore_harvest_history(self._target_id, None)
        if self._note_id:
            self._pm.delete_journal_note(self._note_id)

    def undo(self) -> None:
        self._pm.restore_harvest_history(self._target_id, self._prior_history_dict)
        if self._note_id:
            self._pm.restore_journal_note(self._note_id, self._prior_note_dict)


class SetSuccessionPlanCommand(Command):
    """Replace the succession plan for a bed atomically — undoable (US-12.8).

    Snapshots the prior plan dict on construction so undo restores the
    previous state exactly. ``new_plan`` is a ``SuccessionPlan`` instance;
    passing ``None`` deletes the plan for the bed.
    """

    def __init__(
        self,
        project_manager: "Any",
        bed_id: str,
        new_plan: "Any",  # SuccessionPlan | None
    ) -> None:
        self._pm = project_manager
        self._bed_id = bed_id
        self._new: dict[str, Any] | None = (
            new_plan.to_dict() if new_plan is not None else None
        )
        existing = self._pm.succession_plans.get(bed_id)
        self._old: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Set succession plan")

    def execute(self) -> None:
        if self._new is None:
            self._pm.restore_succession_plan(self._bed_id, None)
        else:
            self._pm.set_succession_plan(self._bed_id, self._new)

    def undo(self) -> None:
        self._pm.restore_succession_plan(self._bed_id, self._old)


class AddJournalNoteCommand(Command):
    """Place a garden journal pin and persist its note dict — undoable (US-12.9).

    Holds a reference to the pre-built :class:`JournalPinItem` so undo/redo
    cycle the same Qt object in and out of the scene rather than recreating
    it (matching :class:`CreateItemCommand`). The ``JournalNote`` body is
    stored on the project manager via ``set_journal_note``.
    """

    def __init__(
        self,
        project_manager: "Any",
        scene: QGraphicsScene,
        pin_item: "Any",   # JournalPinItem
        note: "Any",       # JournalNote
    ) -> None:
        self._pm = project_manager
        self._scene = scene
        self._pin = pin_item
        self._note = note

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add garden journal note")

    def execute(self) -> None:
        if self._pin.scene() is None:
            self._scene.addItem(self._pin)
        self._pm.set_journal_note(self._note)

    def undo(self) -> None:
        self._pm.delete_journal_note(self._note.id)
        if self._pin.scene() is not None:
            self._scene.removeItem(self._pin)


class EditJournalNoteCommand(Command):
    """Edit an existing journal note — undoable (US-12.9).

    Snapshots the prior note dict on construction so undo restores it
    field-for-field. If the note no longer exists at execute-time the
    command is a no-op.
    """

    def __init__(
        self,
        project_manager: "Any",
        new_note: "Any",   # JournalNote
    ) -> None:
        self._pm = project_manager
        self._new_note = new_note
        existing = self._pm.garden_journal_notes.get(new_note.id)
        self._old_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit garden journal note")

    def execute(self) -> None:
        if self._old_dict is None:
            return
        self._pm.set_journal_note(self._new_note)

    def undo(self) -> None:
        self._pm.restore_journal_note(self._new_note.id, self._old_dict)


class DeleteJournalNoteCommand(Command):
    """Remove a journal pin and its note dict — undoable (US-12.9)."""

    def __init__(
        self,
        project_manager: "Any",
        scene: QGraphicsScene,
        pin_item: "Any",   # JournalPinItem
    ) -> None:
        self._pm = project_manager
        self._scene = scene
        self._pin = pin_item
        self._note_id = pin_item.note_id
        existing = self._pm.garden_journal_notes.get(self._note_id)
        self._old_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete garden journal note")

    def execute(self) -> None:
        self._pm.delete_journal_note(self._note_id)
        if self._pin.scene() is not None:
            self._scene.removeItem(self._pin)

    def undo(self) -> None:
        if self._old_dict is not None:
            self._pm.restore_journal_note(self._note_id, self._old_dict)
        if self._pin.scene() is None:
            self._scene.addItem(self._pin)


class AddManualTaskCommand(Command):
    """Add a manual task — undoable (US-C2, #188).

    Snapshots any prior task with the same id on construction so undo restores
    the exact pre-state (normally absence, for a brand-new task).
    """

    def __init__(self, project_manager: "Any", task: "Any") -> None:
        self._pm = project_manager
        self._task = task
        existing = self._pm.manual_tasks.get(task.id)
        self._prior_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Add task")

    def execute(self) -> None:
        self._pm.set_manual_task(self._task)

    def undo(self) -> None:
        self._pm.restore_manual_task(self._task.id, self._prior_dict)


class EditManualTaskCommand(Command):
    """Edit an existing manual task — undoable (US-C2, #188)."""

    def __init__(self, project_manager: "Any", new_task: "Any") -> None:
        self._pm = project_manager
        self._new_task = new_task
        existing = self._pm.manual_tasks.get(new_task.id)
        self._prior_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Edit task")

    def execute(self) -> None:
        self._pm.set_manual_task(self._new_task)

    def undo(self) -> None:
        self._pm.restore_manual_task(self._new_task.id, self._prior_dict)


class DeleteManualTaskCommand(Command):
    """Delete a manual task — undoable (US-C2, #188)."""

    def __init__(self, project_manager: "Any", task_id: str) -> None:
        self._pm = project_manager
        self._task_id = task_id
        existing = self._pm.manual_tasks.get(task_id)
        self._prior_dict: dict[str, Any] | None = (
            dict(existing) if existing is not None else None
        )

    @property
    def description(self) -> str:
        return QCoreApplication.translate("Commands", "Delete task")

    def execute(self) -> None:
        self._pm.delete_manual_task(self._task_id)

    def undo(self) -> None:
        self._pm.restore_manual_task(self._task_id, self._prior_dict)


# Commands whose effect cannot change an item's ground band (#592). Every one of
# them moves, resizes, rotates, edits vertices/curves, copies, links/reparents,
# or changes constraints: ``canvas_scene.on_ground`` reads the item's object
# type, height metadata and group membership, none of which these touch. The
# base default stays True, so a future command is safe until it says otherwise.
# Create is neutral because `addItem` derives a ground surface's band
# synchronously and bulk adds end in `_update_items_z_order`; Delete/Group/
# Ungroup/Boolean/ChangeProperty keep the scan.
_GROUND_BAND_NEUTRAL_COMMANDS: tuple[type[Command], ...] = (
    CreateItemCommand,
    CreateItemsCommand,
    MoveItemsCommand,
    AlignItemsCommand,
    ResizeItemCommand,
    RotateItemCommand,
    MoveVertexCommand,
    SetCurveGeometryCommand,
    AddVertexCommand,
    DeleteVertexCommand,
    MultiVertexMoveCommand,
    LinearArrayCommand,
    GridArrayCommand,
    CircularArrayCommand,
    ArrayAlongPathCommand,
    MirrorItemsCommand,
    SetParentBedCommand,
    AddConstraintCommand,
    RemoveConstraintCommand,
    EditConstraintDistanceCommand,
)
for _ground_band_neutral in _GROUND_BAND_NEUTRAL_COMMANDS:
    _ground_band_neutral.changes_ground_band = False

#: Commands that cannot change which plant-parent contains a plant (#629): an add is
#: derived synchronously by `addItem` and a delete cannot hide anything.
CONTAINMENT_NEUTRAL_COMMANDS = (CreateItemCommand, CreateItemsCommand, DeleteItemsCommand)
for _containment_neutral in CONTAINMENT_NEUTRAL_COMMANDS:
    _containment_neutral.changes_containment = False
