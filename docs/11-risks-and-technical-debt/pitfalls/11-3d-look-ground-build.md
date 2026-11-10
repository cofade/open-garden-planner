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
- **Pinned by:** `tests/unit/test_shadow_caster_base.py::test_the_bed_casts_the_part_below`; `tests/integration/test_scene3d_base_stacking.py::TestMembershipIsReconciledAndTheLinkAloneNeverLifts`; `tests/integration/test_scene3d_base_stacking.py::TestLinkAndLiftAskTheSamePoint`
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

### PF-L3D-09

- **Rule:** The 3D drape follows the shared Hours of Sun both ways, also when 3D opens with it on.
- **Pinned by:** `tests/integration/test_view3d_analysis.py::test_the_toolbar_switching_hours_of_sun_on_lays_the_3d_drape`; `tests/integration/test_view3d_analysis.py::test_3d_opened_with_hours_of_sun_already_on_shows_it_on_the_ground`
- **Source:** PR #584 owner manual pass, ADR-063 addendum "owner manual pass"
- **Status:** standing
- **Legacy:** none (new entry)

Review round 1 made the drape follow the shared Hours of Sun going OFF (a document replace had left it on with the 2D side off). The owner then switched Hours of Sun on in the toolbar: the canvas showed the map, the 3D ground nothing, and the report read "in 3D no hours of sun are shown on the ground". The pipeline was sound — reproduced in the real app on the real engine at the owner's settings, the drape loaded and drew on screen in every order when chosen in the menu — the state machine had one edge. Lesson: when a view mirrors a shared state, test the transition the user makes from the OTHER surface in both directions, and the view's start in each state.

### PF-L3D-10

- **Rule:** Render production plants and verify final seasonal bounds.
- **Pinned by:** `tests/unit/test_plant_forge_review.py::test_winter_skeleton_keeps_ground_and_height`; `tests/unit/test_plant_forge_review.py::test_tall_crowns_retain_foliage_coverage_at_every_lod`; `tests/integration/test_plant_forge_workspace.py::test_workspace_render_flags_use_the_production_worker`; `tests/integration/test_plant_forge_calendar.py::test_instance_harvest_and_task_calendar_agree_across_years`
- **Source:** #387, PR #593, ADR-064
- **Status:** standing
- **Legacy:** none (new entry)

The original render flags disabled the new forge, so CI validated old silhouettes.
Actual output exposed low summer leaf cover, short/floating winter skeletons
and merged spring fruit/autumn blossom. Static bounds before leaf removal and
an evaluator-only timing test missed each seam. The workspace now synthesizes
off the GUI thread, invalidates upgrades on recovery and updates persistent
seasonal Models. Independent wood bounds, area-based foliage and separate accent
parts pin visible truth; harvest reuses exact shared calendar windows.
Climber guides retain actual finite support geometry: orientation alone left a
13.3945 cm gap to a reachable fence. Support discovery runs on the worker and
reuses structural dependencies; the production workspace timing gate includes
300 climbers and 100 supports, rather than bypassing admission with an evaluator.

### PF-L3D-11

- **Rule:** A `CustomMaterial`'s `TextureInput` ignores the `Texture`'s `flipV`, so a shader that samples a north-up ground tile flips `v` itself.
- **Pinned by:** `tests/integration/test_scene3d_ground_render.py::test_the_engine_shows_the_bake_north_up`; `tests/unit/test_quick3d_qml.py::test_the_ground_detail_shader_flips_v_itself`
- **Source:** #388, ADR-065 decision 8
- **Status:** standing
- **Legacy:** none (new entry)

