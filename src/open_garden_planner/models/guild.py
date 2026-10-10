"""Validated, Qt-free guild definitions and deterministic centimetre layouts."""

import math
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from open_garden_planner.models.guild_errors import GuildValidationError, validated_function
from open_garden_planner.models.plant_data import PlantFunction

MAX_GUILD_PLANTS = 200


@dataclass(frozen=True)
class GuildRole:
    function: str
    count_min: int
    ring_radius_cm: float | str
    suggested_species: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuildRole":
        function = validated_function(data.get("function"))
        count = data.get("count_min")
        if type(count) is not int or count < 1:
            raise GuildValidationError("count")
        radius = data.get("ring_radius_cm")
        if radius != "canopy_edge":
            if isinstance(radius, bool) or not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius <= 0:
                raise GuildValidationError("radius")
            radius = float(radius)
        suggestions = data.get("suggested_species", [])
        if not isinstance(suggestions, list) or not all(isinstance(s, str) and s.strip() for s in suggestions):
            raise GuildValidationError("suggestions")
        return cls(function, count, radius, tuple(suggestions))

    def to_dict(self) -> dict[str, Any]:
        return {"function": self.function, "count_min": self.count_min,
                "ring_radius_cm": self.ring_radius_cm, "suggested_species": list(self.suggested_species)}


@dataclass(frozen=True)
class GuildTemplate:
    id: str
    version: int
    name: str
    description: str
    centre: str
    roles: tuple[GuildRole, ...]
    license: str
    attribution: str
    sources: tuple[str, ...] = ()
    name_de: str = ""
    description_de: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuildTemplate":
        if not isinstance(data, dict):
            raise GuildValidationError("object")
        identity = data.get("id")
        if not isinstance(identity, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,99}", identity):
            raise GuildValidationError("id")
        version = data.get("version")
        if type(version) is not int or version < 1:
            raise GuildValidationError("version")
        for key in ("name", "centre", "license", "attribution"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise GuildValidationError("field", field=key)
        centre = data["centre"]
        if centre in {function.value for function in PlantFunction}:
            centre = "function:" + centre
        if centre.startswith("function:"):
            validated_function(centre.removeprefix("function:"))
        rows = data.get("roles")
        if not isinstance(rows, list):
            raise GuildValidationError("roles")
        roles = tuple(GuildRole.from_dict(row) for row in rows)
        if len({r.function for r in roles}) != len(roles):
            raise GuildValidationError("duplicate")
        if 1 + sum(r.count_min for r in roles) > MAX_GUILD_PLANTS:
            raise GuildValidationError("limit")
        for key in ("description", "name_de", "description_de"):
            if not isinstance(data.get(key, ""), str):
                raise GuildValidationError("text", field=key)
        sources = data.get("sources", [])
        if not isinstance(sources, list) or not all(isinstance(s, str) for s in sources):
            raise GuildValidationError("sources")
        return cls(identity, version, data["name"], data.get("description", ""), centre,
                   roles, data["license"], data["attribution"], tuple(sources),
                   data.get("name_de", ""), data.get("description_de", ""))

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "name": self.name,
                "description": self.description, "centre": self.centre,
                "roles": [r.to_dict() for r in self.roles], "license": self.license,
                "attribution": self.attribution, "sources": list(self.sources),
                "name_de": self.name_de, "description_de": self.description_de}


def ring_positions(template: GuildTemplate, centre: tuple[float, float],
                   mature_radius_cm: float | None) -> list[tuple[str, float, float]]:
    """Evenly space deterministic slots sharing a radius, in CAD scene coordinates."""
    rings: dict[float, list[str]] = {}
    for role in template.roles:
        radius = mature_radius_cm if role.ring_radius_cm == "canopy_edge" else role.ring_radius_cm
        if not isinstance(radius, (int, float)) or not math.isfinite(radius) or radius <= 0:
            raise GuildValidationError("spacing")
        rings.setdefault(float(radius), []).extend([role.function] * role.count_min)
    positions = []
    for radius, functions in rings.items():
        for index, function in enumerate(functions):
            angle = 2 * math.pi * index / len(functions)
            positions.append((function, centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle)))
    return positions


def remap_copied_guilds(records: list[dict[str, Any]], *, complete_member_ids: dict[str, set[str]]) -> list[dict[str, Any]]:
    """One deep-copy/remapping rule for all copy surfaces, including nested groups."""
    from uuid import uuid4

    result = deepcopy(records)
    flat: list[dict[str, Any]] = []

    def walk(rows: list[dict[str, Any]]) -> None:
        for record in rows:
            flat.append(record)
            walk(record.get("children") or [])

    walk(result)
    selected = {str(row.get("item_id")) for row in flat}
    centres = {(row.get("metadata") or {}).get("guild", {}).get("guild_id") for row in flat
               if isinstance((row.get("metadata") or {}).get("guild"), dict)
               and isinstance(row["metadata"]["guild"].get("guild_id"), str)
               and row["metadata"]["guild"].get("role") == "centre"}
    replacements = {gid: str(uuid4()) for gid, members in complete_member_ids.items()
                    if members and members.issubset(selected) and gid in centres}
    for row in flat:
        metadata = row.get("metadata") or {}
        guild = metadata.get("guild")
        if not isinstance(guild, dict):
            metadata.pop("guild", None)
            continue
        gid = guild.get("guild_id")
        if isinstance(gid, str) and gid in replacements:
            guild["guild_id"] = replacements[gid]
        else:
            metadata.pop("guild", None)
    return result
