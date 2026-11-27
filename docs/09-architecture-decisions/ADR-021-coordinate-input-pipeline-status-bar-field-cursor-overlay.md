---
id: ADR-021
title: "Coordinate Input Pipeline (Status-Bar Field + Cursor Overlay, Single Buffer)"
status: "Accepted (Phase 13 — Package A, US-A1/A2/A4)"
legacy_anchor: adr-021-coordinate-input-pipeline-status-bar-field--cursor-overlay-single-buffer
---

# ADR-021: Coordinate Input Pipeline (Status-Bar Field + Cursor Overlay, Single Buffer)

**Status**: Accepted (Phase 13 — Package A, US-A1/A2/A4)
**Context**: Typed coordinate entry is the most-requested workflow gap for users coming from AutoCAD/QCAD. Two UI surfaces are needed: a status-bar field (always-visible, CAD convention, predictable) and a cursor-anchored Dynamic Input overlay (modern, immediate). Without a shared state, the two surfaces drift out of sync, focus bounces between them, and the parser has to live in two places. Adding to the complexity, German users expect `,` as the decimal mark but `,` is also the natural dx/dy separator (`@500,200` → ambiguous: dx=500.2 or dx=500,dy=200?).

**Decision**: A single `CoordinateInputBuffer(QObject)` owns the text and the anchor point; both widgets read and write it via Qt signals (`text_changed`, `anchor_changed`, `committed`, `parse_error`). The pure-Python parser (`core/coordinate_input/parser.py`) accepts `@dx,dy` (relative), `@dist<angle` (polar, 0° = east, CCW positive, math convention) and `x,y` (absolute) with deterministic decimal/separator disambiguation rules (A–F): `;` is always separator; `.` + `,` mixed → `.` decimal; only commas → 1 = separator, 3 = locale decimal pair, 2 = ambiguous (prefer locale, `parse_alternative` exposes the secondary reading). The buffer is owned by `CanvasView`; the status-bar `CoordinateInputField(QLineEdit)` (inserted into the existing `_setup_status_bar`) and the floating `DynamicInputOverlay` both subscribe. Anchor is refreshed after every tool `mouse_press`/`mouse_release`/`mouse_double_click`/`key_press` and after tool changes (which also clears stale text). `BaseTool` gains `last_point` (default `None`) and `commit_typed_coordinate(point)` (default no-op); drawing tools (polyline, polygon, circle, rectangle, ellipse, construction line/circle) implement both, reusing the same code path as a mouse click would.

**Alternatives considered**:
- *Status-bar field only* — predictable but slower; users have to glance away from the cursor.
- *Cursor overlay only* — modern but loses always-visible affordance and is easy to dismiss.
- *Locale-only decimal* — would fail every English-speaking user who pastes `100.5,200`.
- *Separator-only decimal* (CAD legacy) — fails German users who naturally type `1,5`.
- *Per-tool typed-input hooks* — would have duplicated focus/anchor wiring N times.

**Consequences**: Adding a new drawing tool that supports typed input is two methods (`last_point` getter + `commit_typed_coordinate`). The parser is reusable for future CSV/DXF-style imports of point lists. The Y-axis flip lives in one place (the parser): user-entered Y reads as math-up-positive and is converted to scene-down-positive at parse time, so the rest of the codebase keeps its existing Y-down convention. The overlay is hidden while the active tool's `last_point` is `None`, avoiding a meaningless polar input UI. `View → Enable Dynamic Input` toggles the overlay independently of the status-bar field. The buffer's `parse_alternative` is currently unused by the UI but available for a future "interpreting as …" tooltip if 2-comma ambiguity becomes a support pain point. **Polar without anchor**: the parser requires `last_point` for polar input (with or without `@`); without it, a `ParseError` is raised instead of silently falling back to the origin — a silent fallback would place a vertex far from the cursor with no feedback.
