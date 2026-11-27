---
id: ADR-014
title: "Bundled `plant_species.json` is single source of truth for species + calendar"
status: "Accepted (Phase 12 — issue #170)"
legacy_anchor: adr-014-bundled-plant_speciesjson-is-single-source-of-truth-for-species--calendar
---

# ADR-014: Bundled `plant_species.json` is single source of truth for species + calendar

**Status**: Accepted (Phase 12 — issue #170)
**Context**: Before #170 there were two bundled JSON files: `planting_calendar.json` (sow/transplant/harvest weeks, frost tolerance) consumed by `planting_calendar_db.py`, and an unbundled species record file that did not exist — species data only came from on-demand API search (Perenual/Trefle/Permapeople), which returns inconsistent or empty pH/NPK fields. Result: dropped plants had no `metadata["plant_species"]` until the user clicked Suchen, and US-12.10d (plant↔soil pH/nutrient warnings) silently no-op'd because `ph_min`/`ph_max`/`n/p/k_demand` were always None.
**Decision**: Collapse to one file — `src/open_garden_planner/resources/data/plant_species.json` — with full `PlantSpeciesData` records (incl. calendar fields) for every species the gallery exposes (118 records at land time: trees, shrubs, vegetables, herbs, berries, fruits, ornamentals). The new `bundled_species_db.py` module owns both the species-record API (`lookup_species`, `populate_item_species_metadata`) used by canvas drop / tool-draw paths, and the legacy calendar API (`get_calendar_entry`, `merge_calendar_data`) used by the plant detail panel. The old `planting_calendar.json` and `planting_calendar_db.py` are deleted.
**Alternatives considered**:
- *Two separate files (species + calendar)* — would duplicate `family`, `frost_tolerance`, `nutrient_demand` and create drift risk. The user explicitly rejected this in design discussion.
- *Auto-merge species data from the existing API at first launch* — only works with network access on first run, can't cover the offline installer experience, and the upstream APIs return inconsistent pH/NPK regardless.
- *Per-record source citations in the JSON* — adds noise. Sources cited at envelope level (`"sources": [...]`) is sufficient for the curated set.
**Consequences**: One file to maintain. Adding a species means writing one record with all fields populated. Drop flow auto-populates metadata for any of the 60+ bundled plants → US-12.10d warnings fire automatically. Long-tail species still fall through to the API search button. Bundle size grows by ~80 KB (negligible).

**Addendum (2026-11-19, #968 — bloom hardiness is a record field, not a list beside it).**
`Traits3D.frost_hardy_bloom` — whether a plant's *flowers* tolerate frost, which decides
whether it blooms by its own months outside the plan's frost-free season (#940) — was a
hand-kept set of sprite stems in `core/plant_art/traits3d.py`, beside the record's
`frost_tolerance`, held together by a one-directional drift guard. It is **not derivable**
from `frost_tolerance`: a beet is `hardy` and has no bloom to keep through a frost (it
bolts), a camellia is `half-hardy` and flowers in winter. So the datum moved into the
record (`"frost_hardy_bloom": true` on the 45 records that have it), which is what ADR-014
already means by "one file": a species' facts belong to its record, and a sprite with no
record is not bloom-hardy by construction. `traits3d` reads the file once at import and
maps records to sprites through the same resolver the gallery uses. The alternative —
keeping the list and documenting it — was rejected because the two could silently disagree
for a plant whose record was edited, which is what the drift guard existed to detect.
