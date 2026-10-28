"""Mesh container, mesh parts and the builder seam (Phase 17 L1.1, #385, gate G7).

Qt-free. ``Mesh.validate()`` must catch each defect class with one failing case
each — including the L0 "wrong roof slope lit" bug (a flat face storing a normal
that is not its winding normal) — and pass everything the default builder emits.
The meshes of REAL canvas items are validated in
``tests/integration/test_scene3d_snapshot.py``.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.core.scene3d import (
    BENT_NORMAL_KINDS,
    MATERIAL_KINDS,
    BuilderContractError,
    BuilderRegistry,
    Material,
    Mesh,
    MeshError,
    MeshPart,
    Params,
    Record,
    Transform,
    default_builder,
    item_seed,
    normal_vs_winding,
    plan_overreach,
    point_in_regions,
    prism_mesh,
    srgb_to_linear,
    verify_builder,
)
from open_garden_planner.core.scene3d.build import (
    HOLE_COVER_LIMIT,
    HOLE_MIN_WIDTH_CM,
    PLAN_MARGIN_CM,
)

#: What the L0 spike measured, frozen when L1.10 deleted it (its provenance field says how).
SPIKE = json.loads((Path(__file__).resolve().parents[1] / "data" / "l0_spike_reference.json")
                   .read_text(encoding="utf-8"))

def default_mesh(record: Record) -> Mesh:
    """The default solid as ONE mesh: its tinted sides plus its fill cap (#627)."""
    return Mesh.merge([part.mesh for part in default_builder(record)])


SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
L_SHAPE = ((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (50.0, 50.0), (50.0, 100.0), (0.0, 100.0))
BOW_TIE = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 300.0))
# a frame 10 m x 8 m with a 10 cm rim — the plan view of a closed fence
FRAME = ((-505.0, -405.0), (505.0, -405.0), (505.0, 405.0), (-505.0, 405.0))
FRAME_HOLE = ((-495.0, -395.0), (-495.0, 395.0), (495.0, 395.0), (495.0, -395.0))  # clockwise
FRAME_AREA = 1010.0 * 810.0 - 990.0 * 790.0  # 36,000 cm²
REPO = Path(__file__).resolve().parents[2]


def cap_area(mesh: Mesh) -> float:
    """Plan-view area of the upward-facing triangles of a mesh, in cm²."""
    p = mesh.positions.astype(np.float64)
    a, b, c = (p[mesh.indices[:, k]] for k in range(3))
    z = np.cross(b - a, c - a)[:, 2]
    return float(z[z > 1e-9].sum() / 2.0)


def assert_walls_face_away_from_the_solid(mesh: Mesh, regions) -> None:
    """Step a hair along each wall normal: outside the footprint. A hair back:
    inside. True for outer walls and for the walls around a hole alike."""
    p = mesh.positions.astype(np.float64)
    n = mesh.normals.astype(np.float64)
    walls = 0
    for tri in mesh.indices:
        normal = n[tri[0]]
        if abs(normal[2]) > 0.5:
            continue  # the cap
        mid = p[tri].mean(axis=0)
        assert not point_in_regions(mid[0] + 0.01 * normal[0], mid[1] + 0.01 * normal[1], regions)
        assert point_in_regions(mid[0] - 0.01 * normal[0], mid[1] - 0.01 * normal[1], regions)
        walls += 1
    assert walls > 0


def triangle(normal: tuple[float, float, float] = (0.0, 0.0, 1.0)) -> Mesh:
    """One CCW-from-above triangle in the ground plane (winding normal = +up)."""
    return Mesh.from_arrays(
        positions=[[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 10.0, 0.0]],
        normals=[normal] * 3,
        colors=[[1.0, 1.0, 1.0, 1.0]] * 3,
        uvs=[[0.0, 0.0]] * 3,
        indices=[0, 1, 2],
    )


def record(**changes: object) -> Record:
    base = Record(
        item_id="11111111-2222-3333-4444-555555555555",
        kind="RAISED_BED",
        shape="rectangle",
        footprints=(SQUARE,),
        transform=Transform(100.0, 200.0, 30.0),
        material=Material("RAISED_BED", fill_rgba=(120, 80, 40, 255)),
        height_cm=40.0,
        params=Params({"seed": "11111111-2222-3333-4444-555555555555"}),
        name="Bed",
    )
    return dataclasses.replace(base, **changes) if changes else base


# ── Mesh ──────────────────────────────────────────────────────────────────────


class TestMesh:
    def test_from_arrays_coerces_dtypes_and_shapes(self) -> None:
        mesh = triangle()
        assert mesh.positions.dtype == np.float32 and mesh.positions.shape == (3, 3)
        assert mesh.normals.dtype == np.float32 and mesh.normals.shape == (3, 3)
        assert mesh.colors.dtype == np.float32 and mesh.colors.shape == (3, 4)
        assert mesh.uvs.dtype == np.float32 and mesh.uvs.shape == (3, 2)
        assert mesh.indices.dtype == np.uint32 and mesh.indices.shape == (1, 3)
        assert (mesh.vertex_count, mesh.triangle_count) == (3, 1)
        mesh.validate()

    def test_flat_and_triple_indices_are_both_accepted(self) -> None:
        """The spike's ``MeshData`` keeps indices flat (M,); contract v2 stores
        (m, 3). ``from_arrays`` takes either, so a ported builder needs no reshape."""
        flat = Mesh.from_arrays([[0, 0, 0]] * 6, [[0, 0, 1]] * 6, [[1, 1, 1, 1]] * 6,
                                [[0, 0]] * 6, [0, 1, 2, 3, 4, 5])
        triples = Mesh.from_arrays([[0, 0, 0]] * 6, [[0, 0, 1]] * 6, [[1, 1, 1, 1]] * 6,
                                   [[0, 0]] * 6, [[0, 1, 2], [3, 4, 5]])
        assert flat == triples and flat.indices.shape == (2, 3)

    def test_arrays_are_read_only(self) -> None:
        mesh = triangle()
        with pytest.raises(ValueError):
            mesh.positions[0, 0] = 99.0
        with pytest.raises(dataclasses.FrozenInstanceError):
            mesh.positions = mesh.normals  # type: ignore[misc]

    def test_empty(self) -> None:
        empty = Mesh.empty()
        assert (empty.vertex_count, empty.triangle_count) == (0, 0)
        empty.validate()
        assert empty.indices.shape == (0, 3)
        with pytest.raises(MeshError, match="empty"):
            empty.bounds()

    def test_bounds(self) -> None:
        low, high = prism_mesh((SQUARE,), 40.0).bounds()
        assert low.tolist() == [-50.0, -50.0, 0.0] and high.tolist() == [50.0, 50.0, 40.0]

    def test_equality_is_by_content(self) -> None:
        assert triangle() == triangle()
        assert triangle() != triangle((0.0, 1.0, 0.0))
        assert triangle() != "a mesh"
        with pytest.raises(TypeError):
            hash(triangle())

    def test_merge_offsets_indices_and_skips_empties(self) -> None:
        a, b = triangle(), prism_mesh((SQUARE,), 10.0)
        merged = Mesh.merge([a, Mesh.empty(), b])
        assert merged.vertex_count == a.vertex_count + b.vertex_count
        assert merged.triangle_count == a.triangle_count + b.triangle_count
        np.testing.assert_array_equal(merged.indices[:1], a.indices)
        np.testing.assert_array_equal(merged.indices[1:], b.indices + a.vertex_count)
        np.testing.assert_array_equal(merged.positions[a.vertex_count:], b.positions)
        merged.validate()
        assert Mesh.merge([]) == Mesh.empty() and Mesh.merge([Mesh.empty()]) == Mesh.empty()

    def test_translated_moves_positions_only(self) -> None:
        moved = triangle().translated(5.0, -3.0, 2.0)
        assert moved.positions[0].tolist() == [5.0, -3.0, 2.0]
        np.testing.assert_array_equal(moved.normals, triangle().normals)
        moved.validate()


