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
- All math happens in scene cm via the Qt-free ``core/shadow_geometry``;
  scene +y is already North — there is NO extra Y-flip here (§8.20).
- Timer starts are guarded with ``contextlib.suppress(RuntimeError)`` — the
  #230 teardown trap (a ``scene.changed`` slot firing into a half-torn-down
  C++ timer aborts the interpreter in CI).
"""

from __future__ import annotations

import contextlib
import math
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from PyQt6.QtCore import QObject, QPointF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import QGraphicsPathItem, QGraphicsScene

from open_garden_planner.core.object_height import effective_height_cm
from open_garden_planner.core.shadow_geometry import (
    MIN_SUN_ELEVATION_DEG,
    Polygon,
    circle_footprint,
    compute_scene_shadows,
    polyline_footprint,
)
from open_garden_planner.core.solar import solar_position

# Simulation states (stable identifiers — user-visible hints live in the app).
STATE_DISABLED = "disabled"
STATE_NO_LOCATION = "no_location"
STATE_NIGHT = "night"
STATE_ACTIVE = "active"

# Above the background image (-1000), below every layer item (>= 0).
_OVERLAY_Z = -500.0

# Semi-transparent cool grey-blue — reads as shade over any ground color.
_SHADOW_COLOR = QColor(38, 50, 78, 80)

_DEBOUNCE_MS = 150
_ELLIPSE_SEGMENTS = 24


class SunShadowOverlayItem(QGraphicsPathItem):
    """Marker subclass — identifiable by tests, invisible to the serializer.

    Not a ``GardenItemMixin``: it must never gain an ``object_type``, join a
    layer, or be picked up by ``project._serialize_item``'s whitelist.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setZValue(_OVERLAY_Z)
        self.setBrush(QBrush(_SHADOW_COLOR))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


def _item_footprints(item: Any) -> list[Polygon]:
    """Scene-space footprint polygon(s) of one canvas item.

    Vertices are mapped through the item's own transform (``mapToScene``),
    so rotation/position are Qt's answer, not a re-derivation — the
    #218/#219 geometry lessons.
    """
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    if isinstance(item, CircleItem):
        center = item.mapToScene(item.center)
        return [circle_footprint(center.x(), center.y(), item.radius)]
    if isinstance(item, EllipseItem):
        rect = item.rect()
        cx, cy = rect.center().x(), rect.center().y()
        rx, ry = rect.width() / 2.0, rect.height() / 2.0
        if rx <= 0 or ry <= 0:
            return []
        step = 2.0 * math.pi / _ELLIPSE_SEGMENTS
        points = [
            item.mapToScene(
                QPointF(cx + rx * math.cos(i * step), cy + ry * math.sin(i * step))
            )
            for i in range(_ELLIPSE_SEGMENTS)
        ]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, RectangleItem):
        rect = item.rect()
        corners = [rect.topLeft(), rect.topRight(), rect.bottomRight(), rect.bottomLeft()]
        points = [item.mapToScene(c) for c in corners]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, PolygonItem):
        polygon = item.polygon()
        points = [item.mapToScene(polygon.at(i)) for i in range(polygon.count())]
        return [[(p.x(), p.y()) for p in points]]
    if isinstance(item, PolylineItem):
        points = [item.mapToScene(p) for p in item.points]
        width = item.pen().widthF()
        if width <= 0:
            width = 1.0
        return polyline_footprint([(p.x(), p.y()) for p in points], width)
    return []


def collect_shadow_casters(
    scene: QGraphicsScene,
) -> list[tuple[Polygon, float]]:
    """Snapshot every visible item with an effective height as (footprint, h).

    Plain-data output — the same snapshot shape the US-E4 worker thread
    consumes (never live QGraphicsItems).
    """
    casters: list[tuple[Polygon, float]] = []
    for item in scene.items():
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None:
            continue
        height = effective_height_cm(object_type, getattr(item, "metadata", None))
        if height is None:
            continue
        for footprint in _item_footprints(item):
            if len(footprint) >= 3:
                casters.append((footprint, height))
    return casters


class SunShadowController(QObject):
    """Computes and paints the unioned solar shadow overlay.

    ``location_provider`` returns the project's location dict (or None) so
    the controller never holds a stale copy — the same indirection the
    status-bar label uses.
    """

    state_changed = pyqtSignal(str)

    def __init__(
        self,
        scene: QGraphicsScene,
        location_provider: Callable[[], dict[str, Any] | None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scene = scene
        self._location_provider = location_provider
        self._enabled = False
        self._sim_dt_utc = datetime.now(UTC)
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
    def sim_datetime_utc(self) -> datetime:
        return self._sim_dt_utc

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
        """Set the simulated instant (timezone-aware; stored as UTC)."""
        if dt.tzinfo is None:
            raise ValueError("sim datetime must be timezone-aware")
        self._sim_dt_utc = dt.astimezone(UTC)
        if self._enabled:
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
        position = solar_position(latitude, longitude, self._sim_dt_utc)
        if position.elevation_deg < MIN_SUN_ELEVATION_DEG:
            self._clear_overlay()
            self._set_state(STATE_NIGHT)
            return
        casters = collect_shadow_casters(self._scene)
        key = (
            round(position.elevation_deg, 4),
            round(position.azimuth_deg, 4),
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
        overlay.setPath(path)
        overlay.setVisible(True)
        self._last_key = key
        self.recompute_count += 1
        self._set_state(STATE_ACTIVE)

    # ── internals ──────────────────────────────────────────────

    def _on_scene_changed(self, _regions: list | None = None) -> None:
        self.schedule_recompute()

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
            overlay.setPath(QPainterPath())
            overlay.setVisible(False)

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
