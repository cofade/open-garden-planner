"""Text annotation tool."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.core.commands import Command
    from open_garden_planner.ui.canvas.canvas_view import CanvasView
    from open_garden_planner.ui.canvas.items.text_item import TextItem


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

    def _translated_name(self) -> str:
        return QCoreApplication.translate("TextTool", "Text")

    def __init__(self, view: "CanvasView") -> None:
        super().__init__(view)
        self._pending_item: TextItem | None = None
        # The CreateItemCommand add_item executed for that item, kept so an
        # empty cancellation can take the pair off scene AND stack (#827).
        # Assigned and cleared together with _pending_item.
        self._pending_command: Command | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Place a text item on left click."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # A click is also how a pending annotation is finished: resolve the
        # previous pair before this click replaces it, or an empty first
        # annotation would keep both its scene item and its stack entry.
        self.cancel()

        from open_garden_planner.ui.canvas.items.text_item import TextItem

        scene = self._view.scene()
        layer_id = scene.active_layer.id if hasattr(scene, "active_layer") and scene.active_layer else None

        item = TextItem(
            scene_pos.x(),
            scene_pos.y(),
            content="",
            layer_id=layer_id,
        )
        command = self._view.add_item(item, "text")
        self._pending_item = item
        self._pending_command = command
        item.start_editing()
        return True

    def mouse_move(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        """Escape cancels placement: an empty annotation leaves no trace."""
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        return False

    def cancel(self) -> None:
        """Cancel a pending text annotation, keeping scene and history in step (#827).

        The placement click already executed its ``CreateItemCommand``, so
        removing the item from the scene alone left the command on the undo
        stack: undo became a no-op and redo resurrected the empty annotation.
        The sequence therefore discards the command FIRST and removes the item
        from the scene only when the discard proved the command left the stack.

        Interleaving fallback: if another command was pushed on top in the
        meantime, ``discard`` refuses (LIFO identity guard) and the empty item
        STAYS in the scene — an item-plus-command pair is consistent in both
        directions, a scene without its command is exactly the bug (#827).
        A non-empty annotation is a real change and keeps item and command
        together, as before.

        Both pending references are cleared first, so repeated
        cancel/deactivate/click calls are no-ops.
        """
        item = self._pending_item
        command = self._pending_command
        self._pending_item = None
        self._pending_command = None

        if item is None or command is None:
            return
        scene = self._view.scene()
        if scene is None or item.toPlainText().strip():
            return  # nothing pending, or a real annotation: keep item + command
        if not self._view.command_manager.discard(command):
            return  # interleaved: item stays in the scene with its command
        if item.scene() is not None:
            scene.removeItem(item)
