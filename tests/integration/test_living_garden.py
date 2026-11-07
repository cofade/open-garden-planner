"""The living garden end to end (Phase 17 L5, #389, ADR-070) — §8.10's integration test.

What a user does, through the real widgets:

- L5.1: the Plan & Sun toolbar's Animate plays the DAY (the time of day, the plan date
  stays) or the YEAR (the plan date, the time stays) at three speeds — every step a
  write of the ONE sim clock, so the 2D overlay and the 3D view follow it;
- L5.2: the 3D strip's Weather menu picks clear, partly cloudy, overcast, rain or snow — the look the
  engine is told is the living look of that weather, a new weather's sky is built at
  once, and the "Wildlife and Falling Leaves" switch reaches the engine;
- L5.3: "Today's Weather" follows the app's own forecast, ONLY while the plan date is
  today, and says why it shows clear otherwise;
- an Analyze drape on the ground pauses the weather (its colours read as its legend's),
  and the Weather button says so;
- the garden's life: the Plant Forge's phenology of the plan's own plants reaches the
  engine as butterflies at a lavender in flower in June and falling leaves under an oak
  turning in October — through the workspace's production Plant Forge, not a hand-made
  buffer (senior review: nothing else drove that path);
- L5.4: Garden Light and String Lights are tools and gallery objects; in 3D their bulbs
  glow and the nearest lamps light (the host is told where).

The engine is replaced at the workspace's seam (``Bench``, ``FakeHost``): the frames
are the render tier's (``test_living_garden_render.py``).
"""

from __future__ import annotations

import threading
from datetime import date, datetime, time, timedelta
from typing import Any

import numpy as np
import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType, get_valid_types_for_shape
from open_garden_planner.core.playback import PlaybackMode
from open_garden_planner.core.scene3d.weather import TODAY, WEATHER_CHOICES, living_look
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from tests.integration.test_view3d_workspace_widget import Bench

BERLIN = {"latitude": 52.52, "longitude": 13.405}
SPLIT = WorkspaceMode.SPLIT


# ── L5.1: playback through the one clock ─────────────────────────────────────


@pytest.fixture
def win(qtbot, monkeypatch):
    get_settings().show_welcome_on_startup = False
    app = GardenPlannerApp()
    qtbot.addWidget(app)
    monkeypatch.setattr(app, "_confirm_discard_changes", lambda: True)
    app._sim_clock.set_datetime(datetime(2026, 6, 21, 12))
    app._project_manager.set_location(dict(BERLIN))
    app._project_manager.mark_clean()
    yield app


def test_animate_plays_the_day_then_the_year_through_the_clock(win, qtbot) -> None:
    bar, clock = win._sun_toolbar, win._sim_clock
    days: list[date] = []
    clock.date_changed.connect(days.append)
    # the default: the day, at Phase 14's speed — the date never moves
    assert bar.playback_mode is PlaybackMode.DAY and bar.playback_speed == "normal"
    bar.set_animation_active(True)
    for _ in range(3):
        bar._on_animate_tick()
    assert (clock.plan_date, clock.time_of_day) == (date(2026, 6, 21), time(12, 30))
    assert days == [], "a day's playback never fires date_changed"
    # the year, chosen in the button's menu: the date moves, the time stays
    menu = bar._animate_button.menu()
    assert menu is not None
    by_text = {action.text(): action for action in menu.actions()}
    by_text[bar.tr("The Year")].trigger()
    by_text[bar.tr("Fast")].trigger()
    assert bar.playback_mode is PlaybackMode.YEAR and bar.playback_speed == "fast"
    assert "year" in bar._animate_button.toolTip()
    bar._on_animate_tick()
    bar._on_animate_tick()
    assert (clock.plan_date, clock.time_of_day) == (date(2026, 7, 5), time(12, 30))
    assert days == [date(2026, 6, 28), date(2026, 7, 5)]
    # the toolbar SHOWS what the clock holds (it wrote through the clock, not itself)
    assert bar.current_wall_datetime() == datetime(2026, 7, 5, 12, 30)
    # and at the end of the year it wraps into the same year
    clock.set_date(date(2026, 12, 29))
    bar._on_animate_tick()
    assert clock.plan_date == date(2026, 1, 5)
    bar.stop_animation()
    assert not bar.animation_active


