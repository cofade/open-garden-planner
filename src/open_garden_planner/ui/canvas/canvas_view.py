"""Canvas view for the garden planner.

The view handles rendering, pan, zoom, and coordinate transformation.
It flips the Y-axis to provide CAD-style coordinates (origin at bottom-left,
Y increasing upward).
"""
from __future__ import annotations

import contextlib
import json
import logging
from datetime import date
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from open_garden_planner.core.commands import Command
    from open_garden_planner.core.plant_renderer import PlantCategory
    from open_garden_planner.ui.canvas.items import CircleItem
    from open_garden_planner.ui.canvas.items.soil_badge_item import SoilBadgeItem

from PyQt6.QtCore import (
    QCoreApplication,
    QEvent,
    QObject,
    QPoint,
    QPointF,
    QRectF,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QContextMenuEvent,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QNativeGestureEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QTransform,
    QWheelEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QGestureEvent,
    QGraphicsItem,
    QGraphicsView,
    QInputDialog,
    QLineEdit,
    QMenu,
    QPinchGesture,
)

from open_garden_planner.core import (
    AddConstraintCommand,
    AlignItemsCommand,
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    MoveItemsCommand,
    RemoveConstraintCommand,
)
from open_garden_planner.core.alignment import (
    AlignMode,
    DistributeMode,
    align_items,
    distribute_items,
)
from open_garden_planner.core.coordinate_input import CoordinateInputBuffer
from open_garden_planner.core.object_types import (
    ObjectType,
    is_bed_type,
    is_plant_parent_type,
)
from open_garden_planner.core.snap import (
    PointSnapper,
    SnapCandidate,
    SnapCandidateKind,
    SnapRegistry,
)
from open_garden_planner.core.snap.providers import (
    CenterSnapProvider,
    EdgeCardinalSnapProvider,
    EndpointSnapProvider,
    IntersectionSnapProvider,
    MidpointSnapProvider,
    NearestSnapProvider,
    PerpendicularSnapProvider,
    TangentSnapProvider,
)
from open_garden_planner.core.snapping import ObjectSnapper, SnapGuide
from open_garden_planner.core.stacking import ArrangeMode, ArrangeOutcome
from open_garden_planner.core.tools import (
    AngleConstraintTool,
    ArcTool,
    BezierTool,
    CalloutTool,
    ChamferTool,
    CircleTool,
    CoincidentConstraintTool,
    ConstraintTool,
    ConstructionCircleTool,
    ConstructionLineTool,
    EdgeLengthConstraintTool,
    EllipseTool,
    EqualConstraintTool,
    FilletTool,
    FixedConstraintTool,
    HorizontalConstraintTool,
    HorizontalDistanceConstraintTool,
    JournalPinTool,
    MeasureTool,
    MirrorTool,
    OffsetTool,
    ParallelConstraintTool,
    PerpendicularConstraintTool,
    PolygonTool,
    PolylineTool,
    RectangleTool,
    SelectTool,
    SymmetryConstraintTool,
    TextTool,
    ToolManager,
    ToolType,
    TrimExtendTool,
    VerticalConstraintTool,
    VerticalDistanceConstraintTool,
)
from open_garden_planner.services.soil_service import (
    ALL_PARAMS,
    PARAM_OVERALL,
    HealthLevel,
    SoilService,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene, GuideLine
from open_garden_planner.ui.canvas.clipboard_operations import (
    ClipboardOperations,
)
from open_garden_planner.ui.canvas.clipboard_operations import (
    _offset_item_dict as _offset_item_dict,
)
from open_garden_planner.ui.canvas.clipboard_operations import (
    _strip_item_ids as _strip_item_ids,
)
from open_garden_planner.ui.canvas.drag_constraints import DragConstraints
from open_garden_planner.ui.canvas.items.resize_handle import (
    DRAG_HANDLE_TYPES,
    RotationHandle,
    VertexHandle,
)

_log = logging.getLogger(__name__)








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
    #: Emitted alongside tool_changed, carrying the ToolType rather than the
    #: (possibly translated) display name — see #304.
    tool_type_changed = pyqtSignal(ToolType)
    #: A one-line message for the main window's status bar.
    #:
    #: This is a SIGNAL, not a parent lookup, and that is the whole point. The
    #: previous implementation asked ``self.parent().statusBar()``, but in the
    #: production layout this view's parent is the ``QSplitter`` built in
    #: ``application.py`` — which has no ``statusBar`` — so the ``hasattr`` guard
    #: silently failed and EVERY ``set_status_message`` caller (two dozen, from
    #: canvas_scene's calibration feedback to garden_item's command descriptions)
    #: was a silent no-op. The #415 propagation-date refusal surfaced it: it
    #: appeared to be refused visibly and delivered nothing at all.
    status_message = pyqtSignal(str)
    import_background_image_requested = pyqtSignal()  # Emitted from empty-canvas right-click
    # US-12.10a: emitted when a bed's "Add soil test…" action is invoked.
    # Args: target_id (bed UUID string or "global"), display_name (informational)
    soil_test_requested = pyqtSignal(str, str)
    # US-12.10e: emitted when the seasonal reminder badge on a bed is clicked.
    # Args: bed_id (UUID string).
    soil_test_badge_clicked = pyqtSignal(str)
    # US-12.7: emitted when a bed/plant's "Log Pest/Disease…" action fires.
    # Args: target_id (UUID string), display_name (informational)
    pest_log_requested = pyqtSignal(str, str)
    # US-C1: emitted when a bed/plant's "Log Harvest…" action fires.
    # Args: target_id (UUID string), display_name (informational)
    harvest_log_requested = pyqtSignal(str, str)
    # US-12.8: emitted when a bed's "Plan Succession…" action fires.
    # Args: bed_id (UUID string), display_name (informational)
    succession_plan_requested = pyqtSignal(str, str)
    # US-12.9: emitted when the Journal Pin tool drops a new pin.
    # Args: scene_x, scene_y (canvas coords, cm).
    journal_note_requested = pyqtSignal(float, float)
    # US-12.9: emitted when an existing pin is double-clicked or the user picks
    # "Edit Note…" from its context menu. Args: note_id (string).
    journal_note_edit_requested = pyqtSignal(str)
    # US-12.9: emitted when an existing pin's "Delete" context-menu entry fires
    # (single pin, with confirmation dialog).
    journal_note_delete_requested = pyqtSignal(str)
    # US-12.9: emitted when one or more journal pins are part of a keyboard
    # Delete-key batch (no per-pin confirmation; matches Delete-key UX for
    # regular items and is undoable). Args: list[str] of note ids.
    journal_notes_batch_delete_requested = pyqtSignal(list)
    # US-12.9: emitted when the sidebar requests viewport centering on a pin.
    journal_note_focus_requested = pyqtSignal(str)

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
        self._drag_constraints = DragConstraints(self)
        self._clipboard_guild_members: dict[str, set[str]] = {}
        self._clipboard_operations = ClipboardOperations(self)

        self._canvas_scene = scene
        self._zoom_factor = 1.0
        self._grid_visible = False
        self._snap_enabled = True
        self._object_snap_enabled = True
        self._midpoint_snap_enabled = True
        self._intersection_snap_enabled = True
        # Phase 13 Package B (US-B4): nearest-point fallback snap, off by
        # default to preserve the existing free-placement-near-edges UX.
        self._nearest_snap_enabled = False
        # Phase 13 Package B (US-B5): perpendicular snap from tool's
        # last_point, off by default.
        self._perpendicular_snap_enabled = False
        # Phase 13 Package B (US-B6): tangent snap from tool's last_point
        # onto circles / arcs, off by default.
        self._tangent_snap_enabled = False
        self._dynamic_input_enabled = True
        self._grid_size = 50.0  # 50cm default grid
        self._scale_bar_visible = True
        # Touch gestures (#321): enabled by default, a sitting of the view; the app
        # applies the saved preference after construction, as for the scale bar.
        # ``_pinch_scale`` / ``_pinch_center`` carry the last values of Qt's own
        # pinch gesture (cumulative scale, viewport centre) while it is active.
        self._touch_gestures_enabled = True
        self._pinch_scale: float | None = None
        self._pinch_center: QPointF | None = None
        #: The press Qt synthesised from the first finger (viewport point, button),
        #: so a pinch that starts on an item can release it instead of dragging it.
        self._touch_mouse_press: tuple[QPointF, Qt.MouseButton] | None = None

        # Drag-time bounding-box snapping engine and visual guides
        self._object_snapper = ObjectSnapper(threshold=10.0)
        self._snap_guides: list[SnapGuide] = []
        self._snap_guide_color = QColor(255, 0, 128, 180)  # Magenta

        # Click-time point snapper (Package A US-A3): endpoint/center/edge
        # come from the legacy anchor system, midpoint/intersection are
        # new providers.  Provider activation tracks the View menu toggles.
        self._snap_registry = SnapRegistry(
            [
                EndpointSnapProvider(),
                IntersectionSnapProvider(),
                MidpointSnapProvider(),
                CenterSnapProvider(),
                EdgeCardinalSnapProvider(),
            ]
        )
        self._point_snapper = PointSnapper(self._snap_registry)
        self._current_snap: SnapCandidate | None = None
        self._snap_indicator_item = None  # QGraphicsItem placeholder
        self._snap_index_dirty = True
        scene.changed.connect(self._on_scene_changed_for_snap)

        # Shared typed-coordinate buffer (Package A US-A1/A2/A4).
        self._input_buffer = CoordinateInputBuffer(self)
        # Lazily-created cursor overlay (US-A4).
        self._dynamic_overlay: object | None = None

        # Pan state
        self._panning = False
        self._pan_start = QPointF()

        # Command manager for undo/redo
        self._command_manager = CommandManager(self)
        # the scene's plan revision moves with every executed / undone / redone command
        self._canvas_scene.set_command_manager(self._command_manager)

        # Update dimension lines after any command (constraint add/remove, item move, etc.)
        self._command_manager.command_executed.connect(
            lambda _desc: self._canvas_scene.update_dimension_lines()
        )
        # Also update after undo/redo (these don't emit command_executed)
        self._command_manager.can_undo_changed.connect(
            lambda _: self._canvas_scene.update_dimension_lines()
        )
        self._command_manager.can_redo_changed.connect(
            lambda _: self._canvas_scene.update_dimension_lines()
        )

        # Drag tracking for undo support
        self._drag_start_positions: dict[QGraphicsItem, QPointF] = {}
        # Constraint-propagated items' start positions during drag
        self._constraint_propagated_starts: dict[QGraphicsItem, QPointF] = {}
        # Child items moved during bed drag (original positions)
        self._child_drag_origins: dict[QGraphicsItem, QPointF] = {}
        # Active handle being dragged — used to re-grab if Qt silently drops it
        self._active_drag_handle: QGraphicsItem | None = None

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
        self._calibration_input.returnPressed.connect(
            self._on_calibration_input_entered
        )

        # Guide lines (drag from ruler to create; stored on the scene for persistence)
        self._guides_visible: bool = True
        self._guide_color: QColor = QColor(0, 100, 220, 160)  # Blue, semi-transparent
        self._guide_highlight_color: QColor = QColor(
            255, 120, 0, 200
        )  # Orange highlight
        # Guide dragging state: (guide, is_new_guide_not_yet_in_list)
        self._dragging_guide: GuideLine | None = None
        self._dragging_guide_is_new: bool = False
        self._hovered_guide: GuideLine | None = None  # guide under cursor

        # Theme colors for overlays (defaults; overridden by apply_theme_colors)
        self._grid_color = QColor(200, 200, 200, 100)
        self._grid_major_color = QColor(180, 180, 180, 150)
        self._canvas_border_color = QColor("#666666")
        self._scale_bar_fg = QColor(40, 40, 40)
        self._scale_bar_outline = QColor(255, 255, 255, 220)

        # Soil health overlay (US-12.10b) — view-level so it's excluded from
        # exports (PNG/SVG/PDF/print) which all go through scene.render().
        self._soil_overlay_visible: bool = False
        self._soil_overlay_param: str = PARAM_OVERALL
        self._soil_service: SoilService | None = None
        # US-12.10e: seasonal reminder badges, keyed by bed UUID.
        self._soil_badges: dict[str, SoilBadgeItem] = {}

        # Set up view properties
        self._setup_view()

    def _setup_tools(self) -> None:
        """Register and initialize drawing tools."""
        # Register basic tools
        self._tool_manager.register_tool(SelectTool(self))
        self._tool_manager.register_tool(MeasureTool(self))
        self._tool_manager.register_tool(ConstraintTool(self))
        self._tool_manager.register_tool(EdgeLengthConstraintTool(self))
        self._tool_manager.register_tool(HorizontalConstraintTool(self))
        self._tool_manager.register_tool(VerticalConstraintTool(self))
        self._tool_manager.register_tool(CoincidentConstraintTool(self))
        self._tool_manager.register_tool(EqualConstraintTool(self))
        self._tool_manager.register_tool(FixedConstraintTool(self))
        self._tool_manager.register_tool(HorizontalDistanceConstraintTool(self))
        self._tool_manager.register_tool(VerticalDistanceConstraintTool(self))
        self._tool_manager.register_tool(ParallelConstraintTool(self))
        self._tool_manager.register_tool(PerpendicularConstraintTool(self))
        self._tool_manager.register_tool(AngleConstraintTool(self))
        self._tool_manager.register_tool(SymmetryConstraintTool(self))

        # Register construction geometry tools
        self._tool_manager.register_tool(ConstructionLineTool(self))
        self._tool_manager.register_tool(ConstructionCircleTool(self))

        # Register CAD editing tools
        self._tool_manager.register_tool(TrimExtendTool(self))
        self._tool_manager.register_tool(OffsetTool(self))
        # Phase 13 Package B (US-B3): fillet & chamfer corner editors.
        self._tool_manager.register_tool(FilletTool(self))
        self._tool_manager.register_tool(ChamferTool(self))
        # Phase 13 Package B (US-B4): mirror selection across an axis.
        self._tool_manager.register_tool(MirrorTool(self))

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

        ellipse_tool = EllipseTool(self, object_type=ObjectType.GENERIC_ELLIPSE)
        ellipse_tool.shortcut = "E"
        self._tool_manager.register_tool(ellipse_tool)

        # Phase 13 Package B (US-B2): 3-point arc tool.
        arc_tool = ArcTool(self)
        self._tool_manager.register_tool(arc_tool)

        # Phase 13 Package B (US-B1): cubic Bezier pen tool.
        bezier_tool = BezierTool(self)
        self._tool_manager.register_tool(bezier_tool)

        text_tool = TextTool(self)
        self._tool_manager.register_tool(text_tool)

        callout_tool = CalloutTool(self)
        self._tool_manager.register_tool(callout_tool)

        journal_pin_tool = JournalPinTool(self)
        self._tool_manager.register_tool(journal_pin_tool)

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
        # Shortcut freed in Phase 13 B1 — "B" now maps to Bezier per the
        # CAD-tool convention (Inkscape / Illustrator / Figma). Garden
        # Bed remains accessible from the Beds & Surfaces gallery.
        garden_bed_tool.shortcut = ""
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

        # Register hedge polygon tool (polygon-based, tiled texture)
        hedge_tool = PolygonTool(self, object_type=ObjectType.HEDGE_POLYGON)
        hedge_tool.tool_type = ToolType.HEDGE_POLYGON
        hedge_tool.display_name = self.tr("Hedge")
        self._tool_manager.register_tool(hedge_tool)

        # Register outdoor furniture tools (rectangle-based, SVG-rendered)
        rect_furniture = [
            (
                ObjectType.TABLE_RECTANGULAR,
                ToolType.TABLE_RECTANGULAR,
                self.tr("Table (Rectangular)"),
            ),
            (ObjectType.CHAIR, ToolType.CHAIR, self.tr("Chair")),
            (ObjectType.BENCH, ToolType.BENCH, self.tr("Bench")),
            (ObjectType.LOUNGER, ToolType.LOUNGER, self.tr("Lounger")),
            (ObjectType.SANDBOX, ToolType.SANDBOX, self.tr("Sandbox")),
            (ObjectType.HOT_TUB, ToolType.HOT_TUB, self.tr("Hot Tub")),
            (ObjectType.SWING, ToolType.SWING, self.tr("Swing")),
            (ObjectType.PICNIC_TABLE, ToolType.PICNIC_TABLE, self.tr("Picnic Table")),
            (ObjectType.HAMMOCK, ToolType.HAMMOCK, self.tr("Hammock")),
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
            (ObjectType.TRAMPOLINE, ToolType.TRAMPOLINE, self.tr("Trampoline")),
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
            (ObjectType.WHEELBARROW, ToolType.WHEELBARROW, self.tr("Wheelbarrow")),
            (ObjectType.PERGOLA, ToolType.PERGOLA, self.tr("Pergola")),
        ]
        for obj_type, tool_type, display_name in rect_infrastructure:
            tool = RectangleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        circle_infrastructure = [
            (ObjectType.RAIN_BARREL, ToolType.RAIN_BARREL, self.tr("Rain Barrel")),
            (ObjectType.WATER_TAP, ToolType.WATER_TAP, self.tr("Water Tap")),
            (ObjectType.BIRD_BATH, ToolType.BIRD_BATH, self.tr("Bird Bath")),
        ]
        for obj_type, tool_type, display_name in circle_infrastructure:
            tool = CircleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        # Register vertical & container gardening tools (US-C3). Containers,
        # wall planters, and trellises are plain shape items tagged with their
        # ObjectType (same pattern as raised beds), so they ride the existing
        # RectangleTool / CircleTool.
        rect_containers = [
            (ObjectType.CONTAINER, ToolType.CONTAINER_RECT, self.tr("Container")),
            (ObjectType.WALL_PLANTER, ToolType.WALL_PLANTER, self.tr("Wall Planter")),
            (ObjectType.TRELLIS, ToolType.TRELLIS, self.tr("Trellis")),
        ]
        for obj_type, tool_type, display_name in rect_containers:
            tool = RectangleTool(self, object_type=obj_type)
            tool.tool_type = tool_type
            tool.display_name = display_name
            self._tool_manager.register_tool(tool)

        round_container = CircleTool(self, object_type=ObjectType.CONTAINER_ROUND)
        round_container.tool_type = ToolType.CONTAINER_ROUND
        round_container.display_name = self.tr("Round Container")
        self._tool_manager.register_tool(round_container)

        # Connect tool change signal
        self._tool_manager.tool_changed.connect(self.tool_changed.emit)
        self._tool_manager.tool_type_changed.connect(self.tool_type_changed.emit)

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
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate
        )

        # Accept drops from gallery panel
        self.setAcceptDrops(True)

        # Pinch-to-zoom and two-finger pan (#321): the viewport is the widget the
        # touch points land on, so it is where touch events are accepted and where
        # the gesture filter sits. Off means Qt keeps synthesising mouse events.
        self.set_touch_gestures_enabled(self._touch_gestures_enabled)

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
        self._refresh_dense_vertex_overlays()

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        """Keep a dense vertex-edit sample tied to the visible viewport pixels."""
        super().scrollContentsBy(dx, dy)
        self._refresh_dense_vertex_overlays()

    def _refresh_dense_vertex_overlays(self) -> None:
        """Ask every selected item with a bounded overlay to re-sample (#551)."""
        scene = self.scene()
        if scene is None:
            return
        for item in scene.selectedItems():
            refresh = getattr(item, "refresh_vertex_edit_overlay", None)
            if callable(refresh):
                refresh()

    # Properties

    # Ruler strip width/height in viewport pixels
    RULER_SIZE: int = 20

    @property
    def zoom_factor(self) -> float:
        """Current zoom factor (1.0 = 100%)."""
        return self._zoom_factor

    @property
    def zoom_percent(self) -> float:
        """Current zoom as percentage."""
        return self._zoom_factor * 100.0

    @property
    def guides_visible(self) -> bool:
        """Whether guide lines and rulers are visible."""
        return self._guides_visible

    def set_guides_visible(self, visible: bool) -> None:
        """Show or hide guide lines and rulers.

        Args:
            visible: Whether guides should be shown.
        """
        self._guides_visible = visible
        self.viewport().update()

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

    def request_soil_test(self, target_id: str, display_name: str = "") -> None:
        """Forward a soil-test request from a bed's context menu (US-12.10a).

        Emits ``soil_test_requested`` so the application (which owns the
        ``ProjectManager``) can open ``SoilTestDialog`` and execute the
        resulting ``AddSoilTestCommand``.
        """
        self.soil_test_requested.emit(target_id, display_name or "")

    def request_pest_log(self, target_id: str, display_name: str = "") -> None:
        """Forward a pest/disease-log request from an item's context menu (US-12.7)."""
        self.pest_log_requested.emit(target_id, display_name or "")

    def request_harvest_log(self, target_id: str, display_name: str = "") -> None:
        """Forward a harvest-log request from an item's context menu (US-C1)."""
        self.harvest_log_requested.emit(target_id, display_name or "")

    def request_succession_plan(self, bed_id: str, display_name: str = "") -> None:
        """Forward a succession-plan request from a bed's context menu (US-12.8)."""
        self.succession_plan_requested.emit(bed_id, display_name or "")

    def request_journal_note(self, scene_x: float, scene_y: float) -> None:
        """Forward a new-journal-note request from :class:`JournalPinTool` (US-12.9)."""
        self.journal_note_requested.emit(float(scene_x), float(scene_y))

    def request_journal_note_edit(self, note_id: str) -> None:
        """Forward an edit request for an existing pin's note (US-12.9)."""
        self.journal_note_edit_requested.emit(str(note_id))

    def request_journal_note_delete(self, note_id: str) -> None:
        """Forward a delete request for an existing pin's note (US-12.9)."""
        self.journal_note_delete_requested.emit(str(note_id))

    def focus_on_journal_pin(self, note_id: str) -> None:
        """Center the viewport on the pin matching ``note_id`` (US-12.9)."""
        from open_garden_planner.ui.canvas.items.journal_pin_item import (
            JournalPinItem,
        )

        scene = self.scene()
        if scene is None:
            return
        for item in scene.items():
            if isinstance(item, JournalPinItem) and item.note_id == note_id:
                self.centerOn(item.pos())
                scene.clearSelection()
                item.setSelected(True)
                return

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
        # Refresh the typed-input anchor (Package A US-A1/A2): previous
        # tool's last_point is stale when switching tools.
        self.refresh_input_anchor()
        # Clear any pending typed input from the previous tool.
        self._input_buffer.clear()

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

    def _zoom_at(self, anchor: QPointF, factor: float) -> None:
        """Zoom by ``factor``, keeping the scene point under ``anchor`` fixed.

        THE one anchored-zoom path: the mouse wheel and the pinch gesture both
        call it, so anchoring, clamping and the ``zoom_changed`` signal stay
        identical (issue #321). ``anchor`` is in viewport pixels.

        The body is the wheel's, with two differences stated here: a zoom that a
        limit did not change returns early (nothing to re-apply or re-emit), and
        the scrollbar compensation rounds rather than truncates its integer step.
        """
        new_zoom = max(self.min_zoom, min(self.max_zoom, self._zoom_factor * factor))
        if new_zoom == self._zoom_factor:
            return
        old_scene_pos = self.mapToScene(anchor.toPoint())
        self._zoom_factor = new_zoom
        self._apply_transform()
        self.zoom_changed.emit(self.zoom_percent)
        # Scroll so the point under the anchor stays in the same screen position.
        new_scene_pos = self.mapToScene(anchor.toPoint())
        scroll_delta = old_scene_pos - new_scene_pos
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value()
            + round(scroll_delta.x() * self._zoom_factor)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value()
            - round(scroll_delta.y() * self._zoom_factor)
        )

    def _pan_by(self, delta: QPointF) -> None:
        """Scroll the plan by a drag of ``delta`` viewport pixels.

        THE one pan path: the middle mouse button and the two-finger gesture both
        call it, so scrollbars (and the minimap that listens to them) move alike
        (issue #321). Map two points to scene so any transform — zoom, Y-flip —
        is handled, and move opposite the finger.
        """
        center = self.viewport().rect().center()
        scene_before = self.mapToScene(center)
        scene_after = self.mapToScene(
            QPoint(round(center.x() + delta.x()), round(center.y() + delta.y()))
        )
        scene_delta = scene_before - scene_after
        self.centerOn(self.mapToScene(center) + scene_delta)

    # Touch gestures (issue #321)

    def set_touch_gestures_enabled(self, enabled: bool) -> None:
        """Accept pinch-to-zoom and two-finger pan on the canvas viewport.

        Qt's **own pinch recognizer** does the arbitration a hand-written state
        machine gets wrong: it starts only when a second finger arrives, so a
        single-finger tap or drag is never claimed and keeps arriving as a
        synthesised mouse event — the tools' own path. With the preference off
        nothing is grabbed and the viewport is exactly as it was before #321.
        """
        self._touch_gestures_enabled = enabled
        viewport = self.viewport()
        if enabled:
            viewport.grabGesture(Qt.GestureType.PinchGesture)
            viewport.installEventFilter(self)
        else:
            viewport.ungrabGesture(Qt.GestureType.PinchGesture)
            viewport.removeEventFilter(self)
            self._end_pinch()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """Route pinch gestures and native trackpad gestures to the handlers."""
        if watched is self.viewport() and self._touch_gestures_enabled:
            kind = event.type()
            if kind == QEvent.Type.MouseButtonPress:
                # The first finger of a pinch is Qt's synthesised mouse press; remember
                # where it landed so the pinch can release it instead of dragging.
                mouse = cast(QMouseEvent, event)
                self._touch_mouse_press = (mouse.position(), mouse.button())
                return False
            if kind == QEvent.Type.MouseButtonRelease:
                self._touch_mouse_press = None
                return False
            if kind == QEvent.Type.Gesture:
                return self._gesture(cast(QGestureEvent, event))
            if kind == QEvent.Type.NativeGesture:
                return self._native_gesture(cast(QNativeGestureEvent, event))
        return super().eventFilter(watched, event)

    def _gesture(self, event: QGestureEvent) -> bool:
        """Apply an active pinch: pan by the fingers' movement, then zoom about them.

        ``totalScaleFactor`` is cumulative over the gesture, so the factor applied
        per step is the ratio to the last one; the fingers' centre moves with a
        plain two-finger drag, which is the pan. Pan first (the content follows
        the fingers), then zoom about their new centre — the other order leaves
        a ``(1 - ratio) * delta`` drift on a pinch that also moves.

        Qt reports the centre in **global** coordinates (its recognizer averages
        ``globalPosition``), so it is mapped to the viewport here, once, before
        anything treats it as a viewport point.
        """
        handled = False
        for gesture in event.gestures():
            if gesture.gestureType() != Qt.GestureType.PinchGesture:
                continue
            pinch = cast(QPinchGesture, gesture)
            state = pinch.state()
            if state == Qt.GestureState.GestureStarted:
                # A pinch must not drag what the first finger touched: release the
                # press Qt synthesised for it, at the point it was made.
                self._cancel_touch_press()
                self._pinch_scale = pinch.totalScaleFactor()
                self._pinch_center = self._viewport_point(pinch)
            elif state in (
                Qt.GestureState.GestureFinished,
                Qt.GestureState.GestureCanceled,
            ):
                self._end_pinch()
            else:
                self._apply_pinch(pinch)
            event.accept(pinch)
            handled = True
        return handled

    def _apply_pinch(self, pinch: QPinchGesture) -> None:
        """One update of an active pinch (or the first one seen after enabling)."""
        center = self._viewport_point(pinch)
        total = pinch.totalScaleFactor()
        if self._pinch_scale is None or self._pinch_center is None:
            # Enabled while the fingers were already down: adopt them, move nothing.
            self._pinch_scale, self._pinch_center = total, center
            return
        delta = center - self._pinch_center
        if not delta.isNull():
            self._pan_by(delta)
        if self._pinch_scale > 0.0 and total > 0.0:
            factor = total / self._pinch_scale
            if factor != 1.0:
                self._zoom_at(center, factor)
            self._pinch_scale = total
        self._pinch_center = center

    def _viewport_point(self, pinch: QPinchGesture) -> QPointF:
        """The gesture's centre in viewport pixels (Qt reports it in global ones)."""
        return QPointF(self.viewport().mapFromGlobal(pinch.centerPoint().toPoint()))

    def _cancel_touch_press(self) -> None:
        """Release the synthesised press of the first finger, at its own press point.

        Qt synthesises a mouse press for the first touch point before a second
        finger can start a pinch. Without this the whole pinch drags (or draws
        with) whatever the first finger landed on; releasing at the press point
        ends that interaction where it began, so the pinch only zooms and pans
        (it may still select the item under the first finger, like a tap).
        """
        press = self._touch_mouse_press
        self._touch_mouse_press = None
        if press is None:
            return
        # A drawing tool's half-made shape is discarded through its own Escape path;
        # a select-tool box likewise. (An item drag is ended by the release below.)
        tool = self._tool_manager.active_tool
        if tool is not None:
            tool.cancel()
        position, button = press
        if button == Qt.MouseButton.NoButton:
            return
        QApplication.sendEvent(
            self.viewport(),
            QMouseEvent(
                QEvent.Type.MouseButtonRelease,
                position,
                QPointF(self.viewport().mapToGlobal(position.toPoint())),
                button,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    def _end_pinch(self) -> None:
        """Forget the active pinch's last values (finished, cancelled or disabled)."""
        self._pinch_scale = None
        self._pinch_center = None
        self._touch_mouse_press = None

    def _native_gesture(self, event: QNativeGestureEvent) -> bool:
        """A trackpad pinch arrives as Qt's native zoom gesture, not as touch."""
        if event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
            factor = 1.0 + event.value()
            if factor > 0.0:
                self._zoom_at(event.position(), factor)
            event.accept()
            return True
        return False

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

    # Soil health overlay (US-12.10b)

    @property
    def soil_overlay_visible(self) -> bool:
        """Whether the soil-health canvas overlay is on."""
        return self._soil_overlay_visible

    @property
    def soil_overlay_param(self) -> str:
        """Current overlay parameter (one of :data:`ALL_PARAMS`)."""
        return self._soil_overlay_param

    def set_soil_service(self, service: SoilService | None) -> None:
        """Inject the long-lived ``SoilService`` used by the overlay.

        The overlay is a no-op until a service is supplied; the application
        wires this once after constructing both objects.
        """
        self._soil_service = service
        if not hasattr(self, "_soil_mismatch_timer"):
            self._soil_mismatch_timer = QTimer(self)
            self._soil_mismatch_timer.setSingleShot(True)
            self._soil_mismatch_timer.setInterval(500)
            self._soil_mismatch_timer.timeout.connect(self._on_soil_debounce_tick)
            if self._canvas_scene is not None:
                self._canvas_scene.changed.connect(self._on_scene_changed_for_soil)
        if self._soil_overlay_visible:
            self.viewport().update()
        self._update_soil_mismatches()
        self._update_soil_badges()

    def refresh_soil_mismatches(self) -> None:
        """Force an immediate mismatch recompute (call after a soil test is saved)."""
        self._update_soil_mismatches()

    def refresh_soil_badges(self) -> None:
        """Force an immediate overdue-badge recompute (call after a soil test is saved)."""
        self._update_soil_badges()

    def _on_scene_changed_for_soil(self, _rects: object = None) -> None:
        """Restart the soil-mismatch debounce on any scene change.

        Guarded against the C++ ``QTimer`` having been torn down already: during
        widget/app teardown the scene can still emit ``changed`` after the view's
        timer is deleted, and an unguarded access raises ``RuntimeError`` inside a
        Qt slot — which aborts the interpreter. (Was a bare lambda before.)
        """
        with contextlib.suppress(RuntimeError):
            self._soil_mismatch_timer.start()

    def _on_soil_debounce_tick(self) -> None:
        """Run by the 500 ms debounce timer; refreshes mismatch borders + badges."""
        self._update_soil_mismatches()
        self._update_soil_badges()

    def _update_soil_mismatches(self) -> None:
        """Recompute plant-soil mismatches for every bed and update their borders."""
        if self._soil_service is None or self._canvas_scene is None:
            return
        from open_garden_planner.core.object_types import is_bed_type
        from open_garden_planner.models.plant_data import PlantSpeciesData
        from open_garden_planner.services.soil_service import SoilService
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        all_items = list(self._canvas_scene.items())
        for item in all_items:
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            bed_id = str(getattr(item, "item_id", ""))
            record = self._soil_service.get_effective_record(bed_id)
            child_ids = {str(c) for c in getattr(item, "_child_item_ids", [])}
            specs: list[PlantSpeciesData] = []
            for child in all_items:
                if not self._canvas_scene.is_present(child):
                    continue
                if str(getattr(child, "item_id", "")) not in child_ids:
                    continue
                ps_dict = getattr(child, "metadata", {}).get("plant_species")
                if ps_dict and isinstance(ps_dict, dict):
                    with contextlib.suppress(Exception):
                        specs.append(PlantSpeciesData.from_dict(ps_dict))
            mismatches = SoilService.get_mismatched_plants(record, specs)
            total_reasons = sum(len(reasons) for _, reasons in mismatches)
            level: str | None = None
            if total_reasons == 1:
                level = "warning"
            elif total_reasons >= 2:
                level = "critical"
            if mismatches:
                tip_lines = [r for _, reasons in mismatches for r in reasons]
                new_tooltip = "\n".join(tip_lines)
            else:
                new_tooltip = ""

            # Idempotent: this method is called unconditionally every
            # soil-debounce tick (~500 ms). An unconditional update() makes
            # the scene emit `changed`, which restarts the same debounce
            # timer that called us — a self-sustaining idle loop (issue
            # #305; measured: one never-selected bed = 16 `changed`/4 s
            # forever). Only touch the item when something the user could
            # observe actually changed. (setToolTip alone does not emit
            # `changed` — measured — but is guarded for the same invariant.)
            prev_level = getattr(item, "_soil_mismatch_level", None)
            item._soil_mismatch_level = level
            if item.toolTip() != new_tooltip:
                item.setToolTip(new_tooltip)
            if level != prev_level:
                item.update()

    def _update_soil_badges(self, today: date | None = None) -> None:
        """Recompute seasonal-reminder badges for every bed (US-12.10e)."""
        if self._soil_service is None or self._canvas_scene is None:
            return
        from open_garden_planner.ui.canvas.items.soil_badge_item import SoilBadgeItem

        eval_date = today if today is not None else date.today()
        present_bed_ids: set[str] = set()

        for item in list(self._canvas_scene.items()):
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            bed_id = str(getattr(item, "item_id", ""))
            if not bed_id:
                continue
            present_bed_ids.add(bed_id)

            history = self._soil_service.get_history(bed_id)
            overdue = SoilService.is_test_overdue(history, eval_date)
            existing = self._soil_badges.get(bed_id)

            if overdue and existing is None:
                badge = SoilBadgeItem(item, bed_id)
                badge.clicked.connect(self.soil_test_badge_clicked.emit)
                self._canvas_scene.addItem(badge)
                badge.update_position()
                self._soil_badges[bed_id] = badge
            elif overdue and existing is not None:
                existing.update_position()
            elif not overdue and existing is not None:
                self._canvas_scene.removeItem(existing)
                self._soil_badges.pop(bed_id, None)

        # Garbage-collect badges for beds no longer in the scene.
        for stale_id in [bid for bid in self._soil_badges if bid not in present_bed_ids]:
            badge = self._soil_badges.pop(stale_id)
            with contextlib.suppress(Exception):
                self._canvas_scene.removeItem(badge)

    def set_soil_overlay_visible(self, visible: bool) -> None:
        """Show or hide the soil-health overlay."""
        if self._soil_overlay_visible == visible:
            return
        self._soil_overlay_visible = visible
        self.viewport().update()

    def set_soil_overlay_param(self, parameter: str) -> None:
        """Set the parameter the overlay colours by (one of :data:`ALL_PARAMS`)."""
        if parameter not in ALL_PARAMS:
            return
        if self._soil_overlay_param == parameter:
            return
        self._soil_overlay_param = parameter
        if self._soil_overlay_visible:
            self.viewport().update()

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
        self._refresh_snap_registry()

    def set_midpoint_snap_enabled(self, enabled: bool) -> None:
        """Set midpoint snap (Package A US-A3) enabled."""
        self._midpoint_snap_enabled = enabled
        self._refresh_snap_registry()

    def set_intersection_snap_enabled(self, enabled: bool) -> None:
        """Set intersection snap (Package A US-A3) enabled."""
        self._intersection_snap_enabled = enabled
        self._refresh_snap_registry()

    def set_nearest_snap_enabled(self, enabled: bool) -> None:
        """Set nearest-point fallback snap (Package B US-B4) enabled."""
        self._nearest_snap_enabled = enabled
        self._refresh_snap_registry()

    def set_perpendicular_snap_enabled(self, enabled: bool) -> None:
        """Set perpendicular snap (Package B US-B5) enabled."""
        self._perpendicular_snap_enabled = enabled
        self._refresh_snap_registry()

    def set_tangent_snap_enabled(self, enabled: bool) -> None:
        """Set tangent snap (Package B US-B6) enabled."""
        self._tangent_snap_enabled = enabled
        self._refresh_snap_registry()

    def set_dynamic_input_enabled(self, enabled: bool) -> None:
        """Set dynamic input (Package A US-A4) enabled."""
        self._dynamic_input_enabled = enabled
        if not enabled and self._dynamic_overlay is not None:
            self._dynamic_overlay.hide_overlay()

    def _ensure_dynamic_overlay(self) -> object:
        """Create the cursor overlay on first use."""
        if self._dynamic_overlay is None:
            from open_garden_planner.ui.widgets.dynamic_input_overlay import (
                DynamicInputOverlay,
            )

            self._dynamic_overlay = DynamicInputOverlay(self, self._input_buffer)
            self._dynamic_overlay.commit_requested.connect(self.commit_typed_coordinate)
        return self._dynamic_overlay

    def _update_dynamic_overlay(self, viewport_pos: object) -> None:
        """Show or hide the Dynamic Input overlay based on context."""
        if not self._dynamic_input_enabled:
            if self._dynamic_overlay is not None:
                self._dynamic_overlay.hide_overlay()
            return
        tool = self._tool_manager.active_tool
        if tool is None or getattr(tool, "tool_type", None) == ToolType.SELECT:
            if self._dynamic_overlay is not None:
                self._dynamic_overlay.hide_overlay()
            return
        if not getattr(tool, "accepts_typed_coordinates", True):
            # Tools whose next click is a geometric pick (3-point arc,
            # etc.) opt out so users don't see a misleading Dist/Angle
            # prompt.
            if self._dynamic_overlay is not None:
                self._dynamic_overlay.hide_overlay()
            return
        if getattr(tool, "last_point", None) is None:
            # Hide until the first click anchors the polar input.
            if self._dynamic_overlay is not None:
                self._dynamic_overlay.hide_overlay()
            return
        overlay = self._ensure_dynamic_overlay()
        # Freeze the overlay in place once the user starts typing — otherwise
        # ``show_near`` on every mouseMove slides it ahead of the cursor and
        # the user can never reach (or finish typing in) the fields.
        if overlay.is_capturing_input() and overlay.isVisible():
            return
        overlay.show_near(viewport_pos)

    @property
    def dynamic_input_enabled(self) -> bool:
        return self._dynamic_input_enabled

    @staticmethod
    def _is_coord_input_char(text: str) -> bool:
        """Bare characters that should route into the Dynamic Input overlay.

        Covers every character the coordinate parser understands: digits,
        decimal/separator marks, polar/relative prefixes, sign, and space.
        """
        if not text or len(text) != 1:
            return False
        return text in "0123456789.,;@<-+ "

    def forward_synthetic_key(self, key: Qt.Key) -> bool:
        """Forward a synthetic ``QKeyEvent(KeyPress, key)`` to the active tool.

        Public surface so the Dynamic Input overlay can ask the active tool
        to handle Enter (empty-buffer finalize) without reaching into
        ``_tool_manager`` directly.  Returns the tool's ``key_press`` result
        (True iff the event was handled).  Anchor is refreshed on success.

        Caveat: this bypasses ``QApplication.sendEvent``.  Tools that inspect
        event metadata (``event.timestamp()``, ``event.spontaneous()``, or
        the current ``QApplication.focusWidget()`` at delivery time) will
        see a stripped event.  Today's tools only read ``event.key()`` so
        the synthetic path is equivalent; revisit if a future tool needs
        more than that.
        """
        tool = self._tool_manager.active_tool
        if tool is None:
            return False
        event = QKeyEvent(
            QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier
        )
        handled = bool(tool.key_press(event))
        if handled:
            self.refresh_input_anchor()
        return handled

    @property
    def point_snapper(self) -> PointSnapper:
        """The shared click-time point snapper (Package A US-A3)."""
        return self._point_snapper

    def _refresh_snap_registry(self) -> None:
        """Sync provider activation with the four user-toggles."""
        reg = self._snap_registry
        if self._object_snap_enabled and not reg.has(EndpointSnapProvider):
            reg.add(EndpointSnapProvider())
            reg.add(CenterSnapProvider())
            reg.add(EdgeCardinalSnapProvider())
        elif not self._object_snap_enabled and reg.has(EndpointSnapProvider):
            reg.remove(EndpointSnapProvider)
            reg.remove(CenterSnapProvider)
            reg.remove(EdgeCardinalSnapProvider)
        if self._midpoint_snap_enabled and not reg.has(MidpointSnapProvider):
            reg.add(MidpointSnapProvider())
        elif not self._midpoint_snap_enabled and reg.has(MidpointSnapProvider):
            reg.remove(MidpointSnapProvider)
        if self._intersection_snap_enabled and not reg.has(IntersectionSnapProvider):
            reg.add(IntersectionSnapProvider())
        elif (
            not self._intersection_snap_enabled
            and reg.has(IntersectionSnapProvider)
        ):
            reg.remove(IntersectionSnapProvider)
        if self._nearest_snap_enabled and not reg.has(NearestSnapProvider):
            reg.add(NearestSnapProvider())
        elif not self._nearest_snap_enabled and reg.has(NearestSnapProvider):
            reg.remove(NearestSnapProvider)
        if (
            self._perpendicular_snap_enabled
            and not reg.has(PerpendicularSnapProvider)
        ):
            reg.add(PerpendicularSnapProvider())
        elif (
            not self._perpendicular_snap_enabled
            and reg.has(PerpendicularSnapProvider)
        ):
            reg.remove(PerpendicularSnapProvider)
        if self._tangent_snap_enabled and not reg.has(TangentSnapProvider):
            reg.add(TangentSnapProvider())
        elif not self._tangent_snap_enabled and reg.has(TangentSnapProvider):
            reg.remove(TangentSnapProvider)

    def set_grid_size(self, size: float) -> None:
        """Set grid size in centimeters."""
        self._grid_size = size
        if self._grid_visible:
            self.viewport().update()

    def set_scale_bar_visible(self, visible: bool) -> None:
        """Set scale bar visibility."""
        self._scale_bar_visible = visible
        self.viewport().update()

    def set_constraints_visible(self, visible: bool) -> None:
        """Set constraint dimension line visibility."""
        self._canvas_scene.set_constraints_visible(visible)

    def update_dimension_lines(self) -> None:
        """Trigger a rebuild of all constraint dimension lines."""
        self._canvas_scene.update_dimension_lines()

    def apply_constraint_solver(self) -> None:
        """Run the constraint solver and move items to satisfy all constraints.

        Call this after adding a new constraint (or changing target distances)
        so objects immediately snap to the required positions.  The resulting
        item moves are NOT recorded on the undo stack; they are folded into
        the subsequent drag or treated as the "initial state" for the newly
        created constraint.
        """
        moves, vertex_moves = self._compute_constraint_solve_moves()
        for item, _old, new in moves:
            item.setPos(new)
        for item, idx, _old_local, new_local in vertex_moves:
            if hasattr(item, "_move_vertex_to"):
                item._move_vertex_to(idx, new_local)
        if moves or vertex_moves:
            self._canvas_scene.update_dimension_lines()

    def _execute_constraint_with_solve(
        self, command: AddConstraintCommand, *, conflicts_checked: bool = False
    ) -> None:
        """Execute a constraint command with solver moves bundled in one undo step.

        Temporarily adds the constraint, computes what the solver would do,
        removes it again, stores the moves on the command, then executes the
        command through the command manager so the full operation (constraint
        addition + position changes) is a single Ctrl+Z step.
        """
        from open_garden_planner.core.constraints import ConstraintType as _CT

        # PARALLEL / PERPENDICULAR / EQUAL are rotation-only: the solver skips them.
        # Bundling solver moves from OTHER constraints would shift polygon vertices and
        # make the freshly applied rotation appear violated. Execute cleanly instead.
        _rotation_only = (_CT.PARALLEL, _CT.PERPENDICULAR, _CT.EQUAL)
        if command._constraint_type in _rotation_only:
            self.command_manager.execute(command)
            self._canvas_scene.update_dimension_lines()
            return

        # Pre-flight feasibility: if this constraint would force the solver to
        # violate an existing one, offer the user an Override/Cancel dialog.
        # Size tools may validate against a synchronous proposed-geometry probe.
        # Its snapshot is restored before this method can enter a modal loop.
        if not conflicts_checked and not self._resolve_constraint_conflicts(command):
            return

        # CAD convention: A is constrained to B → A moves, B stays (reference).
        # Exception: if A already has a FIXED constraint the FIXED pre-pass
        # inside solve_anchored will pin A, so B must remain free to move.
        graph = self._canvas_scene.constraint_graph
        anchor_a_id = command._anchor_a.item_id
        anchor_b_id = command._anchor_b.item_id
        a_is_fixed = any(
            c.constraint_type == _CT.FIXED and c.anchor_a.item_id == anchor_a_id
            for c in graph.constraints.values()
        )
        # Intra-object constraints (e.g. ANGLE on a polygon vertex) have both
        # anchors on the same item.  Pinning B would pin the item itself and
        # prevent the solver from deforming any of its vertices.
        intra_object = anchor_a_id == anchor_b_id
        extra_pinned: set | None = None if (a_is_fixed or intra_object) else {anchor_b_id}

        # 1. Add the constraint temporarily so the solver can compute moves.
        command.execute()
        if command._constraint_type == _CT.EDGE_LENGTH:
            moves, vertex_moves = self._compute_edge_length_constraint_moves(command)
        else:
            moves, vertex_moves = self._compute_constraint_solve_moves(
                extra_pinned=extra_pinned
            )
        # 2. Remove temporarily — we want the official execute() below to do it.
        command.undo()
        # 3. Embed the moves into the command so execute() + undo() handle them.
        command._item_moves = moves
        command._vertex_moves = vertex_moves
        # 4. Execute via command_manager (adds constraint + applies moves; one undo unit).
        self.command_manager.execute(command)
        if moves or vertex_moves:
            self._canvas_scene.update_dimension_lines()

    def _resolve_constraint_conflicts(
        self, command: AddConstraintCommand, *, allow_override: bool = True
    ) -> bool:
        """Return True if ``command`` can proceed, False if the user cancelled.

        Runs a trial solve with the proposed constraint.  If existing
        constraints would be forced out of tolerance, shows a dialog letting
        the user delete conflicting constraints (Override) or back out.
        """
        import uuid as _uuid

        from open_garden_planner.core.constraints import (
            Constraint,
            ConstraintType,
        )
        from open_garden_planner.core.measure_snapper import (
            get_anchor_points,
        )
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )
        from open_garden_planner.ui.dialogs.constraint_conflict_dialog import (
            ConstraintConflictDialog,
        )

        graph = self._canvas_scene.constraint_graph
        if not graph.constraints:
            return True

        trial = Constraint(
            constraint_id=_uuid.uuid4(),
            anchor_a=command._anchor_a,
            anchor_b=command._anchor_b,
            target_distance=command._target_distance,
            constraint_type=command._constraint_type,
            anchor_c=command._anchor_c,
            target_x=command._target_x,
            target_y=command._target_y,
        )

        item_positions: dict = {}
        item_map: dict = {}
        anchor_offsets: dict = {}
        for item in self.scene().items():
            is_garden = isinstance(item, GardenItemMixin)
            is_construction = isinstance(
                item, (ConstructionLineItem, ConstructionCircleItem)
            )
            if not (is_garden or is_construction):
                continue
            uid = item.item_id
            item_map[uid] = item
            pos = item.pos()
            item_positions[uid] = (pos.x(), pos.y())
            for anchor in get_anchor_points(item):
                anchor_offsets[(uid, anchor.anchor_type, anchor.anchor_index)] = (
                    anchor.point.x() - pos.x(),
                    anchor.point.y() - pos.y(),
                )

        deformable_items, deformable_vertices = self._gather_deformable_info(item_map)

        try:
            conflict_ids = graph.find_conflicting_constraints(
                trial_constraint=trial,
                item_positions=item_positions,
                anchor_offsets=anchor_offsets,
                deformable_items=deformable_items,
                deformable_vertices=deformable_vertices,
                tolerance=1.0,
            )
        except Exception:
            return allow_override  # A non-interactive size probe fails closed.

        if not conflict_ids:
            return True

        if not allow_override:
            return False

        type_names: dict = {
            ConstraintType.DISTANCE: self.tr("Distance"),
            ConstraintType.EDGE_LENGTH: self.tr("Edge length"),
            ConstraintType.HORIZONTAL: self.tr("Horizontal"),
            ConstraintType.VERTICAL: self.tr("Vertical"),
            ConstraintType.HORIZONTAL_DISTANCE: self.tr("Horizontal distance"),
            ConstraintType.VERTICAL_DISTANCE: self.tr("Vertical distance"),
            ConstraintType.ANGLE: self.tr("Angle"),
            ConstraintType.PARALLEL: self.tr("Parallel"),
            ConstraintType.PERPENDICULAR: self.tr("Perpendicular"),
            ConstraintType.EQUAL: self.tr("Equal"),
            ConstraintType.FIXED: self.tr("Fixed"),
            ConstraintType.COINCIDENT: self.tr("Coincident"),
            ConstraintType.SYMMETRY_HORIZONTAL: self.tr("Horizontal symmetry"),
            ConstraintType.SYMMETRY_VERTICAL: self.tr("Vertical symmetry"),
            ConstraintType.POINT_ON_EDGE: self.tr("Point on edge"),
            ConstraintType.POINT_ON_CIRCLE: self.tr("Point on circle"),
            ConstraintType.TANGENT: self.tr("Tangent"),
        }
        rows: list[tuple] = []
        for cid in conflict_ids:
            c = graph.constraints.get(cid)
            if c is None:
                continue
            name = type_names.get(c.constraint_type, str(c.constraint_type.name))
            if c.constraint_type in (
                ConstraintType.EDGE_LENGTH,
                ConstraintType.DISTANCE,
                ConstraintType.HORIZONTAL_DISTANCE,
                ConstraintType.VERTICAL_DISTANCE,
                ConstraintType.POINT_ON_CIRCLE,
                ConstraintType.TANGENT,
            ):
                # abs() is defensive; TANGENT's target is the (non-negative) radius.
                rows.append((cid, f"{name} — {abs(c.target_distance) / 100.0:.2f} m"))
            elif c.constraint_type == ConstraintType.ANGLE:
                rows.append((cid, f"{name} — {c.target_distance:.1f}°"))
            else:
                rows.append((cid, name))

        selected = ConstraintConflictDialog.ask(rows, parent=self)
        if selected is None:
            return False  # User cancelled
        for cid in selected:
            graph.remove_constraint(cid)
        self._canvas_scene.update_dimension_lines()
        return True

    def is_constraint_feasible(
        self,
        anchor_a: object,
        anchor_b: object,
        target_distance: float,
        constraint_type: object,
        anchor_c: object = None,
    ) -> bool:
        """Test whether adding a constraint would conflict with existing constraints.

        Builds the current item positions and anchor offsets from the scene, then
        asks the constraint graph to validate the proposed constraint without
        permanently modifying the graph or any item positions.

        Args:
            anchor_a: AnchorRef for the first anchor.
            anchor_b: AnchorRef for the second anchor (vertex for ANGLE).
            target_distance: Desired distance in cm, or degrees for ANGLE.
            constraint_type: ConstraintType.
            anchor_c: Optional third AnchorRef for ANGLE constraints.

        Returns:
            True  — the constraint is compatible with the existing system.
            False — adding it would create an irresolvable conflict.
        """
        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        graph = self._canvas_scene.constraint_graph

        # Collect all item IDs that need positions
        constrained_ids: set = {anchor_a.item_id, anchor_b.item_id}
        if anchor_c is not None:
            constrained_ids.add(anchor_c.item_id)
        for c in graph.constraints.values():
            constrained_ids.add(c.anchor_a.item_id)
            constrained_ids.add(c.anchor_b.item_id)
            if c.anchor_c is not None:
                constrained_ids.add(c.anchor_c.item_id)

        item_positions: dict = {}
        item_map: dict = {}
        anchor_offsets: dict = {}
        construction_ids: set = set()

        for item in self.scene().items():
            is_garden = isinstance(item, GardenItemMixin)
            is_construction = isinstance(
                item, (ConstructionLineItem, ConstructionCircleItem)
            )
            if (is_garden or is_construction) and item.item_id in constrained_ids:
                uid = item.item_id
                item_map[uid] = item
                pos = item.pos()
                item_positions[uid] = (pos.x(), pos.y())
                for anchor in get_anchor_points(item):
                    key = (uid, anchor.anchor_type, anchor.anchor_index)
                    anchor_offsets[key] = (
                        anchor.point.x() - pos.x(),
                        anchor.point.y() - pos.y(),
                    )
                if is_construction:
                    construction_ids.add(uid)

        if len(item_positions) < 2:
            return True  # Not enough items to form a conflict — optimistically allow

        deformable_items, deformable_vertices = self._gather_deformable_info(item_map)

        return graph.validate_constraint(
            anchor_a=anchor_a,  # type: ignore[arg-type]
            anchor_b=anchor_b,  # type: ignore[arg-type]
            target_distance=target_distance,
            constraint_type=constraint_type,  # type: ignore[arg-type]
            item_positions=item_positions,
            anchor_offsets=anchor_offsets,
            anchor_c=anchor_c,  # type: ignore[arg-type]
            deformable_items=deformable_items,
            deformable_vertices=deformable_vertices,
        )

    # Coordinate conversion

    def scene_to_canvas(self, scene_point: QPointF) -> QPointF:
        """Convert scene coordinates to canvas coordinates (Y-flip).

        Scene: Y-down, origin top-left (Qt's abstract convention for the raw
            numbers). NOTE: OGP's view flip renders the same raw scene frame
            Y-up, so a larger scene y is visually north (§11.4 "Canvas Y-axis
            flip") — the frame the Agent API describes to agents.
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
        from open_garden_planner.core.canvas_bounds import clamp_shift_within_canvas
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        # Filter out background images — they should move freely beyond the canvas
        clampable = [i for i in items if not isinstance(i, BackgroundImageItem)]
        if not clampable:
            return

        canvas = self._canvas_scene.canvas_rect
        rects = [
            (r.left(), r.top(), r.right(), r.bottom())
            for r in (item.sceneBoundingRect() for item in clampable)
        ]
        dx, dy = clamp_shift_within_canvas(rects, canvas.width(), canvas.height())

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
        from open_garden_planner.core.canvas_bounds import clamp_delta_within_canvas
        from open_garden_planner.ui.canvas.items import BackgroundImageItem

        clampable = [i for i in items if not isinstance(i, BackgroundImageItem)]
        if not clampable:
            return delta

        canvas = self._canvas_scene.canvas_rect
        rects = [
            (r.left(), r.top(), r.right(), r.bottom())
            for r in (item.sceneBoundingRect() for item in clampable)
        ]
        dx, dy = clamp_delta_within_canvas(
            rects, delta.x(), delta.y(), canvas.width(), canvas.height()
        )
        return QPointF(dx, dy)

    def snap_point(self, point: QPointF) -> QPointF:
        """Snap a point to the grid if snap is enabled, and clamp to canvas.

        Args:
            point: Point in canvas coordinates

        Returns:
            Point snapped to grid (if enabled) and clamped to canvas borders.

        Anchor-snap takes precedence (Package A US-A3): if the dispatcher
        already matched a midpoint / intersection / endpoint candidate
        for this event, applying grid snap would round it back to the
        grid (e.g. a midpoint at (175, 50) becomes (200, 50) with a
        50 cm grid) and silently override the user's intent.  When
        ``_current_snap`` is set, grid snap is skipped and only the
        canvas-bounds clamp remains.
        """
        # Always clamp to canvas borders first
        clamped = self.clamp_to_canvas(point)

        if not self._snap_enabled or self._current_snap is not None:
            return clamped

        snapped = QPointF(
            round(clamped.x() / self._grid_size) * self._grid_size,
            round(clamped.y() / self._grid_size) * self._grid_size,
        )

        # Re-clamp after snapping (grid snap near border could push outside)
        return self.clamp_to_canvas(snapped)

    def _on_scene_changed_for_snap(self, _rects: object) -> None:
        """Mark the snap spatial index for rebuild on next query."""
        self._snap_index_dirty = True

    def _ensure_snap_index(self) -> None:
        """Lazily rebuild the spatial index from the current scene."""
        if not self._snap_index_dirty:
            return
        from PyQt6.QtWidgets import QGraphicsItem as _QGI

        items = [
            it
            for it in self._canvas_scene.items()
            if (it.flags() & _QGI.GraphicsItemFlag.ItemIsSelectable)
        ]
        self._point_snapper.update_scene(items, scene_bounds=self.scene().sceneRect())
        self._snap_index_dirty = False

    @property
    def current_snap_candidate(self) -> SnapCandidate | None:
        """The most recent snap result, or ``None`` if the cursor isn't snapped.

        Drawing tools read this in `mouse_press` to record *which* snap kind
        and source item produced each committed vertex, so the auto-
        constraint emitter (Package B follow-up) can decide whether to
        attach a POINT_ON_EDGE / POINT_ON_CIRCLE / PERPENDICULAR constraint
        on finalization.
        """
        return self._current_snap

    def anchor_snap(
        self,
        scene_pos: QPointF,
        threshold: float = 15.0,
    ) -> tuple[QPointF, SnapCandidate | None]:
        """Snap ``scene_pos`` to the closest enabled anchor candidate.

        Returns the (possibly unchanged) point and the snap candidate that
        produced it (``None`` if no provider matched within ``threshold``).
        Caller can use the candidate's ``kind`` to render a glyph.

        Phase 13 B5: the active drawing tool's ``last_point`` is
        forwarded to the registry as ``reference_point`` so the
        perpendicular and tangent providers can operate against it.
        """
        if not self._snap_registry.providers():
            return scene_pos, None
        self._ensure_snap_index()
        ref = self._active_tool_reference_point()
        hit = self._point_snapper.snap(
            scene_pos, threshold=threshold, reference_point=ref
        )
        if hit is None:
            return scene_pos, None
        return QPointF(hit.point), hit

    def _active_tool_reference_point(self) -> QPointF | None:
        """Return the active drawing tool's anchor for perpendicular/tangent.

        Reads ``last_point`` from the tool — ``None`` when no tool is
        active, the tool exposes no anchor, or the select tool is up.
        """
        tool = self._tool_manager.active_tool
        if tool is None:
            return None
        last = getattr(tool, "last_point", None)
        if last is None:
            return None
        return QPointF(last)

    @property
    def coordinate_input_buffer(self) -> CoordinateInputBuffer:
        """The shared typed-coordinate buffer (Package A US-A1/A2/A4)."""
        return self._input_buffer

    def refresh_input_anchor(self) -> None:
        """Sync the shared input buffer's anchor with the active tool."""
        tool = self._tool_manager.active_tool
        if tool is None:
            self._input_buffer.set_anchor(None)
            return
        self._input_buffer.set_anchor(getattr(tool, "last_point", None))

    def commit_typed_coordinate(self, point: QPointF) -> bool:
        """Forward a parsed coordinate to the active drawing tool.

        Returns ``True`` when accepted; refreshes the input anchor either
        way so the next input is anchored correctly.
        """
        tool = self._tool_manager.active_tool
        if tool is None:
            return False
        try:
            accepted = bool(tool.commit_typed_coordinate(point))
        finally:
            self.refresh_input_anchor()
        return accepted

    def _maybe_apply_anchor_snap(self, tool: object, scene_pos: QPointF) -> QPointF:
        """Apply Package A point snap unless the tool opts out.

        Tools that run their own anchor logic (select, measure,
        constraint family) set ``BaseTool.skip_anchor_snap = True``.
        Using a class flag avoids the fragile string-prefix match on
        ``tool_type.name`` that would have silently mis-classified a
        future tool type whose name happens to share a prefix.
        """
        if tool is None or getattr(tool, "skip_anchor_snap", False):
            self._set_current_snap(None)
            return scene_pos
        snapped, candidate = self.anchor_snap(scene_pos)
        self._set_current_snap(candidate)
        return snapped

    def _set_current_snap(self, candidate: SnapCandidate | None) -> None:
        """Update the current snap candidate; trigger redraw on change."""
        previous = self._current_snap
        self._current_snap = candidate
        if previous is None and candidate is None:
            return
        # Repainting the viewport draws (or clears) the indicator glyph.
        self.viewport().update()

    # Drag-and-drop from gallery panel and plant lists panel

    def dragEnterEvent(self, event) -> None:
        """Accept drag events from the gallery panel or plant lists panel."""
        if event.mimeData().hasText() and (
            event.mimeData().text().startswith("gallery:")
            or event.mimeData().text().startswith("plant_list:")
        ):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        """Accept drag move events from the gallery panel or plant lists panel."""
        if event.mimeData().hasText() and (
            event.mimeData().text().startswith("gallery:")
            or event.mimeData().text().startswith("plant_list:")
        ):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def _create_plant_item_at_scene_pos(
        self,
        scene_pos: QPointF,
        tool_type: ToolType,
        obj_type: ObjectType,
        radius: float,
        species_name: str = "",
        plant_category: PlantCategory | None = None,
        species_dict: dict[str, Any] | None = None,
    ) -> CircleItem:
        """Create a plant item directly at scene_pos with auto-parenting and undo support.

        Shared canonical drop path for gallery drops and Plant Lists panel drops.
        """
        from open_garden_planner.core.commands import CreateItemCommand
        from open_garden_planner.core.tools import ToolType as TT
        from open_garden_planner.ui.plant_creation import build_plant

        self.set_active_tool(tool_type)
        if self._snap_enabled:
            scene_pos = self.snap_point(scene_pos)
        manager = getattr(self.window(), "_project_manager", None)
        item = build_plant(self._canvas_scene, scene_pos, obj_type, radius,
                           species_name=species_name, plant_category=plant_category,
                           species_dict=species_dict,
                           auto_assign=bool(manager and manager.auto_assign_permaculture_layers))

        # One undo step with auto-parenting (CreateItemCommand handles _auto_parent_plant)
        cmd = CreateItemCommand(self._canvas_scene, item)
        self._command_manager.execute(cmd)

        # Switch to select tool and select the new item
        self.set_active_tool(TT.SELECT)
        self._canvas_scene.clearSelection()
        item.setSelected(True)
        return item

    def dropEvent(self, event) -> None:
        """Handle drop from gallery panel or plant lists panel."""
        text = event.mimeData().text()
        if not (text.startswith("gallery:") or text.startswith("plant_list:")):
            super().dropEvent(event)
            return

        event.acceptProposedAction()
        scene_pos = self.mapToScene(event.position().toPoint())

        from open_garden_planner.core.plant_renderer import PlantCategory
        from open_garden_planner.core.tools import ToolType as TT

        # Branch A: Drop from Plant Lists panel (US-G4, issue #320)
        if text.startswith("plant_list:"):
            species_dict = None
            if event.mimeData().hasFormat("application/x-ogp-plant-data"):
                try:
                    species_dict = json.loads(bytes(event.mimeData().data("application/x-ogp-plant-data")).decode("utf-8"))
                except Exception:
                    species_dict = None

            if species_dict is not None:
                from open_garden_planner.models.plant_data import PlantSpeciesData
                species_obj = PlantSpeciesData.from_dict(species_dict)
            else:
                parts = text.split(":")
                entry_id = parts[1] if len(parts) > 1 else ""
                if not entry_id:
                    return

                from open_garden_planner.models.plant_lists import (
                    get_plant_list_store,
                )
                store = get_plant_list_store()
                _pl, entry = store.get_entry(entry_id)
                if entry is None or not entry.species:
                    return
                species_obj = entry.species

            from open_garden_planner.core.plant_sizing import (
                species_drop_diameter_cm,
            )
            from open_garden_planner.services.bundled_species_db import (
                merge_calendar_data,
            )

            name_lower = f"{species_obj.common_name or ''} {species_obj.scientific_name or ''}".lower()
            height = species_obj.max_height_cm or 0.0

            if height >= 350 or any(kw in name_lower for kw in ("tree", "baum", "arbor", "palm", "conifer")):
                tool_type = TT.TREE
                obj_type = ObjectType.TREE
                cat = PlantCategory.ROUND_DECIDUOUS
            elif height >= 100 or any(kw in name_lower for kw in ("shrub", "bush", "strauch", "busch")):
                tool_type = TT.SHRUB
                obj_type = ObjectType.SHRUB
                cat = PlantCategory.SPREADING_SHRUB
            else:
                tool_type = TT.PERENNIAL
                obj_type = ObjectType.PERENNIAL
                cat = PlantCategory.FLOWERING_PERENNIAL

            diameter = species_drop_diameter_cm(species_obj.to_dict(), obj_type.name)

            merged_dict = merge_calendar_data(species_obj.to_dict())
            self._create_plant_item_at_scene_pos(
                scene_pos=scene_pos,
                tool_type=tool_type,
                obj_type=obj_type,
                radius=diameter / 2,
                species_name=species_obj.common_name or species_obj.scientific_name,
                plant_category=cat,
                species_dict=merged_dict,
            )
            return

        # Branch B: Drop from Gallery panel
        # Parse the gallery data: "gallery:TOOL_TYPE:species=xxx:category=YYY"
        parts = text.split(":")
        tool_name = parts[1] if len(parts) > 1 else ""

        # Extract species and category from drag data
        species = ""
        plant_category = None
        for part in parts[2:]:
            if part.startswith("species="):
                species = part[len("species=") :]
            elif part.startswith("category="):
                cat_name = part[len("category=") :]
                with contextlib.suppress(KeyError, ValueError):
                    plant_category = PlantCategory[cat_name]

        # Find the matching ToolType
        try:
            tool_type = TT[tool_name]
        except (KeyError, ValueError):
            return

        # For plant tools (circle-based), create the item directly at the drop location
        if tool_type in (TT.TREE, TT.SHRUB, TT.PERENNIAL):
            obj_map = {
                TT.TREE: ObjectType.TREE,
                TT.SHRUB: ObjectType.SHRUB,
                TT.PERENNIAL: ObjectType.PERENNIAL,
            }
            obj_type = obj_map.get(tool_type, ObjectType.TREE)

            # A gallery entry that names a known species is planted at its real
            # mature spread, exactly like a Plant Database or Plant Lists drop;
            # the type default is only for an unknown/custom name. An 8 m apple
            # tree dropped 2 m wide made the 3D tree unnaturally slim while its
            # height came from the species (#596).
            from open_garden_planner.core.plant_sizing import species_drop_diameter_cm
            from open_garden_planner.services.bundled_species_db import lookup_species

            record = lookup_species(species) if species else None
            diameter = species_drop_diameter_cm(record, obj_type.name)

            self._create_plant_item_at_scene_pos(
                scene_pos=scene_pos,
                tool_type=tool_type,
                obj_type=obj_type,
                radius=diameter / 2,
                species_name=species,
                plant_category=plant_category,
            )
        else:
            # Non-plant tool: activate tool
            self.set_active_tool(tool_type)

    # Event handlers

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for smooth zooming."""
        # Get the scroll amount (typically 120 per notch, but can vary)
        delta = event.angleDelta().y()

        if delta == 0:
            event.accept()
            return

        # Apply immediate zoom: 1.15x per standard wheel notch (120 units). The
        # anchor and clamp live in ``_zoom_at``, shared with the pinch gesture.
        factor = 1.15 ** (delta / 120.0)
        self._zoom_at(event.position(), factor)
        event.accept()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        """Show context menu on empty-canvas right-click."""
        scene_pos = self.mapToScene(event.pos())
        items_at = [
            i for i in self.scene().items(scene_pos)
            if i.isVisible() and i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        ]
        if items_at:
            super().contextMenuEvent(event)
            return
        menu = QMenu(self)
        import_action = menu.addAction(self.tr("Import Background Image..."))
        selected = menu.exec(event.globalPos())
        if selected == import_action:
            self.import_background_image_requested.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for panning and tool operations."""
        # Grab keyboard focus so Delete/arrow keys work
        self.setFocus()

        # ── Guide line handling ─────────────────────────────────────────────
        if self._guides_visible and event.button() == Qt.MouseButton.LeftButton:
            vp_pos = event.position()
            rs = self.RULER_SIZE
            in_top_ruler = vp_pos.y() < rs and vp_pos.x() >= rs
            in_left_ruler = vp_pos.x() < rs and vp_pos.y() >= rs

            if in_top_ruler:
                # Dragging from top ruler → new horizontal guide
                scene_pos = self.mapToScene(vp_pos.toPoint())
                guide = GuideLine(is_horizontal=True, position=scene_pos.y())
                self._dragging_guide = guide
                self._dragging_guide_is_new = True
                event.accept()
                return

            if in_left_ruler:
                # Dragging from left ruler → new vertical guide
                scene_pos = self.mapToScene(vp_pos.toPoint())
                guide = GuideLine(is_horizontal=False, position=scene_pos.x())
                self._dragging_guide = guide
                self._dragging_guide_is_new = True
                event.accept()
                return

            # Check if pressing on an existing guide
            hit = self._guide_hit_test(vp_pos)
            if hit:
                self._dragging_guide = hit
                self._dragging_guide_is_new = False
                event.accept()
                return

        # Handle calibration mode
        if (
            self._canvas_scene.is_calibrating
            and event.button() == Qt.MouseButton.LeftButton
        ):
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
            scene_pos = self._maybe_apply_anchor_snap(tool, scene_pos)
            if tool.mouse_press(event, scene_pos):
                # Tool consumed a click - refresh the typed-input anchor.
                self.refresh_input_anchor()
                event.accept()
                return

        super().mousePressEvent(event)

        # Track which handle (if any) just grabbed the mouse.
        # Qt silently drops the grab on ItemIgnoresTransformations child items
        # between event dispatches, so we re-establish it ourselves in mouseMoveEvent.
        if event.button() == Qt.MouseButton.LeftButton:
            grabber = self.scene().mouseGrabberItem()
            if isinstance(grabber, DRAG_HANDLE_TYPES):
                self._active_drag_handle = grabber
                # Block rotation for items that have an inter-object PARALLEL or
                # PERPENDICULAR constraint — rotating would violate the constraint.
                if isinstance(grabber, RotationHandle):
                    parent = grabber.parentItem()
                    if (parent is not None
                            and hasattr(parent, "item_id")
                            and self._canvas_scene.constraint_graph
                                .has_interobject_rotation_constraint(parent.item_id)):
                        grabber.ungrabMouse()
                        self._active_drag_handle = None
            else:
                self._active_drag_handle = None

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

        # Dynamic Input overlay (Package A US-A4): track the cursor.
        self._update_dynamic_overlay(event.position().toPoint())

        # ── Guide drag ─────────────────────────────────────────────────────
        if self._dragging_guide is not None:
            guide = self._dragging_guide
            if guide.is_horizontal:
                guide.position = scene_pos.y()
                self.setCursor(Qt.CursorShape.SplitVCursor)
            else:
                guide.position = scene_pos.x()
                self.setCursor(Qt.CursorShape.SplitHCursor)

            # Add to scene's guide list on first move (lazy: avoids phantom guide on click)
            if (
                self._dragging_guide_is_new
                and guide not in self._canvas_scene.guide_lines
            ):
                self._canvas_scene.guide_lines.append(guide)

            self.scene().update()
            self.viewport().update()
            event.accept()
            return

        # ── Guide hover cursor ─────────────────────────────────────────────
        if self._guides_visible:
            prev_hovered = self._hovered_guide
            self._hovered_guide = self._guide_hit_test(event.position())
            if self._hovered_guide is not None:
                if self._hovered_guide.is_horizontal:
                    self.setCursor(Qt.CursorShape.SplitVCursor)
                else:
                    self.setCursor(Qt.CursorShape.SplitHCursor)
            elif prev_hovered is not None:
                self.unsetCursor()
            if self._hovered_guide is not prev_hovered:
                self.viewport().update()

        if self._panning:
            # Pan the view by translating (the one pan path, shared with #321's
            # two-finger gesture).
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            self._pan_by(delta)
            event.accept()
            return

        # Re-establish the mouse grab if Qt silently dropped it between events.
        # This happens with ItemIgnoresTransformations child items in PyQt6.
        if (
            self._active_drag_handle is not None
            and self.scene().mouseGrabberItem() is None
            and self._active_drag_handle.scene() is not None
        ):
            self._active_drag_handle.grabMouse()

        # Delegate to active tool (with anchor snap pre-applied for non-select
        # drawing tools, Package A US-A3).
        tool = self._tool_manager.active_tool
        if tool:
            scene_pos = self._maybe_apply_anchor_snap(tool, scene_pos)
            if tool.mouse_move(event, scene_pos):
                event.accept()
                return

        super().mouseMoveEvent(event)

        # Propagate bed movement to child plants during drag
        self._propagate_bed_children_during_drag()

        # Revert any FIXED-constrained items to their pinned position
        self._enforce_fixed_positions()

        # Clamp POINT_ON_EDGE-constrained items to their edge line during drag
        self._enforce_point_on_edge_positions()

        # Apply object snapping and canvas boundary clamping during drag
        self._apply_object_snap_during_drag()
        self._clamp_dragged_items_to_canvas()

        # Propagate constraints to connected items during drag.
        # Skip during rotation — constraint solving doesn't apply while rotating.
        if not isinstance(self._active_drag_handle, RotationHandle):
            self._propagate_constraints_during_drag()

        # Update dimension lines in real-time during drag
        if self._drag_start_positions:
            self._canvas_scene.update_dimension_lines()

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
            if (
                item in self._drag_start_positions
                and item.pos() != self._drag_start_positions[item]
            ):
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
        # Add guide lines as additional snap targets
        guide_x: list[float] = []
        guide_y: list[float] = []
        if self._guides_visible:
            for guide in self._canvas_scene.guide_lines:
                if guide.is_horizontal:
                    guide_y.append(guide.position)
                else:
                    guide_x.append(guide.position)

        snap_result = self._object_snapper.snap(
            combined,
            list(self.scene().items()),
            exclude=exclude,
            canvas_rect=self._canvas_scene.canvas_rect,
            extra_x=guide_x if guide_x else None,
            extra_y=guide_y if guide_y else None,
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

    def _enforce_fixed_positions(self) -> None:
        return self._drag_constraints._enforce_fixed_positions()

    def _enforce_point_on_edge_positions(self) -> None:
        return self._drag_constraints._enforce_point_on_edge_positions()

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
            item in self._drag_start_positions
            and item.pos() != self._drag_start_positions[item]
            for item in selected
        )
        if not any_moved:
            return

        self._clamp_items_to_canvas(selected)

    def _compute_constraint_propagation(
        self,
        moved_items: list[QGraphicsItem],
        delta: QPointF,
    ) -> list[tuple[QGraphicsItem, QPointF]]:
        return self._drag_constraints._compute_constraint_propagation(moved_items, delta)

    def _propagate_constraints_during_drag(self) -> None:
        return self._drag_constraints._propagate_constraints_during_drag()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release to stop panning and finish tool operations."""
        # Clear snap guides
        if self._snap_guides:
            self._snap_guides = []
            self.viewport().update()

        # ── Finalize guide drag ─────────────────────────────────────────────
        if (
            self._dragging_guide is not None
            and event.button() == Qt.MouseButton.LeftButton
        ):
            guide = self._dragging_guide
            vp_pos = event.position()
            rs = self.RULER_SIZE

            # Dragged back into ruler area → remove guide
            dropped_on_ruler = (guide.is_horizontal and vp_pos.y() < rs) or (
                not guide.is_horizontal and vp_pos.x() < rs
            )
            if dropped_on_ruler and guide in self._canvas_scene.guide_lines:
                self._canvas_scene.guide_lines.remove(guide)

            self._dragging_guide = None
            self._dragging_guide_is_new = False
            self.unsetCursor()
            self.scene().update()
            self.viewport().update()
            event.accept()
            return

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

        # Re-establish mouse grab if Qt dropped it (ItemIgnoresTransformations bug).
        # Must happen BEFORE super() so the handle receives the release event.
        if (self._active_drag_handle is not None
                and self.scene().mouseGrabberItem() is None
                and self._active_drag_handle.scene() is not None):
            self._active_drag_handle.grabMouse()

        # Capture whether a vertex drag is ending so we can enforce constraints below.
        was_vertex_drag = (
            isinstance(self._active_drag_handle, VertexHandle)
            and event.button() == Qt.MouseButton.LeftButton
        )
        if was_vertex_drag:
            self._deferring_vertex_undo = True
            self._deferred_vertex_move = None

        # Clear the handle tracking regardless of what handles the release
        self._active_drag_handle = None

        # Delegate to active tool
        tool = self._tool_manager.active_tool
        if tool:
            scene_pos = self.mapToScene(event.position().toPoint())
            scene_pos = self._maybe_apply_anchor_snap(tool, scene_pos)
            if tool.mouse_release(event, scene_pos):
                self.refresh_input_anchor()
                event.accept()
                self._drag_start_positions.clear()
                self._constraint_propagated_starts.clear()
                if was_vertex_drag:
                    self._deferring_vertex_undo = False
                return

        super().mouseReleaseEvent(event)

        if was_vertex_drag:
            self._deferring_vertex_undo = False
            self._enforce_after_vertex_drag()

        # Check if items were dragged and create undo command
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start_positions:
            self._finalize_drag_move()

    def _enforce_after_vertex_drag(self) -> None:
        return self._drag_constraints._enforce_after_vertex_drag()

    def _reenforce_parallel_after_vertex_move(self, item: object, vertex_index: int) -> None:
        return self._drag_constraints._reenforce_parallel_after_vertex_move(item, vertex_index)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle mouse double click for tool operations and constraint editing."""
        scene_pos = self.mapToScene(event.position().toPoint())

        # Double-click on a guide line → edit its position numerically
        if self._guides_visible and event.button() == Qt.MouseButton.LeftButton:
            hit = self._guide_hit_test(event.position())
            if hit:
                self._edit_guide_position(hit)
                event.accept()
                return

        # Check if double-click is on a dimension line to edit constraint
        if event.button() == Qt.MouseButton.LeftButton:
            cid = self._canvas_scene.dimension_line_manager.get_constraint_at(scene_pos)
            if cid is not None:
                self._edit_constraint_distance(cid)
                event.accept()
                return

        tool = self._tool_manager.active_tool
        if tool and tool.mouse_double_click(event, scene_pos):
            self.refresh_input_anchor()
            event.accept()
            return

        # Snapshot positions and scroll state before delegating:
        # Qt's QGraphicsView::mouseDoubleClickEvent internally re-runs its press handler
        # (mousePressEventHandler), which can interact with ItemIsMovable and AnchorUnderMouse
        # under the Y-flip transform to produce spurious position jumps and view panning (issue #108).
        _pre_dbl = {item: item.pos() for item in self.scene().selectedItems()}
        _hbar = self.horizontalScrollBar().value()
        _vbar = self.verticalScrollBar().value()

        super().mouseDoubleClickEvent(event)

        # Restore any position that shifted during double-click processing.
        for item, pos in _pre_dbl.items():
            if item.pos() != pos:
                _log.warning(
                    "Double-click caused position drift on %s: %s → %s (zoom=%.2f) — restoring.",
                    type(item).__name__,
                    pos,
                    item.pos(),
                    self._zoom_factor,
                )
                item.setPos(pos)

        # Restore scroll position if the internal press handler panned the view.
        if self.horizontalScrollBar().value() != _hbar:
            _log.warning(
                "Double-click caused H-scroll drift: %d → %d (zoom=%.2f) — restoring.",
                _hbar,
                self.horizontalScrollBar().value(),
                self._zoom_factor,
            )
            self.horizontalScrollBar().setValue(_hbar)
        if self.verticalScrollBar().value() != _vbar:
            _log.warning(
                "Double-click caused V-scroll drift: %d → %d (zoom=%.2f) — restoring.",
                _vbar,
                self.verticalScrollBar().value(),
                self._zoom_factor,
            )
            self.verticalScrollBar().setValue(_vbar)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press for tool operations and editing."""
        # Handle ESC to cancel calibration
        if event.key() == Qt.Key.Key_Escape and self._canvas_scene.is_calibrating:
            self._canvas_scene.cancel_calibration()
            event.accept()
            return

        # Handle ESC to exit vertex edit mode
        if event.key() == Qt.Key.Key_Escape:
            for item in self._canvas_scene.selectedItems():
                if hasattr(item, "is_vertex_edit_mode") and item.is_vertex_edit_mode:
                    item.exit_vertex_edit_mode()
                    event.accept()
                    return

        # Handle Copy (Ctrl+C)
        if (
            event.key() == Qt.Key.Key_C
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.copy_selected()
            event.accept()
            return

        # Handle Cut (Ctrl+X)
        if (
            event.key() == Qt.Key.Key_X
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.cut_selected()
            event.accept()
            return

        # Handle Paste (Ctrl+V)
        if (
            event.key() == Qt.Key.Key_V
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.paste()
            event.accept()
            return

        # Handle Duplicate (Ctrl+D)
        if (
            event.key() == Qt.Key.Key_D
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.duplicate_selected()
            event.accept()
            return

        # Handle Group (Ctrl+G) / Ungroup (Ctrl+Shift+G)
        if (
            event.key() == Qt.Key.Key_G
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._ungroup_selected()
            else:
                self._group_selected()
            event.accept()
            return

        # Dispatch bare letter/digit keys to registered tools via their shortcut attribute.
        # Guard: no modifier keys; scene not editing text (label edit in progress).
        _focus = self._canvas_scene.focusItem()
        _in_text_edit = _focus is not None and hasattr(_focus, 'toPlainText')

        # Route coordinate-input characters (Package A US-A4) into the Dynamic
        # Input overlay so the user can type `@500,0`, `@300<45`, etc. without
        # ever clicking into the floating fields.  Runs before the tool-shortcut
        # dispatcher: coordinate characters never overlap with tool letters,
        # but explicit ordering avoids surprises if a future tool grabs e.g. ','.
        # ``not event.modifiers()`` mirrors the guard on the tool-shortcut
        # dispatcher below so e.g. a future ``Ctrl+,`` menu accelerator is not
        # silently swallowed here.
        if (
            self._dynamic_input_enabled
            and not event.modifiers()
            and not _in_text_edit
            and event.text()
            and self._is_coord_input_char(event.text())
        ):
            tool = self._tool_manager.active_tool
            if (
                tool is not None
                and getattr(tool, "tool_type", None) != ToolType.SELECT
                and getattr(tool, "last_point", None) is not None
            ):
                overlay = self._ensure_dynamic_overlay()
                overlay.forward_keystroke(event.text())
                event.accept()
                return

        if not event.modifiers() and not _in_text_edit and event.text():
            _key = event.text().upper()
            for _tool in self._tool_manager._tools.values():
                if _tool.shortcut and _tool.shortcut.upper() == _key:
                    self.set_active_tool(_tool.tool_type)
                    event.accept()
                    return

        # Delegate to active tool first
        tool = self._tool_manager.active_tool
        if tool and tool.key_press(event):
            self.refresh_input_anchor()
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

    def _edit_constraint_distance(self, constraint_id) -> None:
        """Open dialog to edit a constraint's target distance.

        After the user confirms a new distance, the constraint solver is run
        immediately so objects move to satisfy the new value.  Both the
        distance change and the resulting item moves are bundled into a single
        undo step.

        Args:
            constraint_id: UUID of the constraint to edit
        """
        from open_garden_planner.core.commands import EditConstraintDistanceCommand
        from open_garden_planner.core.constraints import ConstraintType
        from open_garden_planner.core.tools.constraint_tool import DistanceInputDialog

        graph = self._canvas_scene.constraint_graph
        constraint = graph.constraints.get(constraint_id)
        if constraint is None:
            return
        if constraint.constraint_type not in {
            ConstraintType.DISTANCE,
            ConstraintType.EDGE_LENGTH,
            ConstraintType.HORIZONTAL_DISTANCE,
            ConstraintType.VERTICAL_DISTANCE,
        }:
            return

        dialog = DistanceInputDialog(constraint.target_distance, self)
        if dialog.exec():
            new_distance = dialog.distance_cm()
            if abs(new_distance - constraint.target_distance) > 0.01:
                old_distance = constraint.target_distance

                # CAD convention: A moves, B stays.  If A is already FIXED the
                # pre-pass in solve_anchored pins it, so B must remain free.
                a_is_fixed = any(
                    c.constraint_type == ConstraintType.FIXED
                    and c.anchor_a.item_id == constraint.anchor_a.item_id
                    for c in graph.constraints.values()
                )
                extra_pinned: set | None = (
                    None if a_is_fixed else {constraint.anchor_b.item_id}
                )

                # Temporarily apply new distance so solver can compute moves
                constraint.target_distance = new_distance
                item_moves, vertex_moves = self._compute_constraint_solve_moves(
                    extra_pinned=extra_pinned
                )
                constraint.target_distance = old_distance  # command will set it

                command = EditConstraintDistanceCommand(
                    graph=graph,
                    constraint_id=constraint_id,
                    old_distance=old_distance,
                    new_distance=new_distance,
                    item_moves=item_moves,
                )
                command._vertex_moves = vertex_moves
                self._command_manager.execute(command)

    @staticmethod
    def _get_vertex_local(item: QGraphicsItem, index: int) -> QPointF | None:
        """Get a vertex position in item-local coordinates."""
        from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

        if isinstance(item, PolygonItem):
            polygon = item.polygon()
            if 0 <= index < polygon.count():
                return polygon.at(index)
        elif isinstance(item, PolylineItem):
            points = item.points
            if 0 <= index < len(points):
                return QPointF(points[index])
        return None

    @staticmethod
    def _iter_item_vertices(item: QGraphicsItem) -> list[QPointF]:
        """Return current vertices of a deformable item in item-local coords.

        Dispatches on item type so callers don't have to special-case the
        polygon ``polygon().at(i)`` API vs the polyline ``_points`` list.
        """
        from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

        if isinstance(item, PolygonItem):
            pg = item.polygon()
            return [QPointF(pg.at(i)) for i in range(pg.count())]
        if isinstance(item, PolylineItem):
            return [QPointF(p) for p in item.points]
        return []

    @staticmethod
    def _gather_deformable_info(
        item_map: dict,
    ) -> tuple[set, dict[..., list[tuple[float, float]]]]:
        return DragConstraints._gather_deformable_info(item_map)

    def _compute_edge_length_constraint_moves(
        self, command: AddConstraintCommand
    ) -> tuple[list[tuple[QGraphicsItem, QPointF, QPointF]], list[tuple[QGraphicsItem, int, QPointF, QPointF]]]:
        return self._drag_constraints._compute_edge_length_constraint_moves(command)

    def _compute_constraint_solve_moves(
        self,
        extra_pinned: set | None = None,
    ) -> tuple[list[tuple[QGraphicsItem, QPointF, QPointF]], list[tuple[QGraphicsItem, int, QPointF, QPointF]]]:
        return self._drag_constraints._compute_constraint_solve_moves(extra_pinned)

    def _delete_selected_items(self) -> None:
        """Delete all selected items from the scene with undo support.

        Also removes any distance constraints involving the deleted items.
        If a bed with children is selected, prompts the user.
        """
        selected = list(self.scene().selectedItems())
        if not selected:
            return

        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        # Check for plant-parents (beds/containers/trellises) with children
        beds_with_children = [
            item
            for item in selected
            if isinstance(item, GardenItemMixin)
            and is_plant_parent_type(item.object_type)
            and item.has_children
        ]

        if beds_with_children:
            from PyQt6.QtWidgets import QMessageBox

            msg = QMessageBox(self)
            msg.setWindowTitle(self.tr("Delete Bed"))
            msg.setText(
                self.tr(
                    "The selected bed(s) contain plants. What would you like to do?"
                )
            )
            delete_all_btn = msg.addButton(
                self.tr("Delete bed and plants"),
                QMessageBox.ButtonRole.DestructiveRole,
            )
            msg.addButton(
                self.tr("Keep plants"),
                QMessageBox.ButtonRole.AcceptRole,
            )
            cancel_btn = msg.addButton(QMessageBox.StandardButton.Cancel)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == cancel_btn:
                return

            if clicked == delete_all_btn:
                # Add child plants to the deletion set
                selected_ids = {
                    item.item_id
                    for item in selected
                    if isinstance(item, GardenItemMixin)
                }
                for bed in beds_with_children:
                    for child_id in bed.child_item_ids:
                        if child_id not in selected_ids:
                            child = self._canvas_scene.find_item_by_id(child_id)
                            if child is not None:
                                selected.append(child)
                                selected_ids.add(child_id)
            else:
                # Keep plants: DeleteItemsCommand will handle detaching
                # children on execute and reattaching on undo.
                pass

        # Expand deletion to include associated roof ridges (metadata-linked, not Qt children)
        from uuid import UUID as _UUID

        from open_garden_planner.core.object_types import ObjectType

        _sel_ids = {item.item_id for item in selected if isinstance(item, GardenItemMixin)}
        for _item in list(selected):
            if not isinstance(_item, GardenItemMixin):
                continue
            if _item.object_type != ObjectType.HOUSE:
                continue
            ridge_id_str = _item.metadata.get("ridge_item_id")
            if ridge_id_str and hasattr(self._canvas_scene, "find_item_by_id"):
                try:
                    ridge = self._canvas_scene.find_item_by_id(_UUID(ridge_id_str))
                except ValueError:
                    continue
                if ridge is not None and ridge.item_id not in _sel_ids:
                    selected.append(ridge)
                    _sel_ids.add(ridge.item_id)

        # Collect constraints to remove for deleted items (garden + construction)
        graph = self._canvas_scene.constraint_graph
        constraints_to_remove = []
        for item in selected:
            if isinstance(
                item, (GardenItemMixin, ConstructionLineItem, ConstructionCircleItem)
            ):
                for constraint in graph.get_item_constraints(item.item_id):
                    if constraint not in constraints_to_remove:
                        constraints_to_remove.append(constraint)

        # Remove constraints first (before items are removed from scene)
        for constraint in constraints_to_remove:
            cmd = RemoveConstraintCommand(graph, constraint)
            self._command_manager.execute(cmd)

        # Split journal pins off so each goes through DeleteJournalNoteCommand,
        # which also prunes the matching note dict from ProjectData. Otherwise
        # the keyboard-Delete path would orphan the note (the right-click
        # "Delete" menu already routes correctly via the view signal).
        from open_garden_planner.ui.canvas.items.journal_pin_item import (
            JournalPinItem,
        )

        journal_pin_ids = [
            i.note_id for i in selected if isinstance(i, JournalPinItem)
        ]
        regular_items = [i for i in selected if not isinstance(i, JournalPinItem)]

        if journal_pin_ids:
            self.journal_notes_batch_delete_requested.emit(journal_pin_ids)

        if regular_items:
            command = DeleteItemsCommand(self.scene(), regular_items)
            self._command_manager.execute(command)

    def _move_selected_items(self, event: QKeyEvent) -> None:
        """Move selected items based on arrow key with undo support.

        Normal: move by grid size (default 50cm)
        Shift: move by 1cm (precision mode)

        This method has no explicit handling for Ctrl / Ctrl+Shift
        modifiers on purpose: ``keyPressEvent`` routes every arrow key here
        regardless of modifiers, but Ctrl+Up/Down and Ctrl+Shift+Up/Down
        never actually arrive here in practice, because the Edit ▸ Arrange
        QAction shortcuts (``Bring Forward`` / ``Send Backward`` / etc.,
        issue #338) register those exact key combinations at the window
        level; Qt's shortcut system consumes them before this widget's
        ``keyPressEvent`` is even called. Only bare and Shift+arrow ever
        reach this function's ``event.modifiers()`` check below.
        """
        selected = self.scene().selectedItems()
        if not selected:
            return

        # Exclude items that are FIXED (pinned in place)
        from open_garden_planner.core.constraints import ConstraintType
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        fixed_ids = {
            c.anchor_a.item_id
            for c in self._canvas_scene.constraint_graph.constraints.values()
            if c.constraint_type == ConstraintType.FIXED
        }
        selected = [
            item
            for item in selected
            if not (isinstance(item, GardenItemMixin) and item.item_id in fixed_ids)
        ]
        if not selected:
            return

        # Include child plants of any selected beds
        selected_set = {id(i) for i in selected}
        extra_children: list[QGraphicsItem] = []
        for item in selected:
            if isinstance(item, GardenItemMixin) and is_plant_parent_type(
                item.object_type
            ):
                for child_id in item.child_item_ids:
                    child = self._canvas_scene.find_item_by_id(child_id)
                    if (
                        child is not None
                        and id(child) not in selected_set
                        and not (
                            isinstance(child, GardenItemMixin)
                            and child.item_id in fixed_ids
                        )
                    ):
                        extra_children.append(child)
                        selected_set.add(id(child))
        selected.extend(extra_children)

        # Determine move distance: 1cm precision with Shift, otherwise grid size
        distance = (
            1.0
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier
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

        # Check for constraint propagation
        graph = self._canvas_scene.constraint_graph
        if graph.constraints:
            propagated_deltas = self._compute_constraint_propagation(
                selected,
                delta,
            )
            if propagated_deltas:
                # Combine dragged + propagated into per-item deltas
                all_deltas: list[tuple[QGraphicsItem, QPointF]] = [
                    (item, delta) for item in selected
                ]
                all_deltas.extend(propagated_deltas)
                command = AlignItemsCommand(
                    all_deltas,
                    QCoreApplication.translate("Commands", "Move items (constrained)"),
                )
                self._command_manager.execute(command)
                return

        # Move with undo support (no constraints)
        command = MoveItemsCommand(selected, delta)
        self._command_manager.execute(command)

    def _finalize_drag_move(self) -> None:
        """Create undo command for mouse drag movement if items moved.

        Captures both directly dragged items and constraint-propagated items
        in a single compound undo command with per-item deltas.
        """
        if not self._drag_start_positions:
            self._constraint_propagated_starts.clear()
            return

        # If a resize or rotate command was just pushed to the undo stack, the
        # position/angle change is already captured by that command. Creating a
        # separate MoveItemsCommand would duplicate the delta and cause undo to
        # only revert the position without restoring the size/angle.
        from open_garden_planner.core.commands import ResizeItemCommand, RotateItemCommand

        if self._command_manager.can_undo:
            last_cmd = self._command_manager._undo_stack[-1]
            if isinstance(last_cmd, (ResizeItemCommand, RotateItemCommand)):
                self._drag_start_positions.clear()
                self._constraint_propagated_starts.clear()
                return

        # Collect per-item deltas for both dragged and propagated items
        item_deltas: list[tuple[QGraphicsItem, QPointF]] = []

        for item, start_pos in self._drag_start_positions.items():
            current_pos = item.pos()
            delta = current_pos - start_pos
            if delta.x() != 0 or delta.y() != 0:
                _log.debug(
                    "Item drag delta: start=%s current=%s delta=%s zoom=%.2f",
                    start_pos,
                    current_pos,
                    delta,
                    self._zoom_factor,
                )
                item_deltas.append((item, delta))

        for item, start_pos in self._constraint_propagated_starts.items():
            current_pos = item.pos()
            delta = current_pos - start_pos
            if delta.x() != 0 or delta.y() != 0:
                item_deltas.append((item, delta))

        # Propagate parent (bed/container/trellis) movement to child plants
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        child_start_positions: dict[QGraphicsItem, QPointF] = {}
        for item, delta in list(item_deltas):
            if not isinstance(item, GardenItemMixin) or not is_plant_parent_type(
                item.object_type
            ):
                continue
            for child_id in item.child_item_ids:
                child = self._canvas_scene.find_item_by_id(child_id)
                if child is None:
                    continue
                # Skip if child is already being dragged independently
                if child in self._drag_start_positions:
                    continue
                if child in self._constraint_propagated_starts:
                    continue
                if child in child_start_positions:
                    continue
                # Use the original position tracked during drag, not
                # child.pos() which already includes the visual offset.
                child_start_pos = self._child_drag_origins.get(child, child.pos())
                child_start_positions[child] = child_start_pos
                item_deltas.append((child, delta))

        if item_deltas:
            # Ask the LINK question where the drag left everything - the FINAL
            # positions: a bed dragged in the same gesture is at its new place, and
            # a plant that went with it keeps its bed (the old path's answer). Only
            # then reset for the move command, which re-applies the deltas.
            links = self._plant_bed_link_commands()

            # Reset all items to their start positions
            for item, start_pos in self._drag_start_positions.items():
                item.setPos(start_pos)
            for item, start_pos in self._constraint_propagated_starts.items():
                item.setPos(start_pos)
            for item, start_pos in child_start_positions.items():
                item.setPos(start_pos)

            # Use AlignItemsCommand for per-item deltas (supports undo)
            has_propagated = len(self._constraint_propagated_starts) > 0
            has_children = len(child_start_positions) > 0
            desc = (
                QCoreApplication.translate("Commands", "Move items (constrained)")
                if has_propagated
                else QCoreApplication.translate("Commands", "Move item")
            )
            if len(item_deltas) == 1 and not has_propagated and not has_children:
                # Single item, uniform delta - use simple MoveItemsCommand
                command = MoveItemsCommand([item_deltas[0][0]], item_deltas[0][1])
            else:
                command = AlignItemsCommand(item_deltas, desc)
            # A plant dragged into (or out of) a bed is linked in the SAME step:
            # two stack entries made the first Ctrl+Z undo only the link (#627).
            if links:
                from open_garden_planner.core.commands import CompoundCommand

                command = CompoundCommand([command, *links], desc)
            self._command_manager.execute(command)
        else:  # a click, not a drag: the old re-evaluation of what is selected
            self._update_plant_bed_relationships()

        self._drag_start_positions.clear()
        self._constraint_propagated_starts.clear()
        if hasattr(self, "_child_drag_origins"):
            self._child_drag_origins.clear()

    def _propagate_bed_children_during_drag(self) -> None:
        """Move child plants to follow their parent bed during a live drag."""
        if not self._drag_start_positions:
            return

        from open_garden_planner.ui.canvas.items import GardenItemMixin

        for item, start_pos in self._drag_start_positions.items():
            if not isinstance(item, GardenItemMixin) or not is_plant_parent_type(
                item.object_type
            ):
                continue
            delta = item.pos() - start_pos
            if delta.x() == 0 and delta.y() == 0:
                continue
            for child_id in item.child_item_ids:
                child = self._canvas_scene.find_item_by_id(child_id)
                if child is None or child in self._drag_start_positions:
                    continue
                # Track the child's original position only once. On the first sighting
                # it has NOT moved yet, so its position IS that origin - subtracting
                # the parent's cumulative delta made the child lag the bed by the
                # first frame's movement and put it back short on undo (#627 review).
                if child not in self._child_drag_origins:
                    self._child_drag_origins[child] = child.pos()
                child.setPos(self._child_drag_origins[child] + delta)

    def _update_plant_bed_relationships(self) -> None:
        """Re-evaluate parent-child links for all selected plants at their CURRENT
        positions (no drag in flight).

        Each change is its own undo step here; a finished drag wraps the same
        commands together with its move (``_plant_bed_link_commands`` +
        ``CompoundCommand``), so one Ctrl+Z undoes both (#627).
        """
        for command in self._plant_bed_link_commands():
            self._command_manager.execute(command)

    def _plant_bed_link_commands(self) -> list[Command]:
        """The parent links the selection's positions ask for, as commands - NOT run.

        Asked where the items ARE: a finished drag calls it before resetting them
        for its move command, so the answer is the one the drag produced - a bed
        dragged in the same gesture is at its new place, and the link commands ride
        together with the move in ONE undoable step (``CompoundCommand``).
        """
        from open_garden_planner.core.commands import SetParentBedCommand
        from open_garden_planner.core.plant_renderer import is_plant_type
        from open_garden_planner.ui.canvas.footprints import bed_membership_point
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        commands: list[Command] = []
        for item in self.scene().selectedItems():
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_plant_type(item.object_type):
                continue

            plant_center = bed_membership_point(item)
            current_parent_id = item.parent_bed_id

            new_bed = self._canvas_scene.find_smallest_bed_containing(plant_center)
            new_parent_id = (
                new_bed.item_id
                if (new_bed is not None and isinstance(new_bed, GardenItemMixin))
                else None
            )

            if new_parent_id != current_parent_id:
                commands.append(
                    SetParentBedCommand(
                        self.scene(),
                        item,
                        current_parent_id,
                        new_parent_id,
                    )
                )
        return commands

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the background."""
        super().drawBackground(painter, rect)

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the foreground including canvas border, grid overlay, and snap guides."""
        super().drawForeground(painter, rect)

        # Soil-health overlay (US-12.10b) — painted before grid/guides so the
        # grid and guide lines stay legible above the tint. Drawn at view
        # level so scene.render() (PNG/SVG/PDF/print) excludes it.
        if self._soil_overlay_visible and self._soil_service is not None:
            self._draw_soil_overlay(painter)

        # Draw canvas border
        self._draw_canvas_border(painter)

        # Draw grid overlay on top of everything
        if self._grid_visible:
            self._draw_grid(painter, rect)

        # Draw snap alignment guides
        if self._snap_guides:
            self._draw_snap_guides(painter, rect)

        # Draw the live point-snap glyph (Package A US-A3).
        if self._current_snap is not None:
            self._draw_point_snap_glyph(painter)

        # Draw persistent guide lines
        if self._guides_visible and self._canvas_scene.guide_lines:
            self._draw_guide_lines(painter, rect)

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

    def _draw_soil_overlay(self, painter: QPainter) -> None:
        """Tint each bed by the current soil-health parameter (US-12.10b).

        Beds with no effective soil test get a hatched grey fill so the
        absence of data reads visually distinct from POOR.
        """
        service = self._soil_service
        if service is None:
            return

        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)

        param = self._soil_overlay_param
        for item in self._canvas_scene.items():
            if not is_bed_type(getattr(item, "object_type", None)):
                continue
            target_id = str(getattr(item, "item_id", ""))
            if not target_id:
                continue
            record = service.get_effective_record(target_id)
            level = service.health_level(record, param)
            scene_path = item.mapToScene(item.shape())
            if level is HealthLevel.UNKNOWN:
                painter.setBrush(QBrush(QColor(140, 140, 140, 40),
                                        Qt.BrushStyle.DiagCrossPattern))
            else:
                rgba = service.overlay_rgba(level)
                if rgba is None:
                    continue
                painter.setBrush(QBrush(QColor(*rgba)))
            painter.drawPath(scene_path)

        painter.restore()

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

    def _draw_point_snap_glyph(self, painter: QPainter) -> None:
        """Render the Package A point-snap glyph at the current candidate.

        Each snap kind uses a distinct mark so users can tell which mode
        produced the snap without reading the menu.  The glyph size is
        scaled by 1/zoom so it stays at a constant on-screen size.
        """
        candidate = self._current_snap
        if candidate is None:
            return
        size = 8.0 / max(self._zoom_factor, 0.01)
        pen = QPen(QColor(0, 180, 0, 220))
        pen.setWidth(0)
        pen.setCosmetic(True)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(QColor(0, 180, 0, 90))
        cx = candidate.point.x()
        cy = candidate.point.y()
        kind = candidate.kind
        if kind == SnapCandidateKind.ENDPOINT:
            painter.drawRect(QRectF(cx - size / 2, cy - size / 2, size, size))
        elif kind == SnapCandidateKind.CENTER:
            painter.drawEllipse(QPointF(cx, cy), size / 2, size / 2)
        elif kind == SnapCandidateKind.MIDPOINT:
            from PyQt6.QtGui import QPolygonF

            tri = QPolygonF(
                [
                    QPointF(cx, cy - size / 2),
                    QPointF(cx + size / 2, cy + size / 2),
                    QPointF(cx - size / 2, cy + size / 2),
                ]
            )
            painter.drawPolygon(tri)
        elif kind == SnapCandidateKind.INTERSECTION:
            painter.drawLine(
                QPointF(cx - size / 2, cy - size / 2),
                QPointF(cx + size / 2, cy + size / 2),
            )
            painter.drawLine(
                QPointF(cx - size / 2, cy + size / 2),
                QPointF(cx + size / 2, cy - size / 2),
            )
        elif kind == SnapCandidateKind.NEAREST:
            # Hourglass — two triangles meeting at the snap point.
            from PyQt6.QtGui import QPolygonF

            top = QPolygonF(
                [
                    QPointF(cx - size / 2, cy - size / 2),
                    QPointF(cx + size / 2, cy - size / 2),
                    QPointF(cx, cy),
                ]
            )
            bot = QPolygonF(
                [
                    QPointF(cx - size / 2, cy + size / 2),
                    QPointF(cx + size / 2, cy + size / 2),
                    QPointF(cx, cy),
                ]
            )
            painter.drawPolygon(top)
            painter.drawPolygon(bot)
        elif kind == SnapCandidateKind.PERPENDICULAR:
            # ⊥ symbol — short horizontal base + vertical stem upward.
            painter.drawLine(
                QPointF(cx - size / 2, cy + size / 3),
                QPointF(cx + size / 2, cy + size / 3),
            )
            painter.drawLine(
                QPointF(cx, cy + size / 3),
                QPointF(cx, cy - size / 2),
            )
        elif kind == SnapCandidateKind.TANGENT:
            # Small circle with a horizontal tangent line above it.
            painter.drawEllipse(QPointF(cx, cy + size / 4), size / 3, size / 3)
            painter.drawLine(
                QPointF(cx - size / 2, cy - size / 2),
                QPointF(cx + size / 2, cy - size / 2),
            )
        else:  # EDGE
            painter.drawEllipse(QPointF(cx, cy), size / 3, size / 3)
        painter.restore()

    def _draw_guide_lines(self, painter: QPainter, rect: QRectF) -> None:
        """Draw persistent guide lines in scene coordinates.

        Args:
            painter: QPainter in scene coordinates.
            rect: Current visible rect.
        """
        painter.setBrush(Qt.BrushStyle.NoBrush)

        for guide in self._canvas_scene.guide_lines:
            is_hovered = guide is self._hovered_guide or guide is self._dragging_guide
            color = self._guide_highlight_color if is_hovered else self._guide_color
            pen = QPen(color)
            pen.setWidth(0)  # Cosmetic 1px
            pen.setStyle(Qt.PenStyle.SolidLine)
            painter.setPen(pen)

            if guide.is_horizontal:
                painter.drawLine(
                    QPointF(rect.left(), guide.position),
                    QPointF(rect.right(), guide.position),
                )
            else:
                painter.drawLine(
                    QPointF(guide.position, rect.top()),
                    QPointF(guide.position, rect.bottom()),
                )

    def paintEvent(self, event: QPaintEvent) -> None:
        """Paint the view, then draw overlays in viewport coordinates."""
        super().paintEvent(event)

        painter = QPainter(self.viewport())
        painter.setClipping(False)

        if self._scale_bar_visible:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self._draw_scale_bar(painter)

        if self._guides_visible:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            self._draw_rulers(painter)

        painter.end()

    # Ruler tick intervals (cm), used to pick a nice spacing based on zoom
    _RULER_NICE_INTERVALS = [
        1,
        2,
        5,
        10,
        20,
        50,
        100,
        200,
        500,
        1000,
        2000,
        5000,
        10000,
    ]
    _RULER_MIN_TICK_PX = 50  # Minimum pixels between labelled ticks
    _RULER_BG = QColor(235, 235, 235, 230)
    _RULER_FG = QColor(80, 80, 80)
    _RULER_BORDER = QColor(180, 180, 180)

    def _pick_ruler_interval(self) -> float:
        """Choose a tick interval in cm so ticks are at least _RULER_MIN_TICK_PX apart."""
        for interval in self._RULER_NICE_INTERVALS:
            if interval * self._zoom_factor >= self._RULER_MIN_TICK_PX:
                return float(interval)
        return float(self._RULER_NICE_INTERVALS[-1])

    def _draw_rulers(self, painter: QPainter) -> None:
        """Draw horizontal (top) and vertical (left) rulers in viewport coordinates.

        Args:
            painter: QPainter targeting the viewport (pixel coordinates).
        """
        import math

        rs = self.RULER_SIZE
        vp = self.viewport().rect()
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)

        interval = self._pick_ruler_interval()

        # ── Background strips ──────────────────────────────────────────────
        painter.fillRect(rs, 0, vp.width() - rs, rs, self._RULER_BG)  # top
        painter.fillRect(0, rs, rs, vp.height() - rs, self._RULER_BG)  # left
        painter.fillRect(0, 0, rs, rs, QColor(210, 210, 210, 230))  # corner box

        # ── Border lines ───────────────────────────────────────────────────
        border_pen = QPen(self._RULER_BORDER)
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.drawLine(rs, rs - 1, vp.width(), rs - 1)  # bottom of top ruler
        painter.drawLine(rs - 1, rs, rs - 1, vp.height())  # right of left ruler

        # ── Horizontal ruler (X axis) ──────────────────────────────────────
        painter.setPen(QPen(self._RULER_FG))
        # Determine scene X range visible in the ruler strip
        left_x = self.mapToScene(rs, rs // 2).x()
        right_x = self.mapToScene(vp.width(), rs // 2).x()

        first_tick = math.floor(left_x / interval) * interval
        x = first_tick
        while x <= right_x:
            vp_x = int(self.mapFromScene(x, 0).x())
            if rs <= vp_x <= vp.width():
                painter.drawLine(vp_x, rs - 4, vp_x, rs - 1)  # tick mark
                lbl = self._ruler_label(x)
                # Center label horizontally on the tick (40px box centered at vp_x)
                painter.drawText(
                    vp_x - 20,
                    0,
                    40,
                    rs - 5,
                    int(Qt.AlignmentFlag.AlignHCenter),
                    lbl,
                )
            x += interval

        # ── Vertical ruler (Y axis) ────────────────────────────────────────
        # Scene Y at top of the viewport is the LARGER value (Y-axis is flipped)
        top_y = self.mapToScene(rs // 2, rs).y()
        bottom_y = self.mapToScene(rs // 2, vp.height()).y()
        # Ensure correct iteration order (bottom_y < top_y due to Y-flip)
        y_min, y_max = min(bottom_y, top_y), max(bottom_y, top_y)

        first_tick_y = math.floor(y_min / interval) * interval
        y = first_tick_y
        while y <= y_max:
            vp_y = int(self.mapFromScene(0, y).y())
            if rs <= vp_y <= vp.height():
                painter.drawLine(rs - 4, vp_y, rs - 1, vp_y)  # tick mark
                lbl = self._ruler_label(y)
                # Draw label rotated 90° for vertical ruler.
                # After rotate(-90) at (tx, ty), screen_y_center = ty - 20 for a
                # 40px-tall rotated box.  Set ty = vp_y + 20 so the text centers on
                # the tick.  tx = 1 keeps the 15px-wide box inside the 20px ruler.
                painter.save()
                painter.translate(1, vp_y + 20)
                painter.rotate(-90)
                painter.drawText(
                    0,
                    0,
                    40,
                    rs - 5,
                    int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter),
                    lbl,
                )
                painter.restore()
            y += interval

        # ── Guide line markers on rulers ──────────────────────────────────
        guide_pen = QPen(self._guide_color)
        guide_pen.setWidth(2)
        painter.setPen(guide_pen)
        for guide in self._canvas_scene.guide_lines:
            if guide.is_horizontal:
                vp_y = int(self.mapFromScene(0, guide.position).y())
                if rs <= vp_y <= vp.height():
                    painter.drawLine(0, vp_y, rs - 1, vp_y)
            else:
                vp_x = int(self.mapFromScene(guide.position, 0).x())
                if rs <= vp_x <= vp.width():
                    painter.drawLine(vp_x, 0, vp_x, rs - 1)

    @staticmethod
    def _ruler_label(value: float) -> str:
        """Format a ruler tick label compactly (cm values)."""
        if abs(value) >= 100:
            m = value / 100
            return f"{m:g}m"
        return f"{value:g}"

    # Guide line interaction helpers

    def _guide_hit_test(self, vp_pos: QPointF, hit_px: int = 5) -> GuideLine | None:
        """Return the guide line under vp_pos (viewport coords), or None."""
        for guide in self._canvas_scene.guide_lines:
            if guide.is_horizontal:
                scene_pt = self.mapFromScene(0, guide.position)
                if abs(scene_pt.y() - vp_pos.y()) <= hit_px:
                    return guide
            else:
                scene_pt = self.mapFromScene(guide.position, 0)
                if abs(scene_pt.x() - vp_pos.x()) <= hit_px:
                    return guide
        return None

    def _edit_guide_position(self, guide: GuideLine) -> None:
        """Show input dialog to set guide position numerically."""
        axis = self.tr("Y") if guide.is_horizontal else self.tr("X")
        label = self.tr("{axis} position (cm)").format(axis=axis)
        value, ok = QInputDialog.getDouble(
            self,
            self.tr("Guide position"),
            label,
            guide.position,
            -1_000_000.0,
            1_000_000.0,
            2,
        )
        if ok:
            guide.position = value
            self.scene().update()
            self.viewport().update()

    # Scale bar constants
    _SCALE_BAR_NICE_DISTANCES = [
        1,
        2,
        5,
        10,
        20,
        50,
        100,
        200,
        500,
        1000,
        2000,
        5000,
        10000,
    ]
    _SCALE_BAR_MARGIN = 12
    _SCALE_BAR_TICK_H = 5
    _SCALE_BAR_LINE_WIDTH = 2
    # Total vertical space reserved at viewport bottom for the scale bar
    # (margin + tick + gap + ~8pt text). Used by overlay widgets for clearance.
    SCALE_BAR_RESERVED_PX: int = 40

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
            int(bar_x),
            int(bar_y),
            int(bar_x + bar_width_px),
            int(bar_y),
        )
        # Outline: left tick
        painter.drawLine(
            int(bar_x),
            int(bar_y),
            int(bar_x),
            int(bar_y - tick_h),
        )
        # Outline: right tick
        painter.drawLine(
            int(bar_x + bar_width_px),
            int(bar_y),
            int(bar_x + bar_width_px),
            int(bar_y - tick_h),
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
            int(bar_x),
            int(bar_y),
            int(bar_x + bar_width_px),
            int(bar_y),
        )
        # Foreground: left tick
        painter.drawLine(
            int(bar_x),
            int(bar_y),
            int(bar_x),
            int(bar_y - tick_h),
        )
        # Foreground: right tick
        painter.drawLine(
            int(bar_x + bar_width_px),
            int(bar_y),
            int(bar_x + bar_width_px),
            int(bar_y - tick_h),
        )

        # Foreground: text
        painter.setPen(fg_color)
        painter.drawText(int(text_x), int(text_y), label)

    # ------------------------------------------------------------------
    # Group / Ungroup
    # ------------------------------------------------------------------

    def _group_selected(self) -> None:
        """Group all currently selected items (Ctrl+G)."""
        from open_garden_planner.core.commands import GroupCommand
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        selected = [
            item
            for item in self.scene().selectedItems()
            if not isinstance(item, GroupItem) or item.parentItem() is None
        ]
        # Need at least 2 items (or 1 group child) — sensible minimum is 2
        if len(selected) < 2:
            self.set_status_message(self.tr("Select 2 or more items to group"))
            return

        command = GroupCommand(self.scene(), selected)
        self._command_manager.execute(command)
        self.set_status_message(self.tr("Grouped {n} items").format(n=len(selected)))

    def _ungroup_selected(self) -> None:
        """Ungroup all selected GroupItems (Ctrl+Shift+G)."""
        from open_garden_planner.ui.canvas.items.group_item import GroupItem

        groups = [
            item for item in self.scene().selectedItems() if isinstance(item, GroupItem)
        ]
        if not groups:
            self.set_status_message(self.tr("No group selected"))
            return
        for group in groups:
            self.ungroup_item(group)

    def ungroup_item(self, group: QGraphicsItem) -> None:
        """Ungroup a specific GroupItem."""
        from open_garden_planner.core.commands import UngroupCommand

        command = UngroupCommand(self.scene(), group)
        self._command_manager.execute(command)
        self.set_status_message(self.tr("Ungrouped"))

    def copy_selected(self) -> None:
        return self._clipboard_operations.copy_selected()

    def cut_selected(self) -> None:
        return self._clipboard_operations.cut_selected()

    def paste(self) -> None:
        return self._clipboard_operations.paste()

    def duplicate_selected(self) -> None:
        return self._clipboard_operations.duplicate_selected()

    def create_linear_array(self) -> None:
        return self._clipboard_operations.create_linear_array()

    def create_grid_array(self) -> None:
        return self._clipboard_operations.create_grid_array()

    def create_circular_array(self) -> None:
        return self._clipboard_operations.create_circular_array()

    def boolean_operation(self, operation: str) -> None:
        """Apply union (any count) or intersect/subtract (exactly two) shapes.

        Union also accepts shapes that merely touch: a fence line of three beds
        laid edge to edge is the ordinary case. Intersection and subtraction
        keep requiring a real overlap because their result is ambiguous for a
        contact-only pair (#550).
        """
        from copy import deepcopy

        from PyQt6.QtGui import QColor, QPen
        from PyQt6.QtWidgets import QMessageBox

        from open_garden_planner.core.item_look import copy_visual_style
        from open_garden_planner.core.object_types import (
            get_valid_types_for_shape,
            is_plant_type,
        )
        from open_garden_planner.core.shape_boolean import (
            all_paths_connected,
            boolean_intersect,
            boolean_subtract,
            item_to_painter_path,
            path_has_hole,
            paths_overlap,
            union_outline_many,
        )
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        from open_garden_planner.ui.canvas.items.polygon_item import (
            MAX_POLYGON_VERTICES,
            PolygonItem,
        )

        if operation not in ("union", "intersect", "subtract"):
            return

        selected = self.scene().selectedItems()
        if len(selected) < 2 or (operation != "union" and len(selected) != 2):
            self.set_status_message(
                self.tr(
                    "Select at least two shapes "
                    "(intersection and subtraction need exactly two)"
                )
            )
            return

        # Refuse before anything is mutated. A linked subject would lose its
        # botanical identity, a constrained one would silently break the
        # relation, and a sprite's picture cannot survive flattening to a
        # polygon.
        for item in selected:
            if not isinstance(item, GardenItemMixin):
                continue
            layer = (
                self._canvas_scene.get_layer_by_id(item.layer_id)
                if item.layer_id
                else None
            )
            constraints = (
                self._canvas_scene.constraint_graph.get_item_constraints(item.item_id)
                if item.item_id is not None
                else []
            )
            if (
                is_plant_type(item.object_type)
                or item.paints_sprite
                or item.parent_bed_id is not None
                or item.has_children
                or item.parentItem() is not None
                or constraints
                or (layer is not None and layer.locked)
                or any(
                    key in item.metadata
                    for key in ("plant_species", "guild", "ridge_item_id")
                )
            ):
                self.set_status_message(
                    self.tr(
                        "Boolean operations refuse plants, linked objects, "
                        "constraints, and locked layers"
                    )
                )
                return

        # A union produces ONE item, so every subject must already agree on the
        # layer it will live on. Picking one arbitrarily (Qt does not define
        # selectedItems() order) would move objects across layers unannounced.
        # After the per-item refusals, so a plant on another layer reports the
        # more specific reason.
        layer_ids = {
            getattr(item, "layer_id", None)
            for item in selected
            if isinstance(item, GardenItemMixin)
        }
        if len(layer_ids) > 1:
            self.set_status_message(
                self.tr("All shapes must be on the same layer")
            )
            return

        # Whose opaque data wins when two subjects disagree is a product
        # decision; refuse rather than silently pick one.
        payloads = [
            item.metadata
            for item in selected
            if isinstance(item, GardenItemMixin) and item.metadata
        ]
        if payloads and any(payload != payloads[0] for payload in payloads[1:]):
            self.set_status_message(
                self.tr(
                    "The shapes contain different data; keep them separate or "
                    "make their data consistent"
                )
            )
            return

        paths = [item_to_painter_path(item) for item in selected]
        if any(path is None for path in paths):
            self.set_status_message(
                self.tr(
                    "Boolean operations require closed shapes "
                    "(polygon, rectangle, circle, or ellipse)"
                )
            )
            return
        checked_paths = [path for path in paths if path is not None]

        if operation == "union":
            if not all_paths_connected(checked_paths):
                self.set_status_message(
                    self.tr("Shapes must touch or overlap")
                )
                return
            # ONE union pass: its contour answers the hole test and its
            # flattened polygon is the result (#550 review).
            union = union_outline_many(checked_paths)
            if union is not None:
                result_path, result_poly = union
                if path_has_hole(result_path):
                    self.set_status_message(
                        self.tr(
                            "The merged outline would contain a hole; "
                            "keep the shapes separate"
                        )
                    )
                    return
            else:
                result_poly = None
        else:
            if not paths_overlap(checked_paths[0], checked_paths[1]):
                self.set_status_message(
                    self.tr("Shapes must overlap for this operation")
                )
                return
            if operation == "intersect":
                result_poly = boolean_intersect(checked_paths[0], checked_paths[1])
            else:
                result_poly = boolean_subtract(checked_paths[0], checked_paths[1])

        if result_poly is None:
            self.set_status_message(
                self.tr("Boolean {op} produced an empty result").format(op=operation)
            )
            return

        # A flattening can multiply the vertex count of curved inputs; the plan
        # loader refuses a polygon above MAX_POLYGON_VERTICES, so an over-cap
        # result would be created, saved and then silently dropped on reopen.
        # Refuse it here, where the user can still split the selection (#550).
        if result_poly.count() > MAX_POLYGON_VERTICES:
            self.set_status_message(
                self.tr(
                    "The result would have {count} vertices; the plan supports "
                    "at most {limit}. Keep the shapes separate."
                ).format(count=result_poly.count(), limit=MAX_POLYGON_VERTICES)
            )
            return

        # Preview
        from PyQt6.QtWidgets import QGraphicsPolygonItem as QGPolyItem

        preview = QGPolyItem(result_poly)
        preview.setPen(QPen(QColor(60, 130, 200), 2.0, Qt.PenStyle.DashLine))
        preview.setBrush(QColor(60, 130, 200, 50))
        preview.setZValue(9999)
        self.scene().addItem(preview)

        answer = QMessageBox.question(
            self,
            self.tr("Boolean {op}").format(op=operation.capitalize()),
            self.tr("Apply boolean {op}?").format(op=operation),
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
        )

        self.scene().removeItem(preview)

        if answer != QMessageBox.StandardButton.Ok:
            return

        # Carry the source's appearance through the one look-copy path and its
        # opaque metadata through a copy, so the result survives save/reopen.
        result_item = PolygonItem.from_polygon(result_poly)
        source = next(
            (
                item
                for item in selected
                if isinstance(item, GardenItemMixin) and item.metadata
            ),
            selected[0],
        )
        if isinstance(source, GardenItemMixin):
            if source.object_type in get_valid_types_for_shape("polygon"):
                result_item.object_type = source.object_type
            result_item.name = source.name
            result_item.layer_id = source.layer_id
            result_item.metadata.update(deepcopy(source.metadata))
            copy_visual_style(source, result_item)
            result_item.update()

        from open_garden_planner.core import BooleanShapeCommand

        command = BooleanShapeCommand(
            self.scene(),
            selected[0],
            selected[1],
            result_item,
            operation,
            additional_items=selected[2:],
        )
        self._command_manager.execute(command)

        result_item.setSelected(True)
        self.set_status_message(self.tr("Applied boolean {op}").format(op=operation))

    def create_array_along_path(self) -> None:
        return self._clipboard_operations.create_array_along_path()

    def _serialize_item(self, item: QGraphicsItem) -> dict | None:
        return self._clipboard_operations._serialize_item(item)

    def _restore_layer_id(self, item: QGraphicsItem, obj: dict) -> None:
        return self._clipboard_operations._restore_layer_id(item, obj)

    def _serialize_item_core(self, item: QGraphicsItem) -> dict | None:
        return self._clipboard_operations._serialize_item_core(item)

    def _remap_guild_copy(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._clipboard_operations._remap_guild_copy(records)

    def _deserialize_item(self, obj: dict) -> QGraphicsItem | None:
        return self._clipboard_operations._deserialize_item(obj)

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
            self.set_status_message(
                self.tr("Invalid distance. Enter a number in centimeters.")
            )

    def _clamp_individual_deltas(
        self,
        item_deltas: list[tuple[QGraphicsItem, QPointF]],
    ) -> list[tuple[QGraphicsItem, QPointF]]:
        """Clamp per-item deltas so each item stays inside the canvas.

        Uses the same shared math as ``_clamp_delta_to_canvas`` so the two GUI
        paths and the agent path cannot drift (issue #380; review P2-1).

        Args:
            item_deltas: List of (item, delta) tuples.

        Returns:
            Clamped list of (item, delta) tuples.
        """
        from open_garden_planner.core.canvas_bounds import clamp_delta_within_canvas

        canvas = self._canvas_scene.canvas_rect
        result: list[tuple[QGraphicsItem, QPointF]] = []
        for item, delta in item_deltas:
            rect = item.sceneBoundingRect()
            dx, dy = clamp_delta_within_canvas(
                [(rect.left(), rect.top(), rect.right(), rect.bottom())],
                delta.x(),
                delta.y(),
                canvas.width(),
                canvas.height(),
            )
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

        align_labels = {
            "LEFT": QCoreApplication.translate("Commands", "Align left"),
            "RIGHT": QCoreApplication.translate("Commands", "Align right"),
            "TOP": QCoreApplication.translate("Commands", "Align top"),
            "BOTTOM": QCoreApplication.translate("Commands", "Align bottom"),
            "CENTER_H": QCoreApplication.translate("Commands", "Align center horizontally"),
            "CENTER_V": QCoreApplication.translate("Commands", "Align center vertically"),
        }
        desc = align_labels.get(
            mode.name, QCoreApplication.translate("Commands", "Align items")
        )
        command = AlignItemsCommand(non_zero, desc)
        self._command_manager.execute(command)
        self.set_status_message(desc)

    def arrange_selected(self, mode: ArrangeMode) -> None:
        """Arrange the selected items' stacking order within their layer(s).

        Args:
            mode: Which of the four arrange gestures to perform (bring to
                front/forward, send backward/to back).
        """
        from open_garden_planner.ui.canvas.arrange import build_arrange_command

        selected = self.scene().selectedItems()
        command, outcome = build_arrange_command(self.scene(), selected, mode)
        if command is None:
            messages = {
                ArrangeOutcome.NOTHING_SELECTED: self.tr("Select an object to arrange"),
                ArrangeOutcome.ALREADY_AT_FRONT: self.tr("Already at front"),
                ArrangeOutcome.ALREADY_AT_BACK: self.tr("Already at back"),
                ArrangeOutcome.NO_OVERLAP_ABOVE: self.tr("No overlapping object in front"),
                ArrangeOutcome.NO_OVERLAP_BELOW: self.tr("No overlapping object behind"),
            }
            self.set_status_message(
                messages.get(outcome, self.tr("Select an object to arrange"))
            )
            return

        self._command_manager.execute(command)
        self.set_status_message(command.description)

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

        distribute_labels = {
            "HORIZONTAL": QCoreApplication.translate("Commands", "Distribute horizontally"),
            "VERTICAL": QCoreApplication.translate("Commands", "Distribute vertically"),
        }
        desc = distribute_labels.get(
            mode.name, QCoreApplication.translate("Commands", "Distribute items")
        )
        command = AlignItemsCommand(non_zero, desc)
        self._command_manager.execute(command)
        self.set_status_message(desc)

    def set_status_message(self, message: str) -> None:
        """Ask the main window to show ``message`` in its status bar.

        Routes through the :attr:`status_message` signal, which
        ``GardenPlannerApp`` connects to ``QMainWindow.statusBar()``. It used to
        reach for ``self.parent().statusBar()`` instead, which never resolved in
        the production layout (the parent is a ``QSplitter``), so this call was a
        silent no-op for every caller — see the signal's docstring.

        Args:
            message: The status message to display.
        """
        self.status_message.emit(message)
