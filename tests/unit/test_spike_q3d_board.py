"""Truth gates on the spike's REAL board: the bench plan through ``build_models`` (ADR-048, L0).

The builder tests in ``test_spike_q3d_meshes.py`` prove each builder in
isolation; these prove the pipeline the Beauty Board actually renders — the
showcase plan ``bench_small.ogp`` resolved, built and fitted exactly as the
spike does it, with a recording factory instead of the engine (no GPU):

* every built object's top IS its resolved height (±1 %), every plant's
  top − base IS its height (±3 %) — on the June AND the December build;
* an item the 2D shadow overlay casts nothing for casts nothing in 3D either;
* every flat face of every built model stores its winding normal;
* each shot shows the plan on its own sun date (the board loop, Qt-free).

``ogp-lush-cinematic`` §1 is the contract; the L0 review found each of these
broken on the board while the per-builder tests were green.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from open_garden_planner.spike_q3d import meshes as M
from open_garden_planner.spike_q3d import runner

REPO = Path(__file__).resolve().parents[2]
PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_small.ogp"
JUNE, DECEMBER = date(2026, 6, 21), date(2026, 12, 21)
PLANTS = {"TREE", "SHRUB", "PERENNIAL"}


def _load():
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    scene = CanvasScene()
    pm = ProjectManager()
    pm.load(scene, PLAN)
    return scene, pm.location


def _board(scene, at: date, location=None) -> dict[str, list[tuple]]:
    """item id → [(mesh, kind, casts)] exactly as the spike would hand them to the engine."""
    rows: dict[str, list[tuple]] = defaultdict(list)

    def record(item_id, mesh, kind, casts):
        rows[item_id].append((mesh, kind, casts))
        return item_id

    runner.build_models(scene, at, 110.0, False, make_model=record, location=location)
    return rows


@pytest.fixture(scope="module")
def plan(qapp):  # noqa: ARG001 — a QApplication for the CanvasScene
    scene, location = _load()
    items = {str(i.item_id): i for i in scene.items()
             if hasattr(i, "item_id") and getattr(i, "object_type", None) is not None}
    # built with the plan's OWN location, as the spike's board builds them
    return scene, items, {JUNE: _board(scene, JUNE, location),
                          DECEMBER: _board(scene, DECEMBER, location)}


@pytest.mark.parametrize("at", [JUNE, DECEMBER], ids=["june", "december"])
def test_every_object_top_is_its_resolved_height(plan, at: date) -> None:
    from open_garden_planner.core.object_height import effective_height_cm

    _scene, items, boards = plan
    checked, bad = 0, []
    for item_id, parts in boards[at].items():
        item = items.get(item_id)
        if item is None:
            continue
        h = effective_height_cm(item.object_type, item.metadata, at_date=at)
        if h is None:
            continue  # decoration — the shadow test below pins that it casts nothing
        top = max(float(m.positions[:, 2].max()) for m, _k, _c in parts)
        base = min(float(m.positions[:, 2].min()) for m, _k, _c in parts)
        if item.object_type.name in PLANTS:
            err, tol = (top - max(base, 0.0)) / h - 1.0, 0.03  # a planted plant stands on soil
        else:
            err, tol = top / h - 1.0, 0.01
        checked += 1
        if abs(err) > tol:
            bad.append((item.object_type.name, round(h, 1), round(top, 1), f"{err:+.1%}"))
    # 99 items − 12 with no resolved height (ridge line, lawn, terrace, driveway, 3 garden
    # beds, 2 paths, pond, rain barrel, fire pit) = 87 measured objects, none outside
    assert checked == 87, checked
    assert bad == []


@pytest.mark.parametrize("at", [JUNE, DECEMBER], ids=["june", "december"])
def test_builders_meet_their_height_without_the_fit(plan, at: date) -> None:
    """The height test above cannot fail while ``fit_height`` exists: it forces every
    built top to the data, so a builder overshooting by 15 % would be silently
    squashed (senior review). The scale the fit applied must be ~1."""
    scene, items, _boards = plan
    _models, stats = runner.build_models(scene, at, 110.0, False,
                                         make_model=lambda *args: args)
    assert len(stats.fit_scales) >= 20, stats.fit_scales  # not vacuous
    off = {items[k].object_type.name: round(v, 4) for k, v in stats.fit_scales.items()
           if abs(v - 1.0) > 0.01}
    assert off == {}


@pytest.mark.parametrize("at", [JUNE, DECEMBER], ids=["june", "december"])
def test_3d_casts_shadows_only_where_2d_does(plan, at: date) -> None:
    """RAIN_BARREL (100 cm) and FIRE_PIT (28 cm) cast 3D shadows the 2D view never casts."""
    from open_garden_planner.core.object_height import effective_height_cm

    _scene, items, boards = plan
    casters_3d = {iid for iid, parts in boards[at].items() if any(c for _m, _k, c in parts)}
    # the rule of sun_shadow_controller.collect_shadow_casters: a visible item casts iff
    # the resolver gives it a height at the simulation date
    casters_2d = {iid for iid, item in items.items() if item.isVisible()
                  and effective_height_cm(item.object_type, item.metadata, at_date=at) is not None}
    assert casters_3d - casters_2d == set()
    decorative = {items[i].object_type.name for i in boards[at] if i in items and i not in casters_2d}
    assert {"RAIN_BARREL", "FIRE_PIT"} <= decorative  # drawn, but casting nothing


def test_every_flat_face_on_the_board_stores_its_winding_normal(plan) -> None:
    _scene, items, boards = plan
    worst, flat_total = 1.0, 0
    for item_id, parts in boards[JUNE].items():
        for mesh, kind, _c in parts:
            if kind not in ("vc", "roof", "glass", "water"):
                continue  # foliage/grass: bent-normal cards, exempt by design
            dots, flat = M.normal_vs_winding(mesh)
            if flat.any():
                flat_total += int(flat.sum())
                if dots[flat].min() < worst:
                    worst = float(dots[flat].min())
                    worst_item = items[item_id].object_type.name if item_id in items else item_id
    assert flat_total > 1000
    assert worst >= 0.99, (worst_item, worst)


def test_roofs_wear_their_own_material_and_keep_the_houses_height(plan) -> None:
    """The house and the shed: walls in the shared material, the roof (slabs, soffit, ridge
    cap) as its own "roof" model — the shared 0.35 specular made the noon roof salmon."""
    from open_garden_planner.core.object_height import effective_height_cm

    _scene, items, boards = plan
    roofed = {iid: parts for iid, parts in boards[JUNE].items()
              if iid in items and items[iid].object_type.name in ("HOUSE", "GARAGE_SHED", "TOOL_SHED")}
    assert {items[i].object_type.name for i in roofed} >= {"HOUSE", "GARAGE_SHED"}
    for iid, parts in roofed.items():
        assert sorted(k for _m, k, _c in parts) == ["roof", "vc"]
        assert all(casts for _m, _k, casts in parts)
        roof = next(m for m, k, _c in parts if k == "roof")
        walls = next(m for m, k, _c in parts if k == "vc")
        h = effective_height_cm(items[iid].object_type, items[iid].metadata, at_date=JUNE)
        assert float(roof.positions[:, 2].max()) == pytest.approx(h, rel=0.01)  # the ridge cap
        assert float(walls.positions[:, 2].max()) < float(roof.positions[:, 2].max()) - 5.0
        dots, flat = M.normal_vs_winding(roof)
        assert flat.any() and dots[flat].min() >= 0.99


# ── the per-plant triangle budget on BOTH bench plans, both board dates (reviewer pass 3,
# P1): bench_small December had a 30,808-triangle birch and a 28,016 spruce; bench_large
# 14 trees over 25,000 in June and 15 in December (max 40,954) — the builder test only
# built four small plants ──

LARGE_PLAN = REPO / "tests" / "fixtures" / "plans" / "bench_large.ogp"


@pytest.fixture(scope="module")
def bench_plant_triangles(qapp):  # noqa: ARG001 — a QApplication for the CanvasScene
    """(plan, date) → {item id: (object type, triangles of all its models)} for every plant."""
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene

    out: dict[tuple[str, date], dict[str, tuple[str, int]]] = {}
    for path in (PLAN, LARGE_PLAN):
        scene, pm = CanvasScene(), ProjectManager()
        pm.load(scene, path)
        types = {str(i.item_id): i.object_type.name for i in scene.items()
                 if hasattr(i, "item_id") and getattr(i, "object_type", None) is not None}
        for at in (JUNE, DECEMBER):
            counts: dict[str, int] = defaultdict(int)

            def record(item_id, mesh, _kind, _casts, counts=counts):
                counts[item_id] += mesh.triangle_count

            runner.build_models(scene, at, 110.0, False, make_model=record, location=pm.location)
            out[(path.name, at)] = {iid: (types[iid], n) for iid, n in counts.items()
                                    if types.get(iid) in PLANTS}
    return out


@pytest.mark.parametrize("plan_name", ["bench_small.ogp", "bench_large.ogp"])
@pytest.mark.parametrize("at", [JUNE, DECEMBER], ids=["june", "december"])
def test_every_bench_plant_is_within_its_triangle_budget(bench_plant_triangles, plan_name: str,
                                                         at: date) -> None:
    rows = bench_plant_triangles[(plan_name, at)]
    trees = {iid: n for iid, (t, n) in rows.items() if t == "TREE"}
    others = {iid: (t, n) for iid, (t, n) in rows.items() if t != "TREE"}
    assert len(trees) == (6 if plan_name == "bench_small.ogp" else 40)  # not vacuous
    assert len(others) >= 50
    assert sorted(n for n in trees.values() if n > M.TREE_TRIANGLE_BUDGET) == []
    assert sorted(v for v in others.values() if v[1] > M.PLANT_TRIANGLE_BUDGET) == []


def test_the_december_board_shows_the_december_plan(plan) -> None:
    """Growth-projected plants are taller in December 2026 than in June (21 June planting year)."""
    from open_garden_planner.core.object_height import effective_height_cm

    _scene, items, boards = plan
    spruce = next(i for i, it in items.items()
                  if (it.metadata.get("plant_species") or {}).get("common_name") == "Spruce")
    tops = {at: max(float(m.positions[:, 2].max()) for m, _k, _c in boards[at][spruce])
            for at in (JUNE, DECEMBER)}
    for at, top in tops.items():
        h = effective_height_cm(items[spruce].object_type, items[spruce].metadata, at_date=at)
        assert top == pytest.approx(h, rel=0.03)
    assert tops[DECEMBER] > tops[JUNE] * 1.1


# ── the season comes from the plan's frost dates, never from the look ──
#
# The 3D creator round-1 board showed red fruit and open flowers on 21 December. Fruit
# and flowers are now shown only inside the plan's frost-free season
# (location["frost_dates"], the keys the task generator reads); the fixture carries
# Berlin's (04-09 .. 10-31). Accent geometry is found by its EXACT colour: fruit,
# clusters, spikes and pompoms are drawn in their accent colour, every flower has a
# disk of a fixed colour (meshes.py: tree "#f7e3a0", mound "#f0d060", blades
# "#f2cf4e", sunflower "#5b3a1a" and "#4a2e14"); petals are jittered and not needed.

FRUIT_AND_FLOWER_KINDS = {"fruit", "flower", "cluster", "spike", "pompom"}
DISK_COLORS = ("#f7e3a0", "#f0d060", "#f2cf4e", "#5b3a1a", "#4a2e14")


def _accent_markers() -> np.ndarray:
    names = {accent for _a, _p, kind, accent in M.SPECIES_LOOK.values()
             if kind in FRUIT_AND_FLOWER_KINDS}
    names.add("tomato_green")  # the unripe tomatoes beside the red ones
    return np.array([M.srgb_to_linear(M.ACCENTS[n]) for n in sorted(names)]
                    + [M.srgb_to_linear(c) for c in DISK_COLORS])


def _accent_vertices(parts, markers) -> int:
    total = 0
    for mesh, _kind, _casts in parts:
        rgb = mesh.colors[:, :3]
        hit = (np.abs(rgb[:, None, :] - markers[None, :, :]).max(axis=2) < 1e-6).any(axis=1)
        total += int(hit.sum())
    return total


def _seasonal_plants(items) -> dict[str, str]:
    """item id → species, for every plant whose look carries fruit or flowers."""
    out = {}
    for iid, item in items.items():
        name = ((item.metadata.get("plant_species") or {}).get("common_name") or "").lower()
        look = M.SPECIES_LOOK.get(name)
        if item.object_type.name in PLANTS and look and look[2] in FRUIT_AND_FLOWER_KINDS:
            out[iid] = name
    return out


def test_the_plan_carries_the_frost_dates_the_season_is_read_from(qapp) -> None:  # noqa: ARG001
    _scene, location = _load()
    assert location["frost_dates"] == {"last_spring_frost": "04-09", "first_fall_frost": "10-31"}
    assert runner.in_frost_free_season(location, JUNE) is True
    assert runner.in_frost_free_season(location, DECEMBER) is False


def test_december_shows_no_fruit_or_flowers_june_shows_them(plan) -> None:
    _scene, items, boards = plan
    markers = _accent_markers()
    seasonal = _seasonal_plants(items)
    assert len(seasonal) >= 30, sorted(seasonal.values())  # not vacuous: the bench is full of them
    june = {iid: _accent_vertices(boards[JUNE][iid], markers) for iid in seasonal}
    december = {iid: _accent_vertices(boards[DECEMBER][iid], markers) for iid in seasonal}
    # every one in June but the sweet pepper: its fruit follows the calendar's harvest
    # window, 04-09 + 12..18 weeks = 2 Jul..13 Aug (the tomato's, 18 Jun..27 Aug, holds)
    assert {seasonal[i] for i, n in june.items() if n == 0} == {"sweet pepper"}
    assert {seasonal[i] for i, n in december.items() if n > 0} == set()   # none in December
    # and nothing else on the December board wears a fruit or flower colour
    assert sum(_accent_vertices(parts, markers) for parts in boards[DECEMBER].values()) == 0


def test_without_frost_dates_the_accents_stay(plan) -> None:
    """No data, no seasonal claim: a plan without frost dates keeps fruit and flowers."""
    scene, items, _boards = plan
    markers = _accent_markers()
    seasonal = _seasonal_plants(items)
    for location in (None, {"latitude": 52.52, "longitude": 13.405}):
        board = _board(scene, DECEMBER, location)
        bare = {seasonal[i] for i in seasonal if _accent_vertices(board[i], markers) == 0}
        assert bare == set(), (location, sorted(bare))


def test_out_of_season_plants_keep_their_truth_gates(plan) -> None:
    """Dropping accents must not move a plant's height or spread off the data."""
    from open_garden_planner.ui.canvas.sun_shadow_controller import _plant_canopy_radius_cm

    _scene, items, boards = plan
    checked = 0
    for iid in _seasonal_plants(items):
        item = items[iid]
        mesh = boards[DECEMBER][iid][0][0]
        radius = _plant_canopy_radius_cm(item, DECEMBER) or item.radius
        span = max(float(np.ptp(mesh.positions[:, 0])), float(np.ptp(mesh.positions[:, 1])))
        assert span == pytest.approx(2.0 * radius, rel=0.10), item.name
        checked += 1
    assert checked >= 30


