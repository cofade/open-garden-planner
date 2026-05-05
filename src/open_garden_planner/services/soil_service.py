"""Soil-test service (US-12.10a–e).

Thin facade over ``ProjectManager`` that returns ``SoilTestHistory`` /
``SoilTestRecord`` objects instead of raw dicts. Amendment calculator
(US-12.10c), plant-soil mismatch detection (US-12.10d), and seasonal
overdue-test logic (US-12.10e) are implemented here.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

from PyQt6.QtCore import QCoreApplication

from open_garden_planner.models.amendment import (
    FIX_ADDS_CA,
    FIX_ADDS_K,
    FIX_ADDS_MG,
    FIX_ADDS_N,
    FIX_ADDS_P,
    FIX_ADDS_S,
    FIX_LOWERS_PH,
    FIX_RAISES_PH,
    Amendment,
    AmendmentRecommendation,
)
from open_garden_planner.models.soil_test import SoilTestHistory, SoilTestRecord
from open_garden_planner.services.amendment_loader import (
    AmendmentLoader,
    get_default_loader,
)

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.models.plant_data import PlantSpeciesData

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
    4=Surplus. Adequate (2) and Sufficient (3) are both GOOD — the kit
    literally calls 2 "adequate", which UX-tests as fine. Surplus (4) is
    FAIR because over-fertilisation can imbalance the soil and burn roots.
    """
    if level is None:
        return HealthLevel.UNKNOWN
    if level <= 1:
        return HealthLevel.POOR
    if level == 4:
        return HealthLevel.FAIR
    return HealthLevel.GOOD


_RANK = {
    HealthLevel.UNKNOWN: -1,
    HealthLevel.GOOD: 0,
    HealthLevel.FAIR: 1,
    HealthLevel.POOR: 2,
}

# Default target on the 0–4 Rapitest scale for Ca/Mg/S secondaries (Medium / Sufficient).
_SECONDARY_TARGET = 2

# Smallest pH delta worth correcting — anything below is within measurement noise.
_PH_EPSILON = 0.1


def _level_deficit(current: int | None, target: int) -> int:
    """How many Rapitest steps below ``target`` the bed sits. Unknown → 0."""
    if current is None:
        return 0
    return max(0, target - current)


def _pick_ph(
    current_ph: float | None,
    target_ph: float,
    amendments: list[Amendment],
    used: set[str],
) -> Amendment | None:
    """Return the first pH-fixing amendment whose direction matches the deficit."""
    if current_ph is None:
        return None
    delta = target_ph - current_ph
    if abs(delta) < _PH_EPSILON:
        return None
    needed_fix = FIX_RAISES_PH if delta > 0 else FIX_LOWERS_PH
    for amendment in amendments:
        if amendment.id in used:
            continue
        if needed_fix in amendment.fixes and amendment.ph_effect_per_100g_m2 != 0:
            return amendment
    return None


def _pick_nutrient(
    fix_tag: str, amendments: list[Amendment], used: set[str]
) -> Amendment | None:
    """Return the first unused amendment that carries ``fix_tag``."""
    for amendment in amendments:
        if amendment.id in used:
            continue
        if fix_tag in amendment.fixes:
            return amendment
    return None


def _compute_ph(
    amendment: Amendment,
    current_ph: float | None,
    target_ph: float,
    bed_area_m2: float,
) -> AmendmentRecommendation:
    """Build a pH AmendmentRecommendation per the roadmap formula §1976-2030."""
    current = current_ph if current_ph is not None else target_ph
    delta = abs(target_ph - current)
    effect = abs(amendment.ph_effect_per_100g_m2) or 1.0
    quantity_g = (delta / effect) * 100.0 * bed_area_m2
    return AmendmentRecommendation(
        amendment=amendment,
        quantity_g=quantity_g,
        target_kind="ph",
        current_value=current,
        target_value=target_ph,
    )


