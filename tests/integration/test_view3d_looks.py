"""A day in the garden: the look of the 3D view in the real main window (L1.4, §8.10).

A real ``GardenPlannerApp`` (the 3D workspace is the default since L1.9); its
3D engine is replaced at the documented seam (``Workspace.engine_factory``) by a
host that records what it is told and a ``RecordingSink``. The user sets the
garden's location, moves the toolbar's time through sunrise, noon, sunset and
night, changes the date, changes the quality and the reduced-motion setting in
Preferences, hides the 3D view and shows it again — and the test asserts the look
specs handed to the engine, the number of sky rebuilds, the light's direction,
and that NOTHING BUT LOOK CALLS happened: no geometry, no camera, no frame taken.

Nothing is rendered here. The same looks are judged in pixels by
``test_view3d_looks_render.py`` (opt-in, ``OGP_RENDER3D=1``).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QMessageBox

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.scene3d import RecordingSink, SunState
from open_garden_planner.core.scene3d.look import look_for, moon_travel_scene, sky_is_stale
from open_garden_planner.core.sim_clock import SimInstant
from open_garden_planner.core.solar import solar_position
from open_garden_planner.core.tools import ToolType
from open_garden_planner.ui.dialogs.preferences_dialog import PreferencesDialog
from open_garden_planner.ui.view3d.init_guard import Init3DGuard
from open_garden_planner.ui.view3d.look_controller import SKY_SETTLE_MS
from open_garden_planner.ui.view3d.sync_controller import NO_LOCATION_SUN
from open_garden_planner.ui.view3d.workspace import Workspace, WorkspaceMode
from tests.integration.test_view3d_workspace_widget import FakeHost

BERLIN = {"latitude": 52.52, "longitude": 13.405}
JUNE = date(2026, 6, 21)
DECEMBER = date(2026, 12, 21)
BEGIN, COMMIT, SUN = ("begin", None), ("commit", None), ("set_sun", None)
VIEW3D, PLAN = WorkspaceMode.VIEW3D, WorkspaceMode.PLAN


class Engines:
    """The stand-in engine factory (the recording host is the workspace tests' own)."""

    def __init__(self) -> None:
        self.modes: list[bool] = []
        self.hosts: list[FakeHost] = []
        self.sinks: list[RecordingSink] = []

    def factory(self, prefer_software: bool) -> tuple[FakeHost, RecordingSink]:
        self.modes.append(prefer_software)
        self.hosts.append(FakeHost(prefer_software))
        self.sinks.append(RecordingSink())
        return self.hosts[-1], self.sinks[-1]

    @property
    def host(self) -> FakeHost:
        return self.hosts[-1]

    @property
    def sink(self) -> RecordingSink:
        return self.sinks[-1]


@pytest.fixture()
def look_settings(qtbot):  # noqa: ARG001 - Qt must be up
    """The three 3D settings at known values, and put back afterwards."""
    settings = get_settings()
    saved = (settings.view3d_quality, settings.view3d_reduced_motion, settings.view3d_auto_level)
    settings.view3d_quality, settings.view3d_reduced_motion = "high", False
    yield settings
    settings.view3d_quality, settings.view3d_reduced_motion, settings.view3d_auto_level = saved


@pytest.fixture()
def app3d(qtbot, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, look_settings
          ) -> tuple[GardenPlannerApp, Engines]:  # noqa: ARG001 - the settings come first
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *_a, **_k: QMessageBox.StandardButton.Discard)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    engines = Engines()
    workspace = window._workspace
    assert isinstance(workspace, Workspace)
    workspace.engine_factory = engines.factory                       # THE SEAM
    workspace._guard = Init3DGuard(tmp_path / "log", is_running=lambda _pid: False)
    window.show()
    qtbot.waitExposed(window)
    window.canvas_view.set_snap_enabled(False)
    return window, engines


def _sun_at(clock: Any, wall: datetime) -> SunState:
    """The sun over Berlin for a wall reading of the app's clock — from ``core/solar``."""
    utc = SimInstant.from_datetime(wall, clock.tz).utc
    return SunState.from_solar_position(solar_position(BERLIN["latitude"], BERLIN["longitude"], utc))


def _moment(clock: Any, day: date, wanted: Any) -> datetime:
    """The first minute of ``day`` (the clock's own wall time) whose sun ``wanted`` accepts.

    Found by asking ``core/solar``, so the script does not depend on the time zone
    the test machine happens to be in."""
    start = datetime(day.year, day.month, day.day)
    for minute in range(0, 24 * 60, 2):
        wall = start + timedelta(minutes=minute)
        if wanted(_sun_at(clock, wall), _sun_at(clock, wall + timedelta(minutes=10))):
            return wall
    raise AssertionError(f"no such moment on {day}")