@pytest.mark.parametrize(("frost", "day", "expected"), [
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 6, 21), True),
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 12, 21), False),
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 4, 9), True),
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 4, 8), False),
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 10, 31), True),
    ({"last_spring_frost": "04-09", "first_fall_frost": "10-31"}, date(2026, 11, 1), False),
    # one date only: the window is open on the other side
    ({"last_spring_frost": "04-09"}, date(2026, 3, 1), False),
    ({"last_spring_frost": "04-09"}, date(2026, 12, 21), True),
    ({"first_fall_frost": "10-31"}, date(2026, 12, 21), False),
    ({"first_fall_frost": "10-31"}, date(2026, 1, 15), True),
    # a spring date after the fall date wraps the new year (southern hemisphere)
    ({"last_spring_frost": "09-20", "first_fall_frost": "05-10"}, date(2026, 12, 21), True),
    ({"last_spring_frost": "09-20", "first_fall_frost": "05-10"}, date(2026, 7, 1), False),
    ({"last_spring_frost": "09-20", "first_fall_frost": "05-10"}, date(2026, 5, 10), True),
    # no usable data: no seasonal claim
    ({}, date(2026, 12, 21), True),
    ({"last_spring_frost": "13-40", "first_fall_frost": "04/09"}, date(2026, 12, 21), True),
    ({"last_spring_frost": 409, "first_fall_frost": None}, date(2026, 12, 21), True),
    # the leap day is a valid entry in any year
    ({"last_spring_frost": "02-29", "first_fall_frost": "10-31"}, date(2026, 2, 28), False),
])
def test_frost_free_season_reads_the_plans_frost_dates(frost: dict, day: date,
                                                       expected: bool) -> None:
    assert runner.in_frost_free_season({"frost_dates": frost}, day) is expected


