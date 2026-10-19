"""Collected-file attribution must include hooks and exact vendored wheel copies."""

import csv
from importlib.metadata import PathDistribution
from pathlib import Path

import pytest
from installer.frozen_inventory import collected_metadata


def _wheel(root: Path, name: str, version: str, module: str) -> PathDistribution:
    info = root / f"{name}-{version}.dist-info"
    info.mkdir(parents=True)
    source = root / module
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("# collected code\n", encoding="utf-8")
    (info / "METADATA").write_text(
        f"Name: {name}\nVersion: {version}\nLicense-Expression: MIT\n", encoding="utf-8"
    )
    (info / "LICENSE").write_text("MIT License", encoding="utf-8")
    with (info / "RECORD").open("w", newline="", encoding="utf-8") as output:
        csv.writer(output).writerows((p.relative_to(root).as_posix(), "", "")
                                    for p in root.rglob("*") if p.is_file())
    return PathDistribution(info)


def test_hook_owner_outside_required_closure_is_included(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, "Hook-Lib", "1.2", "hook_lib/__init__.py")
    rows = [("hook_lib", str(tmp_path / "hook_lib/__init__.py"), "PYMODULE")]
    additions, manifest = collected_metadata(rows, [], [], distributions=[wheel])
    assert manifest["distributions"] == [{
        "name": "Hook-Lib", "version": "1.2", "metadata_path": "Hook-Lib-1.2.dist-info",
        "container": None,
    }]
    assert manifest["python_modules"] == ["hook_lib"]
    assert manifest["module_owners"] == {"hook_lib": "Hook-Lib-1.2.dist-info"}
    assert any(dest.endswith("/LICENSE") for dest, _source, _kind in additions)


def test_vendored_record_precedes_container_and_preserves_both_versions(tmp_path: Path) -> None:
    vendor_root = tmp_path / "setuptools/_vendor"
    _wheel(vendor_root, "packaging", "26.0", "packaging/__init__.py")
    container = _wheel(tmp_path, "setuptools", "82.0.0", "setuptools/__init__.py")
    installed_root = tmp_path / "other"
    installed = _wheel(installed_root, "packaging", "26.3", "packaging/__init__.py")
    rows = [("setuptools._vendor.packaging", str(vendor_root / "packaging/__init__.py"), "PYMODULE"),
            ("packaging", str(installed_root / "packaging/__init__.py"), "PYMODULE")]
    _additions, manifest = collected_metadata(rows, [], [], distributions=[container, installed])
    packaging = [r for r in manifest["distributions"] if r["name"] == "packaging"]
    assert {r["version"] for r in packaging} == {"26.0", "26.3"}
    vendor = next(r for r in packaging if r["version"] == "26.0")
    assert vendor["container"] == {"name": "setuptools", "version": "82.0.0"}
    assert vendor["metadata_path"].startswith("ogp-vendored/setuptools/")
    assert manifest["module_owners"]["setuptools._vendor.packaging"] == vendor["metadata_path"]


def test_unowned_collected_wheel_file_refuses_build(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, "Hook-Lib", "1.2", "hook_lib/__init__.py")
    source = tmp_path / "unrecorded.py"
    source.write_text("# unowned\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="no RECORD owner"):
        collected_metadata([("unrecorded", str(source), "PYMODULE")], [], [], distributions=[wheel])


def test_uninstalled_required_wheel_refuses_build(tmp_path: Path) -> None:
    wheel = _wheel(tmp_path, "Hook-Lib", "1.2", "hook_lib/__init__.py")
    with pytest.raises(RuntimeError, match="Required distribution"):
        collected_metadata([], [], [], required_names=["missing"], distributions=[wheel])


@pytest.mark.parametrize("surface", ["binaries", "datas", "scripts"])
def test_non_pyz_inputs_also_select_their_wheel_owner(tmp_path: Path, surface: str) -> None:
    wheel = _wheel(tmp_path, "Hook-Lib", "1.2", "hook_lib/collected.bin")
    row = ("collected.bin", str(tmp_path / "hook_lib/collected.bin"), "DATA")
    args = {"binaries": [], "datas": [], "scripts": []}
    args[surface] = [row]
    _additions, manifest = collected_metadata([], distributions=[wheel], **args)
    assert manifest["distributions"][0]["name"] == "Hook-Lib"
    key = "script_owners" if surface == "scripts" else "file_owners"
    assert manifest[key] == {"collected.bin": "Hook-Lib-1.2.dist-info"}
