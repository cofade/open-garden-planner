"""The Qt-free half of the ground bake (Phase 17 L1.5, #385): the tile grid, the
tile, a record's paint description, and the seam through which ``SceneSync``
keeps the ground in step with the snapshot — driven here by a baker double, so
nothing in this file needs a painter.
"""

from __future__ import annotations

import ast
import dataclasses
from collections.abc import Collection, Mapping
from pathlib import Path

import pytest

from open_garden_planner.core.scene3d import (
    MAX_GROUND_PIXELS,
    MEADOW_RGB,
    PARAM_PAINT_ORIGIN,
    TILE_PX,
    BuilderRegistry,
    GroundBaking,
    GroundGrid,
    GroundSpec,
    GroundTile,
    Material,
    MeshPart,
    Paint,
    Params,
    Record,
    RecordingSink,
    RecordRangeError,
    SceneDiff,
    SceneSync,
    SunState,
    Transform,
    changed_tiles,
    prism_mesh,
)
from open_garden_planner.core.scene3d.sync import SyncStateError

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))


def tile(column: int = 0, row: int = 0, shade: int = 0, side: int = 2) -> GroundTile:
    return GroundTile(column, row, column * 100.0, row * 100.0, 100.0, 100.0, side, side,
                      bytes([shade, shade, shade, 255]) * (side * side))


def flat(item_id: str, east: float = 0.0, north: float = 0.0, **changes: object) -> Record:
    base = Record(item_id=item_id, kind="LAWN", shape="rectangle", footprints=(SQUARE,),
                  transform=Transform(east, north),
                  material=Material("LAWN", fill_rgba=(60, 130, 30, 255), pattern="GRASS",
                                    paint=Paint(stroke_width_cm=2.0)),
                  params=Params({"seed": item_id}))
    return dataclasses.replace(base, **changes) if changes else base


def solid(item_id: str, east: float = 0.0, north: float = 0.0, height: float = 80.0) -> Record:
    return Record(item_id=item_id, kind="SHED", shape="rectangle", footprints=(SQUARE,),
                  transform=Transform(east, north), material=Material("SHED"),
                  height_cm=height, params=Params({"seed": item_id}))


# ── the grid ──────────────────────────────────────────────────────────────────


