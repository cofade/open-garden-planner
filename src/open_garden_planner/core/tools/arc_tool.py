"""3-point Arc drawing tool (Phase 13 Package B — US-B2).

Click start, through-point, end → a unique circular arc through the
three points. If the three points are collinear (or nearly so) the tool
falls back to a 2-vertex polyline so the user's intent is never lost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem

from open_garden_planner.core.cad_geometry import arc_from_three_points

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


_PREVIEW_COLOR = QColor(0, 100, 255)
_PREVIEW_WIDTH = 1.0


class ArcTool(BaseTool):
    """3-click arc tool: start → through-point → end.

    Workflow:
        - Click 1: place start point. A short dashed line previews the
          straight-line segment to the cursor.
        - Click 2: place the through-point. Now the preview shows the
          unique arc passing through start, through-point, and cursor.
          A straight-line preview is shown if the three are collinear.
        - Click 3: commit. If the three points form an arc, an
          ``ArcItem`` is added to the scene; otherwise a 2-vertex
          ``PolylineItem`` is created and a status message explains the
          fallback.
        - Escape: cancel at any time.
    """

    tool_type = ToolType.ARC
    display_name = QCoreApplication.translate("ArcTool", "Arc (3-point)")
    shortcut = "A"
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._p1: QPointF | None = None
        self._p2: QPointF | None = None
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_path: QGraphicsPathItem | None = None

    # ------------------------------------------------------------------
    # Mouse handling
    # ------------------------------------------------------------------

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = self._view.snap_point(scene_pos)
        if self._p1 is None:
            self._p1 = QPointF(snapped)
            self._ensure_preview_line()
            return True
        if self._p2 is None:
            self._p2 = QPointF(snapped)
            self._ensure_preview_path()
            return True
        # Click 3 — commit.
        self._finalize(QPointF(snapped))
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._p1 is None:
            return False
        snapped = self._view.snap_point(scene_pos)
        if self._p2 is None:
            self._update_preview_line(snapped)
            return True
        self._update_preview_path(snapped)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._p1 is not None:
            self.cancel()
            return True
        return False

    # ------------------------------------------------------------------
    # Typed-coordinate input (Package A integration)
    # ------------------------------------------------------------------

    @property
    def last_point(self) -> QPointF | None:
        if self._p2 is not None:
            return QPointF(self._p2)
        if self._p1 is not None:
            return QPointF(self._p1)
        return None

    def commit_typed_coordinate(self, point: QPointF) -> bool:
        # Mirror the mouse_press state machine for typed input.
        if self._p1 is None:
            self._p1 = QPointF(point)
            self._ensure_preview_line()
            return True
        if self._p2 is None:
            self._p2 = QPointF(point)
            self._ensure_preview_path()
            return True
        self._finalize(QPointF(point))
        return True

    # ------------------------------------------------------------------
    # Preview rendering
    # ------------------------------------------------------------------

    def _ensure_preview_line(self) -> None:
        if self._preview_line is not None:
            return
        self._preview_line = QGraphicsLineItem()
        pen = QPen(_PREVIEW_COLOR, _PREVIEW_WIDTH, Qt.PenStyle.DashLine)
        self._preview_line.setPen(pen)
        self._view.scene().addItem(self._preview_line)

    def _update_preview_line(self, cursor: QPointF) -> None:
        if self._preview_line is None or self._p1 is None:
            return
        self._preview_line.setLine(
            self._p1.x(), self._p1.y(), cursor.x(), cursor.y()
        )

    def _ensure_preview_path(self) -> None:
        if self._preview_path is not None:
            return
        self._preview_path = QGraphicsPathItem()
        pen = QPen(_PREVIEW_COLOR, _PREVIEW_WIDTH, Qt.PenStyle.DashLine)
        self._preview_path.setPen(pen)
        self._view.scene().addItem(self._preview_path)
        # Re-purpose the straight line as the start→through indicator.
        if self._preview_line is not None and self._p1 is not None and self._p2 is not None:
            self._preview_line.setLine(
                self._p1.x(), self._p1.y(), self._p2.x(), self._p2.y()
            )

    def _update_preview_path(self, cursor: QPointF) -> None:
        if self._preview_path is None or self._p1 is None or self._p2 is None:
            return
        result = arc_from_three_points(self._p1, self._p2, cursor)
        path = QPainterPath()
        if result is None:
            # Collinear preview — straight segment p1 → cursor.
            path.moveTo(self._p1)
            path.lineTo(cursor)
        else:
            center, radius, start_deg, span_deg = result
            rect = QRectF(
                center.x() - radius,
                center.y() - radius,
                2 * radius,
                2 * radius,
            )
            # Negate angles for Qt's Y-down arc convention (see ArcItem._rebuild_path).
            path.arcMoveTo(rect, -start_deg)
            path.arcTo(rect, -start_deg, -span_deg)
        self._preview_path.setPath(path)

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(self, p3: QPointF) -> None:
        from open_garden_planner.ui.canvas.items import ArcItem, PolylineItem

        if self._p1 is None or self._p2 is None:
            return
        result = arc_from_three_points(self._p1, self._p2, p3)
        self._cleanup_preview()

        scene = self._view.scene()
        layer_id = None
        if hasattr(scene, "active_layer") and scene.active_layer is not None:
            layer_id = scene.active_layer.id

        if result is None:
            # Collinear fallback: place a 2-vertex polyline.
            try:
                item = PolylineItem(
                    points=[QPointF(self._p1), QPointF(p3)],
                    layer_id=layer_id,
                )
                self._view.add_item(item, "polyline")
            except Exception:  # noqa: BLE001
                pass
            self._notify_collinear_fallback()
        else:
            center, radius, start_deg, span_deg = result
            item = ArcItem(
                center=center,
                radius=radius,
                start_deg=start_deg,
                span_deg=span_deg,
                layer_id=layer_id,
            )
            self._view.add_item(item, "arc")
        self._reset_state()

    def _notify_collinear_fallback(self) -> None:
        """Show a transient status-bar message about the line fallback."""
        msg = QCoreApplication.translate(
            "ArcTool", "Points are collinear; drew a line instead"
        )
        # CanvasView exposes a status-message helper in MainWindow; if it
        # isn't available we silently skip the notice.
        window = self._view.window() if hasattr(self._view, "window") else None
        status = getattr(window, "statusBar", None)
        if callable(status):
            bar = status()
            if bar is not None:
                bar.showMessage(msg, 3000)

    def _cleanup_preview(self) -> None:
        if self._preview_line is not None:
            self._view.scene().removeItem(self._preview_line)
            self._preview_line = None
        if self._preview_path is not None:
            self._view.scene().removeItem(self._preview_path)
            self._preview_path = None

    def _reset_state(self) -> None:
        self._p1 = None
        self._p2 = None

    def cancel(self) -> None:
        self._cleanup_preview()
        self._reset_state()
