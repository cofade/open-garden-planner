"""Constraint tool for creating distance constraints between objects."""

from __future__ import annotations

from PyQt6.QtCore import QCoreApplication, QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
    QLabel,
    QVBoxLayout,
)

from open_garden_planner.core.commands import AddConstraintCommand
from open_garden_planner.core.constraints import AnchorRef
from open_garden_planner.core.measure_snapper import (
    AnchorPoint,
    find_nearest_anchor,
    get_anchor_points,
)
from open_garden_planner.core.tools.base_tool import BaseTool, ToolType
from open_garden_planner.ui.canvas.items import GardenItemMixin

# Visual constants
ANCHOR_INDICATOR_RADIUS = 6.0
ANCHOR_INDICATOR_COLOR = QColor(255, 140, 0, 200)  # Orange
ANCHOR_SELECTED_COLOR = QColor(0, 120, 255, 220)  # Blue
SNAP_INDICATOR_COLOR = QColor(0, 180, 0, 200)  # Green
PREVIEW_LINE_COLOR = QColor(0, 120, 255, 160)  # Semi-transparent blue
PEN_WIDTH = 2.5


class DistanceInputDialog(QDialog):
    """Dialog for entering the target distance for a constraint."""

    def __init__(
        self,
        current_distance_cm: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            QCoreApplication.translate("DistanceInputDialog", "Set Constraint Distance")
        )
        self.setMinimumWidth(280)

        layout = QVBoxLayout(self)

        label = QLabel(
            QCoreApplication.translate(
                "DistanceInputDialog",
                "Enter the target distance (meters):",
            )
        )
        layout.addWidget(label)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.01, 999.99)
        self._spin.setDecimals(2)
        self._spin.setSuffix(" m")
        self._spin.setSingleStep(0.10)
        # Pre-fill with current distance converted to meters
        self._spin.setValue(current_distance_cm / 100.0)
        self._spin.selectAll()
        layout.addWidget(self._spin)

        current_label = QLabel(
            QCoreApplication.translate(
                "DistanceInputDialog",
                "Current distance: {distance:.2f} m",
            ).format(distance=current_distance_cm / 100.0)
        )
        current_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(current_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def distance_cm(self) -> float:
        """Return the entered distance in scene units (cm)."""
        return self._spin.value() * 100.0


class ConstraintTool(BaseTool):
    """Tool for creating distance constraints between object anchors.

    Workflow:
    1. Hover over objects to see anchor indicators (small circles).
    2. Click an anchor on object A to select it.
    3. Hover and click an anchor on object B.
    4. A dialog appears to set the target distance.
    5. The constraint is added to the ConstraintGraph via undo/redo.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._anchor_a: AnchorPoint | None = None
        self._current_hover: AnchorPoint | None = None
        self._graphics_items: list = []
        self._anchor_indicators: list = []
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_text: QGraphicsTextItem | None = None
        self._selected_marker: QGraphicsEllipseItem | None = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("ConstraintTool", "Constraint")

    @property
    def shortcut(self) -> str:
        return "K"

    @property
    def cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.CrossCursor)

    def activate(self) -> None:
        super().activate()
        self._reset()

    def deactivate(self) -> None:
        super().deactivate()
        self._reset()

    def _reset(self) -> None:
        """Clear all state and visuals."""
        self._anchor_a = None
        self._current_hover = None
        self._clear_all_visuals()

    def _clear_all_visuals(self) -> None:
        """Remove all graphics items from the scene."""
        scene = self._view.scene()
        if not scene:
            return
        for item in self._graphics_items:
            if item.scene():
                scene.removeItem(item)
        self._graphics_items.clear()
        self._clear_anchor_indicators()
        self._preview_line = None
        self._preview_text = None
        self._selected_marker = None

    def _clear_anchor_indicators(self) -> None:
        """Remove hover anchor indicators."""
        scene = self._view.scene()
        if not scene:
            return
        for item in self._anchor_indicators:
            if item.scene():
                scene.removeItem(item)
        self._anchor_indicators.clear()

    def _show_anchor_indicators(self, scene_pos: QPointF) -> None:
        """Show anchor indicators on objects near the mouse position.

        Displays small circles on all anchors of the hovered object.
        """
        scene = self._view.scene()
        if not scene:
            return

        self._clear_anchor_indicators()

        # Find which item is under the mouse
        items_at = scene.items(scene_pos)
        hovered_item = None
        for item in items_at:
            if isinstance(item, GardenItemMixin) and item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                    hovered_item = item
                    break

        if hovered_item is None:
            return

        # Show all anchors for this item
        anchors = get_anchor_points(hovered_item)
        for anchor in anchors:
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(
                anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2
            )
            pen = QPen(ANCHOR_INDICATOR_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._anchor_indicators.append(indicator)

    def _find_nearest_anchor(self, scene_pos: QPointF) -> AnchorPoint | None:
        """Find the nearest anchor to the scene position."""
        scene = self._view.scene()
        if not scene:
            return None
        return find_nearest_anchor(scene_pos, scene.items())

    def _show_selected_anchor(self, anchor: AnchorPoint) -> None:
        """Show a filled marker at the selected anchor."""
        scene = self._view.scene()
        if not scene:
            return
        r = ANCHOR_INDICATOR_RADIUS + 2
        rect = QRectF(
            anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2
        )
        pen = QPen(ANCHOR_SELECTED_COLOR, PEN_WIDTH)
        self._selected_marker = scene.addEllipse(rect, pen)
        self._selected_marker.setZValue(1003)
        self._graphics_items.append(self._selected_marker)

    def _update_preview(self, end_pos: QPointF) -> None:
        """Update the preview dimension line from anchor A to the current pos."""
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point

        # Remove old preview
        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        # Draw preview line
        pen = QPen(PREVIEW_LINE_COLOR, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, end_pos), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        # Show distance text
        distance_cm = QLineF(start, end_pos).length()
        distance_m = distance_cm / 100.0
        text = f"{distance_m:.2f} m"

        mid_x = (start.x() + end_pos.x()) / 2
        mid_y = (start.y() + end_pos.y()) / 2

        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(ANCHOR_SELECTED_COLOR)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self._preview_text.setFont(font)

        text_rect = self._preview_text.boundingRect()
        self._preview_text.setPos(
            mid_x - text_rect.width() / 2,
            mid_y - text_rect.height() / 2,
        )
        self._preview_text.setFlag(
            QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations
        )
        self._preview_text.setZValue(1002)
        self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        anchor = self._find_nearest_anchor(scene_pos)
        if anchor is None:
            return True  # Consume but do nothing (no anchor near click)

        if self._anchor_a is None:
            # First click: select anchor A
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._show_selected_anchor(anchor)
            return True
        else:
            # Second click: select anchor B and open dialog
            anchor_b = anchor

            # Don't allow constraining same anchor to itself
            if (
                isinstance(self._anchor_a.item, GardenItemMixin)
                and isinstance(anchor_b.item, GardenItemMixin)
                and self._anchor_a.item.item_id == anchor_b.item.item_id
                and self._anchor_a.anchor_type == anchor_b.anchor_type
            ):
                return True

            # Calculate current distance
            dist = QLineF(self._anchor_a.point, anchor_b.point).length()

            # Show distance input dialog
            dialog = DistanceInputDialog(dist, self._view)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                target_cm = dialog.distance_cm()
                self._create_constraint(self._anchor_a, anchor_b, target_cm)

            self._reset()
            return True

    def _create_constraint(
        self,
        anchor_a: AnchorPoint,
        anchor_b: AnchorPoint,
        target_distance: float,
    ) -> None:
        """Create a constraint via the command pattern."""
        scene = self._view.scene()
        if not scene:
            return

        # Build AnchorRef from AnchorPoint
        if not isinstance(anchor_a.item, GardenItemMixin) or not isinstance(
            anchor_b.item, GardenItemMixin
        ):
            return

        ref_a = AnchorRef(
            item_id=anchor_a.item.item_id,
            anchor_type=anchor_a.anchor_type,
            anchor_index=anchor_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=anchor_b.item.item_id,
            anchor_type=anchor_b.anchor_type,
            anchor_index=anchor_b.anchor_index,
        )

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=target_distance,
        )
        self._view.command_manager.execute(command)

        # Move items immediately if target_distance differs from current distance
        self._view.apply_constraint_solver()

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        # Show anchor indicators on hovered objects
        self._show_anchor_indicators(scene_pos)

        # Highlight nearest snappable anchor
        anchor = self._find_nearest_anchor(scene_pos)
        self._current_hover = anchor

        # Update preview line if we have anchor A selected
        if self._anchor_a is not None:
            end = anchor.point if anchor else scene_pos
            self._update_preview(end)

        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self._reset()
            return True
        return False

    def cancel(self) -> None:
        self._reset()
