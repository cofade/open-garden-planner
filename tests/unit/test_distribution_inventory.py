"""Third-party notices + SBOM from the frozen bundle (AUD-051/AUD-055)."""

import json
from pathlib import Path

import pytest
from scripts import generate_distribution_inventory as inventory
from scripts.generate_distribution_inventory import (
    InventoryError,
    _check,
    collect_records,
    describe,
    main,
    render_notices,
    render_sbom,
)

ROOT = Path(__file__).resolve().parents[2]

MIT_TEXT = "MIT License\n\nPermission is hereby granted, free of charge ...\n"


def _write_dist_info(bundle: Path, name: str, version: str, *, license_line: str = "License: MIT",
                     license_file: bool = True, classifier: str | None = None) -> Path:
    dist_info = bundle / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    metadata = [
        "Metadata-Version: 2.1",
        f"Name: {name}",
        f"Version: {version}",
        license_line,
    ]
    if classifier:
        metadata.append(f"Classifier: {classifier}")
    (dist_info / "METADATA").write_text("\n".join(metadata) + "\n", encoding="utf-8")
    if license_file:
        (dist_info / "LICENSE").write_text(MIT_TEXT, encoding="utf-8")
    return dist_info


@pytest.fixture()
def bundle(tmp_path: Path) -> Path:
    root = tmp_path / "bundle" / "_internal"
    _write_dist_info(root, "Example-Lib", "1.2.3")
    _write_dist_info(
        root,
        "Classified",
        "4.5.6",
        license_line="License: UNKNOWN",
        license_file=False,
        classifier="License :: OSI Approved :: Apache Software License",
    )
    return tmp_path / "bundle"


def test_describe_reads_spdx_and_text(bundle: Path) -> None:
    record = describe(bundle / "_internal" / "Example-Lib-1.2.3.dist-info")
    assert record["name"] == "Example-Lib"
    assert record["canonical_name"] == "example-lib"
    assert record["version"] == "1.2.3"
    assert record["spdx"] == "MIT"
    assert MIT_TEXT.strip() in str(record["license_texts"][0])


def test_describe_falls_back_to_the_classifier(bundle: Path) -> None:
    record = describe(bundle / "_internal" / "Classified-4.5.6.dist-info")
    assert record["spdx"] == "Apache-2.0"


def test_describe_fails_closed_without_any_license(tmp_path: Path) -> None:
    dist_info = _write_dist_info(
        tmp_path / "b", "Mystery", "1.0", license_line="License: ", license_file=False
    )
    with pytest.raises(InventoryError, match="Mystery"):
        describe(dist_info)


def test_collect_records_sorts_and_is_non_empty(bundle: Path) -> None:
    records = collect_records(bundle)
    assert [r["canonical_name"] for r in records] == ["classified", "example-lib"]


def test_render_notices_and_sbom_are_complete(bundle: Path) -> None:
    records = collect_records(bundle)
    notices = render_notices(records, "9.9.9")
    assert "Example-Lib 1.2.3" in notices and "MIT" in notices and "Permission is hereby granted" in notices

    sbom = render_sbom(records, "9.9.9")
    assert sbom["bomFormat"] == "CycloneDX" and sbom["specVersion"] == "1.5"
    names = [c["name"] for c in sbom["components"]]
    assert names == ["classified", "example-lib"]
    purls = {c["name"]: c["purl"] for c in sbom["components"]}
    assert purls["example-lib"] == "pkg:pypi/example-lib@1.2.3"


def test_sbom_uses_name_for_non_spdx_license_strings(tmp_path: Path) -> None:
    dist_info = _write_dist_info(
        tmp_path / "b", "Vague", "1.0", license_line="License: MIT License (see file)"
    )
    record = describe(dist_info)
    component = render_sbom([record], "1.0")["components"][0]
    assert component["licenses"] == [{"license": {"name": "MIT License (see file)"}}]


def test_sbom_uses_expression_for_compound_spdx(tmp_path: Path) -> None:
    dist_info = _write_dist_info(
        tmp_path / "b", "Compound", "1.0", license_line="License: Apache-2.0 OR BSD-3-Clause"
    )
    record = describe(dist_info)
    component = render_sbom([record], "1.0")["components"][0]
    assert component["licenses"] == [{"expression": "Apache-2.0 OR BSD-3-Clause"}]


def test_qt_runtime_wheels_get_a_verified_spdx_id(tmp_path: Path) -> None:
    """The Qt runtime wheels say "LGPL v3"; the SBOM must carry the SPDX id."""
    dist_info = _write_dist_info(
        tmp_path / "b", "PyQt6-Qt6", "6.11.0", license_line="License: LGPL v3"
    )
    record = describe(dist_info)
    assert record["spdx"] == "LGPL-3.0-only"
    assert render_sbom([record], "1.0")["components"][0]["licenses"] == [
        {"license": {"id": "LGPL-3.0-only"}}
    ]


def test_sbom_uses_id_for_spdx_identifiers(bundle: Path) -> None:
    record = describe(bundle / "_internal" / "Example-Lib-1.2.3.dist-info")
    component = render_sbom([record], "1.0")["components"][0]
    assert component["licenses"] == [{"license": {"id": "MIT"}}]


