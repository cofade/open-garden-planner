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

# Data files (planting calendar, seed viability, companion planting, etc.)
for f in (RESOURCES / "data").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Web resources (Google Maps picker HTML loaded by QWebEngineView)
for f in (RESOURCES / "web").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Agent API (US-D1.1): the MCP server stack (mcp / uvicorn / starlette / anyio /
# sse-starlette / pydantic) imports protocol, loop and lifespan submodules
# dynamically, and several of these packages read their distribution metadata at
# import time. Collect submodules AND metadata so the frozen exe can start the
# embedded server.
from PyInstaller.utils.hooks import collect_submodules, copy_metadata


def _safe_collect_submodules(pkg):
    # collect_submodules imports every submodule to enumerate it. Some optional
    # submodules hard-fail on import when their extra isn't installed (e.g.
    # ``mcp.cli`` calls sys.exit(1) without the ``cli`` extra), surfacing as a
    # RuntimeError from the isolated child. We don't use those, so skip on error.
    try:
        return collect_submodules(pkg)
    except Exception as exc:  # noqa: BLE001 - optional-dep import failures are expected
        print(f"ogp.spec: skipping collect_submodules({pkg!r}): {exc}")
        return []


_mcp_hiddenimports = []
# Use mcp's concrete subpackages, NOT top-level "mcp" — walking "mcp" would
# import "mcp.cli" (needs the unbundled ``typer`` extra) and abort the build.
for _pkg in (
    "mcp.server",
    "mcp.shared",
    "mcp.types",
    "uvicorn",
    "starlette",
    "anyio",
    "sse_starlette",
    "pydantic",
    "pydantic_settings",  # imported eagerly by FastMCP; has dynamic submodules
    "httpx_sse",
):
    _mcp_hiddenimports += _safe_collect_submodules(_pkg)

for _pkg in (
    "mcp",
    "uvicorn",
    "starlette",
    "anyio",
    "sse_starlette",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "httpx_sse",
):
    datas += copy_metadata(_pkg)

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
        # QtWebEngine — needed for the satellite map picker dialog.
        # The import must run before QApplication is created (handled in main.py).
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebChannel",
        "ezdxf",
        "ezdxf.xclip",
        "ezdxf.fonts",
    ] + _mcp_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "pydoc",
        "doctest",
        # NOTE: do NOT exclude "multiprocessing" — uvicorn imports it eagerly
        # (uvicorn.supervisors -> basereload -> _subprocess) even though we run
        # single-process; excluding it breaks the embedded Agent API (US-D1.1).
        # NOTE: do NOT exclude "unittest" — ezdxf's query support (used by any
        # `import ezdxf`, so both DXF export AND import) pulls in pyparsing,
        # whose top-level `pyparsing/__init__.py` unconditionally imports
        # `pyparsing.testing`, which imports `unittest.TestCase` at module
        # level. Excluding it breaks every DXF-touching feature (US-12.3/12.4,
        # US-D1.4's export_dxf) the first time `ezdxf` is imported in a frozen
        # build — found via the Agent API's export_dxf tool, which was the
        # first codepath in this branch to actually exercise a DXF operation
        # in a fresh frozen build (see tests/manual verification for US-D1.4).
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
    upx_exclude=[
        # pydantic_core ships a compiled extension that UPX can corrupt; it is
        # imported at runtime by the Agent API (US-D1.1), so keep it uncompressed.
        "pydantic_core*.pyd",
    ],
    name="OpenGardenPlanner",
)
