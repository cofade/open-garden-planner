"""End-to-end regressions for the CAD-precision integrity package.

These drive the pieces the user actually touches: the Lock position action, a
real viewport drag, the Properties panel's Layer combo, and save/reload through
the project manager.  Unit-level coverage for the same issues lives in
``tests/unit/test_constraint_integrity.py``,
``tests/unit/test_geometry_identity.py`` and
``tests/unit/test_incidence_consistency.py``.
"""

from __future__ import annotations

import json
import math
from uuid import uuid4

import pytest
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QGraphicsItem, QMenu

from open_garden_planner.core.constraints import (
    AnchorRef,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.properties_panel import PropertiesPanel


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=6000, height_cm=4000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.resize(900, 700)
    view.show()
    qtbot.waitExposed(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


def _lock(item) -> None:
    menu = QMenu()
    action = item.build_lock_context_menu(menu)
    assert item.dispatch_lock_action(action, action) is True


def _drag_in_view(canvas: CanvasView, item, delta: QPointF) -> None:
    """Press on *item*'s centre, move by *delta* in scene units, release."""
    canvas.centerOn(item.mapToScene(item.boundingRect().center()))
    start = canvas.mapFromScene(item.mapToScene(item.boundingRect().center()))
    target = canvas.mapFromScene(
        item.mapToScene(item.boundingRect().center()) + delta
    )
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(canvas.viewport(), (start + target) / 2)
    QTest.mouseMove(canvas.viewport(), target)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, target)


# ── #655: a saved position lock is still a lock after reopening ───────────


def test_saved_lock_still_holds_after_reopen(canvas: CanvasView, tmp_path) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(rect)
    _lock(rect)
    pinned = QPointF(rect.pos())
    path = tmp_path / "locked.ogp"
    ProjectManager().save(scene, path)

    ProjectManager().load(scene, path)
    loaded = next(
        item
        for item in scene.items()
        if getattr(item, "item_id", None) == rect.item_id
    )
    assert loaded.is_position_locked()

    constraint = next(
        constraint
        for constraint in scene.constraint_graph.constraints.values()
        if constraint.constraint_type == ConstraintType.FIXED
    )
    assert constraint.target_x is not None and constraint.target_y is not None, (
        "the lock's target coordinates were dropped on load"
    )
    assert (constraint.target_x, constraint.target_y) == (
        loaded.pos().x(),
        loaded.pos().y(),
    ), "the loaded lock must be pinned in the loaded frame"

    _drag_in_view(canvas, loaded, QPointF(180.0, 120.0))
    assert loaded.pos() == pinned, "a reopened lock must still refuse to move"

    # ...and the next save does not erase it.
    again = tmp_path / "locked-again.ogp"
    ProjectManager().save(scene, again)
    raw = json.loads(again.read_text(encoding="utf-8"))
    fixed = next(
        entry for entry in raw["constraints"] if entry["constraint_type"] == "FIXED"
    )
    assert fixed["target_x"] == pytest.approx(pinned.x())
    assert fixed["target_y"] == pytest.approx(pinned.y())


def test_a_lock_on_a_moved_item_does_not_jump_on_reload(
    canvas: CanvasView, tmp_path, qtbot: object
) -> None:
    """The target names a frame that the serializer normalizes away (#655 P0).

    The rectangle is created at local (600, 700) and then MOVED to pos
    (100, 100); its saved ``x`` is ``pos + rect.x``, so the loader recreates it
    at pos 0.  A saved target of (100, 100) would then move it on the first drag.
    """
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200)
    scene.addItem(rect)
    rect.setPos(100.0, 100.0)
    _lock(rect)
    visible_before = rect.mapToScene(rect.boundingRect().center())
    path = tmp_path / "moved-lock.ogp"
    ProjectManager().save(scene, path)

    ProjectManager().load(scene, path)
    loaded = next(
        item
        for item in scene.items()
        if getattr(item, "item_id", None) == rect.item_id
    )
    visible_after_load = loaded.mapToScene(loaded.boundingRect().center())
    assert visible_after_load.x() == pytest.approx(visible_before.x(), abs=1e-6)
    assert visible_after_load.y() == pytest.approx(visible_before.y(), abs=1e-6)

    _drag_in_view(canvas, loaded, QPointF(180.0, 120.0))
    visible_after_drag = loaded.mapToScene(loaded.boundingRect().center())
    assert visible_after_drag.x() == pytest.approx(visible_before.x(), abs=1e-6), (
        "the first drag after reopening moved the locked item"
    )
    assert visible_after_drag.y() == pytest.approx(visible_before.y(), abs=1e-6)

    again = tmp_path / "moved-lock-again.ogp"
    ProjectManager().save(scene, again)
    ProjectManager().load(scene, again)
    twice = next(
        item
        for item in scene.items()
        if getattr(item, "item_id", None) == rect.item_id
    )
    final = twice.mapToScene(twice.boundingRect().center())
    assert final.x() == pytest.approx(visible_before.x(), abs=1e-6)
    assert final.y() == pytest.approx(visible_before.y(), abs=1e-6)


