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


# ─── Parallel constraint ──────────────────────────────────────────────────────

PREVIEW_PARALLEL_COLOR = QColor(20, 160, 100, 200)   # Green for parallel


def _collect_rotation_chain(scene_items, graph, start_item, delta: float, exclude_id) -> list:
    """BFS through PARALLEL/PERPENDICULAR constraints from *start_item*.

    Returns a list of ``(item, old_rotation, new_rotation, apply_fn)`` tuples for every
    item reachable via existing rotation constraints that should co-rotate by *delta*.
    *exclude_id* is the item_id of the reference (fixed) item — it is never rotated.

    The propagation rule: rotating any item in a PARALLEL or PERPENDICULAR chain by
    *delta* preserves the relative angle between all pairs, so every free connected item
    must rotate by the same *delta*.
    """
    from collections import deque

    from open_garden_planner.core.constraints import ConstraintType

    rotation_types = {ConstraintType.PARALLEL, ConstraintType.PERPENDICULAR}

    # Build a quick id → scene-item map
    item_by_id: dict = {}
    for si in scene_items:
        if hasattr(si, "item_id") and hasattr(si, "_apply_rotation"):
            item_by_id[si.item_id] = si

    visited = {start_item.item_id, exclude_id}
    queue: deque = deque([start_item])
    chain: list = []

    while queue:
        current = queue.popleft()
        for c in graph.get_item_constraints(current.item_id):
            if c.constraint_type not in rotation_types:
                continue
            # Find the other item in this constraint
            other_id = (
                c.anchor_b.item_id
                if c.anchor_a.item_id == current.item_id
                else c.anchor_a.item_id
            )
            if other_id in visited:
                continue
            visited.add(other_id)
            other_item = item_by_id.get(other_id)
            if other_item is None:
                continue
            old_rot = getattr(other_item, "rotation_angle", 0.0)
            chain.append((other_item, old_rot, old_rot + delta, lambda it, ang: it._apply_rotation(ang)))
            queue.append(other_item)

    return chain


def _compute_edge_scene_angle(edge_anchor):
    """Compute the scene angle (degrees [0, 180)) of the edge identified by edge_anchor.

    Works for rectangles (EDGE_* anchors), polygons and polylines
    (EDGE_* midpoints with anchor_index = edge/segment index).
    Returns the angle in degrees [0, 180) or None if not computable.
    """
    import math as _math

    from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
    from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    item = edge_anchor.item
    anchor_type = edge_anchor.anchor_type
    anchor_index = edge_anchor.anchor_index
    anchors = get_anchor_points(item)

    if isinstance(item, RectangleItem):
        corner_map = {
            AnchorType.EDGE_TOP:    (0, 1),
            AnchorType.EDGE_BOTTOM: (2, 3),
            AnchorType.EDGE_LEFT:   (0, 2),
            AnchorType.EDGE_RIGHT:  (1, 3),
        }
        if anchor_type not in corner_map:
            return None
        i0, i1 = corner_map[anchor_type]
        corners = {a.anchor_index: a.point for a in anchors if a.anchor_type == AnchorType.CORNER}
        if i0 not in corners or i1 not in corners:
            return None
        p1, p2 = corners[i0], corners[i1]
    elif isinstance(item, PolygonItem):
        polygon = item.polygon()
        n = polygon.count()
        if n < 2:
            return None
        i = anchor_index
        p1 = item.mapToScene(polygon.at(i))
        p2 = item.mapToScene(polygon.at((i + 1) % n))
    elif isinstance(item, PolylineItem):
        pts = item.points
        i = anchor_index
        if i < 0 or i + 1 >= len(pts):
            return None
        p1 = item.mapToScene(pts[i])
        p2 = item.mapToScene(pts[i + 1])
    else:
        return None

    dx = p2.x() - p1.x()
    dy = p2.y() - p1.y()
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return None
    return _math.degrees(_math.atan2(dy, dx)) % 180.0


def _find_nearest_edge_anchor(scene_pos, scene_items):
    """Find the nearest edge-midpoint anchor (EDGE_* type) across all garden items."""
    import math as _math

    from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
    from open_garden_planner.ui.canvas.items import GardenItemMixin

    SNAP_THRESHOLD = 40.0
    best = None
    best_dist = SNAP_THRESHOLD
    edge_types = {AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM, AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT}

    for item in scene_items:
        if not isinstance(item, GardenItemMixin):
            continue
        if not (item.flags() & item.GraphicsItemFlag.ItemIsSelectable):
            continue
        for anchor in get_anchor_points(item):
            if anchor.anchor_type not in edge_types:
                continue
            dx = anchor.point.x() - scene_pos.x()
            dy = anchor.point.y() - scene_pos.y()
            dist = _math.sqrt(dx * dx + dy * dy)
            if dist < best_dist:
                best_dist = dist
                best = anchor

    return best


