"""Text annotation tool."""

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CancellablePlacement, CanvasView
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
        # The placement command AND the document-state snapshot that let an
        # empty cancellation leave no trace at all (#827, #909). One object
        # so the pair cannot drift apart.
        self._pending: CancellablePlacement | None = None

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
        self._pending = self._view.add_cancellable_item(item, "text")
        item.editing_finished.connect(self.cancel)
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
        """Cancel a pending text annotation, keeping scene, history and dirty state in step.

        The placement click already executed its ``CreateItemCommand``, so
        removing the item from the scene alone left the command on the undo
        stack (#827). ``CanvasView.discard_cancellable_placement`` discards the
        command first and removes the item only when the discard proved the
        command left the stack; it suppresses the withdrawal's own plan changes
        and guards restoration of the document's dirty flag, so click + Esc on a clean plan
        leaves it clean (#909).

        A note that has text is a real change: it is committed first (the
        placement can end without a focus-out — a tool switch, a click that
        starts the next annotation), then item and command are kept together.

        Interleaving fallback: if another command was pushed on top in the
        meantime, ``discard`` refuses (LIFO identity guard) and the empty item
        STAYS in the scene — an item-plus-command pair is consistent in both
        directions, a scene without its command is exactly the bug (#827).

        The pending reference is cleared first, so repeated
        cancel/deactivate/click calls are no-ops.
        """
        pending, self._pending = self._pending, None
        if pending is None:
            return
        item = cast("TextItem", pending.item)
        try:
            item.editing_finished.disconnect(self.cancel)
            item.finish_editing()
            has_text = bool(item.content.strip())
        except RuntimeError:
            # The item died with a document replacement: nothing to keep.
            has_text = False
        if has_text:
            self._view.commit_cancellable_placement(pending)
            return  # a real annotation: keep item + command
        self._view.discard_cancellable_placement(pending)
