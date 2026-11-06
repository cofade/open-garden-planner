"""Package the frozen bundle as an MSIX for the Microsoft Store (issue #375).

Usage:
    python installer/build_msix.py --version 1.37.6 [--bundle dist/OpenGardenPlanner]
                                   [--output dist] [--sign-test] [--dry-run]
    python installer/build_msix.py --check dist/OpenGardenPlanner-v1.37.6.msix

What it produces
    dist/OpenGardenPlanner-v<version>.msix          the package (unsigned unless --sign-test)
    dist/OpenGardenPlanner-v<version>.msix.json     identity, inputs and placeholder flag
    build/msix/                                     stage: AppxManifest.xml, Assets/, resources.pri,
                                                    the makeappx mapping file

Why a separate script and not a flag of build_installer.py
    The NSIS installer and the MSIX package are two distribution channels of the
    SAME frozen bundle (ADR-073). This script never runs PyInstaller: it packages
    whatever ``--bundle`` points at, so the Store package and the installer are
    byte-for-byte the same application, built once.

Identity
    A Store submission is accepted only when the manifest's Identity Name and
    Publisher are the ones Partner Center assigned to the app. They come from the
    environment (``OGP_MSIX_IDENTITY_NAME``, ``OGP_MSIX_PUBLISHER``,
    ``OGP_MSIX_PUBLISHER_DISPLAY_NAME``; CI maps repository variables onto them)
    and fall back to development placeholders that build and install locally but
    that the Store rejects. The sidecar JSON says which of the two was used.

Tools
    ``makeappx.exe`` and ``makepri.exe`` (and ``signtool.exe`` for ``--sign-test``)
    come from the Windows 10/11 SDK; ``find_sdk_tool`` searches
    ``OGP_WINDOWS_SDK_BIN``, PATH and the Windows Kits folders. The NuGet package
    ``Microsoft.Windows.SDK.BuildTools`` carries the same three binaries for a
    machine without the SDK (docs/07 §7.2a).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent.parent
INSTALLER_DIR = ROOT / "installer"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build" / "msix"

APP_NAME = "Open Garden Planner"
APP_EXE_NAME = "OpenGardenPlanner"
APP_DESCRIPTION = (
    "Precision garden planning with CAD-like metric accuracy: beds, plants, "
    "sun and shade, a 3D view and a yearly task calendar."
)
#: The manifest's Application Id and the app execution alias. The alias puts
#: ``OpenGardenPlanner.exe`` on the user's PATH (``%LOCALAPPDATA%\Microsoft\WindowsApps``),
#: which is the ONLY way for a shell to start a Store-installed exe with
#: arguments (the frozen self-test, an MCP client): the package folder under
#: WindowsApps is not directly executable by the user. A double-clicked .ogp
#: reaches the app through the file-type association, not the alias.
APPLICATION_ID = "OpenGardenPlanner"
EXECUTION_ALIAS = "OpenGardenPlanner.exe"

#: Development placeholders. They build and (test-signed) install; the Store
#: rejects them because they are not the identity Partner Center assigned.
DEV_IDENTITY_NAME = "OpenGardenPlanner.Dev"
DEV_PUBLISHER = "CN=OpenGardenPlanner-Dev"
DEV_PUBLISHER_DISPLAY_NAME = "cofade"

ENV_IDENTITY_NAME = "OGP_MSIX_IDENTITY_NAME"
ENV_PUBLISHER = "OGP_MSIX_PUBLISHER"
ENV_PUBLISHER_DISPLAY_NAME = "OGP_MSIX_PUBLISHER_DISPLAY_NAME"
ENV_SDK_BIN = "OGP_WINDOWS_SDK_BIN"

#: Windows 10 1809 is the floor: ``uap5:AppExecutionAlias`` and the desktop
#: ``runFullTrust`` packaging the app needs both exist there, and it is the
#: oldest release the Qt 6 wheels in the bundle support.
MIN_WINDOWS_VERSION = "10.0.17763.0"
MAX_VERSION_TESTED = "10.0.26100.0"

#: Logo files the manifest references (base name -> square size at scale 100).
#: Scale variants (125/150/200/400) and target sizes are generated for each so
#: the Store's asset check and the Start menu / taskbar get a crisp image; the
#: unqualified file at scale 100 is what Windows falls back to without a PRI.
SQUARE_LOGOS: dict[str, int] = {
    "Square44x44Logo": 44,
    "Square150x150Logo": 150,
    "Square310x310Logo": 310,
    "StoreLogo": 50,
}
WIDE_LOGO = ("Wide310x150Logo", (310, 150))
FILE_TYPE_LOGO = "OgpFileType"
SCALES = (100, 125, 150, 200, 400)
TARGET_SIZES = (16, 24, 32, 48, 256)

_NS = {
    "": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "uap5": "http://schemas.microsoft.com/appx/manifest/uap/windows10/5",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
}


class MsixError(RuntimeError):
    """A packaging precondition or tool failed; the message is user-facing."""


@dataclass(frozen=True)
class PackageIdentity:
    """Who the package says it is. ``placeholder`` means the Store will reject it."""

    name: str
    publisher: str
    publisher_display_name: str
    placeholder: bool

    @classmethod
    def from_environment(cls, env: dict[str, str] | None = None) -> PackageIdentity:
        """Read the Partner Center identity from the environment, or fall back."""
        env = os.environ if env is None else env
        name = env.get(ENV_IDENTITY_NAME, "").strip()
        publisher = env.get(ENV_PUBLISHER, "").strip()
        display = env.get(ENV_PUBLISHER_DISPLAY_NAME, "").strip()
        if bool(name) != bool(publisher):
            raise MsixError(
                f"{ENV_IDENTITY_NAME} and {ENV_PUBLISHER} must be set together "
                "(both come from Partner Center > Product identity)"
            )
        if name:
            validate_publisher(publisher)
            validate_identity_name(name)
            return cls(name, publisher, display or DEV_PUBLISHER_DISPLAY_NAME, placeholder=False)
        return cls(DEV_IDENTITY_NAME, DEV_PUBLISHER, display or DEV_PUBLISHER_DISPLAY_NAME,
                   placeholder=True)


_IDENTITY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{2,49}$")


def validate_identity_name(name: str) -> None:
    """The schema's rules for Identity/@Name (3-50 chars, alphanumerics, '.', '-')."""
    if not _IDENTITY_NAME_RE.match(name) or ".." in name:
        raise MsixError(f"invalid MSIX identity name {name!r}")


