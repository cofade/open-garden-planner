"""Vertex, midpoint and curve editing handles; public imports remain compatible."""
import math
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, cast

from PyQt6.QtCore import QCoreApplication, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsSceneContextMenuEvent,
    QGraphicsSceneHoverEvent,
    QGraphicsSceneMouseEvent,
    QMenu,
)

from .garden_item import PositionLockMixin

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QGraphicsItem as ParentItem


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


def _shift_constraint_indices_after_insert(item: Any, insert_index: int) -> None:
    """Shift constraint anchor indices on ``item`` after a vertex is inserted.

    Without this, an edge-length / angle constraint silently retargets a
    different vertex once an earlier vertex is added — the visible symptom is
    geometry suddenly snapping to the wrong place on the next solver pass.
    """
    scene = item.scene() if hasattr(item, "scene") else None
    item_id = getattr(item, "item_id", None)
    if scene is None or item_id is None or not hasattr(scene, "constraint_graph"):
        return
    scene.constraint_graph.shift_vertex_indices(item_id, insert_index, +1)


def _shift_constraint_indices_after_delete(item: Any, deleted_index: int) -> None:
    """Drop constraints on the deleted vertex, then shift higher indices down."""
    scene = item.scene() if hasattr(item, "scene") else None
    item_id = getattr(item, "item_id", None)
    if scene is None or item_id is None or not hasattr(scene, "constraint_graph"):
        return
    graph = scene.constraint_graph
    graph.remove_vertex_constraints(item_id, deleted_index)
    graph.shift_vertex_indices(item_id, deleted_index + 1, -1)


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
        self.setZValue(10_002)  # Above rotation and resize handles

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

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Highlight handle on hover."""
        if event is None:
            return
        self.setBrush(QBrush(VERTEX_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Remove highlight when hover ends."""
        if event is None:
            return
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Start vertex drag operation."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial vertex position
            if self._parent_item is not None and hasattr(self._parent_item, '_get_vertex_position'):
                self._initial_vertex_pos = self._parent_item._get_vertex_position(self._vertex_index)

            self.grabMouse()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Handle vertex movement during drag."""
        if event is None:
            return
        if not self._is_dragging or self._parent_item is None:
            super().mouseMoveEvent(event)
            return

        # Get new position in parent item coordinates, clamped to canvas
        scene_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)

        # Live constraint projection: if any constraint touches this vertex,
        # snap the cursor target to the closest feasible point before painting.
        scene = self._parent_item.scene()
        if scene is not None and hasattr(scene, "project_vertex_drag"):
            scene_pos = scene.project_vertex_drag(
                self._parent_item, self._vertex_index, scene_pos
            )

        parent_pos = self._parent_item.mapFromScene(scene_pos)

        # Apply the vertex move
        if hasattr(self._parent_item, '_move_vertex_to'):
            self._parent_item._move_vertex_to(self._vertex_index, parent_pos)

        _announce_live_edit(self._parent_item)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Complete vertex drag operation."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self.ungrabMouse()
            self._is_dragging = False

            # Register undo command
            if (self._parent_item is not None and
                self._initial_vertex_pos is not None and
                hasattr(self._parent_item, '_on_vertex_move_end')):
                current_pos = cast(Any, self._parent_item)._get_vertex_position(self._vertex_index)
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

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        """Show context menu for vertex operations."""
        if event is None:
            return
        if self._parent_item is None:
            return

        # Polylines are open (no wrap-around): insert-before disabled at v0,
        # insert-after disabled at the last vertex. Polygons wrap.
        from open_garden_planner.ui.canvas.items import PolylineItem
        is_polyline = isinstance(self._parent_item, PolylineItem)
        vertex_count = (
            self._parent_item._get_vertex_count()
            if hasattr(self._parent_item, '_get_vertex_count')
            else 0
        )
        can_insert_before = (not is_polyline) or self._vertex_index > 0
        can_insert_after = (not is_polyline) or self._vertex_index < vertex_count - 1

        # Check if we can delete (need minimum vertices - parent defines minimum)
        can_delete = True
        if hasattr(self._parent_item, '_get_vertex_count'):
            min_count = MINIMUM_VERTICES
            if hasattr(self._parent_item, '_get_minimum_vertex_count'):
                min_count = self._parent_item._get_minimum_vertex_count()
            can_delete = vertex_count > min_count

        _ = QCoreApplication.translate
        menu = QMenu()

        insert_before_action = menu.addAction(_("VertexHandle", "Insert Vertex Before"))
        cast(Any, insert_before_action).setEnabled(can_insert_before)
        insert_after_action = menu.addAction(_("VertexHandle", "Insert Vertex After"))
        cast(Any, insert_after_action).setEnabled(can_insert_after)
        menu.addSeparator()
        delete_action = menu.addAction(_("VertexHandle", "Delete Vertex"))
        cast(Any, delete_action).setEnabled(can_delete)
        if not can_delete:
            min_count = MINIMUM_VERTICES
            if hasattr(self._parent_item, '_get_minimum_vertex_count'):
                min_count = self._parent_item._get_minimum_vertex_count()
            cast(Any, delete_action).setToolTip(f"Cannot delete: minimum {min_count} vertices required")

        action = menu.exec(event.screenPos())

        if action is None:
            event.accept()
            return

        if (action == delete_action and can_delete
                and hasattr(self._parent_item, '_delete_vertex')):
            self._parent_item._delete_vertex(self._vertex_index)
        elif (action == insert_before_action and can_insert_before
                and hasattr(self._parent_item, '_add_vertex_at_edge')
                and hasattr(self._parent_item, '_get_vertex_position')):
            # Edge before this vertex starts at (vertex_index - 1) for both
            # polygons and polylines; polygons wrap so v0's "before" is the
            # last edge.
            prev_idx = (self._vertex_index - 1) % vertex_count
            p1 = self._parent_item._get_vertex_position(prev_idx)
            p2 = self._parent_item._get_vertex_position(self._vertex_index)
            midpoint = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
            self._parent_item._add_vertex_at_edge(prev_idx, midpoint)
        elif (action == insert_after_action and can_insert_after
                and hasattr(self._parent_item, '_add_vertex_at_edge')
                and hasattr(self._parent_item, '_get_vertex_position')):
            next_idx = (self._vertex_index + 1) % vertex_count
            p1 = self._parent_item._get_vertex_position(self._vertex_index)
            p2 = self._parent_item._get_vertex_position(next_idx)
            midpoint = QPointF((p1.x() + p2.x()) / 2.0, (p1.y() + p2.y()) / 2.0)
            self._parent_item._add_vertex_at_edge(self._vertex_index, midpoint)

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

        self.setToolTip(
            QCoreApplication.translate("MidpointHandle", "Click to add a vertex")
        )

    def _setup_flags(self) -> None:
        """Configure interaction flags."""
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setZValue(10_001)  # Below vertex handles

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

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Highlight handle on hover."""
        if event is None:
            return
        self.setBrush(QBrush(MIDPOINT_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Remove highlight when hover ends."""
        if event is None:
            return
        self.setBrush(QBrush(MIDPOINT_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Add a new vertex at this midpoint position."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._parent_item is not None and hasattr(self._parent_item, '_add_vertex_at_edge'):
                # Get the current position (midpoint of the edge)
                pos = self.pos()
                # Insert new vertex after the edge start vertex
                self._parent_item._add_vertex_at_edge(self._edge_index, pos)

            event.accept()
        else:
            super().mousePressEvent(event)

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent | None) -> None:
        """Right-click menu mirrors the left-click action for discoverability."""
        if event is None:
            return
        if self._parent_item is None or not hasattr(self._parent_item, '_add_vertex_at_edge'):
            event.ignore()
            return
        _ = QCoreApplication.translate
        menu = QMenu()
        add_action = menu.addAction(_("MidpointHandle", "Add Vertex Here"))
        action = menu.exec(event.screenPos())
        if action == add_action:
            self._parent_item._add_vertex_at_edge(self._edge_index, self.pos())
        event.accept()


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


# Generated curved outlines (a boolean union of a rectangle and circles, for
# example) carry hundreds of tessellation points. Above this many vertices the
# overlay shows a bounded, pixel-spaced sample of handles and moves the
# coordinate / edge-length text into tooltips (#551). The model keeps every
# vertex; only the on-screen affordances are thinned.
MAX_ANNOTATED_VERTICES = 24
MAX_DENSE_VERTEX_HANDLES = 128
DENSE_HANDLE_SPACING_PX = 24.0


def _visible_viewport_rect(view: Any, margin: float) -> QRectF:
    """The view's viewport in VIEWPORT (logical) pixels, grown by *margin*.

    ``deviceTransform`` is ``sceneTransform * viewportTransform`` on this Qt
    (6.11): it does NOT apply the device-pixel ratio, so both sides of the
    comparison are viewport pixels. Scaling this rect by the DPR (the first
    version of this helper did) samples up to a whole viewport beyond the edge
    on a high-DPI screen (senior review of PR #585, round 5).
    """
    return QRectF(view.viewport().rect()).adjusted(-margin, -margin, margin, margin)


def _dense_sample_view(item: Any) -> Any | None:
    """The first view of *item*'s scene, or None (a bare scene in a unit test)."""
    scene = item.scene()
    views = scene.views() if scene is not None else []
    return views[0] if views else None


def _visible_scene_rect(view: Any | None) -> QRectF | None:
    """The viewport in SCENE coordinates, or None without a viewport."""
    if view is None or view.viewport() is None:
        return None
    return cast(QRectF | None, view.mapToScene(view.viewport().rect()).boundingRect())


def _dense_candidate_scene_rect(view: Any | None) -> QRectF | None:
    """The scene region the dense sampler actually tests candidates inside.

    ``_dense_overlay_indices`` tests ``_visible_viewport_rect(view,
    DENSE_HANDLE_SPACING_PX)`` — the viewport grown by 24 VIEWPORT pixels — not
    the whole scene. This is that same region in scene coordinates: a pan that
    keeps the new viewport inside it reuses the sample correctly, and anything
    larger must re-sample (#594, senior review).
    """
    if view is None or view.viewport() is None:
        return None
    visible = _visible_viewport_rect(view, DENSE_HANDLE_SPACING_PX).toAlignedRect()
    return cast(QRectF | None, view.mapToScene(visible).boundingRect())


def _dense_sample_pose(item: Any) -> tuple[float, ...]:
    """The full scene transform the sample's candidate set was taken at (#594).

    ``sceneTransform`` includes position, rotation, scale, ``transformOriginPoint``
    and the parent chain — every pose change that can move a vertex on screen,
    including a group child whose own ``pos``/``rotation``/``scale`` do not move.
    """
    transform = item.sceneTransform()
    return (
        transform.m11(), transform.m12(), transform.m21(), transform.m22(),
        transform.dx(), transform.dy(),
    )


def _dense_sample_covers_view(item: Any) -> bool:
    """Whether the last dense sample already covers the current viewport (#594).

    The sample's candidate set was the viewport grown by
    ``DENSE_HANDLE_SPACING_PX``. If the new viewport lies inside that same scene
    region and the item has not moved, every vertex now visible was a candidate
    when the sample was taken. A pan only translates the points, so the chosen
    indices keep their pairwise screen spacing; the sample is still valid.
    Re-sampling every scrollbar step is what cost ~100 ms on a 16 384-vertex
    outline.
    """
    cached = getattr(item, "_dense_sample_scene_rect", None)
    sampled_zoom = getattr(item, "_dense_sample_zoom", None)
    sampled_pose = getattr(item, "_dense_sample_pose", None)
    view = _dense_sample_view(item)
    if cached is None or sampled_zoom is None or sampled_pose is None or view is None:
        return False
    if abs(sampled_zoom - abs(view.transform().m11())) > 1e-9:
        return False
    if sampled_pose != _dense_sample_pose(item):
        return False
    current = _visible_scene_rect(view)
    return current is not None and cached.contains(current)


def _remember_dense_sample(item: Any) -> None:
    """Record the scene region the current dense sample actually covered."""
    view = _dense_sample_view(item)
    candidate = _dense_candidate_scene_rect(view)
    if view is None or candidate is None:
        return
    item._dense_sample_scene_rect = candidate
    item._dense_sample_zoom = abs(view.transform().m11())
    item._dense_sample_pose = _dense_sample_pose(item)


def _forget_dense_sample(item: Any) -> None:
    """Drop the sample cache (a non-dense outline, a geometry/pose change, or leaving edit mode)."""
    item._dense_sample_scene_rect = None
    item._dense_sample_zoom = None
    item._dense_sample_pose = None


def _dense_overlay_indices(
    item: Any, points: list[tuple[int, QPointF]]
) -> list[int]:
    """Original indices of a pixel-spaced sample of ``points`` (#551).

    Points are mapped through the first view's device transform, so zooming in
    reveals more vertices and zooming out hides more rather than turning the
    outline into one overlapping pile. A vertex that is currently being dragged
    is kept by :meth:`VertexEditMixin.refresh_vertex_edit_overlay`, which never
    calls this while a handle is down.
    """
    scene = item.scene()
    views = scene.views() if scene is not None else []
    if not views:
        step = max(1, math.ceil(len(points) / MAX_DENSE_VERTEX_HANDLES))
        return [index for index, _point in points[::step]][:MAX_DENSE_VERTEX_HANDLES]
    view = views[0]
    transform = item.deviceTransform(view.viewportTransform())
    visible = _visible_viewport_rect(view, DENSE_HANDLE_SPACING_PX)
    spacing = DENSE_HANDLE_SPACING_PX
    cells: dict[tuple[int, int], list[QPointF]] = {}
    indices: list[int] = []
    for index, local_point in points:
        point = transform.map(local_point)
        if not visible.contains(point):
            continue
        cell = (math.floor(point.x() / spacing), math.floor(point.y() / spacing))
        if any(
            _edge_length(point, previous) < spacing
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for previous in cells.get((cell[0] + dx, cell[1] + dy), [])
        ):
            continue
        cells.setdefault(cell, []).append(point)
        indices.append(index)
        if len(indices) >= MAX_DENSE_VERTEX_HANDLES:
            break
    return indices


def _visible_vertex_indices(
    item: Any, points: list[QPointF]
) -> list[int]:
    """All vertex indices for an ordinary outline, a current pixel sample for a dense one."""
    indexed = list(enumerate(points))
    if len(indexed) <= MAX_ANNOTATED_VERTICES:
        return [index for index, _point in indexed]
    return _dense_overlay_indices(item, indexed)


def _map_to_scene(item: Any, point: QPointF) -> QPointF:
    """``item.mapToScene`` for a mixin mypy cannot see as a QGraphicsItem."""
    return cast(QPointF, item.mapToScene(point))


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

        # Prevent accidental whole-item drag while editing individual vertices
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Hide resize and rotation handles if they exist
        if hasattr(self, 'hide_resize_handles'):
            self.hide_resize_handles()
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()

        # Create vertex and midpoint handles + annotations
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide vertex handles."""
        if not self._is_vertex_edit_mode:
            return

        self._is_vertex_edit_mode = False

        # Restore whole-item movability
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Remove vertex and midpoint handles + annotations
        self._remove_vertex_handles()
        self._remove_midpoint_handles()
        self._remove_annotations()
        _forget_dense_sample(self)

        # Show resize and rotation handles if selected
        if hasattr(self, 'isSelected') and self.isSelected():
            if hasattr(self, 'show_resize_handles'):
                self.show_resize_handles()
            if hasattr(self, 'show_rotation_handle'):
                self.show_rotation_handle()

    def _create_vertex_handles(self) -> None:
        """Create handles for all vertices, sampled when the outline is dense."""
        self._remove_vertex_handles()

        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()
        dense = polygon.count() > MAX_ANNOTATED_VERTICES
        for i in _visible_vertex_indices(self, [polygon.at(j) for j in range(polygon.count())]):
            handle = VertexHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(polygon.at(i))
            if dense:
                point = _map_to_scene(self, polygon.at(i))
                handle.setToolTip(_format_coordinate(point.x(), point.y()))
            self._vertex_handles.append(handle)
        if dense:
            _remember_dense_sample(self)
        else:
            _forget_dense_sample(self)

    def _remove_vertex_handles(self) -> None:
        """Remove all vertex handles."""
        for handle in self._vertex_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._vertex_handles = []

    def _create_midpoint_handles(self) -> None:
        """Create handles at edge midpoints, sampled when the outline is dense."""
        self._remove_midpoint_handles()

        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()
        count = polygon.count()
        dense = count > MAX_ANNOTATED_VERTICES
        owner = cast(Any, self)
        scene = owner.scene()
        transform = None
        if dense and scene is not None and scene.views():
            viewport = scene.views()[0].viewport()
            if viewport is not None:
                transform = owner.deviceTransform(scene.views()[0].viewportTransform())
        candidates: list[tuple[int, QPointF]] = []
        for i in range(count):
            p1 = polygon.at(i)
            p2 = polygon.at((i + 1) % count)
            if (
                transform is not None
                and _edge_length(transform.map(p1), transform.map(p2))
                < 2 * DENSE_HANDLE_SPACING_PX
            ):
                continue
            candidates.append((i, QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)))

        indices = (
            _dense_overlay_indices(self, candidates)
            if dense
            else [index for index, _point in candidates]
        )
        by_index = dict(candidates)
        for i in indices:
            handle = MidpointHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(by_index[i])
            if dense:
                p1 = polygon.at(i)
                p2 = polygon.at((i + 1) % count)
                handle.setToolTip(
                    _format_edge_length(
                        _edge_length(_map_to_scene(self, p1), _map_to_scene(self, p2))
                    )
                )
            self._midpoint_handles.append(handle)

    def _remove_midpoint_handles(self) -> None:
        """Remove all midpoint handles."""
        for handle in self._midpoint_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._midpoint_handles = []

    def refresh_vertex_edit_overlay(self) -> None:
        """Re-sample a dense outline after a zoom or pan; never during a drag.

        A pan that stays inside the sampled scene region does not re-sample
        (#594): every now-visible vertex was already a candidate, and translation
        keeps the chosen indices' pairwise screen spacing. A zoom, or a pan beyond
        the region, samples again.
        """
        if not getattr(self, "_is_vertex_edit_mode", False):
            return
        if self._get_vertex_count() <= MAX_ANNOTATED_VERTICES:
            return
        if any(
            getattr(handle, "_is_dragging", False)
            for handle in [*self._vertex_handles, *self._midpoint_handles]
        ):
            return
        if _dense_sample_covers_view(self):
            return
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._remove_annotations()

    def _update_vertex_handles(self) -> None:
        """Update positions of all vertex and midpoint handles and annotations."""
        if not hasattr(self, 'polygon'):
            return

        polygon = self.polygon()
        count = polygon.count()
        dense = count > MAX_ANNOTATED_VERTICES

        # Update vertex handles (a dense outline holds only a sample)
        for vertex_handle in self._vertex_handles:
            i = vertex_handle.vertex_index
            if i < count:
                vertex_handle.update_position(polygon.at(i))
                if dense:
                    point = _map_to_scene(self, polygon.at(i))
                    vertex_handle.setToolTip(_format_coordinate(point.x(), point.y()))

        # Update midpoint handles
        for midpoint_handle in self._midpoint_handles:
            i = midpoint_handle.edge_index
            if i < count:
                p1 = polygon.at(i)
                p2 = polygon.at((i + 1) % count)
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                midpoint_handle.update_position(midpoint)
                if dense:
                    midpoint_handle.setToolTip(
                        _format_edge_length(
                            _edge_length(_map_to_scene(self, p1), _map_to_scene(self, p2))
                        )
                    )

        # Update annotations
        self._update_annotations()
        # A geometry change invalidates the candidate set's pose/positions (#594).
        _forget_dense_sample(self)

    def _create_annotations(self) -> None:
        """Create coordinate and edge length annotations."""
        self._remove_annotations()

        if not hasattr(self, 'polygon') or not hasattr(self, 'mapToScene'):
            return

        polygon = self.polygon()
        count = polygon.count()
        if count > MAX_ANNOTATED_VERTICES:
            return  # Dense outlines use handle tooltips instead of overlapping labels.

        # Create coordinate labels at each vertex
        for i in range(count):
            point = polygon.at(i)
            scene_pt = self.mapToScene(point)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(point.x(), point.y())
            self._coord_labels.append(label)

        # Create edge length labels at each edge midpoint
        for i in range(count):
            p1 = polygon.at(i)
            p2 = polygon.at((i + 1) % count)
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)
            scene_p2 = self.mapToScene(p2)
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._edge_labels.append(label)

    def _remove_annotations(self) -> None:
        """Remove all annotation labels."""
        for label in self._coord_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._coord_labels = []

        for label in self._edge_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._edge_labels = []

    def _update_annotations(self) -> None:
        """Update annotation text and positions."""
        if not hasattr(self, 'polygon') or not hasattr(self, 'mapToScene'):
            return

        polygon = self.polygon()
        count = polygon.count()
        if count > MAX_ANNOTATED_VERTICES:
            return  # No labels exist for a dense outline; see _create_annotations.

        # Update coordinate labels
        for i, label in enumerate(self._coord_labels):
            if i < count:
                point = polygon.at(i)
                scene_pt = self.mapToScene(point)
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(point.x(), point.y())

        # Update edge length labels
        for i, label in enumerate(self._edge_labels):
            if i < count:
                p1 = polygon.at(i)
                p2 = polygon.at((i + 1) % count)
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)
                scene_p2 = self.mapToScene(p2)
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

        polygon = self.polygon()
        if 0 <= index < polygon.count():
            return cast(QPointF, polygon.at(index))
        return QPointF(0, 0)

    def _get_vertex_count(self) -> int:
        """Get the number of vertices in the polygon.

        Returns:
            Number of vertices
        """
        if not hasattr(self, 'polygon'):
            return 0

        return cast(int, self.polygon().count())

    def _get_minimum_vertex_count(self) -> int:
        """Get the minimum number of vertices allowed (3 for polygons)."""
        return MINIMUM_VERTICES

    def _after_vertex_topology_change(self) -> None:
        """Hook for item-owned structures affected by add/delete topology."""

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a vertex to a new position.

        Args:
            index: Vertex index
            pos: New position in item coordinates
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()
        if 0 <= index < polygon.count():
            # Create new polygon with updated vertex
            vertices = [polygon.at(i) for i in range(polygon.count())]
            vertices[index] = pos
            self.setPolygon(QPolygonF(vertices))

            # Update handles
            self._update_vertex_handles()

            # Update label position
            if hasattr(self, '_position_label'):
                self._position_label()

    def _add_vertex_at_edge(self, edge_index: int, pos: QPointF) -> None:
        """Add a new vertex at an edge position.

        Args:
            edge_index: Index of the edge (starting vertex index)
            pos: Position for the new vertex in item coordinates
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()

        # Insert after edge_index
        insert_index = edge_index + 1
        vertices = [polygon.at(i) for i in range(polygon.count())]
        vertices.insert(insert_index, pos)

        # Update polygon
        self.setPolygon(QPolygonF(vertices))
        self._after_vertex_topology_change()

        # Shift any constraint anchor indices that now point past the insert.
        _shift_constraint_indices_after_insert(self, insert_index)

        # Recreate handles and annotations (indices changed)
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()

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

        polygon = self.polygon()

        # Check minimum vertices
        if polygon.count() <= MINIMUM_VERTICES:
            return

        # Store position for undo
        deleted_pos = polygon.at(index)

        # Drop constraints on the deleted vertex and shift higher indices down.
        _shift_constraint_indices_after_delete(self, index)

        # Remove vertex
        vertices = [polygon.at(i) for i in range(polygon.count()) if i != index]

        # Update polygon
        self.setPolygon(QPolygonF(vertices))
        self._after_vertex_topology_change()

        # Recreate handles and annotations (indices changed)
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()

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

        # Canvas view may request deferred registration so it can bundle constraint
        # corrections (ANGLE solver + PARALLEL re-alignment) into a single undo step.
        view = scene.views()[0] if scene.views() else None
        if view is not None and getattr(view, '_deferring_vertex_undo', False):
            view._deferred_vertex_move = (self, vertex_index, old_pos, new_pos)
            return

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_move_vertex_command,
        )

        command = build_move_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            old_pos,
            new_pos,
        )

        # Add to undo stack without executing (move already applied)
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

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

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_add_vertex_command,
        )

        command = build_add_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
        )

        # Add to undo stack without executing (add already applied)
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

    def _on_vertex_delete(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is deleted. Registers undo command.

        Args:
            vertex_index: Index of the deleted vertex
            pos: Position of the deleted vertex (captured before removal)
        """
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_delete_vertex_command,
        )

        command = build_delete_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
        )

        # Add to undo stack without executing (delete already applied)
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

    def _insert_vertex(self, index: int, pos: QPointF) -> None:
        """Insert a vertex at a specific index (for undo/redo).

        Args:
            index: Index where to insert the vertex
            pos: Position of the new vertex
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()
        vertices = [polygon.at(i) for i in range(polygon.count())]
        vertices.insert(index, pos)
        self.setPolygon(QPolygonF(vertices))
        self._after_vertex_topology_change()

        # Update handles and annotations if in edit mode
        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()

    def _remove_vertex(self, index: int) -> None:
        """Remove a vertex at a specific index (for undo/redo).

        Args:
            index: Index of the vertex to remove
        """
        if not hasattr(self, 'polygon') or not hasattr(self, 'setPolygon'):
            return

        from PyQt6.QtGui import QPolygonF

        polygon = self.polygon()
        vertices = [polygon.at(i) for i in range(polygon.count()) if i != index]
        self.setPolygon(QPolygonF(vertices))
        self._after_vertex_topology_change()

        # Update handles and annotations if in edit mode
        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        # Update label position
        if hasattr(self, '_position_label'):
            self._position_label()


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
        self.setZValue(10_002)

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

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Highlight handle on hover."""
        if event is None:
            return
        self.setBrush(QBrush(VERTEX_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        """Remove highlight when hover ends."""
        if event is None:
            return
        self.setBrush(QBrush(VERTEX_HANDLE_COLOR))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Start corner drag operation."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            # A FIXED rectangle or one with blocking constraints must not deform.
            if self._parent_item is not None and (
                _is_item_fixed(self._parent_item)
                or _has_blocking_constraints(self._parent_item)
            ):
                _emit_scale_blocked_hint(self._parent_item)
                event.ignore()
                return

            self._is_dragging = True
            self._drag_start_pos = event.scenePos()

            # Store initial rectangle and position
            if self._parent_item is not None and hasattr(self._parent_item, 'rect'):
                self._initial_rect = QRectF(self._parent_item.rect())
                self._initial_item_pos = QPointF(self._parent_item.pos())

            # Grab mouse so movement events keep firing even when the cursor
            # leaves this handle — the original cause of "corners are inert".
            self.grabMouse()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Handle corner movement during drag."""
        if event is None:
            return
        if not self._is_dragging or self._parent_item is None:
            super().mouseMoveEvent(event)
            return

        if self._initial_rect is None or self._initial_item_pos is None:
            return

        # Get delta in scene coordinates, clamped to canvas
        current_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)
        delta = current_pos - cast(QPointF, self._drag_start_pos)

        # Apply corner movement
        if hasattr(self._parent_item, '_move_corner_to'):
            self._parent_item._move_corner_to(self._corner, delta, self._initial_rect, self._initial_item_pos)

        _announce_live_edit(self._parent_item)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        """Complete corner drag operation."""
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self.ungrabMouse()
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


