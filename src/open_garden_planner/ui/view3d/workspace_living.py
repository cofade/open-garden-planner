"""The living garden in the 3D workspace (Phase 17 L5, #389, ADR-070).

The 3D strip's "Weather" menu and what it drives. Engine-free: like the other
coordinators of the workspace it is told the host and the look controller by
``Workspace`` and imports no Qt Quick binding.

- **The weather** — Clear, Overcast, Rain, Snow, and Today's Weather (L5.3): the
  forecast the app already fetched (``set_forecast``; the Planting Calendar's weather
  widget — the 3D view fetches nothing itself), ONLY while the plan date is today
  (``weather.todays_weather``). The choice goes to ``LookController.set_weather``;
  the look, the sky, the particles and the wind follow from it there. The button
  names the weather shown; its tooltip names the frame's mood (``weather.mood_of``).
- **The garden's life** — falling leaves, butterflies at the plants in flower,
  fireflies on summer evenings (``particles.ambient_emitters``, from the records the
  engine holds and the phenology the Plant Forge evaluated — ``season_sink``) and the
  glowing bulbs of the garden lights (``lights.lamp_sources``), loaded into the
  host's ONE ambient geometry (``Quick3DHost.set_ambient``) when what it holds
  changes. The checkable "Wildlife and Falling Leaves" switches the life off and on
  (``set_life_enabled``) — the bulbs stay.
- **The lamps that light** — the ``lights.LAMP_SLOTS`` garden lights nearest to the
  camera's target (``nearest_lamps``), told to the host when that set changes.

Both the weather and the life switch are the session's (not stored), like the sim
moment itself (FR-SUN-04): every session starts clear, with life on.

NOTHING HERE TAKES A FRAME (ADR-060 decision 17): the host is told things, never
asked for a picture.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from typing import TYPE_CHECKING, Any, Final

from PyQt6.QtCore import QCoreApplication, QObject, Qt
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu, QToolButton, QWidget

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d.lights import LampSource, lamp_sources, nearest_lamps
from open_garden_planner.core.scene3d.particles import (
    Emitter,
    ambient_buffers,
    ambient_emitters,
)
from open_garden_planner.core.scene3d.weather import TODAY, WEATHER_CHOICES, todays_weather
from open_garden_planner.ui.sim_clock_subscription import connect_qobject

if TYPE_CHECKING:
    from open_garden_planner.core.phenology import PhenologyState
    from open_garden_planner.core.sim_clock import SimClock

    from .look_controller import LookController
    from .sync_controller import TickReport
    from .workspace_protocols import EngineHost

_LOG: Final = logging.getLogger(__name__)
#: The latitude the Plant Forge assumes for a plan without a location (``workspace``).
_DEFAULT_LATITUDE: Final = 52.52


def _tr(text: str) -> str:
    return QCoreApplication.translate("Workspace", text)


def weather_names() -> dict[str, str]:
    """The weather choices as the menu names them (translated)."""
    return {"clear": _tr("Clear"), "overcast": _tr("Overcast"), "rain": _tr("Rain"),
            "snow": _tr("Snow"), TODAY: _tr("Today's Weather")}


def mood_names() -> dict[str, str]:
    """``weather.MOODS`` as the tooltip names them (translated)."""
    return {"night": _tr("Night"), "twilight": _tr("Twilight"), "rain": _tr("Rain"),
            "snow": _tr("Snow"), "overcast": _tr("Overcast"), "morning_dew": _tr("Morning dew"),
            "golden_hour": _tr("Golden hour"), "day": _tr("Day")}


class WorkspaceLivingCoordinator(QObject):
    """The weather menu, the garden's life and its lights (module docstring)."""

    def __init__(self, get_host: Callable[[], EngineHost | None],
                 get_look: Callable[[], LookController | None],
                 get_records: Callable[[], Mapping[str, Any]],
                 get_location: Callable[[], Any],
                 parent: QWidget) -> None:
        super().__init__(parent)
        self._get_host = get_host
        self._get_look = get_look
        self._get_records = get_records
        self._get_location = get_location
        self._clock: SimClock | None = None
        self._weather = "clear"
        self._life = True
        self._forecast: tuple[tuple[str, int], ...] = ()
        self._seasons: Mapping[str, PhenologyState] = {}
        self._sources: tuple[LampSource, ...] = ()
        self._lit: tuple[tuple[float, float, float, float], ...] | None = None
        self._ambient_key: object = None
        self._target: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._button: QToolButton | None = None
        #: Instruments (tests): how often the host was given an ambient buffer / lamps.
        self.ambient_sent = 0
        self.lamps_sent = 0
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: dict[str, QAction] = {}
        names = weather_names()
        tips = {
            "clear": _tr("A clear sky: the sun and its shadows as the plan's sun study has them"),
            "overcast": _tr("A grey sky: soft, faint shadows; the sun stays where it is"),
            "rain": _tr("Rain: a grey sky, wet leaves and ground, falling rain"),
            "snow": _tr("Snow on the ground and the leaves, falling snow"),
            TODAY: _tr("The forecast's weather while the plan date is today; "
                       "on any other date a clear sky"),
        }
        for choice in WEATHER_CHOICES:
            action = QAction(names[choice], self)
            action.setCheckable(True)
            action.setStatusTip(tips[choice])
            action.setToolTip(tips[choice])
            action.triggered.connect(lambda _checked=False, w=choice: self.set_weather(w))
            self._group.addAction(action)
            self._actions[choice] = action
        self._actions["clear"].setChecked(True)
        self._life_action = QAction(_tr("Wildlife and Falling Leaves"), self)
        self._life_action.setCheckable(True)
        self._life_action.setChecked(True)
        self._life_action.setStatusTip(_tr(
            "Show butterflies at the flowers, fireflies on summer evenings and falling "
            "leaves in autumn"))
        self._life_action.triggered.connect(lambda checked=False: self.set_life_enabled(bool(checked)))

    # ── the strip ────────────────────────────────────────────────────────────

    def build_controls(self, strip: QWidget, layout: Any) -> QToolButton:
        """The "Weather" button with its menu, added to the 3D pane's strip."""
        button = QToolButton(strip)
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(button)
        menu.addSection(_tr("Weather"))
        for choice in WEATHER_CHOICES:
            if choice == TODAY:
                menu.addSeparator()
            menu.addAction(self._actions[choice])
        menu.addSeparator()
        menu.addAction(self._life_action)
        button.setMenu(menu)
        layout.addWidget(button)
        self._button = button
        self._refresh_button()
        return button

    @property
    def actions(self) -> dict[str, QAction]:
        """The weather choices' actions, by choice."""
        return dict(self._actions)

    @property
    def life_action(self) -> QAction:
        return self._life_action

    @property
    def button(self) -> QToolButton | None:
        return self._button

    # ── what the workspace tells it ──────────────────────────────────────────

    def connect_clock(self, clock: SimClock) -> None:
        """The plan's clock: a new plan date may make "today's weather" mean another."""
        if self._clock is clock:
            return
        self._clock = clock
        connect_qobject(clock.date_changed, self._on_date)
        self._update_todays()

    def wire(self, look: LookController) -> None:
        """A new engine: give its look the session's weather, and listen to its mood."""
        look.mood_changed.connect(self._on_mood)
        look.set_weather(self._weather)
        self._update_todays()
        host = self._get_host()
        if host is not None:
            self._call(host, "set_life_enabled", self._life)
        self._lit = None
        self._ambient_key = None
        self._refresh_button()

    def unwire(self) -> None:
        """The engine goes: forget what the host was given."""
        self._seasons = {}
        self._sources = ()
        self._lit = None
        self._ambient_key = None

    @property
    def weather_choice(self) -> str:
        return self._weather

    @property
    def life_enabled(self) -> bool:
        return self._life

    def set_weather(self, weather: str) -> None:
        """Pick a weather (``WEATHER_CHOICES``)."""
        if weather not in WEATHER_CHOICES:
            raise ValueError(f"a weather is one of {WEATHER_CHOICES}, got {weather!r}")
        self._weather = weather
        self._actions[weather].setChecked(True)
        look = self._get_look()
        if look is not None:
            look.set_weather(weather)
        self._refresh_button()

    def set_life_enabled(self, enabled: bool) -> None:
        self._life = bool(enabled)
        self._life_action.setChecked(self._life)
        host = self._get_host()
        if host is not None:
            self._call(host, "set_life_enabled", self._life)

    def set_forecast(self, days: Iterable[tuple[str, int]]) -> None:
        """The app's daily forecast: ``(ISO date, WMO code)`` — the Planting Calendar's
        weather widget fetched it; nothing here goes to the network."""
        self._forecast = tuple((str(day), int(code)) for day, code in days)
        self._update_todays()

    def season_sink(self, host: EngineHost) -> Callable[[Mapping[str, PhenologyState]], None]:
        """What the Plant Forge hands its phenology to: the host's plant seasons, then the
        garden's life (which plants flower, which drop their leaves)."""
        forward = getattr(host, "set_plant_seasons", None)

        def sink(states: Mapping[str, PhenologyState]) -> None:
            if callable(forward):
                forward(states)
            self._seasons = dict(states)
            self._refresh_ambient()

        return sink

    def on_applied(self, report: TickReport) -> None:
        """A pass went through: the lights may have moved, come or gone."""
        if report.ground_pass or not report.snapshot:
            return
        try:
            sources = lamp_sources(self._get_records().values())
        except Exception as error:  # noqa: BLE001 - a plan's lights never take 3D down
            _LOG.warning("3D living garden: the garden lights could not be read (%s)",
                         log_text(error))
            return
        if sources != self._sources:
            self._sources = sources
            self._refresh_ambient()
            self._lit = None
            self._send_lamps()

    def camera_moved(self, target: tuple[float, float, float]) -> None:
        """The camera's target moved: the nearest lamps may be others."""
        self._target = (float(target[0]), float(target[1]), float(target[2]))
        if self._sources:
            self._send_lamps()

    # ── internals ────────────────────────────────────────────────────────────

    def _on_date(self, _day: date) -> None:
        self._update_todays()

    def _on_mood(self, _mood: str) -> None:
        self._refresh_button()

    def _update_todays(self) -> None:
        clock, look = self._clock, self._get_look()
        if clock is None or look is None:
            return
        look.set_todays_weather(todays_weather(self._forecast, clock.plan_date, date.today()))
        self._refresh_button()

    def _latitude(self) -> float:
        location = self._get_location()
        latitude = location.get("latitude") if isinstance(location, Mapping) else None
        return float(latitude) if isinstance(latitude, (int, float)) else _DEFAULT_LATITUDE

    def _refresh_ambient(self) -> None:
        """Rebuild the ambient buffer when what it holds changed: the plants' life on
        the plan date and the lights' bulbs."""
        host, clock = self._get_host(), self._clock
        if host is None or clock is None:
            return
        try:
            records = self._get_records()
            emitters: tuple[Emitter, ...] = ()
            if self._seasons:
                emitters = ambient_emitters(records.values(), self._seasons, clock.plan_date,
                                            self._latitude())
            bulbs = tuple(bulb for source in self._sources for bulb in source.bulbs())
            key = (emitters, bulbs)
            if key == self._ambient_key:
                return
            self._ambient_key = key
            self._call(host, "set_ambient", ambient_buffers((*emitters, *bulbs)))
            self.ambient_sent += 1
        except Exception as error:  # noqa: BLE001 - the garden's life never takes 3D down
            _LOG.warning("3D living garden: the garden's life could not be updated (%s)",
                         log_text(error))

    def _send_lamps(self) -> None:
        host = self._get_host()
        if host is None:
            return
        lit = tuple(source.light for source in nearest_lamps(self._sources, self._target))
        if lit == self._lit:
            return
        self._lit = lit
        self._call(host, "set_lamps", list(lit))
        self.lamps_sent += 1

    def _call(self, host: EngineHost, name: str, *arguments: object) -> None:
        method = getattr(host, name, None)
        if not callable(method):
            return      # a stand-in host of the tests without the living garden
        try:
            method(*arguments)
        except Exception as error:  # noqa: BLE001 - as above
            _LOG.warning("3D living garden: %s failed (%s)", name, log_text(error))

    def _refresh_button(self) -> None:
        button = self._button
        if button is None:
            return
        look = self._get_look()
        shown = look.weather if look is not None else (
            "clear" if self._weather == TODAY else self._weather)
        names = weather_names()
        if self._weather == TODAY:
            text = _tr("Weather: Today ({weather})").format(weather=names[shown])
        else:
            text = _tr("Weather: {weather}").format(weather=names[shown])
        button.setText(text)
        tip = [text]
        mood = look.mood if look is not None else ""
        if mood:
            tip.append(_tr("Mood: {mood}").format(mood=mood_names().get(mood, mood)))
        if self._weather == TODAY and (look is None or look.todays_weather is None):
            tip.append(_tr("No forecast for the plan date: today's weather needs the plan "
                           "date to be today and a garden location with a forecast."))
        button.setToolTip("\n".join(tip))
