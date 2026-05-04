# Functional Requirements

Detailed functional requirements for Open Garden Planner. These serve as the specification for implementation.

## FR-1: Canvas and Coordinate System

### FR-1.1 Metric Canvas
- **FR-CANVAS-01**: Canvas uses metric coordinate system (centimeters as base unit)
- **FR-CANVAS-02**: Display can show measurements in cm, m, or mixed (e.g., "2.35 m")
- **FR-CANVAS-03**: Canvas supports zoom from 1:1000 (overview) to 1:1 (detail) scale
- **FR-CANVAS-04**: Pan and zoom via mouse wheel, drag, and keyboard shortcuts

### FR-1.2 Grid System
- **FR-GRID-01**: Optional visible grid overlay (toggleable via toolbar button)
- **FR-GRID-02**: Grid spacing configurable (10cm, 25cm, 50cm, 100cm)
- **FR-GRID-03**: Snap-to-grid toggleable (independent of grid visibility)
- **FR-GRID-04**: Grid renders efficiently at all zoom levels (adaptive detail)

### FR-1.3 Background Image
- **FR-IMG-01**: Import background images (PNG, JPG, TIFF)
- **FR-IMG-02**: Calibrate image scale by marking a known distance (e.g., "this fence is 5.2m")
- **FR-IMG-03**: Two-point calibration: user clicks two points and enters the real-world distance
- **FR-IMG-04**: Adjust image opacity (0-100%)
- **FR-IMG-05**: Lock/unlock image layer to prevent accidental movement
- **FR-IMG-06**: Image stored as reference in project (path or embedded, user choice)
- **FR-IMG-07**: Multiple background images supported (e.g., different areas of property)

## FR-2: Drawing Tools

### FR-2.1 Basic Shapes
- **FR-DRAW-01**: Line tool (click-click or click-drag)
- **FR-DRAW-02**: Rectangle tool (axis-aligned and rotated)
- **FR-DRAW-03**: Polygon tool (click to add vertices, double-click/Enter to close)
- **FR-DRAW-04**: Circle tool (click center, then click rim point to define radius)
- **FR-DRAW-05**: Ellipse tool (future enhancement)
- **FR-DRAW-06**: Arc tool
- **FR-DRAW-07**: Polyline tool (connected line segments, open path)

### FR-2.2 Shape Properties
- **FR-DRAW-10**: Fill color (solid colors, predefined palette, custom color picker)
- **FR-DRAW-11**: Fill pattern/texture (grass, gravel, concrete, wood, water, soil, mulch)
- **FR-DRAW-12**: Stroke color and width
- **FR-DRAW-13**: Stroke style (solid, dashed, dotted)
- **FR-DRAW-14**: Opacity per shape

### FR-2.3 Editing Operations
- **FR-EDIT-01**: Select tool (click, box select, Shift+click for multi-select)
- **FR-EDIT-02**: Move objects (drag or arrow keys with Shift for precision)
- **FR-EDIT-03**: Rotate objects (free rotation and snap to 15 degree increments)
- **FR-EDIT-04**: Scale objects via resize handles (8 handles: 4 corners + 4 edges)
- **FR-EDIT-05**: Delete objects (Delete key, context menu)
- **FR-EDIT-06**: Duplicate objects (Ctrl+D)
- **FR-EDIT-07**: Undo/Redo (Ctrl+Z, Ctrl+Y) with unlimited history per session
- **FR-EDIT-08**: Copy/Paste (Ctrl+C, Ctrl+V) including across projects
- **FR-EDIT-09**: Edit polygon vertices (add, remove, move individual points)

## FR-3: Layers

- **FR-LAYER-01**: Support multiple layers (minimum: Background, Property, Hardscape, Plants, Annotations)
- **FR-LAYER-02**: Default layers created with new project, user can add custom layers
- **FR-LAYER-03**: Layer visibility toggle
- **FR-LAYER-04**: Layer lock toggle (prevent editing)
- **FR-LAYER-05**: Layer opacity
- **FR-LAYER-06**: Layer reordering (drag in layer panel)
- **FR-LAYER-07**: Assign objects to layers (default based on object type, manual override)

## FR-4: Property Objects

Pre-defined object types for common property elements:

