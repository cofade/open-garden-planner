"""Tests for release PR attribution and version bump resolution (issue #543).

Pins the resolution of the merged PR for a release push to the triggering commit
SHA rather than `gh pr list --state merged` (which sorts by creation date and
erroneously attributed PR #484 to PR #521, causing v1.30.14 instead of v1.31.0).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from scripts.resolve_release_pr import (
    _resolve_gh_executable,
    compute_next_version,
    determine_bump_type,
    extract_pr_from_commit_subject,
    main,
    resolve_pr_and_bump,
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

    When both PRs appear in the pulls candidate list, select_merged_pr selects
    #484 because its merged_at timestamp is newer, regardless of creation date.
    """
    pulls: list[dict[str, Any]] = [
        {
            "number": 521,
            "created_at": "2026-10-18T10:00:00Z",
            "merged_at": "2026-10-19T11:19:00Z",
            "base": {"ref": "master"},
            "labels": [],
        },
        {
            "number": 484,
            "created_at": "2026-09-24T10:00:00Z",
            "merged_at": "2026-10-19T21:18:20Z",
            "base": {"ref": "master"},
            "labels": [{"name": "minor"}],
        },
    ]

    selected = select_merged_pr(pulls, target_base="master")
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


def test_select_merged_pr_fallback_and_edge_cases() -> None:
    # Non-dict elements and non-dict base objects
    pulls: list[Any] = [
        "not a dict",
        None,
        {"number": 301, "base": "not a dict", "merged_at": "2026-10-19T10:00:00Z"},
        {"number": 302, "base": {"ref": "develop"}},  # No merged_at
    ]
    # No PR matches master + merged_at, falls back to first valid PR object
    selected = select_merged_pr(pulls, target_base="master")
    assert selected is not None
    assert selected["number"] == 301


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
# Executable resolution
# ---------------------------------------------------------------------------


def test_resolve_gh_executable_custom() -> None:
    assert _resolve_gh_executable("/custom/path/gh") == "/custom/path/gh"


def test_resolve_gh_executable_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/gh" if cmd == "gh" else None)
    assert _resolve_gh_executable(None) == "/usr/bin/gh"


# ---------------------------------------------------------------------------
# Mock-based unit tests for resolve_pr_and_bump
# ---------------------------------------------------------------------------


def _make_subprocess_run(
    tag: str = "v1.30.13",
    api_pulls: list[dict[str, Any]] | None = None,
    api_returncode: int = 0,
    commit_subject: str = "",
    pr_view_labels: list[str] | None = None,
    pr_view_returncode: int = 0,
):
    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cmd_str = " ".join(str(c) for c in cmd)
        # git describe
        if "describe" in cmd:
            if tag:
                return subprocess.CompletedProcess(cmd, 0, stdout=f"{tag}\n", stderr="")
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="fatal: No names found")
        # gh api repos/.../commits/.../pulls
        if "api" in cmd and "commits/" in cmd_str:
            if api_returncode == 0 and api_pulls is not None:
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(api_pulls), stderr="")
            return subprocess.CompletedProcess(cmd, api_returncode or 1, stdout="", stderr="error")
        # git log -1 --format=%s
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=f"{commit_subject}\n", stderr="")
        # gh pr view
        if "pr" in cmd and "view" in cmd:
            if pr_view_returncode == 0 and pr_view_labels is not None:
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="\n".join(pr_view_labels) + "\n", stderr=""
                )
            return subprocess.CompletedProcess(
                cmd, pr_view_returncode or 1, stdout="", stderr="error"
            )
        # git rev-parse HEAD
        if "rev-parse" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef1234\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return fake_run


def test_resolve_pr_and_bump_api_success() -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 484,
                "base": {"ref": "master"},
                "merged_at": "2026-10-19T21:18:20Z",
                "labels": [{"name": "minor"}],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        result = resolve_pr_and_bump(commit_sha="bf4fd77a")

    assert result["pr_number"] == 484
    assert result["labels"] == ["minor"]
    assert result["bump"] == "minor"
    assert result["version"] == "1.31.0"
    assert result["tag"] == "v1.31.0"
    assert result["source"] == "api"


def test_resolve_pr_and_bump_api_string_labels() -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 500,
                "base": {"ref": "master"},
                "merged_at": "2026-10-20T10:00:00Z",
                "labels": ["major"],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        result = resolve_pr_and_bump(commit_sha="aabbccdd")

    assert result["pr_number"] == 500
    assert result["labels"] == ["major"]
    assert result["bump"] == "major"
    assert result["version"] == "2.0.0"
    assert result["tag"] == "v2.0.0"
    assert result["source"] == "api"


def test_resolve_pr_and_bump_subject_fallback() -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.14",
        api_returncode=1,  # API fails or returns empty
        commit_subject="docs(11): split the §11.4 pitfall catalogue (ADR-061) (#546)",
        pr_view_labels=["minor", "documentation"],
    )
    with patch("subprocess.run", side_effect=fake_run):
        result = resolve_pr_and_bump(commit_sha="ccee1122")

    assert result["pr_number"] == 546
    assert result["labels"] == ["minor", "documentation"]
    assert result["bump"] == "minor"
    assert result["version"] == "1.31.0"
    assert result["tag"] == "v1.31.0"
    assert result["source"] == "subject"