# ── fruit follows the planting calendar's harvest window (3D reviewer pass 3) ──
#
# services/task_generator.generate_calendar_tasks: last spring frost + harvest_start weeks
# .. + harvest_end weeks. The 3D view showed red tomatoes from the 9 April last frost.

BERLIN = {"frost_dates": {"last_spring_frost": "04-09", "first_fall_frost": "10-31"}}
TOMATO = {"common_name": "Tomato", "harvest_start": 10, "harvest_end": 20}


@pytest.mark.parametrize(("location", "species", "day", "expected"), [
    (BERLIN, TOMATO, date(2026, 4, 9), False),     # the last frost: planted, no fruit yet
    (BERLIN, TOMATO, date(2026, 6, 17), False),
    (BERLIN, TOMATO, date(2026, 6, 18), True),     # 04-09 + 10 weeks
    (BERLIN, TOMATO, date(2026, 6, 21), True),     # the board's June date
    (BERLIN, TOMATO, date(2026, 8, 27), True),     # 04-09 + 20 weeks
    (BERLIN, TOMATO, date(2026, 8, 28), False),
    (BERLIN, TOMATO, date(2026, 12, 21), False),
    # a window across the new year (southern plan): anchored on last year's frost too
    ({"frost_dates": {"last_spring_frost": "09-20"}}, TOMATO, date(2026, 1, 15), True),
    ({"frost_dates": {"last_spring_frost": "09-20"}}, TOMATO, date(2026, 3, 1), False),
    # negative offsets (a harvest before the last frost) anchor on next year's frost
    (BERLIN, {"harvest_start": -30, "harvest_end": -20}, date(2026, 10, 1), True),
    # no window to read: None, and the frost-free season decides
    (BERLIN, {"harvest_start": 10}, date(2026, 6, 21), None),
    (BERLIN, {"harvest_start": None, "harvest_end": 20}, date(2026, 6, 21), None),
    (BERLIN, {"harvest_start": "10", "harvest_end": 20}, date(2026, 6, 21), None),
    (BERLIN, {"harvest_start": True, "harvest_end": 20}, date(2026, 6, 21), None),
    (BERLIN, {"harvest_start": 20, "harvest_end": 10}, date(2026, 6, 21), None),
    (BERLIN, None, date(2026, 6, 21), None),
    ({"frost_dates": {"first_fall_frost": "10-31"}}, TOMATO, date(2026, 6, 21), None),
    (None, TOMATO, date(2026, 6, 21), None),
    ({"frost_dates": {"last_spring_frost": "02-29"}}, TOMATO, date(2026, 6, 21), None),
])
def test_harvest_window_is_the_planting_calendars(location, species, day: date,
                                                  expected: bool | None) -> None:
    assert runner.in_harvest_window(location, day, species) is expected


