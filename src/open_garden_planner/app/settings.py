"""Application settings management.

Provides persistent storage for user preferences using QSettings.
"""

from PyQt6.QtCore import QSettings


class AppSettings:
    """Manages application settings using Qt's QSettings.

    Settings are stored in the system's native location:
    - Windows: Registry (HKEY_CURRENT_USER/Software/cofade/Open Garden Planner)
    - macOS: ~/Library/Preferences/com.cofade.Open Garden Planner.plist
    - Linux: ~/.config/cofade/Open Garden Planner.conf
    """

    # Settings keys
    KEY_AUTOSAVE_ENABLED = "autosave/enabled"
    KEY_AUTOSAVE_INTERVAL_MINUTES = "autosave/interval_minutes"
    KEY_RECENT_FILES = "recent_files"
    KEY_WINDOW_GEOMETRY = "window/geometry"
    KEY_WINDOW_STATE = "window/state"

    # Default values
    DEFAULT_AUTOSAVE_ENABLED = True
    DEFAULT_AUTOSAVE_INTERVAL_MINUTES = 5
    MIN_AUTOSAVE_INTERVAL_MINUTES = 1
    MAX_AUTOSAVE_INTERVAL_MINUTES = 30

    def __init__(self) -> None:
        """Initialize the settings manager."""
        self._settings = QSettings("cofade", "Open Garden Planner")

    @property
    def autosave_enabled(self) -> bool:
        """Whether auto-save is enabled."""
        return self._settings.value(
            self.KEY_AUTOSAVE_ENABLED,
            self.DEFAULT_AUTOSAVE_ENABLED,
            type=bool,
        )

    @autosave_enabled.setter
    def autosave_enabled(self, enabled: bool) -> None:
        """Set whether auto-save is enabled."""
        self._settings.setValue(self.KEY_AUTOSAVE_ENABLED, enabled)

    @property
    def autosave_interval_minutes(self) -> int:
        """Auto-save interval in minutes."""
        value = self._settings.value(
            self.KEY_AUTOSAVE_INTERVAL_MINUTES,
            self.DEFAULT_AUTOSAVE_INTERVAL_MINUTES,
            type=int,
        )
        # Clamp to valid range
        return max(
            self.MIN_AUTOSAVE_INTERVAL_MINUTES,
            min(self.MAX_AUTOSAVE_INTERVAL_MINUTES, value),
        )

    @autosave_interval_minutes.setter
    def autosave_interval_minutes(self, minutes: int) -> None:
        """Set the auto-save interval in minutes."""
        clamped = max(
            self.MIN_AUTOSAVE_INTERVAL_MINUTES,
            min(self.MAX_AUTOSAVE_INTERVAL_MINUTES, minutes),
        )
        self._settings.setValue(self.KEY_AUTOSAVE_INTERVAL_MINUTES, clamped)

    @property
    def recent_files(self) -> list[str]:
        """List of recently opened file paths."""
        value = self._settings.value(self.KEY_RECENT_FILES, [], type=list)
        return [str(f) for f in value] if value else []

    @recent_files.setter
    def recent_files(self, files: list[str]) -> None:
        """Set the list of recent files."""
        self._settings.setValue(self.KEY_RECENT_FILES, files)

    def add_recent_file(self, file_path: str, max_files: int = 10) -> None:
        """Add a file to the recent files list.

        Args:
            file_path: Path to the file to add
            max_files: Maximum number of recent files to keep
        """
        files = self.recent_files
        # Remove if already in list (will be moved to front)
        if file_path in files:
            files.remove(file_path)
        # Add to front
        files.insert(0, file_path)
        # Truncate to max
        self.recent_files = files[:max_files]

    def clear_recent_files(self) -> None:
        """Clear the recent files list."""
        self.recent_files = []

    @property
    def window_geometry(self) -> bytes | None:
        """Window geometry as bytes (for QMainWindow.restoreGeometry)."""
        value = self._settings.value(self.KEY_WINDOW_GEOMETRY)
        return bytes(value) if value else None

    @window_geometry.setter
    def window_geometry(self, geometry: bytes) -> None:
        """Save window geometry."""
        self._settings.setValue(self.KEY_WINDOW_GEOMETRY, geometry)

    @property
    def window_state(self) -> bytes | None:
        """Window state as bytes (for QMainWindow.restoreState)."""
        value = self._settings.value(self.KEY_WINDOW_STATE)
        return bytes(value) if value else None

    @window_state.setter
    def window_state(self, state: bytes) -> None:
        """Save window state."""
        self._settings.setValue(self.KEY_WINDOW_STATE, state)

    def sync(self) -> None:
        """Force settings to be written to storage."""
        self._settings.sync()


# Singleton instance
_settings_instance: AppSettings | None = None


def get_settings() -> AppSettings:
    """Get the global settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = AppSettings()
    return _settings_instance
