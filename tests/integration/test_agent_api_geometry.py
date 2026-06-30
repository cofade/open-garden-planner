"""Round-trip guard: ``queries.object_bbox`` over the REAL serialiser output.

The Qt-free unit tests in ``test_agent_api_queries.py`` pin the bbox maths against
hand-authored dicts; this test instead builds real items, serialises them through
``ProjectManager.snapshot_dict`` (the exact path the Agent API uses), and asserts
the bbox is correct for each geometry kind. It guards against the hand-authored
fixtures drifting from the serialiser keys — the class of bug (construction lines
falling through to a garbage ``(0,0,0,0)`` box) that the curated dicts can miss.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF

from open_garden_planner.agent_api import queries
from open_garden_planner.core import ProjectManager
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.items import (
    CircleItem,
    ConstructionCircleItem,
    ConstructionLineItem,
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
