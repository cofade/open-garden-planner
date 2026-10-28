"""``Quick3DHost`` without a GPU: the real QML scene, no pixels (Phase 17 L1.2, #385).

Under ``QT_QPA_PLATFORM=offscreen`` Qt Quick falls back to the software scene
graph, which draws no 3D — but ``Garden.qml`` still LOADS, Models are still
created, posed, tinted and destroyed, and their properties can be read back. So
this default-tier file checks everything about the engine boundary that is not a
pixel, on every machine and in the required CI job:

- the scene file and its part components load without a QML error;
- every sink call arrives as the right change of the right Model (read back from
  the QML scene, not from the sink's books);
- the sun, the ground, the camera and the look are mapped into the scene's
  properties in the engine frame;
- the host's state machine: which call is legal in which state, what a closed or
  destroyed host answers, the sink's teardown in every order — also when the engine
  REFUSES to destroy a Model;
- ``health()``: what Qt reports about a host on the GUI thread;
- that a backend which cannot render 3D says so instead of handing out a frame.

What it cannot check — that any of it is DRAWN correctly, and that a wrong call
order no longer kills the process — is the render tier
(``tests/integration/test_quick3d_render.py``, ``test_quick3d_lifecycle.py``).

THE CANARY (review P1-2). A child process first creates a bare ``QQuickView``
with inline ``import QtQuick3D`` QML — ZERO product code. If that fails, this
platform cannot create Qt Quick 3D objects at all and the module skips (on CI it
FAILS: the runners are known to manage it, and a silent skip of this file is how
a broken engine package would ship green). Everything else — a QML error in
``Garden.qml``, a Python exception in the host — happens in the tests below and
FAILS them. The canary used to run the product: a broken ``Garden.qml`` gave 32
skips and 0 failures. ``test_a_broken_scene_file_fails_the_tier_instead_of_skipping_it``
is the positive control for that.
"""

from __future__ import annotations

import ast
import json
import logging
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, ClassVar

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject
from PyQt6.QtGui import QColor, QQuaternion, QVector3D

from open_garden_planner.core.scene3d import (
    GroundSpec,
    Material,
    Mesh,
    MeshPart,
    Params,
    Record,
    RecordingSink,
    SceneSync,
    SunState,
    Transform,
    engine_buffers,
    prism_mesh,
)
from open_garden_planner.core.scene3d.look import PRESETS, look_for, moon_travel_scene
from open_garden_planner.ui.view3d.quick3d.adapter import PartSpec, Quick3DSink
from open_garden_planner.ui.view3d.quick3d.look import (
    COLOR_PROPERTIES,
    LINEAR_COLOR_PROPERTIES,
    NEUTRAL_DAY,
    engine_linear,
    scene_properties,
    sky_properties,
)
from open_garden_planner.ui.view3d.quick3d.shots import PerspectiveShot, TopDownShot
from tests.integration import quick3d_lifecycle_child as lifecycle
from tests.integration.quick3d_render_support import isolated_env

# Qt's QML engine writes a compiled copy of every scene file it loads into the per-user
# cache (<cache>/qmlcache/*.qmlc) - from C++, so nothing in Python redirects it - and this
# file loads a fresh copy of Garden.qml for every control: hundreds of files in the
# developer's profile after a few runs. No QML disk cache for this test process. Set at
# import, during collection, before any QML engine exists (Qt reads the variable once).
os.environ.setdefault("QML_DISABLE_DISK_CACHE", "1")

# pytest-qt installs a Python Qt message handler for every test (its log capture). That is
# the arrangement the engine package forbids beside a shown window: on a real platform Qt
# renders on a thread of its own, and the two deadlock (qt_messages.py). What is MEASURED
# about the offscreen platform is an absence, not a fact: Qt logs "Loading backend software"
# there and names no render loop (on Direct3D 11 and on xcb it says "threaded render loop"),
# and this file ran several hundred times with the capture on and never hung. An absence is
# nothing to build on, so nothing here depends on it: no capture for this module, and no test
# in it installs a Python handler while a host is shown
# (test_no_test_here_installs_a_python_handler_beside_a_shown_host pins that).
pytestmark = pytest.mark.no_qt_log

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"
SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
RED = (230, 20, 20, 255)
BLUE = (20, 40, 230, 255)
#: Set by the positive control only: the QML directory the hosts of this file load.
QML_OVERRIDE = "OGP_TEST_QUICK3D_QML_DIR"
#: The three releases: legal on a closed host, where they do nothing.
RELEASES = ("destroy_part", "release_fill", "clear", "close")

# No product code in here — that is the point (module docstring). It does to bare Qt
# what the tests below do to the host: load a View3D scene from a file, create a Model
# with a geometry from Python, show and hide a window, embed one in a widget.
_CANARY = r'''
import sys, tempfile
from pathlib import Path
from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QByteArray, QMetaObject, QObject, Qt, QUrl
from PyQt6.QtWidgets import QApplication, QWidget
app = QApplication(sys.argv[:1])
from PyQt6.QtQuick import QQuickView
from PyQt6.QtQuick3D import QQuick3DGeometry

QML = """
import QtQuick
import QtQuick3D
import QtQuick3D.Helpers
Item {
    width: 64; height: 48
    function make(geometry) { return part.createObject(parts, {"geometry": geometry}) }
    Component { id: part; Model { materials: PrincipledMaterial { } } }
    View3D {
        anchors.fill: parent
        environment: ExtendedSceneEnvironment { }
        PerspectiveCamera { z: 300 }
        DirectionalLight { }
        Node { id: parts }
    }
}
"""

class Geometry(QQuick3DGeometry):
    def __init__(self):
        super().__init__()
        self.setStride(12)
        self.setVertexData(QByteArray(bytes(36)))
        self.update()

def view_of(directory):
    view = QQuickView()
    view.setSource(QUrl.fromLocalFile(str(Path(directory) / "Canary.qml")))
    assert view.rootObject() is not None, [error.toString() for error in view.errors()]
    return view

with tempfile.TemporaryDirectory() as directory:
    (Path(directory) / "Canary.qml").write_text(QML, encoding="utf-8")
    view = view_of(directory)
    geometry = Geometry()
    model = QMetaObject.invokeMethod(view.rootObject(), "make", Qt.ConnectionType.DirectConnection,
                                     Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", geometry))
    assert isinstance(model, QObject), model
    view.show(); app.processEvents(); view.hide(); app.processEvents()
    parent = QWidget()
    embedded = view_of(directory)
    container = QWidget.createWindowContainer(embedded, parent)
    parent.show(); app.processEvents(); parent.hide(); app.processEvents()
    parent.deleteLater(); view.deleteLater(); app.processEvents()
print("canary ok", flush=True)
'''


# What ``Quick3DHost._run_events`` and ``wait_ready()`` do once the application is quitting.
# ``QCoreApplication.quit()`` does nothing unless the main event loop runs, hence a child.
_QUITTING = r'''
import json, sys, time
from PyQt6.QtCore import QCoreApplication, QTimer
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv[:1])
from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost
from open_garden_planner.ui.view3d.quick3d.lifecycle import WindowFacts

out = {}

def inside():
    host = Quick3DHost((64, 48))
    host.show()
    out["ready"] = host.wait_ready(10.0)
    started = time.perf_counter()
    out["a_pass_while_running"] = Quick3DHost._run_events(5)
    out["a_pass_while_running_s"] = time.perf_counter() - started
    starting = WindowFacts(True, True, False, 64, 48, False, False, 64.0, 48.0)
    looks = [0]
    def facts():
        looks[0] += 1
        return starting
    QCoreApplication.quit()
    started = time.perf_counter()
    out["passes_while_quitting"] = [Quick3DHost._run_events(5) for _ in range(3)]
    out["three_passes_s"] = time.perf_counter() - started
    host._facts = facts
    started = time.perf_counter()
    out["wait_ready"] = host.wait_ready(5.0)
    out["wait_ready_s"] = time.perf_counter() - started
    out["looks"] = looks[0]
    del host._facts
    host.close()

QTimer.singleShot(0, inside)
out["exec"] = app.exec()
print("RESULT " + json.dumps(out), flush=True)
'''


def _child_env(scratch: Path) -> dict[str, str]:
    """A child that cannot reach the developer's data (``isolated_env``), offscreen."""
    return isolated_env(scratch, QT_QPA_PLATFORM="offscreen")


@pytest.fixture(scope="module", autouse=True)
def quick3d_objects_can_be_created(tmp_path_factory: pytest.TempPathFactory) -> None:
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-c", _CANARY], env=_child_env(tmp_path_factory.mktemp("canary")),
        capture_output=True, text=True, timeout=170)
    if proc.returncode == 0 and "canary ok" in proc.stdout:
        return
    message = ("bare Qt cannot create Qt Quick 3D objects under the offscreen platform here "
               f"(no product code involved; exit {proc.returncode}): {proc.stderr[-800:]}")
    if os.environ.get("CI"):
        pytest.fail(message + "\nOn CI this is a failure, not a skip: the runners can, and a "
                    "skipped host tier would let a broken engine package through.")
    pytest.skip(message)


def test_the_canary_contains_no_product_code() -> None:
    """Review P1-2: the canary decides whether this file runs at all. If it imported the
    product, a bug in the product would turn every test here into a skip."""
    assert "open_garden_planner" not in _CANARY and "Garden.qml" not in _CANARY
    assert "import QtQuick3D" in _CANARY and "QQuickView()" in _CANARY


def _qml_dir() -> Path | None:
    override = os.environ.get(QML_OVERRIDE)
    return Path(override) if override else None


def _new_host(size: tuple[int, int] = (64, 48)) -> Any:
    from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

    return Quick3DHost(size, qml_dir=_qml_dir())


def _record(item_id: str, east: float = 0.0, north: float = 0.0, rotation: float = 0.0,
            colour: tuple[int, int, int, int] = RED, height: float | None = 100.0) -> Record:
    return Record(item_id=item_id, kind="SHED", shape="rectangle", footprints=(SQUARE,),
                  transform=Transform(east_cm=east, north_cm=north, rotation_deg=rotation),
                  material=Material("SHED", fill_rgba=colour), height_cm=height,
                  params=Params({"seed": item_id}))


@pytest.fixture()
def host(qtbot) -> Iterator[Any]:  # noqa: ARG001 - Qt must be initialised
    made = _new_host((320, 240))
    yield made
    made.close()


def _uploads() -> int:
    from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry

    return int(BufferGeometry.uploads)


def _assert_look_shown(host: Any, look: Any) -> None:
    """Every look property of the scene file holds what ``scene_properties`` maps."""
    for name, value in scene_properties(look).items():
        shown = host.scene_property(name)
        if name in COLOR_PROPERTIES:
            assert shown == QColor(str(value)), name
        elif name in LINEAR_COLOR_PROPERTIES:
            # handed over as floats: a QColor keeps 16 bits a channel, so that a night
            # colour of a few thousandths survives (8 bits are steps of a fifth there)
            assert (shown.redF(), shown.greenF(), shown.blueF()) == pytest.approx(value, abs=2e-5), name
        elif isinstance(value, float):
            assert shown == pytest.approx(value, rel=1e-12), name
        else:
            assert shown == value, name


def test_a_night_fog_reaches_the_scene_as_the_linear_value_the_look_derived(qtbot) -> None:  # noqa: ARG001
    """L1.4 round 1: the scene's fog colour, put through the ENGINE's own linearisation,
    is the look's linear fog — to four significant digits, also at a few thousandths.
    (As ``#rrggbb`` through the sRGB curve it arrived three times too dark.)"""
    made = _new_host((320, 240))
    try:
        night = look_for(SunState(-11.07, 337.12), "high")
        made.set_look(night)
        shown = made.scene_property("fogColor")
        reached = tuple(engine_linear(channel) for channel in (shown.redF(), shown.greenF(), shown.blueF()))
        assert reached == pytest.approx(night.fog_linear, rel=2e-2)
        assert max(night.fog_linear) < 0.005, "a night fog IS a few thousandths in linear light"
    finally:
        made.close()


def _scene_environment(host: Any) -> QObject:
    """``Garden.qml``'s ``ExtendedSceneEnvironment``. Its AO state is read there: Qt sets
    ``aoEnabled`` itself, so no root property mirrors it."""
    (environment,) = [child for child in host._root.findChildren(QObject)  # noqa: SLF001
                      if "SceneEnvironment" in child.metaObject().className()]
    return environment


def _light_travel(host: Any) -> tuple[float, float, float]:
    """Where the scene's key light shines: its rotation applied to a light's own -Z."""
    rotation: QQuaternion = host.scene_property("sunRotation")
    shines = rotation.rotatedVector(QVector3D(0.0, 0.0, -1.0))
    return (shines.x(), shines.y(), shines.z())


def _broken_copy(tmp_path: Path, old: str, new: str) -> Path:
    from open_garden_planner.ui.view3d.quick3d.host import QML_DIR

    broken = tmp_path / "qml"
    shutil.copytree(QML_DIR, broken)
    scene = broken / "Garden.qml"
    text = scene.read_text(encoding="utf-8")
    assert old in text, f"the control no longer finds {old!r} in Garden.qml"
    scene.write_text(text.replace(old, new), encoding="utf-8")
    return broken


