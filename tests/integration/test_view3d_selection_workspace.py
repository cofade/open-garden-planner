"""Selection, the info card and walk mode in the workspace, on a stand-in engine (L1.8).

``Workspace`` around a real canvas, the engine replaced at its seam by a
``RecordingSink`` and a host that records what it is told and answers a ``pick``
from a script. The host's view is a REAL ``QWindow`` in a window container, its
filters installed on it, and every click and key is delivered to it by ``QTest`` —
through ``QGuiApplication``'s own input path, ``ShortcutOverride`` and the app's
shortcut map included (review 1, P1-3: calling ``eventFilter`` by hand skipped the
path the S key was lost on). Gates G2 (a 3D click → the canvas selection), G3 (the canvas
selection → the ring, through ONE sink call), G6 (the info card says the record's
numbers) and G7 (walk mode borrows the camera and gives it back) — everything about
them that is not a pixel. The same paths on the real engine:
``test_view3d_selection_render.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest
from PyQt6.QtCore import QEvent, QObject, QPoint, QPointF, Qt
from PyQt6.QtGui import QAction, QGuiApplication, QKeySequence, QWindow
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLineEdit, QWidget

from open_garden_planner.core.commands import (
    CreateItemCommand,
    DeleteItemsCommand,
    GroupCommand,
    MoveItemsCommand,
)
from open_garden_planner.core.measurements import format_length
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import RecordingSink
from open_garden_planner.core.scene3d.camera import FOV_DEG
from open_garden_planner.core.scene3d.selection import EMPTY_SELECTION, selection_of
from open_garden_planner.core.scene3d.walk import (
    EYE_HEIGHTS_CM,
    WALK_FOV_DEG,
    WALK_SPEED_CM_S,
    WALKER_RADIUS_CM,
)
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.quick3d.lifecycle import HostStateError
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_view3d_workspace_widget import Bench, FakeHost

PLAN, VIEW3D, SPLIT = WorkspaceMode.PLAN, WorkspaceMode.VIEW3D, WorkspaceMode.SPLIT
BEGIN, COMMIT, SELECT = ("begin", None), ("commit", None), ("set_selection", None)
MODEL_CALLS = {"add", "remove", "replace_geometry", "update_transform", "update_material"}
LEFT, NONE = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton
PLAIN, CTRL, SHIFT = (Qt.KeyboardModifier.NoModifier, Qt.KeyboardModifier.ControlModifier,
                      Qt.KeyboardModifier.ShiftModifier)
HOSTILE = '<b>x</b><img src="file:///C:/Windows/win.ini">'


@dataclass
class Hit:
    item_id: str
    behind: tuple[Any, ...] = ()


#: The input events the stand-in window's tail filter records.
_INPUT = {QEvent.Type.KeyPress, QEvent.Type.KeyRelease, QEvent.Type.ShortcutOverride,
          QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease, QEvent.Type.MouseMove}


class Tail(QObject):
    """Installed FIRST on the stand-in's window, so Qt runs it LAST: it sees exactly the
    input events no filter of the workspace took."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[QEvent.Type] = []

    def eventFilter(self, _watched: QObject | None, event: QEvent | None) -> bool:  # noqa: N802
        if event is not None and event.type() in _INPUT:
            self.events.append(event.type())
        return False


class PickHost(FakeHost):
    """``FakeHost`` whose ``pick`` answers from a script (and still records the call) —
    and whose view is a real ``QWindow`` in a window container, as ``Quick3DHost``'s is:
    the workspace's filters are installed ON it, and input reaches them only through Qt."""

    def __init__(self, prefer_software: bool) -> None:
        super().__init__(prefer_software)
        self.answer: Any = None
        self.error: BaseException | None = None
        self.window = QWindow()
        self.tail = Tail()
        self.window.installEventFilter(self.tail)
        self.focus_calls = 0

    def container(self, parent: QWidget | None = None) -> QWidget:
        self.widget = QWidget.createWindowContainer(self.window, parent)
        return self.widget

    def install_event_filter(self, watcher: Any) -> None:
        super().install_event_filter(watcher)
        self.window.installEventFilter(watcher)

    def focus(self) -> None:
        """``Quick3DHost.focus``: the view's window asks to be activated."""
        self.focus_calls += 1
        self.window.requestActivate()

    def has_focus(self) -> bool:
        return QGuiApplication.focusWindow() is self.window

    def pick(self, _x: float, _y: float) -> Any:
        self.frames_taken.append("pick")
        if self.error is not None:
            raise self.error
        return self.answer


class SelectionBench(Bench):
    def _factory(self, prefer_software: bool) -> tuple[PickHost, RecordingSink]:
        self.factory_calls.append(prefer_software)
        host, sink = PickHost(prefer_software), RecordingSink()
        self.hosts.append(host)
        self.sinks.append(sink)
        return host, sink

    # ── the 3D view's input, delivered by Qt to the host's real window ─────────

    def _taken(self, deliver: Any, kind: QEvent.Type) -> bool:
        """Deliver input with ``deliver()``; True when a filter of the workspace TOOK
        the event of ``kind`` (it never reached the tail)."""
        before = self.host.tail.events.count(kind)
        deliver()
        return self.host.tail.events.count(kind) == before

    def mouse(self, kind: QEvent.Type, x: float, y: float, button=LEFT, modifiers=PLAIN) -> bool:
        window, at = self.host.window, QPoint(round(x), round(y))
        if kind == QEvent.Type.MouseButtonPress:
            return self._taken(lambda: QTest.mousePress(window, button, modifiers, at), kind)
        if kind == QEvent.Type.MouseButtonRelease:
            return self._taken(lambda: QTest.mouseRelease(window, button, modifiers, at), kind)
        return self._taken(lambda: QTest.mouseMove(window, at), kind)

    def click(self, *ray: Any, modifiers=PLAIN, at: tuple[float, float] = (200.0, 150.0)) -> None:
        """A click whose ray meets the items ``ray`` (nearest first); none: the ground."""
        ids = [str(item.item_id) for item in ray]
        self.host.answer = Hit(ids[0], tuple(Hit(i) for i in ids[1:])) if ids else None
        QTest.mouseClick(self.host.window, LEFT, modifiers, QPoint(round(at[0]), round(at[1])))

    def key(self, key: Qt.Key, down: bool = True, modifiers=PLAIN, window: QWindow | None = None) -> bool:
        """A key pressed (or released) in ``window`` — the host's by default; True when a
        filter of the workspace took it."""
        target = window if window is not None else self.host.window
        if down:
            return self._taken(lambda: QTest.keyPress(target, key, modifiers), QEvent.Type.KeyPress)
        return self._taken(lambda: QTest.keyRelease(target, key, modifiers), QEvent.Type.KeyRelease)

    def selected(self) -> list[Any]:
        return list(self.scene.selectedItems())

    def calls(self, ms: int = 60) -> list[tuple[str, str | None]]:
        self.settle(ms)
        calls = self.sink.ops()
        self.sink.clear_calls()
        return calls

    def ring_ids(self) -> tuple[str, ...]:
        return self.sink.selection.ids

    def item(self, x: float, y: float, kind: ObjectType = ObjectType.RAISED_BED, *,
             layer: Layer | None = None, name: str = "") -> RectangleItem:
        made = RectangleItem(x, y, 300.0, 200.0, object_type=kind, name=name,
                             layer_id=(layer or self.scene.active_layer).id)
        self.commands.execute(CreateItemCommand(self.scene, made, "item"))
        made.setSelected(False)
        return made

    def open3d(self, mode: WorkspaceMode = SPLIT) -> None:
        """3D shown and the plan's first pass in the engine (it waits for its notice to
        be painted: a fixed pause would race it)."""
        self.scene.clearSelection()
        self.workspace.set_mode(mode)
        controller = self.workspace.controller
        self.qtbot.waitUntil(lambda: controller.apply_count >= 1 and not controller.dirty,
                             timeout=5000)
        self.settle(30)
        self.sink.clear_calls()


