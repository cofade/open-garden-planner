"""UI tests for the Language submenu in the View menu."""

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.i18n import SUPPORTED_LANGUAGES


class TestLanguageMenu:
    """Tests for the Language submenu."""

    def _get_view_menu(self, window):
        """Helper to get the View menu from the menu bar."""
        for action in window.menuBar().actions():
            if action.text() == "&View":
                return action.menu()
        return None

    def _get_language_submenu(self, window):
        """Helper to get the Language submenu from the View menu."""
        view_menu = self._get_view_menu(window)
        if view_menu is None:
            return None
        for action in view_menu.actions():
            if action.menu() and "Language" in action.text().replace("&", ""):
                return action.menu()
        return None

    def test_language_submenu_exists(self, qtbot) -> None:
        """Test that Language submenu exists in the View menu."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        language_menu = self._get_language_submenu(window)
        assert language_menu is not None, "Language submenu not found in View menu"

    def test_english_action_exists(self, qtbot) -> None:
        """Test that English language action exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        language_menu = self._get_language_submenu(window)
        action_texts = [a.text() for a in language_menu.actions()]
        assert "English" in action_texts

    def test_german_action_exists(self, qtbot) -> None:
        """Test that German language action exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        language_menu = self._get_language_submenu(window)
        action_texts = [a.text() for a in language_menu.actions()]
        assert "Deutsch" in action_texts

    def test_all_supported_languages_present(self, qtbot) -> None:
        """Test that all supported languages have menu actions."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        language_menu = self._get_language_submenu(window)
        action_texts = [a.text() for a in language_menu.actions()]
        for native_name in SUPPORTED_LANGUAGES.values():
            assert native_name in action_texts, (
                f"Language '{native_name}' not found in menu"
            )

    def test_language_actions_are_checkable(self, qtbot) -> None:
        """Test that language actions are checkable (radio-style)."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        language_menu = self._get_language_submenu(window)
        for action in language_menu.actions():
            assert action.isCheckable(), (
                f"Language action '{action.text()}' is not checkable"
            )

    def test_language_actions_dict_populated(self, qtbot) -> None:
        """Test that _language_actions dict is populated."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert hasattr(window, "_language_actions")
        assert len(window._language_actions) == len(SUPPORTED_LANGUAGES)
        for lang_code in SUPPORTED_LANGUAGES:
            assert lang_code in window._language_actions

    def test_exactly_one_language_checked(self, qtbot) -> None:
        """Test that exactly one language action is checked."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)

        # Process deferred timer (QTimer.singleShot(0, ...))
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

        checked = [
            lc for lc, action in window._language_actions.items()
            if action.isChecked()
        ]
        assert len(checked) == 1, (
            f"Expected exactly 1 checked language, got {len(checked)}: {checked}"
        )
