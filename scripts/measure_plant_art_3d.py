"""Measure the 3D plant builder — the numbers its tests and documents state (Phase 17 L1.7, #385).

Every bound a plant test asserts, and every number §8.32.7 and the ADR-064 addendum "plant art v0"
quote, was MEASURED. This script is how; run it again after changing
``core/scene3d/builders/plants.py`` and move the numbers with the code.

The instruments are the unit tests' own (``tests/unit/test_scene3d_plants.py`` is loaded by path:
one definition of a side silhouette, of a height quantile, of the size matrix), so what is
measured here is exactly what is asserted there.

    venv/Scripts/python.exe scripts/measure_plant_art_3d.py truth --ids 3    # built to the data? (full sweep)
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py reach --ids 20   # where a plant ends (full sweep)
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py growth           # does a growing plant stay itself?
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py clones --ids 30  # how alike two ids are
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py shapes           # triangles and bytes per shape
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py scrub --days 180 # a date scrub, tick by tick
    venv/Scripts/python.exe scripts/measure_plant_art_3d.py cache            # the shape cache at its cap

The SWEEP (``truth``, ``reach``): every recipe of both tables × EVERY proportion step the tests
sweep (``SWEEP_STEPS``: height over canopy radius from 1 : 50 to 80 : 1 in 5 % steps) × N ids, a
different id in every cell. A shape depends on nothing but (recipe form, id, proportion step) — the
shape cache's key — so this is every kind of shape the builders can produce, not a sample of
sizes. (Round 1 measured "4,392 builds": 1,912 distinct shapes on 43 of the steps, and stated the
sample's maxima as bounds; three of them were wrong one proportion step further on.)

``truth``   per archetype: the builder's own top before the fit, what the fit repaired
            (``FitReport``), where the plant ends (``reach`` — bounded by construction — and how
            many plants the last step touched), where the foliage's mass is (z95 / z99, with the
            cell of the minimum), ground-flat triangles, the largest plant.
``reach``   the same sweep, the fit's report only (cheap: for many ids): the farthest vertex in
            canopy radii, its distribution, and how many plants the fit's last step reined in.
``growth``  the same id at every proportion step: how alike a plant is to itself one step on
            (side-silhouette IoU in the unit box), against two different ids at the same step.
``clones``  side-silhouette IoU of every pair of N ids per recipe, as a distribution.
``shapes``  the largest plant per archetype and what a remembered shape costs in bytes.
``scrub``   both bench plans, the plan date moved day by day: plants that change per tick, shapes
            rebuilt per tick, milliseconds warm and cold — and the same in units of a reference
            workload timed alongside (a shared machine slows everything down together).
``cache``   N growing plants against a cap that holds exactly M shapes: shapes rebuilt per tick
            at, one past and far past the cap.

Not part of the suite. ``scrub`` needs Qt (it loads plans into a scene); the others need numpy only.

ISOLATED FROM THE OWNER'S DATA, by itself (``isolate``, run at import, before any app import).
``scrub`` loads plans with ``ProjectManager.load``, and a load ends with ``add_recent_file`` — a
write to the app's settings, which outside pytest are the owner's real ones (on Windows the
registry key ``HKCU\\Software\\cofade\\Open Garden Planner``; no environment variable redirects
it). Until this script isolated itself, every ``scrub`` run put the two bench plans at the top of
the owner's recent-files list. It now does what ``tests/conftest.py`` does for the suite: the
settings names are rebound to a per-process test key (``cofade_test``), and USERPROFILE / HOME /
APPDATA / LOCALAPPDATA / XDG_* point at a temporary profile that is removed at exit. Pinned by
``tests/integration/test_scene3d_plants.py::test_the_measuring_script_keeps_out_of_the_owner_s_stores``.
"""

from __future__ import annotations

import argparse
import atexit
import contextlib
import dataclasses
import importlib.util
import os
import shutil
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))   # this checkout's package, whatever else is installed
sys.path.insert(0, str(REPO))           # ... and its tests package

#: The organisation of every test settings key (``tests/conftest.py`` uses the same).
TEST_ORGANIZATION = "cofade_test"
_SETTINGS_MODULE = "open_garden_planner.app.settings"
_PROFILE_VARIABLES = {
    "USERPROFILE": ("profile",),
    "HOME": ("profile",),
    "APPDATA": ("profile", "AppData", "Roaming"),
    "LOCALAPPDATA": ("profile", "AppData", "Local"),
    "XDG_DATA_HOME": ("xdg", "data"),
    "XDG_CONFIG_HOME": ("xdg", "config"),
    "XDG_CACHE_HOME": ("xdg", "cache"),
}


