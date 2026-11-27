---
id: ADR-017
title: "Bed-Specific Features Built Centrally on `GardenItemMixin`"
status: "Accepted (Phase 12 — US-12.8 post-bug)"
legacy_anchor: adr-017-bed-specific-features-built-centrally-on-gardenitemmixin
---

# ADR-017: Bed-Specific Features Built Centrally on `GardenItemMixin`

**Status**: Accepted (Phase 12 — US-12.8 post-bug)
**Context**: Bed-capable shapes are not a single class but four (`RectangleItem`, `PolygonItem`, `EllipseItem`, `CircleItem`) — historical reasons: garden beds are drawn as polygons, raised beds as rectangles, in-ground round beds as circles or ellipses. Each new "bed-only" feature (grid toggle, soil-test entry, pest/disease log, succession plan) was hand-copied into all four `contextMenuEvent` methods. Twice in a row a feature shipped missing from one or more shapes: pest/disease log was missing from `PolygonItem` and `EllipseItem` until #173 added it; succession-plan ("Plan Anbaufolge…") was missing from all three non-rectangle shapes until the post-US-12.8 fix.
**Decision**: Bed-action construction and dispatch live on `GardenItemMixin` as `build_bed_context_menu(menu, *, grid_enabled, supports_grid)` and `dispatch_bed_action(action, actions)`, returning a `BedMenuActions` dataclass. Every bed-capable shape's `contextMenuEvent` calls these two methods inside its `is_bed_type` guard; no shape adds its own action constants for grid/soil/pest/succession. A parametrised regression test (`tests/integration/test_bed_context_menu.py`) iterates over all four shape classes and fails for any missing bed action.
**Rationale**: Adding a fifth shape (or new bed feature) is now a one-file change instead of a four-file diff. The regression test makes divergence detectable in CI rather than at user-report time. Centralising also means translation strings live in a single `"BedActions"` context, so the German/English wording is the same regardless of which shape opened the menu.
**Alternatives considered**:
- *Per-shape menus, manual sync* — the status quo. Rejected: failed twice in three months.
- *Unify the four classes into one* — much larger refactor, complicated by different shape semantics (vertex editing on Polygon, radius on Circle, etc.).
- *Plugin/registry pattern (bed features as data)* — overkill for four actions. The mixin method is just enough indirection.
**Consequences**: Bed-only menu strings now live under context `"BedActions"` instead of `"RectangleItem"`/`"PolygonItem"`/etc. — historical translations under per-shape contexts remain valid for non-bed menu entries (delete, duplicate, arrays, etc.). When introducing a NEW bed feature in the future, the entry point is `BedMenuActions` + `build_bed_context_menu` + `dispatch_bed_action`. The parametrised test must be extended with an `assert actions.<new_field> is not None` line — that single assertion forces the dev to remember the central path.
