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
import math
from collections.abc import Callable, Sequence
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from PyQt6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QWidget,
)

from open_garden_planner.core.object_height import casts_2d_shadow, effective_height_cm
from open_garden_planner.core.object_types import PathFenceStyle
from open_garden_planner.core.roof_style import (
    BUILDING_KINDS,
    roof_overhang_cm,
    roof_pitch_deg,
    roof_style,
)
from open_garden_planner.core.scene3d import (
    PARAM_RIDGE,
    ccw,
    is_buildable_region,
    local_frame,
    pose_point,
    quantize_cm,
    ring_area,
)
from open_garden_planner.core.scene3d.builders.buildings import pitched_roof_triangles
from open_garden_planner.core.scene3d.builders.fences import POROUS_FENCE_STYLES
from open_garden_planner.core.scene3d.builders.lines import DEFAULT_SOLID
from open_garden_planner.core.scene3d.record import (
    PARAM_ROOF_OVERHANG,
    PARAM_ROOF_PITCH,
    PARAM_ROOF_STYLE,
)
from open_garden_planner.core.shade_aggregation import IdentifiedCaster
from open_garden_planner.core.shadow_geometry import (
    MIN_SUN_ELEVATION_DEG,
    Point,
    Polygon,
    ShadowCaster,
    Triangle3D,
    WeightedShadowRegion,
    compute_scene_shadows,
    compute_weighted_shadows,
    shadow_region,
)
from open_garden_planner.core.sim_clock import SimChange, SimClock
from open_garden_planner.core.solar import solar_position
from open_garden_planner.ui.sim_clock_subscription import connect_qobject

from .footprints import (
    OUTLINE_POLYGON,
    OUTLINE_POLYLINE,
    OUTLINE_RECTANGLE,
    ItemLookup,
    footprints_can_self_cross,
    holds_plants,
    item_base_cm,
    item_footprints,
    item_outline,
)
from .items.polyline_item import PolylineItem

# Simulation states (stable identifiers — user-visible hints live in the app).
STATE_DISABLED = "disabled"
STATE_NO_LOCATION = "no_location"
STATE_NIGHT = "night"
STATE_ACTIVE = "active"

# Above the background image (-1000) and the ground surfaces (a lawn, a path, an
# in-ground bed: ``canvas_scene.GROUND_Z_RANGE``), below every other layer item
# (>= 0): a shadow lies ON the ground, under what casts it.
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
        self._weighted_regions: tuple[WeightedShadowRegion, ...] = ()
        self._region_paths: tuple[tuple[QPainterPath, QColor], ...] = ()

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
        if path.isEmpty():
            self._weighted_regions = ()
            self._region_paths = ()
        self._rebuild_feather()

    def set_weighted_regions(self, regions: Sequence[WeightedShadowRegion]) -> None:
        """Cache pre-partitioned weighted shadow regions for porous/opaque painting."""
        self._weighted_regions = tuple(regions)
        built: list[tuple[QPainterPath, QColor]] = []
        base_alpha = _SHADOW_COLOR.alpha()
        for reg in self._weighted_regions:
            if not reg.polygons or reg.occlusion <= 0.0:
                continue
            reg_path = QPainterPath()
            reg_path.setFillRule(Qt.FillRule.OddEvenFill)
            for polygon in reg.polygons:
                reg_path.addPolygon(QPolygonF([QPointF(x, y) for x, y in polygon]))
                reg_path.closeSubpath()
            color = QColor(_SHADOW_COLOR)
            color.setAlpha(max(1, min(255, round(base_alpha * reg.occlusion))))
            built.append((reg_path, color))
        self._region_paths = tuple(built)
        self.update()

    def weighted_regions(self) -> tuple[WeightedShadowRegion, ...]:
        """The weighted shadow regions currently painted on the overlay."""
        return self._weighted_regions

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
        painter: QPainter | None,
        _option: QStyleOptionGraphicsItem | None,
        _widget: QWidget | None = None,
    ) -> None:
        if painter is None:
            return
        path = self.path()
        if path.isEmpty():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # Soft outward penumbra — only outside the shadow's own fill area, so
        # the interior stays flat and there is no darker ring at the boundary.
        region = self._feather_region
        if region is not None and not region.isEmpty():
            max_occ = max((r.occlusion for r in self._weighted_regions), default=1.0)
            painter.save()
            painter.setClipPath(region)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for pen in _FEATHER_PENS:
                if max_occ < 0.999:
                    scaled_pen = QPen(pen)
                    c = QColor(pen.color())
                    c.setAlpha(max(1, round(c.alpha() * max_occ)))
                    scaled_pen.setColor(c)
                    painter.setPen(scaled_pen)
                else:
                    painter.setPen(pen)
                painter.drawPath(path)
            painter.restore()
        # Solid core, hard-cut at the canvas boundary.
        painter.save()
        if self._clip_rect is not None:
            painter.setClipRect(self._clip_rect)
        painter.setPen(Qt.PenStyle.NoPen)
        if self._region_paths and not (
            len(self._weighted_regions) == 1
            and abs(self._weighted_regions[0].occlusion - 1.0) < 1e-6
        ):
            for reg_path, reg_color in self._region_paths:
                painter.setBrush(QBrush(reg_color))
                painter.drawPath(reg_path)
        else:
            painter.setBrush(QBrush(_SHADOW_COLOR))
            painter.drawPath(path)
        painter.restore()


