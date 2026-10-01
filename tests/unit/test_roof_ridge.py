"""Unit tests for the HOUSE -> ROOF_RIDGE sync (issue #364).

The ridge is **derived** geometry: it is created by
:func:`~open_garden_planner.core.roof_ridge.compute_roof_ridge_endpoints` and
must stay a pure function of its owner polygon's geometry. Before this fix,
``PolygonItem._update_ridge_on_boundary`` re-projected the ridge's *existing*
endpoints onto the boundary instead of recomputing them, which made the sync a
membrane: once perturbed, an endpoint had no way back to canonical, the
mutation bypassed the command system, and undo could not restore it.

The two failures this pins, both reproduced before the fix:

* **drift that undo cannot repair** -- ``add_vertex`` moved the second endpoint
  onto a newly introduced slanted edge, and undo restored the polygon exactly
  while leaving the ridge behind. Drift accumulated over repeated cycles.
* **no rotation/scale awareness** -- the membrane kept the ridge's old
  orientation, so a house rotated 30 degrees kept a ridge at 0 degrees (75 cm
  off at 30 degrees, 180 cm at 90 degrees). The roof texture mirrors along the
  ridge (``_paint_with_ridge``), so the roof itself was wrong too.

Both are parametrised over rotation and scale, because the *orientation* defect
is exactly zero at rotation 0 while the *drift* defect reproduces at every
transform — including unrotated, which is how #364 was filed.

This module collects **26** cases (`TestRidgeDriftOnUndo` 20, `TestResizeUndo` 5,
`TestHandMovedRidgeEndpoint` 1). Measured against master's `polygon_item.py` and
`canvas_view.py`: **21 fail, 5 pass**. The 5 that pass are the four
boundary-invariant `test_ridge_stays_on_the_polygon_boundary` cases — satisfied
by the old projection at any transform, by construction — plus
`test_ridge_tracks_the_house_through_rotation[unrotated]`, whose orientation
defect is zero at rotation 0. So **15 of the 20** `TestRidgeDriftOnUndo` cases
fail, and the remaining 6 failures are the whole of `TestResizeUndo` (5) and
`TestHandMovedRidgeEndpoint` (1).

The `TestResizeUndo` cases are worth stating separately: they import the
function this fix introduces, so against master they stop at an `ImportError`
rather than observing anything. Their real proof is that removing the single
sync line from the fixed tree fails all 4 parametrised cases at 300 cm. That
is also why the module-level "21 of 26" is not the whole argument — the sync
line ablation, not the master diff, is what pins `polygon_resize_apply`.
"""

# ruff: noqa: ARG002

import math

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPolygonF
from PyQt6.QtWidgets import QGraphicsScene

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem

#: Tolerated endpoint deviation from canonical, in cm. Well above float noise
#: and the intersection-clamp epsilon, well below a visible 1 cm offset.
RIDGE_EPS_CM = 0.5


def _house_with_ridge(
    width: float = 300.0,
    height: float = 200.0,
    *,
    pos: tuple[float, float] = (1850.0, 300.0),
    rotation: float = 0.0,
    scale: float = 1.0,
    scene: QGraphicsScene | None = None,
) -> tuple[PolygonItem, PolylineItem]:
    """Build a HOUSE and its linked ROOF_RIDGE the way the tool/agent do.

    Mirrors ``PolygonTool._create_roof_ridge`` / ``application.py``: the house
    is positioned, the ridge is created from the *untransformed* polygon, and
    only then is the house rotated/scaled. That order matters -- a HOUSE is
    always created unrotated, and the transform is applied afterwards through
    ``_apply_rotation``, which is what runs the ridge sync. Rotating first and
    creating the ridge from the already-rotated polygon is not a path any
    caller takes, and would test a state the app cannot reach.
    """
    scene = scene if scene is not None else QGraphicsScene()
    house = PolygonItem(
        [
            QPointF(0.0, 0.0),
            QPointF(width, 0.0),
            QPointF(width, height),
            QPointF(0.0, height),
        ],
        object_type=ObjectType.HOUSE,
    )
    house.setPos(*pos)

    p1, p2 = compute_roof_ridge_endpoints(house.polygon(), house.pos())
    ridge = PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE)
    house.set_metadata("ridge_item_id", str(ridge.item_id))
    ridge.set_metadata("owner_polygon_id", str(house.item_id))
    scene.addItem(house)
    scene.addItem(ridge)

    # Apply the transform through the real path, so the sync runs exactly as it
    # does for a rotation handle drag or the Agent API's rotate_object.
    if rotation:
        house._apply_rotation(rotation)
    if scale != 1.0:
        house.setTransformOriginPoint(house.polygon().boundingRect().center())
        house.setScale(scale)
        house._update_ridge_on_boundary()
    return house, ridge