def test_the_animate_timer_drives_the_year(win, qtbot) -> None:
    """The real QTimer, not a hand-called tick."""
    bar, clock = win._sun_toolbar, win._sim_clock
    bar.set_playback_mode(PlaybackMode.YEAR)
    bar.set_playback_speed("slow")
    start = clock.plan_date
    bar.set_animation_active(True)
    qtbot.waitUntil(lambda: clock.plan_date >= start + timedelta(days=2), timeout=3000)
    bar.stop_animation()
    assert clock.time_of_day == time(12, 0)


# ── L5.2 / L5.3: the weather in the 3D strip ─────────────────────────────────


@pytest.fixture
def bench(canvas, qtbot, tmp_path) -> Bench:
    made = Bench(canvas, qtbot, tmp_path, location=dict(BERLIN))
    made.workspace.set_mode(SPLIT)
    made.settle()
    return made


def _menu_actions(bench: Bench) -> dict[str, Any]:
    button = bench.workspace.living.button
    assert button is not None and button.isVisible(), "the Weather button is in the 3D strip"
    menu = button.menu()
    assert menu is not None
    return {action.text(): action for action in menu.actions() if action.text()}


def test_the_weather_menu_paints_the_look_the_engine_is_told(bench: Bench) -> None:
    host, look = bench.host, bench.workspace.look
    assert look is not None and host.looks, "the first pass gave the engine a look"
    sun = bench.workspace.controller.sync.sun
    assert host.looks[-1] == living_look(sun, look.preset, "clear")
    actions = _menu_actions(bench)
    for weather, text in (("rain", "Rain"), ("snow", "Snow"), ("overcast", "Overcast")):
        skies = len(host.skies)
        actions[text].trigger()
        assert look.weather == weather and look.weather_choice == weather
        assert host.looks[-1] == living_look(sun, look.preset, weather)
        assert host.looks[-1].atmosphere.weather == weather
        assert len(host.skies) == skies + 1, "a new weather's sky is built at once"
        assert host.skies[-1].cloud > 0.0
        assert text in bench.workspace.living.button.text()
    actions["Clear"].trigger()
    assert host.looks[-1] == living_look(sun, look.preset, "clear")
    assert "Mood:" in bench.workspace.living.button.toolTip()


@pytest.mark.parametrize("mode", ["light", "dark"])
def test_the_strip_s_menu_buttons_read_as_buttons(bench: Bench, qtbot, mode: str) -> None:
    """Owner's manual test of L5: "Wetter: Klar" was not found as a button. A text
    button that only opens a menu got its arrow drawn UNDER its last letter, and read
    as a label; the Weather and the Analyze buttons now carry ``menuChevron``, and the
    theme gives that arrow room of its own beside the text."""
    from PyQt6.QtWidgets import QMenu, QToolButton, QWidget

    from open_garden_planner.ui.theme import ThemeMode, generate_stylesheet

    strip = bench.workspace.living.button.parentWidget()
    buttons = {b.text(): b for b in strip.findChildren(QToolButton) if b.menu() is not None}
    weather = bench.workspace.living.button
    analyze = buttons.get("Analyze")
    assert analyze is not None, sorted(buttons)
    for button in (weather, analyze):
        assert button.property("menuChevron") is True, button.text()
    # the theme's rule is what makes the property count: the arrow takes room of its own
    host = QWidget()
    qtbot.addWidget(host)
    host.setStyleSheet(generate_stylesheet(ThemeMode(mode)))
    widths = {}
    for chevron in (False, True):
        probe = QToolButton(host)
        probe.setText("Weather: Clear")
        probe.setAutoRaise(True)
        probe.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        probe.setMenu(QMenu(probe))
        probe.setProperty("menuChevron", chevron)
        probe.ensurePolished()
        widths[chevron] = probe.sizeHint().width()
    assert widths[True] >= widths[False] + 10, widths


def test_the_places_hemisphere_reaches_the_look(bench: Bench) -> None:
    """Where the place's noon stands is the look's to know (senior review of L5): a
    garden south of the equator fades its morning dew before a noon due north, and its
    fireflies before a midnight due south (``weather.noon_azimuth``)."""
    look, host = bench.workspace.look, bench.host
    assert look is not None and look.southern is False, "Berlin"
    bench.location = {"latitude": -33.87, "longitude": 151.21}
    bench.workspace.location_changed(bench.location)
    bench.settle()
    assert look.southern is True
    sun = bench.workspace.controller.sync.sun
    assert host.looks[-1] == living_look(sun, look.preset, "clear", southern=True)
    bench.location = None
    bench.workspace.location_changed(None)
    bench.settle()
    assert look.southern is False, "no location: the phenology's northern default"


