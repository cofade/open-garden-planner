---
name: ogp-config-and-flags
description: >
  Catalog of every configuration axis in Open Garden Planner: QSettings keys
  (AppSettings), UI-state persistence (UiStateStore), environment variables
  (.env / OGP_GOOGLE_MAPS_KEY / QT_QPA_PLATFORM / PYTHONUTF8), project-file
  version + per-plan settings, hidden-feature toggles in code, tooling config
  (pyproject/ruff/mypy/pytest/pins/ogp.spec), and CI knobs. Load this when:
  adding or changing a setting or flag; wondering what a settings key does or
  what its default is; configuring environment variables or .env; touching the
  Preferences dialog; deciding whether a change needs a FILE_VERSION bump; or
  a feature seems mysteriously disabled (hidden panel, missing API key,
  default-off snap mode). Includes the "how to add a setting" checklist.
---

# OGP Configuration & Flags Catalog

**Verified 2026-07-03 against v1.23.0** by reading `settings.py`, `ui_state.py`,
`project.py`, `main.py`, `application.py`, `preferences_dialog.py`,
`pyproject.toml`, `installer/ogp.spec`, `ci.yml`, `release.yml`. Flags drift —
if the repo has moved on, re-verify with the commands at the bottom before
trusting a row.

**When NOT to use this skill:** build/run/test commands (`ogp-build-and-run`),
what a subsystem does (`ogp-architecture-contract`, `ogp-qt-cad-reference`,
`ogp-garden-domain-reference`), release/branch/PR process (`ogp-change-control`),
debugging technique (`ogp-debugging-playbook`, `debug-verbose`).

Jargon, defined once:
- **QSettings** — Qt's per-user persistent key/value store. This app constructs
  it as `QSettings("cofade", "Open Garden Planner")`, so it lives at:
  Windows registry `HKEY_CURRENT_USER/Software/cofade/Open Garden Planner`,
  macOS `~/Library/Preferences/com.cofade.Open Garden Planner.plist`,
  Linux `~/.config/cofade/Open Garden Planner.conf`.
- **App setting vs per-plan setting** — app settings (QSettings) follow the
  *user* across all plans; per-plan settings live inside the `.ogp` JSON file
  (`ProjectData`) and follow the *document*.
- **Additive `.ogp` key** — a new top-level key in the project JSON that old
  builds silently ignore on load. Additive keys do NOT bump `FILE_VERSION`.

---

## 1. AppSettings — QSettings catalog

Source: `src/open_garden_planner/app/settings.py` (all keys enumerated below —
the file has no others as of v1.23.0). Access via the singleton
`get_settings()`; each key has a typed property with the default baked in.
All rows **production** unless noted.

### General / startup

| Key | Property | Type | Default | Read by |
|---|---|---|---|---|
| `autosave/enabled` | `autosave_enabled` | bool | `True` | `services/autosave_service.py` |
| `autosave/interval_minutes` | `autosave_interval_minutes` | int | `5` (clamped 1–30 on both read and write) | `services/autosave_service.py` |
| `recent_files` | `recent_files` (+ `add_recent_file`, max 10) | list[str] | `[]` | File menu in `application.py` |
| `startup/show_welcome` | `show_welcome_on_startup` | bool | `True` | `welcome_dialog.py`, startup sequence |
| `updates/skipped_version` | `skipped_version` | str | `""` | update checker in `application.py` ("Skip this version") |

> `window/geometry` and `window/state` (`AppSettings.window_geometry` /
> `window_state`) were **removed in #285**: a never-called duplicate of what
> `UiStateStore` owns under `UiState/` (§2). Old real stores may still hold the
> orphaned keys; nothing reads them.

### Appearance & language

