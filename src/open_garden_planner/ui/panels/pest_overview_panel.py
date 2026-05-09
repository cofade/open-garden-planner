"""Active pest/disease overview panel (US-12.7).

Sidebar widget that lists every unresolved pest/disease entry across all
beds and plants. Double-clicking a row emits ``item_activated(target_id,
display_name)`` so the application can re-open the dialog focused on that
target.
"""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from open_garden_planner.models.pest_log import PestLogHistory


class PestOverviewPanel(QWidget):
    """Lists all unresolved pest/disease entries with target context."""

    item_activated = pyqtSignal(str, str)  # (target_id, display_name)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._header = QLabel(self.tr("Active issues:"))
        self._header.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._header)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list)

        self.refresh({}, {})

    def refresh(
        self, pest_logs: dict[str, Any], items_by_id: dict[str, str]
    ) -> None:
        """Rebuild the list from the project's pest logs.

        Args:
            pest_logs: ``ProjectManager.pest_logs`` — ``{target_id: history_dict}``.
            items_by_id: Mapping from target UUID string → display name. Used to
                annotate each row; missing IDs fall back to ``"(deleted item)"``.
        """
        self._list.clear()
        rows: list[tuple[str, QListWidgetItem]] = []
        for target_id, raw in pest_logs.items():
            try:
                history = PestLogHistory.from_dict(raw)
            except Exception:
                continue
            for rec in history.records:
                if rec.resolved:
                    continue
                display = items_by_id.get(target_id, self.tr("(deleted item)"))
                sev_label = {
                    "low": self.tr("low"),
                    "medium": self.tr("medium"),
                    "high": self.tr("high"),
                }.get(rec.severity, rec.severity)
                text = self.tr(
                    "{display} > {name} ({severity}) — {date}"
                ).format(
                    display=display,
                    name=rec.name or self.tr("(unnamed)"),
                    severity=sev_label,
                    date=rec.date or "?",
                )
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, (target_id, display))
                rows.append((rec.date or "", item))

        rows.sort(key=lambda r: r[0], reverse=True)
        for _, item in rows:
            self._list.addItem(item)

        if not rows:
            placeholder = QListWidgetItem(self.tr("No active issues"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._list.addItem(placeholder)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        target_id, display = data
        self.item_activated.emit(str(target_id), str(display))


__all__ = ["PestOverviewPanel"]
