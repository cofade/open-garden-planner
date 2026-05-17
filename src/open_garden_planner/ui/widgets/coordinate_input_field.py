"""Status-bar typed coordinate input field (Package A US-A1/A2).

Backed by a shared :class:`CoordinateInputBuffer` so the same state is
mirrored in the floating Dynamic Input overlay (US-A4).  The field
delegates parsing to the buffer and dispatches the parsed point to the
active tool's :meth:`commit_typed_coordinate`.
"""

from __future__ import annotations

from PyQt6.QtCore import QPointF, pyqtSignal
from PyQt6.QtGui import QFocusEvent
from PyQt6.QtWidgets import QLineEdit

from open_garden_planner.core.coordinate_input import CoordinateInputBuffer


class CoordinateInputField(QLineEdit):
    """Status-bar QLineEdit that drives typed coordinate placement.

    Signals:
        commit_requested(QPointF): A valid parsed coordinate is ready.
    """

    commit_requested = pyqtSignal(QPointF)

    def __init__(
        self,
        buffer: CoordinateInputBuffer,
        parent: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._buffer = buffer
        # Translate via self.tr() inside __init__ so the active QTranslator
        # is honoured even if it was installed after this module's import.
        self.setPlaceholderText(self.tr("@dx,dy   @dist<angle   x,y"))
        self._help_tooltip = self.tr(
            "Typed coordinate input. Examples: @500,0 (relative), "
            "@300<45 (polar, 0deg = east, CCW positive), 1000,500 "
            "(absolute). Press Enter to commit."
        )
        self.setToolTip(self._help_tooltip)
        self.setClearButtonEnabled(True)
        self.setMaxLength(40)
        self.setMinimumWidth(180)
        self.setMaximumWidth(220)

        self._suppress_buffer_signal = False
        self.textEdited.connect(self._on_text_edited)
        self.returnPressed.connect(self._on_return)
        buffer.text_changed.connect(self._on_buffer_text_changed)
        buffer.parse_error.connect(self._on_parse_error)
        buffer.committed.connect(self._on_committed)

    # --- Slots ---------------------------------------------------------

    def _on_text_edited(self, text: str) -> None:
        # Set the buffer without echoing back to ourselves.
        self._buffer.set_text(text)
        # Clear the stuck error tooltip (if any) on the first keystroke
        # after a ParseError; the user is correcting the input now.
        if self.toolTip() != self._help_tooltip:
            self.setToolTip(self._help_tooltip)
            self._clear_error_styling()

    def _on_return(self) -> None:
        result = self._buffer.commit()
        if result is None:
            self._flash_error()
            return
        # Successful commit -- emit and clear.
        self.commit_requested.emit(result.point)
        self._buffer.clear()

    def _on_buffer_text_changed(self, text: str) -> None:
        if text == self.text():
            return
        # Avoid re-entering textEdited -> setText loop.
        self._suppress_buffer_signal = True
        try:
            self.setText(text)
            self._clear_error_styling()
        finally:
            self._suppress_buffer_signal = False

    def _on_parse_error(self, message: str) -> None:
        self._flash_error()
        # Thread the parser's diagnostic into the field tooltip so the
        # user gets feedback beyond a red flash (e.g. polar without
        # anchor, malformed number, ambiguous separator).  Translate
        # via the "ParseError" context registered in fill_translations.py.
        if message:
            from PyQt6.QtCore import QCoreApplication

            self.setToolTip(QCoreApplication.translate("ParseError", message))

    def _on_committed(self, _point: QPointF) -> None:
        self._clear_error_styling()
        # Restore the help tooltip after a clean commit.
        self.setToolTip(self._help_tooltip)

    # --- Visual ---------------------------------------------------------

    def _flash_error(self) -> None:
        # Red background tint until next edit or successful commit.
        self.setStyleSheet(
            "QLineEdit { background-color: rgba(255, 80, 80, 60); }"
        )

    def _clear_error_styling(self) -> None:
        self.setStyleSheet("")

    # --- Focus management ----------------------------------------------

    def focusOutEvent(self, event: QFocusEvent) -> None:  # noqa: N802 (Qt)
        self._clear_error_styling()
        super().focusOutEvent(event)