def test_the_life_switch_reaches_the_engine(bench: Bench) -> None:
    host = bench.host
    assert host.life[-1] is True, "a new engine starts with life on"
    _menu_actions(bench)["Wildlife and Falling Leaves"].trigger()
    assert host.life[-1] is False and not bench.workspace.living.life_enabled
    _menu_actions(bench)["Wildlife and Falling Leaves"].trigger()
    assert host.life[-1] is True


def test_todays_weather_follows_the_forecast_only_on_today(bench: Bench) -> None:
    look, clock = bench.workspace.look, bench.clock
    today = date.today()
    bench.workspace.set_weather_forecast(_place(BERLIN),
                                         ((today.isoformat(), 63), ("2000-01-01", 73)))
    _menu_actions(bench)["Today's Weather"].trigger()
    assert look.weather_choice == TODAY
    clock.set_date(today)
    bench.settle()
    assert look.weather == "rain" and bench.host.looks[-1].atmosphere.weather == "rain"
    assert "Today (Rain)" in bench.workspace.living.button.text()
    clock.set_date(date(2001, 6, 1))           # another date: a forecast says nothing of it
    bench.settle()
    assert look.weather == "clear" and bench.host.looks[-1].atmosphere.weather == "clear"
    assert "only while the plan date is today" in bench.workspace.living.button.toolTip()


