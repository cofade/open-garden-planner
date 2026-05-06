"""Soil-test trend sparkline (US-12.10e).

A small QPainter widget that plots one parameter (pH, N, P or K) across
all available ``SoilTestRecord`` entries for a bed. Used in the History
tab of :class:`SoilTestDialog`.
"""
from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPaintEvent, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from open_garden_planner.models.soil_test import SoilTestRecord

_PARAM_ATTR: dict[str, str] = {
    "ph": "ph",
    "n": "n_level",
    "p": "p_level",
    "k": "k_level",
}

_PARAM_FIXED_RANGE: dict[str, tuple[float, float]] = {
    "ph": (4.0, 9.0),    # plot range; clamps to 0–14 only when data exceeds this
    "n": (0.0, 4.0),
    "p": (0.0, 4.0),
    "k": (0.0, 4.0),
}

_PARAM_HARD_BOUNDS: dict[str, tuple[float, float]] = {
    "ph": (0.0, 14.0),
    "n": (0.0, 4.0),
    "p": (0.0, 4.0),
    "k": (0.0, 4.0),
}

_AXIS_COLOR = QColor(180, 180, 180)
_LINE_COLOR = QColor(40, 40, 40)
_DOT_COLOR = QColor(40, 40, 40)
_LABEL_COLOR = QColor(110, 110, 110)