def _compute_equal_dimension(anchor) -> float | None:
    """Compute the relevant 'size' dimension for an EQUAL constraint anchor.

    - CircleItem + any EDGE_* → radius
    - RectangleItem + EDGE_TOP/EDGE_BOTTOM → rect width
    - RectangleItem + EDGE_LEFT/EDGE_RIGHT → rect height
    - PolygonItem / PolylineItem + EDGE_* (with index) → segment length

    Returns the dimension in scene units (cm), or None if not computable.
    """
    import math as _math

    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items import PolylineItem, RectangleItem
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    item = anchor.item
    anchor_type = anchor.anchor_type
    anchor_index = anchor.anchor_index

    if isinstance(item, CircleItem):
        return item._radius

    if isinstance(item, RectangleItem):
        rect = item.rect()
        if anchor_type in (AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM):
            return abs(rect.width())
        if anchor_type in (AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT):
            return abs(rect.height())
        return None

    if isinstance(item, PolygonItem):
        polygon = item.polygon()
        n = polygon.count()
        if n < 2:
            return None
        i = anchor_index
        p1 = item.mapToScene(polygon.at(i))
        p2 = item.mapToScene(polygon.at((i + 1) % n))
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        return _math.sqrt(dx * dx + dy * dy)

    if isinstance(item, PolylineItem):
        pts = item.points
        i = anchor_index
        if i < 0 or i + 1 >= len(pts):
            return None
        p1 = item.mapToScene(pts[i])
        p2 = item.mapToScene(pts[i + 1])
        dx, dy = p2.x() - p1.x(), p2.y() - p1.y()
        return _math.sqrt(dx * dx + dy * dy)

    return None


def _build_equal_resize_fn(item, anchor_type):
    """Return (old_size, apply_fn) for resizing item to equalize its dimension.

    apply_fn(item, new_size) resizes the item while keeping its visual center.
    Returns (None, None) if the item/anchor combination is not resizable.
    """
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items import RectangleItem
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    if isinstance(item, CircleItem):
        old_size = item._radius

        def circle_apply(it, new_r: float) -> None:
            r = it.rect()
            cx = r.x() + r.width() / 2
            cy = r.y() + r.height() / 2
            it.setRect(cx - new_r, cy - new_r, 2 * new_r, 2 * new_r)
            it._radius = new_r
            it.update_resize_handles()
            it._position_label()

        return old_size, circle_apply

    if isinstance(item, RectangleItem):
        rect = item.rect()
        if anchor_type in (AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM):
            old_size = abs(rect.width())

            def rect_width_apply(it, new_w: float) -> None:
                r = it.rect()
                scene_cx = it.pos().x() + r.x() + r.width() / 2
                new_px = scene_cx - r.x() - new_w / 2
                it._apply_resize(r.x(), r.y(), new_w, r.height(), new_px, it.pos().y())

            return old_size, rect_width_apply

        if anchor_type in (AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT):
            old_size = abs(rect.height())

            def rect_height_apply(it, new_h: float) -> None:
                r = it.rect()
                scene_cy = it.pos().y() + r.y() + r.height() / 2
                new_py = scene_cy - r.y() - new_h / 2
                it._apply_resize(r.x(), r.y(), r.width(), new_h, it.pos().x(), new_py)

            return old_size, rect_height_apply

    return None, None


def _capture_equal_partner_pre_states(source_item, scene) -> list:
    """Snapshot ALL transitively EQUAL-connected partner sizes before a resize drag.

    Performs a BFS through the full EQUAL constraint chain so that every item
    reachable from source_item (however many hops) is captured for undo bundling.

    Returns list of (partner_item, old_size, apply_fn, partner_anchor_type).
    """
    import collections  # noqa: PLC0415

    from open_garden_planner.core.constraints import ConstraintType  # noqa: PLC0415
    from open_garden_planner.ui.canvas.items import GardenItemMixin  # noqa: PLC0415

    if not hasattr(source_item, "item_id") or not hasattr(scene, "constraint_graph"):
        return []

    graph = scene.constraint_graph
    item_map = {
        it.item_id: it
        for it in scene.items()
        if isinstance(it, GardenItemMixin) and hasattr(it, "item_id")
    }

    results = []
    visited: set = {source_item.item_id}
    queue = collections.deque([source_item])

    while queue:
        current = queue.popleft()
        for c in graph.get_item_constraints(current.item_id):
            if c.constraint_type != ConstraintType.EQUAL:
                continue

            if c.anchor_a.item_id == current.item_id:
                partner_id = c.anchor_b.item_id
                partner_anchor_type = c.anchor_b.anchor_type
            else:
                partner_id = c.anchor_a.item_id
                partner_anchor_type = c.anchor_a.anchor_type

            if partner_id in visited:
                continue
            visited.add(partner_id)

            partner = item_map.get(partner_id)
            if partner is None:
                continue

            old_size, apply_fn = _build_equal_resize_fn(partner, partner_anchor_type)
            if apply_fn is None:
                continue

            results.append((partner, old_size, apply_fn, partner_anchor_type))
            queue.append(partner)

    return results


