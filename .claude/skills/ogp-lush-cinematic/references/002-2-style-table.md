## 2. Style table

| Layer | Rule |
|---|---|
| Light | One key light = the real sun. Warm when low, neutral-white when high. The sky is the fill (image-based lighting) and must **not** out-shine the sun — the first spike renders read flat and blue precisely because the probe dominated. |
| Colour | Plants and objects take colours only from the 2D tables (sprite `PALETTES`/`FRUITS`/`FLOWERS`, object `MATERIALS`). Seasonal colour is a function of those palettes, never a new literal. Albedo stays inside sRGB ~40–240 (no pure black/white surfaces). |
| Form | Chunky, readable silhouettes; bevels on built things; vegetation slightly fuller than nature; real-world dimensions; nothing floats, nothing is cloned. |
| Foliage | Geometric micro-leaves (2 triangles each), **no alpha cards** (aliasing + sort + shadow-pass problems). Normals spherized toward the crown centre (0.55–0.75) so a crown shades like one soft volume. Leaf count follows crown surface area (coverage ≈ 1.6), not a magic number — inside the plant's triangle budget (tree 25,000, bounded by construction: `meshes.TREE_TRIANGLE_BUDGET`; any other plant has a 6,000 target it meets on the bench, max 3,252, but is NOT bounded by — builders dispatch by species archetype, so a tree-archetype species on a non-tree item can reach the tree's count; L1.7 budgets by archetype): wood and fruit/flowers first, then leaves; a crown over it gets fewer, LARGER leaves at the same coverage (conifers: ≤ 12,000 sprays, same spray area), never a sparser crown. A canopy tree is bounded **by construction** (`meshes.TREE_NODES_MAX`): branch segments sized from the crown's larger dimension (max(height, spread) / 28), at most 1,000 skeleton nodes (wood ≤ 13,986), at most 140 fruit or flowers (fruit ≤ 140 × 32 = 4,480; flowers with 8-triangle octahedron centres 140 × 20 = 2,800) and the floor of 2 leaves per twig (≤ 4,000) — 22,466 ≤ 25,000. Gate: every plant of both bench plans on both board dates, and wide crowns up to 4 × wider than tall. |
| Atmosphere | Filmic/ACES tonemapping, gentle glow, depth fog whose colour equals the sky horizon (hides the meadow/sky seam) at **every** preset — low included, or the meadow meets the sky in a one-row cliff — and which BEGINS BEYOND THE PLAN the camera frames, up to 380 m away (`look.fog_depth_cm`: 1.5× / 6× the camera's distance, floors 26 m / 160 m, full by 760 m, so from 380 m to the camera's 600 m limit it begins at 570 m; L4 owner pass: a fixed 26 m drowned a framed plan) — SSAO from Medium up. **No sharpening** (`sharpnessAmount` 0): 0.08 overshot every thin lit edge into near-black dots; every board row records them (`isolated_dark_px`, §5). DOF/vignette only in photo mode. |
| Motion | Wind sways grass and crowns via shader values (uv.x = sway weight, uv.y = phase); animation only while the 3D view is visible; reduced-motion setting stops it. |
| Analysis (L2, ADR-063) | The analysis overlays are the 2D model's answer, not a look: the shadow drape MULTIPLIES the frame by `drape.SHADE_MULTIPLIER` (0.60, 0.62, 0.95; tinted like the canvas's shadow colour) — measured 0.74–0.83 of the lawn's luma from noon to night, never lighter (PF-L3D-07) — the hours-of-sun drape blends the heatmap's ramp over the ground, both unlit and 1.5 cm above it, under everything that stands on it; overlay colours are divided by the exposure, and the arcs are built in pre-compensated colours (`ARC_ENGINE_RGBA`) that read the legend's hue (plan date amber, 21 June orange-red, 21 December blue, 20 March green) within 2.7° in five moods; the plan date's arc is drawn last and 1.5 × thicker; the compass off-white with a red north. X-ray and Cutaway are SCREEN DOORS (25 % of the pixels by an ordered dither; a cut roof none), never blends: the parts keep their shadows (PF-L3D-08); the walls of a roofless house show their inner faces. Judge overlays in EVERY mood, night included — the first gates measured only noon — for READABILITY (an arc against the sky, the drape's edge on lawn and path, the compass letters) and truth (§1: the drape must match the 2D overlay — an engine shadow that disagrees with it is expected, the drape is the answer). A translucent overlay that BRIGHTENS what it covers is a P0 (the alpha bug PF-L3D-06, or an unlit colour through the exposure PF-L3D-07); so is a fade or cut that removes a shadow. Owner questions open: the stipple vs a smooth ghost, whether a selected bed's own plants fade, a flat pre-composited vs a translucent hours-of-sun map. |

**Plant v0 (Package L1.7) — what the production plants are, and are not.** The plants the
pipeline builds (`core/scene3d/builders/plants.py`, §8.29.7) are not the spike's: one cheap
silhouette per 2D sprite archetype — soft volumes and a shell of large geometric leaves, at most
2,000 triangles a plant, bounded per archetype and by construction (measured: canopy 1,904 …
flower 316). Judge them as v0:

- Archetype and palette come from the recipe of the sprite the plan shows
  (`core/plant_art/recipes.py`, resolved by `core/plant_art/resolve.py` — the 2D rule, on the 2D
  renderer's own inputs: the item's type, its own species string as it is, its category). A plant
  whose 3D shape or green contradicts its sprite is a finding; a plant whose *sprite* is odd
  (Lemon Balm drawn as a lemon tree) is a 2D finding that 3D reproduces faithfully. A plant
  given a species from the plant database now shows THAT species' sprite (#445) - a plant that
  still shows its old one is the 2D defect, not a 3D one.
- **No fruit, no flowers, no flower heads, by decision** — the season gates need the plan's frost
  dates, which a record does not carry (Package L3). Their absence against the L0 board is not a
  regression. Crowns are never bare.
- One bark for every species (the 2D BARK texture's mean, `#5d432d`), no species crown forms, no
  support under a climber. Species-accurate plants are Package L3.
- **Unknown height (#557):** the production snapshot keeps `height_cm=None` and carries
  `params["estimated_height_cm"]` separately. `core/plant_height_estimate.py` owns the
  illustrative category table: trees **400 cm**, shrubs/climbers **150 cm**,
  flowers/perennials/grasses/ground cover **60 cm**, vegetables/herbs **50 cm**.
  Category takes precedence over the item kind. The existing sprite recipe supplies the
  matching form and palette at that estimated height; known species, measured/current and
  explicit heights retain their existing precedence and suppress the estimate. The info card
  labels estimates. They drive decorative 3D geometry **and its shadows**, while analytical
  2D shadows and Hours of Sun continue to see an unknown height and exclude that caster.
  Viewing 3D must preserve species/instance metadata, saved objects and undo depth.
  `placeholder_parts` remains a low neutral dome, at most 25 cm, without a shadow, only for a
  height-less record with no usable fallback. The former rule requiring a grey marker for
  every unknown-height gallery/tool plant is superseded by issue #557.
- What the builder GUARANTEES (by construction — the last steps of its fit; tested on hostile
  input to the fit itself): top = height and widest span = canopy diameter exactly, base on the
  ground, and no FOLIAGE vertex further than 1.09 canopy radii from the axis (`REACH_MAX`; the
  gate is 1.10). That this bounds the whole plant rests on an invariant of the trunk builders —
  foliage is the outermost part: wood is built within 0.32 canopy radii of the axis and is never
  moved by the fit (a new archetype with wood must keep it; the tests hold wood inside 0.5). What is MEASURED (re-measure with `scripts/measure_plant_art_3d.py`, command `truth`;
  do not trust; a sample of 63,099 plants — every recipe × every proportion step × three ids):
  the plant is BUILT to those numbers, not scaled into them — the builder's own top is the
  height before the fit touches it (`fit_report`: 1.0000 in every plant), nothing is pressed
  onto the ground, at most 2.2 % of the foliage vertices are pulled back onto the canopy circle —
  and the foliage's mass reaches the top (95 % / 99 % area quantiles per archetype; the smallest
  measured: a mound 0.719 / 0.884 of its height, a rosette 0.605 / 0.719, a hedge 0.877 / 0.938). No
  foliage triangle lies flat on the ground; at least six vertices touch it. Never quote a
  measured number as a guarantee: "at most 1.092 radii" stood in a requirement until one id in
  300,000 read 1.1006. Foliage hue within 10° of the rendered sprite (measured ≤ 5.0°) — of the
  UNTINTED sprite: the canvas lays the item's fill colour over a plant's sprite at 60 / 255, 3D
  does not (an open owner question: should a recoloured plant be tinted in 3D?).
  Two ids: over 30 ids a recipe the most alike pair is 97.5 % alike (two hedge sections), 99 %
  of all pairs are below 95.2 %; a clipped hedge and a flat ground cover repeat by nature.
- A bounding box that is exact after a fit says nothing about the plant. When judging a plant's
  size on a board, look at where its MASS ends, not where its highest leaf tip is: the first
  version built a squash 1.6 times too tall and squashed it back — exact box, body in the lower
  two thirds.
- A date scrub scales remembered shapes (a daily tick of 320 plants: 15 ms on a busy box, 342 ms
  without the cache); the form of a plant changes only when its proportion crosses a 5 % step, by
  at most 2.5 % of stretch in one axis. At a step a plant stays itself — measured, its side
  silhouette in the unit box is 0.99–1.00 the one before (another id: 0.71–0.92); the visible
  steps on a slow scrub are single leaves turning to stay inside the canopy circle (0.94) and a
  conifer gaining a whorl (0.87: the stack is re-divided). Judge those two on a board.
- The #557 proof exercises representative tree, shrub, perennial and vegetable estimates through
  real species assignment → snapshot → production registry → Qt Quick 3D in noon and golden
  hour, with a matching base-commit board. Its review evidence is scoped to dimension fallback
  and spread propagation; it does not replace the full archetype Beauty Board.

