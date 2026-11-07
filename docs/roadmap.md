# Development Roadmap

## Overview

Current work and delivery status. GitHub issues own the work list; ADRs and the
functional requirements own decisions and capability.

| Phase | Version | Status | Description |
|-------|---------|--------|-------------|
| 1 | v0.1 | ✅ Complete | Foundation: Canvas, drawing, file operations |
| 2 | v0.2 | ✅ Complete | Precision: Image import, calibration, measurement |
| 3 | v0.3 | ✅ Complete | Objects & Styling: Rich objects, textures, layers |
| 4 | v0.4 | ✅ Complete | Plants & Metadata: Plant objects, API, sidebar |
| 5 | v0.5 | ✅ Complete | Export & Polish: PNG/SVG/CSV export, shortcuts, themes |
| Backlog | - | ✅ Complete | Rotation, vertex editing, annotations |
| ~~6~~ | ~~v1.0~~ | ~~✅ Complete~~ | ~~Visual Polish & Public Release~~ |
| ~~7~~ | ~~v1.1 – v1.6~~ | ~~✅ Complete~~ | ~~CAD Precision & Constraints~~ |
| **8** | **v1.7 – v1.8.3** | **✅ Complete** | **Location, Climate & Planting Calendar** |
| **9** | **v1.8.5 – v1.8.6** | **✅ Complete** | **Seed Inventory & Propagation Planning** |
| **10** | **v1.8.6 – v1.8.12** | **✅ Complete** | **Companion Planting & Crop Rotation** |
| **11** | **v1.8.13+** | **✅ Complete** | **Bed Interior Design, Visual Polish & Advanced 2D Tools** |
| **12** | **v1.9.0 – v1.10.x** | **✅ Complete** | **Weather & Smart Features** |
| **13** | **v1.11 – v1.29.1** | **✅ Complete (Packages A–D)** | **CAD Precision, Smart Features & Agent Integration** |
| **14** | **v1.24.5 – v1.24.12** | **✅ Complete** ([epic #255](https://github.com/cofade/open-garden-planner/issues/255); no v2.0 bump — see the Phase 14 section) | **3D Visualization & Sun/Shade** |
| **15** | **v1.25.0 – v1.27.0** | **✅ Complete** (Packages 1–3; epic [#284](https://github.com/cofade/open-garden-planner/issues/284)) | **Visual Refresh** |
| 16 | — | Future | Platform & Community |
| 17 | v1.29.10 – v1.37.0 | ✅ Complete (L0–L7; epic [#383](https://github.com/cofade/open-garden-planner/issues/383)) | Living Garden 3D |

## Current work

No roadmap phase is active. Open work is tracked in GitHub issues; the current themes are:

| Theme | Open issues | Why it matters |
|-------|-------------|----------------|
| Store/MSIX readiness | #767, #764, #375 | Distribution and user-data safety on the second channel. |
| 3D rendering quality and performance | #744, #743, #734, #719, #716, #534, #531 | The 3D view's trust and frame budget. |
| CAD and drawing tools | #771, #769, #768, #664, #666 | Precision and editing depth. |
| Architecture and tech debt | #770, #667 | Remove redundant surfaces and make tests repeatable. |

This table is a pointer, not a tracker. Each issue owns its scope and acceptance criteria.

## Completed

### ~~Phase 1: Foundation (v0.1)~~ ✅

**Goal**: Basic working application with canvas, drawing, and file operations.

| ID | User Story | Status |
|----|------------|--------|
| ~~US-1.1~~ | ~~Create new project with specified dimensions~~ | ✅ |
| ~~US-1.2~~ | ~~Pan and zoom the canvas smoothly~~ | ✅ |
| ~~US-1.3~~ | ~~Draw rectangles and polygons on the canvas~~ | ✅ |
| ~~US-1.4~~ | ~~Select, move, and delete objects~~ | ✅ |
| ~~US-1.5~~ | ~~Save project to file and reopen it~~ | ✅ |
| ~~US-1.6~~ | ~~Undo and redo actions~~ | ✅ |
| ~~US-1.7~~ | ~~See cursor coordinates in real-time~~ | ✅ |
| ~~US-1.8~~ | ~~Application displays OGP logo icon~~ | ✅ |
| ~~US-1.9~~ | ~~GitHub repository displays banner image~~ | ✅ |

### ~~Phase 2: Precision & Calibration (v0.2)~~ ✅

**Goal**: Image import, calibration, and measurement tools for real-world accuracy.

| ID | User Story | Status |
|----|------------|--------|
| ~~US-2.1~~ | ~~Import a background image (satellite photo)~~ | ✅ |
| ~~US-2.2~~ | ~~Calibrate the image by marking a known distance~~ | ✅ |
| ~~US-2.3~~ | ~~Toggle a grid overlay~~ | ✅ |
| ~~US-2.4~~ | ~~Snap objects to the grid~~ | ✅ |
| ~~US-2.5~~ | ~~Measure distances between any two points~~ | ✅ |
| ~~US-2.6~~ | ~~See area/perimeter of selected polygons and circles~~ | ✅ |
| ~~US-2.7~~ | ~~Adjust background image opacity~~ | ✅ |
| ~~US-2.8~~ | ~~Lock the background image to prevent moving it~~ | ✅ |
| ~~US-2.9~~ | ~~Draw circles by clicking center then a rim point~~ | ✅ |

### ~~Phase 3: Objects & Styling (v0.3)~~ ✅

**Goal**: Rich object types with visual customization.

| ID | User Story | Status |
|----|------------|--------|
| ~~US-3.1~~ | ~~Add property objects (house, fence, path, etc.)~~ | ✅ |
| ~~US-3.2~~ | ~~Set fill color for objects~~ | ✅ |
| ~~US-3.3~~ | ~~Apply textures/patterns to objects~~ | ✅ |
| ~~US-3.4~~ | ~~Set stroke style (color, width, dash pattern)~~ | ✅ |
| ~~US-3.5~~ | ~~Add labels to objects displayed on canvas~~ | ✅ |
| ~~US-3.6~~ | ~~Organize objects into layers~~ | ✅ |
| ~~US-3.7~~ | ~~Show/hide and lock layers~~ | ✅ |
| ~~US-3.8~~ | ~~Copy and paste objects~~ | ✅ |

### ~~Phase 4: Plants & Metadata (v0.4)~~ ✅

**Goal**: First-class plant objects with metadata and database integration.

| ID | User Story | Status |
|----|------------|--------|
| ~~US-4.1~~ | ~~Add plant objects (tree, shrub, perennial)~~ | ✅ |
| ~~US-4.2~~ | ~~Set plant metadata (species, variety, dates)~~ | ✅ |
| ~~US-4.3~~ | ~~Search for plant species from online database~~ | ✅ |
| ~~US-4.4~~ | ~~Create custom plant species in library~~ | ✅ |
| ~~US-4.5~~ | ~~View plant details in properties panel~~ | ✅ |
| ~~US-4.6~~ | ~~Add garden beds with area calculation~~ | ✅ |
| ~~US-4.7~~ | ~~Filter/search plants in project~~ | ✅ |
| ~~US-4.8~~ | ~~Organized sidebar with icon-based tool panels~~ | ✅ |
| ~~US-4.9~~ | ~~Resize objects by dragging handles~~ | ✅ |

### ~~Phase 5: Export & Polish (v0.5)~~ ✅

**Goal**: Production-ready release with export capabilities and polished UX.

| ID | User Story | Status |
|----|------------|--------|
| ~~US-5.1~~ | ~~Export plan as PNG in various resolutions~~ | ✅ |
| ~~US-5.2~~ | ~~Export plan as SVG~~ | ✅ |
| ~~US-5.3~~ | ~~Export plant list as CSV~~ | ✅ |
| ~~US-5.4~~ | ~~Keyboard shortcuts for all common actions~~ | ✅ |
| ~~US-5.5~~ | ~~Light and dark mode switch~~ | ✅ |
| ~~US-5.6~~ | ~~Welcome screen with recent projects~~ | ✅ |
| ~~US-5.7~~ | ~~Auto-save periodically~~ | ✅ |
| ~~US-5.8~~ | ~~Professional SVG icons for all drawing tools~~ | ✅ |

### ~~Backlog: Core Editing Enhancements~~ ✅

| ID | User Story | Status |
|----|------------|--------|
| ~~US-B.1~~ | ~~Rotate objects (free + 15 degree snap)~~ | ✅ |
| ~~US-B.2~~ | ~~Edit polygon vertices (move, add, remove)~~ | ✅ |
| ~~US-B.3~~ | ~~Vertex coordinate annotations on selection~~ | ✅ |

### Phase 6: Visual Polish & Public Release (v1.0) ✅ Complete

**Goal**: Transform the application from a functional tool into a visually stunning, professionally polished product ready for its first public release. Inspired by competitor analysis of Gardena My Garden and Garden Planner 3.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-6.1 | Rich tileable textures for all materials | Must | ✅ Done |
| US-6.2 | Illustrated SVG plant rendering (hybrid approach) | Must | ✅ Done |
| US-6.3 | Drop shadows on all objects (toggleable) | Must | ✅ Done |
| US-6.4 | Visual scale bar on canvas | Must | ✅ Done |
| US-6.5 | Visual thumbnail gallery sidebar | Must | ✅ Done |
| US-6.6 | Toggleable object labels on canvas | Should | ✅ Done |
| US-6.7 | Branded green theme (light/dark variants) | Should | ✅ Done |
| US-6.8 | Outdoor furniture objects | Must | ✅ Done |
| US-6.9 | Garden infrastructure objects | Must | ✅ Done |
| US-6.10 | Object snapping & alignment tools | Should | ✅ Done |
| US-6.11 | Fullscreen preview mode (F11) | Should | ✅ Done |
| US-6.12 | Internationalization (EN + DE, Qt Linguist) | Must | ✅ Done |
| US-6.13 | Print support with scaling | Should | ✅ Done |
| US-6.14 | Windows installer (NSIS) + .ogp file association | Must | ✅ Done |
| US-6.15 | Path & fence style presets | Must | ✅ Done |

### ~~Phase 7: CAD Precision & Constraints (v1.1 – v1.6)~~ ✅

**Goal**: Full 2D geometric constraint system with numeric precision input, construction aids, and pattern placement — bringing FreeCAD Sketcher-level precision to garden planning.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-7.1 | Measure tool snap to object anchors (centers + edges) | Must | ✅ Done |
| US-7.2 | Distance constraint data model & solver | Must | ✅ Done |
| US-7.3 | Distance constraint tool (dedicated toolbar tool) | Must | ✅ Done |
| US-7.4 | Dimension line visualization (FreeCAD-style, toggleable) | Must | ✅ Done |
| US-7.5 | Constraint solver drag integration (chain propagation) | Must | ✅ Done |
| US-7.6 | Constraints manager panel | Must | ✅ Done |
| US-7.7 | Numeric position input (editable X, Y in properties) | Must | ✅ Done |
| US-7.8 | Numeric dimension input (editable width/height/radius) | Must | ✅ Done |
| US-7.9 | Horizontal/Vertical alignment constraints | Should | ✅ Done |
| US-7.10 | Angle constraints | Should | ✅ Done |
| US-7.11 | Symmetry constraints | Should | ✅ Done |
| US-7.12 | Construction geometry (helper lines, not in exports) | Should | ✅ Done |
| US-7.13 | Draggable guide lines | Should | ✅ Done |
| US-7.14 | Linear array placement | Could | ✅ Done |
| US-7.15 | Grid array placement | Could | ✅ |
| US-7.16 | Circular array placement | Could | ✅ Done |
| US-7.17 | Coincident constraint (merge two anchor points) | Should | ✅ Done |
| US-7.18 | Parallel constraint (two edges stay parallel) | Could | ✅ Done |
| US-7.19 | Perpendicular constraint (two edges at 90°) | Could | ✅ Done |
| US-7.20 | Equal size constraint (same radius/width/height) | Could | ✅ Done |
| US-7.21 | Fix in place / Block constraint (pin object permanently) | Could | ✅ Done |
| US-7.22 | Horizontal/Vertical distance constraints (1D dimensional) | Could | ✅ Done |
| **US-7.23** | **FreeCAD-style constraint toolbar with full icon set** | **Must** | ✅ Done |

### Phase 8: Location, Climate & Planting Calendar (v1.7) ✅ Complete

**Goal**: Enable location-aware planting schedules with a dashboard showing what to do today/this week/this month.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-8.1 | GPS location & climate zone setup | Must | ✅ |
| US-8.2 | Frost date & hardiness zone API lookup | Must | ✅ |
| US-8.3 | Auto-update notification & one-click installer download | Should | ✅ |
| US-8.4 | Plant calendar data model | Must | ✅ |
| US-8.5 | Planting calendar view (tab) | Must | ✅ |
| US-8.6 | Dashboard / today view | Must | ✅ |
| US-8.7 | Tab-based main window architecture | Must | ✅ |

### Phase 9: Seed Inventory & Propagation Planning (v1.8) ✅ Complete

**Goal**: Manage seed packets ("Samenbeutel"), track viability, and plan the full propagation cycle from indoor sowing to transplanting.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-9.1 | Seed packet data model | Must | ✅ v1.8.4 |
| US-9.2 | Seed viability database | Must | ✅ v1.8.4 |
| US-9.3 | Seed inventory management panel | Must | ✅ v1.8.4 |
| US-9.4 | Seed inventory tab view | Must | ✅ v1.8.4 |
| US-9.5 | Propagation planning (pre-cultivation) | Should | ✅ v1.8.5 |
| US-9.6 | Seed-to-plant manual linking | Should | ✅ v1.8.6 |

### Phase 10: Companion Planting & Crop Rotation (v1.8.6 – v1.8.12) ✅ Complete

**Goal**: Help gardeners optimize plant placement with companion planting recommendations and multi-year crop rotation tracking.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-10.1 | Companion planting database | Must | ✅ v1.8.6 |
| US-10.2 | Companion planting visual warnings | Must | ✅ v1.8.7 |
| US-10.3 | Companion planting recommendation panel | Should | ✅ v1.8.8 |
| US-10.4 | Whole-plan compatibility check | Should | ✅ v1.8.9 |
| US-10.5 | Crop rotation data model | Must | ✅ v1.8.11 |
| US-10.6 | Crop rotation recommendations | Should | ✅ v1.8.11 |
| US-10.7 | Season management & plan duplication | Could | ✅ v1.8.12 |

### Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools (v1.8.x) ✅ Complete

**Goal**: Perfect the 2D garden planning experience — bed interiors, annotations, shape operations, drawing tools, interoperability and workflow.

| Status | US | User Story |
|--------|----|------------|
| ✅ | US-11.1 | Plant-Bed Parent-Child Relationship |
| ✅ | US-11.2 | Plant Spacing Circles & Overlap Warnings |
| ✅ | US-11.3 | Square-Foot Grid Overlay |
| ✅ | US-11.5 | Expanded Fill Pattern Library |
| ✅ | US-11.6 | Plant Illustration Expansion & Style Refresh |
| ✅ | US-11.7 | Minimap / Overview Panel |
| ✅ | US-11.8 | Free Text Annotation Tool |
| ✅ | US-11.9 | Auto Area Labels |
| ✅ | US-11.10 | Callout / Leader Line Annotations |
| ✅ | US-11.11 | Group / Ungroup |
| ✅ | US-11.12 | Boolean Shape Operations |
| ✅ | US-11.13 | Array Along Path |
| ✅ | US-11.14 | Ellipse Drawing Tool |
| ✅ | US-11.15 | Offset Tool |
| ✅ | US-11.16 | Trim / Extend Tool |
| ✅ | US-11.24 | Find & Replace Objects |

### Phase 12: Weather & Smart Features (v1.9.0 – v1.10.x) ✅ Complete

**Goal**: Bring live weather data into the garden planning workflow — forecast-based watering decisions and plant-aware frost warnings, fetched at startup via Open-Meteo (no API key required) — plus interoperability (DXF, multi-page PDF) and smart features (shopping list, pest/disease log, succession planting, garden journal, soil health & amendments).

| ID       | User Story                                  | Priority | Status |
|----------|---------------------------------------------|----------|--------|
| US-12.1  | Weather forecast widget in Dashboard         | Must     | ✅     |
| US-12.2  | Frost alert & plant-aware warnings           | Must     | ✅     |
| US-12.3  | DXF export                                   | Should   | ✅     |
| US-12.4  | DXF import                                   | Should   | ✅     |
| US-12.5  | Multi-page PDF export                        | Should   | ✅     |
| US-12.6  | Shopping list generation                     | Could    | ✅     |
| US-12.7  | Pest & disease log                           | Could    | ✅     |
| US-12.8  | Succession planting                          | Could    | ✅     |
| US-12.9  | Garden journal (map-linked notes)            | Could    | ✅     |
| US-12.10 | Soil health tracking & amendment calculator  | Must     | ✅     |
| US-12.11 | Smart amendment composition + library toggle | Should   | ✅     |

### Phase 13: CAD Precision Boost — Package A (v1.11.0) ✅ Complete

**Goal**: Close the most-cited CAD precision gaps in one PR — typed coordinate input (relative + polar), two new snap modes (midpoint + intersection) under a unified snap engine, and a Dynamic Input cursor overlay. See ADR-020 (snap engine) and ADR-021 (input pipeline). Bundled as GitHub issue #186.

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | A1    | Relative coordinate input `@dx,dy` (status bar + cursor overlay) |
| ✅     | A2    | Polar coordinate input `@dist<angle`                             |
| ✅     | A3    | Midpoint + intersection snap modes, View-menu toggles            |
| ✅     | A4    | Dynamic Input cursor-anchored overlay                            |

### Phase 13: CAD Precision Boost — Package B (v1.12.0) ✅ Complete

**Goal**: Close the remaining CAD precision gaps in one coordinated release — curve tools (cubic Bezier + 3-point arc), corner editors (fillet + chamfer), and three new reference-point-aware snap modes (nearest, perpendicular, tangent). See ADR-022 (Bezier model + filleted-rectangle conversion) and ADR-023 (snap pipeline v2).

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | B1    | Cubic Bezier pen tool (drawing only; placed-curve editing → US-B9) |
| ✅     | B2    | 3-point Arc tool (collinear → polyline fallback)                 |
| ✅     | B3    | Fillet (`Shift+F`) + Chamfer (`Shift+C`) corner editors          |
| ✅     | B4    | Nearest-point fallback snap                                      |
| ✅     | B5    | Perpendicular snap from active tool's `last_point`               |
| ✅     | B6    | Tangent snap onto circles + arcs from `last_point`               |
| ⛔     | B7    | Paper Space MVP — *dropped*; see note below                      |

### Phase 13: Smart Features — Package C (v1.17.0) ✅ Complete

**Goal**: Give the plan a single, actionable to-do list. One unified **Tasks** dashboard tab that aggregates every auto-derived action — planting-calendar windows, succession sow/clear, soil amendments, frost protection — plus user-created manual tasks, with persistent done / snooze / dismiss state. See ADR-029 (pure generators + render-time status + dual-store coexistence) and FR-21.

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | C1    | Harvest tracking / yield log (#188) — per-plant/bed log + garden-wide dashboard — see FR-23 |
| ✅     | C2    | Task management & reminders — unified Tasks tab (#188) — see ADR-029 |

### Phase 13: Agent Integration — Package D (MCP Server) ✅ Complete

| Status | Package | Scope | Version / reference |
|--------|---------|-------|---------------------|
| ✅ | D1 | Read, query, render, export, resources and read-analysis prompts over the embedded loopback MCP server. | v1.22–v1.24; ADR-033/034; FR-AGENT-06…12 |
| ✅ | D2 | Token-gated writes: create, move, resize, rotate, species, beds, layers, history, geometry escape hatches. | v1.26–v1.27; ADR-036; FR-AGENT-14…22 |
| ✅ | D3 | Domain tools and prompts: companions, succession, calendar/tasks, soil amendments. | v1.28–v1.29.1; ADR-045; FR-AGENT-23…28 |

### Package F — Permaculture & Polyculture ✅ Complete

| Status | Story | Scope | Version / reference |
|--------|-------|-------|---------------------|
| ✅ | F1 | Permaculture layers and plant-function tags. | v1.30.0; ADR-054/055; FR-32 |
| ✅ | F2 | Plant guilds, templates and diagnostics. | v1.30.0; ADR-054/055 |
| ✅ | F3 | Sun requirement vs computed hours of sun. | v1.30.1; ADR-056 |
| ✅ | F4 | Plan timeline and shared date/sun controls. | v1.30.17; ADR-062 |
| ✅ | F5 | Offline examples and portable templates. | v1.33.0; ADR-066 |

### Package G — Plant Data Quality & Attribution ✅ Complete

| Status | Story | Scope | Version / reference |
|--------|-------|-------|---------------------|
| ✅ | G1 | Data licences and attribution. | v1.28.1 |
| ✅ | G2 | Plant profile header and external links. | v1.28.1 |
| ✅ | G3 | Permapeople companion data and cache. | v1.28.1 |
| ✅ | G4 | Plant favourites and named collections. | v1.29.7; PR #421 |

### Phase 14: 3D Visualization & Sun/Shade ✅ Complete (v1.24.5 – v1.24.12)

No v2.0 release: the phase shipped as patch releases and the major-version framing is retired.

| Status | Story | Scope | Reference |
|--------|-------|-------|-----------|
| ✅ | US-E1 | Solar position engine. | ADR-037; FR-SUN-01 |
| ✅ | US-E2 | Object height property and resolver. | ADR-037; FR-SUN-02 |
| ✅ | US-E3 | 2D analytic shadow overlay and sun controls. | ADR-037; FR-SUN-03/04 |
| ✅ | US-E4 | Hours-of-sun heatmap. | ADR-037; FR-SUN-05 |
| ✅ | US-E5 | 3D engine spike — GO on PyQt6-3D. | ADR-038 |
| ✅ | US-E6 | 3D view MVP. | ADR-038; FR-SUN-06 |
| ✅ | US-E7 | First-person walkthrough. | ADR-038; FR-SUN-07 |
| ✅ | US-E8 | Growth over time. | ADR-037; FR-SUN-08 |
| ✅ | US-E9 | Asset-forge dev tooling. | ADR-040; §8.22 |

### Phase 15: Visual Refresh ✅ Complete (v1.25.0 – v1.27.0)

| Status | Package | Scope | Reference |
|--------|---------|-------|-----------|
| ✅ | 1 | Themed iconography and modernized chrome. | ADR-039; FR-28 |
| ✅ | 2 | Plant illustration redesign (Lush Sprite). | ADR-040; FR-29 |
| ✅ | 3 | Object sprites, textures and iconography. | ADR-042; FR-30 |

## Phase 17: Living Garden 3D

Since L1, the 3D view is the Qt Quick 3D workspace in the main window — Plan / 3D / Split. It follows
every edit, casts shadow-map shadows checked against the 2D ones, selects in both directions
and walks with collision. Editing stays in 2D. L0 is complete with a GO; L1–L7 are complete.

| Status | Package | Scope | Reference |
|--------|---------|-------|-----------|
| ✅ | L0 | Proof of Beauty — GO on Qt Quick 3D. | ADR-048 |
| ✅ | L1 | New engine, workspace, sky, ground bake, default flip. | v1.30.14; ADR-059/060 |
| ✅ | L2 | Analyze in 3D — drapes, probe, sun path, cutaway. | v1.31.0; ADR-063 |
| ✅ | L3 | Plant Forge — procedural species models and LOD. | v1.32.0; ADR-064 |
| ✅ | L4 | Built world complete — roofs, paths, 24 object builders. | v1.34.0; ADR-065 |
| ✅ | L5 | Living garden — playback, weather look, particles, lights. | v1.35.0; ADR-070 |
| ✅ | L6 | Director's cut — photo mode, tours, video, render tool. | v1.37.0; ADR-072 |
| ✅ | L7 | Sky 6.12 — Qt 6.12 and optional atmosphere sky. | v1.36.0; ADR-048 addendum |

## Hardening and patch releases

| Version | PR | Scope |
|---------|----|-------|
| v1.29.5 | #419 | Task-date correctness and audit P1 cluster. |
| v1.29.6 | #422 | CI and release hardening. |
| v1.29.7 | #421 | Package G4 plant favourites and collections. |
| v1.29.8 | #426 | Handled-error logging and harvest offsets. |
| v1.29.9 | #430 | Canvas performance on the 500-object plan. |
| v1.30.0 | #433 | Package F1/F2. |
| v1.30.1 | #436 | Package F3 and heatmap lifecycle. |
| v1.30.2 | #477 | Constraint-tool characterization. |
| v1.30.3 | #487 | Audit package A1. |
| v1.30.4 | #489 | Audit package A5. |
| v1.30.5 | #490 | Audit package A2. |
| v1.30.6 | #497 | Translation completeness for every locale. |
| v1.30.7 | #498 | Worker lifecycle, cache bounds and test hygiene. |
| v1.30.8 | #501 | Canvas paint bound and appearance round-trip. |
| v1.30.10 | #507 | Low-zoom LOD flat fill removed. |
| v1.30.13 | #520 | CI gate integrity. |
| v1.30.14 | #484 | Phase 17 L1 — Qt Quick 3D workspace. |
| v1.30.16 | #545 | Line appearance and cache containment. |
| v1.30.17 | #533 | Package F4 plan timeline. |
| v1.30.18 | #556 | 2D canvas defect batch. |
| v1.30.19 | #565 | L1 follow-ups and Plan & Sun stepping. |
| v1.30.20 | #566 | Plant Details follow-ups. |
| v1.31.0 | #584 | Phase 17 L2 — Analyze in 3D. |
| v1.31.1 | #585 | Non-3D hardening. |
| v1.32.0 | #593 | Phase 17 L3 — Plant Forge. |
| v1.32.1 | #596 | Non-3D follow-up hardening, batch 2. |
| v1.33.0 | #610 | Package F5 examples and templates. |
| v1.34.0 | #613 | Phase 17 L4 — Built world complete. |
| v1.34.1 | #630 | L4 follow-up hardening. |
| v1.34.2 | #632 | Test lifecycle, popup focus and 3D workspace modularization. |
| v1.34.3 | #627 | 2D sun study, heights and plant stacking. |
| v1.34.4 | #639 | Agent move atomicity and 3D stability. |
| v1.34.5 | #640 | Remaining audit packages A4/A6/A7/A9/A12/A13. |
| v1.34.6 | #645 | Precision, UI and diagnostic bugfixes. |
| v1.34.7 | #647 | 3D visual and engine hardening. |
| v1.34.8 | #650 | Touch gestures, region pricing and render gates. |
| v1.34.9 | #649 | Bed membership and atomic constrained rotation. |
| v1.34.10 | #672 | CAD-precision integrity. |
| v1.34.11 | #676 | 3D performance and stability, Slice A. |
| v1.34.12 | #683 | Site-plan-sized background images. |
| v1.34.13 | #686 | Symbol and shadow correctness, Slice B. |
| v1.35.0 | #699 | Phase 17 L5 — Living garden. |
| v1.36.0 | #721 | Phase 17 L7 — Sky 6.12. |
| v1.36.1 | #495 | Russian localization. |
| v1.36.2 | #713 | 2D drawing-tools package. |
| v1.37.0 | #729 | Phase 17 L6 — Director's cut. |
| v1.37.1 | #747 | 2D drawing and CAD integrity follow-ups. |
| v1.37.2 | #750 | Capture-session integrity. |
| v1.37.3 | #752 | Geometry, weather resilience and lighting hygiene. |
| v1.37.4 | #755 | Sky and render-tier integrity. |
| v1.37.5 | #756 | Curved geometry, string lights and shadow cost. |
| v1.37.6 | #759 | Capture quality and L6 hygiene. |
| v1.37.7 | #762 | Engine, smart symbols and CAD hygiene. |
| v1.37.8 | #773 | UI, plant services, agent prompts and weather architecture. |

## Dev Infrastructure

Project-wide infrastructure that is independent of product user stories.

| Status | ID   | Description            | Notes |
|--------|------|------------------------|-------|
| ✅     | DI-1 | SAST pipeline (Bandit) | HIGH-severity scan in CI |
| ✅     | DI-2 | Repository audit 2026-10 | Findings reconciled; epic #392 closed; living debt register §11.3 |
| ✅     | DI-3 | i18n blind-spot hardening | Unique keys, shared `active_language()`, full-tree ruff; ADR-045 addendum |
| ✅     | DI-4 | Serialization & data integrity | Annotations, clipboard, placeholders/UUIDs, atomic loading; §11.3/§11.4 |
| ✅     | DI-5 | CI and release hardening | Locked deps, type budgets, coverage floors, protected checks; ADR-050 |
| ✅     | DI-6 | Wiki sources and community policies | Repository-owned sources and offline checks; ADR-051 |

## Roadmap conventions

Completed rows are one line. Current work carries acceptance criteria only while it is open.
Detailed delivery evidence lives in the GitHub release, the ADR/FR and the issue; do not add it here.
See `ogp-docs-and-writing` for the writing rule.