def _settle(qtbot: Any, ms: int = 0) -> None:
    qtbot.wait(max(ms, SKY_SETTLE_MS + 150))


def _preferences(window: GardenPlannerApp, monkeypatch: pytest.MonkeyPatch, *,
                 quality: str | None = None, reduced_motion: bool | None = None) -> None:
    """Edit → Preferences through the REAL window (``_on_preferences``): the dialog it
    builds is changed as a user would and saved — its ``exec`` returns Accepted — and
    what the window does on "Save" is what is tested (review P1: the window's call to
    the workspace could be deleted and every test still passed)."""
    def run(dialog: PreferencesDialog) -> int:
        if quality is not None:
            combo = dialog._view3d_quality_combo
            combo.setCurrentIndex(combo.findData(quality))
        if reduced_motion is not None:
            dialog._view3d_reduced_motion_check.setChecked(reduced_motion)
        dialog._save_and_accept()
        return 1

    monkeypatch.setattr(PreferencesDialog, "exec", run)
    window._on_preferences()


def test_a_day_in_the_garden_drives_the_look_and_nothing_else(app3d, qtbot, mouse_event,
                                                               monkeypatch) -> None:
    window, engines = app3d
    workspace, canvas = window._workspace, window.canvas_view
    clock = window._sim_clock

    # ── a garden: one raised bed (so that there is geometry that must NOT be rebuilt) ─
    canvas.set_active_tool(ToolType.RAISED_BED)
    tool = canvas.tool_manager.active_tool
    tool.mouse_press(mouse_event, QPointF(400.0, 300.0))
    tool.mouse_move(mouse_event, QPointF(700.0, 500.0))
    tool.mouse_release(mouse_event, QPointF(700.0, 500.0))
    window._on_sun_sim_datetime(datetime(2026, 6, 21, 12, 0))

    # ── 3D is opened: no location yet, so the documented fallback sun ────────
    workspace.set_mode(VIEW3D)
    qtbot.waitUntil(lambda: bool(engines.hosts) and bool(engines.host.looks), timeout=5000)
    host, sink, look, controller = engines.host, engines.sink, workspace.look, workspace.controller
    assert look is not None and controller is not None and engines.modes == [False]
    assert sink.sun == NO_LOCATION_SUN
    assert host.looks == [look_for(NO_LOCATION_SUN, "high")]
    assert host.skies == [look_for(NO_LOCATION_SUN, "high").sky], "the first sky: with the first sun"
    assert host.wind == ["run"], "shown, motion not reduced: the wind runs"
    assert (look.quality, look.preset, look.sky_light) == ("high", "high", True)
    builds = controller.sync.build_count
    framed, placed = workspace.camera.pose, host.cameras[-1]

    # ── the garden gets a location: a real sun, from core/solar ──────────────
    window._project_manager.set_location(dict(BERLIN))
    _settle(qtbot)
    here = _sun_at(clock, clock.wall)
    assert sink.sun == here and host.looks[-1] == look_for(here, "high")

    # ── the toolbar's time, through sunrise, noon, sunset and night ──────────
    script = [
        ("sunrise", _moment(clock, JUNE, lambda now, soon: 1.0 < now.elevation_deg < 5.0
                            and soon.elevation_deg > now.elevation_deg)),
        ("noon", _moment(clock, JUNE, lambda now, soon: now.elevation_deg > 55.0
                         and soon.elevation_deg < now.elevation_deg)),
        ("sunset", _moment(clock, JUNE, lambda now, soon: 4.0 < now.elevation_deg < 6.0
                           and soon.elevation_deg < now.elevation_deg)),
        ("night", _moment(clock, JUNE, lambda now, soon: now.elevation_deg < -6.0
                          and soon.elevation_deg < now.elevation_deg)),
    ]
    sink.clear_calls()
    snapshots, reconciles = controller.snapshot_count, controller.reconcile_count
    unannounced = controller.unannounced_changes
    seen: dict[str, Any] = {}
    for name, wall in script:
        skies_before, shown_sky = len(host.skies), look.sky
        window._on_sun_sim_datetime(wall)
        _settle(qtbot)
        sun = _sun_at(clock, wall)
        expected = look_for(sun, "high")
        # the light: the pipeline told the sink the plan's own sun …
        assert sink.sun == sun, name
        assert sink.ops() == [BEGIN, SUN, COMMIT], f"{name}: a time change is light only"
        sink.clear_calls()
        # … the look handed to the engine is the look of exactly that sun …
        assert host.looks[-1] == expected, name
        assert look.look == expected
        # … and the sky followed: one rebuild for one noticeable move
        assert sky_is_stale(shown_sky, expected.sky), name
        assert len(host.skies) == skies_before + 1 and host.skies[-1] == expected.sky, name
        seen[name] = expected
    assert [seen[name].night for name, _wall in script] == [False, False, False, True]
    # the light's direction: by day minus the sun vector and no moon in the look;
    # at night the sun is down (the sink was told so) and the look states the moon
    for name in ("sunrise", "noon", "sunset"):
        assert seen[name].moon_travel_scene is None
    assert sink.sun is not None and not sink.sun.is_up
    assert seen["night"].moon_travel_scene == moon_travel_scene()
    assert sink.sun.light_travel_scene == pytest.approx(
        tuple(-c for c in sink.sun.direction_scene))
    # moods: the low sun is warm and exposed up, noon is neutral, night is moonlight
    assert seen["sunrise"].mood.exposure > seen["noon"].mood.exposure
    assert seen["noon"].mood.sun_color == "#fff1dc" and seen["night"].mood.sun_color == "#8ea4d6"
    assert seen["sunset"].mood.sun_color != seen["noon"].mood.sun_color

    # ── a time change below the threshold: the look follows, the sky stays ───
    window._on_sun_sim_datetime(script[1][1])       # noon again
    _settle(qtbot)
    sink.clear_calls()
    skies = len(host.skies)
    a_minute_later = script[1][1] + timedelta(minutes=1)
    window._on_sun_sim_datetime(a_minute_later)
    _settle(qtbot)
    nudged = _sun_at(clock, a_minute_later)
    assert not sky_is_stale(look.sky, look_for(nudged, "high").sky)
    assert len(host.skies) == skies, "a quarter of a degree: zero rebuilds"
    assert sink.sun == nudged and sink.ops() == [BEGIN, SUN, COMMIT]
    # a time of day re-lights the garden; the look never snapshots the plan. A snapshot
    # after a time change can only be the workspace's quiet-time check (the 2D shadows
    # repaint), and it finds nothing to change
    qtbot.waitUntil(lambda: controller.idle, timeout=5000)
    assert controller.snapshot_count - snapshots == controller.reconcile_count - reconciles
    assert controller.unannounced_changes == unannounced

    # ── a date change: the same wall time in December ────────────────────────
    sink.clear_calls()
    skies = len(host.skies)
    december = datetime.combine(DECEMBER, a_minute_later.time())
    window._on_sun_sim_datetime(december)
    _settle(qtbot)
    winter = _sun_at(clock, december)
    assert sink.sun == winter and host.looks[-1] == look_for(winter, "high")
    assert len(host.skies) == skies + 1, "the winter sun stands somewhere else: one rebuild"
    assert clock.plan_date == DECEMBER
    assert [op for op in sink.ops() if op[0] not in ("begin", "commit", "set_sun")] == [], \
        "the bed has no growth: a date change moved the light and nothing else"

    # ── Preferences: another quality, then reduced motion ────────────────────
    sink.clear_calls()
    looks, skies, wind = len(host.looks), len(host.skies), len(host.wind)
    _preferences(window, monkeypatch, quality="low")       # Edit → Preferences → Save
    assert host.looks[looks:] == [look_for(winter, "low")], "a preset change is ONE look call"
    assert (look.quality, look.preset) == ("low", "low")
    assert len(host.skies) == skies and len(host.wind) == wind
    shown = PreferencesDialog(window)
    qtbot.addWidget(shown)
    assert shown._view3d_quality_combo.currentData() == "low", "the dialog shows what is stored"
    _preferences(window, monkeypatch, reduced_motion=True)
    assert host.wind[wind:] == ["rest"] and not look.animating, "reduced motion stops the wind"
    assert len(host.looks) == looks + 1, "reduced motion is not a look"

    # ── hide and show: nothing ticks, nothing is rebuilt ─────────────────────
    looks, skies, wind = len(host.looks), len(host.skies), len(host.wind)
    workspace.set_mode(PLAN)
    assert not look._sky_timer.isActive() and not look._auto_timer.isActive()
    workspace.set_mode(VIEW3D)
    _settle(qtbot)
    assert (len(host.looks), len(host.skies), len(host.wind)) == (looks, skies, wind), \
        "the same sun, the same settings: showing the view again tells the engine nothing"
    _preferences(window, monkeypatch, reduced_motion=False)
    assert host.wind[wind:] == ["run"] and look.animating
    workspace.set_mode(PLAN)
    assert host.wind[wind:] == ["run", "stop"], "hidden: the wind's clock stops where it is"
    workspace.set_mode(VIEW3D)
    _settle(qtbot)
    assert host.wind[wind:] == ["run", "stop", "run"]

    # ── and nothing but look calls happened ──────────────────────────────────
    assert sink.ops() == [], "no pipeline call since the date change"
    assert controller.sync.build_count == builds, "not one builder ran after the first pass"
    assert workspace.camera.pose is framed, "no look, sky, preset or wind call moved the camera"
    assert all(call == placed for call in host.cameras[host.cameras.index(placed):]), \
        "showing the view again re-states the same camera; nothing else touched it"
    assert host.frames_taken == [], "the look never took a frame from the live view"
    assert host.releases == 0
    assert sink.state() == controller.sync.expected_state()

    # ── closing the app: the look stops with the engine ──────────────────────
    assert window.close() is True
    assert workspace.look is None and host.closed is True
    assert not look._sky_timer.isActive() and not look._auto_timer.isActive()


