## Case study: data fields exist on the model but no UI to set them (US-12.10d, fixed 2026-05-03)

**Symptom**: Even after F1 fixed the silent serialization gap (case study above), tomato beds still didn't show pH-mismatch warnings in real use. Manual REPL round-trip of `PlantSpeciesData(n_demand="high", ph_min=5.8)` worked perfectly — the data plumbing was correct. But in the running app, every plant the user dropped had `ph_min=ph_max=n_demand=p_demand=k_demand=None`.

**Theories entertained (wrong)**:
- The fix didn't actually deploy (it had — `git show df9871e:plant_data.py` confirmed).
- `merge_calendar_data()` was overwriting the new fields (it wasn't — it only merges calendar fields).
- The library lookup was returning a stale cached `PlantSpeciesData` (no cache layer exists).

**Key signal from the user**: a screenshot of the plant details panel showing **no row** for pH or NPK demand. The fields existed on the dataclass and round-tripped through dict, but **the UI never showed them**. So the user had no way to set them — every plant arrived with `None` because the bundled data files (\`planting_calendar.json\`) only carry \`nutrient_demand: "heavy"\` and the API doesn't return pH ranges, leaving the new fields permanently empty.

**Root cause**: [src/open_garden_planner/ui/panels/plant_database_panel.py](src/open_garden_planner/ui/panels/plant_database_panel.py) — `_create_editable_fields()` had no rows for `ph_min`, `ph_max`, `n_demand`, `p_demand`, `k_demand`, or `nutrient_demand`. The model exposed the fields; the panel didn't.

**Fix**: Added 5 new form rows (pH range Min/Max, N/P/K demand combos, overall demand combo) between Hardiness and Planted, with read-back in `_on_field_changed` and population in `_show_plant_data`. After any field change the panel calls `view.refresh_soil_mismatches()` so the bed border updates live.

**Lesson**: A serialization round-trip test proves *data flows*, not *user intent flows*. When you add a field to a model, also audit the panel/dialog/forms that read & write that model — a "ghost field" with no UI is worse than no field at all because it gives the appearance of completeness in the data layer while silently making the feature unusable. Concretely: when adding a field to `PlantSpeciesData`, also grep `plant_database_panel.py` for any nearby field of the same model (e.g. `hardiness_zone_min`) — that's the natural place to add the matching UI row.

**Sister issues raised** (deferred to follow-up work, but caught during this debug session):
- #170 — autoloading from a shipped local species DB on canvas drop (so the new fields actually have values).
- #171 — past records in the History tab need edit/delete affordances; a typo currently requires deleting the whole bed.

---

