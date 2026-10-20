"""Tests for release PR attribution and version bump resolution (issue #543).

Pins the resolution of the merged PR for a release push to the triggering commit
SHA rather than `gh pr list --state merged` (which sorts by creation date and
erroneously attributed PR #484 to PR #521, causing v1.30.14 instead of v1.31.0).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts.resolve_release_pr import (
    compute_next_version,
    determine_bump_type,
    extract_pr_from_commit_subject,
    select_merged_pr,
)

ROOT = Path(__file__).resolve().parents[2]
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


# ---------------------------------------------------------------------------
# Commit subject PR number extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject,expected",
    [
        ("feat(#385): Phase 17 L1 - Qt Quick 3D replaces Qt 3D (#484)", 484),
        ("docs(11): split the §11.4 pitfall catalogue (ADR-061) (#546)", 546),
        ("fix(#512-#516): mutation-verified gate pin (#520)", 520),
        ("fix: restore line appearance undo and contain styled paint (#545)", 545),
        ("simple title (#1)", 1),
        ("title with multiple (#123) and suffix (#456)", 456),
        ("chore: sync version to v1.30.15 after PR #546", None),
        ("no pr suffix here", None),
        ("suffix with words (#123) extra", None),
        ("suffix with non-digits (#abc)", None),
        ("", None),
    ],
)
def test_extract_pr_from_commit_subject(subject: str, expected: int | None) -> None:
    assert extract_pr_from_commit_subject(subject) == expected


# ---------------------------------------------------------------------------
# PR selection: old-created PR newly merged vs newly-created PR merged earlier
# ---------------------------------------------------------------------------


def test_select_merged_pr_prefers_old_created_newly_merged_pr() -> None:
    """Issue #543 root cause reproduction.

    PR #484 was created in September and merged on 2026-10-19T21:18Z with label 'minor'.
    PR #521 was created in October and merged on 2026-10-19T11:19Z with no label.
    `gh pr list --state merged --base master --limit 1` sorted by `createdAt` desc,
    erroneously returning #521 instead of #484.

    The commit-scoped pulls list for commit bf4fd77a contains #484, and
    select_merged_pr selects it correctly.
    """
    pulls_for_bf4fd77a: list[dict[str, Any]] = [
        {
            "number": 484,
            "created_at": "2026-09-24T10:00:00Z",
            "merged_at": "2026-10-19T21:18:20Z",
            "base": {"ref": "master"},
            "labels": [{"name": "minor"}],
        }
    ]

    selected = select_merged_pr(pulls_for_bf4fd77a, target_base="master")
    assert selected is not None
    assert selected["number"] == 484

    labels = [lbl["name"] for lbl in selected.get("labels", [])]
    bump = determine_bump_type(labels)
    assert bump == "minor"

    # With latest tag v1.30.13, a minor bump gives 1.31.0, not 1.30.14
    version, tag = compute_next_version("v1.30.13", bump)
    assert version == "1.31.0"
    assert tag == "v1.31.0"


def test_select_merged_pr_filters_by_base_branch() -> None:
    pulls: list[dict[str, Any]] = [
        {
            "number": 100,
            "merged_at": "2026-10-19T12:00:00Z",
            "base": {"ref": "feature/other"},
            "labels": [{"name": "major"}],
        },
        {
            "number": 200,
            "merged_at": "2026-10-19T10:00:00Z",
            "base": {"ref": "master"},
            "labels": [{"name": "minor"}],
        },
    ]
    selected = select_merged_pr(pulls, target_base="master")
    assert selected is not None
    assert selected["number"] == 200


def test_select_merged_pr_picks_newest_merge_when_multiple_match() -> None:
    pulls: list[dict[str, Any]] = [
        {
            "number": 101,
            "merged_at": "2026-10-19T10:00:00Z",
            "base": {"ref": "master"},
        },
        {
            "number": 102,
            "merged_at": "2026-10-19T15:00:00Z",
            "base": {"ref": "master"},
        },
    ]
    selected = select_merged_pr(pulls, target_base="master")
    assert selected is not None
    assert selected["number"] == 102


def test_select_merged_pr_empty_list_returns_none() -> None:
    assert select_merged_pr([]) is None
    assert select_merged_pr([{}]) is None


# ---------------------------------------------------------------------------
# Exact label matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "labels,expected_bump",
    [
        (["minor"], "minor"),
        (["major"], "major"),
        (["major", "minor"], "major"),
        (["minor", "bug"], "minor"),
        (["patch"], "patch"),
        (["documentation"], "patch"),
        ([], "patch"),
        # Substrings must NOT match (the grep -q vs grep -qx defect)
        (["not-minor"], "patch"),
        (["subminor"], "patch"),
        (["minor-enhancement"], "patch"),
        (["major-change"], "patch"),
        (["pre-major"], "patch"),
    ],
)
def test_determine_bump_type_exact_matching(labels: list[str], expected_bump: str) -> None:
    assert determine_bump_type(labels) == expected_bump


# ---------------------------------------------------------------------------
# Version computation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tag,bump,expected_version,expected_tag",
    [
        ("v1.30.13", "patch", "1.30.14", "v1.30.14"),
        ("v1.30.13", "minor", "1.31.0", "v1.31.0"),
        ("v1.30.13", "major", "2.0.0", "v2.0.0"),
        ("1.2.3", "patch", "1.2.4", "v1.2.4"),
        ("v0.9.9", "minor", "0.10.0", "v0.10.0"),
        ("v0.9.9", "major", "1.0.0", "v1.0.0"),
        ("invalid", "patch", "1.0.1", "v1.0.1"),
    ],
)
def test_compute_next_version(
    tag: str, bump: str, expected_version: str, expected_tag: str
) -> None:
    v, t = compute_next_version(tag, bump)
    assert v == expected_version
    assert t == expected_tag


# ---------------------------------------------------------------------------
# Real git commit subject test (offline)
# ---------------------------------------------------------------------------


def test_real_commit_bf4fd77a_resolves_pr_484_from_local_git() -> None:
    """Verify that git log extracts PR #484 from commit bf4fd77a without network."""
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%s", "bf4fd77a"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        pytest.skip("Commit bf4fd77a not present in this shallow/partial clone")

    subject = proc.stdout.strip()
    pr_num = extract_pr_from_commit_subject(subject)
    assert pr_num == 484


