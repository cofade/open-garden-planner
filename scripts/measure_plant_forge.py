"""Measure cold synthesis and warm cache lookup for every canonical recipe.

Run with locked Python 3.11: ``python scripts/measure_plant_forge.py --out FILE``.
Results exclude engine upload, first-frame latency and presentation time.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import script_isolation

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def main() -> int:
    script_isolation.isolate()
    from open_garden_planner.core.plant_art import CATEGORIES, SPECIES, SpriteRef
    from open_garden_planner.core.plant_forge import ForgeCache, forge_plant

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    refs = [SpriteRef(group, name) for group, names in (
        ("species", SPECIES), ("categories", CATEGORIES),
    ) for name in sorted(names)]
    rows = []
    for ref in refs:
        durations = []
        for _ in range(3):
            start = time.perf_counter()
            parts = forge_plant(ref, 420, 180, seed=303, lod=0, cache=None)
            durations.append((time.perf_counter() - start) * 1000)
        cache = ForgeCache()
        forge_plant(ref, 420, 180, seed=303, lod=0, cache=cache)
        start = time.perf_counter()
        for _ in range(20):
            forge_plant(ref, 420, 180, seed=303, lod=0, cache=cache)
        rows.append({"recipe": f"{ref.group}/{ref.name}",
                     "cold_ms": statistics.median(durations),
                     "warm_ms": (time.perf_counter() - start) * 1000 / 20,
                     "triangles": sum(p.mesh.triangle_count for p in parts)})
    values = sorted(float(row["cold_ms"]) for row in rows)
    summary = {"recipes": len(rows), "height_cm": 420, "radius_cm": 180, "seed": 303,
               "cold_median_ms": statistics.median(values),
               "cold_p90_ms": values[int(.9 * (len(values) - 1))],
               "cold_max_ms": max(values),
               "warm_median_ms": statistics.median(float(row["warm_ms"]) for row in rows)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"summary": summary, "recipes": rows}, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    script_isolation.isolate_profile()
    raise SystemExit(main())
