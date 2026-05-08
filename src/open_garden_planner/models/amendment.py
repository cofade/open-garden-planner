"""Amendment data model (US-12.10c).

Two dataclasses:

* :class:`Amendment` — one row from ``resources/data/amendments.json``. Carries
  the application-rate and per-fix effect coefficients used by the calculator.
* :class:`AmendmentRecommendation` — calculator output for a single substance
  applied to a single bed. Holds the gram quantity plus a localisable
  "rationale" string (e.g. "Raises pH 5.8 → 6.5") so the inline dialog list and
  the plan dialog render identical text.

Application rates and pH effects are conservative starting figures drawn from
common horticultural references (Rodale, RHS, USDA Extension fact sheets);
real-world rates vary with soil type and crop demand.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Fix tags used by ``Amendment.fixes`` and the priority walk.
FIX_RAISES_PH = "raises_pH"
FIX_LOWERS_PH = "lowers_pH"
FIX_ADDS_N = "adds_N"
FIX_ADDS_P = "adds_P"
FIX_ADDS_K = "adds_K"
FIX_ADDS_CA = "adds_Ca"
FIX_ADDS_MG = "adds_Mg"
FIX_ADDS_S = "adds_S"
FIX_ADDS_SI = "adds_Si"
FIX_IMPROVES_AERATION = "improves_aeration"
FIX_IMPROVES_DRAINAGE = "improves_drainage"
FIX_IMPROVES_WATER_RETENTION = "improves_water_retention"


@dataclass
class Amendment:
    """One soil amendment substance loaded from the bundled JSON.

    Effect fields (``n_level_effect`` etc.) are integer steps on the Rapitest
    scale per single application at ``application_rate_g_m2``. ``ph_effect_per_100g_m2``
    is the approximate pH shift achieved by 100 g/m² (positive = raise,
    negative = lower).
    """

    id: str
    name: str
    name_de: str = ""
    fixes: list[str] = field(default_factory=list)
    application_rate_g_m2: float = 0.0
    ph_effect_per_100g_m2: float = 0.0
    n_level_effect: int = 0
    p_level_effect: int = 0
    k_level_effect: int = 0
    ca_level_effect: int = 0
    mg_level_effect: int = 0
    s_level_effect: int = 0
    organic: bool = True
    release_speed: str = "medium"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Amendment:
        """Deserialise from one JSON row, raising ``ValueError`` on missing keys."""
        try:
            return cls(
                id=data["id"],
                name=data["name"],
                name_de=data.get("name_de", ""),
                fixes=list(data.get("fixes", [])),
                application_rate_g_m2=float(data["application_rate_g_m2"]),
                ph_effect_per_100g_m2=float(data.get("ph_effect_per_100g_m2", 0.0)),
                n_level_effect=int(data.get("n_level_effect", 0)),
                p_level_effect=int(data.get("p_level_effect", 0)),
                k_level_effect=int(data.get("k_level_effect", 0)),
                ca_level_effect=int(data.get("ca_level_effect", 0)),
                mg_level_effect=int(data.get("mg_level_effect", 0)),
                s_level_effect=int(data.get("s_level_effect", 0)),
                organic=bool(data.get("organic", True)),
                release_speed=str(data.get("release_speed", "medium")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid amendment entry: {data!r}") from exc

    def display_name(self, lang: str = "en") -> str:
        """Return the localised display name (falls back to English)."""
        if lang == "de" and self.name_de:
            return self.name_de
        return self.name


@dataclass
class AmendmentRecommendation:
    """Calculator output: apply ``quantity_g`` of ``amendment`` to a bed.

    ``rationale_en`` is the English explanation; ``rationale_args`` is the
    structured tuple ``(target_kind, current, target)`` that the dialogs use
    to render a localised string. The two stay in sync by construction —
    callers should display via the dialogs' ``_format_rationale`` helper rather
    than reading ``rationale_en`` directly.
    """

    amendment: Amendment
    quantity_g: float
    target_kind: str       # one of "ph", "n", "p", "k", "ca", "mg", "s", "structure"
    current_value: float   # numeric current value (pH or 0–4 level)
    target_value: float    # numeric target value
    bed_id: str = ""       # populated by the plan dialog when aggregating; "" for inline
    bed_name: str = ""     # human-readable bed label for the plan dialog
    # Multi-nutrient credit (US-12.11). When a compound substance also covers
    # other deficits beyond ``target_kind``, each is recorded here as
    # ``(kind, current, target)``. Empty for single-nutrient picks.
    credits: list[tuple[str, float, float]] = field(default_factory=list)
    # For structural picks the fix tag drives the rationale text.
    structural_fix: str = ""

    @property
    def rationale_en(self) -> str:
        """Default English rationale string. Dialogs override with self.tr() versions."""
        if self.target_kind == "ph":
            base = (
                f"Raises pH {self.current_value:.1f} → {self.target_value:.1f}"
                if self.target_value > self.current_value
                else f"Lowers pH {self.current_value:.1f} → {self.target_value:.1f}"
            )
        elif self.target_kind == "structure":
            base = f"Improves {self.structural_fix}"
        else:
            nutrient = self.target_kind.upper()
            base = (
                f"Raises {nutrient} level "
                f"{int(self.current_value)} → {int(self.target_value)}"
            )
        if self.credits:
            extras = ", ".join(
                f"{k.upper()} {int(c)}→{int(t)}" for k, c, t in self.credits
            )
            base = f"{base} + also raises {extras}"
        return base


__all__ = [
    "Amendment",
    "AmendmentRecommendation",
    "FIX_ADDS_CA",
    "FIX_ADDS_K",
    "FIX_ADDS_MG",
    "FIX_ADDS_N",
    "FIX_ADDS_P",
    "FIX_ADDS_S",
    "FIX_ADDS_SI",
    "FIX_IMPROVES_AERATION",
    "FIX_IMPROVES_DRAINAGE",
    "FIX_IMPROVES_WATER_RETENTION",
    "FIX_LOWERS_PH",
    "FIX_RAISES_PH",
]
