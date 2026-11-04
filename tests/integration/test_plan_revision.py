"""The plan revision of the canvas scene (Phase 17 L1.3, ADR-060 decision 5).

``CanvasScene.plan_revision`` is one integer that moves exactly when plan CONTENT
changed, ``plan_changed`` says so at once, and ``note_plan_changed()`` is the one
nudge for a writer that goes round the scene's chokepoints. The 3D pipeline starts
its passes from it — and from nothing a mere repaint does
(``test_view3d_sync_controller.py``, ``test_view3d_plan_revision.py``).

Here: the scene alone, with real items and the real undo stack. What moves the
revision, what does not, and the two censuses that keep a new item type and a new
handle from forgetting to announce.
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QLineF, QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
)

from open_garden_planner.core.commands import (
    CommandManager,
    CreateItemCommand,
    DeleteItemsCommand,
    GroupCommand,
    MoveItemsCommand,
    UngroupCommand,
)
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items import garden_item
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.garden_item import GardenItemMixin
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

ITEMS = Path(garden_item.__file__).resolve().parent


class Plan:
    """A canvas with a bed and a tree on it, and the revisions its scene announced."""

    def __init__(self, view: CanvasView, qtbot: Any) -> None:
        self.view, self.qtbot = view, qtbot
        self.scene: CanvasScene = view.scene()
        self.commands = view.command_manager
        self.announced: list[int] = []
        self.scene.plan_changed.connect(self.announced.append)
        self.bed = RectangleItem(400.0, 300.0, 300.0, 200.0, object_type=ObjectType.RAISED_BED,
                                 layer_id=self.scene.active_layer.id)
        self.tree = CircleItem(1500.0, 900.0, 120.0, object_type=ObjectType.TREE,
                               layer_id=self.scene.active_layer.id)
        self.commands.execute(CreateItemCommand(self.scene, self.bed, "bed"))
        self.commands.execute(CreateItemCommand(self.scene, self.tree, "tree"))
        self.settle()

    def settle(self) -> int:
        """Let Qt deliver what it defers (the polish of new items, queued repaints)."""
        self.qtbot.wait(30)
        return self.scene.plan_revision

    def moved_by(self, act: Callable[[], Any]) -> int:
        """How far ``act`` — and whatever Qt delivers for it afterwards — moved the revision."""
        before = self.settle()
        act()
        return self.settle() - before


@pytest.fixture()
def plan(canvas: CanvasView, qtbot) -> Plan:
    return Plan(canvas, qtbot)


# ── the signal and the nudge ─────────────────────────────────────────────────


def test_the_nudge_moves_the_revision_by_one_and_says_so_at_once(plan: Plan) -> None:
    before, heard = plan.scene.plan_revision, len(plan.announced)
    plan.scene.note_plan_changed()
    assert plan.scene.plan_revision == before + 1
    assert plan.announced[heard:] == [before + 1], "synchronously, with the new revision"
    plan.scene.note_plan_changed()
    plan.scene.note_plan_changed()
    assert plan.announced[heard:] == [before + 1, before + 2, before + 3]


def test_a_new_scene_starts_at_zero_and_the_revision_only_grows(qtbot) -> None:
    scene = CanvasScene()
    assert scene.plan_revision == 0
    seen = [scene.plan_revision]
    scene.plan_changed.connect(seen.append)
    scene.resize_canvas(100.0, 100.0)
    scene.clear()
    scene.note_plan_changed()
    assert seen == sorted(set(seen)) and len(seen) == 4


def test_the_module_helper_tells_a_canvas_scene_and_nobody_else(plan: Plan) -> None:
    """``garden_item.note_plan_changed(scene)``: for a caller that holds "a scene,
    maybe" — an item that may be in none, or in a plain ``QGraphicsScene``."""
    before = plan.scene.plan_revision
    garden_item.note_plan_changed(plan.scene)
    assert plan.scene.plan_revision == before + 1
    garden_item.note_plan_changed(None)
    garden_item.note_plan_changed(QGraphicsScene())
    assert plan.scene.plan_revision == before + 1


# ── what moves it ────────────────────────────────────────────────────────────


def _layer_of(plan: Plan) -> Layer:
    return plan.scene.active_layer


