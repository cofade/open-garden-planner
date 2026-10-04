"""The spike's ONLY Qt Quick 3D import module (ADR-047, Phase 17 L0).

Owns the engine side: numpy → ``QQuick3DGeometry``, ``QImage`` →
``QQuick3DTextureData``, the two candidate hosts (``QQuickView`` and
``QQuickWidget``), sun/camera placement, frame waiting, screenshots and the
render-side metrics. The scene → engine frame mapping happens here, exactly
once (``core.scene3d.to_engine_frame``: x = E, y = up, z = −N).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QByteArray, QEventLoop, QObject, QSize, QTimer, QUrl, pyqtProperty
from PyQt6.QtGui import QColor, QImage, QQuaternion, QVector3D
from PyQt6.QtQuick import QQuickView, QQuickWindow
from PyQt6.QtQuick3D import QQuick3DGeometry, QQuick3DTextureData
from PyQt6.QtQuickWidgets import QQuickWidget

from open_garden_planner.spike_q3d.meshes import MeshData

QML_DIR = Path(__file__).resolve().parent / "qml"

_SEM = QQuick3DGeometry.Attribute.Semantic
_F32 = QQuick3DGeometry.Attribute.ComponentType.F32Type
_U32 = QQuick3DGeometry.Attribute.ComponentType.U32Type


def to_engine(points: np.ndarray) -> np.ndarray:
    """Scene (E, N, up) → engine (E, up, −N); determinant +1 keeps winding."""
    out = np.empty_like(points, dtype=np.float32)
    out[:, 0] = points[:, 0]
    out[:, 1] = points[:, 2]
    out[:, 2] = -points[:, 1]
    return out


def vec_to_engine(east: float, north: float, up: float) -> QVector3D:
    return QVector3D(float(east), float(up), float(-north))


class NumpyGeometry(QQuick3DGeometry):
    """Interleaved float32 pos/normal/colour/uv + uint32 indices from a MeshData."""

    STRIDE = 12 * 4

    def __init__(self, mesh: MeshData, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.upload_ms = 0.0
        self.mesh = mesh
        self.set_mesh(mesh)

    def set_mesh(self, mesh: MeshData) -> None:
        t0 = time.perf_counter()
        self.mesh = mesh  # kept for the CPU pick oracle (probes.pick_probe)
        pos = to_engine(mesh.positions)
        nrm = to_engine(mesh.normals)
        vb = np.empty((mesh.vertex_count, 12), np.float32)
        vb[:, 0:3] = pos
        vb[:, 3:6] = nrm
        vb[:, 6:10] = mesh.colors
        vb[:, 10:12] = mesh.uv
        self.clear()
        self.setStride(self.STRIDE)
        self.setVertexData(QByteArray(vb.tobytes()))
        self.setIndexData(QByteArray(np.ascontiguousarray(mesh.indices, np.uint32).tobytes()))
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(_SEM.PositionSemantic, 0, _F32)
        self.addAttribute(_SEM.NormalSemantic, 12, _F32)
        self.addAttribute(_SEM.ColorSemantic, 24, _F32)
        self.addAttribute(_SEM.TexCoordSemantic, 40, _F32)
        self.addAttribute(_SEM.IndexSemantic, 0, _U32)
        if mesh.vertex_count:
            lo, hi = pos.min(axis=0), pos.max(axis=0)
            self.setBounds(QVector3D(*map(float, lo)), QVector3D(*map(float, hi)))
        self.update()
        self.upload_ms = (time.perf_counter() - t0) * 1000.0


class ImageTexture(QQuick3DTextureData):
    """A QImage as an RGBA8 texture (the baked 2D ground)."""

    def __init__(self, image: QImage, parent: QObject | None = None) -> None:
        super().__init__(parent)
        img = image.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        self.setSize(QSize(img.width(), img.height()))
        self.setFormat(QQuick3DTextureData.Format.RGBA8)
        self.setHasTransparency(False)
        self.setTextureData(QByteArray(bytes(ptr)))
        self.update()


class SpikeModel(QObject):
    """One engine Model: its geometry plus the material kind and flags."""

    def __init__(self, item_id: str, geometry: NumpyGeometry, kind: str,
                 casts_shadows: bool = True) -> None:
        super().__init__()
        self._item_id = item_id
        self._geometry = geometry
        self._kind = kind
        self._casts = casts_shadows

    @pyqtProperty(str, constant=True)
    def itemId(self) -> str:  # noqa: N802 — QML property name
        return self._item_id

    @pyqtProperty(QObject, constant=True)
    def geometry(self) -> QObject:
        return self._geometry

    @pyqtProperty(str, constant=True)
    def kind(self) -> str:
        return self._kind

    @pyqtProperty(bool, constant=True)
    def castsShadows(self) -> bool:  # noqa: N802
        return self._casts


@dataclass
class SunState:
    elevation: float
    azimuth: float
    travel_scene: tuple[float, float, float]  # direction the light travels, scene frame
    color: str
    brightness: float
    night: bool


class SpikeRenderer:
    """Hosts GardenSpike.qml in a QQuickView or QQuickWidget and renders shots."""

    def __init__(self, host: str = "view", size: tuple[int, int] = (1280, 720),
                 frame_timeout_s: float = 120.0, log: Any = None) -> None:
        self.host_kind = host
        self.size = size
        self.frames = 0
        self.frame_timeout_s = frame_timeout_s
        self.wait_timeouts = 0
        self._log = log if log is not None else (lambda *_a, **_k: None)
        self.models: list[SpikeModel] = []
        self._keep: list[Any] = []
        t0 = time.perf_counter()
        url = QUrl.fromLocalFile(str(QML_DIR / "GardenSpike.qml"))
        if host == "widget":
            self.widget = QQuickWidget()
            self.widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            self.widget.resize(*size)
            self.widget.setSource(url)
            errors = self.widget.errors()
            self.root = self.widget.rootObject()
            self.widget.frameSwapped.connect(self._on_frame)
        else:
            self.view = QQuickView()
            self.view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            self.view.resize(*size)
            self.view.setSource(url)
            errors = self.view.errors()
            self.root = self.view.rootObject()
            self.view.frameSwapped.connect(self._on_frame)
        if self.root is None:
            raise RuntimeError("QML failed: " + "; ".join(e.toString() for e in errors))
        self.qml_load_ms = (time.perf_counter() - t0) * 1000.0
        self.first_frame_ms: float | None = None
        self._shown_at: float | None = None

    # -- plumbing ----------------------------------------------------------
    def _on_frame(self) -> None:
        self.frames += 1
        if self.first_frame_ms is None and self._shown_at is not None:
            self.first_frame_ms = (time.perf_counter() - self._shown_at) * 1000.0

    def quick_window(self) -> QQuickWindow:
        return self.widget.quickWindow() if self.host_kind == "widget" else self.view

    def show(self) -> None:
        self._shown_at = time.perf_counter()
        if self.host_kind == "widget":
            self.widget.show()
        else:
            self.view.show()

    def graphics_api(self) -> str:
        api = self.quick_window().rendererInterface().graphicsApi()
        return getattr(api, "name", str(api))

    def request_update(self) -> None:
        if self.host_kind == "widget":
            self.widget.update()
        else:
            self.view.update()

    def is_exposed(self) -> bool:
        return bool(self.quick_window().isExposed())

    def wait_frames(self, n: int, timeout_s: float | None = None, label: str = "") -> int:
        """Pump the event loop until ``n`` more frames were presented (or timeout).

        Returns the number of frames presented during the wait. A timeout is a
        finding, not a silent pass: it is counted in ``wait_timeouts`` and logged
        with the exposure state (Windows evidence run v1 spent 56 min in waits
        without a single line of output).
        """
        timeout = self.frame_timeout_s if timeout_s is None else timeout_s
        start = self.frames
        target = start + n
        t0 = time.perf_counter()
        deadline = t0 + timeout
        loop = QEventLoop()
        while self.frames < target and time.perf_counter() < deadline:
            self.request_update()
            QTimer.singleShot(5, loop.quit)
            loop.exec()
        got = self.frames - start
        timed_out = got < n
        if timed_out:
            self.wait_timeouts += 1
        self._log("wait", label=label, want=n, got=got,
                  ms=round((time.perf_counter() - t0) * 1000.0, 1),
                  timeout=timed_out, exposed=self.is_exposed())
        return got

    def grab(self) -> QImage:
        if self.host_kind == "widget":
            return self.widget.grabFramebuffer()
        return self.view.grabWindow()

    # -- scene -------------------------------------------------------------
    def set_models(self, models: list[SpikeModel]) -> None:
        self.models = models
        self.root.setProperty("sceneModels", models)

    def set_ground(self, image: QImage | None, x0: float, y0: float, x1: float, y1: float) -> None:
        if image is None:
            self.root.setProperty("groundTexture", None)
            return
        tex = ImageTexture(image)
        self._keep.append(tex)
        self.root.setProperty("groundTexture", tex)
        self.root.setProperty("groundCenter", vec_to_engine((x0 + x1) / 2, (y0 + y1) / 2, 0))
        self.root.setProperty("groundWidth", float(x1 - x0))
        self.root.setProperty("groundDepth", float(y1 - y0))

    def set_preset(self, preset: str) -> None:
        self.root.setProperty("preset", preset)

    def set_sun(self, sun: SunState) -> None:
        tx, ty, tz = sun.travel_scene
        travel = vec_to_engine(tx, ty, tz).normalized()
        self.root.setProperty("sunTravel", travel)
        # a DirectionalLight shines down its local -Z; rotate -Z onto the travel vector
        self.root.setProperty("sunRotation", QQuaternion.rotationTo(QVector3D(0, 0, -1), travel))
        self.root.setProperty("sunElevation", float(max(sun.elevation, -5.0)))
        # ProceduralSkyTextureData measures longitude from the camera-forward
        # (−z = north) axis; calibrated in the spike (see ADR-047 evidence log).
        self.root.setProperty("skyLongitude", float(sky_longitude(sun.azimuth)))
        self.root.setProperty("sunColor", QColor(sun.color))
        self.root.setProperty("sunBrightness", float(sun.brightness))
        self.root.setProperty("night", bool(sun.night))
        self.root.setProperty("sunVersion", int(self.root.property("sunVersion")) + 1)

    def set_camera(self, eye_scene: tuple[float, float, float],
                   target_scene: tuple[float, float, float], fov: float = 40.0) -> None:
        self.root.setProperty("orthoTopDown", False)
        self.root.setProperty("camPos", vec_to_engine(*eye_scene))
        self.root.setProperty("camTarget", vec_to_engine(*target_scene))
        self.root.setProperty("camFov", float(fov))
        self.root.setProperty("camVersion", int(self.root.property("camVersion")) + 1)

    def set_top_down(self, center_scene: tuple[float, float], magnification: float) -> None:
        self.root.setProperty("camTarget", vec_to_engine(center_scene[0], center_scene[1], 0))
        self.root.setProperty("orthoMagnification", float(magnification))
        self.root.setProperty("orthoTopDown", True)

    def set_exposure(self, exposure: float, probe: float) -> None:
        self.root.setProperty("exposure", float(exposure))
        self.root.setProperty("probeExposure", float(probe))

    def set_animate(self, on: bool) -> None:
        self.root.setProperty("animate", bool(on))

    def pick(self, x: float, y: float) -> dict:
        from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt  # noqa: PLC0415

        ret = QMetaObject.invokeMethod(
            self.root, "pickAt", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", float(x)), Q_ARG("QVariant", float(y)),
        )
        return dict(ret) if ret else {}

    def measure_fps(self, seconds: float) -> float:
        start_frames = self.frames
        self.set_animate(True)
        t0 = time.perf_counter()
        loop = QEventLoop()
        while time.perf_counter() - t0 < seconds:
            self.request_update()
            QTimer.singleShot(1, loop.quit)
            loop.exec()
        self.set_animate(False)
        return (self.frames - start_frames) / max(time.perf_counter() - t0, 1e-6)


def sky_longitude(azimuth_deg: float) -> float:
    """Compass azimuth (clockwise from north) → ProceduralSkyTextureData ``sunLongitude``.

    Measured by the spike's sky probe (ADR-047 evidence log): with longitude L the
    sky draws its sun at compass bearing L − 90°, so L = azimuth + 90°. Re-run
    ``--spike-q3d --orient`` (``sky_ok``) after any Qt upgrade.
    """
    return (azimuth_deg + 90.0) % 360.0
