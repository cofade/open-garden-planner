# 3D Engine & Scene Pitfalls (PF-E3D)

| ID | Rule | Status | Where | Legacy |
|---|---|---|---|---|
| PF-E3D-01 | Retired: each open of the 3D view built a fresh `Qt3DWindow`, because a hidden and re-shown one rendered blank, and the code no longer follows this since the Qt 3D window is gone. | retired | [10](../10-3d-engine-scene.md#pf-e3d-01) |  |
| PF-E3D-02 | Retired: the Qt 3D walk read keys through an event filter on the embedded `Qt3DWindow`, whose key events never reach the `QMainWindow`, and the code no longer follows this since that window is gone. | retired | [10](../10-3d-engine-scene.md#pf-e3d-02) |  |
| PF-E3D-03 | Retired: the Qt 3D walk used `QFirstPersonCameraController` for mouse-look only and moved the walker itself, because the controller free-flies, and the code no longer follows this since Qt 3D is gone. | retired | [10](../10-3d-engine-scene.md#pf-e3d-03) |  |
| PF-E3D-04 | Tooling that must run headless writes its own timestamped log, per-phase metrics and a `faulthandler` watchdog, because without timestamps a slow run and a hung run look the same. | standing | [10](../10-3d-engine-scene.md#pf-e3d-04) | 11.4.5 |
| PF-E3D-05 | Every scene-record length is snapped to 1e-7 cm and every signature match is confirmed by comparing the values, so float dust cannot invent an edit and a hash collision cannot hide one. | standing | [10](../10-3d-engine-scene.md#pf-e3d-05) | 11.4.14 |
| PF-E3D-06 | Whether a Qt Quick frame can be had is read from the frame itself, its size within half a device pixel of the window's, not inferred from Qt's window predicates, and no Python Qt message handler runs beside a shown window. | standing | [10](../10-3d-engine-scene.md#pf-e3d-06) | 11.4.15 |
| PF-E3D-07 | A memory soak takes no frame inside its measured loop, only one before and one after, and a test waits for the condition the product itself waits for, never for a guessed duration. | standing | [10](../10-3d-engine-scene.md#pf-e3d-07) | 11.4.16 |
| PF-E3D-08 | Anything that comes and goes in the 3D pane is a resize of the view, so its room is reserved, and a walk-mode key filter owns a key only if it claims it at `ShortcutOverride`. | standing | [10](../10-3d-engine-scene.md#pf-e3d-08) | 11.4.19 |
| PF-E3D-09 | Measure the unchanged code before crediting a change with a difference, and after merging into a removal scan the whole merged tree for every removed name, not only the files that conflicted. | standing | [10](../10-3d-engine-scene.md#pf-e3d-09) | 11.4.20 |
| PF-E3D-10 | Derived lifetime visibility must preserve the existing throttled 3D clock path while real plan edits still announce revisions. | standing | [10](../10-3d-engine-scene.md#pf-e3d-10) |  |
