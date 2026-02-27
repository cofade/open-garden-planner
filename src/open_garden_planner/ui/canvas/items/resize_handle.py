"""Resize and rotation handles for scaling and rotating garden items."""

import math
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QMenu,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem as ParentItem


def _clamp_pos_to_canvas(pos: QPointF, parent_item: QGraphicsItem) -> QPointF:
    """Clamp a scene position to the canvas boundaries.

    Args:
        pos: Position in scene coordinates
        parent_item: An item whose scene has a canvas_rect property

    Returns:
        Position clamped to canvas rect, or original if no canvas rect available
    """
    scene = parent_item.scene() if parent_item else None
    if scene is not None and hasattr(scene, 'canvas_rect'):
        canvas_rect = scene.canvas_rect
        x = max(canvas_rect.left(), min(pos.x(), canvas_rect.right()))
        y = max(canvas_rect.top(), min(pos.y(), canvas_rect.bottom()))
        return QPointF(x, y)
    return pos


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


def _is_item_fixed(item: "QGraphicsItem") -> bool:
    """Return True if item has a FIXED constraint in the scene's constraint graph."""
    scene = item.scene() if item is not None else None
    if scene is None or not hasattr(scene, "constraint_graph"):
        return False
    item_id = getattr(item, "item_id", None)
    if item_id is None:
        return False
    from open_garden_planner.core.constraints import ConstraintType  # noqa: PLC0415

    for c in scene.constraint_graph.constraints.values():
        if c.constraint_type == ConstraintType.FIXED and c.anchor_a.item_id == item_id:
            return True
    return False


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
            if self._parent_item is not None and _is_item_fixed(self._parent_item):
                event.ignore()
                return
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

        # Calculate delta in scene coordinates, clamped to canvas
        current_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)
        delta = current_pos - self._drag_start_pos

        # Apply resize based on handle position
        self._apply_resize(delta)

        # Propagate to EQUAL-constrained partners in real time
        if self._parent_item is not None and hasattr(self._parent_item, '_propagate_equal_resize_live'):
            self._parent_item._propagate_equal_resize_live()

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

        # Transform delta from scene coordinates to item-local coordinates
        # to account for rotation. Without this, dragging a resize handle on
        # a rotated object would move the object instead of just resizing it.
        rotation = self._parent_item.rotation()
        if rotation != 0.0:
            angle_rad = math.radians(rotation)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            # Inverse rotation: scene -> local
            local_dx = delta.x() * cos_a + delta.y() * sin_a
            local_dy = -delta.x() * sin_a + delta.y() * cos_a
        else:
            cos_a = 1.0
            sin_a = 0.0
            local_dx = delta.x()
            local_dy = delta.y()

        # Calculate new rect based on which handle is being dragged
        new_x = init_rect.x()
        new_y = init_rect.y()
        new_width = init_rect.width()
        new_height = init_rect.height()
        pos_dx = 0.0
        pos_dy = 0.0

        # Determine what changes based on handle position (using local delta)
        if self._position in {
            HandlePosition.TOP_LEFT,
            HandlePosition.MIDDLE_LEFT,
            HandlePosition.BOTTOM_LEFT,
        }:
            # Left handles: adjust x and width
            new_width = init_rect.width() - local_dx
            if new_width >= MINIMUM_SIZE_CM:
                pos_dx = local_dx
            else:
                new_width = MINIMUM_SIZE_CM
                pos_dx = init_rect.width() - MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.TOP_RIGHT,
            HandlePosition.MIDDLE_RIGHT,
            HandlePosition.BOTTOM_RIGHT,
        }:
            # Right handles: adjust width only
            new_width = init_rect.width() + local_dx
            if new_width < MINIMUM_SIZE_CM:
                new_width = MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.TOP_LEFT,
            HandlePosition.TOP_CENTER,
            HandlePosition.TOP_RIGHT,
        }:
            # Top handles: adjust y and height
            new_height = init_rect.height() - local_dy
            if new_height >= MINIMUM_SIZE_CM:
                pos_dy = local_dy
            else:
                new_height = MINIMUM_SIZE_CM
                pos_dy = init_rect.height() - MINIMUM_SIZE_CM

        if self._position in {
            HandlePosition.BOTTOM_LEFT,
            HandlePosition.BOTTOM_CENTER,
            HandlePosition.BOTTOM_RIGHT,
        }:
            # Bottom handles: adjust height only
            new_height = init_rect.height() + local_dy
            if new_height < MINIMUM_SIZE_CM:
                new_height = MINIMUM_SIZE_CM

        # Ensure minimum size
        new_width = max(new_width, MINIMUM_SIZE_CM)
        new_height = max(new_height, MINIMUM_SIZE_CM)

        # Transform local position offset back to scene coordinates
        # Forward rotation: local -> scene
        scene_pos_dx = pos_dx * cos_a - pos_dy * sin_a
        scene_pos_dy = pos_dx * sin_a + pos_dy * cos_a

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
                init_pos.x() + scene_pos_dx,
                init_pos.y() + scene_pos_dy,
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
            if self._parent_item is not None and _is_item_fixed(self._parent_item):
                event.ignore()
                return
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

        # Update positions in case geometry changed (e.g., after vertex editing)
        self.update_resize_handles()

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
        # Capture EQUAL-constrained partner sizes before any propagation (for undo)
        scene = self.scene() if hasattr(self, 'scene') else None  # type: ignore[attr-defined]
        if scene is not None and hasattr(self, 'item_id'):
            from open_garden_planner.core.tools.constraint_tool import (
                _capture_equal_partner_pre_states,  # noqa: PLC0415
            )
            self._equal_partner_pre_states: list = _capture_equal_partner_pre_states(self, scene)
        else:
            self._equal_partner_pre_states = []

    def _propagate_equal_resize_live(self) -> None:
        """Apply EQUAL-constraint propagation to partners during resize drag.

        Guards against re-entrancy so propagation on a partner does not trigger
        a second round of propagation back to this item.
        """
        if getattr(self, '_propagating_equal_resize', False):
            return
        scene = self.scene() if hasattr(self, 'scene') else None  # type: ignore[attr-defined]
        if scene is None:
            return
        self._propagating_equal_resize = True  # type: ignore[attr-defined]
        try:
            from open_garden_planner.core.tools.constraint_tool import (
                _apply_equal_propagation_live,  # noqa: PLC0415
            )
            _apply_equal_propagation_live(self, scene)
        finally:
            self._propagating_equal_resize = False  # type: ignore[attr-defined]

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


