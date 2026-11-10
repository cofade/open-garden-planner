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
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QSpinBox, QVBoxLayout, QWidget

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
    metres, degrees = "{d:.2f} m", "{d:.0f}°"   # as a catalog hands them over
    speak("de", "en_US")
    assert metres.format(d=i18n.LocalizedNumber(2.5)) == "2,50 m"
    assert degrees.format(d=i18n.LocalizedNumber(90.4)) == "90°"
    speak("en", "de_DE")
    assert metres.format(d=i18n.LocalizedNumber(2.5)) == "2.50 m"


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


@pytest.mark.parametrize(("text", "value"), [
    ("1,234", 1.234),          # ONE mark is the decimal mark, never a group separator
    ("1.234", 1.234),
    ("-,5", -0.5), ("+.5", 0.5), ("5.", 5.0), ("5,", 5.0), ("-12", -12.0), ("007", 7.0),
    ("\t155,8\n", 155.8),
])
def test_free_text_reads_what_the_formatters_write_in_either_mark(text, value) -> None:
    assert i18n.parse_decimal(text) == pytest.approx(value)


@pytest.mark.parametrize("text", [
    "nan", "NaN", "inf", "-inf", "Infinity", "+infinity",   # no number field takes these
    "1e3", "1E-3", "1e400",                                 # nor an exponent
    "1_000", "0x10", "١٢",                                  # nor Python's or another script's forms
    "1,234.5", "1.234,5", "1,234,567", "1.2.3", "1 234,5",  # nor a group separator
    "", "  ", ",", ".", "-", "1,-5", "--1", "1 2", "5 cm",
])
def test_free_text_rejects_every_other_form(text) -> None:
    with pytest.raises(ValueError):
        i18n.parse_decimal(text)


def test_a_price_field_never_stores_a_non_finite_number() -> None:
    """The caller that had no guard of its own: "nan" is not below zero."""
    import math

    for text in ("nan", "inf", "-inf"):
        try:
            value = i18n.parse_decimal(text)
        except ValueError:
            continue
        raise AssertionError(f"{text!r} became {value} ({math.isfinite(value)=})")


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


def _focused_spin(qtbot, *, decimals: int = 1, suffix: str = "") -> QDoubleSpinBox:
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    spin = QDoubleSpinBox()
    spin.setRange(-1e6, 1e6)
    spin.setDecimals(decimals)
    spin.setSuffix(suffix)
    layout.addWidget(spin)
    host.show()
    host.activateWindow()
    spin.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(spin.hasFocus, timeout=3000)
    spin.host = host   # the window lives as long as the test holds the field
    return spin


