## 27. The meadow's grass on the engine (#798)

Concept: docs §8.29.12 ("The meadow's grass"); decisions and the before/after tables: ADR-048
addendum "the meadow's grass"; values: `ogp-lush-cinematic` reference 017; lessons PF-L3D-30,
PF-L3D-31. Measured on the dev box (RTX 4070, Direct3D 11, PyQt6 / PyQt6-Qt6 6.12.0),
2026-11-10, unless a line says otherwise:

- **A `Texture` has no anisotropic filtering.** Its meta-object in Qt 6.12 lists `source`,
  `sourceItem`, `textureData`, `textureProvider`, `scaleU`/`V`, `mappingMode`,
  `tilingModeHorizontal`/`Vertical`/`Depth`, `rotationUV`, `positionU`/`V`, `pivotU`/`V`,
  `flipU`/`V`, `indexUV`, `magFilter`, `minFilter`, `mipFilter`, `generateMipmaps`,
  `autoOrientation` — nothing else. A grazing ground is trilinear at best: the mip follows the
  footprint's long axis, so a far texture BLURS (it does not crawl). The far meadow's flicker
  through an orbit, followed on fixed ground points: 0.23 luma RMS zigzag (flat meadow 0.09).
- **`VAR_WORLD_POSITION` is readable in a `Shaded` `CustomMaterial`'s fragment `MAIN`**
  (world centimetres: x east, y up, z south). `ground.frag` lays the grass in world space with
  it, the same on the meadow's 100 m cells and on a 5 m ground tile — one function across
  the plan's edge. UV0 is not used for it (the meadow's mesh carries none).
- **An RGBA16F `QQuick3DTextureData` with `generateMipmaps: true`** samples with linear
  filtering and a full mip chain; its mips average the stored LINEAR values, so a texture
  stored as linear light over its mean keeps mean 1 at every level (the far meadow's mean
  luma within 1.2 of the flat meadow's in every bundled example's default framing; part of
  it is the variation's own local mean). 256² × 8 bytes = 512 KiB, ~683 KiB with mips, ONE
  per host (`GrassDetailTexture`), its `Texture` never re-pointed (§5).
- **A uniform branch around `texture()` in a custom material** (`if (uSurface > 0.5)`) compiles
  and renders on Direct3D 11 with no Qt message, as `water.frag`'s `uHasFill` branch does; the
  grass costs nothing where `uSurface` is 0 (the truth view).
- **A tile texture with alpha below 1 under a `CustomMaterial`** that writes `BASE_COLOR.a = 1`
  draws opaque (`setHasTransparency(False)`): the alpha is data for the shader (the bake's
  coverage, PF-L3D-31), never a blend. A `PrincipledMaterial` would read it as opacity, so the
  tiles draw `ground.frag` at every preset (the Low preset's `tileFlat` is gone).
- **`QImage` premultiplied formats** (`Format_RGBA8888_Premultiplied`, the tiles'): `fill` with
  a transparent colour writes zeros; a raw pixel (72, 127, 52, 0) survives `QPainter`, an opaque
  fill overwrites it, a half-transparent one gives (66, 133, 56, 128) — the colour exactly as
  over an opaque meadow; `convertToFormat` to a straight format divides by the alpha (open
  ground black, half coverage (131, 255, 112, 128)). Copy such tiles with composition mode
  `Source` and force the alpha before handing them to anything that converts.
- **A `CustomMaterial` without light functions takes the scene's ambient lights** like a
  `PrincipledMaterial`: the twilight fill (#802, an `ambientColor` on the fill light) lights the
  meadow as it lights the tiles.
