# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec file for Open Garden Planner.

Build with:
    pyinstaller installer/ogp.spec
"""

import os
import sys
from pathlib import Path

block_cipher = None

# Project root
ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
RESOURCES = SRC / "open_garden_planner" / "resources"
INSTALLER = ROOT / "installer"

# Collect all resource files preserving directory structure
datas = []

# Icons
for f in (RESOURCES / "icons").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Textures
for f in (RESOURCES / "textures").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Plants
for f in (RESOURCES / "plants").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Objects (furniture, infrastructure)
for f in (RESOURCES / "objects").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Translations
for f in (RESOURCES / "translations").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

a = Analysis(
    [str(SRC / "open_garden_planner" / "__main__.py")],
    pathex=[str(SRC)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "open_garden_planner",
        "open_garden_planner.main",
        "open_garden_planner.app",
        "open_garden_planner.app.application",
        "open_garden_planner.app.settings",
        "open_garden_planner.core",
        "open_garden_planner.core.i18n",
        "open_garden_planner.ui",
        "open_garden_planner.ui.theme",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "unittest",
        "pydoc",
        "doctest",
        "multiprocessing",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OpenGardenPlanner",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Windowed app, no console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(INSTALLER / "ogp_app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="OpenGardenPlanner",
)
