"""Golden gate for the 2D footprints (Phase 17 L1.1, #385, gate G3).

``item_footprints`` is the ONE answer to "which ground does this item cover" —
the shadow overlay, the hours-of-sun heatmap, the Qt 3D view and the Qt Quick 3D
pipeline all read it. L1.1 moves it out of ``sun_shadow_controller`` into the
public ``ui/canvas/footprints.py``; this file pins that the move (and every later
edit) changes no number.

The fixture ``tests/fixtures/footprints/footprints_golden.json`` was generated
from the code as it stood BEFORE the move (commit c23c6f0 + this test), with the
exact ``repr`` of every float: every footprint shape x four rotations (0, 17, 90,
213.5 degrees) x two positions, plus dated plants (the canopy grows with the
date). On the platform that generated it the comparison is string equality —
byte-identical. Elsewhere the same structure is required and the numbers may
differ by 1e-9 cm: ``math.cos`` / ``math.sin`` and Qt's rotation call the
platform's C library, which is not correctly rounded on every platform, so the
last bit of a vertex is not portable (measured: nothing here needs it to be).

Regenerating is a deliberate act (a footprint really changed): run

    OGP_WRITE_FOOTPRINT_GOLDEN=1 pytest tests/integration/test_footprints_golden.py

which rewrites the fixture and FAILS, so the run cannot be mistaken for a pass;
review the diff of the JSON, then commit it with the reason.

Rotations are applied with plain ``setTransformOriginPoint`` + ``setRotation``
about a pivot the case names, never through ``_apply_rotation``: for polygons
and polylines the app pivots on ``boundingRect().center()``, which depends on
pen width and painted decorations — this gate pins footprint extraction, not
the pivot rule (``tests/integration/test_rotation_aware_resize.py`` owns that).
Stroke widths are set explicitly for the same reason: a style-table tweak must
not look like a footprint regression.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from PyQt6.QtCore import QPointF, qVersion

from open_garden_planner.core.object_types import ObjectType
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
from open_garden_planner.ui.canvas.footprints import item_footprints, plant_canopy_radius_cm
from open_garden_planner.ui.canvas.items.circle_item import CircleItem
from open_garden_planner.ui.canvas.items.ellipse_item import EllipseItem
from open_garden_planner.ui.canvas.items.polygon_item import PolygonItem
from open_garden_planner.ui.canvas.items.polyline_item import PolylineItem
from open_garden_planner.ui.canvas.items.rectangle_item import RectangleItem

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "footprints" / "footprints_golden.json"
WRITE_ENV = "OGP_WRITE_FOOTPRINT_GOLDEN"

ROTATIONS: tuple[float, ...] = (0.0, 17.0, 90.0, 213.5)
POSITIONS: dict[str, tuple[float, float]] = {"origin": (0.0, 0.0), "moved": (137.25, -42.5)}
PLANT_ROTATIONS: tuple[float, ...] = (0.0, 213.5)
PLANT_DATES: tuple[date | None, ...] = (
    None,
    date(2026, 1, 1),  # the planting day
    date(2030, 6, 21),  # part-grown
    date(2045, 1, 1),  # mature
)

SPECIES = {
    "common_name": "Apple tree",
    "scientific_name": "Malus domestica",
    "min_height_cm": 100.0,
    "max_height_cm": 500.0,
    "min_spread_cm": 50.0,
    "max_spread_cm": 400.0,
}

Factory = Callable[[], tuple[Any, QPointF]]


def _with_stroke(item: Any, width: float) -> Any:
    pen = item.pen()
    pen.setWidthF(width)
    item.setPen(pen)
    return item


def _circle() -> tuple[Any, QPointF]:
    item = CircleItem(310.5, 220.25, 75.0, object_type=ObjectType.GENERIC_CIRCLE)
    return item, item.rect().center()


def _ellipse() -> tuple[Any, QPointF]:
    item = EllipseItem(120.5, 80.25, 260.0, 110.5, object_type=ObjectType.GENERIC_ELLIPSE)
    return item, item.rect().center()


def _rectangle() -> tuple[Any, QPointF]:
    item = RectangleItem(100.3, 50.7, 240.0, 130.5, object_type=ObjectType.GENERIC_RECTANGLE)
    return item, item.rect().center()


def _polygon() -> tuple[Any, QPointF]:
    # concave L, deliberately not centred on its pivot
    vertices = [QPointF(200.0, 100.0), QPointF(520.5, 100.0), QPointF(520.5, 260.25),
                QPointF(360.0, 260.25), QPointF(360.0, 410.0), QPointF(200.0, 410.0)]
    return PolygonItem(vertices, object_type=ObjectType.GENERIC_POLYGON), QPointF(350.0, 250.0)


def _polyline_straight() -> tuple[Any, QPointF]:
    item = PolylineItem([QPointF(50.0, 60.5), QPointF(950.25, 60.5)], object_type=ObjectType.FENCE)
    return _with_stroke(item, 12.0), QPointF(500.0, 60.5)


def _polyline_bent() -> tuple[Any, QPointF]:
    points = [QPointF(100.0, 100.0), QPointF(400.5, 130.25), QPointF(430.0, 380.0),
              QPointF(180.75, 300.0)]
    item = PolylineItem(points, object_type=ObjectType.WALL)
    return _with_stroke(item, 24.5), QPointF(280.0, 240.0)


def _polyline_crossing() -> tuple[Any, QPointF]:
    # the stroke crosses itself: the offset may come back as several rings
    points = [QPointF(100.0, 100.0), QPointF(400.0, 400.0), QPointF(400.0, 100.0),
              QPointF(100.0, 400.0)]
    item = PolylineItem(points, object_type=ObjectType.PATH)
    return _with_stroke(item, 30.0), QPointF(250.0, 250.0)


SHAPES: dict[str, Factory] = {
    "circle": _circle,
    "ellipse": _ellipse,
    "rectangle": _rectangle,
    "polygon": _polygon,
    "polyline_straight": _polyline_straight,
    "polyline_bent": _polyline_bent,
    "polyline_crossing": _polyline_crossing,
}


def _tree(metadata: dict[str, Any]) -> tuple[Any, QPointF]:
    item = CircleItem(640.0, 480.5, 100.0, object_type=ObjectType.TREE)
    item.metadata.update(metadata)
    return item, item.rect().center()


PLANTS: dict[str, Factory] = {
    # species + planting date + measured size: the canopy is projected to the date
    "tree_dated": lambda: _tree({
        "plant_species": dict(SPECIES),
        "plant_instance": {"planting_date": "2026-01-01", "current_height_cm": 100.0,
                           "current_spread_cm": 50.0},
    }),
    # species, never measured: growth disengages, the drawn circle is the canopy
    "tree_unmeasured": lambda: _tree({
        "plant_species": dict(SPECIES),
        "plant_instance": {"planting_date": "2026-01-01"},
    }),
    # a measured spread and no species (an unknown plant name is a supported state)
    "tree_spread_only": lambda: _tree({"plant_instance": {"current_spread_cm": 130.5}}),
    # no metadata at all: the drawn circle
    "tree_plain": lambda: _tree({}),
}


def _place(item: Any, pivot: QPointF, rotation: float, position: tuple[float, float]) -> None:
    item.setTransformOriginPoint(pivot)
    item.setRotation(rotation)
    item.setPos(position[0], position[1])


def _reprs(footprints: list[list[tuple[float, float]]]) -> list[list[list[str]]]:
    return [[[repr(x), repr(y)] for x, y in polygon] for polygon in footprints]


def compute_cases() -> dict[str, Any]:
    """Every golden case from the live code, floats as their exact ``repr``."""
    scene = CanvasScene(5000.0, 3000.0)
    footprints: dict[str, Any] = {}
    canopy: dict[str, str] = {}
    for shape, factory in SHAPES.items():
        for rotation in ROTATIONS:
            for pos_name, position in POSITIONS.items():
                item, pivot = factory()
                scene.addItem(item)
                _place(item, pivot, rotation, position)
                footprints[f"{shape}|rot={rotation}|pos={pos_name}"] = _reprs(item_footprints(item))
    for plant, factory in PLANTS.items():
        for at in PLANT_DATES:
            item, pivot = factory()
            canopy[f"{plant}|date={at}"] = repr(plant_canopy_radius_cm(item, at))
            for rotation in PLANT_ROTATIONS:
                for pos_name, position in POSITIONS.items():
                    item, pivot = factory()
                    scene.addItem(item)
                    _place(item, pivot, rotation, position)
                    key = f"{plant}|date={at}|rot={rotation}|pos={pos_name}"
                    footprints[key] = _reprs(item_footprints(item, at))
    return {"footprints": footprints, "canopy_radius_cm": canopy}


def _write_golden(cases: dict[str, Any]) -> None:
    payload = {
        "meta": {
            "generator": "tests/integration/test_footprints_golden.py",
            "platform": sys.platform,
            "machine": platform.machine(),
            "python": platform.python_version(),
            "qt": qVersion(),
            "floats": "exact repr() strings; compared as strings on meta.platform",
        },
        **cases,
    }
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _assert_close(actual: Any, expected: Any, where: str) -> None:
    """Same nesting and lengths; floats within 1e-9 cm (other platforms only)."""
    if isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected), where
        for index, (a, e) in enumerate(zip(actual, expected, strict=True)):
            _assert_close(a, e, f"{where}[{index}]")
        return
    if expected == "None" or actual == "None":
        assert actual == expected, where
        return
    assert abs(float(actual) - float(expected)) <= 1e-9, (where, actual, expected)


@pytest.fixture(scope="module")
def cases(qapp) -> dict[str, Any]:  # noqa: ARG001 — Qt must exist before items are built
    return compute_cases()


def test_golden_fixture_is_regenerated_only_on_purpose(cases) -> None:
    if os.environ.get(WRITE_ENV) != "1":
        pytest.skip(f"set {WRITE_ENV}=1 to rewrite the golden fixture")
    _write_golden(cases)
    pytest.fail(f"golden fixture rewritten at {GOLDEN} — review its diff and commit it deliberately")


def test_case_matrix_is_complete(cases, qtbot) -> None:
    """Every shape x rotation x position, plus the dated plants — nothing silently dropped."""
    shapes = len(SHAPES) * len(ROTATIONS) * len(POSITIONS)
    plants = len(PLANTS) * len(PLANT_DATES) * len(PLANT_ROTATIONS) * len(POSITIONS)
    assert len(cases["footprints"]) == shapes + plants == 120
    assert len(cases["canopy_radius_cm"]) == len(PLANTS) * len(PLANT_DATES) == 16
    # no case is empty: a shape that stopped producing a footprint would otherwise
    # compare equal to an (also empty) regenerated golden
    assert all(polygons and all(len(p) >= 3 for p in polygons)
               for polygons in cases["footprints"].values())
    # the dated plant really grows across the dates the matrix names
    dated = [float(cases["canopy_radius_cm"][f"tree_dated|date={at}"]) for at in PLANT_DATES[1:]]
    assert dated[0] < dated[1] < dated[2]


def test_footprints_match_the_golden(cases, qtbot) -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert set(cases["footprints"]) == set(golden["footprints"])
    assert set(cases["canopy_radius_cm"]) == set(golden["canopy_radius_cm"])
    if sys.platform == golden["meta"]["platform"]:
        # byte-identical: the exact repr of every float, as a string
        assert cases["canopy_radius_cm"] == golden["canopy_radius_cm"]
        differing = sorted(k for k, v in cases["footprints"].items() if v != golden["footprints"][k])
        assert differing == []
        return
    for key, expected in golden["canopy_radius_cm"].items():
        _assert_close(cases["canopy_radius_cm"][key], expected, key)
    for key, expected in golden["footprints"].items():
        _assert_close(cases["footprints"][key], expected, key)
