"""Callout annotation tool — click target, drag to text box position."""

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QT_TR_NOOP, QCoreApplication, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsLineItem

from .base_tool import BaseTool, ToolType
from .preview_z import PREVIEW_Z_LINE

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CancellablePlacement, CanvasView
    from open_garden_planner.ui.canvas.items.callout_item import CalloutItem


class CalloutTool(BaseTool):
    """Tool for placing callout annotations with a leader line.

    Click to set the arrow tip, drag to position the text box,
    release to place.  The new item immediately enters text-edit mode.
    """

    tool_type = ToolType.CALLOUT
    display_name = QT_TR_NOOP("Callout")
    shortcut = ""
    cursor = Qt.CursorShape.CrossCursor

    def _translated_name(self) -> str:
        return QCoreApplication.translate("CalloutTool", "Callout")

    def __init__(self, view: "CanvasView") -> None:
        super().__init__(view)
        self._target: QPointF | None = None
        self._preview: QGraphicsLineItem | None = None
        # The placed callout's command + document snapshot, so Escape on an
        # empty annotation can withdraw both (#904), exactly like the Text
        # tool did in #827.
        self._pending: CancellablePlacement | None = None

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        # A new drag also finishes a previous annotation: an empty one leaves
        # no trace (#904), a typed one is committed.
        self.cancel()
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
            self._preview.setZValue(PREVIEW_Z_LINE)
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
        self._target = None

        from open_garden_planner.ui.canvas.items.callout_item import CalloutItem

        scene = self._view.scene()
        layer_id = (
            scene.active_layer.id
            if hasattr(scene, "active_layer") and scene.active_layer
            else None
        )
        item = CalloutItem(target, box_offset, content="", layer_id=layer_id)
        self._pending = self._view.add_cancellable_item(item, "callout")
        item.start_editing()
        return True

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            self._view.set_active_tool(ToolType.SELECT)
            return True
        return False

    def cancel(self) -> None:
        """Cancel the drag or a pending empty callout (#904).

        Empty mirrors the Text tool's #827 rule: the placement's
        ``CreateItemCommand`` is discarded first and the item leaves with it,
        so an Escape on an annotation with no text leaves neither a blank
        callout nor a ghost history entry. A callout that has text is
        committed and kept, exactly like a text note.
        """
        self._cleanup_preview()
        self._target = None

        pending, self._pending = self._pending, None
        if pending is None:
            return
        item = cast("CalloutItem", pending.item)
        try:
            item.finish_editing()
            has_text = bool(item.content.strip())
        except RuntimeError:
            # The item died with a document replacement: nothing to keep.
            has_text = False
        if has_text:
            self._view.commit_cancellable_placement(pending)
            return
        self._view.discard_cancellable_placement(pending)

    def _cleanup_preview(self) -> None:
        if self._preview is not None:
            scene = self._view.scene()
            if scene and self._preview.scene() is not None:
                scene.removeItem(self._preview)
            self._preview = None
