"""The numpy → engine-bytes step, byte for byte (Phase 17 L1.2, #385 — gate G4).

``core/scene3d/interleave.py`` is the last Qt-free step before the engine: a
``Mesh`` in the item-local frame becomes the interleaved vertex buffer and the
index buffer Qt Quick 3D is handed (``ui/view3d/quick3d/geometry.py`` only
passes the bytes on). Because it is Qt-free, the default (offscreen) test run
covers the whole layout — stride, offsets, linear colour, the one frame
mapping, bounds — with no GPU.
"""

from __future__ import annotations

import struct

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    COLOR_OFFSET,
    NORMAL_OFFSET,
    POSITION_OFFSET,
    UV_OFFSET,
    VERTEX_STRIDE,
    EngineBuffers,
    Material,
    Mesh,
    Params,
    Record,
    Transform,
    default_builder,
    engine_buffers,
    normal_vs_winding,
    prism_mesh,
)

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
BAR = ((-30.0, -10.0), (30.0, -10.0), (30.0, 10.0), (-30.0, 10.0))  # not square: 60 E x 20 N
L_SHAPE = ((0.0, 0.0), (80.0, 0.0), (80.0, 30.0), (30.0, 30.0), (30.0, 90.0), (0.0, 90.0))


def _record(ring: tuple[tuple[float, float], ...], height: float, shape: str = "polygon") -> Record:
    return Record(item_id="i", kind="SHED", shape=shape, footprints=(ring,),
                  transform=Transform(), material=Material("SHED"), height_cm=height,
                  params=Params({"seed": "i"}))


def _default_meshes() -> list[tuple[str, Mesh]]:
    """Meshes from the DEFAULT builder — what the engine is handed today."""
    cases = [("square", SQUARE, 100.0), ("bar", BAR, 50.0), ("l-shape", L_SHAPE, 240.0)]
    return [(name, Mesh.merge([part.mesh for part in default_builder(_record(ring, height))]))
            for name, ring, height in cases]


MESHES = _default_meshes()


