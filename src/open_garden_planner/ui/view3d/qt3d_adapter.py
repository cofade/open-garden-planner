"""Qt3D engine adapter (US-E6, #261) — the ONLY ``PyQt6.Qt3D*`` importer.

ADR-038's import boundary: if the engine is ever swapped, this file is the
blast radius. It packs the Qt-free ``core/scene3d`` triangle soup into GPU
buffers, owns the scene graph (ground plane, prisms, sun light, camera),
and exposes plain-Python instruments (``last_sun_scene`` /
``last_light_engine``) so tests can assert light updates without rendering.

MVP capability statement (FR-SUN-06): directional sun LIGHT only — Qt3D's
forward renderer has no out-of-the-box shadow mapping, so ground shadow
SHAPES remain the 2D overlay's job (US-E3); face shading direction here
must and does agree with it (pinned in ``tests/unit/test_scene3d.py``).
"""

from __future__ import annotations

import contextlib
import math

import numpy as np
from PyQt6.Qt3DCore import QAttribute, QBuffer, QEntity, QGeometry, QTransform
from PyQt6.Qt3DExtras import (
    QFirstPersonCameraController,
    QOrbitCameraController,
    QPhongMaterial,
    QPlaneMesh,
    Qt3DWindow,
)
from PyQt6.Qt3DRender import QDirectionalLight, QGeometryRenderer
from PyQt6.QtCore import QByteArray, Qt, QTimer
from PyQt6.QtGui import QColor, QVector3D
from PyQt6.QtWidgets import QWidget

from open_garden_planner.core.scene3d import (
    Scene3DRecord,
    extrude_footprint,
    sun_direction_scene,
    to_engine_frame,
)
from open_garden_planner.core.shadow_geometry import MIN_SUN_ELEVATION_DEG
from open_garden_planner.core.walk_camera import (
    EYE_HEIGHT_CM,
    PITCH_LIMIT_DEG,
    WALK_SPEED_CM_S,
    clamp_walk_position,
    look_direction,
    walk_step,
)

_SKY = QColor(168, 200, 228)
_GROUND = QColor(118, 148, 92)
_SUN_WARM = QColor(255, 249, 228)
_NIGHT_BLUE = QColor(150, 165, 210)

# Walk movement key groups (US-E7) — WASD and arrows are equivalent. Stored as
# plain ints (what QKeyEvent.key() yields) so set membership is hash-safe.
_WALK_FORWARD = frozenset({int(Qt.Key.Key_W), int(Qt.Key.Key_Up)})
_WALK_BACK = frozenset({int(Qt.Key.Key_S), int(Qt.Key.Key_Down)})
_WALK_RIGHT = frozenset({int(Qt.Key.Key_D), int(Qt.Key.Key_Right)})
_WALK_LEFT = frozenset({int(Qt.Key.Key_A), int(Qt.Key.Key_Left)})


def _scene_to_engine_array(triples: list[float]) -> np.ndarray:
    """(x, y=N, z=up) rows → engine (x, y=up, z=−N); float32 (n, 3).

    The mapping matrix has determinant +1 (a rotation), so triangle
    winding — and therefore face culling — survives unchanged.
    """
    scene = np.asarray(triples, dtype=np.float32).reshape(-1, 3)
    return np.column_stack([scene[:, 0], scene[:, 2], -scene[:, 1]]).astype(
        np.float32
    )


