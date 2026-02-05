"""Resize and rotation handles for scaling and rotating garden items."""

import math
from enum import Enum, auto
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem as ParentItem


class HandlePosition(Enum):
    """Position of resize handle on an item's bounding rect."""

    TOP_LEFT = auto()
    TOP_CENTER = auto()
    TOP_RIGHT = auto()
    MIDDLE_LEFT = auto()
    MIDDLE_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_CENTER = auto()
    BOTTOM_RIGHT = auto()


# Map handle positions to cursor shapes
HANDLE_CURSORS = {
    HandlePosition.TOP_LEFT: Qt.CursorShape.SizeFDiagCursor,
    HandlePosition.TOP_RIGHT: Qt.CursorShape.SizeBDiagCursor,
    HandlePosition.BOTTOM_LEFT: Qt.CursorShape.SizeBDiagCursor,
    HandlePosition.BOTTOM_RIGHT: Qt.CursorShape.SizeFDiagCursor,
    HandlePosition.TOP_CENTER: Qt.CursorShape.SizeVerCursor,
    HandlePosition.BOTTOM_CENTER: Qt.CursorShape.SizeVerCursor,
    HandlePosition.MIDDLE_LEFT: Qt.CursorShape.SizeHorCursor,
    HandlePosition.MIDDLE_RIGHT: Qt.CursorShape.SizeHorCursor,
}

# Minimum size in centimeters
MINIMUM_SIZE_CM = 1.0

# Handle visual settings
HANDLE_SIZE = 8.0  # pixels (cosmetic)
HANDLE_COLOR = QColor(0, 120, 215)  # Blue
HANDLE_HOVER_COLOR = QColor(0, 180, 255)  # Lighter blue
HANDLE_BORDER_COLOR = QColor(255, 255, 255)  # White border

# Rotation handle settings
ROTATION_HANDLE_OFFSET = 25.0  # pixels above the top center
ROTATION_HANDLE_SIZE = 10.0  # pixels (cosmetic)
ROTATION_HANDLE_COLOR = QColor(46, 204, 113)  # Green
ROTATION_HANDLE_HOVER_COLOR = QColor(88, 214, 141)  # Lighter green
ROTATION_SNAP_ANGLE = 15.0  # degrees for snapping when Shift is held


