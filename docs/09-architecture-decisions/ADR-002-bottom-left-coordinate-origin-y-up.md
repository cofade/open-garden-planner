---
id: ADR-002
title: "Bottom-Left Coordinate Origin (Y-Up)"
status: "Accepted"
legacy_anchor: adr-002-bottom-left-coordinate-origin-y-up
---

# ADR-002: Bottom-Left Coordinate Origin (Y-Up)

**Status**: Accepted
**Context**: Need to choose coordinate system convention for the canvas.
**Decision**: Bottom-left origin with Y-axis increasing upward (CAD convention).
**Rationale**: Standard in CAD software. Eases future 3D transition. Mathematical convention.
**Consequences**: Requires Y-flip transform in QGraphicsView (which uses Y-down). Some complexity in mouse coordinate handling.
