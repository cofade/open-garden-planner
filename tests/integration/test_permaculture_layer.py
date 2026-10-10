"""F1 real-widget workflow: drop, trait history, persistence, filter and preset."""

from PyQt6.QtCore import QPointF, Qt

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.permaculture_commands import (
    AutoAssignPermacultureCommand,
    FoodForestLayersCommand,
    placement_layer,
)
from open_garden_planner.core.project import ProjectData, ProjectManager
from open_garden_planner.core.tools import ToolType
from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.services.plant_api.manager import PlantAPIManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.dialogs.plant_search_dialog import PlantSearchDialog
from open_garden_planner.ui.panels.plant_database_panel import PlantDatabasePanel
from open_garden_planner.ui.widgets.trait_filters import trait_label


def test_drop_edit_undo_roundtrip_filter_preset(qtbot, tmp_path):
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    plant = view._create_plant_item_at_scene_pos(QPointF(500, 500), ToolType.SHRUB,
                                                ObjectType.SHRUB, 50, "blueberry")
    panel = PlantDatabasePanel()
    qtbot.addWidget(panel)
    panel.set_selected_items([plant])
    depth = len(view.command_manager._undo_stack)
    panel.layer_combo.setCurrentIndex(panel.layer_combo.findData("ground_cover"))
    assert len(view.command_manager._undo_stack) == depth + 1
    panel.functions_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert len(view.command_manager._undo_stack) == depth + 2
    assert plant.metadata["plant_species"]["functions"] == ["nitrogen_fixer"]
    view.command_manager.undo()
    panel.set_selected_items([plant])
    assert panel.functions_list.item(0).checkState() == Qt.CheckState.Unchecked
    view.command_manager.redo()
    manager = ProjectManager()
    manager.auto_assign_permaculture_layers = True
    manager.save(scene, tmp_path / "traits.ogp")
    loaded = ProjectData.from_dict(__import__("json").loads((tmp_path / "traits.ogp").read_text(encoding="utf8")))
    assert loaded.auto_assign_permaculture_layers
    assert loaded.objects[0]["metadata"]["plant_species"]["functions"] == ["nitrogen_fixer"]
    active = scene.active_layer
    command = FoodForestLayersCommand(scene, {v.value: trait_label(v.value) for v in PermacultureLayer})
    view.command_manager.execute(command)
    assert len(scene.layers) == 8 and scene.active_layer is active
    assert not FoodForestLayersCommand(scene, {v.value: trait_label(v.value) for v in PermacultureLayer}).added
    target = placement_layer(scene, plant.metadata["plant_species"], True)
    assert target.permaculture_layer == "ground_cover"
    target.name = "Renamed"
    assert placement_layer(scene, plant.metadata["plant_species"], True) is target
    target.locked = True
    assert placement_layer(scene, plant.metadata["plant_species"], True) is active
    dialog = PlantSearchDialog(PlantAPIManager())
    qtbot.addWidget(dialog)
    dialog.trait_filters.function_buttons["nitrogen_fixer"].setChecked(True)
    assert dialog.results_list.count() == 4
    dialog.reject()


def test_auto_assignment_drop_and_setting_history(qtbot, tmp_path):
    scene = CanvasScene(width_cm=3000, height_cm=3000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    manager = ProjectManager()
    view._project_manager = manager
    active = scene.active_layer
    view.command_manager.execute(FoodForestLayersCommand(scene, {value.value: trait_label(value.value) for value in PermacultureLayer}))
    view.command_manager.execute(AutoAssignPermacultureCommand(manager, True))
    view.command_manager.undo()
    assert not manager.auto_assign_permaculture_layers
    view.command_manager.redo()
    assert manager.auto_assign_permaculture_layers
    depth = len(view.command_manager._undo_stack)
    plant = view._create_plant_item_at_scene_pos(QPointF(1500, 1500), ToolType.SHRUB, ObjectType.SHRUB, 50, "blueberry")
    assert len(view.command_manager._undo_stack) == depth + 1
    target = scene.get_layer_by_id(plant.layer_id)
    assert target.permaculture_layer == "shrub" and scene.active_layer is active
    view.command_manager.undo()
    assert plant.scene() is None
    view.command_manager.redo()
    assert plant.layer_id == target.id
    manager.save(scene, tmp_path / "assigned.ogp")
    fresh = CanvasScene()
    other = ProjectManager()
    other.load(fresh, tmp_path / "assigned.ogp")
    assert other.auto_assign_permaculture_layers
    other.new_project()
    assert not other.auto_assign_permaculture_layers
