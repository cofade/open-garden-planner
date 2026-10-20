"""The baked ground in the engine: one textured quad per tile (L1.5). ENGINE module.

``Quick3DHost.set_ground`` hands the complete set of ``TilePlacement`` s here;
``GroundTiles`` keeps one ``Model`` and one texture per tile in the QML scene
(``Garden.qml``: the ``groundTile`` component) and touches only what changed:

- a tile the scene already shows — the same ``pixels`` object, or equal bytes —
  is left alone: an edit that re-bakes four tiles uploads four textures;
- a tile whose picture changed gets a NEW MODEL with a new ``TileTexture``, and
  its old Model is destroyed. ONE TEXTURE PER ``Texture``, FOR LIFE — the texture
  twin of "one geometry per Model" — because a ``Texture`` element must never be
  pointed at a second ``QQuick3DTextureData``: when a data object it once held
  is destroyed, Qt resets the element's ``textureData`` to null, whatever it
  holds by then, and the tile is drawn WHITE. Measured on the dev box (RTX 4070
  and WARP, Qt 6.11): tile A re-textured, then tile B, then one frame — A is
  white; and in a window that presents frames, every re-textured tile was white
  one frame after its edit (the replaced texture is let go when a frame was
  presented). Nothing showed it while a re-bake was followed by a frame and the
  SAME tiles were re-baked next (PF-L3D-04);
- a tile that is no longer named is destroyed with its Model.

Lifetime — the keep-alive rule. A texture made in Python is owned by Python, so
something must hold it while the scene shows it: exactly the one shown, per
tile. The L0 spike's append-only keep-alive list grew the process by one baked
ground per reload. A REPLACED texture — its Model is destroyed in the same call
— is kept until the scene has shown its successor: the next presented frame
(``frame_presented``, called on the GUI thread), and, because a window may
present one frame and no more, at the latest until the next ground update or
``clear``. So at most one generation of replaced textures exists beside the
shown one, and never a growing list.

Seams. Neighbouring tiles are crops of one pixel grid (``core.scene3d.
GroundGrid``), so their pictures meet exactly; what the engine must not add is a
line of its own: the tile textures clamp at their edges (``Garden.qml``) —
repeating would bleed the opposite edge into the border texels — and each quad
is laid ``SEAM_OVERLAP_CM`` wider than its tile on every side, so that two
quads whose shared edge is computed twice in float32 can never leave a hairline
of the meadow below between them.

Known limit — ``grab()`` on a window that presents nothing. Direct3D 11 frees
what was released when a frame is PRESENTED, and a frame rendered by
``Quick3DHost.grab()`` is rendered and never presented. In a hardware-adapter
window that presents no frame, each grabbed frame leaves what was uploaded for
it committed until the view closes. Measured on the dev box (RTX 4070, 0 frames
presented, twenty full re-bakes of a 16 MB ground, every replaced texture
object destroyed): a ``grab()`` after every re-bake +16 MB a cycle, after every
fifth +3.2, NO ``grab()`` +0.000 — the growth belongs to the grabbed frame, not
to the edit or the upload (nothing is rendered, so nothing is uploaded); flat
in every variant on WARP and wherever frames are presented (PF-L3D-04, the grab() paragraph of archive/07-l1-5-ground-bake.md).
Nothing in here can release what the graphics system holds, and applying edits
more slowly changes nothing. THE RULE for whoever drives a host: no repeated
``grab()`` on a live host that is not presenting — a screenshot goes through
the offscreen path (``offscreen.render_records``: a hidden view of its own,
closed after its one frame, which gives everything back).

Failures. A function of the scene file that is missing raises in PyQt; one that
THROWS returns nothing, silently (the QML engine only warns). Both are a
``GroundTileError`` here — the host reports it as its ``EngineError`` — and the
books stay true: a tile the scene did not destroy stays in them, and the next
``clear`` tries it again.
"""

from __future__ import annotations

import weakref
from collections.abc import Sequence
from typing import Any, ClassVar, Final

from PyQt6 import sip
from PyQt6.QtCore import Q_ARG, Q_RETURN_ARG, QByteArray, QMetaObject, QObject, QSize, Qt
from PyQt6.QtGui import QVector3D
from PyQt6.QtQuick3D import QQuick3DObject, QQuick3DTextureData

from .adapter import TilePlacement

__all__ = ["SEAM_OVERLAP_CM", "GroundTileError", "GroundTiles", "TileTexture"]

