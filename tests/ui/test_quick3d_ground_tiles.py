"""The baked ground in a real engine scene — its Models and textures (Phase 17 L1.5, #385).

A ``Quick3DHost`` under the offscreen platform loads ``Garden.qml`` and creates
real ``Model`` s and ``QQuick3DTextureData`` objects, but draws nothing: what is
tested here is the BOOKKEEPING — which tile gets a Model where, what is uploaded
when, what is held and what is let go. What the engine draws with them (north
up, no seam, no growth over twenty re-bakes) is the render tier's:
``tests/integration/test_scene3d_ground_render.py``.

Like ``test_quick3d_host.py``, the file runs only where bare Qt can create Qt
Quick 3D objects offscreen (its canary fixture decides, and fails on CI).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.core.scene3d import GroundSpec, GroundTile, SceneSync
from open_garden_planner.ui.view3d.quick3d.adapter import Quick3DSink
from tests.ui.test_quick3d_host import (
    _broken_copy,
    _new_host,
    quick3d_objects_can_be_created,  # noqa: F401 - the canary decides whether this file runs
)


def _tile(column: int, row: int, shade: int = 90, *, px: tuple[int, int] = (8, 8),
          size_cm: float = 512.0) -> GroundTile:
    return GroundTile(column, row, column * size_cm, row * size_cm, size_cm, size_cm, px[0], px[1],
                      bytes((shade, 120, 60, 255)) * (px[0] * px[1]))


def _show(sink: Quick3DSink, spec: GroundSpec) -> None:
    sink.begin()
    sink.set_ground(spec)
    sink.commit()


def _uploads() -> int:
    from open_garden_planner.ui.view3d.quick3d.ground_tiles import TileTexture

    return int(TileTexture.uploads)


@pytest.fixture()
def host(qtbot: Any) -> Iterator[Any]:  # noqa: ARG001 - Qt must be initialised
    made = _new_host((320, 240))
    yield made
    made.close()


class TestTilesInTheScene:
    def test_every_tile_is_a_model_where_its_rectangle_lies(self, host: Any) -> None:
        from open_garden_planner.ui.view3d.quick3d.ground_tiles import SEAM_OVERLAP_CM

        sink = Quick3DSink(host)
        assert host.ground.readback() == [] and host.scene_property("groundTiled") is False
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=(_tile(0, 0), _tile(1, 0), _tile(0, 1))))
        rows = {(row["column"], row["row"]): row for row in host.ground.readback()}
        assert set(rows) == {(0, 0), (1, 0), (0, 1)} == set(host.ground.keys())
        # scene (east, north) is engine (x, −z); the plan's plane is y = 0
        assert [(rows[key]["x"], rows[key]["y"], rows[key]["z"]) for key in sorted(rows)] == [
            (256.0, 0.0, -256.0), (256.0, 0.0, -768.0), (768.0, 0.0, -256.0)]
        for row in rows.values():
            assert row["textured"] is True and row["visible"] is True
            # a hair wider than its tile on every side: no line of meadow between two quads
            assert row["width"] == pytest.approx(512.0 + 2 * SEAM_OVERLAP_CM, abs=1e-3)
            assert row["depth"] == pytest.approx(512.0 + 2 * SEAM_OVERLAP_CM, abs=1e-3)
        assert 0.0 < SEAM_OVERLAP_CM <= 0.05
        # the bare plan rectangle is not drawn under them (two coplanar surfaces)
        assert host.scene_property("groundTiled") is True and host.scene_property("groundVisible") is True
        assert host.engine_parts() == []  # a tile is no part: the scene's items are untouched

    def test_only_a_tile_whose_picture_changed_is_uploaded(self, host: Any) -> None:
        sink = Quick3DSink(host)
        first = (_tile(0, 0), _tile(1, 0), _tile(0, 1), _tile(1, 1))
        before = _uploads()
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=first))
        assert _uploads() - before == 4
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=first))  # the same objects: nothing
        assert _uploads() - before == 4
        again = tuple(_tile(tile.column, tile.row) for tile in first)  # equal bytes, other objects
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=again))
        assert _uploads() - before == 4
        edited = (first[0], _tile(1, 0, shade=200), first[2], first[3])  # one tile re-baked
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=edited))
        assert _uploads() - before == 5
        assert len(host.ground.readback()) == 4  # four tiles still: the re-baked one is a new Model

    def test_a_replaced_texture_is_a_new_object_and_the_old_one_is_let_go(self, host: Any) -> None:
        """The keep-alive rule: per tile exactly the texture the scene shows, plus — until
        the next frame or the next update — the one it replaced. Never a growing list."""
        sink = Quick3DSink(host)
        _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0), _tile(1, 0))))
        shown = {key: id(entry.texture) for key, entry in host.ground._shown.items()}  # noqa: SLF001
        models = {key: entry.model for key, entry in host.ground._shown.items()}  # noqa: SLF001
        assert host.ground.textures_held() == 2 and host.ground.textures_retired() == 0
        _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0, shade=10), _tile(1, 0))))
        now = {key: id(entry.texture) for key, entry in host.ground._shown.items()}  # noqa: SLF001
        assert now[(0, 0)] != shown[(0, 0)] and now[(1, 0)] == shown[(1, 0)]
        # … and a NEW Model with it: a ``Texture`` element is never pointed at a second
        # texture (it would be drawn white once the first one is let go — render tier)
        assert host.ground._shown[(0, 0)].model is not models[(0, 0)]  # noqa: SLF001
        assert host.ground._shown[(1, 0)].model is models[(1, 0)]  # noqa: SLF001
        assert len(host.ground.readback()) == 2
        assert host.ground.textures_held() == 3 and host.ground.textures_retired() == 1
        host.ground.frame_presented()  # the scene has shown the successor
        assert host.ground.textures_held() == 2 and host.ground.textures_retired() == 0

    def test_twenty_re_bakes_without_a_frame_hold_two_generations_at_most(self, host: Any) -> None:
        """With the display asleep a window presents one frame and no more: the
        replaced textures must not wait for a frame that never comes."""
        from open_garden_planner.ui.view3d.quick3d.ground_tiles import textures_alive

        sink = Quick3DSink(host)
        before = textures_alive()  # what exists on the C++ side (asked of sip)
        most = most_alive = 0
        for generation in range(20):
            _show(sink, GroundSpec(1024.0, 1024.0, tiles=tuple(
                _tile(c, r, shade=10 + generation) for c in range(2) for r in range(2))))
            most = max(most, host.ground.textures_held())
            most_alive = max(most_alive, textures_alive() - before)
        assert most == 8 == most_alive and host.ground.textures_retired() == 4
        assert len(host.ground.readback()) == 4
        sink.clear()
        assert textures_alive() == before  # not one of the eighty is left

    def test_a_tile_that_is_no_longer_named_is_destroyed(self, host: Any) -> None:
        sink = Quick3DSink(host)
        _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0), _tile(1, 0))))
        _show(sink, GroundSpec(512.0, 512.0, tiles=(_tile(0, 0),)))
        assert [(row["column"], row["row"]) for row in host.ground.readback()] == [(0, 0)]
        _show(sink, GroundSpec(512.0, 512.0))  # no tiles: the bare rectangle again
        assert host.ground.readback() == [] and host.ground.keys() == ()
        assert host.scene_property("groundTiled") is False
        assert host.scene_property("groundVisible") is True

    def test_a_tile_of_another_plan_is_moved_not_uploaded(self, host: Any) -> None:
        sink = Quick3DSink(host)
        tile = _tile(0, 0)
        before = _uploads()
        _show(sink, GroundSpec(512.0, 512.0, tiles=(tile,)))
        coarser = GroundTile(0, 0, 0.0, 0.0, 1024.0, 1024.0, 8, 8, tile.pixels)  # half the resolution
        _show(sink, GroundSpec(1024.0, 1024.0, tiles=(coarser,)))
        (row,) = host.ground.readback()
        assert (row["x"], row["z"]) == (512.0, -512.0) and row["width"] == pytest.approx(1024.04, abs=1e-3)
        assert _uploads() - before == 1

    def test_the_sync_drives_it_through_the_sink(self, host: Any) -> None:
        """``SceneSync.set_ground`` → ``Quick3DSink`` → the host: the engine's state reads
        back as what the sync expects, tiles and all."""
        sync = SceneSync(Quick3DSink(host))
        spec = GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0), _tile(1, 0)))
        sync.set_ground(spec)
        assert sync.sink.state().ground == spec == sync.expected_state().ground
        assert len(host.ground.readback()) == 2


class TestTeardown:
    def test_clear_destroys_the_tiles_and_releases_every_texture(self, host: Any) -> None:
        sink = Quick3DSink(host)
        _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0), _tile(1, 0))))
        _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0, shade=1), _tile(1, 0, shade=2))))
        assert host.ground.textures_held() == 4
        sink.clear()
        assert host.ground.readback() == [] and host.ground.textures_held() == 0
        assert host.scene_property("groundTiled") is False
        assert host.scene_property("groundVisible") is False
        _show(sink, GroundSpec(512.0, 512.0, tiles=(_tile(0, 0),)))  # and it can show a ground again
        assert len(host.ground.readback()) == 1

    def test_close_releases_the_textures_without_asking_a_dead_scene(self, qtbot: Any) -> None:  # noqa: ARG002
        made = _new_host((64, 48))
        sink = Quick3DSink(made)
        _show(sink, GroundSpec(512.0, 512.0, tiles=(_tile(0, 0),)))
        assert made.ground.textures_held() == 1
        made.close()
        assert made.ground.textures_held() == 0 and made.ground.keys() == ()
        made.clear()  # on a closed host: a no-op, like every release
        sink.clear()
        assert made.ground.textures_held() == 0


class TestASceneFileThatCannot:
    """A renamed property or a function that fails in ``Garden.qml`` is an engine
    error with its name in it — never a ground that silently is not there."""

    @pytest.mark.parametrize(("old", "new", "message"), [
        ("property bool groundTiled: false", "property bool groundTyled: false",
         "no property 'groundTiled'"),
        ("function createGroundTile(", "function createGroundTileRenamed(",
         "no function createGroundTile"),
        ("function placeGroundTile(", "function placeGroundTileRenamed(",
         "no function placeGroundTile"),
        ("        tile.position = Qt.vector3d(x, 0, z)\n", "        nothingHere.position = 1\n",
         "placeGroundTile\\(\\) did not place"),
    ], ids=["tiled-flag", "create", "place-missing", "place-throws"])
    def test_showing_a_tile_fails_loudly(self, qtbot: Any, tmp_path: Path, old: str, new: str,  # noqa: ARG002
                                         message: str) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        made = Quick3DHost((64, 48), qml_dir=_broken_copy(tmp_path, old, new))
        try:
            sink = Quick3DSink(made)
            sink.begin()
            with pytest.raises(EngineError, match=message):
                sink.set_ground(GroundSpec(512.0, 512.0, tiles=(_tile(0, 0),)))
        finally:
            made.close()

    def test_a_tile_the_scene_did_not_destroy_stays_in_the_books(self, qtbot: Any,  # noqa: ARG002
                                                                 tmp_path: Path) -> None:
        from open_garden_planner.ui.view3d.quick3d.host import EngineError, Quick3DHost

        made = Quick3DHost((64, 48), qml_dir=_broken_copy(
            tmp_path, "        tile.retired = true\n", "        nothingHere.retired = true\n"))
        try:
            sink = Quick3DSink(made)
            _show(sink, GroundSpec(1024.0, 512.0, tiles=(_tile(0, 0), _tile(1, 0))))
            with pytest.raises(EngineError, match="destroyGroundTile\\(\\) did not retire"):
                made.clear()
            # books and engine agree after the failure: both still hold both tiles
            assert set(made.ground.keys()) == {(0, 0), (1, 0)} and len(made.ground.readback()) == 2
            assert made.scene_property("groundTiled") is True
        finally:
            made.close()