def test_compatibility_mode_gets_the_look_without_a_sky(app3d, qtbot, tmp_path: Path,
                                                        monkeypatch) -> None:
    """Gate G8's wiring: a workspace that starts in software mode hands its host looks
    and never a sky — the light probe that costs seconds there is never created."""
    window, engines = app3d
    workspace = window._workspace
    guard = Init3DGuard(tmp_path / "compat", is_running=lambda _pid: False)
    guard.use_software_next_time()
    workspace._guard = Init3DGuard(tmp_path / "compat", is_running=lambda _pid: False)
    window._project_manager.set_location(dict(BERLIN))
    workspace.set_mode(VIEW3D)
    qtbot.waitUntil(lambda: bool(engines.hosts) and bool(engines.host.looks), timeout=5000)
    host, look = engines.host, workspace.look
    assert engines.modes == [True] and look is not None and look.sky_light is False
    clock = window._sim_clock
    for hour in (6, 12, 18, 23):
        window._on_sun_sim_datetime(datetime(2026, 6, 21, hour, 0))
        _settle(qtbot)
        sun = _sun_at(clock, datetime(2026, 6, 21, hour, 0))
        assert host.looks[-1] == look_for(sun, look.preset)
        assert host.looks[-1].plain_sky == host.looks[-1].fog_color
    assert host.skies == [], "no sky texture, so no light probe, in compatibility mode"
    assert len(host.looks) >= 4
    # review P0: no wind in compatibility mode — an animated view renders continuously
    # (1,351 % of one core on WARP); hidden and shown again, still no wind
    workspace.set_mode(PLAN)
    workspace.set_mode(VIEW3D)
    _settle(qtbot)
    assert "run" not in host.wind and not look.animating
    assert look.software and look.preset == look.quality == "high", "a chosen preset is used"
    looks = len(host.looks)
    _preferences(window, monkeypatch, quality="auto")
    assert look.preset == "low", "auto on a software adapter is low: no frames to measure"
    assert host.looks[looks:] == [look_for(_sun_at(clock, datetime(2026, 6, 21, 23, 0)), "low")]
    assert "run" not in host.wind


