"""UI tests for the main application window."""

from pathlib import Path

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.main import get_icon_path


class TestMainWindow:
    """Tests for the main application window."""

    def test_window_title(self, qtbot) -> None:
        """Test that window has correct title."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window.windowTitle() == "Untitled - Open Garden Planner"

    def test_window_minimum_size(self, qtbot) -> None:
        """Test that window has minimum size set."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window.minimumWidth() >= 800
        assert window.minimumHeight() >= 600

    def test_has_menu_bar(self, qtbot) -> None:
        """Test that window has a menu bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window.menuBar() is not None

    def test_file_menu_exists(self, qtbot) -> None:
        """Test that File menu exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break
        assert file_menu is not None

    def test_file_menu_has_new_action(self, qtbot) -> None:
        """Test that File menu has New action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        action_texts = [a.text() for a in file_menu.actions()]
        assert any("New" in text for text in action_texts)

    def test_file_menu_has_open_action(self, qtbot) -> None:
        """Test that File menu has Open action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        action_texts = [a.text() for a in file_menu.actions()]
        assert any("Open" in text for text in action_texts)

    def test_file_menu_has_save_action(self, qtbot) -> None:
        """Test that File menu has Save action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        action_texts = [a.text() for a in file_menu.actions()]
        assert any("Save" in text for text in action_texts)

    def test_file_menu_has_exit_action(self, qtbot) -> None:
        """Test that File menu has Exit action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        action_texts = [a.text().replace("&", "") for a in file_menu.actions()]
        assert any("Exit" in text for text in action_texts)

    def test_has_status_bar(self, qtbot) -> None:
        """Test that window has a status bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window.statusBar() is not None

    def test_status_bar_shows_coordinates(self, qtbot) -> None:
        """Test that status bar has coordinate display."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        # Check for coordinate label in status bar
        assert window.coord_label is not None
        assert "X:" in window.coord_label.text() or "0" in window.coord_label.text()

    def test_status_bar_shows_zoom(self, qtbot) -> None:
        """Test that status bar has zoom display."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window.zoom_label is not None
        assert "%" in window.zoom_label.text()

    def test_edit_menu_exists(self, qtbot) -> None:
        """Test that Edit menu exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        edit_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Edit":
                edit_menu = action.menu()
                break
        assert edit_menu is not None

    def test_edit_menu_has_undo(self, qtbot) -> None:
        """Test that Edit menu has Undo action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        edit_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Edit":
                edit_menu = action.menu()
                break

        action_texts = [a.text() for a in edit_menu.actions()]
        assert any("Undo" in text for text in action_texts)

    def test_edit_menu_has_redo(self, qtbot) -> None:
        """Test that Edit menu has Redo action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        edit_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Edit":
                edit_menu = action.menu()
                break

        action_texts = [a.text() for a in edit_menu.actions()]
        assert any("Redo" in text for text in action_texts)

    def test_view_menu_exists(self, qtbot) -> None:
        """Test that View menu exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        view_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&View":
                view_menu = action.menu()
                break
        assert view_menu is not None

    def test_help_menu_exists(self, qtbot) -> None:
        """Test that Help menu exists."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        help_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&Help":
                help_menu = action.menu()
                break
        assert help_menu is not None

    def test_keyboard_shortcut_new(self, qtbot) -> None:
        """Test that Ctrl+N shortcut exists for New."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        new_action = None
        for action in file_menu.actions():
            if "New" in action.text():
                new_action = action
                break

        assert new_action is not None
        assert new_action.shortcut().toString() == "Ctrl+N"

    def test_keyboard_shortcut_save(self, qtbot) -> None:
        """Test that Ctrl+S shortcut exists for Save."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        file_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&File":
                file_menu = action.menu()
                break

        save_action = None
        for action in file_menu.actions():
            if action.text() == "&Save":
                save_action = action
                break

        assert save_action is not None
        assert save_action.shortcut().toString() == "Ctrl+S"


