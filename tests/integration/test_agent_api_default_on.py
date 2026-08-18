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


# --- US-D2.1: create_object orchestration ---------------------------------
#
# These pin what create_object must mirror from the GUI's own gallery-drop path
# (CanvasView drop handler): species auto-populate, the US-E8 planting-date
# stamp, and active-layer assignment.
#
# Bed membership is NOT reconciled here: CreateItemCommand.execute already calls
# _auto_parent_plant (and undo calls _detach_from_parent), so the link is part of
# the single create step. That is the opposite of move_object, whose
# MoveItemsCommand has no such hook and must reconcile explicitly.


def test_do_agent_create_object_is_one_undoable_step(
    qtbot: Any, monkeypatch: Any
) -> None:
    from uuid import UUID

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        before = len(win.canvas_scene.items())

        result = win._do_agent_create_object(
            "TREE", 300.0, 400.0, None, None, None, None, None
        )

        assert result["action"] == "create"
        assert result["bed_membership_changed"] is False
        item = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert item is not None
        assert len(win.canvas_scene.items()) > before

        # Exactly ONE undo step removes it again (invariants #3/#4/#13).
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert win.canvas_scene.find_item_by_id(UUID(result["item_id"])) is None
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_created_plant_gets_todays_planting_date(qtbot: Any, monkeypatch: Any) -> None:
    """US-E8: EVERY new plant is dated at creation, species or not -- the date
    drives the growth model, and therefore the shadow/heatmap/3D views. The GUI
    stamps it deliberately outside its species guard; so must this."""
    from datetime import date
    from typing import Any as _Any
    from uuid import UUID

    from open_garden_planner.core.growth_model import (
        planting_date_from_metadata,
        stamp_default_planting_date,
    )

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        # No species -- the stamp must still happen.
        result = win._do_agent_create_object(
            "PERENNIAL", 100.0, 100.0, None, None, None, None, None
        )
        item = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert item is not None

        # Compare against what the SAME stamping function writes, rather than
        # hardcoding the metadata schema here (it would drift silently).
        reference: dict[str, _Any] = {}
        stamp_default_planting_date(reference, date.today())
        assert reference, "stamp_default_planting_date wrote nothing -- test is vacuous"
        assert item.metadata == reference

        # Close the loop: the growth model's own READER must see it. Comparing
        # writer-to-writer alone would still agree after a key rename inside
        # plant_instance, and the growth/shadow/heatmap/3D views would silently
        # stop engaging for new plants.
        assert planting_date_from_metadata(item.metadata) == date.today()
    finally:
        win._stop_agent_api()


