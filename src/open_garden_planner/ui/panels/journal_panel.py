"""Sidebar panel listing all garden-journal notes (US-12.9).

Renders one row per note (date + text snippet), sorted reverse-chronologically.
Supports text search across the note body and an optional date-range filter.
Double-clicking a row emits ``note_activated(note_id)``; the application
connects this to centre the viewport on the matching pin and open
:class:`JournalNoteDialog` for editing.
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.journal_note import JournalNote

_SNIPPET_CHARS = 64


class JournalPanel(QWidget):
    """Browse and filter the project's garden-journal notes."""

    note_activated = pyqtSignal(str)  # note_id

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._notes: dict[str, dict[str, Any]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._header = QLabel(self.tr("Garden journal:"))
        self._header.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._header)

        # Search box.
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(self.tr("Search notes…"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._rebuild_list)
        layout.addWidget(self._search_edit)

        # Date range row.
        range_row = QHBoxLayout()
        range_row.setSpacing(4)
        self._range_check = QCheckBox(self.tr("Date range"))
        self._range_check.toggled.connect(self._on_range_toggled)
        range_row.addWidget(self._range_check)

        today = _date.today()
        first = QDate(today.year, today.month, 1)
        self._date_from = QDateEdit(first)
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.setEnabled(False)
        self._date_from.dateChanged.connect(self._rebuild_list)
        range_row.addWidget(self._date_from)

        range_row.addWidget(QLabel("–"))

        self._date_to = QDateEdit(QDate(today.year, today.month, today.day))
        self._date_to.setCalendarPopup(True)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
        self._date_to.setEnabled(False)
        self._date_to.dateChanged.connect(self._rebuild_list)
        range_row.addWidget(self._date_to)
        layout.addLayout(range_row)

        # Results list.
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self._rebuild_list()

    # ── Data wiring ──────────────────────────────────────────────

    def refresh(self, notes: dict[str, Any]) -> None:
        """Replace the cached note dicts and rebuild the list.

        Args:
            notes: ``ProjectManager.garden_journal_notes`` — keyed by note id.
        """
        # Copy defensively so caller mutations don't bleed into the panel state.
        self._notes = {nid: dict(raw) for nid, raw in notes.items()}
        self._rebuild_list()

    # ── Behaviour ────────────────────────────────────────────────

    def _on_range_toggled(self, enabled: bool) -> None:
        self._date_from.setEnabled(enabled)
        self._date_to.setEnabled(enabled)
        self._rebuild_list()

    def _filter_matches(self, note: JournalNote, query: str) -> bool:
        if query and query not in note.text.lower():
            return False
        if not self._range_check.isChecked():
            return True
        # ISO YYYY-MM-DD string compare is lexicographic-safe.
        from_str = self._date_from.date().toString("yyyy-MM-dd")
        to_str = self._date_to.date().toString("yyyy-MM-dd")
        return from_str <= note.date <= to_str

    def _rebuild_list(self) -> None:
        self._list.clear()
        query = self._search_edit.text().strip().lower()
        rows: list[tuple[str, QListWidgetItem]] = []
        for note_id, raw in self._notes.items():
            try:
                note = JournalNote.from_dict(raw)
            except Exception:
                continue
            if not self._filter_matches(note, query):
                continue
            label = self._format_row(note)
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, note_id)
            rows.append((note.date or "", row))

        rows.sort(key=lambda r: r[0], reverse=True)
        for _, row in rows:
            self._list.addItem(row)

        if not rows:
            placeholder = QListWidgetItem(
                self.tr("No matching notes") if (
                    query or self._range_check.isChecked()
                ) else self.tr("No journal notes yet")
            )
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)

    def _format_row(self, note: JournalNote) -> str:
        snippet = note.text.strip().splitlines()[0] if note.text.strip() else ""
        if len(snippet) > _SNIPPET_CHARS:
            snippet = snippet[: _SNIPPET_CHARS - 1] + "…"
        photo_marker = "  📷" if note.photo_path else ""
        if snippet:
            return self.tr("{date} — {snippet}{photo}").format(
                date=note.date or "?",
                snippet=snippet,
                photo=photo_marker,
            )
        return self.tr("{date} — (empty){photo}").format(
            date=note.date or "?",
            photo=photo_marker,
        )

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        note_id = item.data(Qt.ItemDataRole.UserRole)
        if not note_id:
            return
        self.note_activated.emit(str(note_id))


__all__ = ["JournalPanel"]
