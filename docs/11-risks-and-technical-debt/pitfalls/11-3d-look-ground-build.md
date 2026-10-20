# Pitfalls: 3D look, ground and build

Standing rules for this area, one entry each. The heading is the rule. Pins and sources are listed under each entry. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-L3D-01

- **Rule:** A gate the repair itself satisfies is not evidence; a measure must be able to move
- **Pinned by:** `scripts/make_bench_plans.py`; `scripts/make_sprite_resolution_golden.py`; `scripts/measure_plant_art_3d.py`; `tests/conftest.py`; `tests/integration/test_scene3d_plants.py::test_every_gallery_plant_is_built_as_the_sprite_the_canvas_draws`; `tests/integration/test_scene3d_plants.py::test_the_measuring_script_keeps_out_of_the_owner_s_stores`; `tests/unit/test_scene3d_plants.py::TestPlaceholder`; `tests/unit/test_scene3d_plants.py::TestShapeCache`; `tests/unit/test_scene3d_plants.py::test_every_recipe_at_every_proportion_step`; `tests/unit/test_scene3d_plants.py::test_every_recipe_fits_the_plan_s_numbers`
- **Source:** #385
- **Status:** standing; narrative in [archive/09-l1-7-plant-builders.md](../archive/09-l1-7-plant-builders.md#11412-what-the-plant-builders-taught-phase-17-l17-385)
- **Legacy:** README L1153 (legacy 11.4.12)

### PF-L3D-02

- **Rule:** A bounding box is not a footprint; a closed polyline is a ring; pin everything else before changing shipped behaviour
- **Pinned by:** `tests/integration/test_scene3d_base_stacking.py::TestTheLinkAloneNeverLifts`; `tests/unit/test_scene3d_builders.py::TestShedRidge`; `tests/unit/test_shadow_caster_base.py::TestSweptShadowDefinition`
- **Source:** #385
- **Status:** standing; narrative in [archive/08-l1-6-world-stacking.md](../archive/08-l1-6-world-stacking.md#11413-what-the-built-world-and-base-stacking-taught-phase-17-l16-385)
- **Legacy:** README L1396 (legacy 11.4.13)

### PF-L3D-03

- **Rule:** A bound that keeps the topmost N drops what everything stands on; a count is not a time
- **Pinned by:** none — pending Phase 3 review
- **Source:** #385, #438, #469, #470, #484, #501, #502
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#11417-what-the-ground-bake-taught-phase-17-l15-385)
- **Legacy:** README L2526 (legacy 11.4.17)

### PF-L3D-04

- **Rule:** Never point a Texture at a second texture
- **Pinned by:** none — pending Phase 3 review
- **Source:** #532
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#the-bake-itself)
- **Legacy:** README L2660

### PF-L3D-05

- **Rule:** What the looks, the sky and the wind taught (Phase 17 L1.4, #385)
- **Pinned by:** `tests/unit/test_view3d_look_settings.py`
- **Source:** #385, #476, #529, #534
- **Status:** standing; narrative in [archive/06-l1-4-looks-sky-wind.md](../archive/06-l1-4-looks-sky-wind.md#11418-what-the-looks-the-sky-and-the-wind-taught-phase-17-l14-385)
- **Legacy:** README L2930 (legacy 11.4.18)
