"""Group item: a logical container for grouping multiple canvas items."""

from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QTransform
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsScene,
    QGraphicsSceneContextMenuEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .garden_item import GardenItemMixin
from .handle_geometry import selection_frame_rect
from .resize_handle import RotationHandleMixin


def groupable_selection(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """The selection ``Ctrl+G`` acts on (issue #674).

    Only TOP-LEVEL items are group members. Qt keeps a group's children flagged
    selected while the group is selected, so ``scene.selectedItems()`` right
    after a grouping gesture returns the new group *and its members*; counting
    the members would offer Group on a single selected group and a second
    grouping would empty the first (PF-CAN-36). The background image is a
    backdrop, not a plan object: grouping it re-bands it above ground surfaces
    and breaks the z-order, so it is deliberately not groupable.

    A derived ``ROOF_RIDGE`` is owned by its HOUSE and cannot be grouped
    independently (issue #712).
    """
    from open_garden_planner.core.object_types import ObjectType

    from .background_image_item import BackgroundImageItem

    return [
        item
        for item in items
        if item.parentItem() is None
        and not isinstance(item, BackgroundImageItem)
        and getattr(item, "object_type", None) is not ObjectType.ROOF_RIDGE
    ]


def top_level_selection(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """The selection with every group child removed.

    Qt keeps a group's children flagged selected while the group is selected, so
    a bulk action that asks ``scene.selectedItems()`` would move or delete the
    group AND each member again (a member moved twice; a delete/undo that
    restores children as top-level items and empties the group). Every
    selection-wide action filters here first (PF-CAN-36).
    """
    return [item for item in items if item.parentItem() is None]


def selection_tree(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """The items plus every Qt child, once each, parents before children.

    Derived links and graph references live on items a group hides from the
    top-level selection (a nested HOUSE's ridge, a child's constraint, a
    journal pin). Every delete/move path that must account for them walks this
    one tree instead of inventing its own recursion.
    """
    result: list[QGraphicsItem] = []
    pending = list(items)
    seen: set[int] = set()
    while pending:
        item = pending.pop()
        if id(item) in seen:
            continue
        seen.add(id(item))
        result.append(item)
        pending.extend(item.childItems())
    return result


def ungroupable_groups(items: list[QGraphicsItem]) -> list[GroupItem]:
    """The selected groups ``Ctrl+Shift+G`` may dissolve.

    Only TOP-LEVEL groups are dissolved: Qt can keep a just-grouped child group
    flagged selected inside its new parent, and ungrouping one gesture must not
    silently cascade into the nested levels the issue documents as a second
    deliberate step. A turned group is not a valid target: its members' saved
    own angles cannot reproduce the composed Qt matrix (#1022).
    """
    return [
        item
        for item in items
        if isinstance(item, GroupItem)
        and item.parentItem() is None
        and not item.is_turned()
    ]


def is_drillable_group(item: QGraphicsItem) -> bool:
    """Whether a second click may reach *item*'s members (#771)."""
    return isinstance(item, GroupItem)


def group_child_at(
    scene: QGraphicsScene,
    group: QGraphicsItem,
    scene_pos: QPointF,
) -> QGraphicsItem | None:
    """The IMMEDIATE child of *group* under *scene_pos*, if any.

    ``scene.items()`` returns a child, its label or a drag handle first. Walking
    up to the first item whose parent is *group* answers "which member did the
    user click?", so a click anywhere inside a nested group drills to that
    nested group rather than jumping straight to its deepest member. Non-document
    children (labels, badges, resize handles) have no ``item_id`` and are
    skipped; a handle click must keep its normal resize meaning.
    """
    if scene is None or group.scene() is not scene:
        return None
    from .resize_handle import DRAG_HANDLE_TYPES

    for candidate in scene.items(scene_pos):
        if candidate is group:
            continue
        if isinstance(candidate, DRAG_HANDLE_TYPES):
            # The handle's own press must keep its resize/rotate meaning.
            return None
        node: QGraphicsItem | None = candidate
        while node is not None and node is not group:
            parent = node.parentItem()
            if parent is group:
                if isinstance(node, DRAG_HANDLE_TYPES):
                    return None
                if getattr(node, "item_id", None) is None:
                    return None
                return node
            if isinstance(node, DRAG_HANDLE_TYPES):
                return None
            node = parent
    return None


class GroupItem(RotationHandleMixin, GardenItemMixin, QGraphicsItemGroup):
    """A group of canvas items that move, copy, and rotate together.

    Items inside a group lose individual selectability/movability; the group
    is the single unit for all interactions.  Nested groups are supported.
    """

    def __init__(
        self,
        layer_id: uuid.UUID | None = None,
        name: str = "",
    ) -> None:
        GardenItemMixin.__init__(
            self,
            object_type=None,
            name=name,
            layer_id=layer_id,
        )
        QGraphicsItemGroup.__init__(self)
        self.init_rotation_handle()
        #: True once a pivot has been chosen (a turn or a loaded file). The
        #: pivot is NOT recomputed from the angle: a member edit can move the
        #: frame centre, and re-pivoting would shift every member (#1022).
        self._pivot_initialized = False
        self._gesture_pivot: QPointF | None = None
        self._rotation_plan_active = False
        self._rotation_followers: list[tuple[QGraphicsItem, QPointF, QPointF, float, float]] = []
        #: The pivot state entering the current gesture; the command restores it
        #: on undo so a reverted turn cannot leave a new saved pivot behind.
        self._pivot_state_before: tuple[bool, QPointF] | None = None
        #: The member that currently has drill-down edit focus (#771). Drawn as
        #: a solid inner outline, so a second click inside a selected group has
        #: a visible target. Never serialized.
        self._drill_down_child: QGraphicsItem | None = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        """A group that moves, turns or is hidden moves, turns and hides its
        members — and Qt tells THEM nothing (their own position did not change):
        the group announces it (``garden_item.handle_item_change``)."""
        self.handle_item_change(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if value:
                self.show_rotation_handle()
            else:
                self.hide_rotation_handle()
        elif change == QGraphicsItem.GraphicsItemChange.ItemSceneChange and value is None:
            self.remove_rotation_handle()
        if change in (
            QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemTransformHasChanged,
            QGraphicsItem.GraphicsItemChange.ItemRotationHasChanged,
        ):
            # A member's local pos does not change when the group moves, so its
            # free-standing ridge has to be re-derived from the new scene
            # transform (PF-CAN-34; review P2 of #690).
            from ..roof_ridge_link import update_house_ridges_under

            update_house_ridges_under(self)
            if self.isSelected():
                self.update_rotation_handle()
        return super().itemChange(change, value)

    # ------------------------------------------------------------------
    # Rotation (#1022)
    # ------------------------------------------------------------------

    @staticmethod
    def _carried_pose(
        start_centre: QPointF,
        start_angle: float,
        delta: float,
        pivot: QPointF,
    ) -> tuple[QPointF, float]:
        """One formula for a carried item's scene centre and angle.

        Shared by the live gesture and by the command's before/after snapshot
        so the two can never drift (#1022 review).
        """
        rotation = QTransform()
        rotation.rotate(delta)
        return pivot + rotation.map(start_centre - pivot), start_angle + delta

    def _apply_rotation(self, angle: float) -> None:
        """Turn the whole group about its own outline centre.

        The pivot is the union of the members' outlines in the group's local
        frame, never ``boundingRect().center()``: a screen-sized handle or a
        label widens the paint bounds asymmetrically and would drag the
        composed arrangement sideways. Children keep their local positions;
        Qt's group transform is what rotates their scene positions together.
        """
        if not self._pivot_initialized:
            self.setTransformOriginPoint(selection_frame_rect(self).center())
            self._pivot_initialized = True
        pivot = self._gesture_pivot or self.rotation_pivot_scene()
        delta = angle - float(getattr(self, "_rotation_initial_angle", 0.0))
        for follower, start_center, _before, start_angle, _after in self._rotation_followers:
            rect_fn = getattr(follower, "rect", None)
            if not callable(rect_fn):
                continue
            centre, carried_angle = self._carried_pose(
                start_center, start_angle, delta, pivot
            )
            if hasattr(follower, "_apply_rotation"):
                follower._apply_rotation(carried_angle)
            follower.setPos(centre - rect_fn().center())
        self._rotation_angle = angle
        self.setRotation(angle)
        self.update_rotation_handle()
        self._position_label()

    def is_turned(self) -> bool:
        """Whether the group's angle is not a whole 360° multiple (#1022)."""
        angle = float(getattr(self, "rotation_angle", self.rotation()))
        normalized = angle % 360.0
        return min(normalized, 360.0 - normalized) > 1e-6

    def rotation_pivot_scene(self) -> QPointF:
        """The scene point a gesture turns about: the saved pivot once chosen."""
        if self._pivot_initialized:
            return self.mapToScene(self.transformOriginPoint())
        return self.mapToScene(selection_frame_rect(self).center())

    def rotation_pivot_change(
        self,
    ) -> tuple[tuple[bool, QPointF], tuple[bool, QPointF]] | None:
        """The pivot state before and after the current gesture, if any.

        ``RotateItemCommand`` records both sides so undo cannot leave a pivot
        the reverted turn introduced (#1022 review).
        """
        if self._pivot_state_before is None:
            return None
        after = (self._pivot_initialized, QPointF(self.transformOriginPoint()))
        return (self._pivot_state_before, after)

    def restore_rotation_pivot(self, state: tuple[bool, QPointF]) -> None:
        """Put the pivot back to a recorded state (undo/redo/no-op gesture)."""
        initialized, origin = state
        self._pivot_initialized = bool(initialized)
        self.setTransformOriginPoint(QPointF(origin))

    def rotation_targets(self) -> list[QGraphicsItem]:
        """Everything a turn moves: the Qt subtree plus grouped beds' plants.

        Linked plants are top-level items, so they are not in the subtree but
        the gesture and its command carry them. This is the one set both the
        constraint refusal and the follower capture use.
        """
        targets = selection_tree([self])
        scene = self.scene()
        find = getattr(scene, "find_item_by_id", None) if scene is not None else None
        if not callable(find):
            return targets
        from open_garden_planner.core.commands import iter_plant_parents

        seen = {id(item) for item in targets}
        for parent in iter_plant_parents([self]):
            for child_id in getattr(parent, "child_item_ids", ()):
                item = find(child_id)
                if (
                    item is not None
                    and id(item) not in seen
                    and item.parentItem() is None
                    and callable(getattr(item, "rect", None))
                ):
                    targets.append(item)
                    seen.add(id(item))
        return targets

    def rotation_refusal_reason(self) -> str | None:
        """Why a turn would violate an affected item's constraint or lock."""
        from PyQt6.QtCore import QCoreApplication

        scene = self.scene()
        if scene is None:
            return None
        graph = getattr(scene, "constraint_graph", None)
        subtree = {id(entry) for entry in selection_tree([self])}
        find = getattr(scene, "find_item_by_id", None)
        if callable(find):
            from open_garden_planner.core.commands import iter_plant_parents

            for parent in iter_plant_parents([self]):
                for child_id in getattr(parent, "child_item_ids", ()):
                    item = find(child_id)
                    if item is None or item.parentItem() is None:
                        continue
                    if id(item.parentItem()) not in subtree:
                        return QCoreApplication.translate(
                            "GroupItem",
                            "A linked plant belongs to another group; "
                            "remove it from that group before turning this one",
                        )
        targets = self.rotation_targets()
        for item in targets:
            item_id = getattr(item, "item_id", None)
            if (
                graph is not None
                and item_id is not None
                and graph.get_item_constraints(item_id)
            ):
                return QCoreApplication.translate(
                    "GroupItem",
                    "A constrained member cannot be rotated with the group",
                )
        get_layer = getattr(scene, "get_layer_by_id", None)
        if callable(get_layer):
            for item in targets:
                layer_id = getattr(item, "layer_id", None)
                if layer_id is None:
                    continue
                layer = get_layer(layer_id)
                if layer is not None and bool(getattr(layer, "locked", False)):
                    return QCoreApplication.translate(
                        "GroupItem",
                        "A member on a locked layer cannot be rotated with the group",
                    )
        return None

    def begin_rotation_plan(self) -> None:
        """Capture the pivot, start angle and carried plants for a turn.

        Called by the handle gesture and by the Agent API before one command.
        Idempotent within a live gesture: a second call does not recapture the
        followers after they have already moved.
        """
        if self._rotation_plan_active:
            return
        self._rotation_initial_angle = float(self._rotation_angle)
        self._gesture_pivot = self.rotation_pivot_scene()
        self._pivot_state_before = (
            self._pivot_initialized,
            QPointF(self.transformOriginPoint()),
        )
        self._rotation_followers = []
        for item in self.rotation_targets():
            if item is self or item.parentItem() is not None:
                continue
            rect_fn = getattr(item, "rect", None)
            if not callable(rect_fn):
                continue
            centre = item.mapToScene(rect_fn().center())
            angle = float(getattr(item, "rotation_angle", item.rotation()))
            self._rotation_followers.append(
                (item, QPointF(centre), QPointF(item.pos()), angle, angle)
            )
        self._rotation_plan_active = True

    def rotation_follower_snapshots(
        self, angle: float | None = None
    ) -> list[tuple[QGraphicsItem, QPointF, QPointF, float, float]]:
        """The carried items as ``(item, before, after, old angle, new angle)``.

        With *angle*, the after-pose is computed from the captured start pose
        (the Agent API path, before the command has run); without it, the live
        poses after a handle gesture are read.
        """
        followers: list[tuple[QGraphicsItem, QPointF, QPointF, float, float]] = []
        delta = 0.0
        pivot = self._gesture_pivot or self.rotation_pivot_scene()
        if angle is not None:
            delta = angle - float(getattr(self, "_rotation_initial_angle", 0.0))
        for item, start_centre, before, start_angle, _after in self._rotation_followers:
            if angle is None:
                after = QPointF(item.pos())
                new_angle = float(getattr(item, "rotation_angle", item.rotation()))
            else:
                rect_fn = getattr(item, "rect", None)
                if not callable(rect_fn):
                    continue
                centre, new_angle = self._carried_pose(
                    start_centre, start_angle, delta, pivot
                )
                after = QPointF(centre - rect_fn().center())
            if after != before or abs(new_angle - start_angle) > 0.01:
                followers.append((item, before, after, start_angle, new_angle))
        return followers

    def finish_rotation_plan(self) -> None:
        """Drop the live plan; the command owns the recorded poses afterwards."""
        self._rotation_followers = []
        self._gesture_pivot = None
        self._rotation_plan_active = False
        self._pivot_state_before = None

    def _on_rotation_start(self) -> None:
        """Capture the pivot and the linked plants a turn must carry (#1022)."""
        super()._on_rotation_start()
        self.begin_rotation_plan()

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Register the finished group rotation and its carried plants (#1022)."""
        from open_garden_planner.ui.canvas.geometry_apply import (
            register_rotation_command,
        )

        followers = self.rotation_follower_snapshots()
        registered = register_rotation_command(self, initial_angle, followers or None)
        if not registered and self._pivot_state_before is not None:
            # A radial drag that ends where it started must not leave a new
            # saved pivot behind: no command means no undo state to carry it.
            self.restore_rotation_pivot(self._pivot_state_before)
        self.finish_rotation_plan()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,  # noqa: ARG002
        widget: QWidget | None = None,  # noqa: ARG002
    ) -> None:
        """Draw a subtle dashed outline around the group bounding rect."""
        rect = self.childrenBoundingRect()
        if rect.isEmpty():
            return

        # Expand slightly so the outline doesn't clip the children
        rect = rect.adjusted(-2, -2, 2, 2)

        if self.isSelected():
            pen = QPen(QColor(60, 130, 200), 1.5, Qt.PenStyle.DashLine)
        else:
            pen = QPen(QColor(100, 140, 200, 80), 1, Qt.PenStyle.DotLine)

        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

        # Drill-down focus (#771): one member is the edit target while the
        # group stays the Qt selection. The outline disappears with the
        # selection, so exports (which clear it first) never paint it.
        child = self._drill_down_child
        if self.isSelected() and child is not None:
            try:
                if child.scene() is self.scene():
                    focus_rect = self.mapFromScene(child.sceneBoundingRect()).boundingRect()
                    painter.setPen(QPen(QColor(25, 120, 220), 2.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(focus_rect)
            except RuntimeError:
                # The focused member was deleted by an undo/redo between the
                # selection change and this paint.
                pass

    def set_drill_down_child(self, child: QGraphicsItem | None) -> None:
        """Draw *child* as the drill-down focus, or clear it (#771)."""
        if self._drill_down_child is child:
            return
        self._drill_down_child = child
        self.update()

    def addToGroup(self, item: QGraphicsItem) -> None:  # type: ignore[override]
        """Add a member and keep a visible rotation handle on the new outline."""
        super().addToGroup(item)
        if self.isSelected():
            self.update_rotation_handle()

    def removeFromGroup(self, item: QGraphicsItem) -> None:  # type: ignore[override]
        """Remove a member and keep a visible rotation handle on the new outline."""
        super().removeFromGroup(item)
        if self.isSelected():
            self.update_rotation_handle()

    def childrenBoundingRect(self) -> QRectF:
        """Return union of non-screen-space descendant bounds (#919).

        ``PlanLabelItem`` keeps ``ItemIgnoresTransformations`` in Python so Qt's
        BSP tree stays active. Excluding screen-space descendants here prevents
        pixel-sized labels from inflating ``GroupItem`` bounds, selection
        frames, or ``scene.itemAt`` hit-testing.
        """
        ignore_flag = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
        bounds = QRectF()
        stack = list(self.childItems())
        while stack:
            child = stack.pop()
            if getattr(child, "_ignores_transformations", False) or bool(
                child.flags() & ignore_flag
            ):
                continue
            rect = child.boundingRect()
            if not rect.isEmpty():
                mapped = child.mapRectToItem(self, rect)
                bounds = mapped if bounds.isEmpty() else bounds.united(mapped)
            stack.extend(child.childItems())
        return bounds

    def boundingRect(self) -> QRectF:
        """Return children bounding rect with a small margin."""
        return self.childrenBoundingRect().adjusted(-4, -4, 4, 4)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show Group / Ungroup for the current selection (issues #674, #338)."""
        self.normalize_context_menu_selection()
        menu = QMenu()
        group_actions = self.build_group_context_menu(menu)
        if group_actions.offered:
            menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        # Arrange submenu (Bring to Front / Forward / Send Backward / Back)
        arrange_menu = self._build_arrange_menu(menu)

        action = menu.exec(event.screenPos())
        if self.dispatch_group_action(action, group_actions):
            return
        if move_layer_menu and action and action.parent() is move_layer_menu:
            self._dispatch_move_to_layer(action.data())
        elif arrange_menu and action and action.parent() is arrange_menu:
            self._dispatch_arrange(action.data())
