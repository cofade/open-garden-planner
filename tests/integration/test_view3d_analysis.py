"""Analyze in 3D, end to end on the workspace (Phase 17 L2, #386).

The real ``Workspace`` around a real canvas, with the REAL 2D analysis beside it — a
``SunShadowController`` and a ``SunHeatmapController`` whose worker really computes
the day — and the engine replaced at its seam by a ``RecordingSink`` and a stand-in
host that records the overlays, the Cutaway switch, the fades and every frame it is
asked for. Each test follows a user's path through the Analyze menu and holds the
3D side to the 2D side's own answer:

- L2.1: the shadow drape IS the canvas overlay's polygons, cut at the plan; the
  hours-of-sun drape IS the heatmap's map in the canvas's ramp; choosing it switches
  the shared Hours of Sun on; a click on the ground reads the map's cell there — the
  point found by the view ray, checked against the camera's own target — with its
  band, and pins it.
- L2.2: the sun path's arcs are ``core.solar``'s (noon point included), the legend
  names them, and the day sweep runs sunrise → sunset with the drape filling up to
  the whole map and the clock given back.
- L2.3: the info card v1 names the height's source, the growth share, the sun the
  run measured and the sowing / harvest windows; +N years moves the ONE clock and
  shows a before/after built from exactly two frames; Back returns.
- L2.4: Cutaway hides the roofs and fades exactly what stands between the eye and
  the selection.

And the memory rule (ADR-060): nothing here takes a frame by itself — the click's
pick and the jump's two grabs are the only ones. The pixels are the render tier's
(``tests/integration/test_view3d_analysis_render.py``).
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent

from open_garden_planner.core.commands import CreateItemCommand
from open_garden_planner.core.frost_dates import parse_frost
from open_garden_planner.core.heatmap_render import build_sun_lut
from open_garden_planner.core.object_height import METADATA_KEY
from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.core.scene3d import engine_buffers
from open_garden_planner.core.scene3d.camera import FOV_DEG
from open_garden_planner.core.scene3d.drape import sun_hours_drape
from open_garden_planner.core.scene3d.pick_oracle import perspective_ray
from open_garden_planner.core.scene3d.sun_path import ARC_KINDS, dome_point
from open_garden_planner.core.scene3d.xray import XRAY_OPACITY
from open_garden_planner.core.shadow_geometry import clip_to_rect
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE
from open_garden_planner.core.solar import solar_position
from open_garden_planner.services.sun_mismatch_service import band_of
from open_garden_planner.services.task_generator import calendar_windows
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.canvas_view import CanvasView
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem
from open_garden_planner.ui.canvas.sun_heatmap import SunHeatmapController
from open_garden_planner.ui.canvas.sun_shadow_controller import SunShadowController
from open_garden_planner.ui.sun_exposure_text import sun_requirement_label
from open_garden_planner.ui.view3d.analysis_modes import DrapeMode
from open_garden_planner.ui.view3d.workspace import XRAY_DELAY_MS, WorkspaceMode
from tests.integration.test_scene3d_plants import drop
from tests.integration.test_view3d_workspace_widget import Bench, FakeHost

SPLIT = WorkspaceMode.SPLIT
PLAN = WorkspaceMode.PLAN
BERLIN = {"latitude": 52.52, "longitude": 13.40,
          "frost_dates": {"last_spring_frost": "04-15", "first_fall_frost": "10-20"}}
WIDTH, DEPTH = 2000.0, 1500.0
LUT = build_sun_lut()


class GrabHost(FakeHost):
    """The stand-in host, and a picture for every ``grab`` — another colour each time,
    so a before and an after can be told apart."""

    def __init__(self, prefer_software: bool) -> None:
        super().__init__(prefer_software)
        self.grab_colours = [QColor(30, 120, 40), QColor(200, 160, 40)]

    def grab(self, _label: str = "") -> QImage:  # type: ignore[override]
        self.frames_taken.append("grab")
        image = QImage(80, 50, QImage.Format.Format_RGB32)
        image.fill(self.grab_colours[(len(self.frames_taken) - 1) % 2])
        return image

    def pick(self, _x: float, _y: float) -> None:
        self.frames_taken.append("pick")
        return None  # the ground: no item there


class AnalysisBench(Bench):
    """The bench with a garden location and the real 2D analysis wired in."""

    def __init__(self, view: CanvasView, qtbot: Any, folder: Path) -> None:
        super().__init__(view, qtbot, folder, location=dict(BERLIN))
        self.shadows = SunShadowController(self.scene, lambda: self.location, clock=self.clock)
        self.shadows.set_enabled(True)
        self.heatmap = SunHeatmapController(self.scene, lambda: self.location)
        self.requests: list[bool] = []
        self.workspace.connect_analysis(self.shadows, self.heatmap, self._request_sun_hours)

    def _factory(self, prefer_software: bool) -> Any:
        from open_garden_planner.core.scene3d import RecordingSink

        self.factory_calls.append(prefer_software)
        host, sink = GrabHost(prefer_software), RecordingSink()
        self.hosts.append(host)
        self.sinks.append(sink)
        return host, sink

    def _request_sun_hours(self, on: bool) -> None:
        """What the app's ``LiveSunMap.set_enabled`` does, in short: compute the map."""
        self.requests.append(on)
        if on:
            self.heatmap.run_for_day(self.clock.plan_date)
        else:
            self.heatmap.clear()

    def open3d(self) -> None:
        self.workspace.set_mode(SPLIT)
        self.settle()

    def wait_for_map(self) -> Any:
        self.qtbot.waitUntil(lambda: self.heatmap.result() is not None
                             and not self.heatmap.result_pending, timeout=60000)
        self.settle(20)
        return self.heatmap.result()

    def shed(self, x: float, y: float, height: float | None = None,
             kind: ObjectType = ObjectType.TOOL_SHED, size: tuple[float, float] = (300.0, 200.0),
             ) -> RectangleItem:
        item = RectangleItem(x, y, size[0], size[1], object_type=kind,
                             layer_id=self.scene.active_layer.id)
        if height is not None:
            item.metadata[METADATA_KEY] = height
        self.commands.execute(CreateItemCommand(self.scene, item, "shed"))
        return item

    def click_view(self, x: float, y: float) -> None:
        """A left click into the 3D view, through the input filter the host was given."""
        orbit = self.host.filters[0]
        for kind in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease):
            buttons = Qt.MouseButton.LeftButton if kind == QEvent.Type.MouseButtonPress \
                else Qt.MouseButton.NoButton
            event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), Qt.MouseButton.LeftButton,
                                buttons, Qt.KeyboardModifier.NoModifier)
            orbit.eventFilter(None, event)


