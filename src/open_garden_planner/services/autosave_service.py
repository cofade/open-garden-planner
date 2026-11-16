"""Auto-save service for crash recovery.

Provides automatic periodic saving to a temporary location
and recovery detection on startup.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.config.settings import get_settings

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager

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

    def __init__(self, project_manager: ProjectManager, parent: QObject | None = None) -> None:
        """Initialize the auto-save manager."""
        super().__init__(parent)

        self._project_manager = project_manager
        self._settings = get_settings()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer_tick)

        self._scene: QGraphicsScene | None = None
        self._current_project_path: Path | None = None
        self._is_dirty = False
        # Paths belong to the document that wrote/adopted them, not whichever
        # filename project_changed has just rebound us to (#797).
        self._owned_autosaves: set[Path] = set()

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
            self.adopt_recovery_file(autosave_path)
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
        # Add auto-save metadata
        assert self._scene is not None
        save_data = self._project_manager.recovery_dict(self._scene)
        save_data["autosave_metadata"] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "original_file": str(self._current_project_path) if self._current_project_path else None,
        }

        from open_garden_planner.core.plan_io import write_plan
        write_plan(path, save_data)

    def clear_autosave(self) -> None:
        """Remove this document's snapshots after a successful save or discard.

        Never infer ownership from the current filename: a successful load or
        Save As has already emitted project_changed by the time cleanup runs.
        """
        for autosave_path in tuple(self._owned_autosaves):
            try:
                autosave_path.unlink(missing_ok=True)
                self._owned_autosaves.discard(autosave_path)
                logger.info(f"Deleted auto-save file: {autosave_path}")
            except OSError as e:
                logger.warning(f"Failed to delete auto-save file: {e}")

    def adopt_recovery_file(self, path: Path) -> None:
        """Keep a recovered source until this document is saved or discarded."""
        self._owned_autosaves.add(path.absolute())

    def preserve_recovery_file(self, path: Path) -> None:
        """A declined recovery remains on disk, outside this document's cleanup."""
        self._owned_autosaves.discard(path.absolute())

    @classmethod
    def find_recovery_files(cls) -> list[tuple[Path, dict[str, Any]]]:
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

        # Saved plans write beside their original, rather than in the system
        # temp directory. Bound discovery to the same ten recent plans the UI
        # keeps; explicitly opened plans are also checked by the GUI wrapper.
        seen = {path.absolute() for path, _metadata in recovery_files}
        for recent in get_settings().recent_files[:10]:
            found = cls.find_recovery_for_project(Path(recent))
            if found is not None and found[0].absolute() not in seen:
                recovery_files.append(found)
                seen.add(found[0].absolute())
        return recovery_files

    @classmethod
    def find_recovery_for_project(cls, project_path: Path) -> tuple[Path, dict[str, Any]] | None:
        """Find recovery file for a specific project.

        Args:
            project_path: Path to the project file

        Returns:
            (autosave_path, metadata) tuple if found, None otherwise
        """
        try:
            project_name = project_path.stem
            autosave_path = project_path.parent / (
                f"{cls.AUTOSAVE_PREFIX}{project_name}{cls.AUTOSAVE_EXTENSION}"
            )
            if not autosave_path.is_file():
                return None
            metadata = cls._read_autosave_metadata(autosave_path)
            if metadata:
                original = metadata.get("original_file")
                if not isinstance(original, str):
                    return None
                if Path(original).resolve() != project_path.resolve():
                    return None
                # An already saved newer original must not be replaced by
                # an obsolete recovery file. A missing original is recoverable.
                if (project_path.exists()
                        and autosave_path.stat().st_mtime_ns <= project_path.stat().st_mtime_ns):
                    return None
                return (autosave_path, metadata)
        except Exception as e:
            # User-controlled recovery metadata and filesystem paths are one
            # ingestion boundary; an unreadable candidate must not abort startup.
            logger.warning("Failed to inspect recovery for %s: %s", project_path, e)
        return None

    @classmethod
    def _read_autosave_metadata(cls, path: Path) -> dict[str, Any] | None:
        """Read auto-save metadata from a file.

        Args:
            path: Path to the auto-save file

        Returns:
            Metadata dict or None if invalid
        """
        try:
            from open_garden_planner.core.plan_io import read_plan
            data = read_plan(path)
            metadata = data.get("autosave_metadata")
            if not isinstance(metadata, dict) or not isinstance(metadata.get("timestamp"), str):
                return None
            return metadata
        except Exception as e:
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
