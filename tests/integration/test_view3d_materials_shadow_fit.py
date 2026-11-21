"""End-to-end integration tests for 3D materials, lighting, and built-world polish (§8.10).

Exercises the real CanvasScene -> snapshot_records -> SceneSync pipeline and the real
Workspace widget (with FakeHost) for:
- #894: live 3D shadow-map fitting at rest and immediate unlock during camera motion.
- #957: raised bed FillPattern (CORTEN, STONE, CONCRETE, SOLID) from 2D item to 3D parts.
- #965: flat-roofed house vs pitched house facade and flat_roof surface from 2D scene.
- #961: organic 10-vertex pond vs 4-vertex formal pool from 2D scene to 3D relief.
"""

from __future__ import annotations

import math
from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QPolygonF

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.item_look import fill_brush
from open_garden_planner.core.object_height import soil_surface_cm
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink, SceneSync
from open_garden_planner.core.scene3d.builders import palette, production_registry, surfaces
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.init_guard import Init3DGuard
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from open_garden_planner.ui.view3d.workspace import (
    SHADOW_FIT_DELAY_MS,
    Workspace,
    WorkspaceMode,
)
from tests.integration.test_view3d_workspace_widget import FakeHost, pipeline_settled

DAY = date(2026, 6, 21)


def _sync_scene(scene: CanvasScene) -> tuple[RecordingSink, SceneSync]:
    records = snapshot_records(scene, DAY)
    sink = RecordingSink()
    sync = SceneSync(sink, production_registry(), validate=True)
    sync.apply(records)
    assert sync.failures == {}
    return sink, sync


class TestLiveShadowFitAtRest:
    def test_shadows_fit_after_camera_rests_and_unlock_on_motion(
        self, qtbot, tmp_path
    ) -> None:
        """#894: Workspace fits shadows after SHADOW_FIT_DELAY_MS of camera rest, unlocks
        immediately on orbit/reset motion, and clears when leaving 3D mode."""
        scene = CanvasScene(width_cm=1200, height_cm=1000)
        scene.addItem(RectangleItem(200, 200, 300, 200, object_type=ObjectType.HOUSE))
        view = CanvasView(scene)
        clock = SimClock()
        hosts: list[FakeHost] = []

        def factory(prefer_software: bool) -> tuple[FakeHost, RecordingSink]:
            host = FakeHost(prefer_software)
            hosts.append(host)
            return host, RecordingSink()

        ws = Workspace(view, engine_factory=factory, guard=Init3DGuard(tmp_path / "guard"))
        qtbot.addWidget(ws)
        ws.connect_plan(scene, clock, lambda: None)
        ws.resize(900, 600)
        ws.show()
        ws.set_mode(WorkspaceMode.VIEW3D)
        qtbot.waitUntil(lambda: pipeline_settled(ws), timeout=5000)

        assert hosts
        host = hosts[0]
        # After document framing settles and rests for SHADOW_FIT_DELAY_MS, shadows fit
        qtbot.waitUntil(
            lambda: bool(host.fitted_shadows) and host.fitted_shadows[-1] is True,
            timeout=SHADOW_FIT_DELAY_MS + 1500,
        )

        # Start orbiting: must immediately unlock to False so shadow edges do not crawl
        ws.camera.orbit(18.0, 4.0)
        ws._start_camera()
        assert host.fitted_shadows[-1] is False

        # Once the glide finishes and the camera rests again, shadows re-fit to True
        qtbot.waitUntil(lambda: not ws.camera.moving, timeout=3000)
        qtbot.waitUntil(
            lambda: host.fitted_shadows[-1] is True,
            timeout=SHADOW_FIT_DELAY_MS + 1500,
        )

        # Switching back to Plan hides the 3D pane and resets fitted state to False
        ws.set_mode(WorkspaceMode.PLAN)
        assert host.fitted_shadows[-1] is False
        assert not ws._shadow_fit_timer.isActive()
        ws.shutdown()