# The footprint extraction lives in ``ui/canvas/footprints.py`` since Phase 17
# L1.1 (#385) — its public home, shared with the 3D pipeline. (Two private aliases
# here served the Qt 3D view's tests and the L0 spike's; they left with both in L1.10.)


def _shadow_footprints(item: Any, at_date: date | None) -> list[Polygon]:
    """An item's footprint set as the rings its shadow sweep can take (#444).

    ``shadow_region`` repairs a closed stroke's hole and a self-crossing outline;
    both need ``pyclipper`` work, so the walk asks for it only where the extractor
    can have produced one: more than one ring, or the one shape whose outline is
    the user's own vertex order (``footprints.footprints_can_self_cross``). A
    circle's, ellipse's or rectangle's ring is simple by construction and comes
    back untouched — which is what keeps the walk's cost where it was.
    """
    raw = item_footprints(item, at_date)
    if len(raw) > 1 or footprints_can_self_cross(item):
        return shadow_region(raw)
    return raw


def _fence_porosity_info(
    item: Any,
    kind: str,
    metadata: dict[str, Any],
    at_date: date | None,
) -> tuple[str | None, tuple[Point, ...], float]:
    """Extract porous fence style, scene-space centreline points, and stroke width (#440)."""
    if kind not in ("FENCE", "WALL") or not isinstance(item, PolylineItem):
        return None, (), 0.0
    style_enum = getattr(item, "path_fence_style", PathFenceStyle.NONE)
    if style_enum is not PathFenceStyle.NONE:
        raw_style = style_enum.name
    elif metadata.get("smart_symbol_plain_panel"):
        raw_style = "PLAIN"
    else:
        raw_style = DEFAULT_SOLID.get(kind, "WOODEN_FENCE")
    if raw_style not in POROUS_FENCE_STYLES:
        return None, (), 0.0
    outline = item_outline(item, at_date)
    if outline is None or outline.shape != OUTLINE_POLYLINE or len(outline.points) < 2:
        return raw_style, (), 0.0
    pts: list[Point] = []
    for lx, ly in outline.points:
        sp = item.mapToScene(QPointF(lx, ly))
        pts.append((float(sp.x()), float(sp.y())))
    return raw_style, tuple(pts), float(outline.width_cm or 1.0)


@lru_cache(maxsize=128)
def _cached_roof_triangles(
    kind: str,
    shape: str,
    local_ring: tuple[tuple[float, float], ...],
    height: float,
    style: str | None,
    pitch: float | None,
    overhang: float | None,
    ridge: tuple[tuple[float, float], tuple[float, float]] | None,
) -> tuple[Triangle3D, ...]:
    """The pitched roof's LOCAL triangles for one geometry, built once (#701).

    A 150-shed plan asked the 3D roof builder for the same shed's mesh 750 times in one
    walk (1.37 s of a 5.7 s profile, all but 150 of them repeats); the cache key is the
    complete geometry, so an edited roof is a new key and never a stale hit. The
    triangles stay in the record's local frame — the caller poses them, so the same
    mesh serves every identical shed wherever it stands. 128 entries cover the distinct
    roof shapes of a hand-built plan; each holds one building's triangles."""
    params: dict[str, Any] = {}
    if style is not None:
        params[PARAM_ROOF_STYLE] = style
    if pitch is not None:
        params[PARAM_ROOF_PITCH] = pitch
    if overhang is not None:
        params[PARAM_ROOF_OVERHANG] = overhang
    if ridge is not None:
        params[PARAM_RIDGE] = ridge
    return pitched_roof_triangles(kind, shape, local_ring, height, params=params)