L4.5 moved the ground tiles from a `PrincipledMaterial` to a custom material (`ground.frag`,
detail normals from the tile's own luminance). The tiles still carried `flipV: true` on
their `Texture`, and the plan drew mirrored north–south: the flat material honours the
flag, a `TextureInput` does not. The fix samples at `vec2(UV0.x, 1.0 - UV0.y)`. The
north-up gate runs at the High preset, so it judges the custom material, not the flat one.
Mutation check (2026-10-26, RTX 4070): sampling at `UV0` again drops the gate's identity
NCC to 0.47 against its bound of 0.9 (each tile mirrored in itself, so no whole-plan
mirror matches either: north–south 0.13).

### PF-L3D-12

- **Rule:** Do not switch on scene-wide order-independent transparency: `OITWeightedBlended` re-blends L2's multiply drapes and brightens what a shadow drape covers.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_the_scene_uses_no_order_independent_transparency`; `tests/integration/test_view3d_analysis_render.py`
- **Source:** #388, ADR-065 decision 9
- **Status:** standing
- **Legacy:** none (new entry)

Issue #388 asked for greenhouse glass "with OIT". With `oitMethod: OITWeightedBlended` on the
scene environment, four drape tests failed: pixels under the shade layer read up to 243
levels LIGHTER, the PF-L3D-06/07 class of P0. Weighted-blended OIT accumulates every
blended Model into its own buffers and composites them with its own equation, so the
drape's multiply blend no longer multiplies. The greenhouse and cold-frame glass keep the
existing sorted `glass` material.

### PF-L3D-13

- **Rule:** Never fill round the plan with a large surface just under it: a triangle kilometres wide is centimetres off in depth and wins against the plan. Keep one plane, cut the plan out, cells of at most 100 m.
- **Pinned by:** `tests/integration/test_scene3d_ground_render.py::test_the_meadow_never_shows_through_the_plan`; `tests/unit/test_scene3d_meadow.py`; `tests/integration/test_view3d_looks_render.py::test_the_plan_ground_meets_the_meadow_without_a_step`
- **Source:** #388, ADR-065 3D review rounds 1 and 2
- **Status:** standing
- **Legacy:** none (new entry)

The endless meadow was one 4 × 4 km quad of two triangles, 1 cm under the plan. From 14 of 36
orbit cameras on `bench_built` it drew over the pond, the terraces and the paths. Lowering it
to 5 cm passed a 36-view orbit gate but not the workspace's own framing a few wheel notches
out: 13 of 120 views lost up to 52 % of the plan.

The wrong theory was depth-buffer resolution. A 24-bit buffer at a 5 cm near plane resolves
about 0.3 cm at 50 m. The deciding control was the reviewer's: the same quad at −5 cm, cut
into 100 m cells, lost no view. The error is in interpolating a triangle 2 km across.

The 5 cm step had two costs of its own: an ambient-occlusion line of ±14 luma along every
plan edge, and shadows that jumped where they crossed it. The fitted step probe read 0.45
under that line, and `plan_edge_step` now also reports `line`.

Fix: a frame in the plan's plane with the plan cut out (`core/scene3d/meadow.py`). Mutation
check: the old quad, re-created at −5 cm, reads 27,726 key pixels; the gate's bound is 20.

### PF-L3D-14

- **Rule:** Do not feed changing geometry through QML's `ProceduralMesh`: replaced lists kept drawing the first data, and one created later drew nothing. Use a `ReloadableGeometry` on a declared Model.
- **Pinned by:** `tests/ui/test_quick3d_meadow_host.py`; `tests/integration/test_scene3d_ground_render.py::test_the_meadow_never_shows_through_the_plan`
- **Source:** #388, ADR-065 3D review round 2
- **Status:** standing
- **Legacy:** none (new entry)

Measured on D3D11 (RTX 4070), building the meadow's frame in QML:
- A declared `ProceduralMesh` bound to a computed frame drew its first frame (no hole: no
  plan yet) after the plan arrived. Reading back its lists showed the new data; the engine
  never drew it.
- A new `ProceduralMesh` given to the live Model drew nothing, with its lists set either as
  initial properties or afterwards.
- So did a new Model holding a new `ProceduralMesh`.

The selection ring's route works: a `ReloadableGeometry` parented to a Model that
`Garden.qml` declares, set once as its geometry, then reloaded for the Model's life. The
render gate asserts that the meadow is drawn round the plan. It is the same rule as `ogp-3d-renderer` §2's
geometry-lifetime row.

### PF-L3D-15

- **Rule:** Keep `aoStrength` 0 wherever ambient occlusion is off: Qt's `setAoStrength` switches AO on whenever the strength is not 0, whatever `aoEnabled` says.
- **Pinned by:** `tests/ui/test_quick3d_host.py::test_ambient_occlusion_runs_only_where_the_look_asks_for_it`; `tests/unit/test_quick3d_qml.py`
- **Source:** #388, ADR-065 3D re-review of the owner's second pass
- **Status:** standing
- **Legacy:** none (new entry)

L4 faded the AO strength with the camera's distance (`aoStrength: 55 * root.aoFade`) and
left `aoEnabled: !root.topDown && root.ambientOcclusion` as the switch. The Low preset, and
so compatibility mode, then drew SSAO as soon as the camera stood 45-90 m from its target.
Read back from the scene's `ExtendedSceneEnvironment` at Low: `aoEnabled` True with a
strength of 42.8 at 55 m. The look depended on where the camera had been. On bench_large
at noon, Low read 153.89 luma without AO and 150.43 with this bug at 67 m.

The board could not see it: its cameras stand within 25 m, where the fade stays 1, and a
strength that never changes is never written again after the scene loads.

Fix: the strength is 0 unless AO is on (`55 * (!root.topDown && root.ambientOcclusion ?
root.aoFade : 0)`), and `aoEnabled` also requires a fade above 0, so the pass does not run
at strength 0. The host test reads `aoEnabled` and `aoStrength` off the environment at every
preset and four distances, and in the top-down view.

### PF-L3D-16

- **Rule:** Derive held context from both records' consumers and admit lawn blades only where the active preset draws them; detail geometry must degrade to exact prisms below its dimensional floor.
- **Pinned by:** `tests/integration/test_view3d_sync_controller.py`; `tests/unit/test_scene3d_l4_objects.py`; `tests/unit/test_scene3d_l4_surfaces.py`
- **Source:** #611; #607; ADR-065
- **Status:** standing
- **Legacy:** none (new entry)

Door targets and the heightless-lawn predicate determine which old parameters remain valid after a retype. A universal lawn-blade special case retained irrelevant door params. Nominal furniture joints can flip tiny faces; the verified 3 cm detail floor keeps exact dimensions. Y-batched masks preserve the even-odd rule with bounded temporary pair arrays.

### PF-L3D-17

- **Rule:** A solid that should keep its 2D fill shows it on its TOP only, through a per-item `baseColorMap` (`MeshPart.fill_texture`, `vcPart.patternMap`) built from the canvas's own tinted texture — one picture per (pattern, fill colour), never one per item — with UVs `(position + paint_origin) / 256` (the canvas's phase, its `params["paint_origin"]`). Its SIDES are the item's tint (`walls_mesh`, no UVs): one fill-textured prism smears the picture down the edge. A raised flat item that also has relief (a lawn's blades) keeps it, lifted to the new top, and the height gates (`top_cm`/`fit_scale`) ignore `ground_detail` parts. A raised pond's water takes the same picture (`fill_texture` on a `water` part; `water.frag` samples `uFill`). Every `Texture` gets its data at birth: a `Texture` re-pointed at another `QQuick3DTextureData` goes white. Bind a `var`-typed map as `patternMap ? patternMap : null`; `baseColorMap: patternMap` with a null value logs "Unable to assign [undefined] to QQuick3DTexture*" and the render gate fails on it. A fill part's fade tint (`tintLinear`) is its fill colour even when the picture's `tint` is white: a `vc` part's screen door samples no picture (a faded lawn is its colour), while the water door samples `uFill` through the same branch, so a faded raised pool keeps its caustics.
- **Pinned by:** `tests/unit/test_quick3d_qml.py::test_a_fill_part_shows_the_plans_own_picture`; `tests/unit/test_quick3d_adapter.py`; `tests/unit/test_fill_patterns.py`; `tests/unit/test_scene3d_mesh.py`; `tests/unit/test_scene3d_l4_surfaces.py`; `tests/integration/test_scene3d_fill_phase.py`; `tests/integration/test_quick3d_render.py`
- **Source:** #628 follow-up (owner manual pass of #627), ADR-037 addendum
- **Status:** standing
- **Legacy:** none (new entry)

