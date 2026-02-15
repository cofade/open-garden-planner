"""Application settings management.

Provides persistent storage for user preferences using QSettings.
"""

from PyQt6.QtCore import QSettings

from open_garden_planner.ui.theme import ThemeMode


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
    KEY_SHOW_WELCOME = "startup/show_welcome"
    KEY_THEME_MODE = "appearance/theme_mode"
    KEY_SHOW_SHADOWS = "appearance/show_shadows"
    KEY_SHOW_SCALE_BAR = "appearance/show_scale_bar"
    KEY_SHOW_LABELS = "appearance/show_labels"
    KEY_OBJECT_SNAP = "canvas/object_snap_enabled"
    KEY_LANGUAGE = "appearance/language"

    # API key settings
    KEY_TREFLE_API_TOKEN = "api_keys/trefle_token"
    KEY_PERENUAL_API_KEY = "api_keys/perenual_key"
    KEY_PERMAPEOPLE_KEY_ID = "api_keys/permapeople_key_id"
    KEY_PERMAPEOPLE_KEY_SECRET = "api_keys/permapeople_key_secret"

    # Default values
    DEFAULT_AUTOSAVE_ENABLED = True
    DEFAULT_SHOW_WELCOME = True
    DEFAULT_SHOW_SHADOWS = True
    DEFAULT_SHOW_SCALE_BAR = True
    DEFAULT_SHOW_LABELS = True
    DEFAULT_OBJECT_SNAP = True
    DEFAULT_LANGUAGE = "en"
    DEFAULT_AUTOSAVE_INTERVAL_MINUTES = 5
    MIN_AUTOSAVE_INTERVAL_MINUTES = 1
    MAX_AUTOSAVE_INTERVAL_MINUTES = 30
    DEFAULT_THEME_MODE = "system"

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
    def show_welcome_on_startup(self) -> bool:
        """Whether to show welcome screen on startup."""
        return self._settings.value(
            self.KEY_SHOW_WELCOME,
            self.DEFAULT_SHOW_WELCOME,
            type=bool,
        )

    @show_welcome_on_startup.setter
    def show_welcome_on_startup(self, show: bool) -> None:
        """Set whether to show welcome screen on startup."""
        self._settings.setValue(self.KEY_SHOW_WELCOME, show)

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

    @property
    def theme_mode(self) -> ThemeMode:
        """Get the current theme mode preference.

        Returns:
            ThemeMode enum value (LIGHT, DARK, or SYSTEM)
        """
        value = self._settings.value(
            self.KEY_THEME_MODE,
            self.DEFAULT_THEME_MODE,
            type=str,
        )
        # Convert string to enum, default to SYSTEM if invalid
        try:
            return ThemeMode(value.lower())
        except (ValueError, AttributeError):
            return ThemeMode.SYSTEM

    @theme_mode.setter
    def theme_mode(self, mode: ThemeMode) -> None:
        """Set the theme mode preference.

        Args:
            mode: ThemeMode enum value to save
        """
        self._settings.setValue(self.KEY_THEME_MODE, mode.value)

    @property
    def show_shadows(self) -> bool:
        """Whether to show drop shadows on canvas objects."""
        return self._settings.value(
            self.KEY_SHOW_SHADOWS,
            self.DEFAULT_SHOW_SHADOWS,
            type=bool,
        )

    @show_shadows.setter
    def show_shadows(self, show: bool) -> None:
        """Set whether to show drop shadows on canvas objects."""
        self._settings.setValue(self.KEY_SHOW_SHADOWS, show)

    @property
    def show_scale_bar(self) -> bool:
        """Whether to show the scale bar on the canvas."""
        return self._settings.value(
            self.KEY_SHOW_SCALE_BAR,
            self.DEFAULT_SHOW_SCALE_BAR,
            type=bool,
        )

    @show_scale_bar.setter
    def show_scale_bar(self, show: bool) -> None:
        """Set whether to show the scale bar on the canvas."""
        self._settings.setValue(self.KEY_SHOW_SCALE_BAR, show)

    @property
    def show_labels(self) -> bool:
        """Whether to show object labels on the canvas."""
        return self._settings.value(
            self.KEY_SHOW_LABELS,
            self.DEFAULT_SHOW_LABELS,
            type=bool,
        )

    @show_labels.setter
    def show_labels(self, show: bool) -> None:
        """Set whether to show object labels on the canvas."""
        self._settings.setValue(self.KEY_SHOW_LABELS, show)

    @property
    def object_snap_enabled(self) -> bool:
        """Whether snap-to-object is enabled."""
        return self._settings.value(
            self.KEY_OBJECT_SNAP,
            self.DEFAULT_OBJECT_SNAP,
            type=bool,
        )

    @object_snap_enabled.setter
    def object_snap_enabled(self, enabled: bool) -> None:
        """Set whether snap-to-object is enabled."""
        self._settings.setValue(self.KEY_OBJECT_SNAP, enabled)

    @property
    def language(self) -> str:
        """Get the current UI language code (e.g. 'en', 'de')."""
        return str(
            self._settings.value(
                self.KEY_LANGUAGE,
                self.DEFAULT_LANGUAGE,
                type=str,
            )
        )

    @language.setter
    def language(self, lang_code: str) -> None:
        """Set the UI language code."""
        self._settings.setValue(self.KEY_LANGUAGE, lang_code)

    # --- Plant API key properties ---

    @property
    def trefle_api_token(self) -> str:
        """Trefle API token."""
        return str(
            self._settings.value(self.KEY_TREFLE_API_TOKEN, "", type=str)
        )

    @trefle_api_token.setter
    def trefle_api_token(self, token: str) -> None:
        """Set the Trefle API token."""
        self._settings.setValue(self.KEY_TREFLE_API_TOKEN, token)

    @property
    def perenual_api_key(self) -> str:
        """Perenual API key."""
        return str(
            self._settings.value(self.KEY_PERENUAL_API_KEY, "", type=str)
        )

    @perenual_api_key.setter
    def perenual_api_key(self, key: str) -> None:
        """Set the Perenual API key."""
        self._settings.setValue(self.KEY_PERENUAL_API_KEY, key)

    @property
    def permapeople_key_id(self) -> str:
        """Permapeople API key ID."""
        return str(
            self._settings.value(self.KEY_PERMAPEOPLE_KEY_ID, "", type=str)
        )

    @permapeople_key_id.setter
    def permapeople_key_id(self, key_id: str) -> None:
        """Set the Permapeople API key ID."""
        self._settings.setValue(self.KEY_PERMAPEOPLE_KEY_ID, key_id)

    @property
    def permapeople_key_secret(self) -> str:
        """Permapeople API key secret."""
        return str(
            self._settings.value(self.KEY_PERMAPEOPLE_KEY_SECRET, "", type=str)
        )

    @permapeople_key_secret.setter
    def permapeople_key_secret(self, secret: str) -> None:
        """Set the Permapeople API key secret."""
        self._settings.setValue(self.KEY_PERMAPEOPLE_KEY_SECRET, secret)

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
