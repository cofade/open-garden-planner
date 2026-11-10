"""The key to the soil-health overlay's colours (#796).

The overlay tints every bed green, amber or red and hatches one without a soil
test; nothing on screen said which is which. The legend sits in the overlay's
toolbar, so it is there exactly while the overlay is.
"""

from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from open_garden_planner.services.soil_service import HealthLevel, SoilService
from open_garden_planner.ui.theme import theme_qcolor

#: The hatch of a bed without a soil test. The overlay itself is painted by
#: ``CanvasView._draw_soil_overlay``, which holds the same value.
UNKNOWN_RGBA = (140, 140, 140, 40)

_SWATCH = 14


class _Swatch(QWidget):
    """One overlay tint as it looks on the plan: over the canvas colour."""

    def __init__(self, level: HealthLevel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._level = level
        self.setFixedSize(_SWATCH, _SWATCH)

    def sizeHint(self) -> QSize:
        return QSize(_SWATCH, _SWATCH)

    def paintEvent(self, _event: QPaintEvent | None) -> None:
        painter = QPainter(self)
        box = QRect(0, 0, _SWATCH - 1, _SWATCH - 1)
        # The canvas is the same colour in both themes; the tints are
        # translucent, so they are shown over it, as the user sees them.
        painter.fillRect(box, theme_qcolor("canvas_background"))
        rgba = SoilService.overlay_rgba(self._level)
        if rgba is None:
            # A legend chip is far smaller than a bed: the hatch needs the
            # opacity a bed's area gives it, or it reads as an empty box.
            hatch = QColor(*UNKNOWN_RGBA[:3])
            painter.fillRect(box, QBrush(hatch, Qt.BrushStyle.DiagCrossPattern))
        else:
            # Twice the alpha for the same reason: at 14 px the plan's 80 of
            # 255 over cream is three near-identical pastels.
            tint = QColor(*rgba)
            tint.setAlpha(min(255, tint.alpha() * 2))
            painter.fillRect(box, tint)
        painter.setPen(QPen(theme_qcolor("text_secondary"), 1))
        painter.drawRect(box)
        painter.end()


class SoilOverlayLegend(QWidget):
    """Good / Fair / Poor / No soil test, each beside its tint."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 4, 0)
        row.setSpacing(4)
        self.labels: dict[HealthLevel, QLabel] = {}
        for level, text in (
            (HealthLevel.GOOD, self.tr("Good")),
            (HealthLevel.FAIR, self.tr("Fair")),
            (HealthLevel.POOR, self.tr("Poor")),
            (HealthLevel.UNKNOWN, self.tr("No soil test")),
        ):
            row.addWidget(_Swatch(level, self))
            label = QLabel(text, self)
            row.addWidget(label)
            row.addSpacing(8)
            self.labels[level] = label