def test_the_3d_settings_are_always_offered_and_saved(qtbot, look_settings) -> None:
    """Preferences → 3D View: shown and saved like every other group — since L1.9 every
    main window has the 3D workspace (until then a hidden group never rewrote the
    store)."""
    look_settings.view3d_quality = "medium"
    look_settings.view3d_reduced_motion = True
    shown = PreferencesDialog()
    qtbot.addWidget(shown)
    assert not shown._view3d_quality_combo.parentWidget().isHidden()
    assert shown._view3d_quality_combo.currentData() == "medium"
    assert shown._view3d_reduced_motion_check.isChecked()
    assert [shown._view3d_quality_combo.itemData(i) for i in range(5)] == [
        "auto", "low", "medium", "high", "ultra"]
    shown._view3d_quality_combo.setCurrentIndex(0)
    shown._view3d_reduced_motion_check.setChecked(False)
    shown._save_and_accept()
    assert (look_settings.view3d_quality, look_settings.view3d_reduced_motion) == ("auto", False)


def test_the_main_windows_preferences_offer_the_3d_view_group(
        qtbot, monkeypatch: pytest.MonkeyPatch, look_settings) -> None:  # noqa: ARG001
    """The Edit → Preferences action of the real window: the dialog it opens shows the
    3D View group."""
    opened: list[PreferencesDialog] = []

    def record(self: PreferencesDialog) -> int:
        opened.append(self)
        return 0

    monkeypatch.setattr(PreferencesDialog, "exec", record)
    window = GardenPlannerApp()
    qtbot.addWidget(window)
    window._on_preferences()
    assert not opened[-1]._view3d_quality_combo.parentWidget().isHidden()
    window.close()
