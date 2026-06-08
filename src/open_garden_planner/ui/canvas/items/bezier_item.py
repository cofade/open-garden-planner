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

Selecting a placed curve shows draggable control handles for in-place
reshaping (issue #193); see :class:`BezierItem` and ``CurveEditMixin``.
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

from .resize_handle import (
    CURVE_KIND_ANCHOR,
    CURVE_KIND_HANDLE_IN,
    CURVE_KIND_HANDLE_OUT,
    CurveEditMixin,
)

_BEZIER_DEFAULT_COLOR = QColor(60, 60, 60)
_BEZIER_DEFAULT_PEN_WIDTH = 1.5
_MIN_ANCHORS = 2


class BezierItem(CurveEditMixin, QGraphicsPathItem):
    """Multi-segment cubic Bezier curve.

    Selecting a placed curve (sole selection) shows draggable control handles
    (issue #193): an on-curve handle per anchor (moves the anchor and both its
    tangent handles together) plus tangent handles for each anchor's active
    control point. Dragging a tangent keeps the opposite tangent mirrored for a
    smooth (C1) join; hold **Alt** to break it into a corner. Each drag commits
    one undo step via :class:`SetCurveGeometryCommand`.
    """

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
        self.init_curve_edit()

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
        """One on-curve anchor handle per anchor, plus each anchor's active
        tangent handle(s). Endpoint anchors expose only the live tangent."""
        specs: list[tuple[str, int, QPointF]] = []
        n = len(self._anchors)
        for i in range(n):
            specs.append((CURVE_KIND_ANCHOR, i, QPointF(self._anchors[i])))
            if i > 0:
                specs.append((CURVE_KIND_HANDLE_IN, i, QPointF(self._handles_in[i])))
            if i < n - 1:
                specs.append((CURVE_KIND_HANDLE_OUT, i, QPointF(self._handles_out[i])))
        return specs

    def _curve_connectors(self) -> list[tuple[QPointF, QPointF]]:
        lines: list[tuple[QPointF, QPointF]] = []
        n = len(self._anchors)
        for i in range(n):
            if i > 0:
                lines.append((QPointF(self._anchors[i]), QPointF(self._handles_in[i])))
            if i < n - 1:
                lines.append((QPointF(self._anchors[i]), QPointF(self._handles_out[i])))
        return lines

    def _move_control(
        self, kind: str, index: int, local_pos: QPointF, alt: bool
    ) -> None:
        n = len(self._anchors)
        if not 0 <= index < n:
            return
        if kind == CURVE_KIND_ANCHOR:
            # Move the anchor and carry both its tangent handles along.
            delta = local_pos - self._anchors[index]
            self._anchors[index] = QPointF(local_pos)
            self._handles_in[index] = self._handles_in[index] + delta
            self._handles_out[index] = self._handles_out[index] + delta
        elif kind == CURVE_KIND_HANDLE_OUT:
            self._handles_out[index] = QPointF(local_pos)
            if not alt and 0 < index < n - 1:
                # Keep a smooth (C1) join: mirror the incoming tangent.
                self._handles_in[index] = self._anchors[index] * 2.0 - local_pos
        elif kind == CURVE_KIND_HANDLE_IN:
            self._handles_in[index] = QPointF(local_pos)
            if not alt and 0 < index < n - 1:
                self._handles_out[index] = self._anchors[index] * 2.0 - local_pos
        else:
            return
        self._rebuild_path()
        self._update_control_handles()

    def _capture_geometry(self) -> tuple[Any, ...]:
        return (
            "bezier",
            tuple((p.x(), p.y()) for p in self._anchors),
            tuple((p.x(), p.y()) for p in self._handles_in),
            tuple((p.x(), p.y()) for p in self._handles_out),
        )

    def _restore_geometry(self, state: Any) -> None:
        _, anchors, handles_in, handles_out = state
        self._anchors = [QPointF(x, y) for x, y in anchors]
        self._handles_in = [QPointF(x, y) for x, y in handles_in]
        self._handles_out = [QPointF(x, y) for x, y in handles_out]
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
