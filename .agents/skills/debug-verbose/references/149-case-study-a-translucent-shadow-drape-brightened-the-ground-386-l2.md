## Case study: a translucent shadow drape brightened the ground (#386, L2)

**Symptom.** The first 3D shadow drape — the canvas's shadow blue (30, 41, 66) at
alpha 110/255 over the lit meadow — read rgb(79, 107, 75) over a ground of
rgb(25, 73, 11): LIGHTER than the ground it was meant to shade. The new self-test
judge caught it on the GPU and on WARP alike; the lines overlay with the same
shaders but opaque colours read exactly its colour.
**Wrong theories.** Vertex colours not reaching the shader (refuted: opaque colours
came through to the digit); a second sRGB conversion of the drape; drawing the drape
before the ground tiles (refuted: the bare ground without tiles read the same).
**Evidence.** A sweep of known colours through `render_records` measured the blend:
black at a = 0.25 / 0.5 / 0.75 read (67, 102, 56) / (76, 100, 69) / (53, 65, 50);
white at 0.5 read (204, 228, 197). Every value fits
`a·src + (1 − a)·ground + 4·a(1 − a)·64`: a grey term proportional to a(1 − a), largest
at a half — the signature of the DESTINATION ALPHA. With the colour factors applied to
alpha too it becomes 1 − a(1 − a), and the View3D's texture, drawn over the window's
white, lets a(1 − a)·255 through.
**Root cause/fix.** `sourceBlend: SrcAlpha` / `destinationBlend: OneMinusSrcAlpha` on a
CustomMaterial also blends alpha. Add `sourceAlphaBlend: Zero` /
`destinationAlphaBlend: One`: black at 0.5 then reads exactly half the ground, the drape
(16, 44, 12) — on Direct3D 11 (GPU, WARP) and OpenGL. The same rule went onto the
foliage, grass and water materials that blend while X-ray fades them.
**Lesson.** Measure a blend with several alphas and two source colours before trusting
one translucent frame: one sample cannot tell a wrong colour from a wrong equation, and
a term in a(1 − a) points straight at the destination alpha. Pins: the self-test judge
(`selftest.judge_frame`, `TestJudge::test_a_drape_that_brightens_the_ground_fails`) and
`tests/integration/test_view3d_analysis_render.py`. PF-L3D-06.