class TestSceneFile:
    def test_garden_qml_loads_with_the_neutral_day_look(self, host) -> None:
        assert host.qml_load_ms > 0.0
        assert host.view_size() == (320.0, 240.0)
        _assert_look_shown(host, NEUTRAL_DAY)
        assert host.look is NEUTRAL_DAY
        assert host.scene_property("windTime") == 0.0, "the wind is at rest until a policy animates it"
        assert host.scene_property("windRunning") is False
        assert host.scene_property("sunUp") is False and host.scene_property("groundVisible") is False
        assert host.sky is None and host.sky_builds == 0, "no sky before somebody asks for one"
        assert host.scene_property("skyBuilt") is False and host.scene_property("skyBuilds") == 0
        assert host.engine_parts() == []

    @pytest.mark.parametrize("preset", PRESETS)
    @pytest.mark.parametrize(("elevation", "azimuth"), [(-20.0, 10.0), (0.5, 300.0), (5.89, 301.5),
                                                        (15.23, 280.0), (60.9, 170.0)])
    def test_a_look_is_applied_as_plain_data(self, host, preset: str, elevation: float,
                                             azimuth: float) -> None:
        """Every mood at every preset: each look property of the scene holds what the
        mapping says — and afterwards the neutral day again, so nothing sticks."""
        look = look_for(SunState(elevation, azimuth), preset)
        host.set_look(look)
        _assert_look_shown(host, look)
        assert host.look is look
        host.set_look(NEUTRAL_DAY)
        _assert_look_shown(host, NEUTRAL_DAY)

    def test_a_look_builds_no_sky_and_touches_no_model_and_no_camera(self, host) -> None:
        """G6's engine half: a change of look (a preset step) writes look properties and
        nothing else — no geometry, no camera, no sky."""
        sync = SceneSync(Quick3DSink(host))
        sync.apply({"a": _record("a")}, sun=SunState(40.0, 200.0), ground=GroundSpec(800.0, 600.0))
        host.set_camera((0.0, -900.0, 500.0), (0.0, 0.0, 50.0))
        before = (_uploads(), host.part_count(), host.engine_parts(),
                  host.scene_property("camVersion"), host.scene_property("sunRotation"))
        for preset in PRESETS:
            host.set_look(look_for(SunState(40.0, 200.0), preset))
        assert (_uploads(), host.part_count(), host.engine_parts(),
                host.scene_property("camVersion"), host.scene_property("sunRotation")) == before
        assert host.sky_builds == 0 and host.scene_property("skyBuilds") == 0

    def test_a_scene_file_that_does_not_load_is_a_loud_error(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        """The Model/Light property-name trap as a load error, with file and line."""
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        broken = _broken_copy(tmp_path, "            castsShadow: true\n",
                              "            castsShadows: true\n")
        with pytest.raises(EngineError, match=r"Garden\.qml did not load.*castsShadows"):
            Quick3DHost((64, 48), qml_dir=broken)


class TestPropertiesAreChecked:
    """Review P2-2: every ``setProperty`` result used to be ignored. On a QML object a
    name the scene does not declare silently becomes a DYNAMIC property — the value
    goes nowhere, and nothing says so."""

    def test_a_renamed_scene_property_fails_the_host_instead_of_being_set_into_the_void(
            self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        renamed = _broken_copy(tmp_path, "property real sunBrightness: 1.9",
                               "property real sunStrength: 1.9")
        with pytest.raises(EngineError, match="no property 'sunBrightness'"):
            Quick3DHost((64, 48), qml_dir=renamed)

    @pytest.mark.parametrize(("declaration", "name", "call"), [
        ("property bool sunUp: false", "sunUp", lambda h: h.set_sun((0.0, -1.0, 0.0))),
        ("property real groundWidth: 1000", "groundWidth",
         lambda h: SceneSync(Quick3DSink(h)).set_ground(GroundSpec(10.0, 10.0))),
        ("property bool topDown: false", "topDown",
         lambda h: h.set_shot(TopDownShot((0.0, 0.0), 0.5))),
        ("property real camFov: 40", "camFov",
         lambda h: h.set_camera((0.0, -5.0, 5.0), (0.0, 0.0, 0.0))),
    ], ids=["sun", "ground", "top-down", "camera"])
    def test_every_writer_names_the_property_it_could_not_set(
            self, qtbot, tmp_path: Path, declaration: str, name: str, call: Any) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        renamed = _broken_copy(tmp_path, declaration, declaration.replace(name, name + "Renamed"))
        made = Quick3DHost((64, 48), qml_dir=renamed)
        try:
            with pytest.raises(EngineError, match=f"no property '{name}'"):
                call(made)
        finally:
            made.close()

    def test_a_model_without_a_tint_property_is_an_error_and_leaves_no_orphan(
            self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        from open_garden_planner.core.scene3d import engine_pose
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        renamed = _broken_copy(tmp_path, "property vector3d tintLinear: Qt.vector3d(1, 1, 1)",
                               "property vector3d tintLinearRenamed: Qt.vector3d(1, 1, 1)")
        made = Quick3DHost((64, 48), qml_dir=renamed)
        try:
            buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
            with pytest.raises(EngineError, match="no property 'tintLinear'"):
                made.create_part(PartSpec("a", 0, "vc", buffers, True), engine_pose(Transform()), RED)
            assert made.engine_parts() == [], "the half-made Model must not stay in the scene"
        finally:
            made.close()

    def test_a_value_the_property_cannot_take_is_refused(self, host) -> None:
        from open_garden_planner.ui.view3d.quick3d import host as host_module

        with pytest.raises(host_module.EngineError, match="refused .* for its property 'groundWidth'"):
            host_module._set(host._root, "groundWidth", QColor("red"))  # noqa: SLF001
        with pytest.raises(host_module.EngineError, match="no property 'noSuchProperty'"):
            host.scene_property("noSuchProperty")


class TestSinkCallsReachTheQmlScene:
    def test_add_creates_one_model_per_part_with_pose_tint_and_geometry(self, host) -> None:
        sync = SceneSync(Quick3DSink(host), validate=True)
        before = _uploads()
        sync.apply({"a": _record("a", 300.0, 120.0, 17.0), "flat": _record("flat", height=None)})
        parts = host.engine_parts()
        assert len(parts) == 2  # sides + fill cap (#627)
        part = parts[0]
        assert (part.item_id, part.part_index, part.kind) == ("a", 0, "vc")
        assert part.position == pytest.approx((300.0, 0.0, -120.0))   # (E, base, −N)
        assert part.yaw_deg == pytest.approx(17.0)                    # eulerRotation.y = +rotation
        assert part.tint_rgb == RED[:3] and part.casts_shadow and part.has_geometry
        assert part.visible is True
        assert _uploads() - before == 2  # one per Model

    def test_every_material_kind_gets_a_model(self, host) -> None:
        sink = Quick3DSink(host)
        mesh = prism_mesh([SQUARE], 20.0)
        kinds = ("vc", "roof", "foliage", "grass", "glass", "water")
        sink.begin()
        sink.add("all", tuple(MeshPart(mesh, kind, casts_shadow=kind != "glass", tinted=True)
                              for kind in kinds), Transform(), Material("SHED", fill_rgba=BLUE))
        sink.commit()
        parts = sorted(host.engine_parts(), key=lambda p: p.part_index)
        assert tuple(p.kind for p in parts) == kinds
        assert all(p.tint_rgb == BLUE[:3] for p in parts)
        assert [p.casts_shadow for p in parts] == [k != "glass" for k in kinds]

    def test_move_recolour_replace_remove_and_clear(self, host) -> None:
        sink = Quick3DSink(host)
        recording = RecordingSink()
        syncs = (SceneSync(sink), SceneSync(recording))

        def apply(records: dict[str, Record]) -> int:
            before = _uploads()
            for sync in syncs:
                sync.apply(records)
            assert sink.state() == recording.state()
            return _uploads() - before

        assert apply({"a": _record("a"), "b": _record("b", 400.0, colour=BLUE)}) == 4
        assert apply({"a": _record("a", -250.0, -150.0, 30.0), "b": _record("b", 400.0, colour=BLUE)}) == 0
        moved = next(p for p in host.engine_parts() if p.item_id == "a")
        assert moved.position == pytest.approx((-250.0, 0.0, 150.0)) and moved.yaw_deg == pytest.approx(30.0)
        assert apply({"a": _record("a", -250.0, -150.0, 30.0, colour=(250, 220, 10, 255)),
                      "b": _record("b", 400.0, colour=BLUE)}) == 0   # a recolour uploads nothing
        assert next(p for p in host.engine_parts() if p.item_id == "a").tint_rgb == (250, 220, 10)
        assert apply({"a": _record("a", -250.0, -150.0, 30.0, colour=(250, 220, 10, 255), height=300.0),
                      "b": _record("b", 400.0, colour=BLUE)}) == 2   # new geometry: two fresh uploads
        assert len(host.engine_parts()) == 4
        assert apply({"b": _record("b", 400.0, colour=BLUE)}) == 0
        assert [p.item_id for p in host.engine_parts()] == ["b", "b"]
        syncs[0].set_sun(SunState(40.0, 180.0))
        syncs[0].set_ground(GroundSpec(100.0, 100.0))
        sink.clear()
        assert host.engine_parts() == []
        assert host.scene_property("sunUp") is False and host.scene_property("groundVisible") is False

    def test_a_dead_handle_and_an_unknown_kind_are_refused(self, host) -> None:
        from open_garden_planner.core.scene3d import engine_pose
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        pose = engine_pose(Transform())
        handle = host.create_part(PartSpec("a", 0, "vc", buffers, True), pose, RED)
        host.destroy_part(handle)
        for call in (lambda: host.destroy_part(handle), lambda: host.pose_part(handle, pose),
                     lambda: host.tint_part(handle, RED), lambda: host.pose_part(object(), pose)):
            with pytest.raises(EngineError, match="not a live part"):
                call()
        with pytest.raises(EngineError, match="no part component for material kind 'lava'"):
            host.create_part(PartSpec("a", 0, "lava", buffers, True), pose, RED)
        assert host.engine_parts() == []

    def test_a_hidden_model_is_still_listed_and_a_destroyed_one_is_not(self, host) -> None:
        """Review P2-10: ``listParts()`` treated "invisible" as "destroyed". A Model a later
        story hides on purpose is still the engine's — listed, ``visible=False``; a
        destroyed one is gone from the list at once, before its deferred delete."""
        from open_garden_planner.core.scene3d import engine_pose

        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        kept = host.create_part(PartSpec("kept", 0, "vc", buffers, True), engine_pose(Transform()), RED)
        gone = host.create_part(PartSpec("gone", 0, "vc", buffers, True), engine_pose(Transform()), RED)
        assert kept.model.setProperty("visible", False)
        host.destroy_part(gone)
        (part,) = host.engine_parts()  # no event loop ran: the destroyed Model still exists in Qt
        assert (part.item_id, part.visible, part.has_geometry) == ("kept", False, True)

    def test_a_destroyed_model_is_deleted_not_only_retired(self, host) -> None:
        """Destruction, counted in the QML scene itself. A Model that was only RETIRED —
        flagged, unpickable, never deleted — is invisible to ``engine_parts()`` (which
        skips retired Models by design) and to every pixel test (its geometry dies with
        the Python handle, so it draws nothing): a leak nothing else would see. Found by
        a mutant that survived the render tier."""
        from PyQt6.QtCore import QCoreApplication, QEvent, QObject

        from open_garden_planner.core.scene3d import engine_pose

        def models_alive() -> int:
            """Every part Model object in the scene, retired ones included."""
            return sum(1 for child in host._root.findChildren(QObject)  # noqa: SLF001
                       if child.metaObject().indexOfProperty("retired") >= 0)

        def deliver_deferred_deletes() -> None:
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        handles = [host.create_part(PartSpec(str(k), 0, "vc", buffers, True),
                                    engine_pose(Transform()), RED) for k in range(3)]
        assert models_alive() == 3
        host.destroy_part(handles[0])
        host.destroy_part(handles[1])
        assert len(host.engine_parts()) == 1, "gone from the listing at once"
        deliver_deferred_deletes()
        assert models_alive() == 1, "and gone from the scene once Qt delivered the delete"
        host.clear()
        deliver_deferred_deletes()
        assert models_alive() == 0

    def test_the_host_owns_every_model_and_clear_destroys_them_all(self, host) -> None:
        """One owner of Model lifetime (review P1-3): also parts no sink knows about."""
        from open_garden_planner.core.scene3d import engine_pose

        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        handles = [host.create_part(PartSpec(str(k), 0, "vc", buffers, True),
                                    engine_pose(Transform()), RED) for k in range(3)]
        host.set_sun((0.0, -1.0, 0.0))
        assert len(host.engine_parts()) == 3 and host.scene_property("sunUp") is True
        host.clear()
        assert host.engine_parts() == [] and host.scene_property("sunUp") is False
        assert all(handle.model is None and handle.geometry is None for handle in handles)
        host.clear()  # idempotent


class TestSunGroundCamera:
    @pytest.mark.parametrize(("elevation", "azimuth"), [(35.0, 225.0), (60.0, 180.0), (12.0, 95.0),
                                                        (90.0, 0.0)])
    def test_the_light_shines_along_the_suns_travel(self, host, elevation: float,
                                                    azimuth: float) -> None:
        """A DirectionalLight shines down its local −Z; the rotation the host hands the
        scene must turn −Z onto the light's travel — the negated sun vector, in the
        engine frame."""
        sun = SunState(elevation, azimuth)
        sync = SceneSync(Quick3DSink(host))
        sync.set_sun(sun)
        assert host.scene_property("sunUp") is True
        rotation: QQuaternion = host.scene_property("sunRotation")
        shines = rotation.rotatedVector(QVector3D(0.0, 0.0, -1.0))
        east, north, up = sun.light_travel_scene
        assert (shines.x(), shines.y(), shines.z()) == pytest.approx((east, up, -north), abs=1e-5)
        assert shines.y() < 0.0  # downwards

    def test_a_sun_that_is_down_switches_the_light_off(self, host) -> None:
        sync = SceneSync(Quick3DSink(host))
        sync.set_sun(SunState(40.0, 180.0))
        sync.set_sun(SunState(-6.0, 300.0))
        assert host.scene_property("sunUp") is False

    def test_the_ground_is_the_plan_rectangle(self, host) -> None:
        sync = SceneSync(Quick3DSink(host))
        sync.set_ground(GroundSpec(2400.0, 1600.0))
        assert host.scene_property("groundVisible") is True
        center: QVector3D = host.scene_property("groundCenter")
        assert (center.x(), center.y(), center.z()) == (1200.0, 0.0, -800.0)
        assert host.scene_property("groundWidth") == 2400.0
        assert host.scene_property("groundDepth") == 1600.0

    def test_cameras_are_placed_in_the_engine_frame(self, host) -> None:
        host.set_shot(PerspectiveShot(eye=(100.0, -700.0, 420.0), target=(10.0, 20.0, 30.0), fov_deg=50.0))
        eye, target = host.scene_property("camPos"), host.scene_property("camTarget")
        assert (eye.x(), eye.y(), eye.z()) == (100.0, 420.0, 700.0)        # (E, up, −N)
        assert (target.x(), target.y(), target.z()) == (10.0, 30.0, -20.0)
        assert host.scene_property("camFov") == 50.0 and host.scene_property("topDown") is False
        version = host.scene_property("camVersion")
        host.set_shot(TopDownShot(center=(1200.0, 800.0), px_per_cm=0.25))
        target = host.scene_property("camTarget")
        assert (target.x(), target.z()) == (1200.0, -800.0)
        assert host.scene_property("topDown") is True and host.scene_property("topDownScale") == 0.25
        host.set_camera((0.0, -500.0, 300.0), (0.0, 0.0, 0.0))
        assert host.scene_property("camVersion") == version + 1 and host.scene_property("camFov") == 40.0

    def test_the_fog_follows_the_cameras_distance(self, host) -> None:
        """Owner, L4 manual pass: the plan a camera frames lies in front of the fog
        (``look.fog_depth_cm``); the scene's Fog binds the two properties."""
        from open_garden_planner.core.scene3d.look import fog_depth_cm

        host.set_camera((0.0, -500.0, 300.0), (0.0, 0.0, 0.0))  # 5.8 m: L1's fog
        assert (host.scene_property("fogNear"), host.scene_property("fogFar")) == (2_600.0, 16_000.0)
        eye, target = (1_200.0, -6_000.0, 5_000.0), (1_200.0, 800.0, 0.0)
        host.set_camera(eye, target)
        near, far = host.scene_property("fogNear"), host.scene_property("fogFar")
        assert (near, far) == pytest.approx(fog_depth_cm(math.dist(eye, target)))
        assert near > math.dist(eye, target)

    @pytest.mark.parametrize("preset", PRESETS)
    def test_ambient_occlusion_runs_only_where_the_look_asks_for_it(self, host, preset: str) -> None:
        """3D review of L4's second owner pass: Qt's ``setAoStrength`` turns the AO pass
        on whenever the strength is not 0, whatever ``aoEnabled`` says. The strength's
        fade with the camera's distance (45 m to 90 m) switched SSAO on at Low, and so in
        compatibility mode, once the camera stood in between."""
        look = look_for(SunState(40.0, 200.0), preset)
        host.set_look(look)
        environment = _scene_environment(host)
        for distance in (500.0, 5_500.0, 6_700.0, 9_500.0, 500.0):
            host.set_camera((0.0, -0.8 * distance, 0.6 * distance), (0.0, 0.0, 0.0))
            share = min(1.0, max(0.0, (9_000.0 - distance) / 4_500.0))
            wanted = look.preset.ambient_occlusion and share > 0.0
            assert environment.property("aoEnabled") is wanted, distance
            assert environment.property("aoStrength") == pytest.approx(55.0 * share if wanted else 0.0), distance
        host.set_top_down((0.0, 0.0), 0.25)
        assert environment.property("aoEnabled") is False and environment.property("aoStrength") == 0.0

    def test_a_shot_that_cannot_be_rendered_is_refused(self, host) -> None:
        with pytest.raises(ValueError, match="same point"):
            host.set_camera((1.0, 2.0, 3.0), (1.0, 2.0, 3.0))
        with pytest.raises(ValueError, match="px_per_cm"):
            host.set_top_down((0.0, 0.0), 0.0)


def _engine(scene_vector: tuple[float, float, float]) -> tuple[float, float, float]:
    """Scene (E, N, up) -> engine (x = E, y = up, z = -N), written out by hand."""
    east, north, up = scene_vector
    return (east, up, -north)


class TestKeyLight:
    """Gate G1 of L1.4: light travel = -sun vector — whatever look is on screen; at night
    the moon rig's stated direction. Read from the QML scene the engine draws from."""

    @pytest.mark.parametrize("preset", ["low", "high"])
    @pytest.mark.parametrize("elevation", [0.5, 3.0, 5.89, 15.23, 30.0, 60.9, 89.9])
    @pytest.mark.parametrize("azimuth", [0.0, 45.0, 135.0, 180.0, 225.0, 301.5, 359.0])
    def test_by_day_the_light_travels_along_minus_the_sun_vector(
            self, host, elevation: float, azimuth: float, preset: str) -> None:
        sun = SunState(elevation, azimuth)
        sync = SceneSync(Quick3DSink(host))
        host.set_look(look_for(sun, preset))            # the look first …
        sync.set_sun(sun)
        expected = _engine(tuple(-c for c in sun.direction_scene))
        assert host.scene_property("sunUp") is True
        assert _light_travel(host) == pytest.approx(expected, abs=1e-5)
        host.set_look(look_for(sun, "medium"))          # … and the look after the sun
        assert _light_travel(host) == pytest.approx(expected, abs=1e-5)
        assert _light_travel(host)[1] < 0.0, "downwards"

    def test_a_day_look_made_for_another_sun_cannot_aim_the_light(self, host) -> None:
        """Truth before beauty: the look carries no sun direction, so a stale or foreign
        day look changes colours and nothing else."""
        sun = SunState(35.0, 225.0)
        SceneSync(Quick3DSink(host)).set_sun(sun)
        host.set_look(look_for(SunState(8.0, 90.0), "high"))
        assert _light_travel(host) == pytest.approx(
            _engine(tuple(-c for c in sun.direction_scene)), abs=1e-5)

    @pytest.mark.parametrize(("elevation", "azimuth"), [(0.49, 310.0), (-6.0, 330.0), (-40.0, 20.0)])
    def test_at_night_the_key_light_is_the_moon_rigs_stated_direction(
            self, host, elevation: float, azimuth: float) -> None:
        sun = SunState(elevation, azimuth)
        sync = SceneSync(Quick3DSink(host))
        sync.set_sun(sun)
        assert host.scene_property("sunUp") is False, "the sun is down and no look said night yet"
        host.set_look(look_for(sun, "high"))
        assert host.scene_property("sunUp") is True
        assert _light_travel(host) == pytest.approx(_engine(moon_travel_scene()), abs=1e-5)
        east, north, up = moon_travel_scene()
        assert up < 0.0 and north > 0.0, "from high in the south: it travels down and northwards"

    def test_dusk_and_dawn_hand_the_light_over(self, host) -> None:
        sync = SceneSync(Quick3DSink(host))
        day, night = SunState(4.0, 290.0), SunState(-4.0, 300.0)
        for sun in (day, night, day):
            sync.set_sun(sun)
            host.set_look(look_for(sun, "high"))
            travel = moon_travel_scene() if not sun.is_up else tuple(-c for c in sun.direction_scene)
            assert host.scene_property("sunUp") is True
            assert _light_travel(host) == pytest.approx(_engine(travel), abs=1e-5)

    def test_no_sun_and_a_day_look_is_no_key_light(self, host) -> None:
        host.set_look(look_for(SunState(40.0, 180.0), "high"))
        assert host.scene_property("sunUp") is False
        sync = SceneSync(Quick3DSink(host))
        sync.set_sun(SunState(40.0, 180.0))
        sync.reset()        # the sink's teardown: the sun goes, the look stays
        assert host.scene_property("sunUp") is False

    def test_the_antiparallel_direction_is_aimed_too(self, host) -> None:
        """Light travelling along the engine's +Z is the one direction a rotation "from
        -Z" has no unique axis for."""
        host.set_sun((0.0, 0.0, 1.0))
        assert _light_travel(host) == pytest.approx((0.0, 0.0, 1.0), abs=1e-5)


class TestSky:
    """Gate G4's engine half that needs no GPU: what is built, when, and from what."""

    def test_a_sky_is_built_only_when_asked_and_once_per_call(self, host) -> None:
        look = look_for(SunState(20.0, 240.0), "high")
        host.set_look(look)
        assert host.sky is None and host.scene_property("skyBuilt") is False
        host.set_sky(look.sky)
        assert host.sky == look.sky and host.sky_builds == 1
        assert host.scene_property("skyBuilt") is True and host.scene_property("skyBuilds") == 1
        assert host.last_sky_build_ms > 0.0
        for preset in PRESETS:                    # looks, however many, build nothing
            host.set_look(look_for(SunState(20.0, 240.0), preset))
        assert host.sky_builds == 1 and host.scene_property("skyBuilds") == 1
        other = look_for(SunState(22.0, 243.0), "high").sky
        host.set_sky(other)
        assert host.sky == other and host.sky_builds == 2 and host.scene_property("skyBuilds") == 2

    def test_every_build_is_a_fresh_texture_that_owns_its_own_data(self, host) -> None:
        """The pair lives and dies together (``Garden.qml``): a Texture loses its data
        when a data object it held EARLIER is destroyed, so no Texture is re-pointed and
        the data object is its Texture's child."""
        from PyQt6.QtCore import QCoreApplication, QEvent

        seen = []
        for azimuth in (100.0, 140.0, 180.0):
            host.set_sky(look_for(SunState(30.0, azimuth), "high").sky)
            texture = _sky_texture(host)
            data = texture.property("textureData")
            assert data is not None and data.parent() is texture, "the data is the Texture's child"
            assert all(texture is not old_texture and data is not old_data
                       for old_texture, old_data in seen)
            seen.append((texture, data))
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        from PyQt6 import sip

        assert [sip.isdeleted(texture) for texture, _data in seen] == [True, True, False]
        assert [sip.isdeleted(data) for _texture, data in seen] == [True, True, False]
        assert _sky_texture(host) is seen[-1][0]

    def test_the_inputs_reach_the_generator(self, host) -> None:
        sky = look_for(SunState(12.0, 250.0), "high").sky
        host.set_sky(sky)
        data = _sky_texture(host).property("textureData")
        for name, value in sky_properties(sky).items():
            shown = data.property(name)
            if isinstance(value, str):
                assert shown == QColor(value), name
            else:
                assert shown == pytest.approx(value), name
        assert data.property("sunLongitude") == pytest.approx(340.0), "azimuth + 90 degrees"

    def test_dropping_the_sky_goes_back_to_the_plain_background(self, host) -> None:
        host.set_sky(look_for(SunState(30.0, 180.0), "high").sky)
        host.set_sky(None)
        assert host.sky is None and host.scene_property("skyBuilt") is False
        host.set_sky(None)      # nothing to drop: no call into the scene
        assert host.sky_builds == 1

    def test_the_sinks_teardown_leaves_the_look_and_the_sky_alone(self, host) -> None:
        sync = SceneSync(Quick3DSink(host))
        look = look_for(SunState(-10.0, 0.0), "medium")
        sync.apply({"a": _record("a")}, sun=SunState(-10.0, 0.0))
        host.set_look(look)
        host.set_sky(look.sky)
        sync.reset()
        _assert_look_shown(host, look)
        assert host.sky == look.sky and host.scene_property("skyBuilt") is True
        assert host.scene_property("sunUp") is True, "the moon is the look's, not the pipeline's"


def _sky_texture(host: Any) -> Any:
    """The scene's sky Texture object (None: no sky)."""
    return host.scene_property("skyTextureObject")


class TestWind:
    """Gate G7's engine half: the wind's clock runs only while it is told to."""

    @staticmethod
    def _ticks(host: Any, qtbot: Any, ms: int) -> tuple[int, float]:
        from PyQt6.QtQml import QQmlProperty

        count = [0]

        def tick() -> None:
            count[0] += 1

        watched = QQmlProperty(host._root, "windTime")
        assert watched.connectNotifySignal(tick)
        before = float(host.scene_property("windTime"))
        qtbot.wait(ms)
        return count[0], float(host.scene_property("windTime")) - before

    def test_at_rest_nothing_ticks(self, host, qtbot) -> None:
        ticks, moved = self._ticks(host, qtbot, 300)
        assert (ticks, moved) == (0, 0.0)
        assert host.scene_property("windTime") == 0.0

    @staticmethod
    def _advances(host: Any, qtbot: Any, ticks: int = 3) -> float:
        """Wait for ``ticks`` changes of the running clock (no seconds bound: how fast
        frames come is the machine's business) and return how far it moved."""
        from PyQt6.QtQml import QQmlProperty

        count = [0]

        def tick() -> None:
            count[0] += 1

        watched = QQmlProperty(host._root, "windTime")
        assert watched.connectNotifySignal(tick)
        before = float(host.scene_property("windTime"))
        qtbot.waitUntil(lambda: count[0] >= ticks, timeout=20000)
        return float(host.scene_property("windTime")) - before

    def test_running_it_advances_and_stopping_freezes_it_where_it_is(self, host, qtbot) -> None:
        host.set_wind_running(True)
        assert self._advances(host, qtbot) > 0.0      # the positive control
        host.set_wind_running(False)
        frozen = host.scene_property("windTime")
        ticks, moved = self._ticks(host, qtbot, 300)
        assert (ticks, moved) == (0, 0.0), "stopped: not one tick"
        assert host.scene_property("windTime") == frozen > 0.0, "frozen — which is NOT rest"
        host.set_wind_running(True)
        assert self._advances(host, qtbot, 1) > 0.0, "and it goes on from there"
        assert host.scene_property("windTime") > frozen

    def test_rest_stops_the_clock_and_puts_it_back_to_zero(self, host, qtbot) -> None:
        host.set_wind_running(True)
        qtbot.waitUntil(lambda: host.scene_property("windTime") > 0.0, timeout=20000)
        host.rest_wind()
        assert host.scene_property("windTime") == 0.0
        assert host.scene_property("windRunning") is False
        assert self._ticks(host, qtbot, 200) == (0, 0.0)


def _facts(**changes: Any) -> Any:
    """Qt's facts as a live, answerable 320 x 240 window reports them — with ``changes``
    (``size=(w, h)`` sets the WINDOW's size and leaves the scene's at 320 x 240)."""
    from open_garden_planner.ui.view3d.quick3d.lifecycle import WindowFacts

    width, height = changes.pop("size", (320, 240))
    base = {"surface_created": True, "visible": True, "minimised": False, "width": width,
            "height": height, "scene_graph": True, "exposed": True, "root_width": 320.0,
            "root_height": 240.0}
    return WindowFacts(**{**base, **changes})


class _Later(QObject):
    """Runs ``what`` when the event loop delivers the event posted here — what a resize or
    an expose that is still in Qt's queue is to a host."""

    def __init__(self, what: Any) -> None:
        super().__init__()
        self._what = what
        QCoreApplication.postEvent(self, QEvent(QEvent.Type.User))

    def event(self, event: QEvent | None) -> bool:
        if event is not None and event.type() == QEvent.Type.User:
            self._what()
            return True
        return super().event(event)


def _frames(host: Any, *sizes: tuple[int, int]) -> list[tuple[int, int]]:
    """Decide what Qt "renders" from now on: frames of ``sizes``, in that order, the last
    one for ever. Returns the list of frames taken so far (it grows). The offscreen
    platform draws no 3D and has no render target that could lag — what the host does
    WITH a frame of the right or the wrong size is what can be tested here; that Qt hands
    out such frames, and when, is the render tier's."""
    from PyQt6.QtGui import QImage

    taken: list[tuple[int, int]] = []

    def grab_window() -> QImage:
        size = sizes[min(len(taken), len(sizes) - 1)]
        taken.append(size)
        return QImage(size[0], size[1], QImage.Format.Format_RGB32)

    host._view.grabWindow = grab_window  # noqa: SLF001
    host._frames_stubbed = True  # noqa: SLF001
    return taken


def _force(host: Any, *, spent: bool = False, renders_3d: bool = True, **changes: Any) -> None:
    """Put Qt's facts where a real window system would (the offscreen platform cannot:
    it renders no 3D, and nothing collapses or minimises there). The state is a pure
    function of them (``lifecycle.state_of``; its whole truth table is in
    ``tests/unit/test_quick3d_lifecycle_states.py``) — which is what makes the host
    testable here; that Qt's facts DO take these values, and what happens then, is the
    render tier's (``test_quick3d_lifecycle.py``).

    With ``renders_3d`` the host believes it can render, so a live one TAKES frames: unless
    a test decided otherwise (``_frames``), Qt then "renders" frames of the forced
    window's size — nothing here reaches the real ``grabWindow()`` by accident."""
    forced = _facts(**changes)
    host._facts = lambda: forced  # noqa: SLF001
    host._spent = spent  # noqa: SLF001
    if renders_3d:
        host.graphics_api = lambda: "Direct3D11"
        if not getattr(host, "_frames_stubbed", False):
            _frames(host, (forced.width, forced.height))
            host._frames_stubbed = False  # noqa: SLF001 - a default: the next _force renews it


def _sign(host: Any, kind: str = "expose") -> None:
    """Hand the host's watch an event of its view, as Qt would."""
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QExposeEvent, QRegion, QResizeEvent

    event = (QResizeEvent(QSize(320, 240), QSize(320, 240)) if kind == "resize"
             else QExposeEvent(QRegion(0, 0, 320, 240)))
    host._watch.eventFilter(host._view, event)  # noqa: SLF001


STALE = "render target has not caught up"
#: Facts → the state the host must report, and the words its refusal must contain.
NO_FRAME = [
    ({"scene_graph": False, "exposed": False}, "starting", r"would kill the process.*wait_ready\(\)"),
    ({"scene_graph": False}, "starting", r"would kill the process.*wait_ready\(\)"),
    ({"exposed": False}, "starting", r"shown again but not exposed yet.*wait_ready\(\)"),
    ({"root_width": 0.0}, "starting", r"has not caught up.*scene 0 x 240.*wait_ready\(\)"),
    ({"size": (200, 240)}, "starting", r"has not caught up.*window 200 x 240, scene 320 x 240"),
    ({"visible": False}, "hidden", "not visible"),
    ({"visible": False, "exposed": False}, "hidden", "not visible"),
    ({"minimised": True}, "hidden", "minimised"),
    ({"size": (0, 240)}, "hidden", r"no usable area \(0 x 240 px"),       # the collapsed pane
    ({"size": (1, 240)}, "hidden", r"no usable area \(1 x 240 px.*Below 2 px"),
    ({"size": (320, 1)}, "hidden", r"no usable area \(320 x 1 px"),
]


class TestStateMachine:
    """Review rounds 1 to 4. The state is derived from Qt on every call; no Python flag
    says "shown" (the parent of an embedded container shows, hides, resizes and
    collapses it without asking) — and none says "a frame will have the right size":
    only a frame says that."""

    def test_the_host_reads_its_facts_from_qt(self, host) -> None:
        """What the real window says here, under the offscreen platform — the plumbing
        from Qt into ``WindowFacts``. (No fact is a Python flag: each changes because Qt
        changed.)"""
        born = host._facts()  # noqa: SLF001
        assert (born.surface_created, born.visible, born.minimised) == (False, False, False)
        assert (born.width, born.height, born.root_width, born.root_height) == (320, 240, 320.0, 240.0)
        assert host.state.value == "new" and host.is_visible() is False
        host.show()
        assert host._facts().surface_created is True, "Qt created the platform window"  # noqa: SLF001
        assert host.wait_ready(5.0) and host.state.value == "live"
        shown = host._facts()  # noqa: SLF001
        assert (shown.visible, shown.scene_graph, shown.exposed) == (True, True, True)
        assert host.is_visible() is True
        resizes, signs = host._watch.resizes, host._watch.signs  # noqa: SLF001
        host._view.resize(200, 100)  # noqa: SLF001
        assert host.wait_ready(5.0)
        resized = host._facts()  # noqa: SLF001
        assert (resized.width, resized.height, resized.root_width, resized.root_height) == (
            200, 100, 200.0, 100.0)
        assert host._watch.resizes == resizes + 1 and host._watch.signs > signs  # noqa: SLF001
        host.hide()
        assert host._facts().visible is False and host.state.value == "hidden"  # noqa: SLF001

    def test_shown_and_hidden_again_before_any_event_is_not_new(self, host) -> None:
        """Review round 2, P1-A — the red CI job. ``show(); hide()`` with no event in
        between: no scene graph, not visible. The first state machine called that
        ``new`` and took the offscreen frame; on xcb the process segfaulted in the
        next event-loop pass. The platform window EXISTS — the host is hidden, has no
        offscreen frame, and is not spent by the refusal."""
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        host.show()
        host.hide()
        assert host._facts().surface_created is True  # noqa: SLF001
        assert host.state.value == "hidden"
        host.graphics_api = lambda: "Direct3D11"  # past the "no 3D here" check, to the state's
        with pytest.raises(HostStateError, match="not visible"):
            host.grab("after show and hide")
        assert host._spent is False and host.grabs == 0  # noqa: SLF001
        assert host.wait_ready(5.0) is False

    def test_only_a_window_that_never_had_a_platform_window_is_new(self, host) -> None:
        _force(host, surface_created=False, visible=False, exposed=False, scene_graph=False)
        assert host.state.value == "new"
        _force(host, surface_created=True, visible=False, exposed=False, scene_graph=False)
        assert host.state.value == "hidden"

    @pytest.mark.parametrize(("changes", "state", "_words"), NO_FRAME)
    def test_the_state_follows_the_facts(self, host, changes: dict[str, Any], state: str,
                                         _words: str) -> None:
        _force(host)
        assert host.state.value == "live"
        _force(host, **changes)
        assert host.state.value == state
        assert host.is_closed is False and host.is_visible() is changes.get("visible", True)
        _force(host, spent=True, **changes)
        assert host.state.value == "spent"

    @pytest.mark.parametrize(("changes", "_state", "words"), NO_FRAME)
    def test_no_frame_no_pick_no_projection_unless_live(self, host, changes: dict[str, Any],
                                                        _state: str, words: str) -> None:
        """THE guard, in every state that is not live. Shown and grabbed before the first
        expose: a good image and a dead process. A collapsed pane (review round 2,
        P1-B): Qt calls the window visible and exposed, the grab is blank, the pick
        bogus, the projection (0, 0). One pixel wide: no 3D is drawn. Resized a moment
        ago: the scene still has the old size. Qt is NOT asked for a frame in any of
        them — asking is what kills."""
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        taken = _frames(host, (320, 240))
        _force(host, **changes)
        for call in (lambda: host.grab("no"), lambda: host.pick(1.0, 1.0),
                     lambda: host.project(0.0, 0.0, 0.0), lambda: host.wait_ready(0.0)):
            if call.__code__.co_names[-1] == "wait_ready":
                assert call() is False
                continue
            with pytest.raises(HostStateError, match=words):
                call()
        assert taken == [], "a host that is not live must not ask Qt for a frame"
        assert host.grabs == 0 and host._spent is False, "a refusal must not spend the host"  # noqa: SLF001

    def test_a_spent_host_refuses_everything_that_would_kill_it(self, host) -> None:
        """One hidden grab, then ``show()`` — what the old message recommended — killed
        the process. A spent host says: build a new one."""
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        _force(host, spent=True, visible=False, exposed=False, scene_graph=False)
        for call in (host.show, host.container, lambda: host.grab("again"),
                     lambda: host.pick(1.0, 1.0)):
            with pytest.raises(HostStateError, match="Build a new host") as caught:
                call()
            assert "show() it" not in str(caught.value)
        assert host.wait_ready(5.0) is False  # at once: nothing is on its way
        host.hide()                           # harmless

    def test_an_embedded_host_has_no_offscreen_frame(self, host, qtbot) -> None:
        """Its parent may show it at any moment — and then the process would die."""
        from PyQt6.QtWidgets import QWidget

        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        parent = QWidget()
        qtbot.addWidget(parent)
        host.container(parent)
        _force(host, surface_created=False, visible=False, exposed=False, scene_graph=False)
        with pytest.raises(HostStateError, match="embedded host has no offscreen frame"):
            host.grab("embedded")
        assert host.state.value == "new", "the refusal must not spend the host"

    def test_the_watch_counts_events_and_decides_nothing(self, host) -> None:
        """Review round 4, the ruling. Round 3's watch switched a fact ON when an expose
        arrived after a resize — "the render target has caught up" — and the state waited
        for it. Windows sends no expose to a pane that grows where no screen is: the host
        read "starting" for ever. The watch now COUNTS (resize events; events that can
        change what a frame is) and no event makes anything true."""
        from PyQt6.QtCore import QPointF, Qt
        from PyQt6.QtGui import QMouseEvent

        watch, view = host._watch, host._view  # noqa: SLF001
        assert not hasattr(watch, "target_synced") and (watch.resizes, watch.signs) == (0, 0)
        _force(host)
        assert host.state.value == "live"
        _sign(host, "resize")
        assert (watch.resizes, watch.signs) == (1, 1)
        assert host.state.value == "live", "an event changes no state: only Qt's facts do"
        _sign(host, "expose")
        assert (watch.resizes, watch.signs) == (1, 2) and host.state.value == "live"
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(1.0, 1.0), QPointF(1.0, 1.0),
                           Qt.MouseButton.NoButton, Qt.MouseButton.NoButton,
                           Qt.KeyboardModifier.NoModifier)
        assert watch.eventFilter(view, move) is False, "the watch never eats an event"
        assert watch.eventFilter(view, None) is False
        assert (watch.resizes, watch.signs) == (1, 2), "a mouse move is no sign of anything"

    def test_the_frame_is_the_witness(self, host) -> None:
        """Sentence 1 of the contract, and what it rests on. A live host is ASKED for a
        frame; the frame's size decides. Of the window's size: the answer. Of another
        size — the render target is behind, after ``showFullScreen()`` or beyond the
        screen's edge —: ``HostStateError``, counted, and nothing remembered: the host
        still says it is live and asks Qt again the next time."""
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        taken = _frames(host, (320, 240), (49, 240), (49, 240), (320, 240))
        _force(host)
        assert host.grab("fits").width() == 320
        assert (host.grabs, host.stale_frames, taken) == (1, 0, [(320, 240)])
        for _ in range(2):
            with pytest.raises(HostStateError, match=r"49 x 240 px image for a 320 x 240 window.*"
                               + STALE + r".*wait_ready\(\)"):
                host.grab("the old size")
            assert host.state.value == "live", "nothing is latched: the state is Qt's facts"
        assert (host.grabs, host.stale_frames, len(taken)) == (1, 2, 3)
        assert host.grab("caught up").width() == 320, "the next call asks Qt again"
        assert (host.grabs, host.stale_frames, len(taken)) == (2, 2, 4)

    @pytest.mark.parametrize(("image", "ratio", "window", "fits"), [
        ((320, 240), 1.0, (320, 240), True),
        ((319, 240), 1.0, (320, 240), False), ((321, 240), 1.0, (320, 240), False),
        ((320, 239), 1.0, (320, 240), False), ((320, 242), 1.0, (320, 240), False),
        ((640, 480), 2.0, (320, 240), True), ((638, 480), 2.0, (320, 240), False),
        # a fractional ratio rounds: 447 x 1.5 = 670.5 — Qt gives 671; 670 is as far off (half
        # a pixel) and is no window's frame at 1.5 (446 gives 669)
        ((671, 750), 1.5, (447, 500), True), ((670, 750), 1.5, (447, 500), True),
        ((669, 750), 1.5, (447, 500), False), ((672, 750), 1.5, (447, 500), False),
        # review round 5, measured on a real window at 125 %: a 442 px pane has a 553 px frame
        # (552.5 rounds up), a 443 px pane a 554 px one — and "less than one pixel off" took
        # the 553 px frame for the 443 px pane (0.75 off 553.75)
        ((553, 625), 1.25, (442, 500), True), ((554, 625), 1.25, (443, 500), True),
        ((553, 625), 1.25, (443, 500), False), ((554, 625), 1.25, (442, 500), False),
        ((553, 624), 1.25, (442, 500), False),
        # the same at 110 %: 446 -> 491 px (490.6), 447 -> 492 px (491.7)
        ((492, 550), 1.1, (447, 500), True), ((491, 550), 1.1, (447, 500), False),
    ])
    def test_the_size_check_is_exact_to_the_device_pixel(
            self, image: tuple[int, int], ratio: float, window: tuple[int, int], fits: bool) -> None:
        """What sentence 1 of the contract rests on. The check allowed TWO pixels until
        review round 4: a pane moved by one pixel, and the frame of the size it had before
        passed for the current one (measured: a 447 x 500 frame for a 448 x 500 window,
        handed out). And "less than one" until round 5 — true at 100 %, 150 % and 200 %, and
        not in between. The rule is Qt's own rounding: half a device pixel."""
        from PyQt6.QtGui import QImage

        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        frame = QImage(image[0], image[1], QImage.Format.Format_RGB32)
        frame.setDevicePixelRatio(ratio)
        found = Quick3DHost._other_size(frame, _facts(size=window))  # noqa: SLF001
        assert (found is None) is fits, found
        if not fits:
            assert f"{image[0]} x {image[1]} px image for a {window[0]} x {window[1]} window" in found

    RATIOS: ClassVar = (1.0, 1.1, 1.2, 1.25, 1.3, 1.4, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0)

    @pytest.mark.parametrize("ratio", RATIOS)
    def test_the_size_check_is_qts_own_rounding_at_every_ratio(self, ratio: float) -> None:
        """Review round 5, P1-1 — the arithmetic, for every logical width from 2 to 3000 at
        twelve ratios: the frame QT makes for a window (``QSize * ratio``, asked of Qt
        here) is never refused, and the frame of a window one or two logical pixels
        smaller or larger is never taken for it. Before: 750 of 11,993 neighbour frames
        passed at 1.25, and every ratio strictly between 1 and 1.5 had some."""
        from PyQt6.QtCore import QSize

        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        class Frame:  # the three questions the check asks of an image
            def __init__(self, size: QSize) -> None:
                self._size = size

            def width(self) -> int:
                return self._size.width()

            def height(self) -> int:
                return self._size.height()

            def devicePixelRatio(self) -> float:  # noqa: N802 - Qt's name
                return ratio

        def frame_of(width: int) -> Frame:
            return Frame(QSize(width, 300) * ratio)  # Qt's own rounding, not a formula of ours

        other_size = Quick3DHost._other_size  # noqa: SLF001
        refused_right, accepted_neighbour, pairs = [], [], 0
        for width in range(2, 3001):
            window = _facts(size=(width, 300))
            if other_size(frame_of(width), window) is not None:
                refused_right.append(width)
            for neighbour in (width - 2, width - 1, width + 1, width + 2):
                if neighbour >= 2:
                    pairs += 1
                    if other_size(frame_of(neighbour), window) is None:
                        accepted_neighbour.append((neighbour, width))
        assert pairs == 11_993
        assert refused_right == [], f"Qt's own frame refused at {ratio}: {refused_right[:5]}"
        assert accepted_neighbour == [], (
            f"at {ratio} the frame of another window passed {len(accepted_neighbour)} times of "
            f"{pairs}, e.g. (its window, the window asked for) {accepted_neighbour[:3]}")

    def test_pick_and_project_answer_for_a_frame_of_the_windows_size(self, host) -> None:
        """Measured on Direct3D 11: right after a resize, with no frame in between, a pick
        MISSES the box under the cursor — the engine picks with the viewport of the frame
        it rendered last. So ``pick`` and ``project`` take a frame themselves when the
        host has none since the last resize — ONE, not one per call — and refuse when
        that frame has another size, without asking the scene and without a second frame
        (the test below)."""
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        asked: list[str] = []
        host._call = lambda name, *_a: asked.append(name) or {"hit": False, "x": 7.0, "y": 9.0}  # noqa: SLF001
        taken = _frames(host, (320, 240), (320, 240), (320, 240), (49, 240))
        _force(host)
        assert host.pick(1.0, 1.0) is None and host.project(0.0, 0.0, 0.0) == (7.0, 9.0)
        assert host.pick(2.0, 2.0) is None
        assert (len(taken), host.probes) == (1, 1), "one frame for this size, not one per call"
        assert asked == ["pickAt", "projectToView", "pickAt"]
        _sign(host, "resize")  # Qt resized the window (to the same size: the count is what matters)
        assert host.project(0.0, 0.0, 0.0) == (7.0, 9.0) and (len(taken), host.probes) == (2, 2)
        _sign(host, "resize")
        host.grab("a caller's own frame counts as well")
        assert host.pick(3.0, 3.0) is None and (len(taken), host.probes) == (3, 2)
        _sign(host, "resize")
        asked.clear()
        for call in (lambda: host.pick(1.0, 1.0), lambda: host.project(0.0, 0.0, 0.0)):
            with pytest.raises(HostStateError, match=STALE):
                call()
        assert asked == [], "refused on the evidence of the frame: the scene is not asked"
        assert (host.stale_frames, len(taken)) == (1, 4), "ONE frame for the two refusals"
        assert host.state.value == "live"

    def test_while_the_render_target_is_behind_a_tick_costs_one_frame(
            self, host, monkeypatch: pytest.MonkeyPatch) -> None:
        """Review round 5, P1-2. ``pick()`` / ``project()`` took a probe frame on EVERY
        call while the render target was behind: 200 ``project()`` of one tick, 200
        frames, all refused — 0.4 s on the GPU, 0.8 s on WARP, for nothing. Now a refusal
        stands until the host sees something else than it saw then (a sign of progress,
        another size) or ``REPROBE_S`` has passed: 200 refused calls, ONE frame — and a
        host that recovered is asked again at once when a sign came, and after
        ``REPROBE_S`` at the latest when none did."""
        from open_garden_planner.ui.view3d.quick3d import host as host_module
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        asked: list[str] = []
        host._call = lambda name, *_a: asked.append(name) or {"hit": False, "x": 7.0, "y": 9.0}  # noqa: SLF001
        monkeypatch.setattr(host_module, "REPROBE_S", 3600.0)  # the clock is not what is tested first
        taken = _frames(host, (49, 240))
        _force(host)

        def refused(call: Any, times: int) -> None:
            for _ in range(times):
                with pytest.raises(HostStateError, match=STALE):
                    call()

        refused(lambda: host.project(0.0, 0.0, 0.0), 200)
        assert (len(taken), host.probes, host.stale_frames) == (1, 1, 1), "200 refusals, one frame"
        refused(lambda: host.pick(1.0, 1.0), 200)
        assert (len(taken), host.probes, host.stale_frames) == (1, 1, 1), "and none for pick()"
        assert asked == [] and host.state.value == "live"
        # a caller's own grab() always takes a frame — and its refusal stands for the others
        refused(lambda: host.grab("wanted"), 2)
        assert (len(taken), host.probes) == (3, 1)
        refused(lambda: host.pick(1.0, 1.0), 50)
        assert len(taken) == 3

        # a sign of progress, and the frame still does not fit: ONE more frame
        _sign(host, "expose")
        refused(lambda: host.project(0.0, 0.0, 0.0), 200)
        assert (len(taken), host.probes) == (4, 2)
        # the host recovered, and a sign says so: the very next call answers
        _frames(host, (320, 240))
        _sign(host, "expose")
        assert host.project(0.0, 0.0, 0.0) == (7.0, 9.0) and host.pick(1.0, 1.0) is None
        assert host.probes == 3 and asked == ["projectToView", "pickAt"]

        # behind again — and it recovers WITHOUT a sign the watch counts: refused for
        # REPROBE_S at the most, then asked again
        _sign(host, "resize")
        taken = _frames(host, (49, 240))
        refused(lambda: host.pick(1.0, 1.0), 3)
        assert len(taken) == 1
        _frames(host, (320, 240))
        refused(lambda: host.pick(1.0, 1.0), 3)  # nothing told the host: the refusal stands
        monkeypatch.setattr(host_module, "REPROBE_S", 0.0)  # ... until the time is up
        assert host.pick(1.0, 1.0) is None

        # another size is something else than the host saw: it looks again at once
        monkeypatch.setattr(host_module, "REPROBE_S", 3600.0)
        _sign(host, "resize")
        taken = _frames(host, (49, 240))
        refused(lambda: host.pick(1.0, 1.0), 3)
        assert len(taken) == 1
        host._frames_stubbed = False  # noqa: SLF001
        _force(host, size=(200, 240), root_width=200.0)  # the pane has another size now
        assert host.pick(1.0, 1.0) is None, "new facts: a new frame, at once"

    def test_the_time_a_refusal_stands_is_short_and_stated(self) -> None:
        from open_garden_planner.ui.view3d.quick3d import host as host_module
        from open_garden_planner.ui.view3d.quick3d import lifecycle

        assert host_module.REPROBE_S == lifecycle.REPROBE_S == 0.25
        assert "``REPROBE_S`` (0.25 s)" in (lifecycle.__doc__ or "")

    def test_the_one_offscreen_frame_in_another_size_is_an_engine_error(self, host) -> None:
        """There is no "later" for the offscreen frame — the host is spent by it — so a
        wrong size there is nothing a caller could wait out."""
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        _force(host, surface_created=False, visible=False, exposed=False, scene_graph=False)
        assert host.state.value == "new"
        host._view.create = lambda: None  # noqa: SLF001 - Qt is not asked: its answer is given
        _frames(host, (50, 40))
        with pytest.raises(EngineError, match="50 x 40 px image for a 320 x 240 window.*"
                           "not the scene at this size"):
            host.grab("offscreen")
        assert host._spent is True and host.grabs == 0 and host.stale_frames == 0  # noqa: SLF001

    def test_request_frame_is_harmless_in_every_open_state(self, host) -> None:
        host.request_frame()
        host.show()
        assert host.wait_ready(5.0)
        host.request_frame()
        host.hide()
        host.request_frame()

    def test_the_container_embeds_the_view_and_takes_over_show_and_hide(self, host, qtbot) -> None:
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        parent = QWidget()
        qtbot.addWidget(parent)
        layout = QVBoxLayout(parent)
        container = host.container(parent)
        assert host.container() is container, "the container is created once"
        layout.addWidget(container)
        parent.resize(400, 300)
        parent.show()
        host.show()
        qtbot.waitUntil(container.isVisible, timeout=5000)
        assert host.wait_ready(5.0) and host.state.value == "live"
        container.hide()  # the PARENT's side hides it: host.hide() is never called
        assert host.state.value == "hidden" and not host.is_visible()
        container.show()
        assert host.wait_ready(5.0)
        host.hide()
        assert not container.isVisible()


# Only real elapsed-time assertions need the quiet runner. Signature, spy,
# fake-clock and bounded-call-count contracts run with the workers (#601).
class TestWaitReady:
    """The contract's sentences 2 and 3 (``lifecycle.py``): ``wait_ready(timeout_s)``
    starts no pass of the event loop once ``timeout_s`` is up; True means a frame of the
    window's size was just taken; and when nothing is on its way it says False promptly —
    after ``STALL_S`` of silence — never at the deadline."""

    def test_the_default_timeout_is_one_second_and_the_docstring_says_what_the_call_is(self) -> None:
        """Review round 5: the docstring said the default was "safe for one call on the
        GUI thread". It is a nested event loop that takes user input; the workspace needs
        it nowhere on the GUI thread, and the text says so."""
        import inspect

        from open_garden_planner.ui.view3d.quick3d import host as host_module
        from open_garden_planner.ui.view3d.quick3d import lifecycle

        default = inspect.signature(host_module.Quick3DHost.wait_ready).parameters["timeout_s"].default
        assert default == lifecycle.WAIT_READY_DEFAULT_S == 1.0, "10 s was not safe"
        text = " ".join((host_module.Quick3DHost.wait_ready.__doc__ or "").split())
        for words in ("NESTED EVENT LOOP", "takes user input", "nowhere on the GUI thread",
                      "Never call it from a timer slot", "except HostStateError",
                      "PLUS whatever was queued when its last pass began"):
            assert words in text, words

    @pytest.mark.perf
    def test_true_means_a_frame_of_the_windows_size_was_just_taken(self, host) -> None:
        taken = _frames(host, (320, 240))
        _force(host)
        started = time.perf_counter()
        assert host.wait_ready(5.0) is True
        assert time.perf_counter() - started < 0.4, "nothing to wait for"
        assert (taken, host.probes, host.stale_frames) == ([(320, 240)], 1, 0)
        assert host.grab("right after it").width() == 320

    @pytest.mark.perf
    def test_a_live_host_whose_frame_has_another_size_is_refused_promptly(self, host) -> None:
        """Review round 4 — THE finding, as far as it can be put here: Qt reports every
        fact, and the frame has the old size (a pane that grew beyond the screen's edge).
        Nothing is on its way. Round 3 waited for an expose until its deadline; now:
        ONE frame, a wait of ``STALL_S`` for a sign of progress, and False — whatever
        the timeout."""
        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        taken = _frames(host, (49, 240))
        _force(host)
        for timeout in (5.0, 60.0):
            before = len(taken)
            started = time.perf_counter()
            assert host.wait_ready(timeout) is False
            elapsed = time.perf_counter() - started
            assert STALL_S - 0.05 <= elapsed < STALL_S + 0.8, f"{elapsed:.2f} s of {timeout:g} s"
            assert len(taken) == before + 1, "no second frame while nothing has happened"
        assert host.state.value == "live" and host.stale_frames == 2

    @pytest.mark.perf
    def test_a_sign_of_progress_makes_it_take_another_frame(self, host) -> None:
        """The other half: the pane is moved back onto the screen, Qt draws it — an event
        arrives — and the next frame fits."""
        from PyQt6.QtCore import QTimer

        taken = _frames(host, (49, 240), (320, 240))
        _force(host)
        QTimer.singleShot(60, lambda: _sign(host, "expose"))
        started = time.perf_counter()
        assert host.wait_ready(5.0) is True
        assert 0.05 <= time.perf_counter() - started < 1.5
        assert taken == [(49, 240), (320, 240)] and host.stale_frames == 1

    @pytest.mark.perf
    def test_signs_that_keep_coming_do_not_keep_it_beyond_its_timeout(self, host) -> None:
        """Sentence 2 wins over sentence 3: while something keeps happening the host goes
        on looking — up to ``timeout_s``, not a moment longer."""
        from PyQt6.QtCore import QTimer

        taken = _frames(host, (49, 240))
        _force(host)
        ticker = QTimer()
        ticker.timeout.connect(lambda: _sign(host, "expose"))
        ticker.start(20)
        try:
            started = time.perf_counter()
            assert host.wait_ready(0.4) is False
            elapsed = time.perf_counter() - started
        finally:
            ticker.stop()
        assert 0.38 <= elapsed < 1.2, f"{elapsed:.2f} s for a 0.4 s timeout"
        assert 3 <= len(taken) <= 40, f"{len(taken)} frames: one per sign, never a spin"

    @pytest.mark.perf
    @pytest.mark.parametrize(("changes", "frame", "answer", "frames"), [
        ({}, (320, 240), True, 1), ({}, (49, 240), False, 1),
        ({"exposed": False}, (320, 240), False, 0), ({"visible": False}, (320, 240), False, 0),
    ], ids=["live, the frame fits", "live, the frame does not", "starting", "hidden"])
    def test_a_timeout_of_zero_delivers_nothing_and_waits_for_nothing(
            self, host, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any],
            frame: tuple[int, int], answer: bool, frames: int) -> None:
        """Review round 4: ``wait_ready(0.0)`` took 1.0 to 1.4 s — it delivered pending
        events (one expose handler) before it looked at its deadline. Now a zero timeout
        runs no event at all: it looks, takes at most one frame, and answers."""
        from open_garden_planner.ui.view3d.quick3d import host as host_module

        ran: list[str] = []

        class Spy:
            @staticmethod
            def processEvents(*_arguments: Any) -> None:  # noqa: N802 - Qt's name
                ran.append("processEvents")

        monkeypatch.setattr(host_module, "QCoreApplication", Spy)
        host._run_events = lambda _ms: ran.append("a pass") or True  # noqa: SLF001
        delivered: list[int] = []
        pending = _Later(lambda: delivered.append(1))
        taken = _frames(host, frame)
        _force(host, **changes)
        started = time.perf_counter()
        for timeout in (0.0, -3.0):
            assert host.wait_ready(timeout) is answer
        assert time.perf_counter() - started < 0.2
        assert ran == [] and delivered == [], "a zero timeout runs no event loop"
        assert len(taken) == 2 * frames
        del pending

    def test_it_delivers_what_is_pending_before_it_answers(self, host) -> None:
        """Review round 3, P1-1. A host can READ live while the event that changes that
        is still in Qt's queue — the parent hid the pane, or its layout has a new size
        for it. It answered True without a look at the queue."""
        _force(host)
        assert host.state.value == "live"
        pending = _Later(lambda: _force(host, visible=False))  # e.g. the parent hid the pane
        assert host.wait_ready(5.0) is False and host.state.value == "hidden"

        host._frames_stubbed = False  # noqa: SLF001
        _force(host)
        # the parent's layout has a new size for the view: the resize is in the queue
        pending = _Later(lambda: _force(host, size=(200, 240), root_width=200.0))
        assert host.wait_ready(5.0) is True
        assert host._frame_at is not None and host._frame_at[:2] == (200, 240), (  # noqa: SLF001
            "the frame it took was one of the size the window had AFTER the pending resize")
        del pending

    @pytest.mark.parametrize(("changes", "timeout", "expected"), [
        ({}, 5.0, [5000]), ({}, 0.25, [250]), ({"exposed": False}, 0.3, [300]),
        ({"minimised": True}, 5.0, [5000]), ({"size": (0, 240)}, 5.0, [5000]),
        ({"visible": False}, 5.0, []), ({"surface_created": False, "visible": False}, 5.0, []),
        ({}, 0.0, []),
        # review round 5, P2-3: these raised OverflowError (Qt takes milliseconds in a C int)
        ({}, float("inf"), [86_400_000]), ({}, 3.0e6, [86_400_000]), ({}, float("nan"), []),
        ({}, -float("inf"), []),
    ], ids=["live", "live, 0.25 s", "starting", "minimised", "collapsed", "not visible", "new",
            "no timeout", "infinity", "34 days", "not a number", "minus infinity"])
    def test_it_delivers_pending_events_once_and_inside_its_time(
            self, host, monkeypatch: pytest.MonkeyPatch, changes: dict[str, Any], timeout: float,
            expected: list[int]) -> None:
        """ONE delivery of what is queued, before the first look — also for a host that
        reads live — and INSIDE the timeout: Qt is told how long it may take (review
        round 4: the delivery used to sit outside the deadline). None for a host that is
        not visible: its parent shows it synchronously, nothing queued can make it ready."""
        from PyQt6.QtCore import QEventLoop

        from open_garden_planner.ui.view3d.quick3d import host as host_module

        limits: list[int] = []

        class Spy:
            @staticmethod
            def processEvents(flags: Any, limit_ms: int) -> None:  # noqa: N802 - Qt's name
                assert flags == QEventLoop.ProcessEventsFlag.AllEvents
                limits.append(limit_ms)

        monkeypatch.setattr(host_module, "QCoreApplication", Spy)
        _force(host, **changes)
        host.wait_ready(timeout)
        assert limits == expected

    @pytest.mark.perf
    @pytest.mark.parametrize("timeout", [float("inf"), 3.0e6, 1.0e300],
                             ids=["infinity", "34 days", "1e300"])
    def test_a_timeout_without_end_still_ends_after_the_stall_bound(self, host, timeout: float) -> None:
        """Review round 5, P2-3: ``wait_ready(float("inf"))`` raised ``OverflowError``. A
        timeout is clamped to a day — and sentence 3 holds whatever it is: nothing comes,
        False after ``STALL_S``."""
        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        _force(host, scene_graph=False, exposed=False)
        started = time.perf_counter()
        assert host.wait_ready(timeout) is False and host.state.value == "starting"
        assert STALL_S - 0.05 <= time.perf_counter() - started < STALL_S + 0.8

    @pytest.mark.perf
    def test_a_busy_pass_of_the_event_loop_is_not_silence(self, host) -> None:
        """Review round 5, P2-2. The stall bound counted WALL time: with the GUI thread
        busy for 0.7 s inside the wait — a handler of something else — and the repaint
        posted right after it, ``wait_ready(5)`` said False after 0.75 s and True when
        asked again. Silence is time the event loop was idle; a pass that overran its
        step is not counted, however long it took."""
        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        taken = _frames(host, (49, 240))
        _force(host)
        passes: list[float] = []

        def run_events(milliseconds: int) -> bool:
            passes.append(milliseconds)
            if len(passes) == 1:
                time.sleep(STALL_S + 0.2)  # another object's handler: a plan load, a repaint
            elif len(passes) == 2:
                _frames(host, (320, 240))  # the repaint that was queued behind it arrives
                _sign(host, "expose")
            return True

        host._run_events = run_events  # noqa: SLF001
        started = time.perf_counter()
        assert host.wait_ready(5.0) is True, "the host was busy, not silent"
        assert STALL_S + 0.2 <= time.perf_counter() - started < STALL_S + 1.0
        assert len(passes) == 2 and taken == [(49, 240)]
        assert host.longest_quiet_s < 0.1, "the busy pass is no quiet spell either"

    def test_idle_passes_add_up_to_silence_whatever_a_busy_one_took(
            self, host, monkeypatch: pytest.MonkeyPatch) -> None:
        """The other half: a busy pass does not START the stall bound again — it is simply
        not counted. Idle time before it and idle time after it add up to ``STALL_S``.
        (On a clock of its own: how long a pass "took" is what is under test, and a
        loaded machine must not decide it.)"""
        from types import SimpleNamespace

        from open_garden_planner.ui.view3d.quick3d import host as host_module
        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        now = [1000.0]
        monkeypatch.setattr(host_module, "time", SimpleNamespace(perf_counter=lambda: now[0]))
        _force(host, scene_graph=False, exposed=False)
        # an idle pass; a pass in which somebody's handler ran (binary fractions: the clock
        # must add them up without a rounding error deciding the count)
        idle, busy = 1 / 64, 0.25
        took: list[float] = []

        def run_events(_milliseconds: int) -> bool:
            took.append(busy if len(took) == 5 else idle)
            now[0] += took[-1]
            return True

        host._run_events = run_events  # noqa: SLF001
        assert host.wait_ready(30.0) is False
        assert took.count(busy) == 1 and took[5] == busy
        idle_passes = took.count(idle)
        assert idle_passes == round(STALL_S / idle) == 32, (
            f"{idle_passes} idle passes of {idle} s before it gave up: silence must be the "
            f"idle time alone — {STALL_S} s of it, neither less (the busy pass counted) nor "
            "more (the busy pass started the count again)")
        assert now[0] - 1000.0 == STALL_S + busy

    @pytest.mark.perf
    def test_it_comes_back_at_once_when_no_event_loop_can_run(self, host) -> None:
        """Review round 3, P2-1. Once the application is quitting ``QEventLoop.exec()``
        returns at once (``_run_events`` then says False): 158,574 looks at Qt in 3.0 s."""
        forced, looks = _facts(scene_graph=False, exposed=False), [0]

        def facts() -> Any:
            looks[0] += 1
            return forced

        host._facts = facts  # noqa: SLF001
        host._run_events = lambda _milliseconds: False  # noqa: SLF001
        started = time.perf_counter()
        assert host.wait_ready(5.0) is False and host.state.value == "starting"
        assert time.perf_counter() - started < 0.5
        assert looks[0] < 12, f"{looks[0]} looks at Qt: it went on asking"

    def test_a_loop_that_does_not_block_is_asked_a_bounded_number_of_times(self, host) -> None:
        """No busy loop anywhere: even if a pass came back at once for a reason nobody
        thought of, the number of passes is bounded by the timeout."""
        forced, looks = _facts(scene_graph=False, exposed=False), [0]

        def facts() -> Any:
            looks[0] += 1
            return forced

        host._facts = facts  # noqa: SLF001
        host._run_events = lambda _milliseconds: True  # noqa: SLF001 - "ran", in no time
        assert host.wait_ready(0.2) is False
        assert looks[0] < 60, f"{looks[0]} looks at Qt for a 0.2 s timeout"

    @pytest.mark.perf
    def test_a_pass_of_the_event_loop_says_whether_it_ran(self, tmp_path: Path) -> None:
        """The real thing, in a child with a running main loop (``quit()`` does nothing
        without one): before ``QCoreApplication.quit()`` a pass blocks and says True;
        after it every pass says False at once, and ``wait_ready()`` of a host that is
        still starting answers False after a handful of looks."""
        proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
            [sys.executable, "-c", _QUITTING], env=_child_env(tmp_path), capture_output=True,
            text=True, timeout=120, cwd=REPO)
        lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
        assert proc.returncode == 0 and lines, f"exit {proc.returncode}\n{proc.stdout}\n{proc.stderr[-2000:]}"
        out = json.loads(lines[-1][len("RESULT "):])
        assert out["ready"] is True and out["a_pass_while_running"] is True, out
        assert out["a_pass_while_running_s"] >= 0.004, "a pass blocks for its 5 ms"
        assert out["passes_while_quitting"] == [False, False, False], out
        assert out["three_passes_s"] < 0.25, out
        assert out["wait_ready"] is False and out["wait_ready_s"] < 0.5, out
        assert out["looks"] < 12, out

    def test_it_reports_instead_of_hanging(self, host) -> None:
        assert host.wait_ready(5.0) is False, "a host nobody showed is not on its way"
        host.show()
        assert host.wait_ready(5.0) is True and host.state.value == "live"
        host.hide()
        assert host.state.value == "hidden", "hidden at once, whatever Qt still calls exposed"
        assert host.wait_ready(5.0) is False

    @pytest.mark.perf
    @pytest.mark.parametrize("changes", [
        {"visible": False}, {"minimised": True}, {"size": (0, 240)}, {"size": (1, 240)},
        {"surface_created": False, "visible": False},
    ], ids=["hidden", "minimised", "collapsed", "one pixel", "new"])
    def test_it_does_not_wait_for_a_host_that_is_not_on_its_way(self, host,
                                                               changes: dict[str, Any]) -> None:
        _force(host, **changes)
        started = time.perf_counter()
        assert host.wait_ready(5.0) is False
        assert time.perf_counter() - started < 1.0

    @pytest.mark.perf
    def test_it_times_out_without_spinning(self, host) -> None:
        """A window that never starts, and a timeout shorter than the stall bound: False
        when the time is up — after a few dozen looks at Qt, not after the tens of
        thousands a busy loop takes."""
        forced, looks = _facts(scene_graph=False, exposed=False), [0]

        def facts() -> Any:
            looks[0] += 1
            return forced

        host._facts = facts  # noqa: SLF001
        started = time.perf_counter()
        assert host.wait_ready(0.3) is False and host.state.value == "starting"
        elapsed = time.perf_counter() - started
        assert 0.28 <= elapsed < 2.0
        assert looks[0] < 200, f"{looks[0]} looks at Qt in {elapsed:.2f} s: a busy loop"

    @pytest.mark.perf
    @pytest.mark.parametrize("changes", [
        {"scene_graph": False, "exposed": False}, {"exposed": False}, {"root_width": 0.0},
    ], ids=["never exposed", "shown again, never exposed", "the scene never catches up"])
    def test_a_starting_host_that_makes_no_progress_is_given_up_promptly(
            self, host, changes: dict[str, Any]) -> None:
        """Review round 4: "starting" used to mean "on its way", and ``wait_ready()``
        waited for it to its deadline — 5 s, 10 s. A pane SHOWN where no screen is never
        gets its expose; a session that paints nothing never does either. Whatever the
        cause: no sign of progress for ``STALL_S``, and the answer is False."""
        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        _force(host, **changes)
        started = time.perf_counter()
        assert host.wait_ready(30.0) is False and host.state.value == "starting"
        elapsed = time.perf_counter() - started
        assert STALL_S - 0.05 <= elapsed < STALL_S + 0.8, f"{elapsed:.2f} s of 30 s"

    @pytest.mark.perf
    def test_progress_keeps_a_starting_host_waited_for(self, host) -> None:
        """…and a host that IS on its way is not given up: every change of a fact, every
        event of the view, starts the stall bound again."""
        from PyQt6.QtCore import QTimer

        from open_garden_planner.ui.view3d.quick3d.lifecycle import STALL_S

        _force(host, scene_graph=False, exposed=False)
        steps = [lambda: _sign(host, "resize"), lambda: _force(host, scene_graph=True, exposed=False),
                 lambda: _sign(host, "expose"), lambda: _force(host)]
        for index, step in enumerate(steps):
            QTimer.singleShot(int((index + 1) * (STALL_S * 0.7) * 1000), step)
        started = time.perf_counter()
        assert host.wait_ready(10.0) is True
        elapsed = time.perf_counter() - started
        assert 4 * STALL_S * 0.7 - 0.05 <= elapsed < 4 * STALL_S * 0.7 + 1.0, elapsed
        assert host.longest_quiet_s >= STALL_S * 0.6, "the diagnostic saw the quiet spells"

    @pytest.mark.perf
    @pytest.mark.parametrize(("later", "expected"), [
        ({}, True),                              # the first expose arrived: live
        ({"visible": False}, False),             # hidden during the wait
        ({"minimised": True}, False),
        ({"size": (0, 240)}, False),             # the pane was collapsed during the wait
    ], ids=["becomes live", "hidden meanwhile", "minimised meanwhile", "collapsed meanwhile"])
    def test_it_looks_again_in_every_pass(self, host, later: dict[str, Any],
                                          expected: bool) -> None:
        """It looked at visibility once and then span to its timeout (3.0 of 3.0 s)."""
        from PyQt6.QtCore import QTimer

        _frames(host, (320, 240))
        _force(host, scene_graph=False, exposed=False)
        QTimer.singleShot(40, lambda: _force(host, **later))
        started = time.perf_counter()
        assert host.wait_ready(5.0) is expected
        assert time.perf_counter() - started < 0.45, "at the change, not at a bound"

    @pytest.mark.perf
    def test_it_comes_back_when_the_host_is_closed_or_destroyed_during_the_wait(
            self, qtbot) -> None:  # noqa: ARG002
        from PyQt6 import sip
        from PyQt6.QtCore import QTimer

        for kill in (lambda made: made.close(), lambda made: sip.delete(made._view)):  # noqa: SLF001
            made = _new_host()
            forced = _facts(scene_graph=False, exposed=False)
            real = made._facts  # noqa: SLF001
            made._facts = lambda forced=forced, real=real: forced if real() is not None else None  # noqa: SLF001
            QTimer.singleShot(40, lambda made=made, kill=kill: kill(made))
            started = time.perf_counter()
            assert made.wait_ready(5.0) is False
            assert time.perf_counter() - started < 0.45 and made.is_closed
            made.close()

    @pytest.mark.perf
    def test_it_gives_up_as_soon_as_qt_reports_no_graphics_device(self, host) -> None:
        from PyQt6.QtCore import QTimer
        from PyQt6.QtQuick import QQuickWindow

        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        _force(host, scene_graph=False, exposed=False)
        with pytest.raises(HostStateError, match=r"would kill the process\. Call wait_ready\(\) first"):
            host.grab("before Qt said anything")
        QTimer.singleShot(40, lambda: host._view.sceneGraphError.emit(  # noqa: SLF001
            QQuickWindow.SceneGraphError.ContextNotAvailable, "no device today"))
        started = time.perf_counter()
        assert host.wait_ready(5.0) is False
        assert time.perf_counter() - started < 0.45
        assert host.health().scene_graph_error == "no device today"
        # review round 3, P2-6: the refusal said "Call wait_ready() first" — which answers
        # False for this host, for ever. It names the failure and where to read it.
        assert host.state.value == "starting"
        for call in (lambda: host.grab("no device"), lambda: host.pick(1.0, 1.0),
                     lambda: host.project(0.0, 0.0, 0.0)):
            with pytest.raises(HostStateError, match=r"could not create the graphics device.*"
                               r"no device today.*health\(\)\.scene_graph_error") as caught:
                call()
            assert "Call wait_ready() first" not in str(caught.value)
        started = time.perf_counter()
        assert host.wait_ready(5.0) is False, "and it goes on answering False"
        assert time.perf_counter() - started < 0.2, "at once"


