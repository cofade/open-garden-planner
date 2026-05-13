"""Garden journal note dialog (US-12.9).

Opens for a single :class:`JournalNote` — both when placing a new pin via
:class:`JournalPinTool` and when double-clicking an existing pin. On
accept, ``result_note()`` returns the populated note ready to be wrapped
in either :class:`AddJournalNoteCommand` or
:class:`EditJournalNoteCommand`.
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
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.models.journal_note import JournalNote


class JournalNoteDialog(QDialog):
    """Modal dialog for adding or editing a single garden-journal note."""

    def __init__(
        self,
        parent: QWidget | None = None,
        note: JournalNote | None = None,
        project_manager: Any | None = None,
        edit_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._project_manager = project_manager
        self._edit_mode = edit_mode
        self._note_id: str = note.id if note is not None else str(uuid.uuid4())
        self._scene_x: float = note.scene_x if note is not None else 0.0
        self._scene_y: float = note.scene_y if note is not None else 0.0
        self._photo_path: str | None = note.photo_path if note is not None else None

        self.setWindowTitle(
            self.tr("Edit Journal Note") if edit_mode else self.tr("New Journal Note")
        )
        self.setModal(True)
        self.setMinimumWidth(420)

        self._setup_ui()
        # Always start at today; _populate overrides this only if the note
        # actually carries a date string (a freshly built JournalNote has
        # ``date=""`` and would otherwise leave the QDateEdit at its Qt
        # default of 2000-01-01).
        today = _date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        if note is not None:
            self._populate(note)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(self.tr("Date"), self._date_edit)
        layout.addLayout(form)

        layout.addWidget(QLabel(self.tr("Note")))
        self._text_edit = QPlainTextEdit()
        self._text_edit.setPlaceholderText(
            self.tr("What happened here? Observations, weather, plans…")
        )
        self._text_edit.setMinimumHeight(140)
        layout.addWidget(self._text_edit)

        # Photo attachment row.
        photo_row = QHBoxLayout()
        self._photo_label = QLabel()
        self._photo_label.setFixedSize(80, 80)
        self._photo_label.setStyleSheet("border: 1px solid #888;")
        self._photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_label.setText(self.tr("(no photo)"))
        photo_row.addWidget(self._photo_label)

        btn_col = QVBoxLayout()
        self._attach_photo_btn = QPushButton(self.tr("Attach Photo…"))
        self._attach_photo_btn.clicked.connect(self._on_attach_photo)
        btn_col.addWidget(self._attach_photo_btn)

        self._remove_photo_btn = QPushButton(self.tr("Remove Photo"))
        self._remove_photo_btn.clicked.connect(self._on_remove_photo)
        self._remove_photo_btn.setEnabled(False)
        btn_col.addWidget(self._remove_photo_btn)

        photo_row.addLayout(btn_col)
        photo_row.addStretch(1)
        layout.addLayout(photo_row)

        # Disable attach until the project is saved (so we have a directory to
        # copy the photo into).
        if self._project_directory() is None:
            self._attach_photo_btn.setEnabled(False)
            self._attach_photo_btn.setToolTip(
                self.tr("Save project first to attach photos")
            )

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ── Population / behaviour ───────────────────────────────────────────────

    def _populate(self, note: JournalNote) -> None:
        if note.date:
            try:
                yyyy, mm, dd = (int(p) for p in note.date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        self._text_edit.setPlainText(note.text)
        self._photo_path = note.photo_path
        self._update_photo_thumbnail()

    # ── Photo handling ───────────────────────────────────────────────────────

    def _project_directory(self) -> Path | None:
        """Return the project's directory if saved, else ``None``."""
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
        photos_dir = project_dir / "journal_photos"
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
        # Mirror the pest-log dialog: drop the reference only, leave the file
        # on disk in case another note links the same image.
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
                    80, 80,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self._photo_label.setText("")
            self._photo_label.setCursor(Qt.CursorShape.PointingHandCursor)
            self._photo_label.setToolTip(
                self.tr("Click to open in image viewer")
            )
            _jail = (project_dir / "journal_photos").resolve()

            def _open_photo(_e: Any, _path: Path = full, _jail: Path = _jail) -> None:
                if _e.button() != Qt.MouseButton.LeftButton:
                    return
                try:
                    _path.resolve().relative_to(_jail)
                except ValueError:
                    return
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(_path)))

            self._photo_label.mousePressEvent = _open_photo
        self._remove_photo_btn.setEnabled(True)

    # ── Public API ───────────────────────────────────────────────────────────

    def result_note(self) -> JournalNote:
        """Return a populated ``JournalNote`` matching the dialog's state."""
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        return JournalNote(
            id=self._note_id,
            date=date_iso,
            text=self._text_edit.toPlainText().rstrip(),
            photo_path=self._photo_path,
            scene_x=self._scene_x,
            scene_y=self._scene_y,
        )

    # Test helper — populate the editor without going through user input.
    def set_values(
        self,
        *,
        date: str | None = None,
        text: str | None = None,
    ) -> None:
        if date is not None:
            try:
                yyyy, mm, dd = (int(p) for p in date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        if text is not None:
            self._text_edit.setPlainText(text)


__all__ = ["JournalNoteDialog"]
