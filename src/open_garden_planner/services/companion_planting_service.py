"""Companion planting service — loads and queries companion planting compatibility data.

The bundled JSON database covers 60+ common vegetables, herbs, and flowers with
beneficial and antagonistic relationships.  Users can extend it with custom rules
that are persisted per-machine in the app-data directory.

Lookups are bidirectional: if A–B is stored, querying either A or B returns it.
Names are matched case-insensitively by common name, scientific name, or alias.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from open_garden_planner.services.plant_library import get_app_data_dir

_DATA_DIR = Path(__file__).parent.parent / "resources" / "data"
_CUSTOM_RULES_FILENAME = "custom_companion_rules.json"

# Relationship type constants
BENEFICIAL = "beneficial"
ANTAGONISTIC = "antagonistic"
NEUTRAL = "neutral"


@dataclass
class CompanionRelationship:
    """A companion planting relationship between two plants.

    Attributes:
        plant_a: Canonical common name of the first plant.
        plant_b: Canonical common name of the second plant.
        type: Relationship type — "beneficial", "antagonistic", or "neutral".
        reason: Human-readable explanation of the relationship.
        is_custom: True if this rule was added by the user.
    """

    plant_a: str
    plant_b: str
    type: str
    reason: str
    is_custom: bool = field(default=False)


class CompanionPlantingService:
    """Service for querying companion planting relationships.

    Loads a bundled JSON database and optionally user-defined custom rules.
    All lookups are bidirectional and case-insensitive.

    Usage::

        svc = CompanionPlantingService()
        good, bad = svc.get_companions("tomato")
        rel = svc.get_relationship("tomato", "basil")
    """

    def __init__(self) -> None:
        self._db: dict[str, Any] = {}
        # canonical_name -> {scientific_name, family, aliases}
        self._plant_meta: dict[str, dict[str, Any]] = {}
        # alias / scientific_name (lowercased) -> canonical common name
        self._name_index: dict[str, str] = {}
        # canonical_name -> list[CompanionRelationship] (this plant as plant_a)
        self._adjacency: dict[str, list[CompanionRelationship]] = {}
        self._custom_rules: list[CompanionRelationship] = []

        self._load_db()
        self._load_custom_rules()

    # ------------------------------------------------------------------
    # Public query API
    # ------------------------------------------------------------------

    def get_companions(
        self, plant_name: str
    ) -> tuple[list[CompanionRelationship], list[CompanionRelationship]]:
        """Return beneficial and antagonistic companions for a plant.

        Args:
            plant_name: Common name, scientific name, or alias (case-insensitive).

        Returns:
            Tuple of (beneficial_relationships, antagonistic_relationships).
        """
        canonical = self._resolve(plant_name)
        all_rels = self._adjacency.get(canonical, [])
        beneficial = [r for r in all_rels if r.type == BENEFICIAL]
        antagonistic = [r for r in all_rels if r.type == ANTAGONISTIC]
        return beneficial, antagonistic

    def get_relationship(
        self, plant_a: str, plant_b: str
    ) -> CompanionRelationship | None:
        """Return the relationship between two specific plants, or None.

        Args:
            plant_a: Name of the first plant.
            plant_b: Name of the second plant.

        Returns:
            CompanionRelationship if one exists, else None.
        """
        can_a = self._resolve(plant_a)
        can_b = self._resolve(plant_b)
        for rel in self._adjacency.get(can_a, []):
            if rel.plant_b == can_b:
                return rel
        return None

    def get_all_plant_names(self) -> list[str]:
        """Return all canonical common names in the database, sorted."""
        return sorted(self._plant_meta.keys())

    def get_plant_family(self, plant_name: str) -> str | None:
        """Return the botanical family for a plant, or None if unknown."""
        canonical = self._resolve(plant_name)
        return self._plant_meta.get(canonical, {}).get("family") or None

    def get_plant_scientific_name(self, plant_name: str) -> str | None:
        """Return the scientific name for a plant, or None if unknown."""
        canonical = self._resolve(plant_name)
        return self._plant_meta.get(canonical, {}).get("scientific_name") or None

    def get_plants_by_family(self, family: str) -> list[str]:
        """Return canonical names of all plants belonging to a botanical family."""
        family_lower = family.lower()
        return [
            name
            for name, meta in self._plant_meta.items()
            if meta.get("family", "").lower() == family_lower
        ]

    # ------------------------------------------------------------------
    # Custom rule management
    # ------------------------------------------------------------------

    def add_custom_rule(self, rule: CompanionRelationship) -> None:
        """Add or replace a custom companion planting rule.

        If a rule already exists for the same plant pair it is replaced.
        The rule is persisted to the user app-data directory.

        Args:
            rule: The custom relationship to add.
        """
        rule.is_custom = True
        rule.plant_a = rule.plant_a.lower()
        rule.plant_b = rule.plant_b.lower()
        # Remove existing rule for this pair first, then rebuild adjacency
        self._remove_rule_from_lists(rule.plant_a, rule.plant_b)
        self._custom_rules.append(rule)
        self._rebuild_adjacency()
        self._save_custom_rules()

    def remove_custom_rule(self, plant_a: str, plant_b: str) -> bool:
        """Remove a custom rule by plant pair.

        Args:
            plant_a: Name of the first plant.
            plant_b: Name of the second plant.

        Returns:
            True if a rule was removed, False if none was found.
        """
        can_a = self._resolve(plant_a)
        can_b = self._resolve(plant_b)
        original_count = len(self._custom_rules)
        self._remove_rule_from_lists(can_a, can_b)
        if len(self._custom_rules) < original_count:
            self._rebuild_adjacency()
            self._save_custom_rules()
            return True
        return False

    def get_custom_rules(self) -> list[CompanionRelationship]:
        """Return all user-defined custom rules."""
        return list(self._custom_rules)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, name: str) -> str:
        """Resolve any name to its canonical lowercase common name.

        Falls back to returning the lowercased input if no entry is found,
        so unknown plants still work for custom-rule lookups.
        """
        return self._name_index.get(name.lower(), name.lower())

    def _add_to_adjacency(self, rel: CompanionRelationship) -> None:
        """Insert a relationship into the adjacency index in both directions."""
        self._adjacency.setdefault(rel.plant_a, []).append(rel)
        reversed_rel = CompanionRelationship(
            plant_a=rel.plant_b,
            plant_b=rel.plant_a,
            type=rel.type,
            reason=rel.reason,
            is_custom=rel.is_custom,
        )
        self._adjacency.setdefault(rel.plant_b, []).append(reversed_rel)

    def _remove_rule_from_lists(self, can_a: str, can_b: str) -> None:
        """Remove a custom rule from self._custom_rules by canonical plant pair."""
        self._custom_rules = [
            r
            for r in self._custom_rules
            if not (
                (r.plant_a == can_a and r.plant_b == can_b)
                or (r.plant_a == can_b and r.plant_b == can_a)
            )
        ]

    def _rebuild_adjacency(self) -> None:
        """Rebuild the adjacency index from the raw DB and current custom rules."""
        self._adjacency = {}
        for entry in self._db.get("relationships", []):
            rel = CompanionRelationship(
                plant_a=entry["plant_a"].lower(),
                plant_b=entry["plant_b"].lower(),
                type=entry["type"],
                reason=entry.get("reason", ""),
            )
            self._add_to_adjacency(rel)
        for rule in self._custom_rules:
            self._add_to_adjacency(rule)

    def _load_db(self) -> None:
        """Load the bundled companion planting JSON database."""
        try:
            db_path = _DATA_DIR / "companion_planting.json"
            with open(db_path, encoding="utf-8") as f:
                self._db = json.load(f)
        except Exception:
            return

        for name, meta in self._db.get("plants", {}).items():
            canonical = name.lower()
            self._plant_meta[canonical] = meta
            self._name_index[canonical] = canonical
            sci = meta.get("scientific_name", "").lower()
            if sci:
                self._name_index[sci] = canonical
            for alias in meta.get("aliases", []):
                self._name_index[alias.lower()] = canonical

        for entry in self._db.get("relationships", []):
            rel = CompanionRelationship(
                plant_a=entry["plant_a"].lower(),
                plant_b=entry["plant_b"].lower(),
                type=entry["type"],
                reason=entry.get("reason", ""),
            )
            self._add_to_adjacency(rel)

    def _load_custom_rules(self) -> None:
        """Load user-defined custom rules from the app-data directory."""
        custom_path = get_app_data_dir() / _CUSTOM_RULES_FILENAME
        if not custom_path.exists():
            return
        try:
            with open(custom_path, encoding="utf-8") as f:
                data = json.load(f)
            for entry in data.get("rules", []):
                rule = CompanionRelationship(
                    plant_a=entry["plant_a"].lower(),
                    plant_b=entry["plant_b"].lower(),
                    type=entry["type"],
                    reason=entry.get("reason", ""),
                    is_custom=True,
                )
                self._custom_rules.append(rule)
                self._add_to_adjacency(rule)
        except Exception:
            pass

    def _save_custom_rules(self) -> None:
        """Persist custom rules to the app-data directory."""
        custom_path = get_app_data_dir() / _CUSTOM_RULES_FILENAME
        data = {
            "rules": [
                {
                    "plant_a": r.plant_a,
                    "plant_b": r.plant_b,
                    "type": r.type,
                    "reason": r.reason,
                }
                for r in self._custom_rules
            ]
        }
        try:
            with open(custom_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