@pytest.fixture()
def bench(canvas: CanvasView, qtbot, tmp_path) -> SelectionBench:
    return SelectionBench(canvas, qtbot, tmp_path)


def ids(*items: Any) -> tuple[str, ...]:
    return tuple(sorted(str(item.item_id) for item in items))


# ── gate G2: a click in 3D → the canvas selection ────────────────────────────


def test_a_plain_click_selects_only_that_item_on_the_canvas(bench: SelectionBench) -> None:
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    b.setSelected(True)
    bench.calls()
    bench.click(a)
    assert bench.selected() == [a]
    assert bench.host.frames_taken == ["pick"], "one click, one pick"
    assert bench.calls() == [BEGIN, SELECT, COMMIT] and bench.ring_ids() == ids(a)
    bench.click(a)
    assert bench.selected() == [a] and bench.calls() == [], "the same click again: nothing to tell"


def test_ctrl_and_shift_toggle_and_a_click_on_nothing_clears(bench: SelectionBench) -> None:
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    bench.click(a)
    bench.click(b, modifiers=CTRL)
    assert set(bench.selected()) == {a, b}
    bench.settle()
    assert bench.ring_ids() == ids(a, b)
    bench.click(a, modifiers=SHIFT)
    assert bench.selected() == [b]
    bench.click()                                    # the ground, the sky
    assert bench.selected() == []
    bench.click(a)
    bench.click(modifiers=CTRL)                      # the canvas clears here too (measured)
    assert bench.selected() == []
    bench.settle()
    assert bench.ring_ids() == ()


def test_a_drag_selects_nothing_and_takes_no_frame(bench: SelectionBench) -> None:
    """Gate G2: more than ``CLICK_SLOP_PX`` — an orbit or pan gesture — never selects."""
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    b.setSelected(True)
    bench.host.answer = Hit(str(a.item_id))
    bench.mouse(QEvent.Type.MouseButtonPress, 200.0, 150.0)
    bench.mouse(QEvent.Type.MouseMove, 205.0, 150.0)
    bench.mouse(QEvent.Type.MouseMove, 260.0, 190.0)
    bench.mouse(QEvent.Type.MouseButtonRelease, 260.0, 190.0)
    assert bench.selected() == [b] and bench.host.frames_taken == []
    assert bench.workspace.camera.goal != bench.workspace.camera.pose or bench.workspace.camera.moving, (
        "it was a pan of the orbit camera")


def test_an_item_on_a_locked_layer_is_not_selectable_from_3d(bench: SelectionBench) -> None:
    """Gate G2, the locked layer — the rule measured on the canvas
    (``test_view3d_selection_bridge.py``): the click falls through it to what is
    behind, and to nothing when nothing is."""
    locked = Layer(name="locked")
    bench.scene.add_layer(locked)
    wall, behind, free = (bench.item(400.0, 300.0, layer=locked), bench.item(400.0, 900.0),
                          bench.item(2000.0, 300.0))
    bench.scene.update_layer_lock(locked.id, True)
    bench.open3d()
    assert str(wall.item_id) in bench.sink.item_ids(), "a locked layer is SHOWN in 3D"
    free.setSelected(True)
    bench.click(wall)                                # nothing behind it along the ray
    assert bench.selected() == [], "as a click on nothing"
    free.setSelected(True)
    bench.click(wall, behind)                        # the ray goes on to a selectable item
    assert bench.selected() == [behind]
    bench.click(wall, behind, modifiers=CTRL)
    assert bench.selected() == []
    bench.scene.update_layer_lock(locked.id, False)
    bench.click(wall, behind)
    assert bench.selected() == [wall], "unlocked, it is the nearest and it is selected"


def test_an_item_on_a_hidden_layer_has_no_record_and_cannot_be_hit(bench: SelectionBench) -> None:
    hidden = Layer(name="hidden")
    bench.scene.add_layer(hidden)
    ghost, real = bench.item(400.0, 300.0, layer=hidden), bench.item(1500.0, 300.0)
    bench.scene.update_layer_visibility(hidden.id, False)
    bench.open3d()
    assert bench.sink.item_ids() == (str(real.item_id),), "no record: nothing in 3D to click"
    real.setSelected(True)
    bench.click(ghost)                               # a stale id, if one ever came
    assert bench.selected() == []


def test_a_member_of_a_group_selects_the_group_and_every_member_gets_the_ring(
        bench: SelectionBench) -> None:
    a, b, c = bench.item(400.0, 300.0), bench.item(900.0, 300.0), bench.item(2000.0, 300.0)
    bench.commands.execute(GroupCommand(bench.scene, [a, b]))
    group = next(item for item in bench.scene.items() if isinstance(item, GroupItem))
    bench.open3d()
    bench.click(b)
    assert bench.selected() == [group]
    bench.settle()
    assert bench.ring_ids() == ids(a, b)
    bench.click(c, modifiers=CTRL)
    bench.settle()
    assert set(bench.selected()) == {group, c} and bench.ring_ids() == ids(a, b, c)


def test_a_click_while_the_host_cannot_answer_does_nothing_and_says_nothing(
        bench: SelectionBench, caplog: pytest.LogCaptureFixture) -> None:
    """Gate G2: ``HostStateError`` → no change of the selection, no message — neither in
    the pane nor in the log."""
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    b.setSelected(True)
    bench.calls()
    bench.host.error = HostStateError("pick(): the render target has not caught up")
    with caplog.at_level(logging.INFO, logger="open_garden_planner"):
        bench.click(a)
    assert bench.selected() == [b], "not cleared either: 'could not look' is not 'nothing there'"
    assert bench.workspace.status_text() == "" and bench.workspace.message_text() == ""
    assert caplog.records == [] and bench.calls() == []
    assert bench.host.frames_taken == ["pick"]
    bench.host.error = None
    bench.click(a)
    assert bench.selected() == [a]


def test_a_click_does_not_scroll_the_plan_and_changes_no_plan_data(bench: SelectionBench) -> None:
    a = bench.item(4000.0, 2500.0)
    bench.open3d()
    canvas = bench.view
    canvas.centerOn(QPointF(500.0, 500.0))
    centre = canvas.mapToScene(canvas.viewport().rect().center())
    stack = len(bench.commands._undo_stack)  # noqa: SLF001 - "nothing was pushed"
    bench.click(a)
    assert bench.selected() == [a]
    assert canvas.mapToScene(canvas.viewport().rect().center()) == centre
    assert len(bench.commands._undo_stack) == stack  # noqa: SLF001


# ── gate G3: the canvas selection → the ring ─────────────────────────────────


