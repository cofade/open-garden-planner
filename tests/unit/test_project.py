"""Tests for project management and serialization."""

import json
from pathlib import Path

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.project import (
    FILE_VERSION,
    ProjectData,
    ProjectManager,
)
from open_garden_planner.ui.canvas.items import CircleItem, PolygonItem, RectangleItem


class TestProjectData:
    """Tests for ProjectData class."""

    def test_default_values(self) -> None:
        """Test default canvas dimensions."""
        data = ProjectData()
        assert data.canvas_width == 5000.0
        assert data.canvas_height == 3000.0
        assert data.objects == []

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        data = ProjectData(canvas_width=1000, canvas_height=500, objects=[])
        result = data.to_dict()

        assert result["version"] == FILE_VERSION
        assert result["canvas"]["width"] == 1000
        assert result["canvas"]["height"] == 500
        assert "metadata" in result
        assert "modified" in result["metadata"]

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        raw = {
            "version": "1.0",
            "canvas": {"width": 2000, "height": 1500},
            "objects": [{"type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 50}],
        }
        data = ProjectData.from_dict(raw)

        assert data.canvas_width == 2000
        assert data.canvas_height == 1500
        assert len(data.objects) == 1

    def test_from_dict_defaults(self) -> None:
        """Test that missing values get defaults."""
        data = ProjectData.from_dict({})
        assert data.canvas_width == 5000.0
        assert data.canvas_height == 3000.0


class TestProjectManager:
    """Tests for ProjectManager class."""

    @pytest.fixture(autouse=True)
    def setup(self, qtbot):  # noqa: ARG002
        """Set up test fixtures - clean recent files."""
        from open_garden_planner.app.settings import get_settings

        # Clear recent files before each test
        get_settings().clear_recent_files()
        yield
        # Clear recent files after each test
        get_settings().clear_recent_files()

    @pytest.fixture
    def manager(self, qtbot) -> ProjectManager:
        """Create a project manager for testing."""
        return ProjectManager()

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def test_initial_state(self, manager) -> None:
        """Test initial state is clean and untitled."""
        assert manager.current_file is None
        assert not manager.is_dirty
        assert manager.project_name == "Untitled"

    def test_mark_dirty(self, manager, qtbot) -> None:
        """Test marking project as dirty."""
        with qtbot.waitSignal(manager.dirty_changed):
            manager.mark_dirty()

        assert manager.is_dirty

    def test_mark_clean(self, manager, qtbot) -> None:
        """Test marking project as clean."""
        manager.mark_dirty()

        with qtbot.waitSignal(manager.dirty_changed):
            manager.mark_clean()

        assert not manager.is_dirty

    def test_new_project_resets_state(self, manager, qtbot) -> None:
        """Test that new_project resets state."""
        manager.mark_dirty()
        manager._current_file = Path("/fake/path.ogp")

        manager.new_project()

        assert manager.current_file is None
        assert not manager.is_dirty
        assert manager.project_name == "Untitled"


class TestSerialization:
    """Tests for save/load functionality."""

    @pytest.fixture
    def manager(self, qtbot) -> ProjectManager:
        """Create a project manager for testing."""
        return ProjectManager()

    @pytest.fixture
    def scene(self, qtbot) -> QGraphicsScene:
        """Create a scene for testing."""
        return QGraphicsScene()

    def test_save_and_load_rectangle(self, manager, scene, tmp_path) -> None:
        """Test saving and loading a rectangle."""
        # Create a rectangle
        rect = RectangleItem(100, 200, 300, 150)
        scene.addItem(rect)

        # Save
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Clear scene
        scene.clear()
        assert len(scene.items()) == 0

        # Load
        manager.load(scene, file_path)

        # Verify
        items = [i for i in scene.items() if isinstance(i, RectangleItem)]
        assert len(items) == 1
        loaded = items[0]
        assert loaded.rect().x() == 100
        assert loaded.rect().y() == 200
        assert loaded.rect().width() == 300
        assert loaded.rect().height() == 150

    def test_save_and_load_polygon(self, manager, scene, tmp_path) -> None:
        """Test saving and loading a polygon."""
        # Create a polygon
        points = [QPointF(0, 0), QPointF(100, 0), QPointF(50, 100)]
        poly = PolygonItem(points)
        scene.addItem(poly)

        # Save
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Clear scene
        scene.clear()

        # Load
        manager.load(scene, file_path)

        # Verify
        items = [i for i in scene.items() if isinstance(i, PolygonItem)]
        assert len(items) == 1
        loaded = items[0]
        loaded_poly = loaded.polygon()
        assert loaded_poly.count() == 3

    def test_save_and_load_circle(self, manager, scene, tmp_path) -> None:
        """Test saving and loading a circle."""
        # Create a circle
        circle = CircleItem(150, 200, 50)
        scene.addItem(circle)

        # Save
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Clear scene
        scene.clear()
        assert len(scene.items()) == 0

        # Load
        manager.load(scene, file_path)

        # Verify
        items = [i for i in scene.items() if isinstance(i, CircleItem)]
        assert len(items) == 1
        loaded = items[0]
        assert loaded.center.x() == 150
        assert loaded.center.y() == 200
        assert loaded.radius == 50

    def test_save_creates_ogp_extension(self, manager, scene, tmp_path) -> None:
        """Test that save adds .ogp extension."""
        file_path = tmp_path / "test"
        manager.save(scene, file_path)

        assert (tmp_path / "test.ogp").exists()

    def test_file_is_valid_json(self, manager, scene, tmp_path) -> None:
        """Test that saved file is valid JSON."""
        rect = RectangleItem(0, 0, 100, 100)
        scene.addItem(rect)

        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Should not raise
        with open(file_path) as f:
            data = json.load(f)

        assert "version" in data
        assert "canvas" in data
        assert "objects" in data

    def test_save_updates_current_file(self, manager, scene, tmp_path) -> None:
        """Test that save updates current_file."""
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        assert manager.current_file == file_path
        assert manager.project_name == "test"

    def test_save_marks_clean(self, manager, scene, tmp_path) -> None:
        """Test that save marks project as clean."""
        manager.mark_dirty()
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        assert not manager.is_dirty

    def test_load_marks_clean(self, manager, scene, tmp_path) -> None:
        """Test that load marks project as clean."""
        # Create and save a file
        file_path = tmp_path / "test.ogp"
        manager.save(scene, file_path)

        # Mark dirty
        manager.mark_dirty()

        # Load should mark clean
        manager.load(scene, file_path)

        assert not manager.is_dirty