@pytest.fixture()
def small_canvas(qtbot) -> CanvasView:
    scene = CanvasScene(width_cm=WIDTH, height_cm=DEPTH)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.set_snap_enabled(False)
    return view


@pytest.fixture()
def bench(small_canvas: CanvasView, qtbot, tmp_path: Path) -> AnalysisBench:
    made = AnalysisBench(small_canvas, qtbot, tmp_path)
    yield made
    made.heatmap.shutdown()


def vertices(buffers: Any) -> np.ndarray:
    return np.frombuffer(buffers.vertex_data, dtype="<f4").reshape(-1, 12)


def ground_area(buffers: Any) -> float:
    """The area an overlay covers, seen from above (engine x = E, z = -N)."""
    v = vertices(buffers)
    tri = np.frombuffer(buffers.index_data, dtype="<u4").reshape(-1, 3).astype(np.int64)
    xz = v[:, [0, 2]].astype(np.float64)
    a, b, c = xz[tri[:, 0]], xz[tri[:, 1]], xz[tri[:, 2]]
    return float(0.5 * np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                              - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])).sum())


def polygons_area(polygons: list[list[tuple[float, float]]]) -> float:
    """Outers counter-clockwise, holes clockwise: the signed areas add up."""
    total = 0.0
    for ring in polygons:
        xy = np.asarray(ring, dtype=np.float64)
        total += 0.5 * float(np.dot(xy[:, 0], np.roll(xy[:, 1], -1))
                             - np.dot(xy[:, 1], np.roll(xy[:, 0], -1)))
    return total


# ── L2.1: the drapes ─────────────────────────────────────────────────────────


