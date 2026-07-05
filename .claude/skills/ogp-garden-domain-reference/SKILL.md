---
name: ogp-garden-domain-reference
description: >
  Gardening/horticulture domain knowledge pack for Open Garden Planner — as
  encoded in THIS codebase, not a gardening textbook. Load when: touching
  species data, plants, beds/containers/trellises, soil tests/amendments,
  companion planting, spacing, tasks/calendar, succession, crop rotation,
  harvest logs, frost/weather, propagation, or seed inventory; when you need
  to know what a diagnostic (antagonist badge, spacing overlap, soil mismatch,
  capacity overrun) means agronomically and where it is computed; when you
  need the canonical species_key rules, the plant-sizing precedence, the
  Rapitest soil scale, or the meaning of a domain term (brassica, hardiness
  zone, amendment, succession). Also load before adding any bed/container
  feature or editing bundled JSON data files.
---

# OGP Garden Domain Reference

This skill maps the horticultural domain model to its code homes. Every claim
below was verified by reading the cited file on **2026-07-04** (repo at
v1.23.0). Re-verify with the commands at the end before trusting counts.

**When NOT to use this skill:** Qt widget/canvas/QGraphicsView mechanics
(→ `ogp-qt-cad-reference`), architecture invariants like the two-chokepoint
undo rule or FILE_VERSION policy (→ `ogp-architecture-contract`), debugging a
misbehaving task/diagnostic pipeline (→ `ogp-debugging-playbook`, existing
`debug-verbose`), build/run/i18n workflow (→ `ogp-build-and-run`,
`ogp-change-control`). For the 3D/sun-shade campaign that consumes the geo
data described in §7, see `ogp-3d-sunshade-campaign`.

---

## 1. Species data

### 1.1 Bundled DB is the single source of truth (ADR-014)

- **File:** `src/open_garden_planner/resources/data/plant_species.json` —
  top-level dict `{version, description, sources, plants}`; `plants` is a list
  of **118 records** (counted 2026-07-04).
- Each record carries the full curated schema: `scientific_name`,
  `common_name`, `family`, `genus`, `cycle`, `growth_rate`, `flower_type`,
  `pollination_type`, min/max height & spread (cm), `sun_requirement`,
  `water_needs`, hardiness zone min/max, `ph_min`/`ph_max`, edibility,
  frost tolerance, the 8 calendar week-offset fields (see §6.1), germination/
  maturity day ranges, `min_germination_temp_c`, `seed_depth_cm`,
  `prick_out_after_days`, `harden_off_days`, `nutrient_demand`
  (`heavy|medium|light`), and per-nutrient `n_demand`/`p_demand`/`k_demand`.