| Object Type | Default Properties | Representation |
|-------------|-------------------|----------------|
| **House** | Footprint polygon, name | Filled polygon with roof texture option |
| **Garage/Shed** | Footprint polygon, name | Filled polygon |
| **Fence** | Polyline, height, material | Line with fence pattern |
| **Wall** | Polyline, height, thickness | Thick line with fill |
| **Path** | Polyline, width, material | Stroked path with texture |
| **Terrace/Patio** | Polygon, material | Filled polygon with texture |
| **Driveway** | Polygon, material | Filled polygon with texture |
| **Pond/Pool** | Polygon, depth | Filled polygon with water texture |
| **Greenhouse** | Polygon, dimensions | Filled polygon with glass texture |

- **FR-OBJ-01**: Each object type has appropriate default styling
- **FR-OBJ-02**: Objects are first-class entities with editable metadata
- **FR-OBJ-03**: Objects can have custom name/label displayed on canvas
- **FR-OBJ-04**: Object metadata shown in properties panel when selected

## FR-5: Plant Objects

### FR-5.1 Plant Representation
- **FR-PLANT-01**: Plants rendered as illustrated SVG shapes (species-appropriate)
- **FR-PLANT-02**: Visual distinction between trees, shrubs, perennials, annuals
- **FR-PLANT-03**: Optional label showing name/species
- **FR-PLANT-04**: Visual indicator for plant status (healthy, needs attention, planned)

### FR-5.2 Plant Metadata (per instance)

| Field | Type | Description |
|-------|------|-------------|
| Species | Text + lookup | Scientific name (e.g., "Malus domestica") |
| Common Name | Text | Display name (e.g., "Apple Tree") |
| Variety/Cultivar | Text | Specific variety (e.g., "Honeycrisp") |
| Diameter | Number (cm) | Current canopy/spread diameter |
| Height | Number (cm) | Current height |
| Sex | Enum | Male / Female / Monoecious / Unknown |
| Planting Date | Date | When planted |
| Age | Calculated | Derived from planting date |
| Sun Requirement | Enum | Full Sun / Partial Shade / Full Shade |
| Water Needs | Enum | Low / Medium / High |
| Hardiness Zone | Text | USDA zone (e.g., "5-8") |
| Notes | Text | Free-form notes |
| Custom Fields | Key-Value | User-defined additional data |

- **FR-PLANT-05**: All metadata fields editable in properties panel
- **FR-PLANT-06**: Species field supports autocomplete from plant database
- **FR-PLANT-07**: When species selected from database, default values populated

### FR-5.3 Plant Database Integration
- **FR-PLANT-10**: Connect to Trefle.io API for plant species lookup (primary)
- **FR-PLANT-11**: Offline mode: cache previously fetched plant data locally (SQLite)
- **FR-PLANT-12**: User can create custom plant species entries (stored in local library)
- **FR-PLANT-13**: Search plants by common name, scientific name, or characteristics
- **FR-PLANT-14**: Graceful degradation with fallback chain:
  1. Trefle.io API (primary)
  2. Perenual API (secondary)
  3. Permapeople API (tertiary)
  4. Bundled plant database (offline)
  5. User-defined custom entries (always available)

## FR-6: Garden Beds

- **FR-BED-01**: Bed object type (polygon) for vegetable/flower beds
- **FR-BED-02**: Bed metadata: name, soil type, raised (yes/no), height if raised
- **FR-BED-03**: Beds can contain plant objects (visual grouping)
- **FR-BED-04**: Bed area automatically calculated and displayed
- **FR-BED-05**: Grid subdivision display option for planting layout

## FR-7: Measurement Tools

- **FR-MEAS-01**: Distance tool: click two points, displays distance in chosen units
- **FR-MEAS-02**: Persistent dimension annotations (add to plan, editable)
- **FR-MEAS-03**: Area display for selected polygon and circle objects
- **FR-MEAS-04**: Perimeter/circumference display for selected objects
- **FR-MEAS-05**: Scale bar overlay (Phase 6)
- **FR-MEAS-06**: Measurements snap to object vertices/edges

## FR-8: Object Library

- **FR-LIB-01**: User can define custom object templates
- **FR-LIB-02**: Template includes: name, default geometry, default styling, metadata fields
- **FR-LIB-03**: Library stored locally, persists across projects
- **FR-LIB-04**: Drag templates from library to canvas to create instances
- **FR-LIB-05**: Update template propagates to instances (optional, user-confirmed)
- **FR-LIB-06**: Import/export library as JSON for sharing

## FR-9: File Operations