class FakeWeather:
    """The weather service without the network — the rest is the app's own:
    the calendar's weather widget, its worker thread, its signals (the test is marked
    ``real_weather_worker``: the conftest otherwise replaces that thread with a mock). Each fetch is recorded
    and answers its own place's forecast (rain north of the equator, overcast south of
    it) once ``gate`` is open; ``fail`` answers nothing (a failed fetch)."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from open_garden_planner.services.weather_service import DayForecast, WeatherForecast
        from open_garden_planner.ui.widgets import weather_widget

        self.fetches: list[tuple[float, float]] = []
        self.gate = threading.Event()
        self.gate.set()
        self.fail = False

        def fetch(lat: float, lon: float) -> WeatherForecast | None:
            self.fetches.append((lat, lon))
            self.gate.wait(10.0)
            if self.fail:
                return None
            code = 63 if lat > 0 else 3
            return WeatherForecast([DayForecast(date.today().isoformat(), 18.0, 9.0, 4.2, code)],
                                   "2026-11-02T08:00:00+00:00")

        service = type("Service", (), {"fetch_forecast": staticmethod(fetch)})()
        # the worker's own lookup: whatever a test left on the service singleton, this is it
        monkeypatch.setattr(weather_widget, "get_weather_service", lambda: service)


def _place(location: dict[str, float]) -> tuple[float, float]:
    return (location["latitude"], location["longitude"])


@pytest.mark.real_weather_worker
def test_todays_weather_asks_the_calendar_and_keeps_no_stale_forecast(win, monkeypatch, qtbot) -> None:
    """The app's seam (senior review of L5): choosing Today's Weather ASKS the Planting
    Calendar's weather widget for the forecast — with the calendar's tab hidden, the
    default —; the forecast it fetched reaches the 3D view; a failed fetch and a plan
    without a location leave no stale forecast behind."""
    weather = FakeWeather(monkeypatch)
    living, widget = win._workspace.living, win.calendar_view._weather
    today = date.today().isoformat()
    assert win._tab_widget.currentIndex() == 0, "the plan's tab: the calendar is hidden"
    living.actions[TODAY].trigger()
    qtbot.waitUntil(lambda: living.forecast == ((today, 63),), timeout=5000)
    assert weather.fetches == [_place(BERLIN)], "asked for the forecast, once"
    # When fresh forecast is held, picking Today's Weather re-emits and starts no fetch (#693)
    living.set_weather(TODAY)
    assert weather.fetches == [_place(BERLIN)], "fresh forecast: starts no fetch"
    # Invalidate held forecast to simulate a failed fetch
    win._forecast_holder.invalidate()
    win._project_manager.set_location(dict(BERLIN))
    weather.fail = True
    living.set_weather(TODAY)                      # asked again: this fetch fails
    qtbot.waitUntil(lambda: len(weather.fetches) == 2 and living.forecast == (), timeout=5000)
    weather.fail = False
    living.set_weather(TODAY)
    qtbot.waitUntil(lambda: living.forecast == ((today, 63),), timeout=5000)
    assert widget._worker is None, "the fetch is over"
    win._project_manager.set_location({**BERLIN, "frost_dates": {"last_spring_frost": "04-20"}})
    assert living.forecast == ((today, 63),), "the same place (a frost-date edit): it holds"
    assert widget._worker is None, "and nothing is fetched again"
    win._project_manager.set_location(None)
    assert living.forecast == (), "no place: the old forecast is forgotten"
    assert widget._worker is None and len(weather.fetches) == 3, "no location: nothing to fetch"


@pytest.mark.real_weather_worker
def test_picking_todays_weather_with_fresh_held_forecast_starts_no_thread_and_rebuilds_no_dashboard(
    win, monkeypatch, qtbot
) -> None:
    """Issue #693: When a fresh forecast for the plan's location is already held,
    picking Today's Weather in 3D re-emits synchronously, starting NO background
    worker thread and triggering NO dashboard rebuild on the hidden calendar tab."""
    from unittest.mock import MagicMock
    weather = FakeWeather(monkeypatch)
    living = win._workspace.living
    today = date.today().isoformat()
    assert win._tab_widget.currentIndex() == 0, "calendar tab is hidden"

    # 1. First pick fetches forecast
    living.actions[TODAY].trigger()
    qtbot.waitUntil(lambda: living.forecast == ((today, 63),), timeout=5000)
    assert len(weather.fetches) == 1
    assert win._forecast_holder.is_fresh()

    # 2. Switch away to clear weather
    living.actions["clear"].trigger()
    assert living.weather_choice == "clear"

    # 3. Instrument worker start and calendar dashboard rebuild
    fetch_started = MagicMock()
    monkeypatch.setattr(win._forecast_holder, "_start_fetch", fetch_started)
    dashboard_rebuild = MagicMock(wraps=win.calendar_view._rebuild_dashboard)
    monkeypatch.setattr(win.calendar_view, "_rebuild_dashboard", dashboard_rebuild)

    # 4. Pick Today's Weather again
    living.actions[TODAY].trigger()
    qtbot.waitUntil(lambda: living.forecast == ((today, 63),), timeout=5000)

    # 5. Assert 0 worker starts, 0 new fetches, 0 dashboard rebuilds
    assert len(weather.fetches) == 1, "no second network fetch started"
    assert fetch_started.call_count == 0, "no worker thread started"
    assert dashboard_rebuild.call_count == 0, "hidden calendar dashboard not rebuilt"
    assert win._tab_widget.currentIndex() == 0, "calendar remained hidden"


@pytest.mark.real_weather_worker
def test_a_place_change_off_todays_weather_cancels_the_old_places_fetch(win, monkeypatch,
                                                                        qtbot) -> None:
    """Senior review of L5, round 4 (observed): with the calendar's tab hidden and the 3D
    view NOT on Today's Weather, nobody moved the weather widget when the place changed,
    so the old place's late forecast landed on the new plan — labelled as the new place,
    then kept by a frost-date edit and shown when Today's Weather was picked. The widget
    now follows every place at once (``PlantingCalendarView.follow_location``), and the
    3D view takes a forecast only for the plan's own place (the producer says where)."""
    sydney = {"latitude": -33.87, "longitude": 151.21}
    weather = FakeWeather(monkeypatch)
    living, widget = win._workspace.living, win.calendar_view._weather
    alerts: list[object] = []
    win.calendar_view.frost_alerts_ready.connect(alerts.append)
    today = date.today().isoformat()
    try:
        weather.gate.clear()                       # Berlin's fetch hangs on the network
        living.actions[TODAY].trigger()
        qtbot.waitUntil(lambda: weather.fetches == [_place(BERLIN)], timeout=5000)
        in_flight = widget._worker
        assert in_flight is not None
        living.actions["clear"].trigger()          # off Today's Weather …
        win._project_manager.set_location(dict(sydney))   # … the place changes
        assert widget.place() == _place(sydney), "the hidden widget moved at once"
        weather.gate.set()                         # Berlin answers late
        qtbot.waitUntil(in_flight.isFinished, timeout=5000)
        qtbot.wait(50)
        assert living.forecast == () and widget.forecast() is None, "Berlin's never landed"
        assert alerts == [], "no frost alerts against Berlin for a plan in Sydney"
        win._project_manager.set_location({**sydney, "frost_dates": {"last_spring_frost": "09-20"}})
        assert living.forecast == ()
        living.actions[TODAY].trigger()
        qtbot.waitUntil(lambda: living.forecast == ((today, 3),), timeout=5000)
        assert weather.fetches == [_place(BERLIN), _place(sydney)]
        # and a forecast for another place than the plan's is dropped, whoever sends it
        win.calendar_view.forecast_days_ready.emit(_place(BERLIN), ((today, 71),))
        assert living.forecast == ((today, 3),), "Berlin's forecast is not Sydney's"
    finally:
        weather.gate.set()


