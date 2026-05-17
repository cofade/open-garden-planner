# 9. Architecture Decisions

Architecture Decision Records (ADRs) for significant technical choices.

## ADR-001: PyQt6 as GUI Framework

**Status**: Accepted
**Context**: Need a desktop GUI framework for Python with strong 2D graphics support.
**Decision**: Use PyQt6 with QGraphicsView/Scene for the canvas.
**Rationale**: Mature, native look on all platforms, hardware-accelerated 2D, 3D-ready via Qt3D. Large community.
**Consequences**: GPLv3 license required. Larger app size than lightweight alternatives.

## ADR-002: Bottom-Left Coordinate Origin (Y-Up)

**Status**: Accepted
**Context**: Need to choose coordinate system convention for the canvas.
**Decision**: Bottom-left origin with Y-axis increasing upward (CAD convention).
**Rationale**: Standard in CAD software. Eases future 3D transition. Mathematical convention.
**Consequences**: Requires Y-flip transform in QGraphicsView (which uses Y-down). Some complexity in mouse coordinate handling.

## ADR-003: JSON Project File Format (.ogp)

**Status**: Accepted
**Context**: Need a project file format for saving/loading garden plans.
**Decision**: JSON-based .ogp files with embedded images (base64).
**Rationale**: Human-readable, VCS-friendly, no external database needed. Embedded images ensure portability.
**Consequences**: Large file sizes with embedded images. No binary efficiency. Version migration requires JSON schema evolution.

## ADR-004: Command Pattern for Undo/Redo

**Status**: Accepted
**Context**: Need robust undo/redo support for all editing operations.
**Decision**: Wrap all modifications in Command objects, push to QUndoStack.
**Rationale**: Industry standard pattern. Qt provides QUndoStack. Clean separation of actions from UI.
**Consequences**: Every new editing operation requires a corresponding Command class. More code but predictable behavior.

## ADR-005: Fixed Sidebar (Not Dockable)

**Status**: Accepted
**Context**: Whether to use dockable panels (Qt dock widgets) or fixed sidebar.
**Decision**: Fixed sidebar with collapsible panels.
**Rationale**: Simpler UX, consistent layout, no user confusion about panel placement. Lower implementation complexity.
**Consequences**: Less flexibility for power users. May revisit for future versions.

## ADR-006: AI-Generated SVG Assets

**Status**: Accepted (Phase 6)
**Context**: Need illustrated SVG graphics for plants, furniture, and infrastructure objects.
**Decision**: Use AI image generation to create consistent top-down plant/object illustrations, then convert to SVG.
**Rationale**: Fast production, consistent art style, fully custom, no licensing issues. Can iterate on style.
**Consequences**: Quality depends on AI generation capabilities. May need manual cleanup. Style may evolve.

## ADR-007: Tileable PNG Textures (over Procedural)

**Status**: Accepted (Phase 6)
**Context**: Current procedural patterns are too subtle. Need rich, recognizable textures.
**Decision**: Replace procedural fill patterns with pre-made tileable PNG textures.
**Rationale**: Better visual quality, easier to create realistic materials, AI-generated or CC0 sourced.
**Consequences**: Increases app bundle size. Need LOD management for different zoom levels. Less flexibility than procedural.

## ADR-008: Qt Linguist for i18n

**Status**: Accepted (Phase 6)
**Context**: Need multi-language support (English + German initially).
**Decision**: Use Qt Linguist translation system (tr() calls, .ts/.qm files).
**Rationale**: Native Qt integration, industry standard for Qt apps, supports plurals and context, good tooling.
**Consequences**: All strings must be wrapped in tr(). Requires pylupdate6/lrelease build steps. Translation memory maintained in .ts XML files.

## ADR-009: NSIS Windows Installer

**Status**: Accepted (Phase 6)
**Context**: Need professional distribution for public release.
**Decision**: PyInstaller (--onedir) bundled with NSIS installer script.
**Rationale**: Professional install experience (wizard, shortcuts, file association, uninstaller). NSIS is free, mature, widely used.
**Consequences**: Windows-only initially. Need to maintain NSIS script. Cross-platform support deferred.

