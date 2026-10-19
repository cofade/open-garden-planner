"""Scene contract v2 — records, signatures and the diff (Phase 17 L1.1, #385).

Qt-free: no ``qtbot``, no QApplication. The diff matrix on REAL canvas items is
``tests/integration/test_scene3d_snapshot.py``; this file pins the contract
itself: what each signature covers, that a signature is only an accelerator
(Python's ``hash`` collides on real edits), and every combination of the three.
"""

from __future__ import annotations

import ast
import dataclasses
import itertools
import sys
from pathlib import Path

import pytest

from open_garden_planner.core import scene3d
from open_garden_planner.core.scene3d import (
    DIMENSIONLESS_PARAMS,
    EMPTY_PARAMS,
    GEOMETRY_FIELDS,
    MATERIAL_FIELDS,
    MAX_LENGTH_CM,
    MIN_HEIGHT_CM,
    SHAPES,
    SIGNATURE_FIELDS,
    TRANSFORM_FIELDS,
    UNSIGNED_FIELDS,
    Material,
    Params,
    Record,
    SceneDiff,
    Transform,
    diff,
    quantize_cm,
    quantize_deg,
)
from open_garden_planner.core.scene3d.record import RecordRangeError

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))
HOLE = ((-10.0, -10.0), (-10.0, 10.0), (10.0, 10.0), (10.0, -10.0))  # clockwise


def record(item_id: str = "a", **changes: object) -> Record:
    base = Record(
        item_id=item_id,
        kind="RAISED_BED",
        shape="rectangle",
        footprints=(SQUARE,),
        transform=Transform(100.0, 200.0, 30.0),
        material=Material("RAISED_BED", fill_rgba=(120, 80, 40, 255), pattern="WOOD"),
        height_cm=40.0,
        params=Params({"seed": item_id}),
        name="Bed",
    )
    return dataclasses.replace(base, **changes) if changes else base


def scene(*records: Record) -> dict[str, Record]:
    return {r.item_id: r for r in records}


# ── quantisation ──────────────────────────────────────────────────────────────


class TestQuantisation:
    def test_lengths_snap_to_a_nanometre(self) -> None:
        assert quantize_cm(-150.00000000000003) == -150.0
        assert quantize_cm(12.34567894) == 12.3456789
        assert quantize_cm(12.34567896) == 12.345679

    def test_an_edit_of_one_quantum_survives(self) -> None:
        """The resolution cannot hide a real edit: 1e-7 cm is one nanometre, below
        the float32 resolution of every vertex further than ~1 cm from its origin."""
        assert quantize_cm(1.0) != quantize_cm(1.0 + 1e-7)

    def test_negative_zero_is_normalised(self) -> None:
        assert repr(quantize_cm(-1e-12)) == "0.0"
        assert repr(quantize_deg(-1e-12)) == "0.0"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(17.000000000000004, 17.0), (-146.5, 213.5), (360.0, 0.0), (359.9999999999, 0.0),
         (-90.0, 270.0), (720.5, 0.5), (180.0, 180.0)],
    )
    def test_angles_are_normalised_to_one_turn(self, raw: float, expected: float) -> None:
        assert quantize_deg(raw) == expected
        assert 0.0 <= quantize_deg(raw) < 360.0


# ── Transform / Material / Params ─────────────────────────────────────────────


class TestTransform:
    def test_defaults_are_the_identity(self) -> None:
        assert Transform() == Transform(0.0, 0.0, 0.0, 0.0)

    @pytest.mark.parametrize("field", ["east_cm", "north_cm", "rotation_deg", "base_cm"])
    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_a_non_finite_value_is_refused(self, field: str, bad: float) -> None:
        """NaN != NaN: one non-finite transform would report a change on every diff."""
        with pytest.raises(ValueError, match=field):
            Transform(**{field: bad})

    def test_with_base_changes_only_the_base(self) -> None:
        t = Transform(1.0, 2.0, 3.0)
        assert t.with_base(38.0) == Transform(1.0, 2.0, 3.0, 38.0)


