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
from open_garden_planner.core.object_types import PathFenceStyle, StrokeStyle
from open_garden_planner.models.layer import Layer, create_default_layers

# File format version for backward compatibility
FILE_VERSION = "1.3"


@dataclass
class ProjectData:
    """Data structure for a project."""

    canvas_width: float = 5000.0
    canvas_height: float = 3000.0
    objects: list[dict[str, Any]] = field(default_factory=list)
    layers: list[dict[str, Any]] = field(default_factory=list)
    constraints: list[dict[str, Any]] = field(default_factory=list)
    guides: list[dict[str, Any]] = field(default_factory=list)
    location: dict[str, Any] | None = None
    task_completions: list[str] = field(default_factory=list)
    seed_inventory: list[dict[str, Any]] = field(default_factory=list)
    # US-9.5: per-species user overrides for propagation step dates
    # shape: {species_key: {step_id: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}}
    propagation_overrides: dict[str, Any] = field(default_factory=dict)
    # US-10.5: crop rotation history
    crop_rotation: dict[str, Any] = field(default_factory=dict)
    # US-10.7: season management
    season_year: int | None = None
    # List of dicts: {"year": int, "file": "relative/or/absolute/path.ogp"}
    linked_seasons: list[dict[str, Any]] = field(default_factory=list)
    # US-12.10a: per-bed (and "global" default) soil test history
    # shape: {target_id: SoilTestHistory.to_dict()} where target_id is bed UUID or "global"
    soil_tests: dict[str, Any] = field(default_factory=dict)
    # US-12.6: user-entered prices for the shopping list, keyed by ShoppingListItem.id
    shopping_list_prices: dict[str, float] = field(default_factory=dict)
    # US-12.11: amendment-library allowlist + organic-preference flag.
    # ``None`` means "every amendment in the bundled library is enabled" — the
    # default for new projects so the calculator behaves identically to legacy
    # files. A non-``None`` list is the user's explicit toggleable allowlist.
    enabled_amendments: list[str] | None = None
    prefer_organic: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data: dict[str, Any] = {
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
        if self.constraints:
            data["constraints"] = self.constraints
        if self.guides:
            data["guides"] = self.guides
        if self.location:
            data["location"] = self.location
        if self.task_completions:
            data["task_completions"] = sorted(self.task_completions)
        if self.seed_inventory:
            data["seed_inventory"] = self.seed_inventory
        if self.propagation_overrides:
            data["propagation_overrides"] = self.propagation_overrides
        if self.crop_rotation:
            data["crop_rotation"] = self.crop_rotation
        if self.season_year is not None:
            data["season_year"] = self.season_year
        if self.linked_seasons:
            data["linked_seasons"] = self.linked_seasons
        if self.soil_tests:
            data["soil_tests"] = self.soil_tests
        if self.shopping_list_prices:
            data["shopping_list_prices"] = self.shopping_list_prices
        if self.enabled_amendments is not None:
            data["enabled_amendments"] = sorted(self.enabled_amendments)
        if self.prefer_organic is False:
            data["prefer_organic"] = False
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectData":
        """Create ProjectData from dictionary."""
        canvas = data.get("canvas", {})
        return cls(
            canvas_width=canvas.get("width", 5000.0),
            canvas_height=canvas.get("height", 3000.0),
            layers=data.get("layers", []),
            objects=data.get("objects", []),
            constraints=data.get("constraints", []),
            guides=data.get("guides", []),
            location=data.get("location") or None,
            task_completions=data.get("task_completions", []),
            seed_inventory=data.get("seed_inventory", []),
            propagation_overrides=data.get("propagation_overrides", {}),
            crop_rotation=data.get("crop_rotation", {}),
            season_year=data.get("season_year"),
            linked_seasons=data.get("linked_seasons", []),
            soil_tests=data.get("soil_tests", {}),
            shopping_list_prices=data.get("shopping_list_prices", {}),
            enabled_amendments=data.get("enabled_amendments"),
            prefer_organic=bool(data.get("prefer_organic", True)),
        )


class ProjectManager(QObject):
    """Manages the current project state.

    Signals:
        project_changed: Emitted when project is loaded/saved (filename or None)
        dirty_changed: Emitted when dirty state changes
    """

    project_changed = pyqtSignal(object)  # str path or None
    dirty_changed = pyqtSignal(bool)
    location_changed = pyqtSignal(object)  # dict or None
    task_completions_changed = pyqtSignal(object)  # set[str]
    seed_inventory_changed = pyqtSignal(object)    # list[SeedPacket]
    propagation_overrides_changed = pyqtSignal(object)  # dict
    crop_rotation_changed = pyqtSignal(object)  # dict
    season_changed = pyqtSignal(object)  # int year or None
    soil_tests_changed = pyqtSignal(object)  # dict[str, dict]
    shopping_list_prices_changed = pyqtSignal(object)  # dict[str, float]
    enabled_amendments_changed = pyqtSignal(object)  # list[str] or None
    prefer_organic_changed = pyqtSignal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the project manager."""
        super().__init__(parent)
        self._current_file: Path | None = None
        self._dirty = False
        self._location: dict[str, Any] | None = None
        self._task_completions: set[str] = set()
        self._seed_inventory: list[dict[str, Any]] = []
        self._propagation_overrides: dict[str, Any] = {}
        self._crop_rotation: dict[str, Any] = {}
        self._season_year: int | None = None
        self._linked_seasons: list[dict[str, Any]] = []
        self._soil_tests: dict[str, Any] = {}
        self._shopping_list_prices: dict[str, float] = {}
        self._enabled_amendments: list[str] | None = None
        self._prefer_organic: bool = True

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

    @property
    def location(self) -> dict[str, Any] | None:
        """Garden location data, or None if not set."""
        return self._location

    @property
    def task_completions(self) -> set[str]:
        """Set of completed task IDs for the current project."""
        return set(self._task_completions)

    def set_task_completion(self, task_id: str, done: bool) -> None:
        """Mark a task as done or not done, persisting to the project file."""
        if done:
            self._task_completions.add(task_id)
        else:
            self._task_completions.discard(task_id)
        self.task_completions_changed.emit(self._task_completions)
        self.mark_dirty()

    @property
    def seed_inventory(self) -> list[dict[str, Any]]:
        """Seed packets stored in the current project (as raw dicts)."""
        return list(self._seed_inventory)

    def set_seed_inventory(self, packets_dicts: list[dict[str, Any]]) -> None:
        """Replace the project seed inventory and mark project dirty."""
        self._seed_inventory = list(packets_dicts)
        self.seed_inventory_changed.emit(self._seed_inventory)
        self.mark_dirty()

    @property
    def propagation_overrides(self) -> dict[str, Any]:
        """Per-species propagation step date overrides for the current project."""
        return dict(self._propagation_overrides)

    def set_propagation_override(
        self,
        species_key: str,
        step_id: str,
        start: str,
        end: str,
    ) -> None:
        """Store a propagation step date override and mark project dirty.

        Args:
            species_key: Scientific or common name of the species.
            step_id: Propagation step identifier (e.g., 'prick_out').
            start: ISO date string for step start.
            end: ISO date string for step end.
        """
        if species_key not in self._propagation_overrides:
            self._propagation_overrides[species_key] = {}
        self._propagation_overrides[species_key][step_id] = {"start": start, "end": end}
        self.propagation_overrides_changed.emit(self._propagation_overrides)
        self.mark_dirty()

    def clear_propagation_override(self, species_key: str, step_id: str) -> None:
        """Remove a propagation step override and mark project dirty."""
        sp_overrides = self._propagation_overrides.get(species_key, {})
        sp_overrides.pop(step_id, None)
        if not sp_overrides:
            self._propagation_overrides.pop(species_key, None)
        else:
            self._propagation_overrides[species_key] = sp_overrides
        self.propagation_overrides_changed.emit(self._propagation_overrides)
        self.mark_dirty()

    @property
    def crop_rotation(self) -> dict[str, Any]:
        """Crop rotation history for the current project."""
        return dict(self._crop_rotation)

    def set_crop_rotation(self, rotation_data: dict[str, Any]) -> None:
        """Replace the crop rotation history and mark project dirty."""
        self._crop_rotation = dict(rotation_data)
        self.crop_rotation_changed.emit(self._crop_rotation)
        self.mark_dirty()

    @property
    def season_year(self) -> int | None:
        """Current season year, or None if not set."""
        return self._season_year

    @property
    def linked_seasons(self) -> list[dict[str, Any]]:
        """Linked season files sorted by year."""
        return list(self._linked_seasons)

    def set_season(self, year: int | None, linked_seasons: list[dict[str, Any]] | None = None) -> None:
        """Set the season year and optionally update linked seasons."""
        self._season_year = year
        if linked_seasons is not None:
            self._linked_seasons = list(linked_seasons)
        self.season_changed.emit(year)
        self.mark_dirty()

    @property
    def soil_tests(self) -> dict[str, Any]:
        """Per-target soil test history dicts (target_id -> SoilTestHistory dict)."""
        return dict(self._soil_tests)

    def set_soil_test_history(self, target_id: str, history: Any) -> None:
        """Replace the soil test history for ``target_id`` and mark project dirty.

        Args:
            target_id: Bed UUID string or the literal ``"global"``.
            history: SoilTestHistory instance (uses its ``to_dict``).
        """
        self._soil_tests[target_id] = history.to_dict()
        self.soil_tests_changed.emit(self._soil_tests)
        self.mark_dirty()

    @property
    def shopping_list_prices(self) -> dict[str, float]:
        """User-entered prices for the shopping list, keyed by item ID (US-12.6)."""
        return dict(self._shopping_list_prices)

    def set_shopping_list_prices(self, prices: dict[str, float]) -> None:
        """Replace the shopping-list price overrides and mark project dirty.

        Zero is a valid price and round-trips; only ``None`` values are dropped.
        """
        cleaned = {k: float(v) for k, v in prices.items() if v is not None}
        if cleaned == self._shopping_list_prices:
            return
        self._shopping_list_prices = cleaned
        self.shopping_list_prices_changed.emit(self._shopping_list_prices)
        self.mark_dirty()

    @property
    def enabled_amendments(self) -> list[str] | None:
        """Return the user's amendment allowlist (US-12.11).

        ``None`` means every bundled amendment is enabled — the default for new
        and legacy projects. A non-``None`` list is the explicit allowlist
        managed via the Amendment Plan dialog's checkbox panel.
        """
        if self._enabled_amendments is None:
            return None
        return list(self._enabled_amendments)

    def set_enabled_amendments(self, ids: list[str] | None) -> None:
        """Replace the amendment allowlist and mark project dirty.

        Pass ``None`` to reset to "all enabled". A list — even empty — is
        stored verbatim.
        """
        if ids is None:
            new_value: list[str] | None = None
        else:
            new_value = sorted(set(ids))
        if new_value == self._enabled_amendments:
            return
        self._enabled_amendments = new_value
        self.enabled_amendments_changed.emit(new_value)
        self.mark_dirty()

    @property
    def prefer_organic(self) -> bool:
        """Whether the calculator prefers organic substances on tie (US-12.11)."""
        return self._prefer_organic

    def set_prefer_organic(self, value: bool) -> None:
        """Replace the organic-preference flag and mark project dirty."""
        if bool(value) == self._prefer_organic:
            return
        self._prefer_organic = bool(value)
        self.prefer_organic_changed.emit(self._prefer_organic)
        self.mark_dirty()

    def restore_soil_test_history(self, target_id: str, history_dict: dict[str, Any] | None) -> None:
        """Restore (or delete) the soil test history for ``target_id``.

        Used by undo/redo to revert to a previous snapshot. Marks dirty but
        does not require a SoilTestHistory instance.
        """
        if history_dict is None:
            self._soil_tests.pop(target_id, None)
        else:
            self._soil_tests[target_id] = history_dict
        self.soil_tests_changed.emit(self._soil_tests)
        self.mark_dirty()

    def set_location(self, location: dict[str, Any] | None) -> None:
        """Set the garden location and mark project as dirty.

        Args:
            location: Dict with latitude, longitude, elevation_m, frost_dates keys,
                      or None to clear location.
        """
        self._location = location
        self.location_changed.emit(location)
        self.mark_dirty()

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
        self._location = None
        self._task_completions = set()
        self._seed_inventory = []
        self._propagation_overrides = {}
        self._crop_rotation = {}
        self._season_year = None
        self._linked_seasons = []
        self._soil_tests = {}
        self._shopping_list_prices = {}
        self._enabled_amendments = None
        self._prefer_organic = True
        self.project_changed.emit(None)
        self.dirty_changed.emit(False)
        self.location_changed.emit(None)
        self.task_completions_changed.emit(set())
        self.seed_inventory_changed.emit([])
        self.propagation_overrides_changed.emit({})
        self.crop_rotation_changed.emit({})
        self.season_changed.emit(None)
        self.soil_tests_changed.emit({})
        self.shopping_list_prices_changed.emit({})
        self.enabled_amendments_changed.emit(None)
        self.prefer_organic_changed.emit(True)

    def save(self, scene: QGraphicsScene, file_path: Path) -> None:
        """Save the project to a file.

        Args:
            scene: The scene containing objects to save
            file_path: Path to save to
        """
        data = self._serialize_scene(scene)
        data.location = self._location
        data.task_completions = sorted(self._task_completions)
        data.seed_inventory = list(self._seed_inventory)
        data.propagation_overrides = dict(self._propagation_overrides)
        data.crop_rotation = dict(self._crop_rotation)
        data.season_year = self._season_year
        data.linked_seasons = list(self._linked_seasons)
        data.soil_tests = dict(self._soil_tests)
        data.shopping_list_prices = dict(self._shopping_list_prices)
        data.enabled_amendments = (
            list(self._enabled_amendments)
            if self._enabled_amendments is not None
            else None
        )
        data.prefer_organic = self._prefer_organic
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

        # Restore location data
        self._location = data.location
        self.location_changed.emit(self._location)
        # Restore task completions
        self._task_completions = set(data.task_completions)
        self.task_completions_changed.emit(self._task_completions)
        # Restore project seed inventory
        self._seed_inventory = list(data.seed_inventory)
        self.seed_inventory_changed.emit(self._seed_inventory)
        # Restore propagation overrides
        self._propagation_overrides = dict(data.propagation_overrides)
        self.propagation_overrides_changed.emit(self._propagation_overrides)
        # Restore crop rotation history
        self._crop_rotation = dict(data.crop_rotation)
        self.crop_rotation_changed.emit(self._crop_rotation)
        # Restore season data
        self._season_year = data.season_year
        self._linked_seasons = list(data.linked_seasons)
        self.season_changed.emit(self._season_year)
        # Restore soil test history (US-12.10a)
        self._soil_tests = dict(data.soil_tests)
        self.soil_tests_changed.emit(self._soil_tests)
        # Restore shopping list prices (US-12.6)
        self._shopping_list_prices = dict(data.shopping_list_prices)
        self.shopping_list_prices_changed.emit(self._shopping_list_prices)
        # Restore amendment library state (US-12.11)
        self._enabled_amendments = (
            list(data.enabled_amendments)
            if data.enabled_amendments is not None
            else None
        )
        self.enabled_amendments_changed.emit(self._enabled_amendments)
        self._prefer_organic = bool(data.prefer_organic)
        self.prefer_organic_changed.emit(self._prefer_organic)

        # Sync custom plants from project to app library
        self._sync_custom_plants(scene)

        self._current_file = file_path
        self.mark_clean()
        self.project_changed.emit(str(file_path))

        # Track in recent files
        get_settings().add_recent_file(str(file_path))

    def create_new_season(
        self,
        scene: QGraphicsScene,
        new_year: int,
        new_file_path: Path,
        keep_plants: bool = False,
    ) -> None:
        """Create a new season file from the current project.

        Structural objects (beds, fences, paths, etc.) always carry over.
        Plant objects (trees, shrubs, perennials) carry over only when keep_plants=True.
        The current season is recorded in linked_seasons of the new file.

        Args:
            scene: Current canvas scene
            new_year: The year for the new season
            new_file_path: Where to write the new .ogp file
            keep_plants: Whether to copy plant objects to the new season
        """
        # Serialize the current scene
        current_data = self._serialize_scene(scene)
        current_data.location = self._location
        current_data.task_completions = []
        current_data.seed_inventory = list(self._seed_inventory)
        current_data.propagation_overrides = dict(self._propagation_overrides)
        current_data.crop_rotation = dict(self._crop_rotation)
        current_data.soil_tests = dict(self._soil_tests)

        # Filter objects based on keep_plants flag
        if not keep_plants:
            current_data.objects = [
                obj for obj in current_data.objects
                if not self._is_removable_plant_object(obj)
            ]

        # Build linked_seasons: include all previous links + current season
        linked = list(self._linked_seasons)
        if self._current_file is not None and self._season_year is not None:
            # Add current season to the list (use relative path if same dir)
            try:
                rel = self._current_file.relative_to(new_file_path.parent)
                linked_file = str(rel)
            except ValueError:
                linked_file = str(self._current_file)
            # Avoid duplicates
            if not any(s.get("year") == self._season_year for s in linked):
                linked.append({"year": self._season_year, "file": linked_file})
        linked.sort(key=lambda s: s.get("year", 0))

        current_data.season_year = new_year
        current_data.linked_seasons = linked
        new_file_path = new_file_path.with_suffix(".ogp")

        with open(new_file_path, "w", encoding="utf-8") as f:
            json.dump(current_data.to_dict(), f, indent=2)

        # Bidirectional link: update the SOURCE season file so it also lists the new season.
        if self._current_file is not None and self._current_file.exists():
            try:
                with open(self._current_file, encoding="utf-8") as f:
                    source_raw = json.load(f)
                source_linked: list[dict[str, Any]] = source_raw.get("linked_seasons", [])
                # Build relative path from source file's directory to the new file
                try:
                    rel_new = new_file_path.relative_to(self._current_file.parent)
                    new_file_str = str(rel_new)
                except ValueError:
                    new_file_str = str(new_file_path)
                if not any(s.get("year") == new_year for s in source_linked):
                    source_linked.append({"year": new_year, "file": new_file_str})
                    source_linked.sort(key=lambda s: s.get("year", 0))
                    source_raw["linked_seasons"] = source_linked
                    with open(self._current_file, "w", encoding="utf-8") as f:
                        json.dump(source_raw, f, indent=2)
                    # Also update in-memory linked_seasons
                    self._linked_seasons = source_linked
            except Exception:
                pass  # Don't let source-update failure break new-season creation

    @staticmethod
    def _is_plant_object(obj: dict[str, Any]) -> bool:
        """Return True if the serialized object represents a plant item."""
        from open_garden_planner.core.plant_renderer import is_plant_type

        obj_type_name = obj.get("object_type")
        if obj_type_name is None:
            return False
        try:
            from open_garden_planner.core.object_types import ObjectType
            obj_type = ObjectType[obj_type_name]
        except KeyError:
            return False
        return is_plant_type(obj_type)

    # Plant categories that represent permanent multi-year plants (trees and woody shrubs).
    # Anything NOT in this set (vegetables, herbs, flowers, grasses, etc.) is removable.
    _PERMANENT_PLANT_CATEGORIES = frozenset({
        "ROUND_DECIDUOUS", "COLUMNAR_TREE", "WEEPING_TREE", "CONIFER", "FRUIT_TREE", "PALM",
        "SPREADING_SHRUB", "COMPACT_SHRUB",
    })

    @staticmethod
    def _is_removable_plant_object(obj: dict[str, Any]) -> bool:
        """Return True if the object should be removed when clearing for a new season.

        Only trees (all tree categories) and woody shrubs (SPREADING_SHRUB, COMPACT_SHRUB)
        are permanent and kept. Vegetables, herbs, flowers, and other annuals are removed.
        The plant_category saved on the object takes precedence; if absent, the default
        category for the object_type is used.
        """
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.plant_renderer import get_default_category, is_plant_type

        obj_type_name = obj.get("object_type")
        if obj_type_name is None:
            return False
        try:
            obj_type = ObjectType[obj_type_name]
        except KeyError:
            return False
        if not is_plant_type(obj_type):
            return False

        # Resolve the effective plant category
        cat_name = obj.get("plant_category")
        if cat_name is None:
            default_cat = get_default_category(obj_type)
            cat_name = default_cat.name if default_cat else None

        return cat_name not in ProjectManager._PERMANENT_PLANT_CATEGORIES

    def load_season_objects(self, file_path: Path) -> list[dict[str, Any]]:
        """Load and return the serialized objects from a season file.

        Used for compare-view overlay (does not change the current project).

        Args:
            file_path: Path to the season .ogp file to read

        Returns:
            List of serialized object dicts from the season file
        """
        with open(file_path, encoding="utf-8") as f:
            raw_data = json.load(f)
        return raw_data.get("objects", [])

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
        constraints: list[dict[str, Any]] = []

        # Serialize layers if the scene has them
        if hasattr(scene, "layers"):
            layers = [layer.to_dict() for layer in scene.layers]

        for item in scene.items():
            obj_data = self._serialize_item(item)
            if obj_data:
                objects.append(obj_data)

        # Serialize constraints if the scene has a constraint graph
        if hasattr(scene, "constraint_graph") and scene.constraint_graph is not None:
            constraints = scene.constraint_graph.to_list()

        # Serialize guide lines if the scene has them
        guides: list[dict[str, Any]] = []
        if hasattr(scene, "guide_lines"):
            guides = [
                {"is_horizontal": g.is_horizontal, "position": g.position}
                for g in scene.guide_lines
            ]

        return ProjectData(
            canvas_width=scene.width_cm if hasattr(scene, "width_cm") else 5000.0,
            canvas_height=scene.height_cm if hasattr(scene, "height_cm") else 3000.0,
            layers=layers,
            objects=objects,
            constraints=constraints,
            guides=guides,
        )

    def _serialize_item(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Serialize a single graphics item."""
        # Skip items that are Qt children of a GroupItem — they are serialized
        # recursively inside the group's own dict.
        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        if isinstance(item.parentItem(), GroupItem):
            return None

        data = self._serialize_item_core(item)
        if data is None:
            return None

        # Add parent-child relationship fields
        from open_garden_planner.ui.canvas.items import GardenItemMixin
        if isinstance(item, GardenItemMixin):
            if item.parent_bed_id is not None:
                data["parent_bed_id"] = str(item.parent_bed_id)
            if item.child_item_ids:
                data["child_item_ids"] = [str(cid) for cid in item.child_item_ids]

        return data

    def _serialize_item_core(self, item: QGraphicsItem) -> dict[str, Any] | None:
        """Core serialization logic for a single graphics item."""
        # Import here to avoid circular dependency
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            ConstructionCircleItem,
            ConstructionLineItem,
            EllipseItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        if isinstance(item, (ConstructionLineItem, ConstructionCircleItem, BackgroundImageItem)):
            return item.to_dict()
        elif isinstance(item, RectangleItem):
            rect = item.rect()
            data = {
                "type": "rectangle",
                "item_id": str(item.item_id),
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
            if hasattr(item, "label_visible") and not item.label_visible:
                data["label_visible"] = False
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
            if hasattr(item, "area_label_visible") and item.area_label_visible:
                data["area_label_visible"] = True
            return data
        elif isinstance(item, EllipseItem):
            rect = item.rect()
            cx = item.pos().x() + rect.center().x()
            cy = item.pos().y() + rect.center().y()
            data = {
                "type": "ellipse",
                "item_id": str(item.item_id),
                "center_x": cx,
                "center_y": cy,
                "semi_x": rect.width() / 2,
                "semi_y": rect.height() / 2,
            }
            if hasattr(item, "object_type") and item.object_type:
                data["object_type"] = item.object_type.name
            if hasattr(item, "name") and item.name:
                data["name"] = item.name
            if hasattr(item, "metadata") and item.metadata:
                data["metadata"] = item.metadata
            if hasattr(item, "layer_id") and item.layer_id:
                data["layer_id"] = str(item.layer_id)
            if hasattr(item, "label_visible") and not item.label_visible:
                data["label_visible"] = False
            fill_color = item.fill_color if hasattr(item, "fill_color") and item.fill_color else item.brush().color()
            data["fill_color"] = fill_color.name(QColor.NameFormat.HexArgb)
            data["stroke_color"] = item.pen().color().name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            if hasattr(item, "fill_pattern") and item.fill_pattern:
                data["fill_pattern"] = item.fill_pattern.name
            if hasattr(item, "stroke_style") and item.stroke_style:
                data["stroke_style"] = item.stroke_style.name
            if hasattr(item, "rotation_angle") and abs(item.rotation_angle) > 0.01:
                data["rotation_angle"] = item.rotation_angle
            if hasattr(item, "area_label_visible") and item.area_label_visible:
                data["area_label_visible"] = True
            return data
        elif isinstance(item, CircleItem):
            data = {
                "type": "circle",
                "item_id": str(item.item_id),
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
            if hasattr(item, "label_visible") and not item.label_visible:
                data["label_visible"] = False
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
            # Save plant category and species (for plant types)
            if hasattr(item, "plant_category") and item.plant_category is not None:
                data["plant_category"] = item.plant_category.name
            if hasattr(item, "plant_species") and item.plant_species:
                data["plant_species"] = item.plant_species
            # Save spacing radius override (US-11.2)
            if hasattr(item, "_spacing_radius_cm") and item._spacing_radius_cm is not None:
                data["spacing_radius_cm"] = item._spacing_radius_cm
            # Save frost protection override (US-12.2)
            if hasattr(item, "_frost_protection_needed") and item._frost_protection_needed is not None:
                data["frost_protection_needed"] = item._frost_protection_needed
            if hasattr(item, "area_label_visible") and item.area_label_visible:
                data["area_label_visible"] = True
            return data
        elif isinstance(item, PolylineItem):
            data = {
                "type": "polyline",
                "item_id": str(item.item_id),
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
            if hasattr(item, "label_visible") and not item.label_visible:
                data["label_visible"] = False
            # Save custom stroke color (polylines don't have fill, with alpha)
            stroke_color = item.pen().color()
            data["stroke_color"] = stroke_color.name(QColor.NameFormat.HexArgb)
            data["stroke_width"] = item.pen().widthF()
            # Save path/fence style preset
            if hasattr(item, "path_fence_style") and item.path_fence_style and item.path_fence_style.name != "NONE":
                data["path_fence_style"] = item.path_fence_style.name
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
                "item_id": str(item.item_id),
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
            if hasattr(item, "label_visible") and not item.label_visible:
                data["label_visible"] = False
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
            if hasattr(item, "area_label_visible") and item.area_label_visible:
                data["area_label_visible"] = True
            return data

        from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
        if isinstance(item, CalloutItem):
            return item.to_dict()

        from open_garden_planner.ui.canvas.items.group_item import GroupItem
        if isinstance(item, GroupItem):
            children: list[dict[str, Any]] = []
            for child in item.childItems():
                child_data = self._serialize_item_core(child)
                if child_data:
                    children.append(child_data)
            group_data: dict[str, Any] = {
                "type": "group",
                "item_id": str(item.item_id),
                "children": children,
                "x": item.pos().x(),
                "y": item.pos().y(),
            }
            if item.layer_id:
                group_data["layer_id"] = str(item.layer_id)
            if item.name:
                group_data["name"] = item.name
            return group_data

        return None

    def _deserialize_to_scene(
        self, scene: QGraphicsScene, data: ProjectData
    ) -> None:
        """Load objects from ProjectData into scene."""
        # Import here to avoid circular dependency
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            ConstructionCircleItem,
            ConstructionLineItem,
            EllipseItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )

        # Clear dimension lines before removing garden items so the manager can
        # cleanly remove its graphics items while C++ objects are still alive
        if hasattr(scene, "_dimension_line_manager"):
            scene._dimension_line_manager.clear()

        # Clear existing items (including construction geometry)
        for item in list(scene.items()):
            if isinstance(
                item,
                (
                    RectangleItem,
                    CircleItem,
                    EllipseItem,
                    PolygonItem,
                    PolylineItem,
                    BackgroundImageItem,
                    ConstructionLineItem,
                    ConstructionCircleItem,
                ),
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

        # Apply layer visibility/opacity/lock/z-order to all items now that they exist
        if hasattr(scene, "_update_items_visibility"):
            scene._update_items_visibility()
        if hasattr(scene, "_update_items_z_order"):
            scene._update_items_z_order()

        # Load constraints if present
        if data.constraints and hasattr(scene, "constraint_graph"):
            from open_garden_planner.core.constraints import ConstraintGraph

            scene.constraint_graph = ConstraintGraph.from_list(data.constraints)

        # Load guide lines if present
        if data.guides and hasattr(scene, "set_guide_lines"):
            from open_garden_planner.ui.canvas.canvas_scene import GuideLine

            scene.set_guide_lines([
                GuideLine(is_horizontal=g["is_horizontal"], position=g["position"])
                for g in data.guides
            ])
        elif hasattr(scene, "set_guide_lines"):
            scene.set_guide_lines([])

    def _deserialize_item(self, obj: dict[str, Any]) -> QGraphicsItem | None:
        """Deserialize a single object to a graphics item."""
        item = self._deserialize_item_core(obj)
        if item is None:
            return None

        # Restore parent-child relationship fields
        import contextlib

        from open_garden_planner.ui.canvas.items import GardenItemMixin
        if isinstance(item, GardenItemMixin):
            if "parent_bed_id" in obj:
                with contextlib.suppress(ValueError, TypeError):
                    item._parent_bed_id = UUID(obj["parent_bed_id"])
            if "child_item_ids" in obj:
                item._child_item_ids = []
                for cid_str in obj["child_item_ids"]:
                    with contextlib.suppress(ValueError, TypeError):
                        item._child_item_ids.append(UUID(cid_str))

        return item

    def _deserialize_item_core(self, obj: dict[str, Any]) -> QGraphicsItem | None:
        """Core deserialization logic for a single object."""
        # Import here to avoid circular dependency
        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items import (
            BackgroundImageItem,
            CircleItem,
            EllipseItem,
            PolygonItem,
            PolylineItem,
            RectangleItem,
        )
        from open_garden_planner.ui.canvas.items.construction_item import (
            ConstructionCircleItem,
            ConstructionLineItem,
        )

        obj_type = obj.get("type")

        if obj_type == "construction_line":
            return ConstructionLineItem.from_dict(obj)
        elif obj_type == "construction_circle":
            return ConstructionCircleItem.from_dict(obj)
        elif obj_type == "group":
            import contextlib
            from uuid import UUID as _UUID

            from open_garden_planner.ui.canvas.items.group_item import GroupItem
            layer_id = None
            with contextlib.suppress(ValueError, TypeError, KeyError):
                layer_id = _UUID(obj["layer_id"])
            group = GroupItem(layer_id=layer_id, name=obj.get("name", ""))
            with contextlib.suppress(ValueError, TypeError, KeyError):
                group._item_id = _UUID(obj["item_id"])
            for child_data in obj.get("children", []):
                child = self._deserialize_item_core(child_data)
                if child is not None:
                    group.addToGroup(child)
            if "x" in obj and "y" in obj:
                group.setPos(float(obj["x"]), float(obj["y"]))
            return group

        # Extract common fields
        object_type = None
        if "object_type" in obj:
            try:
                object_type = ObjectType[obj["object_type"]]
            except KeyError:
                object_type = None

        name = obj.get("name", "")
        metadata = obj.get("metadata", {})
        label_visible = obj.get("label_visible", True)
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
            # Migrate legacy HEDGE_SECTION rectangles to HEDGE_POLYGON polygons
            if object_type == ObjectType.HEDGE_SECTION:
                x, y, w, h = obj["x"], obj["y"], obj["width"], obj["height"]
                vertices = [
                    QPointF(x, y),
                    QPointF(x + w, y),
                    QPointF(x + w, y + h),
                    QPointF(x, y + h),
                ]
                from open_garden_planner.core.fill_patterns import FillPattern as _FP
                hedge_item = PolygonItem(
                    vertices,
                    object_type=ObjectType.HEDGE_POLYGON,
                    name=name,
                    metadata=metadata,
                    fill_pattern=_FP.HEDGE,
                    layer_id=layer_id,
                )
                if "item_id" in obj:
                    hedge_item._item_id = UUID(obj["item_id"])
                if not label_visible:
                    hedge_item.label_visible = False
                if "rotation_angle" in obj:
                    hedge_item._apply_rotation(obj["rotation_angle"])
                return hedge_item

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
            # Restore item_id so constraints referencing this item still resolve
            if "item_id" in obj:
                item._item_id = UUID(obj["item_id"])
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
            # Restore label visibility
            if not label_visible:
                item.label_visible = False
            # Restore rotation angle
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
            if obj.get("area_label_visible"):
                item.area_label_visible = True
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
            if "item_id" in obj:
                item._item_id = UUID(obj["item_id"])
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
            # Restore label visibility
            if not label_visible:
                item.label_visible = False
            # Restore rotation angle
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
            # Restore plant category and species
            if "plant_category" in obj:
                import contextlib

                from open_garden_planner.core.plant_renderer import PlantCategory
                with contextlib.suppress(KeyError):
                    item.plant_category = PlantCategory[obj["plant_category"]]
            if "plant_species" in obj:
                item.plant_species = obj["plant_species"]
            # Restore spacing radius override (US-11.2)
            if "spacing_radius_cm" in obj:
                item._spacing_radius_cm = obj["spacing_radius_cm"]
            # Restore frost protection override (US-12.2)
            if "frost_protection_needed" in obj:
                item._frost_protection_needed = bool(obj["frost_protection_needed"])
            if obj.get("area_label_visible"):
                item.area_label_visible = True
            return item
        elif obj_type == "ellipse":
            semi_x = float(obj.get("semi_x", 50))
            semi_y = float(obj.get("semi_y", 30))
            cx = float(obj.get("center_x", 0))
            cy = float(obj.get("center_y", 0))
            item = EllipseItem(
                cx - semi_x,
                cy - semi_y,
                semi_x * 2,
                semi_y * 2,
                object_type=object_type or ObjectType.GENERIC_ELLIPSE,
                name=name,
                metadata=metadata,
                fill_pattern=fill_pattern,
                stroke_style=stroke_style,
                layer_id=layer_id,
            )
            if "item_id" in obj:
                item._item_id = UUID(obj["item_id"])
            if "fill_color" in obj:
                color = QColor(obj["fill_color"])
                if hasattr(item, 'fill_color'):
                    item.fill_color = color
                if fill_pattern:
                    item.setBrush(create_pattern_brush(fill_pattern, color))
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
            if not label_visible:
                item.label_visible = False
            if "rotation_angle" in obj:
                item._apply_rotation(obj["rotation_angle"])
            if obj.get("area_label_visible"):
                item.area_label_visible = True
            return item
        elif obj_type == "polyline":
            points = [QPointF(p["x"], p["y"]) for p in obj.get("points", [])]
            if len(points) >= 2:
                # Parse path_fence_style
                path_fence_style = PathFenceStyle.NONE
                if "path_fence_style" in obj:
                    try:
                        path_fence_style = PathFenceStyle[obj["path_fence_style"]]
                    except KeyError:
                        path_fence_style = PathFenceStyle.NONE
                item = PolylineItem(
                    points,
                    object_type=object_type or ObjectType.FENCE,
                    name=name,
                    layer_id=layer_id,
                    path_fence_style=path_fence_style,
                )
                if "item_id" in obj:
                    item._item_id = UUID(obj["item_id"])
                if metadata:
                    item._metadata = metadata
                # Restore custom stroke color if saved (only if no preset overrides it)
                if "stroke_color" in obj and path_fence_style == PathFenceStyle.NONE:
                    pen = item.pen()
                    pen.setColor(QColor(obj["stroke_color"]))
                    if "stroke_width" in obj:
                        pen.setWidthF(obj["stroke_width"])
                    item.setPen(pen)
                # Restore label visibility
                if not label_visible:
                    item.label_visible = False
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
                if "item_id" in obj:
                    item._item_id = UUID(obj["item_id"])
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
                # Restore label visibility
                if not label_visible:
                    item.label_visible = False
                # Restore rotation angle
                if "rotation_angle" in obj:
                    item._apply_rotation(obj["rotation_angle"])
                if obj.get("area_label_visible"):
                    item.area_label_visible = True
                return item
        elif obj_type == "callout":
            from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
            return CalloutItem.from_dict(obj)
        return None
