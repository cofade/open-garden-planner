"""Pending annotations end at the editor boundary, without hiding other writes."""

import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.core.commands import CreateItemCommand
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.fixture
def window(qtbot, monkeypatch):
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    monkeypatch.setattr(app, "_confirm_discard_changes", lambda: True)
    yield app
    app._project_manager.mark_clean()


def _place(window, kind=ToolType.TEXT):
    view = window.canvas_view
    view.set_active_tool(kind)
    tool = view.tool_manager.active_tool
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    tool.mouse_press(event, QPointF(200, 200))
    if kind == ToolType.CALLOUT:
        tool.mouse_release(event, QPointF(300, 250))
    return tool, tool._pending.item


@pytest.mark.parametrize("kind", [ToolType.TEXT, ToolType.CALLOUT])
def test_finishing_inline_edit_announces_placement_at_once(window, kind):
    scene = window.canvas_scene
    revision = scene.plan_revision
    tool, item = _place(window, kind)
    editor = item if kind == ToolType.TEXT else item._text_child
    editor.setPlainText("North border")
    item.finish_editing()
    assert scene.plan_revision > revision
    assert tool._pending is None
    assert item.content == "North border"


def test_resize_during_empty_placement_is_announced_and_survives_cancel(window):
    scene = window.canvas_scene
    tool, item = _place(window)
    revision = scene.plan_revision
    scene.resize_canvas(1234, 2345)
    assert scene.plan_revision > revision
    after_resize = scene.plan_revision
    tool.cancel()
    assert item.scene() is None
    assert scene.plan_revision == after_resize
    assert window._project_manager.is_dirty


def test_refused_discard_keeps_pair_dirty_and_announces_it(window):
    scene, view = window.canvas_scene, window.canvas_view
    tool, item = _place(window)
    other = RectangleItem(20, 20, 30, 30)
    view.command_manager.execute(CreateItemCommand(scene, other, "rectangle"))
    revision = scene.plan_revision
    depth = view.command_manager.undo_depth
    tool.cancel()
    assert item.scene() is scene
    assert view.command_manager.undo_depth == depth
    assert scene.plan_revision > revision
    assert window._project_manager.is_dirty


@pytest.mark.parametrize("kind", [ToolType.TEXT, ToolType.CALLOUT])
def test_save_finishes_annotation_before_serialization(window, tmp_path, kind):
    tool, item = _place(window, kind)
    editor = item if kind == ToolType.TEXT else item._text_child
    editor.setPlainText("Typed but not committed")
    target = tmp_path / "annotation.ogp"
    window._project_manager.save(window.canvas_scene, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert any(obj.get("content") == "Typed but not committed" for obj in data["objects"])
    assert tool._pending is None


def test_history_navigation_finishes_pending_annotation(window):
    tool, item = _place(window)
    item.setPlainText("North border")
    window.canvas_view.command_manager.undo()
    assert item.content == "North border"
    assert tool._pending is None
    assert item.scene() is None
    window.canvas_view.command_manager.redo()
    assert item.scene() is window.canvas_scene
    assert item.content == "North border"


def test_an_old_editor_cannot_finish_a_new_placement(window):
    tool, old = _place(window)
    old.setPlainText("First note")
    old.finish_editing()
    _, current = _place(window)
    old.editing_finished.emit()
    assert tool._pending.item is current
    tool.cancel()


def test_stale_placement_cannot_commit_the_current_placement(window):
    view = window.canvas_view
    tool, old = _place(window)
    stale = tool._pending
    old.setPlainText("First note")
    old.finish_editing()
    _, current = _place(window)
    revision = window.canvas_scene.plan_revision
    view.commit_cancellable_placement(stale)
    assert window.canvas_scene.plan_revision == revision
    assert tool._pending.item is current
    tool.cancel()


def test_a_successful_discard_after_interleaved_commands_keeps_dirty(window):
    scene, view = window.canvas_scene, window.canvas_view
    window._project_manager.mark_clean()
    tool, item = _place(window)
    other = RectangleItem(20, 20, 30, 30)
    command = CreateItemCommand(scene, other, "rectangle")
    view.command_manager.execute(command)
    assert view.command_manager.discard(command)
    tool.cancel()
    assert item.scene() is None
    assert window._project_manager.is_dirty


@pytest.mark.parametrize("mutation", ["add", "remove", "move"])
def test_direct_scene_write_during_annotation_keeps_dirty(window, mutation):
    scene = window.canvas_scene
    bed = RectangleItem(20, 20, 30, 30)
    scene.addItem(bed)
    window._project_manager.mark_clean()
    tool, item = _place(window)
    revision = scene.plan_revision
    if mutation == "add":
        scene.addItem(RectangleItem(100, 100, 30, 30))
    elif mutation == "remove":
        scene.removeItem(bed)
    else:
        bed.setPos(10, 10)
    assert scene.plan_revision > revision
    tool.cancel()
    assert item.scene() is None
    assert window._project_manager.is_dirty
