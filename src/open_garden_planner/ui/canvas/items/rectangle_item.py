"""Rectangle item for the garden canvas."""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsSceneContextMenuEvent, QMenu

from .garden_item import GardenItemMixin


class RectangleItem(GardenItemMixin, QGraphicsRectItem):
    """A rectangle shape on the garden canvas.

    Styled with green fill and darker green stroke.
    Supports selection and movement.
    """

    # Default styling
    FILL_COLOR = QColor(144, 238, 144, 100)  # #90EE90 with alpha 100
    STROKE_COLOR = QColor(34, 139, 34)  # #228B22
    STROKE_WIDTH = 2

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        """Initialize the rectangle item.

        Args:
            x: X coordinate of top-left corner
            y: Y coordinate of top-left corner
            width: Width of rectangle
            height: Height of rectangle
        """
        GardenItemMixin.__init__(self)
        QGraphicsRectItem.__init__(self, x, y, width, height)

        self._setup_styling()
        self._setup_flags()

    def _setup_styling(self) -> None:
        """Configure visual appearance."""
        pen = QPen(self.STROKE_COLOR)
        pen.setWidthF(self.STROKE_WIDTH)
        self.setPen(pen)

        brush = QBrush(self.FILL_COLOR)
        self.setBrush(brush)

    def _setup_flags(self) -> None:
        """Configure item interaction flags."""
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable, True)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu on right-click."""
        # Select this item if not already selected
        if not self.isSelected():
            self.scene().clearSelection()
            self.setSelected(True)

        menu = QMenu()

        # Delete action
        delete_action = menu.addAction("Delete")

        menu.addSeparator()

        # Placeholder actions
        duplicate_action = menu.addAction("Duplicate")
        duplicate_action.setEnabled(False)  # Placeholder

        properties_action = menu.addAction("Properties...")
        properties_action.setEnabled(False)  # Placeholder

        # Execute menu and handle result
        action = menu.exec(event.screenPos())

        if action == delete_action:
            # Delete this item and any other selected items
            scene = self.scene()
            for item in scene.selectedItems():
                scene.removeItem(item)

    @classmethod
    def from_rect(cls, rect: QRectF) -> "RectangleItem":
        """Create a RectangleItem from a QRectF.

        Args:
            rect: The rectangle geometry

        Returns:
            A new RectangleItem
        """
        return cls(rect.x(), rect.y(), rect.width(), rect.height())
