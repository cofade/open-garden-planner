"""Persist & restore window geometry and splitter sizes.

Thin wrapper around the settings backend so that the application doesn't
sprinkle raw key strings throughout `application.py`. Keys live under the
`UiState/` group so they don't collide with app-domain settings handled by
`app/settings.py`.

Note: per-panel collapse/expand state is intentionally NOT persisted. The
sidebar accordion always starts fully collapsed every session (US-226,
ADR-030), so the old ``save_panel_state`` / ``restore_panel_state`` helpers
were removed.
"""

from PyQt6.QtWidgets import QMainWindow, QSplitter

from open_garden_planner.app import settings as app_settings


class UiStateStore:
    """Persist and restore UI-only state (window geometry + main splitter)."""

    GROUP = "UiState"

    def __init__(self) -> None:
        # Same backend as everything else in the app, via the one chokepoint
        # (issue #285, ADR-041) — this store used to build its own and so
        # escaped the test isolation layered on AppSettings (docs §11.4).
        # Called module-qualified on purpose: `app_settings.create_qsettings`
        # is then the single name a test can patch to redirect every consumer.
        self._settings = app_settings.create_qsettings()

    def save_geometry(self, window: QMainWindow) -> None:
        self._settings.setValue(f"{self.GROUP}/geometry", window.saveGeometry())
        self._settings.setValue(f"{self.GROUP}/window_state", window.saveState())

    def restore_geometry(self, window: QMainWindow) -> bool:
        geom = self._settings.value(f"{self.GROUP}/geometry")
        if geom is None:
            return False
        window.restoreGeometry(geom)
        state = self._settings.value(f"{self.GROUP}/window_state")
        if state is not None:
            window.restoreState(state)
        return True

    def save_splitter(self, name: str, splitter: QSplitter) -> None:
        self._settings.setValue(f"{self.GROUP}/splitter_{name}", splitter.saveState())

    def restore_splitter(self, name: str, splitter: QSplitter) -> bool:
        state = self._settings.value(f"{self.GROUP}/splitter_{name}")
        if state is None:
            return False
        splitter.restoreState(state)
        return True