EDITS: dict[str, Callable[[Plan], Any]] = {
    "an item is added by a command": lambda p: p.commands.execute(CreateItemCommand(
        p.scene, RectangleItem(900.0, 900.0, 100.0, 100.0, object_type=ObjectType.RAISED_BED,
                               layer_id=p.scene.active_layer.id), "bed")),
    "an item is added directly": lambda p: p.scene.addItem(
        CircleItem(2500.0, 900.0, 60.0, object_type=ObjectType.SHRUB,
                   layer_id=p.scene.active_layer.id)),
    "an item is removed by a command": lambda p: p.commands.execute(
        DeleteItemsCommand(p.scene, [p.tree])),
    "an item is removed directly": lambda p: p.scene.removeItem(p.tree),
    "an item is moved by a command": lambda p: p.commands.execute(
        MoveItemsCommand([p.bed], QPointF(40.0, 10.0))),
    "an item is moved directly (a drag)": lambda p: p.bed.setPos(p.bed.pos() + QPointF(5.0, 0.0)),
    "an item is turned": lambda p: p.bed.setRotation(30.0),
    "an item is scaled": lambda p: p.bed.setScale(1.5),
    "an item is hidden": lambda p: p.bed.setVisible(False),
    "an item is restacked": lambda p: p.bed.setZValue(p.bed.zValue() + 3.0),
    "an undo": lambda p: p.commands.undo(),
    "an undo and a redo": lambda p: (p.commands.undo(), p.commands.redo()),
    "items are grouped": lambda p: p.commands.execute(GroupCommand(p.scene, [p.bed, p.tree])),
    "a layer is hidden": lambda p: p.scene.update_layer_visibility(_layer_of(p).id, False),
    "a layer is locked": lambda p: p.scene.update_layer_lock(_layer_of(p).id, True),
    "a layer is made translucent": lambda p: p.scene.update_layer_opacity(_layer_of(p).id, 0.4),
    "a layer is added": lambda p: p.scene.add_layer(Layer(name="Trees", z_order=1)),
    "the layers are replaced": lambda p: p.scene.set_layers([Layer(name="Only", z_order=0)]),
    "the canvas is resized": lambda p: p.scene.resize_canvas(8000.0, 6000.0),
    "the scene is cleared": lambda p: p.scene.clear(),
    "the nudge": lambda p: p.scene.note_plan_changed(),
}


@pytest.mark.parametrize("edit", list(EDITS), ids=[name.replace(" ", "_") for name in EDITS])
def test_an_edit_moves_the_revision(plan: Plan, edit: str) -> None:
    heard = len(plan.announced)
    assert plan.moved_by(lambda: EDITS[edit](plan)) >= 1, edit
    assert len(plan.announced) > heard, "and plan_changed said so"


def test_a_group_that_moves_announces_for_its_members(plan: Plan) -> None:
    """Qt tells the MEMBERS of a moved group nothing — their own position did not
    change — so the group has an ``itemChange`` of its own."""
    plan.commands.execute(GroupCommand(plan.scene, [plan.bed, plan.tree]))
    group = next(item for item in plan.scene.items() if isinstance(item, GroupItem))
    assert plan.moved_by(lambda: group.setPos(group.pos() + QPointF(100.0, 0.0))) == 1
    assert plan.moved_by(lambda: group.setRotation(15.0)) >= 1
    assert plan.moved_by(lambda: group.setVisible(False)) >= 1
    assert plan.moved_by(lambda: plan.commands.execute(UngroupCommand(plan.scene, group))) >= 1


def test_a_journal_pin_is_part_of_the_plan(plan: Plan) -> None:
    """A pin is a ``QGraphicsObject``; it got an ``itemChange`` for this. It is still
    placed where it was put, in the scene it was added to."""
    from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem

    pin = JournalPinItem(100.0, 150.0, "note-1", layer_id=plan.scene.active_layer.id)
    assert plan.moved_by(lambda: plan.scene.addItem(pin)) >= 1
    assert pin.scene() is plan.scene and pin.pos() == QPointF(100.0, 150.0)
    assert plan.moved_by(lambda: pin.setPos(220.0, 260.0)) == 1
    assert plan.moved_by(lambda: pin.setSelected(True)) == 0
    assert plan.moved_by(lambda: plan.scene.removeItem(pin)) >= 1
    assert pin.scene() is None


def test_an_item_that_changes_scenes_tells_both(qtbot) -> None:
    first, second = CanvasScene(), CanvasScene()
    item = RectangleItem(0.0, 0.0, 100.0, 100.0, object_type=ObjectType.RAISED_BED)
    first.addItem(item)
    qtbot.wait(20)
    before = first.plan_revision, second.plan_revision
    second.addItem(item)  # Qt takes it out of the first scene itself
    assert first.plan_revision > before[0] and second.plan_revision > before[1]