def _opposite_corner(corner: "RectCorner", rect: QRectF) -> QPointF:
    """The corner of ``rect`` diagonally opposite ``corner`` — the drag anchor."""
    return {
        RectCorner.TOP_LEFT: rect.bottomRight,
        RectCorner.TOP_RIGHT: rect.bottomLeft,
        RectCorner.BOTTOM_LEFT: rect.topRight,
        RectCorner.BOTTOM_RIGHT: rect.topLeft,
    }[corner]()


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

        # Prevent accidental whole-item drag while editing individual corners
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Hide resize and rotation handles if they exist
        if hasattr(self, 'hide_resize_handles'):
            self.hide_resize_handles()
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()

        # Create corner handles and annotations
        self._create_rect_corner_handles()
        self._create_rect_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide corner handles."""
        if not self._is_rect_vertex_edit_mode:
            return

        self._is_rect_vertex_edit_mode = False

        # Restore whole-item movability
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Remove corner handles and annotations
        self._remove_rect_corner_handles()
        self._remove_rect_annotations()

        # Show resize and rotation handles if selected
        if hasattr(self, 'isSelected') and self.isSelected():
            if hasattr(self, 'show_resize_handles'):
                self.show_resize_handles()
            if hasattr(self, 'show_rotation_handle'):
                self.show_rotation_handle()

    def _create_rect_corner_handles(self) -> None:
        """Create handles for all 4 corners."""
        self._remove_rect_corner_handles()

        if not hasattr(self, 'rect'):
            return

        rect = self.rect()
        for corner in RectCorner:
            handle = RectCornerHandle(corner, self)  # type: ignore[arg-type]
            handle.update_position(rect)
            self._rect_corner_handles.append(handle)

    def _remove_rect_corner_handles(self) -> None:
        """Remove all corner handles."""
        for handle in self._rect_corner_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._rect_corner_handles = []

    def _update_rect_corner_handles(self) -> None:
        """Update positions of all corner handles and annotations."""
        if not hasattr(self, 'rect'):
            return

        rect = self.rect()
        for handle in self._rect_corner_handles:
            handle.update_position(rect)

        self._update_rect_annotations()

    def _create_rect_annotations(self) -> None:
        """Create coordinate and edge length annotations for rectangle corners."""
        self._remove_rect_annotations()

        if not hasattr(self, 'rect') or not hasattr(self, 'mapToScene'):
            return

        rect = self.rect()
        corners = [
            QPointF(rect.left(), rect.top()),
            QPointF(rect.right(), rect.top()),
            QPointF(rect.right(), rect.bottom()),
            QPointF(rect.left(), rect.bottom()),
        ]

        # Coordinate labels at each corner
        for corner in corners:
            scene_pt = self.mapToScene(corner)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(corner.x(), corner.y())
            self._rect_coord_labels.append(label)

        # Edge length labels at each edge midpoint (4 edges)
        for i in range(4):
            p1 = corners[i]
            p2 = corners[(i + 1) % 4]
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)
            scene_p2 = self.mapToScene(p2)
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._rect_edge_labels.append(label)

    def _remove_rect_annotations(self) -> None:
        """Remove all rectangle annotation labels."""
        for label in self._rect_coord_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._rect_coord_labels = []

        for label in self._rect_edge_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._rect_edge_labels = []

    def _update_rect_annotations(self) -> None:
        """Update rectangle annotation text and positions."""
        if not hasattr(self, 'rect') or not hasattr(self, 'mapToScene'):
            return

        rect = self.rect()
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
                scene_pt = self.mapToScene(corner)
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(corner.x(), corner.y())

        # Update edge length labels
        for i, label in enumerate(self._rect_edge_labels):
            if i < 4:
                p1 = corners[i]
                p2 = corners[(i + 1) % 4]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)
                scene_p2 = self.mapToScene(p2)
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
        """Move a corner by ``delta`` (scene coords) while keeping the shape a rectangle.

        The diagonally opposite corner is held fixed in scene space; the
        rectangle's local width and height are adjusted to reach the dragged
        corner's new scene position.  Supports rotated rectangles by projecting
        the delta onto the rectangle's local axes.
        """
        if not hasattr(self, 'setRect') or not hasattr(self, 'setPos'):
            return

        # Rotate delta into the rectangle's local frame.  Qt rotation is CW in
        # screen space (Y-down), so use -θ to invert.
        rotation_deg = float(self.rotation()) if hasattr(self, 'rotation') else 0.0
        theta = math.radians(-rotation_deg)
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        local_dx = delta.x() * cos_t - delta.y() * sin_t
        local_dy = delta.x() * sin_t + delta.y() * cos_t

        new_rect = QRectF(initial_rect)

        if corner == RectCorner.TOP_LEFT:
            new_width = initial_rect.width() - local_dx
            new_height = initial_rect.height() - local_dy
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        elif corner == RectCorner.TOP_RIGHT:
            new_width = initial_rect.width() + local_dx
            new_height = initial_rect.height() - local_dy
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        elif corner == RectCorner.BOTTOM_LEFT:
            new_width = initial_rect.width() - local_dx
            new_height = initial_rect.height() + local_dy
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        elif corner == RectCorner.BOTTOM_RIGHT:
            new_width = initial_rect.width() + local_dx
            new_height = initial_rect.height() + local_dy
            if new_width >= MINIMUM_SIZE_CM:
                new_rect.setWidth(new_width)
            if new_height >= MINIMUM_SIZE_CM:
                new_rect.setHeight(new_height)

        # Pin the corner diagonally opposite the dragged one: take its scene
        # position from the PRE-drag geometry, then solve for the pos that puts
        # the new rect's matching corner back on it.
        #
        # Both steps go through the shared transform pair, and that is the point.
        # This was a hand-rolled local-to-scene shift derived under the
        # assumption that the rotation origin stays at the OLD rect centre —
        # which stopped being true the moment the #219 re-pin below was added,
        # sliding a rotated rectangle out from under the cursor by up to 671 cm
        # (a swap of one bug for another, caught in review). `anchored_position`
        # bakes in `O = new_rect.center()`, so the re-pin and the placement are
        # now one coupled solution instead of two half-solutions in one function.
        scene_anchor = scene_point_of(
            _opposite_corner(corner, initial_rect),
            initial_rect,
            initial_pos,
            rotation_deg,
        )
        new_pos = anchored_position(
            new_rect, rotation_deg, scene_anchor, _opposite_corner(corner, new_rect)
        )

        self.setRect(new_rect)
        # The serializer invariant transformOriginPoint == rect().center()
        # (#219). Without it a rotated corner drag stored a centre up to 331 cm
        # from the visible one, i.e. it saved displaced.
        self.setTransformOriginPoint(new_rect.center())  # type: ignore[attr-defined]
        self.setPos(new_pos)
        self._update_rect_corner_handles()
        if hasattr(self, '_position_label'):
            self._position_label()

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

        current_rect = self.rect()
        current_pos = self.pos()

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

        # US-D2.2: the canonical apply path (ui.canvas.geometry_apply), shared
        # with the properties panel, the drag handles and the Agent API. The
        # dict shape below is already the canonical one; the private closure
        # this replaces was missing the #219 origin re-pin, so undo/redo of a
        # rotated corner drag restored rect + pos but left the pivot wrong.
        # Imported here rather than at module scope: geometry_apply imports
        # anchored_position from THIS module, so a top-level import would be
        # circular.
        from open_garden_planner.ui.canvas.geometry_apply import (
            apply_rect_like_geometry,
            capture_rect_like_geometry,
        )

        def apply_geometry(item: QGraphicsItem, geom: dict[str, Any]) -> None:
            """Apply geometry, then refresh this mixin's own corner handles."""
            apply_rect_like_geometry(item, geom)
            if hasattr(item, '_update_rect_corner_handles'):
                item._update_rect_corner_handles()

        # The NEW dict is captured from the item's present state, which
        # _move_corner_to has already set. The OLD dict cannot be captured —
        # the item is already mutated — so it is rebuilt by hand from the
        # pre-drag initial values; this mixin only ever holds rectangles, so
        # the circle bookkeeping capture would add is not needed here.
        old_geometry = {
            'rect_x': initial_rect.x(),
            'rect_y': initial_rect.y(),
            'width': initial_rect.width(),
            'height': initial_rect.height(),
            'pos_x': initial_pos.x(),
            'pos_y': initial_pos.y(),
        }
        new_geometry = capture_rect_like_geometry(self)  # type: ignore[arg-type]

        command = ResizeItemCommand(
            self,  # type: ignore[arg-type]
            old_geometry,
            new_geometry,
            apply_geometry,
        )

        # Add to undo stack without executing (move already applied)
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)


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

        # Prevent accidental whole-item drag while editing individual vertices
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        # Hide rotation handle if it exists
        if hasattr(self, 'hide_rotation_handle'):
            self.hide_rotation_handle()

        # Create vertex and midpoint handles + annotations
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

    def exit_vertex_edit_mode(self) -> None:
        """Exit vertex editing mode - hide vertex handles."""
        if not self._is_vertex_edit_mode:
            return

        self._is_vertex_edit_mode = False

        # Restore whole-item movability
        if hasattr(self, 'setFlag'):
            from PyQt6.QtWidgets import QGraphicsItem
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        # Remove vertex and midpoint handles + annotations
        self._remove_vertex_handles()
        self._remove_midpoint_handles()
        self._remove_annotations()
        _forget_dense_sample(self)

        # Show rotation handle if selected
        if hasattr(self, 'isSelected') and self.isSelected() and hasattr(self, 'show_rotation_handle'):
            self.show_rotation_handle()

    def _create_vertex_handles(self) -> None:
        """Create handles for all vertices, sampled when the path is dense."""
        self._remove_vertex_handles()

        if not hasattr(self, '_points'):
            return

        points = self._points
        dense = len(points) > MAX_ANNOTATED_VERTICES
        for i in _visible_vertex_indices(self, points):
            handle = VertexHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(points[i])
            if dense:
                point = _map_to_scene(self, points[i])
                handle.setToolTip(_format_coordinate(point.x(), point.y()))
            self._vertex_handles.append(handle)
        if dense:
            _remember_dense_sample(self)
        else:
            _forget_dense_sample(self)

    def _remove_vertex_handles(self) -> None:
        """Remove all vertex handles."""
        for handle in self._vertex_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._vertex_handles = []

    def _create_midpoint_handles(self) -> None:
        """Create handles at edge midpoints (no wrap-around for open paths)."""
        self._remove_midpoint_handles()

        if not hasattr(self, '_points'):
            return

        points = self._points
        dense = len(points) > MAX_ANNOTATED_VERTICES
        owner = cast(Any, self)
        scene = owner.scene()
        transform = None
        if dense and scene is not None and scene.views():
            viewport = scene.views()[0].viewport()
            if viewport is not None:
                transform = owner.deviceTransform(scene.views()[0].viewportTransform())
        candidates: list[tuple[int, QPointF]] = []
        # Open path: midpoints between consecutive pairs only (no closing edge)
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            if (
                transform is not None
                and _edge_length(transform.map(p1), transform.map(p2))
                < 2 * DENSE_HANDLE_SPACING_PX
            ):
                continue
            candidates.append((i, QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)))

        indices = (
            _dense_overlay_indices(self, candidates)
            if dense
            else [index for index, _point in candidates]
        )
        by_index = dict(candidates)
        for i in indices:
            handle = MidpointHandle(i, self)  # type: ignore[arg-type]
            handle.update_position(by_index[i])
            if dense:
                p1 = points[i]
                p2 = points[i + 1]
                handle.setToolTip(
                    _format_edge_length(
                        _edge_length(_map_to_scene(self, p1), _map_to_scene(self, p2))
                    )
                )
            self._midpoint_handles.append(handle)

    def _remove_midpoint_handles(self) -> None:
        """Remove all midpoint handles."""
        for handle in self._midpoint_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._midpoint_handles = []

    def refresh_vertex_edit_overlay(self) -> None:
        """Re-sample a dense path after a zoom or pan; never during a drag.

        A pan that stays inside the sampled scene region does not re-sample
        (#594); a zoom, or a pan beyond the region, samples again.
        """
        if not getattr(self, "_is_vertex_edit_mode", False):
            return
        if len(getattr(self, "_points", ())) <= MAX_ANNOTATED_VERTICES:
            return
        if any(
            getattr(handle, "_is_dragging", False)
            for handle in [*self._vertex_handles, *self._midpoint_handles]
        ):
            return
        if _dense_sample_covers_view(self):
            return
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._remove_annotations()

    def _update_vertex_handles(self) -> None:
        """Update positions of all vertex and midpoint handles and annotations."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        dense = len(points) > MAX_ANNOTATED_VERTICES

        # Update vertex handles (a dense path holds only a sample)
        for vertex_handle in self._vertex_handles:
            i = vertex_handle.vertex_index
            if i < len(points):
                vertex_handle.update_position(points[i])
                if dense:
                    point = _map_to_scene(self, points[i])
                    vertex_handle.setToolTip(_format_coordinate(point.x(), point.y()))

        # Update midpoint handles
        for midpoint_handle in self._midpoint_handles:
            i = midpoint_handle.edge_index
            if i < len(points) - 1:
                p1 = points[i]
                p2 = points[i + 1]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                midpoint_handle.update_position(midpoint)
                if dense:
                    midpoint_handle.setToolTip(
                        _format_edge_length(
                            _edge_length(_map_to_scene(self, p1), _map_to_scene(self, p2))
                        )
                    )

        # Update annotations
        self._update_annotations()
        # A geometry change invalidates the candidate set's pose/positions (#594).
        _forget_dense_sample(self)

    def _create_annotations(self) -> None:
        """Create coordinate and edge length annotations."""
        self._remove_annotations()

        if not hasattr(self, '_points') or not hasattr(self, 'mapToScene'):
            return

        points = self._points
        if len(points) > MAX_ANNOTATED_VERTICES:
            return  # Dense paths use handle tooltips instead of overlapping labels.

        # Coordinate labels at each vertex
        for point in points:
            scene_pt = self.mapToScene(point)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
            label.setPos(point.x(), point.y())
            self._coord_labels.append(label)

        # Edge length labels (open path: N-1 edges)
        for i in range(len(points) - 1):
            p1 = points[i]
            p2 = points[i + 1]
            midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
            scene_p1 = self.mapToScene(p1)
            scene_p2 = self.mapToScene(p2)
            length = _edge_length(scene_p1, scene_p2)
            label = AnnotationLabel(self)  # type: ignore[arg-type]
            label.set_text(_format_edge_length(length))
            label.setPos(midpoint.x(), midpoint.y())
            self._edge_labels.append(label)

    def _remove_annotations(self) -> None:
        """Remove all annotation labels."""
        for label in self._coord_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._coord_labels = []

        for label in self._edge_labels:
            if label.scene() is not None:
                cast(Any, label.scene()).removeItem(label)
        self._edge_labels = []

    def _update_annotations(self) -> None:
        """Update annotation text and positions."""
        if not hasattr(self, '_points') or not hasattr(self, 'mapToScene'):
            return

        points = self._points
        if len(points) > MAX_ANNOTATED_VERTICES:
            return  # No labels exist for a dense path; see _create_annotations.

        # Update coordinate labels
        for i, label in enumerate(self._coord_labels):
            if i < len(points):
                point = points[i]
                scene_pt = self.mapToScene(point)
                label.set_text(_format_coordinate(scene_pt.x(), scene_pt.y()))
                label.setPos(point.x(), point.y())

        # Update edge length labels
        for i, label in enumerate(self._edge_labels):
            if i < len(points) - 1:
                p1 = points[i]
                p2 = points[i + 1]
                midpoint = QPointF((p1.x() + p2.x()) / 2, (p1.y() + p2.y()) / 2)
                scene_p1 = self.mapToScene(p1)
                scene_p2 = self.mapToScene(p2)
                length = _edge_length(scene_p1, scene_p2)
                label.set_text(_format_edge_length(length))
                label.setPos(midpoint.x(), midpoint.y())

    def _rebuild_path(self) -> None:
        """Rebuild the QPainterPath from current points."""
        if not hasattr(self, '_points') or not hasattr(self, 'setPath'):
            return

        from PyQt6.QtGui import QPainterPath as _QPainterPath

        points = self._points
        path = _QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
        self.setPath(path)

    def _get_vertex_position(self, index: int) -> QPointF:
        """Get the position of a vertex."""
        if not hasattr(self, '_points'):
            return QPointF(0, 0)

        points = self._points
        if 0 <= index < len(points):
            return QPointF(points[index])
        return QPointF(0, 0)

    def _get_vertex_count(self) -> int:
        """Get the number of vertices."""
        if not hasattr(self, '_points'):
            return 0
        return len(self._points)

    def _get_minimum_vertex_count(self) -> int:
        """Get the minimum number of vertices allowed (2 for polylines)."""
        return MINIMUM_POLYLINE_VERTICES

    def _after_vertex_topology_change(self) -> None:
        """Hook for item-owned structures affected by add/delete topology."""

    def _move_vertex_to(self, index: int, pos: QPointF) -> None:
        """Move a vertex to a new position."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        if 0 <= index < len(points):
            points[index] = pos
            self._rebuild_path()
            self._update_vertex_handles()

            if hasattr(self, '_position_label'):
                self._position_label()

    def _add_vertex_at_edge(self, edge_index: int, pos: QPointF) -> None:
        """Add a new vertex at an edge position."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        insert_index = edge_index + 1
        points.insert(insert_index, pos)

        # Shift any constraint anchor indices that now point past the insert.
        _shift_constraint_indices_after_insert(self, insert_index)

        self._rebuild_path()
        self._after_vertex_topology_change()
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()

        self._on_vertex_add(insert_index, pos)

    def _delete_vertex(self, index: int) -> None:
        """Delete a vertex from the polyline."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        if len(points) <= MINIMUM_POLYLINE_VERTICES:
            return

        deleted_pos = QPointF(points[index])

        # Drop constraints on the deleted vertex and shift higher indices down.
        _shift_constraint_indices_after_delete(self, index)

        del points[index]

        self._rebuild_path()
        self._after_vertex_topology_change()
        self._create_vertex_handles()
        self._create_midpoint_handles()
        self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()

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

        # Canvas view may request deferred registration so it can bundle constraint
        # corrections (ANGLE solver + PARALLEL re-alignment) into a single undo step.
        view = scene.views()[0] if scene.views() else None
        if view is not None and getattr(view, '_deferring_vertex_undo', False):
            view._deferred_vertex_move = (self, vertex_index, old_pos, new_pos)
            return

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_move_vertex_command,
        )

        command = build_move_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            old_pos,
            new_pos,
        )

        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

    def _on_vertex_add(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is added. Registers undo command."""
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_add_vertex_command,
        )

        command = build_add_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
        )

        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

    def _on_vertex_delete(self, vertex_index: int, pos: QPointF) -> None:
        """Called when a vertex is deleted. Registers undo command."""
        scene = getattr(self, 'scene', lambda: None)()
        if scene is None or not hasattr(scene, 'get_command_manager'):
            return

        command_manager = scene.get_command_manager()
        if command_manager is None:
            return

        from open_garden_planner.ui.canvas.geometry_apply import (
            build_delete_vertex_command,
        )

        command = build_delete_vertex_command(
            self,  # type: ignore[arg-type]
            vertex_index,
            pos,
        )

        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)

    def _insert_vertex(self, index: int, pos: QPointF) -> None:
        """Insert a vertex at a specific index (for undo/redo)."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        points.insert(index, pos)
        self._rebuild_path()
        self._after_vertex_topology_change()

        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()

    def _remove_vertex(self, index: int) -> None:
        """Remove a vertex at a specific index (for undo/redo)."""
        if not hasattr(self, '_points'):
            return

        points = self._points
        if 0 <= index < len(points):
            del points[index]
        self._rebuild_path()
        self._after_vertex_topology_change()

        if self._is_vertex_edit_mode:
            self._create_vertex_handles()
            self._create_midpoint_handles()
            self._create_annotations()

        if hasattr(self, '_position_label'):
            self._position_label()


# ---------------------------------------------------------------------------
# Curve (Bezier / Arc) control-handle editing — issue #193 (US-B9)
# ---------------------------------------------------------------------------

# On-curve anchors / arc endpoints (blue squares), tangent + arc through-point
# (green squares), and a read-only arc center marker (gray). Handles render at a
# fixed screen size like the polygon/polyline vertex handles.
CURVE_ANCHOR_SIZE = 8.0  # pixels (cosmetic)
CURVE_TANGENT_SIZE = 7.0  # pixels (cosmetic)
CURVE_ANCHOR_COLOR = QColor(0, 120, 215)  # blue — on-curve anchor / arc endpoint
CURVE_TANGENT_COLOR = QColor(46, 204, 113)  # green — bezier tangent / arc through-point
CURVE_HANDLE_HOVER_COLOR = QColor(0, 180, 255)  # lighter blue on hover
CURVE_CENTER_COLOR = QColor(150, 150, 150)  # gray — read-only arc center
CURVE_CONNECTOR_COLOR = QColor(120, 120, 120)  # thin anchor↔tangent connector

# Control-handle "kind" tags shared between CurveControlHandle and the host item.
CURVE_KIND_ANCHOR = "anchor"
CURVE_KIND_HANDLE_IN = "handle_in"
CURVE_KIND_HANDLE_OUT = "handle_out"
CURVE_KIND_ARC_START = "arc_start"
CURVE_KIND_ARC_THROUGH = "arc_through"
CURVE_KIND_ARC_END = "arc_end"
CURVE_KIND_CENTER = "center"  # read-only display, not draggable

_CURVE_TANGENT_KINDS = frozenset(
    {CURVE_KIND_HANDLE_IN, CURVE_KIND_HANDLE_OUT, CURVE_KIND_ARC_THROUGH}
)


class CurveControlHandle(QGraphicsRectItem):
    """A draggable control point for reshaping a placed Bezier or Arc.

    Each handle is a fixed-screen-size square parented to the curve item. On
    drag it asks the parent to mutate its geometry via ``_move_control`` and,
    on release, to commit a single undo step via ``_end_curve_edit``. The
    ``CURVE_KIND_CENTER`` handle is a read-only marker (not draggable).
    """

    def __init__(self, kind: str, index: int, parent: "ParentItem") -> None:
        super().__init__(parent)
        self._kind = kind
        self._index = index
        self._parent_item = parent
        self._is_dragging = False

        is_anchor = kind in (CURVE_KIND_ANCHOR, CURVE_KIND_ARC_START, CURVE_KIND_ARC_END)
        size = CURVE_ANCHOR_SIZE if is_anchor else CURVE_TANGENT_SIZE
        half = size / 2.0
        self.setRect(-half, -half, size, size)

        if kind == CURVE_KIND_CENTER:
            self._base_color = CURVE_CENTER_COLOR
        elif is_anchor:
            self._base_color = CURVE_ANCHOR_COLOR
        else:
            self._base_color = CURVE_TANGENT_COLOR
        self.setPen(QPen(HANDLE_BORDER_COLOR, 1.0))
        self.setBrush(QBrush(self._base_color))

        self.setFlag(QGraphicsRectItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.setZValue(10_002)  # above resize/rotation handles
        if kind != CURVE_KIND_CENTER:
            self.setAcceptHoverEvents(True)
            self.setCursor(Qt.CursorShape.SizeAllCursor)

    @property
    def kind(self) -> str:
        return self._kind

    @property
    def control_index(self) -> int:
        return self._index

    def update_position(self, pos: QPointF) -> None:
        """Move the handle to a parent-local position."""
        self.setPos(pos)

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        if event is None:
            return
        self.setBrush(QBrush(CURVE_HANDLE_HOVER_COLOR))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent | None) -> None:
        if event is None:
            return
        self.setBrush(QBrush(self._base_color))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if self._kind == CURVE_KIND_CENTER or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self._is_dragging = True
        if hasattr(self._parent_item, "_begin_curve_edit"):
            self._parent_item._begin_curve_edit()
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if not self._is_dragging or self._parent_item is None:
            super().mouseMoveEvent(event)
            return
        scene_pos = _clamp_pos_to_canvas(event.scenePos(), self._parent_item)
        local = self._parent_item.mapFromScene(scene_pos)
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if hasattr(self._parent_item, "_move_control"):
            self._parent_item._move_control(self._kind, self._index, local, alt)
        _announce_live_edit(self._parent_item)
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent | None) -> None:
        if event is None:
            return
        if event.button() == Qt.MouseButton.LeftButton and self._is_dragging:
            self.ungrabMouse()
            self._is_dragging = False
            if hasattr(self._parent_item, "_end_curve_edit"):
                self._parent_item._end_curve_edit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class CurveEditMixin(PositionLockMixin):
    """Selection-driven control-handle editing for Bezier / Arc items.

    Unlike the polygon/polyline ``*VertexEditMixin`` (double-click, insert/delete
    vertices), curve editing is purely *reshape*: handles appear while the curve
    is selected and disappear on deselect. The host item MUST implement **all** of:

    - ``_curve_control_specs() -> list[(kind, index, local_pos)]``
    - ``_curve_connectors() -> list[(local_p1, local_p2)]`` (thin guide lines)
    - ``_move_control(kind, index, local_pos, alt)`` — mutate geometry live
    - ``_capture_geometry()`` / ``_restore_geometry(state)`` — undo snapshots

    The host wires its ``itemChange`` to call :meth:`sync_curve_edit_to_selection`.
    """

    _control_handles: list[CurveControlHandle]
    _connector_lines: list[QGraphicsItem]
    _is_curve_edit_mode: bool
    _edit_snapshot: Any

    def init_curve_edit(self) -> None:
        """Initialise curve editing (call in subclass ``__init__``)."""
        self._control_handles = []
        self._connector_lines = []
        self._is_curve_edit_mode = False
        self._edit_snapshot = None

    @property
    def is_curve_edit_mode(self) -> bool:
        return self._is_curve_edit_mode

    def sync_curve_edit_to_selection(self) -> None:
        """Show control handles while this curve is selected, hide them otherwise.

        Keyed on this item's own selection state so every item's ``itemChange``
        stays self-consistent (a scene-wide "sole selection" gate would leave
        stale handles on an item whose own selection did not change when another
        item joined the selection).
        """
        if self.isSelected() and not _is_item_fixed(self):  # type: ignore[attr-defined, arg-type]
            self.enter_curve_edit_mode()
        else:
            self.exit_curve_edit_mode()

    def enter_curve_edit_mode(self) -> None:
        if self._is_curve_edit_mode:
            return
        self._is_curve_edit_mode = True
        self._create_control_handles()

    def exit_curve_edit_mode(self) -> None:
        if not self._is_curve_edit_mode:
            return
        self._is_curve_edit_mode = False
        self._remove_control_handles()

    def _create_control_handles(self) -> None:
        # Only ever reached via enter_curve_edit_mode on a real host (Bezier/Arc),
        # which implements the full hook contract documented on the class.
        self._remove_control_handles()
        for p1, p2 in self._curve_connectors():  # type: ignore[attr-defined]
            line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y(), self)  # type: ignore[call-overload]
            pen = QPen(CURVE_CONNECTOR_COLOR, 0.0)  # cosmetic 1px, scales-independent
            line.setPen(pen)
            line.setZValue(10_001)
            line.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self._connector_lines.append(line)
        for kind, index, local_pos in self._curve_control_specs():  # type: ignore[attr-defined]
            handle = CurveControlHandle(kind, index, self)  # type: ignore[arg-type]
            handle.update_position(local_pos)
            self._control_handles.append(handle)

    def _remove_control_handles(self) -> None:
        for handle in self._control_handles:
            if handle.scene() is not None:
                cast(Any, handle.scene()).removeItem(handle)
        self._control_handles = []
        for line in self._connector_lines:
            if line.scene() is not None:
                cast(Any, line.scene()).removeItem(line)
        self._connector_lines = []

    def _update_control_handles(self) -> None:
        """Reposition existing handles + connectors after a live geometry change.

        Repositions in place (never recreates) so the handle currently grabbing
        the mouse is not destroyed mid-drag. Falls back to a full rebuild if the
        control count changed unexpectedly.
        """
        if not self._is_curve_edit_mode:
            return
        specs = self._curve_control_specs()  # type: ignore[attr-defined]
        connectors = self._curve_connectors()  # type: ignore[attr-defined]
        if len(specs) != len(self._control_handles) or len(connectors) != len(
            self._connector_lines
        ):
            self._create_control_handles()
            return
        for handle, (_kind, _index, local_pos) in zip(
            self._control_handles, specs, strict=True
        ):
            handle.update_position(local_pos)
        for line, (p1, p2) in zip(self._connector_lines, connectors, strict=True):
            line.setLine(p1.x(), p1.y(), p2.x(), p2.y())  # type: ignore[attr-defined]

    # -- undo snapshot bracketing (shared by all curve hosts) ---------------

    def _begin_curve_edit(self) -> None:
        self._edit_snapshot = self._capture_geometry()  # type: ignore[attr-defined]

    def _end_curve_edit(self) -> None:
        old = self._edit_snapshot
        self._edit_snapshot = None
        if old is None:
            return
        new = self._capture_geometry()  # type: ignore[attr-defined]
        if new == old:
            return
        scene = self.scene()  # type: ignore[attr-defined]
        if scene is None or not hasattr(scene, "get_command_manager"):
            return
        command_manager = scene.get_command_manager()
        if command_manager is None:
            return
        from open_garden_planner.core.commands import SetCurveGeometryCommand

        command = SetCurveGeometryCommand(self, old, new)  # type: ignore[arg-type]
        # Geometry is already applied by the live drag — register without re-exec.
        from open_garden_planner.core.commands import register_applied_with_membership

        register_applied_with_membership(scene, command_manager, command, self)


# Selection dispatch and the view's dropped-grab recovery must recognise the
# same editing controls. These are interactive even though not selectable.
