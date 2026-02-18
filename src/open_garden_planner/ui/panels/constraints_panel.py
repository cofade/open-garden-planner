"""Constraints manager panel for listing, editing, and deleting distance constraints."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from PyQt6.QtCore import QLineF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
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
_COLOR_OVER_CONSTRAINED = QColor(200, 120, 0)


def _make_status_icon(color: QColor, size: int = 16) -> QIcon:
    """Create a small circle icon in the given color."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(color.darker(120), 1))
    painter.setBrush(color)
    painter.drawEllipse(2, 2, size - 4, size - 4)
    painter.end()
    return QIcon(pixmap)


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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.constraint_id = constraint_id
        self._setup_ui(label_a, label_b, target_distance, satisfied)

    def _setup_ui(
        self,
        label_a: str,
        label_b: str,
        target_distance: float,
        satisfied: bool,
    ) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # Status icon
        color = _COLOR_SATISFIED if satisfied else _COLOR_VIOLATED
        icon = _make_status_icon(color)
        self._status_btn = QToolButton()
        self._status_btn.setIcon(icon)
        self._status_btn.setIconSize(QSize(14, 14))
        self._status_btn.setFixedSize(20, 20)
        self._status_btn.setEnabled(False)
        self._status_btn.setToolTip(
            self.tr("Satisfied") if satisfied else self.tr("Violated")
        )
        layout.addWidget(self._status_btn)

        # Object names and distance label
        dist_m = target_distance / 100.0
        text = f"{label_a}  \u2194  {label_b}   {dist_m:.2f} m"
        self._label = QLabel(text)
        self._label.setToolTip(
            self.tr("{a} \u2194 {b}: {d:.2f} m").format(
                a=label_a, b=label_b, d=dist_m
            )
        )
        layout.addWidget(self._label, 1)

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
        self._empty_label.setStyleSheet("color: palette(mid); padding: 12px;")
        layout.addWidget(self._empty_label)

        # Delete all button
        self._delete_all_btn = QPushButton(self.tr("Delete All"))
        self._delete_all_btn.setToolTip(self.tr("Remove all constraints"))
        self._delete_all_btn.clicked.connect(self._on_delete_all)
        layout.addWidget(self._delete_all_btn)

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

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _show_empty(self, empty: bool) -> None:
        """Toggle between empty state and list."""
        self._empty_label.setVisible(empty)
        self._list.setVisible(not empty)
        self._delete_all_btn.setVisible(not empty)

    def _build_item_labels(self) -> dict[UUID, str]:
        """Build a mapping from item UUID to display label."""
        from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin

        labels: dict[UUID, str] = {}
        if self._scene is None:
            return labels

        for item in self._scene.items():
            if isinstance(item, GardenItemMixin):
                name = getattr(item, "name", "") or ""
                obj_type = getattr(item, "object_type", None)
                type_name = obj_type.value if obj_type else ""
                label = name if name else type_name if type_name else self.tr("Object")
                labels[item.item_id] = label
        return labels

    def _is_satisfied(self, constraint: Constraint) -> bool:
        """Check whether a constraint is satisfied (within 1 cm tolerance)."""
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

    def _on_delete_all(self) -> None:
        """Handle Delete All button — emit delete for every constraint."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            cid_str = item.data(Qt.ItemDataRole.UserRole) if item else None
            if cid_str:
                self.constraint_delete_requested.emit(UUID(cid_str))
