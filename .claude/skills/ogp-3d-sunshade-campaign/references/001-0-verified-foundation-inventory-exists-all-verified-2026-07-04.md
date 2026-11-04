## 0. Verified foundation inventory (EXISTS — all verified 2026-07-04)

You are NOT starting from zero. These assets exist and were read from source:

| Asset | Where (verified) | What it gives Phase 14 |
|---|---|---|
| Real-world lat/lng in `.ogp` | `core/project.py` — `set_location()` (~line 742): dict `{latitude, longitude[, elevation_m][, frost_dates]}`; saved as top-level `"location"` key (save ~line 142, load ~line 191). Built by `ui/dialogs/location_dialog.py` (~line 347), frost lookup via `services/climate_service.py` (Open-Meteo ERA5) | Solar position needs exactly lat/lng + a UTC instant. Already persisted per project. May be `None` — every sun feature needs a "no location set" empty-state. |
| Geo-referenced satellite background | ADR-019; `services/google_maps_service.py` (`meters_per_pixel()` line ~100, Web-Mercator), `ui/canvas/items/background_image_item.py` (`geo_metadata` dict incl. `meters_per_pixel`) | True-to-scale ground imagery under the shadow overlay; a second lat source if `location` is unset (do NOT auto-copy — prompt the user). |
| cm-calibrated Y-up model | ADR-002; `docs/08-crosscutting-concepts/README.md` §8.1 (+y = North/up, origin bottom-left). §8.10's "Qt scene is Y-down / `scene_to_canvas`" is the abstract-Qt wording — see `ogp-qt-cad-reference` §1 (owner) for why the data path treats scene as Y-up | A ready ground plane: 1 scene unit = 1 cm, +y(scene) = North. The Y-flip is the #1 trap — see Phase 3. |
| Polygon booleans | `pyclipper>=1.3.0` (`pyproject.toml:47`), used with an integer scale factor in `core/tools/offset_tool.py` (line 22, `PyclipperOffset`). Separately `core/shape_boolean.py` = **QPainterPath-based** union/intersect/subtract (Qt-DEPENDENT, not pyclipper) | Shadow-polygon union. For the Qt-free core, use `pyclipper` (offset_tool precedent). `shape_boolean.py` is fine only in the Qt overlay layer. |
| numpy | pyproject dependency (`numpy>=1.24`) | Heatmap accumulation without a new dependency. |
| Layers system | `models/layer.py` (`Layer`), `ui/canvas/canvas_scene.py:912` `layers`, `ui/panels/layers_panel.py`; all layer ops undoable (#207/#208) | Home for a non-serialized "Sun/Shade" overlay layer; per-layer visibility already respected by render pipeline. |
| Render/export pipeline | `services/scene_rendering.py` `render_scene_region()` (line 132, `y_flip=True` default); Agent API `render_canvas_image` (`agent_api/render.py` line 120, `px_per_cm = width_px / source_rect.width()` line 146). Pixel formula (§8.19; canonical statement: `ogp-qt-cad-reference` §1): `px_x = (x_cm − region_x_cm)·px_per_cm`; `px_y = image_height_px − (y_cm − region_y_cm)·px_per_cm` | **Machine-checkable visual validation**: render the canvas, compute where a shadow tip must land in pixels, assert on actual pixels. Use it — never eyeball. |
| Weather/climate services + async precedent | `services/weather_service.py` (stdlib urllib, 3 h disk cache), `services/climate_service.py`; QThread workers: `ui/widgets/weather_widget.py::_WeatherFetchWorker` (line 33), `services/update_checker.py::UpdateChecker` (line 98) | The blessed off-GUI-thread pattern for Phase 4 heatmap computation. |
| Species height data | `src/open_garden_planner/resources/data/plant_species.json` — top key `plants`, **118 records, 118/118 have `max_height_cm`** (plus `min_height_cm`, `max_spread_cm`). Model: `models/plant_data.py` `min/max_height_cm` (lines 96–97), `current_height_cm` (line 313) | Default plant heights for shadows AND the growth-over-time slice (min→max interpolation). |
| Additive item metadata | `garden_item.py` `_metadata` dict (line 202), `set_metadata`/`get_metadata` (line 739+); `project.py` serializes `item.metadata` wholesale (lines ~1400/1444/1475). Precedent: `core/container_model.py` documents additive `container_*` keys incl. **`container_height_cm`** (default 30) — Qt-free, mirrors `core/plant_sizing` | New `object_height_cm` key round-trips with ZERO serializer changes and old apps ignore it. **No FILE_VERSION bump** (currently `"1.4"`, `core/project.py` line 35 — bump only for new item *types*). |
| Undo machinery | `core/commands.py` `ChangePropertyCommand` (takes `apply_func` — works for metadata keys); two-chokepoint invariant `execute()`/`register_applied()` (#209); `stack_changed` signal for panel refresh (#223) | Height edits become one undoable command. NOTE: the existing container section mutates `meta[...]` directly (NOT undoable) — that is debt, not a precedent to copy. |
| `ObjectType` inventory | `core/object_types.py` line 148+: `FENCE`, `WALL` (polyline), `HOUSE`, `GARAGE_SHED`, `GREENHOUSE`, `HEDGE_*`, `TREE`/`SHRUB`/`PERENNIAL` (circle), `TRELLIS`, containers, furniture | The height-default table in Phase 2 keys off these. |
| Decorative shadows toggle | `config/settings.py:199` `KEY_SHOW_SHADOWS` → `application.py` `_on_toggle_shadows` (~line 2628) → `canvas_scene.set_shadows_enabled` (line 154) → per-item painted drop shadow (`garden_item.py` lines 211/718) | **Cosmetic only.** Phase 14 must NOT reuse this key or its menu item; rename risk is a UX decision — see Phase 3 step 5. |
| Roadmap + open question | `docs/roadmap.md` line 2447 "Phase 14: 3D Visualization & Sun/Shade (Future, v2.0)" (Qt3D integration, object heights, sun path sim, walkthrough, growth vis); `docs/11-risks-and-technical-debt/README.md` line 10: "Qt6 3D capabilities vs dedicated engine? Prototype with Qt3D, evaluate PyVista" | The scope contract and the mandated Phase 5 spike. |
| License | `pyproject.toml` line 10: **GPL-3.0-or-later** | Any new dep must be GPL-compatible (Phase 5 table). |
| ADR home | `docs/09-architecture-decisions/README.md` — single file, ADR-001…ADR-036 (as of v1.24.3). **Next free number: ADR-037** | Where the solar-architecture (ADR-037) and 3D-engine (ADR-038) ADRs go. |

Quick re-verification (run before trusting this table if months have passed —
also see "Provenance and maintenance" at the end):

```bash
# Linux/container (repo checkout, no venv needed for grep-level checks):
grep -n "FILE_VERSION" src/open_garden_planner/core/project.py            # -> line 35: "1.4"
grep -n "location: Dict with latitude" src/open_garden_planner/core/project.py  # -> ~747
grep -n "pyclipper" pyproject.toml                                        # -> "pyclipper>=1.3.0"
python3 -c "import json;d=json.load(open('src/open_garden_planner/resources/data/plant_species.json'));print(sum(1 for r in d['plants'] if r.get('max_height_cm')),'/',len(d['plants']))"
# -> 118 / 118
```

---

