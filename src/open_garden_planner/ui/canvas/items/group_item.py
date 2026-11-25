"""Group item: a logical container for grouping multiple canvas items."""

from __future__ import annotations

import math
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
    deliberate step.
    """
    return [
        item
        for item in items
        if isinstance(item, GroupItem) and item.parentItem() is None
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


def bake_inherited_rotation(
    item: QGraphicsItem,
    *,
    scene_transform: QTransform | None = None,
    old_origin: QPointF | None = None,
) -> None:
    """Move a parent group's rotation into *item*'s own angle (#1022 review).

    ``QGraphicsItemGroup.removeFromGroup`` keeps the child's scene transform by
    leaving the group's rotation in the child's Qt transform matrix. The file
    format stores a member's own ``rotation_angle``, not that matrix, so an
    ungrouped nonsquare rectangle would look right until the next save/reload.
    This rewrites the composed rotation as the item's own rotation about its
    outline centre and translates it so every point keeps its scene position.

    Call it BEFORE ``removeFromGroup`` when the parent transform is still in
    place (the default reads it), or pass the captured ``scene_transform`` and
    ``old_origin`` after removal.
    """
    if getattr(item, "item_id", None) is None:
        return
    if scene_transform is None:
        scene_transform = item.sceneTransform()
    if old_origin is None:
        old_origin = item.scenePos()
    angle = math.degrees(math.atan2(scene_transform.m12(), scene_transform.m11()))
    if abs(angle) < 1e-6:
        return
    apply_rotation = getattr(item, "_apply_rotation", None)
    if not callable(apply_rotation):
        return
    centre = selection_frame_rect(item).center()
    # `removeFromGroup` leaves the group's rotation in the item's Qt transform;
    # replace that matrix with the item's own rotation before applying it.
    item.setTransform(QTransform())
    apply_rotation(angle)
    rotation = QTransform()
    rotation.rotate(angle)
    item.setPos(old_origin + rotation.map(centre) - centre)
    if hasattr(item, "set_drill_down_child"):
        item.set_drill_down_child(None)


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

    def _apply_rotation(self, angle: float) -> None:
        """Turn the whole group about its own outline centre.

        The pivot is the union of the members' outlines in the group's local
        frame, never ``boundingRect().center()``: a screen-sized handle or a
        label widens the paint bounds asymmetrically and would drag the
        composed arrangement sideways. Children keep their local positions;
        Qt's group transform is what rotates their scene positions together.
        """
        if abs(self._rotation_angle) < 1e-9 and abs(self.rotation()) < 1e-9:
            # The pivot is fixed at the first turn. A later member edit can move
            # the frame centre; re-pivoting then would silently shift every
            # member, and the saved transform would no longer reproduce itself.
            self.setTransformOriginPoint(selection_frame_rect(self).center())
        self._rotation_angle = angle
        self.setRotation(angle)
        self.update_rotation_handle()
        self._position_label()

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Register the finished group rotation as one undo step (#1022)."""
        from open_garden_planner.ui.canvas.geometry_apply import (
            register_rotation_command,
        )

        register_rotation_command(self, initial_angle)

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
