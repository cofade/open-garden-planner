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
    EMPTY_PARAMS,
    GEOMETRY_FIELDS,
    MATERIAL_FIELDS,
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

SQUARE = ((-50.0, -50.0), (50.0, -50.0), (50.0, 50.0), (-50.0, 50.0))


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


def _other(field: str) -> object:
    return {
        "kind": "CONTAINER",
        "shape": "polygon",
        "footprints": (SQUARE[:3],),
        "path": ((0.0, 0.0), (10.0, 0.0)),
        "path_width_cm": 12.0,
        "height_cm": 41.0,
        "params": Params({"seed": "a", "radius_cm": 3.0}),
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
STDLIB = set(sys.stdlib_module_names) | {"__future__"}


def _imports(path: Path) -> set[str]:
    """Every module a file imports, absolute — relative imports resolved against
    ``open_garden_planner.core.scene3d`` so a sibling ``core`` module is told apart
    from a parent package's ``ui``."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ["open_garden_planner", "core", "scene3d"]
            if node.level:
                parts = base[: len(base) - (node.level - 1)]
                module = ".".join(parts + ([node.module] if node.module else []))
            else:
                module = node.module or ""
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def test_package_modules_exist() -> None:
    assert {p.name for p in PACKAGE.glob("*.py")} == {
        "__init__.py", "legacy.py", "color.py", "record.py", "diff.py", "frame.py",
        "mesh.py", "sink.py", "build.py", "sync.py",
    }


@pytest.mark.parametrize("path", sorted(PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_package_is_qt_free(path: Path) -> None:
    """Epic #383 / ADR-048 NO-GO insurance: nothing under ``core/scene3d/`` imports
    PyQt6 — and nothing but the standard library, numpy and ``core`` siblings."""
    for name in _imports(path):
        top = name.split(".")[0]
        assert top != "PyQt6", f"{path.name} imports {name}"
        if top in STDLIB or top == "numpy":
            continue
        assert name.startswith("open_garden_planner.core"), f"{path.name} imports {name}"


def test_the_scan_resolves_relative_imports(tmp_path: Path) -> None:
    """The scan must not be blind to its own subject: a relative import of a
    parent package (``from ... import ui``) and a function-local PyQt6 import are
    both seen."""
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
    found = _imports(probe)
    assert "open_garden_planner.core.shadow_geometry" in found
    assert "open_garden_planner.ui" in found
    assert "open_garden_planner.core.scene3d.record" in found
    assert "PyQt6.QtCore" in found


def test_core_siblings_the_package_uses_are_qt_free() -> None:
    """The scan of the package cannot see a ``core`` sibling that imports Qt
    itself, so every sibling it uses is scanned too. The set is pinned: a new
    dependency of the Qt-free core is a decision, not an accident."""
    siblings: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        for name in _imports(path):
            parts = name.split(".")
            if parts[:2] == ["open_garden_planner", "core"] and len(parts) > 2 and parts[2] != "scene3d":
                siblings.add(parts[2])
    assert siblings == {"shadow_geometry", "solar"}
    for sibling in siblings:
        imported = _imports(PACKAGE.parent / f"{sibling}.py")
        assert not any(n.split(".")[0] == "PyQt6" for n in imported), sibling