def test_resolve_pr_and_bump_no_pr_defaults_to_patch() -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.14",
        api_pulls=[],  # empty
        commit_subject="direct push to master without pr suffix",
    )
    with patch("subprocess.run", side_effect=fake_run):
        result = resolve_pr_and_bump(commit_sha="direct1234")

    assert result["pr_number"] is None
    assert result["labels"] == []
    assert result["bump"] == "patch"
    assert result["version"] == "1.30.15"
    assert result["tag"] == "v1.30.15"
    assert result["source"] is None


def test_resolve_pr_and_bump_handles_subprocess_exceptions() -> None:
    def crashing_run(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
        raise OSError("Simulated command execution failure")

    with patch("subprocess.run", side_effect=crashing_run):
        result = resolve_pr_and_bump(commit_sha="errsha")

    # Degrades gracefully: defaults to latest tag v1.0.0 and patch bump v1.0.1
    assert result["latest_tag"] == "v1.0.0"
    assert result["bump"] == "patch"
    assert result["version"] == "1.0.1"
    assert result["tag"] == "v1.0.1"


# ---------------------------------------------------------------------------
# CLI tests (main)
# ---------------------------------------------------------------------------


def test_main_text_format(capsys: pytest.CaptureFixture[str]) -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 484,
                "base": {"ref": "master"},
                "merged_at": "2026-10-19T21:18:20Z",
                "labels": [{"name": "minor"}],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--commit", "bf4fd77a", "--format", "text"])

    assert code == 0
    out = capsys.readouterr().out
    assert "PR #484" in out
    assert "Bump: minor" in out
    assert "Releasing version: 1.31.0" in out


def test_main_json_format(capsys: pytest.CaptureFixture[str]) -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 484,
                "base": {"ref": "master"},
                "merged_at": "2026-10-19T21:18:20Z",
                "labels": [{"name": "minor"}],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--commit", "bf4fd77a", "--format", "json"])

    assert code == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["pr_number"] == 484
    assert parsed["bump"] == "minor"
    assert parsed["version"] == "1.31.0"
    assert parsed["tag"] == "v1.31.0"


def test_main_github_output_format(capsys: pytest.CaptureFixture[str]) -> None:
    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 484,
                "base": {"ref": "master"},
                "merged_at": "2026-10-19T21:18:20Z",
                "labels": [{"name": "minor"}],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--commit", "bf4fd77a", "--format", "github-output"])

    assert code == 0
    out = capsys.readouterr().out
    assert "version=1.31.0" in out
    assert "tag=v1.31.0" in out
    assert "bump=minor" in out
    assert "pr_number=484" in out


def test_main_write_github_output_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gh_output_file = tmp_path / "github_output.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(gh_output_file))

    fake_run = _make_subprocess_run(
        tag="v1.30.13",
        api_pulls=[
            {
                "number": 484,
                "base": {"ref": "master"},
                "merged_at": "2026-10-19T21:18:20Z",
                "labels": [{"name": "minor"}],
            }
        ],
    )
    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--commit", "bf4fd77a", "--write-github-output"])

    assert code == 0
    assert gh_output_file.is_file()
    written = gh_output_file.read_text(encoding="utf-8")
    assert "version=1.31.0\n" in written
    assert "tag=v1.31.0\n" in written
    assert "bump=minor\n" in written
    assert "pr_number=484\n" in written


def test_main_resolves_head_when_commit_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)
    fake_run = _make_subprocess_run(tag="v1.30.13", api_pulls=[])
    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--format", "text"])

    assert code == 0


def test_main_fails_when_git_rev_parse_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_SHA", raising=False)

    def failing_rev_parse(cmd: list[str], *args: Any, **kwargs: Any) -> Any:
        if "rev-parse" in cmd:
            raise subprocess.CalledProcessError(1, cmd, output="fatal")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=failing_rev_parse):
        code = main([])

    assert code == 1


# ---------------------------------------------------------------------------
# Static pins on .github/workflows/release.yml
# ---------------------------------------------------------------------------


def test_release_workflow_delegates_to_resolve_release_pr() -> None:
    """release.yml must delegate version resolution directly to resolve_release_pr.py."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "python scripts/resolve_release_pr.py --write-github-output" in text, (
        "release.yml must call `python scripts/resolve_release_pr.py --write-github-output`"
    )


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


def test_release_workflow_passes_required_env() -> None:
    """release.yml must supply GH_TOKEN, GITHUB_SHA, and GITHUB_REPOSITORY."""
    text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "GH_TOKEN: ${{ github.token }}" in text
    assert "GITHUB_SHA: ${{ github.sha }}" in text
    assert "GITHUB_REPOSITORY: ${{ github.repository }}" in text
