"""The spike's ONLY Qt Quick 3D import module (ADR-048, Phase 17 L0).

Owns the engine side: numpy → ``QQuick3DGeometry``, ``QImage`` →
``QQuick3DTextureData``, the two candidate hosts (``QQuickView`` and
``QQuickWidget``), sun/camera placement, frame waiting, screenshots and the
render-side metrics. The scene → engine frame mapping happens here, exactly
once (``core.scene3d.to_engine_frame``: x = E, y = up, z = −N).
"""

from __future__ import annotations

import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PyQt6.QtCore import QByteArray, QEventLoop, QObject, QSize, QTimer, QUrl, pyqtProperty
from PyQt6.QtGui import QColor, QImage, QQuaternion, QVector3D
from PyQt6.QtQuick import QQuickItem, QQuickView, QQuickWindow
from PyQt6.QtQuick3D import QQuick3DGeometry, QQuick3DTextureData
from PyQt6.QtQuickWidgets import QQuickWidget

from open_garden_planner.spike_q3d.meshes import MeshData, srgb_to_linear

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
        self._shown: weakref.WeakSet[SpikeModel] = weakref.WeakSet()
        self.models: list[SpikeModel] = []
        self._ground: ImageTexture | None = None
        t0 = time.perf_counter()
        url = QUrl.fromLocalFile(str(QML_DIR / "GardenSpike.qml"))
        if host == "widget":
            self.widget = QQuickWidget()
            self.widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
            self.widget.resize(*size)
            self.widget.setSource(url)
            errors = self.widget.errors()
            root = self.widget.rootObject()
            # QQuickWidget renders offscreen on the GUI thread and has no
            # frameSwapped; its internal window reports every rendered frame.
            self.widget.quickWindow().afterRendering.connect(self._on_frame)
        else:
            self.view = QQuickView()
            self.view.setResizeMode(QQuickView.ResizeMode.SizeRootObjectToView)
            self.view.resize(*size)
            self.view.setSource(url)
            errors = self.view.errors()
            root = self.view.rootObject()
            self.view.frameSwapped.connect(self._on_frame)
        if root is None:
            raise RuntimeError("QML failed: " + "; ".join(e.toString() for e in errors))
        self.root: QQuickItem = root
        self.qml_load_ms = (time.perf_counter() - t0) * 1000.0
        self.first_frame_ms: float | None = None
        self._shown_at: float | None = None

    # -- plumbing ----------------------------------------------------------
    def _on_frame(self) -> None:
        self.frames += 1
        if self.first_frame_ms is None and self._shown_at is not None:
            self.first_frame_ms = (time.perf_counter() - self._shown_at) * 1000.0

    @property
    def shown_at(self) -> float | None:
        """``perf_counter()`` when ``show()`` was called (None before)."""
        return self._shown_at

    def quick_window(self) -> QQuickWindow:
        return self.widget.quickWindow() if self.host_kind == "widget" else self.view

    def show(self) -> None:
        self._shown_at = time.perf_counter()
        if self.host_kind == "widget":
            self.widget.show()
        else:
            self.view.show()

    def hide(self) -> None:
        if self.host_kind == "widget":
            self.widget.hide()
        else:
            self.view.hide()

    def close(self) -> None:
        if self.host_kind == "widget":
            self.widget.close()
        else:
            self.view.close()

    # Everything a probe may change (senior review: probes that left the camera,
    # preset, ground or sun behind made every later measurement order-dependent).
    # Root properties that are not view state: the model list is restored through
    # set_models (the re-upload rule), the counters only trigger rebuilds.
    NOT_STATE = frozenset({"sceneModels", "camVersion", "sunVersion"})
    SKY_KEYS = ("sunElevation", "skyLongitude", "night", "skyTop", "skyHorizon", "sunDiscColor")

    @property
    def state_keys(self) -> tuple[str, ...]:
        """Every property GardenSpike.qml declares on its root, minus ``NOT_STATE``.

        Read from the QML's meta-object, not kept by hand: a hand-kept list missed
        the ground placement, wind time, meadow/water colours and the SSGI/SSR
        switches (senior review), and every new property would have leaked.
        """
        mo = self.root.metaObject()
        names = (mo.property(i).name() for i in range(mo.propertyOffset(), mo.propertyCount()))
        return tuple(n for n in names if n not in self.NOT_STATE)

    def view_size(self) -> tuple[float, float]:
        """The view's actual logical size. A window larger than the screen is clamped,
        so the requested ``size`` can be wrong; probes aim with this one."""
        return float(self.root.width()), float(self.root.height())

    @contextmanager
    def preserved_state(self) -> Iterator[None]:
        """Run a probe, then put back every property and model it may have changed."""
        saved = {key: self.root.property(key) for key in self.state_keys}
        models = self.models
        try:
            yield
        finally:
            sky_changed = any(self.root.property(k) != saved[k] for k in self.SKY_KEYS)
            ground = saved["groundTexture"]
            # setProperty returns False for a name the QML does not declare or a value
            # it cannot take: a restore that silently did not happen (senior review,
            # pass 6, which also retired an identity check that only re-read this)
            refused = [key for key, value in saved.items()
                       if not self.root.setProperty(key, value)]
            if refused:
                raise RuntimeError(f"preserved_state: QML refused to restore {refused}")
            self._ground = ground  # Python owns the texture: keep the restored one alive
            if ground is not None:
                # The texture twin of the geometry rule in set_models: a texture data
                # object handed back after being detached renders the plan ground
                # untextured (white) until its data is uploaded again (senior review,
                # pass 4: --iou left the ground white, 9.8 mean luma on the frame).
                # Unconditionally: inferring "detached" from identity at block exit
                # misses a probe that detached it and set it back itself (pass 5).
                ground.setTextureData(ground.textureData())
                ground.update()
            self.set_models(models)
            if sky_changed:  # the light probe is pre-filtered once per sky texture
                self.root.setProperty("sunVersion", int(self.root.property("sunVersion")) + 1)
            if not saved["orthoTopDown"]:  # re-aim the perspective camera at camTarget
                self.root.setProperty("camVersion", int(self.root.property("camVersion")) + 1)

    def copy_view_from(self, other: SpikeRenderer) -> None:
        """Show what ``other`` shows (camera, preset, sun, sky, look), not its ground or models."""
        for key in self.state_keys:
            if key != "groundTexture":  # a texture belongs to its own window
                self.root.setProperty(key, other.root.property(key))
        for counter in ("sunVersion", "camVersion"):  # rebuild the sky, re-aim the camera
            self.root.setProperty(counter, int(self.root.property(counter)) + 1)

    def graphics_api(self) -> str:
        api = self.quick_window().rendererInterface().graphicsApi()
        return getattr(api, "name", str(api))

    def request_update(self) -> None:
        # Both hosts: ask the Quick window for a new frame. QQuickWidget.update()
        # alone only re-composites the last texture and renders nothing new.
        self.quick_window().update()

    def is_exposed(self) -> bool:
        if self.host_kind == "widget":  # renders offscreen: its window is never "exposed"
            return bool(self.widget.isVisible())
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

    def grab(self, label: str = "") -> QImage:
        # Timed on its own: on Windows WARP one grabWindow() of the sky-lit
        # scene took ~100 s while the frames before it took ~1 s each
        # (evidence run v2) — v1's "hang" was six of those.
        t0 = time.perf_counter()
        img = self.widget.grabFramebuffer() if self.host_kind == "widget" else self.view.grabWindow()
        self._log("grab", label=label, ms=round((time.perf_counter() - t0) * 1000.0, 1),
                  px=f"{img.width()}x{img.height()}")
        return img

    # -- scene -------------------------------------------------------------
    def set_models(self, models: list[SpikeModel]) -> None:
        """Show exactly ``models``; safe to call with models shown before.

        Measured (spike, OpenGL; first seen in the Windows evidence run): once
        the Model using a ``QQuick3DGeometry`` is destroyed, handing that
        geometry to a new Model renders nothing and picks nothing (frame
        identical to an empty scene, 0/20 picks); ``update()`` does not help, a
        full re-upload does. A ``Repeater3D`` over a JS array destroys and
        recreates EVERY delegate on any change of the array — so every model
        shown before is re-uploaded here, not only the ones that were removed
        (a model kept across the change still came back blank: 19/20).
        """
        for model in models:
            if model in self._shown:
                model.geometry.set_mesh(model.geometry.mesh)
            self._shown.add(model)
        self.models = list(models)
        self.root.setProperty("sceneModels", self.models)

    def set_ground(self, image: QImage | None, x0: float, y0: float, x1: float, y1: float) -> None:
        if image is None:
            self.root.setProperty("groundTexture", None)
            self._ground = None
            return
        tex = ImageTexture(image)
        self.root.setProperty("groundTexture", tex)
        # Python owns the texture, so hold the one the scene shows — and only that
        # one: an append-only keep-alive list grew RSS ~30 MB per project reload
        # (soak, 10 reloads: linear 771 -> 1035 MB; holding one: flat at ~885 MB).
        self._ground = tex
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
        # (−z = north) axis; calibrated in the spike (see ADR-048 evidence log).
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

    LOOK_COLORS = ("skyTop", "skyHorizon", "sunDiscColor", "fogColor")

    def set_look(self, look: dict[str, Any]) -> None:
        """A mood (``runner.look_for``): sky + fog colours, exposure, probe exposure.

        Apply it BEFORE ``set_sun``: the sun change builds the fresh sky texture
        whose light probe is pre-filtered once, with the colours it is born with.
        """
        for key in self.LOOK_COLORS:
            self.root.setProperty(key, QColor(look[key]))
        self.set_exposure(look["exposure"], look["probe"])

    def set_meadow_albedo(self, color: str) -> None:
        """The endless meadow's albedo — the SAME value the ground bake paints."""
        self.root.setProperty("meadowColor", QColor(color))

    def set_water_albedo(self, color: str) -> None:
        """The pond's albedo (``#rrggbb``), handed to its shader in LINEAR light."""
        r, g, b = (float(v) for v in srgb_to_linear(color))
        self.root.setProperty("waterColor", QVector3D(r, g, b))

    def set_animate(self, on: bool) -> None:
        self.root.setProperty("animate", bool(on))
        if not on:
            # a stopped wind rests at phase 0: otherwise every shot after an fps
            # measurement froze foliage at a run-dependent sway (board noise)
            self.root.setProperty("windTime", 0.0)

    def pick(self, x: float, y: float) -> dict:
        from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt  # noqa: PLC0415

        ret = QMetaObject.invokeMethod(
            self.root, "pickAt", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", float(x)), Q_ARG("QVariant", float(y)),
        )
        return _js_object(ret)

    def project(self, east: float, north: float, up: float) -> tuple[float, float]:
        """Scene point → view pixel coordinates (the same space ``pick`` takes)."""
        from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QMetaObject, Qt  # noqa: PLC0415

        e = vec_to_engine(east, north, up)
        ret = QMetaObject.invokeMethod(
            self.root, "projectToView", Qt.ConnectionType.DirectConnection,
            Q_RETURN_ARG("QVariant"), Q_ARG("QVariant", float(e.x())),
            Q_ARG("QVariant", float(e.y())), Q_ARG("QVariant", float(e.z())),
        )
        d = _js_object(ret)
        return float(d.get("x", float("nan"))), float(d.get("y", float("nan")))

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


def _js_object(ret: Any) -> dict:
    """A QML function's returned JS object arrives as ``QJSValue``, not a dict."""
    if ret is None:
        return {}
    if hasattr(ret, "toVariant"):
        ret = ret.toVariant()
    return dict(ret) if ret else {}


def sky_longitude(azimuth_deg: float) -> float:
    """Compass azimuth (clockwise from north) → ProceduralSkyTextureData ``sunLongitude``.

    Measured by the spike's sky probe (ADR-048 evidence log): with longitude L the
    sky draws its sun at compass bearing L − 90°, so L = azimuth + 90°. Re-run
    ``--spike-q3d --orient`` (``sky_ok``) after any Qt upgrade.
    """
    return (azimuth_deg + 90.0) % 360.0