# Rectangle corner positions for vertex editing
class RectCorner(Enum):
    """Position of vertex handle on a rectangle's corners."""

    TOP_LEFT = auto()
    TOP_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_RIGHT = auto()


# Vertex editing handle settings
VERTEX_HANDLE_SIZE = 8.0  # pixels (cosmetic)
VERTEX_HANDLE_COLOR = QColor(255, 165, 0)  # Orange for vertices
VERTEX_HANDLE_HOVER_COLOR = QColor(255, 200, 100)  # Lighter orange
MIDPOINT_HANDLE_SIZE = 6.0  # pixels (cosmetic) - smaller than vertex handles
MIDPOINT_HANDLE_COLOR = QColor(100, 100, 100)  # Gray for midpoints
MIDPOINT_HANDLE_HOVER_COLOR = QColor(150, 150, 150)  # Lighter gray

# Annotation settings
ANNOTATION_FONT_SIZE = 8
ANNOTATION_TEXT_COLOR = QColor(40, 40, 40)
ANNOTATION_BG_COLOR = QColor(255, 255, 230, 200)  # Light yellow, semi-transparent
ANNOTATION_BORDER_COLOR = QColor(180, 180, 150)
ANNOTATION_VERTEX_OFFSET = 12.0  # pixels offset from vertex handle
ANNOTATION_EDGE_OFFSET = 8.0  # pixels offset from edge midpoint
MINIMUM_VERTICES = 3  # Cannot delete below this count


