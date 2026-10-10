"""Mesh container, mesh parts and the builder seam (Phase 17 L1.1, #385, gate G7).

Qt-free. ``Mesh.validate()`` must catch each defect class with one failing case
each — including the L0 "wrong roof slope lit" bug (a flat face storing a normal
that is not its winding normal) — and pass everything the default builder emits.
The meshes of REAL canvas items are validated in
``tests/integration/test_scene3d_snapshot.py``.
"""

from __future__ import annotations

import dataclasses
import re
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
    prism_mesh,
    srgb_to_linear,
    verify_builder,
)

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
L_SHAPE = ((0.0, 0.0), (100.0, 0.0), (100.0, 50.0), (50.0, 50.0), (50.0, 100.0), (0.0, 100.0))
REPO = Path(__file__).resolve().parents[2]


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
        """Drift guard (dies with the spike in L1.10): the kinds the L0 scene file
        switches on, plus its default ``vc``; ``white`` is the IoU probe's, not a
        builder's."""
        qml = (REPO / "src/open_garden_planner/spike_q3d/qml/GardenSpike.qml").read_text("utf-8")
        switched = set(re.findall(r'modelData\.kind === "(\w+)"', qml))
        assert switched - {"white"} | {"vc"} == MATERIAL_KINDS
        assert frozenset({"vc", "roof", "foliage", "grass", "glass", "water"}) == MATERIAL_KINDS

    def test_parts_compare_by_content(self) -> None:
        assert MeshPart(triangle(), "roof", False) == MeshPart(triangle(), "roof", False)
        assert MeshPart(triangle(), "roof") != MeshPart(triangle(), "vc")


# ── ports from the spike: one rule each, until L1.10 ──────────────────────────


class TestSpikeDriftGuards:
    def test_srgb_to_linear(self) -> None:
        from open_garden_planner.spike_q3d import meshes as spike

        for colour in ("#000000", "#ffffff", "#b4553d", "#487f34", "#0a0b0c", "#4d92c5"):
            np.testing.assert_array_equal(srgb_to_linear(colour), spike.srgb_to_linear(colour))
        with pytest.raises(ValueError):
            srgb_to_linear("b4553d")

    def test_item_seed(self) -> None:
        from open_garden_planner.spike_q3d import meshes as spike

        for item_id in ("11111111-2222-3333-4444-555555555555", "", "x"):
            for salt in ("", "leaves"):
                assert item_seed(item_id, salt) == spike.item_seed(item_id, salt)
        assert item_seed("a") != item_seed("b") and item_seed("a") != item_seed("a", "s")

    def test_normal_vs_winding(self) -> None:
        from open_garden_planner.spike_q3d import meshes as spike

        ours = prism_mesh((L_SHAPE,), 120.0)
        theirs = spike.prism(list(L_SHAPE), 120.0, 0.0, "#ffffff")
        dots, flat = normal_vs_winding(ours)
        spike_dots, spike_flat = spike.normal_vs_winding(theirs)
        np.testing.assert_array_equal(dots, spike_dots)
        np.testing.assert_array_equal(flat, spike_flat)
        np.testing.assert_array_equal(ours.positions, theirs.positions)
        np.testing.assert_array_equal(ours.normals, theirs.normals)


# ── the default builder (honest v0) ───────────────────────────────────────────


class TestDefaultBuilder:
    @pytest.mark.parametrize("height", [40.0, 0.1, 123.456789, 450.0, 1e-3, 33.3])
    def test_prism_top_is_exactly_the_height(self, height: float) -> None:
        (part,) = default_builder(record(height_cm=height))
        low, high = part.mesh.bounds()
        assert float(high[2]) == float(np.float32(height))  # exact, in the float32 the engine gets
        assert float(low[2]) == 0.0  # the item's own ground plane: base_cm is the transform's
        part.validate()

    def test_footprint_is_the_local_footprint(self) -> None:
        (part,) = default_builder(record(footprints=(L_SHAPE,)))
        low, high = part.mesh.bounds()
        assert low[:2].tolist() == [0.0, 0.0] and high[:2].tolist() == [100.0, 100.0]
        # 6 walls x 2 triangles + 4 cap triangles (n - 2 for a simple polygon)
        assert part.mesh.triangle_count == 16
        dots, flat = normal_vs_winding(part.mesh)
        assert flat.all() and dots.min() >= 0.99

    def test_clockwise_footprint_still_faces_out(self) -> None:
        (part,) = default_builder(record(footprints=(tuple(reversed(L_SHAPE)),)))
        part.validate()

    def test_part_is_neutral_and_tinted_by_the_sink(self) -> None:
        """A pure colour change must not rebuild geometry: the mesh carries no
        colour of the item, and the part asks the sink to tint it."""
        (part,) = default_builder(record())
        assert part.tinted is True and part.material_kind == "vc" and part.casts_shadow is True
        assert np.all(part.mesh.colors == 1.0)
        recoloured = record(material=Material("RAISED_BED", fill_rgba=(1, 2, 3, 255)))
        assert default_builder(recoloured) == (part,)

    def test_no_height_means_no_parts(self) -> None:
        """A lawn, a path, a rain barrel: the resolver gives no height, so there is
        no solid — the ground bake (L1.5) paints flat surfaces."""
        assert default_builder(record(height_cm=None)) == ()

    def test_several_rings_become_one_part(self) -> None:
        other = tuple((x + 300.0, y) for x, y in SQUARE)
        (part,) = default_builder(record(shape="polyline", footprints=(SQUARE, other),
                                         path=((-50.0, 0.0), (350.0, 0.0)), path_width_cm=100.0))
        assert part.mesh.triangle_count == 2 * (8 + 2)
        part.validate()

    def test_degenerate_footprints_give_no_parts(self) -> None:
        assert default_builder(record(footprints=())) == ()
        assert default_builder(record(footprints=(SQUARE[:2],))) == ()

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
