"""Toolchain-pin drift guards for the release build (AUD-049)."""

import importlib.util
import json
import re
import tomllib
from pathlib import Path

from scripts.emit_build_evidence import collect, missing_required

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
MANIFEST_VERSION = PYPROJECT["project"]["version"]


def _workflow_files() -> list[Path]:
    """Every workflow and composite action file — derived, never hand-typed.

    A hand-typed list is how a new workflow silently escapes the guard (#377's
    lesson, re-applied here after senior review round 3).
    """
    files = sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    files += sorted((ROOT / ".github" / "actions").glob("*/action.y*ml"))
    return [path for path in files if path.is_file()]


def _files_with_python_pin() -> list[Path]:
    return [p for p in _workflow_files() if "python-version:" in p.read_text(encoding="utf-8")]


def _load_build_installer():
    spec = importlib.util.spec_from_file_location(
        "ogp_build_installer", ROOT / "installer" / "build_installer.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_workflow_pins_a_full_python_patch() -> None:
    files = _files_with_python_pin()
    assert files, "no workflow pins a python-version at all"
    for path in files:
        text = path.read_text(encoding="utf-8")
        # Unquoted values count too: `python-version: 3.11` must fail here, not
        # slip through a quotes-only pattern (senior review round 4).
        versions = re.findall(r"python-version:\s*['\"]?([^'\"\s]+)", text)
        assert versions, f"{path} mentions python-version but yields no value"
        for version in versions:
            assert re.fullmatch(r"3\.11\.\d+", version), (
                f"{path}: python-version {version!r} is not a full 3.11 patch"
            )


def test_every_workflow_pins_the_same_python_patch() -> None:
    versions = set()
    for path in _files_with_python_pin():
        versions.update(
            re.findall(
                r"python-version:\s*['\"]?([^'\"\s]+)",
                path.read_text(encoding="utf-8"),
            )
        )
    assert len(versions) == 1, (
        f"workflows disagree about the interpreter patch: {sorted(versions)} — one value, "
        "and it must have a build on every runner OS (3.11.9 is the newest 3.11 with a "
        "Windows x64 build; later patches are security-only and Linux-only)"
    )


def test_release_pins_the_nsis_version() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    match = re.search(r"choco install nsis(?P<args>[^\n]*)", text)
    assert match, "release.yml no longer installs NSIS"
    assert re.search(r"--version=\d+\.\d+", match.group("args")), (
        "NSIS is installed without an explicit version — the toolchain floats"
    )


def test_build_installer_defaults_to_the_manifest_version() -> None:
    module = _load_build_installer()
    assert module.APP_VERSION == MANIFEST_VERSION


def test_release_emits_and_uploads_build_evidence() -> None:
    text = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "scripts/emit_build_evidence.py" in text
    assert "--require-complete" in text
    assert "dist/build-evidence.json" in text
    assert "name: Upload build evidence" in text


def test_build_evidence_reports_the_live_toolchain() -> None:
    assert collect(commit="abc", run_id="1").get("commit") == "abc"
    assert collect(commit="abc", run_id="1")["run_id"] == "1"
    evidence = collect(commit="abc", run_id="1")
    assert evidence["python"]["version"]
    assert set(evidence["distribution_versions"]) == {
        "pyinstaller",
        "pyinstaller-hooks-contrib",
        "setuptools",
        "wheel",
    }
    # The dict the workflow serialises must be JSON-safe.
    json.dumps(evidence)


def test_build_evidence_completeness_is_checked_from_the_data() -> None:
    complete = {
        "distribution_versions": {
            "pyinstaller": "6.22.3",
            "pyinstaller-hooks-contrib": "2026.8",
            "setuptools": "82.0.0",
            "wheel": "0.48.0",
        },
        "uv": "0.12.23",
        "nsis": "3.13.0",
    }
    assert missing_required(complete) == []
    incomplete = {**complete, "nsis": None}
    assert missing_required(incomplete) == ["nsis"]
    assert missing_required({**complete, "uv": None, "nsis": None}) == ["uv", "nsis"]


def test_emit_build_evidence_requires_complete_when_asked(tmp_path: Path, monkeypatch) -> None:
    from scripts import emit_build_evidence as evidence

    output = tmp_path / "evidence.json"
    incomplete = {
        "distribution_versions": {
            "pyinstaller": "6.22.3",
            "pyinstaller-hooks-contrib": "2026.8",
            "setuptools": "82.0.0",
            "wheel": None,
        },
        "uv": None,
        "nsis": None,
    }
    monkeypatch.setattr(evidence, "collect", lambda **_kwargs: dict(incomplete))
    assert evidence.main(["--output", str(output)]) == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["complete"] is False
    assert evidence.main(["--output", str(output), "--require-complete"]) == 2
