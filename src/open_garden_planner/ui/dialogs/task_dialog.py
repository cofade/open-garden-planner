"""Manual task editor dialog (US-C2 — task management).

Opens for a single :class:`ManualTask` — both when adding a new to-do item and
when editing an existing one. On accept, ``result_task()`` returns the populated
task ready to be persisted under the project's ``manual_tasks`` key.

Mirrors :class:`open_garden_planner.ui.dialogs.journal_note_dialog.JournalNoteDialog`
in structure and style.
"""
from __future__ import annotations

import uuid
from datetime import date as _date

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsScene,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.object_types import (
    get_translated_display_name,
    is_bed_type,
)
from open_garden_planner.models.task import ManualTask


class TaskDialog(QDialog):
    """Modal dialog for adding or editing a single manual to-do task."""

    def __init__(
        self,
        parent: QWidget | None = None,
        task: ManualTask | None = None,
        scene: QGraphicsScene | None = None,
        edit_mode: bool = False,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._edit_mode = edit_mode
        self._task_id: str = task.id if task is not None else str(uuid.uuid4())

        self.setWindowTitle(
            self.tr("Edit Task") if edit_mode else self.tr("New Task")
        )
        self.setModal(True)
        self.setMinimumWidth(440)

        self._setup_ui()
        # Always start at today; _populate overrides this only if the task
        # actually carries a date string (a freshly built ManualTask has
        # ``date=""`` and would otherwise leave the QDateEdit at its Qt
        # default of 2000-01-01).
        today = _date.today()
        self._date_edit.setDate(QDate(today.year, today.month, today.day))
        if task is not None:
            self._populate(task)

    # ── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._date_edit = QDateEdit()
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDisplayFormat("yyyy-MM-dd")
        form.addRow(self.tr("Due Date"), self._date_edit)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText(self.tr("Task summary…"))
        form.addRow(self.tr("Title"), self._title_edit)

        self._bed_combo = QComboBox()
        self._populate_bed_combo()
        form.addRow(self.tr("Linked Bed"), self._bed_combo)

        self._notes_edit = QPlainTextEdit()
        self._notes_edit.setPlaceholderText(self.tr("Details…"))
        self._notes_edit.setMinimumHeight(80)
        form.addRow(self.tr("Notes"), self._notes_edit)

        layout.addLayout(form)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_bed_combo(self) -> None:
        """Fill the bed combo: a "(No bed)" entry first, then every scene bed."""
        self._bed_combo.addItem(self.tr("(No bed)"), None)

        if self._scene is None:
            return

        beds: list[tuple[str, str]] = []
        for item in self._scene.items():
            object_type = getattr(item, "object_type", None)
            if not is_bed_type(object_type):
                continue
            label = getattr(item, "name", "") or get_translated_display_name(
                object_type
            )
            beds.append((label, str(item.item_id)))

        beds.sort(key=lambda b: b[0])
        for label, bed_id in beds:
            self._bed_combo.addItem(label, bed_id)

    # ── Population / behaviour ───────────────────────────────────────────────

    def _populate(self, task: ManualTask) -> None:
        if task.date:
            try:
                yyyy, mm, dd = (int(p) for p in task.date.split("-"))
                self._date_edit.setDate(QDate(yyyy, mm, dd))
            except (ValueError, TypeError):
                pass
        self._title_edit.setText(task.title)
        self._notes_edit.setPlainText(task.notes)
        idx = self._bed_combo.findData(task.bed_id)
        if idx >= 0:
            self._bed_combo.setCurrentIndex(idx)

    # ── Public API ───────────────────────────────────────────────────────────

    def result_task(self) -> ManualTask:
        """Return a populated ``ManualTask`` matching the dialog's state."""
        qd = self._date_edit.date()
        date_iso = f"{qd.year():04d}-{qd.month():02d}-{qd.day():02d}"
        return ManualTask(
            id=self._task_id,
            date=date_iso,
            title=self._title_edit.text().strip(),
            notes=self._notes_edit.toPlainText().rstrip(),
            bed_id=self._bed_combo.currentData(),
        )


__all__ = ["TaskDialog"]
