"""Tests for the Welcome dialog."""

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QListWidget, QPushButton

from open_garden_planner.app.settings import get_settings
from open_garden_planner.ui.dialogs import WelcomeDialog


class TestWelcomeDialog:
    """Tests for WelcomeDialog."""

    @pytest.fixture(autouse=True)
    def setup(self, qtbot):  # noqa: ARG002
        """Set up test fixtures."""
        # Clear recent files before each test
        get_settings().clear_recent_files()

    def test_dialog_creation(self, qtbot):  # noqa: ARG002
        """Test that dialog can be created."""
        dialog = WelcomeDialog()
        assert dialog is not None

    def test_dialog_title(self, qtbot):  # noqa: ARG002
        """Test dialog has correct title."""
        dialog = WelcomeDialog()
        assert "Welcome" in dialog.windowTitle()

    def test_dialog_is_modal(self, qtbot):  # noqa: ARG002
        """Test dialog is modal."""
        dialog = WelcomeDialog()
        assert dialog.isModal()

    def test_dialog_has_new_project_button(self, qtbot):  # noqa: ARG002
        """Test dialog has New Project button."""
        dialog = WelcomeDialog()
        buttons = dialog.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]
        assert "New Project" in button_texts

    def test_dialog_has_open_project_button(self, qtbot):  # noqa: ARG002
        """Test dialog has Open Project button."""
        dialog = WelcomeDialog()
        buttons = dialog.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]
        assert "Open Project..." in button_texts

    def test_dialog_has_recent_list(self, qtbot):  # noqa: ARG002
        """Test dialog has recent projects list."""
        dialog = WelcomeDialog()
        list_widget = dialog.findChild(QListWidget)
        assert list_widget is not None

    def test_dialog_has_checkbox(self, qtbot):  # noqa: ARG002
        """Test dialog has 'show on startup' checkbox."""
        dialog = WelcomeDialog()
        checkbox = dialog.findChild(QCheckBox)
        assert checkbox is not None
        assert "startup" in checkbox.text().lower()

    def test_new_project_signal(self, qtbot):  # noqa: ARG002
        """Test new project signal is emitted."""
        dialog = WelcomeDialog()
        buttons = dialog.findChildren(QPushButton)
        new_button = next(b for b in buttons if b.text() == "New Project")

        with qtbot.waitSignal(dialog.new_project_requested):
            new_button.click()

    def test_open_project_signal(self, qtbot):  # noqa: ARG002
        """Test open project signal is emitted."""
        dialog = WelcomeDialog()
        buttons = dialog.findChildren(QPushButton)
        open_button = next(b for b in buttons if b.text() == "Open Project...")

        with qtbot.waitSignal(dialog.open_project_requested):
            open_button.click()

    def test_checkbox_updates_settings(self, qtbot):  # noqa: ARG002
        """Test checkbox updates settings."""
        dialog = WelcomeDialog()
        checkbox = dialog.findChild(QCheckBox)

        # Uncheck the checkbox
        checkbox.setChecked(False)
        assert not get_settings().show_welcome_on_startup

        # Check the checkbox
        checkbox.setChecked(True)
        assert get_settings().show_welcome_on_startup

    def test_empty_recent_shows_placeholder(self, qtbot):  # noqa: ARG002
        """Test empty recent list shows placeholder."""
        dialog = WelcomeDialog()
        list_widget = dialog.findChild(QListWidget)

        assert list_widget.count() == 1
        item = list_widget.item(0)
        assert "No recent" in item.text()
        # Placeholder should not be selectable
        assert not (item.flags() & Qt.ItemFlag.ItemIsSelectable)

    def test_clear_recent_button(self, qtbot):  # noqa: ARG002
        """Test clear recent button exists."""
        dialog = WelcomeDialog()
        buttons = dialog.findChildren(QPushButton)
        button_texts = [b.text() for b in buttons]
        assert "Clear Recent" in button_texts

    def test_minimum_size(self, qtbot):  # noqa: ARG002
        """Test dialog has minimum size."""
        dialog = WelcomeDialog()
        assert dialog.minimumWidth() >= 400
        assert dialog.minimumHeight() >= 300