def test_every_command_on_the_undo_stack_moves_it_whatever_the_command_does(plan: Plan) -> None:
    """A command that writes ``metadata`` only repaints nothing and moves no item: the
    stack's own signal is the announcement (``CanvasScene.set_command_manager``)."""
    assert plan.moved_by(plan.commands.stack_changed.emit) == 1


def test_a_scene_follows_the_stack_it_was_handed_last(qtbot) -> None:
    scene = CanvasScene()
    first, second = CommandManager(), CommandManager()
    scene.set_command_manager(first)
    scene.set_command_manager(first)   # again: one connection, not two
    first.stack_changed.emit()
    assert scene.plan_revision == 1
    scene.set_command_manager(second)
    first.stack_changed.emit()
    assert scene.plan_revision == 1, "the stack it no longer has is not listened to"
    second.stack_changed.emit()
    assert scene.plan_revision == 2 and scene.get_command_manager() is second
    scene.set_command_manager(None)
    second.stack_changed.emit()
    assert scene.plan_revision == 2


# ── what does NOT move it: a repaint is not an edit ──────────────────────────


def _preview(plan: Plan) -> None:
    """What a drawing tool does under the mouse: plain Qt items, added, reshaped, removed."""
    rubber = QGraphicsRectItem(QRectF(100.0, 100.0, 10.0, 10.0))
    line = QGraphicsLineItem(QLineF(0.0, 0.0, 50.0, 50.0))
    plan.scene.addItem(rubber)
    plan.scene.addItem(line)
    for step in range(20):
        rubber.setRect(QRectF(100.0, 100.0, 10.0 + step, 10.0 + step))
        line.setLine(QLineF(0.0, 0.0, 50.0 + step, 50.0))
        rubber.setPos(float(step), 0.0)
    plan.scene.removeItem(rubber)
    plan.scene.removeItem(line)


def _overlay(plan: Plan) -> None:
    """A derived overlay (the sun's shadow, the heat map): added, repainted, hidden."""
    shadow = QGraphicsEllipseItem(QRectF(0.0, 0.0, 400.0, 200.0))
    shadow.setBrush(QBrush(QColor(0, 0, 0, 60)))
    shadow.setZValue(900.0)
    plan.scene.addItem(shadow)
    shadow.setRect(QRectF(10.0, 0.0, 420.0, 200.0))
    shadow.setVisible(False)


REPAINTS: dict[str, Callable[[Plan], Any]] = {
    "a selection": lambda p: p.bed.setSelected(True),
    "a selection and a clear": lambda p: (p.bed.setSelected(True), p.tree.setSelected(True),
                                          p.scene.clearSelection()),
    "an item repainted": lambda p: p.bed.update(),
    "the scene repainted": lambda p: p.scene.update(),
    "a tool's preview": _preview,
    "a derived overlay": _overlay,
    "an opacity": lambda p: p.bed.setOpacity(0.5),
    "a layer's opacity previewed (a slider drag)": lambda p: p.scene.preview_layer_opacity(
        _layer_of(p).id, 0.3),
    "the active layer": lambda p: p.scene.set_active_layer(_layer_of(p)),
    "labels switched off": lambda p: p.scene.set_labels_visible(False),
    "painted shadows switched off": lambda p: p.scene.set_shadows_enabled(False),
    "a metadata write nobody announced": lambda p: p.bed.metadata.update(note="x"),
}
#: … of which these change nothing a bed and a tree without labels would paint.
NOT_EVEN_A_REPAINT = frozenset({"the active layer", "labels switched off",
                                "a metadata write nobody announced"})


@pytest.mark.parametrize("repaint", list(REPAINTS), ids=[name.replace(" ", "_").replace("'", "")
                                                          for name in REPAINTS])
def test_a_repaint_does_not_move_the_revision(plan: Plan, repaint: str) -> None:
    changed: list[int] = []
    plan.scene.changed.connect(lambda *_regions: changed.append(1))
    assert plan.moved_by(lambda: REPAINTS[repaint](plan)) == 0, repaint
    if repaint not in NOT_EVEN_A_REPAINT:
        assert changed, "… although the canvas WAS repainted (QGraphicsScene.changed fired)"


