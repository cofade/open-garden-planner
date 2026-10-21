"""Resolve release PR attribution and version bump for a master commit (#543).

Resolves the PR whose merge commit triggered a release push, avoiding the
ordering defect of ``gh pr list --state merged`` (which sorts by creation date
and ignores older PRs like #484).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def extract_pr_from_commit_subject(subject: str) -> int | None:
    """Extract PR number from a squash-and-merge or merge commit subject.

    GitHub appends ' (#N)' to the subject of a squash-and-merge commit by default.
    Also handles standard merge commit syntax 'Merge pull request #N'.
    Allows optional trailing whitespace.
    """
    cleaned = subject.strip()
    match = re.search(r"\(#(\d+)\)\s*$", cleaned)
    if match:
        return int(match.group(1))
    merge_match = re.search(r"^Merge pull request #(\d+)", cleaned)
    if merge_match:
        return int(merge_match.group(1))
    return None


def select_merged_pr(
    pulls: list[dict[str, Any]],
    target_base: str = "master",
) -> dict[str, Any] | None:
    """Select the merged PR targeting `target_base` from a commit's pulls list.

    Prioritizes PRs merged to the target base branch. If multiple match, picks
    the one with the newest `merged_at` timestamp. If none match base and
    merged_at, returns None so caller falls back to commit subject parsing.
    """
    if not pulls:
        return None

    matching: list[dict[str, Any]] = []
    for pull in pulls:
        if not isinstance(pull, dict):
            continue
        base = pull.get("base")
        base_ref = base.get("ref") if isinstance(base, dict) else None
        merged_at = pull.get("merged_at")
        if base_ref == target_base and merged_at is not None:
            matching.append(pull)

    if matching:
        # Sort by merged_at descending so the most recent merge wins
        matching.sort(key=lambda p: str(p.get("merged_at") or ""), reverse=True)
        return matching[0]

    return None


def determine_bump_type(labels: list[str]) -> str:
    """Determine version bump type with exact label matching.

    Matches 'major' > 'minor' > 'patch'. Substrings like 'not-minor' or
    'minor-fix' do not trigger a minor bump.
    """
    normalized = {lbl.strip() for lbl in labels if isinstance(lbl, str)}
    if "major" in normalized:
        return "major"
    if "minor" in normalized:
        return "minor"
    return "patch"


def compute_next_version(latest_tag: str, bump_type: str) -> tuple[str, str]:
    """Compute the next semantic version string and git tag from the previous tag."""
    raw = latest_tag.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", raw)
    if match:
        major, minor, patch = map(int, match.groups())
    else:
        major, minor, patch = 1, 0, 0

    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    else:
        patch += 1

    version_str = f"{major}.{minor}.{patch}"
    tag_str = f"v{version_str}"
    return version_str, tag_str


def _resolve_gh_executable(gh_cmd: str | None) -> str:
    if gh_cmd:
        return gh_cmd
    found = shutil.which("gh")
    if found:
        return found
    if sys.platform == "win32":
        default_win = Path(r"C:\Program Files\GitHub CLI\gh.exe")
        if default_win.is_file():
            return str(default_win)
    return "gh"


def resolve_pr_and_bump(
    commit_sha: str,
    repo: str = "cofade/open-garden-planner",
    gh_cmd: str | None = None,
    git_cmd: str | None = None,
) -> dict[str, Any]:
    """Resolve PR number, labels, bump type, and next version for a commit."""
    gh = _resolve_gh_executable(gh_cmd)
    git = git_cmd or shutil.which("git") or "git"

    # Get latest tag
    latest_tag = "v1.0.0"
    try:
        tag_args = [git, "describe", "--tags", "--abbrev=0"]
        if commit_sha:
            tag_args.append(commit_sha)
        tag_proc = subprocess.run(
            tag_args,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        tag_out = tag_proc.stdout.strip()
        if tag_proc.returncode == 0 and tag_out:
            latest_tag = tag_out
    except Exception:
        pass

    source: str | None = None
    pr_number: int | None = None
    labels: list[str] = []

    # Method 1: query GitHub API for PRs associated with the commit SHA
    try:
        api_proc = subprocess.run(
            [gh, "api", f"repos/{repo}/commits/{commit_sha}/pulls"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if api_proc.returncode == 0 and api_proc.stdout.strip():
            pulls_data = json.loads(api_proc.stdout)
            if isinstance(pulls_data, list):
                selected = select_merged_pr(pulls_data, target_base="master")
                if selected:
                    source = "api"
                    pr_number = selected.get("number")
                    raw_labels = selected.get("labels", [])
                    if isinstance(raw_labels, list):
                        for item in raw_labels:
                            if isinstance(item, dict) and "name" in item:
                                labels.append(str(item["name"]))
                            elif isinstance(item, str):
                                labels.append(item)
    except Exception:
        pass

    # Method 2: fallback to commit subject " (#N)" or "Merge pull request #N"
    if pr_number is None:
        try:
            subject_proc = subprocess.run(
                [git, "log", "-1", "--format=%s", commit_sha],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if subject_proc.returncode == 0:
                pr_number = extract_pr_from_commit_subject(subject_proc.stdout)
                if pr_number is not None:
                    source = "subject"
        except Exception:
            pass

    # If resolved via subject fallback, query gh pr view for labels
    if source == "subject" and pr_number is not None:
        try:
            view_proc = subprocess.run(
                [
                    gh,
                    "pr",
                    "view",
                    str(pr_number),
                    "--repo",
                    repo,
                    "--json",
                    "labels",
                    "--jq",
                    ".labels[].name",
                ],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if view_proc.returncode == 0 and view_proc.stdout.strip():
                labels = [
                    line.strip()
                    for line in view_proc.stdout.splitlines()
                    if line.strip()
                ]
        except Exception:
            pass

    bump = determine_bump_type(labels)
    version, tag = compute_next_version(latest_tag, bump)

    return {
        "commit_sha": commit_sha,
        "repo": repo,
        "pr_number": pr_number,
        "labels": labels,
        "bump": bump,
        "latest_tag": latest_tag,
        "version": version,
        "tag": tag,
        "source": source,
    }


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        default=os.environ.get("GITHUB_SHA"),
        help="Commit SHA (defaults to $GITHUB_SHA or HEAD)",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "cofade/open-garden-planner"),
        help="GitHub repository (owner/name)",
    )
    parser.add_argument("--gh", default=None, help="Path to gh executable")
    parser.add_argument("--git", default=None, help="Path to git executable")
    parser.add_argument(
        "--format",
        choices=["text", "json", "github-output"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--write-github-output",
        action="store_true",
        help="Append version, tag, bump, and pr_number to $GITHUB_OUTPUT file if set",
    )
    args = parser.parse_args(argv)

    commit = args.commit
    if not commit:
        git_cmd = args.git or shutil.which("git") or "git"
        try:
            rev_proc = subprocess.run(
                [git_cmd, "rev-parse", "HEAD"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            commit = rev_proc.stdout.strip()
        except Exception as exc:
            print(f"Failed to resolve HEAD commit: {exc}", file=sys.stderr)
            return 1

    result = resolve_pr_and_bump(
        commit_sha=commit,
        repo=args.repo,
        gh_cmd=args.gh,
        git_cmd=args.git,
    )

    if args.format == "json":
        print(json.dumps(result, indent=2))
    elif args.format == "github-output":
        print(f"version={result['version']}")
        print(f"tag={result['tag']}")
        print(f"bump={result['bump']}")
        print(f"pr_number={result['pr_number'] or ''}")
    else:
        pr_str = f"PR #{result['pr_number']}" if result["pr_number"] else "no PR"
        labels_str = f"labels: {result['labels']}" if result["labels"] else "no labels"
        print(
            f"Commit: {result['commit_sha'][:8]} | {pr_str} | {labels_str} | "
            f"Bump: {result['bump']} | {result['latest_tag']} -> {result['tag']}"
        )
        print(f"Releasing version: {result['version']}")

    if args.write_github_output:
        gh_output = os.environ.get("GITHUB_OUTPUT")
        if gh_output:
            with open(gh_output, "a", encoding="utf-8") as f:
                f.write(f"version={result['version']}\n")
                f.write(f"tag={result['tag']}\n")
                f.write(f"bump={result['bump']}\n")
                f.write(f"pr_number={result['pr_number'] or ''}\n")
        else:
            print(
                "Warning: --write-github-output specified but GITHUB_OUTPUT environment variable is not set",
                file=sys.stderr,
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