# one failing case per defect class the brief names ----------------------------


def _replace(mesh: Mesh, **arrays: np.ndarray) -> Mesh:
    return dataclasses.replace(mesh, **arrays)


class TestValidate:
    def test_non_finite_position(self) -> None:
        positions = triangle().positions.copy()
        positions[1, 2] = np.nan
        with pytest.raises(MeshError, match="non-finite.*positions"):
            _replace(triangle(), positions=positions).validate()

    @pytest.mark.parametrize("name", ["normals", "colors", "uvs"])
    def test_non_finite_attribute(self, name: str) -> None:
        array = getattr(triangle(), name).copy()
        array[0, 0] = np.inf
        with pytest.raises(MeshError, match=f"non-finite.*{name}"):
            _replace(triangle(), **{name: array}).validate()

    # ── fix round 2: a mesh never holds a number that is not finite ──────────

    @pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf, 1e300, -3.5e38],
                             ids=["nan", "inf", "-inf", "1e300", "beyond float32"])
    @pytest.mark.parametrize("name", ["positions", "normals", "colors", "uvs"])
    def test_from_arrays_refuses_what_is_not_finite_in_float32(self, name: str, bad: float) -> None:
        """``1e300`` is a finite float64 and an infinite float32. ``validate()``
        catches it — but production runs with ``validate=False``, so the one
        constructor every builder uses refuses it."""
        good = triangle()
        arrays = {attribute: getattr(good, attribute).astype(np.float64)
                  for attribute in ("positions", "normals", "colors", "uvs")}
        arrays[name][0, 0] = bad
        with pytest.raises(MeshError, match=f"non-finite values in {name} once they are float32"):
            Mesh.from_arrays(**arrays, indices=good.indices)
        arrays[name][0, 0] = 3.0e38  # the largest order of magnitude float32 holds: let through
        assert Mesh.from_arrays(**arrays, indices=good.indices).vertex_count == 3

    def test_prism_mesh_refuses_a_height_that_is_not_finite_in_float32(self) -> None:
        for height in (1e300, 3.5e38, float("inf"), float("nan")):
            with pytest.raises(MeshError, match="a height of .* is not finite in float32"):
                prism_mesh((SQUARE,), height)
        for bad in (1e300, -3.5e38, float("inf"), float("nan")):
            with pytest.raises(MeshError, match="a footprint coordinate .* is not finite in float32"):
                prism_mesh((((0.0, 0.0), (bad, 0.0), (5.0, 5.0)),), 40.0)
            with pytest.raises(MeshError, match="a footprint coordinate"):
                prism_mesh((FRAME,), 40.0, ((((0.0, 0.0), (0.0, bad), (5.0, 5.0)),),))
        assert float(prism_mesh((SQUARE,), 1e6).bounds()[1][2]) == 1e6  # the record's bound builds
        assert prism_mesh((SQUARE,), 0.0) == Mesh.empty() and prism_mesh((SQUARE,), -1e300) == Mesh.empty()

    def test_merge_refuses_a_part_that_is_not_finite(self) -> None:
        positions = triangle().positions.copy()
        positions[0, 0] = np.inf
        broken = _replace(triangle(), positions=positions)  # only reachable by hand
        with pytest.raises(MeshError, match="non-finite"):
            Mesh.merge([triangle(), broken])
        # … also when it is the ONLY part and would come out as it went in (round 2
        # said "merge goes through it"; for one part it did not)
        with pytest.raises(MeshError, match="non-finite values in positions"):
            Mesh.merge([broken])
        with pytest.raises(MeshError, match="non-finite"):
            Mesh.merge([Mesh.empty(), broken, Mesh.empty()])
        assert Mesh.merge([triangle()]) is not None and Mesh.merge([Mesh.empty()]) == Mesh.empty()
        with pytest.raises(MeshError, match="non-finite values in positions"):
            broken.require_finite()
        assert triangle().require_finite() == triangle()

    def test_a_height_that_is_zero_in_float32_gives_no_solid(self) -> None:
        """Review round 3, P2-8. ``prism_mesh((SQUARE,), 1e-46)`` built a solid of
        height 0.0 — walls without an area — and ``validate`` let it pass."""
        for nothing in (1e-46, 1e-300, 5e-324):
            assert prism_mesh((SQUARE,), nothing) == Mesh.empty()
        low = prism_mesh((SQUARE,), 1e-3)  # the record's floor: a solid, ten micrometres high
        assert low.triangle_count == 10 and float(low.bounds()[1][2]) == float(np.float32(1e-3))

    def test_index_out_of_bounds(self) -> None:
        with pytest.raises(MeshError, match="index 3 .* 3 vertices"):
            _replace(triangle(), indices=np.array([[0, 1, 3]], np.uint32)).validate()

    def test_wrong_dtype(self) -> None:
        with pytest.raises(MeshError, match="positions.*float32.*float64"):
            _replace(triangle(), positions=triangle().positions.astype(np.float64)).validate()
        with pytest.raises(MeshError, match="indices.*uint32.*int64"):
            _replace(triangle(), indices=np.array([[0, 1, 2]], np.int64)).validate()

    def test_wrong_shape(self) -> None:
        with pytest.raises(MeshError, match=r"colors.*\(3, 4\).*\(3, 3\)"):
            _replace(triangle(), colors=np.ones((3, 3), np.float32)).validate()
        with pytest.raises(MeshError, match=r"indices.*\(m, 3\)"):
            _replace(triangle(), indices=np.array([0, 1, 2], np.uint32)).validate()

    def test_attribute_count_mismatch(self) -> None:
        with pytest.raises(MeshError, match=r"normals.*\(3, 3\).*\(2, 3\)"):
            _replace(triangle(), normals=np.tile([0.0, 0.0, 1.0], (2, 1)).astype(np.float32)).validate()

    def test_non_unit_normal(self) -> None:
        with pytest.raises(MeshError, match="unit length.*2.0"):
            triangle((0.0, 0.0, 2.0)).validate()
        with pytest.raises(MeshError, match="unit length"):
            triangle((0.0, 0.0, 0.0)).validate()

    def test_flat_face_lit_from_the_wrong_side(self) -> None:
        """The L0 roof bug: the face is wound to look up, its stored normal looks
        down (or sideways) — the sun would light the wrong face."""
        with pytest.raises(MeshError, match=r"flat face.*-1\.0"):
            triangle((0.0, 0.0, -1.0)).validate()
        tilted = (0.0, 0.2, 0.9797959)  # 11.5° off: dot = 0.9798 < 0.99
        with pytest.raises(MeshError, match="flat face"):
            triangle(tilted).validate()
        almost = (0.0, 0.1, 0.99498744)  # 5.7° off: dot = 0.995 — inside the gate
        triangle(almost).validate()

    def test_bent_normal_kinds_are_exempt_from_the_winding_rule(self) -> None:
        """Foliage and grass shade with spherized normals by design
        (``ogp-lush-cinematic`` §2): their flat faces need not store the winding normal."""
        leaf = triangle((0.0, 0.0, -1.0))
        leaf.validate(check_winding=False)
        MeshPart(leaf, "foliage").validate()
        MeshPart(leaf, "grass").validate()
        with pytest.raises(MeshError, match="flat face"):
            MeshPart(leaf, "vc").validate()
        assert frozenset({"foliage", "grass"}) == BENT_NORMAL_KINDS <= MATERIAL_KINDS

    def test_degenerate_triangles_are_ignored_by_the_winding_rule(self) -> None:
        sliver = Mesh.from_arrays(
            [[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [20.0, 0.0, 0.0]], [[0.0, 0.0, -1.0]] * 3,
            [[1, 1, 1, 1]] * 3, [[0, 0]] * 3, [0, 1, 2])
        sliver.validate()

    def test_smooth_faces_are_not_judged_as_flat(self) -> None:
        normals = np.array([[0.0, 0.6, 0.8], [0.6, 0.0, 0.8], [0.0, 0.0, 1.0]], np.float32)
        smooth = _replace(triangle(), normals=normals)
        dots, flat = normal_vs_winding(smooth)
        assert not flat.any() and dots[0] > 0.9
        smooth.validate()


# ── MeshPart ──────────────────────────────────────────────────────────────────


class TestMeshPart:
    def test_defaults(self) -> None:
        part = MeshPart(triangle())
        assert (part.material_kind, part.casts_shadow, part.tinted, part.name) == ("vc", True, False, "")

    def test_unknown_material_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="material_kind 'marble'"):
            MeshPart(triangle(), "marble")

    def test_material_kinds_are_the_spike_s(self) -> None:
        """The kinds the L0 scene file switched on (frozen when L1.10 deleted the spike),
        plus its default ``vc``; ``white`` was the IoU probe's, not a builder's."""
        switched = set(SPIKE["qml"]["material_kinds"])
        assert switched - {"white"} | {"vc"} == MATERIAL_KINDS
        assert frozenset({"vc", "roof", "foliage", "grass", "glass", "water"}) == MATERIAL_KINDS

    def test_parts_compare_by_content(self) -> None:
        assert MeshPart(triangle(), "roof", False) == MeshPart(triangle(), "roof", False)
        assert MeshPart(triangle(), "roof") != MeshPart(triangle(), "vc")