The ground bake paints a lawn, path, terrace, generic shape or bed while it lies flat, and
`lies_on_ground` stops the moment a height is typed. The item becomes a plain prism coloured
by one tint — so the owner's raised lawn turned into a flat green slab and the soil bed into a
plain brown one ("all the objects loose their texture when giving them height"). Nothing was
broken: no 3D solid had ever shown a fill pattern, because a height on these kinds could not be
set before #628. The picture is the canvas's, not an approximation:
`core.fill_patterns.tinted_pattern_pixels` returns the same `_tint_texture` result the 2D brush
uses (RGBA8, opaque, mean = the fill colour). A luminance map multiplied by a tint would have
been simpler, but a byte texture has no value above white, so every highlight above the
texture's mean would be clipped — for soil, the light specks that make it read as soil.
`materials.part_tint` is the ONE tint rule the engine read-backs compare against; a recolour
swaps the picture and uploads no geometry.

**The phase was wrong twice.** Raw record coordinates ignore the anchor; the first fix
subtracted it, and the sign was wrong: the record's footprint is CENTRED on the anchor, so
the canvas's item coordinate is `position + paint_origin`. Measured on a real 300 x 200 cm
rectangle at `paint_origin` (760, 480), against the bake: the plus sign reads NCC **0.995**
with the mesh's own UVs; the minus sign **0.759** (MULCH) / **0.866** (BRICK).
`tests/integration/test_scene3d_fill_phase.py` bakes the record and correlates the mesh's UVs,
so the source of truth is the canvas's own painter, not a re-derived formula. Visible on
DECKING, FLAGSTONE and BRICK; invisible on noise textures.

