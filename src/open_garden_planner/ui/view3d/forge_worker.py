"""Priority-queued Plant Forge worker for the 3D view (Phase 17 L3.1, #387).

Upgrades synchronous v0 plant silhouettes in an ``EngineSink`` to forged multi-LOD
species models (`core.plant_forge.forge_record`) with two ordering invariants:
1. **Visible plants first**: plants inside the camera's forward hemisphere sort
   ahead of plants behind the camera, ordered by ascending camera distance.
2. **Latest wins**: submitting a newer snapshot or record for ``item_id``
   supersedes any queued request for that ``item_id``, and any completion whose
   ``geometry_sig`` no longer matches the latest snapshot is discarded without
   touching the sink.
"""

from __future__ import annotations

import datetime
import logging
import math
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from ...core.phenology import (
    DEFAULT_LATITUDE_DEG,
    PhenologyState,
    evaluate_phenology_for_records,
)
from ...core.plant_art import PLANT_KINDS, traits_for
from ...core.plant_forge import (
    DEFAULT_FORGE_CACHE,
    PARAM_CLIMBER_SUPPORT,
    ForgeCache,
    climber_support_signature,
    enrich_climber_record,
    forge_record,
    record_forge_spec,
    select_lod,
    validate_lod,
)
from ...core.scene3d import EngineSink, MeshPart, Params, ParamValue, Record
from ...core.scene3d.builders.plants import plant_sprite

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ForgeJob:
    """Queued forge request for a single plant item."""

    item_id: str
    record: Record
    geometry_sig: object
    lod: int
    visible: bool
    distance_cm: float
    generation: int