class TestGroundGrid:
    def test_the_constants_are_the_measured_ones(self) -> None:
        assert TILE_PX == 512 and MAX_GROUND_PIXELS == 4096 * 4096
        assert MEADOW_RGB == (0x48, 0x7F, 0x34)

    @pytest.mark.parametrize(("width", "depth", "scale", "columns", "rows"), [
        (2400.0, 1600.0, 1.0, 5, 4),      # bench_small: 24 x 16 m
        (5000.0, 3000.0, 1.0, 10, 6),     # bench_large: 15 million pixels, inside the bound
        (512.0, 512.0, 1.0, 1, 1),
        (513.0, 1.0, 1.0, 2, 1),
        (10000.0, 10000.0, 0.25, 5, 5),   # 100 x 100 m: 1 and 1/2 px/cm are over the bound
        (1.0e6, 1.0e6, 2.0 ** -8, 8, 8),  # the largest plan a record can lie on
    ])
    def test_the_finest_power_of_one_half_that_fits(self, width: float, depth: float,
                                                    scale: float, columns: int, rows: int) -> None:
        grid = GroundGrid.for_plan(width, depth)
        assert grid.px_per_cm == scale
        assert (grid.columns, grid.rows) == (columns, rows)
        assert grid.width_px * grid.height_px <= MAX_GROUND_PIXELS
        assert grid.tile_count == columns * rows == len(list(grid.tile_keys()))
        if scale < 1.0:  # … and the next finer one would not have fitted
            assert (width * scale * 2) * (depth * scale * 2) > MAX_GROUND_PIXELS

    def test_the_tiles_are_crops_of_one_pixel_grid(self) -> None:
        """No pixel belongs to two tiles and none to no tile — which is what makes two
        neighbours meet without a seam."""
        grid = GroundGrid.for_plan(1300.0, 700.0)
        seen: set[tuple[int, int]] = set()
        for key in grid.tile_keys():
            x0, y0, width, height = grid.tile_px_rect(key)
            assert 1 <= width <= TILE_PX and 1 <= height <= TILE_PX
            cells = {(x, y) for x in range(x0, x0 + width, 97) for y in range(y0, y0 + height, 97)}
            assert not cells & seen
            seen |= cells
            east, north, width_cm, depth_cm = grid.tile_cm_rect(key)
            assert (east, north) == (x0 / grid.px_per_cm, y0 / grid.px_per_cm)
            assert (width_cm, depth_cm) == (width / grid.px_per_cm, height / grid.px_per_cm)
        assert sum(grid.tile_px_rect(k)[2] * grid.tile_px_rect(k)[3] for k in grid.tile_keys()) == (
            grid.width_px * grid.height_px) == 1300 * 700
        # rows count NORTH from the south edge: the last row is the partial one
        assert grid.tile_px_rect((0, 1)) == (0, 512, 512, 188)
        assert grid.tile_px_rect((2, 0)) == (1024, 0, 276, 512)

    def test_a_plan_that_is_not_whole_pixels_reaches_less_than_a_pixel_past_its_edge(self) -> None:
        grid = GroundGrid.for_plan(100.5, 99.25)
        assert (grid.width_px, grid.height_px) == (101, 100)
        east, north, width, depth = grid.tile_cm_rect((0, 0))
        assert (east, north) == (0.0, 0.0)
        assert 0.0 <= width - 100.5 < 1.0 and 0.0 <= depth - 99.25 < 1.0

    @pytest.mark.parametrize(("box", "expected"), [
        ((10.0, 10.0, 20.0, 20.0), {(0, 0)}),
        ((500.0, 500.0, 520.0, 520.0), {(0, 0), (1, 0), (0, 1), (1, 1)}),
        ((512.0, 0.0, 600.0, 10.0), {(1, 0)}),            # starts ON a border: the east tile only
        ((400.0, 0.0, 512.0, 10.0), {(0, 0)}),            # ends ON a border: it does not reach in
        ((-300.0, -300.0, -1.0, -1.0), set()),            # beside the plan
        ((2300.0, 1500.0, 9000.0, 9000.0), {(4, 2), (4, 3)}),   # clamped to the grid
        ((3000.0, 0.0, 3100.0, 10.0), set()),             # east of the plan
        ((0.0, 0.0, 2400.0, 1600.0), {(c, r) for c in range(5) for r in range(4)}),
        ((20.0, 20.0, 10.0, 10.0), set()),                # no box at all
        ((float("nan"), 0.0, 10.0, 10.0), set()),
    ])
    def test_the_tiles_a_box_reaches_into(self, box: tuple[float, float, float, float],
                                          expected: set[tuple[int, int]]) -> None:
        grid = GroundGrid.for_plan(2400.0, 1600.0)
        assert set(grid.tiles_touching(*box)) == expected
        # ... and the same tiles as four integers, however many they are
        block = grid.tile_block(*box)
        if not expected:
            assert block is None
        else:
            assert block is not None
            first_column, first_row, last_column, last_row = block
            assert {(column, row) for column in range(first_column, last_column + 1)
                    for row in range(first_row, last_row + 1)} == expected

    @pytest.mark.parametrize("box", [
        (-1e300, -1e300, 1e300, 1e300), (float("-inf"), float("-inf"), float("inf"), float("inf")),
        (-1e15, 0.0, 1e15, 1.0)])
    def test_a_box_no_plan_holds_is_the_grids_own_block(
            self, box: tuple[float, float, float, float]) -> None:
        """Whatever comes in, what goes out are tile numbers of THIS grid."""
        grid = GroundGrid.for_plan(2400.0, 1600.0)
        block = grid.tile_block(*box)
        assert block is not None and block[0] == 0 and block[2] == 4
        assert 0 <= block[1] <= block[3] <= 3

    def test_an_item_of_three_metres_moved_a_little_touches_at_most_four_tiles(self) -> None:
        """The arithmetic behind gate G3, for every position: a box no longer than a
        tile reaches into at most two tiles per axis."""
        grid = GroundGrid.for_plan(5000.0, 3000.0)
        tile_cm = TILE_PX / grid.px_per_cm
        most = 0
        for step in range(0, 2000, 7):
            east, north = 100.0 + step * 1.3, 50.0 + step * 0.9
            span = 300.0 + 200.0 + 12.0  # the item, the move, the paint margin
            assert span <= tile_cm
            most = max(most, len(set(grid.tiles_touching(east, north, east + span, north + span))))
        assert most == 4

    @pytest.mark.parametrize("bad", [(0.0, 10.0), (-5.0, 10.0), (10.0, float("inf")),
                                     (float("nan"), 10.0)])
    def test_a_plan_has_a_positive_finite_size(self, bad: tuple[float, float]) -> None:
        with pytest.raises(ValueError, match="positive length"):
            GroundGrid.for_plan(*bad)

    def test_a_tile_outside_the_grid_is_a_key_error(self) -> None:
        with pytest.raises(KeyError):
            GroundGrid.for_plan(100.0, 100.0).tile_px_rect((1, 0))


