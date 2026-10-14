"""End-to-end pipeline test: runtime closure -> synthetic frozen bundle -> notices + SBOM.

Exercises the real orchestrator (`installer/build_installer.run_inventory`), which shells
out to the real generator over a bundle whose ``.dist-info`` metadata is copied from the
running environment. That is what the release does with a PyInstaller bundle; the only
substitution is the artifact, so no multi-minute frozen build is needed to prove the
pipeline wires together, verifies itself, and fails on drift. Synthetic metadata
fixtures cannot prove that all frozen code is attributed; the independent executable
archive regression below covers the hook/vendoring omission found in review.
"""

import importlib.util
import json
import shutil
import sys
import tomllib
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime_closure = _load_module("ogp_runtime_closure_it", ROOT / "installer" / "runtime_closure.py")
build_installer = _load_module("ogp_build_installer_it", ROOT / "installer" / "build_installer.py")


def _dist_info_path(dist) -> Path:
    path = getattr(dist, "_path", None)
    if path is not None and str(path).endswith(".dist-info"):
        return Path(path)
    name = dist.metadata["Name"]
    for candidate in metadata.distributions():
        key = (candidate.metadata["Name"] or "").lower().replace("_", "-")
        if key == (name or "").lower().replace("_", "-") and str(
            getattr(candidate, "_path", "")
        ).endswith(".dist-info"):
            return Path(candidate._path)  # type: ignore[attr-defined]
    raise AssertionError(f"cannot locate .dist-info for {name!r}")


def _synthetic_bundle(bundle: Path) -> list[tuple[str, str]]:
    """Copy the running environment's runtime metadata into a bundle-like layout."""
    internal = bundle / "_internal"
    internal.mkdir(parents=True, exist_ok=True)
    pairs: list[tuple[str, str]] = []
    for name in runtime_closure.runtime_distribution_names():
        dist = metadata.distribution(name)
        source = _dist_info_path(dist)
        shutil.copytree(source, internal / source.name, dirs_exist_ok=True)
        pairs.append((runtime_closure.canonicalize(name), dist.version))
    return pairs