def test_generate_then_check_passes_on_a_fixture(bundle: Path, tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    assert main(["--bundle", str(bundle), "--output-dir", str(out)]) == 0
    assert (out / "ogp-sbom.cdx.json").is_file()
    assert (out / "THIRD_PARTY_NOTICES.md").is_file()

    monkeypatch.setattr(inventory, "_expected_from_environment", lambda: {"classified", "example-lib"})
    assert main(["--bundle", str(bundle), "--output-dir", str(out), "--check"]) == 0

    on_disk = json.loads((out / "ogp-sbom.cdx.json").read_text(encoding="utf-8"))
    on_disk["components"].pop()
    (out / "ogp-sbom.cdx.json").write_text(json.dumps(on_disk), encoding="utf-8")
    assert main(["--bundle", str(bundle), "--output-dir", str(out), "--check"]) == 2


def test_check_reports_bundle_environment_drift(bundle: Path, tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    main(["--bundle", str(bundle), "--output-dir", str(out)])
    records = collect_records(bundle)
    monkeypatch.setattr(
        inventory, "_expected_from_environment", lambda: {"classified", "example-lib", "missing-one"}
    )
    problems = _check(out, None, records)
    assert any("missing-one" in p for p in problems)

    monkeypatch.setattr(inventory, "_expected_from_environment", lambda: {"classified"})
    problems = _check(out, None, records)
    assert any("example-lib" in p for p in problems)


def test_check_validates_versions_against_the_lock(bundle: Path, tmp_path: Path, monkeypatch) -> None:
    out = tmp_path / "out"
    main(["--bundle", str(bundle), "--output-dir", str(out)])
    records = collect_records(bundle)
    monkeypatch.setattr(inventory, "_expected_from_environment", lambda: {"classified", "example-lib"})
    lock = tmp_path / "pylock.toml"
    lock.write_text(
        "lock-version = '1.0'\n"
        "[[packages]]\nname = 'example-lib'\nversion = '9.9.9'\n"
        "[[packages]]\nname = 'classified'\nversion = '4.5.6'\n",
        encoding="utf-8",
    )
    problems = _check(out, lock, records)
    assert any("example-lib" in p and "9.9.9" in p for p in problems)

    lock.write_text(
        "lock-version = '1.0'\n"
        "[[packages]]\nname = 'example-lib'\nversion = '1.2.3'\n"
        "[[packages]]\nname = 'classified'\nversion = '4.5.6'\n",
        encoding="utf-8",
    )
    assert _check(out, lock, records) == []


def test_missing_bundle_fails(tmp_path: Path) -> None:
    assert main(["--bundle", str(tmp_path / "nope"), "--output-dir", str(tmp_path)]) == 2


def test_vendored_bundle_extras_are_expected_components() -> None:
    assert "importlib-metadata" in inventory.VENDORED_BUNDLE_EXTRAS
    assert "importlib-metadata" in inventory._expected_from_environment(), (
        "PyInstaller's vendored importlib_metadata must be expected, not reported as drift"
    )


def test_vendored_extras_are_exempt_from_the_lock_identity_check(
    tmp_path: Path, monkeypatch
) -> None:
    bundle = tmp_path / "bundle"
    _write_dist_info(bundle / "_internal", "importlib-metadata", "8.7.1")
    out = tmp_path / "out"
    assert main(["--bundle", str(bundle), "--output-dir", str(out)]) == 0
    records = collect_records(bundle)
    monkeypatch.setattr(inventory, "_expected_from_environment", lambda: {"importlib-metadata"})
    lock = tmp_path / "pylock.toml"
    lock.write_text("lock-version = '1.0'\n", encoding="utf-8")
    assert _check(out, lock, records) == []


def test_spec_bundles_metadata_and_installer_carries_notices() -> None:
    spec = (ROOT / "installer" / "ogp.spec").read_text(encoding="utf-8")
    assert "runtime_distribution_names()" in spec
    nsi = (ROOT / "installer" / "ogp_installer.nsi").read_text(encoding="utf-8")
    assert 'File "/oname=THIRD_PARTY_NOTICES.md"' in nsi
    assert '!error "NOTICES_FILE is not defined' in nsi, (
        "a missing notices file must fail the NSIS compile, not silently ship without it"
    )
    assert '!error "NOTICES_FILE does not exist' in nsi
    builder = (ROOT / "installer" / "build_installer.py").read_text(encoding="utf-8")
    assert "generate_distribution_inventory.py" in builder
    assert "/DNOTICES_FILE=" in builder


@pytest.mark.skipif(
    not (ROOT / "dist" / "OpenGardenPlanner").is_dir(),
    reason="no frozen bundle in this checkout",
)
def test_real_frozen_bundle_passes_the_inventory_check() -> None:
    """The authoritative run: this checkout's bundle, checked against the lock.

    Only meaningful when the interpreter running the test is the one that built
    the bundle — which is exactly how ``installer/build_installer.py`` runs it
    during a real build. A checkout whose bundle came from a different
    environment is not a product defect, so that case skips with the reason.
    """
    import sys

    interpreter = f"{sys.version_info.major}.{sys.version_info.minor}"
    bundle = ROOT / "dist" / "OpenGardenPlanner"
    bundled = {str(record["canonical_name"]) for record in collect_records(bundle)}
    if bundled != inventory._expected_from_environment():
        pytest.skip(f"frozen bundle in dist/ was not built with Python {interpreter}")
    assert main(["--bundle", str(bundle), "--output-dir", str(ROOT / "dist")]) == 0
    assert main(["--bundle", str(bundle), "--output-dir", str(ROOT / "dist"),
                 "--lock", str(ROOT / "pylock.toml"), "--check"]) == 0
