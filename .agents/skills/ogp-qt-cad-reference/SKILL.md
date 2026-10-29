---
name: ogp-qt-cad-reference
description: >
  Domain-theory knowledge pack for Qt Graphics View + CAD geometry as used in
  Open Garden Planner. Load when: touching canvas items or tools, anything
  involving coordinates or the Y-flip, rendering/export (PNG/PDF/SVG/DXF/agent
  render tool), rotation/resize/transformOriginPoint, snapping or the
  constraint solver, drag handles / ItemIgnoresTransformations, curves and
  arcs, scene/signal lifecycle bugs, or writing Qt tests (qtbot, QTest,
  tool.mouse_press). Teaches the mental models a zero-context engineer lacks;
  every claim is grounded in this repo's source and docs.
---

# ogp-qt-cad-reference reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| OGP Qt + CAD Reference | [Read](references/000-ogp-qt-cad-reference.md) |
| When NOT to use this skill | [Read](references/001-when-not-to-use-this-skill.md) |
| Quick glossary (Qt terms, defined once) | [Read](references/002-quick-glossary-qt-terms-defined-once.md) |
| 1. Coordinate systems — the one mental model | [Read](references/003-1-coordinate-systems-the-one-mental-model.md) |
| 2. The QGraphicsItem geometry contract | [Read](references/004-2-the-qgraphicsitem-geometry-contract.md) |
| 3. `ItemIgnoresTransformations` — what it buys and its two traps | [Read](references/005-3-itemignorestransformations-what-it-buys-and-its-two-traps.md) |
| 4. Signals, slots, and lifecycle safety | [Read](references/006-4-signals-slots-and-lifecycle-safety.md) |
| 5. Snap engine + constraint solver theory | [Read](references/007-5-snap-engine-constraint-solver-theory.md) |
| 6. Curves and arcs (ADR-022/025, `core/cad_geometry.py`) | [Read](references/008-6-curves-and-arcs-adr-022-025-core-cad-geometry-py.md) |
| 7. Driving events in tests — two tiers, one hard rule | [Read](references/009-7-driving-events-in-tests-two-tiers-one-hard-rule.md) |
| Provenance and maintenance | [Read](references/010-provenance-and-maintenance.md) |
