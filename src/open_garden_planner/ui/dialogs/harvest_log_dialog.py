"""Harvest / yield log dialog (US-C1, epic #188).

Right-click a plant or bed → "Log Harvest…" to open this dialog. On accept,
``result_record()`` returns a populated :class:`HarvestRecord` ready to be
wrapped in an ``AddHarvestRecordCommand``.

Two tabs (collapsed to one in edit mode):
  * Entry   — date, quantity, unit, quality, notes, optional photo.
  * History — chronological list of past entries grouped by year (with per-unit
              year subtotals) and Edit/Delete buttons. Hidden in edit mode.
"""
from __future__ import annotations

import shutil
import uuid
from datetime import date as _date
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDate, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.app.paths import default_dialog_dir
from open_garden_planner.models.harvest_log import HarvestHistory, HarvestRecord

#: Default unit choices offered in the (editable) unit combo.
_UNIT_CHOICES = ("kg", "g", "pcs", "bunch", "L")


class HarvestLogDialog(QDialog):
    """Modal dialog for entering a single harvest record."""

    def __init__(
        self,
        parent: QWidget | None = None,
        target_id: str = "",
        target_name: str = "",
        existing_history: HarvestHistory | None = None,
        edit_mode: bool = False,
        edit_record: HarvestRecord | None = None,
        project_manager: Any | None = None,
        command_manager: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._target_id = target_id
        self._target_name = target_name
        self._edit_mode = edit_mode
        self._edit_record_id = edit_record.id if (edit_mode and edit_record) else None
        # Preserve the journal-note link across edits.
        self._edit_journal_note_id = (
            edit_record.journal_note_id if (edit_mode and edit_record) else None
        )
        self._project_manager = project_manager
        self._command_manager = command_manager
        self._existing_history = existing_history
        self._photo_path: str | None = (
            edit_record.photo_path if edit_record is not None else None
        )

        if edit_mode:
            self.setWindowTitle(self.tr("Edit Harvest Entry"))
        elif target_name:
            self.setWindowTitle(self.tr("Harvest Log — {name}").format(name=target_name))
        else:
            self.setWindowTitle(self.tr("Harvest Log"))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui(existing_history)
        if edit_record is not None:
            self._populate(edit_record)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self, existing_history: HarvestHistory | None) -> None:
        layout = QVBoxLayout(self)

        if self._edit_mode:
            layout.addWidget(self._build_entry_tab())
        else:
            self._tabs = QTabWidget()
            self._tabs.addTab(self._build_entry_tab(), self.tr("Entry"))
            self._tabs.addTab(
                self._build_history_tab(existing_history), self.tr("History")
            )
            layout.addWidget(self._tabs)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _build_entry_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()

        # Date
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        today = _date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        form.addRow(self.tr("Date"), self._date_edit)

        # Quantity
        self._quantity_spin = QDoubleSpinBox()
        self._quantity_spin.setRange(0.0, 1_000_000.0)
        self._quantity_spin.setDecimals(2)
        self._quantity_spin.setValue(0.0)
        form.addRow(self.tr("Quantity"), self._quantity_spin)

        # Unit (editable — gardeners may use their own unit names)
        self._unit_combo = QComboBox()
        self._unit_combo.setEditable(True)
        self._unit_combo.addItems(list(_UNIT_CHOICES))
        self._unit_combo.setCurrentText("kg")
        form.addRow(self.tr("Unit"), self._unit_combo)

        # Quality
        self._quality_edit = QLineEdit()
        self._quality_edit.setPlaceholderText(self.tr("e.g. excellent, sweet"))
        form.addRow(self.tr("Quality"), self._quality_edit)

        layout.addLayout(form)

        # Notes
        layout.addWidget(QLabel(self.tr("Notes")))
        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(60)
        layout.addWidget(self._notes_edit)

        # Photo attachment row
        photo_row = QHBoxLayout()
        self._photo_label = QLabel()
        self._photo_label.setFixedSize(64, 64)
        self._photo_label.setStyleSheet("border: 1px solid #888;")
        self._photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_label.setText(self.tr("(no photo)"))
        photo_row.addWidget(self._photo_label)

        photo_btn_col = QVBoxLayout()
        self._attach_photo_btn = QPushButton(self.tr("Attach Photo…"))
        self._attach_photo_btn.clicked.connect(self._on_attach_photo)
        photo_btn_col.addWidget(self._attach_photo_btn)

        self._remove_photo_btn = QPushButton(self.tr("Remove Photo"))
        self._remove_photo_btn.clicked.connect(self._on_remove_photo)
        self._remove_photo_btn.setEnabled(False)
        photo_btn_col.addWidget(self._remove_photo_btn)

        photo_row.addLayout(photo_btn_col)
        photo_row.addStretch(1)
        layout.addLayout(photo_row)

        if self._project_directory() is None:
            self._attach_photo_btn.setEnabled(False)
            self._attach_photo_btn.setToolTip(
                self.tr("Save project first to attach photos")
            )

        layout.addStretch(1)
        return page

    def _build_history_tab(self, history: HarvestHistory | None) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        layout = QVBoxLayout(page)

        layout.addWidget(QLabel(self.tr("Past entries")))

        self._history_records_container = QWidget()
        self._history_records_layout = QVBoxLayout(self._history_records_container)
        self._history_records_layout.setContentsMargins(0, 0, 0, 0)
        self._history_records_layout.setSpacing(2)
        layout.addWidget(self._history_records_container)

        layout.addStretch(1)
        scroll.setWidget(page)

        self._refresh_history_view(history)
        return scroll

    def _refresh_history_view(self, history: HarvestHistory | None) -> None:
        while self._history_records_layout.count():
            item = self._history_records_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        records = list(history.records) if history is not None else []
        records.sort(key=lambda r: r.date, reverse=True)

        if not records:
            self._history_records_layout.addWidget(QLabel(self.tr("No past entries")))
        else:
            current_year: str | None = None
            for rec in records:
                year = rec.date[:4] if rec.date else "?"
                if year != current_year:
                    current_year = year
                    self._history_records_layout.addWidget(
                        self._build_year_header(year, records)
                    )
                self._history_records_layout.addWidget(self._build_history_row(rec))

        self._existing_history = history

    def _build_year_header(self, year: str, records: list[HarvestRecord]) -> QWidget:
        # Per-unit subtotal for this year.
        totals: dict[str, float] = {}
        for r in records:
            if (r.date[:4] if r.date else "?") == year:
                totals[r.unit] = totals.get(r.unit, 0.0) + r.quantity
        parts = ", ".join(f"{qty:g} {unit}" for unit, qty in sorted(totals.items()))
        label = QLabel(self.tr("{year} — {totals}").format(year=year, totals=parts))
        label.setStyleSheet("font-weight: bold; margin-top: 4px;")
        return label

    def _build_history_row(self, rec: HarvestRecord) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(12, 0, 0, 0)
        h.setSpacing(4)

        h.addWidget(QLabel(self._format_history_row(rec)), 1)

        if self._project_manager is not None and self._command_manager is not None:
            edit_btn = QPushButton(self.tr("Edit"))
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, r=rec: self._on_edit_record(r))
            h.addWidget(edit_btn)

            del_btn = QPushButton(self.tr("Delete"))
            del_btn.setFixedWidth(60)
            del_btn.clicked.connect(lambda _, r=rec: self._on_delete_record(r))
            h.addWidget(del_btn)

        return row

    def _format_history_row(self, rec: HarvestRecord) -> str:
        text = self.tr("{date} — {qty} {unit}").format(
            date=rec.date or "?", qty=f"{rec.quantity:g}", unit=rec.unit
        )
        if rec.quality:
            text = text + self.tr(" ({quality})").format(quality=rec.quality)
        return text

    def _on_edit_record(self, rec: HarvestRecord) -> None:
        sub = HarvestLogDialog(
            parent=self,
            target_id=self._target_id,
            target_name=self._target_name,
            edit_mode=True,
            edit_record=rec,
            project_manager=self._project_manager,
        )
        if sub.exec() != QDialog.DialogCode.Accepted:
            return
        from open_garden_planner.core import EditHarvestRecordCommand  # noqa: PLC0415

        new_record = sub.result_record()
        cmd = EditHarvestRecordCommand(
            self._project_manager, self._target_id, new_record
        )
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _on_delete_record(self, rec: HarvestRecord) -> None:
        prompt = self.tr("Delete the harvest entry from {date}?").format(
            date=rec.date or "?"
        )
        reply = QMessageBox.question(
            self,
            self.tr("Delete harvest entry"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from open_garden_planner.core import DeleteHarvestRecordCommand  # noqa: PLC0415

        cmd = DeleteHarvestRecordCommand(
            self._project_manager, self._target_id, rec.id
        )
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _reload_history_after_change(self) -> None:
        if self._project_manager is None:
            return
        history = self._project_manager.get_harvest_history(self._target_id)
        self._refresh_history_view(history)

    # ── Photo handling ───────────────────────────────────────────────────────

    def _project_directory(self) -> Path | None:
        if self._project_manager is None:
            return None
        cur = getattr(self._project_manager, "current_file", None)
        if cur is None:
            return None
        try:
            return Path(cur).resolve().parent
        except Exception:
            return None

    def _on_attach_photo(self) -> None:
        project_dir = self._project_directory()
        if project_dir is None:
            return
        path_str, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Select photo"),
            str(default_dialog_dir()),
            self.tr("Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"),
        )
        if not path_str:
            return
        src = Path(path_str)
        photos_dir = project_dir / "harvest_photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{uuid.uuid4().hex}_{src.name}"
        dest = photos_dir / dest_name
        try:
            shutil.copy2(src, dest)
        except OSError as exc:
            QMessageBox.warning(
                self,
                self.tr("Photo attach failed"),
                self.tr("Could not copy photo: {err}").format(err=str(exc)),
            )
            return
        rel = dest.relative_to(project_dir).as_posix()
        self._photo_path = rel
        self._update_photo_thumbnail()

    def _on_remove_photo(self) -> None:
        self._photo_path = None
        self._update_photo_thumbnail()

    def _update_photo_thumbnail(self) -> None:
        self._photo_label.mousePressEvent = lambda _e: None
        self._photo_label.setCursor(Qt.CursorShape.ArrowCursor)
        self._photo_label.setToolTip("")

        if self._photo_path is None:
            self._photo_label.setPixmap(QPixmap())
            self._photo_label.setText(self.tr("(no photo)"))
            self._remove_photo_btn.setEnabled(False)
            return
        project_dir = self._project_directory()
        if project_dir is None:
            self._photo_label.setText(self.tr("(unsaved)"))
            self._remove_photo_btn.setEnabled(True)
            return
        full = project_dir / self._photo_path
        pix = QPixmap(str(full))
        if pix.isNull():
            self._photo_label.setPixmap(QPixmap())
            self._photo_label.setText(self.tr("(missing)"))
        else:
            self._photo_label.setPixmap(
                pix.scaled(
                    64, 64,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._photo_label.setText("")
            self._photo_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._photo_label.setToolTip(self.tr("Click to open in image viewer"))
            _jail = (project_dir / "harvest_photos").resolve()

            def _open_photo(_e, _path=full, _jail=_jail):
                if _e.button() != Qt.MouseButton.LeftButton:
                    return
                try:
                    _path.resolve().relative_to(_jail)
                except ValueError:
                    return
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(_path)))

            self._photo_label.mousePressEvent = _open_photo
        self._remove_photo_btn.setEnabled(True)

    # ── Behaviour ────────────────────────────────────────────────────────────

    def _populate(self, record: HarvestRecord) -> None:
        if record.date:
            try:
                yyyy, mm, dd = (int(p) for p in record.date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        self._quantity_spin.setValue(record.quantity)
        self._unit_combo.setCurrentText(record.unit)
        self._quality_edit.setText(record.quality)
        if record.notes:
            self._notes_edit.setPlainText(record.notes)
        self._photo_path = record.photo_path
        self._update_photo_thumbnail()

    def _on_accept(self) -> None:
        has_qty = self._quantity_spin.value() > 0
        on_entry_tab = not hasattr(self, "_tabs") or self._tabs.currentIndex() == 0
        if on_entry_tab and not has_qty:
            reply = QMessageBox.question(
                self,
                self.tr("Zero quantity"),
                self.tr("Save entry with zero quantity?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            self._force_new_entry = True
        else:
            self._force_new_entry = False
        self.accept()

    @property
    def has_new_entry(self) -> bool:
        """True when a new record should be added on accept."""
        if self._edit_mode:
            return False
        if getattr(self, "_force_new_entry", False):
            return True
        return self._quantity_spin.value() > 0

    # ── Public API ───────────────────────────────────────────────────────────

    def result_record(self) -> HarvestRecord:
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        kwargs: dict[str, Any] = {
            "date": date_iso,
            "quantity": float(self._quantity_spin.value()),
            "unit": self._unit_combo.currentText().strip() or "kg",
            "quality": self._quality_edit.text().strip(),
            "notes": self._notes_edit.toPlainText().strip(),
            "photo_path": self._photo_path,
        }
        if self._edit_record_id is not None:
            kwargs["id"] = self._edit_record_id
        if self._edit_journal_note_id is not None:
            kwargs["journal_note_id"] = self._edit_journal_note_id
        return HarvestRecord(**kwargs)

    # ── Test helpers ─────────────────────────────────────────────────────────

    def set_values(
        self,
        *,
        date: str | None = None,
        quantity: float | None = None,
        unit: str | None = None,
        quality: str | None = None,
        notes: str | None = None,
    ) -> None:
        if date is not None:
            try:
                yyyy, mm, dd = (int(p) for p in date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        if quantity is not None:
            self._quantity_spin.setValue(quantity)
        if unit is not None:
            self._unit_combo.setCurrentText(unit)
        if quality is not None:
            self._quality_edit.setText(quality)
        if notes is not None:
            self._notes_edit.setPlainText(notes)


__all__ = ["HarvestLogDialog"]
