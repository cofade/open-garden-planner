"""The MSIX packaging script and its release-workflow wiring (issue #375, ADR-073).

The script is pure where it can be (manifest, version, identity, mapping) so
these tests run on every CI OS without the Windows SDK. Packing itself is
covered by ``tests/integration/test_msix_packaging.py`` where ``makeappx`` exists.
"""

from __future__ import annotations

import importlib.util
import re
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

RELEASE = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
STORE_VERIFY = (ROOT / ".github/workflows/msix-store-verify.yml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- version

@pytest.mark.parametrize(("semver", "expected"), [
    ("1.37.6", "1.37.6.0"),
    ("0.0.0", "0.0.0.0"),
    (" 2.10.300 ", "2.10.300.0"),
])
def test_msix_version_is_four_part_with_zero_revision(semver: str, expected: str) -> None:
    """The Store reserves the fourth part; the first three equal the release tag."""
    assert build_msix.msix_version(semver) == expected


@pytest.mark.parametrize("bad", ["1.37", "1.37.6.1", "1.37.6-rc1", "v1.37.6", "1.37.70000", ""])
def test_msix_version_refuses_what_the_store_cannot_represent(bad: str) -> None:
    with pytest.raises(build_msix.MsixError):
        build_msix.msix_version(bad)


# --------------------------------------------------------------------------- identity

def test_identity_falls_back_to_development_placeholder() -> None:
    identity = build_msix.PackageIdentity.from_environment({})
    assert identity.placeholder is True
    assert identity.name == build_msix.DEV_IDENTITY_NAME
    assert identity.publisher.startswith("CN=")


def test_identity_reads_partner_center_values_from_the_environment() -> None:
    env = {
        build_msix.ENV_IDENTITY_NAME: "12345cofade.OpenGardenPlanner",
        build_msix.ENV_PUBLISHER: "CN=0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0",
        build_msix.ENV_PUBLISHER_DISPLAY_NAME: "cofade",
    }
    identity = build_msix.PackageIdentity.from_environment(env)
    assert identity.placeholder is False
    assert identity.name == "12345cofade.OpenGardenPlanner"
    assert identity.publisher == "CN=0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
    assert identity.publisher_display_name == "cofade"


def test_identity_name_without_publisher_is_a_configuration_error() -> None:
    """Half an identity builds a package the Store rejects AND that no longer installs locally."""
    with pytest.raises(build_msix.MsixError, match="must be set together"):
        build_msix.PackageIdentity.from_environment({build_msix.ENV_IDENTITY_NAME: "x.y"})


@pytest.mark.parametrize("publisher", ["0F1E2D3C", "O=cofade", ""])
def test_publisher_must_be_a_distinguished_name(publisher: str) -> None:
    env = {build_msix.ENV_IDENTITY_NAME: "cofade.OpenGardenPlanner", build_msix.ENV_PUBLISHER: publisher}
    with pytest.raises(build_msix.MsixError):
        build_msix.PackageIdentity.from_environment(env)


@pytest.mark.parametrize("name", ["ab", "a..b", "has space", "x" * 51, "-leading"])
def test_identity_name_follows_the_schema(name: str) -> None:
    with pytest.raises(build_msix.MsixError):
        build_msix.validate_identity_name(name)


# --------------------------------------------------------------------------- manifest

def _dev_identity() -> build_msix.PackageIdentity:
    return build_msix.PackageIdentity.from_environment({})


def test_manifest_round_trips_identity_version_and_executable() -> None:
    text = build_msix.render_manifest(_dev_identity(), "1.37.6")
    info = build_msix.parse_manifest(text)
    assert info == {
        "name": build_msix.DEV_IDENTITY_NAME,
        "publisher": build_msix.DEV_PUBLISHER,
        "version": "1.37.6.0",
        "architecture": "x64",
        "executable": "App\\OpenGardenPlanner.exe",
        "application_id": build_msix.APPLICATION_ID,
    }


def test_manifest_declares_what_a_full_trust_win32_app_needs() -> None:
    """runFullTrust, the .ogp association and the execution alias are load-bearing.

    Without the alias a Store install cannot be started with arguments at all
    (the WindowsApps folder is not user-executable), which is how the release
    gate runs ``--selftest`` and how Explorer passes a plan path.
    """
    text = build_msix.render_manifest(_dev_identity(), "1.37.6")
    assert 'EntryPoint="Windows.FullTrustApplication"' in text
    assert '<rescap:Capability Name="runFullTrust" />' in text
    assert '<uap:FileType ContentType="application/x-ogp">.ogp</uap:FileType>' in text
    assert f'<uap5:ExecutionAlias Alias="{build_msix.EXECUTION_ALIAS}" />' in text
    assert build_msix.MIN_WINDOWS_VERSION == "10.0.17763.0", (
        "Windows 10 1809 is the floor of uap5:AppExecutionAlias; raising it needs a reason in ADR-073"
    )
    assert "unvirtualizedResources" not in text, (
        "disabling file-system/registry virtualisation is a restricted capability "
        "that needs Partner Center approval; ADR-073 keeps the default container"
    )
    for logo in ("Square150x150Logo", "Square44x44Logo", "Wide310x150Logo", "StoreLogo"):
        assert f"Assets\\{logo}.png" in text


def test_manifest_is_well_formed_xml_with_one_resource_language() -> None:
    """One en-US resource: the PRI indexes language-neutral images only, and the
    Store rejects a manifest that declares languages the PRI does not carry."""
    text = build_msix.render_manifest(_dev_identity(), "1.37.6")
    assert text.count("<Resource Language=") == 1
    build_msix.parse_manifest(text)  # raises on malformed XML


def test_manifest_escapes_a_publisher_display_name_with_markup_characters() -> None:
    """Repository variables reach XML attributes and text; `&` or `"` must not break the manifest."""
    identity = build_msix.PackageIdentity("cofade.OpenGardenPlanner", 'CN=Garden & "Co"', "Garden & <Co>", False)
    text = build_msix.render_manifest(identity, "1.2.3")
    info = build_msix.parse_manifest(text)  # well-formed, or this raises
    assert info["publisher"] == 'CN=Garden & "Co"'
    assert "<PublisherDisplayName>Garden &amp; &lt;Co&gt;</PublisherDisplayName>" in text


# --------------------------------------------------------------------------- mapping + stage

def test_mapping_file_puts_the_bundle_under_app_and_the_stage_at_the_root(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle"
    (bundle / "_internal" / "sub").mkdir(parents=True)
    (bundle / "OpenGardenPlanner.exe").write_bytes(b"MZ")
    (bundle / "_internal" / "sub" / "x.dll").write_bytes(b"x")
    stage = tmp_path / "stage"
    (stage / "Assets").mkdir(parents=True)
    (stage / "AppxManifest.xml").write_text("<x/>", encoding="utf-8")
    (stage / "Assets" / "StoreLogo.png").write_bytes(b"p")
    (stage / "priconfig.xml").write_text("<x/>", encoding="utf-8")
    mapping = stage / "mapping.txt"

    count = build_msix.write_mapping_file(bundle, stage, mapping)

    lines = mapping.read_text(encoding="utf-8").splitlines()
    assert count == 2
    assert lines[0] == "[Files]"
    assert f'"{bundle / "OpenGardenPlanner.exe"}" "App\\OpenGardenPlanner.exe"' in lines
    assert f'"{bundle / "_internal" / "sub" / "x.dll"}" "App\\_internal\\sub\\x.dll"' in lines
    assert f'"{stage / "AppxManifest.xml"}" "AppxManifest.xml"' in lines
    assert f'"{stage / "Assets" / "StoreLogo.png"}" "Assets\\StoreLogo.png"' in lines
    assert not any("priconfig.xml" in line or "mapping.txt" in line for line in lines), (
        "makepri's config and the mapping file itself must not ship inside the package"
    )


def test_mapping_file_ships_one_pri_and_no_split_resource_packs(tmp_path: Path) -> None:
    """makepri's default config splits scale-125..400 into resources.scale-*.pri resource
    packs that nothing registers; one resources.pri must carry every qualifier (review P1)."""
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "OpenGardenPlanner.exe").write_bytes(b"MZ")
    stage = tmp_path / "stage"
    stage.mkdir()
    for name in ("AppxManifest.xml", "resources.pri", "resources.scale-200.pri", "resources.language-de.pri"):
        (stage / name).write_bytes(b"x")
    mapping = stage / "mapping.txt"
    build_msix.write_mapping_file(bundle, stage, mapping)
    targets = [line.rsplit('"', 2)[1] for line in mapping.read_text(encoding="utf-8").splitlines()[1:]]
    assert "resources.pri" in targets
    assert not [t for t in targets if t.startswith("resources.") and t != "resources.pri"], targets


def test_pri_config_has_no_automatic_resource_packs() -> None:
    config = build_msix.render_pri_config()
    assert "autoResourcePackage" not in config
    assert 'qualifier name="Scale"' in config and 'qualifier name="Language" value="en-US"' in config


def test_stage_writes_manifest_and_every_logo_the_manifest_references(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    manifest = build_msix.build_stage(_dev_identity(), "1.37.6", stage)
    text = manifest.read_text(encoding="utf-8")
    referenced = set(re.findall(r"Assets\\([A-Za-z0-9]+\.png)", text))
    assert referenced, "the manifest references no assets at all"
    present = {p.name for p in (stage / "Assets").iterdir()}
    assert referenced <= present, f"manifest references missing assets: {referenced - present}"
    # Every scale and the taskbar/Explorer target sizes exist for the 44 px icon.
    for scale in build_msix.SCALES:
        assert f"Square44x44Logo.scale-{scale}.png" in present
    for size in build_msix.TARGET_SIZES:
        assert f"Square44x44Logo.targetsize-{size}.png" in present
        assert f"Square44x44Logo.targetsize-{size}_altform-unplated.png" in present
        assert f"{build_msix.FILE_TYPE_LOGO}.targetsize-{size}.png" in present


def test_generated_logo_has_the_pixel_size_its_name_claims(tmp_path: Path) -> None:
    from PIL import Image

    assets = tmp_path / "Assets"
    build_msix.generate_assets(ROOT / "installer" / "ogp_app.ico", ROOT / "installer" / "ogp_file.ico", assets)
    with Image.open(assets / "Square150x150Logo.scale-200.png") as image:
        assert image.size == (300, 300)
        assert image.mode == "RGBA"
    with Image.open(assets / "Wide310x150Logo.png") as image:
        assert image.size == (310, 150)
    with Image.open(assets / "Square44x44Logo.targetsize-256.png") as image:
        assert image.size == (256, 256)


def test_build_refuses_a_missing_bundle(tmp_path: Path) -> None:
    with pytest.raises(build_msix.MsixError, match="frozen bundle not found"):
        build_msix.build("1.37.6", tmp_path / "nope", tmp_path / "out", identity=_dev_identity(),
                         stage_dir=tmp_path / "stage", dry_run=True)


def test_verify_package_rejects_a_container_without_the_app(tmp_path: Path) -> None:
    fake = tmp_path / "x.msix"
    with zipfile.ZipFile(fake, "w") as archive:
        archive.writestr("AppxManifest.xml", build_msix.render_manifest(_dev_identity(), "1.0.0"))
    with pytest.raises(build_msix.MsixError, match="lacks"):
        build_msix.verify_package(fake)


# --------------------------------------------------------------------------- SDK discovery

def test_find_sdk_tool_prefers_the_explicit_override(tmp_path: Path) -> None:
    (tmp_path / "makeappx.exe").write_bytes(b"MZ")
    env = {build_msix.ENV_SDK_BIN: str(tmp_path), "PATH": ""}
    assert build_msix.find_sdk_tool("makeappx.exe", env) == tmp_path / "makeappx.exe"


def test_find_sdk_tool_refuses_an_override_that_lacks_the_tool(tmp_path: Path) -> None:
    """PF-CI-20: an explicit folder that does not hold the tool must not fall through to another copy."""
    env = {build_msix.ENV_SDK_BIN: str(tmp_path), "PATH": ""}
    with pytest.raises(build_msix.MsixError, match=build_msix.ENV_SDK_BIN):
        build_msix.find_sdk_tool("makeappx.exe", env)


def test_find_sdk_tool_picks_the_newest_windows_kit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_msix.shutil, "which", lambda _name: None)
    kits = tmp_path / "Windows Kits" / "10" / "bin"
    for version in ("10.0.19041.0", "10.0.26100.0", "10.0.22621.0"):
        folder = kits / version / "x64"
        folder.mkdir(parents=True)
        (folder / "makeappx.exe").write_bytes(b"MZ")
    env = {"ProgramFiles(x86)": str(tmp_path), "ProgramFiles": str(tmp_path / "none")}
    found = build_msix.find_sdk_tool("makeappx.exe", env)
    assert found == kits / "10.0.26100.0" / "x64" / "makeappx.exe"


def test_find_sdk_tool_reports_absence_instead_of_guessing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_msix.shutil, "which", lambda _name: None)
    env = {"ProgramFiles(x86)": str(tmp_path), "ProgramFiles": str(tmp_path)}
    assert build_msix.find_sdk_tool("makeappx.exe", env) is None


