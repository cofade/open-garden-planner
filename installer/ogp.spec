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

# Qt Quick 3D engine package (ADR-048, Phase 17 L1.2): Garden.qml and its
# shader files live next to the package (ui/view3d/quick3d/host.py resolves
# them via __file__). The frozen exe's `--selftest` loads exactly these files
# from the bundle and renders a frame with every shader — a file this loop
# misses fails the release, not a user (ui/view3d/quick3d/selftest.py).
for f in (SRC / "open_garden_planner" / "ui" / "view3d" / "quick3d" / "qml").rglob("*"):
    if f.is_file():
        rel = f.relative_to(SRC)
        datas.append((str(f), str(rel.parent)))

# Agent API (US-D1.1): the MCP server stack (mcp / uvicorn / starlette / anyio /
# sse-starlette / pydantic) imports protocol, loop and lifespan submodules
# dynamically, and several of these packages read their distribution metadata at
# import time. Collect submodules AND metadata so the frozen exe can start the
# embedded server.
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# AUD-051/AUD-055: bundle the .dist-info of every runtime distribution so the
# third-party notices and the SBOM can be generated from the ACTUAL frozen
# inventory (scripts/generate_distribution_inventory.py reads them back out of
# the built bundle). The closure walks Requires-Dist instead of keeping a
# hand-typed list, so a new dependency appears automatically.
if str(SPECPATH) not in sys.path:
    sys.path.insert(0, str(SPECPATH))
from build_environment import warn_if_unpinned  # noqa: E402
from runtime_closure import runtime_distribution_names  # noqa: E402
from frozen_inventory import MANIFEST_NAME, collected_metadata, write_manifest  # noqa: E402

# #538: a local build must say when the venv holds a distribution the lock no
# longer pins (the retired 3D wheels survived exactly this way after L1.10).
# Advisory here; `python -m installer.build_environment --strict` is the gate form.
warn_if_unpinned()

# The project's own metadata and build-time-only helpers are not third-party.
_EXCLUDED_METADATA = {"open-garden-planner", "pyinstaller-hooks-contrib"}

for _dist in runtime_distribution_names():
    if _dist in _EXCLUDED_METADATA:
        continue
    try:
        datas += copy_metadata(_dist)
    except Exception as exc:  # noqa: BLE001 - fail closed, but say which distribution
        raise RuntimeError(f"ogp.spec: cannot collect metadata for {_dist!r}: {exc}") from exc


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
        # The 3D view (Phase 17: the workspace's 3D pane, ADR-060). Its snapshot is
        # imported with the first switch to 3D.
        "open_garden_planner.ui.view3d",
        "open_garden_planner.ui.view3d.snapshot",
        "open_garden_planner.ui.view3d.ground_bake",
        # Qt Quick 3D engine (ADR-048, L1.2): ui/view3d/quick3d/ is the ONE
        # package that imports these bindings, and it is loaded lazily (the
        # workspace opens 3D on demand; `--selftest` renders a frame). The
        # QtQml hook collects the QtQuick3D QML modules (QtQuick3D,
        # QtQuick3D.Helpers) once the bindings are named. They ship INSIDE the
        # two pinned Qt wheels (PyQt6, PyQt6-Qt6), which move together
        # (tests/unit/test_qt_runtime_pins.py).
        "PyQt6.QtQuick",
        "PyQt6.QtQml",
        "PyQt6.QtQuick3D",
        "open_garden_planner.ui.view3d.quick3d",
        "open_garden_planner.ui.view3d.quick3d.adapter",
        "open_garden_planner.ui.view3d.quick3d.geometry",
        "open_garden_planner.ui.view3d.quick3d.ground_tiles",
        "open_garden_planner.ui.view3d.quick3d.host",
        "open_garden_planner.ui.view3d.quick3d.lifecycle",
        "open_garden_planner.ui.view3d.quick3d.look",
        "open_garden_planner.ui.view3d.quick3d.materials",
        "open_garden_planner.ui.view3d.quick3d.offscreen",
        "open_garden_planner.ui.view3d.quick3d.qt_messages",
        "open_garden_planner.ui.view3d.quick3d.runlog",
        "open_garden_planner.ui.view3d.quick3d.selftest",
        "open_garden_planner.ui.view3d.quick3d.shots",
        # The Plan / 3D / Split workspace (ADR-060, L1.3; the default since L1.9):
        # the main window imports workspace.py at start-up; the pipeline, the orbit
        # input and the list of what 3D could not show come with the first switch
        # to 3D.
        "open_garden_planner.ui.view3d.workspace",
        "open_garden_planner.ui.view3d.sync_controller",
        "open_garden_planner.ui.view3d.init_guard",
        "open_garden_planner.ui.view3d.orbit_input",
        "open_garden_planner.ui.view3d.problems_dialog",
        "open_garden_planner.ui.sim_clock_subscription",
        "open_garden_planner.core.scene3d.camera",
        "open_garden_planner.core.plain_text",
        # The look of the 3D view (L1.4): imported with the first switch to 3D.
        "open_garden_planner.ui.view3d.look_controller",
        "open_garden_planner.core.scene3d.look",
        # Selection, the info card and walk mode (ADR-060 addendum, L1.8): the
        # card and the bridge are imported when the 3D pane is first built, walk
        # mode when it is first entered.
        "open_garden_planner.ui.view3d.selection_bridge",
        "open_garden_planner.ui.view3d.info_card",
        "open_garden_planner.ui.view3d.walk_mode",
        "open_garden_planner.core.scene3d.selection",
        "open_garden_planner.core.scene3d.walk",
        # Analyze in 3D (ADR-063, L2): the analysis controller, the growth jump and its
        # wipe are imported when the 3D pane is first built; the compass letters and
        # the Qt-free drape / sun path / X-ray cores come with them.
        "open_garden_planner.ui.view3d.analysis_controller",
        "open_garden_planner.ui.view3d.analysis_modes",
        "open_garden_planner.ui.view3d.compass_glyphs",
        "open_garden_planner.ui.view3d.growth_jump",
        "open_garden_planner.ui.view3d.wipe",
        "open_garden_planner.core.scene3d.drape",
        "open_garden_planner.core.scene3d.sun_path",
        "open_garden_planner.core.scene3d.xray",
        "open_garden_planner.app.win32_taskbar",
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

# Requires-Dist is a minimum, not the shipped inventory. Hooks can collect
# build/dev packages and copies vendored by setuptools; index actual source
# ownership after Analysis and preserve each copy's own metadata and licenses.
_inventory_datas, _inventory_manifest = collected_metadata(
    a.pure, a.binaries, a.datas, required_names=runtime_distribution_names(), scripts=a.scripts
)
a.datas += _inventory_datas
_inventory_path = Path(workpath) / MANIFEST_NAME

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
# PYZ removes bootstrap stdlib modules (e.g. struct) from Analysis.pure.
# Record its normalized contents, then independently verify the executable.
_inventory_manifest["python_modules"] = sorted(row[0] for row in pyz.toc)
write_manifest(_inventory_path, _inventory_manifest)
a.datas += [(MANIFEST_NAME, str(_inventory_path), "DATA")]

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
