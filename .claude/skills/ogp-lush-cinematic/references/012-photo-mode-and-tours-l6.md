# Photo mode and tours — the values (L6, #390)

ADR-071. Photo mode develops a picture; it never changes what stands in the garden, and every
truth gate of section 1 holds in a developed picture. These are starting values. Tune them with a
before/after board and a note in the taste log.

| Setting | Range | Maps to | Note |
|---|---|---|---|
| Exposure | ±2 stops | a factor on the mood's own exposure | a stop is a stop in every mood |
| Vignette | 0..1 | `vignetteRadius` 0..0.35, strength fixed at 15 | at 1, a corner down to about a third, the middle within 2 % |
| Blur | 0..1 | `depthOfFieldBlurAmount` 0..8 at 1080p, scaled with the picture's height | 0.5 is what a first focus click gives |
| Focus range | | a quarter of the distance, at least 30 cm | |

Grades (`core/scene3d/photo.py`), each on top of the mood's own saturation and contrast:

| Grade | What it does |
|---|---|
| Golden Hour | warm highlights (R ×1.06, B ×0.88), a little warmth in the shadows |
| Crisp Day | contrast ×1.12, saturation ×1.16 around the mid-tones |
| Cool Morning | R ×0.93, B ×1.09, the greens barely touched |
| Soft Film | lifted blacks, softer highlights, saturation ×0.88 |
| Black and White | luma, with the filmic curve the view already has |

A tour starts its wind clock at 10 s, past the shaders' two-second ease-in, and a looped orbit ends
one step before its start. The owner has not judged any of these yet (open taste questions: the
strength of the grades, and whether a tour should ease in on an orbit).
