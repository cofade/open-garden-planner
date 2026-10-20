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

## Current translation gate (#496)

`scripts/check_translations.py` is the required source/catalog/binary gate for every
locale in `SUPPORTED_LANGUAGES`. New wrapped UI keys require all target translations;
new locales require all current keys. Run `update_translations.py`, complete targets
(the fill helper is German-only), compile, then check. No coverage allowances or manual
locale test lists. The compiler rejects incomplete/blank targets and unsupported plural
input; vanished records cannot satisfy coverage. See section 8.3 and docs/TRANSLATING.md.
The older German-only check mentioned in historical examples below is supplementary.
Truly unwrapped UI prose and linguistic quality still require review.


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
- **i18n gate** — the source-derived check that requires every wrapped UI key in every registered
  target language.

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
| Interpreter path | `venv/Scripts/python.exe` (Git-Bash form used throughout AGENTS.md) or `venv\Scripts\python.exe` (cmd) | `.venv/bin/python` |
| GUI runs? | Yes — the app targets Windows (pyproject classifier: `Operating System :: Microsoft :: Windows`) | Not intended; tests run with `QT_QPA_PLATFORM=offscreen` (also set defensively in `tests/conftest.py`) |
| Exe/installer build | Yes (PyInstaller + NSIS; release CI uses windows-latest) | No |

`pyproject.toml` declares constraints; `uv.lock` selects authoritative dependency versions.
`pylock.toml` is the checked PEP 751 export. Do not install from stale requirements files.

## From-scratch checklist

Install Python 3.11 and clone the repository. Bootstrap uv using the one pin in the manifest:

```bash
python -c 'import subprocess,sys,tomllib; p=tomllib.load(open("pyproject.toml","rb"))["tool"]["uv"]["required-version"].removeprefix("=="); subprocess.check_call([sys.executable,"-m","pip","install","uv=="+p])'
uv sync --locked --python 3.11 --all-extras --group build --no-install-project
uv pip install --python .venv/Scripts/python.exe --no-deps --no-build-isolation -e .
uv pip check --python .venv/Scripts/python.exe
```

On Linux use `.venv/bin/python` in the last two commands. CI and release use the shared
`.github/actions/setup-locked-env/action.yml` recipe, including lock freshness. Linux Qt
libraries are listed in ci.yml; tests use QT_QPA_PLATFORM=offscreen, without xvfb.
Build tools and their setuptools/wheel backend are installed from the build group.
Install NSIS separately for a Windows installer; its version and the OS are outside the
Python lock's scope. Optional map credentials are unnecessary for tests and reviews.

Existing command examples below use `venv`; substitute `.venv` for this locked environment.
The supported application metadata remains Python >=3.11; CI uses Python 3.11 on both OSes.

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
| Correctness battery | `venv/Scripts/python.exe -m pytest tests/ -v` | All pass. Parallel by default (`addopts`), and **excludes the `perf`-marked timing tests** - the next row |
| Wall-clock budgets | `venv/Scripts/python.exe -m pytest tests/ -m perf -n 0` | All pass, on a quiet runner. `pyproject.toml` sets `addopts = "-v --tb=short -n auto --dist worksteal -m 'not perf'"`, `qt_api = "pyqt6"`, `testpaths = ["tests"]`. `-n 0` because running the timing tests across workers is the thing the split exists to prevent (§8.10.4) |
| Unit layer only | `venv/Scripts/python.exe -m pytest tests/unit -v` | ~106 files (Qt-free-ish fast tests) |
| Integration layer | `venv/Scripts/python.exe -m pytest tests/integration -v` | ~74 files (end-to-end UI workflows) |
| UI layer | `venv/Scripts/python.exe -m pytest tests/ui -v` | ~19 files (widget-level) |
| Single test | `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished -v` | `::Class::method` selector form |
| Lint | `venv/Scripts/python.exe -m ruff check src/ tests/ scripts/` | Zero findings. Config in `pyproject.toml` (`[tool.ruff]`, py311, line-length 100, E/W/F/I/B/C4/UP/ARG/SIM) |
| Security scan | `venv/Scripts/python.exe -m bandit -r src/ --severity-level high` | Zero HIGH findings (CI fails on HIGH). Bandit is in the `[dev]` extra |
| Types | `venv/Scripts/python.exe scripts/check_mypy_baseline.py` | Strict production-source mypy with Linux/Windows per-file allowances; CI rejects increases |