# ── #662: a locked item is inert during the drag, not restored after it ───


def test_fixed_item_has_zero_transient_positions_during_a_drag(
    canvas: CanvasView, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200, object_type=ObjectType.GENERIC_RECTANGLE)
    scene.addItem(rect)
    _lock(rect)
    pinned = QPointF(rect.pos())

    seen: list[QPointF] = []
    original = RectangleItem.itemChange

    def spy(self, change, value):
        result = original(self, change, value)
        if (
            self is rect
            and change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        ):
            seen.append(QPointF(self.pos()))
        return result

    monkeypatch.setattr(RectangleItem, "itemChange", spy)
    rect.setSelected(True)
    steps_before = canvas.command_manager.undo_depth
    _drag_in_view(canvas, rect, QPointF(200.0, 140.0))
    monkeypatch.undo()

    assert rect.pos() == pinned
    assert seen == [], (
        f"the locked item reported {len(seen)} positions it never had: {seen}"
    )
    # The drag must leave no undo step for an object that cannot move.
    assert canvas.command_manager.undo_depth == steps_before


def test_a_mobile_partner_still_follows_the_fixed_reference(canvas: CanvasView) -> None:
    scene = canvas.scene()
    fixed = RectangleItem(600, 700, 300, 200)
    scene.addItem(fixed)
    _lock(fixed)
    mobile = RectangleItem(1250, 700, 200, 200)
    scene.addItem(mobile)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(fixed.item_id, AnchorType.CENTER),
        AnchorRef(mobile.item_id, AnchorType.CENTER),
        600.0,
    )
    fixed_before = QPointF(fixed.pos())

    mobile.setSelected(True)
    _drag_in_view(canvas, mobile, QPointF(200.0, 0.0))

    assert fixed.pos() == fixed_before, "the fixed reference moved with the drag"
    distance = math.dist(
        (
            fixed.mapToScene(fixed.boundingRect().center()).x(),
            fixed.mapToScene(fixed.boundingRect().center()).y(),
        ),
        (
            mobile.mapToScene(mobile.boundingRect().center()).x(),
            mobile.mapToScene(mobile.boundingRect().center()).y(),
        ),
    )
    assert distance == pytest.approx(600.0, abs=1.0)


def test_the_lock_flag_is_restored_after_the_gesture(canvas: CanvasView) -> None:
    scene = canvas.scene()
    rect = RectangleItem(600, 700, 300, 200)
    scene.addItem(rect)
    _lock(rect)
    rect.setSelected(True)
    _drag_in_view(canvas, rect, QPointF(150.0, 100.0))

    movable = QGraphicsItem.GraphicsItemFlag.ItemIsMovable
    assert rect.flags() & movable, "the drag must not leave the item frozen"

    # Unlocking restores normal behaviour.
    menu = QMenu()
    action = rect.build_lock_context_menu(menu)
    rect.dispatch_lock_action(action, action)
    assert rect.is_position_locked() is False
    before = QPointF(rect.pos())
    _drag_in_view(canvas, rect, QPointF(150.0, 100.0))
    assert rect.pos() != before, "an unlocked item must drag again"


# ── #669 / #670: the add-constraint path the tools actually call ─────────


def _add_constraint(canvas: CanvasView, command, *, conflicts_checked: bool = True):
    canvas._execute_constraint_with_solve(
        command, conflicts_checked=conflicts_checked
    )


def _distance(canvas: CanvasView, first, second, distance: float):
    from open_garden_planner.core.commands import AddConstraintCommand

    return AddConstraintCommand(
        graph=canvas.scene().constraint_graph,
        anchor_a=AnchorRef(first.item_id, AnchorType.CENTER),
        anchor_b=AnchorRef(second.item_id, AnchorType.CENTER),
        target_distance=distance,
    )