def _write_lock(path: Path, pairs: list[tuple[str, str]], *, bump: str | None = None) -> None:
    lines = ["lock-version = '1.0'", ""]
    for name, version in pairs:
        if bump and name == bump:
            version = "999.0.0"
        lines += ["[[packages]]", f"name = '{name}'", f"version = '{version}'", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def test_pipeline_generates_and_verifies_a_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "OpenGardenPlanner"
    pairs = _synthetic_bundle(bundle)
    lock = tmp_path / "pylock.toml"
    _write_lock(lock, pairs)
    output = tmp_path / "out"

    build_installer.run_inventory(bundle, output, lock, version="9.9.9")

    notices = (output / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    sbom_text = (output / "ogp-sbom.cdx.json").read_text(encoding="utf-8")
    sbom = json.loads(sbom_text)
    assert notices.startswith("# Third-party notices")
    assert "Open Garden Planner 9.9.9" in notices, (
        "the artifacts must name the version this build produces, not pyproject's"
    )
    assert sbom["metadata"]["component"]["version"] == "9.9.9"
    components = sbom["components"]
    assert sorted(c["name"] for c in components) == sorted(name for name, _ in pairs), (
        "the SBOM must describe exactly the bundled distributions"
    )
    folded = notices.lower().replace("_", "-").replace(".", "-")
    for name, _version in pairs:
        assert name in folded, f"{name} is missing from the notices"
    assert len(pairs) > 20, "the runtime closure should be non-trivial"


def test_pipeline_fails_closed_on_lock_drift(tmp_path: Path) -> None:
    bundle = tmp_path / "OpenGardenPlanner"
    pairs = _synthetic_bundle(bundle)
    lock = tmp_path / "pylock.toml"
    _write_lock(lock, pairs, bump=pairs[0][0])
    output = tmp_path / "out"

    with pytest.raises(SystemExit) as excinfo:
        build_installer.run_inventory(bundle, output, lock, version="9.9.9")
    assert excinfo.value.code == 1


def test_pipeline_records_the_version_it_was_told(tmp_path: Path) -> None:
    """The release passes its computed version; the artifacts must carry it.

    ``run_inventory`` generates and then checks, so re-running it with a different
    version simply regenerates. The version *check* is exercised where it is real:
    ``generate_distribution_inventory.py --check`` against existing artifacts
    (see ``tests/unit/test_distribution_inventory.py``).
    """
    bundle = tmp_path / "OpenGardenPlanner"
    pairs = _synthetic_bundle(bundle)
    lock = tmp_path / "pylock.toml"
    _write_lock(lock, pairs)
    output = tmp_path / "out"

    build_installer.run_inventory(bundle, output, lock, version="7.7.7")
    sbom = json.loads((output / "ogp-sbom.cdx.json").read_text(encoding="utf-8"))
    assert sbom["metadata"]["component"]["version"] == "7.7.7"
    assert "Open Garden Planner 7.7.7" in (output / "THIRD_PARTY_NOTICES.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.skipif(
    sys.version_info[:2] != (3, 11),
    reason="the committed lock is resolved for the CI Python (3.11); other interpreters "
    "may legally resolve extra marker-conditional distributions",
)
def test_the_real_lock_names_every_runtime_distribution() -> None:
    """The committed lock must cover the closure the spec bundles."""
    locked = {
        runtime_closure.canonicalize(package["name"]): package["version"]
        for package in tomllib.loads((ROOT / "pylock.toml").read_text(encoding="utf-8"))["packages"]
    }
    missing = [
        name for name in runtime_closure.runtime_distribution_names() if name not in locked
    ]
    assert missing == [], f"runtime distributions absent from pylock.toml: {missing}"


@pytest.mark.skipif(
    not (ROOT / "dist/OpenGardenPlanner/OpenGardenPlanner.exe").is_file(),
    reason="no frozen Windows artifact in this checkout",
)
def test_frozen_hook_dependencies_are_in_the_inventory() -> None:
    """An independent archive observation must catch hook/vendoring omissions."""
    readers = pytest.importorskip("PyInstaller.archive.readers")
    archive = readers.CArchiveReader(str(ROOT / "dist/OpenGardenPlanner/OpenGardenPlanner.exe"))
    pyz = archive.open_embedded_archive(next(n for n in archive.toc if n.endswith(".pyz")))
    sbom = json.loads((ROOT / "dist/ogp-sbom.cdx.json").read_text(encoding="utf-8"))
    names = {c["name"] for c in sbom["components"]}
    # These are observed frozen hook inputs, not roots in project.dependencies.
    for module, distribution in (
        ("setuptools", "setuptools"),
        ("packaging", "packaging"),
        ("setuptools._vendor.zipp", "zipp"),
    ):
        if module in pyz.toc:
            assert distribution in names, f"frozen {module} has no inventory component"


@pytest.mark.skipif(
    not (ROOT / "dist/OpenGardenPlanner/OpenGardenPlanner.exe").is_file(),
    reason="no frozen Windows artifact in this checkout",
)
def test_frozen_check_rejects_manifest_archive_drift(monkeypatch) -> None:
    """Changing ownership evidence cannot make the executable acquire a module."""
    pytest.importorskip("PyInstaller.archive.readers")
    from scripts import generate_distribution_inventory as inventory

    bundle = ROOT / "dist/OpenGardenPlanner"
    manifest = inventory._collected_manifest(bundle)
    assert manifest is not None
    manifest["python_modules"].append("invented.module")
    monkeypatch.setattr(inventory, "_collected_manifest", lambda _bundle: manifest)
    sbom = json.loads((ROOT / "dist/ogp-sbom.cdx.json").read_text(encoding="utf-8"))
    problems = inventory._check(
        ROOT / "dist", ROOT / "pylock.toml", inventory.collect_records(bundle),
        sbom["metadata"]["component"]["version"], bundle,
    )
    assert any("does not match the executable's PYZ" in problem for problem in problems)