# ── ports from the spike: one rule each, against its frozen answers (L1.10) ───


class TestSpikeDriftGuards:
    def test_srgb_to_linear(self) -> None:
        for colour, theirs in SPIKE["meshes"]["srgb_to_linear"].items():
            np.testing.assert_array_equal(srgb_to_linear(colour), np.asarray(theirs, np.float32))
        with pytest.raises(ValueError):
            srgb_to_linear("b4553d")

    def test_item_seed(self) -> None:
        for key, theirs in SPIKE["meshes"]["item_seed"].items():
            item_id, salt = key.split("|")
            assert item_seed(item_id, salt) == theirs
        assert item_seed("a") != item_seed("b") and item_seed("a") != item_seed("a", "s")

    def test_normal_vs_winding(self) -> None:
        """Also what the retired Qt 3D view built for a hole-free ring: the spike's prism
        WAS its ``extrude_footprint`` (both deleted in L1.10), vertex for vertex."""
        theirs = SPIKE["meshes"]["prism_l_shape_120"]
        ours = prism_mesh((L_SHAPE,), 120.0)
        dots, flat = normal_vs_winding(ours)
        np.testing.assert_array_equal(dots, np.asarray(theirs["dots"], dots.dtype))
        np.testing.assert_array_equal(flat, np.asarray(theirs["flat"], flat.dtype))
        np.testing.assert_array_equal(ours.positions, np.asarray(theirs["positions"],
                                                                 ours.positions.dtype))
        np.testing.assert_array_equal(ours.normals, np.asarray(theirs["normals"],
                                                               ours.normals.dtype))


# ── the default builder (honest v0) ───────────────────────────────────────────