class VertexHandle(QGraphicsRectItem):
    """A draggable handle for moving polygon vertices.

    Displayed at each vertex when in vertex edit mode.
    """

    def __init__(
        self,
        vertex_index: int,
        parent: "ParentItem",
    ) -> None:
        """Initialize the vertex handle.

        Args:
            vertex_index: Index of the vertex this handle represents
            parent: The parent polygon item
        """
        super().__init__(parent)
        self._vertex_index = vertex_index
        self._parent_item = parent
        self._is_dragging = False
        self._drag_start_pos: QPointF | None = None
        self._initial_vertex_pos: QPointF | None = None

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the handle."""
        half_size = VERTEX_HANDLE_SIZE / 2.0
        self.setRect(-half_size, -half_size, VERTEX_HANDLE_SIZE, VERTEX_HANDLE_SIZE)

        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))

        # Make handle render at fixed screen size regardless of zoom
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setZValue(1002)  # Above rotation and resize handles

    @property
    def vertex_index(self) -> int:
        """Get the vertex index this handle represents."""
        return self._vertex_index

    @vertex_index.setter
    def vertex_index(self, value: int) -> None:
        """Set the vertex index."""
        self._vertex_index = value

    def update_position(self, pos: QPointF) -> None:
        """Update handle position to a specific point.

        Args:
            pos: Position in parent item coordinates
        """
        self.setPos(pos)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Highlight handle on hover."""
        self.setBrush(QBrush(VERTEX_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Remove highlight when hover ends."""
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Start vertex drag operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial vertex position
            if self._parent_item is not None and hasattr(self._parent_item, '_get_vertex_position'):
                self._initial_vertex_pos = self._parent_item._get_vertex_position(self._vertex_index)

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle vertex movement during drag."""
        if not self._is_dragging or self._parent_item is None:
            super().mouseMoveEvent(event)
            return

        # Get new position in parent item coordinates, clamped to canvas
        scene_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)
        parent_pos = self._parent_item.mapFromScene(scene_pos)

        # Apply the vertex move
        if hasattr(self._parent_item, '_move_vertex_to'):
            self._parent_item._move_vertex_to(self._vertex_index, parent_pos)

        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Complete vertex drag operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False

            # Register undo command
            if (self._parent_item is not None and
                self._initial_vertex_pos is not None and
                hasattr(self._parent_item, '_on_vertex_move_end')):
                current_pos = self._parent_item._get_vertex_position(self._vertex_index)
                self._parent_item._on_vertex_move_end(
                    self._vertex_index,
                    self._initial_vertex_pos,
                    current_pos,
                )

            self._drag_start_pos = None
            self._initial_vertex_pos = None

            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Show context menu for vertex operations."""
        if self._parent_item is None:
            return

        # Check if we can delete (need minimum vertices - parent defines minimum)
        can_delete = True
        if hasattr(self._parent_item, '_get_vertex_count'):
            min_count = MINIMUM_VERTICES
            if hasattr(self._parent_item, '_get_minimum_vertex_count'):
                min_count = self._parent_item._get_minimum_vertex_count()
            can_delete = self._parent_item._get_vertex_count() > min_count

        menu = QMenu()

        delete_action = menu.addAction("Delete Vertex")
        delete_action.setEnabled(can_delete)
        if not can_delete:
            min_count = MINIMUM_VERTICES
            if hasattr(self._parent_item, '_get_minimum_vertex_count'):
                min_count = self._parent_item._get_minimum_vertex_count()
            delete_action.setToolTip(f"Cannot delete: minimum {min_count} vertices required")

        action = menu.exec(event.screenPos())

        if (action == delete_action and can_delete
                and hasattr(self._parent_item, '_delete_vertex')):
            self._parent_item._delete_vertex(self._vertex_index)

        event.accept()


class MidpointHandle(QGraphicsEllipseItem):
    """A handle displayed at edge midpoints for adding new vertices.

    Clicking on this handle adds a new vertex at the midpoint position.
    """

    def __init__(
        self,
        edge_index: int,
        parent: "ParentItem",
    ) -> None:
        """Initialize the midpoint handle.

        Args:
            edge_index: Index of the edge (vertex index of the starting vertex)
            parent: The parent polygon item
        """
        super().__init__(parent)
        self._edge_index = edge_index
        self._parent_item = parent

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the handle."""
        half_size = MIDPOINT_HANDLE_SIZE / 2.0
        self.setRect(-half_size, -half_size, MIDPOINT_HANDLE_SIZE, MIDPOINT_HANDLE_SIZE)

        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(MIDPOINT_HANDLE_COLOR))

        # Make handle render at fixed screen size regardless of zoom
        self.setFlag(QGraphicsEllipseItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(1001)  # Below vertex handles

    @property
    def edge_index(self) -> int:
        """Get the edge index this handle represents."""
        return self._edge_index

    @edge_index.setter
    def edge_index(self, value: int) -> None:
        """Set the edge index."""
        self._edge_index = value

    def update_position(self, pos: QPointF) -> None:
        """Update handle position to a specific point.

        Args:
            pos: Position in parent item coordinates
        """
        self.setPos(pos)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Highlight handle on hover."""
        self.setBrush(QBrush(MIDPOINT_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Remove highlight when hover ends."""
        self.setBrush(QBrush(MIDPOINT_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Add a new vertex at this midpoint position."""
        if event.button() == Qt.MouseButton.LeftButton:
            if self._parent_item is not None and hasattr(self._parent_item, '_add_vertex_at_edge'):
                # Get the current position (midpoint of the edge)
                pos = self.pos()
                # Insert new vertex after the edge start vertex
                self._parent_item._add_vertex_at_edge(self._edge_index, pos)

            event.accept()
        else:
            super().mousePressEvent(event)


class AnnotationLabel(QGraphicsItem):
    """A small label with background, used for vertex coordinates and edge lengths.

    Renders at fixed screen size regardless of zoom level.
    """

    def __init__(self, parent: QGraphicsItem) -> None:
        """Initialize the annotation label."""
        super().__init__(parent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)

        self._text = ""
        self._font = QFont("Segoe UI", ANNOTATION_FONT_SIZE)
        self._text_color = ANNOTATION_TEXT_COLOR
        self._bg_color = ANNOTATION_BG_COLOR
        self._border_color = ANNOTATION_BORDER_COLOR
        self._padding = 3.0

    def set_text(self, text: str) -> None:
        """Update the displayed text."""
        self._text = text
        self.prepareGeometryChange()
        self.update()

    def boundingRect(self) -> QRectF:
        """Return the bounding rectangle for the label."""
        from PyQt6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._font)
        text_rect = fm.boundingRect(self._text)
        p = self._padding
        return QRectF(
            -p, -p,
            text_rect.width() + 2 * p,
            text_rect.height() + 2 * p,
        )

    def paint(self, painter: Any, _option: Any, _widget: Any = None) -> None:
        """Paint the label with background."""
        from PyQt6.QtGui import QFontMetricsF

        fm = QFontMetricsF(self._font)
        text_rect = fm.boundingRect(self._text)
        p = self._padding

        bg_rect = QRectF(
            -p, -p,
            text_rect.width() + 2 * p,
            text_rect.height() + 2 * p,
        )

        painter.setPen(QPen(self._border_color, 0.5))
        painter.setBrush(QBrush(self._bg_color))
        painter.drawRoundedRect(bg_rect, 2, 2)

        painter.setFont(self._font)
        painter.setPen(self._text_color)
        painter.drawText(QPointF(0, fm.ascent()), self._text)


def _format_coordinate(x_cm: float, y_cm: float) -> str:
    """Format a vertex coordinate for display.

    Args:
        x_cm: X coordinate in centimeters
        y_cm: Y coordinate in centimeters

    Returns:
        Formatted string like "(3.50, 2.10) m" or "(45.2, 30.1) cm"
    """
    if abs(x_cm) >= 100 or abs(y_cm) >= 100:
        return f"({x_cm / 100:.2f}, {y_cm / 100:.2f}) m"
    return f"({x_cm:.1f}, {y_cm:.1f}) cm"


def _format_edge_length(length_cm: float) -> str:
    """Format an edge length for display.

    Args:
        length_cm: Length in centimeters

    Returns:
        Formatted string like "2.35 m" or "45.2 cm"
    """
    if length_cm >= 100:
        return f"{length_cm / 100:.2f} m"
    return f"{length_cm:.1f} cm"


def _edge_length(p1: QPointF, p2: QPointF) -> float:
    """Calculate the distance between two points in centimeters."""
    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    return math.sqrt(dx * dx + dy * dy)


class VertexEditMixin:
    """Mixin that adds vertex editing functionality to polygon items.

    This mixin provides methods to enter/exit vertex edit mode,
    move vertices, add vertices at midpoints, and delete vertices.
    """

    _vertex_handles: list[VertexHandle]
    _midpoint_handles: list[MidpointHandle]
    _coord_labels: list[AnnotationLabel]
    _edge_labels: list[AnnotationLabel]
    _is_vertex_edit_mode: bool

    def init_vertex_edit(self) -> None:
        """Initialize vertex editing (call in subclass __init__)."""
        self._vertex_handles = []
        self._midpoint_handles = []
        self._coord_labels = []
        self._edge_labels = []
        self._is_vertex_edit_mode = False

    @property
    def is_vertex_edit_mode(self) -> bool:
        """Check if currently in vertex edit mode."""
        return self._is_vertex_edit_mode

    def enter_vertex_edit_mode(self) -> None:
        """Enter vertex editing mode - show vertex and midpoint handles."""
        if self._is_vertex_edit_mode:
            return
        if _is_item_fixed(self):  # type: ignore[arg-type]
            return

        self._is_vertex_edit_mode = True

        # Hide resize and rotation handles if they exist
        if hasattr(self, 'hide_resize_handles'):
            self.hide_resize_handles()  # type: ignore[attr-defined]
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()  # type: ignore[attr-defined]

        # Create vertex and midpoint handles + annotations
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide vertex handles."""
        if not self._is_vertex_edit_mode:
            return

        self._is_vertex_edit_mode = False

        # Remove vertex and midpoint handles + annotations
        self._remove_vertex_handles()
        self._remove_midpoint_handles()
        self._remove_annotations()

        # Show resize and rotation handles if selected
        if hasattr(self, 'isSelected') and self.isSelected():  # type: ignore[attr-defined]
            if hasattr(self, 'show_resize_handles'):
                self.show_resize_handles()  # type: ignore[attr-defined]
            if hasattr(self, 'show_rotation_handle'):
                self.show_rotation_handle()  # type: ignore[attr-defined]

    def _create_vertex_handles(self) -> None:
        """Create handles for all vertices."""
        self._remove_vertex_handles()

        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()  # type: ignore[attr-defined]
        for i in range(polygon.count()):
            handle = VertexHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(polygon.at(i))
            self._vertex_handles.append(handle)

    def _remove_vertex_handles(self) -> None:
        """Remove all vertex handles."""
        for handle in self._vertex_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._vertex_handles = []

    def _create_midpoint_handles(self) -> None:
        """Create handles at edge midpoints."""
        self._remove_midpoint_handles()

        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()  # type: ignore[attr-defined]
        count = polygon.count()

        for i in range(count):
            # Get edge start and end points
            p1 = polygon.at(i)
            p2 = polygon.at((i + 1) % count)

            # Calculate midpoint
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)

            handle = MidpointHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(midpoint)
            self._midpoint_handles.append(handle)

    def _remove_midpoint_handles(self) -> None:
        """Remove all midpoint handles."""
        for handle in self._midpoint_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._midpoint_handles = []

    def _update_vertex_handles(self) -> None:
        """Update positions of all vertex and midpoint handles and annotations."""
        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()  # type: ignore[attr-defined]
        count = polygon.count()

        # Update vertex handles
        for i, handle in enumerate(self._vertex_handles):
            if i < count:
                handle.update_position(polygon.at(i))

        # Update midpoint handles
        for i, handle in enumerate(self._midpoint_handles):
            if i < count:
                p1 = polygon.at(i)
                p2 = polygon.at((i + 1) % count)
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                handle.update_position(midpoint)

        # Update annotations
        self._update_annotations()

    def _create_annotations(self) -> None:
        """Create coordinate and edge length annotations."""
        self._remove_annotations()

        if not hasattr(self, 'polygon') or not hasattr(self, 'mapToScene'):
            return

        polygon = self.polygon()  # type: ignore[attr-defined]
        count = polygon.count()

        # Create coordinate labels at each vertex
        for i in range(count):
            point = polygon.at(i)
            scene_pt = self.mapToScene(point)  # type: ignore[attr-defined]
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(point.x(), point.y())
            self._coord_labels.append(label)

        # Create edge length labels at each edge midpoint
        for i in range(count):
            p1 = polygon.at(i)
            p2 = polygon.at((i + 1) % count)
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
            scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._edge_labels.append(label)

    def _remove_annotations(self) -> None:
        """Remove all annotation labels."""
        for label in self._coord_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._coord_labels = []

        for label in self._edge_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._edge_labels = []

    def _update_annotations(self) -> None:
        """Update annotation text and positions."""
        if not hasattr(self, 'polygon') or not hasattr(self, 'mapToScene'):
            return

        polygon = self.polygon()  # type: ignore[attr-defined]
        count = polygon.count()

        # Update coordinate labels
        for i, label in enumerate(self._coord_labels):
            if i < count:
                point = polygon.at(i)
                scene_pt = self.mapToScene(point)  # type: ignore[attr-defined]
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(point.x(), point.y())

        # Update edge length labels
        for i, label in enumerate(self._edge_labels):
            if i < count:
                p1 = polygon.at(i)
                p2 = polygon.at((i + 1) % count)
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
                scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
                length = _edge_length(scene_p1, scene_p2)
                label.set_text(_format_edge_length(length))
                label.setPos(midpoint.x(), midpoint.y())

    def _get_vertex_position(self, index: int) -> QPointF:
        """Get the position of a vertex.

        Args:
            index: Vertex index

        Returns:
            Position of the vertex in item coordinates
        """
        if not hasattr(self, 'polygon'):
            return QPointF(0, 0)

        polygon = self.polygon()  # type: ignore[attr-defined]
        if 0 <= index < polygon.count():
            return polygon.at(index)
        return QPointF(0, 0)

    def _get_vertex_count(self) -> int:
        """Get the number of vertices in the polygon.

        Returns:
            Number of vertices
        """
        if not hasattr(self, 'polygon'):
            return 0

        return self.polygon().count()  # type: ignore[attr-defined]

    def _get_minimum_vertex_count(self) -> int:
        """Get the minimum number of vertices allowed (3 for polygons)."""
        return MINIMUM_VERTICES

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a vertex to a new position.

        Args:
            index: Vertex index
            pos: New position in item coordinates
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()  # type: ignore[attr-defined]
        if 0 <= index < polygon.count():
            # Create new polygon with updated vertex
            vertices = [polygon.at(i) for i in range(polygon.count())]
            vertices[index] = pos
            self.setPolygon(QPolygonF(vertices))  # type: ignore[attr-defined]

            # Update handles
            self._update_vertex_handles()

            # Update label position
            if hasattr(self, '_position_label'):
                self._position_label()  # type: ignore[attr-defined]

    def _add_vertex_at_edge(self, edge_index: int, pos: QPointF) -> None:
        """Add a new vertex at an edge position.

        Args:
            edge_index: Index of the edge (starting vertex index)
            pos: Position for the new vertex in item coordinates
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()  # type: ignore[attr-defined]

        # Insert after edge_index
        insert_index = edge_index + 1
        vertices = [polygon.at(i) for i in range(polygon.count())]
        vertices.insert(insert_index, pos)

        # Update polygon
        self.setPolygon(QPolygonF(vertices))  # type: ignore[attr-defined]

        # Recreate handles and annotations (indices changed)
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

        # Register undo command
        self._on_vertex_add(insert_index, pos)

    def _delete_vertex(self, index: int) -> None:
        """Delete a vertex from the polygon.

        Args:
            index: Vertex index to delete
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()  # type: ignore[attr-defined]

        # Check minimum vertices
        if polygon.count() <= MINIMUM_VERTICES:
            return

        # Store position for undo
        deleted_pos = polygon.at(index)

        # Remove vertex
        vertices = [polygon.at(i) for i in range(polygon.count()) if i != index]

        # Update polygon
        self.setPolygon(QPolygonF(vertices))  # type: ignore[attr-defined]

        # Recreate handles and annotations (indices changed)
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

        # Register undo command
        self._on_vertex_delete(index, deleted_pos)

    def _on_vertex_move_end(
        self,
        vertex_index: int,
        old_pos: QPointF,
        new_pos: QPointF,
    ) -> None:
        """Called when a vertex move operation completes. Registers undo command.

        Args:
            vertex_index: Index of the moved vertex
            old_pos: Original position
            new_pos: New position
        """
        # Don't register if position didn't change
        if old_pos == new_pos:
            return

        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import MoveVertexCommand

        def apply_vertex_pos(item: QGraphicsItem, index: int, pos: QPointF) -> None:
            """Apply vertex position to item."""
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(index, pos)

        command = MoveVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            old_pos,
            new_pos,
            apply_vertex_pos,
        )

        # Add to undo stack without executing (move already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _on_vertex_add(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is added. Registers undo command.

        Args:
            vertex_index: Index of the new vertex
            pos: Position of the new vertex
        """
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import AddVertexCommand

        def apply_add_vertex(item: QGraphicsItem, index: int, position: QPointF) -> None:
            """Add a vertex to the item."""
            if hasattr(item, '_insert_vertex'):
                item._insert_vertex(index, position)

        def apply_remove_vertex(item: QGraphicsItem, index: int) -> None:
            """Remove a vertex from the item."""
            if hasattr(item, '_remove_vertex'):
                item._remove_vertex(index)

        command = AddVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
            apply_add_vertex,
            apply_remove_vertex,
        )

        # Add to undo stack without executing (add already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _on_vertex_delete(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is deleted. Registers undo command.

        Args:
            vertex_index: Index of the deleted vertex
            pos: Position of the deleted vertex
        """
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import DeleteVertexCommand

        def apply_add_vertex(item: QGraphicsItem, index: int, position: QPointF) -> None:
            """Add a vertex to the item."""
            if hasattr(item, '_insert_vertex'):
                item._insert_vertex(index, position)

        def apply_remove_vertex(item: QGraphicsItem, index: int) -> None:
            """Remove a vertex from the item."""
            if hasattr(item, '_remove_vertex'):
                item._remove_vertex(index)

        command = DeleteVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
            apply_add_vertex,
            apply_remove_vertex,
        )

        # Add to undo stack without executing (delete already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _insert_vertex(self, index: int, pos: QPointF) -> None:
        """Insert a vertex at a specific index (for undo/redo).

        Args:
            index: Index where to insert the vertex
            pos: Position of the new vertex
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()  # type: ignore[attr-defined]
        vertices = [polygon.at(i) for i in range(polygon.count())]
        vertices.insert(index, pos)
        self.setPolygon(QPolygonF(vertices))  # type: ignore[attr-defined]

        # Update handles and annotations if in edit mode
        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

    def _remove_vertex(self, index: int) -> None:
        """Remove a vertex at a specific index (for undo/redo).

        Args:
            index: Index of the vertex to remove
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()  # type: ignore[attr-defined]
        vertices = [polygon.at(i) for i in range(polygon.count()) if i != index]
        self.setPolygon(QPolygonF(vertices))  # type: ignore[attr-defined]

        # Update handles and annotations if in edit mode
        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]