def test_harvest_window_matches_the_task_generator() -> None:
    """The same dates the planting calendar's harvest task spans, from the same rule."""
    from open_garden_planner.services.task_generator import _parse_frost

    last_frost = _parse_frost("04-09", 2026)
    import datetime as dt

    start = last_frost + dt.timedelta(weeks=TOMATO["harvest_start"])
    end = last_frost + dt.timedelta(weeks=TOMATO["harvest_end"])
    assert (start, end) == (date(2026, 6, 18), date(2026, 8, 27))
    for day in (start - dt.timedelta(days=1), start, end, end + dt.timedelta(days=1)):
        assert runner.in_harvest_window(BERLIN, day, TOMATO) is (start <= day <= end)


@pytest.mark.parametrize(("name", "species", "frost_free", "expected"), [
    ("Tomato", TOMATO, True, False),            # fruit: the harvest window wins (4 May)
    ("Tomato", {"common_name": "Tomato"}, True, True),   # no window: the frost season
    ("Apple Tree", {}, True, True),
    ("Marigold", {"harvest_start": 8, "harvest_end": 9}, True, True),  # flowers: frost only
    ("Marigold", {"harvest_start": 1, "harvest_end": 30}, False, False),
    ("Unknown Plant", TOMATO, True, True),
])
def test_only_fruit_follows_the_harvest_window(name: str, species: dict, frost_free: bool,
                                               expected: bool) -> None:
    assert runner.accents_in_season(BERLIN, date(2026, 5, 4), name, species,
                                    frost_free) is expected


