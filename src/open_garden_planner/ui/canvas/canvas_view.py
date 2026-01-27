"""Canvas view for the garden planner.

The view handles rendering, pan, zoom, and coordinate transformation.
It flips the Y-axis to provide CAD-style coordinates (origin at bottom-left,
Y increasing upward).
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import QGraphicsView

from open_garden_planner.core.tools import (
    PolygonTool,
    RectangleTool,
    SelectTool,
    ToolManager,
    ToolType,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


class CanvasView(QGraphicsView):
    """Graphics view for the garden canvas.

    Provides pan, zoom, and coordinate transformation.
    Coordinates shown to user are in CAD convention (Y-up, origin bottom-left).

    Signals:
        coordinates_changed: Emitted when mouse moves, provides (x, y) in cm
        zoom_changed: Emitted when zoom changes, provides zoom percentage
    """

    # Signals
    coordinates_changed = pyqtSignal(float, float)
    zoom_changed = pyqtSignal(float)
    tool_changed = pyqtSignal(str)  # Emitted when active tool changes

    # Zoom limits
    min_zoom: float = 0.01  # 1% - very zoomed out
    max_zoom: float = 50.0  # 5000% - very zoomed in

    def __init__(self, scene: CanvasScene, parent: object = None) -> None:
        """Initialize the canvas view.

        Args:
            scene: The CanvasScene to display
            parent: Parent widget
        """
        super().__init__(scene, parent)

        self._canvas_scene = scene
        self._zoom_factor = 1.0
        self._grid_visible = False
        self._snap_enabled = True
        self._grid_size = 50.0  # 50cm default grid

        # Pan state
        self._panning = False
        self._pan_start = QPointF()

        # Smooth zoom state
        self._target_zoom = 1.0
        self._zoom_velocity = 0.0
        self._zoom_anchor: QPointF | None = None
        self._zoom_timer = QTimer(self)
        self._zoom_timer.setInterval(16)  # ~60 FPS
        self._zoom_timer.timeout.connect(self._animate_zoom)

        # Tool manager
        self._tool_manager = ToolManager(self)
        self._setup_tools()

        # Set up view properties
        self._setup_view()

    def _setup_tools(self) -> None:
        """Register and initialize drawing tools."""
        # Register tools
        self._tool_manager.register_tool(SelectTool(self))
        self._tool_manager.register_tool(RectangleTool(self))
        self._tool_manager.register_tool(PolygonTool(self))

        # Connect tool change signal
        self._tool_manager.tool_changed.connect(self.tool_changed.emit)

        # Set default tool
        self._tool_manager.set_active_tool(ToolType.SELECT)

    def _setup_view(self) -> None:
        """Configure view properties."""
        # Rendering quality
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # View behavior
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # Scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Enable mouse tracking for coordinate updates
        self.setMouseTracking(True)

        # Enable keyboard focus for key events (arrows)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        # Flip Y-axis for CAD convention (origin bottom-left, Y up)
        self._apply_transform()

        # Viewport update mode for smooth rendering
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)

    def _apply_transform(self) -> None:
        """Apply the current transform including Y-flip and zoom."""
        transform = QTransform()
        # Scale for zoom
        transform.scale(self._zoom_factor, -self._zoom_factor)  # Negative Y for flip
        # Translate to put origin at bottom-left after flip
        transform.translate(0, -self._canvas_scene.height_cm)
        self.setTransform(transform)

    # Properties

    @property
    def zoom_factor(self) -> float:
        """Current zoom factor (1.0 = 100%)."""
        return self._zoom_factor

    @property
    def zoom_percent(self) -> float:
        """Current zoom as percentage."""
        return self._zoom_factor * 100.0

    @property
    def grid_visible(self) -> bool:
        """Whether the grid is visible."""
        return self._grid_visible

    @property
    def snap_enabled(self) -> bool:
        """Whether snap to grid is enabled."""
        return self._snap_enabled

    @property
    def grid_size(self) -> float:
        """Current grid size in centimeters."""
        return self._grid_size

    @property
    def tool_manager(self) -> ToolManager:
        """The tool manager for this view."""
        return self._tool_manager

    def set_active_tool(self, tool_type: ToolType) -> None:
        """Set the active drawing tool.

        Args:
            tool_type: The tool type to activate
        """
        self._tool_manager.set_active_tool(tool_type)

    # Zoom methods

    def set_zoom(self, factor: float) -> None:
        """Set zoom to a specific factor.

        Args:
            factor: Zoom factor (1.0 = 100%)
        """
        factor = max(self.min_zoom, min(self.max_zoom, factor))
        self._zoom_factor = factor
        self._apply_transform()
        self.zoom_changed.emit(self.zoom_percent)

    def zoom_in(self, factor: float = 1.1) -> None:
        """Zoom in by the given factor.

        Args:
            factor: Zoom multiplier (default 1.1 for smooth zooming)
        """
        self.set_zoom(self._zoom_factor * factor)

    def zoom_out(self, factor: float = 1.1) -> None:
        """Zoom out by the given factor.

        Args:
            factor: Zoom divisor (default 1.1 for smooth zooming)
        """
        self.set_zoom(self._zoom_factor / factor)

    def reset_zoom(self) -> None:
        """Reset zoom to 100%."""
        self.set_zoom(1.0)

    def fit_in_view(self) -> None:
        """Fit the canvas (not the padded scene) in the view."""
        # Fit to the actual canvas rect, not the padded scene rect
        canvas_rect = self._canvas_scene.canvas_rect
        self.fitInView(canvas_rect, Qt.AspectRatioMode.KeepAspectRatio)
        # Extract zoom factor from current transform
        transform = self.transform()
        self._zoom_factor = abs(transform.m11())  # m11 is the x scale factor
        self.zoom_changed.emit(self.zoom_percent)

    # Grid methods

    def set_grid_visible(self, visible: bool) -> None:
        """Set grid visibility."""
        self._grid_visible = visible
        self.viewport().update()

    def set_snap_enabled(self, enabled: bool) -> None:
        """Set snap to grid enabled."""
        self._snap_enabled = enabled

    def set_grid_size(self, size: float) -> None:
        """Set grid size in centimeters."""
        self._grid_size = size
        if self._grid_visible:
            self.viewport().update()

    # Coordinate conversion

    def scene_to_canvas(self, scene_point: QPointF) -> QPointF:
        """Convert scene coordinates to canvas coordinates (Y-flip).

        Scene: Y-down, origin top-left (Qt convention)
        Canvas: Y-up, origin bottom-left (CAD convention)

        Args:
            scene_point: Point in scene coordinates

        Returns:
            Point in canvas coordinates (cm, Y-up)
        """
        return QPointF(
            scene_point.x(),
            self._canvas_scene.height_cm - scene_point.y(),
        )

    def canvas_to_scene(self, canvas_point: QPointF) -> QPointF:
        """Convert canvas coordinates to scene coordinates (Y-flip).

        Args:
            canvas_point: Point in canvas coordinates (cm, Y-up)

        Returns:
            Point in scene coordinates (Qt convention)
        """
        return QPointF(
            canvas_point.x(),
            self._canvas_scene.height_cm - canvas_point.y(),
        )

    def snap_point(self, point: QPointF) -> QPointF:
        """Snap a point to the grid if snap is enabled.

        Args:
            point: Point in canvas coordinates

        Returns:
            Snapped point if snap enabled, original point otherwise
        """
        if not self._snap_enabled:
            return point

        return QPointF(
            round(point.x() / self._grid_size) * self._grid_size,
            round(point.y() / self._grid_size) * self._grid_size,
        )

    # Event handlers

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for smooth zooming."""
        # Get the scroll amount (typically 120 per notch, but can vary)
        delta = event.angleDelta().y()

        if delta == 0:
            event.accept()
            return

        # Store the zoom anchor point (where the mouse is)
        self._zoom_anchor = self.mapToScene(event.position().toPoint())

        # Calculate zoom velocity based on scroll delta
        # Faster scrolling = faster zoom
        zoom_speed = 0.0002  # Sensitivity factor (lower = more precise)
        self._zoom_velocity += delta * zoom_speed

        # Clamp velocity to prevent extreme zooming
        max_velocity = 0.08  # Maximum zoom speed (lower = more controlled)
        self._zoom_velocity = max(-max_velocity, min(max_velocity, self._zoom_velocity))

        # Start the animation timer if not already running
        if not self._zoom_timer.isActive():
            self._zoom_timer.start()

        event.accept()

    def _animate_zoom(self) -> None:
        """Animate smooth zoom towards target."""
        # Apply velocity to zoom
        if abs(self._zoom_velocity) < 0.001:
            # Velocity too small, stop animation
            self._zoom_velocity = 0.0
            self._zoom_timer.stop()
            return

        # Calculate new zoom factor
        new_zoom = self._zoom_factor * (1.0 + self._zoom_velocity)
        new_zoom = max(self.min_zoom, min(self.max_zoom, new_zoom))

        # Apply the new zoom
        self._zoom_factor = new_zoom
        self._apply_transform()
        self.zoom_changed.emit(self.zoom_percent)

        # Apply friction to slow down
        friction = 0.85
        self._zoom_velocity *= friction

        # Stop if zoom reached limits
        if (new_zoom <= self.min_zoom and self._zoom_velocity < 0) or \
           (new_zoom >= self.max_zoom and self._zoom_velocity > 0):
            self._zoom_velocity = 0.0
            self._zoom_timer.stop()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for panning and tool operations."""
        # Grab keyboard focus so Delete/arrow keys work
        self.setFocus()

        if event.button() == Qt.MouseButton.MiddleButton:
            # Start panning
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        # Delegate to active tool
        tool = self._tool_manager.active_tool
        if tool:
            scene_pos = self.mapToScene(event.position().toPoint())
            if tool.mouse_press(event, scene_pos):
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for panning, tool operations, and coordinate updates."""
        # Update coordinates display
        scene_pos = self.mapToScene(event.position().toPoint())
        self.coordinates_changed.emit(scene_pos.x(), scene_pos.y())

        if self._panning:
            # Pan the view by translating
            delta = event.position() - self._pan_start
            self._pan_start = event.position()

            # Map two points to scene to get proper delta in scene coordinates
            # This correctly handles any transform (zoom, Y-flip, etc.)
            center = self.viewport().rect().center()
            scene_before = self.mapToScene(center)
            scene_after = self.mapToScene(
                center.x() + int(delta.x()),
                center.y() + int(delta.y())
            )

            # Move in opposite direction of mouse drag
            scene_delta = scene_before - scene_after
            new_center = self.mapToScene(center) + scene_delta
            self.centerOn(new_center)
            event.accept()
            return

        # Delegate to active tool
        tool = self._tool_manager.active_tool
        if tool and tool.mouse_move(event, scene_pos):
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to stop panning and finish tool operations."""
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            # Restore tool cursor
            tool = self._tool_manager.active_tool
            if tool:
                self.setCursor(tool.cursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        # Delegate to active tool
        tool = self._tool_manager.active_tool
        if tool:
            scene_pos = self.mapToScene(event.position().toPoint())
            if tool.mouse_release(event, scene_pos):
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle mouse double click for tool operations."""
        tool = self._tool_manager.active_tool
        if tool:
            scene_pos = self.mapToScene(event.position().toPoint())
            if tool.mouse_double_click(event, scene_pos):
                event.accept()
                return

        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press for tool operations and editing."""
        # Delegate to active tool first
        tool = self._tool_manager.active_tool
        if tool and tool.key_press(event):
            event.accept()
            return

        # Handle Delete key
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_items()
            event.accept()
            return

        # Handle arrow keys for moving selected items
        if event.key() in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            self._move_selected_items(event)
            event.accept()
            return

        super().keyPressEvent(event)

    def _delete_selected_items(self) -> None:
        """Delete all selected items from the scene."""
        scene = self.scene()
        selected = scene.selectedItems()
        for item in selected:
            scene.removeItem(item)

    def _move_selected_items(self, event: QKeyEvent) -> None:
        """Move selected items based on arrow key.

        Normal: move by grid size (default 50cm)
        Shift: move by 1cm (precision mode)
        """
        # Determine move distance: 1cm precision with Shift, otherwise grid size
        distance = (
            1.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
            else self._grid_size
        )

        # Determine direction (scene Y increases downward, but we want
        # Up arrow to move items up visually, which means negative Y)
        dx, dy = 0.0, 0.0
        if event.key() == Qt.Key.Key_Left:
            dx = -distance
        elif event.key() == Qt.Key.Key_Right:
            dx = distance
        elif event.key() == Qt.Key.Key_Up:
            dy = distance  # Up arrow = positive Y (up in our flipped view)
        elif event.key() == Qt.Key.Key_Down:
            dy = -distance  # Down arrow = negative Y (down in our flipped view)

        # Move all selected items
        for item in self.scene().selectedItems():
            item.moveBy(dx, dy)

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the background including optional grid."""
        super().drawBackground(painter, rect)

        if self._grid_visible:
            self._draw_grid(painter, rect)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the foreground including canvas border."""
        super().drawForeground(painter, rect)

        # Draw canvas border
        self._draw_canvas_border(painter)

    def _draw_canvas_border(self, painter: QPainter) -> None:
        """Draw a border around the canvas area."""
        # Get the actual canvas rect (not the padded scene rect)
        canvas_rect = self._canvas_scene.canvas_rect

        # Set up pen for border
        border_pen = QPen(QColor("#666666"))  # Dark gray border
        border_pen.setWidth(2)
        border_pen.setCosmetic(True)  # Constant width regardless of zoom
        painter.setPen(border_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Draw rectangle around canvas
        painter.drawRect(canvas_rect)

    def _draw_grid(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the grid overlay."""
        # Determine grid line spacing based on zoom
        grid_size = self._grid_size

        # Make grid adaptive - show coarser grid when zoomed out
        while grid_size * self._zoom_factor < 10:  # Less than 10 pixels
            grid_size *= 2
        while grid_size * self._zoom_factor > 100:  # More than 100 pixels
            grid_size /= 2

        # Set up pen for grid lines
        pen = QPen(QColor(200, 200, 200, 100))
        pen.setWidth(0)  # Cosmetic pen (1 pixel regardless of transform)
        painter.setPen(pen)

        # Calculate grid bounds
        left = int(rect.left() / grid_size) * grid_size
        top = int(rect.top() / grid_size) * grid_size
        right = rect.right()
        bottom = rect.bottom()

        # Draw vertical lines
        x = left
        while x <= right:
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_size

        # Draw horizontal lines
        y = top
        while y <= bottom:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_size

        # Draw major grid lines (every 5th line) slightly darker
        major_pen = QPen(QColor(180, 180, 180, 150))
        major_pen.setWidth(0)
        painter.setPen(major_pen)

        major_grid = grid_size * 5

        x = int(rect.left() / major_grid) * major_grid
        while x <= right:
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += major_grid

        y = int(rect.top() / major_grid) * major_grid
        while y <= bottom:
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += major_grid
