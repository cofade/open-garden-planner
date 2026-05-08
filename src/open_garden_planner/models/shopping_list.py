"""Shopping list data model (US-12.6).

Aggregates everything the user needs to buy for the current plan:
plants placed on the canvas, seed gaps versus the project seed inventory,
and materials (currently soil amendments rolled in from US-12.10c).

Items are produced fresh on demand by ``ShoppingListService`` from the
canvas + project state. Only the user-entered prices are persisted, keyed
by ``ShoppingListItem.id`` so that re-running aggregation re-attaches them.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ShoppingListCategory(Enum):
    """Top-level grouping shown in the dialog and CSV/PDF export."""

    PLANTS = "plants"
    SEEDS = "seeds"
    MATERIALS = "materials"


@dataclass
class ShoppingListItem:
    """One purchasable line in the shopping list."""

    id: str
    category: ShoppingListCategory
    name: str
    quantity: float
    unit: str
    size_descriptor: str = ""
    notes: str = ""
    price_each: float | None = None

    @property
    def total_cost(self) -> float | None:
        """Return ``price_each * quantity`` or ``None`` when no price set."""
        if self.price_each is None:
            return None
        return self.price_each * self.quantity

    def to_export_row(self) -> dict[str, Any]:
        """Render as a flat dict suitable for CSV/PDF/clipboard rendering."""
        return {
            "category": self.category.value,
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "size": self.size_descriptor,
            "price_each": "" if self.price_each is None else self.price_each,
            "total_cost": "" if self.total_cost is None else self.total_cost,
            "notes": self.notes,
        }


__all__ = ["ShoppingListCategory", "ShoppingListItem"]
