"""Incidence-constraint regressions (#669, #670).

Issue #669: the Constraints panel had no branch for POINT_ON_EDGE,
POINT_ON_CIRCLE or TANGENT, so it fell through to a point-to-point distance
check.  A satisfied POINT_ON_EDGE compared the point with the edge's *first
endpoint* and was painted red.

Issue #670 records six reproduced root causes in the incidence pipeline:
unrelated components blocking a compatible link, a trial that pins different
references than the application, a false conflict after a rigid polygon
translation, a solver precision the panel then calls violated, a third anchor
that does not follow a deformed endpoint, and a stored polygon-edge reference
that loses its edge when the edge's direction changes.
"""

from __future__ import annotations

import math
from uuid import uuid4

import pytest
from PyQt6.QtCore import QPointF

from open_garden_planner.core.constraints import (
    APPLY_TOLERANCE_CM,
    DISPLAY_TOLERANCE_CM,
    AnchorRef,
    ConstraintGraph,
    ConstraintType,
    incidence_error,
)
from open_garden_planner.core.measure_snapper import (
    AnchorType,
    anchor_offset_table,
    resolve_anchor_point,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.panels.constraints_panel import ConstraintsPanel


@pytest.fixture()
def canvas(qtbot: object) -> CanvasView:
    scene = CanvasScene(width_cm=8000, height_cm=6000)
    view = CanvasView(scene)
    qtbot.addWidget(view)  # type: ignore[attr-defined]
    view.set_snap_enabled(False)
    return view


# ── #669: the panel must agree with the geometry ──────────────────────────


def _panel_for(scene: CanvasScene, qtbot: object) -> ConstraintsPanel:
    panel = ConstraintsPanel()
    qtbot.addWidget(panel)  # type: ignore[attr-defined]
    panel.set_scene(scene)
    return panel


@pytest.mark.parametrize(
    ("offset", "satisfied"),
    [
        (0.0, True),      # exactly on the edge, far from either endpoint
        (0.05, True),     # sub-millimetre, still inside the 1 mm display band
        (1.0, False),     # 1 cm off the edge is visibly wrong
    ],
)
def test_point_on_edge_panel_satisfaction(
    canvas: CanvasView, qtbot: object, offset: float, satisfied: bool
) -> None:
    scene = canvas.scene()
    reference = RectangleItem(400, 400, 400, 300)  # right edge from (800,400) to (800,700)
    scene.addItem(reference)
    # Corner 0 of the moving rect lands on the reference's right edge.
    moving = RectangleItem(800 + offset, 500, 50, 50)
    scene.addItem(moving)

    graph = scene.constraint_graph
    constraint = graph.add_constraint(
        AnchorRef(moving.item_id, AnchorType.CORNER, 0),
        AnchorRef(reference.item_id, AnchorType.CORNER, 1),
        0.0,
        constraint_type=ConstraintType.POINT_ON_EDGE,
        anchor_c=AnchorRef(reference.item_id, AnchorType.CORNER, 3),
    )

    panel = _panel_for(scene, qtbot)
    assert panel._is_satisfied(constraint) is satisfied


def test_point_on_edge_endpoint_is_not_the_measure(canvas: CanvasView, qtbot) -> None:
    """The old fall-through compared A with B, so a point on a long edge failed."""
    scene = canvas.scene()
    reference = RectangleItem(400, 400, 400, 300)
    scene.addItem(reference)
    # Corner 0 sits in the MIDDLE of the top edge: 200 cm from either corner.
    moving = RectangleItem(500, 400, 50, 50)
    scene.addItem(moving)
    constraint = scene.constraint_graph.add_constraint(
        AnchorRef(moving.item_id, AnchorType.CORNER, 0),
        AnchorRef(reference.item_id, AnchorType.CORNER, 0),
        0.0,
        constraint_type=ConstraintType.POINT_ON_EDGE,
        anchor_c=AnchorRef(reference.item_id, AnchorType.CORNER, 1),
    )
    panel = _panel_for(scene, qtbot)
    assert incidence_error(
        ConstraintType.POINT_ON_EDGE, (500.0, 400.0), (400.0, 400.0), (800.0, 400.0), 0.0
    ) == pytest.approx(0.0)
    assert panel._is_satisfied(constraint)


@pytest.mark.parametrize(
    ("radius_delta", "satisfied"),
    [(0.0, True), (0.4, False)],
)
def test_point_on_circle_panel_satisfaction(qtbot, radius_delta, satisfied) -> None:
    scene = CanvasScene(width_cm=4000, height_cm=4000)
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    circle = CircleItem(500.0, 500.0, 100.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(circle)
    # The marker's centre starts at exactly the circle's radius from its centre.
    marker = RectangleItem(575 + radius_delta, 475, 50, 50)
    scene.addItem(marker)
    constraint = scene.constraint_graph.add_constraint(
        AnchorRef(marker.item_id, AnchorType.CENTER),
        AnchorRef(circle.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.POINT_ON_CIRCLE,
    )
    panel = _panel_for(scene, qtbot)
    assert panel._is_satisfied(constraint) is satisfied


def test_tangent_panel_satisfaction(canvas: CanvasView, qtbot) -> None:
    scene = canvas.scene()
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem

    line = RectangleItem(400, 400, 200, 10)
    scene.addItem(line)
    # A circle centred on the perpendicular through A: tangent contact at A.
    circle = CircleItem(400.0, 450.0, 50.0, object_type=ObjectType.GENERIC_CIRCLE)
    scene.addItem(circle)
    constraint = scene.constraint_graph.add_constraint(
        AnchorRef(line.item_id, AnchorType.CORNER, 0),
        AnchorRef(circle.item_id, AnchorType.CENTER),
        50.0,
        constraint_type=ConstraintType.TANGENT,
        anchor_c=AnchorRef(line.item_id, AnchorType.CORNER, 1),
    )
    panel = _panel_for(scene, qtbot)
    assert panel._is_satisfied(constraint)


# ── #670 cause 1: an unrelated violated component must not block a link ───


def test_unrelated_violated_component_does_not_reject_a_compatible_link(qtbot) -> None:
    graph = ConstraintGraph()
    a, b, c, d = uuid4(), uuid4(), uuid4(), uuid4()
    # Two contradictory target distances on the SAME pair: irreconcilable.
    graph.add_constraint(AnchorRef(a, AnchorType.CENTER), AnchorRef(b, AnchorType.CENTER), 100.0)
    graph.add_constraint(AnchorRef(a, AnchorType.CENTER), AnchorRef(b, AnchorType.CENTER), 500.0)

    positions = {a: (0.0, 0.0), b: (1000.0, 0.0), c: (0.0, 1000.0), d: (300.0, 1000.0)}
    feasible = graph.validate_constraint(
        AnchorRef(c, AnchorType.CENTER),
        AnchorRef(d, AnchorType.CENTER),
        300.0,
        ConstraintType.DISTANCE,
        positions,
        {},
    )
    assert feasible is True, "a broken component elsewhere must not veto this link"


# ── #670 cause 2: the trial must pin what the application pins ────────────


def test_trial_rejects_a_link_the_application_could_not_honour(qtbot) -> None:
    graph = ConstraintGraph()
    moving, reference = uuid4(), uuid4()
    # A is locked where it is; B is construction geometry (also pinned).
    graph.add_constraint(
        AnchorRef(moving, AnchorType.CENTER),
        AnchorRef(moving, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
        target_x=0.0,
        target_y=0.0,
    )
    positions = {moving: (0.0, 0.0), reference: (500.0, 0.0)}
    # The distance the user asks for cannot be reached: neither side may move.
    assert (
        graph.validate_constraint(
            AnchorRef(moving, AnchorType.CENTER),
            AnchorRef(reference, AnchorType.CENTER),
            100.0,
            ConstraintType.DISTANCE,
            positions,
            {},
            pinned_items={reference},
        )
        is False
    ), "a trial that pins what the application pins must refuse an unreachable link"


def test_trial_and_application_agree_for_a_construction_reference(
    canvas: CanvasView, qtbot
) -> None:
    """The real view path: a fixed item against a construction line is infeasible."""
    from open_garden_planner.ui.canvas.items.construction_item import (
        ConstructionLineItem,
    )

    scene = canvas.scene()
    construction = ConstructionLineItem(QPointF(600.0, 400.0), QPointF(600.0, 700.0))
    scene.addItem(construction)
    moving = RectangleItem(100, 100, 60, 60)
    scene.addItem(moving)
    scene.constraint_graph.add_constraint(
        AnchorRef(moving.item_id, AnchorType.CENTER),
        AnchorRef(moving.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
        target_x=moving.pos().x(),
        target_y=moving.pos().y(),
    )
    feasible = canvas.is_constraint_feasible(
        AnchorRef(moving.item_id, AnchorType.CENTER),
        AnchorRef(construction.item_id, AnchorType.ENDPOINT, 0),
        100.0,
        ConstraintType.DISTANCE,
    )
    assert feasible is False


# ── #670 cause 3: a rigidly translated polygon is not a conflict ──────────


def test_rigid_polygon_translation_reports_no_false_conflict(qtbot) -> None:
    """A rigid translation moves the vertices, not just the item (#670 cause 3)."""
    graph = ConstraintGraph()
    polygon_id, target_id = uuid4(), uuid4()
    # An existing intra-item distance from corner 0 to the polygon's centre.
    # It is invariant under a rigid translation, so a compatible trial that
    # slides the whole polygon must not report it as violated.
    corner, centre = (0.0, 0.0), (100.0, 50.0)
    existing = graph.add_constraint(
        AnchorRef(polygon_id, AnchorType.CORNER, 0),
        AnchorRef(polygon_id, AnchorType.CENTER),
        math.dist(corner, centre),
    )
    assert existing.constraint_type == ConstraintType.DISTANCE
    # A second vertex reference makes the polygon deformable, so its vertices
    # are tracked separately from the item — the path this defect lives on.
    graph.add_constraint(
        AnchorRef(polygon_id, AnchorType.CORNER, 0),
        AnchorRef(polygon_id, AnchorType.CORNER, 1),
        200.0,
        constraint_type=ConstraintType.EDGE_LENGTH,
    )

    item_positions = {polygon_id: (0.0, 0.0), target_id: (400.0, 50.0)}
    anchor_offsets = {
        (polygon_id, AnchorType.CORNER, 0): corner,
        (polygon_id, AnchorType.CORNER, 1): (200.0, 0.0),
        (polygon_id, AnchorType.CENTER, 0): centre,
        (target_id, AnchorType.CENTER, 0): (0.0, 0.0),
    }
    deformable_vertices = {
        polygon_id: [(0.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)]
    }
    from open_garden_planner.core.constraints import Constraint

    # Trial: slide the polygon so its centre lands on the target at (400, 50).
    trial_constraint = Constraint(
        constraint_id=uuid4(),
        anchor_a=AnchorRef(polygon_id, AnchorType.CENTER),
        anchor_b=AnchorRef(target_id, AnchorType.CENTER),
        target_distance=0.0,
        constraint_type=ConstraintType.COINCIDENT,
    )
    conflicts = graph.find_conflicting_constraints(
        trial_constraint,
        item_positions,
        anchor_offsets,
        deformable_items={polygon_id},
        deformable_vertices=deformable_vertices,
        tolerance=DISPLAY_TOLERANCE_CM,
    )
    assert conflicts == [], (
        "a rigidly translated polygon was reconstructed at its pre-solve "
        "vertex position, so a satisfied constraint looked violated"
    )


# ── #670 cause 4: the application reaches the displayed precision ─────────


def test_trial_refuses_a_relation_the_panel_would_show_red(qtbot) -> None:
    """A 0.5 cm gap between pinned anchors is visibly violated, so refuse it."""
    graph = ConstraintGraph()
    a, b = uuid4(), uuid4()
    positions = {a: (0.0, 0.0), b: (0.5, 0.0)}
    assert (
        graph.validate_constraint(
            AnchorRef(a, AnchorType.CENTER),
            AnchorRef(b, AnchorType.CENTER),
            0.0,
            ConstraintType.COINCIDENT,
            positions,
            {},
            pinned_items={a, b},
        )
        is False
    )
    # ...while a gap inside the display band is accepted.
    positions = {a: (0.0, 0.0), b: (0.05, 0.0)}
    assert graph.validate_constraint(
        AnchorRef(a, AnchorType.CENTER),
        AnchorRef(b, AnchorType.CENTER),
        0.0,
        ConstraintType.COINCIDENT,
        positions,
        {},
        pinned_items={a, b},
    )


# ── #670 cause 5: the third anchor follows a deformed endpoint ────────────


def test_point_on_edge_follows_a_deformed_second_endpoint(qtbot) -> None:
    graph = ConstraintGraph()
    polygon_id, anchor_item_id, fixed_id = uuid4(), uuid4(), uuid4()

    # Polygon v0=(0,0), v1=(100,0), v2=(100,100), v3=(0,100) at pos (0, 0).
    vertices = {
        polygon_id: [
            (0.0, 0.0),
            (100.0, 0.0),
            (100.0, 100.0),
            (0.0, 100.0),
        ]
    }
    # Force v1 (and v0) to be deformable, then pull v1 toward a fixed point at
    # (150, 150) so edge v0→v1 is no longer the horizontal line it started as.
    graph.add_constraint(
        AnchorRef(polygon_id, AnchorType.CORNER, 0),
        AnchorRef(polygon_id, AnchorType.CORNER, 1),
        100.0,
    )
    graph.add_constraint(
        AnchorRef(polygon_id, AnchorType.CORNER, 1),
        AnchorRef(fixed_id, AnchorType.CENTER),
        50.0,
    )
    graph.add_constraint(
        AnchorRef(polygon_id, AnchorType.CORNER, 1),
        AnchorRef(polygon_id, AnchorType.CORNER, 2),
        100.0,
    )
    # A point on the moving edge, initially off it.
    graph.add_constraint(
        AnchorRef(anchor_item_id, AnchorType.CORNER, 0),
        AnchorRef(polygon_id, AnchorType.CORNER, 0),
        0.0,
        constraint_type=ConstraintType.POINT_ON_EDGE,
        anchor_c=AnchorRef(polygon_id, AnchorType.CORNER, 1),
    )

    item_positions = {
        polygon_id: (0.0, 0.0),
        anchor_item_id: (40.0, 60.0),
        fixed_id: (150.0, 150.0),
    }
    anchor_offsets = {
        (polygon_id, AnchorType.CORNER, 0): (0.0, 0.0),
        (polygon_id, AnchorType.CORNER, 1): (100.0, 0.0),
        (polygon_id, AnchorType.CORNER, 2): (100.0, 100.0),
        (anchor_item_id, AnchorType.CORNER, 0): (0.0, 0.0),
        (fixed_id, AnchorType.CENTER): (0.0, 0.0),
    }
    result = graph.solve_anchored(
        item_positions,
        anchor_offsets,
        pinned_items={fixed_id},
        max_iterations=50,
        tolerance=APPLY_TOLERANCE_CM,
        deformable_items={polygon_id},
        deformable_vertices=vertices,
    )

    def vertex(uid, index, originals):
        delta = result.vertex_deltas.get((uid, index), (0.0, 0.0))
        item_dx, item_dy = result.item_deltas.get(uid, (0.0, 0.0))
        base = originals[index]
        return (base[0] + item_dx + delta[0], base[1] + item_dy + delta[1])

    final_b = vertex(polygon_id, 0, vertices[polygon_id])
    final_c = vertex(polygon_id, 1, vertices[polygon_id])
    final_a = (
        item_positions[anchor_item_id][0]
        + result.item_deltas.get(anchor_item_id, (0.0, 0.0))[0],
        item_positions[anchor_item_id][1]
        + result.item_deltas.get(anchor_item_id, (0.0, 0.0))[1],
    )
    residual = incidence_error(
        ConstraintType.POINT_ON_EDGE, final_a, final_b, final_c, 0.0
    )
    assert residual is not None
    assert residual <= DISPLAY_TOLERANCE_CM, (
        f"A is {residual:.2f} cm off the edge after C was deformed"
    )


# ── #670 cause 6: a stored edge reference survives a direction change ─────


def test_stored_edge_reference_survives_a_direction_change(qtbot) -> None:
    from PyQt6.QtGui import QPolygonF

    scene = CanvasScene(width_cm=4000, height_cm=4000)
    polygon = PolygonItem([QPointF(0, 0), QPointF(0, 200), QPointF(200, 200), QPointF(200, 0)])
    scene.addItem(polygon)
    # Edge 0 is v0→v1: vertical, classified EDGE_LEFT or EDGE_RIGHT.
    initial = resolve_anchor_point(polygon, AnchorType.EDGE_RIGHT, 0)
    assert initial is not None
    assert initial.x() == pytest.approx(0.0), "edge 0 is vertical before the edit"

    # Turn edge 0 horizontal (v0 moves right): the classification must change.
    polygon.setPolygon(
        QPolygonF([QPointF(300, 0), QPointF(0, 200), QPointF(200, 200), QPointF(200, 0)])
    )
    after = resolve_anchor_point(polygon, AnchorType.EDGE_RIGHT, 0)
    assert after is not None
    assert after.x() == pytest.approx(150.0), (
        "the stored EDGE_RIGHT reference followed the edge it was stored on"
    )
    assert after.y() == pytest.approx(100.0)

    # The solver's offset table must answer the same stored key.
    table = anchor_offset_table(polygon)
    for edge_type in (
        AnchorType.EDGE_TOP,
        AnchorType.EDGE_BOTTOM,
        AnchorType.EDGE_LEFT,
        AnchorType.EDGE_RIGHT,
    ):
        assert (edge_type, 0) in table, f"no offset for a stored {edge_type.name}"
        assert table[(edge_type, 0)] == pytest.approx((150.0, 100.0))


def test_vertex_topology_edit_shifts_every_indexed_anchor(qtbot) -> None:
    """The graph contract: insert/delete renumber EDGE anchors too.

    Round-3 review P1: only CORNER/ENDPOINT were shifted, so an edge-middle
    constraint silently moved to a different edge.
    """
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType

    graph = ConstraintGraph()
    item_id = uuid4()
    corner = graph.add_constraint(
        AnchorRef(item_id, AnchorType.CORNER, 3),
        AnchorRef(item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    edge = graph.add_constraint(
        AnchorRef(item_id, AnchorType.EDGE_TOP, 3),
        AnchorRef(item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    split = graph.add_constraint(
        AnchorRef(item_id, AnchorType.EDGE_BOTTOM, 0),
        AnchorRef(item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )

    graph.shift_vertex_indices(item_id, 1, +1)
    assert corner.anchor_a.anchor_index == 4
    assert edge.anchor_a.anchor_index == 4
    # The split edge is index 0; the caller drops it rather than shifting it.
    assert split.anchor_a.anchor_index == 0

    graph.drop_edge_constraints(item_id, {0, 1})
    assert split.constraint_id not in graph.constraints
    assert corner.constraint_id in graph.constraints


def test_vertex_insert_then_undo_restores_indexed_anchors(
    canvas: CanvasView, qtbot: object
) -> None:
    """The command owns the renumbering, so undo restores it (round-4 P1)."""
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    scene = canvas.scene()
    polygon = PolygonItem(
        [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
    )
    scene.addItem(polygon)
    graph = scene.constraint_graph
    corner = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.CORNER, 3),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    closing_edge = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.EDGE_TOP, 3),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    split_edge = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.EDGE_BOTTOM, 0),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )

    polygon._add_vertex_at_edge(0, QPointF(50.0, -20.0))
    assert polygon.polygon().count() == 5
    assert corner.anchor_a.anchor_index == 4
    assert closing_edge.anchor_a.anchor_index == 4
    assert split_edge.constraint_id not in graph.constraints

    canvas.command_manager.undo()
    assert polygon.polygon().count() == 4
    assert graph.constraints[corner.constraint_id].anchor_a.anchor_index == 3
    assert graph.constraints[closing_edge.constraint_id].anchor_a.anchor_index == 3
    assert split_edge.constraint_id in graph.constraints

    canvas.command_manager.redo()
    assert polygon.polygon().count() == 5
    assert graph.constraints[corner.constraint_id].anchor_a.anchor_index == 4


def test_vertex_delete_of_the_first_vertex_drops_the_closing_edge(
    canvas: CanvasView, qtbot: object
) -> None:
    """Deleting vertex 0 removes the closing edge, not the wrong one."""
    from open_garden_planner.core.constraints import AnchorRef, ConstraintType
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem

    scene = canvas.scene()
    polygon = PolygonItem(
        [QPointF(0, 0), QPointF(100, 0), QPointF(100, 100), QPointF(0, 100)]
    )
    scene.addItem(polygon)
    graph = scene.constraint_graph
    closing_edge = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.EDGE_TOP, 3),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    later_edge = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.EDGE_TOP, 1),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )
    corner = graph.add_constraint(
        AnchorRef(polygon.item_id, AnchorType.CORNER, 2),
        AnchorRef(polygon.item_id, AnchorType.CENTER),
        100.0,
        constraint_type=ConstraintType.DISTANCE,
    )

    polygon._delete_vertex(0)
    assert polygon.polygon().count() == 3
    assert closing_edge.constraint_id not in graph.constraints
    assert graph.constraints[later_edge.constraint_id].anchor_a.anchor_index == 0
    assert graph.constraints[corner.constraint_id].anchor_a.anchor_index == 1

    canvas.command_manager.undo()
    assert polygon.polygon().count() == 4
    assert graph.constraints[closing_edge.constraint_id].anchor_a.anchor_index == 3
    assert graph.constraints[later_edge.constraint_id].anchor_a.anchor_index == 1
    assert graph.constraints[corner.constraint_id].anchor_a.anchor_index == 2


def test_incidence_error_definitions(qtbot) -> None:
    """The shared residual: line distance, radius gap and tangency."""
    # Point (5, 3) against the x axis through (0, 0) and (10, 0).
    assert incidence_error(
        ConstraintType.POINT_ON_EDGE, (5.0, 3.0), (0.0, 0.0), (10.0, 0.0), 0.0
    ) == pytest.approx(3.0)
    # On the infinite line, beyond the segment: still zero (matches the solver).
    assert incidence_error(
        ConstraintType.POINT_ON_EDGE, (50.0, 0.0), (0.0, 0.0), (10.0, 0.0), 0.0
    ) == pytest.approx(0.0)
    assert incidence_error(
        ConstraintType.POINT_ON_CIRCLE, (105.0, 0.0), (0.0, 0.0), None, 100.0
    ) == pytest.approx(5.0)
    # Radius (B−A) is perpendicular to the edge (A→C): tangent at A.
    assert incidence_error(
        ConstraintType.TANGENT, (0.0, 0.0), (0.0, 50.0), (100.0, 0.0), 50.0
    ) == pytest.approx(0.0)
    assert incidence_error(
        ConstraintType.TANGENT, (0.0, 0.0), (50.0, 50.0), (100.0, 0.0), 50.0
    ) == pytest.approx(50.0, abs=0.01)
    assert incidence_error(ConstraintType.DISTANCE, (0.0, 0.0), (1.0, 0.0), None, 1.0) is None