### FR-9.1 Project Files
- **FR-FILE-01**: Native project format: `.ogp` (Open Garden Planner) - JSON-based
- **FR-FILE-02**: Project file contains all object data, metadata, layer configuration
- **FR-FILE-03**: Background images: option to embed (base64) or reference (path)
- **FR-FILE-04**: Project files are human-readable and version-control friendly
- **FR-FILE-05**: Save/Save As/Open dialogs with recent files list
- **FR-FILE-06**: Auto-save to temp location (configurable interval)
- **FR-FILE-07**: Crash recovery from auto-save

### FR-9.2 Export
- **FR-EXP-01**: Export to PNG (configurable DPI: 72, 150, 300)
- **FR-EXP-02**: Export to SVG (vector, scalable)
- **FR-EXP-03**: Print support with scaling and page layout (Phase 6)
- **FR-EXP-04**: Export selected objects only or entire canvas
- **FR-EXP-05**: Export includes visible layers only (or all, user choice)
- **FR-EXP-06**: Plant list export: CSV with all plant metadata
- **FR-EXP-07**: Export to DXF (AutoCAD R2010+); shapes map to LWPOLYLINE/CIRCLE/ELLIPSE; layers preserved; 1 unit = 1 cm
- **FR-EXP-08**: Multi-page PDF report with configurable pages (cover, overview, bed details, plant list, legend); paper size A4/A3/Letter/Legal, landscape/portrait

### FR-9.3 Import
- **FR-IMP-01**: Import `.ogp` project files
- **FR-IMP-02**: Import SVG as editable objects (basic support, future)
- **FR-IMP-03**: Import plant list from CSV (batch add plants, future)
- **FR-IMP-04**: Import DXF (LINE, LWPOLYLINE, CIRCLE, ARC, ELLIPSE, SPLINE); configurable scale factor; layer selection; single undo action

## FR-10: User Interface

### FR-10.1 Main Window Layout
```
+------------------------------------------------------------------+
|  Menu Bar                                                         |
+----------+----------------------------------------+--------------+
|          |                                        |              |
|  Object  |                                        |  Properties  |
|  Gallery |              Canvas                    |    Panel     |
|          |                                        |              |
|          |                                        +--------------+
|          |                                        |              |
|          |                                        |   Layers     |
|          |                                        |    Panel     |
+----------+----------------------------------------+--------------+
|  Status Bar (coordinates, zoom level, selection info)             |
+------------------------------------------------------------------+
```

### FR-10.2 UI Requirements
- **FR-UI-01**: Modern, flat design consistent with Windows 11 aesthetics
- **FR-UI-02**: Branded green theme with light/dark variants
- **FR-UI-03**: Fixed sidebar panels (not dockable/floating)
- **FR-UI-04**: Keyboard shortcuts for all common operations
- **FR-UI-05**: Context menus (right-click) for relevant actions
- **FR-UI-06**: Tooltips on all toolbar buttons
- **FR-UI-07**: Status bar: cursor coordinates, zoom %, selection count, current tool
- **FR-UI-08**: Welcome screen with recent files
- **FR-UI-09**: Remember window size, position, panel states between sessions
- **FR-UI-10**: Visual thumbnail gallery sidebar for object/plant browsing
- **FR-UI-11**: Fullscreen preview mode (F11) hiding all UI overlays
- **FR-UI-12**: Toggleable object labels on canvas

### FR-10.3 Object Gallery Sidebar
- Category-based thumbnail gallery (Trees, Shrubs, Flowers, Furniture, etc.)
- Each item: illustration thumbnail (~64-80px) + name label
- Click thumbnail to enter placement mode
- Drag from thumbnail to canvas for direct placement
- Search/filter box at top
- Collapsible categories

### FR-10.4 Accessibility
- **FR-UI-20**: Keyboard navigation for all functions
- **FR-UI-21**: High contrast mode support
- **FR-UI-22**: Configurable font sizes in UI

## FR-11: Internationalization

- **FR-I18N-01**: All UI strings translatable via Qt Linguist (tr() calls)
- **FR-I18N-02**: English as default language
- **FR-I18N-03**: German translation shipped at launch
- **FR-I18N-04**: Language selectable in Settings
- **FR-I18N-05**: Extensible: contributors can add languages via .ts files
- **FR-I18N-06**: Plant scientific names not translated (Latin)

## FR-12: Visual Rendering

- **FR-VIS-01**: Tileable PNG textures for materials (grass, wood, stone, water, etc.)
- **FR-VIS-02**: Illustrated SVG plant shapes (category-based + unique popular species)
- **FR-VIS-03**: Subtle drop shadows on all objects (toggleable)
- **FR-VIS-04**: Visual scale bar overlay on canvas
- **FR-VIS-05**: Object labels (plant names, custom text) toggleable per-object and globally

