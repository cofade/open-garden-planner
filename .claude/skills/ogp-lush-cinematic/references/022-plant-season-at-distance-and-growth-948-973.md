# A plant's season at distance and through growth - crop patches, bulb dormancy, bucketed forge, live year playback, a stable tip weight (#948, #963, #969, #970, #973, #995, #996)

The values and measurements behind FR-3D-FORGE-01/02/03/05/06/07, FR-3D-LIVE-01 and the ADR-064
addendum. Truth first: no height, spread, centring or date claim moved; the far crop
stays inside the plant's own height and `REACH_MAX`, and every LOD keeps its triangle
budget.

## The canopy tip weight is a green-canopy measurement (#969)

`FOLIAGE_TIP_WEIGHT` (`core/scene3d/builders/plants.py`) is the share of its palette's
tip anchors a plant's foliage shows; it keeps the mean sRGB hue within 10 degrees of the
2D sprite. The canopy constant is measured over `GREEN_LEAF_PALETTES` only:

| What | Value | Why |
|---|---|---|
| canopy tip weight | 0.43 over 19 green-leaved canopy sprites | the red-leaved Japanese maple moved the all-sprites median to 0.45 and re-tinted every green crown about one sRGB level |
| a coloured canopy | measured on its own sprite-level hue gate | a red- or purple-leaved tree is not a sample of the green crown's tip; a new colour form must not move the constant |
| the 40 golden trees | foliage mean colours re-measured once | the only intended change: 0.45 -> 0.43 on the green canopy |

The test (`tests/unit/test_scene3d_plants.py::test_the_tip_weights_are_measured_from_the_sprites`)
keeps the green sample and asserts it excludes at least one canopy sprite.

## A sparse LOD2 crown keeps its spread (#970)

The fit scales a plant's box to the canopy diameter and then pulls every vertex past
`REACH_MAX` back onto the circle. At LOD2 a crown is sparse, its farthest leaves sit on
diagonals, and the pull took the diameter in:

| Plant | Before (worst seed, LOD2) | After |
|---|---|---|
| jasmine | 0.890 | 1.040 |
| clematis | 0.890 | 1.040 |
| wisteria | 0.890 | 1.040 |
| cucumber | 0.874 | 1.040 |
| pea | 0.874 | 1.040 |
| climbing-plant category | 0.890 | 1.040 |
| sunflower | 0.881 | 0.941 |
| pear / plum / cherry / oak / birch / willow | 0.911-0.934 | 1.040 |

`assemble.pin_foliage_spread(parts)` turns the fitted foliage's four farthest leaves
about the item's axis so their farthest vertices land on +x, -x, +y and -y; 1.040 is
`REACH_MAX` and inside the gate's +10 %. **It runs after the fit.** Pinning before the fit
made the axis-aligned box larger, so the fit scaled every leaf down and a tall LOD2 birch
fell below its foliage-coverage gate (0.693 against 0.8). Only LOD2 is pinned: beyond
45 m a leaf turned about the trunk is not seen, and LOD0/1 pass every seed. The sunflower pins
its four outermost stem blades (pre-fit, `_pin_spread_to_axes`) because its foliage mixes
curved blades and micro-leaves.

## A spring bulb is dormant, not evergreen (#963)

`Traits3D.leaf_months` (crocus/daffodil February-June, tulip March-June) replaces the
deciduous/evergreen rule for those three; `BULB_LEAF_RAMP_DAYS = 14` fades the clump in
and out. `Traits3D.evergreen` is false for a dormant plant. Measured at 52 N:
crocus/daffodil leaf density 1.0 from February to June, 0 in January, July-December;
tulip from March. At 35 S the six-month seasonal shift applies. At LOD2 the scapes now
live in the flowers part (they are the flowers' stalks), so a July bulb shows neither
leaves nor bare stalks; the neck (5 % of the height) remains.

## The forge cache buckets sizes, the mesh is stretched to exact (#973)

`cache.QUANT_STEP = 1.02`; a size's bucket is `round(log(cm) / log(1.02))`, the build
size `1.02 ** bucket`. A cache hit is scaled to the requested height and spread
(`Mesh.scaled`: positions scaled, normals inverse-transposed, unit length kept). Without
a cache the exact size is built and nothing is scaled.

Measured on a cherry growing 300 -> 570 cm with its radius in proportion, LOD2, 365
daily sizes: **65 builds and 300 hits**, every day's mesh top within 0.5 cm of the day's
height and its spread inside the 10 % gate. Before #973 the key kept 0.01 cm and every
day was a miss. The 65 is about twice the ~33 dimension steps because height and radius
bucket independently. A fence-trained climber's support distance is derived from the
plant's exact radius; it is bucketed by the same 2 % of the quantised radius, so the
climber's key changes with its size bucket, not every day (the support contact may be off
by that half step, well inside the 50 cm support search).

Fruit's phase: `accents.build_fruit_accents` gives each spheroid a phase in UV.y; the
fruit part's season opacity is `(ripeness - 0.55) / 0.45` (ripeness starts at 0.55), and
`screen.vert` collapses each fruit whose phase is not below it. The crop appears over the
harvest window, not on its first day.

