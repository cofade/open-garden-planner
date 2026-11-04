## Case study: a 19 km styled path painted 475 001 elements per frame (#450)

**Symptom.** Repainting a canvas holding a styled path with two points 19 km
apart generated 475 001 stones/dots, and adding 2 000 items one by one took 45 s;
the same adds inside `suspend_z_refresh` took 3.9 s.
**Wrong theories.** The device cache would amortise the path paint (it does not:
the first cached paint still builds the whole item); the cost was the sorted
vertex walk alone (the z re-derivation per add was the second, independent half).
**Evidence.** A paint spy showed `QStyleOptionGraphicsItem.exposedRect` equal to
the item's WHOLE bounding rect during a cached paint — the viewport never reached
the item. The 2 000-add probe counted one `_refresh_layer_z` per item; the
existing `suspend_z_refresh` path measured 3.9 s.
**Root cause/fix.** `PolylineItem.paint` passed no clip to the shared
`PathStylePaint`, so the walk ran over the whole line; and `addItem` re-derived
z for the whole layer per item. The canvas now intersects the exposed rect with
the view's visible scene rect in item coordinates, grows it by the style's
decoration reach, and passes it with a `WalkBudget`; exports clear the cache and
keep full detail. `addItem` gives an appended independent solid the derivation's
own next value on a fixed `Z_POSITION_SCALE` grid - final, not provisional - so a
loop of adds costs one derivation per layer, direct or one item per command;
anything that can re-order the layer (a child, a bed, a roof ridge, a ground
surface, a pre-ranked re-add) still derives synchronously. Credit: the dense-
overlay half of the issue set (#551) and the N-shape boolean half (#550) follow
@Sevoiger's implementation in a personal fork.
**Lesson.** A cached paint's `exposedRect` is not the visible rect. Measure what
the paint call actually receives before trusting a cache; share the clip+budget
contract with the ground bake rather than adding a second walk; and when a
derivation can be avoided, do the arithmetic that makes the value final instead
of scheduling a second pass - a deferred pass is a second visible change.

