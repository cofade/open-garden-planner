"""Constraint tools for creating distance and alignment constraints between objects."""

from __future__ import annotations

import math

from PyQt6.QtCore import QCoreApplication, QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QCursor, QFont, QKeyEvent, QMouseEvent, QPen
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsTextItem,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from open_garden_planner.core.commands import AddConstraintCommand
from open_garden_planner.core.constraints import AnchorRef, ConstraintType
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
PREVIEW_LINE_COLOR = QColor(0, 120, 255, 160)  # Semi-transparent blue for distance
PREVIEW_H_COLOR = QColor(180, 0, 200, 200)      # Purple for horizontal
PREVIEW_V_COLOR = QColor(0, 160, 80, 200)       # Green for vertical
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
    3. Click an anchor on object B.
    4. A dialog appears to set the target distance.
    5. The constraint is added via undo/redo.
    """

    # Subclasses override these to fix the constraint type and visual style
    _CONSTRAINT_TYPE: ConstraintType = ConstraintType.DISTANCE
    _PREVIEW_COLOR: QColor = PREVIEW_LINE_COLOR

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
        return QCoreApplication.translate("ConstraintTool", "Distance Constraint")

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
        """Show anchor indicators on objects near the mouse position."""
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        scene = self._view.scene()
        if not scene:
            return

        self._clear_anchor_indicators()

        items_at = scene.items(scene_pos)
        hovered_item = None
        for item in items_at:
            is_target = isinstance(item, (GardenItemMixin, ConstructionLineItem, ConstructionCircleItem))
            if is_target and item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                hovered_item = item
                break

        if hovered_item is None:
            return

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
        """Update the preview line from anchor A to the current pos."""
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point
        color = self._PREVIEW_COLOR

        # Remove old preview items
        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        # For alignment constraints, snap the preview line to the constraint axis
        if self._CONSTRAINT_TYPE == ConstraintType.HORIZONTAL:
            snapped_end = QPointF(end_pos.x(), start.y())
        elif self._CONSTRAINT_TYPE == ConstraintType.VERTICAL:
            snapped_end = QPointF(start.x(), end_pos.y())
        else:
            snapped_end = end_pos

        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, snapped_end), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        # Distance or alignment label
        if self._CONSTRAINT_TYPE == ConstraintType.HORIZONTAL:
            text = QCoreApplication.translate("ConstraintTool", "≡ H (same Y)")
        elif self._CONSTRAINT_TYPE == ConstraintType.VERTICAL:
            text = QCoreApplication.translate("ConstraintTool", "≡ V (same X)")
        else:
            distance_cm = QLineF(start, end_pos).length()
            text = f"{distance_cm / 100.0:.2f} m"

        mid_x = (start.x() + snapped_end.x()) / 2
        mid_y = (start.y() + snapped_end.y()) / 2

        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(color)
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
            # Second click: select anchor B and create constraint
            anchor_b = anchor

            # Don't allow constraining same anchor to itself
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor_b.item, "item_id")
                and self._anchor_a.item.item_id == anchor_b.item.item_id
                and self._anchor_a.anchor_type == anchor_b.anchor_type
            ):
                return True

            if self._CONSTRAINT_TYPE == ConstraintType.DISTANCE:
                dist = QLineF(self._anchor_a.point, anchor_b.point).length()
                dialog = DistanceInputDialog(dist, self._view)
                if dialog.exec() == QDialog.DialogCode.Accepted:
                    target_cm = dialog.distance_cm()
                    self._create_constraint(self._anchor_a, anchor_b, target_cm)
            else:
                # Alignment constraints need no dialog
                self._create_constraint(self._anchor_a, anchor_b, 0.0)

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

        if not hasattr(anchor_a.item, "item_id") or not hasattr(anchor_b.item, "item_id"):
            return

        ref_a = AnchorRef(
            item_id=anchor_a.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_a.anchor_type,
            anchor_index=anchor_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=anchor_b.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_b.anchor_type,
            anchor_index=anchor_b.anchor_index,
        )

        if not self._view.is_constraint_feasible(
            ref_a, ref_b, target_distance, self._CONSTRAINT_TYPE
        ):
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate("ConstraintTool", "Conflicting Constraint"),
                QCoreApplication.translate(
                    "ConstraintTool",
                    "This constraint conflicts with existing constraints "
                    "and cannot be applied. The existing constraints are unchanged.",
                ),
            )
            return

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=target_distance,
            constraint_type=self._CONSTRAINT_TYPE,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_anchor_indicators(scene_pos)
        anchor = self._find_nearest_anchor(scene_pos)
        self._current_hover = anchor

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


class HorizontalConstraintTool(ConstraintTool):
    """Tool for creating horizontal alignment constraints (same Y coordinate)."""

    _CONSTRAINT_TYPE = ConstraintType.HORIZONTAL
    _PREVIEW_COLOR = PREVIEW_H_COLOR

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_HORIZONTAL

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("HorizontalConstraintTool", "Horizontal Constraint")

    @property
    def shortcut(self) -> str:
        return ""


class VerticalConstraintTool(ConstraintTool):
    """Tool for creating vertical alignment constraints (same X coordinate)."""

    _CONSTRAINT_TYPE = ConstraintType.VERTICAL
    _PREVIEW_COLOR = PREVIEW_V_COLOR

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_VERTICAL

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("VerticalConstraintTool", "Vertical Constraint")

    @property
    def shortcut(self) -> str:
        return ""


PREVIEW_COINCIDENT_COLOR = QColor(0, 160, 200, 200)  # Teal for coincident


class CoincidentConstraintTool(ConstraintTool):
    """Tool for creating coincident constraints (merge two anchor points to same location).

    Workflow:
    1. Hover over objects to see anchor indicators (small circles).
    2. Click an anchor on object A to select it.
    3. Click an anchor on object B — constraint is created immediately (no dialog).
    """

    _CONSTRAINT_TYPE = ConstraintType.COINCIDENT
    _PREVIEW_COLOR = PREVIEW_COINCIDENT_COLOR

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_COINCIDENT

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("CoincidentConstraintTool", "Coincident Constraint")

    @property
    def shortcut(self) -> str:
        return ""

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        """Override to skip the distance dialog — create constraint immediately."""
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        anchor = self._find_nearest_anchor(scene_pos)
        if anchor is None:
            return True

        if self._anchor_a is None:
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._show_selected_anchor(anchor)
            return True
        else:
            anchor_b = anchor

            # Don't allow constraining same anchor to itself
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor_b.item, "item_id")
                and self._anchor_a.item.item_id == anchor_b.item.item_id
                and self._anchor_a.anchor_type == anchor_b.anchor_type
            ):
                return True

            # Create coincident constraint immediately (no dialog needed)
            self._create_constraint(self._anchor_a, anchor_b, 0.0)
            self._reset()
            return True

    def _update_preview(self, end_pos: QPointF) -> None:
        """Override to show a coincident preview with a special marker."""
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point
        color = self._PREVIEW_COLOR

        # Remove old preview items
        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, end_pos), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        text = QCoreApplication.translate("CoincidentConstraintTool", "⦿ Coincident")

        mid_x = (start.x() + end_pos.x()) / 2
        mid_y = (start.y() + end_pos.y()) / 2

        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(color)
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


# Angle constraint visual constants
PREVIEW_ANGLE_COLOR = QColor(200, 100, 0, 200)  # Orange for angle


class AngleInputDialog(QDialog):
    """Dialog for entering the target angle for an angle constraint.

    Provides common presets (90°, 45°, 60°, 120°) as quick buttons plus
    a numeric spin box for custom angles.
    """

    _PRESETS = [45.0, 60.0, 90.0, 120.0]

    def __init__(self, current_angle_deg: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            QCoreApplication.translate("AngleInputDialog", "Set Angle Constraint")
        )
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)

        label = QLabel(
            QCoreApplication.translate("AngleInputDialog", "Enter the target angle (degrees):")
        )
        layout.addWidget(label)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(1.0, 179.0)
        self._spin.setDecimals(1)
        self._spin.setSuffix("°")
        self._spin.setSingleStep(1.0)
        self._spin.setValue(round(current_angle_deg, 1))
        self._spin.selectAll()
        layout.addWidget(self._spin)

        current_label = QLabel(
            QCoreApplication.translate(
                "AngleInputDialog", "Current angle: {angle:.1f}°"
            ).format(angle=current_angle_deg)
        )
        current_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(current_label)

        # Preset buttons row
        preset_layout = QHBoxLayout()
        preset_label = QLabel(QCoreApplication.translate("AngleInputDialog", "Presets:"))
        preset_layout.addWidget(preset_label)
        for angle in self._PRESETS:
            btn = QPushButton(f"{angle:.0f}°")
            btn.setFixedWidth(50)
            btn.clicked.connect(lambda _checked, a=angle: self._spin.setValue(a))
            preset_layout.addWidget(btn)
        layout.addLayout(preset_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def angle_degrees(self) -> float:
        """Return the entered angle in degrees."""
        return self._spin.value()


class AngleConstraintTool(BaseTool):
    """Tool for creating angle constraints between three object anchors.

    Workflow:
    1. Hover over objects to see anchor indicators (small circles).
    2. Click an anchor on object A (first ray endpoint).
    3. Click an anchor on object B (the vertex).
    4. Click an anchor on object C (second ray endpoint).
    5. A dialog appears to set the target angle (presets: 45°, 60°, 90°, 120°).
    6. The constraint is added via undo/redo.

    The angle constraint fixes the angle A-B-C at vertex B.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._anchor_a: AnchorPoint | None = None
        self._anchor_b: AnchorPoint | None = None  # vertex
        self._graphics_items: list = []
        self._anchor_indicators: list = []
        self._preview_line_a: QGraphicsLineItem | None = None
        self._preview_line_b: QGraphicsLineItem | None = None
        self._preview_text: QGraphicsTextItem | None = None
        self._selected_marker_a: QGraphicsEllipseItem | None = None
        self._selected_marker_b: QGraphicsEllipseItem | None = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_ANGLE

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("AngleConstraintTool", "Angle Constraint")

    @property
    def shortcut(self) -> str:
        return ""

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
        self._anchor_a = None
        self._anchor_b = None
        self._clear_all_visuals()

    def _clear_all_visuals(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._graphics_items:
            if item.scene():
                scene.removeItem(item)
        self._graphics_items.clear()
        self._clear_anchor_indicators()
        self._preview_line_a = None
        self._preview_line_b = None
        self._preview_text = None
        self._selected_marker_a = None
        self._selected_marker_b = None

    def _clear_anchor_indicators(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._anchor_indicators:
            if item.scene():
                scene.removeItem(item)
        self._anchor_indicators.clear()

    def _show_anchor_indicators(self, scene_pos: QPointF) -> None:
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        scene = self._view.scene()
        if not scene:
            return
        self._clear_anchor_indicators()
        items_at = scene.items(scene_pos)
        hovered_item = None
        for item in items_at:
            is_target = isinstance(item, (GardenItemMixin, ConstructionLineItem, ConstructionCircleItem))
            if is_target and item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                hovered_item = item
                break
        if hovered_item is None:
            return
        from open_garden_planner.core.measure_snapper import get_anchor_points
        for anchor in get_anchor_points(hovered_item):
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
            pen = QPen(ANCHOR_INDICATOR_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._anchor_indicators.append(indicator)

    def _find_nearest_anchor(self, scene_pos: QPointF) -> AnchorPoint | None:
        scene = self._view.scene()
        if not scene:
            return None
        return find_nearest_anchor(scene_pos, scene.items())

    def _show_selected_marker(self, anchor: AnchorPoint, color: QColor) -> QGraphicsEllipseItem:
        scene = self._view.scene()
        r = ANCHOR_INDICATOR_RADIUS + 2
        rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
        pen = QPen(color, PEN_WIDTH)
        marker = scene.addEllipse(rect, pen)
        marker.setZValue(1003)
        self._graphics_items.append(marker)
        return marker

    def _update_preview(self, mouse_pos: QPointF) -> None:
        """Update preview lines showing the angle being formed."""
        scene = self._view.scene()
        if not scene:
            return
        color = PREVIEW_ANGLE_COLOR

        # Remove old preview items
        for attr in ("_preview_line_a", "_preview_line_b", "_preview_text"):
            item = getattr(self, attr)
            if item is not None and item.scene():
                scene.removeItem(item)
                if item in self._graphics_items:
                    self._graphics_items.remove(item)
            setattr(self, attr, None)

        pen = QPen(color, 2, Qt.PenStyle.DashLine)

        if self._anchor_a is None:
            return

        if self._anchor_b is None:
            # Phase 1: show line from A to mouse
            self._preview_line_a = scene.addLine(
                QLineF(self._anchor_a.point, mouse_pos), pen
            )
            self._preview_line_a.setZValue(1001)
            self._graphics_items.append(self._preview_line_a)
            return

        # Phase 2: anchor_a and anchor_b set, show both rays from B
        vertex = self._anchor_b.point
        end_a = self._anchor_a.point

        # Nearest anchor for C or mouse position
        nearest = self._find_nearest_anchor(mouse_pos)
        end_c = nearest.point if nearest else mouse_pos

        self._preview_line_a = scene.addLine(QLineF(vertex, end_a), pen)
        self._preview_line_a.setZValue(1001)
        self._graphics_items.append(self._preview_line_a)

        self._preview_line_b = scene.addLine(QLineF(vertex, end_c), pen)
        self._preview_line_b.setZValue(1001)
        self._graphics_items.append(self._preview_line_b)

        # Compute and display current angle
        ba_x, ba_y = end_a.x() - vertex.x(), end_a.y() - vertex.y()
        bc_x, bc_y = end_c.x() - vertex.x(), end_c.y() - vertex.y()
        ba_len = math.sqrt(ba_x ** 2 + ba_y ** 2)
        bc_len = math.sqrt(bc_x ** 2 + bc_y ** 2)
        if ba_len > 1e-6 and bc_len > 1e-6:
            cos_val = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)))
            angle_deg = math.degrees(math.acos(cos_val))
            text = f"{angle_deg:.1f}°"
            self._preview_text = scene.addText(text)
            self._preview_text.setDefaultTextColor(color)
            font = QFont()
            font.setPointSize(11)
            font.setBold(True)
            self._preview_text.setFont(font)
            self._preview_text.setFlag(
                QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations
            )
            self._preview_text.setZValue(1002)
            text_rect = self._preview_text.boundingRect()
            self._preview_text.setPos(
                vertex.x() - text_rect.width() / 2,
                vertex.y() - text_rect.height() - 10,
            )
            self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        anchor = self._find_nearest_anchor(scene_pos)
        if anchor is None:
            return True

        if self._anchor_a is None:
            # First click: select anchor A
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._selected_marker_a = self._show_selected_marker(
                anchor, ANCHOR_SELECTED_COLOR
            )
            return True

        if self._anchor_b is None:
            # Second click: select anchor B (vertex)
            # Must be on a different item from A
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor.item, "item_id")
                and self._anchor_a.item.item_id == anchor.item.item_id
            ):
                return True
            self._anchor_b = anchor
            self._selected_marker_b = self._show_selected_marker(
                anchor, QColor(0, 180, 0, 220)  # Green for vertex
            )
            return True

        # Third click: select anchor C and create constraint
        anchor_c = anchor
        if not (
            hasattr(self._anchor_a.item, "item_id")
            and hasattr(self._anchor_b.item, "item_id")
            and hasattr(anchor_c.item, "item_id")
        ):
            self._reset()
            return True

        # All three must be different items
        ids = {
            self._anchor_a.item.item_id,
            self._anchor_b.item.item_id,
            anchor_c.item.item_id,
        }
        if len(ids) < 3:  # noqa: PLR2004
            return True

        # Compute current angle at vertex B
        vertex = self._anchor_b.point
        end_a = self._anchor_a.point
        end_c = anchor_c.point
        ba_x, ba_y = end_a.x() - vertex.x(), end_a.y() - vertex.y()
        bc_x, bc_y = end_c.x() - vertex.x(), end_c.y() - vertex.y()
        ba_len = math.sqrt(ba_x ** 2 + ba_y ** 2)
        bc_len = math.sqrt(bc_x ** 2 + bc_y ** 2)
        if ba_len < 1e-6 or bc_len < 1e-6:
            self._reset()
            return True

        cos_val = max(-1.0, min(1.0, (ba_x * bc_x + ba_y * bc_y) / (ba_len * bc_len)))
        current_angle_deg = math.degrees(math.acos(cos_val))

        dialog = AngleInputDialog(current_angle_deg, self._view)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            target_deg = dialog.angle_degrees()
            self._create_angle_constraint(self._anchor_a, self._anchor_b, anchor_c, target_deg)

        self._reset()
        return True

    def _create_angle_constraint(
        self,
        anchor_a: AnchorPoint,
        anchor_b: AnchorPoint,
        anchor_c: AnchorPoint,
        target_deg: float,
    ) -> None:
        """Create an angle constraint via the command pattern."""
        scene = self._view.scene()
        if not scene:
            return

        ref_a = AnchorRef(
            item_id=anchor_a.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_a.anchor_type,
            anchor_index=anchor_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=anchor_b.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_b.anchor_type,
            anchor_index=anchor_b.anchor_index,
        )
        ref_c = AnchorRef(
            item_id=anchor_c.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_c.anchor_type,
            anchor_index=anchor_c.anchor_index,
        )

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=target_deg,
            constraint_type=ConstraintType.ANGLE,
            anchor_c=ref_c,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_anchor_indicators(scene_pos)
        self._update_preview(scene_pos)
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


