"""The UI language decides the locale, never the operating system on its own (#792).

Root cause pinned here: nothing told Qt the application's locale. A spin box and a
bare ``QLocale()`` formatted in the SYSTEM locale ("155,8", "Mrz") while Python
f-strings always wrote a decimal point ("6361.7 cm²"), so an English UI on a German
machine mixed both, and so did a German UI. ``core/i18n.load_translator`` is now the
one place that decides, and every number in UI text goes through its formatters.

Each test sets the application language to something the (simulated) operating
system does not speak, in both directions.
"""

from __future__ import annotations

import datetime

import pytest
from PyQt6.QtCore import QLocale, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QVBoxLayout, QWidget

from open_garden_planner.core import i18n
from open_garden_planner.core.coordinate_input.parser import parse
from open_garden_planner.core.measurements import format_area, format_length

#: (UI language, the system's locale, the decimal mark the UI must show)
_FOREIGN_SYSTEMS = [
    pytest.param("en", "de_DE", ".", id="english-ui-on-a-german-system"),
    pytest.param("de", "en_US", ",", id="german-ui-on-an-american-system"),
    pytest.param("es", "de_DE", ",", id="spanish-ui-on-a-german-system"),
    pytest.param("ru", "en_US", ",", id="russian-ui-on-an-american-system"),
]


@pytest.fixture
def speak(qapp: QApplication, monkeypatch: pytest.MonkeyPatch):
    """Load a UI language on a simulated system locale; English is put back after."""

    def _speak(language: str, system: str) -> None:
        # raising=False: on the code before the fix there is no seam, and the
        # tests must fail on what the UI shows, not in their own set-up.
        monkeypatch.setattr(i18n, "_system_locale", lambda: QLocale(system), raising=False)
        i18n.load_translator(qapp, language)

    yield _speak
    monkeypatch.undo()
    i18n.load_translator(qapp, "en")


def _spin_text(value: float, decimals: int = 1) -> str:
    spin = QDoubleSpinBox()
    spin.setDecimals(decimals)
    spin.setRange(-1e6, 1e6)
    spin.setValue(value)
    return spin.text()


@pytest.mark.parametrize(("language", "system", "mark"), _FOREIGN_SYSTEMS)
def test_every_number_follows_the_ui_language(qtbot, speak, language, system, mark) -> None:
    """A spin box, the status bar's area and a formatted number agree on one mark."""
    speak(language, system)

    assert QLocale().language() == QLocale(language).language()
    assert _spin_text(155.8) == f"155{mark}8"
    assert format_area(6361.7) == f"6361{mark}7 cm²"
    assert format_area(23500.0) == f"2{mark}35 m²"
    assert format_length(235.0) == f"2{mark}35 m"
    assert i18n.format_decimal(0.0, 2) == f"0{mark}00"
    # No group separator, ever: "1.234" must not be readable as a decimal.
    assert i18n.format_decimal(1234.5, 1) == f"1234{mark}5"


def test_month_names_are_the_ui_languages_not_the_systems(qtbot, speak) -> None:
    """English UI on a German system: "Mar, May, Oct, Dec", never "Mrz, Mai, Okt, Dez"."""
    from open_garden_planner.ui.views.planting_calendar_view import _month_abbr

    speak("en", "de_DE")
    assert [_month_abbr(m) for m in (3, 5, 10, 12)] == ["Mar", "May", "Oct", "Dec"]

    speak("de", "en_US")
    # Qt's own data, the standalone form of a column header ("Mär", not "März"
    # and not Windows' "Mrz").
    assert [_month_abbr(m) for m in (3, 5, 10, 12)] == ["Mär", "Mai", "Okt", "Dez"]


def test_day_and_month_order_belongs_to_the_language(qtbot, speak) -> None:
    speak("en", "de_DE")
    assert i18n.format_day_month(datetime.date(2026, 6, 21)) == "Jun 21"


@pytest.mark.parametrize(
    ("language", "system", "expected"),
    [
        pytest.param("de", "de_AT", "de_AT", id="same-language-keeps-the-region"),
        pytest.param("de", "de_CH", "de_CH", id="swiss-german-keeps-its-decimal-point"),
        pytest.param("en", "en_GB", "en_GB", id="british-english"),
        pytest.param("en", "de_DE", "en_US", id="another-language-contributes-nothing"),
        pytest.param("de", "en_US", "de_DE", id="german-ui-on-an-american-system"),
    ],
)
def test_the_system_contributes_its_region_only_in_the_same_language(
    qtbot, speak, language, system, expected
) -> None:
    speak(language, system)
    assert i18n.current_locale().name() == expected
    assert QLocale().name() == expected


