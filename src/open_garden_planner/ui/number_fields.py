"""Either decimal mark is the decimal mark in a number field (#792, ADR-077).

A ``QDoubleSpinBox`` reads the mark of the other convention as a GROUP separator
and silently drops it: with an English locale "155,8" becomes 1558, with a
German one "155.8" does. The locale follows the UI language and the keyboard
and the clipboard do not: the numeric keypad of a German keyboard types a comma
into an English UI, and a number copied from a German table is pasted into one.

One mechanism covers every way text reaches the field (a key, Ctrl+V, the
context menu's Paste, a drop): a validator in FRONT of the field's own. When
the number part holds exactly one mark and it is the other convention's, the
validator rewrites it to the field's decimal mark and then lets the field's own
validator decide. Text with more than one mark is handed on untouched: Qt reads
it in the field's locale (its own grouping is accepted, the other convention's
is refused), so nothing is guessed. A ``QSpinBox`` has no decimal mark and is
never touched.

It is installed on the spin box that takes the focus, never application-wide:
a Python event filter on the application would run for every event of every
object.
"""

from __future__ import annotations

import functools

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QValidator
from PyQt6.QtWidgets import QApplication, QDoubleSpinBox, QWidget

_MARKS = (",", ".")


def with_field_mark(text: str, mark: str) -> str:
    """*text* with its ONE decimal mark written as *mark*; any other text unchanged.

    Only a text that holds exactly one of ``,`` and ``.`` is rewritten: that one
    is the decimal mark whichever convention wrote it. Two or more marks mean a
    group separator is present, and which one groups is the locale's to say.
    """
    if mark not in _MARKS or text.count(",") + text.count(".") != 1:
        return text
    other = "," if mark == "." else "."
    return text.replace(other, mark)


class _EitherDecimalMark(QValidator):
    """Stands in front of a ``QDoubleSpinBox``'s own validator (module docstring)."""

    def __init__(self, spin: QDoubleSpinBox, own: QValidator) -> None:
        super().__init__(spin.lineEdit())
        self._spin = spin
        self._own = own

    def validate(self, text: str | None, position: int) -> tuple[QValidator.State, str, int]:
        return self._own.validate(self._rewritten(text or ""), position)

    def fixup(self, text: str | None) -> str:
        return self._own.fixup(text or "")

    def _rewritten(self, text: str) -> str:
        spin = self._spin
        if text == spin.specialValueText():
            return text
        # The number stands between the prefix and the suffix; a mark in either
        # of them ("ca. ", " m.") is not the number's.
        prefix, suffix = spin.prefix(), spin.suffix()
        start = len(prefix) if prefix and text.startswith(prefix) else 0
        end = len(text) - len(suffix) if suffix and text.endswith(suffix) else len(text)
        if end < start:
            return text
        number = with_field_mark(text[start:end], spin.locale().decimalPoint())
        return text[:start] + number + text[end:]


class DecimalMarks(QObject):
    """Gives every ``QDoubleSpinBox`` that takes the focus the validator above."""

    def __init__(self, app: QApplication) -> None:
        super().__init__(app)
        app.focusChanged.connect(self._on_focus_changed)

    def _on_focus_changed(self, _old: QWidget | None, new: QWidget | None) -> None:
        if isinstance(new, QDoubleSpinBox) and not sip.isdeleted(new):
            accept_either_decimal_mark(new)


#: The validators in use, by ``id``. Qt owns each one through its line edit, but
#: the Python half lives only while Python holds it: ``spin.lineEdit()`` hands
#: out a temporary wrapper, and when that goes the validator's Python object
#: would go with it and leave Qt calling the base class, which refuses every
#: text. An entry leaves when Qt destroys the validator with its field.
_alive: dict[int, _EitherDecimalMark] = {}


def _forget(key: int, *_destroyed: object) -> None:
    """Drop a validator Qt has destroyed (``destroyed`` passes the object along)."""
    _alive.pop(key, None)


def accept_either_decimal_mark(spin: QDoubleSpinBox) -> None:
    """Put the validator in front of *spin*'s own, once."""
    editor = spin.lineEdit()
    own = editor.validator() if editor is not None else None
    if editor is None or own is None or isinstance(own, _EitherDecimalMark):
        return
    validator = _EitherDecimalMark(spin, own)
    _alive[id(validator)] = validator
    validator.destroyed.connect(functools.partial(_forget, id(validator)))
    editor.setValidator(validator)


_decimal_marks: DecimalMarks | None = None


def install_decimal_marks(app: QApplication) -> None:
    """Install :class:`DecimalMarks` on *app*, once per application object."""
    global _decimal_marks
    if (_decimal_marks is None or sip.isdeleted(_decimal_marks)
            or _decimal_marks.parent() is not app):
        _decimal_marks = DecimalMarks(app)
