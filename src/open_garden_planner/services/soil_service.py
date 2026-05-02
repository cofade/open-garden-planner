"""Soil-test service (US-12.10a, extended in US-12.10b).

Thin facade over ``ProjectManager`` that returns ``SoilTestHistory`` /
``SoilTestRecord`` objects instead of raw dicts. The amendment calculator,
mismatch detection and overdue-test logic land in later 12.10 sub-stories
and are stubbed here to flag premature use.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager

GLOBAL_TARGET_ID = "global"


class HealthLevel(Enum):
    """Coarse soil-health bucket used by the canvas overlay (US-12.10b)."""

    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


# RGBA tuples for the canvas overlay tint (alpha 80 ≈ 31%).
_HEALTH_RGBA: dict[HealthLevel, tuple[int, int, int, int]] = {
    HealthLevel.GOOD: (100, 200, 100, 80),
    HealthLevel.FAIR: (255, 200, 0, 80),
    HealthLevel.POOR: (220, 60, 60, 80),
}

# Parameter key constants for ``health_level``. ``OVERALL`` collapses pH and NPK
# into the worst single bucket; the others isolate one parameter.
PARAM_OVERALL = "overall"
PARAM_PH = "ph"
PARAM_N = "n"
PARAM_P = "p"
PARAM_K = "k"
ALL_PARAMS: tuple[str, ...] = (PARAM_OVERALL, PARAM_PH, PARAM_N, PARAM_P, PARAM_K)


def _ph_level(ph: float | None) -> HealthLevel:
    if ph is None:
        return HealthLevel.UNKNOWN
    if 6.0 <= ph <= 7.0:
        return HealthLevel.GOOD
    if 5.5 <= ph < 6.0 or 7.0 < ph <= 7.5:
        return HealthLevel.FAIR
    return HealthLevel.POOR


def _npk_level(level: int | None) -> HealthLevel:
    """Map a Rapitest 0–4 NPK rating to a HealthLevel.

    The kit semantics: 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient,
    4=Surplus. Adequate (2) is amber because it's borderline.
    """
    if level is None:
        return HealthLevel.UNKNOWN
    if level <= 1:
        return HealthLevel.POOR
    if level == 2:
        return HealthLevel.FAIR
    return HealthLevel.GOOD


_RANK = {
    HealthLevel.UNKNOWN: -1,
    HealthLevel.GOOD: 0,
    HealthLevel.FAIR: 1,
    HealthLevel.POOR: 2,
}


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

    # ── Health level (US-12.10b) ──────────────────────────────────────────────

    @staticmethod
    def health_level(record: SoilTestRecord | None, parameter: str) -> HealthLevel:
        """Rate ``record`` on ``parameter`` (one of :data:`ALL_PARAMS`).

        Returns :attr:`HealthLevel.UNKNOWN` when the relevant fields are unset.
        For ``"overall"`` the worst non-unknown level across pH and NPK wins;
        all-unknown stays unknown.
        """
        if record is None:
            return HealthLevel.UNKNOWN
        if parameter == PARAM_PH:
            return _ph_level(record.ph)
        if parameter == PARAM_N:
            return _npk_level(record.n_level)
        if parameter == PARAM_P:
            return _npk_level(record.p_level)
        if parameter == PARAM_K:
            return _npk_level(record.k_level)
        # OVERALL — worst of the four (ignoring unknown).
        levels = [
            _ph_level(record.ph),
            _npk_level(record.n_level),
            _npk_level(record.p_level),
            _npk_level(record.k_level),
        ]
        known = [lvl for lvl in levels if lvl is not HealthLevel.UNKNOWN]
        if not known:
            return HealthLevel.UNKNOWN
        return max(known, key=_RANK.__getitem__)

    @staticmethod
    def overlay_rgba(level: HealthLevel) -> tuple[int, int, int, int] | None:
        """Return the (r, g, b, a) tint for ``level``, or ``None`` for UNKNOWN.

        Untested beds get hatched grey from the view layer instead of a tint.
        """
        return _HEALTH_RGBA.get(level)

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
