"""Tests for release classification and chore-concealed executable checks (AUD-090)."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import patch

import pytest
from scripts.check_release_classification import (
    classify_commit,
    is_executable_path,
    is_version_sync_diff,
    main,
)


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/open_garden_planner/main.py", True),
        ("src/open_garden_planner/core/geometry.py", True),
        ("installer/ogp.spec", True),
        ("installer/build_installer.py", True),
        ("pyproject.toml", True),
        ("uv.lock", True),
        ("pylock.toml", True),
        ("docs/roadmap.md", False),
        ("docs/09-architecture-decisions/README.md", False),
        ("tests/unit/test_foo.py", False),
        ("scripts/check_something.py", False),
        (".github/workflows/ci.yml", False),
        ("AGENTS.md", False),
    ],
)
def test_is_executable_path(path: str, expected: bool) -> None:
    assert is_executable_path(path) is expected


def test_is_version_sync_diff_valid() -> None:
    diff_output = """
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -10,3 +10,3 @@
-version = "1.34.0"
+version = "1.34.1"
--- a/src/open_garden_planner/__init__.py
+++ b/src/open_garden_planner/__init__.py
@@ -1,3 +1,3 @@
-__version__ = "1.34.0"
+__version__ = "1.34.1"
"""

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout=diff_output, stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        assert is_version_sync_diff("git", "commit123") is True


def test_is_version_sync_diff_invalid_added_code() -> None:
    diff_output = """
--- a/pyproject.toml
+++ b/pyproject.toml
@@ -10,3 +10,4 @@
-version = "1.34.0"
+version = "1.34.1"
+some_extra_setting = "oops"
"""

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd, 0, stdout=diff_output, stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        assert is_version_sync_diff("git", "commit123") is False


def test_classify_commit_docs_only() -> None:
    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="docs: update roadmap\n", stderr="")
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="docs/roadmap.md\nAGENTS.md\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        res = classify_commit("abc12345")

    assert res["classification"] == "METADATA_OR_DOCS"
    assert res["release_required"] is False
    assert res["policy_violation"] is False


def test_classify_commit_version_sync_chore() -> None:
    diff_output = """
--- a/pyproject.toml
+++ b/pyproject.toml
-version = "1.34.0"
+version = "1.34.1"
"""

    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="chore: sync version to v1.34.1\n", stderr="")
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="pyproject.toml\nAGENTS.md\n", stderr="")
        if "diff" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout=diff_output, stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        res = classify_commit("abc12345")

    assert res["classification"] == "VERSION_SYNC_CHORE"
    assert res["release_required"] is False
    assert res["policy_violation"] is False


def test_classify_commit_executable_feature() -> None:
    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="feat(US-1.1): add plant feature\n", stderr="")
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="src/open_garden_planner/core/plant.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        res = classify_commit("abc12345")

    assert res["classification"] == "EXECUTABLE_RELEASE"
    assert res["release_required"] is True
    assert res["policy_violation"] is False


def test_classify_commit_chore_concealing_executable_violation() -> None:
    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="chore: tidy up files\n", stderr="")
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="src/open_garden_planner/ui/canvas.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        res = classify_commit("abc12345")

    assert res["classification"] == "EXECUTABLE_RELEASE"
    assert res["release_required"] is True
    assert res["policy_violation"] is True
    assert "AUD-090 VIOLATION" in res["message"]


def test_main_enforce_fails_on_violation() -> None:
    def fake_run(cmd: list[str], *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if "log" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="chore: sneak in code\n", stderr="")
        if "diff-tree" in cmd:
            return subprocess.CompletedProcess(cmd, 0, stdout="src/open_garden_planner/core/foo.py\n", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with patch("subprocess.run", side_effect=fake_run):
        code = main(["--commit", "badc0de", "--enforce"])

    assert code == 1

