"""Whole-plan companion planting compatibility check dialog.

Scans all plant pairs within a configurable proximity radius and presents
a report with beneficial / antagonistic pairings, a compatibility score,
and live row-click selection of the involved plants on the canvas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from open_garden_planner.services.companion_planting_service import (
        CompanionPlantingService,
        CompanionRelationship,
    )
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


@dataclass
class PlantPairResult:
    """Result of checking one plant pair."""

    plant_a_name: str
    plant_b_name: str
    relationship: CompanionRelationship
    distance_cm: float
    # Canvas items involved (kept for live selection)
    items: list[Any] = field(default_factory=list)


def analyse_plan(
    scene: CanvasScene,
    service: CompanionPlantingService,
    radius_cm: float,
    species_name_fn: object,
    is_plant_fn: object,
    lang: str = "en",
) -> tuple[list[PlantPairResult], list[PlantPairResult]]:
    """Scan all plant pairs within *radius_cm* and return results.

    Returns:
        (beneficial_pairs, antagonistic_pairs) — each a list of PlantPairResult.
    """
    from open_garden_planner.services.companion_planting_service import (
        ANTAGONISTIC,
        BENEFICIAL,
    )

    all_plants = [
        it for it in scene.items()
        if is_plant_fn(it) and species_name_fn(it)
    ]

    beneficial: list[PlantPairResult] = []
    antagonistic: list[PlantPairResult] = []
    seen: set[tuple[int, int]] = set()

    for i, plant_a in enumerate(all_plants):
        center_a = plant_a.mapToScene(plant_a.rect().center())  # type: ignore[attr-defined]
        species_a = species_name_fn(plant_a)
        for j, plant_b in enumerate(all_plants):
            if j <= i:
                continue
            pair_key = (id(plant_a), id(plant_b))
            if pair_key in seen:
                continue
            seen.add(pair_key)

            center_b = plant_b.mapToScene(plant_b.rect().center())  # type: ignore[attr-defined]
            dist = math.hypot(
                center_a.x() - center_b.x(),
                center_a.y() - center_b.y(),
            )
            if dist > radius_cm:
                continue

            species_b = species_name_fn(plant_b)
            rel = service.get_relationship(species_a, species_b)
            if rel is None:
                continue

            display_a = service.get_display_name(species_a, lang)
            display_b = service.get_display_name(species_b, lang)
            result = PlantPairResult(
                plant_a_name=display_a,
                plant_b_name=display_b,
                relationship=rel,
                distance_cm=dist,
                items=[plant_a, plant_b],
            )
            if rel.type == BENEFICIAL:
                beneficial.append(result)
            elif rel.type == ANTAGONISTIC:
                antagonistic.append(result)

    return beneficial, antagonistic


class CompanionCheckDialog(QDialog):
    """Report dialog for whole-plan companion planting compatibility."""

    def __init__(
        self,
        beneficial: list[PlantPairResult],
        antagonistic: list[PlantPairResult],
        service: CompanionPlantingService,
        scene: CanvasScene | None = None,
        lang: str = "en",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._beneficial = beneficial
        self._antagonistic = antagonistic
        self._service = service
        self._scene = scene
        self._lang = lang
        # Map from (table_id, row) -> PlantPairResult for click handling
        self._row_pairs: dict[int, PlantPairResult] = {}
        self._tables: list[QTableWidget] = []

        self.setWindowTitle(self.tr("Companion Planting Report"))
        self.setMinimumSize(620, 480)
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # --- Score ---
        score = self._compute_score()
        score_label = QLabel(self.tr("Compatibility Score: %1").replace("%1", str(score)))
        score_font = QFont()
        score_font.setPointSize(16)
        score_font.setBold(True)
        score_label.setFont(score_font)
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if score >= 70:
            score_label.setStyleSheet("color: #66bb6a;")
        elif score >= 40:
            score_label.setStyleSheet("color: #ffa726;")
        else:
            score_label.setStyleSheet("color: #ef5350;")
        layout.addWidget(score_label)

        # --- Summary ---
        summary = QLabel(
            self.tr("{good} beneficial · {bad} antagonistic pairings").format(
                good=len(self._beneficial),
                bad=len(self._antagonistic),
            )
        )
        summary.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(summary)

        layout.addSpacing(8)

        # --- Antagonistic table ---
        if self._antagonistic:
            bad_header = QLabel(self.tr("Conflicts"))
            bad_font = QFont()
            bad_font.setBold(True)
            bad_header.setFont(bad_font)
            bad_header.setStyleSheet("color: #ef5350;")
            layout.addWidget(bad_header)
            layout.addWidget(self._build_table(self._antagonistic, is_bad=True))

        # --- Beneficial table ---
        if self._beneficial:
            good_header = QLabel(self.tr("Beneficial Pairings"))
            good_font = QFont()
            good_font.setBold(True)
            good_header.setFont(good_font)
            good_header.setStyleSheet("color: #66bb6a;")
            layout.addWidget(good_header)
            layout.addWidget(self._build_table(self._beneficial, is_bad=False))

        if not self._antagonistic and not self._beneficial:
            empty = QLabel(self.tr("No companion planting relationships found among nearby plants."))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setWordWrap(True)
            layout.addWidget(empty)

        layout.addSpacing(8)

        # --- Close button ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton(self.tr("Close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _build_table(self, pairs: list[PlantPairResult], *, is_bad: bool) -> QTableWidget:
        table = QTableWidget(len(pairs), 4)
        table.setHorizontalHeaderLabels([
            self.tr("Plant A"),
            self.tr("Plant B"),
            self.tr("Distance"),
            self.tr("Reason"),
        ])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)

        # Selection color matching the table type (red for conflicts, green for beneficial)
        if is_bad:
            table.setStyleSheet(
                "QTableWidget::item:selected { background-color: rgba(220, 60, 60, 100); }"
            )
        else:
            table.setStyleSheet(
                "QTableWidget::item:selected { background-color: rgba(60, 180, 60, 100); }"
            )

        # Use a subtle semi-transparent tint that works in both light and dark mode
        highlight_color = QColor(220, 60, 60, 40) if is_bad else QColor(60, 180, 60, 40)

        table_id = id(table)
        for row, pair in enumerate(pairs):
            items = [
                QTableWidgetItem(pair.plant_a_name),
                QTableWidgetItem(pair.plant_b_name),
                QTableWidgetItem(f"{pair.distance_cm / 100:.2f} m"),
                QTableWidgetItem(self._service.get_relationship_reason(pair.relationship, self._lang)),
            ]
            for col, item in enumerate(items):
                item.setBackground(highlight_color)
                table.setItem(row, col, item)
            self._row_pairs[(table_id, row)] = pair

        # Connect row click to live canvas selection
        table.itemSelectionChanged.connect(lambda t=table: self._on_row_selected(t))
        self._tables.append(table)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        table.setMaximumHeight(min(200, 30 + len(pairs) * 30))
        return table

    def _on_row_selected(self, table: QTableWidget) -> None:
        """Select the plants for the clicked row on the canvas."""
        if self._scene is None:
            return
        selected_rows = table.selectionModel().selectedRows()
        if not selected_rows:
            return

        # Clear selection in other tables so only one row is active at a time
        for other in self._tables:
            if other is not table:
                other.clearSelection()
        row = selected_rows[0].row()
        pair = self._row_pairs.get((id(table), row))
        if pair is None or not pair.items:
            return

        import contextlib

        self._scene.clearSelection()
        for item in pair.items:
            with contextlib.suppress(RuntimeError):
                item.setSelected(True)

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def _compute_score(self) -> int:
        """Compute 0–100 compatibility score.

        Formula: 100 * good / (good + bad).  If no relationships found, returns 100.
        """
        total = len(self._beneficial) + len(self._antagonistic)
        if total == 0:
            return 100
        return round(100 * len(self._beneficial) / total)
