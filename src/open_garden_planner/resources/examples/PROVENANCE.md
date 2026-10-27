# Offline teaching plans and thumbnails

These original layouts, English/German/Spanish annotations and thumbnails were
authored by Open Garden Planner contributors using `scripts/generate_examples.py`
on 26–27 October 2026. All geometry and species snapshots come from production
constructors and the bundled database; there are no imported site plans, downloaded
models, textures, satellite images or reads from the owner's custom plant library.

| Plan | Learning purpose and actual saved content |
| --- | --- |
| `raised-bed.ogp` | 4 × 2 m raised bed: **16 lettuces, 60 carrots, 88 radishes** (164 crops), plus a ten-plant flower/herb border, gravel access, bench, compost and west-side tool shed. A 2027 succession and fictional soil test belong to the main bed. |
| `food-forest.ogp` | 200 m²: **2 fruit trees, 3 currants, 24 strawberries, 12 chives, 10 borage, 60 carrots and 3 supported runner beans** (114 plants). Continuous mulched beds and 80/90 cm harvest paths replace isolated plants in lawn. |
| `balcony.ogp` | 5 × 3 m: **4 basil, 6 parsley, 4 thyme** in three separate troughs, two chairs and a table, a parasol, a north house wall and metal railings on the west/south/east sides. The basil trough has a fictional soil test. |

The three root `.ogp` files are canonical English. `de/` and `es/` hold localized
variants with identical stable IDs, coordinates, botanical dimensions, species keys,
planting dates, links and canonical artwork species strings. Object names, species
common-name snapshots, layer names, guild text, succession display names, soil notes
and tutorial annotations are translated. Domain codes such as `edible_parts` remain
canonical. Root `.meta.json` files provide localized names/descriptions/attributions;
the shared root PNGs show the English plan. No location or soil state is copied into
ordinary user-exported templates; the separately validated bundled-example copy path
retains these explicit demonstration records.

## Site and date conventions

The teaching date is **21 September 2026**; select it in Plan & Sun. It is an
explicit reference date, never today's date or an implicit global clock change.
The balcony also invites a **21 June 2026, 15:00 local time** shadow comparison.

| Plan | Rounded public city reference | Time zone |
| --- | --- | --- |
| Raised bed | Berlin, 52.5200° N, 13.4050° E | `Europe/Berlin` |
| Food forest | Bonn, 50.7374° N, 7.0982° E | `Europe/Berlin` |
| Balcony | Freiburg im Breisgau, 47.9990° N, 7.8421° E | `Europe/Berlin` |

These coordinates are city references, not the address of a surveyed garden or
balcony. Every plan stores **fictional example frost dates** of 15 May / 15 October;
these are not local climate statistics or a forecast. Both soil records are clearly
labelled **fictional teaching samples**, dated 20 May 2026: pH 6.5, Rapitest N1/P2/K3,
loamy texture. They are not observations or a fertilization prescription.

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

Regenerate with `venv/Scripts/python.exe scripts/generate_examples.py`. The script
isolates all settings/user data before application imports, writes full plans via
the production serializer, stabilizes UUIDs and renders the saved content through
`render_scene_region`. Both portrait/landscape letterboxing axes are centered.
Use `QT_QPA_PLATFORM=minimal:enable_fonts` on Windows for real font measurements.

The production 3D engine on this branch predates L4 (#388): table, chairs, bench,
trellis and parasol currently use existing prism/cylinder proxies. These plans keep
their actual object types and dimensions so L4 can improve those shapes independently.
A tutorial annotation is 2D plan content; it is not a new 3D text billboard.
