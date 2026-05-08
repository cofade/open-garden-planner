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
    FIX_IMPROVES_AERATION,
    FIX_IMPROVES_DRAINAGE,
    FIX_IMPROVES_WATER_RETENTION,
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


_NUTRIENT_KINDS: tuple[str, ...] = ("n", "p", "k", "ca", "mg", "s")
_NUTRIENT_FIX: dict[str, str] = {
    "n": FIX_ADDS_N,
    "p": FIX_ADDS_P,
    "k": FIX_ADDS_K,
    "ca": FIX_ADDS_CA,
    "mg": FIX_ADDS_MG,
    "s": FIX_ADDS_S,
}


def _level_effect(amendment: Amendment, kind: str) -> int:
    """Return the per-application Rapitest-step effect of ``amendment`` on ``kind``."""
    return int(getattr(amendment, f"{kind}_level_effect", 0))


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


def _pick_best_coverage(
    amendments: list[Amendment],
    used: set[str],
    deficits: dict[str, int],
    prefer_organic: bool,
) -> tuple[Amendment, str] | None:
    """Pick the unused amendment that covers the most outstanding nutrient deficits.

    Returns ``(amendment, primary_kind)`` — primary is the nutrient with the
    biggest current deficit among those this substance touches; it sets the
    recommendation's ``target_kind`` and the gram-quantity scale (``deficit ×
    application_rate``). All other nutrients with non-zero ``*_level_effect``
    are credited toward their deficits at the same dose factor.

    Scoring (lexicographic): breadth (number of outstanding deficits covered)
    → prefer-organic (when enabled) → earlier JSON position (preserves the
    historical organic-first bias when both flags favour the same direction).
    """
    best: tuple[Amendment, str] | None = None
    best_key: tuple[int, int, int] | None = None
    for index, candidate in enumerate(amendments):
        if candidate.id in used:
            continue
        covered: list[str] = []
        for kind in _NUTRIENT_KINDS:
            if deficits.get(kind, 0) <= 0:
                continue
            if _level_effect(candidate, kind) <= 0:
                continue
            covered.append(kind)
        if not covered:
            continue
        # Primary = nutrient with the largest outstanding deficit; ties broken
        # by ``_NUTRIENT_KINDS`` order (N before P before K …) for determinism.
        primary_kind = max(covered, key=lambda k: (deficits[k], -_NUTRIENT_KINDS.index(k)))
        breadth = len(covered)
        organic_score = (1 if candidate.organic else 0) if prefer_organic else 0
        key = (breadth, organic_score, -index)
        if best_key is None or key > best_key:
            best_key = key
            best = (candidate, primary_kind)
    return best


def _pick_structural(
    fix_tag: str, amendments: list[Amendment], used: set[str]
) -> Amendment | None:
    """Return the first unused amendment that carries the structural ``fix_tag``."""
    for amendment in amendments:
        if amendment.id in used:
            continue
        if fix_tag in amendment.fixes:
            return amendment
    return None


def _structural_fixes_for(soil_texture: str | None) -> list[str]:
    """Map a soil-texture descriptor to the structural fix tags that address it."""
    if soil_texture == "sandy":
        return [FIX_IMPROVES_WATER_RETENTION]
    if soil_texture == "clayey":
        return [FIX_IMPROVES_DRAINAGE, FIX_IMPROVES_AERATION]
    if soil_texture == "compacted":
        return [FIX_IMPROVES_AERATION]
    return []


def _credit_secondaries(
    pick: Amendment,
    deficits: dict[str, int],
    currents: dict[str, int],
    targets: dict[str, int],
    rec: AmendmentRecommendation,
) -> None:
    """Decrement Ca/Mg/S deficits when a non-nutrient-primary pick (pH) covers them.

    Used by the pH phase: lime also adds Ca, dolomite also adds Mg, elemental
    sulfur also adds S. Each covered secondary is appended to ``rec.credits``
    so the rationale text says e.g. ``"Raises pH 5.8 → 6.5 + also raises CA 0→1"``.
    """
    for kind in ("ca", "mg", "s"):
        effect = _level_effect(pick, kind)
        if effect <= 0:
            continue
        if deficits.get(kind, 0) <= 0:
            continue
        current = currents[kind]
        target = targets[kind]
        rec.credits.append((kind, float(current), float(target)))
        deficits[kind] = max(0, deficits[kind] - effect)
        currents[kind] = min(target, current + effect)


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