## FR-13: Additional Object Types (Phase 6)

### Outdoor Furniture
- Table (rectangular, round), chair, bench, parasol/umbrella, lounger, BBQ/grill, fire pit, planter/pot

### Garden Infrastructure
- Raised bed, compost bin, greenhouse, cold frame, rain barrel, water tap, tool shed

### Path & Fence Styles
- Paths: gravel, stepping stones, paved, wooden boardwalk, dirt
- Fences: wooden, metal/wrought iron, chain link, hedge (living fence), stone wall

## FR-14: Snapping & Alignment (Phase 6)

- **FR-SNAP-01**: Snap to object edges and centers (with visual guide lines)
- **FR-SNAP-02**: Align tools: left, right, top, bottom, center horizontal, center vertical
- **FR-SNAP-03**: Distribute tools: horizontal, vertical (equal spacing)
- **FR-SNAP-04**: Snap toggleable independently from grid snap
- **FR-SNAP-05**: Visual snap guide lines during drag operations

## FR-15: Soil Health Tracking (Phase 12, US-12.10)

- **FR-SOIL-01**: Per-bed soil test entry via right-click → "Add soil test…"; project-wide default via Garden → "Set default soil test…"
- **FR-SOIL-02**: Records pH (0–14), Rapitest categorical NPK levels (N/P 0–4, K 1–4) and secondary nutrients (Ca/Mg/S Low/Medium/High), free-text notes, and optional Lab-mode ppm values
- **FR-SOIL-03**: Effective record hierarchy — bed's latest → project-wide default → none
- **FR-SOIL-04**: Records persist in the `.ogp` file under top-level `soil_tests` and survive save/load round-trip
- **FR-SOIL-05**: Adding a record is undoable via the standard command stack and marks the project dirty
- **FR-SOIL-06** (US-12.10b): Canvas overlay tints beds by overall / pH / N / P / K health bucket; untested beds show a hatched-grey pattern
- **FR-SOIL-07** (US-12.10c): Amendment calculator emits per-bed quantities (g or kg) for pH/NPK/secondary deficits; an Amendment Plan dialog aggregates totals across beds
- **FR-SOIL-08** (US-12.10d): Plant-soil compatibility warnings draw an amber (1 mismatch) or red (≥2 mismatches) border on beds whose hosted plants conflict with the effective soil record; mismatches also surface as Dashboard cards
- **FR-SOIL-09** (US-12.10e): The soil-test dialog's History tab lists past records date-descending and renders pH/N/P/K trend sparklines
- **FR-SOIL-10** (US-12.10e): Seasonal reminder badge — a clock icon at a bed's top-right corner, shown only in sampling months (Mar/Apr, Sep/Oct) when the latest test is older than 180 days; clicking it opens the soil-test dialog. Untested beds are deliberately not flagged.

## FR-16: Pest & Disease Log (Phase 12, US-12.7)

- **FR-PEST-01**: Per-bed and per-plant pest/disease entry via right-click → "Log pest/disease…" on bed-typed rectangle/ellipse/polygon items and plant-typed circle items.
- **FR-PEST-02**: Records date (ISO 8601), kind (`pest` | `disease`), name, severity (`low` | `medium` | `high`), free-text treatment, optional photo, and free-text notes. An optional `resolved_date` marks an issue inactive.
- **FR-PEST-03**: Photos are stored as base64 JPEG inside the record, downscaled to ≤ 1024 px max edge at quality 85 — preserves the project's single-file portability (no sidecar).
- **FR-PEST-04**: Records persist in the `.ogp` file under top-level `pest_disease_logs` (FILE_VERSION ≥ 1.4) and survive save/load round-trip; older files load with an empty log.
- **FR-PEST-05**: Add / edit / delete operations are undoable via the standard command stack and mark the project dirty.
- **FR-PEST-06**: The dialog's History tab lists past records for the target newest first; per-row Edit / Delete actions route through undoable commands.
- **FR-PEST-07**: Active issues (records with `resolved_date is None`) surface on the Dashboard as task cards labelled "*kind* on *target*: *name*" with severity-derived urgency (high = today, medium = this week, low = coming up). Marking the card "Done" sets the record's `resolved_date` to today via an undoable `EditPestDiseaseCommand`.
