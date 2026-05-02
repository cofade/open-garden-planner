"""Soil-test service (US-12.10a).

Thin facade over ``ProjectManager`` that returns ``SoilTestHistory`` /
``SoilTestRecord`` objects instead of raw dicts. The amendment calculator,
mismatch detection and overdue-test logic land in later 12.10 sub-stories
and are stubbed here to flag premature use.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager

GLOBAL_TARGET_ID = "global"


class SoilService:
    """Read/write access to soil-test history stored on a ``ProjectManager``."""

    def __init__(self, project_manager: ProjectManager) -> None:
        self._pm = project_manager

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_history(self, target_id: str) -> SoilTestHistory:
        """Return the history for ``target_id`` (empty if none recorded yet)."""
        raw = self._pm.soil_tests.get(target_id)
        if raw is None:
            return SoilTestHistory(target_id=target_id)
        return SoilTestHistory.from_dict(raw)

    def get_effective_record(self, bed_id: str) -> SoilTestRecord | None:
        """Return the soil test that applies to ``bed_id``.

        Hierarchy: bed's own latest record → global default's latest record → None.
        """
        bed_history = self.get_history(bed_id)
        if bed_history.latest is not None:
            return bed_history.latest
        global_history = self.get_history(GLOBAL_TARGET_ID)
        return global_history.latest

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_record(self, target_id: str, record: SoilTestRecord) -> None:
        """Append ``record`` to the history for ``target_id`` and mark dirty."""
        history = self.get_history(target_id)
        history.records.append(record)
        self._pm.set_soil_test_history(target_id, history)

    # ── Stubs (deferred to later sub-stories) ─────────────────────────────────

    def calculate_amendments(self, *_args, **_kwargs):  # pragma: no cover
        """Compute per-bed amendment quantities (US-12.10c)."""
        raise NotImplementedError("Amendment calculator lands in US-12.10c")

    def get_mismatched_plants(self, *_args, **_kwargs):  # pragma: no cover
        """Detect plant-soil mismatches (US-12.10d)."""
        raise NotImplementedError("Plant-soil mismatch detection lands in US-12.10d")

    def is_test_overdue(self, *_args, **_kwargs) -> bool:  # pragma: no cover
        """Seasonal overdue check (US-12.10e)."""
        raise NotImplementedError("Overdue check lands in US-12.10e")

    def overall_health_color(self, *_args, **_kwargs):  # pragma: no cover
        """Map a record to a HealthLevel (US-12.10b)."""
        raise NotImplementedError("Health colouring lands in US-12.10b")
