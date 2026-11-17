"""Object frames shared by editing, snapping and alignment.

Paint bounds include diagnostic decorations. They must not decide where an
object aligns, snaps or receives its editing decorations.
"""

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsItemGroup


def selection_frame_rect(item: QGraphicsItem) -> QRectF:
    """Return the object's own outline bounds in its local coordinates."""
    if isinstance(item, QGraphicsItemGroup):
        result = QRectF()
        children = item.childItems()
        # Garden groups can also own a name label; only document members count.
        members = [child for child in children if hasattr(child, "item_id")]
        for child in members or children:
            result = result.united(child.mapRectToParent(selection_frame_rect(child)))
        return result
    rect_fn = getattr(item, "rect", None)
    if callable(rect_fn):
        return QRectF(rect_fn())
    polygon_fn = getattr(item, "polygon", None)
    if callable(polygon_fn):
        return QRectF(polygon_fn().boundingRect())
    return item.boundingRect()


def scene_frame_rect(item: QGraphicsItem) -> QRectF:
    """Return the axis-aligned object frame in scene coordinates."""
    return item.mapRectToScene(selection_frame_rect(item))


def object_outline(item: QGraphicsItem) -> QPainterPath:
    """The filled geometric outline, without a pen or diagnostic decorations."""
    path = QPainterPath()
    polygon = getattr(item, "polygon", None)
    if callable(polygon):
        path.addPolygon(polygon())
        path.closeSubpath()
    elif isinstance(item, QGraphicsEllipseItem):
        path.addEllipse(item.rect())
    else:
        path.addRect(selection_frame_rect(item))
    return path