class RectCornerHandle(QGraphicsRectItem):
    """A draggable handle for moving rectangle corners.

    Displayed at each corner when in vertex edit mode for rectangles.
    Moving a corner adjusts the rectangle dimensions.
    """

    def __init__(
        self,
        corner: RectCorner,
        parent: "ParentItem",
    ) -> None:
        """Initialize the corner handle.

        Args:
            corner: Which corner this handle represents
            parent: The parent rectangle item
        """
        super().__init__(parent)
        self._corner = corner
        self._parent_item = parent
        self._is_dragging = False
        self._drag_start_pos: QPointF | None = None
        self._initial_rect: QRectF | None = None
        self._initial_item_pos: QPointF | None = None

        self._setup_appearance()
        self._setup_flags()

    def _setup_appearance(self) -> None:
        """Configure the visual appearance of the handle."""
        half_size = VERTEX_HANDLE_SIZE / 2.0
        self.setRect(-half_size, -half_size, VERTEX_HANDLE_SIZE, VERTEX_HANDLE_SIZE)

        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))

        # Make handle render at fixed screen size regardless of zoom
        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations)

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        # Set cursor based on corner
        if self._corner in (RectCorner.TOP_LEFT, RectCorner.BOTTOM_RIGHT):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        self.setZValue(1002)

    @property
    def corner(self) -> RectCorner:
        """Get the corner this handle represents."""
        return self._corner

    def update_position(self, rect: QRectF) -> None:
        """Update handle position based on rectangle.

        Args:
            rect: The rectangle in item coordinates
        """
        positions = {
            RectCorner.TOP_LEFT: QPointF(rect.left(), rect.top()),
            RectCorner.TOP_RIGHT: QPointF(rect.right(), rect.top()),
            RectCorner.BOTTOM_LEFT: QPointF(rect.left(), rect.bottom()),
            RectCorner.BOTTOM_RIGHT: QPointF(rect.right(), rect.bottom()),
        }
        self.setPos(positions.get(self._corner, QPointF(0, 0)))

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Highlight handle on hover."""
        self.setBrush(QBrush(VERTEX_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        """Remove highlight when hover ends."""
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Start corner drag operation."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial rectangle and position
            if self._parent_item is not None and hasattr(self._parent_item, 'rect'):
                self._initial_rect = QRectF(self._parent_item.rect())
                self._initial_item_pos = QPointF(self._parent_item.pos())

            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Handle corner movement during drag."""
        if not self._is_dragging or self._parent_item is None:
            super().mouseMoveEvent(event)
            return

        if self._initial_rect is None or self._initial_item_pos is None:
            return

        # Get delta in scene coordinates, clamped to canvas
        current_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)
        delta = current_pos - self._drag_start_pos

        # Apply corner movement
        if hasattr(self._parent_item, '_move_corner_to'):
            self._parent_item._move_corner_to(self._corner, delta, self._initial_rect, self._initial_item_pos)

        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Complete corner drag operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self._is_dragging = False

            # Register undo command
            if (self._parent_item is not None and
                self._initial_rect is not None and
                self._initial_item_pos is not None and
                hasattr(self._parent_item, '_on_corner_move_end')):
                self._parent_item._on_corner_move_end(
                    self._initial_rect,
                    self._initial_item_pos,
                )

            self._drag_start_pos = None
            self._initial_rect = None
            self._initial_item_pos = None

            event.accept()
        else:
            super().mouseReleaseEvent(event)