def _building_roof_triangles(
    item: Any,
    kind: str,
    metadata: dict[str, Any],
    height: float,
    ridge_item: Any,
    at_date: date | None,
) -> tuple[Triangle3D, ...]:
    """Extract scene-space pitched-roof triangles for a building caster (#440)."""
    if kind not in BUILDING_KINDS:
        return ()
    outline = item_outline(item, at_date)
    if outline is None or outline.shape not in (OUTLINE_POLYGON, OUTLINE_RECTANGLE):
        return ()
    if len(outline.points) < 3:
        return ()
    matrix = item.sceneTransform()
    frame = local_frame(
        matrix.m11(),
        matrix.m12(),
        matrix.m21(),
        matrix.m22(),
        matrix.dx(),
        matrix.dy(),
        outline.anchor[0],
        outline.anchor[1],
        rotatable=True,
    )
    if not math.isfinite(frame.east_cm + frame.north_cm):
        return ()
    local_ring = ccw(frame.local_ring(outline.points))
    if len(local_ring) < 3 or ring_area(local_ring) == 0.0:
        return ()
    if footprints_can_self_cross(item) and not is_buildable_region(local_ring):
        return ()
    style = roof_style(metadata)
    pitch = roof_pitch_deg(metadata)
    overhang = roof_overhang_cm(metadata)
    ridge: tuple[tuple[float, float], tuple[float, float]] | None = None
    if kind == "HOUSE" and isinstance(ridge_item, PolylineItem) and len(ridge_item.points) >= 2:
        p0 = ridge_item.mapToScene(ridge_item.points[0])
        p1 = ridge_item.mapToScene(ridge_item.points[-1])
        e0 = frame.local_from_scene(p0.x(), p0.y())
        e1 = frame.local_from_scene(p1.x(), p1.y())
        if math.isfinite(e0[0] + e0[1] + e1[0] + e1[1]):
            ridge = (e0, e1)
    try:
        local_tris = _cached_roof_triangles(
            kind,
            outline.shape,
            tuple((round(x, 6), round(y, 6)) for x, y in local_ring),
            round(float(height), 6),
            style,
            None if pitch is None else round(float(pitch), 6),
            None if overhang is None else round(float(quantize_cm(overhang)), 6),
            None if ridge is None else ((round(ridge[0][0], 6), round(ridge[0][1], 6)),
                                        (round(ridge[1][0], 6), round(ridge[1][1], 6))),
        )
    except Exception:  # a hostile outline must not take the overlay down (as before)
        return ()
    if not local_tris:
        return ()
    tf = frame.transform(0.0)
    scene_tris: list[Triangle3D] = []
    for v0, v1, v2 in local_tris:
        sx0, sy0 = pose_point(tf, v0[0], v0[1])
        sx1, sy1 = pose_point(tf, v1[0], v1[1])
        sx2, sy2 = pose_point(tf, v2[0], v2[1])
        scene_tris.append(((sx0, sy0, v0[2]), (sx1, sy1, v1[2]), (sx2, sy2, v2[2])))
    return tuple(scene_tris)


_last_identified: tuple[int, date | None, list[IdentifiedCaster]] | None = None


