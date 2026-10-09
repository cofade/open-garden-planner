"""Read-only verification of the proposed/live master protection policy (#399)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def differences(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        raise ValueError("Protection response and policy must be objects")
    failures: list[str] = []
    checks = actual.get("required_status_checks") or {}
    if checks.get("strict") is not True:
        failures.append("Required checks must require an up-to-date branch")
    if set(checks.get("contexts", [])) != set(expected["required_status_checks"]["contexts"]):
        failures.append("Required check names differ from the committed policy")
    reviews = actual.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        failures.append("Changes must require a pull request")
    elif (reviews.get("required_approving_review_count") != 0
          or reviews.get("require_code_owner_reviews") is not False
          or reviews.get("require_last_push_approval") is not False):
        failures.append("Solo-maintainer PRs must require no approving review")
    for name, required in (("enforce_admins", True), ("allow_force_pushes", False),
                           ("allow_deletions", False)):
        value = actual.get(name)
        if isinstance(value, dict):
            value = value.get("enabled")
        if value is not required:
            failures.append(f"{name} must be {required}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default="cofade/open-garden-planner")
    parser.add_argument("--branch", default="master")
    parser.add_argument("--gh", default="gh")
    parser.add_argument("--payload", type=Path, default=ROOT / "quality/master-protection.json")
    parser.add_argument("--response", type=Path, help="Read an offline REST response instead")
    args = parser.parse_args(argv)
    try:
        expected = json.loads(args.payload.read_text(encoding="utf-8"))
        if args.response:
            raw = args.response.read_text(encoding="utf-8")
        else:
            raw = subprocess.run(
                [args.gh, "api", f"repos/{args.repo}/branches/{args.branch}/protection"],
                check=True, capture_output=True, text=True, encoding="utf-8", timeout=60,
            ).stdout
        failures = differences(json.loads(raw), expected)
        print(json.dumps({"compliant": not failures, "differences": failures}, indent=2))
        return 1 if failures else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Protection verification failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