def test_adding_a_link_does_not_move_an_unrelated_broken_component(
    canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The #670 cause-1 defect, through the application path (review P0).

    Two free rectangles carry contradictory target distances (100 and 500 cm
    between the same anchors).  Adding a compatible link between two other
    rectangles must not touch them, and must not report a conflict.
    """
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.ui.dialogs.constraint_conflict_dialog import (
        ConstraintConflictDialog,
    )

    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(900, 0, 100, 100)
    third = RectangleItem(0, 900, 100, 100)
    fourth = RectangleItem(200, 900, 100, 100)
    for item in (first, second, third, fourth):
        scene.addItem(item)

    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        100.0,
    )
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        500.0,
    )
    before = {item: QPointF(item.pos()) for item in (first, second)}
    asked: list[object] = []

    def _never_ask(rows, parent=None):  # pragma: no cover - the assertion
        asked.append(rows)
        return None

    monkeypatch.setattr(ConstraintConflictDialog, "ask", staticmethod(_never_ask))
    _add_constraint(
        canvas,
        _distance(canvas, third, fourth, 200.0),
        conflicts_checked=False,
    )

    assert asked == [], "an unrelated broken component raised a conflict dialog"
    for label, item in (("first", first), ("second", second)):
        assert item.pos() == before[item], (
            f"{label} moved although its broken component is unrelated to the "
            f"added link"
        )
    assert any(
        c.constraint_type == ConstraintType.DISTANCE
        and c.target_distance == 200.0
        for c in graph.constraints.values()
    )


def test_a_cross_component_trial_is_seen_by_the_conflict_scan(
    canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A trial that JOINS two components must see both sides (round-2 P0).

    A is locked at the origin; B1 is constrained to B2 (locked at (500, 100)).
    Linking A to B1 at 100 cm is geometrically impossible, so the trial says no.
    The conflict scan used to insert the trial without adjacency and see only
    A's side, returning "no conflict" — the dialog then let it through.
    """
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.ui.dialogs.constraint_conflict_dialog import (
        ConstraintConflictDialog,
    )

    scene = canvas.scene()
    anchor = RectangleItem(0, 0, 100, 100)
    moving = RectangleItem(450, 0, 100, 100)
    moving.setPos(500.0, 0.0)
    distant = RectangleItem(450, 100, 100, 100)
    distant.setPos(500.0, 100.0)
    for item in (anchor, moving, distant):
        scene.addItem(item)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(anchor.item_id, AnchorType.CENTER),
        AnchorRef(anchor.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
        target_x=anchor.pos().x(),
        target_y=anchor.pos().y(),
    )
    graph.add_constraint(
        AnchorRef(distant.item_id, AnchorType.CENTER),
        AnchorRef(distant.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
        target_x=distant.pos().x(),
        target_y=distant.pos().y(),
    )
    graph.add_constraint(
        AnchorRef(moving.item_id, AnchorType.CENTER),
        AnchorRef(distant.item_id, AnchorType.CENTER),
        100.0,
    )

    assert not canvas.is_constraint_feasible(
        AnchorRef(anchor.item_id, AnchorType.CENTER),
        AnchorRef(moving.item_id, AnchorType.CENTER),
        100.0,
        ConstraintType.DISTANCE,
    ), "the trial geometry must be recognised as impossible"

    asked: list[object] = []

    def _record(rows, parent=None):
        asked.append(rows)
        return None

    monkeypatch.setattr(
        ConstraintConflictDialog, "ask", staticmethod(_record)
    )
    command = _distance(canvas, anchor, moving, 100.0)
    _add_constraint(canvas, command, conflicts_checked=False)

    assert asked, "the conflict dialog must see the violated B1-B2 relation"
    assert moving.pos() == QPointF(500.0, 0.0), "a cancelled add must not move"
    assert not any(
        c.target_distance == 100.0 and c.constraint_type == ConstraintType.DISTANCE
        for c in graph.constraints.values()
        if c.anchor_a.item_id == anchor.item_id
    ), "the cancelled constraint must not be in the graph"


def test_a_construction_to_garden_link_is_feasible(canvas: CanvasView) -> None:
    """Construction geometry is always pinned, so B must stay free (round-3 P1).

    ``find_item_by_id`` only returns garden items, so the construction branch was
    dead and the trial pinned B as well — refusing a satisfiable link.
    """
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionLineItem,
    )

    scene = canvas.scene()
    construction = ConstructionLineItem(QPointF(600.0, 400.0), QPointF(600.0, 700.0))
    bed = RectangleItem(100, 100, 200, 200)
    scene.addItem(construction)
    scene.addItem(bed)
    construction_anchor = AnchorRef(construction.item_id, AnchorType.ENDPOINT, 0)
    bed_anchor = AnchorRef(bed.item_id, AnchorType.CENTER)

    assert (
        canvas._constraint_reference_pins(construction_anchor, bed_anchor) == set()
    ), "a construction A is already pinned; B must stay free"
    assert canvas.is_constraint_feasible(
        construction_anchor, bed_anchor, 300.0, ConstraintType.DISTANCE
    )
    # The other order pins B (construction), which is also correct.
    assert canvas._constraint_reference_pins(bed_anchor, construction_anchor) == {
        construction.item_id
    }


def test_a_properties_resize_does_not_solve_an_unrelated_component(
    canvas: CanvasView, qtbot: object
) -> None:
    """The resize path solves the edited item's component only (round-3 P1)."""
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.core.measure_snapper import resolve_anchor_point
    from open_garden_planner.ui.panels.properties_panel import PropertiesPanel

    scene = canvas.scene()
    # An unrelated, contradictory pair.
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(900, 0, 100, 100)
    # The edited bed and a partner at a satisfied distance from its right edge.
    bed = RectangleItem(0, 900, 400, 300)
    partner = RectangleItem(800, 900, 100, 100)
    for item in (first, second, bed, partner):
        scene.addItem(item)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        100.0,
    )
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        500.0,
    )
    graph.add_constraint(
        AnchorRef(bed.item_id, AnchorType.EDGE_RIGHT, 0),
        AnchorRef(partner.item_id, AnchorType.CENTER),
        450.0,
    )
    before = {item: QPointF(item.pos()) for item in (first, second)}

    class _Spin:
        def __init__(self, value: float) -> None:
            self._value = value

        def value(self) -> float:
            return self._value

    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel._on_dimension_changed(bed, "rect_size", None, _Spin(600.0), _Spin(300.0))

    for label, item in (("first", first), ("second", second)):
        assert item.pos() == before[item], (
            f"the unrelated {label} pair moved during an unrelated resize"
        )
    right = resolve_anchor_point(bed, AnchorType.EDGE_RIGHT, 0)
    centre = resolve_anchor_point(partner, AnchorType.CENTER, 0)
    assert right is not None and centre is not None
    distance = math.hypot(right.x() - centre.x(), right.y() - centre.y())
    assert distance == pytest.approx(450.0, abs=0.1), (
        "the same-component partner was not re-solved"
    )
    assert any(
        c.constraint_type == ConstraintType.DISTANCE and c.target_distance == 450.0
        for c in graph.constraints.values()
    )


