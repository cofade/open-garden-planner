"""A click in the 3D view selects what a click on the canvas selects (L1.8, gate G2).

``ui/view3d/selection_bridge.py`` turns a 3D pick into a canvas selection. Its rules
are not invented: they are MEASURED here. Every case below is played twice from the
same starting selection — once as a real mouse click on the real canvas
(``QTest.mouseClick`` on the view's viewport: the select tool, Qt's own item
handling, the layer flags), once as the 3D click the bridge receives — and the two
selections must be the same. The literal next to each case is what the canvas was
measured to do (2026-10-12); a canvas that changes its mind fails the case, and the
bridge with it.

What was measured, and is matched:

- a locked item is transparent to a click: it selects what is BEHIND it (on the
  canvas: below it in the stacking order; in 3D: further along the ray) - and when
  nothing is, a plain or Shift click clears the selection while a CTRL click keeps
  it (Qt's own Ctrl rule; fix round 1 - so the bridge is told WHICH modifier, not
  only "toggle");
- Ctrl and Shift both toggle; a click on nothing clears, with or without them;
- a click on a member of a group selects the group.

The one difference this file used to carry - Shift+click through a locked item -
was a defect of the canvas and is repaired (#522): the select tool now asks for the
first SELECTABLE item under the cursor, so the canvas and the bridge agree.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtTest import QTest

from open_garden_planner.core.commands import CreateItemCommand, GroupCommand
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.models.layer import Layer
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.view3d.selection_bridge import (
    apply_click,
    click_target,
    hit_ids,
    is_selectable,
    item_with_id,
    selectable_target,
    selected_record_ids,
    sole_selected,
)

PLAIN = Qt.KeyboardModifier.NoModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier
EMPTY = (4500.0, 2800.0)


@dataclass
class Hit:
    """What ``Quick3DHost.pick`` hands over: the nearest hit and what lies behind it."""

    item_id: str
    behind: tuple[Any, ...] = ()


class Plan:
    """A canvas with the situations the rules are about."""

    def __init__(self, view: CanvasView, qtbot: Any) -> None:
        self.view, self.scene = view, view.scene()
        view.resize(900, 600)
        view.show()
        qtbot.waitExposed(view)
        view.fit_in_view()
        base = self.scene.active_layer
        self.locked = Layer(name="locked")
        self.hidden = Layer(name="hidden")
        self.scene.add_layer(self.locked)
        self.scene.add_layer(self.hidden)
        self.items: dict[str, Any] = {}
        for name, x, y, w, h, layer in (
                ("under", 1000, 1000, 800, 800, base),       # … and a locked item on top of it
                ("over", 1200, 1200, 400, 400, self.locked),
                ("free", 3000, 1000, 400, 400, base),
                ("alone", 200, 2400, 300, 300, self.locked),  # a locked item with nothing below
                ("g1", 3000, 2000, 300, 300, base),
                ("g2", 3400, 2000, 300, 300, base),
                ("ghost", 2000, 200, 300, 300, self.hidden)):
            item = RectangleItem(x, y, w, h, object_type=ObjectType.RAISED_BED,
                                 layer_id=layer.id, name=name)
            view.command_manager.execute(CreateItemCommand(self.scene, item, name))
            self.items[name] = item
        view.command_manager.execute(GroupCommand(self.scene, [self.items["g1"], self.items["g2"]]))
        self.group = next(item for item in self.scene.items() if isinstance(item, GroupItem))
        self.scene.update_layer_lock(self.locked.id, True)
        self.scene.update_layer_visibility(self.hidden.id, False)
        self.scene.clearSelection()

    def id_of(self, name: str) -> str:
        return str(self.items[name].item_id)

    def select(self, names: tuple[str, ...]) -> None:
        self.scene.clearSelection()
        for name in names:
            (self.group if name == "group" else self.items[name]).setSelected(True)

    def selected(self) -> list[str]:
        return sorted("group" if item is self.group else str(getattr(item, "name", ""))
                      for item in self.scene.selectedItems())

    def click_canvas(self, x: float, y: float, modifiers: Qt.KeyboardModifier) -> None:
        point = self.view.mapFromScene(QPointF(x, y))
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton, modifiers,
                         QPoint(point.x(), point.y()))

    def click_3d(self, ray: tuple[str, ...], modifiers: Qt.KeyboardModifier = PLAIN) -> None:
        hit = Hit(self.id_of(ray[0]), tuple(Hit(self.id_of(name)) for name in ray[1:])) if ray else None
        apply_click(self.scene, hit_ids(hit), modifiers)


@pytest.fixture()
def plan(canvas: CanvasView, qtbot) -> Plan:
    return Plan(canvas, qtbot)


#: name, the canvas point, the modifier, what the 3D ray meets (nearest first), the
#: selection before, the selection the CANVAS was measured to end with
CASES = [
    ("plain click selects only that item", (3200, 1200), PLAIN, ("free",), ("under",), ["free"]),
    ("plain click on the only selected item", (3200, 1200), PLAIN, ("free",), ("free",), ["free"]),
    ("plain click on one of several", (3200, 1200), PLAIN, ("free",), ("free", "under"), ["free"]),
    ("ctrl adds", (3200, 1200), CTRL, ("free",), ("under",), ["free", "under"]),
    ("ctrl removes", (3200, 1200), CTRL, ("free",), ("free", "under"), ["under"]),
    ("shift adds", (3200, 1200), SHIFT, ("free",), ("under",), ["free", "under"]),
    ("shift removes", (3200, 1200), SHIFT, ("free",), ("free", "under"), ["under"]),
    ("click on nothing clears", EMPTY, PLAIN, (), ("free", "under"), []),
    ("ctrl+click on nothing clears too", EMPTY, CTRL, (), ("free", "under"), []),
    ("shift+click on nothing clears too", EMPTY, SHIFT, (), ("free", "under"), []),
    ("a locked item lets the click through to what is behind", (1400, 1400), PLAIN,
     ("over", "under"), ("free",), ["under"]),
    ("… also a toggling click", (1400, 1400), CTRL, ("over", "under"), ("free",),
     ["free", "under"]),
    ("… and toggles it off again", (1400, 1400), CTRL, ("over", "under"), ("free", "under"),
     ["free"]),
    ("… and a shift+click toggles what is behind it too", (1400, 1400), SHIFT,
     ("over", "under"), ("free",), ["free", "under"]),
    ("… and a shift+click on it toggles it off again", (1400, 1400), SHIFT,
     ("over", "under"), ("free", "under"), ["free"]),
    ("a locked item with nothing behind is nothing", (350, 2550), PLAIN, ("alone",), ("free",), []),
    ("… a ctrl+click on it keeps the selection", (350, 2550), CTRL, ("alone",), ("free",), ["free"]),
    ("… a shift+click on it clears", (350, 2550), SHIFT, ("alone",), ("free",), []),
    ("a member of a group selects the group", (3150, 2150), PLAIN, ("g1",), ("free",), ["group"]),
    ("the other member too", (3550, 2150), PLAIN, ("g2",), (), ["group"]),
    ("ctrl+click on a member toggles the group", (3150, 2150), CTRL, ("g1",), ("free",),
     ["free", "group"]),
    ("… off", (3150, 2150), CTRL, ("g1",), ("free", "group"), ["free"]),
]


@pytest.mark.parametrize(("name", "point", "modifiers", "ray", "before", "measured"), CASES,
                         ids=[case[0] for case in CASES])
def test_a_3d_click_ends_with_the_selection_a_canvas_click_ends_with(
        plan: Plan, name: str, point, modifiers, ray, before, measured) -> None:
    plan.select(before)
    plan.click_canvas(*point, modifiers)
    on_canvas = plan.selected()
    assert on_canvas == measured, f"the CANVAS no longer does what was measured: {name}"
    plan.select(before)
    plan.click_3d(ray, modifiers)
    assert plan.selected() == on_canvas, name


def test_shift_through_a_locked_item_toggles_what_is_behind_it(plan: Plan) -> None:
    """#522: the repair of the one measured difference this file used to carry.

    The select tool asked ``itemAt``, which answers the LOCKED item on top, and
    handed the click to Qt - whose own toggle key is Ctrl. So Shift+click
    through a locked item was a PLAIN click on what was behind it, and it
    REPLACED the selection instead of toggling it. The tool now asks for the
    first SELECTABLE item under the cursor, so Shift+click toggles what lies
    behind the locked item - the canvas's own rule ("Shift+click adds or
    removes") - and the 3D view, which always did that, no longer differs.
    """
    plan.select(("free",))
    plan.click_canvas(1400, 1400, SHIFT)
    assert plan.selected() == ["free", "under"], "the locked item must not swallow the click"

    plan.select(("free", "under"))
    plan.click_canvas(1400, 1400, SHIFT)
    assert plan.selected() == ["free"], "and a second one takes it back off"


def test_an_item_on_a_hidden_layer_cannot_be_named_by_a_click_and_is_not_selectable(plan: Plan) -> None:
    """It has no record, so the 3D view never names it; a stale id is nothing."""
    from datetime import date

    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    ghost = plan.items["ghost"]
    assert plan.id_of("ghost") not in snapshot_records(plan.scene, date(2026, 6, 21))
    assert not is_selectable(ghost)
    plan.select(("free",))
    plan.click_3d(("ghost",), PLAIN)
    assert plan.selected() == [], "as a click on nothing"
    plan.click_canvas(2150, 350, PLAIN)
    assert plan.selected() == [], "the canvas does not hit it either"


def test_the_locked_layers_items_have_records_and_are_not_selectable(plan: Plan) -> None:
    """A locked layer is SHOWN — in 2D and in 3D — and its items can be hit; what it
    takes away is the selectable flag."""
    from datetime import date

    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    records = snapshot_records(plan.scene, date(2026, 6, 21))
    assert {plan.id_of("over"), plan.id_of("alone")} <= records.keys()
    assert not is_selectable(plan.items["over"]) and is_selectable(plan.items["under"])
    plan.scene.update_layer_lock(plan.locked.id, False)
    assert is_selectable(plan.items["over"])
    plan.click_3d(("over", "under"), PLAIN)
    assert plan.selected() == ["over"], "unlocked: it is the nearest and it is selected"


def test_the_click_target_is_the_outermost_group(plan: Plan) -> None:
    outer = GroupCommand(plan.scene, [plan.group, plan.items["free"]])
    plan.view.command_manager.execute(outer)
    top = next(item for item in plan.scene.items()
               if isinstance(item, GroupItem) and item is not plan.group)
    assert click_target(plan.items["g1"]) is top and click_target(plan.items["free"]) is top
    assert click_target(plan.items["under"]) is plan.items["under"]
    plan.scene.clearSelection()
    plan.click_3d(("g2",), PLAIN)
    assert plan.scene.selectedItems() == [top]
    # one click through two members of the same group is one target, not a toggle twice
    assert selectable_target(plan.scene, [plan.id_of("g1"), plan.id_of("free")]) is top


def test_the_ray_is_read_nearest_first_and_each_item_once() -> None:
    assert hit_ids(None) == ()
    assert hit_ids(Hit("a")) == ("a",)
    # an item with several mesh parts is met several times along one ray
    ray = Hit("a", (Hit("a"), Hit("b"), Hit("a"), Hit(""), Hit("c"), Hit("b")))
    assert hit_ids(ray) == ("a", "b", "c")


def test_ids_that_name_nothing_are_passed_over(plan: Plan) -> None:
    assert item_with_id(plan.scene, "") is None and item_with_id(plan.scene, "no such id") is None
    plan.select(("free",))
    apply_click(plan.scene, ("no such id", plan.id_of("under")), PLAIN)
    assert plan.selected() == ["under"]
    apply_click(plan.scene, ("no such id",), CTRL)
    assert plan.selected() == [], "an id that names NOTHING is a click on nothing, also with Ctrl"


def test_the_ids_the_ring_is_drawn_for(plan: Plan) -> None:
    """2D → 3D: a selected item gives its id; a selected GROUP gives its members' (a
    group covers no ground and has no record)."""
    assert selected_record_ids(plan.scene) == frozenset()
    plan.select(("free", "under"))
    assert selected_record_ids(plan.scene) == {plan.id_of("free"), plan.id_of("under")}
    plan.select(("group",))
    assert selected_record_ids(plan.scene) == {plan.id_of("g1"), plan.id_of("g2")}
    plan.select(("group", "free"))
    assert selected_record_ids(plan.scene) == {plan.id_of("g1"), plan.id_of("g2"), plan.id_of("free")}
    assert all(isinstance(item_id, str) for item_id in selected_record_ids(plan.scene))


def test_sole_selected_is_the_one_item_or_none(plan: Plan) -> None:
    assert sole_selected(plan.scene) is None
    plan.select(("free",))
    assert sole_selected(plan.scene) is plan.items["free"]
    plan.select(("group",))
    assert sole_selected(plan.scene) is plan.group
    plan.select(("free", "under"))
    assert sole_selected(plan.scene) is None


def test_every_step_goes_through_the_scenes_own_selection_signal(plan: Plan) -> None:
    """The canvas's OWN selection path: ``selectionChanged`` fires, so the property
    panels, the status bar and the ring follow — and nothing reaches the undo stack."""
    fired: list[int] = []
    plan.scene.selectionChanged.connect(lambda: fired.append(1))
    undo = plan.view.command_manager.can_undo
    stack = len(plan.view.command_manager._undo_stack)  # noqa: SLF001 - "nothing was pushed"
    plan.click_3d(("free",), PLAIN)
    assert fired and plan.items["free"].isSelected()
    fired.clear()
    plan.click_3d(("free",), PLAIN)
    assert fired == [], "the same click again changes nothing and says nothing"
    plan.click_3d(("under",), CTRL)
    plan.click_3d((), PLAIN)
    assert plan.selected() == [] and len(fired) >= 2
    assert len(plan.view.command_manager._undo_stack) == stack  # noqa: SLF001
    assert plan.view.command_manager.can_undo == undo