class TestGroundTile:
    def test_a_tile_is_plain_data_with_exactly_its_pixels(self) -> None:
        one = tile(2, 3, shade=7)
        assert one.key == (2, 3) and len(one.pixels) == 16
        assert one == tile(2, 3, shade=7) and one != tile(2, 3, shade=8) and one != tile(2, 2, 7)
        assert "pixels" not in repr(one)

    @pytest.mark.parametrize("changes", [
        {"pixels": b"\x00" * 15}, {"pixels": bytearray(16)}, {"width_px": 0}, {"column": -1},
        {"width_cm": 0.0}, {"north_cm": float("nan")},
    ])
    def test_what_is_not_a_tile_is_refused(self, changes: dict[str, object]) -> None:
        with pytest.raises((ValueError, TypeError)):
            dataclasses.replace(tile(), **changes)

    def test_changed_tiles_names_what_to_upload_and_what_to_drop(self) -> None:
        a, b, c = tile(0, 0, 1), tile(1, 0, 2), tile(2, 0, 3)
        assert changed_tiles((), (a, b)) == ((a, b), ())
        assert changed_tiles((a, b), (a, b)) == ((), ())
        again = tile(1, 0, 2)  # another object, the same picture: nothing to upload
        assert again is not b and changed_tiles((a, b), (a, again)) == ((), ())
        repainted = tile(1, 0, 9)
        assert changed_tiles((a, b, c), (a, repainted)) == ((repainted,), ((2, 0),))


class TestGroundSpec:
    def test_the_tiles_are_part_of_the_ground(self) -> None:
        bare = GroundSpec(200.0, 100.0)
        baked = GroundSpec(200.0, 100.0, (tile(0, 0), tile(1, 0)))
        assert bare.tiles == () and bare != baked
        assert baked.plan == bare and bare.plan is bare
        assert baked == GroundSpec(200.0, 100.0, (tile(0, 0), tile(1, 0)))

    def test_two_tiles_for_one_place_and_things_that_are_not_tiles_are_refused(self) -> None:
        with pytest.raises(ValueError, match="one place"):
            GroundSpec(200.0, 100.0, (tile(0, 0, 1), tile(0, 0, 2)))
        with pytest.raises(TypeError):
            GroundSpec(200.0, 100.0, [tile()])  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            GroundSpec(200.0, 100.0, (b"pixels",))  # type: ignore[arg-type]


# ── a record's paint description ──────────────────────────────────────────────


class TestPaint:
    def test_the_defaults_are_qts_own_pen(self) -> None:
        paint = Paint()
        assert (paint.stroke_style, paint.stroke_cap, paint.stroke_join) == (
            "SolidLine", "SquareCap", "BevelJoin")
        assert paint.opacity == 1.0 and paint.stroke_width_cm == 0.0 and paint.rotation_deg == 0.0
        assert hash(Paint()) == hash(paint) and Paint(stroke_width_cm=2.0) != paint
        assert {f.name for f in dataclasses.fields(Paint)} == {
            "stroke_width_cm", "stroke_style", "stroke_cap", "stroke_join", "opacity",
            "rotation_deg"}

    @pytest.mark.parametrize("changes", [
        {"stroke_style": "Wavy"}, {"stroke_cap": "round"}, {"stroke_join": "Mitre"},
        {"stroke_width_cm": -1.0}, {"stroke_width_cm": float("nan")}, {"opacity": 1.5},
        {"opacity": float("nan")}, {"opacity": -0.1},
        {"rotation_deg": float("nan")}, {"rotation_deg": float("inf")},
    ])
    def test_what_no_painter_could_use_is_refused(self, changes: dict[str, object]) -> None:
        with pytest.raises(ValueError):
            Paint(**changes)  # type: ignore[arg-type]

    def test_a_length_beyond_what_a_plan_can_hold_is_out_of_range(self) -> None:
        with pytest.raises(RecordRangeError):
            Paint(stroke_width_cm=1e300)
        with pytest.raises(RecordRangeError):  # the paint origin is a param: a length like any
            Params({PARAM_PAINT_ORIGIN: (2e6, 0.0)})

    def test_the_paint_is_part_of_the_material_and_of_nothing_else(self) -> None:
        """A change of the pen or the opacity is a MATERIAL change: it re-bakes
        tiles and never rebuilds a mesh."""
        base = flat("a")
        for paint in (Paint(stroke_width_cm=3.0), Paint(2.0, "DashLine"), Paint(2.0, opacity=0.5),
                      Paint(2.0, stroke_cap="RoundCap"), Paint(2.0, stroke_join="MiterJoin"),
                      Paint(2.0, rotation_deg=33.0)):  # a turned circle: paint, not geometry
            other = dataclasses.replace(base, material=dataclasses.replace(base.material, paint=paint))
            assert not base.same_material(other)
            assert base.same_geometry(other) and base.same_transform(other)
        with pytest.raises(TypeError):
            Material("LAWN", paint="solid")  # type: ignore[arg-type]

    def test_the_drawn_outline_is_geometry_and_is_held_to_the_range(self) -> None:
        base = flat("a", shape="polygon")
        drawn = dataclasses.replace(base, outline=SQUARE[::-1])
        assert not base.same_geometry(drawn) and base.same_material(drawn)
        assert base.outline == ()
        with pytest.raises(RecordRangeError):
            dataclasses.replace(base, outline=((0.0, 0.0), (2e6, 0.0), (0.0, 5.0)))

    def test_a_record_can_hold_what_was_drawn_and_no_regions(self) -> None:
        """An outline too large for the solid path: nothing can be built of it, and
        the ground bake still has all it needs."""
        painted_only = dataclasses.replace(flat("a", shape="polygon"), footprints=(),
                                           outline=SQUARE)
        assert painted_only.regions == () and painted_only.plan_area_cm2 == 0.0
        assert painted_only.outline == SQUARE


