"""The plan's ground as tiles of plain data (Phase 17 L1.5, #385, ADR-059 addendum).

In 3D everything flat — lawns, terraces, driveways, paths, in-ground beds — is
not geometry: it is PAINTED into the ground, as the 2D canvas paints it. This
module is the Qt-free half of that: the pixel grid over the plan rectangle, the
tile a sink receives, and the seam through which ``SceneSync`` asks for tiles
(``GroundBaking``). The painting itself needs ``QPainter`` and lives in
``ui/view3d/ground_bake.py``.

THE GRID. The plan rectangle runs from scene (0, 0) to (``width_cm`` east,
``depth_cm`` north). Over it lies ONE grid of square pixels, ``px_per_cm`` to
the centimetre, anchored at the south-west corner: pixel column ``i`` covers
east ``[i, i + 1) / px_per_cm``, pixel row ``j`` — counted from the SOUTH —
north ``[j, j + 1) / px_per_cm``. A tile is ``tile_px`` × ``tile_px`` of those
pixels (fewer in the last column and the last row), so every tile is a crop of
the same conceptual image and two neighbours meet without a seam by
construction: no pixel is painted twice and none is resampled.

Resolution. ``px_per_cm`` is the largest power of one half, at most 1, that
keeps the whole ground within ``max_pixels``. At 1 px/cm a fill texture is
painted texel for texel (the textures are drawn at 1 px = 1 cm); at 1/2 and
1/4 a texel block is averaged exactly. A scale in between would resample every
texture and bake the moiré into the ground.

A tile's ``pixels`` are RGBA8, opaque, row 0 on the NORTH edge — the image as a
map shows it. An engine that samples it bottom-up flips it once (Qt Quick 3D:
``flipV``).

BOUNDS. A plan's size comes out of a plan file, and anybody can write one. So
the grid is bounded by construction, before a tile exists: a side longer than
``MAX_PLAN_CM`` (or not a positive finite number) is refused; the pixels of all
tiles together stay within ``max_pixels`` AND their number within
``max_tiles`` — pixels alone do not bound it: a plan of 10 km by 1 cm is one
row of 1-pixel-high tiles, each of them a tile object, a painted image and an
engine texture. ``tiles_touching`` clamps a box to the grid before it does any
arithmetic with it, so a box at infinity names no tile and overflows nothing.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol, runtime_checkable

from .record import MAX_LENGTH_CM

if TYPE_CHECKING:
    from .record import Record
    from .scene_diff import SceneDiff

#: The side of a full tile in pixels. Measured (development box, ``QPainter`` on a
#: ``QImage``): a tile is re-baked in about 0.3 ms plus what its items cost, and four
#: of them are 4 MB to upload; at 1 px/cm it spans 5.12 m, so an item of up to 3 m
#: that is moved a little touches at most 2 × 2 tiles. 256 px made such a move nine
#: tiles; 1024 px made it 16 MB of upload.
TILE_PX: Final = 512
#: The most pixels a ground may have, all tiles together: 4096 × 4096. 64 MB of
#: RGBA8 — once in these tiles, once in the engine's textures, once (and a third
#: more, its mipmaps) on the graphics card. A plan of 24 × 16 m needs 3.8 million
#: at 1 px/cm; one of 50 × 30 m 15 million; beyond that the resolution halves.
MAX_GROUND_PIXELS: Final = 4096 * 4096
#: The most tiles a ground may have (module docstring, "Bounds"). A plan whose
#: pixels fit ``MAX_GROUND_PIXELS`` in full tiles has at most 64; only a plan much
#: longer than wide comes near this number, and it halves its resolution until it
#: is under it.
MAX_GROUND_TILES: Final = 256
#: The longest side a plan may have: what a record can hold (``record.MAX_LENGTH_CM``,
#: 10 km) — no item can lie on ground beyond it.
MAX_PLAN_CM: Final = MAX_LENGTH_CM
#: The sides a tile may have, in pixels: below, a ground is thousands of tiles; above,
#: one tile is more than an engine texture should be.
MIN_TILE_PX: Final = 16
MAX_TILE_PX: Final = 4096
#: Albedo of plan ground no item covers, 8-bit sRGB: the ONE meadow albedo, shared
#: with the endless meadow around the plan (``quick3d.look.NEUTRAL_DAY``, pinned
#: equal by a test) — never the canvas's beige. A plan whose bare ground differs
#: from the meadow reads as an island, at night as a glowing one.
MEADOW_RGB: Final[tuple[int, int, int]] = (0x48, 0x7F, 0x34)

TileKey = tuple[int, int]
"""``(column, row)`` of a tile: columns count east from 0, rows NORTH from 0."""


@dataclass(frozen=True, slots=True)
class GroundTile:
    """One baked rectangle of the plan's ground — plain data, no Qt object.

    ``column`` / ``row``: its place in the grid (rows count north from the
    south edge). ``east_cm`` / ``north_cm``: its south-west corner in the scene;
    ``width_cm`` / ``depth_cm`` its extent east and north. ``pixels``:
    ``width_px`` × ``height_px`` RGBA8 values, row 0 on the tile's NORTH edge.

    Two tiles are equal when they are the same picture at the same place. A
    baker hands an unchanged tile out as the SAME object, so comparing a ground
    with its predecessor costs nothing for the tiles that were not re-baked.
    """

    column: int
    row: int
    east_cm: float
    north_cm: float
    width_cm: float
    depth_cm: float
    width_px: int
    height_px: int
    pixels: bytes = field(repr=False, hash=False)

    def __post_init__(self) -> None:
        if self.column < 0 or self.row < 0:
            raise ValueError(f"a tile's column and row count from 0, got {self.key}")
        if self.width_px < 1 or self.height_px < 1:
            raise ValueError(f"a tile has at least one pixel, got {self.width_px} x {self.height_px}")
        for name in ("east_cm", "north_cm", "width_cm", "depth_cm"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"GroundTile.{name} must be finite, got {getattr(self, name)!r}")
        if self.width_cm <= 0.0 or self.depth_cm <= 0.0:
            raise ValueError(f"a tile covers ground, got {self.width_cm!r} x {self.depth_cm!r} cm")
        if not isinstance(self.pixels, bytes):
            raise TypeError(f"GroundTile.pixels is bytes (RGBA8), got {type(self.pixels).__name__}")
        if len(self.pixels) != self.width_px * self.height_px * 4:
            raise ValueError(
                f"a tile of {self.width_px} x {self.height_px} px holds "
                f"{self.width_px * self.height_px * 4} bytes of RGBA8, got {len(self.pixels)}")

    @property
    def key(self) -> TileKey:
        return (self.column, self.row)


def changed_tiles(old: tuple[GroundTile, ...], new: tuple[GroundTile, ...]
                  ) -> tuple[tuple[GroundTile, ...], tuple[TileKey, ...]]:
    """``(to upload, to drop)`` when a ground goes from ``old`` to ``new``: the
    tiles of ``new`` that ``old`` does not hold as they are, and the keys only
    ``old`` has. What an engine sink does with a new ground, and what a test
    counts ("one edit re-bakes at most four tiles")."""
    held = {tile.key: tile for tile in old}
    upload = tuple(tile for tile in new
                   if (mine := held.get(tile.key)) is not tile and mine != tile)
    kept = {tile.key for tile in new}
    return upload, tuple(key for key in held if key not in kept)


@dataclass(frozen=True, slots=True)
class GroundGrid:
    """The pixel grid over one plan rectangle and its tiles (module docstring)."""

    width_cm: float
    depth_cm: float
    px_per_cm: float
    tile_px: int
    width_px: int
    height_px: int
    columns: int
    rows: int

    @classmethod
    def for_plan(cls, width_cm: float, depth_cm: float, *, tile_px: int = TILE_PX,
                 max_pixels: int = MAX_GROUND_PIXELS,
                 max_tiles: int = MAX_GROUND_TILES) -> GroundGrid:
        """The grid of a plan of ``width_cm`` × ``depth_cm``: the finest resolution
        of 1, 1/2, 1/4 … px/cm at which the ground has at most ``max_pixels``
        pixels and at most ``max_tiles`` tiles. ``ValueError`` for a size that is
        not a positive finite length up to ``MAX_PLAN_CM``, and for a grid setting
        outside its range — all checked before any arithmetic."""
        check_grid_settings(tile_px, max_pixels, max_tiles)
        for name, value in (("width_cm", width_cm), ("depth_cm", depth_cm)):
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"a plan's {name} must be a positive length, got {value!r}")
            if value > MAX_PLAN_CM:
                raise ValueError(f"a plan's {name} of {value!r} cm is beyond what a plan can "
                                 f"hold ({MAX_PLAN_CM:g} cm)")
        px_per_cm = 1.0
        while True:  # at most 50 halvings: both sides are at most 1e6 cm
            width_px = max(1, math.ceil(width_cm * px_per_cm - 1e-9))
            height_px = max(1, math.ceil(depth_cm * px_per_cm - 1e-9))
            columns, rows = -(-width_px // tile_px), -(-height_px // tile_px)
            if ((width_px * height_px <= max_pixels and columns * rows <= max_tiles)
                    or (width_px == 1 and height_px == 1)):
                break
            px_per_cm /= 2.0
        return cls(width_cm=width_cm, depth_cm=depth_cm, px_per_cm=px_per_cm, tile_px=tile_px,
                   width_px=width_px, height_px=height_px, columns=columns, rows=rows)

    @property
    def tile_count(self) -> int:
        return self.columns * self.rows

    def tile_keys(self) -> Iterator[TileKey]:
        """Every tile, row by row from the south-west corner."""
        for row in range(self.rows):
            for column in range(self.columns):
                yield (column, row)

    def tile_px_rect(self, key: TileKey) -> tuple[int, int, int, int]:
        """``(x0, y0, width, height)`` of a tile in grid pixels; ``y0`` counts from
        the SOUTH edge of the plan."""
        column, row = key
        if not (0 <= column < self.columns and 0 <= row < self.rows):
            raise KeyError(f"no tile {key} in a grid of {self.columns} x {self.rows}")
        x0, y0 = column * self.tile_px, row * self.tile_px
        return (x0, y0, min(self.tile_px, self.width_px - x0), min(self.tile_px, self.height_px - y0))

    def tile_cm_rect(self, key: TileKey) -> tuple[float, float, float, float]:
        """``(east, north, width, depth)`` of a tile in scene centimetres — exactly
        its pixels' extent (the last column and row may reach past the plan by
        less than one pixel)."""
        x0, y0, width, height = self.tile_px_rect(key)
        scale = self.px_per_cm
        return (x0 / scale, y0 / scale, width / scale, height / scale)

    def tile_block(self, east0: float, north0: float, east1: float, north1: float
                   ) -> tuple[int, int, int, int] | None:
        """``(first column, first row, last column, last row)`` of the tiles a
        scene-space box (cm) reaches into — four integers, however many tiles
        that is; None for a box that misses the grid. A box that only touches a
        tile's edge from outside does not reach into it."""
        if not (east0 <= east1 and north0 <= north1):  # also False for a NaN
            return None
        scale, tile = self.px_per_cm, self.tile_px
        # clamped to the grid FIRST: what follows only ever sees numbers between 0 and
        # the grid's own size, whatever came in (an infinity too)
        x0, x1 = max(east0 * scale, 0.0), min(east1 * scale, float(self.width_px))
        y0, y1 = max(north0 * scale, 0.0), min(north1 * scale, float(self.height_px))
        if not (x0 < x1 and y0 < y1):
            return None  # beside the grid, or only touching its edge
        return (int(x0 // tile), int(y0 // tile),
                min(self.columns - 1, math.ceil(x1 / tile) - 1),
                min(self.rows - 1, math.ceil(y1 / tile) - 1))

    def tiles_touching(self, east0: float, north0: float, east1: float, north1: float
                       ) -> Iterator[TileKey]:
        """The tiles of ``tile_block``, one by one, row by row from the south-west."""
        block = self.tile_block(east0, north0, east1, north1)
        if block is None:
            return
        for row in range(block[1], block[3] + 1):
            for column in range(block[0], block[2] + 1):
                yield (column, row)


def check_grid_settings(tile_px: int, max_pixels: int, max_tiles: int = MAX_GROUND_TILES) -> None:
    """``ValueError`` for a grid setting outside its range: ``tile_px`` within
    ``MIN_TILE_PX`` … ``MAX_TILE_PX``, ``max_pixels`` within 1 …
    ``MAX_GROUND_PIXELS``, ``max_tiles`` within 1 … ``MAX_GROUND_TILES`` — the
    ceilings are hard: a setting can make a ground coarser, never larger than the
    stated memory bound. Called where the numbers ENTER (a baker's constructor),
    before anything is allocated with them."""
    for name, value, low, high in (("tile_px", tile_px, MIN_TILE_PX, MAX_TILE_PX),
                                   ("max_pixels", max_pixels, 1, MAX_GROUND_PIXELS),
                                   ("max_tiles", max_tiles, 1, MAX_GROUND_TILES)):
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{name} must be an int within {low} … {high}, got {value!r}")


@runtime_checkable
class GroundBaking(Protocol):
    """What ``SceneSync`` needs from a ground baker (``ui/view3d/ground_bake.GroundBaker``).

    Qt-free on purpose: the sync logic and its tests run without a painter, and
    a test hands in a double.
    """

    def bake(self, records: Mapping[str, Record], changes: SceneDiff | None,
             solid: Collection[str], width_cm: float, depth_cm: float
             ) -> tuple[GroundTile, ...]:
        """The ground of ``records`` (bottom to top) on a plan of ``width_cm`` ×
        ``depth_cm``: every tile, an unchanged one as the same object as last time.

        ``solid``: the ids the scene holds a solid for — those are not painted,
        whatever they carry. ``changes``: how ``records`` differ from the records
        of the PREVIOUS call (the diff the geometry path uses), or None when the
        caller cannot say; a baker may use it to look only at what changed.

        A baker MAY STOP EARLY (a time budget): a tile it has not re-painted yet is
        handed out as the object it was — a stale picture there, never a wrong one
        elsewhere — and ``pending`` says how many such tiles there are. Every later
        call, whatever its ``changes`` (an empty diff too), goes on with them —
        and a call that BRINGS changes while tiles are pending does not spend its
        whole budget on the new ones: it also paints at least one tile that was
        already waiting (work that keeps arriving must not starve the work that
        waits). The promise: once ``pending`` is 0, the tiles are those ONE call
        on an empty baker gives for the same records, solids and plan — with a
        diff or without one.
        """

    @property
    def pending(self) -> int:
        """How many tiles still show an older picture than the last ``bake`` call
        asked for. 0: nothing is left to do for those records."""

    def clear(self) -> None:
        """Forget every tile and all pending work: the next ``bake`` paints the
        whole ground anew (a new plan: its tiles are bare until they are painted)."""

    def restart(self) -> None:
        """Forget what the tiles were painted WITH — the records, their order, the
        pending work — and KEEP THE PICTURES: the calls that follow paint every
        tile anew, and until a tile is painted it is handed out as the object it
        was (on the same plan rectangle; on another one the pictures are dropped).

        For a caller whose last ``bake`` raised: the books cannot be trusted any
        more, the pictures are what the user sees. Starting over from bare tiles
        instead would blank the ground on the next edit — stale, never wrong, also
        after a failure."""

    def fresh(self) -> GroundBaking:
        """An empty baker with this one's settings that bakes a whole ground in ONE
        call — a from-scratch reference (no time budget)."""
