"""Shared scene-region renderer used by PNG export and Paper Space viewports.

Both consumers need to:
  - hide selection handles / construction geometry / overlay badges
  - tweak text sizes so labels stay readable in the output
  - paint a region of the source ``QGraphicsScene`` into a target
    rectangle on an arbitrary painter, with the correct Y-flip applied
  - restore everything afterwards even on failure

The export service used to do all of this inline; the paper-space
viewport item needs the same logic but rasterising to a pixmap. This
module is the one place that knows how to do it, so the two callers
stay tiny.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import (
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsTextItem,
)


@contextmanager
def _hidden_overlay_items(scene: QGraphicsScene) -> Iterator[None]:
    """Temporarily hide selection handles + soil reminder badges."""
    from open_garden_planner.ui.canvas.items.resize_handle import (
        MidpointHandle,
        RectCornerHandle,
        ResizeHandle,
        RotationHandle,
        VertexHandle,
    )
    from open_garden_planner.ui.canvas.items.soil_badge_item import SoilBadgeItem

    handle_types = (
        ResizeHandle,
        RotationHandle,
        MidpointHandle,
        RectCornerHandle,
        VertexHandle,
        SoilBadgeItem,
    )
    hidden: list[object] = []
    previously_selected = list(scene.selectedItems())
    for item in scene.items():
        if isinstance(item, handle_types) and item.isVisible():
            item.setVisible(False)
            hidden.append(item)
    scene.clearSelection()
    try:
        yield
    finally:
        for item in hidden:
            item.setVisible(True)  # type: ignore[union-attr]
        for item in previously_selected:
            item.setSelected(True)  # type: ignore[union-attr]


@contextmanager
def _hidden_construction_items(scene: QGraphicsScene) -> Iterator[None]:
    """Temporarily hide construction geometry (helper lines / circles)."""
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionCircleItem,
        ConstructionLineItem,
    )

    hidden: list[object] = []
    for item in scene.items():
        if (
            isinstance(item, (ConstructionLineItem, ConstructionCircleItem))
            and item.isVisible()
        ):
            item.setVisible(False)
            hidden.append(item)
    try:
        yield
    finally:
        for item in hidden:
            item.setVisible(True)  # type: ignore[union-attr]


@contextmanager
def _scaled_text(scene: QGraphicsScene, point_size: int) -> Iterator[None]:
    """Temporarily resize all text items to ``point_size``.

    Text in the source scene is set up for screen viewing; in a smaller
    paper-space viewport the same font would dominate. Callers pass an
    explicit point size so the same helper works at any zoom.
    """
    saved: list[tuple[object, QFont]] = []
    for item in scene.items():
        if isinstance(item, (QGraphicsSimpleTextItem, QGraphicsTextItem)):
            saved.append((item, QFont(item.font())))
            f = QFont(item.font())
            f.setPointSize(max(4, point_size))
            item.setFont(f)
    try:
        yield
    finally:
        for item, original in saved:
            item.setFont(original)  # type: ignore[union-attr]


def render_scene_region(
    scene: QGraphicsScene,
    painter: QPainter,
    target_rect: QRectF,
    source_rect: QRectF,
    *,
    hide_overlays: bool = True,
    hide_construction: bool = True,
    text_point_size: int | None = None,
    y_flip: bool = True,
) -> None:
    """Render ``source_rect`` of ``scene`` into ``target_rect`` on ``painter``.

    The source scene's Y axis points down in Qt coordinates but the
    application paints it Y-up; ``y_flip=True`` applies the standard
    pre-flip used by all visual outputs (PNG, PDF, viewport thumbnails).

    Args:
        scene: Source ``QGraphicsScene``.
        painter: Active painter to draw into.
        target_rect: Destination rectangle in painter coords.
        source_rect: Source rectangle in scene coords (the area to render).
        hide_overlays: If True, hide selection handles and soil badges
            for the duration of the render.
        hide_construction: If True, hide construction-geometry items.
        text_point_size: If set, force all text items to this point size.
            Pass ``None`` (default) to leave the source scene's fonts
            untouched — useful when the caller has already prepared them.
        y_flip: If True, apply the standard Y-flip so scene "up" maps to
            target "up".
    """
    overlay_ctx = (
        _hidden_overlay_items(scene)
        if hide_overlays
        else _noop_context()
    )
    construction_ctx = (
        _hidden_construction_items(scene)
        if hide_construction
        else _noop_context()
    )
    text_ctx = (
        _scaled_text(scene, text_point_size)
        if text_point_size is not None
        else _noop_context()
    )

    with overlay_ctx, construction_ctx, text_ctx:
        painter.save()
        if y_flip:
            painter.translate(target_rect.x(), target_rect.y() + target_rect.height())
            painter.scale(1.0, -1.0)
            local_target = QRectF(0, 0, target_rect.width(), target_rect.height())
            scene.render(painter, local_target, source_rect)
        else:
            scene.render(painter, target_rect, source_rect)
        painter.restore()


@contextmanager
def _noop_context() -> Iterator[None]:
    yield
