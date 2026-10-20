# Pitfalls: 3D look, ground and build

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-L3D-01

- **Rule:** A gate that the repair itself makes true proves nothing, so measure before the repair, make the repair report what it changed, and never make a constraint hold by translating the result.
- **Pinned by:** `tests/unit/test_scene3d_plants.py::test_every_recipe_fits_the_plan_s_numbers`; `tests/unit/test_scene3d_plants.py::test_every_recipe_at_every_proportion_step`; `tests/unit/test_scene3d_plants.py::test_extreme_sizes_and_proportions`; `tests/unit/test_scene3d_plants.py::TestFitReport`
- **Source:** #385
- **Status:** standing; narrative in [archive/09-l1-7-plant-builders.md](../archive/09-l1-7-plant-builders.md#11412-what-the-plant-builders-taught-phase-17-l17-385)
- **Legacy:** b1faaa9 README L1153 (legacy 11.4.12)

### PF-L3D-02

- **Rule:** A plant in a raised bed casts from the bed's soil and is lifted only while its link holds and its stable geometric centre, not its `boundingRect()` centre, lies inside the bed's shape.
- **Pinned by:** `tests/unit/test_shadow_caster_base.py::test_the_bed_casts_the_part_below`; `tests/integration/test_scene3d_base_stacking.py::TestTheLinkAloneNeverLifts`; `tests/integration/test_scene3d_base_stacking.py::TestWhichPointEachDecisionAsks`
- **Source:** #385
- **Status:** standing; narrative in [archive/08-l1-6-world-stacking.md](../archive/08-l1-6-world-stacking.md#11413-what-the-built-world-and-base-stacking-taught-phase-17-l16-385)
- **Legacy:** b1faaa9 README L1396 (legacy 11.4.13)

### PF-L3D-03

- **Rule:** A bound that keeps the topmost N records drops what everything stands on, so a tile loses its smallest records by how much of the tile their paint covers, not by count.
- **Pinned by:** none — the paragraph names no test file; §8.29.5 describes the pins of the bake's lessons.
- **Source:** #385
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#the-bake-itself)
- **Legacy:** b1faaa9 README L2526 (legacy 11.4.17)

### PF-L3D-04

- **Rule:** A `Texture` element holds one texture for life, because destroying any texture it once held nulls its `textureData` and turns the tile white, so a re-baked tile is a new Model with a new texture.
- **Pinned by:** `tests/integration/test_scene3d_ground_render.py::test_a_re_textured_tile_keeps_its_picture`
- **Source:** #532
- **Status:** standing; narrative in [archive/07-l1-5-ground-bake.md](../archive/07-l1-5-ground-bake.md#the-bake-itself)
- **Legacy:** b1faaa9 README L2660 (legacy 11.4.17)

### PF-L3D-05

- **Rule:** Hand the engine every colour derived in linear light through `engine_srgb`, build each sky as a new `Texture` with its own data, and stop the wind clock whenever the pane is hidden.
- **Pinned by:** none — the body names no test for this rule; the tests it names guard other items, a reduce-motion drift guard, a sky-only dusk check and a wind-memory xfail.
- **Source:** #385, #476, #529, #534
- **Status:** standing; narrative in [archive/06-l1-4-looks-sky-wind.md](../archive/06-l1-4-looks-sky-wind.md#11418-what-the-looks-the-sky-and-the-wind-taught-phase-17-l14-385)
- **Legacy:** b1faaa9 README L2930 (legacy 11.4.18)