@pytest.mark.real_weather_worker
def test_a_new_or_opened_plan_never_follows_the_old_places_forecast(win, monkeypatch, qtbot,
                                                                     tmp_path) -> None:
    """File > New while the old place's fetch is still on its way, then Open of a plan
    at another place (senior review of L5, observed: the old place's forecast reached
    the 3D view, the calendar showed its strip without a location, and the new plan's
    frost alerts were computed against it). Through the app's own document paths."""
    sydney = {"latitude": -33.87, "longitude": 151.21}
    plan = tmp_path / "sydney.ogp"
    win._project_manager.set_location(dict(sydney))
    win._project_manager.save(win.canvas_scene, plan)
    win._project_manager.set_location(dict(BERLIN))
    weather = FakeWeather(monkeypatch)
    living, widget = win._workspace.living, win.calendar_view._weather
    alerts: list[object] = []
    win.calendar_view.frost_alerts_ready.connect(alerts.append)
    today = date.today().isoformat()
    try:
        weather.gate.clear()                       # Berlin's fetch hangs on the network
        living.actions[TODAY].trigger()
        qtbot.waitUntil(lambda: weather.fetches == [_place(BERLIN)], timeout=5000)
        in_flight = widget._worker
        assert in_flight is not None
        win._new_project_document(width_cm=2000, height_cm=2000)
        assert win._project_manager.location is None
        weather.gate.set()                         # … and answers after File > New
        qtbot.waitUntil(in_flight.isFinished, timeout=5000)
        qtbot.wait(50)                             # whatever it queued has been run
        assert living.forecast == (), "the old place's late forecast did not land"
        assert widget.forecast() is None and widget._strip.isHidden()
        assert alerts == [], "no frost alerts against another place's weather"
        assert weather.fetches == [_place(BERLIN)], "a plan without a location fetches nothing"

        win._project_manager.set_location(dict(BERLIN))
        qtbot.waitUntil(lambda: living.forecast == ((today, 63),), timeout=5000)
        win._load_project_file(str(plan))
        qtbot.waitUntil(lambda: living.forecast == ((today, 3),), timeout=5000)
        assert weather.fetches == [_place(BERLIN), _place(BERLIN), _place(sydney)], (
            "the open asked once, for the plan's own place — none for the old one first")
        assert (widget._lat, widget._lon) == _place(sydney)
    finally:
        weather.gate.set()


@pytest.mark.parametrize("drape", ["SHADOWS", "SUN_HOURS"])
def test_an_analyze_drape_pauses_the_weather(bench: Bench, drape: str) -> None:
    """Weather > Snow, then Analyze > a drape: the engine is told the sun's own look and
    the button says the weather is paused; Analyze > Nothing on the Ground brings the
    snow back (3D review of L5: snow washed the hours of sun to a pale lavender)."""
    from open_garden_planner.ui.view3d.analysis_modes import DrapeMode

    host, look, workspace = bench.host, bench.workspace.look, bench.workspace
    sun = workspace.controller.sync.sun
    _menu_actions(bench)["Snow"].trigger()
    assert host.looks[-1] == living_look(sun, look.preset, "snow")
    workspace.drape_actions[DrapeMode[drape]].trigger()
    assert workspace.living.analysing and look.weather_paused
    assert host.looks[-1] == living_look(sun, look.preset, "clear", dew=False)
    assert "Snow" in workspace.living.button.text()
    assert "(paused while analysing)" in workspace.living.button.text()
    workspace.drape_actions[DrapeMode.NONE].trigger()
    assert not workspace.living.analysing and not look.weather_paused
    assert host.looks[-1] == living_look(sun, look.preset, "snow")
    assert "paused" not in workspace.living.button.text()
    workspace.drape_actions[DrapeMode[drape]].trigger()
    assert "(paused while analysing)" in workspace.living.button.text()
    workspace.shutdown()            # the engine goes with the drape still on the ground …
    assert workspace.look is None
    assert "paused" not in workspace.living.button.text(), "… and so does the pause (P2)"


