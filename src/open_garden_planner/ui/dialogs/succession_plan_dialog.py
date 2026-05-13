"""Succession planting dialog (US-12.8).

Right-click a bed → "Plan Succession…" opens this dialog. On accept,
``result_plan()`` returns a ``SuccessionPlan`` ready to be wrapped in a
``SetSuccessionPlanCommand``.

Layout
------
* Year spin box at top.
* SeasonBandWidget — custom-painted horizontal timeline with four frost-
  relative season segments and entry pills positioned proportionally.
* QTableWidget — one row per SuccessionEntry (Season | Plant | Start | End).
* Add / Edit / Delete buttons.
* Companion notes area — predecessor/successor compatibility + overlap warnings.
* QDialogButtonBox (OK | Cancel).
"""

from __future__ import annotations

import datetime
from typing import Any

from PyQt6.QtCore import QCoreApplication, QDate, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.succession import (
    SEASON_SEGMENTS,
    SuccessionEntry,
    SuccessionPlan,
    compute_season_segments,
)

_SEGMENT_COLORS: dict[str, QColor] = {
    "early_spring": QColor(144, 202, 249, 200),  # Light blue
    "late_spring": QColor(129, 199, 132, 200),   # Green
    "summer": QColor(255, 213, 79, 200),          # Yellow
    "fall": QColor(255, 138, 101, 200),           # Orange
}

# Module-level segment labels are stored as the ENGLISH source strings, used
# both as the lookup key for translation AND as the fallback when no
# translator is loaded. Look up via ``_segment_label(key)`` so the strings
# are translated through the ``"SuccessionPlanDialog"`` context at runtime.
# The ``i18n-source`` markers exempt these literals from the
# ``TestNoHardcodedEnglish`` scanner — see tests/unit/test_i18n.py.
_SEGMENT_LABELS: dict[str, str] = {
    "early_spring": "Early Spring",  # i18n-source
    "late_spring": "Late Spring",    # i18n-source
    "summer": "Summer",              # i18n-source
    "fall": "Fall",                  # i18n-source
}


def _segment_label(key: str) -> str:
    """Translate a season-segment key for the current UI locale."""
    return QCoreApplication.translate("SuccessionPlanDialog", _SEGMENT_LABELS[key])

# Fallback boundaries (calendar-month-based) when no location is set.
# (month, day) tuples for start and end of each segment.
_FALLBACK_BOUNDARIES: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "early_spring": ((2, 1), (3, 31)),
    "late_spring": ((4, 1), (5, 31)),
    "summer": ((6, 1), (8, 31)),
    "fall": ((9, 1), (11, 15)),
}


def _fallback_segments(year: int) -> dict[str, tuple[datetime.date, datetime.date]]:
    return {
        key: (
            datetime.date(year, start[0], start[1]),
            datetime.date(year, end[0], end[1]),
        )
        for key, (start, end) in _FALLBACK_BOUNDARIES.items()
    }


def _date_to_segment_label(
    date_str: str,
    segments: dict[str, tuple[datetime.date, datetime.date]],
) -> str:
    """Return translated segment label for a date, or empty string."""
    try:
        d = datetime.date.fromisoformat(date_str)
    except ValueError:
        return ""
    for key in SEASON_SEGMENTS:
        start, end = segments[key]
        if start <= d <= end:
            return _segment_label(key)
    return ""


def _assign_pill_rows(
    entries: list[SuccessionEntry],
) -> list[tuple[SuccessionEntry, int]]:
    """Greedy first-fit row allocation so overlapping pills stack on new rows.

    Sorts by start_date, then places each pill in the first row whose previous
    pill ended before this pill starts. Returns (entry, row_index) pairs.
    """
    sortable = sorted(entries, key=lambda e: e.start_date or "9999")
    row_last_end: list[str] = []  # row_last_end[i] = end_date of last pill placed in row i
    placed: list[tuple[SuccessionEntry, int]] = []
    for entry in sortable:
        if not entry.start_date or not entry.end_date:
            placed.append((entry, 0))
            continue
        for idx, last_end in enumerate(row_last_end):
            if last_end < entry.start_date:
                row_last_end[idx] = entry.end_date
                placed.append((entry, idx))
                break
        else:
            row_last_end.append(entry.end_date)
            placed.append((entry, len(row_last_end) - 1))
    return placed


