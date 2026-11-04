"""Reproduce scoped source, import, skill and review-size evidence for epic #392."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def measure(baseline: str) -> dict:
    files = ["app/application.py", "ui/canvas/canvas_view.py",
             "ui/canvas/items/resize_handle.py", "ui/panels/properties_panel.py"]
    sizes = {}
    for relative in files:
        path = "src/open_garden_planner/" + relative
        before = subprocess.check_output(["git", "show", f"{baseline}:{path}"], cwd=ROOT)
        after = (ROOT / path).read_bytes()
        sizes[relative] = {"before_lines": len(before.splitlines()),
                           "after_lines": len(after.splitlines())}
    imports = {}
    for module in ["core.object_types", "core.tools.base_tool", "models.smart_symbol"]:
        code = (
            "import time,sys,json;t=time.perf_counter();"
            f"import open_garden_planner.{module};"
            "print(json.dumps({'ms':(time.perf_counter()-t)*1000,"
            "'project_modules':sum(k.startswith('open_garden_planner') for k in sys.modules),"
            "'ui_modules':[k for k in sys.modules if k.startswith('open_garden_planner.ui')],"
            "'qt_widgets':'PyQt6.QtWidgets' in sys.modules}))"
        )
        imports[module] = [json.loads(subprocess.check_output(
            [sys.executable, "-c", code], cwd=ROOT, encoding="utf-8",
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
        )) for _ in range(3)]
    skills = [{"name": p.parent.name, "entry_bytes": p.stat().st_size,
               "reference_files": len(list((p.parent / "references").glob("*.md")))}
              for p in sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))]
    # All changed files, not just production files; retain that distinction.
    commits = subprocess.check_output(
        ["git", "log", baseline, "-50", "--format=%H"], cwd=ROOT, encoding="utf-8"
    ).splitlines()
    review_units = []
    for sha in commits:
        rows = subprocess.check_output(
            ["git", "diff-tree", "--root", "--no-commit-id", "--numstat", "-r", sha],
            cwd=ROOT, encoding="utf-8",
        ).splitlines()
        production = [row for row in rows if row.split("\t")[-1].startswith("src/")]
        review_units.append({"sha": sha, "production_files": len(production),
                             "production_changed_lines": sum(
                                 int(v) for row in production for v in row.split("\t")[:2]
                                 if v.isdigit())})
    return {"baseline": baseline, "source_sizes": sizes, "imports": imports,
            "root_context_bytes": (ROOT / "AGENTS.md").stat().st_size,
            "skill_entries": skills,
            "review_units": {"scope": "last 50 commits at baseline, production paths only",
                             "samples": review_units,
                             "median_production_files": statistics.median(
                                 row["production_files"] for row in review_units)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(measure(args.baseline), indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
