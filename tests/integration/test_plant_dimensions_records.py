"""Real plant assignment and dimension controls reach 2D, 3D and analysis.

PR #566, #557/#558: the renderer's illustrative height must never become a
recorded/analytical dimension; species spread edits must respect owner sizes.
"""

from __future__ import annotations

import copy
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.plant_height_estimate import ESTIMATED_HEIGHT_PARAM
from open_garden_planner.core.plant_renderer import PlantCategory
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.scene3d import Record
from open_garden_planner.core.scene3d.builders.plants import build_plant, plant_archetype
from open_garden_planner.models.plant_data import PlantSpeciesData
from open_garden_planner.services.bundled_species_db import lookup_species
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.sun_shadow_controller import collect_identified_casters
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel
from open_garden_planner.ui.plant_species_assignment import apply_species_to_item
from open_garden_planner.ui.view3d.snapshot import snapshot_records

DAY = date(2026, 6, 21)


@pytest.fixture()
def plant_editor(qtbot):
    scene = CanvasScene(width_cm=5000, height_cm=5000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    panel = PlantDatabasePanel()
    qtbot.addWidget(panel)
    panel.set_command_manager(view.command_manager)
    return scene, view, panel


def _assign(scene, kind: str = "TREE", category: str = "ROUND_DECIDUOUS") -> CircleItem:
    item = CircleItem(1000, 1000, 80, object_type=ObjectType[kind])
    item.plant_category = PlantCategory[category]
    scene.addItem(item)
    apply_species_to_item(
        item,
        PlantSpeciesData(
            common_name="Turkey oak" if kind == "TREE" else "Sparse online specimen",
            scientific_name="Quercus cerris" if kind == "TREE" else "Evidence specimen",
            max_height_cm=None,
            max_spread_cm=160,
            data_source="trefle",
        ).to_dict(),
    )
    return item


def _record(scene, item: CircleItem, at_date: date | None = DAY) -> Record:
    return snapshot_records(scene, at_date)[str(item.item_id)]


def _dimensions(record: Record) -> tuple[float, float]:
    parts = build_plant(record)
    positions = np.concatenate([part.mesh.positions for part in parts])
    low, high = positions.min(axis=0), positions.max(axis=0)
    return float(high[2]), float(max((high-low)[:2]))


@pytest.mark.parametrize(
    ("kind", "category", "height", "archetype"),
    [
        ("TREE", "ROUND_DECIDUOUS", 400, "canopy"),
        ("SHRUB", "COMPACT_SHRUB", 150, "mound"),
        ("PERENNIAL", "FLOWERING_PERENNIAL", 60, "mound"),
        ("PERENNIAL", "VEGETABLE", 50, "rosette"),
    ],
)
def test_sparse_assignment_estimates_only_the_3d_form(
    plant_editor, kind: str, category: str, height: float, archetype: str
) -> None:
    scene, view, _panel = plant_editor
    item = _assign(scene, kind, category)
    metadata = copy.deepcopy(item.metadata)
    steps, revision = view.command_manager.undo_depth, scene.plan_revision
    manager = ProjectManager()
    saved = manager.snapshot_dict(scene)

    record = _record(scene, item)

    assert record.height_cm is None
    assert record.params[ESTIMATED_HEIGHT_PARAM] == height
    assert plant_archetype(record) == archetype
    assert _dimensions(record) == pytest.approx((height, 160), abs=1e-3)
    assert all(part.casts_shadow for part in build_plant(record))
    assert collect_identified_casters(scene, DAY) == []
    assert item.metadata == metadata
    assert view.command_manager.undo_depth == steps
    assert scene.plan_revision == revision
    after = manager.snapshot_dict(scene)
    # The serializer stamps a new export time; all persisted plan content stays equal.
    saved["metadata"].pop("modified", None)
    after["metadata"].pop("modified", None)
    assert after == saved


@pytest.mark.parametrize("field", ["max_height_spin", "current_height_spin"])
def test_real_height_control_replaces_estimate_and_history_restores_it(
    plant_editor, field: str
) -> None:
    scene, view, panel = plant_editor
    item = _assign(scene)
    panel.set_selected_items([item])
    steps = view.command_manager.undo_depth
    control = getattr(panel, field)
    control.setValue(650)
    control.editingFinished.emit()

    record = _record(scene, item)
    assert view.command_manager.undo_depth == steps+1
    assert record.height_cm == 650
    assert ESTIMATED_HEIGHT_PARAM not in record.params
    assert _dimensions(record)[0] == pytest.approx(650, abs=1e-3)
    assert collect_identified_casters(scene, DAY)[0].height_cm == 650

    view.command_manager.undo()
    record = _record(scene, item)
    assert record.height_cm is None
    assert record.params[ESTIMATED_HEIGHT_PARAM] == 400
    assert _dimensions(record)[0] == pytest.approx(400, abs=1e-3)
    assert collect_identified_casters(scene, DAY) == []

    view.command_manager.redo()
    assert _record(scene, item).height_cm == 650
    assert ESTIMATED_HEIGHT_PARAM not in _record(scene, item).params


def test_bundled_oak_assignment_keeps_recorded_height(plant_editor) -> None:
    scene, _view, _panel = plant_editor
    item = _assign(scene)
    oak = lookup_species("Oak")
    assert oak is not None
    apply_species_to_item(item, dict(oak))
    record = _record(scene, item)
    assert record.height_cm == 4000
    assert ESTIMATED_HEIGHT_PARAM not in record.params
    assert _dimensions(record)[0] == pytest.approx(4000, abs=1e-3)


@pytest.mark.parametrize("rotation", [0, 37])
def test_max_spread_control_updates_geometry_records_history_and_file(
    plant_editor, tmp_path: Path, rotation: float
) -> None:
    scene, view, panel = plant_editor
    item = _assign(scene)
    item._apply_rotation(rotation)
    item_id = str(item.item_id)
    center = item.mapToScene(item.rect().center())
    panel.set_selected_items([item])
    steps, revision = view.command_manager.undo_depth, scene.plan_revision

    panel.max_spread_spin.setValue(300)
    panel.max_spread_spin.editingFinished.emit()

    assert view.command_manager.undo_depth == steps+1
    assert scene.plan_revision > revision
    assert item.radius == 150
    assert item.mapToScene(item.rect().center()) == center
    assert item.transformOriginPoint() == item.rect().center()
    assert _record(scene, item).params["radius_cm"] == 150
    assert _dimensions(_record(scene, item))[1] == pytest.approx(300, abs=1e-3)

    view.command_manager.undo()
    assert item.metadata["plant_species"]["max_spread_cm"] == 160
    assert item.radius == 80
    assert _record(scene, item).params["radius_cm"] == 80
    assert item.mapToScene(item.rect().center()) == center
    view.command_manager.redo()
    assert item.metadata["plant_species"]["max_spread_cm"] == 300
    assert item.radius == 150
    assert _record(scene, item).params["radius_cm"] == 150

    manager = ProjectManager()
    path = tmp_path / "spread.ogp"
    manager.save(scene, path)
    manager.load(scene, path)
    loaded = next(it for it in scene.items() if str(getattr(it, "item_id", "")) == item_id)
    assert loaded.radius == 150
    assert loaded.mapToScene(loaded.rect().center()) == center
    assert loaded.transformOriginPoint() == loaded.rect().center()
    assert loaded.rotation() == rotation
    assert _record(scene, loaded).params["radius_cm"] == 150
    manager.save(scene, path)
    manager.load(scene, path)
    record = snapshot_records(scene, DAY)[item_id]
    assert record.params["radius_cm"] == 150


@pytest.mark.parametrize("override", ["current", "legacy_current", "custom", "spacing", "cleared"])
def test_max_spread_preserves_owner_dimensions_and_cleared_footprint(
    plant_editor, override: str
) -> None:
    scene, view, panel = plant_editor
    item = _assign(scene)
    if override in {"current", "legacy_current"}:
        key = "current_spread_cm" if override == "current" else "current_diameter_cm"
        item.metadata["plant_instance"] = {key: 70}
    elif override == "custom":
        item.set_radius_centered(110)
    elif override == "spacing":
        item.spacing_radius_cm = 30
    radius = item.radius
    old_record_radius = _record(scene, item).params["radius_cm"]
    panel.set_selected_items([item])
    steps = view.command_manager.undo_depth

    panel.max_spread_spin.setValue(0 if override == "cleared" else 300)
    panel.max_spread_spin.editingFinished.emit()

    assert view.command_manager.undo_depth == steps+1
    assert item.radius == radius
    assert _record(scene, item).params["radius_cm"] == old_record_radius
    expected = None if override == "cleared" else 300
    assert item.metadata["plant_species"]["max_spread_cm"] == expected
    if override == "spacing":
        assert item.spacing_radius_cm == 30
    if override in {"current", "legacy_current"}:
        assert item.metadata["plant_instance"][key] == 70
    view.command_manager.undo()
    assert item.radius == radius
    assert item.metadata["plant_species"]["max_spread_cm"] == 160
    view.command_manager.redo()
    assert item.radius == radius


def test_measured_spread_keeps_footprint_while_plan_date_projects_the_canopy(plant_editor) -> None:
    scene, _view, panel = plant_editor
    item = _assign(scene)
    item.metadata["plant_instance"] = {"current_spread_cm": 70, "planting_date": "2020-01-01"}
    panel.set_selected_items([item])
    panel.max_spread_spin.setValue(300)
    panel.max_spread_spin.editingFinished.emit()

    assert item.radius == 80
    assert _record(scene, item, date(2020, 1, 1)).params["radius_cm"] == 35
    # A tree's ten-year growth horizon has elapsed; only the display canopy grows.
    assert _record(scene, item, date(2031, 1, 1)).params["radius_cm"] == 150
    assert item.metadata["plant_instance"]["current_spread_cm"] == 70
    assert item.radius == 80


def test_first_recorded_max_spread_adopts_the_new_species_dimension(plant_editor) -> None:
    scene, view, panel = plant_editor
    item = _assign(scene)
    item.metadata["plant_species"]["max_spread_cm"] = None
    item.set_radius_centered(110)
    panel.set_selected_items([item])
    steps = view.command_manager.undo_depth

    panel.max_spread_spin.setValue(300)
    panel.max_spread_spin.editingFinished.emit()

    assert view.command_manager.undo_depth == steps+1
    assert item.radius == 150
    assert _record(scene, item).params["radius_cm"] == 150
    view.command_manager.undo()
    assert item.radius == 110
    assert item.metadata["plant_species"]["max_spread_cm"] is None
