"""Qt3D spike window (US-E5, #260) — EVIDENCE, NOT PRODUCTION CODE.

Renders a real ``.ogp`` plan (a generated demo plan saved + reloaded
through ``ProjectManager``, or ``--spike-plan <file.ogp>``) as lit,
extruded boxes on a ground plane, with:

- one box per shadow caster (US-E2 heights × US-E3 footprint bboxes),
- a directional sun light from the US-E1 solar vector (Berlin, Jun 21
  12:00 UTC — the campaign's pinned instant),
- a slow scene rotation (proves live rendering, not a stale frame),
- an orbit camera controller.

Machine-checkable evidence flags:
    --spike-screenshot <path>   grab the window into a PNG after ~4 s
    --spike-autoclose <secs>    quit(0) automatically (frozen-exe gate)

Coordinate mapping (documented for ADR-038): scene (x=E, y=N, cm, ADR-002)
→ Qt3D default Y-up frame as (x=E, y=up, z=−N). A solar unit vector
(sE, sN, sUp) therefore becomes (sE, sUp, −sN) and the LIGHT's world
direction is its negation (light travels away from the sun).
"""

from __future__ import annotations

import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def _arg_value(argv: list[str], flag: str) -> str | None:
    if flag in argv:
        index = argv.index(flag)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None


def _build_demo_plan(scene) -> None:
    """A small but real garden: house, shed, greenhouse, fence, wall,
    trees, raised bed — every US-E2 height source represented."""
    from PyQt6.QtCore import QPointF

    from open_garden_planner.core.object_height import METADATA_KEY
    from open_garden_planner.core.object_types import ObjectType
    from open_garden_planner.ui.canvas.items.circle_item import CircleItem
    from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
    from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
    from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

    house = PolygonItem(
        vertices=[
            QPointF(200, 1400), QPointF(1100, 1400),
            QPointF(1100, 2000), QPointF(200, 2000),
        ],
        object_type=ObjectType.HOUSE,
    )
    scene.addItem(house)
    shed = RectangleItem(2600, 1700, 300, 250, object_type=ObjectType.TOOL_SHED)
    scene.addItem(shed)
    greenhouse = RectangleItem(
        2500, 400, 400, 250, object_type=ObjectType.GREENHOUSE
    )
    scene.addItem(greenhouse)
    fence = PolylineItem(
        [QPointF(50, 50), QPointF(2950, 50), QPointF(2950, 1000)],
        object_type=ObjectType.FENCE,
    )
    scene.addItem(fence)
    wall = PolylineItem(
        [QPointF(50, 50), QPointF(50, 2000)], object_type=ObjectType.WALL
    )
    scene.addItem(wall)
    bed = RectangleItem(1500, 300, 400, 200, object_type=ObjectType.RAISED_BED)
    scene.addItem(bed)
    for cx, cy, radius, height in (
        (1800, 1500, 220, 700.0),
        (600, 700, 150, 450.0),
    ):
        tree = CircleItem(cx, cy, radius, object_type=ObjectType.TREE)
        tree.metadata[METADATA_KEY] = height
        scene.addItem(tree)