def _canonical_endpoints(house: PolygonItem) -> tuple[QPointF, QPointF]:
    """The ridge a freshly created HOUSE gets, in scene coordinates.

    Computed in the house's LOCAL frame and mapped through the item's full
    transform, which is what makes this correct for a rotated or scaled house.
    """
    local_1, local_2 = compute_roof_ridge_endpoints(house.polygon(), QPointF(0.0, 0.0))
    return house.mapToScene(local_1), house.mapToScene(local_2)


def _live_endpoints(ridge: PolylineItem) -> tuple[QPointF, QPointF]:
    """The ridge's actual endpoints, in scene coordinates."""
    return ridge.mapToScene(ridge.points[0]), ridge.mapToScene(ridge.points[-1])


def _max_deviation(house: PolygonItem, ridge: PolylineItem) -> float:
    """Largest endpoint distance from canonical, in cm."""
    canonical = _canonical_endpoints(house)
    live = _live_endpoints(ridge)
    return max(
        math.dist(
            (live[i].x(), live[i].y()),
            (canonical[i].x(), canonical[i].y()),
        )
        for i in (0, 1)
    )


TRANSFORMS = [
    pytest.param(0.0, 1.0, id="unrotated"),
    pytest.param(30.0, 1.0, id="rot30"),
    pytest.param(90.0, 1.0, id="rot90"),
    pytest.param(45.0, 1.5, id="rot45-scale1.5"),
]


