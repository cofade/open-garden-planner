# Flowers in bloom — counted by the crown, double-sided, above a bulb's leaves (#940)

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

## The values

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

## Measured (High, 1600 × 900, each plan at its showcase moment, LOD0)

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

## Open questions

- A bulb keeps its leaves and bare scapes all year: the model has no die-back, so July
  shows green straps and thin stalks where real tulips have gone.
- The magnolia's goblets read as paper fans from a 3 m camera; the tulip's as cones on
  70 cm stalks (the plan's own height).
- A blossom tree's flowers are budget-bound at LOD0 (the 529 cm cherry: 813 spur clusters
  at 6.3 cm instead of 3,608 at 3.5 cm — the flower part takes the whole remaining budget,
  so the tree reaches 25,000 triangles in bloom season and out of it).
- The Mediterranean courtyard's vine never ripens since #940: its record's harvest window
  after a 1 February frost (June-July) and its fruit months (September-October) never meet.
  The frost-anchored window does not fit a Mediterranean vine; the data, not the look, is
  the open question.
