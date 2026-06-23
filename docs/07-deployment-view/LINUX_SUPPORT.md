# Linux Support

## Overview

Open Garden Planner now supports Linux through AppImage packaging, providing a universal binary that runs on most modern Linux distributions without installation.

## Architecture

### Cross-Platform Build System

The build system detects the platform and creates appropriate packages:

- **Windows**: NSIS installer (`.exe`)
- **Linux**: AppImage (`.AppImage`)
- **macOS**: Future - DMG or PKG

### Key Components

1. **PyInstaller Spec** (`installer/ogp.spec`)
   - Platform detection using `platform.system()`
   - Conditional icon handling (`.ico` for Windows, `.png` for Linux)
   - Shared resource collection (icons, textures, plants, translations, data, web)

2. **Linux Build Script** (`installer/build_appimage.py`)
   - Creates AppDir structure from PyInstaller bundle
   - Generates `.desktop` file for application menu integration
   - Converts Windows `.ico` to `.png` using Pillow
   - Packages with `appimagetool`

3. **Unified Build Script** (`installer/build_installer.py`)
   - Cross-platform entry point
   - Delegates to platform-specific packaging:
     - Windows → NSIS
     - Linux → AppImage
   - Maintains backwards compatibility with `--skip-nsis` flag

### AppImage Structure

```
AppDir/
├── AppRun                          # Launcher script
├── opengardenplanner.desktop       # Desktop integration
├── ogp_app.png                     # Application icon
└── usr/
    └── bin/
        └── OpenGardenPlanner/      # PyInstaller bundle
            ├── OpenGardenPlanner   # Main executable
            ├── _internal/          # Dependencies
            └── open_garden_planner/
                └── resources/      # Icons, textures, translations, data
```

## CI/CD

### Workflow Structure

Two parallel GitHub Actions workflows:

1. **`.github/workflows/release.yml`** (Windows)
   - Runs on `windows-latest`
   - Builds NSIS installer
   - Creates GitHub release with tag
   - Uploads `OpenGardenPlanner-v*-Setup.exe` and `SHA256SUMS.txt`

2. **`.github/workflows/release-linux.yml`** (Linux)
   - Runs on `ubuntu-latest`
   - Builds AppImage
   - Uploads to the **same** release created by Windows workflow
   - Adds `Open_Garden_Planner-v*-x86_64.AppImage` and `SHA256SUMS-linux.txt`

### Version Synchronization

Both workflows use identical version detection logic:
- Read latest git tag
- Parse PR labels (`major`, `minor`, or default to `patch`)
- Compute new semantic version
- Skip if tag already exists (prevents race conditions)

The Linux workflow waits 10 seconds for the Windows workflow to create the release, then uploads to it.

### System Dependencies (Linux CI)

```bash
sudo apt-get install -y \
  libxcb-xinerama0 libxcb-cursor0 libxkbcommon-x11-0 \
  libgl1-mesa-glx libegl1-mesa libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 \
  libxcb-shape0 libfuse2 file wget
```

Required for:
- PyQt6 runtime (xcb libraries)
- AppImage execution (libfuse2)

## Local Development

### Building on Linux

```bash
# Install dependencies
pip install -e ".[dev]"
pip install pyinstaller

# Convert icon (one-time setup)
python -c "from PIL import Image; img = Image.open('installer/ogp_app.ico'); img.save('installer/ogp_app.png', 'PNG')"

# Download appimagetool
wget https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage
chmod +x appimagetool-x86_64.AppImage
sudo mv appimagetool-x86_64.AppImage /usr/local/bin/appimagetool

# Build AppImage
python installer/build_appimage.py --version 1.17.2

# Or use the unified script
python installer/build_installer.py --version 1.17.2
```

### Running the AppImage

```bash
chmod +x dist/Open_Garden_Planner-v1.17.2-x86_64.AppImage
./dist/Open_Garden_Planner-v1.17.2-x86_64.AppImage
```

### Testing

The AppImage should:
1. Launch without errors
2. Display the main window with all UI elements
3. Load resources (icons, textures, translations)
4. Save/load `.ogp` projects to `~/Documents/Open Garden Planner`
5. Export to PNG/SVG/DXF/PDF

Run the same test suite as Windows:
```bash
python -m pytest tests/ -v
```

## Distribution

### Supported Platforms

