## Foliage in motion, the leaves' stripes and the autumn crown — the values (#800, #805)

Decisions and evidence: ADR-059 addendum "the wind that shows, and the leaves' stripes"; the
engine facts `ogp-3d-renderer` reference 028; lessons PF-L3D-32, PF-L3D-33. Measured on the
family garden (RTX 4070, Direct3D 11) through the tour's capture path.

**The wind's values** (`core/scene3d/wind.py`, one text in the three shaders):

| Value | Setting | Why |
|---|---|---|
| Sway at the top | 0.5 % of the plant's height × the look's strength / 2.5 (clear 2.5, partly cloudy 3.0, overcast 3.5, rain 5.0, snow 1.5) | the issue's rule; calm stays calm, a windier weather sways more |
| Shape | `(y/h)²`, a lean of 0.35 of the swing downwind (from 250°, the particles' westerly) | a cantilever: the foot is where the plan puts it |
| Swing | `1.2 Hz / √(h / 1 m)` in 0.25–2.5 Hz, ±10 % by the item's phase; across the wind 0.4 × at 0.71 of it | a 9.5 m birch 0.39 Hz (2.6 s), a 1.7 m shrub ~0.9 Hz, a 60 cm herb ~1.5 Hz |
| Branches | 0.45 × at the outer top, `reach/r × y/h`, a field smooth in space at 1.65–2.15 × the swing | outer twigs move more than the trunk; a twig and its leaves move together |
| Flutter | 0.25 × along the leaf normal, `max(2 Hz, 1.6 × swing)` × 0.85–1.15 per leaf | at most 5.1 Hz: six frames a cycle at 30 fps, never an alternation |
| Gust | 0.65 ± 0.35 at 0.07 Hz, travelling downwind (0.0021 rad/cm) | neighbours out of step; a calm-and-gust rhythm |

What it reads as (1080p-equivalent px, the upper crown's half swing): the birch at 11 m 1.4–1.7
px (its top leaves several px; 0.06 before), the lilac at 5 m 1.6 px, a basil at 3 m 0.8 px.
**Judge the motion in a clip, never on a contact sheet**: a sheet of every 5th frame shows next
to nothing at these amplitudes (the held shot and the orbit of the handoff are the evidence).

**The leaves' stripes are ambient occlusion.** Diagonal bands across flat micro-leaves from
Medium up are Qt's SSAO occluding each leaf with a camera-facing normal — not shadow acne (the
shadow bias and the map's fit leave them). Every look has an AO bias of at least 1 cm
(`look.AO_FLAT_BIAS_CM`). Judge them on a 3× nearest-neighbour zoom of a backlit crown at golden
hour against the same frame with AO off; the measure is the share of pixels inside flat leaves
more than 1.5 levels off their 3 × 3 mean (cherry, High, 1080p: 0.326 before, 0.184 after, 0.164
without AO). The floor also lifts open flat ground on every clear frame a little (its
self-occlusion 16.9 → 11.4 levels at High) and a backlit crown by about 8 levels.

**Leaf size (open for the owner, kept as built).** At L0 the owner kept small-leaved crowns as
they are. What makes the LOD0 leaves large is the coverage rule meeting the crown's area with few
leaves: the 9.5 m birch has 1,857 leaves of 42 cm median length (3,714 of its 25,000 triangles),
the cherry 2,507 at 31 cm. Options: keep; halve the length at LOD0 (about 4 × the leaf
triangles, still inside the budget, more vertex work in every pass); lobed leaf meshes near the
camera (the bigger step). Alpha cards stay ruled out. No leaf is a stray: nearest neighbour over
two leaf lengths 0 of 1,857–2,838, at most 0.2 % touch the reach clamp.

**The muddy autumn crown (measured, not changed).** The season tint is ONE linear multiplier per
channel for every leaf of a plant (`phenology._palette_autumn_multiplier`: the autumn palette's
mean over the summer palette's, clamped R ≤ 2.1, G ≥ 0.35, B ≥ 0.25). A green palette's dark
and light leaves would need very different red gains (fresh → autumn: about 13 × for the dark
anchor, 1.7 × for the light one), so the clamp leaves the dark leaves olive and the light ones
salmon: the pear (fresh → redleaf) comes out at hue 24°, saturation 0.33 where its autumn palette
reads 354° and 0.52 — the survey's muddy centre crown (luma 56, hue 22°, saturation 0.40). Not
the light, not the crown's own colours. Removing the clamp fixes the hue (349°) but overruns the
albedo ceiling on the light leaves; no single multiplier stays inside 40–240 and on the palette.
The fix is a mapping of each leaf's tone onto the autumn palette's ramp (two anchors per part),
which the falling leaves (crown colours × the season tint, #687) must take the same way.
