# Development Roadmap

## Overview

| Phase | Version | Status | Description |
|-------|---------|--------|-------------|
| 1 | v0.1 | ✅ Complete | Foundation: Canvas, drawing, file operations |
| 2 | v0.2 | ✅ Complete | Precision: Image import, calibration, measurement |
| 3 | v0.3 | ✅ Complete | Objects & Styling: Rich objects, textures, layers |
| 4 | v0.4 | ✅ Complete | Plants & Metadata: Plant objects, API, sidebar |
| 5 | v0.5 | ✅ Complete | Export & Polish: PNG/SVG/CSV export, shortcuts, themes |
| Backlog | - | ✅ Complete | Rotation, vertex editing, annotations |
| **6** | **v1.0** | **In Progress** | **Visual Polish & Public Release** |
| 7 | v2.0+ | Future | Advanced Features |

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
| US-6.15 | Path & fence style presets | Must | |

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
- [ ] Path/fence style presets

---

## Phase 7: Advanced Features (Future, v2.0+)

Future enhancements beyond v1.0:

- Additional drawing tools (arcs, curves, bezier paths)
- DXF import/export for CAD interoperability
- 3D visualization (Qt3D integration)
- Sun path simulation
- Plant growth over time visualization
- Companion planting suggestions
- Plugin system
- Community plant library sharing
- Seasonal view (spring/summer/autumn/winter appearance)
- Irrigation planning
- Companion planting matrix
- Cost estimation
