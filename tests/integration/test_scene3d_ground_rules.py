"""The ground bake's rules for a tile that cannot have everything, and for a bake
that cannot finish at once (Phase 17 L1.5, #385 — the findings of its two reviews).

By COUNTS, with hand-made records and a clock the test owns — what Qt needs to
paint a tile is not asserted anywhere here:

- a tile that cannot hold all its records loses the SMALLEST, never a large one
  (ranked by how much of the tile each record's paint box overlaps): a lawn
  under any number of pavers stays, wherever its edge runs; and an opaque cover
  ends a tile's walk (``GroundBaker._admit``);
- the time budget: a ``bake`` paints at least one tile, leaves the rest PENDING
  as the objects they were, and every later call goes on — to the tiles one
  unbudgeted bake gives; an edit a pass does not starve the backlog; a tile
  whose paint fails keeps its picture and takes nothing else with it;
- a painter that raises: the records painted after it are painted as if it had
  not been there, and its failure is a failure of the item whichever tile it
  happened in.

Parity with the 2D canvas is ``test_scene3d_ground_bake.py``'s; here the judge
is an image painted WITHOUT tiles and without bounds (``unbounded``).
"""

from __future__ import annotations

import math
import random
from collections.abc import Mapping
from typing import Any

import numpy as np
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform

