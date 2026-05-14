"""Persist & restore window geometry, splitter sizes, and panel collapse state.

Thin wrapper around `QSettings` so that the application doesn't sprinkle
raw key strings throughout `application.py`. Keys live under the `UiState/`
group so they don't collide with app-domain settings handled by
`app/settings.py`.
"""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow, QSplitter


class UiStateStore:
    """Persist and restore UI-only state (window/splitter/panel)."""

    GROUP = "UiState"

    def __init__(self) -> None:
        # Use the same explicit (org, app) tuple as app/settings.py so both
        # stores read/write the same QSettings backend regardless of whether
        # main.py has already called setOrganizationName/setApplicationName.
        self._settings = QSettings("cofade", "Open Garden Planner")

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

    def save_panel_state(self, key: str, expanded: bool) -> None:
        self._settings.setValue(f"{self.GROUP}/panel_{key}", expanded)

    def restore_panel_state(self, key: str, default: bool) -> bool:
        raw = self._settings.value(f"{self.GROUP}/panel_{key}")
        if raw is None:
            return default
        # QSettings on some platforms stores bools as strings.
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            return raw.lower() in ("true", "1", "yes")
        return bool(raw)
