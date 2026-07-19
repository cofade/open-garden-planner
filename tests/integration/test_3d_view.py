"""Integration tests for the 3D view (US-E6, #261).

The Qt-free math is pinned in ``tests/unit/test_scene3d.py``; this file
covers the collector on a REAL scene, the adapter's light instrumentation,
window lifecycle (no #230-style teardown crash), and the startup-cost pin
(Qt3D loads only when the user opens the 3D view).

Window/adapter tests are Windows-only: Qt3D needs a real RHI context that
the CI's offscreen Linux platform cannot provide; the Windows dev machine
(where every exe gate runs anyway) is the reference environment.
"""

from __future__ import annotations

import sys

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import FLAT_THICKNESS_CM
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import _item_footprints
from open_garden_planner.ui.view3d.snapshot import collect_scene3d_records

requires_windows_3d = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Qt3D window needs a real RHI context (Windows dev machine only)",
)


@pytest.fixture
def plan_scene(qtbot) -> CanvasScene:  # noqa: ARG001
    scene = CanvasScene(1000.0, 800.0)
    shed = RectangleItem(100, 100, 300, 200, object_type=ObjectType.TOOL_SHED)
    scene.addItem(shed)
    fence = PolylineItem(
        [QPointF(50, 50), QPointF(950, 50)], object_type=ObjectType.FENCE
    )
    scene.addItem(fence)
    tree = CircleItem(700, 500, 120, object_type=ObjectType.TREE)
    tree.metadata[METADATA_KEY] = 600.0
    scene.addItem(tree)
    lawn = RectangleItem(500, 100, 300, 250, object_type=ObjectType.LAWN)
    scene.addItem(lawn)
    return scene


class TestSnapshot:
    def test_records_cover_every_footprint_item(self, plan_scene) -> None:
        records = collect_scene3d_records(plan_scene)
        by_name = {r.name: r for r in records}
        assert len(records) == 4
        assert by_name["TOOL_SHED"].kind == "extruded"
        assert by_name["TOOL_SHED"].height_cm == 250.0  # type default
        assert by_name["FENCE"].height_cm == 120.0
        assert by_name["TREE"].height_cm == 600.0  # explicit metadata
        assert by_name["LAWN"].kind == "flat"  # no height → ground decal
        assert by_name["LAWN"].height_cm == FLAT_THICKNESS_CM

    def test_footprints_match_shadow_extraction(self, plan_scene) -> None:
        """3D solids and 2D shadows must come from the SAME footprints —
        the collector delegates to the US-E3 extraction, pin it."""
        fence = next(
            i for i in plan_scene.items() if isinstance(i, PolylineItem)
        )
        expected = _item_footprints(fence)
        records = [
            r for r in collect_scene3d_records(plan_scene) if r.name == "FENCE"
        ]
        assert len(records) == len(expected)
        assert [list(r.footprint) for r in records] == expected

    def test_hidden_items_are_skipped(self, plan_scene) -> None:
        for item in plan_scene.items():
            item.setVisible(False)
        assert collect_scene3d_records(plan_scene) == []


class TestStartupCost:
    def test_app_construction_does_not_import_qt3d(self, qtbot) -> None:
        """ADR-038: Qt3D loads only behind the 3D-view menu action —
        constructing the app must add no PyQt6.Qt3D* modules."""
        from open_garden_planner.app.application import GardenPlannerApp

        before = {m for m in sys.modules if m.startswith("PyQt6.Qt3D")}
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        after = {m for m in sys.modules if m.startswith("PyQt6.Qt3D")}
        assert after == before
        assert win._view3d_window is None


@requires_windows_3d
class TestAdapter:
    def test_set_sun_day_vectors(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        # Berlin Jun-21 noon (the issue's gate): sun from SSW, high.
        adapter.set_sun(59.29, 203.74)
        sun_e, sun_n, sun_up = adapter.last_sun_scene
        assert sun_e == pytest.approx(-0.2056, abs=0.001)
        assert sun_n == pytest.approx(-0.4675, abs=0.001)
        assert sun_up == pytest.approx(0.8598, abs=0.001)
        # Engine light = negated sun, (E,N,up)→(E,up,−N): y must point DOWN.
        engine_x, engine_y, engine_z = adapter.last_light_engine
        assert engine_x == pytest.approx(0.2056, abs=0.001)
        assert engine_y == pytest.approx(-0.8598, abs=0.001)
        assert engine_z == pytest.approx(-0.4675, abs=0.001)

    def test_set_sun_night_fallback(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        adapter.set_sun(-8.0, 30.0)
        assert adapter.last_light_engine[1] < 0  # still lights from above

    def test_rebuild_counts_and_survives_repeat(self, qtbot, plan_scene) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.qt3d_adapter import Garden3DView

        adapter = Garden3DView()
        records = collect_scene3d_records(plan_scene)
        adapter.rebuild(records, 1000.0, 800.0)
        adapter.rebuild(records, 1000.0, 800.0)  # replace path — no crash
        assert adapter.rebuild_count == 2


@requires_windows_3d
class TestWindowLifecycle:
    def test_open_refresh_close_cleanly(self, qtbot, plan_scene) -> None:
        from open_garden_planner.ui.view3d.view3d_window import View3DWindow

        window = View3DWindow()
        qtbot.addWidget(window)
        refreshes: list[bool] = []
        window.refresh_requested.connect(lambda: refreshes.append(True))
        window.rebuild(collect_scene3d_records(plan_scene), 1000.0, 800.0)
        window.set_sun(59.29, 203.74)
        closed: list[bool] = []
        window.closed.connect(lambda: closed.append(True))
        window.close()
        assert closed