Notes:
- pytest-qt provides `qtbot`; PyQt6 tests need the fixture even when unused
  (Qt init) — `tests/**` has ruff per-file ignores ARG001/ARG002 for this.
- `tests/conftest.py` session-scope-redirects `QSettings` to a
  `"cofade_test"` org so tests never pollute real user settings.

## Translations pipeline (i18n)

Run after adding or changing ANY user-visible string:

```bash
PYTHONUTF8=1 venv/Scripts/python.exe scripts/update_translations.py
# Complete every registered target catalog; fill_translations.py assists German only.
PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py
PYTHONUTF8=1 venv/Scripts/python.exe scripts/compile_translations.py
venv/Scripts/python.exe scripts/check_translations.py
```

| Fact | Value (verified) |
|---|---|
| `.ts` / `.qm` location | `src/open_garden_planner/resources/translations/` — `open_garden_planner_de.ts/.qm` and `open_garden_planner_en.ts/.qm` |
| `fill_translations.py` | German convenience mapping; fills live source keys and preserves completed values. Complete other registered target catalogs directly |
| `compile_translations.py` | Pure-Python `lrelease` replacement — compiles every `.ts` in that dir to `.qm` (no Qt tooling needed) |
| `PYTHONUTF8=1` | Required on Windows: the scripts handle umlauts; without it the default cp1252 codec mangles them |
| Gate test | `venv/Scripts/python.exe -m pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished` — is a supplementary German regression check. The required `scripts/check_translations.py` checks every wrapped source key in every registered locale; truly unwrapped display strings still require review (see AGENTS.md i18n section) |
| Packaging | `installer/ogp.spec` bundles the whole `resources/translations/` dir into the exe — recompile `.qm` BEFORE building |

## Building the frozen exe (PyInstaller)

```bash
# Windows — prerequisite: pip install pyinstaller (not in [dev])
venv/Scripts/python.exe -m PyInstaller installer/ogp.spec --noconfirm
```

Expected outcome: bundle at **`dist/OpenGardenPlanner/`** (~611 MiB in the local v1.29.6 build measured 2026-10-09; not a fixed limit)
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

### `--selftest` — what the smoke test cannot see

The smoke test proves the process **stays up**. It cannot see a subsystem that
died silently behind an `except`, which is exactly how issue **#291** (the Agent
API never started in any released exe) survived six releases, and how **#277** (a
micro mismatch between the core Qt runtime and the old 3D view's Qt 3D wheels) shipped
a crash — that view was imported lazily, so startup and the 8 s smoke both passed.
`main.py --selftest` binds an ephemeral port and starts a real `AgentApiServer` with
poisoned providers, asserting `is_running`, and runs the A1 checks. (Until Phase 17
L1.10 it also imported the six Qt 3D bindings and compared the runtime with their
wheel's micro; that view and its two wheels are gone, and the two remaining Qt pins
are guarded by `tests/unit/test_qt_runtime_pins.py`.)

Since Phase 17 L1.2 it **renders**: the Qt Quick 3D engine package
(`ui/view3d/quick3d/`) is lazily loaded too, and its scene is QML and shader
*files* in the bundle. `--selftest` loads them from the bundle, draws one
hidden 160 × 120 frame with every material kind and checks the pixels
(`ui/view3d/quick3d/selftest.py`). It needs no GPU — Direct3D 11 on WARP will
do, which is what the release runner has. **It cannot hang:** ONE watchdog
bounds the whole self-test — all three blocks, not only the render — and after
300 s writes the reason and every thread's stack into the log and exits with
code 1 (`main._run_selftest_bounded`). That exit was measured NOT to end a
Windows process deadlocked inside Qt, so the watchdog is supervised: the exe
starts itself a second time (`--selftest-supervisor`), and that process
terminates the first at 310 s, exit code 1. Four things to know when it fails:

- The exit code cannot say which check failed; the self-test writes a log to
  `%APPDATA%\cofade\Open Garden Planner\OpenGardenPlanner-selftest-3d.log`
  (beside `app.log`), or to the path in `OGP_SELFTEST_LOG`. It names the
  graphics adapter that rendered, every 3D check, and ends with
  `[selftest_exit] code=…`. A log whose 3D part passed and whose exit code is
  1 points at the first two blocks.
- `[watchdog] fired=True … did not finish within 300 s`, then `Timeout` and
  stack traces: a hang. The frame at the top of the main thread's stack is
  where.
