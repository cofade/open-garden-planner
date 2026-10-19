"""The 3D view's three settings (Phase 17 L1.4, #385): quality, reduced motion, and
where the automatic quality last settled.

The DEFAULTS are product decisions and are asserted on the class constants (an
autouse fixture may change the runtime value — the Agent API tests' rule).
"""

from __future__ import annotations

import pytest

from open_garden_planner.app.settings import AppSettings, get_settings
from open_garden_planner.core.scene3d import look as core_look


def test_the_defaults_are_the_decided_ones() -> None:
    assert AppSettings.DEFAULT_VIEW3D_QUALITY == "auto"
    assert AppSettings.DEFAULT_VIEW3D_REDUCED_MOTION is False
    assert AppSettings.DEFAULT_VIEW3D_AUTO_LEVEL == "medium"
    assert (AppSettings.KEY_VIEW3D_QUALITY, AppSettings.KEY_VIEW3D_REDUCED_MOTION,
            AppSettings.KEY_VIEW3D_AUTO_LEVEL) == (
        "view3d/quality", "view3d/reduced_motion", "view3d/auto_quality_level")


def test_the_choices_are_the_3d_cores_own() -> None:
    """``settings.py`` writes the two tuples out so that reading a setting does not
    import the 3D core at app start; they must BE the core's."""
    assert AppSettings.VIEW3D_QUALITY_CHOICES == core_look.QUALITY_CHOICES
    assert AppSettings.VIEW3D_AUTO_LEVELS == core_look.AUTO_LEVELS
    assert AppSettings.DEFAULT_VIEW3D_QUALITY == core_look.AUTO
    assert AppSettings.DEFAULT_VIEW3D_AUTO_LEVEL in core_look.AUTO_LEVELS


def test_the_settings_module_does_not_import_the_3d_core() -> None:
    import ast
    from pathlib import Path

    from open_garden_planner.app import settings as module

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
    assert not [name for name in imported if "scene3d" in name or "view3d" in name], imported


@pytest.fixture()
def settings(qtbot):  # noqa: ARG001 - Qt must be up
    store = get_settings()
    saved = (store.view3d_quality, store.view3d_reduced_motion, store.view3d_auto_level,
             store.view3d_auto_bars)
    yield store
    (store.view3d_quality, store.view3d_reduced_motion, store.view3d_auto_level,
     store.view3d_auto_bars) = saved


@pytest.mark.parametrize("value", ["auto", "low", "medium", "high", "ultra"])
def test_a_quality_round_trips(settings, value: str) -> None:
    settings.view3d_quality = value
    assert settings.view3d_quality == value


@pytest.mark.parametrize(("written", "read"), [
    ("HIGH", "high"), (" low ", "low"), ("fastest", "auto"), ("", "auto"), ("none", "auto")])
def test_a_quality_nobody_can_name_never_reaches_the_renderer(settings, written: str,
                                                             read: str) -> None:
    settings.view3d_quality = written
    assert settings.view3d_quality == read
    settings._settings.setValue(AppSettings.KEY_VIEW3D_QUALITY, written)   # a hand-edited store
    assert settings.view3d_quality == read


def test_reduced_motion_round_trips_as_a_bool(settings) -> None:
    for value in (True, False, True):
        settings.view3d_reduced_motion = value
        assert settings.view3d_reduced_motion is value


@pytest.mark.parametrize(("written", "read"), [
    ("low", "low"), ("medium", "medium"), ("high", "high"), ("ultra", "medium"),
    ("auto", "medium"), ("", "medium"), ("HIGH", "high")])
def test_the_automatic_level_is_one_of_the_levels_auto_moves_between(settings, written: str,
                                                                    read: str) -> None:
    settings.view3d_auto_level = written
    assert settings.view3d_auto_level == read
    settings._settings.setValue(AppSettings.KEY_VIEW3D_AUTO_LEVEL, written)
    assert settings.view3d_auto_level == read


def test_the_automatic_bars_round_trip(settings) -> None:
    """Review P1: which levels the automatic quality had to leave, until when, and how
    long the next bar lasts — kept beside the level so a new session does not retry."""
    assert AppSettings.KEY_VIEW3D_AUTO_BARS == "view3d/auto_quality_bars"
    settings.view3d_auto_bars = {}
    assert settings.view3d_auto_bars == {}
    bars = {"high": (1_900_000_000.5, 600.0), "medium": (1_800_000_000.0, 300.0)}
    settings.view3d_auto_bars = bars
    assert settings.view3d_auto_bars == bars


@pytest.mark.parametrize("stored", [
    "not json", "[1, 2]", '{"ultra": [1, 2]}', '{"high": [1]}', '{"high": ["x", 2]}',
    '{"high": [true, 2]}', '{"high": [1e999, 2]}',
    '{"high": [' + "9" * 400 + ', 300]}', '{"high": [300, ' + "9" * 400 + ']}'])
def test_a_hand_edited_bar_store_only_loses_bars(settings, stored: str) -> None:
    settings._settings.setValue(AppSettings.KEY_VIEW3D_AUTO_BARS, stored)
    assert settings.view3d_auto_bars == {}
    settings._settings.setValue(AppSettings.KEY_VIEW3D_AUTO_BARS,
                                '{"low": [5.0, 300], "ultra": [1, 2]}')
    assert settings.view3d_auto_bars == {"low": (5.0, 300.0)}


def test_qt_still_exposes_no_motion_preference(qtbot) -> None:  # noqa: ARG001
    """The reduced-motion setting is the app's own because Qt 6.11 has no motion
    preference to honour: ``QAccessibilityHints`` carries ``contrastPreference`` only
    and ``QStyleHints`` nothing about motion (measured 2026-10-12, Windows 11, read
    from the meta-objects). When a Qt upgrade adds one, this test fails — honour it
    in ``LookController.from_settings`` then (FR-3D-LOOK-04)."""
    from PyQt6.QtGui import QGuiApplication

    hints = QGuiApplication.styleHints()
    assert hints is not None
    names: list[str] = []
    for owner in (hints, hints.accessibility()):
        meta = owner.metaObject()
        names += [meta.property(index).name() for index in range(meta.propertyCount())]
    assert "contrastPreference" in names, "the hints object this test reads is the right one"
    assert not [name for name in names if "motion" in name.lower() or "animat" in name.lower()], names
