"""The sun-exposure coordinator (US-F3) on the sim clock and on the theme registry.

In v1.30.1 it connected to ``clock.date_changed`` directly and hung a Python closure on
its own ``destroyed`` signal to take the subscription and its theme listener away.
Measured in bare PyQt 6.11: with the wrappers collected before Qt's deferred delete that
closure runs 0 times (5 of 5) — nothing is taken away. Both registries are not Qt
objects; the rule for them is ADR-053's addendum: ask at the moment of use.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pytest
from PyQt6 import sip
from PyQt6.QtWidgets import QApplication

import open_garden_planner
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.ui import sim_clock_subscription, theme
from open_garden_planner.ui.theme import ThemeMode, apply_theme, is_dark_theme

SOURCE = Path(open_garden_planner.__file__).parent / "ui" / "sun_exposure_coordinator.py"


@pytest.fixture()
def window(qtbot) -> GardenPlannerApp:
    previous = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    yield win
    win._sun_heatmap.shutdown()
    apply_theme(QApplication.instance(), previous)


def test_the_coordinator_is_on_the_clock_through_connect_qobject(window, qtbot) -> None:
    coordinator = window.sun_exposure_coordinator
    guards = sim_clock_subscription._GUARDS.get(coordinator)
    assert guards is not None and len(guards) == 1, "one subscription, booked by the helper"
    assert guards[0].channel is window._sim_clock.date_changed
    qtbot.wait(120)                     # the refresh its construction asked for has run
    assert coordinator.timer.isActive() is False
    window._sim_clock.set_date(date(2031, 3, 3))
    assert coordinator.timer.isActive() is True, "a new plan date schedules a refresh"
    source = SOURCE.read_text(encoding="utf-8")
    assert "date_changed.connect(" not in source and "destroyed.connect(" not in source


def test_a_destroyed_coordinator_is_never_called_and_takes_its_theme_listener_along(
        window, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    """Qt destroys the coordinator with its window while Python still holds the
    wrapper. The next clock write must not call it (``RuntimeError: wrapped C/C++
    object … has been deleted``), and the next theme change takes its listener off
    the module-level list instead of calling into the dead object for ever.

    Every assertion is about THIS coordinator's own subscription and its own listener.
    The theme registry is the process's: the listeners of every coordinator an earlier
    test of the same process (or xdist worker) left dead are on it too, and the first
    theme change takes all of them off at once — a count of the list measured them
    (CI: ``assert 1 == 3 - 1``), not this coordinator."""
    coordinator = window.sun_exposure_coordinator
    clock = window._sim_clock
    listener = coordinator.theme_listener
    (guard,) = sim_clock_subscription._GUARDS[coordinator]
    assert guard.channel is clock.date_changed
    assert listener in theme._theme_listeners
    sip.delete(coordinator)                                  # as Qt does with a dead parent

    with caplog.at_level(logging.ERROR):
        clock.set_date(date(2031, 3, 4))                     # the guard notices at this delivery
        assert sim_clock_subscription._GUARDS.get(coordinator) is None
        with pytest.raises(ValueError, match="not connected"):
            clock.date_changed.disconnect(guard.deliver)     # … and is off the channel
        assert listener in theme._theme_listeners, "the theme was not changed yet"
        mode = ThemeMode.LIGHT if is_dark_theme() else ThemeMode.DARK
        apply_theme(QApplication.instance(), mode)           # … and the listener at this one
        assert listener not in theme._theme_listeners
        apply_theme(QApplication.instance(), mode)
        assert listener not in theme._theme_listeners
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []
    qtbot.wait(100)


def test_a_living_coordinator_still_follows_the_theme(window, qtbot) -> None:
    coordinator = window.sun_exposure_coordinator
    qtbot.wait(120)
    assert coordinator.timer.isActive() is False
    apply_theme(QApplication.instance(), ThemeMode.LIGHT if is_dark_theme() else ThemeMode.DARK)
    assert coordinator.timer.isActive() is True
    assert coordinator.theme_listener in theme._theme_listeners, "a living one stays on"


def test_a_count_of_the_shared_registry_is_not_evidence_about_one_coordinator(qtbot) -> None:
    """The CI failure, reproduced on purpose: two coordinators dead and not yet
    noticed. One theme change takes BOTH listeners off — the list shrinks by two (and
    by more, if an earlier test of this process left one), so "one shorter" fails —
    while the question the test above asks, "is THIS listener still on it?", has one
    answer whatever else waits on the list."""
    previous = ThemeMode.DARK if is_dark_theme() else ThemeMode.LIGHT
    first, second = GardenPlannerApp(), GardenPlannerApp()
    qtbot.addWidget(first)
    qtbot.addWidget(second)
    try:
        dead = [first.sun_exposure_coordinator, second.sun_exposure_coordinator]
        listeners = [coordinator.theme_listener for coordinator in dead]
        before = len(theme._theme_listeners)
        for coordinator in dead:
            sip.delete(coordinator)
        apply_theme(QApplication.instance(),
                    ThemeMode.LIGHT if is_dark_theme() else ThemeMode.DARK)
        assert len(theme._theme_listeners) <= before - 2, "a count measures every dead one"
        assert all(listener not in theme._theme_listeners for listener in listeners)
    finally:
        first._sun_heatmap.shutdown()
        second._sun_heatmap.shutdown()
        apply_theme(QApplication.instance(), previous)
