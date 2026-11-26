## Case study: a grouped bed lost the sun, and cutting the plants out left rings (#1031, 2026-11-26)

Symptom: grouping a ground bed with its plants made the bed bright while every
ungrouped bed stayed shaded. Moving the group into the ground band fixed the
soil but made the grouped plants dark; ungrouping then left a bright circle
around each plant. Grouping the same bed with Lavendel from a planter outside
it brought the bright bed back. Three reports, one feature, and each fix moved
the symptom.

Wrong theories: the first probe compared soil averages in a bare `CanvasView`
with no `SunShadowController`, so both states rendered shadow-free and looked
identical; it "proved" the fill had not changed. The next fix kept a planted
bed group in `GROUND_Z_RANGE` and cut the grouped plants out of the shade with
their `grid_cover_path`. That cover is a circle for a plant but the sprite is
organic, so the hole was bigger than the plant; and the shadow overlay's zoom
picture was rasterised without the cover clip, so the plants were shaded in
the view. After ungrouping the hole persisted as the bright ring. The
Lavendel case (a plant rooted in another planter) was not in the ground band
and lifted the bed above the overlay again.

Key evidence: with the shadow controller enabled, the grouped bed rendered
`122.7 / 88.8 / 40.9` against `91.5 / 75.1 / 47.7` ungrouped, and the group's
z slot was `~0.0006` against the overlay's `-500` while ungrouped ground was
`-750`. After the group was reparented, the bed's own child z was still
`-750`; summing the chain read the group as below the overlay and skipped the
self-paint. The z slot of a group's child is the top-level ancestor's z, never
the sum of the chain.

Root cause: a group paints in ONE z slot, and the sun-study overlays sit
between the ground band and every layer item. No z rule can put a group's
surface below the overlay and its plants above it. The cover cut only hides
pixels; it cannot restore the surface's own shading and it leaves holes that
outlive the group.

Fix: the overlays are registered on the canvas scene, and a ground surface
drawn above them paints them on itself at the end of its own `paint`
(`CanvasScene.paint_ground_overlays`, clipped to the surface's `grid_cover_path`).
The shade, the hours-of-sun fill and the contour layer all use it, and the
surface is invalidated when an overlay changes. Ungrouping returns the exact
pre-group pixels because nothing is cut out any more.

Lesson: when two drawings must interleave but one container can hold only one
z slot, move the paint, not the pixels. A cover clip is a hole, not a layer.
And a group child's z is local — the scene slot is the top-level ancestor's.
Pinned by `tests/integration/test_sun_overlays_on_ground.py` (grouped with its
own plants, with a plant of another planter, group→ungroup identical, hours of
sun on a grouped bed, live-canvas repaint) and PF-CAN-78.

PR #1030 retest: grouping Borage, Pansy and the east perennial bed at 80%
zoom repainted the south-west patch from `89.2 / 66.8 / 50.6` to
`134.6 / 86.6 / 41.0` in the local self-paint implementation. The trace
showed a current cached bitmap drawn at scale `(0.8, 0, 0, -0.8)`. The
exact paint at deeper zoom already put the shadow in the right place. The
bitmap was upright in device pixels and the ground draw flipped it again.
Sharing the device-space blit with the zoom stand-in restored the sampled
colours before, during and after selection. The live family-garden test
pins this case at 80%, where Qt retains a full shadow picture.
