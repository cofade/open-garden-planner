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

from .handle_geometry import (
    HANDLE_BORDER_COLOR as HANDLE_BORDER_COLOR,
)
from .handle_geometry import (
    MINIMUM_SIZE_CM as MINIMUM_SIZE_CM,
)
from .handle_geometry import (
    _announce_live_edit as _announce_live_edit,
)
from .handle_geometry import (
    _clamp_pos_to_canvas as _clamp_pos_to_canvas,
)
from .handle_geometry import (
    _emit_scale_blocked_hint as _emit_scale_blocked_hint,
)
from .handle_geometry import (
    _has_blocking_constraints as _has_blocking_constraints,
)
from .handle_geometry import (
    _is_item_fixed as _is_item_fixed,
)
from .handle_geometry import (
    anchored_position as anchored_position,
)
from .handle_geometry import (
    resize_rect_item_keeping_anchor as resize_rect_item_keeping_anchor,
)
from .handle_geometry import (
    scene_point_of as scene_point_of,
)
from .vertex_handles import (
    _CURVE_TANGENT_KINDS as _CURVE_TANGENT_KINDS,
)
from .vertex_handles import (
    ANNOTATION_BG_COLOR as ANNOTATION_BG_COLOR,
)
from .vertex_handles import (
    ANNOTATION_BORDER_COLOR as ANNOTATION_BORDER_COLOR,
)
from .vertex_handles import (
    ANNOTATION_EDGE_OFFSET as ANNOTATION_EDGE_OFFSET,
)
from .vertex_handles import (
    ANNOTATION_FONT_SIZE as ANNOTATION_FONT_SIZE,
)
from .vertex_handles import (
    ANNOTATION_TEXT_COLOR as ANNOTATION_TEXT_COLOR,
)
from .vertex_handles import (
    ANNOTATION_VERTEX_OFFSET as ANNOTATION_VERTEX_OFFSET,
)
from .vertex_handles import (
    CURVE_ANCHOR_COLOR as CURVE_ANCHOR_COLOR,
)
from .vertex_handles import (
    CURVE_ANCHOR_SIZE as CURVE_ANCHOR_SIZE,
)
from .vertex_handles import (
    CURVE_CENTER_COLOR as CURVE_CENTER_COLOR,
)
from .vertex_handles import (
    CURVE_CONNECTOR_COLOR as CURVE_CONNECTOR_COLOR,
)
from .vertex_handles import (
    CURVE_HANDLE_HOVER_COLOR as CURVE_HANDLE_HOVER_COLOR,
)
from .vertex_handles import (
    CURVE_KIND_ANCHOR as CURVE_KIND_ANCHOR,
)
from .vertex_handles import (
    CURVE_KIND_ARC_END as CURVE_KIND_ARC_END,
)
from .vertex_handles import (
    CURVE_KIND_ARC_START as CURVE_KIND_ARC_START,
)
from .vertex_handles import (
    CURVE_KIND_ARC_THROUGH as CURVE_KIND_ARC_THROUGH,
)
from .vertex_handles import (
    CURVE_KIND_CENTER as CURVE_KIND_CENTER,
)
from .vertex_handles import (
    CURVE_KIND_HANDLE_IN as CURVE_KIND_HANDLE_IN,
)
from .vertex_handles import (
    CURVE_KIND_HANDLE_OUT as CURVE_KIND_HANDLE_OUT,
)
from .vertex_handles import (
    CURVE_TANGENT_COLOR as CURVE_TANGENT_COLOR,
)
from .vertex_handles import (
    CURVE_TANGENT_SIZE as CURVE_TANGENT_SIZE,
)
from .vertex_handles import (
    DENSE_HANDLE_SPACING_PX as DENSE_HANDLE_SPACING_PX,
)
from .vertex_handles import (
    MAX_ANNOTATED_VERTICES as MAX_ANNOTATED_VERTICES,
)
from .vertex_handles import (
    MAX_DENSE_VERTEX_HANDLES as MAX_DENSE_VERTEX_HANDLES,
)
from .vertex_handles import (
    MIDPOINT_HANDLE_COLOR as MIDPOINT_HANDLE_COLOR,
)
from .vertex_handles import (
    MIDPOINT_HANDLE_HOVER_COLOR as MIDPOINT_HANDLE_HOVER_COLOR,
)
from .vertex_handles import (
    MIDPOINT_HANDLE_SIZE as MIDPOINT_HANDLE_SIZE,
)
from .vertex_handles import (
    MINIMUM_POLYLINE_VERTICES as MINIMUM_POLYLINE_VERTICES,
)
from .vertex_handles import (
    MINIMUM_VERTICES as MINIMUM_VERTICES,
)
from .vertex_handles import (
    VERTEX_HANDLE_COLOR as VERTEX_HANDLE_COLOR,
)
from .vertex_handles import (
    VERTEX_HANDLE_HOVER_COLOR as VERTEX_HANDLE_HOVER_COLOR,
)
from .vertex_handles import (
    VERTEX_HANDLE_SIZE as VERTEX_HANDLE_SIZE,
)
from .vertex_handles import (
    AnnotationLabel as AnnotationLabel,
)
from .vertex_handles import (
    CurveControlHandle as CurveControlHandle,
)
from .vertex_handles import (
    CurveEditMixin as CurveEditMixin,
)
from .vertex_handles import (
    MidpointHandle as MidpointHandle,
)
from .vertex_handles import (
    PolylineVertexEditMixin as PolylineVertexEditMixin,
)
from .vertex_handles import (
    RectCorner as RectCorner,
)
from .vertex_handles import (
    RectCornerHandle as RectCornerHandle,
)
from .vertex_handles import (
    RectVertexEditMixin as RectVertexEditMixin,
)
from .vertex_handles import (
    VertexEditMixin as VertexEditMixin,
)
from .vertex_handles import (
    VertexHandle as VertexHandle,
)
from .vertex_handles import (
    _dense_candidate_scene_rect as _dense_candidate_scene_rect,
)
from .vertex_handles import (
    _dense_overlay_indices as _dense_overlay_indices,
)
from .vertex_handles import (
    _dense_sample_covers_view as _dense_sample_covers_view,
)
from .vertex_handles import (
    _dense_sample_pose as _dense_sample_pose,
)
from .vertex_handles import (
    _dense_sample_view as _dense_sample_view,
)
from .vertex_handles import (
    _edge_length as _edge_length,
)
from .vertex_handles import (
    _forget_dense_sample as _forget_dense_sample,
)
from .vertex_handles import (
    _format_coordinate as _format_coordinate,
)
from .vertex_handles import (
    _format_edge_length as _format_edge_length,
)
from .vertex_handles import (
    _map_to_scene as _map_to_scene,
)
from .vertex_handles import (
    _opposite_corner as _opposite_corner,
)
from .vertex_handles import (
    _remember_dense_sample as _remember_dense_sample,
)
from .vertex_handles import (
    _visible_scene_rect as _visible_scene_rect,
)
from .vertex_handles import (
    _visible_vertex_indices as _visible_vertex_indices,
)
from .vertex_handles import (
    _visible_viewport_rect as _visible_viewport_rect,
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

# Handle visual settings
HANDLE_SIZE = 8.0  # pixels (cosmetic)
HANDLE_COLOR = QColor(0, 120, 215)  # Blue
HANDLE_HOVER_COLOR = QColor(0, 180, 255)  # Lighter blue

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
        self.setZValue(20_000)  # Above everything

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
        self.setZValue(10_000)

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
            if self._parent_item is not None and _has_blocking_constraints(
                self._parent_item
            ):
                _emit_scale_blocked_hint(self._parent_item)
                event.ignore()
                return
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial geometry — use rect() (actual geometry) rather
            # than boundingRect() which includes pen width + shadow margin
            # and would inflate dimensions on every drag.
            if self._parent_item is not None:
                if hasattr(self._parent_item, 'rect') and callable(self._parent_item.rect):
                    self._initial_rect = self._parent_item.rect()
                else:
                    self._initial_rect = self._parent_item.boundingRect()
                self._initial_parent_pos = self._parent_item.pos()

                # Notify parent that resize is starting
                if hasattr(self._parent_item, '_on_resize_start'):
                    self._parent_item._on_resize_start()

            self.grabMouse()
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

        _announce_live_edit(self._parent_item)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        """Complete resize operation."""
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self.ungrabMouse()
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

        # Constrain mid-edge handles to a single axis so the perpendicular
        # dimension stays constant (critical for rotated shapes where both
        # local_dx and local_dy are non-zero from any screen-space drag).
        if self._position in {HandlePosition.MIDDLE_LEFT, HandlePosition.MIDDLE_RIGHT}:
            local_dy = 0.0
        elif self._position in {HandlePosition.TOP_CENTER, HandlePosition.BOTTOM_CENTER}:
            local_dx = 0.0

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

        parent = self._parent_item

        # Rect-bearing items (Circle/Rectangle/Ellipse) resize through the one
        # rotation-aware primitive: the corner/edge OPPOSITE the dragged handle
        # stays fixed in the scene and the rotation origin is re-pinned to the
        # new rect centre. The handle position is the AUTHORITATIVE source of
        # which side is fixed — no scene-space or pos_dx inference, which used
        # to disagree under rotation and drift the item (#218 follow-up).
        if (
            hasattr(parent, 'rect')
            and hasattr(parent, 'setTransformOriginPoint')
            and hasattr(parent, '_after_resize_geometry')
        ):
            is_left = self._position in {
                HandlePosition.TOP_LEFT,
                HandlePosition.MIDDLE_LEFT,
                HandlePosition.BOTTOM_LEFT,
            }
            is_right = self._position in {
                HandlePosition.TOP_RIGHT,
                HandlePosition.MIDDLE_RIGHT,
                HandlePosition.BOTTOM_RIGHT,
            }
            is_top = self._position in {
                HandlePosition.TOP_LEFT,
                HandlePosition.TOP_CENTER,
                HandlePosition.TOP_RIGHT,
            }
            is_bottom = self._position in {
                HandlePosition.BOTTOM_LEFT,
                HandlePosition.BOTTOM_CENTER,
                HandlePosition.BOTTOM_RIGHT,
            }

            # Item-specific size constraint (a circle squares the rect so the
            # dragged handle tracks the cursor; rect/ellipse keep w/h as-is).
            if hasattr(parent, '_constrain_resize_size'):
                norm_w, norm_h = parent._constrain_resize_size(
                    new_width,
                    new_height,
                    width_driven=is_left or is_right,
                    height_driven=is_top or is_bottom,
                )
            else:
                norm_w, norm_h = new_width, new_height
            new_rect = QRectF(init_rect.x(), init_rect.y(), norm_w, norm_h)

            # Fixed reference = the side opposite the handle (centre on an axis
            # the handle does not drive). Take its scene position under the
            # start transform (origin == init rect centre — the invariant that
            # holds at resize start) and its position in the new rect.
            oc = init_rect.center()
            old_fx = init_rect.right() if is_left else init_rect.left() if is_right else oc.x()
            old_fy = init_rect.bottom() if is_top else init_rect.top() if is_bottom else oc.y()
            # Through scene_point_of, not inline: this was the third hand-written
            # transcription of the same forward transform in this file, and a
            # helper that leaves a live counterexample beside it teaches the next
            # reader that using it is optional.
            scene_anchor = scene_point_of(
                QPointF(old_fx, old_fy), init_rect, init_pos, rotation
            )
            nc = new_rect.center()
            new_fx = new_rect.right() if is_left else new_rect.left() if is_right else nc.x()
            new_fy = new_rect.bottom() if is_top else new_rect.top() if is_bottom else nc.y()

            resize_rect_item_keeping_anchor(
                parent, new_rect, scene_anchor, QPointF(new_fx, new_fy)
            )
            parent._after_resize_geometry()
            return

        # Non-rect items — PolygonItem is the only class that still carries an
        # _apply_resize (US-D2.2 deleted the rect-item copies as dead code):
        # the existing axis-aligned path.
        scene_pos_dx = pos_dx * cos_a - pos_dy * sin_a
        scene_pos_dy = pos_dx * sin_a + pos_dy * cos_a
        if hasattr(parent, '_dimension_display') and parent._dimension_display is not None:
            parent._dimension_display.update_dimensions(
                new_width, new_height, self.scenePos()
            )
        if hasattr(parent, '_apply_resize'):
            parent._apply_resize(
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
        self.setZValue(20_000)  # Above everything

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
        self.setZValue(10_001)

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

            self.grabMouse()
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
            self.ungrabMouse()
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
            self._resize_initial_rect = self.boundingRect()
        if hasattr(self, 'pos'):
            self._resize_initial_pos = self.pos()
        # Capture EQUAL-constrained partner sizes before any propagation (for undo)
        scene = self.scene() if hasattr(self, 'scene') else None
        if scene is not None and hasattr(self, 'item_id'):
            from open_garden_planner.core.tools.constraint_tool import (
                _capture_equal_partner_pre_states,
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
        scene = self.scene() if hasattr(self, 'scene') else None
        if scene is None:
            return
        self._propagating_equal_resize = True
        try:
            from open_garden_planner.core.tools.constraint_tool import (
                _apply_equal_propagation_live,
            )
            _apply_equal_propagation_live(self, scene)
        finally:
            self._propagating_equal_resize = False

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
            # Pivot about the geometric centre, not the decoration-expanded
            # bounding box, so the pivot is invariant to runtime-only badges
            # (#219). rect() is the serializer's centre (stored as
            # pos + rect.center()); boundingRect() grows asymmetrically for the
            # antagonist badge and would shift the pivot off-centre, so a
            # rotated badged plant drifts on save/reload (badge not persisted).
            if hasattr(self, 'rect'):
                center = self.rect().center()
            elif hasattr(self, 'boundingRect'):
                center = self.boundingRect().center()
            else:
                center = None

            # Set transform origin to center
            if center is not None and hasattr(self, 'setTransformOriginPoint'):
                self.setTransformOriginPoint(center)

            self.setRotation(angle)

        # Update handles
        if hasattr(self, 'update_resize_handles'):
            self.update_resize_handles()
        self.update_rotation_handle()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()


# Rectangle corner positions for vertex editing


DRAG_HANDLE_TYPES = (
    ResizeHandle, RotationHandle, VertexHandle, RectCornerHandle, MidpointHandle, CurveControlHandle,
)