def test_the_ring_follows_the_canvas_selection_through_every_kind_of_change(
        bench: SelectionBench) -> None:
    """Gate G3: after select, add, remove, clear, delete-selected, undo and a plan
    change the set handed to the engine IS the canvas selection — and each of them
    reached the engine as ONE call that touches no model."""
    a, b, c = bench.item(400.0, 300.0), bench.item(1500.0, 300.0), bench.item(2600.0, 300.0)
    bench.open3d()
    records = bench.workspace.controller.sync.records

    def step(expected: tuple[str, ...]) -> list[tuple[str, str | None]]:
        calls = bench.calls()
        assert bench.ring_ids() == expected
        assert bench.sink.selection == selection_of(bench.workspace.controller.sync.records, expected)
        assert bench.sink.state() == bench.workspace.controller.sync.expected_state()
        return calls

    a.setSelected(True)                                                   # select
    assert step(ids(a)) == [BEGIN, SELECT, COMMIT]
    b.setSelected(True)                                                   # add
    assert step(ids(a, b)) == [BEGIN, SELECT, COMMIT]
    a.setSelected(False)                                                  # remove
    assert step(ids(b)) == [BEGIN, SELECT, COMMIT]
    bench.scene.clearSelection()                                          # clear
    assert step(()) == [BEGIN, SELECT, COMMIT]
    b.setSelected(True)
    c.setSelected(True)
    assert not {op for op, _id in step(ids(b, c))} & MODEL_CALLS
    bench.commands.execute(DeleteItemsCommand(bench.scene, [b]))          # delete-selected
    calls = step(ids(c))
    assert calls == [BEGIN, ("remove", str(b.item_id)), SELECT, COMMIT], "one transaction"
    bench.commands.undo()                                                 # undo
    calls = step(tuple(sorted(str(i.item_id) for i in bench.scene.selectedItems())))
    assert ("add", str(b.item_id)) in calls
    assert len(records) == 3 or len(bench.workspace.controller.sync.records) == 3
    bench.scene.clear()             # a plan change: CanvasScene.document_replaced tells it
    fresh = bench.item(700.0, 700.0)
    bench.settle(200)
    assert bench.ring_ids() == () and bench.sink.selection == EMPTY_SELECTION
    bench.sink.clear_calls()
    fresh.setSelected(True)
    assert step(ids(fresh)) == [BEGIN, SELECT, COMMIT]


def test_a_replaced_document_takes_the_selection_along_even_when_its_ids_come_back(
        bench: SelectionBench) -> None:
    """Re-opening the same file brings the same item ids back, unselected. The scene
    says "document replaced" while the OLD items are still in it and still selected
    (``CanvasScene.document_replaced``): reading the selection then would ring the
    new document's twin of the old selection. Nothing is rung, and the card's place
    shows the hint."""
    a = bench.item(400.0, 300.0)
    bench.open3d()
    a.setSelected(True)
    bench.settle()
    assert bench.ring_ids() == ids(a)
    replaced: list[tuple[str, ...]] = []
    bench.scene.document_replaced.connect(
        lambda: replaced.append(tuple(str(i.item_id) for i in bench.scene.selectedItems())))
    bench.scene.clear()
    assert replaced == [ids(a)], "the signal comes while the old item is still selected"
    twin = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                         layer_id=bench.scene.active_layer.id)
    twin._item_id = a.item_id  # noqa: SLF001 - what loading the same file does
    bench.scene.addItem(twin)
    bench.settle(200)
    assert str(twin.item_id) in bench.workspace.controller.sync.records
    assert bench.scene.selectedItems() == []
    assert bench.ring_ids() == () and bench.sink.selection == EMPTY_SELECTION
    card = bench.workspace.info_card
    assert card is not None and not card.isVisible() and card.item_id == ""
    assert card.parentWidget().hint() == "Click an object to see what the 3D view shows of it."


def test_a_selected_item_that_moves_takes_its_ring_along_in_the_same_transaction(
        bench: SelectionBench) -> None:
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    a.setSelected(True)
    bench.calls()
    bench.commands.execute(MoveItemsCommand([a], QPointF(120.0, 40.0)))
    assert bench.calls() == [BEGIN, ("update_transform", str(a.item_id)), SELECT, COMMIT]
    assert bench.sink.selection == selection_of(bench.workspace.controller.sync.records, ids(a))
    bench.commands.execute(MoveItemsCommand([b], QPointF(-30.0, 0.0)))
    assert bench.calls() == [BEGIN, ("update_transform", str(b.item_id)), COMMIT], (
        "an edit of something else does not resend the ring")


def test_a_canvas_selection_in_split_takes_no_snapshot(bench: SelectionBench) -> None:
    """The selection path itself reads nothing of the plan (``Scene3DController.
    set_selection`` -> ``SceneSync.send_selection``: no snapshot, no builder —
    ``test_view3d_selection_controller.py``). This is the same question asked of the
    whole app with the canvas VISIBLE: every selection change of a session, zero
    snapshots, and the engine told the ring alone. It was a strict ``xfail`` until the
    workspace's plan revision stopped the pipeline reading a repaint as an edit (the
    repaints now go to its quiet-time net, which finds nothing — also counted here)."""
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    controller = bench.workspace.controller
    snapshots = controller.snapshot_count
    reconciles = controller.reconcile_count
    for selection in ((a,), (a, b), (b,), ()):
        bench.scene.clearSelection()
        for item in selection:
            item.setSelected(True)
        assert bench.calls(80) == [BEGIN, SELECT, COMMIT]
    assert controller.snapshot_count == snapshots, "zero snapshots per selection change"
    bench.qtbot.waitUntil(lambda: controller.idle, timeout=5000)
    assert controller.unannounced_changes == 0, (
        f"the net ran {controller.reconcile_count - reconciles} time(s) and found nothing")
    assert bench.calls(50) == [], "and told the engine nothing"


def test_selection_while_the_3d_pane_is_hidden_costs_nothing_and_is_caught_up(
        bench: SelectionBench) -> None:
    """Gate G3: hidden = zero engine calls, zero snapshots, and no "building" notice
    for a selection — then ONE catch-up call when the pane shows."""
    a, b = bench.item(400.0, 300.0), bench.item(1500.0, 300.0)
    bench.open3d()
    controller = bench.workspace.controller
    bench.workspace.set_mode(PLAN)
    snapshots = controller.snapshot_count
    for item in (a, b, a, b):
        bench.scene.clearSelection()
        item.setSelected(True)
    a.setSelected(True)
    assert bench.calls(100) == [] and controller.snapshot_count == snapshots
    bench.workspace.set_mode(SPLIT)
    bench.qtbot.waitUntil(lambda: bench.ring_ids() == ids(a, b), timeout=5000)
    assert bench.calls(60) == [BEGIN, SELECT, COMMIT], "ONE transaction, and no model in it"
    bench.workspace.set_mode(PLAN)
    bench.workspace.set_mode(SPLIT)
    assert bench.calls(200) == [], "nothing changed while hidden: nothing is sent"


def test_the_selection_at_the_first_open_is_in_the_first_transaction(bench: SelectionBench) -> None:
    a = bench.item(400.0, 300.0)
    bench.item(1500.0, 300.0)
    a.setSelected(True)
    bench.workspace.set_mode(SPLIT)
    calls = bench.calls(120)
    assert calls[0] == BEGIN and calls[-2:] == [SELECT, COMMIT] and calls.count(BEGIN) == 1
    assert bench.ring_ids() == ids(a)