class TestRidgeDriftOnUndo:
    """Issue #364: drift that undo cannot repair, and does not accumulate."""

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_add_vertex_then_undo_leaves_ridge_canonical(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """The exact #364 repro: add a vertex, undo, ridge must be canonical."""
        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)
        assert _max_deviation(house, ridge) == pytest.approx(0.0, abs=RIDGE_EPS_CM)

        house._insert_vertex(2, QPointF(750.0, 600.0))
        house._remove_vertex(2)  # undo of the add

        assert house.polygon().count() == 4
        deviation = _max_deviation(house, ridge)
        assert deviation <= RIDGE_EPS_CM, (
            f"ridge drifted {deviation:.2f} cm from canonical after undo "
            f"(rotation={rotation}, scale={scale})"
        )

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_repeated_cycles_do_not_accumulate_drift(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """Drift was cumulative before the fix; each cycle must land exactly."""
        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)

        for cycle in range(5):
            house._insert_vertex(2, QPointF(750.0 + cycle * 10, 600.0))
            house._remove_vertex(2)
            deviation = _max_deviation(house, ridge)
            assert deviation <= RIDGE_EPS_CM, (
                f"cycle {cycle + 1}: ridge drifted {deviation:.2f} cm "
                f"(rotation={rotation}, scale={scale})"
            )

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_move_vertex_back_to_original_leaves_ridge_canonical(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """A GUI vertex drag and its undo restore the ridge too."""
        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)

        house._move_vertex_to(2, QPointF(400.0, 250.0))
        house._move_vertex_to(2, QPointF(300.0, 200.0))

        deviation = _max_deviation(house, ridge)
        assert deviation <= RIDGE_EPS_CM, (
            f"ridge drifted {deviation:.2f} cm after a vertex drag + undo "
            f"(rotation={rotation}, scale={scale})"
        )

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_ridge_tracks_the_house_through_rotation(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """A rotated house's ridge runs along the rotated long axis.

        Before the fix the membrane kept the old orientation, so the ridge
        stayed at 0 degrees while the house turned -- 180 cm off at 90 degrees,
        and the roof texture mirrors along this line, so the roof was wrong.
        """
        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)

        canonical = _canonical_endpoints(house)
        live = _live_endpoints(ridge)
        canonical_angle = math.degrees(
            math.atan2(
                canonical[1].y() - canonical[0].y(),
                canonical[1].x() - canonical[0].x(),
            )
        )
        live_angle = math.degrees(
            math.atan2(live[1].y() - live[0].y(), live[1].x() - live[0].x())
        )
        # Compare mod 180: a ridge line is undirected.
        delta = abs((live_angle - canonical_angle + 90) % 180 - 90)
        assert delta < 0.5, (
            f"ridge angle {live_angle:.2f} deg does not follow the house "
            f"(canonical {canonical_angle:.2f} deg, rotation={rotation})"
        )

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_ridge_stays_on_the_polygon_boundary(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """Recomputation must not move the ridge off the owner's outline.

        The pre-existing invariant the D2.6 test asserts: after add/delete
        vertex the endpoints lie on the boundary. A recomputed endpoint is on
        the boundary by construction, which is why this still holds.
        """
        from open_garden_planner.ui.canvas.items.polygon_item import (
            _project_to_polygon_boundary,
        )

        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)

        house._insert_vertex(2, QPointF(750.0, 600.0))
        house._remove_vertex(2)

        for point in ridge.points:
            local = house.mapFromScene(ridge.mapToScene(point))
            projected = _project_to_polygon_boundary(house.polygon(), local)
            assert projected == local, (
                f"ridge endpoint {local} is not on the polygon boundary"
            )


