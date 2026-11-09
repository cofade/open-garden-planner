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

import re
from pathlib import Path

from PyQt6 import sip
from PyQt6.QtCore import QCoreApplication, QEvent, QLibraryInfo, QLocale, QObject, Qt, QTranslator
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
    return locale_for_language(_current_language)


def _apply_locale() -> None:
    """Make Qt's default locale the application's: every spin box, date edit and
    bare ``QLocale()`` created from here on formats in the UI language."""
    QLocale.setDefault(current_locale())


def format_decimal(value: float, decimals: int = 1) -> str:
    """``value`` with a fixed number of decimals in the application's locale.

    The ONE formatter for a number in UI text ("6361.7" in English, "6361,7" in
    German). No group separators: a spin box shows none either, and in a CAD
    readout "1.234" must never be readable as a decimal.
    """
    locale = current_locale()
    locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    return locale.toString(float(value), "f", int(decimals))


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

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
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
