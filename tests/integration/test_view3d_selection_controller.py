"""The selection through the sync controller (Phase 17 L1.8, gate G3, ADR-060).

``Scene3DController.set_selection(ids)`` is the one place the workspace tells the
pipeline what is selected. On a real canvas and a ``RecordingSink``, with the
controller called directly (the canvas's own selection signal and its repaint are
the workspace's: ``test_view3d_selection_workspace.py``):

- hidden: a flag, no snapshot, no sink call — and the ring with the catch-up pass;
- shown: ONE transaction that holds ``set_selection`` and no model call, and — when
  nothing else changed — NO snapshot (the plan did not change);
- a selected item that moves: the ring in the transaction of the move;
- a sink that fails on the ring is recovered like any other failure.
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.commands import DeleteItemsCommand, MoveItemsCommand
from open_garden_planner.core.scene3d import RecordingSink
from open_garden_planner.core.scene3d.selection import EMPTY_SELECTION, Selection, selection_of
from tests.integration.test_view3d_sync_controller import BEGIN, COMMIT, GROUND, SUN, Rig

SELECT = ("set_selection", None)
MODEL_CALLS = {"add", "remove", "replace_geometry", "update_transform", "update_material"}


@pytest.fixture()
def rig(canvas, qtbot) -> Rig:
    return Rig(canvas, qtbot)


def shown(rig: Rig) -> tuple[Any, Any]:
    a, b = rig.bed(), rig.bed(1500.0, 300.0)
    rig.controller.set_active(True)
    rig.settle()
    return a, b


def ids(*items: Any) -> tuple[str, ...]:
    return tuple(sorted(str(item.item_id) for item in items))


def test_a_selection_is_one_transaction_with_no_model_call_and_no_snapshot(rig: Rig) -> None:
    """Gate G3: select, add, remove, clear — each is ``[begin, set_selection, commit]``;
    the plan was not read again (it did not change) and no builder ran."""
    a, b = shown(rig)
    controller = rig.controller
    before = (controller.snapshot_count, controller.apply_count, controller.sync.build_count)
    for count, wanted in enumerate(([a], [a, b], [b], []), start=1):
        controller.set_selection(str(item.item_id) for item in wanted)
        assert rig.recorder.ops() == [], "the pass waits for the event loop, like every pass"
        assert rig.settle() == [BEGIN, SELECT, COMMIT]
        assert rig.recorder.selection.ids == ids(*wanted)
        assert rig.recorder.selection == selection_of(controller.sync.records, ids(*wanted))
        assert controller.selection_count == count
    assert (controller.snapshot_count, controller.apply_count,
            controller.sync.build_count) == before
    report = rig.reports[-1]
    assert report.snapshot is False and report.changes.is_empty and report.retired == 0
    assert rig.recorder.state() == controller.sync.expected_state()


def test_the_same_selection_again_reaches_nobody(rig: Rig) -> None:
    a, _b = shown(rig)
    rig.controller.set_selection([str(a.item_id)])
    rig.settle()
    reports = len(rig.reports)
    for _ in range(5):
        rig.controller.set_selection([str(a.item_id)])
    rig.controller.set_selection([str(a.item_id), "an id with no record"])
    assert rig.settle() == [] and len(rig.reports) == reports
    assert rig.controller.selection_count == 1


def test_many_selection_changes_in_one_turn_are_one_call(rig: Rig) -> None:
    a, b = shown(rig)
    for wanted in ([a], [a, b], [], [b], [a, b]):
        rig.controller.set_selection(str(item.item_id) for item in wanted)
    assert rig.settle() == [BEGIN, SELECT, COMMIT], "they coalesce in the flag"
    assert rig.recorder.selection.ids == ids(a, b)


def test_hidden_selection_changes_are_a_flag_and_ride_the_catch_up_pass(rig: Rig) -> None:
    """Gate G3: while 3D is hidden a selection costs no engine call and no snapshot."""
    a, b = shown(rig)
    controller = rig.controller
    controller.set_active(False)
    before = (controller.snapshot_count, controller.apply_count, controller.selection_count)
    for wanted in ([a], [b], [a, b], [a]):
        controller.set_selection(str(item.item_id) for item in wanted)
    assert rig.settle() == [] and rig.recorder.selection == EMPTY_SELECTION
    assert (controller.snapshot_count, controller.apply_count, controller.selection_count) == before
    assert controller.dirty is False, "a selection owes no build: no 'building' notice for it"
    controller.set_active(True)
    assert rig.settle() == [BEGIN, SELECT, COMMIT]
    assert rig.recorder.selection.ids == ids(a) and controller.snapshot_count == before[0]
    controller.set_active(False)
    controller.set_active(True)
    assert rig.settle() == [], "coming back with nothing changed costs nothing"


def test_a_hidden_edit_and_a_hidden_selection_are_one_catch_up_transaction(rig: Rig) -> None:
    a, b = shown(rig)
    rig.controller.set_active(False)
    rig.commands.execute(MoveItemsCommand([b], QPointF(40.0, 0.0)))
    rig.controller.set_selection([str(a.item_id)])
    rig.controller.set_active(True)
    assert rig.settle() == [BEGIN, ("update_transform", str(b.item_id)), SELECT, COMMIT]


def test_a_selected_item_that_moves_takes_the_ring_along_in_the_moves_transaction(rig: Rig) -> None:
    a, b = shown(rig)
    rig.controller.set_selection([str(a.item_id)])
    rig.settle()
    rig.commands.execute(MoveItemsCommand([a], QPointF(120.0, -30.0)))
    assert rig.settle() == [BEGIN, ("update_transform", str(a.item_id)), SELECT, COMMIT]
    assert rig.recorder.selection == selection_of(rig.controller.sync.records, ids(a))
    rig.commands.execute(MoveItemsCommand([b], QPointF(5.0, 5.0)))
    assert rig.settle() == [BEGIN, ("update_transform", str(b.item_id)), COMMIT]


def test_a_deleted_selected_item_loses_its_ring_and_undo_brings_it_back(rig: Rig) -> None:
    a, b = shown(rig)
    rig.controller.set_selection([str(a.item_id), str(b.item_id)])
    rig.settle()
    rig.commands.execute(DeleteItemsCommand(rig.scene, [a]))
    assert rig.settle() == [BEGIN, ("remove", str(a.item_id)), SELECT, COMMIT]
    assert rig.recorder.selection.ids == ids(b)
    rig.commands.undo()
    calls = rig.settle()
    assert calls[0] == BEGIN and ("add", str(a.item_id)) in calls and calls[-2:] == [SELECT, COMMIT]
    assert rig.recorder.selection.ids == ids(a, b), "the WISH was kept while the item was gone"


def test_the_selection_at_the_first_show_is_in_the_first_transaction(rig: Rig) -> None:
    a = rig.bed()
    rig.controller.set_selection([str(a.item_id)])
    rig.controller.set_active(True)
    assert rig.settle() == [BEGIN, ("add", str(a.item_id)), GROUND, SUN, SELECT, COMMIT]


def test_a_time_change_and_a_selection_in_one_turn(rig: Rig) -> None:
    from datetime import time

    a, _b = shown(rig)
    rig.location = {"latitude": 52.52, "longitude": 13.405}
    rig.controller.refresh_sun()
    rig.settle()
    snapshots = rig.controller.snapshot_count
    rig.clock.set_time_of_day(time(9, 30))
    rig.controller.set_selection([str(a.item_id)])
    assert rig.settle() == [BEGIN, SUN, COMMIT, BEGIN, SELECT, COMMIT], "light, then the ring"
    assert rig.controller.snapshot_count == snapshots, "neither read the plan"


class FailingOnce(RecordingSink):
    """A sink whose next ``set_selection`` raises (an engine error in the ring's upload)."""

    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def set_selection(self, selection: Selection) -> None:
        if self.fail:
            self.fail = False
            raise RuntimeError("the engine refused the ring\n2026 ERROR forged")
        super().set_selection(selection)


def test_a_sink_that_fails_on_the_ring_is_recovered_by_the_full_pass(
        canvas, qtbot, caplog: pytest.LogCaptureFixture) -> None:
    sink = FailingOnce()
    rig = Rig(canvas, qtbot, sink=sink)
    a, b = shown(rig)
    sink.fail = True
    rig.controller.set_selection([str(a.item_id)])
    calls = rig.settle()
    assert ("clear", None) in calls, "reset: the engine's scene was unknown"
    assert calls[-2:] == [SELECT, COMMIT] and sink.selection.ids == ids(a)
    assert sorted(c for c in calls if c[0] == "add") == sorted(
        [("add", str(a.item_id)), ("add", str(b.item_id))])
    assert rig.controller.recovery_count == 1 and rig.controller.last_error is None
    assert sink.state() == rig.controller.sync.expected_state()
    lines = [record.getMessage() for record in caplog.records if record.levelname == "ERROR"]
    assert lines and all("\n" not in line for line in lines), "one plain line each, no forged line"


def test_a_reset_of_the_engine_sends_the_ring_again(rig: Rig) -> None:
    a, _b = shown(rig)
    rig.controller.set_selection([str(a.item_id)])
    rig.settle()
    rig.controller.reset()                 # a fresh host: everything is sent again
    calls = rig.settle()
    assert calls[0] == ("clear", None) and calls[-2:] == [SELECT, COMMIT]
    assert not {op for op, _id in calls} & {"update_transform", "update_material", "replace_geometry"}
    assert rig.recorder.selection.ids == ids(a)


def test_selecting_after_shutdown_is_harmless(rig: Rig) -> None:
    a, _b = shown(rig)
    rig.controller.shutdown()
    rig.controller.set_selection([str(a.item_id)])
    assert rig.settle() == []
