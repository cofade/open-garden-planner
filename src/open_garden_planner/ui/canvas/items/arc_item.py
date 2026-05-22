"""Arc item for the garden canvas (Phase 13 Package B — US-B2).

An ``ArcItem`` is a circular arc defined by its center, radius, start
angle, and signed sweep. It is created by the 3-point ``ArcTool`` and
persists via the standard project save/load pipeline.

The arc is rendered as a stroked ``QPainterPath`` (no fill). It is
selectable, movable, deletable, and supports basic styling through the
properties dialog. Vertex editing (drag start/end/midpoint handles) is
not in the MVP and will follow in a B2.1 iteration.
"""

from __future__ import annotations

import contextlib
import math
import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
)

_ARC_DEFAULT_COLOR = QColor(60, 60, 60)
_ARC_DEFAULT_PEN_WIDTH = 1.5
_ARC_MIN_RADIUS = 0.5  # cm — guards against degenerate arcs


class ArcItem(QGraphicsPathItem):
    """Circular arc defined by center + radius + start_deg + span_deg.

    Angles follow the math convention used by ``arc_from_three_points``:
    degrees CCW from +X. ``span_deg`` is signed (positive CCW, negative
    CW); a CW arc is rendered with ``QPainterPath.arcTo`` using a
    negative sweepLength.
    """

    def __init__(
        self,
        center: QPointF,
        radius: float,
        start_deg: float,
        span_deg: float,
        name: str = "",
        layer_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__()
        if radius < _ARC_MIN_RADIUS:
            raise ValueError(
                f"ArcItem radius must be >= {_ARC_MIN_RADIUS} cm (got {radius})"
            )
        self._item_id = uuid.uuid4()
        self._center = QPointF(center)
        self._radius = float(radius)
        self._start_deg = float(start_deg)
        self._span_deg = float(span_deg)
        self._name = name
        self._layer_id = layer_id
        self._stroke_color: QColor = QColor(_ARC_DEFAULT_COLOR)
        self._stroke_width: float = _ARC_DEFAULT_PEN_WIDTH

        self._rebuild_path()
        self._apply_pen()

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    # ------------------------------------------------------------------
    # Identity / properties
    # ------------------------------------------------------------------

    @property
    def item_id(self) -> uuid.UUID:
        return self._item_id

    @property
    def center(self) -> QPointF:
        """Arc center in scene coordinates (accounts for item position)."""
        return self.mapToScene(self._center)

    @property
    def radius(self) -> float:
        return self._radius

    @property
    def start_deg(self) -> float:
        return self._start_deg

    @property
    def span_deg(self) -> float:
        return self._span_deg

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value

    @property
    def layer_id(self) -> uuid.UUID | None:
        return self._layer_id

    @layer_id.setter
    def layer_id(self, value: uuid.UUID | None) -> None:
        self._layer_id = value

    @property
    def stroke_color(self) -> QColor:
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value: QColor) -> None:
        self._stroke_color = QColor(value)
        self._apply_pen()

    @property
    def stroke_width(self) -> float:
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value: float) -> None:
        self._stroke_width = float(value)
        self._apply_pen()

    # ------------------------------------------------------------------
    # Derived geometry
    # ------------------------------------------------------------------

    def start_point(self) -> QPointF:
        """Scene coordinates of the arc's start point."""
        rad = math.radians(self._start_deg)
        local = QPointF(
            self._center.x() + self._radius * math.cos(rad),
            self._center.y() + self._radius * math.sin(rad),
        )
        return self.mapToScene(local)

    def end_point(self) -> QPointF:
        """Scene coordinates of the arc's end point."""
        rad = math.radians(self._start_deg + self._span_deg)
        local = QPointF(
            self._center.x() + self._radius * math.cos(rad),
            self._center.y() + self._radius * math.sin(rad),
        )
        return self.mapToScene(local)

    def midpoint(self) -> QPointF:
        """Scene coordinates of the arc's angular midpoint."""
        rad = math.radians(self._start_deg + self._span_deg / 2.0)
        local = QPointF(
            self._center.x() + self._radius * math.cos(rad),
            self._center.y() + self._radius * math.sin(rad),
        )
        return self.mapToScene(local)

    # ------------------------------------------------------------------
    # Painting / hit-testing
    # ------------------------------------------------------------------

    def _rebuild_path(self) -> None:
        """Rebuild the QPainterPath from current center/radius/angles.

        ``self._start_deg`` and ``self._span_deg`` use the *math* convention
        (CCW from +X with Y-up). Qt's ``QPainterPath.arcTo`` interprets
        angles in its own Y-down convention where a positive sweep traces
        from the angle toward smaller Y. Negating both arguments converts
        between the two so the rendered arc passes through the points
        returned by ``start_point``/``midpoint``/``end_point``.
        """
        path = QPainterPath()
        cx, cy = self._center.x(), self._center.y()
        bounding_rect = QRectF(
            cx - self._radius,
            cy - self._radius,
            2 * self._radius,
            2 * self._radius,
        )
        path.arcMoveTo(bounding_rect, -self._start_deg)
        path.arcTo(bounding_rect, -self._start_deg, -self._span_deg)
        self.setPath(path)

    def _apply_pen(self) -> None:
        pen = QPen(self._stroke_color)
        pen.setWidthF(self._stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def boundingRect(self) -> QRectF:
        # Inflate by pen width so the stroke isn't clipped on selection.
        base = super().boundingRect()
        m = self._stroke_width / 2.0 + 1.0
        return base.adjusted(-m, -m, m, m)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        if not self.isSelected():
            if self.scene():
                self.scene().clearSelection()
            self.setSelected(True)

        _ = QCoreApplication.translate
        menu = QMenu()
        delete_action = menu.addAction(_("ArcItem", "Delete Arc"))
        action = menu.exec(event.screenPos())

        if action == delete_action and self.scene():
            self.scene().removeItem(self)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete and self.scene():
            self.scene().removeItem(self)
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        scene_center = self.mapToScene(self._center)
        data: dict[str, Any] = {
            "type": "arc",
            "item_id": str(self._item_id),
            "center_x": scene_center.x(),
            "center_y": scene_center.y(),
            "radius": self._radius,
            "start_deg": self._start_deg,
            "span_deg": self._span_deg,
        }
        if self._name:
            data["name"] = self._name
        if self._layer_id is not None:
            data["layer_id"] = str(self._layer_id)
        data["stroke_color"] = self._stroke_color.name(QColor.NameFormat.HexArgb)
        data["stroke_width"] = self._stroke_width
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ArcItem:
        layer_id: uuid.UUID | None = None
        if "layer_id" in data:
            try:
                layer_id = uuid.UUID(data["layer_id"])
            except (ValueError, TypeError):
                layer_id = None
        item = cls(
            center=QPointF(float(data["center_x"]), float(data["center_y"])),
            radius=float(data["radius"]),
            start_deg=float(data["start_deg"]),
            span_deg=float(data["span_deg"]),
            name=str(data.get("name", "")),
            layer_id=layer_id,
        )
        if "item_id" in data:
            with contextlib.suppress(ValueError, TypeError):
                item._item_id = uuid.UUID(data["item_id"])
        if "stroke_color" in data:
            item.stroke_color = QColor(data["stroke_color"])
        if "stroke_width" in data:
            item.stroke_width = float(data["stroke_width"])
        return item
