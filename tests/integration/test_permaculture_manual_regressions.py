"""Owner manual-pass regressions at the actual placement and name surfaces."""

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication, QMainWindow

from open_garden_planner.core.guild_commands import prepare_guild
from open_garden_planner.core.i18n import load_translator
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.permaculture_commands import FoodForestLayersCommand
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.core.tools.circle_tool import CircleTool
from open_garden_planner.models.plant_data import PermacultureLayer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.dialogs.guild_template_editor import GuildTemplateEditor
from open_garden_planner.ui.dialogs.insert_guild_dialog import InsertGuildDialog
from open_garden_planner.ui.panels.guilds_panel import GuildsPanel
from open_garden_planner.ui.widgets.trait_filters import trait_label


@pytest.mark.parametrize("state", ["eligible", "renamed", "hidden", "locked", "disabled"])
def test_gallery_click_blueberry_uses_semantic_layer(qtbot, state):
    window = QMainWindow()
    window._project_manager = ProjectManager(window)
    scene = CanvasScene(width_cm=4000, height_cm=4000)
    view = CanvasView(scene)
    window.setCentralWidget(view)
    qtbot.addWidget(window)
    view.command_manager.execute(FoodForestLayersCommand(scene, {
        value.value: trait_label(value.value) for value in PermacultureLayer
    }))
    window._project_manager.auto_assign_permaculture_layers = state != "disabled"
    active = scene.active_layer
    target = next(layer for layer in scene.layers if layer.permaculture_layer == "shrub")
    if state == "renamed":
        target.name = "Custom shrub layer"
    target.visible = state != "hidden"
    target.locked = state == "locked"
    tool = CircleTool(view, ObjectType.SHRUB)
    tool.set_plant_info(species="blueberry")
    tool._center_point = QPointF(2000, 2000)
    depth = len(view.command_manager._undo_stack)
    tool._finalize_circle(QPointF(2050, 2000))
    plant = next(item for item in scene.items() if getattr(item, "plant_species", "") == "blueberry")
    expected = target if state in {"eligible", "renamed"} else active
    assert scene.get_layer_by_id(plant.layer_id) is expected
    assert scene.active_layer is active
    assert len(view.command_manager._undo_stack) == depth + 1
    view.command_manager.undo()
    assert plant.scene() is None
    view.command_manager.redo()
    assert scene.get_layer_by_id(plant.layer_id) is expected


def test_guild_picker_species_names_are_german(qtbot):
    app = QApplication.instance()
    try:
        assert load_translator(app, "de")
        scene = CanvasScene(width_cm=4000, height_cm=4000)
        picker = InsertGuildDialog(scene)
        qtbot.addWidget(picker)
        picker.template_combo.setCurrentIndex(picker.template_combo.findData("apple-guild"))
        assert picker.centre_combo.currentText() == "Apfelbaum"
        assert [combo.currentText() for combo in picker.role_choices.values()] == [
            "Feuerbohne", "Borretsch", "Erdbeere"
        ]
        editor = GuildTemplateEditor(picker.library, picker.template, duplicate=True)
        qtbot.addWidget(editor)
        assert editor.centre_combo.currentText() == "Apfelbaum — malus domestica"
        view = CanvasView(scene)
        qtbot.addWidget(view)
        command = prepare_guild(scene, picker.template, picker.catalog, "Test", QPointF(2000, 2000))
        view.command_manager.execute(command)
        from open_garden_planner.services.guild_service import compute_guilds

        snapshots = [{"item_id": str(item.item_id), "guild": item.metadata["guild"],
                      "functions": item.metadata["plant_species"]["functions"]} for item in command.items]
        statuses, errors = compute_guilds(snapshots)
        assert not errors
        panel = GuildsPanel(scene)
        qtbot.addWidget(panel)
        panel.set_statuses(statuses)
        root = panel.tree.topLevelItem(0)
        assert [root.child(i).text(0) for i in range(3, 7)] == [
            "Apfelbaum", "Feuerbohne", "Borretsch", "Erdbeere"
        ]
        assert command.items[0].metadata["plant_species"]["common_name"] == "Apple Tree"
        command.items[0].name = "Mein Baum"
        panel.set_statuses(statuses)
        assert panel.tree.topLevelItem(0).child(3).text(0) == "Mein Baum"
    finally:
        load_translator(app, "en")