class DimensionDisplay(QGraphicsItem):
    """Display widget showing dimensions during resize operation.

    Shows width x height in a tooltip-like box near the cursor.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        """Initialize dimension display."""
        super().__init__(parent)

        # Create background box
        self._background = QGraphicsPathItem(self)
        self._background.setPen(QPen(QColor(60, 60, 60), 1))
        self._background.setBrush(QBrush(QColor(240, 240, 240, 230)))

        # Create text item
        self._text = QGraphicsSimpleTextItem(self)
        font = QFont("Segoe UI", 9)
        self._text.setFont(font)
        self._text.setBrush(QBrush(QColor(0, 0, 0)))

        # Make it render at fixed screen size
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(2000)  # Above everything

        self.hide()

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return self.childrenBoundingRect()

    def paint(self, painter, option, widget=None) -> None:
        """Paint method (required by QGraphicsItem)."""
        pass

    def update_dimensions(self, width: float, height: float, pos: QPointF) -> None:
        """Update the displayed dimensions.

        Args:
            width: Width in centimeters
            height: Height in centimeters
            pos: Position in scene coordinates to display near
        """
        # Format dimensions (convert cm to m if > 100cm)
        width_str = f"{width / 100:.2f}m" if width >= 100 else f"{width:.1f}cm"
        height_str = f"{height / 100:.2f}m" if height >= 100 else f"{height:.1f}cm"

        # Set text
        text = f"{width_str} × {height_str}"
        self._text.setText(text)

        # Update background size based on text
        text_rect = self._text.boundingRect()
        padding = 6
        bg_rect = text_rect.adjusted(-padding, -padding, padding, padding)

        path = QPainterPath()
        path.addRoundedRect(bg_rect, 4, 4)
        self._background.setPath(path)

        # Position text within background
        self._text.setPos(bg_rect.left() + padding, bg_rect.top() + padding)

        # Position the display near the cursor
        self.setPos(pos.x() + 15, pos.y() + 15)

        # Show the display
        self.show()

    def hide_display(self) -> None:
        """Hide the dimension display."""
        self.hide()


class ResizeHandle(QGraphicsRectItem):
    """A draggable handle for resizing items.

    Handles are displayed at corners and edges of selected items.
    Corner handles resize proportionally, edge handles resize single dimension.
    """

    def __init__(
        self,
        position: HandlePosition,
        parent: "ParentItem",
    ) -> None:
        """Initialize the resize handle.

        Args:
            position: Which position this handle occupies
            parent: The parent item this handle belongs to
        """
        super().__init__(parent)
        self._position = position
        self._parent_item = parent
        self._is_dragging = False
        self._drag_start_pos: QPointF | None = None
        self._initial_rect: QRectF | None = None
        self._initial_parent_pos: QPointF | None = None

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the handle."""
        # Set size - uses scene coordinates but we want fixed visual size
        half_size = HANDLE_SIZE / 2.0
        self.setRect(-half_size, -half_size, HANDLE_SIZE, HANDLE_SIZE)

        # Style
        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(HANDLE_COLOR))

        # Make handle render at fixed screen size regardless of zoom
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(HANDLE_CURSORS.get(self._position, Qt.CursorShape.ArrowCursor))
        # Z-value above parent
        self.setZValue(1000)

    @property
    def handle_position(self) -> HandlePosition:
        """Get the position of this handle."""
        return self._position

    def update_position(self) -> None:
        """Update handle position based on parent's bounding rect."""
        if self._parent_item is None:
            return

        rect = self._parent_item.boundingRect()

        # Calculate position based on handle position
        positions = {
            HandlePosition.TOP_LEFT: QPointF(rect.left(), rect.top()),
            HandlePosition.TOP_CENTER: QPointF(rect.center().x(), rect.top()),
            HandlePosition.TOP_RIGHT: QPointF(rect.right(), rect.top()),
            HandlePosition.MIDDLE_LEFT: QPointF(rect.left(), rect.center().y()),
            HandlePosition.MIDDLE_RIGHT: QPointF(rect.right(), rect.center().y()),
            HandlePosition.BOTTOM_LEFT: QPointF(rect.left(), rect.bottom()),
            HandlePosition.BOTTOM_CENTER: QPointF(rect.center().x(), rect.bottom()),
            HandlePosition.BOTTOM_RIGHT: QPointF(rect.right(), rect.bottom()),
        }

        pos = positions.get(self._position, QPointF(0, 0))
        self.setPos(pos)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Highlight handle on hover."""
        self.setBrush(QBrush(HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Remove highlight when hover ends."""
        self.setBrush(QBrush(HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Start resize operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial geometry
            if self._parent_item is not None:
                self._initial_rect = self._parent_item.boundingRect()
                self._initial_parent_pos = self._parent_item.pos()

                # Notify parent that resize is starting
                if hasattr(self._parent_item, '_on_resize_start'):
                    self._parent_item._on_resize_start()

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle resize during drag."""
        if not self._is_dragging or self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return

        if self._parent_item is None or self._initial_rect is None:
            return

        # Calculate delta in scene coordinates
        current_pos = event.scenePos()
        delta = current_pos - self._drag_start_pos

        # Apply resize based on handle position
        self._apply_resize(delta)

        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Complete resize operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False

            # Hide dimension display
            if (self._parent_item is not None and
                hasattr(self._parent_item, '_dimension_display') and
                self._parent_item._dimension_display is not None):
                self._parent_item._dimension_display.hide_display()

            # Notify parent that resize is complete
            if self._parent_item is not None and hasattr(self._parent_item, '_on_resize_end'):
                self._parent_item._on_resize_end(
                    self._initial_rect,
                    self._initial_parent_pos,
                )

            self._drag_start_pos = None
            self._initial_rect = None
            self._initial_parent_pos = None

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _apply_resize(self, delta: QPointF) -> None:
        """Apply the resize transformation based on handle position and delta.

        Args:
            delta: Movement delta in scene coordinates
        """
        if self._parent_item is None or self._initial_rect is None:
            return
        if self._initial_parent_pos is None:
            return

        # Get initial values
        init_rect = self._initial_rect
        init_pos = self._initial_parent_pos

        # Calculate new rect based on which handle is being dragged
        new_x = init_rect.x()
        new_y = init_rect.y()
        new_width = init_rect.width()
        new_height = init_rect.height()
        pos_dx = 0.0
        pos_dy = 0.0

        # Determine what changes based on handle position
        if self._position in {
            HandlePosition.TOP_LEFT,
            HandlePosition.MIDDLE_LEFT,
            HandlePosition.BOTTOM_LEFT,
        }:
            # Left handles: adjust x and width
            new_width = init_rect.width() - delta.x()
            if new_width >= MINIMUM_SIZE_CM:
                pos_dx = delta.x()
            else:
                new_width = MINIMUM_SIZE_CM
                pos_dx = init_rect.width() - MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.TOP_RIGHT,
            HandlePosition.MIDDLE_RIGHT,
            HandlePosition.BOTTOM_RIGHT,
        }:
            # Right handles: adjust width only
            new_width = init_rect.width() + delta.x()
            if new_width < MINIMUM_SIZE_CM:
                new_width = MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.TOP_LEFT,
            HandlePosition.TOP_CENTER,
            HandlePosition.TOP_RIGHT,
        }:
            # Top handles: adjust y and height
            new_height = init_rect.height() - delta.y()
            if new_height >= MINIMUM_SIZE_CM:
                pos_dy = delta.y()
            else:
                new_height = MINIMUM_SIZE_CM
                pos_dy = init_rect.height() - MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.BOTTOM_LEFT,
            HandlePosition.BOTTOM_CENTER,
            HandlePosition.BOTTOM_RIGHT,
        }:
            # Bottom handles: adjust height only
            new_height = init_rect.height() + delta.y()
            if new_height < MINIMUM_SIZE_CM:
                new_height = MINIMUM_SIZE_CM

        # Ensure minimum size
        new_width = max(new_width, MINIMUM_SIZE_CM)
        new_height = max(new_height, MINIMUM_SIZE_CM)

        # Update dimension display
        if (hasattr(self._parent_item, '_dimension_display') and
            self._parent_item._dimension_display is not None):
            # Get cursor position for display
            cursor_pos = self.scenePos()
            self._parent_item._dimension_display.update_dimensions(
                new_width,
                new_height,
                cursor_pos,
            )

        # Apply the resize to parent
        if hasattr(self._parent_item, '_apply_resize'):
            self._parent_item._apply_resize(
                new_x,
                new_y,
                new_width,
                new_height,
                init_pos.x() + pos_dx,
                init_pos.y() + pos_dy,
            )


class AngleDisplay(QGraphicsItem):
    """Display widget showing rotation angle during rotation operation.

    Shows the angle in degrees in a tooltip-like box near the cursor.
    """

    def __init__(self, parent: QGraphicsItem | None = None) -> None:
        """Initialize angle display."""
        super().__init__(parent)

        # Create background box
        self._background = QGraphicsPathItem(self)
        self._background.setPen(QPen(QColor(46, 125, 50), 1))
        self._background.setBrush(QBrush(QColor(232, 245, 233, 230)))

        # Create text item
        self._text = QGraphicsSimpleTextItem(self)
        font = QFont("Segoe UI", 9)
        self._text.setFont(font)
        self._text.setBrush(QBrush(QColor(0, 0, 0)))

        # Make it render at fixed screen size
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(2000)  # Above everything

        self.hide()

    def boundingRect(self) -> QRectF:
        """Return bounding rectangle."""
        return self.childrenBoundingRect()

    def paint(self, painter, option, widget=None) -> None:
        """Paint method (required by QGraphicsItem)."""
        pass

    def update_angle(self, angle: float, pos: QPointF) -> None:
        """Update the displayed angle.

        Args:
            angle: Angle in degrees
            pos: Position in scene coordinates to display near
        """
        # Normalize angle to 0-360
        display_angle = angle % 360
        if display_angle < 0:
            display_angle += 360

        # Set text
        text = f"{display_angle:.1f}°"
        self._text.setText(text)

        # Update background size based on text
        text_rect = self._text.boundingRect()
        padding = 6
        bg_rect = text_rect.adjusted(-padding, -padding, padding, padding)

        path = QPainterPath()
        path.addRoundedRect(bg_rect, 4, 4)
        self._background.setPath(path)

        # Position text within background
        self._text.setPos(bg_rect.left() + padding, bg_rect.top() + padding)

        # Position the display near the cursor
        self.setPos(pos.x() + 15, pos.y() + 15)

        # Show the display
        self.show()

    def hide_display(self) -> None:
        """Hide the angle display."""
        self.hide()


class RotationHandle(QGraphicsEllipseItem):
    """A circular handle for rotating items.

    Displayed above the item's top center when selected.
    Dragging rotates the item around its center.
    """

    def __init__(self, parent: "ParentItem") -> None:
        """Initialize the rotation handle.

        Args:
            parent: The parent item this handle belongs to
        """
        super().__init__(parent)
        self._parent_item = parent
        self._is_dragging = False
        self._drag_start_pos: QPointF | None = None
        self._initial_angle: float = 0.0
        self._center: QPointF = QPointF(0, 0)

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the handle."""
        # Set size - circular handle
        half_size = ROTATION_HANDLE_SIZE / 2.0
        self.setRect(-half_size, -half_size, ROTATION_HANDLE_SIZE, ROTATION_HANDLE_SIZE)

        # Style
        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(ROTATION_HANDLE_COLOR))

        # Make handle render at fixed screen size regardless of zoom
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        # Z-value above parent and resize handles
        self.setZValue(1001)

    def update_position(self) -> None:
        """Update handle position above the parent's bounding rect center-top."""
        if self._parent_item is None:
            return

        rect = self._parent_item.boundingRect()

        # Position above the top center
        # Since we use ItemIgnoresTransformations, we need to account for view scale
        view = None
        if self._parent_item.scene():
            views = self._parent_item.scene().views()
            if views:
                view = views[0]

        # Calculate offset in scene coordinates
        offset = ROTATION_HANDLE_OFFSET
        if view:
            # Adjust offset based on view transform
            scale = view.transform().m11()
            if scale > 0:
                offset = ROTATION_HANDLE_OFFSET / scale

        pos = QPointF(rect.center().x(), rect.top() - offset)
        self.setPos(pos)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Highlight handle on hover."""
        self.setBrush(QBrush(ROTATION_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Remove highlight when hover ends."""
        self.setBrush(QBrush(ROTATION_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Start rotation operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial rotation angle and calculate center
            if self._parent_item is not None:
                rect = self._parent_item.boundingRect()
                # Get center in scene coordinates
                self._center = self._parent_item.mapToScene(rect.center())

                # Get initial rotation angle of the item
                if hasattr(self._parent_item, 'rotation_angle'):
                    self._initial_angle = self._parent_item.rotation_angle
                else:
                    self._initial_angle = self._parent_item.rotation()

                # Notify parent that rotation is starting
                if hasattr(self._parent_item, '_on_rotation_start'):
                    self._parent_item._on_rotation_start()

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle rotation during drag."""
        if not self._is_dragging or self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return

        if self._parent_item is None:
            return

        current_pos = event.scenePos()

        # Calculate angles from center to start and current positions
        start_angle = math.atan2(
            self._drag_start_pos.y() - self._center.y(),
            self._drag_start_pos.x() - self._center.x()
        )
        current_angle = math.atan2(
            current_pos.y() - self._center.y(),
            current_pos.x() - self._center.x()
        )

        # Calculate delta in degrees
        delta_degrees = math.degrees(current_angle - start_angle)
        new_angle = self._initial_angle + delta_degrees

        # Check if Shift is held for 15° snapping
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            new_angle = round(new_angle / ROTATION_SNAP_ANGLE) * ROTATION_SNAP_ANGLE

        # Apply the rotation
        self._apply_rotation(new_angle, current_pos)

        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Complete rotation operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False

            # Hide angle display
            if (self._parent_item is not None and
                hasattr(self._parent_item, '_angle_display') and
                self._parent_item._angle_display is not None):
                self._parent_item._angle_display.hide_display()

            # Notify parent that rotation is complete
            if self._parent_item is not None and hasattr(self._parent_item, '_on_rotation_end'):
                self._parent_item._on_rotation_end(self._initial_angle)

            self._drag_start_pos = None

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _apply_rotation(self, angle: float, cursor_pos: QPointF) -> None:
        """Apply the rotation transformation.

        Args:
            angle: New rotation angle in degrees
            cursor_pos: Current cursor position for angle display
        """
        if self._parent_item is None:
            return

        # Update angle display
        if (hasattr(self._parent_item, '_angle_display') and
            self._parent_item._angle_display is not None):
            self._parent_item._angle_display.update_angle(angle, cursor_pos)

        # Apply rotation to parent
        if hasattr(self._parent_item, '_apply_rotation'):
            self._parent_item._apply_rotation(angle)


class ResizeHandlesMixin:
    """Mixin that adds resize handle functionality to garden items.

    This mixin provides methods to create, show, hide, and manage
    resize handles for any item type.
    """

    _resize_handles: list[ResizeHandle]
    _resize_initial_rect: QRectF | None
    _resize_initial_pos: QPointF | None
    _dimension_display: DimensionDisplay | None

    def init_resize_handles(self) -> None:
        """Initialize resize handles (call in subclass __init__)."""
        self._resize_handles = []
        self._resize_initial_rect = None
        self._resize_initial_pos = None
        self._dimension_display = None

    def create_resize_handles(self) -> None:
        """Create all 8 resize handles as child items."""
        if not hasattr(self, '_resize_handles'):
            self._resize_handles = []

        # Remove any existing handles
        self.remove_resize_handles()

        # Create handles for all 8 positions
        for position in HandlePosition:
            handle = ResizeHandle(position, self)  # type: ignore[arg-type]
            handle.update_position()
            self._resize_handles.append(handle)

        # Create dimension display if it doesn't exist
        if not hasattr(self, '_dimension_display') or self._dimension_display is None:
            scene = getattr(self, 'scene', lambda: None)()
            if scene is not None:
                self._dimension_display = DimensionDisplay()
                scene.addItem(self._dimension_display)
                self._dimension_display.hide()

    def remove_resize_handles(self) -> None:
        """Remove all resize handles."""
        if not hasattr(self, '_resize_handles'):
            return

        for handle in self._resize_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._resize_handles = []

        # Remove dimension display
        if hasattr(self, '_dimension_display') and self._dimension_display is not None:
            if self._dimension_display.scene() is not None:
                self._dimension_display.scene().removeItem(self._dimension_display)
            self._dimension_display = None

    def update_resize_handles(self) -> None:
        """Update positions of all resize handles."""
        if not hasattr(self, '_resize_handles'):
            return

        for handle in self._resize_handles:
            handle.update_position()

    def show_resize_handles(self) -> None:
        """Show all resize handles."""
        if not hasattr(self, '_resize_handles') or not self._resize_handles:
            self.create_resize_handles()

        for handle in self._resize_handles:
            handle.show()

    def hide_resize_handles(self) -> None:
        """Hide all resize handles."""
        if not hasattr(self, '_resize_handles'):
            return

        for handle in self._resize_handles:
            handle.hide()

    def _on_resize_start(self) -> None:
        """Called when a resize operation starts."""
        # Store initial state for undo
        if hasattr(self, 'boundingRect'):
            self._resize_initial_rect = self.boundingRect()  # type: ignore[attr-defined]
        if hasattr(self, 'pos'):
            self._resize_initial_pos = self.pos()  # type: ignore[attr-defined]

    def _on_resize_end(
        self,
        initial_rect: QRectF | None,
        initial_pos: QPointF | None,
    ) -> None:
        """Called when a resize operation completes.

        Override in subclass to register undo command.
        """
        pass

    def _apply_resize(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        pos_x: float,
        pos_y: float,
    ) -> None:
        """Apply a resize transformation.

        Override in subclass to implement type-specific resizing.

        Args:
            x: New x position of bounding rect (in item coords)
            y: New y position of bounding rect (in item coords)
            width: New width
            height: New height
            pos_x: New scene x position
            pos_y: New scene y position
        """
        pass


class RotationHandleMixin:
    """Mixin that adds rotation handle functionality to garden items.

    This mixin provides methods to create, show, hide, and manage
    the rotation handle for any item type.
    """

    _rotation_handle: RotationHandle | None
    _rotation_initial_angle: float
    _rotation_angle: float
    _angle_display: AngleDisplay | None

    def init_rotation_handle(self) -> None:
        """Initialize rotation handle (call in subclass __init__)."""
        self._rotation_handle = None
        self._rotation_initial_angle = 0.0
        self._rotation_angle = 0.0
        self._angle_display = None

    @property
    def rotation_angle(self) -> float:
        """Get the current rotation angle in degrees."""
        return self._rotation_angle

    @rotation_angle.setter
    def rotation_angle(self, value: float) -> None:
        """Set the rotation angle in degrees."""
        self._rotation_angle = value

    def create_rotation_handle(self) -> None:
        """Create the rotation handle as a child item."""
        if not hasattr(self, '_rotation_handle'):
            self._rotation_handle = None

        # Remove existing handle
        self.remove_rotation_handle()

        # Create handle
        self._rotation_handle = RotationHandle(self)  # type: ignore[arg-type]
        self._rotation_handle.update_position()

        # Create angle display if it doesn't exist
        if not hasattr(self, '_angle_display') or self._angle_display is None:
            scene = getattr(self, 'scene', lambda: None)()
            if scene is not None:
                self._angle_display = AngleDisplay()
                scene.addItem(self._angle_display)
                self._angle_display.hide()

    def remove_rotation_handle(self) -> None:
        """Remove the rotation handle."""
        if not hasattr(self, '_rotation_handle') or self._rotation_handle is None:
            return

        if self._rotation_handle.scene() is not None:
            self._rotation_handle.scene().removeItem(self._rotation_handle)
        self._rotation_handle = None

        # Remove angle display
        if hasattr(self, '_angle_display') and self._angle_display is not None:
            if self._angle_display.scene() is not None:
                self._angle_display.scene().removeItem(self._angle_display)
            self._angle_display = None

    def update_rotation_handle(self) -> None:
        """Update position of the rotation handle."""
        if not hasattr(self, '_rotation_handle') or self._rotation_handle is None:
            return

        self._rotation_handle.update_position()

    def show_rotation_handle(self) -> None:
        """Show the rotation handle."""
        if not hasattr(self, '_rotation_handle') or self._rotation_handle is None:
            self.create_rotation_handle()

        if self._rotation_handle is not None:
            self._rotation_handle.show()

    def hide_rotation_handle(self) -> None:
        """Hide the rotation handle."""
        if not hasattr(self, '_rotation_handle') or self._rotation_handle is None:
            return

        self._rotation_handle.hide()

    def _on_rotation_start(self) -> None:
        """Called when a rotation operation starts."""
        # Store initial angle for undo
        self._rotation_initial_angle = self._rotation_angle

    def _on_rotation_end(self, initial_angle: float) -> None:
        """Called when a rotation operation completes.

        Override in subclass to register undo command.

        Args:
            initial_angle: The angle before rotation started
        """
        pass

    def _apply_rotation(self, angle: float) -> None:
        """Apply a rotation transformation.

        Args:
            angle: New rotation angle in degrees
        """
        self._rotation_angle = angle

        # Apply the rotation transform to the item
        if hasattr(self, 'setRotation'):
            # Get the center of the bounding rect for rotation pivot
            if hasattr(self, 'boundingRect'):
                rect = self.boundingRect()  # type: ignore[attr-defined]
                center = rect.center()

                # Set transform origin to center
                if hasattr(self, 'setTransformOriginPoint'):
                    self.setTransformOriginPoint(center)  # type: ignore[attr-defined]

            self.setRotation(angle)  # type: ignore[attr-defined]

        # Update handles
        if hasattr(self, 'update_resize_handles'):
            self.update_resize_handles()  # type: ignore[attr-defined]
        self.update_rotation_handle()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]
