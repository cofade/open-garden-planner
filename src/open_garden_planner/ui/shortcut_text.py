"""Keyboard-shortcut text in the user's language.

Qt's ``QKeySequence.toString(NativeText)`` is only as native as the Qt
translation catalog that happens to be loaded; this app ships its own catalogs
and does not install Qt's, so the platform name still arrives as "Shift" /
"Ctrl". The tokens are translated through the same ``ShortcutsDialog`` context
the shortcuts dialog has always used, which keeps one set of translations for
both surfaces (PF-UI-32: the constraint toolbar showed "Umschalt+C ... Shift+C").
"""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QKeySequence


#: Modifier and named-key tokens Qt's native text uses. The shortcuts dialog
#: deliberately passes plain strings ("Ctrl+Shift+Up"), the toolbar passes a
#: real key sequence ("Shift+C"); both end here. Built per call, not at import:
#: the translator can change at runtime (language switch).
def _translated_tokens() -> dict[str, str]:
    return {
        "Ctrl": QCoreApplication.translate("ShortcutsDialog", "Ctrl"),
        "Shift": QCoreApplication.translate("ShortcutsDialog", "Shift"),
        "Alt": QCoreApplication.translate("ShortcutsDialog", "Alt"),
        "Delete": QCoreApplication.translate("ShortcutsDialog", "Delete"),
        "Escape": QCoreApplication.translate("ShortcutsDialog", "Escape"),
        "Up": QCoreApplication.translate("ShortcutsDialog", "Up"),
        "Down": QCoreApplication.translate("ShortcutsDialog", "Down"),
    }


def translate_shortcut_tokens(text: str) -> str:
    """Replace the English modifier/key names in *text* with the UI's names."""
    result = text
    for token, translated in _translated_tokens().items():
        result = result.replace(token, translated)
    return result


def localized_shortcut(shortcut: str) -> str:
    """A shortcut string as the user should see it: native form, localized tokens."""
    native = QKeySequence(shortcut).toString(
        QKeySequence.SequenceFormat.NativeText
    )
    return translate_shortcut_tokens(native)
