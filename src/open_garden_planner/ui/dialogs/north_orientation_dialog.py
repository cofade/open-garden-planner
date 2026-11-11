"""Set the plan's north orientation without rotating the drawing (#663)."""

from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QMouseEvent, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.core.plan_north import normalize_north_angle
from open_garden_planner.ui.theme import theme_color


class NorthCompassWidget(QWidget):
    """A compass rose: click or drag to point true north on the plan.

    The rose shows plan-up as a faint dashed line and true north as a red
    arrow. ``angle_deg`` is degrees clockwise from plan-up, the plan's north
    angle (#663).
    """

    angle_changed = pyqtSignal(float)

    def __init__(self, angle_deg: float = 0.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._angle = normalize_north_angle(angle_deg)
        self._dragging = False
        self.setMinimumSize(200, 200)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(self.tr("Click or drag to point true north on the plan"))

    @property
    def angle_deg(self) -> float:
        return self._angle

    def set_angle(self, angle_deg: object) -> None:
        angle = normalize_north_angle(angle_deg)
        if angle == self._angle:
            return
        self._angle = angle
        self.update()
        self.angle_changed.emit(angle)

    def sizeHint(self) -> QSize:
        return super().sizeHint().expandedTo(self.minimumSize())

    def _centre(self) -> QPointF:
        return QPointF(self.width() / 2.0, self.height() / 2.0)

    def _angle_at(self, point: QPointF) -> float:
        centre = self._centre()
        dx = point.x() - centre.x()
        dy = centre.y() - point.y()  # screen y grows down; up is positive
        return math.degrees(math.atan2(dx, dy)) % 360.0

    def mousePressEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.set_angle(self._angle_at(event.position()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent | None) -> None:
        if self._dragging and event is not None:
            self.set_angle(self._angle_at(event.position()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent | None) -> None:
        if event is not None and event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        centre = self._centre()
        radius = max(10.0, min(self.width(), self.height()) / 2.0 - 20.0)
        border = QColor(theme_color("border"))
        text = QColor(theme_color("text_secondary"))
        accent = QColor(theme_color("error"))

        painter.setPen(QPen(border, 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(centre, radius, radius)

        # A tick every 15 degrees; the four cardinals are longer.
        for step in range(24):
            bearing = step * 15.0
            length = radius * (0.12 if step % 6 == 0 else 0.06)
            outer = self._point(centre, radius, bearing)
            inner = self._point(centre, radius - length, bearing)
            painter.setPen(QPen(border, 1.6 if step % 6 == 0 else 1.0))
            painter.drawLine(inner, outer)

        # Plan-up: the drawing's own 0 degrees, distinct from true north.
        painter.setPen(QPen(border, 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(centre, self._point(centre, radius * 0.78, 0.0))

        # True north.
        tip = self._point(centre, radius * 0.92, self._angle)
        painter.setPen(QPen(accent, 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(centre, tip)
        wing = radius * 0.13
        for side in (-1.0, 1.0):
            edge = self._point(tip, wing, self._angle + 180.0 + side * 26.0)
            painter.drawLine(tip, edge)

        letter_font = QFont(self.font())
        letter_font.setBold(True)
        letter_font.setPointSize(max(8, letter_font.pointSize()))
        painter.setFont(letter_font)
        painter.setPen(QPen(text))
        for bearing, letter in (
            (0.0, self.tr("N")),
            (90.0, self.tr("E")),
            (180.0, self.tr("S")),
            (270.0, self.tr("W")),
        ):
            anchor = self._point(centre, radius - radius * 0.24, bearing + self._angle)
            box = QRectF(anchor.x() - 10.0, anchor.y() - 9.0, 20.0, 18.0)
            painter.drawText(box, Qt.AlignmentFlag.AlignCenter, letter)

    @staticmethod
    def _point(centre: QPointF, radius: float, bearing_deg: float) -> QPointF:
        angle = math.radians(bearing_deg)
        return QPointF(
            centre.x() + radius * math.sin(angle),
            centre.y() - radius * math.cos(angle),
        )


class NorthOrientationDialog(QDialog):
    """File > Set North Orientation: one angle, a compass and a number field."""

    def __init__(self, angle_deg: float = 0.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(self.tr("Set North Orientation"))
        self.setModal(True)
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        self._compass = NorthCompassWidget(angle_deg, self)
        layout.addWidget(self._compass, 1, Qt.AlignmentFlag.AlignHCenter)

        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr("North is")))
        self._angle_field = QDoubleSpinBox(self)
        self._angle_field.setRange(0.0, 359.9)
        self._angle_field.setDecimals(1)
        self._angle_field.setSingleStep(1.0)
        self._angle_field.setWrapping(True)
        self._angle_field.setSuffix(self.tr("° clockwise from up"))
        self._angle_field.setValue(normalize_north_angle(angle_deg))
        row.addWidget(self._angle_field, 1)
        layout.addLayout(row)

        hint = QLabel(
            self.tr(
                "0° points up. The arrow shows where true north lies on the plan; "
                "no object is rotated. The sun, shadows, hours of sun and the "
                "report's north arrow all follow this angle."
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {theme_color('text_secondary')};")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._compass.angle_changed.connect(self._on_compass_changed)
        self._angle_field.valueChanged.connect(self._on_field_changed)

    @property
    def angle_deg(self) -> float:
        return normalize_north_angle(self._angle_field.value())

    def _on_compass_changed(self, angle: float) -> None:
        self._angle_field.blockSignals(True)
        self._angle_field.setValue(angle)
        self._angle_field.blockSignals(False)

    def _on_field_changed(self, value: float) -> None:
        self._compass.blockSignals(True)
        self._compass.set_angle(value)
        self._compass.blockSignals(False)