class TestResizeUndo:
    """#364 review finding: ``ResizeItemCommand.undo`` re-enters a second path.

    ``_apply_resize`` syncs the ridge, so the live drag was always correct. But
    undo/redo of the registered ``ResizeItemCommand`` replays the closure built
    in ``_on_resize_end``, which is a *different* apply function — and it
    restored the polygon while leaving the ridge sized for the resized house:
    300 cm of drift on a 300->600 cm resize, persisted into the ``.ogp``.

    This is the failure mode ADR-046 warns about: adding a fifth polygon-apply
    path without re-deriving the ridge silently rots the invariant. No test in
    the suite resized a HOUSE, which is why a green 6509-test run missed it.
    """

    @pytest.mark.parametrize(("rotation", "scale"), TRANSFORMS)
    def test_undo_of_a_house_resize_restores_the_ridge(
        self, qtbot: object, rotation: float, scale: float
    ) -> None:
        """Drive the real ``ResizeItemCommand`` through undo/redo.

        The command is given the item's own apply closure, so the path under
        test is the production one — not a re-implementation that would pass
        while the real closure stayed broken.
        """
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.items.polygon_item import (
            polygon_resize_apply,
        )

        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(rotation=rotation, scale=scale, scene=scene)

        def geometry() -> dict[str, object]:
            poly = house.polygon()
            return {
                "vertices": [
                    {"x": poly.at(i).x(), "y": poly.at(i).y()}
                    for i in range(poly.count())
                ],
                "pos_x": house.pos().x(),
                "pos_y": house.pos().y(),
            }

        original = geometry()

        # The live drag — this path already synced.
        house._apply_resize(0.0, 0.0, 600.0, 200.0, house.pos().x(), house.pos().y())
        assert _max_deviation(house, ridge) <= RIDGE_EPS_CM, (
            "precondition: the live resize keeps the ridge canonical"
        )
        resized = geometry()
        assert resized != original, "precondition: the resize actually changed geometry"

        command = ResizeItemCommand(house, original, resized, polygon_resize_apply)

        command.undo()
        deviation = _max_deviation(house, ridge)
        assert deviation <= RIDGE_EPS_CM, (
            f"ridge drifted {deviation:.2f} cm after a HOUSE resize undo "
            f"(rotation={rotation}, scale={scale})"
        )

        # Redo replays execute(); the same apply closure, so it must hold too.
        command.execute()
        assert _max_deviation(house, ridge) <= RIDGE_EPS_CM, "ridge drifted after redo"

        command.undo()
        assert _max_deviation(house, ridge) <= RIDGE_EPS_CM, (
            "ridge drifted after a second undo - drift must not accumulate"
        )

    def test_resize_end_registers_the_canonical_apply_function(
        self, qtbot: object
    ) -> None:
        """The production path must *use* ``polygon_resize_apply``, not a copy.

        The test above builds its own ``ResizeItemCommand``, so on its own it
        proves the module-level function syncs and that undo replays
        ``apply_func`` -- but not that ``_on_resize_end`` passes that function.
        Reinstating a local closure there without the sync is the exact shape
        that caused the 300 cm hole, and every other test would still pass.
        """
        from open_garden_planner.core.commands import ResizeItemCommand
        from open_garden_planner.ui.canvas.items.polygon_item import (
            polygon_resize_apply,
        )

        scene = QGraphicsScene()
        house, _ridge = _house_with_ridge(scene=scene)

        registered: list[object] = []

        class _Manager:
            def execute(self, command: object) -> None:
                registered.append(command)

            def register_applied(self, command: object) -> None:
                registered.append(command)

        scene.get_command_manager = lambda: _Manager()  # type: ignore[attr-defined]

        initial_polygon = QPolygonF(house.polygon())
        initial_pos = QPointF(house.pos())
        house._resize_initial_polygon = initial_polygon

        # A real geometry change, then the release that registers the command.
        house._apply_resize(0.0, 0.0, 600.0, 200.0, initial_pos.x(), initial_pos.y())
        house._on_resize_end(initial_polygon.boundingRect(), initial_pos)

        assert registered, "precondition: the resize registered a command"
        command = registered[0]
        assert isinstance(command, ResizeItemCommand)
        assert command._apply_func is polygon_resize_apply, (
            "_on_resize_end must hand ResizeItemCommand the canonical apply "
            "function; a local closure here silently reintroduces the "
            "resize-undo ridge hole"
        )


class TestHandMovedRidgeEndpoint:
    """#364's open decision: a hand-dragged ridge endpoint is not sticky.

    ``PolylineItem._move_vertex_to`` still constrains a hand-dragged endpoint
    onto the owner's outline, so the drag itself is honoured. The next polygon
    edit then recomputes, which discards the manual placement -- recorded here
    so the behaviour is pinned rather than accidental.
    """

    def test_hand_drag_is_honoured_until_the_next_polygon_edit(
        self, qtbot: object
    ) -> None:
        scene = QGraphicsScene()
        house, ridge = _house_with_ridge(scene=scene)

        # A hand drag onto a different part of the outline.
        ridge._move_vertex_to(1, QPointF(300.0, 120.0))
        assert _max_deviation(house, ridge) > RIDGE_EPS_CM, (
            "precondition: the hand drag actually moved the ridge"
        )

        # The next polygon edit recomputes, so the manual placement is dropped.
        house._insert_vertex(2, QPointF(750.0, 600.0))
        house._remove_vertex(2)

        deviation = _max_deviation(house, ridge)
        assert deviation <= RIDGE_EPS_CM, (
            f"ridge should be canonical after a polygon edit, was {deviation:.2f} cm off"
        )
