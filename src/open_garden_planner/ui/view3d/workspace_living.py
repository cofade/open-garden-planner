"""The living garden in the 3D workspace (Phase 17 L5, #389, ADR-070).

The 3D strip's "Weather" menu and what it drives. Engine-free: like the other
coordinators of the workspace it is told the host and the look controller by
``Workspace`` and imports no Qt Quick binding.

- **The weather** — Clear, Partly cloudy (L7), Overcast, Rain, Snow, and Today's Weather (L5.3): the
  forecast the app fetched (``set_forecast``; the Planting Calendar's weather widget —
  the 3D view fetches nothing itself, it ASKS: ``forecast_wanted`` when Today's Weather
  is chosen, and again for a new location or document, which also forget the old
  forecast), ONLY while the plan date is today (``weather.todays_weather``). The choice goes to ``LookController.set_weather``;
  the look, the sky, the particles and the wind follow from it there. The button
  names the weather shown; its tooltip names the frame's mood (``weather.mood_of``).
  While an Analyze drape lies on the ground (``set_analysing``, from the workspace)
  the weather pauses — the drape's colours must read as its legend's — and the button
  says so.
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

import datetime
import logging
from collections.abc import Callable, Iterable, Mapping
from datetime import date
from typing import TYPE_CHECKING, Any, Final

from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMenu, QToolButton, QWidget

from open_garden_planner.core.phenology import plan_latitude
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d import living_buffers
from open_garden_planner.core.scene3d.lights import (
    LIGHT_KINDS,
    LampSource,
    lamp_sources,
    nearest_lamps,
)
from open_garden_planner.core.scene3d.weather import TODAY, WEATHER_CHOICES, todays_weather
from open_garden_planner.core.solar import plan_place
from open_garden_planner.ui.sim_clock_subscription import connect_qobject

if TYPE_CHECKING:
    from open_garden_planner.core.phenology import PhenologyState
    from open_garden_planner.core.sim_clock import SimClock

    from .look_controller import LookController
    from .sync_controller import TickReport
    from .workspace_protocols import EngineHost

_LOG: Final = logging.getLogger(__name__)


def _tr(text: str) -> str:
    return QCoreApplication.translate("Workspace", text)


def weather_names() -> dict[str, str]:
    """The weather choices as the menu names them (translated)."""
    return {"clear": _tr("Clear"), "partly_cloudy": _tr("Partly cloudy"),
            "overcast": _tr("Overcast"), "rain": _tr("Rain"), "snow": _tr("Snow"),
            TODAY: _tr("Today's Weather")}


def mood_names() -> dict[str, str]:
    """``weather.MOODS`` as the tooltip names them (translated)."""
    return {"night": _tr("Night"), "twilight": _tr("Twilight"), "rain": _tr("Rain"),
            "snow": _tr("Snow"), "overcast": _tr("Overcast"), "morning_dew": _tr("Morning dew"),
            "golden_hour": _tr("Golden hour"), "day": _tr("Day")}


class WorkspaceLivingCoordinator(QObject):
    """The weather menu, the garden's life and its lights (module docstring)."""

    #: Today's Weather needs a forecast: the app fetches one through the Planting
    #: Calendar's weather widget (its one fetch path) and hands it to ``set_forecast``.
    forecast_wanted = pyqtSignal()

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
        self._analysing = False
        self._forecast: tuple[tuple[str, int], ...] = ()
        self._forecast_place: tuple[float, float] | None = None   # where it was fetched
        self._seasons: Mapping[str, PhenologyState] = {}
        self._sources: tuple[LampSource, ...] = ()
        self._sources_read = False   # the lights were read from a full pass of this engine
        self._lit: tuple[tuple[float, float, float, float], ...] | None = None
        self._ambient_key: object = None
        self._target: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._button: QToolButton | None = None
        self._pass_date: date | None = None
        self._midnight_timer = QTimer(self)
        self._midnight_timer.setSingleShot(True)
        self._midnight_timer.timeout.connect(self._on_midnight)
        self._arm_midnight_timer()
        #: Instruments (tests): how often the host was given an ambient buffer / lamps.
        self.ambient_sent = 0
        self.lamps_sent = 0
        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: dict[str, QAction] = {}
        names = weather_names()
        tips = {
            "clear": _tr("A clear sky: the sun and its shadows as the plan's sun study has them"),
            "partly_cloudy": _tr("Sun and scattered clouds: the shadows stay, a little "
                                 "softer. The clouds show with the atmosphere sky "
                                 "(Preferences, 3D View, Sky)"),
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
        button.setProperty("menuChevron", True)   # its arrow beside the text (ui/theme.py)
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
        look.set_analysing(self._analysing)
        self._update_todays()
        host = self._get_host()
        if host is not None:
            self._send("set_life_enabled", lambda: host.set_life_enabled(self._life))
        self._lit = None
        self._ambient_key = None
        self._refresh_button()

    def unwire(self) -> None:
        """The engine goes: forget what the host was given (and the drape: the next
        engine's analysis says again what lies on its ground)."""
        self._analysing = False
        self._seasons = {}
        self._sources = ()
        self._sources_read = False
        self._lit = None
        self._ambient_key = None
        self._pass_date = None
        self._refresh_button()  # no "(paused while analysing)" left from the old engine

    @property
    def weather_choice(self) -> str:
        return self._weather

    @property
    def life_enabled(self) -> bool:
        return self._life

    def set_weather(self, weather: str) -> None:
        """Pick a weather (``WEATHER_CHOICES``). Today's Weather asks for the forecast."""
        if weather not in WEATHER_CHOICES:
            raise ValueError(f"a weather is one of {WEATHER_CHOICES}, got {weather!r}")
        self._weather = weather
        self._actions[weather].setChecked(True)
        look = self._get_look()
        if look is not None:
            look.set_weather(weather)
        if weather == TODAY:
            self.forecast_wanted.emit()
        self._refresh_button()

    def document_changed(self) -> None:
        """A new, opened or recovered document: the forecast was the old one's place —
        forget it, and ask NOTHING: the signal comes before the new document's location
        is set, so an ask here fetched the OLD place's forecast (senior review of L5).
        Its ``location_changed`` always follows (``place_changed``)."""
        self._forecast = ()
        self._update_todays()

    def place_changed(self) -> None:
        """The garden location changed (also when a document brings its own): the
        forecast was another place's — forget it, and ask again while Today's Weather
        is chosen. An edit that keeps the coordinates (a frost date) changes nothing while
        the forecast held is the one fetched there: the sky is not cleared and rebuilt.
        (A new document has forgotten its forecast already: ``document_changed``.)"""
        place = self._place()
        if self._forecast and place == self._forecast_place:
            return
        self._forecast_place = place
        self.document_changed()
        if self._weather == TODAY:
            self.forecast_wanted.emit()

    @property
    def forecast(self) -> tuple[tuple[str, int], ...]:
        """The forecast's days the app last gave, ``(ISO date, WMO code)``."""
        return self._forecast

    def set_analysing(self, analysing: bool) -> None:
        """An Analyze drape lies on the ground (True) or not: the weather pauses while it
        does (``LookController.set_analysing``)."""
        self._analysing = bool(analysing)
        look = self._get_look()
        if look is not None:
            look.set_analysing(self._analysing)
        self._refresh_button()

    @property
    def analysing(self) -> bool:
        return self._analysing

    def set_life_enabled(self, enabled: bool) -> None:
        self._life = bool(enabled)
        self._life_action.setChecked(self._life)
        host = self._get_host()
        if host is not None:
            self._send("set_life_enabled", lambda: host.set_life_enabled(self._life))

    def set_forecast(self, place: tuple[float, float] | None,
                     days: Iterable[tuple[str, int]]) -> None:
        """The app's daily forecast for ``place`` — the ``(lat, lon)`` the Planting
        Calendar's weather widget fetched it for —: ``(ISO date, WMO code)`` per day;
        nothing here goes to the network. A forecast for another place than the plan's
        is not this plan's and is dropped: the producer says where it fetched, nobody
        guesses (senior review of L5)."""
        where = None if place is None else (float(place[0]), float(place[1]))
        if where != self._place():
            return
        self._forecast = tuple((str(day), int(code)) for day, code in days)
        self._forecast_place = where
        self._update_todays()

    def season_sink(self, host: EngineHost) -> Callable[..., None]:
        """What the Plant Forge hands its phenology to: the host's plant seasons, then the
        garden's life (which plants flower, which drop their leaves)."""

        def sink(states: Mapping[str, PhenologyState], plan_date: date | None = None) -> None:
            # contained like every living-garden call: the Forge's own error path calls
            # this again (``ForgeWorker.clear``), and a second raise there skipped its reset
            self._send("set_plant_seasons", lambda: host.set_plant_seasons(states))
            self._seasons = dict(states)
            if plan_date is not None:
                self._pass_date = plan_date
            self._refresh_ambient()

        return sink

    def on_applied(self, report: TickReport) -> None:
        """A pass went through: the lights may have moved, come or gone. They are read
        again only when the pass touched a light (or the sync was reset): reading every
        record costs ~40 ms for 500 lights, too much for every pass (ADR-069's slice)."""
        if report.ground_pass or not report.snapshot:
            return
        if self._sources_read and not report.recovered and not self._touches_a_light(report):
            return
        try:
            self._sources_read = True
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

    def _touches_a_light(self, report: TickReport) -> bool:
        changes = report.changes
        touched = {*changes.added, *changes.removed, *changes.transform, *changes.geometry,
                   *changes.material}
        if not touched:
            return False
        lit = {source.item_id for source in self._sources}
        records = self._get_records()
        return any(item_id in lit or getattr(records.get(item_id), "kind", None) in LIGHT_KINDS
                   for item_id in touched)

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

    def _why_no_forecast(self) -> str:
        """Why Today's Weather shows clear: the plan date, the location, or the forecast."""
        clock = self._clock
        if clock is not None and clock.plan_date != date.today():
            return _tr("Today's weather follows the forecast only while the plan date is "
                       "today; on any other date the sky is clear.")
        if self._place() is None:     # the calendar reads the place by the same rule
            return _tr("Today's weather needs a garden location for its forecast.")
        return _tr("The forecast for today is not loaded yet, or could not be fetched.")

    def _latitude(self) -> float:
        return plan_latitude(self._get_location())

    def _place(self) -> tuple[float, float] | None:
        """The plan's coordinates, or None without a location — read as the calendar
        reads them (``solar.plan_place``): the two compare places."""
        return plan_place(self._get_location())

    def _refresh_ambient(self) -> None:
        """Rebuild the ambient buffer when what it holds changed: the plants' life on
        the plan date and the lights' bulbs."""
        host, clock = self._get_host(), self._clock
        if host is None or clock is None:
            return
        try:
            records = self._get_records()
            ambient_date = self._pass_date or clock.plan_date
            living = living_buffers(
                records, self._seasons, ambient_date, self._latitude(), self._target
            )
            key = (living.emitters, living.bulbs)
            if key == self._ambient_key:
                return
            self._ambient_key = key
            self._send("set_ambient", lambda: host.set_ambient(living.buffers))
            self.ambient_sent += 1
        except Exception as error:  # noqa: BLE001 - the garden's life never takes 3D down
            _LOG.warning("3D living garden: the garden's life could not be updated (%s)",
                         log_text(error))

    def _arm_midnight_timer(self) -> None:
        """Schedule a single-shot trigger at the next local midnight (#689)."""
        now = datetime.datetime.now()
        tomorrow = now.date() + datetime.timedelta(days=1)
        midnight = datetime.datetime.combine(tomorrow, datetime.time.min)
        ms = max(1000, int((midnight - now).total_seconds() * 1000.0) + 100)
        self._midnight_timer.start(ms)

    def _on_midnight(self) -> None:
        """Local midnight crossed: re-evaluate Today's Weather and re-arm (#689)."""
        clock = self._clock
        if self._weather == TODAY:
            if clock is not None and clock.plan_date == date.today() - datetime.timedelta(days=1):
                clock.set_date(date.today())
            self.forecast_wanted.emit()
        self._update_todays()
        self._arm_midnight_timer()

    def _send_lamps(self) -> None:
        host = self._get_host()
        if host is None:
            return
        lit = tuple(source.light for source in nearest_lamps(self._sources, self._target))
        if lit == self._lit:
            return
        self._lit = lit
        self._send("set_lamps", lambda: host.set_lamps(list(lit)))
        self.lamps_sent += 1

    def _send(self, name: str, call: Callable[[], None]) -> None:
        """Tell the host something (``EngineHost``'s living-garden methods): a host that
        fails is a warning — the garden's life never takes 3D down."""
        try:
            call()
        except Exception as error:  # noqa: BLE001 - as above
            _LOG.warning("3D living garden: %s failed (%s)", name, log_text(error))

    def _refresh_button(self) -> None:
        button = self._button
        if button is None:
            return
        look = self._get_look()
        # no engine yet: nothing is shown, the choice is (Today's: clear, no forecast)
        wanted = look.weather_wanted if look is not None else (
            "clear" if self._weather == TODAY else self._weather)
        paused = look is not None and look.weather_paused
        names = weather_names()
        if self._weather == TODAY:
            text = _tr("Weather: Today ({weather})").format(weather=names[wanted])
        else:
            text = _tr("Weather: {weather}").format(weather=names[wanted])
        if paused:
            text = _tr("{weather} (paused while analysing)").format(weather=text)
        button.setText(text)
        tip = [text]
        if paused:
            tip.append(_tr("The analysis on the ground shows the clear sun's colours; the "
                           "weather returns when the ground shows nothing."))
        mood = look.mood if look is not None else ""
        if mood:
            tip.append(_tr("Mood: {mood}").format(mood=mood_names().get(mood, mood)))
        if self._weather == TODAY and (look is None or look.todays_weather is None):
            tip.append(self._why_no_forecast())
        button.setToolTip("\n".join(tip))
