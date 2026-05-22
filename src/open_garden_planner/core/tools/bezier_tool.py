"""Cubic Bezier pen tool (Phase 13 Package B — US-B1).

Authoring follows the standard pen-tool convention:

- Mouse press at point ``A``: place anchor ``A`` with both handles at
  ``A`` (corner anchor, zero-length handles).
- Drag (while button held) at ``A``: stretch the *outgoing* handle from
  ``A`` toward the cursor; the incoming handle is the mirror around
  ``A`` (smooth tangent).
- Release: handle locked in.
- Mouse press at ``B``: same workflow for the next anchor; the rubber
  band shows the cubic segment ``A → B`` continuously.
- Enter / Return / double-click: finalize the curve (requires ≥ 2
  anchors).
- Backspace: remove the most recent anchor.
- Escape: cancel.

Vertex / handle editing of a placed curve is deferred to a B1.1
follow-up (consolidated with arc vertex editing).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
)

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


_PREVIEW_COLOR = QColor(0, 100, 255)
_PREVIEW_WIDTH = 1.0
_HANDLE_LINE_COLOR = QColor(160, 160, 160)
_HANDLE_DOT_RADIUS = 2.5


class BezierTool(BaseTool):
    """Cubic-Bezier pen tool."""

    tool_type = ToolType.BEZIER
    display_name = QCoreApplication.translate("BezierTool", "Bezier")
    shortcut = "B"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._anchors: list[QPointF] = []
        self._handles_in: list[QPointF] = []
        self._handles_out: list[QPointF] = []
        self._dragging: bool = False
        self._preview_path: QGraphicsPathItem | None = None
        # Visual aids for the current anchor's handle:
        self._handle_line_out: QGraphicsLineItem | None = None
        self._handle_line_in: QGraphicsLineItem | None = None
        self._handle_dot_out: QGraphicsEllipseItem | None = None
        self._handle_dot_in: QGraphicsEllipseItem | None = None

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = self._view.snap_point(scene_pos)
        self._anchors.append(QPointF(snapped))
        self._handles_in.append(QPointF(snapped))
        self._handles_out.append(QPointF(snapped))
        self._dragging = True
        self._ensure_preview()
        self._refresh_preview(snapped)
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if not self._anchors:
            return False
        snapped = self._view.snap_point(scene_pos)
        if self._dragging:
            i = len(self._anchors) - 1
            anchor = self._anchors[i]
            self._handles_out[i] = QPointF(snapped)
            # Mirror outgoing → incoming for smooth tangent.
            self._handles_in[i] = QPointF(
                2 * anchor.x() - snapped.x(),
                2 * anchor.y() - snapped.y(),
            )
        self._refresh_preview(snapped)
        return True

    def mouse_release(self, event: QMouseEvent, _scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._dragging = False
        return True

    def mouse_double_click(
        self, _event: QMouseEvent, _scene_pos: QPointF
    ) -> bool:
        if len(self._anchors) >= 2:
            # A double-click fires after press+release+press+release. The
            # second press already appended a duplicate anchor at the same
            # spot; remove it so the curve doesn't get a zero-length
            # trailing segment.
            if len(self._anchors) >= 2 and _points_equal(
                self._anchors[-1], self._anchors[-2]
            ):
                self._anchors.pop()
                self._handles_in.pop()
                self._handles_out.pop()
            self._finalize()
            return True
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if len(self._anchors) >= 2:
                self._finalize()
                return True
            return False
        if key == Qt.Key.Key_Escape and self._anchors:
            self.cancel()
            return True
        if key == Qt.Key.Key_Backspace and self._anchors:
            self._anchors.pop()
            self._handles_in.pop()
            self._handles_out.pop()
            if not self._anchors:
                self.cancel()
            else:
                self._refresh_preview(self._anchors[-1])
            return True
        return False

    # ------------------------------------------------------------------
    # Typed-coordinate input (Package A)
    # ------------------------------------------------------------------

    @property
    def last_point(self) -> QPointF | None:
        if self._anchors:
            return QPointF(self._anchors[-1])
        return None

    def commit_typed_coordinate(self, point: QPointF) -> bool:
        """Append a new corner anchor at the typed coordinate.

        Typed input creates a corner anchor (zero-length handles); the
        user can then drag the next anchor with the mouse if they want
        smooth tangents. This keeps the typed pathway predictable.
        """
        self._anchors.append(QPointF(point))
        self._handles_in.append(QPointF(point))
        self._handles_out.append(QPointF(point))
        self._dragging = False
        self._ensure_preview()
        self._refresh_preview(point)
        return True

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _ensure_preview(self) -> None:
        if self._preview_path is None:
            self._preview_path = QGraphicsPathItem()
            pen = QPen(_PREVIEW_COLOR, _PREVIEW_WIDTH, Qt.PenStyle.DashLine)
            self._preview_path.setPen(pen)
            self._view.scene().addItem(self._preview_path)
        if self._handle_line_out is None:
            self._handle_line_out = QGraphicsLineItem()
            self._handle_line_out.setPen(
                QPen(_HANDLE_LINE_COLOR, 0.8, Qt.PenStyle.DotLine)
            )
            self._view.scene().addItem(self._handle_line_out)
        if self._handle_line_in is None:
            self._handle_line_in = QGraphicsLineItem()
            self._handle_line_in.setPen(
                QPen(_HANDLE_LINE_COLOR, 0.8, Qt.PenStyle.DotLine)
            )
            self._view.scene().addItem(self._handle_line_in)
        if self._handle_dot_out is None:
            self._handle_dot_out = QGraphicsEllipseItem()
            self._handle_dot_out.setBrush(QBrush(_HANDLE_LINE_COLOR))
            self._handle_dot_out.setPen(QPen(Qt.PenStyle.NoPen))
            self._view.scene().addItem(self._handle_dot_out)
        if self._handle_dot_in is None:
            self._handle_dot_in = QGraphicsEllipseItem()
            self._handle_dot_in.setBrush(QBrush(_HANDLE_LINE_COLOR))
            self._handle_dot_in.setPen(QPen(Qt.PenStyle.NoPen))
            self._view.scene().addItem(self._handle_dot_in)

    def _refresh_preview(self, cursor: QPointF) -> None:
        if self._preview_path is None or not self._anchors:
            return
        # Build the committed curve through all current anchors.
        path = QPainterPath()
        path.moveTo(self._anchors[0])
        for i in range(1, len(self._anchors)):
            path.cubicTo(
                self._handles_out[i - 1],
                self._handles_in[i],
                self._anchors[i],
            )
        # Append a "next segment" preview from the last anchor to the cursor,
        # using the last anchor's outgoing handle as control1 and cursor as
        # both control2 and end (degenerate but visually intuitive).
        if not self._dragging and len(self._anchors) >= 1:
            out = self._handles_out[-1]
            path.cubicTo(out, cursor, cursor)
        self._preview_path.setPath(path)
        # Update handle visualization for the most recent anchor.
        i = len(self._anchors) - 1
        a = self._anchors[i]
        ho = self._handles_out[i]
        hi = self._handles_in[i]
        if self._handle_line_out is not None:
            self._handle_line_out.setLine(a.x(), a.y(), ho.x(), ho.y())
        if self._handle_line_in is not None:
            self._handle_line_in.setLine(a.x(), a.y(), hi.x(), hi.y())
        r = _HANDLE_DOT_RADIUS
        if self._handle_dot_out is not None:
            self._handle_dot_out.setRect(ho.x() - r, ho.y() - r, 2 * r, 2 * r)
        if self._handle_dot_in is not None:
            self._handle_dot_in.setRect(hi.x() - r, hi.y() - r, 2 * r, 2 * r)

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(self) -> None:
        from open_garden_planner.ui.canvas.items import BezierItem

        if len(self._anchors) < 2:
            self.cancel()
            return
        self._cleanup_preview()
        scene = self._view.scene()
        layer_id = None
        if hasattr(scene, "active_layer") and scene.active_layer is not None:
            layer_id = scene.active_layer.id
        item = BezierItem(
            anchors=list(self._anchors),
            handles_in=list(self._handles_in),
            handles_out=list(self._handles_out),
            layer_id=layer_id,
        )
        self._view.add_item(item, "bezier")
        self._reset_state()

    def _cleanup_preview(self) -> None:
        scene = self._view.scene()
        for attr in (
            "_preview_path",
            "_handle_line_out",
            "_handle_line_in",
            "_handle_dot_out",
            "_handle_dot_in",
        ):
            obj = getattr(self, attr)
            if obj is not None:
                scene.removeItem(obj)
                setattr(self, attr, None)

    def _reset_state(self) -> None:
        self._anchors.clear()
        self._handles_in.clear()
        self._handles_out.clear()
        self._dragging = False

    def cancel(self) -> None:
        self._cleanup_preview()
        self._reset_state()


def _points_equal(a: QPointF, b: QPointF, eps: float = 1e-6) -> bool:
    return abs(a.x() - b.x()) <= eps and abs(a.y() - b.y()) <= eps
