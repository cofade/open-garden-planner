"""Regenerate tests/data/issue_registry.json from the real GitHub repo.

Dev-only helper, not run in CI (the citation gate — check_skill_citations.py —
deliberately checks against the committed snapshot instead of hitting the
network, so it stays fast and doesn't depend on GitHub being reachable or on
rate limits). Run this after adding a new #NNN reference to a skill file, or
whenever the citation gate reports an issue/PR number missing from the
snapshot:

    venv/Scripts/python.exe scripts/refresh_issue_registry.py

Requires the ``gh`` CLI to be authenticated (``gh auth status``).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from check_skill_citations import (
    _ISSUE_REF_RE,
    CORPUS_GLOBS,
    ISSUE_REGISTRY_PATH,
    REPO_ROOT,
)

GH_EXE = r"C:\Program Files\GitHub CLI\gh.exe"
OWNER = "cofade"
REPO = "open-garden-planner"


def _collect_referenced_numbers(root: Path) -> list[int]:
    numbers: set[int] = set()
    for pattern in CORPUS_GLOBS:
        for path in root.glob(pattern):
            text = path.read_text(encoding="utf-8")
            numbers |= {int(m.group(2)) for m in _ISSUE_REF_RE.finditer(text)}
    return sorted(numbers)


def _build_query(numbers: list[int]) -> str:
    lines = ["query {", f'  repository(owner: "{OWNER}", name: "{REPO}") {{']
    for n in numbers:
        lines.append(
            f"    n{n}: issueOrPullRequest(number: {n}) {{ __typename "
            "... on Issue { number title state } "
            "... on PullRequest { number title state } }"
        )
    lines += ["  }", "}"]
    return "\n".join(lines)


def _fetch(numbers: list[int]) -> dict[str, dict]:
    # GitHub's GraphQL query-complexity limit caps how many aliased fields
    # fit in one request; chunk defensively rather than tuning that limit.
    out: dict[str, dict] = {}
    chunk_size = 100
    for i in range(0, len(numbers), chunk_size):
        chunk = numbers[i : i + chunk_size]
        query = _build_query(chunk)
        result = subprocess.run(
            [GH_EXE, "api", "graphql", "-f", f"query={query}"],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
        repo = payload["data"]["repository"]
        for n in chunk:
            entry = repo.get(f"n{n}")
            if entry is None:
                print(f"warning: #{n} not found on GitHub (typo, or deleted?)")
                continue
            out[str(n)] = {
                "title": entry["title"],
                "state": entry["state"],
                "is_pr": entry["__typename"] == "PullRequest",
            }
    return out


def main() -> int:
    numbers = _collect_referenced_numbers(REPO_ROOT)
    print(f"Found {len(numbers)} referenced issue/PR numbers in the corpus.")
    registry = _fetch(numbers)
    out_path = REPO_ROOT / ISSUE_REGISTRY_PATH
    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(registry, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(registry)} entries to {ISSUE_REGISTRY_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
