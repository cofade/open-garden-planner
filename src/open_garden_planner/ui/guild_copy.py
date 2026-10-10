"""Shared guild copy remapping for clipboard, duplicates, arrays and mirrors."""

from typing import Any

from open_garden_planner.models.guild import remap_copied_guilds


def scene_guild_member_ids(scene: Any) -> dict[str, set[str]]:
    members: dict[str, set[str]] = {}
    for item in scene.items():
        guild = getattr(item, "metadata", {}).get("guild")
        if isinstance(guild, dict) and isinstance(guild.get("guild_id"), str):
            members.setdefault(guild["guild_id"], set()).add(str(item.item_id))
    return members


def copy_guild_records(scene: Any, records: list[dict[str, Any]], member_ids: dict[str, set[str]] | None = None) -> list[dict[str, Any]]:
    return remap_copied_guilds(records, complete_member_ids=member_ids if member_ids is not None else scene_guild_member_ids(scene))


def remap_mirror_membership(scene: Any, originals: list[Any], mirrored: list[Any]) -> None:
    """Geometry builders keep source identity; this remaps only copied metadata."""
    pairs = []

    def record(source: Any, target: Any) -> dict[str, Any]:
        pairs.append((source, target))
        children = []
        source_children = [child for child in source.childItems() if hasattr(child, "metadata")]
        target_children = [child for child in target.childItems() if hasattr(child, "metadata")]
        for old, new in zip(source_children, target_children, strict=True):
            if hasattr(old, "metadata") and hasattr(new, "metadata"):
                children.append(record(old, new))
        return {"item_id": str(getattr(source, "item_id", "")),
                "metadata": getattr(source, "metadata", {}), "children": children}

    records = [record(source, target) for source, target in zip(originals, mirrored, strict=True)]
    copied = copy_guild_records(scene, records)
    flat = []

    def walk(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            flat.append(row)
            walk(row.get("children") or [])

    walk(copied)
    for (_, target), row in zip(pairs, flat, strict=True):
        if hasattr(target, "metadata"):
            target.metadata.clear()
            target.metadata.update(row["metadata"])
