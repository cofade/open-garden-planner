# Open Garden Planner - Product Requirements Document

## 1. Overview

### 1.1 Product Vision

Open Garden Planner is an open-source desktop application that enables home gardeners to create metrically accurate 2D plans of their property and garden. Unlike existing tools that are either expensive subscription-based software or imprecise visual-only planners, Open Garden Planner combines CAD-like precision with garden-specific features—all in a free, open-source package.

**For gardeners who value precision and modern tools while staying independent and valuing transparency. We garden with passion—and we want tools that match that passion.**

### 1.2 Goals

- **Metric Accuracy**: Allow users to plan with centimeter-level precision, not just visual approximation
- **Rich Metadata**: Track plant species, varieties, planting dates, and growing requirements as first-class data
- **No Lock-in**: Open-source with standard file formats (JSON project files, PNG/SVG export)
- **Extensible**: Architecture supports future 3D visualization, sun simulation, and community plugins
- **Attractive UI**: Modern, polished interface that feels native to Windows
- **Contributor-Friendly**: Clean architecture, comprehensive tests, and CI/CD to attract open source contributors

### 1.3 Target Users

| Persona | Description | Primary Needs |
|---------|-------------|---------------|
| **Precision Gardener** | Engineering-minded hobbyist who wants exact measurements and documentation | Metric accuracy, plant metadata, exportable plans |
| **Property Planner** | Homeowner planning landscaping changes, needs to communicate with contractors | Scale drawings, dimension annotations, image tracing |
| **Vegetable Gardener** | Plans crop rotation, bed layouts, and companion planting | Bed definitions, plant spacing, variety tracking |

### 1.4 Out of Scope (Initial Release)

- 3D visualization (planned for future versions)
- Sun/shadow simulation (planned for future versions)
- Irrigation planning
- Mobile applications
- Multi-user collaboration
- Cloud storage/sync

### 1.5 Key Design Decisions

Decisions refined through requirements analysis:

| Area | Decision | Rationale |
|------|----------|-----------|
| **Distribution** | Both .exe (PyInstaller) and pip install | Maximum accessibility for different user types |
| **Coordinate Origin** | Bottom-left, Y-axis up | CAD convention, eases future 3D transition |
| **Panel Layout** | Fixed sidebar (not dockable) | Simpler UX, consistent layout |
| **Image Calibration** | Global scale for entire project | Simpler model, assumes consistent image sources |
| **Image Storage** | Embedded in project file by default | Portability over file size |
| **Snapping** | Both grid snap AND object snap | Professional-grade precision |
| **Box Selection** | AutoCAD convention (drag direction matters) | Left→right = enclosing, right→left = crossing |
| **Selection Click** | Click inside filled shapes selects | Intuitive for solid objects |
| **Rotation Pivot** | Object center | Simple, predictable behavior |
| **Label Scaling** | Scale with minimum readable size | Always readable at any zoom |
| **Canvas Size** | User specifies initial size, resizable later | Flexible without being unbounded |
| **Plant Visuals** | Stylized symbols per plant type | Visual distinction, more engaging than circles |
| **Undo History** | Clears on project close | Standard behavior, simpler implementation |
| **Session State** | Remember window size, position, recent files | Professional, convenient UX |
| **Plant Data Priority** | API integration first, then custom entries | Leverage existing plant databases |
| **API Fallback** | Trefle.io → Permapeople → Bundled DB → Custom | Graceful degradation |
| **Textures** | Start with simple patterns, add realistic later | Ship faster, enhance incrementally |
| **Dark Mode** | Defer to Phase 5 | Nice-to-have, not blocking |

---

## 2. Competitive Analysis

### 2.1 Existing Solutions

| Tool | Type | Strengths | Weaknesses |
|------|------|-----------|------------|
| **Garden Planner (smallblueprinter.com)** | Commercial, subscription | Easy to use, plant database | Expensive, no metric precision, web-only |
| **iScape** | Commercial, subscription | Good visualization, AR features | Mobile-focused, expensive, no precision tools |
| **FreeCAD** | Open source CAD | Excellent precision, 3D capable | Not garden-focused, steep learning curve, no plant metadata |
| **QCAD** | Open source CAD | Good 2D precision, DXF support | No garden features, technical UI |
| **elbotho/open-garden-planer** | Open source (GitHub) | Good concept, SVG-based | Incomplete, not usable, web-based |
| **Plant-it** | Open source (GitHub) | Plant tracking, Android | No spatial planning, mobile only |

### 2.2 Market Gap