def test_the_solver_never_translates_a_rigid_self_constraint() -> None:
    """A rigid item's self EDGE_LENGTH must produce no translation (round-5 P0)."""
    from open_garden_planner.core.constraints import (
        APPLY_TOLERANCE_CM,
        AnchorRef,
        ConstraintGraph,
        ConstraintType,
    )
    from open_garden_planner.core.measure_snapper import AnchorType

    graph = ConstraintGraph()
    item = uuid4()
    graph.add_constraint(
        AnchorRef(item, AnchorType.CORNER, 0),
        AnchorRef(item, AnchorType.CORNER, 1),
        400.0,
        constraint_type=ConstraintType.EDGE_LENGTH,
    )
    result = graph.solve_anchored(
        {item: (0.0, 0.0)},
        {
            (item, AnchorType.CORNER, 0): (0.0, 0.0),
            (item, AnchorType.CORNER, 1): (200.0, 0.0),
        },
        max_iterations=20,
        tolerance=APPLY_TOLERANCE_CM,
    )
    assert result.item_deltas == {}, "the rigid shape was translated by the solver"


def test_a_violated_rigid_self_constraint_is_refused_by_the_trial() -> None:
    """The measured residual keeps the conflict dialog alive (round-6 P1)."""
    from open_garden_planner.core.constraints import (
        ConstraintGraph,
        ConstraintType,
    )

    graph = ConstraintGraph()
    item = uuid4()
    assert graph.validate_constraint(
        AnchorRef(item, AnchorType.CORNER, 0),
        AnchorRef(item, AnchorType.CORNER, 2),
        500.0,
        ConstraintType.DISTANCE,
        {item: (0.0, 0.0)},
        {
            (item, AnchorType.CORNER, 0): (0.0, 0.0),
            (item, AnchorType.CORNER, 2): (100.0, 100.0),
        },
    ) is False, "an unenforceable self-constraint must not be approved"