# Symmetry constraint visual constants
PREVIEW_SYMMETRY_COLOR = QColor(140, 0, 180, 200)  # Purple for symmetry


class SymmetryAxisDialog(QDialog):
    """Dialog for choosing the symmetry axis (horizontal or vertical)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            QCoreApplication.translate("SymmetryAxisDialog", "Set Symmetry Axis")
        )
        self.setMinimumWidth(260)
        layout = QVBoxLayout(self)

        label = QLabel(
            QCoreApplication.translate("SymmetryAxisDialog", "Mirror across axis:")
        )
        layout.addWidget(label)

        self._combo = QComboBox()
        self._combo.addItem(
            QCoreApplication.translate(
                "SymmetryAxisDialog", "Horizontal axis (mirror top/bottom)"
            ),
            "H",
        )
        self._combo.addItem(
            QCoreApplication.translate(
                "SymmetryAxisDialog", "Vertical axis (mirror left/right)"
            ),
            "V",
        )
        layout.addWidget(self._combo)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def axis(self) -> str:
        """Return 'H' for horizontal axis or 'V' for vertical axis."""
        return self._combo.currentData()


class SymmetryConstraintTool(BaseTool):
    """Tool for creating symmetry (mirror) constraints between two object anchors.

    Workflow:
    1. Hover to see anchor indicators on objects.
    2. Click anchor A on object A.
    3. Click anchor B on object B.
    4. Choose axis (H or V) in dialog.
    5. The symmetry constraint is added: B mirrors A across the midpoint axis.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._anchor_a: AnchorPoint | None = None
        self._graphics_items: list = []
        self._anchor_indicators: list = []
        self._preview_line: QGraphicsLineItem | None = None
        self._preview_text: QGraphicsTextItem | None = None
        self._selected_marker: QGraphicsEllipseItem | None = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_SYMMETRY

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("SymmetryConstraintTool", "Symmetry Constraint")

    @property
    def shortcut(self) -> str:
        return ""

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
        self._anchor_a = None
        self._clear_all_visuals()

    def _clear_all_visuals(self) -> None:
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
        scene = self._view.scene()
        if not scene:
            return
        for item in self._anchor_indicators:
            if item.scene():
                scene.removeItem(item)
        self._anchor_indicators.clear()

    def _show_anchor_indicators(self, scene_pos: QPointF) -> None:
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        scene = self._view.scene()
        if not scene:
            return
        self._clear_anchor_indicators()
        items_at = scene.items(scene_pos)
        hovered_item = None
        for item in items_at:
            is_target = isinstance(item, (GardenItemMixin, ConstructionLineItem, ConstructionCircleItem))
            if is_target and item.flags() & item.GraphicsItemFlag.ItemIsSelectable:
                hovered_item = item
                break
        if hovered_item is None:
            return
        for anchor in get_anchor_points(hovered_item):
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
            pen = QPen(ANCHOR_INDICATOR_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._anchor_indicators.append(indicator)

    def _find_nearest_anchor(self, scene_pos: QPointF) -> AnchorPoint | None:
        scene = self._view.scene()
        if not scene:
            return None
        return find_nearest_anchor(scene_pos, scene.items())

    def _show_selected_anchor(self, anchor: AnchorPoint) -> None:
        scene = self._view.scene()
        if not scene:
            return
        r = ANCHOR_INDICATOR_RADIUS + 2
        rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
        pen = QPen(ANCHOR_SELECTED_COLOR, PEN_WIDTH)
        self._selected_marker = scene.addEllipse(rect, pen)
        self._selected_marker.setZValue(1003)
        self._graphics_items.append(self._selected_marker)

    def _update_preview(self, end_pos: QPointF) -> None:
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point
        color = PREVIEW_SYMMETRY_COLOR

        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, end_pos), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        text = QCoreApplication.translate("SymmetryConstraintTool", "\u27fa SYM")
        mid_x = (start.x() + end_pos.x()) / 2
        mid_y = (start.y() + end_pos.y()) / 2
        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(color)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self._preview_text.setFont(font)
        text_rect = self._preview_text.boundingRect()
        self._preview_text.setPos(
            mid_x - text_rect.width() / 2, mid_y - text_rect.height() / 2
        )
        self._preview_text.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self._preview_text.setZValue(1002)
        self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        anchor = self._find_nearest_anchor(scene_pos)
        if anchor is None:
            return True

        if self._anchor_a is None:
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._show_selected_anchor(anchor)
            return True

        # Second click: select anchor B
        anchor_b = anchor
        if (
            hasattr(self._anchor_a.item, "item_id")
            and hasattr(anchor_b.item, "item_id")
            and self._anchor_a.item.item_id == anchor_b.item.item_id
        ):
            return True  # Same item — skip

        dialog = SymmetryAxisDialog(self._view)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            axis = dialog.axis()
            self._create_symmetry_constraint(self._anchor_a, anchor_b, axis)

        self._reset()
        return True

    def _create_symmetry_constraint(
        self,
        anchor_a: AnchorPoint,
        anchor_b: AnchorPoint,
        axis: str,
    ) -> None:
        """Create a symmetry constraint via the command pattern.

        The axis position is set to the midpoint between the two anchors
        at creation time, so the constraint is immediately satisfied.
        """
        scene = self._view.scene()
        if not scene:
            return
        if not hasattr(anchor_a.item, "item_id") or not hasattr(anchor_b.item, "item_id"):
            return

        # Compute axis coordinate from the midpoint at creation time
        if axis == "H":
            axis_pos = (anchor_a.point.y() + anchor_b.point.y()) / 2.0
            constraint_type = ConstraintType.SYMMETRY_HORIZONTAL
        else:
            axis_pos = (anchor_a.point.x() + anchor_b.point.x()) / 2.0
            constraint_type = ConstraintType.SYMMETRY_VERTICAL

        ref_a = AnchorRef(
            item_id=anchor_a.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_a.anchor_type,
            anchor_index=anchor_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=anchor_b.item.item_id,  # type: ignore[union-attr]
            anchor_type=anchor_b.anchor_type,
            anchor_index=anchor_b.anchor_index,
        )

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=axis_pos,
            constraint_type=constraint_type,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_anchor_indicators(scene_pos)
        if self._anchor_a is not None:
            anchor = self._find_nearest_anchor(scene_pos)
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