- Ubuntu 20.04+ (focal and later)
- Fedora 35+
- Debian 11+ (bullseye and later)
- Arch Linux (current)
- openSUSE Leap 15.3+
- Other systemd-based distributions with glibc 2.31+

### Runtime Requirements

- **FUSE2**: Required to mount AppImage
  ```bash
  # Ubuntu/Debian
  sudo apt install libfuse2
  
  # Fedora
  sudo dnf install fuse-libs
  
  # Arch
  sudo pacman -S fuse2
  ```

- **System libraries**: Qt6 dependencies (shipped in AppImage, but system GL drivers used)

### Installation Options

1. **Run directly** (no installation):
   ```bash
   chmod +x Open_Garden_Planner-*.AppImage
   ./Open_Garden_Planner-*.AppImage
   ```

2. **User install** (`~/Applications`):
   ```bash
   mkdir -p ~/Applications
   mv Open_Garden_Planner-*.AppImage ~/Applications/
   ```

3. **System-wide** (`/usr/local/bin`):
   ```bash
   sudo mv Open_Garden_Planner-*.AppImage /usr/local/bin/open-garden-planner
   ```

## Known Issues

### AppImage Limitations

1. **Desktop integration**: The `.desktop` file is inside the AppImage and won't appear in application menus automatically. Users must:
   - Right-click the AppImage → "Integrate and run" (if using AppImageLauncher)
   - Or manually extract and install the desktop file

2. **FUSE requirement**: Some modern distributions (Ubuntu 22.04+) ship without FUSE2 by default. Users must install it manually.

3. **Wayland compatibility**: Qt6 supports Wayland, but some visual glitches may occur. Users can force X11:
   ```bash
   QT_QPA_PLATFORM=xcb ./Open_Garden_Planner-*.AppImage
   ```

### Future Improvements

- **Flatpak/Snap packages**: For better desktop integration
- **Native `.deb` and `.rpm` packages**: For distribution-specific package managers
- **Auto-update**: AppImage update mechanism (AppImageUpdate)

## Cross-Platform Compatibility

The codebase is already cross-platform:

- **Paths**: Use `QStandardPaths` for OS-specific directories (`src/open_garden_planner/app/paths.py`)
- **File dialogs**: `QFileDialog` handles platform differences
- **Keyboard shortcuts**: Qt maps to platform conventions (Ctrl on Linux/Windows, Cmd on macOS)
- **Icons**: SVG icons scale on any DPI
- **Fonts**: Qt's font fallback handles missing fonts gracefully

### Platform-Specific Code

Minimal platform-specific code required:

1. **Build scripts**: `installer/build_installer.py`, `installer/build_appimage.py`
2. **PyInstaller spec**: Icon path conditional on platform
3. **CI workflows**: Separate YAML files for Windows and Linux

All application code is platform-agnostic.

## Maintenance

### Adding New Resources

When adding resources (icons, textures, translations):

1. Add to `src/open_garden_planner/resources/`
2. Update `installer/ogp.spec` data collection loop (if adding a new subdirectory)
3. Test PyInstaller bundle on both platforms:
   ```bash
   # Windows
   python -m PyInstaller installer/ogp.spec --noconfirm
   dist\OpenGardenPlanner\OpenGardenPlanner.exe
   
   # Linux
   python -m PyInstaller installer/ogp.spec --noconfirm
   dist/OpenGardenPlanner/OpenGardenPlanner
   ```

### Release Checklist

Before each release:

- [ ] Version bumped in `pyproject.toml` and `src/open_garden_planner/__init__.py`
- [ ] All tests pass on Linux: `pytest tests/ -v`
- [ ] PyInstaller bundle tested locally (8-second timeout smoke test)
- [ ] CI builds pass for both Windows and Linux
- [ ] Both installers uploaded to GitHub release
- [ ] Checksums verified (`SHA256SUMS.txt` and `SHA256SUMS-linux.txt`)
- [ ] Installation tested on clean system (Windows 10/11 and Ubuntu 22.04/24.04)

## References

- [AppImage Documentation](https://docs.appimage.org/)
- [PyInstaller Manual](https://pyinstaller.org/en/stable/)
- [Qt6 Linux Deployment](https://doc.qt.io/qt-6/linux-deployment.html)
- [XDG Desktop Entry Specification](https://specifications.freedesktop.org/desktop-entry-spec/latest/)
