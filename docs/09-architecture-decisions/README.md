# 9. Architecture Decisions

Architecture Decision Records (ADRs) for significant technical choices.

## ADR-001: PyQt6 as GUI Framework

**Status**: Accepted
**Context**: Need a desktop GUI framework for Python with strong 2D graphics support.
**Decision**: Use PyQt6 with QGraphicsView/Scene for the canvas.
**Rationale**: Mature, native look on all platforms, hardware-accelerated 2D, 3D-ready via Qt3D. Large community.
**Consequences**: GPLv3 license required. Larger app size than lightweight alternatives.

## ADR-002: Bottom-Left Coordinate Origin (Y-Up)

**Status**: Accepted
**Context**: Need to choose coordinate system convention for the canvas.
**Decision**: Bottom-left origin with Y-axis increasing upward (CAD convention).
**Rationale**: Standard in CAD software. Eases future 3D transition. Mathematical convention.
**Consequences**: Requires Y-flip transform in QGraphicsView (which uses Y-down). Some complexity in mouse coordinate handling.

## ADR-003: JSON Project File Format (.ogp)

**Status**: Accepted
**Context**: Need a project file format for saving/loading garden plans.
**Decision**: JSON-based .ogp files with embedded images (base64).
**Rationale**: Human-readable, VCS-friendly, no external database needed. Embedded images ensure portability.
**Consequences**: Large file sizes with embedded images. No binary efficiency. Version migration requires JSON schema evolution.

## ADR-004: Command Pattern for Undo/Redo

**Status**: Accepted
**Context**: Need robust undo/redo support for all editing operations.
**Decision**: Wrap all modifications in Command objects, push to QUndoStack.
**Rationale**: Industry standard pattern. Qt provides QUndoStack. Clean separation of actions from UI.
**Consequences**: Every new editing operation requires a corresponding Command class. More code but predictable behavior.

## ADR-005: Fixed Sidebar (Not Dockable)

**Status**: Accepted
**Context**: Whether to use dockable panels (Qt dock widgets) or fixed sidebar.
**Decision**: Fixed sidebar with collapsible panels.
**Rationale**: Simpler UX, consistent layout, no user confusion about panel placement. Lower implementation complexity.
**Consequences**: Less flexibility for power users. May revisit for future versions.

## ADR-006: AI-Generated SVG Assets

**Status**: Accepted (Phase 6)
**Context**: Need illustrated SVG graphics for plants, furniture, and infrastructure objects.
**Decision**: Use AI image generation to create consistent top-down plant/object illustrations, then convert to SVG.
**Rationale**: Fast production, consistent art style, fully custom, no licensing issues. Can iterate on style.
**Consequences**: Quality depends on AI generation capabilities. May need manual cleanup. Style may evolve.

## ADR-007: Tileable PNG Textures (over Procedural)

**Status**: Accepted (Phase 6)
**Context**: Current procedural patterns are too subtle. Need rich, recognizable textures.
**Decision**: Replace procedural fill patterns with pre-made tileable PNG textures.
**Rationale**: Better visual quality, easier to create realistic materials, AI-generated or CC0 sourced.
**Consequences**: Increases app bundle size. Need LOD management for different zoom levels. Less flexibility than procedural.

## ADR-008: Qt Linguist for i18n

**Status**: Accepted (Phase 6)
**Context**: Need multi-language support (English + German initially).
**Decision**: Use Qt Linguist translation system (tr() calls, .ts/.qm files).
**Rationale**: Native Qt integration, industry standard for Qt apps, supports plurals and context, good tooling.
**Consequences**: All strings must be wrapped in tr(). Requires pylupdate6/lrelease build steps. Translation memory maintained in .ts XML files.

## ADR-009: NSIS Windows Installer

**Status**: Accepted (Phase 6)
**Context**: Need professional distribution for public release.
**Decision**: PyInstaller (--onedir) bundled with NSIS installer script.
**Rationale**: Professional install experience (wizard, shortcuts, file association, uninstaller). NSIS is free, mature, widely used.
**Consequences**: Windows-only initially. Need to maintain NSIS script. Cross-platform support deferred.

## ADR-010: Branded Green Theme

**Status**: Accepted (Phase 6)
**Context**: Current theme is generic. Need visual identity.
**Decision**: Garden-themed green color palette as primary brand color with light/dark variants.
**Rationale**: Strong visual identity appropriate for a garden planning tool. Green is universally associated with gardens/nature.
**Consequences**: Replaces current generic light/dark theme. Need careful color balance to avoid "too much green".

## ADR-011: Hybrid Plant Rendering

**Status**: Accepted (Phase 6)
**Context**: How many unique plant SVG illustrations to create.
**Decision**: Hybrid approach: ~15-20 category-based shapes varied by color/size, plus unique illustrations for ~10 most popular species.
**Rationale**: Best balance of visual appeal and production effort. Category shapes cover 90% of cases. Popular species get special treatment.
**Consequences**: Need mapping logic from plant type/species to SVG file. Category shapes must be generic enough to represent multiple species.

## ADR-012: Hybrid Constraint Solver (Gauss-Seidel warm-start + Newton-Raphson refinement)

**Status**: Accepted (Phase 11 — issue #140)
**Context**: The original solver was a pure Gauss-Seidel relaxation loop. It resolves every constraint by a 1D projection along its own geometric direction. This works for decoupled systems but diverges on coupled ones — the canonical failure is two `EDGE_LENGTH` constraints sharing a vertex, where the feasible position is the intersection of two circles. Users reported that constraining edge A to 4.53 m and adjacent edge B to 5.00 m left edge A drifting to 5.21 m (both constraints geometrically satisfiable).
**Decision**: Keep Gauss-Seidel as a fast warm-start, then run damped Newton-Raphson refinement (`constraint_solver_newton.py`) when the residual exceeds tolerance. Add a closed-form circle-circle fast path for the shared-vertex case. Add `numpy` as an explicit dependency (`>=1.24`) for `linalg.lstsq`.
**Alternatives considered**:
- *Pure geometric closed-form* — would need a case per constraint-pair (O(16²)); brittle and high-maintenance.
- *scipy.optimize* — adds ~40 MB to the installer for a problem numpy solves in <20 variables.
- *Analytic Jacobian* — a nice-to-have optimization, but numerical central differences cost microseconds; deferred as TD-008.
**Consequences**: Robust behaviour for user-built CAD sketches (matches SolveSpace/Onshape expectations). +1 runtime dependency (numpy). Jacobian is numerical, not analytic — mild perf ceiling, no correctness impact. See §8.12 for the full solver architecture.
