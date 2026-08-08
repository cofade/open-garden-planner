"""Integration test: Preferences dialog 'Test' button for Permapeople (issue #294).

End-to-end workflow: user types credentials into the Preferences dialog and
really clicks the Test button (found the same way
``test_connect_ai_assistant_dialog.py`` does -- by group-box title, then by
button text). Only the HTTP layer (``requests.Session.get``) is mocked, so a
regression in the dialog wiring, the client's request shape, or the
success/failure/error message routing is caught.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QGroupBox, QPushButton

from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog

_PERMAPEOPLE_GROUP_TITLE = "Permapeople (permapeople.org)"


def _fake_response(status_code: int) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    return response


def _group(dialog: PreferencesDialog, title: str) -> QGroupBox:
    for group in dialog.findChildren(QGroupBox):
        if group.title() == title:
            return group
    raise AssertionError(f"No group box titled {title!r}")


def _permapeople_test_button(dialog: PreferencesDialog) -> QPushButton:
    group = _group(dialog, _PERMAPEOPLE_GROUP_TITLE)
    return next(b for b in group.findChildren(QPushButton) if b.text() == "Test")


@pytest.fixture()
def dialog(qtbot) -> PreferencesDialog:
    dlg = PreferencesDialog()
    qtbot.addWidget(dlg)
    return dlg


def _enter_permapeople_credentials(dialog: PreferencesDialog, key_id: str, key_secret: str) -> None:
    dialog._permapeople_key_id.setText(key_id)
    dialog._permapeople_key_secret.setText(key_secret)


class TestPermapeopleTestButton:
    def test_valid_credentials_report_success(
        self, dialog: PreferencesDialog, monkeypatch: pytest.MonkeyPatch, qtbot
    ) -> None:
        """Happy-path control: valid credentials must still report success
        (passes before and after the #294 fix -- the other tests in this class
        are the actual regression pins for the false-negative behaviour).
        """
        _enter_permapeople_credentials(dialog, "real-key-id", "real-key-secret")
        monkeypatch.setattr(
            "requests.Session.get", MagicMock(return_value=_fake_response(200))
        )

        with (
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.information"
            ) as mock_info,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.warning"
            ) as mock_warn,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.critical"
            ) as mock_critical,
        ):
            qtbot.mouseClick(_permapeople_test_button(dialog), Qt.MouseButton.LeftButton)

        mock_info.assert_called_once()
        mock_warn.assert_not_called()
        mock_critical.assert_not_called()

    def test_invalid_credentials_report_failure(
        self, dialog: PreferencesDialog, monkeypatch: pytest.MonkeyPatch, qtbot
    ) -> None:
        """A genuine 401 (bad credentials) must still surface 'Test Failed' --
        the fix must not paper over real auth failures.
        """
        _enter_permapeople_credentials(dialog, "bad-key-id", "bad-key-secret")
        mock_get = MagicMock(return_value=_fake_response(401))
        monkeypatch.setattr("requests.Session.get", mock_get)

        with (
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.information"
            ) as mock_info,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.warning"
            ) as mock_warn,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.critical"
            ) as mock_critical,
        ):
            qtbot.mouseClick(_permapeople_test_button(dialog), Qt.MouseButton.LeftButton)

        # Bound, not just patched: proves the click actually reached the HTTP
        # layer rather than short-circuiting on the dialog's own field-empty
        # check (which also routes through QMessageBox.warning).
        mock_get.assert_called_once()
        mock_warn.assert_called_once()
        mock_info.assert_not_called()
        mock_critical.assert_not_called()

    def test_network_timeout_reports_error_not_credentials_failure(
        self, dialog: PreferencesDialog, monkeypatch: pytest.MonkeyPatch, qtbot
    ) -> None:
        """The actual root-cause fix, proven through the real button click: a
        connectivity failure (timeout/DNS/reset) must surface as a distinct
        error, not get relabeled 'check your credentials' -- the false
        accusation #294 reported would otherwise still be reachable on a slow
        connection even after the per_page fix.
        """
        _enter_permapeople_credentials(dialog, "real-key-id", "real-key-secret")
        monkeypatch.setattr(
            "requests.Session.get",
            MagicMock(side_effect=requests.exceptions.ReadTimeout("timed out")),
        )

        with (
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.information"
            ) as mock_info,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.warning"
            ) as mock_warn,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.critical"
            ) as mock_critical,
        ):
            qtbot.mouseClick(_permapeople_test_button(dialog), Qt.MouseButton.LeftButton)

        mock_critical.assert_called_once()
        mock_warn.assert_not_called()
        mock_info.assert_not_called()

    def test_server_error_reports_error_not_credentials_failure(
        self, dialog: PreferencesDialog, monkeypatch: pytest.MonkeyPatch, qtbot
    ) -> None:
        """A 5xx/429 is a server-side problem, exercised through the real
        button click: it must surface as 'Test Error', not get relabeled
        'check your credentials' the way a bare False would (issue #294
        follow-up -- an outage must not read as a credentials rejection).
        """
        _enter_permapeople_credentials(dialog, "real-key-id", "real-key-secret")
        monkeypatch.setattr(
            "requests.Session.get", MagicMock(return_value=_fake_response(503))
        )

        with (
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.information"
            ) as mock_info,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.warning"
            ) as mock_warn,
            patch(
                "open_garden_planner.ui.dialogs.preferences_dialog.QMessageBox.critical"
            ) as mock_critical,
        ):
            qtbot.mouseClick(_permapeople_test_button(dialog), Qt.MouseButton.LeftButton)

        mock_critical.assert_called_once()
        mock_warn.assert_not_called()
        mock_info.assert_not_called()