def test_a_may_board_shows_flowers_but_no_tomatoes_yet(plan) -> None:
    """In the frost-free season, before the harvest window: flowers yes, tomatoes no."""
    scene, items, _boards = plan
    may = date(2026, 5, 15)
    board = _board(scene, may, BERLIN)
    markers = _accent_markers()
    seasonal = _seasonal_plants(items)
    shown = {seasonal[i] for i in seasonal if _accent_vertices(board[i], markers) > 0}
    bare = {seasonal[i] for i in seasonal} - shown
    assert {"tomato", "sweet pepper"} <= bare        # harvest from 18 Jun / 2 Jul
    assert {"marigold", "lavender", "magnolia", "apple tree"} <= shown  # flowers; fruit w/o window
    tomato_green = M.srgb_to_linear(M.ACCENTS["tomato_green"])
    for iid in (i for i in seasonal if seasonal[i] == "tomato"):  # not even green ones
        for mesh, _k, _c in board[iid]:
            assert not (np.abs(mesh.colors[:, :3] - tomato_green).max(axis=1) < 1e-6).any()


def test_no_location_makes_no_seasonal_claim() -> None:
    assert runner.in_frost_free_season(None, DECEMBER) is True
    assert runner.in_frost_free_season({"latitude": 52.52}, DECEMBER) is True
    # malformed (a hand-edited file): no data, not a crash in the 3D build
    assert runner.in_frost_free_season({"frost_dates": "04-09"}, DECEMBER) is True
    assert runner.in_frost_free_season({"frost_dates": None}, DECEMBER) is True