No existing tool combines:
- Open source + free
- Desktop application with native feel
- CAD-like metric precision
- Garden-specific metadata and workflows
- Image import with calibration
- Modern, attractive UI

**Open Garden Planner fills this gap.**

---

## 3. Functional Requirements

### 3.1 Canvas and Coordinate System

#### 3.1.1 Metric Canvas
- **FR-CANVAS-01**: Canvas uses metric coordinate system (centimeters as base unit)
- **FR-CANVAS-02**: Display can show measurements in cm, m, or mixed (e.g., "2.35 m")
- **FR-CANVAS-03**: Canvas supports zoom from 1:1000 (overview) to 1:1 (detail) scale
- **FR-CANVAS-04**: Pan and zoom via mouse wheel, drag, and keyboard shortcuts

#### 3.1.2 Grid System
- **FR-GRID-01**: Optional visible grid overlay (toggleable via toolbar button)
- **FR-GRID-02**: Grid spacing configurable (10cm, 25cm, 50cm, 100cm)
- **FR-GRID-03**: Snap-to-grid toggleable (independent of grid visibility)
- **FR-GRID-04**: Grid renders efficiently at all zoom levels (adaptive detail)

#### 3.1.3 Background Image
- **FR-IMG-01**: Import background images (PNG, JPG, TIFF)
- **FR-IMG-02**: Calibrate image scale by marking a known distance (e.g., "this fence is 5.2m")
- **FR-IMG-03**: Two-point calibration: user clicks two points and enters the real-world distance
- **FR-IMG-04**: Adjust image opacity (0-100%)
- **FR-IMG-05**: Lock/unlock image layer to prevent accidental movement
- **FR-IMG-06**: Image stored as reference in project (path or embedded, user choice)
- **FR-IMG-07**: Multiple background images supported (e.g., different areas of property)

**Acceptance Criteria**:
- User imports a Google Maps screenshot, marks two corners of their house (known to be 12m), and the entire image scales correctly
- Drawing a shape and measuring it shows accurate dimensions

### 3.2 Drawing Tools

#### 3.2.1 Basic Shapes
- **FR-DRAW-01**: Line tool (click-click or click-drag)
- **FR-DRAW-02**: Rectangle tool (axis-aligned and rotated)
- **FR-DRAW-03**: Polygon tool (click to add vertices, double-click/Enter to close)
- **FR-DRAW-04**: Circle tool (click center, then click rim point to define radius)
- **FR-DRAW-05**: Ellipse tool (future enhancement)
- **FR-DRAW-06**: Arc tool
- **FR-DRAW-07**: Polyline tool (connected line segments, open path)

#### 3.2.2 Shape Properties
- **FR-DRAW-10**: Fill color (solid colors, predefined palette, custom color picker)
- **FR-DRAW-11**: Fill pattern/texture (grass, gravel, concrete, wood, water, soil, mulch)
- **FR-DRAW-12**: Stroke color and width
- **FR-DRAW-13**: Stroke style (solid, dashed, dotted)
- **FR-DRAW-14**: Opacity per shape

#### 3.2.3 Editing Operations
- **FR-EDIT-01**: Select tool (click, box select, Shift+click for multi-select)
- **FR-EDIT-02**: Move objects (drag or arrow keys with Shift for precision)
- **FR-EDIT-03**: Rotate objects (free rotation and snap to 15° increments)
- **FR-EDIT-04**: Scale objects (maintain aspect ratio with Shift)
- **FR-EDIT-05**: Delete objects (Delete key, context menu)
- **FR-EDIT-06**: Duplicate objects (Ctrl+D)
- **FR-EDIT-07**: Undo/Redo (Ctrl+Z, Ctrl+Y) with unlimited history per session
- **FR-EDIT-08**: Copy/Paste (Ctrl+C, Ctrl+V) including across projects
- **FR-EDIT-09**: Edit polygon vertices (add, remove, move individual points)

### 3.3 Layers

- **FR-LAYER-01**: Support multiple layers (minimum: Background, Property, Hardscape, Plants, Annotations)
- **FR-LAYER-02**: Default layers created with new project, user can add custom layers
- **FR-LAYER-03**: Layer visibility toggle
- **FR-LAYER-04**: Layer lock toggle (prevent editing)
- **FR-LAYER-05**: Layer opacity
- **FR-LAYER-06**: Layer reordering (drag in layer panel)
- **FR-LAYER-07**: Assign objects to layers (default based on object type, manual override)

### 3.4 Property Objects

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

### 3.5 Plant Objects