class TestMaterial:
    def test_tint_prefers_fill_then_stroke_then_the_fallback(self) -> None:
        assert Material("X", fill_rgba=(1, 2, 3, 40), stroke_rgba=(9, 9, 9, 255)).tint_rgba == (1, 2, 3, 255)
        assert Material("FENCE", stroke_rgba=(9, 8, 7, 200)).tint_rgba == (9, 8, 7, 255)
        assert Material("X").tint_rgba == scene3d.FALLBACK_RGBA == (158, 158, 148, 255)

    def test_tint_linear_is_the_srgb_decode(self) -> None:
        r, g, b, a = Material("X", fill_rgba=(255, 0, 188, 255)).tint_linear()
        assert (r, g, a) == (1.0, 0.0, 1.0)
        assert b == pytest.approx(((188 / 255 + 0.055) / 1.055) ** 2.4, abs=1e-12)
        assert 0.50 < b < 0.51  # mid sRGB is ~half the light, not 188/255 = 0.74

    @pytest.mark.parametrize("bad", [(1, 2, 3), (1, 2, 3, 256), (-1, 0, 0, 0), (1.0, 2, 3, 4)])
    def test_a_malformed_colour_is_refused(self, bad: tuple) -> None:
        with pytest.raises(ValueError, match="fill_rgba"):
            Material("X", fill_rgba=bad)  # type: ignore[arg-type]


class TestParams:
    def test_is_a_sorted_immutable_hashable_mapping(self) -> None:
        params = Params({"seed": "abc", "radius_cm": 12.5, "ridge": ((1.0, 2.0), (3.0, 4.0))})
        assert list(params) == ["radius_cm", "ridge", "seed"]
        assert params["radius_cm"] == 12.5
        assert params.get("missing") is None
        assert len(params) == 3 and "seed" in params
        assert dict(params) == {"seed": "abc", "radius_cm": 12.5, "ridge": ((1.0, 2.0), (3.0, 4.0))}
        with pytest.raises(KeyError):
            params["missing"]
        with pytest.raises(AttributeError):
            params.x = 1  # type: ignore[attr-defined]
        with pytest.raises(TypeError):
            params["seed"] = "z"  # type: ignore[index]

    def test_order_of_construction_does_not_matter(self) -> None:
        a = Params({"a": 1, "b": 2})
        b = Params([("b", 2), ("a", 1)])
        assert a == b and hash(a) == hash(b)
        assert a != Params({"a": 1, "b": 3})
        assert Params() == EMPTY_PARAMS and len(EMPTY_PARAMS) == 0

    @pytest.mark.parametrize(
        "bad", [[1, 2], {"k": 1}, {1, 2}, object(), float("nan"), float("inf"), (1, [2])]
    )
    def test_only_plain_immutable_finite_values(self, bad: object) -> None:
        with pytest.raises((TypeError, ValueError)):
            Params({"k": bad})  # type: ignore[dict-item]

    def test_keys_are_strings(self) -> None:
        with pytest.raises(TypeError):
            Params({1: "x"})  # type: ignore[dict-item]

    def test_merged_returns_a_new_mapping(self) -> None:
        base = Params({"a": 1})
        assert base.merged({"b": 2}) == Params({"a": 1, "b": 2})
        assert base == Params({"a": 1})


# ── Record + signatures ───────────────────────────────────────────────────────


