"""Shopping list aggregation service (US-12.6).

Walks the canvas + project state and produces a flat list of
``ShoppingListItem`` rows split into three categories:

* **Plants** — every placed plant, grouped by species, with a count and an
  averaged "current spread" size descriptor.
* **Seeds** — species placed in the plan that have no packet in the project's
  seed inventory ("seed gaps").
* **Materials** — soil amendments aggregated across deficient beds, replicating
  the cross-bed totals shown by :class:`AmendmentPlanDialog` (US-12.10c).

User-entered prices are kept on :class:`ProjectData` keyed by item ID and
reattached on every rebuild, so the dialog can edit them in place and save
them with the project.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from open_garden_planner.core.measurements import calculate_area_and_perimeter
from open_garden_planner.core.object_types import ObjectType, is_bed_type
from open_garden_planner.models.amendment import Amendment
from open_garden_planner.models.shopping_list import (
    ShoppingListCategory,
    ShoppingListItem,
)
from open_garden_planner.services.soil_service import SoilService

if TYPE_CHECKING:
    from open_garden_planner.core.project import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene


_PLANT_OBJECT_TYPES = (ObjectType.TREE, ObjectType.SHRUB, ObjectType.PERENNIAL)


@dataclass
class AggregatedAmendment:
    """Sum of one substance across all beds in the plan.

    Promoted out of :mod:`amendment_plan_dialog` so the shopping list and the
    plan dialog share the same totals.
    """

    amendment: Amendment
    total_g: float = 0.0
    bed_names: list[str] = field(default_factory=list)


def aggregate_amendments(
    scene: CanvasScene,
    soil_service: SoilService,
) -> list[AggregatedAmendment]:
    """Walk every bed in ``scene`` and group amendment recommendations by substance.

    Returns substances ordered by descending total grams (matches the existing
    Amendment Plan dialog ordering).
    """
    by_id: dict[str, AggregatedAmendment] = {}
    for item in scene.items():
        object_type = getattr(item, "object_type", None)
        if not is_bed_type(object_type):
            continue
        target_id = str(getattr(item, "item_id", ""))
        if not target_id:
            continue
        area = _bed_area_m2(item)
        if area <= 0.0:
            continue
        record = soil_service.get_effective_record(target_id)
        recs = SoilService.calculate_amendments(record, bed_area_m2=area)
        if not recs:
            continue
        bed_name = str(getattr(item, "name", "") or "Bed")
        for rec in recs:
            slot = by_id.setdefault(
                rec.amendment.id, AggregatedAmendment(amendment=rec.amendment)
            )
            slot.total_g += rec.quantity_g
            if bed_name not in slot.bed_names:
                slot.bed_names.append(bed_name)
    return sorted(by_id.values(), key=lambda a: -a.total_g)


def _bed_area_m2(item: object) -> float:
    """Return bed area in m², or 0.0 if the item type isn't supported."""
    result = calculate_area_and_perimeter(item)  # type: ignore[arg-type]
    if result is None:
        return 0.0
    area_cm2, _ = result
    return area_cm2 / 10_000.0