#### 3.5.1 Plant Representation
- **FR-PLANT-01**: Plants rendered as circles (canopy diameter) with species-appropriate styling
- **FR-PLANT-02**: Visual distinction between trees, shrubs, perennials, annuals
- **FR-PLANT-03**: Optional label showing name/species
- **FR-PLANT-04**: Visual indicator for plant status (healthy, needs attention, planned)

#### 3.5.2 Plant Metadata (per instance)
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
- **FR-PLANT-07**: When species selected from database, default values populated (sun, water, etc.)

#### 3.5.3 Plant Database Integration
- **FR-PLANT-10**: Connect to Trefle.io API for plant species lookup (primary source)
- **FR-PLANT-11**: Offline mode: cache previously fetched plant data locally (SQLite)
- **FR-PLANT-12**: User can create custom plant species entries (stored in local library)
- **FR-PLANT-13**: Search plants by common name, scientific name, or characteristics
- **FR-PLANT-14**: Graceful degradation with fallback chain:
  1. Trefle.io API (primary, requires internet)
  2. Permapeople API (secondary, requires internet)
  3. Bundled plant database (ships with app, works offline)
  4. User-defined custom entries (always available)

### 3.6 Garden Beds

- **FR-BED-01**: Bed object type (polygon) for vegetable/flower beds
- **FR-BED-02**: Bed metadata: name, soil type, raised (yes/no), height if raised
- **FR-BED-03**: Beds can contain plant objects (visual grouping)
- **FR-BED-04**: Bed area automatically calculated and displayed
- **FR-BED-05**: Grid subdivision display option for planting layout (e.g., square foot gardening)

### 3.7 Measurement Tools

- **FR-MEAS-01**: Distance tool: click two points, displays distance in chosen units
- **FR-MEAS-02**: Persistent dimension annotations (add to plan, editable)
- **FR-MEAS-03**: Area display for selected polygon and circle objects
- **FR-MEAS-04**: Perimeter/circumference display for selected polygon/polyline/circle objects
- **FR-MEAS-05**: Ruler overlay option (along canvas edge)
- **FR-MEAS-06**: Measurements snap to object vertices/edges

### 3.8 Object Library (Custom Definitions)

- **FR-LIB-01**: User can define custom object templates
- **FR-LIB-02**: Template includes: name, default geometry (shape, size), default styling, metadata fields
- **FR-LIB-03**: Library stored locally, persists across projects
- **FR-LIB-04**: Drag templates from library to canvas to create instances
- **FR-LIB-05**: Update template propagates to instances (optional, user-confirmed)
- **FR-LIB-06**: Import/export library as JSON for sharing

### 3.9 File Operations

#### 3.9.1 Project Files
- **FR-FILE-01**: Native project format: `.ogp` (Open Garden Planner) - JSON-based
- **FR-FILE-02**: Project file contains all object data, metadata, layer configuration
- **FR-FILE-03**: Background images: option to embed (base64) or reference (path)
- **FR-FILE-04**: Project files are human-readable and version-control friendly
- **FR-FILE-05**: Save/Save As/Open dialogs with recent files list
- **FR-FILE-06**: Auto-save to temp location (configurable interval)
- **FR-FILE-07**: Crash recovery from auto-save

#### 3.9.2 Export
- **FR-EXP-01**: Export to PNG (configurable DPI: 72, 150, 300)
- **FR-EXP-02**: Export to SVG (vector, scalable)
- **FR-EXP-03**: Export to PDF (optional, for printing)
- **FR-EXP-04**: Export selected objects only or entire canvas
- **FR-EXP-05**: Export includes visible layers only (or all, user choice)
- **FR-EXP-06**: Plant list export: CSV/JSON with all plant metadata

#### 3.9.3 Import
- **FR-IMP-01**: Import `.ogp` project files
- **FR-IMP-02**: Import SVG as editable objects (basic support)
- **FR-IMP-03**: Import plant list from CSV (batch add plants)

### 3.10 User Interface

#### 3.10.1 Main Window Layout
```
┌─────────────────────────────────────────────────────────────────┐
│  Menu Bar                                                        │
├─────────┬───────────────────────────────────────────┬───────────┤
│         │                                           │           │
│  Tool   │                                           │ Properties│
│  Panel  │              Canvas                       │   Panel   │
│         │                                           │           │
│         │                                           ├───────────┤
│         │                                           │           │
│         │                                           │  Layers   │
│         │                                           │   Panel   │
├─────────┴───────────────────────────────────────────┴───────────┤
│  Status Bar (coordinates, zoom level, selection info)            │
└─────────────────────────────────────────────────────────────────┘
```

