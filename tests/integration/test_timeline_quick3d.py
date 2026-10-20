"""US-F4: the real date editor drives lifetime/growth in the Quick 3D workspace.

The existing workspace engine seam records production builder output. No GPU is
required here; the creator's production renders exercise the same records.
"""

from __future__ import annotations

import time
from datetime import date

import numpy as np
import pytest
from PyQt6.QtCore import QDate

from open_garden_planner.core.commands import SetLayerPropertyCommand
from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.solar import solar_position
from open_garden_planner.ui.canvas.footprints import plant_canopy_radius_cm
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_identified_casters
from open_garden_planner.ui.plant_lifetime import change_lifetime_date
from open_garden_planner.ui.view3d.snapshot import snapshot_records
from open_garden_planner.ui.view3d.sync_controller import DATE_REGROW_MIN_MS
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from tests.integration.test_view3d_workspace import build_app3d, first_pass
from tests.integration.test_view3d_workspace_widget import wait_for_pipeline

BERLIN = {"latitude": 52.52, "longitude": 13.405}


@pytest.fixture
def timeline3d(qtbot, monkeypatch, tmp_path):
    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    window._sim_clock.set_date(date(2025, 6, 1))
    window._project_manager.set_location(BERLIN)
    plants = {}
    for name, kind, x, planted, removed, height, spread, measured in (
        ("Apple", ObjectType.TREE, 450, "2024-04-01", None, 800, 600, 150),
        ("Lettuce", ObjectType.PERENNIAL, 1100, "2026-05-01", None, 35, 30, 30),
        ("Hazel", ObjectType.SHRUB, 1700, "2020-04-01", "2027-03-01", 450, 350, 200),
    ):
        instance = {"planting_date": planted, "current_height_cm": measured}
        if removed:
            instance["removal_date"] = removed
        item = CircleItem(
            x, 800, spread / 2, object_type=kind, name=name,
            layer_id=window.canvas_scene.active_layer.id,
            metadata={"plant_species": {"common_name": name, "scientific_name": name,
                                       "max_height_cm": height, "max_spread_cm": spread},
                      "plant_instance": instance},
        )
        window.canvas_scene.addItem(item)
        plants[name] = item
    window.canvas_scene.refresh_timeline()
    window._workspace.set_mode(WorkspaceMode.SPLIT)
    first_pass(window._workspace, qtbot)
    return window, engines, plants


def _set_day(window, qtbot, day: date) -> None:
    window._sun_toolbar._date_edit.setDate(QDate(day.year, day.month, day.day))
    wait_for_pipeline(window._workspace, qtbot)
    assert window._sim_clock.plan_date == window.canvas_scene.plan_date == day


def _assert_present_geometry(window, engines, plants, expected: set[str]) -> None:
    at = window._sim_clock.plan_date
    records = snapshot_records(window.canvas_scene, at)
    ids = {str(plants[name].item_id) for name in expected}
    assert set(records) == set(engines.sink.item_ids()) == ids
    casters = {caster.item_id: caster for caster in collect_identified_casters(window.canvas_scene, at)}
    assert set(casters) == ids
    for name, item in plants.items():
        assert item.isVisible() == (name in expected)
        if name not in expected:
            continue
        item_id = str(item.item_id)
        record = records[item_id]
        height = effective_height_cm(item.object_type, item.metadata, at)
        radius = plant_canopy_radius_cm(item, at)
        assert record.height_cm == height == casters[item_id].height_cm
        assert record.params["radius_cm"] == pytest.approx(radius, abs=1e-6)
        points = np.concatenate([part.mesh.positions for part in engines.sink.item(item_id).parts])
        low, high = points.min(axis=0), points.max(axis=0)
        assert np.isfinite(points).all()
        assert low[2] == pytest.approx(0, abs=1e-3)
        assert high[2] == pytest.approx(height, rel=1e-5)
        assert max(high[0] - low[0], high[1] - low[1]) == pytest.approx(2 * radius, rel=1e-5)


def test_shared_date_removes_future_and_removed_plants_and_regrows_the_survivor(timeline3d, qtbot):
    window, engines, plants = timeline3d
    _assert_present_geometry(window, engines, plants, {"Apple", "Hazel"})
    young = snapshot_records(window.canvas_scene, window._sim_clock.plan_date)[str(plants["Apple"].item_id)]

    _set_day(window, qtbot, date(2027, 3, 1))
    _assert_present_geometry(window, engines, plants, {"Apple", "Lettuce"})
    _set_day(window, qtbot, date(2030, 6, 1))
    _assert_present_geometry(window, engines, plants, {"Apple", "Lettuce"})
    grown = snapshot_records(window.canvas_scene, window._sim_clock.plan_date)[str(plants["Apple"].item_id)]
    assert grown.height_cm > young.height_cm
    assert grown.params["radius_cm"] > young.params["radius_cm"]
    assert engines.host.frames_taken == [], "date changes never read back a live view"

    _set_day(window, qtbot, date(2025, 6, 1))
    _assert_present_geometry(window, engines, plants, {"Apple", "Hazel"})


