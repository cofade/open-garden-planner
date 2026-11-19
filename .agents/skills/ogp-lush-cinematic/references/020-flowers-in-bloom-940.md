# Flowers in bloom — counted by the crown, on their wood, opening one by one (#940)

The rules #940 gave a plant's flowers (`core/plant_art/traits3d.FlowerTraits`,
`core/plant_forge/accents.py`, the bulb and stemmed-flower builders in `herbaceous.py`,
`core/phenology.py`), the values they hold, and how they were measured. Truth first: no
height, spread, date or position moved; the flowers are inside the plant's height and
reach (the bulb's top IS a flower's), every LOD keeps its 25,000 / 6,000 / 800 budget, and
wood, foliage and fruit of the 40 golden trees are byte-identical.

## What hid the flowers

The spring garden's 18 April showed full green crowns and green blade tufts: in 1.5-3 m
close-ups the reviewer counted 0.000-0.018 % flower-coloured pixels. Five causes, the
first not visible in the code's numbers at all:

1. **Every petal faced the ground.** The petal quads were wound so their front face
   pointed away from the flower's facing (86 % of the flowers' normals had z < 0), and the
   plant's `vc` material culls back faces — no petal showed from above, only the small
   centre spheres did (the "1-2 mm dots"). Before resizing or recounting a part, check that
   it can be SEEN: the share of its triangle area facing the camera
   (`test_every_petal_shows_from_above_and_below`: 14 % faced the sky before, 50 % now).
2. **A fixed count:** `max(3, n × 2)` — about 12 flowers on a whole tree.
3. **Size followed the plant** (`plant_scale`, floored at 0.30): a tulip's flower 1.2 cm.
4. **A bulb's flowers sat inside its blades** (anchors at 42-94 % of the height).
5. **Leaves of July in April:** the budburst ramp gave magnolia, cherry, plum and forsythia
   a leaf density of 0.943 on 18 April.

## The values (round 1; review 2 below changes some)

