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
    ANTAGONISTIC,
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

    # must_include members must be in candidates — and must survive the cap
    # below, so they are unioned in FIRST and the truncation then spares them.
    for m in resolved_must:
        if m not in resolved_candidates:
            resolved_candidates.append(m)

    # Cap candidates. Keep every must_include member: slicing the merged list
    # would silently drop a must_include appended at the end, making the result
    # depend on argument order (P1-4).
    if len(resolved_candidates) > MAX_CANDIDATES:
        capped = list(resolved_must)
        for c in resolved_candidates:
            if len(capped) >= MAX_CANDIDATES:
                break
            if c not in capped:
                capped.append(c)
        resolved_candidates = capped

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


def find_sets_for_bed(
    service: CompanionPlantingService,
    bed_plants: list[str],
    *,
    size: int = 3,
) -> dict[str, Any]:
    """Find compatible planting sets for the plants ALREADY in a bed.

    Why this is not ``find_compatible_sets(..., must_include=bed_plants)``:
    ``must_include`` means "every returned set must contain all of these", and
    Bron–Kerbosch only emits *maximal* cliques. Passing the whole bed therefore
    returns nothing unless the bed's plants already form a complete mutually
    beneficial set — which is exactly the situation the user is trying to fix.
    Measured on the bundled graph: that call returns 0 sets for 91% of two-plant
    beds and 100% of three-plant beds, while the palette it builds has ~18
    members. So the real question is "which sets agree with the MOST of what's
    already planted, and what conflicts with the rest?".

    Builds the same candidate palette as the panel/prompt (bed plants plus their
    beneficial companions), finds maximal cliques over it, then ranks them by
    how many bed plants each one already satisfies.

    Args:
        service: The companion planting service.
        bed_plants: Species keys of plants currently in the bed.
        size: Target set size (2–5).

    Returns:
        A dict with:
          ``sets``       — ranked sets, each carrying ``covers`` (bed members
                           included) and ``covers_all`` (bool).
          ``conflicts``  — ONLY bed plants that are genuinely antagonistic to
                           another bed plant, each naming what it clashes with.
                           Empty when no bed pair is antagonistic. A bed plant
                           that merely fits no set of the requested SIZE is
                           reported in ``uncovered`` instead — "not in any
                           3-clique" is not a clash, and calling it one told
                           users mint does not go with cabbage when the bundled
                           data says it does.
          ``uncovered``  — bed plants in no returned set, with no claim made
                           about why.
          ``bed_plants`` — the canonical bed-plant keys (echoed back).
          ``searched_size`` — the set size actually used, which is DOWN from
                           the requested one when no clique of that size
                           exists. Both callers surface it, so a caller can
                           tell "nothing of size 3 exists" from "nothing here
                           is compatible at all".
    """
    if size < 2 or size > 5:
        raise ValueError(f"size must be 2–5, got {size}")

    bed_keys: list[str] = []
    for name in bed_plants:
        canonical = service.resolve_name(name)
        if canonical not in bed_keys:
            bed_keys.append(canonical)

    # Palette: bed plants + one hop of their beneficial companions. This mirrors
    # what the panel and the polyculture prompt used to build by hand.
    candidates = list(bed_keys)
    for key in bed_keys:
        beneficial, _ = service.get_companions(key)
        for rel in beneficial:
            other = service.resolve_name(rel.plant_b)
            if other not in candidates:
                candidates.append(other)

    # No must_include — rank by coverage instead. Try the requested size first,
    # then step DOWN: a 2-clique pair is still real advice even when no third
    # mutual partner exists, and returning nothing for it (or calling it a
    # conflict) is the dead end this function exists to avoid.
    raw_sets: list[dict[str, Any]] = []
    searched_size = size
    for candidate_size in range(size, 1, -1):
        raw_sets = find_compatible_sets(
            service, candidates, size=candidate_size
        )
        searched_size = candidate_size
        if raw_sets:
            break

    covered: set[str] = set()
    for entry in raw_sets:
        members = set(entry["members"])
        covered |= members & set(bed_keys)
        entry["covers"] = sorted(members & set(bed_keys))
        entry["covers_all"] = bool(set(bed_keys).issubset(members))

    raw_sets.sort(
        key=lambda e: (-len(e["covers"]), not e["covers_all"], -e["score"], e["members"])
    )

    # ONLY genuine bed-internal antagonism is a conflict. Checked against the
    # bed's own contents, not against set coverage: an antagonistic pair can
    # never share a clique, so each member is trivially "in some set" via
    # different sets, and a coverage-only check would report nothing at all.
    conflicts: list[dict[str, Any]] = []
    for key in bed_keys:
        clashes = []
        for other in bed_keys:
            if other == key:
                continue
            rel = service.get_relationship(key, other)
            if rel is not None and rel.type == ANTAGONISTIC:
                clashes.append(other)
        if clashes:
            conflicts.append({"species_key": key, "antagonistic_to": clashes})

    uncovered = [key for key in bed_keys if key not in covered]

    return {
        "sets": raw_sets,
        "conflicts": conflicts,
        "uncovered": uncovered,
        "bed_plants": bed_keys,
        "searched_size": searched_size,
    }


def suggest_companions(
    service: CompanionPlantingService,
    species_key: str,
    *,
    exclude_antagonists_of: list[str] | None = None,
    language: str = "en",
) -> list[dict[str, Any]]:
    """Suggest companion plants for a given species, ranked by benefit.

    Args:
        service: The companion planting service.
        species_key: The species to find companions for.
        exclude_antagonists_of: Species keys whose antagonists should be
            excluded from suggestions (e.g. plants already in the bed).
        language: UI language code for the ``name`` display string. The
            ``species_key`` is a stable machine key and never changes with it.

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

    # Build suggestions. Keyed by species so a pair with more than one rule
    # (e.g. a Permapeople rule duplicating a bundled one, which
    # _load_provider_rules adds unconditionally) yields ONE entry, not two
    # identical rows (P2-12).
    suggestions: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for rel in beneficial:
        other = service.resolve_name(rel.plant_b)
        if other == canonical_query:
            continue
        if other in excluded:
            continue

        name = service.get_display_name(other, language)
        source = service.get_relationship_source(rel)

        reasons = [f"beneficial to {species_key}"]
        if other in two_hop:
            reasons.append(f"beneficial to {two_hop[other]} other companions")

        # Score: 1 for direct benefit + 0.5 per 2-hop connection
        score = 1.0 + 0.5 * two_hop.get(other, 0)

        entry = {
            "species_key": other,
            "name": name,
            "reasons": reasons,
            "source": source,
            "score": score,
        }
        existing = seen.get(other)
        if existing is None:
            seen[other] = entry
        else:
            # Keep the best score and prefer a provider/custom source over
            # "bundled" — it is the more specific provenance.
            if score > existing["score"]:
                entry["reasons"] = existing["reasons"] + [
                    r for r in entry["reasons"] if r not in existing["reasons"]
                ]
                seen[other] = entry
            if source != "bundled" and existing["source"] == "bundled":
                existing["source"] = source

    suggestions = list(seen.values())

    # Sort by score descending, then alphabetically
    suggestions.sort(key=lambda s: (-s["score"], s["species_key"]))

    return suggestions
