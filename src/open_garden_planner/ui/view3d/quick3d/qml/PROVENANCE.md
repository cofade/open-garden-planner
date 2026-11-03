# Provenance of the 3D scene files (Phase 17)

Every file in this directory is the app's own (GPL-3.0-or-later) except the
atmosphere sky's, which come from Qt. Like the texture set and the icon set
(`ogp-asset-forge`): no provenance, no merge.

## The atmosphere sky (Phase 17 L7, #391) — Qt's `skymaterial` example

- **Source**: <https://github.com/qt/qtquick3d/tree/v6.12.0/examples/quick3d/skymaterial>,
  tag **v6.12.0** (the version the app pins), fetched 2026-11-02.
- **What it is**: a `SkyMaterial` (new in Qt Quick 3D 6.12) with Hillaire's
  atmosphere ("A Scalable and Production Ready Sky and Atmosphere Rendering
  Technique", 2020) and ray-marched volumetric clouds after Schneider ("Real-time
  Volumetric Cloudscapes of Horizon Zero Dawn", GPU Pro 7).
- **Licence texts**: `LICENSE-qt-skymaterial.txt` beside this file. Each file's
  header keeps its own copyright lines and SPDX identifier.

Per-file licence check (each file's own SPDX header read at the tag):

| File here | From (example) | SPDX at v6.12.0 | Used under | Changes |
| --------- | -------------- | --------------- | ---------- | ------- |
| `atmosphere_transmittance.frag` | `transmittance.frag` | MIT (© 2023 Fernando García Liñán, © 2026 The Qt Company) | MIT | none (a provenance comment) |
| `atmosphere_scatter.frag` | `skytexture.frag` | MIT (same holders) | MIT | none (a provenance comment) |
| `atmosphere.frag` | `advancedsky.frag` | MIT (same holders) | MIT, plus the app's part | the example's code up to its `MAIN()` unchanged; `MAIN()` and `paintedSky()` below the marked boundary are the app's (GPL-3.0-or-later) |
| `AtmosphereSky.qml` | `AdvancedSky.qml` | LicenseRef-Qt-Commercial OR BSD-3-Clause | BSD-3-Clause | the sun set from Python (not a light node), the noise volume handed in, the app's inputs, the LUTs fed only what their shaders read (header lists them) |
| `core/scene3d/cloud_noise.py` (outside this directory) | `cloudnoisetexturedata.cpp` / `.h` | LicenseRef-Qt-Commercial OR BSD-3-Clause | BSD-3-Clause | a numpy port of the same recipe (same hash, octaves, salts), checked against a scalar transcription of the C++ (`tests/unit/test_scene3d_cloud_noise.py`) |

**The painted-sky formula** in `atmosphere.frag`'s `paintedSky()` re-expresses
the arithmetic of Qt's `ProceduralSkyTextureData::generateSkyTexture()`
(`src/helpers/proceduralskytexturedata.cpp`, "LicenseRef-Qt-Commercial OR
GPL-3.0-only") so that the atmosphere sky draws the painted sky's horizon and night
exactly. That module is the Qt Quick 3D the app already ships under GPLv3, and the
app is GPL-3.0-or-later; distributed together they are GPLv3. Recorded here so
nobody has to rediscover where the curve and the sun-glow constants come from.

Not taken from the example: `main.qml`, `SettingsPane.qml`, `main.cpp`, its
CMake files, images and docs.
