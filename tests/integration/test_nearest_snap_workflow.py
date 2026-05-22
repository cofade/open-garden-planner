"""Integration tests for nearest-point snap (Phase 13 Package B — US-B4)."""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.snap.provider import SnapCandidateKind
from open_garden_planner.core.snap.providers import NearestSnapProvider
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.fixture
def window(qtbot) -> GardenPlannerApp:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    win.resize(900, 600)
    win.show()
    qtbot.waitExposed(win)
    return win


def test_default_is_disabled(window: GardenPlannerApp) -> None:
    """Nearest snap is off by default — the View menu action is unchecked
    and the provider is NOT in the active registry."""
    assert window._nearest_snap_action.isChecked() is False
    assert not window.canvas_view._snap_registry.has(NearestSnapProvider)


def test_action_persists_setting(window: GardenPlannerApp) -> None:
    """Toggling the View menu action updates AppSettings and the registry."""
    from open_garden_planner.app.settings import get_settings

    window._nearest_snap_action.setChecked(True)
    window._on_toggle_nearest_snap(True)
    assert get_settings().nearest_snap_enabled is True
    assert window.canvas_view._snap_registry.has(NearestSnapProvider)

    window._nearest_snap_action.setChecked(False)
    window._on_toggle_nearest_snap(False)
    assert get_settings().nearest_snap_enabled is False
    assert not window.canvas_view._snap_registry.has(NearestSnapProvider)
    # Clean up so we don't leak this preference into other tests.
    get_settings().nearest_snap_enabled = False


def test_nearest_snap_yields_point_on_edge_when_enabled(
    window: GardenPlannerApp,
) -> None:
    """With nearest snap on and the cursor floating above a rectangle's
    top edge (away from any midpoint / corner), the cursor snaps onto
    the edge — proving the fallback fires when no other snap kind hits."""
    rect = RectangleItem(0, 0, 200, 100)
    window.canvas_view.scene().addItem(rect)
    # Disable midpoint + intersection so they can't pre-empt the test.
    window._on_toggle_midpoint_snap(False)
    window._on_toggle_intersection_snap(False)
    window._on_toggle_nearest_snap(True)

    # Cursor at (30, -8) — well off any corner/midpoint of the top edge.
    snapped, candidate = window.canvas_view.anchor_snap(QPointF(30, -8))
    assert candidate is not None
    assert candidate.kind == SnapCandidateKind.NEAREST
    # Projection onto the top edge → (30, 0).
    assert abs(snapped.x() - 30) < 1e-6
    assert abs(snapped.y() - 0) < 1e-6

    # Restore defaults so subsequent tests start from a known state.
    window._on_toggle_midpoint_snap(True)
    window._on_toggle_intersection_snap(True)
    window._on_toggle_nearest_snap(False)


def test_endpoint_still_wins_over_nearest(window: GardenPlannerApp) -> None:
    """Even with nearest on, a cursor near a vertex must snap to the
    endpoint — endpoint priority (10) beats nearest (45)."""
    rect = RectangleItem(0, 0, 200, 100)
    window.canvas_view.scene().addItem(rect)
    window._on_toggle_nearest_snap(True)

    snapped, candidate = window.canvas_view.anchor_snap(QPointF(2, 2))
    assert candidate is not None
    assert candidate.kind == SnapCandidateKind.ENDPOINT
    assert abs(snapped.x() - 0) < 1e-6
    assert abs(snapped.y() - 0) < 1e-6

    window._on_toggle_nearest_snap(False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