# ── the board loop (Qt-free): each shot is grabbed with ITS date's models ──


class _FakeImage:
    def save(self, _path: str) -> None:
        pass


class _FakeRenderer:
    """Records which date's models were on screen at every grab."""

    def __init__(self) -> None:
        self.models: list = []
        self.grabs: list[tuple[str, str | None]] = []
        self.shot = ""

    def set_models(self, models: list) -> None:
        self.models = list(models)

    def set_preset(self, _p: str) -> None: ...
    def set_look(self, _look: dict) -> None: ...
    def set_sun(self, _sun) -> None: ...

    def set_camera(self, *_a) -> None: ...

    def wait_frames(self, *_a, **_k) -> int:
        return 0

    def grab(self, label: str = "") -> _FakeImage:
        dates = {m["date"] for m in self.models}
        assert len(dates) == 1, dates
        self.grabs.append((label, dates.pop()))
        return _FakeImage()


class _FakeSun:
    def __init__(self, when) -> None:
        self.elevation, self.azimuth, self.night = 30.0, 180.0, False
        self.when = when


def test_each_shot_is_grabbed_with_its_own_dates_models(tmp_path: Path) -> None:
    builds: list[date] = []

    def build(at: date):
        builds.append(at)
        return [{"date": at.isoformat()}], runner.BuildStats()

    shots = runner.default_shots(2400.0, 1600.0)
    assert {s.when_utc.date() for s in shots} == {JUNE, DECEMBER}  # the board spans two dates
    fake = _FakeRenderer()
    metrics: dict = {}
    measured: list[_FakeImage] = []

    def frame_stats(img: _FakeImage) -> dict:
        measured.append(img)
        return {"isolated_dark_px": len(measured)}

    rows = runner.shoot_board(fake, shots, ["low", "high"], runner.ModelsByDate(build), _FakeSun,
                              tmp_path, lambda *_a, **_k: None, metrics, frame_stats=frame_stats)
    by_label = dict(fake.grabs)
    for shot in shots:
        for preset in ("low", "high"):
            assert by_label[f"{shot.name}_{preset}"] == shot.when_utc.date().isoformat()
    assert sorted(builds) == [JUNE, DECEMBER]  # each date built once, then cached
    assert all(r["build_date"] == r["sun_date"] for r in rows)
    assert len(rows) == 2 * len(shots) and metrics["shots"] is rows
    # every grabbed frame is measured once, and its numbers land in its own row
    assert [r["isolated_dark_px"] for r in rows] == list(range(1, len(rows) + 1))


