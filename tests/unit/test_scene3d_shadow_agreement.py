"""The built world's 3D shadows against the 2D shadow model (Phase 17 L1.6, review
round 1, P1-3; the reach column: review round 2, P1).

``scripts/measure_built_world_shadows.py`` projects every built-world mesh onto the
ground along the sun ray and compares it with what the 2D sun & shade model casts
for the same item. This file runs that measurement and holds the builders to the
table the docs quote (ADR-059's builders addendum, §8.29.6, FR-SUN-11,
``ogp-lush-cinematic`` §1 "Shadows") — within ``TOLERANCE`` (0.05; a reach within
``REACH_TOLERANCE_CM``, 1 cm), so a builder change that moves a kind by a tenth of
an IoU or a tip by a centimetre fails here and takes the docs with it.

It also states the RULE the table is an instance of, kind by kind:

- where 3D builds the solid the 2D model casts — a bed, a box, a plain panel — the
  two shadows are the same (IoU >= 0.99): the truth gate's own case;
- a picket, metal or chain-link fence is mostly air: its 3D shadow lies INSIDE the
  2D one and is a fraction of it — the 2D sun study over-shades behind such a
  fence, and the 3D view will show sun where the hours-of-sun map shows shade;
- a wall, a stone-wall fence and a hedge fence have a nominal section the plan does
  not hold: their 3D shadow is the WIDER one, more so the higher the sun.

And WHERE THE TIP IS (the reach along the shadow direction, 3D minus 2D). Round 1
wrote "shadow length and tip always agree (the height is exact)" into the truth-gate
row. The height is the same number in both models — but the tip is cast by the
highest EDGE, and a gable's ridge stands mid-house where the 2D prism's top edge is
at the far wall: 270 cm short on the bench house. No sentence about shadows goes
next to the gate unless this script prints the number behind it; the doc tests at
the end hold every copy of the table to the script's.
"""

from __future__ import annotations

import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "measure_built_world_shadows.py"
PRISMS = ("raised bed", "container (box)", "plain panel (unknown style)")
POTS = ("terracotta pot", "round tub")
POROUS = ("chain-link fence", "metal fence", "picket fence")  # least solid first
NOMINAL_SECTION = ("wall", "stone-wall fence", "hedge fence")
HEDGES = ("hedge (polygon)", "hedge (section)")
GABLE_SQUARE = ("house, sun square to the ridge", "shed, sun square to the ridge")
ADR = ROOT / "docs" / "09-architecture-decisions" / "README.md"
CONCEPTS = ROOT / "docs" / "08-crosscutting-concepts" / "README.md"
SKILLS = tuple(ROOT / tree / "skills" / "ogp-lush-cinematic" / "SKILL.md"
               for tree in (".claude", ".agents"))


