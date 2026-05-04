"""Pest & disease entry dialog (US-12.7).

Right-click a bed or plant → "Log pest/disease…" to open this dialog. On
accept, ``result_record()`` returns a populated ``PestDiseaseRecord`` ready
to be wrapped in ``AddPestDiseaseCommand`` or ``EditPestDiseaseCommand``.

Two tabs:
  * Entry  — date, kind, name, severity, treatment, photo, notes, resolved
  * History — past records for this target with Edit / Delete buttons

In ``edit_mode`` the History tab is hidden and the dialog preserves the
record's ``id`` on save.
"""
from __future__ import annotations

from datetime import date as _date
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.pest_disease import (
    KIND_VALUES,
    SEVERITY_VALUES,
    PestDiseaseLog,
    PestDiseaseRecord,
    PestKind,
    Severity,
)
from open_garden_planner.services.photo_attachment import (
    PhotoAttachmentError,
    decode_photo_from_base64,
    encode_photo_to_base64,
)

_KIND_LABEL_KEYS: dict[PestKind, str] = {"pest": "Pest", "disease": "Disease"}
_SEVERITY_LABEL_KEYS: dict[Severity, str] = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
}
_THUMB_PX = 160


class PestDiseaseDialog(QDialog):
    """Modal dialog for entering a single pest/disease log record."""

    record_edit_requested = pyqtSignal(str)  # record_id — handled by parent
    record_delete_requested = pyqtSignal(str)  # record_id — handled by parent

    def __init__(
        self,
        parent: QWidget | None = None,
        target_id: str = "",
        target_name: str = "",
        existing_record: PestDiseaseRecord | None = None,
        existing_log: PestDiseaseLog | None = None,
        edit_mode: bool = False,
        project_manager: Any | None = None,
        command_manager: Any | None = None,
    ) -> None:
        """Initialise the dialog.

        Args:
            parent: Parent widget.
            target_id: Bed or plant UUID (informational; routing is the
                caller's job).
            target_name: Human-readable name of the bed/plant for the title.
            existing_record: Pre-populates the form. In ``edit_mode`` its
                ``id`` is preserved by ``result_record``.
            existing_log: Full log used to render the History tab. ``None``
                or empty shows the placeholder.
            edit_mode: When True, hides History tab and preserves
                ``existing_record.id`` on save.
            project_manager: Used only by the History tab for the Edit/
                Delete buttons (signals are emitted; the parent handles the
                command wrapping).
            command_manager: Same.
        """
        super().__init__(parent)
        self._target_id = target_id
        self._target_name = target_name
        self._edit_mode = edit_mode
        self._existing_record = existing_record
        self._existing_log = existing_log
        self._project_manager = project_manager
        self._command_manager = command_manager
        self._photo_b64: str | None = (
            existing_record.photo_base64 if existing_record else None
        )

        title = (
            self.tr("Edit Pest/Disease Record")
            if edit_mode
            else self.tr("Log Pest / Disease")
        )
        if target_name:
            title = f"{title} — {target_name}"
        self.setWindowTitle(title)
        self.setMinimumWidth(480)

        self._tabs = QTabWidget(self)
        self._build_entry_tab()
        if not edit_mode:
            self._build_history_tab()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._tabs)
        layout.addWidget(button_box)

    # ── Entry tab ─────────────────────────────────────────────────────────────

    def _build_entry_tab(self) -> None:
        page = QWidget()
        form = QFormLayout(page)

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        if self._existing_record and self._existing_record.date:
            try:
                y, m, d = (int(p) for p in self._existing_record.date.split("-"))
                self._date_edit.setDate(QDate(y, m, d))
            except ValueError:
                self._date_edit.setDate(QDate.currentDate())
        else:
            self._date_edit.setDate(QDate.currentDate())
        form.addRow(self.tr("Date"), self._date_edit)

        self._kind_combo = QComboBox()
        for kind in KIND_VALUES:
            self._kind_combo.addItem(self.tr(_KIND_LABEL_KEYS[kind]), kind)
        if self._existing_record:
            idx = list(KIND_VALUES).index(self._existing_record.kind)
            self._kind_combo.setCurrentIndex(idx)
        form.addRow(self.tr("Type"), self._kind_combo)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self.tr("e.g. Aphid, Powdery mildew"))
        if self._existing_record:
            self._name_edit.setText(self._existing_record.name)
        form.addRow(self.tr("Name"), self._name_edit)

        self._severity_combo = QComboBox()
        for sev in SEVERITY_VALUES:
            self._severity_combo.addItem(self.tr(_SEVERITY_LABEL_KEYS[sev]), sev)
        if self._existing_record:
            idx = list(SEVERITY_VALUES).index(self._existing_record.severity)
            self._severity_combo.setCurrentIndex(idx)
        form.addRow(self.tr("Severity"), self._severity_combo)

        self._treatment_edit = QPlainTextEdit()
        self._treatment_edit.setPlaceholderText(
            self.tr("e.g. Neem oil weekly; remove affected leaves")
        )
        self._treatment_edit.setFixedHeight(72)
        if self._existing_record:
            self._treatment_edit.setPlainText(self._existing_record.treatment)
        form.addRow(self.tr("Treatment"), self._treatment_edit)

        # Photo row
        photo_row = QWidget()
        photo_layout = QHBoxLayout(photo_row)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        self._photo_label = QLabel()
        self._photo_label.setFixedSize(_THUMB_PX, _THUMB_PX)
        self._photo_label.setStyleSheet(
            "QLabel { border: 1px dashed #888; background: #f6f6f6; }"
        )
        self._photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_label.setText(self.tr("No photo"))
        self._add_photo_btn = QPushButton(self.tr("Add photo…"))
        self._add_photo_btn.clicked.connect(self._on_add_photo)
        self._remove_photo_btn = QPushButton(self.tr("Remove"))
        self._remove_photo_btn.clicked.connect(self._on_remove_photo)
        photo_btns = QVBoxLayout()
        photo_btns.addWidget(self._add_photo_btn)
        photo_btns.addWidget(self._remove_photo_btn)
        photo_btns.addStretch(1)
        photo_layout.addWidget(self._photo_label)
        photo_layout.addLayout(photo_btns)
        photo_layout.addStretch(1)
        form.addRow(self.tr("Photo"), photo_row)
        self._refresh_photo_preview()

        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setFixedHeight(60)
        if self._existing_record:
            self._notes_edit.setPlainText(self._existing_record.notes)
        form.addRow(self.tr("Notes"), self._notes_edit)

        # Resolved (edit-mode only)
        self._resolved_check: QCheckBox | None = None
        self._resolved_date: QDateEdit | None = None
        if self._edit_mode:
            self._resolved_check = QCheckBox(self.tr("Resolved"))
            self._resolved_date = QDateEdit()
            self._resolved_date.setCalendarPopup(True)
            self._resolved_date.setDisplayFormat("yyyy-MM-dd")
            self._resolved_date.setDate(QDate.currentDate())
            self._resolved_date.setEnabled(False)
            if self._existing_record and self._existing_record.resolved_date:
                try:
                    y, m, d = (
                        int(p)
                        for p in self._existing_record.resolved_date.split("-")
                    )
                    self._resolved_date.setDate(QDate(y, m, d))
                except ValueError:
                    pass
                self._resolved_check.setChecked(True)
                self._resolved_date.setEnabled(True)
            self._resolved_check.toggled.connect(self._resolved_date.setEnabled)
            resolved_row = QWidget()
            rl = QHBoxLayout(resolved_row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.addWidget(self._resolved_check)
            rl.addWidget(self._resolved_date)
            rl.addStretch(1)
            form.addRow("", resolved_row)

        self._tabs.addTab(page, self.tr("Entry"))

    # ── History tab ───────────────────────────────────────────────────────────

    def _build_history_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        self._history_list = QListWidget()
        self._history_list.setAlternatingRowColors(True)
        layout.addWidget(self._history_list)
        self._populate_history()

        footer = QWidget()
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(0, 6, 0, 0)
        self._edit_history_btn = QPushButton(self.tr("Edit selected…"))
        self._delete_history_btn = QPushButton(self.tr("Delete selected"))
        self._edit_history_btn.clicked.connect(self._on_edit_selected)
        self._delete_history_btn.clicked.connect(self._on_delete_selected)
        fl.addWidget(self._edit_history_btn)
        fl.addWidget(self._delete_history_btn)
        fl.addStretch(1)
        layout.addWidget(footer)

        self._tabs.addTab(page, self.tr("History"))

    def _populate_history(self) -> None:
        self._history_list.clear()
        records: list[PestDiseaseRecord] = []
        if self._existing_log is not None:
            records = sorted(
                self._existing_log.records, key=lambda r: r.date, reverse=True
            )
        if not records:
            placeholder = QListWidgetItem(self.tr("No records yet."))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._history_list.addItem(placeholder)
            return
        for r in records:
            kind_label = self.tr(_KIND_LABEL_KEYS[r.kind])
            sev_label = self.tr(_SEVERITY_LABEL_KEYS[r.severity])
            status = (
                self.tr("Resolved {date}").format(date=r.resolved_date)
                if r.resolved_date
                else self.tr("Active")
            )
            text = f"{r.date} — {kind_label}: {r.name} ({sev_label}) — {status}"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, r.id)
            self._history_list.addItem(item)

    def _on_edit_selected(self) -> None:
        item = self._history_list.currentItem()
        if not item:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        if record_id:
            self.record_edit_requested.emit(record_id)
            # Reject so the parent's _open_pest_disease_dialog does not also
            # save the (untouched) Entry-tab fields. The Edit signal already
            # routed to the parent which is opening the edit dialog itself.
            self.reject()

    def _on_delete_selected(self) -> None:
        item = self._history_list.currentItem()
        if not item:
            return
        record_id = item.data(Qt.ItemDataRole.UserRole)
        if not record_id:
            return
        if (
            QMessageBox.question(
                self,
                self.tr("Delete record"),
                self.tr("Delete this record? This can be undone."),
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.record_delete_requested.emit(record_id)
            self.reject()

    # ── Photo handlers ────────────────────────────────────────────────────────

    def _on_add_photo(self) -> None:
        path_str, _filter = QFileDialog.getOpenFileName(
            self,
            self.tr("Select photo"),
            "",
            self.tr("Images (*.png *.jpg *.jpeg *.bmp *.gif);;All files (*)"),
        )
        if not path_str:
            return
        try:
            self._photo_b64 = encode_photo_to_base64(Path(path_str))
        except PhotoAttachmentError as exc:
            QMessageBox.warning(
                self, self.tr("Cannot load photo"), str(exc)
            )
            return
        self._refresh_photo_preview()

    def _on_remove_photo(self) -> None:
        self._photo_b64 = None
        self._refresh_photo_preview()

    def _refresh_photo_preview(self) -> None:
        if self._photo_b64:
            pixmap = decode_photo_from_base64(self._photo_b64)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    _THUMB_PX,
                    _THUMB_PX,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._photo_label.setPixmap(scaled)
                self._photo_label.setText("")
                self._remove_photo_btn.setEnabled(True)
                return
        self._photo_label.clear()
        self._photo_label.setText(self.tr("No photo"))
        self._remove_photo_btn.setEnabled(False)

    # ── Result ────────────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                self.tr("Name required"),
                self.tr("Please enter the pest or disease name."),
            )
            return
        self.accept()

    def result_record(self) -> PestDiseaseRecord:
        """Return the populated record. Preserves id in edit_mode."""
        qd = self._date_edit.date()
        date_str = _date(qd.year(), qd.month(), qd.day()).isoformat()

        kind = self._kind_combo.currentData() or "pest"
        severity = self._severity_combo.currentData() or "low"

        resolved_date: str | None = None
        if self._edit_mode and self._resolved_check and self._resolved_check.isChecked():
            rd = self._resolved_date.date() if self._resolved_date else QDate.currentDate()
            resolved_date = _date(rd.year(), rd.month(), rd.day()).isoformat()
        elif self._existing_record and not self._edit_mode:
            resolved_date = self._existing_record.resolved_date

        record_id = (
            self._existing_record.id
            if self._edit_mode and self._existing_record
            else ""
        )
        kwargs: dict[str, Any] = {
            "date": date_str,
            "kind": kind,
            "name": self._name_edit.text().strip(),
            "severity": severity,
            "treatment": self._treatment_edit.toPlainText().strip(),
            "resolved_date": resolved_date,
            "photo_base64": self._photo_b64,
            "notes": self._notes_edit.toPlainText().strip(),
        }
        if record_id:
            kwargs["id"] = record_id
        return PestDiseaseRecord(**kwargs)
