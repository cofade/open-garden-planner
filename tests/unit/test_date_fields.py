"""An English UI does not switch the user to US dates and times (#792, review round 1).

The locale follows the UI language (ADR-077), and an English UI on a system that
speaks another language is ``en_US``. Left to that locale a time field read
"3:30 PM", a date field "6/7/26" and a calendar popup started its week on Sunday,
for a user who had only asked for English words. The app's own fields therefore
take nothing from the territory: one helper (``ui/date_fields``) gives every date
field ISO, every time field 24 hours and every calendar popup a Monday, and one
formatter (``core/i18n.format_short_date``) writes a date in UI text with the
month's NAME, never as a numeric day/month pair.
"""

from __future__ import annotations

import ast
import datetime
import re
from pathlib import Path

import pytest
from PyQt6.QtCore import QDate, QDateTime, QLocale, Qt, QTime
from PyQt6.QtWidgets import QApplication, QDateEdit, QDateTimeEdit, QTimeEdit

from open_garden_planner.core import i18n

SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
HELPER = SRC / "ui" / "date_fields.py"

#: (UI language, the system's locale)
SYSTEMS = [
    pytest.param("en", "de_DE", id="english-ui-on-a-german-system"),
    pytest.param("en", "en_US", id="english-ui-on-an-american-system"),
    pytest.param("en", "en_GB", id="english-ui-on-a-british-system"),
    pytest.param("de", "en_US", id="german-ui-on-an-american-system"),
    pytest.param("es", "es_MX", id="spanish-ui-on-a-mexican-system"),
    pytest.param("ru", "en_US", id="russian-ui-on-an-american-system"),
]


