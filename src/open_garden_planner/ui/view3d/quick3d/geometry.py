"""``QQuick3DGeometry`` fed from interleaved bytes (L1.2). ENGINE module.

All the thinking is in ``core/scene3d/interleave.py`` (Qt-free, tested byte for
byte): this class only hands the buffers to Qt and declares the layout.

One upload per object, on purpose — there is no method to load new data into an
existing ``BufferGeometry``. The L0 spike measured what reuse costs: once the
Model using a ``QQuick3DGeometry`` is destroyed, the same geometry given to a
new Model renders nothing and picks nothing, and ``update()`` does not help
(``ogp-3d-renderer`` §2). A geometry therefore lives exactly as long as its
Model; new geometry means a new object.

The one exception has a class of its own, ``ReloadableGeometry`` (L1.8): the
selection ring's Model is never destroyed, so its geometry is re-loaded in place.
"""

from __future__ import annotations

from typing import ClassVar, Final

from PyQt6.QtCore import QByteArray
from PyQt6.QtGui import QVector3D
from PyQt6.QtQuick3D import QQuick3DGeometry, QQuick3DObject

from open_garden_planner.core.scene3d import (
    COLOR_OFFSET,
    NORMAL_OFFSET,
    POSITION_OFFSET,
    UV_OFFSET,
    VERTEX_STRIDE,
    EngineBuffers,
)

_SEMANTIC: Final = QQuick3DGeometry.Attribute.Semantic
_F32: Final = QQuick3DGeometry.Attribute.ComponentType.F32Type
_U32: Final = QQuick3DGeometry.Attribute.ComponentType.U32Type


def _declare_layout(geometry: QQuick3DGeometry) -> None:
    """The one vertex layout of the package (``core/scene3d/interleave.py``)."""
    geometry.setStride(VERTEX_STRIDE)
    geometry.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
    geometry.addAttribute(_SEMANTIC.PositionSemantic, POSITION_OFFSET, _F32)
    geometry.addAttribute(_SEMANTIC.NormalSemantic, NORMAL_OFFSET, _F32)
    geometry.addAttribute(_SEMANTIC.ColorSemantic, COLOR_OFFSET, _F32)
    geometry.addAttribute(_SEMANTIC.TexCoordSemantic, UV_OFFSET, _F32)
    geometry.addAttribute(_SEMANTIC.IndexSemantic, 0, _U32)


class BufferGeometry(QQuick3DGeometry):
    """One mesh part on the GPU: ``buffers`` uploaded once, at construction."""

    #: Uploads made in this process — the Qt-level instrument behind "a move or a
    #: recolour uploads nothing" (the render tier reads it around each edit).
    uploads: ClassVar[int] = 0

    def __init__(self, buffers: EngineBuffers, parent: QQuick3DObject | None = None) -> None:
        super().__init__(parent)
        self.vertex_count = buffers.vertex_count
        _declare_layout(self)
        self.setVertexData(QByteArray(buffers.vertex_data))
        self.setIndexData(QByteArray(buffers.index_data))
        self.setBounds(QVector3D(*buffers.bounds_min), QVector3D(*buffers.bounds_max))
        # QQuick3DObject.update() exists at runtime; PyQt6 6.11's stubs do not declare it
        self.update()  # type: ignore[attr-defined]
        BufferGeometry.uploads += 1


class ReloadableGeometry(QQuick3DGeometry):
    """A geometry whose data is loaded again and again INTO THE SAME OBJECT (L1.8: the
    selection ring) — the opposite of ``BufferGeometry``, for the opposite case.

    A ``BufferGeometry`` lives exactly as long as its Model, because a geometry
    that outlives its Model draws nothing in the next one. This one belongs to a
    Model that is never destroyed — the scene's one ring Model, its ``parent`` —
    so new data goes into the object the Model already has: a selection change
    creates and destroys NO engine object. (Measured on the L0 spike: a full
    re-upload into a geometry is what works; ``ogp-3d-renderer`` §2.)

    ``loads`` counts them — apart from ``BufferGeometry.uploads``, so that "a move
    uploads no MODEL geometry" keeps its meaning while a selected item's ring
    follows it.
    """

    loads: ClassVar[int] = 0
    #: How many of these objects were ever made in this process: one per host that
    #: showed a selection — the instrument behind "a selection change creates nothing".
    created: ClassVar[int] = 0

    def __init__(self, parent: QQuick3DObject | None = None) -> None:
        super().__init__(parent)
        self.vertex_count = 0
        _declare_layout(self)
        type(self).created += 1   # a subclass keeps counts of its own (MeadowGeometry)

    def load(self, buffers: EngineBuffers, margin_cm: float = 0.0) -> None:
        """Replace what this geometry draws. ``margin_cm`` widens its bounds on every
        side — for a mesh whose vertex shader moves vertices outwards (the engine
        culls by the bounds it is told)."""
        self.setVertexData(QByteArray(buffers.vertex_data))
        self.setIndexData(QByteArray(buffers.index_data))
        low = tuple(value - margin_cm for value in buffers.bounds_min)
        high = tuple(value + margin_cm for value in buffers.bounds_max)
        self.setBounds(QVector3D(*low), QVector3D(*high))
        self.vertex_count = buffers.vertex_count
        self.update()  # type: ignore[attr-defined]  # as above
        type(self).loads += 1


class MeadowGeometry(ReloadableGeometry):
    """The endless meadow's ONE geometry (#388, ``Quick3DHost._show_meadow``): a
    ``ReloadableGeometry`` with counts of its own, so that the ring's and the overlays'
    instruments ("a selection change creates nothing") keep counting only them."""

    loads: ClassVar[int] = 0
    created: ClassVar[int] = 0
