## Case study: every plant in a raised bed had "too little sun" — the sample point was inside the bed (US-F3 x base stacking, found 2026-10-12 while merging v1.30.1 into Phase 17 L1)

**Symptom**: none reported — the feature had shipped the same day with its reference plan
green (a tree and two tomatoes: 0 h north, 16.5 h south). The merge brought it together with
the rule "a plant in a raised bed stands on the bed's soil", and the coordinator asked one
question before any code was touched: does a raised bed shade the tomato standing on it?

**Wrong theories**: none were needed; one was avoided. "The base rule will fix it" — lifting
the plant's own solid by 38 cm changes nothing for the plant: its own solid is left out of its
estimate anyway.

**Key evidence** (a probe test on an export of `origin/master`, the real window, the real
worker, Berlin, 21 June 2026, nothing else on the plan):

```
PROBE | open ground                  | hours=16.5 | record=None                    | badge=False
PROBE | on the 40 cm bed             | hours=0.0  | record=sun_mismatch:too_little | badge=True
PROBE | on the 5 cm bed              | hours=0.0  | record=sun_mismatch:too_little | badge=True
PROBE | in a bed, not linked         | hours=0.0  | record=sun_mismatch:too_little | badge=True
```

**Root cause**: the estimate samples the GROUND cell under the plant's centre and leaves out
the plant's own solid. A raised bed is a solid too, its footprint contains that cell, and a
solid's shadow polygon includes its footprint — the point is "shaded" in every sample of the
day. The reference plan has no bed on it.

**Fix**: the receiver names the soil parent whose solid it stands in
(`SunReceiver.stands_on` ← `ui/canvas/footprints.standing_parent`: linked, visible, a
soil-capable solid, the centre inside — the membership half of the base rule the casters and
the 3D records already used), and that caster is spared for this receiver like its own.
After: 16.5 h on the bed; 10.5 h for a plant on the ground 10 cm north of the bed (the bed
still shades what is beside it); a 3 m wall south of the bed takes exactly the hours it takes
from the same plant with the bed removed. The first cut asked "is the plant LIFTED?" (base >
0) and would have left a plant in a 2 cm edging at 0 hours: a solid can cover the point
without lifting anything — the question is "is the plant in the parent's solid?".

**Lesson**: **when a sample point is "under" an object, list everything else that is under
the object.** And **try a feature first on the plan it is for** — a sun-requirement warning
is for vegetable gardens, and a vegetable garden is raised beds; the reference plan was a
tree. A merge is a second chance to ask the question the feature's own tests did not.

