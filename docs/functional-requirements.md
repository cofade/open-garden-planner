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
- **FR-IMG-08**: Load satellite imagery directly from Google Maps via an embedded picker dialog: address search (Places Autocomplete), navigate the map, drag a rectangle, fetch via Static Maps API. Available when `OGP_GOOGLE_MAPS_KEY` is configured in the project `.env` (ADR-019).
- **FR-IMG-09**: Satellite imports land on the canvas at true real-world scale automatically (no manual two-point calibration), with `meters_per_pixel` derived analytically from the Web-Mercator zoom level and latitude. The manual `Calibrate Scale…` context-menu action remains available as an override.
- **FR-IMG-10**: Satellite imports persist in the `.ogp` project file with geo metadata (center, NW/SE bbox corners, zoom, source, timestamp) — older projects without this metadata continue to load unchanged.

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
- **FR-LAYER-08**: New layers are created at the top of the layer order and become the active layer, so newly drawn elements stay visible and selectable (issue #201)
- **FR-LAYER-09**: All layer operations are undoable via Ctrl+Z/Ctrl+Y: create, delete (including the item reassignment it causes), rename, reorder, visibility, lock, and opacity — an opacity slider drag coalesces into a single undo step

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
- **FR-PLANT-15** *(issue #170)*: On canvas drop or tool draw of a plant, look up the species in the bundled DB (`resources/data/plant_species.json`) by scientific name → common name → alias (case-insensitive). On hit, populate `metadata["plant_species"]` with the full record (pH, NPK demand, sun, water, calendar, hardiness) so the plant detail panel shows data immediately and US-12.10d soil-mismatch warnings fire automatically.
- **FR-PLANT-16** *(issue #170)*: Bundled DB ships records for **every species exposed by the gallery** (currently 118 entries: trees, shrubs, vegetables, herbs, berries, fruits, ornamentals). Every record has `ph_min`, `ph_max`, `nutrient_demand`, `n_demand`, `p_demand`, `k_demand` populated. Where the gallery's species string differs from the canonical common name (e.g. "pea" vs "Garden Pea", "apple tree" vs "Apple Tree"), records carry an optional `aliases` array. Misses fall through to the existing API search button (FR-PLANT-14).
- **FR-PLANT-17** *(issue #213)*: Assigning a database species to an **existing** generic plant — via the plant database panel (Load Custom / Create Custom) or the Plants-menu species search (`application.py`) — writes `metadata["plant_species"]` **and** resizes the drawn footprint so its **diameter equals the species' `max_spread_cm`** (the visible change the issue requires) while keeping the plant centred. The resize is **silent** in the common case; the only thing that prompts is a **manual `spacing_radius_cm` override that conflicts with the database value** — then a dialog offers **Apply database values** (default: resize the footprint and clear the override so the database cascades) or **Keep custom values** (override *and* placed footprint left untouched). The assignment is a single undoable step (`ApplySpeciesCommand`, one undo unit, dirties the document — metadata, override, and footprint radius all revert together). Species with no usable `max_spread_cm` only update metadata (no resize). The footprint is resized via `CircleItem.set_radius_centered()`, which keeps the rotation pivot on the new centre so a rotated plant does not drift on save/reload.

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
- **FR-FILE-08** (issue #199): Save/Open/export dialogs default to a safe, writable location — the open project's folder when one exists, otherwise `<Documents>/Open Garden Planner` (`app/paths.get_projects_dir()`). They must **never** default to the process working directory, which for a packaged build is the install folder; user data stored there is destroyed on upgrade/uninstall. Complemented installer-side by user-data preservation (see deployment view §7.2): the uninstaller backs up any `$INSTDIR\*.ogp` to `Documents\Open Garden Planner\Recovered Plans` before removing the install directory.

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
- **FR-SOIL-11** (US-12.11): Amendment library is user-toggleable. The Amendment Plan dialog hosts an inline collapsible panel listing every bundled amendment as a checkbox, grouped Organic / Mineral / Structural; the user disables substances they don't have on hand and the calculator only picks from the enabled set. The allowlist persists per project under `enabled_amendments`; `None` (the default) means every amendment is enabled.
- **FR-SOIL-12** (US-12.11): Multi-nutrient credit. When a single substance covers multiple deficits (e.g. NPK compound fertilizer 15-6-12), the calculator picks it once and credits all co-fixed nutrients in `AmendmentRecommendation.credits`; the rationale text reads e.g. "Raises N 1→3 + also raises P 1→3, K 1→3" instead of three separate rows. A `prefer_organic` flag on the project (default true) biases tie-breaks toward organic substances; the user can flip it from the same panel.
- **FR-SOIL-13** (US-12.11): Soil-texture-driven structural amendments. `SoilTestRecord` carries an optional `soil_texture` (`sandy`, `loamy`, `clayey`, `compacted`); after the nutrient phase the calculator emits structural-pick rows for sand / perlite / vermiculite / diatomaceous earth driven by the texture (clayey → drainage + aeration; sandy → water retention; compacted → aeration; loamy / `None` → no structural picks).

## FR-16: Shopping List (Phase 12, US-12.6)

- **FR-SHOP-01**: Garden → Shopping List… opens a modal dialog grouping items into Plants / Seeds / Materials.
- **FR-SHOP-02**: Plants are aggregated from canvas TREE/SHRUB/PERENNIAL items by the first available identifier on `metadata.plant_species` — `source_id`, then `scientific_name`, then `common_name`. Bundled-DB plants (where `source_id == ""`) are aggregated by `scientific_name`. The row shows count and the average current spread.
- **FR-SHOP-03**: Seed gaps = species placed in the plan but not present in the project's `seed_inventory`; one packet-sized row per gap.
- **FR-SHOP-04**: Materials roll in: (a) soil amendments aggregated across beds via `SoilService.calculate_amendments`, mirroring the Amendment Plan dialog totals; (b) one "Soil fill" row (m³) — total bed area × per-bed fill depth (default 30 cm, configurable via Properties Panel → "Soil depth" spinbox stored in `metadata["soil_depth_cm"]`); (c) one "Mulch" row (m²) — total bed area. IDs `"soil_fill:m3"` and `"mulch:m2"` are stable so saved prices survive plan rebuilds.
- **FR-SHOP-05**: User-entered prices are editable in the dialog and persist with the project file under `shopping_list_prices` (keyed by item ID); reopening the project restores them. Orphan entries (items no longer in the plan) are pruned on project save.
- **FR-SHOP-08**: Canonical species key — `models.plant_data.species_key(species_dict)` is the single sanctioned way to derive a stable dict key from a species dict (priority: `source_id` → `scientific_name` → `common_name`, normalised lower+strip). See ADR-016.
- **FR-SHOP-06**: Export targets — CSV (`ExportService.export_shopping_list_to_csv`), PDF (`PdfReportService.export_shopping_list_to_pdf`), and tab-separated clipboard text.
- **FR-SHOP-07**: Amendment Plan dialog hands off to the shopping list via an "Add to Shopping List" button (replacing the prior plain-text clipboard placeholder).

## FR-17: Pest & Disease Log (Phase 12, US-12.7)

- **FR-PEST-01**: Right-click on any bed (rectangle/circle/polygon with a bed-type) or any plant (circle item) shows "Log Pest/Disease…" in the context menu, opening `PestLogDialog`.
- **FR-PEST-02**: Each entry stores date, type (`pest`/`disease`), name, severity (`low`/`medium`/`high`), treatment notes, free-form notes, optional photo, and a `resolved` flag (`PestLogRecord` in `models/pest_log.py`).
- **FR-PEST-03**: Records are persisted under top-level key `pest_disease_logs` in the .ogp file, shape `{target_id: PestLogHistory.to_dict()}` where `target_id` is the bed or plant UUID.
- **FR-PEST-04**: Photos attached via the dialog are copied into `{project_dir}/pest_photos/{uuid}_{filename}`; the record stores a project-relative POSIX path so the project file remains portable. Attaching a photo requires a saved project (button disabled with explanatory tooltip otherwise).
- **FR-PEST-05**: All add/edit/delete actions go through `AddPestLogCommand` / `EditPestLogCommand` / `DeletePestLogCommand`, which snapshot the prior history dict for undo/redo.
- **FR-PEST-06**: A "History" tab in the dialog lists past entries for the same target sorted newest-first, with per-row Edit and Delete buttons; resolved rows are visually flagged but not hidden.
- **FR-PEST-07**: A sidebar `PestOverviewPanel` ("Active Pest/Disease Issues") aggregates every unresolved record across the garden, sorted newest-first; double-clicking a row reopens the dialog focused on that target. Targets that no longer exist on the canvas display as "(deleted item)".
- **FR-PEST-08**: When a new season is created (Garden → New Season), only `resolved=False` records carry forward to the new season file. Resolved entries stay in the previous season file as historical record. This makes permanent issues (e.g. tree borers) persist while one-off treated outbreaks (e.g. an aphid bloom) drop off automatically.

## FR-18: Garden Journal (Phase 12, US-12.9)

- **FR-JOURNAL-01**: The Journal Pin tool (toolbar / shortcut **J**) drops a map-pin marker at the click position and opens `JournalNoteDialog` for the new entry. Pins use `ItemIgnoresTransformations` so they stay at a constant screen size at every zoom level.
- **FR-JOURNAL-02**: Each entry stores ISO date, multi-line plain text, optional photo, and the pin's scene coordinates (`JournalNote` in `models/journal_note.py`). Notes are persisted under top-level key `garden_journal_notes` in the .ogp file, keyed by the note's own UUID (independent of any bed or plant).
- **FR-JOURNAL-03**: All add / edit / delete actions are wrapped in `AddJournalNoteCommand` / `EditJournalNoteCommand` / `DeleteJournalNoteCommand`, snapshotting the prior dict for undo/redo. The pin item and note dict are added and removed atomically.
- **FR-JOURNAL-04**: Photo attachments are copied into `{project_dir}/journal_photos/{uuid}_{filename}` (parallel to `pest_photos/`); the note stores a project-relative POSIX path so .ogp files stay portable. Attaching a photo requires a saved project (button disabled with explanatory tooltip otherwise).
- **FR-JOURNAL-05**: A sidebar `JournalPanel` ("Garden Journal") lists all notes reverse-chronologically with a text-search box and an optional from/to date range filter. Double-clicking a row centres the canvas viewport on the pin and re-opens its editor.
- **FR-JOURNAL-06**: Double-clicking a pin (or "Edit Note…" in its right-click menu) opens `JournalNoteDialog`. The dialog's photo thumbnail is clickable and opens the file in the system image viewer; the click path is jailed to the project's `journal_photos/` directory.
- **FR-JOURNAL-07**: An optional "Garden journal notes" checkbox on the PDF export dialog adds a Garden Notes page to the multi-page report — a chronological list of every entry with date, text, and photo filename footnote. The page is rendered by `_render_garden_notes` in `pdf_report_service.py` and the option is plumbed via `PdfReportOptions.include_garden_notes` + `garden_journal_notes`.
- **FR-JOURNAL-08**: Journal notes are date-pinned historical records and do **not** carry over when a new season is created (`create_new_season` drops `journal_pin` canvas items and clears `garden_journal_notes` on the new season's data). The previous season file retains them as the canonical record.


## FR-19: CAD Precision — Typed Coordinate Input + Unified Snap (Phase 13, Package A)

- **FR-INPUT-01** (US-A1): Relative coordinate input `@dx,dy` types a vertex at `(last_point.x + dx, last_point.y − dy)`. The Y-flip implements math convention (`+dy` = up on screen). Available on every multi-click drawing tool (polyline, polygon, rectangle, circle, ellipse, construction line, construction circle) via the status-bar field and the Dynamic Input overlay. Without an anchor point, relative input is rejected with an inline red error tint *and* the parser's diagnostic surfaces in the field's tooltip (e.g. "Relative input requires an existing point to anchor to"); the diagnostic clears on the next keystroke or successful commit.
- **FR-INPUT-02** (US-A2): Polar coordinate input `@dist<angle` (degrees, `0° = east`, CCW positive) types a vertex at `last_point + (dist·cos θ, −dist·sin θ)`. Polar input without a `@` prefix is also accepted and treated as relative to the last point. Polar input requires exactly one `<`. Without an active `last_point` the parser raises `ParseError` (no silent fallback to origin).
- **FR-INPUT-03** (US-A4): Dynamic Input overlay — a frameless distance/angle entry follows the cursor inside the canvas viewport. Visible only when (a) dynamic input is enabled in the View menu, (b) the active tool is not SELECT, and (c) the active tool has a `last_point` to anchor against. Tab cycles fields, Enter commits, Esc returns focus to the canvas. The overlay and the status-bar field mirror a single `CoordinateInputBuffer` per CanvasView; typing in one updates the other live.
- **FR-INPUT-04**: Smart decimal/separator handling (rules A–F in `parser.py`): `;` is always a field separator, mixed `.`/`,` resolves to `.` decimal + `,` separator, comma-only inputs disambiguate by count (1 → separator, 3 → locale decimal pair, 2 → ambiguous with locale-decimal preference and `parse_alternative()` exposing the secondary reading). Whitespace also works as a separator everywhere.
- **FR-SNAP-04** (US-A3): Midpoint snap — yields the midpoint of every straight edge from rectangles, polygons, polylines and construction lines near the cursor. Toggle in View menu → "Snap to Midpoints"; persisted via `AppSettings.midpoint_snap_enabled` (default on). Visual glyph: filled green triangle.
- **FR-SNAP-05** (US-A3): Intersection snap — computes pairwise segment-segment intersections between edges of items near the cursor, capped at 60 segments per query for predictable latency. Self-intersections within a single item are filtered out to avoid duplicating endpoint mode at polygon vertices. Toggle in View menu → "Snap to Intersections"; persisted via `AppSettings.intersection_snap_enabled` (default on). Visual glyph: green X.
- **FR-SNAP-06**: Snap engine performance — a 1000-item scene snaps under 16 ms per query (60 fps budget); enforced by `tests/unit/test_point_snapper.py::test_perf_end_to_end`. The quadtree pre-filter rebuild itself stays under 60 ms; enforced by `tests/unit/test_snap_spatial_index.py::test_perf_thousand_items`.

## FR-20: CAD Precision — Curve Tools, Corner Edits, Reference-Point Snaps (Phase 13, Package B)

### FR-20.1 Curve Tools
- **FR-DRAW-08** (US-B1): Cubic Bezier pen tool. Click-drag per anchor — drag direction sets the outgoing handle; the incoming handle is mirrored automatically for a smooth tangent default. Double-click or Enter commits the curve. ESC cancels. A placed curve is reshaped in place via control handles (see FR-EDIT-12). Shortcut: `B`.
- **FR-DRAW-09** (US-B2): 3-point arc tool. Click **start → end → bulge** — the 2nd click sets the arc's end and the 3rd sets the curvature (the point the arc bulges through). The unique circular arc through the three points is computed via the circumcenter (`core/cad_geometry.arc_from_three_points`) and rendered as an `ArcItem`. (Click order chosen per manual-test feedback on #195: users fix the span first, then dial in curvature, rather than the classic start→through→end order.) The arc is rendered from exact cubic-Bézier segments (`arc_to_painter_path`), so the drawn curve terminates precisely on the user's clicks at any radius — Qt's `arcTo` could otherwise drift the rendered end by millimetres on a shallow, large-radius arc (FR-EDIT-13, ADR-025). If the three points are collinear (twice the signed triangle area ≤ 1.0), the tool falls back to a 2-vertex polyline (start→end) and a status-bar note. Shortcut: `A`.

### FR-20.2 Corner Editing
- **FR-EDIT-10** (US-B3): Fillet tool — round a polyline / polygon / rectangle corner with a tangent arc. The picked corner vertex is split into two tangent points (at distance `r/tan(α)` along each edge from the corner) and a free-standing `ArcItem` is added between them. The most-recently-used radius persists in `AppSettings.fillet_last_radius_cm`; press `R` mid-session to change it. If the radius is too large for the corner (offset > either edge length) the click is ignored with a status-bar hint. Shortcut: `Shift+F`. Filleting a rectangle is a **destructive conversion** (rect → 5-vertex polygon + arc); undo restores the rectangle (ADR-022).
- **FR-EDIT-11** (US-B3): Chamfer tool — bevel a corner with a straight cut at distance `d` along each adjacent edge. Same picking + persistence model as Fillet (`AppSettings.chamfer_last_distance_cm`, press `D` to change). No arc is created — only the host item's vertex list changes. Rectangles convert to polygons just like fillet. Shortcut: `Shift+C`.

### FR-20.3 Reference-Point Snaps
- **FR-SNAP-07** (US-B4): Nearest snap — yields the closest point on any visible edge or curve to the cursor as a fallback below all other snap modes. Priority 45 (lowest), default off (avoids surprising users who rely on free placement near edges). Toggle in View menu → "Snap to Nearest Point"; persisted via `AppSettings.nearest_snap_enabled`. Visual glyph: hourglass.
- **FR-SNAP-08** (US-B5): Perpendicular snap — drops a foot from the active tool's `last_point` onto the nearest straight edge in range. Requires a `reference_point` (no candidate without an anchor — purely cursor-based perpendicular is meaningless). Priority 25. Default off. Toggle in View menu → "Snap Perpendicular"; persisted via `AppSettings.perpendicular_snap_enabled`. Visual glyph: ⊥.
- **FR-SNAP-09** (US-B6): Tangent snap — from the active tool's `last_point` to a circle or arc, computes the contact point of the tangent line via `α = acos(r/|RC|)`. Returns the tangent point closer to the cursor when both solutions are visible. Reference points inside the circle or at the center yield no candidates. For arcs, candidates are filtered to those lying within the arc's sweep. Priority 26. Default off. Toggle in View menu → "Snap Tangent"; persisted via `AppSettings.tangent_snap_enabled`. Visual glyph: small circle + tangent line.
- **FR-SNAP-10** (issues #196/#192/#197): Snap → durable constraint. When a drawing tool commits a vertex at a snapped point, the snap becomes a geometric constraint stored on the scene's `ConstraintGraph` (via the undoable `AddConstraintCommand`): NEAREST/PERPENDICULAR on a straight edge → `POINT_ON_EDGE` (the vertex rides that named edge); MIDPOINT → `COINCIDENT` (vertex pinned to the edge midpoint); NEAREST on a circle/arc → `POINT_ON_CIRCLE`; TANGENT on a circle/arc → `POINT_ON_CIRCLE` + the new `TANGENT` constraint (TANGENT = edge⟂radius; the pair welds the contact to the rim *and* keeps the edge tangent, robustly under drag — see ADR-024). The source edge is identified by `SnapCandidate.source_edge_index` and resolved to concrete anchors by matching `get_anchor_points(source)`. Emitted constraints are enforced by the existing drag pipeline: dragging the reference item drags the constrained vertex along (`_compute_constraint_propagation`), and dragging the constrained item keeps its vertex on the edge/circle (`_enforce_point_on_edge_positions`). A perpendicular snap intentionally emits `POINT_ON_EDGE` rather than the rotation-only `PERPENDICULAR` type (see ADR-024).

### FR-20.4 Paper Space — DROPPED

US-B7 (Paper Space MVP) and the FR-LAYOUT-01 … FR-LAYOUT-06 entries that previously lived here were removed during PR #191 manual-test review. The existing `pdf_report_service` (FR-12.5) already produces multi-page PDFs at chosen paper sizes (A4 / A3 / Letter / Legal) with a built-in scale bar, which covers the user-visible value a Paper Space tab would have provided. The `paper_space/` UI package, viewport item, title block item, scale bar item, and the `paper_layouts` persistence schema were all deleted from the codebase before merge. `FILE_VERSION` stays at 1.4 because the bezier and arc item types (also part of Package B) are still real. The loader silently ignores any `paper_layouts` key found in `.ogp` files saved by short-lived draft builds.

### FR-20.5 Curve Editing (Package B follow-up)
- **FR-EDIT-12** (US-B9, issue #193): In-place reshape of placed Bezier and Arc curves. Selecting a curve shows draggable control handles (`CurveEditMixin` + `CurveControlHandle`); deselecting hides them. *Bezier*: an on-curve handle per anchor (drag carries both tangent handles along) plus a tangent handle for each anchor's active control point — dragging a tangent mirrors the opposite one for a smooth (C1) join, **Alt** breaks it into a corner; endpoint anchors expose only their single live handle. *Arc*: start / through / end handles (any drag recomputes the 3-point arc, so the through-point changes curvature with endpoints fixed) plus a read-only centre marker; a drag that would make the points collinear is rejected. Each drag commits exactly one undo step (`SetCurveGeometryCommand`, geometry-snapshot). The arc persists its through-point (additive `through_x`/`through_y`; legacy files derive the angular midpoint) so handles round-trip through save/reload. Reshape only — adding/deleting anchors or arc control points is out of scope. (ADR-025.)
- **FR-EDIT-13** (US-B11, issue #195): 3-point arc endpoint precision — the rendered arc must terminate on the user's clicks within 1e-3 cm at any radius/sweep. Implemented by rendering arcs from exact cubic-Bézier segments rather than Qt's `arcMoveTo`/`arcTo` (see FR-DRAW-09, ADR-025). The fillet arc inherits the same precise rendering.
- **FR-EDIT-14** (US-B4, issue #187): Mirror tool — reflect the selected shapes across a user-defined axis. Workflow: select shapes → `Shift+M` → click axis start → click axis end (**Shift** constrains the axis to 0/45/90°) → a small modal asks **Copy** (default) or **Move**. *Copy* adds reflected duplicates (fresh ids, so — like paste — copies start unconstrained) and keeps the originals; *Move* replaces the originals with reflections that keep their `item_id`, so existing constraints stay bound. Selecting a bed auto-includes its plants so they reflect with the bed. The reflected result is clamped back onto the canvas (shifted as a group) if the axis would push it off-bounds. One undo step per mirror (`MirrorItemsCommand`). Supported types: polyline, polygon, rectangle, ellipse, circle, arc, bezier — plus rectangle/circle-based SVG furniture & plants, which reflect *positionally* and render un-flipped (LibreCAD behaviour). Text, callouts, journal pins, construction geometry, background image, and groups are skipped with a status note. Geometry is reflected by rebuilding each item (not a Qt mirror transform), so results round-trip through save/load and DXF. Distinct from the Symmetry *constraint* (`CONSTRAINT_SYMMETRY`), which is a persistent relationship rather than a one-shot copy. (`core/mirror_geometry.py`, ADR-026.)

## FR-21: Task Management & Reminders (Phase 13, Package C, US-C2, issue #188)

- **FR-TASK-01**: A dedicated **Tasks** dashboard tab (appended after Seed Inventory, **Ctrl+5**) lists actionable tasks grouped by urgency — Overdue / Today / This Week / Upcoming / No date — plus collapsible **Snoozed** and **Done** sections (`ui/views/tasks_view.py`).
- **FR-TASK-02**: Tasks are produced by six pure, Qt-free generators (`services/task_generator.py`, each `(PlanState) -> list[Task]`): planting-calendar windows (indoor/direct sow, transplant, harvest), propagation steps, succession sow/clear, soil amendments (one per `SoilService.calculate_amendments` recommendation per bed), frost protection (from the weather service's `FrostAlert`s), and user-created manual tasks. `generate_all` flat-maps and dedups by `task_id`.
- **FR-TASK-03**: Manual tasks (`models/task.py` `ManualTask`: date, title, notes, optional bed link) are created/edited via `TaskDialog` and persisted under the additive top-level `.ogp` key `manual_tasks`. Add/Edit/Delete are undoable (`Add/Edit/DeleteManualTaskCommand`).
- **FR-TASK-04**: Per-task status (done / dismissed / snoozed) is stored under the additive key `task_states` (`{task_id: {status, done_date?, snooze_until?}}`), keyed by the deterministic generated id or the manual-task id. `effective_status` (`services/task_status.py`) resolves status at render time against "today": a done task stays visible (struck-through) for 7 days then archives; a snoozed task hides until `snooze_until`; dismissed tasks hide but their id is retained so a regenerated identical task does not resurface.
- **FR-TASK-05**: Both new keys are backwards-compatible (no `FILE_VERSION` bump; older files load with empty dicts). Legacy `task_completions` ids are folded into `task_states` as archived done entries on load, and `set_task_status` keeps `task_completions` in sync so the (unchanged) planting-calendar dashboard still hides completed tasks.
- **FR-TASK-06**: Clicking a task's navigate (→) control switches to the Garden Plan tab and selects/centres the linked bed (`navigate_to_bed`), species items (`navigate_to_species`), or specific items (`navigate_to_items`, e.g. frost-affected plants).
- **FR-TASK-07**: The Tasks tab regenerates on relevant project changes (location, task/manual-task/succession changes, any command) through a 1 s coalescing debounce, and reuses the planting calendar's single weather fetch for frost tasks (`PlantingCalendarView.frost_alerts_ready`) — no second forecast request.
- **FR-TASK-08**: On startup (and on opening a project) a non-modal status-bar message reports overdue manual tasks when `Preferences → Tasks → Notify about overdue tasks on startup` is enabled (default ON, `settings.notify_overdue_tasks_on_startup`).
- **FR-TASK-09**: On new-season rollover, future-dated (and undated) manual tasks carry forward and future snoozes are preserved; past-due manual tasks and done/dismissed states stay in the previous season file.

> Scope note: US-C2 builds a *new* unified Tasks tab on pure generators; the existing planting-calendar "today" dashboard is intentionally left in place (it reads the same project state, so the two cannot diverge in data). A convergence follow-up to refactor that dashboard onto `services/task_generator.py` is tracked separately.

## FR-22: Sidebar Accordion — Hover-Peek + Click-to-Toggle (issue #226, ADR-030)

- **FR-UI-SIDEBAR-01**: Every sidebar panel starts **collapsed** (header-only bar) on each launch; no panel/pin state is persisted across sessions.
- **FR-UI-SIDEBAR-02**: **Hovering** a collapsed bar peeks it open in place after a short debounce (pushing bars below it down); leaving collapses it again after a longer debounce. Fast pointer sweeps do not flicker the bars (re-entering a bar cancels its pending close).
- **FR-UI-SIDEBAR-03**: **Clicking** a panel title toggles it open/closed. Open and close are **animated** (an organic height expansion, not a hard switch). Panels keep a **fixed order** — opening or closing one never reorders the list.
- **FR-UI-SIDEBAR-04**: Open panels **fill the available space** rather than leaving an empty gap: a single open panel expands to fill the sidebar; when several are open each keeps at least its content height and the surplus is shared weighted by content size; when their combined content exceeds the sidebar height it **scrolls**. (There is no draggable divider.)
- **FR-UI-SIDEBAR-05**: The three selection-driven panels (Plant Details, Companion Planting, Crop Rotation) are **hidden entirely** unless a matching item is selected — they do not linger as empty placeholder bars. Selecting a single plant **shows + auto-opens** Plant Details and Companion Planting; selecting a single bed shows + auto-opens Crop Rotation; selecting anything else (or nothing) hides all three. The user can **close a shown panel with a single click**, and it stays closed for that selection; a different selection re-opens it.
- **FR-UI-SIDEBAR-06**: Peek and pin are visually distinct (peek = accent border; pin = left accent rail), with an instant hover highlight on collapsed bars. Keyboard equivalents are deferred (v1 is mouse-only).