def collect_identified_casters(
    scene: QGraphicsScene,
    at_date: date | None = None,
) -> list[IdentifiedCaster]:
    """THE caster walk: every visible item with an effective height, as one
    ``IdentifiedCaster`` per item — its id, its solid footprints, its height and
    where it stands.

    The shadow overlay, the hours-of-sun heatmap and the per-plant sun estimates
    all come from this walk (``collect_shadow_casters`` flattens it), so they can
    never disagree. Plain-data output — the snapshot shape the heatmap worker
    thread consumes (never live QGraphicsItems). ``at_date`` (US-E8) projects
    dated plants to their grown height AND canopy spread at that date.
    ``item_id`` keeps ownership for own-shadow exclusion (US-F3). ``base_cm``
    (Phase 17 L1.6, ADR-037 addendum) is where the item stands: 0 on the ground,
    the soil surface for a plant in a raised bed or container
    (``footprints.item_base_cm`` — the rule the 3D records use too).

    The footprints are the item's REGION, not its raw ring list: a fence that
    closes on itself hands out an outer ring and a hole, and
    ``core.shadow_geometry.shadow_region`` repairs that (and a self-crossing
    outline) into simple rings here, where the item is still known (#444). A
    hole swept on its own would cast the enclosed garden as a slab.
    ``holds_plants`` marks a soil solid a plant can stand in
    (``core.object_height.is_solid_soil_parent``): the sun estimate spares such
    a solid for a plant inside its outline, because it is under the plant, not
    between it and the sun (#481).
    """
    global _last_identified
    casters: list[IdentifiedCaster] = []
    items = scene.items()
    lookup = ItemLookup(items)
    for item in items:
        if not item.isVisible():
            continue
        object_type = getattr(item, "object_type", None)
        if object_type is None or not casts_2d_shadow(object_type):
            continue   # a string of lights casts no 2D shadow (L5.4, owner's decision)
        metadata = getattr(item, "metadata", None)
        meta_dict = metadata if isinstance(metadata, dict) else {}
        if meta_dict.get("smart_symbol_guide"):
            continue
        height = effective_height_cm(
            object_type, metadata, at_date=at_date
        )
        if height is None:
            continue
        footprints = tuple(
            tuple(footprint)
            for footprint in _shadow_footprints(item, at_date)
            if len(footprint) >= 3)
        if footprints:
            kind = str(getattr(object_type, "name", object_type))
            fence_style, fence_points, fence_width_cm = _fence_porosity_info(
                item, kind, meta_dict, at_date
            )
            roof_tris: tuple[Triangle3D, ...] = ()
            if kind in BUILDING_KINDS and len(footprints) == 1:
                ridge_id = meta_dict.get("ridge_item_id") if kind == "HOUSE" else None
                ridge_item = lookup.get(ridge_id) if ridge_id else None
                # A copied/stale link must not let this house use another's
                # ridge; the ownership rule is shared with the 2D lookup and
                # the 3D snapshot (is_owned_ridge).
                if ridge_item is not None:
                    from open_garden_planner.ui.canvas.roof_ridge_link import (
                        is_owned_ridge,
                    )

                    if not is_owned_ridge(item, ridge_item):
                        ridge_item = None
                roof_tris = _building_roof_triangles(
                    item, kind, meta_dict, height, ridge_item, at_date
                )
            casters.append(IdentifiedCaster(
                str(getattr(item, "item_id", id(item))), footprints, height,
                item_base_cm(item, lookup, at_date),
                holds_plants=holds_plants(item, at_date),
                roof_triangles=roof_tris,
                fence_style=fence_style,
                fence_points=fence_points,
                fence_width_cm=fence_width_cm,
            ))
    _last_identified = (id(scene), at_date, casters)
    return casters


def collect_shadow_casters(
    scene: QGraphicsScene,
    at_date: date | None = None,
) -> list[ShadowCaster]:
    """The walk's casters as ``ShadowCaster``s — ``(footprint, height_cm,
    base_cm)``, one per solid footprint: what the shadow overlay unions. Derived
    from ``collect_identified_casters``; there is no second walk."""
    return [ShadowCaster(list(footprint), caster.height_cm, caster.base_cm)
            for caster in collect_identified_casters(scene, at_date)
            for footprint in caster.footprints]


