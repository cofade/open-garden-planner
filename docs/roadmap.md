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
| Backlog | v0.5 | ✅ Complete | Rotation, vertex editing, annotations |
| 6 | v1.0 | ✅ Complete | Visual Polish & Public Release |
| 7 | v1.1 – v1.6 | ✅ Complete | CAD Precision & Constraints |
| 8 | v1.7 | ✅ Complete | Location, Climate & Planting Calendar |
| 9 | v1.8.4 – v1.8.6 | ✅ Complete | Seed Inventory & Propagation Planning |
| 10 | v1.8.6 – v1.8.12 | ✅ Complete | Companion Planting & Crop Rotation |
| 11 | v1.8.13+ | ✅ Complete | Bed Interior Design, Visual Polish & Advanced 2D Tools |
| 12 | v1.9.0 – v1.10.x | ✅ Complete | Weather & Smart Features |
| 13 | v1.11 – v1.29.1 | ✅ Complete (Packages A–D) | CAD Precision, Smart Features & Agent Integration |
| 14 | v1.24.5 – v1.24.12 | ✅ Complete (epic [#255](https://github.com/cofade/open-garden-planner/issues/255); no v2.0 bump) | 3D Visualization & Sun/Shade |
| 15 | v1.25.0 – v1.27.0 | ✅ Complete (Packages 1–3: [#279](https://github.com/cofade/open-garden-planner/issues/279)/[#281](https://github.com/cofade/open-garden-planner/issues/281)/[#284](https://github.com/cofade/open-garden-planner/issues/284)) | Visual Refresh |
| 16 | — | Future | Platform & Community |
| 17 | v1.29.10 – v1.37.0 | ✅ Complete (L0–L7; epic [#383](https://github.com/cofade/open-garden-planner/issues/383)) | Living Garden 3D |

## Current work

No roadmap phase is active. Open work is tracked in GitHub issues; the current themes are:

| Theme | Open issues | Why it matters |
|-------|-------------|----------------|
| Store/MSIX readiness | #767, #375 | Distribution and user-data safety on the second channel. |
| 3D rendering quality and performance | #744, #804, #1012, #1013 | The 3D view's trust and frame budget; #804 (a smooth year lapse) depends on #1013, the committed memory a regrowth still keeps after #531's Model reuse. |
| CAD and drawing tools | — | Precision and editing depth. |
| Documentation before advertising | #939 | The user-facing documents describe today's product before it is shared. |
| Plant Grid follow-ups | #1001, #1003, #1005, #1017 | Typed and snapped grid drafts, Qt-free grid geometry, one overlay owner, grouped-grid bed links, and the native-pixel settle. |
| Agent write frames | #1020 | An agent move of a bed/plant inside a group applies the scene delta in the group frame; found during the Plant Grid review. |
| Repaint oracle | #1004 | The Windows-only native-pixel partial-repaint check fails at 5fbc8620 and passes 4/4 on 0d2d8972; root cause still open. |
| 2D canvas follow-ups | #845, #852, #855 | First-zoom sprite rasterization cost; sun-map contour/label repaint overhead; open-frame weighted-path grazing-sun and food-forest performance. |

This table is a pointer, not a tracker. Each issue owns its scope and acceptance criteria.

### Post-Phase 17 packages

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | GPU memory and frame budget (#531, #534, #598, #667) | A regrown 3D part keeps its Model (in-place geometry reload) and only items that lost a Model count towards a cache release; the seasonal scrub sends one float64 buffer and touches only changed seasonal parts; the wind soak is an assertion again; the G7 soak keeps the product's random hash seed | v1.42.1; [PR #1016](https://github.com/cofade/open-garden-planner/pull/1016); ADR-069 addenda, ADR-064 addendum; §8.10.9, §8.29.11 |
| 🔄 | Plant Grid follow-ups (#1001, #1003, #1005, #1017) | Typed units-aware size/column-spacing/extent, snapped move/resize/rotate/size handles, a Qt-free grid-geometry module, one viewport-overlay placement owner, grouped-grid bed links in the same undo step, and a stable native-pixel settle | Draft PR; ADR-082 addendum; FR-PLANT-25; §8.9.21; PF-CAN-67/70 |
| ✅ | Plant Grid (#1002) | Toolbar tool that places a rectangular species grid with move, resize, rotate, one plant size and a species preview, committed in one undo step and optionally grouped; contributed by tanclin (Discussion #983) | v1.42.0; [PR #1000](https://github.com/cofade/open-garden-planner/pull/1000); ADR-082; FR-PLANT-25; §8.9.21 |
| ✅ | 3D showcase follow-ups (#941, #943, #944, #949, #954, #955, #956, #960, #966, #992) | Two-anchor autumn colours, year-round seasonal grass, a stored plan weather, domed rocks, moss and raked sand with per-stone cuts, a board fence, umbrella Scots pine and a long-hedge leaf budget, a dwarf palm, a pergola climber, part-turn orbits and Ultra window reflections | v1.41.3; [PR #998](https://github.com/cofade/open-garden-planner/pull/998); ADR-059 addendum, ADR-064 addendum 2, ADR-070/072 addenda; FR-3D-PLANT-05–08, FR-3D-GROUND-09, FR-3D-BUILT-10–13, FR-3D-LOOK-09, FR-3D-LIVE-10, FR-3D-TOUR-05 |
| ✅ | Plant seasonal truth & forge stability (#948, #963, #969, #970, #973, #995, #996) | Green canopy tip weight, post-fit LOD2 spread pin, bulb leaf windows and scapes, 2 % size-bucketed forge cache with exact scaling, ripening phases, far crop patches, synchronous regrowth meshes without v0 downgrade, and smooth playback guards | v1.41.2; [PR #994](https://github.com/cofade/open-garden-planner/pull/994); ADR-064 addendum; FR-3D-FORGE-01/02/03/05/06/07, FR-3D-LIVE-01; §8.29.11; PF-L3D-37/38 |
| ✅ | 3D materials, lighting & built-world polish (#883, #884, #887, #894, #953, #957, #958, #959, #961, #965) | Ultra SSR roughness floor and translucent water reflections, per-surface linear albedo scaling, slate shingle / masonry / SSAO polish, resting live shadow fit, cool sky-tinted night fill, raised-bed fill materials, rounded flush natural pond shores, flat-roof modern bungalow, matte pebbles/compost, clean 3D ground borders, startup toolbar reflow and updated modern/wildlife examples | v1.41.1; [PR #990](https://github.com/cofade/open-garden-planner/pull/990); ADR-059 addendum; FR-3D-BUILT-02–04, FR-3D-LOOK-01/03/06 |
| ✅ | Backlog package: locale docs, tabbed Preferences, per-quantity units and 2D truth (#987, #986, #907, #876, #764; partial #852, #855, #667) | Five-locale docs gate, five-tab scrollable Preferences, per-quantity unit profile with provisional Canada (mixed) preset, smooth hours-of-sun map fill with 1.3× label clearance and theme-contrasting mismatch badge, trimmed open-frame shade reach, detection-only Claude Desktop proof, and soak seed plumbing | v1.41.0; [PR #989](https://github.com/cofade/open-garden-planner/pull/989); ADR-081, ADR-059 addendum; FR-MEAS-08–10, FR-SUN-13, FR-SUN-15, FR-UI-PREF-01 |
| ✅ | French locale and reference points (#553, #666) | French application and installer, plus named reference points for snapping and measurement | v1.40.13; [PR #985](https://github.com/cofade/open-garden-planner/pull/985); ADR-080; FR-I18N-13, FR-REF-01–06 |
| ✅ | Plant catalogue and export resolution (#850, #931, #942, #964, #967, #968) | Pictures written at the page's own resolution instead of the canvas's raster level, per-round performance evidence, a green Norway maple, a May-flowering rhododendron, bamboo genus matching, and bloom hardiness read from the species record | v1.40.12; [PR #980](https://github.com/cofade/open-garden-planner/pull/980); ADR-014 addendum, ADR-061 addendum; FR-EXP-02; PF-CAN-68 |
| ✅ | Plan truth, CAD precision and documentation (#828, #829, #945, #875, #976) | Plan time zone and Today reset, selection-scoped split with raised-bed frames, CAD Esc follow-ups, xdist crash evidence, and current product documentation | v1.40.11; [PR #981](https://github.com/cofade/open-garden-planner/pull/981); ADR-053 addendum, ADR-075 addenda 4 and 5, ADR-079; FR-SPLIT-01/02, FR-SUN-04, FR-TOOL-ESC-01; PF-DOM-35 |
| ✅ | Plant gallery and 2D plan reliability (#951, #950, #946, #862, #879, #861, #866, #880) | Plant browsing, roof styles, repaint coverage, live theme and example plans | v1.40.10; [PR #978](https://github.com/cofade/open-garden-planner/pull/978); ADR-037, ADR-076; §8.4 |
| ✅ | 2D canvas, sun overlay & export fixes (#846, #847, #849, #851, #854, #873, #919, #928) | BSP-indexed labels, bounded selected dense polylines & text notes, sun-shadow outline compensation & scrub deferral, 300-dpi/SVG contour pens, anti-moire zoom fills | v1.40.8; [PR #936](https://github.com/cofade/open-garden-planner/pull/936); §8.37; PF-CAN-64–66 |
| ✅ | 3D render verification (#885, #886, #892, #893) | Flat shadow samples, unobstructed sunset samples, per-phase board watchdogs and explicit foliage driver teardown | v1.40.7; [PR #937](https://github.com/cofade/open-garden-planner/pull/937); §8.10.8 |
| ✅ | Canvas editing precision (#840, #841, #843, #844, #853, #867, #872, #874) | Geometric anchors, screen-sized handles, contained labels/tags, fixed plan text size and a clear balcony note | v1.40.6; [PR #934](https://github.com/cofade/open-garden-planner/pull/934); ADR-076 editing addendum |
| ✅ | Recovery and test reliability (#797, #897, #916, #921, #922, #923) | Complete autosaves, bounded selection notifications, portable CPU raster tests, a cheaper full translation gate, and measured Qt guidance | v1.40.5; [PR #932](https://github.com/cofade/open-garden-planner/pull/932); ADR-003 addendum; §8.10.18; PF-CAN-40 |
| ✅ | Canvas repaint package (#848, #877, #878, #927; partial #847) | Canvas repaint caches and unmeasured sun diagnostics | v1.40.4; [PR #926](https://github.com/cofade/open-garden-planner/pull/926); §8.27, §8.37, ADR-076 addendum |
| ✅ | Package #768–#776 | Parametric glasshouse and pergola, Smart Symbols retirement, sprite orientation, layers-panel fixes | v1.37.9; [PR #779](https://github.com/cofade/open-garden-planner/pull/779); ADR-032 addendum; FR-3D-BUILT-01a–01c |
| ✅ | Package #681/#664/#771 | Monthly dependency refresh, scene-wide split along a line, group drill-down | v1.37.10; [PR #783](https://github.com/cofade/open-garden-planner/pull/783); ADR-075; FR-35 |
| ✅ | Package 2D visual polish (#698, #782, #784–#796, #836) | Sharp sprites and fills, a cheap repaint with the sun overlay, quiet spacing warnings, legible labels, true exports, theme and locale fixes, examples in a showcase state, a key for the hours-of-sun map | v1.38.0; [PR #838](https://github.com/cofade/open-garden-planner/pull/838); ADR-076, ADR-077; §8.36, §8.37 |
| ✅ | Package 3D visual polish (#687, #716, #719, #734, #737, #743, #798–#803, #805, #807) | Grass on the meadow, built parts that look like their material, tiled roofs, sharp low-sun shadows in stills, a clean horizon, a steady day lapse with a twilight fill, wind that shows, publishable tour video with an eased orbit, tours kept in the plan | v1.39.0; [PR #882](https://github.com/cofade/open-garden-planner/pull/882); ADR-059 and ADR-072 addenda |
| ✅ | Example plans and repository showcase (#940, #564) | Thirteen bundled examples, each on its own day with a hint layer and a stored camera tour; five species; flowers before the last frost; a 3D flower meadow; a README with a download button and pictures taken from the shipped plans | v1.40.9; [PR #975](https://github.com/cofade/open-garden-planner/pull/975); ADR-066 addendum; FR-EXAMPLE-01–14; follow-ups #941–#950, #953–#974 |
| ✅ | Package plan truth & reports (#663, #856–#860, #863–#865, #868–#871, #899) | Plan north, the plan date on every date-driven surface, one identity for an opened example, task row text, status-bar room, locale numbers, harvest units, PDF legend/plant-list, print grid/order and the shopping-list paginator | v1.39.1; [PR #903](https://github.com/cofade/open-garden-planner/pull/903); ADR-037/066/076/077 addenda; ADR-062; FR-SUN-14, FR-EXAMPLE-11, FR-TASK-01/04; §8.20, §8.31, §8.33, §8.36 |
| ✅ | Measurement units (#673) | Metric / Imperial (US) display and input | v1.40.0; [PR #908](https://github.com/cofade/open-garden-planner/pull/908); ADR-078; FR-MEAS-07 |
| ✅ | Small follow-ups (#904, #909, #842, #905, #881) | Annotation cancellation, bed rotation borders, plant-header layout and frozen-inventory guard | v1.40.1; [PR #913](https://github.com/cofade/open-garden-planner/pull/913); ADR-004 addendum |
| ✅ | Tour and video reliability (#889, #890, #891, #896) | Bounded MP4 tables, safe delivery and shutdown reporting, saved-orbit validation, tour locale coverage | v1.40.2; [PR #915](https://github.com/cofade/open-garden-planner/pull/915); ADR-072 addendum; FR-3D-TOUR-02/04 |

### Phase 16: Platform & Community (future)

- Plugin system for extensibility
- Community template sharing / marketplace
- Irrigation planning and drip-system design
- Cost estimation and advanced budget tracking
- Cross-platform packaging (macOS, Linux)

## Delivery index

All phases 1–15 and 17 are complete; Phase 16 is future. Patch-release detail lives
in GitHub releases; this index keeps one row per story or package with its durable
reference. Phase 17 has its own top-level section because the wiki includes it.

### Phase 1: Foundation (v0.1) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-1.1 | Create new project with specified dimensions | v0.1 |
| ✅ | US-1.2 | Pan and zoom the canvas smoothly | v0.1 |
| ✅ | US-1.3 | Draw rectangles and polygons on the canvas | v0.1 |
| ✅ | US-1.4 | Select, move, and delete objects | v0.1 |
| ✅ | US-1.5 | Save project to file and reopen it | v0.1 |
| ✅ | US-1.6 | Undo and redo actions | v0.1 |
| ✅ | US-1.7 | See cursor coordinates in real-time | v0.1 |
| ✅ | US-1.8 | Application displays OGP logo icon | v0.1 |
| ✅ | US-1.9 | GitHub repository displays banner image | v0.1 |

### Phase 2: Precision & Calibration (v0.2) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-2.1 | Import a background image (satellite photo) | v0.2 |
| ✅ | US-2.2 | Calibrate the image by marking a known distance | v0.2 |
| ✅ | US-2.3 | Toggle a grid overlay | v0.2 |
| ✅ | US-2.4 | Snap objects to the grid | v0.2 |
| ✅ | US-2.5 | Measure distances between any two points | v0.2 |
| ✅ | US-2.6 | See area/perimeter of selected polygons and circles | v0.2 |
| ✅ | US-2.7 | Adjust background image opacity | v0.2 |
| ✅ | US-2.8 | Lock the background image to prevent moving it | v0.2 |
| ✅ | US-2.9 | Draw circles by clicking center then a rim point | v0.2 |

### Phase 3: Objects & Styling (v0.3) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-3.1 | Add property objects (house, fence, path, etc.) | v0.3 |
| ✅ | US-3.2 | Set fill color for objects | v0.3 |
| ✅ | US-3.3 | Apply textures/patterns to objects | v0.3 |
| ✅ | US-3.4 | Set stroke style (color, width, dash pattern) | v0.3 |
| ✅ | US-3.5 | Add labels to objects displayed on canvas | v0.3 |
| ✅ | US-3.6 | Organize objects into layers | v0.3 |
| ✅ | US-3.7 | Show/hide and lock layers | v0.3 |
| ✅ | US-3.8 | Copy and paste objects | v0.3 |

### Phase 4: Plants & Metadata (v0.4) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-4.1 | Add plant objects (tree, shrub, perennial) | v0.4 |
| ✅ | US-4.2 | Set plant metadata (species, variety, dates) | v0.4 |
| ✅ | US-4.3 | Search for plant species from online database | v0.4 |
| ✅ | US-4.4 | Create custom plant species in library | v0.4 |
| ✅ | US-4.5 | View plant details in properties panel | v0.4 |
| ✅ | US-4.6 | Add garden beds with area calculation | v0.4 |
| ✅ | US-4.7 | Filter/search plants in project | v0.4 |
| ✅ | US-4.8 | Organized sidebar with icon-based tool panels | v0.4 |
| ✅ | US-4.9 | Resize objects by dragging handles | v0.4 |

### Phase 5: Export & Polish (v0.5) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-5.1 | Export plan as PNG in various resolutions | v0.5 |
| ✅ | US-5.2 | Export plan as SVG | v0.5 |
| ✅ | US-5.3 | Export plant list as CSV | v0.5 |
| ✅ | US-5.4 | Keyboard shortcuts for all common actions | v0.5 |
| ✅ | US-5.5 | Light and dark mode switch | v0.5 |
| ✅ | US-5.6 | Welcome screen with recent projects | v0.5 |
| ✅ | US-5.7 | Auto-save periodically | v0.5 |
| ✅ | US-5.8 | Professional SVG icons for all drawing tools | v0.5 |

### Backlog: Core Editing Enhancements ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-B.1 | Rotate objects (free + 15 degree snap) | v0.5 |
| ✅ | US-B.2 | Edit polygon vertices (move, add, remove) | v0.5 |
| ✅ | US-B.3 | Vertex coordinate annotations on selection | v0.5 |

### Phase 6: Visual Polish & Public Release (v1.0) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-6.1 | Rich tileable textures for all materials | v1.0 |
| ✅ | US-6.2 | Illustrated SVG plant rendering (hybrid approach) | v1.0 |
| ✅ | US-6.3 | Drop shadows on all objects (toggleable) | v1.0 |
| ✅ | US-6.4 | Visual scale bar on canvas | v1.0 |
| ✅ | US-6.5 | Visual thumbnail gallery sidebar | v1.0 |
| ✅ | US-6.6 | Toggleable object labels on canvas | v1.0 |
| ✅ | US-6.7 | Branded green theme (light/dark variants) | v1.0 |
| ✅ | US-6.8 | Outdoor furniture objects | v1.0 |
| ✅ | US-6.9 | Garden infrastructure objects | v1.0 |
| ✅ | US-6.10 | Object snapping & alignment tools | v1.0 |
| ✅ | US-6.11 | Fullscreen preview mode (F11) | v1.0 |
| ✅ | US-6.12 | Internationalization (EN + DE, Qt Linguist) | v1.0 |
| ✅ | US-6.13 | Print support with scaling | v1.0 |
| ✅ | US-6.14 | Windows installer (NSIS) + .ogp file association | v1.0 |
| ✅ | US-6.15 | Path & fence style presets | v1.0 |

### Phase 7: CAD Precision & Constraints (v1.1 – v1.6) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-7.1 | Measure tool snap to object anchors (centers + edges) | v1.1 – v1.6 |
| ✅ | US-7.2 | Distance constraint data model & solver | v1.1 – v1.6 |
| ✅ | US-7.3 | Distance constraint tool (dedicated toolbar tool) | v1.1 – v1.6 |
| ✅ | US-7.4 | Dimension line visualization (FreeCAD-style, toggleable) | v1.1 – v1.6 |
| ✅ | US-7.5 | Constraint solver drag integration (chain propagation) | v1.1 – v1.6 |
| ✅ | US-7.6 | Constraints manager panel | v1.1 – v1.6 |
| ✅ | US-7.7 | Numeric position input (editable X, Y in properties) | v1.1 – v1.6 |
| ✅ | US-7.8 | Numeric dimension input (editable width/height/radius) | v1.1 – v1.6 |
| ✅ | US-7.9 | Horizontal/Vertical alignment constraints | v1.1 – v1.6 |
| ✅ | US-7.10 | Angle constraints | v1.1 – v1.6 |
| ✅ | US-7.11 | Symmetry constraints | v1.1 – v1.6 |
| ✅ | US-7.12 | Construction geometry (helper lines, not in exports) | v1.1 – v1.6 |
| ✅ | US-7.13 | Draggable guide lines | v1.1 – v1.6 |
| ✅ | US-7.14 | Linear array placement | v1.1 – v1.6 |
| ✅ | US-7.15 | Grid array placement | v1.1 – v1.6 |
| ✅ | US-7.16 | Circular array placement | v1.1 – v1.6 |
| ✅ | US-7.17 | Coincident constraint (merge two anchor points) | v1.1 – v1.6 |
| ✅ | US-7.18 | Parallel constraint (two edges stay parallel) | v1.1 – v1.6 |
| ✅ | US-7.19 | Perpendicular constraint (two edges at 90°) | v1.1 – v1.6 |
| ✅ | US-7.20 | Equal size constraint (same radius/width/height) | v1.1 – v1.6 |
| ✅ | US-7.21 | Fix in place / Block constraint (pin object permanently) | v1.1 – v1.6 |
| ✅ | US-7.22 | Horizontal/Vertical distance constraints (1D dimensional) | v1.1 – v1.6 |
| ✅ | **US-7.23** | **FreeCAD-style constraint toolbar with full icon set** | v1.1 – v1.6 |

### Phase 8: Location, Climate & Planting Calendar (v1.7) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-8.1 | GPS location & climate zone setup | v1.7 |
| ✅ | US-8.2 | Frost date & hardiness zone API lookup | v1.7 |
| ✅ | US-8.3 | Auto-update notification & one-click installer download | v1.7 |
| ✅ | US-8.4 | Plant calendar data model | v1.7 |
| ✅ | US-8.5 | Planting calendar view (tab) | v1.7 |
| ✅ | US-8.6 | Dashboard / today view | v1.7 |
| ✅ | US-8.7 | Tab-based main window architecture | v1.7 |

### Phase 9: Seed Inventory & Propagation Planning (v1.8) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-9.1 | Seed packet data model | v1.8.4 |
| ✅ | US-9.2 | Seed viability database | v1.8.4 |
| ✅ | US-9.3 | Seed inventory management panel | v1.8.4 |
| ✅ | US-9.4 | Seed inventory tab view | v1.8.4 |
| ✅ | US-9.5 | Propagation planning (pre-cultivation) | v1.8.5 |
| ✅ | US-9.6 | Seed-to-plant manual linking | v1.8.6 |

### Phase 10: Companion Planting & Crop Rotation (v1.8.6 – v1.8.12) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-10.1 | Companion planting database | v1.8.6 |
| ✅ | US-10.2 | Companion planting visual warnings | v1.8.7 |
| ✅ | US-10.3 | Companion planting recommendation panel | v1.8.8 |
| ✅ | US-10.4 | Whole-plan compatibility check | v1.8.9 |
| ✅ | US-10.5 | Crop rotation data model | v1.8.11 |
| ✅ | US-10.6 | Crop rotation recommendations | v1.8.11 |
| ✅ | US-10.7 | Season management & plan duplication | v1.8.12 |

### Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools (v1.8.x) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-11.1 | Plant-Bed Parent-Child Relationship | v1.8.x |
| ✅ | US-11.2 | Plant Spacing Circles & Overlap Warnings | v1.8.x |
| ✅ | US-11.3 | Square-Foot Grid Overlay | v1.8.x |
| ✅ | US-11.5 | Expanded Fill Pattern Library | v1.8.x |
| ✅ | US-11.6 | Plant Illustration Expansion & Style Refresh | v1.8.x |
| ✅ | US-11.7 | Minimap / Overview Panel | v1.8.x |
| ✅ | US-11.8 | Free Text Annotation Tool | v1.8.x |
| ✅ | US-11.9 | Auto Area Labels | v1.8.x |
| ✅ | US-11.10 | Callout / Leader Line Annotations | v1.8.x |
| ✅ | US-11.11 | Group / Ungroup | v1.8.x |
| ✅ | US-11.12 | Boolean Shape Operations | v1.8.x |
| ✅ | US-11.13 | Array Along Path | v1.8.x |
| ✅ | US-11.14 | Ellipse Drawing Tool | v1.8.x |
| ✅ | US-11.15 | Offset Tool | v1.8.x |
| ✅ | US-11.16 | Trim / Extend Tool | v1.8.x |
| ✅ | US-11.24 | Find & Replace Objects | v1.8.x |

### Phase 12: Weather & Smart Features (v1.9.0 – v1.10.x) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | US-12.1 | Weather forecast widget in Dashboard | v1.9.0 – v1.10.x |
| ✅ | US-12.2 | Frost alert & plant-aware warnings | v1.9.0 – v1.10.x |
| ✅ | US-12.3 | DXF export | v1.9.0 – v1.10.x |
| ✅ | US-12.4 | DXF import | v1.9.0 – v1.10.x |
| ✅ | US-12.5 | Multi-page PDF export | v1.9.0 – v1.10.x |
| ✅ | US-12.6 | Shopping list generation | v1.9.0 – v1.10.x |
| ✅ | US-12.7 | Pest & disease log | v1.9.0 – v1.10.x |
| ✅ | US-12.8 | Succession planting | v1.9.0 – v1.10.x |
| ✅ | US-12.9 | Garden journal (map-linked notes) | v1.9.0 – v1.10.x |
| ✅ | US-12.10 | Soil health tracking & amendment calculator | v1.9.0 – v1.10.x |
| ✅ | US-12.11 | Smart amendment composition + library toggle | v1.9.0 – v1.10.x |

### Phase 13: CAD Precision Boost — Package A (v1.11.0) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | A1 | Relative coordinate input `@dx,dy` (status bar + cursor overlay) | v1.11.0 |
| ✅ | A2 | Polar coordinate input `@dist<angle` | v1.11.0 |
| ✅ | A3 | Midpoint + intersection snap modes, View-menu toggles | v1.11.0 |
| ✅ | A4 | Dynamic Input cursor-anchored overlay | v1.11.0 |

### Phase 13: CAD Precision Boost — Package B (v1.12.0) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | B1 | Cubic Bezier pen tool (drawing only; placed-curve editing → US-B9) | v1.12.0 |
| ✅ | B2 | 3-point Arc tool (collinear → polyline fallback) | v1.12.0 |
| ✅ | B3 | Fillet (`Shift+F`) + Chamfer (`Shift+C`) corner editors | v1.12.0 |
| ✅ | B4 | Nearest-point fallback snap | v1.12.0 |
| ✅ | B5 | Perpendicular snap from active tool's `last_point` | v1.12.0 |
| ✅ | B6 | Tangent snap onto circles + arcs from `last_point` | v1.12.0 |
| ⛔ | B7 | Paper Space MVP — dropped; see FR-20.4 and the ADR-022 note | — (dropped) |

### Phase 13: Smart Features — Package C (v1.17.0) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | C1 | Harvest tracking / yield log (#188) — per-plant/bed log + garden-wide dashboard — see FR-23 | v1.17.0 |
| ✅ | C2 | Task management & reminders — unified Tasks tab (#188) — see ADR-029 | v1.17.0 |

### Phase 13: Agent Integration — Package D (MCP Server) ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | D1 | Read, query, render, export, resources and read-analysis prompts over the embedded loopback MCP server. | v1.22–v1.24; ADR-033/034; FR-AGENT-06…12 |
| ✅ | D2 | Token-gated writes: create, move, resize, rotate, species, beds, layers, history, geometry escape hatches. | v1.26–v1.27; ADR-036; FR-AGENT-14…22 |
| ✅ | D3 | Domain tools and prompts: companions, succession, calendar/tasks, soil amendments. | v1.28–v1.29.1; ADR-045; FR-AGENT-23…28 |

### Package F — Permaculture & Polyculture ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | F1 | Permaculture layers and plant-function tags. | v1.30.0; ADR-054/055; FR-32 |
| ✅ | F2 | Plant guilds, templates and diagnostics. | v1.30.0; ADR-054/055 |
| ✅ | F3 | Sun requirement vs computed hours of sun. | v1.30.1; ADR-056 |
| ✅ | F4 | Plan timeline and shared date/sun controls. | v1.30.17; ADR-062 |
| ✅ | F5 | Offline examples and portable templates. | v1.33.0; ADR-066 |

### Package G — Plant Data Quality & Attribution ✅ Complete

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | G1 | Data licences and attribution. | v1.28.1 |
| ✅ | G2 | Plant profile header and external links. | v1.28.1 |
| ✅ | G3 | Permapeople companion data and cache. | v1.28.1 |
| ✅ | G4 | Plant favourites and named collections. | v1.29.7; PR #421 |

### Phase 14: 3D Visualization & Sun/Shade ✅ Complete (v1.24.5 – v1.24.12)

No v2.0 release: the phase shipped as patch releases and the major-version framing is retired.

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
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

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | 1 | Themed iconography and modernized chrome. | ADR-039; FR-28 |
| ✅ | 2 | Plant illustration redesign (Lush Sprite). | ADR-040; FR-29 |
| ✅ | 3 | Object sprites, textures and iconography. | ADR-042; FR-30 |

## Phase 17: Living Garden 3D (✅ L0–L7 complete)

Since L1, the 3D view is the Qt Quick 3D workspace in the main window (Plan / 3D / Split); L0 is complete with a GO, and L1–L7 are complete.

| Status | ID | Scope | Version / reference |
|--------|----|-------|---------------------|
| ✅ | L0 | Proof of Beauty — GO on Qt Quick 3D. | ADR-048 |
| ✅ | L1 | New engine, workspace, sky, ground bake, default flip. | v1.30.14; ADR-059/060 |
| ✅ | L2 | Analyze in 3D — drapes, probe, sun path, cutaway. | v1.31.0; ADR-063 |
| ✅ | L3 | Plant Forge — procedural species models and LOD. | v1.32.0; ADR-064 |
| ✅ | L4 | Built world complete — roofs, paths, 24 object builders. | v1.34.0; ADR-065 |
| ✅ | L5 | Living garden — playback, weather look, particles, lights. | v1.35.0; ADR-070 |
| ✅ | L6 | Director's cut — photo mode, tours, video, render tool. | v1.37.0; ADR-072 |
| ✅ | L7 | Sky 6.12 — Qt 6.12 and optional atmosphere sky. | v1.36.0; ADR-048 addendum |

## Dev Infrastructure

Project-wide infrastructure that is independent of product user stories.

| Status | ID | Scope | Notes |
|--------|----|-------|-------|
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
