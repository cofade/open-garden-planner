"""Integration tests for the satellite-background workflow."""

# ruff: noqa: ARG002

from __future__ import annotations

import time
from threading import Event
from unittest.mock import MagicMock

# QtWebEngineWidgets must be imported before QApplication is created. The
# dialog itself imports it, so loading the module early — at the top of
# this test file — keeps the test running with qtbot's app.
from PyQt6 import QtWebEngineWidgets  # noqa: F401, I001
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

import open_garden_planner.ui.dialogs.map_picker_dialog as map_picker_mod  # noqa: F401
from open_garden_planner.services.google_maps_service import (
    BoundingBox,
    FetchCancelled,
    FetchResult,
)


class _DummyWebView(QWidget):
    """Browser seam stub; the real picker dialog and bridge remain in use."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._page = MagicMock()
        self._settings = MagicMock()

    def page(self):  # noqa: D401
        return self._page

    def settings(self):  # noqa: D401
        return self._settings

    def setUrl(self, *_args, **_kwargs) -> None:
        pass


def _menu_action(win, label_fragment: str) -> QAction | None:
    """Find a top-level menu action whose text contains ``label_fragment``."""
    for menu_action in win.menuBar().actions():
        menu = menu_action.menu()
        if menu is None:
            continue
        for act in menu.actions():
            if label_fragment in act.text().replace("&", ""):
                return act
    return None


class TestMenuActionGating:
    def test_action_disabled_when_no_key(self, qtbot, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None
        assert action.isEnabled() is False

    def test_action_enabled_when_key_set(self, qtbot, monkeypatch) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        from open_garden_planner.app.application import GardenPlannerApp

        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None
        assert action.isEnabled() is True

    def test_action_enabled_when_preference_key_is_set(self, qtbot, monkeypatch) -> None:
        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.app.settings import get_settings

        get_settings().google_maps_api_key = "preference-key"
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")

        assert action is not None
        assert action.isEnabled() is True

    def test_preference_key_takes_precedence_over_environment(
        self, qtbot, monkeypatch
    ) -> None:
        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "environment-key")
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.app.settings import get_settings

        get_settings().google_maps_api_key = "preference-key"
        win = GardenPlannerApp()
        qtbot.addWidget(win)

        assert win._resolved_google_maps_api_key() == "preference-key"

    def test_preferences_save_clear_and_import_workflow(
        self, qtbot, monkeypatch
    ) -> None:
        """Real Preferences save/clear drives the menu and picker boundary."""
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.app.settings import get_settings
        from open_garden_planner.ui.dialogs.preferences_dialog import (
            PreferencesDialog,
        )

        monkeypatch.delenv("OGP_GOOGLE_MAPS_KEY", raising=False)
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None
        assert action.isEnabled() is False
        preferences_action = _menu_action(win, "Preferences")
        assert preferences_action is not None
        completed = 0

        def _save_preferences(value: str) -> None:
            nonlocal completed
            dialog = QApplication.activeModalWidget()
            if not isinstance(dialog, PreferencesDialog):
                return
            dialog._google_maps_key.setText(value)
            save_button = next(
                button
                for button in dialog.findChildren(QPushButton)
                if button.text() == dialog.tr("Save")
            )
            save_button.click()
            completed += 1

        QTimer.singleShot(0, lambda: _save_preferences("preference-key"))
        preferences_action.trigger()

        assert get_settings().google_maps_api_key == "preference-key"
        assert completed == 1

        from PIL import Image

        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        fake_result = FetchResult(
            image=Image.new("RGB", (10, 10)),
            meters_per_pixel=0.3,
            zoom=19,
            bbox=BoundingBox(52.521, 13.404, 52.519, 13.406),
            tile_grid=(1, 1),
        )
        captured_api_key = ""
        captured_fetch_keys: list[str] = []
        real_init = MapPickerDialog.__init__

        def _init_and_schedule(self, parent=None, *, api_key=None) -> None:
            nonlocal captured_api_key
            captured_api_key = api_key or ""
            real_init(self, parent, api_key=api_key)
            self._bbox = fake_result.bbox
            QTimer.singleShot(0, self._on_accept)

        monkeypatch.setattr(map_picker_mod, "QWebEngineView", _DummyWebView)
        monkeypatch.setattr(MapPickerDialog, "__init__", _init_and_schedule)
        monkeypatch.setattr(
            map_picker_mod,
            "fetch_bbox",
            lambda *_args, **kwargs: (
                captured_fetch_keys.append(kwargs["api_key"]) or fake_result
            ),
        )
        action.trigger()

        # The real import path marks the project dirty. Mark it clean before
        # pytest-qt closes the window so closeEvent does not open a modal save
        # prompt during headless teardown.
        win._project_manager.mark_clean()
        assert action.isEnabled() is True
        assert captured_api_key == "preference-key"
        assert captured_fetch_keys[-1] == "preference-key"
        assert any(
            item.__class__.__name__ == "BackgroundImageItem"
            for item in win.canvas_scene.items()
        )

        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "environment-key")

        QTimer.singleShot(0, lambda: _save_preferences(""))
        preferences_action.trigger()

        assert get_settings().google_maps_api_key == ""
        assert completed == 2
        assert win._resolved_google_maps_api_key() == "environment-key"
        assert action.isEnabled() is True

        action.trigger()
        win._project_manager.mark_clean()
        assert captured_api_key == "environment-key"
        assert captured_fetch_keys[-1] == "environment-key"

    def test_application_close_cancels_active_satellite_picker(
        self, qtbot, monkeypatch
    ) -> None:
        """Main-window shutdown waits for an active picker worker to finish."""
        from open_garden_planner.app.application import GardenPlannerApp
        from open_garden_planner.ui.dialogs.map_picker_dialog import MapPickerDialog

        monkeypatch.setenv("OGP_GOOGLE_MAPS_KEY", "TEST_KEY")
        win = GardenPlannerApp()
        qtbot.addWidget(win)
        action = _menu_action(win, "Satellite")
        assert action is not None

        started = Event()

        def _blocking_fetch(*_args, cancel_check=None, **_kwargs):
            started.set()
            while cancel_check is not None and not cancel_check():
                time.sleep(0.001)
            raise FetchCancelled("cancelled")

        real_init = MapPickerDialog.__init__

        def _init_and_start(self, parent=None, *, api_key=None) -> None:
            real_init(self, parent, api_key=api_key)
            self._bbox = BoundingBox(52.521, 13.404, 52.519, 13.406)
            QTimer.singleShot(0, self._on_accept)

        monkeypatch.setattr(map_picker_mod, "QWebEngineView", _DummyWebView)
        monkeypatch.setattr(MapPickerDialog, "__init__", _init_and_start)
        monkeypatch.setattr(map_picker_mod, "fetch_bbox", _blocking_fetch)

        def _close_when_fetch_starts() -> None:
            if started.is_set():
                win.close()
            else:
                QTimer.singleShot(1, _close_when_fetch_starts)

        QTimer.singleShot(0, _close_when_fetch_starts)
        action.trigger()
        qtbot.waitUntil(lambda: not win.isVisible(), timeout=3000)

        assert win._active_satellite_picker is None