class SunShadowController(QObject):
    """Computes and paints the unioned solar shadow overlay.

    ``location_provider`` returns the project's location dict (or None) so
    the controller never holds a stale copy — the same indirection the
    status-bar label uses. ``clock`` is the session's one sim clock (the app
    passes its own); without one the controller makes a private clock.
    """

    state_changed = pyqtSignal(str)
    #: The shadow the overlay paints changed (Phase 17 L2.1, #386): ``drape_polygons()``
    #: has new polygons. The 3D drape listens — it never computes a shadow itself.
    shadows_changed = pyqtSignal()

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
        # Through ``connect_qobject`` (L1.3): the channel cannot see Qt destroy
        # this object with its parent, and would call into the dead slot.
        connect_qobject(self._clock.instant_changed, self._on_clock_changed)
        self._overlay: SunShadowOverlayItem | None = None
        self._state = STATE_DISABLED
        self._last_key: tuple[Any, ...] | None = None
        #: What the overlay paints, as plain polygons (scene cm): the shadows' union,
        #: the whole canvas at night, nothing while it shows nothing.
        self._polygons: tuple[tuple[tuple[float, float], ...], ...] = ()
        #: Weighted shadow regions (with porous fence occlusion weights, #440).
        self._regions: tuple[WeightedShadowRegion, ...] = ()
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

    def drape_polygons(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        """The polygons the overlay paints right now (scene cm; even-odd: outers CCW,
        holes CW) — the union of every caster's shadow, the whole canvas at night,
        nothing while the overlay shows nothing. NOT yet cut at the canvas: the
        overlay clips when it paints, and so does the 3D drape that lays these on the
        ground (Phase 17 L2.1, ``core.scene3d.drape.shadow_drape``)."""
        return self._polygons

    def drape_regions(self) -> tuple[WeightedShadowRegion, ...]:
        """The weighted shadow regions the overlay paints right now (#440)."""
        return self._regions

    def _publish(
        self,
        polygons: tuple[tuple[tuple[float, float], ...], ...],
        regions: tuple[WeightedShadowRegion, ...] = (),
    ) -> None:
        if polygons != self._polygons or regions != self._regions:
            self._polygons = polygons
            self._regions = regions
            self.shadows_changed.emit()

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
        global _last_identified
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
        _last_identified = None
        casters = collect_shadow_casters(
            self._scene, at_date=self._clock.plan_date
        )
        identified: list[IdentifiedCaster] = (
            _last_identified[2]
            if _last_identified is not None
            and _last_identified[0] == id(self._scene)
            and _last_identified[1] == self._clock.plan_date
            else []
        )
        canvas_key = (
            (round(canvas_rect.width(), 3), round(canvas_rect.height(), 3))
            if canvas_rect is not None
            else None
        )
        enriched_key = tuple(
            (c.roof_triangles, c.fence_style, c.fence_points, c.fence_width_cm, c.transmittance)
            for c in identified
        )
        key = (
            round(position.elevation_deg, 4),
            round(position.azimuth_deg, 4),
            canvas_key,
            # the base too: a bed that keeps its footprint but changes what its
            # plants stand on must not be skipped as "nothing changed"
            tuple((tuple(c.footprint), c.height_cm, c.base_cm) for c in casters),
            enriched_key,
        )
        overlay = self._alive_overlay()
        if key == self._last_key and overlay is not None and overlay.isVisible():
            self._set_state(STATE_ACTIVE)
            return
        has_enriched = any(
            c.roof_triangles or c.fence_style is not None or c.transmittance is not None
            for c in identified
        )
        if has_enriched:
            weighted = compute_weighted_shadows(
                identified, position.elevation_deg, position.azimuth_deg
            )
            assert weighted is not None
            polygons = weighted.union_polygons
            regions = tuple(weighted.weighted_regions)
        else:
            polygons = compute_scene_shadows(
                casters, position.elevation_deg, position.azimuth_deg
            )
            regions = (
                (WeightedShadowRegion(polygons, occlusion=1.0, transmittance=0.0),)
                if polygons
                else ()
            )
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        for polygon in polygons:
            path.addPolygon(QPolygonF([QPointF(x, y) for x, y in polygon]))
            path.closeSubpath()
        overlay = self._ensure_overlay()
        overlay.set_clip_rect(canvas_rect)
        overlay.set_shadow_path(path)
        overlay.set_weighted_regions(regions)
        overlay.setVisible(True)
        self._last_key = key
        self.recompute_count += 1
        self._publish(
            tuple(tuple((float(x), float(y)) for x, y in polygon) for polygon in polygons),
            regions,
        )
        self._set_state(STATE_ACTIVE)

    # ── internals ──────────────────────────────────────────────

    def _on_scene_changed(self, _regions: list[QRectF] | None = None) -> None:
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
        self._publish(())

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
        left, top, right, bottom = (canvas_rect.left(), canvas_rect.top(), canvas_rect.right(),
                                    canvas_rect.bottom())
        night_poly = ((left, top), (right, top), (right, bottom), (left, bottom))
        night_regions = (WeightedShadowRegion([list(night_poly)], occlusion=1.0, transmittance=0.0),)
        overlay.set_weighted_regions(night_regions)
        overlay.setVisible(True)
        self._last_key = night_key
        self.recompute_count += 1
        self._publish((night_poly,), night_regions)

    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)
