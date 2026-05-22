"""Scale bar for the Paper Space layout (MVP).

Visualises the linear scale of the layout as a tick-marked bar with
labels. The bar's *paper-space* length is fixed; the labels are derived
from the layout's primary viewport scale so the user gets a real-world
reference (e.g. "0 — 1 m — 2 m" at 1:50, "0 — 2 m — 4 m" at 1:100).
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QStyleOptionGraphicsItem,
    QWidget,
)

_DEFAULT_WIDTH_CM = 6.0
_HEIGHT_CM = 0.6
_TICKS = 4  # produces 5 labelled stops including 0


class ScaleBarItem(QGraphicsRectItem):
    """Linear scale bar with labels driven by the viewport scale.

    ``scale_factor`` is paper-cm / model-cm (the viewport's own scale).
    The bar's labels show model-space distance at each tick.
    """

    def __init__(self, scale_factor: float = 0.01) -> None:
        super().__init__(QRectF(0, 0, _DEFAULT_WIDTH_CM, _HEIGHT_CM))
        self._scale_factor = scale_factor

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

        self.setPen(QPen(QColor(20, 20, 20), 0.3))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    @scale_factor.setter
    def scale_factor(self, value: float) -> None:
        if value <= 0:
            return
        self._scale_factor = value
        self.update()

    # ── Painting ───────────────────────────────────────────────────────

    def paint(
        self,
        painter: QPainter,
        _option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        rect = self.rect()
        painter.save()

        bar_height = rect.height() * 0.4
        bar_top = rect.y()
        bar_bottom = bar_top + bar_height
        seg_w = rect.width() / _TICKS

        painter.setPen(QPen(QColor(20, 20, 20), 0.4))
        for i in range(_TICKS):
            x_start = rect.x() + i * seg_w
            brush = (
                QBrush(QColor(20, 20, 20))
                if i % 2 == 0
                else QBrush(QColor(255, 255, 255))
            )
            painter.setBrush(brush)
            painter.drawRect(QRectF(x_start, bar_top, seg_w, bar_height))

        # Total bar length in model-cm.
        bar_paper_cm = rect.width()
        total_model_cm = bar_paper_cm / max(self._scale_factor, 1e-9)
        seg_model_cm = total_model_cm / _TICKS

        font = QFont()
        font.setPointSizeF(0.35)
        painter.setFont(font)
        painter.setPen(QColor(20, 20, 20))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(_TICKS + 1):
            x = rect.x() + i * seg_w
            label = _format_distance(i * seg_model_cm)
            text_rect = QRectF(
                x - seg_w / 2.0,
                bar_bottom + 0.05,
                seg_w,
                rect.height() - bar_height - 0.05,
            )
            painter.drawText(
                text_rect, int(Qt.AlignmentFlag.AlignCenter), label
            )

        painter.restore()

    # ── Serialization ──────────────────────────────────────────────────

    def to_dict(self) -> dict[str, float | str]:
        r = self.rect()
        pos = self.pos()
        return {
            "type": "scale_bar",
            "x": pos.x(),
            "y": pos.y(),
            "width": r.width(),
            "scale_factor": self._scale_factor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | str]) -> ScaleBarItem:
        from PyQt6.QtCore import QPointF

        item = cls(scale_factor=float(data.get("scale_factor", 0.01)))
        item.setRect(
            0.0, 0.0, float(data.get("width", _DEFAULT_WIDTH_CM)), _HEIGHT_CM
        )
        item.setPos(QPointF(float(data.get("x", 0.0)), float(data.get("y", 0.0))))
        return item


def _format_distance(cm: float) -> str:
    """Pretty-print a distance in cm with m / cm units."""
    if cm >= 100.0:
        m = cm / 100.0
        if abs(m - round(m)) < 1e-3:
            return f"{int(round(m))} m"
        return f"{m:.1f} m"
    if cm < 1.0:
        return "0"
    if abs(cm - round(cm)) < 1e-3:
        return f"{int(round(cm))} cm"
    return f"{cm:.0f} cm"
