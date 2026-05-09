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
| ~~7~~ | ~~v1.1 – v1.6~~ | ~~✅ Complete~~ | ~~CAD Precision & Constraints~~ |
| **8** | **v1.7 – v1.8.3** | **✅ Complete** | **Location, Climate & Planting Calendar** |
| **9** | **v1.8.5 – v1.8.6** | **✅ Complete** | **Seed Inventory & Propagation Planning** |
| **10** | **v1.8.6 – v1.8.12** | **✅ Complete** | **Companion Planting & Crop Rotation** |
| **11** | **v1.8.13+** | **🔨 In Progress** | **Bed Interior Design, Visual Polish & Advanced 2D Tools** |
| 12 | v1.9.0 | Future | Weather & Smart Features |
| 13 | v2.0 | Future | 3D Visualization & Sun/Shade |
| 14 | v2.1+ | Future | Platform & Community |

---

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

Every user-visible string must be wrapped for translation. See `docs/08-crosscutting-concepts/` section 8.3.

---

## Dev Infrastructure

> Infrastructure improvements that apply project-wide, independent of product user stories.
> These are tracked here rather than as numbered product US entries.

| Status | ID   | Description            | Notes                                                         |
|--------|------|------------------------|---------------------------------------------------------------|
| ✅     | DI-1 | SAST pipeline (Bandit) | HIGH-severity scan in CI; `bandit>=1.7.0` added as dev dep   |

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

## Phase 11: Bed Interior Design, Visual Polish & Advanced 2D Tools (v1.8.x)

**Goal**: Perfect the 2D garden planning experience — bed interior design, visual polish, annotations, shape operations, drawing tools, interoperability, and workflow improvements.

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

## Phase 12: Weather & Smart Features (v1.9.0)

**Goal**: Bring live weather data into the garden planning workflow — forecast-based watering decisions and plant-aware frost warnings, fetched at startup via Open-Meteo (no API key required).

| ID | User Story | Priority | Status |
|----|------------|----------|--------|
| US-12.1 | Weather forecast widget in Dashboard | Must | ✅ |
| US-12.2 | Frost alert & plant-aware warnings | Must | ✅ |
| US-12.3 | DXF export | Should | ✅ |
| US-12.4 | DXF import | Should | ✅ |
| US-12.5 | Multi-page PDF export | Should | ✅ |
| US-12.6 | Shopping list generation | Could | ✅ |
| US-12.7 | Pest & disease log | Could | ✅ |
| US-12.7 | Pest & disease log | Could | |

| US-12.8 | Succession planting | Could | |
| US-12.9 | Garden journal (map-linked notes) | Could | |
| US-12.10 | Soil health tracking & amendment calculator | Must | ✅ |

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
| `docs/12-glossary.md` | NPK, Amendment, SoilTestRecord, SoilTestHistory, Rapitest scale |

---

## Phase 13: 3D Visualization & Sun/Shade (Future, v2.0)

**Goal**: Full three-dimensional garden view with sun/shade simulation — the milestone that justifies a major version bump.

- 3D visualization (Qt3D integration)
- Object height properties (walls, fences, trees, structures)
- Sun path simulation (shade calculation by season, time-of-day animation, seasonal analysis)
- First-person walkthrough mode
- Plant growth over time visualization (seedling → mature)

---

## Phase 14: Platform & Community (Future, v2.1+)

**Goal**: Extend the platform with community features, plugins, and cross-platform support.

- Plugin system for extensibility
- Community template sharing / marketplace
- Irrigation planning & drip system design
- Cost estimation & budget tracking (advanced)
- Cross-platform packaging (macOS, Linux)
