"""Tests for auto-save functionality."""

import json
import tempfile
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.app.settings import AppSettings, get_settings
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.autosave_service import AutoSaveManager
from open_garden_planner.ui.canvas.items import RectangleItem


class TestAppSettings:
    """Tests for AppSettings class."""

    def test_default_autosave_enabled(self, qtbot) -> None:
        """Test default auto-save enabled state."""
        settings = AppSettings()
        # Default should be True
        assert settings.DEFAULT_AUTOSAVE_ENABLED is True

    def test_default_autosave_interval(self, qtbot) -> None:
        """Test default auto-save interval."""
        settings = AppSettings()
        assert settings.DEFAULT_AUTOSAVE_INTERVAL_MINUTES == 5

    def test_autosave_interval_clamping(self, qtbot) -> None:
        """Test that interval is clamped to valid range."""
        settings = AppSettings()

        # Test setting too low
        settings.autosave_interval_minutes = 0
        assert settings.autosave_interval_minutes >= settings.MIN_AUTOSAVE_INTERVAL_MINUTES

        # Test setting too high
        settings.autosave_interval_minutes = 100
        assert settings.autosave_interval_minutes <= settings.MAX_AUTOSAVE_INTERVAL_MINUTES

    def test_recent_files_operations(self, qtbot) -> None:
        """Test recent files list operations."""
        settings = AppSettings()

        # Clear to start fresh
        settings.clear_recent_files()
        assert settings.recent_files == []

        # Add a file
        settings.add_recent_file("/path/to/file1.ogp")
        assert "/path/to/file1.ogp" in settings.recent_files

        # Add another file - should be at front
        settings.add_recent_file("/path/to/file2.ogp")
        assert settings.recent_files[0] == "/path/to/file2.ogp"

        # Adding same file again moves it to front
        settings.add_recent_file("/path/to/file1.ogp")
        assert settings.recent_files[0] == "/path/to/file1.ogp"

        # Clean up
        settings.clear_recent_files()


class TestAutoSaveManager:
    """Tests for AutoSaveManager class."""

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    @pytest.fixture
    def manager(self, qtbot, scene) -> AutoSaveManager:
        """Create an auto-save manager for testing."""
        mgr = AutoSaveManager(ProjectManager())
        mgr.set_scene(scene)
        return mgr

    def test_initial_state(self, manager, qtbot) -> None:
        """Test initial auto-save manager state."""
        assert manager._scene is not None
        assert manager._current_project_path is None
        assert manager._is_dirty is False

    def test_set_dirty(self, manager, qtbot) -> None:
        """Test setting dirty state."""
        manager.set_dirty(True)
        assert manager._is_dirty is True

        manager.set_dirty(False)
        assert manager._is_dirty is False

    def test_set_project_path(self, manager, qtbot, tmp_path) -> None:
        """Test setting project path."""
        test_path = tmp_path / "test.ogp"
        manager.set_project_path(test_path)
        assert manager._current_project_path == test_path

        manager.set_project_path(None)
        assert manager._current_project_path is None

    def test_autosave_path_untitled(self, manager, qtbot) -> None:
        """Test auto-save path for untitled projects."""
        manager.set_project_path(None)
        path = manager._get_autosave_path()

        assert path.parent == Path(tempfile.gettempdir())
        assert path.stem.startswith("~autosave_untitled__")
        assert len(path.stem.rsplit("__", 1)[1]) == 32
        assert path.suffix == ".ogp"
        assert manager._get_autosave_path() == path

    def test_autosave_path_saved_project(self, manager, qtbot, tmp_path) -> None:
        """Test auto-save path for saved projects."""
        project_path = tmp_path / "my_garden.ogp"
        manager.set_project_path(project_path)
        path = manager._get_autosave_path()

        assert path.parent == tmp_path
        assert path.stem.startswith("~autosave_my_garden__")
        assert len(path.stem.rsplit("__", 1)[1]) == 32
        assert path.suffix == ".ogp"
        assert manager._get_autosave_path() == path

    def test_perform_autosave_creates_file(self, manager, scene, qtbot, tmp_path) -> None:
        """Test that perform_autosave creates a file."""
        # Add an item to the scene
        rect = RectangleItem(100, 100, 200, 150)
        scene.addItem(rect)

        # Set project path
        project_path = tmp_path / "test.ogp"
        manager.set_project_path(project_path)
        manager.set_dirty(True)

        # Perform auto-save
        result = manager.perform_autosave()

        assert result is True
        autosave_path = manager._get_autosave_path()
        assert autosave_path.exists()

        # Verify file content
        with open(autosave_path) as f:
            data = json.load(f)

        assert "autosave_metadata" in data
        assert "timestamp" in data["autosave_metadata"]
        assert data["autosave_metadata"]["original_file"] == str(project_path)

    def test_perform_autosave_skips_without_scene(self, qtbot) -> None:
        """Test that auto-save skips when no scene is set."""
        mgr = AutoSaveManager(ProjectManager())
        # Don't set scene
        result = mgr.perform_autosave()
        assert result is False

    def test_clear_autosave_deletes_file(self, manager, scene, qtbot, tmp_path) -> None:
        """Test that clear_autosave deletes the auto-save file."""
        # Set project path
        project_path = tmp_path / "test.ogp"
        manager.set_project_path(project_path)
        manager.set_dirty(True)

        # Create auto-save
        manager.perform_autosave()
        autosave_path = manager._get_autosave_path()
        assert autosave_path.exists()

        # Clear auto-save
        manager.clear_autosave()
        assert not autosave_path.exists()

    def test_autosave_performed_signal(self, manager, scene, qtbot, tmp_path) -> None:
        """Test that autosave_performed signal is emitted."""
        # Add an item and set up
        rect = RectangleItem(0, 0, 100, 100)
        scene.addItem(rect)
        project_path = tmp_path / "test.ogp"
        manager.set_project_path(project_path)
        manager.set_dirty(True)

        # Listen for signal
        with qtbot.waitSignal(manager.autosave_performed, timeout=1000):
            manager.perform_autosave()