def test_a_selected_item_without_a_record_gets_no_ring_and_harms_nothing(bench: SelectionBench) -> None:
    a = bench.item(400.0, 300.0)
    broken = bench.item(1500.0, 300.0)
    broken.metadata[METADATA_KEY] = float("inf")     # refused by the record layer
    bench.open3d()
    broken.setSelected(True)
    assert bench.calls() == [], "nothing to draw: nothing is sent"
    a.setSelected(True)
    assert bench.calls() == [BEGIN, SELECT, COMMIT] and bench.ring_ids() == ids(a)


def test_closing_the_engine_lets_the_canvas_go(bench: SelectionBench) -> None:
    a = bench.item(400.0, 300.0)
    bench.open3d()
    workspace = bench.workspace
    workspace.shutdown()
    a.setSelected(True)                               # the signal still fires: nobody listens
    bench.scene.clearSelection()
    assert workspace.controller is None and workspace.walking is False
    assert workspace.walk_action.isEnabled() is False


# ── gate G6: the info card ───────────────────────────────────────────────────


def test_the_card_is_shown_for_exactly_one_selected_item_while_3d_is_visible(
        bench: SelectionBench) -> None:
    a, b = bench.item(400.0, 300.0, name="North bed"), bench.item(1500.0, 300.0)
    a.setSelected(True)
    assert bench.workspace.info_card is None, "no pane yet: no card, nothing imported"
    bench.workspace.set_mode(SPLIT)
    bench.settle()
    card = bench.workspace.info_card
    assert card is not None and card.isVisible() and card.title() == "North bed"
    slot = card.parentWidget()
    pane = bench.workspace.pane
    assert slot.parentWidget() is pane, "in the pane's layout — never over the view"
    engine = pane.engine_widget
    assert slot.geometry().top() >= engine.mapTo(pane, engine.rect().bottomLeft()).y(), (
        "BELOW the native view")
    assert slot.hint() == ""
    b.setSelected(True)
    assert not card.isVisible(), "two selected: no card"
    assert slot.hint() == "2 objects selected."
    a.setSelected(False)
    assert card.isVisible() and card.item_id == str(b.item_id) and slot.hint() == ""
    bench.scene.clearSelection()
    assert not card.isVisible() and card.item_id == ""
    assert slot.hint() == "Click an object to see what the 3D view shows of it."
    a.setSelected(True)
    bench.workspace.set_mode(PLAN)
    assert not card.isVisible()
    bench.scene.clearSelection()
    b.setSelected(True)                               # while hidden: nothing is computed
    assert card.item_id == str(a.item_id), "the hidden card was not touched"
    bench.workspace.set_mode(VIEW3D)
    assert card.isVisible() and card.item_id == str(b.item_id), "refreshed when it shows"
    bench.workspace.set_chrome_visible(False)         # fullscreen preview hides the controls
    assert not card.isVisible() and not slot.isVisible()
    bench.workspace.set_chrome_visible(True)
    assert card.isVisible() and slot.isVisible()


def test_no_selection_change_and_no_walk_resizes_the_3d_view(bench: SelectionBench) -> None:
    """THE layout rule of the card and of walk mode's controls. Measured on the real
    engine before it held: a card that came with a selection took 152 px from the
    view, the picture was re-scaled under the pointer, and the Ctrl+click on the
    neighbour of the item just selected met the lawn and cleared the selection; the
    eye-height box made the strip 4 px taller. A resize is also a new swapchain, and
    a view between two sizes answers no click (``HostStateError``: "not now")."""
    a, b = bench.item(400.0, 300.0, name="North bed"), bench.item(1500.0, 300.0)
    herb = drop(bench.view, "PERENNIAL:species=lavender", QPointF(450.0, 350.0))
    bench.open3d()
    pane = bench.workspace.pane
    engine, slot = pane.engine_widget, bench.workspace.info_card.parentWidget()
    assert slot.isVisible() and bench.workspace.info_card.isHidden(), "its place is there at once"
    seen = []

    def look(what: str) -> None:
        bench.settle(30)
        seen.append((what, engine.geometry().getRect(), slot.geometry().getRect(),
                     pane.strip.height()))

    look("nothing selected")
    a.setSelected(True)
    look("a built item")
    b.setSelected(True)
    look("two")
    bench.scene.clearSelection()
    herb.setSelected(True)
    look("a plant: the fullest card")
    bench.scene.clearSelection()
    look("nothing again")
    bench.click(a)
    look("a click in the 3D view")
    bench.workspace.walk_action.trigger()
    assert bench.workspace.walking
    look("walking")
    bench.workspace.set_walking(False)
    look("back in orbit")
    assert {row[1:] for row in seen} == {seen[0][1:]}, [row for row in seen if row[1:] != seen[0][1:]]
    assert engine.height() > 200 and slot.height() == bench.workspace.info_card.slot_height()


def test_the_cards_place_goes_with_the_engine_view(bench: SelectionBench) -> None:
    """No engine view: nothing to stand below, and no hint to click in a view that is
    not there."""
    bench.item(400.0, 300.0)
    bench.open3d()
    slot = bench.workspace.info_card.parentWidget()
    assert slot.isVisible()
    bench.workspace._stop_engine()  # noqa: SLF001 - what a failed pass and a close do
    assert not slot.isVisible() and slot.hint() == "" and bench.workspace.info_card.isHidden()


def test_the_card_shows_the_records_height_at_two_plan_dates(bench: SelectionBench) -> None:
    """Gate G6: a dated tree grows with the plan date; the card's height is the applied
    record's ``height_cm`` — the model's top — at each date, and the canopy its
    ``radius_cm``, never a second computation."""
    apple = drop(bench.view, "TREE:species=apple tree", QPointF(2500.0, 1500.0))
    apple.metadata["plant_instance"] = {
        "planting_date": "2024-04-01", "current_height_cm": 180.0, "current_spread_cm": 120.0}
    bench.open3d()
    apple.setSelected(True)
    card = bench.workspace.info_card
    seen = []
    for day in (date(2026, 6, 21), date(2029, 6, 21)):
        bench.clock.set_date(day)
        bench.settle(120)
        record = bench.workspace.controller.sync.records[str(apple.item_id)]
        assert record.height_cm is not None
        # v1 (L2.3): the height names its source — grown from the measured size
        assert card.value("Height:") == f"{format_length(record.height_cm)} (grown to the plan date)"
        assert card.value("Growth:") is not None
        assert card.value("Canopy diameter:") == format_length(2.0 * float(record.params["radius_cm"]))
        assert str(day.year)[-2:] in (card.value("Sizes on:") or "")
        seen.append(record.height_cm)
    assert seen[1] > seen[0] + 10.0, "the tree really grew between the two dates"
    assert card.value("Type:") == "Tree" and card.note() == ""


def test_a_plant_without_a_known_height_says_so_on_the_card(bench: SelectionBench) -> None:
    herb = drop(bench.view, "PERENNIAL:category=PERENNIAL", QPointF(1200.0, 900.0))
    herb.metadata.pop(METADATA_KEY, None)
    bench.open3d()
    herb.setSelected(True)
    bench.settle()
    record = bench.workspace.controller.sync.records[str(herb.item_id)]
    card = bench.workspace.info_card
    from open_garden_planner.core.plant_height_estimate import ESTIMATED_HEIGHT_PARAM

    assert record.height_cm is None
    est = record.params.get(ESTIMATED_HEIGHT_PARAM)
    assert est is not None
    assert card.value("Height:") == f"{format_length(est)} (estimated)"
    assert card.note() == "", "it HAS a model: the estimated plant form"


