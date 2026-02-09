"""Internationalization (i18n) support for Open Garden Planner.

Manages loading Qt translator files (.qm) for the selected UI language.
"""

from pathlib import Path

from PyQt6.QtCore import QLibraryInfo, QLocale, QTranslator
from PyQt6.QtWidgets import QApplication

# Supported languages: code -> native display name
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "Deutsch",
}

_TRANSLATIONS_DIR = Path(__file__).parent.parent / "resources" / "translations"

# Keep references so translators aren't garbage-collected
_active_translators: list[QTranslator] = []


def load_translator(app: QApplication, lang_code: str) -> bool:
    """Install a QTranslator for the given language.

    For English (the source language), no translator is needed.
    For other languages, loads the corresponding .qm file from
    the translations directory.

    Also loads the Qt base translations (buttons like OK/Cancel)
    for the target locale.

    Args:
        app: The QApplication instance.
        lang_code: Language code (e.g. 'en', 'de').

    Returns:
        True if the translator was loaded (or not needed for English),
        False if loading failed.
    """
    # Clear any previously installed translators
    for translator in _active_translators:
        app.removeTranslator(translator)
    _active_translators.clear()

    # English is the source language — no translation needed
    if lang_code == "en":
        return True

    # Load Qt's own translations (OK, Cancel, etc.)
    qt_translator = QTranslator(app)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(QLocale(lang_code), "qtbase", "_", qt_translations_path):
        app.installTranslator(qt_translator)
        _active_translators.append(qt_translator)

    # Load our app translations
    app_translator = QTranslator(app)
    qm_file = _TRANSLATIONS_DIR / f"open_garden_planner_{lang_code}.qm"

    if qm_file.exists() and app_translator.load(str(qm_file)):
        app.installTranslator(app_translator)
        _active_translators.append(app_translator)
        return True

    return False
