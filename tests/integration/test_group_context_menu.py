"""Integration tests: Group / Ungroup in every groupable item's context menu (#674).

Grouping was reachable only through ``Ctrl+G`` before this change, and the
inverse direction was offered by a group's own menu — a one-sided, undiscoverable
feature. Both directions now come from one shared seam
(``ui/canvas/items/group_menu.py``) that reads the *selection* at menu-open time
and dispatches through the view's keyboard path.

These tests drive the REAL ``contextMenuEvent`` of every item type and the REAL
undo stack; ``QMenu.exec`` is monkeypatched because a popup would block.
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

from open_garden_planner.core.commands import GroupCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.arc_item import ArcItem
from open_garden_planner.ui.canvas.items.bezier_item import BezierItem
from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.construction_item import (
    ConstructionCircleItem,
    ConstructionLineItem,
)
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.journal_pin_item import JournalPinItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.smart_symbol_item import SmartSymbolItem
from open_garden_planner.ui.canvas.items.text_item import TextItem

GROUP = "Group"
UNGROUP = "Ungroup"


# ---------------------------------------------------------------------------
# Factories — one per item type whose context menu must offer the entries.
# ---------------------------------------------------------------------------


def _rectangle(layer_id=None) -> RectangleItem:
    return RectangleItem(
        0, 0, 100, 60, object_type=ObjectType.GENERIC_RECTANGLE, layer_id=layer_id
    )


def _polygon(layer_id=None) -> PolygonItem:
    vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 60), QPointF(0, 60)]
    return PolygonItem(vertices, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)


def _polyline(layer_id=None) -> PolylineItem:
    points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 60)]
    return PolylineItem(points, object_type=ObjectType.FENCE, layer_id=layer_id)


def _circle(layer_id=None) -> CircleItem:
    return CircleItem(0, 0, 30, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_id)


def _ellipse(layer_id=None) -> EllipseItem:
    return EllipseItem(0, 0, 100, 60, object_type=ObjectType.GENERIC_ELLIPSE, layer_id=layer_id)


def _arc(layer_id=None) -> ArcItem:
    return ArcItem(QPointF(0, 0), 50, 0, 90, layer_id=layer_id)


def _bezier(layer_id=None) -> BezierItem:
    anchors = [QPointF(0, 0), QPointF(100, 0)]
    handles = [QPointF(0, 0), QPointF(100, 0)]
    return BezierItem(anchors, handles, handles, layer_id=layer_id)


def _text(layer_id=None) -> TextItem:
    return TextItem(0, 0, content="label", layer_id=layer_id)


def _callout(layer_id=None) -> CalloutItem:
    return CalloutItem(QPointF(0, 0), QPointF(50, 50), content="note", layer_id=layer_id)


def _journal_pin(layer_id=None) -> JournalPinItem:
    return JournalPinItem(0, 0, "note-1", layer_id=layer_id)


def _construction_line(layer_id=None) -> ConstructionLineItem:
    return ConstructionLineItem(QPointF(0, 0), QPointF(100, 0))


def _construction_circle(layer_id=None) -> ConstructionCircleItem:
    return ConstructionCircleItem(0, 0, 50)


def _group(layer_id=None) -> GroupItem:
    group = GroupItem(layer_id=layer_id)
    group.addToGroup(
        RectangleItem(0, 0, 40, 40, object_type=ObjectType.GENERIC_RECTANGLE)
    )
    return group


def _smart_symbol(layer_id=None) -> SmartSymbolItem:
    return SmartSymbolItem("raised_bed_rows", 1, {"rows": 4}, layer_id=layer_id)





#: Every item type whose context menu must offer the entries.
FACTORIES = [
    _rectangle,
    _polygon,
    _polyline,
    _circle,
    _ellipse,
    _arc,
    _bezier,
    _text,
    _callout,
    _journal_pin,
    _construction_line,
    _construction_circle,
    _group,
    _smart_symbol,
]

# (factory, labels with one foreign object also selected, labels when alone)
ITEM_CASES = [
    pytest.param(_rectangle, {GROUP}, set(), id="RectangleItem"),
    pytest.param(_polygon, {GROUP}, set(), id="PolygonItem"),
    pytest.param(_polyline, {GROUP}, set(), id="PolylineItem"),
    pytest.param(_circle, {GROUP}, set(), id="CircleItem"),
    pytest.param(_ellipse, {GROUP}, set(), id="EllipseItem"),
    pytest.param(_arc, {GROUP}, set(), id="ArcItem"),
    pytest.param(_bezier, {GROUP}, set(), id="BezierItem"),
    pytest.param(_text, {GROUP}, set(), id="TextItem"),
    pytest.param(_callout, {GROUP}, set(), id="CalloutItem"),
    pytest.param(_journal_pin, {GROUP}, set(), id="JournalPinItem"),
    pytest.param(_construction_line, {GROUP}, set(), id="ConstructionLineItem"),
    pytest.param(_construction_circle, {GROUP}, set(), id="ConstructionCircleItem"),
    pytest.param(_group, {GROUP, UNGROUP}, {UNGROUP}, id="GroupItem"),
    pytest.param(_smart_symbol, {GROUP}, set(), id="SmartSymbolItem"),
]


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _event() -> MagicMock:
    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    event.screenPos.return_value = QPoint(0, 0)
    return event


def _open_menu(item, monkeypatch, *, choose: str | None = None) -> QMenu:
    """Run the real contextMenuEvent with a non-blocking QMenu.exec."""
    captured: list[QMenu] = []

    def fake_exec(menu_self, *_args, **_kwargs):
        captured.append(menu_self)
        if choose is None:
            return None
        for action in menu_self.actions():
            if action.text() == choose:
                return action
        return None

    monkeypatch.setattr(QMenu, "exec", fake_exec)
    item.contextMenuEvent(_event())
    assert captured, f"{type(item).__name__}.contextMenuEvent never opened a menu"
    return captured[-1]


def _labels(menu: QMenu) -> set[str]:
    return {a.text() for a in menu.actions() if not a.isSeparator()}


def _canvas(qtbot) -> CanvasView:
    scene = CanvasScene(width_cm=2000, height_cm=2000)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    return view


def _stack_depth(view: CanvasView) -> int:
    return len(view.command_manager._undo_stack)


# ---------------------------------------------------------------------------
# Menu matrix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory,with_peer,alone", ITEM_CASES)
def test_menu_follows_the_selection(factory, with_peer, alone, qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    item = factory(layer_id=scene.active_layer.id)
    peer = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(item)
    scene.addItem(peer)

    item.setSelected(True)
    alone_labels = _labels(_open_menu(item, monkeypatch))
    assert alone_labels & {GROUP, UNGROUP} == alone

    peer.setSelected(True)
    pair_labels = _labels(_open_menu(item, monkeypatch))
    assert pair_labels & {GROUP, UNGROUP} == with_peer


def test_a_lone_object_offers_nothing(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    rect = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(rect)
    rect.setSelected(True)

    assert _labels(_open_menu(rect, monkeypatch)) & {GROUP, UNGROUP} == set()


_SHAPE_FACTORIES = [_rectangle, _polygon, _polyline, _circle, _ellipse]


@pytest.mark.parametrize(
    "factory", _SHAPE_FACTORIES, ids=[f.__name__ for f in _SHAPE_FACTORIES]
)
def test_shape_menu_delete_is_the_undoable_view_delete(
    factory, qtbot, monkeypatch
) -> None:
    """A context-menu Delete must go through ``_delete_selected_items``.

    The five shape menus used to call ``scene.removeItem`` directly, which
    bypassed the undo stack and left a HOUSE's metadata-linked roof ridge in
    the plan (round-5 review of #690).
    """
    view = _canvas(qtbot)
    item = factory(layer_id=view.scene().active_layer.id)
    view.scene().addItem(item)
    item.setSelected(True)

    _open_menu(item, monkeypatch, choose="Delete")

    assert item.scene() is None
    assert view.command_manager.can_undo, "the menu delete bypassed the command stack"
    view.command_manager.undo()
    assert item.scene() is view.scene()


@pytest.mark.parametrize("factory,with_peer,alone", ITEM_CASES)
def test_every_menu_routes_through_the_shared_seam(factory, with_peer, alone) -> None:
    """Structural drift guard, like the Arrange and bed-menu suites.

    A future item type that builds its own menu must call the shared builder or
    silently miss Group/Ungroup on every existing shortcut path.
    """
    item = factory()
    src = inspect.getsource(type(item).contextMenuEvent)
    assert "build_group_context_menu" in src, (
        f"{type(item).__name__}.contextMenuEvent must call the shared "
        "build_group_context_menu (issue #674)"
    )
    assert "dispatch_group_action" in src or "group_actions.dispatch" in src, (
        f"{type(item).__name__}.contextMenuEvent must dispatch the entry"
    )


def test_smart_symbol_never_offers_its_own_ungroup(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    smart = _smart_symbol(layer_id=view.scene().active_layer.id)
    view.scene().addItem(smart)
    smart.setSelected(True)

    assert UNGROUP not in _labels(_open_menu(smart, monkeypatch)), (
        "a smart symbol may be grouped but never ungrouped: its members are "
        "generated from its parameters"
    )


def test_smart_symbol_menu_still_ungroups_another_selected_group(
    qtbot, monkeypatch
) -> None:
    """The smart symbol must not hide Ungroup for a different selected group.

    ``Ctrl+Shift+G`` dissolves that group, so a stricter menu would break the
    shared-seam promise (round-6 review P2).
    """
    view = _canvas(qtbot)
    scene = view.scene()
    smart = _smart_symbol(layer_id=scene.active_layer.id)
    group = _group(layer_id=scene.active_layer.id)
    child = next(iter(group.childItems()))
    scene.addItem(smart)
    scene.addItem(group)
    smart.setSelected(True)
    group.setSelected(True)

    assert UNGROUP in _labels(_open_menu(smart, monkeypatch))
    _open_menu(smart, monkeypatch, choose=UNGROUP)

    assert group.scene() is None
    assert child.parentItem() is None


# ---------------------------------------------------------------------------
# Dispatch — Group
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", FACTORIES)
def test_group_entry_groups_the_whole_selection_in_one_undo_step(
    factory, qtbot, monkeypatch
) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    item = factory(layer_id=scene.active_layer.id)
    peer = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(item)
    scene.addItem(peer)
    item.setSelected(True)
    peer.setSelected(True)
    messages: list[str] = []
    view.status_message.connect(messages.append)

    _open_menu(item, monkeypatch, choose=GROUP)

    group = item.parentItem()
    assert isinstance(group, GroupItem), f"{type(item).__name__} was not grouped"
    assert peer.parentItem() is group
    assert _stack_depth(view) == 1, "one gesture must be one undo step"
    assert messages and messages[-1] == "Grouped 2 items"

    view.command_manager.undo()
    assert item.parentItem() is None and peer.parentItem() is None
    assert item.isSelected() and peer.isSelected()


def test_group_plus_foreign_object_nests(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    inner = _group(layer_id=scene.active_layer.id)
    foreign = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(inner)
    scene.addItem(foreign)
    inner.setSelected(True)
    foreign.setSelected(True)

    _open_menu(foreign, monkeypatch, choose=GROUP)

    outer = inner.parentItem()
    assert isinstance(outer, GroupItem) and outer is not inner
    assert foreign.parentItem() is outer
    assert _stack_depth(view) == 1

    view.command_manager.undo()
    assert inner.parentItem() is None and foreign.parentItem() is None


@pytest.mark.parametrize(
    "modifier",
    [Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier],
    ids=["ctrl", "shift"],
)
def test_a_pin_and_a_shape_multi_select_then_group(qtbot, modifier) -> None:
    """Ctrl/Shift+click must keep a selected journal pin and add the shape.

    A pin is an ``ItemIgnoresTransformations`` item; the tool's own toggle path
    is what keeps it selected, where Qt's default Ctrl press replaced the
    selection (manual test 4). The grouped pin+note still uses the one undo
    step covered elsewhere.
    """
    from open_garden_planner.core.tools.select_tool import SelectTool

    view = _canvas(qtbot)
    scene = view.scene()
    pin = _journal_pin(scene.active_layer.id)
    rect = _rectangle(scene.active_layer.id)
    scene.addItem(pin)
    scene.addItem(rect)
    pin.setPos(100, 100)
    pin.setSelected(True)

    tool = view.tool_manager.active_tool
    assert isinstance(tool, SelectTool)
    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = modifier
    centre = rect.mapToScene(rect.rect().center())

    assert tool.mouse_press(event, centre) is True
    assert pin.isSelected()
    assert rect.isSelected()

    view.group_selected()
    group = pin.parentItem()
    assert group is not None
    assert rect.parentItem() is group


def test_smart_symbol_can_be_grouped_with_another_object(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    symbol = _smart_symbol(layer_id=scene.active_layer.id)
    peer = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(symbol)
    scene.addItem(peer)
    symbol.setSelected(True)
    peer.setSelected(True)

    _open_menu(symbol, monkeypatch, choose=GROUP)

    group = symbol.parentItem()
    assert isinstance(group, GroupItem)
    assert peer.parentItem() is group
    view.command_manager.undo()
    assert symbol.parentItem() is None


# ---------------------------------------------------------------------------
# Dispatch — Ungroup
# ---------------------------------------------------------------------------


def _grouped(items, scene) -> GroupItem:
    GroupCommand(scene, items).execute()
    group = items[0].parentItem()
    assert isinstance(group, GroupItem)
    return group


def test_one_group_offers_only_ungroup_and_dissolves_one_level(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    member = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(member)
    group = _grouped([member], scene)
    group.setSelected(True)

    menu = _open_menu(group, monkeypatch)
    assert _labels(menu) & {GROUP, UNGROUP} == {UNGROUP}

    _open_menu(group, monkeypatch, choose=UNGROUP)

    assert member.parentItem() is None
    assert group.scene() is None
    assert _stack_depth(view) == 1

    view.command_manager.undo()
    assert group.scene() is scene
    assert member.parentItem() is group


def test_nested_groups_ungroup_one_level_at_a_time(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    inner_member = _rectangle(layer_id=scene.active_layer.id)
    outer_member = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(inner_member)
    scene.addItem(outer_member)
    inner = _grouped([inner_member], scene)
    outer = _grouped([inner, outer_member], scene)
    assert inner.parentItem() is outer

    outer.setSelected(True)
    _open_menu(outer, monkeypatch, choose=UNGROUP)
    # exactly one level: the inner group is top-level and still whole
    assert inner.parentItem() is None
    assert inner_member.parentItem() is inner
    assert outer_member.parentItem() is None

    inner.setSelected(True)
    _open_menu(inner, monkeypatch, choose=UNGROUP)
    assert inner_member.parentItem() is None
    assert inner.scene() is None


def test_a_just_grouped_selection_offers_ungroup_only(qtbot, monkeypatch) -> None:
    """The state every user is in right after Ctrl+G: Qt leaves the members
    flagged selected, so the menu must still see ONE top-level object (#674
    review P0; PF-CAN-36)."""
    view = _canvas(qtbot)
    scene = view.scene()
    first = _rectangle(layer_id=scene.active_layer.id)
    second = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(first)
    scene.addItem(second)
    first.setSelected(True)
    second.setSelected(True)

    view.group_selected()
    group = first.parentItem()
    assert isinstance(group, GroupItem)
    # The members are still reported as selected by Qt — that is the trap.
    assert set(scene.selectedItems()) != {group}

    labels = _labels(_open_menu(group, monkeypatch))
    assert labels & {GROUP, UNGROUP} == {UNGROUP}

    _open_menu(group, monkeypatch, choose=UNGROUP)
    assert first.parentItem() is None and second.parentItem() is None


def test_two_groups_ungroup_in_one_undo_step(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    first_member = _rectangle(layer_id=scene.active_layer.id)
    second_member = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(first_member)
    scene.addItem(second_member)
    first = _grouped([first_member], scene)
    second = _grouped([second_member], scene)
    first.setSelected(True)
    second.setSelected(True)

    menu = _open_menu(first, monkeypatch)
    assert _labels(menu) & {GROUP, UNGROUP} == {GROUP, UNGROUP}

    _open_menu(first, monkeypatch, choose=UNGROUP)

    assert first.scene() is None and second.scene() is None
    assert first_member.parentItem() is None
    assert second_member.parentItem() is None
    assert _stack_depth(view) == 1, "two groups, one gesture, one undo step"
    assert view.command_manager.last_command is not None
    assert view.command_manager.last_command.description == "Ungroup 2 groups"

    view.command_manager.undo()
    assert first.scene() is scene and second.scene() is scene
    assert first_member.parentItem() is first
    assert second_member.parentItem() is second


def test_the_shortcut_path_is_the_same_implementation(qtbot) -> None:
    """Ctrl+G / Ctrl+Shift+G are the public methods the menu dispatches to."""
    view = _canvas(qtbot)
    scene = view.scene()
    first = _rectangle(layer_id=scene.active_layer.id)
    second = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(first)
    scene.addItem(second)
    first.setSelected(True)
    second.setSelected(True)

    view.group_selected()
    group = first.parentItem()
    assert isinstance(group, GroupItem)

    group.setSelected(True)
    view.ungroup_selected()
    assert first.parentItem() is None
    assert group.scene() is None


# ---------------------------------------------------------------------------
# Selection normalisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory,_with_peer,alone", ITEM_CASES)
def test_right_click_on_an_unselected_object_replaces_the_selection(
    factory, _with_peer, alone, qtbot, monkeypatch
) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    previously = _rectangle(layer_id=scene.active_layer.id)
    item = factory(layer_id=scene.active_layer.id)
    scene.addItem(previously)
    scene.addItem(item)
    previously.setSelected(True)

    labels = _labels(_open_menu(item, monkeypatch))

    assert scene.selectedItems() == [item], (
        f"{type(item).__name__}: the menu was built from a stale selection"
    )
    assert labels & {GROUP, UNGROUP} == alone


def test_deleting_a_group_restores_its_membership_on_undo(qtbot) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    first = _rectangle(layer_id=scene.active_layer.id)
    second = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(first)
    scene.addItem(second)
    first.setSelected(True)
    second.setSelected(True)
    view.group_selected()
    group = first.parentItem()
    assert isinstance(group, GroupItem)

    view._delete_selected_items()
    assert group.scene() is None
    view.command_manager.undo()
    assert group.scene() is scene
    assert first.parentItem() is group and second.parentItem() is group


def test_deleting_a_group_removes_a_childs_constraint(qtbot) -> None:
    """The top-level filter must not hide a child's graph references.

    Before the fix the group vanished but its child's constraint stayed in the
    graph and was written to the plan with a dead anchor (round-7 review P1).
    """
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    view = _canvas(qtbot)
    scene = view.scene()
    child = _rectangle(layer_id=scene.active_layer.id)
    peer = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(child)
    scene.addItem(peer)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(item_id=child.item_id, anchor_type=AnchorType.CENTER),
        AnchorRef(item_id=peer.item_id, anchor_type=AnchorType.CENTER),
        50.0,
    )
    child.setSelected(True)
    peer.setSelected(True)
    view.group_selected()
    group = child.parentItem()
    assert group is not None

    view._delete_selected_items()

    assert group.scene() is None
    assert graph.constraints == {}, "a group child's constraint was left dangling"

    # Two commands: remove constraint, then delete the group.
    view.command_manager.undo()
    assert group.scene() is scene
    view.command_manager.undo()
    assert len(graph.constraints) == 1


def test_the_background_image_is_deliberately_not_groupable(qtbot) -> None:
    """A backdrop grouped with ground surfaces re-bands it above them."""
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice
    from PyQt6.QtGui import QColor, QImage

    from open_garden_planner.ui.canvas.items.background_image_item import (
        BackgroundImageItem,
    )
    from open_garden_planner.ui.canvas.items.group_item import (
        groupable_selection,
        top_level_selection,
    )

    image = QImage(2, 2, QImage.Format.Format_ARGB32)
    image.fill(QColor("white"))
    array = QByteArray()
    buffer = QBuffer(array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, "PNG")
    buffer.close()
    background = BackgroundImageItem("bg.png", _pixmap_data=bytes(array))
    rect = _rectangle()
    assert groupable_selection([background, rect]) == [rect]
    assert top_level_selection([background, rect]) == [background, rect]


def test_right_click_inside_a_multi_selection_keeps_it(qtbot, monkeypatch) -> None:
    view = _canvas(qtbot)
    scene = view.scene()
    first = _rectangle(layer_id=scene.active_layer.id)
    second = _rectangle(layer_id=scene.active_layer.id)
    scene.addItem(first)
    scene.addItem(second)
    first.setSelected(True)
    second.setSelected(True)

    labels = _labels(_open_menu(first, monkeypatch))

    assert set(scene.selectedItems()) == {first, second}
    assert GROUP in labels
