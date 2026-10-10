"""F2 workflows through commands, actual widgets and shared diagnostic snapshots."""

import json
import threading
from dataclasses import asdict

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api.diagnostics import diagnostics_from_records
from open_garden_planner.core.commands import DeleteItemsCommand
from open_garden_planner.core.guild_commands import GuildMembershipCommand, prepare_guild
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.services.guild_library import GuildLibrary
from open_garden_planner.services.species_catalog import offline_catalog
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.dialogs.guild_template_editor import GuildTemplateEditor
from open_garden_planner.ui.dialogs.insert_guild_dialog import InsertGuildDialog
from open_garden_planner.ui.guild_coordinator import GuildCoordinator
from open_garden_planner.ui.panels.diagnostics_panel import DiagnosticsPanel
from open_garden_planner.ui.panels.guilds_panel import GuildsPanel


@pytest.fixture
def guild_canvas(qtbot, tmp_path):
    scene = CanvasScene(width_cm=4000, height_cm=4000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    diagnostics = DiagnosticsPanel(scene)
    guilds = GuildsPanel(scene)
    qtbot.addWidget(diagnostics)
    qtbot.addWidget(guilds)
    coordinator = GuildCoordinator(scene, view.command_manager, diagnostics, guilds, view)
    library = GuildLibrary(user_dir=tmp_path / "guilds")
    return scene, view, coordinator, library


def test_insert_delete_missing_role_and_roundtrip(guild_canvas, tmp_path):
    scene, view, coordinator, library = guild_canvas
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "Orchard", QPointF(1500, 1500))
    view.command_manager.execute(command)
    assert len(view.command_manager._undo_stack) == 1
    identities = [plant.item_id for plant in command.items]
    coordinator.refresh()
    assert not coordinator.statuses[0].missing
    view.command_manager.undo()
    assert all(plant.scene() is None for plant in command.items)
    view.command_manager.redo()
    assert [plant.item_id for plant in command.items] == identities
    fixer = command.items[1]
    view.command_manager.execute(DeleteItemsCommand(scene, [fixer]))
    coordinator.refresh()
    assert coordinator.statuses[0].missing == {"nitrogen_fixer": 1}
    centre = command.items[0]
    assert centre._guild_badge.isVisible()
    assert centre._guild_badge.toolTip()
    records = ProjectManager.diagnostics_snapshot(scene)
    api = diagnostics_from_records(records, kind="guild_role_missing")
    panel = [record for record in coordinator.diagnostics_panel.records if record.kind == "guild_role_missing"]
    assert [a.model_dump() for a in api] == [asdict(p) for p in panel]
    view.command_manager.undo()
    coordinator.refresh()
    assert not coordinator.statuses[0].missing
    view.command_manager.execute(DeleteItemsCommand(scene, [centre]))
    assert all("guild" not in plant.metadata for plant in command.items[1:])
    view.command_manager.undo()
    assert all("guild" in plant.metadata for plant in command.items)
    manager = ProjectManager()
    manager.save(scene, tmp_path / "guild.ogp")
    fresh = CanvasScene(width_cm=4000, height_cm=4000)
    manager.load(fresh, tmp_path / "guild.ogp")
    assert len([item for item in fresh.items() if getattr(item, "metadata", {}).get("guild")]) == 4


