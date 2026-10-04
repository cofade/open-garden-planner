"""Generate the committed 3D benchmark / showcase plans (Phase 17, Package L0).

Two plans, both written through the real ``ProjectManager`` serializer so they
are production ``.ogp`` files, not hand-rolled JSON:

* ``bench_small.ogp`` — a 24 x 16 m family garden (99 items, 61 plants) with every object
  class the 3D pipeline must render: a HOUSE with its auto-created roof ridge,
  shed, greenhouse, pergola, trellis, raised beds and containers with planted
  children (``parent_bed_id``), an in-ground bed, lawn, gravel and
  stepping-stone paths, terrace, pond, trees, shrubs, perennials, vegetables,
  fence, hedge, wall and furniture. It is the beauty-board scene.
* ``bench_large.ogp`` — a 50 x 30 m allotment-style plan with 425 items
  (320 plants) for the performance budgets.

Both are deterministic: positions come from a seeded ``random.Random`` and item
ids are drawn from the same RNG (assigned exactly like ``core/project.py``'s
loader does), so per-plant seeds — and therefore procedural plant shapes —
stay stable across regenerations.

Usage::

    venv/bin/python scripts/make_bench_plans.py           # (re)write fixtures
    venv/bin/python scripts/make_bench_plans.py --check   # verify fixtures are current

The fixtures pin the serializer AND the bundled species data byte for byte
(``tests/integration/test_bench_plans.py``): a change to either — e.g. new
species fields — is regenerated with the first command, never hand-edited.

Saving and loading through ``ProjectManager`` records Recent Files, so this
script points every settings store at a throwaway key first (the same
redirection ``tests/conftest.py`` performs) — it must never touch the user's
own settings.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import uuid
from datetime import date
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

# Before any module that could build a settings store is imported (a QSettings
# binds its organization/application at construction) — see the docstring.
import open_garden_planner.app.settings as _app_settings  # noqa: E402

_app_settings.ORGANIZATION_NAME = "cofade-ogp-tooling"
_app_settings.APPLICATION_NAME = "Open Garden Planner bench generator"

from PyQt6.QtCore import QPointF  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from open_garden_planner.core import ProjectManager  # noqa: E402
from open_garden_planner.core.object_height import METADATA_KEY  # noqa: E402
from open_garden_planner.core.object_types import ObjectType, PathFenceStyle  # noqa: E402
from open_garden_planner.core.roof_ridge import compute_roof_ridge_endpoints  # noqa: E402
from open_garden_planner.services.bundled_species_db import (  # noqa: E402
    populate_item_species_metadata,
)
from open_garden_planner.ui.canvas.canvas_scene import CanvasScene  # noqa: E402
from open_garden_planner.ui.canvas.items import (  # noqa: E402
    CircleItem,
    PolygonItem,
    PolylineItem,
    RectangleItem,
)

OUT_DIR = REPO / "tests" / "fixtures" / "plans"
BERLIN = {"latitude": 52.52, "longitude": 13.405}
# A fixed planting date keeps the growth model deterministic for any sim date.
PLANTED = date(2026, 4, 15).isoformat()


class PlanBuilder:
    """Adds items to a CanvasScene with deterministic ids and positions."""

    def __init__(self, width_cm: float, height_cm: float, seed: str) -> None:
        self.scene = CanvasScene(width_cm, height_cm)
        self.rng = random.Random(seed)
        self.count = 0
        # Default layers get uuid4 ids at construction; pin them so the file is
        # byte-stable across regenerations (items reference layers by id).
        for layer in self.scene.layers:
            layer.id = uuid.UUID(int=self.rng.getrandbits(128), version=4)

    # -- plumbing ---------------------------------------------------------
    def _add(self, item: Any) -> Any:
        # Same assignment core/project.py's loader performs for saved ids.
        item._item_id = uuid.UUID(int=self.rng.getrandbits(128), version=4)
        self.scene.addItem(item)
        self.count += 1
        return item

    @staticmethod
    def _pts(points: list[tuple[float, float]]) -> list[QPointF]:
        return [QPointF(x, y) for x, y in points]

    # -- primitives -------------------------------------------------------
    def rect(self, x: float, y: float, w: float, h: float, ot: ObjectType,
             name: str = "", height_cm: float | None = None) -> RectangleItem:
        item = RectangleItem(x, y, w, h, object_type=ot, name=name)
        if height_cm is not None:
            item.metadata[METADATA_KEY] = float(height_cm)
        return self._add(item)

    def polygon(self, points: list[tuple[float, float]], ot: ObjectType,
                name: str = "") -> PolygonItem:
        return self._add(PolygonItem(self._pts(points), object_type=ot, name=name))

    def circle(self, cx: float, cy: float, r: float, ot: ObjectType,
               name: str = "") -> CircleItem:
        return self._add(CircleItem(cx, cy, r, object_type=ot, name=name))

    def polyline(self, points: list[tuple[float, float]], ot: ObjectType,
                 style: PathFenceStyle = PathFenceStyle.NONE, name: str = "") -> PolylineItem:
        return self._add(
            PolylineItem(self._pts(points), object_type=ot, name=name, path_fence_style=style)
        )

    # -- composites -------------------------------------------------------
    def house(self, points: list[tuple[float, float]], name: str = "House") -> PolygonItem:
        """HOUSE polygon plus its auto ridge — mirrors PolygonTool._create_roof_ridge."""
        house = self.polygon(points, ObjectType.HOUSE, name)
        p1, p2 = compute_roof_ridge_endpoints(house.polygon(), house.pos())
        ridge = self._add(PolylineItem([p1, p2], object_type=ObjectType.ROOF_RIDGE))
        ridge.set_metadata("owner_polygon_id", str(house.item_id))
        house.set_metadata("ridge_item_id", str(ridge.item_id))
        return house

    def plant(self, cx: float, cy: float, common_name: str, ot: ObjectType,
              spread_cm: float | None = None, height_cm: float | None = None,
              parent: Any = None) -> CircleItem:
        """A plant like a gallery drop + species assignment.

        ``spread_cm``/``height_cm`` are the plant's *measured current* size
        (``plant_instance``); trees use them so a 35 m walnut does not swallow
        a 20 m garden. Without them the drawn circle is the species' mature
        spread, exactly what ``apply_species_to_item`` produces.
        """
        item = CircleItem(cx, cy, 30.0, object_type=ot)
        item.plant_species = common_name.lower()
        if not populate_item_species_metadata(item, common_name):
            raise SystemExit(f"bundled species not found: {common_name!r}")
        species = item.metadata["plant_species"]
        instance: dict[str, Any] = {"planting_date": PLANTED}
        if spread_cm is not None:
            instance["current_spread_cm"] = float(spread_cm)
        if height_cm is not None:
            instance["current_height_cm"] = float(height_cm)
        item.metadata["plant_instance"] = instance
        diameter = spread_cm if spread_cm is not None else float(species["max_spread_cm"])
        item.set_radius_centered(diameter / 2.0)
        self._add(item)
        if parent is not None:
            item.parent_bed_id = parent.item_id
            parent.add_child_id(item.item_id)
        return item

    def jitter(self, value: float, amount: float) -> float:
        return value + self.rng.uniform(-amount, amount)


def build_small() -> PlanBuilder:
    """~24 x 16 m showcase garden — every object class, clear zones.

    North: house (+ridge), herb strip, magnolia, greenhouse, gravel yard with
    shed/compost/wheelbarrow behind a stone wall. Middle: terrace with pergola,
    dining set, BBQ and herb pots, fronted by a perennial border. South: lawn
    with pond, bird bath, fire pit, bench, trampoline, cherry tree, a flower
    bed, a shrub border along the west hedge and a stepping-stone path. East:
    gravel path to three raised vegetable beds, a trellis with climbers,
    berry shrubs along the fence, apple/pear/spruce/birch trees.
    """
    b = PlanBuilder(2400.0, 1600.0, seed="ogp-bench-small-v2")
    T = ObjectType

    # --- ground surfaces (bottom of the stack) ---
    b.polygon([(40, 40), (1500, 40), (1500, 640), (40, 640)], T.LAWN, "Lawn")
    b.polygon([(180, 720), (1000, 720), (1000, 960), (180, 960)], T.TERRACE_PATIO, "Terrace")
    b.polygon([(1700, 1140), (2340, 1140), (2340, 1540), (1700, 1540)], T.DRIVEWAY,
              "Gravel yard")
    b.circle(380, 330, 120, T.POND_POOL, "Pond")

    # --- buildings ---
    b.house([(160, 1000), (1060, 1000), (1060, 1540), (160, 1540)])
    b.rect(1340, 1180, 240, 340, T.GREENHOUSE, "Greenhouse")
    b.rect(1960, 1240, 300, 240, T.GARAGE_SHED, "Shed")
    b.rect(220, 740, 380, 210, T.PERGOLA, "Pergola", height_cm=250)

    # --- boundaries ---
    b.polyline([(10, 10), (2390, 10)], T.FENCE, PathFenceStyle.WOODEN_FENCE, "South fence")
    b.polyline([(2390, 10), (2390, 1110)], T.FENCE, PathFenceStyle.WOODEN_FENCE, "East fence")
    b.polygon([(10, 30), (70, 30), (70, 1080), (10, 1080)], T.HEDGE_POLYGON, "Beech hedge")
    b.polyline([(1680, 1120), (2380, 1120)], T.WALL, PathFenceStyle.STONE_WALL, "Yard wall")

    # --- paths ---
    b.polyline([(1000, 840), (1400, 840), (1560, 700), (1560, 120)], T.PATH,
               PathFenceStyle.GRAVEL_PATH, "Gravel path")
    b.polyline([(700, 720), (640, 600), (560, 520), (500, 420)], T.PATH,
               PathFenceStyle.STEPPING_STONES, "Stepping stones")

    # --- beds: herb strip, perennial border, flower bed ---
    herb_strip = b.polygon([(60, 1100), (120, 1100), (120, 1540), (60, 1540)], T.GARDEN_BED,
                           "Herb strip")
    for i, herb in enumerate(["Parsley", "Sage", "Oregano", "Chives", "Thyme"]):
        b.plant(90, 1150 + i * 85, herb, T.PERENNIAL, spread_cm=45, height_cm=35,
                parent=herb_strip)
    border = b.polygon([(180, 650), (1000, 650), (1000, 712), (180, 712)], T.GARDEN_BED,
                       "Perennial border")
    perennials = ["Lavender", "Peony", "Iris", "Echinacea", "Aster", "Geranium",
                  "Chrysanthemum", "Lily", "Borage", "Pansy"]
    for i, name in enumerate(perennials):
        b.plant(220 + i * 82, 681, name, T.PERENNIAL, spread_cm=55,
                height_cm=None, parent=border)
    flower_bed = b.polygon([(90, 70), (430, 60), (460, 190), (120, 210)], T.GARDEN_BED,
                           "Flower bed")
    for (fx, fy), flower in zip(
        [(150, 110), (230, 100), (310, 95), (390, 110), (200, 165), (330, 160)],
        ["Sunflower", "Dahlia", "Marigold", "Cosmos", "Zinnia", "Tulip"],
        strict=True,
    ):
        b.plant(fx, fy, flower, T.PERENNIAL, parent=flower_bed)

    # --- raised beds with vegetables (children) ---
    rows = [
        ["Tomato", "Tomato", "Basil", "Sweet Pepper", "Tomato", "Basil"],
        ["Lettuce", "Cabbage", "Kale", "Lettuce", "Carrot", "Onion", "Beet"],
        ["Zucchini", "Bean (Bush)", "Bean (Bush)", "Leek", "Spinach", "Chives"],
    ]
    for r, crops in enumerate(rows):
        x, y = 1700.0, 160.0 + r * 220.0
        bed = b.rect(x, y, 520, 120, T.RAISED_BED, f"Raised bed {r + 1}")
        step = 520.0 / len(crops)
        for i, crop in enumerate(crops):
            b.plant(x + step * (i + 0.5), y + 60, crop, T.PERENNIAL, parent=bed)

    # --- containers on the terrace ---
    for i, herb in enumerate(["Rosemary", "Lavender", "Thyme"]):
        pot = b.circle(680 + i * 90, 790, 30, T.CONTAINER_ROUND, f"Pot {i + 1}")
        b.plant(680 + i * 90, 790, herb, T.PERENNIAL, spread_cm=45, height_cm=50, parent=pot)

    # --- trellis with climbers ---
    trellis = b.rect(1600, 60, 30, 340, T.TRELLIS, "Trellis")
    b.plant(1660, 140, "Runner Bean", T.PERENNIAL, parent=trellis)
    b.plant(1660, 300, "Cucumber", T.PERENNIAL, spread_cm=90, parent=trellis)

    # --- shrubs: west border along the hedge, berries along the east fence ---
    for i, name in enumerate(["Hydrangea", "Rose", "Lilac", "Boxwood", "Forsythia",
                              "Rhododendron"]):
        b.plant(b.jitter(150, 8), 270 + i * 70, name, T.SHRUB,
                spread_cm=b.rng.uniform(90, 120), height_cm=b.rng.uniform(100, 170))
    for i, name in enumerate(["Blueberry", "Raspberry", "Currant", "Gooseberry"]):
        b.plant(2310, 200 + i * 200, name, T.SHRUB, spread_cm=110,
                height_cm=b.rng.uniform(110, 160))

    # --- trees (measured current size, metres not mature giants) ---
    for tx, ty, name, spread, height in [
        (720, 210, "Cherry Tree", 360, 480),
        (1420, 560, "Birch", 280, 900),
        (1960, 900, "Apple Tree", 340, 420),
        (1580, 1000, "Pear Tree", 280, 450),
        (2270, 980, "Spruce", 240, 800),
        (1180, 1080, "Magnolia", 220, 300),
    ]:
        b.plant(tx, ty, name, T.TREE, spread_cm=spread, height_cm=height)

    # --- furniture ---
    b.rect(330, 790, 160, 90, T.TABLE_RECTANGULAR, "Table")
    for cx, cy in [(350, 760), (470, 760), (350, 910), (470, 910)]:
        b.rect(cx - 22, cy - 22, 45, 45, T.CHAIR, "Chair")
    b.circle(940, 900, 30, T.BBQ_GRILL, "BBQ")
    b.circle(760, 560, 55, T.FIRE_PIT, "Fire pit")
    b.rect(1080, 570, 150, 50, T.BENCH, "Bench")
    b.circle(560, 470, 25, T.BIRD_BATH, "Bird bath")
    b.circle(1150, 280, 140, T.TRAMPOLINE, "Trampoline")
    b.rect(1740, 1180, 90, 90, T.COMPOST_BIN, "Compost")
    b.rect(1760, 1300, 140, 70, T.WHEELBARROW, "Wheelbarrow")
    b.circle(1650, 1185, 30, T.RAIN_BARREL, "Rain barrel")
    return b


def build_large() -> PlanBuilder:
    """50 x 30 m allotment-style plan — 425 items, 320 plants (performance)."""
    b = PlanBuilder(5000.0, 3000.0, seed="ogp-bench-large-v1")
    T = ObjectType
    b.polygon([(30, 30), (4970, 30), (4970, 2970), (30, 2970)], T.LAWN, "Lawn")
    b.house([(200, 2200), (1300, 2200), (1300, 2900), (200, 2900)])
    b.rect(1500, 2500, 400, 350, T.GARAGE_SHED, "Shed")
    b.rect(2100, 2450, 500, 420, T.GREENHOUSE, "Greenhouse")
    b.polyline([(10, 10), (4990, 10), (4990, 2990)], T.FENCE, PathFenceStyle.WOODEN_FENCE,
               "Fence")
    b.polygon([(10, 30), (80, 30), (80, 2990), (10, 2990)], T.HEDGE_POLYGON, "Hedge")
    veg = ["Tomato", "Lettuce", "Cabbage", "Carrot", "Onion", "Bean (Bush)", "Kale",
           "Leek", "Beet", "Spinach", "Zucchini", "Basil", "Sweet Pepper", "Potato",
           "Garlic", "Celery", "Broccoli", "Endive"]
    # 24 raised beds x 10 plants = 240 vegetables
    for row in range(4):
        for col in range(6):
            x, y = 400 + col * 700, 300 + row * 450
            bed = b.rect(x, y, 560, 140, T.RAISED_BED, f"Bed {row}-{col}")
            for i in range(10):
                crop = veg[(row * 6 + col + i) % len(veg)]
                b.plant(x + 28 + i * 56, y + 70, crop, T.PERENNIAL, parent=bed)
            b.polyline([(x - 40, y - 60), (x + 600, y - 60)], T.PATH,
                       PathFenceStyle.GRAVEL_PATH)
    # 40 trees along the edges
    tree_names = ["Apple Tree", "Pear Tree", "Plum Tree", "Cherry Tree", "Birch", "Maple",
                  "Spruce", "Pine", "Walnut Tree", "Magnolia"]
    for i in range(40):
        side = i % 2
        x = 300 + (i // 2) * 230
        y = 2050 if side else 120
        b.plant(b.jitter(x, 30), b.jitter(y, 30), tree_names[i % len(tree_names)], T.TREE,
                spread_cm=b.rng.uniform(250, 500), height_cm=b.rng.uniform(300, 900))
    # 40 shrubs
    shrubs = ["Hydrangea", "Rose", "Lilac", "Boxwood", "Forsythia", "Blueberry",
              "Raspberry", "Currant"]
    for i in range(40):
        b.plant(b.jitter(4700, 60), b.jitter(200 + i * 65, 10), shrubs[i % len(shrubs)],
                T.SHRUB, spread_cm=b.rng.uniform(80, 150), height_cm=b.rng.uniform(80, 180))
    # furniture + misc for draw-call pressure
    for _ in range(30):
        b.rect(b.jitter(3600, 300), b.jitter(2500, 250), 45, 45, T.CHAIR, "Chair")
    for _ in range(20):
        b.circle(b.jitter(3000, 900), b.jitter(2100, 60), 30, T.RAIN_BARREL, "Barrel")
    return b


def _save(builder: PlanBuilder, path: Path) -> None:
    pm = ProjectManager()
    pm.set_location(dict(BERLIN))
    path.parent.mkdir(parents=True, exist_ok=True)
    pm.save(builder.scene, path)


def _normalised(path: Path) -> Any:
    """Plan content minus fields that legitimately change between runs."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.get("metadata", {}).pop("modified", None)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--check", action="store_true",
                        help="regenerate to a temp dir and compare with the committed fixtures")
    args = parser.parse_args(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])  # noqa: F841

    plans = {"bench_small.ogp": build_small, "bench_large.ogp": build_large}
    if args.check:
        failed = False
        with tempfile.TemporaryDirectory() as tmp:
            for name, build in plans.items():
                fresh = Path(tmp) / name
                _save(build(), fresh)
                committed = OUT_DIR / name
                if not committed.is_file() or _normalised(fresh) != _normalised(committed):
                    print(f"STALE: {committed.relative_to(REPO)} — rerun scripts/make_bench_plans.py")
                    failed = True
        print("bench plans: " + ("FAIL" if failed else "OK"))
        return 1 if failed else 0

    for name, build in plans.items():
        builder = build()
        _save(builder, OUT_DIR / name)
        print(f"wrote {OUT_DIR.relative_to(REPO) / name}: {builder.count} items")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
