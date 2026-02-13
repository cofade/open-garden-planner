"""Canvas view for the garden planner.

The view handles rendering, pan, zoom, and coordinate transformation.
It flips the Y-axis to provide CAD-style coordinates (origin at bottom-left,
Y increasing upward).
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
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
    AlignItemsCommand,
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
)
from open_garden_planner.core.alignment import (
    AlignMode,
    DistributeMode,
    align_items,
    distribute_items,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.snapping import ObjectSnapper, SnapGuide
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
        self._object_snap_enabled = True
        self._grid_size = 50.0  # 50cm default grid
        self._scale_bar_visible = True

        # Object snapping engine and visual guides
        self._object_snapper = ObjectSnapper(threshold=10.0)
        self._snap_guides: list[SnapGuide] = []
        self._snap_guide_color = QColor(255, 0, 128, 180)  # Magenta

        # Pan state
        self._panning = False
        self._pan_start = QPointF()

        # Command manager for undo/redo
        self._command_manager = CommandManager(self)
        self._canvas_scene._command_manager = self._command_manager

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
        self._calibration_input.setPlaceholderText(self.tr("Distance in cm"))
        self._calibration_input.setFixedWidth(150)
        self._calibration_input.hide()
        self._calibration_input.returnPressed.connect(self._on_calibration_input_entered)

        # Theme colors for overlays (defaults; overridden by apply_theme_colors)
        self._grid_color = QColor(200, 200, 200, 100)
        self._grid_major_color = QColor(180, 180, 180, 150)
        self._canvas_border_color = QColor("#666666")
        self._scale_bar_fg = QColor(40, 40, 40)
        self._scale_bar_outline = QColor(255, 255, 255, 220)

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
        house_tool.display_name = self.tr("House")
        house_tool.shortcut = "H"
        self._tool_manager.register_tool(house_tool)

        garage_tool = PolygonTool(self, object_type=ObjectType.GARAGE_SHED)
        garage_tool.tool_type = ToolType.GARAGE_SHED
        garage_tool.display_name = self.tr("Garage/Shed")
        self._tool_manager.register_tool(garage_tool)

        terrace_tool = PolygonTool(self, object_type=ObjectType.TERRACE_PATIO)
        terrace_tool.tool_type = ToolType.TERRACE_PATIO
        terrace_tool.display_name = self.tr("Terrace/Patio")
        terrace_tool.shortcut = "T"
        self._tool_manager.register_tool(terrace_tool)

        driveway_tool = PolygonTool(self, object_type=ObjectType.DRIVEWAY)
        driveway_tool.tool_type = ToolType.DRIVEWAY
        driveway_tool.display_name = self.tr("Driveway")
        driveway_tool.shortcut = "D"
        self._tool_manager.register_tool(driveway_tool)

        pond_tool = PolygonTool(self, object_type=ObjectType.POND_POOL)
        pond_tool.tool_type = ToolType.POND_POOL
        pond_tool.display_name = self.tr("Pond/Pool")
        self._tool_manager.register_tool(pond_tool)

        greenhouse_tool = PolygonTool(self, object_type=ObjectType.GREENHOUSE)
        greenhouse_tool.tool_type = ToolType.GREENHOUSE
        greenhouse_tool.display_name = self.tr("Greenhouse")
        self._tool_manager.register_tool(greenhouse_tool)

        garden_bed_tool = PolygonTool(self, object_type=ObjectType.GARDEN_BED)
        garden_bed_tool.tool_type = ToolType.GARDEN_BED
        garden_bed_tool.display_name = self.tr("Garden Bed")
        garden_bed_tool.shortcut = "B"
        self._tool_manager.register_tool(garden_bed_tool)

        lawn_tool = PolygonTool(self, object_type=ObjectType.LAWN)
        lawn_tool.tool_type = ToolType.LAWN
        lawn_tool.display_name = self.tr("Lawn")
        self._tool_manager.register_tool(lawn_tool)

        # Register property object tools (polyline-based)
        fence_tool = PolylineTool(self, object_type=ObjectType.FENCE)
        fence_tool.tool_type = ToolType.FENCE
        fence_tool.display_name = self.tr("Fence")
        fence_tool.shortcut = "F"
        self._tool_manager.register_tool(fence_tool)

        wall_tool = PolylineTool(self, object_type=ObjectType.WALL)
        wall_tool.tool_type = ToolType.WALL
        wall_tool.display_name = self.tr("Wall")
        wall_tool.shortcut = "W"
        self._tool_manager.register_tool(wall_tool)

        path_tool = PolylineTool(self, object_type=ObjectType.PATH)
        path_tool.tool_type = ToolType.PATH
        path_tool.display_name = self.tr("Path")
        path_tool.shortcut = "L"
        self._tool_manager.register_tool(path_tool)

        # Register plant tools (circle-based)
        tree_tool = CircleTool(self, object_type=ObjectType.TREE)
        tree_tool.tool_type = ToolType.TREE
        tree_tool.display_name = self.tr("Tree")
        tree_tool.shortcut = "1"
        self._tool_manager.register_tool(tree_tool)

        shrub_tool = CircleTool(self, object_type=ObjectType.SHRUB)
        shrub_tool.tool_type = ToolType.SHRUB
        shrub_tool.display_name = self.tr("Shrub")
        shrub_tool.shortcut = "2"
        self._tool_manager.register_tool(shrub_tool)

        perennial_tool = CircleTool(self, object_type=ObjectType.PERENNIAL)
        perennial_tool.tool_type = ToolType.PERENNIAL
        perennial_tool.display_name = self.tr("Perennial")
        perennial_tool.shortcut = "3"
        self._tool_manager.register_tool(perennial_tool)

        # Register hedge section tool (rectangle-based, SVG-rendered)
        hedge_tool = RectangleTool(self, object_type=ObjectType.HEDGE_SECTION)
        hedge_tool.tool_type = ToolType.HEDGE_SECTION
        hedge_tool.display_name = self.tr("Hedge Section")
        self._tool_manager.register_tool(hedge_tool)

        # Register outdoor furniture tools (rectangle-based, SVG-rendered)
        rect_furniture = [
            (ObjectType.TABLE_RECTANGULAR, ToolType.TABLE_RECTANGULAR, self.tr("Table (Rectangular)")),
            (ObjectType.CHAIR, ToolType.CHAIR, self.tr("Chair")),
            (ObjectType.BENCH, ToolType.BENCH, self.tr("Bench")),
            (ObjectType.LOUNGER, ToolType.LOUNGER, self.tr("Lounger")),
        ]
        for obj_type, tool_type, display_name in rect_furniture:
            tool = RectangleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        # Register round furniture tools (circle-based, SVG-rendered)
        circle_furniture = [
            (ObjectType.TABLE_ROUND, ToolType.TABLE_ROUND, self.tr("Table (Round)")),
            (ObjectType.PARASOL, ToolType.PARASOL, self.tr("Parasol")),
            (ObjectType.BBQ_GRILL, ToolType.BBQ_GRILL, self.tr("BBQ/Grill")),
            (ObjectType.FIRE_PIT, ToolType.FIRE_PIT, self.tr("Fire Pit")),
            (ObjectType.PLANTER_POT, ToolType.PLANTER_POT, self.tr("Planter/Pot")),
        ]
        for obj_type, tool_type, display_name in circle_furniture:
            tool = CircleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        # Register garden infrastructure tools (SVG-rendered)
        rect_infrastructure = [
            (ObjectType.RAISED_BED, ToolType.RAISED_BED, self.tr("Raised Bed")),
            (ObjectType.COMPOST_BIN, ToolType.COMPOST_BIN, self.tr("Compost Bin")),
            (ObjectType.COLD_FRAME, ToolType.COLD_FRAME, self.tr("Cold Frame")),
            (ObjectType.TOOL_SHED, ToolType.TOOL_SHED, self.tr("Tool Shed")),
        ]
        for obj_type, tool_type, display_name in rect_infrastructure:
            tool = RectangleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        circle_infrastructure = [
            (ObjectType.RAIN_BARREL, ToolType.RAIN_BARREL, self.tr("Rain Barrel")),
            (ObjectType.WATER_TAP, ToolType.WATER_TAP, self.tr("Water Tap")),
        ]
        for obj_type, tool_type, display_name in circle_infrastructure:
            tool = CircleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

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

        # Use minimal updates — only repaint dirty regions
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)

        # Accept drops from gallery panel
        self.setAcceptDrops(True)

    def apply_theme_colors(self, colors: dict[str, str]) -> None:
        """Update overlay colors from the theme palette.

        Args:
            colors: Theme color dictionary from ThemeColors
        """
        if "grid_line" in colors:
            c = QColor(colors["grid_line"])
            c.setAlpha(100)
            self._grid_color = c
        if "grid_line_major" in colors:
            c = QColor(colors["grid_line_major"])
            c.setAlpha(150)
            self._grid_major_color = c
        if "canvas_border" in colors:
            self._canvas_border_color = QColor(colors["canvas_border"])
        if "scale_bar_fg" in colors:
            self._scale_bar_fg = QColor(colors["scale_bar_fg"])
        if "scale_bar_outline" in colors:
            c = QColor(colors["scale_bar_outline"])
            c.setAlpha(220)
            self._scale_bar_outline = c

        # Also propagate to the scene
        self._canvas_scene.apply_theme_colors(colors)
        self.viewport().update()

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
    def object_snap_enabled(self) -> bool:
        """Whether snap to objects is enabled."""
        return self._object_snap_enabled

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

    @property
    def active_tool(self) -> object | None:
        """The currently active drawing tool."""
        return self._tool_manager.active_tool

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

    def set_object_snap_enabled(self, enabled: bool) -> None:
        """Set snap to objects enabled."""
        self._object_snap_enabled = enabled

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

    def clamp_to_canvas(self, point: QPointF) -> QPointF:
        """Clamp a point to stay within canvas boundaries.

        Args:
            point: Point in scene coordinates

        Returns:
            Point clamped to canvas rect
        """
        canvas_rect = self._canvas_scene.canvas_rect
        x = max(canvas_rect.left(), min(point.x(), canvas_rect.right()))
        y = max(canvas_rect.top(), min(point.y(), canvas_rect.bottom()))
        return QPointF(x, y)

    def _clamp_items_to_canvas(self, items: list[QGraphicsItem]) -> None:
        """Push items back so their combined bounding rect stays inside the canvas.

        Computes how far the selection overflows each edge and shifts all items
        together by the smallest correction needed.
        Background images are excluded from clamping.

        Args:
            items: The items to constrain.
        """
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        # Filter out background images — they should move freely beyond the canvas
        clampable = [i for i in items if not isinstance(i, BackgroundImageItem)]
        if not clampable:
            return

        canvas = self._canvas_scene.canvas_rect
        combined = clampable[0].sceneBoundingRect()
        for item in clampable[1:]:
            combined = combined.united(item.sceneBoundingRect())

        dx = 0.0
        dy = 0.0

        if combined.left() < canvas.left():
            dx = canvas.left() - combined.left()
        elif combined.right() > canvas.right():
            dx = canvas.right() - combined.right()

        if combined.top() < canvas.top():
            dy = canvas.top() - combined.top()
        elif combined.bottom() > canvas.bottom():
            dy = canvas.bottom() - combined.bottom()

        if dx != 0 or dy != 0:
            for item in items:
                item.moveBy(dx, dy)

    def _clamp_delta_to_canvas(
        self, items: list[QGraphicsItem], delta: QPointF
    ) -> QPointF:
        """Restrict a proposed movement delta so items stay inside the canvas.

        Background images are excluded from clamping.

        Args:
            items: The items that would be moved.
            delta: The proposed movement (dx, dy).

        Returns:
            A clamped delta that keeps all items within the canvas boundary.
        """
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        clampable = [i for i in items if not isinstance(i, BackgroundImageItem)]
        if not clampable:
            return delta

        canvas = self._canvas_scene.canvas_rect

        # Compute combined bounding rect of clampable items
        combined = clampable[0].sceneBoundingRect()
        for item in clampable[1:]:
            combined = combined.united(item.sceneBoundingRect())

        # Predict where the rect would end up
        moved = combined.translated(delta)

        dx = delta.x()
        dy = delta.y()

        if moved.left() < canvas.left():
            dx = canvas.left() - combined.left()
        elif moved.right() > canvas.right():
            dx = canvas.right() - combined.right()

        if moved.top() < canvas.top():
            dy = canvas.top() - combined.top()
        elif moved.bottom() > canvas.bottom():
            dy = canvas.bottom() - combined.bottom()

        return QPointF(dx, dy)

    def snap_point(self, point: QPointF) -> QPointF:
        """Snap a point to the grid if snap is enabled, and clamp to canvas.

        Args:
            point: Point in canvas coordinates

        Returns:
            Point snapped to grid (if enabled) and clamped to canvas borders
        """
        # Always clamp to canvas borders first
        clamped = self.clamp_to_canvas(point)

        if not self._snap_enabled:
            return clamped

        snapped = QPointF(
            round(clamped.x() / self._grid_size) * self._grid_size,
            round(clamped.y() / self._grid_size) * self._grid_size,
        )

        # Re-clamp after snapping (grid snap near border could push outside)
        return self.clamp_to_canvas(snapped)

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

        # Remember scene position under the mouse before zoom
        old_scene_pos = self.mapToScene(event.position().toPoint())

        # Apply immediate zoom: 1.15x per standard wheel notch (120 units)
        zoom_per_notch = 1.15
        notches = delta / 120.0
        factor = zoom_per_notch ** notches

        new_zoom = max(self.min_zoom, min(self.max_zoom, self._zoom_factor * factor))
        self._zoom_factor = new_zoom
        self._apply_transform()
        self.zoom_changed.emit(self.zoom_percent)

        # Scroll so the point under the mouse stays in the same screen position
        new_scene_pos = self.mapToScene(event.position().toPoint())
        scroll_delta = old_scene_pos - new_scene_pos
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + int(scroll_delta.x() * self._zoom_factor)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(scroll_delta.y() * self._zoom_factor)
        )

        event.accept()

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

        # Apply object snapping and canvas boundary clamping during drag
        self._apply_object_snap_during_drag()
        self._clamp_dragged_items_to_canvas()

    def _apply_object_snap_during_drag(self) -> None:
        """Apply object snapping to items being dragged.

        Called after super().mouseMoveEvent() has already moved items.
        Computes snap offsets and adjusts positions accordingly.
        Background images are excluded from snapping.
        """
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        if not self._object_snap_enabled or not self._drag_start_positions:
            self._snap_guides = []
            return

        selected = self.scene().selectedItems()
        if not selected:
            self._snap_guides = []
            return

        # Don't snap background images
        if all(isinstance(i, BackgroundImageItem) for i in selected):
            self._snap_guides = []
            return

        # Check that at least one item has actually moved (is being dragged)
        any_moved = False
        for item in selected:
            if item in self._drag_start_positions and item.pos() != self._drag_start_positions[item]:
                any_moved = True
                break

        if not any_moved:
            self._snap_guides = []
            return

        # Compute combined bounding rect of all selected items
        combined = selected[0].sceneBoundingRect()
        for item in selected[1:]:
            combined = combined.united(item.sceneBoundingRect())

        # Compute snap against other items (exclude background images as targets)
        exclude = set(selected)
        for scene_item in self.scene().items():
            if isinstance(scene_item, BackgroundImageItem):
                exclude.add(scene_item)
        snap_result = self._object_snapper.snap(
            combined,
            list(self.scene().items()),
            exclude=exclude,
            canvas_rect=self._canvas_scene.canvas_rect,
        )

        # Apply snap offset to all dragged items
        dx = snap_result.snapped_pos.x()
        dy = snap_result.snapped_pos.y()
        if dx != 0 or dy != 0:
            for item in selected:
                item.moveBy(dx, dy)

        # Store guides for rendering and trigger repaint
        self._snap_guides = snap_result.guides
        self.viewport().update()

    def _clamp_dragged_items_to_canvas(self) -> None:
        """Clamp items to canvas boundaries during mouse drag.

        Called after super().mouseMoveEvent() and object snapping.
        Only acts when a drag is in progress (drag_start_positions is populated).
        """
        if not self._drag_start_positions:
            return

        selected = self.scene().selectedItems()
        if not selected:
            return

        # Only clamp if items have actually moved
        any_moved = any(
            item in self._drag_start_positions and item.pos() != self._drag_start_positions[item]
            for item in selected
        )
        if not any_moved:
            return

        self._clamp_items_to_canvas(selected)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to stop panning and finish tool operations."""
        # Clear snap guides
        if self._snap_guides:
            self._snap_guides = []
            self.viewport().update()

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

        # Clamp delta to keep items inside the canvas
        delta = self._clamp_delta_to_canvas(selected, QPointF(dx, dy))
        if delta.x() == 0 and delta.y() == 0:
            return

        # Move with undo support
        command = MoveItemsCommand(selected, delta)
        self._command_manager.execute(command)

    def _finalize_drag_move(self) -> None:
        """Create undo command for mouse drag movement if items moved."""
        if not self._drag_start_positions:
            return

        # If a resize command was just pushed to the undo stack, the position
        # change is already captured by that command. Creating a separate
        # MoveItemsCommand would duplicate the position delta and cause
        # undo to only revert the position without restoring the size.
        from open_garden_planner.core.commands import ResizeItemCommand

        if self._command_manager.can_undo:
            last_cmd = self._command_manager._undo_stack[-1]
            if isinstance(last_cmd, ResizeItemCommand):
                self._drag_start_positions.clear()
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
        """Draw the foreground including canvas border, grid overlay, and snap guides."""
        super().drawForeground(painter, rect)

        # Draw canvas border
        self._draw_canvas_border(painter)

        # Draw grid overlay on top of everything
        if self._grid_visible:
            self._draw_grid(painter, rect)

        # Draw snap alignment guides
        if self._snap_guides:
            self._draw_snap_guides(painter, rect)

    def _draw_canvas_border(self, painter: QPainter) -> None:
        """Draw a border around the canvas area."""
        # Get the actual canvas rect (not the padded scene rect)
        canvas_rect = self._canvas_scene.canvas_rect

        # Set up pen for border
        border_pen = QPen(self._canvas_border_color)
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
        pen = QPen(self._grid_color)
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
        major_pen = QPen(self._grid_major_color)
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

    def _draw_snap_guides(self, painter: QPainter, rect: QRectF) -> None:
        """Draw snap alignment guide lines.

        Args:
            painter: QPainter in scene coordinates.
            rect: Current visible rect.
        """
        pen = QPen(self._snap_guide_color)
        pen.setWidth(0)  # Cosmetic (1px regardless of zoom)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for guide in self._snap_guides:
            # Clip guide to visible rect
            if guide.is_horizontal:
                painter.drawLine(
                    QPointF(rect.left(), guide.start.y()),
                    QPointF(rect.right(), guide.start.y()),
                )
            else:
                painter.drawLine(
                    QPointF(guide.start.x(), rect.top()),
                    QPointF(guide.start.x(), rect.bottom()),
                )

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the view, then draw overlays in viewport coordinates."""
        super().paintEvent(event)

        if self._scale_bar_visible:
            painter = QPainter(self.viewport())
            # Remove clip so the scale bar is always fully drawn,
            # even with MinimalViewportUpdate where only dirty
            # regions are repainted.
            painter.setClipping(False)
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

        # Draw outline pass (thicker, behind the foreground)
        outline_pen = QPen(self._scale_bar_outline)
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

        # Draw foreground pass
        fg_color = QColor(self._scale_bar_fg)
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
            self.set_status_message(self.tr("Copied {count} item(s)").format(count=len(self._clipboard)))

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
            self.set_status_message(self.tr("Cut {count} item(s)").format(count=len(self._clipboard)))

    def paste(self) -> None:
        """Paste items from clipboard."""
        if not self._clipboard:
            self.set_status_message(self.tr("Nothing to paste"))
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

            self.set_status_message(self.tr("Pasted {count} item(s)").format(count=len(pasted_items)))

    def duplicate_selected(self) -> None:
        """Duplicate selected items (copy and paste in one action)."""
        selected = self.scene().selectedItems()
        if not selected:
            self.set_status_message(self.tr("Nothing to duplicate"))
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

            self.set_status_message(self.tr("Duplicated {count} item(s)").format(count=len(duplicated_items)))

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
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
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
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
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
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
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
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
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
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
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
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
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
                if "rotation_angle" in obj:
                    item._apply_rotation(obj["rotation_angle"])
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
                if "rotation_angle" in obj:
                    item._apply_rotation(obj["rotation_angle"])
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
                self.set_status_message(self.tr("Distance must be positive"))
        except ValueError:
            self.set_status_message(self.tr("Invalid distance. Enter a number in centimeters."))

    def _clamp_individual_deltas(
        self, item_deltas: list[tuple[QGraphicsItem, QPointF]],
    ) -> list[tuple[QGraphicsItem, QPointF]]:
        """Clamp per-item deltas so each item stays inside the canvas.

        Args:
            item_deltas: List of (item, delta) tuples.

        Returns:
            Clamped list of (item, delta) tuples.
        """
        canvas = self._canvas_scene.canvas_rect
        result: list[tuple[QGraphicsItem, QPointF]] = []
        for item, delta in item_deltas:
            rect = item.sceneBoundingRect()
            moved = rect.translated(delta)
            dx = delta.x()
            dy = delta.y()
            if moved.left() < canvas.left():
                dx = canvas.left() - rect.left()
            elif moved.right() > canvas.right():
                dx = canvas.right() - rect.right()
            if moved.top() < canvas.top():
                dy = canvas.top() - rect.top()
            elif moved.bottom() > canvas.bottom():
                dy = canvas.bottom() - rect.bottom()
            result.append((item, QPointF(dx, dy)))
        return result

    def align_selected(self, mode: AlignMode) -> None:
        """Align selected items using the given mode.

        Args:
            mode: The alignment mode (LEFT, RIGHT, TOP, BOTTOM, CENTER_H, CENTER_V).
        """
        selected = self.scene().selectedItems()
        if len(selected) < 2:
            self.set_status_message(self.tr("Select at least 2 objects to align"))
            return

        deltas = align_items(selected, mode)
        deltas = self._clamp_individual_deltas(deltas)
        # Filter out zero-movement items
        non_zero = [(item, d) for item, d in deltas if d.x() != 0 or d.y() != 0]
        if not non_zero:
            return

        desc = f"Align {mode.name.lower().replace('_', ' ')}"
        command = AlignItemsCommand(non_zero, desc)
        self._command_manager.execute(command)
        self.set_status_message(desc.capitalize())

    def distribute_selected(self, mode: DistributeMode) -> None:
        """Distribute selected items using the given mode.

        Args:
            mode: The distribution mode (HORIZONTAL or VERTICAL).
        """
        selected = self.scene().selectedItems()
        if len(selected) < 3:
            self.set_status_message(self.tr("Select at least 3 objects to distribute"))
            return

        deltas = distribute_items(selected, mode)
        deltas = self._clamp_individual_deltas(deltas)
        non_zero = [(item, d) for item, d in deltas if d.x() != 0 or d.y() != 0]
        if not non_zero:
            return

        desc = f"Distribute {mode.name.lower()}"
        command = AlignItemsCommand(non_zero, desc)
        self._command_manager.execute(command)
        self.set_status_message(desc.capitalize())

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
