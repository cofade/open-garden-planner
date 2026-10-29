"""Read-only verification of a package's concrete draft-PR handoff (audit A12)."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from typing import Any


def validate(data: dict[str, Any], head: str, issues: set[int]) -> list[str]:
    errors = []
    if data.get("baseRefName") != "master":
        errors.append("PR base must be master")
    if not data.get("isDraft"):
        errors.append("Handoff must remain a draft until explicit owner acceptance")
    if data.get("headRefName") == "master" or data.get("headRefOid") != head:
        errors.append("PR must contain the current feature-branch head")
    closing = {item["number"] for item in data.get("closingIssuesReferences", [])}
    if issues - closing:
        errors.append(f"Missing closing keywords for issues: {sorted(issues - closing)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pr", type=int)
    parser.add_argument("--issue", type=int, action="append", default=[])
    args = parser.parse_args()
    gh = shutil.which("gh") or r"C:\Program Files\GitHub CLI\gh.exe"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    data = json.loads(subprocess.check_output([
        gh, "pr", "view", str(args.pr), "--json",
        "baseRefName,headRefName,headRefOid,isDraft,closingIssuesReferences",
    ], text=True, encoding="utf-8"))
    errors = validate(data, head, set(args.issue))
    print("\n".join(errors) if errors else "Draft package handoff verified.")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
