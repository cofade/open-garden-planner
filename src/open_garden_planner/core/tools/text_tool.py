"""Text annotation tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class TextTool(BaseTool):
    """Tool for placing text annotations on the canvas.

    Click anywhere on the canvas to place a new text item at that position.
    The item immediately enters edit mode — type your text, then click
    elsewhere or press Escape to finish.
    """

    tool_type = ToolType.TEXT
    display_name = QT_TR_NOOP("Text")
    shortcut = ""
    cursor = Qt.CursorShape.IBeamCursor

    def __init__(self, view: "CanvasView") -> None:
        super().__init__(view)
        self._pending_item: object | None = None  # TextItem while editing

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Place a text item on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        from open_garden_planner.ui.canvas.items.text_item import TextItem

        scene = self._view.scene()
        layer_id = scene.active_layer.id if hasattr(scene, "active_layer") and scene.active_layer else None

        item = TextItem(
            scene_pos.x(),
            scene_pos.y(),
            content="",
            layer_id=layer_id,
        )
        self._view.add_item(item, "text")
        self._pending_item = item
        item.start_editing()
        return True

    def mouse_move(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Escape cancels placement (removes empty item)."""
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        """Remove a pending empty text item."""
        if self._pending_item is not None:
            item = self._pending_item
            self._pending_item = None
            scene = self._view.scene()
            if scene and item.scene() is not None and not item.toPlainText().strip():
                scene.removeItem(item)  # type: ignore[arg-type]
