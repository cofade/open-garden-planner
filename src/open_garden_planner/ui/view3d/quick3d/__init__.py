"""The Qt Quick 3D engine package (Phase 17 L1.2, #385; ADR-048, concept §8.29.2).

The other side of ``core/scene3d``'s ``EngineSink``: ``SceneSync`` drives a
``Quick3DSink``, which tells a ``Quick3DHost`` (a ``QQuickView`` showing
``qml/Garden.qml``) what to create, pose, tint and destroy.

THE IMPORT RULE (pinned by ``tests/unit/test_quick3d_boundary.py``): this
package is the only place in the product that imports ``PyQt6.QtQuick3D``,
``PyQt6.QtQuick``, ``PyQt6.QtQml`` or ``PyQt6.QtQuickWidgets`` — and inside it
only the engine modules do:

==============  ======  =====================================================
module          engine  what it is
==============  ======  =====================================================
``adapter``     no      ``Quick3DSink`` + the ``EngineScene`` boundary it drives
``materials``   no      material kinds → QML part components; tint rule
``look``        no      a ``core.scene3d.look.LookSpec`` as the scene's properties (L1.4)
``shots``       no      camera placements as plain data; the top-down projection
``qt_messages`` no      Qt message capture — a shader or QML error fails a render
``selftest``    lazy    the frozen exe's 3D self-test (imports the engine in ``run``)
``geometry``    YES     ``QQuick3DGeometry`` fed from ``core.scene3d.engine_buffers``
``ground_tiles`` YES    the baked ground: one textured quad per tile (L1.5)
``host``        YES     ``Quick3DHost``: the view, the scene, grab, pick, camera
``offscreen``   YES     one hidden view → one ``QImage``; log and watchdog
==============  ======  =====================================================

Importing THIS module is free: it imports nothing and creates no Qt object, so
the app can name the package without paying for the engine. The engine loads
when ``host`` (or ``offscreen``) is imported — which the app does only when the
user first opens 3D (L1.3).
"""
