"""A6/A7: actual menu commands and shutdown survive responsibility extraction."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.agent_api.bridge import BridgeClosedError
from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    EllipseItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


@pytest.mark.parametrize("shape", ["rectangle", "circle", "ellipse", "polygon", "polyline"])
@pytest.mark.parametrize("rotation", [37, 215])
def test_each_shape_menu_duplicates_in_one_history_step(qtbot, monkeypatch, shape, rotation):
    scene = CanvasScene(width_cm=3000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    points = [QPointF(100, 100), QPointF(190, 100), QPointF(170, 170)]
    item = {
        "rectangle": lambda: RectangleItem(100, 100, 90, 70),
        "circle": lambda: CircleItem(150, 150, 30),
        "ellipse": lambda: EllipseItem(100, 100, 90, 70),
        "polygon": lambda: PolygonItem(points),
        "polyline": lambda: PolylineItem(points),
    }[shape]()
    scene.addItem(item)
    item._apply_rotation(rotation)
    item.setSelected(True)
    def choose(menu, _point):
        labels = [action.text() for action in menu.actions()]
        for label in ("Duplicate", "Create Linear Array...", "Create Grid Array...",
                      "Create Circular Array..."):
            assert labels.count(label) == 1
        return next(action for action in menu.actions() if action.text() == "Duplicate")
    monkeypatch.setattr(QMenu, "exec", choose)
    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    depth = view.command_manager.undo_depth
    item.contextMenuEvent(event)
    selected = scene.selectedItems()
    assert len(selected) == 1 and selected[0] is not item
    duplicate = selected[0]
    assert type(duplicate) is type(item)
    assert duplicate.rotation() == rotation
    assert view.command_manager.undo_depth == depth + 1
    view.command_manager.undo()
    assert duplicate.scene() is None and item.scene() is scene
    view.command_manager.redo()
    assert duplicate.scene() is scene


def test_host_shutdown_aborts_queued_call_before_join(qtbot, monkeypatch):
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    bridge = window._agent_bridge
    queued = threading.Event()
    outcome = []
    # This observer runs in the emitting worker, before the queued Qt slot.
    from PyQt6.QtCore import Qt
    bridge._invoke.connect(lambda *_: queued.set(), Qt.ConnectionType.DirectConnection)
    def worker():
        try:
            bridge.run_on_main(lambda: outcome.append("ran"))
        except BridgeClosedError:
            outcome.append("aborted")
    thread = threading.Thread(target=worker)
    thread.start()
    assert queued.wait(2), "the request reached the actual bridge"
    class Server:
        def stop(self):
            # No pumping of Qt: a join before abort would leave the worker waiting.
            thread.join(1)
            assert not thread.is_alive()
            assert outcome == ["aborted"]
    monkeypatch.setattr(window, "_agent_server", Server())
    window._stop_agent_api()
    assert window._agent_server is None
    qtbot.wait(1)
    assert outcome == ["aborted"], "the aborted queued callable must never run later"