- **Loader:** `services/bundled_species_db.py` — builds three lower-cased
  lookup indexes (by scientific name, common name, alias). Canvas drop / tool
  draw calls `populate_item_species_metadata` to auto-fill
  `metadata["plant_species"]` (issue #170); calendar callers use
  `get_calendar_entry` / `merge_calendar_data`.

### 1.2 Online APIs are enrichment only

`services/plant_api/` contains `trefle_client.py`, `perenual_client.py`,
`permapeople_client.py` behind `manager.py`/`base.py`. They cover the long
tail the bundled DB misses. API results are **sparse**: any enum trait can be
absent.

### 1.3 The UNKNOWN rule (lesson from issue #231)

Every trait enum in `models/plant_data.py` (`SunRequirement`, `WaterNeeds`,
`PlantCycle`, `GrowthRate`, `FlowerType`, `PollinationType`) has an
`UNKNOWN = "unknown"` member, and `PlantSpeciesData` defaults to it.

- **UNKNOWN must render as "—" (em-dash), never as the first concrete
  option.** The pre-fix bug: combos excluded UNKNOWN and fell back to
  `setCurrentIndex(0)`, so a tree with a missing lifecycle read "Annual" —
  and the save path then *persisted* that lie. Fix: leading neutral
  `("—", UNKNOWN)` entry per combo.
- Numeric siblings (dimension/pH/hardiness spin-boxes): a missing value is a
  `0` sentinel; use a **non-empty** `setSpecialValueText(self.tr("—"))` —
  Qt treats an *empty* special-value string as disabling the feature, so it
  rendered "0 cm". `.value()` still returns 0 at the dash; save maps
  `value() if > 0 else None` (`test_sparse_species_saves_back_as_none`).

### 1.4 Canonical species key (ADR-016)

`species_key(species_dict)` in `models/plant_data.py` (line ~370):

```
priority: source_id → scientific_name → common_name
output:   stripped + lowercased; "_unknown" if all empty
```

**Why it exists:** the same species must hash to the same key across surfaces
so per-species state never desyncs. **It MUST be used for:**

- Task ids — `make_calendar_task_id(species_key, task_type, year)` in
  `services/task_generator.py` is *the* single id format
  (`f"{species_key}:{task_type}:{year}"`); both the Tasks tab and the planting
  calendar build ids through it (the #12 done/snooze desync bug happened when
  one surface built ids differently).
- Harvest aggregation — `HarvestHistory` caches `species_key` at log time so
  `services/harvest_aggregation.py` totals resolve after the plant item is
  deleted or the season rolls over.

Never invent an ad-hoc key from a display name.

---

## 2. Plant sizing semantics (ADR-028)

Single home: **`core/plant_sizing.py`** (Qt-free). Three independent
quantities:

| Quantity | Meaning | Where stored |
|---|---|---|
| **Footprint** | The drawn circle radius — what the plant occupies visually | `CircleItem._radius` |
| **Spacing override** | User-set planting-distance radius (cm), `None` = "use DB" | item `spacing_radius_cm` |
| **`max_spread_cm`** | Species' mature spread from the DB | `metadata["plant_species"]` |

Precedence (`PlantSizing.effective_spacing_radius_cm`):
**override > `max_spread_cm / 2` > `None`**. `db_spacing_radius_cm()` is the
same `max_spread/2` used when species assignment resizes the footprint so
diameter == `max_spread_cm` (#213) — and only resizes `if db_radius is not
None`, so sparse species never collapse a plant to 0.

**Spacing ring paint gate** (verified in `ui/canvas/items/circle_item.py`):
the dashed ring draws only when `spacing_ring_radius_cm` is not None — i.e.
effective spacing **strictly exceeds** the footprint (a ring inside the
footprint conveys nothing) — **and** the item `isSelected()` *or* has a
spacing-overlap state set. `_positive_number` rejects `bool` so `True` is
never read as 1 cm.

Vocabulary: **spacing** = distance between plants (radius, cm); **spread** =
mature canopy width (diameter, cm). The DB stores spread; spacing is derived.

---

## 3. Beds, containers, plant-parents (ADR-031)

### 3.1 ObjectType taxonomy

`core/object_types.py` — `ObjectType` enum has **43 members** (counted
2026-07-04): polygon structures (HOUSE, GARDEN_BED, LAWN, GREENHOUSE, …),
polylines (FENCE, WALL, PATH, ROOF_RIDGE), plants (TREE, SHRUB, PERENNIAL),
furniture, infrastructure (RAISED_BED, COMPOST_BIN, …), the US-C3 quartet
(CONTAINER, CONTAINER_ROUND, WALL_PLANTER, TRELLIS), generics, text/callout,
GARDEN_JOURNAL_PIN.

### 3.2 The predicate split — memorize this

Two seams that historically both went through `is_bed_type()`:

| Predicate | Set | Members | Gates |
|---|---|---|---|
| `is_bed_type()` | `SOIL_CONTAINER_TYPES` (5) | GARDEN_BED, RAISED_BED, CONTAINER, CONTAINER_ROUND, WALL_PLANTER | soil tests, mismatch borders, amendment/shopping volume, soil-depth UI, square-foot grid |
| `is_plant_parent_type()` | `PLANT_PARENT_TYPES` (6) | the 5 above **+ TRELLIS** | reparenting, drag/copy propagation, "Contained Plants" panel, bed-style context menu |
| `is_container_type()` | `CONTAINER_TYPES` (3) | CONTAINER, CONTAINER_ROUND, WALL_PLANTER | litre-by-height fill, material/drainage props, capacity badge |

**TRELLIS is the only plant-parent that is NOT soil-capable** — that is the
entire reason two predicates exist. Its context menu comes via
`build_bed_context_menu(supports_soil=False)` (pest/harvest/succession yes;
grid and soil test no). Before adding any bed feature, read
`docs/08-crosscutting-concepts/` §8.14 + ADR-017 (bed features build centrally
on `GardenItemMixin`, not per-shape).

Parent/child linkage: a bed/parent holds `child_item_ids` (list of UUIDs);
each plant holds `parent_bed_id`. Spacing checks group by `parent_bed_id`
(§4.2).

### 3.3 Container math (`core/container_model.py`, Qt-free)

Metadata keys (additive — old `.ogp` files round-trip):
`container_height_cm` (default 30), `container_material`
(`terracotta|plastic|wood|metal`, default plastic), `container_drainage`
(default True), `container_soil_volume_l` (explicit override or absent).

- **Soil volume:** `auto_soil_volume_litres = footprint_cm² × height_cm / 1000`
  (1 L = 1000 cm³); explicit positive `container_soil_volume_l` override wins
  (`effective_soil_volume_litres`).
- **Capacity overrun:** `is_capacity_exceeded` = sum of child plants' **drawn
  footprint areas** (NOT spacing-circle areas — spacing is reported by the
  per-plant overlap badge) > container footprint area.
- **Watering hints:** per-material English source strings (terracotta dries
  fast; plastic retains moisture; wood rots if waterlogged; metal heats up) +
  a separate `NO_DRAINAGE_HINT` atom. UI translates the atoms under the
  `"ContainerModel"` context and joins them — never translate the
  concatenated combo (keeps the source set 4+1, not 4×2).

---

## 4. Canvas diagnostics — what each warning means and where it lives

**Golden rule:** badges are already-computed state. The Agent API's
`get_diagnostics` (`agent_api/diagnostics.py`) only *reads* harvested flags
(`ProjectManager.diagnostics_snapshot`) — it **never recomputes**, and it
deliberately does not report positive states (spacing `"ideal"`, rotation
`"good"` are good-state markers, not warnings).

### 4.1 Companion planting / antagonist badge

- **Data:** `resources/data/companion_planting.json` — **40 plants,
  94 relationships** (counted 2026-07-04; the service docstring's "60+" is
  aspirational). Each relationship: `plant_a/plant_b/type/reason/reason_de`;
  types `beneficial|antagonistic|neutral`. User custom rules persist
  per-machine in app-data (`custom_companion_rules.json`), not in the `.ogp`.
- **Service:** `services/companion_planting_service.py`. Lookups are
  **bidirectional** (A–B stored once, queried either way — the reversed copy
  must carry `reason_de` too, or German queries fall back to English) and
  **case-insensitive** across common name, scientific name, aliases, and
  localized names (`name_de`/`name_fr`/`name_es`). `resolve_name` falls back
  to the lowercased input so unknown plants still work for custom rules.
- **Computation:** `application.py::_update_companion_highlights`. Two layers:
  (1) selection-driven colored rings (antagonistic wins over beneficial);
  (2) the **permanent antagonist badge** — any plant with an antagonistic
  neighbor within `_companion_radius_cm` (**default 200 cm / 2 m**,
  user-adjustable via the companion panel) gets
  `set_antagonist_warning(True)`; one antagonist is enough.
- **Agronomic meaning:** antagonists inhibit each other (allelopathy, shared
  pests, resource competition — e.g. fennel next to most vegetables);
  companions help (pest confusion, pollinator attraction).
- **Serialization trap (#219):** `_antagonist_warning` is runtime-only, never
  saved — code must not let badge presence affect geometry (the rotation-pivot
  drift bug).

### 4.2 Spacing overlap

`application.py::_update_spacing_overlaps` (debounced timer + selection
changed). Plants are grouped by `parent_bed_id` (orphans form their own
group); only plants with a non-None `effective_spacing_radius()` participate.
For each pair: **overlap iff `dist < radius_a + radius_b`** (spacing circles
intersect → planted too densely for mature size). State is `"overlap"` or
`"ideal"` per plant. Special case (US-C3b): a TRELLIS parent uses a **1-D
distance projected onto its rotation-aware long axis** — climbers are spaced
along the bar; perpendicular offset is placement noise. Container capacity
(`_update_container_capacity`) runs on the same triggers but is independent
of the spacing-circles toggle.

### 4.3 Soil mismatch

`canvas_view.py::_update_soil_mismatches` (500 ms debounce on scene change),
beds only (`is_bed_type`). Per bed: effective soil record
(`SoilService.get_effective_record` — bed-specific else `"global"`) vs each
child plant's `PlantSpeciesData`. `SoilService.get_mismatched_plants` reasons:

- **pH:** warn when `record.ph < ph_min − 0.05` or `> ph_max + 0.05`. The
  0.05 tolerance is deliberately tight — only float-rounding slack for the
  0.1-step spinbox; a 0.3 margin hid real mismatches.
- **Nutrients:** e.g. plant is a heavy N feeder (`n_demand == "high"`) but
  bed `n_level < 2` (below Adequate on the Rapitest scale) — same for P/K.

Severity is count-based: **1 reason → "warning" (amber border), ≥2 →
"critical" (red)**; reasons become the bed tooltip. A separate seasonal badge
(`_update_soil_badges`) marks beds whose soil test is **overdue**
(`SoilService.is_test_overdue`).

---

## 5. Soil model (docs/08 §8.13, ADR-013/015)

### 5.1 Soil tests (`models/soil_test.py`)

`SoilTestRecord` uses the **Rapitest categorical scale** (consumer test-kit
labels):

| Nutrient | Scale |
|---|---|
| N, P | 0=Depleted, 1=Deficient, 2=Adequate, 3=Sufficient, 4=Surplus |
| K | 1–4 (**no K0** — the kit has no "Depleted" for potassium) |
| Ca, Mg, S | 0=Low, 1=Medium, 2=High |

Plus `ph`, optional `*_ppm` lab-mode readings (mode `"kit"|"lab"` persisted),
`soil_texture ∈ {sandy, loamy, clayey, compacted, None}` (drives structural
picks), notes, UUID. Stored under `.ogp` key `soil_tests` as
`{target_id: SoilTestHistory}` where `target_id` is a **bed UUID or literal
`"global"`** (project-wide default). `SoilTestHistory.latest` tie-breaks
same-date records by *most-recently-appended* (a Lab record saved the same
day as a Kit record must win).

### 5.2 Amendments (ADR-015, `models/amendment.py` + `services/amendment_loader.py`)

- **Data:** `resources/data/amendments.json` — **23 substances** (counted
  2026-07-04): limes, sulfur, blood/bone meal, wood ash, compost, manure,
  epsom salt, gypsum, greensand, rock phosphate, several mineral compounds,
  and 4 structural picks (diatomaceous earth, perlite, vermiculite, coarse
  sand).
- `Amendment` fields: `application_rate_g_m2`, `ph_effect_per_100g_m2`
  (positive = raises pH), integer `*_level_effect` = Rapitest steps per
  application at the base rate, `fixes` tags (`raises_pH`, `adds_N`, …,
  `improves_aeration/drainage/water_retention`), `organic`, `release_speed`,
  `name_de`.
- **Smart composition (US-12.11):** each pick fully closes its primary
  deficit and *credits* co-fixed nutrients at the same dose factor
  (`AmendmentRecommendation.credits`); selection is greedy by breadth (count
  of outstanding deficits touched), organic-preferred, JSON-order tie-break.
- **Toggleable library:** `ProjectData.enabled_amendments` is a per-project
  allowlist of substance ids; **`None` (default) = all enabled**.
  `prefer_organic` defaults True.

### 5.3 The g→kg promotion trap (§11.4 — do not reintroduce)

`ShoppingListService._collect_materials` auto-promotes amendment quantities
from g to kg once the cross-bed total crosses 1000 g. Because user prices in
`shopping_list_prices` are keyed by item **id**, the id must encode the unit
(`amendment:<aid>:g` vs `amendment:<aid>:kg`) — otherwise a price entered at
800 g silently re-binds when the row becomes 1.2 kg (1000× error). Use the
locale-stable `g`/`kg` suffix, never a translated string.

---

## 6. Time-based features

Everything is anchored on the project's **frost dates** (§7).

### 6.1 Planting calendar

Species carry 8 week-offset fields (`models/plant_data.py`):
`indoor_sow_start/end`, `direct_sow_start/end`, `transplant_start/end`
(**relative to the last spring frost; negative = weeks before**), and
`harvest_start/end` (**weeks after planting**). E.g. tomato:
`indoor_sow_start = -8` → sow indoors 8 weeks before last frost.

### 6.2 Tasks engine (ADR-029, `services/task_generator.py`)

Six **pure Qt-free generators** `(PlanState) -> list[Task]`: calendar,
propagation, succession, soil (one task per precomputed amendment rec),
frost, manual. No generator does I/O or reaches into services — everything
arrives via the `PlanState` snapshot (`build_plan_state`). Status
(done/snoozed/dismissed/archived) is **not** stored on `Task`; it is resolved
at render time by `services/task_status.effective_status` from `.ogp`
`task_states` (an expired snooze reads as open; done > 7 days reads as
archived — no background scheduler). `task_completions` is a write-only
legacy mirror. Task ids: §1.4.

### 6.3 Succession planting (`models/succession.py`)

Four frost-relative **season segments**
(`SEASON_SEGMENTS = ("early_spring", "late_spring", "summer", "fall")`):

| Segment | From | To |
|---|---|---|
| early_spring | last_frost − 8w | last_frost − 2w |
| late_spring | last_frost − 2w | last_frost + 4w |
| summer | last_frost + 4w | fall_frost − 4w |
| fall | fall_frost − 4w | fall_frost + 2w |

Plans persist under `.ogp` `succession_plans` keyed by bed id; the engine
emits sow/clear tasks per segment.

### 6.4 Crop rotation (`models/crop_rotation.py`)

`PlantingRecord`: year, season (`spring|summer|fall|winter`), species,
**botanical family** (e.g. Solanaceae, Brassicaceae), `nutrient_demand ∈
{heavy, medium, light, fixer}`, `area_id` (bed UUID).
`get_families_for_area(area_id, last_n_years=3)` powers the rule check:
don't replant the same family in the same bed within ~3 years (soil-borne
disease/pest carry-over), and rotate heavy feeders → light feeders → fixers
(legumes restore nitrogen). Persisted in `.ogp` `crop_rotation`.

### 6.5 Harvest logs (US-C1, `models/harvest_log.py`)

`.ogp` key `harvest_logs` = `{target_id: HarvestHistory}` keyed by **plant or
bed item UUID**; history caches `species_key` + `species_name` at log time
(§1.4). `HarvestRecord`: date, quantity, unit (`kg|g|pcs|bunch|L|…`),
quality, notes, project-relative `photo_path`, `journal_note_id` (each
harvest auto-creates a **pin-less** `harvest`-tagged `JournalNote`).
Aggregation (`services/harvest_aggregation.py`) groups by
**(species, year, unit)** — quantities in different units are never summed.

### 6.6 Frost & weather

- `services/weather_service.py`: Open-Meteo 16-day forecast (free, no key),
  3-hour disk cache. `get_frost_alerts` thresholds (at-or-below): **orange
  ≤ 5.0 °C, red ≤ 2.0 °C** forecast minimum; alerts list affected plant ids
  (frost-tender species from metadata).
- `services/climate_service.py`: Open-Meteo **ERA5 archive** →
  historical daily minima → computed frost dates (`"MM-DD"`) + **USDA
  hardiness zone** (avg annual extreme min → °F → zone table 1a…13b);
  365-day cache.

### 6.7 Propagation & seed inventory

- `models/propagation.py`: `STEP_IDS = (indoor_sow, germination, prick_out,
  harden_off, transplant)`; dates derived from species calendar + frost
  dates; per-species user overrides persist in `.ogp`
  (`propagation_overrides`).
- `models/seed_inventory.py`: `SeedPacket` (species link, variety,
  purchase_year, quantity in `seeds|grams`, germination temps/days,
  light/dark germinator, pre-treatment) in a **global cross-project** store
  (plus a per-project mirror key). `ViabilityStatus ∈ {GOOD, REDUCED,
  EXPIRED, UNKNOWN}` computed from shelf-life data in
  `resources/data/seed_viability.json` (`by_species` + `by_family` fallback;
  133 entries total, counted 2026-07-04). A placed species with no matching
  packet = a **seed gap** → Shopping List Seeds row.

---

## 7. Geo context — the asset the 3D campaign builds on

- **Location dict** (verified `core/project.py::set_location`, ~line 743):
  keys `latitude`, `longitude`, `elevation_m`, `frost_dates`; `frost_dates`
  is a sub-dict with `last_spring_frost` / `first_fall_frost` (`"MM-DD"`) and
  `hardiness_zone` (built in `ui/dialogs/location_dialog.py`, auto-filled
  from `climate_service`). Persisted in the `.ogp`.
- **Satellite calibration (ADR-019):** `MapPickerDialog` (QtWebEngine +
  Google Maps; key via `OGP_GOOGLE_MAPS_KEY` in `.env`) fetches a Static-Maps
  mosaic; `services/google_maps_service.py` derives an **analytical
  pixel→meter scale from Web-Mercator** (`meters_per_pixel(center_lat,
  zoom)`, haversine width). The background image item persists a
  `geo_metadata` dict (incl. `center` `[lat, lng]` and bbox) in the `.ogp`
  (`ui/canvas/items/background_image_item.py`).
- Net effect: an `.ogp` can carry **cm-accurate real-world scale + lat/lon +
  elevation + frost climate** — exactly the inputs a sun-path/shadow engine
  needs. Cross-ref `ogp-3d-sunshade-campaign` before designing anything solar.

---

## 8. Glossary for the non-gardener engineer

Merged from `docs/12-glossary/README.md` plus horticulture terms the code
assumes. UI ships English + German; German-facing quirks flagged inline.

| Term | Meaning here |
|---|---|
| **Companion / antagonist** | Plant pair that helps / harms each other when grown nearby. Encoded as `beneficial`/`antagonistic` relationships in `companion_planting.json`; badge logic §4.1 |
| **Spacing vs spread** | Spread = mature canopy diameter (DB `max_spread_cm`); spacing = required plant-to-plant distance, derived as spread/2 radius unless overridden (§2) |
| **Footprint** | The drawn circle on canvas — the plant's current visual size, independent of spacing |
| **Succession planting** | Multiple sequential crops in one bed within a season (e.g. radish → beans → lamb's lettuce); modeled as season segments (§6.3) |
| **Crop rotation / rotation family** | Not replanting the same botanical family (Brassicaceae, Solanaceae, …) in a bed year over year, to break disease/pest cycles and balance nutrient draw (§6.4) |
| **Brassica** | Member of Brassicaceae (cabbage, kale, broccoli, radish) — the classic rotation-sensitive family |
| **Heavy/medium/light feeder, fixer** | Nutrient-demand classes (`NUTRIENT_DEMANDS`); fixers (legumes) add nitrogen back |
| **Hardiness zone** | USDA climate band (1a–13b) from average annual extreme minimum temperature; computed in `climate_service.py`, compared against species `hardiness_zone_min/max` |
| **Frost dates** | Last spring frost / first fall frost (`"MM-DD"`); the anchor for every calendar computation |
| **Frost-tender** | Species killed by frost (`frost_tolerance: "tender"`); drives frost alerts |
| **Amendment** | Soil-improving substance (lime, blood meal, compost…) with application rate g/m² and per-nutrient effects (§5.2). German name via `name_de` |
| **Structural amendment** | Fixes soil *texture*, not nutrients: sand (drainage), perlite (aeration+drainage), vermiculite (water retention+aeration), diatomaceous earth |
| **Rapitest scale** | Categorical consumer-kit nutrient levels (§5.1); "level < 2" = below Adequate |
| **pH** | Soil acidity; most vegetables want ~6.0–7.0. Species carry `ph_min`/`ph_max`; mismatch tolerance is ±0.05 (§4.3) |
| **NPK** | Nitrogen / Phosphorus / Potassium — the macronutrients tracked per soil test and per species demand |
| **Soil texture** | `sandy` / `loamy` / `clayey` / `compacted` — structural condition on a soil test; loam is the ideal |
| **Propagation** | Raising plants from seed indoors: indoor_sow → germination → prick_out (transplant seedlings to individual pots) → harden_off (acclimatize outdoors) → transplant |
| **Direct sow vs indoor sow** | Seeding straight into the bed vs starting indoors before last frost |
| **Days to maturity** | Sowing/transplant → first harvest; drives `harvest_start/end` offsets |
| **Seed viability** | How many years seeds stay germinable; `seed_viability.json` by species/family |
| **Seed gap** | Placed species with no seed packet in inventory → shopping-list row |
| **Bed / raised bed / container** | Soil-capable plant parents (`is_bed_type`); container fill measured in litres by height (§3.3) |
| **Trellis** | Vertical climber support — plant-parent, holds **no soil**, spacing measured 1-D along its long axis |
| **Harvest log** | Per-item yield records; aggregated per (species, year, unit) (§6.5) |
| **Journal note / pin** | Map-linked dated note; harvest notes are pin-less and `harvest`-tagged |
| **Garden journal (German UI)** | Companion reasons/plant names have `reason_de`/`name_de` fields in the JSON; reversed relationship copies must carry `reason_de` too, and the "—" placeholder is registered under the `PlantDatabasePanel` i18n context |

---

## Provenance and maintenance

All facts verified 2026-07-04 against the working tree. Re-verify:

```bash
# Species record count (expect 118)
python3 -c "import json;print(len(json.load(open('src/open_garden_planner/resources/data/plant_species.json'))['plants']))"

# ObjectType member count (expect 43) + predicate sets
python3 -c "
import re;s=open('src/open_garden_planner/core/object_types.py').read()
b=s.split('class ObjectType(Enum):')[1].split('@dataclass')[0]
print(len(re.findall(r'^\s{4}[A-Z_]+ = auto\(\)', b, re.M)))"
grep -n "SOIL_CONTAINER_TYPES\|PLANT_PARENT_TYPES\|CONTAINER_TYPES" src/open_garden_planner/core/object_types.py

# Companion DB size (expect 40 plants / 94 relationships)
python3 -c "import json;c=json.load(open('src/open_garden_planner/resources/data/companion_planting.json'));print(len(c['plants']),len(c['relationships']))"

# Amendments (expect 23 substances)
python3 -c "import json;print(len(json.load(open('src/open_garden_planner/resources/data/amendments.json'))['substances']))"

# species_key + task id contract
grep -n "def species_key" -A 12 src/open_garden_planner/models/plant_data.py
grep -n "def make_calendar_task_id" -A 12 src/open_garden_planner/services/task_generator.py

# Sizing precedence + ring gate
grep -n "effective_spacing_radius_cm\|spacing_ring_radius_cm" src/open_garden_planner/core/plant_sizing.py
grep -n "isSelected() or self._spacing_overlap" src/open_garden_planner/ui/canvas/items/circle_item.py

# Location dict keys
grep -n "def set_location" -A 8 src/open_garden_planner/core/project.py

# Companion warning radius default (expect 200.0 cm)
grep -n "_companion_radius_cm = " src/open_garden_planner/app/application.py
```

If any count differs, update this file in the same PR that changed the data
(see `ogp-change-control` / `ogp-docs-and-writing`).