def run_spike(argv: list[str]) -> int:
    """Open the spike window; returns the process exit code."""
    try:
        from PyQt6.Qt3DCore import QEntity  # noqa: F401 — availability probe
    except ImportError:
        sys.stderr.write(
            "3D spike unavailable: this build has no PyQt6-3D "
            "(install PyQt6-3D==6.11.0 PyQt6-3D-Qt6==6.11.0). See ADR-038.\n"
        )
        return 2
    from PyQt6.Qt3DCore import QEntity, QTransform
    from PyQt6.Qt3DExtras import (
        QCuboidMesh,
        QOrbitCameraController,
        QPhongMaterial,
        QPlaneMesh,
        Qt3DWindow,
    )
    from PyQt6.Qt3DRender import QDirectionalLight
    from PyQt6.QtCore import QPropertyAnimation, QTimer
    from PyQt6.QtGui import QColor, QGuiApplication, QVector3D
    from PyQt6.QtWidgets import QApplication

    from open_garden_planner.core import ProjectManager
    from open_garden_planner.core.solar import solar_position
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.canvas.sun_shadow_controller import (
        collect_shadow_casters,
    )

    app = QApplication(argv)

    # ── casters from a REAL .ogp (save+reload round trip, or a user plan) ─
    plan_arg = _arg_value(argv, "--spike-plan")
    scene = CanvasScene(3000.0, 2000.0)
    manager = ProjectManager()
    if plan_arg and Path(plan_arg).is_file():
        manager.load(scene, Path(plan_arg))
    else:
        _build_demo_plan(scene)
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "spike_demo.ogp"
            manager.save(scene, plan_path)
            scene.clear()
            manager.load(scene, plan_path)
    casters = collect_shadow_casters(scene)

    # ── 3D scene ────────────────────────────────────────────────
    view = Qt3DWindow()
    view.defaultFrameGraph().setClearColor(QColor(150, 185, 220))
    root = QEntity()

    # Slow rotation of everything — proves live rendering in the screenshot
    # era (a hung pipeline would show the initial angle).
    spin = QEntity(root)
    spin_transform = QTransform()
    spin.addComponent(spin_transform)
    # Parent = spin_transform only for LIFETIME; the target is set below.
    animation = QPropertyAnimation(spin_transform)
    animation.setTargetObject(spin_transform)
    animation.setPropertyName(b"rotationY")
    animation.setStartValue(0.0)
    animation.setEndValue(360.0)
    animation.setDuration(30000)
    animation.setLoopCount(-1)
    animation.start()

    width_cm, height_cm = scene.width_cm, scene.height_cm
    center = QVector3D(width_cm / 2.0, 0.0, -height_cm / 2.0)

    ground_entity = QEntity(spin)
    ground_mesh = QPlaneMesh()
    ground_mesh.setWidth(width_cm)
    ground_mesh.setHeight(height_cm)
    ground_transform = QTransform()
    ground_transform.setTranslation(center)
    ground_material = QPhongMaterial()
    ground_material.setDiffuse(QColor(120, 150, 90))  # lawn green
    ground_entity.addComponent(ground_mesh)
    ground_entity.addComponent(ground_transform)
    ground_entity.addComponent(ground_material)

    box_color = QColor(184, 134, 90)  # warm wood tone
    for footprint, height in casters:
        xs = [p[0] for p in footprint]
        ys = [p[1] for p in footprint]
        w = max(xs) - min(xs)
        d = max(ys) - min(ys)
        if w <= 0 or d <= 0 or height <= 0:  # casters always carry a height
            continue
        cx = (max(xs) + min(xs)) / 2.0
        cy = (max(ys) + min(ys)) / 2.0
        entity = QEntity(spin)
        mesh = QCuboidMesh()
        mesh.setXExtent(w)
        mesh.setYExtent(height)
        mesh.setZExtent(d)
        transform = QTransform()
        # Scene (E, N) → Qt3D (x, −z); base sits on the ground plane.
        transform.setTranslation(QVector3D(cx, height / 2.0, -cy))
        material = QPhongMaterial()
        material.setDiffuse(box_color)
        entity.addComponent(mesh)
        entity.addComponent(transform)
        entity.addComponent(material)

    # ── sun light from the US-E1 engine (pinned campaign instant) ────────
    import math

    position = solar_position(52.52, 13.405, datetime(2026, 6, 21, 12, 0, tzinfo=UTC))
    elev = math.radians(position.elevation_deg)
    az = math.radians(position.azimuth_deg)
    sun_e = math.cos(elev) * math.sin(az)
    sun_n = math.cos(elev) * math.cos(az)
    sun_up = math.sin(elev)
    light_entity = QEntity(root)
    light = QDirectionalLight()
    light.setColor(QColor(255, 250, 230))
    light.setIntensity(1.0)
    # (E, N, up) → (x, y=up, z=−N); light travels opposite the sun vector.
    light.setWorldDirection(QVector3D(-sun_e, -sun_up, sun_n))
    light_entity.addComponent(light)

    # ── camera ──────────────────────────────────────────────────
    camera = view.camera()
    camera.lens().setPerspectiveProjection(45.0, 16.0 / 9.0, 10.0, 100000.0)
    camera.setPosition(center + QVector3D(2500.0, 2200.0, 2800.0))
    camera.setViewCenter(center)
    controller = QOrbitCameraController(root)
    controller.setCamera(camera)
    controller.setLinearSpeed(2000.0)
    controller.setLookSpeed(180.0)

    view.setRootEntity(root)
    view.setTitle("OGP 3D Spike (US-E5) — NOT A PRODUCT FEATURE")
    view.resize(960, 600)
    view.show()

    # ── machine-checkable evidence ──────────────────────────────────
    screenshot_path = _arg_value(argv, "--spike-screenshot")
    if screenshot_path:
        def grab() -> None:
            screen = QGuiApplication.primaryScreen()
            pixmap = screen.grabWindow(view.winId())
            ok = pixmap.save(screenshot_path, "PNG")
            sys.stderr.write(f"SPIKE_SCREENSHOT saved={ok} path={screenshot_path}\n")

        QTimer.singleShot(4000, grab)

    autoclose = _arg_value(argv, "--spike-autoclose")
    if autoclose:
        QTimer.singleShot(int(float(autoclose) * 1000), lambda: app.exit(0))

    return app.exec()
