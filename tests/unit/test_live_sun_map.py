"""The live Hours of Sun map subscribes to the plan's north (#663)."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, pyqtSignal

from open_garden_planner.core.commands import CommandManager
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.live_sun_map import LiveSunMap


class _Project(QObject):
    location_changed = pyqtSignal()
    north_angle_changed = pyqtSignal(float)
    location = {"latitude": 52.52, "longitude": 13.4}
    north_angle_deg = 0.0


class _Heatmap(QObject):
    exposure_changed = pyqtSignal()
    finished = pyqtSignal(bool)
    snapshot = None
    displayed_snapshot = None
    result_pending = False
    exposure_reason = "absent"
    _result_wanted = False
    cleared = 0

    def clear(self) -> None:
        self.cleared += 1

    def suspend_measurements(self) -> None:
        pass

    def invalidate_exposure(self) -> None:
        pass

    def restore_displayed_measurements(self) -> None:
        pass

    def run_for_day(self, _day: object) -> bool:
        return False


class _Toolbar(QObject):
    heatmap_requested = pyqtSignal()
    heatmap_cleared = pyqtSignal()

    def set_heatmap_active(self, _active: bool) -> None:
        pass

    def set_heatmap_busy(self, _busy: bool) -> None:
        pass

    def set_map_status(self, *_status: Any) -> None:
        pass


def test_a_north_change_schedules_the_live_map(qtbot) -> None:
    from open_garden_planner.ui.canvas.sun_exposure_snapshot import collect_exposure_snapshot

    scene = CanvasScene(width_cm=500, height_cm=500)
    project, heatmap, toolbar = _Project(), _Heatmap(), _Toolbar()
    clock = SimClock()
    # A completed map for the current (north-up) frame is on screen.
    shown = collect_exposure_snapshot(scene, project.location, clock.plan_date, 0.0)
    heatmap.displayed_snapshot = shown
    heatmap.snapshot = shown
    live = LiveSunMap(scene, clock, project, heatmap, toolbar, CommandManager())
    live.set_enabled(True)

    project.north_angle_deg = 45.0
    project.north_angle_changed.emit(45.0)
    # The shown result belongs to the old frame: the subscription must clear
    # it and schedule a new day. Without the connection nothing happens.
    assert heatmap.cleared == 1
    assert live._inputs_dirty is True
