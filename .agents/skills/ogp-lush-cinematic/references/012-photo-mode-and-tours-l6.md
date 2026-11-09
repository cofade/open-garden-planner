# Photo mode and tours — the values (L6, #390)

ADR-072. Photo mode develops a picture; it never changes what stands in the garden, and every
truth gate of section 1 holds in a developed picture. These are starting values. Tune them with a
before/after board and a note in the taste log.

| Setting | Range | Maps to | Note |
|---|---|---|---|
| Exposure | -2 to +1.5 stops | a factor on the mood's own exposure | a stop is a stop in every mood; +2 clipped 66 % of a noon picture |
| Vignette | 0..1 | `vignetteRadius` 0..0.20, strength fixed at 15, colour black | at 1, a corner down to about a half, the middle within 2 %; Qt's default grey brightens a night |
| Blur | 0..1 | `PhotoBlur.qml`: a Gaussian of sigma 0..0.006 of the picture's height (6.5 px at 1080p, 13 px at 4K), over the layers behind and in front of the sharp band (#743) | 0.8 is what a first focus click gives; the same share of every picture, so the pane previews a 4K save (Qt's half-resolution blur kept 0.53 of the detail in the pane and 0.92 in the save) |
| Focus point | | the first blur above 0 focuses what the camera looks at; a click moves it | no depth of field without a point: the slider did nothing before a click (owner's manual test) |
| Ultra's reflections | | off while the blur is drawn | with glow, any two effects ahead of Qt's scene effect crash its chain in `d3d11.dll`: the app's blur too (PF-E3D-21, #744) |
| Focus range | | 60 % of the depth at the faintest blur, 3 % at the strongest, geometric in between (half in front, half behind), at least 60 cm (a whole plant; the owner's call), and at least 8 % of the depth at 25 m growing with its square (decided in #743's package, owner may veto) | the depth is along the view's axis; out of focus grows from 0 at the band's edge to full one band further; the band and the blur move together (owner's manual test of #390: a 40 % band showed nothing); the far floor keeps the 38-42 m whole-plan camera from a tilt-shift scale model (about a metre was left sharp) |

Grades (`core/scene3d/photo.py`), each on top of the mood's own saturation and contrast:

| Grade | What it does |
|---|---|
| Golden Hour | warm highlights (R ×1.05, B ×0.95), a little warmth in the shadows; B ×0.88 turned a blue sky olive |
| Crisp Day | an S-curve that leaves 0 and 1 in place (0.12), saturation ×1.08; a straight gain took a third of a sunset to a channel at 0 |
| Cool Morning | R ×0.93, B ×1.09, the greens barely touched |
| Soft Film | lifted blacks, softer highlights, saturation ×0.88 |
| Black and White | luma, with the filmic curve the view already has |

A tour starts its wind clock at 10 s, past the shaders' two-second ease-in, and a looped orbit ends
one step before its start. While it records, each plant has the finest detail its flight asks for
(`ForgeWorker.fly_path`). The owner has not judged any of these yet (open taste questions: the
strength of the grades, whether Black and White needs a filter, and whether a tour should ease in on
an orbit).
