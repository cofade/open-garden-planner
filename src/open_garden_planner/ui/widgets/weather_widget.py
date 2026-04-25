"""Weather forecast widget for US-12.1.

Displays a 7-day forecast strip and an expandable 14-day table.
Fetches data in a background QThread and caches results.
"""

from __future__ import annotations

import datetime
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from open_garden_planner.services.weather_service import (
    WeatherForecast,
    _wmo_to_description,
    get_weather_service,
    wmo_to_icon,
)

# ─── Background worker ────────────────────────────────────────────────────────

class _WeatherFetchWorker(QThread):
    """QThread that fetches a forecast in the background."""

    success = pyqtSignal(object)  # WeatherForecast
    error = pyqtSignal(str)

    def __init__(self, lat: float, lon: float) -> None:
        super().__init__()
        self._lat = lat
        self._lon = lon

    def run(self) -> None:
        try:
            forecast = get_weather_service().fetch_forecast(self._lat, self._lon)
            if forecast is not None:
                self.success.emit(forecast)
            else:
                self.error.emit(self.tr("Forecast unavailable"))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


# ─── Widget ───────────────────────────────────────────────────────────────────

class WeatherWidget(QFrame):
    """Weather forecast widget: 7-day strip + expandable 14-day table."""

    forecast_ready = pyqtSignal()
    forecast_failed = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._lat: float | None = None
        self._lon: float | None = None
        self._forecast: WeatherForecast | None = None
        self._worker: _WeatherFetchWorker | None = None
        self._expanded = False
        self._build_ui()

    # ── construction ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header bar ──────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("weatherWidgetHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 4, 6, 4)

        self._title_lbl = QLabel(self.tr("Weather Forecast"))
        self._title_lbl.setStyleSheet("font-weight: bold; font-size: 9pt;")
        header_layout.addWidget(self._title_lbl)

        header_layout.addStretch()

        self._location_lbl = QLabel()
        self._location_lbl.setStyleSheet("font-size: 8pt; color: #666;")
        header_layout.addWidget(self._location_lbl)

        self._refresh_btn = QPushButton("\U0001f504")  # 🔄
        self._refresh_btn.setFlat(True)
        self._refresh_btn.setFixedSize(24, 22)
        self._refresh_btn.setToolTip(self.tr("Refresh forecast"))
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        header_layout.addWidget(self._refresh_btn)

        self._expand_btn = QPushButton("▾")
        self._expand_btn.setFlat(True)
        self._expand_btn.setFixedSize(24, 22)
        self._expand_btn.setToolTip(self.tr("Show / hide full forecast"))
        self._expand_btn.clicked.connect(self._on_expand_clicked)
        header_layout.addWidget(self._expand_btn)

        outer.addWidget(header)

        # ── Loading label ───────────────────────────────────────────────
        self._loading_lbl = QLabel(self.tr("Loading forecast …"))
        self._loading_lbl.setStyleSheet("color: #666; font-size: 9pt; padding: 8px 12px;")
        self._loading_lbl.hide()
        outer.addWidget(self._loading_lbl)

        # ── Empty-state label ───────────────────────────────────────────
        self._empty_lbl = QLabel(
            self.tr(
                "Set a location to enable weather forecast.\n"
                "Use File › Set Garden Location to configure GPS coordinates."
            )
        )
        self._empty_lbl.setStyleSheet("color: #666; font-size: 9pt; padding: 8px 12px;")
        self._empty_lbl.setWordWrap(True)
        outer.addWidget(self._empty_lbl)

        # ── 7-day strip ─────────────────────────────────────────────────
        self._strip = QWidget()
        strip_layout = QHBoxLayout(self._strip)
        strip_layout.setContentsMargins(4, 4, 4, 4)
        strip_layout.setSpacing(4)
        self._day_cells: list[_DayCell] = []
        for _ in range(7):
            cell = _DayCell()
            self._day_cells.append(cell)
            strip_layout.addWidget(cell)
        outer.addWidget(self._strip)
        self._strip.hide()

        # ── Expandable table ────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            self.tr("Date"),
            self.tr("Weather"),
            self.tr("Max °C"),
            self.tr("Min °C"),
            self.tr("Rain mm"),
        ])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSectionResizeMode(1, self._table.horizontalHeader().ResizeMode.Stretch)
        self._table.setMaximumHeight(280)
        self._table.hide()
        outer.addWidget(self._table)

        # ── Offline / age label ─────────────────────────────────────────
        self._age_lbl = QLabel()
        self._age_lbl.setStyleSheet("color: #888; font-size: 8pt; padding: 2px 12px;")
        self._age_lbl.hide()
        outer.addWidget(self._age_lbl)

        self._show_empty_state()

    # ── public API ──────────────────────────────────────────────────────

    def set_location(self, lat: float | None, lon: float | None) -> None:
        """Set (or clear) the GPS location; reset UI accordingly."""
        self._lat = lat
        self._lon = lon
        if lat is None or lon is None:
            self._show_empty_state()
        else:
            self._location_lbl.setText(f"{lat:.2f}°, {lon:.2f}°")
            self._show_loading()

    def refresh(self) -> None:
        """Start a background fetch for the current location."""
        if self._lat is None or self._lon is None:
            self._show_empty_state()
            return

        # Skip if a fetch for this exact location is already in flight
        if (self._worker is not None and self._worker.isRunning()
                and self._worker._lat == self._lat
                and self._worker._lon == self._lon):
            return

        self._show_loading()
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(500)

        self._worker = _WeatherFetchWorker(self._lat, self._lon)
        self._worker.success.connect(self._on_fetch_success)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.start()

    def forecast(self) -> WeatherForecast | None:
        """Return the currently-held forecast, or None."""
        return self._forecast

    def apply_frost_thresholds(self, orange_c: float, red_c: float) -> None:
        """Tint the 7-day strip cells that breach a frost threshold."""
        if self._forecast is None:
            return
        for i, cell in enumerate(self._day_cells):
            if i < len(self._forecast.days):
                day = self._forecast.days[i]
                if day.min_c <= red_c:
                    cell.set_frost_severity("red")
                elif day.min_c <= orange_c:
                    cell.set_frost_severity("orange")
                else:
                    cell.set_frost_severity(None)

    # ── slots ───────────────────────────────────────────────────────────

    def _on_fetch_success(self, forecast: WeatherForecast) -> None:
        self._forecast = forecast
        self._render_forecast(forecast)
        self.forecast_ready.emit()

    def _on_fetch_error(self, message: str) -> None:
        self.forecast_failed.emit(message)
        self._show_error(message)

    def _on_fetch_finished(self) -> None:
        self._worker = None

    def _on_refresh_clicked(self) -> None:
        if self._lat is not None and self._lon is not None:
            self.refresh()

    def _on_expand_clicked(self) -> None:
        self._expanded = not self._expanded
        self._expand_btn.setText("▴" if self._expanded else "▾")
        self._table.setVisible(self._expanded)

    # ── rendering ───────────────────────────────────────────────────────

    def _render_forecast(self, forecast: WeatherForecast) -> None:
        self._hide_all_content()

        # 7-day strip
        for i, cell in enumerate(self._day_cells):
            if i < len(forecast.days):
                cell.set_day(forecast.days[i])
                cell.show()
            else:
                cell.hide()
        self._strip.show()

        # 14-day table (data for all days)
        self._table.setRowCount(len(forecast.days))
        for row, day in enumerate(forecast.days):
            self._table.setItem(row, 0, QTableWidgetItem(day.date))
            self._table.setItem(row, 1, QTableWidgetItem(f"{wmo_to_icon(day.weathercode)} {_wmo_to_description(day.weathercode)}"))
            self._table.setItem(row, 2, QTableWidgetItem(f"{day.max_c:.1f}"))
            self._table.setItem(row, 3, QTableWidgetItem(f"{day.min_c:.1f}"))
            self._table.setItem(row, 4, QTableWidgetItem(f"{day.precipitation_mm:.1f}"))
        self._table.setVisible(self._expanded)

        # Age label
        age_text = self._format_age(forecast.fetched_at)
        if age_text:
            self._age_lbl.setText(age_text)
            self._age_lbl.show()
        else:
            self._age_lbl.hide()

    # ── state helpers ───────────────────────────────────────────────────

    def _show_empty_state(self) -> None:
        self._hide_all_content()
        self._empty_lbl.show()
        self._location_lbl.setText("")

    def _show_loading(self) -> None:
        self._hide_all_content()
        self._loading_lbl.show()

    def _show_error(self, message: str) -> None:
        self._hide_all_content()
        self._empty_lbl.setText(self.tr("Weather forecast unavailable:\n{message}").format(message=message))
        self._empty_lbl.show()

    def _hide_all_content(self) -> None:
        self._loading_lbl.hide()
        self._empty_lbl.hide()
        self._strip.hide()
        self._table.hide()
        self._age_lbl.hide()

    @staticmethod
    def _format_age(fetched_at_iso: str) -> str:
        """Return a human-readable age string like 'Last updated 2 h ago'."""
        try:
            fetched = datetime.datetime.fromisoformat(fetched_at_iso)
            # Ensure timezone-aware
            if fetched.tzinfo is None:
                fetched = fetched.replace(tzinfo=datetime.UTC)
            now = datetime.datetime.now(datetime.UTC)
            delta = now - fetched
            if delta.total_seconds() < 60:
                return ""
            if delta.total_seconds() < 3600:
                minutes = int(delta.total_seconds() // 60)
                return WeatherWidget.tr("Last updated %1 min ago").replace("%1", str(minutes))
            hours = int(delta.total_seconds() // 3600)
            return WeatherWidget.tr("Last updated %1 h ago").replace("%1", str(hours))
        except Exception:  # noqa: BLE001
            return ""


# ─── Day cell (one day in the 7-day strip) ────────────────────────────────────

class _DayCell(QFrame):
    """One cell showing a single day's forecast."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(90, 110)
        self.setStyleSheet("background: #fafafa; border-radius: 4px;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._day_lbl = QLabel()
        self._day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._day_lbl.setStyleSheet("font-size: 8pt; color: #555;")
        layout.addWidget(self._day_lbl)

        self._icon_lbl = QLabel()
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("font-size: 28pt;")
        layout.addWidget(self._icon_lbl)

        self._temp_lbl = QLabel()
        self._temp_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._temp_lbl.setStyleSheet("font-size: 9pt; color: #333;")
        layout.addWidget(self._temp_lbl)

        self._rain_lbl = QLabel()
        self._rain_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._rain_lbl.setStyleSheet("font-size: 8pt; color: #36c;")
        layout.addWidget(self._rain_lbl)

    def set_day(self, day: Any) -> None:
        """Populate the cell with forecast data."""
        date = datetime.date.fromisoformat(day.date)
        day_name = date.strftime("%a")
        self._day_lbl.setText(day_name)
        self._icon_lbl.setText(wmo_to_icon(day.weathercode))
        self._temp_lbl.setText(f"{day.max_c:.0f}° / {day.min_c:.0f}°")
        if day.precipitation_mm > 0:
            self._rain_lbl.setText(f"{day.precipitation_mm:.1f} mm")
            self._rain_lbl.show()
        else:
            self._rain_lbl.hide()

    def set_frost_severity(self, severity: str | None) -> None:
        """Tint the cell background to indicate frost risk."""
        if severity == "red":
            self.setStyleSheet("background: #f8d7da; border-radius: 4px;")
        elif severity == "orange":
            self.setStyleSheet("background: #fff3cd; border-radius: 4px;")
        else:
            self.setStyleSheet("background: #fafafa; border-radius: 4px;")