def test_the_shadow_drape_is_the_2d_overlays_own_polygons_cut_at_the_plan(bench) -> None:
    bench.shed(800.0, 600.0, height=300.0)
    bench.shed(1700.0, 200.0, height=400.0)  # its shadow runs off the plan's edge
    bench.clock.set_time_of_day(time(9, 30))
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    workspace.set_drape_mode(DrapeMode.SHADOWS)
    assert workspace.drape_actions[DrapeMode.SHADOWS].isChecked()
    drape = host.overlays["drape"]
    assert drape is not None
    expected = clip_to_rect(bench.shadows.drape_polygons(), WIDTH, DEPTH)
    assert expected, "the canvas paints a shadow"
    assert ground_area(drape) == pytest.approx(polygons_area(expected), rel=1e-4)
    # the sun moves: the canvas recomputes, and the drape follows the SAME polygons
    loads = len(host.overlay_calls)
    bench.clock.set_time_of_day(time(16, 0))
    assert len(host.overlay_calls) > loads
    moved = clip_to_rect(bench.shadows.drape_polygons(), WIDTH, DEPTH)
    assert ground_area(host.overlays["drape"]) == pytest.approx(polygons_area(moved), rel=1e-4)
    # night: the canvas shades the whole garden, and so does the drape
    bench.clock.set_time_of_day(time(23, 30))
    assert ground_area(host.overlays["drape"]) == pytest.approx(WIDTH * DEPTH, rel=1e-6)
    workspace.set_drape_mode(DrapeMode.NONE)
    assert host.overlays["drape"] is None


def test_the_hours_of_sun_drape_switches_hours_of_sun_on_and_lays_the_canvas_map(bench) -> None:
    bench.shed(900.0, 700.0, height=250.0)
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    assert bench.requests == [True], "the shared Hours of Sun was switched on"
    shown = bench.wait_for_map()
    expected = engine_buffers(sun_hours_drape(shown.minutes, shown.grid, shown.daylight_minutes, LUT))
    drape = host.overlays["drape"]
    assert drape is not None and drape.vertex_data == expected.vertex_data, "the canvas's map"
    assert drape.index_data == expected.index_data
    # row 0 = SOUTH: the shed's shadow lies NORTH of it at midday, and so does the drape's
    # shade — the drape's darkest vertices are north of the shed's centre
    v = vertices(drape)
    alpha = v[:, 9]
    shaded = v[alpha >= np.quantile(alpha, 0.995)]
    assert -float(np.median(shaded[:, 2])) > 700.0, "the shade lies north of the shed"
    bench.heatmap.clear()  # Hours of Sun switched off elsewhere
    assert host.overlays["drape"] is None


def test_a_click_on_the_ground_reads_the_map_there_and_pins_it(bench) -> None:
    bench.shed(900.0, 700.0, height=250.0)
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    slot = workspace.info_card.parentWidget()
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    assert slot.hint() == "Click the ground to read its hours of sun."
    shown = bench.wait_for_map()
    frames = list(host.frames_taken)
    # the centre of the view looks at the camera's own target, on the ground
    width, height = host.size
    bench.click_view(width / 2.0, height / 2.0)
    assert host.frames_taken == [*frames, "pick"], "the click's one pick, nothing else"
    probe = workspace.analysis.probe_result
    target = workspace.camera.pose.target
    assert (probe.east_cm, probe.north_cm) == pytest.approx(target, abs=1e-6)
    assert probe.reason == "ok" and probe.minutes == shown.minutes_at(*target)
    assert probe.band is band_of(probe.minutes) and probe.day == shown.day
    assert sun_requirement_label(probe.band.value) in slot.hint()
    assert host.overlays["lines"] is not None, "the pin"
    # an off-centre click: the point is where the view ray meets the ground
    eye, aim = workspace.camera.pose.eye, workspace.camera.pose.target_scene
    ray = perspective_ray(eye, aim, FOV_DEG, host.size, 150.0, 320.0)
    reach = -ray.origin[2] / ray.direction[2]
    expected = (ray.origin[0] + reach * ray.direction[0], ray.origin[1] + reach * ray.direction[1])
    bench.click_view(150.0, 320.0)
    probe = workspace.analysis.probe_result
    assert (probe.east_cm, probe.north_cm) == pytest.approx(expected, abs=1e-6)
    # with the shadows on the ground, a ground click only clears the selection
    workspace.set_drape_mode(DrapeMode.SHADOWS)
    before = workspace.analysis.probe_result
    bench.click_view(300.0, 300.0)
    assert workspace.analysis.probe_result == before