| Key | Property | Type | Default | Read by |
|---|---|---|---|---|
| `appearance/theme_mode` | `theme_mode` | `ThemeMode` (`light`/`dark`/`system`; invalid → SYSTEM) | `"system"` | `ui/theme.py` + every color consumer — **see trap below** |
| `appearance/language` | `language` | str | `"en"` | `core/i18n.py` |
| `appearance/show_shadows` | `show_shadows` | bool | `True` | canvas / View menu |
| `appearance/show_scale_bar` | `show_scale_bar` | bool | `True` | canvas / View menu |
| `appearance/show_labels` | `show_labels` | bool | `True` | canvas / View menu |
| `appearance/show_constraints` | `show_constraints` | bool | `True` | canvas / View menu |
| `appearance/show_spacing_circles` | `show_spacing_circles` | bool | `True` | `canvas_view.py`, spacing-ring paint gate |

> **TRAP (§11.4, verified in `docs/11-risks-and-technical-debt/README.md`):
> `ThemeColors.get_colors(ThemeMode.SYSTEM)` ignores the user's theme choice.**
> `apply_theme()` only writes a stylesheet and never mutates
> `QApplication.palette()`, so SYSTEM-mode detection probes the *OS* palette. A
> user who explicitly picked LIGHT on a dark-default OS gets the dark palette
> dict. Rule: only `theme.py` may call `get_colors(ThemeMode.SYSTEM)`; every
> other consumer must call `ThemeColors.get_colors(get_settings().theme_mode)`.

### Canvas snap & input (Phase 13 CAD packages)

| Key | Property | Default | Status / note |
|---|---|---|---|
| `canvas/object_snap_enabled` | `object_snap_enabled` | `True` | production |
| `canvas/midpoint_snap_enabled` | `midpoint_snap_enabled` | `True` | production (US-A3) |
| `canvas/intersection_snap_enabled` | `intersection_snap_enabled` | `True` | production (US-A3) |
| `canvas/nearest_snap_enabled` | `nearest_snap_enabled` | **`False`** | production, **deliberately default-OFF** (US-B4: fallback snap would surprise users relying on free placement near edges) |
| `canvas/perpendicular_snap_enabled` | `perpendicular_snap_enabled` | **`False`** | production, default-OFF opt-in precision aid (US-B5) |
| `canvas/tangent_snap_enabled` | `tangent_snap_enabled` | **`False`** | production, default-OFF opt-in precision aid (US-B6) |
| `canvas/dynamic_input_enabled` | `dynamic_input_enabled` | `True` | production (US-A4 cursor overlay + typed coordinates) |

All read by `ui/canvas/canvas_view.py` / the snap pipeline; toggled from the
View menu. If a snap "doesn't work", check nearest/perpendicular/tangent first —
they default OFF.

### Tool memory ("last used" values)

| Key | Property | Default | Read by |
|---|---|---|---|
| `tools/fillet_last_radius_cm` | `fillet_last_radius_cm` | `25.0` | `core/tools/fillet_tool.py` (prefills the dialog, US-B3) |
| `tools/chamfer_last_distance_cm` | `chamfer_last_distance_cm` | `25.0` | same |

### Weather & tasks

| Key | Property | Default | Read by |
|---|---|---|---|
| `weather/frost_warning_orange_c` | `frost_warning_orange_c` | `5.0` °C | frost alerting (US-12.2) |
| `weather/frost_warning_red_c` | `frost_warning_red_c` | `2.0` °C | frost alerting |
| `tasks/notify_overdue_on_startup` | `notify_overdue_tasks_on_startup` | `True` | startup `TaskReminderBar` (US-C2) |

### Agent API (embedded MCP server, US-D1.x)

| Key | Property | Default | Note |
|---|---|---|---|
| `agent_api/enabled` | `agent_api_enabled` | **`True`** | Default ON is a locked product decision (`tests/unit/test_agent_api_settings.py` asserts the class constants). Read-only tools, loopback-only. Comment in `settings.py`: token auth must land before D2 write tools default-expose mutate access. |
| `agent_api/port` | `agent_api_port` | `8765` | Clamped 1024–65535 on read and write. Server URL is `http://127.0.0.1:<port>/mcp`. |

