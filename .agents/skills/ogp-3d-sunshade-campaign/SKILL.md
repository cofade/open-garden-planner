---
name: ogp-3d-sunshade-campaign
description: >
  Reference pack for Open Garden Planner's SHIPPED 3D + sun/shade subsystems
  (Phase 14, v1.24.5 – v1.24.12 — complete; epic #255 closed). Load this skill
  when MAINTAINING or debugging any of it: 3D view history (Qt 3D, retired), sun path or
  solar position math, shadow projection/casting, shade or hours-of-sun
  heatmaps, object height property, seasonal/time-of-day sun animation,
  first-person walkthrough, or growth visualization. It is a reference, NOT a
  plan — its "TO BUILD" markers are historical and that code already exists. Also load when someone
  says "sun study", "shade map", "solar", "azimuth", "elevation angle",
  "shadow length", "height of fence/wall/tree", or asks which 3D engine to
  use. Contains verified repo asset inventory, the NOAA solar formulas with
  pinned reference numbers, Y-axis discipline for azimuth→scene conversion,
  and GO/NO-GO gates for the 3D engine spike.
---

# ogp-3d-sunshade-campaign reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| Phase 14 Campaign: 3D Visualization & Sun/Shade | [Read](references/000-phase-14-campaign-3d-visualization-sun-shade.md) |
| 0. Verified foundation inventory (EXISTS — all verified 2026-07-04) | [Read](references/001-0-verified-foundation-inventory-exists-all-verified-2026-07-04.md) |
| 1. Campaign map, scope slices, and the solution menu | [Read](references/002-1-campaign-map-scope-slices-and-the-solution-menu.md) |
| 2. Phase 0 — Prerequisites & scope contract | [Read](references/003-2-phase-0-prerequisites-scope-contract.md) |
| 3. Phase 1 — Solar position engine (`core/solar.py`) — TO BUILD | [Read](references/004-3-phase-1-solar-position-engine-core-solar-py-to-build.md) |
| 4. Phase 2 — Object height property — TO BUILD | [Read](references/005-4-phase-2-object-height-property-to-build.md) |
| 5. Phase 3 — 2D shadow projection MVP — TO BUILD | [Read](references/006-5-phase-3-2d-shadow-projection-mvp-to-build.md) |
| 6. Phase 4 — Shade aggregation: hours-of-sun heatmap — TO BUILD | [Read](references/007-6-phase-4-shade-aggregation-hours-of-sun-heatmap-to-build.md) |
| 7. Phase 5 — 3D view decision spike (GO/NO-GO) — TO BUILD | [Read](references/008-7-phase-5-3d-view-decision-spike-go-no-go-to-build.md) |
| 8. Phase 6 — Validation & promotion (per slice) | [Read](references/009-8-phase-6-validation-promotion-per-slice.md) |
| Appendix — Pinned reference numbers (generated 2026-07-04) | [Read](references/010-appendix-pinned-reference-numbers-generated-2026-07-04.md) |
| Provenance and maintenance | [Read](references/011-provenance-and-maintenance.md) |
| F3 maintenance: receiver estimates and document ownership (ADR-056) | [Read](references/012-f3-maintenance-receiver-estimates-and-document-ownership-adr-056.md) |
| F4 maintenance: plant lifetime on the shared date (ADR-062) | [Read](references/013-f4-maintenance-plant-lifetime-on-the-shared-date-adr-062.md) |

Current receiver model (#641): the original F3 ground-level estimate in the
dated maintenance reference below is historical. Per-plant results now use
the exact soil elevation from `item_base_cm`, slice external obstacles above
that plane and preserve holder exclusions. The heatmap remains at ground
level. See `docs/functional-requirements.md` FR-SUN-09/11 and the ADR-056
exact soil-plane addendum.
