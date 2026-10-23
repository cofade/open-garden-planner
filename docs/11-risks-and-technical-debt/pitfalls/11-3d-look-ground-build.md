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

### PF-L3D-06

- **Rule:** A blended custom material must keep the frame's alpha (`sourceAlphaBlend: Zero`, `destinationAlphaBlend: One`): with the colour factors on alpha too, a translucent overlay brightens the view by `a(1 − a)` of the window's white instead of darkening it.
- **Pinned by:** `tests/integration/test_view3d_analysis_render.py::test_the_shadow_drape_darkens_the_ground_towards_its_blue`; `tests/unit/test_quick3d_selftest.py::TestJudge`
- **Source:** #386, ADR-063 decision 3
- **Status:** standing
- **Legacy:** none (new entry)

The first shadow drape (the canvas's shadow blue at alpha 0.43, `SrcAlpha` / `OneMinusSrcAlpha`) read rgb(79, 107, 75) over a meadow of rgb(25, 73, 11) — LIGHTER than the ground it should shade. Opaque colours passed through exactly, so the shader was not the cause. A sweep of known colours found the law: black at a = 0.25, 0.5 and 0.75 read 4·a(1 − a) × 64 grey levels above `(1 − a) · ground`, white at 0.5 the same 64 — a grey term ∝ a(1 − a), largest at a half. That is the destination alpha: blended with the colour factors it becomes `a·a + (1 − a)·1 = 1 − a(1 − a)`, and the View3D's texture, drawn over the window's white, lets `a(1 − a)·255` through. Separate alpha factors that leave the destination alpha at 1 fixed it on Direct3D 11 (GPU and WARP) and OpenGL: black at 0.5 reads exactly half the ground. The same rule went onto the foliage, grass and water materials, which blend only while X-ray fades them. A PrincipledMaterial's own blending (glass) keeps the alpha already. Lesson: measure a blend with several alphas and two source colours before trusting one translucent frame — a single sample cannot tell a wrong colour from a wrong equation.

