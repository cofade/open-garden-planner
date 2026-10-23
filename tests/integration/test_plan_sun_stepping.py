"""Chronological stepping through the real Plan & Sun controls (PR #565)."""

from datetime import datetime, timedelta
from itertools import pairwise

import pytest
from PyQt6.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QDateTimeEdit,
    QStyle,
    QStyleOptionSpinBox,
)

from open_garden_planner.core.plan_timeline import month_number
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE
from tests.integration.test_view3d_workspace import build_app3d


@pytest.fixture
def planner(qtbot, monkeypatch, tmp_path):
    window, _engines = build_app3d(qtbot, monkeypatch, tmp_path)
    return window


@pytest.mark.parametrize("field,section,start,key,expected", [
    ("date", QDateTimeEdit.Section.DaySection, "2026-10-31T12:15", Qt.Key.Key_Up, "2026-11-01T12:15"),
    ("date", QDateTimeEdit.Section.DaySection, "2026-11-01T12:15", Qt.Key.Key_Down, "2026-10-31T12:15"),
    ("date", QDateTimeEdit.Section.MonthSection, "2026-12-15T12:15", Qt.Key.Key_Up, "2027-01-15T12:15"),
    ("date", QDateTimeEdit.Section.MonthSection, "2027-01-15T12:15", Qt.Key.Key_Down, "2026-12-15T12:15"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-10-31T10:59", Qt.Key.Key_Up, "2026-10-31T11:00"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-10-31T11:00", Qt.Key.Key_Down, "2026-10-31T10:59"),
    ("time", QDateTimeEdit.Section.HourSection, "2026-12-31T23:30", Qt.Key.Key_Up, "2027-01-01T00:30"),
    ("time", QDateTimeEdit.Section.HourSection, "2027-01-01T00:30", Qt.Key.Key_Down, "2026-12-31T23:30"),
    ("date", QDateTimeEdit.Section.DaySection, "2028-02-28T12:15", Qt.Key.Key_Up, "2028-02-29T12:15"),
    ("date", QDateTimeEdit.Section.DaySection, "2028-02-29T12:15", Qt.Key.Key_Up, "2028-03-01T12:15"),
    ("date", QDateTimeEdit.Section.DaySection, "2027-03-01T12:15", Qt.Key.Key_Down, "2027-02-28T12:15"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-03-29T01:59", Qt.Key.Key_Up, "2026-03-29T02:00"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-10-25T02:59", Qt.Key.Key_Up, "2026-10-25T03:00"),
])
def test_arrow_steps_carry_and_borrow_the_complete_wall_reading(
        planner, qtbot, field, section, start, key, expected):
    planner._sim_clock.set_datetime(datetime.fromisoformat(start))
    bar = planner._sun_toolbar
    edit = getattr(bar, f"_{field}_edit")
    edit.setFocus()
    edit.setCurrentSection(section)
    changed = []
    bar.datetime_changed.connect(changed.append)
    QTest.keyClick(edit, key)
    expected = datetime.fromisoformat(expected)
    assert planner._sim_clock.wall == expected
    assert bar.current_wall_datetime() == expected
    assert changed == [expected], "one complete reading, never an intermediate old date"
    assert edit.currentSection() == section


@pytest.mark.parametrize("field,section,start,key,expected", [
    ("date", QDateTimeEdit.Section.DaySection, "2026-10-30T12:15", Qt.Key.Key_Up, "2026-11-04T12:15"),
    ("date", QDateTimeEdit.Section.DaySection, "2027-03-02T12:15", Qt.Key.Key_Down, "2027-02-25T12:15"),
    ("date", QDateTimeEdit.Section.MonthSection, "2026-11-15T12:15", Qt.Key.Key_Up, "2027-04-15T12:15"),
    ("date", QDateTimeEdit.Section.MonthSection, "2027-01-15T12:15", Qt.Key.Key_Down, "2026-08-15T12:15"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-12-31T23:58", Qt.Key.Key_Up, "2027-01-01T00:03"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2027-01-01T00:02", Qt.Key.Key_Down, "2026-12-31T23:57"),
    ("time", QDateTimeEdit.Section.HourSection, "2026-12-31T22:45", Qt.Key.Key_Up, "2027-01-01T03:45"),
    ("time", QDateTimeEdit.Section.HourSection, "2027-01-01T01:45", Qt.Key.Key_Down, "2026-12-31T20:45"),
])
def test_held_key_repeat_keeps_the_selected_section_across_boundaries(
        planner, field, section, start, key, expected):
    planner._sim_clock.set_datetime(datetime.fromisoformat(start))
    bar = planner._sun_toolbar
    edit = getattr(bar, f"_{field}_edit")
    edit.setFocus()
    edit.setCurrentSection(section)
    readings = []
    bar.datetime_changed.connect(readings.append)
    try:
        QTest.keyPress(edit, key)
        for _ in range(4):
            event = QKeyEvent(QEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier, "", True, 1)
            QApplication.sendEvent(edit, event)
            QApplication.processEvents()
            assert edit.currentSection() == section
    finally:
        QTest.keyRelease(edit, key)
    # Qt's first auto-repeat starts its own repeat machinery and can step twice.
    # Assert every delivered step and the crossed boundary, not an OS/style cadence.
    assert datetime.fromisoformat(expected) in readings
    assert len(readings) >= 5
    direction = 1 if key == Qt.Key.Key_Up else -1
    for before, after in pairwise([datetime.fromisoformat(start), *readings]):
        if section == QDateTimeEdit.Section.MonthSection:
            assert month_number(after.date()) - month_number(before.date()) == direction
            assert after.day == before.day == 15 and after.time() == before.time()
        else:
            unit = (timedelta(days=1) if field == "date" else
                    timedelta(hours=1) if section == QDateTimeEdit.Section.HourSection else
                    timedelta(minutes=1))
            assert after - before == direction * unit
    assert planner._sim_clock.wall == readings[-1]
    assert readings[-1] == bar.current_wall_datetime()