class TestAutoSaveRecovery:
    def test_untitled_documents_keep_distinct_discoverable_snapshots(self, qtbot, monkeypatch, tmp_path):
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
        first = AutoSaveManager(ProjectManager())
        second = AutoSaveManager(ProjectManager())
        scene = QGraphicsScene()
        first.set_scene(scene)
        second.set_scene(scene)
        assert first.perform_autosave()
        first_path = first._get_autosave_path()
        first_bytes = first_path.read_bytes()
        assert second.perform_autosave()
        second_path = second._get_autosave_path()
        assert first_path != second_path and first_path.read_bytes() == first_bytes
        assert {path for path, _ in AutoSaveManager.find_recovery_files()} == {first_path, second_path}
        first.clear_autosave()
        assert not first_path.exists() and second_path.exists()

    def test_saved_plan_with_glob_characters_discovers_its_snapshot(self, qtbot, tmp_path):
        manager = AutoSaveManager(ProjectManager())
        scene = QGraphicsScene()
        manager.set_scene(scene)
        original = tmp_path / "garden[1].ogp"
        manager.set_project_path(original)
        assert manager.perform_autosave()
        snapshot = manager._get_autosave_path()
        assert AutoSaveManager.find_recovery_for_project(original)[0] == snapshot

    """Tests for auto-save recovery functionality."""

    @pytest.mark.parametrize("stale", [False, True])
    def test_recent_discovery_deduplicates_and_rejects_stale_snapshots(self, qtbot, tmp_path, stale):
        import os

        from open_garden_planner.core.plan_io import write_plan
        from open_garden_planner.core.project import ProjectData

        original = tmp_path / "saved.ogp"
        backup = tmp_path / "~autosave_saved.ogp"
        data = ProjectData().to_dict()
        write_plan(original, data)
        data["autosave_metadata"] = {"timestamp": "2026-11-16T12:00:00Z",
                                     "original_file": str(original)}
        write_plan(backup, data)
        stamp = 1_700_000_000_000_000_000
        os.utime(original, ns=(stamp, stamp))
        os.utime(backup, ns=(stamp + 1_000_000_000, stamp + 1_000_000_000))
        settings = get_settings()
        settings.recent_files = [str(original), str(original)]
        if stale:
            stamp = backup.stat().st_mtime_ns + 1_000_000_000
            os.utime(original, ns=(stamp, stamp))
        found = AutoSaveManager.find_recovery_files()
        assert [path for path, _ in found if path == backup] == ([] if stale else [backup])
        assert backup.exists(), "discovery must never remove an obsolete snapshot"

    def test_clear_only_removes_created_or_adopted_files(self, qtbot, tmp_path):
        project = ProjectManager()
        manager = AutoSaveManager(project)
        plan = tmp_path / "saved.ogp"
        manager.set_project_path(plan)
        backup = manager._get_autosave_path()
        backup.write_bytes(b"another process's recovery")
        manager.clear_autosave()
        assert backup.read_bytes() == b"another process's recovery"

    def test_adopted_symlink_cleanup_preserves_its_target(self, qtbot, tmp_path):
        target = tmp_path / "original.ogp"
        target.write_bytes(b"must survive")
        link = tmp_path / "~autosave_saved.ogp"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("symlinks unavailable")
        manager = AutoSaveManager(ProjectManager())
        manager.adopt_recovery_file(link)
        manager.clear_autosave()
        assert not link.is_symlink()
        assert target.read_bytes() == b"must survive"

    def test_find_recovery_for_project(self, qtbot, tmp_path) -> None:
        """Test finding recovery file for a specific project."""
        # Create a fake auto-save file
        project_path = tmp_path / "my_project.ogp"
        autosave_path = tmp_path / "~autosave_my_project.ogp"

        autosave_data = {
            "version": "1.1",
            "canvas": {"width": 5000, "height": 3000},
            "objects": [],
            "autosave_metadata": {
                "timestamp": "2025-01-15T10:30:00Z",
                "original_file": str(project_path),
            },
        }
        with open(autosave_path, "w") as f:
            json.dump(autosave_data, f)

        # Find recovery
        result = AutoSaveManager.find_recovery_for_project(project_path)

        assert result is not None
        path, metadata = result
        assert path == autosave_path
        assert metadata["original_file"] == str(project_path)

    def test_find_recovery_for_project_not_found(self, qtbot, tmp_path) -> None:
        """Test when no recovery file exists."""
        project_path = tmp_path / "nonexistent.ogp"
        result = AutoSaveManager.find_recovery_for_project(project_path)
        assert result is None

    def test_delete_recovery_file(self, qtbot, tmp_path) -> None:
        """Test deleting a recovery file."""
        # Create a recovery file
        recovery_path = tmp_path / "~autosave_test.ogp"
        recovery_path.write_text("{}")

        assert recovery_path.exists()

        # Delete it
        result = AutoSaveManager.delete_recovery_file(recovery_path)

        assert result is True
        assert not recovery_path.exists()

    def test_read_autosave_metadata(self, qtbot, tmp_path) -> None:
        """Test reading auto-save metadata."""
        autosave_path = tmp_path / "~autosave_test.ogp"
        autosave_data = {
            "version": "1.1",
            "autosave_metadata": {
                "timestamp": "2025-01-15T10:30:00Z",
                "original_file": "/path/to/project.ogp",
            },
        }
        with open(autosave_path, "w") as f:
            json.dump(autosave_data, f)

        metadata = AutoSaveManager._read_autosave_metadata(autosave_path)

        assert metadata is not None
        assert metadata["timestamp"] == "2025-01-15T10:30:00Z"
        assert metadata["original_file"] == "/path/to/project.ogp"

    def test_read_autosave_metadata_invalid_file(self, qtbot, tmp_path) -> None:
        """Test reading metadata from invalid file."""
        invalid_path = tmp_path / "invalid.ogp"
        invalid_path.write_text("not valid json")

        metadata = AutoSaveManager._read_autosave_metadata(invalid_path)
        assert metadata is None


