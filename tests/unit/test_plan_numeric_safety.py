"""Regression tests for the .ogp numeric trust boundary (AUD-041)."""

import json

import pytest

from open_garden_planner.core.plan_io import read_plan, validate_plan_data, write_plan
from open_garden_planner.core.project import ProjectManager
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import RectangleItem


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), 10**400])
def test_invalid_numbers_refused_before_preparing_scene(qtbot, tmp_path, monkeypatch, value):
    pm = ProjectManager()
    scene = CanvasScene()
    path = tmp_path / "bad.ogp"
    path.write_text(json.dumps({"objects": [], "metadata": {"bad": value}}))

    def unexpected_prepare(data):
        pytest.fail("[A1-NUMERIC] invalid data reached scene preparation")

    monkeypatch.setattr(pm, "_prepare_scene_data", unexpected_prepare)
    with pytest.raises(ValueError):
        pm.load(scene, path)


def test_invalid_save_keeps_existing_file(qtbot, tmp_path):
    scene = CanvasScene()
    item = RectangleItem(0, 0, 100, 100)
    scene.addItem(item)
    pm = ProjectManager()
    path = tmp_path / "good.ogp"
    pm.save(scene, path)
    original = path.read_bytes()
    item.metadata["bad"] = float("nan")
    pm.mark_dirty()
    with pytest.raises(ValueError):
        pm.save(scene, path)
    assert path.read_bytes() == original
    assert pm.is_dirty


@pytest.mark.parametrize("payload", [
    {"canvas": {"width": 49, "height": 100}},
    {"canvas": {"width": 100001, "height": 100}},
    {"objects": [{"type": "rectangle", "x": 1e308, "width": 1e308}]},
    {"objects": [{"type": "circle", "center_x": 0, "radius": "Infinity"}]},
    {"objects": [{"type": "group", "children": [{"rotation": "NaN"}]}]},
    {"objects": [{"type": "bezier", "handles_in": [{"x": "1e309", "y": 0}]}]},
    {"objects": [{"type": "background_image", "scale_factor": 1e-320}]},
    {"guides": [{"position": "NaN"}]},
    {"constraints": [{"value": "NaN"}]},
    {"layers": [{"opacity": "NaN"}]},
], ids=["small-canvas", "large-canvas", "extent-overflow", "radius-string",
        "group", "bezier", "image-scale", "guide", "constraint", "layer"])
def test_numeric_errors_cover_nested_geometry(payload):
    with pytest.raises(ValueError):
        validate_plan_data(payload)


def test_json_exponent_overflow(tmp_path):
    path = tmp_path / "overflow.ogp"
    path.write_text('{"objects":[{"x":1e309}]}')
    with pytest.raises(ValueError):
        read_plan(path)


def test_replace_failure_preserves_destination_and_cleans_temp(tmp_path, monkeypatch):
    path = tmp_path / "good.ogp"
    path.write_bytes(b"original")
    monkeypatch.setattr("open_garden_planner.core.plan_io.os.replace",
                        lambda *_: (_ for _ in ()).throw(OSError("fixture")))
    with pytest.raises(OSError):
        write_plan(path, {"objects": []})
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_text_and_finite_off_canvas_geometry_remain_compatible():
    validate_plan_data({"objects": [{"type": "text", "x": -100, "y": 1000000,
                                     "content": "NaN", "font_size": "12.0"}]})
    validate_plan_data({"canvas": {"width": 50, "height": 100000}})


def test_opaque_metadata_numeric_strings_remain_text():
    validate_plan_data({"objects": [{"type": "rectangle", "x": 0, "y": 0,
                                    "metadata": {"value": "NaN", "width": "Infinity"}}]})


def test_live_nan_rotation_is_refused_even_if_serializer_would_omit_it(qtbot, tmp_path):
    scene = CanvasScene()
    item = RectangleItem(0, 0, 100, 100)
    scene.addItem(item)
    item.rotation_angle = float("nan")
    with pytest.raises(ValueError):
        ProjectManager().save(scene, tmp_path / "bad.ogp")


@pytest.mark.parametrize("payload", [
    {"canvas": {"width": "100", "height": 100}},
    {"objects": [{"type": "group", "x": 1e308, "y": 0,
                  "children": [{"type": "rectangle", "x": 1e308, "y": 0, "width": 100, "height": 100}]}]},
    {"objects": [{"type": "polygon", "points": [{"x": -1e308, "y": 0}, {"x": 1e308, "y": 1}]}]},
], ids=["canvas-string", "group-sum", "point-bounds"])
def test_finite_conversion_and_derived_extent_failures_are_atomic(payload):
    with pytest.raises(ValueError):
        validate_plan_data(payload)
