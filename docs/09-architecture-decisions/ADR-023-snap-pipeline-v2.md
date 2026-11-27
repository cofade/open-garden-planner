---
id: ADR-023
title: "Snap Pipeline v2"
status: "Accepted (Phase 13 — Package B, US-B4/B5/B6)"
legacy_anchor: adr-023-snap-pipeline-v2
---

# ADR-023: Snap Pipeline v2

**Status**: Accepted (Phase 13 — Package B, US-B4/B5/B6)

> An earlier draft of this ADR also covered the Paper Space MVP (US-B7). US-B7 was dropped during PR #191 manual-test review — the existing `pdf_report_service` already covers print-to-PDF at chosen paper sizes, and the second-space CAD-style workflow added no user value on top. The `ui/paper_space/` package, `services/scene_rendering.py`, and the `paper_layouts` persistence schema were deleted before merge. This ADR is now scoped to the snap-pipeline change alone. (`scene_rendering.py` survives separately as the PNG-export refactor target.)

**Context**: ADR-020 (snap registry + quadtree) shipped four kinds — endpoint, center, edge, midpoint, intersection. Package B added three more (nearest, perpendicular, tangent), two of which (perpendicular, tangent) are *not* a function of the cursor and the scene alone — they need a **second** anchor: the active tool's `last_point`. Perpendicular drops a foot from `last_point` onto the nearest edge; tangent finds the contact point of a line from `last_point` to a circle's tangent. Bolting these onto `SnapProvider.candidates(cursor, items, threshold)` would have meant either threading `view._drawing_tool.last_point` through every provider or having providers look it up themselves, breaking the pure-function contract.

**Decision**: Extend `SnapProvider.candidates()` with a single new optional argument: `reference_point: QPointF | None = None`, propagated through `SnapRegistry.best()` and `PointSnapper.snap()`. Existing providers (anchor, midpoint, intersection) accept the kwarg and ignore it; new providers (`PerpendicularSnapProvider`, `TangentSnapProvider`) act on it; `NearestSnapProvider` doesn't need it. `CanvasView._active_tool_reference_point()` centralises the lookup so callers don't poke into `tool_manager._active_tool` directly. Priority ordering: endpoint 10 < intersection 15 < center 20 < perpendicular 25 < tangent 26 < midpoint 30 < edge 40 < nearest 45 — the new modes slot below the established kinds.

**Alternatives considered**:
- *Add a `reference_point` provider attribute set externally before each query* — stateful and harder to test (providers should be pure functions of their inputs).
- *Pass a richer `SnapContext` object* — fits future expansion but adds noise for the four providers that don't need it. Defer until at least one more "needs side-channel state" provider arrives.

**Consequences**: The snap signature change is a one-time API churn — all in-tree providers were updated atomically, and external consumers (none yet) get a `None` default. Glyph rendering moved into `CanvasView.drawForeground` (each kind has its own shape: square=endpoint, circle=center, triangle=midpoint, X=intersection, hourglass=nearest, ⊥=perpendicular, small-circle+tangent-line=tangent) — no separate `snap_indicator.py` needed. `FILE_VERSION` bumped to 1.4 for the new `arc`/`bezier` item types; the loader rejects projects with a `version` higher than `FILE_VERSION` so an older binary can't silently round-trip a newer file. Tests: `test_perpendicular_snap_provider.py` (8), `test_tangent_snap_provider.py` (7), `test_nearest_snap_provider.py` (11) + integration tests; `test_scene_rendering.py` (3), `test_export_png_after_refactor.py` (2).
