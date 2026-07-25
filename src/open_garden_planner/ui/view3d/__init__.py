"""3D view of the garden plan (US-E6, #261; engine: PyQt6-3D per ADR-038).

Import discipline: ``qt3d_adapter`` is the ONLY module in the codebase that
may import ``PyQt6.Qt3D*`` — the engine-swap insurance ADR-038 demands.
Everything heavy (triangulation, extrusion, solar vectors, frame mapping)
is Qt-free in ``core/scene3d.py``; the collector (``snapshot.py``) turns
live canvas items into plain-data records on the GUI thread.

The whole package is imported LAZILY (menu action / sim-time forwarding),
never at app startup.
"""
