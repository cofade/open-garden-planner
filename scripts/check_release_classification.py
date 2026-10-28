"""Classify commits for release relevance and detect unreleased changes (AUD-090).

Differentiates:
1. Executable changes (src/open_garden_planner, installer, dependencies) requiring a release.
2. Version-sync chores (mechanical post-release version bumps).
3. Documentation, test, tooling and CI-only changes.

Guards against:
- A chore commit concealing executable code changes (which would bypass release.yml).
- Unnecessary release triggers on doc-only/test-only commits.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Files that participate in mechanical version-sync chores
VERSION_SYNC_FILES = frozenset({
    "pyproject.toml",
    "src/open_garden_planner/__init__.py",
    "uv.lock",
    "pylock.toml",
    "AGENTS.md",
    "CLAUDE.md",
    "docs/roadmap.md",
    "docs/wiki/Roadmap.md",
    "docs/07-deployment-view/README.md",
    "docs/09-architecture-decisions/README.md",
})


def is_executable_path(path: str) -> bool:
    """Check if a repository path affects shipped application runtime or packaging."""
    norm = path.replace("\\", "/")
    if norm.startswith("src/open_garden_planner/"):
        return True
    if norm.startswith("installer/"):
        return True
    return norm in ("pyproject.toml", "uv.lock", "pylock.toml")


def is_version_sync_diff(git_cmd: str, commit_sha: str, cwd: Path = ROOT) -> bool:
    """Verify that changes in version-sync files are strictly version bumps."""
    try:
        proc = subprocess.run(
            [git_cmd, "diff", f"{commit_sha}~1", commit_sha, "--", "src/open_garden_planner/__init__.py", "pyproject.toml"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return False
        diff = proc.stdout
        # Every added line in __init__.py and pyproject.toml should be a version line or comments
        added_lines = [
            line[1:].strip()
            for line in diff.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        version_pattern = re.compile(r'^(version|__version__)\s*=\s*["\']\d+\.\d+\.\d+["\']$')
        for line in added_lines:
            if not line or line.startswith("#"):
                continue
            if not version_pattern.match(line):
                return False
        return True
    except Exception:
        return False


def classify_commit(
    commit_sha: str,
    git_cmd: str | None = None,
    cwd: Path = ROOT,
) -> dict[str, Any]:
    """Classify the release category of a commit."""
    git = git_cmd or shutil.which("git") or "git"

    # Get subject
    sub_proc = subprocess.run(
        [git, "log", "-1", "--format=%s", commit_sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    subject = sub_proc.stdout.strip()
    is_chore_title = subject.startswith("chore:") or subject.startswith("chore(")

    # Get changed files
    files_proc = subprocess.run(
        [git, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", commit_sha],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files = [line.strip() for line in files_proc.stdout.splitlines() if line.strip()]

    executable_files = [f for f in changed_files if is_executable_path(f)]
    non_executable_files = [f for f in changed_files if not is_executable_path(f)]

    is_sync = False
    if executable_files and all(f in VERSION_SYNC_FILES for f in executable_files) and is_version_sync_diff(git, commit_sha, cwd=cwd):
        is_sync = True

    if not executable_files:
        classification = "METADATA_OR_DOCS"
        release_required = False
        policy_violation = False
        message = "Commit touches only documentation, tests, tooling or non-executable metadata."
    elif is_sync:
        classification = "VERSION_SYNC_CHORE"
        release_required = False
        policy_violation = False
        message = "Commit is a mechanical version-sync chore."
    else:
        classification = "EXECUTABLE_RELEASE"
        release_required = True
        if is_chore_title:
            policy_violation = True
            message = (
                f"AUD-090 VIOLATION: Commit has chore prefix ('{subject}') "
                f"but modifies executable files: {executable_files}"
            )
        else:
            policy_violation = False
            message = f"Commit contains executable modifications in: {executable_files}"

    return {
        "commit_sha": commit_sha,
        "subject": subject,
        "is_chore_title": is_chore_title,
        "classification": classification,
        "release_required": release_required,
        "policy_violation": policy_violation,
        "executable_files": executable_files,
        "non_executable_files": non_executable_files,
        "message": message,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD", help="Commit SHA to classify (default: HEAD)")
    parser.add_argument("--json", action="store_true", help="Print json output")
    parser.add_argument("--enforce", action="store_true", help="Fail with exit code 1 on policy violation")
    args = parser.parse_args(argv)

    result = classify_commit(args.commit)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Commit: {result['commit_sha'][:8]} - {result['subject']}")
        print(f"Category: {result['classification']} | Release required: {result['release_required']}")
        print(result["message"])

    if args.enforce and result["policy_violation"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

