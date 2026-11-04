"""The endless meadow in the real QML scene, without a GPU (#388, 3D review round 2).

Under the offscreen platform nothing 3D is drawn, but ``Garden.qml`` loads and its
objects exist. The meadow is ONE Model declared in the scene with ONE geometry of the
host's (``core/scene3d/meadow.py``): loaded when the host starts, and again only when
the plan's rectangle changes — an edit, a re-bake or a new look loads nothing, and no
engine object is created or destroyed for it. (That it is DRAWN around the plan and
never on it is the render tier: ``test_scene3d_ground_render.py``.)
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QObject

from open_garden_planner.core.scene3d.meadow import MEADOW_CELL_CM, MEADOW_HALF_CM
from open_garden_planner.ui.view3d.quick3d.adapter import GroundPlacement
from open_garden_planner.ui.view3d.quick3d.geometry import (
    BufferGeometry,
    MeadowGeometry,
    ReloadableGeometry,
)
from tests.ui.test_quick3d_host import (  # noqa: F401 - the canary guards this module too
    _new_host,
    quick3d_objects_can_be_created,
)

pytestmark = pytest.mark.no_qt_log   # as tests/ui/test_quick3d_host.py: no Python Qt handler

#: The square's grid lines each way, without a plan (41) and with one (and its 2 edges).
LINES = round(2.0 * MEADOW_HALF_CM / MEADOW_CELL_CM) + 1


@pytest.fixture()
def host(qtbot) -> Any:  # noqa: ARG001 - Qt must be initialised
    made = _new_host()
    yield made
    made.close()


def meadow_model(host: Any) -> QObject:
    model = host._call("meadowModel")  # noqa: SLF001 - the scene's own answer
    assert isinstance(model, QObject)
    return model


def plan(width: float, depth: float) -> GroundPlacement:
    """The plan rectangle from scene (0, 0) — its centre in the ENGINE frame (x, up, -N)."""
    return GroundPlacement(center=(width / 2.0, 0.0, -depth / 2.0), width_cm=width, depth_cm=depth)


def test_a_new_host_lays_the_whole_meadow(host) -> None:
    model = meadow_model(host)
    geometry = host._meadow  # noqa: SLF001
    assert isinstance(geometry, MeadowGeometry) and model.property("geometry") is geometry
    assert geometry.parent() is model, "the Model owns it: they go together"
    assert model.property("visible") is True and model.property("pickable") is False
    assert model.property("receivesShadows") is True and model.property("castsShadows") is False
    assert geometry.vertex_count == LINES * LINES, "no plan: no hole"
    assert host.meadow_loads == 1
    assert host.engine_parts() == [] and host.part_count() == 0, "the meadow is no part"


def test_it_is_loaded_again_only_when_the_plan_rectangle_changes(host) -> None:
    made, uploads = ReloadableGeometry.created, BufferGeometry.uploads
    meadows, ring_loads = MeadowGeometry.created, ReloadableGeometry.loads
    geometry = host._meadow  # noqa: SLF001
    host.set_ground(plan(2600.0, 1800.0))
    assert host.meadow_loads == 2 and geometry.vertex_count == (LINES + 2) ** 2
    for _again in range(3):
        host.set_ground(plan(2600.0, 1800.0))   # a re-bake: the same rectangle
    assert host.meadow_loads == 2
    host.set_ground(plan(5000.0, 3000.0))
    host.set_ground(None)                        # no plan: the hole closes
    assert host.meadow_loads == 4 and geometry.vertex_count == LINES * LINES
    assert host._meadow is geometry and meadow_model(host).property("geometry") is geometry  # noqa: SLF001
    assert MeadowGeometry.created == meadows, "one object for the host's life"
    assert ReloadableGeometry.created == made and ReloadableGeometry.loads == ring_loads, \
        "the ring's instruments count the ring (and the overlays), never the meadow"
    assert BufferGeometry.uploads == uploads and host.part_count() == 0


def test_clear_keeps_the_meadow_and_closes_its_hole(host) -> None:
    host.set_ground(plan(2400.0, 1600.0))
    host.clear()
    model = meadow_model(host)
    assert model.property("visible") is True and host._meadow.vertex_count == LINES * LINES  # noqa: SLF001


def test_shadow_reach_covers_every_plan_corner_and_updates_when_the_plan_changes(host) -> None:
    import math

    from open_garden_planner.core.scene3d.look import fog_depth_cm

    eye = (-6000.0, -6000.0, 3000.0)
    host.set_camera(eye, (0.0, 0.0, 0.0))
    host.set_ground(plan(5000.0, 3000.0))
    near, far = fog_depth_cm(math.dist(eye, (0.0, 0.0, 0.0)))
    reach = max(math.dist(eye, (x, y, 0.0)) for x in (0.0, 5000.0) for y in (0.0, 3000.0)) + 1000.0
    assert host._root.property("shadowFar") == pytest.approx(max(9000.0, near, min(reach, far)))  # noqa: SLF001
    host.set_ground(plan(1000.0, 500.0))
    assert host._root.property("shadowFar") < reach  # noqa: SLF001