_DIRECT: Final = Qt.ConnectionType.DirectConnection
#: How far a tile's quad reaches past its tile on every side, in cm (module
#: docstring, "Seams"): a fiftieth of a pixel at 1 px/cm — nothing a picture shows.
SEAM_OVERLAP_CM: Final = 0.02


class GroundTileError(RuntimeError):
    """The scene could not do what a ground tile needs: a function or a property of
    ``Garden.qml`` is missing, or a function failed."""


class TileTexture(QQuick3DTextureData):
    """One tile's picture on its way to the GPU: RGBA8, uploaded once, at construction."""

    #: Uploads made in this process — the instrument behind "an edit uploads only the
    #: tiles it re-baked" (tests read it around each edit).
    uploads: ClassVar[int] = 0

    def __init__(self, tile: TilePlacement, parent: QQuick3DObject | None = None) -> None:
        super().__init__(parent)
        _MADE.add(self)
        self.pixels = tile.pixels  # what it shows — to tell an unchanged tile by
        self.setSize(QSize(tile.width_px, tile.height_px))
        self.setFormat(QQuick3DTextureData.Format.RGBA8)
        self.setHasTransparency(False)
        self.setTextureData(QByteArray(tile.pixels))
        # QQuick3DObject.update() exists at runtime; PyQt6 6.11's stubs do not declare it
        self.update()  # type: ignore[attr-defined]
        TileTexture.uploads += 1


#: Every tile texture made in this process, held WEAKLY: what ``textures_alive`` counts.
_MADE: weakref.WeakSet[TileTexture] = weakref.WeakSet()


def textures_alive() -> int:
    """Tile texture objects that EXIST on the C++ side right now — the keep-alive rule
    as a number: never more than two generations of the tiles a scene shows. Asked of
    sip, not of Python's bookkeeping: a texture is counted while its wrapper lives and
    its C++ object has not been destroyed (a texture made in Python is owned by
    Python, so the two go together). No Python callable hangs on ``destroyed``: such a
    hook may run 0 times when the cyclic collector reaches the wrapper first, and is
    an access violation on a Qt-owned object (PF-E3D-07, item 1 of archive/05-l1-3-workspace.md; pinned by
    ``tests/unit/test_sim_clock_subscription.py``)."""
    return sum(1 for texture in list(_MADE) if not sip.isdeleted(texture))


class _Shown:
    """One tile as the scene shows it: its Model, its texture, where it lies."""

    __slots__ = ("model", "placement", "texture")

    def __init__(self, model: QObject, texture: TileTexture, placement: TilePlacement) -> None:
        self.model = model
        self.texture = texture
        self.placement = placement