def test_existing_centre_preflight_cancel_and_copy(guild_canvas, qtbot):
    scene, view, coordinator, library = guild_canvas
    template = library.templates["apple-guild"]
    original = prepare_guild(scene, template, offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(original)
    for item in original.items:
        item.setSelected(True)
    view.duplicate_selected()
    copies = [item for item in scene.selectedItems() if getattr(item, "metadata", {}).get("guild")]
    assert len(copies) == 4
    assert copies[0].metadata["guild"]["guild_id"] != original.items[0].metadata["guild"]["guild_id"]
    view.command_manager.undo()
    scene.clearSelection()
    original.items[1].setSelected(True)
    view.duplicate_selected()
    assert all("guild" not in item.metadata for item in scene.selectedItems())
    count, depth = len(scene.items()), len(view.command_manager._undo_stack)
    dialog = InsertGuildDialog(scene, library=library)
    qtbot.addWidget(dialog)
    dialog.x_spin.setValue(1)
    dialog.y_spin.setValue(1)
    dialog.insert()
    assert dialog.command is None and dialog.error_label.text()
    dialog.reject()
    assert len(scene.items()) == count and len(view.command_manager._undo_stack) == depth
    # Undoable membership removal lets an existing tree become a new centre.
    centre = original.items[0]
    view.command_manager.execute(GuildMembershipCommand([(item, None) for item in original.items]))
    command = prepare_guild(scene, template, offline_catalog(), "B", QPointF(), existing_centre=centre)
    assert len(command.items) == 3
    view.command_manager.execute(command)
    view.command_manager.undo()
    assert "guild" not in centre.metadata


def test_editor_duplicate_save_reload_insert_and_snapshot(guild_canvas, qtbot):
    scene, view, coordinator, library = guild_canvas
    template = library.templates["apple-guild"]
    editor = GuildTemplateEditor(library, template, duplicate=True)
    qtbot.addWidget(editor)
    editor.name_edit.setText("Custom orchard")
    editor.save()
    assert editor.saved_template is not None
    identity = editor.saved_template.id
    picker = InsertGuildDialog(scene, library=library)
    qtbot.addWidget(picker)
    picker.template_combo.setCurrentIndex(picker.template_combo.findData(identity))
    picker.insert()
    assert picker.command is not None
    view.command_manager.execute(picker.command)
    centre = picker.command.items[0]
    saved = centre.metadata["guild"]["template"]
    edit = GuildTemplateEditor(library, library.templates[identity])
    qtbot.addWidget(edit)
    edit.name_edit.setText("Changed future template")
    edit.save()
    assert edit.saved_template.version == 2
    assert saved["version"] == 1 and saved["name"] == "Custom orchard"


@pytest.mark.parametrize("angle", [0, 45, 215])
def test_badge_does_not_change_geometry(guild_canvas, angle):
    scene, view, coordinator, library = guild_canvas
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(command)
    centre = command.items[0]
    centre.rotation_angle = angle
    before = (centre.rect(), centre.pos(), centre.transformOriginPoint(), ProjectManager._serialize_item(centre))
    view.command_manager.execute(DeleteItemsCommand(scene, [command.items[1]]))
    coordinator.refresh()
    after = (centre.rect(), centre.pos(), centre.transformOriginPoint(), ProjectManager._serialize_item(centre))
    assert before == after


def test_traits_and_guild_warning_over_real_mcp(guild_canvas, qtbot):
    from open_garden_planner.agent_api import AgentApiServer
    from tests.integration.test_agent_api_server import _drive, _free_port, _providers

    scene, view, coordinator, library = guild_canvas
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(command)
    view.command_manager.execute(DeleteItemsCommand(scene, [command.items[1]]))
    coordinator.refresh()
    server = AgentApiServer(_providers(scene), port=_free_port())
    server.start()
    result = {}
    async def body(session):
        detail = await session.call_tool("get_object", {"item_id": str(command.items[0].item_id)})
        result["detail"] = detail.structuredContent["result"]
        warnings = await session.call_tool("get_diagnostics", {"kind": "guild_role_missing"})
        result["warnings"] = warnings.structuredContent["result"]
        resource = await session.read_resource("garden://species")
        result["species"] = json.loads(resource.contents[0].text)
    client = threading.Thread(target=_drive, args=(server, body, result))
    client.start()
    try:
        qtbot.waitUntil(lambda: result.get("done", False), timeout=15000)
        assert "error" not in result, result.get("error")
        assert result["detail"]["permaculture_layer"] == "sub_canopy"
        assert result["detail"]["functions"] == []
        assert result["warnings"][0]["details"]["function"] == "nitrogen_fixer"
        assert result["warnings"][0]["details"]["present_count"] == 0
        assert len(result["species"]) == 118
        assert all("functions" in species and "permaculture_layer" in species for species in result["species"])
    finally:
        server.stop()
        client.join(timeout=5)


def test_grouped_centre_delete_and_navigation(guild_canvas, qtbot):
    scene, view, coordinator, library = guild_canvas
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(command)
    centre, fixer = command.items[:2]
    centre.setSelected(True)
    command.items[2].setSelected(True)
    view._group_selected()
    group = centre.parentItem()
    assert group is not None
    view.command_manager.execute(DeleteItemsCommand(scene, [fixer]))
    coordinator.refresh()
    diagnostic = next(d for d in coordinator.diagnostics_panel.records if d.kind == "guild_role_missing")
    assert diagnostic.item_ids == [str(group.item_id)]
    assert diagnostic.details["centre_id"] == str(centre.item_id)
    coordinator.guilds_panel.select_ids([str(centre.item_id)])
    qtbot.waitUntil(group.isSelected)
    view.command_manager.execute(DeleteItemsCommand(scene, [group]))
    assert "guild" not in command.items[3].metadata
    view.command_manager.undo()
    assert command.items[3].metadata["guild"]["guild_id"] == centre.metadata["guild"]["guild_id"]


def test_explicit_assignment_clears_deficit_and_refresh_is_idempotent(guild_canvas, qtbot):
    scene, view, coordinator, library = guild_canvas
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(command)
    fixer = command.items[1]
    view.command_manager.execute(GuildMembershipCommand([(fixer, None)]))
    coordinator.refresh()
    assert coordinator.statuses[0].missing == {"nitrogen_fixer": 1}
    guild = {"guild_id": command.items[0].metadata["guild"]["guild_id"], "role": "ground_cover"}
    view.command_manager.execute(GuildMembershipCommand([(fixer, guild)]))
    coordinator.refresh()
    assert not coordinator.statuses[0].missing  # Actual functions, even with another intended role.
    panel = coordinator.diagnostics_panel
    panel.kind_filter.setCurrentIndex(panel.kind_filter.findData("guild_role_missing"))
    assert panel.rows.count() == 0
    manager = ProjectManager()
    before = (manager._serialize_scene(scene).to_dict(), len(view.command_manager._undo_stack))
    before[0]["metadata"].pop("modified", None)  # Serialization always stamps wall-clock time.
    for _ in range(5):
        coordinator.refresh()
    qtbot.wait(150)
    after = manager._serialize_scene(scene).to_dict()
    after["metadata"].pop("modified", None)
    assert before == (after, len(view.command_manager._undo_stack))
    scene.clear()
    coordinator.refresh()
    assert not coordinator.statuses and not scene._guild_diagnostics and panel.rows.count() == 0


def test_editor_radius_row_removal_and_readonly(guild_canvas, qtbot):
    from open_garden_planner.ui.dialogs.guild_template_editor import RadiusEditor

    _, _, _, library = guild_canvas
    template = library.templates["apple-guild"]
    editor = GuildTemplateEditor(library, template, duplicate=True)
    qtbot.addWidget(editor)
    radius = editor.roles_table.cellWidget(0, 2)
    assert isinstance(radius, RadiusEditor)
    radius.mode.setCurrentIndex(1)
    radius.distance.setValue(125)
    assert editor.definition().roles[0].ring_radius_cm == 125
    editor.roles_table.removeRow(0)
    editor.roles_table.cellWidget(1, 3).setText("unresolved")
    assert "unresolved" in editor.validation_label.text()
    editor.save()
    assert editor.saved_template is None
    readonly = GuildTemplateEditor(library, template, readonly=True)
    qtbot.addWidget(readonly)
    readonly.save()
    assert readonly.saved_template is None and not library.user_paths


def test_mirror_copy_species_snapshot_is_independent(guild_canvas):
    from open_garden_planner.core.commands import MirrorItemsCommand
    from open_garden_planner.core.mirror_geometry import build_mirrored_item
    from open_garden_planner.ui.plant_traits import apply_trait

    scene, view, _, library = guild_canvas
    original = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(original)
    copies = [build_mirrored_item(item, QPointF(2000, 0), QPointF(2000, 4000)) for item in original.items]
    view.command_manager.execute(MirrorItemsCommand(scene, original.items, copies, copy=True))
    assert copies[0].metadata["guild"]["guild_id"] != original.items[0].metadata["guild"]["guild_id"]
    apply_trait(copies[1], [], field="functions")
    assert original.items[1].metadata["plant_species"]["functions"] == ["nitrogen_fixer"]


@pytest.mark.parametrize("state", ["locked", "hidden"])
def test_existing_centre_honours_ancestor_layers(guild_canvas, state):
    from open_garden_planner.core.commands import MoveToLayerCommand
    from open_garden_planner.core.guild_commands import guild_plant_layers_editable
    from open_garden_planner.models.layer import Layer

    scene, view, _, library = guild_canvas
    original = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(original)
    centre = original.items[0]
    view.command_manager.execute(GuildMembershipCommand([(plant, None) for plant in original.items]))
    centre.setSelected(True)
    original.items[2].setSelected(True)
    view._group_selected()
    group = centre.parentItem()
    target = Layer(name="Protected")
    scene.add_layer(target)
    view.command_manager.execute(MoveToLayerCommand([group], target.id, scene, target.name))
    target.locked = state == "locked"
    target.visible = state != "hidden"
    scene._update_items_visibility()
    assert not guild_plant_layers_editable(scene, centre)
    with pytest.raises(ValueError, match="layers"):
        prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "B", QPointF(), existing_centre=centre)


