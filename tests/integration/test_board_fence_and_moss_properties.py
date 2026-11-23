"""End-to-end UI workflow for Board Fence and Moss fill pattern (#960)."""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPolygonF

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.object_types import (
    PATH_FENCE_STYLES,
    ObjectType,
    PathFenceStyle,
)
from open_garden_planner.core.scene3d import context
from open_garden_planner.core.scene3d.builders import production_registry, surfaces
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel
from open_garden_planner.ui.view3d.snapshot import snapshot_records


def _find_combo_index(combo, data) -> int:
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            return i
    return -1


def test_properties_panel_exposes_board_fence_and_moss_end_to_end(qtbot) -> None:
    """Selecting Board Fence and Moss through PropertiesPanel updates 2D, undo/redo, and 3D."""
    from PyQt6.QtWidgets import QComboBox

    scene = CanvasScene()
    cmd_manager = CommandManager()
    panel = PropertiesPanel(command_manager=cmd_manager)
    qtbot.addWidget(panel)

    fence = PolylineItem(
        [QPointF(0.0, 0.0), QPointF(400.0, 0.0)],
        object_type=ObjectType.FENCE,
        name="Boundary",
    )
    scene.addItem(fence)
    panel.set_selected_items([fence])

    combos = panel.findChildren(QComboBox)
    style_combo = next(
        c for c in combos if _find_combo_index(c, PathFenceStyle.WOODEN_FENCE) >= 0
    )
    # Drift guard: every PathFenceStyle defined in object_types must be reachable in the UI.
    for style in PATH_FENCE_STYLES:
        assert _find_combo_index(style_combo, style) >= 0, f"{style.name} missing from PropertiesPanel"

    board_idx = _find_combo_index(style_combo, PathFenceStyle.BOARD_FENCE)
    style_combo.setCurrentIndex(board_idx)
    assert fence.path_fence_style == PathFenceStyle.BOARD_FENCE

    # Undo/redo round-trip
    assert cmd_manager.can_undo
    cmd_manager.undo()
    assert fence.path_fence_style != PathFenceStyle.BOARD_FENCE
    cmd_manager.redo()
    assert fence.path_fence_style == PathFenceStyle.BOARD_FENCE

    # 3D snapshot and build produce the closed board fence mesh
    records = snapshot_records(scene, date(2026, 10, 20), latitude_deg=51.2)
    fence_rec = records[str(fence.item_id)]
    assert fence_rec.params.get("path_style") == "BOARD_FENCE"
    built = production_registry().build(fence_rec)
    assert built and built[0].name == "fence"

    # Moss fill pattern on a LAWN through PropertiesPanel
    lawn = PolygonItem(
        QPolygonF([QPointF(0, 0), QPointF(400, 0), QPointF(400, 300), QPointF(0, 300)]),
        object_type=ObjectType.LAWN,
        name="Moss Patch",
    )
    lawn.fill_color = QColor(75, 99, 55, 255)
    scene.addItem(lawn)
    panel.set_selected_items([lawn])

    combos = panel.findChildren(QComboBox)
    pattern_combo = next(
        c for c in combos if _find_combo_index(c, FillPattern.GRASS) >= 0
    )
    moss_idx = _find_combo_index(pattern_combo, FillPattern.MOSS)
    assert moss_idx >= 0, "FillPattern.MOSS missing from PropertiesPanel"
    pattern_combo.setCurrentIndex(moss_idx)
    assert lawn.fill_pattern == FillPattern.MOSS

    # October 3D snapshot keeps moss evergreen (no grass-dormancy browning) and dense
    records = snapshot_records(scene, date(2026, 10, 20), latitude_deg=51.2)
    context.with_context(records)
    moss_rec = records[str(lawn.item_id)]
    assert moss_rec.params.get("surface_pattern") == "MOSS"
    assert moss_rec.material.fill_rgba[:3] == (75, 99, 55)
    assert moss_rec.params["lawn_blades"] > int(surfaces.BLADES_PER_M2 * 12.0) * 3
    moss_parts = production_registry().build(moss_rec)
    assert moss_parts and moss_parts[0].name == surfaces.LAWN_BLADES
    assert float(moss_parts[0].mesh.positions[:, 2].max()) <= surfaces.MOSS_BLADE_CM * 1.3 + 0.31
