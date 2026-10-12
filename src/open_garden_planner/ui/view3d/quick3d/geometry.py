"""``QQuick3DGeometry`` fed from interleaved bytes (L1.2). ENGINE module.

All the thinking is in ``core/scene3d/interleave.py`` (Qt-free, tested byte for
byte): this class only hands the buffers to Qt and declares the layout.

One upload per object, on purpose — there is no method to load new data into an
existing ``BufferGeometry``. The L0 spike measured what reuse costs: once the
Model using a ``QQuick3DGeometry`` is destroyed, the same geometry given to a
new Model renders nothing and picks nothing, and ``update()`` does not help
(``ogp-3d-renderer`` §2). A geometry therefore lives exactly as long as its
Model; new geometry means a new object.
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


class BufferGeometry(QQuick3DGeometry):
    """One mesh part on the GPU: ``buffers`` uploaded once, at construction."""

    #: Uploads made in this process — the Qt-level instrument behind "a move or a
    #: recolour uploads nothing" (the render tier reads it around each edit).
    uploads: ClassVar[int] = 0

    def __init__(self, buffers: EngineBuffers, parent: QQuick3DObject | None = None) -> None:
        super().__init__(parent)
        self.vertex_count = buffers.vertex_count
        self.setStride(VERTEX_STRIDE)
        self.setVertexData(QByteArray(buffers.vertex_data))
        self.setIndexData(QByteArray(buffers.index_data))
        self.setPrimitiveType(QQuick3DGeometry.PrimitiveType.Triangles)
        self.addAttribute(_SEMANTIC.PositionSemantic, POSITION_OFFSET, _F32)
        self.addAttribute(_SEMANTIC.NormalSemantic, NORMAL_OFFSET, _F32)
        self.addAttribute(_SEMANTIC.ColorSemantic, COLOR_OFFSET, _F32)
        self.addAttribute(_SEMANTIC.TexCoordSemantic, UV_OFFSET, _F32)
        self.addAttribute(_SEMANTIC.IndexSemantic, 0, _U32)
        self.setBounds(QVector3D(*buffers.bounds_min), QVector3D(*buffers.bounds_max))
        # QQuick3DObject.update() exists at runtime; PyQt6 6.11's stubs do not declare it
        self.update()  # type: ignore[attr-defined]
        BufferGeometry.uploads += 1