class TestDefaultBuilder:
    @pytest.mark.parametrize("height", [40.0, 0.1, 123.456789, 450.0, 1e-3, 33.3])
    def test_prism_top_is_exactly_the_height(self, height: float) -> None:
        parts = default_builder(record(height_cm=height))
        low, high = default_mesh(record(height_cm=height)).bounds()
        assert float(high[2]) == float(np.float32(height))  # exact, in the float32 the engine gets
        assert float(low[2]) == 0.0  # the item's own ground plane: base_cm is the transform's
        for part in parts:
            part.validate()

    def test_footprint_is_the_local_footprint(self) -> None:
        mesh = default_mesh(record(footprints=(L_SHAPE,)))
        low, high = mesh.bounds()
        assert low[:2].tolist() == [0.0, 0.0] and high[:2].tolist() == [100.0, 100.0]
        # 6 walls x 2 triangles + 4 cap triangles (n - 2 for a simple polygon)
        assert mesh.triangle_count == 16
        dots, flat = normal_vs_winding(mesh)
        assert flat.all() and dots.min() >= 0.99

    def test_prism_mesh_takes_a_clockwise_ring_and_still_faces_out(self) -> None:
        """``Record`` refuses a clockwise outer ring; the geometry helper under it
        stays tolerant, as the Qt 3D extrusion it mirrors is."""
        mesh = prism_mesh((tuple(reversed(L_SHAPE)),), 40.0)
        mesh.validate()
        assert mesh.triangle_count == prism_mesh((L_SHAPE,), 40.0).triangle_count == 16
        assert cap_area(mesh) == pytest.approx(7500.0)

    def test_part_is_neutral_and_shows_the_items_fill(self) -> None:
        """A pure colour or pattern change must not rebuild geometry: the mesh carries
        no colour of the item, and the part asks the sink for the item's own fill
        picture (#628 follow-up) - which for SOLID is a flat tint of the same colour."""
        sides, cap = default_builder(record())
        assert (sides.tinted, sides.fill_texture, sides.name) == (True, False, "prism_sides")
        assert (cap.tinted, cap.fill_texture, cap.name) == (False, True, "prism")
        assert sides.material_kind == cap.material_kind == "vc"
        assert sides.casts_shadow is cap.casts_shadow is True
        assert np.all(sides.mesh.colors == 1.0) and np.all(cap.mesh.colors == 1.0)
        recoloured = record(material=Material("RAISED_BED", fill_rgba=(1, 2, 3, 255)))
        assert default_builder(recoloured) == (sides, cap)

    def test_no_height_means_no_parts(self) -> None:
        """A lawn, a path, a rain barrel: the resolver gives no height, so there is
        no solid — the ground bake (L1.5) paints flat surfaces."""
        assert default_builder(record(height_cm=None)) == ()

    def test_the_prism_shows_the_items_fill_with_plan_uvs(self) -> None:
        """#628 follow-up: the raised shape keeps its texture. The part asks for the
        item's fill picture and carries the canvas's phase — ``(position + paint_origin)
        / 256`` on its top, a wrapped ``u`` on its walls — not raw record coordinates
        (the record's footprint is centred on the anchor ``paint_origin``)."""
        from open_garden_planner.core.scene3d import PATTERN_TILE_CM

        origin = (137.0, -42.0)
        rec = record(height_cm=100.0,
                     params=Params({"seed": "x", "paint_origin": origin}))
        sides, cap = default_builder(rec)
        assert cap.fill_texture is True and cap.tinted is False
        assert sides.fill_texture is False and sides.tinted is True
        mesh = cap.mesh
        assert np.all(mesh.normals[:, 2] > 0.999), "the cap is the top face"
        expected = (mesh.positions[:, :2] + np.asarray(origin)) / PATTERN_TILE_CM
        assert np.allclose(mesh.uvs, expected)

    def test_a_fill_part_is_vc_only_and_untinted(self) -> None:
        """The rules ``MeshPart.__post_init__`` holds (a fill picture is a base colour
        map: only the ``vc`` material takes one, and it already carries the colour)."""
        with pytest.raises(ValueError, match="vc"):
            MeshPart(prism_mesh([SQUARE], 10.0), "roof", fill_texture=True)
        with pytest.raises(ValueError, match="not tinted"):
            MeshPart(prism_mesh([SQUARE], 10.0), "vc", tinted=True, fill_texture=True)
        with pytest.raises(ValueError, match="ground detail"):
            MeshPart(prism_mesh([SQUARE], 10.0), "vc", casts_shadow=False,
                     ground_detail=True, fill_texture=True)

    def test_several_rings_become_one_part(self) -> None:
        other = tuple((x + 300.0, y) for x, y in SQUARE)
        rec = record(shape="polyline", footprints=(SQUARE, other),
                     path=((-50.0, 0.0), (350.0, 0.0)), path_width_cm=100.0)
        assert default_mesh(rec).triangle_count == 2 * (8 + 2)
        for part in default_builder(rec):
            part.validate()

    def test_degenerate_footprints_give_no_parts(self) -> None:
        assert default_builder(record(footprints=())) == ()
        assert prism_mesh((SQUARE[:2],), 40.0) == Mesh.empty()
        assert prism_mesh((((0.0, 0.0), (5.0, 0.0), (9.0, 0.0)),), 40.0) == Mesh.empty()
        assert prism_mesh((SQUARE,), 0.0) == Mesh.empty()

    # ── holes (fix round 1, P1-1) ─────────────────────────────────────────────

    def test_a_hole_is_cut_out_of_the_cap(self) -> None:
        """The closed fence: 3.6 m² of stroke, not the 80 m² it encloses."""
        rec = record(footprints=(FRAME,), holes=((FRAME_HOLE,),))
        mesh = default_mesh(rec)
        for part in default_builder(rec):
            part.validate()
        assert cap_area(mesh) == pytest.approx(FRAME_AREA, rel=1e-6)
        assert cap_area(mesh) < 0.05 * 1010.0 * 810.0
        # 4 outer walls + 4 hole walls, two triangles each, + a cap of 4 + 4 + 2 - 2
        assert mesh.triangle_count == 16 + 8
        assert float(mesh.bounds()[1][2]) == 40.0

    def test_walls_face_away_from_the_solid_on_both_sides(self) -> None:
        holed = record(footprints=(FRAME,), holes=((FRAME_HOLE,),))
        walls, _cap = default_builder(holed)
        assert_walls_face_away_from_the_solid(walls.mesh, holed.regions)
        walls, _cap = default_builder(record(footprints=(L_SHAPE,)))
        assert_walls_face_away_from_the_solid(walls.mesh, record(footprints=(L_SHAPE,)).regions)

    def test_prism_mesh_without_the_holes_argument_fills_them(self) -> None:
        """Why ``holes`` must be passed along: the outer ring alone IS the slab."""
        slab = prism_mesh((FRAME,), 40.0)
        assert cap_area(slab) == pytest.approx(1010.0 * 810.0, rel=1e-6)
        with pytest.raises(ValueError, match="2 hole groups for 1 footprint"):
            prism_mesh((FRAME,), 40.0, ((FRAME_HOLE,), ()))

    # ── any sequence of pairs is a ring (fix round 2, P2-7) ───────────────────

    def test_prism_mesh_takes_lists_and_numpy_rows(self) -> None:
        """At ``aaec048`` it took any sequence; with the cached polygon functions
        a list of lists raised ``TypeError: unhashable type``. Coerced now."""
        reference = prism_mesh((L_SHAPE,), 40.0)
        assert prism_mesh([[list(p) for p in L_SHAPE]], 40.0) == reference
        assert prism_mesh([np.array(L_SHAPE)], 40.0) == reference
        assert prism_mesh(np.array([L_SHAPE]), 40.0) == reference
        assert prism_mesh([np.array(L_SHAPE, dtype=np.float32)], 40.0) == reference
        assert prism_mesh([[(0, 0), (100, 0), (100, 50), (50, 50), (50, 100), (0, 100)]], 40.0) == reference
        holed = prism_mesh((FRAME,), 40.0, ((FRAME_HOLE,),))
        assert prism_mesh([np.array(FRAME)], 40.0, [[np.array(FRAME_HOLE)]]) == holed
        assert prism_mesh([[list(p) for p in FRAME]], 40.0, [[[list(p) for p in FRAME_HOLE]]]) == holed
        assert prism_mesh(np.array([FRAME]), 40.0, np.array([[FRAME_HOLE]])) == holed
        assert prism_mesh([], 40.0) == Mesh.empty() and prism_mesh(np.zeros((0, 4, 2)), 40.0) == Mesh.empty()

    # ── a triangle that is nothing in float32 (fix round 2) ───────────────────

    def test_a_cap_triangle_that_is_nothing_in_float32_is_left_out(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A mesh is float32. This ring is a sliver 71 cm long and 0.00001 cm wide:
        counter-clockwise in float64, and its one cap triangle comes out wound
        DOWNWARDS once its corners are rounded to float32 — a flat face lit from
        below. Such a triangle is not emitted (``_FLOAT32_SLIVER``)."""
        from open_garden_planner.core.scene3d import build as build_module
        from open_garden_planner.core.scene3d import is_simple_ring, signed_area

        sliver = ((890.43, 864.001), (925.0150023, 872.1739903), (959.6, 880.347))
        assert is_simple_ring(sliver) and 0.0 < signed_area(sliver) < 0.001
        mesh = prism_mesh((sliver,), 40.0)
        mesh.validate()
        assert mesh.triangle_count == 6  # three walls and no cap
        monkeypatch.setattr(build_module, "_FLOAT32_SLIVER", 0.0)
        unfiltered = prism_mesh((sliver,), 40.0)
        assert unfiltered.triangle_count == 7
        with pytest.raises(MeshError, match="not its winding normal"):
            unfiltered.validate()

    def test_an_ordinary_cap_loses_nothing_to_that_rule(self) -> None:
        """The threshold is far below anything drawn: the smallest things the
        suite builds — a speck of a hundredth of a centimetre, a sliver a
        thousandth wide — keep every cap triangle."""
        for ring, triangles in (
            (((0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01)), 8 + 2),
            (((0.0, 0.0), (1000.0, 0.0), (1000.0, 0.001), (0.0, 0.001)), 8 + 2),
            (tuple((x + 4000.0, y + 4000.0) for x, y in L_SHAPE), 12 + 4),
        ):
            assert prism_mesh((ring,), 40.0).triangle_count == triangles

    # ── self-crossing rings (fix round 1, P2-6) ───────────────────────────────

    def test_a_bow_tie_is_refused_not_built_wrong(self) -> None:
        """Before: the ear clipper produced a cap wound the wrong way, validate()
        failed and production (validate=False) shipped it. Now the builder says no."""
        with pytest.raises(ValueError, match="not a simple polygon"):
            prism_mesh((BOW_TIE,), 40.0)
        lopsided = ((0.0, 0.0), (400.0, 300.0), (400.0, 0.0), (0.0, 200.0))[::-1]
        with pytest.raises(ValueError, match="not a simple polygon"):
            default_builder(record(shape="polygon", footprints=(lopsided,)))

    @pytest.mark.parametrize(
        "ring",
        [((0.0, 0.0), (50.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)),
         ((0.0, 0.0), (50.0, 0.0), (100.0, 0.0), (100.0, 50.0), (100.0, 100.0), (50.0, 100.0),
          (0.0, 100.0), (0.0, 50.0)),
         ((0.0, 0.0), (300.0, 0.0), (300.0, 100.0), (200.0, 100.0), (200.0, 300.0), (100.0, 300.0),
          (100.0, 100.0), (0.0, 100.0)),
         ((0.0, 0.0), (10.0, 0.0), (20.0, 0.0), (30.0, 0.0), (15.0, 40.0)),
         ((0.0, 0.0), (1000.0, 0.0), (1000.0, 0.001), (0.0, 0.001)),
         ((0.0, 0.0), (0.01, 0.0), (0.01, 0.01), (0.0, 0.01))],
        ids=["a vertex on an edge", "a vertex on every edge", "a T with a collinear run",
             "three collinear and an apex", "a sliver", "a hundredth of a centimetre"],
    )
    def test_awkward_but_simple_rings_still_build_the_right_solid(self, ring) -> None:
        """Refusing a ring that crosses itself must not cost the rings that are
        merely awkward: vertices in a row along an edge (a vertex-edited polygon
        has them), a sliver, a speck. Each builds, validates, and its cap is the
        ring's area — ``plan_margin_cm=0.0``: nothing outside the footprint at all."""
        rec = record(shape="polygon", footprints=(ring,))
        parts = verify_builder(default_builder, rec, plan_margin_cm=0.0)
        assert cap_area(Mesh.merge([part.mesh for part in parts])) == pytest.approx(
            rec.plan_area_cm2, rel=1e-6)

    def test_a_frame_whose_rings_have_collinear_vertices(self) -> None:
        outer = ((0.0, 0.0), (100.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0))
        hole = ((50.0, 50.0), (50.0, 150.0), (100.0, 150.0), (150.0, 150.0), (150.0, 50.0),
                (100.0, 50.0))
        rec = record(shape="polygon", footprints=(outer,), holes=((hole,),))
        parts = verify_builder(default_builder, rec, plan_margin_cm=0.0)
        mesh = Mesh.merge([part.mesh for part in parts])
        assert cap_area(mesh) == pytest.approx(200.0 * 200.0 - 100.0 * 100.0, rel=1e-6)
        walls = next(part.mesh for part in parts if part.tinted)
        assert_walls_face_away_from_the_solid(walls, rec.regions)

    def test_output_does_not_depend_on_pose_material_or_name(self) -> None:
        verify_builder(default_builder, record())
        verify_builder(default_builder, record(height_cm=None))


# ── registry ──────────────────────────────────────────────────────────────────


def _roof_builder(rec: Record) -> tuple[MeshPart, ...]:
    return (MeshPart(prism_mesh(rec.footprints, 10.0), "roof"),)


class TestRegistry:
    def test_unknown_kind_falls_back_to_the_default(self) -> None:
        registry = BuilderRegistry()
        assert registry.builder_for("ANYTHING") is default_builder
        assert registry.build(record()) == default_builder(record())
        assert registry.kinds() == frozenset()

    def test_registered_builder_wins_for_its_kind_only(self) -> None:
        registry = BuilderRegistry()
        registry.register("HOUSE", _roof_builder)
        assert registry.builder_for("HOUSE") is _roof_builder
        assert registry.builder_for("TOOL_SHED") is default_builder
        assert registry.build(record(kind="HOUSE"))[0].material_kind == "roof"
        assert registry.kinds() == frozenset({"HOUSE"})

    def test_double_registration_is_an_error_unless_asked_for(self) -> None:
        registry = BuilderRegistry()
        registry.register("HOUSE", _roof_builder)
        with pytest.raises(ValueError, match="HOUSE"):
            registry.register("HOUSE", default_builder)
        registry.register("HOUSE", default_builder, replace=True)
        assert registry.builder_for("HOUSE") is default_builder

    def test_register_many_and_custom_default(self) -> None:
        registry = BuilderRegistry(default=_roof_builder)
        registry.register_many(("RAISED_BED", "CONTAINER"), default_builder)
        assert registry.builder_for("TREE") is _roof_builder
        assert registry.builder_for("CONTAINER") is default_builder

    def test_the_version_moves_with_every_registration_and_only_then(self) -> None:
        """Fix round 2, P2-6: ``SceneSync`` matches items to builders by identity and
        looks for items to rebuild only when this number moved."""
        registry = BuilderRegistry()
        assert registry.version == 0
        registry.register("HOUSE", _roof_builder)
        assert registry.version == 1
        registry.builder_for("HOUSE"), registry.build(record()), registry.kinds()
        assert registry.version == 1  # reading changes nothing
        with pytest.raises(ValueError):
            registry.register("HOUSE", default_builder)
        assert registry.version == 1  # a refused registration changes nothing
        registry.register("HOUSE", default_builder, replace=True)
        registry.register_many(("A", "B"), _roof_builder)
        assert registry.version == 4
        assert all(registry.builder_for(kind) is registry.builder_for(kind)
                   for kind in ("HOUSE", "A", "NO SUCH KIND"))  # the same object, call after call


# ── verify_builder: the test instrument L1.6 / L1.7 use ───────────────────────


class TestVerifyBuilder:
    def test_returns_the_parts(self) -> None:
        assert verify_builder(default_builder, record()) == default_builder(record())

    def test_a_builder_reading_the_material_is_caught(self) -> None:
        def bad(rec: Record) -> tuple[MeshPart, ...]:
            height = 10.0 if rec.material.fill_rgba == (120, 80, 40, 255) else 20.0
            return (MeshPart(prism_mesh(rec.footprints, height)),)

        with pytest.raises(BuilderContractError, match="material"):
            verify_builder(bad, record())

    def test_a_builder_reading_the_transform_is_caught(self) -> None:
        def bad(rec: Record) -> tuple[MeshPart, ...]:
            mesh = prism_mesh(rec.footprints, 10.0).translated(rec.transform.east_cm, 0.0, 0.0)
            return (MeshPart(mesh),)

        with pytest.raises(BuilderContractError, match="transform"):
            verify_builder(bad, record())

    @pytest.mark.parametrize("field", ["item_id", "name", "parent_id"])
    def test_a_builder_reading_an_unsigned_field_is_caught(self, field: str) -> None:
        def bad(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(rec.footprints, 10.0 + len(str(getattr(rec, field))))),)

        with pytest.raises(BuilderContractError, match=field):
            verify_builder(bad, record())

    def test_a_non_deterministic_builder_is_caught(self) -> None:
        counter = iter(range(1, 100))

        def bad(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(rec.footprints, float(next(counter)))),)

        with pytest.raises(BuilderContractError, match="deterministic"):
            verify_builder(bad, record())

    def test_an_invalid_mesh_is_caught(self) -> None:
        def bad(_rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(triangle((0.0, 0.0, -1.0))),)

        with pytest.raises(BuilderContractError, match="flat face"):
            verify_builder(bad, record())

    def test_a_wrong_return_type_is_caught(self) -> None:
        with pytest.raises(BuilderContractError, match="tuple of MeshPart"):
            verify_builder(lambda _rec: [MeshPart(triangle())], record())  # type: ignore[arg-type,return-value]
        with pytest.raises(BuilderContractError, match="tuple of MeshPart"):
            verify_builder(lambda _rec: (triangle(),), record())  # type: ignore[arg-type,return-value]

    def test_a_solid_taller_than_the_plan_says_is_caught(self) -> None:
        """Truth gate "built heights" (``ogp-lush-cinematic`` §1): the top of a
        shadow-casting item is its resolved height — never above it."""
        def bad(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(rec.footprints, 46.0)),)  # +15 % decoration on top

        with pytest.raises(BuilderContractError, match="46.*40"):
            verify_builder(bad, record())
        verify_builder(bad, record(), height_tolerance=0.2)  # an explicit allowance is the caller's

    def test_height_tolerance_in_centimetres(self) -> None:
        """Issue #385's L1.6 gate is ±0.5 cm ABSOLUTE: on a 450 cm house the default
        1 % would let 4.5 cm through."""
        def builder_off_by(delta: float):
            def build(rec: Record) -> tuple[MeshPart, ...]:
                assert rec.height_cm is not None
                return (MeshPart(prism_mesh(rec.footprints, rec.height_cm + delta)),)
            return build

        house = record(height_cm=450.0)
        verify_builder(builder_off_by(4.0), house)  # inside 1 %
        with pytest.raises(BuilderContractError, match="454.*450.*±0.5 cm"):
            verify_builder(builder_off_by(4.0), house, height_tolerance_cm=0.5)
        verify_builder(builder_off_by(0.4), house, height_tolerance_cm=0.5)
        with pytest.raises(BuilderContractError, match="449.4"):
            verify_builder(builder_off_by(-0.6), house, height_tolerance_cm=0.5)

    # ── the plan-view check (fix round 1, P1-1) ───────────────────────────────

    def test_a_builder_that_fills_a_hole_is_caught(self) -> None:
        """The pre-fix default builder, reconstructed: every ring a solid. It passed
        every gate; now it cannot."""
        def every_ring_a_solid(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            rings = [*rec.footprints, *(hole for group in rec.holes for hole in group)]
            return (MeshPart(prism_mesh(rings, rec.height_cm)),)

        fence = record(footprints=(FRAME,), holes=((FRAME_HOLE,),))
        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(every_ring_a_solid, fence)

        def outer_ring_only(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            return (MeshPart(prism_mesh(rec.footprints, rec.height_cm)),)  # forgot rec.holes

        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(outer_ring_only, fence)
        verify_builder(default_builder, fence)
        verify_builder(default_builder, fence, plan_margin_cm=0.0)
        assert HOLE_COVER_LIMIT == 0.5

    def test_a_small_hole_is_protected_too(self) -> None:
        """The limit is a share of the hole, not a distance: a fence around a
        60 cm planter is caught like one around a garden."""
        outer = ((-40.0, -40.0), (40.0, -40.0), (40.0, 40.0), (-40.0, 40.0))
        hole = ((-30.0, -30.0), (-30.0, 30.0), (30.0, 30.0), (30.0, -30.0))
        small = record(footprints=(outer,), holes=((hole,),))

        def filled(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(rec.footprints, 40.0)),)

        with pytest.raises(BuilderContractError, match="of a hole"):
            verify_builder(filled, small)

    def test_a_hole_under_two_huge_triangles_is_seen(self) -> None:
        """The hole is sampled, not the triangles: a slab of two triangles a
        hundred times the size of the hole it covers has no sample point of its
        own inside that hole, and is caught all the same."""
        outer = ((-500.0, -500.0), (500.0, -500.0), (500.0, 500.0), (-500.0, 500.0))
        hole = ((80.0, 210.0), (80.0, 290.0), (160.0, 290.0), (160.0, 210.0))
        well = record(footprints=(outer,), holes=((hole,),))
        slab = (MeshPart(prism_mesh(well.footprints, 40.0)),)
        assert plan_overreach(slab, well.regions, 0.0)[1] == 1.0
        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(lambda rec: (MeshPart(prism_mesh(rec.footprints, 40.0)),), well)
        verify_builder(default_builder, well)

    # ── the hole bound has a floor (fix round 2, P2-9) ────────────────────────

    #: Two runs of a 10 cm stroke, 12 cm apart: the 2 cm x 490 cm sliver between them is a hole.
    SLIVER_OUTER = ((0.0, 0.0), (22.0, 0.0), (22.0, 500.0), (0.0, 500.0))
    SLIVER = ((10.0, 5.0), (10.0, 495.0), (12.0, 495.0), (12.0, 5.0))  # clockwise

    @staticmethod
    def _panels(rec: Record) -> tuple[MeshPart, ...]:
        """An honest fence: a 12 cm panel on each 10 cm run. They meet over the sliver."""
        assert rec.height_cm is not None
        runs = [((-1.0, 0.0), (11.0, 0.0), (11.0, 500.0), (-1.0, 500.0)),
                ((11.0, 0.0), (23.0, 0.0), (23.0, 500.0), (11.0, 500.0))]
        return (MeshPart(prism_mesh(runs, rec.height_cm), name="panels"),)

    def test_a_sliver_of_a_hole_is_not_judged(self) -> None:
        """The re-review's case: this fence was refused for "covering 100 %" of a
        hole 2 cm wide. A hole into which no circle of ``HOLE_MIN_WIDTH_CM``
        fits is a sliver and is not judged."""
        assert HOLE_MIN_WIDTH_CM == 10.0
        fence = record(kind="FENCE", shape="polyline", footprints=(self.SLIVER_OUTER,),
                       holes=((self.SLIVER,),), height_cm=120.0)
        parts = verify_builder(self._panels, fence)
        assert plan_overreach(parts, fence.regions, PLAN_MARGIN_CM) == (0.0, 0.0)
        verify_builder(default_builder, fence)

    @pytest.mark.parametrize("width", [8.0, 9.5])
    def test_just_under_the_floor_is_still_a_sliver(self, width: float) -> None:
        outer = ((0.0, 0.0), (20.0 + width, 0.0), (20.0 + width, 500.0), (0.0, 500.0))
        hole = ((10.0, 5.0), (10.0, 495.0), (10.0 + width, 495.0), (10.0 + width, 5.0))
        fence = record(kind="FENCE", shape="polyline", footprints=(outer,), holes=((hole,),),
                       height_cm=120.0)
        slab = (MeshPart(prism_mesh(fence.footprints, 120.0)),)
        assert plan_overreach(slab, fence.regions, PLAN_MARGIN_CM)[1] == 0.0

    @pytest.mark.parametrize("width", [14.0, 20.0, 60.0])
    def test_a_hole_wider_than_the_floor_is_judged_whole_as_before(self, width: float) -> None:
        """A floor, not another measure: from 10 cm on a hole is judged on every
        point of it, rim included — the numbers other stories pinned stand."""
        outer = ((0.0, 0.0), (20.0 + width, 0.0), (20.0 + width, 500.0), (0.0, 500.0))
        hole = ((10.0, 5.0), (10.0, 495.0), (10.0 + width, 495.0), (10.0 + width, 5.0))
        fence = record(kind="FENCE", shape="polyline", footprints=(outer,), holes=((hole,),),
                       height_cm=120.0)

        def slab(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh(rec.footprints, 120.0)),)  # the hole filled

        assert plan_overreach(slab(fence), fence.regions, PLAN_MARGIN_CM)[1] == 1.0
        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(slab, fence)

        def rim(rec: Record) -> tuple[MeshPart, ...]:
            """Panels that overhang the stroke by 4 cm on the hole's side: 8 cm of its width."""
            runs = [((0.0, 0.0), (14.0, 0.0), (14.0, 500.0), (0.0, 500.0)),
                    ((6.0 + width, 0.0), (20.0 + width, 0.0), (20.0 + width, 500.0), (6.0 + width, 500.0))]
            return (MeshPart(prism_mesh(runs, 120.0)),)

        cover = plan_overreach(rim(fence), fence.regions, PLAN_MARGIN_CM)[1]
        assert cover == pytest.approx(8.0 / width, abs=0.05)  # the rim counts, as it always did
        if cover > HOLE_COVER_LIMIT:
            with pytest.raises(BuilderContractError, match="of a hole"):
                verify_builder(rim, fence)
        else:
            verify_builder(rim, fence)

    # ── an island in a hole is ground, not hole (fix round 3, P2-2) ───────────

    #: A square with a square hole, and an island standing in that hole — three
    #: nested rings: what a self-crossing outline can resolve into.
    OUTER = ((0.0, 0.0), (600.0, 0.0), (600.0, 600.0), (0.0, 600.0))
    MOAT = ((40.0, 40.0), (40.0, 560.0), (560.0, 560.0), (560.0, 40.0))  # clockwise
    ISLAND = ((80.0, 80.0), (520.0, 80.0), (520.0, 520.0), (80.0, 520.0))

    def test_an_island_in_a_hole_is_not_building_over_the_hole(self) -> None:
        """The re-review's case: a correct record, a correct default build — and
        ``verify_builder`` refused it for "covering 69 % of a hole". The 69 % was
        the island: a region of its own, standing where the plan says it stands."""
        nested = record(shape="polygon", footprints=(self.OUTER, self.ISLAND), holes=((self.MOAT,), ()))
        parts = verify_builder(default_builder, nested)
        assert plan_overreach(parts, nested.regions, PLAN_MARGIN_CM) == (0.0, 0.0)
        assert cap_area(Mesh.merge([part.mesh for part in parts])) == pytest.approx(
            nested.plan_area_cm2)
        # what is still caught: the moat itself built over — the open part of the hole
        def moat_filled(rec: Record) -> tuple[MeshPart, ...]:
            return (MeshPart(prism_mesh((self.OUTER,), 40.0)),)

        assert plan_overreach(moat_filled(nested), nested.regions, PLAN_MARGIN_CM)[1] == 1.0
        with pytest.raises(BuilderContractError, match="covers 100% of a hole"):
            verify_builder(moat_filled, nested)
        # … and the same hole WITHOUT an island in the record is judged whole, as before
        hollow = record(shape="polygon", footprints=(self.OUTER,), holes=((self.MOAT,),))
        island_only = (MeshPart(prism_mesh((self.ISLAND,), 40.0)),)
        assert plan_overreach(island_only, hollow.regions, PLAN_MARGIN_CM)[1] == pytest.approx(
            440.0 ** 2 / 520.0 ** 2, abs=0.03)  # 72 % of the hole: a builder that invented an island

    def test_half_a_hole_covered_is_half(self) -> None:
        outer = ((-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0))
        hole = ((-50.0, -50.0), (-50.0, 50.0), (50.0, 50.0), (50.0, -50.0))
        half = record(footprints=(outer,), holes=((hole,),))
        west = ((-100.0, -100.0), (0.0, -100.0), (0.0, 100.0), (-100.0, 100.0))
        parts = (MeshPart(prism_mesh((west,), 40.0)),)
        assert plan_overreach(parts, half.regions, 0.0)[1] == pytest.approx(0.5, abs=0.03)

    def test_reaching_beyond_the_footprint_needs_saying(self) -> None:
        def with_eaves(overhang: float):
            def build(rec: Record) -> tuple[MeshPart, ...]:
                ring = tuple((x + math.copysign(overhang, x), y + math.copysign(overhang, y))
                             for x, y in rec.footprints[0])
                return (MeshPart(prism_mesh((ring,), 40.0)),)
            return build

        verify_builder(with_eaves(35.0), record())  # inside the default reach
        assert PLAN_MARGIN_CM == 50.0
        with pytest.raises(BuilderContractError, match="more than 50 cm outside"):
            verify_builder(with_eaves(120.0), record())
        with pytest.raises(BuilderContractError, match="more than 0 cm outside"):
            verify_builder(with_eaves(35.0), record(), plan_margin_cm=0.0)
        verify_builder(with_eaves(120.0), record(), plan_margin_cm=130.0)
        verify_builder(with_eaves(120.0), record(), plan_margin_cm=None)  # switched off

    # ── the plan view bounds EXCESS, never coverage ──────────────────────────

    def test_a_sparse_plant_inside_its_canopy_passes(self) -> None:
        """A flower, a grass tuft: a few blades standing in the canopy circle cover
        a fraction of a percent of it. The plan view asks no mesh to fill its
        footprint — checked with the very call the plant builders make."""
        canopy = tuple((60.0 * math.cos(2.0 * math.pi * k / 24), 60.0 * math.sin(2.0 * math.pi * k / 24))
                       for k in range(24))
        plant = record(kind="PERENNIAL", shape="circle", footprints=(canopy,), height_cm=80.0)

        def tuft(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            blades = [((x - 1.0, y - 1.0), (x + 1.0, y - 1.0), (x + 1.0, y + 1.0), (x - 1.0, y + 1.0))
                      for x, y in ((0.0, 0.0), (20.0, 10.0), (-25.0, 5.0), (5.0, -30.0), (-10.0, -15.0))]
            return (MeshPart(prism_mesh(blades, rec.height_cm), name="blades"),)

        parts = verify_builder(tuft, plant, height_tolerance=0.03)
        assert cap_area(parts[0].mesh) < 0.002 * plant.plan_area_cm2  # 20 cm² of 11,000
        assert plan_overreach(parts, plant.regions, PLAN_MARGIN_CM) == (0.0, 0.0)
        verify_builder(tuft, plant, plan_margin_cm=0.0)  # … and it is strictly inside as well

    def test_a_canopy_a_few_percent_wider_than_its_circle_passes(self) -> None:
        """Foliage whose hull is 102.3 % of the canopy circle (L1.7's measured upper
        end) reaches 1.1 % of the radius past it — far inside the default reach."""
        def ring(radius: float) -> tuple[tuple[float, float], ...]:
            return tuple((radius * math.cos(2.0 * math.pi * k / 24), radius * math.sin(2.0 * math.pi * k / 24))
                         for k in range(24))

        tree = record(kind="TREE", shape="circle", footprints=(ring(250.0),), height_cm=600.0)

        def crown(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            return (MeshPart(prism_mesh((ring(250.0 * math.sqrt(1.023)),), rec.height_cm), name="crown"),)

        verify_builder(crown, tree, height_tolerance=0.03)

    def test_posts_and_pickets_inside_a_closed_fence_pass(self) -> None:
        """A closed fence built the way a fence is built — a post every metre along
        the centre line, each wider than the stroke — covers a sliver of the
        stroke and next to nothing of the hole. With the call L1.6 makes."""
        fence = record(kind="FENCE", shape="polyline", footprints=(FRAME,), holes=((FRAME_HOLE,),),
                       height_cm=120.0)
        centres = ([(float(x), y) for x in range(-500, 501, 100) for y in (-400.0, 400.0)]
                   + [(x, float(y)) for y in range(-300, 301, 100) for x in (-500.0, 500.0)])

        def posts(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            squares = [((x - 6.0, y - 6.0), (x + 6.0, y - 6.0), (x + 6.0, y + 6.0), (x - 6.0, y + 6.0))
                       for x, y in centres]
            return (MeshPart(prism_mesh(squares, rec.height_cm), name="posts"),)

        parts = verify_builder(posts, fence)
        beyond, hole_cover = plan_overreach(parts, fence.regions, PLAN_MARGIN_CM)
        assert beyond == 0.0 and hole_cover < 0.01
        assert cap_area(parts[0].mesh) < 0.2 * fence.plan_area_cm2  # 36 posts of 144 cm² on 36,000

    def test_each_plan_bound_has_its_own_switch(self) -> None:
        fence = record(footprints=(FRAME,), holes=((FRAME_HOLE,),))

        def slab(rec: Record) -> tuple[MeshPart, ...]:
            assert rec.height_cm is not None
            return (MeshPart(prism_mesh(rec.footprints, rec.height_cm)),)  # the hole filled

        with pytest.raises(BuilderContractError, match="of a hole"):
            verify_builder(slab, fence)
        with pytest.raises(BuilderContractError, match="of a hole"):
            verify_builder(slab, fence, plan_margin_cm=None)  # the hole bound stands alone
        # the other bound sees it too: the middle of an 8 m hole is far outside the footprint
        with pytest.raises(BuilderContractError, match="more than 50 cm outside"):
            verify_builder(slab, fence, hole_cover_limit=None)
        with pytest.raises(BuilderContractError, match="more than 50 cm outside"):
            verify_builder(slab, fence, hole_cover_limit=1.0)  # tuned, not off
        verify_builder(slab, fence, plan_margin_cm=None, hole_cover_limit=None)  # both off: on the caller
        small = record(footprints=(((-40.0, -40.0), (40.0, -40.0), (40.0, 40.0), (-40.0, 40.0)),),
                       holes=((((-30.0, -30.0), (-30.0, 30.0), (30.0, 30.0), (30.0, -30.0)),),))
        with pytest.raises(BuilderContractError, match="of a hole"):
            verify_builder(slab, small)  # a 60 cm hole: only the hole bound can see this one
        verify_builder(slab, small, hole_cover_limit=None)

    def test_plan_overreach_numbers(self) -> None:
        fence = record(footprints=(FRAME,), holes=((FRAME_HOLE,),))
        good = default_builder(fence)
        assert plan_overreach(good, fence.regions, 0.0) == (0.0, 0.0)
        slab = (MeshPart(prism_mesh(fence.footprints, 40.0)),)
        beyond, cover = plan_overreach(slab, fence.regions, 0.0)
        assert cover == 1.0
        # ``beyond`` is the four-points-per-triangle estimate: the slab's cap is two
        # triangles whose every sample lands in the hole, so it reads the whole cap
        # (1010 x 810) where the truth is the hole (990 x 790) — a net for gross
        # errors, as its docstring says, and here it is on the safe side.
        assert 990.0 * 790.0 <= beyond <= 1010.0 * 810.0 + 1e-6
        assert plan_overreach((), fence.regions, 0.0) == (0.0, 0.0)