def test_without_a_map_or_outside_it_the_probe_says_so(bench) -> None:
    bench.open3d()
    workspace = bench.workspace
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    # the map is being computed: its result is queued to this thread, so a click in the
    # same turn of the event loop always finds no map yet
    assert bench.heatmap.result_pending and bench.heatmap.result() is None
    width, height = bench.host.size
    bench.click_view(width / 2.0, height / 2.0)
    slot = workspace.info_card.parentWidget()
    assert workspace.analysis.probe_result.reason == "no_map"
    assert slot.hint() == "The hours of sun are not computed yet for this plan date."
    bench.wait_for_map()
    assert workspace.analysis.probe_result.reason == "ok", "the reading follows the map"
    workspace.analysis.probe(-500.0, -500.0)
    assert slot.hint() == "That spot lies outside the hours-of-sun map."


# ── L2.2: the sun path and the day sweep ─────────────────────────────────────


def test_the_sun_path_and_compass_come_from_core_solar(bench) -> None:
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    workspace.set_sun_path_visible(True)
    assert workspace.sun_path_action.isChecked()
    lines = host.overlays["lines"]
    assert lines is not None
    assert workspace.legend_text() == "Plan date 21 June 21 December 20 March"
    arcs = workspace.analysis.arcs()
    assert tuple(arc.kind for arc in arcs) == ARC_KINDS
    lat, lon = BERLIN["latitude"], BERLIN["longitude"]
    for arc in arcs:
        exact = solar_position(lat, lon, arc.noon.utc)
        assert (arc.noon.elevation_deg, arc.noon.azimuth_deg) == (exact.elevation_deg,
                                                                  exact.azimuth_deg)
    # the dome stands on the plan's centre; the June noon point lies south of it
    june = arcs[1].noon
    point = dome_point((WIDTH / 2, DEPTH / 2), 1.0, june.elevation_deg, june.azimuth_deg)
    assert point[1] < DEPTH / 2
    # the sun ball follows the instant: a time change reloads the lines
    loads = len(host.overlay_calls)
    bench.clock.set_time_of_day(time(15, 0))
    assert len(host.overlay_calls) > loads
    bench.location = None
    workspace.location_changed()
    assert workspace.legend_text() == "Set a garden location to draw the sun path."
    workspace.set_sun_path_visible(False)
    assert workspace.legend_text() == "" and host.overlays["lines"] is None


def test_the_day_sweep_runs_sunrise_to_sunset_and_fills_the_map(bench) -> None:
    bench.shed(900.0, 700.0, height=250.0)
    bench.open3d()
    workspace, host, clock = bench.workspace, bench.host, bench.clock
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    shown = bench.wait_for_map()
    start_time = clock.time_of_day
    analysis = workspace.analysis
    assert workspace.set_sweeping(True) and workspace.sweep_action.isChecked()
    sunrise, sunset = analysis.daylight_minutes()
    assert clock.instant.minute_of_day == sunrise
    previous = np.zeros_like(shown.minutes)
    steps = 0
    while analysis.sweeping:
        minute = clock.instant.minute_of_day
        expected = shown.minutes_through(minute, clock.tz)
        drape = engine_buffers(sun_hours_drape(expected, shown.grid, shown.daylight_minutes, LUT))
        assert host.overlays["drape"].vertex_data == drape.vertex_data, f"at {minute}"
        assert np.all(expected >= previous), "it only fills up"
        previous = expected
        analysis._sweep_step()  # noqa: SLF001 - the timer's slot, stepped by hand
        steps += 1
    assert steps >= (sunset - sunrise) // 10
    np.testing.assert_array_equal(previous, shown.minutes)
    assert clock.time_of_day == start_time, "the clock is given back"
    full = engine_buffers(sun_hours_drape(shown.minutes, shown.grid, shown.daylight_minutes, LUT))
    assert host.overlays["drape"].vertex_data == full.vertex_data
    assert not workspace.sweep_action.isChecked()
    assert host.frames_taken == [], "a sweep takes no frame"


