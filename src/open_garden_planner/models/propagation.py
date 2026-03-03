"""Propagation planning data model — US-9.5.

Models the indoor pre-cultivation cycle for seed packets and placed plants:
  indoor_sow → germination → prick_out → harden_off → transplant

All dates are derived from species calendar data + frost dates, but can be
overridden per-species by the user and are persisted in the project file.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any

# Ordered step IDs used throughout the UI
STEP_IDS = ("indoor_sow", "germination", "prick_out", "harden_off", "transplant")

# Fallback durations when no species-specific data is available
_DEFAULTS = {
    "prick_out_after_days": 21,  # days after indoor sow start
    "harden_off_days": 10,       # length of hardening-off period before transplant
    "germination_days_min": 7,
    "germination_days_max": 14,
}


@dataclass
class PropagationStep:
    """A single step in the propagation timeline.

    Attributes:
        step_id: One of the STEP_IDS constants.
        start_date: Calculated or user-overridden start date.
        end_date: Calculated or user-overridden end date.
            Same as start_date for point events (prick_out, transplant).
        overridden: True when the user has manually set this step's dates.
    """

    step_id: str
    start_date: datetime.date
    end_date: datetime.date
    overridden: bool = False


@dataclass
class PropagationPlan:
    """Full propagation plan for one plant species.

    Contains the computed sequence of steps from indoor sowing to outdoor
    transplanting.  User overrides for individual steps are stored in
    ``overrides`` and applied on top of calculated dates.
    """

    species_key: str
    steps: list[PropagationStep] = field(default_factory=list)
    # step_id → {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    overrides: dict[str, dict[str, str]] = field(default_factory=dict)

    # ── Step access ────────────────────────────────────────────────────────────

    def get_step(self, step_id: str) -> PropagationStep | None:
        """Return the step with the given ID, or None."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def set_step_override(
        self,
        step_id: str,
        start: datetime.date,
        end: datetime.date,
    ) -> None:
        """Store a user override and update the computed step dates."""
        self.overrides[step_id] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
        }
        for step in self.steps:
            if step.step_id == step_id:
                step.start_date = start
                step.end_date = end
                step.overridden = True
                return

    def clear_override(self, step_id: str) -> None:
        """Remove the user override for a step (reverts to calculated dates)."""
        self.overrides.pop(step_id, None)
        for step in self.steps:
            if step.step_id == step_id:
                step.overridden = False

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict (only overrides need persisting)."""
        d: dict[str, Any] = {"species_key": self.species_key}
        if self.overrides:
            d["overrides"] = self.overrides
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PropagationPlan:
        """Deserialize from a dict (steps are recomputed at runtime)."""
        return cls(
            species_key=data.get("species_key", ""),
            overrides=data.get("overrides", {}),
        )


# ── Computation ────────────────────────────────────────────────────────────────

def compute_propagation_plan(
    *,
    species_key: str,
    sow_start: datetime.date,
    sow_end: datetime.date,
    transplant_date: datetime.date,
    germination_days_min: int | None = None,
    germination_days_max: int | None = None,
    prick_out_after_days: int | None = None,
    harden_off_days: int | None = None,
    overrides: dict[str, dict[str, str]] | None = None,
) -> PropagationPlan:
    """Compute a :class:`PropagationPlan` from species data and frost-derived dates.

    Steps:

    - **indoor_sow**: ``sow_start`` → ``sow_end``
    - **germination**: ``sow_start + germination_days_min`` →
      ``sow_start + germination_days_max``
    - **prick_out**: ``sow_start + prick_out_after_days`` (point event)
    - **harden_off**: ``transplant_date - harden_off_days`` → ``transplant_date``
    - **transplant**: ``transplant_date`` (point event)

    User overrides are applied on top of calculated dates.

    Args:
        species_key: Identifier for the species (scientific or common name).
        sow_start: First day of the indoor sowing window.
        sow_end: Last day of the indoor sowing window.
        transplant_date: Target outdoor transplanting date.
        germination_days_min: Min days until germination (default 7).
        germination_days_max: Max days until germination (default 14).
        prick_out_after_days: Days after sow_start to prick out (default 21).
        harden_off_days: Duration of the hardening-off period (default 10).
        overrides: Existing user overrides to apply (dict of dicts).

    Returns:
        A :class:`PropagationPlan` with computed steps and applied overrides.
    """
    germ_min = germination_days_min if germination_days_min is not None else _DEFAULTS["germination_days_min"]
    germ_max = germination_days_max if germination_days_max is not None else _DEFAULTS["germination_days_max"]
    prick_days = prick_out_after_days if prick_out_after_days is not None else _DEFAULTS["prick_out_after_days"]
    harden_days = harden_off_days if harden_off_days is not None else _DEFAULTS["harden_off_days"]
    ov = overrides or {}

    steps: list[PropagationStep] = [
        PropagationStep(
            step_id="indoor_sow",
            start_date=sow_start,
            end_date=sow_end,
        ),
        PropagationStep(
            step_id="germination",
            start_date=sow_start + datetime.timedelta(days=germ_min),
            end_date=sow_start + datetime.timedelta(days=germ_max),
        ),
        PropagationStep(
            step_id="prick_out",
            start_date=sow_start + datetime.timedelta(days=prick_days),
            end_date=sow_start + datetime.timedelta(days=prick_days),
        ),
        PropagationStep(
            step_id="harden_off",
            start_date=transplant_date - datetime.timedelta(days=harden_days),
            end_date=transplant_date,
        ),
        PropagationStep(
            step_id="transplant",
            start_date=transplant_date,
            end_date=transplant_date,
        ),
    ]

    # Apply user overrides
    for step in steps:
        if step.step_id in ov:
            raw = ov[step.step_id]
            try:
                step.start_date = datetime.date.fromisoformat(raw["start"])
                step.end_date = datetime.date.fromisoformat(raw["end"])
                step.overridden = True
            except (KeyError, ValueError):
                pass

    return PropagationPlan(
        species_key=species_key,
        steps=steps,
        overrides=dict(ov),
    )
