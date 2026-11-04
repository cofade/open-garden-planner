"""The analysis overlays, Cutaway and X-ray in the real QML scene, without a GPU (L2, #386).

Under the offscreen platform nothing 3D is drawn, but ``Garden.qml`` loads and its
objects exist, so the rules that matter for memory and for truth are checked on
every machine: an overlay is loaded into the ONE Model the scene declares for it —
no analysis change creates or destroys an engine object (Qt keeps state for every
Model it once drew, #531) — Cutaway hides exactly the roof parts, also one built
while it is on, and X-ray fades exactly the parts of the items it names, also one
rebuilt while its item fades. (That they are DRAWN where they belong is the render
tier: ``tests/integration/test_view3d_analysis_render.py``.)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QObject

from open_garden_planner.core.scene3d import (
    Material,
    MeshPart,
    Transform,
    engine_buffers,
    prism_mesh,
)
from open_garden_planner.core.scene3d.drape import shadow_drape
from open_garden_planner.core.scene3d.sun_path import compass_mesh
from open_garden_planner.core.scene3d.xray import ROOF_KIND, XRAY_OPACITY
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry, ReloadableGeometry
from tests.ui.test_quick3d_host import (  # noqa: F401 - the canary guards this module too
    SQUARE,
    _new_host,
    quick3d_objects_can_be_created,
)

pytestmark = pytest.mark.no_qt_log   # as tests/ui/test_quick3d_host.py: no Python Qt handler


@pytest.fixture()
def host(qtbot) -> Any:  # noqa: ARG001 - Qt must be initialised
    made = _new_host()
    yield made
    made.close()


def overlay_model(host: Any, layer: str) -> QObject:
    model = host._call("overlayModel", layer)  # noqa: SLF001 - the scene's own answer
    assert isinstance(model, QObject)
    return model


def drape(size: float = 200.0) -> Any:
    return engine_buffers(shadow_drape([[(0.0, 0.0), (size, 0.0), (size, size), (0.0, size)]],
                                       1000.0, 1000.0))


class TestOverlays:
    @pytest.mark.parametrize(("layer", "visible"), [("shade", "shadeVisible"),
                                                     ("drape", "drapeVisible"),
                                                     ("lines", "linesVisible")])
    def test_a_new_host_has_every_overlay_model_and_shows_none(self, host, layer: str,
                                                                  visible: str) -> None:
        model = overlay_model(host, layer)
        assert host.scene_property(visible) is False
        assert model.property("visible") is False and model.property("geometry") is None
        assert model.property("pickable") is False and model.property("castsShadows") is False

    def test_an_overlay_is_reloaded_into_one_geometry_and_creates_no_model(self, host) -> None:
        created, uploads = ReloadableGeometry.created, BufferGeometry.uploads
        host.set_overlay("drape", drape(100.0))
        geometry = overlay_model(host, "drape").property("geometry")
        assert isinstance(geometry, ReloadableGeometry)
        assert ReloadableGeometry.created == created + 1
        for size in (150.0, 300.0, 50.0):
            host.set_overlay("drape", drape(size))
            assert overlay_model(host, "drape").property("geometry") is geometry
        assert ReloadableGeometry.created == created + 1   # still the one
        assert BufferGeometry.uploads == uploads             # no model geometry
        assert host.part_count() == 0                        # no item Model
        assert host.overlay_loads == 4 and host.scene_property("drapeVisible") is True

    def test_hiding_keeps_the_geometry_and_showing_again_reuses_it(self, host) -> None:
        host.set_overlay("lines", engine_buffers(compass_mesh((500.0, 500.0), 600.0)))
        geometry = overlay_model(host, "lines").property("geometry")
        host.set_overlay("lines", None)
        assert host.scene_property("linesVisible") is False
        assert overlay_model(host, "lines").property("geometry") is geometry
        host.set_overlay("lines", engine_buffers(compass_mesh((500.0, 500.0), 900.0)))
        assert host.scene_property("linesVisible") is True
        assert overlay_model(host, "lines").property("geometry") is geometry

    def test_an_unknown_layer_is_refused(self, host) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        with pytest.raises(EngineError, match="overlay"):
            host.set_overlay("sky", drape())

    def test_the_sinks_teardown_leaves_the_overlays_alone(self, host) -> None:
        sink = Quick3DSink(host)
        host.set_overlay("drape", drape())
        sink.clear()
        assert host.scene_property("drapeVisible") is True


def _house_parts() -> tuple[MeshPart, ...]:
    mesh = prism_mesh([SQUARE], 100.0)
    return (MeshPart(mesh, "vc", tinted=True, name="walls"),
            MeshPart(mesh.translated(0.0, 0.0, 100.0), ROOF_KIND, name="roof"))


def _drawn(host: Any) -> dict[tuple[str, str], float]:
    """What share of its pixels each part's active material draws (1: its look)."""
    return {(part.item_id, part.kind): part.drawn for part in host.engine_parts()}


