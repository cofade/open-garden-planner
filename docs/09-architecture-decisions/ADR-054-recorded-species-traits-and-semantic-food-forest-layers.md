---
id: ADR-054
title: "Recorded species traits and semantic food-forest layers"
status: "Accepted for Package F1, October 2026. Additive `.ogp` version 1.4."
refs: ["#312"]
legacy_anchor: adr-054-recorded-species-traits-and-semantic-food-forest-layers-312
---

# ADR-054: Recorded species traits and semantic food-forest layers

**Status:** Accepted for Package F1, October 2026. Additive `.ogp` version 1.4.

**Context.** Artwork archetypes, botanical niches and user-managed drawing layers have different meanings. Permapeople's Layer is a design niche, not a lifecycle. A selected plant's saved species snapshot may differ from the offline catalog and must remain undoable without updating a user's machine-wide library.

**Decision.** `PermacultureLayer` has seven concrete lowercase values plus `unknown`; `PlantFunction` has twelve stable lowercase values. Missing facts remain unspecified. Serialization orders/deduplicates functions and preserves unrecognized imported values in `raw_data`. One Qt-free exact-token provider mapper interprets Layer/Uses independently of lifecycle. No prose, name or nutrient-demand inference is permitted. The bundled database uses an explicit curation table, with function evidence documented in §8.26.

Selected-plant traits use `ChangePropertyCommand`, targeting only one saved species field with copied list snapshots. Persistent Plant Details controls refresh in place with blocked signals. Search filters the complete bundled/custom catalog before its display limit. A nonempty query with zero filtered offline matches invokes the configured provider chain; explicit online search is also available. Network requests run on workers, with dialog generation checks and parented polling timers rejecting obsolete results.

A canvas `Layer.permaculture_layer` semantic tag survives renaming/language changes. The seven-layer preset adds only missing tags in one command, preserving existing layers and active layer. The per-project auto-assignment setting defaults off and is undoable. The canonical plant constructor chooses an existing visible/unlocked tagged layer before the creation command; otherwise it uses the ordinary active layer. Editing plant traits never moves existing plants.

**Alternatives rejected.** Inferring traits from gallery categories misclassifies botanical facts; storing translated layer names as identifiers breaks renamed plans; changing the custom library silently changes other plans. Provider requests on the GUI thread freeze interaction.

**Evidence.** `test_permaculture_traits.py`, `test_permaculture_layer.py`, `test_permaculture_search.py`; the recorded Apple provider fixture is pinned offline. Live provider availability is delivery evidence, not a CI dependency.