def test_an_item_without_a_3d_model_shows_its_reason_in_the_lists_own_words(
        bench: SelectionBench) -> None:
    good = bench.item(400.0, 300.0)
    bad = bench.item(1500.0, 1500.0, name="North bed")
    bad.metadata[METADATA_KEY] = float("inf")
    lawn = bench.item(2600.0, 300.0, ObjectType.LAWN, name="Lawn")
    bench.open3d()
    card = bench.workspace.info_card
    bad.setSelected(True)
    reason = "one of its sizes is outside what the 3D view can show"
    assert card.note() == f"Not shown in 3D: {reason}."
    bench.workspace.show_problems()
    assert reason in bench.workspace.problems_dialog.row_text(0), "the SAME words as the list"
    bench.scene.clearSelection()
    lawn.setSelected(True)
    assert card.note() == "Drawn on the ground in 3D: the plan gives it no height."
    bench.scene.clearSelection()
    good.setSelected(True)
    assert card.note() == "" and card.value("Height:") is not None
    bad.metadata[METADATA_KEY] = 80.0                 # fixed: the note goes with the next pass
    bench.scene.clearSelection()
    bad.setSelected(True)
    bench.commands.stack_changed.emit()
    bench.settle()
    assert card.note() == "" and card.value("Height:") == "80.0 cm (set on the object)"


def test_a_plant_on_a_bed_names_its_bed(bench: SelectionBench) -> None:
    bed = bench.item(400.0, 300.0, name=HOSTILE)
    herb = drop(bench.view, "PERENNIAL:category=PERENNIAL", QPointF(550.0, 400.0))
    assert herb.parent_bed_id == bed.item_id, "the drop linked it to the bed under it"
    bench.open3d()
    herb.setSelected(True)
    bench.settle()
    card = bench.workspace.info_card
    assert card.value("Bed:") == HOSTILE, "the bed's name, as its characters"


def test_a_name_that_is_markup_is_shown_as_its_characters_on_the_card(bench: SelectionBench) -> None:
    """The story's security add-on, through the real workspace."""
    bed = bench.item(400.0, 300.0, name=HOSTILE)
    bench.open3d()
    bed.setSelected(True)
    card = bench.workspace.info_card
    assert card.title() == HOSTILE
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in card.labels())
    assert all(label.toolTip() == "" for label in card.labels())


def test_show_in_plan_centres_the_plan_and_leaves_3d_only_mode_for_split(bench: SelectionBench) -> None:
    far = bench.item(4300.0, 2600.0)
    bench.open3d(VIEW3D)
    bench.view.set_zoom(bench.view.zoom_factor * 6.0)
    far.setSelected(True)
    card = bench.workspace.info_card
    assert bench.workspace.mode is VIEW3D and not bench.view.isVisible()
    card._button.click()  # noqa: SLF001
    assert bench.workspace.mode is SPLIT and bench.view.isVisible()
    bench.settle()
    centre = bench.view.mapToScene(bench.view.viewport().rect().center())
    target = far.sceneBoundingRect().center()
    assert abs(centre.x() - target.x()) < 60.0 and abs(centre.y() - target.y()) < 60.0
    assert bench.selected() == [far], "the selection is not touched"
    bench.view.centerOn(QPointF(300.0, 300.0))
    bench.workspace.show_in_plan(str(far.item_id))    # in Split it only centres
    assert bench.workspace.mode is SPLIT
    centre = bench.view.mapToScene(bench.view.viewport().rect().center())
    assert abs(centre.x() - target.x()) < 60.0
    bench.workspace.show_in_plan("no such id")        # nothing to centre on: nothing happens


def test_the_problems_list_still_selects_through_the_same_path(bench: SelectionBench) -> None:
    """``Workspace.select_item`` is ONE path for the list and the click: a group's
    member selects the group; a locked item cannot be selected — and is still shown."""
    locked = Layer(name="locked")
    bench.scene.add_layer(locked)
    a, b, wall = bench.item(400.0, 300.0), bench.item(900.0, 300.0), bench.item(3000.0, 2000.0, layer=locked)
    bench.commands.execute(GroupCommand(bench.scene, [a, b]))
    group = next(item for item in bench.scene.items() if isinstance(item, GroupItem))
    bench.scene.update_layer_lock(locked.id, True)
    bench.open3d()
    bench.workspace.select_item(str(b.item_id))
    assert bench.selected() == [group]
    bench.workspace.select_item(str(wall.item_id))
    assert bench.selected() == []
    bench.workspace.select_item("no such id")
    assert bench.selected() == []


def test_every_list_that_names_objects_selects_through_the_one_select_by_id_path(
        bench: SelectionBench) -> None:
    """ONE select-by-id path (``ui/canvas/select_by_id.py``): a row of the Diagnostics,
    Canopy or Guilds panel (``ObjectNavigator``) and a row of the 3D view's problems
    list (``Workspace.select_item``) give the SAME canvas selection for the same id —
    a group member selects its group, a locked object is not selected, an id that
    names nothing leaves the selection alone — and the ring follows a panel's
    navigation like any other selection: one ring call, no model touched."""
    from open_garden_planner.ui.panels.diagnostics_panel import ObjectNavigator

    locked = Layer(name="locked")
    bench.scene.add_layer(locked)
    a, b, c = bench.item(400.0, 300.0), bench.item(900.0, 300.0), bench.item(1500.0, 300.0)
    before, wall = bench.item(2200.0, 300.0), bench.item(3000.0, 2000.0, layer=locked)
    bench.commands.execute(GroupCommand(bench.scene, [a, b]))
    group = next(item for item in bench.scene.items() if isinstance(item, GroupItem))
    bench.scene.update_layer_lock(locked.id, True)
    bench.open3d()
    navigator = ObjectNavigator(bench.scene)

    def by_panel(item_id: str) -> list[Any]:
        navigator.select_ids([item_id])
        bench.qtbot.waitUntil(lambda: not navigator._navigation.isActive(), timeout=2000)  # noqa: SLF001
        return bench.selected()

    def by_list(item_id: str) -> list[Any]:
        bench.workspace.select_item(item_id)
        return bench.selected()

    expected = {str(c.item_id): [c], str(b.item_id): [group], str(wall.item_id): [],
                "no such id": [before]}
    for item_id, selection in expected.items():
        for path in (by_panel, by_list):
            bench.scene.clearSelection()
            before.setSelected(True)
            assert path(item_id) == selection, (path.__name__, item_id)

    bench.scene.clearSelection()
    bench.calls()
    navigator.select_ids([str(a.item_id)])
    bench.qtbot.waitUntil(lambda: bench.ring_ids() == ids(a, b), timeout=3000)
    assert bench.selected() == [group]
    assert bench.calls() == [BEGIN, SELECT, COMMIT], "the ring, and no model touched"