## Beyond 45 m the crop stays, as patches (#948)

LOD2 built no accent at all. `accents.build_far_accents` now makes single-sided triangular
patches of the crop colour on the crown's outer shell:

| Family | Patch side | Most patches | Colour |
|---|---|---|---|
| flowers / blossoms / clusters / puffs / umbels | 0.16 x the canopy radius | 64 triangles | the recipe's `flowers` spec outer colour, or the cluster/puff/umbel light colour |
| fruit | 0.10 x the canopy radius | 64 triangles | the fruit kind's middle colour |

The LOD2 foliage reserves 64 triangles for them **only when a far family exists**; a
leaf-only canopy keeps the old 16 and its full foliage (birch, willow and Japanese maple
would otherwise lose 24 leaves; #948 review). A cherry with both families gets 32 + 32.
The patches are `with_phase`d, so they open or ripen one by one with the existing
bloom/ripeness state; `_clamp_accent_geo` keeps them inside the plant's height and
`REACH_MAX`. A far flower leans its normal about 30 degrees to the sky and its colour is
lifted by up to ×1.35 with a hue-preserving peak clamp at 0.9 linear, because a flat
vertical patch on the shade side read mauve at golden hour (34 % of its pixels; the tilt
and lift bring it to 27 %). A bulb's far
flower is a small double-sided patch at its scape tip, capped by its canopy radius - a bed
cue at distance, not a single-plant read. A sunflower's head - placed by its builder, not a
crown - gets the same far patch on each stem tip. Pods and root crowns have no far cue
(their green or underground colour does not read at 45 m); pods now ripen by phase like
fruit.

**Measured:** a 4.2 m cherry at 45 m in a 1600 x 900 frame (40 degree vertical FOV):
in bloom 704 crop-coloured pixels of the 942 the far parts change; at ripeness 0.775,
147 of 289. Without the far parts the crown is plain green. Under the golden-hour look
(15.2 degree sun) 27 % of the far-flower pixels still sit in the mauve band (a flat
vertical patch read 34 %); the crown reads as blossom, and the remaining shade is an
owner taste question. A tulip at 2 m shows 3,458 plant pixels on 15 April (red flowers
and green straps) and 54 on 15 July (the 2.5 cm neck only). The engine gate is
`tests/integration/test_plant_forge_workspace.py::test_a_far_crop_and_a_dormant_bulb_render`
(driver `plant_forge_far_driver.py`).

**Rejected:** a crown tint (needs a per-item LOD channel through the host and QML, and
would tint the real flowers at close range); individual far flowers (sub-pixel at 45 m
inside the 800-triangle budget).

## Live year playback keeps forged models on screen and never stalls the RHI (#995, #996)

Manual testing of #973 on `spring-garden.ogp` showed that bucketing `ForgeCache` alone was
not enough for live year playback: every 500 ms `Scene3DController` regrowth pass still
called `SceneSync.apply(records)` with `prepared=None`, which built a v0 `build_silhouette`
for every growing plant on the GUI thread and deleted `_applied_state` in
`ForgeWorker.invalidate()` (leaving winter trees with stale `leaf_density == 0` in QML as
bare conical `_trunk` stumps!). Meanwhile `Workspace._step_forge` accumulated `_retired`
until `QQuickWindow.releaseResources()` and `AutoPreset` step-downs triggered 4.3-5.5 s
synchronous RHI shader recompiles on the next frame, and `SunShadowController._recompute`
solved 2D shadow polygons on every 200 ms tick even in pure `VIEW3D` mode.

| Metric (6 s year playback on `spring-garden.ogp` in `VIEW3D`) | Before (#995/#996) | After |
|---|---|---|
| `v0_build_plant` calls during playback | 132 | 0 |
| `SunShadowController._recompute` in pure `VIEW3D` | 26 (1,143.3 ms) | 0 |
| `QQuickWindow.releaseResources()` during playback | 2 (~5,032 ms stall each) | 0 |
| `AutoPreset` quality during drain & playback | `high -> medium -> low` (4.3 s + 5.5 s stalls) | `high -> high` |
| Presented frames in 6 s | 69 (~11.5 FPS) | 242 (~40.3 FPS) |
| Max `processEvents` turn | 6,060.6 ms | 137.2 ms |

## Traps for the next change

- A far accent is added AFTER the fit: clamp it (`_clamp_accent_geo`) or its patches leave
  the recorded height.
- Pinning a sparse crown BEFORE the fit silently shrinks every leaf through the fit scale;
  the coverage gate is what notices.
- A bulb's scapes belong to the flowers part at every LOD; in wood they stand all year.
- `Mesh.scaled` must inverse-transpose normals: a non-uniform stretch otherwise tilts
  every leaf normal and the flat-face winding gate fails.
- Never pass `prepared=None` to `SceneSync.apply` for already-forged growing plants, and
  never allow `QQuickWindow.releaseResources()` or `AutoPreset` step-downs during playback
  or `ForgeWorker` uploads (PF-L3D-38).
