---
name: ogp-3d-renderer
description: "Measured facts and runbook for Open Garden Planner's Qt Quick 3D renderer (Phase 17, ADR-048; production package ui/view3d/quick3d/ since L1.2; the L0 spike it was measured in, src/open_garden_planner/spike_q3d/, was deleted in L1.10). Load when: writing or debugging anything that imports QtQuick3D/QtQuick/QtQml/QtQuickWidgets; feeding numpy geometry or textures to the engine; placing the sun, sky, shadows or camera; choosing render presets or post effects; hosting a View3D in a QQuickWidget or QQuickView; picking; taking screenshots or offscreen renders; rendering in CI (xvfb + Mesa, Windows WARP); packaging Qt Quick 3D in the PyInstaller exe; or when a 3D frame is black, white, mirrored, washed out, slow or seems to hang. Only facts measured in this repo, each with where and how it was measured."
---

# ogp-3d-renderer reference guide

Read the scope/introduction and the relevant reference below **before acting**.
All rules in the references remain binding. Read method/runbook sections for
the task; load historical case studies only when the symptom matches. Search
the index by subsystem, issue or symptom. Do not infer current delivery status
from dated measurements. New lessons belong in a new reference and index row.

| Topic / symptom | Reference |
|---|---|
| Qt Quick 3D renderer — measured facts and runbook | [Read](references/000-qt-quick-3d-renderer-measured-facts-and-runbook.md) |
| 1. Boundary rules (pinned by tests) | [Read](references/001-1-boundary-rules-pinned-by-tests.md) |
| 2. PyQt6 6.11 binding facts | [Read](references/002-2-pyqt6-6-11-binding-facts.md) |
| 3. Frame and geometry | [Read](references/003-3-frame-and-geometry.md) |
| 4. Light, sky, shadows | [Read](references/004-4-light-sky-shadows.md) |
| 5. Ground texture | [Read](references/005-5-ground-texture.md) |
| 6. Hosts | [Read](references/006-6-hosts.md) |
| 7. Picking | [Read](references/007-7-picking.md) |
| 8. Screenshots and CI rendering | [Read](references/008-8-screenshots-and-ci-rendering.md) |
| 9. Packaging (PyInstaller) | [Read](references/009-9-packaging-pyinstaller.md) |
| 10. CPU-side baselines (not engine) | [Read](references/010-10-cpu-side-baselines-not-engine.md) |
| 11. Symptom → cause (spike chronicle) | [Read](references/011-11-symptom-cause-spike-chronicle.md) |
| 12. The production package — `ui/view3d/quick3d/` (L1.2) | [Read](references/012-12-the-production-package-ui-view3d-quick3d-l1-2.md) |
| 13. The engine inside the app — the workspace (L1.3) | [Read](references/013-13-the-engine-inside-the-app-the-workspace-l1-3.md) |
| 14. Looks, sky and wind on the engine (L1.4) | [Read](references/014-14-looks-sky-and-wind-on-the-engine-l1-4.md) |
| 15. Selection, picking in perspective, walk mode (L1.8) | [Read](references/015-15-selection-picking-in-perspective-walk-mode-l1-8.md) |
| 16. Analyze in 3D on the engine (L2) | [Read](references/016-16-analyze-in-3d-on-the-engine-l2.md) |
| 17. The built world complete on the engine (L4) | [Read](references/017-17-the-built-world-complete-on-the-engine-l4.md) |

The host state contract is owned by `ui/view3d/quick3d/lifecycle.py`.
