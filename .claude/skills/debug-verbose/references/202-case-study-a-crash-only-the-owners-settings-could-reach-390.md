# Case study: a crash only the owner's settings could reach (#390)

**Symptom.** The owner's exe died on the first click in the 3D view with photo mode on and the blur
slider at its maximum: twice, 4 hours apart, with a Windows "access violation in d3d11.dll" and nothing in
`app.log`. In the same sessions the slider seemed to do nothing at all ("I see no difference between a high
and a low blur"). A probe run from source did not die in about 400 clicks, 300 random actions and a slider soak.

**Wrong theories.** (1) The frozen exe differs from the source (a missing shader or QML file in the
bundle): the bundle holds the same Helpers and the same plugin DLLs, and the shaders live inside them.
(2) The probe's window sat behind everything and did not really render: forcing it to the front changed
nothing. (3) The second `View3D` shares the environment and corrupts it: no capture had run. (4) The
selection code on a raised bed: photo mode swallows the click, so it only sets a focus.

**Key evidence.** Both minidumps faulted at `d3d11.dll+0x158c32`. Microsoft's public `d3d11.pdb` (GUID and
age from the DLL's CodeView record, `urllib` to a local folder) and `dbghelp.dll` through `ctypes` named it:
`CContext::OMSetRenderTargets+0x2e2`, a read at 0x16d: Qt handed D3D a render target whose resource was
already released. That pointed at the effect chain, and the owner's registry said what the probe's isolated
profile did not: `view3d/quality = ultra`. The same probe at Ultra died at the first click (3 of 3).

| Ultra with one ingredient changed, photo mode on, blur at maximum | First click |
|---|---|
| unchanged | crash |
| reflections off | survives (4 of 4) |
| glow off (both kinds) | survives (4 of 4) |
| occlusion off, 4x instead of 8x MSAA, FXAA, a smaller shadow map, fewer cascades, PCF 16 | crash |
| photo mode off, 20 clicks on the beds | survives |
| medium, high | survives |

**Root cause.** Reflections, depth of field and glow in one `ExtendedSceneEnvironment` chain on Qt 6.12.0
with Direct3D 11. Only Ultra has reflections, and only photo mode turns the blur on. The second symptom
had its own cause: there is no depth of field without a focused point (`PhotoSettings.depth_of_field`),
so the slider drew nothing until the view was clicked, and that click was the crash.

**Fix.** `Garden.qml`: reflections stand down while the blur is drawn. `workspace_capture.py`: the first
blur above 0 focuses what the camera looks at. The render tier's `ultra_blur` scenario dies without the
gate and passes with it (no result file is the failure).

**Lesson.** A probe that isolates the profile runs on the defaults, and a bug that needs one non-default
setting is invisible to it: before declaring "not reproducible", read the reporter's real settings (the
registry, read-only) and run the probe on them. Name a native crash from its minidump first (public PDB
through `dbghelp`, no debugger), then bisect one ingredient at a time. Two complaints in one session were
two causes. A screen grab of the desktop catches whatever else is on screen: measure the engine's own
`grabWindow`, never the desktop.
