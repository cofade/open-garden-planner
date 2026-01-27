"""Selection tool for selecting and manipulating items."""

from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QMouseEvent, QPen
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsRectItem

from .base_tool import BaseTool, ToolType

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class SelectTool(BaseTool):
    """Tool for selecting items on the canvas.

    Features:
        - Click to select single item
        - Shift+click to add/remove from selection
        - Box selection with AutoCAD convention:
          - Left→right (enclosing): select only fully contained items
          - Right→left (crossing): select items that touch the box
    """

    tool_type = ToolType.SELECT
    display_name = "Select"
    shortcut = "V"
    cursor = Qt.CursorShape.ArrowCursor

    # Box selection colors
    ENCLOSING_COLOR = QColor(0, 120, 215)  # Blue for left-to-right
    CROSSING_COLOR = QColor(0, 180, 0)  # Green for right-to-left

    def __init__(self, view: "CanvasView") -> None:
        """Initialize the select tool."""
        super().__init__(view)
        self._box_start: QPointF | None = None
        self._box_item: QGraphicsRectItem | None = None
        self._is_box_selecting = False

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse press - start box selection if clicking on empty area."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        # Check if clicking on an item
        item = self._view.scene().itemAt(scene_pos, self._view.transform())

        if item is not None:
            # Handle Shift+click for multi-select toggle
            shift_held = event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            is_selectable = item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            if shift_held and is_selectable:
                item.setSelected(not item.isSelected())
                return True  # We handled it
            # Normal click - let QGraphicsView handle it
            return False

        # Clicking on empty area - start box selection
        self._box_start = scene_pos
        self._is_box_selecting = True

        # Clear selection unless Shift is held
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self._view.scene().clearSelection()

        return False  # Still let view process for proper event handling

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse move - update box selection rubber band."""
        if not self._is_box_selecting or self._box_start is None:
            return False

        # Determine selection direction
        is_left_to_right = scene_pos.x() >= self._box_start.x()

        # Create or update rubber band
        rect = self._make_rect(self._box_start, scene_pos)

        if self._box_item is None:
            self._box_item = QGraphicsRectItem()
            self._view.scene().addItem(self._box_item)

        self._box_item.setRect(rect)

        # Style based on direction
        if is_left_to_right:
            # Enclosing selection - solid border, light fill
            pen = QPen(self.ENCLOSING_COLOR, 1)
            pen.setCosmetic(True)
            brush = QBrush(QColor(self.ENCLOSING_COLOR.red(),
                                   self.ENCLOSING_COLOR.green(),
                                   self.ENCLOSING_COLOR.blue(), 30))
        else:
            # Crossing selection - dashed border, light fill
            pen = QPen(self.CROSSING_COLOR, 1, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            brush = QBrush(QColor(self.CROSSING_COLOR.red(),
                                   self.CROSSING_COLOR.green(),
                                   self.CROSSING_COLOR.blue(), 30))

        self._box_item.setPen(pen)
        self._box_item.setBrush(brush)

        return True  # We handled it

    def mouse_release(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Handle mouse release - complete box selection."""
        if not self._is_box_selecting or event.button() != Qt.MouseButton.LeftButton:
            return False

        if self._box_start is not None:
            # Determine selection mode
            is_left_to_right = scene_pos.x() >= self._box_start.x()
            rect = self._make_rect(self._box_start, scene_pos)

            # Only select if box has some size
            if rect.width() > 2 and rect.height() > 2:
                self._select_items_in_box(rect, is_left_to_right, event)

        # Clean up
        self._cleanup_box()

        return True

    def cancel(self) -> None:
        """Cancel box selection."""
        self._cleanup_box()

    def _cleanup_box(self) -> None:
        """Remove box selection visuals and reset state."""
        if self._box_item is not None:
            self._view.scene().removeItem(self._box_item)
            self._box_item = None
        self._box_start = None
        self._is_box_selecting = False

    def _make_rect(self, p1: QPointF, p2: QPointF) -> QRectF:
        """Create a normalized rectangle from two points."""
        x = min(p1.x(), p2.x())
        y = min(p1.y(), p2.y())
        w = abs(p2.x() - p1.x())
        h = abs(p2.y() - p1.y())
        return QRectF(x, y, w, h)

    def _select_items_in_box(
        self,
        rect: QRectF,
        enclosing: bool,
        event: QMouseEvent,
    ) -> None:
        """Select items based on box and selection mode.

        Args:
            rect: The selection rectangle
            enclosing: If True, only select fully enclosed items.
                      If False, select items that intersect (crossing).
            event: Mouse event (to check for Shift modifier)
        """
        add_to_selection = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        # Get all items in the scene
        scene = self._view.scene()

        for item in scene.items():
            # Skip non-selectable items and our own box item
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            if item is self._box_item:
                continue

            item_rect = item.sceneBoundingRect()

            # Enclosing mode: fully inside. Crossing mode: intersects.
            should_select = (
                rect.contains(item_rect) if enclosing else rect.intersects(item_rect)
            )

            if should_select:
                if add_to_selection:
                    # Toggle selection
                    item.setSelected(not item.isSelected())
                else:
                    item.setSelected(True)
