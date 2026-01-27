"""Project management for Open Garden Planner.

Handles project state, serialization, and file I/O.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QPointF, pyqtSignal
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.ui.canvas.items import PolygonItem, RectangleItem

# File format version for backward compatibility
FILE_VERSION = "1.0"


@dataclass
class ProjectData:
    """Data structure for a project."""

    canvas_width: float = 5000.0
    canvas_height: float = 3000.0
    objects: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "version": FILE_VERSION,
            "metadata": {
                "modified": datetime.now(UTC).isoformat(),
            },
            "canvas": {
                "width": self.canvas_width,
                "height": self.canvas_height,
            },
            "objects": self.objects,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        """Create ProjectData from dictionary."""
        canvas = data.get("canvas", {})
        return cls(
            canvas_width=canvas.get("width", 5000.0),
            canvas_height=canvas.get("height", 3000.0),
            objects=data.get("objects", []),
        )


class ProjectManager(QObject):
    """Manages the current project state.

    Signals:
        project_changed: Emitted when project is loaded/saved (filename or None)
        dirty_changed: Emitted when dirty state changes
    """

    project_changed = pyqtSignal(object)  # str path or None
    dirty_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the project manager."""
        super().__init__(parent)
        self._current_file: Path | None = None
        self._dirty = False

    @property
    def current_file(self) -> Path | None:
        """Path to current project file, or None if unsaved."""
        return self._current_file

    @property
    def is_dirty(self) -> bool:
        """Whether the project has unsaved changes."""
        return self._dirty

    @property
    def project_name(self) -> str:
        """Display name for the project."""
        if self._current_file:
            return self._current_file.stem
        return "Untitled"

    def mark_dirty(self) -> None:
        """Mark the project as having unsaved changes."""
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)

    def mark_clean(self) -> None:
        """Mark the project as saved (no unsaved changes)."""
        if self._dirty:
            self._dirty = False
            self.dirty_changed.emit(False)

    def new_project(self) -> None:
        """Start a new untitled project."""
        self._current_file = None
        self._dirty = False
        self.project_changed.emit(None)
        self.dirty_changed.emit(False)

    def save(self, scene: QGraphicsScene, file_path: Path) -> None:
        """Save the project to a file.

        Args:
            scene: The scene containing objects to save
            file_path: Path to save to
        """
        data = self._serialize_scene(scene)
        file_path = file_path.with_suffix(".ogp")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data.to_dict(), f, indent=2)

        self._current_file = file_path
        self.mark_clean()
        self.project_changed.emit(str(file_path))

    def load(self, scene: QGraphicsScene, file_path: Path) -> None:
        """Load a project from a file.

        Args:
            scene: The scene to load objects into
            file_path: Path to load from
        """
        with open(file_path, encoding="utf-8") as f:
            raw_data = json.load(f)

        data = ProjectData.from_dict(raw_data)
        self._deserialize_to_scene(scene, data)

        self._current_file = file_path
        self.mark_clean()
        self.project_changed.emit(str(file_path))

    def _serialize_scene(self, scene: QGraphicsScene) -> ProjectData:
        """Convert scene objects to ProjectData."""
        objects = []

        for item in scene.items():
            obj_data = self._serialize_item(item)
            if obj_data:
                objects.append(obj_data)

        return ProjectData(
            canvas_width=scene.width_cm if hasattr(scene, "width_cm") else 5000.0,
            canvas_height=scene.height_cm if hasattr(scene, "height_cm") else 3000.0,
            objects=objects,
        )

    def _serialize_item(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Serialize a single graphics item."""
        if isinstance(item, RectangleItem):
            rect = item.rect()
            return {
                "type": "rectangle",
                "x": item.pos().x() + rect.x(),
                "y": item.pos().y() + rect.y(),
                "width": rect.width(),
                "height": rect.height(),
            }
        elif isinstance(item, PolygonItem):
            polygon = item.polygon()
            points = []
            for i in range(polygon.count()):
                pt = polygon.at(i)
                points.append({
                    "x": item.pos().x() + pt.x(),
                    "y": item.pos().y() + pt.y(),
                })
            return {
                "type": "polygon",
                "points": points,
            }
        return None

    def _deserialize_to_scene(
        self, scene: QGraphicsScene, data: ProjectData
    ) -> None:
        """Load objects from ProjectData into scene."""
        # Clear existing items (except background)
        for item in list(scene.items()):
            if isinstance(item, (RectangleItem, PolygonItem)):
                scene.removeItem(item)

        # Resize canvas if needed
        if hasattr(scene, "resize_canvas"):
            scene.resize_canvas(data.canvas_width, data.canvas_height)

        # Create items
        for obj in data.objects:
            item = self._deserialize_item(obj)
            if item:
                scene.addItem(item)

    def _deserialize_item(self, obj: dict[str, Any]) -> QGraphicsItem | None:
        """Deserialize a single object to a graphics item."""
        obj_type = obj.get("type")

        if obj_type == "rectangle":
            return RectangleItem(
                obj["x"],
                obj["y"],
                obj["width"],
                obj["height"],
            )
        elif obj_type == "polygon":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 3:
                return PolygonItem(points)
        return None
