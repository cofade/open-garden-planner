---
name: ogp-build-and-run
description: >
  Environment setup, running, building, and packaging Open Garden Planner.
  Load this skill when: setting up the dev environment from scratch (Windows or
  Linux/CI/cloud), running the app or the test suite, building the PyInstaller
  exe or the NSIS installer, adding or bumping a dependency, hitting an
  ImportError / ModuleNotFoundError / frozen-exe startup failure, wondering
  where artifacts, autosaves, settings, or user data land on disk, or checking
  whether the embedded Agent API (MCP) server is up.
---

# OGP Build & Run

Everything needed to recreate the environment, run the app and tests, build and
package, and find where artifacts land. Facts verified against the repo at
**v1.23.0 (2026-07-04)**: `pyproject.toml`, `.github/workflows/ci.yml`,
`installer/ogp.spec`, `installer/build_installer.py`, `docs/07-deployment-view/`,
`docs/08-crosscutting-concepts/` §8.19, and source files cited inline.

**Jargon, defined once:**
- **Frozen exe** — the standalone PyInstaller bundle in `dist/OpenGardenPlanner/`
  (Python interpreter + deps + resources packed together; no venv needed to run it).
- **Agent API** — the MCP (Model Context Protocol) server embedded in the running
  GUI, serving AI agents over HTTP on loopback (`agent_api/` package).
- **`.ogp`** — the app's JSON project file format.
- **i18n gate** — the test that fails if any registered UI string lacks a German
  translation.

## When NOT to use this skill

- Deciding what counts as *passing* evidence, review policy, integration-test
  policy → **ogp-validation-and-qa**.
- Release/version bumping, PR labels, tag rules, merge gates → **ogp-change-control**.
- Catalog of settings keys and feature flags → **ogp-config-and-flags**.
- Measuring/profiling/instrumentation tools → **ogp-diagnostics-and-tooling**.
- Debugging app behavior (not build/import errors) → **ogp-debugging-playbook**
  and the `debug-verbose` skill.

## Two first-class environments

| | Windows dev (canonical) | Linux / CI / cloud |
|---|---|---|
| Purpose | Where the app is actually developed and run as a GUI | Headless tests, lint, security scan (CI runs ubuntu-latest) |
| Python | 3.11+ (`requires-python = ">=3.11"`; CI pins 3.11) | 3.11 |
| Interpreter path | `venv/Scripts/python.exe` (Git-Bash form used throughout CLAUDE.md) or `venv\Scripts\python.exe` (cmd) | `venv/bin/python` or system python after `pip install -e ".[dev]"` |
| GUI runs? | Yes — the app targets Windows (pyproject classifier: `Operating System :: Microsoft :: Windows`) | Not intended; tests run with `QT_QPA_PLATFORM=offscreen` (also set defensively in `tests/conftest.py`) |
| Exe/installer build | Yes (PyInstaller + NSIS; release CI uses windows-latest) | No |

`pyproject.toml` is the source of truth for dependencies. **Trap:**
`requirements.txt` / `requirements-dev.txt` are stale (they list only
PyQt6/Pillow and omit the MCP stack, WebEngine pin, bandit) — do not install
from them; use `pip install -e ".[dev]"`. (Verified 2026-07-04.)

## From-scratch checklist — brand-new machine

### Windows (canonical dev box)

| # | Command (Git Bash) | Expected outcome / trap |
|---|---|---|
| 1 | Install Python 3.11+ (python.org, 64-bit) | `python --version` → 3.11+ |
| 2 | `git clone https://github.com/cofade/open-garden-planner && cd open-garden-planner` | Repo present |
| 3 | `python -m venv venv` | `venv/` created |
| 4 | `venv/Scripts/python.exe -m pip install --upgrade pip` | pip current |
| 5 | `venv/Scripts/python.exe -m pip install -e ".[dev]"` | Installs PyQt6, PyQt6-WebEngine (<6.11), Pillow, requests, python-dotenv, numpy, pyclipper, ezdxf, mcp (<2.0), uvicorn, starlette, pydantic + dev tools (pytest, pytest-qt, pytest-cov, ruff, mypy, bandit) |
| 6 | `venv/Scripts/python.exe -m open_garden_planner` | Main window opens. Agent API auto-starts on 127.0.0.1:8765 (on by default) |
| 7 | `venv/Scripts/python.exe -m pytest tests/ -v` | Full suite passes (unit + integration + ui) |
| 8 | *(only for exe/installer builds)* `venv/Scripts/python.exe -m pip install pyinstaller` | **Trap:** PyInstaller is NOT in the `[dev]` extra — install separately (per README / docs/07) |
| 9 | *(only for installer builds)* Install NSIS from https://nsis.sourceforge.io/ | `makensis` on PATH or at `C:\Program Files (x86)\NSIS\makensis.exe` (both auto-detected by `installer/build_installer.py`) |
| 10 | *(optional)* Create `.env` with `OGP_GOOGLE_MAPS_KEY=...` | Enables the satellite map picker; app runs fine without it (`main.py` loads `.env` via python-dotenv) |

