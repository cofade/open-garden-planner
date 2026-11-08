"""Split a closed shape along a two-click snapped line (#664).

The tool is started from a shape's context menu (``CanvasView.start_split_shape``),
takes two snapped scene points, previews the resulting pieces live, and applies
the cut as exactly one undo step. ``Shift`` constrains the line to 45-degree
steps; ``Esc`` cancels without mutating the scene.
"""

from __future__ import annotations

import contextlib
from copy import deepcopy
from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QColor, QKeyEvent, QMouseEvent, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsLineItem, QGraphicsPolygonItem

from open_garden_planner.core.cad_geometry import snap_point_to_axis_step
from open_garden_planner.core.item_look import copy_visual_style
from open_garden_planner.core.shape_split import (
    polygon_type_for_split,
    split_item_into_local_polygons,
)
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType
from open_garden_planner.core.tools.preview_z import PREVIEW_Z_FILL, PREVIEW_Z_LINE

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class SplitShapeTool(BaseTool):
    """Two snapped picks define an infinite cutting axis; Shift constrains it."""

    tool_type = ToolType.SPLIT
    display_name = QCoreApplication.translate("SplitShapeTool", "Split along line")
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor
    accepts_typed_coordinates = False
    # Keep BaseTool's shared anchor snap: both picks and the preview use it.

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self.source_id: UUID | None = None
        self._start: QPointF | None = None
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_pieces: list[QGraphicsPolygonItem] = []
        self._build_error: str | None = None
        self._scene = view._canvas_scene
        self._scene.document_replaced.connect(self.cancel)

    # ------------------------------------------------------------------
    # Starting and finishing the gesture
    # ------------------------------------------------------------------

    def prepare(self, source_id: UUID) -> None:
        """Arm the tool for one source item without starting a pick yet."""
        self.cancel()
        self.source_id = source_id

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Take the first or second cutting point."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        source = self._source()
        if source is None:
            self._view.set_status_message(
                QCoreApplication.translate(
                    "SplitShapeTool", "The shape to split is no longer available."
                )
            )
            self.cancel()
            self._view.set_active_tool(ToolType.SELECT)
            return True
        reason = self._view.split_refusal_reason(source)
        if reason is not None:
            self._view.set_status_message(
                QCoreApplication.translate(
                    "SplitShapeTool", "This shape cannot be split: {reason}"
                ).format(reason=reason)
            )
            self.cancel()
            self._view.set_active_tool(ToolType.SELECT)
            return True

        if self._start is None:
            self._start = QPointF(scene_pos)
            self._show_line_preview(QPointF(scene_pos))
            self._view.set_status_message(
                QCoreApplication.translate(
                    "SplitShapeTool",
                    "Click the second point of the cutting line; "
                    "Shift constrains the angle. Esc cancels.",
                )
            )
            return True

        end = self._end(scene_pos, event)
        pieces = self._build_pieces(source, self._start, end)
        if pieces is None:
            self._view.set_status_message(
                self._build_error
                or QCoreApplication.translate(
                    "SplitShapeTool",
                    "The cutting line must cross the shape. Choose another second point.",
                )
            )
            self._build_error = None
            return True
        self._build_error = None

        from open_garden_planner.core.commands import SplitShapeCommand

        self._clear_previews()
        self.source_id = None
        self._start = None
        self._view.command_manager.execute(
            SplitShapeCommand(self._scene, source, pieces)
        )
        self._scene.clearSelection()
        for piece in pieces:
            piece.setSelected(True)
        self._view.set_status_message(
            QCoreApplication.translate(
                "SplitShapeTool", "Split the shape into {count} pieces"
            ).format(count=len(pieces))
        )
        self._view.set_active_tool(ToolType.SELECT)
        return True

    def mouse_move(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Follow the cursor with the line and the live pieces."""
        if self._start is None:
            return True
        end = self._end(scene_pos, event)
        self._show_line_preview(end)
        self._show_piece_preview(end)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            self._view.set_status_message(
                QCoreApplication.translate("SplitShapeTool", "Split cancelled")
            )
            self._view.set_active_tool(ToolType.SELECT)
            return True
        return False

    def cancel(self) -> None:
        """Remove every preview and forget the armed source."""
        self._clear_previews()
        self._start = None
        self.source_id = None
        self._build_error = None

    # ------------------------------------------------------------------
    # Geometry and preview
    # ------------------------------------------------------------------

    def _source(self) -> QGraphicsItem | None:
        if self.source_id is None:
            return None
        return self._scene.find_item_by_id(self.source_id)

    def _end(self, point: QPointF, event: QMouseEvent) -> QPointF:
        if self._start is not None and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            return snap_point_to_axis_step(self._start, point, 45)
        return QPointF(point)

    def _build_pieces(
        self,
        source: QGraphicsItem,
        start: QPointF,
        end: QPointF,
    ) -> list[QGraphicsItem] | None:
        """Build the unsaved pieces, or None when the cut is unusable."""
        from open_garden_planner.ui.canvas.items import PolygonItem
        from open_garden_planner.ui.canvas.items.polygon_item import (
            MAX_POLYGON_VERTICES,
        )

        local_polygons = split_item_into_local_polygons(source, start, end)
        if not local_polygons:
            return None
        if any(poly.count() > MAX_POLYGON_VERTICES for poly in local_polygons):
            self._build_error = QCoreApplication.translate(
                "SplitShapeTool",
                "A piece would have {count} vertices; the plan supports at "
                "most {limit}. Choose a simpler cut.",
            ).format(
                count=max(poly.count() for poly in local_polygons),
                limit=MAX_POLYGON_VERTICES,
            )
            return None

        pieces: list[QGraphicsItem] = []
        polygon_type = polygon_type_for_split(
            getattr(source, "object_type", None)
        )
        for polygon in local_polygons:
            item = PolygonItem.from_polygon(polygon)
            # Work in the source's local frame so the material keeps its
            # orientation and the source's rotation is reproduced exactly.
            item._apply_rotation(source.rotation())
            centre = item.transformOriginPoint()
            item.setPos(source.mapToScene(centre) - centre)
            if polygon_type is not None:
                item.object_type = polygon_type
            item.name = getattr(source, "name", "")
            item.label_visible = getattr(source, "label_visible", True)
            item.area_label_visible = getattr(source, "area_label_visible", False)
            item.layer_id = getattr(source, "layer_id", None)
            item.stack_order = getattr(source, "stack_order", None)
            metadata = getattr(source, "metadata", None)
            if metadata:
                item.metadata.update(deepcopy(metadata))
            copy_visual_style(source, item)
            item._setup_styling()
            pieces.append(item)
        return pieces

    def _show_line_preview(self, end: QPointF) -> None:
        if self._start is None:
            return
        if self._preview_line is None:
            self._preview_line = QGraphicsLineItem()
            pen = QPen(QColor(25, 120, 220), 1.5, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._preview_line.setPen(pen)
            self._preview_line.setZValue(PREVIEW_Z_LINE)
            self._scene.addItem(self._preview_line)
        direction = end - self._start
        length = (direction.x() ** 2 + direction.y() ** 2) ** 0.5
        if length <= 1e-6:
            self._preview_line.setLine(
                self._start.x(), self._start.y(), self._start.x(), self._start.y()
            )
            return
        extent = self._scene.sceneRect().width() + self._scene.sceneRect().height()
        direction *= extent / length
        first = self._start - direction
        second = self._start + direction
        self._preview_line.setLine(first.x(), first.y(), second.x(), second.y())

    def _show_piece_preview(self, end: QPointF) -> None:
        source = self._source()
        if source is None or self._start is None:
            self._clear_previews()
            return
        local_polygons = split_item_into_local_polygons(source, self._start, end)
        self._clear_piece_preview()
        if not local_polygons:
            return
        for polygon in local_polygons:
            scene_polygon = source.mapToScene(QPolygonF(polygon))
            preview = QGraphicsPolygonItem(scene_polygon)
            preview.setPen(QPen(QColor(60, 130, 200), 1.2, Qt.PenStyle.DashLine))
            preview.setBrush(QColor(60, 130, 200, 40))
            preview.setZValue(PREVIEW_Z_FILL)
            self._scene.addItem(preview)
            self._preview_pieces.append(preview)

    def _clear_piece_preview(self) -> None:
        for preview in self._preview_pieces:
            with contextlib.suppress(RuntimeError):
                if preview.scene() is not None:
                    self._scene.removeItem(preview)
        self._preview_pieces.clear()

    def _clear_previews(self) -> None:
        self._clear_piece_preview()
        if self._preview_line is not None:
            with contextlib.suppress(RuntimeError):
                if self._preview_line.scene() is not None:
                    self._scene.removeItem(self._preview_line)
        self._preview_line = None
