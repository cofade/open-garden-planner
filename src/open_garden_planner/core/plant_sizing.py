"""Single source of truth for plant sizing precedence.

A plant's size is governed by three independent quantities that used to have
their precedence re-encoded in three places (``garden_item`` resolver,
``circle_item`` paint/boundingRect ring gate, and the species-assignment
helper). This module collapses that into one documented value object so the
rules live in exactly one file (issue #218).

The three quantities:

* **footprint** — the drawn circle radius (``CircleItem._radius``).
* **spacing override** — a user-set planting distance (``spacing_radius_cm``),
  or ``None`` for "use the database".
* **max_spread_cm** — the database value from ``metadata["plant_species"]``.

Precedence (unchanged behaviour, see ``PlantSizing.effective_spacing_radius_cm``):
the manual override wins; otherwise the database ``max_spread_cm / 2``; otherwise
there is no spacing data. The spacing ring is drawn only when the effective
spacing radius exceeds the drawn footprint (a ring that would sit inside the
footprint conveys nothing — the footprint already shows that size).

This module is intentionally Qt-free so the precedence can be unit-tested in
isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


def _positive_number(value: Any) -> float | None:
    """Coerce ``value`` to a positive float, or ``None`` if it is not one.

    The single home for "is this a usable size?" — guards every ``max_spread_cm``
    read so a missing/zero/non-numeric value degrades to "no data" instead of
    raising (``bool`` is rejected so ``True`` is never mistaken for ``1``).
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


class _SizedPlant(Protocol):
    """The duck-typed surface ``sizing_for_item`` reads (a plant ``CircleItem``)."""

    @property
    def radius(self) -> float: ...
    @property
    def spacing_radius_cm(self) -> float | None: ...
    @property
    def metadata(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class PlantSizing:
    """Resolved view of a plant's three sizing quantities and their precedence."""

    footprint_radius_cm: float
    spacing_override_cm: float | None
    db_max_spread_cm: float | None

    @property
    def effective_spacing_radius_cm(self) -> float | None:
        """The planting-distance radius in cm, or ``None`` when no data exists.

        Precedence: user override > ``max_spread_cm / 2`` > ``None`` — identical
        to the historical ``GardenItemMixin.effective_spacing_radius()``.
        """
        if self.spacing_override_cm is not None:
            return self.spacing_override_cm
        db = _positive_number(self.db_max_spread_cm)
        return db / 2.0 if db is not None else None

    @property
    def spacing_source(self) -> str:
        """Where the effective spacing radius comes from: ``override``/``database``/``none``."""
        if self.spacing_override_cm is not None:
            return "override"
        if _positive_number(self.db_max_spread_cm) is not None:
            return "database"
        return "none"

    @property
    def spacing_ring_radius_cm(self) -> float | None:
        """Radius of the dashed spacing ring to draw, or ``None`` to hide it.

        The ring is drawn only when the effective spacing radius is known and
        strictly larger than the drawn footprint — a ring inside the footprint
        adds nothing (the footprint already conveys that size, #213). Returning
        the radius (not a bool) lets callers type-narrow in one step.
        """
        effective = self.effective_spacing_radius_cm
        if effective is not None and effective > self.footprint_radius_cm:
            return effective
        return None

    @property
    def shows_spacing_ring(self) -> bool:
        """Whether the dashed spacing ring should be drawn."""
        return self.spacing_ring_radius_cm is not None


def db_spacing_radius_cm(species_dict: dict[str, Any]) -> float | None:
    """Footprint/spacing radius the database implies for a species, or ``None``.

    Equals ``max_spread_cm / 2`` when ``max_spread_cm`` is a positive number,
    else ``None``. Used by the species-assignment helper to size the drawn
    footprint so its diameter equals ``max_spread_cm`` (#213).
    """
    db = _positive_number(species_dict.get("max_spread_cm"))
    return db / 2.0 if db is not None else None


def sizing_for_item(item: _SizedPlant) -> PlantSizing:
    """Build a :class:`PlantSizing` from a plant item's current state."""
    footprint = float(getattr(item, "radius", 0.0) or 0.0)
    override = getattr(item, "spacing_radius_cm", None)
    meta = getattr(item, "metadata", None) or {}
    species = meta.get("plant_species")
    db_max_spread = species.get("max_spread_cm") if isinstance(species, dict) else None
    return PlantSizing(
        footprint_radius_cm=footprint,
        spacing_override_cm=override,
        db_max_spread_cm=db_max_spread,
    )