Activation is optional — CLAUDE.md convention is to call the venv interpreter
explicitly (`venv/Scripts/python.exe -m ...`), which works from any shell
without activating. `venv\Scripts\activate` (cmd) / `source venv/Scripts/activate`
(Git Bash) also work.

### Linux / CI / cloud (headless)

| # | Command | Expected outcome / trap |
|---|---|---|
| 1 | `sudo apt-get update && sudo apt-get install -y libegl1 libxkbcommon0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0` | Qt runtime libs. **Trap:** without these, importing PyQt6 fails with `ImportError: libEGL.so.1: cannot open shared object file` (or an xcb plugin error). This is the exact list from `.github/workflows/ci.yml` (test job) |
| 2 | `python3 -m venv venv && venv/bin/python -m pip install --upgrade pip` | (CI skips the venv and installs into the runner's Python 3.11) |
| 3 | `venv/bin/python -m pip install -e ".[dev]"` | Same dependency set as Windows |
| 4 | `QT_QPA_PLATFORM=offscreen venv/bin/python -m pytest tests/ -v` | Suite passes headless. `tests/conftest.py` also does `os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")`, so the prefix is belt-and-braces for pytest — but required for any *non-pytest* Qt script |
| 5 | Do not try to build the exe/installer here | PyInstaller output is platform-specific; the shipped artifact is Windows-only (release CI builds on windows-latest) |

The GUI is Windows-targeted; on Linux this repo is for tests/lint/analysis, not
for running the app.

## Running the app

```bash
# Windows (canonical)
venv/Scripts/python.exe -m open_garden_planner
```

Expected: main window opens; embedded Agent API MCP server starts automatically
(see "Agent API quick check" below). Entry point chain:
`__main__.py` → `main.py` (`main()`); console script `open-garden-planner` and
GUI script `open-garden-planner-gui` are also installed by pip.

## Running tests, lint, security scan, types

Command anatomy only — what counts as acceptable results/evidence is
**ogp-validation-and-qa**'s territory.

| What | Command (swap `venv/Scripts/python.exe` → `venv/bin/python` on Linux) | Expected outcome |
|---|---|---|
| Full suite | `venv/Scripts/python.exe -m pytest tests/ -v` | All pass. `pyproject.toml` sets `addopts = "-v --tb=short"`, `qt_api = "pyqt6"`, `testpaths = ["tests"]` |
| Unit layer only | `venv/Scripts/python.exe -m pytest tests/unit -v` | ~106 files (Qt-free-ish fast tests) |
| Integration layer | `venv/Scripts/python.exe -m pytest tests/integration -v` | ~74 files (end-to-end UI workflows) |
| UI layer | `venv/Scripts/python.exe -m pytest tests/ui -v` | ~19 files (widget-level) |
| Single test | `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished -v` | `::Class::method` selector form |
| Lint | `venv/Scripts/python.exe -m ruff check src/` | Zero findings. Config in `pyproject.toml` (`[tool.ruff]`, py311, line-length 100, E/W/F/I/B/C4/UP/ARG/SIM) |
| Security scan | `venv/Scripts/python.exe -m bandit -r src/ --severity-level high` | Zero HIGH findings (CI fails on HIGH). Bandit is in the `[dev]` extra |
| Types | `venv/Scripts/python.exe -m mypy src/` | mypy is in the `[dev]` extra and configured strict in `pyproject.toml` (`[tool.mypy] strict = true`). **Note (2026-07-04):** mypy is NOT run in `ci.yml` — available locally, not a CI gate |

Notes:
- pytest-qt provides `qtbot`; PyQt6 tests need the fixture even when unused
  (Qt init) — `tests/**` has ruff per-file ignores ARG001/ARG002 for this.
- `tests/conftest.py` session-scope-redirects `QSettings` to a
  `"cofade_test"` org so tests never pollute real user settings.

## Translations pipeline (i18n)

Run after adding or changing ANY user-visible string:

```bash
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
```

| Fact | Value (verified) |
|---|---|
| `.ts` / `.qm` location | `src/open_garden_planner/resources/translations/` — `open_garden_planner_de.ts/.qm` and `open_garden_planner_en.ts/.qm` |
| `fill_translations.py` | Holds the full English→German mapping as a Python dict; writes translations + missing contexts into the `.ts`. New strings must be **added to the script's dict** first |
| `compile_translations.py` | Pure-Python `lrelease` replacement — compiles every `.ts` in that dir to `.qm` (no Qt tooling needed) |
| `PYTHONUTF8=1` | Required on Windows: the scripts handle umlauts; without it the default cp1252 codec mangles them |
| Gate test | `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` — fails if any registered string is left unfinished. It CANNOT see hardcoded plain-string call sites that bypass `tr()` (see CLAUDE.md i18n section) |
| Packaging | `installer/ogp.spec` bundles the whole `resources/translations/` dir into the exe — recompile `.qm` BEFORE building |

## Building the frozen exe (PyInstaller)

```bash
# Windows — prerequisite: pip install pyinstaller (not in [dev])
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
```

Expected outcome: bundle at **`dist/OpenGardenPlanner/`** (~99 MB, per docs/07)
containing `OpenGardenPlanner.exe`. Intermediate files in `build/`.

### Exe smoke test — exit code 124 means SUCCESS

```bash
timeout 8 dist/OpenGardenPlanner/OpenGardenPlanner.exe
echo $?   # 124 = success
```

Counterintuitive but deliberate: `timeout` (GNU coreutils, available in Git
Bash) kills the process after 8 seconds and reports exit code **124**
("killed by timeout"). A GUI app that is still alive after 8 s has survived
import, resource loading, and window construction — that is the pass signal.
Any *other* outcome is a failure: an immediate non-124 exit means the frozen
app crashed on startup (typically a missing hidden import or data file that
dev runs never surface). **Required before every merge**, and re-required
after ANY dependency change (see traps below).

### Known build traps (all encoded in `installer/ogp.spec`; verified 2026-07-04)

| Trap | Rule | Why (source) |
|---|---|---|
| MCP stack dynamic imports | `collect_submodules(...)` + `copy_metadata(...)` for `mcp.server`/`mcp.shared`/`mcp.types`, `uvicorn`, `starlette`, `anyio`, `sse_starlette`, `pydantic`, `pydantic_settings`, `httpx_sse` (+ metadata for `pydantic_core`, `mcp`) | uvicorn/anyio/starlette load protocol/loop/lifespan submodules dynamically and read distribution metadata at import; without both, the frozen Agent API fails while dev runs pass (docs/07 §7.6) |
| Never walk top-level `mcp` | Collect the concrete subpackages, NOT `collect_submodules("mcp")` | Walking `mcp` imports `mcp.cli`, which `sys.exit(1)`s without the unbundled `typer` extra and aborts the build; the spec wraps collection in `_safe_collect_submodules` |
| Never exclude `multiprocessing` | It is deliberately absent from the spec `excludes` (comment in spec) | uvicorn imports it eagerly (`uvicorn.supervisors → basereload → _subprocess`) even single-process; excluding it → GUI runs, embedded server silently dies with `ModuleNotFoundError` |
| UPX vs pydantic_core | `upx_exclude=["pydantic_core*.pyd"]` | UPX can corrupt that compiled extension, killing the Agent API at runtime |
| PyQt6-WebEngine pin | `PyQt6-WebEngine>=6.10.0,<6.11` in `pyproject.toml` | Pinned below 6.11 (satellite map picker uses QWebEngineView); do not bump casually |
| mcp major pin | `mcp>=1.12,<2.0` | mcp v2 renames `FastMCP` → `MCPServer` (pyproject comment); `structured_output=False` behavior verified against mcp 1.28.1 |
| Any new dependency | Re-run the exe build + `timeout 8` smoke BEFORE merge | Frozen imports diverge from dev imports; the smoke test is the only thing that catches it (CLAUDE.md Quick Reference) |
| WebEngine import order | `PyQt6.QtWebEngineCore/Widgets/WebChannel` are explicit hiddenimports; the import must run before `QApplication` is created (handled in `main.py`) | Spec comment |

## Building the NSIS installer

```bash
# Full build (PyInstaller + NSIS)
venv/Scripts/python.exe installer/build_installer.py

# Or with an explicit version, or partial:
venv/Scripts/python.exe installer/build_installer.py --version 1.23.0
venv/Scripts/python.exe installer/build_installer.py --skip-nsis         # PyInstaller only
venv/Scripts/python.exe installer/build_installer.py --skip-pyinstaller  # NSIS only, needs existing dist/
```

Expected outcome: `dist/OpenGardenPlanner-v{VERSION}-Setup.exe` (~34 MB, LZMA).
The script writes `src/open_garden_planner/_version.py` before freezing (the
update checker reads it), cleans the previous `dist/OpenGardenPlanner/`, runs
PyInstaller with `--clean`, then `makensis` on `installer/ogp_installer.nsi`.
Default version without `--version` is a stale `1.0.0` constant — real releases
come from CI (`release.yml`, windows-latest), which passes the computed version.
Release/versioning policy itself → **ogp-change-control**.

**Rescue-user-data behavior (issue #199 / ADR-027):** the uninstall section runs
`RMDir /r "$INSTDIR"`, and upgrades silently run the *old* uninstaller first —
so anything saved in the install dir would be wiped. Two guards: (1) the app
never defaults a file dialog into the install dir (see next section); (2) the
uninstaller copies any top-level `$INSTDIR\*.ogp` to
`Documents\Open Garden Planner\Recovered Plans` before the recursive delete
(`/SD IDOK` keeps silent upgrades from hanging on the prompt).

## Where things land — artifact & data map

| Thing | Location | Source (verified) |
|---|---|---|
| Frozen exe bundle | `dist/OpenGardenPlanner/` (installer: `dist/OpenGardenPlanner-v{V}-Setup.exe`; intermediates in `build/`) | `installer/build_installer.py` |
| Default save/open/export dir | `<Documents>/Open Garden Planner` — or the open project's folder. EVERY file dialog must route through `app/paths.py` (`default_dialog_dir()` / `default_save_path()`), the single chokepoint; it never returns the CWD/install dir | `src/open_garden_planner/app/paths.py` (issue #199) |
| Autosave (saved project) | Same directory as the project: `~autosave_{name}.ogp` | `src/open_garden_planner/services/autosave_service.py` |
| Autosave (untitled) | System temp dir: `~autosave_untitled.ogp` | same |
| QSettings | `QSettings("cofade", "Open Garden Planner")` → Windows registry `HKCU\Software\cofade\Open Garden Planner`; Linux `~/.config/cofade/Open Garden Planner.conf` (tests redirect to org `cofade_test`) | `app/settings.py:112`, `tests/conftest.py` |
| App-data dir | Windows `%APPDATA%\OpenGardenPlanner`; Linux `$XDG_DATA_HOME`-or-`~/.local/share` `/OpenGardenPlanner`; macOS `~/Library/Application Support/OpenGardenPlanner` | `services/plant_library.py::get_app_data_dir()` |
| User smart symbols | `<app-data>/smart_symbols/*.json` (drop-a-file extensible; bundled ones in `resources/data/smart_symbols/`) | `services/smart_symbol_library.py` |
| Translations | `src/open_garden_planner/resources/translations/*.ts|.qm` | dir listing |
| API keys | `.env` at repo root (`OGP_GOOGLE_MAPS_KEY`), loaded by `main.py` via python-dotenv; optional | `main.py` |

**Rule for new code:** never construct a default file-dialog path yourself —
call `app/paths.py`. Anything defaulting into the install dir recreates data
loss #199.

## Agent API quick check

With the app running, the embedded MCP server is at
**`http://127.0.0.1:8765/mcp`** — on by default
(`AppSettings.agent_api_enabled` default True, port 8765, loopback-only,
auto-starts on launch; Preferences toggle disables). One-liner:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8765/mcp
```

Expected: **any HTTP status printed** (a bare GET without MCP `Accept` headers
gets a 4xx — that still proves the server is listening). `000` + curl exit 7
(connection refused) = server not running (app closed, setting off, or port
changed in Preferences). After changing the MCP dependency stack, re-verify
against the **frozen** exe, not just dev (docs/07 §7.6).

## Provenance and maintenance

Volatile facts stamped 2026-07-04 (v1.23.0). Re-verify with:

| Fact | One-line re-check |
|---|---|
| Version + deps + pins (WebEngine <6.11, mcp <2.0) | `grep -A20 'dependencies = \[' pyproject.toml` |
| Dev extra contents (pytest/ruff/mypy/bandit; no PyInstaller) | `sed -n '/\[project.optional-dependencies\]/,/^\[/p' pyproject.toml` |
| CI apt package list + offscreen env | `grep -A2 'apt-get install' .github/workflows/ci.yml; grep QT_QPA .github/workflows/ci.yml` |
| Spec traps (safe-collect, no-multiprocessing-exclude, upx_exclude) | `grep -n 'collect_submodules\|multiprocessing\|upx_exclude' installer/ogp.spec` |
| Installer output name/paths | `grep -n 'DIST_DIR\|Setup.exe' installer/build_installer.py` |
| Agent API defaults (enabled/port/path) | `grep -n 'DEFAULT_AGENT_API\|port: int = 8765\|path: str' src/open_garden_planner/app/settings.py src/open_garden_planner/agent_api/server.py` |
| Path chokepoint + autosave locations | `grep -n 'def default_dialog_dir\|AUTOSAVE_PREFIX' src/open_garden_planner/app/paths.py src/open_garden_planner/services/autosave_service.py` |
| Translation file set | `ls src/open_garden_planner/resources/translations/` |
| i18n gate still exists | `grep -n test_german_ts_has_no_unfinished tests/unit/test_i18n.py` |
