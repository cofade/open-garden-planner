"""Build script for Open Garden Planner Windows installer.

Usage:
    python installer/build_installer.py [--skip-pyinstaller] [--skip-nsis]

Prerequisites:
    - PyInstaller: pip install pyinstaller
    - NSIS: https://nsis.sourceforge.io/ (must be in PATH or at default location)
"""

import argparse
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
INSTALLER_DIR = ROOT / "installer"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"


def _manifest_version() -> str:
    """Read the authoritative project version from pyproject.toml (PEP 621).

    A local build without ``--version`` must not invent a version: the update
    checker and the frozen ``_version.py`` both claim to be the manifest's, and
    CI passes the release-computed version explicitly (release.yml).
    """
    try:
        with (ROOT / "pyproject.toml").open("rb") as fh:
            return str(tomllib.load(fh)["project"]["version"])
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise SystemExit(f"Cannot read the project version from pyproject.toml: {exc}") from exc


# App metadata
APP_NAME = "Open Garden Planner"
APP_VERSION = _manifest_version()
APP_EXE_NAME = "OpenGardenPlanner"

# NSIS paths to search
NSIS_PATHS = [
    Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
    Path(r"C:\Program Files\NSIS\makensis.exe"),
]


def find_nsis() -> Path | None:
    """Find makensis.exe on the system."""
    # Check PATH first
    nsis = shutil.which("makensis")
    if nsis:
        return Path(nsis)

    # Check common install locations
    for p in NSIS_PATHS:
        if p.exists():
            return p

    return None


def _check_build_environment() -> None:
    """Warn when the venv holds a distribution the lock does not pin (#538).

    The spec repeats this check so a direct ``pyinstaller installer/ogp.spec``
    run in the Quick Reference is covered too.
    """
    try:
        from build_environment import warn_if_unpinned
    except ImportError:  # imported as `installer.build_installer` from the repo root
        from installer.build_environment import warn_if_unpinned

    warn_if_unpinned(ROOT / "pylock.toml")


def run_pyinstaller() -> None:
    """Run PyInstaller to create the standalone bundle."""
    print("=" * 60)
    print("Step 1: Building with PyInstaller")
    print("=" * 60)
    _check_build_environment()

    spec_file = INSTALLER_DIR / "ogp.spec"
    if not spec_file.exists():
        print(f"ERROR: Spec file not found: {spec_file}")
        sys.exit(1)

    # Clean previous build
    bundle_dir = DIST_DIR / APP_EXE_NAME
    if bundle_dir.exists():
        print(f"Cleaning previous build: {bundle_dir}")
        shutil.rmtree(bundle_dir)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_file),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: PyInstaller build failed!")
        sys.exit(1)

    # Verify output
    exe_path = bundle_dir / f"{APP_EXE_NAME}.exe"
    if not exe_path.exists():
        print(f"ERROR: Expected output not found: {exe_path}")
        sys.exit(1)

    # Calculate bundle size
    total_size = sum(f.stat().st_size for f in bundle_dir.rglob("*") if f.is_file())
    print(f"\nPyInstaller bundle created: {bundle_dir}")
    print(f"Bundle size: {total_size / (1024 * 1024):.1f} MB")


def run_inventory(bundle_dir: Path | None = None, output_dir: Path | None = None,
                  lock_path: Path | None = None, version: str | None = None) -> None:
    """Generate third-party notices and the SBOM from the frozen bundle (AUD-051/055).

    ``version`` MUST be the version this build is producing: ``pyproject.toml``
    lags the release tag until the post-release sync commit, so the default would
    describe the previous release.
    """
    print("\n" + "=" * 60)
    print("Step 1b: Distribution inventory (notices + SBOM)")
    print("=" * 60)

    script = ROOT / "scripts" / "generate_distribution_inventory.py"
    if not script.is_file():
        print(f"ERROR: Inventory generator not found: {script}")
        sys.exit(1)

    bundle = bundle_dir if bundle_dir is not None else DIST_DIR / APP_EXE_NAME
    output = output_dir if output_dir is not None else DIST_DIR
    lock = lock_path if lock_path is not None else ROOT / "pylock.toml"
    cmd = [sys.executable, str(script), "--bundle", str(bundle),
           "--output-dir", str(output), "--lock", str(lock),
           "--app-version", str(version if version is not None else APP_VERSION)]
    print(f"Running: {' '.join(cmd)}")
    if subprocess.run(cmd, cwd=str(ROOT)).returncode != 0:
        print("ERROR: Could not write the distribution inventory!")
        sys.exit(1)
    if subprocess.run([*cmd, "--check"], cwd=str(ROOT)).returncode != 0:
        print("ERROR: Distribution inventory check failed!")
        sys.exit(1)