class TestCanvasTo3DPipelinePolish:
    @pytest.mark.parametrize(("pattern", "expected_surface"), [
        (FillPattern.CORTEN, "corten"),
        (FillPattern.STONE, "masonry"),
        (FillPattern.CONCRETE, "concrete"),
        (FillPattern.TERRACOTTA, "terracotta"),
    ])
    def test_raised_bed_fill_pattern_flows_from_canvas_to_3d_frame(
        self, qtbot, pattern: FillPattern, expected_surface: str
    ) -> None:
        """#957: changing a RAISED_BED's 2D FillPattern updates its 3D frame material."""
        scene = CanvasScene(width_cm=1000, height_cm=1000)
        bed = RectangleItem(100, 100, 240, 100, object_type=ObjectType.RAISED_BED)
        bed.fill_pattern = pattern
        bed.fill_color = QColor(156, 78, 44)
        bed.setBrush(fill_brush(bed, bed.fill_color))
        bed.metadata["object_height_cm"] = 50.0
        scene.addItem(bed)

        sink, _sync = _sync_scene(scene)
        item = sink.item(str(bed.item_id))
        names = [part.name for part in item.parts]
        assert names == ["walls", "soil"]
        walls_part, soil_part = item.parts
        assert walls_part.tinted is True
        assert walls_part.surface == expected_surface
        assert float(soil_part.mesh.positions[:, 2].max()) == pytest.approx(
            soil_surface_cm("RAISED_BED", 50.0)
        )

    def test_flat_roofed_house_flows_from_canvas_with_modern_facade_and_matte_roof(
        self, qtbot
    ) -> None:
        """#965: a flat-roofed HOUSE on CanvasScene builds modern glazing and flat_roof."""
        scene = CanvasScene(width_cm=1500, height_cm=1500)
        poly = QPolygonF([QPointF(0, 0), QPointF(800, 0), QPointF(800, 450), QPointF(0, 450)])
        house = PolygonItem(poly, object_type=ObjectType.HOUSE)
        house.setPos(200, 200)
        house.metadata["object_height_cm"] = 340.0
        house.metadata["roof_style"] = "flat"
        house.fill_pattern = FillPattern.CONCRETE
        house.setBrush(fill_brush(house, house.fill_color))
        scene.addItem(house)

        sink, _sync = _sync_scene(scene)
        parts = sink.item(str(house.item_id)).parts
        roof = next(p for p in parts if p.name == "roof")
        facade_part = next(p for p in parts if p.name == "facade")
        assert roof.surface == "flat_roof"
        iron = np.asarray(palette.IRON.linear, dtype=np.float32)
        white = np.asarray(palette.STEEL_LIGHT.linear, dtype=np.float32)
        assert np.isclose(facade_part.mesh.colors, iron, atol=1e-5).all(axis=1).any()
        assert not np.isclose(facade_part.mesh.colors, white, atol=1e-5).all(axis=1).any()

    def test_organic_pond_vs_formal_pool_flow_from_canvas_to_3d(self, qtbot) -> None:
        """#961: 10-vertex organic pond gets natural bank & water; 4-vertex pool keeps coping."""
        scene = CanvasScene(width_cm=1500, height_cm=1500)
        organic_pts = [
            QPointF(220 * math.cos(2 * math.pi * k / 10), 160 * math.sin(2 * math.pi * k / 10))
            for k in range(10)
        ]
        pond = PolygonItem(QPolygonF(organic_pts), object_type=ObjectType.POND_POOL)
        pond.setPos(400, 400)
        scene.addItem(pond)

        formal_pts = [QPointF(0, 0), QPointF(300, 0), QPointF(300, 200), QPointF(0, 200)]
        pool = PolygonItem(QPolygonF(formal_pts), object_type=ObjectType.POND_POOL)
        pool.setPos(900, 400)
        scene.addItem(pool)

        sink, _sync = _sync_scene(scene)
        pond_water, pond_bank = sink.item(str(pond.item_id)).parts
        pool_water, pool_coping = sink.item(str(pool.item_id)).parts

        assert float(pond_bank.mesh.positions[:, 2].max()) == pytest.approx(surfaces.BANK_UP_CM)
        assert float(pool_coping.mesh.positions[:, 2].max()) == pytest.approx(surfaces.COPING_UP_CM)
        assert pond_water.mesh.colors[0, 1] > pond_water.mesh.colors[0, 2]
        assert np.allclose(pool_water.mesh.colors[0, :3], 0.9, atol=1e-5)
