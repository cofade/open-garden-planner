"""Arc item for the garden canvas (Phase 13 Package B — US-B2).

An ``ArcItem`` is a circular arc defined by its center, radius, start
angle, and signed sweep. It is created by the 3-point ``ArcTool`` and
persists via the standard project save/load pipeline.

The arc is rendered as a stroked ``QPainterPath`` (no fill). It is
selectable, movable, deletable, and supports basic styling through the
properties dialog. Selecting a placed arc shows draggable start /
through / end control handles for in-place reshaping (issue #193).
"""

from __future__ import annotations

import contextlib
import math
import uuid
from typing import Any

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsSceneContextMenuEvent,
    QMenu,
)

from open_garden_planner.core.cad_geometry import (
    arc_from_three_points,
    arc_to_painter_path,
)

from .resize_handle import (
    CURVE_KIND_ARC_END,
    CURVE_KIND_ARC_START,
    CURVE_KIND_ARC_THROUGH,
    CURVE_KIND_CENTER,
    CurveEditMixin,
)

_ARC_DEFAULT_COLOR = QColor(60, 60, 60)
_ARC_DEFAULT_PEN_WIDTH = 1.5
_ARC_MIN_RADIUS = 0.5  # cm — guards against degenerate arcs


class ArcItem(CurveEditMixin, QGraphicsPathItem):
    """Circular arc defined by center + radius + start_deg + span_deg.

    Angles follow the math convention used by ``arc_from_three_points``:
    degrees CCW from +X. ``span_deg`` is signed (positive CCW, negative
    CW); the arc is rendered via :func:`arc_to_painter_path`.

    ``through`` is a point lying on the arc between the endpoints — the
    original 3-point-arc through-point. It is the third degree of freedom
    held fixed while the user drags the start or end control handle, and is
    itself draggable to change curvature without moving the endpoints
    (issue #193). When omitted it defaults to the angular midpoint.
    """

    def __init__(
        self,
        center: QPointF,
        radius: float,
        start_deg: float,
        span_deg: float,
        name: str = "",
        layer_id: uuid.UUID | None = None,
        through: QPointF | None = None,
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
        self._through = (
            QPointF(through) if through is not None else self._angular_midpoint_local()
        )
        self._name = name
        self._layer_id = layer_id
        self._stroke_color: QColor = QColor(_ARC_DEFAULT_COLOR)
        self._stroke_width: float = _ARC_DEFAULT_PEN_WIDTH

        self._rebuild_path()
        self._apply_pen()

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.init_curve_edit()

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

    def _point_at_local(self, angle_deg: float) -> QPointF:
        """Item-local point on the arc's circle at ``angle_deg`` (CCW from +X)."""
        rad = math.radians(angle_deg)
        return QPointF(
            self._center.x() + self._radius * math.cos(rad),
            self._center.y() + self._radius * math.sin(rad),
        )

    def _start_local(self) -> QPointF:
        return self._point_at_local(self._start_deg)

    def _end_local(self) -> QPointF:
        return self._point_at_local(self._start_deg + self._span_deg)

    def _angular_midpoint_local(self) -> QPointF:
        return self._point_at_local(self._start_deg + self._span_deg / 2.0)

    def start_point(self) -> QPointF:
        """Scene coordinates of the arc's start point."""
        return self.mapToScene(self._start_local())

    def end_point(self) -> QPointF:
        """Scene coordinates of the arc's end point."""
        return self.mapToScene(self._end_local())

    def midpoint(self) -> QPointF:
        """Scene coordinates of the arc's angular midpoint."""
        return self.mapToScene(self._angular_midpoint_local())

    # ------------------------------------------------------------------
    # Painting / hit-testing
    # ------------------------------------------------------------------

    def _rebuild_path(self) -> None:
        """Rebuild the QPainterPath from current center/radius/angles.

        Uses :func:`arc_to_painter_path`, which builds the arc from exact
        cubic-Bézier segments so the rendered curve terminates precisely on
        ``start_point()`` / ``end_point()``. Qt's own ``arcMoveTo`` / ``arcTo``
        drift the rendered endpoints by up to a few mm on shallow, large-radius
        arcs (issue #195); the Bézier construction does not.
        """
        self.setPath(
            arc_to_painter_path(
                self._center, self._radius, self._start_deg, self._span_deg
            )
        )

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
    # Control-handle editing (issue #193)
    # ------------------------------------------------------------------

    def itemChange(
        self,
        change: QGraphicsItem.GraphicsItemChange,
        value: Any,
    ) -> Any:
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self.sync_curve_edit_to_selection()
        elif (
            change == QGraphicsItem.GraphicsItemChange.ItemSceneChange
            and value is None
        ):
            self.exit_curve_edit_mode()
        return super().itemChange(change, value)

    def _curve_control_specs(self) -> list[tuple[str, int, QPointF]]:
        """Start / through / end draggable handles + a read-only center marker."""
        return [
            (CURVE_KIND_ARC_START, 0, self._start_local()),
            (CURVE_KIND_ARC_THROUGH, 0, QPointF(self._through)),
            (CURVE_KIND_ARC_END, 0, self._end_local()),
            (CURVE_KIND_CENTER, 0, QPointF(self._center)),
        ]

    def _curve_connectors(self) -> list[tuple[QPointF, QPointF]]:
        return []

    def _move_control(
        self, kind: str, _index: int, local_pos: QPointF, _alt: bool
    ) -> None:
        # Arc has a single control per kind, so index is unused; reshaping always
        # recomputes the 3-point arc, so Alt (corner mode) does not apply.
        start = self._start_local()
        through = QPointF(self._through)
        end = self._end_local()
        if kind == CURVE_KIND_ARC_START:
            start = QPointF(local_pos)
        elif kind == CURVE_KIND_ARC_THROUGH:
            through = QPointF(local_pos)
        elif kind == CURVE_KIND_ARC_END:
            end = QPointF(local_pos)
        else:
            return
        result = arc_from_three_points(start, through, end)
        if result is None:
            return  # collinear — reject; handles keep their last valid spot
        center, radius, start_deg, span_deg = result
        if radius < _ARC_MIN_RADIUS:
            return  # degenerate radius — reject
        self._center = center
        self._radius = radius
        self._start_deg = start_deg
        self._span_deg = span_deg
        self._through = through
        self._rebuild_path()
        self._update_control_handles()

    def _capture_geometry(self) -> tuple[Any, ...]:
        return (
            "arc",
            self._center.x(),
            self._center.y(),
            self._radius,
            self._start_deg,
            self._span_deg,
            self._through.x(),
            self._through.y(),
        )

    def _restore_geometry(self, state: Any) -> None:
        _, cx, cy, radius, start_deg, span_deg, tx, ty = state
        self._center = QPointF(cx, cy)
        self._radius = radius
        self._start_deg = start_deg
        self._span_deg = span_deg
        self._through = QPointF(tx, ty)
        self._rebuild_path()
        self._update_control_handles()

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
        scene_through = self.mapToScene(self._through)
        data: dict[str, Any] = {
            "type": "arc",
            "item_id": str(self._item_id),
            "center_x": scene_center.x(),
            "center_y": scene_center.y(),
            "radius": self._radius,
            "start_deg": self._start_deg,
            "span_deg": self._span_deg,
            # Through-point persists the 3rd DOF so reshape handles round-trip
            # (issue #193); older files without it derive the angular midpoint.
            "through_x": scene_through.x(),
            "through_y": scene_through.y(),
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
        through: QPointF | None = None
        if "through_x" in data and "through_y" in data:
            with contextlib.suppress(ValueError, TypeError):
                through = QPointF(float(data["through_x"]), float(data["through_y"]))
        item = cls(
            center=QPointF(float(data["center_x"]), float(data["center_y"])),
            radius=float(data["radius"]),
            start_deg=float(data["start_deg"]),
            span_deg=float(data["span_deg"]),
            name=str(data.get("name", "")),
            layer_id=layer_id,
            through=through,
        )
        if "item_id" in data:
            with contextlib.suppress(ValueError, TypeError):
                item._item_id = uuid.UUID(data["item_id"])
        if "stroke_color" in data:
            item.stroke_color = QColor(data["stroke_color"])
        if "stroke_width" in data:
            item.stroke_width = float(data["stroke_width"])
        return item
