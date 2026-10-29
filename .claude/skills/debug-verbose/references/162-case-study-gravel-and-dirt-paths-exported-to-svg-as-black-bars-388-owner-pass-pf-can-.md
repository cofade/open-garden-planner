## Case study: gravel and dirt paths exported to SVG as black bars (#388, owner pass, PF-CAN-27)

**Symptom.** After the owner pass made gravel and dirt paths their fill textures, every
gravel and dirt path in an SVG export was an opaque black bar as wide as the path. On the
canvas, in PNG, in PDF and on the 3D ground the paths were right.
**Wrong theories.** None were tried: the senior review found it with a probe, not a user.
The near miss is the gate set. Every check of the new painters was a raster: the bake's
parity with the canvas, white-versus-black backgrounds, renders. `path_style_paint` also
feeds the SVG export, and nothing exported a styled path to SVG.
**Evidence.** The SVG held `<g stroke="#000000" stroke-opacity="1" stroke-width="90">` around
the path, and no `<pattern>` at all. The same export with the old painters was correct.
**Root cause/fix.** The texture was drawn as a `QPen` whose brush was the texture.
`QSvgGenerator` writes a pen as its colour, and a texture brush's colour is black. The fix
fills the stroker's outline instead: `QPainterPathStroker` (width, round cap, round join),
`drawPath(createStroke(path))` with `NoPen` and the texture brush. The SVG then carries a
pattern fill, as a textured area's does.
**Lesson.** A painter that serves several outputs needs an export matrix test the day it
gets a new primitive: canvas, PNG, SVG, PDF. A pen with a non-solid brush is such a
primitive. In this repo a texture is always a fill.
Pins: `tests/integration/test_path_style_export.py` (SVG for every `PathFenceStyle`, PNG and
PDF for the textured ones; it fails on the old painter for exactly gravel and dirt).

