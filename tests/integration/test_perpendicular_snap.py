"""End-to-end perpendicular snap (Phase 13 Package B — US-B5).

Verifies the full plumbing:
  active tool's ``last_point`` → ``CanvasView.anchor_snap`` →
  ``PerpendicularSnapProvider`` (with ``reference_point``) → snap result.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import PerpendicularSnapProvider
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(900, 600)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_default_disabled(window: GardenPlannerApp) -> None:
    assert window._perpendicular_snap_action.isChecked() is False
    assert not window.canvas_view._snap_registry.has(PerpendicularSnapProvider)


def test_action_persists_setting(window: GardenPlannerApp) -> None:
    from open_garden_planner.app.settings import get_settings

    window._perpendicular_snap_action.setChecked(True)
    window._on_toggle_perpendicular_snap(True)
    assert get_settings().perpendicular_snap_enabled is True
    assert window.canvas_view._snap_registry.has(PerpendicularSnapProvider)

    window._perpendicular_snap_action.setChecked(False)
    window._on_toggle_perpendicular_snap(False)
    assert get_settings().perpendicular_snap_enabled is False
    assert not window.canvas_view._snap_registry.has(PerpendicularSnapProvider)
    get_settings().perpendicular_snap_enabled = False


def test_without_active_anchor_no_perpendicular_snap(
    window: GardenPlannerApp,
) -> None:
    """Select tool has no last_point → perpendicular yields nothing,
    so the cursor returns unchanged."""
    rect = RectangleItem(0, 0, 200, 100)
    window.canvas_view.scene().addItem(rect)
    window._on_toggle_perpendicular_snap(True)
    # Stay on the default Select tool; no anchor.
    snapped, candidate = window.canvas_view.anchor_snap(QPointF(30, -8))
    # Either no candidate, or a different (non-perpendicular) kind.
    if candidate is not None:
        assert candidate.kind != SnapCandidateKind.PERPENDICULAR
    window._on_toggle_perpendicular_snap(False)


def test_perpendicular_from_polyline_anchor(window: GardenPlannerApp) -> None:
    """Start a polyline-style draw, click once to set last_point, then
    hover near a rectangle edge — perpendicular foot is the snap."""
    # Disable grid snap so the polyline tool doesn't round our anchor
    # to the nearest 50 cm during mouse_press.
    window.canvas_view.set_snap_enabled(False)

    # Place the rect well inside the canvas so the anchor's negative-y
    # offset doesn't fall outside the canvas-clamp envelope.
    rect = RectangleItem(1000, 1000, 200, 100)
    window.canvas_view.scene().addItem(rect)

    # Isolate perpendicular as the only firing provider for this case.
    window._on_toggle_midpoint_snap(False)
    window._on_toggle_intersection_snap(False)
    window._on_toggle_perpendicular_snap(True)

    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool

    # Anchor at (1030, 920) — above the rect's top edge (y=1000), clear
    # of any vertex (corner is at x=1000).
    from unittest.mock import MagicMock
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QMouseEvent
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    tool.mouse_press(event, QPointF(1030, 920))
    assert tool.last_point is not None
    assert abs(tool.last_point.x() - 1030) < 1e-6
    assert abs(tool.last_point.y() - 920) < 1e-6

    # Perpendicular foot from (1030, 920) onto the top edge (y=1000,
    # x in [1000, 1200]) is (1030, 1000). Cursor at (1032, 1002) sits
    # within threshold of that foot.
    snapped, candidate = window.canvas_view.anchor_snap(QPointF(1032, 1002))
    assert candidate is not None
    assert candidate.kind == SnapCandidateKind.PERPENDICULAR
    assert abs(snapped.x() - 1030) < 1e-6
    assert abs(snapped.y() - 1000) < 1e-6

    # Reset state for other tests.
    tool.cancel()
    window.canvas_view.set_snap_enabled(True)
    window._on_toggle_midpoint_snap(True)
    window._on_toggle_intersection_snap(True)
    window._on_toggle_perpendicular_snap(False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
