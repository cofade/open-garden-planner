"""Location dialog for setting GPS coordinates and frost dates."""

import re
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class _FrostLookupWorker(QThread):
    """Background worker that calls ClimateService.lookup_frost_dates."""

    success = pyqtSignal(object)  # FrostData
    error = pyqtSignal(str)

    def __init__(self, lat: float, lon: float) -> None:
        super().__init__()
        self._lat = lat
        self._lon = lon

    def run(self) -> None:
        try:
            from open_garden_planner.services.climate_service import (  # noqa: PLC0415
                get_climate_service,
            )

            data = get_climate_service().lookup_frost_dates(self._lat, self._lon)
            self.success.emit(data)
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))


class LocationDialog(QDialog):
    """Dialog for setting the garden's GPS location and frost dates.

    Allows entering latitude/longitude (decimal degrees) and optionally
    manual frost dates and hardiness zone.  A "Lookup from Coordinates"
    button fetches frost dates automatically from the Open-Meteo ERA5
    archive in a background thread.
    """

    def __init__(
        self,
        parent: object = None,
        location: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the Location dialog.

        Args:
            parent: Parent widget.
            location: Existing location dict to pre-populate, or None.
        """
        super().__init__(parent)

        self.setWindowTitle(self.tr("Set Garden Location"))
        self.setModal(True)
        self.setMinimumWidth(450)

        self._worker: _FrostLookupWorker | None = None

        self._setup_ui()

        if location:
            self._populate(location)

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # GPS coordinates group
        coords_group = QGroupBox(self.tr("GPS Coordinates"))
        coords_layout = QFormLayout(coords_group)

        # Latitude
        lat_row = QHBoxLayout()
        self._lat_spin = QDoubleSpinBox()
        self._lat_spin.setRange(-90.0, 90.0)
        self._lat_spin.setDecimals(6)
        self._lat_spin.setValue(0.0)
        self._lat_spin.setSuffix("°")
        self._lat_spin.setMinimumWidth(150)
        self._lat_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lat_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        lat_row.addWidget(self._lat_spin)
        lat_row.addWidget(QLabel(self.tr("(−90 to 90, N positive)")))
        lat_row.addStretch()
        coords_layout.addRow(self.tr("Latitude:"), lat_row)

        # Longitude
        lon_row = QHBoxLayout()
        self._lon_spin = QDoubleSpinBox()
        self._lon_spin.setRange(-180.0, 180.0)
        self._lon_spin.setDecimals(6)
        self._lon_spin.setValue(0.0)
        self._lon_spin.setSuffix("°")
        self._lon_spin.setMinimumWidth(150)
        self._lon_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._lon_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        lon_row.addWidget(self._lon_spin)
        lon_row.addWidget(QLabel(self.tr("(−180 to 180, E positive)")))
        lon_row.addStretch()
        coords_layout.addRow(self.tr("Longitude:"), lon_row)

        # Elevation (optional)
        elev_row = QHBoxLayout()
        self._elev_spin = QDoubleSpinBox()
        # Use -9999 as "not set" sentinel
        self._elev_spin.setRange(-9999.0, 9000.0)
        self._elev_spin.setDecimals(0)
        self._elev_spin.setSuffix(" m")
        self._elev_spin.setMinimumWidth(120)
        self._elev_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._elev_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self._elev_spin.setSpecialValueText(self.tr("Not set"))
        self._elev_spin.setValue(-9999.0)
        elev_row.addWidget(self._elev_spin)
        elev_row.addStretch()
        coords_layout.addRow(self.tr("Elevation (optional):"), elev_row)

        layout.addWidget(coords_group)

        # Frost dates group
        frost_group = QGroupBox(self.tr("Frost Dates & Hardiness Zone"))
        frost_group.setToolTip(
            self.tr(
                "These are used for planting calendar calculations. "
                "Leave blank if unknown — use the Lookup button to auto-detect."
            )
        )
        frost_layout = QFormLayout(frost_group)

        # Last spring frost
        spring_row = QHBoxLayout()
        self._spring_frost_edit = QLineEdit()
        self._spring_frost_edit.setPlaceholderText(self.tr("MM-DD, e.g. 04-15"))
        self._spring_frost_edit.setMaximumWidth(120)
        self._spring_frost_edit.setToolTip(
            self.tr("Date of last expected spring frost (MM-DD format)")
        )
        spring_row.addWidget(self._spring_frost_edit)
        spring_row.addStretch()
        frost_layout.addRow(self.tr("Last spring frost:"), spring_row)

        # First fall frost
        fall_row = QHBoxLayout()
        self._fall_frost_edit = QLineEdit()
        self._fall_frost_edit.setPlaceholderText(self.tr("MM-DD, e.g. 10-20"))
        self._fall_frost_edit.setMaximumWidth(120)
        self._fall_frost_edit.setToolTip(
            self.tr("Date of first expected fall frost (MM-DD format)")
        )
        fall_row.addWidget(self._fall_frost_edit)
        fall_row.addStretch()
        frost_layout.addRow(self.tr("First fall frost:"), fall_row)

        # Hardiness zone
        zone_row = QHBoxLayout()
        self._zone_edit = QLineEdit()
        self._zone_edit.setPlaceholderText(self.tr("e.g. 7b or H3"))
        self._zone_edit.setMaximumWidth(100)
        self._zone_edit.setToolTip(
            self.tr(
                "Plant hardiness zone — indicates the coldest winter temperatures "
                "your garden experiences. Used to determine which perennial plants "
                "can survive your winters.\n\n"
                "Common formats:\n"
                "  USDA zones (worldwide):  e.g. 5b, 7a, 8b\n"
                "    Scale 1a (coldest, −51 °C) → 13b (warmest, +18 °C)\n"
                "  RHS zones (UK / Europe):  e.g. H3, H4, H5\n"
                "    Scale H1 (tender, frost-free) → H7 (fully hardy, −25 °C)\n\n"
                "Look up your zone for any country at:\n"
                "  plantmaps.com\n"
                "(scroll down to select your country, then find your area on the map)"
            )
        )
        zone_row.addWidget(self._zone_edit)
        zone_row.addStretch()
        frost_layout.addRow(self.tr("Hardiness zone:"), zone_row)

        # Lookup button row
        lookup_row = QHBoxLayout()
        self._lookup_btn = QPushButton(self.tr("Lookup from Coordinates"))
        self._lookup_btn.setToolTip(
            self.tr(
                "Fetch frost dates automatically from the Open-Meteo ERA5 climate "
                "archive using the coordinates entered above.\n"
                "Results are cached locally for one year."
            )
        )
        self._lookup_btn.clicked.connect(self._on_lookup_clicked)
        lookup_row.addWidget(self._lookup_btn)
        lookup_row.addStretch()
        frost_layout.addRow("", lookup_row)

        # Status label (lookup feedback) — secondary colour from global CSS rule
        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        self._status_label.setProperty("hint", True)
        frost_layout.addRow("", self._status_label)

        layout.addWidget(frost_group)

        layout.addSpacing(8)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _populate(self, location: dict[str, Any]) -> None:
        """Pre-populate dialog fields from existing location data."""
        self._lat_spin.setValue(location.get("latitude", 0.0))
        self._lon_spin.setValue(location.get("longitude", 0.0))

        elev = location.get("elevation_m")
        if elev is not None:
            self._elev_spin.setValue(float(elev))

        frost = location.get("frost_dates", {}) or {}
        self._spring_frost_edit.setText(frost.get("last_spring_frost", ""))
        self._fall_frost_edit.setText(frost.get("first_fall_frost", ""))
        self._zone_edit.setText(frost.get("hardiness_zone", ""))

    def _validate_frost_date(self, value: str) -> bool:
        """Return True if value is empty or matches MM-DD format."""
        if not value:
            return True
        return bool(re.fullmatch(r"(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])", value))

    def _on_accept(self) -> None:
        """Validate inputs before accepting."""
        spring = self._spring_frost_edit.text().strip()
        fall = self._fall_frost_edit.text().strip()

        if not self._validate_frost_date(spring):
            self._spring_frost_edit.setFocus()
            self._spring_frost_edit.selectAll()
            return

        if not self._validate_frost_date(fall):
            self._fall_frost_edit.setFocus()
            self._fall_frost_edit.selectAll()
            return

        self.accept()

    # ------------------------------------------------------------------
    # Frost lookup
    # ------------------------------------------------------------------

    def _on_lookup_clicked(self) -> None:
        """Start background frost date lookup using current coordinates."""
        lat = self._lat_spin.value()
        lon = self._lon_spin.value()

        self._lookup_btn.setEnabled(False)
        self._status_label.setText(self.tr("Looking up frost dates…"))
        self._status_label.setStyleSheet("")  # restore hint colour from global rule

        self._worker = _FrostLookupWorker(lat, lon)
        self._worker.success.connect(self._on_lookup_success)
        self._worker.error.connect(self._on_lookup_error)
        self._worker.finished.connect(self._on_lookup_finished)
        self._worker.start()

    def _on_lookup_success(self, frost_data: object) -> None:
        """Populate frost date fields with data returned by the worker."""
        from open_garden_planner.services.climate_service import FrostData  # noqa: PLC0415

        if not isinstance(frost_data, FrostData):
            return

        if frost_data.last_spring_frost:
            self._spring_frost_edit.setText(frost_data.last_spring_frost)

        if frost_data.first_fall_frost:
            self._fall_frost_edit.setText(frost_data.first_fall_frost)

        if frost_data.hardiness_zone and not self._zone_edit.text().strip():
            self._zone_edit.setText(frost_data.hardiness_zone)

        if not frost_data.last_spring_frost and not frost_data.first_fall_frost:
            msg = self.tr(
                "No frost data found — this location may be in a frost-free zone."
            )
        else:
            source = (
                self.tr("Open-Meteo ERA5 (cached)")
                if frost_data.data_source == "cached"
                else self.tr("Open-Meteo ERA5")
            )
            msg = self.tr("Data source: {source}").format(source=source)

        # Restore hint colour (clear any previous error override)
        self._status_label.setStyleSheet("")
        self._status_label.setText(msg)

    def _on_lookup_error(self, error_msg: str) -> None:
        """Show an error message when the lookup fails."""
        self._status_label.setText(
            self.tr("Lookup failed: {error}").format(error=error_msg)
        )
        self._status_label.setStyleSheet("color: red; font-size: 11px;")

    def _on_lookup_finished(self) -> None:
        """Re-enable the lookup button after the worker finishes."""
        self._lookup_btn.setEnabled(True)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # ------------------------------------------------------------------
    # Result accessor
    # ------------------------------------------------------------------

    @property
    def location_data(self) -> dict[str, Any]:
        """Return location data dict built from dialog values."""
        elev_val = self._elev_spin.value()
        elevation_m: float | None = None if elev_val <= -9999.0 else elev_val

        frost_dates: dict[str, Any] = {}
        spring = self._spring_frost_edit.text().strip()
        fall = self._fall_frost_edit.text().strip()
        zone = self._zone_edit.text().strip()
        if spring:
            frost_dates["last_spring_frost"] = spring
        if fall:
            frost_dates["first_fall_frost"] = fall
        if zone:
            frost_dates["hardiness_zone"] = zone

        data: dict[str, Any] = {
            "latitude": self._lat_spin.value(),
            "longitude": self._lon_spin.value(),
        }
        if elevation_m is not None:
            data["elevation_m"] = elevation_m
        if frost_dates:
            data["frost_dates"] = frost_dates

        return data