@pytest.mark.parametrize("section,start,days", [
    (QDateTimeEdit.Section.MonthSection, "2027-01-31T12:15",
     ["2027-02-28", "2027-03-31", "2027-02-28", "2027-01-31"]),
    (QDateTimeEdit.Section.YearSection, "2028-02-29T12:15",
     ["2029-02-28", "2030-02-28", "2029-02-28", "2028-02-29"]),
])
def test_calendar_steps_preserve_the_preferred_day_after_short_months(planner, section, start, days):
    planner._sim_clock.set_datetime(datetime.fromisoformat(start))
    edit = planner._sun_toolbar._date_edit
    edit.setCurrentSection(section)
    for key, day in zip([Qt.Key.Key_Up, Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Down], days, strict=True):
        QTest.keyClick(edit, key)
        assert planner._sim_clock.wall == datetime.fromisoformat(day + "T12:15")


@pytest.mark.parametrize("field,section", [
    ("date", QDateTimeEdit.Section.DaySection),
    ("date", QDateTimeEdit.Section.MonthSection),
    ("date", QDateTimeEdit.Section.YearSection),
    ("time", QDateTimeEdit.Section.MinuteSection),
    ("time", QDateTimeEdit.Section.HourSection),
])
@pytest.mark.parametrize("at_max", [False, True])
def test_only_absolute_clock_limits_disable_a_step(planner, field, section, at_max):
    day = MAX_PLAN_DATE if at_max else MIN_PLAN_DATE
    wall = datetime(day.year, day.month, day.day, 23 if at_max else 0, 59 if at_max else 0)
    planner._sim_clock.set_datetime(wall)
    bar = planner._sun_toolbar
    edit = getattr(bar, f"_{field}_edit")
    edit.setCurrentSection(section)
    flag = (QAbstractSpinBox.StepEnabledFlag.StepUpEnabled if at_max
            else QAbstractSpinBox.StepEnabledFlag.StepDownEnabled)
    assert not edit.stepEnabled() & flag
    changes = []
    bar.datetime_changed.connect(changes.append)
    QTest.keyClick(edit, Qt.Key.Key_Up if at_max else Qt.Key.Key_Down)
    assert planner._sim_clock.wall == wall
    assert changes == []
    edit.setReadOnly(True)
    assert edit.stepEnabled() == QAbstractSpinBox.StepEnabledFlag.StepNone
    QTest.keyClick(edit, Qt.Key.Key_Down if at_max else Qt.Key.Key_Up)
    assert planner._sim_clock.wall == wall


@pytest.mark.parametrize("field,section,start,expected", [
    ("date", QDateTimeEdit.Section.DaySection, "2026-10-28T12:15", "2026-11-07T12:15"),
    ("date", QDateTimeEdit.Section.MonthSection, "2026-12-15T12:15", "2027-10-15T12:15"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-12-31T23:55", "2027-01-01T00:05"),
    ("time", QDateTimeEdit.Section.HourSection, "2026-12-31T20:45", "2027-01-01T06:45"),
])
def test_page_up_steps_cross_multiple_boundaries_atomically(planner, field, section, start, expected):
    planner._sim_clock.set_datetime(datetime.fromisoformat(start))
    bar = planner._sun_toolbar
    edit = getattr(bar, f"_{field}_edit")
    edit.setCurrentSection(section)
    readings = []
    bar.datetime_changed.connect(readings.append)
    QTest.keyClick(edit, Qt.Key.Key_PageUp)
    expected = datetime.fromisoformat(expected)
    assert planner._sim_clock.wall == expected
    assert readings == [expected]


@pytest.mark.parametrize("field,section,start,expected", [
    ("date", QDateTimeEdit.Section.DaySection, "2026-10-31T12:15", "2026-11-01T12:15"),
    ("time", QDateTimeEdit.Section.MinuteSection, "2026-12-31T23:59", "2027-01-01T00:00"),
])
def test_wheel_uses_the_same_chronological_step(planner, field, section, start, expected):
    planner._sim_clock.set_datetime(datetime.fromisoformat(start))
    edit = getattr(planner._sun_toolbar, f"_{field}_edit")
    edit.setFocus()
    edit.setCurrentSection(section)
    centre = edit.rect().center()
    event = QWheelEvent(QPointF(centre), QPointF(edit.mapToGlobal(centre)), QPoint(), QPoint(0, 120),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(edit, event)
    assert planner._sim_clock.wall == datetime.fromisoformat(expected)


def test_time_spin_button_carries_the_date_and_emits_one_clock_change(planner):
    start = datetime(2026, 12, 31, 23, 59)
    planner._sim_clock.set_datetime(start)
    bar = planner._sun_toolbar
    edit = bar._time_edit
    edit.setCurrentSection(QDateTimeEdit.Section.MinuteSection)
    option = QStyleOptionSpinBox()
    edit.initStyleOption(option)
    button = edit.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option,
                                         QStyle.SubControl.SC_SpinBoxUp, edit)
    assert not button.isEmpty()
    dates, instants, readings = [], [], []
    planner._sim_clock.date_changed.connect(dates.append)
    planner._sim_clock.instant_changed.connect(instants.append)
    bar.datetime_changed.connect(readings.append)
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=button.center())
    expected = datetime(2027, 1, 1)
    assert planner._sim_clock.wall == expected
    assert readings == [expected] and dates == [expected.date()] and len(instants) == 1
