"""Report branch coverage and enforce unrounded package line floors (#402)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_metrics import coverage_section

ROOT = Path(__file__).resolve().parents[1]


def validate_floors(data: Any) -> dict[str, int]:
    if (not isinstance(data, dict) or data.get("schema_version") != 1
            or data.get("non_ui_definition") != "all packages except ui"):
        raise ValueError("Invalid coverage floor metadata")
    floors = data.get("line_floors")
    if not isinstance(floors, dict) or not floors:
        raise ValueError("Coverage floors must name every measured package")
    for name, floor in floors.items():
        if (not isinstance(name, str) or not name or type(floor) is not int
                or not 0 <= floor <= 100):
            raise ValueError("Coverage floors must be integer percentages in [0, 100]")
    return floors


def regressions(packages: dict[str, Any], floors: dict[str, int]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in sorted(packages.keys() | floors.keys()):
        if name not in packages or name not in floors:
            results.append({"package": name, "reason": "Missing package or floor entry"})
            continue
        counts = packages[name]
        valid, covered = counts["statements"], counts["covered_statements"]
        if valid <= 0 or covered * 100 < floors[name] * valid:
            results.append({"package": name, "floor": floors[name],
                            "statements": valid, "covered_statements": covered})
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xml", type=Path, required=True)
    parser.add_argument("--floors", type=Path, default=ROOT / "quality/coverage-floors.json")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-floors", action="store_true")
    args = parser.parse_args(argv)
    result: dict[str, Any] = {"available": False}
    code = 2
    try:
        result = coverage_section(args.xml) or {"available": False, "reason": "Missing XML"}
        if not result["available"]:
            raise ValueError(result["reason"])
        if result.get("unresolved_statements", 0):
            raise ValueError("Coverage includes unresolved source statements")
        packages = {name: counts for name, counts in result["per_package"].items()
                    if counts["statements"] > 0}
        if args.write_floors:
            if sys.platform != "linux" or sys.version_info[:2] != (3, 11):
                raise ValueError("Generate coverage floors under locked Linux/Python 3.11")
            data = {"schema_version": 1, "non_ui_definition": "all packages except ui",
                    "line_floors": {name: v["covered_statements"] * 100 // v["statements"]
                                    for name, v in packages.items()}}
            args.floors.parent.mkdir(parents=True, exist_ok=True)
            args.floors.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            data = json.loads(args.floors.read_text(encoding="utf-8"))
        result["regressions"] = regressions(packages, validate_floors(data))
        code = 1 if result["regressions"] else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {**result, "available": False, "reason": str(exc)}
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Could not write coverage report: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
