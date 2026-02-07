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
    ├── PyInstaller (--onedir mode)
    │   ├── Bundle Python runtime
    │   ├── Bundle all dependencies (PyQt6, etc.)
    │   ├── Bundle resources (SVGs, textures, translations, icons)
    │   └── Output: dist/open_garden_planner/ directory
    │
    └── NSIS Installer Script
        ├── Install wizard (license, path selection)
        ├── Copy bundled files to Program Files
        ├── Create Start Menu shortcut
        ├── Optional desktop shortcut
        ├── Register .ogp file association
        ├── Register custom .ogp file icon
        ├── Add to Add/Remove Programs
        └── Output: OpenGardenPlanner-v1.0-Setup.exe
```

### Installer Features

| Feature | Description |
|---------|-------------|
| **License Display** | Show GPLv3 license during install |
| **Install Path** | User-selectable (default: `C:\Program Files\Open Garden Planner`) |
| **Start Menu** | Shortcut in Start Menu Programs folder |
| **Desktop Shortcut** | Optional desktop shortcut (checkbox) |
| **File Association** | `.ogp` files open with Open Garden Planner |
| **Custom File Icon** | Garden-themed icon for `.ogp` files (based on OGP logo) |
| **Uninstaller** | Clean removal via Add/Remove Programs |
| **Target Size** | < 100 MB installer |

### File Association

```
HKCR\.ogp → OpenGardenPlanner.Project
HKCR\OpenGardenPlanner.Project\DefaultIcon → ogp_file.ico
HKCR\OpenGardenPlanner.Project\shell\open\command → "path\to\ogp.exe" "%1"
```

## 7.3 CI/CD Pipeline (GitHub Actions)

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
    ├── Create GitHub Release
    └── Upload installer artifact
```

## 7.4 System Requirements

| Requirement | Minimum |
|-------------|---------|
| **OS** | Windows 10 (64-bit) |
| **RAM** | 4 GB |
| **Disk** | 200 MB free space |
| **Display** | 1280x720 |
| **GPU** | Any (Qt uses software rendering fallback) |
| **Internet** | Optional (for plant database search) |