#### 3.10.2 UI Requirements
- **FR-UI-01**: Modern, flat design consistent with Windows 11 aesthetics
- **FR-UI-02**: Dark mode support (system preference or manual toggle) - Phase 5
- **FR-UI-03**: Fixed sidebar panels (Properties, Layers) - not dockable/floating
- **FR-UI-04**: Keyboard shortcuts for all common operations
- **FR-UI-05**: Context menus (right-click) for relevant actions
- **FR-UI-06**: Tooltips on all toolbar buttons
- **FR-UI-07**: Status bar shows: cursor coordinates (cm), zoom %, selection count, current tool
- **FR-UI-08**: Sidebar with recent files (VS Code style) integrated into main window
- **FR-UI-09**: "What's New" popup shown after app update with release notes
- **FR-UI-10**: Automatic update check on startup with notification if new version available
- **FR-UI-11**: Remember window size, position, panel states, recent files between sessions

#### 3.10.3 Accessibility
- **FR-UI-20**: Keyboard navigation for all functions
- **FR-UI-21**: High contrast mode support
- **FR-UI-22**: Configurable font sizes in UI

---

## 4. Non-Functional Requirements

### 4.1 Performance

- **NFR-PERF-01**: Smooth canvas interaction (60fps pan/zoom) with up to 500 objects
- **NFR-PERF-02**: File save/load < 2 seconds for typical projects
- **NFR-PERF-03**: PNG export < 5 seconds for high-resolution output
- **NFR-PERF-04**: Memory usage < 500MB for typical projects
- **NFR-PERF-05**: Startup time < 3 seconds on modern hardware

### 4.2 Reliability

- **NFR-REL-01**: No data loss on crash (auto-save recovery)
- **NFR-REL-02**: Graceful handling of corrupted project files (partial load + warning)
- **NFR-REL-03**: Offline functionality (API unavailable should not block core features)

### 4.3 Maintainability

- **NFR-MAINT-01**: Modular architecture (see Section 6)
- **NFR-MAINT-02**: Comprehensive unit tests for geometry and data operations
- **NFR-MAINT-03**: Code documentation (docstrings, architecture docs)
- **NFR-MAINT-04**: Type hints throughout Python codebase

### 4.4 Extensibility

- **NFR-EXT-01**: Plugin architecture for future extensions (post-MVP)
- **NFR-EXT-02**: Data model supports additional object types without schema changes
- **NFR-EXT-03**: Rendering pipeline supports custom object renderers

---

## 5. Technical Architecture

### 5.1 Technology Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Language** | Python 3.11+ | Rapid development, strong ecosystem, contributor accessibility |
| **GUI Framework** | PyQt6 | Mature, native look, excellent 2D graphics (QGraphicsView), 3D-ready (Qt3D) |
| **Graphics** | QGraphicsView/Scene | Hardware-accelerated, handles thousands of objects, built-in pan/zoom |
| **Data Storage** | JSON (project files) | Human-readable, VCS-friendly, no external database needed |
| **Plant API** | Trefle.io REST API | Free, open source, comprehensive plant data |
| **Local Cache** | SQLite | Efficient local plant database cache |
| **Image Handling** | Pillow + Qt | Format support, scaling, memory efficiency |
| **Packaging** | PyInstaller + pip | Both single .exe and pip-installable package |
| **CI/CD** | GitHub Actions | Automated testing, linting, and release builds |

### 5.2 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Presentation Layer                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │  Canvas  │ │  Tools   │ │  Panels  │ │  Dialogs │           │
│  │  Widget  │ │  Widget  │ │ (Props,  │ │ (Export, │           │
│  │          │ │          │ │  Layers) │ │  Import) │           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │            │            │            │                   │
├───────┴────────────┴────────────┴────────────┴──────────────────┤
│                        Application Layer                         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────────┐ │
│  │   Document   │ │    Tools     │ │      Commands            │ │
│  │   Manager    │ │   Manager    │ │   (Undo/Redo Stack)      │ │
│  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────────┘ │
│         │                │                    │                  │
├─────────┴────────────────┴────────────────────┴─────────────────┤
│                          Domain Layer                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │  Geometry  │ │   Objects  │ │   Plants   │ │    Layers    │  │
│  │   Engine   │ │   Model    │ │   Model    │ │    Model     │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                       Infrastructure Layer                       │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │
│  │   File     │ │   Export   │ │  Plant DB  │ │   Settings   │  │
│  │   I/O      │ │   Engine   │ │    API     │ │   Storage    │  │
│  └────────────┘ └────────────┘ └────────────┘ └──────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