def _paste(spin: QDoubleSpinBox, text: str, how: str) -> None:
    QApplication.clipboard().setText(text)
    spin.selectAll()
    if how == "keyboard":
        QTest.keyClick(spin, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    else:   # the Paste row of the field's own context menu
        menu = spin.lineEdit().createStandardContextMenu()
        paste = next(action for action in menu.actions() if action.objectName() == "edit-paste")
        assert paste.isEnabled()
        paste.trigger()
        menu.deleteLater()
    QTest.keyClick(spin, Qt.Key.Key_Return)


@pytest.mark.parametrize("how", ["keyboard", "context-menu"])
@pytest.mark.parametrize(
    ("language", "system", "pasted"),
    [
        # Qt alone reads the other convention's mark as a group separator and drops
        # it: "155,8" pasted into an English field was 1558.
        pytest.param("en", "de_DE", "155,8", id="comma-pasted-into-an-english-ui"),
        pytest.param("de", "en_US", "155.8", id="point-pasted-into-a-german-ui"),
        pytest.param("ru", "en_US", "155.8", id="point-pasted-into-a-russian-ui"),
        pytest.param("en", "de_DE", "155.8", id="the-ui-languages-own-mark"),
        pytest.param("de", "en_US", "155,8", id="the-german-uis-own-mark"),
    ],
)
def test_a_pasted_number_reads_either_mark_as_the_decimal_mark(
        qtbot, speak, language, system, pasted, how) -> None:
    speak(language, system)
    spin = _focused_spin(qtbot, suffix=" cm")
    _paste(spin, pasted, how)
    assert spin.value() == pytest.approx(155.8)


@pytest.mark.parametrize(("language", "pasted", "value"), [
    # More than one mark: the last is the decimal mark and the others group. That is
    # Qt's own reading in the field's locale and it is left alone; the other
    # convention's grouping is refused, never guessed (the field keeps its value).
    ("en", "1,234.5", 1234.5), ("en", "1,234,567", 1234567.0),
    ("en", "1.234,5", None), ("en", "1.2.3", None),
    ("de", "1.234,5", 1234.5), ("de", "1.234.567", 1234567.0),
    ("de", "1,234.5", None), ("de", "1,2,3", None),
])
def test_a_pasted_number_with_group_separators_is_qts_to_read(
        qtbot, speak, language, pasted, value) -> None:
    speak(language, "en_US" if language == "de" else "de_DE")
    spin = _focused_spin(qtbot, decimals=2)
    spin.setRange(-1e9, 1e9)
    spin.setValue(7.5)
    _paste(spin, pasted, "keyboard")
    assert spin.value() == pytest.approx(7.5 if value is None else value)


@pytest.mark.parametrize(("entered", "decimals", "typed", "pasted"), [
    # ADR-077's table of the trade-off, measured in an English UI. None: the paste is
    # refused and the field keeps its value.
    ("155,8", 2, 155.8, 155.8),
    ("1,234", 2, 1.23, None),
    ("1,234", 3, 1.234, 1.234),
    ("1,234.5", 2, 1.23, 1234.5),
    ("1,234.5", 3, 1.234, 1234.5),
])
def test_a_single_mark_is_never_a_thousands_separator(
        qtbot, speak, entered, decimals, typed, pasted) -> None:
    speak("en", "de_DE")
    spin = _focused_spin(qtbot, decimals=decimals)
    spin.setValue(7.0)
    spin.selectAll()
    QTest.keyClicks(spin, entered)
    QTest.keyClick(spin, Qt.Key.Key_Return)
    assert spin.value() == pytest.approx(typed)
    spin.setValue(7.0)
    _paste(spin, entered, "keyboard")
    assert spin.value() == pytest.approx(7.0 if pasted is None else pasted)


def test_a_whole_number_field_is_left_alone(qtbot, speak) -> None:
    """``QSpinBox`` has no decimal mark: nothing is installed on it, Qt's own rule stays."""
    speak("en", "de_DE")
    host = QWidget()
    qtbot.addWidget(host)
    layout = QVBoxLayout(host)
    spin = QSpinBox()
    spin.setRange(0, 100000)
    layout.addWidget(spin)
    host.show()
    spin.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(spin.hasFocus, timeout=3000)
    own = spin.lineEdit().validator()
    QApplication.clipboard().setText("1234")
    spin.selectAll()
    QTest.keyClick(spin, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(spin, Qt.Key.Key_Return)
    assert spin.value() == 1234
    assert spin.lineEdit().validator() is own


def test_the_fields_own_behaviour_survives(qtbot, speak) -> None:
    """Prefix and suffix, the special value, stepping and a second focus."""
    speak("de", "en_US")
    spin = _focused_spin(qtbot, decimals=2, suffix=" m.")      # a mark in the suffix
    spin.setPrefix("ca. ")                                     # and one in the prefix
    spin.setSpecialValueText("keine, bitte")
    spin.setMinimum(0.0)
    spin.setValue(0.0)
    assert spin.text() == "keine, bitte"
    spin.setValue(2.5)
    assert spin.text() == "ca. 2,50 m."
    spin.stepUp()
    assert spin.value() == pytest.approx(3.5)
    _paste(spin, "12.25", "keyboard")
    assert spin.value() == pytest.approx(12.25) and spin.text() == "ca. 12,25 m."
    first = spin.lineEdit().validator()
    spin.clearFocus()
    spin.setFocus(Qt.FocusReason.TabFocusReason)
    qtbot.waitUntil(spin.hasFocus, timeout=3000)
    assert spin.lineEdit().validator() is first, "installed once, not stacked"


def test_the_rule_lives_and_dies_with_its_field(qtbot, speak, qapp) -> None:
    """Qt owns the validator through the field's line edit; Python must hold its Python
    half meanwhile (a validator Python let go refuses every text), and let go of it once
    the field is destroyed: at the next field that takes the focus, not on a ``destroyed``
    signal (PF-E3D-07)."""
    import gc

    from PyQt6 import sip

    from open_garden_planner.ui import number_fields

    speak("en", "de_DE")
    spin = _focused_spin(qtbot)
    validator = spin.lineEdit().validator()
    assert type(validator).__name__ == "_EitherDecimalMark"
    assert any(kept is validator for kept in number_fields._alive)
    held = len(number_fields._alive)
    del validator
    gc.collect()                        # nothing but the registry holds it now
    spin.selectAll()
    QTest.keyClicks(spin, "155,8")
    QTest.keyClick(spin, Qt.Key.Key_Return)
    assert spin.value() == pytest.approx(155.8), "the validator is still the Python one"

    host = spin.host
    del spin.host
    sip.delete(host)                    # the window, the field, its line edit, the validator
    qapp.processEvents()
    _focused_spin(qtbot)                # the next field to take the focus prunes the list
    assert all(not sip.isdeleted(kept) for kept in number_fields._alive)
    assert len(number_fields._alive) <= held, "the destroyed field's validator is gone"


def test_the_app_installs_the_number_field_rule_on_its_application(qapp) -> None:
    """``main()`` installs it once on its QApplication (the test session does the same in
    ``conftest._app_locale``); a second call on the same application is a no-op."""
    import ast
    from pathlib import Path

    from open_garden_planner.ui import number_fields

    # read, not imported: importing ``main`` wants QtWebEngine before any application exists
    main_source = Path(i18n.__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(main_source.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "install_decimal_marks"]
    assert len(calls) == 1 and isinstance(calls[0].args[0], ast.Name)

    installed = number_fields._decimal_marks
    assert installed is not None and installed.parent() is qapp
    number_fields.install_decimal_marks(qapp)
    assert number_fields._decimal_marks is installed


def test_loading_a_language_that_fails_still_applies_a_locale(qtbot, speak, monkeypatch) -> None:
    """Whatever was loaded, Qt's default locale is the application's afterwards."""
    monkeypatch.setattr(i18n, "_TRANSLATIONS_DIR", i18n._TRANSLATIONS_DIR / "missing")
    speak("de", "en_US")
    # The catalog is missing, so the UI stays English, and so does its locale.
    assert i18n.current_language() == "en"
    assert QLocale().name() == "en_US"
