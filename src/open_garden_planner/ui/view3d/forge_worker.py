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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

import numpy as np

from ...core.phenology import (
    DEFAULT_LATITUDE_DEG,
    PhenologyState,
    evaluate_phenology_for_records,
)
from ...core.plant_art import PLANT_KINDS
from ...core.plant_forge import (
    DEFAULT_FORGE_CACHE,
    PART_ACCENTS,
    PART_FOLIAGE,
    PART_WOOD,
    ForgeCache,
    enrich_climber_records,
    forge_record,
    select_lod,
    validate_lod,
)
from ...core.scene3d import EngineSink, Mesh, MeshPart, Record

_log = logging.getLogger(__name__)


def apply_seasonal_appearance(
    parts: Sequence[MeshPart],
    state: PhenologyState | None,
) -> tuple[MeshPart, ...]:
    """Modulate forged ``parts`` by seasonal ``state`` (winter bare wood, autumn foliage, seasonal accents)."""
    if state is None:
        return tuple(parts)

    has_wood = any(p.name == PART_WOOD for p in parts)
    out: list[MeshPart] = []

    for part in parts:
        if part.name == PART_WOOD:
            out.append(part)
        elif part.name == PART_FOLIAGE:
            if state.leaf_density <= 0.05 and has_wood:
                # Deciduous woody plant in winter dormancy: bare branch skeleton only
                continue
            if state.autumn_color > 0.05:
                m = part.mesh
                colors = m.colors.copy()
                # Blend linear RGB toward warm autumn amber/gold while keeping per-vertex variation
                autumn_target = np.array([0.55, 0.18, 0.03], dtype=np.float32)
                w = float(min(max(state.autumn_color * 0.80, 0.0), 0.85))
                colors[:, :3] = (1.0 - w) * colors[:, :3] + w * autumn_target[None, :]
                new_mesh = Mesh(
                    positions=m.positions,
                    normals=m.normals,
                    colors=colors,
                    uvs=m.uvs,
                    indices=m.indices,
                )
                out.append(replace(part, mesh=new_mesh))
            else:
                out.append(part)
        elif part.name == PART_ACCENTS:
            if state.leaf_density <= 0.05:
                continue
            if state.bloom > 0.10 or state.ripeness > 0.10:
                out.append(part)
        else:
            out.append(part)

    return tuple(out) if out else tuple(parts)


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
    ) -> None:
        self._sink = sink
        self._cache = cache
        self._camera_pos: tuple[float, float, float] = (0.0, 0.0, 170.0)
        self._camera_forward: tuple[float, float, float] | None = None
        self._force_lod: int | None = None
        self._generation: int = 0
        self._latest_records: dict[str, Record] = {}
        self._applied_state: dict[str, tuple[object, int, object]] = {}
        self._pending: dict[str, ForgeJob] = {}
        self._phenology: dict[str, PhenologyState] = {}
        self._plan_date: datetime.date | None = None
        self._latitude_deg: float = DEFAULT_LATITUDE_DEG

    @property
    def pending_count(self) -> int:
        """Number of plant items waiting to be forged."""
        return len(self._pending)

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
    ) -> dict[str, PhenologyState]:
        """Evaluate seasonal shader values for all known plants (`<= 16 ms` for 300 plants, 0 mesh rebuilds)."""
        states = evaluate_phenology_for_records(
            tuple(self._latest_records.values()),
            plan_date,
            latitude_deg=latitude_deg,
            last_frost=last_frost,
            snow_override=snow_override,
        )
        self._phenology = dict(states)
        return states

    def clear(self) -> None:
        """Reset all pending jobs and remembered applied states."""
        self._latest_records.clear()
        self._applied_state.clear()
        self._pending.clear()
        self._phenology.clear()

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

        lod = self._force_lod if self._force_lod is not None else select_lod(dist)
        return visible, dist, lod

    def _season_key(self, item_id: str) -> object:
        if self._plan_date is None:
            return None
        state = self._phenology.get(item_id)
        if state is None:
            return None
        return (
            round(state.leaf_density * 10.0),
            round(state.bloom * 5.0),
            round(state.ripeness * 5.0),
            round(state.autumn_color * 10.0),
        )

    def submit_record(self, record: Record, *, lod: int | None = None) -> None:
        """Submit or supersede a single plant ``record`` (`latest wins`)."""
        if record.kind not in PLANT_KINDS:
            return
        self._generation += 1
        self._latest_records[record.item_id] = record
        visible, dist, auto_lod = self._score_record(record)
        chosen_lod = validate_lod(lod) if lod is not None else auto_lod
        sig = record.geometry_sig
        s_key = self._season_key(record.item_id)

        if self._applied_state.get(record.item_id) == (sig, chosen_lod, s_key):
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

        enriched = enrich_climber_records(records)
        plant_records = {r.item_id: r for r in enriched if r.kind in PLANT_KINDS}

        if plan_date is not None:
            self._phenology = dict(
                evaluate_phenology_for_records(
                    tuple(plant_records.values()),
                    plan_date,
                    latitude_deg=self._latitude_deg,
                )
            )

        # Prune removed items
        for stale_id in list(self._latest_records):
            if stale_id not in plant_records:
                self._latest_records.pop(stale_id, None)
                self._applied_state.pop(stale_id, None)
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

    def pending_order(self) -> list[str]:
        """Return pending ``item_id``s sorted with visible plants first, closest first."""
        ordered = sorted(
            self._pending.values(),
            key=lambda j: (0 if j.visible else 1, j.distance_cm, -j.generation, j.item_id),
        )
        return [j.item_id for j in ordered]

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

        self._pending.pop(item_id, None)
        self._applied_state[item_id] = (geometry_sig, lod, self._season_key(item_id))
        if self._sink is not None:
            self._sink.begin()
            try:
                self._sink.replace_geometry(item_id, tuple(parts))
            finally:
                self._sink.commit()
        return True

    def step(self, max_items: int = 1) -> list[str]:
        """Forge and apply up to ``max_items`` highest-priority plants."""
        if max_items < 1 or not self._pending:
            return []

        ids = self.pending_order()[:max_items]
        upgraded: list[tuple[str, tuple[MeshPart, ...], object, int, object]] = []

        for item_id in ids:
            job = self._pending.pop(item_id, None)
            if job is None:
                continue
            latest = self._latest_records.get(item_id)
            if latest is None or latest.geometry_sig != job.geometry_sig:
                continue
            try:
                parts = forge_record(latest, lod=job.lod, cache=self._cache)
                if self._plan_date is not None:
                    parts = apply_seasonal_appearance(parts, self._phenology.get(item_id))
            except Exception:
                _log.exception("Plant Forge failed for item %s", item_id)
                continue
            upgraded.append(
                (item_id, parts, job.geometry_sig, job.lod, self._season_key(item_id))
            )

        if not upgraded:
            return []

        if self._sink is not None:
            self._sink.begin()
            try:
                for item_id, parts, sig, lod, s_key in upgraded:
                    self._sink.replace_geometry(item_id, parts)
                    self._applied_state[item_id] = (sig, lod, s_key)
            finally:
                self._sink.commit()
        else:
            for item_id, _parts, sig, lod, s_key in upgraded:
                self._applied_state[item_id] = (sig, lod, s_key)

        return [item_id for item_id, _, _, _, _ in upgraded]

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
    "apply_seasonal_appearance",
]