def _floats(buffers: EngineBuffers) -> np.ndarray:
    return np.frombuffer(buffers.vertex_data, dtype="<f4").reshape(-1, VERTEX_STRIDE // 4)


class TestLayout:
    def test_the_layout_constants_are_the_spikes(self) -> None:
        """Stride 48: position f32x3 @0, normal f32x3 @12, colour f32x4 @24, uv f32x2 @40."""
        assert (VERTEX_STRIDE, POSITION_OFFSET, NORMAL_OFFSET, COLOR_OFFSET, UV_OFFSET) == (
            48, 0, 12, 24, 40)

    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_sizes(self, name: str, mesh: Mesh) -> None:
        buffers = engine_buffers(mesh)
        assert len(buffers.vertex_data) == mesh.vertex_count * 48
        assert len(buffers.index_data) == mesh.triangle_count * 3 * 4
        assert buffers.vertex_count == mesh.vertex_count
        assert buffers.index_count == mesh.triangle_count * 3
        assert isinstance(buffers.vertex_data, bytes) and isinstance(buffers.index_data, bytes)
        assert not buffers.is_empty

    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_every_vertex_is_packed_field_by_field(self, name: str, mesh: Mesh) -> None:
        """Independent of numpy's reshaping: each vertex re-packed with ``struct`` from the
        mesh's own attributes, mapped by hand (x = E, y = up, z = −N)."""
        buffers = engine_buffers(mesh)
        for index in range(mesh.vertex_count):
            east, north, up = (float(v) for v in mesh.positions[index])
            n_east, n_north, n_up = (float(v) for v in mesh.normals[index])
            expected = struct.pack(
                "<12f", east, up, -north, n_east, n_up, -n_north,
                *(float(v) for v in mesh.colors[index]), *(float(v) for v in mesh.uvs[index]))
            start = index * VERTEX_STRIDE
            assert buffers.vertex_data[start:start + VERTEX_STRIDE] == expected, (name, index)

    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_indices_are_little_endian_uint32_in_triangle_order(self, name: str, mesh: Mesh) -> None:
        buffers = engine_buffers(mesh)
        flat = [int(v) for v in mesh.indices.reshape(-1)]
        assert buffers.index_data == struct.pack(f"<{len(flat)}I", *flat)

    def test_offsets_address_the_attributes(self) -> None:
        mesh = Mesh.from_arrays(
            [[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 10.0]],
            [[0.0, 0.0, 1.0]] * 3,
            [[0.1, 0.2, 0.3, 1.0], [0.4, 0.5, 0.6, 1.0], [0.7, 0.8, 0.9, 0.5]],
            [[0.25, 0.5], [0.75, 1.0], [0.0, 0.125]],
            [0, 1, 2],
        )
        data = engine_buffers(mesh).vertex_data
        second = VERTEX_STRIDE  # the second vertex
        assert struct.unpack_from("<3f", data, second + POSITION_OFFSET) == (4.0, 6.0, -5.0)
        assert struct.unpack_from("<3f", data, second + NORMAL_OFFSET) == (0.0, 1.0, -0.0)
        assert struct.unpack_from("<4f", data, second + COLOR_OFFSET) == pytest.approx(
            (0.4, 0.5, 0.6, 1.0), abs=1e-7)
        assert struct.unpack_from("<2f", data, second + UV_OFFSET) == (0.75, 1.0)


class TestColour:
    def test_colours_stay_linear_and_untouched(self) -> None:
        """The buffer carries the mesh's LINEAR colours bit for bit — no sRGB transfer
        function, no clamp, alpha included (a second gamma would wash every plant out)."""
        colours = np.array([[0.0, 0.214, 1.0, 1.0], [0.5, 0.5, 0.5, 0.25], [2.0, 0.001, 0.73, 0.0]],
                           np.float32)
        mesh = Mesh.from_arrays([[0, 0, 0], [1, 0, 0], [0, 1, 0]], [[0, 0, 1]] * 3, colours,
                                np.zeros((3, 2)), [0, 1, 2])
        packed = _floats(engine_buffers(mesh))[:, 6:10]
        assert packed.tobytes() == colours.astype("<f4").tobytes()

    def test_the_default_builders_neutral_white_reaches_the_engine_as_ones(self) -> None:
        packed = _floats(engine_buffers(MESHES[0][1]))[:, 6:10]
        assert np.array_equal(packed, np.ones_like(packed))


class TestFrame:
    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_positions_and_normals_are_mapped_once(self, name: str, mesh: Mesh) -> None:
        packed = _floats(engine_buffers(mesh))
        assert np.array_equal(packed[:, 0], mesh.positions[:, 0])    # x = East
        assert np.array_equal(packed[:, 1], mesh.positions[:, 2])    # y = up
        assert np.array_equal(packed[:, 2], -mesh.positions[:, 1])   # z = −North
        assert np.array_equal(packed[:, 3], mesh.normals[:, 0])
        assert np.array_equal(packed[:, 4], mesh.normals[:, 2])
        assert np.array_equal(packed[:, 5], -mesh.normals[:, 1])

    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_the_mapping_is_a_rotation_winding_survives(self, name: str, mesh: Mesh) -> None:
        """Determinant +1, measured on the bytes: the triangles of the ENGINE buffer are
        still wound counter-clockwise seen from outside (stored normal · winding normal
        = 1 on every flat face). A mirrored mapping gives −1 here and an inside-out
        garden on screen."""
        buffers = engine_buffers(mesh)
        packed = _floats(buffers)
        engine_mesh = Mesh.from_arrays(
            packed[:, 0:3], packed[:, 3:6], packed[:, 6:10], packed[:, 10:12],
            np.frombuffer(buffers.index_data, dtype="<u4"))
        dots, flat = normal_vs_winding(engine_mesh)
        assert flat.all() and float(dots.min()) > 0.999
        # and the three basis vectors, as columns of the linear map the bytes realise
        basis = Mesh.from_arrays(np.identity(3), np.identity(3), np.ones((3, 4)), np.zeros((3, 2)),
                                 [0, 1, 2])
        columns = _floats(engine_buffers(basis))[:, 0:3].astype(np.float64).T
        assert float(np.linalg.det(columns)) == 1.0

    @pytest.mark.parametrize(("name", "mesh"), MESHES, ids=[n for n, _ in MESHES])
    def test_bounds_are_the_engine_frame_box(self, name: str, mesh: Mesh) -> None:
        buffers = engine_buffers(mesh)
        low, high = mesh.bounds()
        assert buffers.bounds_min == (float(low[0]), float(low[2]), -float(high[1]))
        assert buffers.bounds_max == (float(high[0]), float(high[2]), -float(low[1]))
        packed = _floats(buffers)[:, 0:3]
        assert buffers.bounds_min == tuple(float(v) for v in packed.min(axis=0))
        assert buffers.bounds_max == tuple(float(v) for v in packed.max(axis=0))

    def test_a_prism_stands_on_y_zero_and_reaches_its_height(self) -> None:
        buffers = engine_buffers(prism_mesh([BAR], 50.0))
        assert buffers.bounds_min == (-30.0, 0.0, -10.0)
        assert buffers.bounds_max == (30.0, 50.0, 10.0)


class TestEdges:
    def test_an_empty_mesh_gives_empty_buffers(self) -> None:
        buffers = engine_buffers(Mesh.empty())
        assert buffers.vertex_data == b"" and buffers.index_data == b""
        assert buffers.vertex_count == 0 and buffers.index_count == 0
        assert buffers.is_empty
        assert buffers.bounds_min == (0.0, 0.0, 0.0) == buffers.bounds_max

    def test_the_mesh_is_not_modified(self) -> None:
        mesh = prism_mesh([SQUARE], 100.0)
        before = (mesh.positions.copy(), mesh.normals.copy(), mesh.indices.copy())
        engine_buffers(mesh)
        assert np.array_equal(mesh.positions, before[0])
        assert np.array_equal(mesh.normals, before[1])
        assert np.array_equal(mesh.indices, before[2])

    def test_a_mesh_whose_arrays_are_views_on_immutable_bytes_is_only_read(self) -> None:
        """A builder may hand out arrays that are VIEWS on a ``bytes`` object (a cached
        plant archetype): not writeable, not owning their data. ``engine_buffers`` must
        neither write into them nor ask for ownership — the bytes it produces are the
        ones a mesh with ordinary arrays gives."""
        from dataclasses import replace

        mesh = prism_mesh([L_SHAPE], 240.0)
        frozen = {name: bytes(np.ascontiguousarray(getattr(mesh, name)).tobytes())
                  for name in ("positions", "normals", "colors", "uvs", "indices")}
        widths = {"positions": 3, "normals": 3, "colors": 4, "uvs": 2, "indices": 3}
        views = {name: np.frombuffer(raw, dtype="<u4" if name == "indices" else "<f4").reshape(
            -1, widths[name]) for name, raw in frozen.items()}
        for view in views.values():
            assert not view.flags.writeable and not view.flags.owndata
        on_bytes = replace(mesh, **views)
        assert engine_buffers(on_bytes) == engine_buffers(mesh)
        for name, raw in frozen.items():
            assert getattr(on_bytes, name).tobytes() == raw, f"{name} was written to"
            assert not getattr(on_bytes, name).flags.writeable

    def test_two_calls_give_identical_bytes(self) -> None:
        mesh = prism_mesh([L_SHAPE], 240.0)
        assert engine_buffers(mesh) == engine_buffers(mesh)

    def test_buffers_are_plain_immutable_data(self) -> None:
        buffers = engine_buffers(prism_mesh([SQUARE], 10.0))
        with pytest.raises(AttributeError):
            buffers.vertex_count = 3  # type: ignore[misc]
