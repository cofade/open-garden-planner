## Case study: a crash with no trace under the new sky (#391)

- **Symptom:** the owner's frozen exe vanished about two minutes into testing "Atmosphere with
  clouds". Windows logged `c0000005` in `Qt6Gui.dll`. There was no Python trace, no `crash.log`
  and nothing in `app.log`. Every gate had been green: the render tier, two 3D reviews, two
  senior reviews and the self-test.
- **Wrong theories:** a Python-owned `QQuick3DTextureData` garbage-collected under QML (the host
  holds both data objects for its life); switching the sky alone (215 switches in 200 s: no
  crash); the atmosphere alone (345 actions of time, weather, walk, reduce motion and layout: no
  crash); a known Qt bug (QTBUG-149007 and QTBUG-149590 are near but not this path).
- **Key evidence:** Windows had written a minidump (`%LOCALAPPDATA%\CrashDumps`, from a
  `LocalDumps` key another product set). A stack scan of the faulting thread, with each return
  address named by the nearest export, read `rhiPrepare → resolveLayerIblTexture →
  QSSGRenderSkyMaterialManager::resolve → ensureEnvironmentMap → runPrefilterCycle`. The faulting
  function, disassembled with `capstone`, referenced the warning "%s %p (%s) belongs to QRhi %p,
  but client code attempted to use it with QRhi %p": `sanityCheckResourceOwnership`, reading a
  freed resource's owner as `0x20000000`. A full-app probe printed each action before running it,
  with `faulthandler` on. Seed 7 crashed three of five times at action 186, a painted to
  atmosphere switch at night in snow after a weather change. The other two passed it. With the
  cube off (`enableIBL` false, ScreenSpace) it crashed 0 of 4 times.
- **Root cause:** Qt 6.12.0's sky material light cube pre-filter uses a freed QRhi resource. The
  manager `delete`s textures at once and compares raw pointers to detect changes, so a recycled
  address can pass its cache check. The exact resource is not identified.
- **Fix:** the atmosphere never builds the cube: `enableIBL: false`, `ScreenSpaceHalf`, and the
  painted sky's texture lights the garden under both models (PF-E3D-17). The same seed then ran
  4 × 240 s without a crash, and about 40 % faster.
- **Then the fix's own bug:** the 3D review rejected the first build. Qt's screen path skips
  the probe exposure under post effects, so the sky read 1.8× too bright. Reading
  `tonemapping.glsllib` explained the review's fitted 0.80: `qt_exposure` is `1 − exp(−c × e)`,
  so the shader applies that curve instead of a constant.
- **Lesson:** a native crash with no trace is still readable. Look for a minidump before
  theorising; a stack scan named by nearest exports and a disassembled warning string identify
  the Qt function without symbols. A crash that needs a sequence takes a seeded action probe
  that prints before acting; one seed reproduced it at the same action in three of five runs.
  Gates that render a fresh host per frame never see a sequence.