| What | Value | Why |
|---|---|---|
| A flower's radius | half its recipe radius (`FLOWER_CM_PER_RECIPE_RADIUS` 0.5) | the 2D recipes draw a flower about as many sprite units across as it measures in cm: tulip 3 cm, crocus 2.5, rose 3.25, peony 4.25 |
| … a fruit tree's blossom | 3.5 cm, 5 petals, no centre (`_TREE_SPUR_BLOSSOM`) | one spur's cluster of 3-5 flowers; a berry shrub's single flowers 1.5 cm |
| … a magnolia | 8 cm, 6 petals, cup 1.0, facing 0.75 to the sky | M. × soulangeana's goblets are 15-25 cm across; half the recipe radius undersold it |
| … a sunflower | 11 cm, centre 0.45 of it | a garden sunflower's head |
| Crown cover (`FlowerTraits.cover`) | canopy 0.30, mound / feathery / climber / rosette 0.10, ground 0.15; forsythia 0.45, spirea 0.30, aster and chrysanthemum 0.25, pansy 0.25, petunia, thyme, chamomile 0.20, rose 0.18, magnolia 0.14, peony and dahlia 0.06, hibiscus 0.05 | the share of the crown's outer surface in flower at full bloom — illustrative values like the bloom months, not measurements: masses of small flowers more, a few big ones less |
| Count | `cover × crown_surface_cm2 / (π r²)` | the crown ellipsoid the leaves count by (Thomsen, p = 1.6075) |
| Over budget | fewer, larger flowers, ≤ 1.8× at LOD0, ≤ 3× at LOD1 (`FLOWER_ENLARGE_MAX`); 64 triangles kept free | as fewer, larger leaves keep a distant crown's leaf area — never a sparser bloom |
| Petals | LOD0 quads (≤ 10 a whorl, a second whorl for a double flower), LOD1 one triangle each (≤ 6, one whorl); every petal twice, wound both ways | double-sided under back-face culling |
| Petal shape | from 0.10 r at the base to a blunt tip at r that closes the ring (`PETAL_RING_SHARE` 0.88) | a spiky star read as a crown of thorns; a closed ring reads as one disc or goblet |
| Cup | the tip rises `1.3 × cup × r` (tulip 1.15, crocus 1.0, peony 0.6, rose 0.55, aster 0.12, daffodil 0.12) | a tulip's goblet 1.5 times as deep as wide |
| Petal normals | the face's normal + 0.8 up + 0.35 × (vertex − centre) / r (`PETAL_SKY_BEND`, `PETAL_SPREAD_BEND`) | a thin petal seen from below takes the sun through it; the plain back face rendered near-black maroon (round 1) |
| Petal colour | base 0.92 × the petal colour, tip 0.45 toward the light colour; back 0.82-0.95 × the petal colour | the 2D sprite's petal is its outer colour with a light tip over about a third; the full light tip made daffodils cream-white and crocuses lavender-grey |
| Anchors | leaves within 0.78 (`CROWN_SHELL`) of the farthest leaf in their direction from the foliage's centre (18 × 9 direction bins); none facing steeper down than z −0.55; the flower 0.35 r out of the leaf | a flower inside a crown is hidden by its leaves |
| A bulb (tulip, daffodil, crocus, iris, lily) | strap leaves ≤ 60 % of the height (`BULB_LEAF_TOP`), one leafless scape per flower, flowers inside the fit, `SCAPE_COVER` 0.45 of the clump's ground in flower (tulip on 10 cm: 5, crocus on 5 cm: 2), ≤ 24 | the flower's top is the plant's height; at LOD2 no flower, the scapes reach the top |
| A precocious bloomer's leaves in bloom (`bloom_leaf_density`) | magnolia 0.08, forsythia 0.06, peach 0.10, plum 0.12, cherry 0.18; unfolding over the last quarter of the bloom window (`BLOOM_LEAF_UNFOLD_FROM` 0.75) | a share of leaf AREA: the leaves broken by then are a few cm, the model's are full-grown. 0.35 still read as a green cherry (round 1). Apple and pear flower among unfolding leaves and keep theirs |

## How to measure a flower