class TestAutoSaveTimer:
    """Tests for auto-save timer behavior."""

    @pytest.fixture
    def manager(self, qtbot) -> AutoSaveManager:
        """Create an auto-save manager for testing."""
        scene = QGraphicsScene()
        mgr = AutoSaveManager(ProjectManager())
        mgr.set_scene(scene)
        return mgr

    def test_timer_not_running_initially(self, manager, qtbot) -> None:
        """Test that timer is not running initially."""
        assert not manager._timer.isActive()

    def test_start_with_autosave_enabled(self, manager, qtbot) -> None:
        """Test starting timer when auto-save is enabled."""
        # Ensure auto-save is enabled in settings
        settings = get_settings()
        original = settings.autosave_enabled
        settings.autosave_enabled = True
        try:
            manager.start()
            assert manager._timer.isActive()
            manager.stop()
        finally:
            settings.autosave_enabled = original

    def test_stop_stops_timer(self, manager, qtbot) -> None:
        """Test that stop() stops the timer."""
        # Ensure auto-save is enabled in settings
        settings = get_settings()
        original = settings.autosave_enabled
        settings.autosave_enabled = True
        try:
            manager.start()
            manager.stop()
            assert not manager._timer.isActive()
        finally:
            settings.autosave_enabled = original

    def test_timer_interval_from_settings(self, manager, qtbot) -> None:
        """Test that timer interval is set from settings."""
        settings = get_settings()
        expected_interval_ms = settings.autosave_interval_minutes * 60 * 1000

        manager._update_timer_interval()

        assert manager._timer.interval() == expected_interval_ms