def test_no_list_resolves_an_id_and_selects_on_its_own() -> None:
    """Structure pin of the one select-by-id path: the panels' navigator, the plant
    search, the 3D problems list and the 3D click call ``ui/canvas/select_by_id.py``,
    and no module of the panels or of the 3D package clears the canvas selection or
    looks an item up by id for a selection of its own."""
    import ast
    from pathlib import Path as _Path

    src = _Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"

    def calls(path: _Path, function: str) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == function)
        return {(c.func.id if isinstance(c.func, ast.Name) else getattr(c.func, "attr", ""))
                for c in ast.walk(node) if isinstance(c, ast.Call)}

    assert "select_by_ids" in calls(src / "ui/panels/diagnostics_panel.py", "_navigate")
    assert "select_by_ids" in calls(src / "ui/panels/plant_search_panel.py", "_apply_selection")
    assert "select_by_ids" in calls(src / "ui/view3d/workspace.py", "select_item")
    assert "replace_selection" in calls(src / "ui/view3d/selection_bridge.py", "apply_click")
    offenders = []
    for folder in ("ui/panels", "ui/view3d"):
        for path in sorted((src / folder).rglob("*.py")):
            if path.name == "find_replace_panel.py":
                continue  # selects the items a text search FOUND, not ids
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for call in ast.walk(tree):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                        and call.func.attr == "clearSelection"):
                    offenders.append(f"{path.relative_to(src)}:{call.lineno}")
    assert offenders == [], "a second select-by-id path: use ui/canvas/select_by_id.py"


# ── gate G7: walk mode in the workspace ──────────────────────────────────────


def walk_ready(bench: SelectionBench) -> Any:
    bench.item(400.0, 300.0)
    bench.open3d()
    camera = bench.workspace.camera
    camera.orbit(47.0, 11.0)
    camera.zoom(0.6)
    camera.pan(350.0, -120.0)
    camera.snap()
    bench.workspace._apply_camera()  # noqa: SLF001 - the user has looked around
    return camera


def test_enter_walk_and_leave_restores_the_orbit_pose_exactly(bench: SelectionBench) -> None:
    """Gate G7: the walk borrows the camera; the orbit pose is never touched and is
    what the engine is shown again — the same object, the same numbers."""
    camera = walk_ready(bench)
    workspace, host = bench.workspace, bench.host
    pose, goal = camera.pose, camera.goal
    orbit_call = host.cameras[-1]
    assert orbit_call == (pose.eye, pose.target_scene, FOV_DEG)
    stack = len(bench.commands._undo_stack)  # noqa: SLF001
    assert workspace.walk is None and len(host.filters) == 1, "nothing of walk mode exists yet"

    workspace.walk_action.trigger()
    assert workspace.walking and workspace.walk_action.isChecked() and len(host.filters) == 2
    eye, target, fov = host.cameras[-1]
    assert fov == WALK_FOV_DEG and eye[2] == EYE_HEIGHTS_CM[0] == target[2]
    start = workspace.walk.state
    assert (start.east, start.north) == pytest.approx(pose.target), "where the orbit camera looked"
    assert start.yaw_deg == pytest.approx(pose.yaw_deg % 360.0), "facing the way it looked"
    assert [action.isChecked() for action in workspace.eye_height_actions] == [True, False, False]

    bench.key(Qt.Key.Key_W)                           # walk for a while
    bench.qtbot.waitUntil(lambda: workspace.walk.state.shown != start.shown, timeout=3000)
    bench.settle(120)
    bench.key(Qt.Key.Key_W, down=False)
    bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0)
    bench.mouse(QEvent.Type.MouseMove, 180.0, 140.0)      # look around
    bench.mouse(QEvent.Type.MouseButtonRelease, 180.0, 140.0)
    moved = workspace.walk.state
    assert moved.shown != start.shown and moved.yaw_deg != start.yaw_deg
    assert host.cameras[-1][0][:2] == moved.shown, "the engine sees through the walker's eyes"
    assert camera.pose is pose and camera.goal is goal and not camera.moving

    assert bench.key(Qt.Key.Key_Escape) is True       # Esc leaves
    assert not workspace.walking and not workspace.walk_action.isChecked()
    assert host.cameras[-1] == orbit_call, "the orbit pose, to the last digit"
    assert camera.pose is pose and camera.goal is goal
    assert len(bench.commands._undo_stack) == stack, "walking never touches the plan"  # noqa: SLF001
    assert host.frames_taken == [], "and takes no frame"
    assert bench.key(Qt.Key.Key_Escape) is False, "not walking: Escape is the application's again"


def _walking_at(bench: SelectionBench, at: tuple[float, float] = (2500.0, 1500.0),
                yaw: float = 0.0) -> tuple[Any, list[float]]:
    """Walk mode entered at ``at`` facing ``yaw`` with its clock in the test's hand."""
    walk_ready(bench)
    workspace = bench.workspace
    workspace._camera._pose = type(workspace.camera.pose)(at, 2000.0, yaw, 45.0)  # noqa: SLF001
    assert workspace.set_walking(True) is True
    now = [1000.0]
    workspace.walk.clock = lambda: now[0]
    return workspace.walk, now


def _hold(bench: SelectionBench, walk: Any, now: list[float], key: Qt.Key, seconds: float,
          modifiers=PLAIN, window: QWindow | None = None) -> bool:
    """Hold ``key`` for ``seconds`` of the walker's clock (60 Hz); True when it was taken."""
    taken = bench.key(key, modifiers=modifiers, window=window)
    for _ in range(round(seconds * 60)):
        now[0] += 1.0 / 60.0
        walk.step()
    bench.key(key, down=False, modifiers=modifiers, window=window)
    return taken


def test_the_walkers_keys_beat_the_windows_shortcuts_and_no_other_key_does(
        bench: SelectionBench) -> None:
    """Review 1, P0, on the stand-in's REAL window with keys delivered by Qt: the bench's
    window gets the main window's Snap to Grid (S, a window shortcut), a G and a Ctrl+S.
    The CONTROL first: not walking, S pressed in the 3D window IS that shortcut (the path
    the key was lost on is live here). Walking: S walks the walker back and no action
    fires; G and Ctrl+S — not the walker's — still reach their shortcuts."""
    bench.window.activateWindow()
    bench.qtbot.waitActive(bench.window)
    fired: list[str] = []
    for text in ("S", "G", "Ctrl+S"):
        action = QAction(text, bench.window)
        action.setShortcut(QKeySequence(text))
        action.triggered.connect(lambda _checked=False, name=text: fired.append(name))
        bench.window.addAction(action)
    walk_ready(bench)
    bench.key(Qt.Key.Key_S)
    bench.key(Qt.Key.Key_S, down=False)
    assert fired == ["S"], "the control: an unclaimed S in the 3D window is the window's shortcut"
    fired.clear()
    walk, now = _walking_at(bench)
    start = walk.state.shown
    assert _hold(bench, walk, now, Qt.Key.Key_S, 1.0) is True
    assert fired == [], "S belongs to the walker"
    back = walk.state.shown
    assert back[0] == pytest.approx(start[0], abs=1e-6)
    assert back[1] == pytest.approx(start[1] - WALK_SPEED_CM_S, abs=1e-6), "a second back, south"
    assert _hold(bench, walk, now, Qt.Key.Key_S, 0.5, modifiers=SHIFT) is True
    assert walk.state.shown[1] == pytest.approx(back[1] - WALK_SPEED_CM_S, abs=1e-6), "Shift runs"
    there = walk.state.shown
    bench.key(Qt.Key.Key_G)
    bench.key(Qt.Key.Key_G, down=False)
    bench.key(Qt.Key.Key_S, modifiers=CTRL)
    bench.key(Qt.Key.Key_S, down=False, modifiers=CTRL)
    assert fired == ["G", "Ctrl+S"], "every other key, and a key with Ctrl, is passed on"
    assert walk.state.shown == there and not walk.moving


