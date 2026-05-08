# 11. Risks and Technical Debt

## 11.1 Open Questions

| Question | Impact | Resolution Path |
|----------|--------|-----------------|
| Trefle.io rate limits and reliability? | Plant search UX | Test API, implement robust caching, Permapeople as fallback, bundled DB as last resort |
| Texture licensing for fill patterns? | Legal | Use AI-generated or CC0/public domain textures, document sources |
| DXF export complexity for future versions? | Interoperability | Evaluate ezdxf library, may need simplification |
| Qt6 3D capabilities vs dedicated engine? | Future 3D feature | Prototype with Qt3D, evaluate PyVista as alternative |
| Bundled plant database source? | Offline functionality | Evaluate USDA Plants Database, consider one-time Trefle.io bulk export |
| AI-generated SVG quality consistency? | Visual appeal | Test with multiple prompts, establish style guide, manual cleanup if needed |
| NSIS installer signing? | Trust/distribution | Unsigned initially, document for users; investigate free code signing options |

## 11.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PyQt6 licensing complexity (GPL/Commercial) | Medium | High | Use GPLv3, document clearly, ensure compliance |
| Performance with very large images | Medium | Medium | Implement image tiling/downsampling at zoom levels |
| Scope creep delaying v1.0 | High | High | Strict phase adherence, defer nice-to-haves to Phase 7 |
| Limited development time | High | Medium | Focus on quality over speed, attract contributors |
| Project not attracting contributors | Medium | High | Excellent documentation, clean code, contributor guide, CI/CD |
| External API deprecation | Low | Medium | Fallback chain: Trefle -> Permapeople -> Bundled DB |
| AI-generated SVGs inconsistent quality | Medium | Medium | Establish style reference set, manual review/cleanup |
| Windows installer blocked by SmartScreen | Medium | Low | Document workaround, investigate signing options |
| Large bundle size from PyInstaller | Medium | Low | Optimize includes, strip unused Qt modules |

## 11.3 Technical Debt

| Item | Area | Description | Priority |
|------|------|-------------|----------|
| TD-001 | Plant rendering | Plants currently rendered as flat colored circles | High (Phase 6 addresses) |
| TD-002 | Textures | Procedural patterns are too subtle, barely visible | High (Phase 6 addresses) |
| TD-003 | Plant cache | SQLite cache for plant API data not yet implemented | Medium |
| TD-004 | Object model | Some object types share code that could be better abstracted | Low |
| TD-005 | Test coverage | Some UI components lack automated tests | Medium |
| TD-006 | Error messages | Some error messages are technical, not user-friendly | Low |
| TD-007 | Constraint anchors | Polygon/polyline edge anchors use dynamic `EDGE_TOP/BOTTOM/LEFT/RIGHT` classification (dominant axis). Classification changes when a vertex moves far enough to flip an edge's axis, causing constraint indicators to jump to the wrong edge. Replace with `AnchorType.EDGE_MIDPOINT` + stable numeric `anchor_index` so the edge identity is axis-independent. Workaround in place (index-only match in `_resolve_anchor_position`). | Medium |
| TD-008 | Constraint solver | Newton-Raphson refinement uses a numerical central-difference Jacobian (`constraint_solver_newton._JACOBIAN_H`). An analytic Jacobian per constraint type would be faster (roughly 2N × eval savings per iteration), but numerical cost is microseconds for typical ≤20-variable systems so no user-facing impact. Revisit only if large-scene solves become a bottleneck. | Low |

## 11.4 Known Development Pitfalls

Hard-won lessons from implementation. Read these before modifying the related subsystems.

- **Release workflow race condition with chore commits**: After merging a feature PR, two chore commits are pushed (sync version + mark progress). These land ~37s after the PR merge but the Release workflow building the new tag takes ~2m50s. The chore-commit Release runs start while the tag doesn't exist yet, compute a stale version (e.g., `v1.8.4` instead of `v1.9.2`), and fail with "release with the same tag name already exists". Fixed by adding `if: "!startsWith(github.event.head_commit.message, 'chore:')"` to the release job, which skips the workflow for chore commits.