# --------------------------------------------------------------------------- release.yml wiring

def _step(text: str, name: str) -> str:
    """One step's code, comment lines removed (a comment about the next step
    must not make an assertion about this one pass or fail)."""
    start = text.index(f"- name: {name}")
    after = text[start + 1:]
    match = re.search(r"\n {6}- (?:name|uses):", after)
    block = text[start: start + 1 + match.start()] if match else text[start:]
    return "\n".join(line for line in block.splitlines() if not line.lstrip().startswith("#"))


def test_the_release_builds_the_store_package_after_the_release_and_cannot_fail_it() -> None:
    """ADR-044's placement lesson applied to the Store channel (ADR-073, criterion 5 of #375).

    The MSIX is built from the SAME bundle the installer was built from, after
    `Create GitHub Release` and after the attestation, with `continue-on-error`:
    a missing SDK tool, a Partner Center identity typo or a makeappx regression
    must never cost the GitHub release, which stays the primary channel.
    """
    create = RELEASE.index("- name: Create GitHub Release")
    attest = RELEASE.index("- name: Attest build provenance")
    msix = RELEASE.index("- name: Build the Microsoft Store package (MSIX)")
    upload = RELEASE.index("- name: Upload the Store package")
    assert create < attest < msix < upload

    step = _step(RELEASE, "Build the Microsoft Store package (MSIX)")
    assert "continue-on-error: true" in step
    assert "python installer/build_msix.py" in step
    assert "--version ${{ steps.version.outputs.version }}" in step
    for var in ("OGP_MSIX_IDENTITY_NAME", "OGP_MSIX_PUBLISHER", "OGP_MSIX_PUBLISHER_DISPLAY_NAME"):
        assert f"{var}: ${{{{ vars.{var} }}}}" in step, f"{var} is not mapped from a repository variable"
    assert "--sign-test" not in step, "a Store upload is unsigned; Microsoft signs it after certification"

    upload_step = _step(RELEASE, "Upload the Store package")
    assert "continue-on-error: true" in upload_step
    assert "if-no-files-found: warn" in upload_step
    assert ".msix" in upload_step