def isolate() -> Path | None:
    """Keep this process out of the owner's stores; return the temporary profile's root,
    or None when the process is isolated already (pytest's conftest, a probe helper).

    Two stores, two mechanisms — as ``tests/conftest.py``:

    - the SETTINGS (recent files, preferences): ``app.settings.ORGANIZATION_NAME`` /
      ``APPLICATION_NAME`` are rebound to a per-process test key, which is cleared at exit.
      Every settings backend of the app is built from those two names;
    - the app-data directory and Qt's standard locations (custom plants, logs, caches):
      the profile variables point at a temporary directory, removed at exit.

    Must run before anything of the app is used; this module calls it at import.
    """
    loaded = sys.modules.get(_SETTINGS_MODULE)
    if loaded is not None and loaded.ORGANIZATION_NAME == TEST_ORGANIZATION:
        return None
    root = Path(tempfile.mkdtemp(prefix=f"ogp-measure-{os.getpid()}-"))
    for variable, parts in _PROFILE_VARIABLES.items():
        directory = root.joinpath(*parts)
        directory.mkdir(parents=True, exist_ok=True)
        os.environ[variable] = str(directory)
    import open_garden_planner.app.settings as settings  # after the environment

    settings.ORGANIZATION_NAME = TEST_ORGANIZATION
    settings.APPLICATION_NAME = f"Open Garden Planner Measure {os.getpid()}"

    def forget() -> None:
        with contextlib.suppress(Exception):   # best effort while the interpreter exits
            settings.create_qsettings().clear()
        shutil.rmtree(root, ignore_errors=True)

    atexit.register(forget)
    return root


ISOLATED_PROFILE = isolate()

FIELDS = ("built_top", "z_scale", "xy_scale", "clamped_share", "clamped_reach", "pressed_share",
          "set_down", "centre_shift", "reach", "reined_share", "stretch")


def load(relative: str, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, REPO / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def instruments() -> ModuleType:
    return load("tests/unit/test_scene3d_plants.py", "plant_test_instruments")


def truth(args: argparse.Namespace) -> None:
    t = instruments()
    high: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(lambda: -1e9))
    low: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(lambda: 1e9))
    where: dict[tuple[str, str], str] = {}
    reined: dict[str, int] = defaultdict(int)
    builds: dict[str, int] = defaultdict(int)
    shapes: set[tuple[object, int, int]] = set()
    began = time.perf_counter()
    for sprite in t.ALL_SPRITES:
        recipe = t.recipe_of(sprite)
        form = t.plants._form(recipe)
        geometry = dataclasses.replace(form, palette="")      # the palette moves no vertex
        for step, seed, height, radius in t.sweep_cells(sprite, args.ids):
            parts = t.build_silhouette(recipe, seed, height, radius)
            report = t.fit_report(recipe, seed, height, radius)
            foliage = t.part(parts, t.PART_FOLIAGE).mesh
            z95, z99 = t.height_quantiles(foliage, (0.95, 0.99))
            values = {name: getattr(report, name) for name in FIELDS}
            values.update(z95=z95 / height, z99=z99 / height,
                          flat=float(t.ground_flat_triangles(foliage, height)),
                          triangles=float(t.triangles(parts)), mesh_reach=t.mesh_reach(parts, radius))
            shapes.add((geometry, seed, step))
            cell = f"{sprite.name} at step {step:+d} (h/r {height / radius:.3f}), seed {seed}"
            for key in (recipe["a"], "ALL"):
                builds[key] += 1
                reined[key] += int(report.reined_share > 0.0)
                for name, value in values.items():
                    if value > high[key][name]:
                        high[key][name] = value
                        where[(key, "max " + name)] = cell
                    if value < low[key][name]:
                        low[key][name] = value
                        where[(key, "min " + name)] = cell
        t.clear_shape_cache()
    steps = t.SWEEP_STEPS
    print(f"{builds['ALL']} builds = {len(t.ALL_SPRITES)} recipes x {len(steps)} proportion steps "
          f"({steps[0]:+d} .. {steps[-1]:+d}: h/r {t.PROPORTION_STEP ** steps[0]:.4f} .. "
          f"{t.PROPORTION_STEP ** steps[-1]:.1f}) x {args.ids} ids; {len(shapes)} distinct shapes; "
          f"{time.perf_counter() - began:.0f} s")
    print(f"\n{'archetype':9s}  builds  built top       xy scale  clamped   from    shift   pressed  set down  "
          f"REACH   reined plants   z95    z99    flat  triangles")
    for archetype in [*sorted(t.ARCHETYPES), "ALL"]:
        h, lo = high[archetype], low[archetype]
        print(f"{archetype:9s}  {builds[archetype]:6d}  {lo['built_top']:.4f}..{h['built_top']:.4f}  "
              f"{h['xy_scale']:.4f}    {100 * h['clamped_share']:.2f} %    {h['clamped_reach']:.4f}  "
              f"{h['centre_shift']:.4f}  {h['pressed_share']:.3f}    {h['set_down']:.3f}     "
              f"{h['mesh_reach']:.5f}  {reined[archetype]:5d} ({100 * reined[archetype] / builds[archetype]:.3f} %)  "
              f"{lo['z95']:.3f}  {lo['z99']:.3f}  {h['flat']:.0f}     {h['triangles']:.0f}")
    print("\nwhere the extremes are:")
    for archetype in sorted(t.ARCHETYPES):
        for name in ("min z95", "min z99", "max clamped_reach", "max centre_shift", "max xy_scale",
                     "max clamped_share"):
            print(f"  {archetype:9s} {name:18s} {where[(archetype, name)]}")
    print(f"\nREACH_MAX = {t.REACH_MAX}: the largest reach of a mesh, float32, is "
          f"{high['ALL']['mesh_reach']:.7f} canopy radii")


