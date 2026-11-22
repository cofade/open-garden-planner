# Case study: a far crown lost 11 % of its spread, and the first fix took its leaves with it (#970)

**Symptom**: at LOD2 (18-45 m) some trees and climbers came out narrower than their
canopy: a jasmine, clematis, wisteria and the climbing-plant category at 0.890 of their
diameter on seed 50, a cucumber and pea at 0.874, a sunflower at 0.881. The truth gate is
±10 %, so these were failures, not a look.

**Theories entertained (wrong)**:
- "The skeleton is too narrow at that distance." No: the wood is inside the crown; the
  foliage box was the failure.
- "The per-species proportions are wrong." No: the same recipe passed at LOD0/1 on every
  seed.
- "The fit's `REACH_MAX` clamp is too tight." It is 1.04 and the truth gate allows ±10 %;
  the clamp is not the defect, the box was.

**What the probe measured** (`forge_plant(sprite, h, r, seed=0..63, lod=LOD2)` and the
horizontal bounding box of all parts): most seeds sat at 1.000, and only a few failed —
seed 50 for every climber, seed 23 for the sunflower. The fit scales the box to the
canopy diameter and then pulls every vertex beyond `REACH_MAX` back onto the circle; at
LOD2 the four farthest leaves sit on diagonals, so the pull takes them in and the box
shrinks. The bulbs had the same defect in #940 and were fixed by pointing their four
outermost *blades* along the plan's axes.

**First fix (wrong)**: pin the four farthest micro-leaves onto the axes *before* the fit.
Spread passed on every seed (1.000), but `test_tall_crowns_retain_foliage_coverage_at_every_lod`
failed: the axis-aligned box was now larger, so the fit scaled **every leaf down** and a
tall LOD2 birch fell from 0.8+ to 0.693 foliage coverage. The pin must not change the
plant's size relative to its canopy.

**Final root cause and fix**: the pin belongs **after** the fit. `assemble.pin_foliage_spread`
turns the fitted foliage's four farthest leaves about the item's axis so each leaf's own
farthest vertex lies on +x, -x, +y or -y. Every leaf keeps its size and colour; the box
now spans 1.040 of the diameter (inside +10 %), and the coverage gate is untouched.
Applied at LOD2 only: at 18 m+ a leaf turned about the trunk is not seen, and LOD0/1 pass
on every seed.

**Lesson**: an axis pin is a *post-transform* operation when the transform itself is
derived from the bounding box. Pinning before the fit feeds the pin back into the scale,
and the metric that notices is the coverage gate, not the spread gate. Also: the
sunflower's foliage mixes curved blades and micro-leaves, so a 4-vertex-a-leaf helper
cannot touch it; its own blade pin stays pre-fit, where the blades are still separate.
