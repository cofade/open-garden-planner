"""Runtime-only solar shadow overlay for the canvas (US-E3, #258).

Owns the sun & shade simulation state: the sim instant (UTC), the enabled
flag, and one runtime-only ``QGraphicsPathItem`` overlay holding the unioned
shadow path of every item with an effective height (US-E2 resolver).

Design constraints (campaign fences):

- Shadows are PRECOMPUTED here — never in ``paint()``. Scene changes are
  debounced (150 ms, the companion/spacing precedent) and a snapshot key
  (sun position + caster geometry) skips rebuilds when nothing relevant
  changed — this also breaks the feedback loop where the overlay's own
  ``setPath`` re-fires ``QGraphicsScene.changed``.
- The overlay is NEVER serialized: ``project._serialize_item`` whitelists
  item classes, and the integration test pins that a save/load round-trip
  carries no overlay (the #219 lesson: runtime visuals must not perturb
  save-time geometry).
- The overlay is CLIPPED to the canvas bounds (a long shadow is cut off at
  the garden edge, never spilling onto the grey area outside) and painted
  with a soft, effect-free outward feather; at night (sun below the horizon)
  the whole canvas is shaded rather than the shadows vanishing.
- All math happens in scene cm via the Qt-free ``core/shadow_geometry``;
  scene +y is already North — there is NO extra Y-flip here (§8.20).
- The sim moment is NOT owned here (Phase 17 L1.0, ADR-053): the controller
  reads the one ``core/sim_clock.SimClock`` — ``utc`` for the sun,
  ``plan_date`` (the toolbar's LOCAL day) for growth — and recomputes on its
  ``instant_changed``. The app passes its clock; a standalone controller
  (tests) makes a private one.
- Timer starts are guarded with ``contextlib.suppress(RuntimeError)`` — the
  #230 teardown trap (a ``scene.changed`` slot firing into a half-torn-down
  C++ timer aborts the interpreter in CI).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.shadow_geometry import (
    MIN_SUN_ELEVATION_DEG,
    Polygon,
    compute_scene_shadows,
)
from open_garden_planner.core.sim_clock import SimChange, SimClock
from open_garden_planner.core.solar import solar_position

from .footprints import item_footprints, plant_canopy_radius_cm

# Simulation states (stable identifiers — user-visible hints live in the app).
STATE_DISABLED = "disabled"
STATE_NO_LOCATION = "no_location"
STATE_NIGHT = "night"
STATE_ACTIVE = "active"

# Above the background image (-1000), below every layer item (>= 0).
_OVERLAY_Z = -500.0

# Semi-transparent cool grey-blue — reads as shade over any ground color.
# Slightly deeper + more opaque than the first cut (manual-test feedback).
_SHADOW_COLOR = QColor(30, 41, 66, 110)

# Effect-free soft edge (the scene deliberately avoids QGraphicsEffect): a few
# translucent strokes of the shadow colour, widest/faintest first, painted only
# OUTSIDE the shadow's own fill so the interior stays flat and an outward
# penumbra shows. Widths in scene cm — the halo reaches ~half the widest width
# past the edge.
_FEATHER_STEPS: tuple[tuple[float, int], ...] = (
    (14.0, 16),
    (9.0, 30),
    (5.0, 48),
    (2.5, 66),
)
_FEATHER_MAX_WIDTH = 14.0

_DEBOUNCE_MS = 150


def _build_feather_pens() -> tuple[QPen, ...]:
    """The feather strokes are constant — build them once, not every paint()."""
    pens = []
    for width_cm, alpha in _FEATHER_STEPS:
        color = QColor(_SHADOW_COLOR)
        color.setAlpha(alpha)
        pen = QPen(color)
        pen.setWidthF(width_cm)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pens.append(pen)
    return tuple(pens)


_FEATHER_PENS: tuple[QPen, ...] = _build_feather_pens()


class SunShadowOverlayItem(QGraphicsPathItem):
    """Runtime-only shadow overlay — identifiable by tests, never serialized.

    Not a ``GardenItemMixin``: it must never gain an ``object_type``, join a
    layer, or be picked up by ``project._serialize_item``'s whitelist.

    Painting adds two effect-free niceties (the scene deliberately avoids
    ``QGraphicsEffect`` — see ``canvas_scene``):

    - a HARD clip to the canvas bounds, so a long shadow is simply cut off at
      the garden edge instead of spilling onto the grey outside area;
    - a SOFT outward penumbra, clipped to the area *outside* the shadow so
      the interior stays a flat tone (no darker ring) and only a feather
      shows past the edge.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(_OVERLAY_Z)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self._clip_rect: QRectF | None = None
        self._feather_region: QPainterPath | None = None

    def set_clip_rect(self, rect: QRectF | None) -> None:
        """Bound all painting to ``rect`` (the canvas); None = unbounded."""
        new_rect = QRectF(rect) if rect is not None else None
        if new_rect == self._clip_rect:
            return
        self.prepareGeometryChange()
        self._clip_rect = new_rect
        self._rebuild_feather()
        self.update()

    def set_shadow_path(self, path: QPainterPath) -> None:
        """Set the shadow path and refresh the cached feather region."""
        self.setPath(path)  # base path + prepareGeometryChange + update
        self._rebuild_feather()

    def _rebuild_feather(self) -> None:
        """Cache the outward-feather clip region (canvas minus shadow).

        Computed on change, never in ``paint()`` — the recompute-discipline
        rule extends to the overlay's own edge softening.
        """
        path = self.path()
        if self._clip_rect is None or path.isEmpty():
            self._feather_region = None
            return
        clip = QPainterPath()
        clip.addRect(self._clip_rect)
        self._feather_region = clip.subtracted(path)

    def boundingRect(self) -> QRectF:
        # Painted area is the shadow path plus its outward feather, all clipped
        # to the canvas — never the unclipped shadow tail that runs past the
        # edge. Report a tight superset so itemsBoundingRect()/fit-to-view stay
        # honest.
        rect = super().boundingRect().adjusted(
            -_FEATHER_MAX_WIDTH,
            -_FEATHER_MAX_WIDTH,
            _FEATHER_MAX_WIDTH,
            _FEATHER_MAX_WIDTH,
        )
        if self._clip_rect is not None:
            rect = rect.intersected(self._clip_rect)
        return rect

    def paint(
        self,
        painter: QPainter,
        _option: QStyleOptionGraphicsItem,
        _widget: QWidget | None = None,
    ) -> None:
        path = self.path()
        if path.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Soft outward penumbra — only outside the shadow's own fill area, so
        # the interior stays flat and there is no darker ring at the boundary.
        region = self._feather_region
        if region is not None and not region.isEmpty():
            painter.save()
            painter.setClipPath(region)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for pen in _FEATHER_PENS:
                painter.setPen(pen)
                painter.drawPath(path)
            painter.restore()
        # Solid core, hard-cut at the canvas boundary.
        painter.save()
        if self._clip_rect is not None:
            painter.setClipRect(self._clip_rect)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_SHADOW_COLOR))
        painter.drawPath(path)
        painter.restore()