class _SeasonBandWidget(QWidget):
    """Custom-painted horizontal timeline showing season segments and entry pills."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._segments: dict[str, tuple[datetime.date, datetime.date]] = {}
        self._entries: list[SuccessionEntry] = []

    def set_data(
        self,
        segments: dict[str, tuple[datetime.date, datetime.date]],
        entries: list[SuccessionEntry],
    ) -> None:
        self._segments = segments
        self._entries = entries
        self._update_min_height()
        self.update()

    def _update_min_height(self) -> None:
        placements = _assign_pill_rows(self._entries)
        n_rows = max((row for _, row in placements), default=-1) + 1
        # band area (30) + per-row pill stack
        self.setMinimumHeight(int(34 + max(n_rows, 1) * 16))

    def paintEvent(self, event: Any) -> None:  # noqa: ANN001, ARG002
        if not self._segments:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        band_h = 26
        band_y = 4.0

        # Determine overall date range
        starts = [s for s, _ in self._segments.values()]
        ends = [e for _, e in self._segments.values()]
        range_start = min(starts)
        range_end = max(ends)
        total_days = max((range_end - range_start).days, 1)

        def _x(d: datetime.date) -> float:
            return (d - range_start).days / total_days * w

        # Draw segment bands
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        for key in SEASON_SEGMENTS:
            if key not in self._segments:
                continue
            seg_start, seg_end = self._segments[key]
            x1 = _x(seg_start)
            x2 = _x(seg_end)
            rect = QRectF(x1, band_y, x2 - x1, band_h)
            painter.fillRect(rect, _SEGMENT_COLORS[key])
            painter.setPen(QPen(QColor(60, 60, 60)))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, _segment_label(key))

        # Draw entry pills, stacking on separate rows when they overlap in time.
        pills_top = band_y + band_h + 4
        pill_h = 14.0
        row_gap = 2.0
        pill_font = QFont()
        pill_font.setPointSize(7)
        pill_font.setBold(True)
        fm = QFontMetrics(pill_font)
        painter.setFont(pill_font)

        for entry, row in _assign_pill_rows(self._entries):
            if not entry.start_date or not entry.end_date:
                continue
            try:
                es = datetime.date.fromisoformat(entry.start_date)
                ee = datetime.date.fromisoformat(entry.end_date)
            except ValueError:
                continue
            if es < range_start:
                es = range_start
            if ee > range_end:
                ee = range_end
            x1 = _x(es)
            x2 = max(_x(ee), x1 + 20)
            pill_y = pills_top + row * (pill_h + row_gap)
            pill = QRectF(x1, pill_y, x2 - x1, pill_h)
            painter.setBrush(QColor(46, 125, 50, 200))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pill, 4, 4)
            painter.setPen(QColor(255, 255, 255))
            label = entry.common_name or "?"
            label = fm.elidedText(label, Qt.TextElideMode.ElideRight, int(x2 - x1 - 4))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()


class _EntryDialog(QDialog):
    """Sub-dialog for adding or editing a single SuccessionEntry."""

    def __init__(
        self,
        parent: QWidget | None,
        segments: dict[str, tuple[datetime.date, datetime.date]],
        existing_entry: SuccessionEntry | None = None,
    ) -> None:
        super().__init__(parent)
        self._segments = segments
        self.setWindowTitle(
            self.tr("Edit Entry") if existing_entry else self.tr("Add Entry")
        )
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Plant name (free-text with hint)
        self._plant_edit = QLineEdit()
        self._plant_edit.setPlaceholderText(self.tr("e.g. Lettuce, Tomato, Spinach…"))
        form.addRow(self.tr("Plant"), self._plant_edit)

        # Start date
        self._start_edit = QDateEdit()
        self._start_edit.setCalendarPopup(True)
        self._start_edit.setDisplayFormat("yyyy-MM-dd")
        self._start_edit.dateChanged.connect(self._on_start_date_changed)
        form.addRow(self.tr("Start Date"), self._start_edit)

        # End date
        self._end_edit = QDateEdit()
        self._end_edit.setCalendarPopup(True)
        self._end_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(self.tr("End Date"), self._end_edit)

        # Notes
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setMaximumHeight(60)
        self._notes_edit.setPlaceholderText(self.tr("Optional notes…"))
        form.addRow(self.tr("Notes"), self._notes_edit)

        layout.addLayout(form)

        # Season hint label
        self._season_label = QLabel()
        self._season_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self._season_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Populate if editing
        if existing_entry:
            self._plant_edit.setText(existing_entry.common_name)
            if existing_entry.start_date:
                try:
                    d = datetime.date.fromisoformat(existing_entry.start_date)
                    self._start_edit.setDate(QDate(d.year, d.month, d.day))
                except ValueError:
                    pass
            if existing_entry.end_date:
                try:
                    d = datetime.date.fromisoformat(existing_entry.end_date)
                    self._end_edit.setDate(QDate(d.year, d.month, d.day))
                except ValueError:
                    pass
            self._notes_edit.setPlainText(existing_entry.notes)
        else:
            # Default: start of late spring (or today if outside segments)
            default_start = datetime.date.today()
            if "late_spring" in segments:
                default_start = segments["late_spring"][0]
            self._start_edit.setDate(
                QDate(default_start.year, default_start.month, default_start.day)
            )
            default_end = default_start + datetime.timedelta(weeks=6)
            self._end_edit.setDate(
                QDate(default_end.year, default_end.month, default_end.day)
            )

        self._on_start_date_changed()

        self._result_entry: SuccessionEntry | None = None
        self._edit_id: str = existing_entry.id if existing_entry else ""

    def _on_start_date_changed(self) -> None:
        qd = self._start_edit.date()
        d = datetime.date(qd.year(), qd.month(), qd.day())
        label = _date_to_segment_label(d.isoformat(), self._segments)
        self._season_label.setText(
            self.tr("Season: {seg}").format(seg=label) if label else ""
        )

    def _on_accept(self) -> None:
        name = self._plant_edit.text().strip()
        if not name:
            QMessageBox.warning(self, self.tr("Validation"), self.tr("Plant name is required."))
            return
        qs = self._start_edit.date()
        qe = self._end_edit.date()
        start = datetime.date(qs.year(), qs.month(), qs.day())
        end = datetime.date(qe.year(), qe.month(), qe.day())
        if end < start:
            QMessageBox.warning(
                self,
                self.tr("Validation"),
                self.tr("End date must not be before start date."),
            )
            return
        # Resolve free-text name to canonical species. Tries bundled species DB
        # first (gives scientific_name); falls back to companion service's
        # alias / localised-name index so e.g. "Tomate" → "tomato" for the
        # companion-relationship lookup.
        from open_garden_planner.services.bundled_species_db import (  # noqa: PLC0415
            get_species_by_common_name,
        )
        from open_garden_planner.services.companion_planting_service import (  # noqa: PLC0415
            CompanionPlantingService,
        )

        species = get_species_by_common_name(name)
        scientific = species.get("scientific_name", "") if species else ""
        canonical = CompanionPlantingService().resolve_name(name)
        species_key = scientific.lower() if scientific else canonical

        self._result_entry = SuccessionEntry(
            id=self._edit_id or SuccessionEntry().id,
            species_key=species_key,
            common_name=name,
            scientific_name=scientific,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            notes=self._notes_edit.toPlainText().strip(),
        )
        self.accept()

    def result_entry(self) -> SuccessionEntry | None:
        return self._result_entry


class SuccessionPlanDialog(QDialog):
    """Modal dialog for planning succession crops in a single bed."""

    def __init__(
        self,
        parent: QWidget | None = None,
        bed_id: str = "",
        bed_name: str = "",
        existing_plan: SuccessionPlan | None = None,
        frost_dates: dict[str, Any] | None = None,
        project_manager: Any | None = None,
        command_manager: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._bed_id = bed_id
        self._bed_name = bed_name
        self._project_manager = project_manager
        self._command_manager = command_manager

        self.setWindowTitle(
            self.tr("Succession Plan: {name}").format(name=bed_name)
            if bed_name
            else self.tr("Succession Plan")
        )
        self.setModal(True)
        self.setMinimumWidth(540)

        # Determine starting year
        year = (
            existing_plan.year
            if existing_plan
            else (datetime.date.today().year)
        )

        # Compute frost-relative segments
        self._frost_dates_raw = frost_dates
        self._segments = self._build_segments(year, frost_dates)
        self._no_location = frost_dates is None or not frost_dates.get("frost_dates")

        # Working copy of entries
        self._entries: list[SuccessionEntry] = list(
            existing_plan.entries if existing_plan else []
        )

        self._setup_ui(year)
        self._refresh_table()
        self._refresh_band()
        self._refresh_companion_notes()

        self._result_plan: SuccessionPlan | None = None

    # ── Segment helpers ──────────────────────────────────────────────────────

    def _build_segments(
        self,
        year: int,
        frost_dates: dict[str, Any] | None,
    ) -> dict[str, tuple[datetime.date, datetime.date]]:
        if frost_dates and frost_dates.get("frost_dates"):
            fd = frost_dates["frost_dates"]
            last = fd.get("last_spring_frost", "")
            fall = fd.get("first_fall_frost", "")
            if last and fall:
                try:
                    return compute_season_segments(last, fall, year)
                except (ValueError, KeyError):
                    pass
        return _fallback_segments(year)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self, year: int) -> None:
        layout = QVBoxLayout(self)

        # Year row
        year_row = QHBoxLayout()
        year_row.addWidget(QLabel(self.tr("Year")))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2000, 2100)
        self._year_spin.setValue(year)
        self._year_spin.valueChanged.connect(self._on_year_changed)
        year_row.addWidget(self._year_spin)
        year_row.addStretch()
        layout.addLayout(year_row)

        # No-location warning
        if self._no_location:
            warn = QLabel(
                self.tr("Set project location for accurate season dates.")
            )
            warn.setStyleSheet("color: #888; font-style: italic;")
            layout.addWidget(warn)

        # Season band
        self._band = _SeasonBandWidget()
        layout.addWidget(self._band)

        # Entries table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels([
            self.tr("Season"),
            self.tr("Plant"),
            self.tr("Start Date"),
            self.tr("End Date"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.doubleClicked.connect(self._on_edit)
        self._table.setMinimumHeight(120)
        layout.addWidget(self._table)

        # CRUD buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton(self.tr("Add Entry"))
        add_btn.clicked.connect(self._on_add)
        edit_btn = QPushButton(self.tr("Edit Entry"))
        edit_btn.clicked.connect(self._on_edit)
        del_btn = QPushButton(self.tr("Delete Entry"))
        del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Companion notes
        notes_box = QGroupBox(self.tr("Crop Compatibility"))
        notes_layout = QVBoxLayout(notes_box)
        self._companion_text = QLabel()
        self._companion_text.setWordWrap(True)
        self._companion_text.setAlignment(Qt.AlignmentFlag.AlignTop)
        notes_layout.addWidget(self._companion_text)
        layout.addWidget(notes_box)

        # OK / Cancel
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ── Refresh helpers ──────────────────────────────────────────────────────

    def _refresh_table(self) -> None:
        self._table.setRowCount(0)
        for entry in self._entries_sorted():
            row = self._table.rowCount()
            self._table.insertRow(row)
            seg = _date_to_segment_label(entry.start_date, self._segments)
            self._table.setItem(row, 0, QTableWidgetItem(seg))
            self._table.setItem(row, 1, QTableWidgetItem(entry.common_name))
            self._table.setItem(row, 2, QTableWidgetItem(entry.start_date))
            self._table.setItem(row, 3, QTableWidgetItem(entry.end_date))
        self._table.resizeColumnsToContents()

    def _refresh_band(self) -> None:
        self._band.set_data(self._segments, self._entries_sorted())

    def _refresh_companion_notes(self) -> None:
        notes = self._compute_companion_notes()
        if notes:
            self._companion_text.setText("\n".join(notes))
        else:
            self._companion_text.setText(
                self.tr("No compatibility data for current entries.")
            )

    def _entries_sorted(self) -> list[SuccessionEntry]:
        def _key(e: SuccessionEntry) -> str:
            return e.start_date or "9999-99-99"
        return sorted(self._entries, key=_key)

    def _compute_companion_notes(self) -> list[str]:
        """Build companion compatibility messages for current entries.

        Reasons are rendered in the user's UI language via
        ``get_relationship_reason(rel, lang)`` (falls back to English when the
        DB entry has no ``reason_de``). The "overlaps" warning prefix is also
        wrapped with ``tr()`` so all visible strings translate.
        """
        # Imports are deferred to keep the dialog importable without the
        # application module fully loaded (e.g. in isolated unit tests).
        # ImportError is the only failure we tolerate — anything else (e.g.
        # malformed companion DB) should surface so it can be fixed.
        try:
            from open_garden_planner.app.application import (  # noqa: PLC0415
                GardenPlannerApp,
            )
            from open_garden_planner.services.companion_planting_service import (  # noqa: PLC0415
                CompanionPlantingService,
            )
        except ImportError:
            return []
        svc = CompanionPlantingService()
        lang = GardenPlannerApp._current_lang()

        notes: list[str] = []
        sorted_entries = self._entries_sorted()

        # Predecessor / successor pairs
        for a, b in zip(sorted_entries, sorted_entries[1:], strict=False):
            rel = svc.get_relationship(a.common_name, b.common_name)
            if rel:
                arrow = "✓" if rel.type == "beneficial" else ("⚠" if rel.type == "antagonistic" else "·")
                reason = svc.get_relationship_reason(rel, lang)
                notes.append(
                    f"{arrow} {a.common_name} → {b.common_name}: {reason}"
                )

        # Overlapping pairs (antagonist warning)
        overlap_template = self.tr("{a} overlaps {b}: antagonist")
        for i, a in enumerate(sorted_entries):
            if not a.end_date:
                continue
            for b in sorted_entries[i + 1:]:
                if not b.start_date:
                    continue
                if b.start_date < a.end_date:
                    rel = svc.get_relationship(a.common_name, b.common_name)
                    if rel and rel.type == "antagonistic":
                        notes.append(
                            "⚠ " + overlap_template.format(
                                a=a.common_name, b=b.common_name
                            )
                        )
                else:
                    break
        return notes

    # ── Slot handlers ────────────────────────────────────────────────────────

    def _on_year_changed(self, year: int) -> None:
        self._segments = self._build_segments(year, self._frost_dates_raw)
        self._refresh_band()
        self._refresh_table()
        self._refresh_companion_notes()

    def _on_add(self) -> None:
        dlg = _EntryDialog(self, self._segments)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = dlg.result_entry()
            if entry:
                self._entries.append(entry)
                self._refresh_table()
                self._refresh_band()
                self._refresh_companion_notes()

    def _on_edit(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        sorted_entries = self._entries_sorted()
        if row >= len(sorted_entries):
            return
        target = sorted_entries[row]
        dlg = _EntryDialog(self, self._segments, existing_entry=target)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_entry = dlg.result_entry()
            if new_entry:
                for i, e in enumerate(self._entries):
                    if e.id == target.id:
                        self._entries[i] = new_entry
                        break
                self._refresh_table()
                self._refresh_band()
                self._refresh_companion_notes()

    def _on_delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            return
        sorted_entries = self._entries_sorted()
        if row >= len(sorted_entries):
            return
        target = sorted_entries[row]
        self._entries = [e for e in self._entries if e.id != target.id]
        self._refresh_table()
        self._refresh_band()
        self._refresh_companion_notes()

    def _on_accept(self) -> None:
        year = self._year_spin.value()
        self._result_plan = SuccessionPlan(
            bed_id=self._bed_id,
            year=year,
            entries=list(self._entries),
        )
        self.accept()

    def result_plan(self) -> SuccessionPlan | None:
        """Return the edited SuccessionPlan (only valid after accept())."""
        return self._result_plan