def _compute_structural(
    amendment: Amendment, fix_tag: str, bed_area_m2: float
) -> AmendmentRecommendation:
    """Build a structural AmendmentRecommendation (one full application per bed)."""
    return AmendmentRecommendation(
        amendment=amendment,
        quantity_g=amendment.application_rate_g_m2 * bed_area_m2,
        target_kind="structure",
        current_value=0.0,
        target_value=1.0,
        structural_fix=fix_tag,
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
        enabled_ids: set[str] | None = None,
        prefer_organic: bool = True,
    ) -> list[AmendmentRecommendation]:
        """Compute amendment recommendations for one bed (US-12.11).

        Walks pH first (the pH-shift formula differs from the level math), then
        repeatedly picks the unused substance with the largest combined credit
        toward outstanding NPK + Ca/Mg/S deficits — so a compound NPK fertilizer
        is chosen once and credited toward all three nutrients in a single pick
        rather than burning three separate picks. Finally, derives structural
        fix tags from ``record.soil_texture`` and emits one structural pick per
        tag.

        ``enabled_ids`` (optional) restricts the candidate pool to the user's
        toggled-on set; ``None`` means "all amendments enabled" (default).
        ``prefer_organic`` controls the tie-breaker; turning it off lets mineral
        compounds win when their coverage equals an organic candidate's.

        Returns ``[]`` when ``record`` is ``None``, ``bed_area_m2 <= 0``, or no
        deficits exist. The function is pure: no I/O, no service state.
        """
        if record is None or bed_area_m2 <= 0.0:
            return []

        all_amendments = (loader or get_default_loader()).get_amendments()
        if enabled_ids is None:
            pool = list(all_amendments)
        else:
            pool = [a for a in all_amendments if a.id in enabled_ids]
        used_ids: set[str] = set()
        results: list[AmendmentRecommendation] = []

        # Build the deficit map. pH is tracked separately because its formula
        # is a real-valued shift, not an integer level step.
        deficits: dict[str, int] = {
            "n": _level_deficit(record.n_level, target_n),
            "p": _level_deficit(record.p_level, target_p),
            "k": _level_deficit(record.k_level, target_k),
            "ca": _level_deficit(record.ca_level, _SECONDARY_TARGET),
            "mg": _level_deficit(record.mg_level, _SECONDARY_TARGET),
            "s": _level_deficit(record.s_level, _SECONDARY_TARGET),
        }
        currents: dict[str, int] = {
            "n": record.n_level or 0,
            "p": record.p_level or 0,
            "k": record.k_level or 0,
            "ca": record.ca_level or 0,
            "mg": record.mg_level or 0,
            "s": record.s_level or 0,
        }
        targets: dict[str, int] = {
            "n": target_n, "p": target_p, "k": target_k,
            "ca": _SECONDARY_TARGET, "mg": _SECONDARY_TARGET, "s": _SECONDARY_TARGET,
        }

        # 1. pH (own formula, single pick).
        ph_pick = _pick_ph(record.ph, target_ph, pool, used_ids)
        if ph_pick is not None:
            ph_rec = _compute_ph(ph_pick, record.ph, target_ph, bed_area_m2)
            _credit_secondaries(ph_pick, deficits, currents, targets, ph_rec)
            results.append(ph_rec)
            used_ids.add(ph_pick.id)

        # 2. Nutrient phase — greedy breadth-first pick. One pick fully closes
        #    its primary nutrient's deficit (quantity_g scales with deficit);
        #    co-fixed nutrients are credited at the same dose factor and their
        #    deficits decremented accordingly. Loop until pool exhausted or
        #    every deficit cleared.
        while any(v > 0 for v in deficits.values()):
            pick = _pick_best_coverage(pool, used_ids, deficits, prefer_organic)
            if pick is None:
                break
            amendment, primary_kind = pick
            primary_deficit = deficits[primary_kind]
            primary_current = currents[primary_kind]
            primary_target = targets[primary_kind]
            rec = _compute_nutrient(
                amendment,
                primary_current,
                primary_target,
                primary_kind,
                bed_area_m2,
            )
            # Primary is fully covered by this single application.
            deficits[primary_kind] = 0
            currents[primary_kind] = primary_target
            # Co-fixed nutrients: applying ``primary_deficit`` × base rate gives
            # ``primary_deficit × effect`` steps of credit toward each of them,
            # capped at that nutrient's outstanding deficit.
            for kind in _NUTRIENT_KINDS:
                if kind == primary_kind:
                    continue
                kind_effect = _level_effect(amendment, kind)
                if kind_effect <= 0:
                    continue
                if deficits.get(kind, 0) <= 0:
                    continue
                kind_current = currents[kind]
                kind_target = targets[kind]
                credit = min(deficits[kind], primary_deficit * kind_effect)
                rec.credits.append(
                    (kind, float(kind_current), float(min(kind_target, kind_current + credit)))
                )
                deficits[kind] = max(0, deficits[kind] - credit)
                currents[kind] = min(kind_target, kind_current + credit)
            results.append(rec)
            used_ids.add(amendment.id)

        # 3. Structural phase — soil-texture-driven picks. One pick per fix tag.
        for fix in _structural_fixes_for(record.soil_texture):
            pick = _pick_structural(fix, pool, used_ids)
            if pick is None:
                continue
            results.append(_compute_structural(pick, fix, bed_area_m2))
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
