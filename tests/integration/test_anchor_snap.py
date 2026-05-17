"""Integration tests for midpoint + intersection snap (Package A US-A3)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import (
    IntersectionSnapProvider,
    MidpointSnapProvider,
)
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(900, 600)
    return win


def test_midpoint_action_persists_setting(window: GardenPlannerApp) -> None:
    """Toggling the View menu action flips both runtime + AppSettings."""
    from open_garden_planner.app.settings import get_settings

    window._midpoint_snap_action.setChecked(False)
    window._on_toggle_midpoint_snap(False)
    assert get_settings().midpoint_snap_enabled is False
    assert not window.canvas_view._snap_registry.has(MidpointSnapProvider)

    window._midpoint_snap_action.setChecked(True)
    window._on_toggle_midpoint_snap(True)
    assert get_settings().midpoint_snap_enabled is True
    assert window.canvas_view._snap_registry.has(MidpointSnapProvider)


def test_intersection_action_persists_setting(window: GardenPlannerApp) -> None:
    """Same lifecycle for the intersection toggle."""
    from open_garden_planner.app.settings import get_settings

    window._intersection_snap_action.setChecked(False)
    window._on_toggle_intersection_snap(False)
    assert get_settings().intersection_snap_enabled is False
    assert not window.canvas_view._snap_registry.has(IntersectionSnapProvider)

    window._intersection_snap_action.setChecked(True)
    window._on_toggle_intersection_snap(True)
    assert get_settings().intersection_snap_enabled is True
    assert window.canvas_view._snap_registry.has(IntersectionSnapProvider)


def test_midpoint_snap_pulls_vertex_to_edge_centre(
    window: GardenPlannerApp,
) -> None:
    """End-to-end: scene populated → drawing tool → cursor near edge midpoint
    → vertex lands on the midpoint."""
    rect = RectangleItem(0, 0, 200, 100)
    window.canvas_view.scene().addItem(rect)
    window.canvas_view.set_active_tool(ToolType.FENCE)
    tool = window.canvas_view._tool_manager.active_tool

    # Right-edge midpoint of the rect is at (200, 50).  Cursor 3 cm off.
    snapped, candidate = window.canvas_view.anchor_snap(QPointF(198, 51))
    assert candidate is not None
    assert candidate.kind in (
        SnapCandidateKind.MIDPOINT,
        SnapCandidateKind.EDGE,
        SnapCandidateKind.ENDPOINT,
    )
    # If midpoint is enabled and the cursor is near the edge midpoint,
    # the midpoint candidate must win (endpoint is 50 cm away).
    assert candidate.kind == SnapCandidateKind.MIDPOINT
    assert abs(snapped.x() - 200) < 1e-6
    assert abs(snapped.y() - 50) < 1e-6

    tool.commit_typed_coordinate(snapped)
    last = tool.last_point
    assert last is not None
    assert abs(last.x() - 200) < 1e-6
    assert abs(last.y() - 50) < 1e-6


def test_intersection_snap_pulls_to_cross(window: GardenPlannerApp) -> None:
    """Two crossing polylines: cursor near the cross → snaps to (50, 50)."""
    horiz = PolylineItem([QPointF(-100, 50), QPointF(200, 50)])
    vert = PolylineItem([QPointF(50, -100), QPointF(50, 200)])
    window.canvas_view.scene().addItem(horiz)
    window.canvas_view.scene().addItem(vert)
    window.canvas_view.set_active_tool(ToolType.FENCE)

    snapped, candidate = window.canvas_view.anchor_snap(QPointF(52, 48))
    assert candidate is not None
    assert candidate.kind == SnapCandidateKind.INTERSECTION
    assert abs(snapped.x() - 50) < 1e-6
    assert abs(snapped.y() - 50) < 1e-6


def test_midpoint_disabled_falls_back_to_endpoint(
    window: GardenPlannerApp,
) -> None:
    """When midpoint snap is off, only endpoint/center/edge candidates surface."""
    rect = RectangleItem(0, 0, 200, 100)
    window.canvas_view.scene().addItem(rect)
    window.canvas_view.set_active_tool(ToolType.FENCE)

    window._on_toggle_midpoint_snap(False)
    snapped, candidate = window.canvas_view.anchor_snap(QPointF(100, 1))
    # The top-edge midpoint at (100, 0) is no longer offered; the closest
    # candidate is the top-edge cardinal point at (100, 0) from
    # EdgeCardinalSnapProvider.
    assert candidate is None or candidate.kind != SnapCandidateKind.MIDPOINT
