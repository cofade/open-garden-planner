"""Default-on containment (US-D1.1).

The Agent API server defaults to ON in production, so the test harness must keep
it disabled and the app's auto-start path must honour that — otherwise a full-app
test that pumps the event loop past the 1500 ms deferred start would bind a real
loopback port and hang. These tests are the positive proof that containment
holds (they fail loudly if the autouse guard regresses).
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings


@pytest.fixture(autouse=True)
def _no_welcome_dialog(_reset_app_settings: Any) -> None:
    """Suppress the deferred (singleShot 500 ms) modal Welcome dialog.

    These tests construct several GardenPlannerApp instances; if any lives long
    enough for the startup timer to fire while qtbot pumps events, the modal
    Welcome dialog blocks the run. Depends on the conftest reset so this write
    survives the per-test store clear.
    """
    get_settings().show_welcome_on_startup = False


def test_guard_keeps_agent_api_disabled_in_tests() -> None:
    # The autouse `_disable_agent_api_server` fixture must win over the new
    # default-ON, so no test ever binds 127.0.0.1:8765.
    assert get_settings().agent_api_enabled is False


def test_app_does_not_autostart_server_when_disabled(qtbot: Any) -> None:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    # Invoke the deferred auto-start path directly (no 1500 ms wait). With the
    # guard keeping the setting off, it must NOT construct or bind a server.
    win._maybe_start_agent_api()
    try:
        assert win._agent_server is None
    finally:
        win._stop_agent_api()  # defensive no-op when None


class _StubAgentServer:
    """Minimal stand-in for AgentApiServer — no real socket bound."""

    def __init__(
        self,
        *,
        is_running: bool,
        url: str = "http://127.0.0.1:8765/mcp",
        write_token: str | None = None,
    ) -> None:
        self.is_running = is_running
        self.url = url
        # Mirrors AgentApiServer.write_token: the token the *running* server
        # validates, which the app hands to clients (not the settings value).
        self.write_token = write_token


def test_agent_api_running_url_is_none_without_a_server(qtbot: Any) -> None:
    """US-D1.6: both the Help menu and Preferences 'Connect…' entry points
    derive their URL from this one method — pin it directly, not just
    through the fake-parent-window stand-ins used in the dialog-level tests."""
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        assert win._agent_server is None
        assert win.agent_api_running_url() is None
    finally:
        win._stop_agent_api()


def test_agent_api_running_url_reflects_is_running(qtbot: Any) -> None:
    """The exact bug US-D1.6 round 3 fixed: a *constructed* server that
    isn't actually running (e.g. it failed to bind) must still yield None,
    not its (dead) URL — is_running is the only source of truth."""
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        win._agent_server = _StubAgentServer(is_running=False)
        assert win.agent_api_running_url() is None

        win._agent_server = _StubAgentServer(is_running=True, url="http://127.0.0.1:9191/mcp")
        assert win.agent_api_running_url() == "http://127.0.0.1:9191/mcp"
    finally:
        win._agent_server = None
        win._stop_agent_api()


# ---------------------------------------------------------------------------
# US-D2.0: the app's own write-provider bodies + write-token accessor.
# The end-to-end server test (test_agent_api_writes.py) reimplements the write
# logic against a bare view; these pin GardenPlannerApp's actual delegation
# (_do_agent_move_object/_do_agent_delete_object/_resolve_agent_item), run
# directly on the main thread (no server, no networking, deterministic).
# ---------------------------------------------------------------------------


def _add_tree(win: GardenPlannerApp) -> Any:
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem

    item = CircleItem(300, 300, 20, object_type=ObjectType.TREE)
    win.canvas_scene.addItem(item)
    return item


def _discard_on_close(monkeypatch: Any) -> None:
    """Mutating a plan dirties it; qtbot's teardown close would then block on the
    unsaved-changes modal. Auto-answer Discard (mirrors test_tasks.py)."""
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *_a, **_k: QMessageBox.StandardButton.Discard,
    )


def test_do_agent_move_object_is_one_undoable_step(qtbot: Any, monkeypatch: Any) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        start = item.sceneBoundingRect().center()

        result = win._do_agent_move_object(str(item.item_id), 40.0, 10.0)

        moved = item.sceneBoundingRect().center()
        assert moved.x() == start.x() + 40.0
        assert moved.y() == start.y() + 10.0
        assert result["action"] == "move"
        assert result["x"] == moved.x() and result["y"] == moved.y()
        assert result["children_moved"] == 0
        assert result["bed_membership_changed"] is False
        # Invariants #3/#4/#13: one undo step, it dirties the document, and
        # it reverses cleanly.
        assert win._project_manager.is_dirty
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        back = item.sceneBoundingRect().center()
        assert back.x() == start.x() and back.y() == start.y()
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_bed_with_children_propagates_to_plants(qtbot: Any, monkeypatch: Any) -> None:
    """P0 regression: moving a bed must carry its contained plants along —
    mirroring CanvasView._propagate_bed_children_during_drag's release-time
    commit — not silently abandon them at their old position while
    child_item_ids still (falsely) claims they're inside the bed."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(100, 100, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)
        plant_a = CircleItem(200, 200, 20, object_type=ObjectType.TREE)
        plant_b = CircleItem(350, 250, 20, object_type=ObjectType.PERENNIAL)
        win.canvas_scene.addItem(plant_a)
        win.canvas_scene.addItem(plant_b)
        bed.add_child_id(plant_a.item_id)
        bed.add_child_id(plant_b.item_id)
        plant_a.parent_bed_id = bed.item_id
        plant_b.parent_bed_id = bed.item_id

        bed_start, a_start, b_start = bed.pos(), plant_a.pos(), plant_b.pos()

        result = win._do_agent_move_object(str(bed.item_id), 50.0, 30.0)

        assert result["children_moved"] == 2
        assert bed.pos() == bed_start + QPointF(50.0, 30.0)
        assert plant_a.pos() == a_start + QPointF(50.0, 30.0)
        assert plant_b.pos() == b_start + QPointF(50.0, 30.0)
        # One undo step restores the bed AND both plants together.
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert bed.pos() == bed_start
        assert plant_a.pos() == a_start
        assert plant_b.pos() == b_start
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_plant_into_bed_reconciles_parent(qtbot: Any, monkeypatch: Any) -> None:
    """P1 regression: moving a plant across a bed boundary must reparent it —
    mirroring CanvasView._update_plant_bed_relationships — otherwise
    plants_in_bed/soil-mismatch diagnostics never see the new membership."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)
        plant = CircleItem(50, 50, 20, object_type=ObjectType.TREE)
        win.canvas_scene.addItem(plant)
        assert plant.parent_bed_id is None

        # Move the plant's centre well inside the bed's interior (x:500-900, y:500-800).
        result = win._do_agent_move_object(str(plant.item_id), 620.0, 620.0)

        assert result["bed_membership_changed"] is True
        assert result["new_parent_bed_id"] == str(bed.item_id)
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        # Two undo steps: the reparent (executed second) undoes first, then the move.
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_plant_out_of_bed_detaches_parent(qtbot: Any, monkeypatch: Any) -> None:
    """Mirror of the above: moving a plant OUT of its bed must detach it, not
    leave a stale parent_bed_id/child_item_ids link the diagnostics act on."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)
        # Plant starts inside the bed and is already attached.
        plant = CircleItem(670, 620, 20, object_type=ObjectType.TREE)
        win.canvas_scene.addItem(plant)
        bed.add_child_id(plant.item_id)
        plant.parent_bed_id = bed.item_id

        # Move it far outside the bed.
        result = win._do_agent_move_object(str(plant.item_id), -1000.0, -1000.0)

        assert result["bed_membership_changed"] is True
        assert result["new_parent_bed_id"] is None
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
    finally:
        win._stop_agent_api()


