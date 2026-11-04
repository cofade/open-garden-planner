# Photo mode and tours — the values (L6, #390)

ADR-072. Photo mode develops a picture; it never changes what stands in the garden, and every
truth gate of section 1 holds in a developed picture. These are starting values. Tune them with a
before/after board and a note in the taste log.

| Setting | Range | Maps to | Note |
|---|---|---|---|
| Exposure | -2 to +1.5 stops | a factor on the mood's own exposure | a stop is a stop in every mood; +2 clipped 66 % of a noon picture |
| Vignette | 0..1 | `vignetteRadius` 0..0.20, strength fixed at 15, colour black | at 1, a corner down to about a half, the middle within 2 %; Qt's default grey brightens a night |
| Blur | 0..1 | `depthOfFieldBlurAmount` 0..5 at 1080p, scaled with the picture's height | 0.8 is what a first focus click gives; at 8 Qt's three taps read as ghosts |
| Focus range | | 40 % of the depth (half in front, half behind), at least 30 cm | the depth is along the view's axis |

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