class TestCutaway:
    def test_roofs_are_cut_and_come_back_and_walls_stay(self, host) -> None:
        """A cut roof draws none of its pixels but stays a visible, shadow-casting Model
        (a hidden roof took its shadow off the lawn: 3D review of #386)."""
        sink = Quick3DSink(host)
        sink.begin()
        sink.add("house", _house_parts(), Transform(), Material("HOUSE"))
        sink.commit()
        host.set_roofs_hidden(True)
        assert _drawn(host) == {("house", "vc"): 1.0, ("house", ROOF_KIND): 0.0}
        roof = next(p for p in host.engine_parts() if p.kind == ROOF_KIND)
        assert roof.visible and roof.casts_shadow
        models = {p.kind: p.model for p in host._parts}  # noqa: SLF001
        assert models[ROOF_KIND].property("pickable") is False   # a click goes inside
        host.set_roofs_hidden(False)
        assert _drawn(host) == {("house", "vc"): 1.0, ("house", ROOF_KIND): 1.0}
        assert models[ROOF_KIND].property("pickable") is True

    def test_a_roof_built_while_cutaway_is_on_is_born_cut(self, host) -> None:
        host.set_roofs_hidden(True)
        sink = Quick3DSink(host)
        sink.begin()
        sink.add("house", _house_parts(), Transform(), Material("HOUSE"))
        sink.commit()
        assert _drawn(host)[("house", ROOF_KIND)] == 0.0


class TestXray:
    def _two(self, host: Any) -> Quick3DSink:
        sink = Quick3DSink(host)
        mesh = prism_mesh([SQUARE], 50.0)
        sink.begin()
        for item_id in ("wall", "shed"):
            sink.add(item_id, (MeshPart(mesh, "vc"), MeshPart(mesh, "foliage")), Transform(),
                     Material("SHED"))
        sink.commit()
        return sink

    def test_exactly_the_named_items_fade(self, host) -> None:
        self._two(host)
        host.set_faded_items({"wall"}, XRAY_OPACITY)
        fades = {(p.item_id, p.kind): p.fade for p in host.engine_parts()}
        assert fades == {("wall", "vc"): pytest.approx(XRAY_OPACITY),
                         ("wall", "foliage"): pytest.approx(XRAY_OPACITY),
                         ("shed", "vc"): 1.0, ("shed", "foliage"): 1.0}
        # the faded parts are screen doors of that share (screen.frag / foliage.frag)
        assert _drawn(host) == {("wall", "vc"): pytest.approx(XRAY_OPACITY),
                                ("wall", "foliage"): pytest.approx(XRAY_OPACITY),
                                ("shed", "vc"): 1.0, ("shed", "foliage"): 1.0}
        host.set_faded_items(set(), XRAY_OPACITY)
        assert all(p.fade == 1.0 for p in host.engine_parts())

    def test_a_faded_part_cannot_be_picked_and_comes_back_pickable(self, host) -> None:
        self._two(host)
        host.set_faded_items({"wall"}, XRAY_OPACITY)
        models = {(p.model.property("itemId"), p.kind): p.model for p in host._parts}  # noqa: SLF001
        assert models[("wall", "vc")].property("pickable") is False
        assert models[("shed", "vc")].property("pickable") is True
        host.set_faded_items(frozenset(), XRAY_OPACITY)
        assert models[("wall", "vc")].property("pickable") is True

    def test_a_part_rebuilt_while_its_item_fades_is_born_faded(self, host) -> None:
        sink = self._two(host)
        host.set_faded_items({"wall"}, XRAY_OPACITY)
        sink.begin()
        sink.replace_geometry("wall", (MeshPart(prism_mesh([SQUARE], 80.0), "vc"),))
        sink.commit()
        fades = {(p.item_id, p.kind): p.fade for p in host.engine_parts()}
        assert fades[("wall", "vc")] == pytest.approx(XRAY_OPACITY)

    def test_a_new_opacity_reaches_every_faded_part(self, host) -> None:
        self._two(host)
        host.set_faded_items({"wall"}, 0.5)
        host.set_faded_items({"wall"}, 0.3)
        assert [p.fade for p in host.engine_parts() if p.item_id == "wall"] == [pytest.approx(0.3)] * 2

    def test_an_opacity_outside_zero_to_one_is_refused(self, host) -> None:
        with pytest.raises(ValueError):
            host.set_faded_items({"wall"}, 1.5)
        assert host.faded_items == frozenset()


def test_the_drape_mesh_is_scene_frame_mapped_once(host) -> None:  # noqa: ARG001
    """The engine buffer of a drape lies at engine y = the lift (x = E, y = up, z = -N)."""
    from open_garden_planner.core.scene3d.drape import DRAPE_LIFT_CM

    buffers = drape(100.0)
    vertices = np.frombuffer(buffers.vertex_data, dtype="<f4").reshape(-1, 12)
    assert np.allclose(vertices[:, 1], DRAPE_LIFT_CM)
    assert vertices[:, 2].max() <= 0.0 and vertices[:, 2].min() == pytest.approx(-100.0)
