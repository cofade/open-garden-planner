# 12. Glossary

## 12.1 Terms

| Term | Definition |
|------|-----------|
| **arc42** | Template for software architecture documentation (12 sections) |
| **Canvas** | The main drawing area where garden objects are placed and manipulated |
| **Canopy Diameter** | The spread/width of a tree or shrub's foliage when viewed from above |
| **Amendment** | Soil-improving substance (lime, blood meal, compost, etc.) loaded from `resources/data/amendments.json`. Carries application rate (g/m²) and per-fix effect coefficients used by the calculator |
| **Bundled Species DB** | Curated `resources/data/plant_species.json` shipped with the app (~120 records covering every gallery thumbnail, full pH/NPK/sun/water/calendar fields per species). Looked up on canvas drop and tool draw by scientific name → common name → alias to auto-populate `metadata["plant_species"]`; the long tail still falls through to the on-demand API search (issue #170) |
| **AmendmentRecommendation** | Calculator output for one substance applied to one bed: amendment + grams + rationale (e.g. "Raises pH 5.8 → 6.5") |
| **Calibration** | The process of marking a known distance on an image to establish metric scale |
| **Command Pattern** | Design pattern where every modification is wrapped in an object with execute/undo methods |
| **Garden Bed** | A defined planting area (polygon) that can contain plant objects |
| **GardenObject** | Base class for all drawable entities on the canvas |
| **Layer** | A logical grouping of objects for organization and visibility control |
| **LOD** | Level of Detail — rendering different detail levels at different zoom levels |
| **NPK** | Macronutrients tracked in soil tests: Nitrogen (N), Phosphorus (P), Potassium (K) |
| **OGP** | Open Garden Planner (the application) |
| **.ogp** | Project file format (JSON-based) |
| **Object Snap** | Automatic snapping of new/moved objects to edges/vertices of existing objects |
| **Plant Type** | Category of plant: tree, shrub, perennial, annual, ground cover |
| **Polyline** | A connected series of line segments (open path) used for fences, paths, walls |
| **QGraphicsScene** | Qt class that manages all 2D items on the canvas |
| **QGraphicsView** | Qt class that provides the viewport/widget for displaying the scene |
| **Rapitest scale** | Categorical NPK / Ca-Mg-S labels (Depleted/Deficient/Adequate/Sufficient/Surplus and Low/Medium/High) used by consumer soil test kits and stored on `SoilTestRecord` |
| **Scene Coordinates** | Real-world metric coordinates used internally (centimeters) |
| **Seed Gap** | A species placed on the canvas that has no matching packet in `ProjectData.seed_inventory` — surfaces as a row in the Shopping List Seeds category |
| **Shopping List** | Aggregated buying list (Plants / Seeds / Materials) produced from the current plan; only user-entered prices persist with the project, the rows themselves are recomputed on each open |
| **ShoppingListItem** | One purchasable row: stable ID (e.g. `plant:<species_id>`), category, name, quantity, unit, optional price |
| **ShoppingListCategory** | Top-level group in the shopping list: `PLANTS`, `SEEDS`, or `MATERIALS` |
| **SoilTestRecord** | Single soil test entry: date, pH, NPK levels, secondary nutrients, optional ppm values, notes, optional soil texture |
| **SoilTestHistory** | Time-ordered list of `SoilTestRecord`s for one target (a bed UUID or `"global"` default) |
| **Smart composition** | US-12.11 calculator policy: each pick fully closes its primary nutrient deficit and credits all co-fixed nutrients at the same dose factor; greedy by breadth (count of outstanding deficits the substance touches), with organic-preferred and JSON-order tie-breakers |
| **Structural amendment** | Substance added to fix soil texture rather than nutrient levels — sand (drainage), perlite (aeration + drainage), vermiculite (water retention + aeration + CEC), diatomaceous earth (water retention + silica). Driven by `SoilTestRecord.soil_texture` |
| **Soil texture** | Optional `SoilTestRecord` field — `"sandy"`, `"loamy"`, `"clayey"`, or `"compacted"` (or `None`). Drives the structural-pick phase of the calculator |
| **Enabled set / Amendment library** | Per-project allowlist (`ProjectData.enabled_amendments`) of substance IDs the calculator may pick from. `None` (the default) means every bundled amendment is enabled; the user manages the allowlist via the checkbox panel inside the Amendment Plan dialog |
| **Garden Journal** | Free-standing, map-linked notes pinned to canvas locations. Each entry carries a date, plain text, optional photo, and scene coordinates (`JournalNote` in `models/journal_note.py`); the dedicated sidebar panel supports text search and date-range filtering |
| **Journal Pin** | The constant-screen-size `JournalPinItem` marker dropped on the canvas. Carries only the `note_id` reference; the note body lives in `ProjectData.garden_journal_notes` keyed by that id |
| **Screen Coordinates** | Pixel coordinates on the display; converted via QGraphicsView transform |
| **SVG** | Scalable Vector Graphics — vector image format used for icons and plant illustrations |
| **Tileable Texture** | A small image that can be seamlessly repeated to fill any area |
| **tr()** | Qt translation function used to mark strings for internationalization |
| **Relative coordinate input** | Typed point of the form `@dx,dy` interpreted relative to the active tool's `last_point`. Y is math-positive (up); the parser flips to scene-down. Empty anchor → input rejected. See ADR-021 |
| **Polar coordinate input** | Typed point of the form `@dist<angle` with angle in degrees, `0° = east`, CCW positive. `dist` and `angle` accept either decimal mark. Without an `@`, polar input is still interpreted as relative to `last_point` (CAD convention). See ADR-021 |
| **Dynamic Input** | The frameless distance/angle overlay that floats next to the cursor in the canvas viewport during multi-click drawing. Mirrors the same `CoordinateInputBuffer` as the status-bar field. Hidden when the active tool has no anchor point. See ADR-021 |
| **CoordinateInputBuffer** | `QObject` singleton (per CanvasView) that holds the typed coordinate text and the current anchor. Both the status-bar field and the Dynamic Input overlay subscribe to its signals; this single state prevents the two UI surfaces from drifting out of sync |
| **SnapProvider** | One snap mode (endpoint, center, edge, midpoint, intersection). Subclass of `core/snap/provider.SnapProvider`; yields `SnapCandidate`s for items near a query position. Activation toggled via the View menu and persisted in `AppSettings`. See ADR-020 |
| **SnapCandidate** | One potential snap point produced by a provider. Carries the point, the kind, a priority (lower wins on ties) and the source item |
| **SnapRegistry** | Collection of active `SnapProvider`s with priority-based tie-breaking. Owned by `CanvasView`; its content is driven by the View menu toggles |
| **PointSnapper** | Click-time entry point that combines the `SnapRegistry` with the quadtree spatial index. `CanvasView._maybe_apply_anchor_snap` calls it before every non-select tool mouse event |
| **Midpoint snap** | Snap to the midpoint of any straight edge from a rectangle, polygon, polyline or construction line. Glyph: filled green triangle |
| **Intersection snap** | Snap to the intersection of two straight edges from different items. Glyph: green X. Capped at 60 segments per query for predictable latency |
| **QuadTree (snap)** | Bounded-depth (max 6) spatial index built lazily on `QGraphicsScene.changed`; pre-filters items to a 4×threshold window around the cursor before providers run. Build < 60 ms / 1000 items, query < 1 ms |

## 12.2 Keyboard Shortcuts

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
| Fullscreen Preview | F11 |
| Print | Ctrl+P |

## 12.3 References

- [arc42 Documentation Template](https://arc42.org/)
- [Trefle.io API Documentation](https://trefle.io/)
- [Permapeople API Documentation](https://permapeople.org/knowledgebase/api-docs.html)
- [PyQt6 Documentation](https://www.riverbankcomputing.com/static/Docs/PyQt6/)
- [QGraphicsView Framework](https://doc.qt.io/qt-6/qgraphicsview.html)
- [Qt Linguist Manual](https://doc.qt.io/qt-6/qtlinguist-index.html)
- [NSIS Documentation](https://nsis.sourceforge.io/Docs/)
- [PyInstaller Documentation](https://pyinstaller.org/en/stable/)