def _add_distance_constraint(win: GardenPlannerApp, item: Any, other_id: Any) -> None:
    """Attach a plain distance constraint between ``item`` and an arbitrary
    other UUID — mirrors the graph shape CanvasView's drag-release solver
    checks for, without needing a second real scene item."""
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    graph = win.canvas_scene.constraint_graph
    graph.add_constraint(
        AnchorRef(item.item_id, AnchorType.CENTER),
        AnchorRef(other_id, AnchorType.CENTER),
        100.0,
    )


def test_move_object_refuses_when_item_has_constraint(qtbot: Any, monkeypatch: Any) -> None:
    """Replicating CanvasView's live constraint solver for a one-shot agent
    move is out of scope for this tool — a constrained item must be refused,
    not silently moved while its constraint goes unsatisfied."""
    from uuid import uuid4

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        _add_distance_constraint(win, item, uuid4())
        start = item.pos()

        with pytest.raises(ValueError, match="constraint"):
            win._do_agent_move_object(str(item.item_id), 40.0, 10.0)

        assert item.pos() == start
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_object_refuses_when_bed_child_has_constraint(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The constraint check must cover propagated bed children too, not just
    the primary item being moved."""
    from uuid import uuid4

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem, RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(100, 100, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)
        plant = CircleItem(200, 200, 20, object_type=ObjectType.TREE)
        win.canvas_scene.addItem(plant)
        bed.add_child_id(plant.item_id)
        plant.parent_bed_id = bed.item_id
        _add_distance_constraint(win, plant, uuid4())

        with pytest.raises(ValueError, match="constraint"):
            win._do_agent_move_object(str(bed.item_id), 50.0, 30.0)

        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_delete_object_removes_constraints_referencing_item(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Mirrors CanvasView._delete_selected_items: a dangling constraint
    referencing a deleted item's UUID must not survive the delete."""
    from uuid import uuid4

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        _add_distance_constraint(win, item, uuid4())
        graph = win.canvas_scene.constraint_graph
        assert graph.get_item_constraints(item.item_id)

        result = win._do_agent_delete_object(str(item.item_id))

        assert graph.get_item_constraints(item.item_id) == []
        assert result["constraints_removed"] == 1
    finally:
        win._stop_agent_api()


def test_delete_object_deletes_linked_roof_ridge(qtbot: Any, monkeypatch: Any) -> None:
    """Mirrors CanvasView._delete_selected_items's ridge_item_id expansion:
    deleting a HOUSE must also delete its linked roof ridge, not orphan it."""
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        house = PolygonItem(
            [QPointF(0, 0), QPointF(500, 0), QPointF(500, 400), QPointF(0, 400)],
            object_type=ObjectType.HOUSE,
        )
        win.canvas_scene.addItem(house)
        ridge = PolylineItem(
            [QPointF(0, 200), QPointF(500, 200)], object_type=ObjectType.ROOF_RIDGE
        )
        win.canvas_scene.addItem(ridge)
        house.metadata["ridge_item_id"] = str(ridge.item_id)
        ridge_id = ridge.item_id

        result = win._do_agent_delete_object(str(house.item_id))

        assert win.canvas_scene.find_item_by_id(house.item_id) is None
        assert win.canvas_scene.find_item_by_id(ridge_id) is None
        assert result["linked_items_deleted"] == 1
        # One undo step restores both together.
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert win.canvas_scene.find_item_by_id(house.item_id) is not None
        assert win.canvas_scene.find_item_by_id(ridge_id) is not None
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_and_delete_reject_journal_pin(qtbot: Any, monkeypatch: Any) -> None:
    """Journal pins have a ProjectData-linked delete path (pruning the note
    dict) that DeleteItemsCommand alone doesn't replicate — must be refused,
    not silently mishandled."""
    from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        pin = JournalPinItem(100, 100, note_id="note-1")
        win.canvas_scene.addItem(pin)

        with pytest.raises(ValueError, match="journal pin"):
            win._do_agent_move_object(str(pin.item_id), 10.0, 10.0)
        with pytest.raises(ValueError, match="journal pin"):
            win._do_agent_delete_object(str(pin.item_id))

        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_move_and_delete_refuse_locked_layer_item(qtbot: Any, monkeypatch: Any) -> None:
    """The GUI enforces layer-lock by clearing ItemIsSelectable/ItemIsMovable,
    so a locked-layer item can't be moved or deleted at all. The agent resolves
    by UUID (bypassing selection), so it must honour the lock explicitly — a
    user who locked a layer to protect it expects nothing, agent included, to
    edit it."""
    from open_garden_planner.models.layer import Layer

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        locked = Layer(name="Locked", locked=True)
        win.canvas_scene.add_layer(locked)
        item = _add_tree(win)
        item.layer_id = locked.id
        start = item.pos()

        with pytest.raises(ValueError, match="locked layer"):
            win._do_agent_move_object(str(item.item_id), 40.0, 10.0)
        with pytest.raises(ValueError, match="locked layer"):
            win._do_agent_delete_object(str(item.item_id))

        assert item.pos() == start
        assert win.canvas_scene.find_item_by_id(item.item_id) is not None
        assert win.canvas_view.command_manager.can_undo is False

        # Unlocking makes it editable again.
        locked.locked = False
        result = win._do_agent_move_object(str(item.item_id), 40.0, 10.0)
        assert result["action"] == "move"
        assert item.pos() == start + QPointF(40.0, 10.0)
    finally:
        win._stop_agent_api()


def test_move_and_delete_refuse_group_member(qtbot: Any, monkeypatch: Any) -> None:
    """A group member isn't a top-level object (only a raw snapshot exposes its
    id, nested in the group). The GUI never lets you move/delete a lone member —
    you address the group. moveBy on a QGraphicsItemGroup child would displace it
    within the group, so the agent must refuse and point at the group id."""
    from open_garden_planner.core.commands import GroupCommand
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import CircleItem
    from open_garden_planner.ui.canvas.items.group_item import GroupItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        a = CircleItem(100, 100, 20, object_type=ObjectType.TREE)
        b = CircleItem(300, 100, 20, object_type=ObjectType.TREE)
        win.canvas_scene.addItem(a)
        win.canvas_scene.addItem(b)
        win.canvas_view.command_manager.execute(GroupCommand(win.canvas_scene, [a, b]))
        group = a.parentItem()
        assert isinstance(group, GroupItem)

        # A lone member is refused, pointing at the group.
        with pytest.raises(ValueError, match="member of a group"):
            win._do_agent_move_object(str(a.item_id), 40.0, 10.0)
        with pytest.raises(ValueError, match="member of a group"):
            win._do_agent_delete_object(str(a.item_id))

        # The group itself moves fine — Qt cascades to members natively.
        group_start = group.pos()
        result = win._do_agent_move_object(str(group.item_id), 40.0, 10.0)
        assert result["action"] == "move"
        assert group.pos() == group_start + QPointF(40.0, 10.0)
    finally:
        win._stop_agent_api()


def test_move_returned_center_matches_read_layer_with_badge(
    qtbot: Any, monkeypatch: Any
) -> None:
    """P2-1: the returned x/y must equal what get_object reports (the serialised
    geometry centre), not sceneBoundingRect().center() — which diverges for a
    plant showing the runtime-only antagonist badge (asymmetric boundingRect)."""
    from open_garden_planner.agent_api import queries

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        # Turn on the antagonist badge so boundingRect() is expanded asymmetrically.
        item.set_antagonist_warning(True)
        bbox_center = item.sceneBoundingRect().center()
        read_center = queries.object_center(win._project_manager._serialize_item(item))
        # Precondition: with the badge, the two centres genuinely disagree.
        assert (bbox_center.x(), bbox_center.y()) != read_center

        result = win._do_agent_move_object(str(item.item_id), 0.0, 0.0)

        # The tool reports the read-layer centre, not the bbox centre.
        expected = queries.object_center(win._project_manager._serialize_item(item))
        assert (result["x"], result["y"]) == expected
    finally:
        win._stop_agent_api()


def test_do_agent_delete_object_is_one_undoable_step(qtbot: Any, monkeypatch: Any) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        item = _add_tree(win)
        item_id = item.item_id

        result = win._do_agent_delete_object(str(item_id))

        assert result["action"] == "delete"
        assert win.canvas_scene.find_item_by_id(item_id) is None
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert win.canvas_scene.find_item_by_id(item_id) is not None
    finally:
        win._stop_agent_api()


def test_resolve_agent_item_raises_on_unknown_or_bad_id(qtbot: Any) -> None:
    import pytest

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        with pytest.raises(ValueError):
            win._resolve_agent_item("not-a-uuid")
        with pytest.raises(ValueError):
            win._resolve_agent_item("00000000-0000-0000-0000-000000000000")
    finally:
        win._stop_agent_api()


def test_agent_api_write_token_derives_from_running_server(qtbot: Any) -> None:
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        # No running server -> None.
        assert win._agent_server is None
        assert win.agent_api_write_token() is None

        # Running server with a write token -> that token.
        win._agent_server = _StubAgentServer(is_running=True, write_token="live-token")
        assert win.agent_api_write_token() == "live-token"

        # Running server with writes off (write_token None) -> None.
        win._agent_server = _StubAgentServer(is_running=True, write_token=None)
        assert win.agent_api_write_token() is None

        # Constructed but not running -> None even with a token.
        win._agent_server = _StubAgentServer(is_running=False, write_token="live-token")
        assert win.agent_api_write_token() is None
    finally:
        win._agent_server = None
        win._stop_agent_api()


def test_agent_api_write_token_ignores_settings_regenerated_without_restart(
    qtbot: Any,
) -> None:
    """P2-2: regenerating the token in Preferences persists a new settings value
    but does NOT restart the server. The client must be handed the token the
    live server still validates — the running server's, not settings'."""
    from open_garden_planner.app.settings import get_settings

    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        settings = get_settings()
        # Server is running with the token it was started with.
        win._agent_server = _StubAgentServer(is_running=True, write_token="original")
        # User regenerates in Preferences (settings changes, no restart yet).
        new_settings_token = settings.regenerate_agent_api_token()
        assert new_settings_token != "original"
        # The handed-out token stays the one the live server accepts.
        assert win.agent_api_write_token() == "original"
    finally:
        win._agent_server = None
        win._stop_agent_api()
