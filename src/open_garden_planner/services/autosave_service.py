"""Auto-save service for crash recovery.

Provides automatic periodic saving to a temporary location
and recovery detection on startup.
"""

import json
import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.app.settings import get_settings

logger = logging.getLogger(__name__)


class AutoSaveManager(QObject):
    """Manages automatic saving and crash recovery.

    Auto-saves are stored in:
    - For saved projects: Same directory as project, named ~autosave_{filename}.ogp
    - For unsaved projects: System temp directory, named ~autosave_untitled.ogp

    Signals:
        autosave_performed: Emitted when an auto-save completes (path: str)
        autosave_failed: Emitted when auto-save fails (error: str)
    """

    autosave_performed = pyqtSignal(str)  # path
    autosave_failed = pyqtSignal(str)  # error message

    # Prefix for auto-save files
    AUTOSAVE_PREFIX = "~autosave_"
    AUTOSAVE_EXTENSION = ".ogp"

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the auto-save manager."""
        super().__init__(parent)

        self._settings = get_settings()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

        self._scene: QGraphicsScene | None = None
        self._current_project_path: Path | None = None
        self._is_dirty = False

        # Update timer interval from settings
        self._update_timer_interval()

    def set_scene(self, scene: QGraphicsScene) -> None:
        """Set the scene to auto-save.

        Args:
            scene: The canvas scene to save
        """
        self._scene = scene

    def set_project_path(self, path: Path | None) -> None:
        """Set the current project file path.

        Args:
            path: Path to the project file, or None for untitled
        """
        self._current_project_path = path

    def set_dirty(self, dirty: bool) -> None:
        """Set whether the project has unsaved changes.

        Args:
            dirty: True if there are unsaved changes
        """
        self._is_dirty = dirty

    def start(self) -> None:
        """Start the auto-save timer if enabled."""
        if self._settings.autosave_enabled:
            self._update_timer_interval()
            self._timer.start()
            logger.info(
                f"Auto-save started with interval of "
                f"{self._settings.autosave_interval_minutes} minute(s)"
            )
        else:
            logger.info("Auto-save disabled in settings")

    def stop(self) -> None:
        """Stop the auto-save timer."""
        self._timer.stop()
        logger.info("Auto-save stopped")

    def restart(self) -> None:
        """Restart the auto-save timer (e.g., after settings change)."""
        self.stop()
        self.start()

    def _update_timer_interval(self) -> None:
        """Update the timer interval from settings."""
        interval_ms = self._settings.autosave_interval_minutes * 60 * 1000
        self._timer.setInterval(interval_ms)

    def _on_timer_tick(self) -> None:
        """Handle timer tick - perform auto-save if needed."""
        if not self._is_dirty:
            logger.debug("Auto-save skipped: no unsaved changes")
            return

        if self._scene is None:
            logger.warning("Auto-save skipped: no scene set")
            return

        self.perform_autosave()

    def perform_autosave(self) -> bool:
        """Perform an auto-save immediately.

        Returns:
            True if auto-save succeeded, False otherwise
        """
        if self._scene is None:
            return False

        autosave_path = self._get_autosave_path()
        try:
            self._save_to_file(autosave_path)
            logger.info(f"Auto-saved to: {autosave_path}")
            self.autosave_performed.emit(str(autosave_path))
            return True
        except Exception as e:
            error_msg = f"Auto-save failed: {e}"
            logger.error(error_msg)
            self.autosave_failed.emit(error_msg)
            return False

    def _get_autosave_path(self) -> Path:
        """Get the path for the auto-save file.

        Returns:
            Path where auto-save should be written
        """
        if self._current_project_path:
            # Save next to the project file
            project_dir = self._current_project_path.parent
            project_name = self._current_project_path.stem
            return project_dir / f"{self.AUTOSAVE_PREFIX}{project_name}{self.AUTOSAVE_EXTENSION}"
        else:
            # Save to temp directory for untitled projects
            temp_dir = Path(tempfile.gettempdir())
            return temp_dir / f"{self.AUTOSAVE_PREFIX}untitled{self.AUTOSAVE_EXTENSION}"

    def _save_to_file(self, path: Path) -> None:
        """Save the scene to a file.

        Args:
            path: Path to save to
        """
        # Import here to avoid circular dependency
        from open_garden_planner.core.project import ProjectManager

        # Create a temporary ProjectManager just for serialization
        pm = ProjectManager()

        # Serialize scene data
        data = pm._serialize_scene(self._scene)

        # Add auto-save metadata
        save_data = data.to_dict()
        save_data["autosave_metadata"] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "original_file": str(self._current_project_path) if self._current_project_path else None,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(save_data, f, indent=2)

    def clear_autosave(self) -> None:
        """Delete the current auto-save file (e.g., after manual save)."""
        autosave_path = self._get_autosave_path()
        if autosave_path.exists():
            try:
                autosave_path.unlink()
                logger.info(f"Deleted auto-save file: {autosave_path}")
            except OSError as e:
                logger.warning(f"Failed to delete auto-save file: {e}")

    @classmethod
    def find_recovery_files(cls) -> list[tuple[Path, dict]]:
        """Find all auto-save files that may need recovery.

        Returns:
            List of (path, metadata) tuples for each recovery file found
        """
        recovery_files = []

        # Check temp directory for untitled auto-saves
        temp_dir = Path(tempfile.gettempdir())
        untitled_autosave = temp_dir / f"{cls.AUTOSAVE_PREFIX}untitled{cls.AUTOSAVE_EXTENSION}"
        if untitled_autosave.exists():
            metadata = cls._read_autosave_metadata(untitled_autosave)
            if metadata:
                recovery_files.append((untitled_autosave, metadata))

        return recovery_files

    @classmethod
    def find_recovery_for_project(cls, project_path: Path) -> tuple[Path, dict] | None:
        """Find recovery file for a specific project.

        Args:
            project_path: Path to the project file

        Returns:
            (autosave_path, metadata) tuple if found, None otherwise
        """
        project_dir = project_path.parent
        project_name = project_path.stem
        autosave_path = project_dir / f"{cls.AUTOSAVE_PREFIX}{project_name}{cls.AUTOSAVE_EXTENSION}"

        if autosave_path.exists():
            metadata = cls._read_autosave_metadata(autosave_path)
            if metadata:
                return (autosave_path, metadata)

        return None

    @classmethod
    def _read_autosave_metadata(cls, path: Path) -> dict | None:
        """Read auto-save metadata from a file.

        Args:
            path: Path to the auto-save file

        Returns:
            Metadata dict or None if invalid
        """
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("autosave_metadata", {})
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to read auto-save metadata from {path}: {e}")
            return None

    @classmethod
    def delete_recovery_file(cls, path: Path) -> bool:
        """Delete a recovery file.

        Args:
            path: Path to the recovery file to delete

        Returns:
            True if deleted successfully
        """
        try:
            path.unlink()
            logger.info(f"Deleted recovery file: {path}")
            return True
        except OSError as e:
            logger.warning(f"Failed to delete recovery file: {e}")
            return False