def test_the_locale_is_qts_own_data_not_the_system_object(qtbot, speak) -> None:
    """The system locale object takes its names from Windows ("Mrz", "Mo"); the same
    UI language must read the same on every machine."""
    speak("de", "de_DE")
    locale = i18n.current_locale()
    short = QLocale.FormatType.ShortFormat
    assert locale.standaloneMonthName(3, short) == "Mär"
    assert locale.dayName(1, short) == "Mo."


def test_a_template_with_its_own_precision_follows_the_language(qtbot, speak) -> None:
    """``LocalizedNumber`` lets a translated template keep ``{d:.2f}``."""
    speak("de", "en_US")
    assert "{d:.2f} m".format(d=i18n.LocalizedNumber(2.5)) == "2,50 m"
    assert "{d:.0f}°".format(d=i18n.LocalizedNumber(90.4)) == "90°"
    speak("en", "de_DE")
    assert "{d:.2f} m".format(d=i18n.LocalizedNumber(2.5)) == "2.50 m"


def test_trimmed_integer_and_list_formats(qtbot, speak) -> None:
    speak("de", "en_US")
    assert i18n.format_trimmed(2.50) == "2,5"
    assert i18n.format_trimmed(3.0) == "3"
    assert i18n.format_trimmed(1200.0) == "1200"
    assert i18n.format_integer(1920) == "1.920"
    assert i18n.list_separator() == "; "
    speak("en", "de_DE")
    assert i18n.format_trimmed(2.50) == "2.5"
    assert i18n.format_integer(1920) == "1,920"
    assert i18n.list_separator() == ", "


# ── Round trip: what the UI shows, it accepts back ──────────────────────────


@pytest.mark.parametrize(("language", "system", "mark"), _FOREIGN_SYSTEMS)
def test_a_shown_number_is_accepted_back(qtbot, speak, language, system, mark) -> None:
    """Formatter → parser, spin box → spin box and the typed-coordinate parser."""
    speak(language, system)
    for value, decimals in ((6361.7, 1), (0.05, 2), (-12.345, 3), (1234567.5, 1)):
        shown = i18n.format_decimal(value, decimals)
        assert i18n.parse_decimal(shown) == pytest.approx(value)

    spin = QDoubleSpinBox()
    spin.setRange(-1e6, 1e6)
    spin.setDecimals(2)
    assert spin.valueFromText(spin.textFromValue(155.85)) == pytest.approx(155.85)

    # The typed coordinate field takes what the status bar shows.
    shown = i18n.format_decimal(155.8, 1)
    result = parse(f"{shown} {i18n.format_decimal(20.5, 1)}")
    # (the parser answers in scene coordinates, whose Y axis points down)
    assert (result.point.x(), abs(result.point.y())) == pytest.approx((155.8, 20.5))


@pytest.mark.parametrize("language", ["en", "de", "es", "ru"])
def test_either_decimal_mark_is_accepted_in_free_text(qtbot, speak, language) -> None:
    speak(language, "de_DE")
    assert i18n.parse_decimal("155,8") == pytest.approx(155.8)
    assert i18n.parse_decimal(" 155.8 ") == pytest.approx(155.8)
    with pytest.raises(ValueError):
        i18n.parse_decimal("1.234,5")


@pytest.mark.parametrize(
    ("language", "system", "typed"),
    [
        # The owner's combination: an English UI, and a German keyboard whose
        # numeric keypad types a comma. Qt alone reads "155,8" as 1558.
        pytest.param("en", "de_DE", "155,8", id="comma-typed-into-an-english-ui"),
        pytest.param("de", "en_US", "155.8", id="point-typed-into-a-german-ui"),
        pytest.param("ru", "en_US", "155.8", id="point-typed-into-a-russian-ui"),
        pytest.param("en", "de_DE", "155.8", id="the-ui-languages-own-mark"),
    ],
)
def test_either_decimal_key_types_the_decimal_mark(qtbot, speak, language, system, typed) -> None:
    """Typed with real key events into a focused spin box in a shown window."""
    speak(language, system)
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    spin = QDoubleSpinBox()
    spin.setRange(0.0, 1e6)
    spin.setDecimals(1)
    layout.addWidget(spin)
    host.show()
    host.activateWindow()
    spin.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(spin.hasFocus, timeout=3000)

    spin.selectAll()
    QTest.keyClicks(spin, typed)
    QTest.keyClick(spin, Qt.Key.Key_Return)

    assert spin.value() == pytest.approx(155.8)


def test_loading_a_language_that_fails_still_applies_a_locale(qtbot, speak, monkeypatch) -> None:
    """Whatever was loaded, Qt's default locale is the application's afterwards."""
    monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", i18n._TRANSLATIONS_DIR / "missing")
    speak("de", "en_US")
    # The catalog is missing, so the UI stays English, and so does its locale.
    assert i18n.current_language() == "en"
    assert QLocale().name() == "en_US"
