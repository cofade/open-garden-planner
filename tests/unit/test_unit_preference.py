"""The preference has one process-wide value and one Qt notification seam."""

import ast
from pathlib import Path

from open_garden_planner.config.settings import AppSettings
from open_garden_planner.core.unit_preference import (
    Quantity,
    UnitPreference,
    UnitPreset,
    UnitProfile,
    get_unit_preference,
)
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
    tree = ast.parse(Path("src/open_garden_planner/core/unit_preference.py").read_text())
    allowed = {
        "__future__",
        "dataclasses",
        "enum",
        "open_garden_planner.core.units",
        "open_garden_planner.core.sim_clock",
    }
    assert all(n.module in allowed for n in ast.walk(tree) if isinstance(n, ast.ImportFrom))


def test_setting_default_and_round_trip(qtbot):
    settings = AppSettings()
    assert settings.unit_system == "metric"
    for value, expected in [
        ("imperial", "imperial"),
        (" Imperial ", "imperial"),
        ("furlongs", "metric"),
    ]:
        settings.unit_system = value
        assert settings.unit_system == expected


def test_notifier_forwards(qtbot):
    with qtbot.waitSignal(units_notifier().changed) as blocker:
        get_unit_preference().set_system(U.IMPERIAL)
    assert blocker.args == [U.IMPERIAL]


def test_per_quantity_systems_leave_length_alone():
    preference = UnitPreference()
    profiles: list[UnitProfile] = []
    preference.profile_changed.connect(profiles.append)
    preference.set_quantity_system(Quantity.TEMPERATURE, U.IMPERIAL)
    assert preference.system == U.METRIC
    assert preference.profile.system_for(Quantity.TEMPERATURE) == U.IMPERIAL
    assert profiles[-1].temperature == U.IMPERIAL
    assert profiles[-1].length == U.METRIC


def test_canada_mixed_is_provisional_and_round_trips():
    profile = UnitProfile.for_preset(UnitPreset.CANADA_MIXED)
    assert profile.preset == UnitPreset.CANADA_MIXED
    assert profile.length == U.IMPERIAL
    assert profile.area == U.IMPERIAL
    assert profile.volume == U.METRIC
    assert profile.temperature == U.METRIC
    assert profile.precipitation == U.METRIC
    assert profile.mass == U.METRIC


def test_settings_store_a_custom_profile(qtbot):
    settings = AppSettings()
    custom = UnitProfile(
        length=U.IMPERIAL,
        area=U.IMPERIAL,
        volume=U.METRIC,
        temperature=U.IMPERIAL,
        precipitation=U.IMPERIAL,
        mass=U.METRIC,
    )
    settings.unit_profile = custom
    assert settings.unit_profile == custom
    assert settings.unit_profile.preset == UnitPreset.CUSTOM
    assert settings.unit_system == "imperial"  # the legacy key stays truthful
    settings.unit_profile = UnitProfile.all(U.METRIC)
