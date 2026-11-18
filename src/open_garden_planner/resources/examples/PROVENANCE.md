# Offline teaching plans and thumbnails

These original layouts, English/German/Spanish annotations and thumbnails were
authored by Open Garden Planner contributors using `scripts/generate_examples.py`
on 26–27 October 2026; the harvest histories, the showcase moments and the wider
showcase paths were added, and all thumbnails rendered again, on 10 November 2026 (#795). All geometry and species snapshots come from production
constructors and the bundled database; there are no imported site plans, downloaded
models, textures, satellite images or reads from the owner's custom plant library.

| Plan | Learning purpose and actual saved content |
| --- | --- |
| `raised-bed.ogp` | 4 × 2 m raised bed: **16 lettuces, 60 carrots, 88 radishes** (164 crops), plus a ten-plant flower/herb border, gravel access, bench, compost and west-side tool shed. A 2027 succession and fictional soil test belong to the main bed. |
| `food-forest.ogp` | 600 m² in two halves. The dense half, 20 × 10 m as first shipped: **2 fruit trees, 3 currants, 24 strawberries, 12 chives, 10 borage, 60 carrots and 3 supported runner beans** (114 plants) in continuous mulched beds with 80/90 cm harvest paths. The open half, added with #940: an orchard meadow (two lawns with the wildflower fill) with a pear, an apple and a plum as far apart as their grown crowns need, and a young walnut with six asters as the walnut-tolerant guild (10 plants). No item of the first half changed its id. |
| `balcony.ogp` | 5 × 3 m: **4 basil, 6 parsley, 4 thyme** in three separate troughs, two chairs and a table, a parasol, a north house wall and metal railings on the west/south/east sides. The basil trough has a fictional soil test. |
| `family-garden.ogp` | 24 × 16 m showcase of the 3D view, not a teaching plan: **61 plants** among a house with its ridge, greenhouse, shed, terrace with pergola, lawn with pond and trampoline, three raised beds, trees, hedge, wall and fences. It is the plan of every Beauty Board (`tests/fixtures/plans/bench_small.ogp`, added 3 November 2026, #390), built by the same `scripts/make_bench_plans.py` and with the same item ids, so its procedural plants have the same shapes; a test pins that the two do not drift. Its two polyline paths are as wide as a path one walks on (gravel path 80 cm, stepping stones 50 cm, #795); the fixture keeps the 8 and 6 cm its pinned numbers were measured with. With the walk 50 cm wide, what stood in it was moved out of it: the bird bath to (620, 450) and, in the perennial border, the geranium, the chrysanthemum and the lily to x 612, 746 and 811; the path's points and every other object stand where the fixture has them. What takes a year or more to mature is planted on 1 March instead of the fixture's 15 April, so that a time-lapse from March shows it leafing out. The cherry tree alone is older: planted on 5 November 2022 as a 1.5 m nursery tree, because it has a harvest in June 2026; on the reference date its crown is the 3.7 m the plan was drawn with. It has no soil test and no tutorial annotation. |
| `allotment.ogp` | 15 × 20 m allotment plot: **216 plants** in rows of potatoes, onions, carrots, garlic, cabbage, kale, bush beans, beets, strawberries, rhubarb and tomatoes, a salad bed with a 2027 succession, a pea support, a herb bed, a Three Sisters mound as a guild, berries and a plum tree. Summer house with a mono-pitch roof, greenhouse, cold frames, compost, water tap. The potato bed has a fictional soil sample. |
| `cottage-garden.ogp` | 12 × 12 m formal four-square garden: **123 plants** in four box-edged beds around a rose roundel, inside a picket fence with gravel cross paths. Two guide lines carry the axes; three distance constraints hold the measures between the box edgings and to the bench. |
| `terraced-house-garden.ogp` | 6 × 18 m between two hedges, with true north turned 35 degrees: **23 plants**, a house with a flat-roofed extension, a timber deck, a lawn with sandbox and swing, an apple tree, two borders, a raised bed and a shed with a mono-pitch roof. A second stored tour holds the camera while one day's shadows pass. |
| `roof-terrace.ogp` | 10 × 8 m timber deck on a city roof: **34 plants**, every one in a vessel: four herb and strawberry troughs, an olive and a fig in tubs, three wall planters, a raised bed with a fictional soil sample, two planter pots and a climber on a trellis. Picnic table, loungers, parasol, a string of lights and two lanterns. |
| `spring-garden.ogp` | 14 × 10 m on an April day: **191 plants**, of them 64 crocus, 58 daffodils and 44 tulips planted the autumn before, with magnolia, cherry, plum, apple, forsythia, lilac and rhododendron. The west tulip bed has a fictional soil sample. A second stored tour holds the camera while the year 2026 passes. |
| `wildlife-garden.ogp` | 18 × 14 m flower meadow around a pond: **118 plants**: willow, oak, birch, two elders, viburnum, barberry and holly, six irises on the bank, and drifts of pot marigold, cosmos, flax, chamomile, borage, coneflower, valerian, chicory and hyssop. A boardwalk and a deck at the water, a hammock, trodden paths. The meadow is a lawn with the wildflower fill. |
| `mediterranean-courtyard.ogp` | 12 × 10 m walled patio: **23 plants**: an olive, a fig and a windmill palm in gravel beds, a lemon and an orange in tubs, two grape vines on the pergola, lavender, rosemary, sage and thyme along the walls, pelargoniums in four pots. A house with a hip roof, a plunge pool in a terracotta surround, two loungers, a string of lights and four lanterns. |
| `modern-garden.ogp` | 15 × 12 m: **22 plants**: a red Japanese maple, five box spheres, miscanthus and lavender in three corten beds, a bamboo screen. A flat-roofed bungalow, a slate terrace with hot tub, loungers and fire pit, a reflecting pool, ten lanterns and a string of lights. Four guide lines carry the grid. A second stored tour runs the orbit from 19:15 to 21:00 on the computer's clock. No harvest history: nothing here is eaten. |
| `japanese-garden.ogp` | 12 × 10 m: **30 plants**: two red Japanese maples, a birch, two pines, eight bamboos, three rhododendrons, four box, three miscanthus, six irises and a juniper. A raked sand court with two moss islands and three rocks, a pond with a plank bridge, a tea house with a hip roof and a timber veranda, slate, pebbles and stepping stones, three lanterns. No harvest history. |

The root `.ogp` files are canonical English. `de/` and `es/` hold localized
variants with identical stable IDs, coordinates, botanical dimensions, species keys,
planting dates, links and canonical artwork species strings. Object names, species
common-name snapshots, layer names, guild text, succession display names, soil notes
and tutorial annotations are translated. Domain codes such as `edible_parts` remain
canonical. Root `.meta.json` files provide localized names/descriptions/attributions;
there is one PNG per plan, rendered from the English plan at its showcase moment with
the hint layer hidden, so a thumbnail carries no words in any language (#940). No location
or soil state is copied into
ordinary user-exported templates; the separately validated bundled-example copy path
retains these explicit demonstration records.

## Site and date conventions

Every example opens on a day and in a light of its own (#795, #940): its sidecar
names `showcase_date` and `showcase_utc_time`, the application moves its session clock
there while the example is open and puts the user's own reading back with the next
document. Nothing is saved in settings or in a plan. The three teaching plans keep
**21 September 2026**, the family garden **21 June 2026**, each at 11:00 UTC. The
balcony also invites a **21 June 2026, 15:00 local time** shadow comparison.

All thirteen places lie in the Central European time zone, because the session clock
and the time-of-day tours read the computer's zone, not the plan's (#945): on a
computer set to it, the local times below are what the toolbar shows.

| Plan | Rounded public city reference | Opens on (UTC; local) | Sun at that moment | Frost dates stored (last / first) |
| --- | --- | --- | --- | --- |
| Family garden | Berlin, 52.5200° N, 13.4050° E | 21 June 2026, 11:00; 13:00 | 61° up, south | 9 April / 31 October |
| Mediterranean courtyard | Valencia, 39.4699° N, 0.3763° W | 21 June 2026, 18:25; 20:25 | 11° up, west-north-west | 1 February / 20 December |
| Wildlife garden | Lüneburg, 53.2464° N, 10.4115° E | 14 June 2026, 06:35; 08:35 | 30° up, east | 5 May / 15 October |
| Japanese garden | Düsseldorf, 51.2277° N, 6.7735° E | 20 October 2026, 13:50; 15:50 | 20° up, south-west | 10 April / 5 November |
| Modern garden | Munich, 48.1351° N, 11.5820° E | 15 August 2026, 17:40; 19:40 | 7° up, west | 1 May / 15 October |
| Cottage garden | Bamberg, 49.8988° N, 10.9028° E | 20 June 2026, 09:00; 11:00 | 52° up, south-east | 5 May / 12 October |
| Spring garden | Heidelberg, 49.3988° N, 8.6724° E | 18 April 2026, 11:00; 13:00 | 51° up, south | 8 April / 1 November |
| Terraced-house garden | Cologne, 50.9375° N, 6.9603° E | 21 June 2026, 16:15; 18:15 | 30° up, west | 10 April / 5 November |
| Allotment | Leipzig, 51.3397° N, 12.3731° E | 18 July 2026, 07:00; 09:00 | 32° up, east | 25 April / 20 October |
| Food forest | Bonn, 50.7374° N, 7.0982° E | 21 September 2026, 11:00; 13:00 | 40° up, south | 15 May / 15 October |
| Roof terrace | Vienna, 48.2082° N, 16.3738° E | 12 July 2026, 08:30; 10:30 | 50° up, south-east | 15 April / 25 October |
| Raised bed | Berlin, 52.5200° N, 13.4050° E | 21 September 2026, 11:00; 13:00 | 38° up, south | 15 May / 15 October |
| Balcony | Freiburg im Breisgau, 47.9990° N, 7.8421° E | 21 September 2026, 11:00; 13:00 | 42° up, south | 15 May / 15 October |

The terraced-house garden's true north is turned by 35 degrees; every other plan has
north at the top. Each plan stores a camera tour named "Garden orbit": one turn around
the plan that starts with the showcase sun behind the camera (the allotment starts over
its see-through front fence instead) and looks down at a pitch chosen per plan, so
that a wall or a hedge does not hide the garden. Three plans store a second tour: the
modern garden's orbit from 19:15 to 21:00, the spring garden's held camera through
the year 2026, the terraced-house garden's held camera from 06:00 to 21:00. A bundled
example's 3D view opens on the side its orbit starts from.

These coordinates are city references, not the address of a surveyed garden or
balcony. The frost dates in the table are **fictional example dates**, chosen to be
plausible for the place and stored so that calendars and bloom have something to work
with; the family garden has the bench plan's. None of these are local climate
statistics or a forecast. Both soil records are clearly
labelled **fictional teaching samples**, dated 20 May 2026: pH 6.5, Rapitest N1/P2/K3,
loamy texture. They are not observations or a fertilization prescription.

## Harvest histories (fictional)

Every example carries a small **fictional harvest history** so that the Harvest tab,
a plant's harvest log and the report's harvest page show content (#795). No quantity
is a measurement or a yield claim. Every record's note says so ("Fictional example
entry; not a real harvest record.", translated in `de/` and `es/`).

| Plan | Species with records (entries) | Years |
| --- | --- | --- |
| Family garden | lettuce (2), spinach (2), chives (2), parsley (1), basil (1), cherry (2) | 2026, up to 19 June |
| Food forest | apple (3), peach (3), currant (3), strawberry (4), runner bean (3), chives (3), carrot (1) | 2025 and 2026, up to 18 September |
| Raised bed | lettuce (2), carrot (2), chives (5), pot marigold (2) | 2025 (chives) and 2026, up to 19 September |
| Balcony | basil (4), thyme (4), parsley (1) | 2025 (thyme) and 2026, up to 14 September |
| Allotment | strawberry (3), garden pea (3), potato (1), lettuce (2), rhubarb (3), raspberry (3), currant (2), plum (1) | 2025 and 2026, up to 15 July |
| Cottage garden | lettuce (2), strawberry (3), chives (3), currant (2), sage (2) | 2024 to 2026, up to 17 June |
| Terraced-house garden | lettuce (2), strawberry (3), sage (1) | 2025 and 2026, up to 18 June |
| Roof terrace | strawberry (3), basil (2), lettuce (2), thyme (2) | 2025 and 2026, up to 5 July |
| Spring garden | chives (3), rhubarb (2), thyme (2) | 2024 to 2026, up to 11 April |
| Wildlife garden | chamomile (2), borage (1), pot marigold (1) | 2025 and 2026, up to 10 June |
| Mediterranean courtyard | rosemary (2), sage (1), thyme (2) | 2025 and 2026, up to 13 June |
| Modern garden, Japanese garden | none: nothing in them is eaten | |

The records of a species sit on one plant of it (the one nearest the plan's
south-west corner), as a harvest logged from that plant's context menu would. No date
is earlier than that plant's planting date or later than the plan's reference date.
A tree's first record is at least three years after its planting date and a shrub's
at least one, and a year's total stays within 7 kg per year since planting (the
content tests hold both): the family garden's cherry gave 6.5 kg in its fourth
summer, the food forest's apple 60 kg in its eleventh.
The raised bed stays fully planted on 21 September: what was taken there are outer
leaves and thinnings. Units are the dialog's own (`kg`, `g`, `pcs`, `bunch`). No
journal note is linked, and an example writes nothing into the seed inventory, which
is the user's own store outside every plan.

The raised-bed crops are established at the reference date: lettuce planted
**1 August 2026** (51 days), carrots sown **15 June 2026** (98 days), radishes sown
**20 August 2026** (32 days). The radish area illustrates a fully occupied target
layout; its annotation recommends small successive sowings rather than harvesting
all 88 roots at once. Its separate **2027** succession stores radish
15 March–15 May, bush bean 1 June–31 August, lettuce 1 September–31 October. It is a
calendar demonstration, not an automatically frost-adjusted recommendation.

The apple was planted **15 November 2014**, the peach **15 March 2016**, currants
**10 November 2019**. Nursery-size growth anchors (height/spread) are respectively
120/70 cm, 140/80 cm and 40/30 cm. These are illustrative sizes **at planting**, the
existing growth model's anchor convention. The two trees and shrubs have reached
their unchanged bundled mature sizes by September 2026: apple 8 m high / 6 m spread,
peach 6 m / 5 m, currant 1.8 m / 1.5 m. No species maxima were changed for appearance.
Strawberries date from April 2024, chives April 2021, thyme May 2023; basil and
runner beans from 20 May 2026, parsley 20 August 2026. The forest's sunny root strip
contains June-sown carrots, not last year's garlic left unharvested into autumn.

### Sizes in the plans added with #940

The application grows a plant from its planting date and its size at planting. In the
nine plans added with #940 an established tree, shrub or perennial therefore carries a
recent planting date (1 March 2026, or 25 October 2025 where it must stand through
the winter) together with the size it is meant to have on the showcase day, instead of
a nursery size years back that the growth model would turn into a full-grown tree in a
tub. Sown annuals carry their sowing date and a seedling's size. These dates describe
how the plan is drawn, not a planting recommendation. The food forest's walnut is a
young tree planted on 5 November 2025; its six asters stand at its canopy edge.

A long hedge is drawn as runs of at most 8 m, which is how it keeps its leaves in the
3D view; the runs carry the same name.

## Placement brief and sources

These are illustrative designs, not validated companion-benefit or yield claims.
The sources informed original spacing and grouping; no third-party plan or prose
was copied. Consult cultivar, climate, shade, soil, access and balcony load locally.

* **Raised bed:** lettuce 30 × 30 cm; carrots 10 × 25 cm; radishes 10 × 13 cm.
  RHS [vegetable crop planner](https://schoolgardening.rhs.org.uk/resources/info-sheet/vegetable-crop-planner.aspx)
  and [lettuce guide](https://www.rhs.org.uk/vegetables/lettuce/grow-your-own)
  support crop-dependent spacing; the chosen radish spacing exceeds the minimum
  2.5 cm in the [RHS radish guide](https://www.rhs.org.uk/vegetables/radishes/grow-your-own).
  These are full-size plants, not a depiction of every seed in a drill.
* **Actual soil clearance:** the production raised-bed SVG is 120 × 80 artwork
  units, with the soil rectangle at `(11,11,98,58)`. On a 400 × 200 cm item this is
  a **36.67 cm x inset and 27.5 cm y inset**. Every crop's complete mature circular
  footprint fits that painted opening. The 3D frame is 5 cm; respecting the stricter
  2D opening also clears it. Soil surface is 43 cm for the 45 cm bed; trough soil is
  their stored fill height of 35 cm.
* **Guild composition:** [NC State Extension's permaculture design appendix](https://content.ces.ncsu.edu/extension-gardener-handbook/appendix-g-permaculture-design)
  describes intentional, functional groups around trees. The
  [RHS school-tree guidance](https://schoolgardening.rhs.org.uk/resources/info-sheet/trees-in-school-grounds.aspx)
  motivates clear, ungrassed trunk zones; nothing is piled against these trunks.
  Repeated groups occupy the sunny southern canopy edge and the separate edible
  border, rather than isolated strawberry or potato specimens in grass. Strawberry
  centres are 60 cm apart, respecting the bundled 60 cm spread. This is deliberately
  roomier than the intensive day-neutral system described by
  [University of New Hampshire Extension](https://extension.unh.edu/resource/growing-fruit-strawberries-fact-sheet).
  Borage uses 70 cm centres, chives 35 cm; the root strip uses 20 × 35 cm.
* **Honest membership:** only the apple plus its 16 nearby strawberries and four
  near-tree borage plants share its guild ID (all centres within canopy radius
  +75 cm). The peach-side plants, border borage and supported beans remain separate.
  The builtin guild template's nitrogen-fixer role is intentionally **unfilled**;
  the tutorial asks the user to inspect that missing role. This is not a claim
  that planting a legume guarantees nitrogen transfer to the tree.
* **Containers:** 40 cm basil/thyme and 30 cm parsley horizontal spacing, with
  40 cm between the two rows, respect the unchanged bundled mature footprints.
  Basil/parsley use separate moist troughs; thyme has its own free-draining one.
  [RHS container-herb guidance](https://www.rhs.org.uk/herbs/containers) and the
  [RHS Mediterranean-herb container example](https://www.rhs.org.uk/advice/grow-your-own/containers/veg-on-walls/june-edible-container-idea?lnk=1)
  inform the separate water regimes. The troughs are 110 × 90 × 35 cm, not solitary
  supermarket herbs placed in otherwise empty containers.

The west shed's shade exercise is numeric: on 21 September 2026 at **17:30 CEST**,
Berlin sun elevation is 13.8133°, azimuth 252.2407°. Its analytical shadow at the
raised soil plane (43 cm) covers **24,311 cm² / 51.33%** of the painted soil opening.
The example thereby exposes a real light trade-off that Hours of Sun can inspect.

## Licence and regeneration

Plans, sidecar metadata, localized prose and thumbnails: **CC-BY-SA-4.0**;
attribution: Open Garden Planner contributors. Species snapshots derive from the
bundled CC-BY-SA-4.0 database (see `../data/PROVENANCE.md`); the apple-guild template
snapshot derives from `../data/guilds/apple.json`. Thumbnails use the existing
procedural sprite/texture sets documented in `../plants/PROVENANCE.md`,
`../objects/PROVENANCE.md`, and `../textures/PROVENANCE.md`.
[Licence text](https://creativecommons.org/licenses/by-sa/4.0/).

Regenerate with `venv/Scripts/python.exe scripts/generate_examples.py`
(`--check` compares the shipped plans and sidecars with the generator's output and
writes nothing; `tests/integration/test_example_generation.py` does the same in the
suite, so these files are never edited by hand). The script
isolates all settings/user data before application imports, writes full plans via
the production serializer, stabilizes UUIDs and renders the saved content through
`render_scene_region`. Both portrait/landscape letterboxing axes are centered.
Use `QT_QPA_PLATFORM=minimal:enable_fonts` on Windows for real font measurements.

The production 3D engine on this branch predates L4 (#388): table, chairs, bench,
trellis and parasol currently use existing prism/cylinder proxies. These plans keep
their actual object types and dimensions so L4 can improve those shapes independently.
A tutorial annotation is 2D plan content; it is not a new 3D text billboard.