def reach(args: argparse.Namespace) -> None:
    t = instruments()
    seen: dict[str, list[float]] = defaultdict(list)
    before: dict[str, list[float]] = defaultdict(list)
    reined: dict[str, int] = defaultdict(int)
    worst: dict[str, tuple[float, str]] = {}
    began = time.perf_counter()
    for sprite in t.ALL_SPRITES:
        recipe = t.recipe_of(sprite)
        for step, seed, height, radius in t.sweep_cells(sprite, args.ids):
            report = t.fit_report(recipe, seed, height, radius)
            for key in (recipe["a"], "ALL"):
                seen[key].append(report.reach)
                reined[key] += int(report.reined_share > 0.0)
                before[key].append(100.0 * report.reined_share)
                if report.reined_share > worst.get(key, (0.0, ""))[0]:
                    worst[key] = (report.reined_share,
                                  f"{sprite.name} at step {step:+d}, seed {seed}")
        t.clear_shape_cache()
    count = len(seen["ALL"])
    print(f"{count} plants = {len(t.ALL_SPRITES)} recipes x {len(t.SWEEP_STEPS)} proportion steps x "
          f"{args.ids} ids; {time.perf_counter() - began:.0f} s; REACH_MAX = {t.REACH_MAX}")
    print(f"{'archetype':9s}  plants   farthest vertex / canopy radius: max      p99.9   p99     median   "
          f"plants reined in     most of one plant")
    for archetype in [*sorted(t.ARCHETYPES), "ALL"]:
        values = np.array(seen[archetype])
        share, cell = worst.get(archetype, (0.0, "-"))
        print(f"{archetype:9s}  {len(values):7d}                                    {values.max():.6f}  "
              f"{np.percentile(values, 99.9):.4f}  {np.percentile(values, 99):.4f}  {np.median(values):.4f}   "
              f"{reined[archetype]:6d} ({100 * reined[archetype] / len(values):.4f} %)   "
              f"{100 * share:.2f} % of its vertices: {cell}")