def test_qt_polishing_a_new_item_is_not_a_second_edit(plan: Plan) -> None:
    """A turn of the event loop after an item was added Qt polishes it and tells it
    "you are visible now" although it was visible all along. Announced, that notice
    cost a second whole-plan pass per added item, a turn late (measured)."""
    notices: list[tuple[str, bool]] = []
    item = CircleItem(2600.0, 1200.0, 80.0, object_type=ObjectType.SHRUB,
                      layer_id=plan.scene.active_layer.id)
    original = type(item).itemChange

    def spy(self: Any, change: Any, value: Any) -> Any:
        if self is item and change == garden_item._CHANGE.ItemVisibleHasChanged:
            notices.append((change.name, bool(value)))
        return original(self, change, value)

    type(item).itemChange = spy  # type: ignore[method-assign]
    try:
        plan.commands.execute(CreateItemCommand(plan.scene, item, "shrub"))
        at_once = plan.scene.plan_revision
        plan.qtbot.wait(40)
        assert notices == [("ItemVisibleHasChanged", True)], "Qt did send the notice"
        assert plan.scene.plan_revision == at_once, "… and it moved nothing"
        # a REAL change of visibility is announced, in both directions
        assert plan.moved_by(lambda: item.setVisible(False)) == 1
        assert plan.moved_by(lambda: item.setVisible(True)) == 1
        assert plan.moved_by(lambda: item.setVisible(True)) == 0, "shown, and it was"
    finally:
        type(item).itemChange = original  # type: ignore[method-assign]


def test_an_item_outside_any_scene_announces_to_nobody() -> None:
    item = RectangleItem(0.0, 0.0, 100.0, 100.0, object_type=ObjectType.RAISED_BED)
    item.setPos(10.0, 10.0)          # no scene: nothing to tell, nothing raised
    item.setVisible(False)
    plain = QGraphicsScene()
    plain.addItem(item)              # a scene without a revision
    item.setPos(20.0, 20.0)
    plain.removeItem(item)


# ── the censuses: nobody forgets to announce ─────────────────────────────────


def _classes(path: Path) -> list[ast.ClassDef]:
    return [node for node in ast.parse(path.read_text(encoding="utf-8")).body
            if isinstance(node, ast.ClassDef)]


def _method(node: ast.ClassDef, name: str) -> ast.FunctionDef | None:
    return next((child for child in node.body
                 if isinstance(child, ast.FunctionDef) and child.name == name), None)


def _calls(node: ast.AST) -> list[str]:
    names = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            function = child.func
            names.append(function.attr if isinstance(function, ast.Attribute)
                         else getattr(function, "id", ""))
    return names


def _first_statement_calls(function: ast.FunctionDef) -> list[str]:
    body = [statement for statement in function.body
            if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))]
    return _calls(body[0]) if body else []


def test_every_plan_item_class_announces_through_the_one_hook() -> None:
    """Every ``itemChange`` in ``ui/canvas/items`` calls the hook FIRST
    (``handle_item_change``: the paint cache and the plan revision), and every garden
    item class of the running app HAS such an ``itemChange`` — a new item type cannot
    forget it, and nobody calls the cache half alone any more. The journal pin calls
    the announcing half only: it is drawn at a constant pixel size and was never
    cached."""
    hooked: dict[str, str] = {}
    for path in sorted(ITEMS.glob("*.py")):
        for node in _classes(path):
            change = _method(node, "itemChange")
            if change is None:
                continue
            hook = "announce_plan_change" if node.name == "JournalPinItem" else "handle_item_change"
            assert _first_statement_calls(change) == [hook], (
                f"{path.name}: {node.name}.itemChange must call the hook first")
            hooked[node.name] = path.name
    assert sorted(hooked) == [
        "ArcItem", "BezierItem", "CalloutItem", "CircleItem", "EllipseItem", "GroupItem",
        "JournalPinItem", "PolygonItem", "PolylineItem", "RectangleItem", "TextItem"], hooked

    # every garden item class the running app knows resolves itemChange to one of those
    # (a class without one of its own — the smart symbol — inherits its parent's)
    def subclasses(cls: type) -> set[type]:
        found = set(cls.__subclasses__())
        return found | {deeper for sub in found for deeper in subclasses(sub)}

    import open_garden_planner.ui.canvas.items  # noqa: F401 - loads every item module
    from open_garden_planner.ui.canvas.items import smart_symbol_item  # noqa: F401

    garden = {cls for cls in subclasses(GardenItemMixin)
              if cls.__module__.startswith("open_garden_planner.")}
    assert sorted(cls.__name__ for cls in garden) == [
        "CalloutItem", "CircleItem", "EllipseItem", "GroupItem", "JournalPinItem", "PolygonItem",
        "PolylineItem", "RectangleItem", "SmartSymbolItem", "TextItem"]
    for cls in garden:
        owner = next(base for base in cls.__mro__ if "itemChange" in vars(base))
        assert owner.__name__ in hooked, f"{cls.__name__} takes itemChange from {owner.__name__}"
    # and the cache half is called from the hook alone
    callers = [path.name for path in sorted(ITEMS.glob("*.py"))
               for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
               if isinstance(node, ast.FunctionDef) and node.name == "itemChange"
               and "handle_selection_change_for_cache" in _calls(node)]
    assert callers == []