### 5.3 Key Design Decisions

#### 5.3.1 Coordinate System (3D-Ready)
All objects store coordinates in a 3D-ready format from day one.

**Origin**: Bottom-left corner of canvas (CAD convention)
**Y-axis**: Increases upward (mathematical/CAD convention, not screen coordinates)
**Units**: Centimeters internally, displayed as cm or m based on user preference

```python
@dataclass
class Point:
    x: float  # centimeters, positive = East/Right
    y: float  # centimeters, positive = North/Up (CAD convention)
    z: float = 0.0  # centimeters, elevation (unused in 2D, ready for 3D)
```

Note: Qt's QGraphicsView uses Y-down screen coordinates. The canvas view will apply a transform to flip the Y-axis for display while maintaining the CAD convention in the data model.

#### 5.3.2 Object Model
All drawable entities inherit from a common base:
```python
class GardenObject(ABC):
    id: UUID
    name: str
    layer_id: UUID
    geometry: Geometry  # Abstract geometry (supports 2D and future 3D)
    style: ObjectStyle  # Fill, stroke, opacity
    metadata: dict[str, Any]  # Extensible properties
    z_elevation: float = 0.0  # For future 3D
    height: float = 0.0  # For future 3D extrusion
```

#### 5.3.3 Command Pattern (Undo/Redo)
All modifications wrapped in commands:
```python
class Command(ABC):
    def execute(self) -> None: ...
    def undo(self) -> None: ...

class MoveObjectCommand(Command):
    def __init__(self, obj: GardenObject, old_pos: Point, new_pos: Point): ...
```

#### 5.3.4 Project File Format
```json
{
  "version": "1.0",
  "metadata": {
    "name": "My Garden",
    "created": "2025-01-15T10:30:00Z",
    "modified": "2025-01-20T14:22:00Z",
    "units": "cm",
    "location": {"lat": 52.52, "lon": 13.405}
  },
  "canvas": {
    "width": 5000,
    "height": 3000,
    "background_color": "#f5f5dc"
  },
  "layers": [...],
  "objects": [...],
  "background_images": [...],
  "plant_library": {...}
}
```

### 5.4 Module Structure

```
open_garden_planner/
├── main.py                 # Application entry point
├── app/
│   ├── __init__.py
│   ├── application.py      # QApplication setup, main window
│   └── settings.py         # User preferences, recent files
├── ui/
│   ├── __init__.py
│   ├── main_window.py      # Main window, menus, toolbars
│   ├── canvas/
│   │   ├── canvas_view.py  # QGraphicsView subclass
│   │   ├── canvas_scene.py # QGraphicsScene subclass
│   │   └── grid_renderer.py
│   ├── panels/
│   │   ├── tools_panel.py
│   │   ├── properties_panel.py
│   │   ├── layers_panel.py
│   │   └── library_panel.py
│   ├── dialogs/
│   │   ├── export_dialog.py
│   │   ├── calibration_dialog.py
│   │   └── plant_search_dialog.py
│   └── widgets/
│       ├── color_picker.py
│       └── texture_picker.py
├── core/
│   ├── __init__.py
│   ├── document.py         # Project document model
│   ├── commands.py         # Undo/redo command classes
│   ├── tools/
│   │   ├── base_tool.py
│   │   ├── select_tool.py
│   │   ├── draw_tools.py
│   │   └── measure_tool.py
│   └── geometry/
│       ├── primitives.py   # Point, Line, Polygon, etc.
│       ├── transforms.py   # Rotate, scale, translate
│       └── measurements.py # Distance, area calculations
├── models/
│   ├── __init__.py
│   ├── base_object.py      # GardenObject base class
│   ├── property_objects.py # House, Fence, Path, etc.
│   ├── plant.py            # Plant object with metadata
│   ├── bed.py              # Garden bed
│   └── layer.py            # Layer model
├── services/
│   ├── __init__.py
│   ├── file_service.py     # Save/load projects
│   ├── export_service.py   # PNG, SVG, PDF export
│   ├── plant_api.py        # Trefle.io integration
│   └── plant_cache.py      # Local SQLite cache
├── resources/
│   ├── icons/
│   │   ├── banner.png      # banner used for loading / landing screens and Github
│   │   ├── OGP_logo.png    # logo used for branding and UI iconography
│   ├── textures/
│   ├── styles/
│   └── default_library.json
├── tests/
│   ├── unit/
│   │   ├── test_geometry.py
│   │   ├── test_commands.py
│   │   ├── test_objects.py
│   │   ├── test_plant_model.py
│   │   └── test_serialization.py
│   ├── integration/
│   │   ├── test_file_io.py
│   │   ├── test_export.py
│   │   └── test_plant_api.py
│   └── ui/
│       ├── test_canvas.py
│       ├── test_tools.py
│       └── test_panels.py
├── pyproject.toml          # Project config, dependencies
├── requirements.txt        # Pinned dependencies
├── requirements-dev.txt    # Development dependencies (pytest, ruff, mypy)
├── CONTRIBUTING.md         # Contributor guide
├── LICENSE                 # GPLv3
└── README.md               # Project overview, installation, usage
```

