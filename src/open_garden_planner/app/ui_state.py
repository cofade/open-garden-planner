"""Persist & restore window geometry and splitter sizes.

Thin wrapper around `QSettings` so that the application doesn't sprinkle
raw key strings throughout `application.py`. Keys live under the `UiState/`
group so they don't collide with app-domain settings handled by
`app/settings.py`.

Note: per-panel collapse/expand state is intentionally NOT persisted. The
sidebar accordion always starts fully collapsed every session (US-226,
ADR-030), so the old ``save_panel_state`` / ``restore_panel_state`` helpers
were removed.
"""

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QMainWindow, QSplitter


class UiStateStore:
    """Persist and restore UI-only state (window geometry + main splitter)."""

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

    # ── Sun & shade simulation (US-E3) ──────────────────────────────
    # The last-used sim instant is UI state (like window geometry), NOT
    # project data — deliberately kept out of the .ogp.

    def save_sun_sim_time(self, iso_datetime: str) -> None:
        self._settings.setValue(f"{self.GROUP}/sun_sim_time", iso_datetime)

    def restore_sun_sim_time(self) -> str | None:
        value = self._settings.value(f"{self.GROUP}/sun_sim_time")
        return str(value) if value else None
