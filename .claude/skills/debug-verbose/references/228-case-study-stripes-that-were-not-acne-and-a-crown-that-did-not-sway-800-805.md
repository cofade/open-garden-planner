# Case study: stripes that were not shadow acne, and a crown that would not sway (#800, #805)

## Symptom

Two foliage faults from the 3D promo survey, chased together. A camera held on the family
garden's 9.5 m birch about 11 m out showed a crown that did not move (#800). And on High and
Ultra at golden hour, backlit leaves carried fine diagonal stripes 2-4 px apart (#805), which the
survey called shadow acne from the leaves' back-light term passing their own shadow test at
shadow bias 10.

## Wrong theories

1. **"Raise the shadow bias."** The survey's fix for the stripes. Measured on the cherry (1080p,
   High): bias 10 / 14 / 20 / 40 cm left the stripe share at 0.326 / 0.326 / 0.324 / 0.320; the
   still picture's fitted map (#734, about 1 cm texels) read 0.330. A shadow artifact would have
   followed the map.
2. **A crown-motion metric of the whole crop.** The first high-frequency measure rose with every
   bias (more light between leaves meant more edges) and said the stripes got WORSE — it measured
   leaf edges, not stripes. The measure that worked looks only inside flat leaves: pixels with no
   edge in their 5 x 5 neighbourhood, and how far each lies from its 3 x 3 mean.
3. **The wind was "too weak".** It was weak (0.875 cm for every plant), but more amplitude alone
   would have rippled the crown in place: the phase came from each vertex's world x, 13 rad
   across a 12 m crown. And the wood never moved at all.

## Key evidence

One preset table told the stripes' cause: Low (no ambient occlusion) had none, Medium had them as
High did although its shadow bias is 15. Then on one frame: AO off 0.164, AO bias 1 cm 0.184,
shadow bias 40 cm 0.320. For the wind: the masked Lucas-Kanade track of the upper crown (the
plant's own pixels from the frame against the plant drawn as an empty screen door) read 0.03 px
over 4 s at 960 x 540 — and a 60 cm basil 0.32 px, more than the tree.

## Root cause

The stripes: Qt's SSAO takes a camera-facing normal (`ogp-3d-renderer` reference 24), so a flat
micro-leaf seen at a slant occludes itself in bands — #687's flat-ground self-occlusion, on
every leaf. The wind: an amplitude in fixed centimetres and a per-vertex world phase.

## Fix

`look.AO_FLAT_BIAS_CM` (1 cm) under every look's AO bias (contact unchanged; 2 cm halved it).
`plantSway`: one function of the plant's height, the vertex's place and the item's phase, in the
leaf shader, its screen door and a swaying wood shader, stated in numpy (`core/scene3d/wind.py`);
the shadow pass runs it too (a control without it in `QSSG_ENABLE_ORTHO_SHADOW_PASS` left the
ground still). PF-L3D-32, PF-L3D-33; ADR-059 addendum (#800, #805).

## Lesson

Before fixing a "shadow" artifact, check that it changes when the shadow map does — and look at
the preset table: the setting that switches on with the artifact names it. A metric needs a case
whose answer is known; a crop-wide high-pass counted edges until it was confined to where a
correct picture is flat.