- **Anchor index on same-type anchors**: When multiple anchors share the same `AnchorType` (e.g. rectangle corners are all `CORNER`, polygon vertices are all `CORNER`, polyline vertices are all `ENDPOINT`), each must have a unique `anchor_index` in `get_anchor_points()`. Without it, `DimensionLineManager._resolve_anchor_position()` falls back to type-only matching and picks the first anchor. Always pass `anchor_index=i` when creating `AnchorPoint` for same-type anchors.

- **Dimension line updates after undo/redo**: `CommandManager.command_executed` only fires on `execute()`, NOT on `undo()`/`redo()`. Dimension line updates must also be connected to `can_undo_changed`/`can_redo_changed` signals.

- **3-anchor constraints not solved on add**: `_compute_constraint_solve_moves()` in `canvas_view.py` collects `constrained_ids` from `anchor_a` and `anchor_b` only. Any constraint with a third anchor (`anchor_c`, e.g. ANGLE) must also add `anchor_c.item_id` here, otherwise the third item is absent from `item_positions` and the solver cannot move it — showing as red/violated until the user manually drags an object.

- **Live-drag projection tolerance must be sub-pixel** (PR #169 follow-up): `ConstraintGraph.project_to_feasible()` calls `newton_refine()` with a `tol` parameter that gates an early-return *before* projection: `if max_err <= tol: return`. The starting state has `vertex_pos[moving] = desired_scene_pos` (the cursor). At cm-scale `tol` (e.g. 0.5 cm), the cursor near a feasible point falls inside the slack band on most frames of a near-stationary drag, so the function returns the cursor **unchanged** — the moving vertex slips with the cursor up to that band each frame. On a fully-constrained chain (EDGE_LENGTH on every adjacent pair), the slip looks like the entire polyline rigidly translating because the user can only see the moving vertex's position in scene coords. Fix: `project_to_feasible` defaults to `tolerance=1e-4` (sub-render-precision); `solve_anchored` and other full-graph callers retain their cm-scale tolerances. Defensive companion: `newton_refine` now also calls `write_x(x)` on the early-return path so callers always observe a consistent state.

- **Canvas Y-axis flip**: The view applies `scale(zoom, -zoom)` so **positive scene Y is visually upward** on canvas (CAD-style, origin bottom-left). When computing directional offsets from user-facing angles (e.g. linear array), negate `dy`: `dy = -spacing * sin(angle_rad)` so that 0°=right, 90°=down, 180°=left, 270°=up matches screen-space intuition. The canvas rect in scene coords is `QRectF(0, 0, width_cm, height_cm)` accessed via `self._canvas_scene.canvas_rect`.

- **EDGE_* anchor type instability on polygons/polylines** (TD-007): `_polygon_anchors()` in `measure_snapper.py` classifies each edge as `EDGE_TOP/BOTTOM/LEFT/RIGHT` based on its **current** dominant axis (horizontal vs vertical). This is a dynamic, geometry-dependent label. When a vertex is dragged far enough to flip an edge's dominant axis (e.g. a nearly-horizontal edge becomes nearly-vertical), the freshly-computed anchor type differs from the value stored in the constraint record. `_resolve_anchor_position()` in `dimension_lines.py` then fails on its `(type AND index)` match and falls through to type-only matching, snapping the constraint indicator to the wrong edge. Current workaround: an EDGE_*-aware index-only match block at the top of `_resolve_anchor_position` catches these mismatches before the fallback fires. Long-term fix (TD-007): replace all four `EDGE_*` types with a single `AnchorType.EDGE_MIDPOINT` and use `anchor_index` as the sole edge identity. The edge is always identified by its start-vertex index, not by axis classification, making the anchor stable across all vertex moves.

- **`scene.render()` with negative-height target rect is empty (PyQt6)**: `QRectF(0, H, W, -H).isEmpty()` returns `True`. Passing this as the target to `scene.render()` clips to an empty region — nothing is painted. The correct Y-flip technique is `painter.save(); painter.translate(0, H_PIXELS); painter.scale(1.0, -1.0); scene.render(painter, QRectF(0, 0, W, H), source_rect); painter.restore()`. `H_PIXELS` must be the **image height in pixels**, not the canvas height in cm.

- **`ItemIgnoresTransformations` items render at fixed device-pixel size in `scene.render()`**: When rendering via `scene.render()` (not through a QGraphicsView), `ItemIgnoresTransformations` items render at their natural pixel size regardless of the source→target scale. For a large scene (e.g. 5300 cm) rendered into a small image (774 px), a 10 pt text item can appear as 80+ cm on canvas. Fix: call `ExportService._prepare_text_for_export(scene, scale, dpi)` before rendering and `_restore_text_after_export()` after. The scale = `output_width_cm / canvas_width_cm`.

- **QPdfWriter must use `setResolution(72)` before `setPageLayout()`**: Default QPdfWriter resolution is ~1200 DPI. `painter.viewport()` returns device-pixel dimensions, so all layout math in points (1/72 inch) lands in the top-left corner. Adding `writer.setResolution(72)` makes device pixels equal PDF points and layout coordinates match.

- **`scene.render()` directly on QPdfWriter painter is unreliable (Y-flip + margins)**: QPdfWriter's painter has a non-identity initial transform from margin handling. The painter pre-flip formula `translate(0, cr.top + cr.bottom); scale(1,-1)` is mathematically correct in isolation but produces wrong output because the initial transform shifts the baseline. Fix: render the scene into a temporary `QImage` (where pre-flip is reliable) then embed with `painter.drawImage(content_rect, img)`.

- **Plant items store center in `boundingRect()`, not in `pos()`**: OGP `CircleItem` and similar types define their geometry in local coords with `pos()` always at (0, 0). `item.pos()` and `item.scenePos()` both return (0, 0). To get the visual center in scene coordinates: `item.mapToScene(item.boundingRect().center())`.

- **SVG pattern tiles appear Y-inverted under painter Y-flip**: Qt's `QSvgGenerator` records `<pattern>` elements with `patternUnits="userSpaceOnUse"`. When the scene is rendered with a `scale(1,-1)` painter transform, each pattern tile image is stored un-flipped, but renders upside-down inside the Y-flipped coordinate space. Fix: post-process the SVG after `painter.end()` and add `patternTransform="matrix(1,0,0,-1,0,{tile_height})"` to each `<pattern>` element. See `ExportService._fix_svg_pattern_yflip()`.

- **`QSvgGenerator` does not serialize painter clip regions — texture fills bleed across the canvas**: For texture-filled shapes, Qt emits a "shadow" group containing the polygon `<path>` (`fill="#000000"`) followed by a texture group `<g fill="url(#tex)"><rect x="..." y="..." width="..." height="..."/></g>`. The rect is the *painter's clip bounding rect*, not the polygon shape — and the painter's `setClipPath()` is **never** serialized as `<clipPath>`. In SVG viewers (browsers), the unconstrained rect washes across the whole canvas (often as a brownish overlay if it is a roof-tile texture). PNG export is unaffected because Qt's native renderer applies the clip directly. Fix: post-process the SVG (`ExportService._fix_svg_qt_texture_clipping()`) — pair each non-empty shadow group with the next non-empty texture group in document order, build a `<clipPath>` from the shadow's `<path>` (preserving its `transform`), and wrap the texture group with `clip-path="url(#...)"`. Pairing must be 1:1 with a `used_textures` set; forward-window scans match the same texture from multiple shadows and corrupt the XML tree. Validate SVGs in a real browser (`scripts/svg_preview.py` uses Edge headless) — `QSvgRenderer` is too forgiving and hides this bug.

- **DXF Y-axis: scene Y is already Y-up, no negation needed**: OGP scene uses Y-up (scene Y=0 = visual bottom). DXF also uses Y-up. The formula `dxf_y = canvas_h - scene_y` double-flips. Correct mapping: `dxf_y = scene_y`. Similarly for import: `scene_y = dxf_y * scale` (no negation).

- **`QGraphicsScene.changed` only fires on geometry/visibility, not on Python attribute mutations** (issue #173): The 500 ms debounce timer in `CanvasView` that drives `_update_soil_mismatches` is wired to `scene.changed`. Mutating `parent_bed_id` / `_child_item_ids` on a `GardenItemMixin` instance is a plain Python attribute write — no signal, no scene invalidation, no debounce trigger. Any code path that re-parents a plant (drag-and-drop, properties-panel "Unlink", paste, duplicate, future callers) must explicitly call `trigger_soil_mismatch_refresh(scene)` (in `commands.py`), or the warning borders go stale until the next unrelated scene change. Funnel attach/detach through `SetParentBedCommand` whenever possible — it triggers the refresh itself.

- **Plants stack behind beds when both share a layer's default z**: A new `CircleItem` and a new `RectangleItem` placed on the same layer both get `z_order * 100` from the layer (typically `0`). With equal z-values, Qt stacks by add-order. So a plant drawn *before* its bed renders behind it, even when correctly attached as a child. Fix is to elevate the plant above the bed at every attach site: `ensure_z_above_parent(plant, bed)` in `commands.py`. Already wired into `_auto_parent_plant`, `SetParentBedCommand`, `DeleteItemsCommand.undo`, paste, and duplicate. Any new path that establishes a plant-bed parent link must also call this helper.

- **`ThemeColors.get_colors(ThemeMode.SYSTEM)` ignores the user's theme choice**: `apply_theme()` only writes a stylesheet — it does *not* mutate `QApplication.palette()`. So `detect_system_theme()` (called via `ThemeMode.SYSTEM`) probes the OS palette regardless of what the user picked in Settings → Appearance. A user with `theme_mode=LIGHT` running on a dark-default OS will get the dark-mode palette dict for any code that asks "what colors am I drawing on top of?". Fix: always pass the user's preference — `ThemeColors.get_colors(get_settings().theme_mode)`. Only `theme.py` should call `get_colors()` with `ThemeMode.SYSTEM`; every other consumer must read `get_settings().theme_mode`.

- **Excel reads UTF-8 CSV as Latin-1 unless a BOM is present**: A bare `encoding="utf-8"` write produces correct bytes but Excel on Windows still mojibakes German Umlauts (`Tüte` → `TÃ¼te`). Use `encoding="utf-8-sig"` for any CSV the user is expected to open in Excel. Python's own `csv` module strips the BOM transparently on read with either `utf-8` or `utf-8-sig`, so existing tests don't need to change. The BOM byte sequence is `b"\xef\xbb\xbf"` if you need to assert it directly.

- **`ShoppingListItem.id` must encode the display unit when units auto-promote**: `ShoppingListService._collect_materials` promotes amendment quantities from g to kg once the cross-bed total crosses 1000 g. Because user-entered prices in `ProjectData.shopping_list_prices` are keyed by `id`, the id must capture the unit (`amendment:<aid>:g` vs `amendment:<aid>:kg`) — otherwise a price entered when the row was 800 g silently re-binds to the same row when it later weighs 1.2 kg, multiplying the apparent total by 1000×. Use the locale-stable suffix (`g`, `kg`) — never the translated `_tr()` string — so the id is identical across English/German runs.

## 11.5 Community and Governance

**Feature Requests**: Open to community input, pivots, and voting. The goal is to avoid a dead project — community engagement is welcome.

**Contribution Model**:
- GitHub Issues for bug reports and feature requests
- Pull requests welcome with review process
- Clear CONTRIBUTING.md with code style, testing requirements
- All PRs must pass CI (tests, linting, type checking)
