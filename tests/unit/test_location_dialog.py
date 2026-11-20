"""#945 - the Location dialog names the plan's time zone."""

from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.ui.dialogs.location_dialog import LocationDialog


def _dialog(qtbot, location: dict | None = None) -> LocationDialog:
    dialog = LocationDialog(location=location)
    qtbot.addWidget(dialog)
    return dialog


class TestStoredZone:
    def test_an_existing_zone_is_selected_and_round_trips(self, qtbot) -> None:
        dialog = _dialog(
            qtbot,
            {
                "latitude": 35.0,
                "longitude": 135.8,
                "timezone": "Asia/Tokyo",
            },
        )
        assert dialog._selected_timezone() == "Asia/Tokyo"
        assert dialog.location_data["timezone"] == "Asia/Tokyo"

    def test_no_zone_means_the_computer(self, qtbot) -> None:
        dialog = _dialog(qtbot, {"latitude": 52.5, "longitude": 13.4})
        assert dialog._selected_timezone() is None
        assert "timezone" not in dialog.location_data

    def test_an_unknown_stored_name_stays_visible(self, qtbot) -> None:
        """A hand-edited plan must show what it holds, not claim the computer's."""
        dialog = _dialog(qtbot, {"latitude": 1.0, "longitude": 2.0,
                                 "timezone": "Mars/Olympus_Mons"})
        assert dialog._selected_timezone() == "Mars/Olympus_Mons"
        assert dialog.location_data["timezone"] == "Mars/Olympus_Mons"

    def test_an_unchanged_unknown_stored_name_does_not_block_accept(
        self, qtbot, monkeypatch
    ) -> None:
        """It is already treated as absent on load; do not trap other edits."""
        dialog = _dialog(qtbot, {"latitude": 1.0, "longitude": 2.0,
                                 "timezone": "Mars/Olympus_Mons"})
        accepted: list[bool] = []
        warnings: list[str] = []
        monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))
        monkeypatch.setattr(
            QMessageBox, "warning", lambda *_a, **_k: warnings.append("warning")
        )
        dialog._on_accept()
        assert accepted == [True]
        assert warnings == []


class TestTypedZone:
    def test_a_typed_iana_name_is_accepted(self, qtbot) -> None:
        dialog = _dialog(qtbot)
        dialog._tz_combo.setEditText("America/New_York")
        assert dialog._selected_timezone() == "America/New_York"
        assert dialog.location_data["timezone"] == "America/New_York"

    def test_typing_over_a_selected_zone_uses_the_typed_zone(self, qtbot) -> None:
        """The text is the truth; the selected item's data is stale once edited."""
        dialog = _dialog(qtbot, {"timezone": "Europe/Berlin"})
        assert dialog._selected_timezone() == "Europe/Berlin"

        dialog._tz_combo.setEditText("Asia/Tokyo")

        assert dialog._selected_timezone() == "Asia/Tokyo"
        assert dialog.location_data["timezone"] == "Asia/Tokyo"

    def test_a_lookup_does_not_overwrite_a_typed_zone(self, qtbot) -> None:
        from open_garden_planner.services.climate_service import FrostData

        dialog = _dialog(qtbot)
        dialog._tz_combo.setEditText("Europe/Paris")
        dialog._on_lookup_success(
            FrostData(
                last_spring_frost="04-15",
                first_fall_frost="10-20",
                hardiness_zone="7b",
                data_source="open-meteo",
                latitude=35.0,
                longitude=135.8,
                timezone="Asia/Tokyo",
            )
        )
        assert dialog._selected_timezone() == "Europe/Paris"

    def test_a_lookup_fills_an_untouched_zone(self, qtbot) -> None:
        from open_garden_planner.services.climate_service import FrostData

        dialog = _dialog(qtbot)
        dialog._on_lookup_success(
            FrostData(
                last_spring_frost="04-15",
                first_fall_frost="10-20",
                hardiness_zone="7b",
                data_source="open-meteo",
                latitude=35.0,
                longitude=135.8,
                timezone="Asia/Tokyo",
            )
        )
        assert dialog._selected_timezone() == "Asia/Tokyo"

    def test_a_lookup_does_not_overwrite_an_explicit_computer_zone(self, qtbot) -> None:
        """"Same as this computer" is a choice, not an untouched field."""
        from open_garden_planner.services.climate_service import FrostData

        dialog = _dialog(qtbot, {"timezone": "Europe/Berlin"})
        dialog._tz_combo.setCurrentIndex(0)
        assert dialog._selected_timezone() is None
        dialog._on_lookup_success(
            FrostData(
                last_spring_frost="04-15",
                first_fall_frost="10-20",
                hardiness_zone="7b",
                data_source="open-meteo",
                latitude=35.0,
                longitude=135.8,
                timezone="Asia/Tokyo",
            )
        )
        assert dialog._selected_timezone() is None

    def test_typing_then_selecting_uses_the_selected_zone(self, qtbot) -> None:
        dialog = _dialog(qtbot)
        dialog._tz_combo.setEditText("Asia/Tokyo")
        index = dialog._tz_combo.findData("Europe/Paris")
        assert index > 0

        dialog._tz_combo.setCurrentIndex(index)

        assert dialog._selected_timezone() == "Europe/Paris"
        assert dialog.location_data["timezone"] == "Europe/Paris"

    def test_the_same_as_computer_label_is_compared_case_insensitively(self, qtbot) -> None:
        dialog = _dialog(qtbot)
        label = dialog._tz_combo.itemText(0)
        dialog._tz_combo.setEditText(label.upper())
        assert dialog._selected_timezone() is None

    def test_an_unknown_typed_name_is_refused_with_a_message(
        self, qtbot, monkeypatch
    ) -> None:
        dialog = _dialog(qtbot)
        dialog._tz_combo.setEditText("Nowhere/Special")
        shown: list[tuple[str, str]] = []
        def warning(_parent, title, text, *_args, **_kwargs) -> None:
            shown.append((title, text))

        monkeypatch.setattr(QMessageBox, "warning", warning)
        accepted: list[bool] = []
        monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

        dialog._on_accept()

        assert accepted == []
        assert shown and "Nowhere/Special" in shown[0][1]
