"""Season Manager dialog for US-10.7: Season management & plan duplication."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager


class SeasonManagerDialog(QDialog):
    """Dialog for managing garden plan seasons.

    Allows the user to:
    - See all linked seasons for the current project
    - Create a new season (duplicates current plan)
    - Switch to a different season (opens that .ogp file)
    """

    def __init__(
        self,
        project_manager: ProjectManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._project_manager = project_manager
        self._open_season_path: Path | None = None
        self._new_season_path: Path | None = None
        self._new_season_year: int | None = None
        self._new_season_keep_plants: bool = False

        self.setWindowTitle(self.tr("Season Manager"))
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setMinimumHeight(380)

        self._setup_ui()

    # ── UI Setup ──────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Current season info
        current_year = self._project_manager.season_year
        if current_year:
            current_label = QLabel(
                self.tr("Current season: <b>{year}</b>").format(year=current_year)
            )
        else:
            current_label = QLabel(self.tr("Current season: <b>Not set</b>"))
        layout.addWidget(current_label)

        # Linked seasons list
        seasons_group = QGroupBox(self.tr("Linked Seasons"))
        seasons_layout = QVBoxLayout(seasons_group)

        self._seasons_list = QListWidget()
        self._seasons_list.setMinimumHeight(120)
        self._populate_seasons_list()
        seasons_layout.addWidget(self._seasons_list)

        btn_row = QHBoxLayout()
        self._open_btn = QPushButton(self.tr("Open Selected Season"))
        self._open_btn.setEnabled(False)
        self._open_btn.clicked.connect(self._on_open_season)
        btn_row.addWidget(self._open_btn)
        btn_row.addStretch()
        seasons_layout.addLayout(btn_row)
        layout.addWidget(seasons_group)

        self._seasons_list.currentItemChanged.connect(self._on_season_selection_changed)

        # New season group
        new_group = QGroupBox(self.tr("Create New Season"))
        new_layout = QVBoxLayout(new_group)

        # Year selector
        year_row = QHBoxLayout()
        year_row.addWidget(QLabel(self.tr("Season year:")))
        self._year_spin = QSpinBox()
        self._year_spin.setRange(2000, 2100)
        next_year = (current_year + 1) if current_year else 2026
        self._year_spin.setValue(next_year)
        self._year_spin.setMinimumWidth(90)
        year_row.addWidget(self._year_spin)
        year_row.addStretch()
        new_layout.addLayout(year_row)

        # Plant carry-over options
        plant_label = QLabel(self.tr("Annual plants from current season:"))
        new_layout.addWidget(plant_label)

        self._plant_mode_group = QButtonGroup(self)
        self._radio_clear = QRadioButton(self.tr("Clear annuals (trees and shrubs are kept)"))
        self._radio_keep = QRadioButton(self.tr("Keep all plants (carry over — for perennials/trees)"))
        self._radio_clear.setChecked(True)
        self._plant_mode_group.addButton(self._radio_clear)
        self._plant_mode_group.addButton(self._radio_keep)
        new_layout.addWidget(self._radio_clear)
        new_layout.addWidget(self._radio_keep)

        create_btn_row = QHBoxLayout()
        self._create_btn = QPushButton(self.tr("Save as New Season…"))
        self._create_btn.clicked.connect(self._on_create_season)
        create_btn_row.addWidget(self._create_btn)
        create_btn_row.addStretch()
        new_layout.addLayout(create_btn_row)
        layout.addWidget(new_group)

        # Disable new season creation when there's no saved file
        if self._project_manager.current_file is None:
            self._create_btn.setEnabled(False)
            self._create_btn.setToolTip(
                self.tr("Save the project first before creating a new season")
            )

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate_seasons_list(self) -> None:
        self._seasons_list.clear()
        linked = self._project_manager.linked_seasons
        current_year = self._project_manager.season_year
        current_file = self._project_manager.current_file

        if not linked:
            placeholder = QListWidgetItem(self.tr("No linked seasons yet"))
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self._seasons_list.addItem(placeholder)
            return

        for season in linked:
            year = season.get("year", "?")
            file_str = season.get("file", "")
            # Resolve relative paths against current file's directory
            if current_file and file_str and not Path(file_str).is_absolute():
                resolved = current_file.parent / file_str
            else:
                resolved = Path(file_str) if file_str else None

            exists = resolved is not None and resolved.exists()
            marker = "✓" if exists else "✗"
            is_current = (year == current_year)
            label = f"{year}  {marker}  {file_str}"
            if is_current:
                label = f"▶ {label}  [current]"

            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, {"year": year, "file": file_str, "resolved": resolved})
            if not exists:
                item.setForeground(Qt.GlobalColor.gray)
            self._seasons_list.addItem(item)

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_season_selection_changed(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if current is None:
            self._open_btn.setEnabled(False)
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if data is None:
            self._open_btn.setEnabled(False)
            return
        resolved: Path | None = data.get("resolved")
        self._open_btn.setEnabled(resolved is not None and resolved.exists())

    def _on_open_season(self) -> None:
        item = self._seasons_list.currentItem()
        if item is None:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        resolved: Path | None = data.get("resolved")
        if resolved is None or not resolved.exists():
            QMessageBox.warning(
                self,
                self.tr("File Not Found"),
                self.tr("The season file could not be found:\n{path}").format(path=data.get("file", "")),
            )
            return
        self._open_season_path = resolved
        self.accept()

    def _on_create_season(self) -> None:
        year = self._year_spin.value()
        keep_plants = self._radio_keep.isChecked()
        current_file = self._project_manager.current_file

        # Suggest a filename next to the current file
        if current_file:
            stem = current_file.stem
            # Remove trailing year if present (e.g. MyGarden_2024 → MyGarden)
            parts = stem.rsplit("_", 1)
            base = parts[0] if len(parts) == 2 and parts[1].isdigit() else stem
            suggested = current_file.parent / f"{base}_{year}.ogp"
        else:
            suggested = Path(f"garden_{year}.ogp")

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr("Save New Season As"),
            str(suggested),
            self.tr("Garden Plan (*.ogp)"),
        )
        if not file_path:
            return

        self._new_season_path = Path(file_path)
        self._new_season_year = year
        self._new_season_keep_plants = keep_plants
        self.accept()

    # ── Result accessors ──────────────────────────────────────────────────

    @property
    def action(self) -> str | None:
        """What the user chose: 'open', 'create', or None (closed)."""
        if self._open_season_path is not None:
            return "open"
        if self._new_season_path is not None:
            return "create"
        return None

    @property
    def open_season_path(self) -> Path | None:
        return self._open_season_path

    @property
    def new_season_path(self) -> Path | None:
        return self._new_season_path

    @property
    def new_season_year(self) -> int | None:
        return self._new_season_year

    @property
    def new_season_keep_plants(self) -> bool:
        return self._new_season_keep_plants