Startup path (verified in `application.py`): `_setup_agent_api()` →
`QTimer.singleShot(1500, self._maybe_start_agent_api)` → starts only
`if get_settings().agent_api_enabled`. Preferences dialog restarts/stops the
server when either value changes (compares before/after tuple around the
dialog, ~line 3758).

### 3D view (Phase 17 L1.4, ADR-064 addendum "looks, sky and the animation policy")

| Key | Property | Default | Note |
|---|---|---|---|
| `view3d/quality` | `view3d_quality` | `"auto"` | One of `auto` / `low` / `medium` / `high` / `ultra` (`AppSettings.VIEW3D_QUALITY_CHOICES`, pinned against `core/scene3d/look.py` `QUALITY_CHOICES`); anything else reads as `auto`, so a hand-edited store never reaches the renderer with a name nobody knows. A preset changes what a frame costs, never the mood, the light's direction or the camera. |
| `view3d/reduced_motion` | `view3d_reduced_motion` | `False` | True stops the wind for good: the shaders' clock rests at 0, so every vertex is where its mesh puts it. Qt 6.11 exposes no operating-system "reduce motion" preference (`QStyleHints` has none; a drift guard in `tests/unit/test_view3d_look_settings.py` fails the day one appears), so the setting is the application's own. |
| `view3d/auto_quality_level` | `view3d_auto_level` | `"medium"` | Not in the dialog: where `auto` settled last (`low` / `medium` / `high`, `VIEW3D_AUTO_LEVELS`), written by the look controller on every step of the automatic preset, read when the next 3D view is built. |
| `view3d/auto_quality_bars` | `view3d_auto_bars` | `{}` (empty JSON) | Not in the dialog: the levels `auto` had to leave for being too slow, `{level: [until, next_retry_s]}` — `until` in seconds since the epoch, `next_retry_s` how long the next bar on that level lasts (300 s doubling to 3,600). Written with the level on every step, seeded into `AutoPreset` at the first poll of the next session, so a level that proved too slow is not retried in every session (L1.4 fix round 1). Anything that is not a level with two finite numbers is dropped on read. |

Offered in Preferences → 3D View (every main window has the 3D workspace since L1.9). In the workspace's compatibility mode (software rendering) `auto` reads as `low` and nothing animates, whatever `view3d/reduced_motion` says; reduced motion also freezes `auto` (no animation, no presented frames to measure). On "Save" `application.py` `_on_preferences` calls `Workspace.apply_look_settings()` → `LookController.reload_settings()`: a quality change is ONE `set_look` call (no camera, no geometry, no sky), reduced motion one wind call. Reading a setting does not import the 3D core (`settings.py` writes the two tuples out; a unit test pins them).

### Plant-DB API keys (stored in QSettings, NOT .env)

| Key | Property | Default |
|---|---|---|
| `api_keys/trefle_token` | `trefle_api_token` | `""` |
| `api_keys/perenual_key` | `perenual_api_key` | `""` |
| `api_keys/permapeople_key_id` | `permapeople_key_id` | `""` |
| `api_keys/permapeople_key_secret` | `permapeople_key_secret` | `""` |

Entered in Preferences (with per-API "Test" buttons); consumed by the online
plant-search services. The Google Maps key is also available in Preferences at
`api_keys/google_maps_key`, with `OGP_GOOGLE_MAPS_KEY` / `.env` as the fallback;
neither source is ever bundled in a binary.

---

## 2. UiStateStore — what UI state persists (and what deliberately does not)

Source: `src/open_garden_planner/app/ui_state.py`. Same QSettings backend as §1
— both take it from `app/settings.create_qsettings()`, the only store factory in
`src/` (#285, ADR-041; gated by `tests/unit/test_settings_chokepoint.py`, so do
not hand-roll a second one) — with keys under the `UiState/` group to avoid
colliding with §1. All production.

| Key | Saved / restored |
|---|---|
| `UiState/geometry` | `QMainWindow.saveGeometry()` |
| `UiState/window_state` | `QMainWindow.saveState()` (docks/toolbars) |
| `UiState/splitter_<name>` | per-named `QSplitter.saveState()` |

