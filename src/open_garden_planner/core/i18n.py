"""Internationalization (i18n) support for Open Garden Planner.

Manages loading Qt translator files (.qm) for the selected UI language, and
decides the application's LOCALE from that language (#792): month and weekday
names, decimal marks and number formats follow the language the UI speaks, never
the operating system's locale on its own. :func:`load_translator` is the one
place that decides; everything else asks :func:`current_locale` or one of the
formatters below (a bare ``QLocale()`` agrees, because the decision is also
Qt's default locale).
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import (
    QCoreApplication,
    QDate,
    QEvent,
    QLibraryInfo,
    QLocale,
    QObject,
    Qt,
    QTranslator,
)
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QWidget

# Supported languages: code -> native display name
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "ru": "Русский",
}

_TRANSLATIONS_DIR = Path(__file__).parent.parent / "resources" / "translations"

# Keep references so translators aren't garbage-collected
_active_translators: list[QTranslator] = []
_current_language: str = "en"
# The locale decided for ``_current_language``; None until first asked for.
_current_locale: QLocale | None = None


def current_language() -> str:
    """Return the currently loaded language code (e.g. 'en', 'de', 'es', 'ru')."""
    return _current_language


def set_current_language(lang_code: str) -> None:
    """Set the active language code (and with it the application's locale)."""
    global _current_language
    if lang_code in SUPPORTED_LANGUAGES:
        _current_language = lang_code
        _apply_locale()


def _system_locale() -> QLocale:
    """The operating system's locale — the seam tests replace."""
    return QLocale.system()


def locale_for_language(lang_code: str) -> QLocale:
    """The locale of a UI language.

    The language decides. The operating system contributes its REGION, and only
    when it speaks the same language (a German UI on an Austrian or a Swiss
    system keeps that country's formats); otherwise the language's own default
    region is used. The result is always built from Qt's own locale data, never
    the system locale object itself: that one takes its names from the operating
    system ("Mrz" and "Mo" on Windows where Qt's data says "Mär" and "Mo."), so
    the same UI language would read differently from machine to machine.
    """
    locale = QLocale(lang_code)
    system = _system_locale()
    if system.language() == locale.language():
        regional = QLocale(locale.language(), system.territory())
        if regional.language() == locale.language():
            return regional
    return locale


def current_locale() -> QLocale:
    """Return the locale of the currently loaded language (a copy)."""
    global _current_locale
    if _current_locale is None:
        _current_locale = locale_for_language(_current_language)
    return QLocale(_current_locale)


def _apply_locale() -> None:
    """Make Qt's default locale the application's: every spin box, date edit and
    bare ``QLocale()`` created from here on formats in the UI language."""
    global _current_locale
    _current_locale = locale_for_language(_current_language)
    QLocale.setDefault(_current_locale)


def format_decimal(value: float, decimals: int = 1) -> str:
    """``value`` with a fixed number of decimals in the application's locale.

    The ONE formatter for a number in UI text ("6361.7" in English, "6361,7" in
    German). No group separators: a spin box shows none either, and in a CAD
    readout "1.234" must never be readable as a decimal.
    """
    locale = current_locale()
    locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return locale.toString(float(value), "f", int(decimals))


def format_trimmed(value: float, max_decimals: int = 3) -> str:
    """Like :func:`format_decimal`, without trailing zeros ("2.5", "3")."""
    text = format_decimal(value, max_decimals)
    mark = current_locale().decimalPoint()
    if mark and mark in text:
        text = text.rstrip("0").rstrip(mark)
    return text


def format_integer(value: int) -> str:
    """A whole number WITH the locale's group separators ("1,920" / "1.920").

    For counts a reader scans (pixels of an export), never for a measurement:
    :func:`format_decimal` has no group separators on purpose.
    """
    return current_locale().toString(int(value))


def list_separator() -> str:
    """What separates two numbers written side by side ("52.52, 13.40").

    A comma is no separator where it is the decimal mark: "52,52, 13,40" reads
    as four numbers, so those languages get a semicolon.
    """
    return "; " if current_locale().decimalPoint() == "," else ", "


def month_abbreviation(month: int) -> str:
    """The short name of a month (1 … 12) as a column header or a label.

    The STANDALONE form: German says "Mär" there and "März" inside a date.
    """
    return current_locale().standaloneMonthName(month, QLocale.FormatType.ShortFormat)


def format_day_month(day: datetime.date) -> str:
    """A day without its year ("Jun 21", "21. Juni").

    The ORDER of day and month belongs to the language, so the pattern is a
    translated string (a Qt date pattern: ``d`` the day, ``MMM`` the short
    month); the names come from the application's locale.
    """
    pattern = QCoreApplication.translate("DateFormat", "MMM d")
    return current_locale().toString(QDate(day.year, day.month, day.day), pattern)


def format_short_date(day: datetime.date) -> str:
    """A whole date in UI text ("7 Jun 2026", "7. Juni 2026").

    The ONE formatter for a date a label, a card or a legend writes. Day, the
    month's short NAME, the year: never a numeric day/month pair, whose order
    belongs to the locale's territory and not to the UI language ("6/7/26" is
    7 June in ``en_US``, the locale of an English UI on a non-English system,
    and 6 July to the European reading it). The pattern is a translated Qt
    date pattern like :func:`format_day_month`'s; the name comes from the
    application's locale. A date FIELD or key is ISO instead
    (``ui/date_fields``).
    """
    pattern = QCoreApplication.translate("DateFormat", "d MMM yyyy")
    return current_locale().toString(QDate(day.year, day.month, day.day), pattern)


def parse_decimal(text: str) -> float:
    """The number a user typed, whichever decimal mark they used.

    The inverse of :func:`format_decimal` for free-text fields: what the UI
    shows ("6361,7") must be accepted back, and so must the other convention
    ("6361.7"), because the keyboard does not follow the UI language. Group
    separators are not accepted — the formatters never write one. Raises
    ``ValueError`` like ``float`` does.
    """
    return float(text.strip().replace(",", "."))


_FIXED_SPEC = re.compile(r"\.(\d+)f")


class LocalizedNumber(float):
    """A float that formats itself in the application's locale.

    For a translated template that carries its own precision
    (``"{d:.2f} m".format(d=LocalizedNumber(x))``): the catalogs keep their
    source strings, and the number still follows the UI language.
    """

    def __format__(self, spec: str) -> str:
        match = _FIXED_SPEC.fullmatch(spec)
        if match:
            return format_decimal(float(self), int(match.group(1)))
        return float.__format__(self, spec)


class _DecimalKeys(QObject):
    """Either decimal key types the decimal mark in a number field.

    A ``QDoubleSpinBox`` silently DROPS the mark of the other convention: with an
    English locale "155,8" becomes 1558, with a German one "155.8" does. Since
    the locale follows the UI language (#792) and not the keyboard, the numeric
    keypad of a German keyboard (it types a comma) would otherwise enter a value
    ten times too large into an English UI. Watches only the focused spin box.
    """

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        self._watched: QWidget | None = None
        app.focusChanged.connect(self._on_focus_changed)

    def _on_focus_changed(self, _old: QWidget | None, new: QWidget | None) -> None:
        watched = self._watched
        if watched is not None and not sip.isdeleted(watched):
            watched.removeEventFilter(self)
        self._watched = None
        if isinstance(new, QDoubleSpinBox):
            new.installEventFilter(self)
            self._watched = new

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:
        if (
            isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
            and isinstance(obj, QDoubleSpinBox)
            and event.text() in (",", ".")
            and not event.modifiers() & (
                Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
        ):
            mark = obj.locale().decimalPoint()
            if mark in (",", ".") and event.text() != mark:
                key = Qt.Key.Key_Comma if mark == "," else Qt.Key.Key_Period
                QCoreApplication.sendEvent(
                    obj, QKeyEvent(QEvent.Type.KeyPress, key, event.modifiers(), mark))
                return True
        return False


_decimal_keys: _DecimalKeys | None = None


def _install_decimal_keys(app: QApplication) -> None:
    global _decimal_keys
    if _decimal_keys is None or sip.isdeleted(_decimal_keys) or _decimal_keys.parent() is not app:
        _decimal_keys = _DecimalKeys(app)


def load_translator(app: QApplication, lang_code: str) -> bool:
    """Install a QTranslator for the given language.

    For English (the source language), no translator is needed.
    For other languages, loads the corresponding .qm file from
    the translations directory.

    Also loads the Qt base translations (buttons like OK/Cancel)
    for the target locale, and makes that language's locale the
    application's (see the module docstring): call this BEFORE any widget is
    built — a widget keeps the locale it was created with.

    Args:
        app: The QApplication instance.
        lang_code: Language code (e.g. 'en', 'de').

    Returns:
        True if the translator was loaded (or not needed for English),
        False if loading failed.
    """
    try:
        return _load_translator(app, lang_code)
    finally:
        # Whatever was loaded: the locale belongs to the language now on screen.
        _apply_locale()
        _install_decimal_keys(app)


def _load_translator(app: QApplication, lang_code: str) -> bool:
    global _current_language

    # Clear any previously installed translators
    for translator in _active_translators:
        app.removeTranslator(translator)
    _active_translators.clear()

    # English is the source language — no translation needed
    if lang_code == "en":
        _current_language = "en"
        return True

    # Load Qt's own translations (OK, Cancel, About Qt dialog, etc.)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)

    qt_translator = QTranslator(app)
    if qt_translator.load(QLocale(lang_code), "qtbase", "_", qt_translations_path):
        app.installTranslator(qt_translator)
        _active_translators.append(qt_translator)

    # Also load the meta qt_*.qm (covers additional dialogs like About Qt)
    qt_meta_translator = QTranslator(app)
    if qt_meta_translator.load(QLocale(lang_code), "qt", "_", qt_translations_path):
        app.installTranslator(qt_meta_translator)
        _active_translators.append(qt_meta_translator)

    # Load our app translations
    app_translator = QTranslator(app)
    qm_file = _TRANSLATIONS_DIR / f"open_garden_planner_{lang_code}.qm"

    if qm_file.exists() and app_translator.load(str(qm_file)):
        app.installTranslator(app_translator)
        _active_translators.append(app_translator)
        _current_language = lang_code
        return True

    return False