def test_the_board_samples_every_part_of_the_light_rig(qapp) -> None:  # noqa: ARG001
    """golden_hour (15.2°) and december_noon (14.0°) sampled almost the same point of the
    golden → noon ramp and no shot rendered the 6° golden anchor (3D reviewer pass 4):
    the board covers night, the golden anchor, the ramp and the noon rig, with the sun
    from ``core/solar`` at the bench plan's own location."""
    from open_garden_planner.core.solar import solar_position

    _scene, location = _load()
    lat, lon = float(location["latitude"]), float(location["longitude"])
    shots = {s.name: s for s in runner.default_shots(2400.0, 1600.0)}
    assert list(shots) == ["golden_hour", "sunset", "noon", "morning", "december_noon", "night",
                           "walk"]
    elev = {n: solar_position(lat, lon, s.when_utc).elevation_deg for n, s in shots.items()}
    sunset = solar_position(lat, lon, shots["sunset"].when_utc)
    assert shots["sunset"].when_utc.isoformat() == "2026-06-21T18:38:00+00:00"
    assert sunset.elevation_deg == pytest.approx(5.9, abs=0.05)
    assert sunset.azimuth_deg == pytest.approx(301.5, abs=0.05)
    # the golden anchor itself: within 0.2° of SUN_RAMP_LOW_DEG, on the daytime rig
    assert runner.SUN_LOW_DEG < elev["sunset"] < runner.SUN_RAMP_LOW_DEG
    assert abs(elev["sunset"] - runner.SUN_RAMP_LOW_DEG) < 0.2
    assert elev["night"] < runner.SUN_LOW_DEG
    ramp = [e for e in elev.values() if runner.SUN_RAMP_LOW_DEG < e < runner.SUN_RAMP_HIGH_DEG]
    assert len(ramp) >= 3  # golden_hour, morning, december_noon
    assert max(elev.values()) >= runner.SUN_RAMP_HIGH_DEG  # the noon rig
    # the sunset frame is golden_hour's camera, two hours later
    assert (shots["sunset"].eye, shots["sunset"].target, shots["sunset"].fov) == (
        shots["golden_hour"].eye, shots["golden_hour"].target, shots["golden_hour"].fov)


def test_look_derives_the_fog_and_never_paints_the_ground() -> None:
    """Fog = sky horizon × probe exposure × 0.8 (linear): it must match the sky the skybox draws."""
    golden, noon, low, night, ramp = (_FakeSun(None) for _ in range(5))
    golden.elevation, noon.elevation, low.elevation, ramp.elevation = 6.0, 45.0, 4.0, 15.0
    night.night = True
    for sun in (golden, noon, low, night, ramp):
        look = runner.look_for(sun)
        assert look["fogColor"] == runner.scale_linear(look["skyHorizon"],
                                                       look["probe"] * runner.FOG_OF_HORIZON)
        assert not {"meadowColor", "groundHorizon"} & set(look)
    # pinned independently: the golden rig (6°) #f4d2a6 × probe 0.5 × 0.8 in linear light
    assert runner.look_for(golden)["fogColor"] == "#a28b6d"
    assert runner.scale_linear("#ffffff", 1.0) == "#ffffff"
    assert runner.scale_linear("#808080", 0.5) == "#5c5c5c"


