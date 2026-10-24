"""Analyze in 3D — drapes, sun path, ground probe, day sweep, Cutaway (Phase 17 L2, #386).

Engine-free (no Qt Quick import): it drives the host through three calls —
``set_overlay`` (the shade or the drape, the lines), ``set_roofs_hidden`` and ``set_faded_items``
(``AnalysisHost``) — and the workspace's tests hand it a stand-in. One per 3D
engine; the workspace builds it with the engine and owns it.

THE 2D ANALYSIS STAYS THE TRUTH (ADR-048, the scope note of criterion 8). Nothing
here computes a shadow or a sun hour:

- **Shadows drape** — ``SunShadowController.drape_polygons()``, the polygons the
  canvas overlay paints, laid on the ground when ``shadows_changed`` says they
  changed (``core.scene3d.drape.shadow_drape``) — on the ``"shade"`` layer, which
  MULTIPLIES the frame, so a shadow darkens in every mood.
- **Hours-of-sun drape** — ``SunHeatmapController.result()``, the map the canvas
  shows, laid on the ground when ``computed`` publishes it
  (``core.scene3d.drape.sun_hours_drape``, the canvas's own ramp). Choosing it
  switches the shared Hours of Sun on (``SunHoursSource``, the toolbar's toggle
  follows), and the drape comes and goes with the shared Hours of Sun — switched on
  in the toolbar it replaces what lay on the ground, switched off it goes: one owner
  of the state; choosing another drape leaves the 2D map alone.
- **Probe** — a click on the ground (the workspace turns the click into a ground
  point) reads the shown map's cell (``SunHoursMap.minutes_at``) and its band
  (``sun_mismatch_service.band_of``); a pin marks the spot.

The rest is drawn from ``core.solar`` and the records:

- **Sun path and compass** — ``core.scene3d.sun_path``: the arcs of the plan date,
  the solstices and the March equinox, the sun as a ball at the sim instant, the
  compass rose with the TRANSLATED cardinal letters (``glyphs``).
- **Day sweep** — the clock's time of day runs from sunrise to sunset of the plan
  date (``SWEEP_STEP_MINUTES`` of wall time every ``SWEEP_INTERVAL_MS``), and the
  hours-of-sun drape fills up as it goes: the map's own per-sample masks, taken by
  their time of day (``SunHoursMap.sample_minutes_of_day``), summed as the sweep
  passes them. At sunset it is the whole map; the clock goes back to the time it
  was started at.
- **Cutaway** — roofs off, and the items the view of the selection passes through
  fade (``core.scene3d.xray``) — recomputed when the selection, the records or the
  resting camera change, never per frame.

Paused while the 3D pane is hidden (``set_active``): flags only, and one refresh
when it shows again. A failure to build a mesh is contained — logged once per kind,
the overlay hidden — and never reaches the event loop.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time
from typing import Any, Final, Protocol

import numpy as np
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from open_garden_planner.core.heatmap_render import build_sun_lut
from open_garden_planner.core.plain_text import log_text
from open_garden_planner.core.scene3d import EngineBuffers, Mesh, engine_buffers
from open_garden_planner.core.scene3d.drape import shadow_drape, sun_hours_drape
from open_garden_planner.core.scene3d.pick_oracle import PartsOf
from open_garden_planner.core.scene3d.sun_path import (
    ARC_KINDS,
    DayArc,
    SunPoint,
    compass_mesh,
    day_arc,
    dome_radius,
    hour_marks,
    key_days,
    probe_pin_mesh,
    sun_path_mesh,
)
from open_garden_planner.core.scene3d.xray import XRAY_OPACITY, XrayScene, occluders, xray_scene
from open_garden_planner.core.shade_aggregation import SunHoursMap
from open_garden_planner.core.sim_clock import SimChange, SimClock, SimInstant
from open_garden_planner.core.solar import solar_position
from open_garden_planner.models.plant_data import SunRequirement
from open_garden_planner.services.sun_mismatch_service import band_of
from open_garden_planner.ui.sim_clock_subscription import connect_qobject

from .analysis_modes import DrapeMode

_LOG: Final = logging.getLogger(__name__)

#: The day sweep: this many minutes of wall time per step, a step this often (ms) —
#: a 16-hour midsummer day in about ten seconds.
SWEEP_STEP_MINUTES: Final = 10
SWEEP_INTERVAL_MS: Final = 100
#: While a sweep runs, the hours-of-sun drape is built with at most this many vertices
#: (a step rebuilds it every ``SWEEP_INTERVAL_MS`` on the GUI thread: 62 ms for a
#: 50 x 50 m garden at the full ``MAX_DRAPE_VERTICES`` — senior review of #386).
SWEEP_MAX_VERTICES: Final = 65_536
#: The host calls the controller makes — and the only ones ``_host_call`` dispatches:
#: a frame-taking call (``grab``) must never slip past the frame-taker scan by name.
HOST_CALLS: Final = frozenset({"set_overlay", "set_roofs_hidden", "set_faded_items"})
_LUT: Final = build_sun_lut()


class AnalysisHost(Protocol):
    """What the analysis needs from the engine host (``Quick3DHost`` has it)."""

    def set_overlay(self, layer: str, mesh: EngineBuffers | None) -> None: ...
    def set_roofs_hidden(self, hidden: bool) -> None: ...
    def set_faded_items(self, item_ids: frozenset[str], opacity: float = ...) -> None: ...


class SunHoursSource(Protocol):
    """The shared Hours of Sun (``ui.live_sun_map.LiveSunMap``) — ONE owner of the
    state: its switch, the signal of the switch, and whether the map it shows is
    current (a dated preview may stand while the plan changed: no measurement then)."""

    enabled: bool
    enabled_changed: Any

    def set_enabled(self, enabled: bool) -> None: ...
    def is_current(self) -> bool: ...


LocationProvider = Callable[[], "Mapping[str, Any] | None"]
#: ``glyphs() -> {bearing: outlines}`` — the compass's translated letters (em units).
GlyphProvider = Callable[[], "Mapping[float, Sequence[Sequence[tuple[float, float]]]]"]


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """What a click on the ground found (module docstring).

    ``reason``: ``"ok"`` (``minutes`` and ``band`` are set), ``"no_map"`` (no
    hours-of-sun map is shown), ``"updating"`` (the shown map is a dated preview of a
    plan that has changed since: its measurements are withdrawn until the new map is
    ready — ADR-056), ``"unavailable"`` (that new map could not be computed),
    ``"outside"`` (the point is outside the map's grid). ``day``: the
    map's day when there is a map.
    """

    east_cm: float
    north_cm: float
    reason: str
    minutes: float | None = None
    band: SunRequirement | None = None
    day: date | None = None


def _latlon(location: Mapping[str, Any] | None) -> tuple[float, float] | None:
    if not isinstance(location, Mapping):
        return None
    latitude, longitude = location.get("latitude"), location.get("longitude")
    try:
        return (float(latitude), float(longitude)) if latitude is not None and longitude is not None else None
    except (TypeError, ValueError):
        return None


class AnalysisController(QObject):
    """The analysis of one 3D engine (module docstring)."""

    #: Something the strip shows changed: the drape, the sun path, Cutaway, the sweep.
    changed = pyqtSignal()
    #: The probe's result changed (``probe_result``; None: no probe).
    probe_changed = pyqtSignal()

    def __init__(self, host: AnalysisHost, clock: SimClock, location: LocationProvider,
                 plan_size: Callable[[], tuple[float, float]], *,
                 glyphs: GlyphProvider | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._host = host
        self._clock = clock
        self._location = location
        self._plan_size = plan_size
        self._glyphs = glyphs
        self._active = False
        self._drape_mode = DrapeMode.NONE
        self._sun_path = False
        self._cutaway = False
        self._shadows: Any = None
        self._heatmap: Any = None
        self._sun_hours: SunHoursSource | None = None
        self._probe: ProbeResult | None = None
        self._probe_point: tuple[float, float] | None = None
        # the lines' cached parts: the arcs (by their inputs), the compass (by size)
        self._arcs_key: tuple[Any, ...] | None = None
        self._arcs: tuple[DayArc, ...] = ()
        self._arcs_mesh: Mesh = Mesh.empty()
        self._compass_key: tuple[float, float] | None = None
        self._compass: Mesh = Mesh.empty()
        # the day sweep
        self._sweep = QTimer(self)
        self._sweep.setInterval(SWEEP_INTERVAL_MS)
        self._sweep.timeout.connect(self._sweep_step)
        self._sweep_end = 0
        self._sweep_minute = 0
        self._sweep_return: time | None = None
        #: True while the sweep writes the clock: any other write ends the sweep
        self._sweep_writing = False
        self._swept_map: SunHoursMap | None = None
        self._swept_order: list[int] = []
        self._swept_minutes: list[int] = []
        self._swept_next = 0
        self._swept_sum: np.ndarray | None = None
        # X-ray
        self._xray_revision: object = None
        self._xray_scene: XrayScene | None = None
        self._faded: frozenset[str] = frozenset()
        #: The overlay layer the drape was last loaded into (None: neither shows).
        self._drape_layer: str | None = None
        #: Failures already logged at WARNING, by what failed (one line per kind).
        self._logged: set[str] = set()
        #: Instruments (tests): overlay loads sent, sweep steps taken.
        self.drape_loads = 0
        self.lines_loads = 0
        connect_qobject(clock.instant_changed, self._on_instant)
        connect_qobject(clock.date_changed, self._on_date)

    # ── wiring ───────────────────────────────────────────────────────────────

    def connect_sources(self, shadows: Any = None, heatmap: Any = None,
                        sun_hours: SunHoursSource | None = None) -> None:
        """The 2D analysis this lays on the ground: the shadow controller (its
        ``drape_polygons()`` / ``shadows_changed``), the heatmap controller (its
        ``result()`` / ``computed`` / ``exposure_changed``) and the shared Hours of Sun
        (``SunHoursSource``), whose switch the hours-of-sun drape follows."""
        self._shadows, self._heatmap, self._sun_hours = shadows, heatmap, sun_hours
        for source, signal, slot in self._source_slots():
            getattr(source, signal).connect(slot)
        if sun_hours is not None and sun_hours.enabled:
            # 3D opened with Hours of Sun already on: its map lies on the ground too
            self._on_sun_hours_switched(True)

    def _source_slots(self) -> list[tuple[Any, str, Callable[..., None]]]:
        slots: list[tuple[Any, str, Callable[..., None]]] = []
        if self._shadows is not None:
            slots.append((self._shadows, "shadows_changed", self._on_shadows))
        if self._heatmap is not None:
            slots.append((self._heatmap, "computed", self._on_computed))
            if hasattr(self._heatmap, "exposure_changed"):
                slots.append((self._heatmap, "exposure_changed", self._on_exposure))
        if self._sun_hours is not None:
            slots.append((self._sun_hours, "enabled_changed", self._on_sun_hours_switched))
        return slots

    def shutdown(self) -> None:
        """Stop for good (the engine goes): a sweep gives the time back, then no timer
        and no source signal reaches this. Contained: the engine's teardown goes on even
        when a clock listener fails on the give-back."""
        try:
            self.stop_sweep()
        except Exception as error:  # noqa: BLE001 - the host must still be closed
            self._sweep.stop()
            self._warn("sweep", error)
        self._active = False
        for source, signal, slot in self._source_slots():
            try:
                getattr(source, signal).disconnect(slot)
            except (RuntimeError, TypeError):
                _LOG.debug("3D analysis: %s was already disconnected", signal)
        self._shadows = self._heatmap = self._sun_hours = None

    # ── reads ────────────────────────────────────────────────────────────────

    @property
    def drape_mode(self) -> DrapeMode:
        return self._drape_mode

    @property
    def sun_path_visible(self) -> bool:
        return self._sun_path

    @property
    def cutaway(self) -> bool:
        return self._cutaway

    @property
    def sweeping(self) -> bool:
        return self._sweep.isActive()

    @property
    def probe_result(self) -> ProbeResult | None:
        return self._probe

    @property
    def faded_items(self) -> frozenset[str]:
        return self._faded

    def has_location(self) -> bool:
        return _latlon(self._location()) is not None

    # ── control ──────────────────────────────────────────────────────────────

    def set_active(self, active: bool) -> None:
        """The 3D pane shows (True) or hides: hidden, nothing is sent; shown again,
        everything is sent once. A sweep stops when the pane hides."""
        if active == self._active:
            return
        self._active = active
        if not active:
            self.stop_sweep()
            return
        self._refresh_drape()
        self._refresh_lines()
        self._host_call("set_roofs_hidden", self._cutaway)
        if not self._cutaway:
            self._faded = frozenset()   # Cutaway went off while hidden: nothing fades
        self._host_call("set_faded_items", self._faded, XRAY_OPACITY)
        # everything that shows the state (menu, legend, card) refreshes with the pane:
        # a date moved while it was hidden left the twin-arc legend stale (senior review
        # round 3)
        self.changed.emit()

    def set_drape_mode(self, mode: DrapeMode) -> None:
        # the shared Hours of Sun decides: choosing its drape always switches it on (the
        # toolbar follows), also when the drape was already chosen and the 2D side has
        # switched off since - a document replace, the toolbar (senior review of #386)
        source = self._sun_hours
        if mode is DrapeMode.SUN_HOURS and source is not None and not source.enabled:
            source.set_enabled(True)
        if mode is self._drape_mode:
            return
        self._drape_mode = mode
        if mode is not DrapeMode.SUN_HOURS:
            self.stop_sweep()
            self.clear_probe()   # the pin and its reading belong to the hours of sun
        self._refresh_drape()
        self.changed.emit()

    def set_sun_path_visible(self, visible: bool) -> None:
        if visible == self._sun_path:
            return
        self._sun_path = visible
        self._refresh_lines()
        self.changed.emit()

    def set_cutaway(self, on: bool) -> None:
        if on == self._cutaway:
            return
        self._cutaway = on
        self._host_call("set_roofs_hidden", on)
        if not on:
            self._fade(frozenset())
        self.changed.emit()

    def document_changed(self) -> None:
        """A new plan: its probe, its sweep, its X-ray scene and its fades go; the
        user's choices (drape, sun path, Cutaway) stay."""
        self.stop_sweep()
        self.clear_probe()
        self._xray_scene = None
        self._xray_revision = None
        # nothing fades in a new plan — also when the pane is hidden now: showing it
        # again re-sends this (``set_active``), so a reopened plan's ids are not born faded
        self._faded = frozenset()
        self._host_call("set_faded_items", self._faded, XRAY_OPACITY)
        self._arcs_key = self._compass_key = None

    def location_changed(self) -> None:
        self._arcs_key = None
        self._refresh_lines()
        self.changed.emit()

    # ── the probe ────────────────────────────────────────────────────────────

    def probe(self, east_cm: float, north_cm: float) -> ProbeResult:
        """Read the shown hours-of-sun map at a ground point and pin it there."""
        self._probe_point = (float(east_cm), float(north_cm))
        result = self._measure(*self._probe_point)
        self._set_probe(result)
        self._refresh_lines()
        return result

    def clear_probe(self) -> None:
        had = self._probe_point is not None
        self._probe_point = None
        self._set_probe(None)
        if had:
            self._refresh_lines()

    def _measure(self, east: float, north: float) -> ProbeResult:
        shown = self._shown_map()
        if shown is None:
            return ProbeResult(east, north, "no_map")
        if not self._map_is_current():
            # a dated preview of a changed plan: shown, never measured (ADR-056); when the
            # new map could not be computed, the reading says so instead of "updating"
            reason = "unavailable" if self._map_failed() else "updating"
            return ProbeResult(east, north, reason, day=shown.day)
        minutes = shown.minutes_at(east, north)
        if minutes is None:
            return ProbeResult(east, north, "outside", day=shown.day)
        return ProbeResult(east, north, "ok", minutes, band_of(minutes), shown.day)

    def _set_probe(self, result: ProbeResult | None) -> None:
        if result != self._probe:
            self._probe = result
            self.probe_changed.emit()

    def _map_is_current(self) -> bool:
        """Whether the shown map measures the plan as it is now (the shared Hours of
        Sun says; without one, the heatmap's own reason)."""
        try:
            if self._sun_hours is not None:
                return bool(self._sun_hours.is_current())
            return getattr(self._heatmap, "exposure_reason", "ready") == "ready"
        except RuntimeError:  # torn down
            return False

    def _map_failed(self) -> bool:
        """Whether the shared Hours of Sun says its map could not be computed."""
        try:
            return bool(getattr(self._sun_hours, "unavailable", False))
        except RuntimeError:  # torn down
            return False

    def _shown_map(self) -> SunHoursMap | None:
        heatmap = self._heatmap
        if heatmap is None:
            return None
        try:
            shown = heatmap.result()
        except RuntimeError:  # the controller is being torn down
            return None
        return shown if isinstance(shown, SunHoursMap) else None

    # ── the day sweep ────────────────────────────────────────────────────────

    def daylight_minutes(self) -> tuple[int, int] | None:
        """The plan date's sunrise and sunset as wall minutes of the day — the whole
        day under the midnight sun — or None (no location, polar night)."""
        place = _latlon(self._location())
        if place is None:
            return None
        arc = day_arc(*place, self._clock.plan_date, self._clock.tz)
        if not arc.segments:
            return None
        tz = self._clock.tz
        first, last = arc.segments[0][0], arc.segments[-1][-1]
        # a run that begins (ends) above the horizon has no sunrise (sunset) that day:
        # the sweep starts at midnight (runs to the day's last minute)
        start = 0 if first.elevation_deg > 0.0 else SimInstant.from_datetime(first.utc, tz).minute_of_day
        end = (24 * 60 - 1 if last.elevation_deg > 0.0
               else SimInstant.from_datetime(last.utc, tz).minute_of_day)
        return (start, end) if start < end else None

    def start_sweep(self) -> bool:
        """Sweep the plan date from sunrise to sunset (module docstring). False when
        there is no day to sweep: no garden location, polar night."""
        span = self.daylight_minutes()
        if span is None:
            return False
        if self._sweep.isActive():
            return True
        self._sweep_return = self._clock.time_of_day
        self._sweep_minute, self._sweep_end = span
        if self._drape_mode is not DrapeMode.SUN_HOURS:
            self.set_drape_mode(DrapeMode.SUN_HOURS)
        self._reset_swept()
        self._sweep.start()
        self._write_time(self._sweep_minute)
        self.changed.emit()
        return True

    def stop_sweep(self, *, give_back: bool = True) -> None:
        """End the sweep: the clock goes back to the time it had (``give_back``; not
        when the user set a time of their own during it — theirs stays)."""
        if not self._sweep.isActive():
            return
        self._sweep.stop()
        back, self._sweep_return = self._sweep_return, None
        if back is not None and give_back:
            self._clock.set_time_of_day(back)
        self._refresh_drape()  # the whole map again
        self.changed.emit()

    def _sweep_step(self) -> None:
        self._sweep_minute += SWEEP_STEP_MINUTES
        if self._sweep_minute > self._sweep_end:
            self.stop_sweep()
            return
        self._write_time(self._sweep_minute)

    def _write_time(self, minute: int) -> None:
        self._sweep_writing = True
        try:
            self._clock.set_time_of_day(time(minute // 60, minute % 60))
        finally:
            self._sweep_writing = False

    def _reset_swept(self) -> None:
        self._swept_map = None
        self._swept_sum = None
        self._swept_next = 0

    def _swept(self, shown: SunHoursMap, minute: int) -> np.ndarray | None:
        """The map summed through ``minute`` — incrementally, sample by sample as the
        sweep passes them; from the morning again for another map or a step back."""
        if not shown.progressive:
            return None
        if (shown is not self._swept_map or self._swept_sum is None
                or (self._swept_next and self._swept_minutes[self._swept_next - 1] > minute)):
            minutes = shown.sample_minutes_of_day(self._clock.tz)
            self._swept_order = sorted(range(len(minutes)), key=minutes.__getitem__)
            self._swept_minutes = [minutes[index] for index in self._swept_order]
            self._swept_map = shown
            self._swept_sum = np.zeros((shown.grid.rows, shown.grid.cols), dtype=np.float32)
            self._swept_next = 0
        total = self._swept_sum
        while (self._swept_next < len(self._swept_order)
               and self._swept_minutes[self._swept_next] <= minute):
            index = self._swept_order[self._swept_next]
            total += np.where(shown.sample_sunlit(index), float(shown.step_minutes), 0.0)
            self._swept_next += 1
        return total.copy()

    # ── Cutaway: X-ray ───────────────────────────────────────────────────────

    def update_xray(self, eye: Sequence[float], selected: Collection[str], revision: object,
                    source: Callable[[], tuple[Mapping[str, Any], PartsOf]]) -> None:
        """Fade what stands between ``eye`` and the selected items (Cutaway on and
        something selected), else nothing. ``revision`` names the records the engine
        holds (the scene is rebuilt from ``source()`` only when it changes)."""
        if not self._cutaway or not selected:
            self._fade(frozenset())
            return
        try:
            if self._xray_scene is None or revision != self._xray_revision:
                records, parts_of = source()
                self._xray_scene = xray_scene(records, parts_of)
                self._xray_revision = revision
            found = occluders(self._xray_scene, eye, selected)
        except Exception as error:  # noqa: BLE001 - a fade must never take the view down
            self._warn("xray", error)
            found = frozenset()
        self._fade(found)

    def _fade(self, items: frozenset[str]) -> None:
        """Tell the host what fades — and remember it only once the host was told (a
        hidden pane tells it nothing; showing again re-sends what is remembered)."""
        if items == self._faded:
            return
        if self._host_call("set_faded_items", items, XRAY_OPACITY):
            self._faded = items

    # ── refresh ──────────────────────────────────────────────────────────────

    def _on_shadows(self) -> None:
        if self._drape_mode is DrapeMode.SHADOWS:
            self._refresh_drape()

    def _on_computed(self, _shown: object) -> None:
        self._reset_swept()
        if self._drape_mode is DrapeMode.SUN_HOURS:
            self._refresh_drape()
        if self._probe_point is not None:
            self._set_probe(self._measure(*self._probe_point))
        self.changed.emit()

    def _on_instant(self, _change: SimChange) -> None:
        if self._sweep.isActive() and not self._sweep_writing:
            # the user (or another writer) set a time: theirs stays, the sweep ends
            self.stop_sweep(give_back=False)
        if self._sweep.isActive() and self._drape_mode is DrapeMode.SUN_HOURS:
            self._refresh_drape()
        if self._sun_path:
            self._refresh_lines()

    def _on_date(self, _day: date) -> None:
        self._reset_swept()
        if self._sweep.isActive():
            # another day has other hours of daylight: the sweep of this one ends. The
            # time goes back a turn later — the clock refuses a write from inside its
            # own notification (ADR-053)
            self._sweep.stop()
            QTimer.singleShot(0, self._give_time_back)
        if self._sun_path:
            self._refresh_lines()
            self.changed.emit()   # the legend says which arcs the plan date's arc covers

    def _give_time_back(self) -> None:
        if self._sweep.isActive():   # a new sweep began in between: the time is its own
            return
        back, self._sweep_return = self._sweep_return, None
        if back is None:
            return
        self._clock.set_time_of_day(back)
        self._refresh_drape()  # the whole map again
        self.changed.emit()

    def _on_sun_hours_switched(self, enabled: bool) -> None:
        """The shared Hours of Sun went on or off (the toolbar, a document replace):
        its drape comes or goes with it — on, it replaces whatever lay on the ground —
        and the menu follows (``changed``). It used to follow only "off": with Hours of
        Sun switched on in the toolbar the canvas showed the map and the 3D ground
        nothing (manual pass of PR #584)."""
        if enabled and self._drape_mode is not DrapeMode.SUN_HOURS:
            self.set_drape_mode(DrapeMode.SUN_HOURS)
        elif not enabled and self._drape_mode is DrapeMode.SUN_HOURS:
            self.set_drape_mode(DrapeMode.NONE)

    def _on_exposure(self) -> None:
        """The heatmap's measurements were withdrawn or published: the probe reads
        again (an edit withdraws them at once, the new map brings them back)."""
        if self._probe_point is not None:
            self._set_probe(self._measure(*self._probe_point))

    def _refresh_drape(self) -> None:
        if not self._active:
            return
        try:
            mesh = self._drape_mesh()
        except Exception as error:  # noqa: BLE001 - contained: the drape is hidden
            self._warn("drape", error)
            mesh = None
        buffers = engine_buffers(mesh) if mesh is not None and mesh.vertex_count else None
        # the 2D shadows MULTIPLY the frame (the "shade" layer: darker in every mood); the
        # hours-of-sun map blends over it ("drape"). Switching empties the other layer.
        layer = "shade" if self._drape_mode is DrapeMode.SHADOWS else "drape"
        if self._drape_layer not in (None, layer) and self._host_call(
                "set_overlay", self._drape_layer, None):
            self._drape_layer = None
        if self._host_call("set_overlay", layer, buffers):
            self._drape_layer = layer if buffers is not None else self._drape_layer
            self.drape_loads += 1

    def _drape_mesh(self) -> Mesh | None:
        mode = self._drape_mode
        if mode is DrapeMode.SHADOWS and self._shadows is not None:
            width, depth = self._plan_size()
            return shadow_drape(self._shadows.drape_polygons(), width, depth)
        if mode is DrapeMode.SUN_HOURS:
            shown = self._shown_map()
            if shown is None:
                return None
            minutes = shown.minutes
            if self._sweep.isActive():
                swept = self._swept(shown, self._clock.instant.minute_of_day)
                if swept is not None:
                    return sun_hours_drape(swept, shown.grid, shown.daylight_minutes, _LUT,
                                           max_vertices=SWEEP_MAX_VERTICES)
            return sun_hours_drape(minutes, shown.grid, shown.daylight_minutes, _LUT)
        return None

    def _refresh_lines(self) -> None:
        if not self._active:
            return
        try:
            mesh = self._lines_mesh()
        except Exception as error:  # noqa: BLE001 - contained: the lines are hidden
            self._warn("lines", error)
            mesh = Mesh.empty()
        buffers = engine_buffers(mesh) if mesh.vertex_count else None
        if self._host_call("set_overlay", "lines", buffers):
            self.lines_loads += 1

    def _lines_mesh(self) -> Mesh:
        width, depth = self._plan_size()
        center = (width / 2.0, depth / 2.0)
        radius = dome_radius(width, depth)
        meshes: list[Mesh] = []
        if self._sun_path:
            if self._compass_key != (width, depth):
                glyphs = self._glyphs() if self._glyphs is not None else None
                self._compass = compass_mesh(center, radius, glyphs)
                self._compass_key = (width, depth)
            meshes.append(self._compass)
            place = _latlon(self._location())
            if place is not None:
                meshes.append(self._arcs_for(place, center, radius))
                position = solar_position(*place, self._clock.utc)
                meshes.append(sun_path_mesh((), center, radius, sun=SunPoint(
                    self._clock.utc, position.elevation_deg, position.azimuth_deg)))
        if self._probe_point is not None:
            meshes.append(probe_pin_mesh(self._probe_point, radius))
        return Mesh.merge(meshes)

    def _arcs_for(self, place: tuple[float, float], center: tuple[float, float],
                  radius: float) -> Mesh:
        key = (place, self._clock.tz, self._clock.plan_date, center, radius)
        if key != self._arcs_key:
            days = key_days(self._clock.plan_date)
            self._arcs = tuple(day_arc(*place, days[kind], self._clock.tz, kind)
                               for kind in ARC_KINDS)
            marks = hour_marks(self._arcs[0], self._clock.tz)
            self._arcs_mesh = sun_path_mesh(self._arcs, center, radius, hour_marks=marks)
            self._arcs_key = key
        return self._arcs_mesh

    def arcs(self) -> tuple[DayArc, ...]:
        """The arcs last drawn (tests; empty before the sun path was first shown)."""
        return self._arcs

    def _host_call(self, name: str, *arguments: object) -> bool:
        """Call the host, contained: an engine that fails here is logged, never raised.
        Only ``HOST_CALLS`` are dispatched (a programming error otherwise)."""
        if name not in HOST_CALLS:
            raise ValueError(f"the analysis makes no host call {name!r}")
        if not self._active:
            return False
        try:
            getattr(self._host, name)(*arguments)
        except Exception as error:  # noqa: BLE001 - the health poll reports a dead host
            self._warn(name, error)
            return False
        return True

    def _warn(self, what: str, error: BaseException) -> None:
        if what in self._logged:
            _LOG.debug("3D analysis: %s failed again (%s)", what, log_text(error))
            return
        self._logged.add(what)
        _LOG.warning("3D analysis: %s failed (%s: %s)", what, log_text(type(error).__name__),
                     log_text(error))


def add_years(day: date, years: int, *, lowest: date, highest: date) -> date:
    """``day`` moved by whole years (the growth jump, L2.3), inside ``lowest`` …
    ``highest``; 29 February lands on 1 March in a year that has none — the rule the
    plan's frost dates follow (ADR-049)."""
    year = min(max(day.year + years, lowest.year), highest.year)
    try:
        moved = day.replace(year=year)
    except ValueError:  # 29 February in a common year
        moved = date(year, 3, 1)
    return min(max(moved, lowest), highest)