from open_garden_planner.core.fill_patterns import FillPattern
from open_garden_planner.core.item_look import adopt_pen
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle
from open_garden_planner.core.scene3d import (
    MEADOW_RGB,
    GroundTile,
    Material,
    Paint,
    Params,
    Record,
    SceneDiff,
    Transform,
    diff,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.items import PolygonItem, PolylineItem
from open_garden_planner.ui.canvas.items import path_style_paint as style_paint
from open_garden_planner.ui.view3d import ground_bake
from open_garden_planner.ui.view3d.ground_bake import (
    BAKE_BUDGET_S,
    TILE_RECORDS,
    TILE_VERTICES,
    GroundBaker,
    WalkBudget,
    paint_bounds,
    paint_record,
)
from tests.integration.ground_bake_support import (
    FORMAT,
    Bake,
    canvas_render,
    canvas_rgb,
)
from tests.integration.ground_bake_support import rgba as as_array

BARE = np.array(MEADOW_RGB)
GREEN = (60, 140, 60, 255)
GREY = (150, 150, 150, 255)


def box(half_east: float, half_north: float) -> tuple[tuple[float, float], ...]:
    return ((-half_east, -half_north), (half_east, -half_north), (half_east, half_north),
            (-half_east, half_north))


def surface(item_id: str, half: tuple[float, float], at: tuple[float, float],
            fill: tuple[int, int, int, int] = GREEN, *, shape: str = "rectangle", turn: float = 0.0,
            pattern: str | None = None, opacity: float = 1.0, kind: str = "LAWN",
            ring: tuple[tuple[float, float], ...] | None = None, **params: Any) -> Record:
    """A flat record by hand: a rectangle (or ``ring``) centred on ``at``."""
    return Record(item_id=item_id, kind=kind, shape=shape,
                  footprints=(ring if ring is not None else box(*half),),
                  transform=Transform(at[0], at[1], turn),
                  material=Material(kind, fill_rgba=fill, pattern=pattern, paint=Paint(opacity=opacity)),
                  params=Params({"seed": item_id, **params}))


def pavers(count: int, fill: tuple[int, int, int, int] = GREY) -> dict[str, Record]:
    """``count`` pavers of 20 cm, all in the first tile: a 20 x 20 grid of places,
    24 cm apart — beyond 400 they lie on top of each other."""
    return {f"p{k}": surface(f"p{k}", (10.0, 10.0), (20.0 + 24.0 * (k % 20), 20.0 + 24.0 * ((k // 20) % 20)),
                             fill, kind="TERRACE_PATIO") for k in range(count)}


def unbounded(records: Mapping[str, Record], width: float, depth: float) -> np.ndarray:
    """Every record painted, bottom to top, into ONE image of the plan — no tiles,
    no bound: what the ground would be if a tile could hold everything."""
    image = QImage(int(width), int(depth), FORMAT)
    image.fill(QColor(*MEADOW_RGB))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    budget = WalkBudget(10**9, 10**9, 10**9)
    try:
        for record in records.values():
            painter.setWorldTransform(QTransform(1.0, 0.0, 0.0, -1.0, 0.0, depth))
            paint_record(painter, record, budget=budget)
    finally:
        painter.end()
    return as_array(image)


def baked(records: Mapping[str, Record], width: float = 1100.0, depth: float = 700.0,
          **settings: Any) -> tuple[GroundBaker, np.ndarray]:
    baker = GroundBaker(budget_s=None, **settings)
    baker.bake(records, None, (), width, depth)
    return baker, as_array(baker.image())


def bare_pixels(image: np.ndarray) -> int:
    return int(np.all(image[..., :3] == BARE, axis=2).sum())


def apart(image: np.ndarray, whole: np.ndarray) -> np.ndarray:
    """Where the tiled ground is not the unbounded picture — by more than ONE step
    of 255: Qt fills the last row of a rectangle clipped to a narrow image a step
    lighter than in a wide one (measured: 76 values of this plan's last tile)."""
    return np.abs(image[..., :3] - whole[..., :3]).max(axis=2) > 1


# ── a tile loses its smallest records (reviews 1 and 2, P1) ───────────────────

#: Lawns for the review's plan (1100 x 700 cm; the pavers lie in the first tile):
#: name → (half sizes, centre). The first round's rule kept a lawn only when it
#: covered the WHOLE tile — and its test lawn was the plan rectangle.
LAWNS: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "the plan rectangle": ((550.0, 350.0), (550.0, 350.0)),
    "10 cm inside the plan's edge": ((540.0, 340.0), (550.0, 350.0)),
    "half a centimetre inside": ((549.5, 349.5), (550.0, 350.0)),
    "30 % of the tile": ((140.25, 140.25), (170.25, 170.25)),  # 280.5 cm square: 0.300 of 512 x 512
}


def lawn_of(name: str) -> Record:
    half, at = LAWNS[name]
    return surface("lawn", half, at)


def lawn_pixels(lawn: Record) -> np.ndarray:
    """Where the lawn paints at all, alone on the plan."""
    return np.any(unbounded({"lawn": lawn}, 1100.0, 700.0)[..., :3] != BARE, axis=2)


class TestATileLosesItsSmallestRecords:
    """The rule by its OUTCOME (review 2): when a bound bites, a tile loses its
    smallest records, never a large one. Ranked by how much of the tile each
    record's paint box overlaps; ties to the topmost; the kept ones in z order."""

    @pytest.mark.parametrize("count", [255, 256, 2000])
    @pytest.mark.parametrize("lawn", sorted(LAWNS))
    def test_no_pixel_of_the_lawn_is_bare(self, qtbot: Any, lawn: str, count: int) -> None:
        """A lawn and pavers of 20 cm in one tile. Measured before: with the lawn 10
        cm inside the plan's edge and 256 pavers, 149,604 lawn pixels of the first
        tile were bare meadow (158,721 at half a centimetre; 138,240 for the plan
        rectangle in the first delivery); more pavers did not help. Now: zero, for
        every lawn, at 255, 256 and 2,000 pavers — and what is missing is pavers."""
        under = lawn_of(lawn)
        records = {"lawn": under, **pavers(count)}
        baker, image = baked(records)
        bare = np.all(image[..., :3] == BARE, axis=2)
        assert int((bare & lawn_pixels(under)).sum()) == 0
        whole = unbounded(records, 1100.0, 700.0)
        differs = apart(image, whole)
        if count + 1 <= TILE_RECORDS:
            assert baker.capped == frozenset() and not differs.any()
            return
        # the tile holds 256: the lawn and its 255 topmost pavers (they are all one
        # size: of equals the lower ones go) — and says that it holds less than the plan
        assert baker.capped == frozenset({(0, 0)}) and baker.capped_tiles == 1
        kept = baker._order[(0, 0)]  # noqa: SLF001 - what the tile was painted with, bottom to top
        assert len(kept) == TILE_RECORDS and kept[0] == "lawn"
        assert kept[1:] == tuple(f"p{k}" for k in range(count - 255, count))
        # what is missing is PAVERS: wherever the ground is not the unbounded picture,
        # that picture has a paver
        assert differs.any() and np.all(whole[differs][:, :3] == np.array(GREY[:3]))

    def test_the_smallest_goes_first_even_when_it_is_the_topmost(self, qtbot: Any) -> None:
        """255 pavers of 20 cm, ONE of 12 cm drawn last — on top of everything — and
        the lawn: 257 members, one too many. The one left out is the small paver."""
        records = {"lawn": lawn_of("10 cm inside the plan's edge"), **pavers(255)}
        records["small"] = surface("small", (6.0, 6.0), (500.0, 500.0), (200, 30, 30, 255),
                                   kind="TERRACE_PATIO")
        baker, image = baked(records)
        assert baker.capped == frozenset({(0, 0)})
        kept = baker._order[(0, 0)]  # noqa: SLF001
        assert len(kept) == TILE_RECORDS and "small" not in kept and kept[0] == "lawn"
        differs = apart(image, unbounded(records, 1100.0, 700.0))
        rows, columns = np.nonzero(differs)
        assert 100 <= len(rows) <= 144  # the 12 cm square, and nothing else
        assert columns.min() >= 494 and columns.max() <= 506
        assert 699 - rows.max() >= 494 and 699 - rows.min() <= 506

    def test_the_lowest_of_equals_is_left_out_and_the_tile_says_so(self, qtbot: Any) -> None:
        """257 pavers of one size and nothing else: the lowest is left out — it
        outranks nothing the tile holds — and the tile is capped. (With a lawn under
        them the lawn's arrival says so too; here nothing else does.) The same for
        a SMALLER paver under 256 others."""
        baker, _image = baked(pavers(257))
        assert baker._order[(0, 0)] == tuple(f"p{k}" for k in range(1, 257))  # noqa: SLF001
        assert baker.capped == frozenset({(0, 0)}) and baker.capped_tiles == 1
        under = {"small": surface("small", (6.0, 6.0), (500.0, 500.0), (200, 30, 30, 255),
                                  kind="TERRACE_PATIO"), **pavers(256)}
        baker, _image = baked(under)
        assert "small" not in baker._order[(0, 0)] and len(baker._order[(0, 0)]) == TILE_RECORDS  # noqa: SLF001
        assert baker.capped == frozenset({(0, 0)})

    def test_a_record_ranks_by_what_it_covers_of_the_tile_not_by_its_size(self, qtbot: Any) -> None:
        """A terrace of 6 m in the NEXT tiles whose corner reaches half a centimetre
        into this one, and 256 pavers here: 257 members. The terrace is by far the
        largest record — and covers the least of this tile: it is the one this tile
        leaves out (the tiles it lies in paint it whole)."""
        records = dict(pavers(256))
        records["neighbour"] = surface("neighbour", (300.5, 94.5), (812.0, 606.0), (200, 30, 30, 255),
                                       kind="TERRACE_PATIO")
        baker, image = baked(records)
        kept = baker._order[(0, 0)]  # noqa: SLF001
        assert kept == tuple(f"p{k}" for k in range(256)) and baker.capped == frozenset({(0, 0)})
        assert "neighbour" in baker._order[(1, 1)]  # noqa: SLF001
        differs = apart(image, unbounded(records, 1100.0, 700.0))
        assert int(differs.sum()) <= 4  # the corner of the terrace in this tile: half a centimetre

    def test_of_two_sizes_the_large_ones_are_kept(self, qtbot: Any) -> None:
        """2,000 pavers, every fourth one 12 cm instead of 20: the tile keeps the lawn
        and 255 pavers of 20 cm — the topmost of them — and not one small paver."""
        records: dict[str, Record] = {"lawn": lawn_of("half a centimetre inside")}
        for k in range(2000):
            half = 6.0 if k % 4 == 0 else 10.0
            records[f"p{k}"] = surface(f"p{k}", (half, half),
                                       (20.0 + 24.0 * (k % 20), 20.0 + 24.0 * ((k // 20) % 20)),
                                       GREY, kind="TERRACE_PATIO")
        baker, _image = baked(records)
        kept = baker._order[(0, 0)]  # noqa: SLF001
        large = [f"p{k}" for k in range(2000) if k % 4 != 0]
        assert kept == ("lawn", *large[-255:])
        assert baker.capped == frozenset({(0, 0)})

    @pytest.mark.parametrize("count", [256, 2000])
    def test_a_real_scene_against_the_canvas(self, qtbot: Any, count: int) -> None:
        """Through the product's pipeline, judged by the 2D canvas's own render: a
        LAWN rectangle 10 cm inside the plan's edge and pavers drawn on it (400
        places; beyond 400 pavers they lie on one another). Measured before, at
        256 pavers: mean 24.4 of 255, 130,129 px off by more than 8. Now no lawn
        pixel is bare, what differs are the pavers the tile could not hold — 1
        place of 256 at 256 pavers (484 px, one paver with its outline), 145 places
        of 400 at 2,000 (71,200 px) — and every other pixel of the plan is the
        canvas's, exactly. The mean over the plan is the missing pavers' area times
        their contrast against the lawn: 0.040 and 6.25 with master's luminance tint
        of the paver texture (#502; 0.032 and 4.88 with the old wash)."""
        from open_garden_planner.ui.canvas.items import RectangleItem
        from tests.integration.test_scene3d_ground_bake import compare

        scene = CanvasScene(width_cm=1100.0, height_cm=700.0)
        with scene.suspend_z_refresh(renumber=True):  # as a plan file is loaded
            lawn = RectangleItem(10.0, 10.0, 1080.0, 680.0, object_type=ObjectType.LAWN)
            scene.addItem(lawn)
            for k in range(count):
                scene.addItem(RectangleItem(10.0 + 24.0 * (k % 20), 10.0 + 24.0 * ((k // 20) % 20),
                                            20.0, 20.0, object_type=ObjectType.TERRACE_PATIO))
        _mean, _worst, bake = compare(scene)
        reference = canvas_render(scene, bake.grid)
        image = bake.image()
        background = np.array(canvas_rgb())
        bare = np.all(image[..., :3] == background, axis=2)
        assert int((bare & ~np.all(reference[..., :3] == background, axis=2)).sum()) == 0  # no lawn pixel bare
        assert bake.baker.capped == frozenset({(0, 0)})
        assert str(lawn.item_id) in bake.baker._order[(0, 0)]  # noqa: SLF001
        apart_by = np.abs(image[..., :3] - reference[..., :3])
        off = apart_by.max(axis=2) > 8
        # the places whose pavers are all among the ones the tile could not hold
        missing = len({k % 400 for k in range(count)} - {k % 400 for k in range(count - 255, count)})
        assert missing == (1 if count == 256 else 145)
        assert missing * 20 * 20 <= int(off.sum()) <= missing * 23 * 23
        # … and everywhere else the ground IS the canvas. (The mean over the whole
        # plan is the missing pavers' area times their contrast against the lawn: it
        # says nothing more, and it moved with the paver texture's tint — #502.)
        assert int(apart_by[~off].max()) == 0

    def test_members_that_overlap_the_tile_equally_keep_the_topmost(self, qtbot: Any) -> None:
        """Ties go to the topmost. Six translucent lawns under 300 pavers: all six
        are kept (the first rule kept four "underlays"). 300 translucent lawns:
        the topmost 256 — and the tile is asked about no further record."""
        veils = {f"veil{k}": surface(f"veil{k}", (550.0, 350.0), (550.0, 350.0), (60, 200, 60, 40))
                 for k in range(6)}
        baker, _image = baked({**veils, **pavers(300)})
        kept = baker._order[(0, 0)]  # noqa: SLF001
        assert kept[:6] == tuple(veils) and kept[6:] == tuple(f"p{k}" for k in range(50, 300))
        many = {f"veil{k}": surface(f"veil{k}", (550.0, 350.0), (550.0, 350.0), (60, 200, 60, 40))
                for k in range(300)}
        baker, _image = baked(many)
        assert all(baker._order[key] == tuple(f"veil{k}" for k in range(44, 300))  # noqa: SLF001
                   for key in baker.grid.tile_keys())
        # a tile is asked about 256 members, and about one more that shows it is capped
        assert baker.admission_checks == 6 * (TILE_RECORDS + 1) and len(baker.capped) == 6

    def test_what_the_ranking_does_not_know_is_a_shape(self, qtbot: Any) -> None:
        """The stated limit of ranking box against box: a thin line's paint box is its
        bounding box. 256 diagonal lines across the tile rank with the lawn under
        them — equals — and the lawn, the lowest, is the one left out."""
        records = {"lawn": surface("lawn", (256.0, 256.0), (256.0, 256.0))}
        for k in range(256):
            records[f"line{k}"] = Record(
                item_id=f"line{k}", kind="PATH", shape="polyline", footprints=(),
                transform=Transform(256.0, 256.0), path=((-300.0 + 0.1 * k, -300.0), (300.0 + 0.1 * k, 300.0)),
                path_width_cm=1.0, material=Material("PATH", stroke_rgba=(20, 20, 20, 255), paint=Paint()),
                params=Params({"seed": f"line{k}"}))
        baker, image = baked(records, 512.0, 512.0)
        assert baker.capped == frozenset({(0, 0)}) and "lawn" not in baker._order[(0, 0)]  # noqa: SLF001
        assert bare_pixels(image) > 100_000

    def test_the_vertex_bound_loses_the_smallest_too(self, qtbot: Any) -> None:
        """Forty lawns of 8,192 vertices and one of 16,384, all over the whole tile, on
        a small terrace: 344,068 vertices, and the vertex bound holds 262,144. What
        goes are the lowest-ranked: the terrace (it overlaps least) and, of the
        lawns — equals — the ten lowest."""
        def wavy(vertices: int) -> tuple[tuple[float, float], ...]:
            return tuple((700.0 * (1.0 + 0.02 * (k % 2)) * math.cos(2.0 * math.pi * k / vertices),
                          700.0 * (1.0 + 0.02 * (k % 2)) * math.sin(2.0 * math.pi * k / vertices))
                         for k in range(vertices))

        records = {"terrace": surface("terrace", (50.0, 50.0), (256.0, 256.0), (200, 30, 30, 255))}
        for k in range(40):
            records[f"lawn{k}"] = surface(f"lawn{k}", (0.0, 0.0), (256.0, 256.0), (60, 140, 60, 40),
                                          shape="polygon", ring=wavy(8192))
        records["big"] = surface("big", (0.0, 0.0), (256.0, 256.0), (60, 140, 60, 40), shape="polygon",
                                 ring=wavy(16_384))
        baker = GroundBaker(budget_s=None)
        baker.bake(records, None, (), 512.0, 512.0)
        kept = baker._order[(0, 0)]  # noqa: SLF001
        assert kept == (*(f"lawn{k}" for k in range(10, 40)), "big")
        assert sum(len(records[item_id].footprints[0]) for item_id in kept) == TILE_VERTICES
        assert baker.capped == frozenset({(0, 0)})


# ── an opaque cover ends a tile's walk ────────────────────────────────────────


class TestAnOpaqueCoverEndsTheWalk:
    @pytest.mark.parametrize("lawn", ["polygon", "polygon to the plan's edge", "turned rectangle",
                                      "circle", "ellipse", "textured"])
    def test_a_lawn_of_any_shape_that_covers_the_tile(self, qtbot: Any, lawn: str) -> None:
        """What lies under a record that opaquely covers the tile is not painted —
        whatever the cover's shape: under each of these lawns lies a red terrace
        that must cost nothing."""
        if lawn == "polygon":  # an L with its inner corner far outside the first tile
            ring = ((-600.0, -400.0), (600.0, -400.0), (600.0, 100.0), (300.0, 100.0), (300.0, 400.0),
                    (-600.0, 400.0))
            cover = surface("lawn", (0.0, 0.0), (550.0, 350.0), shape="polygon", ring=ring)
        elif lawn == "polygon to the plan's edge":  # its edges lie ON the tile's borders
            cover = surface("lawn", (550.0, 350.0), (550.0, 350.0), shape="polygon")
        elif lawn == "turned rectangle":
            cover = surface("lawn", (900.0, 900.0), (400.0, 300.0), turn=33.0)
        elif lawn == "circle":
            round_ring = tuple((900.0 * math.cos(math.radians(15.0 * k)),
                                900.0 * math.sin(math.radians(15.0 * k))) for k in range(24))
            cover = surface("lawn", (0.0, 0.0), (256.0, 256.0), shape="circle", ring=round_ring,
                            radius_cm=900.0)
        elif lawn == "ellipse":
            oval = tuple((1200.0 * math.cos(math.radians(15.0 * k)),
                          700.0 * math.sin(math.radians(15.0 * k))) for k in range(24))
            cover = surface("lawn", (0.0, 0.0), (300.0, 250.0), shape="ellipse", ring=oval)
        else:
            cover = surface("lawn", (550.0, 350.0), (550.0, 350.0), (90, 160, 70, 255), pattern="GRASS")
        under = surface("under", (200.0, 200.0), (256.0, 256.0), (200, 30, 30, 255), kind="TERRACE_PATIO")
        records = {"under": under, "lawn": cover, **pavers(12)}
        baker, image = baked(records)
        assert baker._order[(0, 0)] == ("lawn", *(f"p{k}" for k in range(12)))  # noqa: SLF001
        assert baker.capped == frozenset()  # nothing that could be seen was left out
        assert not apart(image, unbounded(records, 1100.0, 700.0)).any()

    def test_a_translucent_lawn_is_painted_with_what_shows_through_it(self, qtbot: Any) -> None:
        """A translucent lawn ends nothing: the soil under it is a member too — and
        the walk ends at the soil, so the gravel under the soil is not."""
        records = {
            "gravel": surface("gravel", (550.0, 350.0), (550.0, 350.0), (200, 200, 200, 255)),
            "soil": surface("soil", (550.0, 350.0), (550.0, 350.0), (120, 80, 40, 255)),
            "lawn": surface("lawn", (550.0, 350.0), (550.0, 350.0), (60, 200, 60, 128)),
            **pavers(2000),
        }
        baker, image = baked(records)
        assert baker.capped == frozenset({(0, 0)})
        # per tile: soil + lawn; in the first one 254 pavers beside them
        assert baker.records_painted == TILE_RECORDS + 5 * 2
        assert baker._order[(0, 0)][:2] == ("soil", "lawn")  # noqa: SLF001
        assert tuple(image[10, 1000, :3]) == (90, 140, 50)  # the lawn over the soil, not over gravel
        assert tuple(image[667, 32, :3]) == (90, 140, 50)  # … and between the pavers of the first tile
        whole = unbounded(records, 1100.0, 700.0)
        differs = apart(image, whole)
        assert np.all(whole[differs][:, :3] == np.array(GREY[:3]))

    def test_an_item_at_half_opacity_ends_nothing_either(self, qtbot: Any) -> None:
        """Translucent by the ITEM's opacity, in an opaque colour: what is under it is
        painted too — the soil; and the walk ends there."""
        records = {
            "gravel": surface("gravel", (550.0, 350.0), (550.0, 350.0), (200, 200, 200, 255)),
            "soil": surface("soil", (550.0, 350.0), (550.0, 350.0), (120, 80, 40, 255)),
            "lawn": surface("lawn", (550.0, 350.0), (550.0, 350.0), (60, 200, 60, 255), opacity=0.5),
        }
        baker, image = baked(records)
        assert all(baker._order[key] == ("soil", "lawn") for key in baker.grid.tile_keys())  # noqa: SLF001
        assert baker.capped == frozenset()
        assert not apart(image, unbounded(records, 1100.0, 700.0)).any()
        assert tuple(image[10, 1000, :3]) != (60, 200, 60)  # the soil shows through

    def test_fifty_thousand_lawns_over_the_whole_plan(self, qtbot: Any) -> None:
        """The counts the ranking costs. OPAQUE lawns: the topmost ends every tile's
        walk — one record a tile, 21 comparisons in all. TRANSLUCENT ones: a tile is
        closed once it holds 256 members that overlap it whole and one more has
        shown that it is capped — 257 comparisons a tile (258 where the small
        square on top is a member too), never 50,000."""
        count = 50_000
        records = {f"r{k}": surface(f"r{k}", (1300.0, 900.0), (1200.0, 800.0), (k % 256, 120, 60, 255))
                   for k in range(count)}
        records["top"] = surface("top", (50.0, 50.0), (700.0, 700.0), (200, 30, 30, 255))
        baker = GroundBaker(budget_s=None)
        baker.bake(records, None, (), 2400.0, 1600.0)
        assert baker.capped == frozenset() and baker.records_painted == 20 + 1
        assert baker.admission_checks == 1 + 20  # "top": its one tile; the topmost lawn: all twenty
        assert baker.entries_held() == count + 1 + 20 + 1
        assert bare_pixels(as_array(baker.image())) == 0
        # the topmost lawn is the one that shows — and one under it costs nothing, ever
        assert tuple(as_array(baker.image())[5, 5, :3]) == ((count - 1) % 256, 120, 60)
        checks = baker.admission_checks
        recoloured = dict(records)
        recoloured["r7"] = surface("r7", (1300.0, 900.0), (1200.0, 800.0), (1, 2, 3, 255))
        tiles = baker.bake(recoloured, SceneDiff(material=("r7",)), (), 2400.0, 1600.0)
        assert baker.last_repainted == () and baker.admission_checks - checks == 20 + 1
        assert all(mine is theirs for mine, theirs in zip(tiles, baker.tiles(), strict=True))

        veils = {key: surface(key, (1300.0, 900.0), (1200.0, 800.0), (40, 120, 60, 40))
                 for key in records if key != "top"}
        veils["top"] = records["top"]
        baker = GroundBaker(budget_s=None)
        baker.bake(veils, None, (), 2400.0, 1600.0)
        # 256 members and the one that shows the tile is capped; where "top" lies, "top" as well
        assert baker.admission_checks == 20 * (TILE_RECORDS + 1) + 1 == 5_141
        assert baker.records_painted == 20 * TILE_RECORDS
        assert baker.entries_held() == count + 1 + 20 * TILE_RECORDS == 55_121
        assert baker.capped == frozenset(baker.grid.tile_keys())
        assert "top" not in baker._order[(1, 1)]  # noqa: SLF001 - the smallest is what that tile lost

    def test_the_search_for_a_cover_reads_no_more_than_a_tiles_vertices(self, qtbot: Any) -> None:
        """A polygon's rings are READ to see whether it covers a tile. Forty opaque
        rings of 16,384 vertices lie AROUND the tile — it is inside their box and
        inside their hole: the tile keeps the sixteen its vertex bound holds (the
        topmost: they all overlap it equally), reads sixteen once — and reads
        nothing of the rest."""
        vertices = 16_384
        half = vertices // 2
        around = (tuple((900.0 * math.cos(2.0 * math.pi * k / (half - 1)),
                         900.0 * math.sin(2.0 * math.pi * k / (half - 1))) for k in range(half))
                  + tuple((800.0 * math.cos(-2.0 * math.pi * k / (half - 1)),
                           800.0 * math.sin(-2.0 * math.pi * k / (half - 1))) for k in range(half)))
        records = {f"z{k}": surface(f"z{k}", (0.0, 0.0), (256.0, 256.0), (10, 20, 30, 255),
                                    shape="polygon", ring=around) for k in range(40)}
        baker = GroundBaker(budget_s=None)
        baker.bake(records, None, (), 512.0, 512.0)
        assert baker.records_painted == TILE_VERTICES // vertices == 16
        assert baker._order[(0, 0)] == tuple(f"z{k}" for k in range(24, 40))  # noqa: SLF001
        assert baker.cover_vertices_read == TILE_VERTICES and baker.capped == frozenset({(0, 0)})

    def test_a_hole_or_an_edge_through_the_tile_is_no_cover(self, qtbot: Any) -> None:
        outer = box(550.0, 350.0)
        pond = tuple(reversed(box(100.0, 100.0)))  # a hole, clockwise, in the first tile's middle
        with_hole = Record(item_id="lawn", kind="LAWN", shape="polygon", footprints=(outer,),
                           holes=((tuple((x - 300.0, y - 100.0) for x, y in pond),),),
                           transform=Transform(550.0, 350.0),
                           material=Material("LAWN", fill_rgba=GREEN, paint=Paint()),
                           params=Params({"seed": "lawn"}))
        records = {"under": surface("under", (550.0, 350.0), (550.0, 350.0), (120, 80, 40, 255)),
                   "lawn": with_hole}
        baker, image = baked(records)
        # the lawn does not end the first tile's walk (the soil shows in its hole) …
        assert tuple(image[699 - 250, 250, :3]) == (120, 80, 40)
        assert baker.records_painted == 2 + 5 * 1  # … and does in the five tiles it covers whole
        assert not apart(image, unbounded(records, 1100.0, 700.0)).any()
        # an edge THROUGH a tile: the lawn is the whole plan but for a notch of 1.5 m at its
        # south-west corner — the first tile lies inside the lawn's box, its middle is lawn
        notched = ((-400.0, -350.0), (550.0, -350.0), (550.0, 350.0), (-550.0, 350.0), (-550.0, -200.0),
                   (-400.0, -200.0))
        records = {"under": surface("under", (550.0, 350.0), (550.0, 350.0), (120, 80, 40, 255)),
                   "lawn": surface("lawn", (0.0, 0.0), (550.0, 350.0), shape="polygon", ring=notched)}
        baker, image = baked(records)
        assert tuple(image[699 - 50, 50, :3]) == (120, 80, 40)  # in the notch: the soil
        assert tuple(image[699 - 256, 256, :3]) == GREEN[:3]  # the tile's middle: the lawn
        assert baker.records_painted == 2 + 5 * 1
        assert not apart(image, unbounded(records, 1100.0, 700.0)).any()

    def test_every_fill_pattern_is_opaque_and_a_translucent_one_would_be_seen(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whether a texture hides what is under it is READ off the brush, once per
        pattern: all 24 do. One that did not would not end a walk."""
        monkeypatch.setattr(ground_bake, "_OPAQUE_PATTERNS", {})
        assert all(ground_bake._pattern_is_opaque(pattern.name) for pattern in FillPattern)
        assert len(ground_bake._OPAQUE_PATTERNS) == len(FillPattern) == 25
        assert ground_bake._pattern_is_opaque(None) and ground_bake._pattern_is_opaque("NO_SUCH")

        def glassy(pattern: FillPattern, color: QColor) -> Any:
            from PyQt6.QtGui import QBrush

            sheet = QPixmap(8, 8)
            sheet.fill(QColor(color.red(), color.green(), color.blue(), 120))
            return QBrush(sheet)

        monkeypatch.setattr(ground_bake, "_OPAQUE_PATTERNS", {})
        monkeypatch.setattr(ground_bake, "create_pattern_brush", glassy)
        assert not ground_bake._pattern_is_opaque("GLASS")
        records = {"soil": surface("soil", (550.0, 350.0), (550.0, 350.0), (120, 80, 40, 255)),
                   "glass": surface("glass", (550.0, 350.0), (550.0, 350.0), (200, 220, 255, 255),
                                    pattern="GLASS")}
        baker, _image = baked(records)
        assert baker.records_painted == 6 * 2  # the soil under the glass is painted


# ── the time budget (review P1-4) ─────────────────────────────────────────────


class Ticks:
    """A clock that advances ``step`` seconds every time it is read."""

    def __init__(self, step: float = 1.0) -> None:
        self.step = step
        self.now = 0.0
        self.reads = 0

    def __call__(self) -> float:
        self.reads += 1
        self.now += self.step
        return self.now


def sixteen(shade: int = 0) -> dict[str, Record]:
    """One square in every tile of a 4 x 4 grid (2048 x 2048 cm)."""
    return {f"t{column}{row}": surface(f"t{column}{row}", (60.0, 60.0),
                                       (256.0 + 512.0 * column, 256.0 + 512.0 * row),
                                       (40 + 12 * column, 40 + 12 * row, shade, 255))
            for row in range(4) for column in range(4)}


def bake16(baker: GroundBaker, records: Mapping[str, Record],
           changes: SceneDiff | None = None) -> dict[tuple[int, int], GroundTile]:
    return {tile.key: tile for tile in baker.bake(records, changes, (), 2048.0, 2048.0)}


def finished(records: Mapping[str, Record]) -> dict[tuple[int, int], GroundTile]:
    return bake16(GroundBaker(budget_s=None), records)


class TestTheTimeBudget:
    def test_the_default_is_ten_milliseconds_and_a_reference_has_none(self) -> None:
        assert BAKE_BUDGET_S == 0.010 == GroundBaker().budget_s
        assert GroundBaker(budget_s=0.5).fresh().budget_s is None
        assert GroundBaker(budget_s=None).budget_s is None

    @pytest.mark.parametrize("budget", [-0.001, float("nan"), float("inf")])
    def test_a_budget_that_is_no_duration_is_refused(self, budget: float) -> None:
        with pytest.raises(ValueError, match="budget_s"):
            GroundBaker(budget_s=budget)

    def test_a_call_paints_until_the_budget_is_spent_and_hands_the_rest_back(self, qtbot: Any) -> None:
        """Sixteen tiles, each with one record; a clock that advances one second a
        reading and a budget of three: three tiles a call. The rest are PENDING —
        bare ground on the first call (there was no picture yet), afterwards the
        very objects they were."""
        clock = Ticks()
        baker = GroundBaker(budget_s=3.0, clock=clock)
        records = sixteen()
        want = finished(records)
        tiles = bake16(baker, records)
        assert len(baker.last_repainted) == 3 and baker.pending == 13
        assert clock.reads == 1 + 3  # once before the first tile, once after each
        for key, tile in tiles.items():
            if key in baker.pending_tiles:
                assert np.all(np.frombuffer(tile.pixels, np.uint8).reshape(-1, 4)[:, :3] == BARE)
            else:
                assert tile.pixels == want[key].pixels
        passes = 1
        while baker.pending:
            before = tiles
            pending_before = set(baker.pending_tiles)
            tiles = bake16(baker, records, SceneDiff())  # nothing new: it goes on
            passes += 1
            assert baker.last_examined == 0  # a continuation looks at no record
            assert set(baker.last_repainted) <= pending_before
            assert len(baker.last_repainted) == min(3, len(pending_before))
            for key, tile in tiles.items():
                if key not in baker.last_repainted:
                    assert tile is before[key]  # stale or finished: the same object
        assert passes == 6  # 3 + 3 + 3 + 3 + 3 + 1
        assert all(tiles[key].pixels == want[key].pixels for key in want)
        idle = bake16(baker, records, SceneDiff())
        assert baker.last_repainted == () and all(idle[key] is tiles[key] for key in tiles)

    def test_a_budget_of_nothing_still_paints_one_tile_a_call(self, qtbot: Any) -> None:
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records = sixteen()
        bake16(baker, records)
        assert len(baker.last_repainted) == 1 and baker.pending == 15
        for left in range(14, -1, -1):
            bake16(baker, records, SceneDiff())
            assert len(baker.last_repainted) == 1 and baker.pending == left

    def test_a_tile_without_records_is_never_pending(self, qtbot: Any) -> None:
        """Bare ground costs nothing: it is not left for another pass."""
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records = {key: record for key, record in sixteen().items() if key in ("t00", "t33")}
        tiles = bake16(baker, records)
        assert baker.pending == 1 and len(baker.last_repainted) == 15  # 14 bare ones and one square
        assert baker.records_painted == 1
        bake16(baker, records, SceneDiff())
        assert baker.pending == 0 and len(tiles) == 16

    def test_the_tiles_nearest_to_the_last_edit_come_first(self, qtbot: Any) -> None:
        baker = GroundBaker(budget_s=3.0, clock=Ticks())
        records = sixteen()
        bake16(baker, records)
        # the whole plan is the first "edit": from its middle outward
        assert set(baker.last_repainted) <= {(1, 1), (2, 1), (1, 2), (2, 2)}
        moved = dict(records)
        moved["t30"] = surface("t30", (60.0, 60.0), (1800.0, 250.0), (255, 0, 0, 255))  # the south-east tile
        bake16(baker, moved, diff(records, moved))
        assert baker.last_repainted[0] == (3, 0)  # the edit itself, before the backlog
        assert set(baker.last_repainted[1:]) <= {(2, 0), (3, 1), (2, 1)}  # then its neighbours
        bake16(baker, moved, SceneDiff())
        # … and the pass after still works outward from that edit
        assert all(abs(column - 3) + row <= 3 for column, row in baker.last_repainted)

    def test_an_edit_while_work_is_pending_looks_only_at_what_it_touches(self, qtbot: Any) -> None:
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records = sixteen()
        bake16(baker, records)
        checks = baker.admission_checks
        assert checks == 16  # one record, one tile, sixteen times
        moved = dict(records)
        moved["t03"] = surface("t03", (60.0, 60.0), (250.0, 1800.0), (255, 0, 0, 255))
        tiles = bake16(baker, moved, diff(records, moved))
        # ONE record is looked at; its ONE tile is asked about each of the 16 records —
        # and none of the fourteen tiles that are still pending is admitted again
        assert baker.last_examined == 1 and baker.admission_checks - checks == 16
        # the edit's tile first — and one tile of the backlog, so that it cannot starve
        assert baker.last_repainted[0] == (0, 3) and len(baker.last_repainted) == 2
        assert baker.pending == 13
        assert tiles[(0, 3)].pixels == finished(moved)[(0, 3)].pixels

    def test_a_record_that_goes_while_its_tile_is_pending(self, qtbot: Any) -> None:
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records = sixteen()
        bake16(baker, records)
        fewer = {key: record for key, record in records.items() if key not in ("t33", "t32")}
        tiles = bake16(baker, fewer, diff(records, fewer))
        while baker.pending:
            tiles = bake16(baker, fewer, SceneDiff())
        want = finished(fewer)
        assert all(tiles[key].pixels == want[key].pixels for key in want)
        assert baker.painted_ids() == tuple(fewer) and baker.failures == {}

    def test_a_reorder_while_work_is_pending(self, qtbot: Any) -> None:
        """Two records in one tile swap places before the tile was ever painted:
        what the tile waits to be painted with is found again."""
        below = surface("below", (200.0, 200.0), (1800.0, 1800.0), (200, 0, 0, 255))
        above = surface("above", (150.0, 150.0), (1800.0, 1800.0), (0, 0, 200, 255))
        first = {**sixteen(), "below": below, "above": above}
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        bake16(baker, first)
        assert (3, 3) in baker.pending_tiles
        swapped = {key: record for key, record in first.items() if key != "below"} | {"below": below}
        changes = diff(first, swapped)
        assert changes.reordered and not changes.touches_sink
        tiles = bake16(baker, swapped, changes)
        while baker.pending:
            tiles = bake16(baker, swapped, SceneDiff())
        want = finished(swapped)
        assert all(tiles[key].pixels == want[key].pixels for key in want)

    def test_an_edit_a_pass_does_not_starve_the_backlog(self, qtbot: Any) -> None:
        """Review 2: with one tile a pass and an edit before every pass, the edit's
        tile was painted and the budget was spent — pending stayed at 14 after 1,
        5, 10, 20 and 40 edits. A call that brings an edit while older tiles wait
        paints the edit's tiles AND one tile of the backlog: the budget plus two
        tiles a pass, and the backlog is gone after as many passes as it has tiles."""
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records: dict[str, Record] = sixteen()
        bake16(baker, records)
        assert baker.pending == 15 and baker.last_repainted == ((1, 1),)
        left = []
        for edit in range(1, 16):
            new = dict(records)
            # the square of the tile painted first, moved a little: an edit that is not backlog
            new["t11"] = surface("t11", (60.0, 60.0), (700.0 + edit, 700.0), (255, 0, 0, 255))
            tiles = bake16(baker, new, diff(records, new))
            records = new
            assert baker.last_examined == 1
            assert baker.last_repainted[0] == (1, 1) and len(baker.last_repainted) == 2
            left.append(baker.pending)
            assert tiles[(1, 1)].pixels == finished(records)[(1, 1)].pixels  # the edit itself is shown
        assert left == list(range(14, -1, -1))
        want = finished(records)
        assert all(tile.pixels == want[tile.key].pixels for tile in baker.tiles())

    def test_an_edit_in_a_pending_tile_is_no_backlog(self, qtbot: Any) -> None:
        """… and the edit's own tile does not count as the backlog's turn."""
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records: dict[str, Record] = sixteen()
        bake16(baker, records)
        new = dict(records)
        new["t33"] = surface("t33", (60.0, 60.0), (1800.0, 1800.0), (255, 0, 0, 255))  # still pending
        bake16(baker, new, diff(records, new))
        assert baker.last_repainted[0] == (3, 3) and len(baker.last_repainted) == 2
        assert baker.pending == 13

    def test_an_edits_own_tiles_come_before_the_backlog(self, qtbot: Any) -> None:
        """An edit that touches two tiles far apart has its middle BETWEEN them —
        where an older pending tile may lie. Sorted by distance alone, that tile was
        painted first, the budget was spent, and the edit was not shown in its own
        pass. This call's tiles come first; the backlog's one tile after them."""
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records: dict[str, Record] = sixteen()
        bake16(baker, records)
        assert baker.pending == 15 and baker.last_repainted == ((1, 1),)
        new = dict(records)
        new["t00"] = surface("t00", (60.0, 60.0), (250.0, 250.0), (255, 0, 0, 255))
        new["t22"] = surface("t22", (60.0, 60.0), (1290.0, 1290.0), (255, 0, 0, 255))
        tiles = bake16(baker, new, diff(records, new))
        first, second = baker.last_repainted  # the middle of the edit is tile (1, 1)
        assert first in ((0, 0), (2, 2)) and second not in ((0, 0), (2, 2))
        assert tiles[first].pixels == finished(new)[first].pixels and baker.pending == 13

    def test_clear_drops_the_pending_work_with_the_tiles(self, qtbot: Any) -> None:
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        bake16(baker, sixteen())
        assert baker.pending == 15
        baker.clear()
        assert baker.pending == 0 and baker.pending_tiles == () and baker.tiles() == ()
        bake16(baker, {})
        assert baker.pending == 0 and len(baker.tiles()) == 16

    @pytest.mark.parametrize("seed", [1, 2, 3])
    def test_the_same_tiles_once_nothing_is_pending_with_a_diff_or_without(
            self, qtbot: Any, seed: int) -> None:
        """Forty random edits — moves, recolours, removals, additions, reorders —
        through three bakers at once: one tile a call with the diff, one tile a
        call WITHOUT a diff, and no budget at all. After every call of the first:
        a tile that is not pending IS the finished picture of the records as they
        are now, and a pending one is the object it was. At the end, all three
        hold the tiles of one bake of the last records."""
        rng = random.Random(seed)
        records: dict[str, Record] = sixteen()
        told = GroundBaker(budget_s=0.0, clock=Ticks())
        untold = GroundBaker(budget_s=0.0, clock=Ticks())
        plain = GroundBaker(budget_s=None)
        shown = bake16(told, records)
        bake16(untold, records)
        bake16(plain, records)
        fresh_id = 0
        for _step in range(40):
            new = dict(records)
            keys = list(new)
            what = rng.choice(["move", "recolour", "remove", "add", "reorder", "nothing"])
            if what == "move" and keys:
                key = rng.choice(keys)
                new[key] = surface(key, (rng.uniform(30.0, 300.0), rng.uniform(30.0, 300.0)),
                                   (rng.uniform(0.0, 2048.0), rng.uniform(0.0, 2048.0)),
                                   new[key].material.fill_rgba or GREEN, turn=rng.choice([0.0, 33.0]))
            elif what == "recolour" and keys:
                key = rng.choice(keys)
                record = new[key]
                new[key] = surface(key, (record.footprints[0][1][0], record.footprints[0][2][1]),
                                   (record.transform.east_cm, record.transform.north_cm),
                                   (rng.randrange(256), rng.randrange(256), 90, rng.choice([255, 255, 120])),
                                   turn=record.transform.rotation_deg)
            elif what == "remove" and len(keys) > 3:
                del new[rng.choice(keys)]
            elif what == "add":
                fresh_id += 1
                key = f"new{fresh_id}"
                new[key] = surface(key, (rng.uniform(30.0, 700.0), rng.uniform(30.0, 700.0)),
                                   (rng.uniform(0.0, 2048.0), rng.uniform(0.0, 2048.0)),
                                   (rng.randrange(256), 30, 200, 255))
            elif what == "reorder" and len(keys) > 1:
                rng.shuffle(keys)
                new = {key: new[key] for key in keys}
            before = shown
            shown = bake16(told, new, diff(records, new))
            bake16(untold, new, None)
            bake16(plain, new, diff(records, new))
            records = new
            want = finished(records)
            assert plain.pending == 0
            for key, tile in shown.items():
                if key in told.pending_tiles:
                    assert tile is before[key], (what, key)  # stale: the object it was
                else:
                    assert tile.pixels == want[key].pixels, (what, key)  # never wrong
        for baker in (told, untold):
            calls = 0
            while baker.pending:
                bake16(baker, records, SceneDiff() if baker is told else None)
                calls += 1
                assert calls <= 16
        want = finished(records)
        for baker in (told, untold, plain):
            assert baker.pending == 0
            assert all(tile.pixels == want[tile.key].pixels for tile in baker.tiles())
            assert baker.painted_ids() and set(baker.painted_ids()) <= set(records)

    def test_the_pipeline_shows_stale_tiles_and_catches_up(self, qtbot: Any) -> None:
        """Through ``SceneSync`` and a real scene: with one tile a pass the sink
        first shows bare ground where the bake has not been, ``ground_pending``
        says so, and after the passes the engine's state is the reference's."""
        from open_garden_planner.core import ProjectManager
        from open_garden_planner.core.scene3d.builders import production_registry
        from tests.integration.test_scene3d_ground_bake import PLANS

        scene = CanvasScene()
        ProjectManager().load(scene, PLANS / "bench_small.ogp")
        bake = Bake(scene, registry=production_registry(), baker=GroundBaker(budget_s=0.0, clock=Ticks()))
        bake.step()
        assert bake.sync.ground_pending and bake.baker.pending > 3
        assert bake.sink.state().ground != bake.sync.expected_state().ground
        assert bake.sink.state().items == bake.sync.expected_state().items  # the solids are all there
        first_pending = bake.baker.pending
        passes = bake.finish()
        assert passes == first_pending and not bake.sync.ground_pending
        assert bake.sink.state() == bake.sync.expected_state()
        whole = Bake(scene, registry=production_registry())
        whole.step()
        assert all(mine.pixels == theirs.pixels for mine, theirs in zip(bake.tiles, whole.tiles, strict=True))


# ── a tile that cannot be painted (review 2, P2-1) ────────────────────────────


class Brittle(GroundBaker):
    """A baker that has no image for the tiles in ``broken`` — and counts what it tried."""

    def __init__(self, **settings: Any) -> None:
        super().__init__(**settings)
        self.broken: set[tuple[int, int]] = set()
        self.attempts: list[tuple[int, int]] = []

    def _paint_tile(self, grid: Any, key: tuple[int, int], records: Any, capped: bool) -> GroundTile:
        self.attempts.append(key)
        if key in self.broken and records:
            raise MemoryError(f"no image for ground tile {key}")
        return super()._paint_tile(grid, key, records, capped)


def painted_tiles(tiles: Any) -> int:
    """Tiles that show something: not all bare ground."""
    return sum(1 for tile in tiles
               if np.any(np.frombuffer(tile.pixels, np.uint8).reshape(-1, 4)[:, :3] != BARE))


class TestATileThatCannotBePainted:
    def test_it_keeps_its_picture_and_takes_nothing_else_with_it(
            self, qtbot: Any, caplog: pytest.LogCaptureFixture) -> None:
        """Review 2: sixteen tiles, one tile a pass, no image for tile (3, 3). The
        failing bake left the sink its sixteen painted tiles — and the NEXT edit,
        in tile (0, 0), took it to ONE: the baker had been cleared, and every edit
        after it cost sixteen tile paints, fifteen passes and a traceback. Now the
        bake does not raise: the tile keeps the picture it had, is listed, is not
        pending, and is tried once more by a call that brings a change."""
        from open_garden_planner.core.scene3d import GroundSpec, RecordingSink, SceneSync

        baker = Brittle(budget_s=0.0, clock=Ticks())
        sink = RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        plan = GroundSpec(2048.0, 2048.0)
        records: dict[str, Record] = sixteen()
        sync.apply(records, ground=plan)
        while sync.ground_pending:
            sync.continue_ground()
        shown = {tile.key: tile for tile in sink.ground.tiles}
        assert painted_tiles(sink.ground.tiles) == 16

        baker.broken = {(3, 3)}
        baker.attempts.clear()
        edited = {**records, "t33": surface("t33", (60.0, 60.0), (1792.0, 1792.0), (255, 0, 0, 255))}
        with caplog.at_level("ERROR"):
            sync.apply(edited)
        assert baker.attempts == [(3, 3)]
        assert baker.tile_failures == {(3, 3): ("MemoryError", "no image for ground tile (3, 3)")}
        assert sync.ground_failure is None and not sync.poisoned  # the bake did not raise
        assert not sync.ground_pending and baker.pending == 0  # … and no pass retries it on its own
        assert all(tile is shown[tile.key] for tile in sink.ground.tiles)  # stale there, the same elsewhere
        assert painted_tiles(sink.ground.tiles) == 16
        assert caplog.text.count("could not be painted") == 1

        # the next edit, in tile (0, 0): its tile, and one more try for the broken one
        baker.attempts.clear()
        moved = {**edited, "t00": surface("t00", (60.0, 60.0), (250.0, 250.0), (0, 0, 255, 255))}
        with caplog.at_level("ERROR"):
            sync.apply(moved)
        assert sorted(baker.attempts) == [(0, 0), (3, 3)] and not sync.ground_pending
        assert painted_tiles(sink.ground.tiles) == 16  # 1 before
        now = {tile.key: tile for tile in sink.ground.tiles}
        assert now[(3, 3)] is shown[(3, 3)] and now[(0, 0)] is not shown[(0, 0)]
        assert all(now[key] is shown[key] for key in shown if key not in ((0, 0),))

        # ten edits elsewhere: two tile paints each (16 before), one pass (15), no further log line
        records = moved
        for edit in range(10):
            baker.attempts.clear()
            new = {**records, "t11": surface("t11", (60.0, 60.0), (700.0 + edit, 700.0), (0, 255, 0, 255))}
            with caplog.at_level("ERROR"):
                sync.apply(new)
            records = new
            assert sorted(baker.attempts) == [(1, 1), (3, 3)] and not sync.ground_pending
            assert painted_tiles(sink.ground.tiles) == 16
        assert caplog.text.count("could not be painted") == 1
        # an idle tick and a continuation try nothing
        baker.attempts.clear()
        assert sync.apply(records).is_empty and sync.continue_ground() is False
        assert baker.attempts == []

        # the tile can be painted again: the next change heals it, and the ground is whole
        baker.broken = set()
        healed = {**records, "t22": surface("t22", (60.0, 60.0), (1290.0, 1290.0), (0, 255, 255, 255))}
        sync.apply(healed)
        assert baker.tile_failures == {} and not sync.ground_pending
        assert sink.state() == sync.expected_state()

    def test_a_bake_that_raises_anywhere_else_does_not_blank_the_ground_either(
            self, qtbot: Any, caplog: pytest.LogCaptureFixture) -> None:
        """The same sixteen tiles, and a bake that raises OUTSIDE a tile's paint — in
        the walk that hands tiles their records. Its books cannot be trusted any
        more, so the sync RESTARTS the baker: the books are forgotten, the pictures
        kept. (It used to clear it: the edit after the failure showed ONE painted
        tile.) Every tile is painted anew over the passes that follow; one the
        baker has not reached is the very object the sink shows — and a tile whose
        record went away in the meantime is bare at once."""
        from open_garden_planner.core.scene3d import GroundSpec, RecordingSink, SceneSync

        class Flaky(Brittle):
            fail_next = False

            def _admit(self, grid: Any, records: Any, dirty: Any) -> Any:
                if self.fail_next:
                    self.fail_next = False
                    raise MemoryError("no memory for the walk")
                return super()._admit(grid, records, dirty)

        baker = Flaky(budget_s=0.0, clock=Ticks())
        sink = RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        records: dict[str, Record] = sixteen()
        sync.apply(records, ground=GroundSpec(2048.0, 2048.0))
        while sync.continue_ground():
            pass
        shown = {tile.key: tile for tile in sink.ground.tiles}
        assert painted_tiles(sink.ground.tiles) == 16

        baker.fail_next = True
        edited = {**records, "t33": surface("t33", (60.0, 60.0), (1792.0, 1792.0), (255, 0, 0, 255))}
        with caplog.at_level("ERROR"):
            sync.apply(edited)
        assert sync.ground_failure == ("MemoryError", "no memory for the walk")
        assert all(tile is shown[tile.key] for tile in sink.ground.tiles)  # the ground stays
        assert baker.entries_held() == 0 and baker.pending == 0  # the books are gone …

        # the edit after the failure: the square of tile (2, 2) is deleted
        baker.attempts.clear()
        gone = {key: record for key, record in edited.items() if key != "t22"}
        sync.apply(gone)
        assert sync.ground_failure is None
        now = {tile.key: tile for tile in sink.ground.tiles}
        assert painted_tiles(sink.ground.tiles) == 15  # … the pictures are not (1 before)
        assert np.all(np.frombuffer(now[(2, 2)].pixels, np.uint8).reshape(-1, 4)[:, :3] == BARE)
        assert all(now[key] is shown[key] for key in shown if key != (2, 2))
        assert baker.pending == 14 and sync.ground_pending
        passes = 1
        while sync.ground_pending:
            sync.continue_ground()
            passes += 1
        final = {tile.key: tile for tile in sink.ground.tiles}
        assert passes == 15 and sorted(baker.attempts) == sorted(shown)  # every tile once: one a pass
        assert sink.state() == sync.expected_state()
        # the same picture again is the same tile: only the two edited tiles are new objects
        assert {key for key in shown if final[key] is not shown[key]} == {(2, 2), (3, 3)}

    def test_a_hole_in_the_books_is_not_a_tile_that_could_not_be_painted(self, qtbot: Any) -> None:
        """Only a tile's PAINT is contained. A pending tile that names a record the
        baker no longer holds is a hole in the books — a bug: it raises (and the sync
        restarts the baker); it is not parked as if its image could not be made."""
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        records = sixteen()
        bake16(baker, records)
        assert baker.pending == 15
        del baker._painted["t33"]  # noqa: SLF001 - the hole
        with pytest.raises(KeyError, match="t33"):
            while baker.pending:
                bake16(baker, records, SceneDiff())
        assert baker.tile_failures == {}

    def test_a_restart_on_another_plan_drops_the_pictures_and_so_does_clear(self, qtbot: Any) -> None:
        def drained(baker: GroundBaker) -> None:
            while True:
                bake16(baker, records)
                if not baker.pending:
                    return

        records = sixteen()
        baker = GroundBaker(budget_s=0.0, clock=Ticks())
        drained(baker)
        baker.restart()
        assert baker.tiles() == () and baker.entries_held() == 0
        assert painted_tiles(bake16(baker, records).values()) == 16  # the pictures were kept …
        drained(baker)
        baker.restart()
        baker.clear()  # … clear() after a restart forgets them: a new plan starts bare
        assert painted_tiles(bake16(baker, records).values()) == 1
        drained(baker)
        baker.restart()
        tiles = baker.bake(records, None, (), 1024.0, 1024.0)  # another plan rectangle: its own grid
        assert len(tiles) == 4 and painted_tiles(tiles) == 1 and baker.pending == 3

    def test_a_tile_that_was_never_painted_is_bare_until_it_can_be(self, qtbot: Any) -> None:
        baker = Brittle(budget_s=None)
        baker.broken = {(2, 1)}
        records = sixteen()
        tiles = bake16(baker, records)
        want = finished(records)
        assert baker.tile_failures.keys() == {(2, 1)} and baker.pending == 0
        assert painted_tiles(tiles.values()) == 15
        assert all(tiles[key].pixels == want[key].pixels for key in want if key != (2, 1))
        again = bake16(baker, records, SceneDiff())  # no change: not tried, the same objects
        assert baker.attempts.count((2, 1)) == 1 and all(again[key] is tiles[key] for key in tiles)
        baker.broken = set()
        healed = bake16(baker, records, None)  # a caller that cannot say what changed: tried again
        assert baker.tile_failures == {} and healed[(2, 1)].pixels == want[(2, 1)].pixels
        baker.clear()
        assert baker.tile_failures == {} and baker.entries_held() == 0

    def test_a_reorder_reaches_a_tile_that_waits_after_a_failure(self, qtbot: Any) -> None:
        """What a failed tile waits to be painted with is kept like a pending tile's —
        and found again when the records swap places."""
        below = surface("below", (200.0, 200.0), (1800.0, 1800.0), (200, 0, 0, 255))
        above = surface("above", (150.0, 150.0), (1800.0, 1800.0), (0, 0, 200, 255))
        first = {**sixteen(), "below": below, "above": above}
        baker = Brittle(budget_s=None)
        baker.broken = {(3, 3)}
        bake16(baker, first)
        swapped = {key: record for key, record in first.items() if key != "below"} | {"below": below}
        baker.broken = set()
        tiles = bake16(baker, swapped, diff(first, swapped))
        assert tiles[(3, 3)].pixels == finished(swapped)[(3, 3)].pixels and baker.tile_failures == {}


# ── a painter that raises (review P2-2, P2-3) ─────────────────────────────────


def stones(item_id: str, at: tuple[float, float], length: float = 300.0) -> Record:
    return Record(item_id=item_id, kind="PATH", shape="polyline", footprints=(),
                  transform=Transform(*at), path=((-length / 2.0, -20.0), (length / 2.0, 30.0)),
                  path_width_cm=30.0,
                  material=Material("PATH", stroke_rgba=(120, 110, 100, 255), paint=Paint()),
                  params=Params({"seed": item_id, "path_style": "STEPPING_STONES"}))


class FailsAt:
    """``QColor`` for ``path_style_paint`` that raises the n-th time it is asked —
    inside a stone's own ``save()``, after the painter was moved and turned to it."""

    def __init__(self, at: int) -> None:
        self.at = at
        self.calls = 0

    def __call__(self, *args: Any) -> QColor:
        self.calls += 1
        if self.calls == self.at:
            raise RuntimeError(f"stone {self.calls}")
        return QColor(*args)


class TestAPainterThatRaises:
    def test_the_record_painted_after_it_is_painted_as_if_it_had_not_been_there(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A stepping-stones path that raises at its third stone leaves the painter
        two ``save()`` levels deep, turned and moved to that stone. Its ONE
        ``restore()`` then popped the wrong level, and the rectangle painted next
        lost 5,476 of 44,104 px. Pose and opacity are set absolutely for every
        record, and the painter of a failing record is ended."""
        patio = surface("patio", (105.0, 105.0), (260.0, 250.0), (200, 60, 30, 255), turn=20.0,
                        kind="TERRACE_PATIO")
        records = {"path": stones("path", (250.0, 250.0)), "patio": patio}
        alone, expected = baked({"patio": patio}, 512.0, 512.0)
        assert alone.failures == {}
        # the patio's own pixels (its antialiased rim blends with whatever lies under it)
        area = np.all(expected[..., :3] == np.array((200, 60, 30)), axis=2)
        assert int(area.sum()) > 43_000

        monkeypatch.setattr(style_paint, "QColor", FailsAt(3))
        baker, image = baked(records, 512.0, 512.0)
        assert baker.failures == {"path": ("RuntimeError", "stone 3")}
        assert int(np.any(image[area][:, :3] != expected[area][:, :3], axis=1).sum()) == 0
        # the failing item is cut off where it failed: its first two stones are there
        beside = np.any(image[..., :3] != BARE, axis=2) & np.all(expected[..., :3] == BARE, axis=2)
        assert 100 < int(beside.sum()) < 2 * 24 * 18 + 200

    def test_paint_record_leaves_the_painter_as_it_found_it_when_it_raises(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        image = QImage(512, 512, FORMAT)
        painter = QPainter(image)
        found = QTransform(1.0, 0.0, 0.0, -1.0, 7.0, 500.0)
        painter.setWorldTransform(found)
        painter.setOpacity(0.75)
        monkeypatch.setattr(style_paint, "QColor", FailsAt(3))
        try:
            with pytest.raises(RuntimeError, match="stone 3"):
                paint_record(painter, stones("path", (250.0, 250.0)))
            assert painter.worldTransform() == found and painter.opacity() == 0.75
        finally:
            painter.end()

    def test_a_failure_in_any_tile_is_a_failure_of_the_item(
            self, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """A path across two tiles fails in the first one painted and paints cleanly
        in the second: ``failures.pop`` ran per tile and reported nothing. The
        failure stays until the tile it happened in is painted without it."""
        path = stones("path", (512.0, 250.0), length=600.0)  # across the border at east 512
        monkeypatch.setattr(style_paint, "QColor", FailsAt(3))
        baker = GroundBaker(budget_s=None)
        baker.bake({"path": path}, None, (), 1024.0, 512.0)
        assert baker.last_repainted == ((0, 0), (1, 0))  # the failing tile first, then a clean one
        assert baker.failures == {"path": ("RuntimeError", "stone 3")}
        # the item is edited and paints cleanly everywhere: the failure goes
        moved = stones("path", (512.0, 260.0), length=600.0)
        baker.bake({"path": moved}, SceneDiff(transform=("path",)), (), 1024.0, 512.0)
        assert baker.failures == {}
        # … and a failing item that leaves the ground takes its failure with it
        monkeypatch.setattr(style_paint, "QColor", FailsAt(1))
        baker.bake({"path": path}, SceneDiff(transform=("path",)), (), 1024.0, 512.0)
        assert "path" in baker.failures
        baker.bake({}, SceneDiff(removed=("path",)), (), 1024.0, 512.0)
        assert baker.failures == {}

    def test_the_failure_is_logged_once(self, qtbot: Any, monkeypatch: pytest.MonkeyPatch,
                                        caplog: pytest.LogCaptureFixture) -> None:
        class Always:
            def __call__(self, *args: Any) -> QColor:
                raise RuntimeError("no colour")

        monkeypatch.setattr(style_paint, "QColor", Always())
        baker = GroundBaker(budget_s=None)
        with caplog.at_level("ERROR"):
            for shift in range(4):
                baker.bake({"path": stones("path", (250.0 + shift, 250.0))}, None, (), 512.0, 512.0)
        assert caplog.text.count("could not be painted") == 1 and "path" in baker.failures


# ── a mitred join reaches two pen widths (review P2-6) ────────────────────────


class TestTheTipOfAHairpin:
    def test_the_tile_a_mitred_tip_pokes_into_paints_it(self, qtbot: Any) -> None:
        """A stone wall strokes its base with a MITRED join: at a hairpin of 30° the
        tip lies 1.93 pen widths from the corner — 87 cm at 45 cm. With a reach of
        1.5 widths the tile it pokes into did not list the path, and the tip was cut
        off at the border (26 px, measured by the review)."""
        scene = CanvasScene(width_cm=1100.0, height_cm=700.0)
        corner = QPointF(437.0, 300.0)  # the tip points east, across the border at east 512
        reach = 200.0
        legs = [QPointF(corner.x() - reach * math.cos(math.radians(15.0)),
                        corner.y() + sign * reach * math.sin(math.radians(15.0))) for sign in (1.0, -1.0)]
        item = PolylineItem([legs[0], corner, legs[1]], object_type=ObjectType.PATH,
                            path_fence_style=PathFenceStyle.STONE_WALL)
        pen = item.pen()
        pen.setWidthF(45.0)
        adopt_pen(item, pen)
        scene.addItem(item)
        bake = Bake(scene, bare_rgb=canvas_rgb())
        bake.step()
        record = bake.records[str(item.item_id)]
        bounds = paint_bounds(record)
        assert bounds is not None and bounds[2] >= 437.0 + 2.0 * 45.0  # the pen's own mitre limit
        assert 437.0 + 1.5 * 45.0 + 6.0 < 512.0  # … where 1.5 widths did not reach the next tile
        assert QPen().miterLimit() == 2.0 == ground_bake._MITRE_LIMIT
        reference = canvas_render(scene, bake.grid)
        painted = np.any(reference[:, 512:, :3] != np.array(canvas_rgb()), axis=2)
        assert int(painted.sum()) > 20  # control: the canvas does paint a tip beyond the border
        assert (1, 0) in bake.baker.last_repainted
        delta = np.abs(bake.image()[..., :3] - reference[..., :3]).max(axis=2)
        assert int((delta[:, 512:] > 8).sum()) == 0

    def test_a_mitred_outline_reaches_as_far(self, qtbot: Any) -> None:
        plain = surface("a", (50.0, 50.0), (200.0, 200.0))
        mitred = Record(item_id="a", kind="LAWN", shape="rectangle", footprints=(box(50.0, 50.0),),
                        transform=Transform(200.0, 200.0),
                        material=Material("LAWN", fill_rgba=GREEN, stroke_rgba=(0, 0, 0, 255),
                                          paint=Paint(stroke_width_cm=10.0, stroke_join="MiterJoin")),
                        params=Params({"seed": "a"}))
        bevelled = Record(item_id="a", kind="LAWN", shape="rectangle", footprints=(box(50.0, 50.0),),
                          transform=Transform(200.0, 200.0),
                          material=Material("LAWN", fill_rgba=GREEN, stroke_rgba=(0, 0, 0, 255),
                                            paint=Paint(stroke_width_cm=10.0)),
                          params=Params({"seed": "a"}))
        plain_east = paint_bounds(plain)[2]  # type: ignore[index]
        assert paint_bounds(bevelled)[2] - plain_east == 10.0  # type: ignore[index]
        assert paint_bounds(mitred)[2] - plain_east == 20.0  # type: ignore[index]


# ── one conversion a tick (review P2-4) ───────────────────────────────────────


def test_a_flat_item_the_solid_path_refuses_is_converted_once_a_tick(
        qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """A lawn of 16,384 vertices and a path of 16,384 points have no regions (the
    solid path refuses them) and are painted from what was drawn. Their outline
    was moved into the record's frame TWICE per tick — once to be refused, once
    to be kept (24 to 43 ms an idle tick, measured by the review). Once."""
    from open_garden_planner.core.scene3d import LocalFrame

    converted: list[int] = []
    real = LocalFrame.local_ring

    def counted(self: Any, points: Any) -> Any:
        converted.append(len(points))
        return real(self, points)

    monkeypatch.setattr(LocalFrame, "local_ring", counted)
    scene = CanvasScene(width_cm=2400.0, height_cm=1600.0)
    ring = [QPointF(1200.0 + 1100.0 * math.cos(2.0 * math.pi * k / 16_384) * (1.0 + 0.05 * (k % 2)),
                    800.0 + 700.0 * math.sin(2.0 * math.pi * k / 16_384) * (1.0 + 0.05 * (k % 2)))
            for k in range(16_384)]
    lawn = PolygonItem(ring, object_type=ObjectType.LAWN)
    line = PolylineItem([QPointF(10.0 + 2380.0 * (k % 2), 10.0 + 1580.0 * k / 16_383) for k in range(16_384)],
                        object_type=ObjectType.PATH)
    scene.addItem(lawn)
    scene.addItem(line)
    bake = Bake(scene)
    bake.step()
    for item in (lawn, line):
        record = bake.records[str(item.item_id)]
        assert record.footprints == ()  # refused by the solid path — painted as drawn
    assert bake.skipped == [] and len(bake.baker.painted_ids()) == 2
    assert converted == [16_384, 16_384]
    converted.clear()
    assert bake.step().is_empty  # an idle tick
    assert converted == [16_384, 16_384]
