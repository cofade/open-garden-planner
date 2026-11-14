# Upstream report [QTBUG-152289](https://qt-project.atlassian.net/browse/QTBUG-152289): glow, reflections and depth of field in one ExtendedSceneEnvironment crash on Direct3D 11

Filed on 2026-11-14 from the owner's Qt account for #744: space "Qt (QTBUG)", type Bug, component
Quick: 3D, affects version 6.12.0, platform Windows. Claude Fable 5 prepared the report and Claude
Opus reviewed it; Claude Opus 5.5 added the series with Qt's own `qml.exe` on the day of filing.
`effect_chain_glow_crash.qml` in this folder is the ticket's only attachment, byte-identical to the
committed file (git blob `3eee7913`). The text below the line is the report as filed: the title, the
"Environment" field, then the description.

---

**Title:** ExtendedSceneEnvironment with glow, screen-space reflections and depth of field crashes on Direct3D 11 (access violation in d3d11.dll, heap corruption at exit)

**Environment:**

Windows 11 Pro (10.0.26200), Direct3D 11, threaded render loop. Reproduced on an NVIDIA GeForce RTX 4070 (driver 610.88) and on WARP (Microsoft Basic Render Driver). Other backends and other Qt versions not tested.

Qt 6.12.0. The first series below was run with Qt's own `qml.exe` from the official Qt 6.12.0 binaries (MSVC 2022 64-bit, download.qt.io, signed by The Qt Company Oy). The second series was run with Qt 6.12.0 from the PyQt6-Qt6 6.12.0 wheel (official Qt binaries, signed by The Qt Company Oy), loading the file with a `QQmlApplicationEngine`. The attached file imports only `QtQuick`, `QtQuick3D` and `QtQuick3D.Helpers`.

## Steps

1. Run `qml effect_chain_glow_crash.qml` (attached). It shows one cube on a plane with an
   `ExtendedSceneEnvironment` that enables `glowEnabled`, `ssrEnabled` and `depthOfFieldEnabled`.
2. Wait for the process to end (the file quits after 3 seconds) and read its exit code.

## Expected

The window shows the cube, and after 3 seconds the file prints `ALIVE after 3 s`, quits and
exits with code 0.

## Actual

The process ends with an access violation (exit code 0xC0000005) or with heap corruption
(0xC0000374). The exit code is the signal: the `ALIVE` line can still appear in a run that
crashes.

Series with Qt's own `qml.exe` (official Qt 6.12.0 binaries, `QT_FORCE_STDERR_LOGGING=1`; WARP rows with `QSG_RHI_PREFER_SOFTWARE_RENDERER=1`):

| Run | Adapter | Runs | 0xC0000005 | 0xC0000374 | Exit code 0 |
|---|---|---|---|---|---|
| `qml effect_chain_glow_crash.qml` | WARP | 10 | 8 | 2 | 0 |
| `qml effect_chain_glow_crash.qml -- --seconds=10` | WARP | 3 | 1 | 1 | 1 |
| `qml effect_chain_glow_crash.qml -- --no-glow` | WARP | 3 | 0 | 0 | 3 |
| `qml effect_chain_glow_crash.qml -- --no-ssr` | WARP | 3 | 0 | 0 | 3 |
| `qml effect_chain_glow_crash.qml -- --no-dof` | WARP | 3 | 0 | 0 | 3 |
| `qml effect_chain_glow_crash.qml` | RTX 4070 | 3 | 2 | 0 | 1 |

In 1 of the 10 WARP runs with the 3-second timer, Qt printed `Device loss detected in Present()` and `Graphics device lost, cleaning up scenegraph and releasing RHI` before it crashed. In the other runs of this series Qt printed no warning.

An earlier logged series on WARP, with the file loaded with a `QQmlApplicationEngine` from the PyQt6-Qt6 6.12.0 wheel (`QSG_RHI_PREFER_SOFTWARE_RENDERER=1`, `QT_FORCE_STDERR_LOGGING=1`):

| Run | Runs | 0xC0000005 | 0xC0000374 | Exit code 0 |
|---|---|---|---|---|
| `qml effect_chain_glow_crash.qml` | 20 | 18 | 2 | 0 |
| `qml effect_chain_glow_crash.qml -- --seconds=10` | 8 | 6 | 2 | 0 |
| `qml effect_chain_glow_crash.qml -- --no-glow` | 3 | 0 | 0 | 3 |
| `qml effect_chain_glow_crash.qml -- --no-ssr` | 3 | 0 | 0 | 3 |
| `qml effect_chain_glow_crash.qml -- --no-dof` | 3 | 0 | 0 | 3 |

Details of that series:

- With the 10-second timer, the 6 runs with 0xC0000005 ended 4 to 5 seconds after their start
  and printed no `ALIVE` line. The 2 runs with 0xC0000374 printed `ALIVE` at 10 seconds and
  ended about 3 seconds later.
- With the 3-second timer, 19 of the 20 runs ended 4 to 5 seconds after their start, and 13 of
  the 20 printed the `ALIVE` line before they ended.
- In 3 of the 20 runs Qt printed `Device loss detected in Present()` and
  `Graphics device lost, cleaning up scenegraph and releasing RHI`, and created a second QRhi
  for the window. In 2 of these 3, Qt then printed `Broken filename passed to function`
  28 times and `QSSG.warning: Failed to load image:` followed by a damaged path. In an earlier
  run with these device-loss lines, the path ended in
  `ers/images/gradientTexture.png` and the characters before that were not printable.
  (`SceneEffect.qml` loads `qrc:/qtquick3d_helpers/images/gradientTexture.png`.)
- In the other runs Qt printed no warning.

Earlier runs on the same machine: 7 on the RTX 4070 (6 exited with 0xC0000005 and none printed
`ALIVE`; the exit code of the seventh was not recorded) and 17 on WARP (16 exited with
0xC0000005 or 0xC0000374; one printed `ALIVE` and exited with code 0).

One crash dump faults at `d3d11.dll+0x158c32`, a read at address 0x16d. Microsoft's public
symbols name it `CContext::OMSetRenderTargets+0x2e2` (the installed `d3d11.dll` is version
10.0.26100.9711). An application that enables the same three effects, with other settings on,
crashed twice at this address.

In Qt 6.12.0, `SceneEffectEnvironment::updateSpatialNode` (`src/helpers/impl/sceneeffects.cpp`)
appends the reflection effect and the depth-of-field effect to the effect list ahead of the main
scene effect, which does the tonemapping and the glow. So the failing chain has two effects
ahead of the scene effect, and glow on.

We have not located the cause in Qt's source.

## Possibly related

- QTBUG-144137 (closed, Qt RHI, fix versions 6.8.7, 6.10.3, 6.11.0, 6.12.0 FF): a Direct3D 11
  crash whose discussion shows a debug-layer message about `OMSetRenderTargets`. This report is
  on 6.12.0.
- QTBUG-143050 (Need More Info, Quick: 3D, 6.11.0): a crash after enabling screen-space
  reflections, reported on Vulkan, with no glow in its description.

## Workaround

The application avoids the crash by turning screen-space reflections off while its depth of
field is on.