# ── SceneSync and its ground baker ────────────────────────────────────────────


class FakeBaker:
    """A ``GroundBaking`` double: one 1 x 1 px tile whose colour says how many
    records it was asked to paint (red) and where they lie (green); it records
    every call."""

    def __init__(self, log: list[str] | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], SceneDiff | None, frozenset[str],
                               tuple[float, float]]] = []
        self.cleared = 0
        self.restarted = 0
        self.pending = 0
        self.fail: Exception | None = None
        self.log = log if log is not None else []
        self._held: tuple[tuple[str, ...], GroundTile] | None = None

    def bake(self, records: Mapping[str, Record], changes: SceneDiff | None,
             solid: Collection[str], width_cm: float, depth_cm: float
             ) -> tuple[GroundTile, ...]:
        self.log.append("bake")
        self.calls.append((tuple(records), changes, frozenset(solid), (width_cm, depth_cm)))
        if self.fail is not None:
            raise self.fail
        painted = tuple(item_id for item_id, record in records.items()
                        if record.material.paint is not None and item_id not in solid)
        state = (painted, tuple(records[i].transform for i in painted), (width_cm, depth_cm))
        if self._held is None or self._held[0] != state:
            where = int(sum(records[i].transform.east_cm for i in painted)) % 256
            self._held = (state, GroundTile(0, 0, 0.0, 0.0, width_cm, depth_cm, 1, 1,
                                            bytes([len(painted), where, 0, 255])))
        return (self._held[1],)

    def clear(self) -> None:
        self.cleared += 1
        self.pending = 0
        self._held = None

    def restart(self) -> None:
        self.restarted += 1
        self.pending = 0
        self._held = None

    def fresh(self) -> FakeBaker:
        return FakeBaker()


class SlowBaker:
    """A ``GroundBaking`` double with a budget of ONE tile a call: a ground of three
    1 x 1 px tiles, each showing how many records are painted. A call re-paints the
    first tile that is behind and leaves the others as the objects they were."""

    def __init__(self, per_call: int = 1) -> None:
        self.per_call = per_call
        self.calls = 0
        self.cleared = 0
        self.restarted = 0
        self.fail: Exception | None = None
        self._shown: list[GroundTile] = []
        self._behind: list[int] = []
        self._count = -1

    @property
    def pending(self) -> int:
        return len(self._behind)

    def bake(self, records: Mapping[str, Record], changes: SceneDiff | None,
             solid: Collection[str], width_cm: float, depth_cm: float
             ) -> tuple[GroundTile, ...]:
        self.calls += 1
        if self.fail is not None:
            raise self.fail
        count = sum(1 for item_id, record in records.items()
                    if record.material.paint is not None and item_id not in solid)
        if not self._shown:
            self._shown = [GroundTile(column, 0, column * 10.0, 0.0, 10.0, 10.0, 1, 1,
                                      bytes([0, 0, 0, 255])) for column in range(3)]
        if count != self._count:
            self._count = count
            self._behind = [0, 1, 2]
        for column in self._behind[:self.per_call]:
            self._shown[column] = GroundTile(column, 0, column * 10.0, 0.0, 10.0, 10.0, 1, 1,
                                             bytes([count, 0, 0, 255]))
        del self._behind[:self.per_call]
        return tuple(self._shown)

    def clear(self) -> None:
        self.cleared += 1
        self._shown, self._behind, self._count = [], [], -1

    def restart(self) -> None:
        """Forgets what it painted; keeps the pictures until each is painted anew."""
        self.restarted += 1
        self._behind, self._count = [], -1

    def fresh(self) -> SlowBaker:
        return SlowBaker(per_call=3)  # a reference: the whole ground in one call


