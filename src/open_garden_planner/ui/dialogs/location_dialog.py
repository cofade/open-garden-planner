"""Location dialog for setting GPS coordinates and frost dates."""

from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PyQt6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from open_garden_planner.core.frost_dates import is_valid_frost_date
from open_garden_planner.core.map_links import map_link_coordinates, short_map_url
from open_garden_planner.core.plan_time import (
    LOCATION_TIMEZONE_KEY,
    plan_timezone,
    plan_timezone_name,
    timezone_names,
)
from open_garden_planner.core.units import LengthStyle
from open_garden_planner.ui.theme import theme_color
from open_garden_planner.ui.widgets.unit_spin_box import LengthSpinBox


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
            from open_garden_planner.services.climate_service import (
                get_climate_service,
            )

            data = get_climate_service().lookup_frost_dates(self._lat, self._lon)
            self.success.emit(data)
        except Exception as exc:
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
        self._lookup_coordinates: tuple[float, float] | None = None
        #: The zone the plan arrived with (#945). An unknown stored name may be
        #: kept as it is: the plan already loaded it as "no plan zone", so
        #: blocking other location edits on it would trap the user.
        self._initial_timezone = plan_timezone_name(location)
        #: Whether the user chose a zone (including "Same as this computer").
        #: Populating the dialog from the plan does not count.
        self._timezone_touched = False

        self._setup_ui()

        if location:
            self._populate(location)
        # User-originated signals only: a programmatic fill (the dialog's own
        # populate, or the lookup) must stay replaceable by a later lookup.
        self._tz_combo.activated.connect(self._on_timezone_chosen)
        line_edit = self._tz_combo.lineEdit()
        if line_edit is not None:
            line_edit.textEdited.connect(self._on_timezone_chosen)

    def _on_timezone_chosen(self, *_args: object) -> None:
        self._timezone_touched = True

    def _cancel_map_link_request(self) -> None:
        self._map_link_timer.stop()
        previous, self._map_link_reply = self._map_link_reply, None
        if previous is not None:
            previous.abort()

    def done(self, result: int) -> None:
        self._cancel_map_link_request()
        self._set_map_link_pending(False)
        super().done(result)

    def _set_map_link_pending(self, pending: bool) -> None:
        self._map_link_pending = pending
        if self._ok_button is not None:
            self._ok_button.setEnabled(not pending)
        self._lookup_btn.setEnabled(not pending and self._worker is None)

    def _map_link_changed(self, value: str) -> None:
        self._cancel_map_link_request()
        self._set_map_link_pending(False)
        self._map_link_status.clear()
        if not value.strip():
            return
        coordinates = map_link_coordinates(value)
        if coordinates is not None:
            self._set_map_link_coordinates(coordinates)
        elif short_map_url(value) is not None:
            self._set_map_link_pending(True)
            self._map_link_status.setText(self.tr("Resolving map link…"))
            self._map_link_timer.start()
        else:
            self._map_link_status.setText(self.tr("No coordinates found in this map link."))

    def _set_map_link_coordinates(self, coordinates: tuple[float, float]) -> None:
        self._lat_spin.setValue(coordinates[0])
        self._lon_spin.setValue(coordinates[1])
        self._map_link_status.setText(self.tr("Coordinates filled from map link."))

    def _resolve_map_link(self) -> None:
        url = short_map_url(self._map_link_edit.text())
        if url is None:
            return
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        request.setTransferTimeout(8000)
        reply = self._map_link_network.head(request)
        self._map_link_reply = reply
        reply.finished.connect(lambda: self._map_link_finished(reply))

    def _map_link_finished(self, reply: QNetworkReply) -> None:
        reply.deleteLater()
        if reply is not self._map_link_reply:
            return
        self._map_link_reply = None
        self._set_map_link_pending(False)
        target = reply.attribute(QNetworkRequest.Attribute.RedirectionTargetAttribute)
        coordinates = map_link_coordinates(target.toString()) if isinstance(target, QUrl) else None
        if coordinates is None:
            self._map_link_status.setText(self.tr("Could not resolve this map link. Try the full link."))
        else:
            self._set_map_link_coordinates(coordinates)

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # GPS coordinates group
        coords_group = QGroupBox(self.tr("GPS Coordinates"))
        coords_layout = QFormLayout(coords_group)

        self._map_link_network = QNetworkAccessManager(self)
        self._map_link_network.setRedirectPolicy(QNetworkRequest.RedirectPolicy.ManualRedirectPolicy)
        self._map_link_reply: QNetworkReply | None = None
        self._map_link_pending = False
        self._map_link_timer = QTimer(self)
        self._map_link_timer.setSingleShot(True)
        self._map_link_timer.setInterval(350)
        self._map_link_timer.timeout.connect(self._resolve_map_link)
        self._map_link_edit = QLineEdit()
        self._map_link_edit.setPlaceholderText(self.tr("Paste a map link or coordinates"))
        coords_layout.addRow(self.tr("Map link:"), self._map_link_edit)
        self._map_link_status = QLabel()
        self._map_link_status.setWordWrap(True)
        coords_layout.addRow(self._map_link_status)
        self._map_link_edit.textChanged.connect(self._map_link_changed)

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
        self._elev_spin = LengthSpinBox(LengthStyle.FEET, value_unit_cm=100.0)
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

        # Time zone (#945): the plan's local wall time for the clock, the sun,
        # a camera tour's time range and "Today".
        self._tz_combo = QComboBox()
        self._tz_combo.setEditable(True)
        self._tz_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._tz_combo.setMinimumWidth(260)
        self._tz_combo.setToolTip(
            self.tr(
                "The garden's time zone. The plan's clock, its sun and a camera "
                "tour's time range use it. Leave it on the computer's zone when "
                "the garden is where this computer is."
            )
        )
        self._tz_combo.addItem(self.tr("Same as this computer"), None)
        for name in timezone_names():
            self._tz_combo.addItem(name, name)
        completer = self._tz_combo.completer()
        if completer is not None:
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        tz_row = QHBoxLayout()
        tz_row.addWidget(self._tz_combo)
        tz_row.addStretch()
        coords_layout.addRow(self.tr("Time zone:"), tz_row)

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
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
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
        self._select_timezone(plan_timezone_name(location))

    def _select_timezone(self, name: str | None) -> None:
        """Select a stored zone, keeping an unknown name visible for the user."""
        if not name:
            self._tz_combo.setCurrentIndex(0)
            return
        index = self._tz_combo.findData(name)
        if index < 0:
            # A hand-edited or newer plan names a zone this tzdata does not
            # know; show it rather than silently claiming the computer's.
            self._tz_combo.addItem(name, name)
            index = self._tz_combo.count() - 1
        self._tz_combo.setCurrentIndex(index)

    def _selected_timezone(self) -> str | None:
        """The zone name the user chose or typed, or ``None`` for the computer's.

        The combo is editable, and ``currentData()`` keeps the *item* that was
        selected before the user typed over it. The text is the truth: the
        IANA names are both the item labels and their values.
        """
        typed = self._tz_combo.currentText().strip()
        same_as_computer = self._tz_combo.itemText(0).strip()
        if not typed or typed.casefold() == same_as_computer.casefold():
            return None
        return typed

    def _has_explicit_timezone(self) -> bool:
        """A zone the user chose, or the one the plan already stored.

        A value the lookup itself filled is neither: a second lookup may update
        it until the user touches the field.
        """
        return self._timezone_touched or (
            self._initial_timezone is not None
            and self._selected_timezone() == self._initial_timezone
        )

    def _validate_frost_date(self, value: str) -> bool:
        """Return True if value is empty or names a real MM-DD date.

        Delegates to the shared validator (#414) so this dialog, the task
        generators and the agent cannot disagree about what a frost date is. The
        previous local regex accepted six dates that never exist (02-30, 02-31,
        04-31, 06-31, 09-31, 11-31); accepting one produced a plan whose frost
        date parsed to nothing, i.e. a plan that silently showed no tasks.
        02-29 stays valid — it is real in a leap year, and the shared parser
        substitutes 1 March in a year that has none.
        """
        return is_valid_frost_date(value)

    def _on_accept(self) -> None:
        """Validate inputs before accepting."""
        if self._map_link_pending:
            return
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

        zone_name = self._selected_timezone()
        keeps_an_unknown_stored_zone = (
            zone_name is not None and zone_name == self._initial_timezone
        )
        if (
            zone_name is not None
            and not keeps_an_unknown_stored_zone
            and plan_timezone({LOCATION_TIMEZONE_KEY: zone_name}) is None
        ):
            self._tz_combo.setFocus()
            line_edit = self._tz_combo.lineEdit()
            if line_edit is not None:
                line_edit.selectAll()
            QMessageBox.warning(
                self,
                self.tr("Unknown time zone"),
                self.tr("{name} is not a known time zone.").format(name=zone_name),
            )
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

        self._lookup_coordinates = (lat, lon)
        self._worker = _FrostLookupWorker(lat, lon)
        self._worker.success.connect(self._on_lookup_success)
        self._worker.error.connect(self._on_lookup_error)
        self._worker.finished.connect(self._on_lookup_finished)
        self._worker.start()

    def _on_lookup_success(self, frost_data: object) -> None:
        """Populate frost date fields with data returned by the worker."""
        from open_garden_planner.services.climate_service import FrostData

        if not isinstance(frost_data, FrostData) or not self._lookup_matches_location():
            return

        if frost_data.last_spring_frost:
            self._spring_frost_edit.setText(frost_data.last_spring_frost)

        if frost_data.first_fall_frost:
            self._fall_frost_edit.setText(frost_data.first_fall_frost)

        if frost_data.hardiness_zone and not self._zone_edit.text().strip():
            self._zone_edit.setText(frost_data.hardiness_zone)

        # The API answered with the coordinates' own zone: offer it unless the
        # user already chose one (#945).
        if frost_data.timezone and not self._has_explicit_timezone():
            self._select_timezone(frost_data.timezone)

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

    def _lookup_matches_location(self) -> bool:
        return self._lookup_coordinates in (None, (self._lat_spin.value(), self._lon_spin.value()))

    def _on_lookup_error(self, error_msg: str) -> None:
        """Show an error message when the lookup fails."""
        if not self._lookup_matches_location():
            return
        self._status_label.setText(
            self.tr("Lookup failed: {error}").format(error=error_msg)
        )
        self._status_label.setStyleSheet(
            f"color: {theme_color('error')}; font-size: 11px;"
        )

    def _on_lookup_finished(self) -> None:
        """Re-enable the lookup button after the worker finishes."""
        if not self._lookup_matches_location():
            self._status_label.clear()
        self._lookup_coordinates = None
        self._lookup_btn.setEnabled(not self._map_link_pending)
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
        zone_name = self._selected_timezone()
        if zone_name is not None:
            data[LOCATION_TIMEZONE_KEY] = zone_name

        return data