---

## 6. Development Roadmap

### Phase 1: Foundation (v0.1)

**Goal**: Basic working application with canvas, drawing, and file operations.

| ID | User Story | Priority |
|----|------------|----------|
| US-1.1 | As a user, I can create a new project with specified dimensions | Must |
| US-1.2 | As a user, I can pan and zoom the canvas smoothly | Must |
| US-1.3 | As a user, I can draw rectangles and polygons on the canvas | Must |
| US-1.4 | As a user, I can select, move, and delete objects | Must |
| US-1.5 | As a user, I can save my project to a file and reopen it | Must |
| US-1.6 | As a user, I can undo and redo my actions | Must |
| US-1.7 | As a user, I can see my cursor coordinates in real-time | Must |
| US-1.8 | As a developer, I want the application to display the OGP logo icon on startup so that the brand identity is visible from the beginning | Should |
| US-1.9 | As a developer, I want the GitHub repository to display the banner image which makes it more appealing for users and contributors | Should |

**Technical Milestones**:
- [x] Project structure setup, dependencies, build system
- [x] Main window with menu bar and status bar
- [x] QGraphicsView canvas with pan/zoom
- [ ] Basic shape rendering (rectangle, polygon)
- [ ] Selection and transformation tools
- [ ] JSON serialization/deserialization
- [ ] Command pattern for undo/redo
- [x] Load and display `OGP_logo.png` (resolution 1024x1024, potentially make rescaled copies as needed) as the application icon (e.g. splash screen, window icon, executable icon, or about dialog)
- [x] Embed `banner.png` (resolution 1920x960) as banner at the top of the GitHub page's ReadMe


### Phase 2: Precision & Calibration (v0.2)

**Goal**: Image import, calibration, and measurement tools for real-world accuracy.

| ID | User Story | Priority |
|----|------------|----------|
| US-2.1 | As a user, I can import a background image (satellite photo) | Must |
| US-2.2 | As a user, I can calibrate the image by marking a known distance | Must |
| US-2.3 | As a user, I can toggle a grid overlay | Must |
| US-2.4 | As a user, I can snap objects to the grid | Should |
| US-2.5 | As a user, I can measure distances between any two points | Must |
| US-2.6 | As a user, I can see area/perimeter of selected polygons and circles | Should |
| US-2.7 | As a user, I can adjust background image opacity | Must |
| US-2.8 | As a user, I can lock the background image to prevent moving it | Should |
| US-2.9 | As a user, I can draw circles by clicking center then a rim point | Must |

**Technical Milestones**:
- [x] Image layer with transformation matrix
- [x] Two-point calibration algorithm
- [x] Grid rendering (adaptive to zoom level)
- [x] Snap-to-grid logic
- [x] Measurement tool (non-persistent)

### Phase 3: Objects & Styling (v0.3)

**Goal**: Rich object types with visual customization.

| ID | User Story | Priority |
|----|------------|----------|
| ~~US-3.1~~ | ~~As a user, I can add property objects (house, fence, path, etc.)~~ | ✅ Must |
| ~~US-3.2~~ | ~~As a user, I can set fill color for objects~~ | ✅ Must |
| ~~US-3.3~~ | ~~As a user, I can apply textures/patterns to objects~~ | ✅ Must |
| ~~US-3.4~~ | ~~As a user, I can set stroke style (color, width, dash pattern)~~ | ✅ Should |
| US-3.5 | As a user, I can add labels to objects displayed on canvas | Should |
| US-3.6 | As a user, I can organize objects into layers | Must |
| US-3.7 | As a user, I can show/hide and lock layers | Must |
| US-3.8 | As a user, I can copy and paste objects | Must |

**Technical Milestones**:
- [ ] Object type hierarchy (PropertyObject subclasses)
- [ ] Style system (fills, strokes, patterns)
- [ ] Texture rendering with Qt
- [ ] Layer model and UI panel
- [ ] Clipboard integration