def _apply_equal_propagation_live(source_item, scene) -> None:
    """Resize ALL transitively EQUAL-connected items to match source_item's current size.

    Performs a BFS so that chains like A→B→C→D all update in one call.
    At each hop the dimension is re-computed from the just-resized item so
    that the correct dimension (width vs height vs radius) is propagated even
    when anchor types differ along the chain.

    Guard against re-entrancy before calling this.
    """
    import collections  # noqa: PLC0415

    from open_garden_planner.core.constraints import ConstraintType  # noqa: PLC0415
    from open_garden_planner.ui.canvas.items import GardenItemMixin  # noqa: PLC0415

    if not hasattr(source_item, "item_id") or not hasattr(scene, "constraint_graph"):
        return

    graph = scene.constraint_graph
    item_map = {
        it.item_id: it
        for it in scene.items()
        if isinstance(it, GardenItemMixin) and hasattr(it, "item_id")
    }

    class _AP:
        def __init__(self, item, anchor_type, anchor_index: int) -> None:
            self.item = item
            self.anchor_type = anchor_type
            self.anchor_index = anchor_index

    # BFS: each entry is the item we just finished resizing.
    # We compute its current dimension for each outgoing EQUAL constraint and
    # propagate to partners that haven't been updated yet.
    visited: set = {source_item.item_id}
    queue = collections.deque([source_item])

    while queue:
        current = queue.popleft()
        for c in graph.get_item_constraints(current.item_id):
            if c.constraint_type != ConstraintType.EQUAL:
                continue

            if c.anchor_a.item_id == current.item_id:
                src_type = c.anchor_a.anchor_type
                src_idx = c.anchor_a.anchor_index
                partner_id = c.anchor_b.item_id
                partner_type = c.anchor_b.anchor_type
            else:
                src_type = c.anchor_b.anchor_type
                src_idx = c.anchor_b.anchor_index
                partner_id = c.anchor_a.item_id
                partner_type = c.anchor_a.anchor_type

            if partner_id in visited:
                continue

            # Compute the current item's dimension for this constraint's port.
            # If the dimension doesn't match what was propagated (e.g. a rectangle
            # whose height is being queried but only its width changed), skip.
            new_size = _compute_equal_dimension(_AP(current, src_type, src_idx))
            if new_size is None:
                continue

            partner = item_map.get(partner_id)
            if partner is None:
                continue

            _, apply_fn = _build_equal_resize_fn(partner, partner_type)
            if apply_fn is None:
                continue

            apply_fn(partner, new_size)
            visited.add(partner_id)
            queue.append(partner)


# ─── Equal-size constraint ─────────────────────────────────────────────────────

PREVIEW_EQUAL_COLOR = QColor(200, 100, 0, 200)   # Amber for equal-size constraint


