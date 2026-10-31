"""Constraint data-integrity regressions (#655, #656, #662).

Issue #655: a ``FIXED`` constraint lost its ``target_x``/``target_y`` on
``ConstraintGraph.from_list()``, so a saved position lock came back as a badge
that could still be dragged (and the next save erased the lock for good).

Issue #656: ``RemoveConstraintCommand.undo()`` restored everything about a
removed constraint except ``anchor_c``, so undoing the removal of a
three-anchor constraint left it structurally different.

Issue #662: a ``FIXED`` item kept ``ItemIsMovable``, so Qt moved it on every
drag step and the view reset it afterwards — six phantom positions per drag.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from open_garden_planner.core.commands import RemoveConstraintCommand
from open_garden_planner.core.constraints import (
    AnchorRef,
    ConstraintGraph,
    ConstraintType,
)
from open_garden_planner.core.measure_snapper import AnchorType
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

FIXED_TARGET = (123.0, 456.0)


def _fixed_constraint_dict(item_id, target_x=None, target_y=None) -> dict:
    data = {
        "constraint_id": str(uuid4()),
        "constraint_type": "FIXED",
        "anchor_a": {
            "item_id": str(item_id),
            "anchor_type": "CENTER",
            "anchor_index": 0,
        },
        "anchor_b": {
            "item_id": str(item_id),
            "anchor_type": "CENTER",
            "anchor_index": 0,
        },
        "target_distance": 0.0,
    }
    if target_x is not None:
        data["target_x"] = target_x
    if target_y is not None:
        data["target_y"] = target_y
    return data


# ── #655: FIXED targets must survive the graph round trip ──────────────────


def test_fixed_targets_survive_graph_round_trip(qtbot) -> None:
    """from_list() must pass target_x/target_y to add_constraint()."""
    item_id = uuid4()
    graph = ConstraintGraph.from_list(
        [_fixed_constraint_dict(item_id, *FIXED_TARGET)]
    )

    constraint = next(iter(graph.constraints.values()))
    assert (constraint.target_x, constraint.target_y) == FIXED_TARGET

    # ...and a second round trip keeps them (the file must not lose them again)
    again = ConstraintGraph.from_list(graph.to_list())
    kept = next(iter(again.constraints.values()))
    assert (kept.target_x, kept.target_y) == FIXED_TARGET


def test_fixed_without_target_pins_the_item_where_it_is(qtbot) -> None:
    """A target-less FIXED constraint is immobile, not skipped (#655)."""
    item_id, other_id = uuid4(), uuid4()
    graph = ConstraintGraph()
    graph.add_constraint(
        AnchorRef(item_id, AnchorType.CENTER),
        AnchorRef(item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
    )
    graph.add_constraint(
        AnchorRef(item_id, AnchorType.CENTER),
        AnchorRef(other_id, AnchorType.CENTER),
        100.0,
    )

    positions = {item_id: (0.0, 0.0), other_id: (400.0, 0.0)}
    result = graph.solve_anchored(positions, {})

    assert item_id not in result.item_deltas, (
        "a FIXED item without stored targets must not be movable"
    )
    assert other_id in result.item_deltas, "the partner must still be solved"


def test_load_drops_a_fixed_constraint_whose_item_is_missing(qtbot) -> None:
    """A dangling FIXED record is removed, not left pinning a dead frame."""
    from uuid import uuid4

    from open_garden_planner.core.constraints import AnchorRef, ConstraintGraph
    from open_garden_planner.core.measure_snapper import AnchorType
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    scene = CanvasScene(width_cm=1000, height_cm=800)
    rect = RectangleItem(100, 200, 300, 150)
    scene.addItem(rect)
    graph = ConstraintGraph()
    graph.add_constraint(
        AnchorRef(rect.item_id, AnchorType.CENTER),
        AnchorRef(rect.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
    )
    ghost = uuid4()
    graph.add_constraint(
        AnchorRef(ghost, AnchorType.CENTER),
        AnchorRef(ghost, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
    )
    retargeted = graph.retarget_fixed_constraints(
        {rect.item_id: (rect.pos().x(), rect.pos().y())}
    )
    assert retargeted == 1
    assert [c.anchor_a.item_id for c in graph.constraints.values()] == [rect.item_id]


def test_load_repairs_a_legacy_fixed_constraint_without_targets(
    qtbot, tmp_path
) -> None:
    """A file written before the fix is repaired from the loaded item (#655)."""
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene(width_cm=1000, height_cm=800)
    rect = RectangleItem(100, 200, 300, 150)
    scene.addItem(rect)
    graph = ConstraintGraph()
    graph.add_constraint(
        AnchorRef(rect.item_id, AnchorType.CENTER),
        AnchorRef(rect.item_id, AnchorType.CENTER),
        0.0,
        constraint_type=ConstraintType.FIXED,
    )
    scene.constraint_graph = graph

    path = tmp_path / "legacy-fixed.ogp"
    ProjectManager().save(scene, path)

    # Simulate a legacy file: the FIXED record carries no targets.
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    for constraint in raw["constraints"]:
        constraint.pop("target_x", None)
        constraint.pop("target_y", None)
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded_scene = CanvasScene(width_cm=1000, height_cm=800)
    ProjectManager().load(loaded_scene, path)

    loaded_graph = loaded_scene.constraint_graph
    constraint = next(iter(loaded_graph.constraints.values()))
    loaded_item = next(
        item for item in loaded_scene.items() if isinstance(item, RectangleItem)
    )
    assert (constraint.target_x, constraint.target_y) == (
        loaded_item.pos().x(),
        loaded_item.pos().y(),
    ), "the repair must use the loaded item's own frame"

    # Saving again writes the repaired lock, so the loss is not permanent.
    again = tmp_path / "repaired.ogp"
    ProjectManager().save(loaded_scene, again)
    saved = json.loads(again.read_text(encoding="utf-8"))
    assert saved["constraints"][0]["target_x"] == constraint.target_x
    assert saved["constraints"][0]["target_y"] == constraint.target_y


# ── #656: RemoveConstraintCommand.undo restores anchor_c ───────────────────


@pytest.mark.parametrize(
    "constraint_type",
    [
        ConstraintType.ANGLE,
        ConstraintType.POINT_ON_EDGE,
        ConstraintType.TANGENT,
    ],
)
def test_remove_constraint_undo_restores_every_anchor(qtbot, constraint_type) -> None:
    """Undo must restore the exact constraint it removed, anchor_c included."""
    anchor_a = AnchorRef(uuid4(), AnchorType.CORNER, 0)
    anchor_b = AnchorRef(uuid4(), AnchorType.CORNER, 1)
    anchor_c = AnchorRef(uuid4(), AnchorType.CORNER, 2)

    graph = ConstraintGraph()
    constraint = graph.add_constraint(
        anchor_a,
        anchor_b,
        90.0,
        constraint_type=constraint_type,
        anchor_c=anchor_c,
    )
    command = RemoveConstraintCommand(graph, constraint)
    command.execute()
    assert graph.constraints == {}

    command.undo()
    restored = next(iter(graph.constraints.values()))
    for anchor in ("anchor_a", "anchor_b", "anchor_c"):
        original = getattr(constraint, anchor)
        after = getattr(restored, anchor)
        assert after is not None, f"{anchor} was dropped by undo()"
        assert (after.item_id, after.anchor_type, after.anchor_index) == (
            original.item_id,
            original.anchor_type,
            original.anchor_index,
        )
    assert restored.constraint_id == constraint.constraint_id
    assert restored.target_distance == constraint.target_distance
    assert restored.constraint_type == constraint.constraint_type


# ── #662: FIXED items must not be drag drivers ─────────────────────────────
#
# The behaviour needs a real viewport drag (Qt's own move handler is what emits
# the phantom positions), so it is pinned in
# tests/integration/test_cad_precision_integrity.py.
