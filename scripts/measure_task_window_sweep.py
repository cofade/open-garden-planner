"""Measure the GUI-vs-agent task-window gap that #414 fixed.

Committed so the figures quoted in ADR-029, §11.4, the roadmap,
CLAUDE.md/AGENTS.md and the debug-verbose case study have a source a reader can
re-run, instead of a prose number nobody can check. Run it from the repo root:

    venv/Scripts/python.exe scripts/measure_task_window_sweep.py
    venv/Scripts/python.exe scripts/measure_task_window_sweep.py --wide

It prints the harness, the before/after missed counts and the surplus count. The
**surplus** is the number that matters: 0 missed can also mean "the GUI listed
everything", so a fix is only real if it missed nothing *and* added nothing.

Two harnesses, and the count depends on which:

* default -- the 64 bundled species that carry calendar offsets x 6 frost dates x
  every 10th day of 2026 (222 cases): **1,836 / 0 / 0**.
* ``--wide`` -- all 118 bundled species x 6 frost dates x every day of 2026
  (2,190 cases): **17,884 / 0 / 0**.

Quote the harness with the number. (An earlier revision of these documents quoted
"2,669", which matched neither sweep and was simply wrong; the round-4 review
caught it. Both figures above are printed by this script.)
"""
from __future__ import annotations

import datetime
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_garden_planner.models.plant_data import PlantSpeciesData  # noqa: E402
from open_garden_planner.services.bundled_species_db import get_species_db  # noqa: E402
from open_garden_planner.services.task_generator import (  # noqa: E402
    PlanState,
    PlantRowInput,
    classify_urgency,
    generate_actionable_for_surface,
    generate_all,
    generate_for_date_window,
)

FROST_DATES = ("03-15", "04-09", "05-15", "09-20", "10-15", "11-15")
DAY_STRIDE = 10
AGENT_LOOKBACK_DAYS = 45
AGENT_LOOKAHEAD_DAYS = 45


def _plant_rows(wide: bool = False) -> list[PlantRowInput]:
    """Bundled species as plan rows.

    ``wide=False`` keeps only species carrying at least one calendar offset — the
    population that can actually produce a task, and therefore the one the
    default harness quotes. ``wide=True`` keeps all of them, which is the harness
    the round-4 review used.
    """
    rows: list[PlantRowInput] = []
    for raw in get_species_db().values():
        sp = PlantSpeciesData.from_dict(raw)
        rows.append(
            PlantRowInput(
                display_name=sp.common_name,
                species_key=sp.scientific_name or sp.common_name,
                indoor_sow_start=sp.indoor_sow_start,
                indoor_sow_end=sp.indoor_sow_end,
                direct_sow_start=sp.direct_sow_start,
                direct_sow_end=sp.direct_sow_end,
                transplant_start=sp.transplant_start,
                transplant_end=sp.transplant_end,
                harvest_start=sp.harvest_start,
                harvest_end=sp.harvest_end,
            )
        )
    if wide:
        return rows
    fields = (
        "harvest_start", "direct_sow_start", "transplant_start", "indoor_sow_start",
    )
    return [r for r in rows if any(getattr(r, f) is not None for f in fields)]


def sweep(wide: bool = False) -> dict[str, int]:
    """Sweep both listings and compare them under the GUI's own listing rule.

    ``wide`` selects the harness: all 118 species on every day of 2026 (the
    review's), or the 64 species with calendar offsets on every 10th day (the
    default, quoted in ADR-029 and §11.4).
    """
    rows = _plant_rows(wide)
    stride = 1 if wide else DAY_STRIDE
    cases = missed_before = missed_after = surplus = 0

    for frost in FROST_DATES:
        for offset in range(0, 365, stride):
            today = datetime.date(2026, 1, 1) + datetime.timedelta(days=offset)
            try:
                last_frost = datetime.date(2026, *(int(x) for x in frost.split("-")))
            except ValueError:
                continue
            state = PlanState(
                today=today, year=2026, last_frost=last_frost, plant_rows=tuple(rows)
            )

            # The agent's explicit date-window read, reduced by the GUI's own
            # listing rule — the comparison #414's sweep specifies.
            agent = {
                t.task_id
                for t in generate_for_date_window(
                    replace(state, actionable_only=False),
                    today - datetime.timedelta(days=AGENT_LOOKBACK_DAYS),
                    today + datetime.timedelta(days=AGENT_LOOKAHEAD_DAYS),
                )
                if classify_urgency(t.start_date, t.end_date, today) is not None
            }
            # ``generate_all`` is the single-year listing master used.
            before = {
                t.task_id for t in generate_all(state)
                if classify_urgency(t.start_date, t.end_date, today) is not None
            }
            after = {t.task_id for t in generate_actionable_for_surface(state)}

            cases += 1
            missed_before += len(agent - before)
            missed_after += len(agent - after)
            surplus += len(after - agent)

    return {
        "species": len(rows),
        "stride": stride,
        "cases": cases,
        "missed_before": missed_before,
        "missed_after": missed_after,
        "surplus": surplus,
    }


def main(argv: list[str] | None = None) -> int:
    import sys as _sys

    wide = "--wide" in (argv if argv is not None else _sys.argv[1:])
    result = sweep(wide)
    print(f"harness                              : {'--wide' if wide else 'default'}")
    print(f"bundled species                      : {result['species']}")
    print(f"frost dates                          : {len(FROST_DATES)} {FROST_DATES}")
    stride_label = "every day" if result["stride"] == 1 else f"every {result['stride']}th day"
    print(f"day stride                           : {stride_label} of 2026")
    print(f"(frost date, day) cases swept        : {result['cases']}")
    print()
    print(f"missed by the GUI on master          : {result['missed_before']}")
    print(f"missed by the GUI now                : {result['missed_after']}")
    print(f"listed now but not by the agent      : {result['surplus']}")
    print()
    if result["missed_after"] or result["surplus"]:
        print("FAILED: the fix is not a clean superset.")
        return 1
    print("OK: the GUI lists every actionable window the agent does, and nothing else.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
