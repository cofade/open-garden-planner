# 7. Deployment View

## 7.1 Distribution Strategy

Open Garden Planner is distributed as:

1. **Windows Installer (primary)**: NSIS-based installer wrapping a PyInstaller bundle
2. **pip install (secondary)**: For Python users who prefer package manager installation
3. **Source (developer)**: Clone repository and run with `python -m open_garden_planner`

## 7.2 Windows Installer (NSIS)

### Build Pipeline

```
Source Code
    │
    ├── PyInstaller (--onedir mode, spec: installer/ogp.spec)
    │   ├── Bundle Python 3.12 runtime
    │   ├── Bundle all dependencies (PyQt6, Pillow, requests, etc.)
    │   ├── Bundle resources (SVGs, textures, translations, icons)
    │   ├── Set application icon (installer/ogp_app.ico)
    │   ├── Windowed mode (no console)
    │   └── Output: dist/OpenGardenPlanner/ directory (~99 MB)
    │
    └── NSIS Installer Script (installer/ogp_installer.nsi)
        ├── LZMA solid compression (32% ratio → ~34 MB installer)
        ├── Install wizard (welcome, license, path, components)
        ├── Copy bundled files to Program Files
        ├── Create Start Menu shortcut + uninstaller shortcut
        ├── Optional desktop shortcut
        ├── Optional .ogp file association with custom icon
        ├── Add to Add/Remove Programs (with size estimate)
        ├── Upgrade detection (silently uninstalls previous version)
        ├── English + German language support
        └── Output: OpenGardenPlanner-v1.0.0-Setup.exe
```

### How to Build

The build is orchestrated by `installer/build_installer.py`:

```bash
# Prerequisites
pip install pyinstaller                    # Python bundler
# Install NSIS from https://nsis.sourceforge.io/

# Full build (PyInstaller + NSIS)
python installer/build_installer.py

# PyInstaller only (skip NSIS)
python installer/build_installer.py --skip-nsis

# NSIS only (requires existing PyInstaller output in dist/)
python installer/build_installer.py --skip-pyinstaller
```

### Installer Files

| File | Purpose |
|------|---------|
| `installer/ogp.spec` | PyInstaller spec file (entry point, resources, excludes, icon) |
| `installer/ogp_installer.nsi` | NSIS installer script (wizard, registry, file association) |
| `installer/build_installer.py` | Build orchestration script |
| `installer/ogp_app.ico` | Application icon (multi-size: 16–256px) |
| `installer/ogp_file.ico` | `.ogp` file type icon |
| `LICENSE` | GPLv3 license text (displayed during install) |

### Installer Features

| Feature | Description |
|---------|-------------|
| **Welcome Page** | Branded welcome with app description |
| **License Display** | GPLv3 license agreement |
| **Install Path** | User-selectable (default: `C:\Program Files\Open Garden Planner`) |
| **Components** | Core (required), desktop shortcut (optional), file association (optional) |
| **Start Menu** | Shortcut in Start Menu Programs folder + uninstaller shortcut |
| **Desktop Shortcut** | Optional desktop shortcut (component checkbox) |
| **File Association** | `.ogp` files open with Open Garden Planner |
| **Custom File Icon** | OGP logo icon for `.ogp` files in Explorer |
| **Upgrade Support** | Detects existing installation, offers silent uninstall before upgrade |
| **Uninstaller** | Clean removal via Add/Remove Programs |
| **Installer Size** | ~34 MB (LZMA compressed, well under 100 MB target) |
| **Languages** | English, German |

### File Association

Registry entries created by the installer:

```
HKCR\.ogp                                          → "OpenGardenPlanner.Project"
HKCR\.ogp\Content Type                              → "application/x-ogp"
HKCR\OpenGardenPlanner.Project                      → "Open Garden Planner Project"
HKCR\OpenGardenPlanner.Project\DefaultIcon          → "$INSTDIR\ogp_file.ico,0"
HKCR\OpenGardenPlanner.Project\shell\open\command   → "$INSTDIR\OpenGardenPlanner.exe" "%1"
```

The application accepts a `.ogp` file path as a command-line argument (`main.py` handles `sys.argv`), enabling double-click-to-open.

### Add/Remove Programs

Registry entries under `HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall\Open Garden Planner`:

| Key | Value |
|-----|-------|
| `DisplayName` | Open Garden Planner |
| `DisplayVersion` | 1.0.0 |
| `Publisher` | cofade |
| `URLInfoAbout` | https://github.com/cofade/open-garden-planner |
| `DisplayIcon` | `$INSTDIR\ogp_app.ico` |
| `UninstallString` | `$INSTDIR\Uninstall.exe` |
| `EstimatedSize` | (computed at install time) |

## 7.3 Release Process (GitHub Releases)

### Creating a Release

1. **Tag the release**: `git tag -a v1.0.0 -m "Release v1.0.0"`
2. **Build the installer**: `python installer/build_installer.py`
3. **Generate checksums**:
   ```powershell
   (Get-FileHash dist\OpenGardenPlanner-v1.0.0-Setup.exe -Algorithm SHA256).Hash > dist\SHA256SUMS.txt
   ```
4. **Create GitHub Release**: Upload `OpenGardenPlanner-v1.0.0-Setup.exe` and `SHA256SUMS.txt` as release assets
5. **Release notes**: Include changelog, system requirements, and verification instructions

### Release Assets

Each release should include:

| Asset | Purpose |
|-------|---------|
| `OpenGardenPlanner-v{VERSION}-Setup.exe` | Windows installer |
| `SHA256SUMS.txt` | SHA-256 checksum for download verification |

### Verification

Users verify download integrity by comparing checksums:

```powershell
# PowerShell
(Get-FileHash .\OpenGardenPlanner-v1.0.0-Setup.exe -Algorithm SHA256).Hash
# Compare with SHA256SUMS.txt from release page
```

## 7.4 CI/CD Pipeline (GitHub Actions)

```
On every push:
    ├── Run linting (ruff)
    ├── Run type checking (mypy)
    └── Run all tests (pytest)

On PR:
    ├── Full test suite
    └── Coverage report

On release tag (v*):
    ├── Build Windows .exe (PyInstaller)
    ├── Build NSIS installer
    ├── Generate SHA256 checksums
    ├── Create GitHub Release
    └── Upload installer + checksums as release assets
```

## 7.5 System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Windows 10 (64-bit) |
| **RAM** | 4 GB |
| **Disk** | 200 MB free space |
| **Display** | 1280x720 |
| **GPU** | Any (Qt uses software rendering fallback) |
| **Internet** | Optional (for plant database search) |