Count the pixels the flowers themselves make: render the same camera twice through the
production board path (`render_beauty_board.Board.frame`, the forge worker's LOD0), once as
is and once with every plant's `flowers` part dropped from the forge's output, and count the
pixels whose colour moved by more than 20/255 in some channel AND whose hue turned by more
than 25°, whose saturation moved by more than 0.2, or whose value ROSE by more than 0.06 — a
flower's shadow only darkens and keeps the hue. The life (butterflies) is the noise floor,
about 0.01 %. Clusters and puffs (lavender, rhododendron) are part of `flowers` and count.

## Measured after round 1 (High, 1600 × 900, each plan at its showcase moment, LOD0)

The share of the frame the flowers make (the method above), the same cameras before and
after #940 (eye → target in plan cm):

| Plan, shot | Camera | Before | After |
|---|---|---|---|
| spring garden 18 Apr, orbit start | the stored "Garden orbit" pose | 0.013 % | 5.03 % |
| spring garden, default framing | the app's | 0.012 % | 3.95 % |
| spring garden, close | (700, 90, 190) → (700, 620, 90) | 0.057 % | 6.67 % |
| spring garden, magnolia ~3 m | (520, 330, 170) → (280, 540, 220) | 0.055 % | 18.0 % |
| spring garden, cherry | (800, 300, 170) → (1110, 500, 300) | 0.024 % | 13.8 % |
| spring garden, plum | (480, 60, 160) → (240, 230, 220) | 0.017 % | 18.5 % |
| spring garden, apple | (900, 60, 160) → (1150, 190, 220) | 0.036 % | 14.2 % |
| spring garden, forsythia | (380, 600, 150) → (95, 620, 90) | 0.095 % | 18.5 % |
| spring garden, tulips | (700, 560, 110) → (500, 712, 15) | 0.079 % | 7.40 % |
| spring garden, crocus (east / west) | (900, 170, 70) → (900, 320, 0) / (500, 20, 70) → (500, 170, 0) | 0.24 / 0.25 % | 5.66 / 3.83 % |
| cottage garden 20 Jun, orbit start | stored pose, ~26 m | 0.080 % | 0.51 % |
| cottage garden, 15 m | (600, −700, 650) → (600, 700, 60) | 0.067 % | 0.48 % |
| cottage garden, close | (600, 110, 260) → (600, 700, 40) | 0.38 % | 2.40 % |
| food forest 21 Sep, asters ~8 m | (1850, 1050, 190) → (2520, 1520, 220) | 0.003 % | 1.21 % |
| food forest, orbit start | stored pose, ~40 m | 0.000 % | 0.068 % |

The before crocus share is the yellow centre dots alone. "A year in the garden" (the
stored held pose): April reads as blossom (pink, white, yellow crowns, sparse leaves),
July as green summer crowns with cherries — before #940 the two frames were alike. At
LOD1 (forced on every plant) the trees' flowers are fewer and up to 3× larger: the cherry
244 instead of 813, the rose a clearly pink dome from the cottage orbit.

## Review 2: what changed and why

The second independent review (frames and probes measured on the merged branch) found one
truth gate failing and five P1. The values that moved:

| What | Was | Now | Why |
|---|---|---|---|
| A bulb's and an allium's spread | the box of a few blades, fitted to 2 r, then every vertex past `REACH_MAX` pulled onto the circle | the four outermost leaves along the plan's axes (within 0.15 rad) at the clump's longest reach (`herbaceous._pin_spread_to_axes`) | with the box's extremes on diagonals the pull took them in: a daffodil 0.868 of 2 r at LOD2, a crocus 0.870, an onion 0.847 - the spread gate failed. Now 0.95-1.03 over seeds 0-63 |
| A bulb's scapes | its wood, shown all year | in its flowers part with the flowers; its wood is its neck (5 % of the height) | ten months a year the bulb stood as bare dark stalks |
| Bloom in its window | a step: 1 on the window's first day, 0 the day after its last | opens over the first `BLOOM_RAMP_DAYS` (10) of its run of months, fades over the last | "A year in the garden" popped whole trees in and out of flower on the 1st |
| How flowers fade | the part's visibility, then the colour pass's dither | each flower collapses by its own phase (UV.y, `accents.with_phase`) in `qml/screen.vert`, in every pass, its shadow too | the dither left whole crowns under the shadows of flowers barely drawn |
| The screen door's colour | `VAR_COLOR` | `COLOR` handed on through `vColor` | read as `VAR_COLOR` the door drew darker and more saturated than the principled look (`ogp-3d-renderer` 24): a crown of blossom brightened the day its bloom reached 1 |
| A precocious bloomer's leaves | held at `bloom_leaf_density` from the window's first day | held from budburst until it has flowered | a cherry's leaves fell from 0.54 on 31 March to 0.18 on 1 April |
| Clusters (lilac, rhododendron, hydrangea, pelargonium) | `max(3, n × 2)` at `ref_r × 0.55 × plant_scale` | counted by the crown's surface (`CLUSTER_COVER` 0.15) at 0.6 of the recipe radius, on the crown's shell (an allium's top third) | the two rules retired for crown flowers in round 1 hid every truss in a green crown |
| A precocious tree's flowers | on leaves that are screen-doored down to 6-18 % in bloom | on its outer twigs (`accents.wood_flower_anchors`: points on the wood's outer 30 % in the crown's box) | a cherry's flowers floated a median 26.9 cm from any wood |
| A precocious shrub's flowers (forsythia) | as a tree's | on its crown's shell, each tied to its nearest wood by a LOD0 twig (6 triangles, 0.2 cm, in the flowers part) | its seven stems cannot carry them: along them the flowers read as yellow bottle-brushes |
| Petal normals | bent out from the flower's centre; an open petal's back its own | bent along the petal only; an open petal's back takes its front's normal; a bulb's goblet keeps its outside normal and leans to the sky by a quarter (`GOBLET_SKY_SHARE`) | the bend across a petal drew pinwheels; the backs read dark violet (cherry 2.93 % of a close-up) |
| The crocus | the "purple" petal colour, tip 0.45 to the light | `FlowerTraits.shade` 0.5 and `tip_light` 0.25 | its hue rose with its brightness under the filmic curve - 268 degrees at value 0.62, 280 at 0.98 - not with the light tip: +12 degrees, pale lilac |
| A plant's flowers' triangles | the LOD's budget left over | at most 0.4 of the LOD's budget (`FLOWER_BUDGET_SHARE`); a fruit tree's spur blossom and the forsythia draw wedge petals (`FlowerTraits.wedge`) | built all year, they had grown the food forest's plant triangles by 80 % (354k to 639k at LOD0) |

Measured on the second round's cameras (High, 1600 × 900, LOD0):

- Flower to nearest wood (`float_check.py`, cm, median / p90 / over 30 cm): cherry 26.9 /
  69.8 / 42.6 % before, 3.1 / 7.6 / 0 % after; magnolia 2.9 / 12.2 / 0 %; plum 2.4 / 5.8 /
  0 %; forsythia 2.7 / 5.8 / 0 % counting its twigs.
- Petal hue against the 2D sprite: cherry -3.5, apple -3.6, magnolia -3.6, tulip +3.0, daffodil +3.8, forsythia +5.2, crocus +7.4 (was +12.1), roses and peonies -0.5, asters +5.8 degrees; dark violet
  undersides 0.30 % of the cherry close-up (was 2.93 %), apple 0.20 % (2.66 %).
- The year tour's held pose, changed pixels between consecutive days, with the flowers and
  with them stripped: 31 Mar to 1 Apr 3.79 / 3.56 %, 31 May to 1 Jun 5.15 / 5.14 %, 10 to
  11 Apr (bloom reaching 1) 1.76 / 0.98 %. The flowers add 0.6-0.9 points on an ordinary day;
  the rest is the growth model rebuilding the trees at their new height and, on 1 June, the
  cherries ripening.
- Plant triangles at LOD0 (all plants built, in bloom or not; before #940 / round 1 /
  now): spring garden 347k / 382k / 310k, cottage garden 281k / 423k / 393k, food forest
  354k / 639k / 580k, wildlife garden 466k / 627k / 607k.

## Open questions

- A bulb out of bloom is its leaves on its neck, green all year: the model has no die-back,
  so July shows green straps where real tulips have gone.
- The forsythia's twigs fan out from its seven stems' ends (its leaf lobes sit there): read
  as fine twigs from the garden, as spokes from a 3 m camera.
- The magnolia's goblets read as paper fans from a 3 m camera; the tulip's as cones on
  70 cm stalks (the plan's own height).
- The flower budget share (0.4) keeps a blossom tree at about 500 wedge spurs, not the 3,600
  its crown asks for: enlarged 1.8 times, a cherry in full bloom is still a green crown with
  pink along its branches from 25 m, more than a pink cloud.
- The food forest's plant triangles are still 64 % over their count before #940: its many
  small flowering plants (24 perennials, 12 chives, 10 borage) each stay under the share.
  Built all year, shown only in bloom: memory and upload, not frame time.
- LOD2 trees, climbers and the sunflower can land 0.87-0.89 of their spread on some seeds:
  the same pull onto `REACH_MAX` after the box fit, identical before #940 (LOD2 builds no
  flowers); the bulbs' and alliums' axis pins are the pattern for a fix.
