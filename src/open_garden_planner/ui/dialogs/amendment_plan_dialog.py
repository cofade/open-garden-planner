"""Cross-bed amendment plan dialog (US-12.10c, US-12.11).

Garden → Amendment Plan… opens this dialog. It walks every bed in the scene,
computes amendment recommendations for each from its effective soil test,
groups results by substance, and shows totals in a single shopping-list view.

Aggregation logic lives in :mod:`open_garden_planner.services.shopping_list_service`
so the totals shown here match the Materials category in the US-12.6 Shopping
List dialog. The "Add to Shopping List" button hands off to that dialog when
wired by the caller; otherwise it falls back to copying a plain-text dump to
the clipboard.

US-12.11 adds an inline "Available amendments" collapsible panel: the user can
disable substances they don't have on hand, and a "Prefer organic" checkbox
biases tie-breakers toward organic substances. Both choices are persisted on
the active :class:`ProjectManager` and survive save/load.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.amendment_loader import get_default_loader
from open_garden_planner.services.shopping_list_service import (
    AggregatedAmendment,
    aggregate_amendments,
)
from open_garden_planner.services.soil_service import SoilService
from open_garden_planner.ui.dialogs.soil_test_dialog import _amendment_display_lang
from open_garden_planner.ui.widgets import CollapsiblePanel

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.models.amendment import Amendment
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


class AmendmentPlanDialog(QDialog):
    """Modal dialog showing the cross-bed amendment plan."""

    def __init__(
        self,
        parent: QWidget | None = None,
        canvas_scene: CanvasScene | None = None,
        soil_service: SoilService | None = None,
        on_add_to_shopping_list: Callable[[], None] | None = None,
        project_manager: ProjectManager | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Amendment Plan"))
        self.setModal(True)
        self.resize(680, 520)

        self._canvas_scene = canvas_scene
        self._soil_service = soil_service
        self._on_add_to_shopping_list = on_add_to_shopping_list
        self._project_manager = project_manager
        self._aggregated: list[AggregatedAmendment] = []
        self._library_checkboxes: dict[str, QCheckBox] = {}
        self._library_loaded = False

        self._setup_ui()
        self._populate_library()
        self._populate_table()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._intro_label = QLabel(
            self.tr(
                "Recommended soil amendments aggregated across all beds with a "
                "deficient soil test. Quantities are totals — purchase rounded up "
                "and consult local extension advice before bulk application."
            )
        )
        self._intro_label.setWordWrap(True)
        layout.addWidget(self._intro_label)

        # US-12.11: amendment-library panel — user toggles which substances are
        # on hand; calculator only picks from the enabled set. Default-collapsed
        # so the dialog opens at the historical compact size.
        self._library_container = QWidget(self)
        library_layout = QVBoxLayout(self._library_container)
        library_layout.setContentsMargins(0, 0, 0, 0)
        library_layout.setSpacing(4)

        # Header row with global toggles.
        header_row = QHBoxLayout()
        self._prefer_organic_check = QCheckBox(self.tr("Prefer organic"), self)
        self._prefer_organic_check.setToolTip(
            self.tr(
                "When two substances cover the same deficits, pick the organic "
                "one. Disable to let mineral compounds compete on equal footing."
            )
        )
        self._prefer_organic_check.toggled.connect(self._on_prefer_organic_toggled)
        header_row.addWidget(self._prefer_organic_check)

        header_row.addStretch(1)

        self._reset_library_button = QPushButton(self.tr("Enable all"), self)
        self._reset_library_button.clicked.connect(self._on_reset_library_clicked)
        header_row.addWidget(self._reset_library_button)

        library_layout.addLayout(header_row)

        # Three group boxes (organic / mineral / structural), each holds a
        # grid of checkboxes inside a scroll area so very long lists stay
        # manageable on small screens.
        self._library_scroll = QScrollArea(self)
        self._library_scroll.setWidgetResizable(True)
        self._library_scroll.setMinimumHeight(180)
        scroll_inner = QWidget(self)
        self._library_inner_layout = QVBoxLayout(scroll_inner)
        self._library_inner_layout.setContentsMargins(2, 2, 2, 2)
        self._library_inner_layout.setSpacing(6)
        self._library_scroll.setWidget(scroll_inner)
        library_layout.addWidget(self._library_scroll)

        self._library_collapsible = CollapsiblePanel(
            self.tr("Available amendments"),
            self._library_container,
            expanded=False,
        )
        layout.addWidget(self._library_collapsible)

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels([
            self.tr("Substance"),
            self.tr("Total"),
            self.tr("Beds"),
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents
        )
        self._table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        self._empty_label = QLabel(self.tr("No deficient beds found."))
        self._empty_label.setVisible(False)
        layout.addWidget(self._empty_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)

        self._add_to_list_button = QPushButton(self.tr("Add to Shopping List"))
        self._add_to_list_button.clicked.connect(self._on_add_to_shopping_list_clicked)
        button_box.addButton(
            self._add_to_list_button, QDialogButtonBox.ButtonRole.ActionRole
        )

        self._copy_button = QPushButton(self.tr("Copy to clipboard"))
        self._copy_button.clicked.connect(self._on_copy_clicked)
        button_box.addButton(
            self._copy_button, QDialogButtonBox.ButtonRole.ActionRole
        )

        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._status_label = QLabel("")
        layout.addWidget(self._status_label)

    # ── Library panel (US-12.11) ─────────────────────────────────────────────

    def _populate_library(self) -> None:
        """Build the checkbox grid from the bundled amendment library.

        Splits substances into organic / mineral / structural sections. The
        check state is sourced from ``ProjectManager.enabled_amendments`` —
        ``None`` (the default) means every checkbox starts ticked.
        """
        loader = get_default_loader()
        try:
            amendments = loader.get_amendments()
        except Exception:
            amendments = []

        organic: list[Amendment] = []
        mineral: list[Amendment] = []
        structural: list[Amendment] = []
        from open_garden_planner.models.amendment import (
            FIX_IMPROVES_AERATION,
            FIX_IMPROVES_DRAINAGE,
            FIX_IMPROVES_WATER_RETENTION,
        )
        structural_tags = {
            FIX_IMPROVES_AERATION,
            FIX_IMPROVES_DRAINAGE,
            FIX_IMPROVES_WATER_RETENTION,
        }
        for a in amendments:
            if structural_tags.intersection(a.fixes) and not (
                a.n_level_effect or a.p_level_effect or a.k_level_effect
            ):
                structural.append(a)
            elif a.organic:
                organic.append(a)
            else:
                mineral.append(a)

        sections = (
            (self.tr("Organic"), organic),
            (self.tr("Mineral"), mineral),
            (self.tr("Structural"), structural),
        )
        enabled = (
            self._project_manager.enabled_amendments
            if self._project_manager is not None
            else None
        )
        enabled_set = set(enabled) if enabled is not None else None
        prefer_organic = (
            self._project_manager.prefer_organic
            if self._project_manager is not None
            else True
        )
        self._prefer_organic_check.blockSignals(True)
        self._prefer_organic_check.setChecked(prefer_organic)
        self._prefer_organic_check.blockSignals(False)

        lang = _amendment_display_lang()
        for title, group in sections:
            if not group:
                continue
            box = QGroupBox(title, self)
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(2)
            for idx, amendment in enumerate(group):
                check = QCheckBox(amendment.display_name(lang), box)
                check.setChecked(
                    enabled_set is None or amendment.id in enabled_set
                )
                check.toggled.connect(self._on_library_toggled)
                self._library_checkboxes[amendment.id] = check
                row, col = divmod(idx, 2)
                grid.addWidget(check, row, col, Qt.AlignmentFlag.AlignLeft)
            self._library_inner_layout.addWidget(box)
        self._library_inner_layout.addStretch(1)
        self._library_loaded = True

    def _on_library_toggled(self, _checked: bool) -> None:
        """User flipped a checkbox — push the new allowlist to ProjectManager."""
        if not self._library_loaded or self._project_manager is None:
            return
        # If every box is ticked, store ``None`` (default state); otherwise
        # store the explicit allowlist of ticked ids.
        ids = [
            amendment_id
            for amendment_id, check in self._library_checkboxes.items()
            if check.isChecked()
        ]
        all_ids = set(self._library_checkboxes.keys())
        new_value: list[str] | None = None if set(ids) == all_ids else sorted(ids)
        self._project_manager.set_enabled_amendments(new_value)
        self._populate_table()

    def _on_prefer_organic_toggled(self, checked: bool) -> None:
        """Push the organic-preference flag to ProjectManager and recompute."""
        if not self._library_loaded or self._project_manager is None:
            return
        self._project_manager.set_prefer_organic(bool(checked))
        self._populate_table()

    def _on_reset_library_clicked(self) -> None:
        """Re-tick every checkbox and clear the project's allowlist."""
        if self._project_manager is not None:
            self._project_manager.set_enabled_amendments(None)
        for check in self._library_checkboxes.values():
            check.blockSignals(True)
            check.setChecked(True)
            check.blockSignals(False)
        self._populate_table()

    # ── Table ────────────────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        """Compute aggregations from the scene and populate the table."""
        if self._canvas_scene is None or self._soil_service is None:
            self._aggregated = []
        else:
            enabled = (
                self._project_manager.enabled_amendments
                if self._project_manager is not None
                else None
            )
            enabled_set = set(enabled) if enabled is not None else None
            prefer_organic = (
                self._project_manager.prefer_organic
                if self._project_manager is not None
                else True
            )
            self._aggregated = aggregate_amendments(
                self._canvas_scene,
                self._soil_service,
                enabled_ids=enabled_set,
                prefer_organic=prefer_organic,
            )
        self._table.setRowCount(len(self._aggregated))
        if not self._aggregated:
            self._empty_label.setVisible(True)
            self._copy_button.setEnabled(False)
            self._add_to_list_button.setEnabled(False)
            return
        self._empty_label.setVisible(False)
        self._copy_button.setEnabled(True)
        self._add_to_list_button.setEnabled(True)
        lang = _amendment_display_lang()
        for row, agg in enumerate(self._aggregated):
            self._table.setItem(
                row, 0, QTableWidgetItem(agg.amendment.display_name(lang))
            )
            self._table.setItem(
                row, 1, QTableWidgetItem(_format_quantity(agg.total_g))
            )
            self._table.setItem(
                row, 2, QTableWidgetItem(", ".join(agg.bed_names))
            )

    # ── Actions ──────────────────────────────────────────────────────────────

    def _on_copy_clicked(self) -> None:
        """Copy the plan as plain text to the system clipboard."""
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        clipboard.setText(self._build_clipboard_text())
        self._status_label.setText(self.tr("Amendment plan copied to clipboard."))

    def _on_add_to_shopping_list_clicked(self) -> None:
        """Hand off to the Shopping List dialog when wired by the host."""
        if self._on_add_to_shopping_list is None:
            self._status_label.setText(self.tr("Shopping list not available."))
            return
        self.accept()
        self._on_add_to_shopping_list()

    def _build_clipboard_text(self) -> str:
        """Render the aggregations as a tab-separated table for paste-into-spreadsheet."""
        lang = _amendment_display_lang()
        # Header row matches the visible column titles (kept in sync with _setup_ui).
        lines = [
            "\t".join(
                (self.tr("Substance"), self.tr("Total"), self.tr("Beds"))
            )
        ]
        for agg in self._aggregated:
            lines.append(
                "\t".join(
                    (
                        agg.amendment.display_name(lang),
                        _format_quantity(agg.total_g),
                        ", ".join(agg.bed_names),
                    )
                )
            )
        return "\n".join(lines)


def _format_quantity(grams: float) -> str:
    """Format a gram quantity. ≥1000 g shown in kg; else g."""
    if grams >= 1000.0:
        return f"{grams / 1000.0:.2f} kg"
    return f"{grams:.0f} g"


__all__ = ["AmendmentPlanDialog"]
