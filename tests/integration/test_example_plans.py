"""#940: every bundled example opens ready to be shown.

Each test drives the gallery's own path (File > New from example > Open Selected ends in
``GardenPlannerApp._open_template_file``) in a real main window whose session clock was
seeded late on a November evening. The plan must then stand on its own day, in the light
it is meant to be seen in, with its hint on a layer that can be hidden for a picture and
with its stored camera tours ready to play. Nothing here names a plan but two tests of
what only one plan has: the rules run over ``tests/example_specs.py``.
"""

import json
from datetime import UTC, datetime, time

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core import sim_clock
from open_garden_planner.core.solar import solar_position
from open_garden_planner.services.example_library import BUNDLED_EXAMPLES, bundled_examples
from open_garden_planner.ui.canvas.items.text_item import TextItem
from open_garden_planner.ui.canvas.sun_shadow_controller import STATE_ACTIVE
from tests.example_specs import HINTS, LIGHT, ORBIT, SPECS

#: 22:30 on a November evening in Central Europe: the sun is down over every garden.
LATE = datetime(2026, 11, 10, 21, 30, tzinfo=UTC)
TOURS_DE = {ORBIT: "Rundflug", "Shadows over the day": "Schatten über den Tag",
            "A year in the garden": "Ein Jahr im Garten"}


@pytest.fixture
def window(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(sim_clock, "_now_to_the_minute", lambda: LATE)
    monkeypatch.setattr("open_garden_planner.services.example_library.user_templates_dir", lambda: tmp_path)
    get_settings().show_welcome_on_startup = False
    win = GardenPlannerApp()
    monkeypatch.setattr(win, "_confirm_discard_changes", lambda: True)
    qtbot.addWidget(win)
    assert win._sim_clock.utc == LATE
    return win


def open_example(window, slug, language="en"):
    entry = next(entry for entry in bundled_examples(language) if entry.path.stem == slug)
    window._open_template_file(str(entry.path))
    assert window._project_manager.current_file is None, "an example opens as an untitled copy"
    return entry


def sidecar(slug):
    return json.loads((BUNDLED_EXAMPLES / f"{slug}.meta.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("slug", sorted(SPECS))
def test_an_example_opens_on_its_day_in_the_light_it_is_meant_for(window, slug):
    spec = SPECS[slug]
    open_example(window, slug)

    clock = window._sim_clock
    assert clock.plan_date == spec.day
    assert clock.utc.time() == time.fromisoformat(sidecar(slug)["showcase_utc_time"])
    place = window._project_manager.location
    sun = solar_position(place["latitude"], place["longitude"], clock.utc)
    low, high, side = LIGHT[spec.light]
    assert low <= sun.elevation_deg <= high, f"{slug}: the sun stands {sun.elevation_deg:.1f} degrees up"
    if side:
        assert (sun.azimuth_deg < 180.0) == (side == "east")
    assert window._sun_controller.state == STATE_ACTIVE, "the plan is not night-dimmed"
    assert window._project_manager.north_angle_deg == spec.north_angle_deg


@pytest.mark.parametrize("slug", sorted(SPECS))
def test_hiding_the_hint_layer_leaves_the_plan_ready_for_a_picture(window, slug):
    open_example(window, slug)
    scene = window.canvas_scene
    texts = [item for item in scene.items() if isinstance(item, TextItem)]
    if not SPECS[slug].hint:
        assert not texts
        return
    (hint,) = texts
    (layer,) = [layer for layer in scene.layers if layer.name == HINTS[""]]
    assert hint.layer_id == layer.id and hint.isVisible()
    assert scene.canvas_rect.contains(hint.sceneBoundingRect())
    shown = {item for item in scene.items() if item.isVisible()}

    scene.update_layer_visibility(layer.id, False)
    assert not hint.isVisible()
    assert {item for item in scene.items() if item.isVisible()} == shown - {hint}, (
        "the layer holds the hint and nothing else")
    scene.update_layer_visibility(layer.id, True)
    assert hint.isVisible()


@pytest.mark.parametrize("slug", sorted(SPECS))
def test_an_examples_stored_tours_are_there_and_can_be_flown(window, slug):
    open_example(window, slug)
    manager = window._project_manager
    tours = manager.camera_tours
    assert [tour.name for tour in tours] == list(SPECS[slug].tours)
    assert manager.last_load_skipped_tours_count == 0
    width, depth = window.canvas_scene.width_cm, window.canvas_scene.height_cm
    for tour in tours:
        tour.spec()                                  # what the recorder takes: it must build
        motion = tour.camera_motion()
        for share in (0.0, 0.25, 0.5, 0.75, 1.0):
            key = motion.at(share)
            assert key.eye[2] > 100.0, f"{slug} / {tour.name}: the camera is above the ground"
            assert key.target[0] == pytest.approx(width / 2, abs=width / 2 + 1)
            assert key.target[1] == pytest.approx(depth / 2, abs=depth / 2 + 1)
    orbit = tours[0]
    assert orbit.orbit.pose.target == pytest.approx((width / 2, depth / 2))
    # far enough to see the whole plan: at least half its diagonal away
    assert orbit.orbit.pose.distance_cm >= (width ** 2 + depth ** 2) ** 0.5 / 2


def test_a_translated_example_names_its_hint_layer_and_tours_in_its_language(window):
    """The German copy of the plan with two tours: both names and the layer are German."""
    open_example(window, "terraced-house-garden", "de")
    names = [tour.name for tour in window._project_manager.camera_tours]
    assert names == [TOURS_DE[name] for name in SPECS["terraced-house-garden"].tours]
    assert [layer.name for layer in window.canvas_scene.layers if layer.name == HINTS["de"]]


def test_the_cottage_garden_is_drawn_to_measure(window):
    """Its two axes are guide lines, and every distance constraint agrees with the drawing:
    a constraint that did not would move an item on the user's first edit."""
    from open_garden_planner.core.constraints import ConstraintType
    from open_garden_planner.core.measure_snapper import get_anchor_points

    open_example(window, "cottage-garden")
    scene = window.canvas_scene
    assert sorted((guide.is_horizontal, guide.position) for guide in scene.guide_lines) == [
        (False, 600.0), (True, 660.0)]
    by_id = {item.item_id: item for item in scene.items() if hasattr(item, "item_id")}
    constraints = list(scene.constraint_graph.constraints.values())
    assert len(constraints) == 3
    for constraint in constraints:
        assert constraint.constraint_type is ConstraintType.DISTANCE and constraint.visible
        points = []
        for ref in (constraint.anchor_a, constraint.anchor_b):
            (point,) = [anchor.point for anchor in get_anchor_points(by_id[ref.item_id])
                        if anchor.anchor_type is ref.anchor_type and anchor.anchor_index == ref.anchor_index]
            points.append(point)
        measured = ((points[0].x() - points[1].x()) ** 2 + (points[0].y() - points[1].y()) ** 2) ** 0.5
        assert measured == pytest.approx(constraint.target_distance, abs=0.1)