class LoggingSink(RecordingSink):
    def __init__(self, log: list[str]) -> None:
        super().__init__()
        self._log = log

    def begin(self) -> None:
        self._log.append("begin")
        super().begin()


PLAN = GroundSpec(2400.0, 1600.0)


class TestTheLeakGatesStatistic:
    """Ruling R41 (FU-19): gate G6 reads the MEDIAN of the last ten cycles' growth.
    The curves are the ones measured on this box."""

    #: WARP, 2026-10-19: flat, ONE step of +20.6 MB at cycle 15, flat again — the run
    #: the old statistic (Theil-Sen over the second half) read as +2.80 MB a cycle.
    STEP = [790.5, 819.3, 819.2, 816.6, 814.9, 813.5, 813.1, 814.1, 814.1, 814.1, 814.1, 814.1,
            813.9, 814.1, 814.2, 834.8, 835.7, 836.4, 836.5, 836.4]
    #: The leak control on the same box: every replaced texture kept, +32 MB a cycle.
    LEAK = [836.6, 870.3, 902.5, 931.8, 964.1, 999.2, 1031.4, 1063.6, 1094.0, 1127.1, 1159.3,
            1192.5, 1224.7, 1256.9, 1286.8, 1320.4, 1352.6, 1384.8, 1417.0, 1447.5]

    def test_one_step_is_no_leak_and_a_leak_is_one(self) -> None:
        import statistics

        from tests.integration.ground_bake_render_driver import tail_growth

        assert abs(tail_growth(self.STEP)) < 0.2 < 2.0  # the bound
        assert tail_growth(self.LEAK) > 30.0 > 8.0      # the control's floor
        # … and what the statistic before read for the same step
        tail = self.STEP[len(self.STEP) // 2:]
        theil_sen = statistics.median((tail[j] - tail[i]) / (j - i)
                                      for i in range(len(tail)) for j in range(i + 1, len(tail)))
        assert theil_sen > 2.0

    def test_a_leak_of_a_quarter_of_the_bound_a_cycle_is_its_own_median(self) -> None:
        from tests.integration.ground_bake_render_driver import tail_growth

        curve = [800.0 + 0.5 * cycle for cycle in range(20)]
        curve[15] += 20.0  # with one step on top of it
        assert tail_growth(curve) == 0.5
        with pytest.raises(ValueError, match="no 10 cycles"):
            tail_growth(curve[:10])


class TestSyncWithAGroundBaker:
    def test_the_double_is_a_ground_baker(self) -> None:
        assert isinstance(FakeBaker(), GroundBaking)
        assert not isinstance(object(), GroundBaking)

    def test_records_and_ground_travel_in_one_transaction_and_the_bake_comes_first(self) -> None:
        log: list[str] = []
        baker, sink = FakeBaker(log), LoggingSink(log)
        sync = SceneSync(sink, ground_baker=baker)
        records = {"lawn": flat("lawn"), "shed": solid("shed", 300.0)}
        changes = sync.apply(records, sun=SunState(40.0, 180.0), ground=PLAN)
        assert log == ["bake", "begin"]  # like a builder: before the sink is touched
        assert sink.transactions == 1
        assert [op for op, _ in sink.ops()] == ["begin", "add", "add", "set_ground", "set_sun",
                                                "commit"]
        ids, given, solid_ids, size = baker.calls[0]
        assert ids == ("lawn", "shed") and given is changes  # the SAME diff the builders ran from
        assert solid_ids == {"shed"} == sync.solid_ids and size == (2400.0, 1600.0)
        ground = sink.ground
        assert ground is not None and ground.plan == PLAN and len(ground.tiles) == 1
        assert ground.tiles[0].pixels == bytes([1, 0, 0, 255])  # the lawn, not the shed
        assert sync.ground == ground and sync.ground_baker is baker

    def test_an_edit_sends_the_ground_only_when_a_tile_changed(self) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        records = {"lawn": flat("lawn"), "shed": solid("shed", 300.0)}
        sync.apply(records, ground=PLAN)
        sink.clear_calls()
        sync.apply(records)  # nothing changed: no call at all — and no ground given again
        assert sink.calls == [] and len(baker.calls) == 2
        sync.apply({**records, "shed": solid("shed", 350.0)})  # a solid moved: the ground stays
        assert [op for op, _ in sink.ops()] == ["begin", "update_transform", "commit"]
        sink.clear_calls()
        sync.apply({"lawn": flat("lawn", 40.0), "shed": solid("shed", 350.0)})
        assert [op for op, _ in sink.ops()] == ["begin", "update_transform", "set_ground", "commit"]
        assert sync.ground is sink.ground

    def test_an_item_is_painted_only_while_no_builder_makes_a_solid_for_it(self) -> None:
        """The rule's second half: a record with a paint description is on the ground
        until a builder builds something for it — the baker is told, with no record
        having changed (so the diff is withheld: it no longer says everything)."""
        baker, sink = FakeBaker(), RecordingSink()
        registry = BuilderRegistry()
        sync = SceneSync(sink, registry, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        assert sync.solid_ids == frozenset() and sink.ground.tiles[0].pixels[0] == 1

        def slab(record: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(record.footprints, 5.0), "vc"),)

        registry.register("LAWN", slab)
        sync.apply({"lawn": flat("lawn")})
        assert baker.calls[-1][1] is None and sync.solid_ids == {"lawn"}
        assert sink.ground.tiles[0].pixels[0] == 0  # no longer painted
        sync.apply({})
        assert sync.solid_ids == frozenset()

    def test_a_baker_that_raises_is_contained_and_starts_over(self, caplog: pytest.LogCaptureFixture
                                                               ) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        shown = sink.ground
        baker.fail = RuntimeError("no memory for a tile")
        with caplog.at_level("ERROR"):
            sync.apply({"lawn": flat("lawn", 10.0), "shed": solid("shed", 300.0)})
        assert sync.ground_failure == ("RuntimeError", "no memory for a tile")
        assert "could not be baked" in caplog.text
        assert not sync.poisoned and set(sink.item_ids()) == {"lawn", "shed"}  # the scene went on
        # the old ground stays; the baker forgets its books and keeps its pictures
        assert sink.ground == shown and (baker.restarted, baker.cleared) == (1, 0)
        baker.fail = None
        sync.apply({"lawn": flat("lawn", 20.0), "shed": solid("shed", 300.0)})
        assert sync.ground_failure is None and sink.ground != shown

    def test_the_edit_after_a_failed_bake_does_not_blank_the_ground(self) -> None:
        """Review 2: a baker that raised was CLEARED, so the next edit re-baked from
        nothing under the baker's budget — one painted tile, the rest bare (16 → 1
        on a real ground). It is RESTARTED now: it forgets its books and keeps its
        pictures, and a tile it has not painted anew is the very object the sink
        already shows."""
        baker, sink = SlowBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        while sync.continue_ground():
            pass
        shown = sink.ground.tiles
        assert [tile.pixels[0] for tile in shown] == [1, 1, 1]
        baker.fail = MemoryError("no image")
        sync.apply({"lawn": flat("lawn", 10.0)})  # the failing edit: the ground stays
        assert sink.ground.tiles == shown and (baker.restarted, baker.cleared) == (1, 0)
        baker.fail = None
        sync.apply({"lawn": flat("lawn", 20.0), "path": flat("path", 500.0)})  # the edit after it
        after = sink.ground.tiles
        assert [tile.pixels[0] for tile in after] == [2, 1, 1]  # cleared, it was [2, 0, 0]
        assert after[1] is shown[1] and after[2] is shown[2] and sync.ground_pending
        while sync.continue_ground():
            pass
        assert [tile.pixels[0] for tile in sink.ground.tiles] == [2, 2, 2]
        assert sink.state() == sync.expected_state()

    def test_a_bake_that_failed_is_not_tried_again_until_something_it_depends_on_changes(
            self, caplog: pytest.LogCaptureFixture) -> None:
        """Review P2-1: three idle ticks after a failing bake were three bakes and
        three ERROR logs with tracebacks. A bake failure is remembered like a
        builder's — until a record, the solids or the plan's rectangle change."""
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        records = {"lawn": flat("lawn")}
        sync.apply(records, ground=PLAN)
        shown = sink.ground
        baker.fail = MemoryError("no image for the third tile")
        moved = {"lawn": flat("lawn", 10.0)}
        with caplog.at_level("ERROR"):
            sync.apply(moved)
            calls = len(baker.calls)
            sink.clear_calls()
            for _tick in range(3):
                assert sync.apply(moved).is_empty
                assert sync.apply(moved, ground=PLAN).is_empty  # the same plan, given again
                assert sync.set_ground(PLAN) is False and sync.continue_ground() is False
        assert len(baker.calls) == calls and caplog.text.count("could not be baked") == 1
        assert sink.calls == [] and sink.ground == shown and (baker.restarted, baker.cleared) == (1, 0)
        assert sync.ground_failure == ("MemoryError", "no image for the third tile")
        # … a record changes: tried again (and it fails again: one more log, one more clear)
        with caplog.at_level("ERROR"):
            sync.apply({"lawn": flat("lawn", 20.0)})
        assert len(baker.calls) == calls + 1 and caplog.text.count("could not be baked") == 2
        # … the set of solids changes with no record changing: tried again
        registry = sync.registry

        def slab(record: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(record.footprints, 5.0), "vc"),)

        registry.register("LAWN", slab)
        sync.apply({"lawn": flat("lawn", 20.0)})
        assert len(baker.calls) == calls + 2
        # … the plan's rectangle changes: tried again — and it heals when the baker does
        assert sync.apply({"lawn": flat("lawn", 20.0)}).is_empty and len(baker.calls) == calls + 2
        baker.fail = None
        assert sync.set_ground(GroundSpec(1000.0, 1000.0)) is True
        assert sync.ground_failure is None and len(baker.calls) == calls + 3

    def test_reset_forgets_the_remembered_failure(self) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        baker.fail = ValueError("boom")
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        assert sync.ground_failure is not None
        sync.reset()
        assert sync.ground_failure is None
        baker.fail = None
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        assert sync.ground_failure is None and sink.ground.tiles[0].pixels[0] == 1

    def test_a_failed_bake_on_another_plan_rectangle_shows_bare_ground(self) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        baker.fail = ValueError("boom")
        sync.apply({"lawn": flat("lawn")}, ground=GroundSpec(1000.0, 1000.0))
        assert sink.ground == GroundSpec(1000.0, 1000.0)  # the old tiles lie on another grid

    def test_reset_clears_the_baker_and_the_next_apply_sends_the_ground_again(self) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn"), "shed": solid("shed", 300.0)}, ground=PLAN)
        sync.reset()
        assert baker.cleared == 1 and sync.solid_ids == frozenset() and sync.ground is None
        assert sink.ground is None
        sync.apply({"lawn": flat("lawn"), "shed": solid("shed", 300.0)}, ground=PLAN)
        assert sink.ground is not None and sink.ground.tiles and sync.solid_ids == {"shed"}

    def test_incremental_equals_a_from_scratch_bake(self) -> None:
        """``expected_state`` bakes with a FRESH baker: the tiles are part of the
        state, so a sink whose ground went stale differs from it."""
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, sun=SunState(40.0, 180.0), ground=PLAN)
        sync.apply({"lawn": flat("lawn", 30.0), "path": flat("path", 500.0)})
        sync.apply({"path": flat("path", 500.0), "shed": solid("shed", 300.0)})
        assert sink.state() == sync.expected_state()
        assert sink.ground.tiles[0].pixels[0] == 1
        stale = RecordingSink()
        stale.begin()
        stale.set_ground(GroundSpec(2400.0, 1600.0, (tile(0, 0, shade=9, side=1),)))
        stale.commit()
        assert stale.state().ground != sync.expected_state().ground

    def test_set_ground_bakes_for_the_records_it_has(self) -> None:
        baker, sink = FakeBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")})
        assert sink.ground is None and baker.calls == []  # no plan rectangle yet: nothing to bake
        assert sync.set_ground(PLAN) is True
        assert sink.ground.tiles[0].pixels[0] == 1 and baker.calls[-1][1] == SceneDiff()
        assert sync.set_ground(PLAN) is False  # the same ground again: no call
        assert sync.set_ground(GroundSpec(1000.0, 1000.0)) is True
        assert sink.ground.plan == GroundSpec(1000.0, 1000.0)

    def test_the_doubles_are_ground_bakers(self) -> None:
        assert isinstance(SlowBaker(), GroundBaking)

        class NoPending:
            def bake(self, *args: object) -> tuple[GroundTile, ...]:
                return ()

            def clear(self) -> None: ...

            def restart(self) -> None: ...

            def fresh(self) -> NoPending:
                return self

        assert not isinstance(NoPending(), GroundBaking)  # ``pending`` is part of the seam

    def test_pending_ground_work_is_reported_and_continued(self) -> None:
        """Review P1-4, the sync's half. A baker that stops early leaves tiles
        pending: the ground sent holds the old tiles for those — the SAME objects —
        ``ground_pending`` says so, and each further pass is one bake and, when a
        tile changed, one transaction with nothing in it but the ground."""
        baker, sink = SlowBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        records = {"lawn": flat("lawn"), "shed": solid("shed", 300.0)}
        sync.apply(records, sun=SunState(40.0, 180.0), ground=PLAN)
        assert sync.ground_pending and baker.pending == 2
        first = sink.ground
        assert [t.pixels[0] for t in first.tiles] == [1, 0, 0]  # one tile done, two still bare
        # everything that is not ground is finished at once, and equal to the reference
        reference = sync.expected_state()
        assert sink.state().items == reference.items and sink.state().sun == reference.sun
        assert sink.state().ground != reference.ground
        behind = [mine is not theirs and mine != theirs
                  for mine, theirs in zip(sink.ground.tiles, reference.ground.tiles, strict=True)]
        assert behind == [False, True, True]  # behind in exactly the pending tiles
        sink.clear_calls()
        assert sync.continue_ground() is True  # more to do
        assert [op for op, _ in sink.ops()] == ["begin", "set_ground", "commit"]
        assert sink.ground.tiles[0] is first.tiles[0] and sink.ground.tiles[2] is first.tiles[2]
        assert sync.continue_ground() is False and not sync.ground_pending
        assert sink.state() == sync.expected_state()  # once nothing is pending: the invariant
        calls = baker.calls
        sink.clear_calls()
        assert sync.continue_ground() is False  # nothing pending: no bake, no call
        assert baker.calls == calls and sink.calls == []

    def test_an_apply_goes_on_with_pending_work_and_an_edit_restarts_it(self) -> None:
        baker, sink = SlowBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        assert sync.apply({"lawn": flat("lawn")}).is_empty and baker.pending == 1  # an idle tick
        assert [t.pixels[0] for t in sink.ground.tiles] == [1, 1, 0]
        sync.apply({"lawn": flat("lawn"), "path": flat("path", 500.0)})  # an edit: all behind again
        assert sync.ground_pending and [t.pixels[0] for t in sink.ground.tiles] == [2, 1, 0]
        while sync.ground_pending:
            sync.continue_ground()
        assert [t.pixels[0] for t in sink.ground.tiles] == [2, 2, 2]
        assert sink.state() == sync.expected_state()

    def test_reset_drops_pending_work_with_the_tiles(self) -> None:
        baker, sink = SlowBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        assert sync.ground_pending
        sync.reset()
        assert not sync.ground_pending and baker.cleared == 1 and sink.ground is None
        assert sync.continue_ground() is False and baker.calls == 1

    def test_a_sink_that_raises_in_a_continuation_poisons_the_sync(self) -> None:
        class Failing(RecordingSink):
            fail = False

            def set_ground(self, ground: GroundSpec) -> None:
                if self.fail:
                    raise RuntimeError("device lost")
                super().set_ground(ground)

        baker, sink = SlowBaker(), Failing()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        sink.fail = True
        with pytest.raises(RuntimeError, match="device lost"):
            sync.continue_ground()
        assert sync.poisoned
        with pytest.raises(SyncStateError):
            sync.continue_ground()
        sink.fail = False
        sync.reset()
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        while sync.ground_pending:
            sync.continue_ground()
        assert sink.state() == sync.expected_state()

    def test_a_baker_that_raises_in_a_continuation_is_contained(self) -> None:
        baker, sink = SlowBaker(), RecordingSink()
        sync = SceneSync(sink, ground_baker=baker)
        sync.apply({"lawn": flat("lawn")}, ground=PLAN)
        shown = sink.ground
        baker.fail = MemoryError("no image")
        assert sync.continue_ground() is False  # contained: restarted, nothing pending
        assert sync.ground_failure == ("MemoryError", "no image") and not sync.poisoned
        assert sink.ground == shown and (baker.restarted, baker.cleared) == (1, 0)

    def test_without_a_baker_the_ground_is_the_callers(self) -> None:
        sink = RecordingSink()
        sync = SceneSync(sink)
        given = GroundSpec(200.0, 100.0, (tile(0, 0, 4),))
        sync.apply({"lawn": flat("lawn")}, ground=given)
        assert sink.ground is given and sync.ground_baker is None
        assert sink.state() == sync.expected_state()


def test_the_ground_module_imports_no_qt() -> None:
    """Qt-free like the rest of ``core/scene3d`` (the package's own AST scan covers
    it too; said here because this is the module a painter would be tempting in)."""
    import open_garden_planner.core.scene3d.ground as ground

    tree = ast.parse(Path(ground.__file__).read_text(encoding="utf-8"))
    imported = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names}
    assert not {name for name in imported if name.startswith("PyQt6")}
