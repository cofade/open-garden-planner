## Case study: the shadow drape still brightened the garden at night (#386, review round 1)

**Symptom.** With the alpha fixed (the case below), the `ogp-3d-reviewer`'s board showed
the shadow drape LIGHTENING what it covered — at night by +17.6 / +24.1 luma (max
+43.7) on 98–100 % of its pixels, at sunset on 89–97 %, at golden hour on 69 % over the
engine's own shadow. Every gate of the first build was green: they all rendered a
60–80° sun on lit ground.
**Wrong theories.** The alpha bug again (refuted: alpha 255 in every frame); a wrong
drape colour (refuted: the colour was the canvas's to the digit).
**Evidence.** A per-mood probe of the same patch: the shown colour moved with the
mood's EXPOSURE (2.4 at night, 1.15 at the golden anchor) — an Unshaded material's
colour is emitted and then exposed and tone-mapped; wherever the lit ground was darker
than that emission, a blend toward it lightened it. Top-down (exposure 1) it darkened.
**Root cause/fix.** An overlay that means "shadow" cannot be a colour blended over the
3D ground. A third overlay Model multiplies the frame (`DstColor` / `Zero`) by a linear
multiplier: 0.74–0.83 of the lawn's luma from noon to night, never lighter; the render
tier now asserts no pixel brightens in three moods. The other overlays divide their
colour by the exposure.
**Lesson.** Measure a look in every mood before calling it right; an overlay that is
"the 2D colour" in a top-down truth view can be wrong in every perspective one.
(PF-L3D-07; the same review found a blended or hidden part drops out of the shadow
map — PF-L3D-08.)