class ForgeWorker:
    """Queue and apply forged 3D plant upgrades (`visible plants first, latest wins`)."""

    def __init__(
        self,
        sink: EngineSink | None = None,
        *,
        cache: ForgeCache | None = DEFAULT_FORGE_CACHE,
        background: bool = False,
        season_sink: Callable[..., None] | None = None,
    ) -> None:
        self._sink = sink
        self._cache = cache
        self._season_sink: Callable[..., None] | None = season_sink
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="plant-forge") if background else None
        self._flight: tuple[ForgeJob, int, Future[tuple[MeshPart, ...]]] | None = None
        self._extra_flights: list[tuple[ForgeJob, int, Future[tuple[MeshPart, ...]]]] = []
        self._epoch = 0
        self._closed = False
        self._camera_pos: tuple[float, float, float] = (0.0, 0.0, 170.0)
        self._camera_forward: tuple[float, float, float] | None = None
        self._force_lod: int | None = None
        self._path_eyes: NDArray[np.float64] | None = None
        self._generation: int = 0
        self._latest_records: dict[str, Record] = {}
        self._applied_state: dict[str, tuple[object, int, object]] = {}
        self._applied_parts: dict[str, tuple[float, float, tuple[MeshPart, ...]]] = {}
        self._sync_forged: set[str] = set()
        self._pending: dict[str, ForgeJob] = {}
        self._phenology: dict[str, PhenologyState] = {}
        self._plan_date: datetime.date | None = None
        self._latitude_deg: float = DEFAULT_LATITUDE_DEG
        self._scene_records: tuple[Record, ...] = ()
        self._support_inputs: object = None
        self._support_generation = 0
        self._support_lock = threading.RLock()
        self._resolved_input_key: object = None
        self._resolved_supports: dict[str, tuple[object, ParamValue | None]] = {}

    @property
    def pending_count(self) -> int:
        """Number of plant items waiting to be forged."""
        return len(self._pending) + int(self._flight is not None) + len(self._extra_flights)

    def phenology_state(self, item_id: str) -> PhenologyState | None:
        """Return the last evaluated `PhenologyState` for `item_id`."""
        return self._phenology.get(item_id)

    def scrub_date(
        self,
        plan_date: datetime.date,
        *,
        latitude_deg: float = DEFAULT_LATITUDE_DEG,
        last_frost: datetime.date | None = None,
        snow_override: float | None = None,
        frost_dates: Mapping[str, object] | None = None,
    ) -> dict[str, PhenologyState]:
        """Evaluate seasonal shader values for all known plants (`<= 16 ms` for 300 plants, 0 mesh rebuilds)."""
        states = evaluate_phenology_for_records(
            tuple(self._latest_records.values()),
            plan_date,
            latitude_deg=latitude_deg,
            last_frost=last_frost,
            snow_override=snow_override,
            frost_dates=frost_dates,
        )
        self._phenology = dict(states)
        if self._season_sink is not None:
            try:
                self._season_sink(states, plan_date=plan_date)
            except TypeError:
                self._season_sink(states)
        return states

    def clear(self) -> None:
        """Reset all pending jobs and remembered applied states."""
        self._latest_records.clear()
        self._applied_state.clear()
        self._applied_parts.clear()
        self._sync_forged.clear()
        self._pending.clear()
        for _job, _epoch, future in self._extra_flights:
            future.cancel()
        self._extra_flights.clear()
        self._phenology.clear()
        self._scene_records = ()
        self._support_inputs = None
        self._support_generation += 1
        self._epoch += 1
        if self._season_sink is not None:
            self._season_sink({})

    def invalidate(self, item_ids: Iterable[str]) -> None:
        """SceneSync replaced these Models; their remembered forge is no longer shown."""
        for item_id in item_ids:
            if item_id in self._sync_forged:
                self._sync_forged.discard(item_id)
                continue
            self._applied_state.pop(item_id, None)

    def shutdown(self) -> None:
        """Forget scene ownership before a bounded, Qt-free synthesis finishes."""
        self._season_sink = None  # a retiring host may already be closed
        self.clear()
        self._closed = True
        self._sink = None
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None

    def _score_record(self, record: Record) -> tuple[bool, float, int]:
        """Return ``(visible_in_front, distance_cm, lod)`` for ``record``."""
        cx, cy, cz = self._camera_pos
        px = float(record.transform.east_cm)
        py = float(record.transform.north_cm)
        pz = float(record.transform.base_cm) + float(record.height_cm or 0.0) * 0.5
        dx = px - cx
        dy = py - cy
        dz = pz - cz
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)

        visible = True
        if self._camera_forward is not None and dist > 1e-3:
            fx, fy, fz = self._camera_forward
            fnorm = math.sqrt(fx * fx + fy * fy + fz * fz)
            if fnorm > 1e-6:
                cos_angle = (dx * fx + dy * fy + dz * fz) / (dist * fnorm)
                # Treat items inside ~100 deg half-angle cone as visible in front
                visible = cos_angle >= -0.15

        if self._path_eyes is not None:
            dist_for_lod = float(np.linalg.norm(self._path_eyes - (px, py, pz), axis=1).min())
        else:
            dist_for_lod = dist
        lod = self._force_lod if self._force_lod is not None else select_lod(dist_for_lod)
        return visible, dist, lod

    @staticmethod
    def _is_climber(record: Record) -> bool:
        sprite = plant_sprite(record)
        return sprite is not None and traits_for(sprite).archetype == "climber"

    def _structure_key(self, item_id: str) -> object:
        # Appearance never enters a geometry key. Support dependencies do.
        record = self._latest_records.get(item_id)
        return self._support_generation if record is not None and self._is_climber(record) else None

    def _enrich_if_climber(
        self, record: Record, scene_records: tuple[Record, ...], support_inputs: object,
    ) -> Record:
        if not self._is_climber(record):
            return record
        with self._support_lock:
            if support_inputs != self._resolved_input_key:
                self._resolved_input_key = support_inputs
                self._resolved_supports.clear()
            plant_key = climber_support_signature((record,))
            cached = self._resolved_supports.get(record.item_id)
            if cached is None or cached[0] != plant_key:
                enriched = enrich_climber_record(record, scene_records)
                support = enriched.params.get(PARAM_CLIMBER_SUPPORT)
                self._resolved_supports[record.item_id] = plant_key, support
                return enriched
            support = cached[1]
            if support is not None and PARAM_CLIMBER_SUPPORT not in record.params:
                return replace(record, params=Params({**record.params, PARAM_CLIMBER_SUPPORT: support}))
            return record

    def _forge_one(
        self, record: Record, lod: int, scene_records: tuple[Record, ...], support_inputs: object,
    ) -> tuple[MeshPart, ...]:
        """Resolve structural support and synthesize together, off the GUI thread."""
        enriched = self._enrich_if_climber(record, scene_records, support_inputs)
        return forge_record(enriched, lod=lod, cache=self._cache)

    def _remember_applied_parts(
        self, item_id: str, record: Record | None, lod: int, parts: Sequence[MeshPart],
    ) -> None:
        if record is None or not parts:
            return
        spec = record_forge_spec(record, lod=lod, cache=self._cache)
        if spec is not None:
            _sprite, height, radius, _seed, _support, _key = spec
            self._applied_parts[item_id] = (height, radius, tuple(parts))

    def prepare_for_sync(
        self,
        records: Mapping[str, Record],
        build_ids: Iterable[str],
    ) -> dict[str, tuple[MeshPart, ...]]:
        """Provide forged plant geometry directly to ``SceneSync.apply(prepared=...)`` (#995).

        Never downgrades an already-forged or cache-warm plant to a v0 silhouette
        (``build_silhouette``) when its height or spread grows on a date step:
        1. If the plant's 2 % size bucket is already in ``self._cache``, stretch and
           return the forged mesh immediately and mark it applied so ``invalidate`` does
           not re-queue it.
        2. If the plant crossed into a cold 2 % size bucket and was already forged on
           screen, stretch its last forged mesh to the new height and spread for the
           immediate frame while the background worker synthesizes the new bucket.
        """
        if self._closed:
            return {}
        ids = tuple(build_ids)
        if not ids:
            return {}
        scene_records = tuple(records.values())
        support_inputs = climber_support_signature(scene_records)
        if support_inputs != self._support_inputs:
            self._support_inputs = support_inputs
            self._support_generation += 1
            self._epoch += 1
        self._scene_records = scene_records
        scene_already_forged = bool(self._applied_parts)
        prepared: dict[str, tuple[MeshPart, ...]] = {}
        for item_id in ids:
            record = records.get(item_id)
            if record is None or record.kind not in PLANT_KINDS:
                continue
            _visible, _dist, auto_lod = self._score_record(record)
            lod = self._force_lod if self._force_lod is not None else auto_lod
            enriched = self._enrich_if_climber(record, scene_records, support_inputs)
            spec = record_forge_spec(enriched, lod=lod, cache=self._cache)
            if spec is None:
                continue
            _sprite, height, radius, _seed, _support, key = spec
            if self._cache is not None and self._cache.contains(key):
                try:
                    parts = forge_record(enriched, lod=lod, cache=self._cache)
                except Exception:
                    _log.exception("Plant Forge cache hit failed for item %s", item_id)
                    continue
                prepared[item_id] = parts
                self._latest_records[item_id] = record
                self._applied_state[item_id] = (
                    record.geometry_sig,
                    lod,
                    self._structure_key(item_id),
                )
                self._applied_parts[item_id] = (height, radius, parts)
                self._pending.pop(item_id, None)
                self._sync_forged.add(item_id)
            elif item_id in self._applied_parts:
                old_h, old_r, old_parts = self._applied_parts[item_id]
                if old_h > 0.0 and old_r > 0.0 and old_parts:
                    sx = radius / old_r
                    sz = height / old_h
                    stretched = tuple(
                        replace(part, mesh=part.mesh.scaled(sx, sx, sz))
                        for part in old_parts
                    )
                    prepared[item_id] = stretched
                    self._applied_parts[item_id] = (height, radius, stretched)
            elif scene_already_forged and item_id not in self._latest_records:
                # A dated plant crossing its planting_date into an already-forged scene
                # is forged immediately so it never flashes a v0 silhouette (#995).
                try:
                    parts = forge_record(enriched, lod=lod, cache=self._cache)
                except Exception:
                    _log.exception("Plant Forge live-entry build failed for item %s", item_id)
                    continue
                prepared[item_id] = parts
                self._latest_records[item_id] = record
                self._applied_state[item_id] = (
                    record.geometry_sig,
                    lod,
                    self._structure_key(item_id),
                )
                self._applied_parts[item_id] = (height, radius, parts)
                self._pending.pop(item_id, None)
                self._sync_forged.add(item_id)
        return prepared

    def submit_record(self, record: Record, *, lod: int | None = None) -> None:
        """Submit or supersede a single plant ``record`` (`latest wins`)."""
        if self._closed or record.kind not in PLANT_KINDS:
            return
        self._generation += 1
        self._latest_records[record.item_id] = record
        visible, dist, auto_lod = self._score_record(record)
        chosen_lod = validate_lod(lod) if lod is not None else auto_lod
        sig = record.geometry_sig
        s_key = self._structure_key(record.item_id)

        if self._applied_state.get(record.item_id) == (sig, chosen_lod, s_key):
            self._pending.pop(record.item_id, None)
            return

        for running, epoch, _future in (
            *([self._flight] if self._flight is not None else ()),
            *self._extra_flights,
        ):
            if (epoch == self._epoch and running.item_id == record.item_id
                    and running.geometry_sig == sig and running.lod == chosen_lod):
                self._pending.pop(record.item_id, None)
                return

        self._pending[record.item_id] = ForgeJob(
            item_id=record.item_id,
            record=record,
            geometry_sig=sig,
            lod=chosen_lod,
            visible=visible,
            distance_cm=dist,
            generation=self._generation,
        )

    def submit_snapshot(
        self,
        records: Iterable[Record],
        *,
        camera_pos: tuple[float, float, float] | None = None,
        camera_forward: tuple[float, float, float] | None = None,
        force_lod: int | None = None,
        plan_date: datetime.date | None = None,
        latitude_deg: float = DEFAULT_LATITUDE_DEG,
        frost_dates: Mapping[str, object] | None = None,
    ) -> None:
        """Update queue from a full scene snapshot (`visible plants first, latest wins`)."""
        if camera_pos is not None:
            self._camera_pos = (
                float(camera_pos[0]),
                float(camera_pos[1]),
                float(camera_pos[2]),
            )
        if camera_forward is not None:
            self._camera_forward = (
                float(camera_forward[0]),
                float(camera_forward[1]),
                float(camera_forward[2]),
            )
        if force_lod is not None:
            self._force_lod = validate_lod(force_lod)

        self._plan_date = plan_date
        self._latitude_deg = float(latitude_deg)

        scene_records = tuple(records)
        support_inputs = climber_support_signature(scene_records)
        if support_inputs != self._support_inputs:
            self._support_inputs = support_inputs
            self._support_generation += 1
            self._epoch += 1  # an old support result cannot enter a new structural scene
        self._scene_records = scene_records
        plant_records = {r.item_id: r for r in scene_records if r.kind in PLANT_KINDS}

        if plan_date is not None:
            self._phenology = dict(
                evaluate_phenology_for_records(
                    tuple(plant_records.values()),
                    plan_date,
                    latitude_deg=self._latitude_deg,
                    frost_dates=frost_dates,
                )
            )
        else:
            self._phenology.clear()
        if self._season_sink is not None:
            try:
                self._season_sink(self._phenology, plan_date=plan_date)
            except TypeError:
                self._season_sink(self._phenology)

        # Prune removed items
        for stale_id in list(self._latest_records):
            if stale_id not in plant_records:
                self._latest_records.pop(stale_id, None)
                self._applied_state.pop(stale_id, None)
                self._applied_parts.pop(stale_id, None)
                self._sync_forged.discard(stale_id)
                self._pending.pop(stale_id, None)

        for record in plant_records.values():
            self.submit_record(record, lod=self._force_lod)

    def update_camera(
        self,
        camera_pos: tuple[float, float, float],
        camera_forward: tuple[float, float, float] | None = None,
        *,
        force_lod: int | None = None,
    ) -> None:
        """Re-prioritise pending jobs and queue LOD switches for the new camera pose."""
        self._camera_pos = (
            float(camera_pos[0]),
            float(camera_pos[1]),
            float(camera_pos[2]),
        )
        self._camera_forward = (
            (
                float(camera_forward[0]),
                float(camera_forward[1]),
                float(camera_forward[2]),
            )
            if camera_forward is not None
            else None
        )
        if force_lod is not None:
            self._force_lod = validate_lod(force_lod)

        for record in list(self._latest_records.values()):
            self.submit_record(record, lod=self._force_lod)

    def fly_path(self, eyes: Sequence[tuple[float, float, float]] | None) -> None:
        """A recording is about to fly past ``eyes`` (L6, ADR-072): each plant takes the finest
        detail any of them asks for and keeps it, so that a frame shows what the view would from
        there and no plant changes its leaves in mid-flight. ``None``: the camera decides again.

        Ending a flight also drops the flight's own in-flight build (``_epoch``): its LOD came
        from a camera that has gone, and applying it would leave that one plant fine until the
        camera next moved (#738)."""
        ending = not eyes
        self._path_eyes = np.asarray(eyes, dtype=np.float64) if eyes else None
        if ending:
            self._epoch += 1   # an in-flight flight job no longer belongs to this scene
        for record in list(self._latest_records.values()):
            self.submit_record(record, lod=self._force_lod)

    def pending_order(self) -> list[str]:
        """Return pending ``item_id``s sorted with visible plants first, closest first."""
        ordered = sorted(
            self._pending.values(),
            key=lambda j: (0 if j.visible else 1, j.distance_cm, -j.generation, j.item_id),
        )
        return [j.item_id for j in ordered]

    def _sink_holds(self, item_id: str) -> bool:
        """Whether the sink still holds ``item_id`` — asked where it can answer.

        A sink reset (a fresh engine, a recovery, a document switch) forgets every
        item; a forge completion that was in flight then has nothing to replace and
        must be dropped, not raised on (#718: the retry livelocked the workspace)."""
        known = getattr(self._sink, "item_ids", None)
        return known is None or item_id in known()

    def apply_completed(
        self,
        item_id: str,
        geometry_sig: object,
        lod: int,
        parts: Sequence[MeshPart],
    ) -> bool:
        """Apply a completed forge build if ``(item_id, geometry_sig)`` is still current."""
        latest = self._latest_records.get(item_id)
        if latest is None or latest.geometry_sig != geometry_sig:
            # Stale completion superseded by a newer edit or deletion ("latest wins")
            return False

        pending = self._pending.get(item_id)
        if pending is not None and pending.lod != lod:
            return False
        if self._sink is not None and not self._sink_holds(item_id):
            return False

        if self._sink is not None:
            self._sink.begin()
            self._sink.replace_geometry(item_id, tuple(parts))
            self._sink.commit()
        self._pending.pop(item_id, None)
        self._applied_state[item_id] = (geometry_sig, lod, self._structure_key(item_id))
        self._remember_applied_parts(item_id, latest, lod, parts)
        return True

    def step(self, max_items: int = 1) -> list[str]:
        """Forge and apply up to ``max_items`` highest-priority plants."""
        if max_items < 1 or (not self._pending and self._flight is None and not self._extra_flights):
            return []

        if self._executor is not None:
            return self._step_background(max_items=max_items)

        ids = self.pending_order()[:max_items]
        upgraded: list[tuple[str, tuple[MeshPart, ...], object, int, object, Record]] = []

        for item_id in ids:
            job = self._pending.pop(item_id, None)
            if job is None:
                continue
            latest = self._latest_records.get(item_id)
            if latest is None or latest.geometry_sig != job.geometry_sig:
                continue
            try:
                parts = self._forge_one(latest, job.lod, self._scene_records, self._support_inputs)
            except Exception:
                _log.exception("Plant Forge failed for item %s", item_id)
                continue
            upgraded.append(
                (item_id, parts, job.geometry_sig, job.lod, self._structure_key(item_id), latest)
            )

        if not upgraded:
            return []
        if self._sink is not None:
            upgraded = [job for job in upgraded if self._sink_holds(job[0])]
            if not upgraded:
                return []

        if self._sink is not None:
            self._sink.begin()
            for item_id, parts, _sig, _lod, _s_key, _rec in upgraded:
                self._sink.replace_geometry(item_id, parts)
            self._sink.commit()
        for item_id, parts, sig, lod, s_key, rec in upgraded:
            self._applied_state[item_id] = (sig, lod, s_key)
            self._remember_applied_parts(item_id, rec, lod, parts)

        return [item_id for item_id, _, _, _, _, _ in upgraded]

    def _step_background(self, max_items: int = 1) -> list[str]:
        """Poll Qt-free syntheses, apply completed ones on the owner thread, and start the next."""
        applied: list[str] = []
        if max_items <= 1 and not self._extra_flights:
            if self._flight is not None:
                job, epoch, future = self._flight
                if not future.done():
                    return applied
                self._flight = None
                try:
                    parts = future.result()
                except Exception:
                    _log.exception("Plant Forge failed for item %s", job.item_id)
                else:
                    if epoch == self._epoch and self.apply_completed(
                        job.item_id, job.geometry_sig, job.lod, parts
                    ):
                        applied.append(job.item_id)
            if self._pending and self._executor is not None:
                item_id = self.pending_order()[0]
                job = self._pending.pop(item_id)
                future = self._executor.submit(
                    self._forge_one, job.record, job.lod, self._scene_records, self._support_inputs,
                )
                self._flight = job, self._epoch, future
            return applied

        all_flights = [
            *([self._flight] if self._flight is not None else ()),
            *self._extra_flights,
        ]
        still_running: list[tuple[ForgeJob, int, Future[tuple[MeshPart, ...]]]] = []
        ready: list[tuple[str, object, int, tuple[MeshPart, ...], Record]] = []
        for entry in all_flights:
            job, epoch, future = entry
            if not future.done():
                still_running.append(entry)
                continue
            try:
                parts = future.result()
            except Exception:
                _log.exception("Plant Forge failed for item %s", job.item_id)
                continue
            if epoch != self._epoch:
                continue
            latest = self._latest_records.get(job.item_id)
            if latest is None or latest.geometry_sig != job.geometry_sig:
                continue
            pending = self._pending.get(job.item_id)
            if pending is not None and pending.lod != job.lod:
                continue
            if self._sink is not None and not self._sink_holds(job.item_id):
                continue
            ready.append((job.item_id, job.geometry_sig, job.lod, parts, latest))

        self._flight = still_running[0] if still_running else None
        self._extra_flights = still_running[1:]

        # Also harvest any warm cache hits at the front of the queue in the same turn (#995).
        if self._cache is not None and self._pending and len(ready) < max_items:
            for item_id in self.pending_order():
                if len(ready) >= max_items:
                    break
                job = self._pending.get(item_id)
                if job is None:
                    continue
                latest = self._latest_records.get(item_id)
                if latest is None or latest.geometry_sig != job.geometry_sig:
                    self._pending.pop(item_id, None)
                    continue
                enriched = self._enrich_if_climber(latest, self._scene_records, self._support_inputs)
                spec = record_forge_spec(enriched, lod=job.lod, cache=self._cache)
                if spec is None or not self._cache.contains(spec[5]):
                    continue
                self._pending.pop(item_id, None)
                if self._sink is not None and not self._sink_holds(item_id):
                    continue
                try:
                    parts = forge_record(enriched, lod=job.lod, cache=self._cache)
                except Exception:
                    _log.exception("Plant Forge failed for item %s", item_id)
                    continue
                ready.append((item_id, job.geometry_sig, job.lod, parts, latest))

        if ready:
            if self._sink is not None:
                self._sink.begin()
                for item_id, _sig, _lod, parts, _latest in ready:
                    self._sink.replace_geometry(item_id, parts)
                self._sink.commit()
            for item_id, sig, lod, parts, latest in ready:
                self._pending.pop(item_id, None)
                self._applied_state[item_id] = (sig, lod, self._structure_key(item_id))
                self._remember_applied_parts(item_id, latest, lod, parts)
                applied.append(item_id)

        if self._pending and self._executor is not None:
            in_flight = int(self._flight is not None) + len(self._extra_flights)
            to_submit = max(0, max_items - in_flight)
            for item_id in self.pending_order()[:to_submit]:
                job = self._pending.pop(item_id)
                future = self._executor.submit(
                    self._forge_one, job.record, job.lod, self._scene_records, self._support_inputs,
                )
                entry = (job, self._epoch, future)
                if self._flight is None:
                    self._flight = entry
                else:
                    self._extra_flights.append(entry)
        return applied

    def drain(self, batch_size: int = 8) -> list[str]:
        """Process all pending plant forge jobs in priority order."""
        done: list[str] = []
        while self._pending:
            batch = self.step(max_items=batch_size)
            if not batch:
                break
            done.extend(batch)
        return done


__all__ = [
    "ForgeJob",
    "ForgeWorker",
]