class SoilSparklineWidget(QWidget):
    """Tiny line chart of one soil parameter over time."""

    def __init__(self, parameter: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        if parameter not in _PARAM_ATTR:
            raise ValueError(f"Unknown sparkline parameter: {parameter!r}")
        self._parameter = parameter
        self._records: list[SoilTestRecord] = []
        self.setMinimumSize(140, 60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_data(self, records: list[SoilTestRecord]) -> None:
        """Replace the sparkline's data and trigger a repaint."""
        # ISO date strings sort lexicographically — same trick as SoilTestHistory.latest.
        self._records = sorted(records, key=lambda r: r.date)
        self.update()

    # ── Painting ───────────────────────────────────────────────────────────────

    def paintEvent(self, _event: QPaintEvent | None) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        painter.fillRect(rect, QColor(255, 255, 255))

        attr = _PARAM_ATTR[self._parameter]
        points = [
            (r.date, getattr(r, attr))
            for r in self._records
            if getattr(r, attr) is not None and r.date
        ]
        if not points:
            self._paint_placeholder(painter, rect)
            return

        # Plot area with margins for labels. margin_left is fixed (not
        # font-metric-derived) so every sparkline in the History tab —
        # whether plotting pH (one decimal) or NPK (integer) — starts its
        # plot region at exactly the same x pixel within its widget (F11).
        margin_left = 32
        margin_right = 8
        margin_top = 6
        margin_bottom = 14
        plot = QRectF(
            rect.left() + margin_left,
            rect.top() + margin_top,
            max(1.0, rect.width() - margin_left - margin_right),
            max(1.0, rect.height() - margin_top - margin_bottom),
        )

        # Axes
        painter.setPen(QPen(_AXIS_COLOR, 1))
        painter.drawLine(plot.topLeft(), plot.bottomLeft())
        painter.drawLine(plot.bottomLeft(), plot.bottomRight())

        y_min, y_max = self._compute_y_range(points)
        x_dates = [self._parse_date(d) for d, _ in points]

        screen_points = self._project_points(points, x_dates, plot, y_min, y_max)

        # Polyline
        if len(screen_points) >= 2:
            pen = QPen(_LINE_COLOR, 1.5)
            painter.setPen(pen)
            for i in range(len(screen_points) - 1):
                painter.drawLine(screen_points[i], screen_points[i + 1])

        # Dots
        painter.setPen(QPen(_DOT_COLOR, 1))
        painter.setBrush(_DOT_COLOR)
        for p in screen_points:
            painter.drawEllipse(p, 2.0, 2.0)

        # Labels
        self._paint_labels(painter, rect, plot, x_dates, y_min, y_max)

    def _paint_placeholder(self, painter: QPainter, rect: QRectF) -> None:
        painter.setPen(_LABEL_COLOR)
        font = QFont(painter.font())
        font.setPointSize(8)
        painter.setFont(font)
        painter.drawText(
            rect, Qt.AlignmentFlag.AlignCenter, self.tr("No history yet")
        )

    def _compute_y_range(self, points: list[tuple[str, float]]) -> tuple[float, float]:
        values = [v for _, v in points]
        data_min = min(values)
        data_max = max(values)
        default_min, default_max = _PARAM_FIXED_RANGE[self._parameter]
        hard_min, hard_max = _PARAM_HARD_BOUNDS[self._parameter]
        # Combine: include data, clamp to hard bounds, fall back to defaults.
        y_min = max(hard_min, min(data_min, default_min))
        y_max = min(hard_max, max(data_max, default_max))
        if y_max - y_min < 1e-6:
            y_min = max(hard_min, y_min - 0.5)
            y_max = min(hard_max, y_max + 0.5)
        # 5% padding inside hard bounds
        pad = (y_max - y_min) * 0.05
        y_min = max(hard_min, y_min - pad)
        y_max = min(hard_max, y_max + pad)
        return y_min, y_max

    def _project_points(
        self,
        points: list[tuple[str, float]],
        x_dates: list[date | None],
        plot: QRectF,
        y_min: float,
        y_max: float,
    ) -> list[QPointF]:
        valid = [d for d in x_dates if d is not None]
        if not valid or len(points) == 1:
            # Single dot centred horizontally
            cx = plot.center().x()
            value = points[0][1]
            cy = self._project_y(value, plot, y_min, y_max)
            return [QPointF(cx, cy)]

        x_min = min(valid)
        x_max = max(valid)
        x_span_days = max(1, (x_max - x_min).days)

        screen: list[QPointF] = []
        for (_, value), d in zip(points, x_dates, strict=True):
            if d is None:
                continue
            x_frac = (d - x_min).days / x_span_days
            sx = plot.left() + x_frac * plot.width()
            sy = self._project_y(value, plot, y_min, y_max)
            screen.append(QPointF(sx, sy))
        return screen

    def _project_y(
        self, value: float, plot: QRectF, y_min: float, y_max: float
    ) -> float:
        clamped = max(y_min, min(y_max, value))
        frac = (clamped - y_min) / (y_max - y_min) if y_max > y_min else 0.5
        return plot.bottom() - frac * plot.height()

    def _paint_labels(
        self,
        painter: QPainter,
        rect: QRectF,
        plot: QRectF,
        x_dates: list[date | None],
        y_min: float,
        y_max: float,
    ) -> None:
        font = QFont(painter.font())
        font.setPointSize(7)
        painter.setFont(font)
        painter.setPen(_LABEL_COLOR)

        y_label_fmt = "{:.1f}" if self._parameter == "ph" else "{:.0f}"
        painter.drawText(
            QRectF(rect.left(), plot.top() - 6, plot.left() - rect.left(), 12),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            y_label_fmt.format(y_max),
        )
        painter.drawText(
            QRectF(rect.left(), plot.bottom() - 6, plot.left() - rect.left(), 12),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            y_label_fmt.format(y_min),
        )

        valid = [d for d in x_dates if d is not None]
        if not valid:
            return
        x_min_str = valid[0].isoformat()
        x_max_str = valid[-1].isoformat()
        painter.drawText(
            QRectF(plot.left(), plot.bottom() + 1, plot.width() / 2, 12),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            x_min_str,
        )
        if x_min_str != x_max_str:
            painter.drawText(
                QRectF(plot.center().x(), plot.bottom() + 1, plot.width() / 2, 12),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                x_max_str,
            )

    @staticmethod
    def _parse_date(iso: str) -> date | None:
        try:
            return date.fromisoformat(iso)
        except (ValueError, TypeError):
            return None
