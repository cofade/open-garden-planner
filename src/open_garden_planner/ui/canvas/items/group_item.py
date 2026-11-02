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

    A group's members are not selectable, so every selected item is top-level;
    the one exception the shortcut has always made is a *selected* GroupItem
    whose ``parentItem()`` is not None (defensive: it cannot happen through the
    canvas). Both the shortcut and every context menu use this one filter, so
    the menu can never offer Group for a selection the shortcut would refuse.
    """
    return [
        item
        for item in items
        if not isinstance(item, GroupItem) or item.parentItem() is None
    ]


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
