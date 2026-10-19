"""The ground bake wired into the 3D workspace (Phase 17 L1.5 Part B, #385; §8.29.5).

The workspace's controller (``ui/view3d/sync_controller.py``) gets ONE
``GroundBaker``; every pass bakes in the same transaction as the geometry, and
while the baker's time budget leaves tiles pending the controller owes GROUND
passes — ``SceneSync.continue_ground()``: no snapshot, no diff — scheduled like any
pass. These tests drive a real ``CanvasScene`` through the app's own commands, a
``RecordingSink`` as the engine, and a baker with a budget of 0 (one tile a pass at
least: every multi-pass path is taken, and the counts are exact).

What is pinned: the ground follows an edit through as many passes as it needs and
ends on the finished ground (``expected_state()``); a pass of the ground takes no
snapshot and the net sees nothing of it (``snapshot_count`` grows by the edits only,
``unannounced_changes`` stays 0); a hidden 3D view does no ground work; a new
document shows none of the old ground; what the bake could not do reaches the
problems list (in the user's words); a re-baked tile's Model is counted for the
release policy; and the main window's workspace builds its controller with a baker.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF, QTimer
from PyQt6.QtGui import QColor

from open_garden_planner.core.commands import CreateItemCommand, MoveItemsCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import GroundTile, RecordingSink
from open_garden_planner.core.sim_clock import SimClock
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d import ground_bake
from open_garden_planner.ui.view3d.ground_bake import GroundBaker
from open_garden_planner.ui.view3d.problems_dialog import (
    GROUND_CAPPED,
    GROUND_FAILED,
    GROUND_PAINT_FAILED,
    View3DProblemsDialog,
    problems_of,
)
from open_garden_planner.ui.view3d.sync_controller import (
    GroundProblems,
    Scene3DController,
    TickReport,
)
from tests.integration.conftest import recolour

NOON = datetime(2026, 6, 21, 12, 0)
#: 4 x 4 tiles of 512 px at 1 px/cm
PLAN_CM = 2048.0


class GroundRig:
    """A canvas of 20.48 m, a clock, a recording sink and the controller with a baker
    of budget 0 between them — wired as the workspace wires them."""

    def __init__(self, qtbot: Any, *, budget_s: float | None = 0.0, quiet_ms: int | None = None,
                 sink: RecordingSink | None = None) -> None:
        self.qtbot = qtbot
        self.scene = CanvasScene(width_cm=PLAN_CM, height_cm=PLAN_CM)
        self.view = CanvasView(self.scene)
        qtbot.addWidget(self.view)
        self.view.set_snap_enabled(False)
        self.commands = self.view.command_manager
        self.clock = SimClock(NOON)
        self.sink = sink if sink is not None else RecordingSink()
        self.baker = GroundBaker(budget_s=budget_s)
        self.controller = Scene3DController(self.scene, self.clock, lambda: None, self.sink,
                                            ground_baker=self.baker, quiet_ms=quiet_ms)
        self.reports: list[TickReport] = []
        self.controller.applied.connect(self.reports.append)

    def add(self, item: Any) -> Any:
        item.layer_id = self.scene.active_layer.id
        self.commands.execute(CreateItemCommand(self.scene, item, "item"))
        return item

    def lawn(self, x: float = 100.0, y: float = 100.0, w: float = 1400.0, h: float = 1400.0) -> Any:
        """A lawn over most of the plan: nine of its sixteen tiles hold it."""
        return self.add(RectangleItem(x, y, w, h, object_type=ObjectType.LAWN))

    def during(self, which: Callable[[TickReport], bool], action: Callable[[], None],
               nth: int = 1) -> list[bool]:
        """Run ``action`` INSIDE the slot of the ``nth`` pass ``which`` accepts. Ground
        passes are posted events: none can run between a pass and its ``applied`` slot,
        so what the action sees is the state that pass left — whatever the machine's
        speed. (Waiting for "apply_count == 1" and then reading ``ground_owed`` raced:
        on a quiet machine every one-tile ground pass had run before the wait looked.)
        Returns a list that holds True once the action ran."""
        ran: list[bool] = []
        seen = [0]

        def slot(report: TickReport) -> None:
            if ran or not which(report):
                return
            seen[0] += 1
            if seen[0] == nth:
                ran.append(True)
                action()

        self.controller.applied.connect(slot)
        return ran

    def settle(self, timeout: int = 10_000) -> None:
        self.qtbot.waitUntil(lambda: self.controller.idle, timeout=timeout)

    def shown(self) -> dict[tuple[int, int], GroundTile]:
        ground = self.sink.ground
        return {tile.key: tile for tile in ground.tiles} if ground is not None else {}

    def finished(self) -> None:
        """The sink holds the FINISHED ground: what one apply of the snapshot gives."""
        assert not self.controller.sync.ground_pending
        assert self.sink.state() == self.controller.sync.expected_state()


@pytest.fixture()
def rig(qtbot: Any) -> GroundRig:
    return GroundRig(qtbot)


def _bare(rig: GroundRig, tile: GroundTile) -> bool:
    return tile.pixels == rig.baker._bare_tile(rig.baker.grid, tile.key).pixels  # noqa: SLF001


# ── the ground follows an edit through its passes ───────────────────────────


def test_a_lawn_is_painted_on_the_ground_over_passes_without_a_snapshot_each(
        rig: GroundRig) -> None:
    """One edit = one snapshot = one diff; the ground then needs as many passes as it
    has tiles to paint at one tile a pass — each a GROUND pass: no snapshot, no apply."""
    rig.lawn()
    rig.controller.set_active(True)
    rig.settle()
    controller = rig.controller
    assert (controller.snapshot_count, controller.apply_count) == (1, 1)
    painted = [key for key, tile in rig.shown().items() if not _bare(rig, tile)]
    assert len(rig.shown()) == 16 and len(painted) == 9  # the lawn's nine tiles
    # the first pass painted at least one tile; every other was a ground pass of its own
    assert controller.ground_count >= 1
    assert controller.ground_count + 1 >= len(painted) // 2  # a pass may also pay the backlog
    ground_reports = [report for report in rig.reports if report.ground_pass]
    assert len(ground_reports) == controller.ground_count
    assert all(not report.snapshot and report.changes.is_empty for report in ground_reports)
    assert controller.unannounced_changes == 0
    rig.finished()


def test_a_drag_snapshots_per_edit_and_the_net_sees_nothing_of_the_bake(rig: GroundRig) -> None:
    """Moves of a lawn, each in its own turn of the event loop: snapshots grow by the
    edits ONLY — never by a ground pass — and the quiet-time net, which looks at
    repaints nobody announced, finds nothing (the bake paints images, not the scene)."""
    lawn = rig.lawn(300.0, 300.0, 700.0, 600.0)
    rig.controller.set_active(True)
    rig.settle()
    snapshots, grounds = rig.controller.snapshot_count, rig.controller.ground_count
    for step in range(8):
        rig.commands.execute(MoveItemsCommand([lawn], QPointF(37.5 if step % 2 else -21.25, 12.0)))
        rig.qtbot.wait(5)
    rig.settle()
    rig.qtbot.wait(450)  # the net's quiet time (400 ms) passes with nothing to look at
    rig.settle()
    controller = rig.controller
    assert controller.snapshot_count - snapshots <= 8  # an edit's pass, at most one each
    assert controller.ground_count > grounds          # the ground followed in passes of its own
    assert controller.unannounced_changes == 0
    rig.finished()


def test_a_ground_pass_neither_spends_nor_extends_an_announcement(qtbot: Any) -> None:
    """The net (ADR-060) treats a repaint as explained only in the turn of its
    announcement's records pass (``_expire_explanation``). A GROUND pass is not a records
    pass: a write nobody announced, made while ground passes run, is still found by the
    net after its quiet time — and counted — and the ground still finishes."""
    from open_garden_planner.core.object_height import METADATA_KEY

    rig = GroundRig(qtbot, quiet_ms=150)
    rig.lawn()  # nine tiles at one a pass: ground passes for a while
    bed = rig.add(RectangleItem(1700.0, 1700.0, 200.0, 200.0, object_type=ObjectType.RAISED_BED))
    owed: list[bool] = []

    def write_unannounced() -> None:
        # inside the SECOND ground pass: the first records pass's announcement has
        # expired one turn after it, and ground work is still owed
        owed.append(rig.controller.sync.ground_pending)  # (the controller owes its pass after the slot)
        bed.metadata[METADATA_KEY] = 120.0  # no command, no nudge …
        bed.update()                        # … a repaint only

    ran = rig.during(lambda report: report.ground_pass, write_unannounced, nth=2)
    rig.controller.set_active(True)
    rig.qtbot.waitUntil(lambda: bool(ran), timeout=5000)
    assert owed == [True], "the write landed while ground passes were still owed"
    applies = rig.controller.apply_count
    rig.settle()
    rig.qtbot.waitUntil(lambda: rig.controller.reconcile_count >= 1, timeout=5000)
    rig.settle()
    assert rig.controller.unannounced_changes == 1 and rig.controller.apply_count == applies + 1
    assert rig.controller.ground_count >= 1
    assert rig.controller.sync.records[str(bed.item_id)].height_cm == 120.0
    rig.finished()


def test_ground_passes_starve_no_timer(rig: GroundRig) -> None:
    """Review 3, P2-4 — the no-starvation guarantee (§8.29.5): a ground pass is a posted
    event, one per turn of the event loop, so a timer that is due runs between two of
    them. A 0 ms timer armed inside ground pass 5 fires before ground pass 7 — whatever
    the machine's speed (``during``: the timer is armed in the pass's own slot)."""
    rig.lawn(0.0, 0.0, PLAN_CM, PLAN_CM)  # all sixteen tiles: many passes at budget 0
    fired: list[int] = []

    def arm() -> None:
        QTimer.singleShot(0, lambda: fired.append(rig.controller.ground_count))

    ran = rig.during(lambda report: report.ground_pass, arm, nth=5)
    rig.controller.set_active(True)
    rig.settle()
    assert ran and rig.controller.ground_count >= 7, rig.controller.ground_count
    assert fired and fired[0] <= 6, f"the timer ran after ground pass {fired}"
    rig.finished()


def test_an_edit_preempts_pending_ground_work_and_the_ground_still_finishes(rig: GroundRig) -> None:
    rig.lawn()
    owed: list[bool] = []

    def edit() -> None:
        owed.append(rig.controller.sync.ground_pending)  # nine tiles at one a pass: work is pending
        # the edit with the NEXT turn (a user's edit never runs inside a pass), and before
        # the first ground pass, which waits for the tick timer
        QTimer.singleShot(0, lambda: rig.add(RectangleItem(1800.0, 1800.0, 150.0, 150.0,
                                                          object_type=ObjectType.TERRACE_PATIO)))

    ran = rig.during(lambda report: report.snapshot and not report.ground_pass, edit)
    rig.controller.set_active(True)
    rig.qtbot.waitUntil(lambda: bool(ran), timeout=5000)
    assert owed == [True]
    rig.settle()
    assert rig.controller.apply_count == 2
    rig.finished()


def test_a_hidden_3d_view_does_no_ground_work_and_goes_on_when_shown(rig: GroundRig) -> None:
    rig.lawn()
    ran = rig.during(lambda report: report.snapshot and not report.ground_pass,
                     lambda: rig.controller.set_active(False))  # hidden right after the pass
    rig.controller.set_active(True)
    rig.qtbot.waitUntil(lambda: bool(ran), timeout=5000)
    painted, grounds = rig.baker.tiles_painted, rig.controller.ground_count
    rig.qtbot.wait(150)
    assert (rig.baker.tiles_painted, rig.controller.ground_count) == (painted, grounds)
    assert rig.controller.ground_owed and rig.controller.sync.ground_pending
    rig.controller.set_active(True)
    rig.settle()
    assert rig.controller.ground_count > grounds and rig.controller.snapshot_count == 1
    rig.finished()


def test_a_new_document_shows_none_of_the_old_ground(rig: GroundRig) -> None:
    """A document change drops the baker's tiles: while the new plan's ground is
    painted, a tile not yet reached is BARE — never a picture of the old plan."""
    rig.lawn()
    rig.controller.set_active(True)
    rig.settle()
    old = rig.shown()
    rig.scene.clear()
    rig.add(RectangleItem(1700.0, 1700.0, 200.0, 200.0, object_type=ObjectType.TERRACE_PATIO))
    rig.controller.document_changed()
    rig.qtbot.waitUntil(lambda: rig.controller.apply_count == 2, timeout=5000)
    for key, tile in rig.shown().items():
        if key not in rig.baker.last_repainted:
            assert _bare(rig, tile), key
            assert tile.pixels != old[key].pixels or _bare(rig, old[key])
    rig.settle()
    rig.finished()


def test_a_re_baked_tile_is_not_counted_for_the_release_policy(qtbot: Any) -> None:
    """A re-baked tile is a NEW Model (``quick3d/ground_tiles.py``), but tile Models are
    not what the workspace's cache release is for: twenty cycles of new tile Models
    stay flat without a release, and a release after tile TEXTURES were replaced
    leaves them behind in Qt Quick 3D (§11.4.17, measured on WARP: +10.7 to +13.3 MB
    a cycle with a release each cycle, flat without). So a pass that only re-baked
    tiles reports nothing retired — and asks for no release."""
    rig = GroundRig(qtbot, budget_s=None)  # the whole ground in one pass: exact counts
    lawn = rig.lawn(100.0, 100.0, 700.0, 300.0)  # two tiles
    rig.controller.set_active(True)
    rig.settle()
    before = len(rig.reports)
    recolour(lawn, QColor(200, 40, 40))
    rig.scene.note_plan_changed()
    rig.settle()
    (report,) = rig.reports[before:]
    assert report.changes.material == (str(lawn.item_id),)
    assert report.retired == 0  # its two tiles are new Models, and are not counted
    rig.finished()


# ── what the bake could not do reaches the problems list ─────────────────────


def test_an_item_whose_paint_fails_is_listed_in_the_users_words(
        rig: GroundRig, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ground_bake.paint_record
    lawn = rig.lawn(100.0, 100.0, 300.0, 300.0)

    def brittle(painter: Any, record: Any, *, budget: Any = None) -> None:
        if record.item_id == str(lawn.item_id):
            raise MemoryError("no image for the lawn")
        real(painter, record, budget=budget)

    monkeypatch.setattr(ground_bake, "paint_record", brittle)
    changes: list[int] = []
    rig.controller.problems_changed.connect(lambda: changes.append(1))
    rig.controller.set_active(True)
    rig.settle()
    problems = rig.controller.ground_problems
    assert problems.items == ((str(lawn.item_id), "LAWN", "MemoryError", "no image for the lawn"),)
    # review 3, P2-3: the lawn IS shown (cut off), so it is no object "not shown in 3D";
    # the ground is incomplete, and the list still names it
    assert problems.incomplete and rig.controller.problem_count == 0 and changes
    rows = problems_of(rig.controller.skipped, rig.controller.failures, problems)
    assert [row.code for row in rows] == [GROUND_PAINT_FAILED]
    dialog = View3DProblemsDialog()
    rig.qtbot.addWidget(dialog)
    dialog.set_problems(rows, lambda _item_id: "Front lawn")
    assert dialog.row_text(0) == "Front lawn (Lawn): it could not be painted completely on the 3D ground"


def test_the_strip_counts_no_object_whose_ground_paint_failed(
        canvas: CanvasView, qtbot: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review 3, P2-3, through the workspace: a lawn whose paint on the ground failed
    lies there cut off — it IS shown. The strip does not count it among the objects
    "not shown in 3D"; it says the ground does not show all of the plan, and the list
    still names the lawn."""
    from tests.integration.test_view3d_workspace_widget import SPLIT, Bench

    real = ground_bake.paint_record
    bench = Bench(canvas, qtbot, tmp_path)
    lawn = RectangleItem(300.0, 300.0, 600.0, 400.0, object_type=ObjectType.LAWN,
                         layer_id=bench.scene.active_layer.id)

    def brittle(painter: Any, record: Any, *, budget: Any = None) -> None:
        if record.item_id == str(lawn.item_id):
            raise MemoryError("no image for the lawn")
        real(painter, record, budget=budget)

    monkeypatch.setattr(ground_bake, "paint_record", brittle)
    bench.commands.execute(CreateItemCommand(bench.scene, lawn, "lawn"))
    workspace = bench.workspace
    workspace.set_mode(SPLIT)
    bench.settle()
    controller = workspace.controller
    assert controller is not None
    qtbot.waitUntil(lambda: controller.idle, timeout=10_000)
    assert controller.ground_problems.items and controller.problem_count == 0
    assert workspace.problems_text() == "The 3D ground does not show all of the plan"
    workspace.show_problems()
    dialog = workspace.problems_dialog
    assert dialog is not None and dialog.row_count() == 1
    assert dialog.row_text(0) == "Lawn: it could not be painted completely on the 3D ground"
    dialog.close()


