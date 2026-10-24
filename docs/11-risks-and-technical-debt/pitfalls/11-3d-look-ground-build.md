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



### PF-L3D-07

- **Rule:** An unlit overlay passes through the mood's exposure, so a 3D shadow drape multiplies the frame and an overlay colour is divided by the exposure.
- **Pinned by:** `tests/integration/test_view3d_analysis_render.py::test_the_shade_darkens_in_every_mood_and_brightens_no_pixel`; `tests/unit/test_quick3d_qml.py::test_the_overlays_blend_as_their_layer_says`
- **Source:** #386, ADR-063 addendum "review round 1"
- **Status:** standing
- **Legacy:** none (new entry)

With PF-L3D-06's alpha fixed, the 3D review still found the shadow drape brightening the garden — at night by +17.6 / +24.1 luma (up to +43.7) on 98–100 % of the pixels it covered, at sunset on 89–97 %, at golden hour on 69 % over the engine's own shadow; GPU and WARP read the same. The wrong theory was the alpha bug again; the frame's alpha was 255 everywhere. The cause: the drape is UNSHADED, and an unshaded colour is emitted and then multiplied by the mood's exposure (2.4 at night, 1.15 at the golden anchor) and the filmic curve — wherever the lit ground is darker than that emission, a blended "shadow" lightens it. The canvas's colour-over-ground recipe has no 3D equivalent. The fix multiplies: a third overlay layer with `DstColor` / `Zero` blending and a linear multiplier (`drape.SHADE_MULTIPLIER`), measured darker in every mood (noon 0.83, golden 0.76, sunset 0.74, December noon 0.78, night 0.76 of the lawn's luma). The same exposure moved the other overlays' colours: the arcs drifted up to 14° off their legend by day and washed out to near white at night, until `overlay.frag` divided by `uExposure` and the arcs were built in pre-compensated colours (within 2.7° in five moods). Lesson: judge an overlay in EVERY mood, not under a 60° sun on lit ground — the first gates all measured noon.

### PF-L3D-08

- **Rule:** A hidden or blended Model drops out of the shadow map, so a part that must keep casting while it fades or is cut is an opaque screen door (a fragment discard) that collapses in the AO depth pass.
- **Pinned by:** `tests/integration/test_view3d_analysis_render.py::test_a_faded_occluder_keeps_its_shadow`; `tests/integration/test_view3d_analysis_render.py::test_cutaway_keeps_the_roofs_shadow`; `tests/integration/test_view3d_analysis_render.py::test_a_screen_door_part_leaves_no_ao_ghost_at_medium`; `tests/unit/test_quick3d_qml.py::test_a_faded_or_cut_part_is_a_screen_door_not_a_blend`
- **Source:** #386, ADR-063 addendum "review round 1"
- **Status:** standing
- **Legacy:** none (new entry)

Cutaway first hid the roofs (`visible: !roofsHidden`) and X-ray faded occluders by opacity (a PrincipledMaterial `opacity`, a blended CustomMaterial). Both dropped the parts from the shadow map: Cutaway frames had 16k–69k pixels more than 10 luma brighter per shot, the house's shadow gone from the lawn, and a faded tree's 30 m shadow vanished (61k pixels) — the selected plant then read as standing in sun. A screen door keeps the part opaque: `screen.frag` discards all but `uOpacity` of the pixels by a 4 × 4 ordered dither (`FRAGCOORD`), and the shadow pass does not run that discard — measured top-down, ground outside the footprints unchanged (max 0.0 for faded trees; about 10 edge pixels for cut roofs), on Direct3D 11 (GPU and WARP) and OpenGL. A cut roof is the same material at opacity 0. The dither also ended the sorting of a blended crown against its own leaves. The depth pass is the exception the second review round measured: the pass that fills ambient occlusion's depth texture does not run the discard either, so from the Medium preset (the AUTO start) a cut roof left a pale ghost of itself on lawn and sky (15,555 px at noon) and a faded occluder its whole silhouette as AO. Every screen-door material therefore collapses in that pass (`#if QSSG_ENABLE_DEPTH_PASS`: `screen.vert`, `foliage_door.vert`, `grass_door.vert`) — the shadow pass does not define it, so the shadow stays: the ghost is gone (what AO adds for a cut roof or a faded box: at most 1.5 luma, up to 26 without the collapse) on Direct3D 11 (GPU, WARP) and OpenGL. Two measured dead ends: `NeverDepthDraw` on the cut roof kept the ghost and LOST the shadow, and switching AO off during Cutaway changed every pixel the AO touches. The look materials carry no discard at all (the screen doors are separate materials and shader copies, drift-pinned), so nothing changes while nothing fades. Lesson: anything that must still shade the ground stays opaque — choose what to discard, not what to hide — and check every pass that reads depth, not only the shadow pass.