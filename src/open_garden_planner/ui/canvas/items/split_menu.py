"""One 'Split Along Line…' context-menu entry for every closed shape (#664).

The four closed-shape classes used to grow their context menus independently;
the boolean entries already repeat. This helper keeps the split entry's
availability and dispatch in one place: every shape asks the same question of
the same view method, and a refusal reason disables the action with the reason
as its tooltip instead of failing after two clicks.
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QGraphicsItem, QMenu


def build_split_action(menu: QMenu, item: QGraphicsItem) -> QAction | None:
    """Append the split entry for *item* when it is a closed shape.

    Returns the action (enabled or disabled), or None for an unsupported item.
    The action's ``triggered`` signal starts the view's split tool for *item*.
    """
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if not isinstance(item, (PolygonItem, RectangleItem, CircleItem, EllipseItem)):
        return None
    scene = item.scene()
    if scene is None:
        return None
    view = next(
        (candidate for candidate in scene.views() if hasattr(candidate, "start_split_shape")),
        None,
    )
    action = menu.addAction(
        QCoreApplication.translate("SplitShapeMenu", "Split Along Line…")
    )
    if action is None:
        return None
    action.setObjectName("split_shape")
    reason_fn = getattr(view, "split_refusal_reason", None)
    start_fn = getattr(view, "start_split_shape", None)
    if not callable(reason_fn) or not callable(start_fn):
        action.setEnabled(False)
        return action
    reason = reason_fn(item)
    action.setEnabled(reason is None)
    if reason is not None:
        action.setToolTip(reason)
        action.setStatusTip(reason)
    action.triggered.connect(
        lambda _checked=False, source=item, start=start_fn: start(source)
    )
    return action


__all__ = ["build_split_action"]
