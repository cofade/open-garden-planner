"""Offline bundled examples and local templates; no user file is opened on listing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_garden_planner.core.templates import BUNDLED_EXAMPLES


def user_templates_dir() -> Path:
    from open_garden_planner.services.plant_library import get_app_data_dir

    path = get_app_data_dir() / "templates"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class ExampleEntry:
    path: Path
    name: str
    description: str = ""
    tags: tuple[str, ...] = ()
    license: str = ""
    thumbnail: Path | None = None
    attribution: str = ""


def bundled_examples(language: str = "en") -> list[ExampleEntry]:
    """Load trusted sidecars; malformed/missing bundled content is a packaging bug."""
    entries = []
    for canonical in sorted(BUNDLED_EXAMPLES.glob("*.ogp")):
        meta = json.loads(canonical.with_suffix(".meta.json").read_text(encoding="utf-8"))
        path = canonical
        if f"name_{language}" in meta and f"description_{language}" in meta:
            localized = BUNDLED_EXAMPLES / language / canonical.name
            if localized.is_file():
                path = localized
        thumbnail = path.with_suffix(".png")
        if not thumbnail.is_file():
            raise FileNotFoundError(thumbnail)
        entries.append(ExampleEntry(
            path, meta.get("name_" + language, meta["name_en"]),
            meta.get("description_" + language, meta["description_en"]),
            tuple(meta["tags"]), meta["license"], thumbnail,
            meta.get("attribution_" + language, meta["attribution"]),
        ))
    return entries


def gallery_entries(language: str = "en") -> list[ExampleEntry]:
    """User filenames need no parsing; corrupt plans fail only when opened."""
    return bundled_examples(language) + [
        ExampleEntry(path, path.stem) for path in sorted(user_templates_dir().glob("*.ogp"))
        if path.is_file()
    ]


def examples_resource(language: str = "en") -> list[dict[str, Any]]:
    """Read-only catalog; intentionally excludes personal templates."""
    return [{"name": e.name, "description": e.description, "tags": list(e.tags),
             "path": str(e.path), "license": e.license, "attribution": e.attribution}
            for e in bundled_examples(language)]