def _compute_nutrient(
    amendment: Amendment,
    current_level: int,
    target_level: int,
    kind: str,
    bed_area_m2: float,
) -> AmendmentRecommendation:
    """Build a nutrient AmendmentRecommendation per the roadmap formula."""
    deficit = max(0, target_level - current_level)
    quantity_g = deficit * amendment.application_rate_g_m2 * bed_area_m2
    return AmendmentRecommendation(
        amendment=amendment,
        quantity_g=quantity_g,
        target_kind=kind,
        current_value=float(current_level),
        target_value=float(target_level),
    )


def _effective_demand(
    spec: PlantSpeciesData,
) -> tuple[str | None, str | None, str | None]:
    """Return (n_demand, p_demand, k_demand), falling back to legacy nutrient_demand."""
    n, p, k = spec.n_demand, spec.p_demand, spec.k_demand
    if n is None and spec.nutrient_demand:
        _map = {"heavy": "high", "light": "low", "fixer": "fixer"}
        mapped = _map.get(spec.nutrient_demand)
        n = p = k = mapped
    return n, p, k


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

    # ── Amendment calculator (US-12.10c) ──────────────────────────────────────

    @staticmethod
    def calculate_amendments(
        record: SoilTestRecord | None,
        target_ph: float = 6.5,
        target_n: int = 3,
        target_p: int = 3,
        target_k: int = 3,
        bed_area_m2: float = 0.0,
        loader: AmendmentLoader | None = None,
    ) -> list[AmendmentRecommendation]:
        """Compute amendment recommendations for one bed.

        Walks deficits in the priority order **pH → N → P → K → Ca → Mg → S**
        and picks the first matching substance for each. Each substance can
        appear at most once per bed.

        Returns ``[]`` when ``record`` is ``None``, ``bed_area_m2 <= 0``, or
        no deficits exist. The function is pure: no I/O, no service state.
        """
        if record is None or bed_area_m2 <= 0.0:
            return []

        amendments = (loader or get_default_loader()).get_amendments()
        used_ids: set[str] = set()
        results: list[AmendmentRecommendation] = []

        # Track Ca/Mg/S deficits dynamically — adding lime also adds Ca, so we
        # decrement the secondary-nutrient deficit after picking it.
        ca_deficit = _level_deficit(record.ca_level, _SECONDARY_TARGET)
        mg_deficit = _level_deficit(record.mg_level, _SECONDARY_TARGET)
        s_deficit = _level_deficit(record.s_level, _SECONDARY_TARGET)

        # 1. pH
        ph_pick = _pick_ph(record.ph, target_ph, amendments, used_ids)
        if ph_pick is not None:
            results.append(_compute_ph(ph_pick, record.ph, target_ph, bed_area_m2))
            used_ids.add(ph_pick.id)
            # Lime / ash also raise Ca; sulfur adds S; dolomite adds Mg.
            if ph_pick.ca_level_effect > 0:
                ca_deficit = max(0, ca_deficit - 1)
            if ph_pick.mg_level_effect > 0:
                mg_deficit = max(0, mg_deficit - 1)
            if ph_pick.s_level_effect > 0:
                s_deficit = max(0, s_deficit - 1)

        # 2-4. NPK
        for fix, current, target, kind in (
            (FIX_ADDS_N, record.n_level, target_n, "n"),
            (FIX_ADDS_P, record.p_level, target_p, "p"),
            (FIX_ADDS_K, record.k_level, target_k, "k"),
        ):
            deficit = _level_deficit(current, target)
            if deficit < 1:
                continue
            pick = _pick_nutrient(fix, amendments, used_ids)
            if pick is None:
                continue
            results.append(
                _compute_nutrient(pick, current or 0, target, kind, bed_area_m2)
            )
            used_ids.add(pick.id)
            # An NPK pick can also bump secondaries (e.g. compost gives N+P+K).
            if pick.ca_level_effect > 0:
                ca_deficit = max(0, ca_deficit - 1)
            if pick.mg_level_effect > 0:
                mg_deficit = max(0, mg_deficit - 1)
            if pick.s_level_effect > 0:
                s_deficit = max(0, s_deficit - 1)

        # 5-7. Ca, Mg, S — only if still deficient after the pH/NPK picks.
        for fix, deficit, current, kind in (
            (FIX_ADDS_CA, ca_deficit, record.ca_level, "ca"),
            (FIX_ADDS_MG, mg_deficit, record.mg_level, "mg"),
            (FIX_ADDS_S, s_deficit, record.s_level, "s"),
        ):
            if deficit < 1:
                continue
            pick = _pick_nutrient(fix, amendments, used_ids)
            if pick is None:
                continue
            results.append(
                _compute_nutrient(
                    pick, current or 0, _SECONDARY_TARGET, kind, bed_area_m2
                )
            )
            used_ids.add(pick.id)

        return results

    # ── US-12.10d: Plant-soil compatibility ───────────────────────────────────

    @staticmethod
    def get_mismatched_plants(
        record: SoilTestRecord | None,
        plant_specs: list[PlantSpeciesData],
    ) -> list[tuple[PlantSpeciesData, list[str]]]:
        """Return (spec, reasons) for each plant whose requirements conflict with record.

        Returns [] when record is None or plant_specs is empty.
        Severity is determined by the caller: 1 entry → amber, ≥2 → red.
        """
        if record is None:
            return []
        results: list[tuple[PlantSpeciesData, list[str]]] = []
        for spec in plant_specs:
            reasons: list[str] = []
            name = spec.common_name or spec.scientific_name or QCoreApplication.translate(
                "SoilService", "Plant"
            )
            if (
                record.ph is not None
                and spec.ph_min is not None
                and spec.ph_max is not None
            ):
                # Tolerance is intentionally tight (0.05) — only enough to
                # absorb float-rounding from the dialog's 0.1-step pH spinbox.
                # A larger margin (originally 0.3) hides real mismatches: a
                # tomato with ph_min=5.8 should warn at pH 5.7, not just 5.4.
                if record.ph < spec.ph_min - 0.05:
                    reasons.append(
                        QCoreApplication.translate(
                            "SoilService",
                            "{name} needs pH ≥{min:.1f}, current {cur:.1f}",
                        ).format(name=name, min=spec.ph_min, cur=record.ph)
                    )
                elif record.ph > spec.ph_max + 0.05:
                    reasons.append(
                        QCoreApplication.translate(
                            "SoilService",
                            "{name} needs pH ≤{max:.1f}, current {cur:.1f}",
                        ).format(name=name, max=spec.ph_max, cur=record.ph)
                    )
            n_d, p_d, k_d = _effective_demand(spec)
            if n_d == "high" and record.n_level is not None and record.n_level < 2:
                reasons.append(
                    QCoreApplication.translate(
                        "SoilService",
                        "{name} is a heavy N feeder (current level: {lvl})",
                    ).format(name=name, lvl=record.n_level)
                )
            if p_d == "high" and record.p_level is not None and record.p_level < 2:
                reasons.append(
                    QCoreApplication.translate(
                        "SoilService",
                        "{name} is a heavy P feeder (current level: {lvl})",
                    ).format(name=name, lvl=record.p_level)
                )
            if k_d == "high" and record.k_level is not None and record.k_level < 2:
                reasons.append(
                    QCoreApplication.translate(
                        "SoilService",
                        "{name} is a heavy K feeder (current level: {lvl})",
                    ).format(name=name, lvl=record.k_level)
                )
            if reasons:
                results.append((spec, reasons))
        return results

    # ── US-12.10e: Seasonal overdue check ─────────────────────────────────────

    @staticmethod
    def is_test_overdue(history: SoilTestHistory | None, today: date) -> bool:
        """Return True when the bed is due for a fresh soil test.

        A bed is overdue iff:
          * the calendar month is a sampling window (Mar/Apr or Sep/Oct), AND
          * a previous test exists, AND
          * the latest record is older than 180 days (or its date is unparseable).

        Untested beds (None / empty history) are intentionally NOT flagged —
        new beds shouldn't nag the gardener until a baseline test exists.
        """
        if today.month not in {3, 4, 9, 10}:
            return False
        if history is None or not history.records:
            return False
        latest = history.latest
        if latest is None:
            return False
        try:
            last_date = date.fromisoformat(latest.date)
        except (ValueError, TypeError):
            return True
        return (today - last_date).days > 180
