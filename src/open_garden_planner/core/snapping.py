"""Object snapping engine for snap-to-object alignment.

Detects nearby object edges and centers during drag operations,
returning snap positions and visual guide line data.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtWidgets import QGraphicsItem


@dataclass
class SnapGuide:
    """A visual guide line to render during snapping."""

    start: QPointF
    end: QPointF
    is_horizontal: bool


@dataclass
class SnapResult:
    """Result of a snap operation."""

    snapped_pos: QPointF
    snapped_x: bool = False
    snapped_y: bool = False
    guides: list[SnapGuide] = field(default_factory=list)


class ObjectSnapper:
    """Computes snap-to-object positions during drag operations.

    Collects edges and centers from all scene items (excluding dragged items)
    and finds the nearest snap targets within a threshold.
    """

    def __init__(self, threshold: float = 10.0) -> None:
        """Initialize the snapper.

        Args:
            threshold: Snap distance threshold in scene units (cm).
        """
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        """Current snap threshold in scene units."""
        return self._threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        """Set snap threshold."""
        self._threshold = max(1.0, value)

    @staticmethod
    def _get_snap_values(item: QGraphicsItem) -> tuple[list[float], list[float]]:
        """Extract horizontal and vertical snap values from an item.

        Returns x-values (left, center, right) and y-values (top, center, bottom)
        from the item's scene bounding rect.

        Args:
            item: A graphics item on the scene.

        Returns:
            Tuple of (x_values, y_values) in scene coordinates.
        """
        rect = item.sceneBoundingRect()
        x_vals = [rect.left(), rect.center().x(), rect.right()]
        y_vals = [rect.top(), rect.center().y(), rect.bottom()]
        return x_vals, y_vals

    def snap(
        self,
        dragged_rect: QRectF,
        scene_items: list[QGraphicsItem],
        exclude: set[QGraphicsItem] | None = None,
        canvas_rect: QRectF | None = None,
        extra_x: list[float] | None = None,
        extra_y: list[float] | None = None,
    ) -> SnapResult:
        """Compute the snap offset for a dragged bounding rect.

        Compares left/center/right and top/center/bottom of the dragged rect
        against the same values of all other items, finding the closest match.

        Args:
            dragged_rect: The bounding rect of the dragged selection in scene coords.
            scene_items: All items in the scene.
            exclude: Items to exclude from snap targets (the dragged items).
            canvas_rect: Optional canvas boundary rect for guide extent.
            extra_x: Additional fixed X snap positions (e.g. vertical guide lines).
            extra_y: Additional fixed Y snap positions (e.g. horizontal guide lines).

        Returns:
            SnapResult with the adjusted position and guide lines.
        """
        if exclude is None:
            exclude = set()

        # Collect snap x/y values from target items
        target_x_values: list[float] = list(extra_x) if extra_x else []
        target_y_values: list[float] = list(extra_y) if extra_y else []

        for item in scene_items:
            if item in exclude:
                continue
            # Skip items that aren't selectable (background images, etc.)
            if not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable):
                continue
            x_vals, y_vals = self._get_snap_values(item)
            target_x_values.extend(x_vals)
            target_y_values.extend(y_vals)

        # Snap x/y values from the dragged rect
        drag_x_vals = [dragged_rect.left(), dragged_rect.center().x(), dragged_rect.right()]
        drag_y_vals = [dragged_rect.top(), dragged_rect.center().y(), dragged_rect.bottom()]

        # Find best X snap
        best_dx: float | None = None
        best_x_distance = self._threshold
        snap_x_target: float | None = None

        for dx in drag_x_vals:
            for tx in target_x_values:
                dist = abs(dx - tx)
                if dist < best_x_distance:
                    best_x_distance = dist
                    best_dx = tx - dx
                    snap_x_target = tx

        # Find best Y snap
        best_dy: float | None = None
        best_y_distance = self._threshold
        snap_y_target: float | None = None

        for dy in drag_y_vals:
            for ty in target_y_values:
                dist = abs(dy - ty)
                if dist < best_y_distance:
                    best_y_distance = dist
                    best_dy = ty - dy
                    snap_y_target = ty

        # Compute snapped position (offset from dragged_rect top-left)
        dx_offset = best_dx if best_dx is not None else 0.0
        dy_offset = best_dy if best_dy is not None else 0.0

        snapped_pos = QPointF(dx_offset, dy_offset)

        # Build guide lines
        guides: list[SnapGuide] = []
        extent = canvas_rect if canvas_rect else QRectF(0, 0, 10000, 10000)

        if snap_x_target is not None:
            # Vertical guide line at the snap x position
            guides.append(SnapGuide(
                start=QPointF(snap_x_target, extent.top()),
                end=QPointF(snap_x_target, extent.bottom()),
                is_horizontal=False,
            ))

        if snap_y_target is not None:
            # Horizontal guide line at the snap y position
            guides.append(SnapGuide(
                start=QPointF(extent.left(), snap_y_target),
                end=QPointF(extent.right(), snap_y_target),
                is_horizontal=True,
            ))

        return SnapResult(
            snapped_pos=snapped_pos,
            snapped_x=best_dx is not None,
            snapped_y=best_dy is not None,
            guides=guides,
        )
