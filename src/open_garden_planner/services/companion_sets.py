"""Compatible-set finder for companion planting (US-D3.1, issue #319).

Given a candidate palette of species, finds maximal cliques of mutually
beneficial, non-antagonistic plants using the Bron–Kerbosch algorithm over
the beneficial companion graph. Antagonist edges are hard exclusions —
no set ever contains an antagonist pair.

The algorithm is deterministic: candidates are processed in sorted order,
and results are ranked by compatibility score (number of beneficial edges
within the set), then alphabetically for stable output.
"""

from __future__ import annotations

from typing import Any

from open_garden_planner.services.companion_planting_service import (
    CompanionPlantingService,
)

# Cap on candidate palette size — prevents combinatorial explosion on large inputs.
MAX_CANDIDATES = 60
# Cap on the number of sets returned — keeps the output manageable.
MAX_SETS = 50


def find_compatible_sets(
    service: CompanionPlantingService,
    candidates: list[str],
    *,
    size: int = 3,
    must_include: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Find maximal compatible sets among the candidate species.

    Args:
        service: The companion planting service (provides the graph).
        candidates: Species keys to consider (e.g. ["corn", "bean", "squash"]).
        size: Target set size (2–5). Sets smaller than this are excluded.
        must_include: Species keys that must be in every returned set
            (e.g. plants already in the bed).

    Returns:
        A list of dicts with keys: members (sorted list), size, score,
        coverage. Sorted by score descending, then alphabetically.
    """
    if size < 2 or size > 5:
        raise ValueError(f"size must be 2–5, got {size}")

    must_include = must_include or []

    # Resolve all candidates to canonical names
    resolved_candidates = []
    for c in candidates:
        canonical = service.resolve_name(c)
        if canonical not in resolved_candidates:
            resolved_candidates.append(canonical)

    # Resolve must_include
    resolved_must = []
    for m in must_include:
        canonical = service.resolve_name(m)
        if canonical not in resolved_must:
            resolved_must.append(canonical)

    # Filter candidates: must_include members must be in candidates
    for m in resolved_must:
        if m not in resolved_candidates:
            resolved_candidates.append(m)

    # Cap candidates
    if len(resolved_candidates) > MAX_CANDIDATES:
        resolved_candidates = resolved_candidates[:MAX_CANDIDATES]

    # Build the beneficial graph as an adjacency set
    beneficial_graph: dict[str, set[str]] = {}
    antagonist_pairs: set[tuple[str, str]] = set()

    for sp in resolved_candidates:
        beneficial_graph[sp] = set()

    for sp in resolved_candidates:
        beneficial, antagonistic = service.get_companions(sp)
        for rel in beneficial:
            other = service.resolve_name(rel.plant_b)
            if other in beneficial_graph and other != sp:
                beneficial_graph[sp].add(other)
                beneficial_graph[other].add(sp)
        for rel in antagonistic:
            other = service.resolve_name(rel.plant_b)
            if other in beneficial_graph:
                pair = tuple(sorted([sp, other]))
                antagonist_pairs.add(pair)

    # Bron–Kerbosch with pivoting to find all maximal cliques
    cliques: list[set[str]] = []

    def _bron_kerbosch(
        r: set[str], p: set[str], x: set[str]
    ) -> None:
        if not p and not x:
            if len(r) >= size:
                # Check no antagonist pairs
                has_antagonist = False
                for a, b in antagonist_pairs:
                    if a in r and b in r:
                        has_antagonist = True
                        break
                if not has_antagonist:
                    cliques.append(r.copy())
            return

        # Pivot: choose the vertex in p ∪ x with most neighbors in p
        union_px = p | x
        if not union_px:
            return
        pivot = max(union_px, key=lambda v: len(beneficial_graph.get(v, set()) & p))

        # Iterate over p \ neighbors(pivot)
        pivot_neighbors = beneficial_graph.get(pivot, set())
        candidates_to_try = p - pivot_neighbors

        for v in sorted(candidates_to_try):
            neighbors_v = beneficial_graph.get(v, set())
            _bron_kerbosch(
                r | {v},
                p & neighbors_v,
                x & neighbors_v,
            )
            p.remove(v)
            x.add(v)

    _bron_kerbosch(set(), set(resolved_candidates), set())

    # Filter by must_include
    if resolved_must:
        must_set = set(resolved_must)
        cliques = [c for c in cliques if must_set.issubset(c)]

    # Build results
    results: list[dict[str, Any]] = []
    for clique in cliques:
        members = sorted(clique)
        # Score = number of beneficial edges within the set
        edge_count = 0
        for i, a in enumerate(members):
            for b in members[i + 1 :]:
                if b in beneficial_graph.get(a, set()):
                    edge_count += 1

        # Coverage: check if all members are in the bundled database
        all_in_db = all(m in service.get_all_plant_names() for m in members)
        any_in_db = any(m in service.get_all_plant_names() for m in members)

        if all_in_db:
            coverage = "full"
        elif any_in_db:
            coverage = "bundled_only"
        else:
            coverage = "partial"

        results.append({
            "members": members,
            "size": len(members),
            "score": float(edge_count),
            "coverage": coverage,
        })

    # Sort by score descending, then alphabetically
    results.sort(key=lambda r: (-r["score"], r["members"]))

    # Cap results
    return results[:MAX_SETS]


def suggest_companions(
    service: CompanionPlantingService,
    species_key: str,
    *,
    exclude_antagonists_of: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Suggest companion plants for a given species, ranked by benefit.

    Args:
        service: The companion planting service.
        species_key: The species to find companions for.
        exclude_antagonists_of: Species keys whose antagonists should be
            excluded from suggestions (e.g. plants already in the bed).

    Returns:
        A list of dicts with keys: species_key, name, reasons, source, score.
        Sorted by score descending.
    """
    exclude_antagonists_of = exclude_antagonists_of or []

    # Get all antagonists of the excluded species
    excluded: set[str] = set()
    for other in exclude_antagonists_of:
        _, antagonistic = service.get_companions(other)
        for rel in antagonistic:
            excluded.add(service.resolve_name(rel.plant_b))

    # Get beneficial companions for the query species
    beneficial, _ = service.get_companions(species_key)

    # Also get companions of companions (2-hop) for ranking
    canonical_query = service.resolve_name(species_key)
    two_hop: dict[str, int] = {}
    for rel in beneficial:
        other = service.resolve_name(rel.plant_b)
        if other == canonical_query:
            continue
        # Count how many of the query's companions also benefit from this one
        other_beneficial, _ = service.get_companions(other)
        for rel2 in other_beneficial:
            candidate = service.resolve_name(rel2.plant_b)
            if candidate != canonical_query and candidate != other:
                two_hop[candidate] = two_hop.get(candidate, 0) + 1

    # Build suggestions
    suggestions: list[dict[str, Any]] = []
    for rel in beneficial:
        other = service.resolve_name(rel.plant_b)
        if other == canonical_query:
            continue
        if other in excluded:
            continue

        name = service.get_display_name(other)
        source = service.get_relationship_source(rel)

        reasons = [f"beneficial to {species_key}"]
        if other in two_hop:
            reasons.append(f"beneficial to {two_hop[other]} other companions")

        # Score: 1 for direct benefit + 0.5 per 2-hop connection
        score = 1.0 + 0.5 * two_hop.get(other, 0)

        suggestions.append({
            "species_key": other,
            "name": name,
            "reasons": reasons,
            "source": source,
            "score": score,
        })

    # Sort by score descending, then alphabetically
    suggestions.sort(key=lambda s: (-s["score"], s["species_key"]))

    return suggestions