@cache
def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("measure_built_world_shadows_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@cache
def _rows() -> dict[str, object]:
    return {row.name: row for row in _script().measure()}


def test_the_measurement_matches_the_documented_table() -> None:
    script = _script()
    assert script.TOLERANCE == 0.05 and script.ELEVATIONS_DEG == (15.0, 35.0, 60.0)
    assert script.REACH_TOLERANCE_CM == 1.0
    assert script.drift(tuple(_rows().values())) == []
    assert set(_rows()) == set(script.DOCUMENTED) and len(script.DOCUMENTED) == 24
    for ratio, iou, reach in script.DOCUMENTED.values():
        assert len(ratio) == len(iou) == len(reach) == 3


def test_the_drift_check_can_fail() -> None:
    """A row that moved by a tenth is reported; so is a tip that moved by two
    centimetres; so is a missing case."""
    script = _script()
    rows = list(_rows().values())
    first = rows[0]
    moved = script.Row(first.name, first.why, tuple(value + 0.1 for value in first.ratio),
                       first.iou, first.reach_cm)
    assert script.drift([moved, *rows[1:]]) == [
        f"{first.name} at {elevation:g} deg: area ratio {value + 0.1:.2f}, documented {documented:.2f}"
        for elevation, value, documented in zip(
            script.ELEVATIONS_DEG, first.ratio, script.DOCUMENTED[first.name][0], strict=True)
    ]
    shifted = script.Row(first.name, first.why, first.ratio, first.iou,
                         (first.reach_cm[0] + 2.0, *first.reach_cm[1:]))
    (problem,) = script.drift([shifted, *rows[1:]])
    assert problem.startswith(f"{first.name} at 15 deg: reach ") and "documented" in problem
    within = script.Row(first.name, first.why, first.ratio, first.iou,
                        tuple(value + 0.4 for value in first.reach_cm))
    assert script.drift([within, *rows[1:]]) == []
    assert script.drift(rows[1:])[0].startswith("cases differ")


@pytest.mark.parametrize("name", PRISMS)
def test_a_prism_casts_the_shadow_the_2d_model_casts(name: str) -> None:
    row = _rows()[name]
    assert min(row.iou) >= 0.99  # type: ignore[attr-defined]
    assert all(abs(value - 1.0) <= 0.01 for value in row.ratio)  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", POROUS)
def test_a_porous_fence_casts_less_in_3d_than_the_2d_model_says(name: str) -> None:
    row = _rows()[name]
    assert max(row.ratio) < 0.75  # type: ignore[attr-defined]
    # its 3D shadow lies inside the 2D strip's: the IoU IS the area ratio (the posts,
    # wider than the stroke, stick out by a hair)
    for ratio, iou in zip(row.ratio, row.iou, strict=True):  # type: ignore[attr-defined]
        assert iou <= ratio + 1e-9 and ratio - iou <= 0.03


def test_the_porous_fences_in_order() -> None:
    chain, metal, picket = (_rows()[name] for name in POROUS)
    for index in range(3):
        assert chain.ratio[index] < metal.ratio[index] < picket.ratio[index]  # type: ignore[attr-defined]
    assert max(chain.ratio) < 0.25  # type: ignore[attr-defined]
    # the number an owner will notice: behind a chain-link fence the hours-of-sun map
    # shows full shade where the 3D fence lets more than four fifths of the sun through
    assert 1.0 - max(chain.ratio) > 0.8  # type: ignore[attr-defined]


@pytest.mark.parametrize("name", NOMINAL_SECTION)
def test_a_nominal_section_casts_a_wider_shadow_the_higher_the_sun(name: str) -> None:
    row = _rows()[name]
    assert row.ratio[0] < row.ratio[1] < row.ratio[2]  # type: ignore[attr-defined]
    assert min(row.ratio) > 1.0  # type: ignore[attr-defined]
    # over the box gate at a low sun, under it at a high one
    assert row.iou[0] >= BOX_GATE_IOU > row.iou[2]  # type: ignore[attr-defined]


#: The truth gate "Shadows" of ``ogp-lush-cinematic`` §1: IoU of a BOX caster's engine
#: shadow against the analytic 2D shadow.
BOX_GATE_IOU = 0.85


def test_which_kinds_meet_the_box_gate_at_every_elevation() -> None:
    """The truth gate (IoU >= 0.85) is defined on a solid box caster. Which built-world
    kinds would meet it at all three elevations is a fact the 3D reviewer needs before
    measuring: the prisms, the two hedges and the round tub — no building, no terracotta
    pot, no wall and no styled fence."""
    meets = {name for name, row in _rows().items() if min(row.iou) >= BOX_GATE_IOU}  # type: ignore[attr-defined]
    assert meets == {*PRISMS, "hedge (polygon)", "hedge (section)", "round tub",
                     "house, flat roof", "house, single-slope roof"}  # L4's roofs (#388)
    below = {name: min(row.iou) for name, row in _rows().items() if name not in meets}  # type: ignore[attr-defined]
    assert max(below.values()) < BOX_GATE_IOU - 0.01  # none of the others is a borderline case


# ── where the tip is: the reach column (review round 2, P1) ──────────────────


def _reach(name: str) -> tuple[float, float, float]:
    reach: tuple[float, float, float] = _rows()[name].reach_cm  # type: ignore[attr-defined]
    return reach


def test_the_reach_is_measured_along_the_shadow_direction() -> None:
    """``reach_cm`` is the tip's position along the shadow direction: for the raised
    bed (a 300 x 120 cm prism, 40 cm high, the sun due south) the 2D shadow ends
    ``60 + 40 / tan a`` north of its centre."""
    script = _script()
    case = next(case for case in script.cases() if case.name == "raised bed")
    for elevation in script.ELEVATIONS_DEG:
        tip = script.reach_cm(script.caster_shadow(case.record, elevation, case.azimuth_deg),
                              case.azimuth_deg)
        assert tip == pytest.approx(60.0 + 40.0 / math.tan(math.radians(elevation)), abs=1e-2)


@pytest.mark.parametrize("name", [*PRISMS, *POTS, *POROUS])
def test_prisms_pots_and_post_fences_end_where_the_2d_shadow_ends(name: str) -> None:
    """What agrees: within 2.5 cm at every elevation. A prism's and a pot's top edge
    is bevelled in by 0.6 cm (the tip is that much short); a fence post is wider than
    the stroke (2 cm, 0.75 cm, 1.5 cm further); a plain panel IS the stroke strip."""
    reach = _reach(name)
    assert max(abs(value) for value in reach) <= 2.5
    if name == "plain panel (unknown style)":
        assert max(abs(value) for value in reach) <= 1e-6
    elif name in POROUS:
        assert min(reach) > 0.0   # the posts stand out of the stroke
    else:
        assert min(reach) > -1.0 and max(reach) < 0.0  # the bevel: a hair short


@pytest.mark.parametrize("name", HEDGES)
def test_a_hedge_s_leaves_reach_a_few_centimetres_further(name: str) -> None:
    reach = _reach(name)
    assert min(reach) > 2.0 and max(reach) < 6.0


@pytest.mark.parametrize(("name", "half_depth_cm"), [(GABLE_SQUARE[0], 270.0), (GABLE_SQUARE[1], 150.0)])
def test_a_gable_s_tip_is_half_the_depth_short_with_the_sun_square_to_the_ridge(
    name: str, half_depth_cm: float
) -> None:
    """What does NOT agree, and why. The 2D model extrudes the whole footprint to the
    ridge height: its highest edge is at the FAR WALL. A gable's ridge is mid-house.
    At a low sun the ridge casts the tip — exactly half the depth short (270 cm on the
    5.4 m deep house, 150 cm on the 3 m shed). At a high sun the far eave casts it —
    lower, but half the depth plus the overhang further out — and the miss shrinks."""
    script = _script()
    case = next(case for case in script.cases() if case.name == name)
    ys = [y for _x, y in case.record.footprints[0]]
    assert (max(ys) - min(ys)) / 2.0 == half_depth_cm  # the footprint's depth, square to the ridge
    reach = _reach(name)
    assert reach[0] == pytest.approx(-half_depth_cm, abs=1e-2)  # 15°: the ridge is the tip
    assert reach[0] <= reach[1] <= reach[2] < -20.0             # the miss shrinks, never closes
    assert reach[2] > -half_depth_cm + 100.0                     # 60°: the eave has taken over
    # … and no builder change is asked for: the roof IS on the ridge (gate G2); the
    # difference is the 2D model's flat-topped prism


def test_along_the_ridge_the_overhang_carries_the_tip_further() -> None:
    from open_garden_planner.core.scene3d.builders import buildings

    reach = _reach("house, sun along the ridge")
    assert all(value == pytest.approx(buildings.HOUSE_ROOF.overhang_cm, abs=1e-2) for value in reach)
    assert buildings.HOUSE_ROOF.overhang_cm == 30.0


@pytest.mark.parametrize(("name", "further_cm"), [("wall", 15.0), ("stone-wall fence", 14.5),
                                                  ("hedge fence", 16.0)])
def test_a_nominal_section_carries_the_tip_further(name: str, further_cm: float) -> None:
    """A wall's coping edge stands 17 cm from the centre line (15 cm of body, 4 cm of
    coping, a 2 cm chamfer) where the 4 cm stroke's edge stands at 2: the tip lies
    15 cm further. A stone-wall fence (a 5 cm stroke): 14.5. A hedge fence: its 40 cm
    thickness less the 8 cm stroke, halved — 16 — plus a leaf's poke."""
    reach = _reach(name)
    assert min(reach) >= further_cm - 1e-2
    assert max(reach) <= further_cm + (5.0 if name == "hedge fence" else 1.0)


# ── every copy of the table is the script's ──────────────────────────────────


def _minus(text: str) -> str:
    return text.replace("−", "-").replace("÷", "/")


def _table_cells(text: str, name: str) -> list[list[str]]:
    """The cells of every Markdown table row whose first cell is ``name``."""
    rows = []
    for line in _minus(text).splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and cells and cells[0] == name:
            rows.append(cells)
    return rows


def test_the_adr_s_table_is_the_documented_one() -> None:
    """ADR-059's builders addendum holds the full table: 24 rows (16, and L4's eight), each with the
    script's three number cells, character for character."""
    script = _script()
    text = ADR.read_text(encoding="utf-8")
    text = text[text.index("**The built world's 3D shadows are not the 2D model's shadows"):]
    text = text[:text.index("**Open owner question (porous fences):**")]
    for name, (ratio, iou, reach) in script.DOCUMENTED.items():
        rows = _table_cells(text, name)
        assert len(rows) == 1, (name, rows)
        assert tuple(rows[0][1:4]) == script.cells(ratio, iou, reach), name


def test_the_concepts_table_carries_the_reach() -> None:
    """§8.29.6 groups the kinds; its numbers are the script's, and it has the reach
    column with the two that matter: the gable's miss and the nominal sections'."""
    text = _minus(CONCEPTS.read_text(encoding="utf-8"))
    script = _script()
    section = text[text.index("**3D shadows against the 2D model.**"):]
    section = section[:section.index("\n### ") if "\n### " in section else len(section)]
    for name in (*POROUS, "wall"):
        (row,) = _table_cells(section, name)
        assert tuple(row[1:4]) == script.cells(*script.DOCUMENTED[name]), name
    for needle in ("Reach 3D - 2D", "-270.0 / -270.0 / -108.2", "-150.0 / -81.4 / -21.0",
                   "+30.0", "analytic", "shadow map"):
        assert needle in section, needle


@pytest.mark.parametrize("skill", SKILLS, ids=[".claude", ".agents"])
def test_the_gate_row_states_the_gate_the_conditions_and_the_reach(skill: Path) -> None:
    """Both skill trees: the gate's number, the measuring conditions of the listed
    numbers, and where the tip is — per kind, with the script's numbers."""
    text = skill.read_text(encoding="utf-8")
    row = _minus(next(line for line in text.splitlines() if line.startswith("| Shadows |")))
    assert "IoU ≥ 0.85" in row and "box caster" in row
    assert "scripts/measure_built_world_shadows.py" in row
    for kind in ("picket", "chain-link", "wall", "house", "pot"):
        assert kind in row, kind
    # the measuring conditions (review round 2, P2-4)
    for needle in ("analytic", "10 m", "shadow map", "thin members", "exempt"):
        assert needle in row, needle
    # the reach, per kind, from DOCUMENTED
    script = _script()
    for name in ("house, sun square to the ridge", "shed, sun square to the ridge", "wall",
                 "stone-wall fence", "hedge fence", "picket fence"):
        reach = script.cells(*script.DOCUMENTED[name])[2]
        assert reach.replace(" / ", "/") in row.replace(" / ", "/"), (name, reach)
    assert "half the depth" in row


def test_the_twin_skills_are_identical() -> None:
    assert SKILLS[0].read_bytes() == SKILLS[1].read_bytes()


def test_no_document_says_that_tips_always_agree() -> None:
    """The sentence round 1 wrote next to the gate — "shadow length and tip always
    agree (the height is exact)" — is false for every gabled building and every
    nominal section. It is gone from every document and skill, in any wording."""
    claim = re.compile(r"length\s+and\s+tips?\s+(always\s+)?agree|tips?\s+always\s+agree"
                       r"|\(the\s+height\s+is\s+exact\)", re.IGNORECASE)
    files = [*sorted((ROOT / "docs").rglob("*.md")),
             *sorted((ROOT / ".claude" / "skills").rglob("*.md")),
             *sorted((ROOT / ".agents" / "skills").rglob("*.md"))]
    assert len(files) > 30
    hits = [f"{path.relative_to(ROOT).as_posix()}: {match.group(0)!r}"
            for path in files
            for match in claim.finditer(" ".join(path.read_text(encoding="utf-8").split()))]
    assert hits == []


#: Runs in a CHILD process, where no conftest isolates anything: the script exactly as
#: documented, twice (the table, then ``--check``), with every way to the owner's
#: settings and data watched. ``QSettings`` is replaced by a recorder that REFUSES
#: before any module of the app is imported, so even a script that did construct one
#: could not touch the real store (the registry key on Windows) from this test.
_WATCHED_RUN = r"""
import json, os, runpy, sys

script, report_path = sys.argv[1], sys.argv[2]
seen = {"qsettings": [], "plans": [], "writes": [], "mkdirs": []}
WRITING = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND


def audit(event, args):
    if event == "open":
        path, mode, flags = str(args[0]), args[1], args[2]
        if path.lower().endswith(".ogp"):
            seen["plans"].append(path)
        writes = (set(mode) & set("wax+")) if isinstance(mode, str) else (
            isinstance(flags, int) and flags & WRITING)
        if writes and path != report_path:
            seen["writes"].append([path, str(mode)])
    elif event == "os.mkdir":
        seen["mkdirs"].append(str(args[0]))


sys.addaudithook(audit)
import PyQt6.QtCore as QtCore


def refused(*args, **kwargs):
    seen["qsettings"].append([str(arg) for arg in args])
    raise RuntimeError("a measuring script constructed a QSettings")


QtCore.QSettings = refused
codes = []
for flags in ([], ["--check"]):
    sys.argv = [script, *flags]
    try:
        runpy.run_path(script, run_name="__main__")
        codes.append("returned")
    except SystemExit as stop:
        codes.append(stop.code)
loaded = sorted(name for name in sys.modules if name.startswith("open_garden_planner"))
report = dict(seen, codes=codes, qt_application=QtCore.QCoreApplication.instance() is not None,
              loaded=loaded)
with open(report_path, "w", encoding="utf-8") as out:
    json.dump(report, out)
"""


def test_run_as_documented_the_script_reaches_no_settings_no_plan_and_no_app_data(
    tmp_path: Path,
) -> None:
    """The last pass. Outside pytest the app's settings are the OWNER'S (on Windows a
    registry key no environment variable redirects), and ``ProjectManager.load`` ends
    by writing the recent-files list into them. A committed script that reached either
    would have to isolate itself, as ``tests/conftest.py`` does. This one does not need
    to, and that is measured here, not read: run as its docstring says — in a process of
    its own, both forms — it

    - constructs no ``QSettings`` (so ``get_settings()`` and ``create_qsettings()``
      never ran), and no Qt application;
    - opens no plan file, so ``ProjectManager.load`` never ran;
    - writes no file and creates no directory, in Python or — as far as a redirected,
      empty profile shows — through Qt.

    What is watched is what is CONSTRUCTED and OPENED, not what is imported: importing
    the ``core`` package loads ``app.settings``, ``core.project`` and PyQt6's modules
    into the script's process (the report's ``loaded`` list says so), so a real store
    is one call away, and "the script imports nothing of the app" would be false.

    If a later change makes one of the three false, the script must call an
    ``isolate()`` before its first app import (the pattern:
    ``scripts/measure_plant_art_3d.py``)."""
    profile = tmp_path / "profile"
    profile.mkdir()
    report_path = tmp_path / "report.json"
    environment = {
        **os.environ,
        "USERPROFILE": str(profile), "HOME": str(profile),
        "APPDATA": str(profile / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(profile / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(profile / "config"), "XDG_DATA_HOME": str(profile / "data"),
        "XDG_CACHE_HOME": str(profile / "cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    done = subprocess.run(
        [sys.executable, "-c", _WATCHED_RUN, str(SCRIPT), str(report_path)],
        cwd=ROOT, env=environment, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["codes"] == [0, 0]            # the table, then --check: no drift
    assert report["qsettings"] == []            # no settings object, real or otherwise
    assert report["qt_application"] is False
    assert report["plans"] == []                # no plan was opened
    assert report["writes"] == [] and report["mkdirs"] == []
    assert list(profile.iterdir()) == []        # nothing arrived in the redirected profile
    assert "open_garden_planner.core.scene3d.builders" in report["loaded"]  # it ran its imports
    assert done.stdout.count("| Kind | 3D area / 2D area | IoU |") == 2  # it did print its table


def test_the_stroke_widths_are_the_2d_presets() -> None:
    """The script is Qt-free and repeats the preset stroke widths; this pins them."""
    from open_garden_planner.core.object_types import (
        PATH_FENCE_STYLES,
        ObjectType,
        PathFenceStyle,
        get_style,
    )

    script = _script()
    for name, width in script.STROKE_CM.items():
        if name == "WALL":
            assert get_style(ObjectType.WALL).stroke_width == width
        else:
            assert PATH_FENCE_STYLES[PathFenceStyle[name]].stroke_width == width
    cases = {case.name: case for case in script.cases()}
    assert cases["wall"].record.path_width_cm == 4.0
    assert cases["wall"].record.height_cm == 200.0 and cases["picket fence"].record.height_cm == 120.0
