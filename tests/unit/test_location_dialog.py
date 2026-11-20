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


class TestTypedZone:
    def test_a_typed_iana_name_is_accepted(self, qtbot) -> None:
        dialog = _dialog(qtbot)
        dialog._tz_combo.setEditText("America/New_York")
        assert dialog._selected_timezone() == "America/New_York"
        assert dialog.location_data["timezone"] == "America/New_York"

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
