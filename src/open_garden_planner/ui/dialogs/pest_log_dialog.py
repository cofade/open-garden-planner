"""Pest and disease log dialog (US-12.7).

Right-click a bed or plant → "Log Pest/Disease…" to open this dialog. On
accept, ``result_record()`` returns a populated ``PestLogRecord`` ready to
be wrapped in an ``AddPestLogCommand``.

Two tabs (collapsed to one in edit mode):
  * Entry   — date, type (pest/disease), name, severity, treatment,
              notes, photo attachment, resolved checkbox.
  * History — list of past entries for this target with Edit/Delete
              buttons. Hidden in edit mode.
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
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.pest_log import PestLogHistory, PestLogRecord


class PestLogDialog(QDialog):
    """Modal dialog for entering a single pest/disease record."""

    def __init__(
        self,
        parent: QWidget | None = None,
        target_id: str = "",
        target_name: str = "",
        existing_history: PestLogHistory | None = None,
        edit_mode: bool = False,
        edit_record: PestLogRecord | None = None,
        project_manager: Any | None = None,
        command_manager: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._target_id = target_id
        self._target_name = target_name
        self._edit_mode = edit_mode
        self._edit_record_id = edit_record.id if (edit_mode and edit_record) else None
        self._project_manager = project_manager
        self._command_manager = command_manager
        self._existing_history = existing_history
        # Stored as project-relative path (POSIX-style separators) once attached.
        self._photo_path: str | None = (
            edit_record.photo_path if edit_record is not None else None
        )

        if edit_mode:
            self.setWindowTitle(self.tr("Edit Pest/Disease Log"))
        elif target_name:
            self.setWindowTitle(
                self.tr("Pest/Disease Log — {name}").format(name=target_name)
            )
        else:
            self.setWindowTitle(self.tr("Pest/Disease Log"))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._setup_ui(existing_history)
        if edit_record is not None:
            self._populate(edit_record)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self, existing_history: PestLogHistory | None) -> None:
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

        # Type (pest / disease)
        self._type_combo = QComboBox()
        self._type_combo.addItem(self.tr("Pest"), userData="pest")
        self._type_combo.addItem(self.tr("Disease"), userData="disease")
        form.addRow(self.tr("Type"), self._type_combo)

        # Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(self.tr("e.g. Aphids, Powdery mildew"))
        form.addRow(self.tr("Name"), self._name_edit)

        # Severity
        self._severity_combo = QComboBox()
        self._severity_combo.addItem(self.tr("Low"), userData="low")
        self._severity_combo.addItem(self.tr("Medium"), userData="medium")
        self._severity_combo.addItem(self.tr("High"), userData="high")
        form.addRow(self.tr("Severity"), self._severity_combo)

        # Treatment
        self._treatment_edit = QLineEdit()
        self._treatment_edit.setPlaceholderText(
            self.tr("e.g. Neem oil spray, weekly")
        )
        form.addRow(self.tr("Treatment"), self._treatment_edit)

        layout.addLayout(form)

        # Notes — multi-line so users can describe affected plants and other context.
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

        # Disable attach when project unsaved (no place to copy the photo to).
        if self._project_directory() is None:
            self._attach_photo_btn.setEnabled(False)
            self._attach_photo_btn.setToolTip(
                self.tr("Save project first to attach photos")
            )

        # Resolved
        self._resolved_check = QCheckBox(self.tr("Resolved"))
        layout.addWidget(self._resolved_check)

        layout.addStretch(1)
        return page

    def _build_history_tab(self, history: PestLogHistory | None) -> QWidget:
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

    def _refresh_history_view(self, history: PestLogHistory | None) -> None:
        while self._history_records_layout.count():
            item = self._history_records_layout.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

        records = list(history.records) if history is not None else []
        records.sort(key=lambda r: r.date, reverse=True)

        if not records:
            self._history_records_layout.addWidget(
                QLabel(self.tr("No past entries"))
            )
        else:
            for rec in records:
                self._history_records_layout.addWidget(self._build_history_row(rec))

        self._existing_history = history

    def _build_history_row(self, rec: PestLogRecord) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        h.addWidget(QLabel(self._format_history_row(rec)), 1)

        if (
            self._project_manager is not None
            and self._command_manager is not None
        ):
            edit_btn = QPushButton(self.tr("Edit"))
            edit_btn.setFixedWidth(60)
            edit_btn.clicked.connect(lambda _, r=rec: self._on_edit_record(r))
            h.addWidget(edit_btn)

            del_btn = QPushButton(self.tr("Delete"))
            del_btn.setFixedWidth(60)
            del_btn.clicked.connect(lambda _, r=rec: self._on_delete_record(r))
            h.addWidget(del_btn)

        return row

    def _format_history_row(self, rec: PestLogRecord) -> str:
        type_label = (
            self.tr("Disease") if rec.entry_type == "disease" else self.tr("Pest")
        )
        sev_label = {
            "low": self.tr("Low"),
            "medium": self.tr("Medium"),
            "high": self.tr("High"),
        }.get(rec.severity, rec.severity)
        text = self.tr("{date} — {type} — {name} ({severity})").format(
            date=rec.date or "?",
            type=type_label,
            name=rec.name or self.tr("(unnamed)"),
            severity=sev_label,
        )
        if rec.resolved:
            text = text + self.tr(" [Resolved]")
        return text

    def _on_edit_record(self, rec: PestLogRecord) -> None:
        sub = PestLogDialog(
            parent=self,
            target_id=self._target_id,
            target_name=self._target_name,
            edit_mode=True,
            edit_record=rec,
            project_manager=self._project_manager,
        )
        if sub.exec() != QDialog.DialogCode.Accepted:
            return
        from open_garden_planner.core import EditPestLogCommand  # noqa: PLC0415

        new_record = sub.result_record()
        cmd = EditPestLogCommand(self._project_manager, self._target_id, new_record)
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _on_delete_record(self, rec: PestLogRecord) -> None:
        prompt = self.tr("Delete the entry from {date}?").format(
            date=rec.date or "?"
        )
        reply = QMessageBox.question(
            self,
            self.tr("Delete pest/disease entry"),
            prompt,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from open_garden_planner.core import DeletePestLogCommand  # noqa: PLC0415

        cmd = DeletePestLogCommand(
            self._project_manager, self._target_id, rec.id
        )
        self._command_manager.execute(cmd)
        self._reload_history_after_change()

    def _reload_history_after_change(self) -> None:
        if self._project_manager is None:
            return
        history = self._project_manager.get_pest_log_history(self._target_id)
        self._refresh_history_view(history)
        # Best-effort overview-panel refresh on the parent application.
        parent = self.parent()
        refresh = getattr(parent, "_refresh_pest_overview", None)
        if callable(refresh):
            refresh()

    # ── Photo handling ───────────────────────────────────────────────────────

    def _project_directory(self) -> Path | None:
        """Return the project's directory if saved, else None."""
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
            "",
            self.tr("Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp)"),
        )
        if not path_str:
            return
        src = Path(path_str)
        photos_dir = project_dir / "pest_photos"
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
        # Always store with POSIX separators so the path round-trips across
        # platforms (the .ogp file may be opened on Windows or Linux).
        rel = dest.relative_to(project_dir).as_posix()
        self._photo_path = rel
        self._update_photo_thumbnail()

    def _on_remove_photo(self) -> None:
        # We do not delete the file on disk — the user may have linked it from
        # an older record. Just clear the reference on this record.
        self._photo_path = None
        self._update_photo_thumbnail()

    def _update_photo_thumbnail(self) -> None:
        self._photo_label.mousePressEvent = lambda _e: None  # reset
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
            _jail = (project_dir / "pest_photos").resolve()
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

    def _populate(self, record: PestLogRecord) -> None:
        if record.date:
            try:
                yyyy, mm, dd = (int(p) for p in record.date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        for idx in range(self._type_combo.count()):
            if self._type_combo.itemData(idx) == record.entry_type:
                self._type_combo.setCurrentIndex(idx)
                break
        self._name_edit.setText(record.name)
        for idx in range(self._severity_combo.count()):
            if self._severity_combo.itemData(idx) == record.severity:
                self._severity_combo.setCurrentIndex(idx)
                break
        self._treatment_edit.setText(record.treatment)
        if record.notes:
            self._notes_edit.setPlainText(record.notes)
        self._photo_path = record.photo_path
        self._update_photo_thumbnail()
        self._resolved_check.setChecked(record.resolved)

    def _on_accept(self) -> None:
        name_filled = bool(self._name_edit.text().strip())
        on_entry_tab = not hasattr(self, "_tabs") or self._tabs.currentIndex() == 0
        # Empty-name warning only when Entry tab is active AND name is blank.
        if on_entry_tab and not name_filled:
            reply = QMessageBox.question(
                self,
                self.tr("Empty name"),
                self.tr("Save entry with empty name?"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            # User confirmed: force-add even though name is empty.
            self._force_new_entry = True
        else:
            self._force_new_entry = False
        self.accept()

    @property
    def has_new_entry(self) -> bool:
        """True when a new record should be added on accept.

        Checks name content rather than active tab so that filling the Entry
        tab, switching to History, then clicking OK still persists the entry.
        """
        if self._edit_mode:
            return False
        if getattr(self, "_force_new_entry", False):
            return True
        return bool(self._name_edit.text().strip())

    # ── Public API ───────────────────────────────────────────────────────────

    def result_record(self) -> PestLogRecord:
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        kwargs: dict[str, Any] = {
            "date": date_iso,
            "entry_type": self._type_combo.currentData(),
            "name": self._name_edit.text().strip(),
            "severity": self._severity_combo.currentData(),
            "treatment": self._treatment_edit.text().strip(),
            "notes": self._notes_edit.toPlainText().strip(),
            "photo_path": self._photo_path,
            "resolved": self._resolved_check.isChecked(),
        }
        if self._edit_record_id is not None:
            kwargs["id"] = self._edit_record_id
        return PestLogRecord(**kwargs)

    # ── Test helpers ─────────────────────────────────────────────────────────

    def set_values(
        self,
        *,
        date: str | None = None,
        entry_type: str | None = None,
        name: str | None = None,
        severity: str | None = None,
        treatment: str | None = None,
        notes: str | None = None,
        resolved: bool | None = None,
    ) -> None:
        if date is not None:
            try:
                yyyy, mm, dd = (int(p) for p in date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        if entry_type is not None:
            for idx in range(self._type_combo.count()):
                if self._type_combo.itemData(idx) == entry_type:
                    self._type_combo.setCurrentIndex(idx)
                    break
        if name is not None:
            self._name_edit.setText(name)
        if severity is not None:
            for idx in range(self._severity_combo.count()):
                if self._severity_combo.itemData(idx) == severity:
                    self._severity_combo.setCurrentIndex(idx)
                    break
        if treatment is not None:
            self._treatment_edit.setText(treatment)
        if notes is not None:
            self._notes_edit.setPlainText(notes)
        if resolved is not None:
            self._resolved_check.setChecked(resolved)


__all__ = ["PestLogDialog"]
