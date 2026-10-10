"""Eager bundled validation, isolated user-file loading and atomic authoring."""

import json
import logging
import os
import tempfile
from pathlib import Path

from open_garden_planner.models.guild import GuildTemplate
from open_garden_planner.services.bundled_species_db import get_species_db
from open_garden_planner.services.plant_library import get_app_data_dir

logger = logging.getLogger(__name__)
_BUNDLED = Path(__file__).parent.parent / "resources/data/guilds"


class GuildLibrary:
    def __init__(self, bundled_dir: Path | None = None, user_dir: Path | None = None) -> None:
        self.bundled_dir = bundled_dir or _BUNDLED
        self.user_dir = user_dir if user_dir is not None else get_app_data_dir() / "guilds"
        self.templates: dict[str, GuildTemplate] = {}
        self.user_paths: dict[str, Path] = {}
        self.errors: list[tuple[str, str]] = []
        self.error_objects: dict[str, Exception] = {}
        self.reload()

    def reload(self) -> None:
        templates: dict[str, GuildTemplate] = {}
        self.errors = []
        self.error_objects = {}
        self.user_paths = {}
        for path in sorted(self.bundled_dir.glob("*.json")):
            template = GuildTemplate.from_dict(json.loads(path.read_text(encoding="utf-8")))
            catalog = get_species_db()
            references = [s for r in template.roles for s in r.suggested_species]
            if not template.centre.startswith("function:"):
                references.append(template.centre)
            if any(ref not in catalog for ref in references):
                raise ValueError(f"Unresolved bundled guild species in {path.name}")
            templates[template.id] = template
        self.user_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.user_dir.glob("*.json")):
            try:
                template = GuildTemplate.from_dict(json.loads(path.read_text(encoding="utf-8")))
                templates[template.id] = template
                self.user_paths[template.id] = path
            except Exception as error:
                logger.warning("Skipping guild template %s: %s", path, error)
                self.errors.append((path.name, str(error)))
                self.error_objects[path.name] = error
        self.templates = templates

    def save(self, template: GuildTemplate) -> Path:
        """Atomic UTF-8 replacement; a failed write preserves the original file."""
        validated = GuildTemplate.from_dict(template.to_dict())
        target = self.user_paths.get(validated.id, self.user_dir / f"{validated.id}.json")
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.user_dir,
                                             suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(validated.to_dict(), stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.reload()
        return target
