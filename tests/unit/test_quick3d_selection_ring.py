"""The selection ring at the engine boundary, without an engine (Phase 17 L1.8).

``Quick3DSink.set_selection`` maps the ring mesh into the engine frame and hands the
bytes to ``EngineScene.set_selection_ring`` — here a list-backed double, so every
line runs in the GPU-less tier. Plus what can be read from the scene file and the
ring's shader as text: the numbers Python and QML must agree on, and the rules the
ring's Model must obey (never pickable, never a part).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    NORMAL_OFFSET,
    UV_OFFSET,
    VERTEX_STRIDE,
    Material,
    Params,
    Record,
    SceneSync,
    SinkProtocolError,
    Transform,
    srgb8_to_linear,
    walk,
)
from open_garden_planner.core.scene3d.selection import (
    EMPTY_SELECTION,
    RING_LIFT_CM,
    RING_WIDTH_PX,
    SELECTION_RGB,
    SELECTION_RGBA,
    selection_of,
)
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from tests.unit.test_quick3d_adapter import EngineGone, FakeScene
from tests.unit.test_quick3d_qml import QML_DIR, SCENE, strip_comments

SRC = Path(__file__).resolve().parents[2] / "src" / "open_garden_planner"
SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))


def item(item_id: str, east: float = 0.0, north: float = 0.0, *, rotation: float = 0.0,
         base: float = 0.0) -> Record:
    return Record(item_id=item_id, kind="SHED", shape="rectangle", footprints=(SQUARE,),
                  transform=Transform(east, north, rotation, base), material=Material("SHED"),
                  height_cm=80.0, params=Params({"seed": item_id}))


@pytest.fixture()
def rig() -> tuple[Quick3DSink, FakeScene, SceneSync, dict[str, Record]]:
    scene = FakeScene()
    sink = Quick3DSink(scene)
    sync = SceneSync(sink)
    records = {"a": item("a", 100.0, 200.0, base=38.0), "b": item("b", 500.0, 0.0)}
    sync.apply(records)
    scene.calls.clear()
    return sink, scene, sync, records


def vertices(buffers) -> np.ndarray:
    return np.frombuffer(buffers.vertex_data, "<f4").reshape(-1, VERTEX_STRIDE // 4)


def test_a_selection_is_mapped_to_the_engine_frame_once_and_handed_over(rig) -> None:
    sink, scene, sync, records = rig
    uploads = sink.geometry_uploads
    assert sync.set_selection(["a"]) is True
    selection = selection_of(records, ["a"])
    assert scene.calls == [("ring", selection.ring.vertex_count), ("frame",)]
    rows = vertices(scene.ring)
    scene_positions = selection.ring.positions
    # scene (E, N, up) -> engine (x = E, y = up, z = -N): the ONE mapping, for the ring too
    assert np.allclose(rows[:, 0], scene_positions[:, 0])
    assert np.allclose(rows[:, 1], scene_positions[:, 2]) and np.allclose(rows[:, 1], 38.0 + RING_LIFT_CM)
    assert np.allclose(rows[:, 2], -scene_positions[:, 1])
    normal = NORMAL_OFFSET // 4
    assert np.allclose(rows[:, normal], selection.ring.normals[:, 0])
    assert np.allclose(rows[:, normal + 1], 0.0), "the band's direction is level in the engine too"
    assert np.allclose(rows[:, normal + 2], -selection.ring.normals[:, 1])
    assert np.array_equal(rows[:, UV_OFFSET // 4:UV_OFFSET // 4 + 2], selection.ring.uvs)
    assert sink.selection == selection == sink.state().selection
    assert (sink.ring_uploads, sink.geometry_uploads) == (1, uploads), "no Model buffer was uploaded"
    assert len(scene.parts) == 2, "no Model was created or destroyed"


def test_an_empty_selection_hides_the_ring(rig) -> None:
    sink, scene, sync, _records = rig
    sync.set_selection(["a"])
    scene.calls.clear()
    assert sync.set_selection([]) is True
    assert scene.calls == [("ring", None), ("frame",)] and scene.ring is None
    assert sink.selection == EMPTY_SELECTION and sink.ring_uploads == 1


def test_the_ring_rides_the_transaction_of_the_move(rig) -> None:
    sink, scene, sync, records = rig
    sync.set_selection(["a"])
    scene.calls.clear()
    moved = {**records, "a": item("a", 150.0, 250.0, rotation=30.0, base=38.0)}
    sync.apply(moved)
    assert [call[0] for call in scene.calls] == ["pose", "ring", "frame"], "one transaction"
    assert sink.state() == sync.expected_state() and sink.selection == selection_of(moved, ["a"])
    assert sink.geometry_uploads == 2, "the two Models of the first apply, and none since"


def test_clear_drops_the_ring_from_the_books_and_the_scene_hides_it(rig) -> None:
    sink, scene, sync, records = rig
    sync.set_selection(["a", "b"])
    sync.reset()                                  # sink.clear() -> scene.clear()
    assert sink.selection == EMPTY_SELECTION and scene.ring is None
    sync.apply(records)
    assert sink.selection == selection_of(records, ["a", "b"]), "the wish came back with the items"
    assert sink.state() == sync.expected_state()


def test_the_protocol_holds_for_the_new_call(rig) -> None:
    sink, scene, _sync, records = rig
    with pytest.raises(SinkProtocolError, match="outside"):
        sink.set_selection(selection_of(records, ["a"]))
    sink.begin()
    with pytest.raises(SinkProtocolError, match="Selection"):
        sink.set_selection({"a"})  # type: ignore[arg-type]
    assert scene.calls == [], "refused before the engine was touched"
    sink.commit()


def test_an_engine_that_fails_on_the_ring_is_recovered_through_reset(rig) -> None:
    sink, scene, sync, records = rig
    scene.fail_once = "set_selection_ring"
    with pytest.raises(RuntimeError, match="engine failed in set_selection_ring"):
        sync.set_selection(["a"])
    assert sync.poisoned
    sync.reset()
    sync.apply(records)
    assert sink.selection == selection_of(records, ["a"]) and scene.ring is not None
    assert sink.state() == sync.expected_state()


def test_a_sink_whose_engine_is_gone_still_clears(rig) -> None:
    sink, scene, sync, _records = rig
    sync.set_selection(["a"])
    scene.dead = True
    sync.reset()                                  # must not raise: the engine is gone
    assert sink.selection == EMPTY_SELECTION and sink.item_ids() == ()
    sink.begin()
    with pytest.raises(EngineGone):
        sink.set_selection(selection_of({"a": item("a")}, ["a"]))


# ── the scene file and the shader, read as text ──────────────────────────────


def scene_text() -> str:
    return strip_comments(SCENE.read_text(encoding="utf-8"))


def ring_block() -> str:
    code = scene_text()
    start = code.index("id: selectionRing")
    return code[code.rindex("Model {", 0, start):]


def test_python_and_qml_agree_on_the_rings_numbers() -> None:
    code = scene_text()
    width = re.search(r"readonly property real ringWidthPx:\s*([\d.]+)", code)
    assert width is not None and float(width.group(1)) == RING_WIDTH_PX
    colour = re.search(r'property color selectionColor:\s*"#([0-9a-fA-F]{6})"', code)
    assert colour is not None
    assert tuple(int(colour.group(1)[i:i + 2], 16) for i in (0, 2, 4)) == SELECTION_RGB
    linear = re.search(r"selectionColorLinear:\s*Qt\.vector3d\(([^)]*)\)", code)
    assert linear is not None
    assert [float(v) for v in linear.group(1).split(",")] == pytest.approx(
        srgb8_to_linear(SELECTION_RGBA)[:3], abs=5e-4), "the default IS the colour, linear"
    assert re.search(r"property real ringDepthScale:\s*0\.01\b", code), "drawn in front (ADR-060)"
    near = re.search(r"PerspectiveCamera\s*\{[^}]*clipNear:\s*([\d.]+)", code, re.DOTALL)
    assert near is not None and float(near.group(1)) == walk.NEAR_PLANE_CM, (
        "the walker's radius is held against THIS near plane (core/scene3d/walk.py)")


def test_the_ring_is_one_static_model_that_cannot_be_picked_and_is_no_part() -> None:
    code = scene_text()
    block = ring_block()
    for needed in ("pickable: false", "castsShadows: false", "receivesShadows: false",
                   "shadingMode: CustomMaterial.Unshaded", "cullMode: Material.NoCulling",
                   'vertexShader: "ring.vert"', 'fragmentShader: "ring.frag"',
                   "visible: root.selectionVisible"):
        assert needed in block, needed
    assert code.count("id: selectionRing") == 1
    assert code.index("Node { id: parts }") < code.index("id: selectionRing"), (
        "beside the parts node, not inside it: listParts() must not see the ring")
    assert "selectionRing" not in code[code.index("function listParts"):code.index("function projectToView")]
    # never created from a Component: nothing can make a second one, and nothing destroys it
    # (each Component's own braces, matched — L1.4 put Components INSIDE the View3D too)
    components = []
    for match in re.finditer(r"Component\s*\{", code):
        depth, end = 0, match.end() - 1
        for end in range(match.end() - 1, len(code)):
            depth += {"{": 1, "}": -1}.get(code[end], 0)
            if depth == 0:
                break
        components.append(code[match.start():end + 1])
    assert len(components) >= 6, "the scene's material and sky components were found"
    assert not any("ring.vert" in component or "selectionRing" in component for component in components)
    assert "selectionRing.destroy" not in code


def test_the_shader_moves_a_vertex_by_band_widths_and_pulls_it_in_front() -> None:
    source = strip_comments((QML_DIR / "ring.vert").read_text(encoding="utf-8"))
    assert "UV0.x * width" in source and "UV0.y * width" in source
    assert "uFlat + depth * uPerDepth" in source
    assert "mat3(MODEL_MATRIX) * NORMAL" in source
    # towards the NEAR PLANE, wherever the backend has it: plainly scaling clip z is
    # right for a 0..1 depth range only — on OpenGL (-1..1) it put the ring behind the
    # ground of the truth view (measured: 0 ring pixels; the render tier's OpenGL row)
    assert "POSITION.z = mix(NEAR_CLIP_VALUE * POSITION.w, POSITION.z, uDepthScale);" in source
    assert "POSITION.z *=" not in source
    fragment = strip_comments((QML_DIR / "ring.frag").read_text(encoding="utf-8"))
    assert "FRAGCOLOR = vec4(uColor, 1.0);" in fragment
    block = ring_block()
    for uniform in ("uColor", "uPerDepth", "uFlat", "uDepthScale"):
        assert f"property {'vector3d' if uniform == 'uColor' else 'real'} {uniform}:" in block


def test_the_ring_colour_is_the_canvas_selection_colour() -> None:
    """ONE selection blue in the app: the select tool's box, the items' highlight pen,
    the 3D ring. The ring's is a mirror (``core`` cannot import the tool's ``QColor``)
    — pinned against both, so a change of one without the others fails here."""
    from open_garden_planner.core.tools.select_tool import SelectTool

    tool = SelectTool.ENCLOSING_COLOR
    assert (tool.red(), tool.green(), tool.blue()) == SELECTION_RGB
    pens = 0
    for name in ("rectangle_item.py", "circle_item.py"):
        tree = ast.parse((SRC / "ui" / "canvas" / "items" / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.If) and "isSelected" in ast.unparse(node.test):
                for call in ast.walk(node):
                    if (isinstance(call, ast.Call) and getattr(call.func, "id", "") == "QColor"
                            and len(call.args) == 4):
                        values = tuple(ast.literal_eval(arg) for arg in call.args[:3])
                        if values == SELECTION_RGB:
                            pens += 1
    assert pens >= 2, "the canvas items' selection highlight pens are this blue"
