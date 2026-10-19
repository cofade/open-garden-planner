"""3D views of the garden plan.

Two generations live here until Phase 17 L1.10 removes the first:

- **The retired "3D View…" window** (US-E6, #261; engine: PyQt6-3D per ADR-038;
  reachable from no menu since L1.9):
  ``view3d_window`` and ``qt3d_adapter`` — the ONLY module in the codebase that
  may import ``PyQt6.Qt3D*``.
- **The 3D workspace** (Phase 17 L1.3, ADR-065), the plan area of every main
  window since L1.9: ``workspace`` (Plan / 3D / Split in the main window),
  ``sync_controller`` (the pipeline's controller), ``orbit_input``, ``init_guard``, ``problems_dialog`` — none of
  which imports an engine — and the engine package ``quick3d/`` (ADR-048), the
  ONLY importer of ``PyQt6.QtQuick3D`` / ``QtQuick`` / ``QtQml``.

``snapshot.py`` turns live canvas items into plain-data records on the GUI thread
for both. Everything heavy (triangulation, builders, solar vectors, frame mapping,
the camera) is Qt-free in ``core/scene3d/``.

Import discipline: importing this package is free (this docstring). At start-up the
main window imports ``workspace`` — which imports no engine — and the engine itself
is loaded on the first switch to 3D or Split (``Workspace.engine_factory``).
"""
