## 22. The atmosphere sky at the painted horizon (#716, #719)

Concept: docs §8.29.14; decisions and the before/after tables: ADR-048 addendum L7.1; values:
`ogp-lush-cinematic` reference 013; lessons PF-L3D-22, PF-L3D-23. Measured on the dev box
(RTX 4070, Direct3D 11, PyQt6 / PyQt6-Qt6 6.12.0), 2026-11-09:

- **A `QQuick3DTextureData`'s alpha reaches a `SkyMaterial` shader** with
  `setHasTransparency(False)`: the sky-view table's RGBA16F alpha carries the clear sky's
  per-elevation profile (`atmosphere_lut.sky_profile`), sampled with the rgb in one
  `texture()` call. The clouds' ambient samples read `.rgb` and are unaffected. A new
  painted sky at the same sun (a weather) refills the table (`SkyViewTexture.set_sky`); the
  sky-view rgb itself is cached per sun (`sky_view_lut`).
- **The frame is not `skyExposed`'s output.** At the noon Overcast the painted sky's radiance
  10° up predicts luminance 0.39 through `1 − exp(−x × probeExposure)`, and the frame reads
  0.62 — the scene's exposure and tone mapping act after it, on both sky models alike. A sky
  level is calibrated in the frame: render at two known factors and solve from the local
  response (`ln out / ln factor`: 0.53–0.94 for the deck at 10°) — PF-L3D-23.
- **Bin a sky by world elevation.** The `--sky-bands` phase (sky-only, `ground=None`, pitch
  10°, field 40°, 640 × 360) bins pixels within ±4° of a bearing in 0.5° bands centred on its
  multiples; each band holds 300–450 pixels, and the median luma of a flat band reproduces to
  0.0 (the painted sky's inversion reads 0.0 away and across at every sun).
- **A probe that keys on a clipped channel depends on what lies behind it.** Gate G4's disc
  finder took a plateau of pixels with EVERY channel ≥ 250. The atmosphere's 6° disc core
  read (255, 255, 252) on `master` and (255, 255, 243) once the profile dimmed the sky round a
  low sun (the 6–15° band 1.49× → 0.96× the painted sky): the disc stood where it was, but
  no plateau was found, and the warm fallback read it 0.49° low over the haze band. A clipped
  core is luma ≥ 250 (a warm core clips red and green first): 169 px, −0.04° at 6°, +0.05° at
  12°; every other view of both skies keeps its path (the painted discs peak at 200–216).
- **On a shared, full machine an offscreen board dies natively.** With the GPU at 11.7–11.9
  of 12.3 GB (other agents' renders) and 3.7 GB of commit left, boards exited 3, 4 and 139
  (segmentation fault) or raised `MemoryError` in `offscreen.image_rgba` at a 0.9 MB image,
  at the first or a later frame, with no Qt message. Nothing in the frames was wrong: the
  same command passed on a retry. Split long phases into batches of a few suns, retry, and
  read `nvidia-smi` before blaming the code.
- **Cost:** none measurable. The profile reuses the gain's cosine-weighted pass over 4,608
  directions (one cached `_balance` per sky) and the cached sky-view rgb. The Python work of
  one atmosphere sky (properties and table bytes), two interleaved rounds of 12 suns on the
  loaded machine: a new sun 244–270 ms median against `master`'s 259–275 ms, a new weather at
  the same sun 1.9 ms against 1.6–1.8 ms.
