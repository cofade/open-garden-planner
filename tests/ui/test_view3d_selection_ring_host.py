"""The selection ring in the real QML scene, without a GPU (Phase 17 L1.8, ADR-060).

Under the offscreen platform nothing 3D is drawn, but ``Garden.qml`` loads and its
objects exist — so the ONE thing the ring must never do can be checked on every
machine: create or destroy an engine object per selection change. The ring's Model
is declared in the scene; its one geometry is made with the first selection and
re-loaded for every later one. (That it is DRAWN in the right place is the render
tier: ``tests/integration/test_view3d_selection_render.py``.)
"""

from __future__ import annotations

from typing import Any

import pytest
from PyQt6.QtCore import QObject

from open_garden_planner.core.scene3d import (
    GroundSpec,
    SceneSync,
    SunState,
    Transform,
    engine_buffers,
    srgb8_to_linear,
)
from open_garden_planner.core.scene3d.selection import (
    EMPTY_SELECTION,
    SELECTION_RGBA,
    selection_of,
)
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry, ReloadableGeometry
from tests.ui.test_quick3d_host import (  # noqa: F401 - the canary guards this module too
    _broken_copy,
    _new_host,
    _record,
    quick3d_objects_can_be_created,
)

pytestmark = pytest.mark.no_qt_log   # as tests/ui/test_quick3d_host.py: no Python Qt handler


@pytest.fixture()
def host(qtbot) -> Any:  # noqa: ARG001 - Qt must be initialised
    made = _new_host()
    yield made
    made.close()


def ring_model(host: Any) -> QObject:
    model = host._call("selectionRingModel")  # noqa: SLF001 - the scene's own answer
    assert isinstance(model, QObject)
    return model


def ring_of(*ids: str, records: dict[str, Any] | None = None) -> Any:
    scene = records if records is not None else {"a": _record("a"), "b": _record("b", 200.0)}
    return engine_buffers(selection_of(scene, ids).ring)


def test_a_new_host_has_the_ring_model_and_shows_no_ring(host) -> None:
    model = ring_model(host)
    assert host.scene_property("selectionVisible") is False
    assert model.property("visible") is False and model.property("geometry") is None
    assert model.property("pickable") is False and model.property("castsShadows") is False
    assert model.property("receivesShadows") is False
    assert host.ring_loads == 0 and host._ring is None  # noqa: SLF001
    assert host.engine_parts() == [] and host.part_count() == 0, "the ring is no part"


def test_the_first_selection_makes_the_one_geometry_and_later_ones_reload_it(host) -> None:
    made, loads = ReloadableGeometry.created, ReloadableGeometry.loads
    uploads = BufferGeometry.uploads
    host.set_selection_ring(ring_of("a"))
    geometry = host._ring  # noqa: SLF001
    model = ring_model(host)
    assert isinstance(geometry, ReloadableGeometry) and model.property("geometry") is geometry
    assert geometry.parent() is model, "the Model owns it: they go together"
    assert host.scene_property("selectionVisible") is True and model.property("visible") is True
    assert geometry.vertex_count == 12 and host.ring_loads == 1
    for count, ids in enumerate((("a", "b"), ("b",), ("a",), ("a", "b")), start=2):
        host.set_selection_ring(ring_of(*ids))
        assert host._ring is geometry and model.property("geometry") is geometry  # noqa: SLF001
        assert geometry.vertex_count == 12 * len(ids) and host.ring_loads == count
    assert ReloadableGeometry.created == made + 1, "five selections, ONE object ever made"
    assert ReloadableGeometry.loads == loads + 5
    assert BufferGeometry.uploads == uploads and host.part_count() == 0


def test_hiding_keeps_the_geometry_for_the_next_selection(host) -> None:
    host.set_selection_ring(ring_of("a"))
    geometry = host._ring  # noqa: SLF001
    made = ReloadableGeometry.created
    for nothing in (None, engine_buffers(EMPTY_SELECTION.ring)):
        host.set_selection_ring(nothing)
        assert host.scene_property("selectionVisible") is False
        assert ring_model(host).property("visible") is False
        assert host._ring is geometry and host.ring_loads == 1  # noqa: SLF001
    host.set_selection_ring(ring_of("b"))
    assert host._ring is geometry and ReloadableGeometry.created == made  # noqa: SLF001
    assert host.scene_property("selectionVisible") is True


def test_the_rings_colour_is_set_exactly_with_the_first_ring(host) -> None:
    host.set_selection_ring(ring_of("a"))
    colour = host.scene_property("selectionColorLinear")
    assert (colour.x(), colour.y(), colour.z()) == pytest.approx(
        srgb8_to_linear(SELECTION_RGBA)[:3], abs=1e-6)


