"""Truth gates on the spike's REAL board: the bench plan through ``build_models`` (ADR-047, L0).

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
            if kind not in ("vc", "glass", "water"):
                continue  # foliage/grass: bent-normal cards, exempt by design
            dots, flat = M.normal_vs_winding(mesh)
            if flat.any():
                flat_total += int(flat.sum())
                if dots[flat].min() < worst:
                    worst = float(dots[flat].min())
                    worst_item = items[item_id].object_type.name if item_id in items else item_id
    assert flat_total > 1000
    assert worst >= 0.99, (worst_item, worst)


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
    assert {seasonal[i] for i, n in june.items() if n == 0} == set()       # every one in June
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
    rows = runner.shoot_board(fake, shots, ["low", "high"], runner.ModelsByDate(build), _FakeSun,
                              tmp_path, lambda *_a, **_k: None, metrics)
    by_label = dict(fake.grabs)
    for shot in shots:
        for preset in ("low", "high"):
            assert by_label[f"{shot.name}_{preset}"] == shot.when_utc.date().isoformat()
    assert sorted(builds) == [JUNE, DECEMBER]  # each date built once, then cached
    assert all(r["build_date"] == r["sun_date"] for r in rows)
    assert len(rows) == 2 * len(shots) and metrics["shots"] is rows


def test_look_derives_the_fog_and_never_paints_the_ground() -> None:
    """Fog = sky horizon × probe exposure × 0.8 (linear): it must match the sky the skybox draws."""
    golden, noon, low, night = (_FakeSun(None) for _ in range(4))
    golden.elevation, noon.elevation, low.elevation = 15.0, 45.0, 4.0
    night.night = True
    for sun in (golden, noon, low, night):
        look = runner.look_for(sun)
        assert look["fogColor"] == runner.scale_linear(look["skyHorizon"],
                                                       look["probe"] * runner.FOG_OF_HORIZON)
        assert not {"meadowColor", "groundHorizon"} & set(look)
    # pinned independently: golden hour #f4d2a6 × probe 0.5 × 0.8 in linear light
    assert runner.look_for(golden)["fogColor"] == "#a28b6d"
    assert runner.scale_linear("#ffffff", 1.0) == "#ffffff"
    assert runner.scale_linear("#808080", 0.5) == "#5c5c5c"


def test_sun_colour_ramps_continuously_between_the_rigs() -> None:
    """15°/6° steps gave December noon (14.0°) a warmer sun than June golden hour (15.2°)."""
    noon, golden, low = runner.SUN_NOON, runner.SUN_GOLDEN, runner.SUN_LOW
    assert runner.sun_light(30.0) == noon and runner.sun_light(60.9) == noon
    assert runner.sun_light(6.0) == golden and runner.sun_light(5.9) == low
    elevs = np.linspace(6.0, 29.99, 200)
    blue = [M.srgb_to_linear(runner.sun_light(e)[0])[2] for e in elevs]
    bright = [runner.sun_light(e)[1] for e in elevs]
    assert np.all(np.diff(blue) >= 0)   # cooler as the sun climbs: never a warm step up
    assert np.all(np.diff(bright) <= 0)
    near = runner.sun_light(29.99)      # continuous into the noon rig
    assert np.abs(M.srgb_to_linear(near[0]) - M.srgb_to_linear(noon[0])).max() < 0.01
    assert abs(near[1] - noon[1]) < 0.01
    dec, june_golden = runner.sun_light(14.04), runner.sun_light(15.23)
    assert M.srgb_to_linear(dec[0])[2] <= M.srgb_to_linear(june_golden[0])[2]