def test_a_tile_that_cannot_hold_its_surfaces_is_a_note_of_the_ground(rig: GroundRig) -> None:
    """257 pavers in one tile: the tile is capped (the smallest left out). It is no
    item's problem; the list gets a note, first, that selects nothing."""
    for k in range(257):
        rig.add(RectangleItem(10.0 + 24.0 * (k % 20), 10.0 + 24.0 * (k // 20), 20.0, 20.0,
                              object_type=ObjectType.TERRACE_PATIO))
    rig.controller.set_active(True)
    rig.settle(timeout=30_000)
    problems = rig.controller.ground_problems
    assert problems == GroundProblems(capped_tiles=1) and problems.incomplete
    assert rig.controller.problem_count == 0
    rows = problems_of(rig.controller.skipped, rig.controller.failures, problems)
    assert [(row.item_id, row.code, row.count) for row in rows] == [("", GROUND_CAPPED, 1)]
    dialog = View3DProblemsDialog()
    rig.qtbot.addWidget(dialog)
    chosen: list[str] = []
    dialog.item_chosen.connect(chosen.append)
    dialog.set_problems(rows, lambda _item_id: "")
    assert dialog.row_text(0) == ("3D ground: in one place the plan puts more surfaces than the "
                                  "ground can show; the smallest are left out")
    dialog.activate_row(0)
    assert chosen == []


def test_a_bake_that_raises_is_a_note_and_is_not_tried_again_on_an_idle_tick(
        rig: GroundRig, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    rig.lawn(100.0, 100.0, 300.0, 300.0)
    monkeypatch.setattr(GroundBaker, "_admit", lambda *_a, **_k: (_ for _ in ()).throw(
        MemoryError("no memory\nfor the walk")))
    with caplog.at_level("ERROR"):
        rig.controller.set_active(True)
        rig.settle()
        problems = rig.controller.ground_problems
        assert problems.failure == ("MemoryError", "no memory\nfor the walk") and problems.incomplete
        rows = problems_of((), {}, problems)
        assert [row.code for row in rows] == [GROUND_FAILED]
        bakes = rig.baker.tiles_painted
        rig.controller.mark_dirty()  # an idle tick: nothing the bake depends on changed
        rig.settle()
        assert rig.baker.tiles_painted == bakes
    errors = [record for record in caplog.records if "could not be baked" in record.getMessage()]
    assert len(errors) == 1
    # ONE line: the exception's message is normalised (it can quote the plan, §8.11)
    assert "\n" not in errors[0].getMessage() and errors[0].exc_info is None


class TileZeroRefused(RecordingSink):
    """Review 3's probe (P1-1): an engine that refuses the ground as soon as tile (0, 0)
    carries a painted picture — the same way every time. After a reset the first slice
    paints other tiles and goes through; the ground pass that reaches (0, 0) fails."""

    def __init__(self) -> None:
        super().__init__()
        self.rig: GroundRig | None = None
        self.refused = 0

    def set_ground(self, ground: Any) -> None:
        rig = self.rig
        if rig is not None and any(tile.key == (0, 0) and not _bare(rig, tile)
                                   for tile in ground.tiles):
            self.refused += 1
            raise RuntimeError("the engine refused tile (0, 0)")
        super().set_ground(ground)


def test_a_ground_pass_that_fails_the_same_way_every_time_gives_up_and_waits_for_a_change(
        qtbot: Any, caplog: pytest.LogCaptureFixture) -> None:
    """Review 3, P1-1. It looped: the ground pass failed → a recovery pass reset and
    applied the first slice, which went through → another ground pass → the same failure
    (measured: 2,308 ground passes and 329 recoveries in 3 s, never idle — a busy loop
    on the GUI thread). Now the SECOND recovery caused by a ground pass since the last
    change is not made: the controller gives up — records dirty, nothing scheduled, one
    ERROR line, a note in the problems list — and the next real edit tries again."""
    from open_garden_planner.ui.view3d.problems_dialog import GROUND_UNFINISHED

    sink = TileZeroRefused()
    rig = GroundRig(qtbot, sink=sink)
    sink.rig = rig
    lawn = rig.lawn()  # tile (0, 0) is under it
    failed: list[str] = []
    rig.controller.failed.connect(failed.append)
    controller = rig.controller
    with caplog.at_level("DEBUG", logger="open_garden_planner.ui.view3d.sync_controller"):
        controller.set_active(True)
        rig.qtbot.wait(1000)
        assert controller.recovery_count <= 1, (controller.recovery_count, controller.ground_count)
        assert controller.idle, "nothing is scheduled after the give-up"
        assert controller.snapshot_count <= 2 and sink.refused == 2
        assert controller.dirty, "nothing was lost: the next change tries again"
        assert len(failed) == 1 and controller.last_error == failed[0]
        problems = controller.ground_problems
        assert problems.unfinished == ("RuntimeError", "the engine refused tile (0, 0)")
        assert problems.incomplete and controller.problem_count == 0
        rows = problems_of(controller.skipped, controller.failures, problems)
        assert [(row.item_id, row.code) for row in rows] == [("", GROUND_UNFINISHED)]
        dialog = View3DProblemsDialog()
        rig.qtbot.addWidget(dialog)
        dialog.set_problems(rows, lambda _item_id: "")
        assert dialog.row_text(0) == ("3D ground: it could not be finished; it is tried again "
                                      "with the next change")
        grounds = controller.ground_count
        rig.qtbot.wait(300)
        assert controller.ground_count == grounds, "no ground pass while given up"

        # the next real edit tries again: its pass rebuilds the scene the failed call
        # left unknown, the ground fails, ONE rebuild for that, it fails again — and waits
        rig.commands.execute(MoveItemsCommand([lawn], QPointF(10.0, 0.0)))
        rig.qtbot.wait(1000)
        assert controller.recovery_count == 1 + 2 and sink.refused == 4
        assert controller.idle and len(failed) == 2
        assert controller.ground_problems.unfinished is not None
        controller.document_changed()  # … and so does a new document
        rig.qtbot.wait(1000)
        assert controller.recovery_count == 3 + 2 and sink.refused == 6 and controller.idle
    lines = [record for record in caplog.records
             if record.name == "open_garden_planner.ui.view3d.sync_controller"
             and record.levelno >= 40]
    assert len(lines) == 1, [record.getMessage() for record in lines]
    assert "painting the 3D ground failed" in lines[0].getMessage()
    assert "\n" not in lines[0].getMessage() and lines[0].exc_info is None


# ── the main window's workspace ──────────────────────────────────────────────


def test_the_workspace_bakes_the_ground_of_what_is_drawn(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Through the real main window (the workspace is always there since L1.9; the
    engine replaced at its seam): the workspace's controller has a baker, a lawn drawn with 3D in Split is
    painted on the ground the engine is sent, and its strip says nothing is missing."""
    from open_garden_planner.ui.view3d.workspace import WorkspaceMode
    from tests.integration.test_view3d_workspace import build_app3d, first_pass
    from tests.integration.test_view3d_workspace_widget import wait_for_pipeline

    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    workspace, scene = window._workspace, window.canvas_scene
    lawn = RectangleItem(200.0, 200.0, 900.0, 700.0, object_type=ObjectType.LAWN,
                         layer_id=scene.active_layer.id)
    window.canvas_view.command_manager.execute(CreateItemCommand(scene, lawn, "lawn"))
    workspace.set_mode(WorkspaceMode.SPLIT)
    controller = first_pass(workspace, qtbot)
    assert isinstance(controller.sync.ground_baker, GroundBaker)
    qtbot.waitUntil(lambda: controller.idle, timeout=10_000)
    wait_for_pipeline(workspace, qtbot)
    ground = engines.sink.ground
    assert ground is not None and ground.tiles
    baker = controller.sync.ground_baker
    assert str(lawn.item_id) in baker.painted_ids()
    assert any(tile.pixels != baker._bare_tile(baker.grid, tile.key).pixels  # noqa: SLF001
               for tile in ground.tiles)
    assert engines.sink.state() == controller.sync.expected_state()
    assert workspace.problems_text() == "" and controller.unannounced_changes == 0


@pytest.mark.parametrize(("language", "unfinished", "capped", "painted"), [
    ("de", "3D-Boden: er konnte nicht fertiggestellt werden; mit der nächsten Änderung wird es "
           "erneut versucht",
     "3D-Boden: an 3 Stellen liegen mehr Flächen, als der Boden zeigen kann; die kleinsten "
     "werden weggelassen",
     "Rasen: die Darstellung auf dem 3D-Boden ist unvollständig"),
    ("es", "Suelo 3D: no se pudo terminar; se volverá a intentar con el próximo cambio",
     "Suelo 3D: en 3 lugares el plano pone más superficies de las que el suelo puede "
     "mostrar; se omiten las más pequeñas",
     "Césped: no se pudo pintar completo sobre el suelo 3D"),
])
def test_the_ground_rows_speak_the_users_language(
        qtbot: Any, language: str, unfinished: str, capped: str, painted: str) -> None:
    """Through Qt's own translator and the compiled catalogs the app ships — the rows
    a user reads, not the catalogs' entries."""
    from PyQt6.QtCore import QCoreApplication, QTranslator

    import open_garden_planner

    translator = QTranslator()
    catalogue = (Path(open_garden_planner.__file__).parent / "resources" / "translations"
                 / f"open_garden_planner_{language}.qm")
    assert translator.load(str(catalogue))
    QCoreApplication.installTranslator(translator)
    try:
        rows = problems_of((), {}, GroundProblems(items=(("id-1", "LAWN", "MemoryError", "x"),),
                                                  capped_tiles=3,
                                                  unfinished=("RuntimeError", "y")))
        dialog = View3DProblemsDialog()
        qtbot.addWidget(dialog)
        dialog.set_problems(rows, lambda _item_id: "")
        assert [dialog.row_text(index) for index in range(3)] == [unfinished, capped, painted]
    finally:
        QCoreApplication.removeTranslator(translator)