def growth(args: argparse.Namespace) -> None:
    t = instruments()
    steps = list(t.SWEEP_STEPS)
    ids = list(range(args.ids))
    print(f"{len(ids)} ids per archetype, every proportion step {steps[0]:+d} .. {steps[-1]:+d}; "
          f"side silhouettes in the unit box, so a pure change of proportion scores 1.0")
    print(f"{'archetype':9s}  the same id one step on: min    p01    p05    median  |  "
          f"another id at the same step: median  p95")
    for archetype in sorted(t.ARCHETYPES):
        adjacent, other = [], []
        for seed in ids:
            previous = None
            for step in steps:
                height = 100.0 * t.PROPORTION_STEP ** step
                grid = t.side_silhouette(t.build_silhouette({"a": archetype}, t.plant_seed(f"grow-{seed}"),
                                                            height, 100.0), height, 100.0)
                if previous is not None:
                    adjacent.append(t.silhouette_iou(previous, grid))
                previous = grid
                if step % 6 == 0:
                    twin = t.side_silhouette(t.build_silhouette(
                        {"a": archetype}, t.plant_seed(f"grow-{seed}-twin"), height, 100.0), height, 100.0)
                    other.append(t.silhouette_iou(grid, twin))
            t.clear_shape_cache()
        a, o = np.array(adjacent), np.array(other)
        print(f"{archetype:9s}                           {a.min():.3f}  {np.percentile(a, 1):.3f}  "
              f"{np.percentile(a, 5):.3f}  {np.median(a):.3f}   |                               "
              f"{np.median(o):.3f}   {np.percentile(o, 95):.3f}")


