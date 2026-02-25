"""Constraints manager panel for listing, editing, and deleting constraints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QLineF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from open_garden_planner.core.constraints import Constraint, ConstraintGraph
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

# Colors matching dimension_lines.py
_COLOR_SATISFIED = QColor(0, 120, 200)
_COLOR_VIOLATED = QColor(220, 40, 40)
_COLOR_ALIGN_SATISFIED = QColor(120, 0, 180)
_COLOR_ANGLE_SATISFIED = QColor(200, 100, 0)
_COLOR_COINCIDENT_SATISFIED = QColor(0, 160, 200)
_COLOR_PARALLEL_SATISFIED = QColor(20, 160, 100)


def _make_status_icon(color: QColor, size: int = 14) -> QPixmap:
    """Create a small circle pixmap in the given color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color.darker(120), 1))
    painter.setBrush(color)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return pixmap


class ConstraintListItem(QWidget):
    """Widget for a single constraint row in the list."""

    delete_requested = pyqtSignal(UUID)

    def __init__(
        self,
        constraint_id: UUID,
        label_a: str,
        label_b: str,
        target_distance: float,
        satisfied: bool,
        constraint_type_name: str = "DISTANCE",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.constraint_id = constraint_id
        self._setup_ui(label_a, label_b, target_distance, satisfied, constraint_type_name)

    def _setup_ui(
        self,
        label_a: str,
        label_b: str,
        target_distance: float,
        satisfied: bool,
        constraint_type_name: str,
    ) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Status icon color depends on type
        is_alignment = constraint_type_name in ("HORIZONTAL", "VERTICAL")
        is_angle = constraint_type_name == "ANGLE"
        is_coincident = constraint_type_name == "COINCIDENT"
        is_parallel = constraint_type_name == "PARALLEL"
        if is_alignment:
            color = _COLOR_ALIGN_SATISFIED if satisfied else _COLOR_VIOLATED
        elif is_angle:
            color = _COLOR_ANGLE_SATISFIED if satisfied else _COLOR_VIOLATED
        elif is_coincident:
            color = _COLOR_COINCIDENT_SATISFIED if satisfied else _COLOR_VIOLATED
        elif is_parallel:
            color = _COLOR_PARALLEL_SATISFIED if satisfied else _COLOR_VIOLATED
        else:
            color = _COLOR_SATISFIED if satisfied else _COLOR_VIOLATED

        pixmap = _make_status_icon(color)
        status_label = QLabel()
        status_label.setPixmap(pixmap)
        status_label.setFixedSize(QSize(20, 20))
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status_label.setToolTip(
            self.tr("Satisfied") if satisfied else self.tr("Violated")
        )
        layout.addWidget(status_label)

        # Object names and constraint label
        if constraint_type_name == "HORIZONTAL":
            detail = self.tr("≡ H")
            tooltip = self.tr("{a} horizontal align {b}").format(a=label_a, b=label_b)
        elif constraint_type_name == "VERTICAL":
            detail = self.tr("≡ V")
            tooltip = self.tr("{a} vertical align {b}").format(a=label_a, b=label_b)
        elif constraint_type_name == "ANGLE":
            detail = f"{target_distance:.1f}°"
            tooltip = self.tr("∠ {a}–{b}–{c}: {d:.1f}°").format(
                a=label_a, b=label_b, c=self.tr("…"), d=target_distance
            )
        elif constraint_type_name == "COINCIDENT":
            detail = self.tr("⦿ Coincident")
            tooltip = self.tr("{a} coincident with {b}").format(a=label_a, b=label_b)
        elif constraint_type_name == "PARALLEL":
            detail = self.tr("\u2225 Parallel")
            tooltip = self.tr("{a} parallel to {b}").format(a=label_a, b=label_b)
        else:
            dist_m = target_distance / 100.0
            detail = f"{dist_m:.2f} m"
            tooltip = self.tr("{a} \u2194 {b}: {d:.2f} m").format(
                a=label_a, b=label_b, d=dist_m
            )

        if constraint_type_name == "ANGLE":
            text = f"∠ {label_a}–{label_b}–…   {detail}"
        elif constraint_type_name == "COINCIDENT":
            text = f"⦿ {label_a}  ↔  {label_b}   {detail}"
        elif constraint_type_name == "PARALLEL":
            text = f"\u2225 {label_a}  \u2225  {label_b}"
        else:
            text = f"{label_a}  \u2194  {label_b}   {detail}"
        label = QLabel(text)
        label.setToolTip(tooltip)
        layout.addWidget(label, 1)

        # Delete button
        delete_btn = QToolButton()
        delete_btn.setText("\u00d7")
        delete_btn.setFixedSize(20, 20)
        delete_btn.setToolTip(self.tr("Delete constraint"))
        delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.constraint_id))
        layout.addWidget(delete_btn)


