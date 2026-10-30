## 18. Counting engine textures without GPU memory (QTBUG-151940)

Concept: docs §8.29.5 known limit 11; the leak itself: reference 13 and TD-040. Measured on
2026-10-30 with the reproducer in `docs/09-architecture-decisions/adr-048-evidence/qtbug-151940/`
(official `qml.exe` 6.12.0, and the PyQt6 6.11.0 / 6.12.0 wheels; RTX 4070, Direct3D 11
hardware and WARP, Vulkan, OpenGL):

- **`View3D.renderStats.textureDetails` counts the textures the engine holds.** With
  `renderStats.extendedDataCollectionEnabled: true` it is a Markdown table with one row per
  `QRhiTexture` in `QSSGRhiContextPrivate::m_textures` (`qquick3drenderstats.cpp`,
  `processRhiContextStats()`). The buffer manager registers the textures it loads there and
  removes it only in `releaseTexture()`, so a texture that is never released stays a row until
  the `QSSGRhiContext` is destroyed. Counting rows shows such a leak exactly and on every
  backend, without reading GPU memory: 16 → 24 → 32 … per release for the #532 leak, 16 in
  every cycle without the release. `renderStats.imageDataSize` moves with it (the buffer
  manager's own sum, not driver memory).
- **Only a cycle that rendered a frame counts.** The display-asleep stall of reference 6 ("Do
  not wait for `frameSwapped` …") hit hardware Direct3D 11 here too: one frame per run, every
  cycle flat. On the same RTX 4070, Vulkan and OpenGL kept presenting, as WARP does. A probe
  that compares counts across a release must count `frameSwapped` and reject a cycle without
  a new frame; the reproducer prints `LEAKTEST INVALID` then.