def test_malformed_identity_does_not_dissolve_unrelated_data(guild_canvas):
    scene, view, _, library = guild_canvas
    original = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(original)
    centre, survivor = original.items[:2]
    centre.metadata["guild"] = {"guild_id": None, "role": "centre"}
    survivor.metadata["guild"] = {"role": "ground_cover", "raw": "preserve"}
    view.command_manager.execute(DeleteItemsCommand(scene, [centre]))
    assert survivor.metadata["guild"] == {"role": "ground_cover", "raw": "preserve"}
    view.command_manager.undo()
    assert centre.metadata["guild"] == {"guild_id": None, "role": "centre"}


def test_deferred_action_and_load_clear_previous_document(guild_canvas, qtbot, tmp_path):
    from PyQt6.QtWidgets import QMenu

    from open_garden_planner.ui.guild_actions import build_guild_actions

    scene, view, coordinator, library = guild_canvas
    original = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(original)
    view.command_manager.execute(DeleteItemsCommand(scene, [original.items[1]]))
    coordinator.refresh()
    assert scene._guild_diagnostics and coordinator.diagnostics_panel.records
    menu = QMenu(view)
    build_guild_actions(menu, original.items[0])
    menu.actions()[-2].trigger()
    manager = ProjectManager()
    empty = tmp_path / "empty.ogp"
    manager.save(CanvasScene(), empty)
    manager.load(scene, empty)
    assert not scene._guild_diagnostics and not coordinator.statuses and not coordinator.diagnostics_panel.records
    qtbot.wait(150)  # Pending action resolves by identity/document generation, without a dialog.


