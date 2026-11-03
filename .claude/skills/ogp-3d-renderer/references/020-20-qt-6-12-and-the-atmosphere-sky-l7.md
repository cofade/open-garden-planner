## 20. Qt 6.12 and the atmosphere sky (L7, #391)

Concept: docs §8.29.14; decisions and every number: ADR-048 addendum L7; lessons: PF-E3D-13,
PF-E3D-14, PF-E3D-15, PF-E3D-16, PF-E3D-17, PF-CI-17, PF-TST-36. Measured on the dev box (RTX 4070, Direct3D 11; WARP on the
same machine), 2026-11-02/03, PyQt6 / PyQt6-Qt6 6.12.0:

- **Destroying an earlier sky Texture nulls the current light probe** (6.12 only): the
  stale destroyed-watcher fires `setLightProbe(nullptr)` although the probe is the new sky,
  and the next frame draws the clear colour — on a host's first sun change (measured without
  the fix: the first rebuild, once also the second; later rebuilds and those after a sky-model
  switch never). `Garden.qml` restores
  the binding in `onLightProbeChanged` (synchronous; `Component.onDestruction` is too early,
  a 0 ms Timer too late). A board renders a fresh host per frame and cannot see it; the
  sky-sequence test can (PF-E3D-16).
- **The pick honours the cull mode.** `qssgrenderray.cpp` v6.12.0 accepts either determinant
  sign for a `NoCulling` material (6.11: positive only). Foliage, grass and glass are picked
  from behind now; the selection witness keeps every face of `materials.TWO_SIDED_KINDS`.
- **Unchanged at the source level** (byte-identical files at v6.11.0 and v6.12.0): the colour
  property's linearisation polynomial (`qssgutils.cpp`) and `sampleProbe.glsllib`
  (`qt_sampleDiffuse` / `qt_sampleGlossy`). `QSGRendererInterface.GraphicsApi` member names
  are the same.
- **`SkyMaterial`** (new in 6.12): `SceneEnvironment.backgroundMode: SceneEnvironment.SkyMaterial`
  with `skyMaterial: <SkyMaterial>`; its QML properties become uniforms by name (a `Texture`
  property is sampled — as `sampler3D` when its data has a depth); `fragmentShader` writes
  `FRAGCOLOR` from `qt_eyeDir`. It renders a cube (`radianceMapSize`, default 512) that backs
  the view (`skyboxMode: Cubemap`, or `ScreenSpaceFull/Half/Quarter` evaluated on screen) and,
  with `enableIBL`, is GGX-filtered into the scene's light (`iblSampleCount`, `iblRenderFrames`
  0 = one frame). Property changes re-render it by themselves.
- **Never let a 6.12.0 `SkyMaterial` build its cube** (PF-E3D-17): its pre-filter
  (`QSSGRenderSkyMaterialManager::runPrefilterCycle`) used a freed QRhi resource, an access
  violation in `Qt6Gui.dll`'s `sanityCheckResourceOwnership` with no Python trace. The owner's
  frozen exe died that way. A full-app probe crashed 3 of 5 times at one painted to atmosphere
  switch, and 0 of 4 with the cube off. Qt builds the cube for `enableIBL`, `skyboxMode:
  Cubemap`, a `ReflectionProbe` or a material reading `SCREEN_TEXTURE`
  (`QSSGLayerRenderData::resolveLayerIblTexture`). The app's atmosphere is `enableIBL: false`
  with `ScreenSpaceHalf`, and the painted sky's texture stays `lightProbe`. With a probe set,
  Qt skips the sky material's IBL pass but `SkyMaterialBackgroundPass` still draws the sky.
- **The screen path applies no exposure under post effects:** Qt compiles `qt_exposure` to a
  pass-through there (`mainFragmentSnippetScreen`; a Custom tonemap has no
  `QSSG_FORCE_IBL_EXPOSURE` variant, while `skybox_hdr_custom` has one). A sky shader writes
  `1 − exp(−c × e)` itself: 1.8× too bright by day and 2.9× at night without it, and a plain
  multiply leaves 13–14 luma by day because the curve compresses bright values.
- **Reading a native crash without a debugger:** a machine with a `LocalDumps` key leaves
  minidumps in `%LOCALAPPDATA%\CrashDumps`. Parse the dump with the `minidump` package, scan
  the faulting thread's stack for return addresses inside loaded modules, and name each by the
  nearest export (`pefile`). Most of Qt Quick 3D's runtime is exported, so the chain is
  readable. Disassemble the faulting function with `capstone`: a `qWarning` format string it
  references names it. PyQt6 cannot convert a `SkyboxMode` enum read through `property()`.
- **It compiles only when every texture it samples exists** — and says nothing otherwise: a
  texture input left null drew Qt's built-in debug sky forever; the example's
  `QuadTextureProvider` tables made the first frame white. Hand it `QQuick3DTextureData`
  (PF-E3D-14). The app's never-shown offscreen view renders ONCE: a second `grabWindow()` was
  an access violation (the host's contract stands).
- **A custom material under a `SkyMaterial`:** Qt calls its `IBL_PROBE()` and includes
  `sampleProbe.glsllib`, but `QSSG_ENABLE_LIGHT_PROBE` stays false. A sky term guarded by
  that macro alone compiles out: the pond read (1, 18, 32) at a 4° sun against the painted
  sky's (5, 40, 65). Guard on the macro OR `defined(SAMPLE_PROBE_GLSLLIB)` (PF-E3D-15);
  the painted sky's frames are identical with either guard.
- **A 3D texture from Python:** `QQuick3DTextureData.setDepth(n)` with `Format.RGBA16F` and
  `Texture { tilingModeDepth: Texture.Repeat }` (the 64³ cloud volume) — sampled with
  `textureLod(volume, vec3, 0.0)` in the sky shader.
- **Cost:** first atmosphere frame 783 ms (painted 663 ms; a one-time compile), each later sun
  change ~200 ms of GUI thread (painted 122 ms: the CPU sky-view table ~110 ms, the gain
  ~30 ms), plus the painted sky it now builds as the light. Per frame on screen (1280 × 720,
  looking into the sky): painted 2.23 ms; the atmosphere at cover 0.4: Half 3.11 ms, Full
  4.38, Quarter 2.55. Half and Full look the same. A board renders a fresh host per frame and
  pays the compile per frame (~2.5-4 s).
- **Software adapter:** the self-test's screen-space atmosphere without the painted probe
  (`sky_probe=False`) renders on WARP (a quarter resolution, before the revision: 44.3 / 28.1
  on both).
- **The sky probe on the atmosphere** reads the disc only once the disc outshines its aerosol
  halo: at the painted disc's energy the probe locked onto the horizon glow 9° below the sun
  (bearing still within 0.35°); `ATMOSPHERE_DISC_ENERGY` 4 → bearing 0.02°, elevation 11.98° for
  12°. A probe that checks only the bearing would have passed the wrong blob.
- **QTBUG-151940** still leaks on the 6.12.0 wheels (8 textures a cycle; *In Review*).
- **`QAccessibilityHints.motionPreference`** exists in 6.12 (Windows reads
  `SPI_GETCLIENTAREAANIMATION`).
