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
    scene = CanvasScene(width_cm=500, height_cm=500)
    project, heatmap, toolbar = _Project(), _Heatmap(), _Toolbar()
    live = LiveSunMap(scene, SimClock(), project, heatmap, toolbar, CommandManager())
    live.set_enabled(True)
    live._inputs_dirty = False  # what the debounce ends with; no event loop ran
    project.north_angle_deg = 45.0
    project.north_angle_changed.emit(45.0)
    # The signal asks the map for a new day; without the subscription the old
    # result would stay current after the plan had turned.
    assert live._inputs_dirty is True
    assert live._timer.isActive()