def test_a_sweep_without_a_location_is_refused_and_says_why(bench) -> None:
    bench.location = None
    bench.open3d()
    assert bench.workspace.set_sweeping(True) is False
    assert not bench.workspace.sweep_action.isChecked()
    assert "no daylight to sweep" in bench.workspace.status_text()


# ── L2.3: the info card v1 and the growth jump ───────────────────────────────


def test_the_card_names_the_heights_source_the_growth_the_sun_and_the_windows(bench) -> None:
    tomato = drop(bench.view, "PERENNIAL:species=tomato", QPointF(1400.0, 1000.0))
    tomato.metadata["plant_instance"] = {"planting_date": "2026-05-01", "current_height_cm": 20.0}
    bench.open3d()
    workspace = bench.workspace
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    bench.wait_for_map()
    tomato.setSelected(True)
    bench.settle()
    card = workspace.info_card
    record = workspace.controller.sync.records[str(tomato.item_id)]
    from open_garden_planner.core.measurements import format_length

    assert card.value("Height:") == f"{format_length(record.height_cm)} (grown to the plan date)"
    assert card.value("Growth:") is not None and card.value("Growth:").endswith(
        "% of the way to full size")
    minutes = bench.heatmap.receiver_minutes[str(tomato.item_id)]
    from PyQt6.QtCore import QLocale

    assert card.value("Sun:").startswith(f"{QLocale().toString(minutes / 60.0, 'f', 1)} h on ")
    assert card.value("Sun:").endswith(sun_requirement_label(band_of(minutes).value))
    species = tomato.metadata["plant_species"]
    frost = parse_frost(BERLIN["frost_dates"]["last_spring_frost"], bench.clock.plan_date.year)
    windows = [w for w in calendar_windows(species.get, frost)
               if w[0] in ("indoor_sow", "direct_sow", "harvest")]
    assert windows, "the bundled tomato has its windows"
    labels = {"indoor_sow": "Sow indoors:", "direct_sow": "Sow outdoors:", "harvest": "Harvest:"}
    for kind, _start, _end in windows:
        assert card.value(labels[kind]) is not None, kind


def test_a_growth_jump_moves_the_clock_and_shows_before_and_after(bench) -> None:
    tree = drop(bench.view, "TREE:species=apple tree", QPointF(1000.0, 700.0))
    tree.metadata["plant_instance"] = {"planting_date": "2024-04-01", "current_height_cm": 150.0,
                                       "current_spread_cm": 100.0}
    bench.open3d()
    workspace, host, clock = bench.workspace, bench.host, bench.clock
    start = clock.plan_date
    controller = workspace.controller
    height_before = controller.sync.records[str(tree.item_id)].height_cm
    workspace.jump_actions[3].trigger()
    assert clock.plan_date == start.replace(year=start.year + 3)
    bench.qtbot.waitUntil(lambda: workspace.wipe is not None
                          and workspace.pane.body.currentWidget() is workspace.wipe, timeout=5000)
    assert host.frames_taken == ["grab", "grab"], "two frames: before and after, no more"
    assert controller.pass_date == clock.plan_date
    assert controller.sync.records[str(tree.item_id)].height_cm > height_before, "it grew"
    before_label, after_label = workspace.wipe.labels()
    assert before_label.startswith("Before: ") and after_label.startswith("After: ")
    assert workspace.back_action.isEnabled() and workspace.back_action.text().startswith("Back to ")
    # jumping again FROM the comparison: its after-picture is the new before (the view is
    # not shown and could give no frame) — one more grab, for the new after
    after_colour = workspace.wipe.after_image().pixelColor(0, 0)
    workspace.jump_actions[1].trigger()
    assert clock.plan_date == start.replace(year=start.year + 4)
    bench.qtbot.waitUntil(lambda: len(host.frames_taken) == 3
                          and workspace.pane.body.currentWidget() is workspace.wipe, timeout=5000)
    assert workspace.wipe._before.pixelColor(0, 0) == after_colour  # noqa: SLF001
    workspace.wipe.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape,
                                           Qt.KeyboardModifier.NoModifier))
    assert workspace.pane.body.currentWidget() is workspace.pane.engine_widget
    bench.settle(120)
    workspace.back_action.trigger()
    assert clock.plan_date == start, "back to where the FIRST jump started"
    assert not workspace.back_action.isEnabled()
    assert workspace.pane.body.currentWidget() is workspace.pane.engine_widget


