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
from pathlib import Path

ROOT = Path(__file__).parent.parent
INSTALLER_DIR = ROOT / "installer"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

# App metadata
APP_NAME = "Open Garden Planner"
APP_VERSION = "1.0.0"
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


def run_pyinstaller() -> None:
    """Run PyInstaller to create the standalone bundle."""
    print("=" * 60)
    print("Step 1: Building with PyInstaller")
    print("=" * 60)

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


def run_nsis() -> None:
    """Run NSIS to create the installer."""
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


def main() -> None:
    """Run the build process."""
    global APP_VERSION

    parser = argparse.ArgumentParser(description="Build Open Garden Planner installer")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Skip PyInstaller step")
    parser.add_argument("--skip-nsis", action="store_true", help="Skip NSIS step")
    parser.add_argument("--version", type=str, help="Override version (e.g. 1.2.0)")
    args = parser.parse_args()

    if args.version:
        APP_VERSION = args.version

    print(f"Building {APP_NAME} v{APP_VERSION}")
    print(f"Project root: {ROOT}")

    if not args.skip_pyinstaller:
        run_pyinstaller()
    else:
        print("Skipping PyInstaller (--skip-pyinstaller)")

    if not args.skip_nsis:
        run_nsis()
    else:
        print("Skipping NSIS (--skip-nsis)")

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