**Deliberately NOT persisted (ADR-030 / issue #226):** per-panel
collapse/expand/pin state. The sidebar accordion starts fully collapsed every
session; the old `save_panel_state`/`restore_panel_state` helpers were
**removed** (the module docstring says so explicitly). Do not re-add panel
persistence without revisiting ADR-030.

---

## 3. Environment variables & .env

| Variable | Status | Purpose | What breaks without it |
|---|---|---|---|
| `OGP_GOOGLE_MAPS_KEY` | production, **user-supplied, never bundled** | Google Maps satellite background picker fallback (ADR-019, docs/08 §8.15) | Preferences (`api_keys/google_maps_key`) takes precedence; this environment/`.env` value is the fallback. The "load satellite background" menu action is disabled with a tooltip when neither source is set; `GoogleMapsKeyMissingError` if reached anyway. Bundling either source in the installer would let it be reverse-engineered and abused (`services/google_maps_service.py` docstring). |
| `QT_QPA_PLATFORM=offscreen` | production (test infra) | Headless Qt rendering | Set by `tests/conftest.py` via `os.environ.setdefault(...)` (line 11) AND by `ci.yml`'s test job env. Without it, tests need a display server. |
| `PYTHONUTF8=1` | production (script infra) | Forces UTF-8 I/O for `scripts/fill_translations.py` / `compile_translations.py` (German umlauts) | Mojibake / encode errors on Windows. Per AGENTS.md, always run translation scripts with it. |
| ~~`OGP_QUICK3D=1`~~ | **gone** (Phase 17 L1.3 – L1.9) | Was the internal switch of the Plan / 3D / Split workspace. L1.9 made the workspace the default and deleted the switch with `quick3d_workspace_enabled()`; nothing reads the variable any more (`tests/integration/test_view3d_workspace.py::test_the_workspace_is_always_there_and_no_switch_is_read`). No escape hatch replaces it: the safety net for a graphics device that fails is the start marker and compatibility mode (`ui/view3d/init_guard.py`, ADR-065 addendum "the default and the removal"). | Nothing. |
| `OGP_RENDER3D=1`, `OGP_WORKSPACE_GATE`, `OGP_WORKSPACE_GATE_EXE` | test infra | The opt-in render tier (real windows on a real device); the scenario file of the workspace gate, read by `tests/integration/workspace_gate_hook.py` only; the frozen gate build's exe for `tests/integration/test_view3d_workspace_render.py -k frozen` (docs/08 §8.10.27). | The render tier skips; the gate's hook still moves the settings store and runs no scenario; the frozen tests skip. |

**.env loading (verified in `main.py` lines 14–27):** `python-dotenv`'s
`load_dotenv()` on the first existing candidate of, in order:
1. **frozen** (PyInstaller): `.env` next to the `.exe` (`sys.executable`'s dir —
   the source-relative lookup misses because `__file__` sits in `_internal/`);
2. **dev**: repo-root `.env` (three parents up from `main.py`).

First hit wins; loading happens at module import, before `QApplication`.

---

## 4. Project-file (.ogp) configuration axes

Source: `src/open_garden_planner/core/project.py`.

### FILE_VERSION

- Current: **`FILE_VERSION = "1.4"`** (line 35). 1.4 = Phase 13 Package B's
  `bezier` and `arc` item types; v1.3 files load transparently.
- **What bumps it:** only changes an older app could *misread* — new item
  types, changed geometry semantics. **What does NOT bump it:** additive
  top-level keys old builds ignore (`harvest_logs`, `task_states`,
  `manual_tasks`, `garden_journal_notes`, container/smart-symbol `metadata`,
  …). This additive-key convention is used by every Package C feature.
- **`paper_layouts` (deprecated):** written only by short-lived US-B7 draft
  builds; `from_dict` intentionally never consumes it (comment at line ~210),
  so those files still open.
- **Forward-compat rejection** (verified, `ProjectManager.load` ~line 962):
  `_is_newer_file_version(file_version, FILE_VERSION)` parses `X.Y`; strictly
  newer files raise `ValueError` ("created by a newer version… please update")
  instead of silently dropping unknown content on the next save. Unparseable
  or missing version strings are treated as *old* (returns `False`), so legacy
  files (e.g. "1.0" or no key) still load.

### Per-plan settings (live in the file, not QSettings)

`ProjectData` fields beyond geometry (`canvas_width/height`, `objects`,
`layers`, `constraints`, `guides`): `location` (geo metadata incl. the
satellite-picker scale/coords), `season_year` + `linked_seasons`,
`task_completions` (write-only compat mirror since #230 — read `task_states`),
`seed_inventory`, `propagation_overrides`, `crop_rotation`, `soil_tests`,
`pest_disease_logs`, `shopping_list_prices`, `excluded_shopping_items`,
`enabled_amendments` (`None` = "all bundled amendments enabled" default) +
`prefer_organic` (default `True`), `succession_plans`,
`garden_journal_notes`, `manual_tasks`, `task_states`, `harvest_logs`.

Rule of thumb: user preference about the *app* → §1 QSettings; data or
preference about *this garden* → `ProjectData`.

---

## 5. Feature-visibility toggles in code (the "experimental flag" pattern)

This repo has no feature-flag framework; experiments ship dark via one-line
visibility calls.

| Toggle | Where | Status |
|---|---|---|
| **Smart Symbols sidebar panel hidden** | `application.py:5337` `set_panel_visible("smart_symbols", False)` | **experimental / deferred UI** (US-C4). Engine, persistence, DXF export, and properties editing all ship and are tested; symbols in existing `.ogp` files still regenerate. Re-enable by deleting that one line (the comment says exactly this). |
| Contextual panels hidden until relevant selection | `set_panel_visible(key, relevant)` for `plant_details` / `companion` / `crop_rotation` in the selection updaters (ADR-030) | production behavior — not a bug when they're absent with nothing selected |
| Satellite menu action disabled | `application.py:7868` `_update_satellite_menu_state` when both the Preferences key and `OGP_GOOGLE_MAPS_KEY` are unset (§3) | production guard |
| Nearest / perpendicular / tangent snap default-OFF | §1 snap table | production, opt-in |
| **3D view in compatibility mode (software rendering), or switched off** | `ui/view3d/init_guard.py`: the last start of 3D died before its first frame (a start marker was left), or the user chose "Use Compatibility Mode Next Time"; a start that died in compatibility mode too switches 3D off | production safety net (ADR-065; the default since L1.9 — there is no switch): the 3D pane says so and offers "Try Hardware Next Time" (FR-3D-WS-07). The flag file `view3d-compat.flag` and the markers `view3d-init-<pid>.marker` sit next to `app.log` |

If "a feature seems disabled", check this table before debugging.

---

## 6. Tooling configuration

### pyproject.toml (verified in full)

| Section | Contents |
|---|---|
| `[tool.ruff]` | `target-version = "py311"`, `line-length = 100`, `src = ["src", "tests"]` |
| `[tool.ruff.lint]` | select `E, W, F, I, B, C4, UP, ARG, SIM`; ignore `E501`, `B008` |
| per-file ignores | `tests/**/*.py` → `ARG001, ARG002` (unused-but-required `qtbot` fixtures) |
| `[tool.mypy]` | `strict = true` (+ the usual disallow/warn set), `follow_imports = "silent"`, `ignore_missing_imports = true`; `tests.*` override relaxes `disallow_untyped_defs` |
| `[tool.pytest.ini_options]` | `testpaths = ["tests"]`, `addopts = "-v --tb=short -n auto --dist worksteal -m 'not perf'"`, `qt_api = "pyqt6"` |
| `[tool.coverage]` | `source = src/open_garden_planner`, `branch = true`, standard exclude lines |

### Dependency pins worth knowing (pyproject `dependencies`)

| Pin | Rationale (from the in-file comment, verified) |
|---|---|
| `PyQt6-WebEngine>=6.10.0,<6.11` | upper-bound pin (needed by the map picker's `QWebEngineView`; must be imported before `QApplication` — `main.py`) |
| `mcp>=1.23,<2.0` | "Pinned to mcp v1 — v2 renames `FastMCP` -> `MCPServer`." uvicorn/starlette/pydantic/anyio/sse-starlette come transitively but are listed where used. |
| `uvicorn>=0.30`, `starlette>=0.37`, `pydantic>=2.11` | Agent API server stack |

**Removed (AUD-052, #454):** the stale top-level requirement mirrors were deleted;
`pyproject.toml` (locked by `uv.lock` + `pylock.toml`) is the dependency source of truth.

### installer/ogp.spec knobs (verified; see docs/07 + §8.19 for narrative)

- `_safe_collect_submodules` over **concrete** MCP subpackages
  (`mcp.server`/`mcp.shared`/`mcp.types`, uvicorn, starlette, anyio,
  sse_starlette, pydantic, pydantic_settings, httpx_sse) — **never top-level
  `mcp`**: walking it imports `mcp.cli`, which `sys.exit(1)`s without the
  unbundled `typer` extra and aborts the build.
- Metadata: the spec bundles the whole **runtime closure** via
  `installer/runtime_closure.py` (`copy_metadata` per resolved distribution; the
  same resolver is read back by `scripts/generate_distribution_inventory.py`).
  Never add a hand-typed per-stack metadata list: a new dependency would silently
  leave the notices/SBOM inventory.
- `excludes` = tkinter/unittest/pydoc/doctest — with an explicit NOTE: **do NOT
  exclude `multiprocessing`** (uvicorn imports it eagerly; excluding it breaks
  the embedded Agent API).
- `upx_exclude = ["pydantic_core*.pyd"]` — UPX can corrupt that compiled
  extension.
- `console=False`; data trees copied: icons, textures, plants, objects,
  translations, data, web (map-picker HTML).

---

## 7. CI axes

### ci.yml (verified)

Three jobs on every branch push + PRs to master, all Python 3.11,
ubuntu-latest: **lint** (`ruff check src/`), **test** (apt Qt libs, then
`pytest tests/ -v` with env `QT_QPA_PLATFORM: offscreen`), **security**
(`bandit -r src/ --severity-level high`). No other env vars or secrets.

### release.yml (verified) — details in `ogp-change-control`

- Triggers on push to master; **chore-skip predicate**:
  `!startsWith(message, 'chore:') && !startsWith(message, 'chore(')` — the
  scoped form was added after `chore(finalize-us):` slipped through and
  wrongly cut a release.
- Version bump from the **labels of the most recently merged master PR**:
  label `major` → X+1.0.0, `minor` → Y+1, else **patch** (default). Skips
  cleanly if the computed tag already exists.
- Builds on windows-latest via `installer/build_installer.py`, NSIS installer +
  SHA256SUMS, `gh release create --generate-notes`. Never tag manually.

---

## 8. How to add a setting — checklist

Derived from `agent_api_enabled` (US-D1.1), whose every step verifiably exists;
copy that pattern.

1. **`settings.py`**: add `KEY_<NAME> = "group/key_name"` constant + a
   `DEFAULT_<NAME>` class constant (+ `MIN_/MAX_` if clamped) + a typed
   `@property`/setter pair reading `self._settings.value(KEY, DEFAULT,
   type=...)`. Clamp in **both** getter and setter if bounded (see
   `agent_api_port`, `autosave_interval_minutes`).
2. **Preferences UI** (`ui/dialogs/preferences_dialog.py`): add the widget in
   the right group box; **load** current value in the populate block (~line
   270), **save** in `_save_and_accept()` (ending with `settings.sync()`).
   Reference class constants for ranges (`AppSettings.MIN_AGENT_API_PORT`).
3. **i18n**: wrap every label/tooltip in `self.tr(...)` — no exceptions
   (AGENTS.md MUST).
4. **Register the strings** in `scripts/fill_translations.py` (the Agent API
   entries sit at ~lines 1875 and 2300), then run
   `PYTHONUTF8=1 venv/Scripts/python.exe scripts/fill_translations.py` and
   `compile_translations.py`;
   `pytest tests/unit/test_i18n.py::TestTranslationFiles::test_german_ts_has_no_unfinished`
   must pass.
5. **Wire the consumer**: react to the changed value where it takes effect. If
   it needs apply-on-OK, compare before/after around the dialog like
   `application.py` does for the Agent API (~line 3758) and restart/refresh
   the affected service.
6. **Tests**: lock the default with a unit test if it's a product decision
   (`tests/unit/test_agent_api_settings.py` asserts the class constants —
   note its rationale: autouse fixtures may override the runtime value, so
   assert the *constant*); add/extend an integration test for the behavior
   (`tests/integration/test_agent_api_default_on.py`).
7. **Docs**: FR entry if user-facing (`docs/functional-requirements.md`), ADR
   if it's a decision, §11.4 if you hit a pitfall — and **update this skill's
   §1 table**.
8. Follow `ogp-change-control` for branch/review/draft-PR gates.

Deciding where it lives: user-scoped app behavior → QSettings (this checklist);
plan-scoped → `ProjectData` field + `to_dict`/`from_dict` (additive key, no
FILE_VERSION bump — §4); pure UI geometry → `UiStateStore` (§2, but never panel
open-state, ADR-030).

---

## Provenance and maintenance

Re-verify each section before relying on it after significant time/version drift:

| Section | Command |
|---|---|
| §1 keys & defaults | `grep -n "KEY_\|DEFAULT_\|MIN_\|MAX_" src/open_garden_planner/app/settings.py` |
| §1 QSettings location | `grep -n "QSettings(" src/open_garden_planner/app/settings.py src/open_garden_planner/app/ui_state.py` |
| §1 theme trap | `grep -n "get_colors(ThemeMode.SYSTEM)" -r src/ docs/11-risks-and-technical-debt/` |
| §2 UiState keys | `grep -n "UiState\|setValue\|save_panel" src/open_garden_planner/app/ui_state.py` |
| §3 env loading | `sed -n '14,28p' src/open_garden_planner/main.py; grep -rn "OGP_GOOGLE_MAPS_KEY\|QT_QPA_PLATFORM" src/ tests/conftest.py .github/workflows/ci.yml` |
| §4 FILE_VERSION | `grep -n "FILE_VERSION\|_is_newer_file_version\|paper_layouts" src/open_garden_planner/core/project.py` |
| §5 hidden panel | `grep -n 'set_panel_visible("smart_symbols"' src/open_garden_planner/app/application.py` |
| §6 tooling | `grep -n "tool.ruff\|tool.mypy\|tool.pytest\|mcp>=\|WebEngine" pyproject.toml; grep -n "multiprocessing\|mcp.cli\|upx_exclude" installer/ogp.spec` |
| §7 CI | `grep -n "chore\|major\|minor\|QT_QPA_PLATFORM" .github/workflows/release.yml .github/workflows/ci.yml` |
| §8 exemplar | `grep -n "agent_api" src/open_garden_planner/ui/dialogs/preferences_dialog.py src/open_garden_planner/app/application.py` |

## Package F1/F2 configuration (ADR-054/055)

`ProjectData.auto_assign_permaculture_layers` is plan-scoped, default false, and
changed through `AutoAssignPermacultureCommand`. Matching uses the optional
`Layer.permaculture_layer` semantic tag, never translated/editable layer names.
Only existing visible/unlocked layers qualify; otherwise the normal active layer
is used. The preset adds missing tags in one undo step and keeps the active layer.
These are additive fields in `.ogp` 1.4.

User templates live under `get_app_data_dir()/guilds/*.json` (see
`services/guild_library.py`). User IDs override bundled IDs. Bad user files are
logged/skipped individually and shown with filename/reason in the picker. The
editor saves atomically and edits user files only; library edits do not enter plan
history or change already placed snapshots. No new environment variables or
QSettings keys are introduced.