class RectVertexEditMixin:
    """Mixin that adds vertex editing functionality to rectangle items.

    This mixin provides methods to enter/exit vertex edit mode for rectangles,
    showing corner handles that allow adjusting the rectangle dimensions.
    """

    _rect_corner_handles: list[RectCornerHandle]
    _rect_coord_labels: list[AnnotationLabel]
    _rect_edge_labels: list[AnnotationLabel]
    _is_rect_vertex_edit_mode: bool

    def init_rect_vertex_edit(self) -> None:
        """Initialize rectangle vertex editing (call in subclass __init__)."""
        self._rect_corner_handles = []
        self._rect_coord_labels = []
        self._rect_edge_labels = []
        self._is_rect_vertex_edit_mode = False

    @property
    def is_vertex_edit_mode(self) -> bool:
        """Check if currently in vertex edit mode."""
        return self._is_rect_vertex_edit_mode

    def enter_vertex_edit_mode(self) -> None:
        """Enter vertex editing mode - show corner handles."""
        if self._is_rect_vertex_edit_mode:
            return
        if _is_item_fixed(self):  # type: ignore[arg-type]
            return

        self._is_rect_vertex_edit_mode = True

        # Hide resize and rotation handles if they exist
        if hasattr(self, 'hide_resize_handles'):
            self.hide_resize_handles()  # type: ignore[attr-defined]
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()  # type: ignore[attr-defined]

        # Create corner handles and annotations
        self._create_rect_corner_handles()
        self._create_rect_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide corner handles."""
        if not self._is_rect_vertex_edit_mode:
            return

        self._is_rect_vertex_edit_mode = False

        # Remove corner handles and annotations
        self._remove_rect_corner_handles()
        self._remove_rect_annotations()

        # Show resize and rotation handles if selected
        if hasattr(self, 'isSelected') and self.isSelected():  # type: ignore[attr-defined]
            if hasattr(self, 'show_resize_handles'):
                self.show_resize_handles()  # type: ignore[attr-defined]
            if hasattr(self, 'show_rotation_handle'):
                self.show_rotation_handle()  # type: ignore[attr-defined]

    def _create_rect_corner_handles(self) -> None:
        """Create handles for all 4 corners."""
        self._remove_rect_corner_handles()

        if not hasattr(self, 'rect'):
            return

        rect = self.rect()  # type: ignore[attr-defined]
        for corner in RectCorner:
            handle = RectCornerHandle(corner, self)  # type: ignore[arg-type]
            handle.update_position(rect)
            self._rect_corner_handles.append(handle)

    def _remove_rect_corner_handles(self) -> None:
        """Remove all corner handles."""
        for handle in self._rect_corner_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._rect_corner_handles = []

    def _update_rect_corner_handles(self) -> None:
        """Update positions of all corner handles and annotations."""
        if not hasattr(self, 'rect'):
            return

        rect = self.rect()  # type: ignore[attr-defined]
        for handle in self._rect_corner_handles:
            handle.update_position(rect)

        self._update_rect_annotations()

    def _create_rect_annotations(self) -> None:
        """Create coordinate and edge length annotations for rectangle corners."""
        self._remove_rect_annotations()

        if not hasattr(self, 'rect') or not hasattr(self, 'mapToScene'):
            return

        rect = self.rect()  # type: ignore[attr-defined]
        corners = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]

        # Coordinate labels at each corner
        for corner in corners:
            scene_pt = self.mapToScene(corner)  # type: ignore[attr-defined]
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(corner.x(), corner.y())
            self._rect_coord_labels.append(label)

        # Edge length labels at each edge midpoint (4 edges)
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
            scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._rect_edge_labels.append(label)

    def _remove_rect_annotations(self) -> None:
        """Remove all rectangle annotation labels."""
        for label in self._rect_coord_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._rect_coord_labels = []

        for label in self._rect_edge_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._rect_edge_labels = []

    def _update_rect_annotations(self) -> None:
        """Update rectangle annotation text and positions."""
        if not hasattr(self, 'rect') or not hasattr(self, 'mapToScene'):
            return

        rect = self.rect()  # type: ignore[attr-defined]
        corners = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]

        # Update coordinate labels
        for i, label in enumerate(self._rect_coord_labels):
            if i < len(corners):
                corner = corners[i]
                scene_pt = self.mapToScene(corner)  # type: ignore[attr-defined]
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(corner.x(), corner.y())

        # Update edge length labels
        for i, label in enumerate(self._rect_edge_labels):
            if i < 4:
                p1 = corners[i]
                p2 = corners[(i + 1) % 4]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
                scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
                length = _edge_length(scene_p1, scene_p2)
                label.set_text(_format_edge_length(length))
                label.setPos(midpoint.x(), midpoint.y())

    def _move_corner_to(
        self,
        corner: RectCorner,
        delta: QPointF,
        initial_rect: QRectF,
        initial_pos: QPointF,
    ) -> None:
        """Move a corner by delta from its initial position.

        Args:
            corner: Which corner to move
            delta: Movement delta in scene coordinates
            initial_rect: Initial rectangle before drag started
            initial_pos: Initial item position before drag started
        """
        if not hasattr(self, 'setRect') or not hasattr(self, 'setPos'):
            return

        # Calculate new rect based on which corner is being dragged
        new_rect = QRectF(initial_rect)
        new_pos = QPointF(initial_pos)

        if corner == RectCorner.TOP_LEFT:
            # Adjust left and top
            new_width = initial_rect.width() - delta.x()
            new_height = initial_rect.height() - delta.y()
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
                new_pos.setX(initial_pos.x() + delta.x())
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)
                new_pos.setY(initial_pos.y() + delta.y())

        elif corner == RectCorner.TOP_RIGHT:
            # Adjust right and top
            new_width = initial_rect.width() + delta.x()
            new_height = initial_rect.height() - delta.y()
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)
                new_pos.setY(initial_pos.y() + delta.y())

        elif corner == RectCorner.BOTTOM_LEFT:
            # Adjust left and bottom
            new_width = initial_rect.width() - delta.x()
            new_height = initial_rect.height() + delta.y()
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
                new_pos.setX(initial_pos.x() + delta.x())
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        elif corner == RectCorner.BOTTOM_RIGHT:
            # Adjust right and bottom
            new_width = initial_rect.width() + delta.x()
            new_height = initial_rect.height() + delta.y()
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        # Apply the new geometry
        self.setRect(new_rect)  # type: ignore[attr-defined]
        self.setPos(new_pos)  # type: ignore[attr-defined]

        # Update corner handles
        self._update_rect_corner_handles()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

    def _on_corner_move_end(
        self,
        initial_rect: QRectF,
        initial_pos: QPointF,
    ) -> None:
        """Called when a corner move operation completes. Registers undo command.

        Args:
            initial_rect: Rectangle before move started
            initial_pos: Item position before move started
        """
        if not hasattr(self, 'rect') or not hasattr(self, 'pos'):
            return

        current_rect = self.rect()  # type: ignore[attr-defined]
        current_pos = self.pos()  # type: ignore[attr-defined]

        # Don't register if nothing changed
        if initial_rect == current_rect and initial_pos == current_pos:
            return

        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import ResizeItemCommand

        def apply_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
            """Apply geometry to the item."""
            if hasattr(item, 'setRect') and hasattr(item, 'setPos'):
                item.setRect(QRectF(
                    geom['rect_x'],
                    geom['rect_y'],
                    geom['width'],
                    geom['height'],
                ))
                item.setPos(geom['pos_x'], geom['pos_y'])
                if hasattr(item, '_update_rect_corner_handles'):
                    item._update_rect_corner_handles()
                if hasattr(item, '_position_label'):
                    item._position_label()

        old_geometry = {
            'rect_x': initial_rect.x(),
            'rect_y': initial_rect.y(),
            'width': initial_rect.width(),
            'height': initial_rect.height(),
            'pos_x': initial_pos.x(),
            'pos_y': initial_pos.y(),
        }

        new_geometry = {
            'rect_x': current_rect.x(),
            'rect_y': current_rect.y(),
            'width': current_rect.width(),
            'height': current_rect.height(),
            'pos_x': current_pos.x(),
            'pos_y': current_pos.y(),
        }

        command = ResizeItemCommand(
            self,  # type: ignore[arg-type]
            old_geometry,
            new_geometry,
            apply_geometry,
        )

        # Add to undo stack without executing (move already applied)
        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)


# Minimum vertices for polylines (need at least 2 points for a line)
MINIMUM_POLYLINE_VERTICES = 2


class PolylineVertexEditMixin:
    """Mixin that adds vertex editing functionality to polyline items.

    Works with polylines that store vertices in a _points list and use
    QPainterPath for rendering (open paths, not closed polygons).
    """

    _vertex_handles: list[VertexHandle]
    _midpoint_handles: list[MidpointHandle]
    _coord_labels: list[AnnotationLabel]
    _edge_labels: list[AnnotationLabel]
    _is_vertex_edit_mode: bool

    def init_vertex_edit(self) -> None:
        """Initialize vertex editing (call in subclass __init__)."""
        self._vertex_handles = []
        self._midpoint_handles = []
        self._coord_labels = []
        self._edge_labels = []
        self._is_vertex_edit_mode = False

    @property
    def is_vertex_edit_mode(self) -> bool:
        """Check if currently in vertex edit mode."""
        return self._is_vertex_edit_mode

    def enter_vertex_edit_mode(self) -> None:
        """Enter vertex editing mode - show vertex and midpoint handles."""
        if self._is_vertex_edit_mode:
            return
        if _is_item_fixed(self):  # type: ignore[arg-type]
            return

        self._is_vertex_edit_mode = True

        # Hide rotation handle if it exists
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()  # type: ignore[attr-defined]

        # Create vertex and midpoint handles + annotations
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide vertex handles."""
        if not self._is_vertex_edit_mode:
            return

        self._is_vertex_edit_mode = False

        # Remove vertex and midpoint handles + annotations
        self._remove_vertex_handles()
        self._remove_midpoint_handles()
        self._remove_annotations()

        # Show rotation handle if selected
        if hasattr(self, 'isSelected') and self.isSelected() and hasattr(self, 'show_rotation_handle'):  # type: ignore[attr-defined]
            self.show_rotation_handle()  # type: ignore[attr-defined]

    def _create_vertex_handles(self) -> None:
        """Create handles for all vertices."""
        self._remove_vertex_handles()

        if not hasattr(self, '_points'):
            return

        for i, point in enumerate(self._points):  # type: ignore[attr-defined]
            handle = VertexHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(point)
            self._vertex_handles.append(handle)

    def _remove_vertex_handles(self) -> None:
        """Remove all vertex handles."""
        for handle in self._vertex_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._vertex_handles = []

    def _create_midpoint_handles(self) -> None:
        """Create handles at edge midpoints (no wrap-around for open paths)."""
        self._remove_midpoint_handles()

        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        # Open path: midpoints between consecutive pairs only (no closing edge)
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)

            handle = MidpointHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(midpoint)
            self._midpoint_handles.append(handle)

    def _remove_midpoint_handles(self) -> None:
        """Remove all midpoint handles."""
        for handle in self._midpoint_handles:
            if handle.scene() is not None:
                handle.scene().removeItem(handle)
        self._midpoint_handles = []

    def _update_vertex_handles(self) -> None:
        """Update positions of all vertex and midpoint handles and annotations."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]

        # Update vertex handles
        for i, handle in enumerate(self._vertex_handles):
            if i < len(points):
                handle.update_position(points[i])

        # Update midpoint handles
        for i, handle in enumerate(self._midpoint_handles):
            if i < len(points) - 1:
                p1 = points[i]
                p2 = points[i + 1]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                handle.update_position(midpoint)

        # Update annotations
        self._update_annotations()

    def _create_annotations(self) -> None:
        """Create coordinate and edge length annotations."""
        self._remove_annotations()

        if not hasattr(self, '_points') or not hasattr(self, 'mapToScene'):
            return

        points = self._points  # type: ignore[attr-defined]

        # Coordinate labels at each vertex
        for point in points:
            scene_pt = self.mapToScene(point)  # type: ignore[attr-defined]
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(point.x(), point.y())
            self._coord_labels.append(label)

        # Edge length labels (open path: N-1 edges)
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
            scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._edge_labels.append(label)

    def _remove_annotations(self) -> None:
        """Remove all annotation labels."""
        for label in self._coord_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._coord_labels = []

        for label in self._edge_labels:
            if label.scene() is not None:
                label.scene().removeItem(label)
        self._edge_labels = []

    def _update_annotations(self) -> None:
        """Update annotation text and positions."""
        if not hasattr(self, '_points') or not hasattr(self, 'mapToScene'):
            return

        points = self._points  # type: ignore[attr-defined]

        # Update coordinate labels
        for i, label in enumerate(self._coord_labels):
            if i < len(points):
                point = points[i]
                scene_pt = self.mapToScene(point)  # type: ignore[attr-defined]
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(point.x(), point.y())

        # Update edge length labels
        for i, label in enumerate(self._edge_labels):
            if i < len(points) - 1:
                p1 = points[i]
                p2 = points[i + 1]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)  # type: ignore[attr-defined]
                scene_p2 = self.mapToScene(p2)  # type: ignore[attr-defined]
                length = _edge_length(scene_p1, scene_p2)
                label.set_text(_format_edge_length(length))
                label.setPos(midpoint.x(), midpoint.y())

    def _rebuild_path(self) -> None:
        """Rebuild the QPainterPath from current points."""
        if not hasattr(self, '_points') or not hasattr(self, 'setPath'):
            return

        from PyQt6.QtGui import QPainterPath as _QPainterPath

        points = self._points  # type: ignore[attr-defined]
        path = _QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
        self.setPath(path)  # type: ignore[attr-defined]

    def _get_vertex_position(self, index: int) -> QPointF:
        """Get the position of a vertex."""
        if not hasattr(self, '_points'):
            return QPointF(0, 0)

        points = self._points  # type: ignore[attr-defined]
        if 0 <= index < len(points):
            return QPointF(points[index])
        return QPointF(0, 0)

    def _get_vertex_count(self) -> int:
        """Get the number of vertices."""
        if not hasattr(self, '_points'):
            return 0
        return len(self._points)  # type: ignore[attr-defined]

    def _get_minimum_vertex_count(self) -> int:
        """Get the minimum number of vertices allowed (2 for polylines)."""
        return MINIMUM_POLYLINE_VERTICES

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a vertex to a new position."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        if 0 <= index < len(points):
            points[index] = pos
            self._rebuild_path()
            self._update_vertex_handles()

            if hasattr(self, '_position_label'):
                self._position_label()  # type: ignore[attr-defined]

    def _add_vertex_at_edge(self, edge_index: int, pos: QPointF) -> None:
        """Add a new vertex at an edge position."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        insert_index = edge_index + 1
        points.insert(insert_index, pos)

        self._rebuild_path()
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

        self._on_vertex_add(insert_index, pos)

    def _delete_vertex(self, index: int) -> None:
        """Delete a vertex from the polyline."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        if len(points) <= MINIMUM_POLYLINE_VERTICES:
            return

        deleted_pos = QPointF(points[index])
        del points[index]

        self._rebuild_path()
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

        self._on_vertex_delete(index, deleted_pos)

    def _on_vertex_move_end(
        self,
        vertex_index: int,
        old_pos: QPointF,
        new_pos: QPointF,
    ) -> None:
        """Called when a vertex move completes. Registers undo command."""
        if old_pos == new_pos:
            return

        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import MoveVertexCommand

        def apply_vertex_pos(item: QGraphicsItem, index: int, pos: QPointF) -> None:
            if hasattr(item, '_move_vertex_to'):
                item._move_vertex_to(index, pos)

        command = MoveVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            old_pos,
            new_pos,
            apply_vertex_pos,
        )

        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _on_vertex_add(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is added. Registers undo command."""
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import AddVertexCommand

        def apply_add_vertex(item: QGraphicsItem, index: int, position: QPointF) -> None:
            if hasattr(item, '_insert_vertex'):
                item._insert_vertex(index, position)

        def apply_remove_vertex(item: QGraphicsItem, index: int) -> None:
            if hasattr(item, '_remove_vertex'):
                item._remove_vertex(index)

        command = AddVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
            apply_add_vertex,
            apply_remove_vertex,
        )

        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _on_vertex_delete(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is deleted. Registers undo command."""
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.core.commands import DeleteVertexCommand

        def apply_add_vertex(item: QGraphicsItem, index: int, position: QPointF) -> None:
            if hasattr(item, '_insert_vertex'):
                item._insert_vertex(index, position)

        def apply_remove_vertex(item: QGraphicsItem, index: int) -> None:
            if hasattr(item, '_remove_vertex'):
                item._remove_vertex(index)

        command = DeleteVertexCommand(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
            apply_add_vertex,
            apply_remove_vertex,
        )

        command_manager._undo_stack.append(command)
        command_manager._redo_stack.clear()
        command_manager.can_undo_changed.emit(True)
        command_manager.can_redo_changed.emit(False)
        command_manager.command_executed.emit(command.description)

    def _insert_vertex(self, index: int, pos: QPointF) -> None:
        """Insert a vertex at a specific index (for undo/redo)."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        points.insert(index, pos)
        self._rebuild_path()

        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]

    def _remove_vertex(self, index: int) -> None:
        """Remove a vertex at a specific index (for undo/redo)."""
        if not hasattr(self, '_points'):
            return

        points = self._points  # type: ignore[attr-defined]
        if 0 <= index < len(points):
            del points[index]
        self._rebuild_path()

        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()  # type: ignore[attr-defined]
