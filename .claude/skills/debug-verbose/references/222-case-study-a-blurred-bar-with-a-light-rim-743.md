# Case study: a blurred foreground bar with a light rim on one side (#743)

## Symptom

On the photo blur's bench (`tests/integration/photoblur_bench.qml`: a dark bar near the camera,
out of focus, over a light panel in focus) the new `PhotoBlur.qml` softened the bar's edges as
designed, but the bar's own inside lit up next to ONE edge: 59 levels against 12 in its middle
at a 360 px picture, a few levels at 4K. Which edge it was changed with the picture size, so the
preview and a 4K save of the same shot differed exactly where the effect was meant to agree.

## Wrong theories

1. **Buffer aliasing.** The effect wrote one layer buffer twice (the far layer, then the near
   one, each read by the pass in between). An Effect's buffers are pooled; aliasing was a fair
   guess. Giving the near layer a buffer of its own changed nothing, to the level.
2. **A half-texel offset in the bilinear pair taps.** An asymmetric artefact smells of one.
   The taps are symmetric by construction, and a sideways shift would have moved every edge.

## Key evidence

Debug output instead of the picture: the compose pass wrote the near layer's amount, its
blurred coverage and its averaged colour into R, G and B (tone mapping off), and later the
layer pass's raw colour and weight. One row across the bar's right edge at 360 px:

| column | 369-375 (bar) | 376 | 377 (panel) |
|---|---|---|---|
| scene red, linear x255 | 1 | **34** | 134 |
| layer weight x255 | 255 | **255** | 0 |

The weight covered the bar's pixels and one more: the multisampled edge pixel, whose colour is
half bar and half panel. In linear light it was 26 times brighter than the bar, and averaged at
full weight it lit the whole blurred edge. The left edge's mixed pixel had fallen to the panel's
side of the depth pass, so that side stayed dark.

## Root cause

The colour is multisampled; Qt's depth pass for `DEPTH_TEXTURE` takes one sample per pixel. A
pixel on a layer's silhouette is therefore partly the thing beside it while its depth puts all of
it in the layer.

## Fix

`photoblur_layer.frag` counts a pixel whose cross neighbour lies outside its layer for a fifth
(`SILHOUETTE_WEIGHT`, PF-E3D-27). The rim read 14 levels at 360 px and 4 at 4K. Pinned by
`test_the_photo_blur_weighs_a_layers_silhouette_for_a_fifth` (source) and
`test_the_blur_bleeds_no_sharp_colour_and_softens_a_near_edge` (render tier, the bench).

## Lesson

When a post effect misbehaves, write its intermediate quantities into the picture's channels
with tone mapping off and read one row of numbers; the picture alone invites theories about
buffers and offsets. And never trust a depth-derived mask at a silhouette: in an MSAA frame the
mask and the colour disagree there by construction.