### Phase 4: Plants & Metadata (v0.4)

**Goal**: First-class plant objects with metadata and database integration.

| ID | User Story | Priority |
|----|------------|----------|
| US-4.1 | As a user, I can add plant objects (tree, shrub, perennial) | Must |
| US-4.2 | As a user, I can set plant metadata (species, variety, dates) | Must |
| US-4.3 | As a user, I can search for plant species from online database | Should |
| US-4.4 | As a user, I can create custom plant species in my library | Must |
| US-4.5 | As a user, I can view plant details in a properties panel | Must |
| US-4.6 | As a user, I can add garden beds with area calculation | Must |
| US-4.7 | As a user, I can filter/search plants in my project | Should |

**Technical Milestones**:
- [ ] Plant model with full metadata schema
- [ ] Trefle.io API integration
- [ ] Local SQLite cache for plant data
- [ ] Custom plant library storage
- [ ] Properties panel for plant editing
- [ ] Plant rendering (species-appropriate symbols)

### Phase 5: Export & Polish (v0.5)

**Goal**: Production-ready release with export capabilities and polished UX.

| ID | User Story | Priority |
|----|------------|----------|
| US-5.1 | As a user, I can export my plan as PNG in various resolutions | Must |
| US-5.2 | As a user, I can export my plan as SVG | Must |
| US-5.3 | As a user, I can export a plant list as CSV | Should |
| US-5.4 | As a user, I can use keyboard shortcuts for all common actions | Should |
| US-5.5 | As a user, I can switch between light and dark mode | Should |
| US-5.6 | As a user, I see a welcome screen with recent projects | Should |
| US-5.7 | As a user, my work is auto-saved periodically | Must |

**Technical Milestones**:
- [ ] PNG export with DPI options
- [ ] SVG export
- [ ] CSV plant list export
- [ ] Keyboard shortcut system
- [ ] Dark mode theming
- [ ] Auto-save and crash recovery
- [ ] Welcome/start screen
- [ ] Windows installer (PyInstaller)

### Phase 6: Advanced Features (v0.6+)

**Future enhancements** (not in initial scope):

- Additional drawing tools (arcs, curves, bezier paths)
- DXF import/export for CAD interoperability
- 3D visualization (Qt3D integration)
- Sun path simulation
- Plant growth over time visualization
- Companion planting suggestions
- Print layout designer
- Plugin system
- Multi-language support

---

## 7. Development Workflow

### 7.1 Feature Development Process

Each feature follows this workflow:

1. **Define**: Identify the specific user story and acceptance criteria
2. **Test First**: Write unit tests for the feature's core logic
3. **Implement**: Write the code to make tests pass
4. **Integration Tests**: Add integration tests if the feature spans modules
5. **UI Tests**: Add UI tests for any visual/interactive components
6. **Manual Verification**: Hands-on testing to ensure everything works as intended
7. **Review**: All tests pass, code is clean, feature is complete
8. **Commit**: With descriptive commit message referencing the user story

### 7.2 Code Quality Standards

- **Type hints**: All functions must have type annotations
- **Docstrings**: Public classes and functions require docstrings
- **Linting**: Code must pass ruff checks (configured in pyproject.toml)
- **Type checking**: Code must pass mypy in strict mode
- **Test coverage**: New code must maintain >80% coverage

### 7.3 Git Workflow

- **main branch**: Always deployable, protected
- **Feature branches**: `feature/US-X.X-short-description`
- **Commits**: Small, atomic, well-described
- **PRs**: Required for all changes, must pass CI

---

## 8. Testing Strategy

**Philosophy**: Comprehensive automated testing is essential for quality and contributor confidence. Every feature must ship with tests. All tests must pass before merging.

### 7.1 Unit Tests (pytest)
- **Geometry module**: Point operations, polygon area, distance calculations, transformations, snapping algorithms
- **Command system**: Execute/undo/redo for all command types, edge cases
- **Object model**: Creation, modification, serialization of all object types
- **File I/O**: Serialization round-trips, backward compatibility, corrupted file handling
- **Export**: Output validation for PNG, SVG, CSV
- **Plant data**: API response parsing, caching, fallback logic

### 7.2 Integration Tests
- **Plant API**: Mock server responses, timeout handling, cache invalidation
- **Document operations**: Full workflow tests (create, modify, save, load, export)
- **Multi-object operations**: Selection, grouping, layer operations