def test_every_weather_choice_has_its_menu_entry(bench: Bench) -> None:
    assert set(bench.workspace.living.actions) == set(WEATHER_CHOICES)
    texts = set(_menu_actions(bench))
    assert {"Clear", "Partly cloudy", "Overcast", "Rain", "Snow", "Today's Weather",
            "Wildlife and Falling Leaves"} <= texts


# ── the garden's life, from the Plant Forge to the engine ───────────────────


def _kinds(buffers: Any) -> set[str]:
    """The particle kinds an ambient buffer holds (its colour's alpha: ``int(a * 4)``)."""
    from open_garden_planner.core.scene3d.interleave import VERTEX_STRIDE

    if buffers is None or buffers.is_empty:
        return set()
    rows = np.frombuffer(buffers.vertex_data, dtype="<f4").reshape(-1, VERTEX_STRIDE // 4)
    names = ("leaf", "butterfly", "firefly", "bulb")
    return {names[int(code * 4)] for code in np.unique(rows[:, 9])}


def test_the_gardens_life_goes_from_the_plant_forge_to_the_engine(qtbot, monkeypatch,
                                                                   tmp_path) -> None:
    """A lavender and an oak drawn on the plan; 3D opened with the PRODUCTION Plant Forge
    (the documented seam of ``test_plant_forge_workspace``). In June the lavender flowers:
    butterflies reach the engine. In October the oak is turning: falling leaves. In January
    neither. Every buffer goes through ``Workspace`` → ``ForgeWorker`` → ``season_sink`` →
    ``WorkspaceLivingCoordinator`` → ``host.set_ambient``."""
    from open_garden_planner.core.commands import CreateItemCommand
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.view3d import workspace as workspace_module
    from tests.integration.test_view3d_workspace import build_app3d, first_pass

    window, engines = build_app3d(qtbot, monkeypatch, tmp_path)
    workspace = window._workspace
    monkeypatch.setattr(workspace_module, "quick3d_engine", workspace.engine_factory)
    window._project_manager.set_location(dict(BERLIN))
    clock = window._sim_clock
    clock.set_datetime(datetime(2026, 6, 21, 12))
    for x, kind, species, height in ((500.0, ObjectType.SHRUB, "Lavender", 60.0),
                                     (1200.0, ObjectType.TREE, "Oak", 500.0)):
        item = CircleItem(x, 500.0, 80.0 if kind is ObjectType.SHRUB else 150.0,
                          object_type=kind, metadata={"height_cm": height})
        item.plant_species = species
        window.canvas_view.command_manager.execute(
            CreateItemCommand(window.canvas_scene, item, species))
    workspace.set_mode(WorkspaceMode.SPLIT)
    first_pass(workspace, qtbot)
    assert workspace._forge_worker is not None, "the production Plant Forge"
    host = engines.host

    def life_on(day: date) -> set[str]:
        sent = len(host.ambient)
        clock.set_date(day)
        qtbot.waitUntil(lambda: len(host.ambient) > sent and bool(host.seasons), timeout=10000)
        return _kinds(host.ambient[-1])

    qtbot.waitUntil(lambda: bool(host.ambient), timeout=10000)
    assert "butterfly" in _kinds(host.ambient[-1]), "June: butterflies at the lavender"
    assert "leaf" not in _kinds(host.ambient[-1])
    assert "leaf" in life_on(date(2026, 10, 20)), "October: the oak drops its leaves"
    assert life_on(date(2026, 1, 15)) == set(), "January: no butterflies, no leaves"
    assert workspace.living.ambient_sent >= 3
    window.close()


def test_the_lights_are_read_again_only_when_a_pass_touches_one(qtbot, monkeypatch) -> None:
    """Reading every record for its lights costs ~40 ms for 500 lights — more than
    ADR-069's slice — so a pass reads them only when it touched a light, removed one, or
    reset the sync (senior review of L5)."""
    from PyQt6.QtWidgets import QWidget

    from open_garden_planner.core.scene3d.scene_diff import SceneDiff
    from open_garden_planner.ui.view3d import workspace_living
    from open_garden_planner.ui.view3d.sync_controller import TickReport
    from tests.integration.test_view3d_workspace_widget import FakeHost
    from tests.unit.test_scene3d_particles import lantern, plant

    reads: list[int] = []
    real = workspace_living.lamp_sources
    monkeypatch.setattr(workspace_living, "lamp_sources",
                        lambda records: (reads.append(1), real(records))[1])
    records = {"lamp": lantern("lamp"), "oak": plant("oak")}
    parent = QWidget()
    qtbot.addWidget(parent)
    host = FakeHost(False)
    living = workspace_living.WorkspaceLivingCoordinator(
        get_host=lambda: host, get_look=lambda: None, get_records=lambda: records,
        get_location=lambda: None, parent=parent)

    def passed(recovered: bool = False, **changes: tuple[str, ...]) -> int:
        living.on_applied(TickReport(changes=SceneDiff(**changes), snapshot=True,
                                     records=len(records), snapshot_ms=0.0, apply_ms=0.0,
                                     recovered=recovered))
        return len(reads)

    assert passed(added=("lamp", "oak")) == 1, "the first full pass reads them"
    assert host.lamps[-1], "and the lamp lights"
    assert passed(transform=("oak",)) == 1, "a tree moved: no light touched"
    assert passed() == 1, "an empty pass"
    assert passed(transform=("lamp",)) == 2, "the lamp moved"
    records["lamp2"] = lantern("lamp2", east=900.0)
    assert passed(added=("lamp2",)) == 3, "a light added after the first read"
    assert len(host.lamps[-1]) == 2, "and it lights too"
    del records["lamp"], records["lamp2"]
    assert passed(removed=("lamp", "lamp2")) == 4, "the lamps are gone"
    assert host.lamps[-1] == [], "and so is their light"
    assert passed(recovered=True) == 5, "a reset sync reads them again"


# ── L5.4: garden lights ──────────────────────────────────────────────────────


def test_garden_lights_are_drawn_with_their_tools_and_light_the_3d_garden(
        bench: Bench, qtbot) -> None:
    """Pick the tool, draw — the lamp is an item of its kind; in 3D its bulbs glow and
    the nearest lamps light (the host is told where)."""
    from unittest.mock import MagicMock

    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    from open_garden_planner.core.scene3d.lights import LAMP_SLOTS

    event = MagicMock(spec=QMouseEvent)
    event.button.return_value = Qt.MouseButton.LeftButton
    event.buttons.return_value = Qt.MouseButton.LeftButton
    event.modifiers.return_value = Qt.KeyboardModifier.NoModifier
    view = bench.view
    assert ObjectType.GARDEN_LIGHT in get_valid_types_for_shape("circle")
    # a string of lights is a LINE (owner's manual test of L5): offered on lines only
    assert ObjectType.STRING_LIGHTS in get_valid_types_for_shape("polyline")
    assert ObjectType.STRING_LIGHTS not in get_valid_types_for_shape("rectangle")
    view.set_active_tool(ToolType.GARDEN_LIGHT)
    tool = view.tool_manager.active_tool
    assert tool is not None and tool._object_type is ObjectType.GARDEN_LIGHT
    tool.mouse_press(event, QPointF(300, 300))
    tool.mouse_press(event, QPointF(320, 300))
    view.set_active_tool(ToolType.STRING_LIGHTS)
    tool = view.tool_manager.active_tool
    assert tool is not None and tool._object_type is ObjectType.STRING_LIGHTS
    for point in (QPointF(500, 400), QPointF(700, 440), QPointF(900, 400)):   # three posts
        tool.mouse_press(event, point)
    tool.mouse_double_click(event, QPointF(900, 400))
    kinds = {getattr(item, "object_type", None) for item in bench.scene.items()}
    assert {ObjectType.GARDEN_LIGHT, ObjectType.STRING_LIGHTS} <= kinds
    from open_garden_planner.ui.canvas.items import PolylineItem

    (drawn,) = [item for item in bench.scene.items()
                if getattr(item, "object_type", None) is ObjectType.STRING_LIGHTS]
    assert isinstance(drawn, PolylineItem) and drawn.point_count == 3
    qtbot.waitUntil(lambda: bool(bench.host.lamps) and len(bench.host.lamps[-1]) == 2, timeout=5000)
    lit = bench.host.lamps[-1]
    # where each light stands is the builder's own point, posed like its Model
    from open_garden_planner.core.scene3d.lights import lamp_sources

    records = bench.workspace.controller.sync.records.values()
    expected = sorted(source.light for source in lamp_sources(records))
    assert sorted(lit) == pytest.approx(expected), "they light from under their lamps"
    assert len(lit) <= LAMP_SLOTS
    assert bench.host.ambient and not bench.host.ambient[-1].is_empty, "their bulbs glow"


@pytest.mark.real_weather_worker
def test_stale_frost_alerts_cleared_on_new_plan_cleared_location_and_failed_fetch(win, monkeypatch, qtbot) -> None:
    """Issue #694: stale frost alerts must not survive File > New, a cleared location,
    or a failed fetch across the 4 places (badge, dashboard, Tasks tab, agent)."""
    from datetime import date

    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.services.weather_service import DayForecast, WeatherForecast
    from open_garden_planner.ui.canvas.items import CircleItem
    from open_garden_planner.ui.widgets import weather_widget

    def add_tender_plant():
        plant = CircleItem(100, 100, 20, object_type=ObjectType.PERENNIAL)
        plant.frost_protection_needed = True
        win.canvas_scene.addItem(plant)
        return plant

    add_tender_plant()

    weather_holder = {"fail": False, "min_c": -2.0}

    def fetch(lat: float, lon: float) -> WeatherForecast | None:
        if weather_holder["fail"]:
            return None
        return WeatherForecast([DayForecast(date.today().isoformat(), 5.0, weather_holder["min_c"], 0.0, 0)],
                               "2026-11-02T08:00:00+00:00")

    service = type("Service", (), {"fetch_forecast": staticmethod(fetch)})()
    monkeypatch.setattr(weather_widget, "get_weather_service", lambda: service)

    # 1. Fetch with location -> frost alerts populate
    win._project_manager.set_location(dict(BERLIN))
    win.calendar_view.refresh()
    qtbot.waitUntil(lambda: len(win.calendar_view.current_frost_alerts) > 0, timeout=5000)

    assert len(win.calendar_view.current_frost_alerts) > 0
    assert win._frost_badge_state[0] > 0
    assert len(win.tasks_view._frost_alerts) > 0
    assert len(win._agent_frost_alerts) > 0

    # 2. Clear location -> all 4 cleared
    win._project_manager.set_location(None)
    qtbot.wait(100)
    assert win.calendar_view.current_frost_alerts == []
    assert win._frost_badge_state == (0, "")
    assert not win._frost_badge.isVisible()
    assert win.tasks_view._frost_alerts == []
    assert win._agent_frost_alerts == []

    # 3. Restore alerts, then File > New -> all 4 cleared
    win._project_manager.set_location(dict(BERLIN))
    win.calendar_view.refresh()
    qtbot.waitUntil(lambda: len(win.calendar_view.current_frost_alerts) > 0, timeout=5000)
    assert len(win.calendar_view.current_frost_alerts) > 0

    win._new_project_document(width_cm=1000, height_cm=1000)
    qtbot.wait(100)
    assert win.calendar_view.current_frost_alerts == []
    assert win._frost_badge_state == (0, "")
    assert not win._frost_badge.isVisible()
    assert win.tasks_view._frost_alerts == []
    assert win._agent_frost_alerts == []

    # 4. Plant and set location again, but fetch fails -> all 4 cleared
    add_tender_plant()
    win._project_manager.set_location(dict(BERLIN))
    win.calendar_view.refresh()
    qtbot.waitUntil(lambda: len(win.calendar_view.current_frost_alerts) > 0, timeout=5000)

    weather_holder["fail"] = True
    win.calendar_view.refresh()
    qtbot.waitUntil(lambda: len(win.calendar_view.current_frost_alerts) == 0, timeout=5000)
    assert win.calendar_view.current_frost_alerts == []
    assert win._frost_badge_state == (0, "")
    assert not win._frost_badge.isVisible()
    assert win.tasks_view._frost_alerts == []
    assert win._agent_frost_alerts == []
