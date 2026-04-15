"""Group item: a logical container for grouping multiple canvas items."""

from __future__ import annotations

import uuid

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
        """Show ungroup action in the context menu."""
        menu = QMenu()
        ungroup_action = menu.addAction("Ungroup")

        menu.addSeparator()

        # Move to Layer submenu (hidden when project has only one layer)
        move_layer_menu = self._build_move_to_layer_menu(menu)

        action = menu.exec(event.screenPos())
        if action == ungroup_action:
            scene = self.scene()
            if scene:
                views = scene.views()
                if views and hasattr(views[0], "ungroup_item"):
                    views[0].ungroup_item(self)
        elif move_layer_menu and action and action.parent() is move_layer_menu:
            self._dispatch_move_to_layer(action.data())
