"""Group item: a logical container for grouping multiple canvas items."""

from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsSceneContextMenuEvent,
    QMenu,
    QStyleOptionGraphicsItem,
    QWidget,
)

from .garden_item import GardenItemMixin


def groupable_selection(items: list[QGraphicsItem]) -> list[QGraphicsItem]:
    """The selection ``Ctrl+G`` acts on (issue #674).

    Only TOP-LEVEL items are group members. Qt keeps a group's children flagged
    selected while the group is selected, so ``scene.selectedItems()`` right
    after a grouping gesture returns the new group *and its members*; counting
    the members would offer Group on a single selected group and a second
    grouping would empty the first (PF-CAN-36). The background image is a
    backdrop, not a plan object: grouping it re-bands it above ground surfaces
    and breaks the z-order, so it is deliberately not groupable.
    """
    from .background_image_item import BackgroundImageItem

    return [
        item
        for item in items
        if item.parentItem() is None and not isinstance(item, BackgroundImageItem)
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


def ungroupable_groups(items: list[QGraphicsItem]) -> list[GroupItem]:
    """The selected groups ``Ctrl+Shift+G`` may dissolve.

    A ``SmartSymbolItem`` is a ``GroupItem`` subclass whose members are
    generated from its parameters: ungrouping it would scatter them and drop
    the parametric identity, so a smart symbol is never offered (or accepted
    as) an ungroup target. It still counts as an ordinary object for Group.

    Only TOP-LEVEL groups are dissolved: Qt can keep a just-grouped child group
    flagged selected inside its new parent, and ungrouping one gesture must not
    silently cascade into the nested levels the issue documents as a second
    deliberate step.
    """
    from .smart_symbol_item import SmartSymbolItem

    return [
        item
        for item in items
        if isinstance(item, GroupItem)
        and item.parentItem() is None
        and not isinstance(item, SmartSymbolItem)
    ]


class GroupItem(GardenItemMixin, QGraphicsItemGroup):
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
        return super().itemChange(change, value)

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