class GroundTiles:
    """The tile Models and textures of one host's scene (module docstring). GUI thread."""

    def __init__(self, root: QObject) -> None:
        self._root = root
        self._shown: dict[tuple[int, int], _Shown] = {}
        self._retired: list[TileTexture] = []

    # ── what it holds (tests and diagnostics) ────────────────────────────────

    def keys(self) -> tuple[tuple[int, int], ...]:
        return tuple(self._shown)

    def textures_held(self) -> int:
        """Texture objects alive on this side: the shown ones, and the replaced ones
        that wait for the next frame. Never more than twice the tiles."""
        return len(self._shown) + len(self._retired)

    def textures_retired(self) -> int:
        return len(self._retired)

    def readback(self) -> list[dict[str, Any]]:
        """Every tile Model of the QML scene that was not destroyed — read from the
        scene, not from these books."""
        rows = self._invoke("listGroundTiles", returns=True)
        value = rows.toVariant() if hasattr(rows, "toVariant") else rows
        if value is None:
            raise GroundTileError("the scene's listGroundTiles() returned nothing — it failed")
        return [dict(row) for row in value]

    # ── driven by Quick3DHost.set_ground ─────────────────────────────────────

    def show(self, tiles: Sequence[TilePlacement]) -> None:
        """Bring the scene to exactly ``tiles``: upload what changed, drop what is
        gone, leave the rest alone."""
        self._release_retired()  # at the latest now: their successors were set a call ago
        wanted = {tile.key for tile in tiles}
        try:
            for key in [key for key in self._shown if key not in wanted]:
                self._drop(key)
            for tile in tiles:
                shown = self._shown.get(tile.key)
                if shown is None:
                    self._create(tile)
                elif shown.texture.pixels is not tile.pixels and shown.texture.pixels != tile.pixels:
                    self._replace(tile)
                elif _moved(shown.placement, tile):
                    self._place(shown.model, tile)
                    shown.placement = tile
        finally:
            self._tiled(bool(self._shown))

    def clear(self) -> None:
        """No tile: every tile Model destroyed, every texture released. It finishes
        whatever fails — every tile is tried, and only then the first failure is
        raised; a tile the scene did not destroy stays in the books."""
        failures: list[GroundTileError] = []
        for key in list(self._shown):
            try:
                self._drop(key)
            except GroundTileError as error:
                failures.append(error)
        self._release_retired()
        self._tiled(bool(self._shown))
        if failures:
            raise failures[0]

    def forget(self) -> None:
        """The scene is gone (the host closed, or Qt destroyed its view): release the
        textures without asking the scene for anything."""
        self._shown.clear()
        self._retired.clear()

    def frame_presented(self) -> None:
        """The scene has shown a frame since the last update: the replaced textures go."""
        self._release_retired()

    # ── internals ────────────────────────────────────────────────────────────

    def _invoke(self, function: str, *arguments: object, returns: bool = False) -> Any:
        try:
            if returns:
                return QMetaObject.invokeMethod(
                    self._root, function, _DIRECT, Q_RETURN_ARG("QVariant"),
                    *(Q_ARG("QVariant", argument) for argument in arguments))
            QMetaObject.invokeMethod(self._root, function, _DIRECT,
                                     *(Q_ARG("QVariant", argument) for argument in arguments))
        except RuntimeError as error:
            raise GroundTileError(f"the scene has no function {function}() ({error})") from error
        return None

    def _tiled(self, tiled: bool) -> None:
        """Tell the scene whether tiles lie on the plan (it then hides the bare
        rectangle). A scene file without the property is an error, not a silent
        dynamic property."""
        meta = self._root.metaObject()
        if (meta is None or meta.indexOfProperty("groundTiled") < 0
                or not self._root.setProperty("groundTiled", tiled)):
            raise GroundTileError("the scene has no property 'groundTiled' (renamed in Garden.qml?)")

    def _retire(self, texture: TileTexture) -> None:
        """A texture the scene no longer shows — kept until its successor was shown
        (the ONE place a texture leaves the shown set: the leak gate's control hooks
        in here)."""
        self._retired.append(texture)

    def _release_retired(self) -> None:
        self._retired.clear()

    def _create(self, tile: TilePlacement) -> None:
        texture = TileTexture(tile)
        model = self._invoke("createGroundTile", tile.key[0], tile.key[1], texture, returns=True)
        if not isinstance(model, QObject):
            raise GroundTileError(f"the scene created no Model for ground tile {tile.key} — "
                                  "createGroundTile() failed")
        self._shown[tile.key] = _Shown(model, texture, tile)  # in the books before it can fail
        self._place(model, tile)

    def _replace(self, tile: TilePlacement) -> None:
        """A tile whose picture changed: its Model is destroyed and a NEW one made,
        with a texture of its own (module docstring: one texture per ``Texture``,
        for life). The old Model goes first, so the books are true whatever fails:
        a Model the scene did not destroy is still the tile's, and a tile whose new
        Model could not be made is not in them."""
        self._drop(tile.key)
        self._create(tile)

    def _place(self, model: QObject, tile: TilePlacement) -> None:
        x, z = float(tile.center[0]), float(tile.center[2])
        self._invoke("placeGroundTile", model, x, z,
                     float(tile.width_cm + 2.0 * SEAM_OVERLAP_CM),
                     float(tile.depth_cm + 2.0 * SEAM_OVERLAP_CM))
        position = model.property("position")
        if not isinstance(position, QVector3D) or abs(position.x() - x) > 0.5 or abs(position.z() - z) > 0.5:
            raise GroundTileError(f"the scene's placeGroundTile() did not place ground tile "
                                  f"{tile.key} — it failed")

    def _drop(self, key: tuple[int, int]) -> None:
        shown = self._shown[key]
        self._invoke("destroyGroundTile", shown.model)
        if not sip.isdeleted(shown.model) and shown.model.property("retired") is not True:
            raise GroundTileError(f"the scene's destroyGroundTile() did not retire ground tile "
                                  f"{key} — it failed; the engine still holds it")
        del self._shown[key]
        self._retire(shown.texture)


def _moved(old: TilePlacement, new: TilePlacement) -> bool:
    return (old.center, old.width_cm, old.depth_cm) != (new.center, new.width_cm, new.depth_cm)
