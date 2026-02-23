"""Construction geometry items for the garden canvas.

Construction items are helper lines and circles that guide placement
but do not appear in PNG/SVG exports or prints. They are styled as
dashed light-blue shapes (FreeCAD convention).
"""

from __future__ import annotations

import uuid
from typing import Any

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QKeyEvent, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
)

# Construction geometry visual style
_CONSTRUCTION_COLOR = QColor(30, 130, 220)       # Light blue
_CONSTRUCTION_PEN_WIDTH = 1.2
_CONSTRUCTION_Z_VALUE = -10.0  # Below all regular items


class ConstructionLineItem(QGraphicsLineItem):
    """A construction line segment for guiding placement.

    Not included in PNG/SVG exports or prints.
    Dashed light-blue style (FreeCAD convention).
    """

    is_construction: bool = True

    def __init__(self, p1: QPointF, p2: QPointF) -> None:
        """Create a construction line from p1 to p2 in scene coordinates.

        Args:
            p1: Start point in scene coordinates.
            p2: End point in scene coordinates.
        """
        super().__init__(QLineF(p1, p2))
        self._item_id = uuid.uuid4()

        pen = QPen(_CONSTRUCTION_COLOR, _CONSTRUCTION_PEN_WIDTH, Qt.PenStyle.DashLine)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        self.setPen(pen)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(_CONSTRUCTION_Z_VALUE)

    @property
    def item_id(self) -> uuid.UUID:
        """Unique identifier for this item."""
        return self._item_id

    @property
    def p1(self) -> QPointF:
        """Start point in scene coordinates."""
        return self.mapToScene(self.line().p1())

    @property
    def p2(self) -> QPointF:
        """End point in scene coordinates."""
        return self.mapToScene(self.line().p2())

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for project file."""
        scene_p1 = self.mapToScene(self.line().p1())
        scene_p2 = self.mapToScene(self.line().p2())
        return {
            "type": "construction_line",
            "item_id": str(self._item_id),
            "x1": scene_p1.x(),
            "y1": scene_p1.y(),
            "x2": scene_p2.x(),
            "y2": scene_p2.y(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstructionLineItem:
        """Deserialize from dictionary."""
        item = cls(
            QPointF(data["x1"], data["y1"]),
            QPointF(data["x2"], data["y2"]),
        )
        if "item_id" in data:
            item._item_id = uuid.UUID(data["item_id"])
        return item

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu."""
        if not self.isSelected():
            if self.scene():
                self.scene().clearSelection()
            self.setSelected(True)

        menu = QMenu()
        delete_action = menu.addAction("Delete Construction Line")
        action = menu.exec(event.screenPos())

        if action == delete_action and self.scene():
            self.scene().removeItem(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Delete key."""
        if event.key() == Qt.Key.Key_Delete and self.scene():
            self.scene().removeItem(self)
        else:
            super().keyPressEvent(event)


class ConstructionCircleItem(QGraphicsEllipseItem):
    """A construction circle for guiding placement.

    Not included in PNG/SVG exports or prints.
    Dashed light-blue style (FreeCAD convention).
    """

    is_construction: bool = True

    def __init__(self, center_x: float, center_y: float, radius: float) -> None:
        """Create a construction circle.

        Args:
            center_x: Center X in scene coordinates.
            center_y: Center Y in scene coordinates.
            radius: Radius in scene units (cm).
        """
        super().__init__(
            center_x - radius,
            center_y - radius,
            radius * 2,
            radius * 2,
        )
        self._item_id = uuid.uuid4()
        self._center_x = center_x
        self._center_y = center_y
        self._radius = radius

        pen = QPen(_CONSTRUCTION_COLOR, _CONSTRUCTION_PEN_WIDTH, Qt.PenStyle.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(_CONSTRUCTION_Z_VALUE)

    @property
    def item_id(self) -> uuid.UUID:
        """Unique identifier for this item."""
        return self._item_id

    @property
    def center(self) -> QPointF:
        """Center point in scene coordinates."""
        rect = self.rect()
        return self.mapToScene(
            QPointF(rect.x() + rect.width() / 2, rect.y() + rect.height() / 2)
        )

    @property
    def radius(self) -> float:
        """Radius in scene units."""
        return self.rect().width() / 2

    def boundingRect(self) -> QRectF:
        """Expanded bounding rect to include pen width."""
        base = super().boundingRect()
        m = _CONSTRUCTION_PEN_WIDTH / 2.0 + 1.0
        return base.adjusted(-m, -m, m, m)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary for project file."""
        scene_center = self.center
        return {
            "type": "construction_circle",
            "item_id": str(self._item_id),
            "center_x": scene_center.x(),
            "center_y": scene_center.y(),
            "radius": self.radius,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstructionCircleItem:
        """Deserialize from dictionary."""
        item = cls(data["center_x"], data["center_y"], data["radius"])
        if "item_id" in data:
            item._item_id = uuid.UUID(data["item_id"])
        return item

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu."""
        if not self.isSelected():
            if self.scene():
                self.scene().clearSelection()
            self.setSelected(True)

        menu = QMenu()
        delete_action = menu.addAction("Delete Construction Circle")
        action = menu.exec(event.screenPos())

        if action == delete_action and self.scene():
            self.scene().removeItem(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle Delete key."""
        if event.key() == Qt.Key.Key_Delete and self.scene():
            self.scene().removeItem(self)
        else:
            super().keyPressEvent(event)