class TestABackendWithout3d:
    """Under the software scene graph Qt Quick 3D draws nothing. A frame without the
    garden must not pass for one — and here that backend is the one we run on."""

    def test_the_backend_is_named_from_qts_enum(self, host) -> None:
        from PyQt6.QtQuick import QSGRendererInterface

        from open_garden_planner.ui.view3d.quick3d.host import GRAPHICS_API_NAMES, RENDERING_APIS

        assert host.graphics_api() == "Software" and host.renders_3d() is False
        # the CI finding: a list of guessed strings said "OpenGLRhi"; PyQt says "OpenGL"
        members = list(QSGRendererInterface.GraphicsApi)
        assert set(GRAPHICS_API_NAMES) == set(members), "every API Qt knows has a name"
        assert len(set(GRAPHICS_API_NAMES.values())) == len(GRAPHICS_API_NAMES)
        for member, name in GRAPHICS_API_NAMES.items():
            assert member.name in (name, name + "Rhi"), (member, name)
        rhi = {name for member, name in GRAPHICS_API_NAMES.items()
               if QSGRendererInterface.isApiRhiBased(member)}
        assert rhi - {"Null"} == RENDERING_APIS

    def test_no_frame_no_pick_no_projection(self, host) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        SceneSync(Quick3DSink(host)).apply({"a": _record("a")})
        host.show()
        assert host.wait_ready(5.0)
        for call in (lambda: host.grab("software"), lambda: host.pick(5.0, 5.0),
                     lambda: host.project(0.0, 0.0, 0.0)):
            with pytest.raises(EngineError, match="Software backend.*draws nothing"):
                call()
        assert host.grabs == 0

    def test_render_records_refuses_and_leaves_the_process_as_it_found_it(
            self, qtbot, capsys: pytest.CaptureFixture[str]) -> None:  # noqa: ARG002
        """Review P2-4: no output unless a log is passed; the message handler and Qt's
        logging rules are put back — also when the render fails, as it must here."""
        from PyQt6.QtCore import QLoggingCategory, qInstallMessageHandler

        from open_garden_planner.ui.view3d.quick3d.offscreen import RenderError, render_records

        def mine(*_args: object) -> None:
            return None

        before = qInstallMessageHandler(mine)
        try:
            with pytest.raises(RenderError, match="Software backend.*no 3D frame"):
                render_records({"a": _record("a")}, shot=TopDownShot((0.0, 0.0), 0.5),
                               sun=SunState(45.0, 225.0), size=(160, 120), graphics_info=True,
                               qml_dir=_qml_dir())
            after = qInstallMessageHandler(before)
        except BaseException:
            qInstallMessageHandler(before)
            raise
        assert after is mine, "the caller's message handler was not put back"
        assert not QLoggingCategory("qt.rhi.general").isDebugEnabled(), "the debug rule stayed on"
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""

    def test_render_records_refuses_beside_a_shown_quick_window(
            self, host, monkeypatch: pytest.MonkeyPatch) -> None:
        """Review round 2, P1-C. ``render_records`` records Qt's messages with a
        process-wide Python handler; a SHOWN Qt Quick window renders on a thread of its
        own, and the two deadlock the process. It refuses — before it installs
        anything.

        "Before it installs anything" is asked of the recorder itself: its ``install``
        is counted, together with how many windows were shown when it ran. (This test
        used to install a handler of its own beside the shown host and call ``hide()``
        — the forbidden arrangement itself; review round 3, P2-3.)"""
        from open_garden_planner.ui.view3d.quick3d import qt_messages
        from open_garden_planner.ui.view3d.quick3d.host import shown_quick_windows
        from open_garden_planner.ui.view3d.quick3d.offscreen import RenderError, render_records

        installs: list[int] = []
        real_install = qt_messages.install

        def install(messages: Any) -> Any:
            installs.append(shown_quick_windows())
            return real_install(messages)

        def render() -> None:
            render_records({"a": _record("a")}, shot=TopDownShot((0.0, 0.0), 0.5), qml_dir=_qml_dir())

        monkeypatch.setattr(qt_messages, "install", install)
        assert shown_quick_windows() == 0
        host.show()
        assert host.wait_ready(5.0) and shown_quick_windows() == 1
        with pytest.raises(RenderError, match=r"1 Qt Quick window\(s\) are shown.*deadlocks"):
            render()
        assert installs == [], "the recorder was installed beside a shown window"
        host.hide()
        assert shown_quick_windows() == 0
        with pytest.raises(RenderError, match="Software backend"):  # past the refusal now
            render()
        assert installs == [0], "installed once, with no window shown"

    def test_render_records_reports_to_a_log_that_is_passed(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.offscreen import RenderError, render_records

        phases: list[str] = []
        with pytest.raises(RenderError):
            render_records({}, shot=TopDownShot((0.0, 0.0), 0.5), qml_dir=_qml_dir(),
                           log=lambda phase, **_fields: phases.append(phase))
        assert phases[0] == "qml_loaded" and phases[-1] == "render_failed"

    def test_a_broken_scene_file_fails_the_render(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import EngineError
        from open_garden_planner.ui.view3d.quick3d.offscreen import render_records

        broken = _broken_copy(tmp_path, "import QtQuick3D.Helpers\n",
                              "import QtQuick3D.Helpers\nimport NoSuchModule\n")
        with pytest.raises(EngineError, match=r"Garden\.qml did not load"):
            render_records({}, shot=TopDownShot((0.0, 0.0), 0.5), qml_dir=broken)

    def test_an_empty_mesh_part_has_no_model(self, host) -> None:
        sink = Quick3DSink(host)
        sink.begin()
        sink.add("a", (MeshPart(Mesh.empty(), "vc"), MeshPart(prism_mesh([SQUARE], 5.0), "roof")),
                 Transform(), Material("SHED"))
        sink.commit()
        (part,) = host.engine_parts()
        assert (part.part_index, part.kind) == (1, "roof")


def _closed_host_answers(host: Any, part: Any) -> dict[str, Any]:
    lifecycle._register_calls()  # noqa: SLF001 - the lifecycle matrix's own table
    return {name: lifecycle._attempt(lambda call=call: call(host, part))  # noqa: SLF001
            for name, call in lifecycle.HOST_CALLS.items()}


def _assert_closed_contract(host: Any, part: Any) -> None:
    assert host.state.value == "closed" and host.is_closed and not host.is_visible()
    for name, answer in _closed_host_answers(host, part).items():
        if name in RELEASES:
            assert answer is None, f"{name}() on a closed host must be a silent no-op: {answer!r}"
        else:
            assert isinstance(answer, str) and answer.startswith("HostStateError: "), (name, answer)
            assert "closed" in answer, (name, answer)


class TestClosedAndDestroyedHosts:
    """Review P1-3: ONE owner of Model lifetime. ``destroy_part`` / ``clear`` / ``close``
    on a closed or destroyed host do nothing; every other call raises ``HostStateError``
    — never sip's ``RuntimeError`` or a ``TypeError`` from a dead C++ object."""

    def _embedded(self, qtbot) -> tuple[Any, Quick3DSink, SceneSync, Any, Any]:  # noqa: ARG002
        from PyQt6.QtWidgets import QWidget

        from open_garden_planner.core.scene3d import engine_pose

        made = _new_host()
        sink = Quick3DSink(made)
        sync = SceneSync(sink)
        sync.apply({"a": _record("a"), "b": _record("b", 200.0)})
        sync.set_sun(SunState(40.0, 180.0))
        sync.set_ground(GroundSpec(500.0, 500.0))
        part = made.create_part(PartSpec("p", 0, "vc", engine_buffers(prism_mesh([SQUARE], 10.0)),
                                         True), engine_pose(Transform()), RED)
        parent = QWidget()
        made.container(parent)
        return made, sink, sync, parent, part

    def test_the_call_table_covers_every_public_call(self) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        lifecycle._register_calls()  # noqa: SLF001
        public = {name for name in dir(Quick3DHost)
                  if not name.startswith("_") and callable(getattr(Quick3DHost, name))}
        assert set(lifecycle.HOST_CALLS) == public - {"is_visible", "health"}

    def test_close_then_anything(self, qtbot) -> None:
        made, _sink, _sync, parent, part = self._embedded(qtbot)
        assert len(made.engine_parts()) >= 2 and not made.is_closed
        made.close()
        _assert_closed_contract(made, part)
        assert part.model is None and part.geometry is None, "close() released every part"
        parent.deleteLater()

    def test_parent_destroyed_then_anything(self, qtbot) -> None:
        """A window container belongs to its parent widget: when that widget is destroyed
        (closing the main window) Qt destroys the view with it. The host learns it by
        asking Qt — nobody told it."""
        from PyQt6 import sip

        made, _sink, _sync, parent, part = self._embedded(qtbot)
        sip.delete(parent)
        _assert_closed_contract(made, part)
        made.close()
        _assert_closed_contract(made, part)

    @pytest.mark.parametrize("order", ["parent destroyed, clear", "parent destroyed, close, clear",
                                       "close, clear"])
    def test_the_sink_clears_cleanly_in_every_order(self, qtbot, order: str) -> None:
        """The three orders of the review, each of which raised: ``TypeError``,
        ``ValueError``, and ``EngineError`` with the sink's books left dirty."""
        from PyQt6 import sip

        made, sink, sync, parent, _part = self._embedded(qtbot)
        if order.startswith("parent destroyed"):
            sip.delete(parent)
        if "close" in order:
            made.close()
        sink.clear()
        assert sink.item_ids() == () and sink.sun is None and sink.ground is None
        assert not sink.in_transaction
        sink.clear()   # idempotent
        made.close()   # and close() after the teardown is quiet, in every order
        sink.clear()
        sync.reset()
        assert made.is_closed

    def test_a_fresh_host_takes_over_after_the_old_one_died(self, qtbot) -> None:
        """The recovery path: the SAME sink and sync, cleared and reset on a dead host,
        attached to a fresh one and applied again."""
        from PyQt6 import sip

        made, sink, sync, parent, _part = self._embedded(qtbot)
        records = {"a": _record("a"), "b": _record("b", 200.0)}
        sip.delete(parent)
        sink.clear()
        sync.reset()
        fresh = _new_host()
        try:
            sink.attach(fresh)
            sync.apply(records)
            sync.set_sun(SunState(40.0, 180.0))
            assert sorted({p.item_id for p in fresh.engine_parts()}) == ["a", "b"]
            assert fresh.scene_property("sunUp") is True
        finally:
            fresh.close()

    def test_an_engine_call_that_fails_mid_transaction_is_recovered_by_reset(self, host) -> None:
        """The L1.1 recipe for a sink on the REAL host (no pixels here; the render tier
        looks at them): the engine refuses the second Model of a transaction, the sync
        is poisoned, ``reset()`` empties the engine through ``Quick3DSink.clear()`` —
        also the Model the failed call left behind — and after ``apply`` the engine
        holds what ``sync.expected_state()`` says."""
        from open_garden_planner.core.scene3d import SyncStateError, engine_pose
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        sink = Quick3DSink(host)
        sync = SceneSync(sink, validate=True)
        sun, ground = SunState(40.0, 180.0), GroundSpec(800.0, 600.0)
        sync.apply({"a": _record("a"), "b": _record("b", 300.0, colour=BLUE)}, sun=sun, ground=ground)
        after = {"a": _record("a", 50.0, 20.0, 30.0), "b": _record("b", 300.0, colour=BLUE),
                 "c": _record("c", -300.0), "d": _record("d", 0.0, 400.0)}

        real_create, calls = host.create_part, [0]

        def refusing(spec: Any, pose: Any, tint: Any) -> object:
            calls[0] += 1
            if calls[0] == 2:
                raise EngineError("injected: the engine refused this Model")
            return real_create(spec, pose, tint)

        host.create_part = refusing
        with pytest.raises(EngineError, match="injected"):
            sync.apply(after)
        del host.create_part
        assert sync.poisoned and sink.in_transaction
        assert sorted({p.item_id for p in host.engine_parts()}) == ["a", "b", "c"]  # half applied
        with pytest.raises(SyncStateError):
            sync.apply(after)

        sync.reset()
        assert not sync.poisoned and not sink.in_transaction
        assert host.engine_parts() == [] and sink.item_ids() == ()
        assert host.scene_property("sunUp") is False and host.scene_property("groundVisible") is False

        sync.apply(after, sun=sun, ground=ground)
        expected = sync.expected_state()
        assert sink.state() == expected
        want = sorted((item_id, index, engine_pose(held.transform).position,
                       held.material.tint_rgba[:3])
                      for item_id, held in expected.items.items()
                      for index, part in enumerate(held.parts) if part.mesh.vertex_count)
        have = sorted((p.item_id, p.part_index, p.position, p.tint_rgb) for p in host.engine_parts())
        assert have == want and len(have) == 8  # four items, sides + cap each
        assert host.scene_property("sunUp") is True and host.scene_property("groundVisible") is True

    def test_close_destroys_every_model_and_is_idempotent(self, qtbot) -> None:  # noqa: ARG002
        made = _new_host()
        sink = Quick3DSink(made)
        SceneSync(sink).apply({"a": _record("a"), "b": _record("b", 200.0)})
        assert len(made.engine_parts()) == 4 and not made.is_closed
        made.close()
        assert made.is_closed
        made.close()  # a second close is a no-op, not an error on a deleted view


def _failing_destroy_copy(tmp_path: Path) -> Path:
    """The scene with a switch: ``failDestroy`` makes ``destroyPart()`` throw — an engine
    that REFUSES to destroy a Model, on demand."""
    return _broken_copy(
        tmp_path, "    function destroyPart(part) {\n",
        "    property bool failDestroy: false\n"
        "    function destroyPart(part) {\n"
        "        if (failDestroy)\n"
        "            throw new Error(\"injected: the engine refuses to destroy this Model\")\n")


class TestTeardownIsExceptionSafe:
    """Review round 2, P2-3. With a ``destroyPart`` that fails, every ``reset()`` forgot
    one more part and the FOURTH "succeeded" with three Models left in the engine and
    the host's books empty. Now a Model leaves the books only when the engine confirms
    it; teardown finishes whatever fails; and it can be tried again."""

    @pytest.fixture()
    def refusing(self, qtbot, tmp_path: Path) -> Iterator[Any]:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import Quick3DHost

        made = Quick3DHost((64, 48), qml_dir=_failing_destroy_copy(tmp_path))
        yield made
        if not made.is_closed:
            assert made._root.setProperty("failDestroy", False)  # noqa: SLF001
        made.close()

    @staticmethod
    def _refuse(made: Any, on: bool) -> None:
        assert made._root.setProperty("failDestroy", on)  # noqa: SLF001

    def test_reset_never_succeeds_while_the_engine_keeps_its_models(self, refusing) -> None:
        from open_garden_planner.core.scene3d import SyncStateError
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        sink = Quick3DSink(refusing)
        sync = SceneSync(sink)
        records = {name: _record(name, 200.0 * k) for k, name in enumerate("abc")}
        sync.apply(records, sun=SunState(40.0, 180.0), ground=GroundSpec(500.0, 500.0))
        self._refuse(refusing, True)
        for attempt in range(1, 6):  # the fourth used to "succeed"
            with pytest.raises(EngineError, match=r"clear\(\): \d+ of \d+ steps failed.*still holds \d+ Model"):
                sync.reset()
            assert sync.poisoned, f"reset() {attempt} must not report success"
            assert refusing.part_count() == len(refusing.engine_parts()) > 0, (
                f"after reset() {attempt}: books and engine must agree")
        # the teardown FINISHED what it could: the sun is off and the ground is gone
        assert refusing.scene_property("sunUp") is False
        assert refusing.scene_property("groundVisible") is False
        assert sink.item_ids() == () and not sink.in_transaction
        with pytest.raises(SyncStateError):
            sync.apply(records)
        self._refuse(refusing, False)  # the engine recovers: the next reset() goes through
        sync.reset()
        assert not sync.poisoned and refusing.part_count() == 0 == len(refusing.engine_parts())
        sync.apply(records)
        assert sink.state() == sync.expected_state()
        assert sorted({p.item_id for p in refusing.engine_parts()}) == ["a", "b", "c"]

    def test_a_sink_whose_clear_failed_builds_nothing_on_the_leftovers(self, refusing) -> None:
        """Its books are empty and the engine is not: ``begin()`` refuses until a
        ``clear()`` went through."""
        from open_garden_planner.core.scene3d import SinkProtocolError
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        sink = Quick3DSink(refusing)
        SceneSync(sink).apply({"a": _record("a")})
        self._refuse(refusing, True)
        with pytest.raises(EngineError):
            sink.clear()
        assert sink.item_ids() == () and refusing.part_count() > 0
        with pytest.raises(SinkProtocolError, match=r"the last clear\(\) failed"):
            sink.begin()
        with pytest.raises(SinkProtocolError, match=r"already holds \d+ Models?"):
            Quick3DSink(refusing)  # and nobody else gets the scene either
        self._refuse(refusing, False)
        sink.clear()
        sink.begin()
        sink.commit()
        assert refusing.part_count() == 0

    def test_a_model_the_engine_did_not_destroy_stays_a_live_part(self, refusing) -> None:
        from open_garden_planner.core.scene3d import engine_pose
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        pose = engine_pose(Transform(east_cm=70.0))
        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        handle = refusing.create_part(PartSpec("a", 0, "vc", buffers, True), pose, RED)
        self._refuse(refusing, True)
        with pytest.raises(EngineError, match=r"destroyPart\(\) did not retire the Model"):
            refusing.destroy_part(handle)
        assert handle.model is not None and handle.geometry is not None, "the buffers it draws stay"
        refusing.pose_part(handle, pose)  # still a live part of this host
        assert refusing.part_count() == 1 == len(refusing.engine_parts())
        assert any("injected" in line for line in refusing.health().qml_warnings)
        self._refuse(refusing, False)
        refusing.destroy_part(handle)
        assert refusing.part_count() == 0 and handle.model is None

    def test_a_scene_without_the_destroy_function_is_an_error_not_a_forgotten_model(
            self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        from open_garden_planner.core.scene3d import engine_pose
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        made = Quick3DHost((64, 48), qml_dir=_broken_copy(
            tmp_path, "    function destroyPart(part) {", "    function destroyPartRenamed(part) {"))
        try:
            buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
            handle = made.create_part(PartSpec("a", 0, "vc", buffers, True),
                                      engine_pose(Transform()), RED)
            with pytest.raises(EngineError, match=r"no function destroyPart\(\)"):
                made.destroy_part(handle)
            with pytest.raises(EngineError, match=r"clear\(\): 1 of 4 steps failed"):
                made.clear()
            assert made.part_count() == 1 == len(made.engine_parts())
        finally:
            made.close()
        assert made.is_closed, "close() goes through: the Model dies with the view"

    def test_close_goes_through_when_a_model_cannot_be_destroyed(
            self, refusing, caplog: pytest.LogCaptureFixture) -> None:
        from open_garden_planner.ui.view3d.quick3d import host as host_module

        SceneSync(Quick3DSink(refusing)).apply({"a": _record("a"), "b": _record("b", 200.0)})
        self._refuse(refusing, True)
        with caplog.at_level(logging.WARNING, logger=host_module.__name__):
            refusing.close()
        assert refusing.is_closed and refusing.state.value == "closed"
        assert sum("could not be destroyed" in r.getMessage() for r in caplog.records) >= 2
        refusing.close()  # and again: a no-op

    def test_a_close_that_raised_can_be_called_again(self, qtbot) -> None:  # noqa: ARG002
        """``close()`` used to set its flag first: a failure half way left a host that
        called itself closed with its window still there. The flag is set last."""
        made = _new_host()
        SceneSync(Quick3DSink(made)).apply({"a": _record("a")})
        view = made._view  # noqa: SLF001

        def refuse() -> None:
            raise RuntimeError("injected: hide() failed")

        view.hide = refuse
        with pytest.raises(RuntimeError, match="injected"):
            made.close()
        assert made.is_closed is False and made.state.value != "closed"
        assert made.part_count() == 0, "the Models went before the window was touched"
        del view.hide
        made.close()
        assert made.is_closed


class TestOneSinkPerScene:
    """Review round 2, P2-4: ``attach()`` accepted a host that already held Models — two
    owners of one scene, and a teardown that destroys the other's Models. Refused."""

    def test_a_sink_refuses_a_scene_that_already_holds_models(self, host, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.core.scene3d import SinkProtocolError

        first = Quick3DSink(host)
        SceneSync(first).apply({"a": _record("a")})
        with pytest.raises(SinkProtocolError, match=r"Quick3DSink\(\): .* already holds \d+ Model"):
            Quick3DSink(host)
        other = _new_host()
        try:
            second = Quick3DSink(other)
            with pytest.raises(SinkProtocolError, match=r"attach\(\): .* already holds \d+ Model"):
                second.attach(host)
            assert second.scene is other, "a refused attach changes nothing"
            first.clear()
            second.attach(host)  # empty now: free to take
            assert second.scene is host
        finally:
            other.close()

    def test_a_closed_host_cannot_be_given_to_a_sink(self, qtbot) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import HostStateError

        made = _new_host()
        made.close()
        with pytest.raises(HostStateError, match="closed"):
            Quick3DSink(made)


class TestSceneFunctionsThatFail:
    """A QML function that THROWS returns nothing to Python — silently; the QML engine
    only warns. "No hit", "(0, 0)" and "no parts" must never mean "could not look"."""

    @pytest.mark.parametrize(("function", "call"), [
        ("pickAt(x, y)", lambda h: h.pick(5.0, 5.0)),
        ("projectToView(x, y, z)", lambda h: h.project(0.0, 0.0, 0.0)),
        ("listParts()", lambda h: h.engine_parts()),
    ], ids=["pick", "project", "engine_parts"])
    def test_a_throwing_function_is_an_engine_error(self, qtbot, tmp_path: Path, function: str,  # noqa: ARG002
                                                    call: Any) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        name = function.split("(")[0]
        made = Quick3DHost((64, 48), qml_dir=_broken_copy(
            tmp_path, f"    function {function} {{\n",
            f"    function {function} {{\n        throw new Error(\"injected: {name} broke\")\n"))
        try:
            _force(made, size=(64, 48), root_width=64.0, root_height=48.0)
            with pytest.raises(EngineError, match=rf"{name}\(\) returned nothing — it failed"):
                call(made)
            assert any(f"injected: {name} broke" in line for line in made.health().qml_warnings)
        finally:
            made.close()

    def test_a_missing_function_is_an_engine_error(self, qtbot, tmp_path: Path) -> None:  # noqa: ARG002
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        made = Quick3DHost((64, 48), qml_dir=_broken_copy(
            tmp_path, "    function listParts() {", "    function listPartsRenamed() {"))
        try:
            with pytest.raises(EngineError, match=r"no function listParts\(\)"):
                made.engine_parts()
        finally:
            made.close()


class TestHealth:
    """Review round 2, P1-C: what a SHOWN host learns about itself — on the GUI thread,
    from Qt's own signals. There is no Qt message recorder for a shown host: a Python
    handler beside Qt's render thread deadlocks the process (the render tier's control:
    ``test_a_python_message_handler_beside_a_shown_window_deadlocks``)."""

    def test_a_healthy_host(self, host, qtbot) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import HostHealth

        assert host.health() == HostHealth(0, (), 0, None) and host.health().ok
        host.show()
        assert host.wait_ready(5.0)
        qtbot.waitUntil(lambda: host.health().frames_presented >= 1, timeout=5000)
        assert host.health().ok and host.slot_calls_off_the_gui_thread == 0
        host.close()
        assert host.health().frames_presented >= 1, "health() answers on a closed host"

    def test_no_python_message_handler_is_installed_while_these_tests_show_hosts(self, host) -> None:
        """Not pytest-qt's either (``pytestmark`` above): asked of Qt, which hands back the
        handler it had when another one is installed."""
        from PyQt6.QtCore import qInstallMessageHandler

        before = qInstallMessageHandler(None)
        qInstallMessageHandler(before)
        assert before is None, f"a Python Qt message handler is installed: {before!r}"
        host.show()
        assert host.wait_ready(5.0)
        during = qInstallMessageHandler(None)
        qInstallMessageHandler(during)
        assert during is None, "building and showing a host must not install one"

    def test_the_host_installs_no_qt_message_handler_and_offers_no_watch(self, host) -> None:
        """Structural: the removed API stays removed, in the host and in its module."""
        from open_garden_planner.ui.view3d.quick3d import host as host_module
        from open_garden_planner.ui.view3d.quick3d import qt_messages

        source = Path(host_module.__file__).read_text(encoding="utf-8")
        assert "qInstallMessageHandler" not in source and "import qt_messages" not in source
        assert not hasattr(host, "watch_messages") and not hasattr(host, "engine_errors")
        assert not hasattr(qt_messages, "logging_sink")

    def test_qt_sees_a_slot_on_scene_graph_error(self, host) -> None:
        """With NOTHING connected Qt answers a failed graphics initialisation with a modal
        error box and then aborts the process (the render tier's control). Qt decides by
        asking whether the signal is connected — this asks the same question."""
        view = host._view  # noqa: SLF001
        assert view.receivers(view.sceneGraphError) >= 1
        assert view.receivers(view.frameSwapped) >= 1

    def test_a_graphics_device_that_cannot_be_created_is_reported_and_logged(
            self, host, qtbot, caplog: pytest.LogCaptureFixture) -> None:
        from PyQt6.QtQuick import QQuickWindow

        from open_garden_planner.ui.view3d.quick3d import host as host_module

        with caplog.at_level(logging.ERROR, logger=host_module.__name__):
            host._view.sceneGraphError.emit(  # noqa: SLF001
                QQuickWindow.SceneGraphError.ContextNotAvailable,
                "Failed to initialize graphics backend for D3D11.")
            assert host.health().scene_graph_error is None, "queued: delivered by the event loop"
            qtbot.waitUntil(lambda: host.health().scene_graph_error is not None, timeout=5000)
        report = host.health()
        assert report.scene_graph_error == "Failed to initialize graphics backend for D3D11."
        assert report.ok is False
        assert [(r.levelno, r.name) for r in caplog.records] == [(logging.ERROR, host_module.__name__)]
        assert "graphics device could not be created" in caplog.records[0].getMessage()
        assert host_module.__name__.startswith("open_garden_planner."), "a child of the app's logger"

    def test_a_qml_warning_is_reported_and_logged(self, qtbot, tmp_path: Path,  # noqa: ARG002
                                                  caplog: pytest.LogCaptureFixture) -> None:
        """A binding that fails at run time raises nothing anywhere; the QML engine's
        ``warnings`` signal carries it — file and line included."""
        from open_garden_planner.ui.view3d.quick3d import host as host_module

        marker = "    property real windTime: 0\n"
        broken = _broken_copy(tmp_path, marker, marker + "    property real probe: nothingHere.value\n")
        with caplog.at_level(logging.WARNING, logger=host_module.__name__):
            made = host_module.Quick3DHost((64, 48), qml_dir=broken)
        try:
            report = made.health()
            assert report.ok is False and report.qml_warning_count == len(report.qml_warnings) >= 1
            assert re.search(r"Garden\.qml:\d+.*nothingHere", report.qml_warnings[0])
            assert any(r.levelno == logging.WARNING and "nothingHere" in r.getMessage()
                       for r in caplog.records)
        finally:
            made.close()

    def test_a_flood_of_qml_warnings_is_counted_not_kept(
            self, host, caplog: pytest.LogCaptureFixture) -> None:
        """The first 50 are kept for ``health()`` and logged; the rest are only counted —
        and the log says so, once (review round 3, P2-7: the comment claimed they were
        logged, the code logged 50 and went silent)."""
        from PyQt6.QtQml import QQmlError

        from open_garden_planner.ui.view3d.quick3d import host as host_module

        def error(k: int) -> QQmlError:
            made = QQmlError()
            made.setDescription(f"injected warning {k}")
            return made

        keep = host_module._KEEP_WARNINGS  # noqa: SLF001
        engine = host._view.engine()  # noqa: SLF001
        with caplog.at_level(logging.WARNING, logger=host_module.__name__):
            engine.warnings.emit([error(k) for k in range(keep + 25)])
            engine.warnings.emit([error(1000)])  # and one more, later
        report = host.health()
        assert report.qml_warning_count == keep + 26
        assert len(report.qml_warnings) == keep
        assert "injected warning 0" in report.qml_warnings[0]
        logged = [record.getMessage() for record in caplog.records]
        each = [line for line in logged if "3D view: QML warning: " in line]
        assert len(each) == keep and "injected warning 0" in each[0]
        assert f"injected warning {keep - 1}" in each[-1], "the first 50, in order"
        said = [line for line in logged if "only counted" in line]
        assert len(said) == 1 and len(logged) == keep + 1, logged[-3:]
        assert f"more than {keep} QML warnings" in said[0]
        assert "health().qml_warning_count" in said[0]


def test_no_test_here_installs_a_python_handler_beside_a_shown_host() -> None:
    """The header's claim, checked (review round 3, P2-3). Two tests of this file call
    ``qInstallMessageHandler``: one only ASKS Qt which handler is installed (it passes
    ``None`` and puts the answer back), the other installs a Python handler — and
    neither takes a host nor shows one in the second case."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    callers: dict[str, ast.FunctionDef] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
               and node.func.id == "qInstallMessageHandler" for node in ast.walk(function)):
            callers[function.name] = function
    asks = "test_no_python_message_handler_is_installed_while_these_tests_show_hosts"
    installs = "test_render_records_refuses_and_leaves_the_process_as_it_found_it"
    assert set(callers) == {asks, installs}
    passed = [ast.unparse(node.args[0]) for node in ast.walk(callers[asks])
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id == "qInstallMessageHandler"]
    assert passed == ["None", "before", "None", "during"], "it only asks, and puts back"
    lonely = callers[installs]
    assert "host" not in {argument.arg for argument in lonely.args.args}
    assert not any(isinstance(node, ast.Attribute) and node.attr in ("show", "container")
                   for node in ast.walk(lonely))


class TestGeometry:
    def test_buffers_are_handed_to_qt_unchanged(self, qtbot) -> None:  # noqa: ARG002
        from PyQt6.QtQuick3D import QQuick3DGeometry

        from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry

        buffers = engine_buffers(prism_mesh([SQUARE], 100.0))
        before = BufferGeometry.uploads
        geometry = BufferGeometry(buffers)
        assert BufferGeometry.uploads == before + 1 and geometry.vertex_count == buffers.vertex_count
        assert geometry.stride() == 48
        assert bytes(geometry.vertexData()) == buffers.vertex_data
        assert bytes(geometry.indexData()) == buffers.index_data
        assert geometry.primitiveType() == QQuick3DGeometry.PrimitiveType.Triangles
        assert geometry.attributeCount() == 5
        low, high = geometry.boundsMin(), geometry.boundsMax()
        assert (low.x(), low.y(), low.z()) == buffers.bounds_min
        assert (high.x(), high.y(), high.z()) == buffers.bounds_max
        semantic = QQuick3DGeometry.Attribute.Semantic
        layout = {geometry.attribute(i).semantic: geometry.attribute(i).offset for i in range(5)}
        assert layout == {semantic.PositionSemantic: 0, semantic.NormalSemantic: 12,
                          semantic.ColorSemantic: 24, semantic.TexCoordSemantic: 40,
                          semantic.IndexSemantic: 0}

    def test_there_is_no_way_to_refill_a_geometry(self) -> None:
        """One geometry per Model lifetime, structurally: the class offers no method that
        uploads again (``ogp-3d-renderer`` §2 — a reused geometry rendered nothing)."""
        from open_garden_planner.ui.view3d.quick3d.geometry import BufferGeometry

        own = {name for name, value in vars(BufferGeometry).items() if callable(value)}
        assert own == {"__init__"}


# ── the positive control for the canary (review P1-2) ────────────────────────

_CONTROL = "test_a_broken_scene_file_fails_the_tier_instead_of_skipping_it"


def test_a_broken_scene_file_fails_the_tier_instead_of_skipping_it(tmp_path: Path) -> None:
    """THIS file, run again in a child pytest with every host pointed at a ``Garden.qml``
    that does not load. With the old canary — which loaded the product's scene itself —
    that run reported ``32 skipped`` and exit code 0: a broken engine package, green.
    Now it must FAIL, and skip nothing."""
    broken = _broken_copy(tmp_path, "import QtQuick3D.Helpers\n",
                          "import QtQuick3D.Helpers\nimport NoSuchModule\n")
    env = _child_env(tmp_path)
    env[QML_OVERRIDE] = str(broken)
    env.pop("CI", None)  # the canary's CI rule is not what is under test here
    this = Path(__file__).resolve()
    proc = subprocess.run(  # noqa: S603 - fixed argv, our own code
        [sys.executable, "-m", "pytest", str(this), "-q", "-p", "no:cacheprovider",
         "--deselect", f"{this.relative_to(REPO).as_posix()}::{_CONTROL}"],
        env=env, capture_output=True, text=True, timeout=170, cwd=REPO)
    summary = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    assert proc.returncode == 1, f"exit {proc.returncode}\n{proc.stdout[-3000:]}\n{proc.stderr[-1500:]}"
    broken_tests = sum(int(n) for n, _ in re.findall(r"(\d+) (failed|errors?)\b", summary))
    assert broken_tests >= 30, summary
    assert "skipped" not in summary, f"a broken scene file must not be skipped away: {summary}"
    assert "did not load" in proc.stdout, "and the failure names the cause"


class TestFillPictures:
    """The items' own fill pictures (#628): the host's side of their lifetime."""

    def test_a_failed_clear_keeps_the_picture_of_a_model_it_could_not_destroy(
            self, qtbot) -> None:  # noqa: ARG002
        """Pictures are forgotten only after EVERY step of clear() succeeded.

        A Model the engine could not destroy is still on screen, showing its picture;
        freeing that texture under it renders white (PF-L3D-17). The next clear()
        finishes and lets the picture go.
        """
        from open_garden_planner.core.scene3d import Material, MeshPart, Transform, prism_mesh
        from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
        from open_garden_planner.ui.view3d.quick3d.host import EngineError

        made = _new_host()
        sink = Quick3DSink(made)
        part = MeshPart(prism_mesh([SQUARE], 40.0), "vc", fill_texture=True)
        try:
            sink.begin()
            sink.add("lawn", (part,), Transform(),
                     Material("LAWN", fill_rgba=(90, 160, 60, 255), pattern="GRASS"))
            sink.commit()
            assert len(made._fill_pictures) == 1  # noqa: SLF001 - the books under test
            original = made._destroy  # noqa: SLF001

            def failing(_part: Any) -> None:
                raise EngineError("the engine refused to destroy it")

            made._destroy = failing  # type: ignore[method-assign]  # noqa: SLF001
            with pytest.raises(EngineError):
                made.clear()
            assert made._fill_pictures, "a surviving Model must keep its picture"  # noqa: SLF001
            made._destroy = original  # type: ignore[method-assign]  # noqa: SLF001
            made.clear()
            assert made._fill_pictures == {} and made.engine_parts() == []  # noqa: SLF001
        finally:
            sink.clear()
            made.close()
