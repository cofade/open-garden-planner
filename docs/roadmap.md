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
| 8 | v1.2 | Planned | Location, Climate & Planting Calendar |
| 9 | v1.3 | Planned | Seed Inventory & Propagation Planning |
| 10 | v1.4 | Planned | Companion Planting & Crop Rotation |
| 11 | v2.0+ | Future | Advanced Features |

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
| US-7.4 | Dimension line visualization (FreeCAD-style, toggleable) | Must | ✅ Done |
| US-7.5 | Constraint solver drag integration (chain propagation) | Must | ✅ Done |
| US-7.6 | Constraints manager panel | Must | ✅ Done |
| US-7.7 | Numeric position input (editable X, Y in properties) | Must | ✅ Done |
| US-7.8 | Numeric dimension input (editable width/height/radius) | Must | ✅ Done |
| US-7.9 | Horizontal/Vertical alignment constraints | Should | ✅ Done |
| US-7.10 | Angle constraints | Should | ✅ Done |
| US-7.11 | Symmetry constraints | Should | ✅ Done |
| US-7.12 | Construction geometry (helper lines, not in exports) | Should | ✅ Done |
| US-7.13 | Draggable guide lines | Should | |
| US-7.14 | Linear array placement | Could | |
| US-7.15 | Grid array placement | Could | |
| US-7.16 | Circular array placement | Could | |
| US-7.17 | Coincident constraint (merge two anchor points) | Should | |
| US-7.18 | Parallel constraint (two edges stay parallel) | Could | |
| US-7.19 | Perpendicular constraint (two edges at 90°) | Could | |
| US-7.20 | Equal size constraint (same radius/width/height) | Could | |
| US-7.21 | Fix in place / Block constraint (pin object permanently) | Could | |
| US-7.22 | Horizontal/Vertical distance constraints (1D dimensional) | Could | |
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
| 6 | Coincident | ⬜ US-7.17 | Grayed out |
| 7 | Parallel | ⬜ US-7.18 | Grayed out |
| 8 | Perpendicular | ⬜ US-7.19 | Grayed out |
| 9 | Equal Size | ⬜ US-7.20 | Grayed out |
| 10 | Fix in Place | ⬜ US-7.21 | Grayed out |
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

## Phase 8: Location, Climate & Planting Calendar (v1.2)

**Goal**: Enable location-aware planting schedules with a dashboard showing what to do today/this week/this month.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-8.1 | GPS location & climate zone setup | Must | |
| US-8.2 | Frost date & hardiness zone API lookup | Must | |
| US-8.3 | Plant calendar data model | Must | |
| US-8.4 | Planting calendar view (tab) | Must | |
| US-8.5 | Dashboard / today view | Must | |
| US-8.6 | Tab-based main window architecture | Must | |

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

### US-8.3: Plant Calendar Data Model

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
- New local database: `resources/data/planting_calendar.json` — curated data for 50+ common vegetables/herbs
- Merge logic: local DB has priority, API data fills gaps

### US-8.4: Planting Calendar View

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

### US-8.5: Dashboard / Today View

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

### US-8.6: Tab-Based Main Window Architecture

**Description**: Refactor the main window to support multiple tabs (Garden Plan, Planting Calendar, Seed Inventory).

**Acceptance Criteria**:
- Tab bar above the canvas area with at least "Garden Plan" tab
- Switching tabs preserves state (no data loss)
- Sidebar panels only visible on Garden Plan tab
- Tab icons for visual distinction
- Keyboard shortcut to switch tabs (Ctrl+1, Ctrl+2, Ctrl+3)
- Existing functionality unchanged — Garden Plan tab works exactly as before

**Technical Notes**:
- This is a prerequisite for US-8.4 and US-9.4 — implement first
- Modify `application.py` -> `_setup_central_widget()`
- Wrap current `QSplitter` in a `QTabWidget`
- Tab 0: existing splitter (canvas + sidebar)
- Tabs 1+: new views added by subsequent phases
- Consider `QStackedWidget` if tab bar styling needs customization

---

## Phase 9: Seed Inventory & Propagation Planning (v1.3)

**Goal**: Manage seed packets ("Samenbeutel"), track viability, and plan the full propagation cycle from indoor sowing to transplanting.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-9.1 | Seed packet data model | Must | |
| US-9.2 | Seed viability database | Must | |
| US-9.3 | Seed inventory management panel | Must | |
| US-9.4 | Seed inventory tab view | Must | |
| US-9.5 | Propagation planning (pre-cultivation) | Should | |
| US-9.6 | Seed-to-plant manual linking | Should | |

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
- Default step durations in `planting_calendar.json`:
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

## Phase 10: Companion Planting & Crop Rotation (v1.4)

**Goal**: Help gardeners optimize plant placement with companion planting recommendations and multi-year crop rotation tracking.

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-10.1 | Companion planting database | Must | |
| US-10.2 | Companion planting visual warnings | Must | |
| US-10.3 | Companion planting recommendation panel | Should | |
| US-10.4 | Whole-plan compatibility check | Should | |
| US-10.5 | Crop rotation data model | Must | |
| US-10.6 | Crop rotation recommendations | Should | |
| US-10.7 | Season management & plan duplication | Could | |

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
- Nutrient demand data in `resources/data/planting_calendar.json` (extend existing)

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

## Phase 11: Advanced Features (Future, v2.0+)

Future enhancements beyond v1.4:

- Additional drawing tools (arcs, curves, bezier paths)
- DXF import/export for CAD interoperability
- 3D visualization (Qt3D integration)
- Sun path simulation
- Plant growth over time visualization
- Plugin system
- Community plant library sharing
- Seasonal view (spring/summer/autumn/winter appearance)
- Irrigation planning
- Cost estimation
