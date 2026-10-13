"""Fail-closed startup for an unprotectable Linux settings store."""

from pathlib import Path
from unittest.mock import patch

from open_garden_planner import main as entrypoint
from open_garden_planner.app.settings import SettingsSecurityError


def test_security_failure_is_visible_and_stops_before_main_window(qapp, monkeypatch):
    # Reuse pytest-qt's application instead of creating a second QApplication.
    with patch("PyQt6.QtWidgets.QApplication", return_value=qapp), \
         patch("PyQt6.QtWidgets.QMessageBox.critical") as error, \
         patch("open_garden_planner.app.settings.get_settings", side_effect=SettingsSecurityError(Path("fixture.conf"))), \
         patch("open_garden_planner.app.application.GardenPlannerApp") as window, \
         patch("open_garden_planner.core.logging_config.setup_logging"), \
         patch("open_garden_planner.core.i18n.load_translator"):
        assert entrypoint.main() == 1
    window.assert_not_called()
    error.assert_called_once()
    assert "fixture.conf" in error.call_args.args[2]
