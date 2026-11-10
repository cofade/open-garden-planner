"""A one-line label that gives way to its row (#796)."""

from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QPainter, QPaintEvent
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget


class ElidedLabel(QLabel):
    """A label that may be narrower than its text, and then ends in "…".

    A plain ``QLabel`` is never narrower than its text. In a row whose other
    cells are a date and buttons that makes ONE long text decide the width of
    the whole list: a frost alert that names twenty plants pushed the date, the
    arrow and the Done button of every row of the calendar's task list out of
    view at 1280 px. This one takes the room the row has left; the full text is
    its tooltip.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setToolTip(text)

    def setText(self, text: str | None) -> None:
        super().setText(text)
        self.setToolTip(text or "")

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(
            self.text(), Qt.TextElideMode.ElideRight, rect.width())
        style = self.style()
        if style is not None:
            style.drawItemText(
                painter, rect, int(self.alignment()), self.palette(), self.isEnabled(), text,
                self.foregroundRole())
        painter.end()