**The picture is the TOP's, and a lawn is not a slab.** The owner's second pass: a raised lawn
"still loses part of its appearance" and a bed its detail. Two separate mistakes. (1) The
blades: `_lawn` returned the plain prism at a height, so the relief that makes a lawn read as
grass was gone; it now builds the solid AND the sward lifted to the new top. Lifting by
`positions[:, 2] += height` on a cached `(blades, 5, 3)` array instead of
`positions[:, :, 2] += height` moved the third *vertex*, not z — the mesh came out sheared
(measured z 0.3..24.4 instead of 20.3..29.4). (2) The sides: ONE fill prism wraps the picture
down the walls (a lawn's grass smeared the full height of the edge), so a raised flat surface
is two Models — tinted sides, fill cap. `top_cm`/`fit_scale` and `verify_builder`'s height gate
must ignore `ground_detail`: a lawn's blades stand 0.3-9.4 cm above the requested height
(swept h = 1..200; 20.3-29.4 for h = 20), and counting them failed G1 for every raised lawn.
The gate's numbers are therefore "the SOLID's top", and `ogp-lush-cinematic` §1 says so.

A raised pool had the same class of loss in a different material: `_raised_pool` drew its
water with the water shader's tint only, so the plan's water texture vanished ("the water
became unreflective"). The water part now takes `fill_texture=True`, and `water.frag` samples
it through a `TextureInput` (`uFill`, gated by `uHasFill`), linearising it with the ground's
polygon (`x(x(0.3053x + 0.6822) + 0.0125)`) while keeping the hue rule and the sky reflection.
**The UVs are the picture too**: `_water` first took `flat_mesh`'s default, one UV per vertex,
and `texture(uFill, UV0)` read a single texel for ever — a flat, darker blue that looked exactly
like the bug it was meant to fix (the committed gate measures luma std **17.25** with the plan
UVs against **0.000** without — one value over 194,304 pixels, on a 300 × 220 cm pond at
40 cm). The flag alone is not the fix; the render gate
(`test_a_raised_pool_shows_the_plans_water`) is.
The screen-door copy `water_door.frag` must carry the same branch (a test pins the two files
apart only by the dither block).

**Measured** (dev box, Direct3D 11, 1000 × 400 top-down frame, two 300 cm squares at 40 cm): the
GRASS-patterned one reads luma std **26.0**, the SOLID one **0.0**, at the same mean
(121.3 / 120.8) — the texture is there and the average brightness is the fill colour.

Traps, all measured: `baseColorMap: patternMap` (a `var`) logs the `undefined` warning above;
a `Texture` re-pointed at a second data object renders white (§5 of `ogp-3d-renderer`), so a
shared picture is created with its data at birth and the sink refcounts it — the host drops it
with the last Model, which kept a recolour of a raised lawn from leaving one texture per colour
behind (`PatternTexture.uploads` 1 → 2, `textures_alive()` back to 0 after a remove). A
`fill_texture` part is not `tinted`: the picture carries the colour, so a patterned part's Model
tint is white — but its fade tint (`tintLinear`) must stay the fill colour, or the X-ray screen
door of a `vc` part (which samples no picture) ghosts white: measured max 255 before the fix. A water part's door DOES sample the picture, so a faded raised pool keeps its caustics. The engine holds
256 KB per picture plus the 256 KB tinted QPixmap it was made from (shared with the canvas's
200-entry cache).

### PF-L3D-18

- **Rule:** Measure an idle 3D view only after its first build was PRESENTED (a frame after the request, then a quiet stretch), and measure a frame cost A/B interleaved round by round — never in blocks.
- **Pinned by:** `tests/integration/test_living_garden_render.py::test_with_reduced_motion_the_idle_frame_counter_stays_at_zero`; `tests/integration/test_living_garden_render.py::test_the_particles_cost_at_most_fifteen_percent_of_a_frame_at_medium`
- **Source:** #389, ADR-070
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: the reduced-motion gate counted 2 "idle" frames under the render tier's environment
and 0 by hand; the frame-cost gate read rain +24 % in one run and +3.7 % in the next. Root
cause: the scene's update requests came at 1.8 s, their frames — the bench plan's pipelines and
the sky's light probe — were presented at 4.8–5.0 s, so "a second without a frame" was reached
before the first picture and the picture was counted as idle; and blocks of seconds per look
measured the machine's drift (clocks, background load), not the look. Fix: `_settle` waits for
a frame after the build was requested and then for a quiet second; `scenario_frame_cost`
renders each look once per round and compares medians over 40 rounds.

### PF-L3D-19

- **Rule:** A probe that compares "near" and "away" pixels of a perspective frame must bin them by the world quantity it cares about (elevation, bearing, distance) — an image row is a plane, not a cone.
- **Pinned by:** `tests/unit/test_board_probes.py::test_a_black_set_sun_is_a_dip_and_a_sky_without_it_is_not`
- **Source:** #695, #717
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: the new set-sun probe failed the **painted** sky on every frame with a 19.7–24.2 luma dip, always at the same reported elevation (−1.12°), while the images looked clean. Root cause: `sun_dip` compared pixels in the same image row; with a 70° field and a +3° pitch the away columns in the horizon rows sit several degrees higher in the sky, and the sky's vertical gradient read as a dip. Fix: compare near (±10° of the sun's bearing) and away (15–45°) pixels in the same 0.25° world-elevation band. The first synthetic positive control passed because its disc and band shared rows; the real camera exposed the difference.

### PF-L3D-20

- **Rule:** A probe marker sized in world units has no guaranteed screen size: before a pixel gate judges it, check that the whole marker is clear and size it from the camera, then pin the measured pixels.
- **Pinned by:** `tests/unit/test_render_beauty_board.py::test_a_distant_camera_gets_a_pin_that_shows_in_the_gate`; `tests/integration/test_view3d_looks_render.py::test_the_analysis_board_finds_its_probe_pin_on_the_built_world`
- **Source:** #704
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: `--analysis` on `bench_built` raised "the probe pin shows in 38 pixels only" before writing a sun-hours row, while the same board passed on `bench_small`. Root cause: the pin's height is a share of the sun-path dome (52 cm on that plan), and the built-world noon camera stands 27 m away; the old search also checked only the first 30 cm, so a point whose ball was under a canopy could win. Fix: require the whole pin to be clear, raise its height from the camera until it shows 60 px (gate 50, cap 4×), and record `pin_height_cm` beside `pin_px`.

### PF-L3D-21

- **Rule:** A structure's 2D picture and its 3D build read ONE parametric layout; never two tables of constants, and never a fixed sprite for one of them.
- **Pinned by:** `tests/integration/test_parametric_structures.py::TestPergola`; `tests/integration/test_parametric_structures.py::TestGreenhouseRidge`
- **Source:** #768 / #769
- **Status:** standing
- **Legacy:** none (new entry)

The old pergola was a 300 x 300 SVG stretched into the item's rectangle, while the 3D builder had its own post/rafter constants (two beams, no purlins): the owner saw a picture that did not match the model and could not scale it. `core/pergola.py` is now the one layout (four posts, four beams, nine rafters, five purlins, with the purlins' top at the item's height); `ui/canvas/items/pergola_paint.py`, the gallery thumbnail and `builders/structures._pergola` all consume it. The same rule made the glasshouse's glazing bays one constant (`core/greenhouse.py`) shared by the 2D bars and the 3D frame, and its ridge one linked `ROOF_RIDGE` rather than a fixed symbol.

### PF-L3D-22

- **Rule:** To give one sky another sky's brightness per elevation, match each ring to the other sky's GRADIENT without its sun, never to its ring means: a sun's glow in a reference ring is spread round the whole ring.
- **Pinned by:** `tests/unit/test_scene3d_atmosphere_sky.py::test_every_ring_of_the_drawn_atmosphere_is_as_bright_as_the_painted_gradient`
- **Source:** #716
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: the first model of the atmosphere's per-elevation profile, which matched every ring of the atmosphere to the painted sky's mean over the azimuth, put a bright ring round the sky at the sun's elevation: away from a 60° sun the drawn sky rose from 0.0845 at 50° to 0.0996 at 60° and fell to 0.0910 at 75° (exposed units, about 10 %). Root cause: the painted sky's disc glow sits within about 25° of the sun, so its ring mean at the sun's elevation is higher than the rings beside it, and the normalisation copies that bump to every azimuth of the atmosphere. Fix: `atmosphere_lut.sky_profile` matches each ring to `painted_gradient` (the painted sky without its sun) times one glow factor from `_balance`, so the light on the ground is still the painted sky's; the atmosphere keeps its own halo round the sun.

### PF-L3D-23

- **Rule:** Do not derive a drawn sky's level by inverting its shader's exposure curve: the frame passes the scene's tone mapping after it. Calibrate a sky level in the frame, from the response to two known scales.
- **Pinned by:** `tests/integration/test_view3d_looks_render.py::test_the_cloud_deck_meets_the_painted_horizon_without_a_band`
- **Source:** #719
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: a two-source model of the cloud deck's level (the example's sun through its airmass, and the sky-view table's ambient samples, both computable on the CPU) fitted its constants to the deck's radiance recovered through `1 − exp(−x × probeExposure)` and missed by −74 % to +23 % over the sun. The same inversion gave the painted Overcast at 10° a lower radiance than the deck, although the frame shows it 19 luma brighter. Root cause: at the noon Overcast the painted sky's radiance there predicts 0.39 through the curve, and the frame reads 0.62: the scene's exposure and tone mapping act on the sky after `skyExposed`. Fix: the deck's anchor (`look.ATMOSPHERE_DECK_LEVEL` and `ATMOSPHERE_DECK_SUNSET`) is measured by rendering the deck at two known factors per sun elevation and solving for the factor in the frame (ADR-048 addendum on #716/#719).

### PF-L3D-24

- **Rule:** A shadow map fitted to the casters (`lockShadowmapTexels: false`) is sharp at a low sun but follows the camera: fit it only for a frame whose camera holds still — a photo, an agent's picture and a held camera's time-lapse ask `Quick3DHost.capture(fitted_shadows=True)` by name — and keep the texel-locked sphere for the live view, an orbit, a flight and any capture that does not ask; locked, a cascade spans the sphere of its whole slice up to `shadowMapFar`, and `pcfFactor` is a radius in scene units that cannot hide a texel larger than it.
- **Pinned by:** `tests/integration/test_view3d_looks_render.py::test_a_long_low_sun_shadow_has_no_stairs_no_lit_teeth_and_no_streaks`; `tests/integration/test_directors_cut.py::test_a_still_camera_fits_its_shadows_and_a_moving_one_keeps_the_views`; `tests/integration/test_directors_cut_render.py::test_a_still_pictures_fitted_shadows_change_only_its_own_frame`; `tests/unit/test_board_probes.py::test_a_stepped_edge_is_measured_as_steps_of_its_own_size`
- **Source:** #734; ADR-059 addendum (#734)
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: in the app's default framing, a solid panel's shadow 20–40 m out stepped by 5 cm across its edge at 15° and 11 cm at 5.9° on High (2.2 / 6.2 px at 1080p), every caster's foot showed lit teeth up to 81 cm long at sunset (34 % of a line 15 cm out lit), and a picket fence's sunset shadow was strewn with bright streaks. Root cause (Qt 6.12's `setupCascadingCamerasForShadowMap`): locked, the last cascade spans a 170 m sphere — 8.3 cm texels on a 2048 page — and the day's `pcfFactor` 2 is 2 cm of light space for every cascade; at an oblique sun the pickets close their slits to 0.5 cm, far under a texel. Unlocked, Qt spans each cascade by the casters' box clipped to the camera's slice — about 1 cm texels on a 24 m plan, no measurable cost — but that box moves with every camera move. Fix: `lockShadowmapTexels: root.topDown || !root.fittedShadows`; `capture` defaults to the view's fit and puts the flag back after its frame; `write_photo`, `agent_picture` and a `HeldCamera` tour's frames pass `fitted_shadows=True` (the panel's far edge 0.64 / 2.24 cm, foot 0.023, streaks 0.165 in the render gate). Two wrong fixes: fitting the live view (a lone synthetic panel showed no extra crawl; the family garden orbited through the capture path crawled 0.69 / 0.38 px a frame fitted against 0.16 / 0.17 locked, 0–10 / 10–20 m) and fitting every capture by default (the self-test's capture-equals-the-view check failed by 24 levels: the frozen exe's `--selftest` would have failed). Dead ends, measured one at a time: a 4096 map halves the steps for four times the texels; a reach without the 9000 cm floor moved the golden-hour camera's 10–20 m band into the coarser cascade; a larger `pcfFactor` smeared the streaks into bands and softened every contact; moving `csmSplit2` traded near for far.

### PF-L3D-25

- **Rule:** Before blaming a renderer for a pattern in a shadow, check that it changes when the shadow map does: a "jitter" made from a multiplicative step modulo a small number is a RAMP, and a low sun stretches a ramp in a caster's height into a regular staircase along its shadow.
- **Pinned by:** `tests/unit/test_scene3d_builders.py::test_picket_tops_repeat_no_pattern_and_follow_the_items_seed`
- **Source:** #734
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: the family garden's fence shadow at golden hour showed regular stair steps, identical with a 4096 map, a tighter cascade and a 32-bit map. Root cause: the L0 picket fence lowered its pickets by `index * 7919 % 13 / 13 * 4` cm — and `7919 mod 13 = 2`, so the tops climbed 0.6 cm a picket for seven pickets and dropped, repeating every 13; at 15° every centimetre is 3.7 cm of shadow. The same formula made every picket fence in every plan a clone. Fix: each picket's drop is a hash of the item's seed (`fences.unit_hash`, `picket_seed`), 0.5–1.5 cm (`PICKET_DROP_CM`). The test checks the autocorrelation of the tops at lags 1–20 (the ramp reads 1.0 at lag 13) — one frame's look cannot tell a ramp from noise.

### PF-L3D-28

- **Rule:** A recorded frame shows its own moment: whatever the live view lets lag behind a threshold (the sky texture and its light probe follow the sun by 1°) is rebuilt EXACTLY on the recording path, or a lapse whose per-frame step is under the threshold updates it on alternate frames and flickers at half the frame rate.
- **Pinned by:** `tests/unit/test_scene3d_look.py::test_a_recorded_frame_asks_for_the_sky_of_its_own_sun`; `tests/integration/test_view3d_look_controller.py::test_a_recorded_frame_builds_the_sky_of_its_own_sun`; `tests/integration/test_directors_cut_render.py::test_a_day_lapse_does_not_flicker_at_dawn_or_dusk`
- **Source:** #799
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: a day time-lapse (04:00-23:00, 300 frames) stepped every second frame at dawn and dusk: the sky band of the family garden's default view zigzagged at RMS 3.86 luma (max 7.3), the frame-difference autocorrelation peaked at lag 2, the day was clean. Root cause: the tour's `settle_sky` used the live view's `SKY_REBUILD_DEG` 1°; the sun moves 0.5-0.7° a frame, so the sky and its probe (and the fog, which follows the SHOWN sky's horizon) were rebuilt on alternate frames while the key light and the exposure followed every frame. Fix: `sky_is_stale(..., threshold_deg=0)` is exact and `settle_sky` asks for it (`RECORDING_SKY_REBUILD_DEG`); the live timer keeps 1°. Measured: the alternation (third difference over eight, outside the rig's corners) 1.86 → 0.08 at dawn; the cost is a sky build a frame, 147 → 291 builds and 158 → 198 s for the 300-frame lapse. The survey's zigzag RMS still reads 0.79 at dawn after the fix: it also counts a smooth curve's bend and the rig's deliberate corners (0.5°, ±6°, the dew's −2°), which is why the gate measures the alternation.

### PF-L3D-29

- **Rule:** Judge a dusk on the GARDEN's light (the rows below the horizon), never only the whole frame — a sky-filled frame fades while the ground brightens — and size any light that is computed from a model on more than one framing: a flat ambient lifts a view full of vertical faces about 1.4x as much as a view of open meadow.
- **Pinned by:** `tests/unit/test_scene3d_look.py::test_the_garden_never_brightens_from_the_last_sun_into_the_night`; `tests/integration/test_view3d_looks_render.py::test_dusk_fades_and_sunset_is_no_cliff`; `tests/integration/test_living_garden_render.py::test_the_living_board_renders_every_shot`
- **Source:** #802
- **Status:** standing
- **Legacy:** none (new entry)

Symptom: the garden grew brighter as night fell (family garden, default framing: ground luminance 0.0196 at a 0.5° sun, 0.0188 at −1°, 0.0379 at night) while the board's `--dusk` gate, which reads the whole frame, passed. Root cause: not the twilight ramp's shape (the survey's guess): the night rig is "day for night" and lights flat ground about 0.95 EV above a 0.5° sun's sky, so the two anchors conflict and no ramp between them can fall monotonically. Fix: the twilight fill (`look.twilight_fill`): an ambient in the sky top's colour, carried by `Garden.qml`'s fill light where a sky lights the view, lifting a calibrated model of the light on open ground (`look.ground_light`) to a target that falls from the golden anchor into the night; both anchors keep the rig's own light. The first prototype held the default framing level but brightened the board's golden-hour camera by 14 % from 4° to 1° (the fill lit its vertical faces 1.12x as much while its fogged rows fell only 0.8x as fast): the day part keeps 40 % of the ground's own fall. On the small examples whose default framing is mostly meadow (balcony, raised bed) the fill lifts less than modelled and twilight still rises by up to 7 % (before: up to 140 %); on the balcony's golden-hour camera the night is brighter than its own 6° frame, which no fill can change while both anchors stay.

