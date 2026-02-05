"""Project management for Open Garden Planner.

Handles project state, serialization, and file I/O.
"""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from PyQt6.QtCore import QObject, QPointF, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGraphicsItem, QGraphicsScene

from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.fill_patterns import FillPattern, create_pattern_brush
from open_garden_planner.core.object_types import StrokeStyle
from open_garden_planner.models.layer import Layer, create_default_layers

# File format version for backward compatibility
FILE_VERSION = "1.1"


@dataclass
class ProjectData:
    """Data structure for a project."""

    canvas_width: float = 5000.0
    canvas_height: float = 3000.0
    objects: list[dict[str, Any]] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)

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
            "layers": self.layers,
            "objects": self.objects,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        """Create ProjectData from dictionary."""
        canvas = data.get("canvas", {})
        return cls(
            canvas_width=canvas.get("width", 5000.0),
            canvas_height=canvas.get("height", 3000.0),
            layers=data.get("layers", []),
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

        # Track in recent files
        get_settings().add_recent_file(str(file_path))

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

        # Sync custom plants from project to app library
        self._sync_custom_plants(scene)

        self._current_file = file_path
        self.mark_clean()
        self.project_changed.emit(str(file_path))

        # Track in recent files
        get_settings().add_recent_file(str(file_path))

    def _sync_custom_plants(self, scene: QGraphicsScene) -> None:
        """Sync custom plants from loaded project to app library.

        Imports any custom plants from the project that don't already exist
        in the global custom plant library.

        Args:
            scene: The scene with loaded items
        """
        try:
            from open_garden_planner.services.plant_library import get_plant_library

            library = get_plant_library()
            plants_to_import: dict[str, dict] = {}

            # Scan all items for custom plant metadata
            for item in scene.items():
                if not hasattr(item, "metadata") or not item.metadata:
                    continue

                plant_species = item.metadata.get("plant_species")
                if not plant_species or not isinstance(plant_species, dict):
                    continue

                # Check if it's a custom plant
                if plant_species.get("data_source") != "custom":
                    continue

                plant_id = plant_species.get("source_id")
                if not plant_id:
                    continue

                # Check if it already exists in library
                if library.get_plant(plant_id) is None:
                    plants_to_import[plant_id] = plant_species

            # Import plants that don't exist
            if plants_to_import:
                imported = library.import_from_dict(plants_to_import)
                if imported > 0:
                    import logging
                    logging.getLogger(__name__).info(
                        f"Imported {imported} custom plant(s) from project file"
                    )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Failed to sync custom plants: {e}")

    def _serialize_scene(self, scene: QGraphicsScene) -> ProjectData:
        """Convert scene objects to ProjectData."""
        objects = []
        layers = []

        # Serialize layers if the scene has them
        if hasattr(scene, "layers"):
            layers = [layer.to_dict() for layer in scene.layers]

        for item in scene.items():
            obj_data = self._serialize_item(item)
            if obj_data:
                objects.append(obj_data)

        return ProjectData(
            canvas_width=scene.width_cm if hasattr(scene, "width_cm") else 5000.0,
            canvas_height=scene.height_cm if hasattr(scene, "height_cm") else 3000.0,
            layers=layers,
            objects=objects,
        )

    def _serialize_item(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Serialize a single graphics item."""
        # Import here to avoid circular dependency
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        if isinstance(item, BackgroundImageItem):
            return item.to_dict()
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            data = {
                "type": "rectangle",
                "x": item.pos().x() + rect.x(),
                "y": item.pos().y() + rect.y(),
                "width": rect.width(),
                "height": rect.height(),
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            if hasattr(item, "layer_id") and item.layer_id:
                data["layer_id"] = str(item.layer_id)
            # Save custom fill and stroke colors (with alpha)
            # Use stored fill_color if available (for textured brushes), otherwise get from brush
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
            return data
        elif isinstance(item, CircleItem):
            data = {
                "type": "circle",
                "center_x": item.pos().x() + item.center.x(),
                "center_y": item.pos().y() + item.center.y(),
                "radius": item.radius,
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            if hasattr(item, "layer_id") and item.layer_id:
                data["layer_id"] = str(item.layer_id)
            # Save custom fill and stroke colors (with alpha)
            # Use stored fill_color if available (for textured brushes), otherwise get from brush
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
            return data
        elif isinstance(item, PolylineItem):
            data = {
                "type": "polyline",
                "points": [{"x": item.pos().x() + p.x(), "y": item.pos().y() + p.y()} for p in item.points],
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            if hasattr(item, "layer_id") and item.layer_id:
                data["layer_id"] = str(item.layer_id)
            # Save custom stroke color (polylines don't have fill, with alpha)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
            return data
        elif isinstance(item, PolygonItem):
            polygon = item.polygon()
            points = []
            for i in range(polygon.count()):
                pt = polygon.at(i)
                points.append({
                    "x": item.pos().x() + pt.x(),
                    "y": item.pos().y() + pt.y(),
                })
            data = {
                "type": "polygon",
                "points": points,
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            if hasattr(item, "layer_id") and item.layer_id:
                data["layer_id"] = str(item.layer_id)
            # Save custom fill and stroke colors (with alpha)
            # Use stored fill_color if available (for textured brushes), otherwise get from brush
            if hasattr(item, "fill_color") and item.fill_color:
                fill_color = item.fill_color
            else:
                fill_color = item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save fill pattern
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            # Save stroke style
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            # Save rotation angle
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
            return data
        return None

    def _deserialize_to_scene(
        self, scene: QGraphicsScene, data: ProjectData
    ) -> None:
        """Load objects from ProjectData into scene."""
        # Import here to avoid circular dependency
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        # Clear existing items
        for item in list(scene.items()):
            if isinstance(
                item, (RectangleItem, CircleItem, PolygonItem, PolylineItem, BackgroundImageItem)
            ):
                scene.removeItem(item)

        # Resize canvas if needed
        if hasattr(scene, "resize_canvas"):
            scene.resize_canvas(data.canvas_width, data.canvas_height)

        # Load layers
        if hasattr(scene, "set_layers"):
            if data.layers:
                layers = [Layer.from_dict(layer_data) for layer_data in data.layers]
                scene.set_layers(layers)
            else:
                # Create default layers if none exist (for backward compatibility)
                scene.set_layers(create_default_layers())

        # Create items
        for obj in data.objects:
            item = self._deserialize_item(obj)
            if item:
                scene.addItem(item)

    def _deserialize_item(self, obj: dict[str, Any]) -> QGraphicsItem | None:
        """Deserialize a single object to a graphics item."""
        # Import here to avoid circular dependency
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        obj_type = obj.get("type")

        # Extract common fields
        object_type = None
        if "object_type" in obj:
            try:
                object_type = ObjectType[obj["object_type"]]
            except KeyError:
                object_type = None

        name = obj.get("name", "")
        metadata = obj.get("metadata", {})
        fill_pattern = None
        if "fill_pattern" in obj:
            try:
                fill_pattern = FillPattern[obj["fill_pattern"]]
            except KeyError:
                fill_pattern = None

        stroke_style = None
        if "stroke_style" in obj:
            try:
                stroke_style = StrokeStyle[obj["stroke_style"]]
            except KeyError:
                stroke_style = None

        layer_id = None
        if "layer_id" in obj:
            try:
                layer_id = UUID(obj["layer_id"])
            except (ValueError, TypeError):
                layer_id = None

        if obj_type == "background_image":
            try:
                return BackgroundImageItem.from_dict(obj)
            except (ValueError, FileNotFoundError):
                # Image file may have been moved/deleted
                return None
        elif obj_type == "rectangle":
            item = RectangleItem(
                obj["x"],
                obj["y"],
                obj["width"],
                obj["height"],
                object_type=object_type or ObjectType.GENERIC_RECTANGLE,
                name=name,
                metadata=metadata,
                fill_pattern=fill_pattern,
                stroke_style=stroke_style,
                layer_id=layer_id,
            )
            # Restore custom colors if saved
            if "fill_color" in obj:
                # If we have a pattern, recreate the brush with both color and pattern
                if fill_pattern:
                    brush = create_pattern_brush(fill_pattern, QColor(obj["fill_color"]))
                else:
                    brush = item.brush()
                    brush.setColor(QColor(obj["fill_color"]))
                item.setBrush(brush)
            if "stroke_color" in obj:
                pen = item.pen()
                pen.setColor(QColor(obj["stroke_color"]))
                if "stroke_width" in obj:
                    pen.setWidthF(obj["stroke_width"])
                if stroke_style:
                    pen.setStyle(stroke_style.to_qt_pen_style())
                item.setPen(pen)
            # Restore rotation angle
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
            return item
        elif obj_type == "circle":
            item = CircleItem(
                obj["center_x"],
                obj["center_y"],
                obj["radius"],
                object_type=object_type or ObjectType.GENERIC_CIRCLE,
                name=name,
                metadata=metadata,
                fill_pattern=fill_pattern,
                stroke_style=stroke_style,
                layer_id=layer_id,
            )
            # Restore custom colors if saved
            if "fill_color" in obj:
                color = QColor(obj["fill_color"])
                # Store the base color in the item
                if hasattr(item, 'fill_color'):
                    item.fill_color = color
                # If we have a pattern, recreate the brush with both color and pattern
                if fill_pattern:
                    brush = create_pattern_brush(fill_pattern, color)
                else:
                    brush = item.brush()
                    brush.setColor(color)
                item.setBrush(brush)
            if "stroke_color" in obj:
                pen = item.pen()
                pen.setColor(QColor(obj["stroke_color"]))
                if "stroke_width" in obj:
                    pen.setWidthF(obj["stroke_width"])
                if stroke_style:
                    pen.setStyle(stroke_style.to_qt_pen_style())
                item.setPen(pen)
            # Restore rotation angle
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
            return item
        elif obj_type == "polyline":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 2:
                item = PolylineItem(
                    points,
                    object_type=object_type or ObjectType.FENCE,
                    name=name,
                    layer_id=layer_id,
                )
                # Restore custom stroke color if saved
                if "stroke_color" in obj:
                    pen = item.pen()
                    pen.setColor(QColor(obj["stroke_color"]))
                    if "stroke_width" in obj:
                        pen.setWidthF(obj["stroke_width"])
                    item.setPen(pen)
                # Restore rotation angle
                if "rotation_angle" in obj:
                    item._apply_rotation(obj["rotation_angle"])
                return item
        elif obj_type == "polygon":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 3:
                item = PolygonItem(
                    points,
                    object_type=object_type or ObjectType.GENERIC_POLYGON,
                    name=name,
                    metadata=metadata,
                    fill_pattern=fill_pattern,
                    stroke_style=stroke_style,
                    layer_id=layer_id,
                )
                # Restore custom colors if saved
                if "fill_color" in obj:
                    color = QColor(obj["fill_color"])
                    # Store the base color in the item
                    if hasattr(item, 'fill_color'):
                        item.fill_color = color
                    # If we have a pattern, recreate the brush with both color and pattern
                    if fill_pattern:
                        brush = create_pattern_brush(fill_pattern, color)
                    else:
                        brush = item.brush()
                        brush.setColor(color)
                    item.setBrush(brush)
                if "stroke_color" in obj:
                    pen = item.pen()
                    pen.setColor(QColor(obj["stroke_color"]))
                    if "stroke_width" in obj:
                        pen.setWidthF(obj["stroke_width"])
                    if stroke_style:
                        pen.setStyle(stroke_style.to_qt_pen_style())
                    item.setPen(pen)
                # Restore rotation angle
                if "rotation_angle" in obj:
                    item._apply_rotation(obj["rotation_angle"])
                return item
        return None
