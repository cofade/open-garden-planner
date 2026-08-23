"""Integration tests: the Arrange context-menu submenu (issue #338, plan step 5).

Modelled on ``tests/integration/test_bed_context_menu.py``: a structural
regression test that fails for any future shared-seam item that forgets to
wire ``GardenItemMixin._build_arrange_menu`` / ``_dispatch_arrange`` into its
own ``contextMenuEvent``. Covers all nine item classes that share the
``_build_move_to_layer_menu`` seam (rectangle, polygon, polyline, circle,
ellipse, text, callout, group, smart symbol) — journal pins are excluded by
design (``ui/canvas/arrange.py`` drops them before they ever reach a layer).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu

import open_garden_planner.ui.canvas.items.garden_item as garden_item_module
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.stacking import ArrangeMode
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.callout_item import CalloutItem
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.group_item import GroupItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.items.smart_symbol_item import SmartSymbolItem
from open_garden_planner.ui.canvas.items.text_item import TextItem

# ---------------------------------------------------------------------------
# Item factories — one per shared-seam class. Each accepts an optional
# layer_id so the same factory works for the bare-construction menu-structure
# test (no layer) and the scene-backed contextMenuEvent test (real layer).
# ---------------------------------------------------------------------------


def _make_rectangle(layer_id=None) -> RectangleItem:
    return RectangleItem(
        0, 0, 100, 60, object_type=ObjectType.GENERIC_RECTANGLE, layer_id=layer_id
    )


def _make_polygon(layer_id=None) -> PolygonItem:
    vertices = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 60), QPointF(0, 60)]
    return PolygonItem(vertices, object_type=ObjectType.GENERIC_POLYGON, layer_id=layer_id)


def _make_polyline(layer_id=None) -> PolylineItem:
    points = [QPointF(0, 0), QPointF(100, 0), QPointF(100, 60)]
    return PolylineItem(points, object_type=ObjectType.FENCE, layer_id=layer_id)


def _make_circle(layer_id=None) -> CircleItem:
    return CircleItem(0, 0, 30, object_type=ObjectType.GENERIC_CIRCLE, layer_id=layer_id)


def _make_ellipse(layer_id=None) -> EllipseItem:
    return EllipseItem(0, 0, 100, 60, object_type=ObjectType.GENERIC_ELLIPSE, layer_id=layer_id)


def _make_text(layer_id=None) -> TextItem:
    return TextItem(0, 0, content="label", layer_id=layer_id)


def _make_callout(layer_id=None) -> CalloutItem:
    return CalloutItem(QPointF(0, 0), QPointF(50, 50), content="note", layer_id=layer_id)


def _make_group(layer_id=None) -> GroupItem:
    return GroupItem(layer_id=layer_id)


def _make_smart_symbol(layer_id=None) -> SmartSymbolItem:
    return SmartSymbolItem("raised_bed_rows", 1, {"rows": 4}, layer_id=layer_id)


ITEM_FACTORIES = [
    pytest.param(_make_rectangle, id="RectangleItem"),
    pytest.param(_make_polygon, id="PolygonItem"),
    pytest.param(_make_polyline, id="PolylineItem"),
    pytest.param(_make_circle, id="CircleItem"),
    pytest.param(_make_ellipse, id="EllipseItem"),
    pytest.param(_make_text, id="TextItem"),
    pytest.param(_make_callout, id="CalloutItem"),
    pytest.param(_make_group, id="GroupItem"),
    pytest.param(_make_smart_symbol, id="SmartSymbolItem"),
]

_EXPECTED_MODES = [
    ArrangeMode.BRING_TO_FRONT,
    ArrangeMode.BRING_FORWARD,
    ArrangeMode.SEND_BACKWARD,
    ArrangeMode.SEND_TO_BACK,
]


# ---------------------------------------------------------------------------
# Structural: _build_arrange_menu appends exactly the four modes, in order.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", ITEM_FACTORIES)
def test_build_arrange_menu_has_four_actions_in_order(factory, qtbot) -> None:  # noqa: ARG001
    item = factory()
    menu = QMenu()

    arrange_menu = item._build_arrange_menu(menu)

    assert arrange_menu is not None
    actions = arrange_menu.actions()
    assert len(actions) == 4, (
        f"{type(item).__name__}: Arrange submenu must have exactly 4 actions, "
        f"got {len(actions)}"
    )
    assert [a.data() for a in actions] == _EXPECTED_MODES, (
        f"{type(item).__name__}: Arrange actions must be in "
        "Bring to Front / Bring Forward / Send Backward / Send to Back order"
    )
    # Every action carries non-empty, translation-ready text.
    for action in actions:
        assert action.text(), f"{type(item).__name__}: arrange action has empty text"


@pytest.mark.parametrize("factory", ITEM_FACTORIES)
def test_build_arrange_menu_is_added_to_parent(factory, qtbot) -> None:  # noqa: ARG001
    """The submenu must actually be attached to the menu passed in."""
    item = factory()
    menu = QMenu()

    arrange_menu = item._build_arrange_menu(menu)

    parent_actions = [a for a in menu.actions() if a.menu() is arrange_menu]
    assert parent_actions, (
        f"{type(item).__name__}: Arrange submenu was built but not appended "
        "to the parent menu"
    )


# ---------------------------------------------------------------------------
# Structural: every shared-seam item's contextMenuEvent must route through
# the shared builder + dispatcher, exactly like the Move-to-Layer pattern
# (test_bed_context_menu.py's `test_context_menu_uses_shared_builder`).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "item_cls",
    [
        RectangleItem, PolygonItem, PolylineItem, CircleItem, EllipseItem,
        TextItem, CalloutItem, GroupItem, SmartSymbolItem,
    ],
)
def test_context_menu_event_uses_shared_arrange_builder(item_cls) -> None:
    """Source-level enforcement, mirroring test_bed_context_menu.py.

    Catches a future shape that bypasses ``_build_arrange_menu`` /
    ``_dispatch_arrange`` (or a shape regressing to a hand-rolled block).
    """
    import inspect

    src = inspect.getsource(item_cls.contextMenuEvent)
    assert "_build_arrange_menu" in src, (
        f"{item_cls.__name__}.contextMenuEvent must call _build_arrange_menu — "
        "Arrange must go through GardenItemMixin (issue #338)."
    )
    assert "_dispatch_arrange" in src, (
        f"{item_cls.__name__}.contextMenuEvent must call _dispatch_arrange — "
        "Arrange action routing must go through GardenItemMixin (issue #338)."
    )


# ---------------------------------------------------------------------------
# End-to-end: driving the REAL contextMenuEvent of each of the nine classes
# must produce a menu that contains the Arrange submenu built by
# _build_arrange_menu. QMenu.exec is monkeypatched (it would otherwise block
# on a real popup) to capture the top-level menu instead of executing it.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("factory", ITEM_FACTORIES)
def test_context_menu_event_offers_arrange_submenu(
    factory, canvas: CanvasView, qtbot, monkeypatch
) -> None:
    scene = canvas.scene()
    layer_id = scene.active_layer.id
    item = factory(layer_id=layer_id)
    scene.addItem(item)

    captured_menus: list[QMenu] = []
    captured_submenus: list[QMenu] = []

    orig_build = garden_item_module.GardenItemMixin._build_arrange_menu

    def spy_build(self, parent_menu):  # noqa: ANN001
        result = orig_build(self, parent_menu)
        captured_submenus.append(result)
        return result

    def fake_exec(self, *args, **kwargs):  # noqa: ANN001, ARG001
        captured_menus.append(self)
        return None  # simulate the user dismissing the menu without a choice

    monkeypatch.setattr(garden_item_module.GardenItemMixin, "_build_arrange_menu", spy_build)
    monkeypatch.setattr(QMenu, "exec", fake_exec)

    event = MagicMock(spec=QGraphicsSceneContextMenuEvent)
    event.screenPos.return_value = QPoint(0, 0)

    item.contextMenuEvent(event)

    assert captured_menus, f"{type(item).__name__}.contextMenuEvent must call menu.exec()"
    assert captured_submenus, (
        f"{type(item).__name__}.contextMenuEvent must build the Arrange submenu"
    )
    arrange_submenu = captured_submenus[-1]
    top_menu = captured_menus[-1]
    parent_actions = [a for a in top_menu.actions() if a.menu() is arrange_submenu]
    assert parent_actions, (
        f"{type(item).__name__}: Arrange submenu was built but never reached "
        "the top-level context menu"
    )
    assert [a.data() for a in arrange_submenu.actions()] == _EXPECTED_MODES


# ---------------------------------------------------------------------------
# Dispatch: RectangleItem end-to-end through _dispatch_arrange, on a real
# CanvasView (so the undo stack + delegation to CanvasView.arrange_selected
# is exercised, not just build_arrange_command directly).
# ---------------------------------------------------------------------------


class TestDispatchArrangeOnRectangleItem:
    def test_send_to_back_flips_z_order_and_is_undoable(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        bottom = RectangleItem(
            0, 0, 100, 100, object_type=ObjectType.GENERIC_RECTANGLE,
            name="bottom", layer_id=layer_id,
        )
        top = RectangleItem(
            20, 20, 100, 100, object_type=ObjectType.GENERIC_RECTANGLE,
            name="top", layer_id=layer_id,
        )
        scene.addItem(bottom)
        scene.addItem(top)
        assert top.zValue() > bottom.zValue(), "second-added item should start on top"

        undo_count_before = len(canvas.command_manager._undo_stack)

        top.setSelected(True)
        top._dispatch_arrange(ArrangeMode.SEND_TO_BACK)

        assert top.zValue() < bottom.zValue(), "Send to Back must flip the z order"
        assert canvas.command_manager.can_undo is True
        undo_count_after_first = len(canvas.command_manager._undo_stack)
        assert undo_count_after_first == undo_count_before + 1, (
            "arranging must push exactly one undo step"
        )

    def test_second_send_to_back_is_a_silent_no_op(
        self, canvas: CanvasView, qtbot
    ) -> None:
        scene = canvas.scene()
        layer_id = scene.active_layer.id
        bottom = RectangleItem(
            0, 0, 100, 100, object_type=ObjectType.GENERIC_RECTANGLE,
            name="bottom", layer_id=layer_id,
        )
        top = RectangleItem(
            20, 20, 100, 100, object_type=ObjectType.GENERIC_RECTANGLE,
            name="top", layer_id=layer_id,
        )
        scene.addItem(bottom)
        scene.addItem(top)

        top.setSelected(True)
        top._dispatch_arrange(ArrangeMode.SEND_TO_BACK)
        undo_count_after_first = len(canvas.command_manager._undo_stack)

        # Already at back: calling again must not push a second undo step.
        top._dispatch_arrange(ArrangeMode.SEND_TO_BACK)
        undo_count_after_second = len(canvas.command_manager._undo_stack)

        assert undo_count_after_second == undo_count_after_first, (
            "a no-op arrange must not push a new undo step"
        )
