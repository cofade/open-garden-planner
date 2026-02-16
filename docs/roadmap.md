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
| ~~6~~ | ~~v1.0~~ | ~~✅ Complete~~ | ~~Visual Polish & Public Release~~ |
| **7** | **v1.1** | **In Progress** | **CAD Precision & Constraints** |
| 8 | v2.0+ | Future | Advanced Features |

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

## Phase 7: CAD Precision & Constraints (v1.1)

**Goal**: Full 2D geometric constraint system with numeric precision input, construction aids, and pattern placement — bringing FreeCAD Sketcher-level precision to garden planning.

**Ref**: GitHub Issue #60

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-7.1 | Measure tool snap to object anchors (centers + edges) | Must | ✅ Done |
| US-7.2 | Distance constraint data model & solver | Must | ✅ Done |
| US-7.3 | Distance constraint tool (dedicated toolbar tool) | Must | ✅ Done |
| US-7.4 | Dimension line visualization (FreeCAD-style, toggleable) | Must | |
| US-7.5 | Constraint solver drag integration (chain propagation) | Must | |
| US-7.6 | Constraints manager panel | Must | |
| US-7.7 | Numeric position input (editable X, Y in properties) | Must | |
| US-7.8 | Numeric dimension input (editable width/height/radius) | Must | |
| US-7.9 | Horizontal/Vertical alignment constraints | Should | |
| US-7.10 | Angle constraints | Should | |
| US-7.11 | Symmetry constraints | Should | |
| US-7.12 | Construction geometry (helper lines, not in exports) | Should | |
| US-7.13 | Draggable guide lines | Should | |
| US-7.14 | Linear array placement | Could | |
| US-7.15 | Grid array placement | Could | |
| US-7.16 | Circular array placement | Could | |

### US-7.1: Measure Tool Snap to Object Anchors

**Description**: Enhance the measure tool to snap to object center points and edge midpoints when clicking near objects, enabling precise object-to-object distance measurement.

**Acceptance Criteria**:
- Measure tool snaps to object center when clicking within 15cm threshold
- Also snaps to edge midpoints (top, bottom, left, right) of rectangles and polygons
- Visual indicator (small circle) shows the active snap point
- Crosshair marker placed at snapped position, not raw click position
- Works for all object types (circles, rectangles, polygons, polylines)

### US-7.2: Distance Constraint Data Model & Solver

**Description**: Implement the constraint data model and iterative position-based constraint solver (Gauss-Seidel relaxation) that resolves constraint chains.

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

---

## Phase 8: Advanced Features (Future, v2.0+)

Future enhancements beyond v1.1:

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