# The footprint extraction lives in ``ui/canvas/footprints.py`` since Phase 17
# L1.1 (#385) — its public home, shared with the 3D pipeline. These two private
# names stay ONLY because ``tests/integration/test_3d_view.py`` and
# ``tests/unit/test_spike_q3d_board.py`` import them and those suites are frozen
# until L1.10 removes Qt 3D and the spike; new code imports the public names.
_item_footprints = item_footprints
_plant_canopy_radius_cm = plant_canopy_radius_cm


def collect_shadow_casters(
    scene: QGraphicsScene,
    at_date: date | None = None,
) -> list[tuple[Polygon, float]]:
    """Snapshot every visible item with an effective height as (footprint, h).

    Plain-data output — the same snapshot shape the US-E4 worker thread
    consumes (never live QGraphicsItems). ``at_date`` (US-E8) projects
    dated plants to their grown height AND canopy spread at that date.
    """
    casters: list[tuple[Polygon, float]] = []
    for item in scene.items():
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        height = effective_height_cm(
            object_type, getattr(item, "metadata", None), at_date=at_date
        )
        if height is None:
            continue
        for footprint in item_footprints(item, at_date):
            if len(footprint) >= 3:
                casters.append((footprint, height))
    return casters


class SunShadowController(QObject):
    """Computes and paints the unioned solar shadow overlay.

    ``location_provider`` returns the project's location dict (or None) so
    the controller never holds a stale copy — the same indirection the
    status-bar label uses. ``clock`` is the session's one sim clock (the app
    passes its own); without one the controller makes a private clock.
    """

    state_changed = pyqtSignal(str)

    def __init__(
        self,
        scene: QGraphicsScene,
        location_provider: Callable[[], dict[str, Any] | None],
        parent: QObject | None = None,
        *,
        clock: SimClock | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._location_provider = location_provider
        self._enabled = False
        self._clock = clock if clock is not None else SimClock()
        # Qt-free channel (ADR-053): like a Qt connection it holds this bound
        # method weakly, so controller → clock → controller is no reference
        # cycle and an unparented controller dies with its last reference.
        self._clock.instant_changed.connect(self._on_clock_changed)
        self._overlay: SunShadowOverlayItem | None = None
        self._state = STATE_DISABLED
        self._last_key: tuple[Any, ...] | None = None
        #: Effective overlay rebuilds — the #206-style recompute instrument.
        self.recompute_count = 0
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(_DEBOUNCE_MS)
        self._debounce.timeout.connect(self.recompute_now)
        scene.changed.connect(self._on_scene_changed)

    # ── public API ─────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def state(self) -> str:
        return self._state

    @property
    def clock(self) -> SimClock:
        return self._clock

    @property
    def sim_datetime_utc(self) -> datetime:
        """The sim instant in UTC — read from the clock, never a private copy."""
        return self._clock.utc

    def set_enabled(self, enabled: bool) -> None:
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            self.recompute_now()
        else:
            self._clear_overlay()
            self._set_state(STATE_DISABLED)

    def set_sim_datetime(self, dt: datetime) -> None:
        """Write a timezone-aware instant to the clock (which re-solves the sun).

        Kept for standalone use; in the app the toolbar writes the clock
        directly. An unchanged instant still re-solves, as it always did.
        """
        if dt.tzinfo is None:
            raise ValueError("sim datetime must be timezone-aware")
        if self._clock.set_datetime(dt) is None and self._enabled:
            self.recompute_now()

    def schedule_recompute(self) -> None:
        """Debounced recompute — wire scene/stack change signals here."""
        if not self._enabled:
            return
        with contextlib.suppress(RuntimeError):  # #230 teardown guard
            self._debounce.start()

    def recompute_now(self) -> None:
        """Recompute the overlay immediately (empty states short-circuit)."""
        if not self._enabled:
            return
        location = self._location_provider()
        latitude = location.get("latitude") if isinstance(location, dict) else None
        longitude = location.get("longitude") if isinstance(location, dict) else None
        if latitude is None or longitude is None:
            self._clear_overlay()
            self._set_state(STATE_NO_LOCATION)
            return
        position = solar_position(latitude, longitude, self._clock.utc)
        canvas_rect = self._canvas_rect()
        if position.elevation_deg < MIN_SUN_ELEVATION_DEG:
            # Night: the whole garden lies in shade — not "no shadow". Fill the
            # canvas rather than clearing it (US-E3 manual-test follow-up).
            self._show_night_overlay(canvas_rect)
            self._set_state(STATE_NIGHT)
            return
        # US-E8: the sim clock doubles as the growth timeline — dated plants
        # cast their date-projected (grown) shadows. L1.0: grown for the plan's
        # LOCAL date (the heatmap's and 3D's), no longer the instant's UTC date.
        casters = collect_shadow_casters(
            self._scene, at_date=self._clock.plan_date
        )
        canvas_key = (
            (round(canvas_rect.width(), 3), round(canvas_rect.height(), 3))
            if canvas_rect is not None
            else None
        )
        key = (
            round(position.elevation_deg, 4),
            round(position.azimuth_deg, 4),
            canvas_key,
            tuple((tuple(fp), h) for fp, h in casters),
        )
        overlay = self._alive_overlay()
        if key == self._last_key and overlay is not None and overlay.isVisible():
            self._set_state(STATE_ACTIVE)
            return
        polygons = compute_scene_shadows(
            casters, position.elevation_deg, position.azimuth_deg
        )
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for polygon in polygons:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in polygon]))
            path.closeSubpath()
        overlay = self._ensure_overlay()
        overlay.set_clip_rect(canvas_rect)
        overlay.set_shadow_path(path)
        overlay.setVisible(True)
        self._last_key = key
        self.recompute_count += 1
        self._set_state(STATE_ACTIVE)

    # ── internals ──────────────────────────────────────────────

    def _on_scene_changed(self, _regions: list | None = None) -> None:
        self.schedule_recompute()

    def _on_clock_changed(self, _change: SimChange) -> None:
        """Any new sim instant (date or time) moves the sun: re-solve now."""
        if self._enabled:
            self.recompute_now()

    def _alive_overlay(self) -> SunShadowOverlayItem | None:
        """The overlay if its C++ object still lives in our scene, else None.

        ``scene.clear()`` (project load/new) deletes items wholesale; touching
        the stale wrapper would raise RuntimeError, so probe defensively and
        drop the reference — the next recompute recreates the overlay.
        """
        overlay = self._overlay
        if overlay is None:
            return None
        try:
            if overlay.scene() is not self._scene:
                self._overlay = None
                return None
        except RuntimeError:  # underlying C++ object deleted by scene.clear()
            self._overlay = None
            return None
        return overlay

    def _ensure_overlay(self) -> SunShadowOverlayItem:
        overlay = self._alive_overlay()
        if overlay is None:
            overlay = SunShadowOverlayItem()
            self._scene.addItem(overlay)
            self._overlay = overlay
        return overlay

    def _clear_overlay(self) -> None:
        self._last_key = None
        overlay = self._alive_overlay()
        if overlay is not None and overlay.isVisible():
            overlay.set_shadow_path(QPainterPath())
            overlay.setVisible(False)

    def _canvas_rect(self) -> QRectF | None:
        """The garden canvas bounds in scene cm (None for a plain scene)."""
        rect = getattr(self._scene, "canvas_rect", None)
        return rect if isinstance(rect, QRectF) else None

    def _show_night_overlay(self, canvas_rect: QRectF | None) -> None:
        """Shade the whole canvas — the sun is below the horizon.

        The shadows do not vanish at night; the entire garden is dark. With no
        canvas bounds (a plain scene) there is nothing sensible to fill, so
        fall back to clearing.
        """
        if canvas_rect is None:
            self._clear_overlay()
            return
        night_key = (
            "night",
            round(canvas_rect.width(), 3),
            round(canvas_rect.height(), 3),
        )
        overlay = self._alive_overlay()
        if night_key == self._last_key and overlay is not None and overlay.isVisible():
            return
        path = QPainterPath()
        path.addRect(canvas_rect)
        overlay = self._ensure_overlay()
        overlay.set_clip_rect(canvas_rect)
        overlay.set_shadow_path(path)
        overlay.setVisible(True)
        self._last_key = night_key
        self.recompute_count += 1

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
