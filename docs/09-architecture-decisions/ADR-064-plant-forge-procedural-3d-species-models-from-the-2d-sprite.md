---
id: ADR-064
title: "Plant Forge — Procedural 3D Species Models from the 2D Sprite Recipes, LODs and Phenology"
status: "Accepted; shipped in v1.32.0 after owner acceptance (PR #593)."
refs: ["#387"]
legacy_anchor: adr-064-plant-forge--procedural-3d-species-models-from-the-2d-sprite-recipes-lods-and-phenology-387
---

# ADR-064: Plant Forge — Procedural 3D Species Models from the 2D Sprite Recipes, LODs and Phenology

**Status:** Accepted; shipped in v1.32.0 after owner acceptance (PR #593).
**Date:** 2026-10-25
**Context:** L3 replaces the first silhouettes with procedural species models,
while preserving plan dimensions, responsive navigation and a shared local date.
The implementation contains 123 recipes in 13 archetypes; the initial PR text's
128 recipes, 16 habits, invented trait APIs and smaller triangle limits were
incorrect and are replaced here by executable contracts.

**Decision:**

1. **One art source.** Frozen `Traits3D` combines crown, branching, leaf and
   illustrative seasonal traits from the existing recipes. The exact Lemon Balm /
   Melissa officinalis alias resolves to the herb category before word matching
   (L3.0 explicitly requests this correction; the earlier #446 decision had left
   it unresolved). Melon and flax keep the already-correct category fallbacks.
   `core/object_art/materials.py` supplies the unchanged object SVG colour tables.
2. **Qt-free synthesis.** `core/plant_forge/` uses stdlib and NumPy for
   space-colonisation skeletons, parallel-transport tubes, geometric micro-leaves,
   tiered conifers, palms, shrubs, hedges, herbaceous forms and climbers. Total
   triangle caps are 25,000 / 6,000 / 800 at LOD0/1/2, as issue #387 requires;
   distance thresholds are 18/45 m. Foliage counts derive from crown area with
   target coverage 1.6; capped distant crowns receive larger leaves. Deciduous
   structural wood keeps its base and full height independently of foliage.
3. **Bounded instance cache.** The LRU stores fully sized, seeded immutable meshes,
   at most 256 entries and 64 MiB of array data. It is not a unit-template cache.
   Local cold synthesis across all 123 recipes (height 420 cm / radius 180 cm / seed 303,
   median of three per recipe, Python 3.11) measured median 3.69 / p90 13.07 / maximum 23.01 ms;
   warm median 0.0012 ms. A disk cache is unnecessary against the issue's median
   150 ms budget. These numbers exclude GUI uploads and presentation.
4. **Background synthesis, main-thread admission.** The workspace retains the
   existing first silhouettes and uses a one-job executor for upgrades. A GUI
   timer admits only a current document epoch, geometry signature and LOD.
   Controller recovery invalidates applied upgrades; orbit and walk camera
   movement update visibility/distance ordering and LOD. Render flags never
   disable this production feature. The Beauty Board uses the same forge and
   seasonal path, rather than silently rendering the old registry alone.
5. **Support precedence.** A climber first uses its trellis parent; otherwise the
   nearest fence/wall/pergola/trellis within 50 cm of its canopy edge, accounting
   for path width, then a three-pole bamboo tripod. Supports are transient record
   inputs, not saved plan mutations. The guide carries the finite segment in the
   plant's local frame, its physical width and relative height/base. Vines reach
   a support within the recorded canopy; a farther support supplies direction
   without enlarging the footprint to invent contact. Resolution runs with
   synthesis on the worker thread. Exact support/plant geometry dependencies
   invalidate its cache and reject older in-flight guides; date-only updates
   reuse them, retaining current plant height and seed.
6. **Stable seasonal geometry.** Flowers, fruits/pods and tubers are separate
   parts. Foliage density/tint/snow, bloom and ripeness update persistent Models
   without mesh copies on season-only changes. Leaf collapse removes seasonal
   shadows too; X-ray retains its independent screen-door shadow policy.
   `core/calendar_windows.py` owns exact frost-relative arithmetic, re-exported
   at the old task-generator API; phenology reads instance harvest offsets and
   the plan's frost dates across all contributing anchor years. Hemisphere
   shifting applies to illustrative seasonal cycles, never to recorded local
   frost dates. Plant existence remains #315's shared clock/lifetime rule.

**Alternatives rejected:** GUI timer batches still block the GUI during synthesis
(measured six-apple batch 116.6 ms). Replacing meshes on a date step defeats the
16 ms scrub contract. A merged accent mesh cannot hide spring fruit independently
of blossom. A render-only feature bypass makes green gates irrelevant to shipping.
A disk cache adds persistence/versioning costs without the measured need.

**Consequences:** No external asset or runtime dependency, plan format change, or
new persistent setting. The old silhouettes remain a temporary first view.
Acceptance uses the production workspace, real engine seasonal tests, 40 mesh
references, calendar/geometry regressions and an independently rendered board.
The 300-plant date budget calls the workspace's actual refresh path with 100
supports, including queue admission and QML updates, rather than timing only
the phenology evaluator. It also asserts unchanged Models/buffers and no new jobs.
The owner approved final beauty and interactive use on 25 October 2026. PR #593
merged under protection and its exact merge commit was released as v1.32.0.

**Finalization benchmark correction (PR #597).** An unchanged-head Windows job
read 16.8508 ms against 16 ms while its matching PR job passed. Five independent
local WARP runs ranged from 10.59 to 24.21 ms under the original maximum-of-three
statistic. Settled collocated controls read 17.49/16.33 ms; grid controls read
13.67/14.93 ms. These observations establish variance and an unrepresentative
fixture, but do not prove render contention or a production regression.
Following the existing NFR median protocol, the gate now establishes typical
per-date callback cost with one fixed set of 15 interleaved samples per date,
retaining the 16.0 ms threshold. Section 8.29.11 defines the protocol, raw/tail
reporting and injected 20 ms negative control. The statistical guarantee has
changed explicitly; no absolute deadline or presented-FPS guarantee is claimed.
This correction changes tests and documentation, not the released runtime.

**Addendum (2026-11-24, #598 — the seasonal callback's headroom).** Measured per stage,
the scene's `setPlantSeasons` was 85 % of the 300-plant callback, and most of it did not
depend on what changed (the payload's conversion to JS, generic property reads). Decided:
the season values cross the host boundary as item ids plus one native float64 buffer of
`SEASON_STRIDE` numbers per plant (`host.season_payload`); the scene keeps an index of its
seasonal parts with what it last wrote and writes only what changed. *Rejected:* sending
only the plants whose state changed (a date step changes nearly all of them — no gain on
the measured case); moving the tints into the materials' uniforms from Python (a second
write path beside the QML bindings that X-ray, Cutaway and the surfaces read). Result and
protocol: §8.29.11 — worst date medians 5.9–6.3 ms on the RTX 4070 and 6.8–7.6 ms on WARP
(13.2–15.3 before); CI asserts 16 ms again, and the render3d jobs of PR #1016 passed on it.
**Status**: Shipped in v1.42.1 (PR #1016).

**Addendum (plant seasonal truth and forge stability, issues #948, #963, #969, #970, #973, #995, #996).**
**Status**: Shipped in [v1.41.2](https://github.com/cofade/open-garden-planner/releases/tag/v1.41.2) after owner acceptance (2026-11-22; [PR #994](https://github.com/cofade/open-garden-planner/pull/994)).
Seven follow-ups to #940 settled how a plant's season survives growth, distance, live year
playback and a growing
species catalogue. (1) **The canopy's tip weight is measured over green-leaved sprites only**
(`GREEN_LEAF_PALETTES`, `FOLIAGE_TIP_WEIGHT["canopy"] = 0.43`). The red-leaved Japanese maple
had moved the all-sprites median from 0.43 to 0.45 and re-tinted every green crown about one
sRGB level; a coloured canopy is now measured on its own sprite-level hue gate and cannot
move the green constant. (2) **A sparse LOD2 crown keeps its spread by turning its four
outermost leaves onto the plan's axes after the fit** (`assemble.pin_foliage_spread`). The
fit scales the box to the canopy and then pulls diagonal tips onto `REACH_MAX`; at LOD2 a
jasmine, cucumber, pea or climbing-plant crown came out at 0.865-0.893 of its diameter on
some seeds. Pinning before the fit was rejected: the larger axis-aligned box made the fit
scale every leaf down, and a tall birch fell below its foliage-coverage gate. Only LOD2 is
pinned; beyond 45 m a leaf turned about the trunk is not seen, and LOD0/1 pass every seed.
(3) **A spring bulb has a leaf window of its own** (`Traits3D.leaf_months`: crocus and
daffodil February-June, tulip March-June). The deciduous rule would have made it bare in
February and leafed all summer; its 14-day ramps replace a step on the 1st, and a dormant
bulb is not `evergreen`. At LOD2 its scapes now live in the flowers part, so July shows
neither leaves nor bare stalks. (4) **The forge cache keys on 2 % geometric size buckets**
(`cache.QUANT_STEP`, `quantised_size_cm`) and stretches a hit to the day's exact height and
spread (`Mesh.scaled`, inverse-transpose normals), so a growing tree keeps one shape for a
bucket instead of being re-forged and re-randomised every day: a 90 % growing season costs
about 65 builds, not 365, and every day's height and spread stay exact. Without a cache the
exact size is built unchanged. (5) **Each fruit carries its own phase** (`accents.with_phase`)
and the fruit part's season opacity is the ripeness progress `0.55 -> 1`, so a crop ripens
one fruit at a time instead of all of it appearing on the harvest window's first day.
Beyond 45 m (**#948**) a flowering or fruit-bearing LOD2 plant (other than a pod) keeps a
sparse crop of large,
single-sided colour patches (`accents.build_far_accents`, at most 64 triangles per family,
inside `REACH_MAX`) whose colour comes from the recipe's own `flowers`/`clusters`/`puffs`/
`umbels`/`fruit` table, with a flower's normal leaned about 30° to the sky and its colour
lifted by up to ×1.35 with a hue-preserving peak clamp at 0.9 linear, so a low sun does
not turn its shade side mauve. A canopy
that has a far crop reserves 64 LOD2 triangles for it; a leaf-only canopy keeps the old 16
and its full foliage. A sunflower's builder-placed head gets the same far patch at its stem
tips; pods and root crowns have no far cue and pods ripen by phase. A crown tint was rejected: it needs a per-item LOD channel through the host
and QML, and it would tint the real flowers at close range. (6) **Live regrowth never downgrades
an already-forged plant to a v0 silhouette (#995):** `Scene3DController` asks
`ForgeWorker.prepare_for_sync` for prepared `PartSpec`s before `SceneSync.apply`, returning a
stretched warm 2 % bucket hit immediately (and keeping its `_applied_state`), stretching the
last forged mesh on a cold bucket miss while the background worker builds the new bucket, or
forging a newly appearing dated plant directly when the scene is already forged; `Workspace`
also evaluates seasonal uniforms on every `SimClock.date_changed` tick and harvests up to 16
plants per `_step_forge` turn. (7) **Toolbar playback holds quality, defers RHI cache drops
and skips hidden 2D work (#996):** while `SunSimToolbar` playback runs, `Workspace` holds
`LookController.hold_preset` and defers `QQuickWindow.releaseResources()` (and resets the
auto-quality sample window during pipeline passes and `ForgeWorker` uploads), `SunShadowController`
skips 2D shadow polygon solves in pure `VIEW3D` mode without `DrapeMode.SHADOWS`,
`CanvasScene.refresh_timeline` invalidates only plants whose canopy radius changed, and
`GardenPlannerApp` defers heavy 2D date diagnostic sweeps until playback stops (PF-L3D-38).
**No `.ogp` format change.**
FR-3D-FORGE-01/02/03/05/06/07, FR-3D-LIVE-01; tests `tests/unit/test_plant_forge_bloom.py`,
`tests/unit/test_plant_forge_l31.py`, `tests/unit/test_phenology.py`,
`tests/unit/test_plant_art.py`, `tests/unit/test_scene3d_mesh.py`,
`tests/unit/test_scene3d_plants.py`, `tests/unit/test_quick3d_qml.py`,
`tests/integration/test_plant_forge_workspace.py` and the 40 golden
tree references (their foliage colours were re-measured once, for #969).

## ADR-064 addendum 2: species forms from the plant's own size (#949, #956, #960)

**Status**: Shipped in [v1.41.3](https://github.com/cofade/open-garden-planner/releases/tag/v1.41.3) after owner acceptance (2026-11-23; [PR #998](https://github.com/cofade/open-garden-planner/pull/998)).

**Context**: the Forge had one palm and one conifer silhouette. A dwarf fan palm
therefore got the windmill palm's bare 0.64-height trunk, a Scots pine got a spruce
cone, and a grape vine on a pergola stayed a column at the post because the support
resolver only knew a rectangle's edge.

**Decision**:
1. **The palm's trunk is a function of the plant.** A palm at or below 160 cm, or one
   whose canopy diameter is at least 1.5 times its height, is the dwarf/clumping form:
   `trunk_share = 0.08`, half the trunk rings, three more fronds, gentler lean
   (`0.05..0.16` vs `0.14..0.34`), and ascending fronds clamped above ground so the trunk
   base stays grounded at `z = 0` across all LODs. A taller palm keeps
   `max(crown.trunk_share, 0.64)`. One builder (`plant_forge/woody.build_forged_palm`),
   chosen from the recorded size.
2. **The Scots pine is an `umbrella`.** `traits3d` gains the named crown shape;
   `build_forged_conifer` (`plant_forge/woody.py`) gives it a broad lower crown, a
   flat-topped head (broad to 80 % of the crown), a short narrow needle (recorded at
   6 cm, width ratio 0.18; the crown-area budget may lengthen it, not widen it), and a
   needle spray that covers each branch to its tip while the wooden branch stops at
   85 %, so no bare spokes show. Other conifers are unchanged.
3. **A pergola climber follows the rafters.** `climbers._support_segments` asks
   `core/pergola.layout` for the pergola's own rafters centred on the footprint bounding
   box, `_concrete_support` records the pergola centre in the plant's local frame, and
   `build_forged_climber` climbs the post to the rafter deck before fanning overhead along
   the nearest rafter and inward across neighbouring rafters within the plant's canopy
   radius. A pergola too small for that layout keeps its outline; trellis and path supports
   are unchanged.
4. **The Japanese maple's leaves are small** (`recipes.py` leaf scale 0.45, from 0.65),
   so its crown is not a mass of large diamonds. The green canopy's tip weight stays
   #994's 0.43, measured over green-leaved sprites only.

**Alternatives rejected**: a second palm builder (two silhouettes to keep in step);
scaling a tall palm down (the trunk stays, the fronds would sink); a pine palette-only
change (the cone is geometry); a pergola's bounding rectangle (the very shape that made
the vine a column); a saved support segment (the support is transient and must follow
the pergola when it moves).

**Consequences**: no `FILE_VERSION` change; no new dependency. The forms are runtime
only. Pinned by `tests/unit/test_plant_forge_l32.py`
(`test_a_scots_pine_is_an_umbrella_not_a_spruce_cone`,
`test_a_dwarf_palm_is_trunkless_and_a_tall_palm_is_not`),
`tests/unit/test_plant_forge_l34.py::TestL34ClimberSupportResolution::test_a_climber_on_a_pergola_is_trained_along_a_rafter`,
`tests/unit/test_plant_art.py` (the crown-shape set), and
`tests/unit/test_scene3d_plants.py` (the measured tip weight).
