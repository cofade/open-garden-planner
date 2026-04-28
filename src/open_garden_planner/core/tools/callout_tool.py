"""Callout annotation tool — click target, drag to text box position."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsLineItem

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class CalloutTool(BaseTool):
    """Tool for placing callout annotations with a leader line.

    Click to set the arrow tip, drag to position the text box,
    release to place.  The new item immediately enters text-edit mode.
    """

    tool_type = ToolType.CALLOUT
    display_name = QT_TR_NOOP("Callout")
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor

    def __init__(self, view: "CanvasView") -> None:
        super().__init__(view)
        self._target: QPointF | None = None
        self._preview: QGraphicsLineItem | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        self._target = scene_pos
        # Show a thin preview line while dragging
        scene = self._view.scene()
        if scene:
            self._preview = QGraphicsLineItem(
                scene_pos.x(), scene_pos.y(), scene_pos.x(), scene_pos.y()
            )
            pen = QPen(Qt.GlobalColor.darkGray, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._preview.setPen(pen)
            scene.addItem(self._preview)
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        if self._target is None or self._preview is None:
            return False
        self._preview.setLine(
            self._target.x(), self._target.y(),
            scene_pos.x(), scene_pos.y(),
        )
        return True

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton or self._target is None:
            return False

        target = self._target
        box_offset = QPointF(
            scene_pos.x() - target.x(),
            scene_pos.y() - target.y(),
        )
        # Ensure a minimum offset so the box is not on top of the tip
        if abs(box_offset.x()) < 20 and abs(box_offset.y()) < 20:
            box_offset = QPointF(80.0, -60.0)

        self._cleanup_preview()

        from open_garden_planner.ui.canvas.items.callout_item import CalloutItem

        scene = self._view.scene()
        layer_id = (
            scene.active_layer.id
            if hasattr(scene, "active_layer") and scene.active_layer
            else None
        )
        item = CalloutItem(target, box_offset, content="", layer_id=layer_id)
        self._view.add_item(item, "callout")
        item.start_editing()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            if self._target is not None:
                self.cancel()
            else:
                self._view.set_active_tool(ToolType.SELECT)
            return True
        return False

    def cancel(self) -> None:
        self._cleanup_preview()
        self._target = None

    def _cleanup_preview(self) -> None:
        if self._preview is not None:
            scene = self._view.scene()
            if scene and self._preview.scene() is not None:
                scene.removeItem(self._preview)
            self._preview = None
