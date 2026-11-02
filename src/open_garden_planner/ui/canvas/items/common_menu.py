"""Shared repeat actions; shape and bed capability guards stay with each item."""

from dataclasses import dataclass

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QGraphicsScene, QMenu


def _labels(context: str) -> tuple[str, ...]:
    # Literal contexts retain the existing catalogs when menu code moves.
    return {
        "RectangleItem": (
            QCoreApplication.translate("RectangleItem", "Duplicate"),
            QCoreApplication.translate("RectangleItem", "Create Linear Array..."),
            QCoreApplication.translate("RectangleItem", "Create Grid Array..."),
            QCoreApplication.translate("RectangleItem", "Create Circular Array..."),
        ),
        "CircleItem": (
            QCoreApplication.translate("CircleItem", "Duplicate"),
            QCoreApplication.translate("CircleItem", "Create Linear Array..."),
            QCoreApplication.translate("CircleItem", "Create Grid Array..."),
            QCoreApplication.translate("CircleItem", "Create Circular Array..."),
        ),
        "EllipseItem": (
            QCoreApplication.translate("EllipseItem", "Duplicate"),
            QCoreApplication.translate("EllipseItem", "Create Linear Array..."),
            QCoreApplication.translate("EllipseItem", "Create Grid Array..."),
            QCoreApplication.translate("EllipseItem", "Create Circular Array..."),
        ),
        "PolygonItem": (
            QCoreApplication.translate("PolygonItem", "Duplicate"),
            QCoreApplication.translate("PolygonItem", "Create Linear Array..."),
            QCoreApplication.translate("PolygonItem", "Create Grid Array..."),
            QCoreApplication.translate("PolygonItem", "Create Circular Array..."),
        ),
        "PolylineItem": (
            QCoreApplication.translate("PolylineItem", "Duplicate"),
            QCoreApplication.translate("PolylineItem", "Create Linear Array..."),
            QCoreApplication.translate("PolylineItem", "Create Grid Array..."),
            QCoreApplication.translate("PolylineItem", "Create Circular Array..."),
        ),
    }[context]


@dataclass(frozen=True)
class RepeatActions:
    """The common menu owns action identity; the view owns every command."""

    actions: tuple[QAction, ...]

    def dispatch(self, action: QAction | None, scene: QGraphicsScene | None) -> bool:
        if action is None or action not in self.actions:
            return False
        methods = ("duplicate_selected", "create_linear_array", "create_grid_array",
                   "create_circular_array")
        if scene is not None and scene.views():
            method = getattr(scene.views()[0], methods[self.actions.index(action)], None)
            if callable(method):
                method()
        return True


def build_repeat_actions(menu: QMenu, context: str) -> RepeatActions:
    actions = []
    for label in _labels(context):
        action = menu.addAction(label)
        assert action is not None  # the string overload constructs an action
        actions.append(action)
    return RepeatActions(tuple(actions))


def dispatch_delete_selection(scene: QGraphicsScene | None) -> bool:
    """Delete the scene selection through the canvas view's undo-aware path.

    A menu that called ``scene.removeItem`` itself bypassed the command stack,
    and a HOUSE's metadata-linked roof ridge is not a Qt child: the direct call
    left the ridge in the plan (round-5 review of #690). The view owns the one
    deletion implementation — linked ridges, constraints and journal-note
    pruning included — exactly as the Delete key does.
    """
    if scene is None:
        return False
    for view in scene.views():
        handler = getattr(view, "_delete_selected_items", None)
        if callable(handler):
            handler()
            return True
    # A bare QGraphicsScene (unit probes) has no view to own the command; the
    # destructive fallback stays available rather than leaving Delete inert.
    for selected in scene.selectedItems():
        scene.removeItem(selected)
    return True
