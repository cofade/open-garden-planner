"""Fillet tool — round a corner with a tangent arc (Phase 13 Package B — US-B3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QGraphicsItem, QInputDialog

from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.cad_geometry import fillet_corner
from open_garden_planner.core.commands import FilletCornerCommand
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.corner_edit_base import (
    CornerEditTool,
    CornerTarget,
    rebuild_with_corner_replaced,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class FilletTool(CornerEditTool):
    """Round one corner of a polyline / polygon / rectangle.

    Workflow:
        1. Activate (``Shift+F``) — a dialog asks for the fillet radius;
           default is the last used value.
        2. Hover near any internal polyline vertex, polygon vertex, or
           rectangle corner; the corner is highlighted.
        3. Left-click commits the fillet. If the radius is too large for
           the corner the click is ignored and a hint shown in the
           status bar.
        4. Press ``R`` mid-session to change the radius without
           re-activating the tool.
    """

    tool_type = ToolType.FILLET
    display_name = QCoreApplication.translate("FilletTool", "Fillet")
    shortcut = "Shift+F"

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._radius: float = get_settings().fillet_last_radius_cm

    def activate(self) -> None:
        super().activate()
        # Show the current radius in the status bar so the user knows what
        # will be applied. R re-opens the input dialog if they want to
        # change it. We deliberately do NOT pop a modal dialog on
        # activation — it blocks under offscreen Qt (broken in CI) and
        # interrupts users who already filleted at the right radius.
        if hasattr(self._view, "set_status_message"):
            msg = QCoreApplication.translate(
                "FilletTool",
                "Fillet radius: {radius:.1f} cm — press R to change",
            ).format(radius=self._radius)
            self._view.set_status_message(msg)

    def key_press(self, event: QKeyEvent) -> bool:
        from PyQt6.QtCore import Qt

        if event.key() == Qt.Key.Key_R:
            self._prompt_for_radius()
            return True
        return super().key_press(event)

    def _prompt_for_radius(self) -> None:
        title = QCoreApplication.translate("FilletTool", "Fillet")
        label = QCoreApplication.translate("FilletTool", "Radius (cm):")
        value, ok = QInputDialog.getDouble(
            self._view,
            title,
            label,
            self._radius,
            0.01,
            100000.0,
            2,
        )
        if ok:
            self._radius = float(value)
            get_settings().fillet_last_radius_cm = self._radius

    # ── Apply the fillet ──────────────────────────────────────────────

    def apply_to_target(self, target: CornerTarget) -> None:
        result = fillet_corner(
            target.p_prev_scene,
            target.p_corner_scene,
            target.p_next_scene,
            self._radius,
        )
        if result is None:
            self._notify_too_large()
            return

        tin_scene, tout_scene, arc_center, start_deg, span_deg = result

        # Build the arc as a free-standing scene item — fillets always
        # land in scene space because they need to align with the
        # modified host item, which may be rotated.
        from open_garden_planner.ui.canvas.items.arc_item import ArcItem

        radius = _radial_distance(arc_center, tin_scene)
        if radius < 0.5:  # ArcItem minimum
            self._notify_too_large()
            return

        arc_item = ArcItem(
            center=arc_center,
            radius=radius,
            start_deg=start_deg,
            span_deg=span_deg,
            layer_id=_layer_of(target.item),
        )

        new_host = rebuild_with_corner_replaced(
            target, tin_scene, tout_scene
        )
        if new_host is None:
            return

        cmd = FilletCornerCommand(
            scene=self._view.scene(),
            original_item=target.item,
            new_item=new_host,
            arc_item=arc_item,
        )
        self._view.command_manager.execute(cmd)

    def _notify_too_large(self) -> None:
        msg = QCoreApplication.translate(
            "FilletTool", "Fillet radius too large for this corner"
        )
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(msg)


def _radial_distance(center: QPointF, p: QPointF) -> float:
    import math

    return math.hypot(p.x() - center.x(), p.y() - center.y())


def _layer_of(item: QGraphicsItem) -> object:
    return getattr(item, "layer_id", None)
