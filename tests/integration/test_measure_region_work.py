"""``scripts/measure_region_work.py``: the table FAILS above a stated ratio.

Phase 17 L1.1 (#385), fix round 5. The script prints what every family of
outlines costs against what it is charged — cost to price. Twice a step ran for
seconds inside the work budget because the clipper was asked in a way no row of
the table measured (a union as a tree, strict and then plain: 14 to 76 times
its price), and both times the script could only have printed that. It ends
with a verdict now: a row above ``MAX_COST_TO_PRICE`` is exit code 1.

The ratio is two timings, so the script itself is run by hand on a quiet
machine (the gate list of section 8.10) — never by the suite. What is tested
here is everything about it that is not a timing: the verdict, the bound, that
``main`` returns it, and that the families of the last two reviews are in the
table and are what their names say.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from open_garden_planner.ui.view3d import snapshot

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "measure_region_work.py"


@pytest.fixture(scope="module")
def script() -> Any:
    spec = importlib.util.spec_from_file_location("measure_region_work", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # not as ``__main__``: it isolates nothing and measures nothing
    return module


def test_a_table_within_the_bound_passes(script: Any, capsys: pytest.CaptureFixture[str]) -> None:
    assert script.gate([(0.4, "a refusal"), (1.7, "a wide path"), (8.1, "holes that touch")]) == 0
    out = capsys.readouterr().out
    assert "the worst cost to price of 3 rows: 8.10 (holes that touch); the bound is 12" in out
    assert "ABOVE" not in out and "FAILED" not in out


def test_a_row_above_the_bound_fails_the_table_and_is_named(script: Any, capsys: pytest.CaptureFixture[str]) -> None:
    rows = [(1.4, "a traced pond"), (34.2, "a slab with 720 bridged holes, its union as a tree"),
            (21.0, "a two-level zigzag, its strict union as a tree"), (script.MAX_COST_TO_PRICE, "exactly on it")]
    assert script.gate(rows) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith("the worst cost to price of 4 rows: 34.20 (a slab with 720 bridged holes")
    assert out[1:3] == ["    ABOVE THE BOUND: 34.20 — a slab with 720 bridged holes, its union as a tree",
                        "    ABOVE THE BOUND: 21.00 — a two-level zigzag, its strict union as a tree"]
    assert out[3].startswith("FAILED") and len(out) == 4  # the row ON the bound is not above it
    assert script.gate(rows, bound=40.0) == 0


def test_the_bound_is_the_stated_one_and_main_returns_the_verdict(script: Any) -> None:
    """12: above the dearest family measured (before #451 re-priced its bridge
    search, holes that touch their wall stood at 3.6 to 8.1; the dearest row is
    1.3 to 1.5 now) and below the smallest of the two defects it exists for (14)."""
    assert script.MAX_COST_TO_PRICE == 12.0
    (main,) = [node for node in ast.parse(SCRIPT.read_text(encoding="utf-8")).body
               if isinstance(node, ast.FunctionDef) and node.name == "main"]
    assert ast.unparse(main.body[-1]) == "return gate(RATIOS)"  # the full run ends with the verdict …
    quick = [node for node in ast.walk(main) if isinstance(node, ast.If) and ast.unparse(node.test) == "args.quick"]
    assert len(quick) == 1 and ast.unparse(quick[0].body[-1]) == "return 0"  # … "--quick" measures no ratio


def test_the_families_of_the_two_reviews_are_rows_of_the_table(script: Any) -> None:
    rows = {label: make for label, _unit, make, _low, _high in script.POLYGONS}
    for label in ("a two-level zigzag", "… turned 30 degrees", "a slab with holes bridged to its wall",
                  "… sheared (nothing level, nothing upright)", "a row of square holes bridged to the edge",
                  "a row of frames (diamonds with a bridged hole each)", "a slab whose holes touch its wall"):
        assert label in rows, label
    assert len(script.POLYGONS) == 10 and len(script.STROKES) == 10


@pytest.fixture
def fresh() -> Any:
    snapshot.clear_outline_cache()
    yield
    snapshot.clear_outline_cache()


def test_each_hole_family_is_what_its_name_says(script: Any, fresh: None) -> None:
    """Through the snapshot's own function, small: a family that silently became
    another outline would leave its row measuring nothing of the kind."""

    def shape(ring: Any) -> tuple[int, list[int]]:
        regions, resolved = snapshot._polygon_regions(tuple(ring))
        assert resolved and not isinstance(regions, snapshot._Refused)
        return len(regions), [len(holes) for _outer, holes in regions]

    assert len(script.bridged_holes(7)) == 4 + 6 * 7 and shape(script.bridged_holes(7)) == (1, [7])
    sheared = script.bridged_holes(7, 0.37)
    assert shape(sheared) == (1, [7])
    assert not any(a[0] == b[0] or a[1] == b[1] for a, b in zip(sheared, sheared[1:], strict=False))  # nothing level, nothing upright
    assert len(script.row_of_keyholes(7)) == 4 + 8 * 7 and shape(script.row_of_keyholes(7)) == (1, [7])
    assert shape(script.row_of_frames(7)) == (7, [1] * 7)
    assert len(script.touching_holes(7)) == 4 + 4 * 7 and shape(script.touching_holes(7)) == (1, [0])  # notches: by a band