def test_create_plant_inside_bed_links_it_to_the_bed(
    qtbot: Any, monkeypatch: Any
) -> None:
    """A plant created inside a bed is linked to it, and the link rides INSIDE
    the single create step (CreateItemCommand._auto_parent_plant) -- one undo
    both removes the plant and detaches it. An unlinked plant would leave
    exactly the stale parent/child state soil-mismatch diagnostics act on."""
    from uuid import UUID

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)

        # Centre well inside the bed's interior (x:500-900, y:500-800).
        result = win._do_agent_create_object(
            "PERENNIAL", 700.0, 650.0, None, None, 20.0, None, None
        )

        assert result["new_parent_bed_id"] == str(bed.item_id)
        # No SECOND undo step was created -- the link is part of the create.
        assert result["bed_membership_changed"] is False
        plant = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert plant is not None
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids

        # Exactly ONE undo step: it removes the plant AND detaches the link
        # (invariant #4 -- one agent write, one Ctrl+Z).
        win.canvas_view.command_manager.undo()
        assert win.canvas_scene.find_item_by_id(UUID(result["item_id"])) is None
        assert plant.item_id not in bed.child_item_ids
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_create_plant_outside_any_bed_stays_unlinked(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Control for the test above: no bed under it, so no second undo step."""
    from uuid import UUID

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = RectangleItem(500, 500, 400, 300, object_type=ObjectType.RAISED_BED)
        win.canvas_scene.addItem(bed)

        result = win._do_agent_create_object(
            "PERENNIAL", 50.0, 50.0, None, None, 20.0, None, None
        )

        assert result["new_parent_bed_id"] is None
        assert result["bed_membership_changed"] is False
        plant = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert plant is not None and plant.parent_bed_id is None
        win.canvas_view.command_manager.undo()
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_created_object_centre_matches_what_the_read_layer_reports(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The API speaks CENTRES in both directions: the x/y you pass in must be
    the x/y a follow-up read reports back, for round AND rectangular types.
    This is what pins the centre->anchor conversion end to end."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        tree = win._do_agent_create_object(
            "TREE", 321.0, 654.0, None, None, 40.0, None, None
        )
        assert tree["x"] == pytest.approx(321.0)
        assert tree["y"] == pytest.approx(654.0)

        bed = win._do_agent_create_object(
            "GARDEN_BED", 1000.0, 2000.0, 250.0, 120.0, None, None, None
        )
        assert bed["x"] == pytest.approx(1000.0)
        assert bed["y"] == pytest.approx(2000.0)
    finally:
        win._stop_agent_api()


def test_created_object_lands_on_the_active_layer(qtbot: Any, monkeypatch: Any) -> None:
    from uuid import UUID

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        active = win.canvas_scene.active_layer
        assert active is not None, "fixture precondition: a layer is active"

        result = win._do_agent_create_object(
            "CONTAINER", 10.0, 10.0, 50.0, 40.0, None, None, None
        )
        item = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert item is not None
        assert item.layer_id == active.id
    finally:
        win._stop_agent_api()


def test_create_refuses_a_locked_active_layer(qtbot: Any, monkeypatch: Any) -> None:
    """The GUI can't draw onto a locked layer either (it clears the item flags).
    The agent bypasses selection entirely, so the lock is honoured explicitly --
    the same rule _resolve_agent_item enforces for move/delete."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    # Bound OUTSIDE the try: a failed assertion inside it would otherwise make
    # the finally clause raise AttributeError and mask the real failure.
    active = win.canvas_scene.active_layer
    assert active is not None, "fixture precondition: a layer is active"
    try:
        active.locked = True
        before = len(win.canvas_scene.items())

        with pytest.raises(ValueError, match="locked"):
            win._do_agent_create_object(
                "TREE", 10.0, 10.0, None, None, None, None, None
            )

        # Refused means nothing was created and nothing is undoable.
        assert len(win.canvas_scene.items()) == before
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        active.locked = False
        win._stop_agent_api()


def test_create_refuses_an_unsupported_type_without_touching_the_scene(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        before = len(win.canvas_scene.items())
        with pytest.raises(ValueError, match="cannot create"):
            win._do_agent_create_object(
                "HOUSE", 10.0, 10.0, 50.0, 50.0, None, None, None
            )
        assert len(win.canvas_scene.items()) == before
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_create_through_the_bridge_wrapper_keeps_arguments_in_order(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Exercise `_agent_create_object` -- the main-thread bridge wrapper the
    server actually calls -- rather than only `_do_agent_create_object`.

    Six of its eight parameters are `float | None` / `str | None`, so a
    width/height transposition anywhere along server -> provider -> wrapper is
    type-identical and would silently yield a 120x250 bed for a 250x120 request.
    Deliberately uses width != height so a swap cannot pass.
    """
    from uuid import UUID

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        result = win._agent_create_object(
            object_type="GARDEN_BED",
            x=400.0,
            y=300.0,
            width=250.0,
            height=120.0,
            radius=None,
            name="Long Bed",
            species=None,
        )
        item = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert item is not None
        assert item.rect().width() == 250.0
        assert item.rect().height() == 120.0
        assert item.name == "Long Bed"
    finally:
        win._stop_agent_api()


def test_create_refuses_species_on_a_non_plant(qtbot: Any, monkeypatch: Any) -> None:
    """The one silent-ignore an otherwise loud tool would have had: a bed
    quietly dropping the species it was handed."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        before = len(win.canvas_scene.items())
        with pytest.raises(ValueError, match="not a plant"):
            win._do_agent_create_object(
                "RAISED_BED", 100.0, 100.0, 200.0, 100.0, None, None, "Tomato"
            )
        assert len(win.canvas_scene.items()) == before
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_create_refuses_an_absurd_plant_size(qtbot: Any, monkeypatch: Any) -> None:
    """radius=10000 (a 100 m tree) is the shape of a metres-for-centimetres
    slip. Unbounded, it reaches render_plant_pixmap's quadratic QImage on the
    Qt main thread (~2.3 GB / ~3 s measured at diameter 24000)."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        before = len(win.canvas_scene.items())
        with pytest.raises(ValueError, match="CENTIMETRES"):
            win._do_agent_create_object(
                "TREE", 100.0, 100.0, None, None, 10000.0, None, None
            )
        assert len(win.canvas_scene.items()) == before
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_created_plant_with_known_species_is_auto_populated(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Mirrors the drop path's populate_item_species_metadata call, so the plant
    detail panel and US-12.10d soil-mismatch warnings light up without the user
    having to click \"Suchen\"."""
    from uuid import UUID

    from open_garden_planner.services.bundled_species_db import lookup_species

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        # Pick the species straight from the bundled DB so the test can't drift
        # from whatever that database actually contains.
        if lookup_species("Tomato") is None:
            pytest.skip("bundled species DB has no 'Tomato' record to exercise")

        result = win._do_agent_create_object(
            "PERENNIAL", 10.0, 10.0, None, None, None, None, "Tomato"
        )
        item = win.canvas_scene.find_item_by_id(UUID(result["item_id"]))
        assert item is not None
        assert item.plant_species == "Tomato"
        # populate_item_species_metadata filled the species block, not left it empty.
        assert item.metadata.get("plant_species")
    finally:
        win._stop_agent_api()


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


# ---------------------------------------------------------------------------
# US-D2.2: resize_object / rotate_object orchestration
#
# These pin what the tools must do against the REAL app: centre preservation
# for every shape, the measured rotation sign, exactly one undo step each, and
# every refusal leaving BOTH the scene and the undo stack untouched.
# ---------------------------------------------------------------------------


def _add_bed(
    win: GardenPlannerApp,
    x: float = 500,
    y: float = 500,
    w: float = 400,
    h: float = 300,
) -> Any:
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import RectangleItem

    bed = RectangleItem(x, y, w, h, object_type=ObjectType.RAISED_BED)
    win.canvas_scene.addItem(bed)
    return bed


def _scene_centre(item: Any) -> Any:
    return item.mapToScene(item.rect().center())


def test_resize_object_preserves_the_centre_and_is_one_undo_step(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The contract the tool's docstring makes: absolute target dimensions, and
    the object's centre does not move. An agent reads x/y, resizes, and the
    coordinates it already holds are still correct."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        before = _scene_centre(bed)

        result = win._do_agent_resize_object(str(bed.item_id), 600.0, 450.0, None)

        assert result["action"] == "resize"
        assert result["width"] == pytest.approx(600.0)
        assert result["height"] == pytest.approx(450.0)
        assert result["radius"] is None
        assert bed.rect().width() == pytest.approx(600.0)
        assert bed.rect().height() == pytest.approx(450.0)
        after = _scene_centre(bed)
        assert after.x() == pytest.approx(before.x())
        assert after.y() == pytest.approx(before.y())
        # The reported centre is the one the READ tools report (same source).
        assert result["x"] == pytest.approx(after.x())
        assert result["y"] == pytest.approx(after.y())

        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert bed.rect().width() == pytest.approx(400.0)
        assert bed.rect().height() == pytest.approx(300.0)
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_resize_object_one_axis_leaves_the_other_alone(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        result = win._do_agent_resize_object(str(bed.item_id), 600.0, None, None)
        assert bed.rect().width() == pytest.approx(600.0)
        assert bed.rect().height() == pytest.approx(300.0)
        assert result["height"] == pytest.approx(300.0)
    finally:
        win._stop_agent_api()


def test_resize_plant_keeps_its_bed_membership(qtbot: Any, monkeypatch: Any) -> None:
    """Resizing is not moving: a plant's parent link must survive it. A resize
    that silently reparented would corrupt the bed's capacity diagnostics."""
    from uuid import UUID

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        created = win._do_agent_create_object(
            "PERENNIAL", 700.0, 650.0, None, None, 20.0, None, None
        )
        plant = win.canvas_scene.find_item_by_id(UUID(created["item_id"]))
        assert plant.parent_bed_id == bed.item_id

        result = win._do_agent_resize_object(created["item_id"], None, None, 45.0)

        assert result["radius"] == pytest.approx(45.0)
        assert result["width"] is None and result["height"] is None
        assert plant.radius == pytest.approx(45.0)
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
    finally:
        win._stop_agent_api()


def test_resize_object_refuses_a_vertex_backed_object(
    qtbot: Any, monkeypatch: Any
) -> None:
    """A polygon has no width/height box. Refuse by name -- a silent no-op would
    leave the agent believing it resized something."""
    from PyQt6.QtCore import QPointF as _QPointF

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import PolygonItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        polygon = PolygonItem(
            [_QPointF(0, 0), _QPointF(200, 0), _QPointF(100, 150)],
            object_type=ObjectType.GARDEN_BED,
        )
        win.canvas_scene.addItem(polygon)
        with pytest.raises(ValueError, match="vertices"):
            win._do_agent_resize_object(str(polygon.item_id), 300.0, 300.0, None)
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_resize_and_rotate_refuse_a_constrained_object(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Same rule move_object already enforces: the live constraint solver has no
    one-shot equivalent, so editing a constrained object would silently violate
    the constraint. Refusing is the honest answer until US-D2.6."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        other = _add_bed(win, x=1500, y=1500)
        _add_distance_constraint(win, bed, other.item_id)
        before_rect = bed.rect()

        with pytest.raises(ValueError, match="geometric constraint"):
            win._do_agent_resize_object(str(bed.item_id), 600.0, 450.0, None)
        with pytest.raises(ValueError, match="geometric constraint"):
            win._do_agent_rotate_object(str(bed.item_id), 90.0, False)

        assert bed.rect() == before_rect
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_resize_refusals_leave_scene_and_undo_stack_untouched(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Every refusal path, asserted rather than assumed: a tool that
    half-applies and then raises passes a happy-path test perfectly."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        item_id = str(bed.item_id)
        before_rect = bed.rect()
        before_pos = bed.pos()

        for kwargs in (
            {"width": 0.0, "height": None, "radius": None},
            {"width": -5.0, "height": None, "radius": None},
            {"width": float("nan"), "height": None, "radius": None},
            {"width": None, "height": None, "radius": 50.0},  # radius on a rect
            {"width": None, "height": None, "radius": None},  # nothing at all
            {"width": 1_000_000.0, "height": None, "radius": None},  # absurd
        ):
            with pytest.raises(ValueError):
                win._do_agent_resize_object(item_id, **kwargs)

        assert bed.rect() == before_rect
        assert bed.pos() == before_pos
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_rotate_object_absolute_vs_relative(qtbot: Any, monkeypatch: Any) -> None:
    """Absolute is idempotent, relative accumulates -- the distinction an agent
    has to be able to rely on to correct an angle without compounding it."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        item_id = str(bed.item_id)

        win._do_agent_rotate_object(item_id, 90.0, False)
        result = win._do_agent_rotate_object(item_id, 90.0, False)
        assert result["rotation_deg"] == pytest.approx(90.0)
        assert bed.rotation_angle == pytest.approx(90.0)

        result = win._do_agent_rotate_object(item_id, 90.0, True)
        assert result["rotation_deg"] == pytest.approx(180.0)
        assert bed.rotation_angle == pytest.approx(180.0)
    finally:
        win._stop_agent_api()


def test_rotate_object_direction_is_counter_clockwise(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Asserted against a measured CORNER POSITION, not the stored angle: the
    angle tells you nothing about which way it turned, and "which way" is the
    promise the tool's docstring makes. Issue #267 is what happens when a
    docstring states a frame the code does not honour."""
    from PyQt6.QtCore import QPointF as _QPointF

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win, x=1000, y=1000, w=400, h=80)  # long axis points EAST
        rect = bed.rect()
        east_tip = _QPointF(rect.x() + rect.width(), rect.y() + rect.height() / 2)
        centre_before = _scene_centre(bed)
        assert bed.mapToScene(east_tip).x() > centre_before.x()

        win._do_agent_rotate_object(str(bed.item_id), 90.0, False)

        after = bed.mapToScene(east_tip)
        centre_after = _scene_centre(bed)
        # CAD Y-up (ADR-002): a larger y is further NORTH.
        assert after.y() > centre_after.y() + 1.0, (
            "+90 must turn an east-pointing object NORTH (counter-clockwise) -- "
            "the rotate_object docstring says so in exactly those words"
        )
    finally:
        win._stop_agent_api()


def test_rotate_object_is_one_undo_step_and_restores_the_angle(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        win._do_agent_rotate_object(str(bed.item_id), 37.0, False)
        assert bed.rotation_angle == pytest.approx(37.0)
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert bed.rotation_angle == pytest.approx(0.0)
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_rotate_object_refuses_a_non_finite_angle(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        with pytest.raises(ValueError, match="finite"):
            win._do_agent_rotate_object(str(bed.item_id), float("inf"), False)
        assert bed.rotation_angle == pytest.approx(0.0)
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_resize_and_rotate_refuse_locked_layer_item(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The shared _resolve_agent_item chokepoint must apply to the new tools
    too -- this is the test that fails if a future tool resolves items itself."""
    from open_garden_planner.models.layer import Layer

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        locked = Layer(name="Locked", locked=True)
        win.canvas_scene.add_layer(locked)
        bed = _add_bed(win)
        bed.layer_id = locked.id

        with pytest.raises(ValueError, match="locked layer"):
            win._do_agent_resize_object(str(bed.item_id), 600.0, 450.0, None)
        with pytest.raises(ValueError, match="locked layer"):
            win._do_agent_rotate_object(str(bed.item_id), 90.0, False)
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


# ---------------------------------------------------------------------------
# US-D2.3: set_species / set_parent_bed orchestration
# ---------------------------------------------------------------------------


def test_set_species_populates_a_hand_drawn_plant(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The gap this closes: a plant the user drew by hand has no species, so
    none of the species-driven features apply to it. Assigning one must go
    through the SAME helper the plant panel and species search use (#213)."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        plant = _add_tree(win)
        result = win._do_agent_set_species(str(plant.item_id), "Tomato", True)

        assert result["action"] == "set_species"
        assert result["species_key"]
        assert plant.metadata.get("plant_species")
        assert win.canvas_view.command_manager.can_undo
        win.canvas_view.command_manager.undo()
        assert plant.metadata.get("plant_species") is None
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_set_species_adopts_the_database_footprint(
    qtbot: Any, monkeypatch: Any
) -> None:
    """As in the app: the drawn footprint takes the species' real mature size.
    This is the visible half of issue #213's design, and it must not differ
    between the GUI and the agent."""
    from open_garden_planner.core.plant_sizing import db_spacing_radius_cm
    from open_garden_planner.services.bundled_species_db import (
        lookup_species,
        merge_calendar_data,
    )

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        plant = _add_tree(win)
        before_radius = plant.radius
        expected = db_spacing_radius_cm(
            merge_calendar_data(dict(lookup_species("Tomato")))
        )
        assert expected is not None and expected != before_radius

        win._do_agent_set_species(str(plant.item_id), "Tomato", True)
        assert plant.radius == pytest.approx(expected)

        win.canvas_view.command_manager.undo()
        assert plant.radius == pytest.approx(before_radius)
    finally:
        win._stop_agent_api()


def test_set_species_none_clears_it(qtbot: Any, monkeypatch: Any) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        plant = _add_tree(win)
        win._do_agent_set_species(str(plant.item_id), "Tomato", True)
        result = win._do_agent_set_species(str(plant.item_id), None, True)

        assert result["species_key"] is None
        assert plant.metadata.get("plant_species") is None
        # Still exactly one undo step for the clear.
        win.canvas_view.command_manager.undo()
        assert plant.metadata.get("plant_species") is not None
    finally:
        win._stop_agent_api()


def test_set_species_refuses_an_unknown_name_and_a_non_plant(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        plant = _add_tree(win)
        bed = _add_bed(win)

        with pytest.raises(ValueError, match="bundled database"):
            win._do_agent_set_species(str(plant.item_id), "Nonexistent Plant", True)
        with pytest.raises(ValueError, match="not a"):
            win._do_agent_set_species(str(bed.item_id), "Tomato", True)

        assert plant.metadata.get("plant_species") is None
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_set_parent_bed_links_a_plant_already_sitting_inside_a_bed(
    qtbot: Any, monkeypatch: Any
) -> None:
    """The exact state move_object cannot reach: the plant is already inside the
    bed geometrically, so no move crosses a boundary, yet it is unlinked."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        plant = _add_tree(win)
        plant.setPos(700 - plant.rect().center().x(), 650 - plant.rect().center().y())
        assert plant.parent_bed_id is None

        result = win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))

        assert result["action"] == "set_parent_bed"
        assert result["bed_membership_changed"] is True
        assert result["new_parent_bed_id"] == str(bed.item_id)
        assert result["link_is_geometric"] is True
        assert plant.parent_bed_id == bed.item_id
        assert plant.item_id in bed.child_item_ids
        assert plant.zValue() > bed.zValue()

        win.canvas_view.command_manager.undo()
        assert plant.parent_bed_id is None
        assert plant.item_id not in bed.child_item_ids
        assert win.canvas_view.command_manager.can_undo is False
    finally:
        win._stop_agent_api()


def test_set_parent_bed_does_not_move_the_plant(
    qtbot: Any, monkeypatch: Any
) -> None:
    """A link change only -- the whole point of having this tool separate from
    move_object."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        plant = _add_tree(win)
        before = plant.pos()
        win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        assert plant.pos() == before
    finally:
        win._stop_agent_api()


def test_set_parent_bed_reports_a_non_geometric_link(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Linking a plant that sits OUTSIDE the bed is deliberately allowed (the
    app's own Link action allows it), but the result says so."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        plant = _add_tree(win)  # at (300, 300), well outside the bed
        result = win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        assert result["link_is_geometric"] is False
        assert plant.parent_bed_id == bed.item_id
    finally:
        win._stop_agent_api()


def test_set_parent_bed_detaches_and_restores_the_original_z(
    qtbot: Any, monkeypatch: Any
) -> None:
    """SetParentBedCommand snapshots zValue so undo restores the USER's z, not
    a recomputed one -- pinned here because the agent is now a caller of it."""
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        plant = _add_tree(win)
        plant.setZValue(42.0)

        win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        result = win._do_agent_set_parent_bed(str(plant.item_id), None)

        assert result["new_parent_bed_id"] is None
        assert result["link_is_geometric"] is None
        assert plant.parent_bed_id is None
        assert plant.zValue() == pytest.approx(42.0)
    finally:
        win._stop_agent_api()


def test_set_parent_bed_accepts_a_trellis_but_refuses_a_house(
    qtbot: Any, monkeypatch: Any
) -> None:
    """Section 8.14 / ADR-017: TRELLIS is a plant parent but not a soil
    container. A HOUSE is neither, and must be refused by name."""
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items import RectangleItem

    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        trellis = RectangleItem(2000, 2000, 200, 40, object_type=ObjectType.TRELLIS)
        house = RectangleItem(3000, 3000, 500, 400, object_type=ObjectType.HOUSE)
        win.canvas_scene.addItem(trellis)
        win.canvas_scene.addItem(house)
        plant = _add_tree(win)

        result = win._do_agent_set_parent_bed(
            str(plant.item_id), str(trellis.item_id)
        )
        assert result["new_parent_bed_id"] == str(trellis.item_id)

        with pytest.raises(ValueError, match="HOUSE"):
            win._do_agent_set_parent_bed(str(plant.item_id), str(house.item_id))
        assert plant.parent_bed_id == trellis.item_id
    finally:
        win._stop_agent_api()


def test_set_parent_bed_refuses_a_no_op_and_a_non_plant(
    qtbot: Any, monkeypatch: Any
) -> None:
    _discard_on_close(monkeypatch)
    win = GardenPlannerApp()
    qtbot.addWidget(win)
    try:
        bed = _add_bed(win)
        plant = _add_tree(win)

        with pytest.raises(ValueError, match="already unlinked"):
            win._do_agent_set_parent_bed(str(plant.item_id), None)
        win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        with pytest.raises(ValueError, match="already linked"):
            win._do_agent_set_parent_bed(str(plant.item_id), str(bed.item_id))
        with pytest.raises(ValueError, match="not a"):
            win._do_agent_set_parent_bed(str(bed.item_id), str(bed.item_id))
    finally:
        win._stop_agent_api()
