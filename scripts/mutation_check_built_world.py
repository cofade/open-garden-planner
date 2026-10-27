"""Mutation check for the built world and the base rule (Phase 17 L1.6, #385).

The sibling of ``mutation_check_scene3d.py``, for the rules this story owns: where
an item stands (``ui/canvas/footprints.item_base_cm``), the shared 2D caster
(``core/shadow_geometry``), the soil rule (``core/object_height``) and the
production builders (``core/scene3d/builders/``).

A green suite says the tests pass. It does not say they would FAIL if the code
were wrong. Every rule below was found missing, or wrong, by a review while all
tests were green; this script switches ONE of them off at a time and runs the
tests that are supposed to notice.

Verdicts:

KILLED    pytest exited with code 1 and named a failed test. The only good one.
SURVIVED  pytest exited with 0: no test pins the rule.
BROKEN    any other exit code (a collection error, a usage error, a crash), or
          exit 1 without a failed test (a fixture error): the mutant did not
          run as a test failure, so it proves nothing. Counts as not killed.
STALE     the text to replace is not found exactly once: the mutant no longer
          mutates anything. Counts as not killed.

How it works: each mutant is one textual replacement in one file. The file is
restored from an in-memory copy in a ``finally`` block, and the script refuses
to start when ``src/`` or ``scripts/`` has uncommitted changes — so a crash can
never be mistaken for your work, and ``git checkout -- src scripts`` is always a
safe way back. The test runs get a throw-away ``APPDATA``: they never write to
the application's real data folder. Nor does anything here reach the owner's
settings: this script imports the standard library only — no module of the app runs
in its process — and every child it starts is pytest, which ``tests/conftest.py``
isolates before any app import (both held by
``tests/unit/test_scene3d_builders_mutation_script.py``).

It is NOT part of the test suite (it rewrites source files and takes several
minutes). Run it by hand after changing the files named above, or their tests::

    venv/Scripts/python.exe scripts/mutation_check_built_world.py            # all mutants
    venv/Scripts/python.exe scripts/mutation_check_built_world.py --list     # names only
    venv/Scripts/python.exe scripts/mutation_check_built_world.py -k badge   # a subset

Exit code 0: every mutant killed. 1: a mutant survived, broke or is stale. 2: refused.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = "src/open_garden_planner/"
BUILDERS = SRC + "core/scene3d/builders/"
U = "tests/unit/"
I = "tests/integration/"  # noqa: E741  (a path prefix, read next to U)

STACKING = I + "test_scene3d_base_stacking.py"
CASTER = U + "test_shadow_caster_base.py"
BUILDER_TESTS = U + "test_scene3d_builders.py"
BUILT_WORLD = I + "test_scene3d_built_world.py"
PRIMITIVES = U + "test_scene3d_builders_primitives.py"
PALETTE = U + "test_scene3d_builders_palette.py"
SHADOWS = U + "test_scene3d_shadow_agreement.py"

#: The geometric centre of a plant, written out — what a link decision must NOT ask.
_RECT_CENTRE = "item.mapToScene(item.rect().center())"


@dataclass(frozen=True)
class Mutant:
    """One broken rule: replace ``old`` with ``new`` in ``path``; ``tests`` (narrowed
    by ``select``, a pytest ``-k`` expression) must fail."""

    label: str
    path: str
    old: str
    new: str
    tests: tuple[str, ...]
    select: str = ""


MUTANTS: tuple[Mutant, ...] = (
    # ── where an item stands (ADR-037 addendum, decision 5) ─────────────────
    Mutant("the link alone lifts (round 0: a bed shrunk away leaves a plant casting from 38 cm)",
           SRC + "ui/canvas/footprints.py",
           # the geometric test lives in ``standing_parent`` since the merge of master's
           # US-F3 (L1.3 fix round 1): ``item_base_cm`` is built on it
           "    if point is None or not shape_contains(parent, point, lookup.shape_of(parent)):\n"
           "        return None\n    return parent\n",
           "    return parent\n",
           (STACKING,), "TestTheLinkAloneNeverLifts"),
    Mutant("the lift asks the link decisions' point (round 1: a badge moves a plant off its soil)",
           SRC + "ui/canvas/footprints.py",
           "    point = standing_point(item)\n",
           "    point = bed_membership_point(item)\n",
           (STACKING,), "TestWhereAPlantStandsDoesNotDependOnABadge or TestWhichPointEachDecisionAsks"),
    Mutant("every link decision asks the stable centre (shipped parenting behaviour changes)",
           SRC + "ui/canvas/footprints.py",
           "    point: QPointF = item.mapToScene(item.boundingRect().center())\n",
           "    point: QPointF = item.mapToScene(item.rect().center())\n",
           (STACKING,), "TestWhichPointEachDecisionAsks"),
    Mutant("auto-parenting (create, bulk create, paste) asks the stable centre",
           SRC + "core/commands.py",
           "    plant_center = bed_membership_point(item)\n",
           f"    plant_center = {_RECT_CENTRE}\n",
           (STACKING,), "TestWhichPointEachDecisionAsks"),
    Mutant("the drop after a drag asks the stable centre",
           SRC + "ui/canvas/canvas_view.py",
           "            plant_center = bed_membership_point(item)\n",
           f"            plant_center = {_RECT_CENTRE}\n",
           (STACKING,), "TestWhichPointEachDecisionAsks"),
    Mutant("the agent's re-link after move_object asks the stable centre",
           SRC + "app/application.py",
           "        plant_center = bed_membership_point(item)\n",
           f"        plant_center = {_RECT_CENTRE}\n",
           (STACKING,), "TestWhichPointEachDecisionAsks"),
    Mutant("set_parent_bed's link_is_geometric asks the stable centre",
           SRC + "app/application.py",
           "            link_is_geometric = centre_is_inside(plant, bed)\n",
           "            link_is_geometric = bool(bed.contains(bed.mapFromScene(\n"
           "                plant.mapToScene(plant.rect().center()))))\n",
           (STACKING,), "TestWhichPointEachDecisionAsks"),
    Mutant("the walk's shape of a parent is its bounding rectangle",
           SRC + "ui/canvas/footprints.py",
           "    path: QPainterPath = parent.clipPath() if parent.isClipped() else parent.shape()\n"
           "    return path\n",
           "    path = QPainterPath()\n    path.addRect(parent.boundingRect())\n    return path\n",
           (STACKING,), "TestTheParentShapeIsBuiltOncePerWalk"),
    Mutant("the parent's shape is rebuilt for every plant",
           SRC + "ui/canvas/footprints.py",
           "        shape = self._shapes.get(key)\n",
           "        shape = None\n",
           (STACKING,), "TestTheParentShapeIsBuiltOncePerWalk"),
    Mutant("a second containment test, written in two statements, goes unnoticed",
           SRC + "ui/canvas/canvas_scene.py",
           "            if shape_contains(item, scene_point):\n",
           "            local = item.mapFromScene(scene_point)\n"
           "            if item.contains(local):\n",
           (STACKING,), "one_point_in_bed_predicate"),
    Mutant("a plant keeps its base when its parent got no record (38 cm over nothing)",
           SRC + "ui/view3d/snapshot.py",
           "    _ground_items_without_a_parent_record(records)\n    return records\n",
           "    return records\n",
           (STACKING,), "without_a_record or stacked_higher"),
    # ── the shared 2D caster ────────────────────────────────────────────────
    Mutant("a bare 3-tuple is a caster again (round 0)",
           SRC + "core/shadow_geometry.py",
           "    if type(caster) is tuple and len(caster) == 2:\n        return caster[0], caster[1], 0.0\n",
           "    if type(caster) is tuple and len(caster) >= 2:\n"
           "        return caster[0], caster[1], (caster[2] if len(caster) > 2 else 0.0)\n",
           (CASTER,), "TestACasterIsATypeNotALength"),
    Mutant("the heatmap's worker drops the base",
           SRC + "core/shadow_geometry.py",
           "            start = base_offset_cm(base, elevation_deg)\n",
           "            start = 0.0\n",
           (STACKING,), "TestHeatmapEndToEnd"),
    Mutant("the overlay's union drops the base",
           SRC + "core/shadow_geometry.py",
           "            footprint, length, direction, base_offset_cm(base_cm, elevation_deg)))\n",
           "            footprint, length, direction, 0.0))\n",
           (CASTER,), "test_and_a_base_really_is_a_different_shadow"),
    # ── the soil rule ───────────────────────────────────────────────────────
    Mutant("a container's soil is 2 cm under its height again (round 0)",
           SRC + "core/object_height.py",
           "    if _type_name(object_type) in _CONTAINER_TYPE_NAMES:\n        return height_cm\n"
           "    return max(height_cm - SOIL_DROP_CM, 0.0)\n",
           "    return max(height_cm - SOIL_DROP_CM, 0.0)\n",
           (CASTER, BUILDER_TESTS, STACKING),
           "container_s_soil or soil_is_where_plants_stand or 3d_base_and_2d_caster or no_lip"),
    Mutant("a parent taller than the scene can hold lifts its plant (it floats over nothing)",
           SRC + "core/object_height.py",
           "            or height_cm > MAX_PARENT_HEIGHT_CM):\n",
           "            or height_cm > math.inf):\n",
           (CASTER, STACKING), "taller_than_the_scene or cannot_hold"),
    # ── corners ─────────────────────────────────────────────────────────────
    Mutant("offset_ring never bevels (round 0: a 116 cm eave spike)",
           BUILDERS + "primitives.py",
           "    bevel = _sharp(before, outward) & (distance * _cross(arriving, edge) > 0.0)\n",
           "    bevel = _sharp(before, outward) & (distance * _cross(arriving, edge) > 1e300)\n",
           (BUILDER_TESTS, PRIMITIVES), "TestAcuteCorners or sharper_corner or acute-triangle"),
    Mutant("sweep never bevels (round 0: a 76 cm spike of coping)",
           BUILDERS + "primitives.py",
           "    sharp = _sharp(before, after)\n",
           "    sharp = _sharp(before, after) & False\n",
           (BUILDER_TESTS, PRIMITIVES),
           "TestAcuteCorners or hairpin or sharp_bend or closed_loop_with_an_acute"),
    Mutant("sweep bevels the inside of the bend",
           BUILDERS + "primitives.py",
           "    outside = sharp[:, None] & (lateral[None, :] * _cross(coming, going)[:, None] < 0.0)  # (m, p)\n",
           "    outside = sharp[:, None] & (lateral[None, :] * _cross(coming, going)[:, None] > 0.0)  # (m, p)\n",
           (BUILDER_TESTS, PRIMITIVES), "TestAcuteCorners or hairpin or sharp_bend"),
    Mutant("the inside mitre is cut at two offsets (the short-leg bound is not the pinned one)",
           BUILDERS + "primitives.py",
           "MITER_LIMIT: Final = 4.0\n",
           "MITER_LIMIT: Final = 2.0\n",
           (BUILDER_TESTS, PRIMITIVES), "shorter_than_the_section or depends_on_the_legs"),
    # ── what a line is built as ─────────────────────────────────────────────
    Mutant("an unknown style is a picket fence (round 0)",
           BUILDERS + "lines.py",
           "    if fences.is_fence_style(style):\n        return str(style)\n    return fences.PLAIN\n",
           "    if fences.is_fence_style(style):\n        return str(style)\n"
           "    return DEFAULT_SOLID.get(record.kind, fences.PLAIN)\n",
           (BUILDER_TESTS,), "plain_panel or which_solid"),
    Mutant("a fence style goes missing from the mirror",
           BUILDERS + "fences.py",
           '    {"WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "HEDGE_FENCE", "STONE_WALL"}\n',
           '    {"WOODEN_FENCE", "METAL_FENCE", "CHAIN_LINK", "STONE_WALL"}\n',
           (PALETTE,), "fence_styles or solid_of_its_own"),
    Mutant("the plain panel is as thick as a post",
           BUILDERS + "fences.py",
           "    return max(record.path_width_cm or 0.0, PLAIN_MIN_WIDTH_CM)\n",
           "    return max(record.path_width_cm or 0.0, POST_CM)\n",
           (BUILDER_TESTS,), "plain_panel or TestGateG1"),
    Mutant("an unknown style is reported on every build",
           BUILDERS + "lines.py",
           "    if style is None or name in _reported_styles:\n        return\n",
           "    if style is None:\n        return\n",
           (BUILDER_TESTS,), "reported_once_per_name"),
    Mutant("the warning memory starts over when it is full (65 names: 65 lines per rebuild pass)",
           BUILDERS + "lines.py",
           "        if _NO_MORE not in _reported_styles:\n"
           "            _reported_styles.add(_NO_MORE)\n",
           "        _reported_styles.clear()\n"
           "        if _NO_MORE not in _reported_styles:\n"
           "            _reported_styles.add(_NO_MORE)\n",
           (BUILDER_TESTS,), "memory_of_reported"),
    Mutant("an unknown style is built plain without a word",
           BUILDERS + "lines.py",
           "    if solid == fences.PLAIN:\n        _report_plain(record)\n",
           "",
           (BUILDER_TESTS,), "reported"),
    # ── ground that is not one plain ring ───────────────────────────────────
    Mutant("the plain block is the first ring only (round 0's house block)",
           BUILDERS + "common.py",
           "    mesh = prism_mesh(record.footprints, height_cm, record.holes)\n",
           "    mesh = prism_mesh(record.footprints[:1], height_cm)\n",
           (BUILDER_TESTS,), "TestGroundThatIsNotOnePlainRing"),
    Mutant("a shape function runs on ground that is not one plain ring",
           BUILDERS + "common.py",
           "        if self.uses_the_plain_block(record):\n            return plain_block(record, height)\n",
           "",
           (BUILDER_TESTS,), "TestGroundThatIsNotOnePlainRing"),
    Mutant("footprint_of hands out the first ring whatever the ground",
           BUILDERS + "common.py",
           "    if not has_one_plain_ring(record):\n        resolved = ",
           "    if False:\n        resolved = ",
           (BUILDER_TESTS,), "TestGroundThatIsNotOnePlainRing"),
    Mutant("a resolved outline that is one ring is built as its kind (a roof on a self-crossing house)",
           BUILDERS + "common.py",
           "    return (len(record.footprints) == 1 and not any(record.holes)\n"
           "            and not record.params.get(PARAM_OUTLINE_RESOLVED))\n",
           "    return len(record.footprints) == 1 and not any(record.holes)\n",
           (BUILDER_TESTS, BUILT_WORLD), "resolved_outline or TestAResolvedOutlineGetsNoRoof"),
    # ── seeds ───────────────────────────────────────────────────────────────
    Mutant("a hedge seeded from numpy's default generator",
           BUILDERS + "hedges.py",
           "    rng = np.random.Generator(np.random.PCG64(seed))\n",
           "    rng = np.random.default_rng(seed)\n",
           (BUILDER_TESTS,), "bit_generator"),
    # ── the 3D-against-2D shadow measurement ────────────────────────────────
    Mutant("the measurement reports no reach (every tip 'agrees')",
           "scripts/measure_built_world_shadows.py",
           "            reaches.append(reach_cm(in_3d, case.azimuth_deg) - reach_cm(in_2d, case.azimuth_deg))\n",
           "            reaches.append(0.0)\n",
           (SHADOWS,)),
    Mutant("a house's roof overhangs twice as far (a builder moves a tip by 30 cm)",
           BUILDERS + "buildings.py",
           "    overhang_cm=30.0, pitch_deg=38.0,\n",
           "    overhang_cm=60.0, pitch_deg=38.0,\n",
           (SHADOWS,)),
    # ── the production registry (the merge of the plant story) ──────────────
    Mutant("the plant builder is not in the production registry (every plant a prism again)",
           BUILDERS + "__init__.py",
           "    register(registry)\n    plants.register(registry)\n",
           "    register(registry)\n",
           (BUILDER_TESTS, BUILT_WORLD), "TestRegistration or two_real_plants"),
)


def verdict_of(returncode: int, a_test_failed: bool) -> str:
    """pytest: 0 all passed, 1 tests failed, 2 interrupted (a collection error among
    them), 3 internal error, 4 usage error (a test id that does not exist), 5 no
    tests collected. A kill is exit 1 WITH a failed test; exit 1 without one is a
    fixture or collection error."""
    if returncode == 0:
        return "SURVIVED"
    return "KILLED" if returncode == 1 and a_test_failed else "BROKEN"


def run(mutant: Mutant, appdata: str) -> tuple[str, str]:
    """``(verdict, detail)`` — KILLED, SURVIVED, BROKEN or STALE."""
    path = REPO / mutant.path
    original = path.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    if text.count(mutant.old) != 1:
        return "STALE", f"pattern found {text.count(mutant.old)}x in {mutant.path}"
    command = [sys.executable, "-m", "pytest", *mutant.tests, "-q", "-x", "-n", "0", "-p", "no:cacheprovider"]
    if mutant.select:
        command += ["-k", mutant.select]
    try:
        path.write_text(text.replace(mutant.old, mutant.new), encoding="utf-8", newline="")
        proc = subprocess.run(
            command, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=1800, check=False, env={**os.environ, "APPDATA": appdata},
        )
    finally:
        path.write_bytes(original)
    lines = proc.stdout.strip().splitlines()
    tail = lines[-1] if lines else proc.stderr.strip()[-200:]
    failed = next((line for line in lines if line.startswith("FAILED tests")), "")
    verdict = verdict_of(proc.returncode, bool(failed))
    if verdict == "BROKEN":
        return verdict, f"pytest exit {proc.returncode}: {tail[:140]}"
    return verdict, (failed[:160] if verdict == "KILLED" else tail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--list", action="store_true", help="print the mutants and exit")
    parser.add_argument("-k", metavar="TEXT", default="", help="only mutants whose label contains TEXT")
    args = parser.parse_args(argv)
    chosen = [m for m in MUTANTS if args.k.lower() in m.label.lower()]
    if args.list:
        for mutant in chosen:
            print(f"{mutant.label}  [{mutant.path}]")
        print(f"{len(chosen)} mutants")
        return 0
    dirty = subprocess.run(["git", "-C", str(REPO), "status", "--porcelain", "--", "src", "scripts"],
                           capture_output=True, text=True, check=False).stdout.strip()
    if dirty:
        print("refusing to run: src/ or scripts/ has uncommitted changes "
              "(this script rewrites source files)\n" + dirty)
        return 2
    not_killed = 0
    with tempfile.TemporaryDirectory(prefix="ogp-mutation-appdata-") as appdata:
        for mutant in chosen:
            verdict, detail = run(mutant, appdata)
            not_killed += verdict != "KILLED"
            print(f"{verdict:<8} {mutant.label}  [{detail}]", flush=True)
    print(f"{len(chosen) - not_killed}/{len(chosen)} mutants killed")
    return 1 if not_killed else 0


if __name__ == "__main__":
    raise SystemExit(main())
