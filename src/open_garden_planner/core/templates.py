"""Portable .ogp templates: explicit field policy and recursive site-data removal.

This is a content filter, not an anonymizer for free-form names or annotations.
Unknown top-level keys fail closed. ADR-066 records the portable subset.
"""

from __future__ import annotations

import json
from datetime import date, time
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


def _bundled_sidecar(source: Path) -> tuple[dict[str, Any], str] | None:
    """The trusted sidecar of a shipped example and the language of its copy.

    ``None`` for every other file, also for one that only shares a shipped
    example's name. A locale directory counts only when the canonical sidecar
    carries that language's name and description.
    """
    resolved = source.resolve()
    canonical = BUNDLED_EXAMPLES / resolved.name
    sidecar = canonical.with_suffix(".meta.json")
    if canonical.suffix != ".ogp" or not canonical.is_file() or not sidecar.is_file():
        return None
    if resolved.parent == BUNDLED_EXAMPLES:
        return json.loads(sidecar.read_text(encoding="utf-8")), "en"
    if resolved.parent.parent != BUNDLED_EXAMPLES:
        return None
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    locale = resolved.parent.name
    if f"name_{locale}" not in meta or f"description_{locale}" not in meta:
        return None
    return meta, locale


#: What a shipped example keeps beyond the portable subset: its public place, its
#: fictional soil sample and its fictional harvest history (ADR-066 addenda).
EXAMPLE_DEMO_FIELDS = ("location", "soil_tests", "harvest_logs")


def example_copy_plan(plan: dict[str, Any], source: Path) -> dict[str, Any]:
    """Keep public demonstration state only for known shipped example paths.

    Export always uses template_plan. An external copy, even with the same name,
    has the ordinary private-template policy. Locale directories are authorized
    by the trusted canonical sidecar's translated name/description keys.
    """
    result = template_plan(plan)
    if _bundled_sidecar(source) is None:
        return result
    for key in EXAMPLE_DEMO_FIELDS:
        if key in plan:
            cleaned = _portable(plan[key])
            if cleaned is not _REMOVED:
                result[key] = cleaned
    return result


def template_title(source: Path, language: str = "en") -> str:
    """The name a person knows the template at *source* by.

    A shipped example's own name from its trusted sidecar: in the language of
    the directory it was opened from, and for the base copy (which serves every
    language without a translated plan) in *language* when the sidecar has it.
    For any other file its stem.
    """
    bundled = _bundled_sidecar(source)
    if bundled is None:
        return source.stem
    meta, locale = bundled
    if locale == "en":
        locale = language
    return str(meta.get(f"name_{locale}") or meta.get("name_en") or source.stem)


def example_showcase_moment(source: Path) -> tuple[date, time] | None:
    """The moment a shipped example is meant to be seen at, or ``None``.

    The sidecar's ``showcase_date`` (the example's reference date, the plan's
    local day) and ``showcase_utc_time`` (a daytime sun over the example's own
    place). A UTC time of day and not a wall time: the session clock reads wall
    time in the computer's zone, and midday on a wall clock in Auckland is night
    over a garden in Berlin. The pair is what ``SimClock.set_utc_time_on`` takes.

    ``None`` for any file that is not a shipped example, and for a sidecar
    without the two fields.
    """
    bundled = _bundled_sidecar(source)
    if bundled is None:
        return None
    meta = bundled[0]
    day, utc_time = meta.get("showcase_date"), meta.get("showcase_utc_time")
    if not isinstance(day, str) or not isinstance(utc_time, str):
        return None
    return date.fromisoformat(day), time.fromisoformat(utc_time)
