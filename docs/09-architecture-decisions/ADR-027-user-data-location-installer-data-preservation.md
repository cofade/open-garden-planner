---
id: ADR-027
title: "User-Data Location & Installer Data Preservation"
status: "Accepted (issue #199)"
legacy_anchor: adr-027-user-data-location--installer-data-preservation
---

# ADR-027: User-Data Location & Installer Data Preservation

**Status**: Accepted (issue #199)

**Context**: A user reported that updating to v1.13.0 deleted every `.ogp` plan they had stored under `C:\Program Files (x86)\Open Garden Planner`. Two independent defects combine to destroy data: (1) the app's `QFileDialog.getSaveFileName`/`getOpenFileName` calls passed `""` as the *directory* argument, so the dialogs open in the process **current working directory** — for a packaged PyInstaller/NSIS build that is the install folder — and users naturally saved their plans where the dialog opened; (2) the NSIS uninstaller runs `RMDir /r "$INSTDIR"`, and the upgrade flow in `.onInit` silently invokes the *old* uninstaller before installing the new build (`ExecWait '$R0 /S _?=$INSTDIR'`), so an in-place update wipes the whole install directory — user plans included.

**Decision**:
1. **User data never defaults under the install directory.** A new `app/paths.py` exposes `get_projects_dir()` → `<Documents>/Open Garden Planner` (resolved via `QStandardPaths.DocumentsLocation`, fallback `~/Documents`), created on first use. This mirrors the existing `services/plant_library.get_app_data_dir()` pattern but targets the user-visible Documents location rather than AppData, because these are documents the user opens and manages directly.
2. **One chokepoint resolves a safe start directory.** `app/paths.default_dialog_dir(current_file)` returns the folder of the open project when one is loaded (so users stay where they last worked), otherwise `get_projects_dir()`; `default_save_path(filename, current_file)` joins it with a default filename. **Every** `QFileDialog` call in the app routes through these — the main-window dialogs (`.ogp` save/open, PNG/SVG/CSV/DXF/PDF export, DXF/background-image import) via `GardenPlannerApp._default_dialog_dir()`/`_default_save_path()`, and the standalone dialogs (shopping-list CSV/PDF export, season-manager new-`.ogp`, journal/pest-log photo pickers) by calling the module helpers directly. None pass `""` or a bare relative filename any more. Centralising in `paths.py` (rather than per-call-site reminders) is deliberate: the original fix missed five call sites precisely because the convention lived only in `application.py`.
3. **The installer treats `$INSTDIR` as possibly containing user files.** Before `RMDir /r`, the uninstall section copies any top-level `$INSTDIR\*.ogp` to a `Recovered Plans` subfolder *inside* the app's default projects folder (`$DOCUMENTS\Open Garden Planner\Recovered Plans`) — one level down from where new saves land, so recovered files sit alongside the user's plans without clobbering them and their provenance is obvious. Because the silent upgrade path executes this same uninstall section, the backup protects pre-existing victims on their *next* update as well as manual uninstalls; a `MessageBox` reports recovered files and carries `/SD IDOK` so silent (`/S`) upgrades auto-dismiss it instead of hanging on an invisible modal (NSIS does **not** auto-suppress a bare `MessageBox` under `/S`).

**Alternatives considered**:
- *Remember the last-used directory in `QSettings`* — rejected as the primary mechanism in favour of a single, predictable, discoverable folder (the user picked the dedicated-folder option); the current-project-folder heuristic already covers "stay where I was working" within a session.
- *Make the NSIS uninstaller delete only an explicit file manifest instead of `RMDir /r`* — rejected for v1: the bundle is installed with `File /r` (hundreds of unenumerated files), so a manifest is brittle. Backing up `*.ogp` before the recursive delete is a smaller, robust safety net.
- *App-startup migration that scans the old install dir and offers to move files out* — deferred; the installer backup already rescues users at their next upgrade. Can be added later if needed.

**Consequences**: New plans/exports land in `Documents\Open Garden Planner`; updates and uninstalls no longer silently destroy plans saved in the install folder. Adds `src/open_garden_planner/app/paths.py` and `_default_dialog_dir()`/`_default_save_path()` helpers in `application.py`; edits the NSIS uninstall section. No `.ogp` format change. Tests: `tests/unit/test_paths.py` (projects dir resolution + creation + fallback) and `tests/integration/test_save_location.py` (dialogs start in the projects dir, and follow the open project's folder). The NSIS backup is Windows-only and verified manually (drop a `.ogp` in `$INSTDIR`, run a new setup, confirm it reappears under `Recovered Plans`).
