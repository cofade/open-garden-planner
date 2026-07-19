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

import numpy as np
from PyQt6.Qt3DCore import QAttribute, QBuffer, QEntity, QGeometry, QTransform
from PyQt6.Qt3DExtras import (
    QOrbitCameraController,
    QPhongMaterial,
    QPlaneMesh,
    Qt3DWindow,
)
from PyQt6.Qt3DRender import QDirectionalLight, QGeometryRenderer
from PyQt6.QtCore import QByteArray
from PyQt6.QtGui import QColor, QVector3D
from PyQt6.QtWidgets import QWidget

from open_garden_planner.core.scene3d import (
    Scene3DRecord,
    extrude_footprint,
    sun_direction_scene,
    to_engine_frame,
)

_SKY = QColor(168, 200, 228)
_GROUND = QColor(118, 148, 92)
_SUN_WARM = QColor(255, 249, 228)
_NIGHT_BLUE = QColor(150, 165, 210)


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
        controller = QOrbitCameraController(self._root)
        controller.setCamera(camera)
        controller.setLinearSpeed(2500.0)
        controller.setLookSpeed(180.0)

        self._view.setRootEntity(self._root)

        #: Test instruments — the last vectors applied (scene / engine frame).
        self.last_sun_scene: tuple[float, float, float] | None = None
        self.last_light_engine: tuple[float, float, float] | None = None
        #: Rebuild counter (test instrument).
        self.rebuild_count = 0

    # ── public API ─────────────────────────────────────────────

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
        self._frame_camera(width_cm, height_cm)
        self.rebuild_count += 1

    def set_sun(self, elevation_deg: float, azimuth_deg: float) -> None:
        """Point the directional light along the US-E1 solar vector.

        Below the horizon: a dim, bluish overhead light so the plan stays
        readable at night (documented MVP behavior, FR-SUN-06).
        """
        self.last_sun_scene = sun_direction_scene(elevation_deg, azimuth_deg)
        if elevation_deg <= 0.0:
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

    # ── internals ──────────────────────────────────────────────

    def _add_prism(self, parent: QEntity, record: Scene3DRecord) -> None:
        positions, normals = extrude_footprint(
            list(record.footprint), record.height_cm
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

    def _frame_camera(self, width_cm: float, height_cm: float) -> None:
        center = QVector3D(width_cm / 2.0, 0.0, -height_cm / 2.0)
        diagonal = max(float(np.hypot(width_cm, height_cm)), 500.0)
        camera = self._view.camera()
        camera.setPosition(
            center + QVector3D(diagonal * 0.55, diagonal * 0.5, diagonal * 0.6)
        )
        camera.setViewCenter(center)
        camera.setUpVector(QVector3D(0.0, 1.0, 0.0))
