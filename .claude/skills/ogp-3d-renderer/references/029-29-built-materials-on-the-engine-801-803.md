## 29. Built materials on the engine (#801, #803) — the specular switch, raw texture inputs, the glint

Concept: docs §8.29.12 ("Materials"); decisions: ADR-059 addendum "what built parts are made
of" (#801, #803); lessons: PF-E3D-32, PF-L3D-34, PF-L3D-35. Measured on the RTX 4070
(Direct3D 11) and, where said, on WARP, 2026-11-10, with other renders on the same GPU.

- **`PrincipledMaterial.specularAmount` is a switch at 0.01, then hardly a dial.** A black
  (#303336) trampoline mat facing a 15.2° sun, the camera 6.5 m back along the sun's azimuth
  and 2.6 m up, roughness 0.95: luma 25.4 at 0.0, 0.005 and 0.01; 62.8 at 0.015; 62.2 at
  0.02; 62.8 at 0.05; 63.5 at 0.35. Roughness moves the grazing sheen more than the amount:
  73.2 at 0.90, 57.7 at 0.98, 54.6 at 1.0 (amount on). The sweep fits a material key that
  enables specular only above 0.01 and a Fresnel term that reaches 1 at grazing whatever F0
  the amount sets. A dull dark surface takes 0 (`SURFACES` rubber and canvas); the amount
  still scales the image light's diffuse by (1 − amount) (§4 of `ogp-lush-cinematic`).
- **`Texture` has no anisotropy.** Qt 6.12's `Quick3D.qmltypes` lists for `QQuick3DTexture`
  only source, sourceItem, textureData, textureProvider, the UV transform, tiling, flips,
  indexUV, mag/min/mip filter, generateMipmaps and autoOrientation. A detail picture stays
  clean at a grazing angle by trilinear mipmaps (isotropic: blurrier than anisotropic, never
  a moiré) and by fading the detail normal with distance (`built_detail.frag`).
- **A `TextureInput` in a custom shader is sampled RAW**: no sRGB decode, no `flipV` (that is
  PrincipledMaterial's own lookup, `ogp-3d-renderer` §5). `texture(map, uv)` at v = 0 reads
  the texture data's FIRST row; a `QQuick3DTextureData` uploaded top row first has v = 0 at
  the picture's top — the 2D brush's frame, so a roof seen from above is the canvas's picture
  (`tests/unit/test_scene3d_roof_uvs.py` holds the uvs to Qt's own `QTransform` of
  `roof_paint`). Mipmaps of a raw RGBA8 texture average its bytes linearly: store LINEAR
  quantities (an albedo multiplier, a slope) and the far mip is their linear mean.
- **A cotangent frame from screen derivatives** (`dFdx` / `dFdy` of `VAR_WORLD_POSITION` and
  of the picture's coordinates, Schüler) bends a normal for a picture laid by ANY uv — a
  gable's mirrored half and a hip's faces need no tangent in the mesh. Compiled and rendered
  on Direct3D 11 (GPU and WARP: the render tier's numbers agreed to the decimal) and OpenGL
  on the GPU (`QSG_RHI_BACKEND=opengl`: the render tier's judge passed every gate); Mesa's
  llvmpipe was not run here — CI's Linux render job runs `test_built_materials_render.py`.
- **`VERTEX` and `NORMAL` in a custom vertex shader are MODEL space**: a wall lays its picture
  by its own plane in the item's frame (it stays on the item when it moves or turns). The
  colour goes on through `COLOR` → a varying: `VAR_COLOR` read in a fragment shader without a
  vertex stage of its own came out darker and more saturated (#687, `built_snow.vert`).
- **`SPECULAR_LIGHT()` replaces a light's specular in a shaded `CustomMaterial`.** Its inputs
  `TO_LIGHT_DIR`, `VIEW_VECTOR`, `NORMAL`, `ROUGHNESS`, `LIGHT_COLOR`, `SHADOW_CONTRIB` compile
  on Direct3D 11; `water.frag` computes GGX with Schlick's Fresnel for water and soft-caps the
  peak at `uGlintCap` = 0.6 / exposure (linear, before the exposure): at the mirror angle of a
  10 / 20 / 30° sun over a 160 cm pond (1280 × 720, high) the clipped share of the water went
  6.14 / 4.48 / 2.73 % → 0.00 %, peak luma 255 → 212.6 / 227.0 / 237.2. A cap of 1.0 still
  clipped 0.6-2.7 % (the warm sun clips red first; the look's grade and glow sit on top). The
  blob was the direct light, not the sky reflection: with `uReflect` 0 it was 4.47 against
  4.48 %.
- **One material per Model, split at the sink.** A part of several surfaces is ONE `MeshPart`
  with `surface_runs`; `Quick3DSink` creates a Model per run (`mesh.surface_pieces`). Models
  43 → 71 for the family garden's built records, 87 → 169 for `bench_large`; vertices
  uploaded and bytes unchanged (151,182 / 8.22 MB and 290,065 / 15.76 MB): a run's vertices
  are its own in every builder measured. The UVs ride in the slot every vertex already had.
- **A picture per scene**: five 256² RGBA8 detail textures (`ROOF_TILES`, `SLATE`, `CONCRETE`,
  `STONE`, `WOOD`), each made on first use through `createPatternTexture` (repeat, mipmaps),
  never re-pointed (§5's white rule), let go with the fill pictures in `clear()`.
- **What it costs** (the family garden at golden hour; a finished readback of a NEW frame per
  preset, `render_beauty_board.py --fps-seconds`, rounds alternating before / after while other
  renders shared the machine). RTX 4070, 1920 × 1080, medians of three rounds: Low 14.1 → 11.3
  ms, Medium 13.5 → 10.7, High 15.2 → 13.8, Ultra 18.6 → 19.8 — inside the rounds' own spread
  (8.2-31.5 ms). WARP, 1280 × 720, two rounds: Low 99.0 / 95.8 → 102.2 / 98.0 ms, Medium 154.9 /
  149.6 → 144.0 / 160.2, High 221.5 / 221.7 → 214.0 / 211.1. No preset measurably dearer; Low
  carries the pictures too (the detail textures are 256², mipmapped). A never-shown host's first
  frame compiles every pipeline it draws: the living board's 171 frames 4.12 → 4.60 s median,
  810 → 850 s in all (one leg each) — the detail material's shaders, most likely; alternating in
  one process, frames with and without the pictures differed by less than their own spread
  (4.5-5.7 s). On a loaded machine the living board passed its 780-s watchdog neither before
  nor after (`test_living_garden_render.py`'s board tests time out there; the same board took
  531-636 s on this machine earlier the same day).
- **A key mask has a hole where a highlight is**: a glint is as bright in the white key as in
  the black one. The render tier fills each row of the (convex) pond between its first and last
  keyed pixel; with the raw key mask the old, clipping glint passed the gate.
- **WARP once wrote a green-only frame** (R = B = 0 on every pixel) for one of 26 frames of the
  `built_materials` scenario (`bm_roof_noon_flat`); the next WARP run of all 32 frames, and the
  OpenGL run, had none. Unexplained. That run's roof-colour gate failed on it (the flat roof's
  mean read (0, 143, 0)): judge every frame a gate uses, so a broken one cannot pass quietly.
