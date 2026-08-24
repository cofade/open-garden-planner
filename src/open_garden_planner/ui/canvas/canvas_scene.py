"""Canvas scene for the garden planner.

The scene holds all the garden objects and manages their rendering.
Coordinates are in centimeters with Y-axis pointing down (Qt convention).
The view handles the Y-flip for display.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
)

from open_garden_planner.core import stacking
from open_garden_planner.models.layer import Layer, create_default_layers


@dataclass
class GuideLine:
    """A persistent guide line for alignment reference.

    Attributes:
        is_horizontal: True = horizontal line (constant Y), False = vertical (constant X).
        position: Position in scene coordinates (Y for horizontal, X for vertical).
    """

    is_horizontal: bool
    position: float


class CanvasScene(QGraphicsScene):
    """Graphics scene for the garden canvas.

    The scene uses centimeters as the coordinate unit.
    Origin is at top-left (Qt convention), with Y increasing downward.
    The CanvasView flips the Y-axis for display (CAD convention).

    Signals:
        layers_changed: Emitted when layers are added, removed, or reordered
        active_layer_changed: Emitted when the active layer changes
    """

    # Default canvas colors (overridden by apply_theme_colors)
    CANVAS_COLOR = QColor("#f5f5dc")
    OUTSIDE_COLOR = QColor("#707070")

    # Signals
    layers_changed = pyqtSignal()
    active_layer_changed = pyqtSignal(object)  # Layer or None
    layer_auto_unhidden = pyqtSignal(UUID)  # emitted when a draw auto-reveals a hidden layer

    def __init__(
        self,
        width_cm: float = 5000.0,
        height_cm: float = 3000.0,
        parent: object = None,
    ) -> None:
        """Initialize the canvas scene.

        Args:
            width_cm: Width of the canvas in centimeters (default 50m)
            height_cm: Height of the canvas in centimeters (default 30m)
            parent: Parent object
        """
        super().__init__(parent)

        self._width_cm = width_cm
        self._height_cm = height_cm

        # Set scene rectangle (0,0 at top-left, dimensions in cm)
        # We use a larger rect to allow panning beyond canvas edges
        self._update_scene_rect()

        # Calibration mode state
        self._calibration_mode = False
        self._calibration_image = None
        self._calibration_points: list[QPointF] = []
        self._calibration_markers: list[QGraphicsLineItem] = []

        # Shadow state (painted shadows on garden items)
        self._shadows_enabled = True

        # Labels state
        self._labels_enabled = True

        # Construction geometry visibility state
        self._construction_visible = True

        # Spacing circles visibility state
        self._spacing_circles_visible = True

        # Layer management
        self._layers: list[Layer] = create_default_layers()
        self._active_layer: Layer | None = self._layers[0] if self._layers else None  # Default to first layer

        # Command manager reference (set by CanvasView after construction)
        self._command_manager = None

        # Constraint graph for distance constraints
        from open_garden_planner.core.constraints import ConstraintGraph

        self.constraint_graph = ConstraintGraph()

        # Dimension line manager for constraint visualization
        from open_garden_planner.ui.canvas.dimension_lines import DimensionLineManager

        self._dimension_line_manager = DimensionLineManager(self)

        # Guide lines (persistent horizontal/vertical reference lines)
        self._guide_lines: list[GuideLine] = []

        # Compare overlay: ghosted plant items from a previous season
        self._compare_items: list[QGraphicsItem] = []
        self._compare_overlay_visible = False

        # Suspends the per-add z-refresh during bulk inserts (issue #338)
        # -- see suspend_z_refresh().
        self._suspend_z_refresh = False
        # Per-layer "next unused rank" cache, valid only while
        # _suspend_z_refresh is True -- see _next_stack_order().
        self._next_rank_cache: dict[UUID | None, int] = {}

    def _update_scene_rect(self) -> None:
        """Update the scene rect with padding for panning."""
        # Add padding around canvas (50% of canvas size on each side)
        padding_x = self._width_cm * 0.5
        padding_y = self._height_cm * 0.5
        self.setSceneRect(QRectF(
            -padding_x,
            -padding_y,
            self._width_cm + 2 * padding_x,
            self._height_cm + 2 * padding_y
        ))

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Draw the scene background.

        Fills the visible area with gray, then draws the canvas area in beige.
        """
        # First fill the entire visible rect with gray (outside canvas area)
        painter.fillRect(rect, QBrush(self.OUTSIDE_COLOR))

        # Then draw canvas area (beige rectangle) on top
        canvas_rect = QRectF(0, 0, self._width_cm, self._height_cm)
        painter.fillRect(canvas_rect, QBrush(self.CANVAS_COLOR))

    # Shadow management (painted shadows — no QGraphicsEffect overhead)

    @property
    def shadows_enabled(self) -> bool:
        """Whether painted shadows are shown on objects."""
        return self._shadows_enabled

    def set_shadows_enabled(self, enabled: bool) -> None:
        """Enable or disable painted shadows on all garden objects.

        Args:
            enabled: Whether shadows should be shown
        """
        self._shadows_enabled = enabled
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin):
                item.shadows_enabled = enabled

    # Label management

    @property
    def labels_enabled(self) -> bool:
        """Whether labels are shown on objects."""
        return self._labels_enabled

    def set_labels_visible(self, visible: bool) -> None:
        """Enable or disable labels on all garden objects.

        Args:
            visible: Whether labels should be shown
        """
        self._labels_enabled = visible
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin):
                item.set_global_labels_visible(visible)

    # Construction geometry visibility management

    @property
    def construction_visible(self) -> bool:
        """Whether construction geometry items are shown."""
        return self._construction_visible

    def set_construction_visible(self, visible: bool) -> None:
        """Show or hide all construction geometry items.

        Args:
            visible: Whether construction geometry should be shown.
        """
        self._construction_visible = visible
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        for item in self.items():
            if isinstance(item, (ConstructionLineItem, ConstructionCircleItem)):
                item.setVisible(visible)

    @property
    def spacing_circles_visible(self) -> bool:
        """Whether spacing circles are shown on plant items."""
        return self._spacing_circles_visible

    def set_spacing_circles_visible(self, visible: bool) -> None:
        """Enable or disable spacing circles on all plant items."""
        self._spacing_circles_visible = visible
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin):
                item.spacing_circles_visible = visible

    def addItem(self, item: QGraphicsItem) -> None:
        """Add an item to the scene, applying shadow and label state.

        Also auto-unhides the item's layer if it is currently hidden, so that
        drawing on a hidden layer reveals the layer and all its items.

        Args:
            item: The graphics item to add
        """
        super().addItem(item)
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        if isinstance(item, (ConstructionLineItem, ConstructionCircleItem)):
            item.setVisible(self._construction_visible)
            return

        if isinstance(item, GardenItemMixin):
            item.shadows_enabled = self._shadows_enabled
            item.set_global_labels_visible(self._labels_enabled)
            item.spacing_circles_visible = self._spacing_circles_visible

            # Auto-unhide the target layer so drawing on a hidden layer reveals it
            if item.layer_id:
                layer = self.get_layer_by_id(item.layer_id)
                if layer and not layer.visible:
                    layer.visible = True
                    self._update_items_visibility()
                    self.layer_auto_unhidden.emit(item.layer_id)

        # Assign a stacking rank so new items render on top of existing
        # same-layer items, then derive z-values for the whole layer
        # (issue #338). Without this, new items default to z=0, below
        # all layer items.
        # A ``layer_id`` of ``None`` (no active layer at drop time, or a
        # bare test item) is ranked in a pseudo-layer at base z 0 — the
        # band those items always occupied — so the plant-above-bed clamp
        # still holds for them.
        #
        # NOT gated on ``isinstance(item, GardenItemMixin)`` — that would
        # silently skip ``ArcItem``/``BezierItem`` (``CurveEditMixin,
        # QGraphicsPathItem``, never a ``GardenItemMixin``) even though they
        # carry ``stack_order``/``layer_id`` and round-trip them in their own
        # ``to_dict``/``from_dict``. Use the one duck-typed eligibility
        # predicate instead (issue #338 review round 2, P0) so every ranked
        # item type is assigned a rank and refreshed the same way.
        if stacking.supports_stacking(item):
            if item.stack_order is None:
                item.stack_order = self._next_stack_order(item.layer_id)
            elif self._suspend_z_refresh:
                # Keep _next_stack_order's per-layer rank cache honest even
                # for an item that already had a rank when it's (re-)added
                # mid-scope (e.g. DeleteItemsCommand.undo restoring several
                # items, one of which already outranks the cache's current
                # "next" value) -- otherwise a later UNranked add in the same
                # suspended scope could be assigned a lower rank than this
                # one and sort out of order (review round 2, P2).
                #
                # Seeding an empty cache entry from just this item's own rank
                # (as an earlier revision did) is wrong when OTHER items still
                # in the layer -- untouched so far this scope -- already carry
                # a higher rank than this one: e.g. a layer holding ranks
                # 1024/2048/3072, only the 1024 item removed and re-added in
                # this scope, then an unranked add would seed the cache to
                # 1024 and hand out 2048, colliding with the untouched item
                # that already has that rank (issue #338 review round 3,
                # P1-1). Seed from the real per-layer max instead so a later
                # unranked add in this scope always lands above every rank
                # visible in the layer, not just the ones re-added so far.
                cached = self._next_rank_cache.get(item.layer_id)
                base = (
                    self._max_existing_rank(item.layer_id)
                    if cached is None
                    else cached
                )
                self._next_rank_cache[item.layer_id] = max(base, item.stack_order)
            if not self._suspend_z_refresh:
                self._refresh_layer_z(item.layer_id)

    # Constraint dimension line management

    @property
    def constraints_visible(self) -> bool:
        """Whether constraint dimension lines are shown."""
        return self._dimension_line_manager.visible

    def set_constraints_visible(self, visible: bool) -> None:
        """Show or hide constraint dimension lines.

        Args:
            visible: Whether dimension lines should be shown
        """
        self._dimension_line_manager.set_visible(visible)

    def reset_constraints(self) -> None:
        """Clear all constraints and their dimension-line visuals.

        Must be called BEFORE scene.clear() so the manager can remove its
        graphics items while the C++ objects are still alive.
        """
        from open_garden_planner.core.constraints import ConstraintGraph

        self._dimension_line_manager.clear()
        self.constraint_graph = ConstraintGraph()

    def update_dimension_lines(self) -> None:
        """Rebuild all dimension line visuals from the constraint graph."""
        self._dimension_line_manager.update_all()

    def project_vertex_drag(
        self,
        item: QGraphicsItem,
        vertex_index: int,
        desired_scene_pos: QPointF,
    ) -> QPointF:
        """Project a live vertex-drag target onto its constraint feasible set.

        Returns ``desired_scene_pos`` unchanged when no constraint touches this
        vertex, or when the item is not tracked as deformable (rigid items use
        a different drag path).  Otherwise builds the minimum solver state —
        all other items pinned — and delegates to
        :py:meth:`ConstraintGraph.project_to_feasible`.
        """
        from open_garden_planner.core.constraints import AnchorType
        from open_garden_planner.core.measure_snapper import get_anchor_points
        from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        if not isinstance(item, (PolygonItem, PolylineItem)):
            return desired_scene_pos
        item_id = getattr(item, "item_id", None)
        if item_id is None:
            return desired_scene_pos

        graph = self.constraint_graph
        vkey = (item_id, vertex_index)
        vertex_types = {AnchorType.CORNER, AnchorType.ENDPOINT}
        touches = any(
            (
                c.anchor_a.item_id == item_id
                and c.anchor_a.anchor_index == vertex_index
                and c.anchor_a.anchor_type in vertex_types
            )
            or (
                c.anchor_b.item_id == item_id
                and c.anchor_b.anchor_index == vertex_index
                and c.anchor_b.anchor_type in vertex_types
            )
            for c in graph.constraints.values()
        )
        if not touches:
            return desired_scene_pos

        item_positions: dict = {}
        anchor_offsets: dict = {}
        deformable_items: set = set()
        deformable_vertices: dict = {}

        for scene_item in self.items():
            if not isinstance(scene_item, GardenItemMixin):
                continue
            uid = scene_item.item_id
            pos = scene_item.pos()
            item_positions[uid] = (pos.x(), pos.y())
            for anchor in get_anchor_points(scene_item):
                anchor_offsets[(uid, anchor.anchor_type, anchor.anchor_index)] = (
                    anchor.point.x() - pos.x(),
                    anchor.point.y() - pos.y(),
                )
            if isinstance(scene_item, PolygonItem):
                polygon = scene_item.polygon()
                verts = [
                    (
                        scene_item.mapToScene(polygon.at(i)).x(),
                        scene_item.mapToScene(polygon.at(i)).y(),
                    )
                    for i in range(polygon.count())
                ]
                deformable_items.add(uid)
                deformable_vertices[uid] = verts
            elif isinstance(scene_item, PolylineItem):
                verts = [
                    (scene_item.mapToScene(pt).x(), scene_item.mapToScene(pt).y())
                    for pt in scene_item.points
                ]
                deformable_items.add(uid)
                deformable_vertices[uid] = verts

        if item_id not in deformable_vertices:
            return desired_scene_pos

        try:
            x, y = graph.project_to_feasible(
                moving_vertex=vkey,
                desired_scene_pos=(desired_scene_pos.x(), desired_scene_pos.y()),
                item_positions=item_positions,
                anchor_offsets=anchor_offsets,
                deformable_items=deformable_items,
                deformable_vertices=deformable_vertices,
            )
        except Exception:
            return desired_scene_pos
        return QPointF(x, y)

    @property
    def dimension_line_manager(self):
        """Access the dimension line manager."""
        return self._dimension_line_manager

    def apply_theme_colors(self, colors: dict[str, str]) -> None:
        """Update canvas colors from the theme palette.

        Args:
            colors: Theme color dictionary from ThemeColors
        """
        self.CANVAS_COLOR = QColor(colors.get("canvas_background", "#f5f5dc"))
        self.OUTSIDE_COLOR = QColor(colors.get("canvas_outside", "#707070"))
        self.update()

    @property
    def width_cm(self) -> float:
        """Width of the canvas in centimeters."""
        return self._width_cm

    @property
    def height_cm(self) -> float:
        """Height of the canvas in centimeters."""
        return self._height_cm

    @property
    def canvas_rect(self) -> QRectF:
        """Get the actual canvas rectangle (not the scene rect with padding)."""
        return QRectF(0, 0, self._width_cm, self._height_cm)

    def get_command_manager(self):
        """Get the command manager for undo/redo operations."""
        return self._command_manager

    @property
    def guide_lines(self) -> list[GuideLine]:
        """List of persistent guide lines."""
        return self._guide_lines

    def set_guide_lines(self, guides: list[GuideLine]) -> None:
        """Replace the guide line list (used when loading a project).

        Args:
            guides: New list of guide lines.
        """
        self._guide_lines = list(guides)

    def resize_canvas(self, width_cm: float, height_cm: float) -> None:
        """Resize the canvas.

        Args:
            width_cm: New width in centimeters
            height_cm: New height in centimeters
        """
        self._width_cm = width_cm
        self._height_cm = height_cm
        self._update_scene_rect()
        self.update()  # Trigger redraw

    def start_image_calibration(self, image_item) -> None:
        """Start inline calibration mode for an image.

        Args:
            image_item: The BackgroundImageItem to calibrate
        """
        self._calibration_mode = True
        self._calibration_image = image_item
        self._calibration_points.clear()
        self._clear_calibration_markers()

        # Notify views that calibration started
        if self.views():
            self.views()[0].set_status_message(
                "Calibration: Click first point on the image"
            )

    def _clear_calibration_markers(self) -> None:
        """Remove calibration visual markers from the scene."""
        for marker in self._calibration_markers:
            self.removeItem(marker)
        self._calibration_markers.clear()

    def add_calibration_point(self, point: QPointF) -> None:
        """Add a calibration point.

        Args:
            point: The point in scene coordinates
        """
        if not self._calibration_mode or len(self._calibration_points) >= 2:
            return

        self._calibration_points.append(point)
        self._draw_calibration_marker(point)

        if len(self._calibration_points) == 1:
            # After first point, update status
            if self.views():
                self.views()[0].set_status_message(
                    "Calibration: Click second point on the image"
                )
        elif len(self._calibration_points) == 2:
            # After second point, draw line and show input
            self._draw_calibration_line()
            if self.views():
                self.views()[0].show_calibration_input(point)

    def _draw_calibration_marker(self, point: QPointF) -> None:
        """Draw a calibration crosshair marker at the given point.

        Args:
            point: The point in scene coordinates
        """
        pen = QPen(Qt.GlobalColor.red, 2)

        # Draw crosshair
        size = 15
        line_h = QGraphicsLineItem(point.x() - size, point.y(), point.x() + size, point.y())
        line_h.setPen(pen)
        self.addItem(line_h)
        self._calibration_markers.append(line_h)

        line_v = QGraphicsLineItem(point.x(), point.y() - size, point.x(), point.y() + size)
        line_v.setPen(pen)
        self.addItem(line_v)
        self._calibration_markers.append(line_v)


    def _draw_calibration_line(self) -> None:
        """Draw a line between the two calibration points."""
        if len(self._calibration_points) != 2:
            return

        pen = QPen(Qt.GlobalColor.red, 2, Qt.PenStyle.DashLine)
        line = QGraphicsLineItem(QLineF(self._calibration_points[0], self._calibration_points[1]))
        line.setPen(pen)
        line.setZValue(999)
        self.addItem(line)
        self._calibration_markers.append(line)

    def finish_calibration(self, distance_cm: float) -> None:
        """Complete the calibration with the entered distance.

        Args:
            distance_cm: The real-world distance in centimeters
        """
        if not self._calibration_mode or len(self._calibration_points) != 2:
            return

        # Calculate pixel distance
        line = QLineF(self._calibration_points[0], self._calibration_points[1])
        pixel_distance = line.length()

        # Apply calibration to the image
        if self._calibration_image:
            self._calibration_image.calibrate(pixel_distance, distance_cm)

        # Clean up calibration mode
        self.cancel_calibration()

        # Notify view
        if self.views():
            self.views()[0].set_status_message("Calibration complete")

    def cancel_calibration(self) -> None:
        """Cancel calibration mode."""
        self._calibration_mode = False
        self._calibration_image = None
        self._calibration_points.clear()
        self._clear_calibration_markers()

        if self.views():
            self.views()[0].hide_calibration_input()
            self.views()[0].set_status_message("")

    @property
    def is_calibrating(self) -> bool:
        """Whether calibration mode is active."""
        return self._calibration_mode

    # Layer Management

    @property
    def layers(self) -> list[Layer]:
        """Get all layers."""
        return self._layers

    def set_layers(self, layers: list[Layer]) -> None:
        """Set the layers list.

        Args:
            layers: New list of layers
        """
        self._layers = layers
        # Set active layer to first layer if not set or invalid
        if not self._active_layer or self._active_layer not in self._layers:
            self._active_layer = self._layers[0] if self._layers else None
        self.layers_changed.emit()
        self._update_items_visibility()

    def add_layer(self, layer: Layer) -> None:
        """Append a layer at the bottom of the order (lowest z_order).

        This is the low-level primitive used for bulk/import flows (e.g. DXF
        import) where the incoming layer order must be preserved as-is. The
        user-facing "Add Layer" action does NOT use this — it inserts at the top
        of the order via LayersPanel (see FR-LAYER-08 / issue #201).

        Args:
            layer: Layer to add
        """
        self._layers.append(layer)
        self.layers_changed.emit()

    def remove_layer(self, layer_id: UUID) -> bool:
        """Remove a layer by ID.

        Args:
            layer_id: ID of layer to remove

        Returns:
            True if layer was removed, False if not found
        """
        for i, layer in enumerate(self._layers):
            if layer.id == layer_id:
                # Don't allow removing the last layer
                if len(self._layers) <= 1:
                    return False
                # Move items from this layer to another layer
                replacement_layer = self._layers[0] if i > 0 else self._layers[1]
                self._move_items_to_layer(layer_id, replacement_layer.id)
                # Remove the layer
                del self._layers[i]
                # Update active layer if needed
                if self._active_layer and self._active_layer.id == layer_id:
                    self._active_layer = replacement_layer
                    self.active_layer_changed.emit(self._active_layer)
                self.layers_changed.emit()
                return True
        return False

    def _move_items_to_layer(self, from_layer_id: UUID, to_layer_id: UUID) -> None:
        """Move all items from one layer to another.

        Args:
            from_layer_id: Source layer ID
            to_layer_id: Destination layer ID
        """
        for item in self.items():
            if hasattr(item, 'layer_id') and item.layer_id == from_layer_id:
                item.layer_id = to_layer_id

    def reorder_layers(self, new_order: list[Layer]) -> None:
        """Reorder layers.

        Args:
            new_order: New layer order (first in list = top, last = bottom)
        """
        self._layers = new_order
        # Update z_order values based on new position
        # Reverse order: first item in list gets highest z_order (on top)
        for i, layer in enumerate(self._layers):
            layer.z_order = len(self._layers) - 1 - i
        self.layers_changed.emit()
        self._update_items_z_order()

    def _max_existing_rank(self, layer_id: UUID | None) -> int:
        """The highest ``stack_order`` currently used in *layer_id*, or 0.

        One O(n) walk of the scene. See :meth:`_next_stack_order` for the
        cached fast path used while a bulk add is suspended.
        """
        existing = [
            item.stack_order
            for item in self.items()
            if item.parentItem() is None
            and getattr(item, "layer_id", None) == layer_id
            and getattr(item, "stack_order", None) is not None
        ]
        return max(existing) if existing else 0

    def _next_stack_order(self, layer_id: UUID | None) -> int:
        """Smallest never-used rank above every existing top-level item in
        *layer_id* (issue #338). Returns ``STACK_STEP`` for an empty layer.

        While a bulk add is suspended (:meth:`suspend_z_refresh`), the
        per-layer "next rank" is cached in ``self._next_rank_cache`` instead
        of re-walking ``self.items()`` (:meth:`_max_existing_rank`) on every
        single unranked add: that O(n) walk per item made loading N
        legacy (no ``stack_order`` key) objects from an old file O(n^2)
        (review round 2, P2 performance finding). The cache is seeded once
        per layer from one O(n) walk on first use, then just bumped by
        ``STACK_STEP`` on every further call for that layer; it is reset at
        the start of every new (non-nested) suspended scope in
        :meth:`suspend_z_refresh`. :meth:`addItem` also keeps the cache
        honest against an item that already had a rank when it's re-added
        mid-scope (e.g. ``DeleteItemsCommand.undo``) — see the comment
        there — so ranked and unranked adds can interleave within one
        suspended scope without a later unranked item getting assigned a
        lower rank than an already-ranked one added earlier in the same
        scope.
        """
        if self._suspend_z_refresh:
            cached = self._next_rank_cache.get(layer_id)
            base = cached if cached is not None else self._max_existing_rank(layer_id)
            next_rank = base + stacking.STACK_STEP
            self._next_rank_cache[layer_id] = next_rank
            return next_rank
        return self._max_existing_rank(layer_id) + stacking.STACK_STEP

    @contextmanager
    def suspend_z_refresh(self, *, renumber: bool = False) -> Iterator[None]:
        """Suspend the per-``addItem`` z-refresh for a batch of adds (issue #338).

        Wrap a loop of ``scene.addItem(...)`` calls in
        ``with scene.suspend_z_refresh(): ...`` so each add only assigns a
        ``stack_order`` rank (as usual, for an item that doesn't have one
        yet) without doing a full per-layer z recompute; one full refresh
        runs once at the end instead of once per item — even if the loop
        raises partway through, since the refresh runs in a ``finally``.
        Used both by the bulk re-add paths that re-insert several items in
        one command (``CreateItemsCommand.execute``, ``DeleteItemsCommand.undo``,
        ``MirrorItemsCommand.execute``/``undo``, ...) and by
        ``ProjectManager.load``'s item-creation loop (``renumber=True``,
        below) — so loading N items does one z-refresh pass instead of N,
        exception-safely (review round 2, P1-1).

        ``renumber=True`` additionally renumbers every layer's items (in
        their current normalized order) to clean ``STACK_STEP`` multiples
        before the refresh. This is for the file-load path only — it is
        what gives a file saved without ``stack_order`` keys (an older app
        version) honest, evenly-spaced ranks the first time the current app
        loads it. Every other bulk re-add path must NOT renumber, since that
        would silently overwrite the exact ranks a command's undo/redo
        snapshot depends on being restored unchanged.

        Nests safely: an inner suspend inside an already-suspended scope is
        a no-op (the outer scope still does the one refresh on exit).
        """
        already_suspended = self._suspend_z_refresh
        self._suspend_z_refresh = True
        if not already_suspended:
            # Fresh (non-nested) scope: start the per-layer rank cache over
            # -- see _next_stack_order().
            self._next_rank_cache = {}
        try:
            yield
        finally:
            if not already_suspended:
                self._end_suspend_z_refresh(renumber=renumber)

    def _end_suspend_z_refresh(self, *, renumber: bool) -> None:
        """Resume z-refresh and run the one deferred refresh (issue #338).

        Shared tail for :meth:`suspend_z_refresh`, always run from its
        ``finally`` block.
        """
        self._suspend_z_refresh = False
        if renumber:
            for layer_id in self._stacking_layer_ids():
                order = self._normalized_layer_order(layer_id)
                for i, item in enumerate(order):
                    if hasattr(item, "stack_order"):
                        item.stack_order = (i + 1) * stacking.STACK_STEP
        self._update_items_z_order()

    def _stacking_layer_ids(self) -> list[UUID | None]:
        """Every layer id that can carry ranked items: the real layers plus
        the ``None`` pseudo-layer for items that have no layer (issue #338).
        """
        return [layer.id for layer in self._layers] + [None]

    @staticmethod
    def _stack_identity(item: QGraphicsItem) -> object:
        """Stable identity used as ``StackEntry.item_id`` (issue #338).

        The item's UUID when it has one (``item_id``), else Python object
        identity. Any other ``layer_id`` carrier (e.g. a bare
        ``QGraphicsItem`` in a test double) degrades gracefully this way: it
        has no ``item_id``, so it falls back to its object identity, and no
        ``_parent_bed_id``/ROOF_RIDGE metadata, so it never participates in
        the parent/child clamp.
        """
        return getattr(item, "item_id", None) or id(item)

    def _layer_top_level_items(self, layer_id: UUID | None) -> list[QGraphicsItem]:
        """Top-level items of one layer, in raw rank order (issue #338).

        Sort key: ``(stack_order is None, stack_order, current bottom-to-top
        scene index)`` — an unranked item sorts to the top of the layer's
        band; ranked items sort by rank; ties fall back to the scene's
        current stacking so the result is stable. This is NOT yet passed
        through :func:`core.stacking.normalize_order` — see
        :meth:`_normalized_layer_order` and :meth:`_stack_entries`.

        Requires :func:`core.stacking.supports_stacking` — the same
        eligibility predicate :meth:`addItem` uses to decide whether an item
        participates in ranking at all. Without it, ``layer_id=None`` would
        match every top-level item that simply lacks a ``layer_id``
        attribute — the overlay items (dimension lines, measure/constraint
        previews, highlights, offset preview) — and a z-refresh of the
        ``None`` pseudo-layer would sweep them into band ``[0, 100)``,
        destroying their much higher fixed z-values (900-9999) (issue #338
        P0-1).
        """
        bottom_to_top = list(reversed(self.items()))
        scene_index = {id(item): i for i, item in enumerate(bottom_to_top)}

        candidates = [
            item
            for item in bottom_to_top
            if item.parentItem() is None
            and stacking.supports_stacking(item)
            and getattr(item, "layer_id", None) == layer_id
        ]

        def _sort_key(item: QGraphicsItem) -> tuple[bool, int, int]:
            rank = getattr(item, "stack_order", None)
            return (rank is None, rank or 0, scene_index[id(item)])

        candidates.sort(key=_sort_key)
        return candidates

    def _stack_entries(
        self,
        layer_id: UUID | None,
        candidates: list[QGraphicsItem] | None = None,
    ) -> list[stacking.StackEntry]:
        """Build one layer's raw (not-yet-normalized) ``StackEntry`` list (issue #338).

        This is the ONE place that derives ``StackEntry.parent_id``/``rect``
        from live Qt items — used by both :meth:`_normalized_layer_order`
        (for the z-value refresh) and
        ``ui.canvas.arrange.build_arrange_command`` (which feeds it straight
        to :func:`core.stacking.arrange`). There must be exactly one way to
        build entries.

        *candidates*: the layer's top-level items, already computed via
        :meth:`_layer_top_level_items`. Pass it in when the caller already
        has it (as :meth:`_normalized_layer_order` does) so this doesn't
        walk the whole scene a second time — ``scene.items()`` is O(n), and
        every extra walk here is another O(n) hit on every single
        ``addItem`` call (performance finding, issue #338 review). Omit it
        to have this method compute it itself (``build_arrange_command``'s
        case, which doesn't already have the list).
        """
        from open_garden_planner.core.object_types import ObjectType

        if candidates is None:
            candidates = self._layer_top_level_items(layer_id)
        ids_in_layer = {self._stack_identity(item) for item in candidates}

        entries: list[stacking.StackEntry] = []
        for item in candidates:
            parent_id = None
            parent_bed_id = getattr(item, "_parent_bed_id", None)
            if parent_bed_id is not None and parent_bed_id in ids_in_layer:
                parent_id = parent_bed_id
            elif (
                getattr(item, "object_type", None) == ObjectType.ROOF_RIDGE
                and hasattr(item, "get_metadata")
            ):
                owner_id_str = item.get_metadata("owner_polygon_id")
                if owner_id_str:
                    owner_uuid: UUID | None
                    try:
                        owner_uuid = UUID(owner_id_str)
                    except (ValueError, TypeError):
                        owner_uuid = None
                    if owner_uuid is not None and owner_uuid in ids_in_layer:
                        parent_id = owner_uuid
            rect = item.sceneBoundingRect()
            entries.append(
                stacking.StackEntry(
                    item_id=self._stack_identity(item),
                    parent_id=parent_id,
                    rect=(rect.x(), rect.y(), rect.width(), rect.height()),
                )
            )
        return entries

    def _normalized_layer_order(self, layer_id: UUID | None) -> list[QGraphicsItem]:
        """Bottom-to-top order for one layer's top-level items (issue #338).

        Builds this layer's raw rank-ordered :class:`~core.stacking.StackEntry`
        list via :meth:`_stack_entries`, passes it through
        :func:`core.stacking.normalize_order` (which moves every plant to
        immediately above its parent bed and every ROOF_RIDGE to immediately
        above its owner polygon, only when that parent is itself in this same
        layer — the derive-only clamp), then maps the normalized entries back
        to live items.
        """
        candidates = self._layer_top_level_items(layer_id)
        items_by_id = {self._stack_identity(item): item for item in candidates}
        normalized = stacking.normalize_order(
            self._stack_entries(layer_id, candidates)
        )
        return [items_by_id[entry.item_id] for entry in normalized]

    def _refresh_layer_z(self, layer_id: UUID | None) -> None:
        """Set every top-level item in *layer_id* to a derived z-value,
        strictly inside that layer's ``[z_order*100, z_order*100+100)``
        band, per its normalized bottom-to-top position (issue #338).

        ``layer_id=None`` is the pseudo-layer of items without a layer; its
        band is base 0 (where such items always rendered). An id that no
        longer resolves to a layer is left untouched.
        """
        if layer_id is None:
            base = 0
        else:
            layer = self.get_layer_by_id(layer_id)
            if layer is None:
                return
            base = layer.z_order * 100
        order = self._normalized_layer_order(layer_id)
        n = len(order)
        if n == 0:
            return
        for i, item in enumerate(order):
            item.setZValue(base + 100 * (i + 1) / (n + 1))

    def _update_items_z_order(self) -> None:
        """Refresh the derived z-value of every item in every layer."""
        for layer_id in self._stacking_layer_ids():
            self._refresh_layer_z(layer_id)

    def get_layer_by_id(self, layer_id: UUID) -> Layer | None:
        """Get a layer by its ID.

        Args:
            layer_id: Layer ID to find

        Returns:
            Layer if found, None otherwise
        """
        for layer in self._layers:
            if layer.id == layer_id:
                return layer
        return None

    @property
    def active_layer(self) -> Layer | None:
        """Get the active layer."""
        return self._active_layer

    def set_active_layer(self, layer: Layer | None) -> None:
        """Set the active layer.

        Args:
            layer: Layer to set as active
        """
        if layer != self._active_layer:
            self._active_layer = layer
            self.active_layer_changed.emit(layer)

    def _update_items_visibility(self) -> None:
        """Update visibility and interaction of all items based on layer state."""
        for item in self.items():
            if hasattr(item, 'layer_id') and item.layer_id:
                layer = self.get_layer_by_id(item.layer_id)
                if layer:
                    # Set visibility
                    item.setVisible(layer.visible)
                    # Set opacity
                    item.setOpacity(layer.opacity)
                    # Set selectability based on lock state
                    if hasattr(item, 'setFlag'):
                        from PyQt6.QtWidgets import QGraphicsItem
                        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, not layer.locked)
                        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, not layer.locked)

    def update_layer_visibility(self, layer_id: UUID, visible: bool) -> None:
        """Update visibility of a layer and its items.

        Args:
            layer_id: Layer ID
            visible: New visibility state
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.visible = visible
            self._update_items_visibility()
            self.layers_changed.emit()

    def update_layer_lock(self, layer_id: UUID, locked: bool) -> None:
        """Update lock state of a layer and its items.

        Args:
            layer_id: Layer ID
            locked: New lock state
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.locked = locked
            self._update_items_visibility()
            self.layers_changed.emit()

    def update_layer_opacity(self, layer_id: UUID, opacity: float) -> None:
        """Update opacity of a layer and its items.

        Args:
            layer_id: Layer ID
            opacity: New opacity (0.0 to 1.0)
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.opacity = max(0.0, min(1.0, opacity))
            self._update_items_visibility()
            self.layers_changed.emit()

    def preview_layer_opacity(self, layer_id: UUID, opacity: float) -> None:
        """Live, NON-undoable opacity preview during slider drags.

        Same mutation as :meth:`update_layer_opacity` but does NOT emit
        ``layers_changed``, so the layers panel is not rebuilt on every slider
        tick. The final value is committed as one undoable
        ``SetLayerPropertyCommand`` on slider release.

        Args:
            layer_id: Layer ID
            opacity: Preview opacity (0.0 to 1.0)
        """
        layer = self.get_layer_by_id(layer_id)
        if layer:
            layer.opacity = max(0.0, min(1.0, opacity))
            self._update_items_visibility()

    # ── Compare overlay (US-10.7) ─────────────────────────────────────────

    @property
    def compare_overlay_visible(self) -> bool:
        """Whether the previous-season compare overlay is shown."""
        return self._compare_overlay_visible

    def set_compare_overlay(self, objects: list[dict[str, Any]]) -> None:
        """Replace the compare overlay with ghosted plant items from objects.

        Only circle-type objects (plants) are shown in the overlay.
        Existing overlay items are removed first.

        Args:
            objects: List of serialized object dicts from a season file
        """
        self.clear_compare_overlay()

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import is_plant_type

        for obj in objects:
            if obj.get("type") != "circle":
                continue
            obj_type_name = obj.get("object_type")
            try:
                obj_type = ObjectType[obj_type_name] if obj_type_name else None
            except KeyError:
                obj_type = None
            if not is_plant_type(obj_type):
                continue

            cx = obj.get("center_x", 0.0)
            cy = obj.get("center_y", 0.0)
            r = obj.get("radius", 50.0)

            # Draw as a ghost ellipse
            ellipse = QGraphicsEllipseItem(cx - r, cy - r, r * 2, r * 2)
            fill_hex = obj.get("fill_color", "#88aaccaa")
            fill = QColor(fill_hex)
            fill.setAlpha(80)  # ~30% opacity
            ellipse.setBrush(QBrush(fill))
            stroke = QColor(fill_hex)
            stroke.setAlpha(160)
            pen = QPen(stroke, 4.0)
            pen.setStyle(Qt.PenStyle.DashLine)
            ellipse.setPen(pen)
            ellipse.setZValue(1000)  # Render on top
            ellipse.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            ellipse.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            ellipse.setVisible(self._compare_overlay_visible)
            super().addItem(ellipse)
            self._compare_items.append(ellipse)

            # Small label showing the plant name.
            # ItemIgnoresTransformations keeps the text right-side-up despite the
            # canvas Y-flip. Position at (cx, cy + r) — above the circle visually
            # because higher scene Y = visually higher in the flipped canvas.
            name = obj.get("name") or (obj_type.name.title() if obj_type else "")
            if name:
                label = QGraphicsSimpleTextItem(name)
                label.setPos(cx, cy + r)
                label_color = QColor(stroke)
                label_color.setAlpha(200)
                label.setBrush(QBrush(label_color))
                label.setZValue(1001)
                label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
                label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
                label.setVisible(self._compare_overlay_visible)
                super().addItem(label)
                self._compare_items.append(label)

    def clear_compare_overlay(self) -> None:
        """Remove all compare overlay ghost items."""
        for item in self._compare_items:
            super().removeItem(item)
        self._compare_items.clear()

    def clear(self) -> None:
        """Remove all items from the scene.

        Overridden so no private tracking list can outlive the C++ objects
        it references: ``QGraphicsScene.clear()`` destroys every item's
        C++ side, and a Python wrapper left in a tracking list afterwards
        would be dangling — the root cause of #337. Dropping every such
        list here, in one chokepoint, makes every subsequent reader safe
        by construction instead of relying on each call site to guard
        itself. Covers both trackers that hold ``QGraphicsItem``
        references: the compare overlay (``_compare_items``,
        ``_compare_overlay_visible``) and image calibration
        (``_calibration_markers``, ``_calibration_points``,
        ``_calibration_image``, ``_calibration_mode``).
        """
        self._compare_items.clear()
        self._compare_overlay_visible = False
        self._calibration_markers.clear()
        self._calibration_points.clear()
        self._calibration_image = None
        self._calibration_mode = False
        super().clear()

    def set_compare_overlay_visible(self, visible: bool) -> None:
        """Show or hide the compare overlay without removing items.

        Args:
            visible: Whether overlay items should be shown
        """
        self._compare_overlay_visible = visible
        for item in self._compare_items:
            item.setVisible(visible)

    # ------------------------------------------------------------------
    # Plant-bed parent-child helpers
    # ------------------------------------------------------------------

    def find_item_by_id(self, item_id: UUID) -> QGraphicsItem | None:
        """Find a garden item by its UUID.

        Args:
            item_id: The UUID to search for.

        Returns:
            The matching item, or None if not found.
        """
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        for item in self.items():
            if isinstance(item, GardenItemMixin) and item.item_id == item_id:
                return item  # type: ignore[return-value]
        return None

    def find_smallest_bed_containing(self, scene_point: QPointF) -> QGraphicsItem | None:
        """Find the smallest plant-parent whose shape contains *scene_point*.

        Plant-parents are beds, containers, wall planters, and trellises
        (:func:`is_plant_parent_type`). When they are nested (e.g. a raised
        bed inside a garden bed, or a pot inside a bed), the smallest enclosing
        parent is returned so the plant is parented to the most specific one.

        Args:
            scene_point: Point in scene coordinates.

        Returns:
            The best-matching plant-parent item, or None.
        """
        from open_garden_planner.core.object_types import is_plant_parent_type
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        best_bed: QGraphicsItem | None = None
        best_area = float("inf")

        for item in self.items():
            if not isinstance(item, GardenItemMixin):
                continue
            if not is_plant_parent_type(item.object_type):
                continue
            local_pt = item.mapFromScene(scene_point)  # type: ignore[union-attr]
            if item.contains(local_pt):  # type: ignore[union-attr]
                rect = item.boundingRect()  # type: ignore[union-attr]
                area = rect.width() * rect.height()
                if area < best_area:
                    best_area = area
                    best_bed = item  # type: ignore[assignment]

        return best_bed
