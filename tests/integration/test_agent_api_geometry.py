"""REAL serializer/query geometry guards + the D2.6 live geometry projection.

The Qt-free unit tests in ``test_agent_api_queries.py`` pin bbox maths against
hand-authored dicts; the first test here instead builds real items, serialises them through
``ProjectManager.snapshot_dict`` (the exact path the Agent API uses), and asserts
the bbox is correct for each geometry kind. It guards against the hand-authored
fixtures drifting from the serialiser keys — the class of bug (construction lines
falling through to a garbage ``(0,0,0,0)`` box) that the curated dicts can miss.
The D2.6 tests then pin the separate live-Qt contract: rotated vertices come
from ``mapToScene``, an unchanged write round trip is exact, and curve/constraint
payloads are deterministic.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api import queries
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.geometry_apply import (
    apply_rotation,
    local_vertex_for_scene,
    scene_vertex_positions,
)
from open_garden_planner.ui.canvas.geometry_inspect import describe_geometry
from open_garden_planner.ui.canvas.items import (
    ArcItem,
    BezierItem,
    CircleItem,
    ConstructionCircleItem,
    ConstructionLineItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)


def _snapshot_for(scene: Any) -> dict[str, Any]:
    return ProjectManager().snapshot_dict(scene)


def _by_type(snapshot: dict[str, Any], type_name: str) -> dict[str, Any]:
    return next(o for o in snapshot["objects"] if o.get("type") == type_name)


def test_object_bbox_matches_real_serialiser(canvas: Any, qtbot: Any) -> None:
    scene = canvas.scene()
    # One of each tricky geometry kind, placed away from the origin so a garbage
    # (0,0,0,0) bbox can't accidentally look right.
    scene.addItem(RectangleItem(100, 50, 200, 80, object_type=ObjectType.RAISED_BED))
    scene.addItem(CircleItem(400, 300, 25, object_type=ObjectType.TREE))
    scene.addItem(ConstructionLineItem(QPointF(500, 600), QPointF(700, 800)))
    scene.addItem(ConstructionCircleItem(150, 250, 30))
    scene.addItem(
        PolylineItem([QPointF(10, 20), QPointF(60, 20), QPointF(60, 90)])
    )

    snapshot = _snapshot_for(scene)

    rect = _by_type(snapshot, "rectangle")
    assert queries.object_bbox(rect) == (100.0, 50.0, 200.0, 80.0)

    circle = _by_type(snapshot, "circle")
    assert queries.object_bbox(circle) == (375.0, 275.0, 50.0, 50.0)

    # Regression: construction lines serialise as x1/y1/x2/y2 — previously this
    # fell through to (0,0,0,0) and polluted every spatial query.
    cline = _by_type(snapshot, "construction_line")
    assert queries.object_bbox(cline) == (500.0, 600.0, 200.0, 200.0)
    assert queries.object_center(cline) == (600.0, 700.0)

    ccircle = _by_type(snapshot, "construction_circle")
    assert queries.object_bbox(ccircle) == (120.0, 220.0, 60.0, 60.0)

    polyline = _by_type(snapshot, "polyline")
    assert queries.object_bbox(polyline) == (10.0, 20.0, 50.0, 70.0)

    # No serialised object may yield a garbage zero-size box at the origin here.
    for obj in snapshot["objects"]:
        x, y, w, h = queries.object_bbox(obj)
        assert (x, y, w, h) != (0.0, 0.0, 0.0, 0.0), obj.get("type")


def test_rotated_polygon_geometry_is_live_scene_space_and_round_trips_exactly(
    canvas: Any, qtbot: Any  # noqa: ARG001
) -> None:
    """US-D2.6: raw serialiser points are not the stable geometry read.

    A rotated polygon's stored local points differ from its live scene vertices.
    ``get_geometry`` must report the latter, and feeding one unchanged vertex
    back through the write conversion must reuse the exact local ``QPointF`` so
    an inverse transform cannot perturb the object by invisible ~1e-14 cm noise.
    """
    scene = canvas.scene()
    polygon = PolygonItem(
        [QPointF(0.0, 0.0), QPointF(180.0, 0.0), QPointF(140.0, 120.0), QPointF(20.0, 90.0)],
        object_type=ObjectType.GARDEN_BED,
    )
    apply_rotation(polygon, 37.0)
    scene.addItem(polygon)

    raw = ProjectManager()._serialize_item(polygon)
    assert raw is not None
    raw_points = raw["points"]
    live_points = scene_vertex_positions(polygon)
    assert any(
        (raw_point["x"], raw_point["y"]) != (live.x(), live.y())
        for raw_point, live in zip(raw_points, live_points, strict=True)
    )

    described = describe_geometry(
        polygon,
        center=queries.object_center(raw),
        constraints=[],
    )
    assert described["type"] == "polygon"
    assert described["vertex_editable"] is True
    assert described["vertex_count"] == 4
    assert described["minimum_vertex_count"] == 3
    assert described["vertices"] == [
        {"x_cm": live.x(), "y_cm": live.y()} for live in live_points
    ]

    for index, live in enumerate(live_points):
        unchanged_local = local_vertex_for_scene(
            polygon, index, live.x(), live.y()
        )
        assert unchanged_local == polygon._get_vertex_position(index)


def test_get_geometry_payload_covers_constraints_and_curve_families(
    canvas: Any, qtbot: Any  # noqa: ARG001
) -> None:
    """The stable read is curated, complete enough to explain a refusal."""
    from open_garden_planner.core.constraints import AnchorRef
    from open_garden_planner.core.measure_snapper import AnchorType

    scene = canvas.scene()
    arc = ArcItem(QPointF(300.0, 220.0), 80.0, 20.0, 120.0, name="Arc")
    bezier = BezierItem(
        [QPointF(600.0, 120.0), QPointF(700.0, 260.0)],
        [QPointF(570.0, 160.0), QPointF(650.0, 210.0)],
        [QPointF(630.0, 90.0), QPointF(730.0, 280.0)],
        name="Bezier",
    )
    scene.addItem(arc)
    scene.addItem(bezier)
    constraint = scene.constraint_graph.add_constraint(
        AnchorRef(arc.item_id, AnchorType.CENTER),
        AnchorRef(bezier.item_id, AnchorType.CENTER),
        250.0,
    )

    arc_geometry = describe_geometry(
        arc,
        center=(300.0, 220.0),
        constraints=scene.constraint_graph.get_item_constraints(arc.item_id),
    )
    assert arc_geometry["curve"] == {
        "kind": "arc",
        "center": {"x_cm": 300.0, "y_cm": 220.0},
        "radius_cm": 80.0,
        "start_deg": 20.0,
        "span_deg": 120.0,
        "through": {
            "x_cm": arc.through_point().x(),
            "y_cm": arc.through_point().y(),
        },
        "anchors": [],
        "handles_in": [],
        "handles_out": [],
    }
    assert arc_geometry["is_constrained"] is True
    assert arc_geometry["constraints"][0]["constraint_id"] == str(
        constraint.constraint_id
    )

    bezier_geometry = describe_geometry(
        bezier,
        center=(650.0, 190.0),
        constraints=[],
    )
    curve = bezier_geometry["curve"]
    assert curve["kind"] == "bezier"
    assert len(curve["anchors"]) == 2
    assert len(curve["handles_in"]) == 2
    assert len(curve["handles_out"]) == 2
    assert bezier_geometry["is_constrained"] is False

    construction = ConstructionLineItem(QPointF(10.0, 20.0), QPointF(90.0, 80.0))
    construction.setPos(25.0, 35.0)
    scene.addItem(construction)
    construction_geometry = describe_geometry(
        construction,
        center=(75.0, 100.0),
        constraints=[],
    )
    assert construction_geometry["endpoints"] == [
        {"x_cm": 35.0, "y_cm": 55.0},
        {"x_cm": 115.0, "y_cm": 115.0},
    ]


def test_get_geometry_reports_native_extents_radius_and_leader(
    canvas: Any, qtbot: Any  # noqa: ARG001
) -> None:
    """The stable read covers the non-vertex families named by #330."""
    from open_garden_planner.ui.canvas.items import CalloutItem

    scene = canvas.scene()
    rectangle = RectangleItem(100.0, 200.0, 180.0, 90.0)
    circle = CircleItem(500.0, 400.0, 45.0)
    callout = CalloutItem(
        QPointF(800.0, 600.0), QPointF(-70.0, 50.0), "Inspect canopy"
    )
    for item in (rectangle, circle, callout):
        scene.addItem(item)

    rectangle_geometry = describe_geometry(
        rectangle, center=(190.0, 245.0), constraints=[]
    )
    assert rectangle_geometry["width_cm"] == 180.0
    assert rectangle_geometry["height_cm"] == 90.0

    circle_geometry = describe_geometry(circle, center=(500.0, 400.0), constraints=[])
    assert circle_geometry["radius_cm"] == 45.0

    callout_geometry = describe_geometry(
        callout, center=(800.0, 600.0), constraints=[]
    )
    assert callout_geometry["leader"] == {
        "tip": {"x_cm": 800.0, "y_cm": 600.0},
        "box_corner": {"x_cm": 730.0, "y_cm": 650.0},
    }