def test_walk_mode_takes_the_keyboard_and_gives_it_back(bench: SelectionBench) -> None:
    """Review 1, P1-2: the plan had the keyboard (W would pick the Wall tool there,
    Escape would reach the canvas). Entering walk mode gives it to the 3D view —
    keys sent to whatever window has the focus now walk — and leaving gives it back."""
    bench.window.activateWindow()
    bench.qtbot.waitActive(bench.window)
    walk_ready(bench)
    workspace = bench.workspace
    bench.view.setFocus()
    bench.qtbot.waitUntil(lambda: QApplication.focusWidget() is bench.view, timeout=2000)
    workspace._camera._pose = type(workspace.camera.pose)((2500.0, 1500.0), 2000.0, 0.0, 45.0)  # noqa: SLF001
    workspace.walk_action.trigger()
    assert workspace.walking and bench.host.focus_calls == 1
    bench.qtbot.waitUntil(lambda: QGuiApplication.focusWindow() is bench.host.window, timeout=2000)
    bench.settle(100)  # the platform's focus events, before a key is pressed into it
    assert QApplication.focusWidget() is bench.host.widget
    walk = workspace.walk
    now = [1000.0]
    walk.clock = lambda: now[0]
    start = walk.state.shown
    focused = QGuiApplication.focusWindow()
    assert _hold(bench, walk, now, Qt.Key.Key_W, 0.5, window=focused) is True
    assert walk.state.shown[1] == pytest.approx(start[1] + WALK_SPEED_CM_S * 0.5, abs=1e-6)
    assert bench.key(Qt.Key.Key_Escape, window=QGuiApplication.focusWindow()) is True
    assert not workspace.walking
    bench.qtbot.waitUntil(lambda: QApplication.focusWidget() is bench.view, timeout=2000)
    assert QGuiApplication.focusWindow() is bench.window.windowHandle(), "the plan has it again"


def test_a_view_that_lost_the_keyboard_keeps_it_where_it_went(bench: SelectionBench) -> None:
    """Leaving gives the focus back only while the 3D view still has it: a user who
    clicked into the plan meanwhile keeps the plan's focus where they put it."""
    bench.window.activateWindow()
    bench.qtbot.waitActive(bench.window)
    walk_ready(bench)
    workspace = bench.workspace
    bench.view.setFocus()
    workspace.set_walking(True)
    bench.qtbot.waitUntil(lambda: QGuiApplication.focusWindow() is bench.host.window, timeout=2000)
    bench.settle(100)
    elsewhere = QLineEdit(bench.window)  # a field of the main window the user clicked into
    elsewhere.show()
    bench.window.activateWindow()
    elsewhere.setFocus()
    bench.qtbot.waitUntil(lambda: QApplication.focusWidget() is elsewhere
                          and QGuiApplication.focusWindow() is bench.window.windowHandle(), timeout=2000)
    bench.settle(100)
    workspace.set_walking(False)
    bench.settle(100)
    assert QApplication.focusWidget() is elsewhere


def test_a_flick_that_turns_the_walkers_view_is_no_click(bench: SelectionBench) -> None:
    """Review 1, P2-4: walking, a left press that moves less than the click's slop is a
    click (it picks, and the view does not turn); one that moves further turns the view
    and picks NOTHING on its release — a look never selects."""
    walk, _now = _walking_at(bench)
    a = next(item for item in bench.scene.items() if isinstance(item, RectangleItem))
    bench.host.answer = Hit(str(a.item_id))
    yaw = walk.state.yaw_deg
    bench.mouse(QEvent.Type.MouseButtonPress, 200.0, 150.0)
    bench.mouse(QEvent.Type.MouseMove, 202.0, 151.0)
    bench.mouse(QEvent.Type.MouseButtonRelease, 202.0, 151.0)
    assert bench.host.frames_taken == ["pick"] and bench.selected() == [a]
    assert walk.state.yaw_deg == yaw, "within the slop: a click, and no look"
    bench.scene.clearSelection()
    bench.mouse(QEvent.Type.MouseButtonPress, 200.0, 150.0)
    bench.mouse(QEvent.Type.MouseMove, 203.0, 150.0)
    bench.mouse(QEvent.Type.MouseMove, 212.0, 150.0)
    bench.mouse(QEvent.Type.MouseButtonRelease, 212.0, 150.0)
    assert walk.state.yaw_deg != yaw, "it looked"
    assert bench.host.frames_taken == ["pick"] and bench.selected() == [], "and picked nothing"


