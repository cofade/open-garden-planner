"""The atmosphere sky's two textures as texture DATA (Phase 17 L7, #391). ENGINE module.

Both are made on the CPU and handed to ``Garden.qml``'s ``buildAtmosphere`` as
``QQuick3DTextureData`` — not rendered by the GPU in the frame as Qt's skymaterial
example does — because a ``SkyMaterial`` compiles its shader only once every texture
it samples exists, and a provider's texture exists only after its first render: the
first frame was white, and an offscreen frame (rendered once) white every time
(measured, L7; ``core/scene3d/atmosphere_lut.py`` says more).

- ``CloudNoiseTexture``: the cloud noise volume (``core/scene3d/cloud_noise.py``), one
  RGBA16F 64³ texture per host, uploaded once, at construction.
- ``SkyViewTexture``: the sky-view table (``core/scene3d/atmosphere_lut.py``), RGBA16F
  128², its alpha the sky's per-elevation profile (#716), REFILLED for every new sun or
  painted sky (``set_sky``: a weather changes the profile at the same sun) — the same
  object: a data object is never re-pointed at another ``Texture`` (that draws white:
  ``ogp-3d-renderer`` §2/§5), and ``setTextureData`` + ``update()`` on the attached one
  is the measured way to change a texture's pixels.

Each is held by the host for its whole life.
"""

from __future__ import annotations

from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtQuick3D import QQuick3DTextureData

from open_garden_planner.core.scene3d.atmosphere_lut import LUT_SIZE, PaintedSky, sky_view_rgba16f
from open_garden_planner.core.scene3d.cloud_noise import SIZE, cloud_noise_rgba16f

__all__ = ["CloudNoiseTexture", "SkyViewTexture"]


class CloudNoiseTexture(QQuick3DTextureData):
    """The cloud noise volume: width = height = depth = ``SIZE``, RGBA16F, tileable."""

    def __init__(self) -> None:
        super().__init__()
        self.setSize(QSize(SIZE, SIZE))
        self.setDepth(SIZE)
        self.setFormat(QQuick3DTextureData.Format.RGBA16F)
        self.setHasTransparency(False)
        self.setTextureData(QByteArray(cloud_noise_rgba16f()))
        # QQuick3DObject.update() exists at runtime; PyQt6's stubs do not declare it
        self.update()  # type: ignore[attr-defined]


class SkyViewTexture(QQuick3DTextureData):
    """The sky-view table of one sky: ``LUT_SIZE``², RGBA16F, row ``v`` = 0 first; rgb
    the clear sky's radiance of this sun, alpha this painted sky's profile."""

    def __init__(self, sun_direction: tuple[float, float, float], painted: PaintedSky) -> None:
        super().__init__()
        self.setSize(QSize(LUT_SIZE, LUT_SIZE))
        self.setFormat(QQuick3DTextureData.Format.RGBA16F)
        self.setHasTransparency(False)
        self.sun_direction: tuple[float, float, float] | None = None
        self.painted: PaintedSky | None = None
        self.set_sky(sun_direction, painted)

    def set_sky(self, sun_direction: tuple[float, float, float], painted: PaintedSky) -> None:
        """Refill the table for a sun (atmosphere coordinates) and the painted sky beneath
        it; the same sun and painted sky: nothing."""
        if sun_direction == self.sun_direction and painted == self.painted:
            return
        self.setTextureData(QByteArray(sky_view_rgba16f(sun_direction, painted)))
        self.update()  # type: ignore[attr-defined]
        self.sun_direction, self.painted = sun_direction, painted