### 7.3 UI Tests (pytest-qt)
- **Canvas interactions**: Pan, zoom, click, drag operations
- **Tool behavior**: Each drawing tool's complete workflow
- **Panel updates**: Properties panel reflects selection, layer panel syncs with document
- **Keyboard shortcuts**: All shortcuts function correctly

### 7.4 Manual Testing Checklist
Each feature requires hands-on testing before completion:
- [ ] Feature works as specified
- [ ] Undo/redo functions correctly for all operations
- [ ] Edge cases handled gracefully (empty selection, invalid input, etc.)
- [ ] UI updates correctly in all scenarios
- [ ] No performance regression

### 7.5 CI/CD Pipeline (GitHub Actions)
- **On every push**: Run linting (ruff), type checking (mypy), all tests
- **On PR**: Full test suite + coverage report
- **On release tag**: Build Windows .exe, create GitHub release with artifacts
- **Coverage requirement**: Maintain >80% coverage on non-UI code

---

## 9. Open Questions and Risks

### 8.1 Open Questions

| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Trefle.io rate limits and reliability? | Plant search UX | Test API, implement robust caching, Permapeople as fallback, bundled DB as last resort |
| Texture licensing for fill patterns? | Legal | Use CC0/public domain textures, document sources |
| DXF export complexity for future versions? | Interoperability | Evaluate ezdxf library, may need simplification |
| Qt6 3D capabilities vs dedicated engine? | Future 3D feature | Prototype with Qt3D, evaluate PyVista as alternative |
| Bundled plant database source? | Offline functionality | Evaluate USDA Plants Database, consider one-time Trefle.io bulk export |

### 8.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyQt6 licensing complexity (GPL/Commercial) | Medium | High | Use GPLv3, document clearly, ensure compliance |
| Performance with very large images | Medium | Medium | Implement image tiling/downsampling at zoom levels |
| Scope creep delaying MVP | High | High | Strict phase adherence, defer nice-to-haves |
| Limited development time (few hours/week) | High | Medium | Focus on quality over speed, attract contributors |
| Project not attracting contributors | Medium | High | Excellent documentation, clean code, contributor guide, CI/CD |
| External API deprecation | Low | Medium | Fallback chain: Trefle → Permapeople → Bundled DB |

### 8.3 Licensing

**GNU General Public License v3 (GPLv3)** - Confirmed

Rationale:
- Required for PyQt6 (unless commercial license purchased)
- Ensures derivative works remain open source
- Strong copyleft protects project from proprietary forks
- Well-understood in open source community

### 8.4 Community and Governance

**Feature Requests**: Open to community input, pivots, and voting. The goal is to avoid a dead project—community engagement is welcome.

**Contribution Model**:
- GitHub Issues for bug reports and feature requests
- Pull requests welcome with review process
- Clear CONTRIBUTING.md with code style, testing requirements
- All PRs must pass CI (tests, linting, type checking)

---

## 10. Success Metrics

### MVP (v0.5) Success Criteria
- [ ] User can complete end-to-end workflow: import image → calibrate → draw property → add plants → save → export PNG
- [ ] 10+ GitHub stars (indicator of interest)
- [ ] 1+ external contributor (pull request merged)
- [ ] No critical bugs in issue tracker for 2 weeks

### Long-term Goals
- Become the go-to open source garden planning tool
- Active community of contributors
- Featured in gardening/open source publications

---

## Appendix A: Keyboard Shortcuts (Planned)

| Action | Shortcut |
|--------|----------|
| New Project | Ctrl+N |
| Open Project | Ctrl+O |
| Save | Ctrl+S |
| Save As | Ctrl+Shift+S |
| Undo | Ctrl+Z |
| Redo | Ctrl+Y |
| Select All | Ctrl+A |
| Delete | Delete |
| Duplicate | Ctrl+D |
| Copy | Ctrl+C |
| Paste | Ctrl+V |
| Zoom In | Ctrl++ or Scroll Up |
| Zoom Out | Ctrl+- or Scroll Down |
| Fit to View | Ctrl+0 |
| Toggle Grid | G |
| Toggle Snap | S |
| Select Tool | V |
| Rectangle Tool | R |
| Polygon Tool | P |
| Line Tool | L |
| Measure Tool | M |
| Plant Tool | T |

---

## Appendix B: References

- [Trefle.io API Documentation](https://trefle.io/)
- [Permapeople API Documentation](https://permapeople.org/knowledgebase/api-docs.html)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [QGraphicsView Framework](https://doc.qt.io/qt-6/qgraphicsview.html)
- [Qt3D Overview](https://doc.qt.io/qt-6/qt3d-index.html) (for future 3D)