- `[supervisor] fired=True … terminated from outside`: the process survived
  its own watchdog — a deadlock inside Qt; the stack dump above that line
  shows the threads waiting for each other. (`[watchdog] armed=True …
  supervisor=process <pid>` only says the second process was started.)
- Under `QT_QPA_PLATFORM=offscreen` nothing renders 3D, so the 3D block
  FAILS there by design (`RenderError: Qt Quick runs on the Software backend`).
  Run `--selftest` with the real platform. To check the GPU-less path locally,
  set `QSG_RHI_PREFER_SOFTWARE_RENDERER=1` (the log then says
  `Microsoft Basic Render Driver`).

Measured 2026-10-11 (three runs each, the whole `--selftest`): frozen exe
3.0–4.1 s on an RTX 4070 and 3.0–3.1 s on WARP on a quiet machine; 6.1–7.2 s on either
while other test suites were running.

```bash
powershell -Command '$p = Start-Process "dist/OpenGardenPlanner/OpenGardenPlanner.exe" -ArgumentList "--selftest" -Wait -PassThru; exit $p.ExitCode'
echo $?   # 0 = PASS, 1 = a subsystem is dead
```

**Quoting matters — the single quotes are load-bearing.** The outer string is
**single**-quoted for bash and the inner PowerShell arguments are
**double**-quoted, not the other way round. Inverted, bash expands `$p` itself
before PowerShell ever sees it, and PowerShell receives
`= Start-Process … ; exit .ExitCode` — two `CommandNotFoundException`s and exit
1, i.e. a gate that now fails unconditionally instead of passing
unconditionally. Both failure directions have been observed here; the form above
is the one that was executed and returns the real code (verified end-to-end: a
child exiting 3 propagates 3).

**Two further traps in the invocation, both measured:**

1. **PowerShell does not wait on a GUI-subsystem process.** A plain
   `& "…\OpenGardenPlanner.exe" --selftest` returns in ~6 ms with an *empty*
   `$LASTEXITCODE` — a gate that passes unconditionally. `Start-Process -Wait
   -PassThru` is why `.github/workflows/release.yml:114` is written that way.
2. **A shell pipe hands the windowed exe a real `sys.stdout`.** Run from Git
   Bash the plain form *does* wait and *does* return the exit code — but the
   selftest's prints are visible (~300 bytes measured; the exact count varies
   with the Qt version string). So the run had a live stdout handle, and a
   regression of #291's `log_config=None` fix would pass cleanly. Use the
   `Start-Process` form, which gives the process no inherited stdout handle.
   **Why, in full: §11.4's #291 entry** (corrected in PR #334 — it used to
   state the claim without the no-inherited-handle condition).

`release.yml` runs `--selftest` against the built exe, but only *after* merge.
`frozen-selftest.yml` (Phase 17 L1.2) builds the bundle with the release recipe
— `python installer/build_installer.py --skip-nsis` — and runs the smoke and
the self-test on every pull request that changes shipped code
(`src/open_garden_planner/**`), the installer, the dependency files or the gate
workflows; it is path-filtered and not a required check. Two things about that
bundle: built without `--version` it calls itself v1.0.0 (the script's
default), so during the smoke its update check finds a newer release and shows
the update bar — the app has no switch for that check, and the verdict does not
depend on it; and the smoke also passes a process that is blocked in an error
dialog — the self-test is the gate. Running the gate locally is still what
makes it a merge gate rather than a post-mortem.

### Known build traps (all encoded in `installer/ogp.spec`; verified 2026-07-04)

