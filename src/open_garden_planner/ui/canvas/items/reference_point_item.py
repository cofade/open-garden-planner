"""The canvas item of a reference point (#666, ADR-080).

A reference point is the existing ``GENERIC_CIRCLE`` record with additive
metadata, so an older version reads it as a small circle. This subclass only
changes how that record is drawn and edited; it is serialized by the ordinary
circle branch of ``ProjectManager``.
"""

from __future__ import annotations

from typing import Any, cast

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneMouseEvent,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core import reference_points as ref
from open_garden_planner.core.cad_geometry import point_to_segment_distance
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.snap.geometry import item_edges

from .circle_item import CircleItem


def nearest_contour_position(
    parent: QGraphicsItem, position: QPointF
) -> tuple[QPointF, float] | None:
    """Project *position* onto the nearest straight edge of *parent*, in scene coords."""
    best: tuple[QPointF, float] | None = None
    for edge in item_edges(parent):
        distance, t = point_to_segment_distance(position, edge.p1(), edge.p2())
        if best is None or distance < best[1]:
            best = (edge.pointAt(t), distance)
    return best


class ReferencePointItem(CircleItem):
    """A named survey datum: a target/cross whose centre is the exact point."""

    def __init__(
        self,
        center_x: float,
        center_y: float,
        radius: float,
        object_type: ObjectType = ObjectType.GENERIC_CIRCLE,
        name: str = "",
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        metadata = dict(metadata or {})
        metadata[ref.MARKER] = True
        super().__init__(
            center_x,
            center_y,
            radius,
            object_type=object_type,
            name=name,
            metadata=metadata,
            **kwargs,
        )
        # The exact centre is the item's position; the circle's own rect is
        # centred on it, so mapToScene(rect().center()) == pos() at any zoom.
        self.prepareGeometryChange()
        QGraphicsEllipseItem.setRect(self, -radius, -radius, radius * 2, radius * 2)
        self._radius = radius
        self._center = QPointF()
        self.setTransformOriginPoint(QPointF())
        self.setPos(center_x, center_y)
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._apply_reference_pen()
        if ref.size_mode(self.metadata) == ref.SIZE_MODE_SCREEN:
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # -- appearance -----------------------------------------------------

    def _apply_reference_pen(self) -> None:
        colour = QColor(ref.color(self.metadata))
        width = ref.stroke_width(self.metadata)
        # The style attributes and the actual pen must agree (core/item_look):
        # copy/paste and the properties panel read the attributes, the canvas
        # reads the pen.
        self.stroke_color = colour
        self.stroke_width = width
        pen = QPen(colour)
        pen.setWidthF(width)
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        super().setPen(pen)

    def setPen(self, *args: Any) -> None:
        """Keep the reference look when a generic path sets a pen."""
        super().setPen(*args)
        if ref.is_reference_point(self.metadata):
            self._apply_reference_pen()

    @property
    def binding_parent(self) -> QGraphicsItem | None:
        """The item whose outline this point is attached to, if it is present."""
        try:
            parent_uuid = ref.parent_id(self.metadata)
            scene = self.scene()
            if parent_uuid is None or scene is None:
                return None
            finder = getattr(scene, "find_item_by_id", None)
            if callable(finder):
                return cast("QGraphicsItem | None", finder(parent_uuid))
            for item in scene.items():
                if getattr(item, "item_id", None) == parent_uuid:
                    return item
        except RuntimeError:
            # The scene is being torn down; a stale lookup must not abort it.
            return None
        return None

    def _visual_radius(self) -> float:
        """The symbol radius in the item's own coordinate unit."""
        return self._radius

    def boundingRect(self) -> QRectF:
        radius = self._visual_radius() + 5.0 + self.pen().widthF() / 2.0
        return QRectF(-radius, -radius, radius * 2.0, radius * 2.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    # -- painting -------------------------------------------------------

    def paint(
        self,
        painter: QPainter | None,
        option: QStyleOptionGraphicsItem | None,
        widget: QWidget | None = None,
    ) -> None:
        del option, widget
        if painter is None:
            return
        scene = self.scene()
        if scene is not None and getattr(scene, "_rendering_minimap", False):
            pen = QPen(self.pen().color(), 2.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawPoint(self.rect().center())
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colour = self.pen().color()
        radius = self._visual_radius()
        centre = self.rect().center()
        painter.setBrush(Qt.BrushStyle.NoBrush)

        if self.isSelected():
            halo = QColor(colour)
            halo.setAlpha(36)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(self.boundingRect())

        pen = QPen(colour, self.pen().widthF())
        pen.setCosmetic(True)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawEllipse(centre, radius * 0.48, radius * 0.48)
        painter.drawLine(
            QPointF(centre.x() - radius, centre.y()),
            QPointF(centre.x() + radius, centre.y()),
        )
        painter.drawLine(
            QPointF(centre.x(), centre.y() - radius),
            QPointF(centre.x(), centre.y() + radius),
        )
        # A solid dot marks the exact snap/measure coordinate.
        painter.setBrush(colour)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(centre, max(self.pen().widthF(), 1.0), max(self.pen().widthF(), 1.0))

        if ref.parent_id(self.metadata) is not None:
            badge_pen = QPen(colour, self.pen().widthF())
            badge_pen.setCosmetic(True)
            painter.setPen(badge_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(
                QRectF(radius * 0.55, -radius * 0.95, radius * 0.42, radius * 0.42)
            )
            painter.drawEllipse(
                QRectF(radius * 0.95, -radius * 0.55, radius * 0.42, radius * 0.42)
            )

        if self.isSelected():
            selected_pen = QPen(QColor("#0078d7"), 1.0, Qt.PenStyle.DashLine)
            selected_pen.setCosmetic(True)
            painter.setPen(selected_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(self.boundingRect().adjusted(1, 1, -1, -1))

    # -- geometry -------------------------------------------------------

    def _projected_position(self, proposed: QPointF) -> QPointF:
        parent = self.binding_parent
        if parent is None or not ref.on_contour(self.metadata):
            return proposed
        projection = nearest_contour_position(parent, proposed)
        return projection[0] if projection is not None else proposed

    def set_radius_centered(self, new_radius: float) -> None:
        if new_radius <= 0:
            return
        self.prepareGeometryChange()
        QGraphicsEllipseItem.setRect(
            self, -new_radius, -new_radius, new_radius * 2.0, new_radius * 2.0
        )
        self._radius = new_radius
        self._center = QPointF()
        self.setTransformOriginPoint(QPointF())
        self._position_label()
        self.update()

    def _compute_area_cm2(self) -> float | None:
        return None

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: Any
    ) -> Any:
        self.handle_item_change(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            parent_item = self.parentItem()
            proposed = (
                parent_item.mapToScene(value) if parent_item is not None else value
            )
            projected = self._projected_position(proposed)
            return (
                parent_item.mapFromScene(projected)
                if parent_item is not None
                else projected
            )
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedChange:
            if not value:
                self.hide_resize_handles()
                self.hide_rotation_handle()
            return QGraphicsEllipseItem.itemChange(self, change, value)
        return QGraphicsEllipseItem.itemChange(self, change, value)

    def _position_label(self) -> None:
        if self._label_item is None:
            return
        radius = self._visual_radius()
        self._label_item.setPos(0.0, -radius - 5.0)

    # -- interaction ----------------------------------------------------

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            from open_garden_planner.ui.reference_points import edit_reference_point

            edit_reference_point(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        if event is None:
            return
        from open_garden_planner.ui.reference_points import reference_context_menu

        menu, lock_action = reference_context_menu(self)
        chosen = menu.exec(event.screenPos())
        self.dispatch_lock_action(chosen, lock_action)
        menu.deleteLater()
        event.accept()
