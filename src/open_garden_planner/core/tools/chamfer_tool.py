"""Chamfer tool — bevel a corner with a straight cut (Phase 13 Package B — US-B3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QInputDialog

from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.cad_geometry import chamfer_corner
from open_garden_planner.core.commands import ChamferCornerCommand
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.core.tools.corner_edit_base import (
    CornerEditTool,
    CornerTarget,
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
            ).format(distance=self._distance)
            self._view.set_status_message(msg)

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

        new_host = rebuild_with_corner_replaced(
            target, cut_in_scene, cut_out_scene
        )
        if new_host is None:
            return

        cmd = ChamferCornerCommand(
            scene=self._view.scene(),
            original_item=target.item,
            new_item=new_host,
        )
        self._view.command_manager.execute(cmd)

    def _notify_too_large(self) -> None:
        msg = QCoreApplication.translate(
            "ChamferTool", "Chamfer distance too large for this corner"
        )
        if hasattr(self._view, "set_status_message"):
            self._view.set_status_message(msg)
