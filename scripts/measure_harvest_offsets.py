"""Measure how the bundled harvest offsets reconcile with ``days_to_maturity``.

Committed so the #416 figures quoted in ADR-049, §11.4, the roadmap,
CLAUDE.md/AGENTS.md and issue #418 have a source a reader can re-run.

    venv/Scripts/python.exe scripts/measure_harvest_offsets.py

Two readings are tested against every species that carries both harvest offsets
and a maturity range:

* **A — frost-relative** (``harvest_start x 7`` inside the maturity range): this
  is what every reader actually implements (``generate_calendar_tasks``, the
  calendar Gantt, the agent's task tools, the 3D spike's fruit window).
* **B — planting-relative** ((``harvest_start`` - latest planting offset) ``x 7``,
  inside the range +/-15 %): the reading ``plant_data.py`` used to *document*.

Both readings fit a majority, which is why the row conversion was deferred on
other grounds (a cited horticultural source per row, plus licence clearance) and
NOT because the data was irreconcilable. Earlier revisions of these documents
quoted "1 fits / 63 miss" and "10 fits / 54 miss"; those numbers matched no
harness and were wrong — the senior review caught them.

Prints the per-species misses so a mismatch is diagnosable rather than just a
different integer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from open_garden_planner.models.plant_data import PlantSpeciesData  # noqa: E402

DATA_FILE = (
    Path(__file__).resolve().parents[1]
    / "src" / "open_garden_planner" / "resources" / "data" / "plant_species.json"
)
TOLERANCE = 0.15
PLANTING_FIELDS = ("indoor_sow_start", "direct_sow_start", "transplant_start")


def _population() -> list[PlantSpeciesData]:
    """Species with both harvest offsets and a maturity range."""
    rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))["plants"]
    return [
        sp for sp in (PlantSpeciesData.from_dict(r) for r in rows)
        if sp.harvest_start is not None
        and sp.harvest_end is not None
        and sp.days_to_maturity_min is not None
        and sp.days_to_maturity_max is not None
    ]


def reading_a_fits(sp: PlantSpeciesData) -> bool:
    days = sp.harvest_start * 7
    return sp.days_to_maturity_min <= days <= sp.days_to_maturity_max


def reading_b_span(sp: PlantSpeciesData) -> int | None:
    """Days from the LATEST plausible planting start to the harvest start."""
    offsets = [o for o in (getattr(sp, f) for f in PLANTING_FIELDS) if o is not None]
    if not offsets:
        return None
    return (sp.harvest_start - max(offsets)) * 7


def reading_b_fits(sp: PlantSpeciesData) -> bool | None:
    span = reading_b_span(sp)
    if span is None:
        return None
    lo = sp.days_to_maturity_min * (1 - TOLERANCE)
    hi = sp.days_to_maturity_max * (1 + TOLERANCE)
    return lo <= span <= hi


def main() -> int:
    population = _population()
    a_fit = [sp for sp in population if reading_a_fits(sp)]
    b_results = [(sp, reading_b_fits(sp)) for sp in population]
    b_fit = [sp for sp, ok in b_results if ok]

    print(f"bundled species with both harvest offsets + maturity : {len(population)}")
    print(f"reading A (frost-relative, what the code does)      : "
          f"{len(a_fit)} fit / {len(population) - len(a_fit)} miss")
    print(f"reading B (planting-relative, +/-15%)                : "
          f"{len(b_fit)} fit / {len(population) - len(b_fit)} miss")
    print()

    neither = [
        sp for sp, b in b_results
        if not reading_a_fits(sp) and b is not True
    ]
    # The COUNT is printed, not just the list: documents quote the count, and a
    # guard that checks a documented number needs the harness to produce it.
    print(f"species that fit neither reading: {len(neither)}")
    for sp in sorted(neither, key=lambda s: s.common_name or ""):
        span = reading_b_span(sp)
        print(
            f"  {(sp.common_name or '?'):<26} A={sp.harvest_start * 7:>4}d  "
            f"B={span if span is None else f'{span:>4}d':<6}  "
            f"stated {sp.days_to_maturity_min}-{sp.days_to_maturity_max}"
        )
    print()

    garlic = next(sp for sp in population if sp.scientific_name == "Allium sativum")
    print(f"garlic under reading A: {garlic.harvest_start * 7} d vs stated "
          f"{garlic.days_to_maturity_min}-{garlic.days_to_maturity_max} "
          f"-> {'FITS' if reading_a_fits(garlic) else 'MISSES'}")
    print(
        "Note the direction: a 26-week frost-relative harvest means an autumn "
        "sowing's garlic is harvested in OCTOBER of the following year, whereas "
        "the row's own sowing window (-26..-24 weeks) puts that sowing in the "
        "PREVIOUS October. The row is internally consistent about the sowing "
        "and still lands the harvest about three months late for the crop."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
