"""Chamfer tool — bevel a corner with a straight cut (Phase 13 Package B — US-B3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QInputDialog

from open_garden_planner.config.settings import get_settings
from open_garden_planner.core.cad_geometry import chamfer_corner
from open_garden_planner.core.commands import ChamferCornerCommand
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


class ChamferTool(CornerEditTool):
    """Bevel one corner of a polyline / polygon / rectangle with a straight cut.

    Workflow mirrors ``FilletTool`` (``Shift+C`` shortcut, ``D`` mid-session
    to change distance), but the corner is replaced with a single straight
    segment instead of an arc — so no ``ArcItem`` is created and the host
    item alone carries the new geometry.
    """

    tool_type = ToolType.CHAMFER
    display_name = QCoreApplication.translate("ChamferTool", "Chamfer")
    shortcut = "Shift+C"

    def __init__(self, view: CanvasView) -> None:
        super().__init__(view)
        self._distance: float = get_settings().chamfer_last_distance_cm

    def activate(self) -> None:
        super().activate()
        if hasattr(self._view, "set_status_message"):
            msg = QCoreApplication.translate(
                "ChamferTool",
                "Chamfer distance: {distance:.1f} cm — press D to change",
            ).format(distance=LocalizedNumber(self._distance))
            self._view.set_status_message(msg)
        # Defer the modal dialog onto the next event-loop tick — see the
        # matching note in `FilletTool.activate()`.
        if _is_interactive_platform():
            QTimer.singleShot(0, self._prompt_for_distance_and_refocus)

    def _prompt_for_distance_and_refocus(self) -> None:
        self._prompt_for_distance()
        if hasattr(self._view, "viewport"):
            self._view.viewport().setMouseTracking(True)
        if hasattr(self._view, "setFocus"):
            self._view.setFocus()

    def key_press(self, event: QKeyEvent) -> bool:
        from PyQt6.QtCore import Qt

        if event.key() == Qt.Key.Key_D:
            self._prompt_for_distance()
            return True
        return super().key_press(event)

    def _prompt_for_distance(self) -> None:
        title = QCoreApplication.translate("ChamferTool", "Chamfer")
        label = QCoreApplication.translate("ChamferTool", "Distance (cm):")
        value, ok = QInputDialog.getDouble(
            self._view,
            title,
            label,
            self._distance,
            0.01,
            100000.0,
            2,
        )
        if ok:
            self._distance = float(value)
            get_settings().chamfer_last_distance_cm = self._distance

    # ── Apply the chamfer ─────────────────────────────────────────────

    def apply_to_target(self, target: CornerTarget) -> None:
        refusal = corner_edit_refusal(target)
        if refusal is not None:
            self._notify_refusal(refusal)
            return

        result = chamfer_corner(
            target.p_prev_scene,
            target.p_corner_scene,
            target.p_next_scene,
            self._distance,
        )
        if result is None:
            self._notify_too_large()
            return

        cut_in_scene, cut_out_scene = result
        replacement = [cut_in_scene, cut_out_scene]

        new_host = rebuild_with_corner_replaced(target, replacement)
        if new_host is None:
            self._notify_refusal(CornerEditRefusal.CONSTRAINT)
            return

        cmd = ChamferCornerCommand(
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
            "ChamferTool", "Chamfer distance too large for this corner"
        )
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(msg)

    def _notify_refusal(self, refusal: CornerEditRefusal) -> None:
        messages = {
            CornerEditRefusal.GROUPED: QCoreApplication.translate(
                "ChamferTool",
                "Cannot edit this corner: the object is inside a group",
            ),
            CornerEditRefusal.UNSUPPORTED_TYPE: QCoreApplication.translate(
                "ChamferTool",
                "Cannot edit this corner: this object type has no polygonal form",
            ),
            CornerEditRefusal.CONSTRAINT: QCoreApplication.translate(
                "ChamferTool",
                "Cannot edit this corner: a constraint is attached to it or to its edges",
            ),
        }
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(messages[refusal])


def _is_interactive_platform() -> bool:
    """Skip activation prompts under the offscreen Qt platform used by CI/tests."""
    app = QApplication.instance()
    return app is not None and app.platformName() != "offscreen"
