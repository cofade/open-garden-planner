"""The build-environment guard reports exactly what differs from the lock (#538)."""

from __future__ import annotations

import io
from dataclasses import dataclass

import pytest
from installer import build_environment


@dataclass
class FakeDistribution:
    name: str
    version: str = "1.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.name}


@pytest.fixture
def lock_path(tmp_path):
    path = tmp_path / "pylock.toml"
    path.write_text(
        'lock-version = "1.0"\n'
        'requires-python = ">=3.11"\n'
        "packages = [\n"
        '  { name = "alpha", version = "1.0" },\n'
        '  { name = "beta", version = "2.0" },\n'
        "]\n",
        encoding="utf-8",
    )
    return path


def test_only_unpinned_distributions_are_reported(lock_path) -> None:
    found = build_environment.environment_problems(
        lock_path,
        installed=[
            FakeDistribution("alpha"),
            FakeDistribution("BETA", "2.0"),
            FakeDistribution("Gamma"),
            FakeDistribution("delta-package", "2.0"),
            FakeDistribution("delta_package", "2.0"),
        ],
    )
    assert [(p.name, p.installed, p.expected) for p in found] == [
        ("delta-package", "2.0", None),
        ("gamma", "1.0", None),
    ]


def test_markers_select_the_one_version_for_this_environment(tmp_path) -> None:
    path = tmp_path / "marked.toml"
    path.write_text(
        "packages = [\n"
        '  { name = "alpha", version = "1.0", marker = "python_version < \'3.0\'" },\n'
        '  { name = "alpha", version = "9.0", marker = "python_version >= \'3.0\'" },\n'
        "]\n",
        encoding="utf-8",
    )
    assert build_environment.environment_problems(
        path, installed=[FakeDistribution("alpha", "9.0")]
    ) == []


def test_a_version_mismatch_is_reported(lock_path) -> None:
    found = build_environment.environment_problems(
        lock_path,
        installed=[FakeDistribution("alpha", "0.9"), FakeDistribution("beta", "2.0")],
    )
    assert [(p.name, p.installed, p.expected) for p in found] == [
        ("alpha", "0.9", "1.0")
    ]


def test_project_and_packaging_tools_are_not_noise(lock_path) -> None:
    found = build_environment.environment_problems(
        lock_path,
        installed=[
            FakeDistribution("open-garden-planner", "1.30.20"),
            FakeDistribution("pip"),
            FakeDistribution("setuptools"),
            FakeDistribution("wheel"),
            FakeDistribution("uv"),
            FakeDistribution("alpha"),
        ],
    )
    assert found == []


def test_a_locked_build_tool_at_another_version_is_a_mismatch(tmp_path) -> None:
    """An allowlisted tool the lock PINS is checked (#571's stale setuptools).

    Skipping every allowlisted name made ``--strict`` print "matches" for a
    setuptools 82.0.0 against a lock pinning 84.1.0 — the exact advisory that
    failed CI. Only a tool the lock does not list (``uv``) may be skipped.
    """
    path = tmp_path / "pylock.toml"
    path.write_text(
        "packages = [\n"
        '  { name = "setuptools", version = "84.1.0" },\n'
        '  { name = "wheel", version = "0.48.0" },\n'
        "]\n",
        encoding="utf-8",
    )
    found = build_environment.environment_problems(
        path,
        installed=[
            FakeDistribution("setuptools", "82.0.0"),
            FakeDistribution("wheel", "0.48.0"),
            FakeDistribution("uv", "0.12.23"),
        ],
    )
    assert [(p.name, p.installed, p.expected) for p in found] == [
        ("setuptools", "82.0.0", "84.1.0")
    ]


def test_a_missing_lock_is_a_warning_not_a_crash(tmp_path, capsys) -> None:
    reported = build_environment.warn_if_unpinned(tmp_path / "absent.toml")
    assert reported == []
    captured = capsys.readouterr()
    assert "cannot compare the build environment" in captured.err


def test_warning_lists_each_problem(lock_path, capsys) -> None:
    reported = build_environment.warn_if_unpinned(
        lock_path,
        installed=[
            FakeDistribution("alpha", "0.9"),
            FakeDistribution("stale-qt", "6.11"),
        ],
    )
    assert [(p.name, p.installed, p.expected) for p in reported] == [
        ("alpha", "0.9", "1.0"),
        ("stale-qt", "6.11", None),
    ]
    captured = capsys.readouterr()
    assert "alpha==0.9 (lock pins 1.0)" in captured.err
    assert "stale-qt==6.11 (not in the lock)" in captured.err
    assert "uv sync --locked --all-extras --group build" in captured.err


def test_strict_mode_fails_on_a_mismatch(lock_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        build_environment.importlib.metadata,
        "distributions",
        lambda: [FakeDistribution("alpha", "0.9"), FakeDistribution("stale-qt")],
    )
    assert build_environment.main(["--lock", str(lock_path)]) == 0
    assert build_environment.main(["--lock", str(lock_path), "--strict"]) == 1
    assert "stale-qt" in capsys.readouterr().err


def test_strict_mode_fails_closed_when_the_lock_cannot_be_read(
    tmp_path, monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        build_environment.importlib.metadata,
        "distributions",
        lambda: [FakeDistribution("alpha")],
    )
    assert build_environment.main(["--lock", str(tmp_path / "absent.toml")]) == 0
    assert (
        build_environment.main(
            ["--lock", str(tmp_path / "absent.toml"), "--strict"]
        )
        == 2
    )
    assert "cannot read" in capsys.readouterr().err


def test_a_clean_environment_passes_strict_mode(lock_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        build_environment.importlib.metadata,
        "distributions",
        lambda: [FakeDistribution("alpha"), FakeDistribution("open-garden-planner")],
    )
    assert build_environment.main(["--lock", str(lock_path), "--strict"]) == 0
    assert "Build environment matches pylock.toml" in capsys.readouterr().out


def test_an_empty_lock_is_rejected(tmp_path) -> None:
    path = tmp_path / "empty.toml"
    path.write_text("packages = []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no packages"):
        build_environment.locked_distributions(path)


def test_warning_does_not_raise_on_a_malformed_lock(tmp_path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("packages = [", encoding="utf-8")
    stream = io.StringIO()
    assert build_environment.warn_if_unpinned(path, stream=stream) == []
    assert "cannot compare the build environment" in stream.getvalue()