def cache(args: argparse.Namespace) -> None:
    t = instruments()
    recipe = t.SPECIES["leek"]                       # an allium: every id's shape has the same size
    fit = args.fit
    plants = [(recipe, t.plant_seed(f"cache-{n}"), 80.0, 10.0) for n in range(4 * fit)]
    one = t.shape_bytes(*plants[0])
    t.resize_shape_cache(fit * one)
    try:
        print(f"a cap of {fit * one:,} bytes = exactly {fit} shapes of {one:,} bytes; "
              f"one tick asks for every plant once, in the same order")
        print("plants  shapes built per tick (ticks 1 .. 6)        seconds per warm tick")
        for count in (fit - 1, fit, fit + 1, fit + fit // 10, 2 * fit, 4 * fit):
            t.clear_shape_cache()
            built, took = [], []
            for _tick in range(6):
                misses = t.shape_cache_info().misses
                began = time.perf_counter()
                for plant in plants[:count]:
                    t.build_silhouette(*plant)
                took.append(time.perf_counter() - began)
                built.append(t.shape_cache_info().misses - misses)
            print(f"{count:6d}  {str(built):44s} {statistics.median(took[1:]):.3f}   "
                  f"(held {t.shape_cache_info().shapes})")
    finally:
        t.resize_shape_cache()
        t.clear_shape_cache()


def clones(args: argparse.Namespace) -> None:
    t = instruments()
    ids = [f"clone-{n}" for n in range(args.ids)]
    values: dict[str, list[float]] = defaultdict(list)
    worst: dict[str, tuple[float, str]] = {}
    for sprite in t.ALL_SPRITES:
        recipe = t.recipe_of(sprite)
        height, spread = t.MATURE[sprite]
        radius = spread / 2.0
        grid = np.array([t.side_silhouette(t.build_silhouette(recipe, t.plant_seed(seed), height, radius),
                                           height, radius).reshape(-1) for seed in ids], np.float64)
        shared = grid @ grid.T
        area = grid.sum(axis=1)
        pairs = (shared / (area[:, None] + area[None, :] - shared))[np.triu_indices(len(ids), 1)]
        values[recipe["a"]].extend(pairs.tolist())
        if pairs.max() > worst.get(recipe["a"], (0.0, ""))[0]:
            worst[recipe["a"]] = (float(pairs.max()), sprite.name)
    print(f"{args.ids} ids per recipe, at its mature size")
    print(f"{'archetype':9s}  pairs    max    p99    p95    median  above 0.97  above 0.95  most alike")
    rows = [*sorted(values.items()), ("ALL", [v for group in values.values() for v in group])]
    for archetype, group in rows:
        alike = np.array(group)
        print(f"{archetype:9s}  {len(alike):6d}  {alike.max():.3f}  {np.percentile(alike, 99):.3f}  "
              f"{np.percentile(alike, 95):.3f}  {np.median(alike):.3f}   {100 * (alike > 0.97).mean():6.2f} %    "
              f"{100 * (alike > 0.95).mean():6.2f} %   {worst.get(archetype, (0, ''))[1]}")


def shapes(_args: argparse.Namespace) -> None:
    t = instruments()
    triangles: dict[str, int] = defaultdict(int)
    held = []
    for sprite in t.ALL_SPRITES:
        recipe = t.recipe_of(sprite)
        for height, radius in t.sizes_of(sprite).values():
            for seed in t.SEEDS:
                count = t.triangles(t.build_silhouette(recipe, t.plant_seed(seed), height, radius))
                triangles[recipe["a"]] = max(triangles[recipe["a"]], count)
        height, spread = t.MATURE[sprite]
        held.append(t.shape_bytes(recipe, 1, height, spread / 2.0))
    print("largest plant per archetype (every recipe x six sizes x five ids), triangles:")
    print("  " + ", ".join(f"{a} {n:,}" for a, n in sorted(triangles.items(), key=lambda kv: -kv[1])))
    print(f"a remembered shape (123 recipes at mature size): min {min(held):,} bytes, "
          f"mean {sum(held) / len(held):,.0f}, max {max(held):,}")
    cap = t.SHAPE_CACHE_BYTES
    print(f"the cache holds {cap / 2**20:.0f} MB: {cap / max(held):,.0f} of the largest shapes, "
          f"{cap * len(held) / sum(held):,.0f} average ones")


def scrub(args: argparse.Namespace) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from open_garden_planner.core import ProjectManager
    from open_garden_planner.ui.canvas.canvas_scene import CanvasScene
    from open_garden_planner.ui.view3d.snapshot import snapshot_records

    budget = load("tests/perf/test_scene3d_plants_budget.py", "plant_budget_instruments")
    start = date.fromisoformat(args.start)
    days = [start + timedelta(days=n) for n in range(args.days + 1)]
    from open_garden_planner.app import settings

    store = settings.create_qsettings()
    assert store.organizationName() == TEST_ORGANIZATION, (
        f"refusing to load a plan: the settings store is {store.organizationName()!r} / "
        f"{store.applicationName()!r}, not a test key — a load would write the owner's recent files")
    print(f"settings key: {store.organizationName()} / {store.applicationName()} (not the owner's)")
    print(f"{args.days} daily ticks from {start}; reference unit {budget.unit_ms():.0f} ms right now")
    for name in sorted(budget.BUDGETS):
        scene = CanvasScene()
        ProjectManager().load(scene, budget.PLANS / name)
        took = time.perf_counter()
        snapshots = [budget.plants_of(snapshot_records(scene, day)) for day in days]
        snapshot_ms = (time.perf_counter() - took) * 1000.0 / len(days)
        print(f"\n{name}: {len(snapshots[0])} plants; snapshot_records {snapshot_ms:.1f} ms a day "
              f"(all records of the plan, not only plants)")
        for mode in ("warm", "cold"):
            unit = budget.unit_ms()
            budget.clear_shape_cache()
            sync = budget.SceneSync(budget.RecordingSink(), budget.plant_registry())
            sync.apply(snapshots[0])
            times, changed, built = [], [], []
            for records in snapshots[1:]:
                if mode == "cold":
                    budget.clear_shape_cache()
                misses, builds = budget.shape_cache_info().misses, sync.build_count
                began = time.perf_counter()
                sync.apply(records)
                times.append((time.perf_counter() - began) * 1000.0)
                changed.append(sync.build_count - builds)
                built.append(budget.shape_cache_info().misses - misses)
            unit = statistics.median([unit, budget.unit_ms()])
            ordered = sorted(times)
            print(f"  {mode}: {statistics.mean(changed):5.1f} plants change per tick (max {max(changed)}), "
                  f"{statistics.mean(built):5.1f} shapes built per tick (max {max(built)}); "
                  f"median {statistics.median(times):6.1f} ms, p95 {ordered[int(0.95 * (len(ordered) - 1))]:6.1f}, "
                  f"max {ordered[-1]:6.1f} = {statistics.median(times) / unit:.3f} units of {unit:.0f} ms")
    del app


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("truth")
    sub.add_argument("--ids", type=int, default=3)
    sub.set_defaults(run=truth)
    sub = commands.add_parser("reach")
    sub.add_argument("--ids", type=int, default=20)
    sub.set_defaults(run=reach)
    sub = commands.add_parser("growth")
    sub.add_argument("--ids", type=int, default=6)
    sub.set_defaults(run=growth)
    sub = commands.add_parser("cache")
    sub.add_argument("--fit", type=int, default=200)
    sub.set_defaults(run=cache)
    sub = commands.add_parser("clones")
    sub.add_argument("--ids", type=int, default=30)
    sub.set_defaults(run=clones)
    commands.add_parser("shapes").set_defaults(run=shapes)
    sub = commands.add_parser("scrub")
    sub.add_argument("--days", type=int, default=180)
    sub.add_argument("--start", default="2026-04-01")
    sub.set_defaults(run=scrub)
    args = parser.parse_args()
    args.run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
