"""The git side of the download-stats workflow, run against a temporary bare repository."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "download_stats_git.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None or shutil.which("git") is None,
    reason="needs bash and git (the workflow runs on ubuntu-latest)",
)

ENV = {
    # inherited GIT_DIR/GIT_INDEX_FILE (pytest run from a git hook) would aim the commands at
    # the real repository
    **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True, text=True
    ).stdout.strip()


def _stats(cwd: Path, action: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**ENV, "STATS_REMOTE": "origin", "DATA_DIR": "data"}
    return subprocess.run(
        ["bash", str(SCRIPT), action], cwd=cwd, env=env, capture_output=True, text=True,
        check=check,
    )


@pytest.fixture
def repos(tmp_path: Path) -> tuple[Path, Path]:
    """A bare remote and a clone of it that already holds a ``master`` commit."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "clone", "-q", str(remote), str(work))
    (work / "README").write_text("master\n", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "HEAD:master")
    return remote, work


def _reset_checkout(work: Path) -> None:
    """What a fresh runner looks like: no worktree, no local data branch."""
    subprocess.run(["git", "worktree", "remove", "--force", "data"], cwd=work, env=ENV,
                   capture_output=True)
    subprocess.run(["git", "branch", "-D", "download-stats"], cwd=work, env=ENV,
                   capture_output=True)


def test_first_run_creates_an_orphan_branch_with_no_history_of_master(
    repos: tuple[Path, Path],
) -> None:
    remote, work = repos
    _stats(work, "prepare")
    assert [p.name for p in (work / "data").iterdir()] == [".git"], "starts empty"
    (work / "data" / "SUMMARY.md").write_text("one\n", encoding="utf-8")
    _stats(work, "publish")

    assert _git(remote, "log", "--format=%s", "download-stats").startswith("chore: download stats ")
    assert _git(remote, "ls-tree", "--name-only", "download-stats") == "SUMMARY.md"
    merge_base = subprocess.run(["git", "merge-base", "master", "download-stats"], cwd=remote,
                                env=ENV, capture_output=True)
    assert merge_base.returncode == 1, "no common history with master"
    assert _git(remote, "rev-parse", "master") == _git(work, "rev-parse", "master")


def test_next_run_extends_the_branch_and_an_unchanged_run_commits_nothing(
    repos: tuple[Path, Path],
) -> None:
    remote, work = repos
    _stats(work, "prepare")
    (work / "data" / "SUMMARY.md").write_text("one\n", encoding="utf-8")
    _stats(work, "publish")

    _reset_checkout(work)
    _stats(work, "prepare")
    assert (work / "data" / "SUMMARY.md").read_text(encoding="utf-8") == "one\n"
    unchanged = _stats(work, "publish")
    assert "nothing to commit" in unchanged.stdout
    assert _git(remote, "rev-list", "--count", "download-stats") == "1"

    (work / "data" / "SUMMARY.md").write_text("two\n", encoding="utf-8")
    _stats(work, "publish")
    assert _git(remote, "rev-list", "--count", "download-stats") == "2"
    assert _git(remote, "rev-list", "--max-parents=0", "download-stats").count("\n") == 0


def test_an_unreachable_remote_fails_instead_of_creating_a_new_orphan_branch(
    repos: tuple[Path, Path], tmp_path: Path
) -> None:
    _, work = repos
    _git(work, "remote", "set-url", "origin", str(tmp_path / "does-not-exist.git"))
    result = _stats(work, "prepare", check=False)
    assert result.returncode != 0
    assert "ls-remote failed" in result.stderr
    assert not (work / "data").exists(), "a network failure is not 'the branch does not exist'"


def test_publish_never_force_pushes_over_a_diverged_remote(repos: tuple[Path, Path]) -> None:
    remote, work = repos
    _stats(work, "prepare")
    (work / "data" / "SUMMARY.md").write_text("one\n", encoding="utf-8")
    _stats(work, "publish")
    before = _git(remote, "rev-parse", "download-stats")

    # a second runner that wrongly believed the branch did not exist
    _reset_checkout(work)
    _git(work, "worktree", "add", "--orphan", "-b", "download-stats", "data")
    (work / "data" / "SUMMARY.md").write_text("other\n", encoding="utf-8")
    result = _stats(work, "publish", check=False)
    assert result.returncode != 0
    assert _git(remote, "rev-parse", "download-stats") == before


def test_usage_error_for_an_unknown_action(repos: tuple[Path, Path]) -> None:
    remote, work = repos
    assert _stats(work, "bogus", check=False).returncode == 64


def test_publish_refuses_to_commit_when_data_is_not_the_data_worktree(
    repos: tuple[Path, Path],
) -> None:
    remote, work = repos
    (work / "data").mkdir()
    (work / "data" / "SUMMARY.md").write_text("stray\n", encoding="utf-8")
    result = _stats(work, "publish", check=False)
    assert result.returncode == 1 and "refusing to commit" in result.stderr
    assert _git(work, "log", "--format=%s") == "init", "nothing was committed on master"
    assert "download-stats" not in _git(remote, "branch", "--list")


def test_a_lookalike_branch_is_not_the_data_branch(repos: tuple[Path, Path]) -> None:
    remote, work = repos
    _git(work, "push", "-q", "origin", "HEAD:refs/heads/feature/download-stats")
    result = _stats(work, "prepare")
    assert "creating it as an orphan" in result.stdout


def test_a_shallow_clone_publishes_onto_existing_history(
    repos: tuple[Path, Path], tmp_path: Path
) -> None:
    """The runner's checkout is `--depth=1`; the data branch is fetched shallow too."""
    remote, work = repos
    _stats(work, "prepare")
    (work / "data" / "SUMMARY.md").write_text("one\n", encoding="utf-8")
    _stats(work, "publish")
    shallow = tmp_path / "shallow"
    _git(tmp_path, "clone", "-q", "--depth=1", f"file://{remote}", str(shallow))
    _stats(shallow, "prepare")
    (shallow / "data" / "SUMMARY.md").write_text("two\n", encoding="utf-8")
    _stats(shallow, "publish")
    assert _git(remote, "rev-list", "--count", "download-stats") == "2"
