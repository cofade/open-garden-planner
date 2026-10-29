# Development Roadmap

## Overview

**Download-report follow-up to #634 (ADR-067): owner-accepted on 28 October 2026 ("perfect").**
The tooling-only chart adds frozen, explicitly estimated pre-observation history and
daily installer bars with sum-preserving week/month/year grouping, independent time
ranges, UTC boundaries, an SVG preview and a localized accessible Pages viewer.
No application release is required. Pages publication follows protected merge and the
one-time setup in deployment section 7.4; FR-STATS records acceptance requirements.

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
| 17 | — | In progress (L0 ✅ **GO** — ADR-048, 2026-10-05; L1 ✅ v1.29.10 + v1.30.14, L2 ✅ v1.31.0, L3 ✅ v1.32.0, L4 ✅ v1.34.0; epic [#383](https://github.com/cofade/open-garden-planner/issues/383)) | Living Garden 3D |

---

## CI and release hardening package (#404, #401, #402, #399)

**Complete, 2026-10-09; released as v1.29.6 via [PR #422](https://github.com/cofade/open-garden-planner/pull/422).** No application behavior change.
Native uv dependency lock and checked PEP 751 export; clean locked Linux/Windows Python 3.11
per-file type allowances; measured package line floors and branch reporting; reviewed
administrator-enforced required checks and normal merges. `Coverage` became a required check
in #514 (ADR-058 addendum); the protection payload and read-only verifier carry it. Live
master enforcement was activated and read back before the normal approved merge.
Temporary-branch enforcement passed in PR #420
(failing head refused; corrected green head merged normally; temporary branches removed).

Final local validation: Windows 7,657 passed / 21 skipped; Linux 7,642 passed / 36 skipped.
Coverage: 39,883/52,841 lines (75.5%) and 9,099/15,490 branches (58.7%); non-UI 79.5% /
67.3%. Both type gates pass at 1,966 errors (Linux 137 files, Windows 136). Locked Windows
PyInstaller build, eight-second startup and subsystem self-test passed. The frozen build
opened the benchmark plan and exported validated PDF, DXF and CSV files. Owner testing
confirmed the frozen build and existing 3D behavior. The protected normal merge and matching
CI release succeeded. One Windows run reported an existing Agent API port-8765 collision
warning; all tests passed. All nine checks passed on the approved head in both push and PR
workflows. CI reports and release artifacts are recorded in the implementing PR and release.

Finalization preserves one invocation: approved feature merge, matching successful CI release,
automatic independently reviewed version-sync chore PR, wiki push and cleanup. No second
manual-test confirmation is required for that mechanical PR. See ADR-050 and deployment docs.

| Issue | Delivery scope | Status |
|---|---|---|
| #404 | Seeded universal lock, packaging/backend group, shared environment setup | Completed in v1.29.6, PR #422 |
| #401 | Locked strict mypy with Linux/Windows per-file allowances and corrected gate docs | Completed in v1.29.6, PR #422 |
| #402 | Fresh Linux package line floors, separate branch report, explicit package inventory | Completed in v1.29.6, PR #422 |
| #399 | Reviewed protection payload and protected/resumable finalization | Completed in v1.29.6; master enforcement verified before merge |

## Development Standards

> These rules apply to every contribution — AI-assisted or human.

### Integration tests are mandatory

**Every User Story must ship with at least one end-to-end integration test.** No PR merges without it.

- Tests live in `tests/integration/test_<feature>.py`
- They exercise the full UI workflow: tool activate → mouse gesture → scene state assertion
- Shared fixtures and coordinate system notes: `tests/integration/conftest.py`
- Full policy and pattern reference: `docs/08-crosscutting-concepts/` section 8.10

### Workflow per US

1. Implement feature with type hints
2. Write unit/widget tests (`tests/unit/`, `tests/ui/`)
3. **Write integration test** (`tests/integration/`) — mandatory
4. Run `pytest tests/ -v`, `ruff check src/`, and `bandit -r src/ --severity-level high` — must all be green
5. Build exe, wait for manual user approval
6. Commit, push, PR, merge

### Translation (i18n)

**Complete, 2026-10-16; released as [v1.30.6](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.6)
via [PR #497](https://github.com/cofade/open-garden-planner/pull/497), closing #496 after owner acceptance.**
Source-derived completeness covers every registered language in both directions:
adding a locale requires all current keys, and adding a wrapped UI string requires
every target translation. The required Test check validates exact context/source/comment
keys, completed values, placeholders, compiled bytes and actual Qt lookups. English/German
each cover 2,631 live keys. Helper/table mutation tests pin extraction; unsupported
forwarding and plural input fail explicitly. Shared companion fallback and shopping-list/
offset translation contexts are corrected. Russian registration and wording stay in #495;
its contributor must merge latest master and pass the shared gate before finalization.

Final evidence: 85 focused tests passed; full Windows suite 8,453 passed / 39 skipped;
Linux coverage suite 8,452 passed / 40 skipped, 80.0% lines / 63.7% branches with no floor
regressions. Independent senior review, all CI checks, frozen startup/self-test and 5,262
packaged translation lookups passed. Owner confirmed the frozen app works correctly.
The published release and successful provenance workflow match merge `aeb9e79b`.

#### Docs updated on completion (#496)

| Document | Updated contract |
|---|---|
| `docs/TRANSLATING.md`, `CONTRIBUTING.md`, PR template | All-locale maintenance workflow |
| `docs/05-building-block-view/`, `docs/07-deployment-view/` | Extraction tooling and required CI enforcement |
| `docs/08-crosscutting-concepts/` | Sections 8.3 and 8.10: inventory and validation |
| `docs/09-architecture-decisions/` | ADR-008 addendum: source authority and compiler boundary |
| `docs/10-quality-requirements/`, `docs/functional-requirements.md` | NFR-MAINT-05 and FR-I18N-07 |
| `docs/11-risks-and-technical-debt/` | Section 11.4: extraction blind spots and runtime contexts |
| Root agent guidance and paired skills | Current commands, gates and regression lessons |
| `docs/wiki/` | Contribution workflow and shipped status; publication follows protected merge |

Every user-visible string must be wrapped for translation. See `docs/08-crosscutting-concepts/` section 8.3.

### Spanish Translation (i18n) & Contributor Guide

**Implemented 2026-10-18 (US-I18N-ES).**
Adds full Spanish localization (`es`, "Español") matching the completeness of English and German:
- 100% key coverage: all 2,631 live source keys across 155 contexts translated with zero missing and zero unfinished keys.
- Menu mnemonics (`&`): zero accelerator collisions across Spanish menubar and all nested submenus (`test_menu_mnemonics_are_unique_per_language`).
- Packaging: NSIS installer updated with `!insertmacro MUI_LANGUAGE "Spanish"`.
- Strict gate verification: passes `scripts/check_translations.py` and `tests/integration/test_translation_gate.py` across English, German, and Spanish.
- Contributor guide: added a dedicated chapter in `CONTRIBUTING.md` ("Contributing translations and adding languages") documenting step-by-step instructions for contributors to update existing translations or add new languages.

**i18n blind-spot fixes (2026-10-04).** Three defects invisible to `test_german_ts_has_no_unfinished` are fixed together: **#393** (five duplicate `TRANSLATIONS` keys shadowed 62 strings; the five `PdfReportService` journal-notes strings never reached `de.ts`, so the German PDF printed English), **#408** (generated soil-amendment task titles stayed English; the task **id** keeps the English data name so saved done/snooze status survives a language switch), and **#410** (the agent `suggest_companions` `name` now follows the UI language, matching the Companion panel). The CI lint step is widened to `ruff check src/ tests/ scripts/`, and `tests/unit/test_i18n.py::TestTranslationRegistry` pins `TRANSLATIONS` key uniqueness with an `ast` parse. See §11.4, §8.19, and the ADR-045 addendum.

---

## Dev Infrastructure

> Infrastructure improvements that apply project-wide, independent of product user stories.
> These are tracked here rather than as numbered product US entries.

| Status | ID   | Description            | Notes                                                         |
|--------|------|------------------------|---------------------------------------------------------------|
| ✅     | DI-1 | SAST pipeline (Bandit) | HIGH-severity scan in CI; `bandit>=1.7.0` added as dev dep   |
| 🔄     | DI-2 | Repository audit 2026-10 | Historical snapshot preserved; [current reconciliation and packages A1–A13](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/audit-2026-10-reconciliation.md) account for 73 P2/P3 findings; all 15 original standalone P0/P1 remediations are complete after #406 in v1.30.2 (PR #477); **A1 (#453), A2 (#454) and A5 (#457) shipped in PRs #487, #490 and #489** — see the delivery-state sections in the reconciliation; epic #392 remains open |
| ✅     | DI-3 | i18n blind-spot hardening | Unique `TRANSLATIONS` keys + shared `active_language()` + full-tree ruff; issues #393/#408/#410; v1.29.2 (PR #411); §11.4, ADR-045 addendum |
| ✅     | DI-4 | Serialization & Data Integrity Hardening | Free-text annotations (`TextItem`) in `.ogp` + roundtrip matrix tests (#394), clipboard serializer unification (#400), background image placeholder & UUID deduplication (#397), atomic two-phase plan loading & autosave safety (#403); v1.29.4 (PR #412); §11.3, §11.4 |
| ✅     | DI-5 | CI and release hardening | Locked dependencies, platform type budgets, package coverage floors, and administrator-enforced checks; issues #404/#401/#402/#399; v1.29.6 (PR #422); ADR-050 |
| ✅     | DI-6 | Wiki sources and community policies | Repository-owned wiki sources, offline rendering/checks, and community policies; ADR-051; manual publication is tracked in issue #417 |

---

## ~~Phase 1: Foundation (v0.1)~~ ✅

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

---

## ~~Phase 2: Precision & Calibration (v0.2)~~ ✅

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

---

## ~~Phase 3: Objects & Styling (v0.3)~~ ✅

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

---

## ~~Phase 4: Plants & Metadata (v0.4)~~ ✅

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

**Remaining technical milestones**:
- [ ] Local SQLite cache for plant data

---

## ~~Phase 5: Export & Polish (v0.5)~~ ✅

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

---

## ~~Backlog: Core Editing Enhancements~~ ✅

| ID | User Story | Status |
|----|------------|--------|
| ~~US-B.1~~ | ~~Rotate objects (free + 15 degree snap)~~ | ✅ |
| ~~US-B.2~~ | ~~Edit polygon vertices (move, add, remove)~~ | ✅ |
| ~~US-B.3~~ | ~~Vertex coordinate annotations on selection~~ | ✅ |

---

## Phase 6: Visual Polish & Public Release (v1.0)

**Goal**: Transform the application from a functional tool into a visually stunning, professionally polished product ready for its first public release. Inspired by competitor analysis of Gardena My Garden and Garden Planner 3.

**Visual Direction**: Lush illustrated style with organic shapes, rich textures, and depth through shadows.

**Graphics Approach**: Pre-made SVG assets (AI-generated) for plants and objects; tileable PNG textures for materials.

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

### US-6.1: Rich Tileable Textures

**Description**: Replace current subtle procedural patterns with visually rich, immediately recognizable tileable PNG textures for all material types.

**Acceptance Criteria**:
- Tileable PNG textures for at minimum: grass, gravel, concrete, wood (deck boards), stone (paving), water, soil/earth, mulch/bark, sand
- Textures seamlessly tileable (no visible seams)
- Scale appropriately with zoom level
- Existing objects using fill patterns automatically use new textures
- Work well in both light and dark theme

**Technical Notes**:
- Texture PNGs at ~256x256 or 512x512, tileable
- Load as QPixmap, use QBrush with TexturePattern mode
- Consider multiple LOD versions for different zoom ranges
- Replace `fill_patterns.py` procedural generation with texture loading system

### US-6.2: Illustrated Plant Rendering

**Description**: Replace flat colored circles with species-appropriate illustrated SVG plant shapes (top-down view). Hybrid approach: ~15-20 category-based base shapes varied by color/size, plus unique illustrations for popular species.

**Acceptance Criteria**:
- Minimum 15 category-based SVGs: round deciduous, columnar tree, weeping tree, conifer, spreading shrub, compact shrub, ornamental grass, flowering perennial, ground cover, climbing plant, hedge section, vegetable, herb, fruit tree, palm
- Each shape: organic illustrated look, color variations, subtle internal detail
- Minimum 8-10 unique species SVGs: rose, lavender, apple tree, cherry tree, sunflower, tomato, boxwood, rhododendron
- Slight color/rotation randomization for natural look
- Existing plant objects map to appropriate shapes

**Technical Notes**:
- SVGs in `resources/plants/` organized by category
- Map PlantType enum + species name -> SVG path
- Render via QSvgRenderer
- Cache rendered QPixmaps for performance

### US-6.3: Drop Shadows

**Description**: Subtle drop shadows on all canvas objects for visual depth. Toggleable in settings.

**Acceptance Criteria**:
- All object types render with soft drop shadow
- Shadow: slight SE offset (~2-4px), semi-transparent black, soft blur
- Toggle in View menu: "Show shadows" (on by default)
- No significant performance impact with 100+ objects

### US-6.4: Visual Scale Bar

**Description**: Persistent scale bar overlay on canvas showing current distance reference.

**Acceptance Criteria**:
- Scale bar in corner of canvas view
- Clean horizontal bar with distance label (e.g., "1 m", "50 cm")
- Auto-adjusts to round numbers as zoom changes
- Semi-transparent background
- Toggleable via View menu

### US-6.5: Visual Thumbnail Gallery Sidebar

**Description**: Redesign object/tool sidebar as visual thumbnail gallery with categories.

**Acceptance Criteria**:
- Categories: Trees, Shrubs, Flowers & Perennials, Vegetables, Ground Cover, Furniture, Fences & Walls, Paths & Surfaces, Garden Infrastructure
- Grid of thumbnails (~64-80px) showing actual illustration + name
- Click to select for placement; drag to canvas for direct placement
- Search/filter box at top
- Scrollable within categories

### US-6.6: Toggleable Object Labels

**Description**: Text labels next to objects showing plant names, custom labels. Toggleable globally and per-object.

**Acceptance Criteria**:
- Plants show species/variety name
- Non-plant objects show custom name or object type
- Global toggle: View menu "Show labels"
- Per-object toggle: Properties panel checkbox
- Labels readable at any zoom (minimum font size)

### US-6.7: Branded Green Theme

**Description**: Garden-themed green color palette with light/dark variants.

**Acceptance Criteria**:
- Primary: garden green palette
- Light theme: white/cream + green accents
- Dark theme: dark gray/slate + softer green accents
- All UI elements styled consistently
- Professional, modern feel

### US-6.8: Outdoor Furniture Objects

**Description**: Library of outdoor furniture with illustrated SVG top-down views.

**Acceptance Criteria**:
- Objects: rectangular table, round table, chair, bench, parasol, lounger, BBQ/grill, fire pit, planter/pot
- Each rendered as illustrated SVG (top-down)
- Resizable, rotatable
- Realistic default dimensions
- Categorized as "Furniture" in gallery

### US-6.9: Garden Infrastructure Objects

**Description**: Practical garden infrastructure objects.

**Acceptance Criteria**:
- Objects: raised bed, compost bin, greenhouse, cold frame, rain barrel, water tap, tool shed
- Illustrated SVG or textured fill
- Realistic default dimensions
- Raised beds show internal soil texture

### US-6.10: Object Snapping & Alignment

**Description**: Smart snap-to-object and alignment/distribution tools.

**Acceptance Criteria**:
- Snap to object edges/centers with visual guides
- Align: left, right, top, bottom, center H, center V
- Distribute: horizontal, vertical (equal spacing)
- Snap toggleable (separate from grid snap)
- Works with multi-selection

### US-6.11: Fullscreen Preview Mode

**Description**: Fullscreen preview hiding all UI (F11).

**Acceptance Criteria**:
- F11 toggles fullscreen preview
- Also via View menu / toolbar button
- Hides: all panels, grid, selection handles, annotations
- Shows only garden illustration on background
- F11 or Escape returns to design mode

### US-6.12: Internationalization (i18n)

**Description**: Multi-language support using Qt Linguist. EN + DE, extensible.

**Acceptance Criteria**:
- All strings wrapped in `tr()` / `QCoreApplication.translate()`
- Translation files: `translations/en.ts`, `translations/de.ts`
- Language selectable in Settings
- German translation complete for all UI
- Contributor documentation for adding languages
- Plant scientific names remain in Latin

### US-6.13: Print Support

**Description**: Print garden plan with proper scaling and page layout.

**Acceptance Criteria**:
- File menu -> Print (Ctrl+P)
- Print preview dialog
- Options: fit to page or specific scale (1:50, 1:100)
- Multi-page for large gardens
- Include/exclude grid, labels, legend

### US-6.14: Windows Installer

**Description**: Professional installer (PyInstaller + NSIS) with file association.

**Acceptance Criteria**:
- PyInstaller bundles as standalone directory
- NSIS installer: wizard, GPLv3 display, path selection, Start Menu shortcut, optional desktop shortcut, .ogp file association, custom .ogp file icon, uninstaller
- Double-clicking .ogp opens the app
- Target size < 100 MB

### US-6.15: Path & Fence Styles

**Description**: Expand polyline objects with path/fence style presets.

**Acceptance Criteria**:
- Paths: gravel, stepping stones, paved, wooden boardwalk, dirt
- Fences: wooden, metal/wrought iron, chain link, hedge, stone wall
- Distinct visual rendering per style
- Selectable in Properties panel
- Width adjustable per object

**Technical Milestones**:
- [x] Texture loading system (replacing procedural patterns)
- [ ] SVG plant illustration asset set (AI-generated)
- [ ] Plant shape rendering engine
- [x] Drop shadow system
- [ ] Scale bar overlay widget
- [ ] Thumbnail gallery sidebar redesign
- [ ] Object label rendering
- [x] Branded green theme
- [ ] Furniture SVG assets + object types
- [x] Infrastructure SVG assets + object types
- [ ] Snap-to-object with visual guides
- [ ] Alignment/distribution tools
- [x] Fullscreen preview mode
- [ ] Qt Linguist i18n + German translation
- [ ] Print support (QPrinter)
- [x] PyInstaller + NSIS installer
- [x] .ogp file association + custom icon
- [x] Path/fence style presets

---

## ~~Phase 7: CAD Precision & Constraints (v1.1 – v1.6)~~ ✅

**Goal**: Full 2D geometric constraint system with numeric precision input, construction aids, and pattern placement — bringing FreeCAD Sketcher-level precision to garden planning.

**Ref**: GitHub Issue #60

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

### US-7.1: Measure Tool Snap to Object Anchors

**Description**: Enhance the measure tool to snap to object center points and edge midpoints when clicking near objects, enabling precise object-to-object distance measurement.

**Acceptance Criteria**:
- Measure tool snaps to object center when clicking within 15cm threshold
- Also snaps to edge midpoints (top, bottom, left, right) of rectangles and polygons
- Visual indicator (small circle) shows the active snap point
- Crosshair marker placed at snapped position, not raw click position
- Works for all object types (circles, rectangles, polygons, polylines)

### US-7.2: Distance Constraint Data Model & Solver

**Description**: Implement the constraint data model and a hybrid Gauss-Seidel + Newton-Raphson constraint solver that resolves constraint chains, including coupled systems like shared-vertex edge-length constraints (see §8.12).

**Acceptance Criteria**:
- `Constraint` dataclass with two anchors (item_id + anchor type), target distance, visibility flag
- `AnchorType` enum: CENTER, EDGE_TOP, EDGE_BOTTOM, EDGE_LEFT, EDGE_RIGHT
- `ConstraintGraph` with adjacency lookup, BFS for connected components
- Iterative relaxation solver: 5 iterations, 1mm tolerance
- Supports pinned items (don't move) and propagates through chains
- Over-constrained detection
- Full serialization for project save/load
- Unit tests for solver (triangle chain, over-constrained, degenerate cases)

### US-7.3: Distance Constraint Tool

**Description**: Dedicated toolbar tool for creating distance constraints between two objects, with anchor point selection and distance input dialog.

**Acceptance Criteria**:
- New "Constraint" tool in toolbar (shortcut: K)
- Workflow: click object A → select anchor → click object B → select anchor → distance dialog
- Anchor indicators (small circles) on hovered objects
- Preview dimension line while selecting second anchor
- Dialog pre-fills current distance, allows setting exact target
- Undo/redo via AddConstraintCommand, RemoveConstraintCommand, EditConstraintDistanceCommand

### US-7.4: Dimension Line Visualization

**Description**: FreeCAD-style dimension annotations with witness lines, arrowheads, and distance text.

**Acceptance Criteria**:
- Dimension line with arrowheads between constrained anchor points
- Witness lines at each anchor
- Distance text centered on line (e.g., "1.20 m"), readable at any zoom
- Satisfied constraints in blue/green, violated in red
- Toggleable via View menu: "Show Constraints"
- Real-time updates when objects move
- Double-click to edit distance value

### US-7.5: Constraint Solver Drag Integration

**Description**: Wire solver into drag system — moving a constrained object propagates through the chain in real-time.

**Acceptance Criteria**:
- Dragged item follows mouse; connected items adjust to satisfy constraints
- Chain propagation: A→B→C, moving A cascades to B then C
- Over-constrained: dimension lines turn red, best-effort positioning
- Undo captures both dragged and constraint-propagated items
- Item deletion cascades to constraint removal
- Constraints in project save/load (new JSON key, file version bump)

### US-7.6: Constraints Manager Panel

**Description**: Dedicated sidebar panel listing all constraints with status, edit, and delete — like FreeCAD's "Randbedingungen" panel.

**Acceptance Criteria**:
- New "Constraints" tab in sidebar
- List: type icon, object names, target distance, status (✓ satisfied / ✗ violated)
- Click to select both objects and highlight dimension line
- Double-click to edit distance
- Delete button/key to remove
- Over-constrained warnings
- Empty state message

### US-7.7: Numeric Position Input

**Description**: Editable X, Y coordinate fields in properties panel for precise positioning.

**Acceptance Criteria**:
- X and Y as editable QDoubleSpinBox (currently read-only labels)
- Values in cm, 1 decimal place
- Changes create MoveItemsCommand for undo/redo
- Constraint solver runs after manual position change

### US-7.8: Numeric Dimension Input

**Description**: Editable width/height/radius fields in properties panel for precise resizing.

**Acceptance Criteria**:
- Diameter editable for circles, Width/Height for rectangles (currently read-only)
- Changes create ResizeItemCommand for undo/redo
- Values in cm, 1 decimal place, minimum >0
- Constraint solver runs after resize

### US-7.9: Horizontal & Vertical Alignment Constraints

**Description**: Constrain two objects to stay on the same horizontal or vertical line.

**Acceptance Criteria**:
- New constraint types: HORIZONTAL (same Y), VERTICAL (same X)
- Created via constraint tool with H/V mode selector
- Solver enforces alignment when objects move
- Composable with distance constraints

### US-7.10: Angle Constraints

**Description**: Fix the angle between three objects (vertex at middle object).

**Acceptance Criteria**:
- ANGLE constraint type (three objects: A, B=vertex, C)
- Angle arc annotation with degree value
- Solver maintains angle during moves
- Common presets: 90°, 45°, 60°, 120°

### US-7.11: Symmetry Constraints

**Description**: Mirror objects across a horizontal or vertical axis.

**Acceptance Criteria**:
- SYMMETRY constraint type (two objects + axis)
- Axis: horizontal, vertical, or construction line
- Moving one mirrors the other
- Visual axis indicator

### US-7.12: Construction Geometry

**Description**: Helper lines/circles that guide placement but don't appear in exports or prints (like FreeCAD's blue construction lines).

**Acceptance Criteria**:
- "Construction" toggle when drawing lines or circles
- Distinct style: dashed, light blue
- Excluded from PNG/SVG export and print
- Usable as snap targets and constraint anchors
- Toggle visibility via View menu
- Persisted in project

### US-7.13: Draggable Guide Lines

**Description**: Horizontal/vertical guide lines draggable from rulers for alignment reference.

**Acceptance Criteria**:
- Drag from top ruler → horizontal guide, left ruler → vertical guide
- Infinite lines spanning full canvas, semi-transparent
- Objects snap to guide lines
- Double-click for exact numeric position
- Drag back to ruler to delete
- Persisted in project, toggleable via View menu

### US-7.14: Linear Array Placement

**Description**: Place N copies of an object along a line with exact spacing.

**Acceptance Criteria**:
- Right-click → "Create Linear Array..."
- Dialog: count, spacing (cm), direction
- Creates copies at exact intervals
- Optional auto-create distance constraints
- Single undo for entire array

### US-7.15: Grid Array Placement

**Description**: Place objects in a rectangular grid with exact row/column spacing.

**Acceptance Criteria**:
- Right-click → "Create Grid Array..."
- Dialog: rows, columns, row spacing, column spacing
- Preview overlay
- Single undo for entire grid

### US-7.16: Circular Array Placement

**Description**: Place objects in a circle with exact radius and angular spacing.

**Acceptance Criteria**:
- Right-click → "Create Circular Array..."
- Dialog: count, radius, start angle, sweep angle
- Equal angular intervals around center
- Single undo

### US-7.17: Coincident Constraint

**Description**: Force two anchor points to occupy the exact same location (zero distance). Like FreeCAD's "Coincident" — useful for attaching the corner of one object exactly onto a vertex or center of another.

**Acceptance Criteria**:
- New `COINCIDENT` constraint type in solver (enforces distance = 0)
- Toolbar button in Constraints section (shortcut: none)
- Workflow: click anchor A → click anchor B → constraint created immediately (no dialog)
- Dimension line visualization: small filled square or diamond marker at the merged point
- Satisfied when both anchors are within 1 mm of each other
- Listed in Constraints panel as "⦿ Coincident"
- Undo/redo via AddConstraintCommand

### US-7.18: Parallel Constraint

**Description**: Keep two line segments (edges of rectangles, polygon sides, polyline segments) parallel to each other. Like FreeCAD's "Parallel" constraint.

**Acceptance Criteria**:
- New `PARALLEL` constraint type in solver
- Workflow: click edge A (near a polyline/rectangle side) → click edge B → constraint applied
- Solver adjusts angle of free object to match the angle of the pinned one
- Dimension line visualization: two parallel arrow markers on each edge
- Listed in Constraints panel as "∥ Parallel"
- Undo/redo via AddConstraintCommand

### US-7.19: Perpendicular Constraint

**Description**: Force two line segments to meet at exactly 90°. Like FreeCAD's "Perpendicular" — useful for paths meeting walls at right angles.

**Acceptance Criteria**:
- New `PERPENDICULAR` constraint type in solver
- Workflow: click edge A → click edge B → constraint applied
- Solver rotates the free object so the angle between edges = 90°
- Dimension line visualization: small right-angle symbol at intersection
- Listed in Constraints panel as "⊾ Perpendicular"
- Undo/redo via AddConstraintCommand

### US-7.20: Equal Size Constraint

**Description**: Constrain two objects to have the same size — same radius for circles, same width or height for rectangles. Like FreeCAD's "Equal" constraint.

**Acceptance Criteria**:
- New `EQUAL_RADIUS`, `EQUAL_WIDTH`, `EQUAL_HEIGHT` constraint types (or single `EQUAL` dispatching by object pair)
- Workflow: select two objects of compatible type → toolbar button creates equal constraint
- Solver resizes the free object to match the size of the pinned/reference one
- Dimension line visualization: "=" annotation near each affected object
- Listed in Constraints panel as "= Equal"
- Undo/redo via AddConstraintCommand

### US-7.21: Fix in Place (Block) Constraint

**Description**: Permanently pin an object to its current position so no solver or drag can move it. Like FreeCAD's "Block" constraint — useful for fixing the house, main fence posts, or reference objects.

**Acceptance Criteria**:
- New `FIXED` constraint type (single anchor only, stores target X/Y position)
- Toolbar button or right-click → "Fix in Place"
- Object cannot be dragged or moved by solver while constraint is active
- Visual indicator: small padlock icon or crossed arrows badge on the object
- Listed in Constraints panel as "🔒 Fixed"
- Removing the constraint restores full movability
- Undo/redo via AddConstraintCommand/RemoveConstraintCommand

### US-7.22: Horizontal & Vertical Distance Constraints

**Description**: Fix the horizontal (X-axis) or vertical (Y-axis) distance between two anchors to a specific value. Distinct from H/V alignment (US-7.9): alignment makes the distance zero on one axis; this sets it to any value. Like FreeCAD's "Horizontal Dimension" and "Vertical Dimension".

**Acceptance Criteria**:
- New `HORIZONTAL_DISTANCE` and `VERTICAL_DISTANCE` constraint types in solver
- Workflow: click anchor A → click anchor B → dialog for exact distance (in meters)
- Solver maintains only the X (or Y) component of the vector, leaving the other axis free
- Dimension line visualization: horizontal (or vertical) double-arrow with value
- Dialog pre-fills current measured H/V distance
- Listed in Constraints panel as "↔ H-dist" / "↕ V-dist"
- Undo/redo via AddConstraintCommand

### US-7.23: FreeCAD-Style Constraint Toolbar with Full Icon Set

**Description**: Replace the current "Constraints" section in the left sidebar with a dedicated horizontal **constraint toolbar** docked at the top of the canvas area, styled exactly like FreeCAD's Sketcher constraint toolbar. All constraint tools are shown as icon buttons in a row: implemented tools have full-color SVG icons, not-yet-implemented tools appear grayed out (disabled) as a visual roadmap preview.

**Reference**: FreeCAD Sketcher workbench toolbar — see screenshot in project notes and look up FreeCAD's actual constraint tool icons at:
- https://wiki.freecad.org/Sketcher_Workbench (constraint tool reference images)
- https://github.com/FreeCAD/FreeCAD source tree `src/Mod/Sketcher/Gui/Resources/icons/` (original SVG icon files for design inspiration — do not copy, use as reference only)

**Tools to include in the toolbar** (in order, matching FreeCAD layout):

| # | Tool | Status | Color |
|---|------|--------|-------|
| 1 | Distance Constraint (K) | ✅ implemented | Full color |
| 2 | Horizontal Alignment | ✅ implemented | Full color |
| 3 | Vertical Alignment | ✅ implemented | Full color |
| 4 | Horizontal Distance | ⬜ US-7.22 | Grayed out |
| 5 | Vertical Distance | ⬜ US-7.22 | Grayed out |
| 6 | Coincident | ✅ US-7.17 | Done |
| 7 | Parallel | ⬜ US-7.18 | Grayed out |
| 8 | Perpendicular | ⬜ US-7.19 | Grayed out |
| 9 | Equal Size | ⬜ US-7.20 | Grayed out |
| 10 | Fix in Place | ✅ US-7.21 | Active |
| 11 | Angle Constraint | ✅ US-7.10 | Active |
| 12 | Symmetry Constraint | ✅ US-7.11 | Active |

**Acceptance Criteria**:

**Layout & placement:**
- New horizontal `QToolBar` docked at the top of the main window (below the existing main toolbar), labeled "Constraints"
- Toolbar is shown only when a constraint tool is active OR always visible (prefer always visible)
- Each button: 32×32px icon, no text label, tooltip showing name + shortcut
- Separator line between groups: Dimensional | Geometric | Advanced
- Remove the "Constraints" category from the left drawing tools panel sidebar (clean up)

**SVG icon design (create all 12 icons in `resources/icons/tools/`):**

Design language: flat, clean, 32×32 viewBox, 2px stroke, rounded caps. Use the FreeCAD icon set as visual reference for each symbol. Color palette for implemented tools:
- Dimensional constraints: deep blue (`#1565C0`) — distance arrows, dimension lines
- Geometric alignment: purple (`#6A1B9A`) — H/V alignment symbols
- Geometric relational: teal (`#00695C`) — parallel, perpendicular, coincident
- Equal/Fix: amber (`#E65100`) — equal sign, padlock

Icon designs per tool:
1. `constraint_distance.svg` — two arrows pointing inward ↔ with a dimension line and measurement hash marks; blue
2. `constraint_horizontal.svg` — horizontal double-headed arrow with a small `H` and an equals sign beneath; purple
3. `constraint_vertical.svg` — vertical double-headed arrow with a small `V` and an equals sign; purple
4. `constraint_h_distance.svg` — horizontal arrow with a numeric `d` label; blue (grayed version = same SVG, opacity 0.3)
5. `constraint_v_distance.svg` — vertical arrow with a numeric `d` label; blue
6. `constraint_coincident.svg` — two circles with overlapping centers and a dot; teal
7. `constraint_parallel.svg` — two parallel slanted lines with arrow pairs; teal
8. `constraint_perpendicular.svg` — two lines meeting at 90° with a small square corner marker; teal
9. `constraint_equal.svg` — `=` sign between two line segments of matching length; amber
10. `constraint_fixed.svg` — padlock icon with small position cross; amber
11. `constraint_angle.svg` — two lines diverging with an arc and degree symbol; blue
12. `constraint_symmetric.svg` — mirrored object pair with a dashed centerline; purple

**Not-yet-implemented buttons:**
- Show all 12 buttons in the toolbar
- Buttons for tools in US-7.10–7.22 (not yet implemented): `setEnabled(False)` + `setToolTip("Coming soon: <name>")`
- Use the same SVG but render at 30% opacity (via `QIcon` with disabled mode, or a separate `_disabled` variant)

**Translation:**
- Add toolbar title and all tooltip strings to both `.ts` files
- Recompile `.qm` files

**Technical notes:**
- `QToolBar` registered with `addToolBar(Qt.ToolBarArea.TopToolBarArea, constraint_toolbar)`
- Buttons are `QToolButton` (checkable, exclusive group) — same pattern as drawing tools panel
- Connect to `ToolManager.tool_changed` to highlight active button
- On tool switch to any constraint type: activate that button in the group
- The existing `DrawingToolsPanel` constraint section (added in US-7.9) is REMOVED in this US

---

## Phase 8: Location, Climate & Planting Calendar (v1.7)

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

### US-8.1: GPS Location & Climate Zone Setup

**Description**: User can set their garden's GPS coordinates to determine the local climate zone and frost dates.

**Acceptance Criteria**:
- Canvas context menu or project settings dialog has "Set Location" option
- GPS coordinate input with latitude/longitude (decimal degrees)
- Coordinates validated (lat: -90 to 90, lon: -180 to 180)
- Tolerance for varying precision (2-6 decimal places)
- Location persisted in the project file (`.ogp`)
- Location indicator shown on canvas or status bar
- Works without GPS — user can also manually enter frost dates as fallback

**Technical Notes**:
- Add `location` dict to `ProjectData`: `{"latitude": float, "longitude": float, "elevation_m": float | None}`
- Add `frost_dates` dict: `{"last_spring_frost": "MM-DD", "first_fall_frost": "MM-DD", "hardiness_zone": "7b"}`
- Store in `.ogp` under new top-level key `"location"`
- New dialog: `ui/dialogs/location_dialog.py`
- Bump `FILE_VERSION` to `"1.2"`

### US-8.2: Frost Date & Hardiness Zone API Lookup

**Description**: Given GPS coordinates, the system automatically looks up local frost dates and hardiness zone via online APIs.

**Acceptance Criteria**:
- After entering GPS coordinates, frost dates are automatically fetched
- USDA zones supported (North America) via Frostline API or similar
- European zones supported via Plantmaps or DWD data
- API results populate the frost date fields automatically
- User can override auto-detected values manually
- Offline fallback: if API unavailable, user enters frost dates manually
- Loading indicator during API call

**Technical Notes**:
- New service: `services/climate_service.py`
- `ClimateService` class with `lookup_frost_dates(lat, lon) -> FrostData`
- API chain pattern similar to `PlantAPIManager`: try multiple sources
- Cache results in `get_app_data_dir()` to avoid repeated lookups
- Consider bundling a coarse hardiness zone GeoJSON for offline fallback

### US-8.3: Auto-Update Notification & One-Click Installer Download

**Description**: At application startup, silently check GitHub Releases for a newer version of the installer (Windows `.exe`). If a newer version is available, display a non-blocking notification banner (or dialog) that informs the user, shows the release notes, and offers a one-click "Download & Install" option. After download, launch the new installer and exit the running app; the NSIS installer supports `/S` silent-ish mode but will prompt for the typical "overwrite existing installation" flow. Only applies to the packaged Windows executable — development environments skip the check.

**Acceptance Criteria**:
- Check runs in a background thread at startup — never blocks the main window
- Compares current version (from `__version__` / git tag embedded at build time) against the latest GitHub Release tag via the GitHub Releases API (`https://api.github.com/repos/<owner>/<repo>/releases/latest`)
- If current ≥ latest: do nothing silently
- If current < latest: show a dismissible notification bar (or `QMessageBox.information`) with:
  - "A new version (vX.Y.Z) is available"
  - Brief release notes (first 300 chars of the release body)
  - "Download & Install" button (downloads `.exe` asset to a temp dir, then launches it, then calls `QApplication.quit()`)
  - "Remind me later" / "Skip this version" button
- User preference "Skip version X.Y.Z" is persisted in QSettings
- Gracefully handles network errors (timeout, no internet) — silently skips the check
- Only active when running from the installed `.exe` (detect via `sys.frozen` or a build-time flag)
- Uses only stdlib + `urllib` for the HTTP check (no extra deps)
- Unit-testable: version comparison logic and API response parsing are pure functions

**Technical Notes**:
- Version embedding: `build_installer.py` writes `_version.py` into the bundled app at build time
- GitHub Releases API: `GET https://api.github.com/repos/cofade/open-garden-planner/releases/latest` → `{"tag_name": "v1.7.x", "body": "...", "assets": [{"name": "OpenGardenPlanner-vX.Y.Z-Setup.exe", "browser_download_url": "..."}]}`
- New file: `src/open_garden_planner/services/update_checker.py`
- Call site: `GardenPlannerApp.__init__` (after window shown), on a `QThread`
- NSIS installer supports running while the old app is closed: download → launch installer → `QApplication.quit()`

---

### US-8.4: Plant Calendar Data Model

**Description**: Extend the plant data model with sowing, transplanting, and harvest timing information.

**Acceptance Criteria**:
- `PlantSpeciesData` extended with planting calendar fields
- Fields: indoor sow window, direct sow window, transplant window, harvest window (all relative to last frost date)
- Days to germination, days to maturity
- Frost tolerance classification (frost-hardy, half-hardy, tender)
- Minimum germination temperature
- Seed depth (cm)
- Local hybrid database with curated data for common vegetables/herbs (50+ species)
- API fallback for extended data from Trefle/Perenual/Permapeople

**Technical Notes**:
- Extend `PlantSpeciesData` in `models/plant_data.py`:
  ```python
  # Planting calendar (weeks relative to last frost date, negative = before)
  indoor_sow_start: int | None = None   # e.g., -8 = 8 weeks before last frost
  indoor_sow_end: int | None = None
  direct_sow_start: int | None = None
  direct_sow_end: int | None = None
  transplant_start: int | None = None
  transplant_end: int | None = None
  harvest_start: int | None = None       # weeks after planting
  harvest_end: int | None = None
  days_to_germination_min: int | None = None
  days_to_germination_max: int | None = None
  days_to_maturity_min: int | None = None
  days_to_maturity_max: int | None = None
  frost_tolerance: str | None = None     # "hardy" | "half-hardy" | "tender"
  min_germination_temp_c: float | None = None
  seed_depth_cm: float | None = None
  ```
- New local database: `resources/data/planting_calendar.json` — curated data for 50+ common vegetables/herbs *(superseded in issue #170 — now `resources/data/plant_species.json`, see ADR-014)*
- Merge logic: local DB has priority, API data fills gaps

### US-8.5: Planting Calendar View

**Description**: A dedicated tab showing a month-by-month calendar of all planting activities based on the garden plan and frost dates.

**Acceptance Criteria**:
- New "Planting Calendar" tab in main window
- 12-month overview (scrollable) showing for each plant in the garden plan:
  - Indoor sowing window (color-coded bar)
  - Direct sowing window
  - Transplanting window
  - Expected harvest window
- Current date highlighted with a "today" marker
- Click on a plant row to see details (germination temp, seed depth, etc.)
- Calendar adjusts automatically when frost dates change
- Empty state when no plants are placed or no location is set

**Technical Notes**:
- New widget: `ui/views/planting_calendar_view.py`
- Custom `QWidget` with a grid-based Gantt chart layout
- Rows = plants from canvas, columns = weeks/months
- Color coding: blue = indoor sow, green = direct sow, orange = transplant, red = harvest
- Derives data from placed plants on canvas + `PlantSpeciesData` calendar fields + project frost dates
- Signal connection: refresh when canvas objects change or frost dates updated

### US-8.6: Dashboard / Today View

**Description**: A dashboard section at the top of the Planting Calendar tab showing actionable tasks for today and this week.

**Acceptance Criteria**:
- "Today" panel at top of Planting Calendar tab
- Shows tasks grouped by urgency: "Overdue", "Today", "This Week", "Coming Up"
- Task types: "Start indoor sowing of X", "Transplant X outdoors", "Direct sow X", "Harvest X"
- Tasks derived automatically from placed plants + calendar data + current date
- Visual indicators for overdue tasks (red), today (yellow), upcoming (green)
- Clicking a task highlights the plant on the canvas (switches to Garden Plan tab)

**Technical Notes**:
- Integrated into `PlanningCalendarView` as a top section
- Uses `QDate.currentDate()` for "today"
- Task generation: compare current date against each plant's calculated windows
- Store task completion state per season in project file (so user can mark "done")

### US-8.7: Tab-Based Main Window Architecture

**Description**: Refactor the main window to support multiple tabs (Garden Plan, Planting Calendar, Seed Inventory).

**Acceptance Criteria**:
- Tab bar above the canvas area with at least "Garden Plan" tab
- Switching tabs preserves state (no data loss)
- Sidebar panels only visible on Garden Plan tab
- Tab icons for visual distinction
- Keyboard shortcut to switch tabs (Ctrl+1, Ctrl+2, Ctrl+3)
- Existing functionality unchanged — Garden Plan tab works exactly as before

**Technical Notes**:
- This is a prerequisite for US-8.5 and US-9.4 — implement first
- Modify `application.py` -> `_setup_central_widget()`
- Wrap current `QSplitter` in a `QTabWidget`
- Tab 0: existing splitter (canvas + sidebar)
- Tabs 1+: new views added by subsequent phases
- Consider `QStackedWidget` if tab bar styling needs customization

---

## Phase 9: Seed Inventory & Propagation Planning (v1.8)

**Goal**: Manage seed packets ("Samenbeutel"), track viability, and plan the full propagation cycle from indoor sowing to transplanting.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-9.1 | Seed packet data model | Must | ✅ v1.8.4 |
| US-9.2 | Seed viability database | Must | ✅ v1.8.4 |
| US-9.3 | Seed inventory management panel | Must | ✅ v1.8.4 |
| US-9.4 | Seed inventory tab view | Must | ✅ v1.8.4 |
| US-9.5 | Propagation planning (pre-cultivation) | Should | ✅ v1.8.5 |
| US-9.6 | Seed-to-plant manual linking | Should | ✅ v1.8.6 |

### US-9.1: Seed Packet Data Model

**Description**: Define the data model for tracking seed packets with all relevant attributes.

**Acceptance Criteria**:
- Each seed packet record contains:
  - Plant species/variety (linked to `PlantSpeciesData`)
  - Purchase/harvest year
  - Quantity (count or weight in grams)
  - Manufacturer/source
  - Batch/lot number (optional)
  - Viability (auto-calculated from species + age)
  - Germination temperature (min/optimal/max)
  - Germination duration (days)
  - Light/dark germinator classification
  - Cold stratification required (yes/no, duration)
  - Pre-treatment notes (scarification, soaking, etc.)
  - Free-text notes
  - Photo attachment (optional, stored as file path)
- Seed viability auto-calculated based on species shelf life and packet age
- Status indicator: "Good", "Reduced viability", "Likely expired"

**Technical Notes**:
- New model: `models/seed_inventory.py`
  ```python
  @dataclass
  class SeedPacket:
      id: str                          # UUID
      species_id: str | None           # Link to PlantSpeciesData
      species_name: str                # Fallback display name
      variety: str = ""
      purchase_year: int = 2024
      quantity: float = 0
      quantity_unit: str = "seeds"     # "seeds" | "grams"
      manufacturer: str = ""
      batch_number: str = ""
      germination_temp_min_c: float | None = None
      germination_temp_opt_c: float | None = None
      germination_temp_max_c: float | None = None
      germination_days_min: int | None = None
      germination_days_max: int | None = None
      light_germinator: bool | None = None    # True=light, False=dark, None=indifferent
      cold_stratification: bool = False
      stratification_days: int | None = None
      pre_treatment: str = ""
      notes: str = ""
      photo_path: str = ""
      created_date: str = ""          # ISO date
  ```
- Viability rules: `resources/data/seed_viability.json` — maps species/family to shelf life in years
- Storage: new top-level key `"seed_inventory"` in `.ogp` project file
- Also store a global seed inventory in `get_app_data_dir()/seed_inventory.json` (not project-specific)

### US-9.2: Seed Viability Database

**Description**: A curated database mapping plant species/families to seed shelf life, enabling automatic viability calculation.

**Acceptance Criteria**:
- Bundled database with viability data for 80+ common species
- Data includes: species/family, typical shelf life (years), viability curve (good/reduced/expired thresholds)
- Auto-lookup when creating a seed packet from a known species
- User can override viability for individual packets
- Source references from established seed viability charts

**Technical Notes**:
- JSON file: `resources/data/seed_viability.json`
  ```json
  {
    "by_species": {
      "tomato": {"shelf_life_years": 5, "reduced_after_years": 4},
      "onion": {"shelf_life_years": 1, "reduced_after_years": 1},
      "lettuce": {"shelf_life_years": 5, "reduced_after_years": 3}
    },
    "by_family": {
      "Solanaceae": {"shelf_life_years": 4, "reduced_after_years": 3},
      "Brassicaceae": {"shelf_life_years": 5, "reduced_after_years": 4}
    }
  }
  ```
- Lookup order: exact species match -> family match -> default (3 years)

### US-9.3: Seed Inventory Management Panel

**Description**: A dedicated panel/dialog for adding, editing, and browsing seed packets.

**Acceptance Criteria**:
- Accessible from Plants menu -> "Manage Seed Inventory"
- Table/card view showing all seed packets with key info at a glance
- Color-coded viability status: green (good), yellow (reduced), red (expired)
- Add new seed packet (with plant species autocomplete from plant database)
- Edit existing seed packet
- Delete seed packet (with confirmation)
- Sort by: name, year, viability, quantity
- Filter by: status (good/reduced/expired), plant family, year
- Search bar for quick finding
- "Needs reorder" indicator when quantity is low (user-defined threshold)

**Technical Notes**:
- New dialog: `ui/dialogs/seed_inventory_dialog.py`
- `QTableView` with custom `QAbstractTableModel` for the seed list
- Or `QListWidget` with custom `QWidget` items for card-style layout
- Reuse plant search/autocomplete from existing `PlantSearchPanel`
- Connect to `PlantLibrary` for species data linking

### US-9.4: Seed Inventory Tab View

**Description**: The Seed Inventory as a dedicated tab in the main window for quick access.

**Acceptance Criteria**:
- "Seed Inventory" tab in main window (third tab after Garden Plan and Planting Calendar)
- Same functionality as the dialog but always accessible
- Quick-add button for new seed packets
- Summary statistics at top: total packets, expired count, needs reorder count
- Batch operations: mark multiple as used, delete multiple

**Technical Notes**:
- New widget: `ui/views/seed_inventory_view.py`
- Shares model/logic with seed inventory dialog (extract into shared service)
- New service: `services/seed_inventory_service.py` — manages CRUD, persistence, viability calculations

### US-9.5: Propagation Planning (Pre-Cultivation)

**Description**: Plan the full indoor propagation cycle: sowing -> germination -> pricking out -> hardening off -> transplanting.

**Acceptance Criteria**:
- For each seed packet or plant in the garden plan, show a propagation timeline:
  1. **Indoor sowing** — start date, required temperature, seed depth
  2. **Germination** — expected duration, check dates
  3. **Pricking out (Pikieren)** — when seedlings have first true leaves
  4. **Hardening off (Abhärten)** — gradual outdoor exposure period (typically 7-14 days)
  5. **Transplanting** — final outdoor planting date (after last frost)
- Each step has a calculated date based on species data + frost dates
- Steps shown as a timeline/Gantt chart in the Planting Calendar
- User can adjust individual dates
- Propagation steps generate tasks in the Dashboard

**Technical Notes**:
- Extend `PlanningCalendarView` with propagation sub-steps
- New model: `models/propagation.py` — `PropagationPlan` with steps
- Default step durations in `plant_species.json` (formerly `planting_calendar.json`, see ADR-014):
  ```json
  {
    "tomato": {
      "indoor_sow_weeks_before_frost": 8,
      "germination_days": [7, 14],
      "prick_out_after_days": 21,
      "harden_off_days": 10,
      "transplant_after_last_frost_days": 14
    }
  }
  ```
- Link propagation plans to seed packets (optional manual linking)

### US-9.6: Seed-to-Plant Manual Linking

**Description**: User can optionally link a seed packet to a placed plant on the canvas.

**Acceptance Criteria**:
- In the Properties panel (when a plant is selected), option to "Link Seed Packet"
- Dropdown/search showing matching seed packets from inventory
- Linked seed packet info shown in Properties panel
- Unlinking is always possible
- Linking does NOT auto-decrement seed quantity (manual quantity management only)
- Linked seeds appear in the Planting Calendar with their propagation timeline

**Technical Notes**:
- Store `seed_packet_id` in `PlantInstance.custom_fields`
- Extend `PropertiesPanel` with seed packet link UI
- Bidirectional: seed inventory view shows which plants a packet is linked to

---

## Phase 10: Companion Planting & Crop Rotation (v1.8.6 – v1.8.12)

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

### US-10.1: Companion Planting Database

**Description**: A curated database of plant compatibility (good neighbors, bad neighbors).

**Acceptance Criteria**:
- Bundled database with companion planting data for 60+ common vegetables/herbs/flowers
- Relationship types: "beneficial" (good neighbor), "antagonistic" (bad neighbor), "neutral"
- Bidirectional relationships (if A helps B, that's recorded for both)
- Reasons/notes for each relationship (e.g., "repels aphids", "competes for nutrients")
- Data sourced from established gardening references
- User can add custom companion planting rules

**Technical Notes**:
- JSON file: `resources/data/companion_planting.json`
  ```json
  {
    "relationships": [
      {
        "plant_a": "tomato",
        "plant_b": "basil",
        "type": "beneficial",
        "reason": "Basil repels aphids and improves tomato flavor"
      },
      {
        "plant_a": "tomato",
        "plant_b": "fennel",
        "type": "antagonistic",
        "reason": "Fennel inhibits tomato growth"
      }
    ]
  }
  ```
- New service: `services/companion_planting_service.py`
- Lookup by species name, common name, or family

### US-10.2: Companion Planting Visual Warnings

**Description**: When placing or moving a plant on the canvas, visually indicate compatibility with neighboring plants.

**Acceptance Criteria**:
- When a plant is selected or being placed, nearby plants are highlighted:
  - Green glow/border: beneficial companion
  - Red glow/border: antagonistic plant
  - No highlight: neutral
- "Nearby" defined by a configurable radius (default: 2m)
- Warnings shown in real-time during drag operations
- Can be toggled on/off in View menu
- Works with both existing placed plants and new plant placement

**Technical Notes**:
- Extend `GardenItem` / plant items with a `set_companion_highlight(type)` method
- Use `QGraphicsDropShadowEffect` or colored border overlay
- Proximity check: iterate nearby items within radius, check companion DB
- Trigger on: item selection, item move, new item placement
- Performance: spatial index or simple distance check (gardens are small)

### US-10.3: Companion Planting Recommendation Panel

**Description**: A sidebar panel showing companion planting recommendations for the selected plant.

**Acceptance Criteria**:
- When a plant is selected, a panel shows:
  - "Good Companions" list with reasons
  - "Bad Companions" list with reasons
  - Which companions are already nearby in the plan
- Clicking a companion in the list highlights it on the canvas (if placed)
- Panel integrated into existing Plant Details panel or as new collapsible panel

**Technical Notes**:
- Extend `PlantDatabasePanel` or create new `CompanionPanel`
- Query `CompanionPlantingService` with selected plant's species
- Cross-reference with plants currently on canvas

### US-10.4: Whole-Plan Compatibility Check

**Description**: Analyze the entire garden plan for companion planting issues.

**Acceptance Criteria**:
- Menu action: Plants -> "Check Companion Planting"
- Scans all plant pairs within proximity radius
- Report dialog showing:
  - Number of beneficial pairings
  - Number of antagonistic pairings (warnings)
  - List of each conflict with plant names, distance, and reason
- Option to highlight all conflicts on the canvas simultaneously
- "Score" or rating for overall plan compatibility

**Technical Notes**:
- New dialog: `ui/dialogs/companion_check_dialog.py`
- Algorithm: for each plant pair within radius, check companion DB
- O(n^2) but fine for garden-scale (typically <100 plants)

### US-10.5: Crop Rotation Data Model

**Description**: Track what was planted where across multiple years/seasons for crop rotation planning.

**Acceptance Criteria**:
- Each bed/area can have a planting history: year -> list of plants
- History persisted in project file
- Plant family classification for rotation rules (Solanaceae, Brassicaceae, etc.)
- Nutrient demand classification: heavy feeder, medium feeder, light feeder, nitrogen fixer (green manure)
- Data for 60+ common species included in the local database

**Technical Notes**:
- Extend `PlantSpeciesData`:
  ```python
  nutrient_demand: str | None = None   # "heavy" | "medium" | "light" | "fixer"
  # family field already exists
  ```
- New model in `models/crop_rotation.py`:
  ```python
  @dataclass
  class PlantingRecord:
      year: int
      season: str           # "spring" | "summer" | "fall" | "winter"
      species_name: str
      family: str
      nutrient_demand: str
      area_id: str          # links to a garden item (bed/area)

  @dataclass
  class CropRotationHistory:
      records: list[PlantingRecord]
  ```
- Store as `"crop_rotation"` key in `.ogp` file
- Nutrient demand data in `resources/data/plant_species.json` (formerly `planting_calendar.json`, see ADR-014)

### US-10.6: Crop Rotation Recommendations

**Description**: Based on planting history, recommend what to plant in each bed this year.

**Acceptance Criteria**:
- For each bed with history, show rotation recommendation:
  - Avoid: same family as last 2-3 years
  - Prefer: follow heavy feeders with medium/light feeders
  - Ideal rotation: Heavy -> Medium -> Light -> Green Manure -> Heavy
- Visual indicator on beds: green (good rotation), yellow (suboptimal), red (violation)
- Recommendation panel showing suggested plant families for each bed
- Warning when placing a plant that violates rotation rules

**Technical Notes**:
- New service: `services/crop_rotation_service.py`
- Rule engine: check last N years of history for family/demand conflicts
- Integrate with companion planting visual system (similar highlight approach)

### US-10.7: Season Management & Plan Duplication

**Description**: Manage multiple seasons/years and duplicate plans for a new season.

**Acceptance Criteria**:
- "New Season" action: duplicate current plan as starting point for next year
- Previous season's plant placements become the rotation history for the new season
- Season selector in the UI to switch between years
- Each season is a separate state of the canvas (different plants, same beds/structures)
- Beds/paths/structures carry over, plants are cleared or kept as user chooses
- Compare view: overlay previous season's plants as ghosted/faded

**Technical Notes**:
- Major feature — likely the most complex US in this phase
- Recommend separate `.ogp` files linked via `"linked_seasons"` metadata field
- Season management dialog: `ui/dialogs/season_manager_dialog.py`

---

## Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools (v1.8.x) ✅ Complete

**Goal**: Perfect the 2D garden planning experience — bed interior design, visual polish, annotations, shape operations, drawing tools, interoperability, and workflow improvements.

> **Status (audited 2026-05-13)**: All Phase 11 user stories shipped. Per-US verification against code:
> US-11.1 ✅ `_parent_bed_id` in `garden_item.py`; 11.2 ✅ `_spacing_radius_cm`; 11.3 ✅ `_grid_enabled`;
> 11.5 ✅ 22 textures in `resources/textures/`; 11.6 ✅ 108 species SVGs in `resources/plants/species/`;
> 11.7 ✅ `minimap_widget.py`; 11.8 ✅ `text_item.py` + `text_tool.py`; 11.9 ✅ `area_label_visible`;
> 11.10 ✅ `callout_item.py`; 11.11 ✅ `group_item.py`; 11.12 ✅ `BooleanShapeCommand`;
> 11.13 ✅ `ArrayAlongPathCommand`; 11.14 ✅ `ellipse_item.py`; 11.15 ✅ `offset_tool.py`;
> 11.16 ✅ `trim_tool.py`; 11.24 ✅ `find_replace_panel.py`.

### Block 1: Bed Interior Design (Top Priority)

### US-11.1: Plant-Bed Parent-Child Relationship

**Description**: Plants placed inside a bed become children of that bed — they move with it, appear in its plant list, and respect its boundaries.

**Acceptance Criteria**:
- When a plant is placed inside a bed's boundary, it's automatically parented to that bed
- Moving a bed moves all its child plants
- Deleting a bed prompts: keep or delete child plants
- Plants can be detached from a bed (drag outside or explicit unlink)
- Bed properties panel shows a list of contained plants with counts
- Copy/paste a bed includes its child plants
- Undo/redo preserves parent-child relationships
- Serialization saves/loads plant-bed associations

**Technical Notes**:
- Extend `GardenItemMixin` with `_parent_bed_id: UUID | None` and `_child_item_ids: list[UUID]`
- Use manual tracking (not Qt's `setParentItem()`) to avoid transform issues
- Modify `commands.py` MoveCommand to propagate movement to children
- Files to modify: `garden_item.py`, `commands.py`, `project.py` (serialization), `properties_panel.py`

---

### US-11.2: Plant Spacing Circles & Overlap Warnings

**Description**: When placing a plant in a bed, show its recommended spacing as a translucent circle. Warn if plants overlap or are too close. Spacing defaults from the plant database but is user-configurable per placement.

**Acceptance Criteria**:
- Each plant shows a faint spacing circle (radius = recommended spacing / 2) when selected or in bed-edit mode
- Spacing value defaults from plant database, user can override in properties panel
- Red highlight / warning icon when spacing circles overlap (plants too close)
- Green highlight when spacing is ideal
- Toggle spacing circles visibility on/off (toolbar button or View menu)
- Spacing data serialized with the plant item
- Works for all plant types: trees, shrubs, perennials, vegetables

**Technical Notes**:
- Add `_spacing_radius: float` to plant items (CircleItem when used as plant)
- Render spacing circle as `QGraphicsEllipseItem` child with low-opacity fill
- Overlap detection: iterate sibling plants in same bed, check distance < sum of spacing radii
- Files: `circle_item.py` (plant rendering), `plant_data.py` (spacing field), `properties_panel.py`

---

### US-11.3: Square-Foot Grid Overlay

**Description**: Any bed can display a customizable interior grid overlay for square-foot gardening or other spacing systems.

**Acceptance Criteria**:
- Right-click bed > "Show Grid" toggles a grid overlay inside the bed boundary
- Grid spacing configurable: 30cm (square-foot), 15cm, 40cm, or custom value
- Grid clips to the bed shape (works with polygons, rectangles, any shape)
- Grid lines are subtle (thin, semi-transparent) and don't appear in exports unless opted in
- Grid cell count shown in bed properties
- Grid offset/rotation follows the bed's rotation
- Grid settings serialized per-bed

**Technical Notes**:
- Add grid rendering to bed items (PolygonItem, RectangleItem when used as GARDEN_BED)
- Use `QPainter.setClipPath(bed_shape)` to clip grid to bed boundary
- Store `_grid_enabled: bool`, `_grid_spacing: float` in GardenItemMixin or bed-specific mixin
- Files: `polygon_item.py`, `rectangle_item.py`, `project.py`, `properties_panel.py`

---

### Block 2: Visual Polish

### US-11.5: Expanded Fill Pattern Library

**Description**: Add 10+ new tileable texture patterns for more realistic and varied garden plan rendering.

**Acceptance Criteria**:
- New patterns: mulch, fine gravel, coarse gravel, river stone, brick (running bond), stone paving, bark, sand, water/ripple, wildflower meadow
- Each pattern is a tileable PNG texture (256×256 or 512×512)
- Patterns available in the fill pattern dropdown for all shape types
- Patterns render correctly at all zoom levels
- Patterns included in PNG/SVG export
- Existing patterns remain unchanged

**Technical Notes**:
- Add PNG files to `src/open_garden_planner/resources/textures/`
- Extend `FillPattern` enum in `fill_patterns.py`
- Update texture loading in `fill_patterns.py`
- Update `ObjectType` defaults where appropriate (e.g., PATH could default to gravel)

---

### US-11.6: Plant Illustration Expansion & Style Refresh

**Description**: Expand the plant SVG library to 100+ species with a consistent, attractive illustration style.

**Acceptance Criteria**:
- 100+ plant SVGs covering: common vegetables (30+), herbs (20+), flowers (20+), trees (15+), shrubs (15+)
- Consistent illustration style: top-down view, similar line weight, cohesive color palette
- SVGs render crisp at all zoom levels
- Each SVG tagged with plant common name for matching with plant database
- Plants shown as recognizable illustrations instead of plain circles on the plan
- SVGs load efficiently (cached, no performance regression)

**Technical Notes**:
- SVGs in `src/open_garden_planner/resources/plants/`
- Extend `plant_renderer.py` SVG loading and caching
- May use AI-assisted SVG generation for quantity
- Map SVG filenames to plant database entries

---

### US-11.7: Minimap / Overview Panel

**Description**: A small semi-transparent overview in the corner of the canvas showing the entire plan with a viewport rectangle for quick navigation.

**Acceptance Criteria**:
- Small overview (~150×100px) in bottom-right corner of canvas
- Shows entire plan as a scaled-down thumbnail
- Red/blue rectangle shows current viewport area
- Click on minimap to pan to that area
- Drag the viewport rectangle to navigate
- Semi-transparent background, non-intrusive
- Auto-hides when plan fits entirely in view
- Toggle via View menu

**Technical Notes**:
- New widget: `src/open_garden_planner/ui/widgets/minimap_widget.py`
- Overlay on top of `canvas_view.py` using `QWidget` overlay or `QGraphicsProxyWidget`
- Render scene thumbnail using `QGraphicsScene.render()` into small QPixmap
- Update on viewport change (connect to `scrollbar.valueChanged`, `zoom_changed`)
- Throttle updates to avoid performance impact (max 10fps)

---

### Block 3: Annotations

### US-11.8: Free Text Annotation Tool

**Description**: Place text blocks anywhere on the canvas with configurable font, size, color, and rotation.

**Acceptance Criteria**:
- New "Text" tool in drawing tools panel (shortcut: T)
- Click on canvas to place text cursor, type to enter text
- Text supports multi-line
- Properties panel: font family, size, color, bold/italic, alignment
- Text items selectable, movable, rotatable like other items
- Double-click to edit text content
- Text serialized in project files
- Text included in exports (PNG, SVG, PDF)

**Technical Notes**:
- New item: `src/open_garden_planner/ui/canvas/items/text_item.py` (QGraphicsTextItem + GardenItemMixin)
- New tool: `src/open_garden_planner/core/tools/text_tool.py`
- Add `TEXT` to ToolType, `GENERIC_TEXT` to ObjectType
- Reuse label editing infrastructure from `GardenItemMixin`

---

### US-11.9: Auto Area Labels

**Description**: Closed shapes automatically display their area (e.g., "12.5 m²") as a centered label that updates when resized.

**Acceptance Criteria**:
- All closed shapes (rectangle, polygon, circle, ellipse) can show area label
- Toggle per-item via right-click > "Show Area" or properties panel checkbox
- Area calculated accurately from shape geometry (polygon area formula, π·r², etc.)
- Displayed in m² (or cm² for small areas, auto-switch threshold)
- Label updates live during resize/drag
- Area label styled differently from name label (smaller, italic, below name)
- Option to show perimeter too

**Technical Notes**:
- Add `_area_label_visible: bool` to GardenItemMixin
- Area calculation: shoelace formula for polygons, π·r² for circles
- Render as child `QGraphicsSimpleTextItem` positioned at centroid
- Files: `garden_item.py`, `rectangle_item.py`, `polygon_item.py`, `circle_item.py`

---

### US-11.10: Callout / Leader Line Annotations

**Description**: Annotation callouts with leader lines (arrows pointing from a text box to a specific feature on the plan).

**Acceptance Criteria**:
- New "Callout" tool — click on target point, drag to place text box, type annotation
- Leader line connects text box to target with an arrowhead
- Leader line re-routes when text box or target moves
- Text box has configurable background (white, transparent) and border
- Multiple leader lines can point to different targets from one text box
- Callouts serializable and included in exports
- Callouts snap to object anchor points

**Technical Notes**:
- New item: `src/open_garden_planner/ui/canvas/items/callout_item.py`
- New tool: `src/open_garden_planner/core/tools/callout_tool.py`
- Leader line: `QGraphicsLineItem` child with arrowhead polygon at end
- Text box: `QGraphicsRectItem` + `QGraphicsTextItem` children

---

### Block 4: Shape Operations

### US-11.11: Group / Ungroup

**Description**: Group multiple items into a single selectable unit. Move, copy, rotate entire groups together.

**Acceptance Criteria**:
- Select multiple items > Ctrl+G to group (or right-click > Group)
- Grouped items show a single selection bounding box
- Moving/rotating/copying the group applies to all members
- Ctrl+Shift+G to ungroup (or right-click > Ungroup)
- Nested groups supported (group of groups)
- Groups serialize/deserialize in project files
- Properties panel shows "Group (N items)" when group is selected

**Technical Notes**:
- Use `QGraphicsItemGroup` from Qt or custom group class
- New item: `src/open_garden_planner/ui/canvas/items/group_item.py`
- Add GroupCommand / UngroupCommand to `commands.py`
- Serialize as `{"type": "group", "children": [...]}` in `project.py`

---

### US-11.12: Boolean Shape Operations

**Description**: Union, intersect, and subtract shapes to create complex bed outlines and landscape features.

**Acceptance Criteria**:
- Select two overlapping shapes, right-click > Boolean > Union / Intersect / Subtract
- Union: merge two shapes into one (outer boundary)
- Intersect: keep only overlapping area
- Subtract: cut shape B from shape A
- Result is a new PolygonItem with the computed outline
- Original shapes removed (with undo support)
- Works with: rectangles, polygons, circles, ellipses
- Preview of result before confirming

**Technical Notes**:
- Use `QPainterPath` boolean operations: `united()`, `intersected()`, `subtracted()`
- Convert each shape to QPainterPath, apply boolean, extract polygon from result via `toFillPolygon()`
- New commands: `BooleanUnionCommand`, `BooleanIntersectCommand`, `BooleanSubtractCommand`
- Files: `commands.py`, context menu in `canvas_view.py` or `select_tool.py`

---

### US-11.13: Array Along Path

**Description**: Place objects evenly along a polyline or curve path (e.g., fence posts along a fence, plants along a border).

**Acceptance Criteria**:
- Select an item + a path (polyline/bezier), right-click > "Array Along Path"
- Dialog: count or spacing, start/end offset, rotation (follow path tangent or fixed)
- Preview shows ghost copies along the path before confirming
- Creates independent copies (not linked instances)
- Single undo action for all placed copies
- Works with any item type as the source

**Technical Notes**:
- Sample points along path at equal arc-length intervals using `QPainterPath.pointAtPercent()`
- For tangent-following rotation: use `QPainterPath.angleAtPercent()`
- New dialog: `src/open_garden_planner/ui/dialogs/array_along_path_dialog.py`
- Reuse existing array command pattern from linear/grid/circular arrays (US-7.14–7.16)

---

### Block 5: Drawing Tools

### US-11.14: Ellipse Drawing Tool

**Description**: Draw axis-aligned or rotatable ellipses for oval beds, ponds, and decorative features.

**Acceptance Criteria**:
- New "Ellipse" tool in Generic Shapes (shortcut: E)
- Click-drag to define bounding rectangle → ellipse drawn inside
- Shift constrains to circle, Alt draws from center
- EllipseItem: selection, movement, resize (independent axes), rotation, labels, styling, layers
- Serialized as `"ellipse"` with center, semi-major, semi-minor, rotation
- Anchor points: center + 4 quadrant points
- Properties panel: semi-major/minor axis numeric input

**Technical Notes**:
- `src/open_garden_planner/core/tools/ellipse_tool.py` (follows `rectangle_tool.py` pattern)
- `src/open_garden_planner/ui/canvas/items/ellipse_item.py` (QGraphicsEllipseItem + GardenItemMixin)
- Add `ELLIPSE` to ToolType, `GENERIC_ELLIPSE` to ObjectType

---

### US-11.15: Offset Tool

**Description**: Offset a shape inward or outward by a specified distance, creating a parallel copy.

**Acceptance Criteria**:
- Select a shape, activate Offset tool, click inside (inward) or outside (outward)
- Input distance via popup or typed value
- Works with: polylines, polygons, rectangles, circles, ellipses
- Creates a new shape (the offset copy), original unchanged
- Preview during cursor movement (shows offset direction)
- Undo support

**Technical Notes**:
- Use `QPainterPath.toSubpathPolygons()` after `QPainterPathStroker` for polygon offset
- Or implement Clipper-based polygon offsetting (more robust for complex polygons)
- Python library option: `pyclipper` for robust polygon offset
- New tool: `src/open_garden_planner/core/tools/offset_tool.py`

---

### US-11.16: Trim / Extend Tool

**Description**: Trim lines/shapes at intersection points, or extend them to meet another shape.

**Acceptance Criteria**:
- Trim mode: click on a segment between two intersections → removes that segment
- Extend mode: click near an endpoint → extends to the nearest intersecting shape
- Works with polylines and polygon edges
- Visual highlight of the segment that will be trimmed/extended on hover
- Undo support

**Technical Notes**:
- Intersection finding: `QPainterPath.intersects()` + compute intersection points
- New tool: `src/open_garden_planner/core/tools/trim_tool.py`
- This is a complex CAD operation — may need to split/modify polyline point lists

---

### Block 6: Workflow

### US-11.24: Find & Replace Objects

**Description**: Search for objects by name/type, batch-select matching items, and bulk-change properties.

**Acceptance Criteria**:
- Ctrl+F opens Find panel
- Search by: name, object type, layer, plant species
- Results highlighted on canvas, listed in panel
- "Select All Matching" button
- Bulk property change: select all matching → change color, fill, layer, etc.
- Replace: change object type (e.g., change all "Tomato" plants to "Cherry Tomato")

---

## Outlook: Additional 2D Features (Candidates for Phase 11 Expansion)

Features identified through competitive analysis of 15+ CAD tools (LibreCAD, QCAD, DraftSight, Inkscape, Affinity Designer, Figma) and 13+ garden planners (GrowVeg, Almanac, Artifact Interactive, iScape, VegPlotter, etc.). These ranked highly but didn't make the initial Phase 11 cut. Revisit after completing Phase 11 core blocks.

### Drawing Tools

| Feature | Priority | Notes |
|---------|----------|-------|
| **Bezier / Spline curves** | High | #1 missing geometry primitive per CAD research. Gardens are organic — curved beds, winding paths, pond outlines need smooth curves. Requires new BezierItem + BezierTool + handle-edit mode. |
| **Arc tool (3-point)** | High | FR-DRAW-06 already listed. Click start, through-point, end to define circular arc. New ArcItem. Natural complement to bezier for precise curved segments. |
| **Fillet & Chamfer** | High | Round off (fillet) or bevel (chamfer) sharp corners on paths, patios, beds. Real gardens never have perfectly sharp 90° corners. Every major CAD tool has this. |
| **Mirror tool** | Medium | Mirror objects across a user-defined axis. Essential for symmetric garden designs. Easy to implement — transform + copy. |
| **Break / Divide / Split** | Low | Split an entity at a click point or divide into N equal segments. Useful for splitting long paths or bed edges. |
| **Stretch tool** | Low | Move vertices inside a selection window while fixing those outside. Power-user CAD feature. |

### Precision Input & Snapping

| Feature | Priority | Notes |
|---------|----------|-------|
| **Relative coordinate input (@dx,dy)** | High | Type `@500,0` to draw 500cm right from last point. Currently users must calculate absolute coordinates. Fundamental CAD precision input. |
| **Polar coordinate input (dist<angle)** | Medium | Specify next point as `@300<45` (300cm at 45°). Useful for angled paths and non-orthogonal layouts. Pairs with relative input. |
| **Additional snap modes** | High | Missing: midpoint (snap to edge center), intersection (where two objects cross), nearest (closest point on edge), perpendicular, tangent. Midpoint and intersection are most impactful. |
| **Dynamic input (on-cursor fields)** | Medium | Floating distance/angle fields near cursor while drawing, Tab to switch. Eliminates looking at status bar. Professional feel. |
| **Object snap tracking** | Low | Temporary dynamic alignment guides from snap points. AutoCAD power feature. |

### Layout & Output

| Feature | Priority | Notes |
|---------|----------|-------|
| **Paper space / print layout** | High | Separate model space (draw 1:1) from paper space (arrange views for printing). Multiple viewports at different scales, title blocks, legends on one sheet. Transforms output from screenshot-quality to professional deliverable. Partially covered by US-11.19 (multi-page PDF) but this is the full CAD approach. |
| **Scale bar for prints** | Medium | Auto-generated scale bar adjusting to print scale. Essential for field-usable printed plans. Simple to implement, high value. Could be added to US-11.19. |
| **Dimension styles** | Low | Named styles for dimension appearance (arrowhead type, text height, decimal precision). Polish feature. |

### Selection & Interaction

| Feature | Priority | Notes |
|---------|----------|-------|
| **Crossing/window selection modes** | Medium | Right-to-left drag = crossing (select touched), left-to-right = window (select enclosed). Professional CAD convention. |
| **Lasso selection** | Low | Freehand selection outline for irregularly grouped objects in dense layouts. |
| **Interactive scale tool** | Low | Scale by precise factor with selectable base point. Currently possible via properties panel but no interactive tool. |

### Visual & Domain-Specific

| Feature | Priority | Notes |
|---------|----------|-------|
| **Paving pattern fills** | Medium | Parametric paving layouts (herringbone, running bond, basket weave) for patios/driveways. Domain-specific visual appeal. |
| **Associative hatch patterns** | Low | Hatch auto-updates when boundary shape changes. Currently fill patterns are static. |
| **Text along path** | Low | Flow text along curved edges for labeling paths, borders. Visual polish. |
| **PDF vector import** | Low | Import PDF and convert to editable vector geometry. Nice-to-have but background image import covers basic need. |

### Smart Features (from Garden Planner Competitors)

| Feature | Priority | Notes |
|---------|----------|-------|
| **Harvest tracking / yield log** | Medium | Log harvest amounts per crop, compare year-over-year. GrowVeg, BioGarden365, VegPlotter have this. Key for improving gardens season to season. Natural extension of garden journal (US-11.23). |
| **Task management / reminders** | Medium | Auto-generate tasks from planting calendar ("Start tomato seeds indoors this week"). GrowVeg does biweekly email alerts from 5,000+ weather stations. High user satisfaction. |
| **Vertical gardening support** | Medium | Growing trend, no competitor handles well. Support for vertical structures, trellises, wall planters. |
| **Container / balcony gardening** | Medium | Frequently requested, poorly served by competitors. Container objects with soil volume, drainage, plant capacity. |
| **Microclimate modeling** | Low | Zero competitors have this. Map microclimates within the garden (wind corridors, heat sinks, frost pockets). Blue ocean but complex. |
| **Soil analysis integration** | Low | Connect soil test results to per-bed recommendations. Nobody does this. |
| **Water usage calculation** | Low | Calculate water needs per zone based on plants, area, climate. Sustainability angle. |
| **Permaculture design tools** | Low | Guilds, zones (0–5), sectors. Only SAGE partially covers this. Large underserved niche community. |
| **Parametric blocks / smart symbols** | Medium | Reusable symbols with configurable parameters (e.g., "raised bed" with length/width/rows). Elevates from drawing tool to design tool. |

### Competitive Benchmarks

- **GrowVeg** (market leader): 21,657 plant varieties, 5,000+ weather stations, biweekly personalized reminders, auto plant count, garden journal with harvest tracking, 441 how-to videos. Weakness: no CAD precision, no seed inventory, subscription-only, web-dependent.
- **OGP's unique strengths**: CAD-precision tools (constraints, dimension lines, angle/symmetry constraints, guide lines, arrays) are unmatched. Seed inventory with viability tracking, companion planting with canvas-level visual warnings, crop rotation data model. Open-source and offline-first.
- **Blue ocean**: Sun/shade simulation (no competitor has it built-in), microclimate modeling, permaculture zones.

---

## Phase 12: Weather & Smart Features (v1.9.0 – v1.10.x) ✅ Complete

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

### US-12.1: Weather Forecast Widget

**Description**: At app startup, fetch a 16-day weather forecast for the project's GPS location (set in US-8.1) from the Open-Meteo API and display it in the Dashboard section of the Planting Calendar tab.

**Acceptance Criteria**:
- Forecast fetched on startup in a background `QThread` — never blocks main window
- Source: Open-Meteo `https://api.open-meteo.com/v1/forecast` with params `daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode&forecast_days=16&timezone=auto`
- No API key required
- **7-day compact strip**: icon (WMO weather code mapped to emoji/SVG), min/max °C, precipitation mm, for days 1–7
- **14-day expandable table**: collapsible section below showing days 8–16 as a table (date, icon, max, min, rain)
- Offline / fetch failed: show most recent cached data with "Last updated X ago" label in muted style
- If no project GPS set: show "Set a location to enable weather forecast" empty state with link to location dialog
- Cache stored in `get_app_data_dir()/weather_cache_{lat:.4f}_{lon:.4f}.json` alongside a fetch timestamp
- Cache considered stale after 3 hours; if fresh (< 3h old) and offline, use cache silently without re-fetching
- No additional Python dependencies — use only `urllib` (stdlib)
- All UI strings wrapped in `self.tr()` / translated in both `.ts` files

**Technical Notes**:
- New service: `src/open_garden_planner/services/weather_service.py`
  - `WeatherService` with `fetch_forecast(lat, lon) -> WeatherForecast | None`
  - `WeatherForecast` dataclass: `days: list[DayForecast]`, `fetched_at: str`
  - `DayForecast`: `date: str, max_c: float, min_c: float, precipitation_mm: float, weathercode: int`
  - WMO code → icon mapping dict (0=☀, 1–3=⛅, 45–48=🌫, 51–67=🌧, 71–77=🌨, 80–82=🌦, 95+=⛈)
  - Cache logic: load/save JSON with timestamp check
- New widget: `src/open_garden_planner/ui/widgets/weather_widget.py`
  - `WeatherWidget(QWidget)` — fetches via `WeatherService`, renders strip + expandable table
  - Signals: `fetch_started`, `fetch_complete`, `fetch_failed`
  - Embedded at top of `PlanningCalendarView.dashboard_section`
- Modify: `src/open_garden_planner/ui/views/planting_calendar_view.py` — add `WeatherWidget` at top of dashboard panel
- Integration test: `tests/integration/test_weather_widget.py` — mock urllib, assert strip renders, assert cache shown with age label

### US-12.2: Frost Alert & Plant-Aware Warnings

**Description**: When the weather forecast includes nights below configurable thresholds, generate visible frost alerts in the Dashboard. Alerts are cross-referenced against frost-sensitive plants placed on the canvas to produce actionable "bring in X tonight" tasks.

**Acceptance Criteria**:
- Two threshold levels, configurable in **Settings → Weather**:
  - **Orange warning**: min temp ≤ 5°C (default) — half-hardy plants at risk
  - **Red alert**: min temp ≤ 2°C (default) — tender plants at risk
- Forecast days hitting a threshold highlighted in the 7-day strip (orange/red background tint on that day's cell)
- Dashboard task list shows frost alert entries: `⚠ Frost tonight: -1°C — protect Tomato (Bed A), Basil (Pot)`
- Tasks include a "Highlight on map" button that switches to Garden Plan tab and selects affected plants
- **Plant sensitivity source** (in priority order):
  1. Per-plant override: new `frost_protection_needed: bool | None` field on plant items (None = use DB default)
  2. `PlantSpeciesData.frost_tolerance`: `"tender"` → warned at red threshold; `"half-hardy"` → warned at orange threshold; `"hardy"` → no warning
- Per-plant override exposed as a checkbox **"Needs frost protection"** in the Properties panel (plant selected)
- Frost alerts re-evaluated whenever the weather cache refreshes or the project is opened
- Settings persist in `QSettings` under `weather/frost_warning_orange_c` and `weather/frost_warning_red_c`
- All strings translated in both `.ts` files

**Technical Notes**:
- Extend `WeatherService`: add `get_frost_alerts(forecast, plants, orange_threshold, red_threshold) -> list[FrostAlert]`
  - `FrostAlert` dataclass: `date: str, min_temp: float, severity: str ("orange"|"red"), affected_plant_ids: list[str]`
- Extend `GardenItemMixin` (plant items only): add `frost_protection_needed: bool | None = None`; serialize in `project.py`
- Extend `PropertiesPanel`: add "Needs frost protection" `QCheckBox` (visible when plant selected)
- Extend `SettingsDialog`: new "Weather" section with two `QDoubleSpinBox` fields for thresholds
- Extend `PlanningCalendarView` dashboard: inject `FrostAlert` tasks into existing task list (sorted by date)
- Modify `WeatherWidget`: tint frost days in the 7-day strip
- Integration test: `tests/integration/test_frost_alerts.py` — mock forecast with frost day, assert dashboard task appears, assert plant highlight works

### Block 2: Interoperability

### US-12.3: DXF Export

**Description**: Export the garden plan to DXF format (AutoCAD R2010+) for professional CAD software interchange.

**Acceptance Criteria**:
- "Export as DXF..." in File menu and Export dialog
- Shape mapping: Rectangle→LWPOLYLINE, Polygon→LWPOLYLINE, Polyline→LWPOLYLINE, Circle→CIRCLE, Ellipse→ELLIPSE
- Layer mapping preserved (OGP layers → DXF layers)
- Construction geometry excluded
- 1 OGP unit = 1 cm in DXF
- Stroke colors mapped to ACI
- Opens correctly in LibreCAD, FreeCAD

**Technical Notes**:
- Dependency: `ezdxf>=0.18` (MIT license, pure Python)
- New service: `src/open_garden_planner/services/dxf_service.py`
- Add to `pyproject.toml` dependencies and `installer/ogp.spec` hiddenimports

---

### US-12.4: DXF Import

**Description**: Import DXF files to bring existing CAD floor plans or site surveys into the garden planner.

**Acceptance Criteria**:
- "Import DXF..." in File menu
- Supported: LINE, LWPOLYLINE, CIRCLE, ARC, ELLIPSE, SPLINE
- Import dialog: preview, scale factor, layer selection
- DXF layers become OGP layers
- Single undo action for entire import
- Unsupported entities: skip with summary count

**Technical Notes**:
- New dialog: `src/open_garden_planner/ui/dialogs/dxf_import_dialog.py`
- Extend `dxf_service.py` with import functions
- Use `ezdxf.readfile()` + entity iteration

---

### US-12.5: Multi-Page PDF Export

**Description**: Generate a professional multi-page PDF report: cover page, plan overview, zoomed detail views, plant list, planting calendar, and legend.

**Acceptance Criteria**:
- "Export PDF Report..." in File menu
- Pages: cover (project name, date, author) → full plan overview → detail views (one per bed, optional) → plant list table → planting calendar → legend
- Configurable: select which pages to include
- Paper sizes: A4, A3, Letter, Legal (landscape/portrait)
- Scale bar, north arrow, title block on plan pages
- Professional typography and layout
- Progress dialog for generation

**Technical Notes**:
- Extend `export_service.py` or new `pdf_report_service.py`
- Use `QPrinter` + `QPainter` or `reportlab` for PDF generation
- Plant list: iterate scene items, collect plant data, render as table
- Calendar data from existing planting calendar model

---

### Block 3: Smart Features

### US-12.6: Shopping List Generation

**Description**: Auto-generate a shopping list from the garden plan with plant quantities, seed needs, materials, and optional cost estimates.

**Acceptance Criteria**:
- "Generate Shopping List" action (menu or toolbar)
- Lists: plants (type, quantity, size), seeds (from seed inventory gaps), materials (soil volume for beds, mulch area)
- Exportable as CSV, PDF, or printable
- Optional cost column (user enters prices per item)
- Groups by category (plants, seeds, materials)

**Follow-up issues (all resolved in one PR):**
- ✅ **#176**: ADR-016 — canonical `species_key()` helper in `models/plant_data.py`; migrated all call sites.
- ✅ **#177**: Extended Materials with "Soil fill" (m³, per-bed configurable depth) and "Mulch" (m²) rows.
- ✅ **#178**: Prune orphan `shopping_list_prices` entries on project save.

---

### US-12.7: Pest & Disease Log

**Description**: Track pest sightings and disease outbreaks per bed/plant with treatment notes and photos.

**Acceptance Criteria**:
- Right-click bed/plant > "Log Pest/Disease"
- Entry: date, type (pest/disease), name, severity, treatment, photo attachment
- History viewable per-bed and per-plant
- Overview panel showing all active issues across the garden
- Data serialized in project file

**Implementation Notes**:
- Data model: `PestLogRecord` / `PestLogHistory` in `src/open_garden_planner/models/pest_log.py`. Severity is categorical (`low`/`medium`/`high`); type is `pest` or `disease`.
- Persistence: serialised under top-level `pest_disease_logs` key as `{target_id: PestLogHistory.to_dict()}`. Photos copied into `{project_dir}/pest_photos/` and stored as project-relative POSIX paths so the .ogp file stays portable.
- Commands: `AddPestLogCommand`, `EditPestLogCommand`, `DeletePestLogCommand` — all undoable, snapshotting prior history for clean restore.
- UI: `PestLogDialog` (Entry + History tabs) opens from the right-click menu on rectangle/circle items (beds and plants). Sidebar `PestOverviewPanel` lists every unresolved entry with double-click reactivation.
- Season carryover: only `resolved=False` records carry to the new season. Resolved entries stay in the previous season as historical record. This makes permanent issues (tree borers) persist while treated outbreaks (a one-off aphid bloom) drop off.
- Photo attachment is gated on a saved project — the button is disabled with tooltip *"Save project first to attach photos"* until `project_manager.current_file` is set.

---

### US-12.8: Succession Planting

**Description**: Plan multiple sequential plantings in the same bed within a season.

**Acceptance Criteria**:
- Bed timeline view showing planting slots per season segment (early spring, late spring, summer, fall)
- Assign different plants to different time slots in the same bed
- Calendar integration: succession plants appear in planting calendar at correct dates
- Visual indicator on bed showing current/next planting
- Companion planting rules apply within each succession group

---

### US-12.9: Garden Journal (Map-Linked Notes)

**Description**: Pin notes and photos to specific locations on the garden plan, creating a visual garden diary.

**Acceptance Criteria**:
- New "Note" tool — click on canvas to place a pin icon
- Click pin to expand note: date, text (rich text), photo attachment
- Pin icon shows on the plan view, subtle when collapsed
- Notes filterable by date range
- Notes included in PDF report export (optional)
- Search across all notes
- Notes serialized in project file

**Technical Notes**:
- New item: `src/open_garden_planner/ui/canvas/items/note_item.py`
- New tool: `src/open_garden_planner/core/tools/note_tool.py`
- Photo storage: save photos in project directory alongside .ogp file

---

### US-12.10: Soil Health Tracking & Amendment Calculator

**Phase**: 12 | **Block**: Smart Features | **Priority**: Must

#### Background

User conducts periodic soil tests (pH, N, P, K, Ca, Mg, S) using Rapitest-style kits or professional lab
reports. OGP records results per bed, visualises soil health on the canvas, and — using the bed's known area
from the CAD model — computes precise amendment quantities in grams. No other garden app can do this because
none carry the geometric model.

**Implemented in five modular sub-stories — execute in order:**

| Sub-story  | Description                                                |
| ---------- | ---------------------------------------------------------- |
| US-12.10a  | Data model + right-click entry dialog + .ogp storage       |
| US-12.10b  | Canvas overlay: overall health tint + parameter drilldown  |
| US-12.10c  | Amendment calculator: inline per-bed + Amendment Plan dialog|
| US-12.10d  | Plant-soil compatibility warnings: bed border + Dashboard  |
| US-12.10e  | Full history + sparkline charts + seasonal reminder badge  |

---

#### Data Model

**New file**: `src/open_garden_planner/models/soil_test.py`

```python
# NPK scale follows Rapitest kit:
#   N: 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus
#   P: 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus
#   K: 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus  (no K0 in kit)
# Secondary nutrients: 0=Low, 1=Medium, 2=High

@dataclass
class SoilTestRecord:
    date: str                    # ISO 8601, e.g. "2026-04-25"
    ph: float | None = None
    n_level: int | None = None   # 0–4
    p_level: int | None = None   # 0–4
    k_level: int | None = None   # 1–4
    ca_level: int | None = None  # 0–2
    mg_level: int | None = None  # 0–2
    s_level: int | None = None   # 0–2
    notes: str = ""

@dataclass
class SoilTestHistory:
    target_id: str               # bed UUID or "global" for project-wide default
    records: list[SoilTestRecord]
```

**Storage**: `.ogp` JSON top-level key `"soil_tests"` → `{target_id: SoilTestHistory.to_dict()}`.

**Hierarchy**: effective record = bed's own latest → fallback to global latest (future: zone in between).

**Plant DB extension** (`src/open_garden_planner/models/plant_data.py`):
Add to `PlantSpeciesData` after `nutrient_demand`:
```python
n_demand: str | None = None   # "low" | "medium" | "high" | "fixer"
p_demand: str | None = None
k_demand: str | None = None
```
Backward-compat: `nutrient_demand="heavy"` → `n_demand="high"` mapped lazily in `SoilService`.

---

#### Amendment Config

**New file**: `src/open_garden_planner/data/amendments.json` (version `"1.0"`)

12 substances bundled at ship time; UI editor deferred. Each entry has:

| Field | Meaning |
|---|---|
| `id` | Stable key for code references |
| `name` / `name_de` | Localised display name |
| `fixes` | List of effects: `"raises_pH"`, `"lowers_pH"`, `"adds_N"`, `"adds_P"`, `"adds_K"`, `"adds_Ca"`, `"adds_Mg"`, `"adds_S"`, `"improves_structure"` |
| `application_rate_g_m2` | Default quantity for one level correction |
| `ph_effect_per_100g_m2` | pH units changed per 100 g/m² applied |
| `{n/p/k/ca/mg}_level_effect` | NPK level steps per one application |
| `organic` | `true` / `false` |
| `release_speed` | `"fast"` / `"slow"` / `"very_slow"` |

Bundled substances: garden lime, dolomite lime, sulfur, blood meal, bone meal, wood ash, compost,
well-rotted manure, epsom salt, gypsum, greensand, rock phosphate.

---

#### Service Layer

**New file**: `src/open_garden_planner/services/soil_service.py`

```python
class SoilService:
    def get_history(self, target_id: str) -> SoilTestHistory: ...
    def get_effective_record(self, bed_id: str) -> SoilTestRecord | None: ...
    def add_record(self, target_id: str, record: SoilTestRecord) -> None: ...
    def calculate_amendments(self, current, target_ph, target_n, target_p, target_k,
                             bed_area_m2) -> list[AmendmentRecommendation]: ...
    def get_mismatched_plants(self, bed_id, plants) -> list[tuple[PlantItem, list[str]]]: ...
    def is_test_overdue(self, bed_id: str) -> bool: ...  # month in {3,4,9,10} AND >180 days
    def overall_health_color(self, record: SoilTestRecord) -> HealthLevel: ...

@dataclass
class AmendmentRecommendation:
    amendment_id: str
    name: str
    quantity_g: float
    rationale: str   # e.g. "Raises pH from 5.8 → 6.5"

class HealthLevel(Enum):
    GOOD = "good"    # green  (100,200,100,80)
    FAIR = "fair"    # amber  (255,200,0,80)
    POOR = "poor"    # red    (220,60,60,80)
    UNTESTED = "untested"  # grey diagonal-hatch
```

Amendment calc formulas:
- pH: `qty_g = abs(target_ph - current_ph) / substance["ph_effect_per_100g_m2"] * 100 * bed_area_m2`
- NPK: `qty_g = (target_level - current_level) * substance["application_rate_g_m2"] * bed_area_m2`

---

#### Key Files

| File | New/Modified | Role |
|---|---|---|
| `src/open_garden_planner/models/soil_test.py` | New | `SoilTestRecord`, `SoilTestHistory` dataclasses |
| `src/open_garden_planner/services/soil_service.py` | New | Business logic: amendments, mismatch detection, overdue check |
| `src/open_garden_planner/data/amendments.json` | New | 12-substance config table (g/m², pH effects, NPK effects) |
| `ui/dialogs/soil_test_dialog.py` | New | Entry dialog (Kit/Lab mode, History tab with sparklines) |
| `ui/dialogs/amendment_plan_dialog.py` | New | Cross-bed amendment plan; "Add to Shopping List" |
| `ui/widgets/soil_sparkline.py` | New | `SoilSparklineWidget` — QPainter polyline, no external lib |
| `src/open_garden_planner/core/project.py` | Modified | Add `soil_tests: dict[str, SoilTestHistory]` to `ProjectData` |
| `src/open_garden_planner/models/plant_data.py` | Modified | Add `n_demand`, `p_demand`, `k_demand` to `PlantSpeciesData` |
| `ui/canvas/canvas_scene.py` | Modified | `drawForeground` overlay, debounced mismatch timer, badges |
| `ui/canvas/items/garden_item.py` | Modified | Context menu "Add soil test…", mismatch border, tooltip |
| `app/application.py` | Modified | Overlay toggle (Ctrl+Shift+S), toolbar combo, Garden menu items |
| `ui/views/planting_calendar_view.py` | Modified | Dashboard soil mismatch cards (urgency AMBER) |

---

#### US-12.10a: Data Model, Entry & Storage

**Branch**: `feature/US-12.10a-soil-data-model`

**Acceptance criteria**:
- Right-click bed → "Add soil test…" → `SoilTestDialog` opens
- Dialog: date picker (default today), pH field (float 0–14), N/P/K dropdowns (None + N0–N4 labels),
  Ca/Mg/S dropdowns (None + Low/Medium/High), notes textarea, Kit/Lab mode toggle
- Kit mode shows categorical labels (Depleted…Surplus); Lab mode shows numeric ppm input
- Garden menu → "Set default soil test…" opens same dialog with `target_id="global"`
- Data persists in `.ogp` `"soil_tests"` key; project marked dirty; undo/redo supported

**Key i18n strings** (add to `scripts/fill_translations.py`):
```
"Add soil test…", "Soil Test", "Soil Test — {name}", "Default Soil Test",
"pH (0–14)", "Nitrogen (N)", "Phosphorus (P)", "Potassium (K)",
"Calcium (Ca)", "Magnesium (Mg)", "Sulfur (S)", "Notes",
"Depleted", "Deficient", "Adequate", "Sufficient", "Surplus",
"Low", "Medium", "High", "Kit (categorical)", "Lab (ppm)"
```

**Integration test** `tests/integration/test_soil_test_entry.py`:
```python
def test_add_soil_test_to_bed_and_persist(app, qtbot, tmp_path):
    # draw rectangle bed → right-click → "Add soil test…"
    # fill: pH=6.2, N=1 (Deficient), P=1, K=1 → accept
    # assert project_data.soil_tests[bed_id].latest.ph == 6.2
    # save to tmp_path → reload → assert round-trip preserves all fields
```

---

#### US-12.10b: Canvas Soil Health Overlay

**Branch**: `feature/US-12.10b-soil-overlay`

**Acceptance criteria**:
- View → "Soil Health Overlay" toggle (Ctrl+Shift+S) tints beds by worst parameter
- Toolbar `QComboBox` (only visible when overlay on): Overall / pH / N / P / K
- Untested beds: grey `Qt.BrushStyle.DiagCrossPattern` fill (alpha 40)
- Overlay excluded from PDF/image exports

**Implementation**:
- `CanvasScene`: add `_soil_overlay_visible: bool = False`, `_soil_overlay_param: str = "overall"`
- Override `drawForeground(painter, rect)` → call `_paint_soil_overlay(painter)` when active
- `_paint_soil_overlay`: iterate bed items → `SoilService.get_effective_record(item_id)` → draw
  `QColor(r,g,b,80)` filled polygon over `item.mapToScene(item.boundingRect())`
- Color map: GOOD=`(100,200,100,80)`, FAIR=`(255,200,0,80)`, POOR=`(220,60,60,80)`
- Per-parameter colour: pH ideal 6.0–7.0; NPK 0/1=red, 2=amber, 3/4=green

**Integration test** `tests/integration/test_soil_overlay.py`

---

#### US-12.10c: Amendment Calculator ✅

**Branch**: implemented on `claude/check-clustering-next-steps-E4ReB` (PR #166).

**Acceptance criteria** (all met):
- `SoilTestDialog` "Amendments" section: target selectors → inline list of amendment + grams for this bed
- Garden → "Amendment Plan…" → `AmendmentPlanDialog`: all deficient beds, grouped by substance,
  totals per substance, "Add all to Shopping List" button (clipboard text — US-12.6 deferred)
- Quantities computed using bed's CAD area via `core.measurements.calculate_area_and_perimeter`

**Amendment priority**: pH correction first, then N, P, K, then secondary nutrients.

**Integration test** `tests/integration/test_amendment_calculator.py`:
```python
def test_amendment_calc_uses_bed_area(app, qtbot):
    # bed with area 2.0 m², soil pH=5.8, target pH=6.5
    # SoilService.calculate_amendments(...) with dolomite_lime
    # expected qty_g ≈ (6.5-5.8)/0.25*100*2.0 = 560 g
    # assert recommendation.quantity_g == pytest.approx(560, rel=0.05)
```

---

#### US-12.10d: Plant-Soil Compatibility Warnings ✅

**Branch**: `claude/check-clustering-next-steps-E4ReB`

**Acceptance criteria**:
- Beds with mismatch: 4 px amber (warning) or red (critical) border rendered in `paint()`
- Hover tooltip: "Soil mismatch: Tomato needs pH 6.5–7.0, current 5.8"
- Dashboard "Today's Tasks": AMBER urgency cards listing each mismatch
- `PlantSpeciesData.n_demand` / `p_demand` / `k_demand` populated for built-in species

**Mismatch rules**:
- pH: `current_ph < plant.ph_min - 0.3` or `current_ph > plant.ph_max + 0.3`
- N: `n_level < 2` and `plant.n_demand == "high"` (Adequate is minimum for heavy feeders)
- P/K: `{p,k}_level < 2` and `plant.{p,k}_demand == "high"`

**Canvas update**: debounced 200 ms `QTimer` in `CanvasScene` (same pattern as spacing circles).
Sets `_soil_mismatch_level: str` on each bed item → read in `paint()`.

**Integration test** `tests/integration/test_plant_soil_warnings.py`

---

#### US-12.10e: History Sparklines & Seasonal Reminder Badge ✅

**Branch**: `feature/US-12.10e-history-and-reminders`

**Acceptance criteria**:
- `SoilTestDialog` "History" tab: scrollable list of past tests + `SoilSparklineWidget` per parameter
- Sparkline: `QPainter` polyline; linear date x-axis; y-axis auto-scaled; dots at each test date
- Seasonal badge: clock icon on bed top-right when `month ∈ {3,4,9,10}` and last test > 180 days ago
- Clicking badge opens `SoilTestDialog` for that bed

**Badge implementation**:
- `SoilBadgeItem(QGraphicsItem)` anchored to bed top-right; updated in `CanvasScene` on scene change
- `mousePressEvent` → emit `soil_test_badge_clicked(bed_id)` signal → `Application` opens dialog

**Integration test** `tests/integration/test_soil_history_and_reminders.py`

---

#### US-12.11: Smart Amendment Composition + User-Toggleable Library + Soil Texture ✅

**Branch**: `claude/roadmap-progress-GwILR`

**Goal**: Make the soil-amendment subsystem usable with the substances people actually own. Real-world fertilizers carry multiple nutrients per bag; the legacy first-pick-per-fix calculator emitted up to three separate rows when one compound product would do. Users on the German market also wanted to disable substances they don't have on hand, plus add structural amendments (sand, perlite, vermiculite, diatomaceous earth) driven by a soil-texture rating.

**Acceptance criteria**:
- Amendment library expanded with eight chemical-generic mineral fertilizers (NPK compound 15-6-12, slow-release lawn fertilizer IBDU, potassium-magnesium sulfate, PK with rock phosphate, ammonium sulfate nitrate, single superphosphate, organo-mineral guano tomato fertilizer) and four structural amendments (diatomaceous earth, perlite, vermiculite, coarse silica sand).
- Calculator rewritten as a deficit-map + greedy max-coverage loop: one pick can credit all nutrients it covers (`AmendmentRecommendation.credits`), reducing a typical NPK-deficient row from three substances to one.
- New `SoilTestRecord.soil_texture` field (`sandy` | `loamy` | `clayey` | `compacted` | `None`) drives a structural-pick phase: clayey → drainage + aeration; sandy → water retention; compacted → aeration.
- Amendment Plan dialog hosts an inline collapsible "Available amendments" panel grouping every substance Organic / Mineral / Structural. Toggling a checkbox triggers immediate recompute. `Prefer organic` toggle. `Enable all` button.
- `ProjectData.enabled_amendments: list[str] | None` (default `None` = all enabled) and `ProjectData.prefer_organic: bool` (default `True`) round-trip through the .ogp file via the `shopping_list_prices` pattern; legacy projects load unchanged.
- Soil-test dialog gains a "Soil texture" combo box (Date / Mode / Soil texture row); the inline amendments preview includes structural rows when texture is set.
- All new strings translated (German). i18n test passes.
- New tests cover: multi-nutrient credit, disabled-amendment skip, organic tie-break flip, structural picks for clayey / sandy / loamy soils, ProjectData round-trip, soil_texture round-trip, and the dialog checkbox-toggle integration.

**Implementation files**:
- Data: `src/open_garden_planner/resources/data/amendments.json` (12 → 23 entries)
- Model: `src/open_garden_planner/models/amendment.py` (4 new FIX_* constants, `AmendmentRecommendation.credits`), `src/open_garden_planner/models/soil_test.py` (`soil_texture` field)
- Calculator: `src/open_garden_planner/services/soil_service.py` (`calculate_amendments` rewrite + `_pick_best_coverage`, `_credit_secondaries`, `_structural_fixes_for`, `_pick_structural`, `_compute_structural`)
- Persistence: `src/open_garden_planner/core/project.py` (ProjectData `enabled_amendments` + `prefer_organic`; ProjectManager proxies + signals; new_project / save / load round-trip)
- UI: `src/open_garden_planner/ui/dialogs/amendment_plan_dialog.py` (CollapsiblePanel + checkboxes + Reset + Prefer-organic), `src/open_garden_planner/ui/dialogs/soil_test_dialog.py` (Soil texture combo)
- Aggregation: `src/open_garden_planner/services/shopping_list_service.py` (`aggregate_amendments` accepts `enabled_ids` + `prefer_organic`; `_collect_materials` reads them from ProjectManager)
- Translations: `scripts/fill_translations.py`
- Tests: `tests/integration/test_amendment_calculator.py` (+7 cases), `tests/unit/test_project.py` (+3 cases), `tests/unit/test_soil_test_history_latest.py` (+2 cases)
- Docs: ADR-015 (design rationale), FR-SOIL-11/12/13, glossary entries (Smart composition, Structural amendment, Soil texture, Enabled set / Amendment library)

**Label-verification follow-up**: Three of the eight commercial fertilizer entries carry a label-derived assumption pending bag re-verification — `slow_release_lawn_fertilizer_ibdu` (IBDU vs methylene-urea), `ammonium_sulfate_nitrate` (S vs SO₃ unit), `single_superphosphate` (single vs triple). Documented in `_notes` of `amendments.json`; corrections land via JSON edits without code changes.

---

#### arc42 Documentation (update after each sub-story — mandatory)

| Document | What to add |
|---|---|
| `docs/05-building-block-view/` | Black boxes: SoilTestHistory, SoilService, SoilTestDialog, AmendmentPlanDialog |
| `docs/06-runtime-view/` | Sequence: add test → overlay update → mismatch recalc |
| `docs/08-crosscutting-concepts/` | New **§ 8.13 Soil Health Tracking**: data hierarchy, Rapitest scale, amendment formula, overlay rendering |
| `docs/09-architecture-decisions/` | ADR: soil data embedded in .ogp (vs. sidecar) |
| `docs/functional-requirements.md` | FR-SOIL-1…FR-SOIL-5 |
| `docs/12-glossary/` | NPK, Amendment, SoilTestRecord, SoilTestHistory, Rapitest scale |

---

## Phase 13: CAD Precision Boost — Package A (v1.11.0)

**Goal**: Close the most-cited CAD precision gaps in one PR — typed coordinate input (relative + polar), two new snap modes (midpoint + intersection) under a unified snap engine, and a Dynamic Input cursor overlay. See ADR-020 (snap engine) and ADR-021 (input pipeline). Bundled as GitHub issue #186.

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | A1    | Relative coordinate input `@dx,dy` (status bar + cursor overlay) |
| ✅     | A2    | Polar coordinate input `@dist<angle`                             |
| ✅     | A3    | Midpoint + intersection snap modes, View-menu toggles            |
| ✅     | A4    | Dynamic Input cursor-anchored overlay                            |

### Acceptance highlights
- Smart decimal/separator parsing handles `,` and `.` deterministically across locales (rules A–F in `core/coordinate_input/parser.py`).
- Single shared `CoordinateInputBuffer` keeps status-bar and cursor overlay in sync.
- Snap providers register on a `SnapRegistry` with priority tie-breaking; quadtree pre-filter holds end-to-end snap < 16 ms on 1000-item scenes (perf gate in tests).
- All drawing tools (polyline, polygon, rectangle, circle, ellipse, construction line/circle) accept typed coordinates via `BaseTool.commit_typed_coordinate`.

### Docs to update on completion
| Document | Section |
|----------|---------|
| `docs/05-building-block-view/` | new `core/snap/`, `core/coordinate_input/`, `ui/widgets/coordinate_input_field.py`, `ui/widgets/dynamic_input_overlay.py` |
| `docs/08-crosscutting-concepts/` | section 8.16 — typed input + unified snap engine |
| `docs/09-architecture-decisions/` | ADR-020 Snap Provider Registry, ADR-021 Coordinate Input Pipeline |
| `docs/functional-requirements.md` | FR-INPUT-01…04, FR-SNAP-04…06 |
| `docs/12-glossary/` | Relative/Polar input, Dynamic Input, SnapProvider, SnapCandidate, SnapRegistry, PointSnapper, midpoint/intersection snap, QuadTree |

---

## Phase 13: CAD Precision Boost — Package B (v1.12.0)

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

### US-B7 dropped during manual-test review

US-B7 originally added a "Layout" tab (`Ctrl+4`) with one page / one viewport / title block / scale bar. Manual testing made it clear the abstraction added no user-visible value on top of what `pdf_report_service` already does (multi-page PDF at A4 / A3 / Letter / Legal, with the model rendered at fit-to-page scale and a built-in scale bar). The Layout tab, viewport item, title block, scale bar item, and `paper_layouts` schema were all removed from PR #191 before merge. `FILE_VERSION` stays at 1.4 because the bezier and arc item types — also part of this phase — are still real. The loader silently ignores the `paper_layouts` key it may encounter in `.ogp` files saved by short-lived draft builds of PR #191.

### Package B follow-ups (post-v1.12.0)

Manual testing of PR #191 surfaced follow-up gaps, closed in later PRs:

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | B8    | Snap engagements emit *enforceable* constraints + new `TANGENT` type (#192/#196/#197, PR #198, v1.13.0) — see ADR-024 |
| ✅     | B9    | Vertex/handle editing for placed Bezier + Arc (#193) — dedicated `CurveEditMixin` + `CurveControlHandle`, one-undo reshape — see ADR-025 |
| ✅     | B11   | 3-point arc endpoint precision (#195) — exact cubic-Bézier rendering (`arc_to_painter_path`); arc tool reordered to **start → end → bulge** per user feedback |
| ✅     | B4    | Mirror tool (#187 remainder) — reflect selection across a two-click axis (Shift = 45°), Copy/Move; per-type rebuild (`core/mirror_geometry.py`), Move preserves `item_id` so constraints stay bound — see ADR-026. Closes epic #187 |

### Acceptance highlights
- `SnapProvider.candidates()` extended with `reference_point: QPointF | None = None`; all in-tree providers updated atomically; existing tests still green.
- File format `FILE_VERSION` bumped 1.3 → 1.4 to register the new `arc` / `bezier` item types. v1.3 files load unchanged — regression test in place.
- Filleted rectangles convert destructively to polygon-with-arc; undo restores the rectangle (ADR-022).
- Shared `services/scene_rendering.render_scene_region()` helper consolidates PNG export's overlay-hiding / Y-flip / text-scaling bookkeeping into one place. PNG export refactored to use it; SVG export + print dialog migration tracked as follow-up.

### Out of scope (deferred)
- Alt-break-symmetry handles on Bezier (smooth-only in MVP)
- Native DXF export of cubic Beziers (rasterised for now)
- `pdf_report_service` + `print_dialog` migration to `render_scene_region` — only `export_to_png` migrated in this PR; the others land in a follow-up

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/05-building-block-view/` | `services/scene_rendering.py`, `core/cad_geometry.py` additions, new `*_tool.py` + `*_item.py` files |
| `docs/09-architecture-decisions/` | ADR-022 Bezier + filleted rect, ADR-023 Snap pipeline v2 |
| `docs/functional-requirements.md` | FR-20 (curves, corners, ref-point snaps) — FR-DRAW-08/09, FR-EDIT-10/11, FR-SNAP-07/08/09 |
| `docs/12-glossary/` | Arc (3-point), Cubic Bezier, Fillet, Chamfer, Nearest/Perpendicular/Tangent snap, Reference point, render_scene_region |

---

## Phase 13: Smart Features — Package C (v1.17.0)

**Goal**: Give the plan a single, actionable to-do list. One unified **Tasks** dashboard tab that aggregates every auto-derived action — planting-calendar windows, succession sow/clear, soil amendments, frost protection — plus user-created manual tasks, with persistent done / snooze / dismiss state. See ADR-029 (pure generators + render-time status + dual-store coexistence) and FR-21.

| Status | US    | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | C1    | Harvest tracking / yield log (#188) — per-plant/bed log + garden-wide dashboard — see FR-23 |
| ✅     | C2    | Task management & reminders — unified Tasks tab (#188) — see ADR-029 |

### US-C1 acceptance highlights

- **"Log Harvest…"** on any plant/bed context menu opens `HarvestLogDialog` (Entry + History tabs); each entry stores date, quantity, editable unit (kg/g/pcs/bunch/L), quality, notes, optional photo. History groups past entries by year with per-unit subtotals. Mirrors the pest-log architecture (US-12.7).
- **Undoable** Add/Edit/Delete (`Add/Edit/DeleteHarvestRecordCommand`); records persist under the additive `.ogp` key `harvest_logs` keyed by item UUID (no `FILE_VERSION` bump). Each `HarvestHistory` caches `species_key`/`species_name` so totals resolve even after the plant is deleted.
- **Garden-wide Harvest dashboard tab** (Ctrl+6 — Ctrl+5 since #310, appended via `indexOf` so existing shortcuts/badges are untouched) shows per-species/per-year/per-unit totals from the pure, Qt-free `services/harvest_aggregation.aggregate_by_species_year` (different units never summed); double-click a row selects that species on the canvas. **CSV export** + optional **PDF "Harvest summary"** page.
- **Journal link**: each harvest auto-creates a **pin-less** `harvest`-tagged `JournalNote` (new `JournalNote.tags`) so it appears in the Garden Journal without a canvas pin; Add/Edit/Delete keep it in sync and undo restores both. The journal note dialog preserves `tags` so editing never strips the marker.
- **Season rollover**: harvest history carries forward (year-over-year totals survive rotation); carried records have their `journal_note_id` severed since the new season starts with a blank journal.

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/functional-requirements.md` | FR-23 (FR-HARVEST-01…10) |
| `docs/05-building-block-view/` | `models/harvest_log.py`, `services/harvest_aggregation.py`, Harvest dashboard tab |
| `docs/12-glossary/` | Harvest log, Harvest aggregation; Ctrl+6 shortcut (Ctrl+5 since #310) |

### US-C2 acceptance highlights

- **Unified Tasks tab** (Ctrl+5 — Ctrl+4 since #310, appended after Seed Inventory via `indexOf` so existing shortcuts/badges are untouched) groups tasks Overdue / Today / This Week / Upcoming / No date, with collapsible **Snoozed** and **Done** sections.
- **Auto-generated tasks** come from six pure, Qt-free `(PlanState) -> list[Task]` generators (`services/task_generator.py`): planting-calendar windows, propagation steps, succession sow/clear, one soil-amendment task per recommendation per bed, frost protection (from the weather service's frost alerts), and manual tasks; `generate_all` flat-maps + dedups by `task_id`.
- **Manual tasks** (`models/task.py` `ManualTask`: date, title, notes, optional bed link) are created/edited via `TaskDialog`; Add/Edit/Delete are undoable.
- **Status is render-time** (`services/task_status.effective_status`): open / snoozed / done / dismissed / archived computed against "today" — no scheduler; expired snoozes reappear, done > 7 days auto-archives.
- **Additive persistence**: new `.ogp` keys `manual_tasks` + `task_states`, no `FILE_VERSION` bump; older files load with empty dicts and legacy `task_completions` is folded to archived-done on load.
- **Dual-store coexistence → converged (#228)**: the original design had `set_task_status` and `set_task_completion` both write `task_states` and the legacy `task_completions` done-set so the (untouched) planting-calendar dashboard stayed consistent with the Tasks tab. The convergence follow-up (#228) retired that: the calendar dashboard now generates its rows from the same `generate_all(build_plan_state(...))` engine and reads `effective_status`, `set_task_completion` delegates to `set_task_status` (single write-path), soil-mismatch is a shared generator on both surfaces, and the calendar refresh was debounced + wired to `stack_changed` (fixing #225's undo/redo staleness). `task_completions` remains only as a write-only `.ogp` compat mirror.
- **Navigate-to-bed** from a task selects/centres the linked bed/species/items on the Garden Plan tab; frost tasks reuse the planting calendar's single weather fetch (`frost_alerts_ready`) — no second forecast request.

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-029 (pure generators, render-time status, dual-store coexistence) |
| `docs/05-building-block-view/` | §5.5 Task subsystem; `services/task_generator.py`, `services/task_status.py`, `models/task.py`, `ui/views/tasks_view.py`, `ui/dialogs/task_dialog.py` |
| `docs/functional-requirements.md` | FR-21 (FR-TASK-01…09) |
| `docs/12-glossary/` | Manual task, Task state, Task generator, Effective status; Ctrl+5 shortcut (Ctrl+4 since #310) |

---

## UI/UX: Sidebar Accordion (issue #226)

**Goal**: Declutter the right sidebar. Replace the static stack of 9 always-expanded panels with a hover-peek + click-to-pin accordion.

| Status | Issue | Description                                                      |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅     | #226  | Hover-peek + click-to-pin sidebar accordion — see ADR-030       |

### Acceptance highlights (revised after manual test — ADR-030 addendum)
- All panels **collapsed at startup** every session (no pin/panel-state persistence).
- **Hover** a bar → peeks open in place (reflow pushes bars below down); leave → collapses (asymmetric debounce, no flicker on fast sweeps).
- **Click** title → toggles open/closed, **animated** (organic height expansion). Panels keep a **fixed order** — opening one never reorders the list.
- Open panels **fill the available space** (content-weighted) instead of leaving an empty gap: one open panel fills the sidebar; several share the surplus by content size; combined overflow **scrolls**. (Equal-share + draggable dividers from the first cut were dropped.)
- Selecting a plant auto-opens Plant Details + Companion; selecting a bed auto-opens Crop Rotation; clearing closes them. An auto-opened panel is **closable with one click** and stays closed for that selection; a different selection re-opens it. Manually-opened panels survive a selection clear.
- New `SidebarController` (`ui/widgets/panel_stack.py`) owns the layout + `PanelState`/`PinSource` machine: one `QVBoxLayout` in a `QScrollArea`, panels never reparented.
- First cut used a bottom `QSplitter` (reparent-on-pin) — reworked after manual testing surfaced reordering, no animation, and unclosable selection panels.

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-030 + manual-test addendum (accordion interaction model, no-splitter rework, no-persistence; refines ADR-005) |
| `docs/08-crosscutting-concepts/` | §8.17 (PanelState machine, no-reparent layout, animation, debounce, dynamic-property QSS gotcha) |
| `docs/functional-requirements.md` | FR-22 (FR-UI-SIDEBAR-01…06) |

---

## Canvas: Per-object stacking order (issue #338)

**Goal**: Add CAD-standard *Bring to Front / Bring Forward / Send Backward / Send to Back* for selected objects, reachable from the right-click context menu, the Properties panel, and keyboard shortcuts — reordering objects **within their own layer only**, with multi-selection keeping relative order and a bed's contained plants moving as one block.

| Status | Issue | Description |
| ------ | ----- | ---------------------------------------------------------------- |
| ✅ | #338 | Per-object stacking order within a layer — see ADR-043 / FR-31 / §8.25 (shipped v1.27.3, PR #340) |

### Acceptance highlights
- **Sparse rank + derived z** — a new `stack_order: int | None` sort key (`STACK_STEP = 1024`) replaces the old all-items-tie-at-`layer.z_order*100` scheme. z is never stored as intent: `CanvasScene._normalized_layer_order`/`_refresh_layer_z` derive it fresh from the current ranks as `layer.z_order*100 + 100*(i+1)/(n+1)`, strictly inside the layer's own band so it can never collide with a fixed overlay z (dimension lines, tool previews, the soil badge, the minimap cutoff — §8.25's reserved-band table; journal pins are their own rank-carrying document item, not a fixed band — see §8.25.6). Ranks are written in exactly four places (`CanvasScene.addItem`, `MoveToLayerCommand`, `ArrangeItemsCommand`, and the post-load renumber when `suspend_z_refresh(renumber=True)` exits) — the refresh itself never writes one, which is what keeps every command's undo snapshot exact.
- **Derive-only clamp for beds and roof ridges** — `core/stacking.py::normalize_order` reorders (never re-ranks) a plant to sit immediately above its parent bed, and a `ROOF_RIDGE` immediately above its owner polygon, only when that parent is itself in the same layer. "Send to Back" on a lone plant stops just above its bed rather than reaching the true bottom, and correctly reports "already at back" when it's already there.
- **One apply seam** — `ui/canvas/arrange.py::build_arrange_command` is the only place that groups a selection by layer and asks the Qt-free `core/stacking.py::arrange` what changes; the Edit ▸ Arrange menu, every item's `Arrange ▸` context-menu submenu (9 shared-seam shapes via `GardenItemMixin`), the Properties panel's Arrange row (single + multi-selection), and the Agent API's `arrange_object` tool all call it — the same discipline `ui/canvas/geometry_apply.py` established for resize/rotate, for the same reason (a copy-per-call-site pattern is how earlier rotated-geometry bugs happened).
- **Undo story** — exactly one `ArrangeItemsCommand` per gesture, however many layers or block members it touches; a no-op (already at front/back, or nothing to step past) pushes nothing onto the undo stack and reports the reason via status message instead.
- **Persistence story, and a real bug fixed en passant** — `.ogp` save order flips from Qt's top-first `scene.items()` to bottom→top, fixing a **proven, pre-existing bug**: every save/load round-trip had silently inverted same-layer stacking (only the plant/bed and roof-ridge cases were band-aided). The new `stack_order` key is additive; `FILE_VERSION` is unchanged. A file without the key loads in file order and gets honest ranks on first load by the new app; the write-order fix benefits *older* app versions too, since they simply read file order.
- **Two design-review catches before anything shipped**: a first draft had the z-refresh also renumber ranks as a side effect — rejected because a refresh runs on many unrelated paths and would silently invalidate a command's undo snapshot taken before it; a second draft assigned a provisional z at add time to be finalized lazily — rejected because it breaks the moment items are deleted from the middle of a layer. Both are recorded as rejected alternatives in ADR-043.
- **Clipboard fix found along the way** — copy/duplicate previously produced layer-less pasted items (no `layer_id` was ever saved to the clipboard dict); paste now carries and validates `layer_id` against the target scene, falling back to the active layer.
- **Bulk-add performance** — `CanvasScene.suspend_z_refresh()` (a context manager, `renumber=True` on the load path) defers the per-add z-refresh across a batch instead of doing one O(layer-size) refresh per item; measured, a 50-item paste into a 2000-object plan went from 316 ms to 91 ms.
- **Agent parity** — the token-gated `arrange_object(item_id, action)` write tool calls the identical seam (bed block and plant clamp included) and refuses a no-op rather than reporting a false success; `ObjectRef`/`ObjectDetail` gain a read-only `stack_index` (0-based, bottom→top, per layer), and `list_objects`/`objects_in_region`/`get_object` are now documented as bottom→top in stacking order (`get_diagnostics` is explicitly not).
- Journal pins stay unarrangeable (no context-menu entry, GUI no-op, agent refusal); arcs/beziers are arrangeable via menu/shortcut but have no context-menu entry (they never had a Move-to-Layer one either).

### Docs updated on completion
| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-043 |
| `docs/functional-requirements.md` | FR-31 (FR-STACK-01…08) |
| `docs/08-crosscutting-concepts/` | §8.25 (new); §8.2 addendum; §8.9.5 stale-claim correction; §8.19 tool list |
| `docs/11-risks-and-technical-debt/` | §11.4 — save/load inversion, clipboard layer-less gap, refresh-writes-state-breaks-undo lesson |
| `docs/12-glossary/` | "Stacking order", "Arrange", "Stack index" |

## Google Maps packaged-build follow-up (Issue #342)

Shipped in v1.27.5 via [PR #344](https://github.com/cofade/open-garden-planner/pull/344): the satellite picker now accepts a Google Maps API key from Preferences, while retaining the environment/adjacent-`.env` fallback for source and packaged builds. Preferences values take precedence, blank values fall back, and credentials are excluded from project files and artifacts. Worker shutdown is asynchronous across picker rejection, window close, and application shutdown. See ADR-019, FR-IMG-08, and §8.15.

## Satellite import redesign around the Maps JavaScript API (Issue #346)

Shipped 2026-09-01 in v1.27.6 via [PR #348](https://github.com/cofade/open-garden-planner/pull/348): for projects Google's EEA terms restrict (Static Maps API rejects `satellite`/`hybrid` with a canonical 403), the picker now offers — and always provides — a **JS-API view capture**: the live map is positioned over the drawn rectangle, the `QWebEngineView` is grabbed at the widget level (no DOM access, no tile harvesting; tile URLs embed the key and taint canvases — html2canvas is structurally dead), and the image is cropped and scaled with the same analytic math plus a baked attribution strip. `FetchResult` gains `source`/`attribution` provenance and `geo_metadata` persists the additive keys. See ADR-019 addendum, FR-IMG-08/FR-IMG-10, §6.3.1, §11.4, and the unit/integration suites in `test_google_maps_js_capture.py` / `test_map_picker_capture.py`. Pan-grid stitching for higher resolution is follow-up [Issue #347](https://github.com/cofade/open-garden-planner/issues/347).

## Pan-grid view capture for higher resolution (Issue #347)

Shipped 2026-09-02 in v1.27.7 via [PR #350](https://github.com/cofade/open-garden-planner/pull/350): the JS-API view capture now raises its resolution ceiling to the Static mosaic's level. The capture is a **pan grid** — a capture-profile phase pins the real viewport + dpr, then the page pans the map across a `cols × rows` (≤ 3×3) grid of viewport positions at one integer zoom and Python grabs and stitches each frame. Seams are eliminated analytically: frame centres sit a whole number of world/css pixels apart (identical sub-pixel phase) and steps are dpr-aligned so `stitch_frames` pastes at integer grabbed-pixel offsets with no overlap. `pick_capture_zoom_and_grid` mirrors the Static `pick_zoom_and_grid` (single-frame capture is the degenerate 1×1 grid — one engine). Per-frame render failures retry twice, then fail cleanly; a mid-capture resize is refused; the stitched mosaic carries exactly one baked attribution strip. `FetchResult` and `geo_metadata` are unchanged. See ADR-019 addendum #347, FR-IMG-11, §6.3.1, §11.4, and the extended unit/integration suites (numerical stitch verification reconstructs a synthetic world image pixel-perfectly). The one real-key assumption (Google's rasterizer phase-determinism between whole-css-px pans) is on the manual-test checklist.

## Build provenance attestation for release artifacts (Issue #356)

Shipped 2026-09-15 in v1.27.9 via [PR #357](https://github.com/cofade/open-garden-planner/pull/357): Windows Defender flagged the installer as `Trojan:Script/Wacatac.C!ml` — a known PyInstaller/Defender false-positive pattern, worsened by the installer being unsigned (issue #89, closed not_planned — no budget for a paid Authenticode cert). `release.yml` now attests build provenance (`actions/attest-build-provenance`, Sigstore-backed, no paid cert) for the installer, the raw app exe it packages, and `SHA256SUMS.txt`, so anyone can independently verify with `gh attestation verify` that a release artifact was built by this project's public CI from a specific public commit. This proves source provenance, not Authenticode signing — SmartScreen/Defender warnings can still appear. See ADR-044, §11.1, §11.2. That budget rationale describes the 2026-09-15 decision; signing options, including no-cost proposals, are now under evaluation in [#375](https://github.com/cofade/open-garden-planner/issues/375), with no option adopted or effectiveness established (#376).

---

## Manual-pass follow-up: four defects (#373, #377, #378, #380)

Shipped together in one PR. Four defects found while dogfooding the agent tooling and the D3.2 manual pass.

| Status | Issue | Description |
| ------ | ----- | ----------- |
| ✅ | #377 | **Tool previews drew behind beds.** Every shape tool's in-progress preview primitive kept Qt's default `z = 0` while real items get a derived z inside `(0, 100)`, so the dashed preview was invisible whenever the gesture overlapped a bed. Fixed by the new `core/tools/preview_z.py`, which holds the reserved preview band (`999`–`1002`, below the minimap's `10000` cutoff) for the 11 modules that build a preview. The issue's own module list was incomplete: it omitted `construction_tool.py` and wrongly included three modules that build no preview item at all; a drift guard re-derives the set from source. See §8.25.6, §11.4. |
| ✅ | #378 | **Crop-rotation panel ignored an existing succession plan.** A bed could show a succession badge while the panel beside it said "every crop is suitable". The panel now shows a display-only **"Planned This Season"** section (planned crops with their botanical family, clearly *not* history) and an explicit message when there is a plan but no history. `CropRotationService` is unchanged — the plan is deliberately **not** fed into `get_recommendation`, which would change the 3-year cooldown for every caller (the rejected option in the issue). See ADR-036 addendum. |
| ✅ | #373 | **App shutdown waited ~10 s for the Agent API thread.** Root-caused with instrumentation: an MCP client holding the SSE stream open never closes it, and uvicorn's graceful shutdown waits for open connections, so `serve()` never returned and both 5 s joins expired. Fixed by cancelling the loop's tasks and stopping the loop directly on `stop()` (measured 10.03 s → 0.58 s with a streaming client; 0.00 s without). `force_exit` alone did **not** fix it. See §11.4. |
| ✅ | #380 | **Agent writes were not canvas-clamped.** The GUI clamps objects to the canvas at five sites; the agent path did not, so `create_object`/`move_object` could strand an object entirely off-plan where it was invisible and un-deletable. New Qt-free `core/canvas_bounds.py` holds the rule once, called by both the GUI drag paths and the agent paths, so they cannot drift. Adds `ObjectRef.outside_canvas` and a `get_diagnostics` kind `outside_canvas` so an already-saved off-plan object is discoverable. This is a deliberate reversal of the earlier "stage an object just off-plan" rationale. See ADR-036 addendum, FR-AGENT-26, §8.19. |

---

## Phase 13: Agent Integration — Package D (MCP Server) — Complete (v1.29.1, PR #382)

**Goal**: Expose the garden plan to AI agents (Claude, Cursor, any MCP client) so they can read, visualise, export, and — behind the explicit write gate — edit it. The running app embeds a **Model Context Protocol server over streamable-HTTP** on `127.0.0.1` (on by default for reads, loopback-only; toggle to disable). D1 shipped the read/visualise/export surface; D2.0–D2.6 shipped the token-gated creation, domain editing, layer, global-history, and low-level geometry tools; D3.1/D3.2 shipped earlier; D3.3/D3.4 shipped in v1.29.1 via PR #382, completing Package D and closing epic #237. See ADR-033/034/036, FR-26, §8.19, and GitHub epic #237.

### Design decisions (from the planning session)
| Axis | Decision |
|------|----------|
| Transport | Embedded **MCP server over streamable-HTTP** hosted by the running app (no separate relay process) |
| Execution | Operates on the **live running app** — reads reflect the open plan; edits go through the undo stack |
| Connection | App binds `127.0.0.1:<port>` (configurable); agent client connects by URL |
| Security | **On by default for reads**, Settings toggle to disable, **loopback-only** bind; D2 scene-mutating tools require both the writes-enabled setting and a bearer token (ADR-036). |
| Approval (writes) | Auto-apply, **fully undoable** — one undo step per agent operation (the contract for D2) |
| Concurrency | **Free co-editing** — agent calls marshaled onto the Qt main thread and serialised |
| Abstraction | **Layered** — domain-level API + low-level geometry escape hatches |
| MCP surface | **Tools + resources + prompts** |
| Read model | **Curated, stable agent schema** (decoupled from `.ogp` FILE_VERSION) with a **raw** escape hatch |
| Addressing | **Stable object UUIDs** primary |
| Vision | **`render_canvas_image` tool** (PNG) + structured data |

### Phasing
| Phase | Scope |
|-------|-------|
| **D1 (v1, MVP)** | Write-ready core + read/query tools + render-image tool + export tools + resources + read-analysis prompts |
| **D2** | Write/edit tools (create/move/resize/delete beds, containers, plants, shapes; assign species; layers; global undo/redo) — auto-apply, one-undo-per-op, free co-edit; low-level geometry escape hatches. **Prerequisite: token auth** (FR-AGENT-03 / §8.11) landed with D2.0. **D2.0 ✅ shipped** the token gate + first write slice (`move_object`/`delete_object`, ADR-036); **D2.1 ✅ shipped** `create_object` (plants + soil containers); **D2.2 ✅ shipped** `resize_object`/`rotate_object` plus the canonical `ui/canvas/geometry_apply` path; **D2.3 ✅ shipped** `set_species`/`set_parent_bed`; **D2.4 ✅ shipped** `list_layers` and layer writes; **D2.5 ✅ shipped** loader-backed shape/structure creation and discovery; **D2.6 ✅ shipped** `get_geometry`, absolute positioning, and polygon/polyline vertex writes. The #353–#355 hardening package adds same-scene load cleanup, fail-closed delete, MCP history, bounded callout input, and a median performance guard. All scene writes remain behind the same ADR-036 double gate. |
| **D3** | Domain-intelligence tools + guided write prompts (companion-aware placement, succession, calendar/tasks, soil amendment planning) |

### US table (D1 = MVP; D2 = write slices)

> D2.0 (token gate + `move_object`/`delete_object`) is described in the phasing
> table above and in ADR-036; every later slice carries its own row here.

| Status | US | Description |
| ------ | -- | ----------- |
| ✅ | D1.1 | **Embedded MCP server core** (spike) — streamable-HTTP server on `127.0.0.1:<port>` on a background asyncio thread; **on by default (read-only)**, Settings toggle to disable; `MainThreadBridge` marshaling boundary; `get_plan_summary` tracer tool; `mcp`/`uvicorn` bundled into the exe (frozen-server verified). See ADR-033/034, FR-26, §8.19. *(PR #239)* |
| ✅ | D1.2 | **Read/query tools** (v1.22.0, PR #241) — `list_objects`/`get_object` (UUID-addressed, curated schema + `raw=True`), spatial queries (`objects_in_region`, `objects_in`, `plants_in_bed`, `nearest_objects`, `measure_distance`), `get_diagnostics` (companion/spacing/soil/capacity/crop-rotation, reads already-computed warnings). Qt-free `queries.py`/`diagnostics.py` over `snapshot_dict`; `AgentProviders` bundle. No FILE_VERSION change. See ADR-034 addendum, §8.19, FR-AGENT-06/07/08. |
| ✅ | D1.3 | **Vision tool** (v1.23.0, PR #242) — `render_canvas_image(x?, y?, width?, height?, layers?, image_width_px?)` returns a PNG of the live canvas + `RenderMeta`, reusing `services/scene_rendering.render_scene_region` (the same pipeline `ExportService.export_to_png`/the PDF report already use). New Qt-touching `agent_api/render.py`; `resolve_image_pixel_size` double-clamps width + derived height to `[128, 2048]`; `AgentProviders.render` is the first parametrized provider (one atomic main-thread hop). Two facts empirically verified against mcp 1.28.1: `Image` isn't pydantic-representable (`@mcp.tool(structured_output=False)` required, plus `Image` must be a genuine top-level import in `server.py`, not function-local) and `render_scene_region`'s `y_flip=True` inverts the rendered pixel Y-axis relative to D1.2's scene frame (correction formula on `RenderMeta.px_per_cm`). **Manual-test fix:** `layers` was originally subtractive-only — a layer the user had toggled off live stayed invisible even when explicitly requested; `_hidden_layers_not_in` now forces the full requested visibility set and restores the original state afterward. Independent review: no P0/P1s, three P2 nits addressed. No FILE_VERSION change. See ADR-034 addendum, §8.19, FR-AGENT-09. |
| ✅ | D1.4 | **Export/save tools** (v1.24.0, PR #243) — `save_plan(file_path?)`, `export_pdf(file_path?, paper_size?, orientation?)`, `export_dxf(file_path?)`, `export_csv(kind, file_path?)`, the first Agent API tools with a filesystem side effect — each calls the exact same service the GUI's File > Export/Save menu already uses, no new export logic. New `agent_api/exports.py`: `resolve_export_path` reuses the `app/paths.py` #199/#204 safe-path chokepoint when no path is given, else force-applies the suffix and requires the parent directory already exist. `save_plan` with no path and no project open raises rather than inventing a filename; given a path it becomes the project's file going forward, mirroring `application._save_to_file` exactly (incl. the issue-#178 stale shopping-list-price prune). No token auth needed — none of the four can make an edit an agent isn't otherwise capable of. Independent review found two P1s (both fixed): `previous_file_path` returning the literal string `"None"` instead of JSON `null` on a first save-as, and `paper_size`/`orientation` not being `Literal`-typed. **Bonus fix found while verifying the frozen exe:** `installer/ogp.spec` excluded `"unittest"`, silently breaking DXF export/import in any freshly-built exe (`ezdxf` → `pyparsing.testing` → `unittest` at import time) — not just this PR's `export_dxf`. Real-world dogfood test (an independent Claude instance driving the live MCP server) confirmed all four tools end-to-end. No FILE_VERSION change. See ADR-034 addendum, §8.19, FR-AGENT-10. |
| ✅ | D1.5 | **Resources + prompts** (issue #249) — 5 read-only resources: `garden://plan` (curated `PlanSummary`), `garden://plan/raw` (uncurated snapshot dict), `garden://canvas.png` (full-canvas PNG, no region/layer args), `garden://diagnostics`, `garden://species` (bundled species DB, 118 records — no `AgentProviders` field needed, `services/bundled_species_db.py` is Qt-free); 2 read-analysis prompts: `audit-plan`, `describe-garden` (new Qt-free `agent_api/prompts.py`, pure text builders over the existing schema types). Almost entirely registration/wiring over D1.1–D1.4's existing building blocks. Verified directly against the installed `mcp==1.28.1` source (not assumed): resources need none of the tool-only `Image`/`structured_output=False` workaround — a `bytes` return + `mime_type="image/png"` on `@mcp.resource()` produces a `BlobResourceContents` automatically, and non-str/bytes returns (pydantic models, dicts, lists) auto-serialize via `pydantic_core.to_json`. No `FILE_VERSION` change. See ADR-034 addendum, §8.19, FR-AGENT-11. |
| ✅ | D1.6 | **AI client onboarding** (issue #240) — in-app "Connect your AI assistant" helper, reached from Help → "Connect AI Assistant…" and Preferences → Agent API: shows/copies the connect URL, **detects installed clients** by their known config locations, and one-click registers the server where each client's own docs support a safe automatic path — **Cursor** (direct JSON merge into `~/.cursor/mcp.json`), **Claude Code** (`claude mcp add --transport http --scope user` CLI, preferred over hand-editing `~/.claude.json`'s nested schema). **Claude Desktop is detection-only** (verified against `modelcontextprotocol.io`'s own docs: its local config only documents stdio servers; a plain local HTTP endpoint is registered through the app's own Settings → Connectors → "Add custom connector" UI, not a config file — auto-writing a guessed schema, or reaching for the `mcp-remote` npm bridge workaround, was rejected as unnecessary risk). Every client, detected or not, also gets a copy-paste snippet + a short "where to put this" note. New Qt-free `services/ai_client_onboarding.py` introduces this codebase's **first atomic-write pattern** (temp file + `os.replace`, backup-before-overwrite, preserves every other key/server) since every prior JSON writer here only ever wrote its own file. Three senior-review rounds: round 1 caught an unguarded `subprocess.TimeoutExpired`/`OSError` from the Claude Code CLI call reaching the Qt slot uncaught; round 2 caught the resulting install having zero visual feedback despite up to ~45s of blocking CLI calls (added a WaitCursor + button-disable, mirroring `preferences_dialog._test_api`'s existing precedent for a blocking call); round 3 caught the deeper bug those two obscured — the Preferences entry point derived its connect URL from settings/widget state rather than asking whether the server was actually **running**, so a saved-but-dead port (e.g. a `PortInUseError` at launch) would have been silently registered as if it worked. Fixed by adding one shared `GardenPlannerApp.agent_api_running_url()` accessor both the Help menu and Preferences entry points now call — the only source of truth is "is the server actually up," never a reconstruction. No token auth needed (registering a client isn't scene-mutating); no `FILE_VERSION` change. See ADR-035, §8.19, FR-AGENT-12. |
| ✅ | D2.1 | **Agent object creation** (v1.26.3, PR [#290](https://github.com/cofade/open-garden-planner/pull/290)) — `create_object(object_type, x, y, width?, height?, radius?, name?, species?)` behind the D2.0 double gate. Slice scope = plants (`TREE`/`SHRUB`/`PERENNIAL`, radius optional → the gallery-drop defaults 100/50/30 cm) + soil containers (`GARDEN_BED`/`RAISED_BED`/`CONTAINER`/`WALL_PLANTER` rectangular, `CONTAINER_ROUND` round, radius required). Coordinates are **centres** in the read tools' own Y-up frame; the rectangle centre→anchor conversion (`anchor = centre − extent/2`) is frame-agnostic by construction. Items are built by the loader's own `_deserialize_item_core`, so there is no second construction path to drift from the serializer. Mirrors the GUI gallery-drop orchestration in full: bundled-species auto-populate, the US-E8 planting-date stamp on **every** new plant (species or not), and active-layer assignment. **Investigation finding:** the initial design assumed the GUI never links a dropped plant to its bed and planned an explicit reconcile — a probe of the real path disproved it. `CreateItemCommand.execute` already calls `_auto_parent_plant` (and `undo` calls `_detach_from_parent`), so the bed link rides *inside* the one create step; the reconcile was removed as dead code and `create_object` is **always exactly one undo step** (unlike `move_object`, whose `MoveItemsCommand` has no such hook). Refuses (leaving scene + undo stack untouched) on an out-of-slice type, a dimension that doesn't fit the shape, a missing/zero/negative extent, a non-finite number, or a locked active layer. New Qt-free `agent_api/creates.py` (validation + `.ogp`-dict building) with drift guards on its inlined `ObjectType` name sets. No `FILE_VERSION` change. See ADR-036 (D2.1 addendum), FR-AGENT-14. |
| ✅ | D2.2 | **Agent resize + rotate, and the canonical geometry-apply path** (PR [#335](https://github.com/cofade/open-garden-planner/pull/335), issue [#326](https://github.com/cofade/open-garden-planner/issues/326)) — `resize_object(item_id, width?, height?, radius?)` (absolute target dimensions in cm; **the object's scene centre is preserved for every type**) and `rotate_object(item_id, angle, relative?)` (degrees, **positive = counter-clockwise**, absolute by default, normalised to `[0, 360)`) behind the D2.0 double gate. The load-bearing half is the extraction: `ResizeItemCommand`/`RotateItemCommand` take a caller-supplied `apply_func`, so every call site had its own closure — the panel's three numeric-entry branches plus a drag-release handler per item class — and adding the agent would have made another. New `ui/canvas/geometry_apply.py` is now the single apply path for every **rect-backed** resize, with the two anchor policies as one parameter and `pos` solved through `resize_handle.anchored_position`/`scene_point_of` (the transform pair extracted from #218's `resize_rect_item_keeping_anchor` so the mutating primitive and the undo-record builders share one formula). `apply_rotation` now has exactly **one** definition in the codebase, drift-guarded. The authoritative list of callers — and of the two deliberate exceptions — is that module's own docstring, stated **there only**: during review five paraphrases of it drifted into three inconsistent answers, which is the very failure the extraction exists to prevent. **The extraction exposed three live GUI bugs, none of them introduced here**, all invisible at rotation 0 and all growing with angle: the panel's copies never re-pinned `transformOriginPoint` (**73.2 cm** displacement for a 30° / 50→100 cm case); `_move_corner_to` had the same omission (**331 cm** between the stored and visible centres); and the EQUAL-constraint partner appliers solved for `pos` as if unrotated (**70.7 cm** at 90°). Senior review caught the last two — and caught that the first fix for the corner drag was a *swap*, trading the save-time bug for a 671 cm interaction bug, because it re-pinned the origin without re-deriving the `pos` that depended on it. The rotation sign was **measured against a real item, then documented, then pinned** against a corner position (never the stored angle) — the #267 lesson applied prospectively. Refuses vertex-backed objects by name (polygons/polylines — vertex editing is US-D2.6), plus D2.0's constrained/pin/group/locked-layer list via a new shared `_agent_require_unconstrained`. Qt-free validation in `agent_api/edits.py` with drift guards. One undo step each. No `FILE_VERSION` change. See ADR-036 (D2.2 addendum), FR-AGENT-15, §8.19, §11.4. |
| ✅ | D2.3 | **Agent species assignment + explicit bed reparenting** (PR [#335](https://github.com/cofade/open-garden-planner/pull/335), issue [#327](https://github.com/cofade/open-garden-planner/issues/327)) — `set_species(item_id, species?, apply_database_size?)` and `set_parent_bed(item_id, bed_id?)` behind the same gate, closing the two gaps that only existed for objects that already exist. `set_species` resolves the name against the bundled DB through the same resolver `create_object` uses and delegates to **`ui/plant_species_assignment.apply_species_to_item`** — the #213 helper the plant panel and species search already share — so the agent is a third *caller*, not a third implementation. **The issue's premise about `apply_database_size` was wrong and the code corrected it**: the app always adopts the species' `max_spread_cm` footprint silently, asking only when a manual spacing override conflicts, so the flag defaults to **`True`** and is the agent's answer to that dialog rather than a "don't resize" switch — defaulting it to `False` as specified would have made the agent behave differently from the GUI on the common path. The D2.1 asymmetry (creation sizes from the fixed 100/50/30 cm defaults because `radius` is an explicit parameter a species must not overrule; the GUI's gallery drop sizes a *named* species from `max_spread_cm`) is **decided and documented**, with `create_object` → `set_species` as the stated two-step for database sizing. `set_parent_bed` is a link change only — the plant does not move — reaching the one state `move_object` cannot: a plant already inside a bed drawn around it. It deliberately does **not** require geometric containment (neither does the app's Link action) and reports `link_is_geometric` instead. `TRELLIS` is accepted as a plant parent though it is not a soil container (§8.14/ADR-017); a `HOUSE` is refused by name with the valid options listed. Undo restores the plant's original z. One undo step each. No `FILE_VERSION` change. See ADR-036 (D2.3 addendum), FR-AGENT-16, §8.19. |
| ✅ | D2.4 | **Layer tools** (v1.27.8, PR [#352](https://github.com/cofade/open-garden-planner/pull/352), issue [#328](https://github.com/cofade/open-garden-planner/issues/328)) — curated UUID-addressed `Layer` records and `list_layers`; `set_object_layer`, `create_layer`, `rename_layer`, `delete_layer`, `set_active_layer`, and visibility/opacity writes reuse the existing layer commands and one-undo contract. **Layer locking is agent-writable in both directions since issue #365** — a deliberate policy reversal of the original decision, recorded as such rather than as a bug: `set_layer_property(layer_id, locked=...)` locks and unlocks through the same `SetLayerPropertyCommand` the Layers panel uses. The *object-level* protection is unchanged and still tests the layer's current lock state, so agents still may not delete a locked layer, move objects onto it, or edit its objects; "unlock, then edit" is simply two ordinary undoable calls. `set_active_layer` is session state and has no undo step. See ADR-034/036 addenda, FR-AGENT-17, §8.19. |
| ✅ | D2.5 | **`create_object` for shapes & structures** (v1.27.8, PR [#352](https://github.com/cofade/open-garden-planner/pull/352), issue [#329](https://github.com/cofade/open-garden-planner/issues/329)) — loader-backed circle, rectangle, ellipse, polygon, polyline, and callout families with native Y-up vertices, a machine-readable `list_creatable_types` roster, and a full `ObjectType` drift guard. `HOUSE` creates its linked `ROOF_RIDGE` in one undo step; direct ridge, journal-pin, generic-text, and legacy hedge-section creation are explicit refusals under the approved contract recorded in the issue-237 implementation session. See ADR-036, FR-AGENT-18, §8.19. |
| ✅ | D2-H1 | **Live MCP QA hardening** ([#353](https://github.com/cofade/open-garden-planner/issues/353)) — shipped in v1.27.10 via PR #360: same-scene load removes every serialized document item so layer counts and object enumeration agree; duplicate UUIDs fail closed; concurrent deletes are deterministic; authenticated `undo`/`redo` operate one command at a time on the global GUI stack. Covered by real-client integration tests. |
| ✅ | D2-H2 | **Bounded callout input** ([#355](https://github.com/cofade/open-garden-planner/issues/355)) — shipped in v1.27.10 via PR #360: signed offsets are finite and canvas-relative (`abs(offset) <= 2 * max(canvas_width, canvas_height)`) before Qt construction; explicit null/non-finite/oversized input leaves scene and history untouched. Covered through the real MCP transport. |
| ✅ | D2-H3 | **CI performance calibration** ([#354](https://github.com/cofade/open-garden-planner/issues/354)) — shipped in v1.27.10 via PR #360: spatial-index test uses warm-up plus repeated median samples (200 ms build / 1 ms query) instead of one noisy wall-clock sample; no spatial-index implementation change. Isolated in its own test/CI commit. |
| ✅ | D2-H4 | **Document lifecycle + layer-lock reversal** ([#365](https://github.com/cofade/open-garden-planner/issues/365)) — `new_plan(width_cm?, height_cm?, force?)` and `open_plan(file_path, force?)`, so an agent is not limited to whatever plan the user happens to have open. Both are **token-gated like `delete_object`** — not merely because they mutate, but because they can discard unsaved work — and both reuse the GUI's own paths (`_on_new_project` extracted into `_new_project_document`; `_open_project_file` split into a raising `_load_project_file` plus its modal-reporting GUI wrapper, so an agent never gets a `QMessageBox` on its behalf). Each refuses on a dirty plan unless `force=true`, because the GUI asks the user there and an agent cannot. `new_plan` refuses an out-of-range canvas rather than clamping it. Plus the **layer-lock policy reversal**: `set_layer_property(locked=...)` now works both ways, with the object-level guards deliberately left absolute. See ADR-034 addendum, FR-AGENT-22, §8.19. |
| ✅ | D1.6a | **Generalized client onboarding** ([#366](https://github.com/cofade/open-garden-planner/issues/366)) — clients become **registry data** rather than `if`/`elif` branches: one frozen `ClientTarget` per client, with `container_key` (`mcpServers` / `mcp_servers` / the nested `mcp.servers`), `syntax` (`json` / `jsonc` / `toml`) and `entry`/`cli_argv` as independent fields, so the dialog gained three new clients (**OpenCode, Codex, Gemini CLI**) with **no UI change**. Backup / atomic-replace / fail-closed / foreign-key preservation now exist once, keyed on syntax. **TOML is appended surgically** (`tomllib` reads, one table's line span is rewritten) because a full re-serialise would destroy the user's own comments in a file OGP does not own — **no new dependency**. **The read-only connect URL is the default hand-out**, closing a real leak: the single "Copy URL" button used to copy the *write-enabled* URL, so the default thing a user pasted into a chat was a live credential. Clients also report **detected / registered / stale**, so a rotated token or changed port surfaces instead of silently failing. See ADR-035 addendum, FR-AGENT-12a. |

| ✅ | D2.7 | **History introspection** ([#362](https://github.com/cofade/open-garden-planner/issues/362)) — unauthenticated read-only `get_history` reports `undo_depth` / `redo_depth` / `next_undo_text` / `next_redo_text` from the same global LIFO stack Ctrl+Z mutates, and never mutates it. This makes two of D2's core invariants machine-checkable with no human reading a menu: "one call = one undo step" (including the documented two-step reparent case) and "a refusal leaves the scene **and** the stack untouched" — previously a write that pushed a command while leaving the scene byte-identical passed every available check. Qt-free (`agent_api/history.py`, behind a Protocol); read-only, no token-gate change, no `FILE_VERSION` change. See FR-AGENT-24, §8.19. |
| ✅ | D2.6 | **Low-level geometry escape hatches** ([#330](https://github.com/cofade/open-garden-planner/issues/330)) — unauthenticated `get_geometry` reports the stable live scene-frame geometry and every referencing constraint; token-gated `set_object_position`, `set_vertex`, `add_vertex`, and `delete_vertex` provide absolute placement and polygon/polyline topology edits. Each actual vertex mutation is one canonical command/undo step; an unchanged request is refused as a no-op rather than adding an empty undo entry, and scene/local conversion reuses the exact current point so inverse-transform noise cannot look like a mutation; minimum 3/2-vertex shapes are enforced by the item protocol. The constraint decision is permanent refusal, made legible by `get_geometry` rather than silently skipping the live multi-item solver. No `FILE_VERSION` change. See ADR-036 D2.6 addendum, FR-AGENT-21, §8.19. |
| ✅ | D3.1 | **Companion tools** ([#319](https://github.com/cofade/open-garden-planner/issues/319)) — unauthenticated read-only `suggest_companions` / `find_compatible_sets` / `check_placement` + the `plan-polyculture-bed` prompt, plus a Companion-panel "Suggest a compatible set…" action. Sets are maximal Bron–Kerbosch cliques over the beneficial companion graph with antagonist pairs as hard exclusions; `size` is a floor, output deterministic, candidates capped at 60 and results at 50. **The panel and the prompt do not pass the bed as `must_include`** — that is measurably wrong (0 sets for 91% of two-plant and 100% of three-plant beds), because Bron–Kerbosch emits only maximal cliques, so `find_sets_for_bed()` instead ranks sets by how much of the bed they keep and names the plants that clash. `check_placement` resolves the bed itself and reports `unknown_bed` rather than a clean-looking `neutral`; spacing/soil are `null` (use `get_diagnostics`). No token, no `FILE_VERSION` change. See ADR-045, FR-AGENT-23, §8.19. |
| ✅ | D3.2 | **Succession tools** ([#331](https://github.com/cofade/open-garden-planner/issues/331)) - unauthenticated read-only `get_succession_plan` / `find_succession_gaps` / `suggest_succession` plus the token-gated `set_succession_plan`, and the `plan-succession` prompt. **First agent write into `ProjectData` rather than the scene graph**, so it has no geometry, no badge and no `geometry_apply.py`: the canvas refresh comes from the already-wired `succession_plans_changed` signal chain rather than a duplicated call, and the refusal contract matters MORE because a half-applied write would corrupt a *stored* plan with nothing on screen to reveal it. Four corrections to the issue's own spec shipped with it: there are **four** season segments (`early_spring`/`late_spring`/`summer`/`fall`), not the three the issue described; the no-location month-based fallback was **extracted** from the succession dialog into `models/succession.py` so the GUI and an agent cannot disagree about what "summer" means; bed resolution uses `is_bed_type`, so a TRELLIS is refused where `check_placement`'s looser `is_plant_parent_type` would accept it; and the within-plan rotation rule is genuinely new logic, because `CropRotationService.check_plant_placement` only compares against `records[0]` and succession entries never enter rotation history at all (the cross-year cooldown IS reused verbatim). `fits_window` deliberately reports "too slow" and "maturity unknown" alike, distinguishable via `days_to_maturity`; a too-slow candidate is returned ranked last, never dropped. No token, no `FILE_VERSION` change. See ADR-034/036 addenda, FR-AGENT-25, §8.19. |
| ✅ | D3.3 | **Calendar & task tools** ([#332](https://github.com/cofade/open-garden-planner/issues/332)) — **Shipped v1.29.1 via PR #382.** unauthenticated read-only `get_tasks` / `get_task_calendar`, token-gated `add_manual_task` / `edit_manual_task` / `delete_manual_task`, and the `plan-my-week` prompt. **The whole seven-generator task engine becomes agent-reachable for the first time**, answering "what should I do this week?". Each task carries the generator's own fields plus the render-time `urgency` (from `classify_urgency`, never re-implemented) and the `status` from the shared store the Tasks tab reads. **Carries the D3 localisation decision**, stated once for both D3 stories: machine keys (`task_id`/`task_type`/`source`) are stable English; `title`/`notes` are display strings in the user's UI language. Three corrections to the issue's own spec implemented with it: `Task.source` has **six** values for seven generators (both soil generators emit `soil`, so `task_type` carries the distinction `source` cannot); `build_plan_state` needed a `today` parameter to make the answer reproducible at all, since only it called `date.today()`; and **agent task-status mutation is refused** — `set_task_status` is not a command, so exposing it would make it the one agent write a single Ctrl+Z cannot reverse. Generated tasks are refused by name on edit/delete (derived state, rebuilt every read). `source`/`status` hiding matches `tasks_view` exactly (`archived` + `dismissed`), so the agent is not a third surface disagreeing with the other two. No `FILE_VERSION` change. See ADR-034/036 addenda, FR-AGENT-27, §8.19. |
| ✅ | D3.4 | **Soil amendment tools** ([#333](https://github.com/cofade/open-garden-planner/issues/333)) — **Shipped v1.29.1 via PR #382.** unauthenticated read-only `get_soil_status` / `recommend_amendments` / `get_soil_mismatches`, token-gated `record_soil_test`, and the `plan-soil-amendments` prompt. **Not a pure wrapper, and the issue said the wrong thing about localisation.** The issue attributed the problem to amendment *names*; those are bilingual *data* (`Amendment.name`/`name_de`) with a stable `id`, so the real gap was narrower and sharper: `get_mismatched_plants`' reason sentences were `translate`-only prose with **no machine key**. That is now one canonical `(reason_code, display_text)` builder with `get_mismatched_plants` as a projection, so both in-app callers are untouched. Three further corrections: the issue's `nitrogen`/`phosphorus`/`potassium` parameters are named `n_level`/`p_level`/`k_level` after the model (a name that states its scale is the cheapest guard), and the secondaries it omitted entirely are added because `_NUTRIENT_KINDS` reasons over all six; the ranges are **per-nutrient** (`k_level` is `1–4`, the kit has no K0; secondaries `0–2`), so one shared range check would be wrong; and **lab ppm is refused by name** because nothing in `services/` reads `*_ppm` and no conversion exists (US-12.10c), so a ppm-only record would report UNKNOWN health while looking complete. Also: `health_level` rates pH/N/P/K only and returns the **overall** rating for an unrecognised parameter, so a secondary reports `health_level: null` (no rating exists) rather than the bed's health mislabelled as calcium's; and `record_source` (`bed`/`global`/`none`) is reported because `get_effective_record` applies its hierarchy invisibly. No `FILE_VERSION` change. See ADR-034/036 addenda, FR-AGENT-28, §8.19. |

D3.3/D3.4 verification includes actual MCP-client calls against the production
provider graph and the frozen app. Review corrected soil response envelopes,
full-year/cross-year task generation, missing propagation, global-record
staleness, German amendment display names and numeric input coercion. See
PF-API-21. The complete write-enabled surface is 57 tools, 5 resources and
6 prompts. Owner approved release after plan/PR review and agent-driven live QA.
The preexisting German amendment-task naming gap is tracked in #408.

### Acceptance highlights (D2.0–D2.6)
- The writes-enabled toggle and bearer token are independent gates: write tools disappear when either is absent, and every call rechecks the token before the Qt hop. Reads remain open.
- Every agent document mutation uses the GUI's command path and remains undoable; `undo()`/`redo()` operate the same global LIFO stack one command at a time and refuse empty stacks.
- `create_object` builds through the loader, preserves the native Y-up frame, and refuses hostile or implausible geometry before Qt sees it; refusals leave the scene and undo stack unchanged.
- `get_geometry` is the stable low-level read: polygon/polyline points are mapped from the **live** Qt transform, curve/extent/radius data is curated rather than exposing serializer internals, and constraints are returned in deterministic order even though writes on those objects refuse.
- `set_object_position` derives a delta and enters the same move orchestration as `move_object`, including logical bed children and plant reparenting. Vertex writes share the GUI's canonical command builders; set/add/delete each add exactly one undo entry and restore the prior list.
- Same-scene save/load has one document-item cleanup predicate; `list_layers.object_count` agrees with the top-level `list_objects` roster, including callouts and Arc/Bezier items.
- Real MCP integration tests cover authentication, geometry frame agreement and no-op refusal, constrained refusals, concurrent delete behavior, global history, save/load, rendering, and adversarial callout offsets; the performance benchmark is reported as repeated medians rather than a single sample.

### Acceptance highlights (D1)
- Server is **on by default (read-only)**, binds **loopback only**, and shows the connect URL (e.g. `http://127.0.0.1:8765/mcp`); a Preferences toggle disables it and stops it cleanly. Getting that URL into each user's AI client is the D1.6 onboarding dialog.
- All Qt-touching work (scene snapshot, render, export, save) is **marshaled onto the main thread** from the server's asyncio thread; the `agent_api` core is otherwise Qt-free and unit-testable.
- Reads return the **curated agent schema** (stable, documented Pydantic models) by default; `raw=True` returns the serializer dict. No `FILE_VERSION` change.
- Objects are addressed by **stable UUID** (`item_id`); every list/query returns ids.
- `render_canvas_image` reuses `render_scene_region` (overlay-hiding / Y-flip / text-scaling already handled).
- **Integration test** boots the embedded server in-process and exercises tools end-to-end over an MCP client; **PyInstaller** build bundles `mcp` + `uvicorn`/`starlette`/`anyio` (hidden imports) and the exe smoke-test confirms the server starts.
- MCP **tool/resource/prompt descriptions are English** (an API contract for agents, not UI) — exempt from i18n; only the **Settings UI** strings go through `tr()`.

### Risks / open questions
- **PyInstaller bundling** of the MCP/uvicorn/starlette stack (hidden imports, `anyio` backends) — validate early in D1.1.
- Running an asyncio/uvicorn loop **alongside the Qt event loop** without blocking the UI — a background thread owns the loop; never call Qt from it directly.
- **Port conflicts** — configurable port + a clear error if the port is taken.
- **Loopback trust** — read tools remain open to local clients by design; all D2 scene-mutating tools are behind the writes-enabled setting and bearer token, with `undo`/`redo` covered by the same gate.

### Docs to update on completion
| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-033 Agent Integration Architecture, ADR-034 Curated Agent Schema, ADR-036 write gate, and the #353/#355/#330 addenda |
| `docs/05-building-block-view/` | `agent_api/` server/provider/schema/edits blocks, live geometry inspector, canonical vertex builders, load cleanup, and history wiring |
| `docs/06-runtime-view/` | agent read/write/geometry/history sequence (asyncio thread → main-thread marshal → command/reply) |
| `docs/08-crosscutting-concepts/` | §8.19 Agent API & thread marshaling, including global history, load cleanup, bounded callout input, and D2.6 geometry |
| `docs/07-deployment-view/` | PyInstaller hidden-imports for `mcp`/`uvicorn`/`starlette` |
| `docs/functional-requirements.md` | FR-26 / FR-AGENT-19/20/21 and FR-SNAP-06 |
| `docs/12-glossary/` | MCP, MCP tool/resource/prompt, Agent API, curated schema, marshaling boundary, loopback, Agent write tool, geometry escape hatch |

---

## Package F — Permaculture & Polyculture (✅ 5 of 5 shipped — Complete)

> Filed from the permapeople.org research session (2026-08-17). Membership and
> order live in the `> Package map & order` blockquote at the head of each issue,
> which is the most current statement of the package's shape. **GitHub outranks
> this table.**
>
> | Status | US | Description |
> | ------ | -- | ----------- |
> | ✅ v1.30.0 | **F1** ([#312](https://github.com/cofade/open-garden-planner/issues/312)) | **Permaculture layer + plant function tags** — foundation of the package, **do first**. `PermacultureLayer` (7 food-forest layers + `UNKNOWN`) and `PlantFunction` (12 functions) as additive species attributes, captured from Permapeople's `Layer`/`Uses`, filled for all 118 bundled records, editable in Plant Details, filterable in search/gallery, exposed in the curated agent schema. Plus an optional food-forest canvas-layer preset. ADR-054/055 and FR-32. |
> | ✅ v1.30.0 | **F2** ([#313](https://github.com/cofade/open-garden-planner/issues/313)) | **Plant guilds** — guild templates, canvas membership, missing-role diagnostic. *Depends on F1*: guilds have nothing to reason on without layer/function tags. |
> | ✅ v1.30.1 | **F3** ([#314](https://github.com/cofade/open-garden-planner/issues/314)) | **Sun-requirement × computed hours-of-sun diagnostic** + canvas badge. Shipped with #428 via PR #436 after owner acceptance (ADR-056): explicit cached exposure, self-shadow exclusion, unavailable states and mature-canopy groups. *Independent*; its layer-stack section follows F1. Builds on the shipped Phase 14 sun/shade engine. |
> | ✅ v1.30.17, PR #533 | **F4** ([#315](https://github.com/cofade/open-garden-planner/issues/315)) | **Plan timeline scrubber** — `removal_date` + plan-state-at-date visibility on the shared sim date. *Independent.* |
> | ✅ v1.33.0, PR #610 | **F5** ([#316](https://github.com/cofade/open-garden-planner/issues/316)) | Offline example gallery and portable templates; includes #379 fixture retirement. Owner accepted the revised executable; shipped in v1.33.0 via PR #610 (ADR-066). |

## Package G — Plant Data Quality & Attribution (✅ 4 of 4 shipped — Complete)

> Same research session as Package F. G1–G3 shipped in v1.28.1 (PR #368). G4 shipped via #320.

| Status | US | Description |
| ------ | -- | ----------- |
| ✅ | **G1** ([#311](https://github.com/cofade/open-garden-planner/issues/311)) | **Licence + attribution** for all bundled data files, a "Data Sources & Licenses" section in About, and a licence line in Plant Details. Shipped v1.28.1 — closed the CC BY-SA compliance gap. **First in the package.** |
| ✅ | **G2** ([#317](https://github.com/cofade/open-garden-planner/issues/317)) | **Plant profile header** — thumbnail, description, external links (Wikipedia/PFAF/POWO), off-thread fetch with disk caching. *Independent.* Shipped v1.28.1. |
| ✅ | **G3** ([#318](https://github.com/cofade/open-garden-planner/issues/318)) | **Permapeople companions** — `get_companions()` with pagination, local cache, three-tier companion service (bundled → custom → provider). Shipped v1.28.1. New settings: `plants/download_images`, `plants/fetch_companion_data`. |
| ✅ | **G4** ([#320](https://github.com/cofade/open-garden-planner/issues/320)) | **Plant favourites & named collections** — a Plant Lists panel with drag-to-canvas, JSON import/export, and Agent API resource `garden://plant-lists` (FR-8). Completes Package G. |

## Phase 14: 3D Visualization & Sun/Shade ✅ Complete (v1.24.5 – v1.24.12 — epic #255)

**Goal**: Full three-dimensional garden view with sun/shade simulation — the milestone that was planned to justify a major version bump.

> **Decision (2026-07-31): there is no v2.0 — the "v2.0 milestone" framing is retired.**
> US-E1…E9 all shipped and [epic #255](https://github.com/cofade/open-garden-planner/issues/255)
> is closed, but every PR merged under the CI default (**patch**), so the milestone landed across
> **v1.24.5 – v1.24.12** and the line moved on to v1.26.2. Reviewed at completion and
> **deliberately not back-filled with a major bump**: the 3D view is not (yet) prominent enough
> in day-to-day use to carry a major-version claim. Versioning stays continuous and CI-driven;
> a future major bump, if there is one, will be earned by something else. Phase-14 scope
> exclusions previously labelled "v2.0" are labelled **Phase 14** throughout the docs.

- 3D visualization (engine decided by the US-E5 spike — **outcome: GO on PyQt6-3D**; PyVista rejected at +466 MB, pyqtgraph.opengl rejected for no directional-light/FPS-camera control. ADR-038)
- Object height properties (walls, fences, trees, structures)
- Sun path simulation (shade calculation by season, time-of-day animation, seasonal analysis)
- First-person walkthrough mode
- Plant growth over time visualization (seedling → mature)

**Planned 2026-07-19 — epic [#255](https://github.com/cofade/open-garden-planner/issues/255).** Each US carries a full stand-alone implementation spec in its issue; the authoritative runbook is the `ogp-3d-sunshade-campaign` skill (load it plus `ogp-change-control` + `ogp-architecture-contract` before starting any US). Slice order is deliberately 2D-first: the sun/shade value (US-E1…E4) ships even if the 3D spike NO-GOs.

| Status | US    | Description                                                        | Issue | Depends on |
| ------ | ----- | ------------------------------------------------------------------ | ----- | ---------- |
| ✅     | US-E1 | Solar position engine — Qt-free `core/solar.py` (NOAA/Meeus, math copied verbatim from the campaign oracle; pinned tests ±0.05° vs oracle + Meeus Example 25.a literature row + physical identities). See ADR-037, FR-SUN-01 | [#256](https://github.com/cofade/open-garden-planner/issues/256) | — |
| ✅     | US-E2 | Object height property — additive `object_height_cm` + Qt-free `core/object_height.py` resolver (explicit → container fill → species `max_height_cm` → per-type default → None; type-matching by enum *name* keeps it Qt-free, name sets pinned against the enum) + undoable "Object height:" panel spin (effective value shown, 0 = Auto clears, `ChangePropertyCommand` apply_func — one undo step). No FILE_VERSION bump. See ADR-037, FR-SUN-02 | [#257](https://github.com/cofade/open-garden-planner/issues/257) | — |
| ✅     | US-E3 | 2D analytic shadow overlay + sun date/time control — Qt-free `core/shadow_geometry.py` (`L = h/tan α`, MinkowskiSum sweep probed live + 8-step fallback, one integer-grid union), runtime-only `SunShadowOverlayItem` (z −500, odd-even fill, never serialized, survives `scene.clear()`), debounced recompute (scene.changed + stack_changed, snapshot-key echo guard), `SunSimToolbar` date/time-slider/animate control (local tz, sim time defaults to the current date/time each session), empty states (no-location hint / whole-canvas night shade), overlay clipped to the canvas bounds with a soft feathered edge. Binding pixel test pins the §8.19 render formula — no mirrored shadows. See ADR-037 addendum, FR-SUN-03/04, §8.20 | [#258](https://github.com/cofade/open-garden-planner/issues/258) | E1, E2 |
| ✅     | US-E4 | Hours-of-sun heatmap — Qt-free `core/shade_aggregation.py` (15-min daylight sampling gated α>0 with shadow calls clamped ≥0.5°, bands <2/2–4/4–6/≥6 h, injected rasterizer) + `ui/canvas/sun_heatmap.py` (QImage rasterizer pinned vs point-in-polygon reference + 2-thread smoke test, `_WeatherFetchWorker`-shaped `HeatmapWorker`, runtime-only pixmap overlay z −450, full-sun transparent). Toy-case gates green on a real WALL scene (Dec 21 = 0 min, Jun 21 = 540±15); 60k-cell full-day compute ≪ 1 s (budget 2 s); recompute on demand only; date-change/sim-off clears; `closeEvent` joins the worker. "Hours of Sun" toolbar button + legend. **Redesigned by [#276](https://github.com/cofade/open-garden-planner/issues/276):** the 4 discrete bands + the toolbar swatch legend are replaced by a smooth cool→warm ramp (alpha falls as sun-hours rise, `SmoothTransformation`) with labeled hourly topographic contour lines (even-hour `{n} h`) serving as the self-describing key — new Qt-free `core/heatmap_render.py` (numpy ramp LUT + vectorized marching squares + Chaikin smoothing); the aggregation/worker/toy-case gates are unchanged (display-only, no FILE_VERSION bump). See ADR-037 addendum, FR-SUN-05 | [#259](https://github.com/cofade/open-garden-planner/issues/259) | E3 |
| ✅     | US-E5 | 3D engine spike — **GO: PyQt6-3D** (ADR-038, owner sign-off on the PR). Version-matched 6.11.0 wheel; the one trap: `PyQt6-3D-Qt6` must pin to `PyQt6-Qt6`'s micro (DLL "Prozedur nicht gefunden" otherwise). Decisive frozen-exe gate PASSED: `--spike-3d` in the packaged exe renders lit extruded boxes from a real `.ogp` (screenshot in ADR-038), dist +13 MB (limit +150). PyVista rejected (+466 MB), pyqtgraph.opengl rejected (no directional-light control / no FPS camera). Spike stayed dormant behind the flag (pinned never-imported-at-startup) until US-E6 removed it — the real 3D view supersedes it. §11.1 row closed | [#260](https://github.com/cofade/open-garden-planner/issues/260) | E2 |
| ✅     | US-E6 | 3D view MVP — View → "3D View…": real prism extrusion of the US-E3 footprints × US-E2 heights (Qt-free `core/scene3d.py`: ear-clip triangulation + triangle soup + the pinned light gate (−0.2056, −0.4675, 0.8598) + sun∥shadow agreement invariant), flat decals for height-less items, orbit camera, sun light follows the sim time/location (night → dim overhead). One Qt3D import boundary (`ui/view3d/qt3d_adapter.py`); lazy load pinned by startup test; deps `PyQt6-3D==6.11.0`+`PyQt6-3D-Qt6==6.11.0` land in pyproject per ADR-038. Viewer-only MVP: manual Refresh, lighting-only (no engine shadow maps — stated). **Manual-test fix:** the viewer is recreated per open (a reused hidden→re-shown Qt3DWindow renders white — Qt3D never rebuilds its RHI swapchain), the previous window retired only once hidden/idle, and cleared on app-exit (else a parentless top-level blocks quit) — see §11.4. See ADR-038 addendum, FR-SUN-06 | [#261](https://github.com/cofade/open-garden-planner/issues/261) | E5 GO |
| ✅     | US-E7 | First-person walkthrough — "Walk" toggle in the 3D View (engine `QFirstPersonCameraController`): WASD/arrows + hold-left-mouse look, fixed 165 cm eye height, plan-bounds clamp (+150 cm margin) via Qt-free `core/walk_camera.py` (pitch ±89° — no gimbal flip), Esc exits, orbit camera restored exactly (pinned). Sim-time light stays live while walking. Stated exclusions: no collision, flat ground, fixed eye height. **Manual-test fixes:** horizontal WASD+arrow movement (the engine's first-person controller free-flew along the pitched view vector — now a custom horizontal loop, `linearSpeed 0` look-only) and flat-decal layer-stacking in 3D (height-less items were ground-plane z-fighting — now lifted + stepped up the 2D order). See ADR-038 addendum, FR-SUN-07 | [#262](https://github.com/cofade/open-garden-planner/issues/262) | E6 |
| ✅     | US-E8 | Growth-over-time visualization — Qt-free `core/growth_model.py` (linear **current→mature** over years-to-maturity: species `days_to_maturity` → else tree 10 y / 3 y / annual ≈season). **No new metadata** — reuses the existing `plant_instance` fields (`planting_date`, `current_height_cm`, `current_spread_cm`). Resolver `at_date` param routes measured+dated plants through the model; independently of any date the measured `current_height_cm` now outranks the species max (new `SOURCE_CURRENT` tooltip), and `collect_shadow_casters` mirrors it for the canopy — shadow overlay, heatmap and 3D all pass the sim date, so scrub +5 y and the garden regrows everywhere from one model. New plants get today's `planting_date` stamped at creation (fresh-creation sites only — never on load). Stored geometry never mutated (byte-identical-save pin, #218/#219 scars). **Redesigned after owner manual test**: the first cut interpolated the *species* min→max keyed on the planting date alone — nothing set that date at creation, so every plant fell through to the mature max ("shadow scales only based on max height") while the Plant Details Current height/spread fields drove nothing at all. See ADR-037 growth addendum (redesign note), FR-SUN-08 | [#263](https://github.com/cofade/open-garden-planner/issues/263) | E6 |
| ✅     | US-E9 | *(Optional)* Asset-forge dev tooling — `ogp-asset-forge` skill (house-style contract derived from the shipped set, generation methods with procedural preferred, provenance discipline: no PROVENANCE.md entry → no merge), mechanical tileability gate (`scripts/check_texture_tileability.py`, seam vs 98th-percentile internal-step metric, threshold 1.6, pinned by test incl. a legacy-seam list that may only shrink — audit found real seams in `flagstone.png`/`glass.png`), and two pilot textures generated procedurally (`decking`, `corten` — deterministic seed, wrap-stamped primitives + wrap-blur, `scripts/generate_asset_forge_textures.py`) wired through `FillPattern` + i18n. No runtime/network dependency; external game-assets skill stays rejected | [#264](https://github.com/cofade/open-garden-planner/issues/264) | — (off critical path) |

Reserved identifiers: **ADR-037** (solar + shadow architecture), **ADR-038** (3D engine choice), **§8.20**, **FR-SUN-\***. `FILE_VERSION` stays `"1.4"` (heights/planted-date are additive metadata).

---

## Phase 15 — Visual Refresh (epic thread: #279 → #281)

The app's visuals grew ad-hoc while functionality matured; Phase 15 modernizes them in packages. Decisions locked in the 2026-07-25 planning session: line+accent icon style, theme-tinted at runtime; icons + chrome in one package; plant art completely redesigned as its own package.

| Status | Package | Description | Issue | Shipped |
| ------ | ------- | ----------- | ----- | ------- |
| ✅ | 1 | **Themed iconography + modernized chrome** — 72-icon line set (62 Tabler v3.45.0 vendored MIT + 10 bespoke) on the 24×24 `currentColor`+accent-sentinel contract, rendered only via the runtime-tinting provider `ui/icons.py`; all 5 legacy load paths + ~28 menu actions migrated, `icons/tools/` deleted; normalize/conformance/provenance gates. Chrome: `ui/theme.py` as the single home of chrome colors (semantic tokens, shared `URGENCY_TOKENS`, typography/color/button roles as dynamic properties, live-switch propagation, saturated banners by design), theme-blind surfaces fixed (dark-mode weather cards, popups off the OS palette), QSS-color lint gate (empty allowlist). ADR-039 (+ review addendum), FR-28, §8.4/§8.21, §5.7, two §11.4 pitfalls. Two senior-review rounds. | [#279](https://github.com/cofade/open-garden-planner/issues/279) | ✅ v1.25.0 (PR [#280](https://github.com/cofade/open-garden-planner/pull/280)) |
| ✅ | 2 | **Plant illustration redesign ("Lush Sprite")** — all 123 SVGs generated by `scripts/generate_plant_sprites.py` (13 seeded archetype builders + recipe tables; generator = provenance; byte-determinism gate makes hand edits unlandable). Top-down radial shading, per-leaf gradients + occlusion, dome foreshortening for ball canopies, conifer branch-whorls, clumped grass/fern tufts (two owner manual-test rounds). Gates: QtSvg-subset allowlist walk, element/byte budgets, and the **visual-weight metric** (ink-coverage [0.30, 0.75], spread ≤ 2.0×, 16 px floor) — palette conformance is enforced transitively via byte-determinism (most colors are mix/lighten-derived, so a literal-set check is not implementable). Bonus: `hedge.png` regenerated in the same leaf language (HEDGE_POLYGON fills with the texture, not the sprite), tileability-gated. Four senior-review rounds. ADR-040, §8.22, FR-29. | [#281](https://github.com/cofade/open-garden-planner/issues/281) | v1.26.0 (PR #282) |
| ✅ | 3 | **Scoped 2026-08-17** (decision log on the epic; ADR-042, FR-30) into three sequential PRs — `minor` label on whichever merges last (v1.27.0). **3a — generated object sprites** ([#308](https://github.com/cofade/open-garden-planner/issues/308)): all 15 furniture/infrastructure SVGs regenerated by `scripts/generate_object_sprites.py` in the "Lush Object" style (full parity with the plant sprites, no baked shadow, viewBox = footprint, `--check` determinism + allowlist/budget/visual-weight gates), roster grown by 9 types (sandbox, trampoline, hot tub, swing, picnic table, hammock, wheelbarrow, pergola, bird bath), aspect-preserving gallery thumbnails, square BBQ art, forward-compat pin (no FILE_VERSION bump). **3b — textures** ([#309](https://github.com/cofade/open-garden-planner/issues/309)): all 24 textures regenerated by `scripts/generate_asset_forge_textures.py` — a numpy float64 torus painter (analytic AA primitives, radial shading, occlusion halos, periodic noise, torus Voronoi, in-repo wrap blur), Lush everywhere, pixel-exact `--check` (bytes are a zlib property — §11.4), tint-band + on-canvas seam gates (both axes), the `KNOWN_SEAMED_LEGACY` grandfather list emptied and deleted, legacy Qt generator deleted. **3c — iconography** ([#310](https://github.com/cofade/open-garden-planner/issues/310)): status bar, tabs + frost badge, Plants/Garden + all File/Edit/View residue, layers_panel migration, `lawn.svg`, code→file gate, all emoji pseudo-icons, View menu regrouped into submenus, Tasks/Harvest → Ctrl+4/5. | [#284](https://github.com/cofade/open-garden-planner/issues/284) | 3a: ✅ [PR #322](https://github.com/cofade/open-garden-planner/pull/322) → v1.26.8 · 3b: ✅ [PR #323](https://github.com/cofade/open-garden-planner/pull/323) → v1.26.9 · 3c: ✅ [PR #325](https://github.com/cofade/open-garden-planner/pull/325) → **v1.27.0** (all 2026-08-18; #324 was the original 3c PR, auto-closed when its stacked base merged) |

> **Decision (2026-07-19):** the external `claude-skill-game-assets-enhancer` skill was evaluated for 3D asset generation and rejected — it produces 2D game sprites via a paid fal.ai API, no 3D assets; Phase 14's 3D pipeline is procedural (extruded footprints). The salvageable idea (AI-generated textures through the existing `fill_patterns.py` seam, already sanctioned by §11.1) is captured as optional US-E9. Full rationale in epic #255.

---

## Phase 16: Platform & Community (Future)

**Goal**: Extend the platform with community features, plugins, and cross-platform support.

- Plugin system for extensibility
- Community template sharing / marketplace
- Irrigation planning & drip system design
- Cost estimation & budget tracking (advanced)
- Cross-platform packaging (macOS, Linux)

---

## Phase 17: Living Garden 3D (epic [#383](https://github.com/cofade/open-garden-planner/issues/383)) — L0 complete (GO), L1–L4 complete

**Current product (since v1.30.14, [PR #484](https://github.com/cofade/open-garden-planner/pull/484))**: the 3D view is the Qt Quick 3D workspace in the main window — View → "3D View" shows it beside the plan (Plan / 3D / Split, Alt+1 / 2 / 3); it follows every edit, casts shadow-map shadows checked against the 2D ones, selects in both directions and walks with collision. The Qt 3D viewer window of US-E6 / E7, unreachable since L1.9, was deleted in L1.10 with its two `PyQt6-3D*` pins, the pre-L1.1 scene module and the L0 spike (its values frozen in `tests/data/l0_spike_reference.json`). The workspace also paints the plan's flat surfaces onto its ground (L1.5). What FR-SUN-06 / 07 / 08 promised and what the new view does is §8.29.9's parity table; the owner shipped the default with #532 open (ADR-060 addendum D5). v1.30.13 was the last release with the Qt 3D window. L0 is complete with a GO; L1.0 (one simulation clock) shipped in v1.29.10 and L1.1–L1.10 in v1.30.14.

**Goal**: make the 3D mode the reason to open the app — *Lush Cinematic* look, experience + analyze (editing stays in 2D, 3D only selects), 100 % procedural models, and **truth before beauty** (heights, spreads, sun, shadows, date and north gated against the data). Owner decisions 2026-10-03. Renderer: Qt Quick 3D replacing the deprecated Qt 3D, decided by the ADR-048 GO/NO-GO spike. Every 3D-visible change goes `ogp-3d-creator` → `ogp-3d-reviewer` → `senior-reviewer` (skills `ogp-lush-cinematic`, `ogp-3d-renderer`).

| Status | Package | Description | Issue |
| ------ | ------- | ----------- | ----- |
| ✅ | L0 | **Proof of Beauty** — ADR-048 criteria committed before measuring; deterministic bench plans; dormant `--spike-q3d` renderer with sky, soft shadows, procedural trees/plants/roofs/fences; measurements M1–M12 in the container and the frozen Windows exe; Beauty Board; agents + skills. **GO 2026-10-05 (owner GPU run in ADR-048 entry 19); evidence tooling deleted.** | [#384](https://github.com/cofade/open-garden-planner/issues/384) |
| ✅ | L1 | **New engine, new light** — sim clock, scene contract v2, engine package, Plan/3D/Split workspace without camera resets, sky + presets, ground bake, built world v0, plant v0, selection sync + walk collision, default flip, Qt 3D removal. **L1.0 ✅ sim clock shipped v1.29.10 ([PR #429](https://github.com/cofade/open-garden-planner/pull/429)); L1.1–L1.10 ✅ shipped v1.30.14 ([PR #484](https://github.com/cofade/open-garden-planner/pull/484))** — see below | [#385](https://github.com/cofade/open-garden-planner/issues/385) |
| ✅ | L2 | **Analyze in 3D** — shadow and sun-hours drapes + ground probe, sun path + compass + day sweep, info card v1 + growth jump with before/after, Cutaway / X-ray. **✅ shipped v1.31.0 ([PR #584](https://github.com/cofade/open-garden-planner/pull/584)) after owner acceptance (ADR-063, FR-3D-ANALYZE-01 … 08)** — see below | [#386](https://github.com/cofade/open-garden-planner/issues/386) |
| ✅ | L3 | **Plant Forge** — shipped in v1.32.0 ([PR #593](https://github.com/cofade/open-garden-planner/pull/593)) after owner acceptance (ADR-064, FR-3D-FORGE-01 … 06) — see below | [#387](https://github.com/cofade/open-garden-planner/issues/387) |
| ✅ | L4 | **Built world complete** — roof styles, paths, glass, 24 object builders, water and lawn. **✅ shipped v1.34.0 ([PR #613](https://github.com/cofade/open-garden-planner/pull/613)) after owner acceptance (ADR-065, FR-3D-BUILT-01 … 08)** — see below | [#388](https://github.com/cofade/open-garden-planner/issues/388) |
| 📋 | L5 | **Living garden** — year/day playback, weather, particles, wind (needs [#315](https://github.com/cofade/open-garden-planner/issues/315)) | [#389](https://github.com/cofade/open-garden-planner/issues/389) |
| 📋 | L6 | **Director's cut** — photo mode, camera tours, `render_3d_view` MCP tool | [#390](https://github.com/cofade/open-garden-planner/issues/390) |
| 📋 | L7 | *(optional)* **Sky 6.12** — Qt 6.12 LTS pins, `SkyMaterial` atmosphere and clouds | [#391](https://github.com/cofade/open-garden-planner/issues/391) |

### Test lifecycle, popup focus, release classification, and 3D workspace modularization — **shipped 2026-10-28 as v1.34.2, PR #632**

One package covers #561, #515, #460, #463, #583, and #580 (closing #447).
- **#515 / AUD-019 / #447:** Parented CategoryDropdown to CategoryToolbar, reclaiming 870 leaked widgets per cycle on window close and eliminating native access violations during QApplication.setStyleSheet re-polish.
- **#561:** Suppressed focus-stealing popups during automated test runs via WA_ShowWithoutActivating and WindowDoesNotAcceptFocus.
- **AUD-018:** Documented formal test layer contract and test-suite hygiene in §8.10.
- **AUD-038 / AUD-086 / AUD-090:** Added tag disposition validation in 
elease.yml, documented ADR-050 version derivation evaluation addendum, and enforced check_release_classification.py in CI to differentiate executable changes from chore PRs.
- **#583:** Split ui/view3d/workspace.py from 2,381 to 1,861 lines by extracting selection, walk, analysis, wipe, and legend coordinators with typed protocols (EngineHost, EngineSink, ShadowsSource, HeatmapSource, SunHoursSource).
- **#580:** Expanded info card body line budget (BODY_LINES = 8) to keep all fact rows (including harvest window) visible without vertical clipping at the narrowest 455 px split pane width.
- **#577:** De-scoped for dedicated geometry research; preserved clean ground drape depth occlusion.

### L4 follow-up hardening — **shipped 2026-10-27 as v1.34.1, PR #630**

One PR covers #611, #607, #604, #617, #624, #618, #609, #600, #603, #626
and #536. Context parameters follow both record types; Low/Medium skip lawn
blade synthesis; exact lawn masking avoids the Python edge loop; roof clamps
have one home and tiny objects use verified prisms. Lawn lighting, corner-aware
shadow reach, the far meadow and distant camera probes receive rendered pins.
Translucent path rims exclude their texture's middle. Selection and reload
measurements wait for admitted forged LODs; screen scaling and first-expose
waits are explicit; the memory soak measures after presented uploads retire.
No memory/performance bound is relaxed. Measurements and residual manual checks
are recorded in [the hardening evidence](https://github.com/cofade/open-garden-planner/blob/master/docs/11-risks-and-technical-debt/audits/2026-10/3d-hardening-611.md).

### L4 acceptance highlights — Built world complete (#388, ADR-065) — **shipped v1.34.0, PR #613**

- **L4.1 roofs and facades:** Roof style (Automatic / Gable / Hip / Single slope /
  Flat), pitch (5–60°) and overhang (0–150 cm) are optional, additive item metadata
  edited in the Properties panel, one undo step each, with no FILE_VERSION bump. The
  roof's top stays the building's height. Windows go on walls that can hold them; the
  door faces the nearest path (a garage the driveway), stored as a wall index so a
  move stays transform-only. Roof-aware 2D casters stay with #440.
- **L4.2 surfaces:** Stepping stones (the 2D walk, slid onto the path at its ends),
  boardwalk planks, paving kerbs, gravel edging, terrace and driveway
  kerbs or deck boards, pond water and coping are `ground_detail` relief: drawn on
  the painted ground, no shadow, never picked. Paths are real widths: presets
  70–100 cm, default 80 cm, the panel up to 500 cm (owner comment on #388).
- **L4.3 / L4.4 objects:** All 24 furniture, play, utility and structure kinds have
  bevelled builders in the 2D object palette, bounded at 4,000 triangles. Every
  object kind has a default height and casts in 2D and 3D. Greenhouse glass keeps
  the existing glass material: scene-wide OIT broke L2's drapes (measured).
  Smart-symbol builders are deferred (#599): a smart symbol is a group of items L4 builds.
- **L4.5 water, lawn, detail:** Lawn blades (220 / m², ≤ 36,000 per lawn, ≤ 60,000
  per plan, water-filled by area) are cut out under flat items above the lawn and
  enclosed buildings on it. L4 originally built blades at every preset; the follow-up
  package admits their geometry only from High up. From Medium
  up, `ground.frag` derives detail normals from the baked ground's own luminance; no
  asset. #586: the Beauty Board's shots include the ground bake.
- **Reviews:** `ogp-3d-reviewer` approved in round 3. The endless meadow is a frame in the
  plan's plane, because one 4 km quad under the plan lost the depth test to it (PF-L3D-13/14).
  Path relief stays within the path. Deck boards lie on the ground. No blades grow through a
  pond's coping or past a gravel or dirt path's round ends, and a path loop keeps its lawn.
  `senior-reviewer` round 1 found three P1s, now fixed:
  - a drag over a lawn re-cuts its blades at most every 0.4 s;
  - decks and other relief are bounded by construction;
  - a roof's lowest edge stays at least half its eave floor above the ground, the style kept.
- **Owner manual passes (2026-10-27, ADR-065's "Owner's manual pass" and "Owner's second manual pass" addenda):** gravel and dirt paths are their
  textures, opaque, in 2D and 3D; a new house is terracotta in 2D, with sandstone 3D walls;
  windows sit either side of a centred door; the fog follows the camera's distance. The
  parasol, fire pit, planter pot, cold frame, rain barrel, water tap, swing, hammock and
  pergola got real default heights: they show them in the panel and cast in 2D and 3D. The
  ground's detail-normal strength is 3.0.

  Follow-ups: #600, #603–#605, #607, #609, #611, #615–#621, #623, #624.

**Delivery (27 October 2026):** [v1.34.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.34.0)
shipped via [PR #613](https://github.com/cofade/open-garden-planner/pull/613), merge
`bcdbb5fd`, after the owner's third manual pass ("all perfect") confirmed every
checklist step, including the second pass's two decisions built into this round
(every standing object without a 2D default now has a real, settable height; the
detail-normal strength is 3.0). `ogp-3d-reviewer` re-reviewed the second pass's
changes and found two P1s, both fixed before merge: the AO fade switched SSAO on at
Low quality regardless of `aoEnabled` (PF-L3D-15), and a house built as a plain
block (a hole, two regions, or an unbuildable ridge) had a sandstone top instead of
roof tiles. `senior-reviewer`'s re-review found one P1, filed rather than fixed per
the owner's non-blocking-defect policy: a plant inside a cold frame or planter pot
now reads 0 h of sun (#621), because both holders gained a height and a shadow in
this round and the per-plant sun estimate was never taught to spare them. Local
validation at the final head (feea6faf): the default tier passed 19,470 (252
skipped; the one local failure is the frozen inventory test, which needs the 3.11
builder interpreter and passes 29/29 there); the perf tier passed 104 at the first
merge, not re-run locally since (the dev box's timings drift with load, #616); the
render tier (Direct3D 11, RTX 4070) passed 198, 6 xfailed, 1 skipped — the looks
file's 9 board tests errored at setup when the Beauty Board driver finished
(`status=ok`) and then crashed while exiting with 0xC000041D (#623), and that file
run alone passed 21 (1 xpassed). The frozen exe (rebuilt at feea6faf): the 8-s
smoke exited 124 once; `--selftest` exited 0 five times in a row (each a Direct3D
11 frame on the RTX 4070, `result=PASS`, 0 Qt errors). All 15 CI checks passed
before protected merge; the matching Release workflow passed, including
provenance attestation. Deliberately left open:
#615 (whether a four-tile ground bake must hold 10 ms on CI), #619 (detail 3.0's
sky-blue gravel crescents under a low sun — owner taste), #621 (the cold-frame/
planter sun regression above), #623 (the intermittent exit crash) and #624 (far
shadows and the meadow edge at extreme zoom/pitch).

### L3 acceptance highlights — Plant Forge (#387, ADR-064) — **shipped v1.32.0, PR #593**

- **L3.0:** Shared traits cover 123 recipes in 13 archetypes. Object SVG material
  tables have one stdlib-only home with byte-conformance checks. Exact Lemon Balm
  aliases now select the herb sprite; melon/flax keep their corrected fallbacks.
- **L3.1–L3.3:** Skeleton/tube/leaf builders cover broadleaf trees, conifers,
  palms, shrubs, hedges and herbaceous forms. LOD caps are 25,000/6,000/800 at
  18/45 m thresholds; cache bounds 256 entries/64 MiB. Crown area drives leaf
  cover at every LOD. Bare structural wood remains grounded at full height.
- **L3.4:** Climbers prefer a trellis parent, then a nearby structure within 50 cm
  of the canopy edge, then a bamboo tripod. Local finite support guides preserve
  physical contact when reachable within the canopy, including rotated plants
  and supports; farther supports cannot enlarge the recorded footprint.
- **L3.5–L3.6:** Background synthesis admits only current document/geometry/LOD
  results. Orbit and walk update LOD. Seasons update existing Models, with
  independent flower, fruit and tuber controls. Exact harvest days share the
  task calendar and local frost dates. Render gates and the Beauty Board exercise
  the production forge. PR #593 review fixes are pinned by workspace, calendar,
  coverage and winter-height regressions. Owner beauty/manual acceptance passed.
  Support discovery runs on the synthesis thread and reuses exact structural
  dependencies on date changes. The 300-plant / 100-support render timing gate
  calls the production workspace refresh and checks zero geometry work/churn.
  Finalization corrected its sampling protocol: the unchanged 16.0 ms threshold
  applies to the worst per-date median of 15 fixed, interleaved wall-time samples;
  raw samples and tails remain visible, and a 20 ms negative control proves rejection
  (ADR-064, section 8.29.11).

Cold synthesis measurement: 123 recipes, height 420 cm / radius 180 cm / seed 303, median of
three builds per recipe on Python 3.11: median 3.69 ms, p90 13.07 ms, maximum 23.01 ms;
warm median 0.0012 ms. Synthesis excludes engine uploads and presentation.

**Delivery (25 October 2026):** [v1.32.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.32.0)
shipped via [PR #593](https://github.com/cofade/open-garden-planner/pull/593), merge
`bdaecb21`, after the owner confirmed all executable checks passed. Local validation:
18,340 source tests passed (249 skipped), 115 timing tests passed, 142 render tests
passed (one expected platform-control failure), and both frozen checks passed
(smoke exit 124, detached self-test exit 0). Independent 3D and senior reviews ended
without outstanding findings; all 23 feature-head CI checks passed before protected
merge. The matching Release workflow passed, including provenance attestation.
Automation did not establish presented FPS; the owner accepted interactive use on
the active display. Existing ground-texture/wind issues #532/#534 remain separate.


### L2 acceptance highlights — Analyze in 3D (#386, ADR-063) — **shipped v1.31.0, PR #584**

- **L2.1 drapes + sun probe.** The 3D ground shows the plan's own 2D analysis: the shadow overlay's polygons (`SunShadowController.drape_polygons()` / `shadows_changed`) or the heatmap's map (`SunHeatmapController.result()` / `computed`, the plain-data `SunHoursMap`), row 0 = south, in the canvas's ramp. Choosing the hours of sun switches the shared Hours of Sun on. A click on the ground reads the map's cell and its band and pins it. Each drape is ONE mesh in ONE Model for the scene's life — no Model or texture per change (#531, #532). Found on the engine: a blended custom material must keep the frame's alpha, or the drape brightens the ground with the window's white (PF-L3D-06).
- **L2.2 sun path + day sweep.** Arcs of the plan date, 21 June, 21 December and 20 March, each one local day from `core.solar`, cut at the horizon; the gate holds — every noon point IS `solar_position` at the day's highest sun. A compass rose with translated letters as geometry. The day sweep runs the shared clock from sunrise to sunset and fills the drape from the map's own per-sample masks (taken by local time of day: the map samples a UTC day), then gives the time back.
- **L2.3 info card v1 + growth jump.** The card names the height's source at the plan date, the growth share, the measured sun and band, and the sowing / harvest windows (`task_generator.calendar_windows`, now the generator's own formula). +1 / +3 / +10 years move the shared date (29 February → 1 March) and show a before/after wipe built from exactly two pictures; Back returns. Plant labels (optional) are left for L3.
- **L2.4 Cutaway / X-ray.** Roofs off by one scene property; the items between the eye and the selection fade (Qt-free segment casts over the meshes the engine holds, the pick oracle's own triangle test), unpickable while faded.
- **Tests:** the §8.10 workflow `tests/integration/test_view3d_analysis.py` (real shadow overlay and heatmap worker beside the workspace), four new unit files, the QML scene without a GPU, the render tier on GPU / WARP / OpenGL, the frozen `--selftest` (both overlay shaders compiled and judged).
- **Owner acceptance (2026-10-24), two manual passes.** Pass 1 found the 3D hours-of-sun drape not following the toolbar switch going on, and the 2D shadows and heatmap hidden under lawns (ground surfaces now lie in `GROUND_Z_RANGE` under the overlays; PF-L3D-09, PF-CAN-22, FR-STACK-09). Pass 2 replaced the strip's separate Past/Future label with the Today button saying Past or Future in place at one width (ADR-062 addendum, PF-TST-26), and found the startup Welcome dialog switched off in the owner's real settings by a review probe, not by the code (PF-TST-27; the startup path is now pinned by `tests/integration/test_startup_welcome.py`; guard follow-up #587). Every checklist step was then confirmed and release authorized. Every CI job passed on the merged head (12 jobs, 23 check runs); the frozen smoke and `--selftest` passed; senior review ended with no P0/P1. The required `Dependencies` checks were unblocked by #575 (v1.30.21), merged first. Open owner questions (X-ray look, fading plants in a selected bed, flat vs tinted sun map, floor inside buildings, near half of the arcs #578, generic shapes under the sun study; the other five tracked in #589) keep the shipped behaviour until decided. Follow-ups: #573, #574, #576–#583, #586–#589; the sync's own process gap is #590.
### Parallel non-3D hardening — **shipped 2026-10-25 as v1.31.1, PR #585**

Built beside L2 without touching the 3D/sun/sim-clock stack: a styled line's walk
is clipped to the visible viewport and budgeted (#450), `addItem` gives an appended
solid the derivation's own next fixed-grid z so one derivation serves a whole loop
(and a one-item-per-command loop), dense vertex-edit overlays are sampled in viewport
pixels (#551), boolean union accepts a contact-connected selection of any size and
ellipses and refuses a result above the plan's polygon vertex cap (#550),
Preferences scrolls its form and opens at content height (#569), and a local build
compares the venv with `pylock.toml` (#538). #446 was closed with evidence: the
whole-name/alias rule shipped in v1.30.18, and the three whole-word residues are the
alias-table case the owner declined. Contributed content: @Sevoiger's personal-fork
implementation informed #550/#551; #569 was reported by @jbuijgers (fork branch
`fix/preferences-dialog-height`). §8.25 (one derivation per layer), §8.9 (shared
path clip), ADR-043 and ADR-061 addenda, FR-EDIT-19, FR-UI-14; the residual
per-command UI refresh (#592) and the dense-overlay scroll re-sample (#594) shipped
in the follow-up batch below.

### Non-3D follow-up hardening, batch 2 — **shipped 2026-10-26 as v1.32.1, PR #596**

Seven work items from the review ledger of L2 (#584) and the non-3D batch (#585), built
without changing the 3D/forge product code, the sun model or serialization:

- **Test signal (#562, #573).** Windows' `offscreen` Qt has no font database, so
  every family resolved to a box engine and the Plan & Sun layout file failed 20
  cases on the dev box while Linux CI passed. `tests/conftest.py::ui_font_family`
  now registers the real Windows faces once and makes Verdana 10 the application
  font; `tests/unit/test_test_font_contract.py` pins the real-engine contract;
  `test_plan_timeline.py`'s leaked `arial.ttf` registration is gone. The file is
  **78 passed / 76.9 s** on the dev box (was 20 failed / 55 passed / 3 skipped).
- **Settings safety (#587).** `create_qsettings()` refuses the production names
  under `offscreen`/`minimal` or in an exact agent/tooling shell unless the
  product's `main()` (`OGP_PRODUCT_PROCESS`) or `script_isolation`'s rebound
  names marked the process; `OGP_ALLOW_PRODUCTION_SETTINGS`
  is the deliberate one-off override. A probe can no longer switch off the
  owner's Welcome dialog. ADR-041 addendum, PF-TST-29.
- **Command-proportional refresh (#592).** `ConstraintGraph.fixed_item_ids()`
  scopes the lock-badge refresh; `Command.changes_ground_band` (default true) lets
  move/resize/rotate/vertex/curve/copy/link/constraint commands skip the
  scene-wide ground-band scan. 600 single adds: **0.31 s → 0.11 s**; a 100-command
  pin counts zero classifications and zero badge refreshes. ADR-043 addendum,
  PF-CAN-25, FR-EDIT-20.
- **Dense overlay scroll (#594).** A selected 16 384-vertex outline re-sampled
  every scrollbar step (~98 ms). The sample is now reused while the viewport stays
  inside the scene region it was taken over; a zoom or a pan beyond it samples
  again (**0.01 ms** cached). ADR-057 addendum, PF-CAN-26, FR-EDIT-20.
- **One height resolver (#581).** `core/object_height.resolve_height()` is the
  single precedence ladder; `effective_height_cm`, `height_source` and
  `height_source_at` project it. Answers unchanged, ADR-037 addendum.
- **PEP 639 license metadata (#574).** SPDX `license`, `license-files`, no license
  classifier, and a `setuptools>=77` build floor; the wheel is Metadata 2.4 with
  `License-Expression` and the LICENSE file, and builds without the deprecation
  warning. ADR-050 addendum, PF-CI-14.
- **Release-status duty (#590).** `finalize-us` §5 now also updates the feature
  ADR/addendum Status line and the README Status paragraph, the two statements
  three syncs in a row left stale.

The local full suite no longer carries the Windows-offscreen Plan & Sun failures:
the file is **78/78** on the dev box and the full suite is green; the root cause
was the box font engine. `docs/08` §8.8/§8.9/§8.10/§8.25, the five ADR addenda, FR-EDIT-20,
PF-CAN-25/26, PF-TST-28/29 and PF-CI-14 record the rules.

**Owner manual pass (2026-10-25) added three fixes to the same release PR.**
Help → About reported **1.2.0** in a direct PyInstaller build because a tracked, stale
`_version.py` shadowed `__version__`; the module is now a gitignored build artifact,
written before PyInstaller and removed after it, read dynamically, with a `__version__`
fallback, a conditional PyInstaller hidden import and a `--selftest` version check against
the version being built (PF-CI-15, ADR-050 addendum). Every short Properties input now shares one **120 px** control column: every numeric
field (right-aligned, including grid spacing, stroke width, soil and object height,
plant spacing, diameter, container height/volume, text size, symbol parameters, and
the position/size/semi-axes pairs) plus every combo (object type, layer, material,
fill pattern, stroke/path style, symbol choice, font) and the colour buttons
(`FIELD_WIDTH`, `_style_numeric_field`, `_style_combo`). A combo value longer than
the column keeps its full text in a tooltip; the popup always shows full names.
Position and size fields carry `X:`/`Y:`/`W:`/`H:` inside the box so both start at
the column edge. Name and text fields stay full width by design; the height tooltip
refreshes on every edit. A gallery drop of a **named** species now adopts
`max_spread_cm` like the Plant Database and Plant Lists drops, so an 8 m apple tree is
no longer 2 m wide in 3D; the display rule for a plant the owner resized is unchanged
(FR-PLANT-15). The only 3D-tier change is its test gate: **16 ms locally**, **25 ms on
CI's software rasterisers** (the 20 ms negative control still exceeds either budget),
after WARP timing failures across runners.

### L1.0 acceptance highlights — one sim clock (#385, ADR-053) — **shipped v1.29.10, [PR #429](https://github.com/cofade/open-garden-planner/pull/429)**

- **One moment for the whole app.** `core/sim_clock.SimClock` (Qt-free) is owned by `GardenPlannerApp`. The sun toolbar is a view of it (it writes edits and mirrors the clock back silently). The shadow overlay reads it (`utc` for the sun, `plan_date` for growth), and the heatmap request and the 3D view read it too. It is not persisted, and every session starts at "now" (FR-SUN-04).
- **Gate: a time change never fires `date_changed`.** It holds by construction on the product's path: the toolbar hands the clock its naive wall reading, which is stored as given, never derived from an instant. It is swept over every minute of an ordinary day and of both DST days, and through the real toolbar on America/Nuuk's pre-midnight-gap day (every slider value plus Animate ticks). The sun and heatmap suites stay green; four app-glue tests in three files now pass local wall times, and the toolbar's `datetime_changed` now carries the wall reading (one toolbar test renamed).
- **Fixes found on the way** (PF-DOM-22):
  - shadows and 3D grew plants for the instant's UTC date, while the heatmap used the local date;
  - a date change while the heatmap computed, or after the worker returned with its result still queued, let the old day's map paint (and a second launch in that queued window could abort the process — unreachable from the busy button, now refused);
  - the date picker allowed years that Windows' system-zone conversion cannot handle (now 1971–2999).
- No `.ogp` change and no new UI strings. The plan for the other ten stories is outlined in the #385 issue table; they were built on story branches and shipped together in PR #484 (v1.30.14).

### L1.0 docs updated on completion

| Document | Section |
|----------|---------|
| `docs/09-architecture-decisions/` | ADR-053 (new); ADR-037 growth addendum revision + inline supersession marker on its time-control paragraph; ADR-048 stale ADR-049 pointer |
| `.claude/skills/` + `.agents/skills/` | `ogp-architecture-contract` invariant 10 (Qt-free list, Channel rule); `ogp-3d-sunshade-campaign` (sim time not persisted, ADR-053 pointer); `application.py` citation lines in `ogp-architecture-contract`, `ogp-config-and-flags`, `ogp-research-frontier` |
| `docs/functional-requirements.md` | FR-SUN-04, FR-SUN-05, FR-SUN-06, FR-SUN-08 |
| `docs/08-crosscutting-concepts/` | §8.20 "One simulation clock" |
| `docs/05-building-block-view/` | `core/sim_clock.py` |
| `docs/06-runtime-view/` | §6.8 Sim clock fan-out |
| `docs/11-risks-and-technical-debt/` | PF-DOM-22 |
| `docs/12-glossary/` | Plan date, Sim clock |
| `CLAUDE.md` / `AGENTS.md` | Phase 17 pickup note |

### L1.1–L1.10 — the new 3D view (#385, ADR-059, ADR-060) — **shipped v1.30.14, [PR #484](https://github.com/cofade/open-garden-planner/pull/484)**

- **The 3D view is a Plan / 3D / Split workspace in the main window**, rendered with Qt Quick 3D (View → "3D View" opens Split; Alt+1 / 2 / 3). The Qt 3D viewer window, `core/scene3d/legacy.py`, `core/walk_camera.py`, the L0 spike and both `PyQt6-3D*` wheels are deleted, and `tests/unit/test_no_qt3d_left.py` keeps them out.
- **One story each:** L1.1 scene contract v2 (`core/scene3d/`); L1.2 the engine package (`ui/view3d/quick3d/`, CI `Render 3D` on Windows WARP and Linux); L1.3 the workspace (lazy engine, crash marker and software fallback); L1.4 looks and sky (presets with Automatic, twilight, wind, reduced motion); L1.5 the ground bake (the plan's flat surfaces painted onto the ground, matching 2D pixel for pixel); L1.6 the built world; L1.7 plant silhouettes (`core/plant_art/`); L1.8 selection sync, the info card and walk collision; L1.9 the default flip with throttled date playback (§8.29.9 holds the FR-SUN-06 / 07 / 08 parity table and the measured budgets); L1.10 the removal.
- **Fixed on the way:** defects of the released app #438, #439, #441, #467, #468, #469, #478, #479, #523, #527; the test suite and developer scripts writing into the developer's real profile, #442; and two found in the new view before it shipped, #476 (a Qt Quick 3D texture trap) and #529 (picket moiré at Low).
- **Owner acceptance, 2026-10-19:** the 36-step manual checklist passed, and the seven decisions put at the pull request were all kept as built — the twilight fade, the noon horizon's lime band, 4× MSAA at Low, the flat sky in compatibility mode, `master`'s rule for a loaded sprite's stated stroke, the new view's cost over the old window (no lighter default preset), and the default shipped with Qt 6.11's ground-texture leak #532 open (ADR-060 addendum D5).
- **Known limitations, filed:** #531 and #532, and the `priority: high` follow-ups #534–#536, #538 and #540 (wind memory, the look on a software-only adapter, a render-test flake, a local build’s contents, CI coverage of the default workspace). Follow-ups #537/#539/#541/#542 shipped on 2026-10-23 as v1.30.19 ([PR #565](https://github.com/cofade/open-garden-planner/pull/565)) after owner acceptance: workspace cleanup/Walk icon, navigation from other tabs, native Reset key text, and no-op throttle stamps. Controlled-clock regressions replace the uptime-dependent test; all three reject the old stamp. Docs updated: ADR-060 addendum, runtime view, §8.29.9, PF-TST-25, both context files and debug-verbose libraries.
- **Docs:** ADR-059 and ADR-060 with their addenda, ADR-048's closing addendum, §8.29, §8.10.5–8.10.13, PF-L3D-01 to PF-L3D-05 and PF-E3D-01 to PF-E3D-09, FR-SUN-06 / 07 / 08, FR-SUN-11, FR-33, the FR-3D-* requirements and the glossary's scene terms (Scene record, Scene diff, Engine sink, …).

---

## Task-date correctness + audit P1 cluster — **shipped v1.29.5** (PR [#419](https://github.com/cofade/open-garden-planner/pull/419))

Not a phase — a hardening package, shipped on `master` alongside v1.29.4. Six
issues from two sources: three correctness bugs found by the ADR-048 L0 senior
reviews, and three effort-S items from the [2026-10 repository audit](https://github.com/cofade/open-garden-planner/issues/392)
(both audit P0s were already closed by #411/#412; this takes the remaining S
items that are disjoint in file terms).

| # | Title | Sev | Effort | Origin | Outcome |
|---|-------|-----|--------|--------|---------|
| [#414](https://github.com/cofade/open-garden-planner/issues/414) | Task calendar: GUI surfaces miss every frost-relative window anchored on another year's frost (TD-037) | P1 | M | ADR-048 L0 senior review | Every GUI surface routes through one shared multi-anchor entry point |
| [#415](https://github.com/cofade/open-garden-planner/issues/415) | Planting calendar: the propagation editor saves steps in the wrong year | bug | S | ADR-048 L0 senior review | Editor shows real dates; inverted overrides ignored, never destroyed |
| [#416](https://github.com/cofade/open-garden-planner/issues/416) | Plant data: harvest offsets are read two ways | bug | S | ADR-048 L0 senior review | Documentation made true; row conversion split out to [#418](https://github.com/cofade/open-garden-planner/issues/418) |
| [#396](https://github.com/cofade/open-garden-planner/issues/396) | Agent API: make Host/Origin (DNS-rebinding) validation explicit (TD-012) | P1 | S | audit AUD-039 | `TransportSecuritySettings` configured by OGP; floor `mcp>=1.23` |
| [#395](https://github.com/cofade/open-garden-planner/issues/395) | Array tools have zero coverage behind their modal dialogs (TD-013) | P1 | S | audit AUD-010 | 13 integration tests; **215 statements newly covered** (321 of 325 never ran before, 106 still do not) per the committed `scripts/measure_array_tool_coverage.py` |
| [#398](https://github.com/cofade/open-garden-planner/issues/398) | Skills contradict `ci.yml` / `server.py` / `docs/09` (TD-015) | P1 | S | audit AUD-064 | Four statements corrected in both skill trees + a drift guard |

### What changed, in one paragraph

The Tasks tab, the planting-calendar dashboard and the Gantt each anchored their
frost-relative task windows on **the current year's** last spring frost, while the
agent's `get_tasks` / `get_task_calendar` anchored on every year that could reach
the requested date. Measured over the 64 bundled species that carry calendar offsets x 6 frost dates x every 10th day of 2026 (222 cases):
**1,836 (task, frost-date, day) cases the GUI missed and the agent listed;
0 after the fix**, with 0 surplus tasks (the urgency filter still applies). Harness committed as `scripts/measure_task_window_sweep.py`. A
southern plan (20 September frost) put a tomato harvest at 29 Nov 2026 – 7 Feb
2027, so on 1 January 2027 a tomato-only plan read *"No tasks — you're all caught
up."* while the task was open. See ADR-029 (addendum) and ADR-049.

### Deliberately deferred

- **[#418](https://github.com/cofade/open-garden-planner/issues/418)** — converting
  the bundled harvest offsets to their true reading. Measured: both readings fit a majority of the 64 comparable rows (38 frost-relative, 45 planting-relative), with 11 fitting neither, so the data is NOT irreconcilable; it needs a cited
  horticultural source per row. **Garlic's harvest window lands ~3 months LATE** (October, not July) until then - and that is independent of which reading you assume, since its row fits the frost-relative one on maturity.
- **#399** (branch protection), **#401** (mypy gate), and **#402** (coverage gate) completed in v1.29.6 via PR #422. Their baselines measured the settled tree after this package.
- **#405** and **#418** completed in v1.29.8 via PR #426; **#409** (NFR-PERF-01) shipped in v1.29.9 via PR #430; **#406** (constraint-tool coverage) shipped in v1.30.2 via PR #477 after owner acceptance.

### Package F1/F2 delivery notes (v1.30.0, PR #433)

F1 (#312) and F2 (#313) shipped together in [v1.30.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.0) via [PR #433](https://github.com/cofade/open-garden-planner/pull/433) after automated gates, independent review and all 13 owner frozen-app checks passed on 11 October 2026. F1 adds saved traits, complete offline filtering/background online fallback and semantic layer assignment. F2 adds immutable guild snapshots, template authoring, preflighted one-step insertion/membership, cosmetic badges and general diagnostics. The template editor and general Diagnostics panel are agreed scope additions. F3 (#314) shipped with heatmap document-lifecycle fix #428 in v1.30.1 via PR #436; F4 (#315) shipped in v1.30.17 via PR #533; F5 (#316) later completed Package F in v1.33.0 via PR #610. ADR-054/055 and FR-32 record the contracts; mandatory workflows include `test_permaculture_layer.py`, `test_guilds.py` and `test_permaculture_manual_regressions.py`. Wiki pages are rendered from these approved repository sources under ADR-051.

### Package F3 acceptance highlights (v1.30.1, PR #436)

F3 (#314) and heatmap lifecycle fix #428 shipped together in [v1.30.1](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.1) via [PR #436](https://github.com/cofade/open-garden-planner/pull/436) on 12 October 2026. The owner confirmed every manual acceptance check before protected finalization.

- Explicit worker results feed ground-level sun estimates excluding self-shadow, cosmetic warning badges, shared panel/MCP diagnostics and mature-canopy groups. ADR-056 and FR-SUN-09/10 record the measurement and unavailable-state contracts; there is no persistent exposure or file-version change.
- Document replacement cancels work and rejects running/queued late results. Deterministic GUI New/Open/recovery and real MCP replacement regressions are pinned in `tests/integration/test_sun_document_lifecycle.py`; the feature workflow is `tests/integration/test_sun_mismatch.py`.
- Independent review reproduced and resolved concave-footprint badge containment and malformed legacy species handling, then returned clean final review. Full validation: 7,938 passed, 34 skipped; line coverage 76.9%, branch 60.3%; 200 casters/receivers 3.267 seconds. Frozen startup, subsystem self-test, real MCP reads/moves/New/Open and inspected renders passed; GitHub CI and release provenance passed.

F4 (#315) shipped in [v1.30.17](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.17) via [PR #533](https://github.com/cofade/open-garden-planner/pull/533) after owner acceptance; F5 (#316) later shipped in v1.33.0 via PR #610. #328 shipped earlier in PR #352 and was excluded from this package.

### Docs updated on F3 completion

| Document | Section |
|---|---|
| `docs/09-architecture-decisions/README.md` | ADR-056 |
| `docs/functional-requirements.md` | FR-SUN-09/10 and Agent API diagnostic kinds |
| `docs/05-building-block-view/README.md`, `docs/06-runtime-view/README.md` | Sun aggregation/coordinators and exposure lifecycle |
| `docs/08-crosscutting-concepts/README.md` | §8.27 cached exposure and shared diagnostics |
| `docs/11-risks-and-technical-debt/README.md` | PF-UI-21 (dead code path) and PF-DOM-24 (sun self-shadow) |
| `docs/12-glossary/README.md` | Sun exposure and mature-canopy grouping |
| `docs/wiki/`, root instruction pair, mirrored skills | Shipped status and maintenance contracts |

### Audit P1 constraint-tool characterization (#406; epic #392)

Implementation checkpoints: real point-tool harness; remaining gestures/state/shape matrices;
shared per-file coverage enforcement (ADR-050 addendum). All 13 registered tools have
press/move/release scenarios and real command/history integration. A newly exposed rectangle
edge-length no-op is fixed by reusing the canonical size applier, with a failing-first regression.
The full-suite baseline measured 679/2340 lines (29.0%) and 68/706 branches (9.6%). The target
file now has a reviewed 60% full-suite line floor; branch coverage remains a separate report.
Full-suite result on reviewed code `588e3db`: 2023/2372 lines (85.3%) and 486/720
branches (67.5%); all package/file floors pass. Overall coverage rose from 76.9%/60.3%
to 80.1%/63.5% (line/branch). The run recorded 8159 passed, 34 skipped and two repaint
budget failures under coverage, also reproduced on unchanged master; all three repaint
budget tests passed in an isolated run without instrumentation. All 13 tool scenarios and 259 focused
gesture/gate tests passed. Independent senior review is clean. Frozen build, eight-second
startup, subsystem self-test, straight/45-degree edge resizing, saved graph identity through
undo/redo, modal cancellation, tool switching and real point-based alignment passed.
Owner manual acceptance passed on 12 October 2026. Protected [PR #477](https://github.com/cofade/open-garden-planner/pull/477) delivered #406 in [v1.30.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.2); the Release workflow completed with build provenance. Backlog intake [PR #466](https://github.com/cofade/open-garden-planner/pull/466) merged first. All 15 original standalone P0/P1 remediation issues are complete; #392 remains open for A1–A13.

Finalization reran 268 focused gesture/gate/context/citation tests, frozen eight-second smoke and `--selftest`, and fresh independent implementation/rebase reviews. The additional full local run without coverage recorded 8160 passed, 34 skipped and one fit-in-view timing miss (16.79 ms against 16.70 ms); unchanged master also missed this budget in the isolated baseline (18.71 ms). CI is green; no timing budget was relaxed.

Owner testing found the pre-existing rotation/constraint interaction, tracked in [#485](https://github.com/cofade/open-garden-planner/issues/485). A real-canvas probe on master and the #406 branch measured a 200 cm corner distance becoming 314.42 cm after rotation and recovering on a nudge. The reported skipped rotation undo was not reproduced in that isolated probe. This follow-up remains separate from #406 and the 73-entry P2/P3 partition.

### Audit package A1 (#453) — shipped in v1.30.3 (PR #487)

Strict numeric `.ogp` ingestion and atomic persistence, release-bound checksum/origin
verification before installer launch, bounded fully decoded thumbnail/Static Maps
responses, and owner-only Linux settings with explicit startup failure. One branch
and one PR (#487) cover AUD-041/042/044/047. Shipped 2026-10-13 as v1.30.3.
No file-format bump, dependency change, credential-key migration, release-right
change or renderer change. Epic #392 stays open.

Final validated source: `f0a5d225` (2026-10-13). Locked Linux full-suite coverage:
8245 passed, 37 skipped; all package/file floors passed. Coverage is 79.9% lines /
63.5% branches overall, and 85.6% / 74.2% outside UI. Windows full suite:
8241 passed, 39 skipped, with two repaint timing misses during concurrent gates
(30.67/23.47 ms against 16.70 ms). Quiet strict repaint reruns passed all three
tests on both this branch and unchanged master; no thresholds or skips changed.
Final line/arc/Bezier/preservation tests: 101 passed; translation/interpolation:
70 passed. Both platform type gates have zero regressions; HIGH Bandit findings:
zero. Lint, lock/export, secrets, agent parity, citations and offline wiki pass.
Fresh independent re-review has no outstanding P0/P1. The controlled-PATH frozen
build passed detached self-test (0) and eight-second startup (124), including
packaged plan/codecs/hash probes. The real v1.30.2 installer was downloaded and
verified at 179026922 bytes against its release checksum, without launch.
Owner manual acceptance on frozen build confirmed 2026-10-13; merged via PR #487
and released as v1.30.3. Wiki publication follows finalization.

### A1 docs updated on implementation

| Document | Section |
|---|---|
| Building blocks / runtime | Shared ingestion components and refusal flows |
| Crosscutting concepts | Error preservation, settings, security and test evidence |
| ADR register | ADR-003, ADR-041 and ADR-044 addenda |
| Deployment / requirements | Verified installation, Linux migration, FR-SAFETY-01–04 |
| Risk register / reconciliation | A1 evidence and pending acceptance |
| Agent context / wiki sources | Current implementation and public behavior |

### Audit package A2 (#454) — shipped v1.30.5 (PR #490)

Owner confirmed all manual checks and authorized finalization on 15 October 2026.
[PR #490](https://github.com/cofade/open-garden-planner/pull/490) merged through
protection as `6854fe66` and shipped in
[v1.30.5](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.5).
All 18 pre-merge CI checks and the matching Release workflow passed, including the
frozen self-test and provenance. The live monthly dependency report passed in
[run 38646071241](https://github.com/cofade/open-garden-planner/actions/runs/38646071241),
created review issue #493 and left the lock unchanged.

Toolchain pins (interpreter `3.11.9`, NSIS `3.13.0`), commit-SHA action pins with a CI
drift guard, `dist/build-evidence.json` emitted and required by the release, a `pip-audit`
scan of the locked export (one recorded exception for macOS source-distribution publishing), the verified-unavailable
Dependabot path replaced by a monthly report-only `dependency-review.yml`, the stale
`requirements*.txt` manifests deleted, and third-party notices + a CycloneDX SBOM generated
from the frozen bundle's own metadata, installed next to `LICENSE`, published and attested.
No runtime dependency change and no lock replacement beyond adding `pip-audit` to the dev
extra (the audit gate itself); no release-right change or `.ogp` version bump. See
ADR-044/ADR-050 addenda and the A2 delivery-state section of the reconciliation.

PR #490's 14 October review found that the declared dependency closure omitted code
collected by PyInstaller hooks. The frozen inventory now also attributes actual Analysis
inputs to wheel RECORD owners, including distinct vendored copies; verifies its ownership
manifest against the executable PYZ; and checks declared license texts. The frozen-hook
regression failed on the original artifact. See ADR-044's review addendum and §11.4.

Final CI also exposed an uncontrolled-duration heartbeat assertion in the existing
sun-mismatch integration test. The delivery gate now holds the real worker in flight,
requires GUI heartbeats and a different thread, then validates its real result; a
synchronous-worker negative control fails. No application behavior or timing budget
was relaxed. See §8.10 and §11.4.

| Document | Section |
|---|---|
| ADR register | ADR-044 and ADR-050 addenda |
| Deployment view | §7.2 build pipeline and installer files, §7.3 release assets, §7.4 toolchain pins, build evidence and the dependency-update runbook |
| Risk register / reconciliation | §11.2 build-advisory update; A2 delivery state |
| Agent context / skills | Mirrored `ogp-config-and-flags` / `ogp-external-positioning` manifest references |

### Audit package A5 (#457) — shipped v1.30.4 (PR #489)

Owner confirmed all frozen-app checks on 14 October 2026, including the German
localization follow-up. [PR #489](https://github.com/cofade/open-garden-planner/pull/489)
merged through protection as `9dc37274` and shipped in
[v1.30.4](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.4).
The matching Release workflow passed, including frozen checks and provenance.

AUD-012: immutable enum-complete constraint panel presentation descriptors, retaining
the existing translation context, icons, colors, formatting and theme refresh.
AUD-023: fresh eight-mutant sample with explicit source/test scope, independent
residual/geometry/pinning/feasibility/conflict-ID assertions and real panel/history
workflow. Existing relevant selection: 432 tests; strengthened selection: 501 tests.
Two confirmed symmetry survivors are killed; one baseline timeout remains identified
separately. All eight strengthened mutations fail assertions. No historical mutation
score or co-change count is promoted into current evidence.

Failing-first regressions and tagged caller-stack tracing exposed all-pinned false
convergence: Newton returned success before computing residuals. Fixed-state residuals
are now measured before return. No tolerance, damping, arbitrary iteration-count,
dependency or file-format change. ADR-012 addendum; [detailed plan](implementation-plan-457.md)
and [reproducible evidence](11-risks-and-technical-debt/audits/2026-10/audit-2026-10-a5-evidence.md).
Initial reviewed source: `cda81961`. Windows full suite: **8313 passed, 37 skipped**
in 910.54 seconds, with no failures or relaxed timing budgets. Focused author checks:
226 passed plus the timeout regression; fresh independent re-review: 191 passed,
no outstanding findings. Ruff, HIGH Bandit (0), translations/interpolation (35),
lock/export, Windows type baseline (0 regressions), context parity, citations,
secrets and offline wiki pass. Controlled-PATH clean frozen build, detached
self-test (0) and eight-second startup (124 equivalent) pass. The English/German
all-type widget board was visually inspected; a real registered Fixed/Fixed/Distance
gesture refused an incompatible target without scene/graph/history changes.
Final feature head `d82a0ae1` passed all cross-platform CI checks: **8317 passed,
37 skipped**; Linux coverage **80.0% lines / 63.6% branches** (non-UI
85.7% / 74.5%), with zero package/file-floor regressions.
Owner checks 1 (theme/readability) and 3 (fixed conflict rejection) passed. Check 2
found English unnamed endpoints in German constraint rows. The follow-up uses
canonical translated object names for all 52 types and compare-overlay plants,
adds missing Hecke/Dachfirst catalog entries, and pins duplicates, explicit names
and real row/tooltip wiring. Owner confirmed the German retest before finalization.
Follow-up tested source `29429088`: Windows full suite **8317 passed, 37 skipped**
in 806.45 seconds; fresh reviews clean (70 label tests and the clock regression),
frozen self-test/startup and other local gates pass. The full run first exposed a
host-hour-dependent sun test; tagged tracing proved its +1 hour crossed midnight.
Its fixture now fixes noon without changing production behavior or timeouts.
Epic #392 remains open; other audit bundles and #485 remain separate.

### A5 docs updated on completion

| Document | Section |
|---|---|
| Building blocks / runtime | Presentation descriptor and pinned feasibility sequence |
| Crosscutting concepts / ADR register | Numerical evidence and ADR-012 addendum |
| Risk register / reconciliation | AUD-012/023, TD-038/039 and measured all-pinned pitfall |
| Agent context / mirrored debug skill | Shipped status and failing-first evidence |
| Wiki sources | Shipped A5 status, descriptor/solver boundary and evidence link; ADR-051 publication |

### Worker lifecycle safety, cache bounds and test hygiene package (#480, #483, #482, #474, #449, #448)

**Complete, 2026-10-16; released as [v1.30.7](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.7) via [PR #498](https://github.com/cofade/open-garden-planner/pull/498), closing #480, #483, #482, #474, #449, #448 after owner acceptance.**
- **#480 & #483 (Worker thread exit safety)**: Deterministic `cancel()` flag and `shutdown()` handshake for `UpdateChecker` and `_WeatherFetchWorker`. When a thread cannot be joined within timeout_ms (e.g. blocked in synchronous urllib.request.urlopen), the worker is retained in `core.worker_lifecycle._RETIRING_WORKERS` until its finished signal is handled, preventing premature garbage collection and C++ `~QThread()` destruction (`0xC0000409` aborts). Clean encapsulation via `PlantingCalendarView.shutdown()`. Pinned in `tests/unit/test_worker_lifecycle.py`, `tests/unit/test_update_checker.py` and `tests/integration/test_weather_widget.py`.
- **#482 (Redundant closure cleanup)**: Removed redundant closure connecting to `self.destroyed` in `GlobalSearchField`. Cleaned up unused `contextlib` import. Pinned in `tests/unit/test_global_search.py`.
- **#474 (Furniture renderer dimension and cache memory bound)**: Clamped maximum furniture dimensions to `MAX_FURNITURE_DIMENSION_PX = 2048` (returning fallback on <= 0, inf, or NaN); capped furniture pixmap cache to `64 MB` with LRU eviction and memory budget tracking. Pinned in `tests/unit/test_furniture_renderer.py`.
- **#449 (FR-AGENT ID uniqueness)**: Renamed duplicate `FR-AGENT-27` to `FR-AGENT-29` in `docs/functional-requirements.md` and added regression gate in `tests/unit/test_ci_quality_gates.py`.
- **#448 (Test environment flakiness)**: Decorated `test_type_cli_missing_mypy_is_an_error_not_a_clean_result` with skipif for non-3.11 interpreters matching `test_type_cli_generate_check_regress_and_reduce`. Added multi-round retry and local load tolerance to `tests/perf/test_nfr_budgets.py` while keeping CI budgets strict.
- **Shortcut overload resolution**: Dedicated `Ctrl+F` to global search focus in `CategoryToolbar` and reassigned Find & Replace to `Ctrl+H` in `GardenPlannerApp`, eliminating ambiguous shortcut overload warnings with whole-window duplicate shortcut assertion gate.

### 2D canvas follow-up: a paint bound, one look rule and a line budget (#470, #472, #473, #502)

**Complete, 2026-10-17; released as [v1.30.8](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.8) via [PR #501](https://github.com/cofade/open-garden-planner/pull/501) after owner acceptance.**

Three pre-existing 2D defects found during the Phase 17 L1 work (#385), shipped together
because none touches the in-flight L1 branch's files (see ADR-057, §8.28, PF-CAN-18). #502 came
from the owner's manual pass of that PR. Independent review of the package also caught two
defects the green suite had passed over — the #472 degrade never ran in the product (it tested
Qt's `widget`, which is always `0` for a *cached* paint, so the condition was never true on the
canvas; it now keys on the item's cache mode), and the #502 round-trip test styled items with a
colour that *is* `GENERIC_RECTANGLE`'s default, so it could not fail; see PF-CAN-18 and PF-CAN-19.
#503 was filed from the same review for the identical `widget` idiom in the LOD flat fill.

- **#502 (manual pass of #501)**: a textured fill did not show the chosen colour - the runtime tint was a
  31 % wash (`_tint_texture`, alpha 80/255), so a light-green fill over the Roof Tiles texture rendered the standard
  brown (`#ca6846` → `#b8925d`); raising the wash flattened the low-contrast materials. Replaced by a **luminance map**
  (chosen colour × the texture's relative luminance), which makes the colour read and preserves relative contrast by
  construction (ADR-042 addendum). The same pass showed the Properties panel disagreeing with the canvas after a
  reload: the loader rebuilt the brush/pen but never restored the stored appearance attributes, so the panel showed the
  object type's defaults and the next save wrote them over the user's colours — the loader now restores them through
  `core/item_look.restore_stored_look` (#438/#469). The §8.10 gate gained the pale-colour case and a relative-contrast
  assertion (reverting the tint fails 19 of 48 cases); `tests/integration/test_item_appearance_roundtrip.py` pins the
  rendered pixels across all five shapes and the Ctrl+D duplicate. Lesson in PF-CAN-19.
- **#472 (Bounded polygon paint)**: `PolygonItem` painted any vertex count a plan held, and a
  reflex-heavy outline makes one antialiased fill quadratic (measured with the item's own pen:
  ~322 ms at 1,024 vertices, ~5.6 s at 16,384). Full detail is now bounded by
  `MAX_FULL_DETAIL_VERTICES = 256`; above it an interactive, unselected paint draws the exact
  outline with a **cosmetic** 1-px pen (essential — a wide solid pen makes the outline a fill
  again), while exports/offscreen renders and selected items keep the exact fill.
  `MAX_POLYGON_VERTICES = 16_384` refuses a hostile
  polygon at the load seam without dropping the rest of the plan. Pinned in
  `tests/integration/test_polygon_paint_bound.py`.
- **#470 (Offset copy keeps its look)**: the offset tool made a rectangle, circle or ellipse copy
  in its object type's default fill, pattern and stroke. One seam, `core/item_look.py::
  copy_visual_style`, now copies both the serialized attributes and the pen/brush, and is shared
  with `mirror_geometry` (chamfer/fillet/trim stayed with #441 on the L1 branch, shipped in v1.30.14). Pinned in
  `tests/integration/test_offset_tool.py`.
- **#473 (Line paint in the budgets)**: the NFR-PERF-01 reference plan held no polyline, so the
  three budget scenarios could not see a slower line paint. A second scenario adds plain fences
  and a styled gravel path to the same plan, with their item cache **disabled** so `paint()` runs
  every frame, pinned deterministically by a `cacheMode()` guard and behaviourally by a same-run
  delta; an absolute per-frame budget for the styled lines stays with #450. Pinned in
  `tests/perf/test_nfr_budgets.py`.

### Shipped v1.30.10: the #409 low-zoom flat fill is removed; the cache-mode predicate is kept (#503, PR #507)

- **#503 (LOD flat fill never fired)**: filed by #501's independent review against its own work —
  `GardenItemMixin.should_use_lod_flat_fill` (the #409 low-zoom flat fill) decided "interactive"
  with `widget is not None`, but Qt passes `widget = 0` for every **cached** paint and every
  unselected canvas item is `DeviceCoordinateCache`, so the branch never ran in the product
  (measured through a real `CanvasScene` + `CanvasView`: one call per paint, no widget, `False` at
  every view state) and its tests passed only because they called the helper directly.

  **Resolved by deletion, not by repair** — issue #503 offered both repairs explicitly. The guard
  was first fixed so the branch ran, then measured on the reference plan it was written for
  (990 items, best of seven rounds, both scenarios below the 0.4 threshold): `fit_in_view` at zoom
  0.316 read **10.61 / 11.50 ms median with the flat fill off, 10.87 ms with it on**, and
  `zoom_step` at 0.348 read **7.97 / 7.98 ms off, 8.20 ms on** — the effect sits below this
  harness's noise (within-arm variation 8 % against a 0.26 ms between-arm difference, and
  no reversed-order run was taken, so no claim about which arm is faster survives). All six
  `tests/perf/test_nfr_budgets.py` cases pass either way, worst reading 12.21 ms against the
  16.70 ms budget. The earlier single-pair reading (10.58/10.64, 8.21/7.40) is superseded: it
  put the `zoom_step` sign the other way round.
  `DeviceCoordinateCache` rasterises a textured item once and every later frame is a blit, so the
  textured `paint()` the LOD existed to avoid was already amortised by the sibling fix from #409;
  the branch could only ever subtract detail. The owner's manual pass then settled what the
  measurement could not: at 20–25 % zoom — where they work, well under the threshold — every
  texture, plant sprite and furniture sprite would have become a solid colour, and the paint-level
  diagnostics drawn after the fill branch would have been skipped.

  **Shipped:** `should_use_lod_flat_fill`, `get_lod_fill_color` and `LOD_FLAT_FILL_THRESHOLD`
  deleted, along with seven call sites in the rectangle, circle, ellipse and polygon items; no
  zoom-dependent simplification remains in the canvas. `is_interactive_paint` is **kept** — it is
  the one definition of "which paint is this", and #472's paint bound needs it for real (44.7 ms at
  1,024 vertices, 589 ms at 16,384); its docstring now records that it classifies paints and does
  not decide detail. #472's suite is restored to its pre-#507 state in full, including its
  fit-in-view harness zoom; the low-zoom seam pair and the 100 %-zoom workaround served only the
  removed branch.

  **The pin inverts, and is parametrised over branches rather than classes.** The seven deleted call
  sites were never seven instances of one thing: two sat inside `if is_plant` and two inside
  `if is_furniture_type`, behind type predicates a `GENERIC_*` fixture never satisfies, so a
  table of the four generic shapes watched only four of seven — and the three unwatched ones are
  exactly the sprite paths the owner's manual pass objected to. Measured by mutation: a `< 0.4`
  flat fill in a plant branch renders a `TREE` circle from interior intensity std 43.09 to 0.00,
  a flat brown disc, while 212 tests in the repo stayed green. The table now carries seven entries
  (the four generic shapes plus a plant circle and furniture rectangle/circle), each rendered
  through a real `CanvasView` at five zoom levels — 0.1, 0.25, 0.4, 0.75, 1.0 — plus the export
  path, asserting the interior still carries its texture's luminance spread with a **lower bound
  only**, so a future change may soften a texture but cannot delete it. Re-introducing a `< 0.4`
  flat fill is caught at **all seven** call sites, mutation-verified per site. The sampled interior
  is the item's own `QGraphicsItem.shape()` — not its bounding box, whose corners are page
  background for three of the four shapes; not a second paint, which any flat-fill branch
  overrides on its way through; not alpha, because the scene paints an opaque background — and
  `TestTheMaskIsTheItem` asserts that invariant, because a mask in the wrong coordinate frame does
  not fail, it *reads background*, which is what a luminance statistic calls texture. ADR-057
  addendum, PF-CAN-20.

### US-F4 plan timeline (#315) — complete, v1.30.17, PR #533

Owner acceptance follow-up shipped on 2026-10-23 as v1.30.19 ([PR #565](https://github.com/cofade/open-garden-planner/pull/565)) after owner acceptance:
date/time editor stepping carries and borrows across calendar and clock boundaries,
including held arrows, wheel/buttons and preferred-day handling. One complete naive
reading updates the shared clock; the midnight workflow pins 2D presence, 3D geometry
and sunlight with no plan edit. Initial boundary regressions failed before the fix;
FR-TIMELINE-06, ADR-062 addendum, runtime view, section 8.31.1 and PF-UI-26 record it.

ADR-062 and FR-34 define a month scrubber/Today on the existing SimClock, undoable
plant removal dates, half-open presence, date-present data diagnostics and current-state
exports/API annotations. The 2D sprite now shares the growth date; fresh creation
uses that date too. Season Manager remains a whole-plan yearly copy. Integration
workflows include real controls, exact boundaries, history, round-trip and rendered
growth/export checks. F5 (#316) remains a separate story. Validation evidence and owner acceptance are recorded in PR #533.

F4 owner-planned integration follow-up (20 October 2026, PR #533): master through v1.30.15 and
release fix #543 are merged into the branch. One permanent adaptive Plan & Sun strip replaces the
duplicate date controls and optional simulation toolbar; solar/decorative shadows
are automatic, Hours of Sun updates while enabled with an honest dated preview,
and image/PDF exports wait for current results. Monthly scrubbing preserves the
preferred day; the 21 June shortcut is removed. ADR-062 / FR-34 / §8.31 record the
decision, with combined-controls and native Qt Quick 3D integration evidence. Owner
acceptance and protected merge are complete; F5 stays separate. Wiki publication follows ADR-051.

Owner visual follow-up (21 October): the initial layout checks omitted the app's
theme and proved containment only. The themed strip now centres whole rows, styles
the time field consistently with the calendar, supplies visible calendar/menu
arrows, shows Today once and repeats a date only for an older map preview. Empty
map labels no longer reserve space before the hidden-plants menu. The integration
workflow checks both themes and all supported locales; the owner accepted the revised interface and requested release.

F4 final delivery: **[v1.30.17](https://github.com/cofade/open-garden-planner/releases/tag/v1.30.17) via [PR #533](https://github.com/cofade/open-garden-planner/pull/533), 2026-10-21**, after owner acceptance. The full local suite, isolated performance selection, all feature CI checks, locale gates, frozen build/smoke/self-test and live MCP checks passed. Coverage floors passed. Independent 3D and senior reviews passed. Six finalization P1 findings were fixed and independently re-reviewed before merge; the accepted strip layout is unchanged.

### Line appearance and cache-containment follow-ups (#524, #525, #526, #471)

Shipped on 2026-10-21 as v1.30.16 ([PR #545](https://github.com/cofade/open-garden-planner/pull/545))
after owner acceptance on the built executable. Preset selection undo restores
the exact previous stroke (#524). Both type-change controls apply the new type's
defaults and clear the preset, restoring the original look on undo (#525).
Round caps and joins survive history (#526). Styled-line bounds contain metal
details and acute paved-path/stone-wall tips through the painter's shared reach (#471).
The focused regressions cover all ten styles, real controls, history/persistence,
panel lifetime, dirty state, cached transforms and ground output. Actual delivery
gate totals are recorded in the PR; no release is claimed before owner acceptance.
The timeline and Russian translation PRs remain separate.

### 2D canvas defect batch (#522, #530, #445, #446, #528)

Five shipped defects on `master`, taken together because they share one theme -
the 2D canvas, the panel that edits it and the tools that read it - and because
each is small, measured and pinned.

| # | What was wrong | What shipped |
|---|----------------|--------------|
| #446 | The sprite resolver matched a species name by **substring**, so a melon was drawn as an eggplant ("melon" is inside "solanum melongena"), a scientific name as a rose ("Petroselinum crispum" contains "rose"), a plant whose name merely CONTAINS another plant's name as that other plant ("peach_tree" as a pea) and a blank species as a rose (the empty string is inside every key). | The name is matched as a **whole name or alias**: the whole name, else a key whose every word is a word of the name ("Broad Bean" -> bean), else a key that holds every word of the name ("Solanum" -> tomato); a name no sprite knows falls back to the plant's category sprite. Measured: 74 of the golden's 1,562 answers change over 37 names, and of the bundled species' 118 names exactly ONE changes - the melon. **What it does not fix:** "Lemon Balm", "Bean (Bush)" and "Sweet Potato" still take a fruit or vegetable sprite, because their names contain a whole word that is another plant's name; a curated alias table would be needed, and was declined. The rule the issue proposed (whole-name only) was measured first and **rejected**: it changes 266 answers over 110 names, and most of those are regressions ("Quercus robur", "Broad Bean", "Sweet Corn" would fall back to a generic sprite). |
| #445 | Assigning a species from the database wrote only the record, and the sprite resolver reads the item's own species **string** - so the plant kept the sprite it was drawn with, in 2D and in 3D alike (a tomato that still looked like a shrub). | The assignment writes that string too (the record's common name, else its scientific name), inside the same `ApplySpeciesCommand`: the record, the footprint, the spacing override and the string revert together in one undo step. |
| #522 | Shift+click on an item on a **locked** layer fell through to a plain click, so it **replaced** the selection instead of toggling it (`itemAt` answers the topmost item, and a locked item is not selectable). | The select tool asks for the first **selectable** item under the cursor, so Shift+click toggles what lies behind the locked item - the canvas's own rule. The 3D selection bridge already did this: the one measured difference between the two views is gone. |
| #530 | Seven Properties-panel edits (a bed's grid on/off and grid spacing, its soil depth; a container's material, drainage, height and soil volume) wrote into the item directly: neither undoable nor a mark of a modified plan - Ctrl+Z undid the container's **creation** instead of its height, and closing the app asked nothing and lost the edit. | Each is one `ChangePropertyCommand`, like the panel's name, height, fill and stroke edits, and each still announces itself to the 3D view (the plan revision moves and the item repaints). A value that was never set is restored as **absent** again, not as `None`. |
| #528 | The perf-marker guard could not see a measurement that travels in an **attribute** - the ground bake's G3 gate was marked `perf` by hand because its stopwatch lives in `ground_bake_support.TimedBaker` - and it flagged a test that times nothing when a method of the same bare name elsewhere holds a stopwatch. | The guard follows the carrier into the local support modules, scoped to the class that owns the attribute, so one class's stopwatch never taints another's; a value that is only **counted** (`len(timestamps)`) is not a duration. G3 is now one of its 40 candidates and its marker is required, not a habit. |

Docs: FR-EDIT-15, FR-EDIT-16, FR-PLANT-21, FR-PLANT-ART-05, PF-DOM-26, PF-DOM-27, PF-UI-24, PF-UI-25, PF-TST-24, the ADR-061 pitfall catalogue and the `CLAUDE.md` / `AGENTS.md` pickup note.

PR #556 senior-review follow-up: Shift+press on an interactive handle keeps Qt mouse delivery before selection transparency. The handle registry is shared with the view's dropped-grab recovery; real resize/rotation drags over a selectable background are pinned at 0, 37 and 143 degrees, including single-step undo. The later #528 review reproduced the original same-module false positive: function indexing and both call-graph closures now preserve lexical ownership, with both class orders and the real ground-bake AST pinned. The manager-free panel regression now actually omits the command manager. See the ADR-058 #528 addendum and §8.10.4.

PR #556 owner manual pass: a legacy saved toolbar row compressed Plan & Sun to
259 pixels in a 1707-pixel window and stretched the neighboring drawing tools.
Startup now restores bounds/splitters while retaining the fixed toolbar topology
(ADR-062 addendum; two-position restart regression). Undoing a species assignment
also clears the profile header, image, links and attribution, rather than leaving
Turkey oak above an empty form; redo restores the whole profile. The melon checklist
now draws/selects a Vegetable before database assignment. The 40 m 3D check names
**Oak (Quercus robur) — Bundled** explicitly: the owner's Turkey oak had no height,
so its neutral marker followed the current contract, and the owner confirmed the
bundled oak renders. Category-based estimated heights are tracked separately in #557.

Additional PR #556 manual-pass finding: Material and Drainage retained their
pre-undo values while focused although metadata, 3D and derived feedback restored
correctly. The shared Properties refresh guard now protects active text input only;
committed dropdown, checkbox and color choices refresh without reselection. Other
controls using that path include fill/stroke style, label/grid/frost toggles and
text bold/italic. The owner completed manual acceptance on 22 October 2026 and
authorized protected finalization and release. The final gate battery and fresh
review cover these source fixes before merge. Category-based unknown-height
estimates (#557), maximum-width geometry propagation (#558), and command coverage
for existing Plant Details species/instance fields (#559) remain separate work.
The broader text/numeric focus guards require history-aware handling (#560);
the committed-choice refresh fix does not remove active-edit protection.

Finalization evidence (22 October 2026): the final default Windows/offscreen
suite recorded 17,058 passed, 234 skipped and 11 Plan & Sun font/layout assertion
failures; the documentation index mismatch from the preceding run is fixed.
Native Windows validation passed all 99 affected checks, including every one of
the 51 Plan & Sun cases. The quiet timing suite passed 98 tests with 10 skips.
Lint, high-severity security, secrets, type-baseline, translations, lock/export,
context/citation/wiki, sprite golden and all 97 mutation-pattern checks passed.
The frozen Python 3.11.9 bundle passed inventory attribution for 72 distributions,
the eight-second smoke (124), and self-test (0), including an RTX 4070 / Direct3D
11 frame. Independent 3D review found all 53 board frames pixel-identical to
master and all truth gates passing. Senior review found no P0/P1 and independently
passed seven native latest-fix cases; its sole EOF-whitespace nit is removed.
Protected merge succeeded on 22 October 2026; shipped as v1.30.18.

### Plant Details follow-ups (#552, #557–#560) — shipped as v1.30.20, PR #566

| Issue | Implemented behavior |
|---|---|
| #552 | FIXED rejects panel X/Y writes; undoable Lock/Unlock across object menus; upright, export-hidden badges follow constraint history and load. |
| #559 | Species and instance edits use independent command snapshots. Spin ticks coalesce within editingFinished boundaries; staged text flushes before save, document guards and history navigation. Shared-library writes remain separate from plan undo. |
| #560 | History refreshes committed values even with editor focus; ordinary same-selection refreshes protect active input and update unrelated fields. |
| #558 | Species-derived Max Spread updates centered 2D/3D dimensions; measured and legacy measured dimensions, spacing overrides and custom footprints retain precedence. A cleared width retains geometry. |
| #557 | Labelled illustrative 3D heights: tree 400 cm, shrub 150 cm, perennial 60 cm, vegetable 50 cm. Authoritative height remains unknown, including analytical 2D sun/shade. |

Implementation evidence: `tests/integration/test_plant_package_558_559_560_552_557.py`
and `tests/integration/test_plant_dimensions_records.py`; ADR-004/013/059,
crosscutting section 8.32 and PF-UI-27. Independent review and current gate results
are recorded in PR #566. Protected merge and release completed on 23 October 2026;
all five issues are closed after owner executable acceptance.

Owner acceptance confirmed plant history/save, widths, estimated heights, locales
and lock behavior. The manual follow-up removes the second painted path padlock.
The reported static sun was a plan without a location; setting coordinates restored
2D/3D shadows and Hours of Sun. A persistent location link beside Hours of Sun now
opens the existing location dialog and clears automatically after configuration
(FR-TIMELINE-07). The owner confirmed both follow-ups on the executable and
authorized release. All 23 feature CI checks passed. Native Windows checks passed
162 tests; serial performance passed 98 with 10 skips. The full local offscreen
suite passed 17,166 with 234 skips and 24 font/layout failures covered by native
Windows and green Linux CI (#562). Independent senior/3D review and frozen smoke
and self-test passed. The published installer checksum and source-bound build
provenance attestation were independently verified against the release merge SHA.



### CI latency follow-up #601 — owner-approved chore (PR #606)

Coverage retains all line/branch data and unchanged package/file floors. Two
stable test-ID hash partitions plus one serial perf producer feed the protected
Coverage check, which requires every measurement and all three files. The
uninstrumented Test job and its duration artifact remain. The perf audit moves
27 deterministic cases from the 116-case serial set; AST reuse, consolidated CLI
sweep consumers and immediate acyclic receiver cleanup remove repeated work.

See ADR-058, §8.10.4, deployment §7.4 and the
[investigation, marker inventory and measured results](11-risks-and-technical-debt/audits/2026-10/ci-latency-601.md).
No application or render-tier scope change; #540/#600/#603 remain separate.
Owner authorized protected merge on 26 October 2026 without GUI testing because
the change is limited to CI/tests/documentation. No release or version sync is needed.

### F5 examples and templates (v1.33.0, PR #610)

Three offline CC-BY-SA-4.0 examples cover an established seven-layer food forest
with a local apple guild, a densely planted 4 x 2 m raised bed with 2027 succession,
and a furnished, enclosed balcony with grouped herb containers. Welcome and File share a thumbnail gallery;
local templates appear from app data. Template copies are untitled/dirty, export
filters named site/history fields and absolute paths, and `garden://examples`
is read-only. The dogfood sample now copies the maintained raised-bed content.

The issue's frost-relative claim was stale: succession stores calendar dates.
No rebasing is added; example descriptions identify illustrative dates. ADR-066,
FR-EXAMPLE-01 through 06, and `test_templates_gallery.py` record the contracts.
Owner executable acceptance was confirmed on 27 October 2026. [PR #610](https://github.com/cofade/open-garden-planner/pull/610)
shipped [v1.33.0](https://github.com/cofade/open-garden-planner/releases/tag/v1.33.0) after independent visual/senior review, 18,504 local
tests, 77 serial performance cases and all 15 hosted checks passed. This completes Package F.

Owner-feedback revision (27 October): all layouts have English/German/Spanish
plan content, editable tutorial notes and public city coordinates for solar study.
Known bundled copies retain fictional soil samples; exported and external
templates still strip site/history data. The main bed holds 164 vegetables wholly
inside the sprite soil. The 114-plant forest uses historical perennial dates,
nursery anchors, cultivated understory and nearby guild membership. The balcony
has 14 herbs, chairs, rails, a wall and a parasol. Reference dates are explicit
teaching choices; opening does not move the shared simulation clock.

### The 2D sun study's geometry and estimates (#444, #481, #620) — parallel non-3D batch 3 — **shipped 2026-10-28 as v1.34.3, PR #627**

Built beside Phase 17 L4 without touching the 3D/sun/sim-clock product code or
serialization: one caster's ring set is now one REGION (#444), the per-plant estimate
spares the soil solid a plant stands in whether or not the link was made (#481), and the
mutation that names the heatmap worker now points at the line the worker really calls
(#620). **Measured** (#444): a 10 m × 8 m closed fence stroke drew **88.8 m²** of shade
where its stroke's prisms give **17.5 m²**; a self-crossing outline drew 80,000 cm² where
its two lobes give 129,282. `core.shadow_geometry.shadow_region` repairs the hole with a
zero-width slit and splits a self-crossing ring into lobes, once per item on the one
caster walk; every simple ring is returned point for point, so the shadow golden fixture
is **not** regenerated (measured: no hole-bearing caster in either bench plan). **Measured**
(#481): a full-sun tomato inside a 40 cm raised bed whose link was never made read **0.0 h**
and warned; it now reads **16.5 h**, and a plant one step outside the bed still loses sun
to it (a per-receiver spare, not a hole in the bed's shadow). ADR-037 addendum "one
caster's ring set is one REGION", ADR-056 addendum, FR-SUN-05/09/11, PF-DOM-28, §8.10.

### A plant draws above the bed it stands in, linked or not (#629) — **shipped 2026-10-28 as v1.34.3, PR #627**

Found by the owner on #627's manual pass: a raised bed, container, wall planter or trellis
drawn AROUND a standing plant hid it in 2D — still visible in 3D, and its sun badge with it.
The in-ground garden bed only looked immune because it is a ground surface in
`GROUND_Z_RANGE`, under everything. The clamp that was meant to prevent this followed
`parent_bed_id`, and drawing a bed around a plant makes no link (#443). Now a plant's
stacking parent is its link, or the smallest plant-parent whose outline contains its stable
centre; it is re-derived on add (only when the parent CAPTURES a plant: 600 childless bed
adds stay at 0.24 s), on arrange, and after every command that can change containment
(`Command.changes_containment`, not `changes_ground_band` — the geometry commands set that
one False). The check is the derivation's own answer compared with the drawing
(`_derived_plant_parent`), not a second rule. Measured: 0.9 ms per command on the 990-item
reference plan (200 plants, none linked), 1.1 ms for 300 plants in 30 beds linked and 2.8 ms
unlinked; a linked plant costs no geometry at all, and a layer whose highest parent is below
every plant costs one comparison each. The parents' shapes are cached for the pass — without
that cache the adversarial 200-plants-under-50-concave-beds plan cost 43 / 330 / 1 661 ms at
6 / 200 / 1 200 vertices, against 8 / 30 / 133 ms with it. ADR-043 addendum, FR-STACK-10,
PF-CAN-29. The merge that landed this section had pasted FR-STACK-10 twice; the duplicate is
gone and the FR-id uniqueness gate now covers **every** FR id instead of only FR-AGENT-*
(it found four pre-existing collisions — FR-SNAP-04/05, FR-PLANT-19, FR-LAYER-09 — which are
renumbered here: FR-SNAP-11/12, FR-PLANT-24, FR-LAYER-10).

### Every item with a footprint can be given a height (#628) — **shipped 2026-10-28 as v1.34.3, PR #627**

The Properties panel's Height field was gated on has_height_semantics, whose last clause
for a type without a per-type default is "an explicit height already exists" — so the field
that would create one could never appear. A generic polygon (the owner's star), an
in-ground bed, a terrace, a pond, a lawn, a path and a driveway could not become solids
without changing the object's TYPE (to Garage, with its look and 3D builder). The question
now splits: the type-level predicate stays, and the panel asks
shows_height_field(..., has_footprint=item_has_footprint(item)) — every footprint
item gets the row, "Auto" (0) stays no height, so a ground surface keeps lying on the
ground until someone types one (then lies_on_ground yields and it is a platform).
Text, callouts, groups, arcs, beziers and journal pins have no footprint and stay without
the field (the whole set is pinned through the real panel, and `item_has_footprint` is
pinned equal to `item_outline(...) is not None` over every placeable kind, because it
answers the same question without building a 16 000-vertex outline). ADR-037 addendum,
FR-SUN-02, PF-UI-29.

The owner's manual pass confirmed the field and found the follow-up: every surface that got a
height lost its texture (a 40 cm lawn became a flat green slab, a 10 cm soil bed a brown one).
New `MeshPart.fill_texture`: such a part shows the item's own fill — the 2D pattern tinted by
the fill colour, or that colour alone for SOLID — supplied by
`core.fill_patterns.tinted_pattern_pixels` and cached per (pattern, colour), refcounted by the
sink so a recolour or a removal leaves no picture behind. UVs are (position + paint_origin) / 256 on a
cap (the canvas's phase); the SIDES are the item's tint (tinted sides + fill cap, no smear down an edge). A garden bed's soil cap is its
"Boden-Substrat"; a container's soil stays the palette's. Measured on Direct3D 11, 1000 × 400
top-down, two 300 cm squares at 40 cm: luma std 26.0 for GRASS against 0.0 for SOLID at the same
mean (121.3 / 120.8). A second owner pass fixed three residues: a raised plain surface is now tinted SIDES + a fill CAP (one prism smeared the picture down the edge), a raised lawn keeps its blades (lifted to the new top; the height gates ignore `ground_detail`), and a raised pool's water samples the plan's own water picture (`uFill`) instead of a flat tint. A plant dropped into a bed also undoes as ONE step now (move + link in one `CompoundCommand`), and a bed dragged on its own now carries its child plants with no lag
(the origin used to be recorded as `child.pos() - delta` on a first sighting, when the child
had not moved). The phase is pinned against the canvas's own painter, not a formula:
`tests/integration/test_scene3d_fill_phase.py` bakes a real rectangle and correlates the
mesh's UVs (NCC 0.995; the opposite sign 0.759 / 0.866). ADR-037 addendum, FR-3D-BUILT-09,
PF-L3D-17.

### Remaining audit packages A4/A6/A7/A9/A12/A13 (#392) ? draft delivery

All six remaining bundle issues (#456/#458/#459/#461/#464/#465) are implemented
on one branch against master, with A4's boundaries established before structural
extraction. ADR-068 and [the per-finding delivery evidence](11-risks-and-technical-debt/audits/2026-10/audit-392-remaining.md)
own the current measurements, decisions, regression nets and residual owner-only
continuity actions. The application/canvas/property/handle extractions preserve
existing commands, serialization, translation contexts and lifecycle boundaries.
The performance harness covers every NFR workload; the archived audit is unchanged.
This is not shipped: owner executable/documentation acceptance and protected merge
remain pending. PR #639 remains separate.

| Documentation | Update |
|---|---|
| Building blocks and runtime | Shared leaves, composed adapters, handle owners and startup refresh |
| Crosscutting/testing and quality | Canonical instruments after extraction and reproducible workload definitions |
| ADRs and debt reconciliation | ADR-068, per-finding evidence, measured samples and preserved historical ledger |
| Agent instructions and skills | Concise mirrored context, exact preserved reference fragments and recursive gates |
| Deployment/security/contributing | Existing policy owner, verified aliases and honest continuity/recovery steps |
| Wiki sources | Architecture and contribution pointers; publication pending after approval/merge |