def test_sun_colour_ramps_continuously_between_the_rigs() -> None:
    """15°/6° steps gave December noon (14.0°) a warmer sun than June golden hour (15.2°);
    the return to the low rig under 6° was a step too (3D reviewer pass 3)."""
    noon, golden, low = runner.SUN_NOON, runner.SUN_GOLDEN, runner.SUN_LOW
    assert runner.sun_light(30.0) == noon and runner.sun_light(60.9) == noon
    assert runner.sun_light(6.0) == golden and runner.sun_light(0.5) == low
    elevs = np.linspace(6.0, 29.99, 200)
    blue = [M.srgb_to_linear(runner.sun_light(e)[0])[2] for e in elevs]
    bright = [runner.sun_light(e)[1] for e in elevs]
    assert np.all(np.diff(blue) >= 0)   # cooler as the sun climbs: never a warm step up
    assert np.all(np.diff(bright) <= 0)
    rising = [runner.sun_light(e)[1] for e in np.linspace(0.5, 6.0, 100)]
    assert np.all(np.diff(rising) >= 0)  # the low sun brightens into the golden rig
    for near, anchor in ((runner.sun_light(29.99), noon), (runner.sun_light(5.99), golden),
                         (runner.sun_light(0.51), low)):  # continuous into every anchor
        assert np.abs(M.srgb_to_linear(near[0]) - M.srgb_to_linear(anchor[0])).max() < 0.01
        assert abs(near[1] - anchor[1]) < 0.01
    dec, june_golden = runner.sun_light(14.04), runner.sun_light(15.23)
    assert M.srgb_to_linear(dec[0])[2] <= M.srgb_to_linear(june_golden[0])[2]


def test_the_sun_never_outshines_its_noon_self() -> None:
    """A low sun crosses more air: its direct light is weaker, never stronger. The golden
    anchor at 2.1 put a 2.03 sun into the 14° December noon, under exposure 1.04, and
    clipped the red channel of sun-facing warm faces on 1.56 % of december_noon_low
    (3D reviewer pass 4). The golden mood is the exposure and the colour."""
    elevs = np.arange(runner.SUN_LOW_DEG, 90.0, 0.05)
    bright = np.array([runner.sun_light(e)[1] for e in elevs])
    assert np.all(np.diff(bright) >= 0)                 # never brighter as the sun sinks
    assert bright.max() == pytest.approx(runner.SUN_NOON[1])
    assert runner.sun_light(14.04)[1] <= runner.SUN_NOON[1]


def _codes(hex_color: str) -> np.ndarray:
    return np.array([int(hex_color[i:i + 2], 16) for i in (1, 3, 5)])


def test_the_day_rig_has_no_steps() -> None:
    """Sky, fog, sun disc, probe and exposure stepped at 8° and 20° (exposure 1.15 → 0.85
    in one degree), the key light at 6°: now continuous from the low rig (0.5°) through
    the golden rig (6°) to the noon rig (30°+), sampled every 0.05°."""
    assert runner.look_for(_sun_at(30.0)) == runner.look_for(_sun_at(60.9))  # noon rig above 30°
    for elev, anchor in ((30.0, runner.LOOK_NOON), (6.0, runner.LOOK_GOLDEN),
                         (0.5, runner.LOOK_LOW)):
        assert runner.day_look(elev) == anchor
    looks = [runner.look_for(_sun_at(e)) for e in np.arange(0.5, 40.0, 0.05)]
    suns = [runner.sun_light(e) for e in np.arange(0.5, 40.0, 0.05)]
    for key in ("skyTop", "skyHorizon", "sunDiscColor", "fogColor"):
        codes = np.array([_codes(look[key]) for look in looks])
        assert np.abs(np.diff(codes, axis=0)).max() <= 1, key  # one 8-bit code per 0.05° at most
    sun_codes = np.array([_codes(c) for c, _b in suns])
    assert np.abs(np.diff(sun_codes, axis=0)).max() <= 1
    assert np.abs(np.diff([b for _c, b in suns])).max() < 0.01
    stops = np.log2([look["exposure"] for look in looks])
    assert np.abs(np.diff(stops)).max() < 0.005
    assert np.abs(np.diff([look["probe"] for look in looks])).max() < 0.002
    # the board's December noon (14.04°): between the golden and the noon exposure, in stops
    t = (14.04 - 6.0) / 24.0
    assert runner.look_for(_sun_at(14.04))["exposure"] == pytest.approx(1.15 ** (1 - t) * 0.85 ** t)
    assert runner.look_for(_sun_at(14.04))["exposure"] == pytest.approx(1.039, abs=0.001)


def _sun_at(elev: float) -> _FakeSun:
    sun = _FakeSun(None)
    sun.elevation = float(elev)
    return sun