def test_a_rigid_shapes_edge_length_refuses_a_properties_resize(
    canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Resizing a rigid shape with its own EDGE_LENGTH is refused (round-5 P0)."""
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.ui.panels.properties_panel import PropertiesPanel

    scene = canvas.scene()
    rect = RectangleItem(100, 100, 200, 100)
    scene.addItem(rect)
    scene.constraint_graph.add_constraint(
        AnchorRef(rect.item_id, AnchorType.CORNER, 0),
        AnchorRef(rect.item_id, AnchorType.CORNER, 1),
        200.0,
        constraint_type=ConstraintType.EDGE_LENGTH,
    )
    before_rect = QRectF(rect.rect())
    before_pos = QPointF(rect.pos())
    steps = canvas.command_manager.undo_depth
    messages: list[str] = []
    original = canvas.set_status_message

    def _record(message: str) -> None:
        messages.append(message)
        original(message)

    monkeypatch.setattr(canvas, "set_status_message", _record)

    class _Spin:
        def __init__(self, value: float) -> None:
            self._value = value

        def value(self) -> float:
            return self._value

    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel._on_dimension_changed(rect, "rect_size", None, _Spin(240.0), _Spin(100.0))

    assert rect.rect() == before_rect, "the refused resize must not change geometry"
    assert rect.pos() == before_pos
    assert canvas.command_manager.undo_depth == steps
    assert messages, "the refusal must be explained to the user"

    # A height-only edit leaves a TOP/BOTTOM edge length untouched and is allowed.
    panel._on_dimension_changed(rect, "rect_size", None, _Spin(200.0), _Spin(140.0))
    assert rect.rect().height() == pytest.approx(140.0)

    # The classification uses the item's LOCAL frame: at 60 degrees a rotated
    # rectangle's top edge is diagonal in scene space (round-7 review P1).
    rect._apply_rotation(60.0)
    panel._on_dimension_changed(rect, "rect_size", None, _Spin(240.0), _Spin(140.0))
    assert rect.rect().width() == pytest.approx(200.0), (
        "a rotated rectangle's constrained top edge was changed by a width edit"
    )

    # The same local-frame rule must not over-refuse: a height-only edit leaves
    # the constrained top edge alone even when the shape is rotated.
    panel._on_dimension_changed(rect, "rect_size", None, _Spin(200.0), _Spin(160.0))
    assert rect.rect().width() == pytest.approx(200.0)
    assert rect.rect().height() == pytest.approx(160.0), (
        "a rotated rectangle's height-only edit was refused although the "
        "constrained top edge is untouched"
    )


def test_a_rigid_shapes_edge_length_cannot_be_edited_as_a_distance(
    canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A rectangle cannot change its own edge length through the solver (#670 P0).

    Round 4: the same-item pin rule freed the rectangle, so editing its top-edge
    edge length translated it by metres.  It is refused instead.
    """
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.core.tools.constraint_tool import DistanceInputDialog

    scene = canvas.scene()
    rect = RectangleItem(100, 100, 200, 100)
    scene.addItem(rect)
    constraint = scene.constraint_graph.add_constraint(
        AnchorRef(rect.item_id, AnchorType.CORNER, 0),
        AnchorRef(rect.item_id, AnchorType.CORNER, 1),
        200.0,
        constraint_type=ConstraintType.EDGE_LENGTH,
    )
    before = QPointF(rect.pos())
    steps = canvas.command_manager.undo_depth

    monkeypatch.setattr(DistanceInputDialog, "exec", lambda _self: True)
    monkeypatch.setattr(DistanceInputDialog, "distance_cm", lambda _self: 400.0)
    canvas._edit_constraint_distance(constraint.constraint_id)

    assert rect.pos() == before, "the rectangle must not be translated"
    assert canvas.command_manager.undo_depth == steps
    assert constraint.target_distance == 200.0


def test_editing_a_distance_does_not_solve_an_unrelated_component(
    canvas: CanvasView, qtbot: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The distance-edit path is component-scoped (round-4 review P1)."""
    from open_garden_planner.core.tools.constraint_tool import DistanceInputDialog

    scene = canvas.scene()
    first = RectangleItem(0, 0, 100, 100)
    second = RectangleItem(900, 0, 100, 100)
    left = RectangleItem(0, 900, 100, 100)
    right = RectangleItem(300, 900, 100, 100)
    for item in (first, second, left, right):
        scene.addItem(item)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        100.0,
    )
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        500.0,
    )
    editable = graph.add_constraint(
        AnchorRef(left.item_id, AnchorType.CENTER),
        AnchorRef(right.item_id, AnchorType.CENTER),
        300.0,
    )
    before = {item: QPointF(item.pos()) for item in (first, second)}

    monkeypatch.setattr(DistanceInputDialog, "exec", lambda _self: True)
    monkeypatch.setattr(DistanceInputDialog, "distance_cm", lambda _self: 400.0)
    canvas._edit_constraint_distance(editable.constraint_id)

    for label, item in (("first", first), ("second", second)):
        assert item.pos() == before[item], (
            f"the unrelated {label} pair moved during a distance edit"
        )
    left_centre = left.mapToScene(left.boundingRect().center())
    right_centre = right.mapToScene(right.boundingRect().center())
    assert math.dist(
        (left_centre.x(), left_centre.y()), (right_centre.x(), right_centre.y())
    ) == pytest.approx(400.0, abs=0.1)


def test_a_vertex_drag_does_not_solve_an_unrelated_component(
    canvas: CanvasView, qtbot: object
) -> None:
    """The vertex-drag correction is component-scoped (round-4 review P1)."""
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    scene = canvas.scene()
    polygon = PolygonItem(
        [QPointF(0, 0), QPointF(200, 0), QPointF(200, 100), QPointF(0, 100)]
    )
    first = RectangleItem(0, 900, 100, 100)
    second = RectangleItem(900, 900, 100, 100)
    for item in (polygon, first, second):
        scene.addItem(item)
    graph = scene.constraint_graph
    graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.CORNER, 0),
        AnchorRef(polygon.item_id, AnchorType.CORNER, 1),
        200.0,
        constraint_type=ConstraintType.EDGE_LENGTH,
    )
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        100.0,
    )
    graph.add_constraint(
        AnchorRef(first.item_id, AnchorType.CENTER),
        AnchorRef(second.item_id, AnchorType.CENTER),
        500.0,
    )
    before = {item: QPointF(item.pos()) for item in (first, second)}
    old = QPointF(polygon.polygon().at(1))
    polygon._move_vertex_to(1, QPointF(240.0, 20.0))
    canvas._deferred_vertex_move = (
        polygon,
        1,
        old,
        QPointF(240.0, 20.0),
    )

    canvas._enforce_after_vertex_drag()

    for label, item in (("first", first), ("second", second)):
        assert item.pos() == before[item], (
            f"the unrelated {label} pair moved during a vertex drag"
        )


def test_a_locked_pair_does_not_block_a_compatible_link(
    canvas: CanvasView, qtbot: object
) -> None:
    """A FIXED pair outside the trial's component must not enter the trial."""
    from open_garden_planner.core.constraints import ConstraintType

    scene = canvas.scene()
    locked_a = RectangleItem(500, 500, 100, 100)
    locked_b = RectangleItem(800, 800, 100, 100)
    locked_a.setPos(500.0, 500.0)
    locked_b.setPos(800.0, 800.0)
    moving = RectangleItem(100, 100, 200, 200)
    reference = RectangleItem(600, 100, 200, 200)
    for item in (locked_a, locked_b, moving, reference):
        scene.addItem(item)
    graph = scene.constraint_graph
    for locked in (locked_a, locked_b):
        graph.add_constraint(
            AnchorRef(locked.item_id, AnchorType.CENTER),
            AnchorRef(locked.item_id, AnchorType.CENTER),
            0.0,
            constraint_type=ConstraintType.FIXED,
            target_x=locked.pos().x(),
            target_y=locked.pos().y(),
        )
    # A knowingly violated link between the two locked items.
    graph.add_constraint(
        AnchorRef(locked_a.item_id, AnchorType.CENTER),
        AnchorRef(locked_b.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.COINCIDENT,
    )

    assert canvas.is_constraint_feasible(
        AnchorRef(moving.item_id, AnchorType.CENTER),
        AnchorRef(reference.item_id, AnchorType.CENTER),
        500.0,
        ConstraintType.DISTANCE,
    ), "an out-of-component locked pair must not make the trial infeasible"


def test_point_on_edge_added_through_the_view_is_satisfied(
    canvas: CanvasView, qtbot: object
) -> None:
    """#669 end to end: the constraint the tool adds is on the edge and green."""
    from open_garden_planner.core.commands import AddConstraintCommand
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.core.measure_snapper import resolve_anchor_point
    from open_garden_planner.ui.panels.constraints_panel import ConstraintsPanel

    scene = canvas.scene()
    reference = RectangleItem(400, 400, 400, 300)
    moving = RectangleItem(800, 500, 50, 50)
    scene.addItem(reference)
    scene.addItem(moving)
    steps = canvas.command_manager.undo_depth
    before = QPointF(moving.pos())

    command = AddConstraintCommand(
        graph=scene.constraint_graph,
        anchor_a=AnchorRef(moving.item_id, AnchorType.CORNER, 0),
        anchor_b=AnchorRef(reference.item_id, AnchorType.CORNER, 1),
        target_distance=0.0,
        constraint_type=ConstraintType.POINT_ON_EDGE,
        anchor_c=AnchorRef(reference.item_id, AnchorType.CORNER, 3),
    )
    _add_constraint(canvas, command)

    assert canvas.command_manager.undo_depth == steps + 1, "one undo step"
    constraint = next(
        c
        for c in scene.constraint_graph.constraints.values()
        if c.constraint_type == ConstraintType.POINT_ON_EDGE
    )
    corner = resolve_anchor_point(moving, AnchorType.CORNER, 0)
    assert corner is not None
    assert corner.x() == pytest.approx(800.0, abs=0.1), "the corner is on the edge"

    panel = ConstraintsPanel()
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_scene(scene)
    assert panel._is_satisfied(constraint), "the row must not be red"

    canvas.command_manager.undo()
    assert not scene.constraint_graph.constraints
    assert moving.pos() == before, "undo must restore the pre-add position"


# ── #658: the Layer combo survives its own change signal ─────────────────


@pytest.mark.parametrize("state", ["hidden", "locked"])
def test_layer_combo_change_does_not_destroy_the_sender(
    canvas: CanvasView, qtbot: object, state: str
) -> None:
    """Moving an item to a hidden/locked layer deselects it mid-signal (#658).

    The selection change synchronously rebuilds the Properties panel; the old
    ``_clear_form`` called ``removeRow``, which destroyed the combo box while its
    own ``currentIndexChanged`` was still being delivered (a SIGSEGV on macOS,
    a silently dropped signal here).
    """
    from PyQt6 import sip
    from PyQt6.QtWidgets import QComboBox

    from open_garden_planner.models.layer import Layer

    scene = canvas.scene()
    target_layer = Layer(
        name="Target", visible=state != "hidden", locked=state == "locked"
    )
    scene.add_layer(target_layer)

    rect = RectangleItem(600, 700, 300, 200)
    scene.addItem(rect)
    rect.setSelected(True)

    panel = PropertiesPanel(command_manager=canvas.command_manager)
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_selected_items([rect])
    # The application wires the panel to the scene's selection; do the same so
    # the re-entrant rebuild happens exactly where it happens for the user.
    scene.selectionChanged.connect(
        lambda: panel.set_selected_items(list(scene.selectedItems()))
    )

    combo = next(
        child
        for child in panel.findChildren(QComboBox)
        if child.findData(target_layer.id) >= 0
    )
    alive: list[bool] = []

    def spy(_index: int) -> None:
        alive.append(not sip.isdeleted(combo))

    combo.currentIndexChanged.connect(spy)
    combo.setCurrentIndex(combo.findData(target_layer.id))

    assert alive == [True], "the change signal was dropped or the sender died in it"
    assert rect.layer_id == target_layer.id, "the item did move to the layer"
    assert panel._current_items == [], "the panel should have cleared"
    canvas.command_manager.undo()
    assert rect.layer_id != target_layer.id
    canvas.command_manager.redo()
    assert rect.layer_id == target_layer.id
