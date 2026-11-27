---
id: ADR-011
title: "Hybrid Plant Rendering"
status: "Superseded by ADR-040 (Phase 6)"
superseded_by: ["ADR-040"]
legacy_anchor: adr-011-hybrid-plant-rendering
---

# ADR-011: Hybrid Plant Rendering

**Status**: Superseded by ADR-040 (Phase 6)
**Context**: How many unique plant SVG illustrations to create.
**Decision**: Hybrid approach: ~15-20 category-based shapes varied by color/size, plus unique illustrations for ~10 most popular species.
**Rationale**: Best balance of visual appeal and production effort. Category shapes cover 90% of cases. Popular species get special treatment.
**Consequences**: Need mapping logic from plant type/species to SVG file. Category shapes must be generic enough to represent multiple species.
