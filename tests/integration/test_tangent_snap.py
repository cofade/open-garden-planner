"""End-to-end tangent snap (Phase 13 Package B — US-B6)."""

from __future__ import annotations

import math
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import TangentSnapProvider
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.items import CircleItem


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(900, 600)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_default_disabled(window: GardenPlannerApp) -> None:
    assert window._tangent_snap_action.isChecked() is False
    assert not window.canvas_view._snap_registry.has(TangentSnapProvider)


def test_action_persists_setting(window: GardenPlannerApp) -> None:
    from open_garden_planner.app.settings import get_settings

    window._tangent_snap_action.setChecked(True)
    window._on_toggle_tangent_snap(True)
    assert get_settings().tangent_snap_enabled is True
    assert window.canvas_view._snap_registry.has(TangentSnapProvider)

    window._tangent_snap_action.setChecked(False)
    window._on_toggle_tangent_snap(False)
    assert get_settings().tangent_snap_enabled is False
    assert not window.canvas_view._snap_registry.has(TangentSnapProvider)
    get_settings().tangent_snap_enabled = False


def test_tangent_from_polyline_anchor(window: GardenPlannerApp) -> None:
    """Anchor at (1200, 1000); circle at (1000, 1000) radius 100.
    Distance d = 200, alpha = 60°; tangent points at (1050, 1000±86.60).
    Cursor near the upper tangent → snap fires with TANGENT kind."""
    window.canvas_view.set_snap_enabled(False)

    circle = CircleItem(1000, 1000, 100)
    window.canvas_view.scene().addItem(circle)

    # Isolate tangent — disable other providers that might fire on the
    # circle (endpoint/center/edge would otherwise dominate at higher
    # priority).
    window._on_toggle_object_snap(False)
    window._on_toggle_midpoint_snap(False)
    window._on_toggle_intersection_snap(False)
    window._on_toggle_tangent_snap(True)

    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool

    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    tool.mouse_press(event, QPointF(1200, 1000))
    assert tool.last_point is not None

    expected_y = 1000 - math.sqrt(3) / 2 * 100  # upper tangent in Y-down
    # Cursor 2 px above the upper tangent point.
    snapped, candidate = window.canvas_view.anchor_snap(
        QPointF(1050, expected_y - 2)
    )
    assert candidate is not None, "tangent snap should have fired"
    assert candidate.kind == SnapCandidateKind.TANGENT
    assert abs(snapped.x() - 1050) < 1e-4
    assert abs(snapped.y() - expected_y) < 1e-4

    tool.cancel()
    window.canvas_view.set_snap_enabled(True)
    window._on_toggle_object_snap(True)
    window._on_toggle_midpoint_snap(True)
    window._on_toggle_intersection_snap(True)
    window._on_toggle_tangent_snap(False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
