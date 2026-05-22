"""Cubic Bezier item (Phase 13 Package B — US-B1).

A ``BezierItem`` is a multi-segment cubic Bezier curve. Storage:
- ``anchors[i]``      — on-curve point (N total)
- ``handles_out[i]``  — outgoing handle from anchor i (controls the curve
                        going forward into segment i → i+1)
- ``handles_in[i]``   — incoming handle into anchor i (controls the curve
                        arriving from segment i-1 → i)

The cubic segment between anchors i and i+1 uses control points
``handles_out[i]`` and ``handles_in[i+1]``. ``handles_in[0]`` and
``handles_out[N-1]`` are unused for an open curve but kept for symmetry
and to simplify a future closed-curve / handle-editing model.

The MVP renders the curve and supports selection / movement / delete.
Per-anchor handle editing (drag a handle to reshape) is deferred to a
B1.1 follow-up alongside arc vertex editing — both share the same
``VertexHandle`` infrastructure.
"""

from __future__ import annotations

import contextlib
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

_BEZIER_DEFAULT_COLOR = QColor(60, 60, 60)
_BEZIER_DEFAULT_PEN_WIDTH = 1.5
_MIN_ANCHORS = 2


class BezierItem(QGraphicsPathItem):
    """Multi-segment cubic Bezier curve."""

    def __init__(
        self,
        anchors: list[QPointF],
        handles_in: list[QPointF],
        handles_out: list[QPointF],
        name: str = "",
        layer_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__()
        if len(anchors) < _MIN_ANCHORS:
            raise ValueError(
                f"BezierItem requires at least {_MIN_ANCHORS} anchors "
                f"(got {len(anchors)})"
            )
        if len(handles_in) != len(anchors) or len(handles_out) != len(anchors):
            raise ValueError(
                "handles_in and handles_out must each have one entry per anchor"
            )

        self._item_id = uuid.uuid4()
        self._anchors: list[QPointF] = [QPointF(p) for p in anchors]
        self._handles_in: list[QPointF] = [QPointF(p) for p in handles_in]
        self._handles_out: list[QPointF] = [QPointF(p) for p in handles_out]
        self._name = name
        self._layer_id = layer_id
        self._stroke_color: QColor = QColor(_BEZIER_DEFAULT_COLOR)
        self._stroke_width: float = _BEZIER_DEFAULT_PEN_WIDTH

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
    def anchors(self) -> list[QPointF]:
        """Copy of the anchor list in item-local coords."""
        return [QPointF(p) for p in self._anchors]

    @property
    def handles_in(self) -> list[QPointF]:
        return [QPointF(p) for p in self._handles_in]

    @property
    def handles_out(self) -> list[QPointF]:
        return [QPointF(p) for p in self._handles_out]

    @property
    def anchor_count(self) -> int:
        return len(self._anchors)

    @property
    def segment_count(self) -> int:
        return max(0, len(self._anchors) - 1)

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
    # Scene-coord accessors (account for item position)
    # ------------------------------------------------------------------

    def anchor_scene(self, index: int) -> QPointF:
        return self.mapToScene(self._anchors[index])

    def start_point(self) -> QPointF:
        return self.anchor_scene(0)

    def end_point(self) -> QPointF:
        return self.anchor_scene(len(self._anchors) - 1)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def _rebuild_path(self) -> None:
        path = QPainterPath()
        path.moveTo(self._anchors[0])
        for i in range(1, len(self._anchors)):
            path.cubicTo(
                self._handles_out[i - 1],
                self._handles_in[i],
                self._anchors[i],
            )
        self.setPath(path)

    def _apply_pen(self) -> None:
        pen = QPen(self._stroke_color)
        pen.setWidthF(self._stroke_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        self.setPen(pen)

    def boundingRect(self) -> QRectF:
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
        delete_action = menu.addAction(_("BezierItem", "Delete Bezier"))
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

    def _point_to_dict(self, p: QPointF, in_scene: bool = True) -> dict[str, float]:
        if in_scene:
            sp = self.mapToScene(p)
            return {"x": sp.x(), "y": sp.y()}
        return {"x": p.x(), "y": p.y()}

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "type": "bezier",
            "item_id": str(self._item_id),
            "anchors": [self._point_to_dict(p) for p in self._anchors],
            "handles_in": [self._point_to_dict(p) for p in self._handles_in],
            "handles_out": [self._point_to_dict(p) for p in self._handles_out],
        }
        if self._name:
            data["name"] = self._name
        if self._layer_id is not None:
            data["layer_id"] = str(self._layer_id)
        data["stroke_color"] = self._stroke_color.name(QColor.NameFormat.HexArgb)
        data["stroke_width"] = self._stroke_width
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BezierItem:
        def _pts(key: str) -> list[QPointF]:
            return [QPointF(float(p["x"]), float(p["y"])) for p in data.get(key, [])]

        layer_id: uuid.UUID | None = None
        if "layer_id" in data:
            with contextlib.suppress(ValueError, TypeError):
                layer_id = uuid.UUID(data["layer_id"])
        item = cls(
            anchors=_pts("anchors"),
            handles_in=_pts("handles_in"),
            handles_out=_pts("handles_out"),
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