class EqualConstraintTool(BaseTool):
    """Tool for creating equal-size constraints between two items.

    Workflow:
    1. Hover over an item — edge midpoints are highlighted (amber circles).
    2. Click an edge midpoint on object A (reference):
       - EDGE_TOP/BOTTOM on rectangle → locks width
       - EDGE_LEFT/RIGHT on rectangle → locks height
       - any EDGE_* on circle → locks radius
       - EDGE_* (with index) on polygon/polyline → locks segment length
    3. Click an edge midpoint on object B — object B is immediately resized so
       its corresponding dimension equals object A's dimension.
    4. The constraint is stored with undo/redo bundling the resize.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._anchor_a = None
        self._graphics_items: list = []
        self._edge_indicators: list = []
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_EQUAL

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("EqualConstraintTool", "Equal Size Constraint")

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
        self._clear_edge_indicators()
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    def _clear_edge_indicators(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._edge_indicators:
            if item.scene():
                scene.removeItem(item)
        self._edge_indicators.clear()

    def _show_edge_indicators(self, scene_pos: QPointF) -> None:
        from open_garden_planner.core.measure_snapper import AnchorType  # noqa: PLC0415

        scene = self._view.scene()
        if not scene:
            return
        self._clear_edge_indicators()

        edge_types = {AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM,
                      AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT}

        items_at = scene.items(scene_pos)
        hovered = None
        for it in items_at:
            if isinstance(it, GardenItemMixin) and it.flags() & it.GraphicsItemFlag.ItemIsSelectable:
                hovered = it
                break

        if hovered is None:
            return

        for anchor in get_anchor_points(hovered):
            if anchor.anchor_type not in edge_types:
                continue
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
            pen = QPen(PREVIEW_EQUAL_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._edge_indicators.append(indicator)

    def _show_selected_anchor(self, anchor) -> None:
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
        color = PREVIEW_EQUAL_COLOR

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

        text = QCoreApplication.translate("EqualConstraintTool", "= Equal")
        mid_x = (start.x() + end_pos.x()) / 2
        mid_y = (start.y() + end_pos.y()) / 2
        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(color)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self._preview_text.setFont(font)
        text_rect = self._preview_text.boundingRect()
        self._preview_text.setPos(mid_x - text_rect.width() / 2, mid_y - text_rect.height() / 2)
        self._preview_text.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self._preview_text.setZValue(1002)
        self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        scene = self._view.scene()
        if not scene:
            return True

        edge = _find_nearest_edge_anchor(scene_pos, scene.items())
        if edge is None:
            return True

        if self._anchor_a is None:
            self._anchor_a = edge
            self._clear_edge_indicators()
            self._show_selected_anchor(edge)
        else:
            anchor_b = edge
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor_b.item, "item_id")
                and self._anchor_a.item.item_id == anchor_b.item.item_id
            ):
                return True

            self._create_equal_constraint(self._anchor_a, anchor_b)
            self._reset()

        return True

    def _create_equal_constraint(self, anchor_a, anchor_b) -> None:
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef, ConstraintType

        scene = self._view.scene()
        if not scene:
            return
        if not hasattr(anchor_a.item, "item_id") or not hasattr(anchor_b.item, "item_id"):
            return

        dim_a = _compute_equal_dimension(anchor_a)
        if dim_a is None:
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate("EqualConstraintTool", "Equal Size Constraint"),
                QCoreApplication.translate(
                    "EqualConstraintTool",
                    "Cannot determine the size dimension for object A.",
                ),
            )
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

        # Resize item B to match item A's dimension
        old_size_b, apply_fn = _build_equal_resize_fn(anchor_b.item, anchor_b.anchor_type)
        item_sizes: list = []
        if apply_fn is not None and old_size_b is not None and abs(dim_a - old_size_b) > 0.01:
            item_sizes = [(anchor_b.item, old_size_b, dim_a, apply_fn)]

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=dim_a,
            constraint_type=ConstraintType.EQUAL,
            item_rotations=item_sizes,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_edge_indicators(scene_pos)
        if self._anchor_a is not None:
            scene = self._view.scene()
            items = scene.items() if scene else []
            edge = _find_nearest_edge_anchor(scene_pos, items)
            end = edge.point if edge else scene_pos
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


class ParallelConstraintTool(BaseTool):
    """Tool for creating parallel constraints between two item edges.

    Workflow:
    1. Hover over an item — edge midpoints are highlighted (green circles).
    2. Click an edge midpoint on object A (reference edge).
    3. Hover and click an edge midpoint on object B — object B is immediately
       rotated so its selected edge is parallel to object A's edge.
    4. The constraint is stored with undo/redo bundling the rotation.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._edge_a = None
        self._graphics_items: list = []
        self._edge_indicators: list = []
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_PARALLEL

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("ParallelConstraintTool", "Parallel Constraint")

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
        self._edge_a = None
        self._clear_all_visuals()

    def _clear_all_visuals(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._graphics_items:
            if item.scene():
                scene.removeItem(item)
        self._graphics_items.clear()
        self._clear_edge_indicators()
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    def _clear_edge_indicators(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._edge_indicators:
            if item.scene():
                scene.removeItem(item)
        self._edge_indicators.clear()

    def _show_edge_indicators(self, scene_pos) -> None:
        from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        scene = self._view.scene()
        if not scene:
            return
        self._clear_edge_indicators()

        edge_types = {AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM,
                      AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT}

        items_at = scene.items(scene_pos)
        hovered = None
        for it in items_at:
            if isinstance(it, GardenItemMixin) and it.flags() & it.GraphicsItemFlag.ItemIsSelectable:
                hovered = it
                break

        if hovered is None:
            return

        for anchor in get_anchor_points(hovered):
            if anchor.anchor_type not in edge_types:
                continue
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
            pen = QPen(PREVIEW_PARALLEL_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._edge_indicators.append(indicator)

    def _show_selected_edge(self, anchor) -> None:
        scene = self._view.scene()
        if not scene:
            return
        r = ANCHOR_INDICATOR_RADIUS + 2
        rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
        pen = QPen(ANCHOR_SELECTED_COLOR, PEN_WIDTH)
        self._selected_marker = scene.addEllipse(rect, pen)
        self._selected_marker.setZValue(1003)
        self._graphics_items.append(self._selected_marker)

    def _update_preview(self, end_pos) -> None:
        scene = self._view.scene()
        if not scene or self._edge_a is None:
            return

        start = self._edge_a.point
        color = PREVIEW_PARALLEL_COLOR

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

        text = QCoreApplication.translate("ParallelConstraintTool", "\u2225 Parallel")
        mid_x = (start.x() + end_pos.x()) / 2
        mid_y = (start.y() + end_pos.y()) / 2
        self._preview_text = scene.addText(text)
        self._preview_text.setDefaultTextColor(color)
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        self._preview_text.setFont(font)
        text_rect = self._preview_text.boundingRect()
        self._preview_text.setPos(mid_x - text_rect.width() / 2, mid_y - text_rect.height() / 2)
        self._preview_text.setFlag(QGraphicsTextItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self._preview_text.setZValue(1002)
        self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        scene = self._view.scene()
        if not scene:
            return True

        edge = _find_nearest_edge_anchor(scene_pos, scene.items())
        if edge is None:
            return True

        if self._edge_a is None:
            self._edge_a = edge
            self._clear_edge_indicators()
            self._show_selected_edge(edge)
        else:
            edge_b = edge
            if (
                hasattr(self._edge_a.item, "item_id")
                and hasattr(edge_b.item, "item_id")
                and self._edge_a.item.item_id == edge_b.item.item_id
            ):
                return True

            self._create_parallel_constraint(self._edge_a, edge_b)
            self._reset()

        return True

    def _create_parallel_constraint(self, edge_a, edge_b) -> None:
        import math as _math  # noqa: F401

        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef, ConstraintType

        scene = self._view.scene()
        if not scene:
            return
        if not hasattr(edge_a.item, "item_id") or not hasattr(edge_b.item, "item_id"):
            return

        alpha_a = _compute_edge_scene_angle(edge_a)
        if alpha_a is None:
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate("ParallelConstraintTool", "Parallel Constraint"),
                QCoreApplication.translate(
                    "ParallelConstraintTool",
                    "Cannot determine the angle of the selected edge on object A.",
                ),
            )
            return

        alpha_b = _compute_edge_scene_angle(edge_b)
        if alpha_b is None:
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate("ParallelConstraintTool", "Parallel Constraint"),
                QCoreApplication.translate(
                    "ParallelConstraintTool",
                    "Cannot determine the angle of the selected edge on object B.",
                ),
            )
            return

        # Prefer rotating edge B (second-clicked / "target") to align with edge A.
        # Fall back to rotating edge A if edge B is already rotation-constrained
        # (has an existing PARALLEL or PERPENDICULAR constraint on its item).
        graph = scene.constraint_graph
        if not graph.has_rotation_constraint(edge_b.item.item_id):
            item_to_rotate = edge_b.item
            rot = getattr(item_to_rotate, "rotation_angle", 0.0)
            delta = (alpha_a - alpha_b + 90.0) % 180.0 - 90.0
        else:
            item_to_rotate = edge_a.item
            rot = getattr(item_to_rotate, "rotation_angle", 0.0)
            delta = (alpha_b - alpha_a + 90.0) % 180.0 - 90.0
        target_rotation = rot + delta

        ref_a = AnchorRef(
            item_id=edge_a.item.item_id,
            anchor_type=edge_a.anchor_type,
            anchor_index=edge_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=edge_b.item.item_id,
            anchor_type=edge_b.anchor_type,
            anchor_index=edge_b.anchor_index,
        )

        item_rotations: list = []
        if hasattr(item_to_rotate, "_apply_rotation") and abs(delta) > 0.01:
            item_rotations = [
                (item_to_rotate, rot, target_rotation, lambda it, ang: it._apply_rotation(ang))
            ]
            # Propagate rotation delta through existing PARALLEL/PERPENDICULAR chains.
            reference_item = edge_b.item if item_to_rotate is edge_a.item else edge_a.item
            chain = _collect_rotation_chain(
                scene.items(), scene.constraint_graph,
                item_to_rotate, delta, reference_item.item_id,
            )
            item_rotations.extend(chain)

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=target_rotation,
            constraint_type=ConstraintType.PARALLEL,
            item_rotations=item_rotations,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_edge_indicators(scene_pos)
        if self._edge_a is not None:
            scene = self._view.scene()
            items = scene.items() if scene else []
            edge = _find_nearest_edge_anchor(scene_pos, items)
            end = edge.point if edge else scene_pos
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


# ─── Perpendicular constraint ─────────────────────────────────────────────────

PREVIEW_PERPENDICULAR_COLOR = QColor(20, 120, 160, 200)   # Blue-teal for perpendicular


class PerpendicularConstraintTool(BaseTool):
    """Tool for creating perpendicular constraints between two item edges.

    Workflow:
    1. Hover over an item — edge midpoints are highlighted (blue-teal circles).
    2. Click an edge midpoint on object A (reference edge).
    3. Hover and click an edge midpoint on object B — object B is immediately
       rotated so its selected edge is perpendicular (90°) to object A's edge.
    4. The constraint is stored with undo/redo bundling the rotation.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._edge_a = None
        self._graphics_items: list = []
        self._edge_indicators: list = []
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_PERPENDICULAR

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate(
            "PerpendicularConstraintTool", "Perpendicular Constraint"
        )

    @property
    def shortcut(self) -> str:
        return ""

    @property
    def cursor(self):
        return QCursor(Qt.CursorShape.CrossCursor)

    def activate(self) -> None:
        super().activate()
        self._reset()

    def deactivate(self) -> None:
        super().deactivate()
        self._reset()

    def _reset(self) -> None:
        self._edge_a = None
        self._clear_all_visuals()

    def _clear_all_visuals(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._graphics_items:
            if item.scene():
                scene.removeItem(item)
        self._graphics_items.clear()
        self._clear_edge_indicators()
        self._selected_marker = None
        self._preview_line = None
        self._preview_text = None

    def _clear_edge_indicators(self) -> None:
        scene = self._view.scene()
        if not scene:
            return
        for item in self._edge_indicators:
            if item.scene():
                scene.removeItem(item)
        self._edge_indicators.clear()

    def _show_edge_indicators(self, scene_pos: QPointF) -> None:
        """Highlight edge-midpoint anchors on the item nearest to scene_pos."""
        self._clear_edge_indicators()
        scene = self._view.scene()
        if not scene:
            return

        from open_garden_planner.core.measure_snapper import AnchorType, get_anchor_points
        from open_garden_planner.ui.canvas.items import GardenItemMixin

        edge_types = {
            AnchorType.EDGE_TOP, AnchorType.EDGE_BOTTOM,
            AnchorType.EDGE_LEFT, AnchorType.EDGE_RIGHT,
        }

        hovered = None
        best_dist = 40.0
        for scene_item in scene.items():
            if not isinstance(scene_item, GardenItemMixin):
                continue
            for anchor in get_anchor_points(scene_item):
                if anchor.anchor_type not in edge_types:
                    continue
                import math as _math
                dx = anchor.point.x() - scene_pos.x()
                dy = anchor.point.y() - scene_pos.y()
                d = _math.sqrt(dx * dx + dy * dy)
                if d < best_dist:
                    best_dist = d
                    hovered = scene_item

        if hovered is None:
            return

        for anchor in get_anchor_points(hovered):
            if anchor.anchor_type not in edge_types:
                continue
            r = ANCHOR_INDICATOR_RADIUS
            rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
            pen = QPen(PREVIEW_PERPENDICULAR_COLOR, PEN_WIDTH)
            indicator = scene.addEllipse(rect, pen)
            indicator.setZValue(1002)
            self._edge_indicators.append(indicator)

    def _show_selected_edge(self, anchor) -> None:
        scene = self._view.scene()
        if not scene:
            return
        r = ANCHOR_INDICATOR_RADIUS
        rect = QRectF(anchor.point.x() - r, anchor.point.y() - r, r * 2, r * 2)
        pen = QPen(ANCHOR_SELECTED_COLOR, PEN_WIDTH)
        self._selected_marker = scene.addEllipse(rect, pen)
        self._selected_marker.setZValue(1003)
        self._graphics_items.append(self._selected_marker)

    def _update_preview(self, end_pos: QPointF) -> None:
        scene = self._view.scene()
        if not scene or self._edge_a is None:
            return

        start = self._edge_a.point
        color = PREVIEW_PERPENDICULAR_COLOR

        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        pen = QPen(color, PEN_WIDTH, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        self._preview_line = scene.addLine(QLineF(start, end_pos), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        mid = QPointF((start.x() + end_pos.x()) / 2, (start.y() + end_pos.y()) / 2)
        text_item = scene.addText("\u22be")
        text_item.setDefaultTextColor(color)
        font = QFont()
        font.setPointSizeF(10.0)
        text_item.setFont(font)
        text_item.setPos(mid)
        text_item.setZValue(1001)
        self._preview_text = text_item
        self._graphics_items.append(self._preview_text)

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        scene = self._view.scene()
        if not scene:
            return True

        edge = _find_nearest_edge_anchor(scene_pos, scene.items())
        if edge is None:
            return True

        if self._edge_a is None:
            self._edge_a = edge
            self._clear_edge_indicators()
            self._show_selected_edge(edge)
        else:
            edge_b = edge
            if (
                hasattr(self._edge_a.item, "item_id")
                and hasattr(edge_b.item, "item_id")
                and self._edge_a.item.item_id == edge_b.item.item_id
            ):
                return True

            self._create_perpendicular_constraint(self._edge_a, edge_b)
            self._reset()

        return True

    def _create_perpendicular_constraint(self, edge_a, edge_b) -> None:
        import math as _math  # noqa: F401

        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef, ConstraintType

        scene = self._view.scene()
        if not scene:
            return
        if not hasattr(edge_a.item, "item_id") or not hasattr(edge_b.item, "item_id"):
            return

        alpha_a = _compute_edge_scene_angle(edge_a)
        if alpha_a is None:
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate(
                    "PerpendicularConstraintTool", "Perpendicular Constraint"
                ),
                QCoreApplication.translate(
                    "PerpendicularConstraintTool",
                    "Cannot determine the angle of the selected edge on object A.",
                ),
            )
            return

        alpha_b = _compute_edge_scene_angle(edge_b)
        if alpha_b is None:
            QMessageBox.warning(
                self._view,
                QCoreApplication.translate(
                    "PerpendicularConstraintTool", "Perpendicular Constraint"
                ),
                QCoreApplication.translate(
                    "PerpendicularConstraintTool",
                    "Cannot determine the angle of the selected edge on object B.",
                ),
            )
            return

        # Prefer rotating edge B (second-clicked / "target") to be perpendicular to edge A.
        # Fall back to rotating edge A if edge B is already rotation-constrained
        # (has an existing PARALLEL or PERPENDICULAR constraint on its item).
        graph = scene.constraint_graph
        if not graph.has_rotation_constraint(edge_b.item.item_id):
            item_to_rotate = edge_b.item
            rot = getattr(item_to_rotate, "rotation_angle", 0.0)
            target_edge_angle = (alpha_a + 90.0) % 180.0
            delta = (target_edge_angle - alpha_b + 90.0) % 180.0 - 90.0
        else:
            item_to_rotate = edge_a.item
            rot = getattr(item_to_rotate, "rotation_angle", 0.0)
            target_edge_angle = (alpha_b + 90.0) % 180.0
            delta = (target_edge_angle - alpha_a + 90.0) % 180.0 - 90.0
        target_rotation = rot + delta

        ref_a = AnchorRef(
            item_id=edge_a.item.item_id,
            anchor_type=edge_a.anchor_type,
            anchor_index=edge_a.anchor_index,
        )
        ref_b = AnchorRef(
            item_id=edge_b.item.item_id,
            anchor_type=edge_b.anchor_type,
            anchor_index=edge_b.anchor_index,
        )

        item_rotations: list = []
        if hasattr(item_to_rotate, "_apply_rotation") and abs(delta) > 0.01:
            item_rotations = [
                (item_to_rotate, rot, target_rotation, lambda it, ang: it._apply_rotation(ang))
            ]
            # Propagate rotation delta through existing PARALLEL/PERPENDICULAR chains.
            reference_item = edge_b.item if item_to_rotate is edge_a.item else edge_a.item
            chain = _collect_rotation_chain(
                scene.items(), scene.constraint_graph,
                item_to_rotate, delta, reference_item.item_id,
            )
            item_rotations.extend(chain)

        command = AddConstraintCommand(
            graph=scene.constraint_graph,
            anchor_a=ref_a,
            anchor_b=ref_b,
            target_distance=target_rotation,
            constraint_type=ConstraintType.PERPENDICULAR,
            item_rotations=item_rotations,
        )
        self._view._execute_constraint_with_solve(command)

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._show_edge_indicators(scene_pos)
        if self._edge_a is not None:
            scene = self._view.scene()
            items = scene.items() if scene else []
            edge = _find_nearest_edge_anchor(scene_pos, items)
            end = edge.point if edge else scene_pos
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


# ─── Fix in place constraint ──────────────────────────────────────────────────

PREVIEW_FIXED_COLOR = QColor(180, 130, 0, 220)   # Gold/amber for fixed constraint


class FixedConstraintTool(BaseTool):
    """Tool for fixing an item in place (blocking it from moving).

    Workflow:
    1. Hover over any item — it is highlighted with a dashed gold outline.
    2. Click the item — a FIXED constraint is created storing its current
       scene position (item.pos()). The item can no longer be dragged or
       moved by the constraint solver.
    3. To release the item, remove the FIXED constraint from the Constraints
       panel or via Ctrl+Z.
    """

    def __init__(self, view) -> None:
        super().__init__(view)
        self._graphics_items: list = []

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_FIXED

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate("FixedConstraintTool", "Fix in Place")

    @property
    def shortcut(self) -> str:
        return ""

    @property
    def cursor(self) -> QCursor:
        return QCursor(Qt.CursorShape.PointingHandCursor)

    def activate(self) -> None:
        super().activate()
        self._clear_graphics()

    def deactivate(self) -> None:
        super().deactivate()
        self._clear_graphics()

    def _clear_graphics(self) -> None:
        scene = self._view.scene()
        if scene:
            for g in self._graphics_items:
                if g.scene():
                    scene.removeItem(g)
        self._graphics_items.clear()

    def mouse_press(self, event: QMouseEvent, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False

        scene = self._view.scene()
        if scene is None:
            return True

        hit = self._find_garden_item_at(scene_pos)
        if hit is None:
            return True

        item_id = hit.item_id
        graph = scene.constraint_graph

        from open_garden_planner.core.constraints import ConstraintType as _CT
        # Prevent double-fixing the same item
        for c in graph.constraints.values():
            if c.constraint_type == _CT.FIXED and c.anchor_a.item_id == item_id:
                return True

        pos = hit.pos()
        from open_garden_planner.core.commands import AddConstraintCommand
        from open_garden_planner.core.constraints import AnchorRef, ConstraintType
        from open_garden_planner.core.measure_snapper import AnchorType

        ref = AnchorRef(item_id=item_id, anchor_type=AnchorType.CENTER, anchor_index=0)
        command = AddConstraintCommand(
            graph=graph,
            anchor_a=ref,
            anchor_b=ref,
            target_distance=0.0,
            constraint_type=ConstraintType.FIXED,
            target_x=pos.x(),
            target_y=pos.y(),
        )
        self._view._execute_constraint_with_solve(command)
        return True

    def mouse_move(self, _event: QMouseEvent, scene_pos: QPointF) -> bool:
        self._clear_graphics()
        hit = self._find_garden_item_at(scene_pos)
        if hit is not None:
            self._draw_hover_indicator(hit)
        return True

    def mouse_release(self, _event: QMouseEvent, _scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event: QKeyEvent) -> bool:
        if event.key() == Qt.Key.Key_Escape:
            self._clear_graphics()
            return True
        return False

    def cancel(self) -> None:
        self._clear_graphics()

    def _find_garden_item_at(self, scene_pos: QPointF):
        """Return the topmost GardenItemMixin under scene_pos, or None."""
        scene = self._view.scene()
        if scene is None:
            return None
        for item in scene.items(scene_pos):
            if isinstance(item, GardenItemMixin) and hasattr(item, "item_id"):
                return item
        return None

    def _draw_hover_indicator(self, item) -> None:
        """Draw a dashed gold outline around the hovered item as a fix-preview."""
        scene = self._view.scene()
        if scene is None:
            return
        br_poly = item.mapToScene(item.boundingRect())
        xs = [br_poly[i].x() for i in range(4)]
        ys = [br_poly[i].y() for i in range(4)]
        rect = QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

        from PyQt6.QtGui import QBrush
        from PyQt6.QtWidgets import QGraphicsSimpleTextItem

        pen = QPen(PREVIEW_FIXED_COLOR, 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        outline = scene.addRect(rect, pen)
        outline.setZValue(1001)
        self._graphics_items.append(outline)

        label = QGraphicsSimpleTextItem(
            QCoreApplication.translate("FixedConstraintTool", "🔒 Fix in place")
        )
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        label.setFont(font)
        label.setBrush(QBrush(PREVIEW_FIXED_COLOR))
        label.setFlag(label.GraphicsItemFlag.ItemIgnoresTransformations)
        label.setPos(rect.right(), rect.top())
        label.setZValue(1002)
        scene.addItem(label)
        self._graphics_items.append(label)


# H/V distance constraint visual constants
PREVIEW_H_DIST_COLOR = QColor(21, 101, 192, 200)    # Deep blue (dimensional)
PREVIEW_V_DIST_COLOR = QColor(21, 101, 192, 200)    # Deep blue (dimensional)


class HDistanceInputDialog(QDialog):
    """Dialog for entering the target horizontal distance for an H-distance constraint."""

    def __init__(self, current_h_dist_cm: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            QCoreApplication.translate(
                "HDistanceInputDialog", "Set Horizontal Distance"
            )
        )
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)

        label = QLabel(
            QCoreApplication.translate(
                "HDistanceInputDialog",
                "Enter the target horizontal distance (meters):",
            )
        )
        layout.addWidget(label)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.01, 999.99)
        self._spin.setDecimals(2)
        self._spin.setSuffix(" m")
        self._spin.setSingleStep(0.10)
        self._spin.setValue(current_h_dist_cm / 100.0)
        self._spin.selectAll()
        layout.addWidget(self._spin)

        current_label = QLabel(
            QCoreApplication.translate(
                "HDistanceInputDialog",
                "Current horizontal distance: {distance:.2f} m",
            ).format(distance=current_h_dist_cm / 100.0)
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


class VDistanceInputDialog(QDialog):
    """Dialog for entering the target vertical distance for a V-distance constraint."""

    def __init__(self, current_v_dist_cm: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(
            QCoreApplication.translate(
                "VDistanceInputDialog", "Set Vertical Distance"
            )
        )
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)

        label = QLabel(
            QCoreApplication.translate(
                "VDistanceInputDialog",
                "Enter the target vertical distance (meters):",
            )
        )
        layout.addWidget(label)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.01, 999.99)
        self._spin.setDecimals(2)
        self._spin.setSuffix(" m")
        self._spin.setSingleStep(0.10)
        self._spin.setValue(current_v_dist_cm / 100.0)
        self._spin.selectAll()
        layout.addWidget(self._spin)

        current_label = QLabel(
            QCoreApplication.translate(
                "VDistanceInputDialog",
                "Current vertical distance: {distance:.2f} m",
            ).format(distance=current_v_dist_cm / 100.0)
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


class HorizontalDistanceConstraintTool(ConstraintTool):
    """Tool for creating horizontal distance constraints (fixed X-axis distance).

    Like FreeCAD's 'Horizontal Dimension'. Distinct from HorizontalConstraintTool
    (which aligns Y coordinates to zero); this tool fixes |bx - ax| = target.
    The Y-axis difference is left free.
    """

    _CONSTRAINT_TYPE = ConstraintType.HORIZONTAL_DISTANCE
    _PREVIEW_COLOR = PREVIEW_H_DIST_COLOR

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_H_DISTANCE

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate(
            "HorizontalDistanceConstraintTool", "Horizontal Distance Constraint"
        )

    @property
    def shortcut(self) -> str:
        return ""

    def _update_preview(self, end_pos: QPointF) -> None:
        """Override to show a horizontal-only preview arrow."""
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point
        color = self._PREVIEW_COLOR

        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        # Snap end to same Y as start — shows horizontal-only distance
        snapped_end = QPointF(end_pos.x(), start.y())

        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, snapped_end), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        h_dist_cm = abs(end_pos.x() - start.x())
        text = QCoreApplication.translate(
            "HorizontalDistanceConstraintTool", "↔ {d:.2f} m"
        ).format(d=h_dist_cm / 100.0)

        mid_x = (start.x() + snapped_end.x()) / 2
        mid_y = start.y()

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
            return True

        if self._anchor_a is None:
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._show_selected_anchor(anchor)
            return True
        else:
            anchor_b = anchor
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor_b.item, "item_id")
                and self._anchor_a.item.item_id == anchor_b.item.item_id
                and self._anchor_a.anchor_type == anchor_b.anchor_type
            ):
                return True

            h_dist_cm = abs(anchor_b.point.x() - self._anchor_a.point.x())
            dialog = HDistanceInputDialog(h_dist_cm, self._view)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                target_cm = dialog.distance_cm()
                self._create_constraint(self._anchor_a, anchor_b, target_cm)

            self._reset()
            return True


class VerticalDistanceConstraintTool(ConstraintTool):
    """Tool for creating vertical distance constraints (fixed Y-axis distance).

    Like FreeCAD's 'Vertical Dimension'. Distinct from VerticalConstraintTool
    (which aligns X coordinates to zero); this tool fixes |by - ay| = target.
    The X-axis difference is left free.
    """

    _CONSTRAINT_TYPE = ConstraintType.VERTICAL_DISTANCE
    _PREVIEW_COLOR = PREVIEW_V_DIST_COLOR

    @property
    def tool_type(self) -> ToolType:
        return ToolType.CONSTRAINT_V_DISTANCE

    @property
    def display_name(self) -> str:
        return QCoreApplication.translate(
            "VerticalDistanceConstraintTool", "Vertical Distance Constraint"
        )

    @property
    def shortcut(self) -> str:
        return ""

    def _update_preview(self, end_pos: QPointF) -> None:
        """Override to show a vertical-only preview arrow."""
        scene = self._view.scene()
        if not scene or self._anchor_a is None:
            return

        start = self._anchor_a.point
        color = self._PREVIEW_COLOR

        if self._preview_line and self._preview_line.scene():
            scene.removeItem(self._preview_line)
            self._graphics_items.remove(self._preview_line)
        if self._preview_text and self._preview_text.scene():
            scene.removeItem(self._preview_text)
            self._graphics_items.remove(self._preview_text)

        # Snap end to same X as start — shows vertical-only distance
        snapped_end = QPointF(start.x(), end_pos.y())

        pen = QPen(color, 2, Qt.PenStyle.DashLine)
        self._preview_line = scene.addLine(QLineF(start, snapped_end), pen)
        self._preview_line.setZValue(1001)
        self._graphics_items.append(self._preview_line)

        v_dist_cm = abs(end_pos.y() - start.y())
        text = QCoreApplication.translate(
            "VerticalDistanceConstraintTool", "↕ {d:.2f} m"
        ).format(d=v_dist_cm / 100.0)

        mid_x = start.x()
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
            return True

        if self._anchor_a is None:
            self._anchor_a = anchor
            self._clear_anchor_indicators()
            self._show_selected_anchor(anchor)
            return True
        else:
            anchor_b = anchor
            if (
                hasattr(self._anchor_a.item, "item_id")
                and hasattr(anchor_b.item, "item_id")
                and self._anchor_a.item.item_id == anchor_b.item.item_id
                and self._anchor_a.anchor_type == anchor_b.anchor_type
            ):
                return True

            v_dist_cm = abs(anchor_b.point.y() - self._anchor_a.point.y())
            dialog = VDistanceInputDialog(v_dist_cm, self._view)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                target_cm = dialog.distance_cm()
                self._create_constraint(self._anchor_a, anchor_b, target_cm)

            self._reset()
            return True