def test_every_handle_that_edits_a_geometry_announces_each_move() -> None:
    """Qt has no ``itemChange`` for a geometry. A handle drag changes one on every
    mouse move, so every handle's ``mouseMoveEvent`` in ``resize_handle.py`` says so —
    all but the rotation handle's, whose ``setRotation`` Qt announces itself."""
    modules = [ITEMS / "resize_handle.py", ITEMS / "vertex_handles.py"]
    movers = {node.name: _method(node, "mouseMoveEvent")
              for module in modules for node in _classes(module)}
    movers = {name: method for name, method in movers.items() if method is not None}
    assert sorted(movers) == ["CurveControlHandle", "RectCornerHandle", "ResizeHandle",
                              "RotationHandle", "VertexHandle"]
    for name, method in movers.items():
        announces = "_announce_live_edit" in _calls(method)
        assert announces is (name != "RotationHandle"), name


def test_a_handle_drag_moves_the_revision_on_every_mouse_move(plan: Plan) -> None:
    """Through the real resize handle of a selected bed: press, three moves, release."""
    from unittest.mock import MagicMock

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsSceneMouseEvent

    from open_garden_planner.ui.canvas.items.resize_handle import ResizeHandle

    plan.bed.setSelected(True)
    plan.settle()
    handle = next(child for child in plan.bed.childItems() if isinstance(child, ResizeHandle))
    start = handle.scenePos()

    def event(at: QPointF) -> MagicMock:
        mouse = MagicMock(spec=QGraphicsSceneMouseEvent)
        mouse.button.return_value = Qt.MouseButton.LeftButton
        mouse.scenePos.return_value = at
        mouse.modifiers.return_value = Qt.KeyboardModifier.NoModifier
        return mouse

    handle.mousePressEvent(event(start))
    rect_before = plan.bed.rect()
    for step in (1, 2, 3):
        before = plan.scene.plan_revision
        handle.mouseMoveEvent(event(start + QPointF(15.0 * step, 10.0 * step)))
        assert plan.scene.plan_revision > before, f"move {step} was announced"
    assert plan.bed.rect() != rect_before, "the drag did change the geometry"
    before = plan.scene.plan_revision
    handle.mouseReleaseEvent(event(start + QPointF(45.0, 30.0)))
    assert plan.scene.plan_revision > before, "the release is a command"


def test_a_polygon_vertex_drag_is_announced_too(plan: Plan) -> None:
    from unittest.mock import MagicMock

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QGraphicsSceneMouseEvent

    from open_garden_planner.ui.canvas.items.resize_handle import VertexHandle

    hedge = PolygonItem([QPointF(2000.0, 200.0), QPointF(2400.0, 220.0), QPointF(2420.0, 620.0),
                         QPointF(2040.0, 660.0)], object_type=ObjectType.HEDGE_POLYGON,
                        layer_id=plan.scene.active_layer.id)
    plan.commands.execute(CreateItemCommand(plan.scene, hedge, "hedge"))
    hedge.setSelected(True)
    hedge.enter_vertex_edit_mode()
    plan.settle()
    handle = next(child for child in hedge.childItems() if isinstance(child, VertexHandle))
    mouse = MagicMock(spec=QGraphicsSceneMouseEvent)
    mouse.button.return_value = Qt.MouseButton.LeftButton
    mouse.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    mouse.scenePos.return_value = handle.scenePos()
    handle.mousePressEvent(mouse)
    before = plan.scene.plan_revision
    mouse.scenePos.return_value = handle.scenePos() + QPointF(60.0, 40.0)
    handle.mouseMoveEvent(mouse)
    assert plan.scene.plan_revision > before