@pytest.fixture
def speak(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    def _speak(language: str, system: str) -> None:
        monkeypatch.setattr(i18n, "_system_locale", lambda: QLocale(system))
        i18n.load_translator(qapp, language)

    yield _speak
    monkeypatch.undo()
    i18n.load_translator(qapp, "en")


# ── the helper ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("language", "system"), SYSTEMS)
def test_a_field_takes_nothing_from_the_territory(qtbot, speak, language, system) -> None:
    from open_garden_planner.ui.date_fields import as_date_field, as_time_field

    speak(language, system)
    time_edit = as_time_field(QTimeEdit(QTime(15, 30)))
    date_edit = as_date_field(QDateEdit(QDate(2026, 6, 7)))
    both = as_date_field(QDateTimeEdit(QDateTime(QDate(2026, 6, 7), QTime(15, 30))))
    for widget in (time_edit, date_edit, both):
        qtbot.addWidget(widget)

    assert time_edit.text() == "15:30"
    assert date_edit.text() == "2026-06-07"
    assert both.text() == "2026-06-07 15:30"
    for edit in (date_edit, both):
        assert edit.calendarPopup()
        assert edit.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday


def test_a_day_without_its_year_names_the_month(qtbot, speak) -> None:
    from open_garden_planner.ui.date_fields import as_date_field

    speak("en", "de_DE")
    edit = as_date_field(QDateEdit(QDate(2026, 6, 7)), without_year=True)
    qtbot.addWidget(edit)
    assert edit.text() == "07 Jun"
    assert edit.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday


def test_a_calendar_of_the_fields_own_keeps_monday(qtbot, speak) -> None:
    from PyQt6.QtWidgets import QCalendarWidget

    from open_garden_planner.ui.date_fields import as_date_field

    speak("en", "de_DE")
    calendar = QCalendarWidget()
    assert calendar.firstDayOfWeek() == Qt.DayOfWeek.Sunday, "what en_US gives on its own"
    edit = as_date_field(QDateEdit(QDate(2026, 6, 7)), calendar=calendar)
    qtbot.addWidget(edit)
    assert edit.calendarWidget() is calendar
    assert calendar.firstDayOfWeek() == Qt.DayOfWeek.Monday


# ── the app's own fields ────────────────────────────────────────────────────


def test_the_plan_strip_and_plant_details_fields_in_an_english_ui(qtbot, speak) -> None:
    from open_garden_planner.ui.panels.plant_database_panel import ClickableDateEdit
    from open_garden_planner.ui.widgets.sun_sim_toolbar import SunSimToolbar

    speak("en", "de_DE")
    toolbar = SunSimToolbar()
    qtbot.addWidget(toolbar)
    toolbar.set_datetime_local(datetime.datetime(2026, 6, 7, 15, 30))
    assert toolbar._date_edit.text() == "2026-06-07"
    assert toolbar._time_edit.text() == "15:30"
    assert toolbar._date_edit.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday

    planted = ClickableDateEdit()
    qtbot.addWidget(planted)
    planted.setDate(QDate(2026, 6, 7))
    assert planted.text() == "2026-06-07"
    assert planted.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday


def test_the_camera_tours_fields_in_an_english_ui(qtbot, speak) -> None:
    from PyQt6.QtCore import QObject, pyqtSignal

    from open_garden_planner.ui.view3d.tour_dialog import TourDialog

    class Capture(QObject):
        tours_changed = pyqtSignal()
        recording = False
        tours_connected = False   # a property, not a call (#737)

        def saved_tours(self) -> list:
            return []

        def orbit_pose(self):
            from open_garden_planner.core.scene3d.camera import CameraPose

            return CameraPose((0.0, 0.0), 1500.0, 0.0, 20.0)

        def plan_date(self) -> datetime.date:
            return datetime.date(2026, 6, 7)

        def __getattr__(self, name: str):
            return lambda *_a, **_k: None

    speak("en", "de_DE")
    dialog = TourDialog(Capture())
    qtbot.addWidget(dialog)
    dialog.time_from.setTime(QTime(15, 30))
    dialog.date_from.setDate(QDate(2026, 6, 7))
    assert dialog.time_from.text() == "15:30" and "M" not in dialog.time_to.text()
    assert dialog.date_from.text() == "2026-06-07"
    for edit in (dialog.date_from, dialog.date_to):
        assert edit.calendarWidget().firstDayOfWeek() == Qt.DayOfWeek.Monday


# ── no field forgets it ─────────────────────────────────────────────────────

_QT_FIELDS = {"QDateEdit": "as_date_field", "QDateTimeEdit": "as_date_field",
              "QTimeEdit": "as_time_field"}
#: What only the helper may call: a format or a week start set anywhere else is a
#: second place that decides.
_HELPER_ONLY = {"setDisplayFormat", "setCalendarPopup", "setCalendarWidget", "setFirstDayOfWeek"}


def _sources() -> list[tuple[Path, ast.Module]]:
    return [(path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
            for path in sorted(SRC.rglob("*.py")) if path != HELPER]


def _base_names(node: ast.ClassDef) -> list[str]:
    return [base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            for base in node.bases]


def _field_classes(trees: list[tuple[Path, ast.Module]]) -> dict[str, tuple[str, ast.ClassDef | None]]:
    """Every date/time field class of the app: name -> (its helper, its class or None for Qt's)."""
    known: dict[str, tuple[str, ast.ClassDef | None]] = {
        name: (helper, None) for name, helper in _QT_FIELDS.items()}
    grew = True
    while grew:
        grew = False
        for _path, tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name not in known:
                    for base in _base_names(node):
                        if base in known:
                            known[node.name] = (known[base][0], node)
                            grew = True
    return known


def _configures_itself(node: ast.ClassDef, helper: str) -> bool:
    """Whether the class's own ``__init__`` hands ``self`` to the helper."""
    for item in ast.walk(node):
        if (isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
                and item.func.id == helper and item.args
                and isinstance(item.args[0], ast.Name) and item.args[0].id == "self"):
            return True
    return False


def test_every_date_and_time_field_is_built_through_the_helper() -> None:
    trees = _sources()
    fields = _field_classes(trees)
    self_made = {name for name, (helper, node) in fields.items()
                 if node is not None and _configures_itself(node, helper)}
    problems: list[str] = []
    built = 0
    for path, tree in trees:
        wrapped: set[int] = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id in set(_QT_FIELDS.values()) and node.args):
                wrapped.add(id(node.args[0]))
        where = path.relative_to(SRC).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else None
            if name in fields:
                built += 1
                if name not in self_made and id(node) not in wrapped:
                    problems.append(f"{where}:{node.lineno}: {name}(...) is not handed to "
                                    f"{fields[name][0]}()")
            if isinstance(node.func, ast.Attribute) and node.func.attr in _HELPER_ONLY:
                problems.append(f"{where}:{node.lineno}: .{node.func.attr}() belongs to "
                                "ui/date_fields.py alone")
    assert built >= 15, f"the walk found only {built} fields: it no longer sees the source"
    assert not problems, "\n".join(problems)


# ── a date in UI text ───────────────────────────────────────────────────────


def test_a_short_date_is_day_month_name_year_in_an_english_ui(qtbot, speak) -> None:
    speak("en", "de_DE")
    assert i18n.format_short_date(datetime.date(2026, 6, 7)) == "7 Jun 2026"
    assert i18n.format_short_date(datetime.date(2026, 12, 24)) == "24 Dec 2026"


@pytest.mark.parametrize(("language", "system"), SYSTEMS)
def test_a_short_date_is_never_a_numeric_day_month_pair(qtbot, speak, language, system) -> None:
    speak(language, system)
    text = i18n.format_short_date(datetime.date(2026, 6, 7))
    # the day first, then a month NAME, then the whole year
    assert re.fullmatch(r"7\.? [^\W\d]+\.? 2026( г\.)?", text), text
    month = i18n.current_locale().monthName(6, QLocale.FormatType.ShortFormat)
    assert month in text


@pytest.mark.parametrize(("language", "system"), SYSTEMS)
def test_the_sun_maps_key_writes_its_day_with_the_one_formatter(
        qtbot, speak, language, system) -> None:
    """The key's title is a legend text: the day in UI text, never ISO (which
    is for a date FIELD, a file and the Agent API). Until the second review of
    the 2D branch it wrote ``day.isoformat()``."""
    from open_garden_planner.ui.canvas.sun_legend import legend_title

    speak(language, system)
    day = datetime.date(2026, 6, 7)
    title = legend_title(day)
    assert title.endswith(i18n.format_short_date(day)), title
    assert "2026-06-07" not in title
    assert legend_title(None) and "2026" not in legend_title(None)


def test_the_3d_card_and_the_legend_write_dates_and_numbers_with_the_one_formatter(
        qtbot, speak) -> None:
    from open_garden_planner.ui.view3d import info_card, workspace_legend

    speak("en", "de_DE")
    day = datetime.date(2026, 6, 7)
    assert info_card._short_date(day) == "7 Jun 2026"
    assert workspace_legend._locale_date(day) == "7 Jun 2026"
    assert workspace_legend._locale_date(None) == ""
    assert info_card._day_month(day) == i18n.format_day_month(day)
    speak("de", "en_US")
    assert workspace_legend._locale_number(1234.56) == "1234,6", "no group separator"


def test_no_ui_text_is_formatted_with_a_bare_locale() -> None:
    """``QLocale().toString(...)`` beside the formatters is a second formatter: it
    writes group separators and the territory's numeric date."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if path == SRC / "core" / "i18n.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"QLocale\(\)\s*\.toString\(|FormatType\.ShortFormat\)\s*$", line) \
                    and "dayName" not in line and "monthName" not in line:
                found.append(f"{path.relative_to(SRC).as_posix()}:{number}: {line.strip()}")
    assert not found, "\n".join(found)