def test_the_walkers_world_is_built_from_what_the_engine_holds(
        bench: SelectionBench, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review 1, P2-3: entering walk mode builds no mesh a second time — the world is
    made of the parts the sink holds, and equals the world the builders would make —
    and a date change (plants regrow; the walker walks through plants) keeps it."""
    import numpy as np

    from open_garden_planner.core.scene3d.walk import build_world

    walk_ready(bench)
    drop(bench.view, "TREE:species=apple tree", QPointF(2500.0, 1200.0))
    bench.settle(150)
    workspace = bench.workspace
    controller = workspace.controller
    registry = controller.sync.registry
    original = registry.builder_for
    asked: list[str] = []

    def counting(kind: str) -> Any:
        asked.append(kind)
        return original(kind)

    monkeypatch.setattr(registry, "builder_for", counting)
    workspace._camera._pose = type(workspace.camera.pose)((2500.0, 1500.0), 2000.0, 0.0, 45.0)  # noqa: SLF001
    assert workspace.set_walking(True) is True
    assert asked == [], "nothing was built a second time"
    world = workspace.walk.world
    bounds = controller.plan_bounds()
    expected = build_world(controller.sync.records, bounds.max_east, bounds.max_north,
                           parts_of=lambda record: original(record.kind)(record))
    assert world.solid_ids == expected.solid_ids
    assert np.array_equal(world.segments, expected.segments)
    snapshots = controller.snapshot_count
    bench.clock.set_date(date(2026, 3, 1))
    bench.qtbot.waitUntil(lambda: controller.snapshot_count > snapshots and not controller.dirty,
                          timeout=5000)
    bench.settle(80)
    assert workspace.walk.world is world, "a regrown plant is no obstacle: the world is kept"


def test_the_toggle_leaves_too_and_walk_mode_can_be_entered_again(bench: SelectionBench) -> None:
    camera = walk_ready(bench)
    workspace = bench.workspace
    pose = camera.pose
    assert workspace.set_walking(True) is True
    first = workspace.walk
    workspace.walk_action.trigger()                   # the toggle, off
    assert not workspace.walking and bench.host.cameras[-1] == (pose.eye, pose.target_scene, FOV_DEG)
    assert workspace.set_walking(True) is True and workspace.walk is first
    assert len(bench.host.filters) == 2, "the filter is installed once"
    assert workspace.set_walking(True) is True, "asked twice: still walking, nothing restarted"
    assert workspace.set_walking(False) is False and workspace.set_walking(False) is False


def test_hiding_and_showing_the_pane_while_walking_keeps_the_walker(bench: SelectionBench) -> None:
    """Gate G7: Plan mode and back — the walker is where it was, looking where it
    looked, and the engine is shown its view again; a key held when the pane went
    does not walk on."""
    walk_ready(bench)
    workspace, host = bench.workspace, bench.host
    workspace.set_walking(True)
    bench.mouse(QEvent.Type.MouseButtonPress, 100.0, 100.0)
    bench.mouse(QEvent.Type.MouseMove, 150.0, 100.0)
    bench.mouse(QEvent.Type.MouseButtonRelease, 150.0, 100.0)
    bench.key(Qt.Key.Key_W)
    bench.settle(60)
    workspace.set_mode(PLAN)
    state = workspace.walk.state
    assert workspace.walking and workspace.walk.moving is False, "every key was let go"
    bench.settle(150)
    assert workspace.walk.state == state
    sent = len(host.cameras)
    workspace.set_mode(SPLIT)
    bench.settle(60)
    assert workspace.walking and workspace.walk.state == state
    assert len(host.cameras) > sent and host.cameras[-1][2] == WALK_FOV_DEG
    assert host.cameras[-1][0][:2] == state.shown
    bench.settle(150)
    assert workspace.walk.state == state, "W was held when the pane went: it does not walk on"


def test_the_eye_height_presets_move_the_eye_and_are_kept(bench: SelectionBench) -> None:
    walk_ready(bench)
    workspace, host = bench.workspace, bench.host
    actions = workspace.eye_height_actions          # the Walk button's menu
    assert workspace._walk_button.menu() is not None  # noqa: SLF001
    assert [action.data() for action in actions] == list(EYE_HEIGHTS_CM)
    assert actions[0].text() == "Adult – 1.65 m" and actions[2].text() == "Child – 1.10 m"
    actions[2].trigger()                               # chosen BEFORE walking
    assert [action.isChecked() for action in actions] == [False, False, True]
    workspace.set_walking(True)
    assert host.cameras[-1][0][2] == 110.0
    actions[1].trigger()
    assert host.cameras[-1][0][2] == 150.0 == host.cameras[-1][1][2]
    workspace.set_walking(False)
    workspace.set_walking(True)
    assert host.cameras[-1][0][2] == 150.0, "kept for the session"
    with pytest.raises(ValueError, match="one of"):
        workspace.set_eye_height(172.0)


def test_a_walk_starts_on_free_ground_and_stops_at_what_is_drawn(bench: SelectionBench) -> None:
    """The walker's world is made of the records the engine was sent, with the meshes
    the registry builds: a raised bed blocks at its planks."""
    bed = bench.item(2000.0, 1500.0)                   # 300 x 200 at (2000..2300, 1500..1700)
    bench.open3d()
    workspace = bench.workspace
    camera = workspace.camera
    camera.pan(2150.0 - camera.goal.target[0], 0.0)
    camera.snap()
    centre = bed.sceneBoundingRect().center()
    workspace._camera._pose = type(camera.pose)(  # noqa: SLF001 - look at the middle of the bed
        (centre.x(), centre.y()), camera.pose.distance_cm, 0.0, camera.pose.pitch_deg)
    assert workspace.set_walking(True) is True
    world, state = workspace.walk.world, workspace.walk.state
    assert world.solid_ids == (str(bed.item_id),)
    from open_garden_planner.core.scene3d.walk import is_free

    assert is_free(world, *state.shown), "moved off the bed to the nearest free ground"
    rect = bed.sceneBoundingRect()
    outside = (state.shown[0] < rect.left() or state.shown[0] > rect.right()
               or state.shown[1] < rect.top() or state.shown[1] > rect.bottom())
    assert outside


def test_an_edit_while_walking_rebuilds_the_walkers_world(bench: SelectionBench) -> None:
    walk_ready(bench)
    workspace = bench.workspace
    workspace.set_walking(True)
    before = workspace.walk.world
    spot = workspace.walk.state.shown
    wall = bench.item(spot[0] - 150.0, spot[1] - 100.0)        # dropped right onto the walker
    bench.settle(120)
    after = workspace.walk.world
    assert after is not before and str(wall.item_id) in after.solid_ids
    from open_garden_planner.core.scene3d.walk import is_free

    assert workspace.walking and is_free(after, *workspace.walk.state.shown)
    assert workspace.walk.state.shown != spot, "it was moved off the new solid"
    wall.setSelected(True)                                     # a selection is no edit
    bench.settle(80)
    assert workspace.walk.world is after


def test_reset_view_and_a_new_document_leave_walk_mode(bench: SelectionBench) -> None:
    walk_ready(bench)
    workspace = bench.workspace
    workspace.set_walking(True)
    workspace.reset_view()
    assert not workspace.walking and not workspace.walk_action.isChecked()
    bench.qtbot.waitUntil(lambda: not workspace.camera.moving, timeout=5000)
    assert bench.host.cameras[-1][2] == FOV_DEG
    workspace.set_walking(True)
    bench.scene.clear()                     # CanvasScene.document_replaced tells it
    assert not workspace.walking
    bench.item(700.0, 700.0)
    bench.settle(200)
    assert bench.host.cameras[-1][2] == FOV_DEG, "the new document is framed by the orbit camera"


def test_a_click_still_selects_while_walking(bench: SelectionBench) -> None:
    walk_ready(bench)
    a = next(item for item in bench.scene.items() if isinstance(item, RectangleItem))
    workspace = bench.workspace
    workspace.set_walking(True)
    state = workspace.walk.state
    bench.click(a)
    assert bench.selected() == [a] and bench.host.frames_taken == ["pick"]
    assert workspace.walking and workspace.walk.state == state, "a click is not a look"
    bench.click()
    assert bench.selected() == []


def test_walk_mode_needs_a_running_view_and_free_ground(bench: SelectionBench) -> None:
    workspace = bench.workspace
    assert workspace.walk_action.isEnabled() is False, "no 3D yet: nothing to walk in"
    assert workspace.set_walking(True) is False and workspace.walk is None
    slab = RectangleItem(-500.0, -500.0, 6000.0, 4000.0, object_type=ObjectType.RAISED_BED,
                         layer_id=bench.scene.active_layer.id)
    bench.commands.execute(CreateItemCommand(bench.scene, slab, "slab"))   # covers the whole plan
    bench.open3d()
    assert workspace.walk_action.isEnabled() is True
    workspace.walk_action.trigger()
    assert not workspace.walking and not workspace.walk_action.isChecked()
    assert workspace.status_text() == "There is no free ground to walk on."
    assert bench.host.cameras[-1][2] == FOV_DEG


# wall-clock: the distance is checked against the time W was really held, so it runs in
# the serial `-m perf -n 0` step, not beside the default run's workers (ADR-058)
@pytest.mark.perf
def test_the_walker_walks_at_walking_pace_on_the_workspaces_timer(bench: SelectionBench) -> None:
    """End to end through Qt's timer: W held for about half a second moves the walker
    about 70 cm ahead (the timer's own jitter is the tolerance)."""
    import time as stopwatch

    walk_ready(bench)
    workspace = bench.workspace
    camera = workspace.camera
    workspace._camera._pose = type(camera.pose)((2500.0, 1500.0), 2000.0, 0.0, 45.0)  # noqa: SLF001
    workspace.set_walking(True)
    start = workspace.walk.state.shown
    began = stopwatch.perf_counter()
    bench.key(Qt.Key.Key_W)
    bench.settle(500)
    bench.key(Qt.Key.Key_W, down=False)
    held = stopwatch.perf_counter() - began
    walked = workspace.walk.state.shown[1] - start[1]
    assert walked == pytest.approx(WALK_SPEED_CM_S * held, abs=WALK_SPEED_CM_S * 0.12)
    assert workspace.walk.state.shown[0] == pytest.approx(start[0], abs=1e-6)
    assert WALKER_RADIUS_CM < walked < 200.0