def test_german_refusal_and_api_messages(guild_canvas, qtbot):
    from open_garden_planner.core.i18n import load_translator
    from open_garden_planner.models.guild_errors import GuildValidationError

    scene, view, _, library = guild_canvas
    app = __import__("PyQt6.QtWidgets", fromlist=["QApplication"]).QApplication.instance()
    try:
        assert load_translator(app, "de")
        editor = GuildTemplateEditor(library)
        qtbot.addWidget(editor)
        editor.save()
        assert "Name darf nicht leer" in editor.validation_label.text()
        assert "must be" not in editor.validation_label.text()
        picker = InsertGuildDialog(scene, library=library)
        qtbot.addWidget(picker)
        picker.x_spin.setValue(1)
        picker.y_spin.setValue(1)
        picker.insert()
        assert "Zeichenfläche hinaus" in picker.error_label.text()
        assert "outside the canvas" not in picker.error_label.text()
        command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
        view.command_manager.execute(command)
        view.command_manager.execute(GuildMembershipCommand([(plant, None) for plant in command.items]))
        picker.reload()
        centre = command.items[0]
        picker.existing_combo.setCurrentIndex(picker.existing_combo.findData(str(centre.item_id)))
        view.command_manager.execute(DeleteItemsCommand(scene, [centre]))
        picker.insert()
        assert "Zentrum ist nicht mehr im Plan" in picker.error_label.text()
        assert "no longer in the plan" not in picker.error_label.text()
        assert str(GuildValidationError("bounds")).startswith("Guild layout extends")
    finally:
        load_translator(app, "en")


def test_preview_and_pending_navigation_invalidated_on_document_replacement(guild_canvas, qtbot, tmp_path):
    scene, view, coordinator, library = guild_canvas
    picker = InsertGuildDialog(scene, library=library)
    qtbot.addWidget(picker)
    picker.preview()
    assert picker._preview
    scene.clear()
    assert picker._closed and not picker._preview
    picker.reject()  # Idempotent cleanup after C++ marker destruction.
    command = prepare_guild(scene, library.templates["apple-guild"], offline_catalog(), "A", QPointF(1500, 1500))
    view.command_manager.execute(command)
    manager = ProjectManager()
    file = tmp_path / "same-ids.ogp"
    manager.save(scene, file)
    coordinator.diagnostics_panel.select_ids([str(command.items[0].item_id)])
    coordinator.guilds_panel.select_ids([str(command.items[0].item_id)])
    manager.load(scene, file)
    qtbot.wait(150)
    assert not scene.selectedItems()


def test_coordinator_accepts_non_circular_imported_plant(guild_canvas):
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    scene, _, coordinator, library = guild_canvas
    plant = RectangleItem(0, 0, 40, 60)
    plant.object_type = ObjectType.PERENNIAL
    scene.addItem(plant)
    coordinator.refresh()
    assert not coordinator.statuses
    plant.metadata["guild"] = {"guild_id": "imported", "role": "centre", "name": "Imported",
                               "template": library.templates["apple-guild"].to_dict()}
    before = (plant.rect(), plant.pos(), plant.transformOriginPoint(), ProjectManager._serialize_item(plant))
    coordinator.refresh()
    assert plant._guild_badge.isVisible()
    assert coordinator.statuses[0].missing["nitrogen_fixer"] == 1
    assert before == (plant.rect(), plant.pos(), plant.transformOriginPoint(), ProjectManager._serialize_item(plant))