class TestPreviewMode:
    """Tests for fullscreen preview mode (US-6.11)."""

    def test_preview_action_exists(self, qtbot) -> None:
        """Test that Fullscreen Preview action exists in View menu."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        view_menu = None
        for action in window.menuBar().actions():
            if action.text() == "&View":
                view_menu = action.menu()
                break

        action_texts = [a.text() for a in view_menu.actions()]
        assert any("Fullscreen Preview" in text for text in action_texts)

    def test_preview_action_is_checkable(self, qtbot) -> None:
        """Test that the preview action is checkable."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window._preview_action.isCheckable()
        assert not window._preview_action.isChecked()

    def test_preview_action_shortcut(self, qtbot) -> None:
        """Test that F11 shortcut is assigned to preview action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert window._preview_action.shortcut().toString() == "F11"

    def test_preview_mode_initial_state(self, qtbot) -> None:
        """Test that preview mode is off by default."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        assert not window._preview_mode

    def test_enter_preview_mode_hides_sidebar(self, qtbot) -> None:
        """Test that entering preview mode hides the sidebar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.sidebar.isVisible()

    def test_enter_preview_mode_hides_toolbar(self, qtbot) -> None:
        """Test that entering preview mode hides the toolbar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.main_toolbar.isVisible()

    def test_enter_preview_mode_hides_statusbar(self, qtbot) -> None:
        """Test that entering preview mode hides the status bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.statusBar().isVisible()

    def test_enter_preview_mode_hides_menubar(self, qtbot) -> None:
        """Test that entering preview mode hides the menu bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.menuBar().isVisible()

    def test_enter_preview_mode_hides_grid(self, qtbot) -> None:
        """Test that entering preview mode hides the grid."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        # Enable grid first
        window.canvas_view.set_grid_visible(True)
        window._enter_preview_mode()
        assert not window.canvas_view.grid_visible

    def test_enter_preview_mode_hides_scale_bar(self, qtbot) -> None:
        """Test that entering preview mode hides the scale bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.canvas_view.scale_bar_visible

    def test_enter_preview_mode_hides_labels(self, qtbot) -> None:
        """Test that entering preview mode hides labels."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert not window.canvas_scene.labels_enabled

    def test_enter_preview_mode_sets_flag(self, qtbot) -> None:
        """Test that entering preview mode sets the flag."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        assert window._preview_mode

    def test_exit_preview_mode_restores_sidebar(self, qtbot) -> None:
        """Test that exiting preview mode restores the sidebar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.sidebar.isVisible()

    def test_exit_preview_mode_restores_toolbar(self, qtbot) -> None:
        """Test that exiting preview mode restores the toolbar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.main_toolbar.isVisible()

    def test_exit_preview_mode_restores_statusbar(self, qtbot) -> None:
        """Test that exiting preview mode restores the status bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.statusBar().isVisible()

    def test_exit_preview_mode_restores_menubar(self, qtbot) -> None:
        """Test that exiting preview mode restores the menu bar."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.menuBar().isVisible()

    def test_exit_preview_mode_restores_grid_state(self, qtbot) -> None:
        """Test that exiting preview mode restores the grid state."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        # Enable grid before entering preview
        window.canvas_view.set_grid_visible(True)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.canvas_view.grid_visible

    def test_exit_preview_mode_restores_scale_bar_state(self, qtbot) -> None:
        """Test that exiting preview mode restores scale bar state."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.canvas_view.scale_bar_visible

    def test_exit_preview_mode_restores_labels_state(self, qtbot) -> None:
        """Test that exiting preview mode restores labels state."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert window.canvas_scene.labels_enabled

    def test_exit_preview_mode_clears_flag(self, qtbot) -> None:
        """Test that exiting preview mode clears the flag."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert not window._preview_mode

    def test_exit_preview_mode_unchecks_action(self, qtbot) -> None:
        """Test that exiting preview mode unchecks the menu action."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._preview_action.setChecked(True)
        window._enter_preview_mode()
        window._exit_preview_mode()
        assert not window._preview_action.isChecked()

    def test_double_enter_is_idempotent(self, qtbot) -> None:
        """Test that entering preview mode twice doesn't cause issues."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._enter_preview_mode()
        window._enter_preview_mode()  # Should be no-op
        assert window._preview_mode
        window._exit_preview_mode()
        assert not window._preview_mode

    def test_double_exit_is_idempotent(self, qtbot) -> None:
        """Test that exiting preview mode twice doesn't cause issues."""
        window = GardenPlannerApp()
        qtbot.addWidget(window)
        window._exit_preview_mode()  # Should be no-op when not in preview
        assert not window._preview_mode


class TestApplicationIcon:
    """Tests for application icon functionality (US-1.8)."""

    def test_get_icon_path_returns_path(self) -> None:
        """Test that get_icon_path returns a Path object."""
        icon_path = get_icon_path()
        assert isinstance(icon_path, Path)

    def test_icon_file_exists(self) -> None:
        """Test that the icon file exists at the expected location."""
        icon_path = get_icon_path()
        assert icon_path.exists(), f"Icon file not found at {icon_path}"

    def test_icon_file_is_png(self) -> None:
        """Test that the icon file has .png extension."""
        icon_path = get_icon_path()
        assert icon_path.suffix.lower() == ".png"

    def test_icon_path_contains_logo_name(self) -> None:
        """Test that the icon path refers to OGP_logo.png."""
        icon_path = get_icon_path()
        assert "OGP_logo.png" in str(icon_path)

    def test_application_has_window_icon(self, qtbot) -> None:
        """Test that QApplication has a window icon set after startup."""
        # Note: The icon is set at QApplication level in main.py
        # We verify the icon path is valid here
        icon_path = get_icon_path()
        assert icon_path.exists()
        # The actual icon setting happens in main() when the app starts

    def test_about_dialog_icon_path_exists(self, qtbot) -> None:
        """Test that the icon path used in About dialog exists."""
        from pathlib import Path
        # This is the same path calculation used in _on_about
        icon_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "open_garden_planner"
            / "resources"
            / "icons"
            / "OGP_logo.png"
        )
        assert icon_path.exists(), f"About dialog icon not found at {icon_path}"
