"""Pest & disease log service (US-12.7).

Thin facade over ``ProjectManager`` that returns ``PestDiseaseLog`` /
``PestDiseaseRecord`` objects instead of raw dicts. Tracks active issues
(``resolved_date is None``) across all targets for the Dashboard panel.

Mirrors the shape of ``SoilService`` (US-12.10) — no Qt signals here; the
project manager emits ``pest_disease_logs_changed`` whenever this service
mutates its state.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from open_garden_planner.models.pest_disease import (
    PestDiseaseLog,
    PestDiseaseRecord,
)

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager


class PestDiseaseService:
    """Read/write access to pest/disease logs stored on a ``ProjectManager``."""

    def __init__(self, project_manager: ProjectManager) -> None:
        self._pm = project_manager

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_log(self, target_id: str) -> PestDiseaseLog:
        """Return the log for ``target_id`` (empty if no records yet)."""
        raw = self._pm.pest_disease_logs.get(target_id)
        if raw is None:
            return PestDiseaseLog(target_id=target_id)
        return PestDiseaseLog.from_dict(raw)

    def get_active_issues(self) -> list[tuple[str, PestDiseaseRecord]]:
        """All unresolved records across every target.

        Returns a list of ``(target_id, record)`` tuples sorted by descending
        date — newest issues first. The caller is responsible for resolving
        ``target_id`` to a human-readable bed/plant name (the service has no
        scene access).
        """
        result: list[tuple[str, PestDiseaseRecord]] = []
        for target_id, raw in self._pm.pest_disease_logs.items():
            log = PestDiseaseLog.from_dict(raw)
            for record in log.active:
                result.append((target_id, record))
        result.sort(key=lambda pair: pair[1].date, reverse=True)
        return result

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_record(self, target_id: str, record: PestDiseaseRecord) -> None:
        """Append ``record`` to the log for ``target_id`` and mark dirty."""
        log = self.get_log(target_id)
        log.records.append(record)
        self._pm.set_pest_disease_log(target_id, log)

    def update_record(self, target_id: str, record: PestDiseaseRecord) -> None:
        """Replace the record with the same ``id`` in the target's log.

        No-op if the id is not present (defensive — should not happen via UI).
        """
        log = self.get_log(target_id)
        for idx, existing in enumerate(log.records):
            if existing.id == record.id:
                log.records[idx] = record
                self._pm.set_pest_disease_log(target_id, log)
                return

    def delete_record(self, target_id: str, record_id: str) -> None:
        """Delete the record with ``record_id`` from the target's log."""
        log = self.get_log(target_id)
        log.records = [r for r in log.records if r.id != record_id]
        self._pm.set_pest_disease_log(target_id, log)
