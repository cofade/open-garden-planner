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
  (about 0.1 s) and a light probe Qt filters once per texture, so it follows the
  sun only when the sun moved noticeably (``look.sky_is_stale``), and — while the
  sun is being dragged — only once it rests (``SKY_SETTLE_MS``); a change of phase
  (sunset, the end of twilight, and back: ``look.sky_phase``) is built at once.
  The light, the exposure and the fog follow every instant. The fog is derived
  from the sky that is ON SCREEN, so it meets the horizon also while the sky lags.
  A sky the engine cannot build is logged ONCE, the session goes on with the
  plain sky and the flat fill, and the look is sent all the same.
- **The animation policy.** Wind runs only while the 3D pane is shown, the
  reduced-motion setting is off and the adapter is not a software one. Hidden:
  the clock stops where it is and nothing ticks. Reduced motion: the clock rests
  at 0 — every vertex where its mesh puts it.

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
from dataclasses import replace
from typing import Any, Final, Protocol

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d import SunState
from open_garden_planner.core.scene3d.look import (
    AUTO,
    AUTO_LEVELS,
    AutoPolicy,
    AutoPreset,
    LookSpec,
    SkySpec,
    fog_linear,
    look_for,
    normalise_quality,
    sky_is_stale,
    sky_phase,
)

_LOG: Final = logging.getLogger(__name__)

#: A sky that went stale is rebuilt once the sun has rested this long: a time slider
#: being dragged moves the sun many times a second, and one build costs about 0.1 s
#: of the GUI thread. The light, the exposure and the fog never wait.
SKY_SETTLE_MS: Final = 150
#: How often the automatic preset reads the host's frame count while the wind runs.
AUTO_SAMPLE_MS: Final = 500


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
    #: A sky texture was built — and, from the second one on, an old one retired
    #: with it. Nobody has to count them: a retired sky leaves nothing behind
    #: without a cache release (measured, the sky soak: 0.0 MB per sun change in
    #: committed and in dedicated GPU memory over 20 changes; a sky that is NOT
    #: destroyed reads 8.1) — unlike a retired Model (ADR-060 decision 15).
    sky_rebuilt = pyqtSignal()

    def __init__(self, host: LookHost, *, software: bool, quality: str = AUTO,
                 reduced_motion: bool = False, auto_level: str = "medium",
                 auto_bars: Mapping[str, tuple[float, float]] | None = None,
                 on_auto_level: Callable[[str], None] | None = None,
                 on_auto_bars: Callable[[dict[str, tuple[float, float]]], None] | None = None,
                 policy: AutoPolicy | None = None, parent: QObject | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 wall_clock: Callable[[], float] = time.time) -> None:
        """``software``: the host renders on a software adapter (the workspace's
        compatibility mode) — no sky, no wind, ``auto`` = ``low``. ``auto_bars``:
        the stored bars, ``{level: (until, next_retry_s)}`` with ``until`` in
        ``wall_clock`` seconds; ``on_auto_level`` / ``on_auto_bars`` store them again
        after every step of the automatic preset."""
        super().__init__(parent)
        self._host = host
        self._software = bool(software)
        self._sky_light = not self._software
        self._quality = normalise_quality(quality)
        self._reduced_motion = bool(reduced_motion)
        self._on_auto_level = on_auto_level
        self._on_auto_bars = on_auto_bars
        self._clock = clock
        self._wall_clock = wall_clock
        now = wall_clock()
        self._auto = AutoPreset(auto_level, policy, bars={
            level: (until - now, retry) for level, (until, retry) in (auto_bars or {}).items()})
        self._sky_failed = False
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
        self._auto_timer = QTimer(self)
        self._auto_timer.setInterval(AUTO_SAMPLE_MS)
        self._auto_timer.timeout.connect(self._sample_frames)

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

        return cls(host, software=software, quality=settings.view3d_quality,
                   reduced_motion=settings.view3d_reduced_motion,
                   auto_level=settings.view3d_auto_level, auto_bars=settings.view3d_auto_bars,
                   on_auto_level=keep_level, on_auto_bars=keep_bars, parent=parent)

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
        return self._reduced_motion

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
        if bool(reduced) == self._reduced_motion or self._closed:
            return
        self._reduced_motion = bool(reduced)
        self._update_wind()

    def reload_settings(self) -> None:
        """The Preferences dialog was accepted: follow what it stored."""
        from open_garden_planner.app.settings import get_settings

        settings = get_settings()
        self.set_quality(settings.view3d_quality)
        self.set_reduced_motion(settings.view3d_reduced_motion)

    def shutdown(self) -> None:
        """Stop for good (the engine goes). The host is not touched."""
        self._closed = True
        self._showing = self._wind_running = False
        for timer in (self._sky_timer, self._auto_timer):
            with contextlib.suppress(RuntimeError):  # the #230 teardown guard
                timer.stop()

    # ── internals ────────────────────────────────────────────────────────────

    def _apply(self) -> None:
        """Bring the host's look — and, if it must follow, its sky — to the current sun
        and preset. A look equal to the one the host has is not sent again. The sky
        and the look are sent separately: a sky the engine refuses never keeps the
        look from the screen."""
        sun = self._sun
        if sun is None:
            return
        look = look_for(sun, self.preset)
        if self._sky_light:
            shown = self._sky_shown
            if shown is None or sky_phase(shown) != sky_phase(look.sky):
                self._build_sky(look.sky)       # the first sky; sunset, nightfall: at once
            elif sky_is_stale(shown, look.sky):
                if self._showing:
                    self._sky_timer.start()     # (re)started: built when the sun rests
            else:
                self._sky_timer.stop()          # back within the threshold: nothing owed
            shown = self._sky_shown
            if shown is not None and shown.horizon != look.sky.horizon:
                # the sky on screen is an older one: the fog must meet THAT horizon
                look = replace(look, fog_linear=fog_linear(
                    shown.horizon, look.mood.probe_exposure, shown.sky_energy))
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

    def _build_sky(self, sky: SkySpec) -> None:
        """Build ``sky`` — or, when the engine cannot, log it ONCE and go on for the rest
        of the session with the plain sky and the flat fill (``sky_light`` False)."""
        self._sky_timer.stop()
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

    def _settle_sky(self) -> None:
        """The sun rested: build the sky it asks for now (if it is still stale)."""
        sun = self._sun
        if sun is None or self._closed or not self._showing or not self._sky_light:
            return
        wanted = look_for(sun, self.preset).sky
        if not sky_is_stale(self._sky_shown, wanted):
            return
        self._build_sky(wanted)
        self._apply()   # the fog meets the new horizon (or the plain sky, if it failed)

    def _update_wind(self) -> None:
        """The animation policy: wind only while shown, motion not reduced, and not on a
        software adapter (an animated view renders continuously)."""
        run = self._showing and not self._reduced_motion and not self._software
        try:
            if self._reduced_motion:
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
        if run and self._quality == AUTO:
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