class TestRecord:
    def test_every_field_belongs_to_exactly_one_group(self) -> None:
        """Drift guard: a field added to Record must be put into a signature or be
        declared unsigned — it can never silently be in none."""
        names = {f.name for f in dataclasses.fields(Record)}
        groups = [GEOMETRY_FIELDS, TRANSFORM_FIELDS, MATERIAL_FIELDS, UNSIGNED_FIELDS,
                  SIGNATURE_FIELDS]
        assert set().union(*groups) == names
        assert sum(len(g) for g in groups) == len(names)  # disjoint
        assert UNSIGNED_FIELDS == ("item_id", "name", "parent_id")
        assert SIGNATURE_FIELDS == ("geometry_sig", "transform_sig", "material_sig")

    def test_selection_and_hover_are_not_in_the_record_at_all(self) -> None:
        names = {f.name for f in dataclasses.fields(Record)}
        assert not {n for n in names if "select" in n or "hover" in n}

    @pytest.mark.parametrize("field", GEOMETRY_FIELDS)
    def test_each_geometry_field_moves_only_the_geometry_signature(self, field: str) -> None:
        base = record()
        changed = record(**{field: _other(field)})
        assert changed.geometry_sig != base.geometry_sig
        assert changed.transform_sig == base.transform_sig
        assert changed.material_sig == base.material_sig
        assert not base.same_geometry(changed)
        assert base.same_transform(changed) and base.same_material(changed)

    def test_transform_moves_only_the_transform_signature(self) -> None:
        base = record()
        for t in (Transform(101.0, 200.0, 30.0), Transform(100.0, 200.0, 31.0),
                  Transform(100.0, 200.0, 30.0, 5.0)):
            changed = record(transform=t)
            assert changed.transform_sig != base.transform_sig
            assert changed.geometry_sig == base.geometry_sig
            assert changed.material_sig == base.material_sig

    def test_material_moves_only_the_material_signature(self) -> None:
        base = record()
        for m in (Material("RAISED_BED", fill_rgba=(1, 2, 3, 255), pattern="WOOD"),
                  Material("RAISED_BED", fill_rgba=(120, 80, 40, 255), pattern="SOIL"),
                  Material("RAISED_BED", fill_rgba=(120, 80, 40, 255), pattern="WOOD",
                           stroke_rgba=(0, 0, 0, 255)),
                  Material("OTHER", fill_rgba=(120, 80, 40, 255), pattern="WOOD")):
            changed = record(material=m)
            assert changed.material_sig != base.material_sig
            assert changed.geometry_sig == base.geometry_sig
            assert changed.transform_sig == base.transform_sig

    @pytest.mark.parametrize("field", ["name", "parent_id"])
    def test_unsigned_fields_move_no_signature(self, field: str) -> None:
        base = record()
        changed = record(**{field: "something else"})
        assert changed != base  # the records differ …
        assert (changed.geometry_sig, changed.transform_sig, changed.material_sig) == (
            base.geometry_sig, base.transform_sig, base.material_sig)  # … no signature does

    def test_equal_records_have_equal_signatures(self) -> None:
        a, b = record(), record()
        assert a == b and a is not b
        assert (a.geometry_sig, a.transform_sig, a.material_sig) == (
            b.geometry_sig, b.transform_sig, b.material_sig)

    def test_an_unknown_shape_is_refused(self) -> None:
        with pytest.raises(ValueError, match="shape"):
            record(shape="blob")
        assert set(SHAPES) == {"circle", "ellipse", "rectangle", "polygon", "polyline"}

    @pytest.mark.parametrize("bad", [0.0, -1.0, float("inf"), float("nan")])
    def test_a_height_is_positive_and_finite_or_absent(self, bad: float) -> None:
        """An infinite or zero height would reach the engine as a non-finite or
        empty mesh; "no height" has one spelling, None."""
        with pytest.raises(ValueError, match="height"):
            record(height_cm=bad)
        assert hash(1.0) == hash(2.0**61) == hash(2.0**-61)  # what the collision test below uses

    # ── fix round 2: no length beyond what a plan can hold ───────────────────

    def test_the_bound_is_ten_kilometres(self) -> None:
        import numpy as np

        assert MAX_LENGTH_CM == 1e6
        assert issubclass(RecordRangeError, ValueError)
        # far inside float32, and still resolving a millimetre there
        assert float(np.float32(MAX_LENGTH_CM)) == MAX_LENGTH_CM
        assert float(np.spacing(np.float32(MAX_LENGTH_CM))) == 0.0625

    @pytest.mark.parametrize("height", [1e300, 1.0000001e6, 3.5e38, float("inf")],
                             ids=["1e300", "just over the bound", "beyond float32", "infinite"])
    def test_a_height_beyond_the_bound_is_refused(self, height: float) -> None:
        """The re-review's case. ``1e300`` is positive and finite — and in the
        mesh's float32 it is infinity. The record decides it once, for every
        builder: such a height is not a height a plan can hold."""
        with pytest.raises(RecordRangeError, match="a height of .* beyond what a plan can hold"):
            record(height_cm=height)
        assert record(height_cm=MAX_LENGTH_CM).height_cm == MAX_LENGTH_CM  # the bound itself is in

    @pytest.mark.parametrize(
        ("label", "changes"),
        [("a footprint coordinate", {"footprints": (((0.0, 0.0), (2e6, 0.0), (2e6, 5.0)),)}),
         ("a footprint coordinate, negative", {"footprints": (((-1e300, 0.0), (5.0, 0.0), (5.0, 5.0)),)}),
         ("a hole coordinate", {"footprints": (((-9.0, -9.0), (9.0, -9.0), (9.0, 9.0), (-9.0, 9.0)),),
                                "holes": ((((-1.0, -1.0), (-1.0, 2e6), (1.0, 1.0)),),)}),
         ("a centre line", {"path": ((0.0, 0.0), (0.0, -1.5e6))}),
         ("a stroke width", {"path_width_cm": 1e300}),
         ("a radius", {"params": lambda: Params({"radius_cm": 1e7})}),
         ("a ridge", {"params": lambda: Params({"ridge": ((0.0, 0.0), (1e300, 0.0))})}),
         ("a position east", {"transform": lambda: Transform(1e300, 0.0)}),
         ("a position north", {"transform": lambda: Transform(0.0, -2e6)}),
         ("a base", {"transform": lambda: Transform(0.0, 0.0, 0.0, 1e9)})],
    )
    def test_every_length_of_a_record_is_bounded(self, label: str, changes: dict) -> None:
        with pytest.raises(RecordRangeError, match="beyond what a plan can hold"):
            record(**{key: value() if callable(value) else value for key, value in changes.items()})

    # ── fix round 3: a height has a floor; which float params are lengths ────

    @pytest.mark.parametrize("height", [1e-300, 1e-46, 1e-45, 9.99e-4],
                             ids=["1e-300", "zero in float32", "the smallest float32", "just under the floor"])
    def test_a_height_below_the_floor_is_refused(self, height: float) -> None:
        """Review round 3, P2-8: the range rule covered overflow only. ``1e-46`` is
        positive and finite — and ZERO in the mesh's float32: a solid without a
        height, its walls triangles without an area, that passes ``validate``."""
        with pytest.raises(RecordRangeError, match="a height of .* is below what a solid can have"):
            record(height_cm=height)
        assert MIN_HEIGHT_CM == 1e-3
        assert record(height_cm=MIN_HEIGHT_CM).height_cm == MIN_HEIGHT_CM  # the floor itself is in

    def test_a_float_param_is_a_length_unless_it_is_named_otherwise(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Review round 3, P2-7. Every float in ``Params`` is held to the bound —
        right for the two there are, and a surprise for a later one that is a
        ratio or a count of days. The rule is stated where it is applied, the
        refusal names the way out, and the way out is one line."""
        from open_garden_planner.core.scene3d import record as record_module

        assert frozenset() == DIMENSIONLESS_PARAMS  # nothing is exempt today
        with pytest.raises(RecordRangeError, match="taken for a length in cm unless its key is "
                                                   "listed in record.DIMENSIONLESS_PARAMS"):
            Params({"days_since_epoch": 2e7})
        monkeypatch.setattr(record_module, "DIMENSIONLESS_PARAMS", frozenset({"days_since_epoch"}))
        assert Params({"days_since_epoch": 2e7, "radius_cm": 30.0})["days_since_epoch"] == 2e7
        with pytest.raises(RecordRangeError, match="radius_cm"):
            Params({"days_since_epoch": 2e7, "radius_cm": 2e7})  # … the others are lengths still
        with pytest.raises(ValueError, match="non-finite"):
            Params({"days_since_epoch": float("inf")})  # exempt from the bound, not from being a number
        assert "A FLOAT is taken for a length" in (Params.__doc__ or "")

    def test_what_is_not_a_length_is_not_bounded(self) -> None:
        """An angle wraps, a string is a string, an int is not a length: only
        floats that become geometry are held to the bound."""
        assert Transform(0.0, 0.0, 1e9).rotation_deg == 1e9
        assert Params({"seed": "x" * 100, "count": 10**12, "flag": True})["count"] == 10**12
        assert record(transform=Transform(MAX_LENGTH_CM, -MAX_LENGTH_CM)).transform.east_cm == 1e6

    def test_footprints_are_outer_rings_counter_clockwise(self) -> None:
        """Fix round 1: ``footprints`` holds OUTER rings only, and says so by
        orientation. A clockwise ring is a hole — refused here, so it can never
        again be extruded as a solid."""
        with pytest.raises(ValueError, match="OUTER rings.*-10000"):
            record(footprints=(SQUARE[::-1],))
        with pytest.raises(ValueError, match="OUTER rings"):
            record(footprints=(SQUARE, HOLE))  # the pre-fix shape of a closed fence
        with pytest.raises(ValueError, match="positive area"):
            record(footprints=(SQUARE[:2],))  # no area
        with pytest.raises(ValueError, match="positive area"):
            record(footprints=(((0.0, 0.0), (5.0, 0.0), (9.0, 0.0)),))
        assert record(footprints=()).plan_area_cm2 == 0.0  # no footprint is not an error

    def test_holes_belong_to_their_outer_ring_and_turn_clockwise(self) -> None:
        holed = record(holes=((HOLE,),))
        assert holed.regions == ((SQUARE, (HOLE,)),)
        assert holed.plan_area_cm2 == 10000.0 - 400.0
        assert record().regions == ((SQUARE, ()),) and record().plan_area_cm2 == 10000.0
        with pytest.raises(ValueError, match="clockwise"):
            record(holes=((HOLE[::-1],),))  # counter-clockwise: that is an outer ring
        with pytest.raises(ValueError, match="2 entries for 1 footprints"):
            record(holes=((HOLE,), ()))
        two = record(footprints=(SQUARE, tuple((x + 200.0, y) for x, y in SQUARE)),
                     holes=((), (tuple((x + 200.0, y) for x, y in HOLE),)))
        assert [len(h) for _outer, h in two.regions] == [0, 1]

    def test_no_holes_has_one_spelling(self) -> None:
        """``holes=((),)`` and ``holes=()`` say the same; they must be one record,
        or an unchanged item would diff as a geometry change."""
        spelled_out = record(holes=((),))
        assert spelled_out.holes == () and spelled_out == record()
        assert spelled_out.same_geometry(record())

    def test_a_hole_is_geometry(self) -> None:
        plain, holed = record(), record(holes=((HOLE,),))
        assert not plain.same_geometry(holed)
        assert plain.same_transform(holed) and plain.same_material(holed)
        assert diff(scene(plain), scene(holed)) == SceneDiff(geometry=("a",))

    def test_a_record_without_a_height_is_decoration(self) -> None:
        assert record().casts_shadow is True
        assert record(height_cm=None).casts_shadow is False
        assert record().base_cm == 0.0
        assert record(transform=Transform(0.0, 0.0, 0.0, 38.0)).base_cm == 38.0

    def test_a_signature_is_only_an_accelerator(self) -> None:
        """``hash(-1.0) == hash(-2.0)`` in CPython, so a vertex moved from -1 cm to
        -2 cm has the SAME tuple hash. ``same_geometry`` (and therefore ``diff``)
        compares the values too, or that edit would never reach the engine."""
        a = record(footprints=(((-1.0, 3.0), (5.0, 3.0), (5.0, 9.0)),))
        b = record(footprints=(((-2.0, 3.0), (5.0, 3.0), (5.0, 9.0)),))
        assert a.geometry_sig == b.geometry_sig  # the collision, measured
        assert not a.same_geometry(b)
        assert diff(scene(a), scene(b)).geometry == ("a",)

    @pytest.mark.parametrize(
        ("field", "one", "other"),
        [("footprints", (((-1.0, 3.0), (5.0, 3.0), (5.0, 9.0)),), (((-2.0, 3.0), (5.0, 3.0), (5.0, 9.0)),)),
         ("holes", ((((-1.0, -10.0), (-10.0, 10.0), (10.0, 10.0), (10.0, -10.0)),),),
          ((((-2.0, -10.0), (-10.0, 10.0), (10.0, 10.0), (10.0, -10.0)),),)),
         ("path", ((-1.0, 0.0), (10.0, 0.0)), ((-2.0, 0.0), (10.0, 0.0))),
         ("path_width_cm", 1.0, 2.0**-61),
         ("height_cm", 2.0**-9 + 2.0**-42, 2.0**19 + 2.0**-9),
         ("params", Params({"seed": "a", "radius_cm": -1.0}), Params({"seed": "a", "radius_cm": -2.0}))],
        ids=["footprints", "holes", "path", "path_width_cm", "height_cm", "params"],
    )
    def test_every_geometry_value_is_compared_not_only_hashed(self, field, one, other) -> None:
        """The same collision in each field that holds numbers. Two floats collide
        when they are equal modulo 2**61 - 1 — ``-1.0`` and ``-2.0`` by CPython's
        special case for the hash -1, ``1.0`` and ``2.0**-61`` by the modulus (as
        ``1.0`` and ``2.0**61`` are; that one is beyond what a record may hold) —
        and a field that was hashed but not compared would lose exactly those edits.
        A height has a floor as well as a ceiling; its pair differs by
        ``(2**61 - 1) / 2**42``: 0.00195 cm and 5,243 m.
        (``kind`` and ``shape`` are strings: no collision can be written down.)"""
        a, b = record(**{field: one}), record(**{field: other})
        assert one != other
        assert a.geometry_sig == b.geometry_sig, "the pair no longer collides: pick another"
        assert not a.same_geometry(b)
        assert diff(scene(a), scene(b)) == SceneDiff(geometry=("a",))

    def test_a_transform_and_a_material_are_compared_too(self) -> None:
        """One rule for all three signatures: the signature first, the values second.
        An item moved from 1 cm west of the origin to 2 cm west of it has the same
        ``transform_sig`` — a hash-only comparison would leave it where it was. A
        material's 8-bit channels cannot be made to collide by hand, so a material
        whose hash says nothing stands in for the collision."""
        here, there = record(transform=Transform(-1.0, 5.0)), record(transform=Transform(-2.0, 5.0))
        assert here.transform_sig == there.transform_sig  # the collision, measured
        assert not here.same_transform(there)
        assert diff(scene(here), scene(there)) == SceneDiff(transform=("a",))
        tall, taller = (record(transform=Transform(0.0, 0.0, 0.0, base)) for base in (-1.0, -2.0))
        assert tall.transform_sig == taller.transform_sig and not tall.same_transform(taller)

        class Collides(Material):
            """A material whose hash says nothing — what a collision looks like."""

            __slots__ = ()

            def __hash__(self) -> int:
                return 1

        red, blue = Collides("X", (255, 0, 0, 255)), Collides("X", (0, 0, 255, 255))
        a, b = record(material=red), record(material=blue)
        assert a.material_sig == b.material_sig and not a.same_material(b)
        assert diff(scene(a), scene(b)) == SceneDiff(material=("a",))


def _other(field: str) -> object:
    return {
        "kind": "CONTAINER",
        "shape": "polygon",
        "footprints": (SQUARE[:3],),
        "path": ((0.0, 0.0), (10.0, 0.0)),
        "path_width_cm": 12.0,
        "height_cm": 41.0,
        "params": Params({"seed": "a", "radius_cm": 3.0}),
        "holes": ((HOLE,),),
    }[field]


# ── diff ──────────────────────────────────────────────────────────────────────

_CHANGES: dict[str, dict[str, object]] = {
    "geometry": {"height_cm": 99.0},
    "transform": {"transform": Transform(1.0, 2.0, 3.0)},
    "material": {"material": Material("RAISED_BED", fill_rgba=(0, 0, 0, 255))},
}


class TestDiff:
    def test_identical_scenes_give_an_empty_diff(self) -> None:
        old = scene(record("a"), record("b"))
        result = diff(old, scene(record("a"), record("b")))
        assert result == SceneDiff() and result.is_empty and not result.touches_sink
        assert diff(old, old).is_empty

    @pytest.mark.parametrize(
        "combo", [c for n in range(4) for c in itertools.combinations(_CHANGES, n)]
    )
    def test_every_combination_of_the_three_signatures(self, combo: tuple[str, ...]) -> None:
        """Three INDEPENDENT comparisons: an item is listed under each aspect that
        changed and under no other — all eight combinations."""
        changes: dict[str, object] = {}
        for aspect in combo:
            changes.update(_CHANGES[aspect])
        result = diff(scene(record("a"), record("b")), scene(record("a", **changes), record("b")))
        assert result.geometry == (("a",) if "geometry" in combo else ())
        assert result.transform == (("a",) if "transform" in combo else ())
        assert result.material == (("a",) if "material" in combo else ())
        assert result.added == () and result.removed == ()
        assert result.is_empty is (combo == ())

    def test_added_and_removed_keep_paint_order(self) -> None:
        old = scene(record("a"), record("b"), record("c"))
        new = scene(record("x"), record("b"), record("y"))
        result = diff(old, new)
        assert result.added == ("x", "y")  # the new snapshot's order, bottom to top
        assert result.removed == ("a", "c")  # the old snapshot's order
        assert result.geometry == result.transform == result.material == ()

    def test_an_added_item_is_never_also_a_change(self) -> None:
        result = diff({}, scene(record("a")))
        assert result == SceneDiff(added=("a",))
        assert diff(scene(record("a")), {}) == SceneDiff(removed=("a",))

    def test_a_pure_reorder_is_never_a_geometry_change(self) -> None:
        old = scene(record("a"), record("b"), record("c"))
        new = scene(record("c"), record("a"), record("b"))
        result = diff(old, new)
        assert result.geometry == result.transform == result.material == ()
        assert result.added == result.removed == ()
        assert result.reordered is True
        assert not result.touches_sink  # nothing to tell the engine: depth sorts solids
        assert not result.is_empty  # … but the ground bake paints in this order

    def test_adding_or_removing_alone_is_not_a_reorder(self) -> None:
        old = scene(record("a"), record("b"))
        assert diff(old, scene(record("a"), record("n"), record("b"))).reordered is False
        assert diff(old, scene(record("b"))).reordered is False

    def test_a_rename_gives_an_empty_diff(self) -> None:
        assert diff(scene(record("a")), scene(record("a", name="Renamed"))).is_empty

    def test_changed_ids_lists_each_item_once_in_paint_order(self) -> None:
        old = scene(record("a"), record("b"), record("c"))
        new = scene(record("a", height_cm=1.0, transform=Transform(9.0, 9.0)),
                    record("b"), record("c", material=Material("X")))
        assert diff(old, new).changed == ("a", "c")


# ── the Qt-free rule (gate G6) ────────────────────────────────────────────────

PACKAGE = Path(scene3d.__file__).parent
CORE = PACKAGE.parent
SRC = CORE.parents[1]
STDLIB = set(sys.stdlib_module_names) | {"__future__"}
MODULES = sorted(PACKAGE.rglob("*.py"))  # sub-packages too: later stories add builders


def _package_of(path: Path) -> list[str]:
    """The package a source file belongs to, as dotted-name parts."""
    return list(path.relative_to(SRC).parent.parts)


def _imports(path: Path, package: list[str] | None = None) -> set[str]:
    """Every module a file imports, absolute — relative imports are resolved
    against the file's own package, so a ``core`` sibling (``from ..solar import``)
    is told apart from another top-level package (``from ...ui import``)."""
    base = package if package is not None else _package_of(path)
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = base[: len(base) - (node.level - 1)]
                module = ".".join(parts + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def _core_module_file(name: str) -> Path | None:
    """The source file of ``open_garden_planner.core.<...>``, or None when the
    dotted name is not a module (an imported function or class)."""
    parts = name.split(".")
    if parts[:2] != ["open_garden_planner", "core"] or len(parts) < 3:
        return None
    stem = SRC.joinpath(*parts)
    for candidate in (stem.with_suffix(".py"), stem / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def test_the_scan_covers_the_whole_package() -> None:
    assert {p.name for p in MODULES} >= {
        "__init__.py", "color.py", "record.py", "scene_diff.py", "frame.py",
        "polygon.py", "mesh.py", "sink.py", "build.py", "sync.py",
    }
    # fix round 1: the module is `scene_diff`; `core.scene3d.diff` is only the function
    assert not (PACKAGE / "diff.py").exists()
    # L1.10: the pre-L1.1 module left with the Qt 3D view
    assert not (PACKAGE / "legacy.py").exists()
    assert _package_of(PACKAGE / "record.py") == ["open_garden_planner", "core", "scene3d"]


@pytest.mark.parametrize("path", MODULES, ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_package_is_qt_free(path: Path) -> None:
    """Epic #383 / ADR-048 NO-GO insurance: nothing under ``core/scene3d/`` imports
    PyQt6 — and nothing but the standard library, numpy and ``core`` modules."""
    for name in _imports(path):
        top = name.split(".")[0]
        assert top != "PyQt6", f"{path.name} imports {name}"
        if top in STDLIB or top == "numpy":
            continue
        assert name.startswith("open_garden_planner.core"), f"{path.name} imports {name}"


def test_the_scan_resolves_relative_imports(tmp_path: Path) -> None:
    """The scan must not be blind to its own subject: a relative import of a
    parent package (``from ...ui import``) and a function-local PyQt6 import are
    both seen, and a sub-package resolves one level deeper."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "\n".join([
            "from ..shadow_geometry import Polygon",
            "from ...ui import canvas",
            "from . import record",
            "def f():",
            "    from PyQt6 import QtCore",
            "",
        ]),
        encoding="utf-8",
    )
    found = _imports(probe, ["open_garden_planner", "core", "scene3d"])
    assert "open_garden_planner.core.shadow_geometry" in found
    assert "open_garden_planner.ui" in found
    assert "open_garden_planner.core.scene3d.record" in found
    assert "PyQt6.QtCore" in found
    nested = _imports(probe, ["open_garden_planner", "core", "scene3d", "builders"])
    assert "open_garden_planner.core.scene3d.shadow_geometry" in nested
    assert "open_garden_planner.core.ui" in nested


