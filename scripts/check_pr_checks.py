"""Read-only current-head/required-check verification before a normal merge (#399)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def differences(pr: dict[str, Any], head: str, required: list[str]) -> list[str]:
    if not isinstance(pr, dict):
        raise ValueError("PR response must be an object")
    failures: list[str] = []
    if pr.get("headRefOid") != head:
        failures.append("PR head changed after verification")
    if pr.get("baseRefName") != "master":
        failures.append("PR base must be master")
    checks = pr.get("statusCheckRollup")
    if not isinstance(checks, list) or not checks:
        return failures + ["PR has no current-head check results"]
    seen: set[str] = set()
    for check in checks:
        if not isinstance(check, dict):
            raise ValueError("Check result must be an object")
        name = check.get("name") or check.get("context")
        if not isinstance(name, str):
            failures.append("Check has no name")
            continue
        seen.add(name)
        good = (check.get("status") == "COMPLETED" and check.get("conclusion") == "SUCCESS"
                or check.get("state") == "SUCCESS")
        if not good:
            # Non-required intentionally skipped jobs are not failed checks.
            skipped = (check.get("status") == "COMPLETED"
                       and check.get("conclusion") in {"SKIPPED", "NEUTRAL"})
            if name in required or not skipped:
                failures.append(f"Check is not successful: {name}")
    failures.extend(f"Required check is missing: {name}" for name in sorted(set(required) - seen))
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--repo", default="cofade/open-garden-planner")
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--response", type=Path)
    args = parser.parse_args(argv)
    try:
        required = json.loads((ROOT / "quality/master-protection.json").read_text(
            encoding="utf-8"))["required_status_checks"]["contexts"]
        if args.response:
            raw = args.response.read_text(encoding="utf-8")
        else:
            raw = subprocess.run(
                [args.gh, "pr", "view", str(args.pr), "--repo", args.repo,
                 "--json", "headRefOid,baseRefName,statusCheckRollup"],
                check=True, capture_output=True, text=True, encoding="utf-8", timeout=60,
            ).stdout
        failures = differences(json.loads(raw), args.head, required)
        print(json.dumps({"verified_head": args.head, "compliant": not failures,
                          "differences": failures}, indent=2))
        return 1 if failures else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"PR check verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
