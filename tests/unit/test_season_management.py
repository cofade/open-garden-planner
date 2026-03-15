"""Unit tests for US-10.7: Season management & plan duplication."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_garden_planner.core.project import ProjectData, ProjectManager


# ─── ProjectData season fields ─────────────────────────────────────────────────


class TestProjectDataSeasonFields:
    def test_defaults(self) -> None:
        data = ProjectData()
        assert data.season_year is None
        assert data.linked_seasons == []

    def test_to_dict_omits_when_empty(self) -> None:
        data = ProjectData()
        d = data.to_dict()
        assert "season_year" not in d
        assert "linked_seasons" not in d

    def test_to_dict_includes_when_set(self) -> None:
        data = ProjectData(
            season_year=2025,
            linked_seasons=[{"year": 2024, "file": "garden_2024.ogp"}],
        )
        d = data.to_dict()
        assert d["season_year"] == 2025
        assert d["linked_seasons"] == [{"year": 2024, "file": "garden_2024.ogp"}]

    def test_from_dict_round_trip(self) -> None:
        original = ProjectData(
            season_year=2026,
            linked_seasons=[{"year": 2025, "file": "garden_2025.ogp"}],
        )
        restored = ProjectData.from_dict(original.to_dict())
        assert restored.season_year == 2026
        assert restored.linked_seasons == [{"year": 2025, "file": "garden_2025.ogp"}]

    def test_from_dict_missing_fields(self) -> None:
        """Old project files without season fields parse without error."""
        d = {"canvas": {"width": 5000, "height": 3000}, "layers": [], "objects": []}
        data = ProjectData.from_dict(d)
        assert data.season_year is None
        assert data.linked_seasons == []


# ─── ProjectManager season API ────────────────────────────────────────────────


class TestProjectManagerSeasonAPI:
    def test_initial_state(self, qtbot) -> None:  # noqa: ARG002
        pm = ProjectManager()
        assert pm.season_year is None
        assert pm.linked_seasons == []

    def test_set_season_emits_signal(self, qtbot) -> None:  # noqa: ARG002
        pm = ProjectManager()
        emitted = []
        pm.season_changed.connect(emitted.append)
        pm.set_season(2025)
        assert emitted == [2025]
        assert pm.season_year == 2025

    def test_set_season_with_linked(self, qtbot) -> None:  # noqa: ARG002
        pm = ProjectManager()
        linked = [{"year": 2024, "file": "old.ogp"}]
        pm.set_season(2025, linked)
        assert pm.linked_seasons == linked

    def test_new_project_resets_season(self, qtbot) -> None:  # noqa: ARG002
        pm = ProjectManager()
        pm.set_season(2025, [{"year": 2024, "file": "old.ogp"}])
        emitted = []
        pm.season_changed.connect(emitted.append)
        pm.new_project()
        assert pm.season_year is None
        assert pm.linked_seasons == []
        assert None in emitted

    def test_marks_dirty_on_set_season(self, qtbot) -> None:  # noqa: ARG002
        pm = ProjectManager()
        assert not pm.is_dirty
        pm.set_season(2025)
        assert pm.is_dirty


# ─── create_new_season ────────────────────────────────────────────────────────


class TestCreateNewSeason:
    def test_creates_file_without_plants(self, qtbot, tmp_path) -> None:  # noqa: ARG002
        """New season file should contain only structural objects when keep_plants=False."""
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.core.project import ProjectManager
        from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

        scene = QGraphicsScene()

        # Add a structural item (bed)
        rect = RectangleItem(
            x=0, y=0, width=200, height=100,
            object_type=ObjectType.GARDEN_BED,
        )
        scene.addItem(rect)

        # Add a plant item (perennial)
        circle = CircleItem(
            center_x=300, center_y=300, radius=50,
            object_type=ObjectType.PERENNIAL,
        )
        scene.addItem(circle)

        pm = ProjectManager()
        # Simulate a saved current file so create_new_season can record the link
        current_file = tmp_path / "garden_2024.ogp"
        current_file.write_text("{}")
        pm._current_file = current_file
        pm._season_year = 2024

        new_file = tmp_path / "garden_2025.ogp"
        pm.create_new_season(scene, 2025, new_file, keep_plants=False)

        assert new_file.exists()
        data = json.loads(new_file.read_text())
        objects = data.get("objects", [])
        obj_types = [o.get("object_type") for o in objects]
        assert "PERENNIAL" not in obj_types
        assert "GARDEN_BED" in obj_types
        assert data["season_year"] == 2025

    def test_creates_file_with_plants(self, qtbot, tmp_path) -> None:  # noqa: ARG002
        """New season file should contain plants when keep_plants=True."""
        from PyQt6.QtWidgets import QGraphicsScene

        from open_garden_planner.core.object_types import ObjectType
        from open_garden_planner.ui.canvas.items import CircleItem

        scene = QGraphicsScene()
        circle = CircleItem(
            center_x=100, center_y=100, radius=40,
            object_type=ObjectType.TREE,
        )
        scene.addItem(circle)

        pm = ProjectManager()
        pm._current_file = tmp_path / "garden_2024.ogp"
        pm._current_file.write_text("{}")
        pm._season_year = 2024

        new_file = tmp_path / "garden_2025.ogp"
        pm.create_new_season(scene, 2025, new_file, keep_plants=True)

        data = json.loads(new_file.read_text())
        obj_types = [o.get("object_type") for o in data.get("objects", [])]
        assert "TREE" in obj_types

    def test_linked_seasons_recorded(self, qtbot, tmp_path) -> None:  # noqa: ARG002
        """Previous season should appear in linked_seasons of new file."""
        from PyQt6.QtWidgets import QGraphicsScene

        pm = ProjectManager()
        current_file = tmp_path / "garden_2024.ogp"
        current_file.write_text("{}")
        pm._current_file = current_file
        pm._season_year = 2024

        new_file = tmp_path / "garden_2025.ogp"
        pm.create_new_season(QGraphicsScene(), 2025, new_file, keep_plants=False)

        data = json.loads(new_file.read_text())
        linked = data.get("linked_seasons", [])
        years = [s["year"] for s in linked]
        assert 2024 in years


# ─── _is_plant_object ────────────────────────────────────────────────────────


class TestIsPlantObject:
    def test_plant_object(self) -> None:
        obj = {"type": "circle", "object_type": "PERENNIAL"}
        assert ProjectManager._is_plant_object(obj) is True

    def test_tree_is_plant(self) -> None:
        assert ProjectManager._is_plant_object({"type": "circle", "object_type": "TREE"}) is True

    def test_shrub_is_plant(self) -> None:
        assert ProjectManager._is_plant_object({"type": "circle", "object_type": "SHRUB"}) is True

    def test_garden_bed_not_plant(self) -> None:
        assert ProjectManager._is_plant_object({"type": "polygon", "object_type": "GARDEN_BED"}) is False

    def test_no_object_type(self) -> None:
        assert ProjectManager._is_plant_object({"type": "rectangle"}) is False

    def test_unknown_object_type(self) -> None:
        assert ProjectManager._is_plant_object({"type": "circle", "object_type": "UNKNOWN_TYPE"}) is False


# ─── _is_removable_plant_object ────────────────────────────────────────────────


class TestIsRemovablePlantObject:
    def test_perennial_default_category_is_removable(self) -> None:
        # PERENNIAL default category is FLOWERING_PERENNIAL → removable
        assert ProjectManager._is_removable_plant_object({"type": "circle", "object_type": "PERENNIAL"}) is True

    def test_perennial_with_vegetable_category_is_removable(self) -> None:
        obj = {"type": "circle", "object_type": "PERENNIAL", "plant_category": "VEGETABLE"}
        assert ProjectManager._is_removable_plant_object(obj) is True

    def test_perennial_with_herb_category_is_removable(self) -> None:
        obj = {"type": "circle", "object_type": "PERENNIAL", "plant_category": "HERB"}
        assert ProjectManager._is_removable_plant_object(obj) is True

    def test_shrub_default_category_is_not_removable(self) -> None:
        # SHRUB default category is SPREADING_SHRUB → permanent
        assert ProjectManager._is_removable_plant_object({"type": "circle", "object_type": "SHRUB"}) is False

    def test_shrub_with_vegetable_category_is_removable(self) -> None:
        # Vegetable placed using shrub object type → should still be removed
        obj = {"type": "circle", "object_type": "SHRUB", "plant_category": "VEGETABLE"}
        assert ProjectManager._is_removable_plant_object(obj) is True

    def test_shrub_with_compact_category_is_not_removable(self) -> None:
        obj = {"type": "circle", "object_type": "SHRUB", "plant_category": "COMPACT_SHRUB"}
        assert ProjectManager._is_removable_plant_object(obj) is False

    def test_tree_default_category_is_not_removable(self) -> None:
        assert ProjectManager._is_removable_plant_object({"type": "circle", "object_type": "TREE"}) is False

    def test_tree_with_fruit_category_is_not_removable(self) -> None:
        obj = {"type": "circle", "object_type": "TREE", "plant_category": "FRUIT_TREE"}
        assert ProjectManager._is_removable_plant_object(obj) is False

    def test_garden_bed_is_not_removable(self) -> None:
        assert ProjectManager._is_removable_plant_object({"type": "polygon", "object_type": "GARDEN_BED"}) is False

    def test_no_object_type_is_not_removable(self) -> None:
        assert ProjectManager._is_removable_plant_object({"type": "rectangle"}) is False
