# A plant's season at distance and through growth - crop patches, bulb dormancy, bucketed forge, a stable tip weight (#948, #963, #969, #970, #973)

The values and measurements behind FR-3D-FORGE-01/02/05/06/07 and the ADR-064
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
fell below its foliage-coverage gate (0.693 against 0.8). Only LOD2 is pinned: at 18 m+
a leaf turned about the trunk is not seen, and LOD0/1 pass every seed. The sunflower pins
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
bucket independently.

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

The LOD2 foliage reserves 64 triangles for them (32 leaves fewer than the old 16-triangle
reserve); a cherry with both families gets 32 + 32. The patches are `with_phase`d, so they
open or ripen one by one with the existing bloom/ripeness state; `_clamp_accent_geo` keeps
them inside the plant's height and `REACH_MAX`. A bulb's far flower is a double-sided patch
at its scape tip (2.5 x the flower radius, capped at 0.22 x the canopy radius).

**Measured:** a 4.2 m cherry at 45 m in a 1600 x 900 frame (40 degree vertical FOV) reads
as a green crown with a pink speckle in bloom and red specks at ripeness 0.775; without the
far parts it is plain green. A tulip at 2 m shows red flowers and green straps on 15 April,
and on 15 July the frame holds only the 2.5 cm neck.

**Rejected:** a crown tint (needs a per-item LOD channel through the host and QML, and
would tint the real flowers at close range); individual far flowers (sub-pixel at 45 m
inside the 800-triangle budget).

## Traps for the next change

- A far accent is added AFTER the fit: clamp it (`_clamp_accent_geo`) or its patches leave
  the recorded height.
- Pinning a sparse crown BEFORE the fit silently shrinks every leaf through the fit scale;
  the coverage gate is what notices.
- A bulb's scapes belong to the flowers part at every LOD; in wood they stand all year.
- `Mesh.scaled` must inverse-transpose normals: a non-uniform stretch otherwise tilts
  every leaf normal and the flat-face winding gate fails.
