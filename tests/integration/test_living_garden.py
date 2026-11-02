"""The living garden end to end (Phase 17 L5, #389, ADR-070) — §8.10's integration test.

What a user does, through the real widgets:

- L5.1: the Plan & Sun toolbar's Animate plays the DAY (the time of day, the plan date
  stays) or the YEAR (the plan date, the time stays) at three speeds — every step a
  write of the ONE sim clock, so the 2D overlay and the 3D view follow it;
- L5.2: the 3D strip's Weather menu picks clear, overcast, rain or snow — the look the
  engine is told is the living look of that weather, a new weather's sky is built at
  once, and the "Wildlife and Falling Leaves" switch reaches the engine;
- L5.3: "Today's Weather" follows the app's own forecast, ONLY while the plan date is
  today, and says why it shows clear otherwise;
- an Analyze drape on the ground pauses the weather (its colours read as its legend's),
  and the Weather button says so;
- L5.4: Garden Light and String Lights are tools and gallery objects; in 3D their bulbs
  glow and the nearest lamps light (the host is told where).

The engine is replaced at the workspace's seam (``Bench``, ``FakeHost``): the frames
are the render tier's (``test_living_garden_render.py``).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

import pytest

from open_garden_planner.app.application import GardenPlannerApp
from open_garden_planner.app.settings import get_settings
from open_garden_planner.core.object_types import ObjectType, get_valid_types_for_shape
from open_garden_planner.core.playback import PlaybackMode
from open_garden_planner.core.scene3d.weather import TODAY, WEATHER_CHOICES, living_look
from open_garden_planner.core.tools.base_tool import ToolType
from open_garden_planner.ui.view3d.workspace import WorkspaceMode
from tests.integration.test_view3d_workspace_widget import Bench, FakeHost

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
    qtbot.waitUntil(lambda: clock.plan_date >= date(start.year, start.month, start.day + 2), timeout=3000)
    bar.stop_animation()
    assert clock.time_of_day == time(12, 0)


# ── L5.2 / L5.3: the weather in the 3D strip ─────────────────────────────────


class LivingHost(FakeHost):
    """The stand-in host, and what the living garden tells it."""

    def __init__(self, prefer_software: bool) -> None:
        super().__init__(prefer_software)
        self.ambient: list[Any] = []
        self.lamps: list[list[tuple[float, float, float, float]]] = []
        self.life: list[bool] = []
        self.seasons: list[Any] = []

    def set_ambient(self, buffers: Any) -> None:
        self.ambient.append(buffers)

    def set_lamps(self, lamps: list[tuple[float, float, float, float]]) -> None:
        self.lamps.append(list(lamps))

    def set_life_enabled(self, enabled: bool) -> None:
        self.life.append(bool(enabled))

    def set_plant_seasons(self, states: Any) -> None:
        self.seasons.append(states)


class LivingBench(Bench):
    def _factory(self, prefer_software: bool) -> tuple[Any, Any]:
        from open_garden_planner.core.scene3d import RecordingSink

        self.factory_calls.append(prefer_software)
        host, sink = LivingHost(prefer_software), RecordingSink()
        self.hosts.append(host)
        self.sinks.append(sink)
        return host, sink


@pytest.fixture
def bench(canvas, qtbot, tmp_path) -> LivingBench:
    made = LivingBench(canvas, qtbot, tmp_path, location=dict(BERLIN))
    made.workspace.set_mode(SPLIT)
    made.settle()
    return made


def _menu_actions(bench: LivingBench) -> dict[str, Any]:
    button = bench.workspace.living.button
    assert button is not None and button.isVisible(), "the Weather button is in the 3D strip"
    menu = button.menu()
    assert menu is not None
    return {action.text(): action for action in menu.actions() if action.text()}


def test_the_weather_menu_paints_the_look_the_engine_is_told(bench: LivingBench) -> None:
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


def test_the_life_switch_reaches_the_engine(bench: LivingBench) -> None:
    host = bench.host
    assert host.life[-1] is True, "a new engine starts with life on"
    _menu_actions(bench)["Wildlife and Falling Leaves"].trigger()
    assert host.life[-1] is False and not bench.workspace.living.life_enabled
    _menu_actions(bench)["Wildlife and Falling Leaves"].trigger()
    assert host.life[-1] is True


def test_todays_weather_follows_the_forecast_only_on_today(bench: LivingBench) -> None:
    look, clock = bench.workspace.look, bench.clock
    today = date.today()
    bench.workspace.set_weather_forecast(((today.isoformat(), 63), ("2000-01-01", 73)))
    _menu_actions(bench)["Today's Weather"].trigger()
    assert look.weather_choice == TODAY
    clock.set_date(today)
    bench.settle()
    assert look.weather == "rain" and bench.host.looks[-1].atmosphere.weather == "rain"
    assert "Today (Rain)" in bench.workspace.living.button.text()
    clock.set_date(date(2001, 6, 1))           # another date: a forecast says nothing of it
    bench.settle()
    assert look.weather == "clear" and bench.host.looks[-1].atmosphere.weather == "clear"
    assert "No forecast for the plan date" in bench.workspace.living.button.toolTip()


@pytest.mark.parametrize("drape", ["SHADOWS", "SUN_HOURS"])
def test_an_analyze_drape_pauses_the_weather(bench: LivingBench, drape: str) -> None:
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


def test_every_weather_choice_has_its_menu_entry(bench: LivingBench) -> None:
    assert set(bench.workspace.living.actions) == set(WEATHER_CHOICES)
    texts = set(_menu_actions(bench))
    assert {"Clear", "Overcast", "Rain", "Snow", "Today's Weather",
            "Wildlife and Falling Leaves"} <= texts


# ── L5.4: garden lights ──────────────────────────────────────────────────────


def test_garden_lights_are_drawn_with_their_tools_and_light_the_3d_garden(
        bench: LivingBench, qtbot) -> None:
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
    assert ObjectType.STRING_LIGHTS in get_valid_types_for_shape("rectangle")
    view.set_active_tool(ToolType.GARDEN_LIGHT)
    tool = view.tool_manager.active_tool
    assert tool is not None and tool._object_type is ObjectType.GARDEN_LIGHT
    tool.mouse_press(event, QPointF(300, 300))
    tool.mouse_press(event, QPointF(320, 300))
    view.set_active_tool(ToolType.STRING_LIGHTS)
    tool = view.tool_manager.active_tool
    assert tool is not None and tool._object_type is ObjectType.STRING_LIGHTS
    tool.mouse_press(event, QPointF(500, 400))
    tool.mouse_move(event, QPointF(900, 430))
    tool.mouse_release(event, QPointF(900, 430))
    kinds = {getattr(item, "object_type", None) for item in bench.scene.items()}
    assert {ObjectType.GARDEN_LIGHT, ObjectType.STRING_LIGHTS} <= kinds
    qtbot.waitUntil(lambda: bool(bench.host.lamps) and len(bench.host.lamps[-1]) == 2, timeout=5000)
    lit = bench.host.lamps[-1]
    assert all(0.0 < up < 260.0 for _e, _n, up, _w in lit), "they light from their bulbs"
    assert len(lit) <= LAMP_SLOTS
    assert bench.host.ambient and not bench.host.ambient[-1].is_empty, "their bulbs glow"