def run_nsis() -> None:
    """Run NSIS to create the installer.

    ``--skip-pyinstaller`` is for iterating on the installer itself: the NSIS
    step, the inventory and the frozen ``_version.py`` all label the *existing*
    bundle, so the version passed on the command line must be the one that
    bundle was built with — otherwise the installer, SBOM and notices can claim
    a version the packaged exe does not carry (senior review round 3).
    """
    print("\n" + "=" * 60)
    print("Step 2: Building NSIS installer")
    print("=" * 60)

    nsis_exe = find_nsis()
    if nsis_exe is None:
        print("ERROR: NSIS not found!")
        print("Install from: https://nsis.sourceforge.io/")
        print("Or add makensis.exe to your PATH.")
        sys.exit(1)

    nsi_script = INSTALLER_DIR / "ogp_installer.nsi"
    if not nsi_script.exists():
        print(f"ERROR: NSIS script not found: {nsi_script}")
        sys.exit(1)

    # Verify PyInstaller output exists
    bundle_dir = DIST_DIR / APP_EXE_NAME
    if not bundle_dir.exists():
        print(f"ERROR: PyInstaller bundle not found: {bundle_dir}")
        print("Run PyInstaller first (without --skip-pyinstaller)")
        sys.exit(1)

    cmd = [
        str(nsis_exe),
        f"/DVERSION={APP_VERSION}",
        f"/DSRCDIR={bundle_dir}",
        f"/DOUTDIR={DIST_DIR}",
        f"/DLICENSE_FILE={ROOT / 'LICENSE'}",
        f"/DNOTICES_FILE={DIST_DIR / 'THIRD_PARTY_NOTICES.md'}",
        f"/DAPP_ICON={INSTALLER_DIR / 'ogp_app.ico'}",
        f"/DFILE_ICON={INSTALLER_DIR / 'ogp_file.ico'}",
        str(nsi_script),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print("ERROR: NSIS build failed!")
        sys.exit(1)

    installer_path = DIST_DIR / f"OpenGardenPlanner-v{APP_VERSION}-Setup.exe"
    if installer_path.exists():
        size_mb = installer_path.stat().st_size / (1024 * 1024)
        print(f"\nInstaller created: {installer_path}")
        print(f"Installer size: {size_mb:.1f} MB")
        if size_mb > 100:
            print("WARNING: Installer exceeds 100 MB target!")
    else:
        print("WARNING: Expected installer file not found at expected path.")
        print("Check NSIS output above for the actual output location.")


def _version_module_path() -> Path:
    """The generated module's one path (a build artifact, never source)."""
    return ROOT / "src" / "open_garden_planner" / "_version.py"


def _write_version_module(version: str) -> Path:
    """Write the version module for ONE PyInstaller run and return its path.

    The module is a BUILD ARTIFACT, not source (PF-CI-15). It is read
    DYNAMICALLY by ``services/update_checker.py``, so PyInstaller bundles it
    only because ``installer/ogp.spec`` lists it as a hidden import when it
    exists. ``_remove_version_module`` deletes it after PyInstaller, so a later
    direct build cannot silently bundle a stale release version.
    """
    version_file = _version_module_path()
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(
        f'"""Auto-generated by build_installer.py — do not edit."""\n'
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )
    print(f"Wrote version {version} to {version_file}")
    return version_file


def _remove_version_module() -> None:
    """Delete the generated module after PyInstaller (PF-CI-15)."""
    version_file = _version_module_path()
    if version_file.exists():
        version_file.unlink()


def main() -> None:
    """Run the build process."""
    global APP_VERSION

    parser = argparse.ArgumentParser(description="Build Open Garden Planner installer")
    parser.add_argument("--skip-pyinstaller", action="store_true",
                        help="Skip PyInstaller step (the existing bundle keeps its version; "
                             "pass the version it was built with)")
    parser.add_argument("--skip-nsis", action="store_true", help="Skip NSIS step")
    parser.add_argument("--version", type=str, help="Override version (e.g. 1.2.0)")
    args = parser.parse_args()

    if args.version:
        APP_VERSION = args.version

    print(f"Building {APP_NAME} v{APP_VERSION}")
    print(f"Project root: {ROOT}")

    if not args.skip_pyinstaller:
        _write_version_module(APP_VERSION)
        try:
            run_pyinstaller()
        finally:
            _remove_version_module()
    else:
        print("Skipping PyInstaller (--skip-pyinstaller)")

    run_inventory(version=APP_VERSION)

    if not args.skip_nsis:
        run_nsis()
    else:
        print("Skipping NSIS (--skip-nsis)")

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
