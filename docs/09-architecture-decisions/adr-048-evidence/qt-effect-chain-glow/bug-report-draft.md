# Draft upstream report: glow plus two effects in one ExtendedSceneEnvironment crash on Direct3D 11

Not filed. Filing needs the owner's Qt account (create in the "Qt (QTBUG)" space, not COIN).
Attach `effect_chain_glow_crash.qml` from this folder. Prepared for #744 of Open Garden Planner.

---

**Title:** ExtendedSceneEnvironment: glow with screen-space reflections and depth of field crashes the render thread in d3d11.dll (OMSetRenderTargets)

**Affected version:** 6.12.0

**Component:** Quick: 3D

**Platform:** Windows 11 Pro (10.0.26200), Direct3D 11. Reproduced on NVIDIA GeForce RTX 4070 and on WARP (Microsoft Basic Render Driver). Other backends not tested.

**Environment:** Qt 6.12.0 from the PyQt6-Qt6 6.12.0 wheel (official Qt binaries inside), loaded with `QQmlApplicationEngine`. The attached file uses no other code.

## Steps

1. Run `qml effect_chain_glow_crash.qml` (attached). It shows one cube on a plane with an
   `ExtendedSceneEnvironment` that sets `glowEnabled`, `ssrEnabled` and `depthOfFieldEnabled`.
2. Wait 3 seconds.

## Expected

The window shows the cube, and after 3 seconds the file prints `ALIVE after 3 s` and quits.

## Actual

The process dies at the first frame with an access violation (exit code 0xC0000005) and prints
nothing, no Qt warning either. The crash dump faults at `d3d11.dll+0x158c32`
(`CContext::OMSetRenderTargets+0x2e2`, a read at address 0x16d), the same address as two crashes
of an application on the Ultra quality preset of its own (named from Microsoft's public
`d3d11.pdb`). A raw scan of the faulting thread's stack (no symbols for Qt's private code) finds
addresses in Qt6Gui near `QRhi::finish`, in Qt6Quick3D and in Qt6Quick's batch renderer.

Counts on one machine (Windows 11, RTX 4070): 6 of 7 GPU runs exited with 0xC0000005 and the
seventh ended without printing `ALIVE`; 3 of 3 WARP runs (`QSG_RHI_PREFER_SOFTWARE_RENDERER=1`)
died the same way.

## What changes it

| Run | Result |
|---|---|
| `qml effect_chain_glow_crash.qml` (glow + reflections + depth of field) | crash at the first frame |
| `-- --no-glow` | prints ALIVE |
| `-- --no-ssr` | prints ALIVE |
| `-- --no-dof` | prints ALIVE |

The number of effects, not their kind, seems to matter. With glow on, two effects ahead of the
environment's own scene (tonemapper) effect break the chain; one is fine with any number of passes
and buffers. Observed with the same cube scene:

- two pass-through user `Effect`s in `effects` (each one `Pass` whose fragment shader writes
  `texture(INPUT, INPUT_UV)`), with glow: no crash, but the picture is grey where the cube was;
- reflections plus one pass-through user `Effect`, with glow: a black picture, or a crash when
  `ssrEnabled` is switched on after the first frame;
- reflections plus depth of field with glow, `ssrEnabled` switched on after the first frame: a white
  picture;
- any of these pairs without glow: correct pictures.

The failure looks like an intermediate render target of the effect chain released or reused while
the glow passes still use it, when more than one effect runs ahead of the scene effect.

## Workaround

Keep at most one effect ahead of the scene effect while glow is on (the application turns
screen-space reflections off while its depth of field is drawn).