# ---------------------------------------------------------------------------
# Static pins on .github/workflows/release.yml
# ---------------------------------------------------------------------------


def test_release_workflow_does_not_use_latest_created_merged_pr() -> None:
    """release.yml must not use `gh pr list --state merged` to determine version.

    `gh pr list` sorts by creation date, newest first. For long-running PRs,
    newer-created PRs shadow the merged PR (#543).
    """
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "gh pr list --state merged" not in text, (
        "release.yml contains `gh pr list --state merged`, which sorts by creation "
        "date and ignores older merged PRs (issue #543)"
    )


def test_release_workflow_pins_commit_sha_pulls_lookup() -> None:
    """release.yml must query PRs for the triggering commit SHA."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert re.search(r"commits/(\$|%\{).*pulls", text) or "commits/${COMMIT_SHA}/pulls" in text, (
        "release.yml must query GitHub API for pulls associated with the commit SHA"
    )


def test_release_workflow_pins_squash_subject_fallback() -> None:
    """release.yml must have a fallback that extracts (#N) from the commit subject."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert r"\(#([0-9]+)\)" in text or re.search(r"\(#\[0-9\]\+\)", text), (
        "release.yml must extract the PR number suffix '(#N)' from the commit subject"
    )


def test_release_workflow_pins_exact_label_grep() -> None:
    """release.yml must use `grep -qx` for major and minor to avoid substring matching."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert 'grep -qx "major"' in text or "grep -qx 'major'" in text, (
        "release.yml must match 'major' label with exact line matching (`grep -qx`)"
    )
    assert 'grep -qx "minor"' in text or "grep -qx 'minor'" in text, (
        "release.yml must match 'minor' label with exact line matching (`grep -qx`)"
    )
    # Ensure loose grep without -x is gone
    assert 'grep -q "major"' not in text and "grep -q 'major'" not in text, (
        "release.yml still contains loose `grep -q \"major\"`"
    )
    assert 'grep -q "minor"' not in text and "grep -q 'minor'" not in text, (
        "release.yml still contains loose `grep -q \"minor\"`"
    )