| Trap | Rule | Why (source) |
|---|---|---|
| MCP stack dynamic imports | `collect_submodules(...)` for `mcp.server`/`mcp.shared`/`mcp.types`, `uvicorn`, `starlette`, `anyio`, `sse_starlette`, `pydantic`, `pydantic_settings`, `httpx_sse`; distribution metadata is bundled for the required runtime closure by `installer/runtime_closure.py`, plus actual collected wheel owners via `installer/frozen_inventory.py` (including hooks and distinct vendored copies) | uvicorn/anyio/starlette load protocol/loop/lifespan submodules dynamically and read distribution metadata at import; without both, the frozen Agent API fails while dev runs pass (docs/07 §7.6). Do not hand-type a per-stack metadata list — a new dependency would silently leave the notices/SBOM inventory (AUD-051/#454) |
| Never walk top-level `mcp` | Collect the concrete subpackages, NOT `collect_submodules("mcp")` | Walking `mcp` imports `mcp.cli`, which `sys.exit(1)`s without the unbundled `typer` extra and aborts the build; the spec wraps collection in `_safe_collect_submodules` |
| Never exclude `multiprocessing` | It is deliberately absent from the spec `excludes` (comment in spec) | uvicorn imports it eagerly (`uvicorn.supervisors → basereload → _subprocess`) even single-process; excluding it → GUI runs, embedded server silently dies with `ModuleNotFoundError` |
| UPX vs pydantic_core | `upx_exclude=["pydantic_core*.pyd"]` | UPX can corrupt that compiled extension, killing the Agent API at runtime |
| PyQt6-WebEngine pin | `PyQt6-WebEngine>=6.10.0,<6.11` in `pyproject.toml` | Pinned below 6.11 (satellite map picker uses QWebEngineView); do not bump casually |
| mcp major pin | `mcp>=1.23,<2.0` | mcp v2 renames `FastMCP` → `MCPServer` (pyproject comment); `structured_output=False` behavior verified against mcp 1.28.1 |
| Any new dependency | Re-run the exe build + `timeout 8` smoke **and `--selftest`** BEFORE merge | Frozen imports diverge from dev imports, and the smoke alone cannot see a subsystem that died silently (#291, #277) — see the `--selftest` section above (AGENTS.md Quick Reference) |
| A dependency REMOVED from the lock | Re-sync the venv (`uv sync --locked …`, the from-scratch checklist) before building locally | Removing a pin does not uninstall its wheel; PyInstaller's Qt hooks collect the QML modules (and the DLLs their plugins need) of every Qt wheel installed. Measured in Phase 17 L1.10: a dev-venv build after dropping the old 3D view's runtime wheel still carried its eleven DLLs and its QML module; a locked-env build did not (ADR-048 closing addendum, §11.4.20) |
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

Expected outcome: `dist/OpenGardenPlanner-v{VERSION}-Setup.exe` (v1.29.6 release download ~171 MiB, measured 2026-10-09; LZMA).
The script writes `src/open_garden_planner/_version.py` before freezing (the
update checker reads it), cleans the previous `dist/OpenGardenPlanner/`, runs
PyInstaller with `--clean`, then `makensis` on `installer/ogp_installer.nsi`.
Default version without `--version` comes from `pyproject.toml` — real releases
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
| QSettings | `QSettings("cofade", "Open Garden Planner")` → Windows registry `HKCU\Software\cofade\Open Garden Planner`; Linux `~/.config/cofade/Open Garden Planner.conf` (tests redirect to org `cofade_test`) | `app/settings.py:26` `create_qsettings`, `tests/conftest.py` |
| App-data dir | Windows `%APPDATA%\OpenGardenPlanner`; Linux `$XDG_DATA_HOME`-or-`~/.local/share` `/OpenGardenPlanner`; macOS `~/Library/Application Support/OpenGardenPlanner` | `services/plant_library.py::get_app_data_dir()` |
| User smart symbols | `<app-data>/smart_symbols/*.json` (drop-a-file extensible; bundled ones in `resources/data/smart_symbols/`) | `services/smart_symbol_library.py` |
| Translations | `src/open_garden_planner/resources/translations/*.ts|.qm` | dir listing |
| API keys | Google Maps key is stored in Preferences at `api_keys/google_maps_key`; blank Preferences falls back to `.env` at repo root (`OGP_GOOGLE_MAPS_KEY`), loaded by `main.py` via python-dotenv; optional | `app/settings.py`, `application.py`, `main.py` |

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
| i18n gate still exists | `grep -n test_registered_languages_cover_current_source_and_binary tests/unit/test_i18n.py` |

### Host PATH contamination: ICU / WebEngine (#453, 2026-10-13)

PyInstaller collected ICU 78.3 from the Codex Poppler runtime on PATH. The frozen
WebEngine import then failed with a missing procedure; source Qt loaded Windows'
native ICU 72.1. Compare Analysis-00.toc provenance, DLL versions and PE exports
before changing Qt pins. pefile's default 8,192-export limit can produce false
missing-symbol reports for Qt; use a higher limit for that diagnostic.
A clean build with PATH restricted to the locked venv, Windows system directories,
Python and Git passed detached --selftest (0) and the eight-second smoke (124).
The package's self-test also checks strict plan persistence, supported image codecs
and verified-installer hashing. No dependency or spec change was required.