## ADR-010: Branded Green Theme

**Status**: Accepted (Phase 6)
**Context**: Current theme is generic. Need visual identity.
**Decision**: Garden-themed green color palette as primary brand color with light/dark variants.
**Rationale**: Strong visual identity appropriate for a garden planning tool. Green is universally associated with gardens/nature.
**Consequences**: Replaces current generic light/dark theme. Need careful color balance to avoid "too much green".

## ADR-011: Hybrid Plant Rendering

**Status**: Accepted (Phase 6)
**Context**: How many unique plant SVG illustrations to create.
**Decision**: Hybrid approach: ~15-20 category-based shapes varied by color/size, plus unique illustrations for ~10 most popular species.
**Rationale**: Best balance of visual appeal and production effort. Category shapes cover 90% of cases. Popular species get special treatment.
**Consequences**: Need mapping logic from plant type/species to SVG file. Category shapes must be generic enough to represent multiple species.

## ADR-012: Hybrid Constraint Solver (Gauss-Seidel warm-start + Newton-Raphson refinement)

**Status**: Accepted (Phase 11 — issue #140)
**Context**: The original solver was a pure Gauss-Seidel relaxation loop. It resolves every constraint by a 1D projection along its own geometric direction. This works for decoupled systems but diverges on coupled ones — the canonical failure is two `EDGE_LENGTH` constraints sharing a vertex, where the feasible position is the intersection of two circles. Users reported that constraining edge A to 4.53 m and adjacent edge B to 5.00 m left edge A drifting to 5.21 m (both constraints geometrically satisfiable).
**Decision**: Keep Gauss-Seidel as a fast warm-start, then run damped Newton-Raphson refinement (`constraint_solver_newton.py`) when the residual exceeds tolerance. Add a closed-form circle-circle fast path for the shared-vertex case. Add `numpy` as an explicit dependency (`>=1.24`) for `linalg.lstsq`.
**Alternatives considered**:
- *Pure geometric closed-form* — would need a case per constraint-pair (O(16²)); brittle and high-maintenance.
- *scipy.optimize* — adds ~40 MB to the installer for a problem numpy solves in <20 variables.
- *Analytic Jacobian* — a nice-to-have optimization, but numerical central differences cost microseconds; deferred as TD-008.
**Consequences**: Robust behaviour for user-built CAD sketches (matches SolveSpace/Onshape expectations). +1 runtime dependency (numpy). Jacobian is numerical, not analytic — mild perf ceiling, no correctness impact. See §8.12 for the full solver architecture.

## ADR-014: Bundled `plant_species.json` is single source of truth for species + calendar

**Status**: Accepted (Phase 12 — issue #170)
**Context**: Before #170 there were two bundled JSON files: `planting_calendar.json` (sow/transplant/harvest weeks, frost tolerance) consumed by `planting_calendar_db.py`, and an unbundled species record file that did not exist — species data only came from on-demand API search (Perenual/Trefle/Permapeople), which returns inconsistent or empty pH/NPK fields. Result: dropped plants had no `metadata["plant_species"]` until the user clicked Suchen, and US-12.10d (plant↔soil pH/nutrient warnings) silently no-op'd because `ph_min`/`ph_max`/`n/p/k_demand` were always None.
**Decision**: Collapse to one file — `src/open_garden_planner/resources/data/plant_species.json` — with full `PlantSpeciesData` records (incl. calendar fields) for every species the gallery exposes (118 records at land time: trees, shrubs, vegetables, herbs, berries, fruits, ornamentals). The new `bundled_species_db.py` module owns both the species-record API (`lookup_species`, `populate_item_species_metadata`) used by canvas drop / tool-draw paths, and the legacy calendar API (`get_calendar_entry`, `merge_calendar_data`) used by the plant detail panel. The old `planting_calendar.json` and `planting_calendar_db.py` are deleted.
**Alternatives considered**:
- *Two separate files (species + calendar)* — would duplicate `family`, `frost_tolerance`, `nutrient_demand` and create drift risk. The user explicitly rejected this in design discussion.
- *Auto-merge species data from the existing API at first launch* — only works with network access on first run, can't cover the offline installer experience, and the upstream APIs return inconsistent pH/NPK regardless.
- *Per-record source citations in the JSON* — adds noise. Sources cited at envelope level (`"sources": [...]`) is sufficient for the curated set.
**Consequences**: One file to maintain. Adding a species means writing one record with all fields populated. Drop flow auto-populates metadata for any of the 60+ bundled plants → US-12.10d warnings fire automatically. Long-tail species still fall through to the API search button. Bundle size grows by ~80 KB (negligible).

## ADR-015: Multi-nutrient Amendment Composition + User-toggleable Library

**Status**: Accepted (Phase 12 — US-12.11)
**Context**: US-12.10c shipped a calculator that walked deficits in priority order and picked the *first matching unused* substance for each fix tag. This worked for single-nutrient organics (blood meal → N, bone meal → P, greensand → K) but silently mishandled real-world commercial fertilizers, where one bag carries N + P + K + Mg + S in a single product. The old "consume substance, decrement secondaries by 1 step" rule under-credited compound fertilizers and produced over-long lists. Users also wanted to disable substances they don't have on hand, and to add structural amendments (sand, perlite, vermiculite, diatomaceous earth) driven by a soil-texture rating.
**Decision**: Replace the pick-once-per-fix loop with a **deficit-map + greedy max-coverage** loop. Each iteration scores every unused candidate by the number of currently-outstanding nutrient deficits it touches; the breadth-leader is picked, its primary nutrient is fully closed (quantity scales with deficit), and co-fixed nutrients are credited at the same dose factor and recorded in `AmendmentRecommendation.credits`. The pool is filtered by a per-project `enabled_amendments` allowlist that the user manages from a checkbox panel embedded in the existing Amendment Plan dialog. A `prefer_organic` flag biases tie-breaks. A new `SoilTestRecord.soil_texture` field drives a structural-pick phase that runs after the nutrient phase.
**Alternatives considered**:
- *Linear-program optimal solver* (e.g. scipy.optimize.linprog) — would minimise total grams across all substances. Rejected: ≤24 substances × ≤7 nutrients is too small to justify a numpy/scipy build dependency, the greedy pick is provably optimal for the breadth metric, and users prefer "one bag covers most" reasoning over "two-half-bags covers slightly less". 
- *Two-pass: organic first, then mineral* — clean conceptually but loses the "one compound substance covers multiple deficits" insight that motivated the rewrite.
- *Per-substance application_rate scaled by chemistry mass-balance (NPK %)* — would let the calculator do exact label-percentage math. Deferred: keeps the calculator's domain to "Rapitest level steps", avoids per-substance NPK% data entry on JSON, and the +1 step credit suffices for end-user purchasing decisions.
**Consequences**: Compound NPK fertilizers (Blaukorn, Tomatendünger, etc.) emit one row instead of three. Users see an honest "Raises N 1→3 + also raises P 1→3, K 1→3" rationale. Disabling substances changes both the inline preview and the cross-bed plan and shopping-list materials in real time. Soil-texture-driven structural picks add up to two rows for clayey soil (drainage + aeration), one row for sandy or compacted soil. Bundle data file grows by 12 entries (12 → 23 substances). No file-format bump; legacy projects load with `enabled_amendments=None` (= all enabled) and `soil_texture=None` (no structural picks).

## ADR-013: Soil Data Embedded in `.ogp` (not a sidecar file)

**Status**: Accepted (Phase 12 — US-12.10a)
**Context**: Per-bed soil tests need to persist across sessions. Two reasonable shapes: (a) embed under a top-level `"soil_tests"` key in the existing `.ogp` JSON file, or (b) ship a sidecar `<project>.soil.json` next to the `.ogp` file.
**Decision**: Embed soil tests directly in the `.ogp` file under `"soil_tests"`, bumping `FILE_VERSION` to `1.3`.
**Rationale**:
- *Single-file portability* — the `.ogp` file already carries seed inventory, location, propagation overrides etc.; soil tests fit the same contract. Users move/share one file.
- *Atomic save* — soil-test mutation participates in the existing dirty-flag/save flow. No risk of `.ogp` and sidecar drifting out of sync.
- *Undo coherence* — `AddSoilTestCommand` operates on `ProjectManager` state; the same instance the canvas commands work against. A sidecar would need its own dirty-tracking and merge protocol.
**Alternatives considered**:
- *Sidecar JSON* — would let lab-mode CSV imports drop a file alongside the project, but the same goal is achievable through Garden → Import inside the embedded model in 12.10c. The portability cost outweighs the import convenience.
- *Per-bed metadata field on `RectangleItem` etc.* — entangles canvas-item lifetime with historical data. Deleting a bed would lose its test history; restoring it via undo would not bring history back. Project-level storage avoids this.
**Consequences**: `.ogp` files grow modestly (≈100 bytes per test record). Migration path is one-way (v1.3 files cannot be opened in older binaries — same convention as v1.2). All later 12.10 sub-stories (overlay, calculator, warnings, sparklines) consume the same `SoilService` facade and inherit the storage decision automatically.

## ADR-016: Canonical Species Key

**Status**: Accepted (Phase 12 — issue #176)
**Context**: Five species identity fields existed across the codebase — `source_id`, `scientific_name`, `common_name`, `species_id`, `species_name` — with each module resolving them in a different order and with different normalisation. US-12.6 patched around the inconsistency with a local `_norm_species_key()` function in `shopping_list_service.py`. US-12.8 (Succession Planting) and US-12.9 (Journal) would both need to key data by species and would have baked the inconsistency deeper or invented yet another normaliser.
**Decision**: A single `species_key(species: dict[str, str]) -> str` function in `models/plant_data.py` is the only sanctioned way to derive a stable dict key from a species dict. Priority: `source_id` → `scientific_name` → `common_name`. Output is always `.strip().lower()`. Returns `"_unknown"` if all fields are absent or empty. All existing call sites migrated in issue #176.
**Rationale**: `source_id` is preferred because it is stable across common-name renames; all existing comparisons already worked case-insensitively once stripped, so the normalisation step is backward-compatible with on-disk project files. Centralising the logic means future call sites cannot diverge silently.
**Alternatives considered**:
- *New UUID `species_id` field on every canvas item* — would give a true stable key. Rejected: requires a data-migration for existing `.ogp` files and a coordinated change to the plant-drop workflow. Deferred until a file-version bump is warranted.
- *Normalise inside every caller* — the status quo. Rejected: each caller diverged slightly; the inconsistency was already causing phantom seed-gap misses in US-12.6.
**Consequences**: Keys in `propagation_overrides` and `shopping_list_prices` are stable unless a plant's `source_id` changes (API re-imports only — rare). `crop_rotation_service.py` was not migrated because it keys exclusively on botanical family name, not species identity.

## ADR-018: Object Gallery Moves to Top Toolbar (Sims-style Category Dropdowns + Global Search)

**Status**: Accepted (Phase 12 — UI refactor)
**Context**: The `GalleryPanel` sidebar widget held all ~120 placeable objects (beds, shapes, plants, structures, surfaces, furniture, infrastructure, fences) in 11 stacked categories with a search box and category dropdown. It was the first of 10 collapsible panels in a 450 px right sidebar. Three problems compounded: (a) the most-used action — "draw a garden bed" — sat as the *tenth* category (`Paths & Surfaces`), requiring the user to scroll past 100+ plants/objects first; (b) the sidebar overall was dense with 10 panels visible at once; (c) the toolbar at the top was intentionally minimal (5 tools) and left horizontal screen real estate unused.
**Decision**: Replace the sidebar gallery with **10 category-icon buttons in the top toolbar**, each opening a popup dropdown of 64×64 thumbnails (3-column grid) with an in-popup filter field. A separate **global search field** on the toolbar searches across every object regardless of category. The toolbar layout is `[5 core tools] | [10 category buttons] | [stretch] | [search field]`. Icons are SVG; 7 of 10 categories reuse existing icons from `resources/icons/tools/`, 3 new SVGs were added (`vegetable`, `furniture`, `infrastructure`).
**Alternatives considered**:
- *Sims-style left-rail "Build / Plant / Manage" modes* — bigger UX shift, would have required mode switching for previously-single-screen workflows. Rejected as too invasive for the value delivered.
- *Sidebar tabs (Objects / Plan / Garden)* — preserved the gallery in the sidebar, but did not solve the "scroll past 100 plants to find a bed" problem.
- *Promote only the top-3 shapes to the toolbar, keep gallery* — solves discoverability for beds but leaves the dense sidebar untouched.
- *Floating inspector for selection-dependent panels* — orthogonal concern, deferred. Selection panels currently still live in the sidebar.
**Consequences**: One-click access to every category. The "Garden Bed" tool is now the first item in the first dropdown (`Beds & Surfaces`), reflecting actual usage frequency. Gallery data lives in a single source (`ui/widgets/gallery_data.py`) consumed by both the dropdowns and the global search. `GalleryPanel`, its `_panels/__init__.py` export, and its test file are removed; translation strings migrated from context `GalleryPanel` to `GalleryData`. The sidebar drops from 10 to 9 panels and is reordered so selection-related panels (Properties → Plant Details → Companion → Crop Rotation) sit directly under each other. Drag-from-dropdown to canvas is preserved (same MIME format the canvas already accepts).

**Toolbar layout note (3-toolbar split):** The category buttons live in a *separate* `CategoryToolbar` rather than being embedded in `MainToolbar`. Three top-row toolbars are added in this order: `MainToolbar` (Select/Measure/Text/Callout/Pin) → `ConstraintToolbar` (CAD constraints) → `CategoryToolbar` (10 category dropdowns + global search). Qt's `addToolBar` ordering puts them left-to-right on the same row, with the search field naturally rightmost. Splitting also keeps the icon-lookup for category buttons free of `_CATEGORY_ICON_MAP` glue: the icon filename now lives on `GalleryCategory.icon_name` itself, set at construction (before any `tr()` translation), so locale-independent lookup is intrinsic to the data.

**Search-popup focus note:** The global search uses a `Qt.ToolTip`-flagged, `WA_ShowWithoutActivating` results popup with a no-focus QListWidget. Without these, the `Qt.Popup` window activates on every `show()` and steals keyboard focus from the QLineEdit — every keystroke after the first lands on the popup and is lost.

**Persistence:** Window geometry, the main splitter, and each tracked `CollapsiblePanel`'s expanded state are persisted to `QSettings` (`UiState/…` group) by the lightweight `app/ui_state.py` wrapper. Save on `closeEvent` plus a live-save on every `expanded_changed` signal.

## ADR-017: Bed-Specific Features Built Centrally on `GardenItemMixin`

**Status**: Accepted (Phase 12 — US-12.8 post-bug)
**Context**: Bed-capable shapes are not a single class but four (`RectangleItem`, `PolygonItem`, `EllipseItem`, `CircleItem`) — historical reasons: garden beds are drawn as polygons, raised beds as rectangles, in-ground round beds as circles or ellipses. Each new "bed-only" feature (grid toggle, soil-test entry, pest/disease log, succession plan) was hand-copied into all four `contextMenuEvent` methods. Twice in a row a feature shipped missing from one or more shapes: pest/disease log was missing from `PolygonItem` and `EllipseItem` until #173 added it; succession-plan ("Plan Anbaufolge…") was missing from all three non-rectangle shapes until the post-US-12.8 fix.
**Decision**: Bed-action construction and dispatch live on `GardenItemMixin` as `build_bed_context_menu(menu, *, grid_enabled, supports_grid)` and `dispatch_bed_action(action, actions)`, returning a `BedMenuActions` dataclass. Every bed-capable shape's `contextMenuEvent` calls these two methods inside its `is_bed_type` guard; no shape adds its own action constants for grid/soil/pest/succession. A parametrised regression test (`tests/integration/test_bed_context_menu.py`) iterates over all four shape classes and fails for any missing bed action.
**Rationale**: Adding a fifth shape (or new bed feature) is now a one-file change instead of a four-file diff. The regression test makes divergence detectable in CI rather than at user-report time. Centralising also means translation strings live in a single `"BedActions"` context, so the German/English wording is the same regardless of which shape opened the menu.
**Alternatives considered**:
- *Per-shape menus, manual sync* — the status quo. Rejected: failed twice in three months.
- *Unify the four classes into one* — much larger refactor, complicated by different shape semantics (vertex editing on Polygon, radius on Circle, etc.).
- *Plugin/registry pattern (bed features as data)* — overkill for four actions. The mixin method is just enough indirection.
**Consequences**: Bed-only menu strings now live under context `"BedActions"` instead of `"RectangleItem"`/`"PolygonItem"`/etc. — historical translations under per-shape contexts remain valid for non-bed menu entries (delete, duplicate, arrays, etc.). When introducing a NEW bed feature in the future, the entry point is `BedMenuActions` + `build_bed_context_menu` + `dispatch_bed_action`. The parametrised test must be extended with an `assert actions.<new_field> is not None` line — that single assertion forces the dev to remember the central path.

## ADR-019: In-App Satellite Background Picker via Google Maps + Embedded QtWebEngine

**Status**: Accepted (Phase 12 — satellite-import feature)
**Context**: Bringing a garden's satellite image onto the canvas was a fully manual process: take a screenshot of Google Maps, save it locally, import via `File → Import Background Image…`, then start the calibration tool and click two reference points whose real distance is known. Two pain points: (a) the screenshot-and-import dance is friction every time a new project starts; (b) calibration is the canonical source of subtle scale errors — picking the two points 1 px off propagates to every measurement in the canvas. Free open satellite providers (ESRI World Imagery, Sentinel) either lacked the sub-meter resolution needed for garden planning or had ToS that made them awkward for a Windows binary.
**Decision**: Embed a Google Maps picker inside the app via `QWebEngineView` + Google Maps JS API for navigation/drawing/address search, and use **Google Static Maps API** for the actual image fetch. The JS↔Python bridge is `QWebChannel`. Image fetch is in a worker `QThread`, automatically using a 2×2 or 3×3 mosaic of Static-Maps calls when the chosen bounding box does not fit a single 1280×1280 tile at the desired zoom (algorithm: pick the highest zoom — up to 20 — at which `cols × rows ≤ 3 × 3`). Pixel-to-meter scale is **derived analytically** from Web-Mercator (`mpp = cos(lat) × 2π × 6378137 / (256 × 2^zoom)`), so the resulting `BackgroundImageItem` lands on the canvas at true real-world size — no manual calibration step. Manual override remains via the existing "Calibrate Scale…" context menu (the saved `scale_factor` wins over the geo-derived value at load time).
**Alternatives considered**:
- *Free providers (ESRI, Bing, Mapbox)* — Mapbox/Bing have free tiers but slightly lower max resolution; ESRI World Imagery is keyless but ToS limits commercial redistribution. Google's $200/month free credit (~100k Static Maps calls/month) is overkill for hobby use; chose maximum image quality + simplest setup over multi-provider plumbing.
- *External browser + URL paste-back* — leaner (no QtWebEngine, no ~50 MB installer bloat) but a workflow break that loses the immediacy of "pick area → image on canvas".
- *Coordinate input only (no visual picker)* — simplest implementation but defeats the purpose; finding a garden by lat/lng without a map is hostile.
- *Tile-layer overlay on canvas* — would require ongoing tile fetches as the user pans/zooms within the project, blowing past sensible API budgets. Static one-time fetch keeps the call count to 1–9 per project.
**Consequences**: The `MapPickerDialog` (File → "Load Satellite Background…") replaces the screenshot-and-calibrate workflow for the typical case. `BackgroundImageItem` now carries optional `geo_metadata` (center + bbox + zoom + meters-per-pixel + source + timestamp) that persists through the `.ogp` project file — older project files without geo data load unchanged via the existing `to_dict`/`from_dict` path. **API-key handling** is the critical operational caveat: the key is read from `OGP_GOOGLE_MAPS_KEY` (loaded from `.env` via `python-dotenv` in `main.py`) and must **never** be bundled into the release `.exe` — any binary distributing the key could be reverse-engineered and the key abused. The menu item is disabled with an explanatory tooltip when the key is missing. Installer impact: `PyQt6-WebEngine>=6.10` adds ~50 MB to the runtime; spec file bundles the picker HTML from `resources/web/`. Web platform requirement: `from PyQt6 import QtWebEngineWidgets` is done at `main.py` module level, before `QApplication(...)` — Qt enforces this so it can configure OpenGL sharing in time.


## ADR-020: Unified Snap Provider Registry + QuadTree Spatial Index

**Status**: Accepted (Phase 13 — Package A, US-A3)
**Context**: Snapping logic was split across two unrelated modules. `core/snapping.py` (the `ObjectSnapper`) compares left/center/right and top/center/bottom values of a *dragged* bounding rect against every other item's bounding rect — a 1-D value match producing full-height/width magenta dashed guide lines, used only during drag operations. `core/measure_snapper.py` enumerates *point* anchors (centers, edge midpoints, vertices) and is used by the MeasureTool (and indirectly by every constraint tool's anchor picker) via `find_nearest_anchor`. Two new snap modes — midpoint of any straight edge, and intersection of two edges — were required by US-A3, and the existing systems had no place to put them: the bounding-box engine cannot represent a midpoint and the anchor-points helper is a flat function with no notion of activation toggles or performance budget. Both paths iterated every scene item on every query, which is fine at ~50 items but became visible on 1000-item gardens.

**Decision**: Add `core/snap/` as a thin orchestration layer that *wraps* the existing geometry helpers without replacing them. A `SnapProvider` ABC owns one snap mode (endpoint, center, edge, midpoint, intersection); a `SnapRegistry` collects providers and runs them on a query, breaking ties by `priority` (endpoint 10 < intersection 15 < midpoint 30 < center 20 < edge 40). `EndpointSnapProvider`, `CenterSnapProvider`, `EdgeCardinalSnapProvider` delegate to `measure_snapper.get_anchor_points` and filter by `AnchorType`. `MidpointSnapProvider` walks edges of rectangles/polygons/polylines/construction-lines via a new `core/snap/geometry.item_edges` helper. `IntersectionSnapProvider` does pairwise segment intersection capped at 60 segments per query. A bounded-depth (max 6) `QuadTree` (`core/snap/spatial_index.py`) pre-filters candidates — items spanning multiple children are duplicated into every overlapping child and `_query` deduplicates via `id()`, trading a little memory for simpler insert logic. `PointSnapper` glues the index to the registry and is the single entry point used by `CanvasView`. The two legacy modules stay intact; the new path is opt-in.

**Alternatives considered**:
- *Replace `ObjectSnapper` and `measure_snapper` entirely*. Rejected: the constraint solver and 20+ call sites pin `AnchorType` and `get_anchor_points`; a one-shot rewrite would have ballooned the PR and made the diff unreviewable. The wrap-don't-replace shim leaves master green at every commit.
- *Embed midpoint/intersection inside `measure_snapper`*. Rejected: the legacy helper has no notion of enable/disable toggles, no spatial index, and would have grown to ~500 lines mixing data extraction with orchestration.
- *Use an external `rtree` package instead of a hand-rolled QuadTree*. Rejected: adds a non-trivial native dependency (libspatialindex) that complicates the PyInstaller build. The QuadTree passes the 16 ms 60-fps budget at 1000 items.

**Consequences**: The new modes ship with one menu toggle each (`View → Snap to Midpoints`, `Snap to Intersections`), persisted in `AppSettings`. Glyphs (square = endpoint, circle = center, triangle = midpoint, X = intersection, dot = edge) are rendered in `CanvasView.drawForeground` and stay at constant on-screen size via 1/zoom scaling. The drag-time bbox snapper is untouched; future work may unify it under the same registry if a need arises. `tests/unit/test_snap_providers.py` (19 tests) covers each provider; `tests/unit/test_snap_spatial_index.py` and `tests/unit/test_point_snapper.py` enforce the perf gate.

## ADR-021: Coordinate Input Pipeline (Status-Bar Field + Cursor Overlay, Single Buffer)

**Status**: Accepted (Phase 13 — Package A, US-A1/A2/A4)
**Context**: Typed coordinate entry is the most-requested workflow gap for users coming from AutoCAD/QCAD. Two UI surfaces are needed: a status-bar field (always-visible, CAD convention, predictable) and a cursor-anchored Dynamic Input overlay (modern, immediate). Without a shared state, the two surfaces drift out of sync, focus bounces between them, and the parser has to live in two places. Adding to the complexity, German users expect `,` as the decimal mark but `,` is also the natural dx/dy separator (`@500,200` → ambiguous: dx=500.2 or dx=500,dy=200?).

**Decision**: A single `CoordinateInputBuffer(QObject)` owns the text and the anchor point; both widgets read and write it via Qt signals (`text_changed`, `anchor_changed`, `committed`, `parse_error`). The pure-Python parser (`core/coordinate_input/parser.py`) accepts `@dx,dy` (relative), `@dist<angle` (polar, 0° = east, CCW positive, math convention) and `x,y` (absolute) with deterministic decimal/separator disambiguation rules (A–F): `;` is always separator; `.` + `,` mixed → `.` decimal; only commas → 1 = separator, 3 = locale decimal pair, 2 = ambiguous (prefer locale, `parse_alternative` exposes the secondary reading). The buffer is owned by `CanvasView`; the status-bar `CoordinateInputField(QLineEdit)` (inserted into the existing `_setup_status_bar`) and the floating `DynamicInputOverlay` both subscribe. Anchor is refreshed after every tool `mouse_press`/`mouse_release`/`mouse_double_click`/`key_press` and after tool changes (which also clears stale text). `BaseTool` gains `last_point` (default `None`) and `commit_typed_coordinate(point)` (default no-op); drawing tools (polyline, polygon, circle, rectangle, ellipse, construction line/circle) implement both, reusing the same code path as a mouse click would.

**Alternatives considered**:
- *Status-bar field only* — predictable but slower; users have to glance away from the cursor.
- *Cursor overlay only* — modern but loses always-visible affordance and is easy to dismiss.
- *Locale-only decimal* — would fail every English-speaking user who pastes `100.5,200`.
- *Separator-only decimal* (CAD legacy) — fails German users who naturally type `1,5`.
- *Per-tool typed-input hooks* — would have duplicated focus/anchor wiring N times.

**Consequences**: Adding a new drawing tool that supports typed input is two methods (`last_point` getter + `commit_typed_coordinate`). The parser is reusable for future CSV/DXF-style imports of point lists. The Y-axis flip lives in one place (the parser): user-entered Y reads as math-up-positive and is converted to scene-down-positive at parse time, so the rest of the codebase keeps its existing Y-down convention. The overlay is hidden while the active tool's `last_point` is `None`, avoiding a meaningless polar input UI. `View → Enable Dynamic Input` toggles the overlay independently of the status-bar field. The buffer's `parse_alternative` is currently unused by the UI but available for a future "interpreting as …" tooltip if 2-comma ambiguity becomes a support pain point. **Polar without anchor**: the parser requires `last_point` for polar input (with or without `@`); without it, a `ParseError` is raised instead of silently falling back to the origin — a silent fallback would place a vertex far from the cursor with no feedback.