class Garden3DView:
    """Owns the Qt3DWindow and its scene graph; rebuildable from records."""

    def __init__(self) -> None:
        self._view = Qt3DWindow()
        self._view.defaultFrameGraph().setClearColor(_SKY)
        self._root = QEntity()
        self._content: QEntity | None = None
        self._container: QWidget | None = None

        light_entity = QEntity(self._root)
        self._light = QDirectionalLight()
        self._light.setColor(_SUN_WARM)
        self._light.setIntensity(1.0)
        light_entity.addComponent(self._light)

        camera = self._view.camera()
        camera.lens().setPerspectiveProjection(45.0, 16.0 / 9.0, 10.0, 200000.0)
        # Track the real surface size — a hardcoded aspect ratio renders
        # stretched at any non-16:9 window size (review P2).
        self._view.widthChanged.connect(self._update_aspect_ratio)
        self._view.heightChanged.connect(self._update_aspect_ratio)
        self._orbit_controller = QOrbitCameraController(self._root)
        self._orbit_controller.setCamera(camera)
        self._orbit_controller.setLinearSpeed(2500.0)
        self._orbit_controller.setLookSpeed(180.0)

        # Walkthrough (US-E7): the first-person controller drives mouse-LOOK
        # only. Its translation moves along the pitched view vector (looking
        # up lifts the walker + slows the ground pace) and binds arrows only,
        # so movement is our own horizontal loop — linearSpeed 0 disables its.
        self._walk_controller = QFirstPersonCameraController(self._root)
        self._walk_controller.setCamera(camera)
        self._walk_controller.setLinearSpeed(0.0)
        self._walk_controller.setLookSpeed(160.0)
        self._walk_controller.setEnabled(False)

        # Horizontal keyboard movement (WASD + arrows): a frame timer steps
        # the walker along the look's ground projection while keys are held.
        self._walk_keys: set[int] = set()
        self._walk_timer = QTimer()
        self._walk_timer.setInterval(16)  # ~60 fps
        self._walk_timer.timeout.connect(self._walk_move_tick)

        self._camera_mode = "orbit"
        self._saved_orbit: tuple[QVector3D, QVector3D, QVector3D] | None = None
        self._plan_size: tuple[float, float] = (1000.0, 800.0)

        self._view.setRootEntity(self._root)

        #: Test instruments — the last vectors applied (scene / engine frame).
        self.last_sun_scene: tuple[float, float, float] | None = None
        self.last_light_engine: tuple[float, float, float] | None = None
        #: Rebuild counter (test instrument).
        self.rebuild_count = 0

    # ── public API ─────────────────────────────────────────────

    def window_handle(self) -> Qt3DWindow:
        """The underlying Qt3DWindow — the real keyboard-focus target while
        walking (the container embeds a foreign QWindow, so key events land
        HERE, not on the ancestor widgets; review P1)."""
        return self._view

    def container(self, parent: QWidget | None = None) -> QWidget:
        """The embeddable window container (created once)."""
        if self._container is None:
            self._container = QWidget.createWindowContainer(self._view, parent)
            self._container.setMinimumSize(480, 320)
        return self._container

    def rebuild(
        self,
        records: list[Scene3DRecord],
        width_cm: float,
        height_cm: float,
    ) -> None:
        """Replace the content subtree from a fresh snapshot."""
        if self._content is not None:
            self._content.setParent(None)
            self._content.deleteLater()
        content = QEntity(self._root)

        ground = QEntity(content)
        ground_mesh = QPlaneMesh()
        ground_mesh.setWidth(width_cm)
        ground_mesh.setHeight(height_cm)
        ground_transform = QTransform()
        # QPlaneMesh lies in the engine XZ plane; scene center (w/2, h/2)
        # maps to engine (w/2, 0, −h/2).
        ground_transform.setTranslation(
            QVector3D(width_cm / 2.0, 0.0, -height_cm / 2.0)
        )
        ground_material = QPhongMaterial()
        ground_material.setDiffuse(_GROUND)
        ground.addComponent(ground_mesh)
        ground.addComponent(ground_transform)
        ground.addComponent(ground_material)

        for record in records:
            self._add_prism(content, record)

        self._content = content
        self._plan_size = (width_cm, height_cm)
        if self._camera_mode == "orbit":
            self._frame_camera(width_cm, height_cm)
        else:
            # Refreshing onto a smaller plan must not strand the walker
            # outside the new bounds (review P2) — re-clamp immediately.
            self._clamp_walk_camera()
        self.rebuild_count += 1

    def set_sun(self, elevation_deg: float, azimuth_deg: float) -> None:
        """Point the directional light along the US-E1 solar vector.

        Below the horizon: a dim, bluish overhead light so the plan stays
        readable at night (documented MVP behavior, FR-SUN-06).
        """
        self.last_sun_scene = sun_direction_scene(elevation_deg, azimuth_deg)
        # One horizon definition for 2D and 3D: below the shadow module's
        # minimum the 2D overlay shows night, so the 3D light does too.
        if elevation_deg < MIN_SUN_ELEVATION_DEG:
            engine = (0.15, -1.0, 0.1)
            self._light.setColor(_NIGHT_BLUE)
            self._light.setIntensity(0.35)
        else:
            sun_e, sun_n, sun_up = self.last_sun_scene
            # Light TRAVELS away from the sun — negate, then map frames once.
            engine = to_engine_frame(-sun_e, -sun_n, -sun_up)
            self._light.setColor(_SUN_WARM)
            self._light.setIntensity(1.0)
        self._light.setWorldDirection(QVector3D(*engine))
        self.last_light_engine = engine

    # ── walkthrough camera mode (US-E7) ─────────────────────────────

    @property
    def camera_mode(self) -> str:
        return self._camera_mode

    def set_camera_mode(self, mode: str) -> None:
        """Switch orbit ⇄ walk. Walk pins the eye at EYE_HEIGHT_CM on the
        (flat) ground and clamps to plan bounds + margin; leaving walk
        restores the orbit camera exactly as it was (issue #262 gate)."""
        if mode == self._camera_mode:
            return
        camera = self._view.camera()
        if mode == "walk":
            self._saved_orbit = (
                camera.position(),
                camera.viewCenter(),
                camera.upVector(),
            )
            self._orbit_controller.setEnabled(False)
            width_cm, height_cm = self._plan_size
            east, north = clamp_walk_position(
                camera.position().x(), -camera.position().z(),
                width_cm, height_cm,
            )
            position = QVector3D(east, EYE_HEIGHT_CM, -north)
            camera.setPosition(position)
            # Look toward the plan center at eye level — a defined start.
            camera.setViewCenter(
                QVector3D(width_cm / 2.0, EYE_HEIGHT_CM, -height_cm / 2.0)
            )
            camera.setUpVector(QVector3D(0.0, 1.0, 0.0))
            camera.positionChanged.connect(self._clamp_walk_camera)
            camera.viewCenterChanged.connect(self._clamp_walk_view)
            self._walk_controller.setEnabled(True)
            self._walk_keys.clear()
            self._walk_timer.start()
            self._camera_mode = "walk"
        else:
            with contextlib.suppress(TypeError):
                camera.positionChanged.disconnect(self._clamp_walk_camera)
            with contextlib.suppress(TypeError):
                camera.viewCenterChanged.disconnect(self._clamp_walk_view)
            self._walk_controller.setEnabled(False)
            self._walk_timer.stop()
            self._walk_keys.clear()
            if self._saved_orbit is not None:
                position, view_center, up_vector = self._saved_orbit
                camera.setPosition(position)
                camera.setViewCenter(view_center)
                camera.setUpVector(up_vector)
            self._orbit_controller.setEnabled(True)
            self._camera_mode = "orbit"

    def _clamp_walk_camera(self) -> None:
        """Keep the walker at eye height inside the plan (+margin).

        Re-entrancy safe: the corrected position satisfies the clamp, so
        the second positionChanged emission changes nothing.
        """
        camera = self._view.camera()
        position = camera.position()
        width_cm, height_cm = self._plan_size
        east, north = clamp_walk_position(
            position.x(), -position.z(), width_cm, height_cm
        )
        corrected = QVector3D(east, EYE_HEIGHT_CM, -north)
        if corrected != position:
            camera.setPosition(corrected)

    def _clamp_walk_view(self) -> None:
        """Enforce the ±89° pitch limit on the walk look direction.

        QFirstPersonCameraController tilts without any limit; this slot is
        what makes core/walk_camera's pitch rule REAL at runtime (review
        P1): when the look pitch exceeds the limit, the view center is
        re-projected through ``look_direction`` (which clamps). Re-entrancy
        safe — the corrected pitch satisfies the limit, so the second
        emission returns early.
        """
        camera = self._view.camera()
        position = camera.position()
        look = camera.viewCenter() - position
        east, north, up = look.x(), -look.z(), look.y()
        horizontal = math.hypot(east, north)
        distance = math.sqrt(east * east + north * north + up * up)
        if distance <= 1e-6:
            return
        pitch = math.degrees(math.atan2(up, horizontal))
        if abs(pitch) <= PITCH_LIMIT_DEG:
            return
        yaw = math.degrees(math.atan2(east, north))
        new_e, new_n, new_up = look_direction(yaw, pitch)
        camera.setViewCenter(
            position
            + QVector3D(new_e * distance, new_up * distance, -new_n * distance)
        )

    def walk_key_press(self, key: int) -> None:
        """Register a held movement key (forwarded from the window's event
        filter on the Qt3D window — the real keyboard-focus target)."""
        self._walk_keys.add(int(key))

    def walk_key_release(self, key: int) -> None:
        self._walk_keys.discard(int(key))

    def walk_clear_keys(self) -> None:
        """Drop all held movement keys — e.g. the 3D window lost focus, so the
        KeyRelease for a held key will never arrive (would strand the walker
        drifting until the next mode toggle)."""
        self._walk_keys.clear()

    def _walk_move_tick(self) -> None:
        """Advance the walker one frame from the held keys — HORIZONTAL only.

        Moves position AND viewCenter by the same ground delta so the look
        direction is preserved (no tilt when walking while pitched), then
        clamps to plan bounds + eye height. WASD and arrows are equivalent,
        and speed is independent of pitch.
        """
        keys = self._walk_keys
        if not keys:
            return
        forward = bool(keys & _WALK_FORWARD) - bool(keys & _WALK_BACK)
        strafe = bool(keys & _WALK_RIGHT) - bool(keys & _WALK_LEFT)
        if forward == 0 and strafe == 0:
            return
        camera = self._view.camera()
        position = camera.position()
        look = camera.viewCenter() - position
        yaw = math.degrees(math.atan2(look.x(), -look.z()))
        distance = WALK_SPEED_CM_S * (self._walk_timer.interval() / 1000.0)
        width_cm, height_cm = self._plan_size
        east, north = walk_step(
            position.x(), -position.z(), yaw, forward, strafe, distance
        )
        east, north = clamp_walk_position(east, north, width_cm, height_cm)
        new_position = QVector3D(east, EYE_HEIGHT_CM, -north)
        delta = new_position - position
        if delta.isNull():
            return
        camera.setPosition(new_position)
        camera.setViewCenter(camera.viewCenter() + delta)

    # ── internals ──────────────────────────────────────────────

    def _add_prism(self, parent: QEntity, record: Scene3DRecord) -> None:
        positions, normals = extrude_footprint(
            list(record.footprint), record.height_cm, base_cm=record.base_cm
        )
        if not positions:
            return
        pos_engine = _scene_to_engine_array(positions)
        nor_engine = _scene_to_engine_array(normals)
        vertex_count = pos_engine.shape[0]
        interleaved = np.hstack([pos_engine, nor_engine]).astype(np.float32)

        entity = QEntity(parent)
        geometry = QGeometry(entity)
        buffer = QBuffer(geometry)
        buffer.setData(QByteArray(interleaved.tobytes()))

        stride = 6 * 4  # 6 floats per vertex
        position_attribute = QAttribute(geometry)
        position_attribute.setName(QAttribute.defaultPositionAttributeName())
        position_attribute.setVertexBaseType(QAttribute.VertexBaseType.Float)
        position_attribute.setVertexSize(3)
        position_attribute.setAttributeType(
            QAttribute.AttributeType.VertexAttribute
        )
        position_attribute.setBuffer(buffer)
        position_attribute.setByteStride(stride)
        position_attribute.setByteOffset(0)
        position_attribute.setCount(vertex_count)
        geometry.addAttribute(position_attribute)

        normal_attribute = QAttribute(geometry)
        normal_attribute.setName(QAttribute.defaultNormalAttributeName())
        normal_attribute.setVertexBaseType(QAttribute.VertexBaseType.Float)
        normal_attribute.setVertexSize(3)
        normal_attribute.setAttributeType(
            QAttribute.AttributeType.VertexAttribute
        )
        normal_attribute.setBuffer(buffer)
        normal_attribute.setByteStride(stride)
        normal_attribute.setByteOffset(3 * 4)
        normal_attribute.setCount(vertex_count)
        geometry.addAttribute(normal_attribute)

        renderer = QGeometryRenderer(entity)
        renderer.setGeometry(geometry)
        renderer.setPrimitiveType(QGeometryRenderer.PrimitiveType.Triangles)
        renderer.setVertexCount(vertex_count)

        material = QPhongMaterial(entity)
        r, g, b, _a = record.color_rgba
        material.setDiffuse(QColor(r, g, b))
        # Lift ambient toward the diffuse so unlit faces read as shaded
        # surfaces, not black holes.
        material.setAmbient(QColor(int(r * 0.35), int(g * 0.35), int(b * 0.35)))

        entity.addComponent(renderer)
        entity.addComponent(material)

    def _update_aspect_ratio(self) -> None:
        width, height = self._view.width(), self._view.height()
        if width > 0 and height > 0:
            self._view.camera().setAspectRatio(width / height)

    def _frame_camera(self, width_cm: float, height_cm: float) -> None:
        center = QVector3D(width_cm / 2.0, 0.0, -height_cm / 2.0)
        diagonal = max(float(np.hypot(width_cm, height_cm)), 500.0)
        camera = self._view.camera()
        camera.setPosition(
            center + QVector3D(diagonal * 0.55, diagonal * 0.5, diagonal * 0.6)
        )
        camera.setViewCenter(center)
        camera.setUpVector(QVector3D(0.0, 1.0, 0.0))