def test_date_burst_keeps_quick3d_regrowth_throttled_and_shows_its_last_day(timeline3d, qtbot):
    window, engines, plants = timeline3d
    controller = window._workspace.controller
    _set_day(window, qtbot, date(2028, 1, 1))
    reports = []
    controller.applied.connect(reports.append)
    before = controller.snapshot_count
    apple_id = str(plants["Apple"].item_id)

    # First step at once, then a burst within the same regrowth interval. The
    # date editor is the real UI write path, not a controller callback shortcut.
    window._sun_toolbar._date_edit.setDate(QDate(2028, 2, 1))
    qtbot.waitUntil(lambda: any(apple_id in report.changes.geometry for report in reports))
    first = controller.snapshot_count
    deferred = controller.date_deferrals
    for month in range(3, 13):
        window._sun_toolbar._date_edit.setDate(QDate(2028, month, 1))
    assert controller.date_deferrals > deferred
    assert controller._date_timer.isActive(), "one trailing regrowth is booked"
    assert controller.snapshot_count == first, "the burst never queues intermediate regrowths"
    wait_for_pipeline(window._workspace, qtbot)
    assert controller.snapshot_count == before + 2
    assert controller._pass_date == date(2028, 12, 1)
    _assert_present_geometry(window, engines, plants, {"Apple", "Lettuce"})
    assert engines.sink.sun == SunState.from_solar_position(
        solar_position(BERLIN["latitude"], BERLIN["longitude"], window._sim_clock.utc))
    assert engines.host.frames_taken == []


@pytest.mark.parametrize("boundary", [date(2026, 5, 1), date(2027, 3, 1)])
def test_crossing_a_lifetime_boundary_does_not_bypass_date_regrowth_throttle(
        timeline3d, qtbot, boundary):
    """Separate event-loop turns crossed presence boundaries on every step and
    used to announce ten plan edits, defeating the clock's 500 ms regrow path."""
    from datetime import timedelta

    window, engines, plants = timeline3d
    controller = window._workspace.controller
    _set_day(window, qtbot, boundary)
    scene = window.canvas_scene
    revision, snapshots = scene.plan_revision, controller.snapshot_count
    started = time.monotonic()
    for step in range(10):
        target = boundary - timedelta(days=1) if step % 2 == 0 else boundary
        window._sun_toolbar._date_edit.setDate(QDate(target.year, target.month, target.day))
        # No change of plan content happened, even though setVisible did change.
        assert scene.plan_revision == revision
        qtbot.wait(15)  # real turns between steps: coalescing one turn cannot pass
    elapsed_ms = (time.monotonic() - started) * 1000
    # This is the controller's semantic rate bound, not a speed requirement:
    # a slow runner may legitimately advance through more than one interval.
    assert controller.snapshot_count - snapshots <= 1 + int(elapsed_ms / DATE_REGROW_MIN_MS)
    wait_for_pipeline(window._workspace, qtbot)
    assert controller._pass_date == boundary
    expected = {"Apple", "Hazel", "Lettuce"} if boundary.year == 2026 else {"Apple", "Lettuce"}
    _assert_present_geometry(window, engines, plants, expected)
    assert engines.host.frames_taken == []


def test_manual_visibility_layer_and_lifetime_history_edits_still_announce_plan_changes(timeline3d, qtbot):
    window, engines, plants = timeline3d
    _set_day(window, qtbot, date(2027, 3, 1))
    scene, apple = window.canvas_scene, plants["Apple"]
    revision = scene.plan_revision
    apple.setVisible(False)
    assert scene.plan_revision > revision
    revision = scene.plan_revision
    apple.setVisible(True)
    assert scene.plan_revision > revision

    layer = scene.active_layer
    commands = window.canvas_view.command_manager
    revision = scene.plan_revision
    commands.execute(SetLayerPropertyCommand(scene, layer, "visible", True, False))
    assert scene.plan_revision > revision
    assert not apple.isVisible()
    revision = scene.plan_revision
    commands.undo()
    assert scene.plan_revision > revision
    assert apple.isVisible()

    # This write also calls refresh_timeline, but is a real undoable plan edit:
    # the command path must still announce it after presence was applied.
    revision = scene.plan_revision
    assert change_lifetime_date(apple, "removal_date", "2027-02-01")
    assert scene.plan_revision > revision
    wait_for_pipeline(window._workspace, qtbot)
    _assert_present_geometry(window, engines, plants, {"Lettuce"})
    revision = scene.plan_revision
    commands.undo()
    assert scene.plan_revision > revision
    wait_for_pipeline(window._workspace, qtbot)
    _assert_present_geometry(window, engines, plants, {"Apple", "Lettuce"})
    revision = scene.plan_revision
    commands.redo()
    assert scene.plan_revision > revision
    wait_for_pipeline(window._workspace, qtbot)
    _assert_present_geometry(window, engines, plants, {"Lettuce"})
