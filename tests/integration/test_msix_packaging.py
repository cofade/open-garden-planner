"""End-to-end: a frozen-looking bundle becomes a Store-shaped MSIX (issue #375, ADR-073).

The workflow under test is the one `release.yml` and `msix-store-verify.yml`
run: stage (manifest + assets) -> mapping file -> ``makeappx pack`` -> inspect.
On a machine without the Windows SDK the test stops after the stage and the
mapping file (the ``--dry-run`` path), which is still the whole Python side of
the pipeline; where ``makeappx.exe`` is found (a Windows dev box with the SDK,
or a ``windows-latest`` runner) it packs for real and reads the result back.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("build_msix", ROOT / "installer" / "build_msix.py")
assert _SPEC is not None and _SPEC.loader is not None
build_msix = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("build_msix", build_msix)
_SPEC.loader.exec_module(build_msix)


def _fake_bundle(root: Path) -> Path:
    """The shape of ``dist/OpenGardenPlanner`` with a few bytes in it."""
    bundle = root / "OpenGardenPlanner"
    (bundle / "_internal" / "PyQt6" / "Qt6" / "plugins").mkdir(parents=True)
    (bundle / "OpenGardenPlanner.exe").write_bytes(b"MZ" + b"\0" * 64)
    (bundle / "_internal" / "base_library.zip").write_bytes(b"PK\x05\x06" + b"\0" * 18)
    (bundle / "_internal" / "PyQt6" / "Qt6" / "plugins" / "qwindows.dll").write_bytes(b"MZ")
    (bundle / "_internal" / "ogp-collected-distributions.json").write_text("{}", encoding="utf-8")
    return bundle


def test_dry_run_stages_a_complete_package_layout(tmp_path: Path) -> None:
    """The Python half of the pipeline, on any OS: stage, mapping and the record."""
    bundle = _fake_bundle(tmp_path)
    identity = build_msix.PackageIdentity.from_environment({})

    mapping = build_msix.build("1.37.6", bundle, tmp_path / "out", identity=identity,
                               stage_dir=tmp_path / "stage", dry_run=True)

    assert mapping == tmp_path / "stage" / "mapping.txt"
    lines = mapping.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "[Files]"
    targets = [line.rsplit('"', 2)[1] for line in lines[1:]]
    assert "App\\OpenGardenPlanner.exe" in targets
    assert "App\\_internal\\PyQt6\\Qt6\\plugins\\qwindows.dll" in targets
    assert "AppxManifest.xml" in targets
    assert "Assets\\Square44x44Logo.png" in targets
    assert all(not t.startswith("App\\") or "\\" in t[4:] or t == "App\\OpenGardenPlanner.exe" for t in targets)

    record = json.loads((tmp_path / "out" / "OpenGardenPlanner-v1.37.6.msix.json").read_text(encoding="utf-8"))
    assert record["dry_run"] is True
    assert record["identity"]["placeholder"] is True
    assert record["bundle_files"] == 4
    assert record["msix_version"] == "1.37.6.0"


@pytest.mark.skipif(build_msix.find_sdk_tool("makeappx.exe") is None,
                    reason="makeappx.exe (Windows SDK) not available on this machine")
def test_makeappx_packs_the_stage_and_the_package_reads_back(tmp_path: Path) -> None:
    """The real tool validates the manifest against Microsoft's schema - the one
    check no Python test can imitate - and the package must say what we told it."""
    bundle = _fake_bundle(tmp_path)
    identity = build_msix.PackageIdentity.from_environment({})

    package = build_msix.build("1.37.6", bundle, tmp_path / "out", identity=identity,
                               stage_dir=tmp_path / "stage")

    assert package == tmp_path / "out" / "OpenGardenPlanner-v1.37.6.msix"
    info = build_msix.verify_package(package)
    assert info["name"] == build_msix.DEV_IDENTITY_NAME
    assert info["version"] == "1.37.6.0"
    assert info["executable"] == "App\\OpenGardenPlanner.exe"
    assert info["signed"] is False, "a Store upload is unsigned; --sign-test is only for a local install"
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
    assert "App/_internal/PyQt6/Qt6/plugins/qwindows.dll" in names
    assert "Assets/Square150x150Logo.scale-200.png" in names
    if build_msix.find_sdk_tool("makepri.exe") is not None:
        assert "resources.pri" in names, "makepri was available, so the scaled assets must be indexed"
    record = json.loads(package.with_suffix(".msix.json").read_text(encoding="utf-8"))
    assert record["package"]["files"] == len(names)
