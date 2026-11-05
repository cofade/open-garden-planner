"""The look of the 3D view, kept in step with the sun (Phase 17 L1.4). Engine-free.

    pipeline pass ─► the sun the sink was told ─► look_for(sun, preset) ─► host.set_look
                                                   │ the sky, when the sun moved noticeably
                                                   ▼
                                               host.set_sky

One ``LookController`` per engine host. It decides nothing about the look itself
— that is ``core/scene3d/look.py`` (Qt-free data) — and it never learns where the
sun is by itself: the workspace hands it the ``SunState`` the pipeline last sent
to the sink (``Scene3DController.applied`` → ``sync.sun``), so the light and the
look can never be computed from two moments or two solar paths.

What it owns:

- **The render mode** (``software``): ONE parameter decides the three things a
  software adapter cannot afford — no sky texture (each light probe costs seconds
  there), no wind (an animated view renders continuously: 1,351 % of one core on
  WARP, measured by the review), and ``auto`` pinned to ``low`` (it measures
  presented frames, and a still view presents none). The workspace passes its
  compatibility mode.
- **The preset.** A fixed one from the settings, or ``auto``: ``AutoPreset`` fed
  with the host's count of PRESENTED frames, polled on a timer that runs only
  while the wind animates (a view that draws on demand has no frame rate to
  measure — so reduced motion also freezes the automatic choice). A view that
  presents nothing — the display asleep — is no data, and the preset holds. A
  preset step is one ``set_look``: no camera, no geometry. Where ``auto`` settled
  and which levels it had to leave (and until when) are stored, so a new session
  neither starts over nor retries a barred level.
- **The sky.** The procedural sky is a whole texture generated on the GUI thread
  (about 0.1 s, 0.3 s under the atmosphere) and a light probe Qt filters once per
  texture, so it follows the sun only when the sun moved noticeably
  (``look.sky_is_stale``), and — while the
  sun is being dragged — only once it rests (``SKY_SETTLE_MS``); a change of phase
  (sunset, the end of twilight, and back: ``look.sky_phase``) is built at once.
  The light, the exposure and the fog follow every instant. The fog is derived
  from the sky that is ON SCREEN, so it meets the horizon also while the sky lags.
  A sky the engine cannot build is logged ONCE, the session goes on with the
  plain sky and the flat fill, and the look is sent all the same.
- **The sky model (L7, #391).** ``painted`` (the default) or ``atmosphere`` — Qt
  6.12's ``SkyMaterial`` with volumetric clouds (``look.SKY_MODELS``), never on a
  software adapter. The atmosphere needs the cloud noise volume (about a second of
  numpy): it is made on a worker thread when the model is chosen, and until it is
  ready the painted sky shows — the look's sky turns into an atmosphere sky only
  once the volume exists, so the GUI thread never waits for it. An atmosphere whose
  build fails at once (the scene refuses the call) or whose volume cannot be made
  falls back to the painted sky for the rest of the session. A shader that compiles
  to nothing is NOT seen here — Qt then draws its debug sky without a word
  (PF-E3D-14); the frozen self-test compiles the bundle's shader (point 8).
- **The animation policy.** Wind runs only while the 3D pane is shown, motion is
  not reduced and the adapter is not a software one. Motion is reduced by the
  app's setting OR — since Qt 6.12 (Phase 17 L7) — by the operating system's
  "reduce motion" preference (``QAccessibilityHints.motionPreference``), followed
  live: either one stops the wind; neither can switch the other off. Hidden:
  the clock stops where it is and nothing ticks. Reduced motion: the clock rests
  at 0 — every vertex where its mesh puts it. The particles of L5 (rain, snow,
  leaves, butterflies, fireflies) move on the SAME clock: reduced motion makes them
  a photograph and an idle view presents no frame (issue #389's gate).
- **The weather (L5, ADR-070).** ``set_weather``: clear, partly cloudy, overcast, rain,
  snow — or
  ``today`` (L5.3), which shows the weather ``set_todays_weather`` was given (the
  forecast's, only while the plan date is today; else clear). The look is
  ``weather.living_look(sun, preset, weather)``; a new weather builds its sky at once
  (``look.sky_must_build_now``). ``mood`` names what the frame shows. While an Analyze
  drape lies on the ground (``set_analysing``) the weather PAUSES: the look is the sun's
  own — clear, no dew — so the drape's colours read against its legend (a snow cover
  washed the hours of sun to a pale lavender: 3D review of L5).

NOTHING HERE TAKES A FRAME (ADR-060 decision 17): the host is told things and
asked for ``health()``; ``grab`` / ``wait_ready`` / ``pick`` / ``project`` are not
called. A scan of the workspace's modules pins it.

GUI thread only. No Qt Quick import: this module runs in the GPU-less tier.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import replace
from typing import Any, Final, Protocol

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.scene3d.look import (
    ATMOSPHERE,
    AUTO,
    AUTO_LEVELS,
    PAINTED,
    AutoPolicy,
    AutoPreset,
    LookSpec,
    SkySpec,
    normalise_quality,
    normalise_sky_model,
    sky_is_stale,
    sky_must_build_now,
)
from open_garden_planner.core.scene3d.weather import (
    TODAY,
    WEATHER_SPECS,
    WEATHERS,
    living_look,
    mood_of,
    normalise_weather,
    weather_fog,
)

_LOG: Final = logging.getLogger(__name__)

#: A sky that went stale is rebuilt once the sun has rested this long: a time slider
#: being dragged moves the sun many times a second, and one build costs about 0.12 s
#: of the GUI thread (0.32 s under the atmosphere, which builds both skies). The light,
#: the exposure and the fog never wait. Longer than a playback step (200 ms): at 150 ms
#: the timer fired between every two steps and a playing day rebuilt the sky on almost
#: every step (#722).
SKY_SETTLE_MS: Final = 300
#: A playing day still follows the sun: a sky this stale is built at the next pass, even
#: though its settle timer keeps being restarted by the steps (#722).
SKY_MAX_STALENESS_MS: Final = 1000
#: How often the automatic preset reads the host's frame count while the wind runs.
AUTO_SAMPLE_MS: Final = 500
#: How often the cloud volume's worker is looked at while it runs (L7; the geometry
#: lane's way: a poll of one future costs nothing).
NOISE_POLL_MS: Final = 50


def _make_cloud_noise() -> bytes:
    from open_garden_planner.core.scene3d.cloud_noise import cloud_noise_rgba16f

    return cloud_noise_rgba16f()


def system_reduced_motion() -> bool:
    """Whether the operating system asks for less motion — Qt 6.12's
    ``QAccessibilityHints.motionPreference`` (Phase 17 L7; Qt 6.11 had none, so
    until then the app's setting was the only switch). False without an
    application object: nothing to read."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication

    hints = QGuiApplication.styleHints() if QGuiApplication.instance() is not None else None
    accessibility = hints.accessibility() if hints is not None else None
    if accessibility is None:
        return False
    return accessibility.motionPreference() == Qt.MotionPreference.ReducedMotion


class LookHost(Protocol):
    """What the look needs of an engine host (``Quick3DHost`` has it all)."""

    def set_look(self, look: LookSpec) -> None: ...
    def set_sky(self, sky: SkySpec | None) -> None: ...
    def set_wind_running(self, running: bool) -> None: ...
    def rest_wind(self) -> None: ...
    def health(self) -> Any: ...


class LookController(QObject):
    """Keeps a host's look in step with the sun, the settings and the frame rate
    (module docstring)."""

    #: The preset in use changed (a setting, or a step of the automatic one).
    preset_changed = pyqtSignal(str)
    #: The mood of the frame changed (``core.scene3d.weather.MOODS``) — L5.
    mood_changed = pyqtSignal(str)
    #: A sky texture was built — and, from the second one on, an old one retired
    #: with it. Nobody has to count them: a retired sky leaves nothing behind
    #: without a cache release (measured, the sky soak: 0.0 MB per sun change in
    #: committed and in dedicated GPU memory over 20 changes; a sky that is NOT
    #: destroyed reads 8.1) — unlike a retired Model (ADR-060 decision 15).
    sky_rebuilt = pyqtSignal()

    def __init__(self, host: LookHost, *, software: bool, quality: str = AUTO,
                 reduced_motion: bool = False, system_reduced_motion: bool = False,
                 sky_model: str = PAINTED, auto_level: str = "medium",
                 auto_bars: Mapping[str, tuple[float, float]] | None = None,
                 on_auto_level: Callable[[str], None] | None = None,
                 on_auto_bars: Callable[[dict[str, tuple[float, float]]], None] | None = None,
                 policy: AutoPolicy | None = None, parent: QObject | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time) -> None:
        """``software``: the host renders on a software adapter (the workspace's
        compatibility mode) — no sky, no wind, ``auto`` = ``low``.
        ``reduced_motion``: the app's setting; ``system_reduced_motion``: the
        operating system's preference (``system_reduced_motion()``). ``sky_model``:
        one of ``look.SKY_MODELS`` (L7). ``auto_bars``:
        the stored bars, ``{level: (until, next_retry_s)}`` with ``until`` in
        ``wall_clock`` seconds; ``on_auto_level`` / ``on_auto_bars`` store them again
        after every step of the automatic preset."""
        super().__init__(parent)
        self._host = host
        self._software = bool(software)
        self._sky_light = not self._software
        self._quality = normalise_quality(quality)
        self._reduced_motion = bool(reduced_motion)
        self._system_reduced_motion = bool(system_reduced_motion)
        self._on_auto_level = on_auto_level
        self._on_auto_bars = on_auto_bars
        self._clock = clock
        self._wall_clock = wall_clock
        now = wall_clock()
        self._auto = AutoPreset(auto_level, policy, bars={
            level: (until - now, retry) for level, (until, retry) in (auto_bars or {}).items()})
        self._sky_failed = False
        #: L6.2: a recording holds the automatic preset where it is (``hold_preset``).
        self._preset_held = False
        #: L5: the weather picked (``WEATHER_CHOICES``) and what ``today`` stands for.
        self._weather = "clear"
        self._todays: str | None = None
        self._analysing = False
        self._southern = False   # the place lies south of the equator (noon due north)
        self._mood = ""
        self._sun: SunState | None = None
        self._look: LookSpec | None = None       # the look the host was last given
        self._sky_shown: SkySpec | None = None   # the sky the host shows
        self._showing = False
        self._wind_running = False
        self._rested = False                     # the host's wind clock is known to be at 0
        self._closed = False
        #: Instruments (the gates read them).
        self.sky_rebuilds = 0
        self.look_calls = 0
        self._sky_timer = QTimer(self)
        self._sky_timer.setSingleShot(True)
        self._sky_timer.setInterval(SKY_SETTLE_MS)
        self._sky_timer.timeout.connect(self._settle_sky)
        #: When the sky on show first became stale, on ``time.monotonic`` (None: not
        #: stale). The settle timer restarts on every playback step, so this is what
        #: keeps a playing sky following the sun (#722).
        self._sky_stale_since: float | None = None
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_SAMPLE_MS)
        self._auto_timer.timeout.connect(self._sample_frames)
        #: L7: the sky model chosen, whether the atmosphere was refused (for the
        #: session), and the cloud volume's worker (None: not asked for yet).
        self._sky_model = normalise_sky_model(sky_model)
        self._atmosphere_failed = False
        self._noise_ready = False
        self._noise_future: Future[bytes] | None = None
        self._noise_lane: ThreadPoolExecutor | None = None
        self._noise_timer = QTimer(self)
        self._noise_timer.setSingleShot(True)
        self._noise_timer.setInterval(NOISE_POLL_MS)
        self._noise_timer.timeout.connect(self._check_noise)
        self._want_noise()

    @classmethod
    def from_settings(cls, host: LookHost, *, software: bool,
                      parent: QObject | None = None) -> LookController:
        """A controller on the user's settings; it stores where ``auto`` settles and
        which levels it had to leave."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()

        def keep_level(level: str) -> None:
            get_settings().view3d_auto_level = level

        def keep_bars(bars: dict[str, tuple[float, float]]) -> None:
            get_settings().view3d_auto_bars = bars

        controller = cls(host, software=software, quality=settings.view3d_quality,
                         reduced_motion=settings.view3d_reduced_motion,
                         system_reduced_motion=system_reduced_motion(),
                         sky_model=settings.view3d_sky_model,
                         auto_level=settings.view3d_auto_level,
                         auto_bars=settings.view3d_auto_bars,
                         on_auto_level=keep_level, on_auto_bars=keep_bars, parent=parent)
        controller._follow_system_motion()
        return controller

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def quality(self) -> str:
        """The setting: ``auto`` or a preset."""
        return self._quality

    @property
    def preset(self) -> str:
        """The preset in use. ``auto`` on a software adapter is ``low``: nothing is
        animated there, so there are no presented frames to choose from."""
        if self._quality != AUTO:
            return self._quality
        return "low" if self._software else self._auto.preset

    @property
    def software(self) -> bool:
        """The render mode the workspace gave: a software adapter."""
        return self._software

    @property
    def reduced_motion(self) -> bool:
        """Whether motion is reduced: the app's setting OR the system's preference."""
        return self._reduced_motion or self._system_reduced_motion

    @property
    def system_reduced_motion(self) -> bool:
        """The operating system's "reduce motion" preference, as last told."""
        return self._system_reduced_motion

    @property
    def sky_model(self) -> str:
        """The setting: ``painted`` or ``atmosphere`` (L7)."""
        return self._sky_model

    @property
    def sky_model_shown(self) -> str:
        """The model the sky is DRAWN with now: ``atmosphere`` only when chosen, on a
        GPU, its cloud volume ready and the engine never having refused it."""
        if (self._sky_model == ATMOSPHERE and self._noise_ready and not self._software
                and not self._atmosphere_failed):
            return ATMOSPHERE
        return PAINTED

    @property
    def sky_light(self) -> bool:
        """Whether this host is lit by a sky texture (False: the software fallback, or
        a sky the engine could not build — for the rest of the session)."""
        return self._sky_light

    @property
    def animating(self) -> bool:
        """Whether the wind's clock runs right now."""
        return self._wind_running

    @property
    def look(self) -> LookSpec | None:
        """The look the host was last given (None before the first sun)."""
        return self._look

    @property
    def sky(self) -> SkySpec | None:
        """The sky the host shows (None: none yet, or no sky light)."""
        return self._sky_shown

    @property
    def auto(self) -> AutoPreset:
        return self._auto

    @property
    def weather_choice(self) -> str:
        """The weather picked: one of ``weather.WEATHER_CHOICES`` (``today`` included)."""
        return self._weather

    @property
    def weather(self) -> str:
        """The weather shown (``weather.WEATHERS``): ``weather_wanted`` — or clear while
        an Analyze drape lies on the ground (``set_analysing``)."""
        return "clear" if self._analysing else self.weather_wanted

    @property
    def weather_wanted(self) -> str:
        """The weather picked, resolved (``weather.WEATHERS``): the choice — or for
        ``today`` what the forecast says while the plan date is today, else clear."""
        if self._weather == TODAY:
            return self._todays if self._todays in WEATHERS else "clear"
        return self._weather

    @property
    def analysing(self) -> bool:
        """An Analyze drape lies on the ground: the weather (and the dew) pause."""
        return self._analysing

    @property
    def weather_paused(self) -> bool:
        """A weather was picked that the drape on the ground holds back."""
        return self._analysing and self.weather_wanted != "clear"

    @property
    def todays_weather(self) -> str | None:
        """What ``today`` stands for right now (None: no forecast for the plan date)."""
        return self._todays

    @property
    def mood(self) -> str:
        """The mood of the look on screen (``weather.MOODS``; ``""`` before a sun)."""
        return self._mood

    # ── what the workspace tells it ──────────────────────────────────────────

    def set_sun(self, sun: SunState | None) -> None:
        """The sun the pipeline last sent to the sink — after EVERY pass. None (nothing
        was sent yet, or the sync was reset) changes nothing: no look, and no sky,
        before the first sun is known."""
        if sun is None or self._closed:
            return
        self._sun = sun
        self._apply()

    def set_showing(self, showing: bool) -> None:
        """The 3D pane became visible (True) or hidden (False). Hidden: nothing ticks."""
        if self._closed or showing == self._showing:
            return
        self._showing = showing
        if not showing:
            self._sky_timer.stop()   # a stale sky waits for the view to be seen again
        self._update_wind()
        if showing and self._sun is not None:
            self._apply()            # also builds the sky that went stale while hidden

    def set_weather(self, weather: str) -> None:
        """Pick the weather (``weather.WEATHER_CHOICES``; anything else: clear). A new
        weather is applied at once — its sky too."""
        weather = normalise_weather(weather)
        if weather == self._weather or self._closed:
            return
        self._weather = weather
        self._apply()

    def set_analysing(self, analysing: bool) -> None:
        """An Analyze drape (2D shadows, hours of sun) lies on the ground (True) or not.
        While it does, the look is the sun's own — no weather, no dew: a weather
        recolours the ground under the drape, and its colour key no longer reads as the
        legend's (the 3D review measured a 59° hue shift under snow)."""
        if bool(analysing) == self._analysing or self._closed:
            return
        self._analysing = bool(analysing)
        self._apply()

    def set_southern(self, southern: bool) -> None:
        """The garden lies south of the equator (True): its noon stands due north —
        where the morning dew fades and the fireflies' midnight is (``living_look``)."""
        if bool(southern) == self._southern or self._closed:
            return
        self._southern = bool(southern)
        self._apply()

    @property
    def southern(self) -> bool:
        return self._southern

    def set_todays_weather(self, weather: str | None) -> None:
        """What ``today`` stands for: the forecast's preset for the plan date — given
        only while the plan date is today (``weather.todays_weather``), else None."""
        weather = weather if weather in WEATHERS else None
        if weather == self._todays or self._closed:
            return
        self._todays = weather
        if self._weather == TODAY:
            self._apply()

    def set_quality(self, quality: str) -> None:
        """``auto`` or a preset (anything else: ``auto``)."""
        quality = normalise_quality(quality)
        if quality == self._quality or self._closed:
            return
        before = self.preset
        self._quality = quality
        self._auto.pause()
        self._update_wind()
        self._preset_may_have_changed(before)

    def set_reduced_motion(self, reduced: bool) -> None:
        """The app's setting (Preferences → 3D View → Reduce motion)."""
        if bool(reduced) == self._reduced_motion or self._closed:
            return
        self._reduced_motion = bool(reduced)
        self._update_wind()

    def set_system_reduced_motion(self, reduced: bool) -> None:
        """The operating system's preference changed (``motionPreferenceChanged``)."""
        if bool(reduced) == self._system_reduced_motion or self._closed:
            return
        self._system_reduced_motion = bool(reduced)
        self._update_wind()

    def _follow_system_motion(self) -> None:
        """Follow the system's preference while this controller lives (Qt 6.12)."""
        from PyQt6.QtGui import QGuiApplication

        hints = QGuiApplication.styleHints() if QGuiApplication.instance() is not None else None
        accessibility = hints.accessibility() if hints is not None else None
        if accessibility is None:
            return
        accessibility.motionPreferenceChanged.connect(self._system_motion_changed)

    def _system_motion_changed(self, *_args: object) -> None:
        self.set_system_reduced_motion(system_reduced_motion())

    def hold_preset(self, held: bool) -> None:
        """A camera tour is recording (L6.2): the view presents few frames while the host
        renders, which must not read as a slow machine. The automatic preset stops
        measuring until it is over."""
        self._preset_held = bool(held)
        self._update_wind()

    def settle_sky(self) -> None:
        """Build the sky the sun asks for NOW, not when the sun rests: a tour's frame shows
        its own moment. Nothing happens when the sky on show is still good enough."""
        self._sky_timer.stop()
        self._settle_sky()

    def set_sky_model(self, model: str) -> None:
        """Draw the sky with ``model`` (``look.SKY_MODELS``, L7): at once, like a new
        weather — or, for the atmosphere, once its cloud volume is ready."""
        model = normalise_sky_model(model)
        if model == self._sky_model or self._closed:
            return
        self._sky_model = model
        self._want_noise()
        self._apply()

    def reload_settings(self) -> None:
        """The Preferences dialog was accepted: follow what it stored."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        self.set_quality(settings.view3d_quality)
        self.set_reduced_motion(settings.view3d_reduced_motion)
        self.set_sky_model(settings.view3d_sky_model)

    def shutdown(self) -> None:
        """Stop for good (the engine goes). The host is not touched."""
        self._closed = True
        self._showing = self._wind_running = False
        for timer in (self._sky_timer, self._auto_timer, self._noise_timer):
            with contextlib.suppress(RuntimeError):  # the #230 teardown guard
                timer.stop()
        lane, self._noise_lane = self._noise_lane, None
        if lane is not None:
            lane.shutdown(wait=False, cancel_futures=True)

    # ── internals ────────────────────────────────────────────────────────────

    def _apply(self) -> None:
        """Bring the host's look — and, if it must follow, its sky — to the current sun
        and preset. A look equal to the one the host has is not sent again. The sky
        and the look are sent separately: a sky the engine refuses never keeps the
        look from the screen."""
        sun = self._sun
        if sun is None:
            return
        look = self._living_look(sun)
        if self._sky_light:
            shown = self._sky_shown
            if sky_must_build_now(shown, look.sky):
                self._sky_stale_since = None
                self._build_sky(look.sky)       # the first sky; sunset, nightfall, a weather: at once
            elif sky_is_stale(shown, look.sky):
                if self._showing:
                    now = self._clock()
                    if self._sky_stale_since is None:
                        self._sky_stale_since = now
                    if (now - self._sky_stale_since) * 1000.0 >= SKY_MAX_STALENESS_MS:
                        self._sky_stale_since = None
                        self._build_sky(look.sky)   # too long stale: follow the sun now
                    else:
                        self._sky_timer.start()     # (re)started: built when the sun rests
            else:
                self._sky_timer.stop()          # back within the threshold: nothing owed
                self._sky_stale_since = None
            shown = self._sky_shown
            if shown is not None and shown.horizon != look.sky.horizon:
                # the sky on screen is an older one: the fog must meet THAT horizon
                look = replace(look, fog_linear=weather_fog(
                    shown.horizon, look.mood.probe_exposure, shown.sky_energy,
                    WEATHER_SPECS[self.weather].sky_grey, look.mood.twilight))
        mood = mood_of(look, sun)
        if mood != self._mood:
            self._mood = mood
            self.mood_changed.emit(mood)
        if look == self._look:
            return
        try:
            self._host.set_look(look)
        except Exception as error:  # noqa: BLE001 - a dead engine must not take the app down
            _LOG.error("3D look: the engine refused the look (%s: %s)",
                       log_text(type(error).__name__), log_text(error))
            _LOG.debug("3D look: the engine refused the look - traceback", exc_info=error)
            return
        self._look = look
        self.look_calls += 1

    def _living_look(self, sun: SunState) -> LookSpec:
        """The look to show at ``sun``: the weather shown, and the dew unless a drape
        lies on the ground."""
        look = living_look(sun, self.preset, self.weather, dew=not self._analysing,
                           southern=self._southern)
        model = self.sky_model_shown
        if model == look.sky.model:
            return look
        return replace(look, sky=replace(look.sky, model=model))

    def _build_sky(self, sky: SkySpec) -> None:
        """Build ``sky`` — or, when the engine cannot, log it ONCE and go on for the rest
        of the session with the plain sky and the flat fill (``sky_light`` False)."""
        self._sky_timer.stop()
        self._sky_stale_since = None
        if sky.model == ATMOSPHERE:
            try:
                self._host.set_sky(sky)
            except Exception as error:  # noqa: BLE001 - the painted sky is the fallback
                self._atmosphere_failed = True
                _LOG.error("3D look: the atmosphere sky could not be built; the view goes on "
                           "with the painted sky (%s: %s)",
                           log_text(type(error).__name__), log_text(error))
                _LOG.debug("3D look: the atmosphere sky - traceback", exc_info=error)
                sky = replace(sky, model=PAINTED)
            else:
                self._sky_shown = sky
                self.sky_rebuilds += 1
                self.sky_rebuilt.emit()
                return
        try:
            self._host.set_sky(sky)
        except Exception as error:  # noqa: BLE001 - the look must reach the screen anyway
            self._sky_light = False
            self._sky_shown = None
            if not self._sky_failed:
                self._sky_failed = True
                _LOG.error("3D look: the sky could not be built; the view goes on with a plain "
                           "sky (%s: %s)", log_text(type(error).__name__), log_text(error))
                _LOG.debug("3D look: the sky could not be built - traceback", exc_info=error)
            with contextlib.suppress(Exception):  # whatever half a sky left behind goes
                self._host.set_sky(None)
            return
        self._sky_shown = sky
        self.sky_rebuilds += 1
        self.sky_rebuilt.emit()

    def _want_noise(self) -> None:
        """Start making the cloud volume when the atmosphere is chosen and it is not
        made yet (L7): ONE worker, one job; nothing on a software adapter."""
        if (self._sky_model != ATMOSPHERE or self._software or self._noise_ready
                or self._noise_future is not None or self._closed):
            return
        self._noise_lane = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cloud-noise")
        self._noise_future = self._noise_lane.submit(_make_cloud_noise)
        self._noise_timer.start()

    def _check_noise(self) -> None:
        """The worker answered (or not yet: look again). A volume that could not be made
        leaves the painted sky for the session."""
        future = self._noise_future
        if future is None or self._closed:
            return
        if not future.done():
            self._noise_timer.start()
            return
        lane, self._noise_lane = self._noise_lane, None
        if lane is not None:
            lane.shutdown(wait=False)
        try:
            future.result()
        except Exception as error:  # noqa: BLE001 - the painted sky is the fallback
            self._atmosphere_failed = True
            _LOG.error("3D look: the cloud volume could not be made; the view keeps the "
                       "painted sky (%s: %s)", log_text(type(error).__name__), log_text(error))
            return
        self._noise_ready = True
        self._apply()   # the atmosphere replaces the painted sky now (at once: a new model)

    def _settle_sky(self) -> None:
        """The sun rested: build the sky it asks for now (if it is still stale)."""
        sun = self._sun
        if sun is None or self._closed or not self._showing or not self._sky_light:
            return
        wanted = self._living_look(sun).sky
        if not sky_is_stale(self._sky_shown, wanted):
            return
        self._build_sky(wanted)
        self._apply()   # the fog meets the new horizon (or the plain sky, if it failed)

    def _update_wind(self) -> None:
        """The animation policy: wind only while shown, motion not reduced, and not on a
        software adapter (an animated view renders continuously)."""
        reduced = self.reduced_motion
        run = self._showing and not reduced and not self._software
        try:
            if reduced:
                if not self._rested or self._wind_running:
                    self._host.rest_wind()       # at rest: the clock IS 0
                    self._rested = True
            elif run != self._wind_running:
                self._host.set_wind_running(run)
                self._rested = False
        except Exception as error:  # noqa: BLE001 - as in _apply
            _LOG.error("3D look: the wind could not be switched (%s: %s)",
                       log_text(type(error).__name__), log_text(error))
            run = False
        self._wind_running = run
        # the automatic preset measures only frames that flow: while the wind runs
        if run and self._quality == AUTO and not self._preset_held:
            if not self._auto_timer.isActive():
                self._auto.pause()
                self._auto_timer.start()
        else:
            self._auto_timer.stop()
            self._auto.pause()

    def _sample_frames(self) -> None:
        if self._closed or not self._wind_running or self._quality != AUTO:
            self._auto_timer.stop()
            return
        try:
            frames = int(getattr(self._host.health(), "frames_presented", 0))
        except Exception:  # noqa: BLE001 - a host that is gone presents nothing: no data
            return
        before = self.preset
        stepped = self._auto.observe(self._clock(), frames)
        if stepped is None:
            return
        _LOG.info("3D look: automatic quality %s -> %s", before, stepped)
        now_wall = self._wall_clock()
        bars = {level: (now_wall + remaining, retry)
                for level, (remaining, retry) in self._auto.bars_at(self._clock()).items()}
        try:
            if self._on_auto_level is not None and stepped in AUTO_LEVELS:
                self._on_auto_level(stepped)
            if self._on_auto_bars is not None:
                self._on_auto_bars(bars)
        except Exception as error:  # noqa: BLE001 - a store that cannot be written
            _LOG.warning("3D look: the automatic quality could not be stored (%s)",
                         log_text(error))
        self._preset_may_have_changed(before)

    def _preset_may_have_changed(self, before: str) -> None:
        if self.preset == before:
            return
        self._apply()
        self.preset_changed.emit(self.preset)