def test_the_store_package_is_not_a_release_asset() -> None:
    """An unsigned MSIX cannot be installed by a user; attaching it would only confuse.

    It is a workflow artifact for the owner's Partner Center upload until a Store
    listing exists; the attestation subject list stays exactly what ADR-044 pinned.
    """
    create_step = _step(RELEASE, "Create GitHub Release")
    assert ".msix" not in create_step
    attest_step = _step(RELEASE, "Attest build provenance")
    assert ".msix" not in attest_step


def test_the_store_verify_workflow_installs_and_selftests_the_package() -> None:
    """The measurement the spike exists for (ADR-073): a REAL install of the
    test-signed package, started through its execution alias with --selftest."""
    assert "workflow_dispatch:" in STORE_VERIFY
    triggers = STORE_VERIFY[STORE_VERIFY.index("\non:\n"): STORE_VERIFY.index("\npermissions:")]
    assert "push:" not in triggers, "never on a push: it costs a Windows build and an app install"
    paths = re.findall(r'^      - "([^"]+)"$', triggers, re.MULTILINE)
    assert paths == ["installer/build_msix.py", ".github/workflows/msix-store-verify.yml"], (
        "on pull requests only when the packaging itself changes; frozen-selftest.yml "
        "already gates every shipped-code change"
    )
    assert "python installer/build_installer.py --skip-nsis" in STORE_VERIFY
    assert "python installer/build_msix.py" in STORE_VERIFY and "--sign-test" in STORE_VERIFY
    assert "Add-AppxPackage" in STORE_VERIFY
    assert "Cert:\\LocalMachine\\TrustedPeople" in STORE_VERIFY
    assert f"{build_msix.EXECUTION_ALIAS}" in STORE_VERIFY and "--selftest" in STORE_VERIFY
    assert "Remove-AppxPackage" in STORE_VERIFY
    assert "permissions:\n  contents: read" in STORE_VERIFY
