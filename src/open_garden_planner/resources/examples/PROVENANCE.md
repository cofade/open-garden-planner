# Offline example plans and thumbnails

All three layouts were authored for Open Garden Planner by the project contributors
on 2026-10-26 using `scripts/generate_examples.py`. There is no imported site plan,
satellite imagery, address or real garden location. The generator uses only the
bundled species database and apple-guild definition; no local custom plant library.

| Plan | Content | Thumbnail |
| --- | --- | --- |
| `food-forest.ogp` | Illustrative 200 m² food forest, seven layers, apple guild, 2026–2036 lifetime | `food-forest.png` |
| `raised-bed.ogp` | Illustrative 4 × 2 m raised-bed polyculture and 2027 succession | `raised-bed.png` |
| `balcony.ogp` | Illustrative 5 × 3 m balcony with three linked herb containers | `balcony.png` |

Plans, sidecar metadata and thumbnails: **CC-BY-SA-4.0**, attribution:
Open Garden Planner contributors. Species snapshots derive from the bundled
CC-BY-SA-4.0 database (RHS, Cornell, Kew, USDA/GRIN, UMN, OSU; see
`../data/PROVENANCE.md`); the guild derives from `../data/guilds/`.
Thumbnails are rendered by the app's `render_scene_region` from these layouts,
using its existing plant/object sprites and textures. Their provenance is in
`../plants/PROVENANCE.md`, `../objects/PROVENANCE.md`, and `../textures/PROVENANCE.md`.
License text: https://creativecommons.org/licenses/by-sa/4.0/ .

These are learning layouts, not site-specific horticultural recommendations.
Check climate, mature spacing, light, structural loads and crop dates locally.
Succession entries store calendar dates; importing does not rebase them onto local
frost dates or the current year. Free-form object names remain authored content.

Regenerate with `venv/Scripts/python.exe scripts/generate_examples.py`.
The script isolates settings and user data, assigns stable IDs, writes `.ogp` via
the production serializer and creates PNGs through the shared scene renderer.
Use `QT_QPA_PLATFORM=minimal:enable_fonts` on Windows to render real fonts.
