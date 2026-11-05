"""Integration tests for agent delete_object on a group containing journal pins (issue #740)."""

import uuid

from open_garden_planner.app.agent_host import AgentHost
from open_garden_planner.core.commands import AddJournalNoteCommand, GroupCommand
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.models.journal_note import JournalNote
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem


class DummyHost:
    def __init__(self, scene: CanvasScene, view: CanvasView, pm: ProjectManager) -> None:
        self.canvas_scene = scene
        self.canvas_view = view
        self._project_manager = pm
        self.command_manager = view.command_manager

    def _resolve_agent_item(self, item_id: str) -> object:
        uid = uuid.UUID(item_id)
        return self.canvas_scene.find_item_by_id(uid)

    def _agent_linked_roof_ridge(self, item: object) -> list[object]:
        return []

    def _agent_require_unique_items(self, items: list[object], action: str = "delete") -> None:
        pass

    def _agent_item_uuid(self, item: object) -> uuid.UUID:
        return item.item_id

    def _agent_item_constraints(self, item: object) -> list[object]:
        return []

    def _agent_document_items(self) -> list[object]:
        return [i for i in self.canvas_scene.items() if hasattr(i, "item_id")]


def test_agent_delete_object_on_group_prunes_nested_notes(qtbot: object) -> None:
    """Agent delete_object(group_id) removes nested pins and notes in one undo step."""
    scene = CanvasScene()
    view = CanvasView(scene=scene)
    pm = ProjectManager()
    dummy = DummyHost(scene, view, pm)
    agent = AgentHost(dummy)  # type: ignore[arg-type]

    note = JournalNote(date="2026-05-13", text="Planting note", scene_x=10.0, scene_y=20.0)
    pin = JournalPinItem(x=10.0, y=20.0, note_id=note.id)
    rect = RectangleItem(0.0, 0.0, 100.0, 100.0, layer_id=scene.active_layer.id)
    scene.addItem(rect)
    view.command_manager.execute(AddJournalNoteCommand(pm, scene, pin, note))
    assert note.id in pm.garden_journal_notes

    # Group rect and pin
    cmd = GroupCommand(scene, [rect, pin])
    view.command_manager.execute(cmd)
    group = rect.parentItem()
    assert group is not None
    group_id_str = str(group.item_id)

    # Agent calls delete_object on the group
    result = agent._do_agent_delete_object(group_id_str)
    assert result["action"] == "delete"
    assert group.scene() is None
    assert pin.scene() is None
    assert note.id not in pm.garden_journal_notes

    # Undo restores group, pin, and note in ONE step
    agent._do_agent_undo()
    assert group.scene() is scene
    assert pin.parentItem() is group
    assert note.id in pm.garden_journal_notes

    # Redo deletes group, pin, and note again
    view.command_manager.redo()
    assert group.scene() is None
    assert note.id not in pm.garden_journal_notes
