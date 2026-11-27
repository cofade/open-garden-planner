---
id: ADR-007
title: "Tileable PNG Textures (over Procedural)"
status: "Superseded by ADR-042 (Phase 6)"
superseded_by: ["ADR-042"]
legacy_anchor: adr-007-tileable-png-textures-over-procedural
---

# ADR-007: Tileable PNG Textures (over Procedural)

**Status**: Superseded by ADR-042 (Phase 6)
**Context**: Current procedural patterns are too subtle. Need rich, recognizable textures.
**Decision**: Replace procedural fill patterns with pre-made tileable PNG textures.
**Rationale**: Better visual quality, easier to create realistic materials, AI-generated or CC0 sourced.
**Consequences**: Increases app bundle size. Need LOD management for different zoom levels. Less flexibility than procedural.