def test_clear_hides_the_ring_and_destroys_nothing_of_it(host) -> None:
    sink = Quick3DSink(host)
    sync = SceneSync(sink)
    records = {"a": _record("a"), "b": _record("b", 200.0)}
    sync.apply(records, sun=SunState(40.0, 180.0), ground=GroundSpec(500.0, 500.0))
    sync.set_selection(["a"])
    geometry = host._ring  # noqa: SLF001
    assert host.scene_property("selectionVisible") is True
    sync.reset()
    assert host.scene_property("selectionVisible") is False and host.engine_parts() == []
    assert host._ring is geometry and ring_model(host).property("geometry") is geometry  # noqa: SLF001
    sync.apply(records)
    assert host.scene_property("selectionVisible") is True, "the wish came back with the items"
    assert sink.state() == sync.expected_state()


def test_a_selection_session_through_the_real_sink_touches_no_model(host) -> None:
    """Gate G3 at the engine: the Models read back FROM THE QML SCENE are the same
    objects, in the same poses, around every selection change; a selected item that
    moves re-poses its Model and reloads the ring — and uploads no Model buffer."""
    sink = Quick3DSink(host)
    sync = SceneSync(sink)
    records = {"a": _record("a"), "b": _record("b", 200.0), "c": _record("c", -200.0)}
    sync.apply(records, sun=SunState(40.0, 180.0), ground=GroundSpec(900.0, 900.0))
    parts = host.engine_parts()
    handles = set(host._parts)  # noqa: SLF001 - identity of the engine's Models
    uploads, made = BufferGeometry.uploads, ReloadableGeometry.created
    for step, ids in enumerate((["a"], ["a", "c"], ["c"], [], ["b"], ["a", "b", "c"], [])):
        assert sync.set_selection(ids) is True, step
        assert host.engine_parts() == parts and set(host._parts) == handles  # noqa: SLF001
        assert host.scene_property("selectionVisible") is bool(ids)
        assert sink.state() == sync.expected_state()
    assert BufferGeometry.uploads == uploads and sink.geometry_uploads == 6  # two per item
    assert ReloadableGeometry.created == made + 1 and sink.ring_uploads == 5 == host.ring_loads

    sync.set_selection(["a"])
    loads = host.ring_loads
    moved = {**records, "a": _record("a", 60.0)}
    sync.apply(moved)
    assert host.ring_loads == loads + 1, "the ring went with the move"
    assert BufferGeometry.uploads == uploads and set(host._parts) == handles  # noqa: SLF001
    assert [p.position for p in host.engine_parts()
            if p.item_id == "a"] == [(60.0, 0.0, 0.0), (60.0, 0.0, 0.0)]  # sides + cap
    sync.apply({**moved, "b": _record("b", 250.0)})
    assert host.ring_loads == loads + 1, "an edit of something else does not reload the ring"


def test_the_ring_is_at_the_standing_base_in_the_engine_frame(host) -> None:
    """A plant on a bed: the ring's vertices are lifted to the bed's soil (the record's
    base) — in the ENGINE frame that is y, not z."""
    import dataclasses

    import numpy as np

    from open_garden_planner.core.scene3d import VERTEX_STRIDE
    from open_garden_planner.core.scene3d.selection import RING_LIFT_CM

    plant = dataclasses.replace(_record("p"), transform=Transform(120.0, 340.0, 0.0, 38.0))
    buffers = ring_of("p", records={"p": plant})
    rows = np.frombuffer(buffers.vertex_data, "<f4").reshape(-1, VERTEX_STRIDE // 4)
    assert np.allclose(rows[:, 1], 38.0 + RING_LIFT_CM)
    assert buffers.bounds_min[1] == buffers.bounds_max[1] == pytest.approx(38.0 + RING_LIFT_CM)
    host.set_selection_ring(buffers)
    assert host._ring.vertex_count == buffers.vertex_count  # noqa: SLF001


def test_a_scene_file_without_the_rings_functions_is_an_engine_error(qtbot, tmp_path) -> None:  # noqa: ARG001
    from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

    broken = Quick3DHost((64, 48), qml_dir=_broken_copy(
        tmp_path, "    function setSelectionGeometry(geometry) {",
        "    function setSelectionGeometryRenamed(geometry) {"))
    try:
        with pytest.raises(EngineError, match=r"no function setSelectionGeometry\(\)"):
            broken.set_selection_ring(ring_of("a"))
        assert broken._ring is None, "no half-made ring is kept"  # noqa: SLF001
        assert broken.scene_property("selectionVisible") is False
        broken.set_selection_ring(None)   # hiding still works
    finally:
        broken.close()
