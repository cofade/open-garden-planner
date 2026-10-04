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
    ProjectManager().load(scene, PLAN)
    return scene


def _board(scene, at: date) -> dict[str, list[tuple]]:
    """item id → [(mesh, kind, casts)] exactly as the spike would hand them to the engine."""
    rows: dict[str, list[tuple]] = defaultdict(list)

    def record(item_id, mesh, kind, casts):
        rows[item_id].append((mesh, kind, casts))
        return item_id

    runner.build_models(scene, at, 110.0, False, make_model=record)
    return rows


@pytest.fixture(scope="module")
def plan(qapp):  # noqa: ARG001 — a QApplication for the CanvasScene
    scene = _load()
    items = {str(i.item_id): i for i in scene.items()
             if hasattr(i, "item_id") and getattr(i, "object_type", None) is not None}
    return scene, items, {JUNE: _board(scene, JUNE), DECEMBER: _board(scene, DECEMBER)}


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
