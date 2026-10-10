"""Qt-free explicit membership validation and recorded-function coverage."""

from collections import Counter
from dataclasses import dataclass
from typing import Any

from open_garden_planner.models.guild import GuildTemplate
from open_garden_planner.models.guild_errors import GuildValidationError, validated_function
from open_garden_planner.models.plant_data import PlantFunction


@dataclass(frozen=True)
class GuildStatus:
    guild_id: str
    centre_id: str
    name: str
    member_ids: tuple[str, ...]
    required: dict[str, int]
    present: dict[str, int]

    @property
    def missing(self) -> dict[str, int]:
        return {f: count - self.present.get(f, 0) for f, count in self.required.items()
                if count > self.present.get(f, 0)}


def compute_guilds(members: list[dict[str, Any]]) -> tuple[list[GuildStatus], list[dict[str, Any]]]:
    """Malformed links remain saved, but never count toward successful coverage."""
    valid: dict[str, list[dict[str, Any]]] = {}
    errors: list[dict[str, Any]] = []

    def warning(member: dict[str, Any], reason: str, error: Exception | None = None) -> None:
        errors.append({"kind": "guild_data_warning", "severity": "warning",
                       "item_ids": [str(member.get("item_id", ""))], "message": reason,
                       "details": {"reason": reason, "reason_code": error.code if isinstance(error, GuildValidationError) else None,
                                   "reason_details": error.details if isinstance(error, GuildValidationError) else {}}})

    for member in members:
        guild = member.get("guild")
        if guild is None:
            continue
        try:
            if not isinstance(guild, dict) or not isinstance(guild.get("guild_id"), str) or not guild["guild_id"]:
                raise GuildValidationError("link")
            role = guild.get("role")
            if role != "centre":
                validated_function(role)
            else:
                GuildTemplate.from_dict(guild["template"])
                if not isinstance(guild.get("name"), str) or not guild["name"].strip():
                    raise GuildValidationError("centre_name")
            valid.setdefault(guild["guild_id"], []).append(member)
        except Exception as error:
            warning(member, f"Invalid saved guild metadata: {error}", error)
    statuses = []
    for gid, group in valid.items():
        centres = [m for m in group if m["guild"]["role"] == "centre"]
        if len(centres) != 1:
            for member in group:
                warning(member, "Guild must have exactly one valid centre", GuildValidationError("one_centre"))
            continue
        centre = centres[0]
        template = GuildTemplate.from_dict(centre["guild"]["template"])
        counts: Counter[str] = Counter()
        for member in group:
            functions = member.get("functions") or []
            if not isinstance(functions, list):
                functions = []
            counts.update(f.value for f in PlantFunction if f.value in functions)
        statuses.append(GuildStatus(gid, str(centre["item_id"]), centre["guild"]["name"],
                                   tuple(str(m["item_id"]) for m in group),
                                   {r.function: r.count_min for r in template.roles}, dict(counts)))
    return statuses, errors


def guild_diagnostics(statuses: list[GuildStatus]) -> list[dict[str, Any]]:
    diagnostics = []
    for status in statuses:
        for function in status.missing:
            required, present = status.required[function], status.present.get(function, 0)
            diagnostics.append({"kind": "guild_role_missing", "severity": "warning",
                "item_ids": [status.centre_id],
                "message": f"Guild '{status.name}' needs {required} {function} plant(s); {present} recorded.",
                "details": {"guild_id": status.guild_id, "centre_id": status.centre_id,
                            "function": function, "required_count": required, "present_count": present,
                            "guild_name": status.name}})
    return diagnostics
