"""The preference has one process-wide value and one Qt notification seam."""
import ast
from pathlib import Path

from open_garden_planner.config.settings import AppSettings
from open_garden_planner.core.unit_preference import UnitPreference, get_unit_preference
from open_garden_planner.core.units import UnitSystem as U
from open_garden_planner.ui.units_notifier import units_notifier


def test_default_is_metric():
    assert UnitPreference().system == U.METRIC


def test_set_system_emits_once():
    preference = UnitPreference()
    calls = []
    preference.changed.connect(calls.append)
    preference.set_system(U.IMPERIAL)
    preference.set_system(U.IMPERIAL)
    assert calls == [U.IMPERIAL]


def test_module_is_qt_free():
    tree = ast.parse(Path('src/open_garden_planner/core/unit_preference.py').read_text())
    allowed = {'__future__', 'open_garden_planner.core.units', 'open_garden_planner.core.sim_clock'}
    assert all(n.module in allowed for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))


def test_setting_default_and_round_trip(qtbot):
    settings = AppSettings()
    assert settings.unit_system == 'metric'
    for value, expected in [('imperial', 'imperial'), (' Imperial ', 'imperial'), ('furlongs', 'metric')]:
        settings.unit_system = value
        assert settings.unit_system == expected


def test_notifier_forwards(qtbot):
    with qtbot.waitSignal(units_notifier().changed) as blocker:
        get_unit_preference().set_system(U.IMPERIAL)
    assert blocker.args == [U.IMPERIAL]
