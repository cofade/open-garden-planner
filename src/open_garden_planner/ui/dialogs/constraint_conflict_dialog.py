"""Modal dialog offered when a new constraint cannot coexist with existing ones.

Shown by :class:`CanvasView` when :py:meth:`ConstraintGraph.find_conflicting_constraints`
returns a non-empty list.  The user can either cancel the new constraint or
override — delete the listed conflicting constraints and proceed.
"""

from uuid import UUID

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)


class ConstraintConflictDialog(QDialog):
    """Offer the user an Override-or-Cancel choice when a constraint conflicts.

    Populated with the conflicting constraints' descriptions; returns the set
    of constraint IDs the user elected to delete (empty set on cancel).
    """

    def __init__(
        self,
        conflicts: list[tuple[UUID, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Constraint conflict"))
        self.setModal(True)
        self._conflicts = conflicts
        self._selected_ids: set[UUID] = set()
        self._setup_ui()
        self.resize(460, 320)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(
            self.tr(
                "The new constraint cannot be satisfied together with the following "
                "existing constraints. Select which ones to delete, or cancel."
            )
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for cid, label in self._conflicts:
            row = QListWidgetItem()
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.setProperty("constraint_id", str(cid))
            row.setSizeHint(checkbox.sizeHint())
            self._list.addItem(row)
            self._list.setItemWidget(row, checkbox)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(
            self.tr("Override (delete selected)")
        )
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr("Cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        self._selected_ids = set()
        for i in range(self._list.count()):
            row = self._list.item(i)
            widget = self._list.itemWidget(row)
            if isinstance(widget, QCheckBox) and widget.isChecked():
                cid_str = widget.property("constraint_id")
                if cid_str:
                    self._selected_ids.add(UUID(cid_str))
        self.accept()

    @property
    def selected_ids(self) -> set[UUID]:
        """Constraint IDs the user chose to delete (empty if cancelled)."""
        return self._selected_ids

    @staticmethod
    def ask(
        conflicts: list[tuple[UUID, str]],
        parent: QWidget | None = None,
    ) -> set[UUID] | None:
        """Convenience: show dialog. Returns selected IDs or ``None`` on cancel."""
        dlg = ConstraintConflictDialog(conflicts, parent)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return dlg.selected_ids
