"""Portable .ogp templates: explicit field policy and recursive site-data removal.

This is a content filter, not an anonymizer for free-form names or annotations.
Unknown top-level keys fail closed. ADR-066 records the portable subset.
"""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

KEEP_PROJECT_FIELDS = frozenset({
    "canvas_width", "canvas_height", "objects", "layers", "constraints", "guides",
    "succession_plans", "auto_assign_permaculture_layers",
})
STRIP_PROJECT_FIELDS = frozenset({
    "location", "task_completions", "seed_inventory", "propagation_overrides",
    "crop_rotation", "season_year", "linked_seasons", "soil_tests", "pest_disease_logs",
    "shopping_list_prices", "excluded_shopping_items", "enabled_amendments",
    "prefer_organic", "garden_journal_notes", "manual_tasks", "task_states", "harvest_logs",
})
KEEP_PLAN_KEYS = (KEEP_PROJECT_FIELDS - {"canvas_width", "canvas_height"}) | {"version", "canvas"}
_SITE_KEYS = frozenset({
    "geo_metadata", "photos", "photo_paths", "image_path", "file_path", "source_path",
})
_REMOVED = object()
BUNDLED_EXAMPLES = Path(__file__).resolve().parent.parent / "resources" / "examples"


def _absolute_path(value: str) -> bool:
    return (PurePosixPath(value).is_absolute() or bool(PureWindowsPath(value).drive)
            or bool(PureWindowsPath(value).root)
            or PureWindowsPath(value).is_absolute() or value.lower().startswith("file:"))


def _portable(value: Any) -> Any:
    if isinstance(value, str) and _absolute_path(value):
        return _REMOVED
    if isinstance(value, dict):
        result = {}
        for key, child in value.items():
            if key in _SITE_KEYS or _absolute_path(key):
                continue
            cleaned = _portable(child)
            if cleaned is not _REMOVED:
                result[key] = cleaned
        return result
    if isinstance(value, list):
        return [cleaned for child in value if (cleaned := _portable(child)) is not _REMOVED]
    return value


def _objects(value: Any) -> Any:
    """Filter canvas records only; custom dictionaries may also have a type key."""
    if not isinstance(value, list):
        return _portable(value)
    result = []
    for record in value:
        if isinstance(record, dict) and record.get("type") in ("background_image", "journal_pin"):
            continue
        cleaned = _portable(record)
        if isinstance(record, dict) and isinstance(cleaned, dict) and "children" in record:
            cleaned["children"] = _objects(record["children"])
        if cleaned is not _REMOVED:
            result.append(cleaned)
    return result


def template_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Return a detached portable subset; never modify the source snapshot."""
    result = {}
    for key, value in plan.items():
        if key in KEEP_PLAN_KEYS:
            cleaned = _objects(value) if key == "objects" else _portable(value)
            if cleaned is not _REMOVED:
                result[key] = cleaned
    return result


def example_copy_plan(plan: dict[str, Any], source: Path) -> dict[str, Any]:
    """Keep public demonstration state only for known shipped example paths.

    Export always uses template_plan. An external copy, even with the same name,
    has the ordinary private-template policy. Locale directories are authorized
    by the trusted canonical sidecar's translated name/description keys.
    """
    result = template_plan(plan)
    resolved = source.resolve()
    canonical = BUNDLED_EXAMPLES / resolved.name
    if not canonical.is_file() or canonical.suffix != ".ogp":
        return result
    if resolved.parent != BUNDLED_EXAMPLES:
        if resolved.parent.parent != BUNDLED_EXAMPLES:
            return result
        meta = json.loads(canonical.with_suffix(".meta.json").read_text(encoding="utf-8"))
        locale = resolved.parent.name
        if f"name_{locale}" not in meta or f"description_{locale}" not in meta:
            return result
    for key in ("location", "soil_tests"):
        if key in plan:
            cleaned = _portable(plan[key])
            if cleaned is not _REMOVED:
                result[key] = cleaned
    return result
