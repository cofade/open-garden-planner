"""Canvas view for the garden planner.

The view handles rendering, pan, zoom, and coordinate transformation.
It flips the Y-axis to provide CAD-style coordinates (origin at bottom-left,
Y increasing upward).
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsView, QLineEdit

from open_garden_planner.core import (
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.tools import (
    CircleTool,
    MeasureTool,
    PolygonTool,
    PolylineTool,
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
        self._scale_bar_visible = True

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

        # Command manager for undo/redo
        self._command_manager = CommandManager(self)

        # Drag tracking for undo support
        self._drag_start_positions: dict[QGraphicsItem, QPointF] = {}

        # Clipboard for copy/paste
        self._clipboard: list[dict] = []
        self._paste_offset = 20.0  # Offset in cm for pasted items

        # Tool manager
        self._tool_manager = ToolManager(self)
        self._setup_tools()

        # Calibration input widget (hidden by default)
        self._calibration_input = QLineEdit(self)
        self._calibration_input.setPlaceholderText("Distance in cm")
        self._calibration_input.setFixedWidth(150)
        self._calibration_input.hide()
        self._calibration_input.returnPressed.connect(self._on_calibration_input_entered)

        # Set up view properties
        self._setup_view()

    def _setup_tools(self) -> None:
        """Register and initialize drawing tools."""
        # Register basic tools
        self._tool_manager.register_tool(SelectTool(self))
        self._tool_manager.register_tool(MeasureTool(self))

        # Register generic shape tools
        rect_tool = RectangleTool(self, object_type=ObjectType.GENERIC_RECTANGLE)
        rect_tool.shortcut = "R"
        self._tool_manager.register_tool(rect_tool)

        poly_tool = PolygonTool(self, object_type=ObjectType.GENERIC_POLYGON)
        poly_tool.shortcut = "P"
        self._tool_manager.register_tool(poly_tool)

        circle_tool = CircleTool(self, object_type=ObjectType.GENERIC_CIRCLE)
        circle_tool.shortcut = "C"
        self._tool_manager.register_tool(circle_tool)

        # Register property object tools (polygon-based)
        house_tool = PolygonTool(self, object_type=ObjectType.HOUSE)
        house_tool.tool_type = ToolType.HOUSE
        house_tool.display_name = "House"
        house_tool.shortcut = "H"
        self._tool_manager.register_tool(house_tool)

        garage_tool = PolygonTool(self, object_type=ObjectType.GARAGE_SHED)
        garage_tool.tool_type = ToolType.GARAGE_SHED
        garage_tool.display_name = "Garage/Shed"
        self._tool_manager.register_tool(garage_tool)

        terrace_tool = PolygonTool(self, object_type=ObjectType.TERRACE_PATIO)
        terrace_tool.tool_type = ToolType.TERRACE_PATIO
        terrace_tool.display_name = "Terrace/Patio"
        terrace_tool.shortcut = "T"
        self._tool_manager.register_tool(terrace_tool)

        driveway_tool = PolygonTool(self, object_type=ObjectType.DRIVEWAY)
        driveway_tool.tool_type = ToolType.DRIVEWAY
        driveway_tool.display_name = "Driveway"
        driveway_tool.shortcut = "D"
        self._tool_manager.register_tool(driveway_tool)

        pond_tool = PolygonTool(self, object_type=ObjectType.POND_POOL)
        pond_tool.tool_type = ToolType.POND_POOL
        pond_tool.display_name = "Pond/Pool"
        self._tool_manager.register_tool(pond_tool)

        greenhouse_tool = PolygonTool(self, object_type=ObjectType.GREENHOUSE)
        greenhouse_tool.tool_type = ToolType.GREENHOUSE
        greenhouse_tool.display_name = "Greenhouse"
        self._tool_manager.register_tool(greenhouse_tool)

        garden_bed_tool = PolygonTool(self, object_type=ObjectType.GARDEN_BED)
        garden_bed_tool.tool_type = ToolType.GARDEN_BED
        garden_bed_tool.display_name = "Garden Bed"
        garden_bed_tool.shortcut = "B"
        self._tool_manager.register_tool(garden_bed_tool)

        # Register property object tools (polyline-based)
        fence_tool = PolylineTool(self, object_type=ObjectType.FENCE)
        fence_tool.tool_type = ToolType.FENCE
        fence_tool.display_name = "Fence"
        fence_tool.shortcut = "F"
        self._tool_manager.register_tool(fence_tool)

        wall_tool = PolylineTool(self, object_type=ObjectType.WALL)
        wall_tool.tool_type = ToolType.WALL
        wall_tool.display_name = "Wall"
        wall_tool.shortcut = "W"
        self._tool_manager.register_tool(wall_tool)

        path_tool = PolylineTool(self, object_type=ObjectType.PATH)
        path_tool.tool_type = ToolType.PATH
        path_tool.display_name = "Path"
        path_tool.shortcut = "L"
        self._tool_manager.register_tool(path_tool)

        # Register plant tools (circle-based)
        tree_tool = CircleTool(self, object_type=ObjectType.TREE)
        tree_tool.tool_type = ToolType.TREE
        tree_tool.display_name = "Tree"
        tree_tool.shortcut = "1"
        self._tool_manager.register_tool(tree_tool)

        shrub_tool = CircleTool(self, object_type=ObjectType.SHRUB)
        shrub_tool.tool_type = ToolType.SHRUB
        shrub_tool.display_name = "Shrub"
        shrub_tool.shortcut = "2"
        self._tool_manager.register_tool(shrub_tool)

        perennial_tool = CircleTool(self, object_type=ObjectType.PERENNIAL)
        perennial_tool.tool_type = ToolType.PERENNIAL
        perennial_tool.display_name = "Perennial"
        perennial_tool.shortcut = "3"
        self._tool_manager.register_tool(perennial_tool)

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

        # Accept drops from gallery panel
        self.setAcceptDrops(True)

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
    def scale_bar_visible(self) -> bool:
        """Whether the scale bar is visible."""
        return self._scale_bar_visible

    @property
    def tool_manager(self) -> ToolManager:
        """The tool manager for this view."""
        return self._tool_manager

    @property
    def command_manager(self) -> CommandManager:
        """The command manager for undo/redo."""
        return self._command_manager

    def add_item(self, item: QGraphicsItem, item_type: str = "item") -> None:
        """Add an item to the scene with undo support.

        Args:
            item: The graphics item to add
            item_type: Description for undo (e.g., "rectangle", "polygon")
        """
        command = CreateItemCommand(self.scene(), item, item_type)
        self._command_manager.execute(command)

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

    def set_scale_bar_visible(self, visible: bool) -> None:
        """Set scale bar visibility."""
        self._scale_bar_visible = visible
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

    # Drag-and-drop from gallery panel

    def dragEnterEvent(self, event) -> None:
        """Accept drag events from the gallery panel."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("gallery:"):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """Accept drag move events from the gallery panel."""
        if event.mimeData().hasText() and event.mimeData().text().startswith("gallery:"):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        """Handle drop from the gallery panel - activate the tool and simulate a click."""
        text = event.mimeData().text()
        if not text.startswith("gallery:"):
            super().dropEvent(event)
            return

        event.acceptProposedAction()

        # Parse the gallery data: "gallery:TOOL_TYPE:species=xxx:category=YYY"
        parts = text.split(":")
        tool_name = parts[1] if len(parts) > 1 else ""

        # Find the matching ToolType
        try:
            from open_garden_planner.core.tools import ToolType as TT

            tool_type = TT[tool_name]
        except (KeyError, ValueError):
            return

        # Activate the tool
        self.set_active_tool(tool_type)

        # Map the drop position to scene coordinates
        scene_pos = self.mapToScene(event.position().toPoint())

        # For plant tools (circle-based), create the item directly at the drop location
        if tool_type in (TT.TREE, TT.SHRUB, TT.PERENNIAL):
            from open_garden_planner.ui.canvas.items import CircleItem

            # Determine plant size defaults
            size_map = {TT.TREE: 200.0, TT.SHRUB: 100.0, TT.PERENNIAL: 60.0}
            default_diameter = size_map.get(tool_type, 100.0)

            # Map ToolType to ObjectType
            obj_map = {
                TT.TREE: ObjectType.TREE,
                TT.SHRUB: ObjectType.SHRUB,
                TT.PERENNIAL: ObjectType.PERENNIAL,
            }
            obj_type = obj_map.get(tool_type, ObjectType.TREE)

            # Snap to grid if enabled
            if self._snap_enabled:
                scene_pos = self._snap_to_grid(scene_pos)

            item = CircleItem(
                center_x=scene_pos.x(),
                center_y=scene_pos.y(),
                radius=default_diameter / 2,
                object_type=obj_type,
            )
            # Assign to active layer
            active_layer = self._canvas_scene.active_layer
            if active_layer:
                item.layer_id = active_layer.id

            # Use the command manager for undo support
            cmd = CreateItemCommand(self._canvas_scene, item)
            self._command_manager.execute(cmd)

            # Switch to select tool and select the new item
            self.set_active_tool(TT.SELECT)
            self._canvas_scene.clearSelection()
            item.setSelected(True)

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

        # Handle calibration mode
        if self._canvas_scene.is_calibrating and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            self._canvas_scene.add_calibration_point(scene_pos)
            event.accept()
            return

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

        # Store positions of selected items for drag undo tracking
        # Must be AFTER super() so item selection is updated
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_positions = {
                item: item.pos() for item in self.scene().selectedItems()
            }

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
                self._drag_start_positions.clear()
                return

        super().mouseReleaseEvent(event)

        # Check if items were dragged and create undo command
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_positions:
            self._finalize_drag_move()

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
        # Handle ESC to cancel calibration
        if event.key() == Qt.Key.Key_Escape and self._canvas_scene.is_calibrating:
            self._canvas_scene.cancel_calibration()
            event.accept()
            return

        # Handle Copy (Ctrl+C)
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.copy_selected()
            event.accept()
            return

        # Handle Cut (Ctrl+X)
        if event.key() == Qt.Key.Key_X and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.cut_selected()
            event.accept()
            return

        # Handle Paste (Ctrl+V)
        if event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.paste()
            event.accept()
            return

        # Handle Duplicate (Ctrl+D)
        if event.key() == Qt.Key.Key_D and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.duplicate_selected()
            event.accept()
            return

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
        """Delete all selected items from the scene with undo support."""
        selected = self.scene().selectedItems()
        if not selected:
            return
        command = DeleteItemsCommand(self.scene(), selected)
        self._command_manager.execute(command)

    def _move_selected_items(self, event: QKeyEvent) -> None:
        """Move selected items based on arrow key with undo support.

        Normal: move by grid size (default 50cm)
        Shift: move by 1cm (precision mode)
        """
        selected = self.scene().selectedItems()
        if not selected:
            return

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

        # Move with undo support
        command = MoveItemsCommand(selected, QPointF(dx, dy))
        self._command_manager.execute(command)

    def _finalize_drag_move(self) -> None:
        """Create undo command for mouse drag movement if items moved."""
        if not self._drag_start_positions:
            return

        # Find items that actually moved
        moved_items = []
        total_delta = QPointF(0, 0)

        for item, start_pos in self._drag_start_positions.items():
            current_pos = item.pos()
            if start_pos != current_pos:
                moved_items.append(item)
                # Calculate delta (should be same for all items in a drag)
                total_delta = current_pos - start_pos

        if moved_items and (total_delta.x() != 0 or total_delta.y() != 0):
            # Move items back to start, then execute command to move them
            # This ensures the command captures the correct state
            for item in moved_items:
                start_pos = self._drag_start_positions[item]
                item.setPos(start_pos)

            command = MoveItemsCommand(moved_items, total_delta)
            self._command_manager.execute(command)

        self._drag_start_positions.clear()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the background."""
        super().drawBackground(painter, rect)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the foreground including canvas border and grid overlay."""
        super().drawForeground(painter, rect)

        # Draw canvas border
        self._draw_canvas_border(painter)

        # Draw grid overlay on top of everything
        if self._grid_visible:
            self._draw_grid(painter, rect)

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

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the view, then draw overlays in viewport coordinates."""
        super().paintEvent(event)

        if self._scale_bar_visible:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_scale_bar(painter)
            painter.end()

    # Scale bar constants
    _SCALE_BAR_NICE_DISTANCES = [
        1, 2, 5, 10, 20, 50,
        100, 200, 500,
        1000, 2000, 5000, 10000,
    ]
    _SCALE_BAR_MARGIN = 12
    _SCALE_BAR_TICK_H = 5
    _SCALE_BAR_LINE_WIDTH = 2

    @staticmethod
    def _format_distance(cm: float) -> str:
        """Format a distance in cm as a human-readable string.

        Args:
            cm: Distance in centimeters

        Returns:
            Formatted string (e.g., "50 cm", "2 m", "1.5 km")
        """
        if cm >= 100000:
            km = cm / 100000
            return f"{km:g} km"
        if cm >= 100:
            m = cm / 100
            return f"{m:g} m"
        return f"{cm:g} cm"

    def _pick_scale_bar_distance(self) -> float:
        """Pick the best round distance for the scale bar at current zoom.

        Returns:
            Distance in cm that produces a bar of reasonable pixel width.
        """
        target_px = 150.0
        best = self._SCALE_BAR_NICE_DISTANCES[0]
        best_diff = abs(best * self._zoom_factor - target_px)

        for d in self._SCALE_BAR_NICE_DISTANCES:
            px = d * self._zoom_factor
            diff = abs(px - target_px)
            if diff < best_diff:
                best = d
                best_diff = diff

        return float(best)

    def _draw_scale_bar(self, painter: QPainter) -> None:
        """Draw a Google Maps-style scale bar in the bottom-left corner.

        Minimal design: text label above a horizontal line with end ticks,
        drawn with a white outline for legibility over any background.

        Args:
            painter: QPainter targeting the viewport (pixel coordinates)
        """
        distance_cm = self._pick_scale_bar_distance()
        bar_width_px = distance_cm * self._zoom_factor
        label = self._format_distance(distance_cm)

        margin = self._SCALE_BAR_MARGIN
        tick_h = self._SCALE_BAR_TICK_H
        lw = self._SCALE_BAR_LINE_WIDTH

        # Text setup
        font = QFont()
        font.setPointSize(8)
        font.setBold(True)
        painter.setFont(font)
        # Position: bottom-right corner
        vp = self.viewport().rect()
        bar_x = vp.width() - margin - bar_width_px
        bar_y = vp.height() - margin
        text_x = bar_x
        text_y = bar_y - tick_h - 4  # gap between text baseline and tick top

        # Draw white outline pass (thicker, behind the dark foreground)
        outline_pen = QPen(QColor(255, 255, 255, 220))
        outline_pen.setWidth(lw + 3)
        outline_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outline_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        # Outline: horizontal line
        painter.drawLine(
            int(bar_x), int(bar_y),
            int(bar_x + bar_width_px), int(bar_y),
        )
        # Outline: left tick
        painter.drawLine(
            int(bar_x), int(bar_y),
            int(bar_x), int(bar_y - tick_h),
        )
        # Outline: right tick
        painter.drawLine(
            int(bar_x + bar_width_px), int(bar_y),
            int(bar_x + bar_width_px), int(bar_y - tick_h),
        )

        # Outline: text
        outline_pen.setWidth(3)
        painter.setPen(outline_pen)
        painter.drawText(int(text_x), int(text_y), label)

        # Draw dark foreground pass
        fg_color = QColor(40, 40, 40)
        fg_pen = QPen(fg_color)
        fg_pen.setWidth(lw)
        fg_pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(fg_pen)

        # Foreground: horizontal line
        painter.drawLine(
            int(bar_x), int(bar_y),
            int(bar_x + bar_width_px), int(bar_y),
        )
        # Foreground: left tick
        painter.drawLine(
            int(bar_x), int(bar_y),
            int(bar_x), int(bar_y - tick_h),
        )
        # Foreground: right tick
        painter.drawLine(
            int(bar_x + bar_width_px), int(bar_y),
            int(bar_x + bar_width_px), int(bar_y - tick_h),
        )

        # Foreground: text
        painter.setPen(fg_color)
        painter.drawText(int(text_x), int(text_y), label)

    def copy_selected(self) -> None:
        """Copy selected items to clipboard."""
        selected = self.scene().selectedItems()
        if not selected:
            return

        # Serialize selected items
        self._clipboard = []
        for item in selected:
            obj_data = self._serialize_item(item)
            if obj_data:
                self._clipboard.append(obj_data)

        # Show status message
        if len(self._clipboard) > 0:
            self.set_status_message(f"Copied {len(self._clipboard)} item(s)")

    def cut_selected(self) -> None:
        """Cut selected items (copy then delete)."""
        selected = self.scene().selectedItems()
        if not selected:
            return

        # Copy first
        self.copy_selected()

        # Then delete
        if self._clipboard:
            self._delete_selected_items()
            self.set_status_message(f"Cut {len(self._clipboard)} item(s)")

    def paste(self) -> None:
        """Paste items from clipboard."""
        if not self._clipboard:
            self.set_status_message("Nothing to paste")
            return

        # Deselect all items
        for item in self.scene().selectedItems():
            item.setSelected(False)

        # Create new items from clipboard
        pasted_items = []
        for obj_data in self._clipboard:
            # Create a copy of the object data
            obj_copy = obj_data.copy()

            # Apply offset to position
            if "x" in obj_copy:
                obj_copy["x"] += self._paste_offset
            if "y" in obj_copy:
                obj_copy["y"] += self._paste_offset
            if "center_x" in obj_copy:
                obj_copy["center_x"] += self._paste_offset
            if "center_y" in obj_copy:
                obj_copy["center_y"] += self._paste_offset
            if "points" in obj_copy:
                obj_copy["points"] = [
                    {"x": p["x"] + self._paste_offset, "y": p["y"] + self._paste_offset}
                    for p in obj_copy["points"]
                ]

            # Deserialize the item
            item = self._deserialize_item(obj_copy)
            if item:
                pasted_items.append(item)

        # Add all pasted items to scene and select them
        if pasted_items:
            # Use command for undo support
            from open_garden_planner.core import CreateItemsCommand

            command = CreateItemsCommand(self.scene(), pasted_items, "pasted objects")
            self._command_manager.execute(command)

            # Select the pasted items
            for item in pasted_items:
                item.setSelected(True)

            self.set_status_message(f"Pasted {len(pasted_items)} item(s)")

    def duplicate_selected(self) -> None:
        """Duplicate selected items (copy and paste in one action)."""
        selected = self.scene().selectedItems()
        if not selected:
            self.set_status_message("Nothing to duplicate")
            return

        # Serialize selected items directly (don't modify clipboard)
        items_to_duplicate = []
        for item in selected:
            obj_data = self._serialize_item(item)
            if obj_data:
                items_to_duplicate.append(obj_data)

        if not items_to_duplicate:
            return

        # Deselect all items
        for item in self.scene().selectedItems():
            item.setSelected(False)

        # Create new items with offset
        duplicated_items = []
        for obj_data in items_to_duplicate:
            obj_copy = obj_data.copy()

            # Apply offset to position
            if "x" in obj_copy:
                obj_copy["x"] += self._paste_offset
            if "y" in obj_copy:
                obj_copy["y"] += self._paste_offset
            if "center_x" in obj_copy:
                obj_copy["center_x"] += self._paste_offset
            if "center_y" in obj_copy:
                obj_copy["center_y"] += self._paste_offset
            if "points" in obj_copy:
                obj_copy["points"] = [
                    {"x": p["x"] + self._paste_offset, "y": p["y"] + self._paste_offset}
                    for p in obj_copy["points"]
                ]

            # Deserialize the item
            item = self._deserialize_item(obj_copy)
            if item:
                duplicated_items.append(item)

        # Add all duplicated items to scene and select them
        if duplicated_items:
            from open_garden_planner.core import CreateItemsCommand

            command = CreateItemsCommand(self.scene(), duplicated_items, "duplicated objects")
            self._command_manager.execute(command)

            # Select the duplicated items
            for item in duplicated_items:
                item.setSelected(True)

            self.set_status_message(f"Duplicated {len(duplicated_items)} item(s)")

    def _serialize_item(self, item: QGraphicsItem) -> dict | None:
        """Serialize a single graphics item (reuses project manager logic).

        Args:
            item: The graphics item to serialize

        Returns:
            Dictionary representation of the item, or None if not serializable
        """
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        if isinstance(item, BackgroundImageItem):
            return item.to_dict()
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            data = {
                "type": "rectangle",
                "x": item.pos().x() + rect.x(),
                "y": item.pos().y() + rect.y(),
                "width": rect.width(),
                "height": rect.height(),
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            # Save custom fill and stroke colors (with alpha)
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            return data
        elif isinstance(item, CircleItem):
            data = {
                "type": "circle",
                "center_x": item.pos().x() + item.center.x(),
                "center_y": item.pos().y() + item.center.y(),
                "radius": item.radius,
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            # Save custom fill and stroke colors (with alpha)
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            return data
        elif isinstance(item, PolylineItem):
            data = {
                "type": "polyline",
                "points": [{"x": item.pos().x() + p.x(), "y": item.pos().y() + p.y()} for p in item.points],
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            # Save custom stroke color (polylines don't have fill, with alpha)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            return data
        elif isinstance(item, PolygonItem):
            polygon = item.polygon()
            points = []
            for i in range(polygon.count()):
                pt = polygon.at(i)
                points.append({
                    "x": item.pos().x() + pt.x(),
                    "y": item.pos().y() + pt.y(),
                })
            data = {
                "type": "polygon",
                "points": points,
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            # Save custom fill and stroke colors (with alpha)
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            return data
        return None

    def _deserialize_item(self, obj: dict) -> QGraphicsItem | None:
        """Deserialize a single object to a graphics item.

        Args:
            obj: Dictionary representation of the item

        Returns:
            Graphics item, or None if deserialization failed
        """
        from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
        from open_garden_planner.core.object_types import ObjectType, StrokeStyle
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        obj_type = obj.get("type")

        # Extract common fields
        object_type = None
        if "object_type" in obj:
            try:
                object_type = ObjectType[obj["object_type"]]
            except KeyError:
                object_type = None

        name = obj.get("name", "")
        metadata = obj.get("metadata", {})
        fill_pattern = None
        if "fill_pattern" in obj:
            try:
                fill_pattern = FillPattern[obj["fill_pattern"]]
            except KeyError:
                fill_pattern = None

        stroke_style = None
        if "stroke_style" in obj:
            try:
                stroke_style = StrokeStyle[obj["stroke_style"]]
            except KeyError:
                stroke_style = None

        if obj_type == "background_image":
            try:
                return BackgroundImageItem.from_dict(obj)
            except (ValueError, FileNotFoundError):
                # Image file may have been moved/deleted
                return None
        elif obj_type == "rectangle":
            item = RectangleItem(
                obj["x"],
                obj["y"],
                obj["width"],
                obj["height"],
                object_type=object_type or ObjectType.GENERIC_RECTANGLE,
                name=name,
                metadata=metadata,
                fill_pattern=fill_pattern,
                stroke_style=stroke_style,
            )
            # Restore custom colors if saved
            if "fill_color" in obj:
                # If we have a pattern, recreate the brush with both color and pattern
                if fill_pattern:
                    brush = create_pattern_brush(fill_pattern, QColor(obj["fill_color"]))
                else:
                    brush = item.brush()
                    brush.setColor(QColor(obj["fill_color"]))
                item.setBrush(brush)
            if "stroke_color" in obj:
                pen = item.pen()
                pen.setColor(QColor(obj["stroke_color"]))
                if "stroke_width" in obj:
                    pen.setWidthF(obj["stroke_width"])
                if stroke_style:
                    pen.setStyle(stroke_style.to_qt_pen_style())
                item.setPen(pen)
            return item
        elif obj_type == "circle":
            item = CircleItem(
                obj["center_x"],
                obj["center_y"],
                obj["radius"],
                object_type=object_type or ObjectType.GENERIC_CIRCLE,
                name=name,
                metadata=metadata,
                fill_pattern=fill_pattern,
                stroke_style=stroke_style,
            )
            # Restore custom colors if saved
            if "fill_color" in obj:
                color = QColor(obj["fill_color"])
                # Store the base color in the item
                if hasattr(item, 'fill_color'):
                    item.fill_color = color
                # If we have a pattern, recreate the brush with both color and pattern
                if fill_pattern:
                    brush = create_pattern_brush(fill_pattern, color)
                else:
                    brush = item.brush()
                    brush.setColor(color)
                item.setBrush(brush)
            if "stroke_color" in obj:
                pen = item.pen()
                pen.setColor(QColor(obj["stroke_color"]))
                if "stroke_width" in obj:
                    pen.setWidthF(obj["stroke_width"])
                if stroke_style:
                    pen.setStyle(stroke_style.to_qt_pen_style())
                item.setPen(pen)
            return item
        elif obj_type == "polyline":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 2:
                item = PolylineItem(
                    points,
                    object_type=object_type or ObjectType.FENCE,
                    name=name,
                )
                # Restore custom stroke color if saved
                if "stroke_color" in obj:
                    pen = item.pen()
                    pen.setColor(QColor(obj["stroke_color"]))
                    if "stroke_width" in obj:
                        pen.setWidthF(obj["stroke_width"])
                    item.setPen(pen)
                return item
        elif obj_type == "polygon":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 3:
                item = PolygonItem(
                    points,
                    object_type=object_type or ObjectType.GENERIC_POLYGON,
                    name=name,
                    metadata=metadata,
                    fill_pattern=fill_pattern,
                    stroke_style=stroke_style,
                )
                # Restore custom colors if saved
                if "fill_color" in obj:
                    color = QColor(obj["fill_color"])
                    # Store the base color in the item
                    if hasattr(item, 'fill_color'):
                        item.fill_color = color
                    # If we have a pattern, recreate the brush with both color and pattern
                    if fill_pattern:
                        brush = create_pattern_brush(fill_pattern, color)
                    else:
                        brush = item.brush()
                        brush.setColor(color)
                    item.setBrush(brush)
                if "stroke_color" in obj:
                    pen = item.pen()
                    pen.setColor(QColor(obj["stroke_color"]))
                    if "stroke_width" in obj:
                        pen.setWidthF(obj["stroke_width"])
                    if stroke_style:
                        pen.setStyle(stroke_style.to_qt_pen_style())
                    item.setPen(pen)
                return item
        return None

    def show_calibration_input(self, scene_pos: QPointF) -> None:
        """Show calibration input widget near the given scene position.

        Args:
            scene_pos: Position in scene coordinates
        """
        # Convert scene position to view coordinates
        view_pos = self.mapFromScene(scene_pos)

        # Position the input widget near the cursor (offset to the right and down)
        x = view_pos.x() + 20
        y = view_pos.y() + 20

        # Keep within view bounds
        if x + self._calibration_input.width() > self.width():
            x = view_pos.x() - self._calibration_input.width() - 20
        if y + self._calibration_input.height() > self.height():
            y = view_pos.y() - self._calibration_input.height() - 20

        self._calibration_input.move(int(x), int(y))
        self._calibration_input.clear()
        self._calibration_input.show()
        self._calibration_input.setFocus()

    def hide_calibration_input(self) -> None:
        """Hide the calibration input widget."""
        self._calibration_input.hide()

    def _on_calibration_input_entered(self) -> None:
        """Handle Enter key in calibration input."""
        text = self._calibration_input.text().strip()
        try:
            distance_cm = float(text)
            if distance_cm > 0:
                self._canvas_scene.finish_calibration(distance_cm)
            else:
                self.set_status_message("Distance must be positive")
        except ValueError:
            self.set_status_message("Invalid distance. Enter a number in centimeters.")

    def set_status_message(self, message: str) -> None:
        """Set status message (to be picked up by main window).

        Args:
            message: The status message to display
        """
        # This will be picked up by the main window's status bar
        # For now, we'll emit it as a signal if the parent has a status bar
        if self.parent() and hasattr(self.parent(), 'statusBar'):
            status_bar = self.parent().statusBar()
            if status_bar:
                status_bar.showMessage(message)
