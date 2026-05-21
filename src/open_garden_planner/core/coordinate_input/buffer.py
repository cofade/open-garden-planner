"""Shared input state between status-bar field and cursor overlay.

A single ``CoordinateInputBuffer`` instance acts as the source of truth so
that whatever a user types in the status-bar field is mirrored in the
floating Dynamic Input overlay, and vice versa.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QPointF, pyqtSignal

from open_garden_planner.core.coordinate_input.parser import (
    ParsedCoordinate,
    ParseError,
    parse,
)


class CoordinateInputBuffer(QObject):
    """Holds the current typed coordinate string and the active anchor point.

    Signals:
        text_changed(str): The buffered string changed (use to mirror widgets).
        anchor_changed(QPointF | None): The active tool's last point changed.
        committed(QPointF): The user confirmed a parsed coordinate.
        parse_error(str): The current text failed to parse.
    """

    text_changed = pyqtSignal(str)
    anchor_changed = pyqtSignal(object)  # QPointF | None
    committed = pyqtSignal(QPointF)
    parse_error = pyqtSignal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._text = ""
        self._anchor: QPointF | None = None

    @property
    def text(self) -> str:
        return self._text

    @property
    def anchor(self) -> QPointF | None:
        return self._anchor

    def set_text(self, value: str) -> None:
        """Update the buffered string. Re-emits ``text_changed`` once."""
        if value == self._text:
            return
        self._text = value
        self.text_changed.emit(value)

    def clear(self) -> None:
        if not self._text:
            return
        self._text = ""
        self.text_changed.emit("")

    def set_anchor(self, point: QPointF | None) -> None:
        if point is None and self._anchor is None:
            return
        if (
            point is not None
            and self._anchor is not None
            and point == self._anchor
        ):
            return
        self._anchor = QPointF(point) if point is not None else None
        self.anchor_changed.emit(self._anchor)

    def try_parse(self) -> ParsedCoordinate | None:
        """Return a parsed coordinate or ``None`` if the text is empty."""
        if not self._text.strip():
            return None
        try:
            return parse(self._text, self._anchor)
        except ParseError as exc:
            self.parse_error.emit(str(exc))
            return None

    def commit(self) -> ParsedCoordinate | None:
        """Parse and emit ``committed`` on success. Returns the parsed coord."""
        result = self.try_parse()
        if result is None:
            return None
        self.committed.emit(result.point)
        return result
