# Pitfalls: CI, release and supply chain

One entry per lesson, each under its permanent `PF-<AREA>-<NN>` ID. Each entry gives its rule, the test that pins it, its sources and its status. Index: [§11.4](../README.md#114-known-development-pitfalls).

### PF-CI-01

- **Rule:** Third-party attribution for the frozen build comes from the files PyInstaller actually collected, mapped through wheel RECORDs including vendored copies, not from declared dependencies.
- **Pinned by:** `tests/unit/test_frozen_inventory.py`; `tests/integration/test_distribution_inventory_pipeline.py::test_frozen_hook_dependencies_are_in_the_inventory`
- **Source:** #454, #490
- **Status:** standing
- **Legacy:** b1faaa9 README L112

- **Attribute frozen code from collected files, not only declared dependencies**
  (PR #490 / #454): the 47-component SBOM check passed while the executable's PYZ
  contained unreported setuptools, packaging, pytest/mypy dependencies and nested
  vendored libraries. `Requires-Dist` and a hardcoded hook exception did not describe
  what PyInstaller collected. `installer/frozen_inventory.py` now maps actual Analysis
  source paths through wheel RECORDs, with nested vendored precedence, and bundles
  those owners' metadata/licenses plus a module/file ownership manifest. The checker
  compares it with the executable PYZ and locks containing-wheel versions for vendored
  copies; declared license files must exist and their text must reach the notices.
  Pinned by `tests/unit/test_frozen_inventory.py` and
  `tests/integration/test_distribution_inventory_pipeline.py::test_frozen_hook_dependencies_are_in_the_inventory`
  (observed failing on the original artifact). Synthetic fixtures constructed from the
  expected closure prove orchestration, not complete frozen attribution.

### PF-CI-02

- **Rule:** Build inputs read the project's own dependencies from `pyproject.toml` and walk only third parties through installed metadata, because a stale `*.egg-info` on `sys.path` can shadow the project.
- **Pinned by:** none — The body names no test for this rule.
- **Source:** #454, #490
- **Status:** standing
- **Legacy:** b1faaa9 README L126

- **A stale `*.egg-info` on `sys.path` silently shrinks anything derived from installed metadata (#454, 2026-10-13).** The runtime-distribution resolver behind the release's third-party notices and SBOM returned **five** distributions (the project + `Pillow` + the three `PyQt6*` wheels) when a test ran it, but the same interpreter returned **48** when the module was run directly. Root cause: a legacy `src/open_garden_planner.egg-info` (version `0.1.0`, written years earlier) was still on disk; the editable install puts `src/` on `sys.path`, and `importlib.metadata.distribution("open-garden-planner")` returns the **first** match — so `Requires-Dist` described a two-year-old project. Two lessons. (1) **Check what `sys.path` order resolves** — when a metadata lookup disagrees with a file a human can read, print the distribution's `_path`; the answer is usually "you got a different distribution than you meant". (2) **Anchor build inputs on the manifest, not on the environment's copy of yourself**: the resolver now reads `[project].dependencies` from `pyproject.toml` and only walks *third parties* through installed metadata, so no stale artefact of the project's own history can change what ships. Related, same task: PyInstaller's `hook-importlib_metadata` bundles setuptools' **vendored** `importlib_metadata` (Apache-2.0) even though nothing declares it — the initial explicit hook exception was superseded in PR #490 by physical RECORD attribution of every collected wheel owner, including vendored copies (see the preceding pitfall).

### PF-CI-03

- **Rule:** A packaged build resolves the Google Maps key from Preferences first, then the environment or a `.env` beside the executable, and never bundles, serializes, logs or auto-copies the secret.
- **Pinned by:** none — The body says regression coverage pins key precedence and the menu refresh but names no test.
- **Source:** #342
- **Status:** standing
- **Legacy:** b1faaa9 README L203

- **A source checkout's `.env` is not automatically present in a packaged build, and a credential setting must not become a project secret.** The satellite picker originally read only `OGP_GOOGLE_MAPS_KEY`, so Python launches that loaded the repository `.env` worked while a frozen executable showed a disabled menu. The supported fallback remains the process environment or `.env` beside the executable. Issue #342 adds a Preferences value at `api_keys/google_maps_key`, with Preferences-first resolution and blank-field fallback to the environment. The key is intentionally absent from `.ogp` serialization, PyInstaller data, logs, and user-facing error details; never "fix" a frozen-build credential problem by bundling or auto-copying the secret. Regression coverage pins both resolution precedence and the immediate menu refresh after saving/clearing Preferences.

### PF-CI-04

- **Rule:** In a windowed frozen exe `sys.stdout` can be `None`, so uvicorn starts with `log_config=None`, and the frozen `--selftest` runs detached so no inherited stdout handle masks a regression.
- **Pinned by:** none — The body names only the frozen exe's `--selftest` release check, which is not a test under tests/.
- **Source:** #277, #291, #334
- **Status:** standing
- **Legacy:** b1faaa9 README L232

**A windowed PyInstaller build launched with no console has `sys.stdout is None`, and uvicorn's default log config dereferences it — the Agent API was dead in every released exe (issue #291, closed).** Symptom: the Preferences "Enable Agent API" box is ticked, nothing listens on the port, no error dialog appears, and "Connect AI Assistant…" reports *"the Agent API is currently disabled"* about an already-enabled feature. Works perfectly from source. **Root cause**: `console=False` (what we ship) allocates no console, so when the exe is launched detached — a double-click, or `Start-Process` — `sys.stdout`/`sys.stderr` are `None` (**not** unconditionally; see the correction below); `uvicorn.Config.__init__` calls `configure_logging()`, and uvicorn's default formatter does `self.use_colors = sys.stdout.isatty()` (`uvicorn/logging.py`), so `dictConfig` raises `ValueError: Unable to configure formatter 'default'` and the server never starts. **Fix**: pass `log_config=None` to `uvicorn.Config` — we want none of uvicorn's logging anyway (`log_level` and `access_log=False` are already set, the latter deliberately so the `?token=` query param never reaches a log). **Why it hid for six releases, three compounding reasons**: (1) the failure is caught by `_start_agent_api`'s `except Exception` → `logger.exception`, but **no logging handler is configured anywhere in this app**, and with `sys.stderr is None` even `logging.lastResort` is mute — the traceback is destroyed; (2) the only user-visible trace is an 8-second status-bar message; (3) every diagnostic instinct reaches for a `console=True` build, **which has a real stdout and therefore cannot reproduce it** — the observation changes the result. **Lessons**: a frozen-exe check that only asserts "the app survives 8 seconds" cannot see a silently-dead subsystem, which is why `--selftest` now starts the server and asserts it binds — the same reasoning that produced the Qt3D `--selftest` after #277. **Corrected 2026-08-19 (PR #334):** this entry previously said the windowed exe has `sys.stdout is None` *unconditionally*, so `--selftest` reproduced the shipping condition "for free". Measured: it does not. `console=False` means no console is *allocated*, but a redirected handle is still inherited — launched from a shell pipe the frozen exe wrote **~300 bytes to stdout**, so `sys.stdout` was a live pipe and a regression of the `log_config=None` fix would pass. The shipping condition needs **no inherited stdout handle**: launch it detached (`Start-Process -Wait -PassThru`, which is what `release.yml` does and what the gate lists now prescribe). The observation-changes-the-result trap in this very entry had a second storey; and when a UI message explains an absent thing, check whether the absence has more than one cause — `agent_api_running_url()` returning `None` meant both "switched off" and "failed to start", and the copy named only the first.



### PF-CI-05

- **Rule:** The release job skips commits whose message starts with `chore:`, so version-sync chore pushes cannot start a release that computes a stale version while the new tag is still building.
- **Pinned by:** none — The body names no test; the guard is the `if:` condition on the release job itself.
- **Source:** none recorded
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l270-release-workflow-race-condition-with-chore-commits)
- **Legacy:** b1faaa9 README L270

### PF-CI-06

- **Rule:** Retired: `PyQt6-3D-Qt6` had to be pinned to the exact `PyQt6-Qt6` micro version, with all four Qt wheels moving together, and the code no longer follows this rule.
- **Pinned by:** none — The entry is retired, and the guard its body names, tests/unit/test_qt3d_version_guard.py, no longer exists.
- **Source:** #274, #277
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l317-pyinstaller-frozen-exe-fails-to-load-qt3d-dlls-on-a-pyqt6-3d-qt6--pyqt6-qt6-micro-version-mismatch)
- **Legacy:** b1faaa9 README L317

### PF-CI-07

- **Rule:** File dialogs default to the open project's folder or `<Documents>/Open Garden Planner`, never the working directory, and the uninstaller copies `.ogp` files out of `$INSTDIR` before removing it.
- **Pinned by:** `tests/unit/test_paths.py`; `tests/integration/test_save_location.py`
- **Source:** #199
- **Status:** standing; narrative in [archive/12-incident-narratives.md](../archive/12-incident-narratives.md#archive-l354-never-default-a-file-dialog-into-the-install-directory-never-let-the-uninstaller-wipe-it-blind)
- **Legacy:** b1faaa9 README L354

### PF-CI-08

- **Rule:** Retired: a non-critical CI job that has never run green is deleted or repaired, never tolerated or muted with `continue-on-error`, and the workflow it concerned no longer exists.
- **Pinned by:** none — The entry is retired and its body names no test; the workflow it concerned was deleted.
- **Source:** #161, #293
- **Status:** retired; narrative in [archive/13-retired.md](../archive/13-retired.md#archive-l400-a-non-critical-ci-job-that-fails-permanently-is-indistinguishable-from-one-that-does-nothing--and-it-trains-everyone-to-scroll-past-the-actions-tab)
- **Legacy:** b1faaa9 README L400

### PF-CI-09

- **Rule:** A version-only `pyproject.toml` edit makes `uv.lock` stale, so the version-sync chore refreshes the lock's project version offline together with both source version declarations.
- **Pinned by:** `tests/integration/test_ci_quality_workflows.py::test_version_sync_cli_is_offline_transactional_and_idempotent`
- **Source:** #399, #402, #404, #417, #420, #422
- **Status:** standing
- **Legacy:** b1faaa9 README L2886

A version-only edit to `pyproject.toml` makes `uv.lock` stale. The measured probe failed
`uv lock --check --offline`, then `uv lock --offline` changed only the editable project's
version. `scripts/prepare_version_sync.py` stages and validates this refresh before applying
any source writes, compares full third-party records, and regenerates the export. The
version-sync chore must therefore include the lock alongside both source declarations.
Pinned by `test_version_sync_cli_is_offline_transactional_and_idempotent`.

Fresh baselines must use declared locked dependencies: the developer venv included undeclared
Qt stubs and older type/coverage tools. Linux and Windows also disagreed about one ignore: 229
were unused on both platforms, while one Windows-unused ignore remained needed on Linux.
Only common unused directives were removed; allowances are measured per platform. Pinned by
`test_baseline_keeps_platforms_independent_and_rejects_tool_drift`.


**Offline refresh is not the same as a universal re-resolve.** A cold locked Linux install
cached its selected wheels but lacked other-platform resolver metadata. Changing only the
project version triggered a re-resolve and failed offline; a freshness check did not fix it.
Version sync now stages the editable lock-record version before native offline validation,
then verifies all third-party records unchanged. The real subprocess test uses an empty cache
on both platforms. Underlying tool stderr must be reported; a process exit alone hid the cause.

**CI hardening review findings (#404/#402/#399).** A fresh Windows checkout changed the export's
1,857 LF endings to CRLF; a working-copy byte check missed it. Generated locks now have explicit
LF attributes. Coverage records must have unique normalized file/line identities and supplied
summary counts must agree with aggregates, or duplicated XML statements can inflate a floor.
An injected second-file write failure verifies full version-sync rollback. Release recovery
resolves a published tag and successful workflow from the feature merge SHA; tag transition
is required only when observing a new merge, so restart after publication can finish normally.
The isolated protection PR #420 rejected its failing head and merged its corrected green head
without a bypass under the proposed admin-enforced policy; temporary branches/policy were
removed. Master enforcement was activated and verified before PR #422 merged normally. Evidence: quality/protection-validation.json.

**Hosted update tooling can lag a reproducible CI pin (2026-10-09).** The first security
update attempt failed with `tool_version_not_supported`: detected uv `==0.12.23`, supported
uv `0.12.18`. Evidence: [Dependabot run 37951191628](https://github.com/cofade/open-garden-planner/actions/runs/37951191628).
The project CI and release used the agreed pinned tool successfully. Preserve the pin and
perform the setuptools advisory update in a separately reviewed manual dependency PR;
automatic security-update support is unresolved, not a successful remediation. An exact
bootstrap pin must be checked against hosted update tooling as well as installation tooling.

**Unicode CLI output needs an explicit stream encoding** (issue #417): UTF-8 wiki files did not prevent redirected Windows stdout from using cp1252. The comparison command emitted byte 0x96 for an en dash and failed to encode a check mark. `scripts/sync_wiki.py` now sets stdout and stderr to UTF-8 before printing. The subprocess comparison regression in `tests/integration/test_wiki_publication.py` captures real Unicode diffs without a UTF-8 environment override.

### PF-CI-10

- **Rule:** Release version bump derives from the triggering merge commit SHA (via `scripts/resolve_release_pr.py` with commit pulls lookup, squash subject `(#N)` fallback, and exact label matching), never from `gh pr list --state merged` which sorts by creation date and ignores older-created PRs.
- **Pinned by:** `tests/unit/test_release_version.py`
- **Source:** #484, #543
- **Status:** standing
- **Legacy:** none

**Release version determination must resolve the triggering merge commit, not the latest-created PR (#543, 2026-10-20).** PR #484 (Phase 17 L1) carried the `minor` label when merged as `bf4fd77a`, but `release.yml` published `v1.30.14` (patch) instead of `v1.31.0`. `gh pr list --state merged --base master --limit 1` sorts by PR creation date (`createdAt` descending), not merge time. Because PR #484 was created weeks earlier in September, it was shadowed by PR #521 (created and merged earlier on the same day without a label). Additionally, loose `grep -q` used substring matching. Resolution: `release.yml` delegates version determination to `scripts/resolve_release_pr.py --write-github-output`, which resolves the triggering commit SHA via `gh api repos/{repo}/commits/{commit_sha}/pulls` filtering for master merges, falls back to extracting `(#N)` from the commit subject line, and evaluates bump types using exact label matching.


### PF-CI-11

- **Rule:** Windows executables, installers, and desktop shortcuts require multi-resolution `.ico` files containing all standard frames (16x16 to 256x256), and `SetCurrentProcessExplicitAppUserModelID` must be called before any GUI or WebEngine subsystem imports; an icon with only 16x16 leaves the Windows taskbar with a generic blank window icon.
- **Pinned by:** `tests/unit/test_app_icons.py`
- **Source:** #545
- **Status:** standing
- **Legacy:** none

**Windows taskbar icon requires multi-resolution icon frames and early AppUserModelID initialization (#545, 2026-10-21).** Running the packaged frozen executable or Python module on Windows 11 showed a generic blank application icon in the taskbar instead of the Open Garden Planner logo. Root causes: (1) `installer/ogp_app.ico` and `installer/ogp_file.ico` originally contained only a single 16x16 icon frame (710 bytes); Windows taskbars require 24x24, 32x32, or 48x48 (depending on DPI scaling) and discard incomplete icons. (2) In `main.py`, `SetCurrentProcessExplicitAppUserModelID` was invoked after importing `QtWebEngineWidgets`, which initializes Chromium helper windows before the AppUserModelID is established. (3) Windows 11 Explorer aggressively caches blank taskbar states per AppUserModelID; reusing an identifier that failed initially maintains the blank icon. (4) Qt registers the window class with `LoadIcon(NULL, IDI_APPLICATION)` (`0x1002b`); if no Start Menu shortcut is installed, Windows Explorer taskbars fall back to `GCLP_HICON` unless native window class icons (`GCLP_HICON`, `GCLP_HICONSM`), window messages (`WM_SETICON`), and `System.AppUserModel.RelaunchIconResource` (`PKEY_AppUserModel_RelaunchIconResource`) are explicitly stamped on the window's COM `IPropertyStore`. Resolution: `scripts/generate_app_icons.py` generates multi-resolution `.ico` files with all 7 standard Windows frames (16, 24, 32, 48, 64, 128, 256); `SetCurrentProcessExplicitAppUserModelID` runs at process entry before any GUI imports with fresh AppID `cofade.opengardenplanner.app`; `GardenPlannerApp` and `WelcomeDialog` set window icons explicitly; `open_garden_planner.app.win32_taskbar` configures `WM_SETICON`, class icons, and window `IPropertyStore` relaunch properties. Pinned by `tests/unit/test_app_icons.py` and `--selftest`.


### PF-CI-12

- **Rule:** The required `Dependencies` job audits against a live advisory database, so it can turn `master` red with no code change; answer with a targeted `uv lock --upgrade-package` per named package (never a full upgrade), and let CI waive only the advisories named in the governance test's `WAIVERS` and justified in §11.2.
- **Pinned by:** `tests/unit/test_dependency_governance.py::test_ci_audits_the_locked_closure_on_every_shipped_platform`
- **Source:** #571, #572
- **Status:** standing
- **Legacy:** none

**A live advisory database fails a required check with no code change (#571, 2026-10-24).** `master` (`50324280`) went red on `Dependencies (ubuntu-latest)` and `Dependencies (windows-latest)` — both required — on GHSA-xmj3-9gf7-h52w (setuptools < 84.1.0), so no PR could pass branch protection. CI at 22:12Z on 2026-10-23 saw one advisory; a local run of the same command hours later saw seven (six more in `filelock` 4.2.0, a dev-only package reached through `pip-audit` → `cachecontrol[filecache]`). Dependabot could not open the fix: its uv (0.12.19) is older than the project's `==0.12.23` pin (the 2026-10-09 note under PF-CI-09). Resolution: pin the build group's setuptools to the first patched version and move only the named packages with `uv lock --upgrade-package` (the deployment view's runbook now has this path), re-export `pylock.toml`, re-run `pip-audit` and rebuild the frozen bundle. The fix also covered the advisory behind the one standing waiver (`PYSEC-2026-3447`, fixed in 83.0.0), so the waiver ended too: a waiver that matches nothing would hide that advisory if its range were ever widened. `test_dependency_governance.py::WAIVERS` now names every allowed waiver (none): the test requires CI's whole `pip-audit` command line to be the plain command plus exactly those waivers, so neither an abbreviated `--ignore` nor `|| true` slips in. It does not check that a waived advisory still matches the lock — ending a waiver whose advisory was fixed stays a review duty (the 2026-10-24 case was found by reading the audit output).

### PF-CI-13

- **Rule:** A local frozen build must compare the build venv with `pylock.toml` and warn (strictly fail on request) when it holds a distribution the lock no longer pins. Removing a pin does not uninstall the package, and PyInstaller's hooks can collect its files even when the application never imports it.
- **Pinned by:** `tests/unit/test_build_environment.py`
- **Source:** #538
- **Status:** standing
- **Legacy:** none (new entry)

### PF-CI-14

- **Rule:** The project license is a PEP 639 SPDX expression (`license = "GPL-3.0-or-later"`) plus `license-files = ["LICENSE"]`, with no `License ::` classifier, and the build floor is `setuptools>=77`. An isolated build (`[build-system] requires`) floats, so the build group's pin alone does not protect it.
- **Pinned by:** `tests/unit/test_packaging_metadata.py`; `tests/unit/test_main_hardening.py`
- **Source:** #574
- **Status:** standing
- **Legacy:** none (new entry)

setuptools 82/84 emits `SetuptoolsDeprecationWarning` with a 2027-02-18 due date for a `{text = ...}` license table and for a license classifier beside an SPDX expression. The wheel built without isolation and with `uv build` now carries `Metadata-Version: 2.4`, `License-Expression: GPL-3.0-or-later`, `License-File: LICENSE`, and the LICENSE itself under `dist-info/licenses/`, with no warning. The floor matters because an isolated `pip install .` resolves the newest setuptools regardless of the build group.

### PF-CI-15

- **Rule:** `_version.py` is a build artifact, not source: `build_installer.py` writes it before PyInstaller and removes it afterwards, and the path is gitignored. A direct `python -m PyInstaller installer/ogp.spec` build has no such file, and the frozen app must fall back to `open_garden_planner.__version__`. The read is DYNAMIC, so PyInstaller cannot discover it: the spec lists `open_garden_planner._version` as a hidden import only when the file exists, or a release exe would report the previous synced version. A tracked or left-behind stale file lets a green build show the wrong version in About.
- **Pinned by:** `tests/unit/test_packaging_metadata.py`
- **Source:** #596 manual pass (AUD-072)
- **Status:** standing
- **Legacy:** none (new entry)

The About dialog in a direct PyInstaller build said **1.2.0** while `pyproject.toml` and `__init__.py` said 1.31.1. The cause was a tracked `_version.py` from 2026-03-01 that `build_installer.py` overwrote only on the release path; the direct gate bundled the stale file. The script now also deletes the module in a `finally` after PyInstaller, so a release build cannot leave it behind for a later direct build. The freeze/fallback path is pinned by monkeypatching `sys.frozen` and removing `open_garden_planner._version` from `sys.modules`; the release direction is pinned by injecting a module whose `__version__` differs from the package's. `installer/ogp.spec` grew the conditional hidden import in the same change, because the dynamic import removed the static edge PyInstaller used to follow; `test_packaging_metadata.py` pins the write/remove pair, the fallback, the release direction and the spec line; `tests/unit/test_main_hardening.py` pins the `--selftest` version check against `OGP_EXPECTED_VERSION`.


### PF-CI-16

- **Rule:** A required coverage check must require every measurement to succeed and combine every explicitly named partition, including serial perf coverage; failed, skipped or missing inputs must fail the check.
- **Pinned by:** `tests/unit/test_gate_commands.py::test_coverage_shards_and_merge_are_pinned`; `tests/unit/test_gate_commands.py::test_coverage_topology_pin_rejects_incomplete_measurements`
- **Source:** #601; ADR-058
- **Status:** pointer → [§8.10.4](../../08-crosscutting-concepts/README.md#8104-the-inner-loop-and-which-run-is-the-gate-509)
- **Legacy:** none (new entry)