def test_a_jump_from_29_february_lands_on_1_march_and_the_clock_bounds_it(bench) -> None:
    bench.open3d()
    workspace, clock = bench.workspace, bench.clock
    clock.set_date(date(2028, 2, 29))
    bench.settle(600)
    workspace.jump_actions[1].trigger()
    assert clock.plan_date == date(2029, 3, 1)
    clock.set_date(date(2998, 6, 1))
    bench.settle(600)
    workspace.jump_actions[10].trigger()
    assert clock.plan_date == date(2999, 6, 1) <= MAX_PLAN_DATE
    workspace.jump_actions[10].trigger()
    assert clock.plan_date == date(2999, 6, 1), "at the clock's bound the date stays"


# ── L2.4: Cutaway ────────────────────────────────────────────────────────────


def test_cutaway_hides_the_roofs_and_fades_what_stands_before_the_selection(bench) -> None:
    bed = bench.shed(WIDTH / 2 - 150.0, DEPTH / 2 - 100.0, kind=ObjectType.RAISED_BED)
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    eye = workspace.camera.pose.eye
    target = (WIDTH / 2, DEPTH / 2)
    # a tall shed a little way from the bed towards the eye: in the line of sight
    near = (target[0] + 0.12 * (eye[0] - target[0]), target[1] + 0.12 * (eye[1] - target[1]))
    blocker = bench.shed(near[0] - 100.0, near[1] - 100.0, height=700.0, size=(200.0, 200.0))
    aside = bench.shed(150.0, 150.0, height=700.0, size=(100.0, 100.0))
    bench.settle()
    bed.setSelected(True)
    bench.settle()
    workspace.set_cutaway(True)
    assert workspace.cutaway_action.isChecked() and host.roofs_hidden is True
    bench.qtbot.waitUntil(lambda: host.faded == {str(blocker.item_id)}, timeout=3000)
    assert getattr(host, "fade_opacity", None) == XRAY_OPACITY
    assert str(aside.item_id) not in host.faded and str(bed.item_id) not in host.faded
    # the selection goes: nothing fades
    bench.scene.clearSelection()
    bench.qtbot.wait(XRAY_DELAY_MS + 100)
    assert host.faded == frozenset()
    bed.setSelected(True)
    bench.qtbot.waitUntil(lambda: host.faded == {str(blocker.item_id)}, timeout=3000)
    workspace.set_cutaway(False)
    assert host.roofs_hidden is False and host.faded == frozenset()
    assert host.frames_taken == [], "Cutaway takes no frame"


# ── the pane's life ──────────────────────────────────────────────────────────


def test_nothing_is_sent_while_the_pane_is_hidden_and_all_of_it_when_it_shows(bench) -> None:
    bench.open3d()
    workspace, host = bench.workspace, bench.host
    workspace.set_mode(PLAN)
    bench.settle()
    calls = len(host.overlay_calls)
    workspace.set_sun_path_visible(True)
    workspace.set_drape_mode(DrapeMode.SHADOWS)
    bench.clock.set_time_of_day(time(14, 0))
    assert len(host.overlay_calls) == calls, "hidden: flags only"
    workspace.set_mode(SPLIT)
    bench.settle()
    assert host.overlays["lines"] is not None and "drape" in host.overlays
    assert len(host.overlay_calls) >= calls + 2


def test_a_new_document_drops_the_probe_and_the_jump(bench) -> None:
    bench.open3d()
    workspace = bench.workspace
    workspace.set_drape_mode(DrapeMode.SUN_HOURS)
    bench.wait_for_map()
    workspace.analysis.probe(500.0, 500.0)
    workspace.jump_actions[1].trigger()
    bench.settle(150)
    assert workspace.analysis.probe_result is not None and workspace.back_action.isEnabled()
    bench.scene.document_replaced.emit()
    bench.settle(150)
    assert workspace.analysis.probe_result is None
    assert not workspace.back_action.isEnabled()
    assert workspace.drape_actions[DrapeMode.SUN_HOURS].isChecked(), "the user's choice stays"
