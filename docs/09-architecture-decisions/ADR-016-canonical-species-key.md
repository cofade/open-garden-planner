---
id: ADR-016
title: "Canonical Species Key"
status: "Accepted (Phase 12 — issue #176)"
legacy_anchor: adr-016-canonical-species-key
---

# ADR-016: Canonical Species Key

**Status**: Accepted (Phase 12 — issue #176)
**Context**: Five species identity fields existed across the codebase — `source_id`, `scientific_name`, `common_name`, `species_id`, `species_name` — with each module resolving them in a different order and with different normalisation. US-12.6 patched around the inconsistency with a local `_norm_species_key()` function in `shopping_list_service.py`. US-12.8 (Succession Planting) and US-12.9 (Journal) would both need to key data by species and would have baked the inconsistency deeper or invented yet another normaliser.
**Decision**: A single `species_key(species: dict[str, str]) -> str` function in `models/plant_data.py` is the only sanctioned way to derive a stable dict key from a species dict. Priority: `source_id` → `scientific_name` → `common_name`. Output is always `.strip().lower()`. Returns `"_unknown"` if all fields are absent or empty. All existing call sites migrated in issue #176.
**Rationale**: `source_id` is preferred because it is stable across common-name renames; all existing comparisons already worked case-insensitively once stripped, so the normalisation step is backward-compatible with on-disk project files. Centralising the logic means future call sites cannot diverge silently.
**Alternatives considered**:
- *New UUID `species_id` field on every canvas item* — would give a true stable key. Rejected: requires a data-migration for existing `.ogp` files and a coordinated change to the plant-drop workflow. Deferred until a file-version bump is warranted.
- *Normalise inside every caller* — the status quo. Rejected: each caller diverged slightly; the inconsistency was already causing phantom seed-gap misses in US-12.6.
**Consequences**: Keys in `propagation_overrides` and `shopping_list_prices` are stable unless a plant's `source_id` changes (API re-imports only — rare). `crop_rotation_service.py` was not migrated because it keys exclusively on botanical family name, not species identity.
