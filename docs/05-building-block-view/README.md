# 5. Building Block View

## 5.1 High-Level Architecture

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

## 5.2 Module Structure

```
src/open_garden_planner/
├── __main__.py                   # Entry point (python -m)
├── main.py                       # Application launch
├── app/
│   └── application.py            # GardenPlannerApp (QMainWindow)
├── core/
│   ├── commands.py               # Undo/redo command pattern
│   ├── project.py                # Save/load, ProjectManager
│   ├── object_types.py           # ObjectType enum, default styles
│   ├── fill_patterns.py          # Texture/pattern rendering
│   ├── geometry/                 # Point, Polygon, Rectangle primitives
│   └── tools/                    # Drawing tools
│       ├── base_tool.py          # ToolType enum, BaseTool ABC
│       ├── tool_manager.py       # ToolManager with signals
│       ├── select_tool.py        # Selection + box select + vertex editing
│       ├── rectangle_tool.py     # Rectangle drawing
│       ├── polygon_tool.py       # Polygon drawing
│       ├── circle_tool.py        # Circle drawing
│       ├── polyline_tool.py      # Polyline/path drawing
│       ├── plant_tool.py         # Plant placement
│       └── measure_tool.py       # Distance measurement
├── ui/
│   ├── canvas/
│   │   ├── canvas_view.py        # QGraphicsView: pan/zoom, key/mouse handling
│   │   ├── canvas_scene.py       # QGraphicsScene: holds all objects
│   │   └── items/                # QGraphicsItem subclasses
│   │       ├── garden_item.py    # Base item (GardenItem)
│   │       ├── rectangle_item.py # Rectangle rendering
│   │       ├── polygon_item.py   # Polygon rendering
│   │       ├── circle_item.py    # Circle rendering
│   │       ├── polyline_item.py  # Polyline rendering
│   │       ├── plant_item.py     # Plant rendering (CircleItem)
│   │       └── background_image_item.py
│   ├── panels/                   # Sidebar panels
│   │   ├── drawing_tools_panel.py
│   │   ├── properties_panel.py
│   │   ├── layers_panel.py
│   │   ├── find_plants_panel.py
│   │   └── plant_details_panel.py
│   ├── dialogs/                  # Modal dialogs
│   │   ├── new_project_dialog.py
│   │   ├── welcome_dialog.py
│   │   ├── export_dialog.py
│   │   └── settings_dialog.py
│   ├── widgets/
│   │   └── toolbar.py            # MainToolbar
│   └── theme.py                  # Light/Dark theme system
├── services/
│   └── plant_api.py              # Trefle.io/Permapeople integration
└── resources/
    ├── icons/                    # App icons, banner
    │   └── tools/                # SVG tool icons
    ├── textures/                 # Tileable PNG textures (Phase 6)
    ├── plants/                   # Plant SVG illustrations (Phase 6)
    └── objects/                  # Object SVG illustrations (Phase 6)

tests/
├── unit/                         # Unit tests
├── integration/                  # Integration tests
└── ui/                           # UI tests (pytest-qt)
```

## 5.3 Object Model

All drawable entities inherit from a common base:

```python
class GardenObject(ABC):
    id: UUID
    name: str
    layer_id: UUID
    geometry: Geometry        # Abstract geometry
    style: ObjectStyle        # Fill, stroke, opacity
    metadata: dict[str, Any]  # Extensible properties
    rotation: float           # Degrees
    z_elevation: float = 0.0  # For future 3D
    height: float = 0.0       # For future 3D extrusion
```

### Object Type Hierarchy

```
GardenObject (ABC)
├── ShapeObject
│   ├── RectangleObject (house, garage, terrace, driveway)
│   ├── PolygonObject (custom shapes, garden beds)
│   ├── CircleObject (ponds, circular features)
│   └── PolylineObject (fences, paths, walls)
├── PlantObject
│   ├── TreePlant
│   ├── ShrubPlant
│   ├── PerennialPlant
│   ├── AnnualPlant
│   └── GroundCoverPlant
├── FurnitureObject (Phase 6)
│   ├── Table, Chair, Bench, Parasol, BBQ, etc.
└── InfrastructureObject (Phase 6)
    ├── RaisedBed, CompostBin, Greenhouse, etc.
```

## 5.4 Project File Format

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
