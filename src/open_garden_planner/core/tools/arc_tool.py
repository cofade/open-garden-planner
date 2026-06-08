"""3-point Arc drawing tool (Phase 13 Package B — US-B2).

Click start, through-point, end → a unique circular arc through the
three points. If the three points are collinear (or nearly so) the tool
falls back to a 2-vertex polyline so the user's intent is never lost.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QGraphicsLineItem, QGraphicsPathItem

from open_garden_planner.core.cad_geometry import arc_from_three_points, arc_to_painter_path

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


_PREVIEW_COLOR = QColor(0, 100, 255)
_PREVIEW_WIDTH = 1.0


class ArcTool(BaseTool):
    """3-click arc tool: start → end → bulge.

    Workflow:
        - Click 1: place the start point. A short dashed line previews the
          straight-line segment to the cursor.
        - Click 2: place the end point. The dashed line now shows the
          start→end chord, and the preview arc bulges through the cursor.
          A straight-line preview is shown if the three points are collinear.
        - Click 3: place the bulge / through-point and commit. If the three
          points form an arc an ``ArcItem`` is added to the scene; otherwise a
          2-vertex ``PolylineItem`` (start→end) is created and a status
          message explains the fallback.
        - Escape: cancel at any time.

    The arc still passes through all three points; only the click *order*
    differs from a classic 3-point arc — the end is picked second so the user
    fixes the span first, then dials in the curvature (issue #195 follow-up).
    Internally ``_p1`` = start, ``_p2`` = end, and the third click is the
    through / bulge point stored on ``ArcItem``.
    """

    tool_type = ToolType.ARC
    display_name = QCoreApplication.translate("ArcTool", "Arc (3-point)")
    shortcut = "A"
    cursor = Qt.CursorShape.CrossCursor
    # The second + third clicks pick geometric points (end, then bulge),
    # not polar offsets from p1 — the Dist/Angle overlay would mislead
    # users into expecting it to control sweep direction.
    accepts_typed_coordinates = False

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._p1: QPointF | None = None  # start
        self._p2: QPointF | None = None  # end
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
        # Re-purpose the straight line as the start→end chord indicator.
        if self._preview_line is not None and self._p1 is not None and self._p2 is not None:
            self._preview_line.setLine(
                self._p1.x(), self._p1.y(), self._p2.x(), self._p2.y()
            )

    def _update_preview_path(self, cursor: QPointF) -> None:
        if self._preview_path is None or self._p1 is None or self._p2 is None:
            return
        # p1 = start, p2 = end, cursor = the bulge / through-point.
        result = arc_from_three_points(self._p1, cursor, self._p2)
        if result is None:
            # Collinear bulge — straight chord start → end.
            path = QPainterPath()
            path.moveTo(self._p1)
            path.lineTo(self._p2)
        else:
            center, radius, start_deg, span_deg = result
            # Same exact-endpoint builder ArcItem uses, so preview == final.
            path = arc_to_painter_path(center, radius, start_deg, span_deg)
        self._preview_path.setPath(path)

    # ------------------------------------------------------------------
    # Finalize
    # ------------------------------------------------------------------

    def _finalize(self, through: QPointF) -> None:
        from open_garden_planner.ui.canvas.items import ArcItem, PolylineItem

        if self._p1 is None or self._p2 is None:
            return
        # p1 = start, p2 = end, through = the 3rd-click bulge / through-point.
        result = arc_from_three_points(self._p1, through, self._p2)
        self._cleanup_preview()

        scene = self._view.scene()
        layer_id = None
        if hasattr(scene, "active_layer") and scene.active_layer is not None:
            layer_id = scene.active_layer.id

        if result is None:
            # Collinear fallback: a straight 2-vertex polyline from start to end.
            try:
                item = PolylineItem(
                    points=[QPointF(self._p1), QPointF(self._p2)],
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
                through=QPointF(through),  # keep the user's bulge point for editing
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
