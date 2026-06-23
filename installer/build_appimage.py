"""Build script for Open Garden Planner Linux AppImage.

Usage:
    python installer/build_appimage.py [--version VERSION]

Prerequisites:
    - PyInstaller: pip install pyinstaller
    - appimagetool: Download from https://github.com/AppImage/AppImageKit/releases
      or install via package manager
"""

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
INSTALLER_DIR = ROOT / "installer"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"

# App metadata
APP_NAME = "Open Garden Planner"
APP_ID = "com.github.cofade.opengardenplanner"
APP_EXE_NAME = "OpenGardenPlanner"
APP_VERSION = "1.0.0"

# Categories for the .desktop file
DESKTOP_CATEGORIES = "Graphics;VectorGraphics;Engineering;"


def create_appdir(bundle_dir: Path, version: str) -> Path:
    """Create AppDir structure from PyInstaller bundle.

    AppDir layout:
        AppDir/
        ├── AppRun (symlink or script)
        ├── opengardenplanner.desktop
        ├── ogp_app.png (icon)
        └── usr/
            └── bin/
                └── OpenGardenPlanner/ (PyInstaller bundle)
    """
    print("=" * 60)
    print("Creating AppDir structure")
    print("=" * 60)

    appdir = BUILD_DIR / "AppDir"
    if appdir.exists():
        print(f"Cleaning previous AppDir: {appdir}")
        shutil.rmtree(appdir)

    appdir.mkdir(parents=True, exist_ok=True)
    usr_bin = appdir / "usr" / "bin"
    usr_bin.mkdir(parents=True, exist_ok=True)

    # Copy PyInstaller bundle
    print(f"Copying bundle from {bundle_dir} to {usr_bin}")
    shutil.copytree(bundle_dir, usr_bin / APP_EXE_NAME)

    # Create AppRun launcher script
    apprun = appdir / "AppRun"
    apprun.write_text(
        f"""#!/bin/bash
# AppRun launcher for {APP_NAME}
SELF=$(readlink -f "$0")
HERE=${{SELF%/*}}
export PATH="${{HERE}}/usr/bin:${{PATH}}"
export LD_LIBRARY_PATH="${{HERE}}/usr/lib:${{LD_LIBRARY_PATH}}"
exec "${{HERE}}/usr/bin/{APP_EXE_NAME}/{APP_EXE_NAME}" "$@"
""",
        encoding="utf-8",
    )
    # Make AppRun executable
    apprun.chmod(apprun.stat().st_mode | stat.S_IEXEC)

    # Create .desktop file
    desktop_file = appdir / f"{APP_ID.split('.')[-1]}.desktop"
    desktop_file.write_text(
        f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
GenericName=Garden Planning Tool
Comment=Open-source garden planning with CAD-like precision
Exec={APP_EXE_NAME}
Icon=ogp_app
Categories={DESKTOP_CATEGORIES}
Terminal=false
""",
        encoding="utf-8",
    )

    # Copy icon (convert .ico to .png if needed)
    ico_path = INSTALLER_DIR / "ogp_app.ico"
    png_path = appdir / "ogp_app.png"

    # For now, try to extract largest icon from .ico using Pillow
    # If that fails, we'll need a pre-made .png
    try:
        from PIL import Image
        with Image.open(ico_path) as img:
            # ICO files contain multiple sizes; get the largest
            img.save(png_path, "PNG")
        print(f"Converted icon: {png_path}")
    except Exception as e:
        print(f"WARNING: Could not convert icon: {e}")
        print("Please provide installer/ogp_app.png manually")
        # Create a symlink for now so the build doesn't fail
        if ico_path.exists():
            shutil.copy(ico_path, png_path)

    print(f"AppDir created: {appdir}")
    return appdir


def build_appimage(appdir: Path, version: str) -> Path:
    """Build AppImage from AppDir using appimagetool."""
    print("\n" + "=" * 60)
    print("Building AppImage")
    print("=" * 60)

    # Find appimagetool
    appimagetool = shutil.which("appimagetool")
    if appimagetool is None:
        # Try common download location
        download_path = Path.home() / "appimagetool-x86_64.AppImage"
        if download_path.exists():
            appimagetool = str(download_path)
        else:
            print("ERROR: appimagetool not found!")
            print("Download from: https://github.com/AppImage/AppImageKit/releases")
            print(f"  wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage")
            print(f"  chmod +x appimagetool-x86_64.AppImage")
            print("  sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool")
            sys.exit(1)

    output_path = DIST_DIR / f"{APP_NAME.replace(' ', '_')}-v{version}-x86_64.AppImage"
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # Remove old AppImage
    if output_path.exists():
        output_path.unlink()

    # Set ARCH environment variable (required by appimagetool)
    env = os.environ.copy()
    env["ARCH"] = "x86_64"

    cmd = [appimagetool, str(appdir), str(output_path)]
    print(f"Running: {' '.join(cmd)}")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        print("ERROR: appimagetool failed!")
        sys.exit(1)

    if output_path.exists():
        # Make it executable
        output_path.chmod(output_path.stat().st_mode | stat.S_IEXEC)
        size_mb = output_path.stat().st_size / (1024 * 1024)
        print(f"\nAppImage created: {output_path}")
        print(f"Size: {size_mb:.1f} MB")
        return output_path
    else:
        print("ERROR: AppImage was not created at expected path")
        sys.exit(1)


def run_pyinstaller(version: str) -> Path:
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
    exe_path = bundle_dir / APP_EXE_NAME
    if not exe_path.exists():
        print(f"ERROR: Expected output not found: {exe_path}")
        sys.exit(1)

    # Calculate bundle size
    total_size = sum(f.stat().st_size for f in bundle_dir.rglob("*") if f.is_file())
    print(f"\nPyInstaller bundle created: {bundle_dir}")
    print(f"Bundle size: {total_size / (1024 * 1024):.1f} MB")

    return bundle_dir


def main() -> None:
    """Run the Linux AppImage build process."""
    global APP_VERSION

    parser = argparse.ArgumentParser(description="Build Open Garden Planner AppImage")
    parser.add_argument("--version", type=str, help="Override version (e.g. 1.2.0)")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Skip PyInstaller step")
    args = parser.parse_args()

    if args.version:
        APP_VERSION = args.version

    print(f"Building {APP_NAME} v{APP_VERSION} for Linux")
    print(f"Project root: {ROOT}")

    # Step 1: PyInstaller bundle
    if not args.skip_pyinstaller:
        # Write version module
        version_file = ROOT / "src" / "open_garden_planner" / "_version.py"
        version_file.write_text(
            f'"""Auto-generated by build script — do not edit."""\n'
            f'__version__ = "{APP_VERSION}"\n',
            encoding="utf-8",
        )
        print(f"Wrote version {APP_VERSION} to {version_file}")

        bundle_dir = run_pyinstaller(APP_VERSION)
    else:
        print("Skipping PyInstaller (--skip-pyinstaller)")
        bundle_dir = DIST_DIR / APP_EXE_NAME
        if not bundle_dir.exists():
            print(f"ERROR: Bundle not found: {bundle_dir}")
            sys.exit(1)

    # Step 2: Create AppDir
    appdir = create_appdir(bundle_dir, APP_VERSION)

    # Step 3: Build AppImage
    appimage_path = build_appimage(appdir, APP_VERSION)

    print("\n" + "=" * 60)
    print("Build complete!")
    print("=" * 60)
    print(f"\nTo run: {appimage_path}")
    print(f"To install: Copy to ~/Applications or /usr/local/bin/")


if __name__ == "__main__":
    main()