class ShoppingListService:
    """Build a shopping list from the current scene + project state."""

    def __init__(
        self,
        scene: CanvasScene,
        soil_service: SoilService,
        project_manager: ProjectManager,
    ) -> None:
        self._scene = scene
        self._soil_service = soil_service
        self._project_manager = project_manager

    # ── Public API ────────────────────────────────────────────────────────────

    def build(self) -> list[ShoppingListItem]:
        """Return a fresh list with saved prices reattached."""
        items: list[ShoppingListItem] = []
        items.extend(self._collect_plants())
        items.extend(self._collect_seed_gaps())
        items.extend(self._collect_materials())
        self._apply_saved_prices(items)
        return items

    # ── Aggregators ───────────────────────────────────────────────────────────

    def _collect_plants(self) -> list[ShoppingListItem]:
        """Group placed plant items by species and emit one row per species."""
        groups: dict[str, dict] = defaultdict(
            lambda: {"name": "", "count": 0, "spreads": [], "type_name": ""}
        )
        for item in self._scene.items():
            if getattr(item, "object_type", None) not in _PLANT_OBJECT_TYPES:
                continue
            metadata = getattr(item, "metadata", None) or {}
            plant_species = metadata.get("plant_species") or {}
            plant_instance = metadata.get("plant_instance") or {}

            species_id = (
                plant_species.get("source_id")
                or plant_species.get("scientific_name")
                or plant_species.get("common_name")
                or "_unknown"
            )
            display_name = (
                plant_species.get("common_name")
                or plant_species.get("scientific_name")
                or getattr(item, "name", "")
                or "Unknown plant"
            )
            spread = plant_instance.get("current_spread_cm") or plant_instance.get(
                "current_diameter_cm"
            )

            slot = groups[str(species_id)]
            slot["name"] = display_name
            slot["count"] += 1
            if isinstance(spread, (int, float)) and spread > 0:
                slot["spreads"].append(float(spread))
            slot["type_name"] = self._object_type_label(item.object_type)

        out: list[ShoppingListItem] = []
        for species_id, slot in sorted(groups.items(), key=lambda kv: kv[1]["name"].lower()):
            size = ""
            if slot["spreads"]:
                avg = sum(slot["spreads"]) / len(slot["spreads"])
                size = f"~{avg:.0f} cm spread"
            out.append(
                ShoppingListItem(
                    id=f"plant:{species_id}",
                    category=ShoppingListCategory.PLANTS,
                    name=slot["name"],
                    quantity=float(slot["count"]),
                    unit="plants",
                    size_descriptor=size,
                    notes=slot["type_name"],
                )
            )
        return out

    def _collect_seed_gaps(self) -> list[ShoppingListItem]:
        """Emit one packet-sized row per species placed on the canvas with no
        matching packet in the project seed inventory."""
        placed_species: dict[str, str] = {}
        for item in self._scene.items():
            if getattr(item, "object_type", None) not in _PLANT_OBJECT_TYPES:
                continue
            metadata = getattr(item, "metadata", None) or {}
            plant_species = metadata.get("plant_species") or {}
            sid = (
                plant_species.get("source_id")
                or plant_species.get("scientific_name")
                or plant_species.get("common_name")
            )
            if not sid:
                continue
            placed_species.setdefault(
                str(sid),
                plant_species.get("common_name")
                or plant_species.get("scientific_name")
                or str(sid),
            )

        owned_species: set[str] = set()
        for packet in self._project_manager.seed_inventory:
            sid = packet.get("species_id") or packet.get("species_name")
            if sid:
                owned_species.add(str(sid))

        gaps = sorted(
            (sid, name) for sid, name in placed_species.items() if sid not in owned_species
        )
        return [
            ShoppingListItem(
                id=f"seed:{sid}",
                category=ShoppingListCategory.SEEDS,
                name=name,
                quantity=1.0,
                unit="packet",
                notes="Not in project seed inventory",
            )
            for sid, name in gaps
        ]

    def _collect_materials(self) -> list[ShoppingListItem]:
        """Roll the cross-bed amendment totals into shopping-list rows."""
        out: list[ShoppingListItem] = []
        for agg in aggregate_amendments(self._scene, self._soil_service):
            out.append(
                ShoppingListItem(
                    id=f"amendment:{agg.amendment.id}",
                    category=ShoppingListCategory.MATERIALS,
                    name=agg.amendment.name,
                    quantity=round(agg.total_g, 1),
                    unit="g",
                    notes=", ".join(agg.bed_names),
                )
            )
        return out

    # ── Price persistence ─────────────────────────────────────────────────────

    def _apply_saved_prices(self, items: list[ShoppingListItem]) -> None:
        saved = self._project_manager.shopping_list_prices
        for item in items:
            price = saved.get(item.id)
            if price is not None:
                item.price_each = float(price)

    def update_price(self, item: ShoppingListItem, price: float | None) -> None:
        """Mutate ``item`` and persist the change to ``ProjectManager``."""
        item.price_each = price
        prices = dict(self._project_manager.shopping_list_prices)
        if price is None or price == 0:
            prices.pop(item.id, None)
        else:
            prices[item.id] = float(price)
        self._project_manager.set_shopping_list_prices(prices)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _object_type_label(object_type: ObjectType) -> str:
        from open_garden_planner.core.object_types import get_style

        try:
            return get_style(object_type).display_name
        except Exception:  # noqa: BLE001
            return object_type.name.replace("_", " ").title()


__all__ = [
    "AggregatedAmendment",
    "ShoppingListService",
    "aggregate_amendments",
]
