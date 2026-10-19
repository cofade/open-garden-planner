"""The 3D view of the garden plan (Phase 17, ADR-048 / ADR-059 / ADR-060).

- **The workspace** (L1.3, ADR-060), the plan area of every main window since L1.9:
  ``workspace`` (Plan / 3D / Split in the main window), ``sync_controller`` (the
  pipeline's controller), ``orbit_input``, ``init_guard``, ``problems_dialog``,
  ``look_controller``, ``selection_bridge``, ``info_card``, ``walk_mode`` — none of
  which imports an engine.
- **The engine package** ``quick3d/`` (ADR-048): the ONLY importer of
  ``PyQt6.QtQuick3D`` / ``QtQuick`` / ``QtQml``.

``snapshot.py`` turns live canvas items into plain-data records on the GUI thread.
Everything heavy (triangulation, builders, solar vectors, frame mapping, the camera)
is Qt-free in ``core/scene3d/``. (The US-E6 "3D View…" window on Qt 3D, ADR-038, and
its adapter lived here until L1.10 deleted them.)

Import discipline: importing this package is free (this docstring). At start-up the
main window imports ``workspace`` — which imports no engine — and the engine itself
is loaded on the first switch to 3D or Split (``Workspace.engine_factory``).
"""