def validate_publisher(publisher: str) -> None:
    """Identity/@Publisher is an X.500 distinguished name; Partner Center issues ``CN=<GUID>``."""
    if not publisher.startswith("CN="):
        raise MsixError(f"MSIX publisher must be a distinguished name starting with 'CN=' ({publisher!r})")


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def msix_version(version: str) -> str:
    """``1.37.6`` -> ``1.37.6.0``: four numeric parts, revision 0 (the Store reserves it).

    Pre-release suffixes are refused on purpose: the Store cannot represent them,
    and a package whose version does not equal the release tag would mislead the
    update checker and every support conversation.
    """
    match = _SEMVER_RE.match(version.strip())
    if not match:
        raise MsixError(f"version must be MAJOR.MINOR.PATCH, got {version!r}")
    parts = [int(p) for p in match.groups()]
    if any(p > 65535 for p in parts):
        raise MsixError(f"each version part must fit 16 bits for MSIX, got {version!r}")
    return f"{parts[0]}.{parts[1]}.{parts[2]}.0"


def render_manifest(identity: PackageIdentity, version: str) -> str:
    """The AppxManifest.xml for one build. Pure: no I/O, no environment."""
    from xml.sax.saxutils import escape, quoteattr

    v4 = msix_version(version)
    publisher_attr = quoteattr(identity.publisher)  # includes the surrounding quotes
    display_text = escape(identity.publisher_display_name)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Package
  xmlns="{_NS['']}"
  xmlns:uap="{_NS['uap']}"
  xmlns:uap5="{_NS['uap5']}"
  xmlns:rescap="{_NS['rescap']}"
  IgnorableNamespaces="uap uap5 rescap">

  <Identity Name="{identity.name}"
            Publisher={publisher_attr}
            Version="{v4}"
            ProcessorArchitecture="x64" />

  <Properties>
    <DisplayName>{APP_NAME}</DisplayName>
    <PublisherDisplayName>{display_text}</PublisherDisplayName>
    <Logo>Assets\\StoreLogo.png</Logo>
    <Description>{APP_DESCRIPTION}</Description>
  </Properties>

  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop"
                        MinVersion="{MIN_WINDOWS_VERSION}"
                        MaxVersionTested="{MAX_VERSION_TESTED}" />
  </Dependencies>

  <Resources>
    <Resource Language="en-US" />
  </Resources>

  <Applications>
    <Application Id="{APPLICATION_ID}"
                 Executable="App\\{APP_EXE_NAME}.exe"
                 EntryPoint="Windows.FullTrustApplication">
      <uap:VisualElements DisplayName="{APP_NAME}"
                          Description="{APP_DESCRIPTION}"
                          BackgroundColor="transparent"
                          Square150x150Logo="Assets\\Square150x150Logo.png"
                          Square44x44Logo="Assets\\Square44x44Logo.png">
        <uap:DefaultTile Wide310x150Logo="Assets\\Wide310x150Logo.png"
                         Square310x310Logo="Assets\\Square310x310Logo.png" />
      </uap:VisualElements>
      <Extensions>
        <uap:Extension Category="windows.fileTypeAssociation">
          <uap:FileTypeAssociation Name="ogp">
            <uap:DisplayName>{APP_NAME} Project</uap:DisplayName>
            <uap:Logo>Assets\\{FILE_TYPE_LOGO}.png</uap:Logo>
            <uap:SupportedFileTypes>
              <uap:FileType ContentType="application/x-ogp">.ogp</uap:FileType>
            </uap:SupportedFileTypes>
          </uap:FileTypeAssociation>
        </uap:Extension>
        <uap5:Extension Category="windows.appExecutionAlias"
                        Executable="App\\{APP_EXE_NAME}.exe"
                        EntryPoint="Windows.FullTrustApplication">
          <uap5:AppExecutionAlias>
            <uap5:ExecutionAlias Alias="{EXECUTION_ALIAS}" />
          </uap5:AppExecutionAlias>
        </uap5:Extension>
      </Extensions>
    </Application>
  </Applications>

  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
