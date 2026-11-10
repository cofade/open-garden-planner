"""Fillet tool — round a corner by baking a tangent arc into the host (US-B3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QPointF, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QInputDialog

from open_garden_planner.config.settings import get_settings
from open_garden_planner.core.cad_geometry import fillet_corner, sample_arc_points
from open_garden_planner.core.commands import FilletCornerCommand
from open_garden_planner.core.i18n import LocalizedNumber
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.corner_edit_base import (
    CornerEditRefusal,
    CornerEditTool,
    CornerTarget,
    corner_edit_refusal,
    rebuild_with_corner_replaced,
)

if TYPE_CHECKING:
    from open_garden_planner.ui.canvas.canvas_view import CanvasView


class FilletTool(CornerEditTool):
    """Round one corner of a polyline / polygon / rectangle.

    The tangent arc is sampled into the host item's own vertex list
    (``cad_geometry.sample_arc_points``), so the rounded corner is part of the
    shape: it moves, saves, groups and undoes as one object. The old tool added
    a free-standing ``ArcItem`` that stayed behind when the host moved.

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

    def _translated_name(self) -> str:
        return QCoreApplication.translate("FilletTool", "Fillet")

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._radius: float = get_settings().fillet_last_radius_cm

    def activate(self) -> None:
        super().activate()
        if hasattr(self._view, "set_status_message"):
            msg = QCoreApplication.translate(
                "FilletTool",
                "Fillet radius: {radius:.1f} cm — press R to change",
            ).format(radius=LocalizedNumber(self._radius))
            self._view.set_status_message(msg)
        # Defer the modal dialog onto the next event-loop tick so tool
        # activation fully completes first and the canvas keeps its mouse
        # focus / hover tracking after the dialog closes. Running the
        # modal synchronously inside `activate()` was leaving the view
        # unable to receive mouse_move events afterwards (PR #191
        # manual-test feedback). Skipped under offscreen Qt (CI / tests).
        if _is_interactive_platform():
            QTimer.singleShot(0, self._prompt_for_radius_and_refocus)

    def _prompt_for_radius_and_refocus(self) -> None:
        self._prompt_for_radius()
        # Explicitly hand focus back to the view so the next mouse_move
        # is delivered to this tool. QInputDialog.exec() can leave focus
        # on the dialog's parent rather than on the graphics view itself.
        if hasattr(self._view, "viewport"):
            self._view.viewport().setMouseTracking(True)
        if hasattr(self._view, "setFocus"):
            self._view.setFocus()

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
        refusal = corner_edit_refusal(target)
        if refusal is not None:
            self._notify_refusal(refusal)
            return

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
        radius = _radial_distance(arc_center, tin_scene)
        replacement = [
            tin_scene,
            *sample_arc_points(arc_center, radius, start_deg, span_deg),
            tout_scene,
        ]

        new_host = rebuild_with_corner_replaced(target, replacement)
        if new_host is None:
            self._notify_refusal(CornerEditRefusal.CONSTRAINT)
            return

        cmd = FilletCornerCommand(
            scene=self._view.scene(),
            original_item=target.item,
            new_item=new_host,
            vertex_index=target.vertex_index,
            inserted_count=len(replacement),
        )
        # A cut corner changes which plants the bed contains: reconcile the
        # membership in the SAME undo step (#443/PF-CAN-32, round-5 review P1).
        from open_garden_planner.core.commands import (
            Command,
            CompoundCommand,
            ReconcileBedMembershipCommand,
        )

        command: Command = cmd
        scene = self._view.scene()
        item_id = getattr(target.item, "item_id", None)
        if scene is not None and item_id is not None:
            reconcile = ReconcileBedMembershipCommand(
                scene, focus_parents={item_id}
            )
            command = CompoundCommand([cmd, reconcile], cmd.description)
        self._view.command_manager.execute(command)

    def _notify_too_large(self) -> None:
        msg = QCoreApplication.translate(
            "FilletTool", "Fillet radius too large for this corner"
        )
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(msg)

    def _notify_refusal(self, refusal: CornerEditRefusal) -> None:
        messages = {
            CornerEditRefusal.GROUPED: QCoreApplication.translate(
                "FilletTool",
                "Cannot edit this corner: the object is inside a group",
            ),
            CornerEditRefusal.UNSUPPORTED_TYPE: QCoreApplication.translate(
                "FilletTool",
                "Cannot edit this corner: this object type has no polygonal form",
            ),
            CornerEditRefusal.CONSTRAINT: QCoreApplication.translate(
                "FilletTool",
                "Cannot edit this corner: a constraint is attached to it or to its edges",
            ),
        }
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(messages[refusal])


def _radial_distance(center: QPointF, p: QPointF) -> float:
    import math

    return math.hypot(p.x() - center.x(), p.y() - center.y())


def _is_interactive_platform() -> bool:
    """Skip activation prompts under the offscreen Qt platform used by CI/tests."""
    app = QApplication.instance()
    return app is not None and app.platformName() != "offscreen"