class ConstraintsPanel(QWidget):
    """Sidebar panel for managing distance constraints.

    Lists all constraints with status (satisfied/violated), enables
    selecting, editing (double-click), and deleting constraints.

    Signals:
        constraint_selected: Emitted when a constraint row is clicked.
            Carries the constraint UUID.
        constraint_edit_requested: Emitted on double-click for distance editing.
            Carries the constraint UUID.
        constraint_delete_requested: Emitted when the delete button is clicked.
            Carries the constraint UUID.
    """

    constraint_selected = pyqtSignal(object)  # UUID
    constraint_edit_requested = pyqtSignal(object)  # UUID
    constraint_delete_requested = pyqtSignal(object)  # UUID

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene: CanvasScene | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Constraint list
        self._list = QListWidget()
        self._list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        # Empty state label (shown when no constraints)
        self._empty_label = QLabel(
            self.tr("No constraints yet.\nUse the Constraint tool (K) to add one.")
        )
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        self._empty_label.setStyleSheet("QLabel { padding: 12px; font-style: italic; }")
        layout.addWidget(self._empty_label)

        layout.addStretch()

    def set_scene(self, scene: CanvasScene) -> None:
        """Set the canvas scene to read constraints from."""
        self._scene = scene

    def refresh(self) -> None:
        """Rebuild the constraint list from the scene's constraint graph."""
        self._list.clear()

        if self._scene is None:
            self._show_empty(True)
            return

        graph: ConstraintGraph = self._scene.constraint_graph
        constraints = list(graph.constraints.values())

        if not constraints:
            self._show_empty(True)
            return

        self._show_empty(False)

        # Build item-id -> label lookup
        item_labels = self._build_item_labels()

        for constraint in constraints:
            label_a = item_labels.get(constraint.anchor_a.item_id, self.tr("Object"))
            label_b = item_labels.get(constraint.anchor_b.item_id, self.tr("Object"))
            satisfied = self._is_satisfied(constraint)

            row_widget = ConstraintListItem(
                constraint.constraint_id,
                label_a,
                label_b,
                constraint.target_distance,
                satisfied,
                constraint.constraint_type.name,
            )
            row_widget.delete_requested.connect(self.constraint_delete_requested.emit)

            item = QListWidgetItem(self._list)
            hint = row_widget.sizeHint()
            hint.setHeight(max(hint.height(), 32))
            item.setSizeHint(hint)
            # Store constraint id for later retrieval
            item.setData(Qt.ItemDataRole.UserRole, str(constraint.constraint_id))
            self._list.addItem(item)
            self._list.setItemWidget(item, row_widget)

        # Adjust height: show up to 6 rows then scroll
        self._adjust_list_height()

    def delete_all(self) -> None:
        """Delete all constraints (called from header button)."""
        # Collect all IDs first — emitting signals mid-loop causes refresh()
        # to clear the list, breaking iteration
        ids = [
            UUID(self._list.item(i).data(Qt.ItemDataRole.UserRole))
            for i in range(self._list.count())
            if self._list.item(i) and self._list.item(i).data(Qt.ItemDataRole.UserRole)
        ]
        for cid in ids:
            self.constraint_delete_requested.emit(cid)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _show_empty(self, empty: bool) -> None:
        """Toggle between empty state and list."""
        self._empty_label.setVisible(empty)
        self._list.setVisible(not empty)

    def _build_item_labels(self) -> dict[UUID, str]:
        """Build a mapping from item UUID to a unique display label."""
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        raw: dict[UUID, str] = {}
        if self._scene is None:
            return raw

        for item in self._scene.items():
            if isinstance(item, GardenItemMixin):
                name = getattr(item, "name", "") or ""
                if name:
                    raw[item.item_id] = name
                    continue
                obj_type = getattr(item, "object_type", None)
                if obj_type is not None:
                    # Use the enum member name, formatted for readability.
                    # Strip "GENERIC_" prefix and title-case (e.g. GENERIC_RECTANGLE → Rectangle)
                    type_name = obj_type.name.replace("_", " ").title()
                    type_name = type_name.removeprefix("Generic ")
                    raw[item.item_id] = type_name
                else:
                    raw[item.item_id] = self.tr("Object")

        # Append counters to disambiguate items with the same label
        label_count: dict[str, int] = {}
        for label in raw.values():
            label_count[label] = label_count.get(label, 0) + 1

        occurrence: dict[str, int] = {}
        labels: dict[UUID, str] = {}
        for item_id, label in raw.items():
            if label_count[label] > 1:
                occurrence[label] = occurrence.get(label, 0) + 1
                labels[item_id] = f"{label} {occurrence[label]}"
            else:
                labels[item_id] = label

        return labels

    def _is_satisfied(self, constraint: Constraint) -> bool:
        """Check whether a constraint is satisfied (within tolerance)."""
        import math

        from open_garden_planner.core.constraints import ConstraintType

        if self._scene is None:
            return False

        dlm = self._scene.dimension_line_manager
        pos_a = dlm._resolve_anchor_position(
            constraint.anchor_a.item_id,
            constraint.anchor_a.anchor_type,
            constraint.anchor_a.anchor_index,
        )
        pos_b = dlm._resolve_anchor_position(
            constraint.anchor_b.item_id,
            constraint.anchor_b.anchor_type,
            constraint.anchor_b.anchor_index,
        )
        if pos_a is None or pos_b is None:
            return False

        if constraint.constraint_type == ConstraintType.HORIZONTAL:
            return abs(pos_b.y() - pos_a.y()) < 1.0
        if constraint.constraint_type == ConstraintType.VERTICAL:
            return abs(pos_b.x() - pos_a.x()) < 1.0
        if constraint.constraint_type == ConstraintType.COINCIDENT:
            dx = pos_b.x() - pos_a.x()
            dy = pos_b.y() - pos_a.y()
            return math.sqrt(dx * dx + dy * dy) < 0.1  # 1 mm tolerance
        if constraint.constraint_type == ConstraintType.ANGLE:
            if constraint.anchor_c is None:
                return False
            pos_c = dlm._resolve_anchor_position(
                constraint.anchor_c.item_id,
                constraint.anchor_c.anchor_type,
                constraint.anchor_c.anchor_index,
            )
            if pos_c is None:
                return False
            ba_x, ba_y = pos_a.x() - pos_b.x(), pos_a.y() - pos_b.y()
            bc_x, bc_y = pos_c.x() - pos_b.x(), pos_c.y() - pos_b.y()
            ba_len = math.sqrt(ba_x * ba_x + ba_y * ba_y)
            bc_len = math.sqrt(bc_x * bc_x + bc_y * bc_y)
            if ba_len < 1e-6 or bc_len < 1e-6:
                return False
            cos_val = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)))
            current_deg = math.degrees(math.acos(cos_val))
            return abs(current_deg - constraint.target_distance) < 0.5
        if constraint.constraint_type == ConstraintType.PARALLEL:
            # Satisfied when item B's rotation matches the stored target (±0.5°)
            item_b = dlm._find_item_by_id(constraint.anchor_b.item_id)
            current_rot = getattr(item_b, "rotation_angle", 0.0) if item_b else 0.0
            angle_error = abs((current_rot - constraint.target_distance + 90.0) % 180.0 - 90.0)
            return angle_error < 0.5

        current_dist = QLineF(pos_a, pos_b).length()
        return abs(current_dist - constraint.target_distance) < 1.0

    def _adjust_list_height(self) -> None:
        """Adjust list widget height based on number of rows."""
        row_height = 36
        count = self._list.count()
        max_visible = 6
        if count <= max_visible:
            self._list.setFixedHeight(max(row_height, count * row_height))
        else:
            height = max_visible * row_height
            self._list.setMaximumHeight(height)
            self._list.setMinimumHeight(height)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_row_changed(self, row: int) -> None:
        """Handle row selection — select both constrained objects on canvas."""
        if row < 0:
            return
        item = self._list.item(row)
        if item is None:
            return
        cid_str = item.data(Qt.ItemDataRole.UserRole)
        if cid_str:
            self.constraint_selected.emit(UUID(cid_str))

    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Handle double-click — request distance editing."""
        cid_str = item.data(Qt.ItemDataRole.UserRole)
        if cid_str:
            self.constraint_edit_requested.emit(UUID(cid_str))