</Package>
"""


def parse_manifest(text: str) -> dict[str, str]:
    """Identity, version and executable of a manifest (for tests and ``--check``)."""
    root = ET.fromstring(text)
    ns = _NS[""]
    identity = root.find(f"{{{ns}}}Identity")
    application = root.find(f"{{{ns}}}Applications/{{{ns}}}Application")
    if identity is None or application is None:
        raise MsixError("manifest has no Identity or Application element")
    return {
        "name": identity.get("Name", ""),
        "publisher": identity.get("Publisher", ""),
        "version": identity.get("Version", ""),
        "architecture": identity.get("ProcessorArchitecture", ""),
        "executable": application.get("Executable", ""),
        "application_id": application.get("Id", ""),
    }


# --------------------------------------------------------------------------- assets

def _load_icon(ico: Path, size: int):  # type: ignore[no-untyped-def]
    """The .ico frame closest to ``size`` (never upscaled past 256), as RGBA."""
    from PIL import Image

    with Image.open(ico) as image:
        frames = sorted(image.info.get("sizes", {(image.width, image.height)}))
        best = next((s for s in frames if s[0] >= size), frames[-1])
        image.size = best
        image.load()
        return image.convert("RGBA")


def _square(ico: Path, side: int):  # type: ignore[no-untyped-def]
    from PIL import Image

    source = _load_icon(ico, side)
    return source.resize((side, side), Image.Resampling.LANCZOS)


def _padded(ico: Path, box: tuple[int, int], fraction: float = 0.8):  # type: ignore[no-untyped-def]
    """The icon centred on a transparent ``box``, filling ``fraction`` of the short side."""
    from PIL import Image

    side = int(min(box) * fraction)
    icon = _square(ico, side)
    canvas = Image.new("RGBA", box, (0, 0, 0, 0))
    canvas.paste(icon, ((box[0] - side) // 2, (box[1] - side) // 2), icon)
    return canvas


def generate_assets(app_ico: Path, file_ico: Path, assets_dir: Path) -> list[Path]:
    """Write every logo the manifest and the Store expect; return the files written.

    The tiles (150, 310, wide) carry the icon on a transparent field so Windows
    draws them on the user's accent colour; the 44 px and target-size variants
    fill the frame because they are the taskbar and Explorer icons.
    """
    assets_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def save(image, name: str) -> None:  # type: ignore[no-untyped-def]
        path = assets_dir / name
        image.save(path, format="PNG", optimize=True)
        written.append(path)

    for base, side in SQUARE_LOGOS.items():
        padded = side >= 150
        for scale in SCALES:
            px = round(side * scale / 100)
            image = _padded(app_ico, (px, px)) if padded else _square(app_ico, px)
            save(image, f"{base}.scale-{scale}.png")
            if scale == 100:
                save(image, f"{base}.png")
    for size in TARGET_SIZES:
        image = _square(app_ico, size)
        save(image, f"Square44x44Logo.targetsize-{size}.png")
        save(image, f"Square44x44Logo.targetsize-{size}_altform-unplated.png")

    wide_base, (w, h) = WIDE_LOGO
    for scale in SCALES:
        image = _padded(app_ico, (round(w * scale / 100), round(h * scale / 100)))
        save(image, f"{wide_base}.scale-{scale}.png")
        if scale == 100:
            save(image, f"{wide_base}.png")

    for size in TARGET_SIZES:
        save(_square(file_ico, size), f"{FILE_TYPE_LOGO}.targetsize-{size}.png")
    save(_square(file_ico, 44), f"{FILE_TYPE_LOGO}.png")
    return written


# --------------------------------------------------------------------------- tools

def find_sdk_tool(name: str, env: dict[str, str] | None = None) -> Path | None:
    """Locate ``name`` (makeappx.exe, makepri.exe, signtool.exe).

    Order: ``OGP_WINDOWS_SDK_BIN``, PATH, then the newest ``x64`` folder under
    the Windows Kits roots (what a GitHub ``windows-latest`` runner has).
    """
    env = os.environ if env is None else env
    override = env.get(ENV_SDK_BIN, "").strip()
    if override:
        candidate = Path(override) / name
        if candidate.is_file():
            return candidate
        # An explicit folder that lacks the tool is a configuration error, not a
        # reason to fall through to some other copy (PF-CI-20 is about the wrong copy).
        raise MsixError(f"{ENV_SDK_BIN}={override!r} does not contain {name}")
    found = shutil.which(name)
    if found:
        return Path(found)
    roots = [
        Path(env.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin",
        Path(env.get("ProgramFiles", r"C:\Program Files")) / "Windows Kits" / "10" / "bin",
    ]
    candidates: list[Path] = []
    for root in roots:
        if root.is_dir():
            candidates.extend(root.glob(f"10.0.*/x64/{name}"))
    if not candidates:
        return None
    return max(candidates, key=lambda p: [int(x) for x in p.parts[-3].split(".") if x.isdigit()])


def _run(cmd: list[str], what: str, *, display: str | None = None,
         env: dict[str, str] | None = None) -> None:
    """Run one tool; ``display`` replaces the echoed command line (a script with a
    password in it is echoed as its label, never verbatim)."""
    print(f"Running: {display if display is not None else subprocess.list2cmdline(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                                encoding="utf-8", errors="replace", env=env)
    except OSError as exc:
        # WinError 14001 (side-by-side configuration) is what a makeappx.exe
        # copied WITHOUT its neighbouring DLLs raises: the tool must be used
        # from the complete SDK (or BuildTools NuGet) `bin/<version>/x64` folder.
        raise MsixError(f"{what}: {cmd[0]} could not be started ({exc})") from exc
    _emit(sys.stdout, result.stdout)
    if result.returncode != 0:
        _emit(sys.stderr, result.stderr)
        raise MsixError(f"{what} failed with exit code {result.returncode}")


def _emit(stream, text: str) -> None:  # type: ignore[no-untyped-def]
    """Print tool output without dying on a console code page (the SDK tools
    print smart quotes and box characters that cp1252 cannot encode)."""
    encoding = getattr(stream, "encoding", None) or "utf-8"
    stream.write(text.encode(encoding, errors="replace").decode(encoding, errors="replace"))
    stream.flush()


# --------------------------------------------------------------------------- stage + pack

def _package_path(rel: Path) -> str:
    """A path inside the package: backslashes on every host, as makeappx expects."""
    return "\\".join(rel.parts)


def write_mapping_file(bundle_dir: Path, stage_dir: Path, mapping_path: Path) -> int:
    """makeappx's ``/f`` mapping: the bundle under ``App\\``, the stage at the root.

    A mapping file means the 600 MiB bundle is never copied; makeappx reads the
    files where PyInstaller left them. Returns the number of bundle files mapped.
    """
    lines = ["[Files]"]
    count = 0
    for path in sorted(p for p in bundle_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(bundle_dir)
        lines.append(f'"{path}" "App\\{_package_path(rel)}"')
        count += 1
    for path in sorted(p for p in stage_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(stage_dir)
        if rel.name in {mapping_path.name, "priconfig.xml"}:
            continue
        if rel.name.startswith("resources.") and rel.suffix == ".pri" and rel.name != "resources.pri":
            # A split resource pack (resources.scale-200.pri ...) that makepri
            # writes from a config with automatic resource packages: nothing
            # registers it, so it would be inert payload. render_pri_config
            # prevents the split; this keeps a stray one out of the package.
            continue
        lines.append(f'"{path}" "{_package_path(rel)}"')
    mapping_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def build_stage(identity: PackageIdentity, version: str, stage_dir: Path,
                app_ico: Path = INSTALLER_DIR / "ogp_app.ico",
                file_ico: Path = INSTALLER_DIR / "ogp_file.ico") -> Path:
    """Write the manifest and assets into ``stage_dir``; return the manifest path."""
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True)
    manifest = stage_dir / "AppxManifest.xml"
    manifest.write_text(render_manifest(identity, version), encoding="utf-8")
    generate_assets(app_ico, file_ico, stage_dir / "Assets")
    return manifest


def render_pri_config() -> str:
    """The makepri config: ONE ``resources.pri`` carrying every scale and target size.

    ``makepri createconfig`` would add ``<autoResourcePackage qualifier="Scale"/>``
    (and Language, DXFeatureLevel), which splits scale 125-400 into
    ``resources.scale-*.pri`` resource packs that a plain MSIX never registers -
    the scaled logos would then be unreachable while the files still ship
    (review of PR #761). No automatic packages, so everything lands in the main PRI.
    """
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<resources targetOsVersion="10.0.0" majorVersion="1">
  <index root="\\" startIndexAt="\\">
    <default>
      <qualifier name="Language" value="en-US"/>
      <qualifier name="Contrast" value="standard"/>
      <qualifier name="Scale" value="100"/>
      <qualifier name="HomeRegion" value="001"/>
      <qualifier name="TargetSize" value="256"/>
      <qualifier name="LayoutDirection" value="LTR"/>
      <qualifier name="Theme" value="dark"/>
      <qualifier name="AlternateForm" value=""/>
      <qualifier name="DXFeatureLevel" value="DX9"/>
      <qualifier name="Configuration" value=""/>
      <qualifier name="DeviceFamily" value="Universal"/>
      <qualifier name="Custom" value=""/>
    </default>
    <indexer-config type="folder" foldernameAsQualifier="true" filenameAsQualifier="true" qualifierDelimiter="."/>
    <indexer-config type="resw" convertDotsToSlashes="true" initialPath=""/>
    <indexer-config type="resjson" initialPath=""/>
    <indexer-config type="PRI"/>
  </index>
</resources>
"""


def make_pri(stage_dir: Path, makepri: Path) -> Path:
    """Index the qualified assets (scale-*, targetsize-*) into one ``resources.pri``."""
    config = stage_dir / "priconfig.xml"
    config.write_text(render_pri_config(), encoding="utf-8")
    pri = stage_dir / "resources.pri"
    _run([str(makepri), "new", "/pr", str(stage_dir), "/cf", str(config),
          "/mn", str(stage_dir / "AppxManifest.xml"), "/of", str(pri), "/o"], "makepri new")
    return pri


def pack(mapping_path: Path, output: Path, makeappx: Path) -> Path:
    """``makeappx pack`` with full manifest validation (no ``/nv``)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    _run([str(makeappx), "pack", "/f", str(mapping_path), "/p", str(output), "/o"], "makeappx pack")
    return output


def sign_for_local_test(msix: Path, identity: PackageIdentity, signtool: Path) -> Path:
    """Sign with a throw-away self-signed certificate whose subject equals the publisher.

    Only for measuring the package on a developer machine or a CI runner: the
    .cer written next to the package must be imported into *Trusted People* of
    the LOCAL MACHINE before ``Add-AppxPackage`` accepts it. A Store submission
    is uploaded UNSIGNED; Microsoft signs it after certification.
    """
    cer = msix.with_suffix(".test.cer")
    pfx = msix.with_suffix(".test.pfx")
    password = "ogp-msix-test"
    # Windows PowerShell 5.1 started FROM pwsh 7 inherits a PSModulePath whose first
    # entries are the PowerShell 7 module folders; 5.1 cannot load those editions of
    # Microsoft.PowerShell.Security, and the Cert: drive is then missing
    # ("Cannot find drive 'Cert'", first run of msix-store-verify.yml on PR #761).
    # Run the script without the inherited PSModulePath and import the modules by name.
    child_env = {k: v for k, v in os.environ.items() if k.upper() != "PSMODULEPATH"}
    script = f"""
$ErrorActionPreference = 'Stop'
Import-Module Microsoft.PowerShell.Security, PKI
$cert = New-SelfSignedCertificate -Type Custom -Subject '{identity.publisher}' `
  -KeyUsage DigitalSignature -FriendlyName 'OGP MSIX test signing' `
  -CertStoreLocation 'Cert:\\CurrentUser\\My' -NotAfter (Get-Date).AddDays(30) `
  -TextExtension @('2.5.29.37={{text}}1.3.6.1.5.5.7.3.3', '2.5.29.19={{text}}')
$pw = ConvertTo-SecureString -String '{password}' -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath '{pfx}' -Password $pw | Out-Null
Export-Certificate -Cert $cert -FilePath '{cer}' | Out-Null
Remove-Item -Path ('Cert:\\CurrentUser\\My\\' + $cert.Thumbprint)
Write-Output ('thumbprint=' + $cert.Thumbprint)
"""
    _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], "test certificate",
         display="powershell <New-SelfSignedCertificate + Export-PfxCertificate script>", env=child_env)
    try:
        _run([str(signtool), "sign", "/fd", "SHA256", "/a", "/f", str(pfx), "/p", password, str(msix)],
             "signtool sign", display=f"{signtool} sign /fd SHA256 /a /f {pfx} /p <test password> {msix}")
    finally:
        with contextlib.suppress(OSError):
            pfx.unlink()
    return cer


def verify_package(msix: Path) -> dict[str, object]:
    """Open the package as the zip it is and report what it claims (``--check``)."""
    if not zipfile.is_zipfile(msix):
        raise MsixError(f"{msix} is not a zip container")
    with zipfile.ZipFile(msix) as archive:
        names = set(archive.namelist())
        required = {"AppxManifest.xml", "AppxBlockMap.xml", "[Content_Types].xml",
                    f"App/{APP_EXE_NAME}.exe"}
        missing = sorted(required - names)
        if missing:
            raise MsixError(f"{msix.name} lacks {', '.join(missing)}")
        info = parse_manifest(archive.read("AppxManifest.xml").decode("utf-8"))
        info["signed"] = "AppxSignature.p7x" in names
        info["files"] = len(names)
        info["bytes"] = msix.stat().st_size
        return info


# --------------------------------------------------------------------------- main

def build(version: str, bundle_dir: Path, output_dir: Path, *, identity: PackageIdentity,
          stage_dir: Path = BUILD_DIR, sign_test: bool = False, dry_run: bool = False,
          app_ico: Path = INSTALLER_DIR / "ogp_app.ico",
          file_ico: Path = INSTALLER_DIR / "ogp_file.ico") -> Path:
    """Stage, index, pack (and optionally test-sign) one package; return its path.

    ``dry_run`` stops after the stage and the mapping file, which is everything
    the Linux CI and the unit tests can exercise without the Windows SDK.
    """
    exe = bundle_dir / f"{APP_EXE_NAME}.exe"
    if not exe.is_file():
        raise MsixError(f"frozen bundle not found: {exe} (run installer/build_installer.py --skip-nsis first)")
    print("=" * 60)
    print(f"MSIX: {APP_NAME} v{version} ({msix_version(version)}) from {bundle_dir}")
    print(f"Identity: {identity.name} / {identity.publisher}"
          + ("  [DEVELOPMENT PLACEHOLDER - the Store rejects this identity]" if identity.placeholder else ""))
    print("=" * 60)

    build_stage(identity, version, stage_dir, app_ico=app_ico, file_ico=file_ico)
    makepri = find_sdk_tool("makepri.exe")
    makeappx = find_sdk_tool("makeappx.exe")
    if not dry_run:
        if makeappx is None:
            raise MsixError(f"makeappx.exe not found - install the Windows SDK or set {ENV_SDK_BIN}")
        if makepri is None:
            print(f"WARNING: makepri.exe not found - packaging without resources.pri "
                  f"(scaled assets will not resolve; set {ENV_SDK_BIN} for a Store-grade package)")
        else:
            make_pri(stage_dir, makepri)

    mapping = stage_dir / "mapping.txt"
    count = write_mapping_file(bundle_dir, stage_dir, mapping)
    print(f"Mapped {count} bundle files + stage into {mapping}")

    output = output_dir / f"{APP_EXE_NAME}-v{version}.msix"
    sidecar = output.with_suffix(".msix.json")
    record: dict[str, object] = {
        "version": version,
        "msix_version": msix_version(version),
        "bundle": str(bundle_dir),
        "bundle_files": count,
        "identity": asdict(identity),
        "dry_run": dry_run,
        "test_signed": False,
    }
    if dry_run:
        print("Dry run: stage and mapping written, no package produced.")
        output_dir.mkdir(parents=True, exist_ok=True)
        sidecar.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return mapping

    assert makeappx is not None
    pack(mapping, output, makeappx)
    if sign_test:
        signtool = find_sdk_tool("signtool.exe")
        if signtool is None:
            raise MsixError(f"signtool.exe not found - install the Windows SDK or set {ENV_SDK_BIN}")
        cer = sign_for_local_test(output, identity, signtool)
        record["test_signed"] = True
        record["test_certificate"] = str(cer)
        print(f"Test-signed; trust {cer} in LocalMachine\\TrustedPeople before Add-AppxPackage.")

    record["package"] = verify_package(output)
    sidecar.write_text(json.dumps(record, indent=2), encoding="utf-8")
    size_mb = output.stat().st_size / (1024 * 1024)
    print(f"\nPackage created: {output} ({size_mb:.1f} MB)")
    print(f"Record: {sidecar}")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Package {APP_NAME} as an MSIX for the Microsoft Store")
    parser.add_argument("--version", help="Release version MAJOR.MINOR.PATCH (defaults to pyproject.toml)")
    parser.add_argument("--bundle", type=Path, default=DIST_DIR / APP_EXE_NAME,
                        help="PyInstaller onedir bundle (default: dist/OpenGardenPlanner)")
    parser.add_argument("--output", type=Path, default=DIST_DIR, help="Output directory (default: dist)")
    parser.add_argument("--stage", type=Path, default=BUILD_DIR, help="Stage directory (default: build/msix)")
    parser.add_argument("--sign-test", action="store_true",
                        help="Sign with a throw-away self-signed certificate for a local install test")
    parser.add_argument("--dry-run", action="store_true",
                        help="Write the stage and mapping file only (no Windows SDK needed)")
    parser.add_argument("--check", type=Path, metavar="MSIX",
                        help="Inspect an existing package and print its identity as JSON")
    args = parser.parse_args(argv)

    try:
        if args.check is not None:
            print(json.dumps(verify_package(args.check), indent=2))
            return 0
        version = args.version
        if not version:
            sys.path.insert(0, str(INSTALLER_DIR))
            from build_installer import _manifest_version

            version = _manifest_version()
        identity = PackageIdentity.from_environment()
        build(version, args.bundle, args.output, identity=identity, stage_dir=args.stage,
              sign_test=args.sign_test, dry_run=args.dry_run)
        return 0
    except MsixError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
