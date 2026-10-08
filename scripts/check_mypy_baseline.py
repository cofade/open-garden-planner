"""Check production mypy errors against explicit per-file/platform allowances (#401)."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.audit_metrics import parse_mypy

ROOT = Path(__file__).resolve().parents[1]


def validate_baseline(data: Any, mypy_version: str) -> dict[str, Any]:
    """Reject stale tools and invalid allowances instead of silently budgeting them."""
    if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
            or data["schema_version"] != 1):
        raise ValueError("Unsupported mypy baseline schema")
    if data.get("target_python") != "3.11" or data.get("mypy_version") != mypy_version:
        raise ValueError("Baseline Python/mypy metadata does not match the locked tools")
    envs = data.get("environments")
    if not isinstance(envs, dict) or not envs or set(envs) - {"linux", "win32"}:
        raise ValueError("Baseline must contain Linux/Windows environment records")
    for env in envs.values():
        if not isinstance(env, dict) or not isinstance(env.get("per_file"), dict):
            raise ValueError("Invalid per-file baseline")
        for path, count in env["per_file"].items():
            if (not path.startswith("src/open_garden_planner/") or "\\" in path
                    or ".." in path.split("/") or type(count) is not int or count < 0):
                raise ValueError("Invalid production path or error allowance")
    return data


def regressions(actual: dict[str, int], allowed: dict[str, int]) -> list[dict[str, Any]]:
    return [
        {"path": path, "actual": count, "allowed": allowed.get(path, 0)}
        for path, count in sorted(actual.items()) if count > allowed.get(path, 0)
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=Path("quality/mypy-baseline.json"))
    parser.add_argument("--report", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    path = args.baseline if args.baseline.is_absolute() else root / args.baseline
    result: dict[str, Any] = {"available": False}
    code = 2
    try:
        if sys.version_info[:2] != (3, 11) or sys.platform not in {"linux", "win32"}:
            raise ValueError("Use locked Python 3.11 on Linux or Windows")
        version = importlib.metadata.version("mypy")
        data = None
        if path.exists():
            data = validate_baseline(json.loads(path.read_text(encoding="utf-8")), version)
        elif not args.write_baseline:
            raise ValueError("Mypy baseline is missing")
        if not args.write_baseline and sys.platform not in data["environments"]:
            raise ValueError("Baseline is missing this platform")
        proc = subprocess.run(
            [sys.executable, "-m", "mypy", "src/open_garden_planner", "--no-incremental",
             "--show-error-codes", "--no-pretty", "--no-color-output"],
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=1800, check=False,
        )
        result = parse_mypy(proc.returncode, proc.stdout, proc.stderr)
        result.update({"mypy_version": version, "platform": sys.platform, "target_python": "3.11"})
        if not result["available"]:
            raise ValueError(result["reason"])
        if args.write_baseline:
            data = data or {"schema_version": 1, "target_python": "3.11",
                            "mypy_version": version, "environments": {}}
            data["environments"][sys.platform] = {"per_file": result["per_file"]}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            result["regressions"] = []
        else:
            result["regressions"] = regressions(
                result["per_file"], data["environments"][sys.platform]["per_file"]
            )
        code = 1 if result["regressions"] else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired,
            importlib.metadata.PackageNotFoundError) as exc:
        result = {**result, "available": False, "reason": str(exc)}
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"Could not write type report: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
