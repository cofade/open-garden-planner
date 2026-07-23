"""US-E8 wiring tests — the signal paths, not the collectors.

The growth tests elsewhere call ``collect_shadow_casters`` /
``collect_scene3d_records`` directly, so they pass even when nothing is
wired to invoke them. These drive the REAL widgets instead:

* editing Current height in the Plant Details panel must make the sun/shade
  shadow recompute (a metadata-only write reaches neither ``scene.changed``
  nor ``stack_changed`` — the owner's "the field does nothing" bug);
* scrubbing the sim date must rebuild the 3D geometry, not just the light;
* loading a plan must NOT stamp a planting date into a dateless plant.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import (
    SunShadowController,
    collect_shadow_casters,
)
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel

BERLIN = {"latitude": 52.52, "longitude": 13.405}
SPECIES = {
    "scientific_name": "Malus domestica",
    "common_name": "Apple",
    "max_height_cm": 800.0,
    "max_spread_cm": 600.0,
}


def _tree(scene: CanvasScene, measured: bool = True) -> CircleItem:
    tree = CircleItem(400, 400, 100, object_type=ObjectType.TREE)
    tree.metadata["plant_species"] = dict(SPECIES)
    if measured:
        tree.metadata["plant_instance"] = {"current_height_cm": 150.0}
    scene.addItem(tree)
    return tree


def _settle(qtbot, controller) -> int:
    """Run until the overlay stops re-triggering itself; return the count.

    Creating/updating the overlay item is itself a scene change, so
    ``recompute_count`` keeps climbing for a few debounce cycles after
    ``set_enabled(True)``. Taking a baseline before that settles makes any
    "it recomputed!" assertion pass on its own noise — which is exactly how
    the first cut of these tests passed against the UNFIXED code.
    """
    previous = -1
    while previous != controller.recompute_count:
        previous = controller.recompute_count
        qtbot.wait(250)  # > _DEBOUNCE_MS (150)
    return controller.recompute_count


class TestPanelEditReachesTheShadow:
    """P0 regression: the owner types a height and the canvas must react."""

    def _setup(self, qtbot):
        scene = CanvasScene(2000.0, 2000.0)
        tree = _tree(scene)
        controller = SunShadowController(scene, lambda: BERLIN)
        controller.set_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        controller.set_enabled(True)
        baseline = _settle(qtbot, controller)
        panel = PlantDatabasePanel()
        qtbot.addWidget(panel)
        panel.set_selected_items([tree])
        baseline = _settle(qtbot, controller)
        return scene, controller, panel, baseline

    def test_current_height_edit_triggers_recompute(self, qtbot) -> None:
        scene, controller, panel, baseline = self._setup(qtbot)

        panel.current_height_spin.setValue(600.0)

        qtbot.waitUntil(
            lambda: controller.recompute_count > baseline, timeout=2000
        )
        _, height = collect_shadow_casters(scene)[0]
        assert height == pytest.approx(600.0)

    def test_current_spread_edit_triggers_recompute(self, qtbot) -> None:
        scene, controller, panel, baseline = self._setup(qtbot)

        panel.current_spread_spin.setValue(250.0)

        qtbot.waitUntil(
            lambda: controller.recompute_count > baseline, timeout=2000
        )
        footprint, _ = collect_shadow_casters(scene)[0]
        xs = [x for x, _ in footprint]
        assert (max(xs) - min(xs)) == pytest.approx(250.0, abs=2.0)


class TestLoadNeverStampsAPlantingDate:
    """The stamp is a FRESH-CREATION rule; loading must not rewrite a plan."""

    def test_dateless_plant_round_trips_untouched(self, qtbot, tmp_path) -> None:  # noqa: ARG002
        scene = CanvasScene(2000.0, 2000.0)
        tree = _tree(scene)
        assert "planting_date" not in tree.metadata["plant_instance"]

        manager = ProjectManager()
        first = tmp_path / "legacy.ogp"
        manager.save(scene, first)

        scene.clear()
        manager.load(scene, first)
        loaded = next(i for i in scene.items() if isinstance(i, CircleItem))
        instance = loaded.metadata.get("plant_instance", {})
        assert "planting_date" not in instance, (
            "loading must never invent a planting date"
        )

        second = tmp_path / "resaved.ogp"
        manager.save(scene, second)
        assert json.loads(first.read_text(encoding="utf-8"))["objects"] == (
            json.loads(second.read_text(encoding="utf-8"))["objects"]
        )


class TestSimDateRebuilds3D:
    """Scrubbing the DATE must regrow the 3D geometry, not only move the sun.

    Uses a stand-in window so the assertion runs headlessly — Qt3D itself
    needs an RHI context (Windows-only, see test_3d_view).
    """

    def _app(self, qtbot):
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        win._view3d_window = MagicMock()
        return win

    def test_same_day_different_time_does_not_rebuild(self, qtbot) -> None:
        win = self._app(qtbot)
        win._on_sun_sim_datetime(datetime(2026, 6, 21, 10, 0, tzinfo=UTC))
        win._view3d_window.rebuild.reset_mock()

        win._on_sun_sim_datetime(datetime(2026, 6, 21, 16, 0, tzinfo=UTC))

        win._view3d_window.rebuild.assert_not_called()
        assert win._view3d_window.set_sun.called  # light still follows time

    def test_new_day_rebuilds_the_geometry(self, qtbot) -> None:
        win = self._app(qtbot)
        win._on_sun_sim_datetime(datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
        win._view3d_window.rebuild.reset_mock()

        win._on_sun_sim_datetime(datetime(2031, 6, 21, 12, 0, tzinfo=UTC))

        win._view3d_window.rebuild.assert_called_once()
