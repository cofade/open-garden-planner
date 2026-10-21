"""One undoable write path for plant instance lifetime dates."""

from functools import partial
from typing import Any

from open_garden_planner.core.commands import ChangePropertyCommand
from open_garden_planner.core.plan_timeline import instance_date
from open_garden_planner.core.sim_clock import MAX_PLAN_DATE, MIN_PLAN_DATE

_DATE_LABELS = {"planting_date": "planting date", "removal_date": "removal date"}


def _apply_date(item: Any, value: str | None, *, field: str) -> None:
    item.prepareGeometryChange()
    instance = item.metadata.setdefault("plant_instance", {})
    if value is None:
        instance.pop(field, None)
    else:
        instance[field] = value
    scene = item.scene()
    if scene is not None and hasattr(scene, "refresh_timeline"):
        scene.refresh_timeline()
    item.update()


def change_lifetime_date(item: Any, field: str, value: str | None) -> bool:
    """One date edit = one command. Reject inverted intervals before mutation."""
    if field not in _DATE_LABELS:
        raise ValueError("not a plant lifetime date")
    candidate = dict(item.metadata)
    instance = dict(candidate.get("plant_instance") or {})
    instance[field] = value
    candidate["plant_instance"] = instance
    parsed = instance_date(candidate, field)
    if value is not None and parsed is None:
        raise ValueError("invalid ISO date")
    old = (item.metadata.get("plant_instance") or {}).get(field)
    if old == value:
        return False
    if parsed is not None and not MIN_PLAN_DATE <= parsed <= MAX_PLAN_DATE:
        raise ValueError("date outside supported plan range")
    start = instance_date(candidate, "planting_date")
    end = instance_date(candidate, "removal_date")
    if start is not None and end is not None and end <= start:
        raise ValueError("removal must follow planting")
    scene = item.scene()
    manager = getattr(scene, "_command_manager", None)
    if manager is None:
        return False
    manager.execute(ChangePropertyCommand(
        item, _DATE_LABELS[field], old, value, apply_func=partial(_apply_date, field=field)))
    return True