def test_core_modules_the_package_reaches_are_qt_free() -> None:
    """The scan of the package cannot see a ``core`` sibling that imports Qt
    itself, so every ``core`` module the package reaches — directly or through
    another — is scanned too. A later story may add a sibling; it cannot add one
    that drags Qt in (``core.object_types`` does, for its translated labels)."""
    seen: dict[Path, set[str]] = {}
    queue = list(MODULES)
    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen[path] = _imports(path)
        for name in seen[path]:
            target = _core_module_file(name)
            if target is not None and target not in seen:
                queue.append(target)
    offenders = sorted(
        f"{path.relative_to(SRC).as_posix()} imports {name}"
        for path, names in seen.items() for name in names if name.split(".")[0] == "PyQt6"
    )
    assert offenders == []
    siblings = {path.stem for path in seen if path.parent == CORE}
    assert {"shadow_geometry", "solar"} <= siblings  # the walk left the package: not vacuous
    # ... and it does tell a Qt-importing core module apart
    assert any(n.split(".")[0] == "PyQt6" for n in _imports(CORE / "object_types.py"))


def test_diff_is_the_function_and_the_module_has_its_own_name() -> None:
    """``core.scene3d.diff`` used to be both a function and a module of that name
    (the function shadowed the module on the package). The module is
    ``scene_diff`` now; importing ``diff`` and ``SceneDiff`` from the package —
    what every consumer does — is unchanged."""
    import importlib

    from open_garden_planner.core.scene3d import SceneDiff as from_package
    from open_garden_planner.core.scene3d import diff as function

    module = importlib.import_module("open_garden_planner.core.scene3d.scene_diff")
    assert callable(function) and function is module.diff and scene3d.diff is module.diff
    assert from_package is module.SceneDiff
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("open_garden_planner.core.scene3d.diff")
